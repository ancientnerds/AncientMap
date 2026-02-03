"""
Epigraphic Database Heidelberg (EDH) Connector.

Source #39 from research paper.
Protocol: REST (deprecated)
Auth: None
License: CC-BY-SA 4.0
Priority: P1

API: https://edh-www.adw.uni-heidelberg.de/

Note: EDH funding expired at end of 2021. The API endpoint at
/data/api/inscriptions/search appears to no longer be functional.
The project data is still available via bulk downloads and SPARQL.
See: https://edh.ub.uni-heidelberg.de/data
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class EDHConnector(BaseConnector):
    """EDH connector for Latin inscriptions.

    Note: The EDH REST API appears to be deprecated after project
    funding ended in 2021. Bulk data downloads are still available.
    """

    connector_id = "edh"
    connector_name = "Epigraphic Database Heidelberg"
    description = "Latin inscriptions from the Roman world"

    content_types = [ContentType.INSCRIPTION]

    base_url = "https://edh.ub.uni-heidelberg.de"
    website_url = "https://edh.ub.uni-heidelberg.de"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY-SA 4.0"
    attribution = "Epigraphic Database Heidelberg"

    # API deprecated in 2021 when funding ended
    available = False
    unavailable_reason = "EDH REST API deprecated in 2021. Bulk data available at https://edh.ub.uni-heidelberg.de/data"

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
        """Search EDH inscriptions.

        Note: EDH REST API deprecated in 2021 when funding ended.
        This connector is marked as unavailable.
        """
        return []

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get inscriptions near a location."""
        try:
            # EDH supports geographic search
            params = {
                "lat": lat,
                "lon": lon,
                "radius": radius_km,
                "format": "json",
                "rows": limit,
            }

            response = await self.rest.get("/data/api/inscriptions/search", params=params)

            if not response or "items" not in response:
                return []

            items = []
            for inscription in response.get("items", []):
                try:
                    item = ContentItem(
                        id=f"edh:{inscription.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.INSCRIPTION,
                        title=inscription.get("text_cleaned", "Latin inscription"),
                        description=inscription.get("transcription"),
                        url=f"https://edh-www.adw.uni-heidelberg.de/edh/inschrift/{inscription.get('id', '')}",
                        place_name=inscription.get("findspot_modern"),
                        lat=float(inscription["latitude"]) if inscription.get("latitude") else None,
                        lon=float(inscription["longitude"]) if inscription.get("longitude") else None,
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=inscription,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse EDH inscription: {e}")

            return items

        except Exception as e:
            logger.error(f"EDH location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific inscription by ID."""
        try:
            if item_id.startswith("edh:"):
                item_id = item_id[4:]

            response = await self.rest.get(f"/data/api/inscriptions/{item_id}", params={"format": "json"})

            if not response:
                return None

            return ContentItem(
                id=f"edh:{item_id}",
                source=self.connector_id,
                content_type=ContentType.INSCRIPTION,
                title=response.get("text_cleaned", "Latin inscription"),
                description=response.get("transcription"),
                url=f"https://edh-www.adw.uni-heidelberg.de/edh/inschrift/{item_id}",
                thumbnail_url=response.get("photo_url"),
                date=response.get("not_before"),
                period=response.get("dating"),
                place_name=response.get("findspot_modern"),
                lat=float(response["latitude"]) if response.get("latitude") else None,
                lon=float(response["longitude"]) if response.get("longitude") else None,
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get EDH inscription {item_id}: {e}")
            return None
