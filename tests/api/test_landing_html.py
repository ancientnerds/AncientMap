"""Payload builders for GET /home (landing-live sections, 2026-09-09).

DB-less: fetch_landing_data is patched out. The field names asserted here
are the contract anRoute.ts::LandingRoute declares.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

import pytest
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
# What get_site_stats() hands the route; by_source is the /api/stats map.
_SITE_STATS = {
    "total_sites": 1_759_673,
    "by_source": {"ancient_nerds": 5004, "pleiades": 13780},
    "curated_countries": 98,
}
# The document's cache key under the fixed shell build the store fixture sets.
_KEY = "landing:home:build-1"


@pytest.fixture(autouse=True)
def store():
    """The Redis document cache as a dict, and a fixed shell build."""
    data: dict[str, bytes] = {}
    with (
        patch.object(landing_html, "entry_version", return_value="build-1"),
        patch.object(landing_html, "cache_get_bytes", side_effect=data.get),
        patch.object(
            landing_html, "cache_set_bytes", side_effect=lambda k, v, ttl: data.__setitem__(k, v)
        ),
        patch.object(landing_html, "cache_delete", side_effect=lambda k: data.pop(k, None)),
    ):
        yield data


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
        "latest_papers": [{"slug": "osiris-shaft", "title": "Water in the Osiris Shaft"}],
        "journal_total": 23,
        "news_stats": {"total_items": 3189, "total_articles": 23},
    }


def test_home_route_hands_the_landing_payload_and_substitutes_hero_counts():
    # render_app_shell is mocked, so the "injected" body is part of the fake shell
    shell = (
        '<html><div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div id="root"><p>live</p></div></html>'
    )
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()),
        patch.object(landing_html, "get_site_stats", return_value=_SITE_STATS),
        patch.object(
            landing_html,
            "get_current_research",
            new=AsyncMock(
                return_value={
                    "running": {
                        "question": "Osiris",
                        "started_at": "2026-09-09T06:00:00",
                        "sites_found": 12,
                    }
                }
            ),
        ),
        patch(
            "api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")
        ) as render,
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
    assert route["stats"] == {
        "sites": 1_759_673,
        "sources": 2,
        "stories": 3189,
        "journals": 23,
        "papers": 24,
    }
    # Stories and journals are their portal and a count — the live page lists
    # itself, so no row of either ships any more.
    assert set(route) == {"type", "stats", "journals", "papers"}
    assert route["journals"] == {"total": 23}
    # Papers is a count, the agent line and the newest titles as links: the cards
    # live on /research/, the titles give Google a path to a new paper.
    assert route["papers"] == {
        "total": 24,
        "theo": {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12},
        "latest": [{"slug": "osiris-shaft", "title": "Water in the Osiris Shaft"}],
    }


def test_home_route_omits_sections_without_rows_and_serves_from_cache():
    data = _landing_data()
    data.update(paper_total=0, journal_total=0)
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=data) as fetch,
        patch.object(
            landing_html,
            "get_site_stats",
            return_value={
                "total_sites": 5,
                "by_source": {"ancient_nerds": 5},
                "curated_countries": 1,
            },
        ),
        patch.object(
            landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})
        ),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "")) as render,
        patch(
            "api.seo_shell.render_app_shell", return_value=_SHELL_MARKERS + '<div id="root"></div>'
        ),
    ):
        asyncio.run(landing_html.home(db=object()))
        asyncio.run(landing_html.home(db=object()))

    route = render.call_args[0][0]
    assert route["journals"] is None and route["papers"] is None
    assert fetch.call_count == 1  # second call came from the cached document


def test_home_stays_decodable_when_the_client_accepts_gzip():
    """Two gzip-negotiated hits must decode identically.

    Caching the Response object breaks that: GZipMiddleware sets
    Content-Encoding on the very `raw_headers` list the Response carries, so
    the cached object came back on hit two already labelled gzip — and the
    middleware then passed the uncompressed body through untouched
    (`content_encoding_set`), which is ERR_CONTENT_DECODING_FAILED in the
    browser. The cache holds bytes for exactly this reason.
    """
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
            return_value=_SITE_STATS,
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


def test_home_answers_head_from_the_cache_without_a_body(store):
    store[_KEY] = landing_html._pack(time.time(), b"<html>cached</html>")
    app = FastAPI()
    app.include_router(landing_html.router)
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    head = client.head("/home")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["cache-control"] == "public, max-age=300"
    assert client.get("/home").text == "<html>cached</html>"


# --- The shared document cache (TTFB audit 2026-10-20) -----------------------
# Measured that day: 41 % of the browser requests for "/" waited for a rebuild
# of up to ~1 s, because each API process kept its own 300 s copy and rebuilt
# it inside the request. The copy is shared now and refreshed behind the reply.


def _patched_build(render):
    return (
        patch.object(landing_html, "_render_document", side_effect=render),
        patch.object(
            landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})
        ),
        patch.object(landing_html, "get_session", return_value=nullcontext(object())),
    )


async def _home_then_drain():
    resp = await landing_html.home(db=object())
    await asyncio.gather(*landing_html._refreshing)
    return resp


def test_a_stale_copy_is_served_at_once_and_rebuilt_behind_the_reply(store):
    store[_KEY] = landing_html._pack(time.time() - 301, b"<html>old</html>")
    a, b, c = _patched_build(lambda db, theo: b"<html>new</html>")
    with a as render, b, c:
        resp = asyncio.run(_home_then_drain())

    assert resp.body == b"<html>old</html>"  # the visitor did not wait for the build
    assert render.call_count == 1
    built_at, body = landing_html._unpack(store[_KEY])
    assert body == b"<html>new</html>" and time.time() - built_at < 5


def test_a_fresh_copy_triggers_no_rebuild(store):
    store[_KEY] = landing_html._pack(time.time() - 10, b"<html>fresh</html>")
    a, b, c = _patched_build(lambda db, theo: b"<html>new</html>")
    with a as render, b, c:
        resp = asyncio.run(_home_then_drain())

    assert resp.body == b"<html>fresh</html>"
    assert render.call_count == 0


def test_one_rebuild_per_process_however_many_requests_find_the_copy_stale(store):
    store[_KEY] = landing_html._pack(time.time() - 301, b"<html>old</html>")

    async def three_requests():
        replies = [await landing_html.home(db=object()) for _ in range(3)]
        await asyncio.gather(*landing_html._refreshing)
        return replies

    a, b, c = _patched_build(lambda db, theo: b"<html>new</html>")
    with a as render, b, c:
        replies = asyncio.run(three_requests())

    assert [r.body for r in replies] == [b"<html>old</html>"] * 3
    assert render.call_count == 1


def test_a_failed_background_rebuild_drops_the_copy(store):
    """Behind a broken build the next request must build, and fail, itself."""
    store[_KEY] = landing_html._pack(time.time() - 301, b"<html>old</html>")

    def broken(db, theo):
        raise RuntimeError("sidecar down")

    a, b, c = _patched_build(broken)
    with a, b, c:
        resp = asyncio.run(_home_then_drain())

    assert resp.body == b"<html>old</html>"
    assert _KEY not in store


def test_a_new_frontend_build_is_never_answered_with_the_old_document(store):
    store[_KEY] = landing_html._pack(time.time(), b"<html>build 1</html>")
    a, b, c = _patched_build(lambda db, theo: b"<html>build 2</html>")
    with (
        a as render,
        b,
        c,
        patch.object(landing_html, "entry_version", return_value="build-2"),
    ):
        resp = asyncio.run(_home_then_drain())

    assert resp.body == b"<html>build 2</html>"
    assert render.call_count == 1
    assert landing_html._unpack(store["landing:home:build-2"])[1] == b"<html>build 2</html>"


def test_the_build_runs_off_the_event_loop(store):
    threads = []

    def render(db, theo):
        threads.append(threading.get_ident())
        return b"<html>new</html>"

    a, b, c = _patched_build(render)
    with a, b, c:
        asyncio.run(_home_then_drain())

    assert threads and threads[0] != threading.get_ident()
