"""
Sites API Routes - High Performance Spatial Queries.

Supports:
- Viewport filtering (bounding box)
- H3 clustering for zoom levels
- Source/type/period filtering
- Site updates (admin)
- Static JSON fallback when database is empty
"""

import json
import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern, cache_get, cache_set
from pipeline.database import get_db
from pipeline.normalizers.site_type import normalize_site_type

logger = logging.getLogger(__name__)
router = APIRouter()

# Paths to static sites JSON files (both need to be kept in sync)
STATIC_SITES_PATH = Path(__file__).parent.parent.parent / "ancient-nerds-map" / "dist" / "data" / "sites" / "index.json"
PUBLIC_SITES_PATH = Path(__file__).parent.parent.parent / "public" / "data" / "sites" / "index.json"

# Cache for static sites (loaded once)
_static_sites_cache = None


def _load_static_sites():
    """Load sites from static JSON file (cached)."""
    global _static_sites_cache

    if _static_sites_cache is not None:
        return _static_sites_cache

    # Try dist path first (local dev), then public path (Docker / fallback)
    if STATIC_SITES_PATH.exists():
        path = STATIC_SITES_PATH
    elif PUBLIC_SITES_PATH.exists():
        path = PUBLIC_SITES_PATH
    else:
        logger.warning(f"Static sites file not found at {STATIC_SITES_PATH} or {PUBLIC_SITES_PATH}")
        return None

    logger.info(f"Loading static sites from {path}")
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        sites = data.get("sites", [])
        logger.info(f"Loaded {len(sites)} sites from static JSON")
        _static_sites_cache = sites
        return sites
    except Exception as e:
        logger.error(f"Failed to load static sites: {e}")
        return None


def _filter_static_sites(sites, sources=None, site_type=None, period_max=None, skip=0, limit=50000):
    """Filter static sites by source, type, and period."""
    filtered = sites

    if sources:
        filtered = [s for s in filtered if s.get("s") in sources]

    if site_type:
        filtered = [s for s in filtered if s.get("t") == site_type]

    if period_max is not None:
        def period_matches(site):
            p = site.get("p")
            if p is None:
                return True  # Include sites without period
            if isinstance(p, list) and len(p) > 0:
                return p[0] <= period_max  # Check period_start
            return True
        filtered = [s for s in filtered if period_matches(s)]

    # Apply pagination
    return filtered[skip:skip + limit]


def _convert_static_site(site):
    """Convert static site format to API response format."""
    result = {
        "id": site.get("i"),
        "n": site.get("n"),
        "la": site.get("la"),
        "lo": site.get("lo"),
        "s": site.get("s"),
        "t": site.get("t"),
        "p": site.get("p")[0] if isinstance(site.get("p"), list) and site.get("p") else None,
    }
    # Include period_name if present (user-edited period)
    if site.get("pn"):
        result["pn"] = site.get("pn")
    if site.get("d"):
        result["d"] = site.get("d")
    if site.get("im"):
        result["i"] = site.get("im")
    if site.get("c"):
        result["c"] = site.get("c")
    if site.get("u"):
        result["u"] = site.get("u")
    if site.get("an"):
        result["an"] = site.get("an")
    return result


class SiteUpdateRequest(BaseModel):
    """Request model for updating a site."""
    title: str = Field(..., max_length=500)
    location: str | None = Field(default=None, max_length=500)
    category: str = Field(..., max_length=100)
    period: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    sourceUrl: str | None = Field(default=None, max_length=2000)
    coordinates: list[float] = Field(..., min_length=2, max_length=2, description="[lng, lat]")


def _period_to_year(period: str) -> int | None:
    """Convert period name to approximate year for dot coloring."""
    period_years = {
        '< 4500 BC': -5000,
        '4500 - 3000 BC': -3750,
        '3000 - 1500 BC': -2250,
        '1500 - 500 BC': -1000,
        '500 BC - 1 AD': -250,
        '1 - 500 AD': 250,
        '500 - 1000 AD': 750,
        '1000 - 1500 AD': 1250,
        '1500+ AD': 1750,
        'Unknown': None,
    }
    return period_years.get(period)


def _update_single_json_file(file_path: Path, site_id: str, site_update: 'SiteUpdateRequest') -> bool:
    """Update a single static JSON file with the edited site data."""
    if not file_path.exists():
        logger.warning(f"Static sites file not found: {file_path}")
        return False

    try:
        # Load the JSON file
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)

        sites = data.get("sites", [])
        updated = False

        # Find and update the site
        for site in sites:
            # Check both 'i' (compact) and 'id' formats
            sid = site.get("i") or site.get("id")
            if sid == site_id:
                site["n"] = site_update.title
                site["la"] = site_update.coordinates[1]  # lat
                site["lo"] = site_update.coordinates[0]  # lon
                site["t"] = site_update.category
                # Store period name in 'pn' field
                site["pn"] = site_update.period
                # Also update numeric period for dot coloring
                period_year = _period_to_year(site_update.period)
                if period_year is not None:
                    site["p"] = [period_year, period_year]  # [start, end]
                else:
                    site["p"] = None
                if site_update.description:
                    site["d"] = site_update.description[:500]  # Truncate to match export
                if site_update.sourceUrl:
                    site["u"] = site_update.sourceUrl
                updated = True
                logger.info(f"Updated site {site_id} in {file_path.name}")
                break

        if updated:
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'))  # Compact JSON
            return True
        else:
            logger.warning(f"Site {site_id} not found in {file_path.name}")
            return False

    except Exception as e:
        logger.error(f"Failed to update {file_path.name}: {e}")
        return False


def _update_static_json(site_id: str, site_update: 'SiteUpdateRequest'):
    """Update both static JSON files with the edited site data."""
    dist_updated = _update_single_json_file(STATIC_SITES_PATH, site_id, site_update)
    public_updated = _update_single_json_file(PUBLIC_SITES_PATH, site_id, site_update)

    if dist_updated or public_updated:
        logger.info(f"Static JSON updated - dist: {dist_updated}, public: {public_updated}")

    return dist_updated or public_updated




def _load_pinned_sites(
    source_id: str,
    snap_date: str,
    site_type: str | None = None,
    period_max: int | None = None,
) -> list[dict]:
    """Load sites for a pinned source from a snapshot JSON file."""
    from api.routes.snapshots import SNAPSHOTS_DIR
    path = SNAPSHOTS_DIR / f"{snap_date}.json"
    if not path.exists():
        logger.warning(f"Pinned snapshot not found: {snap_date}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sites = [s for s in data.get("sites", []) if s.get("s") == source_id]
    if site_type:
        sites = [s for s in sites if s.get("t") == site_type]
    if period_max is not None:
        sites = [s for s in sites if s.get("p") is None or s["p"] <= period_max]
    return sites


@router.get("/all")
async def get_all_sites(
    db: Session = Depends(get_db),
    source: list[str] | None = Query(None, description="Filter by source IDs"),
    site_type: str | None = Query(None, description="Filter by site type"),
    period_max: int | None = Query(None, description="Max period year"),
    skip: int = Query(0, ge=0, description="Number of records to skip (pagination)"),
    limit: int = Query(100000, ge=1, le=100000, description="Max results"),
):
    """
    Get all sites as compact JSON for globe rendering.

    Returns minimal data for fast transfer:
    - id, name, lat, lon, source_id, site_type, period_start

    Respects version pins: if a source is pinned to a snapshot, data for that
    source comes from the snapshot file instead of the live database.

    Falls back to static JSON if database is empty.
    """
    # Check active pins
    from api.routes.snapshots import get_active_pins
    pins = get_active_pins(db)

    # Determine which requested sources are pinned vs live
    requested_sources = set(source) if source else {"ancient_nerds", "lyra", "ancient_nerds_community"}
    pinned_sources: dict[str, str] = {sid: pins[sid] for sid in requested_sources if sid in pins and pins[sid] is not None}  # type: ignore[misc]
    live_sources = [sid for sid in requested_sources if sid not in pinned_sources]

    # Include pin fingerprint in cache key so pinned vs unpinned don't collide
    pin_fp = ",".join(f"{k}={v}" for k, v in sorted(pinned_sources.items())) if pinned_sources else "none"
    source_key = ",".join(sorted(requested_sources))
    cache_key = f"sites:all:{source_key}:{site_type or 'all'}:{period_max or 'all'}:{skip}:{limit}:pin={pin_fp}"

    # Try cache first (30 min TTL)
    cached = cache_get(cache_key)
    if cached:
        return cached

    all_sites: list[dict] = []

    # Load pinned sources from snapshot files
    for sid, snap_date in pinned_sources.items():
        all_sites.extend(_load_pinned_sites(sid, snap_date, site_type, period_max))

    # Load live sources from database
    if live_sources:
        try:
            conditions = ["source_id = ANY(:sources)"]
            params: dict[str, object] = {"limit": limit, "skip": skip, "sources": live_sources}

            if site_type:
                conditions.append("site_type = :site_type")
                params["site_type"] = site_type

            if period_max is not None:
                conditions.append("(period_start IS NULL OR period_start <= :period_max)")
                params["period_max"] = period_max

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    id::text,
                    name,
                    lat,
                    lon,
                    source_id,
                    site_type,
                    period_start,
                    period_name,
                    description,
                    thumbnail_url,
                    country,
                    source_url,
                    edited_by,
                    updated_at
                FROM unified_sites
                WHERE {where_clause}
                OFFSET :skip
                LIMIT :limit
            """)

            result = db.execute(query, params)

            for row in result:
                site = {
                    "id": row.id,
                    "n": row.name,
                    "la": row.lat,
                    "lo": row.lon,
                    "s": row.source_id,
                    "t": row.site_type,
                    "p": row.period_start,
                }
                if row.period_name:
                    site["pn"] = row.period_name
                if row.description:
                    site["d"] = row.description
                if row.thumbnail_url:
                    site["i"] = row.thumbnail_url
                if row.country:
                    site["c"] = row.country
                if row.source_url:
                    site["u"] = row.source_url
                if row.edited_by and row.edited_by != "initial":
                    site["eb"] = row.edited_by
                if row.updated_at:
                    site["ea"] = row.updated_at.isoformat()
                all_sites.append(site)
        except Exception as e:
            logger.warning(f"Database query failed for live sources: {e}")
            # Fall back to static JSON for live sources
            static_sites = _load_static_sites()
            if static_sites:
                filtered = _filter_static_sites(static_sites, live_sources, site_type, period_max, skip, limit)
                all_sites.extend(_convert_static_site(s) for s in filtered)

    if all_sites:
        response = {
            "count": len(all_sites),
            "sites": all_sites,
            "dataSource": "postgres" if live_sources else "snapshot",
        }
        cache_set(cache_key, response, ttl=1800)
        return response

    # If no live sources were requested (all pinned) and no pinned sites found,
    # or if DB was empty — try static JSON as final fallback
    if not pinned_sources:
        static_sites = _load_static_sites()
        if static_sites:
            filtered = _filter_static_sites(static_sites, source, site_type, period_max, skip, limit)
            converted = [_convert_static_site(s) for s in filtered]
            logger.info(f"Returning {len(converted)} sites from static JSON")
            return {
                "count": len(converted),
                "sites": converted,
                "dataSource": "json",
            }

    return {
        "count": 0,
        "sites": [],
        "dataSource": "none",
    }


@router.get("/viewport")
async def get_sites_in_viewport(
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    source: list[str] | None = Query(None),
    limit: int = Query(10000, le=100000),
    db: Session = Depends(get_db),
):
    """
    Get sites within a bounding box (viewport).

    Uses PostGIS spatial index via ST_MakeEnvelope and && operator.
    """
    # Use PostGIS bounding box operator (&&) which leverages spatial index
    # ST_MakeEnvelope(xmin, ymin, xmax, ymax, srid) creates a bounding box
    conditions = [
        "geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
    ]
    params: dict[str, object] = {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "limit": limit,
    }

    if source:
        conditions.append("source_id = ANY(:sources)")
        params["sources"] = source

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT
            id::text,
            name,
            lat,
            lon,
            source_id,
            site_type,
            period_start
        FROM unified_sites
        WHERE {where_clause}
        LIMIT :limit
    """)

    result = db.execute(query, params)

    sites = []
    for row in result:
        sites.append({
            "id": row.id,
            "n": row.name,
            "la": row.lat,
            "lo": row.lon,
            "s": row.source_id,
            "t": row.site_type,
            "p": row.period_start,
        })

    return {
        "count": len(sites),
        "sites": sites,
    }


@router.get("/clustered")
async def get_clustered_sites(
    resolution: int = Query(3, ge=0, le=7, description="H3 resolution (0=global, 7=fine)"),
    source: list[str] | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get sites clustered by pre-computed H3 hex indexes.

    Returns cluster centers with counts for efficient rendering at low zoom.
    Uses h3_index_res5 for coarse views (res 0-5) and h3_index_res7 for fine views (6-7).

    Resolution guide:
    - 0-1: Global view (continent-level clusters)
    - 2-3: Regional view (country-level)
    - 4-5: Local view (city-level)
    - 6-7: Detailed view (neighborhood-level)
    """
    params = {}
    source_filter = ""

    if source:
        source_filter = "AND source_id = ANY(:sources)"
        params["sources"] = source

    # Use pre-computed H3 indexes for efficient clustering
    # h3_index_res5 for coarse views, h3_index_res7 for fine views
    if resolution <= 5:
        h3_column = "h3_index_res5"
    else:
        h3_column = "h3_index_res7"

    # Use H3 indexes with GROUP BY for fast clustering
    # Fall back to grid-based if H3 index is NULL
    query = text(f"""
        WITH clusters AS (
            SELECT
                COALESCE({h3_column}, CONCAT(ROUND(lat::numeric, 1)::text, '_', ROUND(lon::numeric, 1)::text)) as cluster_key,
                COUNT(*) as count,
                AVG(lat) as center_lat,
                AVG(lon) as center_lon,
                MODE() WITHIN GROUP (ORDER BY source_id) as primary_source
            FROM unified_sites
            WHERE lat IS NOT NULL AND lon IS NOT NULL {source_filter}
            GROUP BY cluster_key
        )
        SELECT
            center_lat as lat,
            center_lon as lon,
            count,
            primary_source as source_id
        FROM clusters
        ORDER BY count DESC
        LIMIT 50000
    """)

    result = db.execute(query, params)

    clusters = []
    for row in result:
        clusters.append({
            "la": round(row.lat, 4),
            "lo": round(row.lon, 4),
            "c": row.count,
            "s": row.source_id,
        })

    return {
        "resolution": resolution,
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


@router.get("/search")
async def search_sites(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
):
    """
    Search sites across all sources by name (spaceless-aware).

    Returns compact format matching /sites/all for frontend reuse.
    """
    from pipeline.utils.text import normalize_name

    normalized = normalize_name(q)
    if not normalized or len(normalized) < 2:
        return {"count": 0, "sites": []}

    # Escape SQL LIKE wildcards in user input
    normalized_escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    spaceless = normalized.replace(" ", "")
    spaceless_escaped = spaceless.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # Exact + spaceless match on name_normalized
    query = text("""
        SELECT
            id::text, name, lat, lon, source_id, site_type,
            period_start, period_name, description, country, source_url,
            CASE
                WHEN name_normalized = :norm THEN 1
                WHEN replace(name_normalized, ' ', '') = :spaceless THEN 2
            END AS rank
        FROM unified_sites
        WHERE name_normalized = :norm
           OR replace(name_normalized, ' ', '') = :spaceless
        ORDER BY rank, name
        LIMIT :limit
    """)

    result = db.execute(query, {
        "norm": normalized,
        "spaceless": spaceless,
        "limit": limit,
    })
    sites = []
    seen_ids = set()
    for row in result:
        seen_ids.add(row.id)
        site = {
            "id": row.id,
            "n": row.name,
            "la": row.lat,
            "lo": row.lon,
            "s": row.source_id,
            "t": row.site_type,
            "p": row.period_start,
        }
        if row.period_name:
            site["pn"] = row.period_name
        if row.description:
            site["d"] = row.description
        if row.country:
            site["c"] = row.country
        if row.source_url:
            site["u"] = row.source_url
        sites.append(site)

    # If not enough results, broaden with ILIKE substring match
    if len(sites) < limit:
        remaining = limit - len(sites)
        ilike_query = text("""
            SELECT
                id::text, name, lat, lon, source_id, site_type,
                period_start, period_name, description, country, source_url
            FROM unified_sites
            WHERE (name_normalized ILIKE :pattern ESCAPE '\\'
                   OR replace(name_normalized, ' ', '') ILIKE :spaceless_pattern ESCAPE '\\')
              AND id::text != ALL(:seen)
            ORDER BY name
            LIMIT :limit
        """)
        result2 = db.execute(ilike_query, {
            "pattern": f"%{normalized_escaped}%",
            "spaceless_pattern": f"%{spaceless_escaped}%",
            "seen": list(seen_ids),
            "limit": remaining,
        })
        for row in result2:
            site = {
                "id": row.id,
                "n": row.name,
                "la": row.lat,
                "lo": row.lon,
                "s": row.source_id,
                "t": row.site_type,
                "p": row.period_start,
            }
            if row.period_name:
                site["pn"] = row.period_name
            if row.description:
                site["d"] = row.description
            if row.country:
                site["c"] = row.country
            if row.source_url:
                site["u"] = row.source_url
            sites.append(site)

    return {"count": len(sites), "sites": sites}


# =============================================================================
# Snapshot Endpoints (must be above /{site_id} catch-all to avoid shadowing)
# =============================================================================


@router.get("/snapshots")
async def get_snapshots(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent database snapshots."""
    from api.services.snapshots import list_snapshots
    return {"snapshots": list_snapshots(db, limit)}


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot_endpoint(
    snapshot_id: str,
    authorization: str | None = Header(None),
    x_admin_pin: str | None = Header(None, alias="X-Admin-Pin"),
    db: Session = Depends(get_db),
):
    """Restore all rows from a snapshot."""
    from api.services.snapshots import restore_snapshot

    _verify_admin(authorization, x_admin_pin)

    count = restore_snapshot(db, snapshot_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Snapshot not found or empty")

    global _static_sites_cache
    _static_sites_cache = None

    return {"restored": count, "snapshot_id": snapshot_id}


@router.get("/{site_id}/alternates")
async def get_site_alternates(
    site_id: str,
    db: Session = Depends(get_db),
):
    """
    Find alternate database entries for the same real-world site.

    Matches by shared normalized names (via unified_site_names) within ~50 km,
    from a different source. Joins source_meta for display info.
    """
    # First get the site's location
    site_query = text("""
        SELECT id, lat, lon FROM unified_sites WHERE id::text = :site_id
    """)
    site_row = db.execute(site_query, {"site_id": site_id}).fetchone()
    if not site_row:
        raise HTTPException(status_code=404, detail="Site not found")

    query = text("""
        WITH site_names AS (
            SELECT name_normalized FROM unified_site_names WHERE site_id = :site_uuid
        )
        SELECT DISTINCT ON (us.source_id)
            us.id::text AS id,
            us.source_id,
            us.name,
            us.source_url,
            us.description,
            us.thumbnail_url,
            us.site_type,
            us.period_name,
            us.period_start,
            us.country,
            us.lat,
            us.lon,
            sm.name AS source_name,
            sm.color AS source_color
        FROM unified_sites us
        JOIN unified_site_names usn ON usn.site_id = us.id
        LEFT JOIN source_meta sm ON sm.id = us.source_id
        WHERE usn.name_normalized IN (SELECT name_normalized FROM site_names)
          AND us.id != :site_uuid
          AND ABS(us.lat - :lat) < 0.5
          AND ABS(us.lon - :lon) < 0.5
        ORDER BY us.source_id, us.name
    """)

    result = db.execute(query, {
        "site_uuid": site_row.id,
        "lat": site_row.lat,
        "lon": site_row.lon,
    })

    alternates = []
    for row in result:
        alt = {
            "id": row.id,
            "sourceId": row.source_id,
            "sourceName": row.source_name or row.source_id,
            "sourceColor": row.source_color or "#888888",
            "name": row.name,
            "lat": row.lat,
            "lon": row.lon,
        }
        if row.source_url:
            alt["sourceUrl"] = row.source_url
        if row.description:
            alt["description"] = row.description
        if row.thumbnail_url:
            alt["thumbnailUrl"] = row.thumbnail_url
        if row.site_type:
            alt["siteType"] = row.site_type
        if row.period_name:
            alt["periodName"] = row.period_name
        if row.period_start is not None:
            alt["periodStart"] = row.period_start
        if row.country:
            alt["country"] = row.country
        alternates.append(alt)

    return {"alternates": alternates}


@router.get("/{site_id}")
async def get_site_detail(
    site_id: str,
    db: Session = Depends(get_db),
):
    """Get full details for a single site."""
    # Try UUID match first, then fall back to name search
    import uuid as _uuid
    try:
        _uuid.UUID(site_id)
        is_uuid = True
    except ValueError:
        is_uuid = False

    if is_uuid:
        query = text("""
            SELECT id::text, source_id, source_record_id, name, lat, lon,
                   site_type, period_start, period_end, period_name,
                   country, description, thumbnail_url, source_url, raw_data
            FROM unified_sites WHERE id::text = :site_id
        """)
        result = db.execute(query, {"site_id": site_id})
    else:
        query = text("""
            SELECT id::text, source_id, source_record_id, name, lat, lon,
                   site_type, period_start, period_end, period_name,
                   country, description, thumbnail_url, source_url, raw_data
            FROM unified_sites
            WHERE name ILIKE :name
               OR name_normalized = LOWER(:name)
               OR REPLACE(name_normalized, ' ', '') = LOWER(REPLACE(:name, ' ', ''))
               OR id IN (SELECT site_id FROM unified_site_names WHERE name ILIKE :name)
            LIMIT 1
        """)
        result = db.execute(query, {"name": site_id})

    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    return {
        "id": row.id,
        "sourceId": row.source_id,
        "sourceRecordId": row.source_record_id,
        "name": row.name,
        "lat": row.lat,
        "lon": row.lon,
        "type": row.site_type,
        "periodStart": row.period_start,
        "periodEnd": row.period_end,
        "periodName": row.period_name,
        "country": row.country,
        "description": row.description,
        "thumbnailUrl": row.thumbnail_url,
        "sourceUrl": row.source_url,
        "rawData": row.raw_data,
    }


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract token from Authorization: Bearer <token> header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer scheme")
    return authorization[7:]  # Remove "Bearer " prefix


def _sync_to_radar(db: Session, site_id: str, site_update: 'SiteUpdateRequest', lat: float, lon: float) -> int:
    """Sync site changes to user_contributions via promoted_site_id FK. Returns synced count."""
    sync_result = db.execute(
        text("""
            UPDATE user_contributions
            SET corrected_name = :name,
                description = :description,
                lat = :lat,
                lon = :lon,
                site_type = :site_type,
                period_name = :period_name,
                thumbnail_url = (SELECT thumbnail_url FROM unified_sites WHERE id::text = :site_id),
                wikipedia_url = :source_url
            WHERE promoted_site_id::text = :site_id
            RETURNING id
        """),
        {
            "site_id": site_id,
            "name": site_update.title,
            "description": site_update.description,
            "lat": lat,
            "lon": lon,
            "site_type": normalize_site_type(site_update.category),
            "period_name": site_update.period,
            "source_url": site_update.sourceUrl,
        },
    )
    return len(sync_result.fetchall())


def _verify_admin(authorization: str | None, x_admin_pin: str | None) -> str:
    """Verify admin credentials. Returns edited_by label. Raises HTTPException on failure."""
    from api.services.admin_auth import ADMIN_PIN

    if authorization:
        admin_key = _extract_bearer_token(authorization)
        configured_admin_key = os.getenv("ADMIN_KEY", "")
        if not configured_admin_key:
            raise HTTPException(status_code=503, detail="Admin access not configured")
        if not secrets.compare_digest(admin_key, configured_admin_key):
            raise HTTPException(status_code=403, detail="Invalid admin key")
        return "admin"
    elif x_admin_pin:
        if not ADMIN_PIN:
            raise HTTPException(status_code=503, detail="Admin PIN not configured")
        if not secrets.compare_digest(x_admin_pin, ADMIN_PIN):
            raise HTTPException(status_code=403, detail="Invalid admin PIN")
        return "audit"
    else:
        raise HTTPException(status_code=401, detail="Authorization required")


@router.put("/{site_id}")
async def update_site(
    site_id: str,
    site_update: SiteUpdateRequest,
    authorization: str | None = Header(None, description="Bearer token for admin authentication"),
    x_admin_pin: str | None = Header(None, alias="X-Admin-Pin"),
    db: Session = Depends(get_db),
):
    """
    Update a site's details (admin only).

    Updates name, description, location, coordinates, category, period, and source URL.
    Accepts EITHER:
    - Authorization: Bearer <ADMIN_KEY> header (existing)
    - X-Admin-Pin: <4-digit PIN> header (DB audit page)
    """
    edited_by = _verify_admin(authorization, x_admin_pin)

    # First check if site exists
    check_query = text("SELECT id FROM unified_sites WHERE id::text = :site_id")
    result = db.execute(check_query, {"site_id": site_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Site not found")

    # Extract lat/lon from coordinates [lng, lat]
    lon = site_update.coordinates[0]
    lat = site_update.coordinates[1]

    # Convert period name to approximate year for dot coloring
    period_start = _period_to_year(site_update.period)

    # Update the site - period_name stores the display string, period_start stores numeric year
    update_query = text("""
        UPDATE unified_sites
        SET
            name = :name,
            description = :description,
            lat = :lat,
            lon = :lon,
            geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            site_type = :site_type,
            period_name = :period_name,
            period_start = :period_start,
            source_url = :source_url,
            edited_by = :edited_by,
            updated_at = NOW()
        WHERE id::text = :site_id
    """)

    db.execute(update_query, {
        "site_id": site_id,
        "name": site_update.title,
        "description": site_update.description,
        "lat": lat,
        "lon": lon,
        "site_type": normalize_site_type(site_update.category),
        "period_name": site_update.period,
        "period_start": period_start,
        "source_url": site_update.sourceUrl,
        "edited_by": edited_by,
    })

    # Sync changes to user_contributions (radar) where promoted_site_id matches
    synced = _sync_to_radar(db, site_id, site_update, lat, lon)

    db.commit()

    # Also update static JSON file so both sources stay in sync
    static_updated = _update_static_json(site_id, site_update)

    # Invalidate all sites caches to ensure fresh data on next request
    deleted = cache_delete_pattern("sites:*")
    if synced > 0:
        cache_delete_pattern("radar:*")

    # Clear the static sites cache so it reloads from file
    global _static_sites_cache
    _static_sites_cache = None

    logger.info(f"Updated site {site_id}: {site_update.title} (DB + static JSON: {static_updated}, radar synced: {synced}, invalidated {deleted} cache entries)")

    return {"success": True, "message": "Site updated successfully", "staticUpdated": static_updated, "radarSynced": synced}


# =============================================================================
# Batch Update Endpoint
# =============================================================================


class BatchSiteUpdate(BaseModel):
    """Single site update within a batch."""
    id: str = Field(..., max_length=100)
    title: str = Field(..., max_length=500)
    location: str | None = Field(default=None, max_length=500)
    category: str = Field(..., max_length=100)
    period: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    sourceUrl: str | None = Field(default=None, max_length=2000)
    country: str | None = Field(default=None, max_length=200)
    coordinates: list[float] = Field(..., min_length=2, max_length=2)


@router.post("/batch-update")
async def batch_update_sites(
    updates: list[BatchSiteUpdate],
    authorization: str | None = Header(None),
    x_admin_pin: str | None = Header(None, alias="X-Admin-Pin"),
    db: Session = Depends(get_db),
):
    """
    Apply multiple site updates in a single transaction with snapshot.

    Creates a snapshot of all affected rows before applying changes.
    Syncs changes to radar (user_contributions) where applicable.
    """
    from api.services.snapshots import create_snapshot

    edited_by = _verify_admin(authorization, x_admin_pin)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    if len(updates) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 updates per batch")

    site_ids = [u.id for u in updates]

    # Create snapshot before changes
    snapshot_id = create_snapshot(
        db, site_ids,
        created_by=edited_by,
        description=f"Edited {len(updates)} site{'s' if len(updates) != 1 else ''}",
        snapshot_type="edit",
    )

    total_synced = 0
    for update in updates:
        lon = update.coordinates[0]
        lat = update.coordinates[1]
        period_start = _period_to_year(update.period)

        db.execute(
            text("""
                UPDATE unified_sites SET
                    name = :name, description = :description,
                    lat = :lat, lon = :lon,
                    geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                    site_type = :site_type, period_name = :period_name,
                    period_start = :period_start, source_url = :source_url,
                    country = :country,
                    edited_by = :edited_by, updated_at = NOW()
                WHERE id::text = :site_id
            """),
            {
                "site_id": update.id,
                "name": update.title,
                "description": update.description,
                "lat": lat,
                "lon": lon,
                "site_type": normalize_site_type(update.category),
                "period_name": update.period,
                "period_start": period_start,
                "source_url": update.sourceUrl,
                "country": update.country,
                "edited_by": edited_by,
            },
        )

        # Sync to radar
        fake_req = SiteUpdateRequest(
            title=update.title, category=update.category,
            period=update.period, description=update.description,
            sourceUrl=update.sourceUrl, coordinates=update.coordinates,
        )
        total_synced += _sync_to_radar(db, update.id, fake_req, lat, lon)

    db.commit()

    cache_delete_pattern("sites:*")
    if total_synced > 0:
        cache_delete_pattern("radar:*")

    global _static_sites_cache
    _static_sites_cache = None

    # Create file-based snapshot for version history dropdown
    from api.services.snapshots import export_file_snapshot
    file_snapshot_key = export_file_snapshot(db)

    return {
        "snapshot_id": snapshot_id,
        "updated": len(updates),
        "synced_radar": total_synced,
        "file_snapshot": file_snapshot_key,
    }


# =============================================================================
# Batch Upload Endpoint
# =============================================================================


class ParsedSitePayload(BaseModel):
    """A site to be upserted via upload."""
    name: str = Field(..., max_length=500)
    lat: float
    lon: float
    site_type: str | None = Field(default=None, max_length=100)
    period_name: str | None = Field(default=None, max_length=100)
    period_start: int | None = None
    country: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    source_url: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    existing_id: str | None = Field(default=None, max_length=100)  # If updating an existing site


class BatchUploadRequest(BaseModel):
    """Request body for batch upload."""
    sites: list[ParsedSitePayload]
    target_source: str


@router.post("/batch-upload")
async def batch_upload_sites(
    body: BatchUploadRequest,
    authorization: str | None = Header(None),
    x_admin_pin: str | None = Header(None, alias="X-Admin-Pin"),
    db: Session = Depends(get_db),
):
    """
    Upload sites in bulk — inserts new sites and updates existing ones.

    Creates a snapshot of all sites that will be updated before applying changes.
    """
    import uuid as _uuid

    from api.services.snapshots import create_snapshot

    edited_by = _verify_admin(authorization, x_admin_pin)

    sites = body.sites
    target_source = body.target_source

    if not sites:
        raise HTTPException(status_code=400, detail="No sites provided")
    if len(sites) > 5000:
        raise HTTPException(status_code=400, detail="Maximum 5000 sites per upload")

    # Separate inserts from updates
    update_ids = [s.existing_id for s in sites if s.existing_id]
    snapshot_id = None
    if update_ids:
        snapshot_id = create_snapshot(
            db, update_ids,
            created_by=edited_by,
            description=f"Upload to {target_source} ({len(sites)} rows, {len(update_ids)} updates)",
            snapshot_type="upload",
        )

    inserted = 0
    updated = 0
    errors = []

    for i, site in enumerate(sites):
        period_start = site.period_start
        if period_start is None and site.period_name:
            period_start = _period_to_year(site.period_name)

        if site.existing_id:
            # Update existing
            db.execute(
                text("""
                    UPDATE unified_sites SET
                        name = :name, lat = :lat, lon = :lon,
                        geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                        site_type = :site_type, period_name = :period_name,
                        period_start = :period_start, country = :country,
                        description = :description, source_url = :source_url,
                        thumbnail_url = :thumbnail_url,
                        edited_by = :edited_by, updated_at = NOW()
                    WHERE id::text = :site_id
                """),
                {
                    "site_id": site.existing_id,
                    "name": site.name, "lat": site.lat, "lon": site.lon,
                    "site_type": normalize_site_type(site.site_type) if site.site_type else None,
                    "period_name": site.period_name, "period_start": period_start,
                    "country": site.country, "description": site.description,
                    "source_url": site.source_url, "thumbnail_url": site.thumbnail_url,
                    "edited_by": edited_by,
                },
            )
            updated += 1
        else:
            # Insert new
            new_id = str(_uuid.uuid4())
            from pipeline.utils.text import normalize_name
            name_norm = normalize_name(site.name) if site.name else site.name
            record_id = f"upload-{new_id[:8]}"
            try:
                db.execute(
                    text("""
                        INSERT INTO unified_sites (
                            id, source_id, source_record_id, name, name_normalized,
                            lat, lon, geom, site_type, period_name, period_start,
                            country, description, source_url, thumbnail_url,
                            edited_by, created_at
                        ) VALUES (
                            :id, :source_id, :source_record_id, :name, :name_normalized,
                            :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                            :site_type, :period_name, :period_start,
                            :country, :description, :source_url, :thumbnail_url,
                            :edited_by, NOW()
                        )
                    """),
                    {
                        "id": new_id, "source_id": target_source,
                        "source_record_id": record_id,
                        "name": site.name, "name_normalized": name_norm,
                        "lat": site.lat, "lon": site.lon,
                        "site_type": normalize_site_type(site.site_type) if site.site_type else None,
                        "period_name": site.period_name, "period_start": period_start,
                        "country": site.country, "description": site.description,
                        "source_url": site.source_url, "thumbnail_url": site.thumbnail_url,
                        "edited_by": edited_by,
                    },
                )
                inserted += 1
            except Exception as e:
                logger.error(f"Batch upload row {i} ({site.name}): {e}")
                errors.append({"row": i, "name": site.name, "error": "Insert failed for this row"})

    db.commit()
    cache_delete_pattern("sites:*")

    global _static_sites_cache
    _static_sites_cache = None

    return {
        "snapshot_id": snapshot_id,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
    }
