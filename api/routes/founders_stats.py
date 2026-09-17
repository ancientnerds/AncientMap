# SPDX-License-Identifier: AGPL-3.0-only
"""The founders dashboard's data: five endpoints under /api/stats, all behind
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
from api.services import founders_stats as fs
from pipeline.umami_db import (
    SQL_CONTENT,
    SQL_FEEDBACK,
    SQL_HOUR_BUCKETS,
    SQL_MAP,
    SQL_OVERVIEW,
    SQL_SESSION_EVENTS,
    SQL_SOURCES,
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
