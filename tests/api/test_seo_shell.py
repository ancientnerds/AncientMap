# SPDX-License-Identifier: AGPL-3.0-only
"""ssr_shell_response() spliced die SSR-Ausgabe in die gebaute Shell (react-ssr Task 9).

Seit Task 16 der einzige Weg: die alte shell_response(SeoPage, headers)
starb zusammen mit pipeline/seo_pages.py.
"""

from __future__ import annotations

from api import seo_shell


def test_splices_ssr_output(monkeypatch):
    monkeypatch.setattr(seo_shell, "render_page", lambda route: ("<title>T</title>", "<p>B</p>"))
    monkeypatch.setattr(
        seo_shell,
        "render_app_shell",
        lambda entry, **kw: f"{entry}|{kw['head_html']}|{kw['root_html']}",
    )
    resp = seo_shell.ssr_shell_response(
        "site.html",
        {"type": "sitesIndex", "countries": []},
        {"Cache-Control": "public, max-age=3600"},
    )
    assert resp.body.decode() == "site.html|<title>T</title>|<p>B</p>"
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["cache-control"] == "public, max-age=3600"


def test_route_json_cannot_break_out_of_the_script_tag(monkeypatch):
    """Wie seo_pages._route_json(): '<' wird zu \\u003c maskiert, non-ASCII bleibt."""
    captured: dict = {}

    def fake_shell(entry, **kw):
        captured.update(kw)
        return "x"

    monkeypatch.setattr(seo_shell, "render_page", lambda route: ("<t></t>", "<p></p>"))
    monkeypatch.setattr(seo_shell, "render_app_shell", fake_shell)

    seo_shell.ssr_shell_response(
        "story.html", {"type": "story", "headline": "</script><b>", "country": "Türkiye"}, {}
    )
    assert "</script>" not in captured["route"]
    assert "\\u003c/script>" in captured["route"]
    assert "Türkiye" in captured["route"]  # ensure_ascii=False, wie bisher


def test_ssr_failure_propagates_loudly(monkeypatch):
    """Kein Fallback auf den Python-Renderer — der 502-Handler in main.py übernimmt."""
    import pytest

    from api.ssr_client import SsrUnavailableError

    def boom(route):
        raise SsrUnavailableError("SSR service unreachable")

    monkeypatch.setattr(seo_shell, "render_page", boom)
    with pytest.raises(SsrUnavailableError):
        seo_shell.ssr_shell_response("site.html", {"type": "sitesIndex", "countries": []}, {})
