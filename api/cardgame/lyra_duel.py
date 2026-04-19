"""Lyra NPC duel mode — scaled difficulty practice against Lyra."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.cardgame.constants import LYRA_TIERS, PACK_PRICES
from api.cardgame.models import CardDeck, CardPlayerStats, CardStats, LyraBattle
from api.cardgame.synergies import describe_synergies
from pipeline.database import CreditGrant, DiscordUser


def _build_lyra_deck(session: Session, tier: int) -> list[CardStats]:
    """Build Lyra's deck for the given tier.

    Themed to scholarly, well-documented sites — the kind of knowledge
    Lyra would have memorized. Higher tiers pull from rarer, more
    impressive sites.
    """
    cfg = LYRA_TIERS[tier]

    # Prefer cards with high cultural_influence (well-documented sites)
    # Tiebreak by antiquity so Lyra gets impressive ancient sites
    cards = (
        session.query(CardStats)
        .filter(
            CardStats.rarity_tier >= cfg["min_tier"],
            CardStats.rarity_tier <= cfg["max_tier"],
        )
        .order_by(CardStats.cultural_influence.desc(), CardStats.antiquity.desc())
        .limit(10)
        .all()
    )

    # If fewer than 5 cards exist in range, fall back to any cards
    if len(cards) < 5:
        cards = (
            session.query(CardStats)
            .filter(
                CardStats.rarity_tier >= cfg["min_tier"],
            )
            .order_by(CardStats.cultural_influence.desc())
            .limit(10)
            .all()
        )

    return list(cards)


def _get_player_deck(
    session: Session, user: DiscordUser
) -> tuple[list[CardStats], CardDeck | None]:
    """Fetch the player's active deck, or their best available deck."""
    deck_row = (
        session.query(CardDeck)
        .filter(
            CardDeck.user_id == user.id,
            CardDeck.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not deck_row:
        # Fall back to the most recent deck
        deck_row = (
            session.query(CardDeck)
            .filter(CardDeck.user_id == user.id)
            .order_by(CardDeck.created_at.desc())
            .first()
        )

    if not deck_row:
        return [], None

    # Load deck cards
    from api.cardgame.models import CardCollection

    card_rows = (
        session.query(CardCollection, CardStats)
        .join(CardStats, CardCollection.site_id == CardStats.site_id)
        .filter(CardCollection.user_id == user.id)
        .all()
    )

    deck_card_ids = set(deck_row.card_ids) if deck_row.card_ids else set()
    deck_cards = [cs for cs, _ in card_rows if str(cs.site_id) in deck_card_ids]

    return deck_cards[:10], deck_row


def can_challenge_lyra(session: Session, user_id: uuid.UUID, tier: int) -> tuple[bool, str | None]:
    """Check if a player can challenge Lyra at the given tier today.

    Returns (can_challenge, last_result). last_result is None/'win'/'loss'.
    """
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        session.query(LyraBattle)
        .filter(
            LyraBattle.user_id == user_id,
            LyraBattle.lyra_tier == tier,
            LyraBattle.played_at >= today_start,
        )
        .first()
    )
    if existing:
        return False, existing.result
    return True, None


def get_lyra_status(session: Session, user_id: uuid.UUID) -> dict[int, dict]:
    """Return player's daily challenge status for all 4 Lyra tiers."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    battles = (
        session.query(LyraBattle)
        .filter(
            LyraBattle.user_id == user_id,
            LyraBattle.played_at >= today_start,
        )
        .all()
    )
    by_tier = {b.lyra_tier: b for b in battles}
    return {
        tier: {
            "status": by_tier[tier].result if tier in by_tier else "available",
            "can_challenge": tier not in by_tier,
        }
        for tier in LYRA_TIERS
    }


def resolve_lyra_duel(
    session: Session,
    user: DiscordUser,
    tier: int,
) -> dict:
    """Run a Lyra duel for the given tier.

    Returns a full result dict with battle details, rewards, and status.
    """
    cfg = LYRA_TIERS[tier]

    # Get player's deck
    player_cards, deck_row = _get_player_deck(session, user)
    if len(player_cards) < 5:
        raise ValueError("You need at least 5 cards in your active deck to challenge Lyra.")

    # Build Lyra's deck
    lyra_deck = _build_lyra_deck(session, tier)
    if len(lyra_deck) < 5:
        raise ValueError(
            f"Lyra's deck is not ready yet (only {len(lyra_deck)} cards available). Try again later."
        )

    # Resolve battle using the existing engine
    battle_seed = f"lyra_{tier}_{user.id}_{datetime.now(UTC).isoformat()}"
    from api.cardgame.battle import resolve_battle

    player_commander = deck_row.commander_empire_id if deck_row else None
    result = resolve_battle(
        player_cards,
        lyra_deck,
        battle_seed,
        challenger_commander=player_commander,
    )

    player_won = result["winner"] == "challenger"
    player_score = result["challenger_wins"]
    lyra_score = result["defender_wins"]

    # Calculate rewards
    credits_earned = cfg["win_credits"] if player_won else cfg["loss_credits"]
    xp_earned = cfg["win_xp"] if player_won else cfg["loss_xp"]
    pack_reward = cfg["win_pack"] if player_won else None

    # Credit grant
    user.credits += credits_earned
    session.add(
        CreditGrant(
            user_id=user.id,
            amount=credits_earned,
            reason=f"lyra_duel_tier_{tier}_{'win' if player_won else 'loss'}",
        )
    )

    # XP
    ps = session.get(CardPlayerStats, user.id)
    if not ps:
        ps = CardPlayerStats(user_id=user.id)
        session.add(ps)
    ps.xp += xp_earned

    # Pack reward (win at tier 3+)
    pack_cards = None
    if pack_reward:
        from api.cardgame.packs import open_pack

        pack_cost = PACK_PRICES[pack_reward]["cost"]
        user.credits += pack_cost
        session.add(
            CreditGrant(
                user_id=user.id,
                amount=pack_cost,
                reason=f"lyra_duel_tier_{tier}_pack_reward",
            )
        )
        pack_cards = open_pack(session, user, pack_reward)

    # Record battle
    battle = LyraBattle(
        user_id=user.id,
        lyra_tier=tier,
        result="win" if player_won else "loss",
        player_score=player_score,
        lyra_score=lyra_score,
        credits_earned=credits_earned,
        xp_earned=xp_earned,
        pack_reward=pack_reward,
    )
    session.add(battle)

    return {
        "tier": tier,
        "lyra_name": cfg["name"],
        "player_won": player_won,
        "player_score": player_score,
        "lyra_score": lyra_score,
        "credits_earned": credits_earned,
        "xp_earned": xp_earned,
        "pack_reward": pack_reward,
        "pack_cards": pack_cards,
        "player_synergies": result["challenger_synergies"],
        "lyra_synergies": result["defender_synergies"],
        "rounds": result["rounds"],
    }
