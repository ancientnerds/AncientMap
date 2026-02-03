"""
Europe PMC Connector.

Source #20 from research paper.
Protocol: REST
Auth: None
License: Open
Priority: P2

API: https://europepmc.org/RestfulWebService
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class EuropePMCConnector(BaseConnector):
    """Europe PMC connector for life science papers."""

    connector_id = "europe_pmc"
    connector_name = "Europe PMC"
    description = "Open science platform for life science literature"

    content_types = [ContentType.PAPER]

    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    website_url = "https://europepmc.org"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Open Access"
    attribution = "Europe PMC"

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
        """Search Europe PMC."""
        try:
            params = {
                "query": query,
                "resultType": "core",
                "format": "json",
                "pageSize": limit,
                "cursorMark": "*",
            }

            response = await self.rest.get("/search", params=params)

            if not response or "resultList" not in response:
                return []

            items = []
            for result in response.get("resultList", {}).get("result", []):
                try:
                    # Build URL
                    pmid = result.get("pmid")
                    pmcid = result.get("pmcid")
                    url = ""
                    if pmcid:
                        url = f"https://europepmc.org/article/PMC/{pmcid}"
                    elif pmid:
                        url = f"https://europepmc.org/article/MED/{pmid}"

                    item = ContentItem(
                        id=f"europe_pmc:{pmid or pmcid or result.get('id', '')}",
                        source=self.connector_id,
                        content_type=ContentType.PAPER,
                        title=result.get("title", "Untitled"),
                        description=result.get("abstractText"),
                        url=url,
                        creator=result.get("authorString"),
                        date=result.get("firstPublicationDate"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=result,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse Europe PMC result: {e}")

            return items

        except Exception as e:
            logger.error(f"Europe PMC search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific paper by PMID or PMCID."""
        try:
            if item_id.startswith("europe_pmc:"):
                item_id = item_id[11:]

            # Try to determine if it's a PMID or PMCID
            "MED" if item_id.isdigit() else "PMC"

            response = await self.rest.get(
                "/search",
                params={
                    "query": f"EXT_ID:{item_id}",
                    "resultType": "core",
                    "format": "json",
                }
            )

            if response and "resultList" in response:
                results = response.get("resultList", {}).get("result", [])
                if results:
                    result = results[0]
                    pmid = result.get("pmid")
                    pmcid = result.get("pmcid")
                    url = ""
                    if pmcid:
                        url = f"https://europepmc.org/article/PMC/{pmcid}"
                    elif pmid:
                        url = f"https://europepmc.org/article/MED/{pmid}"

                    return ContentItem(
                        id=f"europe_pmc:{item_id}",
                        source=self.connector_id,
                        content_type=ContentType.PAPER,
                        title=result.get("title", "Untitled"),
                        description=result.get("abstractText"),
                        url=url,
                        creator=result.get("authorString"),
                        date=result.get("firstPublicationDate"),
                        license=self.license,
                        attribution=self.attribution,
                        raw_data=result,
                    )

        except Exception as e:
            logger.error(f"Failed to get Europe PMC paper {item_id}: {e}")

        return None
