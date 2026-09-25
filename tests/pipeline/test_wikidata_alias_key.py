# SPDX-License-Identifier: AGPL-3.0-only
"""Lyra's Wikidata aliases are keyed by Postgres, from the raw name - never by normalize_name().

`unified_site_names.name_normalized` is the match key `left(lower(unaccent(name)), 500)`
(pipeline/lyra/site_key.py); site_matcher binds the raw name and computes its side in SQL.
`_store_wikidata_aliases` computed the key with pipeline.utils.text.normalize_name instead, which
decomposes (NFKD) and strips combining marks - it drops the Japanese (han)dakuten (ヤップ島 ->
ヤッフ島), leaves Hangul as bare jamo, and cuts a parenthesised part ("Cerutti Mastodon (CM) site"
-> "cerutti mastodon  site"). Read on production 2026-09-25: exactly 11 alias rows of curated
sites carry a key other than the SQL key of their own name, all `wikidata_alias` - North Sentinel
Island, Yap (4), Cerutti Mastodon site, Roopkund Lake, Charnwood Forest (2), Doggerland (2). No
exact lookup of those names reaches the site, and a second Lyra match of the same site would add
the alias again under the SQL key next to the old one (the existence check compared Python keys).

The writer now inserts with the key computed in the INSERT itself and lets the (site_id,
name_normalized) constraint decide what already exists.
"""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace

from pipeline.lyra import site_identifier
from pipeline.lyra.site_key import site_key_sql
from tests.fake_sql import RecordingSession

SITE = uuid.UUID("624a1828-419b-46e4-93d0-ef7b4981aa29")
INSERT = "INSERT INTO unified_site_names"


def _store(names, canonical="Yap", inserted=1):
    session = RecordingSession({INSERT: [SimpleNamespace(id=1)] * inserted})
    stored = site_identifier._store_wikidata_aliases(session, SITE, names, canonical)
    return session, stored


def test_the_key_is_computed_in_the_insert_from_the_raw_name():
    session, _ = _store(["ヤップ島"])
    (sql,) = session.statements()
    assert INSERT in sql
    assert site_key_sql(":name") in sql  # the alias's key, by Postgres
    assert site_key_sql(":canonical") in sql  # the site's own name is not stored as its alias
    assert "ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING" in sql
    (params,) = [p for _, p in session.log]
    assert params == {
        "site_id": SITE,
        "name": "ヤップ島",
        "canonical": "Yap",
        "name_type": "wikidata_alias",
    }


def test_no_python_key_is_made():
    source = inspect.getsource(site_identifier._store_wikidata_aliases)
    assert "normalize_name(" not in source  # no call; the docstring may name it
    assert "name_normalized=" not in source


def test_every_name_of_three_or_more_characters_is_offered():
    session, stored = _store(["ヤップ島", "Wa", "", None, "Yap Islands"], inserted=1)
    assert [p["name"] for _, p in session.log] == ["ヤップ島", "Yap Islands"]
    assert stored == 2  # each INSERT answered with one new row


def test_an_alias_the_constraint_already_holds_is_not_counted():
    session, stored = _store(["ヤップ島"], inserted=0)
    assert len(session.statements()) == 1
    assert stored == 0


def test_nothing_to_store_touches_nothing():
    session, stored = _store([])
    assert session.statements() == []
    assert stored == 0
