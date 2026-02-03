"""
IIIF Consortium Connector.

Source #29 from research paper.
Protocol: IIIF
Auth: Varies
License: Varies
Priority: P2

API: https://iiif.io/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.iiif import IIIFProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class IIIFConsortiumConnector(BaseConnector):
    """IIIF Consortium connector for high-resolution images."""

    connector_id = "iiif"
    connector_name = "IIIF Consortium"
    description = "High-resolution images from IIIF-compliant institutions"

    content_types = [ContentType.PHOTO, ContentType.MANUSCRIPT, ContentType.MAP]

    base_url = "https://iiif.io"
    protocol = ProtocolType.IIIF
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Varies"
    attribution = "IIIF Consortium"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.iiif = IIIFProtocol(rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search IIIF resources.

        Note: IIIF doesn't have a central search - this is a stub
        for searching known IIIF endpoints.
        """
        # IIIF is a protocol, not a centralized repository
        # Individual institutions implement their own IIIF endpoints
        logger.warning("IIIF Consortium connector: search requires specific manifest URLs")
        return []

    async def get_manifest(self, manifest_url: str) -> ContentItem | None:
        """Get content from a specific IIIF manifest."""
        try:
            manifest = await self.iiif.get_manifest(manifest_url)

            if not manifest:
                return None

            # Parse manifest
            label = manifest.get("label", {})
            if isinstance(label, dict):
                label = label.get("en", [label.get("@value", "Unknown")])[0]
            elif isinstance(label, list):
                label = label[0]

            # Get thumbnail from first canvas
            thumbnail = None
            sequences = manifest.get("sequences", [])
            if sequences:
                canvases = sequences[0].get("canvases", [])
                if canvases:
                    thumbnail = canvases[0].get("thumbnail", {}).get("@id")

            return ContentItem(
                id=f"iiif:{manifest.get('@id', manifest_url)}",
                source=self.connector_id,
                content_type=ContentType.PHOTO,
                title=label if isinstance(label, str) else "Unknown",
                description=manifest.get("description"),
                url=manifest_url,
                thumbnail_url=thumbnail,
                license=manifest.get("license"),
                attribution=manifest.get("attribution", self.attribution),
                raw_data=manifest,
            )

        except Exception as e:
            logger.error(f"Failed to get IIIF manifest: {e}")
            return None

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific manifest by URL or ID."""
        # If it looks like a URL, try to fetch it directly
        if item_id.startswith("http"):
            return await self.get_manifest(item_id)
        elif item_id.startswith("iiif:"):
            return await self.get_manifest(item_id[5:])
        return None
