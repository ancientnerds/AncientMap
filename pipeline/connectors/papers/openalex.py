"""
OpenAlex Connector.

Open catalog of 240M+ scholarly works with no authentication required.

Protocol: REST
Auth: None required (email in User-Agent recommended for polite pool)
Rate Limit: 100,000/day, 10/sec
License: CC0

API Docs: https://docs.openalex.org/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


def reconstruct_abstract(inverted_index: dict) -> str:
    """
    Reconstruct abstract from OpenAlex's inverted index format.

    OpenAlex stores abstracts as inverted indexes for compression:
    {"The": [0], "study": [1], "examines": [2]} -> "The study examines"

    Args:
        inverted_index: Dictionary mapping words to their positions

    Returns:
        Reconstructed abstract string
    """
    if not inverted_index:
        return ""

    # Build position -> word mapping
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))

    # Sort by position and join
    words.sort(key=lambda x: x[0])
    return " ".join(word for _, word in words)


@ConnectorRegistry.register
class OpenAlexConnector(BaseConnector):
    """OpenAlex connector for scholarly works."""

    connector_id = "openalex"
    connector_name = "OpenAlex"
    description = "Open catalog of 240M+ scholarly works"

    content_types = [ContentType.PAPER]

    base_url = "https://api.openalex.org"
    website_url = "https://openalex.org"
    protocol = ProtocolType.REST
    rate_limit = 10.0  # 10 req/sec allowed
    requires_auth = False
    auth_type = AuthType.NONE

    license = "CC0"
    attribution = "OpenAlex"

    # Fields to select from API (reduce response size)
    SELECT_FIELDS = "id,title,abstract_inverted_index,authorships,publication_year,primary_location,cited_by_count,doi,type"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        # Use polite pool with email for better rate limits
        headers = {
            "User-Agent": "AncientNerdsMap/1.0 (mailto:contact@ancientnerds.com)"
        }
        self.rest = RestProtocol(
            base_url=self.base_url,
            rate_limit=self.rate_limit,
            headers=headers,
        )

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search OpenAlex for scholarly works.

        Args:
            query: Search query string
            content_type: Ignored (always returns papers)
            limit: Maximum results (max 200 per request)
            offset: Not used (OpenAlex uses cursor pagination)
            **kwargs: Additional search parameters
                - publication_year: Filter by year or range (e.g., "2020" or "2020-2023")
                - type: Filter by work type (e.g., "article", "book-chapter")
                - is_oa: Filter for open access only (True/False)

        Returns:
            List of ContentItem objects
        """
        try:
            params = {
                "search": query,
                "per-page": min(limit, 200),
                "select": self.SELECT_FIELDS,
            }

            # Build filter string for additional parameters
            filters = []
            if year := kwargs.get("publication_year"):
                if "-" in str(year):
                    start, end = str(year).split("-")
                    filters.append(f"publication_year:{start}-{end}")
                else:
                    filters.append(f"publication_year:{year}")

            if work_type := kwargs.get("type"):
                filters.append(f"type:{work_type}")

            if kwargs.get("is_oa") is True:
                filters.append("is_oa:true")

            if filters:
                params["filter"] = ",".join(filters)

            response = await self.rest.get("/works", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for work in response.get("results", []):
                try:
                    item = self._parse_work(work)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse OpenAlex result: {e}")

            logger.info(f"OpenAlex search for '{query}' returned {len(items)} results")
            return items

        except Exception as e:
            logger.error(f"OpenAlex search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """
        Get specific work by OpenAlex ID.

        Args:
            item_id: OpenAlex ID (e.g., "W2741809807" or "openalex:W2741809807"
                     or full URL "https://openalex.org/W2741809807")

        Returns:
            ContentItem or None if not found
        """
        try:
            # Normalize ID
            if item_id.startswith("openalex:"):
                item_id = item_id[9:]
            if item_id.startswith("https://openalex.org/"):
                item_id = item_id[21:]

            params = {"select": self.SELECT_FIELDS}
            response = await self.rest.get(f"/works/{item_id}", params=params)

            if not response:
                return None

            return self._parse_work(response)

        except Exception as e:
            logger.error(f"Failed to get OpenAlex work {item_id}: {e}")
            return None

    async def get_works_by_author(
        self,
        author_id: str,
        limit: int = 20,
    ) -> list[ContentItem]:
        """
        Get works by a specific author.

        Args:
            author_id: OpenAlex author ID (e.g., "A5023888391")
            limit: Maximum results

        Returns:
            List of works by the author
        """
        try:
            if author_id.startswith("https://openalex.org/"):
                author_id = author_id[21:]

            params = {
                "filter": f"author.id:{author_id}",
                "per-page": min(limit, 200),
                "select": self.SELECT_FIELDS,
            }

            response = await self.rest.get("/works", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for work in response.get("results", []):
                item = self._parse_work(work)
                if item:
                    items.append(item)

            return items

        except Exception as e:
            logger.error(f"Failed to get works by author {author_id}: {e}")
            return []

    async def get_works_citing(
        self,
        work_id: str,
        limit: int = 20,
    ) -> list[ContentItem]:
        """
        Get works that cite a given work.

        Args:
            work_id: OpenAlex work ID
            limit: Maximum results

        Returns:
            List of citing works
        """
        try:
            if work_id.startswith("openalex:"):
                work_id = work_id[9:]
            if work_id.startswith("https://openalex.org/"):
                work_id = work_id[21:]

            params = {
                "filter": f"cites:{work_id}",
                "per-page": min(limit, 200),
                "select": self.SELECT_FIELDS,
            }

            response = await self.rest.get("/works", params=params)

            if not response or "results" not in response:
                return []

            items = []
            for work in response.get("results", []):
                item = self._parse_work(work)
                if item:
                    items.append(item)

            return items

        except Exception as e:
            logger.error(f"Failed to get works citing {work_id}: {e}")
            return []

    def _parse_work(self, work: dict) -> ContentItem | None:
        """Parse an OpenAlex work response into a ContentItem."""
        try:
            work_id = work.get("id", "")
            if not work_id:
                return None

            # Extract ID from URL if needed
            if work_id.startswith("https://openalex.org/"):
                work_id = work_id[21:]

            title = work.get("title", "Untitled")

            # Reconstruct abstract from inverted index
            abstract = None
            inverted_index = work.get("abstract_inverted_index")
            if inverted_index:
                abstract = reconstruct_abstract(inverted_index)

            # Extract authors
            authors = []
            for authorship in work.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name")
                if name:
                    authors.append(name)

            # Get URL from primary location or DOI
            url = ""
            primary_location = work.get("primary_location", {}) or {}
            if primary_location:
                landing_page = primary_location.get("landing_page_url")
                if landing_page:
                    url = landing_page

            # Fallback to DOI
            if not url:
                doi = work.get("doi")
                if doi:
                    url = doi if doi.startswith("http") else f"https://doi.org/{doi}"

            # Fallback to OpenAlex page
            if not url:
                url = f"https://openalex.org/{work_id}"

            # Get PDF URL if available
            pdf_url = None
            if primary_location:
                pdf = primary_location.get("pdf_url")
                if pdf:
                    pdf_url = pdf

            # Publication year
            year = work.get("publication_year")
            date = str(year) if year else None

            return ContentItem(
                id=f"openalex:{work_id}",
                source=self.connector_id,
                content_type=ContentType.PAPER,
                title=title,
                description=abstract,
                url=url,
                media_url=pdf_url,
                creator=", ".join(authors) if authors else None,
                date=date,
                date_numeric=year,
                license=self.license,
                attribution=self.attribution,
                raw_data={
                    "openalex_id": work_id,
                    "doi": work.get("doi"),
                    "cited_by_count": work.get("cited_by_count"),
                    "type": work.get("type"),
                    "authors": authors,
                    "has_pdf": pdf_url is not None,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse OpenAlex work: {e}")
            return None
