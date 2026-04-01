# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Lyra LLM backend abstraction — AnthropicBackend, factory."""

import os

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.services.lyra_backends import (
    AnthropicBackend,
    _langchain_messages_to_openai,
    _langchain_tools_to_openai,
    get_backend,
)

# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


class TestMessageConversion:
    def test_system_message(self):
        from langchain_core.messages import SystemMessage

        msgs = _langchain_messages_to_openai([SystemMessage(content="Hello")])
        assert msgs == [{"role": "system", "content": "Hello"}]

    def test_human_message(self):
        from langchain_core.messages import HumanMessage

        msgs = _langchain_messages_to_openai([HumanMessage(content="Hi")])
        assert msgs == [{"role": "user", "content": "Hi"}]

    def test_ai_message_no_tools(self):
        from langchain_core.messages import AIMessage

        msgs = _langchain_messages_to_openai([AIMessage(content="Sure")])
        assert msgs == [{"role": "assistant", "content": "Sure"}]

    def test_ai_message_with_tools(self):
        from langchain_core.messages import AIMessage

        ai = AIMessage(
            content="Let me search",
            tool_calls=[{"id": "call_1", "name": "search_sites", "args": {"query": "pompeii"}}],
        )
        msgs = _langchain_messages_to_openai([ai])
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert len(msgs[0]["tool_calls"]) == 1
        tc = msgs[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "search_sites"
        assert '"pompeii"' in tc["function"]["arguments"]

    def test_tool_message(self):
        from langchain_core.messages import ToolMessage

        msgs = _langchain_messages_to_openai(
            [ToolMessage(content="result data", tool_call_id="call_1")]
        )
        assert msgs == [{"role": "tool", "tool_call_id": "call_1", "content": "result data"}]

    def test_full_conversation(self):
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        msgs = _langchain_messages_to_openai(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user msg"),
                AIMessage(content="", tool_calls=[{"id": "c1", "name": "t1", "args": {}}]),
                ToolMessage(content="result", tool_call_id="c1"),
                AIMessage(content="answer"),
            ]
        )
        assert len(msgs) == 5
        assert [m["role"] for m in msgs] == [
            "system",
            "user",
            "assistant",
            "tool",
            "assistant",
        ]


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


class TestToolConversion:
    def test_converts_langchain_tool(self):
        from langchain_core.tools import tool

        @tool
        def dummy_tool(query: str) -> str:
            """A dummy tool."""
            return query

        result = _langchain_tools_to_openai([dummy_tool])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "dummy_tool"


# ---------------------------------------------------------------------------
# AnthropicBackend
# ---------------------------------------------------------------------------


class TestAnthropicBackend:
    def test_init(self):
        backend = AnthropicBackend(
            model="claude-haiku-4-5-20251001",
            api_key="test-key",
            max_tokens=8192,
        )
        assert backend.model == "claude-haiku-4-5-20251001"
        assert backend.max_tokens == 8192

    def test_client_created_on_init(self):
        backend = AnthropicBackend(model="test", api_key="key", max_tokens=4096)
        assert backend._client is not None


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


class TestGetBackend:
    def setup_method(self):
        # Clear backend cache between tests
        from api.services import lyra_backends

        lyra_backends._backends.clear()

    def test_creates_anthropic_for_anthropic(self):
        backend = get_backend("claude-haiku-4-5-20251001", "anthropic")
        assert isinstance(backend, AnthropicBackend)

    def test_caches_backends(self):
        b1 = get_backend("claude-haiku-4-5-20251001", "anthropic")
        b2 = get_backend("claude-haiku-4-5-20251001", "anthropic")
        assert b1 is b2

    def test_different_models_different_backends(self):
        b1 = get_backend("claude-haiku-4-5-20251001", "anthropic")
        b2 = get_backend("claude-sonnet-4-20250514", "anthropic")
        assert b1 is not b2
