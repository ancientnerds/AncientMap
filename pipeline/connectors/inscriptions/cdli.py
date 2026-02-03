"""
Cuneiform Digital Library Initiative (CDLI) Connector.

Source #40 from research paper.
Protocol: REST (website moved, no public API)
Auth: None
License: Open
Priority: P1

Website: https://cdli.earth/ (moved from cdli.ucla.edu)

Note: CDLI has migrated to cdli.earth. The old SPARQL endpoint at
cdli.ucla.edu/sparql no longer exists. No public search API is available.
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class CDLIConnector(BaseConnector):
    """CDLI connector for cuneiform inscriptions."""

    connector_id = "cdli"
    connector_name = "CDLI"
    description = "Cuneiform tablets and inscriptions"

    content_types = [ContentType.INSCRIPTION, ContentType.PRIMARY_TEXT]

    base_url = "https://cdli.earth"
    website_url = "https://cdli.earth"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Open"
    attribution = "Cuneiform Digital Library Initiative"

    # No public API available after migration to cdli.earth
    available = False
    unavailable_reason = "CDLI migrated to cdli.earth - no public search API available"

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
        """Search CDLI cuneiform texts.

        Note: CDLI has no public search API after migration to cdli.earth.
        This connector is marked as unavailable.
        """
        return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific artifact by P-number."""
        try:
            if item_id.startswith("cdli:"):
                item_id = item_id[5:]

            # CDLI artifacts are identified by P-numbers (e.g., P123456)
            if not item_id.startswith("P"):
                item_id = f"P{item_id}"

            # Try to get artifact page - may need HTML parsing
            logger.warning("CDLI connector item retrieval not fully implemented")
            return None

        except Exception as e:
            logger.error(f"Failed to get CDLI artifact {item_id}: {e}")
            return None
