"""
Nomisma.org Connector.

Source #43 from research paper.
Protocol: SPARQL + REST
Auth: None
License: CC-BY
Priority: P1

API: http://nomisma.org/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.protocols.sparql import SparqlProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class NomismaConnector(BaseConnector):
    """Nomisma.org connector for numismatic linked data."""

    connector_id = "nomisma"
    connector_name = "Nomisma.org"
    description = "Linked open data for numismatics"

    content_types = [ContentType.COIN]

    base_url = "http://nomisma.org"
    website_url = "http://nomisma.org"
    protocol = ProtocolType.SPARQL
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC-BY"
    attribution = "Nomisma.org"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.sparql = SparqlProtocol(endpoint="http://nomisma.org/query")
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Nomisma using SPARQL."""
        try:
            sparql_query = f"""
            PREFIX nmo: <http://nomisma.org/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX foaf: <http://xmlns.com/foaf/0.1/>

            SELECT ?coin ?label ?description ?thumbnail ?mint ?authority
            WHERE {{
                ?coin a nmo:TypeSeriesItem .
                ?coin skos:prefLabel ?label .
                FILTER(LANG(?label) = "en" || LANG(?label) = "")
                FILTER(CONTAINS(LCASE(?label), LCASE("{query}")))
                OPTIONAL {{ ?coin dcterms:description ?description }}
                OPTIONAL {{ ?coin foaf:thumbnail ?thumbnail }}
                OPTIONAL {{ ?coin nmo:hasMint ?mint }}
                OPTIONAL {{ ?coin nmo:hasAuthority ?authority }}
            }}
            LIMIT {limit}
            OFFSET {offset}
            """

            results = await self.sparql.query(sparql_query)

            items = []
            for binding in results.get("results", {}).get("bindings", []):
                coin_uri = binding.get("coin", {}).get("value", "")
                coin_id = coin_uri.split("/")[-1] if coin_uri else ""

                item = ContentItem(
                    id=f"nomisma:{coin_id}",
                    source=self.connector_id,
                    content_type=ContentType.COIN,
                    title=binding.get("label", {}).get("value", "Coin type"),
                    description=binding.get("description", {}).get("value"),
                    url=coin_uri or f"http://nomisma.org/id/{coin_id}",
                    thumbnail_url=binding.get("thumbnail", {}).get("value"),
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Nomisma search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific coin type by ID."""
        try:
            if item_id.startswith("nomisma:"):
                item_id = item_id[8:]

            # Get JSON-LD representation
            response = await self.rest.get(
                f"/id/{item_id}",
                headers={"Accept": "application/json"}
            )

            if not response:
                return None

            return ContentItem(
                id=f"nomisma:{item_id}",
                source=self.connector_id,
                content_type=ContentType.COIN,
                title=response.get("prefLabel", {}).get("en", "Coin type"),
                description=response.get("definition", {}).get("en"),
                url=f"http://nomisma.org/id/{item_id}",
                license=self.license,
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Nomisma coin type {item_id}: {e}")
            return None
