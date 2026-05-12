"""Contextvar-based token accumulator for Theo / Lyra runs.

`state.total_tokens` has historically been an unused field — the DB
completion write read 0 every time despite hundreds of LLM calls per
run. Threading the token count back through every call signature would
touch ~15 caller sites including non-Theo code (article_generator,
journal_assessor, …), so we route it via a contextvar instead.

Usage:
    # At the top of a long-running run (e.g. ConvergenceOrchestrator.run):
    token_accounting.bind(state)

    # … inside every LLM-call helper:
    token_accounting.add_usage(usage_dict)

The contextvar propagates through `asyncio.create_task` and
`asyncio.to_thread` (which `copy_context()` internally), so handler
chains that hop between coroutines and worker threads still credit the
right state.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger(__name__)

# The state object whose total_tokens field should be incremented for
# LLM calls made within this context. `None` means we're outside a
# tracked run — calls then no-op silently.
_active_state: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "theo_active_state", default=None
)


def bind(state) -> contextvars.Token:
    """Bind a ResearchState to the current async context.

    Returns the contextvar Token so the caller can restore the previous
    binding (rarely needed — runs are full-process scoped in practice).
    """
    return _active_state.set(state)


def unbind(token: contextvars.Token) -> None:
    """Restore the previous binding (or unset)."""
    _active_state.reset(token)


def add_usage(usage: dict | None) -> None:
    """Add `input_tokens + output_tokens` to the bound state's counter.

    Silently no-ops when no state is bound (e.g. CLI scripts, tests).
    Silently no-ops on malformed usage shapes.
    """
    if not usage:
        return
    state = _active_state.get()
    if state is None:
        return
    try:
        tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
    except (TypeError, ValueError):
        return
    if tokens <= 0:
        return
    # ResearchState.total_tokens is a plain int — no lock needed because
    # asyncio handlers run on the same event loop thread; the only thread
    # hop is asyncio.to_thread which copies the contextvar but doesn't
    # parallelise writes (the worker holds the GIL during the add).
    state.total_tokens = getattr(state, "total_tokens", 0) + tokens
