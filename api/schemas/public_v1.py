"""
Pydantic response models for the Public API v1.

These models use developer-friendly field names (not compact internal names)
and include OpenAPI examples for auto-generated documentation.
"""

from pydantic import BaseModel, Field

# =============================================================================
# Status
# =============================================================================


class StatusResponse(BaseModel):
    """API health and version information."""

    status: str = Field(description="Service status", json_schema_extra={"example": "ok"})
    version: str = Field(description="API version", json_schema_extra={"example": "1.0.0"})
    commit: str = Field(
        description="Git commit hash of the running build", json_schema_extra={"example": "8c8b02f"}
    )
    total_sites: int = Field(
        description="Total archaeological sites in database (>0 = healthy)",
        json_schema_extra={"example": 750000},
    )
    source_count: int = Field(
        description="Number of active data sources", json_schema_extra={"example": 18}
    )


# =============================================================================
# Sites
# =============================================================================


class SiteResult(BaseModel):
    """A single archaeological site in search results."""

    id: str = Field(
        description="Unique site identifier (UUID)",
        json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    )
    name: str = Field(description="Site name", json_schema_extra={"example": "Stonehenge"})
    latitude: float = Field(
        description="Latitude in decimal degrees", json_schema_extra={"example": 51.1789}
    )
    longitude: float = Field(
        description="Longitude in decimal degrees", json_schema_extra={"example": -1.8262}
    )
    source_id: str = Field(
        description="Data source identifier", json_schema_extra={"example": "ancient_nerds"}
    )
    site_type: str | None = Field(
        None,
        description="Type of archaeological site",
        json_schema_extra={"example": "stone circle"},
    )
    period_start: int | None = Field(
        None,
        description="Estimated start date (negative = BC)",
        json_schema_extra={"example": -3000},
    )
    period_name: str | None = Field(
        None, description="Named period", json_schema_extra={"example": "Neolithic"}
    )
    country: str | None = Field(
        None, description="Country name", json_schema_extra={"example": "United Kingdom"}
    )
    source_url: str | None = Field(None, description="Link to original source record")


class SiteSearchResponse(BaseModel):
    """Response for site search queries."""

    count: int = Field(description="Number of results returned", json_schema_extra={"example": 3})
    results: list[SiteResult] = Field(description="Matching sites")


class SiteDetailResponse(SiteResult):
    """Full detail for a single archaeological site."""

    description: str | None = Field(None, description="Site description")
    thumbnail_url: str | None = Field(None, description="Thumbnail image URL")
    period_end: int | None = Field(None, description="Estimated end date (negative = BC)")


# =============================================================================
# Sources
# =============================================================================


class SourcePublic(BaseModel):
    """A data source contributing sites to the database."""

    id: str = Field(description="Source identifier", json_schema_extra={"example": "pleiades"})
    name: str = Field(
        description="Human-readable source name", json_schema_extra={"example": "Pleiades"}
    )
    site_count: int = Field(
        description="Number of sites from this source", json_schema_extra={"example": 38000}
    )
    color: str = Field(
        description="Hex color for map display", json_schema_extra={"example": "#e74c3c"}
    )
    category: str | None = Field(
        None, description="Source category", json_schema_extra={"example": "ancient_world"}
    )
    description: str | None = Field(None, description="Brief description of the source")
    license: str | None = Field(None, description="Data license (e.g. CC-BY-SA-4.0)")
    url: str | None = Field(None, description="Source website URL")


class SourceDetailResponse(BaseModel):
    """Detailed breakdown for a single data source."""

    id: str = Field(description="Source identifier", json_schema_extra={"example": "pleiades"})
    name: str = Field(
        description="Human-readable source name", json_schema_extra={"example": "Pleiades"}
    )
    site_count: int = Field(
        description="Number of sites from this source", json_schema_extra={"example": 38000}
    )
    color: str = Field(
        description="Hex color for map display", json_schema_extra={"example": "#e74c3c"}
    )
    category: str | None = Field(None, description="Source category")
    description: str | None = Field(None, description="Brief description of the source")
    license: str | None = Field(None, description="Data license")
    url: str | None = Field(None, description="Source website URL")
    types: dict[str, int] = Field(
        description="Top site types with counts",
        json_schema_extra={"example": {"settlement": 12000, "temple": 3500}},
    )
    periods: dict[str, int] = Field(
        description="Period distribution with counts",
        json_schema_extra={"example": {"500 BC - 1 AD": 15000, "1 - 500 AD": 8000}},
    )


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
    total_count: int = Field(
        description="Total items matching filters", json_schema_extra={"example": 150}
    )
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

    total_sites: int = Field(
        description="Total archaeological sites in database", json_schema_extra={"example": 750000}
    )
    by_source: dict[str, int] = Field(
        description="Site count per data source",
        json_schema_extra={"example": {"pleiades": 38000, "dare": 22000}},
    )
    last_updated: str | None = Field(
        None, description="ISO 8601 timestamp of most recently updated site"
    )


# =============================================================================
# Facets
# =============================================================================


class FacetSource(BaseModel):
    """Source info for faceted search."""

    id: str = Field(description="Source identifier")
    name: str = Field(description="Human-readable source name")
    color: str = Field(description="Hex color for display")
    count: int = Field(description="Number of sites from this source")
    description: str | None = Field(None, description="Brief description of the source")
    category: str | None = Field(None, description="Source category")


class FacetsResponse(BaseModel):
    """Distinct filter facets for populating dropdowns without loading all sites."""

    categories: list[str] = Field(description="Distinct site types")
    countries: list[str] = Field(description="Distinct country names")
    sources: list[FacetSource] = Field(description="Available data sources with counts")


# =============================================================================
# Cards
# =============================================================================


class CardPublic(BaseModel):
    """A card description for an archaeological site."""

    site_id: str = Field(
        description="Unique site identifier (UUID)",
        json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    )
    name: str = Field(description="Site name", json_schema_extra={"example": "Parthenon"})
    card_description: str = Field(
        description="Short card description (~200 chars)",
        json_schema_extra={
            "example": "Iconic temple atop the Athenian Acropolis, built in 447 BC as a monument to Athena."
        },
    )
    country: str | None = Field(
        None, description="Country name", json_schema_extra={"example": "Greece"}
    )
    site_type: str | None = Field(
        None, description="Type of archaeological site", json_schema_extra={"example": "temple"}
    )
    period_name: str | None = Field(
        None, description="Named historical period", json_schema_extra={"example": "Classical"}
    )
    category_group: str | None = Field(
        None,
        description="Category group (e.g. Settlements, Religious)",
        json_schema_extra={"example": "Religious"},
    )
    rarity_tier: int = Field(
        description="Rarity tier (1=Common, 2=Uncommon, 3=Rare, 4=Epic, 5=Legendary)",
        json_schema_extra={"example": 5},
    )
    rarity_name: str = Field(
        description="Rarity tier name", json_schema_extra={"example": "Legendary"}
    )
    total_power: int = Field(description="Total power score", json_schema_extra={"example": 92})
    antiquity: int = Field(description="Antiquity stat", json_schema_extra={"example": 18})
    fortification: int = Field(description="Fortification stat", json_schema_extra={"example": 15})
    cultural_influence: int = Field(
        description="Cultural influence stat", json_schema_extra={"example": 20}
    )
    mystery: int = Field(description="Mystery stat", json_schema_extra={"example": 19})
    legacy: int = Field(description="Legacy stat", json_schema_extra={"example": 20})


class CardsResponse(BaseModel):
    """Paginated card descriptions response."""

    count: int = Field(description="Number of results returned", json_schema_extra={"example": 50})
    total: int = Field(description="Total matching cards", json_schema_extra={"example": 1200})
    cards: list[CardPublic] = Field(description="Card descriptions")


# =============================================================================
# Empires (Seshat polities)
# =============================================================================


class EmpireOut(BaseModel):
    """A historical polity from the Seshat databank."""

    polity_id: str = Field(
        description="Seshat polity identifier", json_schema_extra={"example": "it_roman_principate"}
    )
    name: str = Field(description="Polity name", json_schema_extra={"example": "Roman Principate"})
    start_year: int | None = Field(
        None,
        description="Start year (negative = BC)",
        json_schema_extra={"example": -27},
    )
    end_year: int | None = Field(
        None,
        description="End year (negative = BC)",
        json_schema_extra={"example": 284},
    )
    capital: str | None = Field(
        None, description="Capital city", json_schema_extra={"example": "Rome"}
    )
    territory: int | None = Field(
        None,
        description="Peak territory in km²",
        json_schema_extra={"example": 5000000},
    )


class EmpireListOut(BaseModel):
    """Response listing empires/polities."""

    empires: list[EmpireOut] = Field(description="Matching polities")
    total: int = Field(description="Total matching polities", json_schema_extra={"example": 400})
