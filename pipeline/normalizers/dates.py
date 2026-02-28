"""
Date parsing and normalization utilities.
"""

import re

# Global date cutoffs - defines the project scope: Ancient History
# Americas: Pre-Columbian (up to 1500 AD)
# Rest of World: Classical/Ancient (up to 500 AD)
DATE_CUTOFF_AMERICAS = 1500
DATE_CUTOFF_REST_OF_WORLD = 500

# Americas bounding box (longitude-based)
AMERICAS_LON_MIN = -170  # Western Alaska/Aleutians
AMERICAS_LON_MAX = -30  # Eastern Brazil


_BC_AD_RE = re.compile(
    r"^\s*(\d+)\s*(?:-\s*\d+\s*)?(?:(B)\s*\.?\s*C|(?:(A)\s*\.?\s*D))",
    re.IGNORECASE,
)


def parse_year(value) -> int | None:
    """Parse a year value from various formats.

    Handles: plain ints/floats, ISO dates ("2024-01-15"),
    BC/AD strings ("3500 BC", "3500 B C", "150 AD", "4500 - 2500 BC").
    For ranges, returns the start (first number).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value != 0 else None
    if isinstance(value, str):
        # Try BC/AD pattern first — "3500 BC", "3500 B C", "150 - 160 AD"
        m = _BC_AD_RE.match(value)
        if m:
            year = int(m.group(1))
            if m.group(2):  # BC
                return -year
            return year

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


def passes_date_cutoff(record: dict) -> bool:
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


def parse_iso_date(date_str: str) -> int | None:
    """Parse ISO date string and extract year."""
    if not date_str:
        return None
    try:
        # Handle YYYY-MM-DD or just YYYY
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


def parse_epoch_timestamp(ts: int) -> int | None:
    """Parse Unix epoch timestamp and extract year."""
    if ts is None:
        return None
    from datetime import datetime

    try:
        dt = datetime.fromtimestamp(ts)
        return dt.year
    except (ValueError, OSError):
        return None


_WIKIDATA_TIME_RE = re.compile(r"^([+-])0*(\d+)-")


def extract_year_from_wikidata_time(time_str: str, precision: int) -> int | None:
    """Convert Wikidata time value to a year integer.

    Handles precision levels:
      6 = millennium  → midpoint of millennium (e.g. +3000 → 2500)
      7 = century     → midpoint of century (e.g. +0500 → 450)
      8 = decade      → start of decade
      9+ = year       → exact year

    Args:
        time_str: Wikidata ISO-style time, e.g. "+2024-01-01T00:00:00Z" or "-0500-00-00T00:00:00Z"
        precision: Wikidata precision integer (6=millennium, 7=century, 8=decade, 9=year, etc.)
    """
    if not time_str:
        return None
    m = _WIKIDATA_TIME_RE.match(time_str)
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    year = int(m.group(2))
    if year == 0:
        return None
    if precision <= 6:
        # Millennium precision: return midpoint (year - 500), but floor at 1
        return sign * max(year - 500, 1)
    if precision == 7:
        # Century precision: return midpoint (year - 50), but floor at 1
        return sign * max(year - 50, 1)
    return sign * year
