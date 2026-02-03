"""
MediaWiki API Protocol Handler.

Provides access to MediaWiki-based sites including:
- Wikimedia Commons (images, maps)
- Wikipedia (summaries, images)
- Wikidata (structured data)
"""

import asyncio
from typing import Any

import httpx
from loguru import logger


class MediaWikiProtocol:
    """
    MediaWiki API protocol handler.

    Supports:
    - Image search and metadata
    - Page content retrieval
    - Category listing
    - File info (dimensions, license, etc.)
    """

    def __init__(
        self,
        api_url: str = "https://commons.wikimedia.org/w/api.php",
        timeout: float = 30.0,
        rate_limit: float = 5.0,  # Wikimedia allows up to 200 req/s with good UA
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize MediaWiki protocol handler.

        Args:
            api_url: MediaWiki API endpoint URL
            timeout: Request timeout
            rate_limit: Max requests per second
            http_client: Optional shared HTTP client
        """
        self.api_url = api_url
        self.timeout = timeout
        self.rate_limit = rate_limit

        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

    async def __aenter__(self):
        if self._owns_client and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
            self._owns_client = True
        return self._http_client

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        if self.rate_limit <= 0:
            return

        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._last_request_time = asyncio.get_event_loop().time()

    async def _request(
        self,
        params: dict[str, Any],
        method: str = "GET",
    ) -> dict[str, Any]:
        """
        Make API request.

        Args:
            params: API parameters
            method: HTTP method

        Returns:
            API response
        """
        await self._rate_limit()

        # Always include format
        params = {
            "format": "json",
            "formatversion": "2",
            **params,
        }

        headers = {
            "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
            "Accept": "application/json",
        }

        try:
            if method == "GET":
                response = await self.client.get(
                    self.api_url,
                    params=params,
                    headers=headers,
                )
            else:
                response = await self.client.post(
                    self.api_url,
                    data=params,
                    headers=headers,
                )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"MediaWiki API error: {e}")
            raise

    async def search_images(
        self,
        query: str,
        limit: int = 20,
        file_type: str = None,
    ) -> list[dict[str, Any]]:
        """
        Search for images on Wikimedia Commons.

        Args:
            query: Search query
            limit: Maximum results
            file_type: Filter by MIME type (e.g., "bitmap", "drawing")

        Returns:
            List of image info dictionaries
        """
        params = {
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",  # File namespace
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": min(limit, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 800,  # Thumbnail width
        }

        if file_type:
            params["gsrsearch"] = f"filetype:{file_type} {query}"

        result = await self._request(params)

        pages = result.get("query", {}).get("pages", [])

        images = []
        for page in pages:
            imageinfo = page.get("imageinfo", [{}])[0]
            extmetadata = imageinfo.get("extmetadata", {})

            images.append({
                "pageid": page.get("pageid"),
                "title": page.get("title", "").replace("File:", ""),
                "url": imageinfo.get("url"),
                "thumburl": imageinfo.get("thumburl"),
                "width": imageinfo.get("width"),
                "height": imageinfo.get("height"),
                "mime": imageinfo.get("mime"),
                "description": self._extract_metadata(extmetadata, "ImageDescription"),
                "artist": self._extract_metadata(extmetadata, "Artist"),
                "license": self._extract_metadata(extmetadata, "LicenseShortName"),
                "license_url": self._extract_metadata(extmetadata, "LicenseUrl"),
                "date": self._extract_metadata(extmetadata, "DateTimeOriginal"),
            })

        return images

    async def search_category_images(
        self,
        category: str,
        limit: int = 50,
        recursive: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get images from a Commons category.

        Args:
            category: Category name (with or without "Category:" prefix)
            limit: Maximum results
            recursive: Include subcategories

        Returns:
            List of image info dictionaries
        """
        # Normalize category name
        if not category.startswith("Category:"):
            category = f"Category:{category}"

        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": category,
            "gcmtype": "file",
            "gcmlimit": min(limit, 500),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 800,
        }

        result = await self._request(params)
        pages = result.get("query", {}).get("pages", [])

        images = []
        for page in pages:
            imageinfo = page.get("imageinfo", [{}])[0]
            extmetadata = imageinfo.get("extmetadata", {})

            images.append({
                "pageid": page.get("pageid"),
                "title": page.get("title", "").replace("File:", ""),
                "url": imageinfo.get("url"),
                "thumburl": imageinfo.get("thumburl"),
                "width": imageinfo.get("width"),
                "height": imageinfo.get("height"),
                "description": self._extract_metadata(extmetadata, "ImageDescription"),
                "artist": self._extract_metadata(extmetadata, "Artist"),
                "license": self._extract_metadata(extmetadata, "LicenseShortName"),
            })

        return images

    async def get_page_images(
        self,
        title: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get images used on a Wikipedia page.

        Args:
            title: Page title
            limit: Maximum images

        Returns:
            List of image info dictionaries
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "images",
            "imlimit": min(limit, 50),
        }

        result = await self._request(params)
        pages = result.get("query", {}).get("pages", [])

        if not pages:
            return []

        page = pages[0]
        images = page.get("images", [])

        # Get full image info
        if images:
            image_titles = "|".join(img["title"] for img in images[:limit])
            return await self.get_image_info(image_titles)

        return []

    async def get_image_info(
        self,
        titles: str,
    ) -> list[dict[str, Any]]:
        """
        Get detailed info for specific images.

        Args:
            titles: Pipe-separated list of image titles

        Returns:
            List of image info dictionaries
        """
        params = {
            "action": "query",
            "titles": titles,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 800,
        }

        result = await self._request(params)
        pages = result.get("query", {}).get("pages", [])

        images = []
        for page in pages:
            if "imageinfo" not in page:
                continue

            imageinfo = page["imageinfo"][0]
            extmetadata = imageinfo.get("extmetadata", {})

            images.append({
                "pageid": page.get("pageid"),
                "title": page.get("title", "").replace("File:", ""),
                "url": imageinfo.get("url"),
                "thumburl": imageinfo.get("thumburl"),
                "width": imageinfo.get("width"),
                "height": imageinfo.get("height"),
                "description": self._extract_metadata(extmetadata, "ImageDescription"),
                "artist": self._extract_metadata(extmetadata, "Artist"),
                "license": self._extract_metadata(extmetadata, "LicenseShortName"),
            })

        return images

    async def get_page_summary(
        self,
        title: str,
        sentences: int = 3,
    ) -> dict[str, Any] | None:
        """
        Get summary/extract of a Wikipedia page.

        Args:
            title: Page title
            sentences: Number of sentences to extract

        Returns:
            Dictionary with extract and page info
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts|pageimages",
            "exintro": True,
            "exsentences": sentences,
            "explaintext": True,
            "pithumbsize": 400,
        }

        result = await self._request(params)
        pages = result.get("query", {}).get("pages", [])

        if not pages:
            return None

        page = pages[0]
        if "missing" in page:
            return None

        return {
            "pageid": page.get("pageid"),
            "title": page.get("title"),
            "extract": page.get("extract"),
            "thumbnail": page.get("thumbnail", {}).get("source"),
            "pageurl": f"https://en.wikipedia.org/wiki/{page.get('title', '').replace(' ', '_')}",
        }

    async def search_historical_maps(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search for historical maps on Wikimedia Commons.

        Args:
            query: Search query (e.g., empire name)
            limit: Maximum results

        Returns:
            List of map image dictionaries
        """
        # Search with map-specific terms
        search_terms = f"{query} (map OR carte OR historical OR ancient)"

        params = {
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": f"filetype:bitmap {search_terms}",
            "gsrlimit": min(limit * 2, 50),  # Get extra to filter
            "prop": "imageinfo|categories",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 800,
            "cllimit": 10,
        }

        result = await self._request(params)
        pages = result.get("query", {}).get("pages", [])

        maps = []
        for page in pages:
            title = page.get("title", "").lower()
            categories = [c.get("title", "").lower() for c in page.get("categories", [])]

            # Filter for actual maps
            is_map = (
                "map" in title or
                any("map" in cat for cat in categories) or
                any("carte" in cat for cat in categories)
            )

            if not is_map:
                continue

            imageinfo = page.get("imageinfo", [{}])[0]
            extmetadata = imageinfo.get("extmetadata", {})

            maps.append({
                "pageid": page.get("pageid"),
                "title": page.get("title", "").replace("File:", ""),
                "url": imageinfo.get("url"),
                "thumburl": imageinfo.get("thumburl"),
                "width": imageinfo.get("width"),
                "height": imageinfo.get("height"),
                "description": self._extract_metadata(extmetadata, "ImageDescription"),
                "date": self._extract_metadata(extmetadata, "DateTimeOriginal"),
                "license": self._extract_metadata(extmetadata, "LicenseShortName"),
            })

            if len(maps) >= limit:
                break

        return maps

    def _extract_metadata(
        self,
        extmetadata: dict[str, Any],
        key: str,
    ) -> str | None:
        """Extract value from extmetadata, stripping HTML."""
        if key not in extmetadata:
            return None

        value = extmetadata[key].get("value", "")

        # Strip HTML tags (simple approach)
        import re
        clean = re.sub(r"<[^>]+>", "", value)
        return clean.strip() if clean else None
