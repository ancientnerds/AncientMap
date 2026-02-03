"""
Google Books Connector.

Source #25 from research paper.
Protocol: REST
Auth: API Key (optional for limited access)
License: Varies
Priority: P3

API: https://developers.google.com/books/docs/v1/getting_started
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class GoogleBooksConnector(BaseConnector):
    """Google Books connector."""

    connector_id = "google_books"
    connector_name = "Google Books"
    description = "Books from Google's library digitization project"

    content_types = [ContentType.BOOK]

    base_url = "https://www.googleapis.com/books/v1"
    website_url = "https://books.google.com"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False  # Optional API key for higher limits
    auth_type = AuthType.API_KEY

    license = "Varies"
    attribution = "Google Books"

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
        """Search Google Books."""
        try:
            params = {
                "q": query,
                "maxResults": min(limit, 40),  # Google Books max is 40
                "startIndex": offset,
            }

            if self.api_key:
                params["key"] = self.api_key

            response = await self.rest.get("/volumes", params=params)

            if not response or "items" not in response:
                return []

            items = []
            for volume in response.get("items", []):
                try:
                    volume_info = volume.get("volumeInfo", {})

                    # Get thumbnail
                    thumbnail = None
                    if volume_info.get("imageLinks"):
                        thumbnail = volume_info["imageLinks"].get("thumbnail")

                    item = ContentItem(
                        id=f"google_books:{volume.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.BOOK,
                        title=volume_info.get("title", "Unknown"),
                        description=volume_info.get("description"),
                        url=volume_info.get("infoLink", ""),
                        thumbnail_url=thumbnail,
                        creator=", ".join(volume_info.get("authors", [])),
                        date=volume_info.get("publishedDate"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=volume,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse Google Books volume: {e}")

            return items

        except Exception as e:
            logger.error(f"Google Books search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific volume by ID."""
        try:
            if item_id.startswith("google_books:"):
                item_id = item_id[13:]

            params = {}
            if self.api_key:
                params["key"] = self.api_key

            response = await self.rest.get(f"/volumes/{item_id}", params=params)

            if not response:
                return None

            volume_info = response.get("volumeInfo", {})
            thumbnail = None
            if volume_info.get("imageLinks"):
                thumbnail = volume_info["imageLinks"].get("thumbnail")

            return ContentItem(
                id=f"google_books:{item_id}",
                source=self.connector_id,
                content_type=ContentType.BOOK,
                title=volume_info.get("title", "Unknown"),
                description=volume_info.get("description"),
                url=volume_info.get("infoLink", ""),
                thumbnail_url=thumbnail,
                creator=", ".join(volume_info.get("authors", [])),
                date=volume_info.get("publishedDate"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Google Books volume {item_id}: {e}")
            return None
