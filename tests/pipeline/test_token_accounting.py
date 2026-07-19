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


# --- Cache-token accounting (2026-07-19) -------------------------------------
# Live probe against MiniMax M3 (Anthropic-compat endpoint) showed:
#     Usage(input_tokens=61, output_tokens=54, cache_read_input_tokens=128, ...)
# — cached input is reported SEPARATELY from input_tokens. Theo's repetitive
# system prompts and accumulated source contexts hit MiniMax's implicit prompt
# cache, so the bulk of real input landed in cache fields the accounting never
# read: a 6h research run recorded ~458k tokens while draining ~2 full 9.7M
# five-hour quota blocks (~20x undercount).


def test_add_usage_counts_cache_fields() -> None:
    state = _FakeState()
    tok = token_accounting.bind(state)
    try:
        token_accounting.add_usage(
            {
                "input_tokens": 61,
                "output_tokens": 54,
                "cache_read_input_tokens": 128,
                "cache_creation_input_tokens": 10,
            }
        )
        assert state.total_tokens == 61 + 54 + 128 + 10
    finally:
        token_accounting.unbind(tok)


def test_usage_to_dict_extracts_all_fields() -> None:
    """Mirror of the live M3 Usage object shape from the 2026-07-19 probe."""
    from types import SimpleNamespace

    usage = SimpleNamespace(
        input_tokens=61,
        output_tokens=54,
        cache_read_input_tokens=128,
        cache_creation_input_tokens=0,
    )
    assert token_accounting.usage_to_dict(usage) == {
        "input_tokens": 61,
        "output_tokens": 54,
        "cache_read_input_tokens": 128,
        "cache_creation_input_tokens": 0,
    }


def test_usage_to_dict_handles_missing_and_none() -> None:
    """Anthropic-proper or older shapes may lack cache fields or carry None."""
    from types import SimpleNamespace

    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=None)
    d = token_accounting.usage_to_dict(usage)
    assert d["input_tokens"] == 10
    assert d["output_tokens"] == 5
    assert d["cache_read_input_tokens"] == 0
    assert d["cache_creation_input_tokens"] == 0
    assert token_accounting.usage_to_dict(None) == {}


def test_all_llm_paths_credit_full_usage() -> None:
    """Every LLM call path must build its usage dict via usage_to_dict (or
    the config-side token_accounting_usage helper wrapping it) so cache
    fields are never silently dropped again. Source-level check, same
    style as test_retry_limit_reduced_to_two."""
    import inspect

    from pipeline.lyra import config, minimax_shared

    # The shared helper itself must go through usage_to_dict...
    assert "usage_to_dict" in inspect.getsource(config.token_accounting_usage)
    # ...and both response paths must use it.
    assert "token_accounting_usage(" in inspect.getsource(config._normalize_anthropic_response)
    assert "usage_to_dict(" in inspect.getsource(minimax_shared.minimax_chat_anthropic)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
