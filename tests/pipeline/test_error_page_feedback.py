# SPDX-License-Identifier: AGPL-3.0-only
"""The 404 page reports itself (event `not_found`, the input of the dashboard's
"Toter Link" problem) and asks what the visitor was looking for (feedback event
`not_found`); the 410 page does neither — there is nothing to look for."""

from __future__ import annotations

from pipeline.article_html_renderer import render_error_html


def test_404_page_carries_the_feedback_form():
    html = render_error_html("Page")
    assert "What were you looking for?" in html
    assert "umami.track('feedback'" in html
    assert "prompt:'not_found'" in html
    assert 'maxlength="100"' in html


def test_404_page_reports_itself_once_per_view():
    """SQL_NOT_FOUND groups these events by path and referrer host — a 404 that
    nobody types into is invisible otherwise."""
    html = render_error_html("Page")
    assert "umami.track('not_found'" in html
    assert "path: location.pathname" in html
    # The referrer is clipped to its host: no query strings, no deep paths.
    assert "document.referrer.split('/')[2]" in html
    # Fired on load: /pulse.js is deferred, so window.umami does not exist yet
    # while this inline script runs.
    assert "addEventListener('load'" in html


def test_410_page_has_no_feedback_form():
    html = render_error_html("Story", code=410)
    assert "What were you looking for?" not in html
    assert "umami.track" not in html
