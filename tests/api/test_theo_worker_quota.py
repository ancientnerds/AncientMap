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
# 2026-07-19: tier alone is not enough — a paper costs ~19-25% of the weekly
# budget, so a batch start must fit the remaining budget or it parks in the
# weekly wall mid-run. None = probe carried no weekly value: batch runs
# never start blind.


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
# are gated on two adaptive conditions: <=3 days to the reset, and the
# weekly budget covers the PRE-RESET SHARE of one paper (12% at the
# measured batch-run pace — calibrated 2026-08-08 from the first real
# plan-token measurement, was an eyeballed 25) plus 5%/remaining-day
# Lyra reserve. The last
# run of the weekend may cross the reset onto Monday's fresh budget — the
# weekly must just never hit 0% mid-run (that aborts runs).


def _claim(now, weekly=100, run_h=_RUN_H):
    return tw._batch_claim_allowed(True, "HEALTHY", weekly, now_utc=now, avg_run_hours=run_h)


def test_window_closed_early_week():
    # Monday through Thursday: >3 days to the reset — the fresh budget
    # belongs to Lyra and interactive research, regardless of how full it is.
    assert _claim(datetime(2026, 8, 3, 0, 1, tzinfo=UTC)) is False  # Mon
    assert _claim(datetime(2026, 8, 4, 12, 0, tzinfo=UTC)) is False  # Tue
    assert _claim(datetime(2026, 8, 6, 23, 59, tzinfo=UTC)) is False  # Thu 23:59


def test_window_opens_friday():
    # Fri 00:00 = exactly 3.0 days to reset. An 18h paper burns entirely
    # before the reset -> required = 12 (paper) + 3.0 * 5 (Lyra) = 27.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    assert _claim(fri, weekly=100) is True
    assert _claim(fri, weekly=28) is True
    assert _claim(fri, weekly=26) is False  # surplus too small for Friday


def test_required_budget_shrinks_toward_reset():
    # The SAME 22% weekly is not enough on Friday (needs 27) but fine on
    # Saturday noon (36h left -> 12 + 1.5*5 = 19.5): closer to the reset,
    # less of the budget must stay reserved.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    sat_noon = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    assert _claim(fri, weekly=22) is False
    assert _claim(sat_noon, weekly=22) is True


def test_last_run_may_cross_the_reset():
    # Sunday 20:00 = 4h left. An 18h paper burns only 4/18 of its cost
    # before the reset -> required = 12*0.222 + 0.167*5 ~= 3.5. Even a
    # nearly-drained week can still launch the weekend's last run — it
    # finishes on Monday's fresh budget, and Monday itself allows no NEW
    # starts (window closed).
    sun_evening = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)
    assert _claim(sun_evening, weekly=10) is True
    assert _claim(sun_evening, weekly=3) is False  # pre-reset share won't fit


def test_measured_pace_scales_pre_reset_share():
    # Sat 22:00 = 26h left. An 18h paper fits entirely before the reset
    # (required 12 + 1.083*5 ~= 17.4); a slow 30h paper defers 4/30 of its
    # burn past the reset (required 12*0.867 + 5.4 ~= 15.8). weekly=16.5
    # sits exactly between the two.
    sat_night = datetime(2026, 8, 8, 22, 0, tzinfo=UTC)
    assert _claim(sat_night, weekly=16.5, run_h=18.0) is False
    assert _claim(sat_night, weekly=16.5, run_h=30.0) is True


def test_never_starts_into_empty_weekly():
    # Sun 23:00 = 1h left: even the tiniest pre-reset share (1/18 of a
    # paper ~= 0.7% + reserve) must fit — the weekly hitting 0% mid-run
    # aborts the run and freezes the shared plan.
    sun_late = datetime(2026, 8, 9, 23, 0, tzinfo=UTC)
    assert _claim(sun_late, weekly=2) is True
    assert _claim(sun_late, weekly=0.5) is False


def test_window_env_override(monkeypatch):
    """MAX_DAYS_TO_RESET=7 restores always-on starts (budget still applies)."""
    monkeypatch.setattr("api.services.theo_config.THEO_BATCH_MAX_DAYS_TO_RESET", 7.0)
    monday = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    # 6.5 days to reset -> required 12 + 6.5*5 = 44.5
    assert _claim(monday, weekly=100) is True
    assert _claim(monday, weekly=40) is False


def test_hours_until_weekly_reset():
    # Fri 00:00 -> exactly 72h; Monday just after the reset -> almost a
    # full week (the reset that just passed must not count).
    assert tw._hours_until_weekly_reset(datetime(2026, 8, 7, 0, 0, tzinfo=UTC)) == 72.0
    almost_week = tw._hours_until_weekly_reset(datetime(2026, 8, 3, 0, 1, tzinfo=UTC))
    assert 167.9 < almost_week < 168.0


class TestWatchdogStateAcrossContainers:
    """The daemon runs in the theo-worker container, /research/health is
    served by the api container. Without publishing, the endpoint reported
    UNKNOWN while the worker sat at HEALTHY (observed 2026-08-18)."""

    def test_a_process_without_the_daemon_reads_the_published_state(self, monkeypatch):
        from api.services import theo_quota_monitor as qm

        monkeypatch.setattr(qm, "_started", False)
        published = {"tier": "HEALTHY", "probe_count": 290, "limiter": {}}
        monkeypatch.setattr(
            "api.cache.cache_get", lambda key: published if key == qm.WATCHDOG_STATE_KEY else None
        )

        assert qm.get_watchdog_state() == published

    def test_the_daemon_process_trusts_its_own_state(self, monkeypatch):
        from api.services import theo_quota_monitor as qm

        monkeypatch.setattr(qm, "_started", True)
        monkeypatch.setitem(qm._state, "tier", "THROTTLED")
        monkeypatch.setattr("api.cache.cache_get", lambda key: {"tier": "HEALTHY", "limiter": {}})

        assert qm.get_watchdog_state()["tier"] == "THROTTLED"

    def test_nothing_published_stays_honest(self, monkeypatch):
        """A dead daemon must expire into UNKNOWN, never a stale HEALTHY."""
        from api.services import theo_quota_monitor as qm

        monkeypatch.setattr(qm, "_started", False)
        monkeypatch.setitem(qm._state, "tier", qm.TIER_UNKNOWN)
        monkeypatch.setattr("api.cache.cache_get", lambda key: None)

        assert qm.get_watchdog_state()["tier"] == "UNKNOWN"

    def test_each_probe_publishes(self, monkeypatch):
        from api.services import theo_quota_monitor as qm

        written: dict = {}
        monkeypatch.setattr(
            "api.cache.cache_set",
            lambda key, value, ttl=3600: written.update({"key": key, "value": value, "ttl": ttl}),
        )
        monkeypatch.setitem(qm._state, "tier", "HEALTHY")

        qm._publish_state()

        assert written["key"] == qm.WATCHDOG_STATE_KEY
        assert written["value"]["tier"] == "HEALTHY"
        # Must outlive a probe interval, or the endpoint flaps to UNKNOWN.
        assert written["ttl"] > qm.QUOTA_PROBE_INTERVAL_S
