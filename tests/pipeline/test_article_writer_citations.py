"""Test that _write_article_body assembles sections and calls the LLM correctly."""
from unittest.mock import patch

import pytest

from pipeline.lyra.article_generator import _write_article_body
from pipeline.lyra.config import LyraSettings, NormalizedResponse, TextBlock


@pytest.fixture
def settings():
    return LyraSettings(
        anthropic_api_key="test",
        llm_backend="anthropic",
        model_article="claude-sonnet-4-5-20251022",
    )


def test_write_article_body_sends_sections(settings):
    """_write_article_body passes section payloads in the user message."""
    captured_kwargs = {}

    def fake_call_api(**kwargs):
        captured_kwargs.update(kwargs)
        return NormalizedResponse(
            content=[TextBlock(text="## Discoveries\n\nArticle prose here. [1]")],
            stop_reason="end_turn",
        )

    sections = [
        {
            "label": "Discoveries",
            "items": [
                {
                    "headline": "Ancient temple found",
                    "citation": 1,
                    "channel_name": "Ancient Architects",
                    "significance": 8,
                    "summary": "Researchers discovered a temple in Peru",
                    "facts": ["Temple dates to 500 BCE", "Located in southern Peru"],
                }
            ],
        }
    ]

    with patch("pipeline.lyra.article_generator.call_api", side_effect=fake_call_api):
        result = _write_article_body(sections, speculative=[], settings=settings)

    assert "Article prose here. [1]" in result

    # Check the user message contains section material
    messages = captured_kwargs.get("messages", [])
    user_msg = messages[0]["content"]
    assert "<source_material>" in user_msg
    assert "Ancient temple found" in user_msg
    assert "Temple dates to 500 BCE" in user_msg

    # Uses thinking and the article model
    assert captured_kwargs.get("thinking") == {"type": "adaptive"}
    assert captured_kwargs.get("model") == "claude-sonnet-4-5-20251022"
    assert captured_kwargs.get("max_tokens") == 128000
