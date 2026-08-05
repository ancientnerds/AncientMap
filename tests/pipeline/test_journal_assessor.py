"""Tests for journal_assessor.py."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from pipeline.lyra.journal_assessor import (
    QUALITY_BLOCKED_DOMAINS,
    SPELLING_FIXES,
    AssessmentResult,
    _check_d1_proper_nouns,
    _check_d2_citation_coverage,
    _check_d3_academic_citations,
    _check_d4_screenshots,
    _check_d5_source_quality,
    _check_d6_spelling,
    _check_d7_citation_format,
    _check_d8_week_date,
    _check_d9_summary,
    _check_d10_section_balance,
    _extract_proper_nouns,
    _fix_d7_citation_format,
    _fix_d8_week_date,
    _significant_keywords,
    _validate_d1_correction,
)


class TestD7CitationFormat:
    def test_comma_citations_detected(self):
        body = "Evidence found [6, 7] at the site."
        issues = _check_d7_citation_format(body, [{"citation": 6}, {"citation": 7}])
        assert not issues["passed"]

    def test_normal_citations_pass(self):
        body = "Evidence found [6] [7] at the site."
        issues = _check_d7_citation_format(body, [{"citation": 6}, {"citation": 7}])
        assert issues["passed"]

    def test_fix_normalizes_commas(self):
        body = "Evidence found [6, 7] at the site."
        fixed = _fix_d7_citation_format(body, [{"citation": 6}, {"citation": 7}])
        assert "[6] [7]" in fixed
        assert "[6, 7]" not in fixed

    def test_fix_triple_comma(self):
        body = "Evidence found [1, 2, 3] at the site."
        fixed = _fix_d7_citation_format(body, [{"citation": 1}, {"citation": 2}, {"citation": 3}])
        assert "[1] [2] [3]" in fixed

    def test_orphaned_citations_detected(self):
        body = "Evidence [99] not in sources."
        result = _check_d7_citation_format(body, [{"citation": 1}])
        assert not result["passed"]

    def test_orphaned_citations_removed(self):
        body = "Evidence [99] not in sources."
        fixed = _fix_d7_citation_format(body, [{"citation": 1}])
        assert "[99]" not in fixed

    def test_valid_citation_preserved(self):
        body = "Evidence [1] in sources."
        fixed = _fix_d7_citation_format(body, [{"citation": 1}])
        assert "[1]" in fixed


class TestD8WeekDate:
    def test_correct_date_passes(self):
        title = "Week of March 30: Something Happened"
        ws = datetime(2026, 3, 30, tzinfo=UTC)
        result = _check_d8_week_date(title, ws)
        assert result["passed"]

    def test_wrong_date_fails(self):
        title = "Week of March 16: Something Happened"
        ws = datetime(2026, 3, 30, tzinfo=UTC)
        result = _check_d8_week_date(title, ws)
        assert not result["passed"]

    def test_no_week_start_passes(self):
        title = "Week of March 16: Something Happened"
        result = _check_d8_week_date(title, None)
        assert result["passed"]

    def test_fix_replaces_date(self):
        body = "Week of March 16: Something Happened\n\nContent here."
        ws = datetime(2026, 3, 30, tzinfo=UTC)
        fixed = _fix_d8_week_date(body, ws)
        assert "March 30" in fixed
        assert "March 16" not in fixed
        assert "Something Happened" in fixed


class TestD2CitationCoverage:
    def test_uncited_paragraph_detected(self):
        # Need 4+ uncited paragraphs to fail (up to 3 allowed)
        long_para = (
            "This is a long paragraph with more than three hundred characters that "
            "makes factual claims about archaeological sites without any citation "
            "markers anywhere in the text. It describes excavation findings from "
            "multiple seasons of fieldwork at a prehistoric settlement where "
            "researchers uncovered artifacts dating back thousands of years."
        )
        body = "\n\n".join([long_para] * 4)
        result = _check_d2_citation_coverage(body, [{"citation": 1}])
        assert not result["passed"]
        assert len(result["uncited_paragraphs"]) == 4

    def test_cited_paragraph_passes(self):
        body = (
            "This is a long paragraph with more than one hundred characters that "
            "makes factual claims about archaeological sites with a citation [1] "
            "marker in the text."
        )
        result = _check_d2_citation_coverage(body, [{"citation": 1}])
        assert result["passed"]

    def test_short_paragraphs_ignored(self):
        body = "Short uncited para.\n\nAnother short one."
        result = _check_d2_citation_coverage(body, [{"citation": 1}])
        assert result["passed"]

    def test_headers_ignored(self):
        body = "## This is a header with more than one hundred characters that would otherwise trigger the check but should be ignored"
        result = _check_d2_citation_coverage(body, [{"citation": 1}])
        assert result["passed"]


class TestD3AcademicCitations:
    def test_author_year_detected(self):
        body = "The site was first described (Smith, 2019) and later confirmed."
        result = _check_d3_academic_citations(body)
        assert not result["passed"]

    def test_et_al_detected(self):
        body = "Recent work (Johnson et al., 2023) supports this."
        result = _check_d3_academic_citations(body)
        assert not result["passed"]

    def test_bracket_citations_pass(self):
        body = "The site was first described [1] and later confirmed [2]."
        result = _check_d3_academic_citations(body)
        assert result["passed"]


class TestD5SourceQuality:
    def test_blocked_domain_detected(self):
        sources = [
            {"citation": 1, "url": "https://www.tripadvisor.com/page", "label": "Trip"},
        ]
        result = _check_d5_source_quality(sources)
        assert not result["passed"]
        assert len(result["bad_sources"]) == 1

    def test_good_domain_passes(self):
        sources = [
            {"citation": 1, "url": "https://www.nature.com/article", "label": "Nature"},
        ]
        result = _check_d5_source_quality(sources)
        assert result["passed"]

    def test_multiple_bad_sources(self):
        sources = [
            {"citation": 1, "url": "https://www.quizlet.com/set", "label": "Quiz"},
            {"citation": 2, "url": "https://gaia.com/show", "label": "Gaia"},
            {"citation": 3, "url": "https://nature.com/article", "label": "Nature"},
        ]
        result = _check_d5_source_quality(sources)
        assert not result["passed"]
        assert len(result["bad_sources"]) == 2


class TestD10SectionBalance:
    def test_balanced_passes(self):
        # Build a body ~1600 words with balanced sections (each ~390 words, under 400)
        section = "Word " * 388 + "[1] and text.\n\n"
        body = (
            "## Section One\n\n"
            + section
            + "## Section Two\n\n"
            + section
            + "## Section Three\n\n"
            + section
            + "## Section Four\n\n"
            + section
        )
        result = _check_d10_section_balance(body)
        assert result["passed"]

    def test_overlong_section_detected(self):
        long_section = "Word " * 650 + "[1].\n\n"
        body = "## Section One\n\n" + long_section + "## Section Two\n\nShort [1].\n\n"
        # Total ~900 words, below 1500 threshold — will have two issues
        result = _check_d10_section_balance(body)
        assert not result["passed"]

    def test_uncited_section_detected(self):
        section = "Word " * 80 + "no citations here.\n\n"
        cited = "Word " * 80 + "[1] citation here.\n\n"
        body = "## Cited Section\n\n" + cited + "## Uncited Section\n\n" + section
        # Will fail on word count too, but let's check it detects uncited
        result = _check_d10_section_balance(body)
        assert not result["passed"]
        assert any("0 citations" in i for i in result["issues"])


class TestSpellingDict:
    def test_dolman_in_dict(self):
        assert "dolman" in SPELLING_FIXES
        assert SPELLING_FIXES["dolman"] == "dolmen"

    def test_blocked_domains(self):
        assert "quizlet.com" in QUALITY_BLOCKED_DOMAINS
        assert "tripadvisor.com" in QUALITY_BLOCKED_DOMAINS


class TestAssessmentResult:
    def test_perfect_score(self):
        r = AssessmentResult(
            score=10,
            passed=True,
            dimensions={f"D{i}": True for i in range(1, 11)},
            fixes_applied=[],
            iteration=1,
        )
        assert r.passed
        assert r.score == 10

    def test_failing_score(self):
        dims = {f"D{i}": True for i in range(1, 11)}
        dims["D1"] = False
        dims["D6"] = False
        r = AssessmentResult(
            score=8,
            passed=False,
            dimensions=dims,
            fixes_applied=[],
            iteration=2,
        )
        assert not r.passed
        assert r.score == 8


@pytest.mark.live_llm
class TestD1ProperNouns:
    """Test mechanical fuzzy-match proper noun checking.

    Marked live_llm (Follow-up-Ticket 3, 2026-08-05): _check_d1_proper_nouns
    unconditionally calls call_api (real MiniMax) whenever the body has any
    proper nouns, wrapped in a broad try/except that swallows failures —
    several tests here (test_exact_match_passes, test_fuzzy_mismatch_detected,
    test_spelling_fixes_in_proper_nouns) hit the network every run. The whole
    class is marked together rather than splitting it method-by-method."""

    def test_extract_proper_nouns(self):
        text = "The Montesiepi Chapel was built by Galgano Guidotti near San Galgano."
        nouns = _extract_proper_nouns(text)
        assert "Montesiepi Chapel" in nouns
        assert "Galgano Guidotti" in nouns
        assert "San Galgano" in nouns

    def test_exact_match_passes(self):
        body = "The Montesiepi Chapel is notable."
        sources = [{"label": "Montesiepi Chapel - Wikipedia", "url": "https://en.wikipedia.org"}]
        settings = MagicMock()
        result = _check_d1_proper_nouns(body, sources, settings)
        assert result["passed"]

    def test_fuzzy_mismatch_detected(self):
        body = "The Monteppi Chapel is notable."
        sources = [
            {
                "label": "Montesiepi Chapel - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Montesiepi_Chapel",
            }
        ]
        settings = MagicMock()
        result = _check_d1_proper_nouns(body, sources, settings)
        assert not result["passed"]
        assert len(result["issues"]) >= 1
        assert result["issues"][0]["find"] == "Monteppi Chapel"
        assert result["issues"][0]["replace"] == "Montesiepi Chapel"

    def test_no_nouns_passes(self):
        body = "this is all lowercase text."
        sources = [{"label": "some source", "url": "https://example.com"}]
        settings = MagicMock()
        result = _check_d1_proper_nouns(body, sources, settings)
        assert result["passed"]

    def test_validate_rejects_identity(self):
        assert not _validate_d1_correction("Foo Bar", "Foo Bar", [])

    def test_validate_rejects_case_only(self):
        assert not _validate_d1_correction("Foo Bar", "foo bar", [])

    def test_validate_rejects_bad_spelling(self):
        assert not _validate_d1_correction("Foo Bar", "Foo dolman", [])

    def test_validate_rejects_youtube_only(self):
        sources = [{"url": "https://youtube.com/watch?v=abc", "label": "Galgano Guidotti"}]
        assert not _validate_d1_correction("Galano Giati", "Galgano Guidotti", sources)

    def test_validate_accepts_academic(self):
        sources = [{"url": "https://en.wikipedia.org/wiki/Galgano", "label": "Galgano Guidotti"}]
        assert _validate_d1_correction("Galano Giati", "Galgano Guidotti", sources)

    def test_spelling_fixes_in_proper_nouns(self):
        body = "The Volkonsky Dolman stands tall."
        sources = [{"label": "Volkonsky Dolmen", "url": "https://example.com"}]
        settings = MagicMock()
        result = _check_d1_proper_nouns(body, sources, settings)
        assert not result["passed"]
        fix = result["issues"][0]
        assert fix["find"] == "Volkonsky Dolman"
        assert fix["replace"] == "Volkonsky Dolmen"


class TestD4Screenshots:
    """Test mechanical keyword overlap for screenshot placement."""

    def test_well_placed_image_passes(self):
        body = (
            "## Ancient Temples\n\n"
            "The ancient temple of Karnak features massive stone columns and intricate carvings.\n\n"
            "![Ancient temple Karnak stone columns](https://example.com/img.jpg)\n\n"
            "More text here."
        )
        result = _check_d4_screenshots(body)
        assert result["passed"]

    def test_no_images_passes(self):
        body = "Just text, no images at all."
        result = _check_d4_screenshots(body)
        assert result["passed"]

    def test_significant_keywords(self):
        kw = _significant_keywords("Ancient temple Karnak stone columns")
        assert "ancient" in kw
        assert "temple" in kw
        assert "karnak" in kw
        assert "stone" in kw
        # "of" (3 chars) should be excluded
        kw2 = _significant_keywords("The cat sat on the mat")
        assert "the" not in kw2  # only 3 chars

    def test_too_few_alt_keywords_skipped(self):
        """Images with <2 significant keywords in alt text are skipped."""
        body = "Some paragraph text.\n\n![Map](https://example.com/img.jpg)\n\nMore text."
        result = _check_d4_screenshots(body)
        assert result["passed"]  # "Map" is only 3 chars, skipped


class TestD6SpellingMechanical:
    """Test dictionary-only spelling check."""

    def test_known_misspelling_detected(self):
        body = "The dolman was erected in the Bronze Age."
        result = _check_d6_spelling(body)
        assert not result["passed"]
        assert result["issues"][0]["find"] == "dolman"
        assert result["issues"][0]["replace"] == "dolmen"

    def test_correct_spelling_passes(self):
        body = "The dolmen was erected in the Bronze Age."
        result = _check_d6_spelling(body)
        assert result["passed"]

    def test_multiple_fixes(self):
        body = "The dolman culture was Nufian in origin."
        result = _check_d6_spelling(body)
        assert not result["passed"]
        finds = {i["find"] for i in result["issues"]}
        assert "dolman" in finds
        assert "Nufian" in finds


class TestD9SummaryMechanical:
    """Test mechanical proper noun check for summary accuracy."""

    def test_accurate_summary_passes(self, monkeypatch):
        # Mock the LLM layer so it doesn't make real API calls
        from pipeline.lyra import journal_assessor
        from pipeline.lyra.config import NormalizedResponse, TextBlock

        monkeypatch.setattr(
            journal_assessor,
            "call_api",
            lambda **kwargs: NormalizedResponse(content=[TextBlock(text='{"accurate": true}')]),
        )
        body = (
            "*This week covers discoveries at Galgano Guidotti site.*\n\n"
            "---\n\n"
            "## Main Story\n\n"
            "Galgano Guidotti was a medieval knight."
        )
        result = _check_d9_summary(body)
        assert result["passed"]

    def test_mismatched_noun_detected(self, monkeypatch):
        from pipeline.lyra import journal_assessor
        from pipeline.lyra.config import NormalizedResponse, TextBlock

        monkeypatch.setattr(
            journal_assessor,
            "call_api",
            lambda **kwargs: NormalizedResponse(
                content=[TextBlock(text='{"accurate": false, "issues": ["mismatch"]}')]
            ),
        )
        body = (
            "*This week covers discoveries at Galano Giati site.*\n\n"
            "---\n\n"
            "## Main Story\n\n"
            "Galgano Guidotti was a medieval knight."
        )
        result = _check_d9_summary(body)
        assert not result["passed"]
        assert len(result["issues"]) >= 1

    def test_no_summary_passes(self):
        body = "## Just a header\n\nNo italic summary here."
        result = _check_d9_summary(body)
        assert result["passed"]

    def test_summary_noun_not_in_body_flagged(self, monkeypatch):
        from pipeline.lyra import journal_assessor
        from pipeline.lyra.config import NormalizedResponse, TextBlock

        monkeypatch.setattr(
            journal_assessor,
            "call_api",
            lambda **kwargs: NormalizedResponse(
                content=[TextBlock(text='{"accurate": false, "issues": ["not in body"]}')]
            ),
        )
        body = (
            "*Amazing finds at Xanadu Palace revealed.*\n\n"
            "---\n\n"
            "## Main Story\n\n"
            "Completely different topic about something else entirely."
        )
        result = _check_d9_summary(body)
        assert not result["passed"]
        assert any("Xanadu Palace" in issue for issue in result["issues"])
