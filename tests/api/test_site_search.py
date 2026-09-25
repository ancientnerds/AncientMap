# SPDX-License-Identifier: AGPL-3.0-only
"""/api/sites/search (api/routes/sites.py search_sites): the phrase tiers and the word tier.

Umami, 2026-09-17..25: visitors typed "the valley of kings", "the valley of kings, egypt" and
"giza, egypt" and found nothing, because every tier matched the query as one string. Run
read-only on production 2026-09-25, the word tier finds the Valley of the Kings and the Giza
sites for exactly those queries.

DB-less: the route runs against tests/fake_sql.RecordingSession. The keys the route asks
Postgres for (the name_normalized expression, pipeline/lyra/site_key.py) are answered here with
what Postgres returns for these ASCII queries.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.routes import sites as sr
from tests.fake_sql import RecordingSession

COUNTRIES = ["egypt", "england", "turkiye", "united kingdom"]


@pytest.fixture(autouse=True)
def _no_cache_no_limits(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(sr, "cache_get", lambda key: store.get(key))
    monkeypatch.setattr(sr, "cache_set", lambda key, value, ttl=0: store.__setitem__(key, value))
    monkeypatch.setattr(sr, "get_client_ip", lambda req: "203.0.113.9")
    monkeypatch.setattr(sr._search_limiter, "check", lambda ip: True)


def _search(q: str, keys: dict[str, str]) -> RecordingSession:
    db = RecordingSession(
        {
            " AS kl": [SimpleNamespace(**keys)],
            "DISTINCT lower(unaccent(country))": [SimpleNamespace(c=c) for c in COUNTRIES],
        }
    )
    sr.search_sites(req=None, q=q, limit=20, db=db)
    return db


def _search_statement(db: RecordingSession) -> tuple[str, dict]:
    return next((sql, p) for sql, p in db.log if "FROM unified_sites us" in sql)


def test_search_words_drop_the_filler_and_the_short_words():
    assert sr.search_words("the valley of kings, egypt") == ["valley", "kings", "egypt"]
    assert sr.search_words("Giza, Egypt") == ["giza", "egypt"]
    # Two characters cannot drive the trigram index (pg_trgm needs three)
    assert sr.search_words("kv 62 valley") == ["valley"]
    assert sr.search_words("temple temple of zeus") == ["temple", "zeus"]


def test_a_word_names_a_country_by_the_start_of_one_of_its_words():
    assert sr.country_matches("egypt", COUNTRIES) == ["egypt"]
    assert sr.country_matches("egy", COUNTRIES) == ["egypt"]
    assert sr.country_matches("kingdom", COUNTRIES) == ["united kingdom"]
    assert sr.country_matches("valley", COUNTRIES) == []


def test_the_query_keys_come_from_postgres_with_the_column_expression():
    """name_normalized is left(lower(unaccent(name)), 500); a Python key folds neither the
    Turkish dotless i nor o-slash (pipeline/lyra/site_key.py)."""
    db = _search("Göbeklitepe", {"k": "gobeklitepe", "kl": "gobeklitepe"})
    keys_sql, keys_params = db.log[0]
    assert "left(lower(unaccent(:raw)), 500) AS k" in keys_sql
    assert keys_params["raw"] == "Göbeklitepe"
    sql, params = _search_statement(db)
    assert params["k"] == "gobeklitepe" and params["p_name"] == "%gobeklitepe%"
    assert params["p_space"] == "%gobeklitepe%"
    # The column itself, no function: that is what the trigram indexes of 0024 cover
    assert "unaccent(us.name_normalized)" not in sql
    assert "us.name_normalized LIKE :p_name ESCAPE '\\'" in sql
    assert "replace(us.name_normalized, ' ', '') LIKE :p_space ESCAPE '\\'" in sql


def test_a_wildcard_in_the_query_matches_itself():
    db = _search("100%_x", {"k": "100%_x", "kl": "100\\%\\_x"})
    _sql, params = _search_statement(db)
    assert params["p_name"] == "%100\\%\\_x%"


def test_one_word_has_no_word_tier():
    db = _search("stonehenge", {"k": "stonehenge", "kl": "stonehenge", "w0": "stonehenge"})
    sql, params = _search_statement(db)
    assert "~ :r0" not in sql and "r0" not in params


def test_the_valley_of_kings_egypt_is_found_word_by_word():
    db = _search(
        "the valley of kings, egypt",
        {
            "k": "the valley of kings, egypt",
            "kl": "the valley of kings, egypt",
            "w0": "valley",
            "w1": "kings",
            "w2": "egypt",
        },
    )
    sql, params = _search_statement(db)
    flat = " ".join(sql.split())
    assert params["r0"] == "\\mvalley" and params["r1"] == "\\mkings"
    # "egypt" names a country: the country, or the name, may hold it
    assert params["c2"] == ["egypt"]
    assert (
        "(us.name_normalized ~ :r0 AND us.name_normalized ~ :r1 AND "
        "(lower(unaccent(us.country)) = ANY(CAST(:c2 AS text[])) OR us.name_normalized ~ :r2))"
    ) in flat
    # Rank 4 needs every word in the name, rank 5 took the country
    assert (
        "WHEN us.name_normalized ~ :r0 AND us.name_normalized ~ :r1 AND us.name_normalized ~ :r2 THEN 4"
        in flat
    )


def test_only_country_words_make_no_word_tier():
    """Without a word that has to be in the name, the arm would have nothing the index can
    answer and would scan every row."""
    db = _search(
        "united kingdom",
        {"k": "united kingdom", "kl": "united kingdom", "w0": "united", "w1": "kingdom"},
    )
    sql, _params = _search_statement(db)
    assert "~ :r0" not in sql.split("WHERE", 1)[1]


def test_a_word_key_is_escaped_for_the_regular_expression():
    """A word is \\w characters only, but its key comes from unaccent(), which may map a
    letter onto something else; whatever it returns is matched literally."""
    assert sr._REGEX_SYNTAX.sub(r"\\\1", "a.b(c)") == "a\\.b\\(c\\)"
