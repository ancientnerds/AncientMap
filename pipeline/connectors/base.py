"""
Base connector class for all external data source integrations.

All source-specific connectors inherit from BaseConnector and implement
the required abstract methods for search and retrieval.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime

import httpx
from loguru import logger

from pipeline.connectors.types import (
    AuthType,
    ContentItem,
    ContentType,
    HealthCheckResult,
    ProtocolType,
    SourceInfo,
)


class BaseConnector(ABC):
    """
    Abstract base class for all content connectors.

    Subclasses must implement:
    - search(): Search for content matching a query
    - get_item(): Get a specific item by ID

    Optional methods to override:
    - get_by_location(): Get content near geographic coordinates
    - get_by_period(): Get content from a time period
    - get_by_empire(): Get content related to an empire/civilization
    - batch_fetch(): Fetch all items for pre-computation
    """

    # Class attributes to be set by subclasses
    connector_id: str = None  # e.g., "met_museum"
    connector_name: str = None  # e.g., "Metropolitan Museum of Art"
    description: str = None

    # What types of content this connector provides
    content_types: list[ContentType] = []

    # Configuration
    base_url: str = None
    protocol: ProtocolType = ProtocolType.REST
    rate_limit: float = 1.0  # Requests per second
    timeout: float = 30.0  # Request timeout in seconds

    # Authentication
    requires_auth: bool = False
    auth_type: AuthType = AuthType.NONE

    # Licensing
    license: str = None
    attribution: str = None

    def __init__(
        self,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize the connector.

        Args:
            api_key: API key for authenticated sources
            http_client: Optional shared HTTP client
        """
        if self.connector_id is None:
            raise ValueError("connector_id must be set in subclass")

        self.api_key = api_key
        self._http_client = http_client
        self._owns_client = http_client is None

        # Rate limiting state
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

        logger.info(f"Initialized {self.connector_name} connector")

    async def __aenter__(self):
        """Async context manager entry."""
        if self._owns_client and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
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

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for requests."""
        headers = {}

        if self.auth_type == AuthType.API_KEY and self.api_key:
            # Default API key header - subclasses can override
            headers["X-Api-Key"] = self.api_key
        elif self.auth_type == AuthType.BEARER and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    def get_source_info(self) -> SourceInfo:
        """Get metadata about this connector."""
        return SourceInfo(
            connector_id=self.connector_id,
            connector_name=self.connector_name,
            description=self.description,
            content_types=self.content_types.copy(),
            protocol=self.protocol,
            requires_auth=self.requires_auth,
            auth_type=self.auth_type if self.requires_auth else None,
            rate_limit=self.rate_limit,
            enabled=True,
            license=self.license,
            attribution=self.attribution,
        )

    # Whether this connector is available (set to False for stubs/archived services)
    available: bool = True
    unavailable_reason: str = None  # Reason why connector is unavailable

    async def ping(self) -> bool:
        """
        Quick connectivity check - just verify the API is reachable.

        This is a lightweight check using HTTP HEAD request, much faster
        than doing a full search query.

        Returns:
            True if the API endpoint is reachable, False otherwise.
        """
        try:
            response = await self.http_client.head(
                self.base_url,
                timeout=5.0,
                follow_redirects=True,
            )
            return response.status_code < 500
        except Exception:
            # Fall back to GET if HEAD not supported
            try:
                response = await self.http_client.get(
                    self.base_url,
                    timeout=5.0,
                    follow_redirects=True,
                )
                return response.status_code < 500
            except Exception:
                return False

    async def health_check(self) -> HealthCheckResult:
        """
        Test connectivity to the external API.

        Uses lightweight ping() instead of full search for faster checks.
        Returns status, response time, and any error message.
        Subclasses can override for custom health checks.
        """
        import time

        # Check if connector is marked as unavailable
        if not self.available:
            return HealthCheckResult(
                status="unavailable",
                response_time_ms=0,
                error_message=self.unavailable_reason or "Service unavailable",
            )

        start = time.time()
        try:
            reachable = await self.ping()
            elapsed = (time.time() - start) * 1000

            if reachable:
                return HealthCheckResult(
                    status="ok",
                    response_time_ms=elapsed,
                )
            else:
                return HealthCheckResult(
                    status="error",
                    response_time_ms=elapsed,
                    error_message="API not reachable",
                )
        except Exception as e:
            return HealthCheckResult(
                status="error",
                response_time_ms=(time.time() - start) * 1000,
                error_message=str(e),
            )

    # =========================================================================
    # Abstract methods that must be implemented
    # =========================================================================

    @abstractmethod
    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Search for content matching query.

        Args:
            query: Search query string
            content_type: Filter by content type (optional)
            limit: Maximum number of results
            offset: Offset for pagination
            **kwargs: Additional source-specific parameters

        Returns:
            List of ContentItem objects
        """
        pass

    @abstractmethod
    async def get_item(self, item_id: str) -> ContentItem | None:
        """
        Get a specific item by its ID.

        Args:
            item_id: The item's ID in this source

        Returns:
            ContentItem or None if not found
        """
        pass

    # =========================================================================
    # Optional methods with default implementations
    # =========================================================================

    async def get_by_location(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        limit: int = 20,
    ) -> list[ContentItem]:
        """
        Get content near a geographic location.

        Default implementation returns empty list - override for sources
        that support spatial queries.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius in kilometers
            content_type: Filter by content type
            limit: Maximum number of results

        Returns:
            List of ContentItem objects
        """
        return []

    async def get_by_period(
        self,
        period_start: int,
        period_end: int,
        culture: str | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Get content from a time period.

        Default implementation returns empty list - override for sources
        that support temporal queries.

        Args:
            period_start: Start year (negative for BCE)
            period_end: End year
            culture: Filter by culture/civilization
            limit: Maximum number of results

        Returns:
            List of ContentItem objects
        """
        return []

    async def get_by_empire(
        self,
        empire_name: str,
        period_name: str | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Get content related to an empire or civilization.

        Default implementation calls search() with empire name.

        Args:
            empire_name: Name of the empire (e.g., "Roman Empire")
            period_name: Specific period within empire (e.g., "Roman Principate")
            content_type: Filter by content type
            limit: Maximum number of results

        Returns:
            List of ContentItem objects
        """
        search_term = period_name or empire_name
        return await self.search(
            query=f"{search_term} ancient",
            content_type=content_type,
            limit=limit,
            **kwargs,
        )

    async def get_by_site(
        self,
        site_name: str,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Get content related to an archaeological site.

        Default implementation calls search() with site name.

        Args:
            site_name: Name of the site (e.g., "Pompeii")
            location: Location string for context
            lat: Latitude of site
            lon: Longitude of site
            content_type: Filter by content type
            limit: Maximum number of results

        Returns:
            List of ContentItem objects
        """
        return await self.search(
            query=site_name,
            content_type=content_type,
            limit=limit,
            **kwargs,
        )

    async def batch_fetch(
        self,
        limit: int | None = None,
        **kwargs,
    ) -> Iterator[ContentItem]:
        """
        Fetch all items for batch pre-computation.

        Default implementation raises NotImplementedError.
        Override for sources that support bulk export.

        Args:
            limit: Maximum items to fetch (None for all)
            **kwargs: Source-specific parameters

        Yields:
            ContentItem objects
        """
        raise NotImplementedError(
            f"{self.connector_name} does not support batch fetching"
        )

    # =========================================================================
    # Helper methods for subclasses
    # =========================================================================

    def normalize_for_search(self, text: str) -> str:
        """
        Normalize text for search comparison.

        Removes diacritics, lowercases, and trims whitespace.
        """
        import unicodedata

        # Normalize unicode and remove diacritics
        normalized = unicodedata.normalize("NFD", text)
        ascii_text = "".join(
            c for c in normalized if unicodedata.category(c) != "Mn"
        )

        # Lowercase and clean whitespace
        return " ".join(ascii_text.lower().split())

    def extract_primary_name(self, name: str) -> str:
        """
        Extract the primary searchable name from a site title.

        Examples:
        - "The Great Pyramid of Giza" -> "Great Pyramid Giza"
        - "Al-Rabadha" -> "Al-Rabadha" (preserves hyphenated names)
        """
        import re

        # Split on subtitle separators but preserve hyphenated words
        result = re.split(r"\s+-\s+|\s*[(,]\s*", name)[0].strip()

        # Remove leading articles
        result = re.sub(r"^(The|A|An)\s+", "", result, flags=re.IGNORECASE)

        # Remove filler words
        result = re.sub(r"\b(of|the|at|in|on)\b", " ", result, flags=re.IGNORECASE)

        # Clean up whitespace
        return " ".join(result.split()).strip() or name

    def extract_country(self, location: str) -> str:
        """Extract country from a location string (last part after comma)."""
        if not location:
            return ""
        parts = location.split(",")
        return parts[-1].strip()

    def score_relevance(
        self,
        item_title: str,
        search_query: str,
        primary_name: str,
        country: str = "",
        boost_keywords: list[str] = None,
    ) -> int:
        """
        Score how relevant an item is to a search query (0-100).

        Args:
            item_title: Title of the item being scored
            search_query: Original search query
            primary_name: Extracted primary name from query
            country: Country for geographic matching
            boost_keywords: Keywords that increase relevance

        Returns:
            Relevance score 0-100
        """
        normalized_item = self.normalize_for_search(item_title)
        normalized_query = self.normalize_for_search(search_query)
        normalized_primary = self.normalize_for_search(primary_name)
        normalized_country = self.normalize_for_search(country)

        score = 0

        # Exact match with full query
        if normalized_item == normalized_query:
            score += 100
        # Item starts with query
        elif normalized_item.startswith(normalized_query):
            score += 80
        # Item contains full query
        elif normalized_query in normalized_item:
            score += 70
        # Item contains primary name
        elif normalized_primary in normalized_item:
            score += 50
        # Check individual words (at least 4 chars)
        else:
            words = [w for w in normalized_primary.split() if len(w) >= 4]
            if words:
                matched = sum(1 for w in words if w in normalized_item)
                score += int((matched / len(words)) * 40)

        # Country bonus
        if normalized_country and normalized_country in normalized_item:
            score += 15

        # Keyword boost
        if boost_keywords:
            for kw in boost_keywords:
                if kw.lower() in normalized_item:
                    score += 10
                    break

        return min(score, 100)

    def create_content_item(
        self,
        item_id: str,
        title: str,
        url: str,
        content_type: ContentType,
        **kwargs,
    ) -> ContentItem:
        """
        Helper to create a ContentItem with source set automatically.

        Args:
            item_id: Unique ID for this item
            title: Item title
            url: URL to original
            content_type: Type of content
            **kwargs: Additional ContentItem fields

        Returns:
            ContentItem instance
        """
        return ContentItem(
            id=item_id,
            source=self.connector_id,
            content_type=content_type,
            title=title,
            url=url,
            fetched_at=datetime.utcnow(),
            **kwargs,
        )
