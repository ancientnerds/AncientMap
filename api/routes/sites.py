"""
Sites API Routes - High Performance Spatial Queries.

Supports:
- Viewport filtering (bounding box)
- H3 clustering for zoom levels
- Source/type/period filtering
- Site updates, batch upload, and replace-source (admin)
- Static JSON fallback when database is empty
"""

import hashlib
import json
import logging
import random
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern, cache_get, cache_set
from api.services.jwt_auth import require_founder
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import DiscordUser, get_db
from pipeline.normalizers.site_type import normalize_site_type

_heavy_limiter = RateLimiter(max_requests=50, window_seconds=60, namespace="heavy_sites")

logger = logging.getLogger(__name__)
router = APIRouter()

# Paths to static sites JSON files (both need to be kept in sync)
STATIC_SITES_PATH = (
    Path(__file__).parent.parent.parent
    / "ancient-nerds-map"
    / "dist"
    / "data"
    / "sites"
    / "index.json"
)
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
        with open(path, encoding="utf-8") as f:
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
    return filtered[skip : skip + limit]


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
        "< 4500 BC": -5000,
        "4500 - 3000 BC": -3750,
        "3000 - 1500 BC": -2250,
        "1500 - 500 BC": -1000,
        "500 BC - 1 AD": -250,
        "1 - 500 AD": 250,
        "500 - 1000 AD": 750,
        "1000 - 1500 AD": 1250,
        "1500+ AD": 1750,
        "Unknown": None,
    }
    return period_years.get(period)


def _update_single_json_file(
    file_path: Path, site_id: str, site_update: "SiteUpdateRequest"
) -> bool:
    """Update a single static JSON file with the edited site data."""
    if not file_path.exists():
        logger.warning(f"Static sites file not found: {file_path}")
        return False

    try:
        # Load the JSON file
        with open(file_path, encoding="utf-8") as f:
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
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))  # Compact JSON
            return True
        else:
            logger.warning(f"Site {site_id} not found in {file_path.name}")
            return False

    except Exception as e:
        logger.error(f"Failed to update {file_path.name}: {e}")
        return False


def _update_static_json(site_id: str, site_update: "SiteUpdateRequest"):
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
    req: Request,
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
    if not _heavy_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests")
    # Check active pins
    from api.routes.snapshots import get_active_pins

    pins = get_active_pins(db)

    # Determine which requested sources are pinned vs live
    requested_sources = (
        set(source) if source else {"ancient_nerds", "lyra", "ancient_nerds_community"}
    )
    pinned_sources: dict[str, str] = {
        sid: pins[sid]  # type: ignore[misc]
        for sid in requested_sources
        if sid in pins and pins[sid] is not None
    }
    live_sources = [sid for sid in requested_sources if sid not in pinned_sources]

    # Include pin fingerprint in cache key so pinned vs unpinned don't collide
    pin_fp = (
        ",".join(f"{k}={v}" for k, v in sorted(pinned_sources.items()))
        if pinned_sources
        else "none"
    )
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
            conditions = ["us.source_id = ANY(:sources)"]
            params: dict[str, object] = {"limit": limit, "skip": skip, "sources": live_sources}

            if site_type:
                conditions.append("us.site_type = :site_type")
                params["site_type"] = site_type

            if period_max is not None:
                conditions.append("(us.period_start IS NULL OR us.period_start <= :period_max)")
                params["period_max"] = period_max

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    us.id::text,
                    us.name,
                    us.lat,
                    us.lon,
                    us.source_id,
                    us.site_type,
                    us.period_start,
                    us.period_name,
                    us.description,
                    us.thumbnail_url,
                    us.country,
                    us.source_url,
                    us.edited_by,
                    us.updated_at,
                    us.last_audited,
                    cs.card_description,
                    cs.confidence_score,
                    us.raw_data
                FROM unified_sites us
                LEFT JOIN card_stats cs ON cs.site_id = us.id
                WHERE {where_clause}
                OFFSET :skip
                LIMIT :limit
            """)

            result = db.execute(query, params)

            site_ids_list = []
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
                if row.card_description:
                    site["cd"] = row.card_description
                if row.confidence_score is not None:
                    site["cf"] = round(row.confidence_score, 2)
                if row.edited_by and row.edited_by != "initial":
                    site["eb"] = row.edited_by
                if row.updated_at:
                    site["ea"] = row.updated_at.isoformat()
                if row.last_audited:
                    site["aud"] = row.last_audited.isoformat()
                rd = row.raw_data
                if isinstance(rd, str):
                    try:
                        rd = json.loads(rd)
                    except (ValueError, TypeError):
                        rd = None
                if isinstance(rd, dict) and "description_citations" in rd:
                    site["dc"] = rd["description_citations"]
                all_sites.append(site)
                site_ids_list.append(row.id)

            # Batch-load reference links for all sites
            if site_ids_list:
                ref_result = db.execute(
                    text("""
                        SELECT site_id::text, content_url, title, link_metadata,
                               relevance_score
                        FROM site_content_links
                        WHERE content_type = 'reference'
                        AND content_url IS NOT NULL
                        ORDER BY site_id, relevance_score DESC
                    """)
                )
                refs_by_site: dict[str, list] = {}
                for rrow in ref_result:
                    sid = rrow.site_id
                    if sid not in refs_by_site:
                        refs_by_site[sid] = []
                    if len(refs_by_site[sid]) < 5:
                        meta = rrow.link_metadata or {}
                        refs_by_site[sid].append(
                            {
                                "u": rrow.content_url,
                                "t": (rrow.title or "")[:200],
                                "d": meta.get("domain", ""),
                                "k": meta.get("link_type", "article"),
                            }
                        )
                # Merge refs into site dicts
                if refs_by_site:
                    site_map = {s["id"]: s for s in all_sites}
                    for sid, refs in refs_by_site.items():
                        if sid in site_map:
                            site_map[sid]["rf"] = refs

        except Exception as e:
            logger.error(f"Database query failed for live sources: {e}", exc_info=True)
            # Do NOT silently fall back to static JSON — surface the error so
            # missing-column / query bugs are caught immediately instead of
            # serving stale data labelled as "postgres".
            raise HTTPException(
                status_code=500, detail="Database query failed for live sites"
            ) from e

    data_source = "snapshot"
    if live_sources:
        data_source = "postgres"

    if all_sites:
        response = {
            "count": len(all_sites),
            "sites": all_sites,
            "dataSource": data_source,
        }
        cache_set(cache_key, response, ttl=1800)
        return response

    # If no live sources were requested (all pinned) and no pinned sites found,
    # or if DB was empty — try static JSON as final fallback
    if not pinned_sources:
        static_sites = _load_static_sites()
        if static_sites:
            filtered = _filter_static_sites(
                static_sites, source, site_type, period_max, skip, limit
            )
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
    conditions = ["geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"]
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
        sites.append(
            {
                "id": row.id,
                "n": row.name,
                "la": row.lat,
                "lo": row.lon,
                "s": row.source_id,
                "t": row.site_type,
                "p": row.period_start,
            }
        )

    return {
        "count": len(sites),
        "sites": sites,
    }


@router.get("/clustered")
async def get_clustered_sites(
    req: Request,
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
    if not _heavy_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests")
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
        clusters.append(
            {
                "la": round(row.lat, 4),
                "lo": round(row.lon, 4),
                "c": row.count,
                "s": row.source_id,
            }
        )

    return {
        "resolution": resolution,
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


@router.get("/random")
async def random_sites(
    req: Request,
    limit: int = Query(50, ge=1, le=200, description="Number of random sites"),
    db: Session = Depends(get_db),
):
    """Return random sites proportionally sampled across all sources."""
    if not _heavy_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests")
    # Step 1: get per-source counts
    counts_result = db.execute(
        text("SELECT source_id, COUNT(*) AS cnt FROM unified_sites GROUP BY source_id")
    )
    source_counts = [(row.source_id, row.cnt) for row in counts_result]
    if not source_counts:
        return {"count": 0, "sites": []}

    total = sum(cnt for _, cnt in source_counts)
    min_per_source = 2

    # Step 2: allocate slots proportionally with a minimum per source
    allocations: dict[str, int] = {}
    for src, cnt in source_counts:
        share = max(min_per_source, round(cnt / total * limit))
        allocations[src] = share

    # Scale down if over budget
    alloc_total = sum(allocations.values())
    if alloc_total > limit:
        factor = limit / alloc_total
        allocations = {src: max(1, round(n * factor)) for src, n in allocations.items()}

    # Step 3: sample from each source
    all_sites = []
    for src, n in allocations.items():
        query = text("""
            SELECT us.id::text, us.name, us.lat, us.lon, us.source_id, us.site_type,
                   us.period_start, us.period_name, us.description, us.country, us.source_url,
                   cs.card_description
            FROM unified_sites us
            LEFT JOIN card_stats cs ON cs.site_id = us.id
            WHERE us.source_id = :src
            ORDER BY RANDOM()
            LIMIT :n
        """)
        result = db.execute(query, {"src": src, "n": n})
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
            if row.country:
                site["c"] = row.country
            if row.source_url:
                site["u"] = row.source_url
            if row.card_description:
                site["cd"] = row.card_description
            all_sites.append(site)

    # Shuffle the combined results so sources are interleaved
    random.shuffle(all_sites)
    all_sites = all_sites[:limit]

    return {"count": len(all_sites), "sites": all_sites}


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

    # Single query: exact > spaceless > substring, prefer rows with card_description
    query = text("""
        SELECT
            us.id::text, us.name, us.lat, us.lon, us.source_id, us.site_type,
            us.period_start, us.period_name, us.description, us.country, us.source_url,
            cs.card_description,
            CASE
                WHEN us.name_normalized = :norm THEN 1
                WHEN replace(us.name_normalized, ' ', '') = :spaceless THEN 2
                ELSE 3
            END AS rank
        FROM unified_sites us
        LEFT JOIN card_stats cs ON cs.site_id = us.id
        WHERE us.name_normalized = :norm
           OR replace(us.name_normalized, ' ', '') = :spaceless
           OR us.name_normalized ILIKE :pattern ESCAPE '\\'
           OR replace(us.name_normalized, ' ', '') ILIKE :spaceless_pattern ESCAPE '\\'
        ORDER BY (cs.card_description IS NULL), rank, us.name
        LIMIT :limit
    """)

    result = db.execute(
        query,
        {
            "norm": normalized,
            "spaceless": spaceless,
            "pattern": f"%{normalized_escaped}%",
            "spaceless_pattern": f"%{spaceless_escaped}%",
            "limit": limit,
        },
    )
    sites = []
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
        if row.country:
            site["c"] = row.country
        if row.source_url:
            site["u"] = row.source_url
        if row.card_description:
            site["cd"] = row.card_description
        sites.append(site)

    return {"count": len(sites), "sites": sites}


# =============================================================================
# Snapshot Endpoints (must be above /{site_id} catch-all to avoid shadowing)
# =============================================================================


@router.get("/snapshots")
async def get_snapshots(
    limit: int = Query(20, ge=1, le=100),
    source_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List recent database snapshots, optionally filtered by source."""
    from api.services.snapshots import list_snapshots

    return {"snapshots": list_snapshots(db, limit, source_id=source_id)}


@router.post("/snapshots/create")
async def create_manual_snapshot_endpoint(
    source_id: str = Query(...),
    description: str = Query("Manual snapshot"),
    _user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Create a manual snapshot of all sites in a source (founders only)."""
    from api.services.snapshots import create_manual_snapshot

    valid_sources = {"ancient_nerds", "lyra", "ancient_nerds_community"}
    if source_id not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_id. Must be one of: {', '.join(sorted(valid_sources))}",
        )

    result = create_manual_snapshot(
        db, source_id, created_by=_user.username, description=description
    )
    if not result["snapshot_id"]:
        raise HTTPException(status_code=404, detail=f"No sites found for source '{source_id}'")

    return result


@router.post("/snapshots/export")
async def export_file_snapshot_endpoint(
    _user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Create a file snapshot of the current DB state (founders only)."""
    from api.services.snapshots import export_file_snapshot

    snapshot_key = export_file_snapshot(db)
    return {"snapshot_key": snapshot_key}


@router.get("/snapshots/{snapshot_id}/preview")
async def preview_snapshot_endpoint(
    snapshot_id: str,
    db: Session = Depends(get_db),
):
    """Preview what restoring a snapshot would change (current vs old values)."""
    from api.services.snapshots import preview_snapshot

    result = preview_snapshot(db, snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return result


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot_endpoint(
    snapshot_id: str,
    _user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Restore all rows from a snapshot (founders only)."""
    from api.services.snapshots import restore_snapshot

    result = restore_snapshot(db, snapshot_id, restored_by=_user.username)
    if result["restored"] == 0:
        raise HTTPException(status_code=404, detail="Snapshot not found or empty")

    global _static_sites_cache
    _static_sites_cache = None

    return {
        "restored": result["restored"],
        "snapshot_id": snapshot_id,
        "undo_snapshot_id": result["undo_snapshot_id"],
    }


@router.get("/{site_id}/history")
async def get_site_edit_history(
    site_id: str,
    db: Session = Depends(get_db),
):
    """Get the edit history for a single site from snapshot records."""
    from api.services.snapshots import site_edit_history

    history = site_edit_history(db, site_id)
    return {"site_id": site_id, "history": history}


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

    result = db.execute(
        query,
        {
            "site_uuid": site_row.id,
            "lat": site_row.lat,
            "lon": site_row.lon,
        },
    )

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
            SELECT us.id::text, us.source_id, us.source_record_id, us.name, us.lat, us.lon,
                   us.site_type, us.period_start, us.period_end, us.period_name,
                   us.country, us.description, us.thumbnail_url, us.source_url, us.raw_data,
                   cs.card_description,
                   cs.best_wiki_url, cs.source_language
            FROM unified_sites us
            LEFT JOIN card_stats cs ON cs.site_id = us.id
            WHERE us.id::text = :site_id
        """)
        result = db.execute(query, {"site_id": site_id})
    else:
        query = text("""
            SELECT us.id::text, us.source_id, us.source_record_id, us.name, us.lat, us.lon,
                   us.site_type, us.period_start, us.period_end, us.period_name,
                   us.country, us.description, us.thumbnail_url, us.source_url, us.raw_data,
                   cs.card_description,
                   cs.best_wiki_url, cs.source_language
            FROM unified_sites us
            LEFT JOIN card_stats cs ON cs.site_id = us.id
            WHERE us.name ILIKE :name
               OR us.name_normalized = LOWER(:name)
               OR REPLACE(us.name_normalized, ' ', '') = LOWER(REPLACE(:name, ' ', ''))
               OR us.id IN (SELECT site_id FROM unified_site_names WHERE name ILIKE :name)
            LIMIT 1
        """)
        result = db.execute(query, {"name": site_id})

    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    resp = {
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
    }
    if row.card_description:
        resp["cardDescription"] = row.card_description
    if row.best_wiki_url:
        resp["bestWikiUrl"] = row.best_wiki_url
    if row.source_language:
        resp["sourceLanguage"] = row.source_language
    # Extract description_citations from raw_data
    rd = row.raw_data
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except (ValueError, TypeError):
            rd = None
    if isinstance(rd, dict):
        if "description_citations" in rd:
            resp["descriptionCitations"] = rd["description_citations"]
        resp["rawData"] = rd

    # Reference links from site_content_links (web-discovered sources)
    ref_rows = db.execute(
        text("""
            SELECT content_url, title, link_metadata
            FROM site_content_links
            WHERE site_id::text = :site_id
              AND content_type = 'reference'
              AND content_url IS NOT NULL
            ORDER BY relevance_score DESC
            LIMIT 5
        """),
        {"site_id": row.id},
    ).fetchall()
    if ref_rows:
        resp["referenceLinks"] = [
            {
                "url": r.content_url,
                "title": (r.title or "")[:200],
                "domain": (r.link_metadata or {}).get("domain", ""),
                "kind": (r.link_metadata or {}).get("link_type", "article"),
            }
            for r in ref_rows
        ]

    return resp


def _sync_to_radar(
    db: Session, site_id: str, site_update: "SiteUpdateRequest", lat: float, lon: float
) -> int:
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


@router.put("/{site_id}")
async def update_site(
    site_id: str,
    site_update: SiteUpdateRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Update a site's details (founders only).

    Updates name, description, location, coordinates, category, period, and source URL.
    """
    edited_by = user.username

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

    db.execute(
        update_query,
        {
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
        },
    )

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

    logger.info(
        f"Updated site {site_id}: {site_update.title} (DB + static JSON: {static_updated}, radar synced: {synced}, invalidated {deleted} cache entries)"
    )

    return {
        "success": True,
        "message": "Site updated successfully",
        "staticUpdated": static_updated,
        "radarSynced": synced,
    }


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
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Apply multiple site updates in a single transaction with snapshot (founders only).

    Creates a snapshot of all affected rows before applying changes.
    Syncs changes to radar (user_contributions) where applicable.
    """
    from api.services.snapshots import create_snapshot

    edited_by = user.username

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    if len(updates) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 updates per batch")

    site_ids = [u.id for u in updates]

    # Determine source_id from the edited sites (use first site's source)
    src_row = db.execute(
        text("SELECT source_id FROM unified_sites WHERE id::text = :sid LIMIT 1"),
        {"sid": site_ids[0]},
    ).fetchone()
    edit_source = src_row.source_id if src_row else None

    # Create snapshot before changes
    snapshot_id = create_snapshot(
        db,
        site_ids,
        created_by=edited_by,
        description=f"Edited {len(updates)} site{'s' if len(updates) != 1 else ''}",
        snapshot_type="edit",
        source_id=edit_source,
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
            title=update.title,
            category=update.category,
            period=update.period,
            description=update.description,
            sourceUrl=update.sourceUrl,
            coordinates=update.coordinates,
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
    card_description: str | None = Field(default=None, max_length=300)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    description_citations: list[dict] | None = None
    reference_links: list[dict] | None = None
    existing_id: str | None = Field(default=None, max_length=100)  # If updating an existing site


class BatchUploadRequest(BaseModel):
    """Request body for batch upload."""

    sites: list[ParsedSitePayload]
    target_source: str
    create_snapshot: bool = True


@router.post("/batch-upload")
async def batch_upload_sites(
    body: BatchUploadRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Upload sites in bulk — inserts new sites and updates existing ones (founders only).

    Creates a snapshot of all sites that will be updated before applying changes.
    """
    import uuid as _uuid

    from api.services.snapshots import create_snapshot

    edited_by = user.username

    sites = body.sites
    target_source = body.target_source

    if not sites:
        raise HTTPException(status_code=400, detail="No sites provided")

    # Separate inserts from updates
    update_ids = [s.existing_id for s in sites if s.existing_id]
    snapshot_id = None
    snapshot_error = None
    if update_ids and body.create_snapshot:
        try:
            snapshot_id = create_snapshot(
                db,
                update_ids,
                created_by=edited_by,
                description=f"Upload to {target_source} ({len(sites)} rows, {len(update_ids)} updates)",
                snapshot_type="upload",
                source_id=target_source,
            )
        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            snapshot_error = str(e)
            db.rollback()

    from pipeline.utils.text import normalize_name

    # Separate into update vs insert batches and build param lists
    update_params = []
    insert_params = []
    card_stats_params = []
    errors: list[dict] = []

    for site in sites:
        period_start = site.period_start
        if period_start is None and site.period_name:
            period_start = _period_to_year(site.period_name)

        site_type = normalize_site_type(site.site_type) if site.site_type else None

        if site.existing_id:
            update_params.append(
                {
                    "site_id": site.existing_id,
                    "name": site.name,
                    "lat": site.lat,
                    "lon": site.lon,
                    "site_type": site_type,
                    "period_name": site.period_name,
                    "period_start": period_start,
                    "country": site.country,
                    "description": site.description,
                    "source_url": site.source_url,
                    "thumbnail_url": site.thumbnail_url,
                    "edited_by": edited_by,
                }
            )
            if site.card_description or site.confidence_score is not None:
                card_stats_params.append(
                    {
                        "site_id": site.existing_id,
                        "card_description": site.card_description,
                        "confidence_score": site.confidence_score,
                    }
                )
        else:
            new_id = str(_uuid.uuid4())
            name_norm = normalize_name(site.name) if site.name else site.name
            record_id = f"upload-{new_id[:8]}"
            insert_params.append(
                {
                    "id": new_id,
                    "source_id": target_source,
                    "source_record_id": record_id,
                    "name": site.name,
                    "name_normalized": name_norm,
                    "lat": site.lat,
                    "lon": site.lon,
                    "site_type": site_type,
                    "period_name": site.period_name,
                    "period_start": period_start,
                    "country": site.country,
                    "description": site.description,
                    "source_url": site.source_url,
                    "thumbnail_url": site.thumbnail_url,
                    "edited_by": edited_by,
                }
            )
            if site.card_description or site.confidence_score is not None:
                card_stats_params.append(
                    {
                        "site_id": new_id,
                        "card_description": site.card_description,
                        "confidence_score": site.confidence_score,
                    }
                )

    # Batch UPDATE existing sites
    if update_params:
        db.execute(
            text("""
                UPDATE unified_sites SET
                    name = :name, lat = :lat, lon = :lon,
                    geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                    site_type = :site_type, period_name = :period_name,
                    period_start = :period_start, country = :country,
                    description = :description, source_url = :source_url,
                    thumbnail_url = :thumbnail_url,
                    edited_by = :edited_by, updated_at = NOW(), last_audited = NOW()
                WHERE id::text = :site_id
            """),
            update_params,
        )

    # Batch INSERT new sites
    if insert_params:
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
            insert_params,
        )

    # Batch UPSERT card_stats
    if card_stats_params:
        db.execute(
            text("""
                INSERT INTO card_stats (site_id, card_description, confidence_score,
                    antiquity, fortification, cultural_influence, mystery,
                    legacy, total_power, rarity_score, rarity_tier, category_group)
                VALUES (CAST(:site_id AS uuid), :card_description, :confidence_score,
                    0, 0, 0, 0, 0, 0, 0, 0, 'unknown')
                ON CONFLICT (site_id)
                DO UPDATE SET
                    card_description = COALESCE(EXCLUDED.card_description, card_stats.card_description),
                    confidence_score = COALESCE(EXCLUDED.confidence_score, card_stats.confidence_score)
            """),
            card_stats_params,
        )

    # Write description_citations into raw_data and reference_links into site_content_links
    citations_written = 0
    reflinks_written = 0
    reflinks_errors = 0

    # Batch citations: collect all params, execute once
    citation_params = []
    for site in sites:
        if not site.description_citations:
            continue
        sid = site.existing_id or next(
            (p["id"] for p in insert_params if p["name"] == site.name), None
        )
        if sid:
            citation_params.append({
                "site_id": sid,
                "citations": json.dumps(site.description_citations),
            })
    if citation_params:
        db.execute(
            text("""
                UPDATE unified_sites
                SET raw_data = COALESCE(raw_data, '{}'::jsonb)
                    || jsonb_build_object(
                        'description_citations', CAST(:citations AS jsonb)
                    )
                WHERE id::text = :site_id
            """),
            citation_params,
        )
        citations_written = len(citation_params)

    # Batch ref links: collect all params, execute once
    reflink_params = []
    for site in sites:
        if not site.reference_links:
            continue
        sid = site.existing_id or next(
            (p["id"] for p in insert_params if p["name"] == site.name), None
        )
        if not sid:
            continue
        for idx, link in enumerate(site.reference_links[:5]):
            url = link.get("url", "")
            domain = link.get("domain", "")
            if not url:
                continue
            quality = link.get("quality", "medium")
            base_score = 0.9 if quality == "high" else 0.7
            relevance = round(base_score - (idx * 0.05), 2)
            url_hash = hashlib.md5(
                url.encode(),
                usedforsecurity=False,
            ).hexdigest()[:8]
            reflink_params.append({
                "sid": sid,
                "cid": f"{domain}:{url_hash}",
                "title": (link.get("title") or "")[:500],
                "url": url,
                "score": relevance,
                "meta": json.dumps({
                    "domain": domain,
                    "link_type": link.get("link_type", "article"),
                }),
            })
        reflinks_written += 1
    if reflink_params:
        try:
            db.execute(
                text("""
                    INSERT INTO site_content_links
                        (site_id, content_type, content_source,
                         content_id, title, content_url,
                         relevance_score, link_metadata)
                    VALUES
                        (CAST(:sid AS uuid), 'reference',
                         'web_discovery', :cid, :title,
                         :url, :score,
                         CAST(:meta AS jsonb))
                    ON CONFLICT (site_id, content_source, content_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content_url = EXCLUDED.content_url,
                        relevance_score = EXCLUDED.relevance_score,
                        link_metadata = EXCLUDED.link_metadata
                """),
                reflink_params,
            )
        except Exception as e:
            logger.warning("Batch ref link insert failed: %s", e)
            reflinks_errors = len(reflink_params)

    inserted = len(insert_params)
    updated = len(update_params)

    db.commit()
    cache_delete_pattern("sites:*")

    global _static_sites_cache
    _static_sites_cache = None

    result = {
        "snapshot_id": snapshot_id,
        "inserted": inserted,
        "updated": updated,
        "citations_written": citations_written,
        "reflinks_written": reflinks_written,
        "reflinks_errors": reflinks_errors,
        "errors": errors,
    }
    if snapshot_error:
        result["snapshot_error"] = snapshot_error
    return result


class ReplaceSourceRequest(BaseModel):
    """Request body for replace-source (snapshot + wipe + insert)."""

    sites: list[ParsedSitePayload]
    target_source: str


@router.post("/replace-source")
async def replace_source(
    body: ReplaceSourceRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Replace all sites for a source: snapshot current state, delete, insert fresh.

    Safety guarantees:
    - Snapshot is committed FIRST in its own transaction. If it fails, nothing is deleted.
    - Delete + insert happen in a second transaction. If insert fails, delete is rolled back.
    - Protected sources (community, lyra) cannot be replaced.
    - Verifies snapshot row count matches existing site count before proceeding.
    """
    import uuid as _uuid

    from api.services.snapshots import create_snapshot
    from pipeline.utils.text import normalize_name

    edited_by = user.username
    target_source = body.target_source
    sites = body.sites

    if not sites:
        raise HTTPException(status_code=400, detail="No sites provided")

    # Guard: never wipe protected sources
    protected = {"community", "lyra", "ancient_nerds_community"}
    if target_source in protected:
        raise HTTPException(
            status_code=400,
            detail=f"Source '{target_source}' is protected and cannot be replaced",
        )

    # ── PHASE 1: Snapshot (committed independently) ──────────────────
    existing_ids = [
        r.id
        for r in db.execute(
            text("SELECT id::text AS id FROM unified_sites WHERE source_id = :src"),
            {"src": target_source},
        ).fetchall()
    ]

    snapshot_id = None
    if existing_ids:
        # Create snapshot and commit it immediately so it persists
        # even if the subsequent delete/insert fails
        try:
            snapshot_id = create_snapshot(
                db,
                site_ids=existing_ids,
                created_by=edited_by,
                description=(
                    f"Before replace-source {target_source}"
                    f" ({len(existing_ids)} old → {len(sites)} new)"
                ),
                snapshot_type="upload",
                source_id=target_source,
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Snapshot creation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Snapshot creation failed — database NOT modified: {e}",
            ) from None

        # Verify snapshot was actually persisted with correct row count
        verify = db.execute(
            text("SELECT row_count FROM db_snapshots WHERE id::text = :sid"),
            {"sid": snapshot_id},
        ).fetchone()
        if not verify or verify.row_count != len(existing_ids):
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Snapshot verification failed — expected {len(existing_ids)}"
                    f" rows, got {verify.row_count if verify else 0}."
                    " Database NOT modified."
                ),
            )

    # ── PHASE 2: Delete + Insert (single transaction) ────────────────
    # If anything in this phase fails, the entire thing rolls back
    # and the snapshot from phase 1 remains for manual recovery.
    try:
        # Extend timeout — bulk delete with FK checks is slow
        db.execute(text("SET LOCAL statement_timeout = '300s'"))

        if existing_ids:
            src_filter = "SELECT id FROM unified_sites WHERE source_id = :src"
            # CASCADE tables: delete explicitly to avoid slow cascades
            for tbl in (
                "site_content_links",
                "card_stats",
                "unified_site_names",
                "wiki_images",
            ):
                db.execute(
                    text(
                        f"DELETE FROM {tbl}"  # noqa: S608
                        f" WHERE site_id IN ({src_filter})"
                    ),
                    {"src": target_source},
                )
            # SET NULL tables: null out FK references
            db.execute(
                text(
                    "UPDATE unified_sites SET parent_site_id = NULL"
                    f" WHERE parent_site_id IN ({src_filter})"
                ),
                {"src": target_source},
            )
            for tbl in (
                "news_items",
                "site_likes",
                "site_bookmarks",
            ):
                db.execute(
                    text(
                        f"UPDATE {tbl} SET site_id = NULL"  # noqa: S608
                        f" WHERE site_id IN ({src_filter})"
                    ),
                    {"src": target_source},
                )
            # user_contributions uses promoted_site_id, not site_id
            db.execute(
                text(
                    "UPDATE user_contributions SET promoted_site_id = NULL"
                    f" WHERE promoted_site_id IN ({src_filter})"
                ),
                {"src": target_source},
            )
            # Now delete the sites themselves — no FK checks needed
            deleted = db.execute(
                text("DELETE FROM unified_sites WHERE source_id = :src"),
                {"src": target_source},
            ).rowcount

            if deleted != len(existing_ids):
                logger.warning(
                    "Delete count mismatch: expected %d, got %d",
                    len(existing_ids),
                    deleted,
                )

        # Build insert params
        insert_params = []
        card_params = []
        for site in sites:
            site_id = site.existing_id or str(_uuid.uuid4())
            period_start = site.period_start
            if period_start is None and site.period_name:
                period_start = _period_to_year(site.period_name)
            site_type = normalize_site_type(site.site_type) if site.site_type else None
            name_norm = normalize_name(site.name) if site.name else site.name
            record_id = f"upload-{site_id[:8]}"

            insert_params.append(
                {
                    "id": site_id,
                    "source_id": target_source,
                    "source_record_id": record_id,
                    "name": site.name,
                    "name_normalized": name_norm,
                    "lat": site.lat,
                    "lon": site.lon,
                    "site_type": site_type,
                    "period_name": site.period_name,
                    "period_start": period_start,
                    "country": site.country,
                    "description": site.description,
                    "source_url": site.source_url,
                    "thumbnail_url": site.thumbnail_url,
                    "edited_by": edited_by,
                }
            )

            if site.card_description or site.confidence_score is not None:
                card_params.append(
                    {
                        "site_id": site_id,
                        "card_description": site.card_description,
                        "confidence_score": site.confidence_score,
                    }
                )

        # Batch INSERT sites
        if insert_params:
            db.execute(
                text("""
                    INSERT INTO unified_sites (
                        id, source_id, source_record_id,
                        name, name_normalized,
                        lat, lon, geom,
                        site_type, period_name, period_start,
                        country, description, source_url,
                        thumbnail_url, edited_by, created_at
                    ) VALUES (
                        CAST(:id AS uuid), :source_id,
                        :source_record_id, :name, :name_normalized,
                        :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                        :site_type, :period_name, :period_start,
                        :country, :description, :source_url,
                        :thumbnail_url, :edited_by, NOW()
                    )
                """),
                insert_params,
            )

        # Batch INSERT card_stats
        if card_params:
            db.execute(
                text("""
                    INSERT INTO card_stats (
                        site_id, card_description, confidence_score,
                        antiquity, fortification, cultural_influence,
                        mystery, legacy, total_power,
                        rarity_score, rarity_tier, category_group
                    ) VALUES (
                        CAST(:site_id AS uuid), :card_description,
                        :confidence_score,
                        0, 0, 0, 0, 0, 0, 0, 0, 'unknown'
                    )
                """),
                card_params,
            )

        # Write enrichment data (citations + ref links) — batched
        citations_written = 0
        reflinks_written = 0

        # Batch citations
        citation_params = []
        for site in sites:
            if not site.description_citations:
                continue
            enrich_id = site.existing_id or next(
                (p["id"] for p in insert_params if p["name"] == site.name),
                None,
            )
            if enrich_id:
                citation_params.append({
                    "site_id": enrich_id,
                    "citations": json.dumps(site.description_citations),
                })
        if citation_params:
            db.execute(
                text("""
                    UPDATE unified_sites
                    SET raw_data = COALESCE(raw_data, '{}'::jsonb)
                        || jsonb_build_object(
                            'description_citations', CAST(:citations AS jsonb)
                        )
                    WHERE id::text = :site_id
                """),
                citation_params,
            )
            citations_written = len(citation_params)

        # Batch ref links
        reflink_params = []
        for site in sites:
            if not site.reference_links:
                continue
            enrich_id = site.existing_id or next(
                (p["id"] for p in insert_params if p["name"] == site.name),
                None,
            )
            if not enrich_id:
                continue
            for idx, link in enumerate(site.reference_links[:5]):
                url = link.get("url", "")
                domain = link.get("domain", "")
                if not url:
                    continue
                url_hash = hashlib.md5(
                    url.encode(),
                    usedforsecurity=False,
                ).hexdigest()[:8]
                quality = link.get("quality", "medium")
                base_score = 0.9 if quality == "high" else 0.7
                relevance = round(base_score - (idx * 0.05), 2)
                reflink_params.append({
                    "sid": enrich_id,
                    "cid": f"{domain}:{url_hash}",
                    "title": (link.get("title") or "")[:500],
                    "url": url,
                    "score": relevance,
                    "meta": json.dumps({
                        "domain": domain,
                        "link_type": link.get("link_type", "article"),
                    }),
                })
            reflinks_written += 1
        if reflink_params:
            db.execute(
                text("""
                    INSERT INTO site_content_links
                        (site_id, content_type, content_source,
                         content_id, title, content_url,
                         relevance_score, link_metadata)
                    VALUES
                        (CAST(:sid AS uuid), 'reference',
                         'web_discovery', :cid, :title,
                         :url, :score,
                         CAST(:meta AS jsonb))
                """),
                reflink_params,
            )

        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Replace-source failed after snapshot: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Replace failed — all changes rolled back."
                f" Snapshot {snapshot_id} preserved for recovery."
                f" Error: {e}"
            ),
        ) from None

    cache_delete_pattern("sites:*")

    global _static_sites_cache
    _static_sites_cache = None

    return {
        "snapshot_id": snapshot_id,
        "deleted": len(existing_ids),
        "inserted": len(insert_params),
        "citations_written": citations_written,
        "reflinks_written": reflinks_written,
    }


# =============================================================================
# Delete Site Endpoint
# =============================================================================


@router.delete("/{site_id}")
async def delete_site(
    site_id: str,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Delete a site and its card_stats row (founders only)."""
    # Verify site exists
    row = db.execute(
        text("SELECT id, name FROM unified_sites WHERE id::text = :site_id"),
        {"site_id": site_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")

    db.execute(text("DELETE FROM card_stats WHERE site_id::text = :site_id"), {"site_id": site_id})
    db.execute(text("DELETE FROM unified_sites WHERE id::text = :site_id"), {"site_id": site_id})
    db.commit()

    cache_delete_pattern("sites:*")
    global _static_sites_cache
    _static_sites_cache = None

    return {"deleted": True, "site_id": site_id, "name": row.name}


# =============================================================================
# Mark Audited Endpoint
# =============================================================================


class MarkAuditedRequest(BaseModel):
    """Mark all sites in a source as audited."""

    source_id: str = Field(..., max_length=50)


@router.post("/mark-audited")
async def mark_sites_audited(
    body: MarkAuditedRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Stamp last_audited = NOW() on all sites in a source (founders only).

    Used after an audit pass to record that all sites have been reviewed,
    even if only a few needed actual changes.
    """
    result = db.execute(
        text("UPDATE unified_sites SET last_audited = NOW() WHERE source_id = :source_id"),
        {"source_id": body.source_id},
    )
    db.commit()

    return {
        "source_id": body.source_id,
        "marked": result.rowcount,
    }


# =============================================================================
# Reference Links Import
# =============================================================================


@router.post("/reference-links/import")
async def import_reference_links(
    request: Request,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """
    Bulk import reference links into site_content_links (founders only).

    Accepts JSON array of {site_id, content_type, content_source, content_id,
    title, content_url, relevance_score, link_metadata, thumbnail_url}.
    Dedupes by (site_id, content_source, content_id) on conflict.
    """
    body = await request.json()
    if not isinstance(body, list):
        raise HTTPException(status_code=400, detail="Expected JSON array")

    inserted = 0
    skipped = 0
    for link in body:
        site_id = link.get("site_id")
        content_url = link.get("content_url")
        if not site_id or not content_url:
            skipped += 1
            continue

        metadata = link.get("link_metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        try:
            db.execute(
                text("""
                    INSERT INTO site_content_links
                        (site_id, content_type, content_source, content_id,
                         title, content_url, relevance_score,
                         link_metadata, thumbnail_url)
                    VALUES
                        (CAST(:site_id AS uuid), :content_type,
                         :content_source, :content_id,
                         :title, :content_url, :relevance_score,
                         CAST(:metadata AS jsonb), :thumbnail_url)
                    ON CONFLICT (site_id, content_source, content_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content_url = EXCLUDED.content_url,
                        relevance_score = EXCLUDED.relevance_score,
                        link_metadata = EXCLUDED.link_metadata
                """),
                {
                    "site_id": site_id,
                    "content_type": link.get("content_type", "reference"),
                    "content_source": link.get("content_source", "web_discovery"),
                    "content_id": link.get("content_id", ""),
                    "title": (link.get("title") or "")[:500],
                    "content_url": content_url,
                    "relevance_score": link.get("relevance_score"),
                    "metadata": json.dumps(metadata),
                    "thumbnail_url": link.get("thumbnail_url"),
                },
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert ref link for {site_id}: {e}")
            skipped += 1
            db.rollback()

    db.commit()
    return {"inserted": inserted, "skipped": skipped}
