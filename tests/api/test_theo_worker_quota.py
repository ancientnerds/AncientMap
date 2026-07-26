"""Quota-awareness of the Theo worker (2026-07-06 fixes).

Three behaviors born from the failed E2E of 2026-07-05:
1. The stall guard must not kill a run whose counters are frozen because
   the LIMITER is frozen (sleeping out a quota trough is not a stall).
2. A run that dies with the quota flag set must be 'deferred', not
   'failed' — the event bus swallows QuotaExhaustedError into ctx.error,
   so the worker needs ctx.quota_exhausted to route correctly.
3. Batch rows may only be claimed while the watchdog reports HEALTHY —
   starting a fresh multi-hour run into a half-drained window is wasted
   budget.
"""

import asyncio
from types import SimpleNamespace

import pytest

from api.services import theo_worker as tw

# --- 1. Stall guard ignores limiter-frozen time -----------------------------


@pytest.mark.asyncio
async def test_stall_guard_spares_run_while_limiter_frozen(monkeypatch):
    """Frozen counters + frozen limiter = quota pause, NOT a stall."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))  # never moves
    monkeypatch.setattr(tw, "_limiter_frozen", lambda: True)  # quota pause
    monkeypatch.setattr(tw, "_read_limiter_activity", lambda is_batch: 0)  # static

    async def fake_process(rid, q, opts, is_batch=False):
        await asyncio.sleep(0.6)  # well past the grace window
        return None

    monkeypatch.setattr(tw, "_process_request", fake_process)

    await tw._run_with_stall_guard("rid", "q", None, False)  # must not raise


@pytest.mark.asyncio
async def test_stall_guard_still_kills_frozen_run_when_limiter_healthy(monkeypatch):
    """Control: limiter NOT frozen and NOT ticking, frozen counters stall-kill."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))
    monkeypatch.setattr(tw, "_limiter_frozen", lambda: False)
    monkeypatch.setattr(tw, "_read_limiter_activity", lambda is_batch: 0)  # static

    async def fake_process(rid, q, opts, is_batch=False):
        await asyncio.sleep(100)

    monkeypatch.setattr(tw, "_process_request", fake_process)

    with pytest.raises(tw._StallDetected):
        await tw._run_with_stall_guard("rid", "q", None, False)


@pytest.mark.asyncio
async def test_stall_guard_spares_run_while_limiter_ticking(monkeypatch):
    """2026-07-19: DB counters only flush on event emissions, and event gaps
    stretch past the grace window when the limiter crawls after a quota
    trough (observed live: 16min gap vs 45min grace; ee3493e8 on 07-13 was
    almost certainly killed this way with 349 calls / 1M tokens on the
    clock). The limiter's total_requests counter is a direct liveness
    signal: while it keeps climbing, LLM calls are flowing and the run is
    NOT stalled — no matter what the DB sig says."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))  # never moves
    monkeypatch.setattr(tw, "_limiter_frozen", lambda: False)

    ticks = {"n": 0}

    def climbing_activity(is_batch):
        ticks["n"] += 1
        return ticks["n"]

    monkeypatch.setattr(tw, "_read_limiter_activity", climbing_activity)

    async def fake_process(rid, q, opts, is_batch=False):
        await asyncio.sleep(0.6)  # well past the grace window
        return None

    monkeypatch.setattr(tw, "_process_request", fake_process)

    await tw._run_with_stall_guard("rid", "q", None, False)  # must not raise


# --- 2. Terminal status routing ---------------------------------------------


def test_terminal_status_cancelled_wins():
    ctx = SimpleNamespace(error="Run cancelled by user", quota_exhausted=True)
    assert tw._terminal_status_for_error(ctx) == "cancelled"


def test_terminal_status_quota_flag_defers():
    ctx = SimpleNamespace(
        error="Handler failed on ContentFetched: QuotaExhaustedError('...')",
        quota_exhausted=True,
    )
    assert tw._terminal_status_for_error(ctx) == "deferred"


def test_terminal_status_plain_error_fails():
    ctx = SimpleNamespace(error="Decomposition produced no research angles", quota_exhausted=False)
    assert tw._terminal_status_for_error(ctx) == "failed"


def test_terminal_status_without_flag_attribute_fails():
    """Old ctx objects without the flag must still route to 'failed'."""
    ctx = SimpleNamespace(error="boom")
    assert tw._terminal_status_for_error(ctx) == "failed"


# --- 3. Batch claims require HEALTHY watchdog + weekly headroom --------------
# 2026-07-19: tier alone is not enough — a paper costs ~19% of the weekly
# budget, so starting a batch run with less than THEO_BATCH_MIN_WEEKLY_PCT
# remaining just parks it in the weekly wall mid-run. None = probe carried
# no weekly value: batch runs never start blind.


@pytest.mark.parametrize(
    "gate_open,tier,weekly,expected",
    [
        (True, "HEALTHY", 100, True),
        (True, "HEALTHY", 25, True),  # boundary: exactly the floor
        (True, "HEALTHY", 24.9, False),  # below the floor: paper won't fit
        (True, "HEALTHY", 0, False),  # the 07-08..07-12 wall
        (True, "HEALTHY", None, False),  # probe blind: never start blind
        (True, "DEGRADED", 100, False),
        (True, "EXHAUSTED", 100, False),
        (True, "UNKNOWN", 100, False),
        (False, "HEALTHY", 100, False),
    ],
)
def test_batch_claim_allowed(gate_open, tier, weekly, expected):
    assert tw._batch_claim_allowed(gate_open, tier, weekly) is expected
