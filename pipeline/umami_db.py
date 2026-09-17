# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only access to Umami's tables for the founders dashboard and the
alerts. Same Postgres as everything else, its own database ``umami``, its own
role (UMAMI_DB_PASSWORD from the VPS .env). Every query is parameterised and
scoped to one website and a half-open time window [:since, :until); nothing
here writes.

Umami 3 columns this relies on (verified on production, 2026-09-17):
``website_event`` (event_id, website_id, session_id, created_at, url_path,
referrer_domain, utm_source, event_type, event_name), ``event_data``
(website_event_id, data_key, string_value, number_value) and ``session``
(session_id, country, city, device). event_type 1 = pageview, 2 = custom event.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from pipeline.config import settings

#: The Umami website whose events we read — the same id the tracker tag carries.
logger = logging.getLogger(__name__)

WEBSITE_ID = os.getenv("VITE_UMAMI_WEBSITE_ID", "")


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Lazy: importing this module never connects; the first query does.
    A missing UMAMI_DB_PASSWORD is a misconfigured deploy and fails loudly."""
    password = os.environ["UMAMI_DB_PASSWORD"]
    url = URL.create(
        "postgresql",
        username="umami",
        password=password,
        host=settings.database.host,
        port=settings.database.port,
        database="umami",
    )
    return create_engine(url, pool_pre_ping=True, pool_size=2, connect_args={"connect_timeout": 10})


SQL_OVERVIEW = """
SELECT
  count(*) FILTER (WHERE event_type = 1)                        AS views,
  count(DISTINCT session_id)                                    AS sessions,
  count(DISTINCT session_id) FILTER (WHERE created_at >= :live) AS live_sessions
FROM website_event
WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
"""

SQL_MAP = """
SELECT s.country, s.city, date_part('hour', e.created_at AT TIME ZONE 'UTC')::int AS hour,
       count(DISTINCT e.session_id) AS sessions
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.event_type = 1
  AND e.created_at >= :since AND e.created_at < :until
GROUP BY 1, 2, 3
"""

SQL_HOUR_BUCKETS = """
SELECT date_trunc('hour', created_at) AS hour, count(*) FILTER (WHERE event_type = 1) AS views,
       count(DISTINCT session_id) AS sessions
FROM website_event
WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 1
"""

SQL_SESSION_EVENTS = """
SELECT e.session_id, e.created_at, e.event_type, e.event_name, e.url_path, e.referrer_domain,
       e.utm_source, s.country, s.device,
       (SELECT jsonb_object_agg(d.data_key, coalesce(d.string_value, d.number_value::text))
          FROM event_data d WHERE d.website_event_id = e.event_id) AS data
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.created_at >= :since AND e.created_at < :until
ORDER BY e.session_id, e.created_at
"""

#: Two levels: first one row per event (event_data is key-value, so a site's
#: name and its country live in separate rows), then the ranking. Without the
#: first level a site would lose its country and a search its result count.
SQL_CONTENT = """
WITH ev AS (
    SELECT
        e.event_id,
        e.event_name,
        max(d.string_value) FILTER (
            WHERE d.data_key IN ('name', 'story', 'paper', 'q')
        ) AS label,
        max(d.string_value) FILTER (WHERE d.data_key = 'country') AS country,
        max(d.number_value) FILTER (WHERE d.data_key = 'results') AS results
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    WHERE e.website_id = :website_id AND e.event_type = 2
      AND e.created_at >= :since AND e.created_at < :until
      AND e.event_name IN ('site_open', 'story_open', 'paper_open', 'search')
    GROUP BY e.event_id, e.event_name
)
SELECT
    event_name,
    label,
    max(country) AS country,
    min(results) AS results,
    count(*) AS n
FROM ev
WHERE label IS NOT NULL AND label <> ''
GROUP BY event_name, label
ORDER BY n DESC
LIMIT 300
"""

SQL_FEEDBACK = """
SELECT e.created_at, e.url_path,
       max(d.string_value) FILTER (WHERE d.data_key = 'prompt') AS prompt,
       max(d.string_value) FILTER (WHERE d.data_key = 'answer') AS answer,
       max(d.string_value) FILTER (WHERE d.data_key = 'text')   AS text
FROM website_event e JOIN event_data d ON d.website_event_id = e.event_id
WHERE e.website_id = :website_id AND e.event_name = 'feedback'
  AND e.created_at >= :since AND e.created_at < :until
GROUP BY e.event_id, e.created_at, e.url_path ORDER BY e.created_at DESC LIMIT 200
"""

SQL_SOURCES = """
SELECT coalesce(nullif(utm_source, ''), nullif(referrer_domain, ''), 'direct') AS source,
       count(DISTINCT session_id) AS sessions
FROM website_event
WHERE website_id = :website_id AND event_type = 1
  AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 2 DESC LIMIT 40
"""


def fetch(sql: str, since: datetime, until: datetime, **params: Any) -> list[dict[str, Any]]:
    """Run one of the SQL_* texts for our website and the window [since, until)."""
    if not WEBSITE_ID:
        # Empty id would silently return zero rows for every panel — the
        # deploy forgot VITE_UMAMI_WEBSITE_ID in the container env.
        logger.warning("VITE_UMAMI_WEBSITE_ID is empty — every stats query returns nothing")
    with engine().connect() as conn:
        rows = conn.execute(
            text(sql), {"website_id": WEBSITE_ID, "since": since, "until": until, **params}
        )
        return [dict(r._mapping) for r in rows]
