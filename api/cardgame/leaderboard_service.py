"""Shared card-game queries used by both the REST routes and Discord commands.

/api/cards/leaderboard and the /leaderboard slash command (and likewise
/api/cards/collection and /cards) ran byte-identical query/sort logic in two
places — audit P7-17. This module is the single implementation both call;
presentation (JSON response vs Discord embed) stays with each consumer.
"""

from api.cardgame.models import CardCollection, CardPlayerStats, CardStats
from api.services.lyra_tools import _escape_ilike
from pipeline.database import DiscordUser, UnifiedSite

_LEADERBOARD_SORT_COLUMNS = {
    "wins": CardPlayerStats.wins,
    "cards": CardPlayerStats.total_cards,
    "power": CardPlayerStats.xp,
    "streak": CardPlayerStats.best_streak,
}


def get_leaderboard_entries(session, sort: str, limit: int) -> list[dict]:
    """Top players joined with their Discord identity, serialized to dicts.

    sort: wins | cards | power | streak (both callers validate the value
    upstream — route regex / slash-command choices).
    """
    query = session.query(CardPlayerStats, DiscordUser).join(
        DiscordUser, CardPlayerStats.user_id == DiscordUser.id
    )
    order_col = _LEADERBOARD_SORT_COLUMNS.get(sort)
    if order_col is not None:
        query = query.order_by(order_col.desc())
    rows = query.limit(limit).all()
    return [
        {
            "username": user.username if user else "Unknown",
            "avatar_hash": user.avatar_hash if user else None,
            "wins": ps.wins,
            "losses": ps.losses,
            "draws": ps.draws,
            "total_cards": ps.total_cards,
            "xp": ps.xp,
            "best_streak": ps.best_streak,
            "daily_streak": ps.daily_streak,
        }
        for ps, user in rows
    ]


def fetch_collection_page(
    session,
    user_id,
    *,
    rarity: int | None = None,
    group: str | None = None,
    civilization: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list, int]:
    """One page of a user's collection: (rows, total).

    rows are (CardCollection, CardStats, UnifiedSite) tuples ordered by
    rarity then power. The Discord command only uses the rarity filter;
    the REST route additionally filters by group/civilization.
    """
    query = (
        session.query(CardCollection, CardStats, UnifiedSite)
        .join(CardStats, CardCollection.site_id == CardStats.site_id)
        .join(UnifiedSite, CardCollection.site_id == UnifiedSite.id)
        .filter(CardCollection.user_id == user_id)
    )
    if rarity is not None:
        query = query.filter(CardStats.rarity_tier == rarity)
    if group:
        query = query.filter(CardStats.category_group == group)
    if civilization:
        query = query.filter(
            CardStats.civilization.ilike(f"%{_escape_ilike(civilization)}%", escape="\\")
        )
    total = query.count()
    rows = (
        query.order_by(CardStats.rarity_tier.desc(), CardStats.total_power.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return rows, total
