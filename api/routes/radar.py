"""
Lyra Radar API — site candidates for the curated (``ancient_nerds``) set.

A candidate is a place named in our own content that is not in the curated
5,004-site set. It may well exist under one of the bulk external sources
(osm_historic, wikidata, vici_org, geonames …), and usually does — 377 of the
553 cards live on prod on 2026-09-14 did. That is not a duplicate, it is
enrichment: the external row supplies coordinates and metadata the curated set
still lacks. `data_sources` and `external_sources` on each item say which.

Shows enriched, promoted ("added") and rejected items. `matched` (resolved to a
curated site) and `not_a_site` are excluded.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern, cache_get, cache_set
from api.services.jwt_auth import require_founder
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import DiscordUser, get_db
from pipeline.utils.text import categorize_period, normalize_name

_radar_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="heavy_radar")

logger = logging.getLogger(__name__)
router = APIRouter()

# 60s, not 300s. The Lyra pipeline cannot bust this cache — import-linter
# forbids pipeline importing api — so the TTL is the whole staleness budget. At
# 5 minutes a founder who approved a card kept seeing it come back.
CACHE_TTL = 60


def _require_uuid(value: str, status_code: int, detail: str) -> None:
    """Reject non-UUID identifiers before they hit Postgres (avoids 500s)."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=status_code, detail=detail) from None


# The enrichment score, as ONE SQL expression. It used to be written out five
# times (here as dead Python, plus /list, /map, /sites-map, plus SCORE_WEIGHTS
# in the frontend) and the copies had drifted: two of them scored period_name
# differently, so 167 of 553 cards showed a percentage that disagreed with the
# number the list had sorted them by. `p` is the table alias to score.
def _score_sql(p: str) -> str:
    return f"""(25
     + CASE WHEN {p}.lat IS NOT NULL AND {p}.lon IS NOT NULL THEN 20 ELSE 0 END
     + CASE WHEN {p}.country IS NOT NULL AND {p}.country != '' THEN 10 ELSE 0 END
     + CASE WHEN {p}.site_type IS NOT NULL AND {p}.site_type != '' THEN 10 ELSE 0 END
     + CASE WHEN {p}.period_name IS NOT NULL AND {p}.period_name != '' THEN 10 ELSE 0 END
     + CASE WHEN LENGTH({p}.description) >= 50 THEN 10 ELSE 0 END
     + CASE WHEN {p}.wikipedia_url IS NOT NULL THEN 5 ELSE 0 END
     + CASE WHEN {p}.thumbnail_url IS NOT NULL THEN 5 ELSE 0 END
     + CASE WHEN {p}.wikidata_id IS NOT NULL THEN 5 ELSE 0 END
    )"""


def _missing_core_fields(item: dict) -> list[str]:
    """Fields required for manual promotion. Wikipedia/thumbnail/QID are score
    bonuses, not blockers — newly discovered sites rarely have them."""
    missing = []
    if item.get("lat") is None or item.get("lon") is None:
        missing.append("coordinates")
    if not item.get("country"):
        missing.append("country")
    if not item.get("site_type"):
        missing.append("site_type")
    if len(item.get("description") or "") < 50:
        missing.append("description")
    return missing


def _apply_overrides(item: dict, overrides: dict) -> dict:
    """Merge founder-supplied field overrides onto a contribution dict.

    Returns a new dict; None values in overrides are ignored (field not sent).
    """
    merged = dict(item)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return merged


class PromoteOverrides(BaseModel):
    """Founder-supplied field fixes applied at promotion time only.

    Never persisted onto the un-promoted contribution — that would be
    clobbered by the next enrichment pass when the facts hash changes.
    """

    name: str | None = Field(None, min_length=2, max_length=500)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    country: str | None = Field(None, max_length=100)
    site_type: str | None = Field(None, max_length=100)
    period_name: str | None = Field(None, max_length=100)
    period_start: int | None = None
    period_end: int | None = None
    description: str | None = None


def _review_entry(action: str, username: str, **extra) -> dict:
    return {
        "action": action,
        "user": username,
        "at": datetime.now(UTC).isoformat(),
        **extra,
    }


def _build_video_refs(videos_json: list[dict] | None) -> list[dict]:
    """Deduplicate and format video references from a JSON aggregate."""
    videos: list[dict[str, object]] = []
    seen = set()
    if not videos_json:
        return videos
    for v in videos_json:
        vid = v.get("video_id")
        if vid and vid not in seen:
            seen.add(vid)
            ts = v.get("timestamp_seconds") or 0
            deep_url = f"https://www.youtube.com/watch?v={vid}"
            if ts > 0:
                deep_url += f"&t={ts}s"
            videos.append(
                {
                    "video_id": vid,
                    "channel_name": v.get("channel_name", ""),
                    "timestamp_seconds": ts,
                    "deep_url": deep_url,
                }
            )
    return videos


def _flatten_facts(all_facts: list | None) -> list[str]:
    """Flatten and deduplicate nested fact arrays."""
    unique = set()
    if not all_facts:
        return []
    for fact_list in all_facts:
        if isinstance(fact_list, list):
            for fact in fact_list:
                if isinstance(fact, str) and fact.strip():
                    unique.add(fact.strip())
    return sorted(unique)


def _find_nearest_an_sites_batch(
    db: Session,
    items: list[dict],
    max_km: float = 10.0,
) -> dict[str, dict]:
    """Find closest AN Originals site within max_km for each item with coords.

    Returns dict mapping item_id -> {"name": ..., "distance_km": ...}.
    Uses a single query with a VALUES list + LATERAL JOIN.
    """
    coords = [
        (it["id"], it["lat"], it["lon"])
        for it in items
        if it.get("lat") is not None and it.get("lon") is not None
    ]
    if not coords:
        return {}

    delta = max_km / 111.0

    # Build parameterized VALUES rows: (:idx_0, :lat_0, :lon_0), ...
    value_fragments = []
    params: dict = {"delta": delta, "max_km": max_km}
    for i, (_, lat, lon) in enumerate(coords):
        value_fragments.append(f"(:idx_{i}, :lat_{i}, :lon_{i})")
        params[f"idx_{i}"] = i
        params[f"lat_{i}"] = float(lat)
        params[f"lon_{i}"] = float(lon)

    values_clause = ", ".join(value_fragments)

    rows = db.execute(
        text(f"""
        WITH candidates(idx, clat, clon) AS (
            VALUES {values_clause}
        )
        SELECT DISTINCT ON (c.idx)
            c.idx,
            us.id::text AS an_site_id,
            us.name,
            SQRT(POW((c.clat - us.lat) * 111.0, 2)
               + POW((c.clon - us.lon) * 111.0 * COS(RADIANS(c.clat)), 2)) AS dist_km
        FROM candidates c
        JOIN unified_sites us
          ON us.source_id = 'ancient_nerds'
         AND us.lat BETWEEN c.clat - :delta AND c.clat + :delta
         AND us.lon BETWEEN c.clon - :delta AND c.clon + :delta
        WHERE SQRT(POW((c.clat - us.lat) * 111.0, 2)
                 + POW((c.clon - us.lon) * 111.0 * COS(RADIANS(c.clat)), 2)) <= :max_km
        ORDER BY c.idx, dist_km
    """),
        params,
    ).fetchall()

    result: dict[str, dict] = {}
    for row in rows:
        item_id = coords[row.idx][0]
        if item_id not in result:  # DISTINCT ON handles this, but be safe
            result[item_id] = {
                "site_id": row.an_site_id,
                "name": row.name,
                "distance_km": round(row.dist_km, 1),
            }
    return result


@router.get("/map")
def get_radar_map_data(db: Session = Depends(get_db)):
    """Lightweight endpoint for map pins — just coords + display fields."""
    cache_key = "radar:map"
    cached = cache_get(cache_key)
    if cached:
        return cached

    rows = db.execute(
        text(f"""
        SELECT uc.id::text, uc.source, COALESCE(uc.corrected_name, uc.name) AS display_name,
               COALESCE(uc.enrichment_status, 'pending') AS enrichment_status,
               uc.country, uc.site_type, uc.period_name, uc.period_start, uc.lat, uc.lon,
               uc.description, uc.wikipedia_url, uc.thumbnail_url, uc.wikidata_id,
               {_score_sql("uc")} AS enrichment_score,
               uc.mention_count
        FROM user_contributions uc
        WHERE uc.source IN ('lyra', 'user')
          AND COALESCE(uc.enrichment_status, 'pending') NOT IN ('matched', 'not_a_site', 'failed')
          AND uc.lat IS NOT NULL AND uc.lon IS NOT NULL
        LIMIT 5000
    """)
    ).fetchall()

    result = [dict(r._mapping) for r in rows]
    cache_set(cache_key, result, ttl=CACHE_TTL)
    return result


_VISIBLE_CLAUSE = (
    "COALESCE(uc.enrichment_status, 'pending') NOT IN ('failed', 'not_a_site', 'matched')"
)

_STATUS_CLAUSES = {
    "all": _VISIBLE_CLAUSE,
    "enriched": "uc.enrichment_status = 'enriched'",
    "added": "uc.enrichment_status = 'promoted'",
    "rejected": "uc.enrichment_status IN ('rejected', 'dismissed')",
}


def _build_radar_query(status_clause: str, order_clause: str, single_id: bool = False) -> str:
    """The one radar item query. /list pages it; /item/{id} fetches one row.

    Both need identical fields — a dot on the map that renders a different
    shape of card than the list is how the two panes drift apart.
    """
    id_filter = "AND uc.id = CAST(:contribution_id AS uuid)" if single_id else ""
    pagination = "" if single_id else "LIMIT :limit OFFSET :offset"
    return f"""
        WITH contrib AS (
            SELECT
                uc.id,
                uc.source,
                uc.name,
                uc.corrected_name,
                uc.enrichment_status,
                uc.mention_count,
                uc.country,
                uc.site_type,
                uc.period_name,
                uc.period_start,
                uc.period_end,
                uc.thumbnail_url,
                uc.wikipedia_url,
                uc.enrichment_data,
                uc.created_at,
                uc.lat,
                uc.lon,
                uc.description,
                uc.wikidata_id,
                {_score_sql("uc")} AS computed_score
            FROM user_contributions uc
            WHERE uc.source IN ('lyra', 'user')
              AND {status_clause}
              AND uc.mention_count >= :min_mentions
              {id_filter}
        ),
        video_agg AS (
            SELECT
                c.id AS contrib_id,
                jsonb_agg(DISTINCT jsonb_build_object(
                    'video_id', ni.video_id,
                    'channel_name', nc.name,
                    'timestamp_seconds', ni.timestamp_seconds
                )) AS videos,
                jsonb_agg(ni.facts) FILTER (WHERE ni.facts IS NOT NULL) AS all_facts,
                COUNT(DISTINCT ni.video_id) AS unique_videos,
                COUNT(DISTINCT nc.id) AS unique_channels,
                MAX(ni.created_at) AS last_mentioned,
                (ARRAY_AGG(ni.screenshot_url ORDER BY ni.created_at DESC) FILTER (WHERE ni.screenshot_url IS NOT NULL))[1] AS latest_screenshot_url,
                AVG(ni.significance) FILTER (WHERE ni.significance IS NOT NULL) AS avg_significance,
                MODE() WITHIN GROUP (ORDER BY ni.news_category) FILTER (WHERE ni.news_category IS NOT NULL) AS top_news_category,
                BOOL_OR(ni.speculative_tag IS NOT NULL) AS is_speculative,
                (ARRAY_AGG(ni.speculative_tag) FILTER (WHERE ni.speculative_tag IS NOT NULL))[1] AS speculative_tag
            FROM contrib c
            -- Match on the raw name AND the AI-corrected one. The pipeline
            -- keys contributions on normalize_name(corrected_name or name)
            -- (site_matcher.py:_upsert_lyra_suggestion), so joining on c.name
            -- alone left 25 cards with no videos, facts, screenshot or
            -- last_mentioned even though their news items existed.
            JOIN news_items ni ON lower(trim(ni.site_name_extracted))
                 IN (lower(trim(c.name)), lower(trim(COALESCE(c.corrected_name, c.name))))
            JOIN news_videos nv ON nv.id = ni.video_id
            JOIN news_channels nc ON nc.id = nv.channel_id
            GROUP BY c.id
            -- No HAVING here: a predicate inside this CTE cannot filter the
            -- outer LEFT JOIN, it only deletes the group, which silently
            -- stripped the evidence off every non-matching card while the row
            -- count stayed at 553. The filters live in the outer WHERE now.
        )
        SELECT
            COUNT(*) OVER() AS _total_count,
            c.id::text,
            c.source,
            COALESCE(c.corrected_name, c.name) AS display_name,
            CASE WHEN c.corrected_name IS NOT NULL AND c.corrected_name != c.name
                 THEN c.name ELSE NULL END AS original_name,
            COALESCE(c.enrichment_status, 'pending') AS enrichment_status,
            c.computed_score,
            c.country,
            c.site_type,
            c.period_name,
            c.period_start,
            c.period_end,
            c.thumbnail_url,
            c.wikipedia_url,
            c.lat,
            c.lon,
            c.description,
            c.wikidata_id,
            c.enrichment_data,
            COALESCE(va.unique_videos, 0) AS unique_videos,
            COALESCE(va.unique_channels, 0) AS unique_channels,
            c.mention_count,
            va.last_mentioned,
            va.videos,
            va.all_facts,
            va.latest_screenshot_url,
            va.avg_significance,
            va.top_news_category,
            COALESCE(va.is_speculative, false) AS is_speculative,
            va.speculative_tag
        FROM contrib c
        LEFT JOIN video_agg va ON va.contrib_id = c.id
        WHERE (:news_category = 'all' OR va.top_news_category = :news_category)
          AND (:hide_speculative = false OR COALESCE(va.is_speculative, false) = false)
        ORDER BY {order_clause}
        {pagination}
    """


def _row_to_item(row) -> dict:
    enrichment_status = row.enrichment_status

    rejection_reason = None
    if enrichment_status == "rejected" and row.enrichment_data:
        rejected = row.enrichment_data.get("rejected_match", {})
        if rejected.get("reason") == "country_mismatch":
            rejection_reason = (
                f'Matched to "{rejected.get("site_name", "?")}" '
                f"({rejected.get('site_country', '?')}), "
                f"but video context indicates {rejected.get('contribution_country', '?')}"
            )

    period_name = row.period_name
    if row.period_start is not None:
        period_name = categorize_period(row.period_start)

    confidence = None
    ai_reasoning = None
    data_sources = []
    external_sources = []
    if row.enrichment_data and isinstance(row.enrichment_data, dict):
        external_sources = row.enrichment_data.get("external_sources", [])
        ident = row.enrichment_data.get("identification", {})
        if isinstance(ident, dict):
            confidence = ident.get("confidence")
            ai_reasoning = ident.get("reasoning")
        if row.enrichment_data.get("wikidata"):
            data_sources.append("wikidata")
            if isinstance(row.enrichment_data["wikidata"], dict) and row.enrichment_data[
                "wikidata"
            ].get("wikipedia"):
                data_sources.append("wikipedia")
        if row.enrichment_data.get("research"):
            data_sources.append("ai_research")
        if row.enrichment_data.get("db_match"):
            data_sources.append("db_match")

    # Add wikidata source if wikidata_id is present (even without enrichment_data)
    if row.wikidata_id and "wikidata" not in data_sources:
        data_sources.append("wikidata")

    # Derive commons_url from enrichment data
    commons_url = None
    if row.enrichment_data and isinstance(row.enrichment_data, dict):
        wd = row.enrichment_data.get("wikidata", {})
        if isinstance(wd, dict):
            cc = wd.get("commons_category")
            if cc:
                commons_url = f"https://commons.wikimedia.org/wiki/Category:{cc.replace(' ', '_')}"
            elif wd.get("thumbnail_url"):
                thumb = wd["thumbnail_url"]
                # Extract filename from Wikimedia Commons thumbnail URL
                # Format: .../thumb/a/ab/Filename.jpg/300px-Filename.jpg
                parts = thumb.split("/")
                if len(parts) >= 2:
                    # The filename is the second-to-last path segment
                    commons_url = f"https://commons.wikimedia.org/wiki/File:{parts[-2]}"

    return {
        "id": row.id,
        "source": row.source,
        "display_name": row.display_name,
        "original_name": row.original_name,
        "enrichment_status": enrichment_status,
        "enrichment_score": row.computed_score,
        "rejection_reason": rejection_reason,
        "country": row.country,
        "site_type": row.site_type,
        "period_name": period_name,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "thumbnail_url": row.thumbnail_url,
        "screenshot_url": getattr(row, "latest_screenshot_url", None),
        "avg_significance": round(float(row.avg_significance), 1) if row.avg_significance else None,
        "top_news_category": getattr(row, "top_news_category", None),
        "is_speculative": getattr(row, "is_speculative", False),
        "speculative_tag": getattr(row, "speculative_tag", None),
        "ai_reasoning": ai_reasoning,
        "wikipedia_url": row.wikipedia_url,
        "lat": row.lat,
        "lon": row.lon,
        "description": row.description,
        "wikidata_id": row.wikidata_id,
        "mention_count": row.mention_count,
        "facts": _flatten_facts(row.all_facts),
        "videos": _build_video_refs(row.videos),
        "unique_videos": row.unique_videos,
        "unique_channels": row.unique_channels,
        "last_mentioned": row.last_mentioned.isoformat() if row.last_mentioned else None,
        "external_sources": external_sources,
        "confidence": confidence,
        "data_sources": data_sources,
        "commons_url": commons_url,
        "nearby_an_site": None,
    }
    # No `suggestions`/`best_match`: those were computed for status
    # 'pending'/'enriching' only, and nothing ever holds those statuses —
    # match and identify run in the same hourly cycle, so a contribution
    # goes straight to a terminal status. The frontend blocks that rendered
    # them are gone too.


def _attach_nearby(db: Session, items: list[dict]) -> list[dict]:
    nearby_map = _find_nearest_an_sites_batch(db, items)
    for item in items:
        if item["id"] in nearby_map:
            item["nearby_an_site"] = nearby_map[item["id"]]
    return items


@router.get("/list")
def get_radar(
    req: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    # Default 0: mention_count is now derived from news_items, so a candidate
    # whose evidence sits under a different spelling legitimately has 0. A
    # floor of 1 would hide it entirely.
    min_mentions: int = Query(0, ge=0),
    sort_by: str = Query("score", pattern="^(score|mentions|recency)$"),
    status: str = Query("enriched", pattern="^(all|enriched|added|rejected)$"),
    news_category: str = Query("all"),
    hide_speculative: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Page through radar candidates.

    Defaults to `enriched` — the items that are actually awaiting a decision.
    Under the old `all` default, 132 of 553 cards were already-handled
    (rejected/dismissed/promoted) work, and promotion raises an item's score,
    so approved cards floated back to the top of the queue.
    """
    if not _radar_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests")
    cache_key = (
        f"radar:list:{page}:{page_size}:{min_mentions}:{sort_by}:{status}"
        f":{news_category}:{hide_speculative}"
    )
    cached = cache_get(cache_key)
    if cached:
        return cached

    offset = (page - 1) * page_size

    if sort_by == "mentions":
        order_clause = "c.mention_count DESC, c.id"
    elif sort_by == "recency":
        order_clause = "va.last_mentioned DESC NULLS LAST, c.mention_count DESC, c.id"
    else:
        order_clause = "c.computed_score DESC, c.mention_count DESC, c.id"

    contrib_rows = db.execute(
        text(_build_radar_query(_STATUS_CLAUSES[status], order_clause)),
        {
            "min_mentions": min_mentions,
            "news_category": news_category,
            "hide_speculative": hide_speculative,
            "limit": page_size,
            "offset": offset,
        },
    ).fetchall()

    total_count = contrib_rows[0]._total_count if contrib_rows else 0
    page_items = _attach_nearby(db, [_row_to_item(row) for row in contrib_rows])

    response = {
        "items": page_items,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_more": offset + len(page_items) < total_count,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response


@router.get("/item/{contribution_id}")
def get_radar_item(contribution_id: str, db: Session = Depends(get_db)):
    """One radar candidate, in the same shape /list returns.

    The map loads every candidate with coordinates while the list holds one
    page, so clicking a dot used to hit a card that was not in the DOM and do
    nothing at all — silently, for 412 of 436 dots on first load.
    """
    _require_uuid(contribution_id, 404, "Contribution not found")
    row = db.execute(
        text(_build_radar_query(_VISIBLE_CLAUSE, "c.id", single_id=True)),
        {
            "contribution_id": contribution_id,
            "min_mentions": 1,
            "news_category": "all",
            "hide_speculative": False,
        },
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return _attach_nearby(db, [_row_to_item(row)])[0]


@router.get("/stats")
def get_radar_stats(db: Session = Depends(get_db)):
    """
    Get summary stats for the radar page header.
    """
    cache_key = "radar:stats"
    cached = cache_get(cache_key)
    if cached:
        return cached

    stats_query = text("""
        SELECT
            COUNT(*) FILTER (
                WHERE COALESCE(enrichment_status, 'pending') NOT IN ('failed', 'not_a_site', 'matched')
            ) AS total_radar,
            -- 'enriched' only. Counting promoted rows here too meant every
            -- approval incremented both this number and `added`, so the header
            -- read as if the queue had not shrunk.
            COUNT(*) FILTER (
                WHERE enrichment_status = 'enriched'
            ) AS enriched_count,
            COUNT(*) FILTER (
                WHERE enrichment_status IN ('rejected', 'dismissed')
            ) AS rejected_count,
            COUNT(*) FILTER (
                WHERE enrichment_status = 'promoted'
            ) AS added_count
        FROM user_contributions
        WHERE source IN ('lyra', 'user')
    """)

    row = db.execute(stats_query).fetchone()

    # The curated set, not all 1.76M unified_sites. This number is the thing a
    # radar candidate is measured against — quoting the bulk-import total made
    # the queue look pointless next to it.
    sites_known = (
        db.execute(
            text("SELECT COUNT(*) FROM unified_sites WHERE source_id = 'ancient_nerds'")
        ).scalar()
        or 0
    )

    response = {
        "total_radar": (row.total_radar or 0) if row else 0,
        "enriched_count": (row.enriched_count or 0) if row else 0,
        "rejected_count": (row.rejected_count or 0) if row else 0,
        "added_count": (row.added_count or 0) if row else 0,
        "curated_sites": sites_known,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response


@router.post("/cache-bust")
def bust_radar_cache(_user: DiscordUser = Depends(require_founder)):
    """Clear radar cache (founders only)."""
    count = cache_delete_pattern("radar:*")
    return {"cleared": count}


@router.post("/{contribution_id}/promote")
def promote_to_db(
    contribution_id: str,
    overrides: PromoteOverrides | None = None,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Promote an enriched radar item into unified_sites (founders only).

    Requires core fields (coords, country, site_type, description >= 50 chars)
    after applying optional founder overrides. Wikipedia/thumbnail/QID are
    score bonuses, not blockers.
    """
    _require_uuid(contribution_id, 404, "Contribution not found")

    # Fetch the contribution
    row = db.execute(
        text("SELECT * FROM user_contributions WHERE id = :id"),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    item = dict(row._mapping)

    # Must be enriched
    if item.get("enrichment_status") != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot promote: status is '{item.get('enrichment_status')}', expected 'enriched'",
        )

    # Must not already be promoted
    if item.get("promoted_site_id") is not None:
        raise HTTPException(status_code=409, detail="Already promoted")

    override_dict = overrides.model_dump(exclude_none=True) if overrides else {}
    effective = _apply_overrides(item, override_dict)

    missing = _missing_core_fields(effective)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Missing core fields: {', '.join(missing)}",
                "missing": missing,
            },
        )

    display_name = override_dict.get("name") or effective.get("corrected_name") or effective["name"]

    # Determine source_id for the new unified_sites row
    source_id = "lyra" if effective.get("source") == "lyra" else "ancient_nerds_community"

    # Compute period_name from period_start if available
    period_name = effective.get("period_name")
    if effective.get("period_start") is not None:
        period_name = categorize_period(effective["period_start"])

    new_site_id = uuid.uuid4()
    name_norm = normalize_name(display_name)

    # INSERT into unified_sites
    db.execute(
        text("""
        INSERT INTO unified_sites (
            id, source_id, source_record_id, name, name_normalized,
            lat, lon, geom,
            site_type, period_start, period_end, period_name,
            country, description, thumbnail_url, source_url,
            edited_by
        ) VALUES (
            :id, :source_id, :source_record_id, :name, :name_normalized,
            :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            :site_type, :period_start, :period_end, :period_name,
            :country, :description, :thumbnail_url, :source_url,
            'radar_promote'
        )
    """),
        {
            "id": new_site_id,
            "source_id": source_id,
            "source_record_id": str(item["id"]),
            "name": display_name,
            "name_normalized": name_norm,
            "lat": effective["lat"],
            "lon": effective["lon"],
            "site_type": effective.get("site_type"),
            "period_start": effective.get("period_start"),
            "period_end": effective.get("period_end"),
            "period_name": period_name,
            "country": effective.get("country"),
            "description": effective.get("description"),
            "thumbnail_url": effective.get("thumbnail_url"),
            "source_url": effective.get("wikipedia_url"),
        },
    )

    # INSERT into unified_site_names for trigram search
    db.execute(
        text("""
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        VALUES (:site_id, :name, :name_normalized, 'label')
    """),
        {
            "site_id": new_site_id,
            "name": display_name,
            "name_normalized": name_norm,
        },
    )

    # UPDATE the contribution: status + audit entry (overrides recorded, not applied)
    enrichment_data = dict(item.get("enrichment_data") or {})
    enrichment_data["review"] = _review_entry(
        "promote", user.username, overrides=override_dict, site_id=str(new_site_id)
    )
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'promoted', promoted_site_id = :site_id,
            enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"site_id": new_site_id, "id": contribution_id, "ed": json.dumps(enrichment_data)},
    )

    db.commit()

    # Bust caches
    cache_delete_pattern("radar:*")
    cache_delete_pattern("sites:*")

    return {"success": True, "site_id": str(new_site_id)}


@router.post("/{contribution_id}/dismiss")
def dismiss_contribution(
    contribution_id: str,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Founder-reject a radar candidate (founders only).

    Uses status 'dismissed' (NOT 'rejected') — the enrichment pipeline
    re-processes 'rejected' rows each cycle, which would resurrect the card.
    'dismissed' is excluded from the pipeline work query.
    """
    _require_uuid(contribution_id, 404, "Contribution not found")
    row = db.execute(
        text("SELECT enrichment_status, enrichment_data FROM user_contributions WHERE id = :id"),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    if row.enrichment_status != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot dismiss: status is '{row.enrichment_status}', expected 'enriched'",
        )

    enrichment_data = dict(row.enrichment_data or {})
    enrichment_data["review"] = _review_entry("dismiss", user.username)
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'dismissed', enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"id": contribution_id, "ed": json.dumps(enrichment_data)},
    )
    db.commit()

    cache_delete_pattern("radar:*")
    return {"success": True}


class MergeRequest(BaseModel):
    site_id: str


@router.post("/{contribution_id}/merge")
def merge_into_site(
    contribution_id: str,
    body: MergeRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Merge a radar candidate into an existing unified_sites row (founders only).

    Stores the candidate's name(s) as aliases so future news mentions match
    the existing site directly and this card never regenerates.
    """
    _require_uuid(contribution_id, 404, "Contribution not found")
    _require_uuid(body.site_id, 422, "Invalid site_id format")
    row = db.execute(
        text("""
        SELECT name, corrected_name, enrichment_status, enrichment_data
        FROM user_contributions WHERE id = :id
    """),
        {"id": contribution_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contribution not found")

    if row.enrichment_status != "enriched":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot merge: status is '{row.enrichment_status}', expected 'enriched'",
        )

    site = db.execute(
        text("SELECT id, name FROM unified_sites WHERE id = :sid"),
        {"sid": body.site_id},
    ).fetchone()
    if not site:
        raise HTTPException(status_code=404, detail="Target site not found")

    # Store candidate name(s) as aliases (idempotent per normalized name)
    aliases = {row.name}
    if row.corrected_name:
        aliases.add(row.corrected_name)
    for alias in aliases:
        alias_norm = normalize_name(alias)
        if not alias_norm:
            continue
        db.execute(
            text("""
            INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
            SELECT :site_id, :name, :name_normalized, 'alias'
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_site_names
                WHERE site_id = :site_id AND name_normalized = :name_normalized
            )
        """),
            {"site_id": body.site_id, "name": alias, "name_normalized": alias_norm},
        )

    enrichment_data = dict(row.enrichment_data or {})
    enrichment_data["review"] = _review_entry(
        "merge", user.username, site_id=body.site_id, site_name=site.name
    )
    db.execute(
        text("""
        UPDATE user_contributions
        SET enrichment_status = 'matched', enrichment_data = CAST(:ed AS JSONB)
        WHERE id = :id
    """),
        {"id": contribution_id, "ed": json.dumps(enrichment_data)},
    )
    db.commit()

    cache_delete_pattern("radar:*")
    return {"success": True, "site_id": body.site_id, "site_name": site.name}
