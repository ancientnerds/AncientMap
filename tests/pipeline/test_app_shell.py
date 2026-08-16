# SPDX-License-Identifier: AGPL-3.0-only
"""
Indexed pages are served as the real app shell, not a separate bare page.

Before this, /news-archive/{slug} and friends returned standalone HTML with
their own markup and no app bundle: no header, no navigation, none of the
site's styling. These tests pin the splice — one <title>, the built asset
tags preserved, content inside #root, and window.__AN_ROUTE__ present.
"""

import re

import pytest

from pipeline import app_shell

SHELL = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Story Archive | Ancient Nerds</title>
    <meta name="description" content="placeholder" />
    <meta property="og:title" content="placeholder" />
    <meta property="og:image" content="https://ancientnerds.com/landing/og-image.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <link rel="canonical" href="https://ancientnerds.com/articles.html" />
    <link rel="stylesheet" href="/assets/story-abc123.css" />
  </head>
  <body>
    <noscript>
      <div style="min-height: 100vh;">
        <h1>Archaeological Site Detail - Ancient Nerds</h1>
        <p>View detailed information about archaeological sites worldwide.</p>
      </div>
    </noscript>
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


class TestCanonical:
    """Every indexed document must carry exactly one canonical.

    articles.html and research.html ship their own; until 2026-08-09 the
    splice left it in place, so /articles/{slug} served two canonicals — the
    first pointing at /articles.html (verified on prod).
    """

    def test_only_the_page_canonical_survives(self, shell_dir):
        html = _render(head='<link rel="canonical" href="https://ancientnerds.com/articles/x">')
        assert html.count('rel="canonical"') == 1
        assert "/articles.html" not in html

    def test_the_stylesheet_link_is_untouched(self, shell_dir):
        """The rule must not eat every <link>."""
        assert "/assets/story-abc123.css" in _render()


class TestNoscriptFallback:
    """The shell's no-JS stand-in must not outrank the real content.

    Live on prod until 2026-08-09: every indexed page opened with the
    shell's boilerplate <h1> ("Archaeological Site Detail - Ancient
    Nerds"), and its min-height:100vh wrapper pushed the server-rendered
    content a full viewport below the fold without JavaScript.
    """

    def test_placeholder_h1_is_gone(self, shell_dir):
        html = _render(root="<h1>Archaeological Sites in England</h1>")
        assert "Archaeological Site Detail - Ancient Nerds" not in html
        assert re.findall(r"<h1[^>]*>(.*?)</h1>", html) == ["Archaeological Sites in England"]

    def test_noscript_block_is_removed_entirely(self, shell_dir):
        html = _render()
        assert "<noscript>" not in html
        assert "min-height: 100vh" not in html

    def test_real_content_and_assets_survive(self, shell_dir):
        html = _render(root="<p>content</p>")
        assert '<div id="root"><p>content</p></div>' in html
        assert "/assets/story-def456.js" in html
