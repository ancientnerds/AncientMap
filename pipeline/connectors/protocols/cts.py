"""
CTS (Canonical Text Services) Protocol Handler.

Provides CTS protocol support for accessing classical texts from repositories
like the Perseus Digital Library.

CTS is a standard for citing and retrieving passages of text using URNs.
URN format: urn:cts:NAMESPACE:WORK:PASSAGE

CTS Requests:
- GetCapabilities: List available texts in a repository
- GetValidReff: Get valid passage references for a work
- GetPassage: Retrieve text content by URN
- GetPassagePlus: Get passage with metadata
- GetFirstUrn/GetPrevNextUrn: Navigation helpers

References:
- CTS spec: http://cite-architecture.org/cts/
- Perseus CTS: http://cts.perseids.org/
- Scaife Viewer API: https://scaife.perseus.org/
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

# CTS XML namespaces
CTS_NAMESPACES = {
    "cts": "http://chs.harvard.edu/xmlns/cts",
    "ti": "http://chs.harvard.edu/xmlns/cts/ti",
    "tei": "http://www.tei-c.org/ns/1.0",
    "dc": "http://purl.org/dc/elements/1.1/",
}


@dataclass
class CTSWork:
    """Represents a CTS text work."""

    urn: str
    title: str
    language: str | None = None
    description: str | None = None

    # Grouping
    textgroup: str | None = None
    textgroup_name: str | None = None

    # Editions/translations
    edition: str | None = None
    label: str | None = None

    # Citation scheme
    citation_scheme: list[str] = field(default_factory=list)


@dataclass
class CTSPassage:
    """Represents a CTS text passage."""

    urn: str
    text: str
    language: str | None = None

    # Reference info
    prev_urn: str | None = None
    next_urn: str | None = None

    # Metadata
    title: str | None = None
    work_title: str | None = None
    author: str | None = None

    # Raw TEI/XML for advanced processing
    raw_xml: str | None = None


@dataclass
class CTSReference:
    """Represents a valid CTS reference/citation."""

    urn: str
    level: int
    label: str | None = None
    children: list["CTSReference"] = field(default_factory=list)


class CTSProtocol:
    """
    CTS (Canonical Text Services) protocol handler.

    Provides access to classical texts via CTS-compliant endpoints.
    Supports both traditional CTS/XML endpoints and modern JSON APIs.
    """

    def __init__(
        self,
        base_url: str,
        api_version: str = "cts",  # "cts" for XML, "api" for JSON
        timeout: float = 30.0,
        rate_limit: float = 2.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize CTS protocol handler.

        Args:
            base_url: CTS endpoint URL
            api_version: API type ("cts" for XML, "api" for JSON/Scaife)
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second
            http_client: Optional shared HTTP client
        """
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
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
        """Enforce rate limiting between requests."""
        if self.rate_limit <= 0:
            return

        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._last_request_time = asyncio.get_event_loop().time()

    async def _request_xml(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        """Make CTS XML request."""
        await self._rate_limit()

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com)",
            "Accept": "application/xml, text/xml",
        }

        logger.debug(f"CTS request: {url}")

        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()

        return ET.fromstring(response.text)

    async def _request_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make CTS JSON request (Scaife-style API)."""
        await self._rate_limit()

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com)",
            "Accept": "application/json",
        }

        logger.debug(f"CTS JSON request: {url}")

        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()

        return response.json()

    async def get_capabilities(self) -> list[CTSWork]:
        """
        Get list of available texts (TextInventory).

        Returns:
            List of CTSWork objects representing available texts
        """
        try:
            if self.api_version == "api":
                return await self._get_capabilities_json()
            else:
                return await self._get_capabilities_xml()
        except Exception as e:
            logger.error(f"Failed to get CTS capabilities: {e}")
            return []

    async def _get_capabilities_xml(self) -> list[CTSWork]:
        """Get capabilities via XML CTS endpoint."""
        root = await self._request_xml("GetCapabilities")

        works = []
        for textgroup in root.findall(".//ti:textgroup", CTS_NAMESPACES):
            tg_urn = textgroup.get("urn", "")
            tg_name = self._get_text_xml(textgroup, ".//ti:groupname")

            for work_elem in textgroup.findall(".//ti:work", CTS_NAMESPACES):
                work_elem.get("urn", "")
                work_title = self._get_text_xml(work_elem, ".//ti:title")
                work_lang = work_elem.get("{http://www.w3.org/XML/1998/namespace}lang")

                # Get editions
                for edition in work_elem.findall(".//ti:edition", CTS_NAMESPACES):
                    ed_urn = edition.get("urn", "")
                    ed_label = self._get_text_xml(edition, ".//ti:label")
                    ed_desc = self._get_text_xml(edition, ".//ti:description")

                    # Parse citation scheme
                    citations = []
                    for cit in edition.findall(".//ti:citation", CTS_NAMESPACES):
                        label = cit.get("label")
                        if label:
                            citations.append(label)

                    works.append(CTSWork(
                        urn=ed_urn,
                        title=work_title or ed_label or "",
                        language=work_lang,
                        description=ed_desc,
                        textgroup=tg_urn,
                        textgroup_name=tg_name,
                        edition=ed_urn,
                        label=ed_label,
                        citation_scheme=citations,
                    ))

        return works

    async def _get_capabilities_json(self) -> list[CTSWork]:
        """Get capabilities via JSON API (Scaife-style)."""
        data = await self._request_json("library/")

        works = []
        # JSON API structure varies by implementation
        for item in data.get("textGroups", data.get("texts", [])):
            works.append(CTSWork(
                urn=item.get("urn", ""),
                title=item.get("title", item.get("label", "")),
                language=item.get("lang"),
                description=item.get("description"),
            ))

        return works

    async def get_valid_reff(
        self,
        urn: str,
        level: int = 1,
    ) -> list[CTSReference]:
        """
        Get valid references for a work at a given level.

        Args:
            urn: Work URN (e.g., urn:cts:greekLit:tlg0012.tlg001.perseus-grc2)
            level: Citation level (1 = book, 2 = chapter, etc.)

        Returns:
            List of CTSReference objects
        """
        try:
            if self.api_version == "api":
                return await self._get_valid_reff_json(urn, level)
            else:
                return await self._get_valid_reff_xml(urn, level)
        except Exception as e:
            logger.error(f"Failed to get valid refs for {urn}: {e}")
            return []

    async def _get_valid_reff_xml(self, urn: str, level: int) -> list[CTSReference]:
        """Get valid references via XML endpoint."""
        params = {"urn": urn, "level": str(level)}
        root = await self._request_xml("GetValidReff", params)

        refs = []
        for reff in root.findall(".//cts:reff/cts:urn", CTS_NAMESPACES):
            if reff.text:
                refs.append(CTSReference(
                    urn=reff.text.strip(),
                    level=level,
                ))

        return refs

    async def _get_valid_reff_json(self, urn: str, level: int) -> list[CTSReference]:
        """Get valid references via JSON API."""
        # Scaife-style: /library/{urn}/toc/
        path = f"library/{urn}/toc/"
        data = await self._request_json(path)

        refs = []
        for item in data.get("toc", data.get("references", [])):
            if isinstance(item, str):
                refs.append(CTSReference(urn=item, level=level))
            elif isinstance(item, dict):
                refs.append(CTSReference(
                    urn=item.get("urn", ""),
                    level=level,
                    label=item.get("label"),
                ))

        return refs

    async def get_passage(
        self,
        urn: str,
    ) -> CTSPassage | None:
        """
        Get a text passage by URN.

        Args:
            urn: Passage URN (e.g., urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1-1.10)

        Returns:
            CTSPassage object or None if not found
        """
        try:
            if self.api_version == "api":
                return await self._get_passage_json(urn)
            else:
                return await self._get_passage_xml(urn)
        except Exception as e:
            logger.error(f"Failed to get passage {urn}: {e}")
            return None

    async def _get_passage_xml(self, urn: str) -> CTSPassage | None:
        """Get passage via XML CTS endpoint."""
        params = {"urn": urn}
        root = await self._request_xml("GetPassage", params)

        # Find passage content
        passage_elem = root.find(".//cts:passage", CTS_NAMESPACES)
        if passage_elem is None:
            # Try TEI body
            passage_elem = root.find(".//tei:body", CTS_NAMESPACES)

        if passage_elem is None:
            return None

        # Extract text content (strip tags)
        text = self._extract_text(passage_elem)

        # Get navigation URNs
        prev_elem = root.find(".//cts:prevnext/cts:prev", CTS_NAMESPACES)
        next_elem = root.find(".//cts:prevnext/cts:next", CTS_NAMESPACES)

        return CTSPassage(
            urn=urn,
            text=text,
            prev_urn=prev_elem.text if prev_elem is not None and prev_elem.text else None,
            next_urn=next_elem.text if next_elem is not None and next_elem.text else None,
            raw_xml=ET.tostring(passage_elem, encoding="unicode"),
        )

    async def _get_passage_json(self, urn: str) -> CTSPassage | None:
        """Get passage via JSON API."""
        # Scaife-style: /library/passage/{urn}/
        path = f"library/passage/{urn}/"
        data = await self._request_json(path)

        text = data.get("text_content", data.get("content", ""))

        return CTSPassage(
            urn=urn,
            text=text,
            title=data.get("title"),
            work_title=data.get("work_title"),
            author=data.get("author"),
            prev_urn=data.get("prev"),
            next_urn=data.get("next"),
        )

    async def get_passage_plus(
        self,
        urn: str,
    ) -> CTSPassage | None:
        """
        Get passage with additional metadata.

        Args:
            urn: Passage URN

        Returns:
            CTSPassage with metadata
        """
        params = {"urn": urn}

        try:
            root = await self._request_xml("GetPassagePlus", params)

            # Parse passage
            passage = await self._get_passage_xml(urn)
            if passage is None:
                return None

            # Add metadata
            label = root.find(".//cts:label", CTS_NAMESPACES)
            if label is not None and label.text:
                passage.title = label.text

            return passage

        except Exception:
            # Fall back to regular GetPassage
            return await self.get_passage(urn)

    async def get_first_urn(self, urn: str) -> str | None:
        """Get the first valid URN for a work."""
        refs = await self.get_valid_reff(urn, level=1)
        if refs:
            return refs[0].urn
        return None

    async def search(
        self,
        query: str,
        urn: str | None = None,
        limit: int = 20,
    ) -> list[CTSPassage]:
        """
        Search for text matching query.

        Note: Not all CTS endpoints support search. This method
        tries JSON API search if available.

        Args:
            query: Search query
            urn: Optional URN to limit search scope
            limit: Maximum results

        Returns:
            List of matching passages
        """
        try:
            if self.api_version == "api":
                # Scaife-style search
                params = {"q": query, "size": str(limit)}
                if urn:
                    params["urn"] = urn

                data = await self._request_json("search/", params)

                passages = []
                for hit in data.get("hits", data.get("results", [])):
                    passages.append(CTSPassage(
                        urn=hit.get("urn", ""),
                        text=hit.get("content", hit.get("text", "")),
                        title=hit.get("title"),
                    ))

                return passages

            else:
                logger.warning("Search not supported on XML CTS endpoints")
                return []

        except Exception as e:
            logger.error(f"CTS search failed: {e}")
            return []

    def _get_text_xml(self, elem: ET.Element, path: str) -> str | None:
        """Get text from element path."""
        child = elem.find(path, CTS_NAMESPACES)
        if child is not None and child.text:
            return child.text.strip()
        return None

    def _extract_text(self, elem: ET.Element) -> str:
        """Extract all text content from element, stripping tags."""
        texts = []
        if elem.text:
            texts.append(elem.text)
        for child in elem:
            texts.append(self._extract_text(child))
            if child.tail:
                texts.append(child.tail)
        return " ".join(texts).strip()

    @staticmethod
    def parse_urn(urn: str) -> dict[str, str | None]:
        """
        Parse a CTS URN into components.

        URN format: urn:cts:NAMESPACE:TEXTGROUP.WORK.VERSION:PASSAGE

        Args:
            urn: CTS URN string

        Returns:
            Dictionary with parsed components
        """
        pattern = r"^urn:cts:([^:]+):([^.]+)\.([^.]+)(?:\.([^:]+))?(?::(.+))?$"
        match = re.match(pattern, urn)

        if not match:
            return {
                "namespace": None,
                "textgroup": None,
                "work": None,
                "version": None,
                "passage": None,
            }

        return {
            "namespace": match.group(1),
            "textgroup": match.group(2),
            "work": match.group(3),
            "version": match.group(4),
            "passage": match.group(5),
        }

    @staticmethod
    def build_urn(
        namespace: str,
        textgroup: str,
        work: str,
        version: str | None = None,
        passage: str | None = None,
    ) -> str:
        """
        Build a CTS URN from components.

        Args:
            namespace: Namespace (e.g., "greekLit")
            textgroup: Text group ID (e.g., "tlg0012")
            work: Work ID (e.g., "tlg001")
            version: Edition/translation version
            passage: Passage reference (e.g., "1.1-1.10")

        Returns:
            CTS URN string
        """
        urn = f"urn:cts:{namespace}:{textgroup}.{work}"
        if version:
            urn = f"{urn}.{version}"
        if passage:
            urn = f"{urn}:{passage}"
        return urn


class CTSError(Exception):
    """CTS protocol error."""

    def __init__(self, message: str, urn: str | None = None):
        self.message = message
        self.urn = urn
        super().__init__(f"CTS error: {message}" + (f" (URN: {urn})" if urn else ""))


# Well-known CTS endpoints
CTS_ENDPOINTS = {
    "perseus": "https://cts.perseids.org/api/cts",
    "scaife": "https://scaife.perseus.org/library/",
    "perseids": "https://cts.perseids.org/api/cts",
    "croala": "http://croala.ffzg.unizg.hr/basex/cts",
}

# Well-known text URN prefixes
CTS_NAMESPACES_INFO = {
    "greekLit": {
        "name": "Greek Literature",
        "description": "Classical Greek texts",
        "examples": ["tlg0012.tlg001 (Homer, Iliad)", "tlg0012.tlg002 (Homer, Odyssey)"],
    },
    "latinLit": {
        "name": "Latin Literature",
        "description": "Classical Latin texts",
        "examples": ["phi0472.phi001 (Vergil, Aeneid)", "phi0631.phi001 (Cicero)"],
    },
    "pdlrefwk": {
        "name": "Perseus Reference Works",
        "description": "Lexica, grammars, and reference works",
        "examples": ["lsj (Liddell-Scott-Jones)", "lewis (Lewis & Short)"],
    },
}

# Common Homer URNs for testing
HOMER_URNS = {
    "iliad_greek": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2",
    "iliad_english": "urn:cts:greekLit:tlg0012.tlg001.perseus-eng2",
    "odyssey_greek": "urn:cts:greekLit:tlg0012.tlg002.perseus-grc2",
    "odyssey_english": "urn:cts:greekLit:tlg0012.tlg002.perseus-eng2",
}
