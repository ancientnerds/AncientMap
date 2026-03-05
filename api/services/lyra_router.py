"""
Lyra model router — keyword heuristic routing + per-request context.

Routes incoming requests to the appropriate model tier:
  - "premium" (MiniMax) — credit-based, highest quality
  - "heavy" (Qwen3.5 2B, think=on) — complex queries, thinking + tools + retrieval
  - "trivial" (Qwen3.5 2B, think=off) — greetings, meta, reactions; no tools, no retrieval
"""

import os
import re
from contextvars import ContextVar
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Model configuration from env
# ---------------------------------------------------------------------------

LOCAL_MODEL = os.getenv("LYRA_OLLAMA_MODEL", "qwen3.5:2b")


# ---------------------------------------------------------------------------
# Per-request context (replaces lyra_tools._current_backend global)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context. Passed through the pipeline."""

    backend_type: str  # "minimax" | "local"
    model_tier: str  # "trivial" | "heavy" | "premium"
    model_name: str  # "qwen3.5:2b" | "MiniMax-M2.5"
    embedding_backend: str  # "voyage" | "local"
    supports_thinking: bool  # True for heavy, False for trivial
    supports_tools: bool  # True for heavy, False for trivial


_request_ctx: ContextVar[RequestContext] = ContextVar("lyra_request_ctx")


def get_request_context() -> RequestContext:
    """Get the current request context (raises LookupError if not set)."""
    return _request_ctx.get()


def set_request_context(ctx: RequestContext) -> None:
    """Set the current request context."""
    _request_ctx.set(ctx)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def route_request(backend: str, message: str) -> RequestContext:
    """Route to the right model. Called once at request start.

    Args:
        backend: "minimax" or "local" (from frontend toggle).
        message: The user's message text (for tier classification).
    """
    if backend == "minimax":
        from api.services.lyra_tools import LLM_MODEL

        return RequestContext(
            backend_type="minimax",
            model_tier="premium",
            model_name=LLM_MODEL,
            embedding_backend="voyage",
            supports_thinking=True,
            supports_tools=True,
        )

    tier = _classify_query(message)
    if tier == "trivial":
        return RequestContext(
            backend_type="local",
            model_tier="trivial",
            model_name=LOCAL_MODEL,
            embedding_backend="local",
            supports_thinking=False,
            supports_tools=False,
        )
    else:
        return RequestContext(
            backend_type="local",
            model_tier="heavy",
            model_name=LOCAL_MODEL,
            embedding_backend="local",
            supports_thinking=True,
            supports_tools=True,
        )


# ---------------------------------------------------------------------------
# Query classifier — zero-latency keyword heuristic
# ---------------------------------------------------------------------------

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|sup|yo|howdy|greetings|hola|hei|heya)\b", re.IGNORECASE),
    re.compile(r"^(good\s+(morning|afternoon|evening|day))\b", re.IGNORECASE),
]

_SIMPLE_PATTERNS = [
    re.compile(r"^(who are you|what are you|what can you do)\b", re.IGNORECASE),
    re.compile(r"^(help|thanks|thank you|ok|okay|yes|no|bye|goodbye)\b", re.IGNORECASE),
    re.compile(r"^(what[\u2018\u2019']?s? up|how are you|nice to meet you)\b", re.IGNORECASE),
    re.compile(r"^(test|ping|are you there|you there)\b", re.IGNORECASE),
]


def _classify_query(message: str) -> str:
    """Keyword heuristic — zero latency.

    Returns "trivial" for greetings/meta/reactions (think=off, no tools),
    "heavy" for everything else (think=on, tools + retrieval).
    """
    msg = message.strip()

    # Greetings → trivial
    for pattern in _GREETING_PATTERNS:
        if pattern.search(msg):
            return "trivial"

    # Simple meta → trivial
    for pattern in _SIMPLE_PATTERNS:
        if pattern.search(msg):
            return "trivial"

    # Very short messages without query keywords → trivial
    if len(msg) < 12:
        if any(
            kw in msg.lower()
            for kw in ("site", "find", "search", "show", "where", "what", "tell", "list")
        ):
            return "heavy"
        return "trivial"

    # Everything else → heavy (thinking + tools + retrieval)
    return "heavy"


def get_classification_reason(ctx: RequestContext) -> str:
    """Human-readable explanation of why a tier was chosen (shown in pipeline UI)."""
    if ctx.model_tier == "trivial":
        return "Greeting/meta \u2192 think=off, no tools"
    if ctx.model_tier == "heavy":
        return "Query \u2192 think=on, tools + retrieval"
    return "Premium cloud model"
