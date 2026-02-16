"""
Lyra Chat API Routes.

Endpoints:
- POST /lyra/chat     — Turnstile + rate limit (20/hr/IP)
- POST /lyra/admin    — Bearer LYRA_ADMIN_KEY (no rate limit)
"""

import json
import logging
import os
import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.services.admin_auth import get_client_ip
from api.services.rate_limiter import RateLimiter
from api.services.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LYRA_ADMIN_KEY = os.getenv("LYRA_ADMIN_KEY", "")
SSE_MAX_DURATION = 300  # Max SSE stream duration in seconds (5 minutes)

_rate_limiter = RateLimiter(max_requests=int(os.getenv("LYRA_RATE_LIMIT", "20")), namespace="lyra")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class _ImagePayload(BaseModel):
    """Single base64 image in a Lyra chat request."""
    data: str = Field(..., max_length=2_000_000, description="data:image/...;base64,...")


class LyraChatRequest(BaseModel):
    """Request body for Lyra chat."""
    message: str = Field(..., min_length=1, max_length=4000)
    images: list[_ImagePayload] | None = Field(default=None, max_length=5, description="Base64 images")
    context_type: str = Field(default="global", description="Where chat was opened: global, site, empire, news")
    context_id: str | None = Field(default=None, max_length=100, description="UUID of site, empire polity ID, or news item ID")
    context_year: int | None = Field(default=None, description="Year for empire context")
    turnstile_token: str = Field(..., description="Cloudflare Turnstile token")
    history: list[dict] | None = Field(default=None, max_length=50, description="Conversation history [{role, content}]")


class LyraAdminRequest(BaseModel):
    """Request body for admin (no Turnstile)."""
    message: str = Field(..., min_length=1, max_length=4000)
    images: list[_ImagePayload] | None = Field(default=None, max_length=5)
    context_type: str = "global"
    context_id: str | None = Field(default=None, max_length=100)
    context_year: int | None = None
    history: list[dict] | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/chat")
async def lyra_chat(request: LyraChatRequest, req: Request):
    """
    Chat with Lyra. Requires Turnstile token. Rate limited to 20/hr/IP.

    Returns SSE stream with token, sites, and done events.
    """
    ip = get_client_ip(req)

    # 1. Turnstile verification
    if not await verify_turnstile(request.turnstile_token, ip):
        raise HTTPException(status_code=403, detail="Turnstile verification failed")

    # 2. Rate limit
    if not _rate_limiter.check(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({_rate_limiter.max_requests} requests/hour). Try again later.",
        )

    return _stream_response(
        message=request.message,
        images=[img.model_dump() for img in request.images] if request.images else None,
        history=request.history,
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
    Admin chat with Lyra. No Turnstile, no rate limit.

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
        history=request.history,
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
    """Create an SSE streaming response from the Lyra agent."""

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
