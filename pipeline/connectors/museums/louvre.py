"""
Louvre Museum Connector.

Source #3 from research paper.
Protocol: HTML scraping (no public JSON API)
Auth: None
License: Terms of Use
Priority: P2

Website: https://collections.louvre.fr/

Note: The Louvre does not provide a public JSON/REST API.
Their collections can be browsed at collections.louvre.fr but requires
HTML parsing. This connector extracts data from the search results page.
"""

import re

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class LouvreConnector(BaseConnector):
    """Louvre Museum connector.

    Extracts collection data from the Louvre Collections website.
    Note: Uses HTML parsing as there is no public JSON API.
    """

    connector_id = "louvre"
    connector_name = "Louvre Museum"
    description = "Artworks and artifacts from the Louvre Museum, Paris"

    content_types = [ContentType.ARTIFACT, ContentType.ARTWORK]

    base_url = "https://collections.louvre.fr"
    website_url = "https://www.louvre.fr"
    protocol = ProtocolType.REST
    rate_limit = 1.0  # Be gentle - scraping
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Terms of Use"
    attribution = "Musée du Louvre"

    # No public JSON API - would require HTML scraping which is fragile
    available = False
    unavailable_reason = "No public API - collections.louvre.fr has no JSON endpoint"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(
            base_url=self.base_url,
            rate_limit=self.rate_limit,
            headers={"Accept-Language": "en,fr"}
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Louvre collection via HTML parsing.

        The Louvre collections site doesn't have a JSON API, so we parse
        the HTML search results page.
        """
        try:
            page = (offset // 24) + 1 if limit > 0 else 1  # Louvre uses 24 items per page

            # Get search results page
            response = await self.rest.get_raw(
                "/recherche",
                params={"q": query, "page": page},
            )

            html_content = response.text

            # Parse results from HTML
            items = self._parse_search_results(html_content, limit)
            return items

        except Exception as e:
            logger.error(f"Louvre search failed: {e}")
            return []

    def _parse_search_results(self, html: str, limit: int) -> list[ContentItem]:
        """Parse search results from Louvre collections HTML page."""
        items = []

        try:
            # Find result cards - they are in <article class="card">
            # Pattern: <article class="card">...<a href="/en/oeuvre/...">...<img src="...">...
            card_pattern = re.compile(
                r'<article[^>]*class="[^"]*card[^"]*"[^>]*>(.*?)</article>',
                re.DOTALL | re.IGNORECASE
            )

            for match in card_pattern.finditer(html):
                if len(items) >= limit:
                    break

                card_html = match.group(1)

                try:
                    # Extract URL and ID
                    url_match = re.search(r'href="(/(?:en/)?oeuvre/[^"]+)"', card_html)
                    if not url_match:
                        continue

                    relative_url = url_match.group(1)
                    full_url = f"{self.base_url}{relative_url}"

                    # Extract ID from URL (e.g., /en/oeuvre/ark:/53355/cl010062370)
                    id_match = re.search(r'ark:/(\d+/[a-z0-9]+)', relative_url)
                    item_id = id_match.group(1) if id_match else relative_url.split('/')[-1]

                    # Extract title
                    title_match = re.search(
                        r'<h\d[^>]*class="[^"]*card__title[^"]*"[^>]*>(.*?)</h\d>',
                        card_html, re.DOTALL
                    )
                    title = "Unknown artwork"
                    if title_match:
                        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

                    # Extract thumbnail
                    thumbnail = None
                    img_match = re.search(r'<img[^>]+src="([^"]+)"', card_html)
                    if img_match:
                        thumbnail = img_match.group(1)
                        if thumbnail.startswith('/'):
                            thumbnail = f"{self.base_url}{thumbnail}"

                    # Extract subtitle/description (often contains artist, date)
                    desc_match = re.search(
                        r'<p[^>]*class="[^"]*card__subtitle[^"]*"[^>]*>(.*?)</p>',
                        card_html, re.DOTALL
                    )
                    description = None
                    if desc_match:
                        description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

                    item = ContentItem(
                        id=f"louvre:{item_id}",
                        source=self.connector_id,
                        content_type=ContentType.ARTWORK,
                        title=title,
                        description=description,
                        url=full_url,
                        thumbnail_url=thumbnail,
                        museum="Musée du Louvre",
                        license=self.license,
                        attribution=self.attribution,
                    )
                    items.append(item)

                except Exception as e:
                    logger.debug(f"Failed to parse Louvre card: {e}")
                    continue

            logger.info(f"Louvre: parsed {len(items)} results")
            return items

        except Exception as e:
            logger.error(f"Failed to parse Louvre HTML: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific artwork by ID."""
        try:
            if item_id.startswith("louvre:"):
                item_id = item_id[7:]

            # Construct URL for the artwork page
            # Handle both ark IDs and simple IDs
            if "ark:" in item_id or "/" in item_id:
                url_path = f"/en/oeuvre/ark:/{item_id}"
            else:
                url_path = f"/en/oeuvre/{item_id}"

            response = await self.rest.get_raw(url_path)
            html = response.text

            # Extract title from page
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            title = "Unknown artwork"
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            # Extract main image
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
                id=f"louvre:{item_id}",
                source=self.connector_id,
                content_type=ContentType.ARTWORK,
                title=title,
                description=description,
                url=f"{self.base_url}{url_path}",
                thumbnail_url=thumbnail,
                museum="Musée du Louvre",
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get Louvre item {item_id}: {e}")
            return None
