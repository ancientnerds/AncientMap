"""
Pleiades GIS Connector.

Source #38 from research paper.
Protocol: REST + RSS
Auth: None
License: CC-BY
Priority: P1

URL: https://pleiades.stoa.org/downloads

Note: This connector focuses on GIS/geographic data from Pleiades.
For full GIS data, bulk downloads are available at the downloads page.
"""

import xml.etree.ElementTree as ET

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PleiadesGISConnector(BaseConnector):
    """Pleiades GIS connector for ancient place GIS data.

    Provides geographic/GIS-focused access to Pleiades data including
    coordinates and spatial information for ancient places.
    """

    connector_id = "pleiades_gis"
    connector_name = "Pleiades GIS"
    description = "GIS data for ancient places from Pleiades"

    content_types = [ContentType.MAP]

    base_url = "https://pleiades.stoa.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY"
    attribution = "Pleiades"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Pleiades for places with GIS data.

        Uses the RSS search endpoint and parses results for geographic info.
        For bulk GIS data, use the downloads page.
        """
        try:
            params = {
                "SearchableText": query,
                "portal_type": "Place",
                "review_state": "published",
                "b_size": limit,
                "b_start": offset,
            }

            # Get RSS feed which includes place info
            response = await self.rest.get_raw("/search_rss", params=params)
            rss_content = response.text

            # Parse RSS to get place IDs, then fetch JSON for each
            items = await self._parse_rss_and_fetch_geo(rss_content, limit)
            return items

        except Exception as e:
            logger.error(f"Pleiades GIS search failed: {e}")
            return []

    async def _parse_rss_and_fetch_geo(self, rss_content: str, limit: int) -> list[ContentItem]:
        """Parse RDF/RSS 1.0 and fetch GeoJSON data for each place."""
        items = []

        try:
            root = ET.fromstring(rss_content)

            # RDF 1.0 format - items are direct children of rdf:RDF
            place_ids = []
            for item in root.findall("{http://purl.org/rss/1.0/}item")[:limit]:
                link = item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
                if "/places/" in link:
                    place_id = link.split("/places/")[-1].rstrip("/")
                    if place_id:
                        place_ids.append((place_id, item))

            # For each place, try to get GeoJSON data
            for place_id, rss_item in place_ids[:limit]:
                try:
                    # Fetch place JSON which includes coordinates
                    place_data = await self.rest.get(f"/places/{place_id}/json")

                    if place_data:
                        item = self._create_gis_item(place_id, place_data, rss_item)
                        if item:
                            items.append(item)
                except Exception as e:
                    # Fall back to RSS-only data
                    logger.debug(f"Could not fetch JSON for place {place_id}: {e}")
                    item = self._create_rss_only_item(place_id, rss_item)
                    if item:
                        items.append(item)

            logger.info(f"Pleiades GIS: found {len(items)} places with GIS data")
            return items

        except ET.ParseError as e:
            logger.error(f"Failed to parse Pleiades RSS: {e}")
            return []

    def _create_gis_item(self, place_id: str, place_data: dict, rss_item) -> ContentItem | None:
        """Create ContentItem with full GIS data from JSON."""
        try:
            # Get coordinates from reprPoint or locations
            lat, lon = None, None
            repr_point = place_data.get("reprPoint")
            if repr_point and len(repr_point) >= 2:
                lon, lat = repr_point[0], repr_point[1]

            # Get bounding box if available
            bbox = place_data.get("bbox")

            title = place_data.get("title", "Unknown Place")
            description = place_data.get("description", "")

            # Add GIS-specific info to description
            if lat and lon:
                description = f"Coordinates: {lat:.4f}, {lon:.4f}. {description}"
            if bbox:
                description = f"{description} Bounding box: {bbox}"

            return ContentItem(
                id=f"pleiades_gis:{place_id}",
                source=self.connector_id,
                content_type=ContentType.MAP,
                title=title,
                description=description.strip() if description else None,
                url=f"https://pleiades.stoa.org/places/{place_id}",
                lat=lat,
                lon=lon,
                place_name=title,
                license=self.license,
                attribution=self.attribution,
                raw_data=place_data,
            )

        except Exception as e:
            logger.debug(f"Error creating GIS item: {e}")
            return None

    def _create_rss_only_item(self, place_id: str, rss_item) -> ContentItem | None:
        """Create ContentItem from RDF/RSS data only."""
        try:
            title = rss_item.findtext("{http://purl.org/rss/1.0/}title", "Unknown Place")
            link = rss_item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", f"https://pleiades.stoa.org/places/{place_id}")
            description = rss_item.findtext("{http://purl.org/rss/1.0/}description", "")

            return ContentItem(
                id=f"pleiades_gis:{place_id}",
                source=self.connector_id,
                content_type=ContentType.MAP,
                title=title,
                description=description if description else None,
                url=link,
                place_name=title,
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.debug(f"Error creating RSS-only item: {e}")
            return None

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get places near a location.

        Uses coordinate-based search to find nearby ancient places.
        """
        try:
            # Calculate bounding box for search
            # 1 degree latitude ≈ 111 km
            lat_delta = radius_km / 111.0
            # 1 degree longitude varies by latitude
            import math
            lon_delta = radius_km / (111.0 * math.cos(math.radians(lat))) if lat != 0 else radius_km / 111.0

            lat - lat_delta
            lat + lat_delta
            lon - lon_delta
            lon + lon_delta

            # Search for places (Pleiades doesn't have direct bbox query in search)
            # So we search broadly and filter by distance
            # Use a search term that's likely to match many places in the area
            await self.rest.get_raw(
                "/search_rss",
                params={
                    "portal_type": "Place",
                    "review_state": "published",
                    "b_size": limit * 2,  # Get extra to filter
                }
            )

            # This is a basic implementation - for production would need
            # proper spatial query support
            logger.debug(f"Pleiades GIS: location search near ({lat}, {lon})")

            # For now, return empty as proper bbox search would need post-filtering
            # which requires fetching all place JSONs
            return []

        except Exception as e:
            logger.error(f"Pleiades GIS location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific place GIS data by ID."""
        try:
            if item_id.startswith("pleiades_gis:"):
                item_id = item_id[13:]

            response = await self.rest.get(f"/places/{item_id}/json")

            if not response:
                return None

            # Extract coordinate information
            coords = response.get("reprPoint", [None, None])

            return ContentItem(
                id=f"pleiades_gis:{item_id}",
                source=self.connector_id,
                content_type=ContentType.MAP,
                title=response.get("title", "Unknown Place"),
                description=response.get("description"),
                url=f"https://pleiades.stoa.org/places/{item_id}",
                lat=coords[1] if len(coords) > 1 else None,
                lon=coords[0] if coords else None,
                place_name=response.get("title"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Pleiades GIS data {item_id}: {e}")
            return None
