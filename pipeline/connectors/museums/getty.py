"""
Getty Museum Connector.

Source #4 from research paper.
Protocol: HTML parsing (API requires JS)
Auth: None
License: CC0
Priority: P2

Website: https://www.getty.edu/art/collection/

Note: The Getty provides a data.getty.edu API but its documentation
requires JavaScript. This connector uses HTML parsing from the
collection website.
"""

import json
import re

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class GettyMuseumConnector(BaseConnector):
    """Getty Museum connector for artworks and artifacts.

    Extracts collection data from the Getty Museum website.
    Uses HTML parsing since the API documentation requires JavaScript.
    """

    connector_id = "getty_museum"
    connector_name = "Getty Museum"
    description = "Artworks and artifacts from the J. Paul Getty Museum"

    content_types = [ContentType.ARTIFACT, ContentType.ARTWORK]

    base_url = "https://www.getty.edu"
    website_url = "https://www.getty.edu"
    protocol = ProtocolType.REST
    rate_limit = 1.0  # Be gentle when scraping
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC0"
    attribution = "J. Paul Getty Museum"

    # data.getty.edu API docs require JavaScript, no working REST endpoint found
    available = False
    unavailable_reason = "No public search API - data.getty.edu requires JavaScript"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(
            base_url=self.base_url,
            rate_limit=self.rate_limit,
            headers={"Accept": "text/html,application/xhtml+xml"}
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Getty Museum collection.

        The Getty website uses a JavaScript-based search interface.
        We parse the initial HTML which may contain embedded JSON data.
        """
        try:
            page = (offset // 20) + 1 if limit > 0 else 1

            # Try the collection search page
            response = await self.rest.get_raw(
                "/art/collection/search",
                params={"query": query, "page": page},
            )

            html_content = response.text

            # Try to extract data from embedded JSON (React state)
            items = self._parse_embedded_json(html_content, limit)
            if items:
                return items

            # Fallback to HTML parsing
            return self._parse_search_results(html_content, limit)

        except Exception as e:
            logger.error(f"Getty Museum search failed: {e}")
            return []

    def _parse_embedded_json(self, html: str, limit: int) -> list[ContentItem]:
        """Try to extract data from embedded JSON in the page."""
        items = []

        try:
            # Look for __NEXT_DATA__ or similar embedded state
            json_patterns = [
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'"results"\s*:\s*(\[.*?\])',
            ]

            for pattern in json_patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))

                        # Navigate to results based on pattern matched
                        results = []
                        if isinstance(data, list):
                            results = data
                        elif isinstance(data, dict):
                            # Try common paths
                            results = (
                                data.get("props", {}).get("pageProps", {}).get("results", []) or
                                data.get("results", []) or
                                data.get("objects", []) or
                                data.get("items", [])
                            )

                        for result in results[:limit]:
                            item = self._parse_json_result(result)
                            if item:
                                items.append(item)

                        if items:
                            logger.info(f"Getty: extracted {len(items)} items from embedded JSON")
                            return items

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.debug(f"Getty JSON extraction failed: {e}")

        return items

    def _parse_json_result(self, result: dict) -> ContentItem | None:
        """Parse a JSON result object."""
        try:
            item_id = result.get("id") or result.get("objectId") or result.get("uuid", "")
            title = result.get("title") or result.get("name") or "Unknown artwork"

            # Extract URL
            url = result.get("url")
            if not url and item_id:
                url = f"https://www.getty.edu/art/collection/object/{item_id}"

            # Extract thumbnail
            thumbnail = (
                result.get("thumbnail") or
                result.get("primaryImage") or
                result.get("image", {}).get("url") if isinstance(result.get("image"), dict) else result.get("image")
            )

            return ContentItem(
                id=f"getty_museum:{item_id}",
                source=self.connector_id,
                content_type=ContentType.ARTWORK,
                title=title,
                description=result.get("description") or result.get("summary"),
                url=url,
                thumbnail_url=thumbnail,
                creator=result.get("artist") or result.get("maker"),
                date=result.get("date") or result.get("dateText"),
                museum="J. Paul Getty Museum",
                license=self.license,
                attribution=self.attribution,
                raw_data=result,
            )
        except Exception as e:
            logger.debug(f"Failed to parse Getty JSON result: {e}")
            return None

    def _parse_search_results(self, html: str, limit: int) -> list[ContentItem]:
        """Parse search results from HTML when JSON extraction fails."""
        items = []

        try:
            # Look for artwork cards in the HTML
            # Pattern varies by site design but often includes object links
            re.compile(
                r'<a[^>]+href="(/art/collection/object/[^"]+)"[^>]*>.*?'
                r'(?:<img[^>]+src="([^"]+)"[^>]*>)?.*?'
                r'(?:<[^>]+class="[^"]*title[^"]*"[^>]*>([^<]+)<)?',
                re.DOTALL | re.IGNORECASE
            )

            # Also try to find object URLs
            url_pattern = re.compile(r'/art/collection/object/([A-Z0-9]+)')

            seen_ids = set()
            for match in url_pattern.finditer(html):
                if len(items) >= limit:
                    break

                object_id = match.group(1)
                if object_id in seen_ids:
                    continue
                seen_ids.add(object_id)

                # Try to find more info around this link
                context_start = max(0, match.start() - 500)
                context_end = min(len(html), match.end() + 500)
                context = html[context_start:context_end]

                # Extract title
                title_match = re.search(
                    r'(?:title|alt|aria-label)="([^"]+)"',
                    context, re.IGNORECASE
                )
                title = title_match.group(1) if title_match else f"Getty Object {object_id}"

                # Extract thumbnail
                thumbnail = None
                img_match = re.search(r'<img[^>]+src="([^"]+)"', context)
                if img_match:
                    thumbnail = img_match.group(1)
                    if thumbnail.startswith('/'):
                        thumbnail = f"{self.base_url}{thumbnail}"

                item = ContentItem(
                    id=f"getty_museum:{object_id}",
                    source=self.connector_id,
                    content_type=ContentType.ARTWORK,
                    title=title,
                    url=f"https://www.getty.edu/art/collection/object/{object_id}",
                    thumbnail_url=thumbnail,
                    museum="J. Paul Getty Museum",
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            if items:
                logger.info(f"Getty: parsed {len(items)} results from HTML")

            return items

        except Exception as e:
            logger.error(f"Failed to parse Getty HTML: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific artwork by ID."""
        try:
            if item_id.startswith("getty_museum:"):
                item_id = item_id[13:]

            response = await self.rest.get_raw(f"/art/collection/object/{item_id}")
            html = response.text

            # Extract title from page
            title_match = re.search(
                r'<h1[^>]*>(.*?)</h1>',
                html, re.DOTALL
            )
            title = "Unknown artwork"
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            # Extract image from og:image meta
            thumbnail = None
            img_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if img_match:
                thumbnail = img_match.group(1)

            # Extract description from meta
            desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
            description = None
            if desc_match:
                description = desc_match.group(1)

            return ContentItem(
                id=f"getty_museum:{item_id}",
                source=self.connector_id,
                content_type=ContentType.ARTWORK,
                title=title,
                description=description,
                url=f"https://www.getty.edu/art/collection/object/{item_id}",
                thumbnail_url=thumbnail,
                museum="J. Paul Getty Museum",
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get Getty item {item_id}: {e}")
            return None
