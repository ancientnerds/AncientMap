"""
Content API Routes - Unified External Content Access.

Provides endpoints for fetching content from 50+ external sources
through the unified Connectors Module.

Endpoints:
- GET /api/content/search - Search across all connectors
- GET /api/content/by-location - Content near a location
- GET /api/content/by-site - Content for a site
- GET /api/content/by-empire/{empire_id} - Content for an empire
- GET /api/content/sources - List available content sources
- POST /api/content/connectors/verify-refresh - Verify before refresh
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from pipeline.connectors import ConnectorRegistry
from pipeline.connectors.types import ContentItem, ContentType

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# Refresh Protection Configuration
# ============================================================================

from api.services.admin_auth import (
    AdminPinRequest,
    AdminPinResponse,
    get_client_ip,
    verify_admin_pin,
)

# Rate limiting: track last refresh time per IP
_refresh_timestamps: dict[str, float] = {}
REFRESH_COOLDOWN_SECONDS = 300  # 5 minutes between refreshes per IP


# ============================================================================
# Response Models
# ============================================================================

class ContentItemResponse(BaseModel):
    """Single content item response."""

    id: str
    source: str
    content_type: str
    title: str
    url: str
    thumbnail_url: str | None = None
    media_url: str | None = None
    embed_url: str | None = None
    creator: str | None = None
    creator_url: str | None = None
    date: str | None = None
    period: str | None = None
    culture: str | None = None
    description: str | None = None
    license: str | None = None
    attribution: str | None = None
    museum: str | None = None
    relevance_score: float = 0.0

    @classmethod
    def from_content_item(cls, item: ContentItem) -> "ContentItemResponse":
        """Convert ContentItem to response model."""
        # Helper to convert lists to strings (some connectors return lists)
        def ensure_string(val) -> str | None:
            if val is None:
                return None
            if isinstance(val, list):
                return "; ".join(str(v) for v in val)
            return str(val)

        return cls(
            id=item.id,
            source=item.source,
            content_type=item.content_type.value,
            title=ensure_string(item.title) or "",
            url=item.url,
            thumbnail_url=item.thumbnail_url,
            media_url=item.media_url,
            embed_url=item.embed_url,
            creator=ensure_string(item.creator),
            creator_url=item.creator_url,
            date=ensure_string(item.date),
            period=ensure_string(item.period),
            culture=ensure_string(item.culture),
            description=ensure_string(item.description),
            license=ensure_string(item.license),
            attribution=ensure_string(item.attribution),
            museum=ensure_string(item.museum),
            relevance_score=item.relevance_score,
        )


class ContentSearchResponse(BaseModel):
    """Response for content search endpoints."""

    items: list[ContentItemResponse]
    total_count: int
    sources_searched: list[str]
    sources_failed: list[str] = []
    items_by_source: dict[str, int] = {}
    search_time_ms: float
    cached: bool = False


class SourceInfoResponse(BaseModel):
    """Response for source info."""

    connector_id: str
    connector_name: str
    description: str | None = None
    content_types: list[str]
    protocol: str | None = None
    requires_auth: bool = False
    rate_limit: float = 1.0
    enabled: bool = True
    license: str | None = None
    attribution: str | None = None


class SampleItemResponse(BaseModel):
    """A sample item from test results."""

    id: str
    title: str
    url: str
    thumbnail_url: str | None = None


class QueryTestResultResponse(BaseModel):
    """Result of a single test query against a connector."""

    query_id: str
    query_name: str
    result_count: int
    sample_items: list[SampleItemResponse] = []
    response_time_ms: float = 0.0
    error: str | None = None


class ConnectorStatusResponse(BaseModel):
    """Status of a single connector."""

    connector_id: str
    connector_name: str
    category: str  # museums, sites, papers, etc.
    status: str  # ok, warning, error, unknown, unavailable
    available: bool = True  # False for archived/stub connectors
    base_url: str | None = None  # Website URL for the connector
    last_ping: str | None = None
    last_sync: str | None = None
    error_message: str | None = None
    item_count: int | None = None
    response_time_ms: float | None = None
    tabs: list[str] = []  # UI tabs this connector populates (Photos, Artworks, Maps, 3D, Artifacts, Books)
    # Test results (optional, populated when tests are run)
    test_results: dict[str, QueryTestResultResponse] | None = None
    api_docs_url: str | None = None


class StatusSummary(BaseModel):
    """Summary of connector statuses."""

    total: int
    ok: int
    warning: int
    error: int
    unknown: int
    unavailable: int = 0


class ConnectorsStatusResponse(BaseModel):
    """Response for connector status endpoint."""

    connectors: list[ConnectorStatusResponse]
    summary: StatusSummary
    checked_at: str


# ============================================================================
# Startup: Initialize Connectors
# ============================================================================

def _init_connectors():
    """Initialize connectors with API keys from environment."""
    api_keys = {
        # Add API keys as needed for connectors that require authentication
        # Example: "europeana": os.environ.get("EUROPEANA_API_KEY"),
    }

    ConnectorRegistry.set_api_keys({k: v for k, v in api_keys.items() if v})


# Initialize on module load
_init_connectors()


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/search", response_model=ContentSearchResponse)
async def search_content(
    query: str = Query(..., min_length=1, description="Search query"),
    content_types: list[str] | None = Query(
        default=None,
        description="Filter by content types (photo, artifact, map, model_3d, etc.)"
    ),
    sources: list[str] | None = Query(
        default=None,
        description="Filter to specific sources (met_museum, sketchfab, etc.)"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    timeout: float = Query(default=30.0, ge=1.0, le=60.0, description="Timeout in seconds"),
):
    """
    Search for content across all (or specified) connectors.

    Returns aggregated results from museums, 3D model sources,
    map collections, and other content providers.
    """
    # Parse content types
    parsed_types = None
    if content_types:
        try:
            parsed_types = [ContentType(ct) for ct in content_types]
        except ValueError as e:
            raise HTTPException(400, f"Invalid content type: {e}") from e

    # Perform search
    result = await ConnectorRegistry.search_all(
        query=query,
        content_type=parsed_types[0] if parsed_types and len(parsed_types) == 1 else None,
        sources=sources,
        limit_per_source=limit // max(1, len(sources or []) or 5),
        timeout=timeout,
    )

    return ContentSearchResponse(
        items=[ContentItemResponse.from_content_item(item) for item in result.items[:limit]],
        total_count=len(result.items),
        sources_searched=result.sources_searched,
        sources_failed=result.sources_failed,
        items_by_source=result.items_by_source,
        search_time_ms=result.search_time_ms,
        cached=result.cached,
    )


@router.get("/by-location", response_model=ContentSearchResponse)
async def content_by_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_km: float = Query(default=50, ge=1, le=500, description="Search radius in km"),
    content_types: list[str] | None = Query(default=None),
    sources: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    timeout: float = Query(default=30.0, ge=1.0, le=60.0),
):
    """
    Get content near a geographic location.

    Useful for site popups - finds nearby artifacts, photos, maps, etc.
    """
    parsed_types = None
    if content_types:
        try:
            parsed_types = [ContentType(ct) for ct in content_types]
        except ValueError as e:
            raise HTTPException(400, f"Invalid content type: {e}") from e

    result = await ConnectorRegistry.get_by_location_all(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        content_type=parsed_types[0] if parsed_types and len(parsed_types) == 1 else None,
        sources=sources,
        limit_per_source=limit // max(1, len(sources or []) or 5),
        timeout=timeout,
    )

    return ContentSearchResponse(
        items=[ContentItemResponse.from_content_item(item) for item in result.items[:limit]],
        total_count=len(result.items),
        sources_searched=result.sources_searched,
        sources_failed=result.sources_failed,
        items_by_source=result.items_by_source,
        search_time_ms=result.search_time_ms,
        cached=result.cached,
    )


@router.get("/by-site", response_model=ContentSearchResponse)
async def content_by_site(
    name: str = Query(..., min_length=1, description="Site name"),
    location: str | None = Query(default=None, description="Location string"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    culture: str | None = Query(default=None, description="Culture/civilization"),
    content_types: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    timeout: float = Query(default=45.0, ge=1.0, le=120.0),
):
    """
    Get all content related to an archaeological site.

    Fetches 3D models, maps, artifacts, photos from all relevant sources.
    """
    parsed_types = None
    if content_types:
        try:
            parsed_types = [ContentType(ct) for ct in content_types]
        except ValueError as e:
            raise HTTPException(400, f"Invalid content type: {e}") from e

    result = await ConnectorRegistry.get_for_site(
        site_name=name,
        location=location,
        lat=lat,
        lon=lon,
        content_types=parsed_types,
        limit_per_source=limit // 5,
        timeout=timeout,
    )

    return ContentSearchResponse(
        items=[ContentItemResponse.from_content_item(item) for item in result.items[:limit]],
        total_count=len(result.items),
        sources_searched=result.sources_searched,
        sources_failed=result.sources_failed,
        items_by_source=result.items_by_source,
        search_time_ms=result.search_time_ms,
        cached=result.cached,
    )


@router.get("/by-empire/{empire_id}", response_model=ContentSearchResponse)
async def content_by_empire(
    empire_id: str,
    empire_name: str | None = Query(default=None, description="Empire display name"),
    period_name: str | None = Query(default=None, description="Specific period name"),
    content_types: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    timeout: float = Query(default=45.0, ge=1.0, le=120.0),
):
    """
    Get content related to an empire or civilization.

    Fetches artifacts, maps, photos for empire popups.
    """
    # Use empire_name if provided, otherwise use empire_id
    name = empire_name or empire_id.replace("_", " ").title()

    parsed_types = None
    if content_types:
        try:
            parsed_types = [ContentType(ct) for ct in content_types]
        except ValueError as e:
            raise HTTPException(400, f"Invalid content type: {e}") from e

    result = await ConnectorRegistry.get_for_empire(
        empire_name=name,
        period_name=period_name,
        content_types=parsed_types,
        limit_per_source=limit // 5,
        timeout=timeout,
    )

    return ContentSearchResponse(
        items=[ContentItemResponse.from_content_item(item) for item in result.items[:limit]],
        total_count=len(result.items),
        sources_searched=result.sources_searched,
        sources_failed=result.sources_failed,
        items_by_source=result.items_by_source,
        search_time_ms=result.search_time_ms,
        cached=result.cached,
    )


@router.get("/sources", response_model=list[SourceInfoResponse])
async def list_sources():
    """
    List all available content sources with their status.

    Returns info about each connector including content types,
    rate limits, and authentication requirements.
    """
    sources = ConnectorRegistry.list_sources()

    return [
        SourceInfoResponse(
            connector_id=s.connector_id,
            connector_name=s.connector_name,
            description=s.description,
            content_types=[ct.value for ct in s.content_types],
            protocol=s.protocol.value if s.protocol else None,
            requires_auth=s.requires_auth,
            rate_limit=s.rate_limit,
            enabled=s.enabled,
            license=s.license,
            attribution=s.attribution,
        )
        for s in sources
    ]


@router.get("/types")
async def list_content_types():
    """List all available content types."""
    return {
        "content_types": [
            {"id": ct.value, "name": ct.name.replace("_", " ").title()}
            for ct in ContentType
        ]
    }


class SingleConnectorTestResponse(BaseModel):
    """Response for single connector test."""

    connector_id: str
    test_results: dict[str, QueryTestResultResponse]


@router.get("/connectors/status")
async def get_connectors_status(
    check_live: bool = Query(
        default=False,
        description="If true, actively ping all connectors (slower but accurate). Otherwise returns cached status."
    ),
    timeout: float = Query(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Timeout in seconds for each health check"
    ),
    include_tests: bool = Query(
        default=False,
        description="If true, run test queries against all connectors (expensive operation)."
    ),
    run_tests_for: str | None = Query(
        default=None,
        description="Run tests for a single connector only (returns minimal response)."
    ),
):
    """
    Get status of all content connectors, optionally with test results.

    - check_live=True: actively pings each connector (slower but accurate)
    - include_tests=True: run test queries against all connectors (expensive)
    - run_tests_for=<connector_id>: run tests for a single connector only
    """
    from datetime import datetime

    # Single connector test mode
    if run_tests_for:
        test_results = await ConnectorRegistry.run_connector_tests(
            run_tests_for, timeout=timeout
        )
        # Convert to response format
        test_results_response = {
            qid: QueryTestResultResponse(
                query_id=tr.query_id,
                query_name=tr.query_name,
                result_count=tr.result_count,
                sample_items=[
                    SampleItemResponse(
                        id=item.id,
                        title=item.title,
                        url=item.url,
                        thumbnail_url=item.thumbnail_url,
                    )
                    for item in tr.sample_items
                ],
                response_time_ms=tr.response_time_ms,
                error=tr.error,
            )
            for qid, tr in test_results.items()
        }
        # Return minimal response for single connector test
        return SingleConnectorTestResponse(
            connector_id=run_tests_for,
            test_results=test_results_response,
        )

    # Full status check
    if check_live or include_tests:
        statuses = await ConnectorRegistry.check_all_status(
            timeout=timeout,
            include_tests=include_tests,
        )
    else:
        statuses = ConnectorRegistry.get_cached_status()

    # Calculate summary
    summary = StatusSummary(
        total=len(statuses),
        ok=sum(1 for s in statuses if s.status == "ok"),
        warning=sum(1 for s in statuses if s.status == "warning"),
        error=sum(1 for s in statuses if s.status == "error"),
        unknown=sum(1 for s in statuses if s.status == "unknown"),
        unavailable=sum(1 for s in statuses if s.status == "unavailable"),
    )

    def convert_test_results(test_results):
        """Convert test results to response format."""
        if not test_results:
            return None
        return {
            qid: QueryTestResultResponse(
                query_id=tr.query_id,
                query_name=tr.query_name,
                result_count=tr.result_count,
                sample_items=[
                    SampleItemResponse(
                        id=item.id,
                        title=item.title,
                        url=item.url,
                        thumbnail_url=item.thumbnail_url,
                    )
                    for item in tr.sample_items
                ],
                response_time_ms=tr.response_time_ms,
                error=tr.error,
            )
            for qid, tr in test_results.items()
        }

    return ConnectorsStatusResponse(
        connectors=[
            ConnectorStatusResponse(
                connector_id=s.connector_id,
                connector_name=s.connector_name,
                category=s.category,
                status=s.status,
                available=getattr(s, 'available', True),
                base_url=getattr(s, 'base_url', None),
                last_ping=s.last_ping.isoformat() if s.last_ping else None,
                last_sync=s.last_sync.isoformat() if s.last_sync else None,
                error_message=s.error_message,
                item_count=s.item_count,
                response_time_ms=s.response_time_ms,
                tabs=getattr(s, 'tabs', []),
                test_results=convert_test_results(getattr(s, 'test_results', None)),
                api_docs_url=getattr(s, 'api_docs_url', None),
            )
            for s in statuses
        ],
        summary=summary,
        checked_at=datetime.utcnow().isoformat(),
    )


# ============================================================================
# Admin PIN Verification Endpoints
# ============================================================================

@router.post("/admin/verify-pin", response_model=AdminPinResponse)
async def verify_pin(request: AdminPinRequest, req: Request):
    """
    Verify Turnstile + admin PIN.

    Used by: site editing, connector tests, any admin action without rate limiting.
    """
    ip = get_client_ip(req)
    return await verify_admin_pin(request.pin, request.turnstile_token, ip)


@router.post("/connectors/verify-refresh", response_model=AdminPinResponse)
async def verify_refresh(request: AdminPinRequest, req: Request):
    """
    Verify Turnstile + admin PIN with rate limiting.

    Used by: connector refresh (pings external APIs, so rate limited to 1 per 5 min).
    """
    ip = get_client_ip(req)

    # Extra rate limit for refresh (hits external APIs)
    now = time.time()
    last_refresh = _refresh_timestamps.get(ip, 0)
    cooldown_remaining = int(REFRESH_COOLDOWN_SECONDS - (now - last_refresh))

    if cooldown_remaining > 0:
        return AdminPinResponse(
            verified=False,
            error="rate_limited",
            message=f"Please wait {cooldown_remaining} seconds before refreshing again.",
            cooldown_remaining=cooldown_remaining,
        )

    result = await verify_admin_pin(request.pin, request.turnstile_token, ip)

    if result.verified:
        _refresh_timestamps[ip] = now
        logger.info(f"Connector refresh authorized for {ip}")

    return result
