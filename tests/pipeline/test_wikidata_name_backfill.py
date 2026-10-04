# SPDX-License-Identifier: AGPL-3.0-only
"""The Wikidata name backfill: what it asks for, what it keeps, what it writes.

A visitor who typed "Machu Picchu" as マチュ・ピチュ found nothing, because the
curated rows carry only their Latin name (4,537 of the 4,900 have a QID in
site_external_ids and no name row beyond the one label - read on production
2026-10-04). Wikidata has a label in up to 140 languages for such a site, so the
names are one read-only call per 50 sites away. This pins the three things that
make that safe: the language list is asked within the API's own limit, a name is
never written twice, and the key comes from the one definition.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pipeline.lyra.site_key import site_key_sql
from pipeline.wikidata_name_backfill import (
    LANGUAGES,
    LANGUAGES_PER_REQUEST,
    _insert_sql,
    fetch_names,
    main,
    plan,
    read_qid_file,
    report,
    store,
)

QID = "Q676203"  # Machu Picchu


def _entity(labels: dict[str, str], aliases: dict[str, list[str]] | None = None) -> dict:
    return {
        "labels": {lang: {"value": value} for lang, value in labels.items()},
        "aliases": {
            lang: [{"value": v} for v in values] for lang, values in (aliases or {}).items()
        },
    }


@pytest.fixture
def one_call(monkeypatch):
    """Answer every call with one item; record the parameters it was asked with."""
    calls: list[dict] = []

    def _fake(params: dict[str, str], timeout: int = 45) -> dict:
        calls.append(params)
        return {
            "entities": {
                QID: _entity({"ja": "マチュ・ピチュ", "en": "Machu Picchu"}, {"zh": ["麻丘比丘"]})
            }
        }

    monkeypatch.setattr("pipeline.wikidata_name_backfill._http_json", _fake)
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)
    return calls


def test_the_language_list_is_asked_within_the_api_limit():
    """84 languages in one call came back {"error": {"code": "toomanyvalues",
    "parameter": "languages", "limit": 50}} (measured 2026-10-04 on Q676203)."""
    assert len(LANGUAGES) > LANGUAGES_PER_REQUEST  # the list is wider than one call allows
    for i in range(0, len(LANGUAGES), LANGUAGES_PER_REQUEST):
        assert len(LANGUAGES[i : i + LANGUAGES_PER_REQUEST]) <= LANGUAGES_PER_REQUEST
    assert len(set(LANGUAGES)) == len(LANGUAGES), "a repeated language code is a wasted slot"


def test_the_names_of_a_site_come_back_with_their_language(one_call):
    found, requests_made = fetch_names([QID])
    # The raw answer, as Wikidata has it: dropping the site's own name is plan()'s job
    assert found[QID] == [("Machu Picchu", "en"), ("マチュ・ピチュ", "ja"), ("麻丘比丘", "zh")]
    assert requests_made == 2  # 83 languages, 50 per call
    assert "labels|aliases" in one_call[0]["props"]
    assert one_call[0]["ids"] == QID


def test_one_name_is_kept_once_however_many_languages_spell_it_alike(monkeypatch):
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)
    monkeypatch.setattr(
        "pipeline.wikidata_name_backfill._http_json",
        lambda params, timeout=45: {
            "entities": {
                QID: _entity({"de": "Machu Picchu", "fr": "Machu Picchu", "es": "Machu Picchu"})
            }
        },
    )
    found, _ = fetch_names([QID])
    assert found[QID] == [("Machu Picchu", "de")]


def test_an_api_error_loses_that_block_and_not_the_run(monkeypatch):
    """A site whose names are missing stays findable by its own name, which is where it
    was before; the run must continue."""
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)
    answers = [
        {"error": {"code": "toomanyvalues"}},
        {"entities": {QID: _entity({"ja": "マチュ・ピチュ"})}},
    ]
    monkeypatch.setattr(
        "pipeline.wikidata_name_backfill._http_json", lambda params, timeout=45: answers.pop(0)
    )
    found, requests_made = fetch_names([QID])
    assert requests_made == 2
    assert found[QID] == [("マチュ・ピチュ", "ja")]


def test_the_sites_own_name_is_not_asked_to_be_written_as_its_own_alias():
    found = {QID: [("マチュ・ピチュ", "ja"), ("Machu Picchu", "en")]}
    plans = plan([("site-1", "Machu Picchu", QID)], found)
    assert [name for name, _lang in plans[0].rows] == ["マチュ・ピチュ"]


def test_a_site_without_a_label_yields_no_plan_and_asks_for_nothing_to_write():
    plans = plan(
        [("site-1", "Machu Picchu", QID), ("site-2", "Nowhere", "Q1")],
        {QID: [("マチュ・ピチュ", "ja")]},
    )
    assert [p.site_id for p in plans] == ["site-1"]


def test_the_key_is_computed_by_the_insert_from_the_raw_name():
    """The search compares against left(lower(unaccent(name)), 500)
    (pipeline/lyra/site_key.py). _store_wikidata_aliases computes it that way per
    alias; the batched statement has to, or its rows are unreachable."""
    sql = _insert_sql(2)
    assert site_key_sql("n.name") in sql
    assert "name_normalized," in sql
    # Never a Python-side key: it folds neither the Turkish dotless i nor ø, and it
    # drops a parenthesised suffix the column keeps
    assert "normalize_name" not in sql
    assert site_key_sql(":canonical") in sql  # the site's own name is not its own alias
    assert "ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING" in sql
    assert "'wikidata_alias'" in sql
    assert "language_code" in sql
    # CAST, never ":n0::text": SQLAlchemy's text() does not read a bind that is
    # immediately followed by a colon, and the statement then dies with
    # "syntax error at or near ':'" (measured 2026-10-04 on production)
    assert "CAST(:n0 AS text)" in sql
    assert "::text" not in sql


class _Logged:
    """A session that records the statement and its binds, and answers a row count."""

    def __init__(self) -> None:
        self.log: list[tuple[str, dict]] = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.log.append((str(stmt), params))
        return SimpleNamespace(rowcount=2)

    def commit(self) -> None:
        self.commits += 1


def test_what_is_written_is_exactly_the_planned_rows():
    session = _Logged()
    plan_row = plan(
        [("site-1", "Machu Picchu", QID)], {QID: [("マチュ・ピチュ", "ja"), ("麻丘比丘", "zh")]}
    )[0]
    assert store(session, plan_row) == 2
    (sql, params) = session.log[0]
    assert "INSERT INTO unified_site_names" in sql
    assert params["site_id"] == "site-1"
    assert params["canonical"] == "Machu Picchu"
    assert params["n0"] == "マチュ・ピチュ" and params["l0"] == "ja"
    assert params["n1"] == "麻丘比丘" and params["l1"] == "zh"
    assert session.commits == 1, "one commit per site, so a failure keeps what it wrote"


def test_a_qid_file_needs_no_database(tmp_path, one_call, capsys):
    """The yield must be measurable without a database, before anything is written."""
    path = tmp_path / "qids.tsv"
    path.write_text(f"# comment\n{QID}\tMachu Picchu\n\n", encoding="utf-8")
    assert read_qid_file(path) == [("", "Machu Picchu", QID)]
    assert main(["--qids", str(path)]) == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["sites_considered"] == 1
    assert summary["rows"] == 2  # マチュ・ピチュ and 麻丘比丘, not "Machu Picchu" itself
    assert summary["languages"] == {"ja": 1, "zh": 1}
    assert summary["examples"][0]["qid"] == QID


def test_the_report_says_what_a_run_would_write():
    found = {QID: [("マチュ・ピチュ", "ja"), ("麻丘比丘", "zh")]}
    plans = plan([("site-1", "Machu Picchu", QID), ("site-2", "Nowhere", "Q2")], found)
    summary = report(
        plans, [("site-1", "Machu Picchu", QID), ("site-2", "Nowhere", "Q2")], requests_made=2
    )
    assert summary["sites_considered"] == 2
    assert summary["sites_with_names"] == 1
    assert summary["sites_without_a_label"] == 1
    assert summary["rows"] == 2
    assert summary["rows_per_site"] == 2.0
    assert summary["api_requests"] == 2
