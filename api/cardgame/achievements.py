"""Achievement system — 102 achievements across 10 categories.

Provides:
- ACHIEVEMENTS: complete definition dict
- seed_achievements(): upsert all definitions into DB (idempotent)
- check_achievements(): event-driven checker, returns newly unlocked
- claim_achievement_reward(): grant credits/xp/cards for a claimed achievement
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.cardgame.models import (
    Achievement,
    CardCollection,
    CardPlayerStats,
    CardStats,
    EmpireCollection,
    ExpeditionProgress,
    QuizSession,
    UserAchievement,
)
from pipeline.database import (
    CreditGrant,
    DiscordUser,
    SiteBookmark,
    SiteLike,
    TokenUsageLog,
    UnifiedSite,
)

# ---------------------------------------------------------------------------
# Achievement definitions — all 102
# ---------------------------------------------------------------------------
# Format: id -> {category, name, description, tier, reward_credits, reward_xp,
#                reward_card_tier, reward_card_count, icon, sort_order, hidden}

ACHIEVEMENTS: dict[str, dict] = {}
_order = 0


def _a(
    id: str,
    category: str,
    name: str,
    desc: str,
    tier: str,
    cr: int,
    xp: int,
    icon: str,
    card_tier: int | None = None,
    card_count: int = 0,
    hidden: bool = False,
) -> None:
    global _order
    _order += 1
    ACHIEVEMENTS[id] = {
        "category": category,
        "name": name,
        "description": desc,
        "tier": tier,
        "reward_credits": cr,
        "reward_xp": xp,
        "reward_card_tier": card_tier,
        "reward_card_count": card_count,
        "icon": icon,
        "sort_order": _order,
        "hidden": hidden,
    }


# ---- EXPLORER (12) ----
_a(
    "explorer_first_sight",
    "explorer",
    "First Sight",
    "View your first archaeological site on the globe",
    "bronze",
    50,
    10,
    "\U0001f441",
)
_a(
    "explorer_ten_wonders",
    "explorer",
    "Ten Wonders",
    "Interact with 10 different sites",
    "bronze",
    100,
    15,
    "\U0001f30d",
)
_a(
    "explorer_hundred_sites",
    "explorer",
    "The Grand Tour",
    "Interact with 100 different sites",
    "silver",
    500,
    25,
    "\U0001f5fa",
    1,
    1,
)
_a(
    "explorer_five_hundred",
    "explorer",
    "Seasoned Traveler",
    "Interact with 500 different sites",
    "gold",
    1500,
    40,
    "\U0001f9ed",
    2,
    1,
)
_a(
    "explorer_thousand",
    "explorer",
    "World Walker",
    "Interact with 1,000 different sites",
    "platinum",
    3000,
    75,
    "\U0001f30f",
    3,
    1,
)
_a(
    "explorer_continent_hopper",
    "explorer",
    "Continent Hopper",
    "Interact with sites on 5 different continents",
    "silver",
    500,
    25,
    "\u2708\ufe0f",
    1,
    1,
)
_a(
    "explorer_seven_continents",
    "explorer",
    "Seven Continents",
    "Interact with sites on all inhabited continents",
    "gold",
    1000,
    25,
    "\U0001f30e",
    2,
    1,
)
_a(
    "explorer_time_traveler",
    "explorer",
    "Time Traveler",
    "Interact with sites from 5 different period categories",
    "silver",
    300,
    20,
    "\u231b",
    1,
    1,
)
_a(
    "explorer_screenshot",
    "explorer",
    "Captured Moment",
    "Take a screenshot of the globe",
    "bronze",
    50,
    5,
    "\U0001f4f8",
)
_a(
    "explorer_street_view",
    "explorer",
    "Boots on the Ground",
    "View Google Street View for any site",
    "bronze",
    100,
    10,
    "\U0001f463",
)
_a(
    "explorer_offline",
    "explorer",
    "Off the Grid",
    "Enable offline mode and download data",
    "bronze",
    450,
    15,
    "\U0001f4e1",
    1,
    1,
)
_a(
    "explorer_random",
    "explorer",
    "Hand of Fate",
    "Use the Random Site button",
    "bronze",
    100,
    10,
    "\U0001f3b2",
)

# ---- SCHOLAR (10) ----
_a(
    "scholar_first_question",
    "scholar",
    "Curious Mind",
    "Ask Lyra your first question",
    "bronze",
    100,
    15,
    "\U0001f4ac",
)
_a(
    "scholar_ten_questions",
    "scholar",
    "Apprentice Scholar",
    "Have 10 conversations with Lyra",
    "bronze",
    200,
    20,
    "\U0001f4da",
)
_a(
    "scholar_fifty_questions",
    "scholar",
    "Dedicated Student",
    "Have 50 conversations with Lyra",
    "silver",
    500,
    30,
    "\U0001f393",
    1,
    1,
)
_a(
    "scholar_two_hundred",
    "scholar",
    "Walking Encyclopedia",
    "Have 200 conversations with Lyra",
    "gold",
    1500,
    50,
    "\U0001f4d6",
    2,
    1,
)
_a(
    "scholar_five_hundred",
    "scholar",
    "Grand Librarian",
    "Have 500 conversations with Lyra",
    "platinum",
    3000,
    75,
    "\U0001f3db",
    3,
    1,
)
_a(
    "scholar_site_context",
    "scholar",
    "Field Researcher",
    "Ask Lyra about a specific site",
    "bronze",
    100,
    15,
    "\U0001f50d",
)
_a(
    "scholar_news_context",
    "scholar",
    "Current Affairs",
    "Ask Lyra about a news item",
    "bronze",
    100,
    15,
    "\U0001f4f0",
)
_a(
    "scholar_empire_context",
    "scholar",
    "Empire Analyst",
    "Ask Lyra about an empire",
    "bronze",
    100,
    15,
    "\U0001f451",
)
_a(
    "scholar_image_analyst",
    "scholar",
    "Visual Archaeologist",
    "Send Lyra an image for analysis",
    "silver",
    500,
    25,
    "\U0001f4f7",
    1,
    1,
)
_a(
    "scholar_big_spender",
    "scholar",
    "Patron of Knowledge",
    "Spend 1,000 total credits on Lyra",
    "gold",
    1000,
    30,
    "\U0001f4b0",
)
_a(
    "scholar_polyglot",
    "scholar",
    "Polyglot Excavator",
    "Ask Lyra about sites in 10 different countries",
    "silver",
    500,
    25,
    "\U0001f30d",
)
_a(
    "scholar_time_weaver",
    "scholar",
    "Time Weaver",
    "Explore sites from 5 different period categories",
    "silver",
    500,
    25,
    "\u231b",
)
_a(
    "scholar_deep_diver",
    "scholar",
    "Deep Diver",
    "Send 10+ messages in a single conversation",
    "bronze",
    200,
    15,
    "\U0001f9bf",
)
_a(
    "scholar_cartographer",
    "scholar",
    "Lyra's Cartographer",
    "Discover 50 sites through Lyra conversations",
    "gold",
    1000,
    30,
    "\U0001f5fa",
)

# ---- COLLECTOR (14) ----
_a(
    "collector_first_card",
    "collector",
    "First Artifact",
    "Own your first card",
    "bronze",
    50,
    10,
    "\U0001f0cf",
)
_a(
    "collector_ten_cards",
    "collector",
    "Budding Collector",
    "Own 10 cards",
    "bronze",
    100,
    15,
    "\U0001f4e6",
)
_a(
    "collector_fifty_cards",
    "collector",
    "Growing Archive",
    "Own 50 cards",
    "silver",
    500,
    25,
    "\U0001f4da",
)
_a(
    "collector_hundred_cards",
    "collector",
    "Centurion's Hoard",
    "Own 100 cards",
    "silver",
    1000,
    30,
    "\U0001f3fa",
    2,
    1,
)
_a(
    "collector_two_fifty",
    "collector",
    "Master Curator",
    "Own 250 cards",
    "gold",
    2000,
    50,
    "\U0001f3db",
    3,
    1,
)
_a(
    "collector_five_hundred",
    "collector",
    "Living Museum",
    "Own 500 cards",
    "platinum",
    3000,
    60,
    "\U0001f3f0",
    4,
    1,
)
_a(
    "collector_first_uncommon",
    "collector",
    "Uncommon Discovery",
    "Own your first Uncommon card",
    "bronze",
    100,
    10,
    "\U0001f535",
)
_a(
    "collector_first_rare",
    "collector",
    "Rare Find",
    "Own your first Rare card",
    "silver",
    250,
    15,
    "\U0001f7e3",
)
_a(
    "collector_first_epic",
    "collector",
    "Epic Excavation",
    "Own your first Epic card",
    "gold",
    500,
    25,
    "\U0001f7e0",
    2,
    1,
)
_a(
    "collector_first_legendary",
    "collector",
    "Legendary Relic",
    "Own your first Legendary card",
    "platinum",
    1500,
    40,
    "\U0001f534",
    3,
    1,
)
_a(
    "collector_all_groups",
    "collector",
    "Complete Catalogue",
    "Own at least one card from every category group",
    "gold",
    1000,
    30,
    "\U0001f4cb",
)
_a(
    "collector_first_star",
    "collector",
    "Stellar Upgrade",
    "Evolve a card to 2 stars",
    "silver",
    250,
    15,
    "\u2b50",
)
_a(
    "collector_five_star",
    "collector",
    "Masterwork",
    "Evolve a card to maximum 5 stars",
    "platinum",
    1500,
    40,
    "\U0001f31f",
)
_a(
    "collector_first_empire",
    "collector",
    "Imperial Standard",
    "Own your first Empire card",
    "bronze",
    200,
    10,
    "\U0001f6a9",
)

# ---- WARRIOR (12) ----
_a(
    "warrior_first_blood",
    "warrior",
    "First Blood",
    "Win your first PvP battle",
    "bronze",
    100,
    15,
    "\u2694\ufe0f",
)
_a(
    "warrior_ten_victories",
    "warrior",
    "Veteran Gladiator",
    "Win 10 PvP battles",
    "bronze",
    250,
    25,
    "\U0001f396",
    1,
    1,
)
_a(
    "warrior_fifty_victories",
    "warrior",
    "Centurion",
    "Win 50 PvP battles",
    "silver",
    1000,
    40,
    "\U0001f6e1",
    2,
    1,
)
_a(
    "warrior_hundred_victories",
    "warrior",
    "Imperator",
    "Win 100 PvP battles",
    "gold",
    2000,
    60,
    "\U0001f451",
    3,
    1,
)
_a(
    "warrior_three_hundred",
    "warrior",
    "Immortal",
    "Win 300 PvP battles",
    "platinum",
    3000,
    75,
    "\U0001f525",
    4,
    1,
)
_a(
    "warrior_streak_three",
    "warrior",
    "Hot Streak",
    "Achieve a 3-win streak",
    "bronze",
    150,
    15,
    "\U0001f525",
)
_a(
    "warrior_streak_seven",
    "warrior",
    "Unstoppable",
    "Achieve a 7-win streak",
    "silver",
    500,
    25,
    "\U0001f4a5",
    1,
    1,
)
_a(
    "warrior_streak_fifteen",
    "warrior",
    "Phalanx Unbroken",
    "Achieve a 15-win streak",
    "gold",
    1000,
    40,
    "\U0001f6e1",
    2,
    1,
)
_a(
    "warrior_streak_thirty",
    "warrior",
    "Alexander's March",
    "Achieve a 30-win streak",
    "platinum",
    2000,
    60,
    "\U0001f3c6",
)
_a(
    "warrior_high_stakes",
    "warrior",
    "Fortune Favors the Bold",
    "Win a staked battle with 1,000+ credits on the line",
    "silver",
    500,
    25,
    "\U0001f4b0",
    1,
    1,
)
_a(
    "warrior_snap_master",
    "warrior",
    "Snap Decision",
    "Use Snap and win the battle",
    "silver",
    500,
    25,
    "\u26a1",
)
_a(
    "warrior_flawless",
    "warrior",
    "Flawless Victory",
    "Win a battle 5-0",
    "gold",
    1000,
    30,
    "\U0001f48e",
)

# ---- ARCHAEOLOGIST (6) ----
_a(
    "archaeologist_first_dig",
    "archaeologist",
    "First Dig",
    "Submit your first site contribution",
    "bronze",
    250,
    20,
    "\u26cf\ufe0f",
    2,
    1,
)
_a(
    "archaeologist_five_digs",
    "archaeologist",
    "Field Worker",
    "Submit 5 site contributions",
    "silver",
    750,
    25,
    "\U0001f9f1",
    2,
    1,
)
_a(
    "archaeologist_twenty_digs",
    "archaeologist",
    "Senior Archaeologist",
    "Submit 20 site contributions",
    "gold",
    1500,
    35,
    "\U0001f3fa",
    3,
    1,
)
_a(
    "archaeologist_first_photo",
    "archaeologist",
    "Photo Evidence",
    "Upload your first site image",
    "bronze",
    250,
    15,
    "\U0001f4f7",
)
_a(
    "archaeologist_ten_photos",
    "archaeologist",
    "Field Photographer",
    "Upload 10 site images",
    "silver",
    500,
    15,
    "\U0001f4f8",
)
_a(
    "archaeologist_patreon",
    "archaeologist",
    "Patron of the Arts",
    "Become a Patreon supporter at any tier",
    "gold",
    1000,
    10,
    "\U0001f49b",
)

# ---- HISTORIAN (10) ----
_a(
    "historian_first_quiz",
    "historian",
    "Pop Quiz",
    "Complete your first quiz session",
    "bronze",
    100,
    15,
    "\u2753",
)
_a(
    "historian_ten_quizzes",
    "historian",
    "Studious",
    "Complete 10 quiz sessions",
    "bronze",
    200,
    20,
    "\U0001f4dd",
    1,
    1,
)
_a(
    "historian_fifty_quizzes",
    "historian",
    "Trivia Master",
    "Complete 50 quiz sessions",
    "silver",
    750,
    30,
    "\U0001f9e0",
    1,
    1,
)
_a(
    "historian_hundred_quizzes",
    "historian",
    "Walking Library",
    "Complete 100 quiz sessions",
    "gold",
    1500,
    40,
    "\U0001f3db",
    2,
    1,
)
_a(
    "historian_first_perfect",
    "historian",
    "Perfection",
    "Score 5/5 on a quiz",
    "bronze",
    200,
    20,
    "\U0001f4af",
    1,
    1,
)
_a(
    "historian_ten_perfects",
    "historian",
    "Consistent Genius",
    "Score 5/5 on 10 quizzes",
    "silver",
    500,
    30,
    "\U0001f4a1",
)
_a(
    "historian_fifty_perfects",
    "historian",
    "Infallible",
    "Score 5/5 on 50 quizzes",
    "gold",
    1500,
    50,
    "\U0001f9d9",
    3,
    1,
)
_a(
    "historian_chronologist",
    "historian",
    "Chronologist",
    "Answer 25 age comparison questions correctly",
    "silver",
    500,
    25,
    "\u23f3",
)
_a(
    "historian_geographer",
    "historian",
    "Ancient Geographer",
    "Answer 25 country questions correctly",
    "silver",
    500,
    25,
    "\U0001f5fa",
)
_a(
    "historian_total_correct",
    "historian",
    "Ten Thousand Answers",
    "Get 250 total correct quiz answers",
    "platinum",
    1250,
    55,
    "\U0001f3c5",
)

# ---- EXPEDITIONER (12) ----
_a(
    "expeditioner_first_step",
    "expeditioner",
    "Into the Unknown",
    "Complete your first expedition stage",
    "bronze",
    100,
    15,
    "\U0001f97e",
)
_a(
    "expeditioner_first_complete",
    "expeditioner",
    "Mission Accomplished",
    "Complete your first full expedition",
    "silver",
    500,
    30,
    "\U0001f3c1",
    1,
    1,
)
_a(
    "expeditioner_three_complete",
    "expeditioner",
    "Seasoned Explorer",
    "Complete 3 different expeditions",
    "silver",
    750,
    30,
    "\U0001f9ed",
    2,
    1,
)
_a(
    "expeditioner_five_complete",
    "expeditioner",
    "Master Explorer",
    "Complete 5 different expeditions",
    "gold",
    1500,
    50,
    "\U0001f30d",
    3,
    1,
)
_a(
    "expeditioner_all_complete",
    "expeditioner",
    "World Conqueror",
    "Complete all 10 expeditions",
    "platinum",
    3000,
    75,
    "\U0001f30f",
    4,
    1,
)
_a(
    "expeditioner_nile",
    "expeditioner",
    "Child of the Nile",
    "Complete the Nile Valley expedition",
    "bronze",
    150,
    10,
    "\U0001f3fa",
)
_a(
    "expeditioner_aegean",
    "expeditioner",
    "Odysseus Returns",
    "Complete the Aegean expedition",
    "bronze",
    150,
    10,
    "\u26f5",
)
_a(
    "expeditioner_mesoamerica",
    "expeditioner",
    "Jaguar's Path",
    "Complete the Mesoamerica expedition",
    "bronze",
    150,
    10,
    "\U0001f406",
)
_a(
    "expeditioner_fertile",
    "expeditioner",
    "Cradle of Civilization",
    "Complete the Fertile Crescent expedition",
    "bronze",
    150,
    10,
    "\U0001f33e",
)
_a(
    "expeditioner_british",
    "expeditioner",
    "Druid's Circle",
    "Complete the British Isles expedition",
    "bronze",
    150,
    10,
    "\U0001faa8",
)
_a(
    "expeditioner_all_empires",
    "expeditioner",
    "Empire Collector",
    "Own all 9 expedition empire cards",
    "gold",
    1000,
    40,
    "\U0001f451",
    2,
    1,
)
_a(
    "expeditioner_speedrun",
    "expeditioner",
    "Blitzkrieg",
    "Complete an expedition within 24 hours",
    "gold",
    500,
    30,
    "\u26a1",
    1,
    1,
)

# ---- PATRON (10) ----
_a(
    "patron_first_login",
    "patron",
    "Welcome, Traveler",
    "Log in for the first time",
    "bronze",
    50,
    5,
    "\U0001f44b",
)
_a(
    "patron_first_daily",
    "patron",
    "Dawn Ritual",
    "Claim your first daily reward",
    "bronze",
    50,
    10,
    "\U0001f305",
)
_a(
    "patron_streak_three",
    "patron",
    "Three-Day Vigil",
    "Maintain a 3-day login streak",
    "bronze",
    100,
    15,
    "\U0001f525",
    1,
    1,
)
_a(
    "patron_streak_seven",
    "patron",
    "Week of Devotion",
    "Maintain a 7-day login streak",
    "silver",
    500,
    25,
    "\U0001f4a7",
    1,
    1,
)
_a(
    "patron_streak_fourteen",
    "patron",
    "Fortnight's Watch",
    "Maintain a 14-day login streak",
    "silver",
    1000,
    30,
    "\U0001f6e1",
    2,
    1,
)
_a(
    "patron_streak_thirty",
    "patron",
    "Eternal Flame",
    "Maintain a 30-day login streak",
    "gold",
    2000,
    50,
    "\U0001f525",
    3,
    1,
)
_a(
    "patron_streak_hundred",
    "patron",
    "Unbreakable",
    "Maintain a 100-day login streak",
    "platinum",
    3000,
    75,
    "\U0001f48e",
)
_a(
    "patron_first_pack",
    "patron",
    "First Purchase",
    "Open your first card pack",
    "bronze",
    100,
    10,
    "\U0001f381",
)
_a(
    "patron_ten_packs",
    "patron",
    "Frequent Buyer",
    "Open 10 card packs",
    "silver",
    500,
    20,
    "\U0001f4e6",
    1,
    1,
)
_a("patron_fifty_packs", "patron", "Pack Rat", "Open 50 card packs", "gold", 1500, 30, "\U0001f4e6")

# ---- CARTOGRAPHER (6) ----
_a(
    "cartographer_measure",
    "cartographer",
    "The Great Measure",
    "Use the measurement tool between two points",
    "bronze",
    100,
    10,
    "\U0001f4cf",
)
_a(
    "cartographer_proximity",
    "cartographer",
    "Proximity Alert",
    "Use proximity search to find nearby sites",
    "bronze",
    100,
    10,
    "\U0001f4e1",
)
_a(
    "cartographer_satellite",
    "cartographer",
    "Eye in the Sky",
    "Enable the satellite map layer",
    "bronze",
    50,
    5,
    "\U0001f6f0",
)
_a(
    "cartographer_layers",
    "cartographer",
    "Layer Cake",
    "Enable 5+ different map layers in one session",
    "silver",
    500,
    25,
    "\U0001f5fa",
    1,
    1,
)
_a(
    "cartographer_sea_level",
    "cartographer",
    "Rising Tides",
    "Adjust the sea level slider for paleoshoreline",
    "bronze",
    100,
    10,
    "\U0001f30a",
    1,
    1,
)
_a(
    "cartographer_trade_routes",
    "cartographer",
    "Silk Road Scholar",
    "Enable the ancient trade routes layer",
    "silver",
    250,
    15,
    "\U0001f42b",
    2,
    1,
)

# ---- CURATOR (10) ----
_a(
    "curator_first_like",
    "curator",
    "Seal of Approval",
    "Like your first site",
    "bronze",
    50,
    10,
    "\u2764\ufe0f",
)
_a(
    "curator_ten_likes",
    "curator",
    "Enthusiast",
    "Like 10 different sites",
    "bronze",
    100,
    15,
    "\U0001f44d",
)
_a(
    "curator_fifty_likes",
    "curator",
    "Connoisseur",
    "Like 50 different sites",
    "silver",
    500,
    25,
    "\U0001f31f",
    1,
    1,
)
_a(
    "curator_two_hundred_likes",
    "curator",
    "Patron of Ruins",
    "Like 200 different sites",
    "gold",
    1500,
    40,
    "\U0001f3db",
    3,
    1,
)
_a(
    "curator_first_bookmark",
    "curator",
    "First Bookmark",
    "Bookmark your first site",
    "bronze",
    50,
    10,
    "\U0001f516",
)
_a(
    "curator_ten_bookmarks",
    "curator",
    "Personal Archive",
    "Bookmark 10 different sites",
    "bronze",
    100,
    15,
    "\U0001f4da",
)
_a(
    "curator_fifty_bookmarks",
    "curator",
    "Obsessive Cataloguer",
    "Bookmark 50 different sites",
    "silver",
    500,
    25,
    "\U0001f4d1",
    1,
    1,
)
_a(
    "curator_two_hundred_bookmarks",
    "curator",
    "Comprehensive Atlas",
    "Bookmark 200 different sites",
    "gold",
    1000,
    30,
    "\U0001f5fa",
)
_a(
    "curator_category_sampler",
    "curator",
    "Cultural Sampler",
    "Like sites from at least 8 different category groups",
    "silver",
    500,
    15,
    "\U0001f3ad",
    1,
    1,
)
_a(
    "curator_country_collector",
    "curator",
    "United Nations",
    "Like sites from at least 30 different countries",
    "gold",
    2000,
    30,
    "\U0001f1fa\U0001f1f3",
    2,
    1,
)


# ---------------------------------------------------------------------------
# Seed function — idempotent upsert
# ---------------------------------------------------------------------------


def seed_achievements(session: Session) -> int:
    """Upsert all 102 achievement definitions into the achievements table.

    Returns the number of rows upserted.
    """
    rows = []
    for aid, a in ACHIEVEMENTS.items():
        rows.append(
            {
                "id": aid,
                "category": a["category"],
                "name": a["name"],
                "description": a["description"],
                "tier": a["tier"],
                "reward_credits": a["reward_credits"],
                "reward_xp": a["reward_xp"],
                "reward_card_tier": a["reward_card_tier"],
                "reward_card_count": a["reward_card_count"],
                "icon": a["icon"],
                "sort_order": a["sort_order"],
                "hidden": a["hidden"],
            }
        )

    if not rows:
        return 0

    stmt = pg_insert(Achievement).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "category": stmt.excluded.category,
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "tier": stmt.excluded.tier,
            "reward_credits": stmt.excluded.reward_credits,
            "reward_xp": stmt.excluded.reward_xp,
            "reward_card_tier": stmt.excluded.reward_card_tier,
            "reward_card_count": stmt.excluded.reward_card_count,
            "icon": stmt.excluded.icon,
            "sort_order": stmt.excluded.sort_order,
            "hidden": stmt.excluded.hidden,
        },
    )
    session.execute(stmt)
    session.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# Event → achievement mapping — which achievements to check per event
# ---------------------------------------------------------------------------

_EVENT_ACHIEVEMENTS: dict[str, list[str]] = {
    "login": [
        "patron_first_login",
    ],
    "site_like": [
        "curator_first_like",
        "curator_ten_likes",
        "curator_fifty_likes",
        "curator_two_hundred_likes",
        "curator_category_sampler",
        "curator_country_collector",
        # Explorer achievements based on interaction count
        "explorer_first_sight",
        "explorer_ten_wonders",
        "explorer_hundred_sites",
        "explorer_five_hundred",
        "explorer_thousand",
        "explorer_continent_hopper",
        "explorer_seven_continents",
        "explorer_time_traveler",
    ],
    "site_bookmark": [
        "curator_first_bookmark",
        "curator_ten_bookmarks",
        "curator_fifty_bookmarks",
        "curator_two_hundred_bookmarks",
        # Explorer achievements based on interaction count
        "explorer_first_sight",
        "explorer_ten_wonders",
        "explorer_hundred_sites",
        "explorer_five_hundred",
        "explorer_thousand",
        "explorer_continent_hopper",
        "explorer_seven_continents",
        "explorer_time_traveler",
    ],
    "daily_claim": [
        "patron_first_daily",
        "patron_streak_three",
        "patron_streak_seven",
        "patron_streak_fourteen",
        "patron_streak_thirty",
        "patron_streak_hundred",
    ],
    "starter_claim": [
        "collector_first_card",
        "collector_ten_cards",
    ],
    "pack_open": [
        "patron_first_pack",
        "patron_ten_packs",
        "patron_fifty_packs",
        "collector_first_card",
        "collector_ten_cards",
        "collector_fifty_cards",
        "collector_hundred_cards",
        "collector_two_fifty",
        "collector_five_hundred",
        "collector_first_uncommon",
        "collector_first_rare",
        "collector_first_epic",
        "collector_first_legendary",
        "collector_all_groups",
        "collector_first_star",
        "collector_five_star",
        "collector_first_empire",
    ],
    "battle_complete": [
        "warrior_first_blood",
        "warrior_ten_victories",
        "warrior_fifty_victories",
        "warrior_hundred_victories",
        "warrior_three_hundred",
        "warrior_streak_three",
        "warrior_streak_seven",
        "warrior_streak_fifteen",
        "warrior_streak_thirty",
        "warrior_high_stakes",
        "warrior_snap_master",
        "warrior_flawless",
    ],
    "quiz_submit": [
        "historian_first_quiz",
        "historian_ten_quizzes",
        "historian_fifty_quizzes",
        "historian_hundred_quizzes",
        "historian_first_perfect",
        "historian_ten_perfects",
        "historian_fifty_perfects",
        "historian_chronologist",
        "historian_geographer",
        "historian_total_correct",
    ],
    "expedition_stage": [
        "expeditioner_first_step",
        "expeditioner_first_complete",
        "expeditioner_three_complete",
        "expeditioner_five_complete",
        "expeditioner_all_complete",
        "expeditioner_nile",
        "expeditioner_aegean",
        "expeditioner_mesoamerica",
        "expeditioner_fertile",
        "expeditioner_british",
        "expeditioner_all_empires",
        "expeditioner_speedrun",
    ],
    "contribution": [
        "archaeologist_first_dig",
        "archaeologist_five_digs",
        "archaeologist_twenty_digs",
    ],
    "lyra_chat": [
        "scholar_first_question",
        "scholar_ten_questions",
        "scholar_fifty_questions",
        "scholar_two_hundred",
        "scholar_five_hundred",
        "scholar_site_context",
        "scholar_news_context",
        "scholar_empire_context",
        "scholar_image_analyst",
        "scholar_big_spender",
        "scholar_polyglot",
        "scholar_time_weaver",
        "scholar_deep_diver",
        "scholar_cartographer",
    ],
    "frontend_event": [
        "explorer_screenshot",
        "explorer_street_view",
        "explorer_offline",
        "explorer_random",
        "cartographer_measure",
        "cartographer_proximity",
        "cartographer_satellite",
        "cartographer_layers",
        "cartographer_sea_level",
        "cartographer_trade_routes",
    ],
    # Retroactive full check — used when loading the achievements page
    "full_check": list(ACHIEVEMENTS.keys()),
}


# ---------------------------------------------------------------------------
# Continent mapping for explorer_continent_hopper / seven_continents
# ---------------------------------------------------------------------------

CONTINENT_MAP: dict[str, str] = {}
_AFRICA = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cameroon",
    "Cape Verde",
    "Central African Republic",
    "Chad",
    "Comoros",
    "Democratic Republic of the Congo",
    "Djibouti",
    "Egypt",
    "Equatorial Guinea",
    "Eritrea",
    "Eswatini",
    "Ethiopia",
    "Gabon",
    "Ghana",
    "Guinea",
    "Guinea-Bissau",
    "Ivory Coast",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Mauritius",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Republic of the Congo",
    "Rwanda",
    "Senegal",
    "Sierra Leone",
    "Somalia",
    "South Africa",
    "South Sudan",
    "Sudan",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "Zambia",
    "Zimbabwe",
]
_ASIA = [
    "Afghanistan",
    "Armenia",
    "Azerbaijan",
    "Bahrain",
    "Bangladesh",
    "Bhutan",
    "Brunei",
    "Cambodia",
    "China",
    "Cyprus",
    "Georgia",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Israel",
    "Japan",
    "Jordan",
    "Kazakhstan",
    "Kuwait",
    "Kyrgyzstan",
    "Laos",
    "Lebanon",
    "Malaysia",
    "Maldives",
    "Mongolia",
    "Myanmar",
    "Nepal",
    "North Korea",
    "Oman",
    "Pakistan",
    "Palestine",
    "Philippines",
    "Qatar",
    "Saudi Arabia",
    "Singapore",
    "South Korea",
    "Sri Lanka",
    "Syria",
    "Taiwan",
    "Tajikistan",
    "Thailand",
    "Timor-Leste",
    "Turkey",
    "T\u00fcrkiye",
    "Turkmenistan",
    "United Arab Emirates",
    "Uzbekistan",
    "Vietnam",
    "Yemen",
]
_EUROPE = [
    "Albania",
    "Andorra",
    "Austria",
    "Belarus",
    "Belgium",
    "Bosnia and Herzegovina",
    "Bulgaria",
    "Croatia",
    "Czech Republic",
    "Denmark",
    "Estonia",
    "Finland",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "Iceland",
    "Ireland",
    "Italy",
    "Kosovo",
    "Latvia",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Malta",
    "Moldova",
    "Monaco",
    "Montenegro",
    "Netherlands",
    "North Macedonia",
    "Norway",
    "Poland",
    "Portugal",
    "Romania",
    "Russia",
    "San Marino",
    "Serbia",
    "Slovakia",
    "Slovenia",
    "Spain",
    "Sweden",
    "Switzerland",
    "Ukraine",
    "United Kingdom",
]
_NORTH_AMERICA = [
    "Antigua and Barbuda",
    "Bahamas",
    "Barbados",
    "Belize",
    "Canada",
    "Costa Rica",
    "Cuba",
    "Dominica",
    "Dominican Republic",
    "El Salvador",
    "Grenada",
    "Guatemala",
    "Haiti",
    "Honduras",
    "Jamaica",
    "Mexico",
    "Nicaragua",
    "Panama",
    "Saint Kitts and Nevis",
    "Saint Lucia",
    "Saint Vincent and the Grenadines",
    "Trinidad and Tobago",
    "United States",
]
_SOUTH_AMERICA = [
    "Argentina",
    "Bolivia",
    "Brazil",
    "Chile",
    "Colombia",
    "Ecuador",
    "Guyana",
    "Paraguay",
    "Peru",
    "Suriname",
    "Uruguay",
    "Venezuela",
]
_OCEANIA = [
    "Australia",
    "Fiji",
    "Kiribati",
    "Marshall Islands",
    "Micronesia",
    "Nauru",
    "New Zealand",
    "Palau",
    "Papua New Guinea",
    "Samoa",
    "Solomon Islands",
    "Tonga",
    "Tuvalu",
    "Vanuatu",
]

for _c in _AFRICA:
    CONTINENT_MAP[_c] = "Africa"
for _c in _ASIA:
    CONTINENT_MAP[_c] = "Asia"
for _c in _EUROPE:
    CONTINENT_MAP[_c] = "Europe"
for _c in _NORTH_AMERICA:
    CONTINENT_MAP[_c] = "North America"
for _c in _SOUTH_AMERICA:
    CONTINENT_MAP[_c] = "South America"
for _c in _OCEANIA:
    CONTINENT_MAP[_c] = "Oceania"


# ---------------------------------------------------------------------------
# Period bucket mapping for explorer_time_traveler
# ---------------------------------------------------------------------------


def _get_period_bucket(period_start: int | None) -> str | None:
    if period_start is None:
        return None
    if period_start < -3000:
        return "Prehistoric"
    if period_start < -1200:
        return "Bronze Age"
    if period_start < -500:
        return "Iron Age"
    if period_start < 500:
        return "Classical"
    return "Medieval"


# ---------------------------------------------------------------------------
# Individual achievement checkers
# ---------------------------------------------------------------------------


def _already_unlocked(session: Session, user_id: uuid.UUID, achievement_id: str) -> bool:
    """Check if achievement is already unlocked (avoids expensive queries)."""
    return session.query(
        session.query(UserAchievement)
        .filter(
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_id == achievement_id,
        )
        .exists()
    ).scalar()


def _check_single(
    session: Session,
    user_id: uuid.UUID,
    aid: str,
    context: dict | None = None,
) -> bool:
    """Check if a single achievement should be unlocked. Returns True if newly met."""
    if _already_unlocked(session, user_id, aid):
        return False

    # --- CURATOR ---
    if aid == "curator_first_like":
        return session.query(SiteLike).filter(SiteLike.user_id == user_id).count() >= 1

    if aid == "curator_ten_likes":
        return session.query(SiteLike).filter(SiteLike.user_id == user_id).count() >= 10

    if aid == "curator_fifty_likes":
        return session.query(SiteLike).filter(SiteLike.user_id == user_id).count() >= 50

    if aid == "curator_two_hundred_likes":
        return session.query(SiteLike).filter(SiteLike.user_id == user_id).count() >= 200

    if aid == "curator_first_bookmark":
        return session.query(SiteBookmark).filter(SiteBookmark.user_id == user_id).count() >= 1

    if aid == "curator_ten_bookmarks":
        return session.query(SiteBookmark).filter(SiteBookmark.user_id == user_id).count() >= 10

    if aid == "curator_fifty_bookmarks":
        return session.query(SiteBookmark).filter(SiteBookmark.user_id == user_id).count() >= 50

    if aid == "curator_two_hundred_bookmarks":
        return session.query(SiteBookmark).filter(SiteBookmark.user_id == user_id).count() >= 200

    if aid == "curator_category_sampler":
        count = session.execute(
            text("""
            SELECT COUNT(DISTINCT cs.category_group)
            FROM site_likes sl
            JOIN card_stats cs ON cs.site_id = sl.site_id
            WHERE sl.user_id = :uid
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (count or 0) >= 8

    if aid == "curator_country_collector":
        count = session.execute(
            text("""
            SELECT COUNT(DISTINCT us.country)
            FROM site_likes sl
            JOIN unified_sites us ON us.id = sl.site_id
            WHERE sl.user_id = :uid AND us.country IS NOT NULL
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (count or 0) >= 30

    # --- EXPLORER (interaction-based) ---
    if aid in (
        "explorer_first_sight",
        "explorer_ten_wonders",
        "explorer_hundred_sites",
        "explorer_five_hundred",
        "explorer_thousand",
    ):
        thresholds = {
            "explorer_first_sight": 1,
            "explorer_ten_wonders": 10,
            "explorer_hundred_sites": 100,
            "explorer_five_hundred": 500,
            "explorer_thousand": 1000,
        }
        # Count distinct sites from likes + bookmarks
        count = session.execute(
            text("""
            SELECT COUNT(*) FROM (
                SELECT site_id FROM site_likes WHERE user_id = :uid
                UNION
                SELECT site_id FROM site_bookmarks WHERE user_id = :uid
            ) combined
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (count or 0) >= thresholds[aid]

    if aid == "explorer_continent_hopper":
        rows = session.execute(
            text("""
            SELECT DISTINCT us.country FROM (
                SELECT site_id FROM site_likes WHERE user_id = :uid
                UNION
                SELECT site_id FROM site_bookmarks WHERE user_id = :uid
            ) combined
            JOIN unified_sites us ON us.id = combined.site_id
            WHERE us.country IS NOT NULL
        """),
            {"uid": str(user_id)},
        ).fetchall()
        continents = {CONTINENT_MAP.get(r[0]) for r in rows if r[0] in CONTINENT_MAP}
        return len(continents) >= 5

    if aid == "explorer_seven_continents":
        rows = session.execute(
            text("""
            SELECT DISTINCT us.country FROM (
                SELECT site_id FROM site_likes WHERE user_id = :uid
                UNION
                SELECT site_id FROM site_bookmarks WHERE user_id = :uid
            ) combined
            JOIN unified_sites us ON us.id = combined.site_id
            WHERE us.country IS NOT NULL
        """),
            {"uid": str(user_id)},
        ).fetchall()
        continents = {CONTINENT_MAP.get(r[0]) for r in rows if r[0] in CONTINENT_MAP}
        return len(continents) >= 6

    if aid == "explorer_time_traveler":
        rows = session.execute(
            text("""
            SELECT DISTINCT us.period_start FROM (
                SELECT site_id FROM site_likes WHERE user_id = :uid
                UNION
                SELECT site_id FROM site_bookmarks WHERE user_id = :uid
            ) combined
            JOIN unified_sites us ON us.id = combined.site_id
            WHERE us.period_start IS NOT NULL
        """),
            {"uid": str(user_id)},
        ).fetchall()
        buckets = {_get_period_bucket(r[0]) for r in rows}
        buckets.discard(None)
        return len(buckets) >= 5

    # --- EXPLORER (frontend events) ---
    if aid in (
        "explorer_screenshot",
        "explorer_street_view",
        "explorer_offline",
        "explorer_random",
    ):
        event_map = {
            "explorer_screenshot": "screenshot_taken",
            "explorer_street_view": "street_view_opened",
            "explorer_offline": "offline_downloaded",
            "explorer_random": "random_site_used",
        }
        if context and context.get("event_type") == event_map[aid]:
            return True
        # Check feature_flags
        ps = session.get(CardPlayerStats, user_id)
        if ps and ps.feature_flags:
            return ps.feature_flags.get(event_map[aid], False)
        return False

    # --- CARTOGRAPHER (frontend events) ---
    if aid in (
        "cartographer_measure",
        "cartographer_proximity",
        "cartographer_satellite",
        "cartographer_layers",
        "cartographer_sea_level",
        "cartographer_trade_routes",
    ):
        event_map = {
            "cartographer_measure": "measurement_used",
            "cartographer_proximity": "proximity_used",
            "cartographer_satellite": "satellite_enabled",
            "cartographer_layers": "layers_enabled",
            "cartographer_sea_level": "sea_level_adjusted",
            "cartographer_trade_routes": "trade_routes_enabled",
        }
        evt = event_map[aid]
        if aid == "cartographer_layers":
            if context and context.get("event_type") == "layers_enabled":
                return (context.get("layer_count", 0) or 0) >= 5
            ps = session.get(CardPlayerStats, user_id)
            if ps and ps.feature_flags:
                return (ps.feature_flags.get("max_layers", 0) or 0) >= 5
            return False

        if context and context.get("event_type") == evt:
            return True
        ps = session.get(CardPlayerStats, user_id)
        if ps and ps.feature_flags:
            return ps.feature_flags.get(evt, False)
        return False

    # --- PATRON ---
    if aid == "patron_first_login":
        return True  # If this check fires, user exists

    if aid == "patron_first_daily":
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.last_daily is not None

    if aid in (
        "patron_streak_three",
        "patron_streak_seven",
        "patron_streak_fourteen",
        "patron_streak_thirty",
        "patron_streak_hundred",
    ):
        thresholds = {
            "patron_streak_three": 3,
            "patron_streak_seven": 7,
            "patron_streak_fourteen": 14,
            "patron_streak_thirty": 30,
            "patron_streak_hundred": 100,
        }
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.daily_streak >= thresholds[aid]

    if aid in ("patron_first_pack", "patron_ten_packs", "patron_fifty_packs"):
        thresholds = {
            "patron_first_pack": 1,
            "patron_ten_packs": 10,
            "patron_fifty_packs": 50,
        }
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.packs_opened >= thresholds[aid]

    # --- COLLECTOR ---
    if aid in (
        "collector_first_card",
        "collector_ten_cards",
        "collector_fifty_cards",
        "collector_hundred_cards",
        "collector_two_fifty",
        "collector_five_hundred",
    ):
        thresholds = {
            "collector_first_card": 1,
            "collector_ten_cards": 10,
            "collector_fifty_cards": 50,
            "collector_hundred_cards": 100,
            "collector_two_fifty": 250,
            "collector_five_hundred": 500,
        }
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.total_cards >= thresholds[aid]

    if aid in (
        "collector_first_uncommon",
        "collector_first_rare",
        "collector_first_epic",
        "collector_first_legendary",
    ):
        tier_map = {
            "collector_first_uncommon": 2,
            "collector_first_rare": 3,
            "collector_first_epic": 4,
            "collector_first_legendary": 5,
        }
        count = (
            session.query(CardCollection)
            .join(CardStats, CardCollection.site_id == CardStats.site_id)
            .filter(
                CardCollection.user_id == user_id,
                CardStats.rarity_tier >= tier_map[aid],
            )
            .count()
        )
        return count >= 1

    if aid == "collector_all_groups":
        count = session.execute(
            text("""
            SELECT COUNT(DISTINCT cs.category_group)
            FROM card_collections cc
            JOIN card_stats cs ON cs.site_id = cc.site_id
            WHERE cc.user_id = :uid
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (count or 0) >= 10

    if aid == "collector_first_star":
        count = (
            session.query(CardCollection)
            .filter(CardCollection.user_id == user_id, CardCollection.star_level >= 2)
            .count()
        )
        return count >= 1

    if aid == "collector_five_star":
        count = (
            session.query(CardCollection)
            .filter(CardCollection.user_id == user_id, CardCollection.star_level >= 5)
            .count()
        )
        return count >= 1

    if aid == "collector_first_empire":
        return (
            session.query(EmpireCollection).filter(EmpireCollection.user_id == user_id).count() >= 1
        )

    # --- WARRIOR ---
    if aid in (
        "warrior_first_blood",
        "warrior_ten_victories",
        "warrior_fifty_victories",
        "warrior_hundred_victories",
        "warrior_three_hundred",
    ):
        thresholds = {
            "warrior_first_blood": 1,
            "warrior_ten_victories": 10,
            "warrior_fifty_victories": 50,
            "warrior_hundred_victories": 100,
            "warrior_three_hundred": 300,
        }
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.wins >= thresholds[aid]

    if aid in (
        "warrior_streak_three",
        "warrior_streak_seven",
        "warrior_streak_fifteen",
        "warrior_streak_thirty",
    ):
        thresholds = {
            "warrior_streak_three": 3,
            "warrior_streak_seven": 7,
            "warrior_streak_fifteen": 15,
            "warrior_streak_thirty": 30,
        }
        ps = session.get(CardPlayerStats, user_id)
        return ps is not None and ps.best_streak >= thresholds[aid]

    if aid == "warrior_high_stakes":
        if context and context.get("is_winner") and context.get("effective_stake", 0) >= 1000:
            return True
        return False

    if aid == "warrior_snap_master":
        if context and context.get("is_winner") and context.get("user_snapped"):
            return True
        return False

    if aid == "warrior_flawless":
        if context and context.get("is_winner") and context.get("winner_score", 0) == 5:
            return True
        return False

    # --- SCHOLAR ---
    if aid in (
        "scholar_first_question",
        "scholar_ten_questions",
        "scholar_fifty_questions",
        "scholar_two_hundred",
        "scholar_five_hundred",
    ):
        thresholds = {
            "scholar_first_question": 1,
            "scholar_ten_questions": 10,
            "scholar_fifty_questions": 50,
            "scholar_two_hundred": 200,
            "scholar_five_hundred": 500,
        }
        count = session.query(TokenUsageLog).filter(TokenUsageLog.user_id == user_id).count()
        return count >= thresholds[aid]

    if aid == "scholar_site_context":
        return context is not None and context.get("context_type") == "site"

    if aid == "scholar_news_context":
        return context is not None and context.get("context_type") == "news"

    if aid == "scholar_empire_context":
        return context is not None and context.get("context_type") == "empire"

    if aid == "scholar_image_analyst":
        return context is not None and context.get("has_images", False)

    if aid == "scholar_big_spender":
        total = session.execute(
            text("""
            SELECT COALESCE(SUM(credits_used), 0) FROM token_usage_logs WHERE user_id = :uid
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (total or 0) >= 1000

    if aid == "scholar_polyglot":
        # Accumulate countries in feature_flags and check threshold
        if not context:
            return False
        ps = session.get(CardPlayerStats, user_id)
        if not ps:
            return False
        flags = ps.feature_flags or {}
        seen = set(flags.get("lyra_countries_seen", []))
        new_countries = context.get("countries_found", [])
        if new_countries:
            seen.update(new_countries)
            flags["lyra_countries_seen"] = list(seen)
            ps.feature_flags = flags
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ps, "feature_flags")
        return len(seen) >= 10

    if aid == "scholar_time_weaver":
        # Accumulate periods in feature_flags and check threshold
        if not context:
            return False
        ps = session.get(CardPlayerStats, user_id)
        if not ps:
            return False
        flags = ps.feature_flags or {}
        seen = set(flags.get("lyra_periods_seen", []))
        new_periods = context.get("periods_found", [])
        if new_periods:
            seen.update(new_periods)
            flags["lyra_periods_seen"] = list(seen)
            ps.feature_flags = flags
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ps, "feature_flags")
        return len(seen) >= 5

    if aid == "scholar_deep_diver":
        if not context:
            return False
        return context.get("history_length", 0) >= 10

    if aid == "scholar_cartographer":
        # Accumulate site IDs in feature_flags and check threshold
        if not context:
            return False
        ps = session.get(CardPlayerStats, user_id)
        if not ps:
            return False
        flags = ps.feature_flags or {}
        seen = set(flags.get("lyra_sites_discovered", []))
        new_sites = context.get("site_ids_found", [])
        if new_sites:
            seen.update(new_sites)
            flags["lyra_sites_discovered"] = list(seen)
            ps.feature_flags = flags
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ps, "feature_flags")
        return len(seen) >= 50

    # --- HISTORIAN ---
    if aid in (
        "historian_first_quiz",
        "historian_ten_quizzes",
        "historian_fifty_quizzes",
        "historian_hundred_quizzes",
    ):
        thresholds = {
            "historian_first_quiz": 1,
            "historian_ten_quizzes": 10,
            "historian_fifty_quizzes": 50,
            "historian_hundred_quizzes": 100,
        }
        count = (
            session.query(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.score.isnot(None))
            .count()
        )
        return count >= thresholds[aid]

    if aid == "historian_first_perfect":
        count = (
            session.query(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.score == 5)
            .count()
        )
        return count >= 1

    if aid == "historian_ten_perfects":
        count = (
            session.query(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.score == 5)
            .count()
        )
        return count >= 10

    if aid == "historian_fifty_perfects":
        count = (
            session.query(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.score == 5)
            .count()
        )
        return count >= 50

    if aid == "historian_chronologist":
        # Count correct age_comparison answers from JSONB
        result = session.execute(
            text("""
            SELECT COUNT(*) FROM (
                SELECT qs.id, q->>'type' as qtype,
                       q->>'correct' as correct_answer,
                       qs.answers_key->(q_idx::int) as user_answer
                FROM quiz_sessions qs,
                     jsonb_array_elements(qs.questions) WITH ORDINALITY arr(q, q_idx)
                WHERE qs.user_id = :uid AND qs.score IS NOT NULL
                  AND q->>'type' = 'age_comparison'
            ) sub
            WHERE sub.correct_answer = trim(both '"' from sub.user_answer::text)
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (result or 0) >= 25

    if aid == "historian_geographer":
        result = session.execute(
            text("""
            SELECT COUNT(*) FROM (
                SELECT qs.id, q->>'type' as qtype,
                       q->>'correct' as correct_answer,
                       qs.answers_key->(q_idx::int) as user_answer
                FROM quiz_sessions qs,
                     jsonb_array_elements(qs.questions) WITH ORDINALITY arr(q, q_idx)
                WHERE qs.user_id = :uid AND qs.score IS NOT NULL
                  AND q->>'type' = 'country'
            ) sub
            WHERE sub.correct_answer = trim(both '"' from sub.user_answer::text)
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (result or 0) >= 25

    if aid == "historian_total_correct":
        total = session.execute(
            text("""
            SELECT COALESCE(SUM(score), 0) FROM quiz_sessions
            WHERE user_id = :uid AND score IS NOT NULL
        """),
            {"uid": str(user_id)},
        ).scalar()
        return (total or 0) >= 250

    # --- EXPEDITIONER ---
    if aid == "expeditioner_first_step":
        count = (
            session.query(ExpeditionProgress)
            .filter(ExpeditionProgress.user_id == user_id, ExpeditionProgress.current_stage >= 1)
            .count()
        )
        return count >= 1

    if aid == "expeditioner_first_complete":
        count = (
            session.query(ExpeditionProgress)
            .filter(ExpeditionProgress.user_id == user_id, ExpeditionProgress.completed.is_(True))
            .count()
        )
        return count >= 1

    if aid == "expeditioner_three_complete":
        count = (
            session.query(ExpeditionProgress)
            .filter(ExpeditionProgress.user_id == user_id, ExpeditionProgress.completed.is_(True))
            .count()
        )
        return count >= 3

    if aid == "expeditioner_five_complete":
        count = (
            session.query(ExpeditionProgress)
            .filter(ExpeditionProgress.user_id == user_id, ExpeditionProgress.completed.is_(True))
            .count()
        )
        return count >= 5

    if aid == "expeditioner_all_complete":
        count = (
            session.query(ExpeditionProgress)
            .filter(ExpeditionProgress.user_id == user_id, ExpeditionProgress.completed.is_(True))
            .count()
        )
        return count >= 10

    if aid in (
        "expeditioner_nile",
        "expeditioner_aegean",
        "expeditioner_mesoamerica",
        "expeditioner_fertile",
        "expeditioner_british",
    ):
        exp_map = {
            "expeditioner_nile": "nile_valley",
            "expeditioner_aegean": "aegean",
            "expeditioner_mesoamerica": "mesoamerica",
            "expeditioner_fertile": "fertile_crescent",
            "expeditioner_british": "british_isles",
        }
        return (
            session.query(ExpeditionProgress)
            .filter(
                ExpeditionProgress.user_id == user_id,
                ExpeditionProgress.expedition_id == exp_map[aid],
                ExpeditionProgress.completed.is_(True),
            )
            .count()
        ) >= 1

    if aid == "expeditioner_all_empires":
        count = session.query(EmpireCollection).filter(EmpireCollection.user_id == user_id).count()
        return count >= 9

    if aid == "expeditioner_speedrun":
        result = session.execute(
            text("""
            SELECT 1 FROM expedition_progress
            WHERE user_id = :uid AND completed = true
              AND completed_at IS NOT NULL AND created_at IS NOT NULL
              AND (completed_at - created_at) < INTERVAL '24 hours'
            LIMIT 1
        """),
            {"uid": str(user_id)},
        ).first()
        return result is not None

    # --- ARCHAEOLOGIST ---
    if aid in ("archaeologist_first_dig", "archaeologist_five_digs", "archaeologist_twenty_digs"):
        thresholds = {
            "archaeologist_first_dig": 1,
            "archaeologist_five_digs": 5,
            "archaeologist_twenty_digs": 20,
        }
        count = session.execute(
            text("""
            SELECT COUNT(*) FROM user_contributions WHERE source = 'user'
        """)
        ).scalar()
        return (count or 0) >= thresholds[aid]

    if aid == "archaeologist_first_photo":
        # Placeholder — image uploads tracked via context
        return context is not None and context.get("has_photo", False)

    if aid == "archaeologist_ten_photos":
        return False  # Placeholder until photo tracking exists

    if aid == "archaeologist_patreon":
        user = session.get(DiscordUser, user_id)
        if not user or not user.roles:
            return False
        patron_roles = {"1083785196861657198", "1083785565398380544", "1083785826586075278"}
        return bool(set(user.roles) & patron_roles)

    return False


# ---------------------------------------------------------------------------
# Main checker — event-driven
# ---------------------------------------------------------------------------


def check_achievements(
    session: Session,
    user_id: uuid.UUID,
    event_type: str,
    context: dict | None = None,
) -> list[dict]:
    """Check achievements relevant to the given event type.

    Returns list of newly unlocked achievement dicts (for frontend toast).
    Uses INSERT ... ON CONFLICT DO NOTHING for race-condition safety.
    """
    achievement_ids = _EVENT_ACHIEVEMENTS.get(event_type, [])
    if not achievement_ids:
        return []

    newly_unlocked = []
    for aid in achievement_ids:
        if aid not in ACHIEVEMENTS:
            continue
        if _check_single(session, user_id, aid, context):
            # Try to insert — ON CONFLICT means another request already unlocked it
            stmt = (
                pg_insert(UserAchievement)
                .values(
                    user_id=user_id,
                    achievement_id=aid,
                )
                .on_conflict_do_nothing(constraint="uq_user_achievement")
            )
            result = session.execute(stmt)
            if result.rowcount > 0:
                a = ACHIEVEMENTS[aid]
                newly_unlocked.append(
                    {
                        "id": aid,
                        "name": a["name"],
                        "description": a["description"],
                        "tier": a["tier"],
                        "icon": a["icon"],
                        "reward_credits": a["reward_credits"],
                        "reward_xp": a["reward_xp"],
                        "reward_card_tier": a["reward_card_tier"],
                        "reward_card_count": a["reward_card_count"],
                    }
                )

    if newly_unlocked:
        session.flush()

    return newly_unlocked


# ---------------------------------------------------------------------------
# Claim reward
# ---------------------------------------------------------------------------


def claim_achievement_reward(
    session: Session,
    user: DiscordUser,
    achievement_id: str,
) -> dict:
    """Grant credits/xp/cards for a claimed achievement.

    Returns dict with reward breakdown.
    Raises ValueError if not unlocked, already claimed, or not found.
    """
    ua = (
        session.query(UserAchievement)
        .filter(
            UserAchievement.user_id == user.id,
            UserAchievement.achievement_id == achievement_id,
        )
        .first()
    )
    if not ua:
        raise ValueError("Achievement not unlocked")
    if ua.claimed:
        raise ValueError("Achievement already claimed")

    a_def = ACHIEVEMENTS.get(achievement_id)
    if not a_def:
        raise ValueError("Unknown achievement")

    # Lock user row
    session.query(DiscordUser).filter(DiscordUser.id == user.id).with_for_update().first()

    # Grant credits
    if a_def["reward_credits"] > 0:
        user.credits += a_def["reward_credits"]
        session.add(
            CreditGrant(
                user_id=user.id,
                amount=a_def["reward_credits"],
                reason=f"achievement_{achievement_id}",
            )
        )

    # Grant XP
    if a_def["reward_xp"] > 0:
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            ps = CardPlayerStats(user_id=user.id)
            session.add(ps)
        ps.xp += a_def["reward_xp"]

    # Grant cards
    card_info = None
    if a_def["reward_card_tier"] and a_def["reward_card_count"] > 0:
        from api.cardgame.packs import _card_to_dict, _pick_card

        owned = {
            r[0]
            for r in session.query(CardCollection.site_id)
            .filter(CardCollection.user_id == user.id)
            .all()
        }
        cards = []
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            ps = CardPlayerStats(user_id=user.id)
            session.add(ps)

        for _ in range(a_def["reward_card_count"]):
            card = _pick_card(session, a_def["reward_card_tier"], owned)
            if card:
                if card.site_id not in owned:
                    session.add(
                        CardCollection(
                            user_id=user.id,
                            site_id=card.site_id,
                            acquired_via=f"achievement_{achievement_id}",
                        )
                    )
                    owned.add(card.site_id)
                    ps.total_cards += 1
                    cards.append(_card_to_dict(session, card))

        if cards:
            card_info = cards

    # Mark claimed
    ua.claimed = True
    ua.claimed_at = datetime.now(UTC)
    session.flush()

    return {
        "credits": a_def["reward_credits"],
        "xp": a_def["reward_xp"],
        "cards": card_info,
        "achievement_id": achievement_id,
    }
