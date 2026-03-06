"""
API routes for Theodore Furcade — async archaeological research agent.

Endpoints:
  POST   /theo/research          — Submit a new research request
  GET    /theo/research          — List user's requests (last 24h)
  GET    /theo/research/{id}     — Get single request with full report
  GET    /theo/research/{id}/stream — SSE stream for live progress
  DELETE /theo/research/{id}     — Cancel a queued request
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.services.jwt_auth import get_optional_user
from api.services.theo_config import EFFORT_CONFIG, MAX_REQUESTS_PER_USER
from api.services.theo_worker import get_live_events
from pipeline.database import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ResearchSubmitRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)
    effort: str = Field(default="auto")


class ResearchSubmitResponse(BaseModel):
    id: str
    status: str
    position: int
    estimated_minutes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_uuid(request_id: str) -> None:
    """Validate that request_id is a valid UUID. Raises 404 if not."""
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Research request not found")


def _get_user_id(req: Request) -> str:
    """Get user identifier — Discord ID if logged in, IP otherwise."""
    user = get_optional_user(req)
    if user:
        return user.discord_id
    forwarded = req.headers.get("x-forwarded-for", "")
    return (
        forwarded.split(",")[0].strip() if forwarded else req.client.host if req.client else "anon"
    )


def _estimate_minutes(effort: str, queue_position: int) -> int:
    """Rough estimate based on effort and queue position."""
    base = {"quick": 3, "deep": 10, "full": 20, "auto": 8}.get(effort, 8)
    return base * max(queue_position, 1)


# ---------------------------------------------------------------------------
# POST /theo/research — Submit new research request
# ---------------------------------------------------------------------------


@router.post("/research", response_model=ResearchSubmitResponse)
async def submit_research(body: ResearchSubmitRequest, req: Request):
    """Submit a new research question for Theo to investigate."""
    if body.effort not in EFFORT_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid effort: {body.effort}")

    user_id = _get_user_id(req)

    # Check user's active request count
    with get_session() as session:
        count = session.execute(
            text("""
                SELECT COUNT(*) FROM research_requests
                WHERE user_id = :uid AND status IN ('queued', 'running')
            """),
            {"uid": user_id},
        ).scalar()

        if count >= MAX_REQUESTS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"Max {MAX_REQUESTS_PER_USER} concurrent requests per user",
            )

        # Insert new request
        request_id = str(uuid.uuid4())
        session.execute(
            text("""
                INSERT INTO research_requests (id, user_id, question, effort, status, created_at)
                VALUES (:id, :uid, :q, :effort, 'queued', NOW())
            """),
            {
                "id": request_id,
                "uid": user_id,
                "q": body.question,
                "effort": body.effort,
            },
        )
        session.commit()

        # Get queue position
        position = session.execute(
            text("""
                SELECT COUNT(*) FROM research_requests
                WHERE status IN ('queued', 'running') AND created_at <= (
                    SELECT created_at FROM research_requests WHERE id = :id
                )
            """),
            {"id": request_id},
        ).scalar()

    return ResearchSubmitResponse(
        id=request_id,
        status="queued",
        position=position or 1,
        estimated_minutes=_estimate_minutes(body.effort, position or 1),
    )


# ---------------------------------------------------------------------------
# GET /theo/research — List user's requests
# ---------------------------------------------------------------------------


@router.get("/research")
async def list_research(req: Request):
    """List the current user's research requests (last 24h, not expired)."""
    user_id = _get_user_id(req)

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT id::text, question, effort, status, sites_found, tools_used,
                       duration_ms, error_message, created_at, completed_at
                FROM research_requests
                WHERE user_id = :uid
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 20
            """),
            {"uid": user_id},
        ).fetchall()

    return [
        {
            "id": r.id,
            "question": r.question,
            "effort": r.effort,
            "status": r.status,
            "sites_found": r.sites_found,
            "tools_used": r.tools_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /theo/research/{id} — Get full request with report
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}")
async def get_research(request_id: str, req: Request):
    """Get a single research request including the full report."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    with get_session() as session:
        row = session.execute(
            text("""
                SELECT id::text, user_id, question, effort, status, result_json,
                       pipeline_trace, sites_found, tools_used, total_tokens,
                       duration_ms, error_message, created_at, completed_at, expires_at
                FROM research_requests
                WHERE id = :id
            """),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Research request not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your research request")
    if row.expires_at and row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Research report expired")

    result = json.loads(row.result_json) if row.result_json else None

    return {
        "id": row.id,
        "question": row.question,
        "effort": row.effort,
        "status": row.status,
        "result": result,
        "pipeline_trace": row.pipeline_trace,
        "sites_found": row.sites_found,
        "tools_used": row.tools_used,
        "total_tokens": row.total_tokens,
        "duration_ms": row.duration_ms,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


# ---------------------------------------------------------------------------
# GET /theo/research/{id}/stream — SSE for live progress
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}/stream")
async def stream_research(request_id: str, req: Request):
    """SSE stream for live progress updates while a request is processing."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    # Verify ownership
    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, status FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your request")

    # If already completed, return a single done event
    if row.status in ("completed", "failed", "cancelled"):

        async def _done_gen():
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'status': row.status})}\n\n"

        return StreamingResponse(
            _done_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _stream_gen():
        """Stream live events, polling the event buffer."""
        import asyncio

        cursor = 0
        idle_count = 0
        max_idle = 300  # 5 minutes of no events → close

        while idle_count < max_idle:
            events = get_live_events(request_id)
            if cursor < len(events):
                for evt in events[cursor:]:
                    event_type = evt.get("type", "progress")
                    yield f"event: {event_type}\ndata: {json.dumps(evt)}\n\n"
                cursor = len(events)
                idle_count = 0

                # Check if we've reached a terminal event
                if any(e.get("type") in ("done", "error") for e in events[cursor - 1 :]):
                    return
            else:
                idle_count += 1

            await asyncio.sleep(1)

        yield f"event: timeout\ndata: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(
        _stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# DELETE /theo/research/{id} — Cancel a queued request
# ---------------------------------------------------------------------------


@router.delete("/research/{request_id}")
async def cancel_research(request_id: str, req: Request):
    """Cancel a queued research request. Cannot cancel running requests."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, status FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not your request")
        if row.status != "queued":
            raise HTTPException(
                status_code=409, detail=f"Cannot cancel request in '{row.status}' state"
            )

        session.execute(
            text("UPDATE research_requests SET status = 'cancelled' WHERE id = :id"),
            {"id": request_id},
        )
        session.commit()

    return {"status": "cancelled"}
