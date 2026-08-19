"""Daily rewards, streak tracking, and contribution reward stubs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


def owned_site_ids(session: Session, user_id) -> set:
    """Site ids the user already holds.

    card_collections has UNIQUE (user_id, site_id), so handing out a card the
    user already owns is an IntegrityError, not a silent no-op.
    """
    return {
        r[0]
        for r in session.query(CardCollection.site_id)
        .filter(CardCollection.user_id == user_id)
        .all()
    }


def has_claimed_starter(session: Session, user_id) -> bool:
    """Whether the user ever received a starter deck.

    Owning cards is not the same thing — the daily reward, contribution rewards
    and achievements all grant cards too, and gating on card count locked anyone
    who claimed a daily first out of the starter deck for good.
    """
    return (
        session.query(CardCollection.site_id)
        .filter(
            CardCollection.user_id == user_id,
            CardCollection.acquired_via == "starter",
        )
        .first()
        is not None
    )


def claim_daily(session: Session, user: DiscordUser) -> dict:
    """Claim daily reward: 1 Common card + credits + streak tracking.

    Returns dict with reward info.
    Raises AlreadyClaimedError if already claimed today.
    """
    now = datetime.now(UTC)

    # Lock user row to prevent concurrent credit manipulation
    (
        session.query(DiscordUser)
        .filter(DiscordUser.id == user.id)
        .populate_existing()
        .with_for_update()
        .first()
    )

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
    session.add(
        CreditGrant(
            user_id=user.id,
            amount=DAILY_CREDITS,
            reason="card_daily",
        )
    )

    # Give 1 Common card
    owned = owned_site_ids(session, user.id)
    from api.cardgame.packs import _pick_card

    card = _pick_card(session, 1, owned)
    card_info = None
    if card:
        session.add(
            CardCollection(
                user_id=user.id,
                site_id=card.site_id,
                acquired_via="daily",
            )
        )
        ps.total_cards += 1
        from api.cardgame.packs import _card_to_dict

        card_info = _card_to_dict(session, card)

    # Check streak rewards (best match wins — check from highest threshold down)
    streak_reward = None
    for day_threshold, reward_type, reward_value, repeating in reversed(STREAK_REWARDS):
        triggered = (
            (ps.daily_streak % day_threshold == 0)
            if repeating
            else (ps.daily_streak == day_threshold)
        )
        if triggered:
            streak_reward = {"type": reward_type, "value": reward_value, "streak": day_threshold}
            # Apply bonus credits from streak reward
            if reward_type == "credits":
                bonus = int(reward_value)
                user.credits += bonus
                session.add(
                    CreditGrant(
                        user_id=user.id,
                        amount=bonus,
                        reason=f"streak_bonus_{day_threshold}d",
                    )
                )
            elif reward_type == "pack":
                from api.cardgame.constants import PACK_PRICES
                from api.cardgame.packs import open_pack

                # Grant credits to cover the pack cost so the user isn't charged
                pack_cost = PACK_PRICES.get(reward_value, {}).get("cost", 0)
                if pack_cost > 0:
                    user.credits += pack_cost
                pack_cards = open_pack(session, user, reward_value)
                streak_reward["cards"] = pack_cards
            break

    return {
        "credits": DAILY_CREDITS,
        "card": card_info,
        "daily_streak": ps.daily_streak,
        "streak_reward": streak_reward,
    }


def claim_starter_deck(session: Session, user: DiscordUser) -> list[dict]:
    """Give the user 10 starter cards across different categories.

    Raises AlreadyHasStarterError if the user already claimed a starter deck.
    """
    # with_for_update() on a missing row locks nothing — create the stats row
    # first (racing creators collapse on the primary key), then lock it.
    # populate_existing() forces a refresh of already-loaded attributes.
    session.execute(
        pg_insert(CardPlayerStats)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    ps = (
        session.query(CardPlayerStats)
        .filter(CardPlayerStats.user_id == user.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if has_claimed_starter(session, user.id):
        raise AlreadyHasStarterError("You already claimed your starter deck")

    # Pick 10 well-distributed cards: prefer diverse groups and low tiers
    # Get one card per category group, then fill remaining slots.
    # Cards the user already holds (e.g. from a daily claimed first) are excluded —
    # UNIQUE (user_id, site_id) makes a duplicate an IntegrityError.
    owned = owned_site_ids(session, user.id)
    groups_seen: set[str] = set()
    starter_cards: list[CardStats] = []

    # First: one card per group (Common/Uncommon)
    for tier in [1, 2]:
        query = session.query(CardStats).filter(CardStats.rarity_tier == tier)
        if owned:
            query = query.filter(CardStats.site_id.notin_(owned))
        cards = query.order_by(func.random()).limit(50).all()
        for card in cards:
            if card.category_group not in groups_seen and len(starter_cards) < STARTER_DECK_SIZE:
                groups_seen.add(card.category_group)
                starter_cards.append(card)

    # Fill remaining slots
    if len(starter_cards) < STARTER_DECK_SIZE:
        exclude = owned | {c.site_id for c in starter_cards}
        query = session.query(CardStats).filter(CardStats.rarity_tier.in_([1, 2]))
        if exclude:
            query = query.filter(CardStats.site_id.notin_(exclude))
        fill = query.order_by(func.random()).limit(STARTER_DECK_SIZE - len(starter_cards)).all()
        starter_cards.extend(fill)

    # Add to collection
    from api.cardgame.packs import _card_to_dict

    result = []
    for card in starter_cards:
        session.add(
            CardCollection(
                user_id=user.id,
                site_id=card.site_id,
                acquired_via="starter",
            )
        )
        result.append(_card_to_dict(session, card))

    ps.total_cards += len(starter_cards)

    return result


# ---------------------------------------------------------------------------
# Contribution reward stubs (Phase 6 — wired in later)
# ---------------------------------------------------------------------------


def reward_site_submission(session: Session, user: DiscordUser) -> dict | None:
    """Award 1 Uncommon+ card for an approved site submission."""
    from api.cardgame.packs import _card_to_dict, _pick_card

    owned = owned_site_ids(session, user.id)
    card = _pick_card(session, 2, owned)  # min Uncommon
    if card:
        session.add(
            CardCollection(
                user_id=user.id,
                site_id=card.site_id,
                acquired_via="contribution_site",
            )
        )
        ps = session.get(CardPlayerStats, user.id)
        if ps:
            ps.total_cards += 1
        return _card_to_dict(session, card)
    return None


def reward_image_upload(session: Session, user: DiscordUser) -> dict | None:
    """Award 1 Common card for an approved image upload."""
    from api.cardgame.packs import _card_to_dict, _pick_card

    owned = owned_site_ids(session, user.id)
    card = _pick_card(session, 1, owned)
    if card:
        session.add(
            CardCollection(
                user_id=user.id,
                site_id=card.site_id,
                acquired_via="contribution_image",
            )
        )
        ps = session.get(CardPlayerStats, user.id)
        if ps:
            ps.total_cards += 1
        return _card_to_dict(session, card)
    return None
