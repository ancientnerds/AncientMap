"""Payload builders for GET /home (landing-live sections, 2026-09-09).

DB-less: fetch_landing_data is patched out. The field names asserted here
are the contract anRoute.ts::LandingRoute declares.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from api.routes import landing_html
from api.routes.landing_html import apply_stats, sites_compact, sites_long
from pipeline.database import get_db

# The three hero markers apply_stats() insists on; a shell without them raises.
_SHELL_MARKERS = (
    '<div data-stat="sites">1.7M+</div><span data-stat="sites-long">1.7 million</span>'
    '<div data-stat="countries">90+</div>'
)


def test_number_formats():
    assert sites_compact(1_759_673) == "1.76M"
    assert sites_compact(999_999) == "999K"
    assert sites_long(1_759_673) == "1.7 million"


def test_apply_stats_replaces_only_marked_values():
    html = (
        '<div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div class="hero-stat-value">30+</div>'
    )
    out = apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    assert 'data-stat="sites">1.76M<' in out
    assert 'data-stat="sites-long">1.7 million<' in out
    assert 'data-stat="countries">98<' in out
    assert '<div class="hero-stat-value">30+</div>' in out


def test_apply_stats_replaces_every_occurrence_of_a_marker():
    html = _SHELL_MARKERS + '<b data-stat="countries">90+</b>'
    out = apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    assert out.count(">98<") == 2


def test_apply_stats_raises_when_the_shell_lost_a_marker():
    """A missing marker is a broken shell, not a cosmetic miss — the hero would
    ship the hard-coded "90+" forever. Same standard as render_app_shell()
    refusing a shell without #root."""
    html = '<div data-stat="sites">1.7M+</div><span data-stat="sites-long">1.7 million</span>'
    try:
        apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    except ValueError as exc:
        assert 'data-stat="countries"' in str(exc)
    else:
        raise AssertionError("apply_stats accepted a shell without the countries marker")


def _landing_data():
    return {
        "paper_total": 24,
        "journal_total": 23,
        "news_stats": {"total_items": 3189, "total_articles": 23},
    }


def test_home_route_hands_the_landing_payload_and_substitutes_hero_counts():
    landing_html._cache.clear()
    # render_app_shell is mocked, so the "injected" body is part of the fake shell
    shell = (
        '<html><div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div id="root"><p>live</p></div></html>'
    )
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()),
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 1_759_673, "curated_countries": 98}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12}})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")) as render,
        patch("api.seo_shell.render_app_shell", return_value=shell),
    ):
        resp = asyncio.run(landing_html.home(db=object()))

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=300"
    body = resp.body.decode()
    assert 'data-stat="sites">1.76M<' in body and "<p>live</p>" in body
    assert 'data-stat="countries">98<' in body

    route = render.call_args[0][0]
    assert route["type"] == "landing"
    assert route["stats"] == {"sites": 1_759_673, "stories": 3189, "journals": 23, "papers": 24}
    # Stories and journals are their portal and a count — the live page lists
    # itself, so no row of either ships any more.
    assert set(route) == {"type", "stats", "journals", "papers"}
    assert route["journals"] == {"total": 23}
    # Papers is a count and the agent line, nothing else: the cards live on
    # /research/ and the homepage shows them through its portal.
    assert route["papers"] == {
        "total": 24,
        "theo": {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12},
    }


def test_home_route_omits_sections_without_rows_and_serves_from_cache():
    landing_html._cache.clear()
    data = _landing_data()
    data.update(paper_total=0, journal_total=0)
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=data) as fetch,
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 5, "curated_countries": 1}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "")) as render,
        patch("api.seo_shell.render_app_shell", return_value=_SHELL_MARKERS + '<div id="root"></div>'),
    ):
        asyncio.run(landing_html.home(db=object()))
        asyncio.run(landing_html.home(db=object()))

    route = render.call_args[0][0]
    assert route["journals"] is None and route["papers"] is None
    assert fetch.call_count == 1  # second call came from the 300 s cache


def test_home_stays_decodable_when_the_client_accepts_gzip():
    """Two gzip-negotiated hits must decode identically.

    Caching the Response object breaks that: GZipMiddleware sets
    Content-Encoding on the very `raw_headers` list the Response carries, so
    the cached object came back on hit two already labelled gzip — and the
    middleware then passed the uncompressed body through untouched
    (`content_encoding_set`), which is ERR_CONTENT_DECODING_FAILED in the
    browser. The cache holds bytes for exactly this reason.
    """
    landing_html._cache.clear()
    shell = "<html>" + _SHELL_MARKERS + '<div id="root">' + "<p>live</p>" * 60 + "</div></html>"
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.include_router(landing_html.router)
    app.dependency_overrides[get_db] = lambda: object()
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()) as fetch,
        patch.object(
            landing_html,
            "get_site_stats",
            return_value={"total_sites": 1_759_673, "curated_countries": 98},
        ),
        patch.object(
            landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})
        ),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")),
        patch("api.seo_shell.render_app_shell", return_value=shell),
        TestClient(app) as client,
    ):
        first = client.get("/home", headers={"Accept-Encoding": "gzip"})
        second = client.get("/home", headers={"Accept-Encoding": "gzip"})

    assert first.status_code == 200 and second.status_code == 200
    assert fetch.call_count == 1  # hit two really is the cached document
    assert first.text == second.text
    assert '<div id="root">' in second.text and "<p>live</p>" in second.text


def test_home_answers_head_from_the_cache_without_a_body():
    landing_html._cache.clear()
    landing_html._cache["home"] = (time.monotonic() + 300, b"<html>cached</html>")
    app = FastAPI()
    app.include_router(landing_html.router)
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    head = client.head("/home")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["cache-control"] == "public, max-age=300"
    assert client.get("/home").text == "<html>cached</html>"
