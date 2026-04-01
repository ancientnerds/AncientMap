"""
Lyra model router — per-request context.

Lyra uses Anthropic (Haiku/Sonnet/Opus). Theo uses MiniMax M2.7 (configured separately).
"""

from contextvars import ContextVar
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Per-request context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context. Passed through the pipeline."""

    backend_type: str  # "anthropic" | "minimax"
    model_tier: str  # "premium" | "heavy"
    model_name: str
    embedding_backend: str  # "voyage"
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


def route_request(backend: str, message: str) -> RequestContext:
    """Route to Anthropic cloud LLM. Called once at request start.

    Args:
        backend: Unused, kept for API compat.
        message: The user's message text (unused, kept for API compat).
    """
    from api.services.lyra_tools import LLM_MODEL

    return RequestContext(
        backend_type="anthropic",
        model_tier="premium",
        model_name=LLM_MODEL,
        embedding_backend="voyage",
        supports_thinking=False,
        supports_tools=True,
    )


def get_classification_reason(ctx: RequestContext) -> str:
    """Human-readable explanation of why a tier was chosen (shown in pipeline UI)."""
    if ctx.model_tier == "heavy":
        return "MiniMax M2.7 \u2192 think=on, tools + retrieval"
    return "Premium cloud model"
