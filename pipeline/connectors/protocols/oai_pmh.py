"""
OAI-PMH Protocol Handler.

Provides OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting)
support for harvesting metadata from repositories like arXiv.

OAI-PMH Verbs:
- Identify: Get repository information
- ListMetadataFormats: List available metadata formats
- ListSets: List available sets/collections
- ListIdentifiers: List record identifiers (headers only)
- ListRecords: List full records with metadata
- GetRecord: Get a single record by identifier

References:
- OAI-PMH spec: http://www.openarchives.org/OAI/openarchivesprotocol.html
- arXiv OAI: https://arxiv.org/help/oa
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

# OAI-PMH XML namespaces
OAI_NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


@dataclass
class OAIRecord:
    """Represents a single OAI-PMH record."""

    identifier: str
    datestamp: str | None = None
    set_specs: list[str] | None = None
    deleted: bool = False
    metadata: dict[str, Any] | None = None
    about: list[str] | None = None

    # Dublin Core fields (common metadata format)
    title: str | None = None
    creators: list[str] | None = None
    subjects: list[str] | None = None
    description: str | None = None
    publisher: str | None = None
    contributors: list[str] | None = None
    date: str | None = None
    type: str | None = None
    format: str | None = None
    source: str | None = None
    language: str | None = None
    relation: str | None = None
    coverage: str | None = None
    rights: str | None = None


@dataclass
class OAIListResult:
    """Result of a ListRecords or ListIdentifiers request."""

    records: list[OAIRecord]
    resumption_token: str | None = None
    complete_list_size: int | None = None
    cursor: int | None = None
    expiration_date: str | None = None


class OAIPMHProtocol:
    """
    OAI-PMH protocol handler for metadata harvesting.

    Supports all OAI-PMH verbs with proper error handling,
    resumption token support, and Dublin Core parsing.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        rate_limit: float = 0.33,  # arXiv requires 3-second delay
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize OAI-PMH protocol handler.

        Args:
            base_url: OAI-PMH base URL (e.g., http://export.arxiv.org/oai2)
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second (default 0.33 = 3s delay)
            http_client: Optional shared HTTP client
        """
        self.base_url = base_url.rstrip("/")
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

    async def _request(
        self,
        verb: str,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        """
        Make OAI-PMH request and return parsed XML.

        Args:
            verb: OAI-PMH verb (Identify, ListRecords, etc.)
            params: Additional parameters

        Returns:
            Parsed XML root element

        Raises:
            OAIError: For OAI-PMH protocol errors
            httpx.HTTPStatusError: For HTTP errors
        """
        await self._rate_limit()

        request_params = {"verb": verb}
        if params:
            request_params.update(params)

        headers = {
            "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com)",
            "Accept": "application/xml, text/xml",
        }

        logger.debug(f"OAI-PMH request: {verb} to {self.base_url}")

        response = await self.client.get(
            self.base_url,
            params=request_params,
            headers=headers,
        )
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.text)

        # Check for OAI-PMH errors
        error = root.find("oai:error", OAI_NAMESPACES)
        if error is not None:
            error_code = error.get("code", "unknown")
            error_msg = error.text or "Unknown error"
            raise OAIError(error_code, error_msg)

        return root

    async def identify(self) -> dict[str, Any]:
        """
        Get repository information.

        Returns:
            Dictionary with repository info (name, baseURL, protocolVersion, etc.)
        """
        root = await self._request("Identify")

        identify = root.find("oai:Identify", OAI_NAMESPACES)
        if identify is None:
            return {}

        info = {}
        fields = [
            "repositoryName", "baseURL", "protocolVersion",
            "adminEmail", "earliestDatestamp", "deletedRecord",
            "granularity",
        ]

        for field in fields:
            elem = identify.find(f"oai:{field}", OAI_NAMESPACES)
            if elem is not None and elem.text:
                info[field] = elem.text

        return info

    async def list_metadata_formats(
        self,
        identifier: str | None = None,
    ) -> list[dict[str, str]]:
        """
        List available metadata formats.

        Args:
            identifier: Optional record identifier to get formats for

        Returns:
            List of format dictionaries with metadataPrefix, schema, namespace
        """
        params = {}
        if identifier:
            params["identifier"] = identifier

        root = await self._request("ListMetadataFormats", params)

        formats = []
        for fmt in root.findall(".//oai:metadataFormat", OAI_NAMESPACES):
            format_info = {}
            for field in ["metadataPrefix", "schema", "metadataNamespace"]:
                elem = fmt.find(f"oai:{field}", OAI_NAMESPACES)
                if elem is not None and elem.text:
                    format_info[field] = elem.text
            formats.append(format_info)

        return formats

    async def list_sets(self) -> list[dict[str, str]]:
        """
        List available sets/collections.

        Returns:
            List of set dictionaries with setSpec, setName
        """
        root = await self._request("ListSets")

        sets = []
        for set_elem in root.findall(".//oai:set", OAI_NAMESPACES):
            set_info = {}
            for field in ["setSpec", "setName"]:
                elem = set_elem.find(f"oai:{field}", OAI_NAMESPACES)
                if elem is not None and elem.text:
                    set_info[field] = elem.text
            sets.append(set_info)

        return sets

    async def get_record(
        self,
        identifier: str,
        metadata_prefix: str = "oai_dc",
    ) -> OAIRecord | None:
        """
        Get a single record by identifier.

        Args:
            identifier: OAI record identifier (e.g., oai:arXiv.org:2301.00001)
            metadata_prefix: Metadata format (default: oai_dc for Dublin Core)

        Returns:
            OAIRecord or None if not found
        """
        params = {
            "identifier": identifier,
            "metadataPrefix": metadata_prefix,
        }

        try:
            root = await self._request("GetRecord", params)

            record_elem = root.find(".//oai:record", OAI_NAMESPACES)
            if record_elem is None:
                return None

            return self._parse_record(record_elem)

        except OAIError as e:
            if e.code == "idDoesNotExist":
                return None
            raise

    async def list_records(
        self,
        metadata_prefix: str = "oai_dc",
        from_date: str | None = None,
        until_date: str | None = None,
        set_spec: str | None = None,
        resumption_token: str | None = None,
    ) -> OAIListResult:
        """
        List records from the repository.

        Args:
            metadata_prefix: Metadata format (default: oai_dc)
            from_date: Harvest from this date (YYYY-MM-DD or ISO datetime)
            until_date: Harvest until this date
            set_spec: Limit to specific set
            resumption_token: Token from previous incomplete list

        Returns:
            OAIListResult with records and optional resumption token
        """
        if resumption_token:
            params = {"resumptionToken": resumption_token}
        else:
            params = {"metadataPrefix": metadata_prefix}
            if from_date:
                params["from"] = from_date
            if until_date:
                params["until"] = until_date
            if set_spec:
                params["set"] = set_spec

        root = await self._request("ListRecords", params)

        records = []
        for record_elem in root.findall(".//oai:record", OAI_NAMESPACES):
            record = self._parse_record(record_elem)
            if record:
                records.append(record)

        # Parse resumption token
        result = OAIListResult(records=records)
        token_elem = root.find(".//oai:resumptionToken", OAI_NAMESPACES)
        if token_elem is not None:
            result.resumption_token = token_elem.text
            if token_elem.get("completeListSize"):
                result.complete_list_size = int(token_elem.get("completeListSize"))
            if token_elem.get("cursor"):
                result.cursor = int(token_elem.get("cursor"))
            if token_elem.get("expirationDate"):
                result.expiration_date = token_elem.get("expirationDate")

        return result

    async def list_all_records(
        self,
        metadata_prefix: str = "oai_dc",
        from_date: str | None = None,
        until_date: str | None = None,
        set_spec: str | None = None,
        max_records: int = 1000,
    ) -> AsyncIterator[OAIRecord]:
        """
        Iterate through all records, handling resumption tokens.

        Args:
            metadata_prefix: Metadata format
            from_date: Harvest from date
            until_date: Harvest until date
            set_spec: Limit to set
            max_records: Maximum records to retrieve

        Yields:
            OAIRecord objects
        """
        count = 0
        resumption_token = None

        while count < max_records:
            result = await self.list_records(
                metadata_prefix=metadata_prefix,
                from_date=from_date if resumption_token is None else None,
                until_date=until_date if resumption_token is None else None,
                set_spec=set_spec if resumption_token is None else None,
                resumption_token=resumption_token,
            )

            for record in result.records:
                if count >= max_records:
                    return
                yield record
                count += 1

            if not result.resumption_token:
                break

            resumption_token = result.resumption_token

    async def list_identifiers(
        self,
        metadata_prefix: str = "oai_dc",
        from_date: str | None = None,
        until_date: str | None = None,
        set_spec: str | None = None,
        resumption_token: str | None = None,
    ) -> OAIListResult:
        """
        List record identifiers (headers only, no metadata).

        More efficient than ListRecords when you only need identifiers.

        Args:
            metadata_prefix: Metadata format
            from_date: From date
            until_date: Until date
            set_spec: Set specification
            resumption_token: Resumption token

        Returns:
            OAIListResult with records (header info only)
        """
        if resumption_token:
            params = {"resumptionToken": resumption_token}
        else:
            params = {"metadataPrefix": metadata_prefix}
            if from_date:
                params["from"] = from_date
            if until_date:
                params["until"] = until_date
            if set_spec:
                params["set"] = set_spec

        root = await self._request("ListIdentifiers", params)

        records = []
        for header_elem in root.findall(".//oai:header", OAI_NAMESPACES):
            record = OAIRecord(
                identifier=self._get_text(header_elem, "oai:identifier"),
                datestamp=self._get_text(header_elem, "oai:datestamp"),
                set_specs=[
                    s.text for s in header_elem.findall("oai:setSpec", OAI_NAMESPACES)
                    if s.text
                ],
                deleted=header_elem.get("status") == "deleted",
            )
            records.append(record)

        result = OAIListResult(records=records)
        token_elem = root.find(".//oai:resumptionToken", OAI_NAMESPACES)
        if token_elem is not None:
            result.resumption_token = token_elem.text
            if token_elem.get("completeListSize"):
                result.complete_list_size = int(token_elem.get("completeListSize"))

        return result

    def _parse_record(self, record_elem: ET.Element) -> OAIRecord | None:
        """Parse a single record element."""
        header = record_elem.find("oai:header", OAI_NAMESPACES)
        if header is None:
            return None

        record = OAIRecord(
            identifier=self._get_text(header, "oai:identifier"),
            datestamp=self._get_text(header, "oai:datestamp"),
            set_specs=[
                s.text for s in header.findall("oai:setSpec", OAI_NAMESPACES)
                if s.text
            ],
            deleted=header.get("status") == "deleted",
        )

        # Parse Dublin Core metadata if present
        metadata = record_elem.find("oai:metadata", OAI_NAMESPACES)
        if metadata is not None:
            dc = metadata.find("oai_dc:dc", OAI_NAMESPACES)
            if dc is not None:
                record.title = self._get_text(dc, "dc:title")
                record.creators = self._get_all_text(dc, "dc:creator")
                record.subjects = self._get_all_text(dc, "dc:subject")
                record.description = self._get_text(dc, "dc:description")
                record.publisher = self._get_text(dc, "dc:publisher")
                record.contributors = self._get_all_text(dc, "dc:contributor")
                record.date = self._get_text(dc, "dc:date")
                record.type = self._get_text(dc, "dc:type")
                record.format = self._get_text(dc, "dc:format")
                record.source = self._get_text(dc, "dc:source")
                record.language = self._get_text(dc, "dc:language")
                record.relation = self._get_text(dc, "dc:relation")
                record.coverage = self._get_text(dc, "dc:coverage")
                record.rights = self._get_text(dc, "dc:rights")

        return record

    def _get_text(self, elem: ET.Element, path: str) -> str | None:
        """Get text from a child element."""
        child = elem.find(path, OAI_NAMESPACES)
        if child is not None and child.text:
            return child.text.strip()
        return None

    def _get_all_text(self, elem: ET.Element, path: str) -> list[str]:
        """Get text from all matching child elements."""
        return [
            child.text.strip()
            for child in elem.findall(path, OAI_NAMESPACES)
            if child.text
        ]


class OAIError(Exception):
    """OAI-PMH protocol error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"OAI-PMH error [{code}]: {message}")


# Common arXiv sets/categories for archaeology-related content
ARXIV_ARCHAEOLOGY_SETS = [
    "physics:physics.hist-ph",  # History and Philosophy of Physics
    "cs:cs.CY",  # Computers and Society
    "stat:stat.AP",  # Applications (Statistics)
    "physics:physics.soc-ph",  # Physics and Society
]
