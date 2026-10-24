# SPDX-License-Identifier: AGPL-3.0-only
"""/api/stats/* — die Daten des Founders-Dashboards hinter dem an_stats-Cookie.

DB-los: pipeline.umami_db.fetch wird am Routenmodul (fr.fetch) durch eine
Attrappe ersetzt, die je nach SQL-Text Zeilen liefert; das Cookie wird mit
einem Testschlüssel signiert wie in test_stats_access.py.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes import founders_stats as fr
from api.routes import stats_access as sa
from api.services import jwt_auth
from pipeline import stats_analysis as fs
from pipeline import visitor_class as vc

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
    for name in ("overview", "countries", "visitors", "daily", "search", "field-vitals", "crawlers", "server", "creators", "map", "live", "globe", "clusters", "devices", "content", "feedback", "sources", "journeys", "problems", "members"):  # fmt: skip
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


def _umami(sid: str, created: datetime) -> dict:
    """The session columns every SQL_SESSION_EVENTS row carries. A screen of
    its own per session keeps it out of the machine rules' fingerprint groups
    (pipeline/visitor_class.py); _arrival() sets a shared one on purpose."""
    return {"browser": "chrome", "os": "Android", "screen": f"{sid}-screen", "language": "en-US",
            "session_created": created, "visit_id": f"v-{sid}"}  # fmt: skip


def test_overview_counts_and_types_come_from_the_session_rows(monkeypatch):
    t = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "mobile", "data": None, **_umami("a", t)},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": None, **_umami("b", t)},
        {"session_id": "b", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/globe.html", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "desktop", "data": {"site": "1"}, **_umami("b", t)},
        {"session_id": "c", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "referrer_domain": None, "utm_source": "chatgpt.com", "country": "US", "device": "mobile", "data": None, **_umami("c", t)},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.overview(days=7, _session=SESSION))
    # `ai` is a subset of `all` and overlaps `human`; the three never add up.
    assert out["sessions"] == {"all": 3, "human": 1, "ai": 1}
    assert out["types"] == {"explorer": 1}
    assert out["hours"][-1] == {"hour": t, "sessions": 3, "human": 1, "ai": 1}


def test_daily_fetches_the_whole_history_once_and_ends_with_today(monkeypatch):
    now = datetime.now(UTC)
    rows = [
        {"session_id": "a", "created_at": now, "event_type": 1, "event_name": None, "url_path": "/", "referrer_domain": None, "utm_source": None, "country": "DE", "device": "mobile", "data": None, **_umami("a", now)},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    # The unwrapped helper, for the same reason as /countries: it is cached.
    out = asyncio.run(fr._daily_line.__wrapped__())
    assert out["today"]["day"] == now.date().isoformat()
    assert out["today"]["visitors"] == 1
    assert out["days"][0]["day"] == fs.TRACKER_FIRST_FULL_DAY.isoformat()
    assert len(out["days"]) == (now.date() - fs.TRACKER_FIRST_FULL_DAY).days
    assert len(fetch.calls) == 1
    assert fetch.calls[0][1] == datetime(2026, 9, 18, tzinfo=UTC)


def test_creators_name_the_channels_from_our_own_database(monkeypatch):
    from datetime import date

    rows = [
        {
            "event_name": "media_play",
            "media": "vid00000001",
            "day": date(2026, 10, 9),
            "n": 3,
            "visitors": 3,
        }
    ]
    fetch = Fetch(**{"media_play": rows})
    monkeypatch.setattr(fr, "fetch", fetch)

    class Query:
        def join(self, *a, **kw):
            return self

        def filter(self, *a, **kw):
            return self

        def all(self):
            from types import SimpleNamespace

            return [SimpleNamespace(id="vid00000001", name="Ancient Architects", title="Baalbek")]

    class Db:
        def query(self, *cols):
            return Query()

    out = asyncio.run(fr.creators(days=30, db=Db(), _session=SESSION))
    assert out["channels"] == [
        {"channel": "Ancient Architects", "starts": 3, "viewers": 3, "clicks": 0}
    ]
    assert fetch.calls[0][3] == {"clicks_since": fr.OUTBOUND_FIX}
    assert out["clicks_since"] == "2026-10-09T06:42:00+00:00"


def test_server_says_why_when_the_log_is_missing(monkeypatch):
    from pipeline import server_load

    monkeypatch.setattr(server_load, "read_samples", lambda: None)
    out = asyncio.run(fr.server(_session=SESSION))
    assert out["report"] is None and "server_load.jsonl" in out["log_reason"]


def test_server_puts_each_day_s_visitors_beside_its_load(monkeypatch):
    from pipeline import server_load

    now = datetime.now(UTC)
    sample = {"t": now - timedelta(minutes=3), "cpu": 3.0, "load1": 0.2, "load5": 0.3, "mem_used": 31.0, "mem_total_mb": 11960, "disk_used": 59.0, "disk_free_gb": 80.0, "cores": 6}  # fmt: skip
    monkeypatch.setattr(server_load, "read_samples", lambda: [sample])

    async def daily():
        return {
            "days": [],
            "today": {"day": now.date().isoformat(), "visitors": 42, "human": 9, "ai": 1},
        }

    monkeypatch.setattr(fr, "_daily_line", daily)
    out = asyncio.run(fr.server(_session=SESSION))
    assert out["report"]["days"][-1]["visitors"] == 42
    assert out["report"]["now"]["disk_used"] == 59.0


def test_crawlers_say_why_when_the_log_is_missing(monkeypatch):
    from pipeline import crawler_log

    monkeypatch.setattr(crawler_log, "read_fetches", lambda: None)
    out = asyncio.run(fr.crawlers(days=7, _session=SESSION))
    assert out["report"] is None
    assert "crawlers.log" in out["log_reason"]


def test_crawlers_fold_the_window_against_the_published_ranges(monkeypatch):
    import ipaddress
    import json

    from pipeline import crawler_log

    now = datetime.now(UTC)
    lines = [
        json.dumps({"t": (now - timedelta(days=d)).isoformat(), "ip": "66.249.66.1", "req": "GET /", "status": 200, "ua": "Googlebot/2.1"})
        for d in (1, 10)
    ]  # fmt: skip

    async def ranges():
        return {"google": [ipaddress.ip_network("66.249.64.0/19")]}

    monkeypatch.setattr(crawler_log, "read_fetches", lambda: crawler_log.parse_lines(lines))
    monkeypatch.setattr(crawler_log, "published_ranges", ranges)
    out = asyncio.run(fr.crawlers(days=7, _session=SESSION))
    # The ten-day-old fetch is outside the 7-day window.
    assert out["report"]["bots"][0]["requests"] == 1
    assert out["log_reason"] is None


def test_map_returns_the_points_for_the_requested_days(monkeypatch):
    pts = [{"country": "DE", "sessions": 2}]
    fetch = Fetch(**{"GROUP BY s.country": pts})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr.visitor_map(days=2, _session=SESSION))
    assert out == {"points": pts}
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=2)


def test_countries_still_slice_one_fetch_into_four_windows(monkeypatch):
    now = datetime.now(UTC)
    common = {"referrer_domain": None, "utm_source": None, "device": "mobile"}  # fmt: skip
    rows = [
        # Still clicking: counts in every window, including "now".
        {"session_id": "live", "created_at": now, "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "DE", **common, **_umami("live", now)},
        {"session_id": "live", "created_at": now, "event_type": 2, "event_name": "search", "url_path": "/globe.html", "data": {"q": "x"}, "country": "DE", **common, **_umami("live", now)},
        # Yesterday: in 7 and 30 days, not in today or now. Two URLs make a
        # person only for a session that came from somewhere (Session.human).
        {"session_id": "old", "created_at": now - timedelta(days=1), "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "US", **common, "referrer_domain": "www.google.com", **_umami("old", now - timedelta(days=1))},
        {"session_id": "old", "created_at": now - timedelta(days=1), "event_type": 1, "event_name": None, "url_path": "/", "data": None, "country": "US", **common, **_umami("old", now - timedelta(days=1))},
        # Three weeks back: only the 30-day tile.
        {"session_id": "ancient", "created_at": now - timedelta(days=21), "event_type": 1, "event_name": None, "url_path": "/globe.html", "data": None, "country": "PE", **common, "referrer_domain": "www.google.com", **_umami("ancient", now - timedelta(days=21))},
        {"session_id": "ancient", "created_at": now - timedelta(days=21), "event_type": 1, "event_name": None, "url_path": "/", "data": None, "country": "PE", **common, **_umami("ancient", now - timedelta(days=21))},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    # The unwrapped helper: /countries is cached for COUNTRY_TTL seconds, and a
    # cache hit from another test would answer before the fetch ever runs.
    out = asyncio.run(fr._month_fold.__wrapped__())["countries"]
    assert [r["country"] for r in out["now"]["countries"]] == ["DE"]
    assert [r["country"] for r in out["today"]["countries"]] == ["DE"]
    assert [r["country"] for r in out["d7"]["countries"]] == ["DE", "US"]
    assert [r["country"] for r in out["d30"]["countries"]] == ["DE", "PE", "US"]
    assert out["d30"]["sessions"] == 3 and out["d30"]["all"] == 3
    # One query for four tiles, and it reaches back thirty days.
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=fr.COMPARE_DAYS)
    # A tile compares once the window before it lies after the tracker's first
    # full day: the 7-day one from 2 October 2026, the 30-day one from 17 November.
    first_day = datetime.combine(fs.TRACKER_FIRST_FULL_DAY, datetime.min.time(), UTC)
    for tile, days in (("d7", 7), ("d30", 30)):
        covered = now - timedelta(days=2 * days) >= first_day
        assert (out[tile]["change"] is not None) == covered, tile


def _arrival(sid: str, at: datetime, country: str, screen: str) -> list[dict]:
    """One page view and nothing else, with the columns the machine rules
    group on (pipeline/visitor_class.py fingerprint) and Umami's session start."""
    return [
        {"session_id": sid, "created_at": at, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "data": None,
         "country": country, "referrer_domain": None, "utm_source": None, "device": "desktop", "browser": "chrome",
         "os": "Windows 10", "screen": screen, "language": "en-US", "session_created": at, "visit_id": f"v-{sid}"},
    ]  # fmt: skip


def _burst_rows(now: datetime) -> list[dict]:
    """Nine one-page sessions of one fingerprint inside two minutes (a burst:
    BURST_MIN is 8) and one arrival of another fingerprint a minute ago."""
    rows = [
        r
        for i in range(9)
        for r in _arrival(f"b{i}", now - timedelta(seconds=150 - 10 * i), "SG", "1280x1200")
    ]
    return rows + _arrival("new", now - timedelta(minutes=1), "DE", "1920x1080")


def test_the_now_tile_counts_people_and_puts_the_scrapers_beside_them(monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(fr, "fetch", Fetch(**{"ORDER BY e.session_id": _burst_rows(now)}))
    fold = asyncio.run(fr._month_fold.__wrapped__())
    tile = fold["countries"]["now"]
    # The arrival has one page view and no act yet: undecided, and counted.
    assert tile["sessions"] == 1
    assert [r["country"] for r in tile["countries"]] == ["DE"]
    assert tile["all"] == 10
    assert tile["bots"] == {"sessions": 9, "country": "SG"}
    # The other tiles count humans only: neither the burst nor the arrival.
    assert fold["countries"]["today"]["sessions"] == 0
    # /live labels its rows from the same fold.
    assert fold["live_classes"]["new"] == "undecided"
    assert {fold["live_classes"][f"b{i}"] for i in range(9)} == {"scraper_js"}


def test_the_now_tile_names_no_country_without_a_scraper(monkeypatch):
    now = datetime.now(UTC)
    rows = _arrival("new", now - timedelta(minutes=1), "DE", "1920x1080")
    monkeypatch.setattr(fr, "fetch", Fetch(**{"ORDER BY e.session_id": rows}))
    tile = asyncio.run(fr._month_fold.__wrapped__())["countries"]["now"]
    assert tile["bots"] == {"sessions": 0, "country": None}


def test_countries_answer_the_four_tiles_of_the_fold(monkeypatch):
    async def fold():
        return {"countries": {"now": "N"}, "live_classes": {}}

    monkeypatch.setattr(fr, "_month_fold", fold)
    assert asyncio.run(fr.visitor_countries(_session=SESSION)) == {"now": "N"}


# ---- /visitors ------------------------------------------------------------


def _no_request_log(monkeypatch, tmp_path):
    from pipeline import crawler_log, request_log

    monkeypatch.setattr(request_log, "LOG_PATH", tmp_path / "requests.log")

    async def ranges():
        raise AssertionError("no log, so no ranges fetch")

    monkeypatch.setattr(crawler_log, "published_ranges", ranges)


def test_visitors_answer_every_class_and_say_why_the_request_log_is_missing(monkeypatch, tmp_path):
    _no_request_log(monkeypatch, tmp_path)
    now = datetime.now(UTC)
    fetch = Fetch(**{"ORDER BY e.session_id": _burst_rows(now)})
    monkeypatch.setattr(fr, "fetch", fetch)
    out = asyncio.run(fr._visitors.__wrapped__(36))
    assert set(out) == {"days", "labels", "sessions", "daily", "bursts", "requests"}
    # Every class and reason the panel can meet has its English label.
    assert {*vc.SESSION_CLASSES, *vc.SESSION_REASONS, *vc.REQUEST_CLASSES} <= set(out["labels"])
    assert out["days"] == 36
    sessions = out["sessions"]
    assert sessions["total"] == 10
    assert list(sessions["classes"]) == list(vc.SESSION_CLASSES)
    assert list(sessions["reasons"]) == list(vc.SESSION_REASONS)
    assert sessions["classes"]["scraper_js"] == 9 and sessions["classes"]["undecided"] == 1
    assert sessions["reasons"]["burst"] == 9
    assert sessions["humans_in_machine_groups"] == 0
    # One row per UTC day (two when the fixture straddles midnight), every class in it.
    assert all(set(d) == {"day", *vc.SESSION_CLASSES} for d in out["daily"])
    assert sum(d["scraper_js"] for d in out["daily"]) == 9
    assert out["daily"][-1]["day"] == now.date().isoformat()
    # The burst, as JSON the cache can hold: strings, not datetimes.
    [burst] = out["bursts"]
    assert burst["sessions"] == 9 and burst["country"] == "SG" and burst["screen"] == "1280x1200"
    assert isinstance(burst["start"], str) and burst["start"] <= burst["end"]
    requests = out["requests"]
    assert requests["report"] is None
    assert "requests.log does not exist yet" in requests["log_reason"]
    assert len(fetch.calls) == 1
    assert fetch.calls[0][2] - fetch.calls[0][1] == timedelta(days=36)


def test_visitors_list_only_the_bursts_of_the_last_week(monkeypatch, tmp_path):
    _no_request_log(monkeypatch, tmp_path)
    old = datetime.now(UTC) - timedelta(days=fr.BURST_DAYS + 1)
    rows = [
        r
        for i in range(9)
        for r in _arrival(f"b{i}", old + timedelta(seconds=i), "SG", "1280x1200")
    ]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"ORDER BY e.session_id": rows}))
    out = asyncio.run(fr._visitors.__wrapped__(30))
    assert out["sessions"]["reasons"]["burst"] == 9
    assert out["bursts"] == []


def test_visitors_set_umami_beside_the_request_log_from_its_first_line(monkeypatch, tmp_path):
    import json

    from pipeline import crawler_log, request_log

    now = datetime.now(UTC)
    first = now - timedelta(days=3)
    log = tmp_path / "requests.log"
    line = {"ip": "203.0.113.9", "ref": "", "proto": "HTTP/2.0", "purpose": "", "dest": "document", "dnt": "", "gpc": "", "ua": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"}  # fmt: skip
    log.write_text(
        "\n".join(
            json.dumps({**line, "t": t.isoformat(), "req": req, "status": 200})
            for t, req in (
                (first, "GET /sites/peru/x-1"),
                (first + timedelta(seconds=5), "POST /api/pulse"),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(request_log, "LOG_PATH", log)
    monkeypatch.setattr(request_log, "_report", None)

    async def ranges():
        return {}

    monkeypatch.setattr(crawler_log, "published_ranges", ranges)
    page = {"event_type": 1, "event_name": None, "data": None, "country": "DE", "utm_source": None, "device": "desktop", "browser": "chrome"}  # fmt: skip
    rows = [
        # Before the log's first line: on neither side.
        {**page, "session_id": "a", "created_at": first - timedelta(hours=1), "url_path": "/sites/peru/x-1", "referrer_domain": None},
        # Counted: a server-rendered path, not from a search engine.
        {**page, "session_id": "b", "created_at": first + timedelta(seconds=1), "url_path": "/sites/peru/x-1", "referrer_domain": None},
        # Left out: an arrival from Google, and a page the service worker serves.
        {**page, "session_id": "c", "created_at": first + timedelta(hours=1), "url_path": "/articles/x", "referrer_domain": "www.google.com"},
        {**page, "session_id": "d", "created_at": first + timedelta(hours=2), "url_path": "/globe.html", "referrer_domain": None},
    ]  # fmt: skip
    fetch = Fetch(**{"ORDER BY e.session_id": rows})
    monkeypatch.setattr(fr, "fetch", fetch)
    # A one-day window: the fetch still reaches back to the log's first line.
    out = asyncio.run(fr._visitors.__wrapped__(1))
    report = out["requests"]["report"]
    assert out["requests"]["log_reason"] is None
    assert report["classes"]["browser_js"]["requests"] == 1
    assert report["beacon_check"] == {"pages_with_js": 1, "umami_pageviews": 1}
    assert fetch.calls[0][1] == first
    # The window's own fold leaves the older rows out.
    assert out["sessions"]["total"] == 0
    # The module's cached report is not changed by the API's addition.
    assert "umami_pageviews" not in request_log._report[2]["beacon_check"]


def test_visitors_ask_the_cached_fold_for_their_window(monkeypatch):
    calls: list[int] = []

    async def fake(days):
        calls.append(days)
        return {"days": days}

    monkeypatch.setattr(fr, "_visitors", fake)
    assert asyncio.run(fr.visitors(days=36, _session=SESSION)) == {"days": 36}
    assert calls == [36]


def test_the_class_unions_of_the_dashboard_are_visitor_class_s():
    """types.ts spells the classes out as unions; this keeps them equal to the
    one definition (pipeline/visitor_class.py)."""
    import re
    from pathlib import Path

    types = (
        Path(__file__).resolve().parents[2] / "ancient-nerds-map/src/components/dashboard/types.ts"
    ).read_text(encoding="utf-8")

    def union(name: str) -> list[str]:
        body = re.search(rf"export type {name} =([^;]*?)\n\n", types)
        assert body, name
        return re.findall(r"'([a-z_]+)'", body.group(1))

    assert union("SessionClass") == list(vc.SESSION_CLASSES)
    assert union("SessionReason") == list(vc.SESSION_REASONS)
    assert union("RequestClass") == list(vc.REQUEST_CLASSES)


def test_content_splits_the_rows_by_event_and_caps_the_lists(monkeypatch):
    rows = [
        {
            "event_name": "site_open",
            "label": f"S{i}",
            "country": "Peru",
            "results": None,
            "n": 20 - i,
            "visitors": 20 - i,
        }
        for i in range(20)
    ]
    rows += [{"event_name": "story_open", "label": "st", "country": None, "results": None, "n": 3, "visitors": 2}]  # fmt: skip
    rows += [
        {
            "event_name": "paper_open",
            "label": "/research/p",
            "country": None,
            "results": None,
            "n": 2,
            "visitors": 2,
        }
    ]
    searches = [
        {"session_id": f"s{i}", "created_at": datetime(2026, 9, 19, tzinfo=UTC), "q": f"q{i}", "results": 0}
        for i in range(40)
    ]  # fmt: skip
    monkeypatch.setattr(
        fr,
        "fetch",
        Fetch(**{"'site_open', 'story_open'": rows, "e.event_name = 'search'": searches}),
    )
    out = asyncio.run(fr.content(days=7, _session=SESSION))
    assert [r["label"] for r in out["sites"]][:2] == ["S0", "S1"] and len(out["sites"]) == 15
    # A site keeps its country and a search its result count — the panel shows both.
    assert out["sites"][0]["country"] == "Peru"
    assert out["searches"][0]["results"] == 0
    assert out["stories"][0]["label"] == "st"
    assert out["papers"][0]["label"] == "/research/p"
    assert len(out["searches"]) == 30


def test_content_ranks_opened_things_by_visitors(monkeypatch):
    """2026-09-25: the week's most opened site had 24 opens from six sessions of
    one laptop; a site four people opened once each is the bigger number."""
    rows = [
        {"event_name": "site_open", "label": "Petroglyph Beach", "country": "USA", "results": None, "n": 24, "visitors": 6},
        {"event_name": "site_open", "label": "Els Munts", "country": "Spain", "results": None, "n": 8, "visitors": 8},
    ]  # fmt: skip
    monkeypatch.setattr(fr, "fetch", Fetch(**{"'site_open', 'story_open'": rows}))
    out = asyncio.run(fr.content(days=7, _session=SESSION))
    assert [r["label"] for r in out["sites"]] == ["Els Munts", "Petroglyph Beach"]


def test_content_hands_out_no_session_id(monkeypatch):
    """SQL_CONTENT selects the visitor behind the last hit, because /problems
    names them on its empty-search rows. Nothing on the content panel renders
    any of it, and an untouched row would ship up to 75 whole Umami session
    ids — the join key of every other table in that database — each with a
    country, a device and a browser, into a response the page throws away.
    Every other route cuts an id to eight characters."""
    row = {
        "event_name": "site_open",
        "label": "Giza",
        "country": "Egypt",
        "results": None,
        "n": 23,
        "visitors": 9,
        "last_at": datetime(2026, 9, 19, tzinfo=UTC),
        "last_session": "cf01aa30-ef2f-5e7e-b509-cb95b1c1a095",
        "last_country": "DE",
        "last_device": "mobile",
        "last_browser": "chrome",
    }
    search = {
        "session_id": "cf01aa30-ef2f-5e7e-b509-cb95b1c1a095",
        "created_at": datetime(2026, 9, 19, tzinfo=UTC),
        "q": "giza",
        "results": Decimal("14.0000"),
    }
    monkeypatch.setattr(
        fr,
        "fetch",
        Fetch(**{"'site_open', 'story_open'": [row], "e.event_name = 'search'": [search]}),
    )
    out = asyncio.run(fr.content(days=7, _session=SESSION))
    assert out["sites"] == [
        {"event_name": "site_open", "label": "Giza", "country": "Egypt", "results": None, "n": 23, "visitors": 9}
    ]  # fmt: skip
    # results is numeric in event_data: a Decimal the panel compared with 0 and never matched
    assert out["searches"] == [
        {"event_name": "search", "label": "giza", "country": None, "results": 14, "n": 1, "visitors": 1}
    ]  # fmt: skip
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
        "gate_stops",
        "by_device",
    }
    assert out["loads"] == 2 and out["reached"] == 1
    assert out["not_reached"] == {
        "unsupported": 0,
        "error": 0,
        "abandoned": 1,
        "no_signal": 0,
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


def _live_classes(monkeypatch, classes: dict[str, str]) -> None:
    """The thirty-day fold /live labels its rows from, without its fetch."""

    async def fold():
        return {"countries": {}, "live_classes": classes}

    monkeypatch.setattr(fr, "_month_fold", fold)


def test_live_splits_the_here_and_now_from_the_last_visitor(monkeypatch):
    _live_classes(monkeypatch, {})
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
    _live_classes(monkeypatch, {})
    now = datetime.now(UTC)
    rows = [_live_row(f"s{i}", i, now) for i in range(8)]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"AS last_seen": rows}))
    out = asyncio.run(fr.live(_session=SESSION))
    assert out["total"] == 8
    assert out["shown"] == fr.LIVE_LIMIT == len(out["visitors"])


def test_live_keeps_the_bots_and_labels_every_row_with_its_class(monkeypatch):
    # Owner, 2026-10-22: the list keeps everyone and says what each one is.
    # The fold is keyed by the full session id; the row prints it cut short.
    now = datetime.now(UTC)
    long_id = "b" * 36
    _live_classes(monkeypatch, {long_id: "scraper_js", "gone": "human"})
    rows = [_live_row(long_id, 1, now), _live_row("fresh", 2, now)]
    monkeypatch.setattr(fr, "fetch", Fetch(**{"AS last_seen": rows}))
    out = asyncio.run(fr.live(_session=SESSION))
    assert [(v["session"], v["class"]) for v in out["visitors"]] == [
        (long_id[: fs.SESSION_ID_CHARS], "scraper_js"),
        # Arrived after the cached fold: no class yet, and no guess.
        ("fresh", None),
    ]

    monkeypatch.setattr(fr, "fetch", Fetch(**{"AS last_seen": [_live_row("gone", 9 * 60, now)]}))
    assert asyncio.run(fr.live(_session=SESSION))["last"]["class"] == "human"


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
        {"session_id": "c", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common, **_umami("c", t)},
        {"session_id": "c", "created_at": t, "event_type": 2, "event_name": "filter_toggle", "url_path": "/news-archive/x-1", "data": {"filter": "type"}, **common, **_umami("c", t)},
    ]  # fmt: skip


def _session_rows(t: datetime) -> list[dict]:
    """Two sessions: one story reader who opened a site, one single-page bounce."""
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    return [
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common, **_umami("a", t)},
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "site_open", "url_path": "/news-archive/x-1", "data": {"site": "1"}, **common, **_umami("a", t)},
        {"session_id": "a", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/sites/peru/x-1", "data": None, **common, **_umami("a", t)},
        {"session_id": "b", "created_at": t, "event_type": 1, "event_name": None, "url_path": "/news-archive/x-1", "data": None, **common, **_umami("b", t)},
    ]  # fmt: skip


def test_journeys_carry_chains_entries_exits_outbound_and_reading_from_one_fetch(monkeypatch):
    t = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    common = {"referrer_domain": "google.com", "utm_source": None, "country": "DE", "device": "mobile"}  # fmt: skip
    extra = [
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "outbound_click", "url_path": "/sites/peru/x-1", "data": {"host": "youtube.com"}, **common, **_umami("a", t)},
        {"session_id": "a", "created_at": t, "event_type": 2, "event_name": "scroll_depth", "url_path": "/sites/peru/x-1", "data": {"page": "site", "depth": "50"}, **common, **_umami("a", t)},
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
