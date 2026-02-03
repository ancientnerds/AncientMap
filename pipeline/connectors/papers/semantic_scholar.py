"""
Semantic Scholar Connector.

AI-powered research tool for scientific literature with 200M+ papers.

Protocol: REST
Auth: Optional API key (free tier works)
Rate Limit: 100 req/5 min unauthenticated
License: ODC-BY

API Docs: https://api.semanticscholar.org/api-docs/graph
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class SemanticScholarConnector(BaseConnector):
    """Semantic Scholar connector for academic papers."""

    connector_id = "semantic_scholar"
    connector_name = "Semantic Scholar"
    description = "AI-powered research tool for scientific literature"

    content_types = [ContentType.PAPER]

    base_url = "https://api.semanticscholar.org/graph/v1"
    website_url = "https://www.semanticscholar.org"
    protocol = ProtocolType.REST
    rate_limit = 0.33  # 100 req/5 min = ~0.33 req/sec
    requires_auth = False
    auth_type = AuthType.NONE

    license = "ODC-BY"
    attribution = "Semantic Scholar"

    # Fields to request from API
    PAPER_FIELDS = "paperId,title,abstract,authors,year,url,citationCount,openAccessPdf"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    def get_auth_headers(self) -> dict:
        """Get authentication headers if API key is configured."""
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search Semantic Scholar for academic papers.

        Args:
            query: Search query string
            content_type: Ignored (always returns papers)
            limit: Maximum results (max 100 per request)
            offset: Starting offset for pagination
            **kwargs: Additional search parameters
                - year: Filter by publication year or range (e.g., "2020-2023")
                - fields_of_study: Filter by field (e.g., "History", "Archaeology")

        Returns:
            List of ContentItem objects
        """
        try:
            params = {
                "query": query,
                "limit": min(limit, 100),
                "offset": offset,
                "fields": self.PAPER_FIELDS,
            }

            # Add optional filters
            if year := kwargs.get("year"):
                params["year"] = year
            if fields := kwargs.get("fields_of_study"):
                params["fieldsOfStudy"] = fields

            headers = self.get_auth_headers()
            response = await self.rest.get("/paper/search", params=params, headers=headers)

            if not response or "data" not in response:
                return []

            items = []
            for paper in response.get("data", []):
                try:
                    item = self._parse_paper(paper)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse Semantic Scholar result: {e}")

            logger.info(f"Semantic Scholar search for '{query}' returned {len(items)} results")
            return items

        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """
        Get specific paper by Semantic Scholar ID.

        Args:
            item_id: Paper ID (e.g., "649def34f8be52c8b66281af98ae884c09aef38b"
                     or "semantic_scholar:649def...")

        Returns:
            ContentItem or None if not found
        """
        try:
            # Normalize ID
            if item_id.startswith("semantic_scholar:"):
                item_id = item_id[17:]

            params = {"fields": self.PAPER_FIELDS}
            headers = self.get_auth_headers()

            response = await self.rest.get(f"/paper/{item_id}", params=params, headers=headers)

            if not response:
                return None

            return self._parse_paper(response)

        except Exception as e:
            logger.error(f"Failed to get Semantic Scholar paper {item_id}: {e}")
            return None

    async def get_paper_citations(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> list[ContentItem]:
        """
        Get papers that cite a given paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum results

        Returns:
            List of citing papers
        """
        try:
            if paper_id.startswith("semantic_scholar:"):
                paper_id = paper_id[17:]

            params = {
                "fields": self.PAPER_FIELDS,
                "limit": min(limit, 100),
            }
            headers = self.get_auth_headers()

            response = await self.rest.get(
                f"/paper/{paper_id}/citations",
                params=params,
                headers=headers,
            )

            if not response or "data" not in response:
                return []

            items = []
            for citation in response.get("data", []):
                paper = citation.get("citingPaper")
                if paper:
                    item = self._parse_paper(paper)
                    if item:
                        items.append(item)

            return items

        except Exception as e:
            logger.error(f"Failed to get citations for {paper_id}: {e}")
            return []

    async def get_paper_references(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> list[ContentItem]:
        """
        Get papers referenced by a given paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum results

        Returns:
            List of referenced papers
        """
        try:
            if paper_id.startswith("semantic_scholar:"):
                paper_id = paper_id[17:]

            params = {
                "fields": self.PAPER_FIELDS,
                "limit": min(limit, 100),
            }
            headers = self.get_auth_headers()

            response = await self.rest.get(
                f"/paper/{paper_id}/references",
                params=params,
                headers=headers,
            )

            if not response or "data" not in response:
                return []

            items = []
            for ref in response.get("data", []):
                paper = ref.get("citedPaper")
                if paper:
                    item = self._parse_paper(paper)
                    if item:
                        items.append(item)

            return items

        except Exception as e:
            logger.error(f"Failed to get references for {paper_id}: {e}")
            return []

    def _parse_paper(self, paper: dict) -> ContentItem | None:
        """Parse a Semantic Scholar paper response into a ContentItem."""
        try:
            paper_id = paper.get("paperId")
            if not paper_id:
                return None

            title = paper.get("title", "Untitled")

            # Extract authors
            authors = []
            for author in paper.get("authors", []):
                name = author.get("name")
                if name:
                    authors.append(name)

            # Get URL (prefer semantic scholar, fallback to open access PDF)
            url = paper.get("url", "")
            if not url:
                url = f"https://www.semanticscholar.org/paper/{paper_id}"

            # Get PDF URL if available
            pdf_url = None
            open_access_pdf = paper.get("openAccessPdf")
            if open_access_pdf:
                pdf_url = open_access_pdf.get("url")

            # Publication year
            year = paper.get("year")
            date = str(year) if year else None

            return ContentItem(
                id=f"semantic_scholar:{paper_id}",
                source=self.connector_id,
                content_type=ContentType.PAPER,
                title=title,
                description=paper.get("abstract"),
                url=url,
                media_url=pdf_url,
                creator=", ".join(authors) if authors else None,
                date=date,
                date_numeric=year,
                license=self.license,
                attribution=self.attribution,
                raw_data={
                    "paper_id": paper_id,
                    "citation_count": paper.get("citationCount"),
                    "authors": authors,
                    "has_open_access_pdf": pdf_url is not None,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse Semantic Scholar paper: {e}")
            return None
