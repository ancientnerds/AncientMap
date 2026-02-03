"""
Perseus Digital Library Connector.

Source #23 from research paper.
Protocol: CTS (Canonical Text Services)
Auth: None
License: Open
Priority: P1

Perseus provides classical Greek and Latin texts via CTS protocol.
The main endpoints are:
- Traditional CTS: https://cts.perseids.org/api/cts
- Scaife Viewer: https://scaife.perseus.org/library/

References:
- Perseus: https://www.perseus.tufts.edu/hopper/
- Scaife: https://scaife.perseus.org/
- CTS: http://cite-architecture.org/cts/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.cts import (
    CTS_ENDPOINTS,
    CTSPassage,
    CTSProtocol,
    CTSWork,
)
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# Well-known classical texts for archaeology/history
CLASSICAL_WORKS = {
    # Greek Literature
    "homer_iliad": {
        "urn": "urn:cts:greekLit:tlg0012.tlg001",
        "title": "Iliad",
        "author": "Homer",
        "language": "grc",
        "description": "Epic poem about the Trojan War",
    },
    "homer_odyssey": {
        "urn": "urn:cts:greekLit:tlg0012.tlg002",
        "title": "Odyssey",
        "author": "Homer",
        "language": "grc",
        "description": "Epic poem about Odysseus' journey home",
    },
    "herodotus_histories": {
        "urn": "urn:cts:greekLit:tlg0016.tlg001",
        "title": "Histories",
        "author": "Herodotus",
        "language": "grc",
        "description": "Account of the Greco-Persian Wars",
    },
    "thucydides_peloponnesian": {
        "urn": "urn:cts:greekLit:tlg0003.tlg001",
        "title": "History of the Peloponnesian War",
        "author": "Thucydides",
        "language": "grc",
        "description": "History of the war between Athens and Sparta",
    },
    "pausanias_greece": {
        "urn": "urn:cts:greekLit:tlg0525.tlg001",
        "title": "Description of Greece",
        "author": "Pausanias",
        "language": "grc",
        "description": "Ancient travel guide to Greece and its monuments",
    },
    "strabo_geography": {
        "urn": "urn:cts:greekLit:tlg0099.tlg001",
        "title": "Geography",
        "author": "Strabo",
        "language": "grc",
        "description": "Encyclopedic work on geography of the known world",
    },
    "plato_republic": {
        "urn": "urn:cts:greekLit:tlg0059.tlg030",
        "title": "Republic",
        "author": "Plato",
        "language": "grc",
        "description": "Dialogue on justice and the ideal state",
    },
    "aristotle_politics": {
        "urn": "urn:cts:greekLit:tlg0086.tlg035",
        "title": "Politics",
        "author": "Aristotle",
        "language": "grc",
        "description": "Treatise on political philosophy",
    },
    # Latin Literature
    "vergil_aeneid": {
        "urn": "urn:cts:latinLit:phi0690.phi003",
        "title": "Aeneid",
        "author": "Virgil",
        "language": "lat",
        "description": "Epic poem on the founding of Rome",
    },
    "livy_history": {
        "urn": "urn:cts:latinLit:phi0914.phi001",
        "title": "Ab Urbe Condita",
        "author": "Livy",
        "language": "lat",
        "description": "History of Rome from its founding",
    },
    "tacitus_annals": {
        "urn": "urn:cts:latinLit:phi1351.phi005",
        "title": "Annals",
        "author": "Tacitus",
        "language": "lat",
        "description": "History of the Roman Empire",
    },
    "caesar_gallic": {
        "urn": "urn:cts:latinLit:phi0448.phi001",
        "title": "Commentarii de Bello Gallico",
        "author": "Julius Caesar",
        "language": "lat",
        "description": "Account of the Gallic Wars",
    },
    "pliny_natural": {
        "urn": "urn:cts:latinLit:phi0978.phi001",
        "title": "Naturalis Historia",
        "author": "Pliny the Elder",
        "language": "lat",
        "description": "Encyclopedic work on natural history",
    },
    "vitruvius_architecture": {
        "urn": "urn:cts:latinLit:phi1056.phi001",
        "title": "De Architectura",
        "author": "Vitruvius",
        "language": "lat",
        "description": "Treatise on architecture and engineering",
    },
}


@ConnectorRegistry.register
class PerseusConnector(BaseConnector):
    """
    Perseus Digital Library connector for classical texts.

    Provides access to Greek and Latin texts through the CTS protocol.
    Texts are retrieved by URN (Uniform Resource Name) following the
    CTS citation scheme.
    """

    connector_id = "perseus"
    connector_name = "Perseus Digital Library"
    description = "Classical Greek and Latin texts from Tufts University"

    content_types = [ContentType.PRIMARY_TEXT]

    base_url = "https://scaife.perseus.org"
    website_url = "https://www.perseus.tufts.edu"
    protocol = ProtocolType.CTS
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Open"
    attribution = "Perseus Digital Library, Tufts University"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)

        # Use Scaife Viewer API (modern JSON-based)
        self.cts = CTSProtocol(
            base_url=f"{self.base_url}/library/",
            api_version="api",
            rate_limit=self.rate_limit,
        )

        # Also have access to traditional CTS endpoint
        self.cts_xml = CTSProtocol(
            base_url=CTS_ENDPOINTS["perseus"],
            api_version="cts",
            rate_limit=self.rate_limit,
        )

    async def __aenter__(self):
        await self.cts.__aenter__()
        await self.cts_xml.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cts.__aexit__(exc_type, exc_val, exc_tb)
        await self.cts_xml.__aexit__(exc_type, exc_val, exc_tb)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search Perseus texts.

        Args:
            query: Search query (searches text content and metadata)
            content_type: Ignored (always returns PRIMARY_TEXT)
            limit: Maximum results
            offset: Result offset
            **kwargs: Additional parameters
                - language: Filter by language ("grc", "lat", "eng")
                - author: Filter by author name
                - urn: Search within specific work

        Returns:
            List of ContentItem objects
        """
        try:
            # First, try to search using the API
            passages = await self.cts.search(
                query=query,
                urn=kwargs.get("urn"),
                limit=limit,
            )

            items = []
            for passage in passages:
                item = self._passage_to_content_item(passage)
                if item:
                    # Apply relevance scoring
                    item.relevance_score = self._calculate_relevance(passage.text, query)
                    items.append(item)

            # If API search doesn't work, search known works by title/author
            if not items:
                items = self._search_known_works(query, limit)

            logger.info(f"Perseus search for '{query}' returned {len(items)} results")
            return items[:limit]

        except Exception as e:
            logger.error(f"Perseus search failed: {e}")
            # Fall back to searching known works
            return self._search_known_works(query, limit)

    async def get_item(self, item_id: str) -> ContentItem | None:
        """
        Get specific text by URN.

        Args:
            item_id: CTS URN (e.g., "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1")

        Returns:
            ContentItem or None
        """
        try:
            # Normalize ID
            if item_id.startswith("perseus:"):
                item_id = item_id[8:]

            # Ensure it's a valid URN
            if not item_id.startswith("urn:cts:"):
                # Try to find in known works
                for work_info in CLASSICAL_WORKS.values():
                    if item_id in work_info["urn"]:
                        item_id = work_info["urn"]
                        break

            # Get passage
            passage = await self.cts.get_passage(item_id)

            if passage:
                return self._passage_to_content_item(passage)

            # Try XML endpoint as fallback
            passage = await self.cts_xml.get_passage(item_id)
            if passage:
                return self._passage_to_content_item(passage)

            return None

        except Exception as e:
            logger.error(f"Failed to get Perseus text {item_id}: {e}")
            return None

    async def get_work(self, work_key: str) -> ContentItem | None:
        """
        Get a well-known classical work by key.

        Args:
            work_key: Key from CLASSICAL_WORKS (e.g., "homer_iliad")

        Returns:
            ContentItem with work metadata
        """
        work_info = CLASSICAL_WORKS.get(work_key)
        if not work_info:
            return None

        return ContentItem(
            id=f"perseus:{work_info['urn']}",
            source=self.connector_id,
            content_type=ContentType.PRIMARY_TEXT,
            title=work_info["title"],
            description=work_info.get("description"),
            url=f"{self.base_url}/reader/{work_info['urn']}/",
            creator=work_info.get("author"),
            license=self.license,
            attribution=self.attribution,
            raw_data={
                "urn": work_info["urn"],
                "language": work_info.get("language"),
                "work_key": work_key,
            },
        )

    async def get_available_works(self) -> list[CTSWork]:
        """
        Get list of all available works in Perseus.

        Returns:
            List of CTSWork objects
        """
        try:
            return await self.cts.get_capabilities()
        except Exception as e:
            logger.error(f"Failed to get Perseus capabilities: {e}")
            return []

    async def get_passage(
        self,
        urn: str,
        with_navigation: bool = True,
    ) -> CTSPassage | None:
        """
        Get a text passage by URN.

        Args:
            urn: CTS URN with passage reference
            with_navigation: Include prev/next URNs

        Returns:
            CTSPassage object
        """
        try:
            if with_navigation:
                return await self.cts.get_passage_plus(urn)
            else:
                return await self.cts.get_passage(urn)
        except Exception as e:
            logger.error(f"Failed to get passage {urn}: {e}")
            return None

    async def get_table_of_contents(
        self,
        urn: str,
        level: int = 1,
    ) -> list[dict]:
        """
        Get table of contents for a work.

        Args:
            urn: Work URN (without passage reference)
            level: Citation level (1 = book, 2 = chapter, etc.)

        Returns:
            List of reference dictionaries
        """
        try:
            refs = await self.cts.get_valid_reff(urn, level)
            return [{"urn": ref.urn, "label": ref.label} for ref in refs]
        except Exception as e:
            logger.error(f"Failed to get TOC for {urn}: {e}")
            return []

    async def get_homer_iliad(
        self,
        book: int | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        language: str = "grc",
    ) -> ContentItem | None:
        """
        Convenience method to get Homer's Iliad.

        Args:
            book: Book number (1-24)
            line_start: Starting line number
            line_end: Ending line number (defaults to line_start)
            language: "grc" for Greek, "eng" for English

        Returns:
            ContentItem with the requested passage
        """
        version = "perseus-grc2" if language == "grc" else "perseus-eng2"
        urn = f"urn:cts:greekLit:tlg0012.tlg001.{version}"

        if book:
            passage_ref = str(book)
            if line_start:
                passage_ref = f"{book}.{line_start}"
                if line_end and line_end != line_start:
                    passage_ref = f"{book}.{line_start}-{book}.{line_end}"
            urn = f"{urn}:{passage_ref}"

        return await self.get_item(urn)

    async def get_homer_odyssey(
        self,
        book: int | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        language: str = "grc",
    ) -> ContentItem | None:
        """
        Convenience method to get Homer's Odyssey.

        Args:
            book: Book number (1-24)
            line_start: Starting line number
            line_end: Ending line number
            language: "grc" for Greek, "eng" for English

        Returns:
            ContentItem with the requested passage
        """
        version = "perseus-grc2" if language == "grc" else "perseus-eng2"
        urn = f"urn:cts:greekLit:tlg0012.tlg002.{version}"

        if book:
            passage_ref = str(book)
            if line_start:
                passage_ref = f"{book}.{line_start}"
                if line_end and line_end != line_start:
                    passage_ref = f"{book}.{line_start}-{book}.{line_end}"
            urn = f"{urn}:{passage_ref}"

        return await self.get_item(urn)

    def _passage_to_content_item(self, passage: CTSPassage) -> ContentItem:
        """Convert CTSPassage to ContentItem."""
        # Parse URN for metadata
        urn_parts = CTSProtocol.parse_urn(passage.urn)

        # Find matching known work for metadata
        title = passage.title or passage.work_title
        author = passage.author
        language = passage.language

        for work_info in CLASSICAL_WORKS.values():
            if work_info["urn"] in passage.urn:
                title = title or f"{work_info['title']} - {urn_parts.get('passage', '')}"
                author = author or work_info.get("author")
                language = language or work_info.get("language")
                break

        # Build URL
        if urn_parts.get("passage"):
            url = f"{self.base_url}/reader/{passage.urn}/"
        else:
            url = f"{self.base_url}/library/{passage.urn}/"

        return ContentItem(
            id=f"perseus:{passage.urn}",
            source=self.connector_id,
            content_type=ContentType.PRIMARY_TEXT,
            title=title or passage.urn,
            description=passage.text[:500] + "..." if len(passage.text) > 500 else passage.text,
            url=url,
            creator=author,
            license=self.license,
            attribution=self.attribution,
            raw_data={
                "urn": passage.urn,
                "language": language,
                "namespace": urn_parts.get("namespace"),
                "textgroup": urn_parts.get("textgroup"),
                "work": urn_parts.get("work"),
                "version": urn_parts.get("version"),
                "passage": urn_parts.get("passage"),
                "prev_urn": passage.prev_urn,
                "next_urn": passage.next_urn,
                "text": passage.text,
            },
        )

    def _search_known_works(self, query: str, limit: int) -> list[ContentItem]:
        """Search through known classical works by metadata."""
        query_lower = query.lower()
        results = []

        for work_key, work_info in CLASSICAL_WORKS.items():
            # Check if query matches title, author, or description
            searchable = " ".join([
                work_info.get("title", ""),
                work_info.get("author", ""),
                work_info.get("description", ""),
            ]).lower()

            if query_lower in searchable:
                item = ContentItem(
                    id=f"perseus:{work_info['urn']}",
                    source=self.connector_id,
                    content_type=ContentType.PRIMARY_TEXT,
                    title=work_info["title"],
                    description=work_info.get("description"),
                    url=f"{self.base_url}/reader/{work_info['urn']}/",
                    creator=work_info.get("author"),
                    license=self.license,
                    attribution=self.attribution,
                    raw_data={
                        "urn": work_info["urn"],
                        "language": work_info.get("language"),
                        "work_key": work_key,
                    },
                )
                # Score by how early the match appears
                item.relevance_score = 1.0 if query_lower in work_info.get("title", "").lower() else 0.5
                results.append(item)

        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]

    def _calculate_relevance(self, text: str, query: str) -> float:
        """Calculate relevance score for a passage."""
        if not text or not query:
            return 0.0

        text_lower = text.lower()
        query_lower = query.lower()
        query_terms = query_lower.split()

        # Count term occurrences
        total_matches = sum(text_lower.count(term) for term in query_terms)

        # Normalize by text length
        score = min(1.0, total_matches / max(1, len(text) / 100))

        return score
