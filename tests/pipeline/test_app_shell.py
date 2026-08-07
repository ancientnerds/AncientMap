# SPDX-License-Identifier: AGPL-3.0-only
"""
Indexed pages are served as the real app shell, not a separate bare page.

Before this, /news-archive/{slug} and friends returned standalone HTML with
their own markup and no app bundle: no header, no navigation, none of the
site's styling. These tests pin the splice — one <title>, the built asset
tags preserved, content inside #root, and window.__AN_ROUTE__ present.
"""

import json
import re
from datetime import datetime

import pytest

from pipeline import app_shell, seo_pages

SHELL = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Story Archive | Ancient Nerds</title>
    <meta name="description" content="placeholder" />
    <meta property="og:title" content="placeholder" />
    <meta property="og:image" content="https://ancientnerds.com/landing/og-image.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <link rel="stylesheet" href="/assets/story-abc123.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/assets/story-def456.js"></script>
  </body>
</html>"""


@pytest.fixture
def shell_dir(tmp_path, monkeypatch):
    (tmp_path / "story.html").write_text(SHELL, encoding="utf-8")
    monkeypatch.setattr(app_shell, "FRONTEND_DIR", tmp_path)
    app_shell._cache.clear()
    return tmp_path


def _render(**kw):
    return app_shell.render_app_shell(
        "story.html",
        head_html=kw.get("head", "<title>New</title>"),
        root_html=kw.get("root", "<p>content</p>"),
        route=kw.get("route", '{"type":"story"}'),
    )


def test_built_asset_tags_survive(shell_dir):
    html = _render()
    assert "/assets/story-def456.js" in html
    assert "/assets/story-abc123.css" in html


def test_content_lands_inside_root(shell_dir):
    html = _render(root="<p>hello</p>")
    assert '<div id="root"><p>hello</p></div>' in html


def test_route_object_is_injected(shell_dir):
    html = _render(route='{"type":"story","id":7}')
    assert 'window.__AN_ROUTE__={"type":"story","id":7};' in html


def test_placeholder_head_tags_are_replaced_not_duplicated(shell_dir):
    """Two <title> or two og:title tags let the crawler pick the wrong one."""
    html = _render(head='<title>Real</title><meta property="og:title" content="Real">')
    assert html.count("<title>") == 1
    assert "Story Archive | Ancient Nerds" not in html
    assert html.count('property="og:title"') == 1
    assert 'content="placeholder"' not in html


def test_missing_shell_fails_loudly(tmp_path, monkeypatch):
    """A missing build is a broken deploy — it must not degrade silently."""
    monkeypatch.setattr(app_shell, "FRONTEND_DIR", tmp_path)
    app_shell._cache.clear()
    with pytest.raises(app_shell.ShellUnavailableError, match="missing"):
        _render()


def test_shell_is_reread_when_the_build_changes(shell_dir):
    assert "/assets/story-def456.js" in _render()
    (shell_dir / "story.html").write_text(
        SHELL.replace("story-def456.js", "story-rebuilt-999999.js"), encoding="utf-8"
    )
    assert "/assets/story-rebuilt-999999.js" in _render()
    assert "/assets/story-def456.js" not in _render()


# --- fragments -------------------------------------------------------------


def _story(**over):
    base = {
        "id": 42,
        "headline": "Cyclopean walls found",
        "summary": "A survey.",
        "facts": ["One", "Two"],
        "post_text": "First line.\nSecond line.",
        "screenshot_url": "/data/news/shot.jpg",
        "youtube_url": "https://youtube.com/watch?v=abc",
        "video_title": "The video",
        "channel_name": "A Channel",
        "published_at": datetime(2026, 7, 1),
        "news_category": "excavation",
        "site_name": "Aartswoud",
        "site_id": "383a0107-b7f7-4431-a752-590f3c0a42b2",
        "site_country": "Netherlands",
    }
    base.update(over)
    return base


def test_story_page_shows_the_video_snapshot():
    """The screenshot existed in the data but was only ever an og:image."""
    page = seo_pages.story_page(_story())
    assert "/data/news/shot.jpg" in page.body
    assert "youtube.com/watch?v=abc" in page.body
    route = json.loads(page.route)
    assert route["screenshotUrl"].endswith("/data/news/shot.jpg")
    assert route["youtubeUrl"] == "https://youtube.com/watch?v=abc"


def test_story_payload_lets_react_render_without_a_fetch():
    route = json.loads(seo_pages.story_page(_story()).route)
    assert route["type"] == "story"
    assert route["headline"] == "Cyclopean walls found"
    assert route["facts"] == ["One", "Two"]
    assert route["postText"].startswith("First line.")


def test_story_links_to_the_canonical_site_url():
    page = seo_pages.story_page(_story())
    assert "/sites/netherlands/aartswoud-383a0107" in page.body


def test_story_without_a_linked_site_still_renders():
    page = seo_pages.story_page(_story(site_id="", site_country="", site_name=""))
    assert "<h1>" in page.body or "Cyclopean" in page.body


def test_route_json_cannot_break_out_of_the_script_tag():
    """A headline containing </script> would otherwise end the inline script."""
    page = seo_pages.story_page(_story(headline="</script><script>alert(1)</script>"))
    assert "</script><script>alert(1)" not in page.route
    assert "\\u003c/script>" in page.route or "\\u003c" in page.route
    json.loads(page.route)


def test_story_entry_is_the_story_shell():
    assert seo_pages.story_page(_story()).entry == "story.html"


def test_archive_carries_its_listing():
    page = seo_pages.story_archive_page(
        [{"slug": "a-1", "headline": "A", "summary": "s"}], page=1, total_pages=3, total=120
    )
    route = json.loads(page.route)
    assert route["type"] == "storyArchive"
    assert route["totalPages"] == 3
    assert route["stories"][0]["slug"] == "a-1"
    assert "/news-archive/a-1" in page.body


def test_ai_notice_on_generated_pages_but_not_on_curated_sites():
    """Art. 50 applies to the AI-written text, not to human-curated site records."""
    from pipeline.article_html_renderer import AI_NOTICE_HTML

    assert AI_NOTICE_HTML in seo_pages.story_page(_story()).body

    site = {
        "id": "383a0107-b7f7-4431-a752-590f3c0a42b2",
        "name": "Aartswoud",
        "country": "Netherlands",
        "site_type": "Settlement",
        "period_name": "3000 BC",
        "description": "A settlement.",
        "lat": 52.7,
        "lon": 4.98,
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


def test_site_page_links_to_the_globe_with_the_site_preselected():
    site = {
        "id": "383a0107-b7f7-4431-a752-590f3c0a42b2",
        "name": "Aartswoud",
        "country": "Netherlands",
        "site_type": "Settlement",
        "period_name": "3000 BC",
        "description": "A settlement.",
        "lat": 52.7,
        "lon": 4.98,
    }
    empty = {
        "alt_names": [],
        "image": None,
        "news": [],
        "links": [],
        "parent": None,
        "siblings": [],
    }
    body = seo_pages.site_detail_page(site, empty).body
    assert "/globe.html?site=383a0107-b7f7-4431-a752-590f3c0a42b2" in body


@pytest.mark.parametrize(
    ("make", "expected_entry"),
    [
        (lambda: seo_pages.story_archive_page([], 1, 1, 0), "story.html"),
        (lambda: seo_pages.sites_index_page([]), "site.html"),
        (lambda: seo_pages.country_sites_page("Malta", []), "site.html"),
        (lambda: seo_pages.research_index_page([]), "research.html"),
        (lambda: seo_pages.article_index_page([]), "articles.html"),
    ],
)
def test_every_listing_targets_a_real_vite_entry(make, expected_entry):
    page = make()
    assert page.entry == expected_entry
    json.loads(page.route)
    assert re.search(r"<title>.*?</title>", page.head)


def test_research_page_accepts_an_iso_string_date():
    """paper_summary_kwargs() serialises published_at to a string, not a datetime.

    Calling .strftime() on it 500'd every /research/{slug} page in production
    (2026-08-07).
    """
    paper = {
        "title": "A Paper",
        "slug": "a-paper",
        "summary": "Abstract.",
        "author": "Theo",
        "published_at": "2026-07-01T12:00:00",
    }
    page = seo_pages.research_page(paper, "<p>body</p>")
    assert "2026-07-01" in page.body
    assert '"datePublished": "2026-07-01"' in page.head


def test_research_page_still_accepts_a_datetime():
    paper = {
        "title": "A Paper",
        "slug": "a-paper",
        "summary": "Abstract.",
        "author": "Theo",
        "published_at": datetime(2026, 7, 1),
    }
    assert "2026-07-01" in seo_pages.research_page(paper, "<p>body</p>").body


def test_article_page_accepts_both_date_forms():
    for value in ("2026-07-01T00:00:00", datetime(2026, 7, 1)):
        page = seo_pages.article_page(
            {"title": "T", "slug": "t", "summary": "s", "published_at": value}, "<p>b</p>"
        )
        assert "2026-07-01" in page.body


def test_story_page_accepts_an_iso_string_date():
    page = seo_pages.story_page(_story(published_at="2026-07-01T00:00:00"))
    assert "2026-07-01" in page.body
