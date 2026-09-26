"""
Date parsing and normalization utilities.
"""

import re
from collections.abc import Mapping
from typing import Any

# Global date cutoffs - defines the project scope: Ancient History (owner decision E3, 2026-09-19;
# Oceania joined the Americas' cutoff by decision O7, 2026-09-26: "Ozeanien wie Amerika")
# Americas: Pre-Columbian (up to 1500 AD)
# Oceania: pre-contact, like the Americas (up to 1500 AD)
# Rest of World: Classical/Ancient (up to 500 AD)
DATE_CUTOFF_AMERICAS = 1500
DATE_CUTOFF_OCEANIA = 1500
DATE_CUTOFF_REST_OF_WORLD = 500

# Americas bounding box (longitude-based)
AMERICAS_LON_MIN = -170  # Western Alaska/Aleutians
AMERICAS_LON_MAX = -30  # Eastern Brazil

#: The three E3 regions, in the order `e3_region` tests them.
OCEANIA = "Oceania"
AMERICAS = "Americas"
REST_OF_WORLD = "rest of world"
E3_CUTOFFS: Mapping[str, int] = {
    OCEANIA: DATE_CUTOFF_OCEANIA,
    AMERICAS: DATE_CUTOFF_AMERICAS,
    REST_OF_WORLD: DATE_CUTOFF_REST_OF_WORLD,
}

#: Oceania as the United Nations geoscheme draws it (M49 region 009, with its four sub-regions
#: Australia and New Zealand, Melanesia, Micronesia and Polynesia): every state and territory,
#: under the names a row's `country` carries, compared as `country_key` reads them. Three island
#: names M49 files under another region's state are added because a row may carry the island's own
#: name: Hawaii (United States) and Easter Island / Rapa Nui (Chile). Rows that carry the state's
#: name instead - on production on 2026-09-26 Easter Island's eleven curated rows say "Chile" and
#: French Polynesia's three say "France" - are placed by `OCEANIA_PARTS`. Western New Guinea is
#: Indonesia's, which M49 files under South-eastern Asia: it stays in the rest of the world.
#:
#: The spellings are the ones `unified_sites.country` holds (read-only, 2026-09-26): the curated
#: rows and `lookup_country` (Natural Earth's `name`) spell the name out; `geonames` and `dare`
#: store the ISO 3166-1 alpha-2 code (`AU`, `GU`, `PF`, ...), so every Oceania code is listed too;
#: `earth_impacts` and `radiocarbon_paleo` store "Region, Country" ("Queensland, Australia"),
#: which `country_key` reads by its last part.
OCEANIA_ISO_CODES = frozenset(
    {
        # Australia and New Zealand
        "au",
        "nz",
        "cx",
        "cc",
        "hm",
        "nf",
        # Melanesia
        "fj",
        "nc",
        "pg",
        "sb",
        "vu",
        # Micronesia
        "gu",
        "ki",
        "mh",
        "fm",
        "nr",
        "mp",
        "pw",
        "um",
        # Polynesia
        "as",
        "ck",
        "nu",
        "pn",
        "pf",
        "ws",
        "tk",
        "to",
        "tv",
        "wf",
    }
)
OCEANIA_COUNTRIES = OCEANIA_ISO_CODES | frozenset(
    {
        # Australia and New Zealand
        "australia",
        "new zealand",
        "christmas island",
        "cocos (keeling) islands",
        "cocos islands",
        "heard island and mcdonald islands",
        "norfolk island",
        # Melanesia
        "fiji",
        "new caledonia",
        "papua new guinea",
        "solomon islands",
        "vanuatu",
        # Micronesia
        "guam",
        "kiribati",
        "marshall islands",
        "micronesia",
        "federated states of micronesia",
        "micronesia (federated states of)",
        "nauru",
        "northern mariana islands",
        "palau",
        "united states minor outlying islands",
        # Polynesia
        "american samoa",
        "cook islands",
        "french polynesia",
        "niue",
        "pitcairn",
        "pitcairn islands",
        "samoa",
        "tokelau",
        "tonga",
        "tuvalu",
        "wallis and futuna",
        "wallis and futuna islands",
        # island names a row may carry instead of its state's
        "hawaii",
        "easter island",
        "rapa nui",
    }
)

_US_PACIFIC: tuple[tuple[float, float, float, float], ...] = (
    (-179.0, 18.0, -154.0, 29.0),  # Hawaii, the Northwestern Hawaiian Islands, Midway
    (144.0, 13.0, 147.0, 21.0),  # Guam and the Northern Mariana Islands
    (-172.0, -15.0, -168.0, -11.0),  # American Samoa, Swains Island included
    (166.0, 19.0, 167.0, 20.0),  # Wake Island
)

_RAPA_NUI = ((-110.0, -28.0, -105.0, -26.0),)  # Rapa Nui and Salas y Gomez
_FRENCH_PACIFIC = (
    (-155.0, -28.5, -134.0, -7.0),  # French Polynesia
    (157.0, -24.0, 173.0, -17.0),  # New Caledonia with Chesterfield, Matthew and Hunter
    (-179.0, -15.0, -176.0, -13.0),  # Wallis and Futuna
)
_PITCAIRN = ((-131.0, -26.0, -124.0, -23.0),)  # the Pitcairn Islands

#: The Pacific islands of states whose rows carry the state's name (or its ISO code): one box per
#: island group, `(lon_min, lat_min, lon_max, lat_max)` in degrees, each drawn around the group and
#: reaching no other part of that state. A row is Oceania when its `country_key` is the key and its
#: point lies in one of the key's boxes (the edges count).
OCEANIA_PARTS: Mapping[str, tuple[tuple[float, float, float, float], ...]] = {
    "chile": _RAPA_NUI,
    "cl": _RAPA_NUI,
    "france": _FRENCH_PACIFIC,
    "fr": _FRENCH_PACIFIC,
    "united kingdom": _PITCAIRN,
    "gb": _PITCAIRN,
    "united states": _US_PACIFIC,
    "united states of america": _US_PACIFIC,
    "usa": _US_PACIFIC,
    "us": _US_PACIFIC,
}


def country_key(country: str | None) -> str | None:
    """A `country` value as the Oceania lists compare it: the text after its last comma (the
    whole value when it has none - "Queensland, Australia" is read as "australia"), spaces
    stripped, lower-cased. `mechanical/lane.py` renders the same reading into SQL from the same
    lists (`in_oceania_sql`)."""
    if country is None:
        return None
    return country.rsplit(",", 1)[-1].strip(" ").lower()


def in_oceania(country: str | None, lat: float | None, lon: float | None) -> bool:
    """Whether a row lies in Oceania: its country is one of Oceania's, or its point lies on a
    Pacific island group of the state it names (`OCEANIA_PARTS`)."""
    key = country_key(country)
    if key is None:
        return False
    if key in OCEANIA_COUNTRIES:
        return True
    if lat is None or lon is None:
        return False
    return any(
        lon_min <= lon <= lon_max and lat_min <= lat <= lat_max
        for lon_min, lat_min, lon_max, lat_max in OCEANIA_PARTS.get(key, ())
    )


def e3_region(record: Mapping[str, Any]) -> str | None:
    """The E3 region of a record (`OCEANIA`, `AMERICAS` or `REST_OF_WORLD`), or None when it has
    no longitude and the region cannot be told.

    Oceania first: Hawaii, Easter Island and French Polynesia lie inside the Americas' longitude
    window too, and they are Oceania. Then the Americas by the longitude window, then the rest.
    """
    lon = record.get("lon")
    if lon is None:
        return None
    if in_oceania(record.get("country"), record.get("lat"), lon):
        return OCEANIA
    if AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX:
        return AMERICAS
    return REST_OF_WORLD


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
    - Oceania (`e3_region`: the country, or a Pacific island group of the state named): <= 1500 AD
    - Americas (lon -170 to -30): Must be <= 1500 AD
    - Rest of World: Must be <= 500 AD
    - Records WITHOUT dates: INCLUDED (can't filter unknown)

    Args:
        record: Site record dict with period_start, period_end, lat, lon and country fields; a
            record without a country is placed by its longitude alone

    Returns:
        True if record should be included, False if it should be filtered out
    """
    # Get the relevant date (prefer period_end, fallback to period_start)
    date = record.get("period_end") or record.get("period_start")
    if date is None:
        return True  # No date = include (conservative)

    region = e3_region(record)
    if region is None:
        return True  # No location = include

    return date <= E3_CUTOFFS[region]


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
