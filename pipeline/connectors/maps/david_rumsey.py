"""
David Rumsey Map Collection Connector.

Migrated from: ancient-nerds-map/src/services/ancientMapsService.ts

Searches the David Rumsey Map Collection for historical maps.
Features:
- Relevance scoring based on site/location matching
- Map keyword boosting
- Date extraction from metadata
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# Minimum relevance score to include a map (0-100)
MIN_RELEVANCE_SCORE = 25

# Map-related keywords that boost relevance
MAP_KEYWORDS = [
    "map", "carte", "mapa", "karte", "plan", "atlas", "chart",
    "ancient", "antique", "historical", "historic", "old",
    "region", "territory", "empire", "kingdom", "province"
]


@ConnectorRegistry.register
class DavidRumseyConnector(BaseConnector):
    """
    David Rumsey Map Collection connector.

    Provides access to historical maps from the David Rumsey collection.
    """

    connector_id = "david_rumsey"
    connector_name = "David Rumsey Map Collection"
    description = "Historical maps from the David Rumsey Map Collection"

    content_types = [ContentType.MAP]

    base_url = "https://www.davidrumsey.com/luna/servlet/as"
    website_url = "https://www.davidrumsey.com"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Non-commercial use"
    attribution = "David Rumsey Map Collection, David Rumsey Map Center, Stanford Libraries"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(
            base_url=self.base_url,
            rate_limit=self.rate_limit,
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search for historical maps matching query.

        Args:
            query: Search query (site name, region, etc.)
            content_type: Ignored (always returns maps)
            limit: Maximum results
            offset: Pagination offset
            **kwargs: Additional parameters:
                - location: Location string for context
                - country: Country for geographic matching

        Returns:
            List of ContentItem objects for maps
        """
        if not query.strip():
            return []

        location = kwargs.get("location", "")
        country = kwargs.get("country") or self.extract_country(location)

        # Extract primary search name
        primary_name = self.extract_primary_name(query)
        search_term = f"{primary_name} {country}".strip() if country else primary_name

        params = {
            "q": search_term,
            "os": offset,
            "bs": limit,
        }

        try:
            async with self.rest:
                response = await self.rest.get("search", params)

            results = response.get("results", [])
            if not results:
                return []

            logger.debug(f"David Rumsey: Found {len(results)} maps for '{search_term}'")

            # Score and filter maps
            items = []
            for result in results:
                item = self._parse_result(result, query, primary_name, country)
                if item and item.relevance_score >= MIN_RELEVANCE_SCORE:
                    items.append(item)

            # Sort by relevance
            items.sort(key=lambda x: x.relevance_score, reverse=True)

            logger.info(f"David Rumsey: Returning {len(items)} relevant maps for '{query}'")
            return items

        except Exception as e:
            logger.error(f"David Rumsey search error: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get a specific map by its ID."""
        # David Rumsey doesn't have a direct item API
        # Would need to search by ID
        logger.warning("David Rumsey get_item not implemented")
        return None

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
        """Get historical maps for an archaeological site."""
        return await self.search(
            query=site_name,
            limit=limit,
            location=location or "",
            **kwargs,
        )

    async def get_by_empire(
        self,
        empire_name: str,
        period_name: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """Get historical maps for an empire."""
        search_term = period_name or empire_name
        return await self.search(
            query=f"{search_term} map",
            limit=limit,
            **kwargs,
        )

    def _parse_result(
        self,
        result: dict,
        original_query: str,
        primary_name: str,
        country: str,
    ) -> ContentItem | None:
        """Parse David Rumsey API result into ContentItem."""
        item_id = result.get("id")
        title = result.get("displayName", "Untitled")

        if not item_id:
            return None

        # Get thumbnail URLs
        thumbnail = result.get("urlSize2", "")
        full_image = result.get("urlSize4") or result.get("urlSize2", "")

        if not thumbnail:
            return None

        # Extract date from fieldValues
        date = None
        field_values = result.get("fieldValues", [])
        for field in field_values:
            if field.get("fieldName") == "Date":
                date = field.get("value")
                break

        # Build web URL
        url = f"https://www.davidrumsey.com/luna/servlet/detail/{item_id}"

        # Calculate relevance score
        score = self.score_relevance(
            item_title=title,
            search_query=original_query,
            primary_name=primary_name,
            country=country,
            boost_keywords=MAP_KEYWORDS,
        )

        return ContentItem(
            id=item_id,
            source=self.connector_id,
            content_type=ContentType.MAP,
            title=title,
            url=url,
            thumbnail_url=thumbnail,
            media_url=full_image,
            date=date,
            relevance_score=score,
            license=self.license,
            attribution=self.attribution,
            raw_data=result,
        )
