# SPDX-License-Identifier: AGPL-3.0-only
"""The end of the funnel, read off our own database for the founders
dashboard: how many people signed up, how many of them are founders, and when
anybody last did something that needed an account.

Under pipeline/, not api/, for the reason stats_analysis.py is: the Lyra image
ships pipeline/ only, and the weekly digest will want these numbers too. The
models come from pipeline.database, so a renamed column is a type error here
rather than a 500 after the deploy. card_collections is deliberately absent -
it is declared in api/cardgame/models.py, which pipeline may not import.

All-time counts, never a window. Measured 2026-09-19: five members, two of
them founders, zero acts of any kind in the last seven days, forty in the last
thirty, newest signup twenty-two days old. Any window reads zero and says
nothing, so the panel counts the whole history and dates it instead.

Every act carries its own count of distinct actors, because at this size the
total alone is a lie: 126 Lyra answers come from 2 accounts and 59 research
requests from 2, 57 of them from one. "Research requests 59" without "by 2"
reads as member activity and is one person's week.

The two act id spaces are never joined and must not be: site_likes,
site_bookmarks and token_usage_logs carry a UUID foreign key into
discord_users.id, research_requests carries a String(255) Discord snowflake.
`by` is therefore "distinct actors on this table", never "distinct members".

Aggregates only. No query selects username, discord_id, avatar_hash or
credits: the founders get counts, never a list of their members.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from pipeline.database import (
    DiscordUser,
    ResearchRequest,
    SiteBookmark,
    SiteLike,
    TokenUsageLog,
)

#: What a member can do that leaves a row behind, in the order the panel
#: prints them. The label is what a founder reads; the model is what is
#: counted. Annotated `Any` on purpose: mypy joins four unrelated model
#: classes to `type[Base]`, and `model.created_at` is then an attribute error
#: on a base class that has no such column.
ACTS: tuple[tuple[str, Any], ...] = (
    ("Likes", SiteLike),
    ("Bookmarks", SiteBookmark),
    ("Lyra answers", TokenUsageLog),
    ("Research requests", ResearchRequest),
)


def members_query(founder_role: str) -> Select:
    """One statement, one round trip: two member counts, two member dates and
    a count, an actor count and a date per act.

    ``founder_role`` is the Discord role id and arrives from the caller -
    api.services.jwt_auth.FOUNDER_ROLE_ID - because pipeline may not import
    api. It is bound through SQLAlchemy Core, not a text() fragment: a
    hand-written ``:founder_role::jsonb`` would bind the name ``founder_rol``,
    because SQLAlchemy's bind regex stops at the first colon of the cast.

    `last_login` carries the same founder filter as `founders`, because the
    panel prints it under the "Founders" tile. Unfiltered it was the newest
    login of any member under a label that says founders - today the two
    happen to be the same row (2026-09-19 06:26:02), which is exactly the kind
    of coincidence that hides a wrong label until it stops being true.
    """
    founders_only = DiscordUser.roles.contains([founder_role])
    columns: list[Any] = [
        select(func.count()).select_from(DiscordUser).scalar_subquery().label("members"),
        select(func.count())
        .select_from(DiscordUser)
        .where(founders_only)
        .scalar_subquery()
        .label("founders"),
        select(func.max(DiscordUser.created_at)).scalar_subquery().label("newest_signup"),
        select(func.max(DiscordUser.last_login))
        .where(founders_only)
        .scalar_subquery()
        .label("last_login"),
    ]
    for i, (_label, model) in enumerate(ACTS):
        columns.append(select(func.count()).select_from(model).scalar_subquery().label(f"n{i}"))
        columns.append(
            # `.distinct()` on the column, not func.distinct(): the latter
            # renders "count(distinct(user_id))" with SQLAlchemy 2.0, which
            # Postgres accepts but nobody reading the log can tell from a
            # function call.
            select(func.count(model.user_id.distinct()))
            .select_from(model)
            .scalar_subquery()
            .label(f"by{i}")
        )
        columns.append(select(func.max(model.created_at)).scalar_subquery().label(f"at{i}"))
    return select(*columns)


def _stamp(value: Any) -> str | None:
    """Every timestamp on these tables is a naive DateTime written by a
    container running Etc/UTC. Without the tzinfo the browser reads
    "2026-08-28T01:33:22" as local time and the panel is two hours out."""
    return value.replace(tzinfo=UTC).isoformat() if value else None


def shape_members(row: Any) -> dict[str, Any]:
    """The one row of members_query() as the panel reads it."""
    return {
        "members": row.members,
        "founders": row.founders,
        "newest_signup": _stamp(row.newest_signup),
        "last_login": _stamp(row.last_login),
        "acts": [
            {
                "act": label,
                "n": getattr(row, f"n{i}"),
                #: Distinct actors on THIS table. Not comparable across acts -
                #: research_requests keys on a Discord snowflake, the other
                #: three on discord_users.id.
                "by": getattr(row, f"by{i}"),
                "at": _stamp(getattr(row, f"at{i}")),
            }
            for i, (label, _model) in enumerate(ACTS)
        ],
    }


def member_totals(db: Session, founder_role: str) -> dict[str, Any]:
    return shape_members(db.execute(members_query(founder_role)).one())
