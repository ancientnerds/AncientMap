"""Daily rewards, streak tracking, and contribution reward stubs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.cardgame.constants import (
    DAILY_CREDITS,
    STARTER_DECK_SIZE,
    STREAK_REWARDS,
)
from api.cardgame.models import (
    CardCollection,
    CardPlayerStats,
    CardStats,
)
from pipeline.database import CreditGrant, DiscordUser


class AlreadyClaimedError(Exception):
    pass


class AlreadyHasStarterError(Exception):
    pass


def claim_daily(session: Session, user: DiscordUser) -> dict:
    """Claim daily reward: 1 Common card + credits + streak tracking.

    Returns dict with reward info.
    Raises AlreadyClaimedError if already claimed today.
    """
    now = datetime.now(UTC)

    # Lock user row to prevent concurrent credit manipulation
    session.query(DiscordUser).filter(DiscordUser.id == user.id).with_for_update().first()

    ps = (
        session.query(CardPlayerStats)
        .filter(CardPlayerStats.user_id == user.id)
        .with_for_update()
        .first()
    )
    if not ps:
        ps = CardPlayerStats(user_id=user.id)
        session.add(ps)
        session.flush()

    # Check if already claimed today
    if ps.last_daily:
        last = ps.last_daily.replace(tzinfo=UTC) if ps.last_daily.tzinfo is None else ps.last_daily
        if last.date() == now.date():
            raise AlreadyClaimedError("Daily reward already claimed today")

        # Check streak continuity (claimed yesterday)
        yesterday = (now - timedelta(days=1)).date()
        if last.date() == yesterday:
            ps.daily_streak += 1
        else:
            ps.daily_streak = 1
    else:
        ps.daily_streak = 1

    ps.last_daily = now

    # Give credits
    user.credits += DAILY_CREDITS
    session.add(CreditGrant(
        user_id=user.id,
        amount=DAILY_CREDITS,
        reason="card_daily",
    ))

    # Give 1 Common card
    owned = {
        r[0] for r in
        session.query(CardCollection.site_id)
        .filter(CardCollection.user_id == user.id)
        .all()
    }
    from api.cardgame.packs import _pick_card
    card = _pick_card(session, 1, owned)
    card_info = None
    if card:
        session.add(CardCollection(
            user_id=user.id,
            site_id=card.site_id,
            acquired_via="daily",
        ))
        ps.total_cards += 1
        from api.cardgame.packs import _card_to_dict
        card_info = _card_to_dict(session, card)

    # Check streak rewards (best match wins — check from highest threshold down)
    streak_reward = None
    for day_threshold, reward_type, reward_value, repeating in reversed(STREAK_REWARDS):
        triggered = (
            (ps.daily_streak % day_threshold == 0) if repeating
            else (ps.daily_streak == day_threshold)
        )
        if triggered:
            streak_reward = {"type": reward_type, "value": reward_value, "streak": day_threshold}
            # Apply bonus credits from streak reward
            if reward_type == "credits":
                bonus = int(reward_value)
                user.credits += bonus
                session.add(CreditGrant(
                    user_id=user.id,
                    amount=bonus,
                    reason=f"streak_bonus_{day_threshold}d",
                ))
            break

    return {
        "credits": DAILY_CREDITS,
        "card": card_info,
        "daily_streak": ps.daily_streak,
        "streak_reward": streak_reward,
    }


def claim_starter_deck(session: Session, user: DiscordUser) -> list[dict]:
    """Give the user 10 starter cards across different categories.

    Raises AlreadyHasStarterError if user already has cards.
    """
    # Lock player stats row to prevent concurrent starter claims
    ps = (
        session.query(CardPlayerStats)
        .filter(CardPlayerStats.user_id == user.id)
        .with_for_update()
        .first()
    )
    if ps and ps.total_cards > 0:
        raise AlreadyHasStarterError("You already have cards")

    if not ps:
        ps = CardPlayerStats(user_id=user.id)
        session.add(ps)

    # Pick 10 well-distributed cards: prefer diverse groups and low tiers
    # Get one card per category group, then fill remaining slots
    groups_seen: set[str] = set()
    starter_cards: list[CardStats] = []

    # First: one card per group (Common/Uncommon)
    for tier in [1, 2]:
        cards = (
            session.query(CardStats)
            .filter(CardStats.rarity_tier == tier)
            .order_by(func.random())
            .limit(50)
            .all()
        )
        for card in cards:
            if card.category_group not in groups_seen and len(starter_cards) < STARTER_DECK_SIZE:
                groups_seen.add(card.category_group)
                starter_cards.append(card)

    # Fill remaining slots
    if len(starter_cards) < STARTER_DECK_SIZE:
        existing_ids = {c.site_id for c in starter_cards}
        fill = (
            session.query(CardStats)
            .filter(
                CardStats.rarity_tier.in_([1, 2]),
                CardStats.site_id.notin_(existing_ids),
            )
            .order_by(func.random())
            .limit(STARTER_DECK_SIZE - len(starter_cards))
            .all()
        )
        starter_cards.extend(fill)

    # Add to collection
    from api.cardgame.packs import _card_to_dict
    result = []
    for card in starter_cards:
        session.add(CardCollection(
            user_id=user.id,
            site_id=card.site_id,
            acquired_via="starter",
        ))
        result.append(_card_to_dict(session, card))

    ps.total_cards = len(starter_cards)

    return result


# ---------------------------------------------------------------------------
# Contribution reward stubs (Phase 6 — wired in later)
# ---------------------------------------------------------------------------

def reward_site_submission(session: Session, user: DiscordUser) -> dict | None:
    """Award 1 Uncommon+ card for an approved site submission."""
    from api.cardgame.packs import _card_to_dict, _pick_card
    owned = {
        r[0] for r in
        session.query(CardCollection.site_id)
        .filter(CardCollection.user_id == user.id)
        .all()
    }
    card = _pick_card(session, 2, owned)  # min Uncommon
    if card:
        session.add(CardCollection(
            user_id=user.id,
            site_id=card.site_id,
            acquired_via="contribution_site",
        ))
        ps = session.get(CardPlayerStats, user.id)
        if ps:
            ps.total_cards += 1
        return _card_to_dict(session, card)
    return None


def reward_image_upload(session: Session, user: DiscordUser) -> dict | None:
    """Award 1 Common card for an approved image upload."""
    from api.cardgame.packs import _card_to_dict, _pick_card
    owned = {
        r[0] for r in
        session.query(CardCollection.site_id)
        .filter(CardCollection.user_id == user.id)
        .all()
    }
    card = _pick_card(session, 1, owned)
    if card:
        session.add(CardCollection(
            user_id=user.id,
            site_id=card.site_id,
            acquired_via="contribution_image",
        ))
        ps = session.get(CardPlayerStats, user.id)
        if ps:
            ps.total_cards += 1
        return _card_to_dict(session, card)
    return None
