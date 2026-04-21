"""Unit tests for pipeline.lyra.research_checklist — programmatic quality gate.

All tests are pure: no LLM, no DB, no network.
"""

from pipeline.lyra.research_checklist import (
    _check_citation_integrity,
    _check_minimum_content,
    _check_no_phantom_sources,
    _check_no_uncited_sections,
    _check_section_structure,
    run_research_checklist,
)
from pipeline.lyra.theo_citations import CitationRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_registry(num_sources: int = 3) -> CitationRegistry:
    """Create a registry with N sources, each assigned a reference number."""
    reg = CitationRegistry()
    for i in range(num_sources):
        sid = reg.register_source(
            url=f"https://example.com/source-{i}",
            title=f"Source {i}",
            snippet=f"This is a snippet for source {i}.",
        )
        reg.assign_reference_number(sid)
    return reg


def _make_paper(
    body_sections: list[str] | None = None,
    citations_per_section: list[list[int]] | None = None,
    include_abstract: bool = True,
    include_refs: bool = True,
    body_length: int = 0,
) -> str:
    """Build a minimal research paper markdown string."""
    parts: list[str] = ["# Test Research Paper\n"]

    if include_abstract:
        parts.append("## Abstract\n\nThis paper investigates test topics.\n")

    if body_sections is None:
        body_sections = ["Analysis", "Discussion"]
    if citations_per_section is None:
        citations_per_section = [[1, 2], [2, 3]]

    for i, section in enumerate(body_sections):
        cites = citations_per_section[i] if i < len(citations_per_section) else []
        cite_str = " ".join(f"[{n}]" for n in cites)
        # Ensure body paragraphs are substantial (>100 chars)
        content = (
            f"This section contains detailed analysis of the archaeological evidence "
            f"found at multiple excavation sites across the region. {cite_str}"
        )
        parts.append(f"## {section}\n\n{content}\n")

    if include_refs:
        parts.append("## References\n\n[1] Source 1 — https://example.com/1\n[2] Source 2 — https://example.com/2\n[3] Source 3 — https://example.com/3\n")

    paper = "\n".join(parts)

    # Pad to minimum length if requested
    if body_length > 0 and len(paper) < body_length:
        padding = "x" * (body_length - len(paper))
        # Insert before References
        ref_idx = paper.find("## References")
        if ref_idx >= 0:
            paper = paper[:ref_idx] + padding + "\n\n" + paper[ref_idx:]
        else:
            paper += padding

    return paper


# ---------------------------------------------------------------------------
# TestCheckCitationIntegrity
# ---------------------------------------------------------------------------


class TestCheckCitationIntegrity:
    def test_valid_citations_pass(self):
        reg = _make_registry(3)
        body = "Some text [1] and more [2] and [3].\n\n## References\n\n[1] A\n[2] B\n[3] C"
        result = _check_citation_integrity(body, reg)
        assert result.passed

    def test_orphan_citation_fails(self):
        reg = _make_registry(2)  # Only refs [1] and [2]
        body = "Text [1] [2] [99].\n\n## References\n\n[1] A\n[2] B"
        result = _check_citation_integrity(body, reg)
        assert not result.passed
        assert "99" in result.message

    def test_empty_body_passes(self):
        reg = _make_registry(0)
        result = _check_citation_integrity("", reg)
        assert result.passed

    def test_citations_in_refs_section_ignored(self):
        reg = _make_registry(2)
        # [99] only appears in References section — should pass
        body = "Text [1] [2].\n\n## References\n\n[1] A\n[2] B\n[99] phantom"
        result = _check_citation_integrity(body, reg)
        assert result.passed


# ---------------------------------------------------------------------------
# TestCheckNoPhantomSources
# ---------------------------------------------------------------------------


class TestCheckNoPhantomSources:
    def test_all_sources_cited_passes(self):
        reg = _make_registry(3)
        body = "Text [1] [2] [3].\n\n## References\n\n[1] A\n[2] B\n[3] C"
        result = _check_no_phantom_sources(body, reg)
        assert result.passed

    def test_phantom_source_fails(self):
        reg = _make_registry(3)  # Refs [1], [2], [3]
        body = "Text [1] [2].\n\n## References\n\n[1] A\n[2] B\n[3] C"
        result = _check_no_phantom_sources(body, reg)
        assert not result.passed
        assert "3" in result.message

    def test_no_sources_passes(self):
        reg = CitationRegistry()
        result = _check_no_phantom_sources("Some text.", reg)
        assert result.passed


# ---------------------------------------------------------------------------
# TestCheckMinimumContent
# ---------------------------------------------------------------------------


class TestCheckMinimumContent:
    def test_sufficient_content_passes(self):
        reg = _make_registry(4)
        body = "x" * 2500 + "\n\n## References\n\n[1] A"
        result = _check_minimum_content(body, reg)
        assert result.passed

    def test_short_body_fails(self):
        reg = _make_registry(4)
        body = "Short.\n\n## References\n\n[1] A"
        result = _check_minimum_content(body, reg)
        assert not result.passed
        assert "too short" in result.message.lower()

    def test_too_few_sources_fails(self):
        reg = _make_registry(1)  # Only 1 source
        body = "x" * 3000 + "\n\n## References\n\n[1] A"
        result = _check_minimum_content(body, reg)
        assert not result.passed
        assert "few sources" in result.message.lower()

    def test_boundary_2000_chars(self):
        reg = _make_registry(3)
        # Exactly 2000 chars in body (before refs)
        body = "a" * 2000 + "\n\n## References\n\n[1] A"
        result = _check_minimum_content(body, reg)
        assert result.passed


# ---------------------------------------------------------------------------
# TestCheckSectionStructure
# ---------------------------------------------------------------------------


class TestCheckSectionStructure:
    def test_valid_structure_passes(self):
        paper = _make_paper()
        result = _check_section_structure(paper)
        assert result.passed

    def test_missing_abstract_fails(self):
        paper = _make_paper(include_abstract=False)
        result = _check_section_structure(paper)
        assert not result.passed
        assert "abstract" in result.message.lower() or "introduction" in result.message.lower()

    def test_missing_references_fails(self):
        paper = _make_paper(include_refs=False)
        result = _check_section_structure(paper)
        assert not result.passed
        assert "references" in result.message.lower() or "sources" in result.message.lower()

    def test_introduction_accepted_instead_of_abstract(self):
        paper = "# Title\n\n## Introduction\n\nIntro text.\n\n## Analysis\n\nBody [1].\n\n## References\n\n[1] A"
        result = _check_section_structure(paper)
        assert result.passed

    def test_no_body_sections_fails(self):
        paper = "# Title\n\n## Abstract\n\nAbstract.\n\n## References\n\n[1] A"
        result = _check_section_structure(paper)
        assert not result.passed
        assert "body sections" in result.message.lower()


# ---------------------------------------------------------------------------
# TestCheckNoUncitedSections
# ---------------------------------------------------------------------------


class TestCheckNoUncitedSections:
    def test_all_sections_cited_passes(self):
        paper = _make_paper()
        result = _check_no_uncited_sections(paper)
        assert result.passed

    def test_uncited_analysis_section_fails(self):
        paper = _make_paper(
            body_sections=["Analysis", "Discussion"],
            citations_per_section=[[], [1, 2]],  # Analysis has no citations
        )
        result = _check_no_uncited_sections(paper)
        assert not result.passed
        assert "Analysis" in result.message

    def test_exempt_sections_skipped(self):
        # Abstract and Methodology should never be flagged
        paper = (
            "# Title\n\n"
            "## Abstract\n\nLong abstract text that is definitely more than one hundred characters to test the length threshold properly.\n\n"
            "## Methodology\n\nWe used excavation methods at multiple sites across the region for a prolonged period of multi-year fieldwork.\n\n"
            "## Results\n\nDetailed results with citation evidence from multiple archaeological investigations across the region. [1] [2]\n\n"
            "## References\n\n[1] A\n[2] B"
        )
        result = _check_no_uncited_sections(paper)
        assert result.passed

    def test_short_section_not_flagged(self):
        # Sections with <100 chars content are not flagged
        paper = (
            "# Title\n\n"
            "## Abstract\n\nShort.\n\n"
            "## Analysis\n\nBrief note.\n\n"  # <100 chars, won't be flagged
            "## Discussion\n\nDetailed discussion of findings from excavation data supporting our hypothesis about ancient construction. [1]\n\n"
            "## References\n\n[1] A"
        )
        result = _check_no_uncited_sections(paper)
        assert result.passed


# ---------------------------------------------------------------------------
# TestRunResearchChecklist (integration)
# ---------------------------------------------------------------------------


class TestRunResearchChecklist:
    def test_perfect_paper_passes(self):
        reg = _make_registry(3)
        paper = _make_paper(body_length=2500)
        result = run_research_checklist(paper, reg)
        assert result.passed
        assert result.summary == "ALL PASSED"

    def test_multiple_failures(self):
        reg = _make_registry(1)  # too few sources
        paper = "# Title\n\nShort paper."  # no structure, too short
        result = run_research_checklist(paper, reg)
        assert not result.passed
        assert "FAILED" in result.summary

    def test_to_dict_serialization(self):
        reg = _make_registry(3)
        paper = _make_paper(body_length=2500)
        result = run_research_checklist(paper, reg)
        d = result.to_dict()
        assert "passed" in d
        assert "summary" in d
        assert "checks" in d
        assert "citation_integrity" in d["checks"]
        assert d["checks"]["citation_integrity"]["passed"] is True
