"""Tests for call_api() in config.py.

Verifies that:
1. Ollama backend caps max_tokens and overrides model
2. reasoning_effort is ignored (no-op)
3. parse_prefilled_json and parse_json_response work correctly
"""

from unittest.mock import MagicMock, patch

from pipeline.lyra.config import (
    NormalizedResponse,
    TextBlock,
    call_api,
    parse_json_response,
    parse_prefilled_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(text: str, finish_reason: str = "stop") -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = text

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 20

    response = MagicMock()
    response.choices = [choice]
    response.model = "test-model"
    response.usage = usage
    return response


def _make_ollama_settings():
    """Build fake settings for Ollama backend."""
    settings = MagicMock()
    settings.llm_backend = "ollama"
    settings.ollama_api_key = "unused"
    settings.ollama_base_url = "http://localhost:11434/v1"
    settings.ollama_model = "qwen3:8b"
    settings.temperature_min = 0.0
    settings.max_tokens = 32000
    return settings


# ---------------------------------------------------------------------------
# Tests: call_api() with Ollama backend
# ---------------------------------------------------------------------------


class TestCallApiOllama:
    @patch("pipeline.lyra.config._get_ollama_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_ollama_caps_max_tokens(self, mock_settings, mock_client):
        mock_settings.return_value = _make_ollama_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",  # Should be overridden
            max_tokens=32000,
            messages=[{"role": "user", "content": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["max_tokens"] == 4096  # Capped
        assert sent["model"] == "qwen3:8b"  # Overridden

    @patch("pipeline.lyra.config._get_ollama_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_ollama_skips_reasoning_effort(self, mock_settings, mock_client):
        mock_settings.return_value = _make_ollama_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            reasoning_effort="high",
        )

        sent = client.chat.completions.create.call_args[1]
        assert "reasoning_effort" not in sent


# ---------------------------------------------------------------------------
# Tests: parse helpers
# ---------------------------------------------------------------------------


class TestParseHelpers:
    def test_parse_json_response_plain(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_response_fenced(self):
        result = parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_complete(self):
        result = parse_prefilled_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_missing_brace(self):
        result = parse_prefilled_json('"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_with_whitespace(self):
        result = parse_prefilled_json('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}
