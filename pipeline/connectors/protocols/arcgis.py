"""
ArcGIS REST API Protocol Handler.

Provides access to ArcGIS Feature Services used by:
- Historic England
- Ireland SMR (Sites and Monuments Record)
- Various heritage mapping services
"""

import asyncio
from typing import Any

import httpx
from loguru import logger


class ArcGISProtocol:
    """
    ArcGIS Feature Service protocol handler.

    Supports:
    - Feature queries with spatial filters
    - Attribute queries
    - Paginated results
    - GeoJSON output
    """

    def __init__(
        self,
        base_url: str,
        layer_id: int = 0,
        timeout: float = 60.0,
        rate_limit: float = 2.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize ArcGIS protocol handler.

        Args:
            base_url: Feature service URL (e.g., "https://example.com/arcgis/rest/services/MyService/FeatureServer")
            layer_id: Layer ID to query (default 0)
            timeout: Request timeout
            rate_limit: Max requests per second
            http_client: Optional shared HTTP client
        """
        self.base_url = base_url.rstrip("/")
        self.layer_id = layer_id
        self.timeout = timeout
        self.rate_limit = rate_limit

        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

    async def __aenter__(self):
        if self._owns_client and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
            self._owns_client = True
        return self._http_client

    @property
    def query_url(self) -> str:
        """Get the query endpoint URL."""
        return f"{self.base_url}/{self.layer_id}/query"

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        if self.rate_limit <= 0:
            return

        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._last_request_time = asyncio.get_event_loop().time()

    async def query(
        self,
        where: str = "1=1",
        out_fields: str = "*",
        geometry: dict[str, Any] | None = None,
        geometry_type: str = "esriGeometryEnvelope",
        spatial_rel: str = "esriSpatialRelIntersects",
        out_sr: int = 4326,
        return_geometry: bool = True,
        result_offset: int = 0,
        result_record_count: int = 1000,
        order_by_fields: str | None = None,
    ) -> dict[str, Any]:
        """
        Query features from the service.

        Args:
            where: SQL-like WHERE clause
            out_fields: Fields to return (* for all)
            geometry: Geometry filter (envelope, point, polygon)
            geometry_type: Type of geometry filter
            spatial_rel: Spatial relationship
            out_sr: Output spatial reference (4326 = WGS84)
            return_geometry: Include geometry in response
            result_offset: Starting record number
            result_record_count: Max records to return
            order_by_fields: Field(s) to sort by

        Returns:
            Query response with features
        """
        await self._rate_limit()

        params = {
            "where": where,
            "outFields": out_fields,
            "outSR": out_sr,
            "returnGeometry": str(return_geometry).lower(),
            "resultOffset": result_offset,
            "resultRecordCount": result_record_count,
            "f": "json",
        }

        if geometry:
            params["geometry"] = self._serialize_geometry(geometry)
            params["geometryType"] = geometry_type
            params["spatialRel"] = spatial_rel
            params["inSR"] = 4326

        if order_by_fields:
            params["orderByFields"] = order_by_fields

        try:
            response = await self.client.get(
                self.query_url,
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"ArcGIS query error: {e}")
            raise

    async def query_geojson(
        self,
        where: str = "1=1",
        out_fields: str = "*",
        geometry: dict[str, Any] | None = None,
        result_offset: int = 0,
        result_record_count: int = 1000,
    ) -> dict[str, Any]:
        """
        Query features and return as GeoJSON.

        Args:
            where: SQL-like WHERE clause
            out_fields: Fields to return
            geometry: Geometry filter
            result_offset: Starting record
            result_record_count: Max records

        Returns:
            GeoJSON FeatureCollection
        """
        await self._rate_limit()

        params = {
            "where": where,
            "outFields": out_fields,
            "outSR": 4326,
            "returnGeometry": "true",
            "resultOffset": result_offset,
            "resultRecordCount": result_record_count,
            "f": "geojson",
        }

        if geometry:
            params["geometry"] = self._serialize_geometry(geometry)
            params["geometryType"] = "esriGeometryEnvelope"
            params["spatialRel"] = "esriSpatialRelIntersects"
            params["inSR"] = 4326

        try:
            response = await self.client.get(
                self.query_url,
                params=params,
                headers={"Accept": "application/geo+json"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"ArcGIS GeoJSON query error: {e}")
            raise

    async def query_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        where: str = "1=1",
        out_fields: str = "*",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Query features within a bounding box.

        Args:
            min_lon: Minimum longitude
            min_lat: Minimum latitude
            max_lon: Maximum longitude
            max_lat: Maximum latitude
            where: Additional WHERE filter
            out_fields: Fields to return
            limit: Maximum features

        Returns:
            List of feature dictionaries
        """
        geometry = {
            "xmin": min_lon,
            "ymin": min_lat,
            "xmax": max_lon,
            "ymax": max_lat,
            "spatialReference": {"wkid": 4326},
        }

        result = await self.query(
            where=where,
            out_fields=out_fields,
            geometry=geometry,
            result_record_count=limit,
        )

        return result.get("features", [])

    async def query_by_point(
        self,
        lon: float,
        lat: float,
        radius_meters: float = 1000,
        where: str = "1=1",
        out_fields: str = "*",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query features near a point.

        Args:
            lon: Longitude
            lat: Latitude
            radius_meters: Search radius in meters
            where: Additional WHERE filter
            out_fields: Fields to return
            limit: Maximum features

        Returns:
            List of feature dictionaries
        """
        # Convert radius to approximate degrees
        # (1 degree ≈ 111km at equator, less at higher latitudes)
        import math
        lat_factor = math.cos(math.radians(lat))
        radius_deg = radius_meters / 111000

        geometry = {
            "xmin": lon - (radius_deg / lat_factor),
            "ymin": lat - radius_deg,
            "xmax": lon + (radius_deg / lat_factor),
            "ymax": lat + radius_deg,
            "spatialReference": {"wkid": 4326},
        }

        result = await self.query(
            where=where,
            out_fields=out_fields,
            geometry=geometry,
            result_record_count=limit,
        )

        return result.get("features", [])

    async def query_all_paginated(
        self,
        where: str = "1=1",
        out_fields: str = "*",
        page_size: int = 1000,
        max_records: int = 10000,
    ) -> list[dict[str, Any]]:
        """
        Paginate through all matching records.

        Args:
            where: SQL-like WHERE clause
            out_fields: Fields to return
            page_size: Records per page
            max_records: Maximum total records

        Returns:
            List of all feature dictionaries
        """
        all_features = []
        offset = 0

        while offset < max_records:
            result = await self.query(
                where=where,
                out_fields=out_fields,
                result_offset=offset,
                result_record_count=page_size,
            )

            features = result.get("features", [])
            if not features:
                break

            all_features.extend(features)
            offset += len(features)

            # Check if we've got all records
            if len(features) < page_size:
                break

            # Check for exceeded transfer limit
            if result.get("exceededTransferLimit"):
                logger.info(f"ArcGIS transfer limit reached at offset {offset}")
            else:
                break

        logger.info(f"Fetched {len(all_features)} features from ArcGIS")
        return all_features

    async def get_layer_info(self) -> dict[str, Any]:
        """
        Get metadata about the layer.

        Returns:
            Layer metadata dictionary
        """
        await self._rate_limit()

        url = f"{self.base_url}/{self.layer_id}"
        params = {"f": "json"}

        response = await self.client.get(url, params=params)
        response.raise_for_status()

        return response.json()

    async def get_record_count(self, where: str = "1=1") -> int:
        """
        Get count of records matching query.

        Args:
            where: SQL-like WHERE clause

        Returns:
            Record count
        """
        await self._rate_limit()

        params = {
            "where": where,
            "returnCountOnly": "true",
            "f": "json",
        }

        response = await self.client.get(self.query_url, params=params)
        response.raise_for_status()

        result = response.json()
        return result.get("count", 0)

    def _serialize_geometry(self, geometry: dict[str, Any]) -> str:
        """Serialize geometry to JSON string."""
        import json
        return json.dumps(geometry)

    def extract_coordinates(
        self,
        feature: dict[str, Any],
    ) -> tuple | None:
        """
        Extract lat/lon from a feature.

        Args:
            feature: ArcGIS feature dictionary

        Returns:
            (lat, lon) tuple or None
        """
        geometry = feature.get("geometry")
        if not geometry:
            return None

        # Point geometry
        if "x" in geometry and "y" in geometry:
            return (geometry["y"], geometry["x"])

        # Polygon/polyline - use centroid
        if "rings" in geometry:
            # Calculate centroid of first ring
            ring = geometry["rings"][0]
            if ring:
                sum_x = sum(p[0] for p in ring)
                sum_y = sum(p[1] for p in ring)
                return (sum_y / len(ring), sum_x / len(ring))

        return None
