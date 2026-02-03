"""
MorphoSource Connector.

Source #34 from research paper.
Protocol: REST
Auth: None (for public data)
License: Open (varies by item)
Priority: P2

API: https://www.morphosource.org/catalog/media.json
Documentation: https://morphosource.stoplight.io/docs/morphosource-api/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class MorphoSourceConnector(BaseConnector):
    """MorphoSource connector for 3D biological and archaeological specimens.

    MorphoSource is a repository for 3D models of biological and archaeological
    specimens. The API returns media records in a nested response structure.
    """

    connector_id = "morphosource"
    connector_name = "MorphoSource"
    description = "3D scans of biological and archaeological specimens"

    content_types = [ContentType.MODEL_3D, ContentType.ARTIFACT]

    base_url = "https://www.morphosource.org"
    website_url = "https://www.morphosource.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    available = False
    unavailable_reason = "MorphoSource API returns mostly biological specimens, not archaeological content"

    license = "Varies"
    attribution = "MorphoSource"

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
        """Search MorphoSource media catalog.

        Uses the catalog/media endpoint which returns a response with
        nested "response.media" array containing media records.
        """
        try:
            page = offset // limit + 1 if limit > 0 else 1
            params = {
                "search_text": query,
                "per_page": limit,
                "page": page,
            }

            response = await self.rest.get("/catalog/media.json", params=params)

            if not response:
                logger.warning("MorphoSource returned empty response")
                return []

            # MorphoSource returns nested structure: {"response": {"media": [...]}}
            media_list = []
            if isinstance(response, dict):
                if "response" in response:
                    media_list = response["response"].get("media", [])
                elif "media" in response:
                    media_list = response["media"]
                elif "results" in response:
                    media_list = response["results"]

            if not media_list:
                logger.debug(f"No MorphoSource media found for query: {query}")
                return []

            items = []
            for media in media_list:
                try:
                    item = self._parse_media_item(media)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse MorphoSource media: {e}")

            logger.info(f"MorphoSource: found {len(items)} results for '{query}'")
            return items

        except Exception as e:
            logger.error(f"MorphoSource search failed: {e}")
            return []

    def _parse_media_item(self, media: dict) -> ContentItem | None:
        """Parse a MorphoSource media record.

        Media records have fields as arrays (e.g., "id": ["000812487"]).
        """
        try:
            # Helper to get first value from array or string
            def first_val(field):
                val = media.get(field)
                if isinstance(val, list):
                    return val[0] if val else None
                return val

            media_id = first_val("id") or ""
            title = first_val("title") or first_val("physical_object_title") or "Unknown specimen"

            # Build description from available metadata
            desc_parts = []
            taxonomy = first_val("physical_object_taxonomy_name")
            if taxonomy:
                desc_parts.append(f"Species: {taxonomy}")
            media_type = first_val("media_type")
            if media_type:
                desc_parts.append(f"Type: {media_type}")
            org = first_val("physical_object_organization")
            if org:
                desc_parts.append(f"From: {org}")
            short_desc = first_val("short_description") or first_val("description")
            if short_desc and len(short_desc) < 500:
                desc_parts.append(short_desc)

            description = " | ".join(desc_parts) if desc_parts else None

            # Get ARK identifier for URL
            ark = first_val("ark")
            if ark:
                url = f"https://www.morphosource.org/{ark.replace('ark:/', 'ark:/')}"
            else:
                url = f"https://www.morphosource.org/concern/media/{media_id}"

            # License info
            license_url = first_val("license")
            license_name = self.license
            if license_url and "creativecommons" in license_url:
                if "by-nc" in license_url:
                    license_name = "CC BY-NC 4.0"
                elif "by-sa" in license_url:
                    license_name = "CC BY-SA 4.0"
                elif "by" in license_url:
                    license_name = "CC BY 4.0"

            return ContentItem(
                id=f"morphosource:{media_id}",
                source=self.connector_id,
                content_type=ContentType.MODEL_3D,
                title=title,
                description=description,
                url=url,
                creator=first_val("creator"),
                license=license_name,
                license_url=license_url,
                attribution=self.attribution,
                raw_data=media,
            )

        except Exception as e:
            logger.debug(f"Error parsing MorphoSource media: {e}")
            return None

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific media by ID."""
        try:
            if item_id.startswith("morphosource:"):
                item_id = item_id[13:]

            # Search for the specific item by ID
            params = {"search_text": item_id, "per_page": 1}
            response = await self.rest.get("/catalog/media.json", params=params)

            if not response:
                return None

            # Extract media from nested response
            media_list = []
            if isinstance(response, dict):
                if "response" in response:
                    media_list = response["response"].get("media", [])
                elif "media" in response:
                    media_list = response["media"]

            if not media_list:
                return None

            return self._parse_media_item(media_list[0])

        except Exception as e:
            logger.error(f"Failed to get MorphoSource media {item_id}: {e}")
            return None
