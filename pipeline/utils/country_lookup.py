"""
Country lookup utility for reverse geocoding coordinates to country names.

Uses a pre-built country boundaries dataset for fast point-in-polygon lookups.
Falls back to a simple lat/lon bounding box approach when shapely is not available.
"""

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

# Try to import shapely for precise polygon lookups
try:
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    logger.warning("Shapely not available, using bounding box fallback for country lookup")


# Path to country boundaries data
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "boundaries"
COUNTRIES_FILE = DATA_DIR / "countries.geojson"


class CountryLookup:
    """
    Fast country lookup from coordinates using spatial indexing.

    Usage:
        lookup = CountryLookup()
        country = lookup.get_country(45.0, 12.0)  # Returns "Italy"
    """

    def __init__(self):
        self._countries: list[dict] = []
        self._spatial_index = None
        self._geometries = []
        self._loaded = False

    def _load_data(self):
        """Load country boundaries data lazily."""
        if self._loaded:
            return

        if not COUNTRIES_FILE.exists():
            logger.warning(f"Country boundaries file not found: {COUNTRIES_FILE}")
            logger.info("Run 'python -m pipeline.utils.country_lookup --download' to fetch data")
            self._loaded = True
            return

        try:
            with open(COUNTRIES_FILE, encoding="utf-8") as f:
                data = json.load(f)

            features = data.get("features", [])
            logger.info(f"Loading {len(features)} country boundaries...")

            if SHAPELY_AVAILABLE:
                # Build spatial index for fast lookups
                for feature in features:
                    props = feature.get("properties", {})
                    geom = feature.get("geometry")

                    if geom:
                        try:
                            shapely_geom = shape(geom)
                            self._geometries.append(shapely_geom)
                            self._countries.append(
                                {
                                    "name": props.get("ADMIN")
                                    or props.get("name")
                                    or props.get("NAME"),
                                    "iso_a2": props.get("ISO_A2") or props.get("iso_a2"),
                                    "iso_a3": props.get("ISO_A3") or props.get("iso_a3"),
                                }
                            )
                        except Exception as e:
                            logger.debug(f"Failed to parse geometry: {e}")

                if self._geometries:
                    self._spatial_index = STRtree(self._geometries)
                    logger.info(f"Built spatial index with {len(self._geometries)} countries")
            else:
                # Fallback: store bounding boxes
                for feature in features:
                    props = feature.get("properties", {})
                    geom = feature.get("geometry")

                    if geom:
                        bbox = self._compute_bbox(geom)
                        if bbox:
                            self._countries.append(
                                {
                                    "name": props.get("ADMIN")
                                    or props.get("name")
                                    or props.get("NAME"),
                                    "iso_a2": props.get("ISO_A2") or props.get("iso_a2"),
                                    "iso_a3": props.get("ISO_A3") or props.get("iso_a3"),
                                    "bbox": bbox,
                                    "geometry": geom,
                                }
                            )

                logger.info(f"Loaded {len(self._countries)} country bounding boxes")

        except Exception as e:
            logger.error(f"Failed to load country boundaries: {e}")

        self._loaded = True

    def _compute_bbox(self, geometry: dict) -> tuple[float, float, float, float] | None:
        """Compute bounding box from GeoJSON geometry."""
        coords = self._extract_all_coords(geometry)
        if not coords:
            return None

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return (min(lons), min(lats), max(lons), max(lats))

    def _extract_all_coords(self, geometry: dict) -> list[tuple[float, float]]:
        """Extract all coordinates from a GeoJSON geometry."""
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        result = []

        if geom_type == "Point":
            result.append(tuple(coords[:2]))
        elif geom_type == "MultiPoint" or geom_type == "LineString":
            result.extend([tuple(c[:2]) for c in coords])
        elif geom_type == "Polygon":
            for ring in coords:
                result.extend([tuple(c[:2]) for c in ring])
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                for ring in polygon:
                    result.extend([tuple(c[:2]) for c in ring])
        elif geom_type == "MultiLineString":
            for line in coords:
                result.extend([tuple(c[:2]) for c in line])
        elif geom_type == "GeometryCollection":
            for geom in geometry.get("geometries", []):
                result.extend(self._extract_all_coords(geom))

        return result

    def _point_in_polygon(self, lon: float, lat: float, geometry: dict) -> bool:
        """Simple ray casting algorithm for point-in-polygon test."""
        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")

        if geom_type == "Polygon":
            return self._point_in_polygon_rings(lon, lat, coords)
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                if self._point_in_polygon_rings(lon, lat, polygon):
                    return True
        return False

    def _point_in_polygon_rings(self, lon: float, lat: float, rings: list) -> bool:
        """Check if point is in polygon defined by rings (exterior + holes)."""
        if not rings:
            return False

        # Check exterior ring
        exterior = rings[0]
        if not self._point_in_ring(lon, lat, exterior):
            return False

        # Check holes (should NOT be in any hole)
        for hole in rings[1:]:
            if self._point_in_ring(lon, lat, hole):
                return False

        return True

    def _point_in_ring(self, lon: float, lat: float, ring: list) -> bool:
        """Ray casting algorithm for point in ring."""
        n = len(ring)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]

            if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def get_country(self, lat: float, lon: float) -> str | None:
        """
        Get country name for given coordinates.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees

        Returns:
            Country name or None if not found
        """
        self._load_data()

        if not self._countries:
            return None

        if SHAPELY_AVAILABLE and self._spatial_index:
            point = Point(lon, lat)

            # Query spatial index for candidates
            candidates = self._spatial_index.query(point)

            for idx in candidates:
                if hasattr(idx, "__index__"):
                    idx = idx.__index__()
                if self._geometries[idx].contains(point):
                    return self._countries[idx]["name"]
        else:
            # Bounding box fallback
            for country in self._countries:
                bbox = country.get("bbox")
                if bbox:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        # Further check with polygon
                        if self._point_in_polygon(lon, lat, country.get("geometry", {})):
                            return country["name"]

        return None

    def get_country_iso(self, lat: float, lon: float) -> str | None:
        """Get ISO country code for given coordinates."""
        self._load_data()

        if not self._countries:
            return None

        if SHAPELY_AVAILABLE and self._spatial_index:
            point = Point(lon, lat)
            candidates = self._spatial_index.query(point)

            for idx in candidates:
                if hasattr(idx, "__index__"):
                    idx = idx.__index__()
                if self._geometries[idx].contains(point):
                    return self._countries[idx].get("iso_a2")
        else:
            for country in self._countries:
                bbox = country.get("bbox")
                if bbox:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        if self._point_in_polygon(lon, lat, country.get("geometry", {})):
                            return country.get("iso_a2")

        return None


# Global singleton instance
_lookup_instance: CountryLookup | None = None


def get_country_lookup() -> CountryLookup:
    """Get singleton CountryLookup instance."""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = CountryLookup()
    return _lookup_instance


@lru_cache(maxsize=10000)
def lookup_country(lat: float, lon: float) -> str | None:
    """
    Lookup country name from coordinates (cached).

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees

    Returns:
        Country name or None if not found
    """
    return get_country_lookup().get_country(lat, lon)


# Country name → ISO 3166-1 alpha-2 code mapping.
# Ported from frontend countryFlags.ts + Natural Earth long-form names.
NAME_TO_ISO: dict[str, str] = {
    # Middle East & Near East
    "egypt": "EG",
    "iraq": "IQ",
    "iran": "IR",
    "syria": "SY",
    "jordan": "JO",
    "israel": "IL",
    "lebanon": "LB",
    "türkiye": "TR",
    "turkey": "TR",  # legacy alias — canonical name is "Türkiye"
    "saudi arabia": "SA",
    "yemen": "YE",
    "oman": "OM",
    "united arab emirates": "AE",
    "kuwait": "KW",
    "bahrain": "BH",
    "qatar": "QA",
    "palestine": "PS",
    "cyprus": "CY",
    # Europe
    "greece": "GR",
    "italy": "IT",
    "spain": "ES",
    "france": "FR",
    "portugal": "PT",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "great britain": "GB",
    "ireland": "IE",
    "germany": "DE",
    "austria": "AT",
    "switzerland": "CH",
    "netherlands": "NL",
    "belgium": "BE",
    "luxembourg": "LU",
    "denmark": "DK",
    "sweden": "SE",
    "norway": "NO",
    "finland": "FI",
    "iceland": "IS",
    "poland": "PL",
    "czech republic": "CZ",
    "czechia": "CZ",
    "slovakia": "SK",
    "hungary": "HU",
    "romania": "RO",
    "bulgaria": "BG",
    "serbia": "RS",
    "croatia": "HR",
    "slovenia": "SI",
    "bosnia and herzegovina": "BA",
    "montenegro": "ME",
    "north macedonia": "MK",
    "macedonia": "MK",
    "albania": "AL",
    "kosovo": "XK",
    "moldova": "MD",
    "ukraine": "UA",
    "belarus": "BY",
    "lithuania": "LT",
    "latvia": "LV",
    "estonia": "EE",
    "malta": "MT",
    "monaco": "MC",
    "andorra": "AD",
    "san marino": "SM",
    "vatican city": "VA",
    "liechtenstein": "LI",
    # Asia
    "china": "CN",
    "japan": "JP",
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "democratic people's republic of korea": "KP",
    "taiwan": "TW",
    "mongolia": "MN",
    "vietnam": "VN",
    "viet nam": "VN",
    "thailand": "TH",
    "myanmar": "MM",
    "burma": "MM",
    "cambodia": "KH",
    "laos": "LA",
    "lao people's democratic republic": "LA",
    "malaysia": "MY",
    "singapore": "SG",
    "indonesia": "ID",
    "philippines": "PH",
    "brunei": "BN",
    "east timor": "TL",
    "timor-leste": "TL",
    # South Asia
    "india": "IN",
    "pakistan": "PK",
    "bangladesh": "BD",
    "sri lanka": "LK",
    "nepal": "NP",
    "bhutan": "BT",
    "maldives": "MV",
    "afghanistan": "AF",
    # Central Asia
    "kazakhstan": "KZ",
    "uzbekistan": "UZ",
    "turkmenistan": "TM",
    "tajikistan": "TJ",
    "kyrgyzstan": "KG",
    # Russia & Caucasus
    "russia": "RU",
    "russian federation": "RU",
    "georgia": "GE",
    "georgia (country)": "GE",
    "armenia": "AM",
    "azerbaijan": "AZ",
    # Africa
    "morocco": "MA",
    "algeria": "DZ",
    "tunisia": "TN",
    "libya": "LY",
    "sudan": "SD",
    "south sudan": "SS",
    "ethiopia": "ET",
    "eritrea": "ER",
    "djibouti": "DJ",
    "somalia": "SO",
    "kenya": "KE",
    "tanzania": "TZ",
    "united republic of tanzania": "TZ",
    "uganda": "UG",
    "rwanda": "RW",
    "burundi": "BI",
    "democratic republic of the congo": "CD",
    "drc": "CD",
    "congo": "CG",
    "republic of the congo": "CG",
    "gabon": "GA",
    "equatorial guinea": "GQ",
    "cameroon": "CM",
    "central african republic": "CF",
    "chad": "TD",
    "niger": "NE",
    "nigeria": "NG",
    "benin": "BJ",
    "togo": "TG",
    "ghana": "GH",
    "ivory coast": "CI",
    "côte d'ivoire": "CI",
    "liberia": "LR",
    "sierra leone": "SL",
    "guinea": "GN",
    "guinea-bissau": "GW",
    "senegal": "SN",
    "gambia": "GM",
    "the gambia": "GM",
    "republic of the gambia": "GM",
    "mauritania": "MR",
    "mali": "ML",
    "burkina faso": "BF",
    "cape verde": "CV",
    "cabo verde": "CV",
    "angola": "AO",
    "zambia": "ZM",
    "zimbabwe": "ZW",
    "malawi": "MW",
    "mozambique": "MZ",
    "botswana": "BW",
    "namibia": "NA",
    "south africa": "ZA",
    "lesotho": "LS",
    "eswatini": "SZ",
    "swaziland": "SZ",
    "madagascar": "MG",
    "mauritius": "MU",
    "seychelles": "SC",
    "comoros": "KM",
    # Americas
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "canada": "CA",
    "mexico": "MX",
    "guatemala": "GT",
    "belize": "BZ",
    "honduras": "HN",
    "el salvador": "SV",
    "nicaragua": "NI",
    "costa rica": "CR",
    "panama": "PA",
    "cuba": "CU",
    "jamaica": "JM",
    "haiti": "HT",
    "dominican republic": "DO",
    "puerto rico": "PR",
    "bahamas": "BS",
    "trinidad and tobago": "TT",
    "barbados": "BB",
    "colombia": "CO",
    "venezuela": "VE",
    "ecuador": "EC",
    "peru": "PE",
    "bolivia": "BO",
    "brazil": "BR",
    "paraguay": "PY",
    "uruguay": "UY",
    "argentina": "AR",
    "chile": "CL",
    "guyana": "GY",
    "suriname": "SR",
    "french guiana": "GF",
    # Oceania
    "australia": "AU",
    "new zealand": "NZ",
    "papua new guinea": "PG",
    "fiji": "FJ",
    "solomon islands": "SB",
    "vanuatu": "VU",
    "samoa": "WS",
    "tonga": "TO",
    "micronesia": "FM",
    "palau": "PW",
    "marshall islands": "MH",
    "kiribati": "KI",
    "nauru": "NR",
    "tuvalu": "TV",
    # Territories & Dependencies
    "greenland": "GL",
    "easter island": "CL",
    "faroe islands": "FO",
    "gibraltar": "GI",
    "bermuda": "BM",
    "cayman islands": "KY",
    "hong kong": "HK",
    "macau": "MO",
}

# Sub-national place names that contain a country's name as a whole word, each mapped to the ISO code
# of the country it really lies in (never the contained name's). Phase 4's V14 (scripts/remediation/
# phase4/verify4.py) reads them beside NAME_TO_ISO, longest first, so "New South Wales" is Australia
# and not Wales: pilot 3 (2026-09-24) held Lake Mungo, "a dry lake located in New South Wales,
# Australia", as a site placed in Wales. Derived from data - the census run's 88,936 pool sentences
# scanned for a NAME_TO_ISO name directly preceded by a capitalised word or inside a longer proper
# name - and each entry verified (output/remediation/AUDIT_LOG.md, pilot 4). Left out: names without
# one country ("New Guinea": PG and ID; "Belize River": GT and BZ; "Caucasian Albania", "British
# India", "Middle Niger"), the bare "West Azerbaijan" (the census also uses it for western
# Azerbaijan), and names that are no sub-national place ("British Honduras", the colony that is all
# of Belize). "South Wales" is Wales and is not listed. Not in NAME_TO_ISO, so country_name_variants
# and normalize_country never return one of these names.
SUBNATIONAL_NAME_TO_ISO: dict[str, str] = {
    "new south wales": "AU",
    "new mexico": "US",
    "new england": "US",
    "central macedonia": "GR",
    "western macedonia": "GR",
    "eastern macedonia and thrace": "GR",
    "greek macedonia": "GR",
    "west azerbaijan province": "IR",
    "upper jordan valley": "IL",
    "jordan hill": "GB",  # Dorset
    "kraku lu jordan": "RS",
    "el peru": "GT",  # El Perú-Waka', Petén
    "inner niger delta": "ML",
    "lapis niger": "IT",  # the Roman Forum
    "denmark fjord": "GL",
}

# Reverse mapping: ISO code → list of known name variants (for context text checking)
_ISO_TO_NAMES: dict[str, list[str]] = {}
for _name, _iso in NAME_TO_ISO.items():
    _ISO_TO_NAMES.setdefault(_iso, []).append(_name)


def normalize_country(name: str) -> str:
    """Normalize country name to ISO 2-letter code for comparison.

    Falls back to lowercased name if no mapping found.
    """
    if not name:
        return ""
    lower = name.strip().lower()
    if lower in NAME_TO_ISO:
        return NAME_TO_ISO[lower]
    # Handle compound names like "Chile, Easter Island"
    for part in lower.split(","):
        part = part.strip()
        if part in NAME_TO_ISO:
            return NAME_TO_ISO[part]
    # Already an ISO code (e.g. "tr" from DB) — uppercase for consistent comparison
    if len(lower) == 2 and lower.isalpha():
        return lower.upper()
    return lower


# Country names whose canonical display form differs from what older code,
# third-party APIs, or legacy data tend to emit. Add entries here whenever a
# country is officially renamed — the UI and DB will use the canonical form.
_DISPLAY_CANONICAL: dict[str, str] = {
    "turkey": "Türkiye",
    "türkiye": "Türkiye",
}


def canonicalize_country_display_name(name: str | None) -> str | None:
    """Return the preferred display form of a country name.

    Connectors should route `unified_sites.country` writes through this so new
    data doesn't reintroduce legacy names (e.g. "Turkey" → "Türkiye"). Unknown
    or None inputs are returned unchanged.
    """
    if not name:
        return name
    return _DISPLAY_CANONICAL.get(name.strip().lower(), name)


def country_name_variants(name: str) -> list[str]:
    """Return all known name variants for a country (for text searching).

    E.g. "United States of America" → ["united states", "united states of america", "usa"]
    """
    iso = NAME_TO_ISO.get(name.strip().lower() if name else "")
    if iso:
        return _ISO_TO_NAMES.get(iso, [])
    return [name.strip().lower()] if name else []


# Country (ISO code of NAME_TO_ISO) -> its demonyms: the English nationality adjective(s) and the
# people noun where it differs (Danish/Dane, Spanish/Spaniard), written as proper nouns. The Phase-4
# card rule (scripts/remediation/phase4/verify4.py, V10) holds a card that names a modern
# nationality (pilot 2 published "a Danish hill"); what it holds is this table without the
# ancient-culture adjectives below (MODERN_NATIONALITY_DEMONYMS). Data only, like NAME_TO_ISO; each
# reader implements its own match. Written 2026-09-24 from the card style rule the design calls "the
# existing style rule" (scripts/verify_descriptions.py DEMONYM_MAP, whose modern adjectives it
# keeps) and completed with the standard English demonym of every other country NAME_TO_ISO knows.
# Ethnonyms and historic names (Khmer, Magyar, Persian, Mongol) are not demonyms of a modern country
# and are not listed. A country name that is also its adjective ("New Zealand") is NAME_TO_ISO's
# already.
ISO_TO_DEMONYMS: dict[str, tuple[str, ...]] = {
    # Middle East & Near East
    "EG": ("Egyptian",),
    "IQ": ("Iraqi",),
    "IR": ("Iranian",),
    "SY": ("Syrian",),
    "JO": ("Jordanian",),
    "IL": ("Israeli",),
    "LB": ("Lebanese",),
    "TR": ("Turkish", "Turk"),
    "SA": ("Saudi", "Saudi Arabian"),
    "YE": ("Yemeni",),
    "OM": ("Omani",),
    "AE": ("Emirati",),
    "KW": ("Kuwaiti",),
    "BH": ("Bahraini",),
    "QA": ("Qatari",),
    "PS": ("Palestinian",),
    "CY": ("Cypriot", "Cyprian"),
    # Europe
    "GR": ("Greek", "Hellenic", "Hellene"),
    "IT": ("Italian",),
    "ES": ("Spanish", "Spaniard"),
    "FR": ("French",),
    "PT": ("Portuguese",),
    "GB": ("British", "Briton", "English", "Scottish", "Scots", "Scot", "Welsh", "Northern Irish"),
    "IE": ("Irish",),
    "DE": ("German",),
    "AT": ("Austrian",),
    "CH": ("Swiss",),
    "NL": ("Dutch", "Netherlander"),
    "BE": ("Belgian",),
    "LU": ("Luxembourgish", "Luxembourger"),
    "DK": ("Danish", "Dane"),
    "SE": ("Swedish", "Swede"),
    "NO": ("Norwegian",),
    "FI": ("Finnish", "Finn"),
    "IS": ("Icelandic", "Icelander"),
    "PL": ("Polish", "Pole"),
    "CZ": ("Czech",),
    "SK": ("Slovak", "Slovakian"),
    "HU": ("Hungarian",),
    "RO": ("Romanian",),
    "BG": ("Bulgarian",),
    "RS": ("Serbian", "Serb"),
    "HR": ("Croatian", "Croat"),
    "SI": ("Slovenian", "Slovene"),
    "BA": ("Bosnian", "Herzegovinian"),
    "ME": ("Montenegrin",),
    "MK": ("Macedonian",),
    "AL": ("Albanian",),
    "XK": ("Kosovar", "Kosovan"),
    "MD": ("Moldovan",),
    "UA": ("Ukrainian",),
    "BY": ("Belarusian",),
    "LT": ("Lithuanian",),
    "LV": ("Latvian",),
    "EE": ("Estonian",),
    "MT": ("Maltese",),
    "MC": ("Monégasque", "Monegasque", "Monacan"),
    "AD": ("Andorran",),
    "SM": ("Sammarinese",),
    "VA": ("Vatican",),
    "LI": ("Liechtensteiner",),
    # Asia
    "CN": ("Chinese",),
    "JP": ("Japanese",),
    "KR": ("South Korean", "Korean"),
    "KP": ("North Korean",),
    "TW": ("Taiwanese",),
    "MN": ("Mongolian",),
    "VN": ("Vietnamese",),
    "TH": ("Thai",),
    "MM": ("Burmese",),
    "KH": ("Cambodian",),
    "LA": ("Lao", "Laotian"),
    "MY": ("Malaysian",),
    "SG": ("Singaporean",),
    "ID": ("Indonesian",),
    "PH": ("Filipino", "Filipina", "Philippine"),
    "BN": ("Bruneian",),
    "TL": ("Timorese",),
    # South Asia
    "IN": ("Indian",),
    "PK": ("Pakistani",),
    "BD": ("Bangladeshi",),
    "LK": ("Sri Lankan",),
    "NP": ("Nepali", "Nepalese"),
    "BT": ("Bhutanese",),
    "MV": ("Maldivian",),
    "AF": ("Afghan",),
    # Central Asia
    "KZ": ("Kazakh", "Kazakhstani"),
    "UZ": ("Uzbek", "Uzbekistani"),
    "TM": ("Turkmen",),
    "TJ": ("Tajik", "Tajikistani"),
    "KG": ("Kyrgyz", "Kyrgyzstani"),
    # Russia & Caucasus
    "RU": ("Russian",),
    "GE": ("Georgian",),
    "AM": ("Armenian",),
    "AZ": ("Azerbaijani", "Azeri"),
    # Africa
    "MA": ("Moroccan",),
    "DZ": ("Algerian",),
    "TN": ("Tunisian",),
    "LY": ("Libyan",),
    "SD": ("Sudanese",),
    "SS": ("South Sudanese",),
    "ET": ("Ethiopian",),
    "ER": ("Eritrean",),
    "DJ": ("Djiboutian",),
    "SO": ("Somali",),
    "KE": ("Kenyan",),
    "TZ": ("Tanzanian",),
    "UG": ("Ugandan",),
    "RW": ("Rwandan",),
    "BI": ("Burundian",),
    "CD": ("Congolese",),
    "CG": ("Congolese",),
    "GA": ("Gabonese",),
    "GQ": ("Equatorial Guinean", "Equatoguinean"),
    "CM": ("Cameroonian",),
    "CF": ("Central African",),
    "TD": ("Chadian",),
    "NE": ("Nigerien",),
    "NG": ("Nigerian",),
    "BJ": ("Beninese",),
    "TG": ("Togolese",),
    "GH": ("Ghanaian",),
    "CI": ("Ivorian",),
    "LR": ("Liberian",),
    "SL": ("Sierra Leonean",),
    "GN": ("Guinean",),
    "GW": ("Bissau-Guinean",),
    "SN": ("Senegalese",),
    "GM": ("Gambian",),
    "MR": ("Mauritanian",),
    "ML": ("Malian",),
    "BF": ("Burkinabé", "Burkinabe"),
    "CV": ("Cape Verdean", "Cabo Verdean"),
    "AO": ("Angolan",),
    "ZM": ("Zambian",),
    "ZW": ("Zimbabwean",),
    "MW": ("Malawian",),
    "MZ": ("Mozambican",),
    "BW": ("Motswana", "Batswana", "Botswanan"),
    "NA": ("Namibian",),
    "ZA": ("South African",),
    "LS": ("Basotho", "Mosotho"),
    "SZ": ("Swazi",),
    "MG": ("Malagasy",),
    "MU": ("Mauritian",),
    "SC": ("Seychellois",),
    "KM": ("Comorian", "Comoran"),
    # Americas
    "US": ("American",),
    "CA": ("Canadian",),
    "MX": ("Mexican",),
    "GT": ("Guatemalan",),
    "BZ": ("Belizean",),
    "HN": ("Honduran",),
    "SV": ("Salvadoran", "Salvadorian"),
    "NI": ("Nicaraguan",),
    "CR": ("Costa Rican",),
    "PA": ("Panamanian",),
    "CU": ("Cuban",),
    "JM": ("Jamaican",),
    "HT": ("Haitian",),
    "DO": ("Dominican",),
    "PR": ("Puerto Rican",),
    "BS": ("Bahamian",),
    "TT": ("Trinidadian", "Tobagonian"),
    "BB": ("Barbadian", "Bajan"),
    "CO": ("Colombian",),
    "VE": ("Venezuelan",),
    "EC": ("Ecuadorian",),
    "PE": ("Peruvian",),
    "BO": ("Bolivian",),
    "BR": ("Brazilian",),
    "PY": ("Paraguayan",),
    "UY": ("Uruguayan",),
    "AR": ("Argentine", "Argentinian"),
    "CL": ("Chilean",),
    "GY": ("Guyanese",),
    "SR": ("Surinamese",),
    "GF": ("French Guianese", "Guianese"),
    # Oceania
    "AU": ("Australian",),
    "NZ": ("New Zealander",),
    "PG": ("Papua New Guinean", "Papuan"),
    "FJ": ("Fijian",),
    "SB": ("Solomon Islander",),
    "VU": ("Ni-Vanuatu",),
    "WS": ("Samoan",),
    "TO": ("Tongan",),
    "FM": ("Micronesian",),
    "PW": ("Palauan",),
    "MH": ("Marshallese",),
    "KI": ("I-Kiribati",),
    "NR": ("Nauruan",),
    "TV": ("Tuvaluan",),
    # Territories & Dependencies
    "GL": ("Greenlandic", "Greenlander"),
    "FO": ("Faroese",),
    "GI": ("Gibraltarian",),
    "BM": ("Bermudian",),
    "KY": ("Caymanian",),
    "HK": ("Hongkonger", "Hong Konger"),
    "MO": ("Macanese",),
}

# The Phase-4 card rule splits the demonyms in two (owner decision 2026-09-24: the final design,
# entry [6] of output/remediation/logs/design_texts_images_2026-09-22.json, wins - card_texts, RULES:
# "No country name. ... Cultural adjectives such as Roman, Egyptian or Maya are allowed";
# docs/procedures/PHASE4_CONTRACTS.md section 6).
#
# (a) The adjectives of an ancient culture (and a people noun the table carries, "Hellene"): a card
# may carry one even where the same word is a modern country's demonym ("Greek", "Egyptian",
# "Macedonian"), and V10 never holds one - its plural, its -man noun or a demonym inside it
# ("Romano-British") neither. Each entry is an ancient culture, following the design's line: the
# design's three examples, the owner's list of 2026-09-24, and - chosen here - the ancient cultures
# whose word the table carries (Hellenic, Hellene, Macedonian: ancient Greece and Macedon), the
# culture of Roman Britain and of Roman Gaul, two spellings (Incan, Nasca, Nabatean) and the ancient
# cultures of the catalogue's regions the owner's list does not name. The rule cannot tell a culture
# from a nationality in the same word ("the first Greek site to be inscribed" means Greece): what
# the card says is the reviewer's CARD line and the audit's to judge.
ANCIENT_CULTURE_ADJECTIVES: frozenset[str] = frozenset({
    # the design's examples and the owner's list
    "Roman", "Greek", "Egyptian", "Maya", "Mayan", "Inca", "Aztec", "Olmec", "Toltec", "Zapotec",
    "Mixtec", "Moche", "Nazca", "Etruscan", "Celtic", "Gallic", "Iberian", "Phoenician", "Punic",
    "Carthaginian", "Persian", "Assyrian", "Babylonian", "Sumerian", "Akkadian", "Hittite",
    "Minoan", "Mycenaean", "Nabataean", "Thracian", "Dacian", "Scythian", "Norse", "Viking",
    "Anglo-Saxon", "Pictish", "Khmer", "Nubian", "Kushite", "Byzantine", "Hellenistic",
    "Mesopotamian",
    # ancient Greece and Macedon, whose words the table carries under GR and MK
    "Hellenic", "Hellene", "Macedonian",
    # Roman Britain and Roman Gaul ("Romano-British" carries the modern "British")
    "Romano-British", "Gallo-Roman",
    # other spellings of the owner's
    "Incan", "Nasca", "Nabatean",
    # Europe and the Mediterranean
    "Italic", "Samnite", "Cycladic", "Nuragic", "Illyrian", "Celtiberian", "Sarmatian",
    # Anatolia, the Near East and Iran
    "Phrygian", "Lydian", "Lycian", "Urartian", "Achaemenid", "Parthian", "Sasanian", "Elamite",
    "Canaanite",
    # Africa and South Asia
    "Meroitic", "Aksumite", "Harappan",
    # the Americas before 1500
    "Chavín", "Tiwanaku", "Wari", "Chimú", "Puebloan",
})  # fmt: skip

# (b) The modern-nationality demonyms V10 holds: every demonym of ISO_TO_DEMONYMS that is no word of
# (a) - derived, never written twice, so a word of (a) is never held whatever the table carries.
MODERN_NATIONALITY_DEMONYMS: frozenset[str] = frozenset(
    demonym
    for demonyms in ISO_TO_DEMONYMS.values()
    for demonym in demonyms
    if demonym not in ANCIENT_CULTURE_ADJECTIVES
)


def download_country_boundaries():
    """Download Natural Earth country boundaries."""
    import io
    import urllib.request
    import zipfile

    # Natural Earth 110m cultural vectors (countries)
    # Small file (~800KB) good enough for most lookups
    url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading country boundaries from Natural Earth...")
    logger.info(f"URL: {url}")

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()

        logger.info(f"Downloaded {len(data) / 1024:.1f} KB")

        # Extract GeoJSON from shapefile in zip
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Look for the .shp file and convert to GeoJSON
            shp_name = None
            for name in zf.namelist():
                if name.endswith(".shp"):
                    shp_name = name
                    break

            if shp_name:
                # We need to use a different approach - download GeoJSON directly
                pass

    except Exception as e:
        logger.warning(f"Failed to download shapefile: {e}")

    # Try GeoJSON endpoint instead
    geojson_url = (
        "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
    )

    logger.info(f"Trying GeoJSON endpoint: {geojson_url}")

    try:
        with urllib.request.urlopen(geojson_url, timeout=120) as response:
            data = response.read()

        logger.info(f"Downloaded {len(data) / 1024 / 1024:.1f} MB")

        # Validate JSON
        json.loads(data)

        # Save to file
        with open(COUNTRIES_FILE, "wb") as f:
            f.write(data)

        logger.info(f"Saved to {COUNTRIES_FILE}")
        return True

    except Exception as e:
        logger.error(f"Failed to download GeoJSON: {e}")
        return False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Country lookup utility")
    parser.add_argument("--download", action="store_true", help="Download country boundaries data")
    parser.add_argument("--test", action="store_true", help="Test lookup functionality")
    parser.add_argument("--lat", type=float, help="Latitude to lookup")
    parser.add_argument("--lon", type=float, help="Longitude to lookup")

    args = parser.parse_args()

    if args.download:
        success = download_country_boundaries()
        if success:
            print("Download successful!")
        else:
            print("Download failed!")
            exit(1)

    elif args.lat is not None and args.lon is not None:
        country = lookup_country(args.lat, args.lon)
        if country:
            print(f"Country: {country}")
        else:
            print("Country not found")

    elif args.test:
        # Test some known locations
        test_cases = [
            (41.9028, 12.4964, "Italy"),  # Rome
            (51.5074, -0.1278, "United Kingdom"),  # London
            (40.7128, -74.0060, "United States of America"),  # New York
            (35.6762, 139.6503, "Japan"),  # Tokyo
            (31.2304, 121.4737, "China"),  # Shanghai
            (-33.8688, 151.2093, "Australia"),  # Sydney
        ]

        print("Testing country lookup...")
        for lat, lon, expected in test_cases:
            result = lookup_country(lat, lon)
            status = "OK" if result and expected.lower() in result.lower() else "FAIL"
            print(f"  ({lat}, {lon}): {result} [{status}]")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
