"""
Library of Congress Connector.

Source #27 from research paper.
Protocol: REST
Auth: None
License: Public Domain (mostly)
Priority: P1

API: https://www.loc.gov/apis/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class LibraryOfCongressConnector(BaseConnector):
    """Library of Congress connector for images and documents."""

    connector_id = "loc"
    connector_name = "Library of Congress"
    description = "Photos, prints, and drawings from the Library of Congress"

    content_types = [ContentType.PHOTO, ContentType.DOCUMENT, ContentType.MAP]

    base_url = "https://www.loc.gov"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Public Domain"
    attribution = "Library of Congress"

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
        """Search Library of Congress."""
        try:
            # Determine collection based on content type
            collection = "photos"
            if content_type == ContentType.MAP:
                collection = "maps"
            elif content_type == ContentType.DOCUMENT:
                collection = "manuscripts"

            params = {
                "q": query,
                "fo": "json",
                "c": limit,
                "sp": offset // limit + 1 if limit > 0 else 1,
            }

            response = await self.rest.get(f"/{collection}/", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for result in response.get("results", []):
                try:
                    # Get thumbnail from image URLs
                    thumbnail = None
                    if result.get("image_url"):
                        images = result["image_url"]
                        if isinstance(images, list) and images:
                            thumbnail = images[0]
                        elif isinstance(images, str):
                            thumbnail = images

                    # Determine content type from original format
                    ct = ContentType.PHOTO
                    if content_type:
                        ct = content_type
                    elif "map" in result.get("original_format", [""])[0].lower() if result.get("original_format") else False:
                        ct = ContentType.MAP

                    item = ContentItem(
                        id=f"loc:{result.get('id', '')}",
                        source=self.connector_id,
                        content_type=ct,
                        title=result.get("title", "Unknown"),
                        description=result.get("description", [""])[0] if result.get("description") else None,
                        url=result.get("url", ""),
                        thumbnail_url=thumbnail,
                        creator=result.get("contributor", [""])[0] if result.get("contributor") else None,
                        date=result.get("date", ""),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=result,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse LoC item: {e}")

            return items

        except Exception as e:
            logger.error(f"Library of Congress search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific item by ID."""
        try:
            if item_id.startswith("loc:"):
                item_id = item_id[4:]

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
                id=f"loc:{item_id}",
                source=self.connector_id,
                content_type=ContentType.PHOTO,
                title=item_data.get("title", "Unknown"),
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
            logger.error(f"Failed to get LoC item {item_id}: {e}")
            return None
