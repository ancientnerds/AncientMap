"""Test that _verify_article sends article and facts to the LLM and extracts the result."""
from unittest.mock import patch

import pytest

from pipeline.lyra.article_generator import _verify_article
from pipeline.lyra.config import LyraSettings, NormalizedResponse, TextBlock


@pytest.fixture
def settings():
    return LyraSettings(
        anthropic_api_key="test",
        llm_backend="anthropic",
        model_article_verify="claude-sonnet-4-5-20251022",
    )


def test_verify_article_extracts_verified_body(settings):
    """_verify_article sends article + facts and extracts text between markers."""
    captured_kwargs = {}

    def fake_call_api(**kwargs):
        captured_kwargs.update(kwargs)
        verified_text = (
            "[CHANGES]\nNo changes needed.\n[/CHANGES]\n\n"
            "[START_VERIFIED]\n## Test\n\nVerified prose. [1]\n[END_VERIFIED]"
        )
        return NormalizedResponse(
            content=[TextBlock(text=verified_text)],
            stop_reason="end_turn",
        )

    article = "## Test\n\nSome prose. [1]"
    facts = {1: ["Key fact about the site."]}

    with patch("pipeline.lyra.article_generator.call_api", side_effect=fake_call_api):
        result = _verify_article(article, facts, settings)

    # Result is the text between [START_VERIFIED] and [END_VERIFIED]
    assert result == "## Test\n\nVerified prose. [1]"

    # Verify the call includes article and facts in the user message
    messages = captured_kwargs.get("messages", [])
    user_msg = messages[0]["content"]
    assert "<article_draft>" in user_msg
    assert "Some prose. [1]" in user_msg
    assert "[1] Facts:" in user_msg
    assert "Key fact about the site." in user_msg

    # Uses thinking, not temperature
    assert captured_kwargs.get("thinking") == {"type": "adaptive"}
    assert captured_kwargs.get("model") == "claude-sonnet-4-5-20251022"
    assert captured_kwargs.get("max_tokens") == 128000
