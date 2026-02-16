"""
Wikimedia Commons Connector.

Provides access to images and maps from Wikimedia Commons.

Features:
- Image search with metadata
- Historical map search
- Category-based retrieval (precise path via WikimediaResolver)
- License information extraction
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.imagery.wikimedia_resolver import _resolver
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

    content_types = [ContentType.PHOTO, ContentType.MAP, ContentType.ARTWORK, ContentType.VIDEO]

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
                elif content_type == ContentType.VIDEO:
                    results = await self.mediawiki.search_images(
                        query=query,
                        limit=limit,
                        file_type="video",
                    )
                    # Resolve .webm transcodes — Ogg Theora has poor browser support
                    if results:
                        titles = [r["title"] for r in results if r.get("title")]
                        transcodes = await self.mediawiki.get_video_transcodes(titles)
                        for r in results:
                            webm_url = transcodes.get(r.get("title", ""))
                            if webm_url:
                                r["transcode_url"] = webm_url
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

            logger.info(f"Wikimedia: Returning {len(items)} items for '{query}'")
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

    async def get_by_site(
        self,
        site_name: str,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """Get photos and videos for a site.

        Two-path strategy:
        - Precise path: if WikimediaResolver finds a Commons category, search
          within that category for accurate results.
        - Fallback path: free-text search with country disambiguation.
        """
        source_url = kwargs.get("source_url")
        entity = await _resolver.resolve(site_name, source_url)

        if entity and entity.commons_category:
            return await self._search_in_category(
                entity.commons_category, site_name, content_type, limit
            )

        # Fallback: free-text search with country disambiguation
        query = site_name
        if location:
            country = self.extract_country(location)
            if country:
                query = f"{site_name} {country}"

        if content_type:
            return await self.search(query=query, content_type=content_type, limit=limit)

        photos = await self.search(
            query=query,
            content_type=ContentType.PHOTO,
            limit=limit,
        )

        videos = await self.search(
            query=query,
            content_type=ContentType.VIDEO,
            limit=max(limit // 4, 5),
        )

        return photos + videos

    async def _search_in_category(
        self,
        commons_category: str,
        site_name: str,
        content_type: ContentType | None,
        limit: int,
    ) -> list[ContentItem]:
        """Search within a resolved Commons category for precise results.

        Category constraint is only used for photos/images — most Commons
        videos are NOT filed under the site's main category, so videos
        always use free-text search to avoid returning empty results.
        """
        logger.info(f"Wikimedia: precise search in category '{commons_category}'")

        if content_type == ContentType.VIDEO:
            # Videos: free-text search (category constraint is too restrictive)
            return await self.search(
                query=site_name,
                content_type=ContentType.VIDEO,
                limit=limit,
            )

        if content_type:
            # Photos/maps/artwork from category
            return await self.get_category_images(commons_category, limit=limit)

        # No filter: category images (photos) + free-text video search
        photos = await self.get_category_images(commons_category, limit=limit)

        videos = await self.search(
            query=site_name,
            content_type=ContentType.VIDEO,
            limit=max(limit // 4, 5),
        )

        return photos + videos

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

        # Determine content type from MIME/title if not specified
        if content_type is None:
            mime = result.get("mime", "")
            if mime.startswith("video/"):
                content_type = ContentType.VIDEO
            else:
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

        # Prefer .webm transcode for videos (browser compatibility)
        media_url = result.get("transcode_url") or url

        return ContentItem(
            id=str(page_id) if page_id else title,
            source=self.connector_id,
            content_type=content_type,
            title=title.replace("File:", ""),
            url=page_url,
            thumbnail_url=thumb_url or url,
            media_url=media_url,
            creator=result.get("artist"),
            date=result.get("date"),
            description=result.get("description"),
            license=result.get("license"),
            license_url=result.get("license_url"),
            attribution=f"{result.get('artist', 'Unknown')} via Wikimedia Commons",
            raw_data=result,
        )
