"""Utility modules for the data pipeline."""

from pipeline.utils.http import fetch_with_retry, download_file
from pipeline.utils.logging import setup_logging
from pipeline.utils.geo import (
    is_valid_coordinates,
    haversine_distance,
    parse_wkt_point,
    get_centroid,
    normalize_coordinates,
)
from pipeline.utils.text import (
    normalize_name,
    normalize_for_search,
    clean_description,
    extract_period_from_text,
    sanitize_filename,
)

__all__ = [
    # HTTP utilities
    "fetch_with_retry",
    "download_file",
    # Logging
    "setup_logging",
    # Geographic utilities
    "is_valid_coordinates",
    "haversine_distance",
    "parse_wkt_point",
    "get_centroid",
    "normalize_coordinates",
    # Text utilities
    "normalize_name",
    "normalize_for_search",
    "clean_description",
    "extract_period_from_text",
    "sanitize_filename",
]
