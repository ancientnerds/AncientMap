"""
Open Context Connector.

Source #9 from research paper.
Protocol: REST + GeoJSON
Auth: None
License: CC-BY
Priority: P1

API: https://opencontext.org/about/services
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class OpenContextConnector(BaseConnector):
    """Open Context connector for archaeological data."""

    connector_id = "open_context"
    connector_name = "Open Context"
    description = "Archaeological data publication platform"

    content_types = [ContentType.ARTIFACT, ContentType.DOCUMENT]

    base_url = "https://opencontext.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY"
    attribution = "Open Context"

    # Blocked by Anubis bot protection as of 2024
    available = False
    unavailable_reason = "API blocked by Anubis bot protection"

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
        """Search Open Context.

        Note: Site blocked by Anubis bot protection.
        This connector is marked as unavailable.
        """
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific item by UUID."""
        try:
            if item_id.startswith("open_context:"):
                item_id = item_id[13:]

            response = await self.rest.get(f"/subjects/{item_id}.json")

            if not response:
                return None

            return ContentItem(
                id=f"open_context:{item_id}",
                source=self.connector_id,
                content_type=ContentType.ARTIFACT,
                title=response.get("label", "Unknown"),
                description=response.get("description"),
                url=response.get("uri", f"https://opencontext.org/subjects/{item_id}"),
                thumbnail_url=response.get("thumbnail"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Open Context item {item_id}: {e}")
            return None
