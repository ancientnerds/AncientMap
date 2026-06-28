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
        (20.0, TIER_DEGRADED),
        (10.0, TIER_DEGRADED),
        (5.0001, TIER_DEGRADED),  # just over the EXHAUSTED threshold
        (5.0, TIER_EXHAUSTED),  # boundary: at 5, exhausted
        (3.0, TIER_EXHAUSTED),
        (0.0, TIER_EXHAUSTED),
        (-1.0, TIER_EXHAUSTED),  # negative (defensive) still exhausted
        (None, TIER_UNKNOWN),  # probe failed to extract the value
    ],
)
def test_classify_tier(five_hour_pct, expected):
    assert _classify_tier(five_hour_pct) == expected


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
