"""
Street View availability checking endpoint.

Uses Google's Street View metadata API to check if coverage exists
at given coordinates. Results are cached to minimize API calls.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Query

from api.cache import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache TTL: 24 hours (Street View coverage rarely changes)
CACHE_TTL = 86400

# Google Maps API key (optional - if not set, always returns available=True)
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


@router.get("/check")
async def check_street_view(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius: int = Query(100, description="Search radius in meters")
):
    """
    Check if Street View coverage exists at the given coordinates.

    Returns:
        - available: bool - whether Street View exists
        - pano_id: str | None - panorama ID if available
    """
    # Round coordinates for cache key (4 decimal places ≈ 11m precision)
    cache_key = f"streetview:{lat:.4f}:{lon:.4f}"

    # Check cache first
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # If no API key configured, always return available (let embed handle it)
    if not GOOGLE_MAPS_API_KEY:
        result = {"available": True, "pano_id": None, "no_key": True}
        cache_set(cache_key, result, ttl=CACHE_TTL)
        return result

    # Call Google Street View metadata API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/streetview/metadata",
                params={
                    "location": f"{lat},{lon}",
                    "radius": radius,
                    "key": GOOGLE_MAPS_API_KEY
                }
            )

            if response.status_code != 200:
                logger.warning(f"Street View API error: {response.status_code}")
                result = {"available": True, "pano_id": None, "error": True}
                # Don't cache errors
                return result

            data = response.json()

            # API returns status: "OK" with pano_id if coverage exists
            # Returns status: "ZERO_RESULTS" if no coverage
            if data.get("status") == "OK" and data.get("pano_id"):
                result = {
                    "available": True,
                    "pano_id": data.get("pano_id"),
                    "location": data.get("location")
                }
            else:
                result = {"available": False, "pano_id": None}

            # Cache result
            cache_set(cache_key, result, ttl=CACHE_TTL)
            return result

    except Exception as e:
        logger.warning(f"Street View check failed: {e}")
        # On error, return available=True to let embed handle it
        return {"available": True, "pano_id": None, "error": True}
