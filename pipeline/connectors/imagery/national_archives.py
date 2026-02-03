"""
U.S. National Archives Connector.

Source #28 from research paper.
Protocol: REST
Auth: None
License: Public Domain
Priority: P2

API: https://www.archives.gov/developer
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class NationalArchivesConnector(BaseConnector):
    """U.S. National Archives connector for documents and images."""

    connector_id = "nara"
    connector_name = "National Archives"
    description = "Documents and images from the U.S. National Archives"

    content_types = [ContentType.PHOTO, ContentType.DOCUMENT]

    base_url = "https://catalog.archives.gov/api/v1"
    website_url = "https://www.archives.gov"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Public Domain"
    attribution = "National Archives and Records Administration"

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
        """Search National Archives catalog."""
        try:
            params = {
                "q": query,
                "rows": limit,
                "offset": offset,
            }

            # Filter by type if specified
            if content_type == ContentType.PHOTO:
                params["type.all"] = "image"
            elif content_type == ContentType.DOCUMENT:
                params["type.all"] = "document"

            response = await self.rest.get("/", params=params)

            if not response or "opaResponse" not in response:
                return []

            results = response.get("opaResponse", {}).get("results", {}).get("result", [])

            items = []
            for result in results:
                try:
                    desc = result.get("description", {})

                    # Get thumbnail
                    thumbnail = None
                    objects = result.get("objects", {}).get("object", [])
                    if objects and isinstance(objects, list) and objects:
                        obj = objects[0]
                        if isinstance(obj, dict):
                            thumbnail = obj.get("thumbnail", {}).get("@url")

                    item = ContentItem(
                        id=f"nara:{result.get('naId', '')}",
                        source=self.connector_id,
                        content_type=ContentType.DOCUMENT,
                        title=desc.get("item", {}).get("title", "Unknown"),
                        description=desc.get("item", {}).get("scopeAndContentNote"),
                        url=f"https://catalog.archives.gov/id/{result.get('naId', '')}",
                        thumbnail_url=thumbnail,
                        date=desc.get("item", {}).get("productionDateArray", {}).get("productionDate", [{}])[0].get("year") if desc.get("item", {}).get("productionDateArray") else None,
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=result,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse NARA item: {e}")

            return items

        except Exception as e:
            logger.error(f"National Archives search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific item by NAID."""
        try:
            if item_id.startswith("nara:"):
                item_id = item_id[5:]

            response = await self.rest.get(f"/{item_id}")

            if not response or "opaResponse" not in response:
                return None

            result = response.get("opaResponse", {}).get("result", {})
            desc = result.get("description", {})

            return ContentItem(
                id=f"nara:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=desc.get("item", {}).get("title", "Unknown"),
                description=desc.get("item", {}).get("scopeAndContentNote"),
                url=f"https://catalog.archives.gov/id/{item_id}",
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get NARA item {item_id}: {e}")
            return None
