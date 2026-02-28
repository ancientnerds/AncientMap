"""
Lyra Chat API Routes.

Endpoints:
- POST /lyra/chat     — Discord OAuth login required, credits deducted
"""

import json
import logging
import time
import uuid
from math import ceil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.services.jwt_auth import get_current_user
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import DiscordUser as DBUser
from pipeline.database import get_session as get_db_session

logger = logging.getLogger(__name__)

router = APIRouter()

_chat_limiter = RateLimiter(max_requests=15, window_seconds=60, namespace="lyra_chat")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SSE_MAX_DURATION = 300  # Max SSE stream duration in seconds (5 minutes)

# Anti-exploit: cap conversation history for low-credit users to bound max request cost
LOW_CREDIT_THRESHOLD = 20  # credits below which history is truncated
LOW_CREDIT_MAX_HISTORY = 5  # max history messages for low-credit users (~2-3 exchanges)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class _ImagePayload(BaseModel):
    """Single base64 image in a Lyra chat request."""

    data: str = Field(
        ...,
        max_length=2_000_000,
        pattern=r"^data:image/(png|jpeg|gif|webp);base64,",
        description="data:image/...;base64,...",
    )


class _HistoryMessage(BaseModel):
    """Single message in conversation history."""

    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class LyraChatRequest(BaseModel):
    """Request body for Lyra chat (login required, no Turnstile)."""

    message: str = Field(..., min_length=1, max_length=4000)
    images: list[_ImagePayload] | None = Field(
        default=None, max_length=5, description="Base64 images"
    )
    context_type: str = Field(
        default="global", description="Where chat was opened: global, site, empire, news"
    )
    context_id: str | None = Field(
        default=None, max_length=100, description="UUID of site, empire polity ID, or news item ID"
    )
    context_year: int | None = Field(default=None, description="Year for empire context")
    history: list[_HistoryMessage] | None = Field(
        default=None, max_length=50, description="Conversation history [{role, content}]"
    )


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
    if not _chat_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")

    user = get_current_user(req)

    # Check unlimited flag and credits atomically
    with get_db_session() as session:
        db_user = (
            session.query(DBUser)
            .filter(
                DBUser.id == user.id,
            )
            .with_for_update()
            .first()
        )
        if not db_user:
            raise HTTPException(status_code=402, detail="No credits remaining")

        # Unlimited users bypass credit deduction
        if db_user.is_unlimited:
            return _stream_response(
                message=request.message,
                images=[img.model_dump() for img in request.images] if request.images else None,
                history=[h.model_dump() for h in request.history] if request.history else None,
                context_type=request.context_type,
                context_id=request.context_id,
                context_year=request.context_year,
            )

        if db_user.credits <= 0:
            raise HTTPException(status_code=402, detail="No credits remaining")

        db_user.credits -= 1  # 1-credit deposit
        deposit_remaining = db_user.credits

    # Anti-exploit: limit history length for low-credit users to bound max cost
    history = [h.model_dump() for h in request.history] if request.history else None
    if (
        deposit_remaining < LOW_CREDIT_THRESHOLD
        and history
        and len(history) > LOW_CREDIT_MAX_HISTORY
    ):
        history = history[-LOW_CREDIT_MAX_HISTORY:]

    return _stream_response_with_credits(
        user_id=user.id,
        deposit_remaining=deposit_remaining,
        message=request.message,
        images=[img.model_dump() for img in request.images] if request.images else None,
        history=history,
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
    deposit_remaining: int,
    message: str,
    images: list[dict] | None,
    history: list[dict] | None,
    context_type: str,
    context_id: str | None,
    context_year: int | None,
) -> StreamingResponse:
    """Create an SSE streaming response with atomic credit reconciliation on completion.

    The caller has already pre-deducted 1 credit as a deposit. On the `done` event,
    we calculate the real cost and reconcile: deduct the remainder or refund overpayment.
    """

    async def generate():
        deadline = time.monotonic() + SSE_MAX_DURATION
        done_fired = False
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

                # Intercept "done" event to reconcile credits and log usage
                if event_type == "done":
                    done_fired = True
                    tokens = chunk.get("metadata", {}).get("tokens", {})
                    input_tokens = tokens.get("input", 0)
                    output_tokens = tokens.get("output", 0)
                    voyage_tokens = tokens.get("voyage", 0)
                    credits_used = max(1, ceil((input_tokens + output_tokens) / 100))

                    # Collect tool metadata from done event for achievement context
                    tool_meta = {}
                    meta = chunk.get("metadata", {})
                    for key in ("site_ids_found", "countries_found", "periods_found", "tool_calls_count", "history_length"):
                        if key in meta:
                            tool_meta[key] = meta[key]

                    # Reconcile: 1 credit already deducted as deposit
                    credits_remaining, new_achievements, chat_streak = _reconcile_credits(
                        user_id=user_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        voyage_tokens=voyage_tokens,
                        credits_used=credits_used,
                        context_type=context_type,
                        has_images=bool(images),
                        tool_metadata=tool_meta,
                    )

                    if "metadata" not in chunk:
                        chunk["metadata"] = {}
                    chunk["metadata"]["credits_used"] = credits_used
                    chunk["metadata"]["credits_remaining"] = credits_remaining
                    chunk["metadata"]["chat_streak"] = chat_streak

                yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"

                # Emit achievements SSE event if any were unlocked
                if event_type == "done" and new_achievements:
                    yield f"event: achievements\ndata: {json.dumps({'type': 'achievements', 'achievements': new_achievements})}\n\n"

        except Exception as e:
            logger.error(f"Lyra stream error: {e}", exc_info=True)
            # Refund the 1-credit deposit if done event never fired (no answer generated)
            if not done_fired:
                try:
                    with get_db_session() as session:
                        u = (
                            session.query(DBUser)
                            .filter(DBUser.id == user_id)
                            .with_for_update()
                            .first()
                        )
                        if u:
                            u.credits += 1
                except Exception:
                    logger.error("Failed to refund deposit after stream error", exc_info=True)
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


def _reconcile_credits(
    user_id: uuid.UUID,
    input_tokens: int,
    output_tokens: int,
    voyage_tokens: int,
    credits_used: int,
    context_type: str = "global",
    has_images: bool = False,
    tool_metadata: dict | None = None,
) -> tuple[int, list[dict], int]:
    """Reconcile credits after streaming. 1 credit was already pre-deducted as deposit.

    If real cost > 1: deduct the remainder.
    If real cost == 1: no adjustment needed (deposit covers it).
    Logs usage regardless.
    Returns (remaining_credits, newly_unlocked_achievements, chat_streak).
    """
    from pipeline.database import DiscordUser, TokenUsageLog, get_session

    additional = credits_used - 1  # deposit was 1

    with get_session() as session:
        user = (
            session.query(DiscordUser).filter(DiscordUser.id == user_id).with_for_update().first()
        )
        if not user:
            return 0, [], 0

        if additional > 0:
            user.credits = max(0, user.credits - additional)

        session.add(
            TokenUsageLog(
                user_id=user_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                voyage_tokens=voyage_tokens,
                credits_used=credits_used,
            )
        )
        remaining = user.credits

        # Build enriched context for achievement checks
        from api.cardgame.achievements import check_achievements

        ctx: dict = {
            "context_type": context_type,
            "has_images": has_images,
        }
        if tool_metadata:
            ctx.update(tool_metadata)

        unlocked = check_achievements(
            session,
            user_id,
            "lyra_chat",
            context=ctx,
        )

        # Track chat streak
        _update_chat_streak(session, user_id)

        # Read back streak for frontend
        from api.cardgame.models import CardPlayerStats
        ps = session.get(CardPlayerStats, user_id)
        streak = (ps.feature_flags or {}).get("lyra_chat_streak", 0) if ps else 0

    return remaining, unlocked, streak


def _update_chat_streak(session: "Session", user_id: uuid.UUID) -> None:  # type: ignore[name-defined]  # noqa: F821
    """Update daily chat streak in CardPlayerStats.feature_flags."""
    from datetime import date

    from api.cardgame.models import CardPlayerStats

    ps = session.get(CardPlayerStats, user_id)
    if not ps:
        return

    flags = ps.feature_flags or {}
    today = date.today().isoformat()
    last_chat = flags.get("lyra_last_chat_date")

    if last_chat == today:
        return  # already chatted today

    yesterday = (date.today() - __import__("datetime").timedelta(days=1)).isoformat()
    if last_chat == yesterday:
        flags["lyra_chat_streak"] = flags.get("lyra_chat_streak", 0) + 1
    else:
        flags["lyra_chat_streak"] = 1

    flags["lyra_last_chat_date"] = today
    ps.feature_flags = flags
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(ps, "feature_flags")
