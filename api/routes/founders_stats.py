# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: seven endpoints under /api/stats, all behind
the ``an_stats`` cookie (stats_access.require_stats_session). Rows come from
pipeline.umami_db, the founder-level shaping from api.services.founders_stats.

``fetch`` is imported as a module attribute on purpose: the tests replace
``fr.fetch`` and never touch a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.routes.stats_access import require_stats_session
from pipeline import stats_analysis as fs
from pipeline.umami_db import (
    SQL_CONTENT,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_HOUR_BUCKETS,
    SQL_MAP,
    SQL_NOT_FOUND,
    SQL_OVERVIEW,
    SQL_SESSION_EVENTS,
    SQL_SOURCES,
    SQL_VITALS,
    fetch,
)

router = APIRouter()

#: "Live" on the pulse tile = sessions with an event in the last five minutes.
LIVE_WINDOW = timedelta(minutes=5)


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


@router.get("/overview")
async def overview(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    now = datetime.now(UTC)

    def block(since: datetime, until: datetime) -> dict[str, int]:
        row = fetch(SQL_OVERVIEW, since, until, live=now - LIVE_WINDOW)[0]
        return {"views": row["views"], "sessions": row["sessions"], "live": row["live_sessions"]}

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = block(midnight, now)
    # Yesterday up to the same time of day, so the two tiles compare like with like.
    yesterday = block(midnight - timedelta(days=1), now - timedelta(days=1))
    since, until = _window(days)
    sessions = fs.sessions_from_rows(fetch(SQL_SESSION_EVENTS, since, until))
    human = [s for s in sessions if s.human]
    return {
        "today": today,
        "yesterday": yesterday,
        "days": days,
        "sessions": {"all": len(sessions), "human": len(human)},
        "types": fs.session_type_shares(sessions),
        "hours": fetch(SQL_HOUR_BUCKETS, since, until),
    }


#: The flag row's longest window. One fetch serves all four tiles — the
#: shorter ones are slices of it, so the panel costs a single query.
COUNTRY_DAYS = 30


@router.get("/countries")
async def visitor_countries(
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    """Who is here — sessions per country for now, today, 7 and 30 days."""
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


@router.get("/map")
async def visitor_map(
    days: int = Query(1, ge=1, le=30),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    return {"points": fetch(SQL_MAP, since, until)}


@router.get("/content")
async def content(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    rows = fetch(SQL_CONTENT, since, until)
    return {
        "sites": [r for r in rows if r["event_name"] == "site_open"][:15],
        "stories": [r for r in rows if r["event_name"] == "story_open"][:15],
        "papers": [r for r in rows if r["event_name"] == "paper_open"][:15],
        "searches": [r for r in rows if r["event_name"] == "search"][:30],
    }


@router.get("/journeys")
async def journeys(
    days: int = Query(7, ge=1, le=90),
    _session: dict = Depends(require_stats_session),
) -> dict[str, Any]:
    since, until = _window(days)
    sessions = fs.sessions_from_rows(fetch(SQL_SESSION_EVENTS, since, until))
    return {
        "chains": [{"chain": chain, "sessions": n} for chain, n in fs.journeys(sessions)],
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
    since, until = _window(days)
    rows = fetch(SQL_SOURCES, since, until)
    return {
        "sources": [
            {
                "source": r["source"],
                "family": fs.source_family(r["source"]),
                "sessions": r["sessions"],
            }
            for r in rows
        ]
    }
