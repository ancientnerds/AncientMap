# SPDX-License-Identifier: AGPL-3.0-only
"""A withdrawn story's 410 page gives its visitor somewhere to go.

Measured 2026-10-01: 12 % of all story views (Umami) and 24 % of the Google
clicks on story pages (Search Console, 28 days) end on a withdrawn story's 410
page, and that page offered three generic links. The 410 status stays — it is
what makes Google drop the URL — but the person who arrives from a search
result now finds the archive search, the newest stories and the globe.
"""

from __future__ import annotations

from pipeline.article_html_renderer import render_error_html, story_recovery_html

LATEST = [
    ("sun-chariot-fragment-found-4711", "Sun Chariot fragment found"),
    ("trundholm-bog-survey-planned-4600", "Trundholm bog survey planned"),
]


def _page(latest=LATEST) -> str:
    return render_error_html(
        "Story",
        410,
        "This story has been withdrawn from the archive.",
        recovery_html=story_recovery_html(latest),
    )


def test_410_page_offers_the_archive_search_as_a_plain_get_form():
    html = _page()
    # /news-archive/?q= is server-rendered and works without JS; its q is
    # clipped to 100 characters (_render_news_archive_page).
    assert '<form class="nf-feedback" action="/news-archive/" method="get" role="search">' in html
    assert 'name="q"' in html
    assert 'maxlength="100"' in html


def test_410_page_links_the_newest_stories():
    html = _page()
    assert (
        '<a href="/news-archive/sun-chariot-fragment-found-4711">Sun Chariot fragment found</a>'
        in html
    )
    assert (
        '<a href="/news-archive/trundholm-bog-survey-planned-4600">Trundholm bog survey planned</a>'
        in html
    )


def test_410_page_links_the_globe_beyond_the_nav():
    assert 'class="nf-globe" href="/globe.html"' in _page()


def test_a_headline_cannot_inject_markup():
    html = _page([("x-1", '<script>alert(1)</script> & "quotes"')])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;quotes&quot;" in html


def test_without_stories_the_search_and_globe_remain():
    html = _page([])
    assert 'action="/news-archive/"' in html
    assert 'href="/globe.html"' in html
    assert "Latest stories" not in html


def test_410_page_stays_gone_and_unindexed_and_silent():
    html = _page()
    assert '<meta name="robots" content="noindex">' in html
    assert "<h1" in html and ">410</h1>" in html
    assert "This story has been withdrawn from the archive." in html
    # test_error_page_feedback pins the same: a 410 reports nothing.
    assert "umami.track" not in html


def test_other_error_pages_carry_no_recovery_block():
    for html in (
        render_error_html("Page"),
        render_error_html("Story"),
        render_error_html("Site", 410),
    ):
        assert "nf-latest" not in html
        assert 'role="search"' not in html
