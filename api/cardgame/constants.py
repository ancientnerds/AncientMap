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

# Keep in sync with: src/constants/colors.ts CATEGORY_TO_GROUP
_GROUP_DEFINITIONS: dict[str, list[str]] = {
    "Settlements": [
        "City",
        "Town",
        "Village",
        "Settlement",
        "Urban",
        "Villa",
        "City/town/settlement",
        "Residence/villa/farmhouse",
        "City/town/settlement, Pyramid complex",
    ],
    "Fortifications": [
        "Castle",
        "Citadel",
        "Fort",
        "Fortress",
        "Military",
        "Wall",
        "Gate",
        "Fortress/citadel",
        "Castle/palace",
        "Gate/archway/bridge",
        "Fortification",
    ],
    "Religious": [
        "Church",
        "Mosque",
        "Temple",
        "Monastery",
        "Sacred site",
        "Sanctuary",
        "Religious",
        "Temple complex",
        "Church/cathedral",
        "Minaret/tower",
        "Stone cross",
    ],
    "Burial & Death": [
        "Cemetery",
        "Necropolis",
        "Tomb",
        "Burial",
        "Funerary",
        "Necropolis/tombs complex",
        "Barrow",
        "Mound/tumulus",
        "Cairn",
        "Elongated skulls",
    ],
    "Megalithic": [
        "Megalithic",
        "Megalithic stones",
        "Megalithic structures",
        "Megalithic statues",
        "Megalithic walls",
        "Stone circle",
        "Dolmen",
        "Standing stone",
        "Henge",
        "Timber circle",
        "Polygonal masonry",
    ],
    "Rock & Cave": [
        "Cave",
        "Cave Structures",
        "Rock relief/carving",
        "Rock art",
        "Petroglyphs",
        "Sculptured stone",
        "Cave Structures, Rock art",
        "Geoglyphs",
    ],
    "Infrastructure": [
        "Road",
        "Bridge",
        "Mine",
        "Quarry",
        "Infrastructure",
        "Road/avenue/trackway",
        "Reservoir/aqueduct/canal",
        "Mine/quarry",
        "Earthwork",
        "Well",
    ],
    "Water & Ports": [
        "Aqueduct",
        "Bath",
        "Harbor",
        "Port",
        "Underwater structures",
        "Shipwreck",
    ],
    "Monuments": [
        "Monument",
        "Memorial",
        "Stadium",
        "Theater",
        "Theatre",
        "Forum",
        "Palace",
        "Pyramid complex",
        "Museum",
        "Amphitheatre",
        "Scheduled monument",
        "Heritage site",
        "Archaeological site",
    ],
    "Other": [
        "Site",
        "Ruin",
        "Inscription",
        "Natural feature",
        "Impact crater",
        "Geological interest",
        "Magnetic anomaly",
        "Unknown",
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
    (-8000, 10),  # before 8000 BCE
    (-4500, 9),  # 8000-4500 BCE
    (-3000, 8),  # 4500-3000 BCE
    (-2000, 7),  # 3000-2000 BCE
    (-1000, 6),  # 2000-1000 BCE
    (-500, 5),  # 1000-500 BCE
    (0, 4),  # 500-1 BCE
    (500, 3),  # 1-500 CE
    (1000, 2),  # 500-1000 CE
    (1500, 1),  # 1000-1500 CE
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

# Discord embed colors only — frontend card colors are in rarity.ts
RARITY_COLORS: dict[int, int] = {
    1: 0x9E9E9E,  # Common — grey
    2: 0x4CAF50,  # Uncommon — green
    3: 0x2196F3,  # Rare — blue
    4: 0x9C27B0,  # Epic — purple
    5: 0xFFC107,  # Legendary — gold
}

# ---------------------------------------------------------------------------
# Pack definitions — type → (credit_cost, card_count, guarantees)
# guarantees = list of minimum rarity tiers (1=Common, 5=Legendary)
# ---------------------------------------------------------------------------

PACK_PRICES: dict[str, dict] = {
    "common": {"cost": 500, "cards": 3, "guarantees": [1, 1, 1]},
    "uncommon": {"cost": 1500, "cards": 3, "guarantees": [2, 1, 1]},
    "rare": {"cost": 5000, "cards": 5, "guarantees": [3, 2, 2, 1, 1]},
    "epic": {"cost": 15000, "cards": 5, "guarantees": [4, 3, 1, 1, 1]},
}

# Weighted rarity distribution for non-guaranteed slots
# Tuned for ~1% legendary per Bronze pack, ~10% per Epic pack.
RARITY_WEIGHTS: dict[int, float] = {
    1: 45,  # Common
    2: 30,  # Uncommon
    3: 15,  # Rare
    4: 4,  # Epic
    5: 0.33,  # Legendary
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
BATTLE_MAX_STAKE = 50000  # hard cap per duel — prevents absurd whale bets
STARTER_DECK_SIZE = 10

# Streak rewards: (day_threshold, reward_type, reward_value, repeating)
# repeating=True means the reward triggers every N days (via modulo)
STREAK_REWARDS: list[tuple[int, str, str, bool]] = [
    (3, "credits", "150", True),  # small bump every 3 days
    (7, "pack", "uncommon", True),  # weekly uncommon pack
    (14, "credits", "500", False),  # bi-weekly bonus (one-shot per cycle)
    (30, "pack", "rare", False),  # monthly rare pack (one-shot per cycle)
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

SYNERGY_CATEGORY_BONUS = 1  # +1 to group's primary stat
SYNERGY_TEMPORAL_BONUS = 1  # +1 legacy

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
    ("Religious", "Burial & Death"),  # sacred burial grounds
    ("Settlements", "Fortifications"),  # city-fortress complexes
    ("Water & Ports", "Infrastructure"),  # engineering marvels
    ("Megalithic", "Religious"),  # ritual stone circles
    ("Monuments", "Settlements"),  # civic centers
]
CROSS_COMBO_BONUS = 2

# ---------------------------------------------------------------------------
# Snap mechanic (Phase B)
# ---------------------------------------------------------------------------

SNAP_MULTIPLIER = 2  # stakes double on snap
SNAP_TIMEOUT_SECONDS = 30  # time to decide after a snap
ROUND_REVEAL_SECONDS = 10  # time between round reveals

# ---------------------------------------------------------------------------
# Quiz (Phase C)
# ---------------------------------------------------------------------------

QUIZ_QUESTIONS_PER_SESSION = 5
QUIZ_CREDITS_PER_CORRECT = 10
QUIZ_XP_PER_CORRECT = 5
QUIZ_PERFECT_BONUS_TIER = 1  # Common card for 5/5
QUIZ_DAILY_LIMIT = 3  # max quiz sessions per day

# ---------------------------------------------------------------------------
# Expeditions (Phase D)
# ---------------------------------------------------------------------------

EXPEDITION_STAGES = 5
EXPEDITION_WIN_CREDITS = 15
EXPEDITION_COMPLETE_PACK = "uncommon"
EXPEDITION_COOLDOWN_SECONDS = 30

# ---------------------------------------------------------------------------
# Card Evolution (Phase E)
# ---------------------------------------------------------------------------

# Fibonacci-based evolution: each star costs 2, 3, 5, 8, 13 duplicates
STAR_LEVELS: dict[int, dict] = {
    1: {"duplicates_needed": 2, "stat_bonus": 1},  # ★     — 2 dupes
    2: {"duplicates_needed": 5, "stat_bonus": 1},  # ★★    — 5 dupes total (2+3)
    3: {"duplicates_needed": 10, "stat_bonus": 1},  # ★★★   — 10 dupes total (2+3+5)
    4: {"duplicates_needed": 18, "stat_bonus": 1},  # ★★★★  — 18 dupes total (2+3+5+8)
    5: {"duplicates_needed": 31, "stat_bonus": 1},  # ★★★★★ — 31 dupes total (2+3+5+8+13)
}
MAX_STAR_LEVEL = 5


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


# ---------------------------------------------------------------------------
# Empire Cards & Commander System
# ---------------------------------------------------------------------------

# Thematic stat per empire — what the commander bonus applies to
EMPIRE_THEMATIC_STATS: dict[str, str] = {
    "roman": "fortification",
    "egyptian": "mystery",
    "greek": "cultural_influence",
    "han": "legacy",
    "maurya": "cultural_influence",
    "akkadian": "antiquity",
    "kush": "mystery",
    "axum": "mystery",
    "maya": "mystery",
    "inca": "fortification",
    "aztec": "fortification",
    "byzantine": "legacy",
    "achaemenid": "fortification",
    "assyrian": "fortification",
    "babylonian": "mystery",
    "hittite": "fortification",
    "minoan": "mystery",
    "mycenaean": "fortification",
    "phoenician": "cultural_influence",
    "carthaginian": "fortification",
    "macedonian": "fortification",
    "seleucid": "cultural_influence",
    "parthian": "fortification",
    "kushan": "cultural_influence",
    "sassanid": "fortification",
    "shang": "antiquity",
    "zhou": "legacy",
    "qin": "fortification",
    "indus_valley": "antiquity",
    "gupta": "cultural_influence",
    "zapotec": "mystery",
    "teotihuacan": "mystery",
    "olmec": "antiquity",
    "carolingian": "legacy",
    "etruscan": "mystery",
    "mitanni": "antiquity",
    "elam": "antiquity",
}

# Period strings and display names computed from the single source of truth
from pipeline.historical_boundaries.empire_metadata import (
    EMPIRE_METADATA,
    get_empire_period,
)

EMPIRE_DISPLAY_NAMES: dict[str, str] = {eid: meta["name"] for eid, meta in EMPIRE_METADATA.items()}

# Commander bonuses
COMMANDER_BONUS = 1  # +1 to thematic stat for homeland cards
COMMANDER_MAX_CARDS = 3  # max cards that get the commander bonus

# Crossroads synergy: empire diversity of site cards
CROSSROADS_THRESHOLDS: list[tuple[int, int]] = [
    (6, 2),  # 6+ different empires → +2 cultural_influence to ALL cards
    (4, 1),  # 4+ different empires → +1 cultural_influence to ALL cards
]

# Ancient Anchor: pre-empire sites
ANCIENT_ANCHOR_THRESHOLD = 2  # need 2+ anchor cards
ANCIENT_ANCHOR_BONUS = 1  # +1 mystery to all anchor cards

# ---------------------------------------------------------------------------
# Trade Routes synergy
# ---------------------------------------------------------------------------

TRADE_ROUTE_BONUS = 1  # +1 Legacy per active route
TRADE_NETWORK_BONUS = 2  # +2 Legacy when route is part of a triangle
TRADE_ROUTE_MAX_ACTIVE = 3  # max routes per deck

# (name, empire_a, empire_b, trade_goods)
TRADE_ROUTES: list[tuple[str, str, str, str]] = [
    ("Silk Road", "han", "roman", "silk, spices, glassware"),
    ("Incense Route", "axum", "roman", "frankincense, ivory, gold"),
    ("Nile Corridor", "egyptian", "kush", "gold, ebony, exotic animals"),
    ("Royal Road", "achaemenid", "greek", "tribute, ideas, diplomats"),
    ("Amber Road", "roman", "carolingian", "amber, furs, metalwork"),
    ("Lapis Lazuli Road", "indus_valley", "akkadian", "lapis lazuli, textiles, grain"),
    ("Obsidian Network", "olmec", "maya", "obsidian, jade, cacao"),
    ("Tin Route", "phoenician", "minoan", "tin, copper, purple dye"),
    ("Spice Trade", "roman", "maurya", "pepper, gems, cotton"),
    ("Gandhara Corridor", "kushan", "han", "Buddhism, art, horses"),
    ("Red Sea Circuit", "egyptian", "axum", "myrrh, gold, papyrus"),
    ("Punic Exchange", "carthaginian", "greek", "grain, pottery, metals"),
    ("Fertile Crescent Link", "babylonian", "hittite", "tin, textiles, diplomacy"),
    ("Anatolian Bridge", "hittite", "mycenaean", "copper, iron, olive oil"),
    ("Persian Gulf Trade", "elam", "akkadian", "timber, stone, bitumen"),
    ("Hellenistic Corridor", "seleucid", "macedonian", "Greek culture, coinage"),
    ("Sassanid Silk Road", "sassanid", "byzantine", "silk, spices, religion"),
    ("Zhou Bronze Road", "zhou", "shang", "bronze, oracle bones, ritual vessels"),
    ("Mesoamerican Tribute", "aztec", "maya", "cacao, feathers, jade"),
    ("Gupta Maritime Trade", "gupta", "sassanid", "spices, textiles, philosophy"),
    ("Kushan Silk Route", "kushan", "roman", "silk, horses, gemstones"),
    ("Nubian Trade", "axum", "kush", "salt, gold, slaves"),
    ("Aegean Bronze Trade", "babylonian", "mycenaean", "tin, textiles, amber"),
]

# Expedition → empire card reward mapping
EXPEDITION_EMPIRE_REWARDS: dict[str, str | None] = {
    "nile_valley": "egyptian",
    "aegean": "greek",
    "mesoamerica": "maya",
    "fertile_crescent": "akkadian",
    "british_isles": None,  # Ancient Anchor — no empire card
    "indus_valley": "maurya",
    "east_asia": "han",
    "sub_saharan": "kush",
    "andes": "inca",
    "mediterranean": "roman",
}

# Empire card educational descriptions
EMPIRE_DESCRIPTIONS: dict[str, str] = {
    "roman": "From a small city-state on the Tiber to the greatest empire of antiquity. Roman engineering, law, and military organization shaped Western civilization for millennia.",
    "egyptian": "For 3,000 years the pharaohs ruled the Nile Valley, building monuments that still astound. Egyptian religion, writing, and architecture influenced all subsequent Mediterranean civilizations.",
    "greek": "The Greek city-states pioneered democracy, philosophy, theater, and the Olympic Games. Their intellectual legacy forms the foundation of Western thought.",
    "han": "The Han Dynasty consolidated China into a unified empire with a centralized bureaucracy, the Silk Road, and advances in papermaking that changed the world.",
    "maurya": "Under Chandragupta and Ashoka, the Maurya Empire unified most of the Indian subcontinent. Ashoka's edicts promoting non-violence are among history's earliest human rights declarations.",
    "akkadian": "The world's first empire, founded by Sargon of Akkad around 2334 BCE. It united Mesopotamia under a single ruler for the first time.",
    "kush": "The Kingdom of Kush rivaled Egypt for centuries, with its own pyramids, iron industry, and trade networks stretching from Central Africa to the Mediterranean.",
    "axum": "One of the four great powers of the ancient world. The Aksumite Empire controlled Red Sea trade routes and was among the first states to adopt Christianity.",
    "maya": "The Maya built magnificent cities in the jungle, developed the most sophisticated writing system in the Americas, and made astronomical calculations of stunning accuracy.",
    "inca": "Without wheels, iron, or written language, the Inca built 40,000 km of roads across extreme mountain terrain and administered the largest empire in pre-Columbian America.",
    "aztec": "The Aztec Triple Alliance dominated Mesoamerica through military conquest and tributary networks, building the island city of Tenochtitlan with a population exceeding 200,000.",
    "byzantine": "The Eastern Roman Empire preserved Greek and Roman knowledge for a millennium, defending Christendom while the West fell into fragmentation.",
    "achaemenid": "The largest empire the ancient world had yet seen, stretching from Egypt to India. The Achaemenids pioneered religious tolerance, postal systems, and imperial roads.",
    "assyrian": "Masters of siege warfare and empire administration. The Assyrians created the first true imperial bureaucracy and the great library of Ashurbanipal.",
    "babylonian": "Home of the Hanging Gardens and the Code of Hammurabi. Babylonian astronomers mapped the stars with precision unmatched for centuries.",
    "hittite": "The Hittites were among the first to smelt iron, and their battle with Egypt at Kadesh produced history's first known peace treaty.",
    "minoan": "Europe's first advanced civilization, centered on Crete. The Minoans built elaborate palace complexes and developed a writing system still undeciphered.",
    "mycenaean": "Warriors and traders who inspired Homer's epics. Mycenaean fortifications and Linear B tablets reveal a sophisticated Bronze Age civilization.",
    "phoenician": "The Phoenicians invented the alphabet, colonized the Mediterranean, and built a trading network that connected three continents.",
    "carthaginian": "Founded by Phoenician settlers, Carthage became Rome's greatest rival. Hannibal's crossing of the Alps remains one of military history's boldest feats.",
    "macedonian": "Alexander the Great's empire stretched from Greece to India, spreading Greek culture across the known world and creating the Hellenistic age.",
    "seleucid": "Successors to Alexander in the East, the Seleucids ruled a vast multicultural empire blending Greek, Persian, and Mesopotamian traditions.",
    "parthian": "The Parthian Empire held Rome at bay for centuries with their legendary mounted archers and controlled the lucrative Silk Road trade routes.",
    "kushan": "At the crossroads of civilizations, the Kushans facilitated the spread of Buddhism along the Silk Road and patronized Gandharan art.",
    "sassanid": "The last great Persian empire before Islam, renowned for its art, architecture, and the preservation of Zoroastrian traditions.",
    "shang": "China's first historically verified dynasty, the Shang developed oracle bone script — the ancestor of modern Chinese characters.",
    "zhou": "The longest-lasting Chinese dynasty produced Confucius, Laozi, and Sun Tzu. The Zhou concept of the Mandate of Heaven shaped Chinese political philosophy.",
    "qin": "Though brief, the Qin Dynasty unified China, standardized weights and writing, built the Great Wall's first incarnation, and created the Terracotta Army.",
    "indus_valley": "One of the world's earliest urban civilizations, with grid-planned cities, indoor plumbing, and a writing system that remains undeciphered after a century of study.",
    "gupta": "India's Golden Age — the Gupta period produced breakthroughs in mathematics (including the concept of zero), astronomy, literature, and art.",
    "zapotec": "The Zapotecs built Monte Alban atop a flattened mountain, one of Mesoamerica's earliest cities, and developed one of the region's first writing systems.",
    "teotihuacan": "The mysterious city of Teotihuacan, with its massive Pyramid of the Sun, was the largest city in the pre-Columbian Americas at its peak.",
    "olmec": "The 'mother culture' of Mesoamerica. The Olmec created colossal stone heads and laid the foundations for later Maya and Aztec civilizations.",
    "carolingian": "Charlemagne united much of Western Europe for the first time since Rome, sparking a cultural revival that preserved classical learning.",
    "etruscan": "The Etruscans preceded and deeply influenced Rome, contributing the arch, the toga, gladiatorial combat, and much of Roman religious practice.",
    "mitanni": "A Hurrian-speaking empire that rivaled Egypt and the Hittites. The Mitanni were among the first to use war chariots as a decisive military force.",
    "elam": "One of the oldest civilizations in the world, Elam developed its own writing system and repeatedly clashed with and influenced Mesopotamian cultures.",
}

EMPIRE_PERIODS: dict[str, str] = {eid: get_empire_period(eid) for eid in EMPIRE_METADATA}
