"""Test that call_api() correctly wraps documents into content blocks."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.config import _call_anthropic_api, LyraSettings


@pytest.fixture
def settings():
    return LyraSettings(anthropic_api_key="test-key", llm_backend="anthropic")


def test_documents_become_content_blocks(settings):
    """Documents are prepended to the last user message as content blocks."""
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(type="text", text="result")]
        mock_resp.stop_reason = "end_turn"
        mock_resp.model = "test"
        mock_resp.usage.input_tokens = 10
        mock_resp.usage.output_tokens = 5
        return mock_resp

    with patch("pipeline.lyra.config._get_client") as mock_client:
        mock_client.return_value.messages.create = fake_create
        _call_anthropic_api(
            settings,
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": "Write this section."}],
            documents=[{"title": "Source 1", "data": "Some source text."}],
        )

    msgs = captured["messages"]
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "document"
    assert content[0]["citations"] == {"enabled": True}
    assert content[0]["title"] == "Source 1"
    assert content[-1]["type"] == "text"
    assert content[-1]["text"] == "Write this section."


def test_no_documents_unchanged(settings):
    """Without documents, user message content stays as a string."""
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(type="text", text="result")]
        mock_resp.stop_reason = "end_turn"
        mock_resp.model = "test"
        mock_resp.usage.input_tokens = 10
        mock_resp.usage.output_tokens = 5
        return mock_resp

    with patch("pipeline.lyra.config._get_client") as mock_client:
        mock_client.return_value.messages.create = fake_create
        _call_anthropic_api(
            settings,
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": "Just a question."}],
        )

    msgs = captured["messages"]
    assert msgs[0]["content"] == "Just a question."
