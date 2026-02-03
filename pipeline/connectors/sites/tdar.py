"""
tDAR (The Digital Archaeological Record) Connector.

Source #15 from research paper.
Protocol: REST
Auth: Login required
License: Varies
Priority: P3

API: https://core.tdar.org/
"""



from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class TDARConnector(BaseConnector):
    """tDAR connector for digital archaeological records."""

    connector_id = "tdar"
    connector_name = "tDAR"
    description = "The Digital Archaeological Record repository"

    content_types = [ContentType.DOCUMENT, ContentType.PAPER]

    base_url = "https://core.tdar.org/api"
    website_url = "https://www.tdar.org"
    protocol = ProtocolType.REST
    rate_limit = 1.0
    requires_auth = True
    auth_type = AuthType.BASIC

    license = "Varies"
    attribution = "tDAR"

    # Requires institutional login - no public API access
    available = False
    unavailable_reason = "tDAR requires institutional login credentials for API access"

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
        """Search tDAR repository.

        Note: tDAR requires institutional login for API access.
        This connector is marked as unavailable.
        """
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific resource by ID."""
        # TODO: Implement item retrieval
        return None
