"""
Portable Antiquities Scheme (PAS) Connector.

Source #7 from research paper.
Protocol: REST
Auth: None
License: CC-BY 2.0 (NOT CC-BY-NC-SA - verified at finds.org.uk)
Priority: P2

API: https://finds.org.uk/database/api
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PASConnector(BaseConnector):
    """Portable Antiquities Scheme connector for UK archaeological finds."""

    connector_id = "pas"
    connector_name = "Portable Antiquities Scheme"
    description = "Archaeological finds recorded in England and Wales"

    content_types = [ContentType.ARTIFACT, ContentType.COIN]

    base_url = "https://finds.org.uk/database"
    website_url = "https://finds.org.uk"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY 2.0"  # Corrected: PAS uses CC-BY 2.0, not NC-SA
    attribution = "The Portable Antiquities Scheme"

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
        """Search PAS database."""
        try:
            params = {
                "q": query,
                "format": "json",
                "rows": limit,
                "start": offset,
            }

            # Filter by object type
            if content_type == ContentType.COIN:
                params["objectType"] = "COIN"

            response = await self.rest.get("/search/results", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for record in response.get("results", []):
                try:
                    content_item = self._parse_record(record)
                    if content_item:
                        items.append(content_item)
                except Exception as e:
                    logger.debug(f"Failed to parse PAS record: {e}")

            return items

        except Exception as e:
            logger.error(f"PAS search failed: {e}")
            return []

    def _parse_record(self, record: dict) -> ContentItem | None:
        """Parse PAS record to ContentItem."""
        record_id = record.get("id", "")
        object_type = record.get("objectType", "")

        # Determine content type
        content_type = ContentType.COIN if object_type == "COIN" else ContentType.ARTIFACT

        # Get thumbnail from images
        thumbnail = None
        if record.get("thumbnail"):
            thumbnail = f"https://finds.org.uk{record['thumbnail']}"

        return ContentItem(
            id=f"pas:{record_id}",
            source=self.connector_id,
            content_type=content_type,
            title=record.get("broadperiod", "Unknown") + " " + object_type.lower(),
            description=record.get("description"),
            url=f"https://finds.org.uk/database/artefacts/record/id/{record_id}",
            thumbnail_url=thumbnail,
            date=record.get("fromDate"),
            period=record.get("broadperiod"),
            culture=record.get("culture"),
            place_name=record.get("county"),
            lat=float(record["lat"]) if record.get("lat") else None,
            lon=float(record["lon"]) if record.get("lon") else None,
            license=self.license,
            attribution=self.attribution,
            raw_data=record,
        )

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific find by ID."""
        try:
            if item_id.startswith("pas:"):
                item_id = item_id[4:]

            response = await self.rest.get(
                f"/artefacts/record/id/{item_id}",
                params={"format": "json"}
            )

            if response:
                return self._parse_record(response)

        except Exception as e:
            logger.error(f"Failed to get PAS item {item_id}: {e}")

        return None

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get finds near a location."""
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "d": radius_km,
                "format": "json",
                "rows": limit,
            }

            if content_type == ContentType.COIN:
                params["objectType"] = "COIN"

            response = await self.rest.get("/search/results", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for record in response.get("results", []):
                try:
                    content_item = self._parse_record(record)
                    if content_item:
                        items.append(content_item)
                except Exception as e:
                    logger.debug(f"Failed to parse PAS record: {e}")

            return items

        except Exception as e:
            logger.error(f"PAS location search failed: {e}")
            return []
