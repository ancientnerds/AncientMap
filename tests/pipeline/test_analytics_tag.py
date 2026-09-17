# SPDX-License-Identifier: AGPL-3.0-only
"""Umami tracker tag — one markup in two places.

vite.config.ts (analyticsTag) puts the tag into every built entry, and with it
into every server-rendered page; pipeline/article_html_renderer.py
(analytics_tag) puts the same tag into the Python-rendered error pages. Both
only when VITE_UMAMI_WEBSITE_ID is set, so dev and local builds stay
untracked.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.article_html_renderer import analytics_tag, render_error_html

_VITE_CONFIG = Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "vite.config.ts"
_TAG_PREFIX = '<script defer src="/pulse.js" data-website-id="'
_TAG_SUFFIX = '" data-do-not-track="true"></script>'


def test_ohne_website_id_kein_tag(monkeypatch):
    monkeypatch.delenv("VITE_UMAMI_WEBSITE_ID", raising=False)
    assert analytics_tag() == ""
    assert "pulse.js" not in render_error_html("Page")


def test_mit_website_id_steht_der_tag_im_head_der_fehlerseite(monkeypatch):
    monkeypatch.setenv("VITE_UMAMI_WEBSITE_ID", "3d0c1a2b-1111-4222-8333-444455556666")
    tag = analytics_tag()
    assert tag == f"{_TAG_PREFIX}3d0c1a2b-1111-4222-8333-444455556666{_TAG_SUFFIX}"
    html = render_error_html("Page")
    head = html.split("</head>")[0]
    assert tag in head


def test_website_id_wird_html_escaped(monkeypatch):
    monkeypatch.setenv("VITE_UMAMI_WEBSITE_ID", 'x"><script>alert(1)</script>')
    assert "<script>alert" not in analytics_tag()


def test_vite_plugin_schreibt_denselben_tag():
    source = _VITE_CONFIG.read_text(encoding="utf-8")
    assert "function analyticsTag(" in source
    assert _TAG_PREFIX + "${websiteId}" + _TAG_SUFFIX in source
    assert "VITE_UMAMI_WEBSITE_ID" in source
