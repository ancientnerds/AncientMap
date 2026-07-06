"""Quota watchdog daemon for the MiniMax Token Plan.

A background task that probes the token plan every QUOTA_PROBE_INTERVAL_S
and classifies the 5h-rolling remaining percentage into three health
tiers. The classification drives two protective behaviours:

1. The MiniMax rate limiter (`pipeline.lyra.minimax_limiter.limiter`) is
   frozen while the tier is EXHAUSTED (the 30min freeze is re-asserted on
   every exhausted probe), so in-flight LLM calls sleep in place instead
   of burning the empty tail of the window. The tier only recovers once
   the 5h window is back at >= QUOTA_RESUME_PCT (hysteresis) — "pause
   until the quota actually resets", per user requirement 2026-07-06.
2. The Theo worker poll loop consults `get_watchdog_state()` and refuses
   to re-claim deferred rows while EXHAUSTED; batch rows additionally
   require a fully HEALTHY tier to start at all.

State transitions are notified once via Discord webhook (best-effort,
no retry — see api/services/notify.py). The same tier does not
re-notify, so an EXHAUSTED->EXHAUSTED probe with no movement is silent.

Architecture mirrors the Theo worker daemon exactly (see
theo_worker.start_worker): an outer `_safe_loop` wrapper catches any
Exception, logs with exc_info, sleeps 10s, restarts the inner loop.
This is critical because a transient httpx timeout must not kill the
daemon — quota monitoring is the last line of defence.

Public API:
    start_watchdog() -> None       Idempotent: starts the background task.
    get_watchdog_state() -> dict   Latest state for the /research/health
                                   endpoint. Never raises.

The classifier `_classify_tier(5h_pct) -> str` is a pure function and
is covered by tests/test_theo_quota_monitor.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timezone

from api.services.notify import send_discord_webhook
from api.services.theo_config import (
    DEFERRED_RETRY_BACKOFF_S,
    QUOTA_DEGRADED_PCT,
    QUOTA_HEALTHY_PCT,
    QUOTA_PROBE_INTERVAL_S,
    QUOTA_RESUME_PCT,
    THEO_WATCHDOG_DISABLED,
)

logger = logging.getLogger(__name__)


# --- Tier classification ----------------------------------------------------

TIER_HEALTHY = "HEALTHY"
TIER_DEGRADED = "DEGRADED"
TIER_EXHAUSTED = "EXHAUSTED"
TIER_UNKNOWN = "UNKNOWN"  # probe failed; no opinion yet


def _classify_tier(
    five_hour_remaining_percent: float | None,
    prev_tier: str | None = None,
) -> str:
    """Pure function: 5h-rolling % (+ previous tier) -> health tier.

    Boundaries are inclusive at the lower edge (so 30% is still HEALTHY
    but 20% is already EXHAUSTED — see theo_config for the rationale).
    Returns TIER_UNKNOWN when the value is None.

    Hysteresis (2026-07-06): coming FROM exhausted, the tier only recovers
    once the window is back at >= QUOTA_RESUME_PCT. Crossing 20.0001%
    would otherwise unfreeze a paused run for a few minutes of burn and
    re-freeze immediately — flapping without forward progress.
    """
    if five_hour_remaining_percent is None:
        return TIER_UNKNOWN
    if prev_tier == TIER_EXHAUSTED and five_hour_remaining_percent < QUOTA_RESUME_PCT:
        return TIER_EXHAUSTED
    if five_hour_remaining_percent > QUOTA_HEALTHY_PCT:
        return TIER_HEALTHY
    if five_hour_remaining_percent > QUOTA_DEGRADED_PCT:
        return TIER_DEGRADED
    return TIER_EXHAUSTED


# --- Module-level state -----------------------------------------------------

# Mutable singleton dict. All access is from one event loop (FastAPI runs
# uvicorn 1 worker, see theo_worker docstring), so no lock is needed.
_state: dict = {
    "tier": TIER_UNKNOWN,
    "since": None,  # ISO timestamp when the current tier was first observed
    "last_transition": None,  # ISO timestamp of the most recent tier change
    "last_probe_at": None,
    "last_probe_ok": None,  # bool | None
    "five_hour_remaining_percent": None,
    "weekly_remaining_percent": None,
    "probe_count": 0,
    "consecutive_failures": 0,
    "last_error": None,
    "limiter_frozen_by_watchdog": False,
    "watchdog_disabled": THEO_WATCHDOG_DISABLED,
}

_started = False
_start_lock = asyncio.Lock() if False else None  # noqa: F841 — placeholder, see start_watchdog


def get_watchdog_state() -> dict:
    """Return the latest watchdog state. Never raises.

    Includes a fresh `limiter` snapshot so the /research/health endpoint
    can return quota+limiter+watchdog in one call. The probe is NOT
    refreshed on each call — it runs on its own schedule in the daemon.
    """
    try:
        from pipeline.lyra.minimax_limiter import limiter

        limiter_snapshot = limiter.stats
    except Exception as exc:  # noqa: BLE001 — diagnostic endpoint
        limiter_snapshot = {"error": str(exc)}
    # Return a shallow copy so callers can't mutate our state.
    return {**_state, "limiter": limiter_snapshot}


# --- Discord notify ---------------------------------------------------------


# Cap to avoid log spam if the Discord URL is set to a typo and 4xx's
# repeatedly — we still log each failure in [notify], but the watchdog
# itself only fires when the tier changes, not per-probe.
def _notify_transition(prev_tier: str, new_tier: str, snapshot: dict) -> None:
    """Send a Discord webhook on a tier change. Best-effort, never raises.

    Same tier (e.g. EXHAUSTED -> EXHAUSTED with different %) is silent —
    we only notify on the transition itself. The weekly and 5h values in
    the embed come from the probe that triggered the transition.
    """
    if prev_tier == new_tier:
        return
    pct = snapshot.get("five_hour_remaining_percent")
    weekly = snapshot.get("weekly_remaining_percent")
    colour = {
        TIER_HEALTHY: 0x2ECC71,  # green
        TIER_DEGRADED: 0xF1C40F,  # amber
        TIER_EXHAUSTED: 0xE74C3C,  # red
    }.get(new_tier, 0x95A5A6)  # grey for UNKNOWN

    embed = {
        "title": f"Theo quota: {prev_tier} -> {new_tier}",
        "color": colour,
        "fields": [
            {
                "name": "5h remaining",
                "value": f"{pct}%" if pct is not None else "n/a",
                "inline": True,
            },
            {
                "name": "Weekly remaining",
                "value": f"{weekly}%" if weekly is not None else "n/a",
                "inline": True,
            },
        ],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    send_discord_webhook({"embeds": [embed]})
    logger.info(
        "[THEO-WATCHDOG] State transition %s -> %s (5h=%s, weekly=%s) — Discord notified.",
        prev_tier,
        new_tier,
        pct,
        weekly,
    )


# --- Limiter control --------------------------------------------------------

# How long to keep the limiter frozen when the tier flips to EXHAUSTED.
# 30min is a safety ceiling, NOT a guarantee: the watchdog re-probes every
# 60s and unfreezes explicitly the moment the tier recovers. The 30min
# ceiling matters only if the watchdog itself is broken.
# Was 6h (2026-06-29: reduced from 6*3600 to 30*60 — the long freeze held
# the limiter through 3+ rollovers of the 5h window, leaving the next task
# stuck for hours after the quota had already recovered. Probe-based
# unfreezing makes the long ceiling unnecessary.)
_FREEZE_DURATION_S = 30 * 60


def _freeze_limiter() -> None:
    """Freeze the global limiter so new calls fail fast with QuotaExhaustedError."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        with limiter._lock:  # noqa: SLF001 — internal but stable; we own the singleton
            limiter._frozen_until = time.monotonic() + _FREEZE_DURATION_S  # noqa: SLF001
        _state["limiter_frozen_by_watchdog"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[THEO-WATCHDOG] Failed to freeze limiter: %s", exc)


def _unfreeze_limiter() -> None:
    """Lift the freeze. Idempotent — no-op if the limiter is not frozen."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        with limiter._lock:  # noqa: SLF001
            if limiter._frozen_until != 0.0:  # noqa: SLF001
                limiter._frozen_until = 0.0  # noqa: SLF001
        _state["limiter_frozen_by_watchdog"] = False
    except Exception as exc:  # noqa: BLE001
        logger.warning("[THEO-WATCHDOG] Failed to unfreeze limiter: %s", exc)


# --- The probe loop ---------------------------------------------------------


async def _loop() -> None:
    """Inner loop: probe the quota, classify, react. Runs forever."""
    logger.info(
        "[THEO-WATCHDOG] Probe loop started (interval=%ds, healthy>%d%%, exhausted<=%d%%).",
        QUOTA_PROBE_INTERVAL_S,
        QUOTA_HEALTHY_PCT,
        QUOTA_DEGRADED_PCT,
    )
    # Lazy import — minimax_shared is heavy and pulls in httpx; the daemon
    # start should not block on it.
    from pipeline.lyra.minimax_shared import probe_minimax_quota

    while True:
        prev_tier = _state["tier"]
        try:
            quota = probe_minimax_quota()  # 60s server-side cache
            _state["probe_count"] += 1
            _state["last_probe_at"] = datetime.now(UTC).isoformat()
            if quota.get("ok"):
                _state["last_probe_ok"] = True
                _state["consecutive_failures"] = 0
                _state["last_error"] = None
                five_h = quota.get("five_hour_remaining_percent")
                weekly = quota.get("weekly_remaining_percent")
                _state["five_hour_remaining_percent"] = five_h
                _state["weekly_remaining_percent"] = weekly
                new_tier = _classify_tier(five_h, prev_tier)
            else:
                _state["last_probe_ok"] = False
                _state["consecutive_failures"] += 1
                _state["last_error"] = quota.get("error", "unknown")
                # Probe failed: keep the previous tier, log it.
                new_tier = prev_tier if prev_tier != TIER_UNKNOWN else TIER_UNKNOWN
                logger.debug(
                    "[THEO-WATCHDOG] Probe failed (consecutive=%d): %s",
                    _state["consecutive_failures"],
                    _state["last_error"],
                )
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            _state["consecutive_failures"] += 1
            _state["last_error"] = str(exc)[:200]
            new_tier = prev_tier if prev_tier != TIER_UNKNOWN else TIER_UNKNOWN
            logger.warning("[THEO-WATCHDOG] Probe raised: %s", exc)

        # Re-assert the freeze on EVERY exhausted probe, not just on the
        # transition. The freeze is a 30min ceiling — during a multi-hour
        # EXHAUSTED stretch it would otherwise self-expire and let calls
        # flow against a known-empty window until the next 2056 refroze it.
        # Extending it each probe keeps in-place waiters asleep until the
        # hysteresis (QUOTA_RESUME_PCT) releases the tier for real.
        if new_tier == TIER_EXHAUSTED:
            _freeze_limiter()

        now_iso = datetime.now(UTC).isoformat()
        if new_tier != prev_tier:
            _state["last_transition"] = now_iso
            if _state["since"] is None:
                _state["since"] = now_iso
            # Log the transition at a level that matches severity.
            if new_tier == TIER_EXHAUSTED:
                # Freeze already asserted above; this is just the loud log.
                logger.error(
                    "[THEO-WATCHDOG] Tier -> EXHAUSTED (5h=%s, weekly=%s). Limiter frozen "
                    "until 5h >= %d%% (resume hysteresis).",
                    _state["five_hour_remaining_percent"],
                    _state["weekly_remaining_percent"],
                    QUOTA_RESUME_PCT,
                )
            elif prev_tier == TIER_EXHAUSTED and new_tier in (TIER_HEALTHY, TIER_DEGRADED):
                logger.warning(
                    "[THEO-WATCHDOG] Tier EXHAUSTED -> %s. Unfreezing limiter.",
                    new_tier,
                )
                _unfreeze_limiter()
            else:
                logger.info("[THEO-WATCHDOG] Tier %s -> %s.", prev_tier, new_tier)
            _state["tier"] = new_tier
            _state["since"] = now_iso
            _notify_transition(prev_tier, new_tier, _state)
        else:
            # Same tier: don't re-notify, but periodically log so a healthy
            # state is visible in the docker logs without flooding them.
            if _state["probe_count"] % 10 == 0:
                logger.info(
                    "[THEO-WATCHDOG] Probe #%d: tier=%s 5h=%s weekly=%s",
                    _state["probe_count"],
                    new_tier,
                    _state["five_hour_remaining_percent"],
                    _state["weekly_remaining_percent"],
                )

        await asyncio.sleep(QUOTA_PROBE_INTERVAL_S)


async def _safe_loop() -> None:
    """Outer wrapper: restarts _loop on any exception.

    Mirrors theo_worker._safe_poll_loop. A flaky httpx call, a transient
    ImportError, or any other exception must not kill the daemon. The
    inner loop is the actual probe; the outer loop is the safety net.
    """
    while True:
        try:
            await _loop()
        except asyncio.CancelledError:
            # Shutdown — propagate, do not restart.
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[THEO-WATCHDOG] Probe loop crashed, restarting in 10s: %s",
                exc,
                exc_info=True,
            )
            await asyncio.sleep(10)


def start_watchdog() -> None:
    """Start the watchdog daemon. Idempotent: safe to call multiple times.

    Called from theo_worker.start_worker() during FastAPI lifespan startup.
    If THEO_WATCHDOG_DISABLED is set, the call is a no-op (logged once).
    """
    global _started
    if THEO_WATCHDOG_DISABLED:
        logger.info("[THEO-WATCHDOG] THEO_WATCHDOG_DISABLED=1 — watchdog will not start.")
        return
    if _started:
        return
    _started = True
    # asyncio.create_task needs a running loop. The Theo worker is started
    # from FastAPI's lifespan (api/main.py), which runs inside an asyncio
    # event loop, so this is safe.
    asyncio.create_task(_safe_loop())
    logger.info("[THEO-WATCHDOG] Background task created.")
