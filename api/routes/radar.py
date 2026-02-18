"""
Lyra Radar API - Sites Lyra found in YouTube videos that aren't in our DB yet.

Shows candidates for addition: enriched, pending, promoted ("added"), and
rejected items. Matched items (already in DB) and not_a_site are excluded.
"""

import logging
import os
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern, cache_get, cache_set
from api.routes.sites import _verify_admin
from pipeline.database import get_db
from pipeline.utils.text import categorize_period, normalize_name

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_BUST_SECRET = os.getenv("LYRA_ADMIN_KEY", "")

CACHE_TTL = 300  # 5 minutes


def find_similar_sites_batch(
    db: Session, names: list[str], limit_per_name: int = 5,
) -> dict[str, list[dict]]:
    """
    Find similar sites for multiple names using pg_trgm.

    Uses the <% operator (not the word_similarity function) so PostgreSQL
    can use the GIN trigram index on unified_site_names.name_normalized.

    Returns a dict mapping each input name to its top matches.
    """
    if not names:
        return {}

    # Set threshold so <% operator filters at 0.3 similarity
    db.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.3"))

    per_name_query = text("""
        SELECT usn.site_id, us.name AS site_name, us.thumbnail_url,
               us.country, us.source_id, us.source_url,
               sm.name AS source_name,
               word_similarity(:qname, usn.name_normalized) AS similarity
        FROM unified_site_names usn
        JOIN unified_sites us ON us.id = usn.site_id
        LEFT JOIN source_meta sm ON sm.id = us.source_id
        WHERE :qname <% usn.name_normalized
        ORDER BY usn.name_normalized <->> :qname
        LIMIT :limit
    """)

    matches_by_name: dict[str, list[dict]] = {n: [] for n in names}

    for qname in names:
        rows = db.execute(per_name_query, {
            "qname": qname, "limit": limit_per_name * 4,
        }).fetchall()

        seen_site_ids: set[str] = set()
        for row in rows:
            sid = str(row.site_id)
            if sid in seen_site_ids:
                continue
            seen_site_ids.add(sid)

            wikipedia_url = None
            if row.source_id == "wikidata" and row.source_url:
                wikipedia_url = row.source_url
            elif row.site_name:
                wiki_name = row.site_name.replace(" ", "_")
                wikipedia_url = f"https://en.wikipedia.org/wiki/{wiki_name}"

            matches_by_name[qname].append({
                "site_id": sid,
                "name": row.site_name,
                "similarity": round(row.similarity, 2),
                "thumbnail_url": row.thumbnail_url,
                "wikipedia_url": wikipedia_url,
                "country": row.country,
                "source_id": row.source_id,
                "source_name": row.source_name,
            })

            if len(matches_by_name[qname]) >= limit_per_name:
                break

    return matches_by_name


def _compute_display_score(item: dict) -> int:
    """Compute the same weighted score the frontend displays as a percentage."""
    score = 25  # name always present
    if item.get("lat") is not None and item.get("lon") is not None:
        score += 20
    if item.get("country"):
        score += 10
    if item.get("site_type"):
        score += 10
    if item.get("period_name"):
        score += 10
    desc = item.get("description") or ""
    if len(desc) >= 50:
        score += 10
    if item.get("wikipedia_url"):
        score += 5
    if item.get("thumbnail_url"):
        score += 5
    if item.get("wikidata_id"):
        score += 5
    return score


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
            videos.append({
                "video_id": vid,
                "channel_name": v.get("channel_name", ""),
                "timestamp_seconds": ts,
                "deep_url": deep_url,
            })
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


def _find_nearest_an_site(db: Session, lat: float, lon: float, max_km: float = 10.0):
    """Find closest AN Originals site within max_km. Returns dict or None."""
    delta = max_km / 111.0
    row = db.execute(text("""
        SELECT name,
               SQRT(POW((:lat - lat) * 111.0, 2) + POW((:lon - lon) * 111.0 * COS(RADIANS(:lat)), 2)) AS dist_km
        FROM unified_sites
        WHERE source_id = 'ancient_nerds'
          AND lat BETWEEN :lat - :delta AND :lat + :delta
          AND lon BETWEEN :lon - :delta AND :lon + :delta
        ORDER BY dist_km
        LIMIT 1
    """), {"lat": lat, "lon": lon, "delta": delta}).fetchone()
    if row and row.dist_km <= max_km:
        return {"name": row.name, "distance_km": round(row.dist_km, 1)}
    return None


@router.get("/map")
async def get_radar_map_data(db: Session = Depends(get_db)):
    """Lightweight endpoint for map pins — just coords + display fields."""
    cache_key = "radar:map"
    cached = cache_get(cache_key)
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT id::text, source, COALESCE(corrected_name, name) AS display_name,
               COALESCE(enrichment_status, 'pending') AS enrichment_status,
               country, site_type, period_name, lat, lon,
               (25
                + 20
                + CASE WHEN country IS NOT NULL AND country != '' THEN 10 ELSE 0 END
                + CASE WHEN site_type IS NOT NULL AND site_type != '' THEN 10 ELSE 0 END
                + CASE WHEN period_name IS NOT NULL AND period_name != '' THEN 10 ELSE 0 END
                + CASE WHEN LENGTH(description) >= 50 THEN 10 ELSE 0 END
                + CASE WHEN wikipedia_url IS NOT NULL THEN 5 ELSE 0 END
                + CASE WHEN thumbnail_url IS NOT NULL THEN 5 ELSE 0 END
                + CASE WHEN wikidata_id IS NOT NULL THEN 5 ELSE 0 END
               ) AS enrichment_score,
               mention_count
        FROM user_contributions
        WHERE source IN ('lyra', 'user')
          AND COALESCE(enrichment_status, 'pending') NOT IN ('matched', 'not_a_site', 'failed')
          AND lat IS NOT NULL AND lon IS NOT NULL
    """)).fetchall()

    result = [dict(r._mapping) for r in rows]
    cache_set(cache_key, result, ttl=CACHE_TTL)
    return result


@router.get("/sites-map")
async def get_sites_map(db: Session = Depends(get_db)):
    """All unified_sites with enrichment score for the background map layer."""
    cache_key = "radar:sites-map"
    cached = cache_get(cache_key)
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT id::text, name, lat, lon,
          (45
           + CASE WHEN country IS NOT NULL AND country != '' THEN 10 ELSE 0 END
           + CASE WHEN site_type IS NOT NULL AND site_type != '' THEN 10 ELSE 0 END
           + CASE WHEN period_name IS NOT NULL AND period_name != '' THEN 10 ELSE 0 END
           + CASE WHEN LENGTH(description) >= 50 THEN 10 ELSE 0 END
           + CASE WHEN source_url IS NOT NULL THEN 5 ELSE 0 END
           + CASE WHEN thumbnail_url IS NOT NULL THEN 5 ELSE 0 END
          ) AS score
        FROM unified_sites
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """)).fetchall()

    result = {
        "cols": ["id", "n", "la", "lo", "sc"],
        "rows": [[r.id, r.name, float(r.lat), float(r.lon), r.score] for r in rows],
    }
    cache_set(cache_key, result, ttl=1800)
    return result


@router.get("/list")
async def get_radar(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    min_mentions: int = Query(1, ge=1),
    sort_by: str = Query("score", pattern="^(score|mentions|recency)$"),
    status: str = Query("all", pattern="^(all|enriched|pending|added|rejected)$"),
    source_filter: str = Query("all", pattern="^(all|lyra|user)$"),
    db: Session = Depends(get_db),
):
    """
    Get Lyra radar items: sites found in YouTube videos that aren't in our DB.

    Excludes matched (already in DB), not_a_site, and failed items.
    Supports source_filter: 'all' (default), 'lyra' (radar), 'user' (community).
    """
    cache_key = f"radar:list:{page}:{page_size}:{min_mentions}:{sort_by}:{status}:{source_filter}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # ── Status filter → SQL WHERE clause ───────────────────────────
    status_clause = "COALESCE(uc.enrichment_status, 'pending') NOT IN ('failed', 'not_a_site', 'matched')"
    if status == "enriched":
        status_clause = "uc.enrichment_status = 'enriched'"
    elif status == "pending":
        status_clause = "COALESCE(uc.enrichment_status, 'pending') IN ('pending', 'enriching')"
    elif status == "added":
        status_clause = "uc.enrichment_status = 'promoted'"
    elif status == "rejected":
        status_clause = "uc.enrichment_status = 'rejected'"

    # For mentions/recency: push sort + pagination into SQL
    # For score: fetch all rows, sort in Python (score is computed post-query)
    sql_paginated = sort_by in ("mentions", "recency")
    offset = (page - 1) * page_size

    if sort_by == "mentions":
        order_clause = "c.mention_count DESC, c.id"
    elif sort_by == "recency":
        order_clause = "va.last_mentioned DESC NULLS LAST, c.mention_count DESC, c.id"
    else:
        order_clause = "c.mention_count DESC, c.id"

    limit_clause = "LIMIT :limit OFFSET :offset" if sql_paginated else ""
    count_col = "COUNT(*) OVER() AS _total_count," if sql_paginated else ""

    contributions_query = text(f"""
        WITH contrib AS (
            SELECT
                uc.id,
                uc.source,
                uc.name,
                uc.corrected_name,
                uc.enrichment_status,
                uc.score,
                uc.mention_count,
                uc.country,
                uc.site_type,
                uc.period_name,
                uc.period_start,
                uc.thumbnail_url,
                uc.wikipedia_url,
                uc.enrichment_data,
                uc.created_at,
                uc.lat,
                uc.lon,
                uc.description,
                uc.wikidata_id
            FROM user_contributions uc
            WHERE uc.source IN ('lyra', 'user')
              AND (:source_filter = 'all' OR uc.source = :source_filter)
              AND {status_clause}
              AND uc.mention_count >= :min_mentions
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
                MAX(ni.created_at) AS last_mentioned
            FROM contrib c
            JOIN news_items ni ON lower(trim(ni.site_name_extracted)) = lower(trim(c.name))
            JOIN news_videos nv ON nv.id = ni.video_id
            JOIN news_channels nc ON nc.id = nv.channel_id
            GROUP BY c.id
        )
        SELECT
            {count_col}
            c.id::text,
            c.source,
            COALESCE(c.corrected_name, c.name) AS display_name,
            CASE WHEN c.corrected_name IS NOT NULL AND c.corrected_name != c.name
                 THEN c.name ELSE NULL END AS original_name,
            COALESCE(c.enrichment_status, 'pending') AS enrichment_status,
            c.score AS enrichment_score,
            c.country,
            c.site_type,
            c.period_name,
            c.period_start,
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
            va.all_facts
        FROM contrib c
        LEFT JOIN video_agg va ON va.contrib_id = c.id
        ORDER BY {order_clause}
        {limit_clause}
    """)

    params = {"min_mentions": min_mentions, "source_filter": source_filter}
    if sql_paginated:
        params["limit"] = page_size
        params["offset"] = offset

    contrib_rows = db.execute(contributions_query, params).fetchall()

    def _row_to_item(row) -> dict:
        enrichment_status = row.enrichment_status

        rejection_reason = None
        if enrichment_status == "rejected" and row.enrichment_data:
            rejected = row.enrichment_data.get("rejected_match", {})
            if rejected.get("reason") == "country_mismatch":
                rejection_reason = (
                    f"Matched to \"{rejected.get('site_name', '?')}\" "
                    f"({rejected.get('site_country', '?')}), "
                    f"but video context indicates {rejected.get('contribution_country', '?')}"
                )

        period_name = row.period_name
        if row.period_start is not None:
            period_name = categorize_period(row.period_start)

        confidence = None
        data_sources = []
        external_sources = []
        if row.enrichment_data and isinstance(row.enrichment_data, dict):
            external_sources = row.enrichment_data.get("external_sources", [])
            ident = row.enrichment_data.get("identification", {})
            if isinstance(ident, dict):
                confidence = ident.get("confidence")
            if row.enrichment_data.get("wikidata"):
                data_sources.append("wikidata")
                if isinstance(row.enrichment_data["wikidata"], dict) and row.enrichment_data["wikidata"].get("wikipedia"):
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

        item = {
            "id": row.id,
            "source": row.source,
            "display_name": row.display_name,
            "original_name": row.original_name,
            "enrichment_status": enrichment_status,
            "enrichment_score": 0,
            "rejection_reason": rejection_reason,
            "country": row.country,
            "site_type": row.site_type,
            "period_name": period_name,
            "period_start": row.period_start,
            "thumbnail_url": row.thumbnail_url,
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
            "suggestions": [],
            "best_match": None,
            "external_sources": external_sources,
            "confidence": confidence,
            "data_sources": data_sources,
            "commons_url": commons_url,
            "nearby_an_site": None,
        }
        item["enrichment_score"] = _compute_display_score(item)
        if row.lat is not None and row.lon is not None:
            item["nearby_an_site"] = _find_nearest_an_site(db, row.lat, row.lon)
        return item

    if sql_paginated:
        # SQL already sorted and paginated; total comes from window function
        total_count = contrib_rows[0]._total_count if contrib_rows else 0
        page_items = [_row_to_item(row) for row in contrib_rows]
    else:
        # score sort: build all items, sort in Python, then slice
        items = [_row_to_item(row) for row in contrib_rows]
        items.sort(key=lambda x: x["enrichment_score"], reverse=True)
        total_count = len(items)
        page_items = items[offset:offset + page_size]

    # ── Fuzzy suggestions for pending/enriching items only ──────────
    # Wrapped in try/except: suggestions are optional, a pg_trgm or
    # missing-table error must not 500 the whole radar list.
    pending_names = [
        normalize_name(item["display_name"])
        for item in page_items
        if item["enrichment_status"] in ("pending", "enriching")
    ]
    if pending_names:
        try:
            all_suggestions = find_similar_sites_batch(db, pending_names, limit_per_name=5)
            name_idx = 0
            for item in page_items:
                if item["enrichment_status"] in ("pending", "enriching"):
                    qname = pending_names[name_idx]
                    name_idx += 1
                    suggestions = all_suggestions.get(qname, [])
                    item["suggestions"] = suggestions
                    if suggestions and suggestions[0]["similarity"] >= 0.6:
                        item["best_match"] = suggestions[0]
        except Exception:
            logger.warning("Fuzzy suggestions failed — returning items without suggestions", exc_info=True)

    response = {
        "items": page_items,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_more": offset + len(page_items) < total_count,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response


@router.get("/stats")
async def get_radar_stats(db: Session = Depends(get_db)):
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
            COUNT(*) FILTER (
                WHERE enrichment_status IN ('enriched', 'promoted')
            ) AS enriched_count,
            COUNT(*) FILTER (
                WHERE COALESCE(enrichment_status, 'pending') IN ('pending', 'enriching')
            ) AS pending_count,
            COUNT(*) FILTER (
                WHERE enrichment_status = 'promoted'
            ) AS added_count
        FROM user_contributions
        WHERE source IN ('lyra', 'user')
    """)

    row = db.execute(stats_query).fetchone()

    sites_known = db.execute(text("SELECT COUNT(*) FROM unified_sites")).scalar() or 0

    response = {
        "total_radar": (row.total_radar or 0) if row else 0,
        "enriched_count": (row.enriched_count or 0) if row else 0,
        "pending_count": (row.pending_count or 0) if row else 0,
        "added_count": (row.added_count or 0) if row else 0,
        "total_sites_known": sites_known,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response


@router.post("/cache-bust")
async def bust_radar_cache(authorization: str | None = Header(None)):
    """Called by the Lyra pipeline after processing to show fresh data."""
    if not CACHE_BUST_SECRET:
        raise HTTPException(status_code=503, detail="LYRA_ADMIN_KEY not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    if not secrets.compare_digest(authorization[7:], CACHE_BUST_SECRET):
        raise HTTPException(status_code=403, detail="Invalid token")
    count = cache_delete_pattern("radar:*")
    return {"cleared": count}


@router.post("/{contribution_id}/promote")
async def promote_to_db(
    contribution_id: str,
    authorization: str | None = Header(None),
    x_admin_pin: str | None = Header(None, alias="X-Admin-Pin"),
    db: Session = Depends(get_db),
):
    """
    Promote a 100%-enriched radar item into unified_sites.

    Manual admin action only — no AI/automation should call this.
    """
    _verify_admin(authorization, x_admin_pin)

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
        raise HTTPException(status_code=409, detail=f"Cannot promote: status is '{item.get('enrichment_status')}', expected 'enriched'")

    # Must not already be promoted
    if item.get("promoted_site_id") is not None:
        raise HTTPException(status_code=409, detail="Already promoted")

    # Build a dict compatible with _compute_display_score
    display_name = item.get("corrected_name") or item["name"]
    score_item = {
        "lat": item.get("lat"),
        "lon": item.get("lon"),
        "country": item.get("country"),
        "site_type": item.get("site_type"),
        "period_name": item.get("period_name"),
        "description": item.get("description"),
        "wikipedia_url": item.get("wikipedia_url"),
        "thumbnail_url": item.get("thumbnail_url"),
        "wikidata_id": item.get("wikidata_id"),
    }
    score = _compute_display_score(score_item)
    if score < 100:
        raise HTTPException(status_code=409, detail=f"Enrichment score is {score}%, must be 100%")

    # Determine source_id for the new unified_sites row
    source_id = "lyra" if item.get("source") == "lyra" else "ancient_nerds_community"

    # Compute period_name from period_start if available
    period_name = item.get("period_name")
    if item.get("period_start") is not None:
        period_name = categorize_period(item["period_start"])

    new_site_id = uuid.uuid4()
    name_norm = normalize_name(display_name)

    # INSERT into unified_sites
    db.execute(text("""
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
    """), {
        "id": new_site_id,
        "source_id": source_id,
        "source_record_id": str(item["id"]),
        "name": display_name,
        "name_normalized": name_norm,
        "lat": item["lat"],
        "lon": item["lon"],
        "site_type": item.get("site_type"),
        "period_start": item.get("period_start"),
        "period_end": item.get("period_end"),
        "period_name": period_name,
        "country": item.get("country"),
        "description": item.get("description"),
        "thumbnail_url": item.get("thumbnail_url"),
        "source_url": item.get("wikipedia_url"),
    })

    # INSERT into unified_site_names for trigram search
    db.execute(text("""
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        VALUES (:site_id, :name, :name_normalized, 'label')
    """), {
        "site_id": new_site_id,
        "name": display_name,
        "name_normalized": name_norm,
    })

    # UPDATE the contribution
    db.execute(text("""
        UPDATE user_contributions
        SET enrichment_status = 'promoted', promoted_site_id = :site_id
        WHERE id = :id
    """), {"site_id": new_site_id, "id": contribution_id})

    db.commit()

    # Bust caches
    cache_delete_pattern("radar:*")
    cache_delete_pattern("sites:*")

    return {"success": True, "site_id": str(new_site_id)}
