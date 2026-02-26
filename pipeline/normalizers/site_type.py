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
    "City", "Town", "Village", "Settlement", "Urban", "Villa",
    "City/town/settlement", "Residence/villa/farmhouse",
    "City/town/settlement, Pyramid complex",
    # Fortifications
    "Castle", "Citadel", "Fort", "Fortress", "Military", "Wall", "Gate",
    "Fortress/citadel", "Castle/palace",
    "Gate/archway/bridge", "Fortification",
    # Religious
    "Church", "Mosque", "Temple", "Monastery", "Sacred site", "Sanctuary",
    "Religious", "Temple complex", "Church/cathedral", "Minaret/tower",
    "Stone cross",
    # Burial & Death
    "Cemetery", "Necropolis", "Tomb", "Burial", "Funerary",
    "Necropolis/tombs complex", "Barrow", "Mound/tumulus",
    "Cairn", "Elongated skulls",
    # Megalithic
    "Megalithic", "Megalithic stones", "Megalithic structures",
    "Megalithic statues", "Megalithic walls", "Stone circle", "Dolmen",
    "Standing stone", "Henge", "Timber circle", "Polygonal masonry",
    # Rock & Cave
    "Cave", "Cave Structures", "Rock relief/carving", "Rock art",
    "Petroglyphs", "Sculptured stone", "Cave Structures, Rock art",
    "Geoglyphs",
    # Infrastructure
    "Road", "Bridge", "Mine", "Quarry", "Infrastructure",
    "Road/avenue/trackway", "Reservoir/aqueduct/canal", "Mine/quarry",
    "Earthwork", "Well",
    # Water & Ports
    "Aqueduct", "Bath", "Harbor", "Port",
    "Underwater structures", "Shipwreck",
    # Monuments
    "Monument", "Memorial", "Stadium", "Theater", "Theatre",
    "Forum", "Palace", "Pyramid complex", "Museum", "Amphitheatre",
    "Scheduled monument", "Heritage site", "Archaeological site",
    # Other
    "Site", "Ruin", "Inscription", "Natural feature", "Impact crater",
    "Geological interest", "Magnetic anomaly", "Unknown",
]

# ---------------------------------------------------------------------------
# Build case+underscore-insensitive lookup → canonical form
# ---------------------------------------------------------------------------
_LOOKUP: dict[str, str] = {}

for _canonical in CANONICAL_TYPES:
    _key = _canonical.lower().replace("_", " ")
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
    "ruins": "Ruin",
    "tumulus": "Mound/tumulus",
    "barrow": "Barrow",
    "mausoleum": "Tomb",
    "catacomb": "Tomb",
    "menhir": "Standing stone",
    "stone_circle": "Stone circle",
    "megalith": "Megalithic",
    "megalithic_temple": "Megalithic structures",
    "megalithic_structure": "Megalithic structures",
    "stone_monument": "Monument",
    "hillfort": "Fort",
    "oppidum": "Fort",
    "shrine": "Sanctuary",
    "colony": "Settlement",
    "amphitheater": "Amphitheatre",
    "amphitheatre": "Amphitheatre",
    "hippodrome": "Stadium",
    "circus": "Stadium",
    "baths": "Bath",
    "thermae": "Bath",
    "agora": "Forum",
    "petroglyph": "Petroglyphs",
    "pictograph": "Rock art",
    "rock_art": "Rock art",
    "standing_stone": "Standing stone",
    "harbour": "Harbor",
    "statue": "Monument",
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
        return "Unknown"

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
