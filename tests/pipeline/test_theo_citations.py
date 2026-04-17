"""Tests for CitationRegistry and audit_citations in theo_citations."""
import re

import pytest

from pipeline.lyra.theo_citations import (
    CitationRegistry,
    audit_citations,
    detect_language_bleed,
    detect_placeholder_markers,
    finalize_references,
)

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


# ---------------------------------------------------------------------------
# detect_placeholder_markers
# ---------------------------------------------------------------------------


def test_detect_placeholder_markers_finds_hyphen_variant():
    """Literal [N - topic] placeholder (hyphen) is detected."""
    text = "Acoustic resonance is documented [N - acoustic resonance properties] widely."
    hits = detect_placeholder_markers(text)
    assert len(hits) == 1
    assert "acoustic resonance" in hits[0]


def test_detect_placeholder_markers_finds_endash_variant():
    """En-dash [N – topic] variant is also detected."""
    text = "Chemistry analyses [N – geopolymer chemistry] confirmed the hypothesis."
    assert len(detect_placeholder_markers(text)) == 1


def test_detect_placeholder_markers_real_citations_not_flagged():
    """Real [1], [42] citations must NOT match the placeholder regex."""
    text = "Rome was founded in 753 BC [1]. Later expansion followed [42]."
    assert detect_placeholder_markers(text) == []


# ---------------------------------------------------------------------------
# detect_language_bleed
# ---------------------------------------------------------------------------


def test_detect_language_bleed_chinese():
    """CJK characters embedded in English prose are flagged."""
    text = "Experimental archaeology (实验考古学) has demonstrated this method."
    hits = detect_language_bleed(text)
    assert hits == ["实验考古学"]


def test_detect_language_bleed_cyrillic():
    """Cyrillic characters embedded in English prose are flagged."""
    text = "The researcher Иванов published in 1923."
    assert detect_language_bleed(text) == ["Иванов"]


def test_detect_language_bleed_plain_english():
    """Pure English prose has no bleed."""
    assert detect_language_bleed("The pyramids are old.") == []


# ---------------------------------------------------------------------------
# audit_citations — new fields
# ---------------------------------------------------------------------------


def test_audit_citations_flags_placeholder_markers():
    """Paper with [N - topic] fails audit with placeholder_markers populated."""
    registry = CitationRegistry()
    paper = "This claim lacks a real citation [N - acoustic resonance properties] because synthesis failed."
    result = audit_citations(paper, registry)

    assert len(result["placeholder_markers"]) == 1
    assert result["passed"] is False


def test_audit_citations_flags_language_bleed():
    """Non-Latin script in prose fails audit."""
    registry = CitationRegistry()
    sid = registry.register_source("https://a.com", "Source A", "snippet")
    registry.assign_reference_number(sid)

    paper = "Experimental archaeology 实验考古学 has demonstrated this technique. [1]"
    result = audit_citations(paper, registry)

    assert len(result["language_bleed"]) == 1
    assert result["passed"] is False


def test_audit_citations_ignores_bleed_inside_references_section():
    """Non-Latin script inside the ## References section must not trigger bleed detection.

    Reference titles legitimately contain foreign-language text (Chinese/Russian
    papers, etc.) and should not fail the audit.
    """
    registry = CitationRegistry()
    sid = registry.register_source("https://a.com", "Source A", "snippet")
    registry.assign_reference_number(sid)

    paper = (
        "This English paragraph has a valid citation. [1]\n\n"
        "## References\n\n"
        "[1] 實驗考古學研究 — https://a.com"
    )
    result = audit_citations(paper, registry)

    assert result["language_bleed"] == []


def test_audit_citations_ignores_placeholder_inside_references_section():
    """[N - topic] style strings in the References section are ignored."""
    registry = CitationRegistry()
    sid = registry.register_source("https://a.com", "Source A", "snippet")
    registry.assign_reference_number(sid)

    paper = (
        "Clean English prose with citation. [1]\n\n"
        "## References\n\n"
        "[1] A title that happens to have [N - sample] brackets — https://a.com"
    )
    result = audit_citations(paper, registry)

    assert result["placeholder_markers"] == []


# ---------------------------------------------------------------------------
# finalize_references
# ---------------------------------------------------------------------------


def _make_registry_with_sources(n: int) -> tuple[CitationRegistry, list[str]]:
    registry = CitationRegistry()
    ids = [
        registry.register_source(f"https://s{i}.com", f"Source {i}", "snippet")
        for i in range(n)
    ]
    return registry, ids


def test_finalize_references_renumbers_in_first_occurrence_order():
    """[5] appearing before [3] becomes [1], [3] becomes [2]."""
    registry, ids = _make_registry_with_sources(5)
    # Working numbers are 1..5 assigned by sorted-sid order — simulate explicitly
    working = {ids[i]: i + 1 for i in range(5)}

    # Paper cites [5] first, then [3], then [5] again — others never cited
    paper = "First claim [5]. Second claim [3]. Third claim [5]."

    new_text, final_map = finalize_references(paper, working, registry)

    assert new_text == "First claim [1]. Second claim [2]. Third claim [1]."
    # ids[4] (was working [5]) -> new [1], ids[2] (was working [3]) -> new [2]
    assert final_map[ids[4]] == 1
    assert final_map[ids[2]] == 2
    # Unused sources not in final map
    assert ids[0] not in final_map
    assert ids[1] not in final_map
    assert ids[3] not in final_map


def test_finalize_references_drops_unused_sources_from_registry():
    """After finalize, registry.reference_numbers contains only cited sources."""
    registry, ids = _make_registry_with_sources(5)
    working = {ids[i]: i + 1 for i in range(5)}

    paper = "Only cite source [2] here."

    finalize_references(paper, working, registry)

    # Only ids[1] (working [2]) should be registered
    assert len(registry.reference_numbers) == 1
    assert ids[1] in registry.reference_numbers
    assert registry.reference_numbers[ids[1]] == 1


def test_finalize_references_produces_contiguous_numbers():
    """Final numbers are [1..M] with no gaps."""
    registry, ids = _make_registry_with_sources(10)
    working = {ids[i]: i + 1 for i in range(10)}

    # Cite working numbers 3, 7, 1, 9 — scattered
    paper = "Claim [3]. Claim [7]. Claim [1]. Claim [9]."

    _, final_map = finalize_references(paper, working, registry)

    final_nums = sorted(final_map.values())
    assert final_nums == [1, 2, 3, 4]


def test_finalize_references_no_collision_on_renumber():
    """Two-pass substitution: old [5] → new [2] must not then be re-mapped if old [2] → new [7]."""
    registry, ids = _make_registry_with_sources(5)
    working = {ids[i]: i + 1 for i in range(5)}

    # [5] appears first (will become [1]), then [2] (will become [2]), then [3] (will become [3])
    # The risk: naive pass-through could renumber the freshly-written [1] again.
    paper = "[5] then [2] then [3]."

    new_text, _ = finalize_references(paper, working, registry)

    assert new_text == "[1] then [2] then [3]."


def test_finalize_references_unknown_markers_left_alone():
    """[99] that's not in the working map is not touched (audit catches it later)."""
    registry, ids = _make_registry_with_sources(2)
    working = {ids[0]: 1, ids[1]: 2}

    paper = "Known [1], unknown [99], known [2]."

    new_text, _ = finalize_references(paper, working, registry)

    # Cited [1]->[1] first, [2]->[2] second. [99] left alone.
    assert "[99]" in new_text


def test_finalize_references_references_list_matches():
    """After finalize, registry.format_references_list yields exactly M entries in order."""
    registry, ids = _make_registry_with_sources(5)
    working = {ids[i]: i + 1 for i in range(5)}

    paper = "Claim [4]. Claim [1]."

    finalize_references(paper, working, registry)
    refs = registry.format_references_list()

    lines = refs.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("[1] Source 3")  # ids[3] (was working [4]) -> new [1]
    assert lines[1].startswith("[2] Source 0")  # ids[0] (was working [1]) -> new [2]


def test_finalize_references_empty_paper():
    """No [N] markers → no registrations, paper unchanged."""
    registry, ids = _make_registry_with_sources(3)
    working = {ids[i]: i + 1 for i in range(3)}

    paper = "A paper with no citations at all."

    new_text, final_map = finalize_references(paper, working, registry)

    assert new_text == paper
    assert final_map == {}
    assert registry.reference_numbers == {}
