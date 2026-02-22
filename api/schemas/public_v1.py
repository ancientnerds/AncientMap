"""
Pydantic response models for the Public API v1.

These models use developer-friendly field names (not compact internal names)
and include OpenAPI examples for auto-generated documentation.
"""

from pydantic import BaseModel, Field

# =============================================================================
# Sites
# =============================================================================


class SiteResult(BaseModel):
    """A single archaeological site in search results."""

    id: str = Field(description="Unique site identifier (UUID)", json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"})
    name: str = Field(description="Site name", json_schema_extra={"example": "Stonehenge"})
    latitude: float = Field(description="Latitude in decimal degrees", json_schema_extra={"example": 51.1789})
    longitude: float = Field(description="Longitude in decimal degrees", json_schema_extra={"example": -1.8262})
    source_id: str = Field(description="Data source identifier", json_schema_extra={"example": "ancient_nerds"})
    site_type: str | None = Field(None, description="Type of archaeological site", json_schema_extra={"example": "stone circle"})
    period_start: int | None = Field(None, description="Estimated start date (negative = BC)", json_schema_extra={"example": -3000})
    period_name: str | None = Field(None, description="Named period", json_schema_extra={"example": "Neolithic"})
    country: str | None = Field(None, description="Country name", json_schema_extra={"example": "United Kingdom"})


class SiteSearchResponse(BaseModel):
    """Response for site search queries."""

    count: int = Field(description="Number of results returned", json_schema_extra={"example": 3})
    results: list[SiteResult] = Field(description="Matching sites")


class SiteDetailResponse(SiteResult):
    """Full detail for a single archaeological site."""

    description: str | None = Field(None, description="Site description")
    source_url: str | None = Field(None, description="Link to original source")
    thumbnail_url: str | None = Field(None, description="Thumbnail image URL")
    period_end: int | None = Field(None, description="Estimated end date (negative = BC)")


# =============================================================================
# Sources
# =============================================================================


class SourcePublic(BaseModel):
    """A data source contributing sites to the database."""

    id: str = Field(description="Source identifier", json_schema_extra={"example": "pleiades"})
    name: str = Field(description="Human-readable source name", json_schema_extra={"example": "Pleiades"})
    site_count: int = Field(description="Number of sites from this source", json_schema_extra={"example": 38000})
    color: str = Field(description="Hex color for map display", json_schema_extra={"example": "#e74c3c"})
    category: str | None = Field(None, description="Source category", json_schema_extra={"example": "ancient_world"})
    description: str | None = Field(None, description="Brief description of the source")


class SourcesResponse(BaseModel):
    """Response listing all data sources."""

    count: int = Field(description="Number of sources", json_schema_extra={"example": 18})
    sources: list[SourcePublic] = Field(description="Available data sources")


# =============================================================================
# News
# =============================================================================


class NewsVideoPublic(BaseModel):
    """Video information for a news item."""

    id: str = Field(description="YouTube video ID", json_schema_extra={"example": "dQw4w9WgXcQ"})
    title: str = Field(description="Video title")
    channel_name: str = Field(description="YouTube channel name")
    published_at: str = Field(description="ISO 8601 publication date")
    thumbnail_url: str | None = Field(None, description="Video thumbnail URL")


class NewsSiteRef(BaseModel):
    """Reference to an archaeological site linked from a news item."""

    id: str = Field(description="Site UUID")
    name: str = Field(description="Site name")
    latitude: float = Field(description="Site latitude")
    longitude: float = Field(description="Site longitude")


class NewsItemPublic(BaseModel):
    """A news item from the Lyra archaeological news pipeline."""

    id: int = Field(description="News item ID")
    headline: str = Field(description="Item headline")
    summary: str = Field(description="Brief summary")
    youtube_url: str | None = Field(None, description="Link to YouTube video")
    youtube_deep_url: str | None = Field(None, description="Deep link to timestamp in video")
    video: NewsVideoPublic = Field(description="Source video information")
    site: NewsSiteRef | None = Field(None, description="Linked archaeological site, if any")
    created_at: str = Field(description="ISO 8601 creation timestamp")


class NewsFeedPublicResponse(BaseModel):
    """Paginated news feed response."""

    items: list[NewsItemPublic] = Field(description="News items")
    total_count: int = Field(description="Total items matching filters", json_schema_extra={"example": 150})
    page: int = Field(description="Current page number", json_schema_extra={"example": 1})
    has_more: bool = Field(description="Whether more pages are available")


# =============================================================================
# Channels
# =============================================================================


class ChannelPublic(BaseModel):
    """A YouTube channel tracked by the news pipeline."""

    id: str = Field(description="YouTube channel ID")
    name: str = Field(description="Channel name")


# =============================================================================
# Stats
# =============================================================================


class StatsResponse(BaseModel):
    """Database statistics."""

    total_sites: int = Field(description="Total archaeological sites in database", json_schema_extra={"example": 750000})
    by_source: dict[str, int] = Field(description="Site count per data source", json_schema_extra={"example": {"pleiades": 38000, "dare": 22000}})
