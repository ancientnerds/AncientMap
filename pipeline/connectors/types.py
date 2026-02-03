"""
Content types and data models for the Connectors Module.

Defines the universal ContentItem dataclass that all connectors produce,
plus enums for content types and authentication methods.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    """Types of content that connectors can provide."""

    # Visual content
    PHOTO = "photo"
    ARTWORK = "artwork"
    MAP = "map"

    # 3D content
    MODEL_3D = "model_3d"

    # Physical objects
    ARTIFACT = "artifact"
    COIN = "coin"

    # Textual content
    INSCRIPTION = "inscription"
    PRIMARY_TEXT = "primary_text"  # Ancient texts (Perseus, CDLI)
    MANUSCRIPT = "manuscript"
    BOOK = "book"
    PAPER = "paper"  # Academic papers
    DOCUMENT = "document"  # Historical documents

    # Multimedia
    VIDEO = "video"
    AUDIO = "audio"

    # Reference
    VOCABULARY_TERM = "vocabulary_term"
    PLACE = "place"
    PERIOD = "period"


class AuthType(str, Enum):
    """Authentication types for connectors."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BASIC = "basic"
    BEARER = "bearer"


class ProtocolType(str, Enum):
    """Protocol types for data retrieval."""

    REST = "rest"
    SPARQL = "sparql"
    ARCGIS = "arcgis"
    OAI_PMH = "oai_pmh"
    IIIF = "iiif"
    CTS = "cts"  # Canonical Text Services
    MEDIAWIKI = "mediawiki"
    BULK = "bulk"  # Bulk file download


@dataclass
class ContentItem:
    """
    Universal content item returned by all connectors.

    This is the standardized format that all connectors must produce,
    enabling unified handling across the application.
    """

    # Required fields
    id: str
    source: str  # Connector ID (e.g., "met_museum", "sketchfab")
    content_type: ContentType
    title: str
    url: str  # Link to original item

    # Optional description
    description: str | None = None

    # Media URLs
    thumbnail_url: str | None = None
    media_url: str | None = None  # Direct media (image, model, PDF)
    embed_url: str | None = None  # For embeddable content (Sketchfab)

    # Creator/author info
    creator: str | None = None
    creator_url: str | None = None

    # Date information
    date: str | None = None  # Display date string
    date_numeric: int | None = None  # Year for sorting (negative = BCE)

    # Cultural/historical context
    period: str | None = None
    period_start: int | None = None
    period_end: int | None = None
    culture: str | None = None

    # Geographic information
    lat: float | None = None
    lon: float | None = None
    place_name: str | None = None
    country: str | None = None

    # Rights and attribution
    license: str | None = None
    license_url: str | None = None
    attribution: str | None = None

    # Object metadata (for artifacts/museum items)
    object_type: str | None = None
    material: str | None = None
    dimensions: str | None = None
    museum: str | None = None

    # Engagement metrics (for platforms like Sketchfab)
    view_count: int | None = None
    like_count: int | None = None

    # Relevance scoring
    relevance_score: float = 0.0

    # Caching metadata
    fetched_at: datetime | None = None
    expires_at: datetime | None = None

    # Raw data for debugging/extension
    raw_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "source": self.source,
            "content_type": self.content_type.value,
            "title": self.title,
            "url": self.url,
        }

        # Add optional fields if present
        optional_fields = [
            "description", "thumbnail_url", "media_url", "embed_url",
            "creator", "creator_url", "date", "date_numeric",
            "period", "period_start", "period_end", "culture",
            "lat", "lon", "place_name", "country",
            "license", "license_url", "attribution",
            "object_type", "material", "dimensions", "museum",
            "view_count", "like_count", "relevance_score",
        ]

        for field_name in optional_fields:
            value = getattr(self, field_name, None)
            if value is not None:
                result[field_name] = value

        # Handle datetime fields
        if self.fetched_at:
            result["fetched_at"] = self.fetched_at.isoformat()
        if self.expires_at:
            result["expires_at"] = self.expires_at.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentItem":
        """Create ContentItem from dictionary."""
        # Convert content_type string to enum
        if isinstance(data.get("content_type"), str):
            data["content_type"] = ContentType(data["content_type"])

        # Convert datetime strings
        for dt_field in ["fetched_at", "expires_at"]:
            if isinstance(data.get(dt_field), str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)


@dataclass
class ContentSearchResult:
    """Result of a content search across connectors."""

    items: list[ContentItem] = field(default_factory=list)
    total_count: int = 0
    sources_searched: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    items_by_source: dict[str, int] = field(default_factory=dict)
    search_time_ms: float = 0.0
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "total_count": self.total_count,
            "sources_searched": self.sources_searched,
            "sources_failed": self.sources_failed,
            "items_by_source": self.items_by_source,
            "search_time_ms": self.search_time_ms,
            "cached": self.cached,
        }


@dataclass
class SourceInfo:
    """Information about a content source/connector."""

    connector_id: str
    connector_name: str
    description: str | None = None
    content_types: list[ContentType] = field(default_factory=list)
    protocol: ProtocolType | None = None
    requires_auth: bool = False
    auth_type: AuthType | None = None
    rate_limit: float = 1.0  # Requests per second
    enabled: bool = True
    last_sync: datetime | None = None
    item_count: int | None = None
    license: str | None = None
    attribution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "connector_id": self.connector_id,
            "connector_name": self.connector_name,
            "description": self.description,
            "content_types": [ct.value for ct in self.content_types],
            "protocol": self.protocol.value if self.protocol else None,
            "requires_auth": self.requires_auth,
            "auth_type": self.auth_type.value if self.auth_type else None,
            "rate_limit": self.rate_limit,
            "enabled": self.enabled,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "item_count": self.item_count,
            "license": self.license,
            "attribution": self.attribution,
        }


@dataclass
class HealthCheckResult:
    """Result of a health check on a connector."""

    status: str  # "ok", "warning", "error", "unavailable"
    response_time_ms: float
    error_message: str | None = None
    item_count: int | None = None


@dataclass
class SampleItem:
    """A sample item from test results."""

    id: str
    title: str
    url: str
    thumbnail_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
        }


@dataclass
class QueryTestResult:
    """Result of a single test query against a connector."""

    query_id: str
    query_name: str
    result_count: int
    sample_items: list[SampleItem] = field(default_factory=list)
    response_time_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query_id": self.query_id,
            "query_name": self.query_name,
            "result_count": self.result_count,
            "sample_items": [item.to_dict() for item in self.sample_items],
            "response_time_ms": self.response_time_ms,
            "error": self.error,
        }


@dataclass
class ConnectorStatus:
    """Status information for a connector."""

    connector_id: str
    connector_name: str
    category: str  # museums, sites, papers, etc.
    status: str  # "ok", "warning", "error", "unknown", "unavailable"
    available: bool = True  # False for archived/stub connectors
    base_url: str | None = None  # Website URL for the connector
    last_ping: datetime | None = None
    last_sync: datetime | None = None
    error_message: str | None = None
    item_count: int | None = None
    response_time_ms: float | None = None
    tabs: list[str] = field(default_factory=list)  # UI tabs this connector populates
    # Test results (optional, populated when tests are run)
    test_results: dict[str, QueryTestResult] | None = None
    api_docs_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "connector_id": self.connector_id,
            "connector_name": self.connector_name,
            "category": self.category,
            "status": self.status,
            "available": self.available,
            "base_url": self.base_url,
            "last_ping": self.last_ping.isoformat() if self.last_ping else None,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "error_message": self.error_message,
            "item_count": self.item_count,
            "response_time_ms": self.response_time_ms,
            "tabs": self.tabs,
        }
        if self.test_results is not None:
            result["test_results"] = {
                qid: tr.to_dict() for qid, tr in self.test_results.items()
            }
        if self.api_docs_url is not None:
            result["api_docs_url"] = self.api_docs_url
        return result
