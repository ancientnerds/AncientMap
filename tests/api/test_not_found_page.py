# SPDX-License-Identifier: AGPL-3.0-only
"""GET /not-found — the answer for every path no other location serves.

Until 2026-09-17 nginx's `location /` fell back to index.html, so a mistyped
or retired URL (/seo/site/…, /definitely-not-a-page) answered 200 with the
homepage shell — a soft 404 for each of them. try_files now hands those
requests to this route (location @not_found), which must be an honest 404
that stays out of the index.

DB-less: the route takes no session.
"""

from __future__ import annotations

import asyncio

from api.routes import landing_html as lh


def _call():
    return asyncio.run(lh.not_found_page())


def test_antwortet_404_mit_html():
    resp = _call()
    assert resp.status_code == 404
    assert resp.media_type == "text/html"


def test_seite_ist_die_fehlerseite_und_noindex():
    body = _call().body.decode()
    assert "<title>Page Not Found | Ancient Nerds</title>" in body
    assert '<meta name="robots" content="noindex">' in body
    assert 'href="/"' in body


def test_kurz_cachebar_wie_die_anderen_404_seiten():
    assert _call().headers["cache-control"] == "public, max-age=300"
