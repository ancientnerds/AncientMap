"""
Lyra model router — per-request context.

Lyra uses Mercury 2 cloud or Anthropic (Haiku/Sonnet/Opus) depending on
LYRA_LLM_BACKEND env var. Theo uses local Ollama (configured separately).
"""

import os
from contextvars import ContextVar
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Per-request context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context. Passed through the pipeline."""

    backend_type: str  # "mercury" | "anthropic" | "local" (local = Theo only)
    model_tier: str  # "premium" | "heavy"
    model_name: str
    embedding_backend: str  # "voyage" | "local"
    supports_thinking: bool
    supports_tools: bool


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


_BACKEND = os.getenv("LYRA_LLM_BACKEND", "mercury")


def route_request(backend: str, message: str) -> RequestContext:
    """Route to cloud LLM. Called once at request start.

    Args:
        backend: Unused, kept for API compat. Routing is controlled by
                 LYRA_LLM_BACKEND env var ("mercury" | "anthropic").
        message: The user's message text (unused, kept for API compat).
    """
    from api.services.lyra_tools import LLM_MODEL

    if _BACKEND == "anthropic":
        return RequestContext(
            backend_type="anthropic",
            model_tier="premium",
            model_name=LLM_MODEL,
            embedding_backend="voyage",
            supports_thinking=False,
            supports_tools=True,
        )

    return RequestContext(
        backend_type="mercury",
        model_tier="premium",
        model_name=LLM_MODEL,
        embedding_backend="voyage",
        supports_thinking=False,
        supports_tools=True,
    )


def get_classification_reason(ctx: RequestContext) -> str:
    """Human-readable explanation of why a tier was chosen (shown in pipeline UI)."""
    if ctx.model_tier == "heavy":
        return "Local model \u2192 think=on, tools + retrieval"
    return "Premium cloud model"
