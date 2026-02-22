"""
Public API v1 — Curated endpoints for external developers.

Mounted as a sub-application at /api/v1 with its own OpenAPI docs:
  - /api/v1/docs   — Swagger UI
  - /api/v1/redoc  — ReDoc

All endpoints are rate-limited to 10 requests per minute per IP.
"""

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set
from api.schemas.public_v1 import (
    ChannelPublic,
    FacetSource,
    FacetsResponse,
    NewsFeedPublicResponse,
    NewsItemPublic,
    NewsSiteRef,
    NewsVideoPublic,
    SiteDetailResponse,
    SiteResult,
    SiteSearchResponse,
    SourcePublic,
    SourcesResponse,
    StatsResponse,
)
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import get_db

logger = logging.getLogger(__name__)

_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="public_v1")

RATE_LIMIT = 10


async def rate_limit_dependency(request: Request, response: Response):
    """FastAPI dependency that enforces rate limiting and sets response headers."""
    ip = get_client_ip(request)
    allowed, remaining, reset_seconds = _limiter.check_with_info(ip)

    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_seconds)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Max 10 requests per minute.",
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
                "Retry-After": str(reset_seconds),
            },
        )


# Default source colors (same as internal sources router)
_SOURCE_COLORS = {
    "ancient_nerds": "#FFD700", "lyra": "#8b5cf6", "ancient_nerds_community": "#22c55e",
    "pleiades": "#e74c3c", "dare": "#6c5ce7", "topostext": "#00bcd4",
    "unesco": "#ffd700", "wikidata": "#9966ff", "osm_historic": "#ff9800",
    "historic_england": "#c0392b", "ireland_nms": "#ff6699", "arachne": "#8e44ad",
    "megalithic_portal": "#9966cc", "sacred_sites": "#ff69b4", "rock_art": "#e67e22",
    "inscriptions_edh": "#5dade2", "coins_nomisma": "#d4af37",
    "shipwrecks_oxrep": "#0066ff", "volcanic_holvol": "#ff0000",
    "eamena": "#d35400", "open_context": "#2980b9",
    "default": "#ff00ff",
}


def create_public_api() -> FastAPI:
    """Create the public API v1 sub-application with its own OpenAPI docs."""

    public_app = FastAPI(
        title="Ancient Nerds Map — Public API",
        description=(
            "Access archaeological site data from 750K+ sites worldwide.\n\n"
            "All endpoints are rate-limited to **10 requests per minute** per IP address.\n\n"
            "Data is sourced from Pleiades, DARE, UNESCO, OpenStreetMap, Wikidata, "
            "and other open archaeological databases."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: allow all origins, GET-only for public read access
    public_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    public_app.add_middleware(GZipMiddleware, minimum_size=500)

    @public_app.exception_handler(Exception)
    async def public_error_handler(request: Request, exc: Exception):
        logger.error(f"Public API error on {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # =========================================================================
    # 1. GET /sites.geojson — GeoJSON FeatureCollection
    # =========================================================================

    @public_app.get(
        "/sites.geojson",
        summary="Get sites as GeoJSON",
        description=(
            "Returns archaeological sites as a GeoJSON FeatureCollection (RFC 7946).\n\n"
            "Supports filtering by source, country, period, type, and bounding box."
        ),
        tags=["Sites"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def get_sites_geojson(
        response: Response,
        db: Session = Depends(get_db),
        source: list[str] | None = Query(None, description="Filter by source IDs"),
        country: str | None = Query(None, description="Filter by country name"),
        period: int | None = Query(None, description="Max period_start year"),
        type: str | None = Query(None, alias="type", description="Filter by site_type"),
        bbox: str | None = Query(None, description="Bounding box: minlon,minlat,maxlon,maxlat"),
        limit: int = Query(10000, ge=1, le=50000, description="Max features returned"),
    ):
        parts = [
            "pubv1:geojson",
            ",".join(sorted(source)) if source else "_",
            country or "_",
            str(period) if period is not None else "_",
            type or "_",
            bbox or "_",
            str(limit),
        ]
        cache_key = ":".join(parts)
        cached = cache_get(cache_key)
        if cached:
            return cached

        bbox_parsed = None
        if bbox:
            try:
                coords = [float(c) for c in bbox.split(",")]
                if len(coords) != 4:
                    raise ValueError
                bbox_parsed = {"minlon": coords[0], "minlat": coords[1], "maxlon": coords[2], "maxlat": coords[3]}
            except (ValueError, IndexError):
                raise HTTPException(status_code=400, detail="Invalid bbox format. Expected: minlon,minlat,maxlon,maxlat") from None

        conditions = []
        params: dict = {"limit": limit}
        if source:
            conditions.append("source_id = ANY(:sources)")
            params["sources"] = source
        if country:
            conditions.append("country ILIKE :country")
            params["country"] = country
        if period is not None:
            conditions.append("(period_start IS NULL OR period_start <= :period)")
            params["period"] = period
        if type:
            conditions.append("site_type = :site_type")
            params["site_type"] = type
        if bbox_parsed:
            conditions.append("geom && ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)")
            params.update(bbox_parsed)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = text(f"""
            SELECT id::text, name, lat, lon, source_id, site_type,
                   period_start, period_name, country, description,
                   source_url, thumbnail_url
            FROM unified_sites
            WHERE {where_clause}
            LIMIT :limit
        """)
        result = db.execute(query, params)

        features = []
        for row in result:
            properties = {"id": row.id, "name": row.name, "source_id": row.source_id}
            if row.site_type:
                properties["site_type"] = row.site_type
            if row.period_start is not None:
                properties["period_start"] = row.period_start
            if row.period_name:
                properties["period_name"] = row.period_name
            if row.country:
                properties["country"] = row.country
            if row.description:
                properties["description"] = row.description
            if row.source_url:
                properties["source_url"] = row.source_url
            if row.thumbnail_url:
                properties["thumbnail_url"] = row.thumbnail_url

            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row.lon, row.lat]},
                "properties": properties,
            })

        geojson = {
            "type": "FeatureCollection",
            "metadata": {"api": "v1", "count": len(features), "limit": limit},
            "features": features,
        }
        cache_set(cache_key, geojson, ttl=300)
        return geojson

    # =========================================================================
    # 2. GET /sites/search — Full-text site search
    # =========================================================================

    @public_app.get(
        "/sites/search",
        summary="Search for archaeological sites",
        description=(
            "Search sites by name. Matches are case-insensitive and ignore spaces/diacritics.\n\n"
            "Returns up to 50 results sorted by relevance (exact matches first)."
        ),
        response_model=SiteSearchResponse,
        tags=["Sites"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def search_sites(
        q: str = Query(..., min_length=2, max_length=200, description="Search query"),
        limit: int = Query(50, ge=1, le=200, description="Max results"),
        db: Session = Depends(get_db),
    ):
        cache_key = f"pubv1:search:{q.lower().strip()}:{limit}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        # Spaceless matching: compare with spaces/diacritics stripped
        query = text("""
            SELECT id::text, name, lat, lon, source_id, site_type,
                   period_start, period_name, country
            FROM unified_sites
            WHERE name ILIKE :pattern
            ORDER BY
                CASE WHEN LOWER(name) = LOWER(:exact) THEN 0 ELSE 1 END,
                LENGTH(name),
                name
            LIMIT :limit
        """)
        result = db.execute(query, {
            "pattern": f"%{q.strip()}%",
            "exact": q.strip(),
            "limit": limit,
        })

        results = [
            SiteResult(
                id=row.id,
                name=row.name,
                latitude=row.lat,
                longitude=row.lon,
                source_id=row.source_id,
                site_type=row.site_type,
                period_start=row.period_start,
                period_name=row.period_name,
                country=row.country,
            )
            for row in result
        ]

        response = SiteSearchResponse(count=len(results), results=results)
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    # =========================================================================
    # 3. GET /sites/{site_id} — Single site detail
    # =========================================================================

    @public_app.get(
        "/sites/{site_id}",
        summary="Get site details",
        description="Get full details for a single archaeological site by UUID.",
        response_model=SiteDetailResponse,
        tags=["Sites"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={
            404: {"description": "Site not found"},
            429: {"description": "Rate limit exceeded"},
        },
    )
    async def get_site_detail(
        site_id: str,
        db: Session = Depends(get_db),
    ):
        cache_key = f"pubv1:site:{site_id}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        query = text("""
            SELECT id::text, name, lat, lon, source_id, site_type,
                   period_start, period_end, period_name, country,
                   description, source_url, thumbnail_url
            FROM unified_sites
            WHERE id::text = :site_id
            LIMIT 1
        """)
        row = db.execute(query, {"site_id": site_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Site not found")

        response = SiteDetailResponse(
            id=row.id,
            name=row.name,
            latitude=row.lat,
            longitude=row.lon,
            source_id=row.source_id,
            site_type=row.site_type,
            period_start=row.period_start,
            period_end=row.period_end,
            period_name=row.period_name,
            country=row.country,
            description=row.description,
            source_url=row.source_url,
            thumbnail_url=row.thumbnail_url,
        )
        cache_set(cache_key, response.model_dump(), ttl=600)
        return response

    # =========================================================================
    # 4. GET /sources — List data sources
    # =========================================================================

    @public_app.get(
        "/sources",
        summary="List data sources",
        description="List all data sources with site counts and display colors.",
        response_model=SourcesResponse,
        tags=["Sources"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def list_sources(db: Session = Depends(get_db)):
        cache_key = "pubv1:sources"
        cached = cache_get(cache_key)
        if cached:
            return cached

        query = text("""
            SELECT
                sm.id as source_id,
                sm.name,
                COALESCE(site_counts.count, 0) as site_count,
                COALESCE(sm.color, :default_color) as color,
                sm.category,
                sm.description
            FROM source_meta sm
            LEFT JOIN (
                SELECT source_id, COUNT(*) as count
                FROM unified_sites
                GROUP BY source_id
            ) site_counts ON sm.id = site_counts.source_id
            WHERE sm.enabled = true
            ORDER BY COALESCE(site_counts.count, 0) DESC
        """)
        result = db.execute(query, {"default_color": _SOURCE_COLORS["default"]})

        sources = [
            SourcePublic(
                id=row.source_id,
                name=row.name or row.source_id.replace("_", " ").title(),
                site_count=row.site_count,
                color=row.color or _SOURCE_COLORS.get(row.source_id, _SOURCE_COLORS["default"]),
                category=row.category,
                description=row.description,
            )
            for row in result
        ]

        response = SourcesResponse(count=len(sources), sources=sources)
        cache_set(cache_key, response.model_dump(), ttl=600)
        return response

    # =========================================================================
    # 5. GET /news — Paginated news feed
    # =========================================================================

    @public_app.get(
        "/news",
        summary="Get archaeological news",
        description=(
            "Paginated news feed from the Lyra archaeological news pipeline.\n\n"
            "Each item links to a YouTube video and optionally to an archaeological site on the map."
        ),
        response_model=NewsFeedPublicResponse,
        tags=["News"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def get_news(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=50, description="Items per page"),
        db: Session = Depends(get_db),
    ):
        cache_key = f"pubv1:news:{page}:{page_size}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        offset = (page - 1) * page_size

        # Total count of published items
        count_result = db.execute(text(
            "SELECT COUNT(*) FROM news_items WHERE post_text IS NOT NULL"
        ))
        total_count = count_result.scalar()

        query = text("""
            SELECT
                ni.id,
                ni.headline,
                ni.summary,
                ni.timestamp_seconds,
                ni.created_at,
                nv.id as video_id,
                nv.title as video_title,
                nv.published_at as video_published_at,
                nv.thumbnail_url as video_thumbnail,
                nc.name as channel_name,
                us.id::text as site_id,
                us.name as site_name,
                us.lat as site_lat,
                us.lon as site_lon
            FROM news_items ni
            JOIN news_videos nv ON ni.video_id = nv.id
            JOIN news_channels nc ON nv.channel_id = nc.id
            LEFT JOIN unified_sites us ON ni.site_id = us.id
            WHERE ni.post_text IS NOT NULL
            ORDER BY nv.published_at DESC, ni.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        result = db.execute(query, {"limit": page_size, "offset": offset})

        items = []
        for row in result:
            youtube_url = f"https://www.youtube.com/watch?v={row.video_id}"
            youtube_deep_url = None
            if row.timestamp_seconds:
                youtube_deep_url = f"https://www.youtube.com/watch?v={row.video_id}&t={row.timestamp_seconds}s"

            site_ref = None
            if row.site_id:
                site_ref = NewsSiteRef(
                    id=row.site_id,
                    name=row.site_name,
                    latitude=row.site_lat,
                    longitude=row.site_lon,
                )

            items.append(NewsItemPublic(
                id=row.id,
                headline=row.headline,
                summary=row.summary,
                youtube_url=youtube_url,
                youtube_deep_url=youtube_deep_url,
                video=NewsVideoPublic(
                    id=row.video_id,
                    title=row.video_title,
                    channel_name=row.channel_name,
                    published_at=row.video_published_at.isoformat() if row.video_published_at else "",
                    thumbnail_url=row.video_thumbnail,
                ),
                site=site_ref,
                created_at=row.created_at.isoformat() if row.created_at else "",
            ))

        response = NewsFeedPublicResponse(
            items=items,
            total_count=total_count,
            page=page,
            has_more=(offset + page_size) < total_count,
        )
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    # =========================================================================
    # 6. GET /news/channels — List YouTube channels
    # =========================================================================

    @public_app.get(
        "/news/channels",
        summary="List news channels",
        description="List all enabled YouTube channels tracked by the news pipeline.",
        response_model=list[ChannelPublic],
        tags=["News"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def list_channels(db: Session = Depends(get_db)):
        cache_key = "pubv1:channels"
        cached = cache_get(cache_key)
        if cached:
            return cached

        query = text("""
            SELECT id, name
            FROM news_channels
            WHERE enabled = true
            ORDER BY name
        """)
        result = db.execute(query)
        channels = [ChannelPublic(id=row.id, name=row.name) for row in result]
        cache_set(cache_key, [c.model_dump() for c in channels], ttl=3600)
        return channels

    # =========================================================================
    # 7. GET /stats — Database statistics
    # =========================================================================

    @public_app.get(
        "/stats",
        summary="Get database statistics",
        description="Total site count and breakdown by data source.",
        response_model=StatsResponse,
        tags=["Stats"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def get_stats(db: Session = Depends(get_db)):
        cache_key = "pubv1:stats"
        cached = cache_get(cache_key)
        if cached:
            return cached

        total = db.execute(text("SELECT COUNT(*) FROM unified_sites")).scalar()
        result = db.execute(text("""
            SELECT source_id, COUNT(*) as count
            FROM unified_sites
            GROUP BY source_id
            ORDER BY count DESC
        """))
        by_source = {row.source_id: row.count for row in result}

        response = StatsResponse(total_sites=total, by_source=by_source)
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    # =========================================================================
    # 8. GET /facets — Distinct filter facets
    # =========================================================================

    @public_app.get(
        "/facets",
        summary="Get filter facets",
        description=(
            "Returns distinct categories, countries, and source metadata "
            "for populating filter dropdowns without loading all sites."
        ),
        response_model=FacetsResponse,
        tags=["Sites"],
        dependencies=[Depends(rate_limit_dependency)],
        responses={429: {"description": "Rate limit exceeded"}},
    )
    async def get_facets(db: Session = Depends(get_db)):
        cache_key = "pubv1:facets"
        cached = cache_get(cache_key)
        if cached:
            return cached

        # Distinct site types
        cat_result = db.execute(text(
            "SELECT DISTINCT site_type FROM unified_sites "
            "WHERE site_type IS NOT NULL AND site_type != '' "
            "ORDER BY site_type"
        ))
        categories = [row[0] for row in cat_result]

        # Distinct countries
        country_result = db.execute(text(
            "SELECT DISTINCT country FROM unified_sites "
            "WHERE country IS NOT NULL AND country != '' "
            "ORDER BY country"
        ))
        countries = [row[0] for row in country_result]

        # Sources with counts
        source_result = db.execute(text("""
            SELECT
                sm.id as source_id,
                sm.name,
                COALESCE(sm.color, :default_color) as color,
                COALESCE(sc.count, 0) as site_count
            FROM source_meta sm
            LEFT JOIN (
                SELECT source_id, COUNT(*) as count
                FROM unified_sites
                GROUP BY source_id
            ) sc ON sm.id = sc.source_id
            WHERE sm.enabled = true
            ORDER BY COALESCE(sc.count, 0) DESC
        """), {"default_color": _SOURCE_COLORS["default"]})

        sources = [
            FacetSource(
                id=row.source_id,
                name=row.name or row.source_id.replace("_", " ").title(),
                color=row.color or _SOURCE_COLORS.get(row.source_id, _SOURCE_COLORS["default"]),
                count=row.site_count,
            )
            for row in source_result
        ]

        response = FacetsResponse(
            categories=categories,
            countries=countries,
            sources=sources,
        )
        cache_set(cache_key, response.model_dump(), ttl=600)
        return response

    return public_app
