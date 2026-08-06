"""Tests for _uncited_ratio helper used by the per-section repair pass."""

from pipeline.lyra.handlers.paper import PaperHandler


def test_uncited_ratio_all_cited():
    prose = "First para [1] with content. More text.\n\nSecond para [2] with content. More."
    assert PaperHandler._uncited_ratio(prose) == 0.0


def test_uncited_ratio_half_uncited():
    prose = (
        "First paragraph has a citation [1] to support this long factual claim here.\n\n"
        "Second paragraph has no marker whatsoever and is deliberately over fifty characters."
    )
    assert PaperHandler._uncited_ratio(prose) == 0.5


def test_uncited_ratio_ignores_headings():
    prose = (
        "## Heading\n\n"
        "First actual paragraph with a citation [1] and enough length to count as factual.\n\n"
        "Second actual paragraph is missing its marker though it is over fifty characters."
    )
    # One of two factual paragraphs uncited
    assert PaperHandler._uncited_ratio(prose) == 0.5


def test_uncited_ratio_ignores_short_paragraphs():
    prose = "Short.\n\nAlso short.\n\nFinally a real factual paragraph over fifty characters [1]."
    # Only one paragraph is long enough to be factual, and it has a citation
    assert PaperHandler._uncited_ratio(prose) == 0.0


def test_uncited_ratio_empty():
    assert PaperHandler._uncited_ratio("") == 0.0
