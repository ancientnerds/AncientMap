# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Lyra model router — query classification and RequestContext routing."""

import os

import pytest

# Ensure env vars are set before importing
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.services.lyra_router import (
    RequestContext,
    _classify_query,
    route_request,
)

# ---------------------------------------------------------------------------
# _classify_query — keyword heuristic
# ---------------------------------------------------------------------------


class TestClassifyQuery:
    """Test the zero-latency keyword heuristic classifier."""

    # -- Greetings → fast --

    @pytest.mark.parametrize(
        "msg",
        [
            "hi",
            "Hello",
            "Hey there",
            "hey Lyra",
            "sup",
            "yo",
            "howdy",
            "greetings",
            "hola",
            "hei",
            "heya",
            "Good morning",
            "good afternoon",
            "Good evening",
            "good day",
        ],
    )
    def test_greetings_route_to_fast(self, msg: str):
        assert _classify_query(msg) == "fast"

    # -- Simple meta questions → fast --

    @pytest.mark.parametrize(
        "msg",
        [
            "who are you",
            "what are you",
            "what can you do",
            "help",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "yes",
            "no",
            "bye",
            "goodbye",
            "what's up",
            "how are you",
            "nice to meet you",
            "test",
            "ping",
            "are you there",
        ],
    )
    def test_simple_meta_questions_route_to_fast(self, msg: str):
        assert _classify_query(msg) == "fast"

    # -- Short non-query messages → fast --

    @pytest.mark.parametrize("msg", ["wow", "cool", "nice", "lol", "hmm", "k"])
    def test_short_non_query_messages_fast(self, msg: str):
        assert _classify_query(msg) == "fast"

    # -- Short but complex queries → heavy --

    @pytest.mark.parametrize(
        "msg",
        [
            "find sites",
            "search it",
            "show Crete",
            "where is it",
            "what is it",
            "tell me",
            "list sites",
        ],
    )
    def test_short_complex_queries_route_to_heavy(self, msg: str):
        assert _classify_query(msg) == "heavy"

    # -- Archaeology queries → heavy --

    @pytest.mark.parametrize(
        "msg",
        [
            "What Minoan sites are on Crete?",
            "Tell me about Göbekli Tepe",
            "Show me Bronze Age settlements in Turkey",
            "What are the oldest sites in Egypt?",
            "Compare Roman and Greek temple architecture",
            "recent discoveries in underwater archaeology",
            "What has MegalithomaniaUK been covering?",
        ],
    )
    def test_archaeology_queries_route_to_heavy(self, msg: str):
        assert _classify_query(msg) == "heavy"

    # -- Edge cases --

    def test_empty_string(self):
        assert _classify_query("") == "fast"

    def test_whitespace_only(self):
        assert _classify_query("   ") == "fast"

    def test_greeting_with_question(self):
        # "hello" at the start triggers greeting pattern
        assert _classify_query("hello there") == "fast"

    def test_long_greeting(self):
        # Greeting pattern should still match even with extra words
        assert _classify_query("hey Lyra, how are you doing today?") == "fast"

    def test_12_char_boundary(self):
        # < 12 chars without keywords → fast
        assert _classify_query("interesting") == "fast"  # 11 chars
        # >= 12 chars without pattern match → heavy
        assert _classify_query("very curious") == "heavy"  # 12 chars


# ---------------------------------------------------------------------------
# route_request — full routing
# ---------------------------------------------------------------------------


class TestRouteRequest:
    """Test the full route_request() function."""

    def test_minimax_returns_premium_context(self):
        ctx = route_request("minimax", "anything")
        assert ctx.backend_type == "minimax"
        assert ctx.model_tier == "premium"
        assert ctx.embedding_backend == "voyage"
        assert ctx.supports_thinking is True
        assert ctx.supports_tools is True

    def test_local_greeting_returns_fast_context(self):
        ctx = route_request("local", "hi there")
        assert ctx.backend_type == "local"
        assert ctx.model_tier == "fast"
        assert ctx.embedding_backend == "local"
        assert ctx.supports_thinking is False
        assert ctx.supports_tools is True

    def test_local_complex_returns_heavy_context(self):
        ctx = route_request("local", "What sites are in Turkey?")
        assert ctx.backend_type == "local"
        assert ctx.model_tier == "heavy"
        assert ctx.embedding_backend == "local"
        assert ctx.supports_thinking is True
        assert ctx.supports_tools is True

    def test_request_context_is_frozen(self):
        ctx = route_request("minimax", "hello")
        with pytest.raises(AttributeError):
            ctx.model_tier = "fast"  # type: ignore[misc]

    def test_model_names_from_env(self, monkeypatch):
        monkeypatch.setenv("LYRA_OLLAMA_MODEL_HEAVY", "test-heavy:7b")
        monkeypatch.setenv("LYRA_OLLAMA_MODEL_FAST", "test-fast:1b")
        # Need to reimport to pick up env change
        import importlib

        import api.services.lyra_router as router_mod

        importlib.reload(router_mod)
        ctx = router_mod.route_request("local", "What is Pompeii?")
        assert ctx.model_name == "test-heavy:7b"
        ctx2 = router_mod.route_request("local", "hi")
        assert ctx2.model_name == "test-fast:1b"
        # Restore
        importlib.reload(router_mod)
