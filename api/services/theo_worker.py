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
                    session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = 'failed', error_message = :msg, completed_at = NOW()
                            WHERE id = :id
                        """),
                        {"id": request_id, "msg": ctx.error},
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
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"[THEO] Unexpected error for request {request_id}: {exc}", exc_info=True)
        _release_reservation(request_id)
        emit({"type": "done", "status": "failed"})
        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_requests
                    SET status = 'failed', error_message = :msg, completed_at = NOW()
                    WHERE id = :id
                """),
                {"id": request_id, "msg": str(exc)},
            )
            session.commit()

    finally:
        # Delay cleanup so SSE streams have time to read the terminal event
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(10, _live_events.pop, request_id, None)
        except RuntimeError:
            _live_events.pop(request_id, None)


async def _poll_loop() -> None:
    """Main polling loop — picks up queued requests and processes them."""
    print("[THEO] Worker poll loop started", flush=True)
    logger.info("[THEO] Worker poll loop started")
    while not _shutdown:
        try:
            # Find the oldest queued request
            with get_session() as session:
                row = session.execute(
                    text("""
                        SELECT id::text, question, specialist_options
                        FROM research_requests
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        LIMIT 1
                    """)
                ).fetchone()

            if row:
                async with _semaphore:
                    await _process_request(row.id, row.question, row.specialist_options)
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
    print("[THEO] Background worker tasks created", flush=True)
    logger.info("[THEO] Background worker tasks created")
