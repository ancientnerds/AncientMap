"""
Ireland Sites and Monuments Record (SMR) Connector.

Source #14 from research paper.
Protocol: ArcGIS REST
Auth: None
License: CC-BY 4.0
Priority: P1

API: https://maps.archaeology.ie/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.arcgis import ArcGISProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class IrelandSMRConnector(BaseConnector):
    """Ireland SMR connector for archaeological sites and monuments."""

    connector_id = "ireland_smr"
    connector_name = "Ireland SMR"
    description = "Sites and Monuments Record of Ireland"

    content_types = [ContentType.DOCUMENT]

    base_url = "https://maps.archaeology.ie/arcgis/rest/services"
    website_url = "https://www.archaeology.ie"
    protocol = ProtocolType.ARCGIS
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY 4.0"
    attribution = "National Monuments Service, Ireland"

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
        """Search Ireland SMR database."""
        try:
            results = await self.arcgis.query_features(
                layer_url=f"{self.base_url}/smr/FeatureServer/0",
                where=f"CLASSDESC LIKE '%{query}%' OR TOWNLAND LIKE '%{query}%'",
                out_fields="*",
                result_count=limit,
                result_offset=offset,
            )

            items = []
            for feature in results:
                attrs = feature.get("attributes", {})
                geom = feature.get("geometry", {})

                item = ContentItem(
                    id=f"ireland_smr:{attrs.get('SMR_NO', '')}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=f"{attrs.get('CLASSDESC', 'Unknown')} at {attrs.get('TOWNLAND', '')}",
                    description=attrs.get("CLASSDESC"),
                    url=f"https://maps.archaeology.ie/HistoricEnvironment/?SMESSION=smrs:{attrs.get('SMR_NO', '')}",
                    lat=geom.get("y"),
                    lon=geom.get("x"),
                    place_name=attrs.get("TOWNLAND"),
                    period=attrs.get("PERIOD"),
                    license=self.license,
                    attribution=self.attribution,
                    raw_data=feature,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Ireland SMR search failed: {e}")
            return []

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """Get monuments near a location."""
        try:
            results = await self.arcgis.query_features(
                layer_url=f"{self.base_url}/smr/FeatureServer/0",
                geometry={
                    "x": lon,
                    "y": lat,
                    "spatialReference": {"wkid": 4326}
                },
                geometry_type="esriGeometryPoint",
                spatial_rel="esriSpatialRelIntersects",
                distance=radius_km * 1000,
                units="esriSRUnit_Meter",
                out_fields="*",
                result_count=limit,
            )

            items = []
            for feature in results:
                attrs = feature.get("attributes", {})
                geom = feature.get("geometry", {})

                item = ContentItem(
                    id=f"ireland_smr:{attrs.get('SMR_NO', '')}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=f"{attrs.get('CLASSDESC', 'Unknown')} at {attrs.get('TOWNLAND', '')}",
                    url=f"https://maps.archaeology.ie/HistoricEnvironment/?SMESSION=smrs:{attrs.get('SMR_NO', '')}",
                    lat=geom.get("y"),
                    lon=geom.get("x"),
                    place_name=attrs.get("TOWNLAND"),
                    period=attrs.get("PERIOD"),
                    license=self.license,
                    attribution=self.attribution,
                    raw_data=feature,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Ireland SMR location search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific monument by SMR number."""
        # TODO: Implement item retrieval
        return None
