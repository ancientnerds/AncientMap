# SPDX-License-Identifier: AGPL-3.0-only
"""#ev-NN anchors on the research paper page (studio spec 2026-09-26 §2.7, §4.5).

Video descriptions deep-link claims as /research/{slug}#ev-NN, and the studio
captures the paper scrolled to them. nh3 strips id attributes from the markdown
output, so the anchors are injected into the finished HTML, the way
_heading_anchors restores h2/h3 ids. The paragraph is the one whose text opens
with the evidence entry's anchor_text, compared through normalize_anchor_text
(pipeline/lyra/theo_publishing, stream A: the publish gate's contract C9), and
these tests also pin the one property of that function the page relies on: a
markdown paragraph and its rendered text normalise to the same key.
"""

from __future__ import annotations

import pytest

from pipeline.article_html_renderer import markdown_to_html
from pipeline.lyra.theo_publishing import MIN_ANCHOR_CHARS, normalize_anchor_text
from pipeline.research_html_renderer import (
    PaperPageError,
    VideoMoment,
    _paragraph_text,
    inject_evidence_anchors,
    paper_markdown,
    resolve_evidence_anchors,
)

REPORT = (
    "## The Quarry\n\n"
    'The "Stone of the Pregnant Woman" weighs about 1,000 tonnes -- roughly the mass of '
    "*three* jumbo jets [1] [2].\n\n"
    "Ruprechtsberger's team dated the quarry face to the 1st century AD... "
    "a date others dispute [3].\n\n"
    "## References\n\n"
    "[1] Doe, J. (2020). Baalbek quarries. https://example.org/paper\n"
)
# An anchor is the opening of its paragraph; two entries may open the same one.
EVIDENCE = [
    {
        "id": "ev-01",
        "anchor_text": 'The "Stone of the Pregnant Woman" weighs about 1,000 tonnes -- roughly',
    },
    {"id": "ev-02", "anchor_text": "Ruprechtsberger's team dated the quarry face"},
    {"id": "ev-03", "anchor_text": "Ruprechtsberger's team dated the quarry face to the 1st"},
]
MOMENTS = {"ev-01": [VideoMoment("dQw4w9WgXcQ", 312, "Baalbek: the 1,000-tonne question")]}
NOWHERE = {"id": "ev-07", "anchor_text": "Machu Picchu was built by the Inca"}
TOO_SHORT = {"id": "ev-08", "anchor_text": "the"}

P1 = (
    "The \u201cStone of the Pregnant Woman\u201d weighs about 1,000 tonnes \u2013 roughly "
    "the mass of <em>three</em> jumbo jets [1] [2]."
)
P2 = (
    "Ruprechtsberger\u2019s team dated the quarry face to the 1st century AD\u2026 "
    "a date others dispute [3]."
)
REFS = (
    '<h2 id="references">References</h2>\n'
    '<p>[1] Doe, J. (2020). Baalbek quarries. <a href="https://example.org/paper" '
    'rel="noopener noreferrer" target="_blank">https://example.org/paper</a></p>'
)
VIDEO_LINK = (
    ' <a class="theo-evidence-video" '
    'href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=312s" target="_blank" '
    'rel="noopener noreferrer" '
    'title="Watch this passage in the video: Baalbek: the 1,000-tonne question">'
    "Video at 5:12</a>"
)


def rendered() -> str:
    return markdown_to_html(paper_markdown(REPORT, "Baalbek"))


class TestNormalizeAnchorTextContract:
    """What the page needs from stream A's normalize_anchor_text."""

    @pytest.mark.parametrize(
        "paragraph",
        [
            'The "Stone" weighs 1,000 tonnes -- or --- so [1].',
            "Ruprechtsberger's team dated it to the 1st century AD... others dispute it [3].",
            "A paragraph with a [linked source](https://example.org/x) and **strong** words [4].",
            "It is *very likely* that the blocks were moved on sledges & rollers [5].",
            "Two   spaces\nand a soft line break stay one space [6].",
            "See <https://example.org/x> for the survey [8].",
            "A backslash \\*escaped\\* star [9].",
            "Aa &amp; bb [12].",
        ],
    )
    def test_markdown_and_its_rendered_text_share_one_key(self, paragraph):
        inner = markdown_to_html(paragraph, toc=False).removeprefix("<p>").removesuffix("</p>")
        assert normalize_anchor_text(paragraph) == normalize_anchor_text(_paragraph_text(inner))


class TestResolveEvidenceAnchors:
    def test_maps_each_id_to_its_paragraph_index(self):
        # <p> order in the rendered body: P1, P2, the reference line.
        assert resolve_evidence_anchors(rendered(), EVIDENCE) == {
            "ev-01": 0,
            "ev-02": 1,
            "ev-03": 1,
        }

    def test_an_anchor_found_nowhere_fails(self):
        with pytest.raises(PaperPageError, match="ev-07 matches 0 paragraphs"):
            resolve_evidence_anchors(rendered(), [NOWHERE])

    def test_an_anchor_from_the_middle_of_a_paragraph_does_not_resolve(self):
        # Contract C9: the paragraph must START WITH the anchor, as the
        # writer brief asks ("anchor_text is the opening of that paragraph").
        with pytest.raises(PaperPageError, match="ev-09 matches 0 paragraphs"):
            resolve_evidence_anchors(
                rendered(), [{"id": "ev-09", "anchor_text": "a date others dispute"}]
            )

    def test_an_opening_that_recurs_inside_another_paragraph_still_resolves(self):
        html = markdown_to_html(
            "The Stone of the Pregnant Woman weighs roughly 1,000 tonnes [1].\n\n"
            "In fact the Stone of the Pregnant Woman weighs roughly as much as three jets [2].",
            toc=False,
        )
        anchor = {"id": "ev-01", "anchor_text": "The Stone of the Pregnant Woman weighs roughly"}
        assert resolve_evidence_anchors(html, [anchor]) == {"ev-01": 0}

    def test_an_anchor_opening_two_paragraphs_fails(self):
        html = markdown_to_html(
            "Roman engineers moved blocks with capstans [1].\n\n"
            "Roman engineers moved blocks with ramps too [2].",
            toc=False,
        )
        with pytest.raises(PaperPageError, match="ev-08 matches 2 paragraphs"):
            resolve_evidence_anchors(
                html, [{"id": "ev-08", "anchor_text": "Roman engineers moved blocks"}]
            )

    def test_an_anchor_shorter_than_the_minimum_fails(self):
        with pytest.raises(
            PaperPageError,
            match=f"ev-08: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation",
        ):
            resolve_evidence_anchors(rendered(), [TOO_SHORT])

    def test_every_unresolved_entry_is_named_at_once(self):
        with pytest.raises(PaperPageError) as err:
            resolve_evidence_anchors(rendered(), [NOWHERE, TOO_SHORT])
        assert "ev-07" in str(err.value) and "ev-08" in str(err.value)


class TestInjectEvidenceAnchors:
    def test_exact_markup_for_the_fixture_paper(self):
        assert inject_evidence_anchors(rendered(), EVIDENCE, MOMENTS) == (
            '<h2 id="the-quarry">The Quarry</h2>\n'
            f'<p id="ev-01" class="theo-evidence">{P1}{VIDEO_LINK}</p>\n'
            '<p id="ev-02" class="theo-evidence">'
            f'<span class="theo-evidence-anchor" id="ev-03"></span>{P2}</p>\n'
            f"{REFS}"
        )

    def test_a_paper_without_evidence_is_returned_unchanged(self):
        html = rendered()
        assert inject_evidence_anchors(html, [], {}) == html

    def test_anchors_survive_only_because_they_are_injected_after_nh3(self):
        # attr_list ids in the markdown are stripped by the sanitizer ...
        assert 'id="ev-01"' not in markdown_to_html("A claim [1].\n{: #ev-01 }")
        # ... while the injected ones are in the served HTML.
        assert 'id="ev-01"' in inject_evidence_anchors(rendered(), EVIDENCE[:1])

    def test_markdown_to_html_itself_never_adds_evidence_ids(self):
        # Journals and the Medium copy share markdown_to_html: the anchors are
        # a research-page step only.
        assert "theo-evidence" not in rendered()

    def test_video_time_past_an_hour_reads_h_mm_ss(self):
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[:1], {"ev-01": [VideoMoment("dQw4w9WgXcQ", 3725, "Long")]}
        )
        assert "&amp;t=3725s" in html
        assert "Video at 1:02:05</a>" in html

    def test_the_same_moment_named_by_two_ids_of_one_paragraph_links_once(self):
        moment = VideoMoment("dQw4w9WgXcQ", 400, "V")
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[1:], {"ev-02": [moment], "ev-03": [moment]}
        )
        assert html.count("Video at 6:40") == 1

    def test_the_video_title_is_escaped_in_the_attribute(self):
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[:1], {"ev-01": [VideoMoment("dQw4w9WgXcQ", 1, 'A "quoted" <b>')]}
        )
        assert 'title="Watch this passage in the video: A &quot;quoted&quot; &lt;b&gt;"' in html

    def test_unresolvable_evidence_raises_instead_of_dropping_the_anchor(self):
        with pytest.raises(PaperPageError, match="ev-07 matches 0 paragraphs"):
            inject_evidence_anchors(rendered(), [NOWHERE])
