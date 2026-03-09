"""Tests for the OpenAI-based call_api() in config.py.

Verifies that:
1. call_api() translates kwargs to OpenAI format
2. response_format pass-through works
3. prefill="{" → json_object response_format
4. Mercury backend uses model/max_tokens from kwargs
5. Ollama backend caps max_tokens and overrides model
6. reasoning_effort is passed through (explicit and from thinking)
7. parse_prefilled_json and parse_json_response work correctly
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
    response.model = "mercury-2"
    response.usage = usage
    return response


def _make_mercury_settings():
    """Build fake settings for Mercury backend."""
    settings = MagicMock()
    settings.llm_backend = "mercury"
    settings.api_key = "test-key"
    settings.base_url = "https://api.inceptionlabs.ai/v1"
    settings.temperature_min = 0.0
    settings.max_tokens = 32000
    return settings


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
# Tests: call_api() with Mercury backend
# ---------------------------------------------------------------------------


class TestCallApiMercury:
    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_basic_call(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response('{"test": true}')
        mock_client.return_value = client

        result = call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
        )

        assert isinstance(result, NormalizedResponse)
        assert result.content[0].text == '{"test": true}'

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_response_format_passthrough(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response(
            '{"is_archaeology": true}'
        )
        mock_client.return_value = client

        schema = {"type": "object", "properties": {"is_archaeology": {"type": "boolean"}}}
        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "RelevanceCheck", "strict": True, "schema": schema},
            },
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["response_format"]["type"] == "json_schema"
        assert sent["response_format"]["json_schema"]["schema"] == schema
        assert sent["response_format"]["json_schema"]["name"] == "RelevanceCheck"

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_prefill_json_uses_json_object(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response('{"key": "value"}')
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            prefill="{",
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["response_format"] == {"type": "json_object"}

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_system_string_passthrough(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            system="You are helpful.",
            messages=[{"role": "user", "content": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["messages"][0]["role"] == "system"
        assert sent["messages"][0]["content"] == "You are helpful."

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_system_blocks_merged(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            system=[
                {"type": "text", "text": "You are helpful."},
                {"type": "text", "text": "Be concise."},
            ],
            messages=[{"role": "user", "content": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["messages"][0]["role"] == "system"
        assert "You are helpful." in sent["messages"][0]["content"]
        assert "Be concise." in sent["messages"][0]["content"]

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_thinking_translates_to_reasoning_effort_high(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            thinking={"type": "enabled", "budget_tokens": 4096},
        )

        sent = client.chat.completions.create.call_args[1]
        assert "thinking" not in sent
        assert sent["reasoning_effort"] == "high"

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_explicit_reasoning_effort_passthrough(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            reasoning_effort="low",
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["reasoning_effort"] == "low"

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_explicit_reasoning_effort_overrides_thinking(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            thinking={"type": "enabled", "budget_tokens": 4096},
            reasoning_effort="medium",
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["reasoning_effort"] == "medium"

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_unsupported_params_stripped(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
            tool_choice={"type": "any"},
            tools=[{"name": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert "tool_choice" not in sent
        assert "tools" not in sent

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_temperature_clamped_to_min(self, mock_settings, mock_client):
        settings = _make_mercury_settings()
        settings.temperature_min = 0.1
        mock_settings.return_value = settings
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert sent["temperature"] == 0.1

    @patch("pipeline.lyra.config._get_mercury_client")
    @patch("pipeline.lyra.config._get_settings")
    def test_no_reasoning_effort_when_not_specified(self, mock_settings, mock_client):
        mock_settings.return_value = _make_mercury_settings()
        client = MagicMock()
        client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_client.return_value = client

        call_api(
            model="mercury-2",
            max_tokens=1024,
            messages=[{"role": "user", "content": "test"}],
        )

        sent = client.chat.completions.create.call_args[1]
        assert "reasoning_effort" not in sent


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
