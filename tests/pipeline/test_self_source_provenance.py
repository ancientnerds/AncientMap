"""Provenance rule — own papers are context, never evidence (spec §5).

The plan text refers to the adapter class as `AncientNerdsResearchAdapter`,
but the actual class in theo_sources.py is `PublicResearchAdapter` (source
name "ancientnerds_research") — tests target the real class.
"""

from pathlib import Path

import pytest

from pipeline.lyra.theo_sources import PublicResearchAdapter, RawSource


def test_rawsource_has_self_flag_default_false():
    s = RawSource(url="u", title="t", snippet="s")
    assert s.self_source is False


def test_own_research_adapter_is_context_tier():
    adapter = PublicResearchAdapter()
    assert adapter.default_tier == 4  # context tier — sorts behind 1..3


def test_specialist_prompt_contains_self_rule():
    prompt = Path("pipeline/lyra/prompts/theo_specialist_analysis.txt").read_text(encoding="utf-8")
    assert "[self]" in prompt


@pytest.mark.asyncio
async def test_search_marks_results_as_self_source(monkeypatch):
    """search() prefixes titles with '[self] ', sets self_source=True, and
    passes through the tier-4 default_tier (spec §5)."""
    from pipeline.lyra import theo_research_index

    def _fake_search_sections(query, limit=3):
        return [
            {
                "paper_id": "p1",
                "paper_title": "Some Prior Paper",
                "paper_slug": "some-prior-paper",
                "section_title": "Introduction",
                "section_text": "Some text about the topic.",
                "section_index": 0,
                "author_username": "theo",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(theo_research_index, "search_sections", _fake_search_sections)

    adapter = PublicResearchAdapter()
    results = await adapter.search("test query")

    assert len(results) == 1
    r = results[0]
    assert r.title.startswith("[self] Some Prior Paper")
    assert r.self_source is True
    assert r.default_tier == 4
