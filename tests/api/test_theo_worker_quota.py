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
from datetime import UTC, datetime, timezone
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


# A Friday noon — 60h before the Monday 00:00 UTC reset, comfortably inside
# the default end-of-week window, so these cases test the gate/tier logic in
# isolation. avg_run_hours is injected so no DB read happens in tests.
_FRIDAY = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
_RUN_H = 18.0


@pytest.mark.parametrize(
    "gate_open,tier,weekly,expected",
    [
        (True, "HEALTHY", 100, True),
        (True, "HEALTHY", 0, False),  # the 07-08..07-12 wall
        (True, "HEALTHY", None, False),  # probe blind: never start blind
        (True, "DEGRADED", 100, False),
        (True, "EXHAUSTED", 100, False),
        (True, "UNKNOWN", 100, False),
        (False, "HEALTHY", 100, False),
    ],
)
def test_batch_claim_allowed(gate_open, tier, weekly, expected):
    assert (
        tw._batch_claim_allowed(gate_open, tier, weekly, now_utc=_FRIDAY, avg_run_hours=_RUN_H)
        is expected
    )


# --- 4. End-of-week batch window: day x budget x measured speed --------------
# 2026-08-04: the weekly budget resets Monday 00:00 UTC and the feeder had
# burned it to 50% by Tuesday. Batch starts (Entität queue + Dauerforscher)
# are gated on three adaptive conditions: <=3 days to the reset, the run
# fits before the reset at the MEASURED batch-run speed, and the weekly
# budget covers one paper (25%) plus 5%/remaining-day Lyra reserve.


def _claim(now, weekly=100, run_h=_RUN_H):
    return tw._batch_claim_allowed(True, "HEALTHY", weekly, now_utc=now, avg_run_hours=run_h)


def test_window_closed_early_week():
    # Monday through Thursday: >3 days to the reset — the fresh budget
    # belongs to Lyra and interactive research, regardless of how full it is.
    assert _claim(datetime(2026, 8, 3, 0, 1, tzinfo=UTC)) is False  # Mon
    assert _claim(datetime(2026, 8, 4, 12, 0, tzinfo=UTC)) is False  # Tue
    assert _claim(datetime(2026, 8, 6, 23, 59, tzinfo=UTC)) is False  # Thu 23:59


def test_window_opens_friday():
    # Fri 00:00 = exactly 3.0 days to reset. Required budget:
    # 25 (paper) + 3.0 * 5 (Lyra reserve) = 40.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    assert _claim(fri, weekly=100) is True
    assert _claim(fri, weekly=41) is True
    assert _claim(fri, weekly=39) is False  # surplus too small for Friday


def test_required_budget_shrinks_toward_reset():
    # The SAME 35% weekly is not enough on Friday (needs 40) but fine on
    # Saturday noon (36h left -> 25 + 1.5*5 = 32.5): closer to the reset,
    # less of the budget must stay reserved.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    sat_noon = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    assert _claim(fri, weekly=35) is False
    assert _claim(sat_noon, weekly=35) is True


def test_run_must_fit_before_reset():
    # Sunday 05:00 = 19h left: an 18h paper still fits, so the start is
    # allowed — but a slow Theo (30h average) is already cut off Saturday
    # night, and Sunday 08:00 (16h left) blocks even the 18h pace.
    sun_early = datetime(2026, 8, 9, 5, 0, tzinfo=UTC)
    sun_morning = datetime(2026, 8, 9, 8, 0, tzinfo=UTC)
    sat_night = datetime(2026, 8, 8, 22, 0, tzinfo=UTC)  # 26h left
    assert _claim(sun_early, run_h=18.0) is True
    assert _claim(sun_morning, run_h=18.0) is False
    assert _claim(sat_night, run_h=30.0) is False
    assert _claim(sat_night, run_h=18.0) is True


def test_fast_theo_extends_the_window():
    # A 6h pace keeps Sunday afternoon open (7h left >= 6h, required
    # 25 + 0.29*5 ~= 26.5).
    sun_afternoon = datetime(2026, 8, 9, 17, 0, tzinfo=UTC)
    assert _claim(sun_afternoon, weekly=30, run_h=6.0) is True
    assert _claim(sun_afternoon, weekly=30, run_h=8.0) is False


def test_hard_floor_still_applies():
    # THEO_BATCH_MIN_WEEKLY_PCT (25) is a safety net below the dynamic
    # requirement — right before the reset the dynamic requirement tends
    # toward the paper cost alone, never below the floor.
    sun_late = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)
    assert _claim(sun_late, weekly=24, run_h=2.0) is False


def test_window_env_override(monkeypatch):
    """MAX_DAYS_TO_RESET=7 restores always-on starts (budget still applies)."""
    monkeypatch.setattr("api.services.theo_config.THEO_BATCH_MAX_DAYS_TO_RESET", 7.0)
    monday = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    # 6.5 days to reset -> required 25 + 6.5*5 = 57.5
    assert _claim(monday, weekly=100) is True
    assert _claim(monday, weekly=50) is False


def test_hours_until_weekly_reset():
    # Fri 00:00 -> exactly 72h; Monday just after the reset -> almost a
    # full week (the reset that just passed must not count).
    assert tw._hours_until_weekly_reset(datetime(2026, 8, 7, 0, 0, tzinfo=UTC)) == 72.0
    almost_week = tw._hours_until_weekly_reset(datetime(2026, 8, 3, 0, 1, tzinfo=UTC))
    assert 167.9 < almost_week < 168.0
