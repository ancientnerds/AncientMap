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

from api.services.theo_config import RESULT_TTL_HOURS, THEO_PARALLEL_SLOTS, THEO_RESEARCH_COST
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


async def _process_request(
    request_id: str,
    question: str,
    specialist_options: dict | None = None,
) -> None:
    """Process a single research request using the V2 convergence pipeline."""
    logger.info(f"[THEO] Starting request {request_id}")

    # Register live events buffer before pipeline starts so SSE streaming works immediately
    _live_events[request_id] = []

    # Mark request as running
    with get_session() as session:
        session.execute(
            text("UPDATE research_requests SET status = 'running' WHERE id = :id"),
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
            # Release reserved credits on failure/cancel
            _release_reservation(request_id)

            if "cancelled" in ctx.error.lower():
                emit({"type": "done", "status": "cancelled"})
                logger.info(f"[THEO] Request {request_id} cancelled by user")
            else:
                emit({"type": "done", "status": "failed"})
                with get_session() as session:
                    # Persist the in-memory diagnostic state on failure so
                    # we can post-mortem from psql alone — previously the
                    # failure path threw away debug_log + counters, which
                    # is exactly when we most want them.
                    session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = 'failed',
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
                logger.warning(f"[THEO] Request {request_id} failed: {ctx.error}")
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
                                completed_at = NOW(),
                                expires_at = NOW() + (:ttl * INTERVAL '1 hour')
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
                            "ttl": RESULT_TTL_HOURS,
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
# the angles need, even when that means a 4+ hour wall clock. Run 12 timed out
# at 14400s mid-saturation. The 12h ceiling here is a stuck-process
# safety net, not a quality gate.
_REQUEST_TIMEOUT_SECONDS = 43200  # 12 hours

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
    last_change = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_STALL_POLL_SECONDS)
            if task in done:
                return task.result()
            sig = _read_progress_sig(request_id)
            now = time.monotonic()
            if sig is not None and sig != last_sig:
                last_sig, last_change = sig, now
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
    finally:
        if not task.done():
            task.cancel()


async def _poll_loop() -> None:
    """Main polling loop — picks up queued requests and processes them."""
    print("[THEO] Worker poll loop started", flush=True)
    logger.info("[THEO] Worker poll loop started")
    while not _shutdown:
        try:
            # Quota watchdog gate (2026-06-28). When the tier is EXHAUSTED
            # the limiter is already frozen, so any run we pick up will
            # QuotaExhaustedError within the first LLM call and re-defer
            # — burning the 5min re-claim back-off for nothing. Sleep and
            # skip; the watchdog will lift the gate within ~60s once a
            # healthy probe comes in. Health/degraded tiers are fine to
            # proceed on; HEALTHY is the normal case.
            try:
                from api.services.theo_quota_monitor import get_watchdog_state

                if get_watchdog_state().get("tier") == "EXHAUSTED":
                    await asyncio.sleep(60)
                    continue
            except Exception:  # noqa: BLE001 — never let a watchdog read kill the poll loop
                pass
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
                        WHERE status = 'queued'
                           OR (status = 'deferred'
                               AND completed_at < NOW() - INTERVAL '5 minutes')
                        ORDER BY created_at ASC
                        LIMIT 1
                    """)
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


async def cleanup_expired() -> None:
    """Delete expired research requests (runs hourly)."""
    while not _shutdown:
        try:
            with get_session() as session:
                result = session.execute(
                    text("DELETE FROM research_requests WHERE expires_at < NOW()")
                )
                session.commit()
                deleted = result.rowcount
                if deleted:
                    logger.info(f"[THEO] Cleaned up {deleted} expired research requests")
        except Exception as e:
            logger.warning(f"[THEO] Cleanup error: {e}")
        await asyncio.sleep(3600)  # Every hour


async def cleanup_stale_deferred() -> None:
    """Fail out research requests stuck in 'deferred' too long.

    Runs hourly. A 'deferred' request is one that hit a quota exhaustion
    (2026-06-28 plan) and is waiting for the 5h-rolling window to reset.
    If quota does not recover within DEFERRED_MAX_AGE_HOURS, the request
    is marked 'failed' with a clear reason so the queue does not grow
    forever. The user's reserved credits are released.

    Companion to cleanup_expired — different status (deferred vs
    expires_at past) but the same idea: keep the queue bounded.
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
    asyncio.create_task(cleanup_expired())
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
