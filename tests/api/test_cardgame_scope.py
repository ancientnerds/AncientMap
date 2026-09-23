# SPDX-License-Identifier: AGPL-3.0-only
"""Card draws skip retired sites (E4), and the 'Stones of Britain' pool covers the UK parts.

The draws are ORM queries. tests/fake_sql.OrmSession builds them with a real SQLAlchemy
Query and renders each statement with the PostgreSQL dialect when it is executed, so the
tests read the SQL production would run - including the correlated NOT EXISTS of
card_site_in_scope(), which has to correlate to card_stats and not to a copy of it.
"""

from __future__ import annotations

import random
import re
import uuid
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from api.cardgame import expedition, lyra_duel, packs, quiz, rewards
from api.cardgame.models import CardStats, card_site_in_scope
from tests.fake_sql import OrmSession

#: How card_site_in_scope() renders inside a query over card_stats: a NOT EXISTS over an
#: aliased unified_sites, correlated to the drawn card.
_IN_SCOPE = re.compile(
    r"NOT \(EXISTS \(SELECT \*\s+FROM unified_sites AS (\w+)\s+"
    r"WHERE \1\.id = card_stats\.site_id AND \1\.scope_status = 'retired'\)\)"
)


def in_scope(sql: str) -> bool:
    return bool(_IN_SCOPE.search(sql))


def test_the_criterion_correlates_to_the_drawn_card():
    stmt = OrmSession()._real.query(CardStats).filter(card_site_in_scope()).statement
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert in_scope(sql)
    # correlated, not a cartesian product with a second card_stats
    assert sql.count("FROM card_stats") == 1


def test_the_criterion_survives_a_query_that_joins_unified_sites_itself():
    """The quiz, /random and the collection page join UnifiedSite. With the plain table in
    the subquery, auto-correlation swallowed its FROM and SQLAlchemy raised on every such
    draw ("returned no FROM clauses due to auto-correlation")."""
    from pipeline.database import UnifiedSite

    stmt = (
        OrmSession()
        ._real.query(CardStats, UnifiedSite)
        .join(UnifiedSite, CardStats.site_id == UnifiedSite.id)
        .filter(card_site_in_scope())
        .statement
    )
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert in_scope(sql)


def test_pack_draws_skip_retired_sites():
    session = OrmSession()
    packs._pick_card(session, 2, set())
    assert len(session.sql) == 2  # the unowned draw, then the any-card draw
    for sql in session.sql:
        assert in_scope(sql)


def test_the_starter_deck_skips_retired_sites(monkeypatch):
    # first answer: the player's stats row the function locks and updates
    session = OrmSession([[SimpleNamespace(total_cards=0)]])
    monkeypatch.setattr(session, "execute", lambda *a, **k: None, raising=False)  # pg_insert
    monkeypatch.setattr(rewards, "has_claimed_starter", lambda s, uid: False)
    monkeypatch.setattr(rewards, "owned_site_ids", lambda s, uid: set())
    rewards.claim_starter_deck(session, SimpleNamespace(id=uuid.uuid4()))
    # the two tier draws and the fill draw
    draws = [sql for sql in session.sql if "FROM card_stats" in sql and "rarity_tier" in sql]
    assert len(draws) == 3
    for sql in draws:
        assert in_scope(sql)


def test_expedition_decks_skip_retired_sites():
    session = OrmSession()
    expedition._build_npc_deck(session, ["England"], stage=1)
    assert len(session.sql) == 2  # regional draw, then the fill draw (fewer than 5 found)
    for sql in session.sql:
        assert in_scope(sql)


def test_lyra_decks_skip_retired_sites():
    session = OrmSession()
    lyra_duel._build_lyra_deck(session, 1)
    assert len(session.sql) == 2
    for sql in session.sql:
        assert in_scope(sql)


def test_every_quiz_question_draws_only_shown_sites():
    rng = random.Random(1)  # noqa: S311 - quiz shuffling, not crypto
    for generate in (
        quiz._generate_age_comparison,
        quiz._generate_country_question,
        quiz._generate_category_question,
        quiz._generate_stat_question,
        quiz._generate_period_question,
    ):
        session = OrmSession()
        generate(session, rng)
        (draw,) = session.sql[:1]
        assert in_scope(draw), generate.__name__


def test_stones_of_britain_draws_from_every_part_of_the_uk():
    """The dataset spells the UK by its parts (England 1,052, Wales 118, Scotland 83,
    Northern Ireland 4). With 'United Kingdom' alone the pool held 69 cards, without
    Stonehenge or Skara Brae - the two sites its own description names."""
    countries = expedition.EXPEDITIONS["british_isles"]["countries"]
    for part in ("England", "Scotland", "Wales", "Northern Ireland", "Ireland"):
        assert part in countries
    session = OrmSession()
    expedition._build_npc_deck(session, countries, stage=1)
    regional = session.sql[0]
    for part in ("England", "Scotland", "Wales", "Northern Ireland"):
        assert f"'{part}'" in regional


class _ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def test_public_random_cards_skip_retired_sites(monkeypatch):
    from api.cardgame import routes

    session = OrmSession()
    monkeypatch.setattr(routes, "get_session", lambda: _ctx(session))
    routes.get_random_cards(count=5)
    (sql,) = session.sql
    assert in_scope(sql)


def test_card_stats_of_a_retired_site_answer_410(monkeypatch):
    import pytest
    from fastapi import HTTPException

    from api.cardgame import routes

    sid = uuid.uuid4()
    session = OrmSession(
        [[SimpleNamespace(site_id=sid)], [SimpleNamespace(scope_status="retired")]]
    )
    monkeypatch.setattr(routes, "get_session", lambda: _ctx(session))
    with pytest.raises(HTTPException) as exc:
        routes.get_card_stats(str(sid))
    assert exc.value.status_code == 410


def test_the_discord_card_command_never_shows_a_retired_site():
    """/card <name> looks the site up by name; a retired site has no card to show."""
    from api.cardgame.discord_commands import _find_card_site

    session = OrmSession([[SimpleNamespace(name="Damascus Gate")]])
    assert _find_card_site(session, "damascus").name == "Damascus Gate"
    (sql,) = session.sql
    assert "unified_sites.source_id = 'ancient_nerds'" in sql
    assert "unified_sites.scope_status IS DISTINCT FROM 'retired'" in sql


def test_the_collection_page_keeps_owned_cards_of_retired_sites():
    """Owned cards stay the player's - in the collection as in their decks and battles
    (which load straight from card_ids). Only new draws skip a retired site; hiding the
    card from the collection alone would leave it playing in decks the player can't see."""
    from api.cardgame.leaderboard_service import fetch_collection_page

    session = OrmSession()
    fetch_collection_page(session, uuid.uuid4())
    assert session.sql and not any(in_scope(sql) for sql in session.sql)
