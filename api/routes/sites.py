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
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern, cache_get, cache_set
from pipeline.database import get_db

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
    title: str
    location: str | None = None
    category: str
    period: str
    description: str | None = None
    sourceUrl: str | None = None
    coordinates: list[float]  # [lng, lat]


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




@router.get("/all")
async def get_all_sites(
    db: Session = Depends(get_db),
    source: list[str] | None = Query(None, description="Filter by source IDs"),
    site_type: str | None = Query(None, description="Filter by site type"),
    period_max: int | None = Query(None, description="Max period year"),
    skip: int = Query(0, ge=0, description="Number of records to skip (pagination)"),
    limit: int = Query(50000, ge=1, le=1000000, description="Max results (capped at 1M)"),
):
    """
    Get all sites as compact JSON for globe rendering.

    Returns minimal data for fast transfer:
    - id, name, lat, lon, source_id, site_type, period_start

    Falls back to static JSON if database is empty.
    """
    time.time()

    # Build cache key from parameters
    source_key = ",".join(sorted(source)) if source else "all"
    cache_key = f"sites:all:{source_key}:{site_type or 'all'}:{period_max or 'all'}:{skip}:{limit}"

    # Try cache first (30 min TTL)
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Try database first
    try:
        # Build query with filters
        conditions = []
        params = {"limit": limit, "skip": skip}

        if source:
            conditions.append("source_id = ANY(:sources)")
            params["sources"] = source

        if site_type:
            conditions.append("site_type = :site_type")
            params["site_type"] = site_type

        if period_max:
            conditions.append("(period_start IS NULL OR period_start <= :period_max)")
            params["period_max"] = period_max

        where_clause = " AND ".join(conditions) if conditions else "1=1"

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
                source_url
            FROM unified_sites
            WHERE {where_clause}
            OFFSET :skip
            LIMIT :limit
        """)

        query_start = time.time()
        result = db.execute(query, params)
        (time.time() - query_start) * 1000

        # Return as compact array of arrays for minimal JSON size
        serialize_start = time.time()
        sites = []
        images_found = 0
        for row in result:
            site = {
                "id": row.id,
                "n": row.name,  # Short keys for smaller JSON
                "la": row.lat,
                "lo": row.lon,
                "s": row.source_id,
                "t": row.site_type,
                "p": row.period_start,
            }
            # Only include optional fields if present (saves bandwidth)
            if row.period_name:
                site["pn"] = row.period_name
            if row.description:
                site["d"] = row.description
            if row.thumbnail_url:
                site["i"] = row.thumbnail_url
                images_found += 1
            if row.country:
                site["c"] = row.country
            if row.source_url:
                site["u"] = row.source_url
            sites.append(site)
        (time.time() - serialize_start) * 1000

        if sites:
            response = {
                "count": len(sites),
                "sites": sites,
                "dataSource": "postgres",
            }
            # Cache for 30 minutes
            cache_set(cache_key, response, ttl=1800)
            return response

        logger.info("Database returned no sites, falling back to static JSON")
    except Exception as e:
        logger.warning(f"Database query failed, falling back to static files: {e}")

    # Fall back to static JSON
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

    # No data available
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
    limit: int = Query(10000, le=50000),
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
    params = {
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


@router.get("/{site_id}")
async def get_site_detail(
    site_id: str,
    db: Session = Depends(get_db),
):
    """Get full details for a single site."""
    query = text("""
        SELECT
            id::text,
            source_id,
            source_record_id,
            name,
            lat,
            lon,
            site_type,
            period_start,
            period_end,
            period_name,
            country,
            description,
            thumbnail_url,
            source_url,
            raw_data
        FROM unified_sites
        WHERE id::text = :site_id
    """)

    result = db.execute(query, {"site_id": site_id})
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


@router.put("/{site_id}")
async def update_site(
    site_id: str,
    site_update: SiteUpdateRequest,
    authorization: str | None = Header(None, description="Bearer token for admin authentication"),
    db: Session = Depends(get_db),
):
    """
    Update a site's details (admin only).

    Updates name, description, location, coordinates, category, period, and source URL.
    Requires admin key for authentication via Authorization: Bearer header.
    Set admin key via ADMIN_KEY environment variable.
    """
    # Verify admin key from Authorization header
    admin_key = _extract_bearer_token(authorization)
    configured_admin_key = os.getenv("ADMIN_KEY", "")
    if not configured_admin_key:
        logger.warning("ADMIN_KEY not configured - site update endpoint disabled")
        raise HTTPException(status_code=503, detail="Admin access not configured")

    if not secrets.compare_digest(admin_key, configured_admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

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
            source_url = :source_url
        WHERE id::text = :site_id
    """)

    db.execute(update_query, {
        "site_id": site_id,
        "name": site_update.title,
        "description": site_update.description,
        "lat": lat,
        "lon": lon,
        "site_type": site_update.category,
        "period_name": site_update.period,
        "period_start": period_start,
        "source_url": site_update.sourceUrl,
    })
    db.commit()

    # Also update static JSON file so both sources stay in sync
    static_updated = _update_static_json(site_id, site_update)

    # Invalidate all sites caches to ensure fresh data on next request
    deleted = cache_delete_pattern("sites:*")

    # Clear the static sites cache so it reloads from file
    global _static_sites_cache
    _static_sites_cache = None

    logger.info(f"Updated site {site_id}: {site_update.title} (DB + static JSON: {static_updated}, invalidated {deleted} cache entries)")

    return {"success": True, "message": "Site updated successfully", "staticUpdated": static_updated}
