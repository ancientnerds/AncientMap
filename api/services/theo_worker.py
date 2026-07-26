"""
Background worker for Theodore Furcade — processes research requests asynchronously.

Polls the research_requests table for queued requests (FIFO),
runs the agent pipeline, and saves structured reports to the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import text

from api.services.theo_config import (
    THEO_MIN_TASK_INTERVAL_S,
    THEO_PARALLEL_SLOTS,
    THEO_RESEARCH_COST,
)
from pipeline.database import get_session

logger = logging.getLogger(__name__)


def _release_reservation(request_id: str) -> None:
    """Release reserved credits when a research request fails or is cancelled."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT user_id FROM research_requests WHERE id = :id"),
                {"id": request_id},
            ).fetchone()
            if not row:
                return
            session.execute(
                text("""
                    UPDATE discord_users SET reserved_credits = GREATEST(reserved_credits - :cost, 0)
                    WHERE discord_id = :uid AND is_unlimited = FALSE
                """),
                {"uid": row.user_id, "cost": THEO_RESEARCH_COST},
            )
            session.commit()
    except Exception as exc:
        logger.warning(f"[THEO] Reservation release failed for {request_id}: {exc}")


def _deduct_credits(request_id: str) -> None:
    """Deduct credits and release reservation on successful completion."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT user_id FROM research_requests WHERE id = :id"),
                {"id": request_id},
            ).fetchone()
            if not row:
                return
            session.execute(
                text("""
                    UPDATE discord_users
                    SET credits = credits - :cost,
                        reserved_credits = GREATEST(reserved_credits - :cost, 0)
                    WHERE discord_id = :uid AND is_unlimited = FALSE
                """),
                {"uid": row.user_id, "cost": THEO_RESEARCH_COST},
            )
            session.commit()
    except Exception as exc:
        logger.warning(f"[THEO] Credit deduction failed for {request_id}: {exc}")


# Single-slot semaphore — only 1 research request at a time
_semaphore = asyncio.Semaphore(THEO_PARALLEL_SLOTS)

# Per-request live events for SSE streaming (request_id -> list[dict])
_live_events: dict[str, list[dict]] = {}
_MAX_EVENTS_PER_REQUEST = 500
_MAX_LIVE_ENTRIES = 100

_shutdown = False


def _append_event(request_id: str, event: dict) -> None:
    """Append an event to the live events list with bounds checking."""
    events = _live_events.get(request_id)
    if events is None:
        return
    if len(events) < _MAX_EVENTS_PER_REQUEST:
        events.append(event)


def get_live_events(request_id: str) -> list[dict]:
    """Return accumulated live events for a request (for SSE streaming)."""
    return _live_events.get(request_id, [])


def _terminal_status_for_error(ctx) -> str:
    """Route a run that ended with ctx.error to its terminal status.

    'cancelled' wins (user intent), then 'deferred' for quota deaths
    (ctx.quota_exhausted is set by EventBus.emit — the exception itself
    never propagates), then 'failed' for everything real.
    """
    if "cancelled" in ctx.error.lower():
        return "cancelled"
    if getattr(ctx, "quota_exhausted", False):
        return "deferred"
    return "failed"


async def _process_request(
    request_id: str,
    question: str,
    specialist_options: dict | None = None,
) -> None:
    """Process a single research request using the V2 convergence pipeline."""
    logger.info(f"[THEO] Starting request {request_id}")

    # Register live events buffer before pipeline starts so SSE streaming works immediately
    _live_events[request_id] = []

    # Mark request as running. started_at is the batch-pacing clock: the next
    # batch task may only start THEO_MIN_TASK_INTERVAL_S after this moment.
    with get_session() as session:
        session.execute(
            text(
                "UPDATE research_requests SET status = 'running', started_at = NOW() WHERE id = :id"
            ),
            {"id": request_id},
        )
        session.commit()

    pipeline_trace: list[dict] = []
    start = time.monotonic()

    def emit(event: dict) -> None:
        _append_event(request_id, event)
        pipeline_trace.append(event)

    try:
        force_include = (specialist_options or {}).get("force_include", [])
        force_exclude = (specialist_options or {}).get("force_exclude", [])
        video_ids = (specialist_options or {}).get("video_ids", [])
        web_urls = (specialist_options or {}).get("web_urls", [])
        disabled_adapters = (specialist_options or {}).get("disabled_adapters", [])

        from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

        orchestrator = ConvergenceOrchestrator()
        ctx: Any = await orchestrator.run(
            question,
            emit,
            request_id=request_id,
            force_include=force_include,
            force_exclude=force_exclude,
            video_ids=video_ids,
            web_urls=web_urls,
            disabled_adapters=disabled_adapters,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        if ctx.error:
            # Release reserved credits on failure/cancel/defer
            _release_reservation(request_id)

            status = _terminal_status_for_error(ctx)
            if status == "cancelled":
                emit({"type": "done", "status": "cancelled"})
                logger.info(f"[THEO] Request {request_id} cancelled by user")
            else:
                # 'deferred' = quota death swallowed into ctx.error by the
                # event bus (ctx.quota_exhausted) — retry when the window
                # recovers. 'failed' = a real failure.
                emit({"type": "done", "status": status})
                with get_session() as session:
                    # Persist the in-memory diagnostic state on failure so
                    # we can post-mortem from psql alone — previously the
                    # failure path threw away debug_log + counters, which
                    # is exactly when we most want them.
                    session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = :status,
                                error_message = :msg,
                                debug_log = :debug_log,
                                total_tokens = :tokens,
                                llm_calls = :llm_calls,
                                sites_found = :sites,
                                duration_ms = :duration,
                                completed_at = NOW()
                            WHERE id = :id
                        """),
                        {
                            "status": status,
                            "id": request_id,
                            "msg": ctx.error,
                            "debug_log": json.dumps(ctx.debug_log),
                            "tokens": ctx.total_tokens,
                            "llm_calls": ctx.llm_call_count,
                            "sites": len(ctx.registry.sources) if hasattr(ctx, "registry") else 0,
                            "duration": duration_ms,
                        },
                    )
                    session.commit()
                log = logger.warning if status == "deferred" else logger.error
                log(f"[THEO] Request {request_id} {status}: {ctx.error}")
        else:
            # Deduct credits and release reservation on success
            _deduct_credits(request_id)

            result = {
                "report": ctx.paper_text,
                "title": ctx.paper_title,
                "card_description": ctx.card_description,
                "audit": ctx.audit_result,
                "quality_score": ctx.quality_score,
                # Persist probative image metadata so reflow/rewrite backfills
                # can rebuild captions against the source list without
                # re-fetching from connectors.
                "probative_images": getattr(ctx, "probative_images", []) or [],
                # Hero banner picked from the probative_images list — used as
                # the page-top banner and og:image. None when no probative
                # images were embedded.
                "hero_image": getattr(ctx, "hero_image", None),
            }
            emit({"type": "done", "status": "completed"})
            try:
                with get_session() as session:
                    session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = 'completed',
                                result_json = :result,
                                pipeline_trace = :trace,
                                debug_log = :debug_log,
                                total_tokens = :tokens,
                                llm_calls = :llm_calls,
                                duration_ms = :duration,
                                sites_found = :sites,
                                tools_used = :tools,
                                completed_at = NOW()
                            WHERE id = :id
                        """),
                        {
                            "id": request_id,
                            "result": json.dumps(result),
                            "trace": json.dumps(pipeline_trace),
                            "debug_log": json.dumps(ctx.debug_log),
                            "tokens": ctx.total_tokens,
                            "llm_calls": ctx.llm_call_count,
                            "duration": duration_ms,
                            "sites": len(ctx.registry.sources),
                            "tools": len(ctx.specialist_analyses),
                        },
                    )
                    session.commit()
            except Exception as db_exc:
                logger.error(f"[THEO] DB commit failed for {request_id}: {db_exc}")
            logger.info(
                f"[THEO] Request {request_id} completed in {duration_ms}ms"
                f" ({ctx.total_tokens} tokens)"
            )

    except Exception as exc:
        from pipeline.lyra.minimax_limiter import (
            InsufficientQuotaError,
            QuotaExhaustedError,
        )

        # 2026-06-28: quota errors are *deferred* not failed — the 5h window
        # will reset. The worker re-queues deferred rows after 1h.
        is_quota_error = isinstance(exc, (InsufficientQuotaError, QuotaExhaustedError))
        duration_ms = int((time.monotonic() - start) * 1000)
        if is_quota_error:
            logger.warning(f"[THEO] Quota hit on request {request_id} — deferring: {exc}")
        else:
            logger.error(
                f"[THEO] Unexpected error for request {request_id}: {exc}",
                exc_info=True,
            )
        _release_reservation(request_id)
        emit({"type": "done", "status": "deferred" if is_quota_error else "failed"})
        with get_session() as session:
            # Even on an unexpected crash, try to persist whatever
            # diagnostic state the orchestrator already built up. `ctx`
            # may not exist if the exception fired before orchestrator.run
            # returned, so guard everything with getattr.
            ctx_local = locals().get("ctx", None)
            target_status = "deferred" if is_quota_error else "failed"
            session.execute(
                text("""
                    UPDATE research_requests
                    SET status = :status,
                        error_message = :msg,
                        debug_log = :debug_log,
                        total_tokens = :tokens,
                        llm_calls = :llm_calls,
                        sites_found = :sites,
                        duration_ms = :duration,
                        completed_at = NOW()
                    WHERE id = :id
                """),
                {
                    "status": target_status,
                    "id": request_id,
                    "msg": str(exc),
                    "debug_log": json.dumps(
                        getattr(ctx_local, "debug_log", []) if ctx_local else []
                    ),
                    "tokens": getattr(ctx_local, "total_tokens", 0) if ctx_local else 0,
                    "llm_calls": getattr(ctx_local, "llm_call_count", 0) if ctx_local else 0,
                    "sites": len(ctx_local.registry.sources)
                    if ctx_local and hasattr(ctx_local, "registry")
                    else 0,
                    "duration": duration_ms,
                },
            )
            session.commit()

    finally:
        # Delay cleanup so SSE streams have time to read the terminal event
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(10, _live_events.pop, request_id, None)
        except RuntimeError:
            _live_events.pop(request_id, None)


# Hard ceiling on a single research run. The user's explicit guidance is that
# research QUALITY (sources, citations, image grounding) is paramount — the
# pipeline must be free to do as many saturation rounds + cross-pollinations as
# the angles need. Since 2026-07-26 runs crawl at low priority (~12-18h normal,
# quota troughs stack on top) against a 72h orchestrator deadline
# (ResearchConfig.deadline_hours) that force-finishes gracefully. This worker
# ceiling sits just above it as the stuck-process safety net — it must only
# fire when the orchestrator's own deadline handling is itself wedged.
_REQUEST_TIMEOUT_SECONDS = 73 * 3600  # 73 hours (orchestrator deadline + 1h)

# --- Stall detection -------------------------------------------------------
# A healthy run flushes climbing counters to the DB every ~30s
# (convergence_orchestrator._flush_progress_to_db). A stalled run — e.g. M3
# structured-output never letting an angle saturate — freezes those counters
# while still heartbeating, so it would otherwise sit until the 12h hard
# timeout above and hold the single worker slot the whole time. We cancel a run
# whose counters show ZERO movement for _STALL_GRACE_SECONDS. Because the signal
# is "no progress" (not wall-clock), a slow-but-healthy long run that keeps
# advancing is never killed early.
_STALL_GRACE_SECONDS = 2700  # 45 min of zero progress => stalled
_STALL_POLL_SECONDS = 180  # re-check the DB counters every 3 min


class _StallDetected(Exception):
    """Raised when a running request stops making any progress."""


def _limiter_frozen() -> bool:
    """True while the MiniMax limiter is quota-frozen. Used by the stall
    guard: frozen counters during a quota pause are expected, not a stall."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        return limiter.is_frozen()
    except Exception:  # noqa: BLE001 — a read failure must not kill the guard
        return False


def _read_limiter_activity() -> int | None:
    """The limiter's lifetime request count — a liveness signal for the
    stall guard (2026-07-19). The DB progress counters only flush on event
    emissions, and event gaps stretch past the stall grace when the
    limiter crawls after a quota trough (observed live: 16min gap at
    delay 42s / concurrency 2; ee3493e8 on 07-13 was killed at 45min with
    349 calls / 1M tokens on the clock — almost certainly a healthy
    crawling run, not a hang). A climbing count means LLM calls are
    flowing, so the run is NOT stalled regardless of the DB sig. Caveat:
    the limiter is shared by every MiniMax caller in this process, so a
    true Theo stall is only detected once those go quiet — the 12h hard
    timeout backstops that corner."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        return limiter.stats["total_requests"]
    except Exception:  # noqa: BLE001 — a read failure must not kill the guard
        return None


def _mark_failed_running(request_id: str, msg: str) -> None:
    """Mark a still-'running' request failed and release its credit reservation."""
    _release_reservation(request_id)
    try:
        with get_session() as session:
            session.execute(
                text(
                    "UPDATE research_requests SET status = 'failed', "
                    "error_message = :msg, completed_at = NOW() "
                    "WHERE id = :id AND status = 'running'"
                ),
                {"id": request_id, "msg": msg},
            )
            session.commit()
    except Exception as exc:
        logger.warning("[THEO] Failed to mark request %s as failed: %s", request_id, exc)


def _read_progress_sig(request_id: str) -> tuple | None:
    """(llm_calls, total_tokens, sites_found, tools_used) from the DB, or None."""
    try:
        with get_session() as session:
            row = session.execute(
                text(
                    "SELECT llm_calls, total_tokens, sites_found, tools_used "
                    "FROM research_requests WHERE id = :id"
                ),
                {"id": request_id},
            ).fetchone()
        return (row.llm_calls, row.total_tokens, row.sites_found, row.tools_used) if row else None
    except Exception as exc:
        logger.warning("[THEO] progress read failed for %s: %s", request_id, exc)
        return None


async def _run_with_stall_guard(
    request_id: str, question: str, specialist_options: dict | None
) -> None:
    """Run a request, cancelling it if its progress counters freeze.

    Raises ``_StallDetected`` when no counter has moved for
    ``_STALL_GRACE_SECONDS``; a still-advancing run is left alone no matter how
    long it takes.
    """
    task = asyncio.create_task(_process_request(request_id, question, specialist_options))
    last_sig = _read_progress_sig(request_id)
    last_activity = _read_limiter_activity()
    last_change = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_STALL_POLL_SECONDS)
            if task in done:
                return task.result()
            sig = _read_progress_sig(request_id)
            activity = _read_limiter_activity()
            now = time.monotonic()
            if sig is not None and sig != last_sig:
                last_sig, last_change = sig, now
            elif _limiter_frozen():
                # Quota pause: the run's LLM calls are sleeping inside the
                # frozen limiter, so counters CANNOT move. Known cause, not
                # a stall — reset the clock so the pause doesn't accumulate
                # toward the grace window.
                last_change = now
            elif activity is not None and activity != last_activity:
                # LLM calls are flowing even though no event has flushed
                # the DB counters yet — a slow phase (e.g. post-trough
                # crawl), not a stall (2026-07-19).
                last_change = now
            elif (now - last_change) >= _STALL_GRACE_SECONDS:
                logger.error(
                    "[THEO] Request %s no progress for %ss (sig=%s) — cancelling stalled run.",
                    request_id,
                    _STALL_GRACE_SECONDS,
                    last_sig,
                )
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001 — swallow CancelledError + cleanup errors
                    pass
                raise _StallDetected
            if activity is not None:
                last_activity = activity
    finally:
        if not task.done():
            task.cancel()


# --- Batch pacing gate (2026-07-04) ----------------------------------------
# Batch tasks (is_batch=TRUE) start at most once per THEO_MIN_TASK_INTERVAL_S,
# start-to-start. The clock is MAX(started_at) over ALL tasks — a manual UI
# run burns the same shared quota, so it pushes the next batch slot back. UI
# rows themselves bypass the gate entirely (they are is_batch=FALSE in the
# claim query). DB-based, so the pacing survives worker restarts and deploys.


def _batch_gate_open(last_start_age_s: float | None, min_interval_s: float) -> bool:
    """True when a batch task may start: nothing ever started, or the most
    recent start is at least min_interval_s ago."""
    return last_start_age_s is None or last_start_age_s >= min_interval_s


def _batch_claim_allowed(gate_open: bool, tier: str, weekly_pct: float | None) -> bool:
    """Batch rows need an open pacing gate, a positively HEALTHY watchdog,
    AND enough weekly budget for a whole paper (2026-07-19). Starting a
    fresh multi-hour full-depth run into a half-drained window (DEGRADED)
    just parks it in the freeze minutes later — wait for the window
    instead. UNKNOWN (no probe yet / watchdog down) is treated as
    not-healthy, and a missing weekly value blocks the same way: batch
    runs never start blind. The weekly floor exists because a paper costs
    ~19% of the calendar-week budget — below THEO_BATCH_MIN_WEEKLY_PCT the
    run would hit the weekly wall (error 2056) mid-flight."""
    from api.services.theo_config import THEO_BATCH_MIN_WEEKLY_PCT

    if not gate_open or tier != "HEALTHY":
        return False
    return weekly_pct is not None and weekly_pct >= THEO_BATCH_MIN_WEEKLY_PCT


def _read_last_start_age_s() -> float | None:
    """Seconds since the most recent task start (any kind), or None if no
    task has ever started."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT EXTRACT(EPOCH FROM (NOW() - MAX(started_at))) FROM research_requests")
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as exc:
        logger.warning("[THEO] last-start read failed: %s", exc)
        return None


async def _poll_loop() -> None:
    """Main polling loop — picks up queued requests and processes them."""
    print("[THEO] Worker poll loop started", flush=True)
    logger.info("[THEO] Worker poll loop started")
    gate_was_open: bool | None = None
    while not _shutdown:
        try:
            # Quota watchdog gate (2026-06-28). When the tier is EXHAUSTED
            # the limiter is already frozen, so any run we pick up would
            # sleep inside the limiter from its very first LLM call. Sleep
            # and skip; the watchdog lifts the gate once the window has
            # recovered past QUOTA_RESUME_PCT.
            tier = "UNKNOWN"
            weekly_pct = None
            try:
                from api.services.theo_quota_monitor import get_watchdog_state

                watchdog = get_watchdog_state()
                tier = watchdog.get("tier", "UNKNOWN")
                weekly_pct = watchdog.get("weekly_remaining_percent")
                if tier == "EXHAUSTED":
                    await asyncio.sleep(60)
                    continue
            except Exception:  # noqa: BLE001 — never let a watchdog read kill the poll loop
                pass
            # Batch pacing: while the gate is closed (or the watchdog is not
            # positively HEALTHY, or the weekly budget won't fit a whole
            # paper), batch rows are invisible to the claim query below — a
            # younger UI row still gets picked up immediately.
            gate_open = _batch_gate_open(_read_last_start_age_s(), THEO_MIN_TASK_INTERVAL_S)
            batch_allowed = _batch_claim_allowed(gate_open, tier, weekly_pct)
            if gate_open != gate_was_open:
                logger.info(
                    "[THEO] Batch pacing gate %s (min start-to-start interval %ss, "
                    "tier=%s, weekly=%s%%)",
                    "OPEN" if gate_open else "CLOSED",
                    THEO_MIN_TASK_INTERVAL_S,
                    tier,
                    weekly_pct,
                )
                gate_was_open = gate_open

            # Find the oldest runnable request. 'queued' = freshly submitted;
            # 'deferred' = quota hit earlier, ready for a retry after the 5min
            # back-off window. Without the timestamp check a deferred row would
            # get re-claimed on the very next poll iteration and re-defer
            # immediately, creating a tight loop.
            with get_session() as session:
                row = session.execute(
                    text("""
                        SELECT id::text, question, specialist_options
                        FROM research_requests
                        WHERE (status = 'queued'
                               OR (status = 'deferred'
                                   AND completed_at < NOW() - INTERVAL '5 minutes'))
                          AND (is_batch = FALSE OR :batch_allowed)
                        ORDER BY created_at ASC
                        LIMIT 1
                    """),
                    {"batch_allowed": batch_allowed},
                ).fetchone()

            if row:
                async with _semaphore:
                    try:
                        await asyncio.wait_for(
                            _run_with_stall_guard(row.id, row.question, row.specialist_options),
                            timeout=_REQUEST_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        logger.error(
                            "[THEO] Request %s exceeded %ss hard timeout — marking failed.",
                            row.id,
                            _REQUEST_TIMEOUT_SECONDS,
                        )
                        _mark_failed_running(
                            row.id,
                            f"Request exceeded {_REQUEST_TIMEOUT_SECONDS}s timeout "
                            "and was force-cancelled.",
                        )
                    except _StallDetected:
                        logger.error(
                            "[THEO] Request %s stalled (no progress for %ss) — marking failed.",
                            row.id,
                            _STALL_GRACE_SECONDS,
                        )
                        _mark_failed_running(
                            row.id,
                            f"Request made no progress for {_STALL_GRACE_SECONDS}s "
                            "(stalled) and was cancelled.",
                        )
                # Inter-task backoff (2026-06-29). Without this, the worker
                # picks up the next task immediately after the previous one
                # ends, hammering the API while the 5h quota is still
                # draining. THEO_INTER_TASK_BACKOFF_S=30s gives the
                # watchdog probe enough time to flag DEGRADED/EXHAUSTED
                # before the next task starts. Firing whether the task
                # succeeded or failed.
                from api.services.theo_config import THEO_INTER_TASK_BACKOFF_S

                await asyncio.sleep(THEO_INTER_TASK_BACKOFF_S)
            else:
                await asyncio.sleep(3)  # No work — wait before polling again

        except Exception as e:
            logger.error(f"[THEO] Poll loop error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def cleanup_stale_deferred() -> None:
    """Fail out research requests stuck in 'deferred' too long.

    Runs hourly. A 'deferred' request is one that hit a quota exhaustion
    (2026-06-28 plan) and is waiting for the 5h-rolling window to reset.
    If quota does not recover within DEFERRED_MAX_AGE_HOURS, the request
    is marked 'failed' with a clear reason so the queue does not grow
    forever. The user's reserved credits are released.
    """
    from api.services.theo_config import DEFERRED_MAX_AGE_HOURS

    while not _shutdown:
        try:
            with get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT id::text, user_id
                        FROM research_requests
                        WHERE status = 'deferred'
                          AND completed_at < NOW() - (:hours * INTERVAL '1 hour')
                        """
                    ),
                    {"hours": DEFERRED_MAX_AGE_HOURS},
                ).fetchall()
                stale_ids = [r.id for r in rows]
                if not stale_ids:
                    await asyncio.sleep(3600)
                    continue
                reason = (
                    f"Quota did not recover within {DEFERRED_MAX_AGE_HOURS} hours "
                    f"after the run was deferred. Marked failed to keep the queue bounded."
                )
                session.execute(
                    text(
                        """
                        UPDATE research_requests
                        SET status = 'failed',
                            error_message = :msg,
                            completed_at = NOW()
                        WHERE id = ANY(:ids)
                          AND status = 'deferred'
                        """
                    ),
                    {"msg": reason, "ids": stale_ids},
                )
                session.commit()
            # Release credit reservations outside the session above. The
            # helper uses its own session, so the order doesn't matter.
            for rid in stale_ids:
                _release_reservation(rid)
            logger.warning(
                f"[THEO] Marked {len(stale_ids)} stale-deferred request(s) failed "
                f"(>{DEFERRED_MAX_AGE_HOURS}h without quota recovery)."
            )
        except Exception as e:
            logger.warning(f"[THEO] Stale-deferred cleanup error: {e}")
        await asyncio.sleep(3600)  # Every hour


async def start_worker() -> None:
    """Start the Theo worker background tasks."""
    global _shutdown
    _shutdown = False

    # Recover orphaned requests left in 'running' state from a previous crash
    try:
        with get_session() as session:
            result = session.execute(
                text("UPDATE research_requests SET status = 'queued' WHERE status = 'running'")
            )
            session.commit()
            if result.rowcount:
                logger.info(f"[THEO] Recovered {result.rowcount} orphaned running request(s)")
    except Exception as e:
        logger.warning(f"[THEO] Recovery check failed: {e}")

    async def _safe_poll_loop() -> None:
        """Wrapper that restarts _poll_loop on crash."""
        while not _shutdown:
            try:
                await _poll_loop()
            except Exception as exc:
                logger.error(f"[THEO] Poll loop crashed, restarting in 10s: {exc}", exc_info=True)
                await asyncio.sleep(10)

    asyncio.create_task(_safe_poll_loop())
    asyncio.create_task(cleanup_stale_deferred())
    # Quota watchdog (2026-06-28 plan): a background daemon that probes
    # the MiniMax Token Plan every 60s, classifies the 5h-rolling
    # remaining budget into HEALTHY/DEGRADED/EXHAUSTED, freezes the
    # limiter on EXHAUSTED, and sends a Discord webhook on transitions.
    # The poll loop above also consults get_watchdog_state() and skips
    # pickup while EXHAUSTED, so this is the *active* half of the
    # self-throttling story.
    from api.services.theo_quota_monitor import start_watchdog

    start_watchdog()
    print("[THEO] Background worker tasks created", flush=True)
    logger.info("[THEO] Background worker tasks created")
