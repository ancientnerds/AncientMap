"""
Lyra model router — keyword heuristic routing + per-request context.

Routes incoming requests to the appropriate model tier:
  - "premium" (MiniMax) — credit-based, highest quality
  - "heavy" (Qwen3.5 4B) — complex queries, tool calling, thinking
  - "fast" (Qwen3.5 0.8B) — greetings, simple meta questions
"""

import os
import re
from contextvars import ContextVar
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Model configuration from env
# ---------------------------------------------------------------------------

HEAVY_MODEL = os.getenv("LYRA_OLLAMA_MODEL_HEAVY", "qwen3.5:4b")
FAST_MODEL = os.getenv("LYRA_OLLAMA_MODEL_FAST", "qwen3.5:0.8b")


# ---------------------------------------------------------------------------
# Per-request context (replaces lyra_tools._current_backend global)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context. Passed through the pipeline."""

    backend_type: str  # "minimax" | "local"
    model_tier: str  # "fast" | "heavy" | "premium"
    model_name: str  # "qwen3.5:0.8b" | "qwen3.5:4b" | "MiniMax-M2.5"
    embedding_backend: str  # "voyage" | "local"
    supports_thinking: bool  # True for 4B+, False for 0.8B
    supports_tools: bool  # True for all


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
    if tier == "fast":
        return RequestContext(
            backend_type="local",
            model_tier="fast",
            model_name=FAST_MODEL,
            embedding_backend="local",
            supports_thinking=False,
            supports_tools=True,
        )
    else:
        return RequestContext(
            backend_type="local",
            model_tier="heavy",
            model_name=HEAVY_MODEL,
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
    re.compile(r"^(what'?s? up|how are you|nice to meet you)\b", re.IGNORECASE),
    re.compile(r"^(test|ping|are you there|you there)\b", re.IGNORECASE),
]


def _classify_query(message: str) -> str:
    """Keyword heuristic — zero latency.

    Returns "fast" for simple queries, "heavy" for everything else.
    """
    msg = message.strip()

    # Very short messages are simple
    if len(msg) < 12:
        # Check if it's a short but complex query (e.g. "sites in Crete")
        if any(
            kw in msg.lower()
            for kw in ("site", "find", "search", "show", "where", "what", "tell", "list")
        ):
            return "heavy"
        return "fast"

    # Check greeting patterns
    for pattern in _GREETING_PATTERNS:
        if pattern.search(msg):
            return "fast"

    # Check simple meta patterns
    for pattern in _SIMPLE_PATTERNS:
        if pattern.search(msg):
            return "fast"

    # Default: capable model for archaeology queries
    return "heavy"
