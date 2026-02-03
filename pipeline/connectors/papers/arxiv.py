"""
arXiv Connector.

Source #19 from research paper.
Protocol: OAI-PMH + Atom API
Auth: None
License: Varies (mostly open)
Priority: P2

arXiv provides two APIs:
1. Atom/RSS API for search (http://export.arxiv.org/api/query)
2. OAI-PMH for metadata harvesting (http://export.arxiv.org/oai2)

We use OAI-PMH for systematic harvesting and Atom for search queries.

References:
- API docs: https://arxiv.org/help/api/
- OAI-PMH: https://arxiv.org/help/oa
- Rate limits: 3 second delay between requests
"""

import re
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.oai_pmh import OAIPMHProtocol, OAIRecord
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# Atom/OpenSearch namespaces for search API
ATOM_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@ConnectorRegistry.register
class ArXivConnector(BaseConnector):
    """
    arXiv connector for academic preprints.

    Uses OAI-PMH for harvesting and Atom API for search.
    Particularly useful for archaeology-related papers in:
    - physics.hist-ph (History and Philosophy of Physics)
    - cs.CY (Computers and Society)
    - stat.AP (Statistics Applications)
    """

    connector_id = "arxiv"
    connector_name = "arXiv"
    description = "Open access preprint repository for scientific papers"

    content_types = [ContentType.PAPER]

    base_url = "http://export.arxiv.org"
    website_url = "https://arxiv.org"
    protocol = ProtocolType.OAI_PMH
    rate_limit = 0.33  # 3 second delay between requests (arXiv policy)
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Varies (see individual papers)"
    attribution = "arXiv.org"

    # OAI-PMH endpoint
    oai_url = "http://export.arxiv.org/oai2"

    # Atom search API endpoint
    search_url = "http://export.arxiv.org/api/query"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.oai = OAIPMHProtocol(
            base_url=self.oai_url,
            rate_limit=self.rate_limit,
        )
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        await self.oai.__aenter__()
        self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.oai.__aexit__(exc_type, exc_val, exc_tb)
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._http_client

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search arXiv preprints using the Atom API.

        Args:
            query: Search query (supports arXiv query syntax)
            content_type: Ignored (always returns papers)
            limit: Maximum results (max 100 per request)
            offset: Starting offset for pagination
            **kwargs: Additional search parameters
                - category: arXiv category (e.g., "physics.hist-ph")
                - sort_by: relevance, lastUpdatedDate, submittedDate
                - sort_order: ascending, descending

        Returns:
            List of ContentItem objects
        """
        try:
            # Build search query
            search_query = self._build_search_query(query, kwargs.get("category"))

            params = {
                "search_query": search_query,
                "start": offset,
                "max_results": min(limit, 100),  # arXiv max is 100
                "sortBy": kwargs.get("sort_by", "relevance"),
                "sortOrder": kwargs.get("sort_order", "descending"),
            }

            # Make request to Atom API
            response = await self.client.get(
                self.search_url,
                params=params,
                headers={"User-Agent": "AncientNerdsMap/1.0"},
            )
            response.raise_for_status()

            # Parse Atom feed
            root = ET.fromstring(response.text)
            items = []

            for entry in root.findall("atom:entry", ATOM_NAMESPACES):
                item = self._parse_atom_entry(entry)
                if item:
                    items.append(item)

            logger.info(f"arXiv search for '{query}' returned {len(items)} results")
            return items

        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """
        Get specific preprint by arXiv ID.

        Args:
            item_id: arXiv ID (e.g., "2301.00001" or "arxiv:2301.00001")

        Returns:
            ContentItem or None if not found
        """
        try:
            # Normalize ID
            if item_id.startswith("arxiv:"):
                item_id = item_id[6:]
            if item_id.startswith("oai:arXiv.org:"):
                item_id = item_id[14:]

            # Use Atom API for single item lookup
            params = {"id_list": item_id}

            response = await self.client.get(
                self.search_url,
                params=params,
                headers={"User-Agent": "AncientNerdsMap/1.0"},
            )
            response.raise_for_status()

            root = ET.fromstring(response.text)
            entry = root.find("atom:entry", ATOM_NAMESPACES)

            if entry is not None:
                return self._parse_atom_entry(entry)

            return None

        except Exception as e:
            logger.error(f"Failed to get arXiv paper {item_id}: {e}")
            return None

    async def harvest_by_set(
        self,
        set_spec: str,
        from_date: str | None = None,
        until_date: str | None = None,
        max_records: int = 100,
    ) -> list[ContentItem]:
        """
        Harvest papers from a specific arXiv set using OAI-PMH.

        Args:
            set_spec: arXiv set (e.g., "physics:physics.hist-ph")
            from_date: Start date (YYYY-MM-DD)
            until_date: End date (YYYY-MM-DD)
            max_records: Maximum records to retrieve

        Returns:
            List of ContentItem objects
        """
        items = []

        try:
            async for record in self.oai.list_all_records(
                metadata_prefix="oai_dc",
                set_spec=set_spec,
                from_date=from_date,
                until_date=until_date,
                max_records=max_records,
            ):
                if not record.deleted:
                    item = self._oai_record_to_content_item(record)
                    if item:
                        items.append(item)

            logger.info(f"Harvested {len(items)} papers from arXiv set {set_spec}")

        except Exception as e:
            logger.error(f"OAI-PMH harvest failed: {e}")

        return items

    async def harvest_recent(
        self,
        days: int = 7,
        categories: list[str] | None = None,
        max_records: int = 100,
    ) -> list[ContentItem]:
        """
        Harvest recent papers from specified categories.

        Args:
            days: Number of days back to harvest
            categories: List of arXiv categories (defaults to archaeology-related)
            max_records: Maximum records per category

        Returns:
            List of ContentItem objects
        """
        if categories is None:
            # Default to categories relevant to archaeology/history
            categories = [
                "physics:physics.hist-ph",
                "cs:cs.CY",
                "stat:stat.AP",
            ]

        from_date = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
        from_date_str = from_date.strftime("%Y-%m-%d")

        all_items = []
        for category in categories:
            items = await self.harvest_by_set(
                set_spec=category,
                from_date=from_date_str,
                max_records=max_records,
            )
            all_items.extend(items)

        return all_items

    async def get_repository_info(self) -> dict:
        """Get arXiv OAI-PMH repository information."""
        return await self.oai.identify()

    async def list_sets(self) -> list[dict]:
        """List available arXiv sets/categories."""
        return await self.oai.list_sets()

    def _build_search_query(
        self,
        query: str,
        category: str | None = None,
    ) -> str:
        """Build arXiv search query string."""
        # If query contains field prefixes, use as-is
        if any(f in query for f in ["all:", "ti:", "au:", "abs:", "cat:"]):
            search_query = query
        else:
            # Default to searching title only to reduce false positives
            search_query = f"ti:{query}"

        # Add category filter if specified
        if category:
            search_query = f"({search_query}) AND cat:{category}"

        return search_query

    def _parse_atom_entry(self, entry: ET.Element) -> ContentItem | None:
        """Parse an Atom entry into a ContentItem."""
        try:
            # Extract ID
            id_elem = entry.find("atom:id", ATOM_NAMESPACES)
            if id_elem is None or not id_elem.text:
                return None

            # arXiv IDs are like "http://arxiv.org/abs/2301.00001v1"
            arxiv_url = id_elem.text
            arxiv_id = self._extract_arxiv_id(arxiv_url)

            # Title
            title_elem = entry.find("atom:title", ATOM_NAMESPACES)
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            title = " ".join(title.split())  # Normalize whitespace

            # Summary/abstract
            summary_elem = entry.find("atom:summary", ATOM_NAMESPACES)
            description = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else None
            if description:
                description = " ".join(description.split())

            # Authors
            authors = []
            for author in entry.findall("atom:author", ATOM_NAMESPACES):
                name_elem = author.find("atom:name", ATOM_NAMESPACES)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)

            # Published date
            published_elem = entry.find("atom:published", ATOM_NAMESPACES)
            date = published_elem.text[:10] if published_elem is not None and published_elem.text else None
            date_numeric = int(date[:4]) if date else None

            # Categories
            categories = []
            for cat in entry.findall("arxiv:primary_category", ATOM_NAMESPACES):
                term = cat.get("term")
                if term:
                    categories.append(term)
            for cat in entry.findall("atom:category", ATOM_NAMESPACES):
                term = cat.get("term")
                if term and term not in categories:
                    categories.append(term)

            # Links
            pdf_url = None
            abs_url = None
            for link in entry.findall("atom:link", ATOM_NAMESPACES):
                rel = link.get("rel", "")
                href = link.get("href", "")
                link_type = link.get("type", "")

                if link_type == "application/pdf" or href.endswith(".pdf"):
                    pdf_url = href
                elif rel == "alternate":
                    abs_url = href

            # Limit authors to first 3 to avoid showing hundreds
            if len(authors) > 3:
                creator_str = ", ".join(authors[:3]) + " et al."
            else:
                creator_str = ", ".join(authors) if authors else None

            return ContentItem(
                id=f"arxiv:{arxiv_id}",
                source=self.connector_id,
                content_type=ContentType.PAPER,
                title=title,
                description=description,
                url=abs_url or arxiv_url,
                media_url=pdf_url,
                creator=creator_str,
                date=date,
                date_numeric=date_numeric,
                license=self.license,
                attribution=self.attribution,
                raw_data={
                    "arxiv_id": arxiv_id,
                    "categories": categories,
                    "authors": authors,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse arXiv entry: {e}")
            return None

    def _oai_record_to_content_item(self, record: OAIRecord) -> ContentItem | None:
        """Convert OAI-PMH record to ContentItem."""
        try:
            # Extract arXiv ID from OAI identifier
            # Format: oai:arXiv.org:2301.00001
            arxiv_id = record.identifier
            if arxiv_id.startswith("oai:arXiv.org:"):
                arxiv_id = arxiv_id[14:]

            title = record.title or ""
            description = record.description

            # Authors from Dublin Core
            authors = record.creators or []

            # Date
            date = record.date
            date_numeric = None
            if date:
                try:
                    date_numeric = int(date[:4])
                except (ValueError, IndexError):
                    pass

            # Categories from sets
            categories = record.set_specs or []

            # Build URLs
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            # Limit authors to first 3 to avoid showing hundreds
            if len(authors) > 3:
                creator_str = ", ".join(authors[:3]) + " et al."
            else:
                creator_str = ", ".join(authors) if authors else None

            return ContentItem(
                id=f"arxiv:{arxiv_id}",
                source=self.connector_id,
                content_type=ContentType.PAPER,
                title=title,
                description=description,
                url=abs_url,
                media_url=pdf_url,
                creator=creator_str,
                date=date,
                date_numeric=date_numeric,
                license=record.rights or self.license,
                attribution=self.attribution,
                raw_data={
                    "arxiv_id": arxiv_id,
                    "categories": categories,
                    "oai_identifier": record.identifier,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to convert OAI record: {e}")
            return None

    def _extract_arxiv_id(self, url_or_id: str) -> str:
        """Extract clean arXiv ID from URL or identifier."""
        # Handle URLs like http://arxiv.org/abs/2301.00001v1
        if "arxiv.org" in url_or_id:
            match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/\s]+)", url_or_id)
            if match:
                arxiv_id = match.group(1)
                # Remove version suffix
                arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
                return arxiv_id

        # Handle OAI identifiers
        if url_or_id.startswith("oai:arXiv.org:"):
            return url_or_id[14:]

        # Handle arxiv: prefix
        if url_or_id.startswith("arxiv:"):
            return url_or_id[6:]

        return url_or_id
