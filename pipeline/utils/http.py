"""
HTTP utilities for the data pipeline.

Provides robust HTTP fetching with retry logic, rate limiting awareness,
and proper error handling.
"""

import gzip
import hashlib
from pathlib import Path
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from loguru import logger

from pipeline.config import settings


# Default headers for requests
DEFAULT_HEADERS = {
    "User-Agent": "AncientNerds/1.0 (Research Platform; contact@ancientnerds.com)",
    "Accept": "application/json, text/csv, application/xml, */*",
}


class HTTPError(Exception):
    """Custom HTTP error with status code."""

    def __init__(self, message: str, status_code: int = None, response: httpx.Response = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RateLimitError(HTTPError):
    """Raised when rate limited by a data source."""
    pass


@retry(
    stop=stop_after_attempt(settings.pipeline.http_max_retries),
    wait=wait_exponential(multiplier=settings.pipeline.http_retry_delay, min=1, max=60),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
def fetch_with_retry(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    json_data: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: Optional[int] = None,
) -> httpx.Response:
    """
    Fetch URL with automatic retry on transient failures.

    Args:
        url: URL to fetch
        method: HTTP method (GET, POST, etc.)
        headers: Additional headers to include
        params: Query parameters
        json_data: JSON body for POST requests
        data: Form data for POST requests (application/x-www-form-urlencoded)
        timeout: Request timeout in seconds

    Returns:
        httpx.Response object

    Raises:
        HTTPError: For HTTP errors (4xx, 5xx)
        RateLimitError: When rate limited (429)
        httpx.TimeoutException: On timeout after retries
    """
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}
    timeout = timeout or settings.pipeline.http_timeout

    logger.debug(f"Fetching {method} {url}")

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.request(
            method=method,
            url=url,
            headers=request_headers,
            params=params,
            json=json_data,
            data=data,
        )

    # Handle rate limiting
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "60")
        raise RateLimitError(
            f"Rate limited by {url}. Retry after {retry_after}s",
            status_code=429,
            response=response,
        )

    # Handle other HTTP errors
    if response.status_code >= 400:
        raise HTTPError(
            f"HTTP {response.status_code} for {url}: {response.text[:200]}",
            status_code=response.status_code,
            response=response,
        )

    logger.debug(f"Fetched {url} ({response.status_code}, {len(response.content)} bytes)")
    return response


def download_file(
    url: str,
    dest_path: Path,
    force: bool = False,
    decompress_gzip: bool = True,
) -> Path:
    """
    Download a file to disk with caching support.

    Args:
        url: URL to download
        dest_path: Destination path (directory or file)
        force: Force re-download even if file exists
        decompress_gzip: Automatically decompress .gz files

    Returns:
        Path to downloaded file
    """
    # Ensure dest_path is a Path
    dest_path = Path(dest_path)

    # If dest_path is a directory, derive filename from URL
    if dest_path.is_dir():
        filename = url.split("/")[-1].split("?")[0]
        dest_path = dest_path / filename

    # Check if file exists and skip if not forcing
    if dest_path.exists() and not force:
        logger.info(f"File already exists: {dest_path}")
        return dest_path

    # Ensure parent directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading {url} to {dest_path}")

    response = fetch_with_retry(url)

    # Write content to file
    content = response.content

    # Decompress gzip if needed
    if decompress_gzip and (url.endswith(".gz") or url.endswith(".gzip")):
        logger.info("Decompressing gzip content...")
        content = gzip.decompress(content)
        # Remove .gz extension from filename
        if dest_path.suffix == ".gz":
            dest_path = dest_path.with_suffix("")

    dest_path.write_bytes(content)

    # Calculate hash for verification
    file_hash = hashlib.md5(content).hexdigest()
    logger.info(f"Downloaded {len(content):,} bytes (MD5: {file_hash})")

    return dest_path


