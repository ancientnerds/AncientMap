"""Tests for the MiniMax tool calling conversion in call_api().

Verifies that:
1. Non-native + output_config + no thinking → tools + tool_choice (not prefill)
2. ToolUseBlock response → TextBlock with serialized JSON (caller-transparent)
3. Thinking-enabled calls bypass tool calling (keep prefill + retry)
4. Calls without output_config are unaffected
5. All downstream parsers (parse_prefilled_json, parse_json_response) work
   with tool-calling-converted responses
"""

import json
from unittest.mock import MagicMock, patch

import anthropic.types

from pipeline.lyra.config import (
    _tool_use_to_text_block,
    call_api,
    parse_prefilled_json,
)


# ---------------------------------------------------------------------------
# Helpers: build realistic Anthropic SDK response objects
# ---------------------------------------------------------------------------

def _make_text_response(text: str, stop_reason: str = "end_turn") -> anthropic.types.Message:
    """Build a Message with a single TextBlock."""
    return anthropic.types.Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="MiniMax-M2.5",
        content=[anthropic.types.TextBlock(type="text", text=text)],
        stop_reason=stop_reason,
        usage=anthropic.types.Usage(input_tokens=10, output_tokens=10),
    )


def _make_tool_use_response(tool_input: dict) -> anthropic.types.Message:
    """Build a Message with a single ToolUseBlock (what MiniMax returns for tool calls)."""
    return anthropic.types.Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="MiniMax-M2.5",
        content=[anthropic.types.ToolUseBlock(
            type="tool_use",
            id="toolu_test",
            name="structured_output",
            input=tool_input,
        )],
        stop_reason="tool_use",
        usage=anthropic.types.Usage(input_tokens=10, output_tokens=10),
    )


def _make_thinking_response(thinking_text: str, json_text: str) -> anthropic.types.Message:
    """Build a Message with ThinkingBlock + TextBlock (extended thinking path)."""
    return anthropic.types.Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="MiniMax-M2.5",
        content=[
            anthropic.types.ThinkingBlock(type="thinking", thinking=thinking_text, signature="sig"),
            anthropic.types.TextBlock(type="text", text=json_text),
        ],
        stop_reason="end_turn",
        usage=anthropic.types.Usage(input_tokens=10, output_tokens=50),
    )


# Fake settings: non-native provider (MiniMax)
FAKE_SETTINGS = MagicMock(
    anthropic_base_url="https://api.minimax.io/anthropic",
    temperature_min=0.01,
)

# Schemas matching the real pipeline ones
RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_archaeology": {"type": "boolean"},
        "is_speculative": {"type": "boolean"},
        "speculative_tags": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["is_archaeology", "reason"],
}

IDENTIFY_SITE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_site": {"type": "boolean"},
        "site_name": {"type": "string"},
        "confidence": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["is_site", "confidence", "reasoning"],
}


# ---------------------------------------------------------------------------
# Tests: _tool_use_to_text_block helper
# ---------------------------------------------------------------------------

class TestToolUseToTextBlock:
    def test_converts_tool_use_to_text(self):
        tool_input = {"is_archaeology": True, "reason": "Discusses excavation at Pompeii"}
        response = _make_tool_use_response(tool_input)
        result = _tool_use_to_text_block(response)

        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.stop_reason == "end_turn"
        assert json.loads(result.content[0].text) == tool_input

    def test_preserves_unicode(self):
        tool_input = {"site_name": "Göbekli Tepe", "reason": "Anatolian Neolithic"}
        response = _make_tool_use_response(tool_input)
        result = _tool_use_to_text_block(response)
        assert json.loads(result.content[0].text)["site_name"] == "Göbekli Tepe"

    def test_passthrough_when_no_tool_use(self):
        response = _make_text_response('{"is_archaeology": true}')
        result = _tool_use_to_text_block(response)
        assert result is response

    def test_complex_nested_schema(self):
        tool_input = {
            "key_topics": [
                {"headline": "New pyramid found", "timestamp_range": "00:05:00-00:10:00"},
                {"headline": "Dating results", "timestamp_range": "00:15:00-00:20:00"},
            ]
        }
        response = _make_tool_use_response(tool_input)
        result = _tool_use_to_text_block(response)
        parsed = json.loads(result.content[0].text)
        assert len(parsed["key_topics"]) == 2

    def test_original_response_not_mutated(self):
        response = _make_tool_use_response({"test": True})
        result = _tool_use_to_text_block(response)
        assert response.content[0].type == "tool_use"
        assert result.content[0].type == "text"


# ---------------------------------------------------------------------------
# Tests: call_api() tool calling conversion
# ---------------------------------------------------------------------------

class TestCallApiToolCalling:
    @patch("pipeline.lyra.config._is_native_anthropic", return_value=False)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_output_config_becomes_tools(self, mock_create, _s, _n):
        tool_input = {"is_archaeology": True, "reason": "excavation"}
        mock_create.return_value = _make_tool_use_response(tool_input)

        result = call_api(
            MagicMock(),
            model="MiniMax-M2.5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            output_config={"format": {"type": "json_schema", "schema": RELEVANCE_SCHEMA}},
            prefill="{",
        )

        sent = mock_create.call_args[1]
        assert sent["tools"][0]["name"] == "structured_output"
        assert sent["tools"][0]["input_schema"] == RELEVANCE_SCHEMA
        assert sent["tool_choice"] == {"type": "any"}
        assert "output_config" not in sent
        # Prefill suppressed
        assert all(m["role"] != "assistant" for m in sent["messages"])
        # Response converted
        assert result.content[0].type == "text"
        assert json.loads(result.content[0].text)["is_archaeology"] is True

    @patch("pipeline.lyra.config._is_native_anthropic", return_value=False)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_thinking_bypasses_tool_calling(self, mock_create, _s, _n):
        json_text = '{"is_site": true, "confidence": "high", "reasoning": "clear match"}'
        mock_create.return_value = _make_thinking_response("I think...", json_text)

        result = call_api(
            MagicMock(),
            model="MiniMax-M2.5",
            max_tokens=5120,
            messages=[{"role": "user", "content": "test"}],
            output_config={"format": {"type": "json_schema", "schema": IDENTIFY_SITE_SCHEMA}},
            thinking={"type": "enabled", "budget_tokens": 4096},
            prefill="{",
        )

        sent = mock_create.call_args[1]
        assert "tools" not in sent
        assert "output_config" not in sent
        assert sent["messages"][-1] == {"role": "assistant", "content": "{"}
        assert result.content[0].type == "thinking"
        assert result.content[1].type == "text"

    @patch("pipeline.lyra.config._is_native_anthropic", return_value=False)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_no_schema_unchanged(self, mock_create, _s, _n):
        mock_create.return_value = _make_text_response("Q115679382")
        call_api(
            MagicMock(),
            model="MiniMax-M2.5",
            max_tokens=32,
            messages=[{"role": "user", "content": "pick entity"}],
            prefill="Q",
        )
        sent = mock_create.call_args[1]
        assert "tools" not in sent
        assert sent["messages"][-1] == {"role": "assistant", "content": "Q"}

    @patch("pipeline.lyra.config._is_native_anthropic", return_value=False)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_max_tokens_floor_still_applied(self, mock_create, _s, _n):
        mock_create.return_value = _make_tool_use_response({"test": True})
        call_api(
            MagicMock(),
            model="MiniMax-M2.5",
            max_tokens=256,
            messages=[{"role": "user", "content": "test"}],
            output_config={"format": {"type": "json_schema", "schema": RELEVANCE_SCHEMA}},
        )
        assert mock_create.call_args[1]["max_tokens"] == 1024

    @patch("pipeline.lyra.config._is_native_anthropic", return_value=True)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_native_anthropic_keeps_output_config(self, mock_create, _s, _n):
        mock_create.return_value = _make_text_response('{"is_archaeology": true}')
        call_api(
            MagicMock(),
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            messages=[{"role": "user", "content": "test"}],
            output_config={"format": {"type": "json_schema", "schema": RELEVANCE_SCHEMA}},
            prefill="{",
        )
        sent = mock_create.call_args[1]
        assert "output_config" in sent
        assert "tools" not in sent

    @patch("pipeline.lyra.config._is_native_anthropic", return_value=False)
    @patch("pipeline.lyra.config._get_settings", return_value=FAKE_SETTINGS)
    @patch("pipeline.lyra.config._throttled_create")
    def test_empty_schema_falls_through(self, mock_create, _s, _n):
        mock_create.return_value = _make_text_response('{"test": true}')
        call_api(
            MagicMock(),
            model="MiniMax-M2.5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            output_config={"format": {"type": "json_schema"}},
            prefill="{",
        )
        assert "tools" not in mock_create.call_args[1]


# ---------------------------------------------------------------------------
# Tests: caller compatibility (parse_prefilled_json on converted responses)
# ---------------------------------------------------------------------------

class TestCallerCompatibility:
    """Verify that all downstream callers can parse tool-calling-converted responses."""

    def test_relevance_gate_pattern(self):
        """summarizer.py:116 — next(text block) → parse_prefilled_json"""
        tool_input = {"is_archaeology": True, "is_speculative": False, "reason": "Excavation at Pompeii"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        text_block = next((b.text for b in converted.content if hasattr(b, "text")), None)
        result = parse_prefilled_json(text_block)
        assert result["is_archaeology"] is True

    def test_summarize_video_pattern(self):
        """summarizer.py:248 — parse_prefilled_json → .get("key_topics")"""
        tool_input = {"key_topics": [{"headline": "New chamber", "timestamp_range": "05:00-10:00"}]}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        text_block = next((b.text for b in converted.content if hasattr(b, "text")), None)
        assert len(parse_prefilled_json(text_block).get("key_topics", [])) == 1

    def test_tweet_generator_pattern(self):
        """tweet_generator.py:99 — parse_prefilled_json → .get("posts", [])"""
        tool_input = {"posts": [{"headline": "Post 1"}, {"headline": "Post 2"}]}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        text_block = next((b.text for b in converted.content if hasattr(b, "text")), None)
        assert len(parse_prefilled_json(text_block).get("posts", [])) == 2

    def test_call_ai_wrapper_pattern(self):
        """site_identifier.py:527 — for block in content → parse_prefilled_json"""
        tool_input = {"is_site": True, "site_name": "Karahan Tepe", "confidence": "high", "reasoning": "match"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        for block in converted.content:
            if hasattr(block, "text"):
                result = parse_prefilled_json(block.text)
                break
        assert result["site_name"] == "Karahan Tepe"

    def test_escalation_for_else_pattern(self):
        """site_identifier.py:1141 — for-else with break"""
        tool_input = {"is_site": False, "confidence": "high", "reasoning": "modern city"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        result = None
        for block in converted.content:
            if hasattr(block, "text") and block.text:
                result = parse_prefilled_json(block.text)
                break
        else:
            result = None
        assert result is not None
        assert result["is_site"] is False

    def test_research_synthesis_pattern(self):
        """site_researcher.py:511 — for block → parse → match ID"""
        tool_input = {"source": "wikidata", "id": "Q115679382", "confidence": "high", "reasoning": "match"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        for block in converted.content:
            if hasattr(block, "text") and block.text:
                result = parse_prefilled_json(block.text)
                break
        assert result["id"] == "Q115679382"

    def test_disambiguate_pattern(self):
        """site_identifier.py:693 — chosen_index extraction"""
        tool_input = {"chosen_index": 2, "confidence": "high", "reasoning": "location matches"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        text_block = next((b.text for b in converted.content if hasattr(b, "text")), None)
        result = parse_prefilled_json(text_block)
        assert isinstance(result["chosen_index"], int)
        assert result["chosen_index"] == 2


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_dict(self):
        converted = _tool_use_to_text_block(_make_tool_use_response({}))
        assert json.loads(converted.content[0].text) == {}

    def test_special_chars_roundtrip(self):
        tool_input = {"reasoning": 'The site "Göbekli Tepe" has\nnew evidence.'}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        assert "Göbekli Tepe" in json.loads(converted.content[0].text)["reasoning"]

    def test_numeric_values_roundtrip(self):
        tool_input = {"chosen_index": 3, "score": 0.95, "count": 0}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        parsed = json.loads(converted.content[0].text)
        assert parsed["chosen_index"] == 3
        assert parsed["score"] == 0.95

    def test_null_values_roundtrip(self):
        tool_input = {"suggested_modification": None, "level": "verified"}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        assert json.loads(converted.content[0].text)["suggested_modification"] is None

    def test_nested_arrays_roundtrip(self):
        tool_input = {"topics": [{"facts": ["a", "b"], "sites": [{"name": "X"}]}]}
        converted = _tool_use_to_text_block(_make_tool_use_response(tool_input))
        parsed = json.loads(converted.content[0].text)
        assert parsed["topics"][0]["facts"] == ["a", "b"]
