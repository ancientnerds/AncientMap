"""
API configuration loader.

Loads API keys and settings from config.json in the project root.
Falls back to environment variables if config.json is missing or incomplete.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Find project root (where config.json should be)
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env file from project root
load_dotenv(PROJECT_ROOT / ".env")
CONFIG_FILE = PROJECT_ROOT / "config.json"


@lru_cache
def load_config() -> dict:
    """Load configuration from config.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid config.json: {e}")
    return {}


def get_api_key(service: str, key_name: str = "api_key") -> str | None:
    """
    Get API key for a service.

    Checks config.json first, then environment variables.

    Args:
        service: Service name (mapbox)
        key_name: Key name within service config (access_token)

    Returns:
        API key string or None
    """
    config = load_config()

    # Try config.json first
    api_keys = config.get("api_keys", {})
    service_config = api_keys.get(service, {})
    key = service_config.get(key_name)

    if key:
        return key

    # Fall back to environment variables
    env_var_map = {
        ("mapbox", "access_token"): "MAPBOX_ACCESS_TOKEN",
    }

    env_var = env_var_map.get((service, key_name))
    if env_var:
        return os.getenv(env_var)

    return None


def get_rate_limit(service: str) -> float:
    """Get rate limit delay for a service (seconds between requests)."""
    config = load_config()
    rate_limits = config.get("rate_limits", {})

    defaults = {
        "wikidata": 2.0,
        "commons": 0.5,
        "megalithic": 1.0,
    }

    return rate_limits.get(service, defaults.get(service, 1.0))


def get_database_config() -> dict:
    """Get database configuration."""
    config = load_config()
    db_config = config.get("database", {})

    return {
        "host": db_config.get("host") or os.getenv("POSTGRES_HOST", "localhost"),
        "port": db_config.get("port") or int(os.getenv("POSTGRES_PORT", "5432")),
        "user": db_config.get("user") or os.getenv("POSTGRES_USER", "ancient_map"),
        "password": db_config.get("password") or os.getenv("POSTGRES_PASSWORD", ""),
        "database": db_config.get("database") or os.getenv("POSTGRES_DB", "ancient_map"),
    }


def get_mapbox_token() -> str | None:
    """Get Mapbox access token."""
    return get_api_key("mapbox", "access_token")


def print_config_status():
    """Print status of API key configuration."""
    services = [
        ("Mapbox", "mapbox", "access_token", "https://account.mapbox.com/access-tokens/"),
    ]

    print("\n" + "=" * 70)
    print("API KEY CONFIGURATION STATUS")
    print("=" * 70)
    print(f"Config file: {CONFIG_FILE}")
    print(f"Config exists: {CONFIG_FILE.exists()}")
    print("-" * 70)

    for name, service, key_name, url in services:
        key = get_api_key(service, key_name)
        status = "OK" if key else "MISSING"
        masked = f"{key[:4]}...{key[-4:]}" if key and len(key) > 8 else ("SET" if key else "NOT SET")
        print(f"{name:15} [{status:7}] {masked:20} {url}")

    print("=" * 70)
    print("\nTo configure, set MAPBOX_ACCESS_TOKEN in .env file")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print_config_status()
