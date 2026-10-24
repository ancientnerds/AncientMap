# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: twenty endpoints under /api/stats, all
behind the ``an_stats`` cookie (stats_access.require_stats_session). Umami rows
come from pipeline.umami_db, the member counts from pipeline.members_stats,
nginx's referral, crawler and request logs from pipeline.referral_log,
pipeline.crawler_log and pipeline.request_log, Google's view of us (Search
Console, CrUX) from api/services, every visitor class from
pipeline.visitor_class, and every founder-level shaping from
pipeline.stats_analysis.

``fetch`` is imported as a module attribute on purpose: the tests replace
``fr.fetch`` and never touch a database.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.cache import cached
from api.routes.stats_access import require_stats_session
from api.services import crux, jwt_auth, search_console
from pipeline import crawler_log, members_stats, referral_log, request_log, server_load
from pipeline import stats_analysis as fs
from pipeline import visitor_class as vc
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
#: Who the Now tile counts: the humans, and the arrivals no rule has decided
#: yet - a visitor who arrived thirty seconds ago has one page view and no act
#: to their name. A session a machine rule marked is left out (owner,
#: 2026-10-22) and counted beside it as `bots`.
LIVE_CLASSES = frozenset({*vc.HUMAN_CLASSES, "undecided"})
#: The live panel's own window, and how far back it looks for the last visitor
#: when nobody is here. Measured 2026-09-19: a thirty-minute window was empty
#: in 20 % of all minutes and the longest gap between two events was 117
#: minutes, so a 24-hour lookback always names somebody. It is the window in
#: which a new arrival counts as undecided, so it is that one object.
HERE_WINDOW = vc.UNDECIDED_WINDOW
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
#: How long /visitors is reused: the dashboard asks every five minutes, and
#: the requests part re-reads its log only when a file of it changed.
VISITORS_TTL = 300
#: The bursts /visitors lists: those that ended in the last BURST_DAYS, at
#: most BURST_LIST of them, newest first.
BURST_DAYS = 7
BURST_LIST = 10
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


@cached("stats:month", ttl=COUNTRY_TTL)
async def _month_fold() -> dict[str, Any]:
    """The four flag tiles and the live list's visitor classes from one
    thirty-day fold.

    Cached rather than recomputed per request: this is the only query on the
    page that reaches back a month. The cache is api/cache.py's - Redis when
    it is up, and then both API containers share one copy; a bounded
    per-process dict when it is not, and then they do not. No argument, so the
    key is the prefix and no founder's session ever reaches it.

    The month is also the lookback the machine rules need: a burst, a day's
    volume and a lockstep crawl are judged against every start of the
    fingerprint in it, so a session that is live now is classed against its
    whole history and not against the last five minutes. `live_classes` maps
    every session seen in the last LIVE_LOOKBACK to its class, for /live.
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

    def block(since: datetime | None, classes: frozenset[str] = vc.HUMAN_CLASSES) -> dict[str, Any]:
        rows = fs.countries(sessions, now=now, since=since, classes=classes)
        everyone = fs.countries(sessions, now=now, since=since, classes=None)
        return {
            "sessions": sum(r["sessions"] for r in rows),
            "all": sum(r["sessions"] for r in everyone),
            "countries": rows,
        }

    def bots(since: datetime) -> dict[str, Any]:
        """The JS scrapers beside the Now tile's people, with the country most
        of them came from ("??" where Umami could not place them)."""
        rows = fs.countries(sessions, now=now, since=since, classes={"scraper_js"})
        return {
            "sessions": sum(r["sessions"] for r in rows),
            "country": rows[0]["country"] if rows else None,
        }

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    live = now - LIVE_LOOKBACK
    return {
        "countries": {
            "now": {**block(now - LIVE_WINDOW, LIVE_CLASSES), "bots": bots(now - LIVE_WINDOW)},
            "today": block(midnight),
            "d7": {**block(now - timedelta(days=7)), "change": change(7)},
            "d30": {**block(None), "change": change(COUNTRY_DAYS)},
        },
        "live_classes": {
            str(s.id): vc.session_class(s, now)[0]
            for s in sessions
            if s.last_seen is not None and s.last_seen >= live
        },
    }


@router.get("/countries")
async def visitor_countries(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here — sessions per country for now, today, 7 and 30 days; on
    the Now tile the people, with the JS scrapers counted beside them."""
    return (await _month_fold())["countries"]


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


def _daily_classes(
    rows: list[dict[str, Any]], sessions: list[fs.Session], now: datetime
) -> list[dict[str, Any]]:
    """Sessions per UTC day and class, oldest first, folded a day at a time
    as stats_analysis.daily_visitors does (fs.sessions_per_day)."""
    per_day = fs.sessions_per_day(rows, sessions)
    out = []
    for day in sorted(per_day):
        counts = Counter(vc.session_class(s, now)[0] for s in per_day[day])
        out.append({"day": day.isoformat(), **{c: counts[c] for c in vc.SESSION_CLASSES}})
    return out


def _ssr_pageviews(rows: list[dict[str, Any]], since: datetime) -> int:
    """Umami's side of beacon_check: page views from `since` on, on the paths
    the server renders, without the arrivals from a search engine - the same
    paths and the same cut request_log applies to its browser_js pages, so the
    two are counted alike and set side by side, never joined."""
    return sum(
        1
        for r in rows
        if r["event_type"] == 1
        and r["created_at"] >= since
        and request_log.ssr_page(r["url_path"] or "/")
        and not request_log.from_search(r["referrer_domain"] or "", f"GET {r['url_path']}")
    )


@cached("stats:visitors", ttl=VISITORS_TTL)
async def _visitors(days: int) -> dict[str, Any]:
    """Both halves of "Who is visiting?": Umami's sessions by class over the
    window, and nginx's request log by class over its own REQUEST_DAYS.

    The requests part runs off the event loop: a first read parses up to a
    week of log lines and loads the ASN table (about a second). Without
    requests.log (every dev box, and the VPS before the deploy that adds the
    log) it is null and `log_reason` says why; the operators' ranges are then
    not fetched at all, as in /crawlers.
    """
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    report = None
    if request_log.LOG_PATH.exists():
        ranges = await crawler_log.published_ranges()
        report = await asyncio.to_thread(request_log.report, ranges, now)
    asn_reason = await asyncio.to_thread(request_log.asn_reason)
    # One fetch for both halves: back to the request log's first line when
    # that lies before the window, for the beacon check's Umami count.
    covered = (
        datetime.fromisoformat(report["covered_from"])
        if report is not None and report["covered_from"] is not None
        else now
    )
    rows = fetch(SQL_SESSION_EVENTS, min(since, covered), now)
    window = [r for r in rows if r["created_at"] >= since]
    sessions = fs.sessions_from_rows(window)
    recent = now - timedelta(days=BURST_DAYS)
    bursts = [
        {**b, "start": b["start"].isoformat(), "end": b["end"].isoformat()}
        for b in vc.bursts(sessions)
        if b["end"] >= recent
    ]
    if report is not None:
        report = {
            **report,
            "beacon_check": {
                **report["beacon_check"],
                "umami_pageviews": _ssr_pageviews(rows, covered),
            },
        }
    return {
        "days": days,
        # The panel prints these; one definition, in visitor_class.
        "labels": vc.LABELS,
        "sessions": vc.session_counts(sessions, now),
        "daily": _daily_classes(window, sessions, now),
        "bursts": bursts[:BURST_LIST],
        "requests": {
            "report": report,
            "log_reason": None if report is not None else request_log.unavailable_reason(),
            "asn_reason": asn_reason,
        },
    }


@router.get("/visitors")
async def visitors(
    days: int = Query(7, ge=1, le=ALL_DAYS_MAX),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is visiting: the sessions that ran our JavaScript by class (human,
    from an AI answer, JS scraper, undecided, unclear) with the rule behind
    each, the recent bursts, and every page request nginx logged by what sent
    it (pipeline/visitor_class.py has every rule). The two are never joined
    per visitor."""
    return await _visitors(days)


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
            vitals=fetch(SQL_VITALS, since, until, sessions=fs.human_ids(sessions)),
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
    nobody is. Fixed windows: the page's range switch does not touch this.

    Bots stay in the list, each row labelled with its visitor class from the
    thirty-day fold /countries shares (owner, 2026-10-22). That fold is up to
    COUNTRY_TTL old, so a session that arrived after it has no class yet:
    `class` is null for it, not a guess."""
    now = datetime.now(UTC)
    rows = fetch(SQL_LIVE, now - LIVE_LOOKBACK, now)
    here = [r for r in rows if r["last_seen"] >= now - HERE_WINDOW]
    classes = (await _month_fold())["live_classes"]

    def row(r: dict[str, Any]) -> dict[str, Any]:
        return {**fs.live_row(r, now), "class": classes.get(str(r["session"]))}

    return {
        "window_minutes": int(HERE_WINDOW.total_seconds() // 60),
        "lookback_hours": int(LIVE_LOOKBACK.total_seconds() // 3600),
        "total": len(here),
        "shown": min(len(here), LIVE_LIMIT),
        "visitors": [row(r) for r in here[:LIVE_LIMIT]],
        "last": row(rows[0]) if rows and not here else None,
    }


#: When a click out to YouTube started to mean one (deploy 2556cc4, the same
#: deploy as the scroll capture): before it, a click on a story's video
#: poster - played in place - was counted as an outbound click as well.
OUTBOUND_FIX = fs.CAPTURE_FIX


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
