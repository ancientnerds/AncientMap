"""
Site type normalization utilities.
"""

from typing import Optional


# Mapping from various raw site types to normalized categories
SITE_TYPE_MAPPING = {
    # Archaeological sites
    "archaeological_site": "Archaeological Site",
    "archaeological site": "Archaeological Site",
    "ruin": "Ruin",
    "ruins": "Ruin",

    # Tombs and burial sites
    "tomb": "Tomb",
    "tumulus": "Tomb",
    "barrow": "Tomb",
    "burial": "Tomb",
    "necropolis": "Tomb",
    "mausoleum": "Tomb",
    "catacomb": "Tomb",

    # Megalithic
    "dolmen": "Megalithic",
    "menhir": "Megalithic",
    "stone_circle": "Megalithic",
    "megalith": "Megalithic",
    "standing_stone": "Megalithic",

    # Fortifications
    "fort": "Fortification",
    "hillfort": "Fortification",
    "castle": "Fortification",
    "fortress": "Fortification",
    "citadel": "Fortification",
    "oppidum": "Fortification",

    # Religious
    "temple": "Temple",
    "sanctuary": "Temple",
    "shrine": "Temple",

    # Settlements
    "settlement": "Settlement",
    "city": "Settlement",
    "town": "Settlement",
    "village": "Settlement",
    "colony": "Settlement",

    # Entertainment
    "amphitheatre": "Amphitheatre",
    "amphitheater": "Amphitheatre",
    "theatre": "Theatre",
    "theater": "Theatre",
    "stadium": "Stadium",
    "hippodrome": "Stadium",
    "circus": "Stadium",

    # Infrastructure
    "aqueduct": "Infrastructure",
    "road": "Infrastructure",
    "bridge": "Infrastructure",
    "bath": "Infrastructure",
    "baths": "Infrastructure",
    "thermae": "Infrastructure",
    "forum": "Infrastructure",
    "agora": "Infrastructure",

    # Art
    "rock_art": "Rock Art",
    "petroglyph": "Rock Art",
    "pictograph": "Rock Art",

    # Natural events
    "volcanic_eruption": "Volcanic Event",
    "volcano": "Volcanic Event",
    "earthquake": "Earthquake",
    "tsunami": "Tsunami",
    "impact_crater": "Impact Crater",

    # Maritime
    "shipwreck": "Shipwreck",
    "port": "Port",
    "harbor": "Port",
    "harbour": "Port",

    # Inscriptions
    "inscription": "Inscription",

    # Other
    "monument": "Monument",
    "statue": "Monument",
}


def normalize_site_type(site_type: Optional[str]) -> str:
    """Normalize site type to a canonical category.

    Args:
        site_type: Raw site type string from source data

    Returns:
        Normalized site type category
    """
    if not site_type:
        return "Unknown"

    # Clean and lowercase for matching
    cleaned = site_type.lower().strip().replace(" ", "_")

    # Look up in mapping
    if cleaned in SITE_TYPE_MAPPING:
        return SITE_TYPE_MAPPING[cleaned]

    # Try without underscores
    no_underscore = cleaned.replace("_", " ")
    if no_underscore in SITE_TYPE_MAPPING:
        return SITE_TYPE_MAPPING[no_underscore]

    # Return title-cased original if no mapping found
    return site_type.replace("_", " ").title()
