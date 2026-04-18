"""Tests for CitationRegistry and audit_citations in theo_citations."""
import re

import pytest

from pipeline.lyra.theo_citations import (
    CitationRegistry,
    audit_citations,
    detect_language_bleed,
    detect_placeholder_markers,
    finalize_references,
    parse_references_section,
    score_tier_by_domain,
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


# ---------------------------------------------------------------------------
# audit_citations — prose-only idempotence
# ---------------------------------------------------------------------------


def test_audit_is_idempotent_to_references_section():
    """Appending ## References must not change invalid/orphaned/uncited results.

    This was the judge vs paper-assembly audit disagreement: the re-run at
    judge time saw the refs-list prefixes as inline citations. After the
    prose-only scan rewrite, both audits produce identical output.
    """
    registry = CitationRegistry()
    sid_a = registry.register_source("https://a.example/page", "A", "snippet")
    sid_b = registry.register_source("https://b.example/page", "B", "snippet")
    registry.assign_reference_number(sid_a)  # → [1]
    registry.assign_reference_number(sid_b)  # → [2]

    prose = (
        "Rome was founded in 753 BC [1]. The senate was established soon after [2]."
    )
    with_refs = (
        prose
        + "\n\n## References\n\n"
        + "[1] A — https://a.example/page (accessed 2026-04-18)\n"
        + "[2] B — https://b.example/page (accessed 2026-04-18)"
    )

    a1 = audit_citations(prose, registry)
    a2 = audit_citations(with_refs, registry)

    for key in (
        "passed",
        "total_citations",
        "total_references",
        "orphaned_refs",
        "invalid_markers",
        "uncited_paragraphs",
    ):
        assert a1[key] == a2[key], f"audit field {key!r} differs with/without refs section"


# ---------------------------------------------------------------------------
# score_tier_by_domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        # Tier 1 — academic / institutional
        ("https://www.cambridge.org/core/journal-of-archaeology", 1),
        ("https://doi.org/10.1093/oxrevecpol/graaa035", 1),
        ("https://arxiv.org/abs/2301.12345", 1),
        ("https://www.jstor.org/stable/1234", 1),
        ("https://sub.domain.edu/paper.pdf", 1),
        ("https://www.nature.com/articles/xyz", 1),
        ("https://dept.ox.ac.uk/research", 1),
        # Tier 2 — reputable general-audience + reference
        ("https://en.wikipedia.org/wiki/Rome", 2),
        ("https://www.britannica.com/topic/Anunnaki", 2),
        ("https://www.nationalgeographic.com/history/article/xyz", 2),
        ("https://www.bbc.com/news/world-europe-12345", 2),
        ("https://www.penn.museum/collections/123", 2),
        # Tier 3 — everything else
        ("https://some-blog.example.com/post", 3),
        ("https://randomsite.info/article", 3),
        ("", 3),
    ],
)
def test_score_tier_by_domain(url, expected):
    assert score_tier_by_domain(url) == expected


def test_register_source_defaults_tier_from_domain():
    """Registering a cambridge.org URL sets tier=1 without explicit assignment."""
    registry = CitationRegistry()
    sid = registry.register_source(
        "https://www.cambridge.org/journals/archaeology",
        "Cambridge Archaeology",
        "snippet",
    )
    assert registry.sources[sid].reliability_tier == 1


def test_register_source_defaults_tier_for_general_domain():
    """Unknown domain defaults to tier 3 instead of 0 (unscored)."""
    registry = CitationRegistry()
    sid = registry.register_source("https://random.example.net/post", "Random", "snippet")
    assert registry.sources[sid].reliability_tier == 3


def test_register_source_explicit_tier_overrides_domain():
    """Adapters/audit can still override the domain-based default."""
    registry = CitationRegistry()
    sid = registry.register_source("https://random.example.net/post", "Random", "snippet")
    # Simulate angle_audit promoting this source to tier 2 later in the pipeline.
    registry.sources[sid].reliability_tier = 2
    assert registry.sources[sid].reliability_tier == 2


# ---------------------------------------------------------------------------
# parse_references_section
# ---------------------------------------------------------------------------


def test_parse_references_section_basic():
    """Standard [N] Title — URL (accessed YYYY-MM-DD) [Tier] lines parse cleanly."""
    refs = (
        "[1] Historical Vedic religion — https://en.wikipedia.org/wiki/Vedic_religion "
        "(accessed 2026-04-18) [Reputable]\n"
        "[2] A review of ZnO — https://doi.org/10.1063/1.1992666 "
        "(accessed 2026-04-18) [Academic]\n"
        "[3] Some Blog Post — https://blog.example.com/post"
    )
    parsed = parse_references_section(refs)
    assert len(parsed) == 3
    assert parsed[0]["num"] == 1
    assert parsed[0]["title"] == "Historical Vedic religion"
    assert parsed[0]["url"] == "https://en.wikipedia.org/wiki/Vedic_religion"
    assert parsed[0]["accessed"] == "2026-04-18"
    assert parsed[0]["tier_label"] == "Reputable"
    assert parsed[1]["tier_label"] == "Academic"
    assert parsed[2]["accessed"] is None
    assert parsed[2]["tier_label"] is None


def test_parse_references_section_round_trip():
    """Parsed entries can be re-emitted matching format_references_list output."""
    registry = CitationRegistry()
    sid_a = registry.register_source(
        "https://www.cambridge.org/paper", "Cambridge Paper", "snippet"
    )
    sid_b = registry.register_source(
        "https://en.wikipedia.org/wiki/Rome", "Rome", "snippet"
    )
    registry.assign_reference_number(sid_a)
    registry.assign_reference_number(sid_b)

    refs_text = registry.format_references_list()
    parsed = parse_references_section(refs_text)

    assert len(parsed) == 2
    # The domain-based tier defaults: cambridge.org → Academic, wikipedia → Reputable
    assert parsed[0]["tier_label"] == "Academic"
    assert parsed[1]["tier_label"] == "Reputable"


def test_parse_references_section_skips_unparseable_lines():
    """Garbage lines between entries are silently skipped."""
    refs = (
        "[1] A valid entry — https://a.example/x\n"
        "\n"
        "garbage line without a number\n"
        "[2] Another valid entry — https://b.example/y"
    )
    parsed = parse_references_section(refs)
    assert [p["num"] for p in parsed] == [1, 2]


# ---------------------------------------------------------------------------
# End-to-end: edit-flow gap fill (simulates the PATCH handler's renumber)
# ---------------------------------------------------------------------------


def test_patch_flow_fills_gap_in_citation_numbering():
    """Simulate MrSchneebly's [7]-missing scenario: after renumber, contiguous."""
    # The editor removes the sentence that contained [7]. Body now cites 1..6, 8..10.
    body = (
        "Intro with cite [1]. More prose [2] and [3]. Body [4]. "
        "Section [5] with another [6]. No more 7. Later claim [8]. "
        "Next [9]. Closing [10]."
    )

    # Simulate the PATCH flow: parse refs → register → finalize_references
    refs = (
        "[1] A — https://a.example\n"
        "[2] B — https://b.example\n"
        "[3] C — https://c.example\n"
        "[4] D — https://d.example\n"
        "[5] E — https://e.example\n"
        "[6] F — https://f.example\n"
        "[7] G — https://g.example\n"  # user-deleted inline, still in refs
        "[8] H — https://h.example\n"
        "[9] I — https://i.example\n"
        "[10] J — https://j.example"
    )
    parsed = parse_references_section(refs)

    registry = CitationRegistry()
    working = {}
    for entry in parsed:
        sid = registry.register_source(entry["url"], entry["title"], "")
        working[sid] = entry["num"]

    new_body, final_map = finalize_references(body, working, registry)
    # After renumber: 1..9 contiguous, [7] dropped from registry
    nums = sorted({int(m) for m in re.findall(r"\[(\d+)\]", new_body)})
    assert nums == list(range(1, 10)), f"expected [1..9], got {nums}"
    # Registry has only the 9 survivors (G dropped)
    assert len(registry.reference_numbers) == 9
    assert all("g.example" not in s.url for s in registry.sources.values() if s.id in registry.reference_numbers)
