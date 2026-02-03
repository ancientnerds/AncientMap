"""
Query Parser for Natural Language to Structured Filters.

Parses user queries to extract:
- Time periods (e.g., "Roman Empire", "2000 BC", "Bronze Age")
- Locations (e.g., "Europe", "Greece", "Mediterranean")
- Site types (e.g., "churches", "temples", "tombs")
- Keywords for semantic search
- Actions (e.g., "highlight", "show", "find")
"""

import re
from dataclasses import dataclass, field


@dataclass
class QueryIntent:
    """Structured representation of a parsed query."""
    original_query: str
    search_terms: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    wants_highlight: bool = False
    site_types: list[str] = field(default_factory=list)
    period_name: str | None = None
    region_name: str | None = None
    source_ids: list[str] | None = None  # Specific source collections to search
    feature_type: str | None = None       # Geographic feature for proximity search
    feature_radius_km: float = 50.0          # Radius for proximity search


class QueryParser:
    """
    Parse natural language queries to extract structured filters.

    Example:
        parser = QueryParser()
        intent = parser.parse("Find Roman temples in Greece")
        # intent.filters = {"period_start_gte": -27, "period_end_lte": 476, ...}
        # intent.site_types = ["temple"]
        # intent.region_name = "Greece"
    """

    # Historical period mappings (year ranges)
    PERIOD_KEYWORDS = {
        # Major empires/civilizations
        "roman empire": (-27, 476, "Roman Empire"),
        "roman": (-753, 476, "Roman"),
        "greek": (-800, -31, "Greek"),
        "ancient greece": (-800, -31, "Ancient Greece"),
        "hellenistic": (-323, -31, "Hellenistic"),
        "byzantine": (330, 1453, "Byzantine"),
        "ottoman": (1299, 1922, "Ottoman"),
        "persian": (-550, -330, "Persian Empire"),
        "egyptian": (-3100, -30, "Ancient Egypt"),
        "ancient egypt": (-3100, -30, "Ancient Egypt"),
        "mesopotamian": (-3500, -539, "Mesopotamian"),
        "sumerian": (-4500, -1900, "Sumerian"),
        "babylonian": (-1894, -539, "Babylonian"),
        "assyrian": (-2500, -609, "Assyrian"),
        "phoenician": (-1500, -300, "Phoenician"),
        "carthaginian": (-814, -146, "Carthaginian"),
        "etruscan": (-900, -27, "Etruscan"),
        "celtic": (-800, 400, "Celtic"),
        "viking": (793, 1066, "Viking"),
        "medieval": (500, 1500, "Medieval"),
        "crusader": (1095, 1291, "Crusader"),

        # Archaeological periods
        "paleolithic": (-3000000, -10000, "Paleolithic"),
        "mesolithic": (-10000, -5000, "Mesolithic"),
        "neolithic": (-10000, -3300, "Neolithic"),
        "chalcolithic": (-4500, -3300, "Chalcolithic"),
        "bronze age": (-3300, -1200, "Bronze Age"),
        "iron age": (-1200, -500, "Iron Age"),
        "classical": (-500, 500, "Classical"),
        "antiquity": (-3000, 500, "Antiquity"),
        "prehistoric": (-3000000, -3000, "Prehistoric"),

        # Regional periods
        "minoan": (-3000, -1100, "Minoan"),
        "mycenaean": (-1600, -1100, "Mycenaean"),
        "archaic": (-800, -480, "Archaic Greek"),
    }

    # Region bounding boxes (min_lat, max_lat, min_lon, max_lon)
    REGION_BOUNDS = {
        "europe": (35, 71, -10, 40, "Europe"),
        "western europe": (36, 60, -10, 15, "Western Europe"),
        "eastern europe": (40, 60, 15, 40, "Eastern Europe"),
        "southern europe": (35, 47, -10, 30, "Southern Europe"),
        "northern europe": (54, 71, -10, 30, "Northern Europe"),
        "mediterranean": (30, 46, -6, 36, "Mediterranean"),
        "middle east": (12, 42, 26, 63, "Middle East"),
        "near east": (28, 42, 26, 50, "Near East"),
        "levant": (29, 37, 34, 42, "Levant"),
        "anatolia": (36, 42, 26, 45, "Anatolia"),
        "asia minor": (36, 42, 26, 45, "Asia Minor"),
        "north africa": (15, 37, -17, 35, "North Africa"),
        "egypt": (22, 32, 25, 35, "Egypt"),
        "mesopotamia": (29, 38, 38, 49, "Mesopotamia"),
        "persia": (25, 40, 44, 63, "Persia"),
        "iran": (25, 40, 44, 63, "Iran"),
        "greece": (35, 42, 19, 30, "Greece"),
        "italy": (36, 47, 6, 19, "Italy"),
        "spain": (36, 44, -10, 4, "Spain"),
        "iberia": (36, 44, -10, 4, "Iberian Peninsula"),
        "france": (42, 51, -5, 8, "France"),
        "gaul": (42, 51, -5, 8, "Gaul"),
        "britain": (50, 59, -8, 2, "Britain"),
        "british isles": (50, 61, -11, 2, "British Isles"),
        "germany": (47, 55, 6, 15, "Germany"),
        "balkans": (39, 47, 13, 30, "Balkans"),
        "turkey": (36, 42, 26, 45, "Turkey"),
        "israel": (29, 34, 34, 36, "Israel"),
        "palestine": (31, 33, 34, 36, "Palestine"),
        "syria": (32, 37, 35, 42, "Syria"),
        "iraq": (29, 38, 38, 49, "Iraq"),
        "jordan": (29, 34, 34, 39, "Jordan"),
        "lebanon": (33, 35, 35, 37, "Lebanon"),
        "cyprus": (34, 36, 32, 35, "Cyprus"),
        "crete": (34, 36, 23, 27, "Crete"),
        "sicily": (36, 39, 12, 16, "Sicily"),
        "sardinia": (38, 42, 8, 10, "Sardinia"),
        "africa": (-35, 37, -17, 52, "Africa"),
        "asia": (0, 55, 25, 180, "Asia"),
        "central asia": (35, 55, 50, 90, "Central Asia"),
        "india": (8, 35, 68, 97, "India"),
        "china": (18, 54, 73, 135, "China"),
        "americas": (-56, 72, -170, -30, "Americas"),
        "north america": (15, 72, -170, -50, "North America"),
        "south america": (-56, 15, -82, -30, "South America"),
        "mesoamerica": (14, 24, -118, -83, "Mesoamerica"),
    }

    # Site type mappings (query term -> database values)
    SITE_TYPE_KEYWORDS = {
        "church": ["church", "chapel", "basilica", "cathedral"],
        "churches": ["church", "chapel", "basilica", "cathedral"],
        "temple": ["temple", "sanctuary", "shrine"],
        "temples": ["temple", "sanctuary", "shrine"],
        "tomb": ["tomb", "burial", "necropolis", "cemetery", "grave", "mausoleum"],
        "tombs": ["tomb", "burial", "necropolis", "cemetery", "grave", "mausoleum"],
        "burial": ["tomb", "burial", "necropolis", "cemetery", "grave"],
        "cemetery": ["cemetery", "necropolis", "burial"],
        "fort": ["fort", "fortress", "fortification", "castle", "citadel"],
        "fortress": ["fort", "fortress", "fortification", "castle", "citadel"],
        "castle": ["castle", "fortress", "fort"],
        "wall": ["wall", "fortification", "defensive"],
        "city": ["city", "settlement", "town", "urban"],
        "settlement": ["settlement", "village", "town", "habitation"],
        "villa": ["villa", "estate", "rural"],
        "road": ["road", "via", "highway", "route"],
        "bridge": ["bridge", "viaduct", "aqueduct"],
        "aqueduct": ["aqueduct", "water"],
        "bath": ["bath", "thermae", "spa"],
        "theater": ["theater", "theatre", "amphitheater", "odeon"],
        "amphitheater": ["amphitheater", "amphitheatre", "arena"],
        "stadium": ["stadium", "hippodrome", "circus"],
        "palace": ["palace", "royal"],
        "monument": ["monument", "memorial", "stele"],
        "inscription": ["inscription", "epigraph"],
        "mosaic": ["mosaic"],
        "statue": ["statue", "sculpture"],
        "pyramid": ["pyramid"],
        "megalith": ["megalith", "megalithic", "dolmen", "menhir", "stone circle"],
        "stone circle": ["stone circle", "henge", "megalithic"],
        "dolmen": ["dolmen", "megalith"],
        "menhir": ["menhir", "standing stone"],
        "cave": ["cave", "grotto", "rock shelter"],
        "rock art": ["rock art", "petroglyph", "pictograph"],
        "mine": ["mine", "quarry", "mining"],
        "shipwreck": ["shipwreck", "wreck"],
        "harbor": ["harbor", "harbour", "port"],
        "lighthouse": ["lighthouse", "pharos"],
        "monastery": ["monastery", "convent", "abbey"],
        "mosque": ["mosque", "masjid"],
        "synagogue": ["synagogue"],
        "bones": ["burial", "tomb", "cemetery", "skeleton", "ossuary"],
        "skeleton": ["burial", "tomb", "cemetery", "skeleton"],
        "artifacts": ["settlement", "archaeological_site"],
        "ruins": ["ruin", "archaeological_site"],
        "archaeological": ["archaeological_site", "ancient"],
    }

    # Action keywords that indicate highlighting
    HIGHLIGHT_KEYWORDS = [
        "highlight", "show", "display", "mark", "indicate",
        "point out", "locate", "find", "where", "map"
    ]

    # Source collection patterns (query terms -> source IDs)
    SOURCE_PATTERNS = {
        "ancient nerds": ["ancient_nerds"],
        "ancientnerds": ["ancient_nerds"],
        "primary source": ["ancient_nerds"],
        "main database": ["ancient_nerds"],
        "megalithic portal": ["megalithic_portal"],
        "megalithic": ["megalithic_portal"],
        "unesco": ["unesco"],
        "world heritage": ["unesco"],
        "wikidata": ["wikidata"],
        "wikipedia": ["wikidata"],
        "pleiades": ["pleiades"],
        "roman places": ["pleiades", "dare"],
        "inscriptions": ["inscriptions_edh"],
        "latin inscriptions": ["inscriptions_edh"],
        "edh": ["inscriptions_edh"],
        "osm": ["osm_historic"],
        "openstreetmap": ["osm_historic"],
        "ireland": ["ireland_nms"],
        "irish sites": ["ireland_nms"],
        "historic england": ["historic_england"],
        "england": ["historic_england"],
        "topostext": ["topostext"],
        "dare": ["dare"],
        "arachne": ["arachne"],
        "shipwreck": ["shipwrecks_oxrep"],
        "shipwrecks": ["shipwrecks_oxrep"],
        "ship wreck": ["shipwrecks_oxrep"],
        "rock art": ["rock_art"],
        "petroglyphs": ["rock_art"],
        "sacred sites": ["sacred_sites"],
        "sacred places": ["sacred_sites"],
        "open context": ["open_context"],
        "all sources": ["all"],
        "all databases": ["all"],
        "everywhere": ["all"],
    }

    # Geographic feature patterns for proximity searches
    FEATURE_PATTERNS = {
        "volcano": "volcano",
        "volcanic": "volcano",
        "volcanos": "volcano",
        "volcanoes": "volcano",
        "eruption": "volcano",
        "volcanic eruption": "volcano",
        "near volcano": "volcano",
        "near volcanos": "volcano",
        "near volcanoes": "volcano",
        "impact crater": "impact_crater",
        "impact craters": "impact_crater",
        "crater": "impact_crater",
        "craters": "impact_crater",
        "meteorite": "impact_crater",
        "meteorite impact": "impact_crater",
        "asteroid impact": "impact_crater",
        "meteor": "impact_crater",
        "near crater": "impact_crater",
        "near craters": "impact_crater",
    }

    def __init__(self):
        # Compile regex patterns for efficiency
        self._year_pattern = re.compile(
            r'(\d{1,5})\s*(bc|bce|ad|ce|b\.c\.|a\.d\.)',
            re.IGNORECASE
        )
        self._year_range_pattern = re.compile(
            r'(\d{1,5})\s*(?:to|-)\s*(\d{1,5})\s*(bc|bce|ad|ce)?',
            re.IGNORECASE
        )
        self._older_than_pattern = re.compile(
            r'older\s+than\s+(\d{1,5})\s*(bc|bce|ad|ce|years?)?',
            re.IGNORECASE
        )
        self._newer_than_pattern = re.compile(
            r'(?:newer|younger|after)\s+(?:than\s+)?(\d{1,5})\s*(bc|bce|ad|ce)?',
            re.IGNORECASE
        )

    def parse(self, query: str) -> QueryIntent:
        """
        Parse a natural language query into structured filters.

        Args:
            query: Natural language query string

        Returns:
            QueryIntent with extracted filters and search terms
        """
        query_lower = query.lower()

        intent = QueryIntent(
            original_query=query,
            search_terms=[],
            filters={},
            wants_highlight=False
        )

        # Check for highlight intent
        for keyword in self.HIGHLIGHT_KEYWORDS:
            if keyword in query_lower:
                intent.wants_highlight = True
                break

        # Extract source collections to search
        self._extract_sources(query_lower, intent)

        # Extract geographic feature for proximity search
        self._extract_features(query_lower, intent)

        # Extract time period from named periods
        self._extract_named_period(query_lower, intent)

        # Extract explicit year constraints
        self._extract_year_constraints(query_lower, intent)

        # Extract region/location
        self._extract_region(query_lower, intent)

        # Extract site types
        self._extract_site_types(query_lower, intent)

        # Extract remaining keywords for semantic search
        intent.search_terms = self._extract_search_keywords(query, intent)

        return intent

    def _extract_sources(self, query_lower: str, intent: QueryIntent):
        """Extract specific source collections to search."""
        for pattern, source_ids in self.SOURCE_PATTERNS.items():
            if pattern in query_lower:
                intent.source_ids = source_ids
                break

    def _extract_features(self, query_lower: str, intent: QueryIntent):
        """Extract geographic feature types for proximity searches."""
        # Check for "near" + feature patterns first (more specific)
        for pattern, feature_type in self.FEATURE_PATTERNS.items():
            if pattern in query_lower:
                intent.feature_type = feature_type
                # Check for radius specification (e.g., "within 100km of volcano")
                radius_match = re.search(r'within\s+(\d+)\s*(?:km|kilometers?|miles?)', query_lower)
                if radius_match:
                    radius = float(radius_match.group(1))
                    # Convert miles to km if needed
                    if 'mile' in query_lower:
                        radius *= 1.60934
                    intent.feature_radius_km = radius
                break

    def _extract_named_period(self, query_lower: str, intent: QueryIntent):
        """Extract named historical periods."""
        for keyword, (start, end, name) in self.PERIOD_KEYWORDS.items():
            if keyword in query_lower:
                # Only set if not already set (first match wins for specificity)
                if "period_start_gte" not in intent.filters:
                    intent.filters["period_start_gte"] = start
                    intent.filters["period_end_lte"] = end
                    intent.period_name = name
                break

    def _extract_year_constraints(self, query_lower: str, intent: QueryIntent):
        """Extract explicit year mentions and constraints."""
        # Check for "older than X BC" pattern
        older_match = self._older_than_pattern.search(query_lower)
        if older_match:
            year = int(older_match.group(1))
            era = older_match.group(2)
            if era and era.lower() in ('bc', 'bce', 'b.c.'):
                year = -year
            elif era and 'year' in era.lower():
                # "older than 2000 years" - relative to now
                year = 2024 - year
            intent.filters["period_start_lte"] = year

        # Check for "newer than" / "after" pattern
        newer_match = self._newer_than_pattern.search(query_lower)
        if newer_match:
            year = int(newer_match.group(1))
            era = newer_match.group(2)
            if era and era.lower() in ('bc', 'bce', 'b.c.'):
                year = -year
            intent.filters["period_start_gte"] = year

        # Check for explicit year mentions (e.g., "2000 BC")
        year_matches = self._year_pattern.findall(query_lower)
        for year_str, era in year_matches:
            year = int(year_str)
            if era.lower() in ('bc', 'bce', 'b.c.'):
                year = -year
            # If we don't have constraints yet, use this as a reference point
            if "period_start_lte" not in intent.filters and "period_start_gte" not in intent.filters:
                # Create a range around this date (±500 years)
                intent.filters["period_start_gte"] = year - 500
                intent.filters["period_end_lte"] = year + 500

    def _extract_region(self, query_lower: str, intent: QueryIntent):
        """Extract geographic region from query."""
        for region, bounds in self.REGION_BOUNDS.items():
            if region in query_lower:
                min_lat, max_lat, min_lon, max_lon, name = bounds
                intent.filters["min_lat"] = min_lat
                intent.filters["max_lat"] = max_lat
                intent.filters["min_lon"] = min_lon
                intent.filters["max_lon"] = max_lon
                intent.region_name = name
                break

        # Also check for country names that might be in the database
        # These will be used as text filters
        country_keywords = [
            "greece", "italy", "spain", "france", "germany", "turkey",
            "egypt", "israel", "jordan", "syria", "iraq", "iran",
            "britain", "england", "scotland", "wales", "ireland",
            "portugal", "morocco", "tunisia", "libya", "algeria",
            "austria", "switzerland", "belgium", "netherlands",
            "poland", "czech", "hungary", "romania", "bulgaria",
            "croatia", "slovenia", "serbia", "albania", "macedonia"
        ]
        for country in country_keywords:
            if country in query_lower:
                intent.filters["country_contains"] = country.title()
                break

    def _extract_site_types(self, query_lower: str, intent: QueryIntent):
        """Extract site type filters from query."""
        found_types = set()
        for keyword, db_types in self.SITE_TYPE_KEYWORDS.items():
            if keyword in query_lower:
                found_types.update(db_types)

        if found_types:
            intent.site_types = list(found_types)
            intent.filters["site_type_in"] = list(found_types)

    def _extract_search_keywords(self, query: str, intent: QueryIntent) -> list[str]:
        """Extract remaining keywords for semantic search."""
        # Remove stopwords and already-parsed terms
        stopwords = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
            "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did",
            "and", "or", "but", "if", "then", "than",
            "any", "some", "all", "each", "every",
            "can", "could", "would", "should", "may", "might",
            "there", "here", "where", "when", "what", "which", "who",
            "this", "that", "these", "those",
            "i", "you", "we", "they", "he", "she", "it",
            "me", "him", "her", "us", "them",
            "my", "your", "our", "their", "his", "its",
            "yes", "no", "please", "thank", "thanks"
        }

        # Also remove parsed keywords
        parsed_keywords = set()
        parsed_keywords.update(self.HIGHLIGHT_KEYWORDS)
        for kw in self.PERIOD_KEYWORDS.keys():
            parsed_keywords.update(kw.split())
        for kw in self.REGION_BOUNDS.keys():
            parsed_keywords.update(kw.split())
        for kw in self.SITE_TYPE_KEYWORDS.keys():
            parsed_keywords.add(kw)

        # Tokenize and filter
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [
            w for w in words
            if w not in stopwords
            and w not in parsed_keywords
            and len(w) > 2
            and not w.isdigit()
        ]

        return keywords


# Convenience function for quick parsing
def parse_query(query: str) -> QueryIntent:
    """Parse a query string into structured intent."""
    parser = QueryParser()
    return parser.parse(query)
