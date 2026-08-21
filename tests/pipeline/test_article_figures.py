"""
Standalone images in journal/research bodies become <figure> with a caption.

Journals rendered bare <img> inside a <p>: 1280px wide in a 720px text column
(measured live 2026-08-21), no caption, no credit for the frame. The renderer
is shared with research papers and the Medium copies, so these cases guard
every consumer at once.
"""

import re

from pipeline.article_html_renderer import markdown_to_html


def render(md: str) -> str:
    return markdown_to_html(md, toc=False)


class TestStandaloneImages:
    def test_pipeline_screenshot_gets_caption_and_source_link(self):
        html = render("![Excavation trench](/data/news/screenshots/Xtm2bRRA5h4_296.webp)")
        assert '<figure class="article-figure">' in html
        assert '<figcaption class="article-figcaption">' in html
        assert "Excavation trench" in html
        # Offset and id come from the filename convention — the only thing
        # tying a frame back to the video it was cut from.
        assert "https://www.youtube.com/watch?v=Xtm2bRRA5h4&t=296s" in html

    def test_non_screenshot_image_gets_caption_but_no_invented_credit(self):
        html = render("![A museum photo](https://example.org/photo.jpg)")
        assert "A museum photo" in html
        assert "youtube.com" not in html
        assert "watch the source" not in html

    def test_image_without_alt_gets_no_empty_caption(self):
        html = render("![](https://example.org/photo.jpg)")
        assert "<figure" in html
        assert "figcaption" not in html


class TestUntouched:
    def test_image_inside_a_sentence_stays_in_the_sentence(self):
        html = render("Ein Satz mit ![inline](/x.png) mittendrin.")
        assert "<figure" not in html
        assert "mittendrin" in html

    def test_plain_paragraphs_are_unaffected(self):
        html = render("Nur Text.\n\nZweiter Absatz.")
        assert "<figure" not in html
        assert html.count("<p>") == 2


class TestHeadingAnchors:
    """
    h2/h3 need ids so a table of contents can link to them. Python-Markdown's
    toc extension writes them and nh3 strips them again (id is not on its
    allowlist), so they are added back after sanitizing.
    """

    def test_headings_get_a_slug_id(self):
        html = render("## Baalbek monolith & the quarry\n\n### Sources")
        assert '<h2 id="baalbek-monolith-the-quarry">' in html
        assert '<h3 id="sources">' in html

    def test_heading_text_survives_unchanged(self):
        html = render("## Baalbek monolith & the quarry")
        assert "Baalbek monolith &amp; the quarry</h2>" in html

    def test_markup_inside_a_heading_does_not_land_in_the_id(self):
        html = render("## The *big* stone")
        assert '<h2 id="the-big-stone">' in html
        assert "<em>big</em>" in html

    def test_heading_without_sluggable_text_keeps_no_id(self):
        html = render("## ###")
        assert "id=" not in html


class TestSafety:
    """
    The caption is the one place where an attribute value becomes element
    content. nh3 leaves "<script>" unescaped INSIDE an attribute — inert
    there, live in a caption — so the alt has to be escaped on the way out.
    These assert on the caption, not on the whole document: the img tag
    legitimately keeps nh3's own escaping.
    """

    @staticmethod
    def caption(html: str) -> str:
        match = re.search(r'<figcaption class="article-figcaption">(.*?)</figcaption>', html, re.S)
        return match.group(1) if match else ""

    def test_markup_in_alt_lands_in_the_caption_escaped(self):
        # No ">" in this alt, so it survives the img-tag regex — exactly the
        # case that would have injected a live tag into the caption.
        html = render("![<img src=x onerror=alert(1)](/data/news/screenshots/abcdefghijk_1.webp)")
        caption = self.caption(html)
        assert caption, "die Figure muss entstehen, sonst testet der Fall nichts"
        assert "<img" not in caption
        assert "&lt;img" in caption

    def test_quote_in_alt_cannot_break_out_of_the_caption(self):
        html = render('![evil" onerror="alert(1)](/data/news/screenshots/abcdefghijk_1.webp)')
        caption = self.caption(html)
        assert "&quot;" in caption or "&#x27;" in caption
        assert 'onerror="' not in caption

    def test_entities_are_not_double_escaped(self):
        html = render("![Fläche &amp; Fundstelle](/data/news/screenshots/abcdefghijk_1.webp)")
        assert "&amp;amp;" not in self.caption(html)

    def test_only_a_real_video_id_produces_a_link(self):
        # Eleven chars is the YouTube id length; anything else is not one.
        html = render("![x](/data/news/screenshots/short_1.webp)")
        assert "youtube.com" not in html
