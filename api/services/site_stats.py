# SPDX-License-Identifier: AGPL-3.0-only
"""Site counts shared by /api/stats and the homepage (api/routes/landing_html.py).

One query set, one 5-minute cache. `curated_countries` is the number of
countries with ancient_nerds sites — the same set the /sites/{country}
hubs are built from, so the hero counter and the hub list agree.
"""

from __future__ import annotations

from sqlalchemy import text

from api.cache import cache_get, cache_set
from pipeline.database import get_session

# v2: the pre-2026-09 value under "api:stats" has no curated_countries and
# survives a deploy in Redis — the homepage hero would KeyError on it.
CACHE_KEY = "api:stats:v2"


def get_site_stats() -> dict:
    cached = cache_get(CACHE_KEY)
    if cached:
        return cached
    with get_session() as session:
        total_sites = session.execute(text("SELECT COUNT(*) FROM unified_sites")).scalar()
        by_source = {
            row.source_id: row.count
            for row in session.execute(
                text(
                    """
                    SELECT source_id, COUNT(*) AS count
                    FROM unified_sites
                    GROUP BY source_id
                    ORDER BY count DESC
                    """
                )
            )
        }
        curated_countries = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT country) FROM unified_sites
                WHERE source_id = 'ancient_nerds' AND country IS NOT NULL AND country <> ''
                """
            )
        ).scalar()
    response = {
        "total_sites": total_sites,
        "by_source": by_source,
        "curated_countries": curated_countries or 0,
    }
    cache_set(CACHE_KEY, response, ttl=300)
    return response
