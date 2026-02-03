"""
CyArk Connector.

Source #32 from research paper.
Protocol: Sketchfab (via partner)
Auth: OAuth
License: CC-BY-NC 4.0 (NON-COMMERCIAL USE ONLY)
Priority: P3

URL: https://www.cyark.org/
WARNING: CyArk content is for non-commercial use only per their Data Use Policy.
"""

from typing import List, Optional
from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.types import ContentType, ContentItem, AuthType, ProtocolType
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.protocols.rest import RestProtocol


@ConnectorRegistry.register
class CyArkConnector(BaseConnector):
    """CyArk connector for heritage site 3D models."""

    connector_id = "cyark"
    connector_name = "CyArk"
    description = "3D documentation of cultural heritage sites"

    content_types = [ContentType.MODEL_3D]

    base_url = "https://www.cyark.org"
    protocol = ProtocolType.REST
    rate_limit = 1.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY-NC 4.0"  # Non-commercial use only
    attribution = "CyArk (https://www.cyark.org)"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: Optional[ContentType] = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> List[ContentItem]:
        """Search CyArk projects.

        Note: CyArk uses Sketchfab for 3D model hosting.
        This connector searches CyArk's project database.
        """
        # TODO: Implement CyArk website/API search
        logger.warning("CyArk connector not fully implemented - uses Sketchfab for models")
        return []

    async def get_item(self, item_id: str) -> Optional[ContentItem]:
        """Get specific project by ID."""
        # TODO: Implement item retrieval
        return None
