"""Test that _verify_article passes article and facts as document blocks."""
from unittest.mock import patch

import pytest

from pipeline.lyra.article_generator import _verify_article
from pipeline.lyra.config import LyraSettings, NormalizedResponse, TextBlock


@pytest.fixture
def settings():
    return LyraSettings(
        anthropic_api_key="test",
        model_verify="claude-sonnet-4-5-20251022",
    )


def test_verify_article_passes_two_documents(settings):
    """_verify_article sends article and source facts as separate document blocks."""
    captured_docs = []
    captured_kwargs = {}

    def fake_call_api(**kwargs):
        captured_docs.extend(kwargs.get("documents") or [])
        captured_kwargs.update(kwargs)
        verified_text = "[CHANGES]\nNo changes needed.\n[/CHANGES]\n\n[START_VERIFIED]\n## Test\n\nVerified prose. [1]\n[END_VERIFIED]"
        return NormalizedResponse(
            content=[TextBlock(text=verified_text)],
            stop_reason="end_turn",
        )

    article = "## Test\n\nSome prose. [1]"
    facts = {1: ["Key fact about the site."]}

    with patch("pipeline.lyra.article_generator.call_api", side_effect=fake_call_api):
        result = _verify_article(article, facts, settings)

    assert result == "## Test\n\nVerified prose. [1]"
    assert len(captured_docs) == 2
    titles = {d["title"] for d in captured_docs}
    assert "Article Draft" in titles
    assert "Source Facts by Citation" in titles
    assert captured_kwargs.get("prefill") == "[CHANGES]\n"
    assert captured_kwargs.get("temperature") == 0.0
