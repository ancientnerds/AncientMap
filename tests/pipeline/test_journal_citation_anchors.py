"""The canonical journal page links its citations in the served HTML.

The standalone SPA reader used to build these links in the browser, so
/articles/{slug} — the page a crawler and a reader without JavaScript see —
carried "[6]" as plain text. These tests pin the server-side contract: the
anchors, their class and their data-citation key, which the reader binds the
hover card to.
"""

import re

from pipeline.article_html_renderer import (
    journal_citation_anchors,
    markdown_to_html,
    normalize_citation_markers,
    parse_web_citations,
)

BODY = (
    "Roman engineers moved the blocks with capstans [1], or so the video "
    "claims [6, 7]. The temple itself is later [V2].\n\n"
    "### Sources\n\n"
    "1. [Capstans and sledges](https://example.org/capstans)\n"
    "2. [Not cited in the text](https://example.org/uncited)\n"
)


def rendered() -> str:
    md = normalize_citation_markers(BODY)
    return journal_citation_anchors(markdown_to_html(md), parse_web_citations(md))


class TestTheSourcesList:
    def test_a_numbered_source_line_is_the_citation_target(self):
        assert parse_web_citations(BODY) == {
            1: "https://example.org/capstans",
            2: "https://example.org/uncited",
        }

    def test_a_line_without_a_number_is_not_a_source(self):
        assert parse_web_citations("### Sources\n\n- [A](https://example.org/a)\n") == {}


class TestGroupedMarkers:
    def test_a_group_becomes_one_marker_per_number(self):
        assert normalize_citation_markers("claims [6, 7] here") == "claims [6] [7] here"

    def test_two_markers_in_a_row_are_split(self):
        assert normalize_citation_markers("see [3][5]") == "see [3] [5]"

    def test_a_single_marker_is_left_alone(self):
        assert normalize_citation_markers("see [3]") == "see [3]"

    def test_both_numbers_of_a_group_become_links(self):
        html = rendered()
        assert 'data-citation="6"' in html and 'data-citation="7"' in html


class TestTheServedAnchors:
    def test_a_web_citation_links_to_its_source(self):
        html = rendered()
        assert (
            '<a class="article-citation-link" data-citation="1" '
            'href="https://example.org/capstans" target="_blank" '
            'rel="noopener noreferrer">[1]</a>' in html
        )

    def test_a_video_citation_points_at_the_source_list(self):
        """A video citation has no URL: the reader finds its card at the
        source list, exactly as the SPA reader's #sources link did."""
        assert (
            '<a class="article-citation-link" data-citation="V2" href="#sources">[V2]</a>'
            in rendered()
        )

    def test_a_citation_without_a_source_points_at_the_source_list(self):
        md = normalize_citation_markers("A claim [9] with no source line.\n")
        html = journal_citation_anchors(markdown_to_html(md), parse_web_citations(md))
        assert 'data-citation="9" href="#sources"' in html

    def test_the_link_text_is_the_marker_a_reader_knows(self):
        assert ">[" in rendered() and "</a>" in rendered()

    def test_no_plain_marker_is_left_in_the_prose(self):
        """Every marker is either an anchor or gone: the reader shows the same
        "[1]" as its link text, so the prose itself must hold none."""
        body = rendered().split("<h3")[0]
        outside_links = re.sub(r'<a class="article-citation-link".*?</a>', "", body)
        assert re.search(r"\[V?\d+", outside_links) is None


class TestWhatMustNotBeLinked:
    def test_a_marker_inside_a_link_is_not_a_second_link(self):
        """The Markdown already turned "[title](url)" into a link; a marker in
        its text belongs to that link, not to the source list."""
        md = normalize_citation_markers("See [the wall [3]](https://example.org/wall).\n")
        html = journal_citation_anchors(markdown_to_html(md), parse_web_citations(md))
        assert html.count("<a ") == 1
        assert "data-citation" not in html

    def test_a_marker_in_a_code_sample_stays_text(self):
        md = normalize_citation_markers("Cite like this:\n\n```\nfacts [1]\n```\n")
        html = journal_citation_anchors(markdown_to_html(md), {1: "https://example.org/a"})
        assert "data-citation" not in html
        assert "[1]" in html

    def test_a_marker_in_a_link_target_is_untouched(self):
        """Markdown link syntax itself must survive: the group normaliser runs
        on the source, the anchors on the rendered HTML."""
        md = normalize_citation_markers("A [link](https://example.org/x?a=[1]) here.\n")
        assert "https://example.org/x?a=[1]" in md


class TestTheAnchorsSurviveTheSanitizer:
    def test_nh3_keeps_no_data_attribute_of_its_own(self):
        """Why the anchors are injected after the sanitizer, like the heading
        ids: the attribute is not on nh3's allowlist, so the Markdown cannot
        carry it."""
        assert "data-citation" not in markdown_to_html("A claim [1].\n", toc=False)

    def test_the_injected_anchor_is_in_the_served_html(self):
        assert 'data-citation="1"' in rendered()
