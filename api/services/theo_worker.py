"""
Background worker for Theodore Furcade — processes research requests asynchronously.

Polls the research_requests table for queued requests (FIFO),
runs the agent pipeline, and saves structured reports to the DB.
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from api.services.theo_config import (
    EFFORT_CONFIG,
    RESULT_TTL_HOURS,
    THEO_MAX_TOKENS,
    THEO_PARALLEL_SLOTS,
)
from api.services.theo_prompts import THEO_SYSTEM_PROMPT
from pipeline.database import get_session

logger = logging.getLogger(__name__)

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


async def _process_request(request_id: str, question: str, effort: str) -> None:
    """Process a single research request using the Lyra agent pipeline."""
    effort_cfg = EFFORT_CONFIG.get(effort, EFFORT_CONFIG["auto"])

    # Phase 2 will set backend_type="minimax" and model_name to MiniMax M2.7
    raise NotImplementedError(
        "Theo backend not configured — Phase 2 will wire MiniMax M2.7"
    )

    # Track live events for SSE
    # Evict oldest completed entries if at capacity
    if len(_live_events) >= _MAX_LIVE_ENTRIES:
        for rid, events in list(_live_events.items()):
            if any(e.get("type") in ("done", "error") for e in events):
                _live_events.pop(rid, None)
                break
        else:
            # All entries are still active — evict oldest anyway
            oldest = next(iter(_live_events))
            _live_events.pop(oldest, None)
    _live_events[request_id] = []

    start_ms = time.monotonic()
    collected_text: list[str] = []
    pipeline_trace: list[dict] = []
    sites_found = 0
    tools_used = 0
    total_tokens = 0

    try:
        # Mark as running
        with get_session() as session:
            session.execute(
                text("UPDATE research_requests SET status = 'running' WHERE id = :id"),
                {"id": request_id},
            )
            session.commit()

        _append_event(request_id, {"type": "status", "content": "Research started"})

        async for event in run_agent_stream(
            message=question,
            context_type="global",
            ctx=ctx,
            system_prompt=THEO_SYSTEM_PROMPT,
            num_ctx=THEO_NUM_CTX,
            max_tokens=THEO_MAX_TOKENS,
            base_url=THEO_OLLAMA_BASE_URL or None,
        ):
            event_type = event.get("type", "")

            if event_type == "token":
                collected_text.append(event.get("content", ""))
            elif event_type == "thinking":
                pass  # Internal reasoning, not included in report
            elif event_type == "pipeline":
                pipeline_trace.append(event)
                if event.get("stage") == "tool_call" and event.get("status") == "done":
                    tools_used += 1
            elif event_type == "sites":
                site_list = event.get("sites", [])
                sites_found += len(site_list)
            elif event_type == "done":
                meta = event.get("metadata", {})
                total_tokens = meta.get("input_tokens", 0) + meta.get("output_tokens", 0)

            # Forward to SSE listeners
            _append_event(request_id, event)

            # Respect max rounds for non-auto efforts
            max_rounds = effort_cfg["max_rounds"]
            if max_rounds and tools_used >= max_rounds:
                break

        duration_ms = int((time.monotonic() - start_ms) * 1000)
        result_text = "".join(collected_text)

        # Build structured result JSON
        result = {
            "report": result_text,
            "sites_found": sites_found,
            "tools_used": tools_used,
            "total_tokens": total_tokens,
            "effort": effort,
            "duration_ms": duration_ms,
        }

        now = datetime.now(UTC)
        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_requests
                    SET status = 'completed',
                        result_json = :result,
                        pipeline_trace = cast(:trace as jsonb),
                        sites_found = :sites,
                        tools_used = :tools,
                        total_tokens = :tokens,
                        duration_ms = :duration,
                        completed_at = :completed,
                        expires_at = :expires
                    WHERE id = :id
                """),
                {
                    "id": request_id,
                    "result": json.dumps(result, ensure_ascii=False),
                    "trace": json.dumps(pipeline_trace, ensure_ascii=False),
                    "sites": sites_found,
                    "tools": tools_used,
                    "tokens": total_tokens,
                    "duration": duration_ms,
                    "completed": now,
                    "expires": now + timedelta(hours=RESULT_TTL_HOURS),
                },
            )
            session.commit()

        _append_event(request_id, {"type": "done", "status": "completed"})
        logger.info(
            f"[THEO] Research {request_id} completed in {duration_ms}ms "
            f"({sites_found} sites, {tools_used} tools)"
        )

    except Exception as e:
        duration_ms = int((time.monotonic() - start_ms) * 1000)
        logger.error(f"[THEO] Research {request_id} failed: {e}", exc_info=True)
        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_requests
                    SET status = 'failed',
                        error_message = :err,
                        duration_ms = :duration,
                        completed_at = NOW()
                    WHERE id = :id
                """),
                {"id": request_id, "err": str(e)[:2000], "duration": duration_ms},
            )
            session.commit()
        _append_event(request_id, {"type": "error", "error": "Research request failed"})

    finally:
        # Clean up live events after a delay (let SSE clients finish reading)
        await asyncio.sleep(600)
        _live_events.pop(request_id, None)


async def _poll_loop() -> None:
    """Main polling loop — picks up queued requests and processes them."""
    logger.info("[THEO] Worker started (polling for research requests)")
    while not _shutdown:
        try:
            # Find the oldest queued request
            with get_session() as session:
                row = session.execute(
                    text("""
                        SELECT id::text, question, effort
                        FROM research_requests
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        LIMIT 1
                    """)
                ).fetchone()

            if row:
                async with _semaphore:
                    await _process_request(row.id, row.question, row.effort)
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

    asyncio.create_task(_poll_loop())
    asyncio.create_task(cleanup_expired())
    logger.info("[THEO] Background worker tasks created")
