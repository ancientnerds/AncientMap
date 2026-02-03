"""
GeoNames Connector.

Source #51 from research paper.
Protocol: REST
Auth: Username (free registration)
License: CC-BY
Priority: P1

API: https://www.geonames.org/export/web-services.html
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class GeoNamesConnector(BaseConnector):
    """GeoNames connector for geographic place names."""

    connector_id = "geonames"
    connector_name = "GeoNames"
    description = "Geographical database with place names"

    content_types = [ContentType.DOCUMENT]

    base_url = "http://api.geonames.org"
    website_url = "https://www.geonames.org"
    protocol = ProtocolType.REST
    rate_limit = 1.0  # GeoNames has strict rate limits
    requires_auth = True
    auth_type = AuthType.API_KEY  # Actually uses username

    license = "CC-BY"
    attribution = "GeoNames"

    def __init__(self, api_key: str | None = None, **kwargs):
        """Initialize with API key (GeoNames username)."""
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)
        # GeoNames uses 'username' parameter instead of API key
        self.username = api_key or "demo"  # 'demo' has very limited access

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search GeoNames places."""
        try:
            params = {
                "q": query,
                "maxRows": limit,
                "startRow": offset,
                "username": self.username,
                "type": "json",
            }

            response = await self.rest.get("/searchJSON", params=params)

            if not response or "geonames" not in response:
                return []

            items = []
            for place in response.get("geonames", []):
                try:
                    item = ContentItem(
                        id=f"geonames:{place.get('geonameId', '')}",
                        source=self.connector_id,
                        content_type=ContentType.DOCUMENT,
                        title=place.get("name", "Unknown"),
                        description=f"{place.get('fcodeName', '')} in {place.get('countryName', '')}",
                        url=f"https://www.geonames.org/{place.get('geonameId', '')}",
                        lat=float(place["lat"]) if place.get("lat") else None,
                        lon=float(place["lng"]) if place.get("lng") else None,
                        place_name=place.get("name"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=place,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse GeoNames place: {e}")

            return items

        except Exception as e:
            logger.error(f"GeoNames search failed: {e}")
            return []

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get places near a location."""
        try:
            params = {
                "lat": lat,
                "lng": lon,
                "radius": radius_km,
                "maxRows": limit,
                "username": self.username,
                "type": "json",
            }

            response = await self.rest.get("/findNearbyJSON", params=params)

            if not response or "geonames" not in response:
                return []

            items = []
            for place in response.get("geonames", []):
                try:
                    item = ContentItem(
                        id=f"geonames:{place.get('geonameId', '')}",
                        source=self.connector_id,
                        content_type=ContentType.DOCUMENT,
                        title=place.get("name", "Unknown"),
                        description=f"{place.get('fcodeName', '')} in {place.get('countryName', '')}",
                        url=f"https://www.geonames.org/{place.get('geonameId', '')}",
                        lat=float(place["lat"]) if place.get("lat") else None,
                        lon=float(place["lng"]) if place.get("lng") else None,
                        place_name=place.get("name"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=place,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse GeoNames place: {e}")

            return items

        except Exception as e:
            logger.error(f"GeoNames location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific place by GeoNames ID."""
        try:
            if item_id.startswith("geonames:"):
                item_id = item_id[9:]

            params = {
                "geonameId": item_id,
                "username": self.username,
                "type": "json",
            }

            response = await self.rest.get("/getJSON", params=params)

            if not response or "geonameId" not in response:
                return None

            return ContentItem(
                id=f"geonames:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=response.get("name", "Unknown"),
                description=f"{response.get('fcodeName', '')} in {response.get('countryName', '')}",
                url=f"https://www.geonames.org/{item_id}",
                lat=float(response["lat"]) if response.get("lat") else None,
                lon=float(response["lng"]) if response.get("lng") else None,
                place_name=response.get("name"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get GeoNames place {item_id}: {e}")
            return None
