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
from pipeline import stats_analysis as fs

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
    for name in ("overview", "countries", "map", "live", "globe", "clusters", "devices", "content", "feedback", "sources", "journeys", "problems", "members"):  # fmt: skip
        assert f"/api/stats/{name}" in paths, name


# ---- endpoints ------------------------------------------------------------


def test_overview_runs_one_query_and_answers_four_keys(monkeypatch):
    fetch = Fetch(**{"ORDER BY e.session_id": []})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    assert set(out) == {"days", "sessions", "types", "hours"}
    assert out["sessions"] == {"all": 0, "human": 0, "ai": 0}
    # The strip is a fixed axis, not one bar per hour that had events.
    assert len(out["hours"]) == fs.HOURLY_STRIP_HOURS
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=7)


def test_overview_counts_and_types_come_from_the_session_rows(monkeypatch):
    t = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "mobile", "data": None},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": None},
        {"session_id": "b", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": {"site": "1"}},
        {"session_id": "c", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "referrer_domain": None, "utm_source": "chatgpt.com", "country": "US", "device": "mobile", "data": None},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    # `ai` is a subset of `all` and overlaps `human`; the three never add up.
    assert out["sessions"] == {"all": 3, "human": 1, "ai": 1}
    assert out["types"] == {"explorer": 1}
    assert out["hours"][-1] == {"hour": t, "sessions": 3, "human": 1, "ai": 1}


def test_map_returns_the_points_for_the_requested_days(monkeypatch):
    pts = [{"country": "DE", "city": "Berlin", "hour": 8, "sessions": 2}]
    fetch = Fetch(**{"date_part('hour'": pts})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.visitor_map(days=2, _session=SESSION))
    assert out == {"points": pts}
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=2)


def test_countries_still_slice_one_fetch_into_four_windows(monkeypatch):
    now = datetime.now(UTC)
    common = {"referrer_domain": None, "utm_source": None, "device": "mobile"}  # fmt: skip
    rows = [
        # Still clicking: counts in every window, including "now".
        {"session_id": "live", "created_at": now, "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "DE", **common},
        {"session_id": "live", "created_at": now, "event_type": 2, "event_name": "search", "url_path": "/globe.html", "data": {"q": "x"}, "country": "DE", **common},
        # Yesterday: in 7 and 30 days, not in today or now.
        {"session_id": "old", "created_at": now - timedelta(days=1), "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "US", **common},
        {"session_id": "old", "created_at": now - timedelta(days=1), "event_type": 1, "event_name": None, "url_path": "/", "data": None, "country": "US", **common},
        # Three weeks back: only the 30-day tile.
        {"session_id": "ancient", "created_at": now - timedelta(days=21), "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "PE", **common},
        {"session_id": "ancient", "created_at": now - timedelta(days=21), "event_type": 1, "event_name": None, "url_path": "/", "data": None, "country": "PE", **common},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    # The unwrapped helper: /countries is cached for COUNTRY_TTL seconds, and a
    # cache hit from another test would answer before the fetch ever runs.
    out = asyncio.run(fr._country_windows.__wrapped__())
    assert [r["country"] for r in out["now"]["countries"]] == ["DE"]
    assert [r["country"] for r in out["today"]["countries"]] == ["DE"]
    assert [r["country"] for r in out["d7"]["countries"]] == ["DE", "US"]
    assert [r["country"] for r in out["d30"]["countries"]] == ["DE", "PE", "US"]
    assert out["d30"]["sessions"] == 3 and out["d30"]["all"] == 3
    # One query for four tiles, and it reaches back thirty days.
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=fr.COUNTRY_DAYS)


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


def test_content_hands_out_no_session_id(monkeypatch):
    """SQL_CONTENT selects the visitor behind the last hit, because /problems
    names them on its empty-search rows. Nothing on the content panel renders
    any of it, and an untouched row would ship up to 75 whole Umami session
    ids — the join key of every other table in that database — each with a
    country, a device and a browser, into a response the page throws away.
    Every other route cuts an id to eight characters."""
    row = {
        "event_name": "search",
        "label": "giza",
        "country": None,
        "results": 14,
        "n": 23,
        "last_at": datetime(2026, 9, 19, tzinfo=UTC),
        "last_session": "cf01aa30-ef2f-5e7e-b509-cb95b1c1a095",
        "last_country": "DE",
        "last_device": "mobile",
        "last_browser": "chrome",
    }
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'site_open', 'story_open'": [row]}))
    out = asyncio.run(fr.content(days=7, _session=SESSION))
    assert out["searches"] == [
        {"event_name": "search", "label": "giza", "country": None, "results": 14, "n": 23}
    ]
    assert "cf01aa30" not in repr(out)


def test_feedback_returns_the_items(monkeypatch):
    items = [{"created_at": datetime(2026, 9, 17, tzinfo=UTC), "url_path": "/sites/peru/x-1", "prompt": "site_page", "answer": "no", "text": "coordinates are off"}]  # fmt: skip
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'feedback'": items}))
    out = asyncio.run(fr.feedback(days=30, _session=SESSION))
    assert out == {"items": items}


#: SQL_SOURCES' marker is NOT "'direct'": SQL_NOT_FOUND carries the same
#: coalesce(..., 'direct') and Fetch answers with the first marker that
#: matches, so the two would trade rows.
SOURCE_ROWS = [
    {"source": "www.google.com", "sessions": 12, "views": 62},
    {"source": "youtube", "sessions": 5, "views": 5},
    {"source": "chatgpt.com", "sessions": 2, "views": 3},
    {"source": "direct", "sessions": 9, "views": 20},
]


def test_sources_carry_views_and_the_log_coverage(monkeypatch):
    monkeypatch.setattr(fr, "fetch", Fetch(**{"nullif(utm_source": SOURCE_ROWS}))
    monkeypatch.setattr(fr.referral_log, "read_visits", lambda: [])
    out = asyncio.run(fr.sources(days=7, _session=SESSION))
    assert [(s["source"], s["family"], s["sessions"], s["views"]) for s in out["sources"]] == [
        ("www.google.com", "google", 12, 62),
        ("youtube", "youtube", 5, 5),
        ("chatgpt.com", "ai", 2, 3),
        ("direct", "direct", 9, 20),
    ]
    assert isinstance(out["log"], dict) and out["log_reason"] is None


def test_sources_say_why_the_log_is_missing_on_a_dev_box(monkeypatch):
    monkeypatch.setattr(fr, "fetch", Fetch(**{"nullif(utm_source": SOURCE_ROWS}))
    monkeypatch.setattr(fr.referral_log, "read_visits", lambda: None)
    out = asyncio.run(fr.sources(days=7, _session=SESSION))
    assert out["log"] is None
    assert str(fr.referral_log.LOG_PATH) in out["log_reason"]


def test_sources_bucket_a_bare_perplexity_as_ai(monkeypatch):
    """Die Live-Zeile, die heute unter "Other" landet: Perplexity hängt
    utm_source=perplexity an, und das ist kein Host."""
    rows = [{"source": "perplexity", "sessions": 1, "views": 1}]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"nullif(utm_source": rows}))
    monkeypatch.setattr(fr.referral_log, "read_visits", lambda: None)
    out = asyncio.run(fr.sources(days=7, _session=SESSION))
    assert out["sources"][0]["family"] == "ai"


def test_globe_asks_only_for_the_globe_path(monkeypatch):
    since = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    rows = [
        {
            "session_id": "a",
            "views": 2,
            "ready": 1,
            "ready_ms": [9450.0],
            "gate_left": 0,
            "gate_quit": 0,
            "unsupported": 0,
            "failed": 0,
            "context_lost": 0,
            "abandoned": 1,
            "abandon_ms": [6100.0],
            "first_view": since + timedelta(hours=2),
            "endings_since": since,
        }
    ]
    fetch = Fetch(**{"'globe_ready'": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.globe(days=7, _session=SESSION))
    assert set(out) == {
        "loads",
        "reached",
        "gave_up",
        "sessions",
        "ready_ms",
        "not_reached",
        "abandon_ms",
    }
    assert out["loads"] == 2 and out["reached"] == 1
    assert out["not_reached"] == {
        "gate": 0,
        "unsupported": 0,
        "error": 0,
        "abandoned": 1,
        "no_signal": 0,
        "unmeasured": 0,
    }
    assert out["abandon_ms"]["samples"] == 1
    assert len(fetch.calls) == 1 and fetch.calls[0][3] == {"path": fr.GLOBE_PATH}


def test_the_windows_the_dashboard_prints_as_words():
    """Vier Konstanten, die das Frontend als Text ausschreibt — sie sind hier
    als Literale festgenagelt, weil jeder andere Test sie gegen sich selbst
    prüft und eine Änderung deshalb durch alle Gates läuft. Pulse.tsx druckt
    "sessions, last 5 min" (LIVE_WINDOW) und die Kachel "30 days"
    (COUNTRY_DAYS); LiveNow.tsx liest window_minutes und lookback_hours aus
    der Antwort, aber die Kachel darüber sagt fünf Minuten."""
    assert fr.LIVE_WINDOW == timedelta(minutes=5)
    assert fr.HERE_WINDOW == timedelta(minutes=30)
    assert fr.LIVE_LOOKBACK == timedelta(hours=24)
    assert fr.COUNTRY_DAYS == 30
    # Länger als das Refresh-Intervall des Dashboards (60 s), sonst ist die
    # Trefferquote null: genau das war der erste Entwurf mit 55 s.
    assert fr.COUNTRY_TTL > 60


def test_clusters_pass_the_minimum_id_count(monkeypatch):
    rows = [{"screen": "1366x1366", "browser": "chrome", "os": "Mac OS", "sessions": 22}]
    fetch = Fetch(**{"date_trunc('minute'": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.clusters(days=7, _session=SESSION))
    assert len(fetch.calls) == 1 and fetch.calls[0][3] == {"min_ids": fr.CLUSTER_MIN_IDS}
    assert out["min_ids"] == 3 and out["flagged"] == 22
    # Kein Sitzungstotal: der Nenner kommt aus /overview.
    assert "sessions" not in out


def test_devices_fold_laptop_into_desktop_and_keep_the_counts(monkeypatch):
    rows = [
        {"device": "laptop", "language": "en-US", "sessions": 117},
        {"device": "mobile", "language": "en-US", "sessions": 45},
        {"device": "desktop", "language": "de-DE", "sessions": 6},
    ]
    fetch = Fetch(**{"s.language": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.devices(days=7, _session=SESSION))
    assert len(fetch.calls) == 1
    assert out["sessions"] == 168
    assert out["devices"][0] == {"device": "desktop", "sessions": 123}
    assert out["language_groups"][0] == {"language": "en", "sessions": 162}


def _live_row(session: str, minutes_ago: int, now: datetime) -> dict:
    return {
        "session": session,
        "last_seen": now - timedelta(minutes=minutes_ago),
        "page_since": now - timedelta(minutes=minutes_ago + 1),
        "url_path": "/sites/peru/x-1",
        "title": "Machu Picchu | Ancient Nerds",
        "country": "CH",
        "device": "laptop",
        "browser": "chrome",
    }


def test_live_splits_the_here_and_now_from_the_last_visitor(monkeypatch):
    now = datetime.now(UTC)
    rows = [_live_row("here", 3, now), _live_row("gone", 9 * 60, now)]
    fetch = Fetch(**{"AS last_seen": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.live(_session=SESSION))
    assert (out["total"], out["shown"]) == (1, 1)
    # Die Zahlen, die das Panel als Worte druckt: LiveNow.tsx schreibt "in the
    # last {window_minutes} minutes" und "Nobody in the {lookback_hours} hours
    # before that either". In Minuten und Stunden, nicht in Sekunden.
    assert out["window_minutes"] == 30
    assert out["lookback_hours"] == 24
    assert [v["session"] for v in out["visitors"]] == ["here"]
    assert out["last"] is None
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == fr.LIVE_LOOKBACK

    monkeypatch.setattr(fr, "fetch", Fetch(**{"AS last_seen": [_live_row("gone", 9 * 60, now)]}))
    empty = asyncio.run(fr.live(_session=SESSION))
    assert empty["total"] == 0 and empty["visitors"] == []
    assert empty["last"]["session"] == "gone"


def test_live_caps_the_list_at_the_limit(monkeypatch):
    now = datetime.now(UTC)
    rows = [_live_row(f"s{i}", i, now) for i in range(8)]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"AS last_seen": rows}))
    out = asyncio.run(fr.live(_session=SESSION))
    assert out["total"] == 8
    assert out["shown"] == fr.LIVE_LIMIT == len(out["visitors"])


def test_members_hand_the_founder_role_to_the_query(monkeypatch):
    calls: list[tuple] = []
    answer = {
        "members": 5,
        "founders": 2,
        "newest_signup": "2026-08-28T01:33:22+00:00",
        "last_login": "2026-09-19T06:26:02+00:00",
        "acts": [{"act": "Likes", "n": 2, "by": 1, "at": None}],
    }
    monkeypatch.setattr(
        fr.members_stats,
        "member_totals",
        lambda db, role: calls.append((db, role)) or answer,
    )
    out = asyncio.run(fr.members(db="session", _session=SESSION))
    assert calls == [("session", jwt_auth.FOUNDER_ROLE_ID)]
    assert out == answer
    # Aggregate, sonst nichts — kein Name, keine Id, kein Guthaben.
    assert set(out) == {"members", "founders", "newest_signup", "last_login", "acts"}


def _human_bounce_rows(t: datetime) -> list[dict]:
    """A visitor who toggled a filter and still left above the fold. Session b
    of _session_rows() is a bare one-page fetch and no longer counts as a
    bounce — nothing tells it from a crawler. The act is `filter_toggle` and
    not `share`: a shared page is an engaged visit, which fs.ENGAGEMENTS keeps
    out of the bounce list."""
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    return [
        {"session_id": "c", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common},
        {"session_id": "c", "created_at": t, "event_type": 2, "event_name": "filter_toggle", "url_path": "/news-archive/x-1", "data": {"filter": "type"}, **common},
    ]  # fmt: skip


def _session_rows(t: datetime) -> list[dict]:
    """Two sessions: one story reader who opened a site, one single-page bounce."""
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    return [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common},
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/news-archive/x-1", "data": {"site": "1"}, **common},
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "data": None, **common},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common},
    ]  # fmt: skip


def test_journeys_carry_chains_entries_exits_outbound_and_reading_from_one_fetch(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    extra = [
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "outbound_click", "url_path": "/sites/peru/x-1", "data": {"host": "youtube.com"}, **common},
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "scroll_depth", "url_path": "/sites/peru/x-1", "data": {"page": "site", "depth": "50"}, **common},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": _session_rows(t) + extra})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.journeys(days=14, _session=SESSION))
    assert set(out) == {"chains", "pages", "outbound", "reading"}
    assert out["chains"][0] == {"chain": "google → story → site_open → site", "sessions": 1}
    assert out["pages"]["sessions"] == 1 and out["pages"]["entries"][0]["page"] == "story"
    assert out["outbound"] == [{"host": "youtube.com", "clicks": 1, "visitors": 1}]
    assert out["reading"]["pages"] == [{"page": "site", "sessions": [1, 1, 0, 0]}]
    # Eine Abfrage für vier Antworten, und sie trägt das erfragte Fenster.
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=14)


def test_problems_run_six_queries_in_one_window(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    fetch = Fetch(
        **{"ORDER BY e.session_id": _session_rows(t) + _human_bounce_rows(t)},
        **{"'not_found'": [{"path": "/old", "referrer": "example.org", "n": 4, "sessions": 4}]},
        **{
            "'vital'": [
                {"page": "story", "name": "LCP", "p75": 4100.0, "samples": 12, "sessions": 7}
            ]
        },  # fmt: skip
        **{
            "'js_error'": [
                {"message": "x is not a function", "page": "globe", "n": 12, "sessions": 5}
            ]
        },  # fmt: skip
        **{
            "'webgl_lost'": [{"phase": "live", "reason": "context_lost", "n": 2, "sessions": 2}]
        },  # fmt: skip
        # The content query also feeds the ranking: a search that found nothing
        # is only actionable with the word attached.
        **{
            "'site_open', 'story_open'": [
                {
                    "event_name": "search",
                    "label": "atlantis",
                    "country": None,
                    "results": 0,
                    "n": 5,
                },
                {"event_name": "search", "label": "giza", "country": None, "results": 9, "n": 4},
                {
                    "event_name": "site_open",
                    "label": "Giza",
                    "country": "Egypt",
                    "results": None,
                    "n": 9,
                },
            ]
        },
    )
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.problems(days=7, _session=SESSION))
    assert [p["kind"] for p in out["problems"]] == [
        "js_error",  # 5 visitors reached × 3
        "slow_page",  # 7 visitors × 4100 ms against the 2500 ms budget
        "broken_link",  # 4 visitors × 2
        "webgl_lost",  # 2 visitors × 3
        "empty_search",  # "atlantis", 5 searches
        "shallow_exit",  # session c left after the headline
    ]
    assert [p["score"] for p in out["problems"]] == [15, 11, 8, 6, 5, 1]
    dead = next(p for p in out["problems"] if p["kind"] == "empty_search")
    assert dead["label"] == "atlantis"  # the term, not just a count
    assert not any(p["label"] == "giza" for p in out["problems"])  # that one found something
    # One window for all six queries, no query run twice.
    windows = {(since, until) for _, since, until, _ in fetch.calls}
    assert len(fetch.calls) == 6 and len(windows) == 1
