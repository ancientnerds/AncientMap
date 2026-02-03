"""
Getty Union List of Artist Names (ULAN) Connector.

Source #49 from research paper.
Protocol: SPARQL
Auth: None
License: ODC-By
Priority: P2

API: http://vocab.getty.edu/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.sparql import SparqlProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class GettyULANConnector(BaseConnector):
    """Getty ULAN connector for artist names."""

    connector_id = "getty_ulan"
    connector_name = "Getty ULAN"
    description = "Union List of Artist Names controlled vocabulary"

    content_types = [ContentType.DOCUMENT]

    base_url = "http://vocab.getty.edu"
    website_url = "https://www.getty.edu/research/tools/vocabularies/ulan/"
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
        """Search Getty ULAN artist names."""
        try:
            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>

            SELECT ?subject ?label ?biography ?birthDate ?deathDate
            WHERE {{
                ?subject a gvp:Subject .
                ?subject skos:inScheme <http://vocab.getty.edu/ulan/> .
                ?subject gvp:prefLabelGVP/xl:literalForm ?label .
                FILTER(CONTAINS(LCASE(?label), LCASE("{query}")))
                OPTIONAL {{ ?subject gvp:biographyPreferred/gvp:biographyNote ?biography }}
                OPTIONAL {{ ?subject gvp:estStart ?birthDate }}
                OPTIONAL {{ ?subject gvp:estEnd ?deathDate }}
            }}
            LIMIT {limit}
            OFFSET {offset}
            """

            results = await self.sparql.query(sparql_query)

            items = []
            for binding in results.get("results", {}).get("bindings", []):
                subject_uri = binding.get("subject", {}).get("value", "")
                subject_id = subject_uri.split("/")[-1] if subject_uri else ""

                # Build date range if available
                birth = binding.get("birthDate", {}).get("value", "")
                death = binding.get("deathDate", {}).get("value", "")
                date = ""
                if birth and death:
                    date = f"{birth} - {death}"
                elif birth:
                    date = f"b. {birth}"
                elif death:
                    date = f"d. {death}"

                item = ContentItem(
                    id=f"getty_ulan:{subject_id}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=binding.get("label", {}).get("value", "ULAN Artist"),
                    description=binding.get("biography", {}).get("value"),
                    url=subject_uri,
                    creator=binding.get("label", {}).get("value"),
                    date=date if date else None,
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Getty ULAN search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific ULAN artist by ID."""
        try:
            if item_id.startswith("getty_ulan:"):
                item_id = item_id[11:]

            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>

            SELECT ?label ?biography ?birthDate ?deathDate
            WHERE {{
                <http://vocab.getty.edu/ulan/{item_id}> gvp:prefLabelGVP/xl:literalForm ?label .
                OPTIONAL {{ <http://vocab.getty.edu/ulan/{item_id}> gvp:biographyPreferred/gvp:biographyNote ?biography }}
                OPTIONAL {{ <http://vocab.getty.edu/ulan/{item_id}> gvp:estStart ?birthDate }}
                OPTIONAL {{ <http://vocab.getty.edu/ulan/{item_id}> gvp:estEnd ?deathDate }}
            }}
            """

            results = await self.sparql.query(sparql_query)

            bindings = results.get("results", {}).get("bindings", [])
            if not bindings:
                return None

            binding = bindings[0]
            birth = binding.get("birthDate", {}).get("value", "")
            death = binding.get("deathDate", {}).get("value", "")
            date = ""
            if birth and death:
                date = f"{birth} - {death}"
            elif birth:
                date = f"b. {birth}"
            elif death:
                date = f"d. {death}"

            return ContentItem(
                id=f"getty_ulan:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=binding.get("label", {}).get("value", "ULAN Artist"),
                description=binding.get("biography", {}).get("value"),
                url=f"http://vocab.getty.edu/ulan/{item_id}",
                creator=binding.get("label", {}).get("value"),
                date=date if date else None,
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get Getty ULAN artist {item_id}: {e}")
            return None
