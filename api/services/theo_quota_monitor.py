"""Quota watchdog daemon for the MiniMax Token Plan.

A background task that probes the token plan every QUOTA_PROBE_INTERVAL_S
and classifies the remaining 5h-budget percentage into health tiers.
(The "5h window" is a FIXED block — e.g. 10:00-15:00 UTC, resetting to
100% at the boundary — not a rolling window; measured live 2026-07-19.)
The classification drives two protective behaviours:

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
from datetime import UTC, datetime

from api.services.notify import send_discord_webhook
from api.services.theo_config import (
    QUOTA_FREEZE_PCT,
    QUOTA_HEALTHY_PCT,
    QUOTA_PROBE_INTERVAL_S,
    QUOTA_RESUME_PCT,
    QUOTA_THROTTLE_PCT,
    QUOTA_WEEKLY_FREEZE_PCT,
    THEO_WATCHDOG_DISABLED,
)

logger = logging.getLogger(__name__)


# --- Tier classification ----------------------------------------------------

TIER_HEALTHY = "HEALTHY"
TIER_DEGRADED = "DEGRADED"
TIER_THROTTLED = "THROTTLED"
TIER_EXHAUSTED = "EXHAUSTED"
TIER_UNKNOWN = "UNKNOWN"  # probe failed; no opinion yet

# Fail-closed threshold (audit 2026-08-05): a single failed probe keeps the
# previous tier — transient network blips must not flap the limiter — but a
# stale tier held forever fails OPEN (a dead probe endpoint would leave a
# last-known HEALTHY in place and batch claims would keep starting blind).
# After this many CONSECUTIVE probe failures (5 x QUOTA_PROBE_INTERVAL_S
# without a successful measurement) the tier is demoted to TIER_UNKNOWN,
# which blocks batch claims in theo_worker._batch_claim_allowed.
_PROBE_FAILURE_DEMOTE_THRESHOLD = 5

# --- Training-corpus growth guard -------------------------------------------
# The corpus (docs/TRAINING_DATA_POLICY.md) is append-only by design, so the
# only thing between it and a full disk is a loud counter. Checked from the
# probe loop rather than a second daemon: it is one cheap query every ~6h.
_CORPUS_WARN_BYTES = 5 * 1024**3
_CORPUS_ALARM_BYTES = 20 * 1024**3
_CORPUS_CHECK_EVERY_PROBES = 360  # 6h at QUOTA_PROBE_INTERVAL_S=60
_corpus_alert_level = ""  # "" | "warn" | "alarm"; re-notify only on change


def _check_corpus_size() -> None:
    """Log training-corpus growth, notify on threshold crossings.

    Blocking DB call — invoke via asyncio.to_thread.
    """
    global _corpus_alert_level
    try:
        from pipeline.lyra.training_corpus import corpus_size_report

        report = corpus_size_report()
    except Exception as exc:  # noqa: BLE001 — a size probe never breaks the watchdog
        logger.warning("[THEO-WATCHDOG] Corpus size probe failed: %s", exc)
        return

    total = report["total_bytes"]
    gib = total / 1024**3
    logger.info(
        "[THEO-WATCHDOG] Training corpus: %.2f GiB (%d documents, %d artifacts)",
        gib,
        report["documents"],
        report["artifacts"],
    )

    if total >= _CORPUS_ALARM_BYTES:
        level = "alarm"
    elif total >= _CORPUS_WARN_BYTES:
        level = "warn"
    else:
        level = ""

    if level and level != _corpus_alert_level:
        send_discord_webhook(
            {
                "embeds": [
                    {
                        "title": "📚 Training corpus growth",
                        "description": (
                            f"The corpus is at **{gib:.1f} GiB** "
                            f"({report['documents']} documents, "
                            f"{report['artifacts']} artifacts).\n"
                            + (
                                "Past the 20 GiB alarm threshold — check disk headroom "
                                "and the archive dump retention."
                                if level == "alarm"
                                else "Past the 5 GiB notice threshold."
                            )
                        ),
                        "color": 0xE67E22 if level == "alarm" else 0x95A5A6,
                    }
                ]
            }
        )
    _corpus_alert_level = level


def _tier_after_probe_failure(prev_tier: str, consecutive_failures: int) -> str:
    """Tier to hold after a failed probe: previous tier below the demotion
    threshold, TIER_UNKNOWN at or above it (see comment on the constant)."""
    if consecutive_failures >= _PROBE_FAILURE_DEMOTE_THRESHOLD:
        if prev_tier != TIER_UNKNOWN:
            logger.warning(
                "[THEO-WATCHDOG] %d consecutive probe failures — demoting tier %s -> %s.",
                consecutive_failures,
                prev_tier,
                TIER_UNKNOWN,
            )
        return TIER_UNKNOWN
    return prev_tier


def _classify_tier(
    five_hour_remaining_percent: float | None,
    prev_tier: str | None = None,
    *,
    weekly_remaining_percent: float | None = None,
) -> str:
    """Pure function: 5h-rolling % + weekly % (+ previous tier) -> health tier.

    Boundaries are inclusive at the lower edge (30% is still HEALTHY,
    20% is already THROTTLED, 5% is already EXHAUSTED — see theo_config
    for the rationale). Returns TIER_UNKNOWN when the value is None.

    Weekly wall (2026-07-19): at or below QUOTA_WEEKLY_FREEZE_PCT the tier
    is EXHAUSTED no matter what the 5h window says — an empty weekly budget
    rejects every call (error 2056) while leaving the 5h window untouched,
    which is exactly the state the 5h ladder misreads as HEALTHY. Checked
    before the hysteresis so a weekly wall cannot be lifted by a full 5h
    window. No weekly hysteresis: the % only refills at the Monday reset.

    Hysteresis (2026-07-06): coming FROM exhausted, the tier only recovers
    once the window is back at >= QUOTA_RESUME_PCT — no freeze/thaw
    flapping at the boundary. THROTTLED has no hysteresis: oscillating
    around 20% just alternates crawl/warn, which is the intended
    equilibrium.
    """
    if five_hour_remaining_percent is None:
        return TIER_UNKNOWN
    if weekly_remaining_percent is not None and weekly_remaining_percent <= QUOTA_WEEKLY_FREEZE_PCT:
        return TIER_EXHAUSTED
    if prev_tier == TIER_EXHAUSTED and five_hour_remaining_percent < QUOTA_RESUME_PCT:
        return TIER_EXHAUSTED
    if five_hour_remaining_percent > QUOTA_HEALTHY_PCT:
        return TIER_HEALTHY
    if five_hour_remaining_percent > QUOTA_THROTTLE_PCT:
        return TIER_DEGRADED
    if five_hour_remaining_percent > QUOTA_FREEZE_PCT:
        return TIER_THROTTLED
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


# The daemon runs in the theo-worker container while /research/health is
# served by the api container. Each probe publishes its result here so the
# endpoint reports the tier that actually gates the worker instead of its
# own never-probed UNKNOWN (observed 2026-08-18: endpoint said UNKNOWN
# while the worker sat at HEALTHY, probe #290). The TTL outlives three
# probe intervals, so a dead daemon expires into an honest UNKNOWN rather
# than a stale HEALTHY.
WATCHDOG_STATE_KEY = "theo:watchdog_state"
WATCHDOG_STATE_TTL = QUOTA_PROBE_INTERVAL_S * 3


def _local_snapshot() -> dict:
    """This process's state plus a fresh limiter snapshot."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        limiter_snapshot = limiter.stats
    except Exception as exc:  # noqa: BLE001 — diagnostic endpoint
        limiter_snapshot = {"error": str(exc)}
    # Return a shallow copy so callers can't mutate our state.
    return {**_state, "limiter": limiter_snapshot}


def _publish_state() -> None:
    """Share this probe's result with the other containers."""
    from api.cache import cache_set

    try:
        cache_set(WATCHDOG_STATE_KEY, _local_snapshot(), ttl=WATCHDOG_STATE_TTL)
    except Exception as exc:  # noqa: BLE001 — publishing must not kill the daemon
        logger.warning("[THEO-WATCHDOG] state publish failed: %s", exc)


def get_watchdog_state() -> dict:
    """Return the latest watchdog state. Never raises.

    Includes a fresh `limiter` snapshot so the /research/health endpoint
    can return quota+limiter+watchdog in one call. The probe is NOT
    refreshed on each call — it runs on its own schedule in the daemon.

    A process that does not run the daemon has no state of its own, so it
    reads what the daemon published. When nothing was published (daemon
    down or never started) the local UNKNOWN is the truthful answer.
    """
    if not _started:
        from api.cache import cache_get

        published = cache_get(WATCHDOG_STATE_KEY)
        if published:
            return published
    return _local_snapshot()


# --- Discord notify ---------------------------------------------------------


# Cap to avoid log spam if the Discord URL is set to a typo and 4xx's
# repeatedly — we still log each failure in [notify], but the watchdog
# itself only fires when the tier changes, not per-probe.
def _notify_transition(prev_tier: str, new_tier: str, snapshot: dict) -> None:
    """Send a Discord webhook on a tier change. Best-effort, never raises.

    Same tier (e.g. EXHAUSTED -> EXHAUSTED with different %) is silent —
    we only notify on the transition itself. The weekly and 5h values in
    the embed come from the probe that triggered the transition.

    Sync by design (the webhook in notify.py is a blocking httpx call) —
    the async probe loop invokes this via `asyncio.to_thread` so a slow
    Discord endpoint cannot stall the loop.
    """
    if prev_tier == new_tier:
        return
    # Only transitions entering or leaving EXHAUSTED carry operator-
    # actionable signal. A routine block cycle walks HEALTHY -> DEGRADED
    # -> THROTTLED -> EXHAUSTED -> HEALTHY — webhooking every step meant
    # ~5 pings per normal research run (2026-07-19). The skipped steps
    # are still visible in the logs via the transition log lines.
    if TIER_EXHAUSTED not in (prev_tier, new_tier):
        return
    pct = snapshot.get("five_hour_remaining_percent")
    weekly = snapshot.get("weekly_remaining_percent")
    colour = {
        TIER_HEALTHY: 0x2ECC71,  # green
        TIER_DEGRADED: 0xF1C40F,  # amber
        TIER_THROTTLED: 0xE67E22,  # orange — crawl mode
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


def _throttle_limiter() -> None:
    """Clamp the global limiter to crawl mode (THROTTLED band). Re-asserted
    on every throttled probe; recovery is adaptive once probes stop."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        limiter.throttle()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[THEO-WATCHDOG] Failed to throttle limiter: %s", exc)


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


def _restore_limiter_full_speed() -> None:
    """Clear any leftover crawl clamp after a real quota recovery.

    Invariant (2026-07-19): tier HEALTHY == limiter at full speed. HEALTHY
    means >30% of the block remains — pacing against it is pure waste, and
    the adaptive ramp alone needs 1h+ to undo a THROTTLE clamp (observed
    live: 20+ min at delay 42s / concurrency 2 against a 100% window)."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        limiter.restore_full_speed()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[THEO-WATCHDOG] Failed to restore limiter speed: %s", exc)


# --- The probe loop ---------------------------------------------------------


async def _loop() -> None:
    """Inner loop: probe the quota, classify, react. Runs forever."""
    logger.info(
        "[THEO-WATCHDOG] Probe loop started (interval=%ds, healthy>%d%%, "
        "throttled<=%d%%, frozen<=%d%%, resume>=%d%%).",
        QUOTA_PROBE_INTERVAL_S,
        QUOTA_HEALTHY_PCT,
        QUOTA_THROTTLE_PCT,
        QUOTA_FREEZE_PCT,
        QUOTA_RESUME_PCT,
    )
    # Lazy import — minimax_shared is heavy and pulls in httpx; the daemon
    # start should not block on it.
    from pipeline.lyra.minimax_shared import probe_minimax_quota

    while True:
        prev_tier = _state["tier"]
        try:
            # Sync httpx call — run in a thread so the probe never blocks
            # the event loop. 60s server-side cache.
            quota = await asyncio.to_thread(probe_minimax_quota)
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
                new_tier = _classify_tier(five_h, prev_tier, weekly_remaining_percent=weekly)
                # Saturation controller (2026-07-26): tune the crawl-lane
                # delay to the live headroom so batch research saturates a
                # flat plan when the window is full and backs off as it
                # drains. Percentage-based — survives plan upgrades.
                try:
                    from pipeline.lyra.minimax_limiter import (
                        crawl_delay_for_window,
                        set_crawl_delay_s,
                    )

                    set_crawl_delay_s(crawl_delay_for_window(five_h))
                except Exception as exc:  # noqa: BLE001 — tuning is best-effort
                    logger.warning("[THEO-WATCHDOG] Crawl-delay tuning failed: %s", exc)
            else:
                _state["last_probe_ok"] = False
                _state["consecutive_failures"] += 1
                _state["last_error"] = quota.get("error", "unknown")
                # Probe failed: keep the previous tier for transient blips,
                # demote to UNKNOWN at the fail-closed threshold.
                new_tier = _tier_after_probe_failure(prev_tier, _state["consecutive_failures"])
                logger.debug(
                    "[THEO-WATCHDOG] Probe failed (consecutive=%d): %s",
                    _state["consecutive_failures"],
                    _state["last_error"],
                )
        except Exception as exc:  # noqa: BLE001 — probe is best-effort
            _state["consecutive_failures"] += 1
            _state["last_error"] = str(exc)[:200]
            new_tier = _tier_after_probe_failure(prev_tier, _state["consecutive_failures"])
            logger.warning("[THEO-WATCHDOG] Probe raised: %s", exc)

        # Re-assert the limiter clamp on EVERY probe, not just on tier
        # transitions. The freeze is a 30min ceiling — during a multi-hour
        # EXHAUSTED stretch it would otherwise self-expire and let calls
        # flow against a known-empty window until the next 2056 refroze it.
        # Same for THROTTLED: the limiter's adaptive growth would crawl
        # back up between probes without the re-assert.
        if new_tier == TIER_EXHAUSTED:
            _freeze_limiter()
        elif new_tier == TIER_THROTTLED:
            _throttle_limiter()

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
            elif new_tier == TIER_THROTTLED:
                logger.warning(
                    "[THEO-WATCHDOG] Tier -> THROTTLED (5h=%s). Limiter crawling: "
                    "the running task keeps finishing work on the remaining tail.",
                    _state["five_hour_remaining_percent"],
                )
            elif new_tier == TIER_HEALTHY:
                # Invariant: HEALTHY == full-speed limiter. Unfreeze (no-op
                # unless coming from EXHAUSTED) and clear any crawl clamp
                # left over from THROTTLED/EXHAUSTED — the block has reset,
                # pacing against a fresh window is pure waste (2026-07-19).
                logger.warning(
                    "[THEO-WATCHDOG] Tier %s -> HEALTHY. Limiter unfrozen and "
                    "restored to full speed.",
                    prev_tier,
                )
                _unfreeze_limiter()
                _restore_limiter_full_speed()
            elif prev_tier == TIER_EXHAUSTED and new_tier == TIER_DEGRADED:
                # Unfreeze only — at 20-30% remaining the leftover crawl
                # pacing is protective, so it is left to recover adaptively.
                logger.warning("[THEO-WATCHDOG] Tier EXHAUSTED -> DEGRADED. Unfreezing limiter.")
                _unfreeze_limiter()
            else:
                logger.info("[THEO-WATCHDOG] Tier %s -> %s.", prev_tier, new_tier)
            _state["tier"] = new_tier
            _state["since"] = now_iso
            await asyncio.to_thread(_notify_transition, prev_tier, new_tier, _state)
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

        _publish_state()
        if _state["probe_count"] and _state["probe_count"] % _CORPUS_CHECK_EVERY_PROBES == 0:
            await asyncio.to_thread(_check_corpus_size)
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
