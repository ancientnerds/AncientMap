"""PvE Expedition mode — themed single-player campaigns against NPC decks."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.cardgame.constants import (
    EXPEDITION_COMPLETE_PACK,
    EXPEDITION_COOLDOWN_SECONDS,
    EXPEDITION_STAGES,
    EXPEDITION_WIN_CREDITS,
    PACK_PRICES,
)
from api.cardgame.models import (
    CardDeck,
    CardPlayerStats,
    CardStats,
    ExpeditionProgress,
)
from pipeline.database import CreditGrant, DiscordUser

# ---------------------------------------------------------------------------
# Expedition definitions — themed by region
# ---------------------------------------------------------------------------

EXPEDITIONS: dict[str, dict] = {
    "nile_valley": {
        "name": "The Nile Valley",
        "description": "Journey along the Nile from the pyramids of Giza to the temples of Abu Simbel.",
        "countries": ["Egypt", "Sudan"],
        "lore": [
            "The Nile Valley was the cradle of Egyptian civilization, sustaining agriculture for millennia.",
            "Memphis served as the capital of ancient Egypt for much of its history.",
            "The Valley of the Kings contains the tombs of pharaohs from the New Kingdom.",
            "Nubian civilizations along the upper Nile had their own pyramids and temples.",
            "Abu Simbel was carved directly into rock cliffs by Ramesses II.",
        ],
    },
    "aegean": {
        "name": "The Aegean World",
        "description": "Explore the birthplace of Western civilization across Greece and Turkey.",
        "countries": ["Greece", "Turkey", "Türkiye"],
        "lore": [
            "Minoan Crete was home to Europe's first advanced civilization.",
            "The Mycenaeans built massive fortified palaces across the Peloponnese.",
            "Classical Athens became the world's first democracy in 508 BCE.",
            "The Oracle at Delphi was considered the center of the world by the ancient Greeks.",
            "Ephesus was one of the largest cities of the Roman Empire.",
        ],
    },
    "mesoamerica": {
        "name": "Mesoamerican Empires",
        "description": "Discover the Maya, Aztec, and Zapotec civilizations of Central America.",
        "countries": ["Mexico", "Guatemala", "Honduras", "Belize"],
        "lore": [
            "The Maya developed one of the most sophisticated writing systems in the ancient world.",
            "Teotihuacan's Pyramid of the Sun is one of the largest structures in the Western Hemisphere.",
            "Monte Alban was the Zapotec capital, built atop a flattened mountain.",
            "The Maya calendar was more accurate than the European Julian calendar.",
            "Chichen Itza's El Castillo aligns with the equinox, casting a serpent shadow.",
        ],
    },
    "fertile_crescent": {
        "name": "The Fertile Crescent",
        "description": "Visit where humanity first built cities, from Mesopotamia to the Levant.",
        "countries": ["Iraq", "Syria", "Iran", "Lebanon", "Jordan", "Israel", "Palestine"],
        "lore": [
            "Uruk may have been the world's first true city, home to 80,000 people by 2900 BCE.",
            "The Code of Hammurabi is one of the oldest deciphered legal codes.",
            "Persepolis was the ceremonial capital of the Achaemenid Empire.",
            "Petra was carved from red sandstone by the Nabataeans as a trading hub.",
            "Gobekli Tepe predates pottery, metalworking, and even agriculture.",
        ],
    },
    "british_isles": {
        "name": "Stones of Britain",
        "description": "From Stonehenge to Skara Brae, the megalithic mysteries of the British Isles.",
        "countries": ["United Kingdom", "Ireland"],
        "lore": [
            "Stonehenge was built in stages over 1,500 years starting around 3000 BCE.",
            "Skara Brae in Orkney is older than Stonehenge and the Egyptian pyramids.",
            "Newgrange's passage tomb perfectly aligns with the winter solstice sunrise.",
            "The Avebury stone circle is the largest in Britain, enclosing an entire village.",
            "Hadrian's Wall marked the northern limit of the Roman Empire for centuries.",
        ],
    },
    "indus_valley": {
        "name": "The Indus Enigma",
        "description": "Unravel the mysteries of the Indus Valley civilization and ancient India.",
        "countries": ["India", "Pakistan"],
        "lore": [
            "Mohenjo-daro had advanced urban planning with grid streets and indoor plumbing.",
            "The Indus script remains undeciphered — one of archaeology's great puzzles.",
            "Harappa's granary suggests a centralized economy existed 4,500 years ago.",
            "The Great Bath at Mohenjo-daro may be the world's first public pool.",
            "The Indus civilization was larger than contemporary Egypt and Mesopotamia combined.",
        ],
    },
    "east_asia": {
        "name": "Dynasties of the East",
        "description": "From the Terracotta Army to the Great Wall — the ancient empires of East Asia.",
        "countries": ["China", "Japan", "South Korea", "Mongolia"],
        "lore": [
            "The Terracotta Army guards Qin Shi Huang's tomb with 8,000 unique warriors.",
            "The Great Wall was built over centuries by multiple dynasties.",
            "Japan's Jomon pottery is among the oldest in the world, dating to 14,000 BCE.",
            "Chang'an (Xi'an) was the eastern terminus of the Silk Road.",
            "Korea's dolmen culture left behind over 30,000 megalithic tombs.",
        ],
    },
    "sub_saharan": {
        "name": "African Kingdoms",
        "description": "The great civilizations of Sub-Saharan Africa, from Aksum to Great Zimbabwe.",
        "countries": ["Ethiopia", "Zimbabwe", "Mali", "Nigeria", "Tanzania", "Kenya", "Ghana", "South Africa"],
        "lore": [
            "Aksum was one of the four great powers of the ancient world alongside Rome.",
            "Great Zimbabwe's stone walls were built without mortar and still stand today.",
            "Timbuktu was a center of Islamic learning with libraries of 700,000 manuscripts.",
            "The Nok culture of Nigeria produced some of Africa's earliest terracotta sculptures.",
            "Lalibela's churches were carved from solid rock in the 12th century.",
        ],
    },
    "andes": {
        "name": "Peaks of the Andes",
        "description": "High-altitude civilizations from the Inca to the Nazca of South America.",
        "countries": ["Peru", "Bolivia", "Colombia", "Ecuador", "Chile"],
        "lore": [
            "Machu Picchu sits at 2,430m elevation, built without wheels or iron tools.",
            "The Nazca Lines can only be fully appreciated from the air — but were made 2,000 years ago.",
            "Tiwanaku near Lake Titicaca was a spiritual center for centuries before the Inca.",
            "The Inca built 40,000 km of roads across extreme mountain terrain.",
            "Caral-Supe is the oldest known civilization in the Americas, dating to 3000 BCE.",
        ],
    },
    "mediterranean": {
        "name": "Mare Nostrum",
        "description": "Rome's lake — the civilizations that ringed the Mediterranean Sea.",
        "countries": [
            "Italy", "Tunisia", "Libya", "Spain", "France",
            "Croatia", "Algeria", "Morocco", "Malta", "Cyprus",
        ],
        "lore": [
            "Carthage was Rome's greatest rival until its complete destruction in 146 BCE.",
            "Pompeii was perfectly preserved under volcanic ash from Vesuvius in 79 CE.",
            "The Colosseum could hold 50,000 spectators and had a retractable sunshade.",
            "Leptis Magna in Libya was one of the most beautiful cities of the Roman Empire.",
            "Malta's Megalithic Temples are older than Stonehenge and the Egyptian pyramids.",
        ],
    },
}


def _build_npc_deck(
    session: Session,
    countries: list[str],
    stage: int,
) -> list[CardStats]:
    """Build an NPC deck from cards matching the expedition's countries.

    Higher stages use higher-rarity cards.
    """
    # Stage 1-2: tier 1+, stage 3-4: tier 2+, stage 5: tier 3+
    min_tier = min(1 + (stage - 1) // 2, 3)

    regional_cards = (
        session.query(CardStats)
        .filter(
            CardStats.civilization.in_(countries),
            CardStats.rarity_tier >= min_tier,
        )
        .order_by(func.random())
        .limit(10)
        .all()
    )

    if len(regional_cards) < 5:
        existing_ids = {c.site_id for c in regional_cards}
        fill = (
            session.query(CardStats)
            .filter(
                CardStats.rarity_tier >= min_tier,
                CardStats.site_id.notin_(existing_ids) if existing_ids else True,
            )
            .order_by(func.random())
            .limit(10 - len(regional_cards))
            .all()
        )
        regional_cards.extend(fill)

    return regional_cards


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_available_expeditions() -> list[dict]:
    """List all expedition definitions."""
    return [
        {
            "id": eid,
            "name": exp["name"],
            "description": exp["description"],
            "stages": EXPEDITION_STAGES,
        }
        for eid, exp in EXPEDITIONS.items()
    ]


def get_expedition_progress(session: Session, user_id) -> list[dict]:
    """Get user's progress on all expeditions."""
    rows = (
        session.query(ExpeditionProgress)
        .filter(ExpeditionProgress.user_id == user_id)
        .all()
    )
    progress_map = {r.expedition_id: r for r in rows}

    result = []
    for eid, exp in EXPEDITIONS.items():
        p = progress_map.get(eid)
        result.append({
            "expedition_id": eid,
            "name": exp["name"],
            "current_stage": p.current_stage if p else 0,
            "completed": p.completed if p else False,
            "started_at": p.created_at.isoformat() if p and p.created_at else None,
        })
    return result


def play_expedition_stage(
    session: Session,
    user: DiscordUser,
    expedition_id: str,
) -> dict:
    """Play the next stage of an expedition.

    Returns battle result, lore text, and rewards.
    """
    if expedition_id not in EXPEDITIONS:
        raise ValueError(f"Unknown expedition: {expedition_id}")

    # Lock user row to prevent concurrent credit manipulation
    session.query(DiscordUser).filter(DiscordUser.id == user.id).with_for_update().first()

    exp = EXPEDITIONS[expedition_id]

    progress = (
        session.query(ExpeditionProgress)
        .filter(
            ExpeditionProgress.user_id == user.id,
            ExpeditionProgress.expedition_id == expedition_id,
        )
        .first()
    )
    if not progress:
        progress = ExpeditionProgress(
            user_id=user.id,
            expedition_id=expedition_id,
            current_stage=0,
        )
        session.add(progress)
        session.flush()

    if progress.completed:
        raise ValueError("Expedition already completed")

    # Enforce cooldown between stage attempts
    if progress.last_stage_played_at:
        last = progress.last_stage_played_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - last).total_seconds()
        if elapsed < EXPEDITION_COOLDOWN_SECONDS:
            remaining = int(EXPEDITION_COOLDOWN_SECONDS - elapsed)
            raise ValueError(f"Cooldown active — wait {remaining}s before next stage")

    stage = progress.current_stage + 1
    if stage > EXPEDITION_STAGES:
        raise ValueError("Expedition already completed")

    # Load player's active deck
    deck_row = (
        session.query(CardDeck)
        .filter(CardDeck.user_id == user.id, CardDeck.is_active)
        .first()
    )
    if not deck_row or len(deck_row.card_ids) < 5:
        raise ValueError("You need an active deck with at least 5 cards")

    player_cards = [
        session.get(CardStats, uuid.UUID(cid))
        for cid in deck_row.card_ids
    ]
    player_cards = [c for c in player_cards if c is not None]

    npc_deck = _build_npc_deck(session, exp["countries"], stage)

    from api.cardgame.battle import resolve_battle
    battle_seed = f"expedition_{expedition_id}_{user.id}_{stage}_{datetime.now(UTC).isoformat()}"
    result = resolve_battle(player_cards, npc_deck, battle_seed)

    progress.last_stage_played_at = datetime.now(UTC)
    player_won = result["winner"] == "challenger"

    lore = exp["lore"][stage - 1] if stage <= len(exp["lore"]) else ""
    rewards = {"credits": 0, "xp": 0, "pack": None, "pack_cards": None}

    if player_won:
        progress.current_stage = stage

        rewards["credits"] = EXPEDITION_WIN_CREDITS
        user.credits += EXPEDITION_WIN_CREDITS
        session.add(CreditGrant(
            user_id=user.id,
            amount=EXPEDITION_WIN_CREDITS,
            reason=f"expedition_{expedition_id}_stage_{stage}",
        ))

        rewards["xp"] = 15
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            ps = CardPlayerStats(user_id=user.id)
            session.add(ps)
        ps.xp += 15

        if stage >= EXPEDITION_STAGES:
            progress.completed = True
            progress.completed_at = datetime.now(UTC)
            rewards["pack"] = EXPEDITION_COMPLETE_PACK

            # Award completion pack (give credits then open so audit trail is clean)
            from api.cardgame.packs import open_pack
            pack_cost = PACK_PRICES[EXPEDITION_COMPLETE_PACK]["cost"]
            user.credits += pack_cost
            session.add(CreditGrant(
                user_id=user.id,
                amount=pack_cost,
                reason=f"expedition_{expedition_id}_completion_pack",
            ))
            rewards["pack_cards"] = open_pack(session, user, EXPEDITION_COMPLETE_PACK)

    return {
        "expedition": exp["name"],
        "stage": stage,
        "total_stages": EXPEDITION_STAGES,
        "battle_result": result,
        "player_won": player_won,
        "lore": lore,
        "rewards": rewards,
        "completed": progress.completed,
    }
