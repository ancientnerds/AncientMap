# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.members_stats — das Ende des Trichters: Anmeldungen und was
Mitglieder je getan haben.

Datenbanklos. Die Datenschutzgrenze des Panels wird am kompilierten SQL
geprüft, weil dort die einzige Stelle ist, an der ein Leck auftauchen könnte.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from pipeline.members_stats import ACTS, members_query, shape_members

FOUNDER_ROLE = "933105341292486707"


def _compiled():
    return members_query(FOUNDER_ROLE).compile(dialect=postgresql.dialect())


def test_the_member_query_never_selects_a_name_an_id_or_a_balance():
    sql = str(_compiled())
    for column in ("username", "discord_id", "avatar_hash", "credits", "submitter_ip"):
        assert column not in sql, column
    for table in (
        "discord_users",
        "site_likes",
        "site_bookmarks",
        "token_usage_logs",
        "research_requests",
    ):
        assert table in sql, table
    # card_collections lebt unter api/cardgame/models.py — pipeline darf das
    # nicht importieren, also zählt das Panel es nicht mit.
    assert "card_collections" not in sql


def test_the_founder_role_is_a_bound_parameter_not_a_literal():
    """Das ist es, was die Namensverstümmelung von ``:founder_role::jsonb``
    verhindert: SQLAlchemys Bind-Regex hört am ersten Doppelpunkt des Casts
    auf und bände ``founder_rol``."""
    compiled = _compiled()
    assert FOUNDER_ROLE not in str(compiled)
    assert [FOUNDER_ROLE] in compiled.params.values()


def test_the_founder_login_is_filtered_to_founders():
    """Das Datum steht unter der Kachel "Founders". Heute ist es zufällig
    dieselbe Zeile wie der jüngste Login überhaupt (2026-09-19 06:26:02) —
    genau die Art Zufall, die ein falsches Label verdeckt."""
    sql = str(_compiled())
    assert sql.count("roles @>") == 2, sql


def test_every_act_carries_a_distinct_actor_count():
    """ "Research requests 59" ohne "by 2" liest sich als Mitgliederaktivität
    und ist die Woche einer Person."""
    assert str(_compiled()).count("count(DISTINCT") == len(ACTS)


def test_shape_members_stamps_naive_timestamps_as_utc():
    row = SimpleNamespace(
        members=5,
        founders=2,
        newest_signup=datetime(2026, 8, 28, 1, 33, 22),
        last_login=None,
        n0=2,
        by0=1,
        at0=None,
        n1=0,
        by1=0,
        at1=None,
        n2=126,
        by2=2,
        at2=None,
        n3=59,
        by3=2,
        at3=None,
    )
    out = shape_members(row)
    assert out["newest_signup"] == "2026-08-28T01:33:22+00:00"
    assert out["last_login"] is None
    assert [a["act"] for a in out["acts"]] == [label for label, _model in ACTS]
    assert [(a["n"], a["by"]) for a in out["acts"]] == [(2, 1), (0, 0), (126, 2), (59, 2)]
    assert all(a["at"] is None for a in out["acts"])
