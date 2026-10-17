# SPDX-License-Identifier: AGPL-3.0-only
"""Google Search Console for the founders dashboard: how Google shows us.

Reads the Search Analytics API of the domain property ``sc-domain:
ancientnerds.com`` with the read-only service account scripts/gsc_report.py
uses locally (secrets/gsc-key.json). On the VPS its key JSON is the env value
GSC_SERVICE_ACCOUNT_JSON, one line, in the .env the API containers read.

Verified against the live API on 2026-10-09: the property answers with
``responseAggregationType: byProperty``; the daily series reaches back to
2026-02-17 (232 days with impressions); the last final day lags two to three
days behind today; 4,539 pages had at least one impression in 28 days. A day
without a single impression is absent from the rows, not a zero row.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
QUERY_URL = "https://www.googleapis.com/webmasters/v3/sites/sc-domain%3Aancientnerds.com/searchAnalytics/query"
#: Search Console keeps sixteen months; ask for all of it.
HISTORY_DAYS = 486
#: The comparison window: four whole weeks, so weekdays cancel out.
WINDOW_DAYS = 28
#: Rows the panel lists per ranking.
TOP = 10
#: The API's largest page; the page count needs every row of the window.
MAX_ROWS = 25_000
SITE_PREFIX = "https://ancientnerds.com"


def _session() -> AuthorizedSession:
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GSC_SERVICE_ACCOUNT_JSON is not set - the search panel has no access to Search Console"
        )
    creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    return AuthorizedSession(creds)


def _query(
    session: AuthorizedSession, start: date, end: date, dimensions: list[str], rows: int = MAX_ROWS
) -> list[dict[str, Any]]:
    response = session.post(
        QUERY_URL,
        json={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions,
            "rowLimit": rows,
        },
        timeout=60,
    )
    response.raise_for_status()
    # The API leaves "rows" out entirely when nothing matched.
    return response.json().get("rows", [])


def _totals(session: AuthorizedSession, start: date, end: date) -> dict[str, Any]:
    """One window without dimensions: the property's own sums and average position."""
    window = {"start": start.isoformat(), "end": end.isoformat()}
    rows = _query(session, start, end, [], rows=1)
    if not rows:
        # A window without a single impression: nothing shown, nothing clicked.
        return {**window, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": None}
    row = rows[0]
    return {
        **window,
        "clicks": int(row["clicks"]),
        "impressions": int(row["impressions"]),
        "ctr": row["ctr"],
        "position": row["position"],
    }


def daily_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One point per day from the first day with data to the last, the days
    Search Console left out filled in as zeros (they had no impression)."""
    by_day = {date.fromisoformat(r["keys"][0]): r for r in rows}
    if not by_day:
        return []
    first, last = min(by_day), max(by_day)
    out = []
    for i in range((last - first).days + 1):
        day = first + timedelta(days=i)
        r = by_day.get(day)
        out.append(
            {
                "day": day.isoformat(),
                "clicks": int(r["clicks"]) if r else 0,
                "impressions": int(r["impressions"]) if r else 0,
                "position": r["position"] if r else None,
            }
        )
    return out


def _path(url: str) -> str:
    """The path of one of our URLs, "/" for the start page."""
    if not url.startswith(SITE_PREFIX):
        return url
    return url[len(SITE_PREFIX) :] or "/"


def search_overview(today: date) -> dict[str, Any]:
    """Everything the panel draws, in six calls: the daily line, the last
    finished 28 days against the 28 before them, the top queries and pages of
    the window, and how many pages Google showed at least once in each window."""
    session = _session()
    days = daily_series(_query(session, today - timedelta(days=HISTORY_DAYS), today, ["date"]))
    if not days:
        return {
            "days": [],
            "current": None,
            "previous": None,
            "queries": [],
            "pages": [],
            "pages_shown": None,
        }
    last = date.fromisoformat(days[-1]["day"])
    cur_start = last - timedelta(days=WINDOW_DAYS - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=WINDOW_DAYS - 1)
    queries = _query(session, cur_start, last, ["query"], rows=TOP)
    pages_now = _query(session, cur_start, last, ["page"])
    pages_before = _query(session, prev_start, prev_end, ["page"])
    return {
        "days": days,
        "current": _totals(session, cur_start, last),
        "previous": _totals(session, prev_start, prev_end),
        "queries": [
            {
                "query": r["keys"][0],
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "position": r["position"],
            }
            for r in queries
        ],
        # The page rows come sorted by clicks, like every Search Analytics answer.
        "pages": [
            {
                "path": _path(r["keys"][0]),
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "position": r["position"],
            }
            for r in pages_now[:TOP]
        ],
        "pages_shown": {"current": len(pages_now), "previous": len(pages_before)},
    }
