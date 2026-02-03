"""
HathiTrust Digital Library Connector.

Source #21 from research paper.
Protocol: REST
Auth: None (for search)
License: Varies
Priority: P2

API: https://www.hathitrust.org/data
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class HathiTrustConnector(BaseConnector):
    """HathiTrust connector for digitized books."""

    connector_id = "hathitrust"
    connector_name = "HathiTrust"
    description = "Digital library of millions of books from research libraries"

    content_types = [ContentType.BOOK]

    base_url = "https://catalog.hathitrust.org/api/volumes"
    website_url = "https://www.hathitrust.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Varies"
    attribution = "HathiTrust Digital Library"

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
        """Search HathiTrust catalog."""
        try:
            # HathiTrust uses a different search endpoint
            {
                "q1": query,
                "field1": "ocr",
                "a": "srchls",
                "lmt": limit,
                "pn": offset // limit + 1 if limit > 0 else 1,
            }

            # Note: Full text search requires more complex handling
            logger.warning("HathiTrust connector search not fully implemented")
            return []

        except Exception as e:
            logger.error(f"HathiTrust search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific volume by ID."""
        try:
            if item_id.startswith("hathitrust:"):
                item_id = item_id[11:]

            response = await self.rest.get(f"/brief/htid/{item_id}.json")

            if not response or "items" not in response:
                return None

            items = response.get("items", [])
            if not items:
                return None

            item = items[0]
            record = response.get("records", {}).get(item.get("fromRecord", ""), {})

            return ContentItem(
                id=f"hathitrust:{item_id}",
                source=self.connector_id,
                content_type=ContentType.BOOK,
                title=record.get("titles", ["Unknown"])[0] if record.get("titles") else "Unknown",
                description=record.get("description"),
                url=item.get("itemURL", f"https://babel.hathitrust.org/cgi/pt?id={item_id}"),
                creator=record.get("authors", [""])[0] if record.get("authors") else None,
                date=record.get("publishDates", [""])[0] if record.get("publishDates") else None,
                license=item.get("usRightsString", self.license),
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get HathiTrust volume {item_id}: {e}")
            return None
