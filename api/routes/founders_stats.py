# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: nineteen endpoints under /api/stats, all
behind the ``an_stats`` cookie (stats_access.require_stats_session). Umami rows
come from pipeline.umami_db, the member counts from pipeline.members_stats,
nginx's referral log from pipeline.referral_log, Google's view of us (Search
Console, CrUX) and nginx's crawler log from api/services, and every
founder-level shaping from pipeline.stats_analysis.

``fetch`` is imported as a module attribute on purpose: the tests replace
``fr.fetch`` and never touch a database.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.cache import cached
from api.routes.stats_access import require_stats_session
from api.services import crawler_log, crux, jwt_auth, search_console
from pipeline import members_stats, referral_log, server_load
from pipeline import stats_analysis as fs
from pipeline.database import NewsChannel, NewsVideo, get_db
from pipeline.umami_db import (
    CLUSTER_MIN_IDS,
    GLOBE_PATH,
    SQL_CLUSTERS,
    SQL_CONTENT,
    SQL_CREATOR,
    SQL_DEVICES,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_GLOBE,
    SQL_LIVE,
    SQL_MAP,
    SQL_NOT_FOUND,
    SQL_SEARCH_EVENTS,
    SQL_SESSION_EVENTS,
    SQL_SOURCES,
    SQL_VITALS,
    SQL_WEBGL_LOST,
    fetch,
)

router = APIRouter()

#: The longest window a panel may ask for. The dashboard asks every panel for
#: the whole history since the tracker's first event (owner, 2026-10-10), so
#: this is a sanity bound, not a choice: ten years.
ALL_DAYS_MAX = 3650

#: "Live" on the pulse tile: sessions with an event in the last five minutes.
LIVE_WINDOW = timedelta(minutes=5)
#: The live panel's own window, and how far back it looks for the last visitor
#: when nobody is here. Measured 2026-09-19: a thirty-minute window was empty
#: in 20 % of all minutes and the longest gap between two events was 117
#: minutes, so a 24-hour lookback always names somebody.
HERE_WINDOW = timedelta(minutes=30)
LIVE_LOOKBACK = timedelta(hours=24)
#: Rows the live panel prints. At one visitor an hour this is never reached;
#: it exists so a burst cannot make the panel the tallest thing on the phone.
LIVE_LIMIT = 6
#: The flag row's longest window. One fetch serves all four tiles.
COUNTRY_DAYS = 30
#: How far /countries reads: twice the longest tile, so the 7- and 30-day
#: tiles can each be set against the window before them.
COMPARE_DAYS = 2 * COUNTRY_DAYS
#: How long /countries' thirty-day fold is reused. It must be LONGER than the
#: dashboard's poll interval or it can never hit: useStats refreshes every
#: 60 000 ms (ancient-nerds-map/src/components/dashboard/useStats.ts:10), and
#: a 55-second entry is always expired by the time the next request arrives -
#: 0 % hit rate for a single open dashboard, which is what the first draft
#: shipped. At 90 s every second refresh is served from cache.
#: Redis holds it, so the two API containers share one copy; without Redis
#: api/cache.py falls back to a per-process dict and each container keeps its
#: own. Worth having even though the query costs 10 ms today: it is the only
#: one that will grow with the calendar rather than with the traffic.
COUNTRY_TTL = 90
#: How long the growth line is reused. A day's point only grows during that
#: day, so five minutes is fresh enough, and the panel asks at that cadence.
DAILY_TTL = 300
#: Search Console's newest final day is two to three days old and moves once
#: a day, so an hour is fresh; the first call after it costs six API requests.
SEARCH_TTL = 3600
#: CrUX publishes one new weekly window a week.
FIELD_VITALS_TTL = 12 * 3600


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


@router.get("/overview")
async def overview(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """One fetch, three panels: the pulse strip, the session types and the
    scraper panel's denominator.

    `human` and `ai` both count sessions and they overlap - an assistant can
    send a person. They are never added together.
    """
    since, until = _window(days)
    rows = fetch(SQL_SESSION_EVENTS, since, until)
    sessions = fs.sessions_from_rows(rows)
    return {
        "days": days,
        "sessions": {
            "all": len(sessions),
            "human": sum(1 for s in sessions if s.human),
            "ai": sum(1 for s in sessions if s.from_ai),
        },
        "types": fs.session_type_shares(sessions),
        "hours": fs.hourly_sessions(rows, sessions, until),
    }


@cached("stats:countries", ttl=COUNTRY_TTL)
async def _country_windows() -> dict[str, Any]:
    """The four flag tiles from one thirty-day fold.

    Cached rather than recomputed per request: this is the only query on the
    page that reaches back a month. The cache is api/cache.py's - Redis when
    it is up, and then both API containers share one copy; a bounded
    per-process dict when it is not, and then they do not. No argument, so the
    key is the prefix and no founder's session ever reaches it.

    Note the 30-day fold costs the same 10-13 ms as the 7-day one today
    (measured 2026-09-19: 794 rows either way) - the tracker has two days of
    history. The cache is here for October, not for now.
    """
    now = datetime.now(UTC)
    rows = fetch(SQL_SESSION_EVENTS, now - timedelta(days=COMPARE_DAYS), now)
    month = now - timedelta(days=COUNTRY_DAYS)
    sessions = fs.sessions_from_rows([r for r in rows if r["created_at"] >= month])
    first_day = datetime.combine(fs.TRACKER_FIRST_FULL_DAY, time.min, UTC)

    def humans(start: datetime, end: datetime) -> int:
        """Confirmed humans among the ids seen in [start, end), folded on that
        window alone - both sides of a comparison counted the same way."""
        window = [r for r in rows if start <= r["created_at"] < end]
        return sum(1 for s in fs.sessions_from_rows(window) if s.human)

    def change(days: int) -> dict[str, int] | None:
        """This window against the one before it; None while the one before
        reaches back past the tracker's first full day."""
        start = now - timedelta(days=2 * days)
        if start < first_day:
            return None
        cut = now - timedelta(days=days)
        return {"now": humans(cut, now), "before": humans(start, cut)}

    def block(since: datetime | None, human_only: bool = True) -> dict[str, Any]:
        rows = fs.countries(sessions, since=since, human_only=human_only)
        everyone = fs.countries(sessions, since=since, human_only=False)
        return {
            "sessions": sum(r["sessions"] for r in rows),
            "all": sum(r["sessions"] for r in everyone),
            "countries": rows,
        }

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "now": block(now - LIVE_WINDOW, human_only=False),
        "today": block(midnight),
        "d7": {**block(now - timedelta(days=7)), "change": change(7)},
        "d30": {**block(None), "change": change(COUNTRY_DAYS)},
    }


@router.get("/countries")
async def visitor_countries(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here — sessions per country for now, today, 7 and 30 days."""
    return await _country_windows()


@cached("stats:daily", ttl=DAILY_TTL)
async def _daily_line() -> dict[str, Any]:
    """The growth line: every day since the tracker's first full day.

    One fetch of the whole history, cached like /countries because it is the
    other query that grows with the calendar. Measured 2026-10-09: 16,800
    events since 17 September, fetched in 0.27 s.
    """
    now = datetime.now(UTC)
    since = datetime.combine(fs.TRACKER_FIRST_FULL_DAY, time.min, UTC)
    return fs.daily_visitors(fetch(SQL_SESSION_EVENTS, since, now), now.date())


@router.get("/daily")
async def daily(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Is the audience growing — visitors and confirmed humans per UTC day."""
    return await _daily_line()


@cached("stats:search", ttl=SEARCH_TTL)
async def _search_overview() -> dict[str, Any]:
    """Six Search Console calls, run off the event loop: google-auth's session
    is synchronous, and the first call after the hour takes seconds."""
    return await asyncio.to_thread(search_console.search_overview, datetime.now(UTC).date())


@router.get("/search")
async def search(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """How Google shows us: impressions, clicks and position per day since the
    property's first data, the last 28 finished days against the 28 before,
    the top queries and pages, and how many pages Google showed at all."""
    return await _search_overview()


@cached("stats:field-vitals", ttl=FIELD_VITALS_TTL)
async def _field_vitals() -> dict[str, Any]:
    return await crux.field_vitals()


@router.get("/field-vitals")
async def field_vitals(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Google's own speed numbers for the origin: CrUX p75 LCP, INP and CLS per
    week, phone and desktop."""
    return await _field_vitals()


@router.get("/server")
async def server(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Is the server keeping up: the host's newest sample, its days since the
    log began with the visitors of each day beside them, and the warning
    levels. Its window is its own."""
    samples = await asyncio.to_thread(server_load.read_samples)
    if samples is None:
        return {"report": None, "log_reason": server_load.unavailable_reason()}
    report = server_load.load_report(samples, datetime.now(UTC))
    daily = await _daily_line()
    visitors = {p["day"]: p["visitors"] for p in [*daily["days"], daily["today"]]}
    for day in report["days"]:
        day["visitors"] = visitors.get(day["day"])
    return {"report": report, "log_reason": None}


@router.get("/crawlers")
async def crawlers(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Which search engines and AI systems fetched our pages in the window,
    verified against their operators' published addresses."""
    fetches = await asyncio.to_thread(crawler_log.read_fetches)
    if fetches is None:
        return {"report": None, "log_reason": crawler_log.unavailable_reason()}
    since, _until = _window(days)
    ranges = await crawler_log.published_ranges()
    return {"report": crawler_log.crawler_report(fetches, ranges, since), "log_reason": None}


@router.get("/map")
async def visitor_map(
    days: int = Query(1, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    return {"points": fetch(SQL_MAP, since, until)}


#: What a /content row hands the panel. SQL_CONTENT also selects the visitor
#: behind the last hit (last_session, last_country, last_device, last_browser)
#: because /problems ranks its empty searches from the same query and names
#: that visitor - but TopContent renders none of it, and an untouched row would
#: ship up to 75 full Umami session ids, each with a country, a device and a
#: browser, into a response the page throws away. Everything else on this
#: dashboard cuts an id to fs.SESSION_ID_CHARS; this is how that rule reaches
#: the one route that shapes no row of its own.
CONTENT_KEYS = ("event_name", "label", "country", "results", "n", "visitors")


@router.get("/content")
async def content(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    rows = [{k: r[k] for k in CONTENT_KEYS} for r in fetch(SQL_CONTENT, since, until)]

    def opened(event: str) -> list[dict[str, Any]]:
        # People first: 24 opens of one site were six sessions of one laptop
        picked = [r for r in rows if r["event_name"] == event]
        return sorted(picked, key=lambda r: (-r["visitors"], -r["n"]))[:15]

    return {
        "sites": opened("site_open"),
        "stories": opened("story_open"),
        "papers": opened("paper_open"),
        # Folded from the single events: a pause mid-word is no search term
        "searches": fs.search_terms(fetch(SQL_SEARCH_EVENTS, since, until)),
    }


@router.get("/journeys")
async def journeys(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    rows = fetch(SQL_SESSION_EVENTS, since, until)
    sessions = fs.sessions_from_rows(rows)
    return {
        "chains": [{"chain": chain, "sessions": n} for chain, n in fs.journeys(sessions)],
        "pages": fs.entry_exit_pages(sessions),
        "outbound": fs.outbound_links(rows),
        # The reading funnel folds out of the same rows: scroll_depth carries
        # its own page type, so it costs no query and cannot disagree with the
        # chains above it.
        "reading": fs.reading_funnel(rows),
    }


@router.get("/problems")
async def problems(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    sessions = fs.sessions_from_rows(fetch(SQL_SESSION_EVENTS, since, until))
    return {
        "problems": fs.problems(
            sessions,
            not_found=fetch(SQL_NOT_FOUND, since, until),
            vitals=fetch(SQL_VITALS, since, until),
            errors=fetch(SQL_ERRORS, since, until),
            searches=[r for r in fetch(SQL_CONTENT, since, until) if r["event_name"] == "search"],
            webgl=fetch(SQL_WEBGL_LOST, since, until),
        )
    }


@router.get("/feedback")
async def feedback(
    days: int = Query(30, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    return {"items": fetch(SQL_FEEDBACK, since, until)}


@router.get("/sources")
async def sources(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Where the sessions came from, and how many arrivals the tracker missed.

    Two counts of one thing, deliberately side by side: Umami only sees a
    visitor whose browser ran our script, nginx sees every request. The gap
    measured on 2026-09-19 (189 Google arrivals against 62 Umami views) was
    mostly Chrome prefetching Google's results; since 2026-09-25 nginx logs
    Sec-Purpose and referral_log counts a prefetch out (its docstring has
    the measurement: Umami saw 90 % of the real views).
    """
    since, until = _window(days)
    rows = fetch(SQL_SOURCES, since, until)
    visits = referral_log.read_visits()
    return {
        "sources": [
            {
                "source": r["source"],
                "family": fs.source_family(r["source"]),
                "sessions": r["sessions"],
                "views": r["views"],
            }
            for r in rows
        ],
        "log": referral_log.coverage_report(visits, since, until) if visits is not None else None,
        "log_reason": None if visits is not None else referral_log.unavailable_reason(),
    }


@router.get("/globe")
async def globe(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Does the globe come up, how long does it take when it does, and how the
    loads that never got there ended (`not_reached`, summing to `gave_up`, and
    `abandon_ms`). One scan of /globe.html; see stats_analysis.globe_funnel."""
    since, until = _window(days)
    return fs.globe_funnel(fetch(SQL_GLOBE, since, until, path=GLOBE_PATH))


@router.get("/clusters")
async def clusters(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Browser fingerprints that are one machine, not several people. The
    denominator comes from /overview, which the page already has."""
    since, until = _window(days)
    rows = fetch(SQL_CLUSTERS, since, until, min_ids=CLUSTER_MIN_IDS)
    return fs.clusters(rows, min_ids=CLUSTER_MIN_IDS)


@router.get("/devices")
async def devices(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Phone or not, and which language the browser asked for — one scan over
    the sessions in the window, counts only."""
    since, until = _window(days)
    return fs.devices_and_languages(fetch(SQL_DEVICES, since, until))


@router.get("/live")
async def live(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here now and what they have open, and who was here last when
    nobody is. Fixed windows: the page's range switch does not touch this."""
    now = datetime.now(UTC)
    rows = fetch(SQL_LIVE, now - LIVE_LOOKBACK, now)
    here = [r for r in rows if r["last_seen"] >= now - HERE_WINDOW]
    return {
        "window_minutes": int(HERE_WINDOW.total_seconds() // 60),
        "lookback_hours": int(LIVE_LOOKBACK.total_seconds() // 3600),
        "total": len(here),
        "shown": min(len(here), LIVE_LIMIT),
        "visitors": [fs.live_row(r, now) for r in here[:LIVE_LIMIT]],
        "last": fs.live_row(rows[0], now) if rows and not here else None,
    }


#: When a click out to YouTube started to mean one (deploy 2556cc4, UTC):
#: before it, a click on a story's video poster - played in place - was
#: counted as an outbound click as well.
OUTBOUND_FIX = datetime(2026, 10, 9, 6, 42, tzinfo=UTC)


@router.get("/creators")
async def creators(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    db: Session = Depends(get_db),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """What the stories send the creators: videos started on our pages and
    clicks out to YouTube, per channel, per day and per video."""
    since, until = _window(days)
    rows = fetch(SQL_CREATOR, since, until, clicks_since=OUTBOUND_FIX)
    ids = {r["media"] for r in rows if r["media"]}
    videos = {
        v.id: (v.name, v.title)
        for v in db.query(NewsVideo.id, NewsChannel.name, NewsVideo.title)
        .join(NewsChannel, NewsVideo.channel_id == NewsChannel.id)
        .filter(NewsVideo.id.in_(ids))
        .all()
    }
    return {**fs.creator_traffic(rows, videos), "clicks_since": OUTBOUND_FIX.isoformat()}


@router.get("/members")
async def members(
    db: Session = Depends(get_db),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """The end of the funnel: signups and what members have ever done.
    Aggregates only — no name, no id, no credit balance leaves this route."""
    return members_stats.member_totals(db, jwt_auth.FOUNDER_ROLE_ID)
