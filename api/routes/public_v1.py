"""
Public API v1 — GeoJSON endpoint for archaeological sites.

Experimental / alpha. No authentication required.
Rate-limited to 10 requests per minute per IP.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_get, cache_set
from api.services.rate_limiter import RateLimiter
from pipeline.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="public_v1")

RATE_LIMIT = 10


async def rate_limit_dependency(request: Request, response: Response):
    """FastAPI dependency that enforces rate limiting and sets response headers."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host
    allowed, remaining, reset_seconds = _limiter.check_with_info(ip)

    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_seconds)
    response.headers["X-API-Status"] = "experimental"

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Max 10 requests per minute.",
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
                "X-API-Status": "experimental",
                "Retry-After": str(reset_seconds),
            },
        )


@router.get(
    "/sites.geojson",
    summary="Get archaeological sites as GeoJSON",
    description=(
        "**Experimental API — subject to change without notice.**\n\n"
        "Returns archaeological sites as a GeoJSON FeatureCollection (RFC 7946). "
        "Rate-limited to 10 requests per minute per IP."
    ),
    response_description="GeoJSON FeatureCollection",
    responses={
        429: {"description": "Rate limit exceeded"},
    },
    tags=["Public API"],
    dependencies=[Depends(rate_limit_dependency)],
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
    # Build a cache key from all params
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

    # Parse bbox
    bbox_parsed = None
    if bbox:
        try:
            coords = [float(c) for c in bbox.split(",")]
            if len(coords) != 4:
                raise ValueError
            bbox_parsed = {
                "minlon": coords[0],
                "minlat": coords[1],
                "maxlon": coords[2],
                "maxlat": coords[3],
            }
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid bbox format. Expected: minlon,minlat,maxlon,maxlat") from None

    # Build dynamic SQL
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
        conditions.append(
            "geom && ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)"
        )
        params.update(bbox_parsed)

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
            country,
            description,
            source_url,
            thumbnail_url
        FROM unified_sites
        WHERE {where_clause}
        LIMIT :limit
    """)

    result = db.execute(query, params)

    features = []
    for row in result:
        properties = {
            "id": row.id,
            "name": row.name,
            "source_id": row.source_id,
        }
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
            "geometry": {
                "type": "Point",
                "coordinates": [row.lon, row.lat],
            },
            "properties": properties,
        })

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "api": "v1-alpha",
            "experimental": True,
            "warning": "This API is experimental and subject to change without notice.",
            "count": len(features),
            "limit": limit,
        },
        "features": features,
    }

    cache_set(cache_key, geojson, ttl=300)

    return geojson
