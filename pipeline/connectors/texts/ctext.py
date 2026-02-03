"""
Chinese Text Project Connector.

Source #24 from research paper.
Protocol: JSON
Auth: None
License: Open
Priority: P2

API: https://ctext.org/tools/api
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class ChineseTextProjectConnector(BaseConnector):
    """Chinese Text Project connector for classical Chinese texts."""

    connector_id = "ctext"
    connector_name = "Chinese Text Project"
    description = "Classical Chinese texts with translations"

    content_types = [ContentType.PRIMARY_TEXT]

    base_url = "https://api.ctext.org"
    website_url = "https://ctext.org"
    protocol = ProtocolType.REST
    rate_limit = 1.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Open"
    attribution = "Chinese Text Project"

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
        """Search Chinese Text Project."""
        try:
            params = {
                "title": query,
            }

            response = await self.rest.get("/gettextinfo", params=params)

            if not response:
                return []

            # Parse response - simplified stub
            logger.warning("Chinese Text Project connector not fully implemented")
            return []

        except Exception as e:
            logger.error(f"Chinese Text Project search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific text by URN."""
        try:
            if item_id.startswith("ctext:"):
                item_id = item_id[6:]

            params = {
                "urn": item_id,
            }

            response = await self.rest.get("/gettextinfo", params=params)

            if not response:
                return None

            return ContentItem(
                id=f"ctext:{item_id}",
                source=self.connector_id,
                content_type=ContentType.PRIMARY_TEXT,
                title=response.get("title", "Unknown"),
                description=response.get("description"),
                url=f"https://ctext.org/{item_id}",
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Chinese Text Project text {item_id}: {e}")
            return None
