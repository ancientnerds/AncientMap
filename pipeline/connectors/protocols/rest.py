"""
REST/JSON Protocol Handler.

Provides a base class for REST API communication with:
- Async HTTP requests via httpx
- Automatic retries with exponential backoff
- Rate limiting
- Error handling and response parsing
"""

import asyncio
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class RestProtocol:
    """
    REST API protocol handler.

    Provides consistent HTTP communication with:
    - GET/POST requests
    - JSON parsing
    - Rate limiting
    - Retry logic
    """

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        rate_limit: float = 1.0,  # Requests per second
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize REST protocol handler.

        Args:
            base_url: Base URL for all requests
            headers: Default headers to include
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second
            http_client: Optional shared HTTP client
        """
        self.base_url = base_url.rstrip("/")
        self.default_headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com)",
            **(headers or {}),
        }
        self.timeout = timeout
        self.rate_limit = rate_limit

        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

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
    def client(self) -> httpx.AsyncClient:
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

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        """
        Build full URL from path and query parameters.

        Args:
            path: URL path (relative to base_url)
            params: Query parameters

        Returns:
            Full URL string
        """
        if path.startswith(("http://", "https://")):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"

        if params:
            # Filter out None values
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                query = urlencode(filtered, doseq=True)
                url = f"{url}?{query}"

        return url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make GET request and return JSON response.

        Args:
            path: URL path
            params: Query parameters
            headers: Additional headers

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: For 4xx/5xx responses
            httpx.TimeoutException: For timeouts
        """
        await self._rate_limit()

        url = self.build_url(path, params)
        request_headers = {**self.default_headers, **(headers or {})}

        logger.debug(f"GET {url}")

        response = await self.client.get(url, headers=request_headers)
        response.raise_for_status()

        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def post(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make POST request and return JSON response.

        Args:
            path: URL path
            data: Form data
            json_data: JSON body
            headers: Additional headers

        Returns:
            Parsed JSON response
        """
        await self._rate_limit()

        url = self.build_url(path)
        request_headers = {**self.default_headers, **(headers or {})}

        logger.debug(f"POST {url}")

        response = await self.client.post(
            url,
            data=data,
            json=json_data,
            headers=request_headers,
        )
        response.raise_for_status()

        return response.json()

    async def get_raw(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """
        Make GET request and return raw response.

        Useful for non-JSON responses or when you need headers.
        """
        await self._rate_limit()

        url = self.build_url(path, params)
        request_headers = {**self.default_headers, **(headers or {})}

        logger.debug(f"GET (raw) {url}")

        response = await self.client.get(url, headers=request_headers)
        response.raise_for_status()

        return response

    async def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page_param: str = "page",
        limit_param: str = "limit",
        limit: int = 100,
        max_pages: int = 10,
        results_key: str = "results",
    ) -> list[dict[str, Any]]:
        """
        Paginate through API results.

        Args:
            path: URL path
            params: Base query parameters
            page_param: Name of page parameter
            limit_param: Name of limit parameter
            limit: Items per page
            max_pages: Maximum pages to fetch
            results_key: Key in response containing results

        Returns:
            List of all results
        """
        all_results = []
        params = params or {}

        for page in range(1, max_pages + 1):
            page_params = {
                **params,
                page_param: page,
                limit_param: limit,
            }

            try:
                response = await self.get(path, page_params)

                # Extract results
                if results_key in response:
                    results = response[results_key]
                elif isinstance(response, list):
                    results = response
                else:
                    results = []

                if not results:
                    break

                all_results.extend(results)

                # Check if we've got all results
                if len(results) < limit:
                    break

            except Exception as e:
                logger.warning(f"Pagination error on page {page}: {e}")
                break

        return all_results

    async def paginate_offset(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        offset_param: str = "offset",
        limit_param: str = "limit",
        limit: int = 100,
        max_items: int = 1000,
        results_key: str = "results",
        total_key: str | None = "total",
    ) -> list[dict[str, Any]]:
        """
        Paginate using offset-based pagination.

        Args:
            path: URL path
            params: Base query parameters
            offset_param: Name of offset parameter
            limit_param: Name of limit parameter
            limit: Items per request
            max_items: Maximum total items to fetch
            results_key: Key in response containing results
            total_key: Key in response containing total count

        Returns:
            List of all results
        """
        all_results = []
        params = params or {}
        offset = 0

        while offset < max_items:
            page_params = {
                **params,
                offset_param: offset,
                limit_param: limit,
            }

            try:
                response = await self.get(path, page_params)

                # Extract results
                if results_key in response:
                    results = response[results_key]
                elif isinstance(response, list):
                    results = response
                else:
                    results = []

                if not results:
                    break

                all_results.extend(results)
                offset += len(results)

                # Check if we've got all results
                if total_key and total_key in response:
                    total = response[total_key]
                    if offset >= total:
                        break

                if len(results) < limit:
                    break

            except Exception as e:
                logger.warning(f"Pagination error at offset {offset}: {e}")
                break

        return all_results
