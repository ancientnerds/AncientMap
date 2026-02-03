"""
American Numismatic Society Connector.

Source #44 from research paper.
Protocol: SPARQL
Auth: None
License: Open
Priority: P2

API: http://numismatics.org/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.sparql import SparqlProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class ANSConnector(BaseConnector):
    """American Numismatic Society connector for coins."""

    connector_id = "ans"
    connector_name = "American Numismatic Society"
    description = "Ancient and medieval coins from ANS collection"

    content_types = [ContentType.COIN]

    base_url = "http://numismatics.org"
    website_url = "http://numismatics.org"
    protocol = ProtocolType.SPARQL
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Open"
    attribution = "American Numismatic Society"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.sparql = SparqlProtocol(endpoint="http://numismatics.org/sparql")

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search ANS coins using SPARQL."""
        try:
            sparql_query = f"""
            PREFIX nmo: <http://nomisma.org/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX foaf: <http://xmlns.com/foaf/0.1/>

            SELECT ?coin ?label ?description ?thumbnail
            WHERE {{
                ?coin a nmo:NumismaticObject .
                ?coin dcterms:title ?label .
                FILTER(CONTAINS(LCASE(?label), LCASE("{query}")))
                OPTIONAL {{ ?coin dcterms:description ?description }}
                OPTIONAL {{ ?coin foaf:thumbnail ?thumbnail }}
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
                    id=f"ans:{coin_id}",
                    source=self.connector_id,
                    content_type=ContentType.COIN,
                    title=binding.get("label", {}).get("value", "Coin"),
                    description=binding.get("description", {}).get("value"),
                    url=coin_uri,
                    thumbnail_url=binding.get("thumbnail", {}).get("value"),
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"ANS search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific coin by ID."""
        try:
            if item_id.startswith("ans:"):
                item_id = item_id[4:]

            # Query specific coin
            sparql_query = f"""
            PREFIX nmo: <http://nomisma.org/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX foaf: <http://xmlns.com/foaf/0.1/>

            SELECT ?label ?description ?thumbnail
            WHERE {{
                <http://numismatics.org/collection/{item_id}> dcterms:title ?label .
                OPTIONAL {{ <http://numismatics.org/collection/{item_id}> dcterms:description ?description }}
                OPTIONAL {{ <http://numismatics.org/collection/{item_id}> foaf:thumbnail ?thumbnail }}
            }}
            """

            results = await self.sparql.query(sparql_query)

            bindings = results.get("results", {}).get("bindings", [])
            if not bindings:
                return None

            binding = bindings[0]
            return ContentItem(
                id=f"ans:{item_id}",
                source=self.connector_id,
                content_type=ContentType.COIN,
                title=binding.get("label", {}).get("value", "Coin"),
                description=binding.get("description", {}).get("value"),
                url=f"http://numismatics.org/collection/{item_id}",
                thumbnail_url=binding.get("thumbnail", {}).get("value"),
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get ANS coin {item_id}: {e}")
            return None
