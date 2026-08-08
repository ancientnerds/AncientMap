# SPDX-License-Identifier: AGPL-3.0-only
"""Story-page extras added 2026-08-08.

Three kinds of data sat in news_items for months without ever reaching the
page: the researched web sources, the video offset, and the pipeline's own
speculative label. Plus the palette: these pages rendered links in Material
blue, a colour that appears nowhere in the design system.
"""

from __future__ import annotations

from pipeline import seo_pages


def _story(**over) -> dict:
    base = {
        "id": 6895,
        "headline": "Sanskrit texts describe explosive weapons",
        "summary": "A summary.",
        "post_text": "Body paragraph.",
        "facts": ["Fact one"],
        "site_name": "Mohenjo-daro",
        "site_id": "abc12345-0000-0000-0000-000000000000",
        "site_country": "Pakistan",
        "youtube_url": "https://www.youtube.com/watch?v=XYZ",
        "published_at": "2026-07-01T00:00:00",
        "news_category": "artifact",
    }
    base.update(over)
    return base


class TestSources:
    def test_web_sources_are_rendered(self):
        body = seo_pages.story_page(
            _story(
                web_sources=[
                    {
                        "url": "https://www.wisdomlib.org/x",
                        "title": "Astras in the Mahabharata",
                        "snippet": "The word astra literally means a missile.",
                    }
                ]
            )
        ).body
        assert "<h2>Sources</h2>" in body
        assert "Astras in the Mahabharata" in body
        assert "wisdomlib.org" in body  # bare host helps readers judge a link
        assert "literally means a missile" in body

    def test_non_http_sources_are_dropped(self):
        """web_sources is LLM-derived — a javascript: URL must never render."""
        body = seo_pages.story_page(
            _story(web_sources=[{"url": "javascript:alert(1)", "title": "evil"}])
        ).body
        assert "javascript:" not in body
        assert "<h2>Sources</h2>" not in body  # nothing valid left to show

    def test_missing_title_falls_back_to_host(self):
        body = seo_pages.story_page(
            _story(web_sources=[{"url": "http://ok.example/y", "title": ""}])
        ).body
        assert "ok.example" in body

    def test_no_sources_renders_no_section(self):
        assert "<h2>Sources</h2>" not in seo_pages.story_page(_story()).body


class TestSiteLinks:
    def test_site_links_to_detail_page_and_globe(self):
        body = seo_pages.story_page(_story()).body
        assert "/globe.html?site=abc12345-0000-0000-0000-000000000000" in body
        assert "/sites/pakistan/" in body.lower()

    def test_site_without_id_stays_plain_text(self):
        """A name the matcher never resolved must not fake a link."""
        body = seo_pages.story_page(_story(site_id="", site_country="")).body
        assert "Mohenjo-daro" in body
        assert "/globe.html?site=" not in body


class TestVideoDeepLink:
    def test_timestamp_offset_is_appended(self):
        body = seo_pages.story_page(_story(timestamp_seconds=754)).body
        assert "&amp;t=754s" in body  # HTML-escaped inside the href attribute

    def test_zero_or_missing_offset_links_to_the_video_start(self):
        for offset in (None, 0, "not-an-int"):
            body = seo_pages.story_page(_story(timestamp_seconds=offset)).body
            assert "t=" not in body.replace("target=", "")


class TestSpeculativeBadge:
    def test_tag_is_shown_next_to_the_headline(self):
        body = seo_pages.story_page(_story(speculative_tag="speculative")).body
        assert 'an-badge">speculative' in body

    def test_untagged_story_has_no_badge(self):
        assert "an-badge" not in seo_pages.story_page(_story()).body


class TestPalette:
    def test_links_use_the_design_system_colours(self):
        css = seo_pages.SSR_CSS
        assert "a{color:#00c8c8" in css  # --text-link (cyan-500)
        assert "#00cc66" in css  # --accent-primary (green-bright)

    def test_material_blue_is_gone_from_the_rules(self):
        """It survives only in the comment that records why it left."""
        import re

        rules = re.sub(r"/\*.*?\*/", "", seo_pages.SSR_CSS, flags=re.DOTALL)
        assert "4fc3f7" not in rules
        assert "4fc3f7" in seo_pages.SSR_CSS  # the explanatory note stays


class TestArchiveCards:
    """The listing query already joins video + site; the cards used to drop
    both and render title-plus-blurb only, so every entry looked the same."""

    def _cards(self, **over) -> str:
        story = {
            "slug": "sanskrit-weapons-6895",
            "headline": "Sanskrit texts describe explosive weapons",
            "summary": "A summary of the story.",
            "published_at": "2026-07-01T00:00:00",
            "news_category": "artifact",
            "site_name": "Mohenjo-daro",
            "channel_name": "Ancient Architects",
        }
        story.update(over)
        return seo_pages.story_archive_page([story], page=1, total_pages=1, total=1).body

    def test_card_shows_date_category_site_and_channel(self):
        body = self._cards()
        assert "July 01, 2026" in body
        assert "artifact" in body
        assert "Mohenjo-daro" in body
        assert "via Ancient Architects" in body

    def test_card_links_to_the_story(self):
        assert "/news-archive/sanskrit-weapons-6895" in self._cards()

    def test_sparse_story_renders_without_a_meta_line(self):
        body = self._cards(published_at=None, news_category=None, site_name="", channel_name="")
        assert "an-card-meta" not in body
        assert "Sanskrit texts describe explosive weapons" in body

    def test_speculative_tag_marks_the_card(self):
        assert 'an-badge">speculative' in self._cards(speculative_tag="speculative")
