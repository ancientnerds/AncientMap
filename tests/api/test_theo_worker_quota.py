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

    async def fake_process(rid, q, opts):
        await asyncio.sleep(0.6)  # well past the grace window
        return None

    monkeypatch.setattr(tw, "_process_request", fake_process)

    await tw._run_with_stall_guard("rid", "q", None)  # must not raise


@pytest.mark.asyncio
async def test_stall_guard_still_kills_frozen_run_when_limiter_healthy(monkeypatch):
    """Control: with the limiter NOT frozen, frozen counters still stall-kill."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))
    monkeypatch.setattr(tw, "_limiter_frozen", lambda: False)

    async def fake_process(rid, q, opts):
        await asyncio.sleep(100)

    monkeypatch.setattr(tw, "_process_request", fake_process)

    with pytest.raises(tw._StallDetected):
        await tw._run_with_stall_guard("rid", "q", None)


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


# --- 3. Batch claims require a HEALTHY watchdog ------------------------------


@pytest.mark.parametrize(
    "gate_open,tier,expected",
    [
        (True, "HEALTHY", True),
        (True, "DEGRADED", False),
        (True, "EXHAUSTED", False),
        (True, "UNKNOWN", False),
        (False, "HEALTHY", False),
    ],
)
def test_batch_claim_allowed(gate_open, tier, expected):
    assert tw._batch_claim_allowed(gate_open, tier) is expected
