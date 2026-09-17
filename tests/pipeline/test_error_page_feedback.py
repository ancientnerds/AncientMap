# SPDX-License-Identifier: AGPL-3.0-only
"""The 404 page asks what the visitor was looking for (feedback event
`not_found`); the 410 page does not — there is nothing to look for."""

from __future__ import annotations

from pipeline.article_html_renderer import render_error_html


def test_404_page_carries_the_feedback_form():
    html = render_error_html("Page")
    assert "What were you looking for?" in html
    assert "umami.track('feedback'" in html
    assert "prompt:'not_found'" in html
    assert 'maxlength="100"' in html


def test_410_page_has_no_feedback_form():
    html = render_error_html("Story", code=410)
    assert "What were you looking for?" not in html
    assert "umami.track" not in html
