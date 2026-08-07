"""Tests for the quota watchdog classifier and state plumbing.

The watchdog (api.services.theo_quota_monitor) classifies the
MiniMax 5h-rolling remaining % into one of four tiers and exposes
the latest state via get_watchdog_state(). These tests cover the
pure-function classifier and the state-dict / probe-failure path;
they do NOT start the daemon (which would require a real probe or
a heavy mock of probe_minimax_quota).
"""

from __future__ import annotations

import pytest

from api.services import theo_quota_monitor as wm
from api.services.theo_quota_monitor import (
    TIER_DEGRADED,
    TIER_EXHAUSTED,
    TIER_HEALTHY,
    TIER_THROTTLED,
    TIER_UNKNOWN,
    _classify_tier,
)

# --- _classify_tier: pure-function boundaries -------------------------------


@pytest.mark.parametrize(
    "five_hour_pct,expected",
    [
        (100.0, TIER_HEALTHY),
        (80.0, TIER_HEALTHY),
        (50.0, TIER_HEALTHY),  # above QUOTA_HEALTHY_PCT=30
        (30.0001, TIER_HEALTHY),  # just over the threshold
        (30.0, TIER_DEGRADED),  # boundary: at 30, no longer healthy
        (25.0, TIER_DEGRADED),
        (20.0001, TIER_DEGRADED),  # just over the THROTTLED threshold
        # 2026-07-06 v2: at 80% used the run is THROTTLED (crawl: it can
        # still finish its synthesis on the remaining 20%), and only the
        # last 5% — the reserve that keeps Lyra alive — is a hard freeze.
        (20.0, TIER_THROTTLED),  # boundary: at 20, crawl mode
        (10.0, TIER_THROTTLED),
        (5.0001, TIER_THROTTLED),
        (5.0, TIER_EXHAUSTED),  # boundary: at 5, frozen
        (3.0, TIER_EXHAUSTED),
        (0.0, TIER_EXHAUSTED),
        (-1.0, TIER_EXHAUSTED),  # negative (defensive) still exhausted
        (None, TIER_UNKNOWN),  # probe failed to extract the value
    ],
)
def test_classify_tier(five_hour_pct, expected):
    assert _classify_tier(five_hour_pct) == expected


# --- Weekly wall (2026-07-19): the weekly budget dominates the 5h ladder ----
# Born from the 07-08..07-12 standstill: the calendar-week budget was at 0%
# (every call 429'd with error 2056) while the 5h window sat untouched at
# 100% — precisely BECAUSE nothing could burn it. The classifier read only
# the 5h value, reported HEALTHY, and the batch gate fed 17 tasks into the
# wall. Weekly must therefore be able to force EXHAUSTED on its own.


@pytest.mark.parametrize(
    "five_hour_pct,weekly_pct,prev_tier,expected",
    [
        (100.0, 0.0, None, TIER_EXHAUSTED),  # the blind-spot scenario itself
        (100.0, 5.0, None, TIER_EXHAUSTED),  # boundary: at 5, frozen
        (100.0, 5.0001, None, TIER_HEALTHY),  # above the reserve: 5h ladder rules
        (100.0, None, None, TIER_HEALTHY),  # no weekly data -> 5h-only behavior
        (10.0, 100.0, None, TIER_THROTTLED),  # healthy weekly leaves 5h ladder alone
        (100.0, 0.0, TIER_HEALTHY, TIER_EXHAUSTED),  # regardless of prev tier
        # Monday reset: weekly refilled, 5h full -> recovery passes hysteresis.
        (100.0, 100.0, TIER_EXHAUSTED, TIER_HEALTHY),
        # Weekly refilled but 5h below QUOTA_RESUME_PCT: hysteresis still holds.
        (30.0, 100.0, TIER_EXHAUSTED, TIER_EXHAUSTED),
    ],
)
def test_classify_tier_weekly_wall(five_hour_pct, weekly_pct, prev_tier, expected):
    assert _classify_tier(five_hour_pct, prev_tier, weekly_remaining_percent=weekly_pct) == expected


# --- Hysteresis: once EXHAUSTED, stay paused until real recovery ------------


@pytest.mark.parametrize(
    "five_hour_pct,prev_tier,expected",
    [
        # From EXHAUSTED, crossing the THROTTLED/DEGRADED/HEALTHY boundaries
        # is NOT enough — the window must recover to QUOTA_RESUME_PCT (50).
        (10.0, TIER_EXHAUSTED, TIER_EXHAUSTED),  # NOT throttled: stay frozen
        (25.0, TIER_EXHAUSTED, TIER_EXHAUSTED),
        (35.0, TIER_EXHAUSTED, TIER_EXHAUSTED),
        (49.9, TIER_EXHAUSTED, TIER_EXHAUSTED),
        (50.0, TIER_EXHAUSTED, TIER_HEALTHY),  # at resume threshold: released
        (80.0, TIER_EXHAUSTED, TIER_HEALTHY),
        # Hysteresis only applies coming FROM exhausted — THROTTLED moves
        # freely across its boundaries (crawl <-> warn equilibrium).
        (35.0, TIER_HEALTHY, TIER_HEALTHY),
        (35.0, TIER_DEGRADED, TIER_HEALTHY),
        (25.0, TIER_THROTTLED, TIER_DEGRADED),
        (25.0, TIER_HEALTHY, TIER_DEGRADED),
        (10.0, TIER_DEGRADED, TIER_THROTTLED),
        # Unknown probe value stays UNKNOWN regardless of history.
        (None, TIER_EXHAUSTED, TIER_UNKNOWN),
    ],
)
def test_classify_tier_hysteresis(five_hour_pct, prev_tier, expected):
    assert _classify_tier(five_hour_pct, prev_tier) == expected


# --- THROTTLED tier: limiter crawl mode --------------------------------------


def test_throttle_limiter_forces_crawl():
    """While THROTTLED, the watchdog clamps the limiter to crawl mode:
    concurrency floor + throttle delay. No freeze — calls keep flowing,
    just slowly, so a run at 80% usage can still finish its synthesis."""
    from pipeline.lyra.minimax_limiter import _THROTTLE_DELAY_S, MiniMaxLimiter

    lim = MiniMaxLimiter()
    assert lim.stats["current_concurrency"] == 8

    lim.throttle()
    assert lim.stats["current_concurrency"] == 1
    assert lim.stats["current_delay"] == _THROTTLE_DELAY_S
    assert not lim.is_frozen(), "throttle must NOT freeze — crawl, not pause"


# --- get_watchdog_state: must not raise even with no daemon running ---------


def test_get_watchdog_state_does_not_raise_without_daemon():
    """get_watchdog_state is the hot path for /research/health. It must
    never raise — the daemon may not have started yet (e.g. during
    the first 60s of process startup) and the endpoint must still
    return a valid response."""
    state = wm.get_watchdog_state()
    assert isinstance(state, dict)
    # The state always carries these keys even before the first probe.
    for key in (
        "tier",
        "since",
        "last_transition",
        "last_probe_at",
        "last_probe_ok",
        "five_hour_remaining_percent",
        "weekly_remaining_percent",
        "probe_count",
        "consecutive_failures",
        "last_error",
        "limiter_frozen_by_watchdog",
        "watchdog_disabled",
        "limiter",
    ):
        assert key in state, f"missing key: {key}"
    # Before any probe, tier is UNKNOWN.
    assert state["tier"] == TIER_UNKNOWN
    assert state["probe_count"] == 0


# --- State transitions: classifier output drives the state-machine update --


def test_state_transition_health_to_exhausted_updates_state(monkeypatch):
    """Simulate one HEALTHY probe then one EXHAUSTED probe: state should
    reflect the new tier and the last_transition timestamp should be set."""
    from api.services import theo_quota_monitor as wm

    # Reset the state dict to a known starting point.
    wm._state["tier"] = TIER_UNKNOWN
    wm._state["since"] = None
    wm._state["last_transition"] = None
    wm._state["probe_count"] = 0
    wm._state["five_hour_remaining_percent"] = None

    # Run the classifier directly — the loop is async, but the state
    # transitions are pure.
    first = _classify_tier(80.0)
    wm._state["tier"] = first
    wm._state["since"] = "2026-06-28T00:00:00+00:00"
    wm._state["last_transition"] = "2026-06-28T00:00:00+00:00"

    second = _classify_tier(3.0)
    assert second == TIER_EXHAUSTED
    assert second != wm._state["tier"]  # the change triggers notify + freeze

    # Mirror what the loop would do (the real loop also writes the probe
    # fields into _state before classifying — we do the same here).
    wm._state["tier"] = second
    wm._state["last_transition"] = "2026-06-28T00:01:00+00:00"
    wm._state["five_hour_remaining_percent"] = 3.0

    snap = wm.get_watchdog_state()
    assert snap["tier"] == TIER_EXHAUSTED
    assert snap["five_hour_remaining_percent"] == 3.0
    # Snapshot must not share state with the module dict (defensive copy).
    snap["tier"] = "HACKED"
    assert wm._state["tier"] == TIER_EXHAUSTED


# --- notify_transition: no Discord URL = silent no-op ---------------------


def test_notify_transition_is_silent_when_webhook_unset(monkeypatch):
    """send_discord_webhook is a no-op when DISCORD_WEBHOOK_URL is unset.
    notify_transition must therefore never raise even in that case."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    wm._notify_transition(TIER_HEALTHY, TIER_EXHAUSTED, {"five_hour_remaining_percent": 2.0})


# --- Recovery restores full speed (2026-07-19) -------------------------------


@pytest.mark.real_limiter_pacing
def test_restore_limiter_full_speed_clears_crawl_clamp():
    """After the quota block resets (tier -> HEALTHY), the limiter must NOT
    keep the THROTTLED-era clamp. Observed live 2026-07-19: 20+ min after
    recovery to a 100% window the limiter still crawled at delay 42s /
    concurrency 2 — the adaptive ramp (20 successes per step) needs 1h+ to
    undo a clamp that no longer has a reason to exist."""
    from pipeline.lyra.minimax_limiter import limiter

    limiter.throttle()
    assert limiter.stats["current_concurrency"] == 1

    before_requests = limiter.stats["total_requests"]
    wm._restore_limiter_full_speed()

    stats = limiter.stats
    assert stats["current_concurrency"] == 8
    assert stats["current_delay"] == 0.5
    # The liveness counter must never be touched — the stall guard reads it.
    assert stats["total_requests"] == before_requests


# --- Discord gating: only EXHAUSTED transitions notify (2026-07-19) ----------


def test_notify_transition_gated_to_exhausted_transitions(monkeypatch):
    """A routine quota-block cycle produces HEALTHY->DEGRADED->THROTTLED->
    EXHAUSTED->HEALTHY — five webhooks per run is noise. Only transitions
    entering or leaving EXHAUSTED carry operator-actionable signal."""
    sent = []
    monkeypatch.setattr(wm, "send_discord_webhook", lambda payload: sent.append(payload))
    snapshot = {"five_hour_remaining_percent": 50.0, "weekly_remaining_percent": 50.0}

    wm._notify_transition(TIER_HEALTHY, TIER_DEGRADED, snapshot)
    wm._notify_transition(TIER_DEGRADED, TIER_THROTTLED, snapshot)
    assert sent == []

    wm._notify_transition(TIER_THROTTLED, TIER_EXHAUSTED, snapshot)
    wm._notify_transition(TIER_EXHAUSTED, TIER_HEALTHY, snapshot)
    assert len(sent) == 2


# --- Limiter freeze / unfreeze: end-to-end with the real limiter ---------


def test_freeze_and_unfreeze_limiter_roundtrip():
    """When the watchdog decides the tier is EXHAUSTED, it freezes the
    limiter; when the tier recovers, it unfreezes. The end-to-end round
    trip should be observable on limiter.is_frozen()."""
    from pipeline.lyra.minimax_limiter import limiter

    # Make sure the limiter starts unfrozen for this test.
    limiter.unfreeze()
    assert not limiter.is_frozen()

    wm._freeze_limiter()
    assert wm._state["limiter_frozen_by_watchdog"] is True
    assert limiter.is_frozen()

    wm._unfreeze_limiter()
    assert wm._state["limiter_frozen_by_watchdog"] is False
    assert not limiter.is_frozen()


# --- 2026-06-29 fixes ------------------------------------------------------


def test_freeze_duration_is_30_minutes():
    """The watchdog must not freeze the limiter for 6 hours — that left
    tasks stuck through multiple rollovers of the 5h window. 30min is
    a safety ceiling; the probe unfreezes earlier when quota recovers."""
    assert wm._FREEZE_DURATION_S == 30 * 60


def test_2062_is_throttle_2056_is_quota():
    """2026-07-29 revision of the 06-29 assumption: 2062 ('Token Plan rate
    limit reached') is the plan's SHORT-WINDOW rate cap, not the budget — it
    fired at 5h=71% / weekly=27% remaining and killed a 15h run. It now
    classifies as a plan-rate throttle (window-clearing backoff at call
    sites); only 2056/credit markers remain budget exhaustion."""
    from pipeline.lyra.minimax_limiter import is_plan_rate_throttle, is_quota_error

    assert is_quota_error("Error 429: Token Plan rate limit reached (2062)") is False
    assert is_plan_rate_throttle("Error 429: Token Plan rate limit reached (2062)") is True
    assert is_quota_error("Error 429: Token Plan usage limit reached (2056)") is True
    assert is_plan_rate_throttle("Error 429: Token Plan usage limit reached (2056)") is False
    # Plain transient rate limit is neither quota nor plan throttle.
    assert is_quota_error("Error 429: rate_limit_error (transient)") is False
    assert is_plan_rate_throttle("Error 429: rate_limit_error (transient)") is False


def test_inter_task_backoff_constant_exists():
    """The poll loop must sleep THEO_INTER_TASK_BACKOFF_S between tasks
    so the watchdog probe has time to flag DEGRADED/EXHAUSTED before the
    next task starts burning tokens."""
    from api.services.theo_config import THEO_INTER_TASK_BACKOFF_S

    assert THEO_INTER_TASK_BACKOFF_S == 30


def test_retry_limit_reduced_to_two():
    """config._call_anthropic_api's _max_attempts was 5 → 2 (2026-06-29)
    to stop the retry storm that burned ~740k tokens in 24h on bad-JSON
    retries."""
    import inspect

    from pipeline.lyra.config import _call_anthropic_api

    src = inspect.getsource(_call_anthropic_api)
    assert "_max_attempts = 2" in src
    # And the OLD value must NOT be present (catches accidental fallback).
    assert "_max_attempts = 5" not in src


def test_external_cancellation_raises_on_non_running_status(monkeypatch):
    """Ghost-task guard: when the DB row's status is no longer 'running'
    (e.g. user cancelled via API), _check_external_cancellation raises
    _CancelledByUser so the orchestrator can stop cleanly.

    Mocks the DB session so no real DB is needed."""
    from pipeline.lyra import convergence_orchestrator as co
    from pipeline.lyra.convergence_orchestrator import _CancelledByUser

    class FakeRow:
        def __getitem__(self, i):
            return "cancelled"

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args, **_kwargs):
            class FakeResult:
                def fetchone(self_inner):
                    return FakeRow()

            return FakeResult()

    # get_session is imported inside the function, so patch it at the
    # source module: pipeline.database.
    monkeypatch.setattr("pipeline.database.get_session", lambda: FakeSession())
    with pytest.raises(_CancelledByUser, match="status changed to 'cancelled'"):
        co._check_external_cancellation("test-rid")


def test_external_cancellation_passes_silently_when_running(monkeypatch):
    """The happy path: when status is 'running', no exception fires."""

    class FakeRow:
        def __getitem__(self, i):
            return "running"

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args, **_kwargs):
            class FakeResult:
                def fetchone(self_inner):
                    return FakeRow()

            return FakeResult()

    from pipeline.lyra import convergence_orchestrator as co

    monkeypatch.setattr("pipeline.database.get_session", lambda: FakeSession())
    co._check_external_cancellation("test-rid")  # must not raise


def test_external_cancellation_swallows_db_errors(monkeypatch):
    """A transient DB error must NOT kill the pipeline. The check is
    best-effort: only a confirmed non-'running' status triggers the cancel."""

    class BrokenSession:
        def __enter__(self):
            raise RuntimeError("connection refused")

        def __exit__(self, *args):
            return False

    from pipeline.lyra import convergence_orchestrator as co

    monkeypatch.setattr("pipeline.database.get_session", lambda: BrokenSession())
    co._check_external_cancellation("test-rid")  # must not raise
