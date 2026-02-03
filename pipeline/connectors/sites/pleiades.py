"""
Pleiades Connector.

Source #8 from research paper.
Protocol: REST + Bulk
Auth: None
License: CC-BY
Priority: P1

API: https://pleiades.stoa.org/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PleiadesConnector(BaseConnector):
    """Pleiades connector for ancient places."""

    connector_id = "pleiades"
    connector_name = "Pleiades"
    description = "Gazetteer of ancient places"

    content_types = [ContentType.DOCUMENT]

    base_url = "https://pleiades.stoa.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY"
    attribution = "Pleiades"

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
        """Search Pleiades places."""
        try:
            # Use RSS endpoint which returns XML
            params = {
                "SearchableText": query,
                "portal_type": "Place",
                "review_state": "published",
                "b_size": limit,
                "b_start": offset,
            }

            # Use get_raw() since RSS returns XML, not JSON
            response = await self.rest.get_raw("/search_rss", params=params)
            rss_content = response.text

            # Parse the RSS/XML response
            return self._parse_rss(rss_content, limit)

        except Exception as e:
            logger.error(f"Pleiades search failed: {e}")
            return []

    def _parse_rss(self, rss_content: str, limit: int) -> list[ContentItem]:
        """Parse RDF/RSS 1.0 response from Pleiades search.

        Pleiades returns RDF 1.0 format where items are at top level,
        not nested inside channel.
        """
        import xml.etree.ElementTree as ET

        items = []
        try:
            root = ET.fromstring(rss_content)

            # RDF 1.0 namespace

            # In RDF 1.0, items are direct children of rdf:RDF, not inside channel
            # Find all <item> elements (in default namespace)
            for item in root.findall("{http://purl.org/rss/1.0/}item")[:limit]:
                # Get link from rdf:about attribute
                link = item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")

                title = item.findtext("{http://purl.org/rss/1.0/}title", "Unknown Place")
                description = item.findtext("{http://purl.org/rss/1.0/}description", "")

                # Extract place ID from link
                place_id = ""
                if "/places/" in link:
                    place_id = link.split("/places/")[-1].rstrip("/")

                if place_id:
                    content_item = ContentItem(
                        id=f"pleiades:{place_id}",
                        source=self.connector_id,
                        content_type=ContentType.DOCUMENT,
                        title=title,
                        description=description,
                        url=link,
                        license=self.license,
                        attribution=self.attribution,
                    )
                    items.append(content_item)

            logger.info(f"Pleiades: found {len(items)} places")
            return items

        except ET.ParseError as e:
            logger.error(f"Failed to parse Pleiades RSS: {e}")
            return []

    def _parse_json_response(self, response: dict, limit: int) -> list[ContentItem]:
        """Parse JSON response if available."""
        items = []

        # Handle different possible JSON structures
        results = response.get("results", response.get("items", []))

        for result in results[:limit]:
            try:
                place_id = result.get("id", result.get("@id", ""))
                if isinstance(place_id, str) and "/places/" in place_id:
                    place_id = place_id.split("/places/")[-1].rstrip("/")

                title = result.get("title", "Unknown Place")
                description = result.get("description", "")
                url = result.get("url", f"https://pleiades.stoa.org/places/{place_id}")

                # Extract coordinates if available
                lat, lon = None, None
                repr_point = result.get("reprPoint")
                if repr_point and len(repr_point) >= 2:
                    lon, lat = repr_point[0], repr_point[1]

                content_item = ContentItem(
                    id=f"pleiades:{place_id}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=title,
                    description=description,
                    url=url,
                    lat=lat,
                    lon=lon,
                    license=self.license,
                    attribution=self.attribution,
                    raw_data=result,
                )
                items.append(content_item)
            except Exception as e:
                logger.debug(f"Failed to parse JSON result: {e}")

        return items

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific place by ID."""
        try:
            if item_id.startswith("pleiades:"):
                item_id = item_id[9:]

            response = await self.rest.get(f"/places/{item_id}/json")

            if not response:
                return None

            return ContentItem(
                id=f"pleiades:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=response.get("title", "Unknown Place"),
                description=response.get("description"),
                url=f"https://pleiades.stoa.org/places/{item_id}",
                lat=response.get("reprPoint", [None, None])[1],
                lon=response.get("reprPoint", [None, None])[0],
                place_name=response.get("title"),
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Pleiades place {item_id}: {e}")
            return None
