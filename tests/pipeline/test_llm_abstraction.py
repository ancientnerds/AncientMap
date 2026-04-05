"""Tests for the unified LLM abstraction layer in config.py."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.config import LyraSettings


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
