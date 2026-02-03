"""
Wikimedia Commons Connector.

Provides access to images and maps from Wikimedia Commons.

Features:
- Image search with metadata
- Historical map search
- Category-based retrieval
- License information extraction
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.mediawiki import MediaWikiProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class WikimediaConnector(BaseConnector):
    """
    Wikimedia Commons connector.

    Provides access to CC-licensed images and maps from Wikimedia Commons.
    """

    connector_id = "wikimedia"
    connector_name = "Wikimedia Commons"
    description = "Images and historical maps from Wikimedia Commons"

    content_types = [ContentType.PHOTO, ContentType.MAP, ContentType.ARTWORK]

    base_url = "https://commons.wikimedia.org/w/api.php"
    website_url = "https://commons.wikimedia.org"
    protocol = ProtocolType.MEDIAWIKI
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Various CC licenses"
    attribution = "Wikimedia Commons"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.mediawiki = MediaWikiProtocol(
            api_url=self.base_url,
            rate_limit=self.rate_limit,
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search for images on Wikimedia Commons.

        Args:
            query: Search query
            content_type: Filter by PHOTO, MAP, or ARTWORK
            limit: Maximum results
            offset: Pagination offset
            **kwargs: Additional parameters

        Returns:
            List of ContentItem objects
        """
        if not query.strip():
            return []

        try:
            async with self.mediawiki:
                if content_type == ContentType.MAP:
                    results = await self.mediawiki.search_historical_maps(
                        query=query,
                        limit=limit,
                    )
                else:
                    results = await self.mediawiki.search_images(
                        query=query,
                        limit=limit,
                    )

            items = []
            for result in results:
                item = self._parse_image_result(result, content_type)
                if item:
                    items.append(item)

            logger.info(f"Wikimedia: Returning {len(items)} images for '{query}'")
            return items

        except Exception as e:
            logger.error(f"Wikimedia search error: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get a specific image by its page ID or title."""
        try:
            async with self.mediawiki:
                # If item_id is numeric, it's a page ID
                if item_id.isdigit():
                    title = f"File:{item_id}"  # Need to look up
                else:
                    title = item_id if item_id.startswith("File:") else f"File:{item_id}"

                results = await self.mediawiki.get_image_info(title)

            if results:
                return self._parse_image_result(results[0])

            return None

        except Exception as e:
            logger.error(f"Wikimedia get_item error: {e}")
            return None

    async def get_by_empire(
        self,
        empire_name: str,
        period_name: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """Get images for an empire/civilization."""
        search_term = period_name or empire_name

        # For empires, try to get both photos and maps
        items = []

        # Get photos
        photos = await self.search(
            query=f"{search_term} ancient",
            content_type=ContentType.PHOTO,
            limit=limit // 2,
        )
        items.extend(photos)

        # Get maps
        maps = await self.search(
            query=search_term,
            content_type=ContentType.MAP,
            limit=limit // 2,
        )
        items.extend(maps)

        return items[:limit]

    async def search_maps(
        self,
        query: str,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Search specifically for historical maps."""
        return await self.search(
            query=query,
            content_type=ContentType.MAP,
            limit=limit,
        )

    async def get_category_images(
        self,
        category: str,
        limit: int = 50,
    ) -> list[ContentItem]:
        """Get images from a Commons category."""
        try:
            async with self.mediawiki:
                results = await self.mediawiki.search_category_images(
                    category=category,
                    limit=limit,
                )

            items = []
            for result in results:
                item = self._parse_image_result(result)
                if item:
                    items.append(item)

            return items

        except Exception as e:
            logger.error(f"Wikimedia category error: {e}")
            return []

    def _parse_image_result(
        self,
        result: dict,
        content_type: ContentType | None = None,
    ) -> ContentItem | None:
        """Parse Wikimedia image result into ContentItem."""
        title = result.get("title", "")
        url = result.get("url")
        thumb_url = result.get("thumburl")

        if not url or not title:
            return None

        # Determine content type from title if not specified
        if content_type is None:
            title_lower = title.lower()
            if "map" in title_lower or "carte" in title_lower:
                content_type = ContentType.MAP
            elif any(word in title_lower for word in ["painting", "portrait", "art"]):
                content_type = ContentType.ARTWORK
            else:
                content_type = ContentType.PHOTO

        # Build Commons page URL
        page_id = result.get("pageid")
        if page_id:
            page_url = f"https://commons.wikimedia.org/wiki/File:{title.replace('File:', '').replace(' ', '_')}"
        else:
            page_url = url

        return ContentItem(
            id=str(page_id) if page_id else title,
            source=self.connector_id,
            content_type=content_type,
            title=title.replace("File:", ""),
            url=page_url,
            thumbnail_url=thumb_url or url,
            media_url=url,
            creator=result.get("artist"),
            date=result.get("date"),
            description=result.get("description"),
            license=result.get("license"),
            license_url=result.get("license_url"),
            attribution=f"{result.get('artist', 'Unknown')} via Wikimedia Commons",
            raw_data=result,
        )
