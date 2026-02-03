"""
ARIADNE Portal Connector.

Source #10 from research paper.
Protocol: REST + SPARQL
Auth: None
License: Varies
Priority: P1

API: https://portal.ariadne-infrastructure.eu/api
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class ARIADNEConnector(BaseConnector):
    """ARIADNE Portal connector for European archaeological data."""

    connector_id = "ariadne"
    connector_name = "ARIADNE Portal"
    description = "European archaeological research infrastructure"

    content_types = [ContentType.ARTIFACT, ContentType.DOCUMENT, ContentType.MODEL_3D]

    base_url = "https://portal.ariadne-infrastructure.eu/api"
    website_url = "https://portal.ariadne-infrastructure.eu"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Varies"
    attribution = "ARIADNE"

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
        """Search ARIADNE Portal."""
        try:
            params = {
                "q": query,
                "size": limit,
                "from": offset,
            }

            response = await self.rest.get("/search", params=params)

            if not response:
                return []

            # Parse ElasticSearch response structure
            # Response has: total, hits (array), aggregations
            hits = response.get("hits", [])
            if not hits:
                return []

            items = []
            for hit in hits:
                try:
                    item = self._parse_hit(hit)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse ARIADNE hit: {e}")

            logger.info(f"ARIADNE search for '{query}' returned {len(items)} results")
            return items

        except Exception as e:
            logger.error(f"ARIADNE search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific resource by ID."""
        try:
            if item_id.startswith("ariadne:"):
                item_id = item_id[8:]

            response = await self.rest.get(f"/resource/{item_id}")

            if not response:
                return None

            # Single resource response has same structure as hit data
            return self._parse_resource(response)

        except Exception as e:
            logger.error(f"Failed to get ARIADNE resource {item_id}: {e}")
            return None

    def _parse_hit(self, hit: dict) -> ContentItem | None:
        """Parse an ElasticSearch hit into a ContentItem."""
        hit_id = hit.get("id")
        data = hit.get("data", {})

        if not hit_id or not data:
            return None

        # Extract coordinates from spatial data
        lat, lon = None, None
        spatial = data.get("spatial", [])
        if spatial and isinstance(spatial, list) and len(spatial) > 0:
            first_spatial = spatial[0]
            if isinstance(first_spatial, dict):
                location = first_spatial.get("location", {})
                if location:
                    lon = location.get("lon")
                    lat = location.get("lat")

        # Extract temporal info
        temporal = data.get("temporal", [])
        date_info = None
        if temporal and isinstance(temporal, list) and len(temporal) > 0:
            first_temporal = temporal[0]
            if isinstance(first_temporal, dict):
                period_name = first_temporal.get("periodName")
                from_year = first_temporal.get("from")
                to_year = first_temporal.get("to")
                if period_name:
                    date_info = period_name
                elif from_year and to_year:
                    date_info = f"{from_year} - {to_year}"

        # Determine content type based on resourceType
        resource_type = data.get("resourceType", "")
        if "3d" in resource_type.lower() or "model" in resource_type.lower():
            ct = ContentType.MODEL_3D
        elif "image" in resource_type.lower():
            ct = ContentType.ARTIFACT
        else:
            ct = ContentType.DOCUMENT

        return ContentItem(
            id=f"ariadne:{hit_id}",
            source=self.connector_id,
            content_type=ct,
            title=data.get("title", "Untitled"),
            description=data.get("description"),
            url=f"https://portal.ariadne-infrastructure.eu/resource/{hit_id}",
            lat=lat,
            lon=lon,
            date=date_info,
            creator=data.get("creator"),
            license=self.license,
            attribution=self.attribution,
            raw_data=data,
        )

    def _parse_resource(self, response: dict) -> ContentItem | None:
        """Parse a single resource response."""
        # Single resource endpoint returns data directly (not wrapped in hit)
        resource_id = response.get("id") or response.get("identifier")
        if not resource_id:
            return None

        # Extract coordinates
        lat, lon = None, None
        spatial = response.get("spatial", [])
        if spatial and isinstance(spatial, list) and len(spatial) > 0:
            first_spatial = spatial[0]
            if isinstance(first_spatial, dict):
                location = first_spatial.get("location", {})
                if location:
                    lon = location.get("lon")
                    lat = location.get("lat")

        # Extract temporal info
        temporal = response.get("temporal", [])
        date_info = None
        if temporal and isinstance(temporal, list) and len(temporal) > 0:
            first_temporal = temporal[0]
            if isinstance(first_temporal, dict):
                period_name = first_temporal.get("periodName")
                if period_name:
                    date_info = period_name

        resource_type = response.get("resourceType", "")
        if "3d" in resource_type.lower() or "model" in resource_type.lower():
            ct = ContentType.MODEL_3D
        elif "image" in resource_type.lower():
            ct = ContentType.ARTIFACT
        else:
            ct = ContentType.DOCUMENT

        return ContentItem(
            id=f"ariadne:{resource_id}",
            source=self.connector_id,
            content_type=ct,
            title=response.get("title", "Untitled"),
            description=response.get("description"),
            url=f"https://portal.ariadne-infrastructure.eu/resource/{resource_id}",
            lat=lat,
            lon=lon,
            date=date_info,
            creator=response.get("creator"),
            license=self.license,
            attribution=self.attribution,
            raw_data=response,
        )
