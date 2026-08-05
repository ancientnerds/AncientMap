"""
U.S. National Archives Connector.

Source #28 from research paper.
Protocol: REST
Auth: API key (x-api-key header; free key via NARA Catalog support ticket)
License: Public Domain
Priority: P2

API: https://catalog.archives.gov/api/v2/api-docs/
Quota: 10,000 calls/month per key (support-set default) — this connector is
used for on-demand imagery/document search, not bulk crawls; keep it that way.
"""

import os

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# v2 filter vocabulary (verified 2026-08-05 against live API).
_MATERIAL_FILTERS = {
    ContentType.PHOTO: "Photographs and other Graphic Materials",
    ContentType.DOCUMENT: "Textual Records",
}


@ConnectorRegistry.register
class NationalArchivesConnector(BaseConnector):
    """U.S. National Archives connector for documents and images.

    Ported to Catalog API v2 on 2026-08-05 (v1 retired 2026-07; returned the
    SPA's HTML shell). Verified live: /records/search with q, limit, page,
    availableOnline, typeOfMaterials and ?naId= single-record lookup; hits at
    body.hits.hits[]._source.record with digitalObjects[], productionDates
    ([{"year": 1943, "logicalDate": "1943-01-01"}]), scopeAndContentNote.
    """

    connector_id = "nara"
    connector_name = "National Archives"
    description = "Documents and images from the U.S. National Archives"

    content_types = [ContentType.PHOTO, ContentType.DOCUMENT]

    base_url = "https://catalog.archives.gov/api/v2"
    website_url = "https://www.archives.gov"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = True
    auth_type = AuthType.API_KEY

    license = "Public Domain"
    attribution = "National Archives and Records Administration"

    available = True

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key or os.getenv("NARA_API_KEY"), **kwargs)
        self.rest = RestProtocol(
            base_url=self.base_url,
            headers={"x-api-key": self.api_key} if self.api_key else None,
            rate_limit=self.rate_limit,
        )

    def _require_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "NARA_API_KEY missing — Catalog API v2 requires the x-api-key "
                "header (free key via Catalog_API@nara.gov)."
            )

    @staticmethod
    def _parse_record(record: dict) -> ContentItem:
        na_id = record.get("naId", "")
        digital_objects = record.get("digitalObjects") or []
        first_obj = digital_objects[0] if digital_objects else {}

        dates = record.get("productionDates") or []
        year = dates[0].get("year") if dates else None

        return ContentItem(
            id=f"nara:{na_id}",
            source=NationalArchivesConnector.connector_id,
            content_type=ContentType.DOCUMENT,
            title=record.get("title", "Unknown"),
            description=record.get("scopeAndContentNote"),
            url=f"https://catalog.archives.gov/id/{na_id}",
            thumbnail_url=first_obj.get("thumbnailUrl") or None,
            date=year,
            license=NationalArchivesConnector.license,
            attribution=NationalArchivesConnector.attribution,
            raw_data=record,
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search National Archives catalog (v2)."""
        self._require_key()

        params: dict = {
            "q": query,
            "limit": limit,
            # Undigitized records have no viewable objects — useless for the
            # imagery/document surfaces this connector feeds.
            "availableOnline": "true",
        }
        if offset:
            params["page"] = offset // limit + 1

        material = _MATERIAL_FILTERS.get(content_type) if content_type else None
        if material:
            params["typeOfMaterials"] = material

        response = await self.rest.get("/records/search", params=params)
        hits = (((response or {}).get("body") or {}).get("hits") or {}).get("hits") or []

        items = []
        for hit in hits:
            try:
                items.append(self._parse_record(hit.get("_source", {}).get("record", {})))
            except Exception as e:
                logger.debug(f"Failed to parse NARA item: {e}")
        return items

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get a specific record by NAID (v2 exposes it via ?naId= search)."""
        self._require_key()

        if item_id.startswith("nara:"):
            item_id = item_id[5:]

        response = await self.rest.get("/records/search", params={"naId": item_id, "limit": 1})
        hits = (((response or {}).get("body") or {}).get("hits") or {}).get("hits") or []
        if not hits:
            return None
        return self._parse_record(hits[0].get("_source", {}).get("record", {}))
