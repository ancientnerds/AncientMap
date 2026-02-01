"""
Sketchfab 3D Models Connector.

Migrated from: ancient-nerds-map/src/services/sketchfabService.ts

Searches Sketchfab for 3D models of archaeological sites and artifacts.
Features:
- Relevance scoring based on site name matching
- Archaeology keyword boosting
- Cultural heritage category filtering
- Human-created models only (excludes AI-generated)
"""

from typing import List, Optional
from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.types import ContentType, ContentItem, AuthType, ProtocolType
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.protocols.rest import RestProtocol


# Minimum relevance score to include a model (0-100)
# Lowered to 10 since Sketchfab already filters by cultural-heritage-history category
MIN_RELEVANCE_SCORE = 10

# Archaeology-related keywords that boost relevance
ARCHAEOLOGY_KEYWORDS = [
    "ancient", "archaeological", "archaeology", "ruins", "temple", "tomb",
    "pyramid", "monument", "historic", "historical", "heritage", "excavation",
    "artifact", "artefact", "relic", "antique", "medieval", "roman", "greek",
    "egyptian", "mesopotamian", "byzantine", "ottoman", "islamic", "christian",
    "mosque", "church", "cathedral", "palace", "fortress", "castle", "citadel"
]


@ConnectorRegistry.register
class SketchfabConnector(BaseConnector):
    """
    Sketchfab 3D model connector.

    Provides access to the Sketchfab API for cultural heritage 3D models.
    """

    connector_id = "sketchfab"
    connector_name = "Sketchfab"
    description = "3D models of archaeological sites, artifacts, and historical objects"

    content_types = [ContentType.MODEL_3D]

    base_url = "https://api.sketchfab.com/v3"
    protocol = ProtocolType.REST
    rate_limit = 2.0  # Sketchfab can rate limit
    requires_auth = False  # Public API, OAuth only for uploads
    auth_type = AuthType.NONE

    license = "Varies by model"
    attribution = "3D models from Sketchfab"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(
            base_url=self.base_url,
            rate_limit=self.rate_limit,
        )

    async def search(
        self,
        query: str,
        content_type: Optional[ContentType] = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> List[ContentItem]:
        """
        Search for 3D models matching query.

        Args:
            query: Search query (site name, artifact type, etc.)
            content_type: Ignored (always returns 3D models)
            limit: Maximum results
            offset: Pagination offset
            **kwargs: Additional parameters:
                - location: Location string for context
                - country: Country for geographic matching

        Returns:
            List of ContentItem objects for 3D models
        """
        if not query.strip():
            return []

        location = kwargs.get("location", "")
        country = kwargs.get("country") or self.extract_country(location)

        # Extract primary search name
        primary_name = self.extract_primary_name(query)
        search_term = f"{primary_name} {country}".strip() if country else primary_name

        params = {
            "type": "models",
            "q": search_term,
            "sort_by": "-likeCount",
            "count": min(limit * 2, 50),  # Get extra for filtering
            "categories": "cultural-heritage-history",
            "ai_generated": "false",
        }

        try:
            async with self.rest:
                response = await self.rest.get("search", params)

            # Handle None or non-dict response
            if not response or not isinstance(response, dict):
                logger.warning(f"Sketchfab: Invalid API response for '{search_term}'")
                return []

            results = response.get("results", [])
            if not results:
                return []

            logger.debug(f"Sketchfab: Found {len(results)} models for '{search_term}'")

            # Score and filter models
            items = []
            for result in results:
                try:
                    item = self._parse_result(result, query, primary_name, country)
                    if item:
                        logger.debug(f"Sketchfab: Model '{item.title}' scored {item.relevance_score}")
                        if item.relevance_score >= MIN_RELEVANCE_SCORE:
                            items.append(item)
                except Exception as parse_err:
                    logger.warning(f"Sketchfab: Failed to parse model: {parse_err}")

            # Sort by relevance and limit
            items.sort(key=lambda x: x.relevance_score, reverse=True)
            items = items[:limit]

            logger.info(f"Sketchfab: Returning {len(items)} relevant models for '{query}'")
            return items

        except Exception as e:
            logger.error(f"Sketchfab search error: {e}")
            return []

    async def get_item(self, item_id: str) -> Optional[ContentItem]:
        """Get a specific 3D model by its UID."""
        try:
            async with self.rest:
                response = await self.rest.get(f"models/{item_id}")

            return self._parse_result(response, "", "", "")

        except Exception as e:
            logger.error(f"Sketchfab get_item error: {e}")
            return None

    async def get_by_site(
        self,
        site_name: str,
        location: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        content_type: Optional[ContentType] = None,
        limit: int = 20,
        **kwargs,
    ) -> List[ContentItem]:
        """Get 3D models for an archaeological site."""
        return await self.search(
            query=site_name,
            limit=limit,
            location=location or "",
            **kwargs,
        )

    def _parse_result(
        self,
        result: dict,
        original_query: str,
        primary_name: str,
        country: str,
    ) -> Optional[ContentItem]:
        """Parse Sketchfab API result into ContentItem."""
        if not result or not isinstance(result, dict):
            return None

        uid = result.get("uid")
        name = result.get("name", "Untitled")

        if not uid:
            return None

        # Safe nested access - handle None values from API
        thumbnails_obj = result.get("thumbnails") or {}
        thumbnails = thumbnails_obj.get("images", []) if isinstance(thumbnails_obj, dict) else []
        thumbnail = self._select_thumbnail(thumbnails)

        # Use Sketchfab's default thumbnail URL as fallback
        if not thumbnail:
            thumbnail = f"https://media.sketchfab.com/models/{uid}/thumbnails/initial/thumbnail.jpeg"

        # Safe user access - handle None values
        user = result.get("user") or {}
        if not isinstance(user, dict):
            user = {}
        creator = user.get("displayName") or user.get("username") or "Unknown"
        username = user.get("username", "")
        creator_url = user.get("profileUrl") or f"https://sketchfab.com/{username}"

        # Calculate relevance score
        score = self.score_relevance(
            item_title=name,
            search_query=original_query,
            primary_name=primary_name,
            country=country,
            boost_keywords=ARCHAEOLOGY_KEYWORDS,
        )

        # Safe license access - handle None values
        license_obj = result.get("license") or {}
        license_label = license_obj.get("label") if isinstance(license_obj, dict) else None

        return ContentItem(
            id=uid,
            source=self.connector_id,
            content_type=ContentType.MODEL_3D,
            title=name,
            url=f"https://sketchfab.com/3d-models/{uid}",
            thumbnail_url=thumbnail,
            embed_url=f"https://sketchfab.com/models/{uid}/embed?autostart=1&ui_controls=1&ui_infos=0&ui_watermark=0",
            creator=creator,
            creator_url=creator_url,
            view_count=result.get("viewCount", 0),
            like_count=result.get("likeCount", 0),
            relevance_score=score,
            license=license_label,
            raw_data=result,
        )

    def _select_thumbnail(self, thumbnails: list) -> Optional[str]:
        """Select best thumbnail from available options."""
        if not thumbnails:
            return None

        # Prefer ~640px width
        for thumb in thumbnails:
            width = thumb.get("width", 0)
            if 480 <= width <= 800:
                return thumb.get("url")

        # Fall back to any thumbnail >= 200px
        for thumb in thumbnails:
            if thumb.get("width", 0) >= 200:
                return thumb.get("url")

        # Last resort: first thumbnail
        return thumbnails[0].get("url") if thumbnails else None
