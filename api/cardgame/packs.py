"""Pack opening logic + rarity rolls + card evolution."""

import random
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.cardgame.constants import PACK_PRICES, RARITY_WEIGHTS, STAR_LEVELS
from api.cardgame.models import (
    CardCollection,
    CardPackLog,
    CardPlayerStats,
    CardStats,
)
from pipeline.database import CreditGrant, DiscordUser


class InsufficientCreditsError(Exception):
    pass


class InvalidPackTypeError(Exception):
    pass


def _weighted_rarity_roll(min_tier: int) -> int:
    """Roll a rarity tier with weighted probability, respecting minimum."""
    eligible = {t: w for t, w in RARITY_WEIGHTS.items() if t >= min_tier}
    tiers = list(eligible.keys())
    weights = list(eligible.values())
    return random.choices(tiers, weights=weights, k=1)[0]  # noqa: S311 — game logic


def _pick_card(session: Session, tier: int, owned_site_ids: set[uuid.UUID]) -> CardStats | None:
    """Pick a random card of the given rarity tier, preferring unowned cards.

    Tries unowned first, falls back to any card of the tier (for evolution).
    """
    # Try to find an unowned card
    unowned = (
        session.query(CardStats)
        .filter(
            CardStats.rarity_tier == tier,
            CardStats.site_id.notin_(owned_site_ids) if owned_site_ids else True,
        )
        .order_by(func.random())
        .first()
    )
    if unowned:
        return unowned

    # All cards of this tier are owned — return any (will become evolution XP)
    return (
        session.query(CardStats)
        .filter(CardStats.rarity_tier == tier)
        .order_by(func.random())
        .first()
    )


def _evolve_card(session: Session, user_id: uuid.UUID, site_id: uuid.UUID) -> dict | None:
    """Add 1 XP to an existing card, check for star upgrade.

    Returns evolution info dict or None.
    """
    coll = (
        session.query(CardCollection)
        .filter(CardCollection.user_id == user_id, CardCollection.site_id == site_id)
        .first()
    )
    if not coll:
        return None

    coll.card_xp += 1
    old_star = coll.star_level

    # Check for star upgrade (check highest star first)
    for star in sorted(STAR_LEVELS.keys(), reverse=True):
        if star > coll.star_level and coll.card_xp >= STAR_LEVELS[star]["duplicates_needed"]:
            coll.star_level = star
            break

    return {
        "star_level": coll.star_level,
        "card_xp": coll.card_xp,
        "evolved": coll.star_level > old_star,
        "new_star": coll.star_level if coll.star_level > old_star else None,
    }


def open_pack(
    session: Session,
    user: DiscordUser,
    pack_type: str,
) -> list[dict]:
    """Open a card pack: deduct credits, roll cards, add to collection.

    Returns list of card dicts with stats and site info.
    Raises InsufficientCreditsError or InvalidPackTypeError.
    """
    pack = PACK_PRICES.get(pack_type)
    if not pack:
        raise InvalidPackTypeError(f"Unknown pack type: {pack_type}")

    # Lock user row to prevent concurrent credit manipulation
    (
        session.query(DiscordUser)
        .filter(DiscordUser.id == user.id)
        .populate_existing()
        .with_for_update()
        .first()
    )

    cost = pack["cost"]
    if user.credits < cost:
        raise InsufficientCreditsError(
            f"Need {cost} credits for {pack_type} pack, have {user.credits}"
        )

    # Deduct credits
    user.credits -= cost

    # Audit trail
    session.add(
        CreditGrant(
            user_id=user.id,
            amount=-cost,
            reason=f"card_pack_{pack_type}",
        )
    )

    # Get user's existing collection
    owned_ids = {
        row[0]
        for row in session.query(CardCollection.site_id)
        .filter(CardCollection.user_id == user.id)
        .all()
    }

    # Roll cards
    guarantees = pack["guarantees"]
    cards_out = []

    for min_tier in guarantees:
        tier = _weighted_rarity_roll(min_tier)
        card = _pick_card(session, tier, owned_ids)

        if card is None:
            raise RuntimeError(f"No cards exist at rarity tier {tier} — pack roll cannot proceed")

        card_dict = _card_to_dict(session, card)

        if card.site_id in owned_ids:
            # Duplicate → evolution XP instead of wasted
            evo = _evolve_card(session, user.id, card.site_id)
            if evo:
                card_dict["duplicate"] = True
                card_dict["star_level"] = evo["star_level"]
                card_dict["card_xp"] = evo["card_xp"]
                card_dict["evolved"] = evo["evolved"]
        else:
            # New card
            owned_ids.add(card.site_id)
            session.add(
                CardCollection(
                    user_id=user.id,
                    site_id=card.site_id,
                    acquired_via=f"pack_{pack_type}",
                )
            )
            card_dict["duplicate"] = False
            card_dict["star_level"] = 1
            card_dict["card_xp"] = 0
            card_dict["evolved"] = False

        cards_out.append(card_dict)

    # Log the pack opening
    session.add(
        CardPackLog(
            user_id=user.id,
            pack_type=pack_type,
            credits_spent=cost,
            cards_received=[str(c["site_id"]) for c in cards_out],
        )
    )

    # Update player stats (only count genuinely new cards)
    new_card_count = sum(1 for c in cards_out if not c.get("duplicate"))
    player_stats = session.get(CardPlayerStats, user.id)
    if player_stats:
        player_stats.total_cards += new_card_count
        player_stats.packs_opened += 1
    else:
        session.add(
            CardPlayerStats(
                user_id=user.id,
                total_cards=new_card_count,
                packs_opened=1,
            )
        )

    return cards_out


def _card_to_dict(session: Session, card: CardStats, user_id: uuid.UUID | None = None) -> dict:
    """Convert a CardStats row to a response dict including site info.

    If user_id is provided, includes star_level and card_xp from their collection.
    """
    from pipeline.database import UnifiedSite

    site = session.get(UnifiedSite, card.site_id)
    from api.cardgame.constants import RARITY_NAMES, STAR_LEVELS

    d = {
        "site_id": str(card.site_id),
        "name": site.name if site else "Unknown",
        "country": site.country if site else None,
        "period_name": site.period_name if site else None,
        "period_start": site.period_start if site else None,
        "thumbnail_url": site.thumbnail_url if site else None,
        "site_type": site.site_type if site else None,
        "antiquity": card.antiquity,
        "fortification": card.fortification,
        "cultural_influence": card.cultural_influence,
        "mystery": card.mystery,
        "legacy": card.legacy,
        "total_power": card.total_power,
        "rarity_tier": card.rarity_tier,
        "rarity_name": RARITY_NAMES.get(card.rarity_tier, "Common"),
        "category_group": card.category_group,
    }

    # Include evolution info if user_id provided
    if user_id:
        coll = (
            session.query(CardCollection)
            .filter(CardCollection.user_id == user_id, CardCollection.site_id == card.site_id)
            .first()
        )
        if coll:
            d["star_level"] = coll.star_level
            d["card_xp"] = coll.card_xp
            # Star bonus: +1 to highest stat at star 2, +1 to second at star 3
            if coll.star_level >= 2:
                stats = {
                    "antiquity": card.antiquity,
                    "fortification": card.fortification,
                    "cultural_influence": card.cultural_influence,
                    "mystery": card.mystery,
                    "legacy": card.legacy,
                }
                sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
                d[sorted_stats[0][0]] += STAR_LEVELS[2]["stat_bonus"]
                d["total_power"] += STAR_LEVELS[2]["stat_bonus"]
                if coll.star_level >= 3:
                    d[sorted_stats[1][0]] += STAR_LEVELS[3]["stat_bonus"]
                    d["total_power"] += STAR_LEVELS[3]["stat_bonus"]

    return d
