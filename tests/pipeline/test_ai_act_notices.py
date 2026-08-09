# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50 EU AI Act: visible AI notices on server-rendered content pages.

Ported 2026-08-09 from the standalone renderers to pipeline/seo_pages.py.
render_article_html, render_story_html, render_news_archive_html and
render_article_listing_html were never served — nginx routes these URLs to
the app-shell splice — and only this file kept them alive. The obligation is
unchanged, so the assertions moved instead of disappearing.
"""

import json
import re
from datetime import datetime

from pipeline import seo_pages
from pipeline.article_html_renderer import AI_NOTICE_HTML


def _story(**over) -> dict:
    base = {
        "id": 1,
        "headline": "Test Discovery",
        "summary": "A summary.",
        "post_text": "Body paragraph one.\nBody paragraph two.",
        "facts": [],
        "published_at": datetime(2026, 7, 1),
    }
    base.update(over)
    return base


def _paper(**over) -> dict:
    base = {
        "title": "A paper",
        "slug": "a-paper",
        "summary": "An abstract.",
        "author": "Theo",
        "published_at": datetime(2026, 7, 1),
    }
    base.update(over)
    return base


def test_ai_notice_constant_is_explicit():
    assert "AI-generated" in AI_NOTICE_HTML
    assert 'data-ai-generated="true"' in AI_NOTICE_HTML


class TestNoticePresence:
    """Every AI-written page type carries the visible disclosure."""

    def test_story_page(self):
        assert AI_NOTICE_HTML in seo_pages.story_page(_story()).body

    def test_story_archive(self):
        assert AI_NOTICE_HTML in seo_pages.story_archive_page([], 1, 1, 0).body

    def test_article_page(self):
        assert AI_NOTICE_HTML in seo_pages.article_page(_paper(), "<p>Body.</p>").body

    def test_article_index(self):
        assert AI_NOTICE_HTML in seo_pages.article_index_page([]).body

    def test_research_page(self):
        assert AI_NOTICE_HTML in seo_pages.research_page(_paper(), "<p>Body.</p>").body

    def test_research_index(self):
        assert AI_NOTICE_HTML in seo_pages.research_index_page([]).body

    def test_curated_site_records_carry_no_notice(self):
        """Art. 50 covers the AI-written text, not human-curated site records."""
        site = {
            "id": "abc12345-0000-0000-0000-000000000000",
            "name": "Nemrut",
            "country": "Türkiye",
            "site_type": "Temple complex",
            "period_name": "500 BC - 1 AD",
            "description": "A place.",
            "lat": 1.0,
            "lon": 2.0,
        }
        empty = {
            "alt_names": [],
            "image": None,
            "news": [],
            "links": [],
            "parent": None,
            "siblings": [],
        }
        assert AI_NOTICE_HTML not in seo_pages.site_detail_page(site, empty).body


def _jsonld(head: str) -> dict:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', head, re.DOTALL)
    assert match, "no JSON-LD block found"
    return json.loads(match.group(1))


class TestResearchAuthorship:
    """Theo is a pipeline, not a person — the schema must not claim otherwise."""

    def test_theo_is_an_organization(self):
        head = seo_pages.research_page(_paper(), "<p>b</p>").head
        assert '"@type": "Person", "name": "Theo"' not in head
        assert "AI research pipeline" in head
        assert _jsonld(head)["author"]["@type"] == "Organization"

    def test_a_human_author_stays_a_person(self):
        head = seo_pages.research_page(_paper(author="MrSchneebly"), "<p>b</p>").head
        assert _jsonld(head)["author"]["@type"] == "Person"
        assert _jsonld(head)["author"]["name"] == "MrSchneebly"

    def test_a_quote_in_the_name_cannot_break_the_json(self):
        head = seo_pages.research_page(_paper(author='O"Brien'), "<p>b</p>").head
        assert _jsonld(head)["author"]["name"] == 'O"Brien'
