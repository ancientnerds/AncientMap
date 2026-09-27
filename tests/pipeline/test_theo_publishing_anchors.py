"""Evidence anchors: one normalisation for the markdown here and the page's HTML (stream B)."""

import pytest

from pipeline.lyra.theo_publishing import (
    EVIDENCE_ID_RE,
    MIN_ANCHOR_CHARS,
    YOUTUBE_ID_RE,
    normalize_anchor_text,
    poster_web_path,
    report_paragraphs,
    resolve_evidence_anchors,
)
from tests.pipeline.theo_publish_fixtures import EVIDENCE, REPORT, REQ


def test_markdown_and_rendered_text_normalise_to_the_same_string():
    markdown = 'The **Stone** of the "Pregnant" Woman -- a [block](https://x.example) [1] weighs...'
    rendered = "The Stone of the “Pregnant” Woman – a block [1] weighs…"
    expected = 'the stone of the "pregnant" woman - a block weighs...'
    assert normalize_anchor_text(markdown) == expected
    assert normalize_anchor_text(rendered) == expected


# (markdown source, the text content markdown_to_html renders for it): both
# sides must fold to one key. The rendered forms were taken from
# pipeline.article_html_renderer.markdown_to_html (tags removed, entities
# unescaped) when this plan was written.
@pytest.mark.parametrize(
    ("markdown", "rendered"),
    [
        (
            "See <https://example.org/x> for the survey [8].",
            "See https://example.org/x for the survey [8].",
        ),
        ("A backslash \\*escaped\\* star [9].", "A backslash *escaped* star [9]."),
        (
            "Escaped \\[brackets\\] and a \\_word\\_ stay [10].",
            "Escaped [brackets] and a _word_ stay [10].",
        ),
        ("Aa &amp; bb &mdash; cc [12].", "Aa & bb — cc [12]."),
    ],
)
def test_autolinks_escapes_and_entities_fold_like_the_rendered_text(markdown, rendered):
    assert normalize_anchor_text(markdown) == normalize_anchor_text(rendered)


@pytest.mark.parametrize(
    ("typographic", "typed"),
    [
        (
            "«Guillemets», a 5′ block, a 3″ gap ‒ and ― dashes [13].",
            '"Guillemets", a 5\' block, a 3" gap - and - dashes [13].',
        ),
        ("STRASSE and Straße fold alike [14].", "strasse and strasse fold alike [14]."),
    ],
)
def test_rare_typography_and_case_fold_to_what_a_writer_types(typographic, typed):
    assert normalize_anchor_text(typographic) == normalize_anchor_text(typed)


def test_ids_are_matched_whole():
    assert EVIDENCE_ID_RE.fullmatch("ev-01")
    assert EVIDENCE_ID_RE.fullmatch("ev-01\n") is None
    assert EVIDENCE_ID_RE.fullmatch("ev-1") is None
    # ASCII digits only, like the frontend's PAPER_HASH_RE copy: \d would also
    # take Arabic-Indic or full-width digits.
    assert EVIDENCE_ID_RE.fullmatch("ev-\u0660\u0661") is None
    assert EVIDENCE_ID_RE.fullmatch("ev-\uff10\uff11") is None


def test_youtube_ids_are_matched_whole():
    assert YOUTUBE_ID_RE.fullmatch("dQw4w9WgXcQ")
    assert YOUTUBE_ID_RE.fullmatch("dQw4w9WgXcQ\n") is None
    assert YOUTUBE_ID_RE.fullmatch("dQw4w9WgXc") is None
    assert YOUTUBE_ID_RE.fullmatch("dQw4w9WgXcQQ") is None


def test_the_poster_is_the_studio_thumbnail_in_the_papers_folder():
    assert (
        poster_web_path(REQ, "dQw4w9WgXcQ") == f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg"
    )


def test_citation_and_draft_markers_disappear():
    assert (
        normalize_anchor_text("Dated to 9600 BC [S:1a2b3c4d5e6f] [2, 3] [4–6].")
        == "dated to 9600 bc ."
    )


def test_emphasis_underscores_go_but_snake_case_stays():
    assert (
        normalize_anchor_text("The _Kybalion_ cites the_all principle")
        == "the kybalion cites the_all principle"
    )


def test_report_paragraphs_are_prose_only():
    paragraphs = report_paragraphs(REPORT)
    assert len(paragraphs) == 5
    assert paragraphs[0].startswith("In 2014 a team")
    assert paragraphs[1].startswith("The Stone of the Pregnant Woman")
    assert all(not p.startswith(("#", "!", "*", "[1]")) for p in paragraphs)


def test_each_published_anchor_hits_exactly_one_paragraph():
    resolved, issues = resolve_evidence_anchors(REPORT, EVIDENCE)
    assert issues == []
    assert resolved == {"ev-01": 1, "ev-02": 4}


def test_ambiguous_missing_and_short_anchors_are_reported():
    report = (
        "# T\n\nRoman engineers moved blocks with capstans [1].\n\n"
        "Roman engineers moved blocks with ramps too [1].\n\n"
        "## References\n\n[1] A — https://a.example (accessed 2026-01-01)\n"
    )
    evidence = [
        {"id": "ev-01", "anchor_text": "Roman engineers moved blocks"},
        {"id": "ev-02", "anchor_text": "Greek engineers moved the blocks"},
        {"id": "ev-03", "anchor_text": "Roman"},
    ]
    resolved, issues = resolve_evidence_anchors(report, evidence)
    assert resolved == {}
    assert issues == [
        "ev-01: anchor_text matches 2 paragraphs (needs exactly 1)",
        "ev-02: anchor_text matches 0 paragraphs (needs exactly 1)",
        f"ev-03: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation",
    ]
