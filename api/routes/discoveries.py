"""
Lyra Discoveries API - All Lyra-extracted sites as a curation overview.

Shows every site Lyra extracts from YouTube videos that is NOT in the
manually-curated `ancient_nerds` source. Includes matched (to pleiades,
dare, wikidata, etc.), enriched, and pending items.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set
from pipeline.database import get_db
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)
router = APIRouter()

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
    db.execute(text("SET pg_trgm.word_similarity_threshold = 0.3"))

    per_name_query = text("""
        SELECT usn.site_id, us.name AS site_name, us.thumbnail_url,
               us.country, us.source_id, us.source_url,
               word_similarity(:qname, usn.name_normalized) AS similarity
        FROM unified_site_names usn
        JOIN unified_sites us ON us.id = usn.site_id
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
    videos = []
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


@router.get("/list")
async def get_discoveries(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    min_mentions: int = Query(1, ge=1),
    sort_by: str = Query("score", regex="^(score|mentions|recency)$"),
    status: str = Query("all", regex="^(all|matched|enriched|pending|rejected)$"),
    db: Session = Depends(get_db),
):
    """
    Get all Lyra discoveries: any site extracted from YouTube videos that
    is NOT in the ancient_nerds source.

    Sources:
    1. user_contributions WHERE source='lyra' (primary)
    2. Direct site_matcher matches (news_items with site_id set, no contribution)
    """
    cache_key = f"discoveries:list:{page}:{page_size}:{min_mentions}:{sort_by}:{status}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # ── Part 1: Lyra user_contributions ─────────────────────────────
    # For each contribution, get matched site info (if any) from enrichment_data,
    # and aggregate video references from news_items.
    contributions_query = text("""
        WITH contrib AS (
            SELECT
                uc.id,
                uc.name,
                uc.enrichment_status,
                uc.score,
                uc.mention_count,
                uc.country,
                uc.site_type,
                uc.period_name,
                uc.thumbnail_url,
                uc.wikipedia_url,
                uc.enrichment_data,
                uc.created_at,
                uc.lat,
                uc.lon,
                uc.description,
                uc.wikidata_id
            FROM user_contributions uc
            WHERE uc.source = 'lyra'
              AND COALESCE(uc.enrichment_status, 'pending') NOT IN ('failed', 'not_a_site')
              AND uc.mention_count >= :min_mentions
        ),
        -- Get matched site info by extracting match_id from enrichment_data
        matched_info AS (
            SELECT
                c.id AS contrib_id,
                us.id AS matched_site_id,
                us.name AS matched_site_name,
                us.source_id AS matched_source,
                us.thumbnail_url AS matched_thumbnail,
                us.country AS matched_country,
                us.site_type AS matched_site_type,
                us.period_name AS matched_period_name,
                us.lat AS matched_lat,
                us.lon AS matched_lon,
                us.description AS matched_description,
                us.source_url AS matched_source_url
            FROM contrib c
            JOIN unified_sites us
                ON us.id = (c.enrichment_data #>> '{identification,match_id}')::uuid
            WHERE c.enrichment_data #>> '{identification,match_type}' IN ('db_match', 'wikidata_match')
              AND c.enrichment_data #>> '{identification,match_id}' IS NOT NULL
        ),
        -- Aggregate video references per contribution
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
            c.id::text,
            c.name AS display_name,
            COALESCE(c.enrichment_status, 'pending') AS enrichment_status,
            c.score AS enrichment_score,
            mi.matched_site_id::text,
            mi.matched_site_name,
            mi.matched_source,
            -- Prefer matched site metadata, fall back to contribution
            COALESCE(mi.matched_country, c.country) AS country,
            COALESCE(mi.matched_site_type, c.site_type) AS site_type,
            COALESCE(mi.matched_period_name, c.period_name) AS period_name,
            COALESCE(mi.matched_thumbnail, c.thumbnail_url) AS thumbnail_url,
            COALESCE(c.wikipedia_url, mi.matched_source_url) AS wikipedia_url,
            COALESCE(mi.matched_lat, c.lat) AS lat,
            COALESCE(mi.matched_lon, c.lon) AS lon,
            COALESCE(mi.matched_description, c.description) AS description,
            c.wikidata_id,
            COALESCE(va.unique_videos, 0) AS unique_videos,
            COALESCE(va.unique_channels, 0) AS unique_channels,
            c.mention_count,
            va.last_mentioned,
            va.videos,
            va.all_facts
        FROM contrib c
        LEFT JOIN matched_info mi ON mi.contrib_id = c.id
        LEFT JOIN video_agg va ON va.contrib_id = c.id
        -- Exclude items matched to ancient_nerds
        WHERE mi.matched_source IS DISTINCT FROM 'ancient_nerds'
    """)

    contrib_rows = db.execute(contributions_query, {
        "min_mentions": min_mentions,
    }).fetchall()

    # Track contribution names AND matched site IDs so we skip them in Part 2
    contrib_names_lower = set()
    contrib_matched_site_ids = set()
    items = []

    for row in contrib_rows:
        contrib_names_lower.add(row.display_name.lower().strip())
        if row.matched_site_id:
            contrib_matched_site_ids.add(row.matched_site_id)

        enrichment_status = row.enrichment_status
        # Apply status filter
        if status == "matched" and enrichment_status != "matched":
            continue
        if status == "enriched" and enrichment_status not in ("enriched", "promoted"):
            continue
        if status == "pending" and enrichment_status not in ("pending", "enriching"):
            continue
        if status == "rejected" and enrichment_status != "rejected":
            continue

        item = {
            "id": row.id,
            "display_name": row.display_name,
            "enrichment_status": enrichment_status,
            "enrichment_score": 0,
            "matched_site_id": row.matched_site_id,
            "matched_site_name": row.matched_site_name,
            "matched_source": row.matched_source,
            "country": row.country,
            "site_type": row.site_type,
            "period_name": row.period_name,
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
        }
        # Generate Wikipedia URL from matched site name if none exists
        if not item["wikipedia_url"] and item["matched_site_name"]:
            wiki_name = item["matched_site_name"].replace(" ", "_")
            item["wikipedia_url"] = f"https://en.wikipedia.org/wiki/{wiki_name}"
        item["enrichment_score"] = _compute_display_score(item)
        items.append(item)

    # ── Part 2: Direct matches without user_contribution ────────────
    # news_items with site_id set, joined to unified_sites where source_id != 'ancient_nerds',
    # that don't already have a user_contribution.
    if status in ("all", "matched"):
        direct_query = text("""
            WITH direct AS (
                SELECT
                    us.id AS site_id,
                    us.name AS site_name,
                    us.source_id,
                    us.thumbnail_url,
                    us.country,
                    us.site_type,
                    us.period_name,
                    us.source_url,
                    us.lat,
                    us.lon,
                    us.description,
                    COUNT(*) AS mention_count,
                    COUNT(DISTINCT ni.video_id) AS unique_videos,
                    COUNT(DISTINCT nv.channel_id) AS unique_channels,
                    MAX(ni.created_at) AS last_mentioned,
                    jsonb_agg(DISTINCT jsonb_build_object(
                        'video_id', ni.video_id,
                        'channel_name', nc.name,
                        'timestamp_seconds', ni.timestamp_seconds
                    )) AS videos,
                    jsonb_agg(ni.facts) FILTER (WHERE ni.facts IS NOT NULL) AS all_facts
                FROM news_items ni
                JOIN unified_sites us ON us.id = ni.site_id
                JOIN news_videos nv ON nv.id = ni.video_id
                JOIN news_channels nc ON nc.id = nv.channel_id
                WHERE ni.site_id IS NOT NULL
                  AND ni.site_match_tried = true
                  AND us.source_id != 'ancient_nerds'
                GROUP BY us.id, us.name, us.source_id, us.thumbnail_url,
                         us.country, us.site_type, us.period_name, us.source_url,
                         us.lat, us.lon, us.description
                HAVING COUNT(*) >= :min_mentions
            )
            SELECT * FROM direct
        """)

        direct_rows = db.execute(direct_query, {
            "min_mentions": min_mentions,
        }).fetchall()

        for row in direct_rows:
            # Skip if already covered by a Part 1 contribution (by name or matched site ID)
            site_id_str = str(row.site_id)
            if row.site_name.lower().strip() in contrib_names_lower:
                continue
            if site_id_str in contrib_matched_site_ids:
                continue

            wikipedia_url = None
            if row.source_id == "wikidata" and row.source_url:
                wikipedia_url = row.source_url

            item = {
                "id": str(row.site_id),
                "display_name": row.site_name,
                "enrichment_status": "matched",
                "enrichment_score": 0,
                "matched_site_id": str(row.site_id),
                "matched_site_name": row.site_name,
                "matched_source": row.source_id,
                "country": row.country,
                "site_type": row.site_type,
                "period_name": row.period_name,
                "thumbnail_url": row.thumbnail_url,
                "wikipedia_url": wikipedia_url,
                "lat": row.lat,
                "lon": row.lon,
                "description": row.description,
                "wikidata_id": None,
                "mention_count": row.mention_count,
                "facts": _flatten_facts(row.all_facts),
                "videos": _build_video_refs(row.videos),
                "unique_videos": row.unique_videos,
                "unique_channels": row.unique_channels,
                "last_mentioned": row.last_mentioned.isoformat() if row.last_mentioned else None,
                "suggestions": [],
                "best_match": None,
            }
            item["enrichment_score"] = _compute_display_score(item)
            items.append(item)

    # ── Sort ────────────────────────────────────────────────────────
    if sort_by == "score":
        items.sort(key=lambda x: x["enrichment_score"], reverse=True)
    elif sort_by == "mentions":
        items.sort(key=lambda x: x["mention_count"], reverse=True)
    elif sort_by == "recency":
        items.sort(key=lambda x: x["last_mentioned"] or "", reverse=True)

    # ── Paginate ────────────────────────────────────────────────────
    total_count = len(items)
    offset = (page - 1) * page_size
    page_items = items[offset:offset + page_size]

    # ── Fuzzy suggestions for pending/enriching items only ──────────
    pending_names = [
        normalize_name(item["display_name"])
        for item in page_items
        if item["enrichment_status"] in ("pending", "enriching") and not item["matched_site_id"]
    ]
    if pending_names:
        all_suggestions = find_similar_sites_batch(db, pending_names, limit_per_name=5)
        name_idx = 0
        for item in page_items:
            if item["enrichment_status"] in ("pending", "enriching") and not item["matched_site_id"]:
                qname = pending_names[name_idx]
                name_idx += 1
                suggestions = all_suggestions.get(qname, [])
                item["suggestions"] = suggestions
                if suggestions and suggestions[0]["similarity"] >= 0.6:
                    item["best_match"] = suggestions[0]

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
async def get_discovery_stats(db: Session = Depends(get_db)):
    """
    Get summary stats for the discoveries page header.
    """
    cache_key = "discoveries:stats"
    cached = cache_get(cache_key)
    if cached:
        return cached

    stats_query = text("""
        SELECT
            COUNT(*) FILTER (
                WHERE COALESCE(enrichment_status, 'pending') NOT IN ('failed', 'not_a_site')
            ) AS total_discoveries,
            COUNT(*) FILTER (
                WHERE enrichment_status = 'matched'
            ) AS matched_count,
            COUNT(*) FILTER (
                WHERE enrichment_status IN ('enriched', 'promoted')
            ) AS enriched_count,
            COUNT(*) FILTER (
                WHERE COALESCE(enrichment_status, 'pending') IN ('pending', 'enriching')
            ) AS pending_count
        FROM user_contributions
        WHERE source = 'lyra'
    """)

    row = db.execute(stats_query).fetchone()

    sites_known = db.execute(text("SELECT COUNT(*) FROM unified_sites")).scalar() or 0

    response = {
        "total_discoveries": row.total_discoveries or 0,
        "matched_count": row.matched_count or 0,
        "enriched_count": row.enriched_count or 0,
        "pending_count": row.pending_count or 0,
        "total_sites_known": sites_known,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response
