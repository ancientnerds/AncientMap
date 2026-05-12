"""Tests for the contextvar-based token accumulator."""

from __future__ import annotations

import contextvars

import pytest

from pipeline.lyra import token_accounting


class _FakeState:
    """Minimal stand-in for ResearchState — only the attribute we touch."""

    def __init__(self) -> None:
        self.total_tokens = 0


def test_accumulates_in_bound_state() -> None:
    state = _FakeState()
    token_accounting.bind(state)
    token_accounting.add_usage({"input_tokens": 100, "output_tokens": 50})
    token_accounting.add_usage({"input_tokens": 200, "output_tokens": 80})
    assert state.total_tokens == 430


def test_unbinds_cleanly() -> None:
    state = _FakeState()
    tok = token_accounting.bind(state)
    token_accounting.add_usage({"input_tokens": 5, "output_tokens": 5})
    assert state.total_tokens == 10
    token_accounting.unbind(tok)
    # Subsequent add_usage with no state bound is a silent no-op.
    token_accounting.add_usage({"input_tokens": 99, "output_tokens": 99})
    assert state.total_tokens == 10


def test_no_bind_is_silent() -> None:
    # Run inside a fresh context so any previous test's bind doesn't leak.
    def _inner() -> None:
        token_accounting.add_usage({"input_tokens": 100, "output_tokens": 50})

    ctx = contextvars.copy_context()
    # Reset the var inside the fresh context, then call _inner.
    ctx.run(token_accounting._active_state.set, None)
    ctx.run(_inner)
    # We just need it to not raise — nothing to assert about an unbound run.


def test_malformed_usage_is_silent() -> None:
    state = _FakeState()
    token_accounting.bind(state)
    token_accounting.add_usage(None)
    token_accounting.add_usage({})
    token_accounting.add_usage({"input_tokens": "not-a-number", "output_tokens": 5})
    assert state.total_tokens == 0


def test_zero_usage_is_noop() -> None:
    state = _FakeState()
    token_accounting.bind(state)
    token_accounting.add_usage({"input_tokens": 0, "output_tokens": 0})
    assert state.total_tokens == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
