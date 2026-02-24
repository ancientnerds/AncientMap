"""Card game constants — single source of truth for game rules.

Builds category-to-group mapping from the canonical site_type normalizer
so there's no duplication with the pipeline code.
"""

from pipeline.normalizers.site_type import normalize_site_type

# ---------------------------------------------------------------------------
# Category groups — each canonical site_type maps to one group.
# The normalizer's CANONICAL_TYPES list is organized by section comments;
# we replicate that grouping here explicitly.
# ---------------------------------------------------------------------------

_GROUP_DEFINITIONS: dict[str, list[str]] = {
    "Settlements": [
        "city", "town", "village", "settlement", "urban", "villa",
        "City/town/settlement", "Residence/villa/farmhouse",
        "City/town/settlement, Pyramid complex",
    ],
    "Fortifications": [
        "castle", "citadel", "fort", "fortress", "military", "wall", "gate",
        "Fortress/citadel", "Castle/palace", "Fortress",
        "Gate/archway/bridge", "Wall", "Fortification",
    ],
    "Religious": [
        "church", "mosque", "temple", "monastery", "sacred_site", "sanctuary",
        "religious", "Temple complex", "Church/cathedral", "Minaret/tower",
        "Stone cross",
    ],
    "Burial & Death": [
        "cemetery", "necropolis", "tomb", "burial", "funerary",
        "Necropolis/tombs complex", "Cemetery", "Barrow", "Mound/tumulus",
        "Cairn", "Elongated skulls",
    ],
    "Megalithic": [
        "megalithic", "Megalithic stones", "Megalithic structures",
        "Megalithic statues", "Megalithic walls", "Stone circle", "Dolmen",
        "Standing stone", "Henge", "Timber circle", "Polygonal masonry",
        "Megalithic",
    ],
    "Rock & Cave": [
        "cave", "Cave Structures", "Rock relief/carving", "Rock art",
        "Petroglyphs", "Sculptured stone", "Cave Structures, Rock art",
        "Geoglyphs",
    ],
    "Infrastructure": [
        "road", "bridge", "mine", "quarry", "infrastructure",
        "Road/avenue/trackway", "Reservoir/aqueduct/canal", "Mine/quarry",
        "Earthwork", "Well",
    ],
    "Water & Ports": [
        "aqueduct", "bath", "harbor", "port",
        "Underwater structures", "Bath", "Shipwreck",
    ],
    "Monuments": [
        "monument", "memorial", "stadium", "theater", "theatre", "Theatre",
        "forum", "palace", "Pyramid complex", "Museum", "Amphitheatre",
        "scheduled_monument", "heritage_site", "archaeological_site", "Monument",
    ],
    "Other": [
        "site", "ruin", "inscription", "natural_feature", "impact_crater",
        "Geological interest", "Magnetic anomaly", "unknown", "Unknown",
    ],
}

# Build reverse lookup: site_type → group name
CATEGORY_GROUP: dict[str, str] = {}
for _group, _types in _GROUP_DEFINITIONS.items():
    for _t in _types:
        CATEGORY_GROUP[_t] = _group

# ---------------------------------------------------------------------------
# Fortification stat per group (how defensible the site type is)
# ---------------------------------------------------------------------------

GROUP_FORTIFICATION: dict[str, int] = {
    "Fortifications": 10,
    "Megalithic": 8,
    "Monuments": 7,
    "Infrastructure": 6,
    "Settlements": 5,
    "Water & Ports": 4,
    "Religious": 3,
    "Burial & Death": 2,
    "Rock & Cave": 2,
    "Other": 3,
}

# ---------------------------------------------------------------------------
# Antiquity stat buckets — (upper_bound_exclusive, stat_value)
# period_start is negative for BCE, positive for CE
# ---------------------------------------------------------------------------

ANTIQUITY_BUCKETS: list[tuple[int, int]] = [
    (-8000, 10),   # before 8000 BCE
    (-4500, 9),    # 8000-4500 BCE
    (-3000, 8),    # 4500-3000 BCE
    (-2000, 7),    # 3000-2000 BCE
    (-1000, 6),    # 2000-1000 BCE
    (-500, 5),     # 1000-500 BCE
    (0, 4),        # 500-1 BCE
    (500, 3),      # 1-500 CE
    (1000, 2),     # 500-1000 CE
    (1500, 1),     # 1000-1500 CE
]
ANTIQUITY_DEFAULT = 5  # for sites with no period_start

# ---------------------------------------------------------------------------
# Type advantage wheel — group A beats group B
# ---------------------------------------------------------------------------

TYPE_ADVANTAGE: dict[str, str] = {
    "Fortifications": "Settlements",
    "Settlements": "Religious",
    "Religious": "Burial & Death",
    "Burial & Death": "Megalithic",
    "Megalithic": "Fortifications",
    "Monuments": "Infrastructure",
    "Infrastructure": "Water & Ports",
    "Water & Ports": "Rock & Cave",
    "Rock & Cave": "Monuments",
}
TYPE_ADVANTAGE_BONUS = 2

# ---------------------------------------------------------------------------
# Rarity tiers — (min_rarity_score, tier_number, tier_name)
# Thresholds calibrated after first generator run; these are starting values.
# ---------------------------------------------------------------------------

RARITY_TIERS: list[tuple[int, int, str]] = [
    (60, 5, "Legendary"),
    (45, 4, "Epic"),
    (30, 3, "Rare"),
    (18, 2, "Uncommon"),
    (0, 1, "Common"),
]

RARITY_NAMES: dict[int, str] = {t: name for _, t, name in RARITY_TIERS}

# Discord embed colors per rarity tier
RARITY_COLORS: dict[int, int] = {
    1: 0x9E9E9E,   # Common — grey
    2: 0x4CAF50,   # Uncommon — green
    3: 0x2196F3,   # Rare — blue
    4: 0x9C27B0,   # Epic — purple
    5: 0xFFC107,   # Legendary — gold
}

# ---------------------------------------------------------------------------
# Pack definitions — type → (credit_cost, card_count, guarantees)
# guarantees = list of minimum rarity tiers (1=Common, 5=Legendary)
# ---------------------------------------------------------------------------

PACK_PRICES: dict[str, dict] = {
    "bronze": {"cost": 500, "cards": 3, "guarantees": [1, 1, 1]},
    "silver": {"cost": 1500, "cards": 3, "guarantees": [2, 1, 1]},
    "gold": {"cost": 5000, "cards": 5, "guarantees": [3, 2, 2, 1, 1]},
    "legendary": {"cost": 15000, "cards": 5, "guarantees": [4, 3, 1, 1, 1]},
}

# Weighted rarity distribution for non-guaranteed slots
RARITY_WEIGHTS: dict[int, int] = {
    1: 40,   # Common
    2: 30,   # Uncommon
    3: 18,   # Rare
    4: 9,    # Epic
    5: 3,    # Legendary
}

# ---------------------------------------------------------------------------
# Mystery stat — (site_type, period_name) combo count thresholds
# ---------------------------------------------------------------------------

MYSTERY_BUCKETS: list[tuple[int, int]] = [
    (1, 10),
    (2, 9),
    (5, 8),
    (10, 7),
    (25, 6),
    (50, 5),
    (100, 4),
    (150, 3),
    (200, 2),
]
MYSTERY_DEFAULT = 1  # combo_count >= 200

# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------

DAILY_CREDITS = 100
BATTLE_WIN_CREDITS = 25
BATTLE_CARD_DROP_CHANCE = 0.10  # 10%
STARTER_DECK_SIZE = 10

# Streak rewards: (day_threshold, reward_type, reward_value, repeating)
# repeating=True means the reward triggers every N days (via modulo)
STREAK_REWARDS: list[tuple[int, str, str, bool]] = [
    (3, "credits", "150", True),     # small bump every 3 days
    (7, "pack", "silver", True),     # weekly silver pack
    (14, "credits", "500", False),   # bi-weekly bonus (one-shot per cycle)
    (30, "pack", "gold", False),     # monthly gold pack (one-shot per cycle)
]


# ---------------------------------------------------------------------------
# Synergy system (Phase A)
# ---------------------------------------------------------------------------

SYNERGY_THRESHOLD = 3  # min cards to trigger a synergy

# Each group's "primary stat" — boosted when category synergy triggers
GROUP_PRIMARY_STAT: dict[str, str] = {
    "Settlements": "cultural_influence",
    "Fortifications": "fortification",
    "Religious": "mystery",
    "Burial & Death": "antiquity",
    "Megalithic": "fortification",
    "Rock & Cave": "antiquity",
    "Infrastructure": "legacy",
    "Water & Ports": "cultural_influence",
    "Monuments": "legacy",
    "Other": "mystery",
}

SYNERGY_CATEGORY_BONUS = 1   # +1 to group's primary stat
SYNERGY_REGIONAL_BONUS = 1   # +1 cultural_influence
SYNERGY_TEMPORAL_BONUS = 1   # +1 legacy

# Period buckets for temporal synergy (upper_bound_exclusive, bucket_name)
PERIOD_BUCKETS: list[tuple[int, str]] = [
    (-3000, "Prehistoric"),
    (-1200, "Bronze Age"),
    (-500, "Iron Age"),
    (500, "Classical"),
    (1500, "Medieval"),
]

# Cross-combo: category pairs from same country → +2 mystery to both
CROSS_COMBO_PAIRS: list[tuple[str, str]] = [
    ("Religious", "Burial & Death"),       # sacred burial grounds
    ("Settlements", "Fortifications"),     # city-fortress complexes
    ("Water & Ports", "Infrastructure"),   # engineering marvels
    ("Megalithic", "Religious"),           # ritual stone circles
    ("Monuments", "Settlements"),          # civic centers
]
CROSS_COMBO_BONUS = 2

# ---------------------------------------------------------------------------
# Snap mechanic (Phase B)
# ---------------------------------------------------------------------------

SNAP_MULTIPLIER = 2          # stakes double on snap
SNAP_TIMEOUT_SECONDS = 30    # time to decide after a snap
ROUND_REVEAL_SECONDS = 10    # time between round reveals

# ---------------------------------------------------------------------------
# Quiz (Phase C)
# ---------------------------------------------------------------------------

QUIZ_QUESTIONS_PER_SESSION = 5
QUIZ_CREDITS_PER_CORRECT = 10
QUIZ_XP_PER_CORRECT = 5
QUIZ_PERFECT_BONUS_TIER = 1  # Common card for 5/5
QUIZ_DAILY_LIMIT = 3         # max quiz sessions per day

# ---------------------------------------------------------------------------
# Expeditions (Phase D)
# ---------------------------------------------------------------------------

EXPEDITION_STAGES = 5
EXPEDITION_WIN_CREDITS = 15
EXPEDITION_COMPLETE_PACK = "silver"
EXPEDITION_COOLDOWN_SECONDS = 30

# ---------------------------------------------------------------------------
# Card Evolution (Phase E)
# ---------------------------------------------------------------------------

STAR_LEVELS: dict[int, dict] = {
    1: {"duplicates_needed": 0, "stat_bonus": 0},
    2: {"duplicates_needed": 3, "stat_bonus": 1},   # +1 to highest stat
    3: {"duplicates_needed": 8, "stat_bonus": 1},   # +1 to second highest (cumulative)
}


# ---------------------------------------------------------------------------
# Player Level System
# ---------------------------------------------------------------------------

LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500, 7500, 10000]


def get_level(xp: int) -> tuple[int, int, int]:
    """Returns (level, xp_into_level, xp_needed_for_next)."""
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp < threshold:
            prev = LEVEL_THRESHOLDS[i - 1]
            return i, xp - prev, threshold - prev
    return len(LEVEL_THRESHOLDS), xp, 0


def get_group(site_type: str | None) -> str:
    """Get the category group for a site type, normalizing first."""
    normalized = normalize_site_type(site_type)
    return CATEGORY_GROUP.get(normalized, "Other")


def get_rarity_tier(rarity_score: int) -> tuple[int, str]:
    """Get (tier_number, tier_name) for a rarity score."""
    for min_score, tier, name in RARITY_TIERS:
        if rarity_score >= min_score:
            return tier, name
    return 1, "Common"
