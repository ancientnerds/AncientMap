"""
Date parsing and normalization utilities.
"""

import re
from collections.abc import Mapping
from typing import Any

# Global date cutoffs - defines the project scope: Ancient History.
#
# The rule in force is the owner's LABEL rule (decision D58, 2026-10-24): only the medieval Old
# World - Europe, Byzantium and the Vikings - is out after 500 AD; every other region keeps its sites
# through 1500 AD (`scope_region`, `LABEL_CUTOFFS`, `passes_date_cutoff`).
#
# The numeric rule it replaces (owner decision E3, 2026-09-19; Oceania joined the Americas' cutoff by
# decision O7, 2026-09-26: "Ozeanien wie Amerika") stays here because the delivered scope lanes were
# rehearsed and applied with it (`e3_region`, `E3_CUTOFFS`, `passes_e3_cutoff`):
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


# ------------------------------------------------------------------- the label rule (D58, 2026-10-24)
#: D58 (owner, 2026-10-24): "only the medieval Old World of Europe, Byzantium and the Vikings is
#: out; non-European sites of 500-1500 stay in". The rule was always a label - the word "medieval"
#: carries the region in itself (no Americanist calls the Maya of 1200 AD medieval) - and Lalibela,
#: Angkor, Great Zimbabwe, Ife, Nara and the Islamic Golden Age are its named examples of what stays.
#: In machine form it is a region test: a site of the medieval Old World keeps the 500 AD cutoff,
#: every other site has 1500 AD.
MEDIEVAL_OLD_WORLD = "medieval Old World"
#: A point outside the Americas and Oceania whose row names no country: the rule cannot tell
#: Lisbon from Lagos, so the row keeps the Old World's stricter cutoff - only a country that is
#: not Europe's or Byzantium's earns a site the 1500 AD of the rest of the world. (The E3 rule
#: placed such a row in its rest of the world, 500 AD, too: for a row without a country the
#: label rule changes nothing. The loader looks the country up before it asks.)
UNPLACED_OLD_WORLD = "Old World, country unknown"
LABEL_CUTOFF_MEDIEVAL_OLD_WORLD = 500
LABEL_CUTOFF_REST_OF_WORLD = 1500
#: The five regions of the label rule, in the order `scope_region` tests them, and their cutoffs.
LABEL_CUTOFFS: Mapping[str, int] = {
    OCEANIA: DATE_CUTOFF_OCEANIA,
    AMERICAS: DATE_CUTOFF_AMERICAS,
    UNPLACED_OLD_WORLD: LABEL_CUTOFF_MEDIEVAL_OLD_WORLD,
    MEDIEVAL_OLD_WORLD: LABEL_CUTOFF_MEDIEVAL_OLD_WORLD,
    REST_OF_WORLD: LABEL_CUTOFF_REST_OF_WORLD,
}

#: The medieval Old World, by the `country` a row carries (compared as `country_key` reads it):
#:
#: * **Europe** as the United Nations geoscheme draws it (M49 region 150: Eastern, Northern,
#:   Southern and Western Europe) - the whole of Russia is Eastern Europe there, so Russia is
#:   listed and its Asian part taken out by `NON_EUROPEAN_PARTS` (east of the Urals, 60 E) -, the
#:   four nations the curated rows name instead of the United Kingdom, Kosovo, and the sea names
#:   the curated rows carry for a point off a European coast ("Baltic Sea");
#: * **Byzantium**: Turkiye (Anatolia and Thrace, the empire's heartland from 500 to 1453; the
#:   Seljuk and Ottoman sites of the same centuries count with it - the rule asks the region, not
#:   the dynasty) and Cyprus (Byzantine 395-1191). The empire's other lands of 500-1500 - the
#:   Levant, Egypt and Byzantine Africa until the Arab conquests of 636-698, and the Crusader states
#:   of 1099-1291 there - are `LABEL_BORDERLINE_COUNTRIES`: there the subject decides, not the place;
#: * **the Vikings**: Scandinavia, Iceland and the British Isles are Europe already; Norse Greenland
#:   is a borderline country, and L'Anse aux Meadows is named by its item (`VIKING_SUBJECT_QIDS`).
#:
#: As with Oceania, the ISO 3166-1 alpha-2 codes are listed too (`geonames` and `dare` store them).
EUROPE_ISO_CODES = frozenset(
    {
        # Eastern Europe
        "by", "bg", "cz", "hu", "pl", "md", "ro", "ru", "sk", "ua",
        # Northern Europe
        "ax", "dk", "ee", "fo", "fi", "gg", "is", "ie", "im", "je", "lv", "lt", "no", "sj", "se",
        "gb", "uk",
        # Southern Europe
        "al", "ad", "ba", "hr", "gi", "gr", "va", "it", "mt", "me", "mk", "pt", "sm", "rs", "si",
        "es", "xk",
        # Western Europe
        "at", "be", "fr", "de", "li", "lu", "mc", "nl", "ch",
    }
)  # fmt: skip
BYZANTIUM_ISO_CODES = frozenset({"tr", "cy"})
MEDIEVAL_OLD_WORLD_COUNTRIES = (
    EUROPE_ISO_CODES
    | BYZANTIUM_ISO_CODES
    | frozenset(
        {
            # Eastern Europe
            "belarus", "bulgaria", "czechia", "czech republic", "hungary", "poland", "moldova",
            "republic of moldova", "romania", "russia", "russian federation", "slovakia",
            "ukraine",
            # Northern Europe
            "aland islands", "åland islands", "denmark", "estonia", "faroe islands", "finland",
            "guernsey", "iceland", "ireland", "isle of man", "jersey", "latvia", "lithuania",
            "norway", "svalbard and jan mayen", "sweden", "united kingdom", "great britain",
            "england", "scotland", "wales", "northern ireland", "channel islands",
            # Southern Europe
            "albania", "andorra", "bosnia and herzegovina", "croatia", "gibraltar", "greece",
            "holy see", "vatican city", "italy", "malta", "montenegro", "north macedonia",
            "macedonia", "portugal", "san marino", "serbia", "slovenia", "spain", "kosovo",
            # Western Europe
            "austria", "belgium", "france", "germany", "liechtenstein", "luxembourg", "monaco",
            "netherlands", "the netherlands", "switzerland",
            # the seas a curated point off a European coast names
            "baltic sea", "north sea",
            # Byzantium
            "türkiye", "turkiye", "turkey", "cyprus", "northern cyprus",
        }
    )
)  # fmt: skip

_ASIAN_RUSSIA = (
    (60.0, -90.0, 180.0, 90.0),  # east of the Urals: Siberia and the Russian Far East
    (-180.0, -90.0, -170.0, 90.0),  # Chukotka east of the antimeridian
)
_CANARY_ISLANDS = ((-18.5, 27.3, -13.0, 29.5),)  # the Guanche islands, conquered 1402-1496
_FRENCH_INDIAN_OCEAN = (
    (55.2, -21.4, 55.9, -20.8),  # Reunion
    (44.9, -13.1, 45.4, -12.6),  # Mayotte (Swahili coast)
)

#: The parts of a medieval Old World state that lie outside it: a row whose `country_key` is the key
#: and whose point lies in one of the key's boxes (`(lon_min, lat_min, lon_max, lat_max)`, the edges
#: counting) is not in the medieval Old World. The Americas' and Oceania's parts of these states
#: (French Guiana, Greenland, French Polynesia, ...) are placed before this test, by
#: `in_oceania` and the Americas' longitude window.
NON_EUROPEAN_PARTS: Mapping[str, tuple[tuple[float, float, float, float], ...]] = {
    "russia": _ASIAN_RUSSIA,
    "russian federation": _ASIAN_RUSSIA,
    "ru": _ASIAN_RUSSIA,
    "spain": _CANARY_ISLANDS,
    "es": _CANARY_ISLANDS,
    "france": _FRENCH_INDIAN_OCEAN,
    "fr": _FRENCH_INDIAN_OCEAN,
}

#: The countries where the label - not the region - decides a site dated 500-1500 AD: the window
#: keeps them through 1500 (they are not Europe), but a site there may be of the medieval Old World
#: by its subject, and a scope verdict asks it (`label_borderline`):
#:
#: * the Levant (Syria, Lebanon, Israel, Palestine, Jordan): Byzantine until 636-640, the Crusader
#:   states of 1099-1291; the Umayyad, Abbasid, Fatimid, Ayyubid and Mamluk sites stay;
#: * Egypt and Byzantine Africa (Libya, Tunisia, Algeria): Byzantine until 641 and 698;
#: * the Caucasus (Georgia, Armenia, Azerbaijan): Christian kingdoms under Byzantine influence, not
#:   the empire itself;
#: * Greenland: the Norse settlements of 985-1450 are the Vikings; the Thule and Dorset sites stay.
LABEL_BORDERLINE_COUNTRIES = frozenset(
    {
        "syria", "lebanon", "israel", "palestine", "state of palestine", "west bank", "gaza",
        "jordan", "egypt", "libya", "tunisia", "algeria", "georgia", "armenia", "azerbaijan",
        "greenland",
        "sy", "lb", "il", "ps", "jo", "eg", "ly", "tn", "dz", "ge", "am", "az", "gl",
    }
)  # fmt: skip

#: Sites the label puts out by their subject wherever they lie: the Viking settlement of
#: L'Anse aux Meadows in Newfoundland (D58: "L'Anse aux Meadows stays out (Viking subject)"), by
#: its Wikidata item (read in `site_proposals` on 2026-10-24: Q189113).
VIKING_SUBJECT_QIDS: Mapping[str, str] = {"Q189113": "L'Anse aux Meadows"}


def in_medieval_old_world(country: str | None, lat: float | None, lon: float | None) -> bool:
    """Whether a row lies in the medieval Old World (Europe and Byzantium): its country is one of
    `MEDIEVAL_OLD_WORLD_COUNTRIES` and its point does not lie in a non-European part of that state
    (`NON_EUROPEAN_PARTS`; without a point no part can be told, and the country decides)."""
    key = country_key(country)
    if key is None or key not in MEDIEVAL_OLD_WORLD_COUNTRIES:
        return False
    if None in (lat, lon):
        return True
    return not any(
        lon_min <= lon <= lon_max and lat_min <= lat <= lat_max
        for lon_min, lat_min, lon_max, lat_max in NON_EUROPEAN_PARTS.get(key, ())
    )


def scope_region(record: Mapping[str, Any]) -> str | None:
    """The region of a record under the label rule (D58): `OCEANIA`, `AMERICAS`,
    `UNPLACED_OLD_WORLD` (a point outside the Americas and Oceania without a country),
    `MEDIEVAL_OLD_WORLD` or `REST_OF_WORLD`, or None without a longitude.

    Oceania first and the Americas by the longitude window second, as in `e3_region`; then the
    medieval Old World by the country; every other country is the rest of the world.
    """
    lon = record.get("lon")
    if lon is None:
        return None
    country = record.get("country")
    if in_oceania(country, record.get("lat"), lon):
        return OCEANIA
    if AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX:
        return AMERICAS
    if country is None:
        return UNPLACED_OLD_WORLD
    if in_medieval_old_world(country, record.get("lat"), lon):
        return MEDIEVAL_OLD_WORLD
    return REST_OF_WORLD


def window_date(record: Mapping[str, Any]) -> int | None:
    """The date the window tests: `period_end` unless it is missing or 0, else `period_start`."""
    return record.get("period_end") or record.get("period_start")


def label_borderline(record: Mapping[str, Any]) -> bool:
    """Whether the label, not the region, decides the record (D58): it has a longitude, is dated
    after 500 AD and through 1500 AD, and its country is one of `LABEL_BORDERLINE_COUNTRIES` (none
    of them Oceania's or the medieval Old World's, so the window keeps the record through 1500). A
    scope verdict asks whether its subject is Byzantine, Crusader or Norse."""
    date = window_date(record)
    if record.get("lon") is None or date is None:
        return False
    if not LABEL_CUTOFF_MEDIEVAL_OLD_WORLD < date <= LABEL_CUTOFF_REST_OF_WORLD:
        return False
    return country_key(record.get("country")) in LABEL_BORDERLINE_COUNTRIES


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


def passes_date_cutoff(record: Mapping[str, Any]) -> bool:
    """
    Check if record passes the GLOBAL regional date cutoff: the label rule (owner decision D58,
    2026-10-24).

    Applied to ALL sources during loading. This defines project scope.

    Rules (`scope_region`):
    - Oceania (the country, or a Pacific island group of the state named): <= 1500 AD
    - Americas (lon -170 to -30): <= 1500 AD
    - The medieval Old World (Europe, Byzantium): <= 500 AD
    - Rest of World (Asia, Africa, the Near East outside Byzantium): <= 1500 AD
    - A point outside the Americas and Oceania without a country: <= 500 AD (only a country
      proves a site is not of the medieval Old World)
    - Records WITHOUT dates: INCLUDED (can't filter unknown)
    - Records without a longitude: INCLUDED

    A record of a `LABEL_BORDERLINE_COUNTRIES` country passes; whether its subject is Byzantine,
    Crusader or Norse is a scope verdict's question (`label_borderline`), not this check's.

    Args:
        record: Site record dict with period_start, period_end, lat, lon and country fields

    Returns:
        True if record should be included, False if it should be filtered out
    """
    date = window_date(record)
    if date is None:
        return True  # No date = include (conservative)

    region = scope_region(record)
    if region is None:
        return True  # No location = include

    return date <= LABEL_CUTOFFS[region]


def passes_e3_cutoff(record: Mapping[str, Any]) -> bool:
    """The numeric rule D58 replaced (E3 with O7): Oceania and the Americas through 1500 AD, the
    rest of the world through 500 AD (`e3_region`). Kept for the delivered scope lanes, whose
    rendered SQL (`mechanical.lane.outside_e3_window`) is this rule negated, and for the E3
    census (`census/tests/t11_scope_window.py`)."""
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
