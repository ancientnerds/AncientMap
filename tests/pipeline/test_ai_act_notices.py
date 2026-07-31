# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50 EU AI Act: visible AI notices on server-rendered content pages."""

from datetime import datetime

from pipeline.article_html_renderer import (
    AI_NOTICE_HTML,
    render_article_html,
    render_article_listing_html,
    render_news_archive_html,
    render_story_html,
)


def _story() -> dict:
    return {
        "id": 1,
        "headline": "Test Discovery",
        "summary": "A summary.",
        "post_text": "Body paragraph one.\nBody paragraph two.",
        "facts": [],
        "site_name": None,
        "site_id": None,
        "youtube_url": None,
        "channel_name": None,
        "video_title": None,
        "news_category": None,
        "created_at": datetime(2026, 7, 1),
        "published_at": datetime(2026, 7, 1),
        "screenshot_url": None,
    }


def test_ai_notice_constant_is_explicit():
    assert "AI-generated" in AI_NOTICE_HTML
    assert 'data-ai-generated="true"' in AI_NOTICE_HTML


def test_article_page_has_ai_notice():
    html = render_article_html(
        title="Test Journal",
        content_md="Hello **world**",
        summary="Sum",
        published_at=datetime(2026, 7, 1),
        week_start=datetime(2026, 6, 22),
        week_end=datetime(2026, 6, 28),
        slug="test-journal",
    )
    assert AI_NOTICE_HTML in html


def test_story_page_has_ai_notice():
    assert AI_NOTICE_HTML in render_story_html(_story())


def test_news_archive_listing_has_ai_notice():
    html = render_news_archive_html(
        [("July 30, 2026", [_story()])], total_count=1, page=1, total_pages=1
    )
    assert AI_NOTICE_HTML in html


def test_article_listing_has_ai_notice():
    html = render_article_listing_html(
        [
            {
                "title": "Test Journal",
                "summary": "Sum",
                "slug": "test-journal",
                "published_at": "2026-07-01",
                "week_start": datetime(2026, 6, 22),
                "week_end": datetime(2026, 6, 28),
            }
        ]
    )
    assert AI_NOTICE_HTML in html
