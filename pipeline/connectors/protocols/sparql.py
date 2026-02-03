"""
SPARQL Protocol Handler.

Provides SPARQL query execution for endpoints like:
- British Museum
- Getty vocabularies (AAT, TGN, ULAN)
- CDLI (Cuneiform Digital Library)
- Nomisma.org
- Wikidata
"""

import asyncio
from typing import Any

import httpx
from loguru import logger


class SparqlProtocol:
    """
    SPARQL endpoint query handler.

    Supports:
    - SELECT queries returning bindings
    - CONSTRUCT queries returning triples
    - ASK queries returning boolean
    - Multiple output formats (JSON, XML, CSV)
    """

    def __init__(
        self,
        endpoint: str,
        default_graph: str | None = None,
        timeout: float = 60.0,
        rate_limit: float = 0.5,  # SPARQL endpoints are often slow
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize SPARQL protocol handler.

        Args:
            endpoint: SPARQL endpoint URL
            default_graph: Default graph URI (optional)
            timeout: Query timeout in seconds
            rate_limit: Maximum queries per second
            http_client: Optional shared HTTP client
        """
        self.endpoint = endpoint
        self.default_graph = default_graph
        self.timeout = timeout
        self.rate_limit = rate_limit

        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

    async def __aenter__(self):
        if self._owns_client and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
            self._owns_client = True
        return self._http_client

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        if self.rate_limit <= 0:
            return

        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._last_request_time = asyncio.get_event_loop().time()

    async def query(
        self,
        sparql_query: str,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """
        Execute SPARQL query and return results.

        Args:
            sparql_query: SPARQL query string
            output_format: Output format (json, xml, csv)

        Returns:
            Query results as dictionary
        """
        await self._rate_limit()

        # Prepare request
        headers = {
            "Accept": self._get_accept_header(output_format),
            "User-Agent": "AncientNerdsMap/1.0",
        }

        params = {
            "query": sparql_query,
        }
        if self.default_graph:
            params["default-graph-uri"] = self.default_graph

        logger.debug(f"SPARQL query to {self.endpoint}")

        try:
            # Try GET first (many endpoints prefer this for SELECT)
            response = await self.client.get(
                self.endpoint,
                params=params,
                headers=headers,
            )

            # Fall back to POST if GET fails with 414 (URI too long)
            if response.status_code == 414:
                response = await self.client.post(
                    self.endpoint,
                    data=params,
                    headers=headers,
                )

            response.raise_for_status()

            if output_format == "json":
                return response.json()
            else:
                return {"raw": response.text}

        except httpx.HTTPStatusError as e:
            logger.error(f"SPARQL query failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"SPARQL query error: {e}")
            raise

    def _get_accept_header(self, format: str) -> str:
        """Get Accept header for output format."""
        formats = {
            "json": "application/sparql-results+json",
            "xml": "application/sparql-results+xml",
            "csv": "text/csv",
            "tsv": "text/tab-separated-values",
            "rdf": "application/rdf+xml",
            "turtle": "text/turtle",
            "ntriples": "application/n-triples",
        }
        return formats.get(format, "application/sparql-results+json")

    async def select(
        self,
        sparql_query: str,
    ) -> list[dict[str, Any]]:
        """
        Execute SELECT query and return bindings as list of dicts.

        Args:
            sparql_query: SPARQL SELECT query

        Returns:
            List of binding dictionaries
        """
        result = await self.query(sparql_query, "json")

        bindings = result.get("results", {}).get("bindings", [])

        # Convert SPARQL JSON format to simple dicts
        simplified = []
        for binding in bindings:
            row = {}
            for var, value_obj in binding.items():
                # Extract just the value, dropping type info
                row[var] = value_obj.get("value")
            simplified.append(row)

        return simplified

    async def ask(self, sparql_query: str) -> bool:
        """
        Execute ASK query and return boolean result.

        Args:
            sparql_query: SPARQL ASK query

        Returns:
            Boolean result
        """
        result = await self.query(sparql_query, "json")
        return result.get("boolean", False)

    async def construct(
        self,
        sparql_query: str,
        output_format: str = "turtle",
    ) -> str:
        """
        Execute CONSTRUCT query and return RDF.

        Args:
            sparql_query: SPARQL CONSTRUCT query
            output_format: RDF format (turtle, rdf, ntriples)

        Returns:
            RDF string
        """
        result = await self.query(sparql_query, output_format)
        return result.get("raw", "")

    def build_values_clause(
        self,
        variable: str,
        values: list[str],
        is_uri: bool = False,
    ) -> str:
        """
        Build a VALUES clause for filtering.

        Args:
            variable: Variable name (without ?)
            values: List of values
            is_uri: Whether values are URIs

        Returns:
            VALUES clause string
        """
        if not values:
            return ""

        if is_uri:
            formatted = " ".join(f"<{v}>" for v in values)
        else:
            formatted = " ".join(f'"{v}"' for v in values)

        return f"VALUES ?{variable} {{ {formatted} }}"

    def build_filter_regex(
        self,
        variable: str,
        pattern: str,
        flags: str = "i",
    ) -> str:
        """
        Build a FILTER with regex.

        Args:
            variable: Variable name (without ?)
            pattern: Regex pattern
            flags: Regex flags (i for case-insensitive)

        Returns:
            FILTER clause string
        """
        return f'FILTER(REGEX(?{variable}, "{pattern}", "{flags}"))'

    def build_filter_lang(
        self,
        variable: str,
        languages: list[str] = None,
    ) -> str:
        """
        Build a FILTER for language tags.

        Args:
            variable: Variable name (without ?)
            languages: List of language codes (e.g., ["en", "la"])

        Returns:
            FILTER clause string
        """
        if not languages:
            languages = ["en", ""]  # English or no language tag

        conditions = " || ".join(
            f'LANG(?{variable}) = "{lang}"' for lang in languages
        )
        return f"FILTER({conditions})"


# Common SPARQL prefixes used in cultural heritage data
COMMON_PREFIXES = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX schema: <http://schema.org/>
PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
"""


def with_prefixes(query: str, additional_prefixes: str = "") -> str:
    """
    Add common prefixes to a SPARQL query.

    Args:
        query: SPARQL query without prefixes
        additional_prefixes: Source-specific prefixes

    Returns:
        Query with prefixes prepended
    """
    return f"{COMMON_PREFIXES}\n{additional_prefixes}\n{query}"
