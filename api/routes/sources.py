"""
Sources API Routes.

Provides source metadata for filtering and display.
Falls back to static JSON files if database is empty.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set
from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# Path to static sources.json (relative to project root)
STATIC_SOURCES_PATH = Path(__file__).parent.parent.parent / "public" / "data" / "sources.json"

# Default source colors (matches pipeline SOURCE_CONFIG)
DEFAULT_SOURCE_COLORS = {
    # PRIMARY SOURCES
    "ancient_nerds": "#FFD700",   # Gold - Primary source (manually curated)
    "lyra": "#8b5cf6",            # Purple - Lyra auto-discoveries

    # Core ancient world
    "pleiades": "#e74c3c",        # Red - ancient places
    "dare": "#6c5ce7",            # Violet-blue - Roman Empire
    "topostext": "#00bcd4",       # Cyan - ancient texts (NO TEAL - coastlines are teal)

    # Global databases
    "unesco": "#ffd700",          # Gold/Yellow - UNESCO
    "wikidata": "#9966ff",        # Purple - Wikidata (NO GREEN)
    "osm_historic": "#ff9800",    # Orange - OSM (NO GREEN)

    # Europe
    "historic_england": "#c0392b", # Dark red - England
    "ireland_nms": "#ff6699",     # Pink - Ireland (NO GREEN)
    "arachne": "#8e44ad",         # Dark purple - Arachne
    "megalithic_portal": "#9966cc", # Amethyst Purple - megaliths

    # Specialized
    "sacred_sites": "#ff69b4",    # Hot Pink - sacred sites
    "rock_art": "#e67e22",        # Orange - rock art
    "inscriptions_edh": "#5dade2", # Light blue - inscriptions
    "coins_nomisma": "#d4af37",   # Gold - coins
    "shipwrecks_oxrep": "#0066ff", # Ocean Blue - shipwrecks
    "volcanic_holvol": "#ff0000", # Bright Red - volcanoes

    # Americas & MENA
    "dinaa": "#cd853f",           # Peru brown - Americas
    "eamena": "#d35400",          # Dark orange - MENA
    "open_context": "#2980b9",    # Strong blue - Open Context

    # Fallback
    "default": "#ff00ff",         # Magenta - visible fallback
}


def _load_static_sources():
    """Load sources from static JSON file."""
    if not STATIC_SOURCES_PATH.exists():
        logger.warning(f"Static sources file not found: {STATIC_SOURCES_PATH}")
        return None

    with open(STATIC_SOURCES_PATH) as f:
        data = json.load(f)

    sources = []
    for source_id, info in data.get("sources", {}).items():
        sources.append({
            "id": source_id,
            "name": info.get("n", source_id.replace("_", " ").title()),
            "count": info.get("cnt", 0),
            "color": info.get("c", DEFAULT_SOURCE_COLORS.get(source_id, DEFAULT_SOURCE_COLORS["default"])),
            "isPrimary": source_id in ("ancient_nerds", "lyra"),
            "enabledByDefault": info.get("on", False),
            "priority": 0 if source_id == "ancient_nerds" else (1 if source_id == "lyra" else 50),
            "category": info.get("cat"),
            "description": info.get("d"),
        })

    return {
        "count": len(sources),
        "sources": sorted(sources, key=lambda x: (x["priority"], -x["count"])),
    }


@router.get("/")
async def get_sources(db: Session = Depends(get_db)):
    """
    Get all sources with site counts, including primary/default flags.
    Falls back to static JSON if database is empty.
    """
    # Try cache first
    cache_key = "api:sources:all"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Try database first
    try:
        query = text("""
            SELECT
                sm.id as source_id,
                COALESCE(site_counts.count, 0) as count,
                sm.name,
                COALESCE(sm.color, :default_color) as color,
                COALESCE(sm.is_primary, false) as is_primary,
                COALESCE(sm.enabled_by_default, false) as enabled_by_default,
                COALESCE(sm.priority, 999) as priority,
                sm.category,
                sm.description
            FROM source_meta sm
            LEFT JOIN (
                SELECT source_id, COUNT(*) as count
                FROM unified_sites
                GROUP BY source_id
            ) site_counts ON sm.id = site_counts.source_id
            WHERE sm.enabled = true
            ORDER BY sm.priority, COALESCE(site_counts.count, 0) DESC
        """)

        result = db.execute(query, {"default_color": DEFAULT_SOURCE_COLORS["default"]})

        sources = []
        for row in result:
            source_id = row.source_id
            sources.append({
                "id": source_id,
                "name": row.name or source_id.replace("_", " ").title(),
                "count": row.count,
                "color": row.color or DEFAULT_SOURCE_COLORS.get(source_id, DEFAULT_SOURCE_COLORS["default"]),
                "isPrimary": row.is_primary,
                "enabledByDefault": row.enabled_by_default,
                "priority": row.priority,
                "category": row.category,
                "description": row.description,
            })

        if sources:
            response = {
                "count": len(sources),
                "sources": sources,
            }
            cache_set(cache_key, response, ttl=600)
            return response
    except Exception as e:
        logger.warning(f"Database query failed, falling back to static files: {e}")

    # Fall back to static JSON
    logger.info("Loading sources from static JSON file")
    response = _load_static_sources()
    if response:
        cache_set(cache_key, response, ttl=600)
        return response

    raise HTTPException(status_code=500, detail="No source data available")


@router.get("/{source_id}")
async def get_source_detail(
    source_id: str,
    db: Session = Depends(get_db),
):
    """Get details for a single source (cached for 10 minutes)."""
    # Try cache first
    cache_key = f"api:sources:{source_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Get count
    count_query = text("""
        SELECT COUNT(*) FROM unified_sites WHERE source_id = :source_id
    """)
    result = db.execute(count_query, {"source_id": source_id})
    count = result.scalar()

    if count == 0:
        raise HTTPException(status_code=404, detail="Source not found")

    # Get type breakdown
    type_query = text("""
        SELECT site_type, COUNT(*) as count
        FROM unified_sites
        WHERE source_id = :source_id AND site_type IS NOT NULL
        GROUP BY site_type
        ORDER BY count DESC
        LIMIT 20
    """)
    result = db.execute(type_query, {"source_id": source_id})
    types = {row.site_type: row.count for row in result}

    # Get period breakdown
    period_query = text("""
        SELECT
            CASE
                WHEN period_start < -4500 THEN '< 4500 BC'
                WHEN period_start < -3000 THEN '4500 - 3000 BC'
                WHEN period_start < -1500 THEN '3000 - 1500 BC'
                WHEN period_start < -500 THEN '1500 - 500 BC'
                WHEN period_start < 1 THEN '500 BC - 1 AD'
                WHEN period_start < 500 THEN '1 - 500 AD'
                WHEN period_start < 1500 THEN '500 - 1500 AD'
                ELSE 'Unknown'
            END as period,
            COUNT(*) as count
        FROM unified_sites
        WHERE source_id = :source_id
        GROUP BY period
        ORDER BY MIN(COALESCE(period_start, 0))
    """)
    result = db.execute(period_query, {"source_id": source_id})
    periods = {row.period: row.count for row in result}

    response = {
        "id": source_id,
        "name": source_id.replace("_", " ").title(),
        "count": count,
        "color": DEFAULT_SOURCE_COLORS.get(source_id, DEFAULT_SOURCE_COLORS["default"]),
        "types": types,
        "periods": periods,
    }

    # Cache for 10 minutes
    cache_set(cache_key, response, ttl=600)
    return response
