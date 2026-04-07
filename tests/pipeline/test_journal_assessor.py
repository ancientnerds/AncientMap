"""Tests for journal_assessor.py."""

from datetime import UTC, datetime

from pipeline.lyra.journal_assessor import (
    QUALITY_BLOCKED_DOMAINS,
    SPELLING_FIXES,
    AssessmentResult,
    _check_d2_citation_coverage,
    _check_d3_academic_citations,
    _check_d5_source_quality,
    _check_d7_citation_format,
    _check_d8_week_date,
    _check_d10_section_balance,
    _fix_d7_citation_format,
    _fix_d8_week_date,
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
        body = (
            "Short para.\n\n"
            "This is a long paragraph with more than one hundred characters that "
            "makes factual claims about archaeological sites without any citation "
            "markers anywhere in the text."
        )
        result = _check_d2_citation_coverage(body, [{"citation": 1}])
        assert not result["passed"]
        assert len(result["uncited_paragraphs"]) == 1

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
