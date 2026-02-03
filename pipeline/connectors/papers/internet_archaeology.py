"""
Internet Archaeology Connector.

Source #18 from research paper.
Protocol: RSS + Scrape
Auth: None
License: CC-BY 3.0
Priority: P3

URL: https://intarch.ac.uk/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class InternetArchaeologyConnector(BaseConnector):
    """Internet Archaeology connector for archaeological papers."""

    connector_id = "internet_archaeology"
    connector_name = "Internet Archaeology"
    description = "Open access archaeological research journal"

    content_types = [ContentType.PAPER]

    base_url = "https://intarch.ac.uk"
    protocol = ProtocolType.REST
    rate_limit = 1.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY 3.0"
    attribution = "Internet Archaeology"

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
        """Search Internet Archaeology."""
        # TODO: Implement RSS parsing and search
        logger.warning("Internet Archaeology connector not fully implemented")
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific article by ID."""
        # TODO: Implement item retrieval
        return None
