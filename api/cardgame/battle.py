"""Battle resolution engine — pure function, deterministic given seed."""

import random
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.cardgame.constants import (
    BATTLE_CARD_DROP_CHANCE,
    BATTLE_WIN_CREDITS,
    RARITY_NAMES,
    TYPE_ADVANTAGE,
    TYPE_ADVANTAGE_BONUS,
)
from api.cardgame.models import CardBattle, CardPlayerStats, CardStats
from api.cardgame.synergies import compute_synergies, describe_synergies
from pipeline.database import CreditGrant, DiscordUser, UnifiedSite

STAT_NAMES = ["antiquity", "fortification", "cultural_influence", "mystery", "legacy"]


def _get_stat(card: CardStats, stat_name: str) -> int:
    return getattr(card, stat_name)


def resolve_battle(
    challenger_deck: list[CardStats],
    defender_deck: list[CardStats],
    battle_id: str,
) -> dict:
    """Resolve a 5-round battle between two decks.

    Applies synergy bonuses from category, regional, temporal, and cross-combo
    synergies before comparing stats each round.

    Args:
        challenger_deck: List of CardStats (up to 10 cards)
        defender_deck: List of CardStats (up to 10 cards)
        battle_id: Used as random seed for reproducibility

    Returns:
        {rounds, winner, challenger_wins, defender_wins,
         challenger_synergies, defender_synergies}
    """
    rng = random.Random(battle_id)  # noqa: S311 — game logic, not crypto

    # Shuffle decks
    c_deck = list(challenger_deck)
    d_deck = list(defender_deck)
    rng.shuffle(c_deck)
    rng.shuffle(d_deck)

    # Compute synergy bonuses for both decks
    c_synergies = compute_synergies(c_deck)
    d_synergies = compute_synergies(d_deck)

    # Pick 5 stats in random order
    stats_order = list(STAT_NAMES)
    rng.shuffle(stats_order)

    rounds = []
    c_wins = 0
    d_wins = 0
    c_index = 0
    d_index = 0

    for round_num, stat_name in enumerate(stats_order):
        if c_index >= len(c_deck) or d_index >= len(d_deck):
            break

        c_card = c_deck[c_index]
        d_card = d_deck[d_index]

        c_stat = _get_stat(c_card, stat_name)
        d_stat = _get_stat(d_card, stat_name)

        # Synergy bonuses
        c_syn = c_synergies.get(str(c_card.site_id), {}).get(stat_name, 0)
        d_syn = d_synergies.get(str(d_card.site_id), {}).get(stat_name, 0)

        # Type advantage bonus
        c_advantage = TYPE_ADVANTAGE.get(c_card.category_group) == d_card.category_group
        d_advantage = TYPE_ADVANTAGE.get(d_card.category_group) == c_card.category_group

        c_effective = c_stat + c_syn + (TYPE_ADVANTAGE_BONUS if c_advantage else 0)
        d_effective = d_stat + d_syn + (TYPE_ADVANTAGE_BONUS if d_advantage else 0)

        # Tiebreaker: higher antiquity stat wins
        if c_effective == d_effective:
            c_effective = c_card.antiquity
            d_effective = d_card.antiquity

        if c_effective > d_effective:
            winner = "challenger"
            c_wins += 1
        elif d_effective > c_effective:
            winner = "defender"
            d_wins += 1
        else:
            winner = "draw"

        round_data = {
            "round": round_num + 1,
            "stat": stat_name,
            "challenger_card": str(c_card.site_id),
            "defender_card": str(d_card.site_id),
            "challenger_value": c_stat,
            "defender_value": d_stat,
            "challenger_bonus": (TYPE_ADVANTAGE_BONUS if c_advantage else 0) + c_syn,
            "defender_bonus": (TYPE_ADVANTAGE_BONUS if d_advantage else 0) + d_syn,
            "challenger_synergy": c_syn,
            "defender_synergy": d_syn,
            "winner": winner,
        }
        rounds.append(round_data)

        # Antiquity special: winner removes loser's next card
        if stat_name == "antiquity" and winner != "draw":
            if winner == "challenger" and d_index + 1 < len(d_deck):
                d_index += 1
                round_data["antiquity_removal"] = str(d_deck[d_index].site_id)
            elif winner == "defender" and c_index + 1 < len(c_deck):
                c_index += 1
                round_data["antiquity_removal"] = str(c_deck[c_index].site_id)

        c_index += 1
        d_index += 1

    if c_wins > d_wins:
        overall_winner = "challenger"
    elif d_wins > c_wins:
        overall_winner = "defender"
    else:
        overall_winner = "draw"

    return {
        "rounds": rounds,
        "winner": overall_winner,
        "challenger_wins": c_wins,
        "defender_wins": d_wins,
        "challenger_synergies": describe_synergies(challenger_deck),
        "defender_synergies": describe_synergies(defender_deck),
    }


def apply_battle_result(
    session: Session,
    battle: CardBattle,
    result: dict,
    challenger: DiscordUser,
    defender: DiscordUser,
) -> None:
    """Update battle record, player stats, and distribute rewards."""
    # Lock both user rows to prevent concurrent credit manipulation
    session.query(DiscordUser).filter(DiscordUser.id == challenger.id).with_for_update().first()
    session.query(DiscordUser).filter(DiscordUser.id == defender.id).with_for_update().first()

    now = datetime.now(UTC)

    battle.status = "resolved"
    battle.rounds = result["rounds"]
    battle.challenger_wins = result["challenger_wins"]
    battle.defender_wins = result["defender_wins"]
    battle.resolved_at = now

    winner_user = None

    if result["winner"] == "challenger":
        battle.winner_id = challenger.id
        winner_user = challenger
    elif result["winner"] == "defender":
        battle.winner_id = defender.id
        winner_user = defender

    # Handle stake (snap_multiplier scales the effective stake)
    effective_stake = battle.stake_credits * (battle.snap_multiplier or 1)
    if effective_stake > 0 and winner_user:
        winner_user.credits += effective_stake * 2
        session.add(CreditGrant(
            user_id=winner_user.id,
            amount=effective_stake * 2,
            reason="card_battle_stake_win",
        ))

    # Update player stats
    for user, is_winner in [
        (challenger, result["winner"] == "challenger"),
        (defender, result["winner"] == "defender"),
    ]:
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            ps = CardPlayerStats(user_id=user.id)
            session.add(ps)

        if result["winner"] == "draw":
            ps.draws += 1
            ps.win_streak = 0
        elif is_winner:
            ps.wins += 1
            ps.win_streak += 1
            ps.best_streak = max(ps.best_streak, ps.win_streak)
            ps.xp += 25
        else:
            ps.losses += 1
            ps.win_streak = 0
            ps.xp += 5  # consolation XP

    # Winner gets credits + chance at card drop
    if winner_user:
        winner_user.credits += BATTLE_WIN_CREDITS
        session.add(CreditGrant(
            user_id=winner_user.id,
            amount=BATTLE_WIN_CREDITS,
            reason="card_battle_win",
        ))

        # Random card drop
        rng = random.Random(str(battle.id) + "drop")  # noqa: S311 — game logic
        if rng.random() < BATTLE_CARD_DROP_CHANCE:
            from api.cardgame.models import CardCollection
            from api.cardgame.packs import _pick_card

            owned = {
                r[0] for r in
                session.query(CardCollection.site_id)
                .filter(CardCollection.user_id == winner_user.id)
                .all()
            }
            card = _pick_card(session, 1, owned)
            if card:
                session.add(CardCollection(
                    user_id=winner_user.id,
                    site_id=card.site_id,
                    acquired_via="battle_drop",
                ))
                ps = session.get(CardPlayerStats, winner_user.id)
                if ps:
                    ps.total_cards += 1
