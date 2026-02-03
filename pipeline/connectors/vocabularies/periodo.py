"""
PeriodO Connector.

Source #50 from research paper.
Protocol: JSON-LD
Auth: None
License: CC0
Priority: P1

API: https://perio.do/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PeriodOConnector(BaseConnector):
    """PeriodO connector for historical period definitions."""

    connector_id = "periodo"
    connector_name = "PeriodO"
    description = "Gazetteer of period definitions for historical data"

    content_types = [ContentType.DOCUMENT]

    base_url = "https://data.perio.do"
    website_url = "https://perio.do"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC0"
    attribution = "PeriodO"

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
        """Search PeriodO period definitions."""
        try:
            # PeriodO provides a JSON-LD dataset
            # The API returns the full dataset - need to filter client-side
            response = await self.rest.get("/", headers={"Accept": "application/json"})

            if not response:
                return []

            # Search through periods
            items = []
            query_lower = query.lower()

            authorities = response.get("authorities", {})
            for auth_id, authority in authorities.items():
                for period_id, period in authority.get("periods", {}).items():
                    label = period.get("label", "")
                    if query_lower in label.lower():
                        # Get date range
                        start = period.get("start", {})
                        stop = period.get("stop", {})
                        start_year = start.get("in", {}).get("year") if start else None
                        stop_year = stop.get("in", {}).get("year") if stop else None

                        date = ""
                        if start_year and stop_year:
                            date = f"{start_year} to {stop_year}"
                        elif start_year:
                            date = f"from {start_year}"
                        elif stop_year:
                            date = f"to {stop_year}"

                        item = ContentItem(
                            id=f"periodo:{period_id}",
                            source=self.connector_id,
                            content_type=ContentType.DOCUMENT,
                            title=label,
                            description=f"Period definition from {authority.get('source', {}).get('title', 'Unknown source')}",
                            url=f"https://perio.do/{auth_id}/p{period_id.split('p')[-1] if 'p' in period_id else period_id}",
                            date=date if date else None,
                            place_name=period.get("spatialCoverageDescription"),
                            license=self.license,
                            attribution=self.attribution,
                        )
                        items.append(item)

                        if len(items) >= limit:
                            return items[offset:offset + limit]

            return items[offset:offset + limit]

        except Exception as e:
            logger.error(f"PeriodO search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific period definition by ID."""
        try:
            if item_id.startswith("periodo:"):
                item_id = item_id[8:]

            # Need to fetch full dataset and find the period
            response = await self.rest.get("/", headers={"Accept": "application/json"})

            if not response:
                return None

            # Search for the period
            authorities = response.get("authorities", {})
            for auth_id, authority in authorities.items():
                for period_id, period in authority.get("periods", {}).items():
                    if period_id == item_id or period_id.endswith(item_id):
                        label = period.get("label", "Unknown Period")

                        start = period.get("start", {})
                        stop = period.get("stop", {})
                        start_year = start.get("in", {}).get("year") if start else None
                        stop_year = stop.get("in", {}).get("year") if stop else None

                        date = ""
                        if start_year and stop_year:
                            date = f"{start_year} to {stop_year}"
                        elif start_year:
                            date = f"from {start_year}"
                        elif stop_year:
                            date = f"to {stop_year}"

                        return ContentItem(
                            id=f"periodo:{period_id}",
                            source=self.connector_id,
                            content_type=ContentType.DOCUMENT,
                            title=label,
                            description=f"Period definition from {authority.get('source', {}).get('title', 'Unknown source')}",
                            url=f"https://perio.do/{auth_id}/p{period_id.split('p')[-1] if 'p' in period_id else period_id}",
                            date=date if date else None,
                            place_name=period.get("spatialCoverageDescription"),
                            license=self.license,
                            attribution=self.attribution,
                        )

            return None

        except Exception as e:
            logger.error(f"Failed to get PeriodO period {item_id}: {e}")
            return None
