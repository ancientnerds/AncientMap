"""
Background worker for Theodore Furcade — processes research requests asynchronously.

Polls the research_requests table for queued requests (FIFO),
runs the agent pipeline, and saves structured reports to the DB.
"""

import asyncio
import logging

from sqlalchemy import text

from api.services.theo_config import THEO_PARALLEL_SLOTS
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
    # Phase 2 will wire MiniMax M2.7 here. Until then, fail immediately.
    _msg = "Theo backend not configured — Phase 2 will wire MiniMax M2.7"
    logger.warning(f"[THEO] {_msg} (request {request_id})")
    with get_session() as session:
        session.execute(
            text("""
                UPDATE research_requests
                SET status = 'failed', error_message = :msg, completed_at = NOW()
                WHERE id = :id
            """),
            {"id": request_id, "msg": _msg},
        )
        session.commit()


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
