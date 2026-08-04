"""Tests for CitationRegistry and audit_citations in theo_citations."""

import re

import pytest

from pipeline.lyra.theo_citations import (
    CitationRegistry,
    _normalize_url,
    audit_citations,
    detect_language_bleed,
    detect_placeholder_markers,
    finalize_references,
    inject_citation_for_paragraph,
    parse_references_section,
    score_tier_by_domain,
    strip_uncited_factual_paragraphs,
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
    source_id = registry.register_source("https://www.example.com/page", "Example", "snippet")
    assert registry.sources[source_id].domain == "example.com"


def test_register_source_sets_timestamp():
    """access_timestamp is set to a non-empty ISO-8601 string."""
    registry = CitationRegistry()
    source_id = registry.register_source("https://jstor.org/stable/123", "JSTOR", "...")
    ts = registry.sources[source_id].access_timestamp
    assert ts
    # Rough ISO check: YYYY-MM-DDTHH:MM:SS
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)


def test_register_source_preserves_academic_metadata():
    """When the discovering adapter has DOI/authors/venue, those flow into CitedSource."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.1002/gea.3340100203",
        title="Geologic weathering and the age of the sphinx",
        snippet="...",
        date="1995-01-01",
        doi="10.1002/gea.3340100203",
        authors=["Lal Gauri, K.", "Sinai, J.J.", "Bandyopadhyay, J.K."],
        venue="Geoarchaeology",
        citation_count=87,
    )
    source = registry.sources[sid]
    assert source.doi == "10.1002/gea.3340100203"
    assert source.authors == ["Lal Gauri, K.", "Sinai, J.J.", "Bandyopadhyay, J.K."]
    assert source.venue == "Geoarchaeology"
    assert source.citation_count == 87


def test_register_source_defaults_metadata_to_empty():
    """Callers without academic metadata get empty defaults (no crash on missing kwargs)."""
    registry = CitationRegistry()
    sid = registry.register_source("https://youtu.be/abc123", "Some video", "snippet")
    source = registry.sources[sid]
    assert source.doi == ""
    assert source.authors == []
    assert source.venue == ""
    assert source.citation_count == 0


def test_register_source_merges_metadata_on_dedup():
    """If the same URL is re-registered with richer fields, empty ones get filled in.

    Pipeline scenario: Wikipedia adapter discovers a DOI link with no metadata,
    then OpenAlex adapter discovers the same paper with full citation data. The
    second registration should enrich the first record, not be discarded.
    """
    registry = CitationRegistry()
    sid1 = registry.register_source(
        url="https://doi.org/10.1002/gea.3340100203",
        title="Sphinx weathering paper",
        snippet="...",
    )
    sid2 = registry.register_source(
        url="https://doi.org/10.1002/gea.3340100203",
        title="Sphinx weathering paper (longer)",
        snippet="...",
        doi="10.1002/gea.3340100203",
        authors=["Lal Gauri, K.", "Sinai, J.J."],
        venue="Geoarchaeology",
        citation_count=87,
    )
    assert sid1 == sid2  # same source, deduped
    source = registry.sources[sid1]
    assert source.doi == "10.1002/gea.3340100203"
    assert source.authors == ["Lal Gauri, K.", "Sinai, J.J."]
    assert source.venue == "Geoarchaeology"
    assert source.citation_count == 87


def test_register_source_preserves_first_writer_metadata():
    """First non-empty metadata wins on conflict; doesn't get overwritten by a later registration."""
    registry = CitationRegistry()
    sid1 = registry.register_source(
        url="https://doi.org/10.1234/foo",
        title="First",
        snippet="...",
        venue="Nature",
    )
    registry.register_source(
        url="https://doi.org/10.1234/foo",
        title="Second",
        snippet="...",
        venue="Science",  # different — should NOT overwrite "Nature"
    )
    assert registry.sources[sid1].venue == "Nature"


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
    ids = [registry.register_source(f"https://source{i}.com", f"Source {i}", "s") for i in range(3)]
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
        registry.register_source(f"https://s{i}.com", f"Source {i}", "snippet") for i in range(n)
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

    prose = "Rome was founded in 753 BC [1]. The senate was established soon after [2]."
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
# audit_citations — non-numeric bracketed markers (pipeline debug leaks)
# ---------------------------------------------------------------------------


def _registry_with_one_ref() -> CitationRegistry:
    registry = CitationRegistry()
    sid = registry.register_source("https://a.example/page", "A", "snippet")
    registry.assign_reference_number(sid)  # → [1]
    return registry


def test_audit_flags_hex_pipeline_token():
    """A bracketed hex token like [5620e1fb87f7] must fail the audit."""
    registry = _registry_with_one_ref()
    prose = "The source [5620e1fb87f7] suggests X [1]."
    result = audit_citations(prose, registry)
    assert "5620e1fb87f7" in result["non_numeric_markers"]
    assert result["passed"] is False
    assert any("non-numeric" in i for i in result["issues"])


def test_audit_does_not_flag_markdown_links():
    """[text](url) is a markdown link, not a citation marker — must not flag."""
    registry = _registry_with_one_ref()
    prose = "See [Wikipedia](https://en.wikipedia.org/wiki/Foo) for background [1]."
    result = audit_citations(prose, registry)
    assert result["non_numeric_markers"] == []
    assert result["passed"] is True


def test_audit_does_not_flag_footnote_refs():
    """[^n] is a markdown footnote reference — must not flag."""
    registry = _registry_with_one_ref()
    prose = "Noted [^1] elsewhere [1]."
    result = audit_citations(prose, registry)
    assert result["non_numeric_markers"] == []
    assert result["passed"] is True


def test_audit_placeholder_not_double_flagged():
    """[N - topic] is detected as a placeholder, must not also be reported
    as a non-numeric marker."""
    registry = _registry_with_one_ref()
    prose = "A claim [N - context] leaked into prose [1]."
    result = audit_citations(prose, registry)
    assert result["placeholder_markers"] == ["[N - context]"]
    assert result["non_numeric_markers"] == []
    # still fails because placeholder_markers is non-empty
    assert result["passed"] is False


def test_audit_flags_multiple_non_numeric_tokens_deduped():
    """Multiple non-numeric tokens should all be reported, order-preserving and deduped."""
    registry = _registry_with_one_ref()
    prose = "Mixed [TODO] and [abc-123] plus another [TODO] with [1]."
    result = audit_citations(prose, registry)
    # Deduped: TODO appears once even though it shows up twice in prose
    assert result["non_numeric_markers"] == ["TODO", "abc-123"]
    assert result["passed"] is False


def test_audit_clean_prose_still_passes():
    """Baseline: no non-numeric tokens → non_numeric_markers is empty and does
    not flip an otherwise-passing paper to failed."""
    registry = _registry_with_one_ref()
    prose = "Rome was founded in 753 BC [1]."
    result = audit_citations(prose, registry)
    assert result["non_numeric_markers"] == []
    assert result["passed"] is True


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


def test_register_source_self_source_forces_tier_4_and_flag():
    """self_source=True overrides the domain scorer to tier 4 and sets the flag.

    Uses a cambridge.org URL (tier 1 by domain) to prove the override wins
    over even the strongest domain signal — an adapter's self-knowledge
    beats URL heuristics (spec 2026-08-04 §5).
    """
    registry = CitationRegistry()
    sid = registry.register_source(
        "https://www.cambridge.org/core/some-self-paper",
        "[self] Some Prior Paper",
        "snippet",
        self_source=True,
    )
    source = registry.sources[sid]
    assert source.reliability_tier == 4
    assert source.self_source is True


def test_register_source_self_source_upgrades_existing_record_on_dedup():
    """Re-registering an already-known URL with self_source=True upgrades
    the existing record's tier, flag, AND title — every enforcement surface
    (prompt rule, References list, audit) reads the title string, not the
    flag, so the [self] marker must land there too."""
    registry = CitationRegistry()
    url = "https://ancientnerds.com/theo/public/some-paper"
    sid1 = registry.register_source(url, "Some Paper — Intro", "snippet")
    assert registry.sources[sid1].self_source is False
    assert registry.sources[sid1].title == "Some Paper — Intro"

    sid2 = registry.register_source(url, "[self] Some Paper — Intro", "snippet", self_source=True)
    assert sid1 == sid2
    assert registry.sources[sid1].self_source is True
    assert registry.sources[sid1].reliability_tier == 4
    assert registry.sources[sid1].title == "[self] Some Paper — Intro"
    assert registry.sources[sid1].title.count("[self]") == 1


def test_register_source_self_source_upgrade_does_not_double_prefix_title():
    """A second self_source=True re-registration is a no-op on the flag and
    must not add a second [self] prefix to an already-marked title."""
    registry = CitationRegistry()
    url = "https://ancientnerds.com/theo/public/some-paper"
    registry.register_source(url, "Some Paper — Intro", "snippet")
    registry.register_source(url, "irrelevant", "snippet", self_source=True)
    sid3 = registry.register_source(url, "irrelevant", "snippet", self_source=True)
    assert registry.sources[sid3].title.count("[self]") == 1


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
    sid_b = registry.register_source("https://en.wikipedia.org/wiki/Rome", "Rome", "snippet")
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
    assert all(
        "g.example" not in s.url
        for s in registry.sources.values()
        if s.id in registry.reference_numbers
    )


# ---------------------------------------------------------------------------
# _normalize_url — collapses version-padded and tracking-polluted URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,canonical",
    [
        # preprints.org version stripping
        (
            "https://www.preprints.org/manuscript/202108.0087/v5/download",
            "https://preprints.org/manuscript/202108.0087",
        ),
        (
            "https://www.preprints.org/manuscript/202108.0087/v9",
            "https://preprints.org/manuscript/202108.0087",
        ),
        # preprints.org /download without a version — still stripped to manuscript page
        (
            "https://preprints.org/manuscript/202108.0087/download",
            "https://preprints.org/manuscript/202108.0087",
        ),
        # arxiv version stripping
        ("https://arxiv.org/abs/2301.12345v3", "https://arxiv.org/abs/2301.12345"),
        ("https://arxiv.org/pdf/1206.0113", "https://arxiv.org/pdf/1206.0113"),
        # arxiv pdf path with version
        (
            "https://arxiv.org/pdf/2301.12345v3.pdf",
            "https://arxiv.org/pdf/2301.12345.pdf",
        ),
        # arxiv pdf path with version, no .pdf extension
        (
            "https://arxiv.org/pdf/2301.12345v3",
            "https://arxiv.org/pdf/2301.12345",
        ),
        # biorxiv version stripping
        (
            "https://www.biorxiv.org/content/10.1101/2023.01.01.000000v2.full.pdf",
            "https://biorxiv.org/content/10.1101/2023.01.01.000000.full.pdf",
        ),
        # biorxiv with 'v' characters earlier in the path (DOI or date slug)
        (
            "https://www.biorxiv.org/content/10.1101/2024.05.vat.123456v2.full.pdf",
            "https://biorxiv.org/content/10.1101/2024.05.vat.123456.full.pdf",
        ),
        # researchgate profile-to-publication collapse
        (
            "https://www.researchgate.net/profile/Jane-Doe/publication/328144532_Ancient_geopolymer",
            "https://researchgate.net/publication/328144532_Ancient_geopolymer",
        ),
        # utm/fragment stripping + lowercase host
        (
            "https://EN.Wikipedia.org/wiki/Foo?utm_source=x&utm_medium=y#section",
            "https://en.wikipedia.org/wiki/Foo",
        ),
        # www stripping and ref=
        (
            "https://www.jstor.org/stable/1234?ref=homepage",
            "https://jstor.org/stable/1234",
        ),
        # doi preserved exactly (already canonical)
        (
            "https://doi.org/10.1093/oxrevecpol/graaa035",
            "https://doi.org/10.1093/oxrevecpol/graaa035",
        ),
        # doi.org with www prefix and utm tracking — must normalize to canonical
        (
            "https://www.doi.org/10.1093/oxrevecpol/graaa035?utm_source=twitter#ref",
            "https://doi.org/10.1093/oxrevecpol/graaa035",
        ),
        # gclid (Google Ads)
        ("https://example.com/page?gclid=abc123", "https://example.com/page"),
        # fbclid (Facebook)
        ("https://example.com/page?fbclid=abc123", "https://example.com/page"),
        # mc_eid (Mailchimp)
        ("https://example.com/page?mc_eid=abc123", "https://example.com/page"),
        # _hsenc (HubSpot)
        ("https://example.com/page?_hsenc=abc123", "https://example.com/page"),
        # Mixed: real param + tracking — real param survives
        ("https://example.com/search?q=hello&utm_source=x", "https://example.com/search?q=hello"),
        # empty + malformed tolerated
        ("", ""),
        ("not a url", "not a url"),
    ],
)
def test_normalize_url(raw, canonical):
    assert _normalize_url(raw) == canonical


# ---------------------------------------------------------------------------
# register_source — URL-normalized dedup
# ---------------------------------------------------------------------------


def test_register_source_dedupes_preprint_versions():
    """Two URLs that differ only by preprint version stamp register as one source."""
    registry = CitationRegistry()
    id_v5 = registry.register_source(
        "https://www.preprints.org/manuscript/202108.0087/v5/download",
        "Polygonal Masonry",
        "snippet",
    )
    id_v9 = registry.register_source(
        "https://www.preprints.org/manuscript/202108.0087/v9",
        "Polygonal Masonry (v9)",
        "snippet",
    )
    assert id_v5 == id_v9
    assert len(registry.sources) == 1
    # First-seen URL is preserved for display
    assert registry.sources[id_v5].url.endswith("/v5/download")


def test_register_source_dedupes_tracking_params():
    """Two URLs that differ only by tracking params register as one source."""
    registry = CitationRegistry()
    id_a = registry.register_source("https://example.com/page?utm_source=twitter", "A", "s")
    id_b = registry.register_source("https://example.com/page?utm_source=reddit", "A", "s")
    assert id_a == id_b


def test_register_source_dedupes_www_prefix():
    """www.example.com and example.com register as the same source."""
    registry = CitationRegistry()
    id_a = registry.register_source("https://www.example.com/x", "A", "s")
    id_b = registry.register_source("https://example.com/x", "A", "s")
    assert id_a == id_b


def test_register_source_distinct_urls_remain_distinct():
    """Genuinely different URLs still get different source_ids."""
    registry = CitationRegistry()
    id_a = registry.register_source("https://example.com/page-a", "A", "s")
    id_b = registry.register_source("https://example.com/page-b", "B", "s")
    assert id_a != id_b
    assert len(registry.sources) == 2


# ---------------------------------------------------------------------------
# format_references_list — invariant: one source per entry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# inject_citation_for_paragraph — smart claim-injection
# ---------------------------------------------------------------------------


def _registry_with_claim(
    claim_text: str, url: str = "https://example.org/source"
) -> tuple[CitationRegistry, str]:
    registry = CitationRegistry()
    sid = registry.register_source(url, "Source", "snippet text")
    registry.add_claim(claim_text, [sid])
    return registry, sid


def test_inject_returns_none_when_registry_empty():
    """No claims → no injection possible."""
    registry = CitationRegistry()
    paragraph = "The Watchers in the Book of Enoch are described as fallen angels."
    assert inject_citation_for_paragraph(paragraph, registry) is None


def test_inject_returns_none_for_short_paragraph():
    """A two-word paragraph has nothing to match against."""
    registry, _ = _registry_with_claim(
        "The Watchers in the Book of Enoch are fallen angels who taught humans."
    )
    assert inject_citation_for_paragraph("Yes indeed.", registry) is None


def test_inject_returns_none_when_no_match():
    """Unrelated paragraph and claim → no injection."""
    registry, _ = _registry_with_claim(
        "The Watchers in the Book of Enoch are fallen angels who taught forbidden knowledge."
    )
    para = "The Roman aqueducts of Segovia were constructed during the reign of Trajan."
    assert inject_citation_for_paragraph(para, registry) is None


def test_inject_appends_marker_for_high_overlap_paragraph():
    """A paragraph that lexically overlaps a claim gets the claim's [N] appended."""
    registry, sid = _registry_with_claim(
        "The Watchers in the Book of Enoch are described as fallen angels who taught humans forbidden knowledge."
    )
    para = (
        "The Book of Enoch's Watchers narrative describes fallen angels who came down to "
        "earth and taught humans forbidden knowledge they should not have."
    )
    out = inject_citation_for_paragraph(para, registry)
    assert out is not None
    # A reference number was assigned and appended
    assert re.search(r"\[\d+\]\s*$", out)
    # The original prose is preserved (no rewrites)
    assert "Book of Enoch" in out
    assert "fallen angels" in out
    # The source got a real reference number
    assert sid in registry.reference_numbers


def test_inject_returns_paragraph_unchanged_when_already_cited():
    """If the paragraph already contains the claim's marker, leave it alone."""
    registry, sid = _registry_with_claim(
        "The Watchers in the Book of Enoch are described as fallen angels."
    )
    num = registry.assign_reference_number(sid)
    para = f"The Book of Enoch describes the Watchers as fallen angels who came down. [{num}]"
    out = inject_citation_for_paragraph(para, registry)
    # Documented contract: None when the paragraph already carries every
    # candidate marker — the caller then keeps the paragraph unchanged, so
    # no double-citation can occur (see paper.py stage-3 injection loop).
    assert out is None


def test_inject_picks_best_match_when_multiple_candidates():
    """Among several claims, the one with strongest overlap wins."""
    registry = CitationRegistry()
    sid_low = registry.register_source("https://low.example/", "Low", "s")
    sid_high = registry.register_source("https://high.example/", "High", "s")
    registry.add_claim(
        "Roman aqueducts in Segovia were built during the reign of Trajan around 100 CE.",
        [sid_low],
    )
    registry.add_claim(
        "The Watchers in the Book of Enoch are described as fallen angels who came down "
        "from heaven and taught humans forbidden astronomical knowledge.",
        [sid_high],
    )
    para = (
        "The Book of Enoch's Watchers narrative describes fallen angels who came down "
        "and taught humans forbidden astronomical knowledge from the heavens above."
    )
    out = inject_citation_for_paragraph(para, registry)
    assert out is not None
    # Only the high-overlap claim's source should have been cited
    assert sid_high in registry.reference_numbers
    assert sid_low not in registry.reference_numbers


def test_inject_skips_claims_without_source_ids():
    """Claims with empty source_ids cannot be cited and are ignored."""
    registry = CitationRegistry()
    registry.add_claim(
        "The Book of Enoch's Watchers narrative describes fallen angels who taught humans.",
        [],  # no sources
    )
    para = "The Watchers of Enoch were fallen angels who taught forbidden knowledge to humans."
    assert inject_citation_for_paragraph(para, registry) is None


def test_strip_uses_injection_to_preserve_supported_paragraph():
    """End-to-end: strip helper reaches into the registry to cite an uncited paragraph."""
    registry = CitationRegistry()
    sid = registry.register_source("https://enoch.example/", "Enoch Source", "snippet")
    registry.add_claim(
        "The Watchers in the Book of Enoch are fallen angels who taught humans forbidden knowledge from heaven.",
        [sid],
    )
    paper = (
        "## Investigation\n\n"
        "The Book of Enoch's Watchers narrative describes fallen angels who came down "
        "and taught humans forbidden knowledge from heaven, a tradition older than most "
        "biblical scholarship acknowledges in modern surveys of the apocryphal corpus.\n"
    )
    out = strip_uncited_factual_paragraphs(paper, registry)
    # Paragraph survived the strip (was not gutted)
    assert "Book of Enoch" in out
    # And got a real [N] marker
    assert re.search(r"\[\d+\]", out)
    assert sid in registry.reference_numbers


def test_strip_drops_unsupported_paragraph_when_no_claim_match():
    """Strip still removes paragraphs the registry can't support."""
    registry = CitationRegistry()
    # A claim that doesn't match the paragraph at all
    sid = registry.register_source("https://other.example/", "Unrelated", "snippet")
    registry.add_claim(
        "The Roman aqueducts of Segovia were constructed under the reign of Trajan.",
        [sid],
    )
    # Five-section paper so the section-preserve safeguard doesn't trigger.
    factual_unsupported = (
        "Sumerian cuneiform tablets from the third millennium BCE describe the "
        "Anunnaki as celestial visitors who descended from the heavens and shaped "
        "human civilization in measurable archaeological ways."
    )
    paper = (
        "## Investigation\n\n"
        + factual_unsupported
        + "\n\n"
        + "Filler factual paragraph one with citations [1] to keep the section above the preservation threshold by word count.\n\n"
        + "Filler factual paragraph two with citations [1] to keep the section above the preservation threshold by word count.\n\n"
        + "Filler factual paragraph three with citations [1] to keep the section above the preservation threshold by word count.\n"
    )
    out = strip_uncited_factual_paragraphs(paper, registry)
    # The unsupported paragraph is gone
    assert "Sumerian cuneiform tablets" not in out


def test_prune_orphaned_references_drops_unused_assignments():
    """Run 14 regression: assigned ref numbers without [N] in prose are pruned."""
    from pipeline.lyra.theo_citations import prune_orphaned_references

    registry = CitationRegistry()
    cited_sid = registry.register_source("https://cited.example/", "Cited", "snip")
    uncited_sid = registry.register_source("https://orphan.example/", "Orphan", "snip")
    third_sid = registry.register_source("https://third.example/", "Third", "snip")
    registry.assign_reference_number(cited_sid)  # → 1
    registry.assign_reference_number(uncited_sid)  # → 2 (orphan)
    registry.assign_reference_number(third_sid)  # → 3
    paper = "## Investigation\n\nFact one [1]. Fact three [3].\n\n## References\n\n[1] x\n[2] y\n[3] z\n"
    pruned = prune_orphaned_references(paper, registry)
    assert pruned == 1
    assert cited_sid in registry.reference_numbers
    assert uncited_sid not in registry.reference_numbers
    assert third_sid in registry.reference_numbers


def test_prune_orphaned_references_only_scans_prose_not_refs_section():
    """Numbers only present in the References list shouldn't count as cited."""
    from pipeline.lyra.theo_citations import prune_orphaned_references

    registry = CitationRegistry()
    sid = registry.register_source("https://x.example/", "X", "snip")
    registry.assign_reference_number(sid)
    paper = "## Investigation\n\nNo citations here at all.\n\n## References\n\n[1] X — https://x.example/\n"
    pruned = prune_orphaned_references(paper, registry)
    assert pruned == 1
    assert sid not in registry.reference_numbers


def test_strip_preserves_h1_title_block():
    """The `# Paper Title` block must survive the strip pass.

    Run 10 regression: the H1 title was treated as uncited factual prose
    (>50 chars, no [N] marker) and stripped. Downstream title-extraction then
    fell back to the raw user question, producing a 600-char H1.
    """
    registry = CitationRegistry()
    sid = registry.register_source("https://x.example/", "X", "snippet")
    registry.add_claim("Filler claim about megaliths and stone working.", [sid])
    paper = (
        "# Celestial Beings in Ancient Texts and Megalithic Monuments\n\n"
        "## Investigation\n\n"
        "Megaliths at Puma Punku show machined precision visible to the naked eye [1].\n"
    )
    out = strip_uncited_factual_paragraphs(paper, registry)
    assert "# Celestial Beings in Ancient Texts and Megalithic Monuments" in out


def test_strip_preserves_h2_h3_headings():
    """Section and subsection headings must also survive (defensive)."""
    registry = CitationRegistry()
    sid = registry.register_source("https://x.example/", "X", "snippet")
    registry.add_claim("Filler claim about the Mediterranean basin.", [sid])
    paper = (
        "## A Long Section Heading That Definitely Exceeds Fifty Characters In Total\n\n"
        "### A Long Subsection Heading That Definitely Exceeds Fifty Characters In Total\n\n"
        "Some prose with a citation [1] so the section preservation safeguard does not trigger.\n"
    )
    out = strip_uncited_factual_paragraphs(paper, registry)
    assert "## A Long Section Heading" in out
    assert "### A Long Subsection Heading" in out


def test_strip_existing_references_section_no_op_when_absent():
    from pipeline.lyra.theo_citations import strip_existing_references_section

    text = "# Title\n\n## Intro\n\nProse with no refs section [1].\n"
    out, removed = strip_existing_references_section(text)
    assert out == text
    assert removed == 0


def test_strip_existing_references_section_drops_llm_emitted_block():
    """Paper 1 regression: LLM emits its own ## References block before the
    pipeline appends the canonical one. The frontend then splits on the first
    heading and shows the LLM's URL-less fake refs."""
    from pipeline.lyra.theo_citations import strip_existing_references_section

    text = (
        "# Title\n\n## Intro\n\nProse with citation [1].\n\n"
        "## References\n\n"
        "[1] Chen, Y., et al. (2021). Piezoelectric properties of granite.\n"
        "[2] Dunn, C. (2011). *The Giza Power Plant*.\n"
    )
    out, removed = strip_existing_references_section(text)
    assert "## References" not in out
    assert "Chen, Y." not in out
    assert "Prose with citation [1]." in out
    assert removed > 0


def test_strip_existing_references_section_also_matches_sources_heading():
    from pipeline.lyra.theo_citations import strip_existing_references_section

    text = "# Title\n\nProse [1].\n\n## Sources\n\n[1] Something\n"
    out, _ = strip_existing_references_section(text)
    assert "## Sources" not in out
    assert "Prose [1]." in out


def test_strip_existing_references_section_handles_h3_heading():
    from pipeline.lyra.theo_citations import strip_existing_references_section

    text = "# T\n\nProse.\n\n### References\n\n[1] x\n"
    out, _ = strip_existing_references_section(text)
    assert "References" not in out


def test_strip_orphan_citation_markers_no_op_when_all_valid():
    from pipeline.lyra.theo_citations import strip_orphan_citation_markers

    text = "Fact one [1] and fact two [2].\n\n## References\n\n[1] x\n[2] y\n"
    out, removed = strip_orphan_citation_markers(text, valid_nums={1, 2})
    assert out == text
    assert removed == 0


def test_strip_orphan_citation_markers_drops_unknown_numbers():
    """Paper 2 regression: body cites [30]-[34] but refs only go to [29]."""
    from pipeline.lyra.theo_citations import strip_orphan_citation_markers

    text = (
        "Erosion patterns are well-documented. [30] [31] Different mechanism. [2]\n"
        "\n## References\n\n[1] X — https://x.example/\n[2] Y — https://y.example/\n"
    )
    out, removed = strip_orphan_citation_markers(text, valid_nums={1, 2})
    assert removed == 2
    assert "[30]" not in out
    assert "[31]" not in out
    assert "[2]" in out  # valid marker preserved
    # Refs section is untouched
    assert "[1] X — https://x.example/" in out


def test_strip_orphan_citation_markers_does_not_touch_refs_section():
    """Numbers in the refs section (each line starts with [N]) must survive
    even if their N isn't in valid_nums — refs are scanned separately."""
    from pipeline.lyra.theo_citations import strip_orphan_citation_markers

    text = "Prose without citations.\n\n## References\n\n[7] Old entry — https://x.example/\n"
    out, removed = strip_orphan_citation_markers(text, valid_nums=set())
    assert "[7] Old entry" in out
    assert removed == 0


def test_strip_orphan_citation_markers_cleans_punctuation_spacing():
    """After stripping, sentences shouldn't have double spaces or stray space
    before a full stop."""
    from pipeline.lyra.theo_citations import strip_orphan_citation_markers

    text = "Claim with two orphans [99] [98] then valid [1].\n"
    out, removed = strip_orphan_citation_markers(text, valid_nums={1})
    assert removed == 2
    assert "  " not in out
    assert "[99]" not in out
    assert "[98]" not in out
    assert "[1]" in out


def test_format_references_list_one_source_per_entry():
    """Every non-empty reference line starts with [N] and has at most one URL.

    Guards against the multi-URL-crammed-into-one-entry bug we saw in
    production papers (e.g. Shining Ones reference [13] had three URLs).
    """
    registry = CitationRegistry()
    sid1 = registry.register_source("https://a.example/page", "A", "s")
    sid2 = registry.register_source("https://b.example/page", "B", "s")
    sid3 = registry.register_source("https://c.example/page", "C", "s")
    registry.assign_reference_number(sid1)
    registry.assign_reference_number(sid2)
    registry.assign_reference_number(sid3)
    refs = registry.format_references_list()
    for line in refs.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Each non-empty line begins with [N]
        assert re.match(r"^\[\d+\]", stripped), f"Unexpected line start: {line!r}"
        # At most one URL per line
        url_count = line.count("http://") + line.count("https://")
        assert url_count <= 1, f"Reference line packs multiple URLs: {line!r}"


# ---------------------------------------------------------------------------
# Tier-preference filter
# ---------------------------------------------------------------------------


def test_prefer_tier_1_source_ids_drops_lower_tiers_when_academic_available():
    """Mixed-tier claim: only the academic source survives the filter."""
    from pipeline.lyra.theo_citations import prefer_tier_1_source_ids

    registry = CitationRegistry()
    academic = registry.register_source("https://doi.org/10.x/y", "Academic", "s")
    registry.sources[academic].reliability_tier = 1
    youtube = registry.register_source("https://youtu.be/abc", "YT", "s")
    registry.sources[youtube].reliability_tier = 3
    wiki = registry.register_source("https://en.wikipedia.org/wiki/X", "Wiki", "s")
    registry.sources[wiki].reliability_tier = 2

    chosen = prefer_tier_1_source_ids([youtube, academic, wiki], registry)
    assert chosen == [academic]


def test_prefer_tier_1_source_ids_keeps_all_when_no_academic():
    """Without any tier-1, all sources (in original order) are preserved."""
    from pipeline.lyra.theo_citations import prefer_tier_1_source_ids

    registry = CitationRegistry()
    youtube = registry.register_source("https://youtu.be/abc", "YT", "s")
    registry.sources[youtube].reliability_tier = 3
    wiki = registry.register_source("https://en.wikipedia.org/wiki/X", "Wiki", "s")
    registry.sources[wiki].reliability_tier = 2

    chosen = prefer_tier_1_source_ids([youtube, wiki], registry)
    assert chosen == [youtube, wiki]


def test_prefer_tier_1_source_ids_keeps_unknown_sids_in_other_bucket():
    """Unregistered SIDs pass through in the 'other' bucket — downstream code
    is responsible for resolving them. Dropping them here would break flows
    that assign reference numbers before the source is fully registered."""
    from pipeline.lyra.theo_citations import prefer_tier_1_source_ids

    registry = CitationRegistry()
    real = registry.register_source("https://real.example/", "Real", "s")
    registry.sources[real].reliability_tier = 2
    chosen = prefer_tier_1_source_ids(["does-not-exist", real], registry)
    assert "does-not-exist" in chosen
    assert real in chosen


def test_prefer_tier_1_source_ids_still_drops_other_bucket_when_tier_1_wins():
    """When a tier-1 source is present, unknown sids in the 'other' bucket
    are dropped along with tier-2/3 — academic source is load-bearing."""
    from pipeline.lyra.theo_citations import prefer_tier_1_source_ids

    registry = CitationRegistry()
    academic = registry.register_source("https://doi.org/10.x/y", "Academic", "s")
    registry.sources[academic].reliability_tier = 1
    chosen = prefer_tier_1_source_ids(["unknown-sid", academic], registry)
    assert chosen == [academic]


def test_inject_citation_for_paragraph_uses_tier_preference():
    """Paragraph injection emits only tier-1 [N] markers when the claim has both."""
    from pipeline.lyra.theo_citations import inject_citation_for_paragraph

    registry = CitationRegistry()
    academic = registry.register_source(
        "https://doi.org/10.x/y", "Sphinx weathering paper", "Limestone weathering."
    )
    registry.sources[academic].reliability_tier = 1
    youtube = registry.register_source(
        "https://youtu.be/abc", "Random video", "Some video about pyramids."
    )
    registry.sources[youtube].reliability_tier = 3

    claim_text = (
        "Limestone weathering produces vertical grooves on the Sphinx enclosure walls "
        "consistent with rainfall erosion documented across the Giza Plateau."
    )
    registry.add_claim(claim_text, [youtube, academic])

    paragraph = (
        "Vertical grooves on the Sphinx enclosure walls show limestone weathering "
        "consistent with rainfall erosion patterns documented across the Giza Plateau."
    )
    out = inject_citation_for_paragraph(
        paragraph, registry, min_overlap_ratio=0.4, min_overlap_words=4
    )
    assert out is not None
    # Tier-1 source gets a [N]; tier-3 should not.
    assert registry.reference_numbers.get(academic) is not None
    assert registry.reference_numbers.get(youtube) is None
    n_academic = registry.reference_numbers[academic]
    assert f"[{n_academic}]" in out


# ---------------------------------------------------------------------------
# Rich (academic) reference format
# ---------------------------------------------------------------------------


def test_format_references_emits_rich_format_when_full_metadata_present():
    """DOI + authors + venue + parseable year unlock the academic citation shape."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.1002/gea.3340100203",
        title="Geologic weathering and its implications on the age of the sphinx",
        snippet="...",
        date="1995-01-15",
        doi="10.1002/gea.3340100203",
        authors=["Lal Gauri, K.", "Sinai, J.J.", "Bandyopadhyay, J.K."],
        venue="Geoarchaeology",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "Lal Gauri, K., Sinai, J.J., and Bandyopadhyay, J.K." in refs
    assert "(1995)" in refs
    assert "Geoarchaeology" in refs
    assert "DOI: 10.1002/gea.3340100203" in refs
    assert "[Academic]" in refs
    # Rich format does NOT include the raw URL; the DOI is the canonical anchor.
    assert "https://doi.org/10.1002/gea.3340100203" not in refs


def test_format_references_falls_back_to_legacy_when_doi_missing():
    """YouTube / Wikipedia / blog sources keep the existing [N] Title — URL shape."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://youtu.be/abc123",
        title="Some video",
        snippet="snippet",
    )
    registry.sources[sid].reliability_tier = 3
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "[1] Some video — https://youtu.be/abc123" in refs
    assert "DOI:" not in refs


def test_format_references_falls_back_when_authors_missing():
    """A DOI alone (no authors / no venue) is not enough — drop to legacy."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.x/y",
        title="Paper",
        snippet="s",
        doi="10.x/y",
        venue="Some Journal",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "[1] Paper — https://doi.org/10.x/y" in refs
    assert "DOI:" not in refs


def test_format_references_falls_back_when_year_unparseable():
    """No year in `date` → not enough for academic shape; legacy emitted instead."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.x/y",
        title="Untimed Paper",
        snippet="s",
        date="",
        doi="10.x/y",
        authors=["Smith, J."],
        venue="Journal",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "Untimed Paper — https://doi.org/10.x/y" in refs
    assert "DOI:" not in refs


def test_format_references_single_author_no_and():
    """Single-author block doesn't synthesize an 'and'."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.x/y",
        title="Solo work",
        snippet="s",
        date="2020",
        doi="10.x/y",
        authors=["Solo, A."],
        venue="Journal X",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "[1] Solo, A. (2020). Solo work. Journal X. DOI: 10.x/y" in refs


def test_format_references_two_authors_uses_and_without_comma():
    """Two-author block uses 'A and B', not 'A, and B'."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.x/y",
        title="Duet",
        snippet="s",
        date="2021",
        doi="10.x/y",
        authors=["A, B.", "C, D."],
        venue="JJ",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs = registry.format_references_list()
    assert "A, B. and C, D. (2021)" in refs


def test_parse_references_section_handles_rich_format():
    """parse_references_section reads back the rich academic shape."""
    refs = (
        "[1] Lal Gauri, K., Sinai, J.J., and Bandyopadhyay, J.K. (1995). "
        "Geologic weathering and its implications on the age of the sphinx. "
        "Geoarchaeology. DOI: 10.1002/gea.3340100203 (accessed 2026-05-13) [Academic]"
    )
    parsed = parse_references_section(refs)
    assert len(parsed) == 1
    entry = parsed[0]
    assert entry["num"] == 1
    assert entry["title"] == "Geologic weathering and its implications on the age of the sphinx"
    assert entry["venue"] == "Geoarchaeology"
    assert entry["year"] == 1995
    assert entry["doi"] == "10.1002/gea.3340100203"
    assert entry["authors"] == "Lal Gauri, K., Sinai, J.J., and Bandyopadhyay, J.K."
    assert entry["accessed"] == "2026-05-13"
    assert entry["tier_label"] == "Academic"
    # URL synthesized from DOI so downstream link rendering still works.
    assert entry["url"] == "https://doi.org/10.1002/gea.3340100203"


def test_parse_references_section_mixed_formats():
    """Rich and legacy lines coexist in the same References block."""
    refs = (
        "[1] Smith, J. (2020). A paper. Journal. DOI: 10.x/y (accessed 2026-01-01) [Academic]\n"
        "[2] Blog post — https://blog.example.com/post"
    )
    parsed = parse_references_section(refs)
    assert len(parsed) == 2
    assert parsed[0]["doi"] == "10.x/y"
    assert parsed[0]["authors"] == "Smith, J."
    assert parsed[1]["doi"] is None
    assert parsed[1]["url"] == "https://blog.example.com/post"


def test_parse_references_round_trip_rich():
    """format_references_list → parse_references_section preserves the structure."""
    registry = CitationRegistry()
    sid = registry.register_source(
        url="https://doi.org/10.1234/abc",
        title="Roundtrip paper",
        snippet="...",
        date="2024-06-01",
        doi="10.1234/abc",
        authors=["First, A.", "Second, B."],
        venue="Nature",
    )
    registry.sources[sid].reliability_tier = 1
    registry.assign_reference_number(sid)
    refs_text = registry.format_references_list()
    parsed = parse_references_section(refs_text)
    assert len(parsed) == 1
    assert parsed[0]["doi"] == "10.1234/abc"
    assert parsed[0]["venue"] == "Nature"
    assert parsed[0]["year"] == 2024
