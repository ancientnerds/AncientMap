"""
Packard Humanities Institute (PHI) Connector.

Source #42 from research paper.
Protocol: Bulk download
Auth: None
License: Personal/Fair Use Only (NOT Open - see Terms of Use)
Priority: P3

URL: https://inscriptions.packhum.org/

WARNING: PHI Terms of Use explicitly state content is for "personal study" only.
Commercial use and redistribution are NOT permitted without explicit permission.
This connector should only be used for reference links, not data copying.
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class PackardConnector(BaseConnector):
    """Packard Humanities Institute connector for Greek inscriptions."""

    connector_id = "packard"
    connector_name = "Packard Humanities Institute"
    description = "Greek inscriptions database"

    content_types = [ContentType.INSCRIPTION]

    base_url = "https://inscriptions.packhum.org"
    protocol = ProtocolType.REST
    rate_limit = 1.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Personal/Fair Use Only"  # NOT open - see PHI Terms of Use
    attribution = "Packard Humanities Institute"
    # WARNING: This connector should only provide reference links, not copy data

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
        """Search PHI Greek inscriptions.

        Note: PHI primarily provides bulk data access.
        Web search interface may require scraping.
        """
        # TODO: Implement PHI search - may need bulk data processing
        logger.warning("Packard Humanities Institute connector not fully implemented")
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific inscription by ID."""
        try:
            if item_id.startswith("packard:"):
                item_id = item_id[8:]

            # PHI uses region/book/inscription identifiers
            logger.warning("Packard Humanities Institute connector item retrieval not fully implemented")
            return None

        except Exception as e:
            logger.error(f"Failed to get PHI inscription {item_id}: {e}")
            return None
