"""
Configuration management for the ANCIENT NERDS - Research Platform data pipeline.

Uses pydantic-settings for type-safe configuration with environment variable support.
"""

from pathlib import Path
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    user: str = "ancient_map"
    password: str = ""  # Required: Set POSTGRES_PASSWORD in .env
    host: str = "localhost"
    port: int = 5432
    db: str = "ancient_map"

    @property
    def url(self) -> str:
        """Construct database URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def async_url(self) -> str:
        """Construct async database URL for SQLAlchemy async."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @property
    def url(self) -> str:
        """Construct Redis URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class PipelineSettings(BaseSettings):
    """Data pipeline settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Directories
    data_raw_dir: Path = Field(default=Path("./data/raw"))
    data_processed_dir: Path = Field(default=Path("./data/processed"))

    # Logging
    log_level: str = "INFO"

    # HTTP settings
    http_timeout: int = 30  # seconds
    http_max_retries: int = 3
    http_retry_delay: float = 1.0  # seconds

    # Processing settings
    batch_size: int = 1000

    @field_validator("data_raw_dir", "data_processed_dir", mode="before")
    @classmethod
    def ensure_path(cls, v):
        """Convert string to Path and ensure directory exists."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path


class APISettings(BaseSettings):
    """API server settings."""

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    reload: bool = False
    secret_key: str = ""  # Required: Set API_SECRET_KEY in .env (use: openssl rand -hex 32)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


class RateLimitSettings(BaseSettings):
    """Rate limiting settings by tier."""

    model_config = SettingsConfigDict(
        env_prefix="RATE_LIMIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anonymous: int = 100      # requests per day
    free: int = 1000          # requests per day
    pro: int = 50000          # requests per day
    enterprise: int = 0       # 0 = unlimited


class Settings(BaseSettings):
    """Main settings class that combines all settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    api: APISettings = Field(default_factory=APISettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    # External API keys (optional)
    europeana_api_key: Optional[str] = None
    mapbox_access_token: Optional[str] = None


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Convenience function for quick access
settings = get_settings()


def get_ai_thread_limit() -> int:
    """
    Get the thread limit for AI services.

    Returns cpu_count - 2 (reserved for FastAPI/Vite), with minimum 1 thread.
    This ensures 2 threads are always available for the web server and frontend.
    """
    import os
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count - 2)


# =============================================================================
# Data Source Configuration
# =============================================================================

# Priority order for source databases (lower = higher priority for canonical values)
SOURCE_PRIORITY = {
    "pleiades": 1,
    "unesco": 2,
    "historic_england": 3,
    "ads": 4,
    "open_context": 5,
    "dinaa": 6,
    "eamena": 7,
    "geonames": 8,
    "p3k14c": 9,
    # Add more sources as needed
}

# Data source URLs
DATA_SOURCES = {
    "pleiades": {
        "name": "Pleiades",
        "description": "A community-built gazetteer and graph of ancient places",
        "url": "https://pleiades.stoa.org/",
        "download_url": "https://pleiades.stoa.org/downloads/pleiades-places-latest.csv.gz",
        "json_url": "https://atlantides.org/downloads/pleiades/json/pleiades-places-latest.json.gz",
        "license": "CC-BY 3.0",
        "attribution": "Pleiades © Ancient World Mapping Center and Institute for the Study of the Ancient World",
    },
    "unesco": {
        "name": "UNESCO World Heritage Sites",
        "description": "Cultural and natural heritage sites of outstanding universal value",
        "url": "https://whc.unesco.org/",
        "api_url": "https://whc.unesco.org/en/list/xml/",
        "license": "Open with attribution",
        "attribution": "© UNESCO World Heritage Centre",
    },
    "geonames": {
        "name": "GeoNames",
        "description": "Geographical database with archaeological features",
        "url": "https://www.geonames.org/",
        "download_url": "https://download.geonames.org/export/dump/allCountries.zip",
        "license": "CC-BY 4.0",
        "attribution": "Data from GeoNames.org, CC-BY 4.0",
    },
    "open_context": {
        "name": "Open Context",
        "description": "Publisher of open research data in archaeology",
        "url": "https://opencontext.org/",
        "api_url": "https://opencontext.org/subjects-search/.json",
        "license": "CC-BY, CC0",
        "attribution": "Data from Open Context",
    },
    "p3k14c": {
        "name": "P3k14c Radiocarbon Database",
        "description": "Global database of archaeological radiocarbon dates",
        "url": "https://www.p3k14c.org/",
        "download_url": "https://core.tdar.org/collection/70213/p3k14c-data",
        "license": "CC0",
        "attribution": "P3k14c Database (Schmid et al. 2022)",
    },
    "historic_england": {
        "name": "Historic England",
        "description": "National heritage data for England",
        "url": "https://historicengland.org.uk/",
        "api_url": "https://services.arcgis.com/LmXvOCPHIZ4t/arcgis/rest/services",
        "license": "OGL v3.0",
        "attribution": "Contains data © Historic England. Licensed under OGL v3.0",
    },
    "eamena": {
        "name": "EAMENA",
        "description": "Endangered Archaeology in the Middle East and North Africa",
        "url": "https://eamena.org/",
        "api_url": "https://database.eamena.org/api/",
        "license": "Open Access",
        "attribution": "EAMENA Database",
    },
    # NCEI Natural Hazards
    "ncei_earthquakes": {
        "name": "NCEI Significant Earthquakes",
        "description": "6,000+ significant earthquakes with socioeconomic impact data",
        "url": "https://www.ncei.noaa.gov/maps/hazards/",
        "api_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes",
        "license": "Public Domain",
        "attribution": "NOAA National Centers for Environmental Information",
    },
    "ncei_tsunamis": {
        "name": "NCEI Tsunami Events",
        "description": "2,500+ tsunami events with source and impact data",
        "url": "https://www.ncei.noaa.gov/maps/hazards/",
        "api_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events",
        "license": "Public Domain",
        "attribution": "NOAA National Centers for Environmental Information",
    },
    "ncei_tsunami_obs": {
        "name": "NCEI Tsunami Observations",
        "description": "28,000+ tsunami observation points with wave heights",
        "url": "https://www.ncei.noaa.gov/maps/hazards/",
        "api_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/runups",
        "license": "Public Domain",
        "attribution": "NOAA National Centers for Environmental Information",
    },
    "ncei_volcanoes": {
        "name": "NCEI Significant Volcanic Eruptions",
        "description": "600+ volcanic eruptions with socioeconomic impact data",
        "url": "https://www.ncei.noaa.gov/maps/hazards/",
        "api_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes/events",
        "license": "Public Domain",
        "attribution": "NOAA National Centers for Environmental Information",
    },
}

# Standard site categories (unified taxonomy)
SITE_CATEGORIES = [
    "settlement",
    "temple",
    "tomb",
    "cemetery",
    "fortress",
    "palace",
    "monument",
    "sanctuary",
    "theater",
    "amphitheater",
    "stadium",
    "bath",
    "aqueduct",
    "road",
    "bridge",
    "port",
    "mine",
    "quarry",
    "villa",
    "farm",
    "workshop",
    "market",
    "church",
    "mosque",
    "pyramid",
    "tumulus",
    "megalith",
    "rock_art",
    "cave",
    "other",
    "unknown",
]

# Standard time periods (simplified)
TIME_PERIODS = {
    "prehistoric": {"start": -3000000, "end": -3000, "label": "Prehistoric"},
    "bronze_age": {"start": -3000, "end": -1200, "label": "Bronze Age"},
    "iron_age": {"start": -1200, "end": -500, "label": "Iron Age"},
    "classical": {"start": -500, "end": 500, "label": "Classical Antiquity"},
    "late_antique": {"start": 200, "end": 700, "label": "Late Antiquity"},
    "medieval": {"start": 500, "end": 1500, "label": "Medieval"},
    "unknown": {"start": None, "end": None, "label": "Unknown"},
}
