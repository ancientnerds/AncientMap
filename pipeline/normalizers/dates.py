"""
Date parsing and normalization utilities.
"""

from typing import Dict, Optional

# Global date cutoffs - defines the project scope: Ancient History
# Americas: Pre-Columbian (up to 1500 AD)
# Rest of World: Classical/Ancient (up to 500 AD)
DATE_CUTOFF_AMERICAS = 1500
DATE_CUTOFF_REST_OF_WORLD = 500

# Americas bounding box (longitude-based)
AMERICAS_LON_MIN = -170  # Western Alaska/Aleutians
AMERICAS_LON_MAX = -30   # Eastern Brazil


def parse_year(value) -> Optional[int]:
    """Parse a year value from various formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value != 0 else None
    if isinstance(value, str):
        # Handle ISO dates like "2024-01-15"
        if "-" in value and len(value) >= 4:
            try:
                return int(value.split("-")[0])
            except ValueError:
                pass
        # Handle plain years
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def passes_date_cutoff(record: Dict) -> bool:
    """
    Check if record passes the GLOBAL regional date cutoff.

    Applied to ALL sources during loading. This defines project scope.

    Rules:
    - Americas (lon -170 to -30): Must be <= 1500 AD
    - Rest of World: Must be <= 500 AD
    - Records WITHOUT dates: INCLUDED (can't filter unknown)

    Args:
        record: Site record dict with period_start, period_end, lat, lon fields

    Returns:
        True if record should be included, False if it should be filtered out
    """
    # Get the relevant date (prefer period_end, fallback to period_start)
    date = record.get("period_end") or record.get("period_start")
    if date is None:
        return True  # No date = include (conservative)

    # Determine region by longitude
    lon = record.get("lon")
    if lon is None:
        return True  # No location = include

    is_americas = AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX
    cutoff = DATE_CUTOFF_AMERICAS if is_americas else DATE_CUTOFF_REST_OF_WORLD

    return date <= cutoff


def parse_iso_date(date_str: str) -> Optional[int]:
    """Parse ISO date string and extract year."""
    if not date_str:
        return None
    try:
        # Handle YYYY-MM-DD or just YYYY
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


def parse_epoch_timestamp(ts: int) -> Optional[int]:
    """Parse Unix epoch timestamp and extract year."""
    if ts is None:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.year
    except (ValueError, OSError):
        return None
