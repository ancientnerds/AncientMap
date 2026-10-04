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


def test_the_order_the_visitor_reads_is_described_sites_first():
    """Read on production 2026-10-04, 1,595,613 of the 1,759,573 shown sites carry neither a
    card description nor a description (list_inscriptions and canmore_scotland alone hold
    821,000 of them), and "great zimbabwe" answered with three bare names before the one
    described site. The card renders the OR of both columns, so the OR is the key - and it
    comes before the rank, or a bare name would still outrank a described site."""
    db = _search(
        "great zimbabwe",
        {"k": "great zimbabwe", "kl": "great zimbabwe", "w0": "great", "w1": "zimbabwe"},
    )
    sql, _params = _search_statement(db)
    order = " ".join(sql.split("ORDER BY", 1)[1].split())
    assert order.startswith(
        "(NULLIF(btrim(us.description), '') IS NULL AND cs.card_description IS NULL), rank,"
    )
    # The bare key that was there alone reads as "no card teaser" alone, and put every site
    # with only a description behind the bare ones
    assert not order.startswith("(cs.card_description IS NULL),")


#: A real production row (osm_historic, read 2026-10-04): the loaders keyed it with
#: normalize_name, which NFKD-decomposes the hamza, while Postgres's unaccent leaves it.
ARABIC_AS_STORED = "مقام الامام العباس بن علي"
ARABIC_AS_TYPED = "مقام الإمام العباس بن علي"


#: The bracketed name as the loaders keyed it and as the column's canonical flavour keeps
#: it.
BRACKETED_QUERY = "Tonbulle [Inv. 84/339]"


def _with_word_keys(q: str, keys: dict[str, str]) -> dict[str, str]:
    """Add the word keys the key-statement answers with, one per word the word tier uses
    (search_words is the splitter, so the fixture cannot drift from it)."""
    out = dict(keys)
    out.update({f"w{i}": word for i, word in enumerate(sr.search_words(q))})
    return out


def test_a_query_is_also_bound_in_the_loaders_flavour_of_the_key():
    """80,081 of the 1,759,573 rows on production hold a key that is not the canonical
    expression, so a query needs both flavours to find a site by its own name. Here the
    loaders dropped a bracketed suffix that the canonical flavour keeps."""
    db = _search(
        BRACKETED_QUERY,
        _with_word_keys(
            BRACKETED_QUERY, {"k": "tonbulle [inv. 84/339]", "kl": "tonbulle [inv. 84/339]"}
        ),
    )
    sql, params = _search_statement(db)
    assert params["k"] == "tonbulle [inv. 84/339]"  # unaccent leaves the brackets
    assert params["k_loader"] == "tonbulle"  # normalize_name drops them
    assert params["p_name_loader"] == "%tonbulle%"
    assert params["p_space_loader"] == "%tonbulle%"
    # Found by that arm, not only ranked by it
    where = sql.split("WHERE", 1)[1]
    assert "us.name_normalized LIKE :p_name_loader ESCAPE '\\'" in where
    assert "replace(us.name_normalized, ' ', '') LIKE :p_space_loader ESCAPE '\\'" in where


def test_an_exact_name_in_the_loaders_flavour_ranks_like_an_exact_name():
    db = _search(
        BRACKETED_QUERY,
        _with_word_keys(
            BRACKETED_QUERY, {"k": "tonbulle [inv. 84/339]", "kl": "tonbulle [inv. 84/339]"}
        ),
    )
    sql, params = _search_statement(db)
    flat = " ".join(sql.split())
    assert "WHEN us.name_normalized = :k_loader THEN 1" in flat
    assert "WHEN replace(us.name_normalized, ' ', '') = :k_space_loader THEN 2" in flat
    assert params["k_space_loader"] == "tonbulle"


def test_a_word_is_found_in_either_flavour_of_the_key():
    """The Arabic case from production: typed with the hamza, a word does not match the key
    the loaders wrote, so the site was unreachable under its own name."""
    words = sr.search_words(ARABIC_AS_TYPED)
    assert words[1] == "الإمام"  # the word the two flavours disagree on
    db = _search(
        ARABIC_AS_TYPED,
        _with_word_keys(ARABIC_AS_TYPED, {"k": ARABIC_AS_TYPED, "kl": ARABIC_AS_TYPED}),
    )
    sql, params = _search_statement(db)
    flat = " ".join(sql.split())
    # unaccent leaves Arabic alone, so the canonical word keeps the hamza ...
    assert params["r1"] == "\\m" + words[1]
    # ... and the loaders' flavour of the same word drops it
    assert params["rl1"] == "\\m" + "الامام"
    assert "(us.name_normalized ~ :r1 OR us.name_normalized ~ :rl1)" in flat
    # The words that fold alike cost no second bind
    assert all(f"rl{i}" not in params for i in range(len(words)) if i != 1)
    # The whole typed name matches the stored key in one piece as well
    assert params["k_loader"] == ARABIC_AS_STORED
    assert params["p_name_loader"] == f"%{ARABIC_AS_STORED}%"


def test_a_word_the_two_flavours_agree_on_costs_no_second_regex():
    """A Latin query keeps one bind per word: a second spelling of a word that both
    flavours agree on could only cost time, and the 57,563 ASCII rows that differ do so in
    their brackets, not in their letters."""
    db = _search(
        "the valley of kings",
        _with_word_keys(
            "the valley of kings", {"k": "the valley of kings", "kl": "the valley of kings"}
        ),
    )
    sql, params = _search_statement(db)
    assert "rl0" not in params and "rl1" not in params
    # And the whole query, not only its words: the canonical arms alone
    assert "p_name_loader" not in params
    assert ":p_name_loader" not in sql
    assert "k_loader" not in params
