# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: thirteen endpoints under /api/stats, all
behind the ``an_stats`` cookie (stats_access.require_stats_session). Umami rows
come from pipeline.umami_db, the member counts from pipeline.members_stats,
nginx's referral log from pipeline.referral_log, and every founder-level
shaping from pipeline.stats_analysis.

``fetch`` is imported as a module attribute on purpose: the tests replace
``fr.fetch`` and never touch a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.cache import cached
from api.routes.stats_access import require_stats_session
from api.services import jwt_auth
from pipeline import members_stats, referral_log
from pipeline import stats_analysis as fs
from pipeline.database import get_db
from pipeline.umami_db import (
    CLUSTER_MIN_IDS,
    GLOBE_PATH,
    SQL_CLUSTERS,
    SQL_CONTENT,
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


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


@router.get("/overview")
async def overview(
    days: int = Query(7, ge=1, le=90),
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
    sessions = fs.sessions_from_rows(
        fetch(SQL_SESSION_EVENTS, now - timedelta(days=COUNTRY_DAYS), now)
    )

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
        "d7": block(now - timedelta(days=7)),
        "d30": block(None),
    }


@router.get("/countries")
async def visitor_countries(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here — sessions per country for now, today, 7 and 30 days."""
    return await _country_windows()


@router.get("/map")
async def visitor_map(
    days: int = Query(1, ge=1, le=30),
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
    days: int = Query(7, ge=1, le=90),
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
    days: int = Query(7, ge=1, le=90),
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
    days: int = Query(7, ge=1, le=90),
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
    days: int = Query(30, ge=1, le=365),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    return {"items": fetch(SQL_FEEDBACK, since, until)}


@router.get("/sources")
async def sources(
    days: int = Query(7, ge=1, le=90),
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
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Does the globe come up, how long does it take when it does, and how the
    loads that never got there ended (`not_reached`, summing to `gave_up`, and
    `abandon_ms`). One scan of /globe.html; see stats_analysis.globe_funnel."""
    since, until = _window(days)
    return fs.globe_funnel(fetch(SQL_GLOBE, since, until, path=GLOBE_PATH))


@router.get("/clusters")
async def clusters(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Browser fingerprints that are one machine, not several people. The
    denominator comes from /overview, which the page already has."""
    since, until = _window(days)
    rows = fetch(SQL_CLUSTERS, since, until, min_ids=CLUSTER_MIN_IDS)
    return fs.clusters(rows, min_ids=CLUSTER_MIN_IDS)


@router.get("/devices")
async def devices(
    days: int = Query(7, ge=1, le=90),
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


@router.get("/members")
async def members(
    db: Session = Depends(get_db),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """The end of the funnel: signups and what members have ever done.
    Aggregates only — no name, no id, no credit balance leaves this route."""
    return members_stats.member_totals(db, jwt_auth.FOUNDER_ROLE_ID)
