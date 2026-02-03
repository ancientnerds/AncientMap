"""
Library of Congress Maps Connector.

Source #36 from research paper.
Protocol: REST
Auth: None
License: Public Domain
Priority: P1

API: https://www.loc.gov/maps/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class LOCMapsConnector(BaseConnector):
    """Library of Congress Maps connector for historical maps."""

    connector_id = "loc_maps"
    connector_name = "Library of Congress Maps"
    description = "Historical maps from the Library of Congress"

    content_types = [ContentType.MAP]

    base_url = "https://www.loc.gov"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Public Domain"
    attribution = "Library of Congress, Geography and Map Division"

    # Blocked by Cloudflare bot protection
    available = False
    unavailable_reason = "API blocked by Cloudflare bot protection"

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
        """Search Library of Congress Maps collection.

        Note: API blocked by Cloudflare bot protection.
        This connector is marked as unavailable.
        """
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific map by ID."""
        try:
            if item_id.startswith("loc_maps:"):
                item_id = item_id[9:]

            response = await self.rest.get(f"/item/{item_id}/", params={"fo": "json"})

            if not response or "item" not in response:
                return None

            item_data = response.get("item", {})

            thumbnail = None
            if item_data.get("image_url"):
                images = item_data["image_url"]
                if isinstance(images, list) and images:
                    thumbnail = images[0]

            return ContentItem(
                id=f"loc_maps:{item_id}",
                source=self.connector_id,
                content_type=ContentType.MAP,
                title=item_data.get("title", "Unknown Map"),
                description=item_data.get("description"),
                url=item_data.get("url", f"https://www.loc.gov/item/{item_id}/"),
                thumbnail_url=thumbnail,
                creator=item_data.get("contributor"),
                date=item_data.get("date"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get LoC Maps item {item_id}: {e}")
            return None
