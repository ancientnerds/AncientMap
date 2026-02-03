"""
Getty Art & Architecture Thesaurus (AAT) Connector.

Source #47 from research paper.
Protocol: SPARQL
Auth: None
License: ODC-By
Priority: P1

API: http://vocab.getty.edu/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.sparql import SparqlProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class GettyAATConnector(BaseConnector):
    """Getty AAT connector for art and architecture terms."""

    connector_id = "getty_aat"
    connector_name = "Getty AAT"
    description = "Art & Architecture Thesaurus controlled vocabulary"

    content_types = [ContentType.DOCUMENT]

    base_url = "http://vocab.getty.edu"
    website_url = "https://www.getty.edu/research/tools/vocabularies/aat/"
    protocol = ProtocolType.SPARQL
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "ODC-By"
    attribution = "Getty Research Institute"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.sparql = SparqlProtocol(endpoint="http://vocab.getty.edu/sparql")

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Getty AAT terms."""
        try:
            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>

            SELECT ?subject ?label ?scopeNote
            WHERE {{
                ?subject a gvp:Subject .
                ?subject skos:inScheme <http://vocab.getty.edu/aat/> .
                ?subject gvp:prefLabelGVP/xl:literalForm ?label .
                FILTER(LANG(?label) = "en")
                FILTER(CONTAINS(LCASE(?label), LCASE("{query}")))
                OPTIONAL {{ ?subject skos:scopeNote/rdf:value ?scopeNote }}
            }}
            LIMIT {limit}
            OFFSET {offset}
            """

            results = await self.sparql.query(sparql_query)

            items = []
            for binding in results.get("results", {}).get("bindings", []):
                subject_uri = binding.get("subject", {}).get("value", "")
                subject_id = subject_uri.split("/")[-1] if subject_uri else ""

                item = ContentItem(
                    id=f"getty_aat:{subject_id}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=binding.get("label", {}).get("value", "AAT Term"),
                    description=binding.get("scopeNote", {}).get("value"),
                    url=subject_uri,
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Getty AAT search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific AAT term by ID."""
        try:
            if item_id.startswith("getty_aat:"):
                item_id = item_id[10:]

            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>

            SELECT ?label ?scopeNote
            WHERE {{
                <http://vocab.getty.edu/aat/{item_id}> gvp:prefLabelGVP/xl:literalForm ?label .
                FILTER(LANG(?label) = "en")
                OPTIONAL {{ <http://vocab.getty.edu/aat/{item_id}> skos:scopeNote/rdf:value ?scopeNote }}
            }}
            """

            results = await self.sparql.query(sparql_query)

            bindings = results.get("results", {}).get("bindings", [])
            if not bindings:
                return None

            binding = bindings[0]
            return ContentItem(
                id=f"getty_aat:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=binding.get("label", {}).get("value", "AAT Term"),
                description=binding.get("scopeNote", {}).get("value"),
                url=f"http://vocab.getty.edu/aat/{item_id}",
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get Getty AAT term {item_id}: {e}")
            return None
