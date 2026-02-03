"""
Europeana Connector.

Source #5 from research paper.
Protocol: REST + SPARQL + IIIF
Auth: API Key
License: Varies by item
Priority: P1

API: https://pro.europeana.eu/page/apis
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class EuropeanaConnector(BaseConnector):
    """Europeana connector for European cultural heritage."""

    connector_id = "europeana"
    connector_name = "Europeana"
    description = "European cultural heritage from 3,000+ institutions"

    content_types = [
        ContentType.ARTIFACT,
        ContentType.ARTWORK,
        ContentType.PHOTO,
        ContentType.MANUSCRIPT,
        ContentType.MAP,
    ]

    base_url = "https://api.europeana.eu/record/v2"
    website_url = "https://www.europeana.eu"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = True
    auth_type = AuthType.API_KEY

    license = "Varies by item"
    attribution = "Europeana"

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
        """Search Europeana collection."""
        if not self.api_key:
            logger.warning("Europeana API key not configured")
            return []

        try:
            params = {
                "wskey": self.api_key,
                "query": query,
                "rows": limit,
                "start": offset + 1,
                "profile": "rich",
            }

            # Add content type filter
            if content_type:
                type_mapping = {
                    ContentType.PHOTO: "IMAGE",
                    ContentType.ARTIFACT: "3D",
                    ContentType.MANUSCRIPT: "TEXT",
                    ContentType.MAP: "IMAGE",
                }
                if content_type in type_mapping:
                    params["qf"] = f"TYPE:{type_mapping[content_type]}"

            response = await self.rest.get("/search.json", params=params)

            if not response or "items" not in response:
                return []

            items = []
            for item in response.get("items", []):
                try:
                    content_item = self._parse_item(item)
                    if content_item:
                        items.append(content_item)
                except Exception as e:
                    logger.debug(f"Failed to parse Europeana item: {e}")

            return items

        except Exception as e:
            logger.error(f"Europeana search failed: {e}")
            return []

    def _parse_item(self, item: dict) -> ContentItem | None:
        """Parse Europeana item to ContentItem."""
        item_id = item.get("id", "")
        title = item.get("title", ["Untitled"])[0] if item.get("title") else "Untitled"

        # Determine content type from Europeana type
        europeana_type = item.get("type", "IMAGE")
        content_type = ContentType.ARTIFACT
        if europeana_type == "IMAGE":
            content_type = ContentType.PHOTO
        elif europeana_type == "TEXT":
            content_type = ContentType.MANUSCRIPT
        elif europeana_type == "3D":
            content_type = ContentType.MODEL_3D

        # Get thumbnail
        thumbnail = None
        if item.get("edmPreview"):
            thumbnail = item["edmPreview"][0]

        # Get URL
        url = item.get("guid", f"https://www.europeana.eu/item{item_id}")

        return ContentItem(
            id=f"europeana:{item_id}",
            source=self.connector_id,
            content_type=content_type,
            title=title,
            description=item.get("dcDescription", [""])[0] if item.get("dcDescription") else None,
            url=url,
            thumbnail_url=thumbnail,
            creator=item.get("dcCreator", [""])[0] if item.get("dcCreator") else None,
            date=item.get("year", [""])[0] if item.get("year") else None,
            license=item.get("rights", [""])[0] if item.get("rights") else self.license,
            attribution=self.attribution,
            raw_data=item,
        )

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific item by ID."""
        if not self.api_key:
            return None

        try:
            # Remove prefix if present
            if item_id.startswith("europeana:"):
                item_id = item_id[10:]

            response = await self.rest.get(
                f"{item_id}.json",
                params={"wskey": self.api_key}
            )

            if response and "object" in response:
                return self._parse_item(response["object"])

        except Exception as e:
            logger.error(f"Failed to get Europeana item {item_id}: {e}")

        return None
