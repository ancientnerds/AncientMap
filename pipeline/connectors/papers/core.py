"""
CORE (Connecting Repositories) Connector.

Source #16 from research paper.
Protocol: REST
Auth: API Key
License: Open
Priority: P1

API: https://core.ac.uk/documentation/api/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class COREConnector(BaseConnector):
    """CORE connector for academic papers."""

    connector_id = "core"
    connector_name = "CORE"
    description = "World's largest collection of open access research papers"

    content_types = [ContentType.PAPER]

    base_url = "https://api.core.ac.uk/v3"
    website_url = "https://core.ac.uk"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = True
    auth_type = AuthType.API_KEY

    license = "Open Access"
    attribution = "CORE"

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
        """Search CORE for academic papers."""
        if not self.api_key:
            logger.warning("CORE API key not configured")
            return []

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}

            params = {
                "q": query,
                "limit": limit,
                "offset": offset,
            }

            response = await self.rest.get("/search/works", params=params, headers=headers)

            if not response or "results" not in response:
                return []

            items = []
            for result in response.get("results", []):
                try:
                    item = ContentItem(
                        id=f"core:{result.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.PAPER,
                        title=result.get("title", "Untitled"),
                        description=result.get("abstract"),
                        url=result.get("downloadUrl") or result.get("sourceFulltextUrls", [""])[0] if result.get("sourceFulltextUrls") else "",
                        creator=", ".join(result.get("authors", [])),
                        date=result.get("publishedDate"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=result,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse CORE result: {e}")

            return items

        except Exception as e:
            logger.error(f"CORE search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific paper by ID."""
        if not self.api_key:
            return None

        try:
            if item_id.startswith("core:"):
                item_id = item_id[5:]

            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = await self.rest.get(f"/works/{item_id}", headers=headers)

            if not response:
                return None

            return ContentItem(
                id=f"core:{item_id}",
                source=self.connector_id,
                content_type=ContentType.PAPER,
                title=response.get("title", "Untitled"),
                description=response.get("abstract"),
                url=response.get("downloadUrl", ""),
                creator=", ".join(response.get("authors", [])),
                date=response.get("publishedDate"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get CORE paper {item_id}: {e}")
            return None
