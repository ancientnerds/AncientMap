"""Shared archaeological-site lookup against ``unified_sites``.

Lives in ``pipeline/`` so both containers can reach it. The query used to sit
inside ``api.services.lyra_tools.search_sites``, a LangChain ``@tool``; the
Lyra image ships ``pipeline/`` only (see Dockerfile.lyra), so
``UnifiedSitesAdapter`` raised ``ModuleNotFoundError: No module named 'api'``
on every research query and silently returned no sources. Our own curated,
tier-1 site data was therefore absent from every weekly journal since at least
2026-07-05.

Only SQLAlchemy and ``pipeline.database`` are needed here, so this works in the
Lyra container unchanged. ``api`` re-exports both helpers for its callers.
"""

from __future__ import annotations

from sqlalchemy import text

from pipeline.database import get_session

# Columns every caller needs. Kept in one place so the two ORDER BY variants
# below cannot drift apart.
_SELECT_COLUMNS = """
    s.id::text, s.name, s.lat, s.lon, s.site_type, s.period_name,
    s.period_start, s.country, s.description, s.thumbnail_url
"""


def escape_ilike(value: str) -> str:
    """Escape ILIKE metacharacters (%, _, \\) so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_sites(
    query: str,
    period: str | None = None,
    country: str | None = None,
    site_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search archaeological sites by name, period, country, or type.

    Args:
        query: Search text (site name, keyword, or description fragment).
        period: Filter by period name (e.g. 'Bronze Age').
        country: Filter by country (e.g. 'Turkey').
        site_type: Filter by site type (e.g. 'settlement').
        limit: Maximum results (default 10, capped at 25).

    Returns:
        Site dicts, deduplicated by name with the highest-priority source kept.
        Empty when nothing matches.
    """
    query = (query or "")[:500].strip()
    limit = max(1, min(limit, 25))
    conditions = ["1=1"]
    params: dict = {"limit": limit}

    if query:
        conditions.append(
            "(unaccent(s.name) ILIKE unaccent(:q) OR s.description ILIKE :q "
            "OR unaccent(s.name_normalized) ILIKE unaccent(:q_norm))"
        )
        q_safe = escape_ilike(query)
        params["q"] = f"%{q_safe}%"
        params["q_norm"] = f"%{q_safe.lower()}%"

    if period:
        conditions.append("s.period_name ILIKE :period")
        params["period"] = f"%{escape_ilike(period)}%"

    if country:
        conditions.append("s.country ILIKE :country")
        params["country"] = f"%{escape_ilike(country)}%"

    if site_type:
        conditions.append("s.site_type ILIKE :site_type")
        params["site_type"] = f"%{escape_ilike(site_type)}%"

    where = " AND ".join(conditions)
    # Exact-name matches first, but only when there is a name to match on.
    name_match_rank = (
        "CASE WHEN unaccent(s.name) ILIKE unaccent(:q) THEN 0 ELSE 1 END,\n" if query else ""
    )
    sql = f"""
        SELECT {_SELECT_COLUMNS}
        FROM unified_sites s
        LEFT JOIN source_meta sm ON s.source_id = sm.id
        WHERE {where}
        ORDER BY
            {name_match_rank}sm.priority ASC NULLS LAST,
            s.period_start ASC NULLS LAST
        LIMIT :limit
    """

    with get_session() as session:
        rows = session.execute(text(sql), params).fetchall()

    sites: list[dict] = []
    seen_names: set[str] = set()
    for r in rows:
        norm = r.name.lower().strip()
        if norm in seen_names:
            continue
        seen_names.add(norm)

        site = {
            "id": r.id,
            "name": r.name,
            "lat": round(r.lat, 4),
            "lon": round(r.lon, 4),
            "type": r.site_type,
            "period": r.period_name,
            "country": r.country,
        }
        if r.thumbnail_url:
            site["thumbnail_url"] = r.thumbnail_url
        if r.description:
            site["description"] = r.description[:400]
        sites.append(site)

    return sites
