"""Provenance rule — own papers are context, never evidence (spec §5).

The plan text refers to the adapter class as `AncientNerdsResearchAdapter`,
but the actual class in theo_sources.py is `PublicResearchAdapter` (source
name "ancientnerds_research") — tests target the real class.
"""

from pathlib import Path

import pytest

from pipeline.lyra.theo_citations import CitationRegistry
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
    # Distinctive phrase — guards against the rule regressing to a vague
    # restatement that loses the "never count toward corroboration" teeth.
    assert "never count them toward corroboration" in prompt


@pytest.mark.asyncio
async def test_search_marks_results_as_self_source(monkeypatch):
    """search() prefixes titles with '[self] ' exactly once, sets
    self_source=True, and passes through the tier-4 default_tier (spec §5)."""
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
    assert r.title.count("[self]") == 1  # prefix applied exactly once
    assert r.self_source is True
    assert r.default_tier == 4


def test_registry_round_trip_self_source_tier_and_reference_marker():
    """End-to-end: a RawSource discovered with self_source=True lands in the
    CitationRegistry at tier 4 with the flag set, and the rendered References
    list still carries the [self] marker (it's part of the title text) —
    resolves the review finding that the tier demotion was inert because
    register_source always applied score_tier_by_domain and never saw the
    adapter's self-knowledge."""
    raw = RawSource(
        url="https://ancientnerds.com/theo/public/some-prior-paper",
        title="[self] Some Prior Paper — Introduction (AncientNerds Research)",
        snippet="Some text about the topic.",
        source_api="ancientnerds_research",
        default_tier=4,
        self_source=True,
    )

    registry = CitationRegistry()
    sid = registry.register_source(
        url=raw.url,
        title=raw.title,
        snippet=raw.snippet,
        self_source=raw.self_source,
    )

    source = registry.sources[sid]
    assert source.reliability_tier == 4
    assert source.self_source is True

    registry.assign_reference_number(sid)
    refs_md = registry.format_references_list()
    assert "[self] Some Prior Paper" in refs_md
