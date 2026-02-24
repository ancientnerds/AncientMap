"""Empire metadata — single source of truth for all empire display data.

No heavy dependencies (no shapely/geojson) so this can be imported anywhere,
including inside the API Docker container.
"""

EMPIRE_METADATA: dict[str, dict] = {
    # Ancient Near East (7)
    'egyptian': {'name': 'Egyptian Kingdom', 'region': 'Ancient Near East', 'startYear': -3100, 'endYear': -30, 'color': 0xFFD700},
    'akkadian': {'name': 'Akkadian Empire', 'region': 'Ancient Near East', 'startYear': -2334, 'endYear': -2154, 'color': 0xFFA07A},
    'elam': {'name': 'Elam', 'region': 'Ancient Near East', 'startYear': -3200, 'endYear': -601, 'color': 0xE6A44C},
    'babylonian': {'name': 'Babylonian Empire', 'region': 'Ancient Near East', 'startYear': -1894, 'endYear': -539, 'color': 0xFFB347},
    'assyrian': {'name': 'Assyrian Empire', 'region': 'Ancient Near East', 'startYear': -2500, 'endYear': -609, 'color': 0xFF6B6B},
    'hittite': {'name': 'Hittite Empire', 'region': 'Ancient Near East', 'startYear': -1600, 'endYear': -1178, 'color': 0xFFAA00},
    'mitanni': {'name': 'Mitanni', 'region': 'Ancient Near East', 'startYear': -1500, 'endYear': -1241, 'color': 0xD4A574},

    # Mediterranean (9)
    'minoan': {'name': 'Minoan Civilization', 'region': 'Mediterranean', 'startYear': -1600, 'endYear': -1401, 'color': 0x20B2AA},
    'mycenaean': {'name': 'Mycenaean Greece', 'region': 'Mediterranean', 'startYear': -1500, 'endYear': -1101, 'color': 0x48D1CC},
    'phoenician': {'name': 'Phoenicia', 'region': 'Mediterranean', 'startYear': -700, 'endYear': -616, 'color': 0x9370DB},
    'etruscan': {'name': 'Etruscan Civilization', 'region': 'Mediterranean', 'startYear': -750, 'endYear': -265, 'color': 0xDB7093},
    'greek': {'name': 'Greek City-States', 'region': 'Mediterranean', 'startYear': -800, 'endYear': -338, 'color': 0xFFA07A},
    'macedonian': {'name': 'Macedonian Empire', 'region': 'Mediterranean', 'startYear': -338, 'endYear': -168, 'color': 0xFF8866},
    'carthaginian': {'name': 'Carthaginian Empire', 'region': 'Mediterranean', 'startYear': -814, 'endYear': -146, 'color': 0xFFAA88},
    'roman': {'name': 'Roman Empire', 'region': 'Mediterranean', 'startYear': -509, 'endYear': 476, 'color': 0xFF7777},
    'byzantine': {'name': 'Byzantine Empire', 'region': 'Mediterranean', 'startYear': 330, 'endYear': 1453, 'color': 0xFF99AA},

    # Persian/Central Asia (5)
    'achaemenid': {'name': 'Achaemenid Persia', 'region': 'Persian/Central Asia', 'startYear': -550, 'endYear': -330, 'color': 0x00BFFF},
    'seleucid': {'name': 'Seleucid Empire', 'region': 'Persian/Central Asia', 'startYear': -312, 'endYear': -63, 'color': 0x00CED1},
    'parthian': {'name': 'Parthian Empire', 'region': 'Persian/Central Asia', 'startYear': -247, 'endYear': 224, 'color': 0x40E0D0},
    'kushan': {'name': 'Kushan Empire', 'region': 'Persian/Central Asia', 'startYear': 43, 'endYear': 237, 'color': 0x5F9EA0},
    'sassanid': {'name': 'Sassanid Empire', 'region': 'Persian/Central Asia', 'startYear': 224, 'endYear': 651, 'color': 0x7FFFD4},

    # East Asia (4)
    'shang': {'name': 'Shang Dynasty', 'region': 'East Asia', 'startYear': -1600, 'endYear': -1046, 'color': 0xFFD700},
    'zhou': {'name': 'Zhou Dynasty', 'region': 'East Asia', 'startYear': -1046, 'endYear': -256, 'color': 0xFFE135},
    'qin': {'name': 'Qin Dynasty', 'region': 'East Asia', 'startYear': -221, 'endYear': -206, 'color': 0xFF5733},
    'han': {'name': 'Han Dynasty', 'region': 'East Asia', 'startYear': -206, 'endYear': 220, 'color': 0xFF6347},

    # South Asia (3)
    'indus_valley': {'name': 'Indus Valley (Harappan)', 'region': 'South Asia', 'startYear': -3000, 'endYear': -1701, 'color': 0x66CDAA},
    'maurya': {'name': 'Maurya Empire', 'region': 'South Asia', 'startYear': -322, 'endYear': -185, 'color': 0x7FFF00},
    'gupta': {'name': 'Gupta Empire', 'region': 'South Asia', 'startYear': 320, 'endYear': 550, 'color': 0x00FF7F},

    # Africa (2)
    'kush': {'name': 'Kingdom of Kush', 'region': 'Africa', 'startYear': -1070, 'endYear': 350, 'color': 0xFF8C00},
    'axum': {'name': 'Aksumite Empire', 'region': 'Africa', 'startYear': 100, 'endYear': 940, 'color': 0xCD853F},

    # Americas (6)
    'olmec': {'name': 'Olmec Civilization', 'region': 'Americas', 'startYear': -650, 'endYear': -351, 'color': 0x228B22},
    'zapotec': {'name': 'Zapotec Civilization', 'region': 'Americas', 'startYear': -500, 'endYear': 900, 'color': 0x3CB371},
    'teotihuacan': {'name': 'Teotihuacan', 'region': 'Americas', 'startYear': -50, 'endYear': 704, 'color': 0x2E8B57},
    'maya': {'name': 'Maya Civilization', 'region': 'Americas', 'startYear': -2000, 'endYear': 1500, 'color': 0x00FF7F},
    'aztec': {'name': 'Aztec Empire', 'region': 'Americas', 'startYear': 1428, 'endYear': 1521, 'color': 0x7CFC00},
    'inca': {'name': 'Inca Empire', 'region': 'Americas', 'startYear': 1438, 'endYear': 1533, 'color': 0x7FFF00},

    # Medieval Europe (1)
    'carolingian': {'name': 'Carolingian Empire', 'region': 'Medieval Europe', 'startYear': 751, 'endYear': 888, 'color': 0x6495ED},
}


def format_year(year: int) -> str:
    """Format a year integer as '3100 BCE' or '476 CE'."""
    if year <= 0:
        return f"{abs(year)} BCE"
    return f"{year} CE"


def get_empire_period(empire_id: str) -> str:
    """Get formatted period string for an empire, e.g. '509 BCE \u2013 476 CE'."""
    meta = EMPIRE_METADATA.get(empire_id)
    if not meta:
        return ""
    return f"{format_year(meta['startYear'])} \u2013 {format_year(meta['endYear'])}"
