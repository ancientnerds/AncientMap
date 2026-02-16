"""
OpenAI-compatible API wrapper for Lyra.

Exposes /v1/models and /v1/chat/completions so that Open WebUI
(or any OpenAI-compatible client) can talk to Lyra's LangChain agent.
"""

import json
import logging
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

LYRA_ADMIN_KEY = os.getenv("LYRA_ADMIN_KEY", "")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_bearer(authorization: str | None) -> None:
    """Validate Authorization: Bearer <LYRA_ADMIN_KEY>."""
    if not LYRA_ADMIN_KEY:
        raise HTTPException(status_code=503, detail="LYRA_ADMIN_KEY not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer <key> required")
    if not secrets.compare_digest(authorization[7:], LYRA_ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class _ContentPart(BaseModel):
    type: str
    text: str | None = None
    image_url: dict | None = None


class _Message(BaseModel):
    role: str
    content: str | list[_ContentPart]


class ChatCompletionRequest(BaseModel):
    model: str = "lyra"
    messages: list[_Message] = Field(..., min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

@router.get("/v1/models")
async def list_models(authorization: str | None = Header(None)):
    _verify_bearer(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": "lyra",
                "object": "model",
                "created": 1700000000,
                "owned_by": "ancient-nerds",
            }
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

def _extract_lyra_params(messages: list[_Message]) -> dict:
    """Convert OpenAI messages list into run_agent_stream() kwargs."""
    # Last user message becomes the prompt
    message_text = ""
    images: list[dict] = []

    # Find last user message
    last_user = None
    for msg in reversed(messages):
        if msg.role == "user":
            last_user = msg
            break

    if last_user is None:
        raise HTTPException(status_code=400, detail="No user message found")

    if isinstance(last_user.content, str):
        message_text = last_user.content
    else:
        for part in last_user.content:
            if part.type == "text" and part.text:
                message_text += part.text
            elif part.type == "image_url" and part.image_url:
                url = part.image_url.get("url", "")
                if url:
                    images.append({"data": url})

    # Build history from all messages except the last user message
    # (only user + assistant messages; skip system — Lyra has its own)
    history: list[dict] = []
    for msg in messages:
        if msg is last_user:
            break
        if msg.role in ("user", "assistant"):
            content = msg.content if isinstance(msg.content, str) else " ".join(
                p.text for p in msg.content if p.type == "text" and p.text
            )
            history.append({"role": msg.role, "content": content})

    return {
        "message": message_text,
        "images": images or None,
        "history": history or None,
        "context_type": "global",
        "context_id": None,
        "context_year": None,
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(None),
):
    _verify_bearer(authorization)

    params = _extract_lyra_params(request.messages)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if request.stream:
        return _stream_openai(completion_id, created, params)
    else:
        return await _buffer_openai(completion_id, created, params)


# ---------------------------------------------------------------------------
# Streaming response (SSE in OpenAI format)
# ---------------------------------------------------------------------------

def _stream_openai(completion_id: str, created: int, params: dict) -> StreamingResponse:
    async def generate():
        from api.services.lyra_agent import run_agent_stream

        collected_sites: list[dict] = []
        collected_news: list[dict] = []

        async for chunk in run_agent_stream(**params):
            event_type = chunk.get("type", "")

            if event_type == "token":
                text = chunk.get("content", "")
                if text:
                    yield _sse_chunk(completion_id, created, text)

            elif event_type == "status":
                # Stream tool-use status as italic markdown
                status_text = chunk.get("content", "")
                if status_text:
                    yield _sse_chunk(completion_id, created, f"\n\n*{status_text}*\n\n")

            elif event_type == "sites":
                collected_sites = chunk.get("sites", [])

            elif event_type == "news":
                collected_news = chunk.get("news", [])

            elif event_type == "done":
                # Append referenced sites as markdown
                if collected_sites:
                    sites_md = "\n\n---\n**Referenced Sites:**\n"
                    for s in collected_sites[:20]:
                        name = s.get("name", "Unknown")
                        country = s.get("country", "")
                        site_type = s.get("site_type", "")
                        parts = [p for p in [site_type, country] if p]
                        label = f"{name} ({', '.join(parts)})" if parts else name
                        sites_md += f"- {label}\n"
                    yield _sse_chunk(completion_id, created, sites_md)

                # Append news as YouTube links
                if collected_news:
                    news_md = "\n\n**Related News:**\n"
                    for n in collected_news[:10]:
                        headline = n.get("headline", "Video")
                        vid = n.get("video_id", "")
                        channel = n.get("channel", "")
                        if vid:
                            news_md += f"- [{headline}](https://youtube.com/watch?v={vid})"
                        else:
                            news_md += f"- {headline}"
                        if channel:
                            news_md += f" — {channel}"
                        news_md += "\n"
                    yield _sse_chunk(completion_id, created, news_md)

                # Final chunk with finish_reason + usage
                metadata = chunk.get("metadata", {})
                tokens = metadata.get("tokens", {})
                yield _sse_finish(completion_id, created, tokens)
                yield "data: [DONE]\n\n"
                return

            elif event_type == "error":
                error_msg = chunk.get("error", "An error occurred")
                yield _sse_chunk(completion_id, created, f"\n\n**Error:** {error_msg}")
                yield _sse_finish(completion_id, created, {})
                yield "data: [DONE]\n\n"
                return

        # If we exit the loop without a done event, close gracefully
        yield _sse_finish(completion_id, created, {})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_chunk(completion_id: str, created: int, content: str) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": "lyra",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _sse_finish(completion_id: str, created: int, tokens: dict) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": "lyra",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": tokens.get("input", 0),
            "completion_tokens": tokens.get("output", 0),
            "total_tokens": tokens.get("input", 0) + tokens.get("output", 0),
        },
    }
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Non-streaming response
# ---------------------------------------------------------------------------

async def _buffer_openai(completion_id: str, created: int, params: dict) -> JSONResponse:
    from api.services.lyra_agent import run_agent_stream

    full_content = ""
    collected_sites: list[dict] = []
    collected_news: list[dict] = []
    tokens: dict = {}

    async for chunk in run_agent_stream(**params):
        event_type = chunk.get("type", "")

        if event_type == "token":
            full_content += chunk.get("content", "")
        elif event_type == "status":
            pass  # Skip status in non-streaming (tool use is invisible)
        elif event_type == "sites":
            collected_sites = chunk.get("sites", [])
        elif event_type == "news":
            collected_news = chunk.get("news", [])
        elif event_type == "done":
            metadata = chunk.get("metadata", {})
            tokens = metadata.get("tokens", {})
        elif event_type == "error":
            raise HTTPException(status_code=500, detail=chunk.get("error", "Agent error"))

    # Append sites and news to content
    if collected_sites:
        full_content += "\n\n---\n**Referenced Sites:**\n"
        for s in collected_sites[:20]:
            name = s.get("name", "Unknown")
            country = s.get("country", "")
            site_type = s.get("site_type", "")
            parts = [p for p in [site_type, country] if p]
            label = f"{name} ({', '.join(parts)})" if parts else name
            full_content += f"- {label}\n"

    if collected_news:
        full_content += "\n\n**Related News:**\n"
        for n in collected_news[:10]:
            headline = n.get("headline", "Video")
            vid = n.get("video_id", "")
            channel = n.get("channel", "")
            if vid:
                full_content += f"- [{headline}](https://youtube.com/watch?v={vid})"
            else:
                full_content += f"- {headline}"
            if channel:
                full_content += f" — {channel}"
            full_content += "\n"

    return JSONResponse({
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": "lyra",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": full_content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": tokens.get("input", 0),
            "completion_tokens": tokens.get("output", 0),
            "total_tokens": tokens.get("input", 0) + tokens.get("output", 0),
        },
    })
