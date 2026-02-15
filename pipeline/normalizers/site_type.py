"""
Site type normalization — single source of truth.

Canonical site_type values are the keys of CATEGORY_COLORS in
ancient-nerds-map/src/constants/colors.ts.  This module builds a
case-insensitive + underscore/space-insensitive lookup so that
'Rock_Art', 'ROCK ART', 'rock art' all resolve to 'Rock art'.

Synonyms (e.g. 'ruins' → 'ruin', 'mausoleum' → 'tomb') are also
mapped here so connectors don't need per-source fixups.
"""

# ---------------------------------------------------------------------------
# Canonical site types — mirrors CATEGORY_COLORS keys exactly.
# When you add a category to colors.ts, add it here too.
# ---------------------------------------------------------------------------
CANONICAL_TYPES: list[str] = [
    # Settlements
    "city", "town", "village", "settlement", "urban", "villa",
    "City/town/settlement", "Residence/villa/farmhouse",
    "City/town/settlement, Pyramid complex",
    # Fortifications
    "castle", "citadel", "fort", "fortress", "military", "wall", "gate",
    "Fortress/citadel", "Castle/palace", "Fortress",
    "Gate/archway/bridge", "Wall", "Fortification",
    # Religious
    "church", "mosque", "temple", "monastery", "sacred_site", "sanctuary",
    "religious", "Temple complex", "Church/cathedral", "Minaret/tower",
    "Stone cross",
    # Burial & Death
    "cemetery", "necropolis", "tomb", "burial", "funerary",
    "Necropolis/tombs complex", "Cemetery", "Barrow", "Mound/tumulus",
    "Cairn", "Elongated skulls",
    # Megalithic
    "megalithic", "Megalithic stones", "Megalithic structures",
    "Megalithic statues", "Megalithic walls", "Stone circle", "Dolmen",
    "Standing stone", "Henge", "Timber circle", "Polygonal masonry",
    "Megalithic",
    # Rock & Cave
    "cave", "Cave Structures", "Rock relief/carving", "Rock art",
    "Petroglyphs", "Sculptured stone", "Cave Structures, Rock art",
    "Geoglyphs",
    # Infrastructure
    "road", "bridge", "mine", "quarry", "infrastructure",
    "Road/avenue/trackway", "Reservoir/aqueduct/canal", "Mine/quarry",
    "Earthwork", "Well",
    # Water & Ports
    "aqueduct", "bath", "harbor", "port",
    "Underwater structures", "Bath", "Shipwreck",
    # Monuments
    "monument", "memorial", "stadium", "theater", "theatre", "Theatre",
    "forum", "palace", "Pyramid complex", "Museum", "Amphitheatre",
    "scheduled_monument", "heritage_site", "archaeological_site", "Monument",
    # Other
    "site", "ruin", "inscription", "natural_feature", "impact_crater",
    "Geological interest", "Magnetic anomaly", "unknown", "Unknown",
]

# ---------------------------------------------------------------------------
# Build case+underscore-insensitive lookup → canonical form
# ---------------------------------------------------------------------------
_LOOKUP: dict[str, str] = {}

for _canonical in CANONICAL_TYPES:
    _key = _canonical.lower().replace("_", " ")
    # First entry wins — lowercase forms appear first in the list, so
    # 'monument' beats 'Monument', 'theatre' beats 'Theatre', etc.
    if _key not in _LOOKUP:
        _LOOKUP[_key] = _canonical
    # Also index the underscore variant
    _key_us = _canonical.lower().replace(" ", "_")
    if _key_us != _key and _key_us not in _LOOKUP:
        _LOOKUP[_key_us] = _canonical

# ---------------------------------------------------------------------------
# Synonyms — source-specific names that should map to a canonical type.
# Only add here when the source name is genuinely a different word for the
# same thing.  Do NOT merge distinct types (castle ≠ fort ≠ fortress).
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, str] = {
    "ruins": "ruin",
    "tumulus": "Mound/tumulus",
    "barrow": "Barrow",
    "mausoleum": "tomb",
    "catacomb": "tomb",
    "menhir": "Standing stone",
    "stone_circle": "Stone circle",
    "megalith": "megalithic",
    "megalithic_temple": "Megalithic structures",
    "megalithic_structure": "Megalithic structures",
    "stone_monument": "monument",
    "hillfort": "fort",
    "oppidum": "fort",
    "shrine": "sanctuary",
    "colony": "settlement",
    "amphitheater": "Amphitheatre",
    "amphitheatre": "Amphitheatre",
    "hippodrome": "stadium",
    "circus": "stadium",
    "baths": "bath",
    "thermae": "bath",
    "agora": "forum",
    "petroglyph": "Petroglyphs",
    "pictograph": "Rock art",
    "rock_art": "Rock art",
    "standing_stone": "Standing stone",
    "harbour": "harbor",
    "statue": "monument",
}

# Normalize synonym keys the same way
_SYNONYM_LOOKUP: dict[str, str] = {}
for _syn_key, _syn_val in _SYNONYMS.items():
    _SYNONYM_LOOKUP[_syn_key.lower().replace("_", " ")] = _syn_val
    _us = _syn_key.lower().replace(" ", "_")
    if _us != _syn_key.lower().replace("_", " "):
        _SYNONYM_LOOKUP[_us] = _syn_val


def normalize_site_type(site_type: str | None) -> str:
    """Normalize a site type string to its canonical form.

    Resolution order:
    1. Exact canonical match (case+underscore insensitive)
    2. Synonym match → canonical form
    3. Pass-through (strip whitespace only)
    """
    if not site_type or not site_type.strip():
        return "unknown"

    cleaned = site_type.strip()
    key = cleaned.lower().replace("_", " ")

    # Direct canonical match
    if key in _LOOKUP:
        return _LOOKUP[key]

    # Synonym match
    if key in _SYNONYM_LOOKUP:
        return _SYNONYM_LOOKUP[key]

    # Also try underscore variant for synonyms
    key_us = cleaned.lower().replace(" ", "_")
    if key_us in _SYNONYM_LOOKUP:
        return _SYNONYM_LOOKUP[key_us]

    # Unknown type — pass through as-is (don't title-case, don't guess)
    return cleaned
