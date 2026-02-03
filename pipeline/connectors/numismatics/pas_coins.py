"""
Portable Antiquities Scheme Coins Connector.

Source #46 from research paper.
Protocol: REST
Auth: None
License: CC-BY-NC-SA
Priority: P1

API: https://finds.org.uk/database/api

Note: This uses the same PAS database as the museums/pas.py connector
but focuses specifically on numismatic finds (coins).
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PASCoinsConnector(BaseConnector):
    """Portable Antiquities Scheme connector for coins."""

    connector_id = "pas_coins"
    connector_name = "PAS Coins"
    description = "Coin finds recorded in England and Wales"

    content_types = [ContentType.COIN]

    base_url = "https://finds.org.uk/database"
    website_url = "https://finds.org.uk"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY-NC-SA"
    attribution = "Portable Antiquities Scheme"

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
        """Search PAS for coins."""
        try:
            params = {
                "q": query,
                "objectType": "COIN",  # Filter to coins only
                "format": "json",
                "rows": limit,
                "start": offset,
            }

            response = await self.rest.get("/search/results", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for record in response.get("results", []):
                try:
                    # Get thumbnail from images
                    thumbnail = None
                    if record.get("thumbnail"):
                        thumbnail = f"https://finds.org.uk{record['thumbnail']}"

                    # Build descriptive title for coin
                    denomination = record.get("denomination", "")
                    ruler = record.get("ruler", "")
                    period = record.get("broadperiod", "")
                    title_parts = [p for p in [period, ruler, denomination, "coin"] if p]
                    title = " ".join(title_parts)

                    item = ContentItem(
                        id=f"pas_coins:{record.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.COIN,
                        title=title,
                        description=record.get("description"),
                        url=f"https://finds.org.uk/database/artefacts/record/id/{record.get('id', '')}",
                        thumbnail_url=thumbnail,
                        date=record.get("fromDate"),
                        period=period,
                        place_name=record.get("county"),
                        lat=float(record["lat"]) if record.get("lat") else None,
                        lon=float(record["lon"]) if record.get("lon") else None,
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=record,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse PAS coin: {e}")

            return items

        except Exception as e:
            logger.error(f"PAS Coins search failed: {e}")
            return []

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get coins near a location."""
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "d": radius_km,
                "objectType": "COIN",
                "format": "json",
                "rows": limit,
            }

            response = await self.rest.get("/search/results", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for record in response.get("results", []):
                try:
                    thumbnail = None
                    if record.get("thumbnail"):
                        thumbnail = f"https://finds.org.uk{record['thumbnail']}"

                    denomination = record.get("denomination", "")
                    ruler = record.get("ruler", "")
                    period = record.get("broadperiod", "")
                    title_parts = [p for p in [period, ruler, denomination, "coin"] if p]
                    title = " ".join(title_parts)

                    item = ContentItem(
                        id=f"pas_coins:{record.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.COIN,
                        title=title,
                        description=record.get("description"),
                        url=f"https://finds.org.uk/database/artefacts/record/id/{record.get('id', '')}",
                        thumbnail_url=thumbnail,
                        period=period,
                        place_name=record.get("county"),
                        lat=float(record["lat"]) if record.get("lat") else None,
                        lon=float(record["lon"]) if record.get("lon") else None,
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=record,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse PAS coin: {e}")

            return items

        except Exception as e:
            logger.error(f"PAS Coins location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific coin by ID."""
        try:
            if item_id.startswith("pas_coins:"):
                item_id = item_id[10:]

            response = await self.rest.get(
                f"/artefacts/record/id/{item_id}",
                params={"format": "json"}
            )

            if not response:
                return None

            thumbnail = None
            if response.get("thumbnail"):
                thumbnail = f"https://finds.org.uk{response['thumbnail']}"

            denomination = response.get("denomination", "")
            ruler = response.get("ruler", "")
            period = response.get("broadperiod", "")
            title_parts = [p for p in [period, ruler, denomination, "coin"] if p]
            title = " ".join(title_parts)

            return ContentItem(
                id=f"pas_coins:{item_id}",
                source=self.connector_id,
                content_type=ContentType.COIN,
                title=title,
                description=response.get("description"),
                url=f"https://finds.org.uk/database/artefacts/record/id/{item_id}",
                thumbnail_url=thumbnail,
                period=period,
                place_name=response.get("county"),
                lat=float(response["lat"]) if response.get("lat") else None,
                lon=float(response["lon"]) if response.get("lon") else None,
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get PAS coin {item_id}: {e}")
            return None
