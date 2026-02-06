"""
Lyra Discoveries API - Aggregated discovery data from news pipeline.

Provides deduplicated, scored discoveries with fuzzy site matching.
"""

import logging
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set
from pipeline.database import get_db
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_TTL = 300  # 5 minutes


def compute_score(mentions: int, videos: int, channels: int, days_since: float) -> float:
    """
    Compute importance score for a discovery.

    Formula weights:
    - 40% log-scaled mentions
    - 25% log-scaled unique videos
    - 20% unique channels (linear, capped at 5)
    - 15% recency (decays over 90 days)

    Returns a score between 0-1.
    """
    # Log-scaled mentions (1 mention = 0, 10 mentions = 1)
    log_mentions = math.log10(max(1, mentions)) / math.log10(10)
    log_mentions = min(1.0, log_mentions)

    # Log-scaled videos
    log_videos = math.log10(max(1, videos)) / math.log10(10)
    log_videos = min(1.0, log_videos)

    # Channels (linear, capped at 5)
    channel_score = min(1.0, channels / 5.0)

    # Recency (1.0 for today, decays to 0 over 90 days)
    recency = max(0.0, 1.0 - (days_since / 90.0))

    score = (
        0.40 * log_mentions +
        0.25 * log_videos +
        0.20 * channel_score +
        0.15 * recency
    )
    return round(score, 3)


def find_similar_sites(db: Session, normalized_name: str, limit: int = 5) -> list[dict]:
    """
    Find similar sites using pg_trgm word_similarity.

    Returns top matches with similarity >= 0.3.
    """
    result = db.execute(text("""
        SELECT DISTINCT ON (usn.site_id)
            usn.site_id,
            usn.name AS matched_name,
            us.name AS site_name,
            us.thumbnail_url,
            us.country,
            us.source_id,
            us.source_url,
            word_similarity(:name, usn.name_normalized) AS similarity
        FROM unified_site_names usn
        JOIN unified_sites us ON us.id = usn.site_id
        WHERE word_similarity(:name, usn.name_normalized) >= 0.3
        ORDER BY usn.site_id, word_similarity(:name, usn.name_normalized) DESC
    """), {"name": normalized_name})

    matches = []
    for row in result:
        # Construct Wikipedia URL if wikidata source
        wikipedia_url = None
        if row.source_id == "wikidata" and row.source_url:
            wikipedia_url = row.source_url
        elif row.site_name:
            # Fallback: construct from site name
            wiki_name = row.site_name.replace(" ", "_")
            wikipedia_url = f"https://en.wikipedia.org/wiki/{wiki_name}"

        matches.append({
            "site_id": str(row.site_id),
            "name": row.site_name,
            "similarity": round(row.similarity, 2),
            "thumbnail_url": row.thumbnail_url,
            "wikipedia_url": wikipedia_url,
            "country": row.country,
        })

    # Sort by similarity descending, take top N
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


@router.get("/list")
async def get_discoveries(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    min_mentions: int = Query(1, ge=1),
    sort_by: str = Query("score", regex="^(score|mentions|recency)$"),
    db: Session = Depends(get_db),
):
    """
    Get aggregated discoveries from news items.

    Groups news_items by normalized site_name_extracted where:
    - site_id IS NULL (not matched to a known site)
    - site_match_tried = true (matching was attempted)

    Returns deduplicated discoveries with:
    - All unique facts from all mentions
    - All video references with timestamps
    - Computed importance score
    - Top 5 similar site suggestions
    """
    cache_key = f"discoveries:list:{page}:{page_size}:{min_mentions}:{sort_by}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Aggregate query: group by normalized site name
    # Collect all facts, video IDs, channels, and compute stats
    agg_query = text("""
        WITH extracted AS (
            SELECT
                ni.site_name_extracted,
                lower(trim(ni.site_name_extracted)) AS name_normalized,
                ni.facts,
                ni.video_id,
                ni.timestamp_seconds,
                nv.title AS video_title,
                nc.id AS channel_id,
                nc.name AS channel_name,
                ni.created_at
            FROM news_items ni
            JOIN news_videos nv ON nv.id = ni.video_id
            JOIN news_channels nc ON nc.id = nv.channel_id
            WHERE ni.site_id IS NULL
              AND ni.site_match_tried = true
              AND ni.site_name_extracted IS NOT NULL
              AND ni.site_name_extracted != ''
        ),
        grouped AS (
            SELECT
                name_normalized,
                MAX(site_name_extracted) AS display_name,
                COUNT(*) AS mention_count,
                COUNT(DISTINCT video_id) AS unique_videos,
                COUNT(DISTINCT channel_id) AS unique_channels,
                MAX(created_at) AS last_mentioned,
                jsonb_agg(DISTINCT jsonb_build_object(
                    'video_id', video_id,
                    'channel_name', channel_name,
                    'timestamp_seconds', timestamp_seconds
                )) AS videos,
                jsonb_agg(facts) FILTER (WHERE facts IS NOT NULL) AS all_facts
            FROM extracted
            GROUP BY name_normalized
            HAVING COUNT(*) >= :min_mentions
        )
        SELECT
            name_normalized,
            display_name,
            mention_count,
            unique_videos,
            unique_channels,
            last_mentioned,
            videos,
            all_facts
        FROM grouped
        ORDER BY
            CASE WHEN :sort_by = 'mentions' THEN mention_count END DESC NULLS LAST,
            CASE WHEN :sort_by = 'recency' THEN last_mentioned END DESC NULLS LAST,
            mention_count DESC,
            last_mentioned DESC
    """)

    rows = db.execute(agg_query, {
        "min_mentions": min_mentions,
        "sort_by": sort_by,
    }).fetchall()

    # Process all rows for scoring, then paginate
    now = datetime.now(UTC)
    items_with_score = []

    for row in rows:
        # Calculate days since last mention
        if row.last_mentioned:
            last_dt = row.last_mentioned
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            days_since = (now - last_dt).total_seconds() / 86400
        else:
            days_since = 90.0

        score = compute_score(
            mentions=row.mention_count,
            videos=row.unique_videos,
            channels=row.unique_channels,
            days_since=days_since,
        )

        # Flatten and deduplicate facts from all mentions
        unique_facts = set()
        if row.all_facts:
            for fact_list in row.all_facts:
                if isinstance(fact_list, list):
                    for fact in fact_list:
                        if isinstance(fact, str) and fact.strip():
                            unique_facts.add(fact.strip())

        # Process video references
        videos = []
        seen_video_ids = set()
        if row.videos:
            for v in row.videos:
                vid = v.get("video_id")
                if vid and vid not in seen_video_ids:
                    seen_video_ids.add(vid)
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

        items_with_score.append({
            "name_normalized": row.name_normalized,
            "display_name": row.display_name,
            "facts": sorted(unique_facts),
            "videos": videos,
            "score": score,
            "mention_count": row.mention_count,
            "unique_videos": row.unique_videos,
            "unique_channels": row.unique_channels,
            "last_mentioned": row.last_mentioned.isoformat() if row.last_mentioned else None,
        })

    # Sort by score if that's the sort method
    if sort_by == "score":
        items_with_score.sort(key=lambda x: x["score"], reverse=True)

    # Paginate
    total_count = len(items_with_score)
    offset = (page - 1) * page_size
    page_items = items_with_score[offset:offset + page_size]

    # Find similar sites for each item on this page
    for item in page_items:
        normalized = normalize_name(item["name_normalized"])
        suggestions = find_similar_sites(db, normalized, limit=5)
        item["suggestions"] = suggestions

        # Best match if top suggestion has similarity >= 0.6
        if suggestions and suggestions[0]["similarity"] >= 0.6:
            item["best_match"] = suggestions[0]
        else:
            item["best_match"] = None

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

    # Count unique discoveries (unmatched sites)
    discoveries = db.execute(text("""
        SELECT COUNT(DISTINCT lower(trim(site_name_extracted)))
        FROM news_items
        WHERE site_id IS NULL
          AND site_match_tried = true
          AND site_name_extracted IS NOT NULL
          AND site_name_extracted != ''
    """)).scalar() or 0

    # Total known sites
    sites_known = db.execute(text("""
        SELECT COUNT(*) FROM unified_sites
    """)).scalar() or 0

    # Total name variants
    name_variants = db.execute(text("""
        SELECT COUNT(*) FROM unified_site_names
    """)).scalar() or 0

    response = {
        "total_discoveries": discoveries,
        "total_sites_known": sites_known,
        "total_name_variants": name_variants,
    }

    cache_set(cache_key, response, ttl=CACHE_TTL)
    return response
