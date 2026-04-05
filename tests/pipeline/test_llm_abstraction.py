"""Tests for the unified LLM abstraction layer in config.py."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.config import (
    LyraSettings,
    NormalizedResponse,
    TextBlock,
    _call_anthropic_api,
)


@pytest.fixture
def anthropic_settings():
    return LyraSettings(
        anthropic_api_key="sk-ant-test",
        llm_backend="anthropic",
    )


@pytest.fixture
def minimax_settings():
    return LyraSettings(
        minimax_api_key="sk-cp-test",
        minimax_base_url="https://api.minimax.io/anthropic",
        llm_backend="minimax",
    )


class TestClientSelection:
    def test_anthropic_backend_uses_anthropic_client(self, anthropic_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(anthropic_settings)
            mock.assert_called_once_with("sk-ant-test")

    def test_minimax_backend_uses_minimax_anthropic_client(self, minimax_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_minimax_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(minimax_settings)
            mock.assert_called_once_with(minimax_settings)


import json


class TestStructuredOutputToolTrick:
    def test_build_tool_from_schema(self):
        from pipeline.lyra.config import _build_structured_output_tool

        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer"}},
            "required": ["score"],
        }
        tool = _build_structured_output_tool(schema)
        assert tool["name"] == "structured_output"
        assert tool["input_schema"] == schema
        assert "description" in tool

    def test_extract_tool_result_from_tool_use_block(self):
        from pipeline.lyra.config import _extract_tool_use_json

        # Simulate Anthropic SDK response content blocks
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Let me reason..."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "structured_output"
        tool_block.input = {"score": 85, "reason": "important discovery"}

        content = [thinking_block, tool_block]
        result = _extract_tool_use_json(content)
        assert result == '{"score": 85, "reason": "important discovery"}'

    def test_extract_tool_result_no_tool_block_returns_none(self):
        from pipeline.lyra.config import _extract_tool_use_json

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = '{"score": 85}'

        result = _extract_tool_use_json([text_block])
        assert result is None

    def test_extract_tool_result_empty_content(self):
        from pipeline.lyra.config import _extract_tool_use_json

        result = _extract_tool_use_json([])
        assert result is None


# ---------------------------------------------------------------------------
# Helpers for TestUnifiedDispatch
# ---------------------------------------------------------------------------


def _make_mock_text_response(text="result"):
    """Create a mock Anthropic Messages response with a text block."""
    mock_resp = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    text_block.citations = None
    mock_resp.content = [text_block]
    mock_resp.stop_reason = "end_turn"
    mock_resp.model = "test-model"
    mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return mock_resp


def _make_mock_tool_response(tool_input: dict):
    """Create a mock Anthropic Messages response with a tool_use block."""
    mock_resp = MagicMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "structured_output"
    tool_block.input = tool_input
    mock_resp.content = [tool_block]
    mock_resp.stop_reason = "end_turn"
    mock_resp.model = "MiniMax-M2.7"
    mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return mock_resp


class TestUnifiedDispatch:
    def test_anthropic_structured_output_uses_output_config(self, anthropic_settings):
        """Anthropic backend uses native output_config for json_schema."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response('{"score": 85}')

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                anthropic_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"score": {"type": "integer"}},
                        },
                    },
                },
            )

        assert "output_config" in captured
        assert "tools" not in captured

    def test_minimax_structured_output_uses_tool_trick(self, minimax_settings):
        """MiniMax backend converts json_schema into forced tool call."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_tool_response({"score": 85})

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            resp = _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"score": {"type": "integer"}},
                        },
                    },
                },
            )

        assert "output_config" not in captured
        assert "tools" in captured
        assert captured["tools"][0]["name"] == "structured_output"
        assert captured["tool_choice"] == {"type": "tool", "name": "structured_output"}
        assert captured["model"] == "MiniMax-M2.7"
        assert resp.text == '{"score": 85}'

    def test_minimax_temperature_clamped(self, minimax_settings):
        """MiniMax clamps temperature=0.0 to 0.01."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                temperature=0.0,
                messages=[{"role": "user", "content": "test"}],
            )

        assert captured["temperature"] == 0.01

    def test_minimax_model_override(self, minimax_settings):
        """MiniMax overrides all model names to MiniMax-M2.7."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-opus-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
            )

        assert captured["model"] == "MiniMax-M2.7"

    def test_minimax_documents_inlined(self, minimax_settings):
        """MiniMax inlines documents into user message text."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "Summarize this."}],
                documents=[{"title": "Source 1", "data": "Source text here."}],
            )

        msgs = captured["messages"]
        user_content = msgs[-1]["content"]
        assert isinstance(user_content, str)
        assert "Source 1" in user_content
        assert "Source text here." in user_content
        assert "Summarize this." in user_content

    def test_minimax_tool_trick_fallback_to_text(self, minimax_settings):
        """If MiniMax returns text instead of tool_use, fall back to text."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response('{"score": 85}')

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            resp = _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"score": {"type": "integer"}},
                        },
                    },
                },
            )

        assert resp.text == '{"score": 85}'

    def test_anthropic_thinking_passed_through(self, anthropic_settings):
        """Anthropic backend passes thinking config through."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("article body here")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                anthropic_settings,
                model="claude-opus-4-6",
                max_tokens=128000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": "Write article"}],
            )

        assert captured["thinking"] == {"type": "adaptive"}
        assert "temperature" not in captured

    def test_minimax_thinking_passed_through(self, minimax_settings):
        """MiniMax Anthropic endpoint also supports thinking."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("article body here")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-opus-4-6",
                max_tokens=128000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": "Write article"}],
            )

        assert captured["thinking"] == {"type": "adaptive"}
        assert captured["model"] == "MiniMax-M2.7"
