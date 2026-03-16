"""Test that _write_section passes source data as a document block."""
from unittest.mock import patch

import pytest

from pipeline.lyra.article_generator import _write_section
from pipeline.lyra.config import LyraSettings, NormalizedResponse, TextBlock


@pytest.fixture
def settings():
    return LyraSettings(
        anthropic_api_key="test",
        model_article="claude-sonnet-4-5-20251022",
    )


def test_write_section_passes_documents(settings):
    """_write_section sends section payload as a document block."""
    captured_docs = []

    def fake_call_api(**kwargs):
        captured_docs.extend(kwargs.get("documents") or [])
        return NormalizedResponse(
            content=[TextBlock(text="## Test Section\n\nSome prose.")],
            stop_reason="end_turn",
        )

    with patch("pipeline.lyra.article_generator.call_api", side_effect=fake_call_api):
        result = _write_section(
            payload="[1] Headline\nSome facts.",
            is_speculative=False,
            settings=settings,
            section_label="## Test Section",
        )

    assert result == "## Test Section\n\nSome prose."
    assert len(captured_docs) == 1
    assert captured_docs[0]["data"] == "[1] Headline\nSome facts."
    assert captured_docs[0]["title"] == "## Test Section"
