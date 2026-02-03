"""
Historic England Connector.

Source #13 from research paper.
Protocol: ArcGIS REST
Auth: None
License: OGL (Open Government Licence)
Priority: P1

API: https://historicengland.org.uk/listing/the-list/data-downloads/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.arcgis import ArcGISProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class HistoricEnglandConnector(BaseConnector):
    """Historic England connector for listed buildings and monuments."""

    connector_id = "historic_england"
    connector_name = "Historic England"
    description = "Listed buildings, scheduled monuments, and heritage sites in England"

    content_types = [ContentType.DOCUMENT]

    base_url = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services"
    website_url = "https://historicengland.org.uk"
    protocol = ProtocolType.ARCGIS
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "OGL"
    attribution = "Historic England"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.arcgis = ArcGISProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Historic England database."""
        try:
            # Search Listed Buildings layer
            results = await self.arcgis.query_features(
                layer_url=f"{self.base_url}/Listed_Buildings/FeatureServer/0",
                where=f"Name LIKE '%{query}%'",
                out_fields="*",
                result_count=limit,
                result_offset=offset,
            )

            items = []
            for feature in results:
                attrs = feature.get("attributes", {})
                geom = feature.get("geometry", {})

                item = ContentItem(
                    id=f"historic_england:{attrs.get('ListEntry', '')}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=attrs.get("Name", "Unknown"),
                    description=attrs.get("ListDescription"),
                    url=f"https://historicengland.org.uk/listing/the-list/list-entry/{attrs.get('ListEntry', '')}",
                    lat=geom.get("y"),
                    lon=geom.get("x"),
                    place_name=attrs.get("Location"),
                    license=self.license,
                    attribution=self.attribution,
                    raw_data=feature,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Historic England search failed: {e}")
            return []

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get heritage sites near a location."""
        try:
            results = await self.arcgis.query_features(
                layer_url=f"{self.base_url}/Listed_Buildings/FeatureServer/0",
                geometry={
                    "x": lon,
                    "y": lat,
                    "spatialReference": {"wkid": 4326}
                },
                geometry_type="esriGeometryPoint",
                spatial_rel="esriSpatialRelIntersects",
                distance=radius_km * 1000,  # Convert to meters
                units="esriSRUnit_Meter",
                out_fields="*",
                result_count=limit,
            )

            items = []
            for feature in results:
                attrs = feature.get("attributes", {})
                geom = feature.get("geometry", {})

                item = ContentItem(
                    id=f"historic_england:{attrs.get('ListEntry', '')}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=attrs.get("Name", "Unknown"),
                    description=attrs.get("ListDescription"),
                    url=f"https://historicengland.org.uk/listing/the-list/list-entry/{attrs.get('ListEntry', '')}",
                    lat=geom.get("y"),
                    lon=geom.get("x"),
                    place_name=attrs.get("Location"),
                    license=self.license,
                    attribution=self.attribution,
                    raw_data=feature,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Historic England location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific listing by ID."""
        # TODO: Implement item retrieval
        return None
