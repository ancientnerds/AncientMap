"""
Lyra Chat API Routes.

Endpoints:
- POST /lyra/chat     — Discord OAuth login required, credits deducted
- POST /lyra/admin    — Bearer LYRA_ADMIN_KEY (no rate limit, no credits)
"""

import json
import logging
import os
import secrets
import time
import uuid
from math import ceil

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.services.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LYRA_ADMIN_KEY = os.getenv("LYRA_ADMIN_KEY", "")
SSE_MAX_DURATION = 300  # Max SSE stream duration in seconds (5 minutes)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class _ImagePayload(BaseModel):
    """Single base64 image in a Lyra chat request."""
    data: str = Field(..., max_length=2_000_000, description="data:image/...;base64,...")


class _HistoryMessage(BaseModel):
    """Single message in conversation history."""
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class LyraChatRequest(BaseModel):
    """Request body for Lyra chat (login required, no Turnstile)."""
    message: str = Field(..., min_length=1, max_length=4000)
    images: list[_ImagePayload] | None = Field(default=None, max_length=5, description="Base64 images")
    context_type: str = Field(default="global", description="Where chat was opened: global, site, empire, news")
    context_id: str | None = Field(default=None, max_length=100, description="UUID of site, empire polity ID, or news item ID")
    context_year: int | None = Field(default=None, description="Year for empire context")
    history: list[_HistoryMessage] | None = Field(default=None, max_length=50, description="Conversation history [{role, content}]")


class LyraAdminRequest(BaseModel):
    """Request body for admin (no Turnstile)."""
    message: str = Field(..., min_length=1, max_length=4000)
    images: list[_ImagePayload] | None = Field(default=None, max_length=5)
    context_type: str = "global"
    context_id: str | None = Field(default=None, max_length=100)
    context_year: int | None = None
    history: list[_HistoryMessage] | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/chat")
async def lyra_chat(request: LyraChatRequest, req: Request):
    """
    Chat with Lyra. Requires Discord login + credits.

    Returns SSE stream with token, sites, done events.
    The done event includes credits_remaining.
    """
    user = get_current_user(req)

    # Check credits
    if user.credits <= 0:
        raise HTTPException(status_code=402, detail="No credits remaining")

    return _stream_response_with_credits(
        user_id=user.id,
        message=request.message,
        images=[img.model_dump() for img in request.images] if request.images else None,
        history=[h.model_dump() for h in request.history] if request.history else None,
        context_type=request.context_type,
        context_id=request.context_id,
        context_year=request.context_year,
    )


@router.post("/admin/verify")
async def lyra_admin_verify(authorization: str | None = Header(None)):
    """
    Lightweight key check — no LLM call, just verifies the Bearer token.
    Used by the frontend auth gate before opening the chat.
    """
    if not LYRA_ADMIN_KEY:
        raise HTTPException(status_code=503, detail="LYRA_ADMIN_KEY not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth")

    if not secrets.compare_digest(authorization[7:], LYRA_ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid key")

    return {"verified": True}


@router.post("/admin")
async def lyra_admin(
    request: LyraAdminRequest,
    authorization: str | None = Header(None),
):
    """
    Admin chat with Lyra. No login, no credits, no rate limit.

    Requires Authorization: Bearer <LYRA_ADMIN_KEY>.
    """
    if not LYRA_ADMIN_KEY:
        raise HTTPException(status_code=503, detail="LYRA_ADMIN_KEY not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer <key> required")

    token = authorization[7:]
    if not secrets.compare_digest(token, LYRA_ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    return _stream_response(
        message=request.message,
        images=[img.model_dump() for img in request.images] if request.images else None,
        history=[h.model_dump() for h in request.history] if request.history else None,
        context_type=request.context_type,
        context_id=request.context_id,
        context_year=request.context_year,
    )


def _stream_response(
    message: str,
    images: list[dict] | None,
    history: list[dict] | None,
    context_type: str,
    context_id: str | None,
    context_year: int | None,
) -> StreamingResponse:
    """Create an SSE streaming response from the Lyra agent (no credits tracking)."""

    async def generate():
        deadline = time.monotonic() + SSE_MAX_DURATION
        try:
            from api.services.lyra_agent import run_agent_stream

            async for chunk in run_agent_stream(
                message=message,
                images=images,
                history=history,
                context_type=context_type,
                context_id=context_id,
                context_year=context_year,
            ):
                if time.monotonic() > deadline:
                    yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'Response time limit reached'})}\n\n"
                    return
                event_type = chunk.get("type", "token")
                yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"

        except Exception as e:
            logger.error(f"Lyra stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'An internal error occurred'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_response_with_credits(
    user_id: uuid.UUID,
    message: str,
    images: list[dict] | None,
    history: list[dict] | None,
    context_type: str,
    context_id: str | None,
    context_year: int | None,
) -> StreamingResponse:
    """Create an SSE streaming response with credit deduction on completion."""

    async def generate():
        deadline = time.monotonic() + SSE_MAX_DURATION
        try:
            from api.services.lyra_agent import run_agent_stream

            async for chunk in run_agent_stream(
                message=message,
                images=images,
                history=history,
                context_type=context_type,
                context_id=context_id,
                context_year=context_year,
            ):
                if time.monotonic() > deadline:
                    yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'Response time limit reached'})}\n\n"
                    return

                event_type = chunk.get("type", "token")

                # Intercept "done" event to deduct credits and add credits_remaining
                if event_type == "done":
                    tokens = chunk.get("metadata", {}).get("tokens", {})
                    input_tokens = tokens.get("input", 0)
                    output_tokens = tokens.get("output", 0)
                    voyage_tokens = tokens.get("voyage", 0)
                    credits_used = max(1, ceil((input_tokens + output_tokens) / 100))

                    # Deduct credits and log usage
                    credits_remaining = _deduct_credits(
                        user_id=user_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        voyage_tokens=voyage_tokens,
                        credits_used=credits_used,
                    )

                    # Add credits info to the done event metadata
                    if "metadata" not in chunk:
                        chunk["metadata"] = {}
                    chunk["metadata"]["credits_used"] = credits_used
                    chunk["metadata"]["credits_remaining"] = credits_remaining

                yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"

        except Exception as e:
            logger.error(f"Lyra stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': 'An internal error occurred'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _deduct_credits(
    user_id: uuid.UUID,
    input_tokens: int,
    output_tokens: int,
    voyage_tokens: int,
    credits_used: int,
) -> int:
    """Deduct credits from user and log usage. Returns remaining credits."""
    from pipeline.database import DiscordUser, TokenUsageLog, get_session

    with get_session() as session:
        user = session.query(DiscordUser).filter(DiscordUser.id == user_id).with_for_update().first()
        if not user:
            return 0

        user.credits = max(0, user.credits - credits_used)
        session.add(TokenUsageLog(
            user_id=user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            voyage_tokens=voyage_tokens,
            credits_used=credits_used,
        ))
        remaining = user.credits

    return remaining
