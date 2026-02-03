"""
Getty Thesaurus of Geographic Names (TGN) Connector.

Source #48 from research paper.
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
class GettyTGNConnector(BaseConnector):
    """Getty TGN connector for geographic names."""

    connector_id = "getty_tgn"
    connector_name = "Getty TGN"
    description = "Thesaurus of Geographic Names controlled vocabulary"

    content_types = [ContentType.DOCUMENT]

    base_url = "http://vocab.getty.edu"
    website_url = "https://www.getty.edu/research/tools/vocabularies/tgn/"
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
        """Search Getty TGN place names."""
        try:
            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
            PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>

            SELECT ?subject ?label ?scopeNote ?lat ?long
            WHERE {{
                ?subject a gvp:Subject .
                ?subject skos:inScheme <http://vocab.getty.edu/tgn/> .
                ?subject gvp:prefLabelGVP/xl:literalForm ?label .
                FILTER(LANG(?label) = "en" || LANG(?label) = "")
                FILTER(CONTAINS(LCASE(?label), LCASE("{query}")))
                OPTIONAL {{ ?subject skos:scopeNote/rdf:value ?scopeNote }}
                OPTIONAL {{ ?subject wgs:lat ?lat }}
                OPTIONAL {{ ?subject wgs:long ?long }}
            }}
            LIMIT {limit}
            OFFSET {offset}
            """

            results = await self.sparql.query(sparql_query)

            items = []
            for binding in results.get("results", {}).get("bindings", []):
                subject_uri = binding.get("subject", {}).get("value", "")
                subject_id = subject_uri.split("/")[-1] if subject_uri else ""

                lat = None
                lon = None
                if binding.get("lat"):
                    try:
                        lat = float(binding["lat"]["value"])
                    except (ValueError, TypeError):
                        pass
                if binding.get("long"):
                    try:
                        lon = float(binding["long"]["value"])
                    except (ValueError, TypeError):
                        pass

                item = ContentItem(
                    id=f"getty_tgn:{subject_id}",
                    source=self.connector_id,
                    content_type=ContentType.DOCUMENT,
                    title=binding.get("label", {}).get("value", "TGN Place"),
                    description=binding.get("scopeNote", {}).get("value"),
                    url=subject_uri,
                    lat=lat,
                    lon=lon,
                    place_name=binding.get("label", {}).get("value"),
                    license=self.license,
                    attribution=self.attribution,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Getty TGN search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific TGN place by ID."""
        try:
            if item_id.startswith("getty_tgn:"):
                item_id = item_id[10:]

            sparql_query = f"""
            PREFIX gvp: <http://vocab.getty.edu/ontology#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
            PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>

            SELECT ?label ?scopeNote ?lat ?long
            WHERE {{
                <http://vocab.getty.edu/tgn/{item_id}> gvp:prefLabelGVP/xl:literalForm ?label .
                FILTER(LANG(?label) = "en" || LANG(?label) = "")
                OPTIONAL {{ <http://vocab.getty.edu/tgn/{item_id}> skos:scopeNote/rdf:value ?scopeNote }}
                OPTIONAL {{ <http://vocab.getty.edu/tgn/{item_id}> wgs:lat ?lat }}
                OPTIONAL {{ <http://vocab.getty.edu/tgn/{item_id}> wgs:long ?long }}
            }}
            """

            results = await self.sparql.query(sparql_query)

            bindings = results.get("results", {}).get("bindings", [])
            if not bindings:
                return None

            binding = bindings[0]
            lat = None
            lon = None
            if binding.get("lat"):
                try:
                    lat = float(binding["lat"]["value"])
                except (ValueError, TypeError):
                    pass
            if binding.get("long"):
                try:
                    lon = float(binding["long"]["value"])
                except (ValueError, TypeError):
                    pass

            return ContentItem(
                id=f"getty_tgn:{item_id}",
                source=self.connector_id,
                content_type=ContentType.DOCUMENT,
                title=binding.get("label", {}).get("value", "TGN Place"),
                description=binding.get("scopeNote", {}).get("value"),
                url=f"http://vocab.getty.edu/tgn/{item_id}",
                lat=lat,
                lon=lon,
                place_name=binding.get("label", {}).get("value"),
                license=self.license,
                attribution=self.attribution,
            )

        except Exception as e:
            logger.error(f"Failed to get Getty TGN place {item_id}: {e}")
            return None
