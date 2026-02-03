"""
Metropolitan Museum of Art Connector.

The Met provides a robust, free REST API with CC0-licensed images.
One of the best museum APIs with high rate limits (80 req/s).

API docs: https://metmuseum.github.io/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# Department IDs for filtering
ANCIENT_DEPARTMENTS = {
    3: "Ancient Near Eastern Art",
    6: "Asian Art",
    10: "Egyptian Art",
    13: "Greek and Roman Art",
    14: "Islamic Art",
    16: "Medieval Art",
}


@ConnectorRegistry.register
class MetMuseumConnector(BaseConnector):
    """
    Metropolitan Museum of Art connector.

    Provides access to 500K+ artworks from The Met collection.
    All images marked isPublicDomain are CC0.
    """

    connector_id = "met_museum"
    connector_name = "Metropolitan Museum of Art"
    description = "Artworks and artifacts from The Metropolitan Museum of Art"

    content_types = [ContentType.ARTIFACT, ContentType.ARTWORK]

    base_url = "https://collectionapi.metmuseum.org/public/collection/v1"
    website_url = "https://www.metmuseum.org"
    protocol = ProtocolType.REST
    rate_limit = 20.0  # Met allows 80 req/s, we're conservative
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC0"
    attribution = "The Metropolitan Museum of Art"

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
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search The Met collection.

        Args:
            query: Search query
            content_type: Filter by content type
            limit: Maximum results
            offset: Pagination offset
            **kwargs: Additional parameters:
                - has_images: Only return objects with images (default True)
                - department_id: Filter by department

        Returns:
            List of ContentItem objects
        """
        if not query.strip():
            return []

        has_images = kwargs.get("has_images", True)
        department_id = kwargs.get("department_id")

        params = {
            "q": query,
            "hasImages": str(has_images).lower(),
        }

        if department_id:
            params["departmentId"] = department_id

        try:
            async with self.rest:
                # First, get object IDs
                response = await self.rest.get("search", params)

            object_ids = response.get("objectIDs", [])

            if not object_ids:
                return []

            logger.debug(f"Met: Found {len(object_ids)} objects for '{query}'")

            # Limit the IDs we'll fetch details for
            object_ids = object_ids[offset:offset + limit * 2]

            # Fetch object details
            items = []
            async with self.rest:
                for obj_id in object_ids:
                    if len(items) >= limit:
                        break

                    try:
                        obj = await self.rest.get(f"objects/{obj_id}")
                        item = self._parse_object(obj)
                        if item:
                            items.append(item)
                    except Exception as e:
                        logger.debug(f"Met: Failed to fetch object {obj_id}: {e}")
                        continue

            logger.info(f"Met: Returning {len(items)} items for '{query}'")
            return items

        except Exception as e:
            logger.error(f"Met search error: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get a specific artwork by its object ID."""
        try:
            async with self.rest:
                obj = await self.rest.get(f"objects/{item_id}")

            return self._parse_object(obj)

        except Exception as e:
            logger.error(f"Met get_item error: {e}")
            return None

    async def get_by_period(
        self,
        period_start: int,
        period_end: int,
        culture: str | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """Get artworks from a time period."""
        # Met API doesn't support date range search directly
        # Build a query using period/culture info
        if culture:
            query = f"{culture} ancient"
        else:
            # Use approximate era
            if period_start < -2000:
                query = "ancient near east bronze age"
            elif period_start < -500:
                query = "ancient greek archaic classical"
            elif period_start < 500:
                query = "roman empire hellenistic"
            else:
                query = "medieval byzantine"

        return await self.search(query=query, limit=limit, **kwargs)

    async def get_by_empire(
        self,
        empire_name: str,
        period_name: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """Get artworks for an empire/civilization."""
        # Map common empire names to Met search terms
        search_mappings = {
            "roman": "roman",
            "greek": "greek",
            "egyptian": "egyptian",
            "persian": "persian achaemenid",
            "byzantine": "byzantine",
            "assyrian": "assyrian",
            "babylonian": "babylonian mesopotamian",
            "ottoman": "islamic ottoman",
            "macedonian": "greek hellenistic",
        }

        # Find best match
        empire_lower = empire_name.lower()
        search_term = empire_name

        for key, value in search_mappings.items():
            if key in empire_lower:
                search_term = value
                break

        return await self.search(
            query=search_term,
            content_type=content_type,
            limit=limit,
            **kwargs,
        )

    async def get_by_department(
        self,
        department_id: int,
        limit: int = 50,
    ) -> list[ContentItem]:
        """Get artworks from a specific department."""
        try:
            async with self.rest:
                response = await self.rest.get("objects", {"departmentIds": department_id})

            object_ids = response.get("objectIDs", [])[:limit * 2]

            items = []
            async with self.rest:
                for obj_id in object_ids:
                    if len(items) >= limit:
                        break

                    try:
                        obj = await self.rest.get(f"objects/{obj_id}")
                        item = self._parse_object(obj)
                        if item:
                            items.append(item)
                    except Exception:
                        continue

            return items

        except Exception as e:
            logger.error(f"Met department error: {e}")
            return []

    def _parse_object(self, obj: dict) -> ContentItem | None:
        """Parse Met API object into ContentItem."""
        object_id = obj.get("objectID")
        title = obj.get("title", "Untitled")

        if not object_id:
            return None

        # Only include public domain images
        if not obj.get("isPublicDomain"):
            return None

        # Get image URL
        primary_image = obj.get("primaryImage")
        small_image = obj.get("primaryImageSmall")

        if not primary_image and not small_image:
            return None

        # Determine content type
        classification = obj.get("classification", "").lower()
        content_type = ContentType.ARTIFACT

        if any(word in classification for word in ["painting", "drawing", "print"]):
            content_type = ContentType.ARTWORK

        # Extract date
        date = obj.get("objectDate")
        date_begin = obj.get("objectBeginDate")

        # Build source URL
        url = obj.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{object_id}"

        return ContentItem(
            id=str(object_id),
            source=self.connector_id,
            content_type=content_type,
            title=title,
            url=url,
            thumbnail_url=small_image or primary_image,
            media_url=primary_image,
            creator=obj.get("artistDisplayName"),
            date=date,
            date_numeric=date_begin,
            period=obj.get("period"),
            culture=obj.get("culture"),
            object_type=obj.get("objectName"),
            material=obj.get("medium"),
            dimensions=obj.get("dimensions"),
            museum="The Metropolitan Museum of Art",
            place_name=obj.get("city"),
            country=obj.get("country"),
            license="CC0",
            attribution="The Metropolitan Museum of Art",
            raw_data=obj,
        )
