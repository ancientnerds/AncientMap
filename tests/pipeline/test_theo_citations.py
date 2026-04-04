"""Tests for CitationRegistry and audit_citations in theo_citations."""
import re

import pytest

from pipeline.lyra.theo_citations import CitationRegistry, audit_citations

# ---------------------------------------------------------------------------
# register_source
# ---------------------------------------------------------------------------


def test_register_source_deduplicates():
    """Registering the same URL twice returns the same id and stores one entry."""
    registry = CitationRegistry()
    url = "https://www.example.com/page"
    id1 = registry.register_source(url, "Example Page", "Some snippet")
    id2 = registry.register_source(url, "Example Page (duplicate)", "Other snippet")

    assert id1 == id2
    assert len(registry.sources) == 1


def test_register_source_extracts_domain():
    """Domain is extracted from URL, stripping leading 'www.'."""
    registry = CitationRegistry()
    source_id = registry.register_source(
        "https://www.example.com/page", "Example", "snippet"
    )
    assert registry.sources[source_id].domain == "example.com"


def test_register_source_sets_timestamp():
    """access_timestamp is set to a non-empty ISO-8601 string."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://jstor.org/stable/123", "JSTOR", "...")
    ts = registry.sources[source_id].access_timestamp
    assert ts
    # Rough ISO check: YYYY-MM-DDTHH:MM:SS
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)


# ---------------------------------------------------------------------------
# assign_reference_number
# ---------------------------------------------------------------------------


def test_assign_reference_number_idempotent():
    """Assigning a reference number to the same source twice returns the same number."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://a.com", "A", "snippet")
    num1 = registry.assign_reference_number(source_id)
    num2 = registry.assign_reference_number(source_id)
    assert num1 == num2


def test_assign_reference_number_sequential():
    """Three distinct sources get sequential reference numbers [1], [2], [3]."""
    registry = CitationRegistry()
    ids = [
        registry.register_source(f"https://source{i}.com", f"Source {i}", "s")
        for i in range(3)
    ]
    nums = [registry.assign_reference_number(sid) for sid in ids]
    assert nums == [1, 2, 3]


# ---------------------------------------------------------------------------
# add_claim
# ---------------------------------------------------------------------------


def test_add_claim():
    """add_claim appends the claim to registry.claims."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://a.com", "A", "snippet")
    registry.add_claim("Rome was founded in 753 BC", [source_id], specialist_id="historian")
    assert len(registry.claims) == 1
    assert registry.claims[0].claim_text == "Rome was founded in 753 BC"
    assert registry.claims[0].source_ids == [source_id]
    assert registry.claims[0].specialist_id == "historian"


# ---------------------------------------------------------------------------
# format_references_list
# ---------------------------------------------------------------------------


def test_format_references_list_empty():
    """An empty registry returns an empty string."""
    registry = CitationRegistry()
    assert registry.format_references_list() == ""


def test_format_references_list_tiers():
    """Tier 1 gets [Academic], tier 2 gets [Reputable], tier 3 gets no label."""
    registry = CitationRegistry()

    # Register three sources with different tiers
    id1 = registry.register_source("https://academic.edu/paper", "Academic Paper", "...")
    id2 = registry.register_source("https://reputable.org/article", "Reputable Article", "...")
    id3 = registry.register_source("https://general.com/post", "General Post", "...")

    registry.sources[id1].reliability_tier = 1
    registry.sources[id2].reliability_tier = 2
    registry.sources[id3].reliability_tier = 3

    registry.assign_reference_number(id1)
    registry.assign_reference_number(id2)
    registry.assign_reference_number(id3)

    refs = registry.format_references_list()

    assert "[Academic]" in refs
    assert "[Reputable]" in refs
    # Tier 3 line should not contain a label in brackets
    lines = refs.splitlines()
    tier3_line = next(ln for ln in lines if "General Post" in ln)
    assert "[Academic]" not in tier3_line
    assert "[Reputable]" not in tier3_line


# ---------------------------------------------------------------------------
# audit_citations
# ---------------------------------------------------------------------------


def test_audit_citations_passes():
    """Paper with valid [1] marker and matching reference -> passed=True."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://a.com", "Source A", "snippet")
    registry.assign_reference_number(source_id)

    paper = "This is a well-supported factual claim about ancient Rome founded in 753 BC. [1]"
    result = audit_citations(paper, registry)

    assert result["passed"] is True
    assert result["invalid_markers"] == []
    assert result["uncited_paragraphs"] == 0


def test_audit_citations_invalid_marker():
    """Paper with [99] but no reference 99 -> invalid_markers=[99]."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://a.com", "Source A", "snippet")
    registry.assign_reference_number(source_id)  # assigns [1]

    paper = "This sentence cites a non-existent reference. [99]"
    result = audit_citations(paper, registry)

    assert 99 in result["invalid_markers"]
    assert result["passed"] is False


def test_audit_citations_uncited_paragraph():
    """A paragraph longer than 50 chars without any [N] -> uncited_paragraphs=1."""
    registry = CitationRegistry()

    paper = "This is a long paragraph without any citation markers at all and it is definitely over fifty characters."
    result = audit_citations(paper, registry)

    assert result["uncited_paragraphs"] == 1
    assert result["passed"] is False


def test_audit_citations_ignores_headings():
    """Paragraphs starting with '# ' are not counted as uncited."""
    registry = CitationRegistry()

    # A heading followed by a separator - the heading starts with #
    paper = "# This is a heading that is definitely longer than fifty characters total\n\nShort."
    result = audit_citations(paper, registry)

    # The heading paragraph should not be flagged as uncited
    assert result["uncited_paragraphs"] == 0
