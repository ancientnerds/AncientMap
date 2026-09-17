# SPDX-License-Identifier: AGPL-3.0-only
"""/api/stats/* — die Daten des Founders-Dashboards hinter dem an_stats-Cookie.

DB-los: pipeline.umami_db.fetch wird am Routenmodul (fr.fetch) durch eine
Attrappe ersetzt, die je nach SQL-Text Zeilen liefert; das Cookie wird mit
einem Testschlüssel signiert wie in test_stats_access.py.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes import founders_stats as fr
from api.routes import stats_access as sa
from api.services import jwt_auth

SESSION = {"scope": "stats", "sub": "42", "name": "martin"}


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(jwt_auth, "SECRET_KEY", "k" * 40)


def _req(cookie: str | None = None) -> Request:
    headers = [(b"cookie", f"{sa.COOKIE_NAME}={cookie}".encode())] if cookie else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/stats/overview",
            "query_string": b"",
            "headers": headers,
        }
    )


class Fetch:
    """fetch()-Attrappe: merkt sich jeden Aufruf, antwortet je nach SQL-Text."""

    def __init__(self, **by_marker):
        self.by_marker = by_marker
        self.calls: list[tuple[str, datetime, datetime, dict]] = []

    def __call__(self, sql, since, until, **params):
        self.calls.append((sql, since, until, params))
        for marker, rows in self.by_marker.items():
            if marker in sql:
                return rows
        return []


# ---- dependency -----------------------------------------------------------


def test_routes_require_the_stats_cookie():
    with pytest.raises(HTTPException) as e:
        sa.require_stats_session(_req())
    assert e.value.status_code == 401
    assert sa.require_stats_session(_req(sa.mint_stats_token("1", "m")))["scope"] == "stats"


def test_a_login_token_does_not_open_the_stats_api():
    with pytest.raises(HTTPException) as e:
        sa.require_stats_session(_req(jwt_auth.create_token("1", "42")))
    assert e.value.status_code == 401


def test_every_stats_route_depends_on_the_founder_session():
    for route in fr.router.routes:
        deps = [d.call for d in route.dependant.dependencies]  # type: ignore[attr-defined]
        assert sa.require_stats_session in deps, route.path  # type: ignore[attr-defined]


def test_router_is_mounted_under_api_stats():
    from api.main import app

    # The OpenAPI schema, not app.routes: how FastAPI stores included routers
    # changed between the local and the CI version (a _IncludedRouter wrapper
    # without .path), while the schema is the documented contract either way.
    paths = set(app.openapi()["paths"])
    for name in ("overview", "map", "content", "feedback", "sources", "journeys", "problems"):
        assert f"/api/stats/{name}" in paths, name


# ---- endpoints ------------------------------------------------------------


def test_overview_shapes_the_rows(monkeypatch):
    monkeypatch.setattr(
        fr,
        "fetch",
        lambda sql, since, until, **p: (
            [{"views": 10, "sessions": 4, "live_sessions": 1}] if "live_sessions" in sql else []
        ),
    )
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    assert out["today"]["views"] == 10 and out["today"]["live"] == 1
    assert out["days"] == 7
    assert out["sessions"] == {"all": 0, "human": 0} and out["types"] == {} and out["hours"] == []


def test_overview_windows_are_today_yesterday_and_the_requested_days(monkeypatch):
    fetch = Fetch(live_sessions=[{"views": 1, "sessions": 1, "live_sessions": 0}])
    monkeypatch.setattr(fr, "fetch", fetch)
    asyncio.run(fr.overview(days=3, _session=SESSION))
    overview_calls = [c for c in fetch.calls if "live_sessions" in c[0]]
    assert len(overview_calls) == 2
    (_, today_since, today_until, today_p), (_, y_since, y_until, _) = overview_calls
    assert today_since.tzinfo is UTC and today_since.hour == 0 and today_since.minute == 0
    assert y_until - y_since == today_until - today_since  # yesterday up to the same hour
    assert y_since == today_since - timedelta(days=1)
    assert today_until - today_p["live"] == timedelta(minutes=5)
    window = next(c for c in fetch.calls if "ORDER BY e.session_id" in c[0])
    assert window[2] - window[1] == timedelta(days=3)


def test_overview_counts_and_types_come_from_the_session_rows(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    rows = [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "mobile", "data": None},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": None},
        {"session_id": "b", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": {"site": "1"}},
    ]  # fmt: skip
    fetch = Fetch(
        live_sessions=[{"views": 3, "sessions": 2, "live_sessions": 0}],
        **{"ORDER BY e.session_id": rows},
        **{"date_trunc('hour'": [{"hour": t, "views": 3, "sessions": 2}]},
    )
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    assert out["sessions"] == {"all": 2, "human": 1}
    assert out["types"] == {"entdecker": 1}
    assert out["hours"] == [{"hour": t, "views": 3, "sessions": 2}]


def test_map_returns_the_points_for_the_requested_days(monkeypatch):
    pts = [{"country": "DE", "city": "Berlin", "hour": 8, "sessions": 2}]
    fetch = Fetch(**{"date_part('hour'": pts})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.visitor_map(days=2, _session=SESSION))
    assert out == {"points": pts}
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=2)


def test_content_splits_the_rows_by_event_and_caps_the_lists(monkeypatch):
    rows = [
        {
            "event_name": "site_open",
            "label": f"S{i}",
            "country": "Peru",
            "results": None,
            "n": 20 - i,
        }
        for i in range(20)
    ]
    rows += [{"event_name": "story_open", "label": "st", "country": None, "results": None, "n": 3}]
    rows += [
        {
            "event_name": "paper_open",
            "label": "/research/p",
            "country": None,
            "results": None,
            "n": 2,
        }
    ]
    rows += [{"event_name": "search", "label": f"q{i}", "country": None, "results": 0, "n": 1} for i in range(40)]  # fmt: skip
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'site_open', 'story_open'": rows}))
    out = asyncio.run(fr.content(days=7, _session=SESSION))
    assert [r["label"] for r in out["sites"]][:2] == ["S0", "S1"] and len(out["sites"]) == 15
    # A site keeps its country and a search its result count — the panel shows both.
    assert out["sites"][0]["country"] == "Peru"
    assert out["searches"][0]["results"] == 0
    assert out["stories"][0]["label"] == "st"
    assert out["papers"][0]["label"] == "/research/p"
    assert len(out["searches"]) == 30


def test_feedback_returns_the_items(monkeypatch):
    items = [{"created_at": datetime(2026, 9, 17, tzinfo=UTC), "url_path": "/sites/peru/x-1", "prompt": "site_page", "answer": "no", "text": "coordinates are off"}]  # fmt: skip
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'feedback'": items}))
    out = asyncio.run(fr.feedback(days=30, _session=SESSION))
    assert out == {"items": items}


def test_sources_carry_the_family(monkeypatch):
    rows = [
        {"source": "www.google.com", "sessions": 12},
        {"source": "youtube", "sessions": 5},
        {"source": "chatgpt.com", "sessions": 2},
        {"source": "direct", "sessions": 9},
    ]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'direct'": rows}))
    out = asyncio.run(fr.sources(days=7, _session=SESSION))
    assert [(s["source"], s["family"], s["sessions"]) for s in out["sources"]] == [
        ("www.google.com", "google", 12),
        ("youtube", "youtube", 5),
        ("chatgpt.com", "ai", 2),
        ("direct", "direct", 9),
    ]


def _session_rows(t: datetime) -> list[dict]:
    """Two sessions: one story reader who opened a site, one single-page bounce."""
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    return [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common},
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/news-archive/x-1", "data": {"site": "1"}, **common},
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "data": None, **common},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common},
    ]  # fmt: skip


def test_journeys_returns_the_chains_of_the_requested_window(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    fetch = Fetch(**{"ORDER BY e.session_id": _session_rows(t)})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.journeys(days=14, _session=SESSION))
    assert out == {"chains": [{"chain": "google → story → site_open → site", "sessions": 1}]}
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=14)


def test_problems_join_the_three_problem_queries_with_the_sessions(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    fetch = Fetch(
        **{"ORDER BY e.session_id": _session_rows(t)},
        **{"'not_found'": [{"path": "/old", "referrer": "example.org", "n": 4}]},
        **{"'vital'": [{"page": "story", "name": "LCP", "p75": 4100.0, "samples": 3}]},
        **{"'js_error'": [{"message": "x is not a function", "page": "globe", "n": 12}]},
    )
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.problems(days=7, _session=SESSION))
    assert [p["kind"] for p in out["problems"]] == [
        "js_error",  # 12 hits × 3
        "broken_link",  # 4 × 2
        "slow_page",  # 3 samples
        "shallow_exit",  # session b read one story and left
    ]
    # One window for all four queries, no query run twice.
    windows = {(since, until) for _, since, until, _ in fetch.calls}
    assert len(fetch.calls) == 4 and len(windows) == 1
