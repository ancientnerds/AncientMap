# SPDX-License-Identifier: AGPL-3.0-only
"""The Wikidata name backfill: what it asks for, what it keeps, what it writes.

A visitor who typed "Machu Picchu" as マチュ・ピチュ found nothing, because the
curated rows carry only their Latin name (4,537 of the 4,900 have a QID in
site_external_ids and no name row beyond the one label - read on production
2026-10-04). Wikidata has a label in up to 140 languages for such a site, so the
names are one read-only call per 50 sites away. This pins the three things that
make that safe: the language list is asked within the API's own limit, a name is
never written twice, and the key comes from the one definition.

The fourth case came from a visitor on 2026-10-04, who typed the Telugu name
మాచు పిచ్చు and found nothing: Wikidata's Telugu *label* is the Latin
"machu pichu", and మాచు పిచ్చు is the title of the tewiki article, a different
property. So the article titles are asked for as well, and the pins below cover
them: a name Wikidata labels and an article that titles alike is one row, and a
wiki that is not an article (a Wikivoyage entry, a Wikinews headline) is no name.
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

#: The name the owner typed on 2026-10-04 and the search did not find: Wikidata has
#: no Telugu label for Q676203 (only the Latin transcription "machu pichu"), the
#: Telugu name is the title of the item's article, tewiki.
TELUGU_ARTICLE_TITLE = "మాచు పిచ్చు"


def _entity(labels: dict[str, str], aliases: dict[str, list[str]] | None = None) -> dict:
    return {
        "labels": {lang: {"value": value} for lang, value in labels.items()},
        "aliases": {
            lang: [{"value": v} for v in values] for lang, values in (aliases or {}).items()
        },
    }


def _with_sitelinks(sitelinks: dict[str, str]) -> dict:
    entity = _entity({})
    entity["sitelinks"] = {
        site: {"site": site, "title": title} for site, title in sitelinks.items()
    }
    return entity


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
    assert found[QID] == [
        ("Machu Picchu", "en", "wikidata_alias"),
        ("マチュ・ピチュ", "ja", "wikidata_alias"),
        ("麻丘比丘", "zh", "wikidata_alias"),
    ]
    assert requests_made == 2  # 83 languages, 50 per call
    assert "labels|aliases" in one_call[0]["props"]
    assert one_call[0]["ids"] == QID


def test_the_title_of_the_articles_about_the_site_comes_back_too(monkeypatch):
    """A visitor types the name as the Wikipedia of their language writes it, which
    Wikidata keeps somewhere else than in a label: for Telugu (te) the label is the
    Latin "machu pichu", the article title is మాచు పిచ్చు. Measured 2026-10-04 on
    Q676203, where only the first of the two is a label."""
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)
    calls: list[dict] = []

    def _fake(params: dict[str, str], timeout: int = 45) -> dict:
        calls.append(params)
        return {
            "entities": {
                QID: _with_sitelinks(
                    {
                        "tewiki": TELUGU_ARTICLE_TITLE,
                        "knwiki": "ಮಾಆಛ್ಛು ಪಿಚ್ಚು",
                        "enwiki": "Machu Picchu",
                    }
                )
            }
        }

    monkeypatch.setattr("pipeline.wikidata_name_backfill._http_json", _fake)
    found, _requests_made = fetch_names([QID])
    # The article about the site in the owner's own name is here, and the English one
    # too - dropping the site's own name is plan()'s job, it does not know it yet
    assert found[QID] == [
        ("Machu Picchu", "en", "wikipedia_title"),
        (TELUGU_ARTICLE_TITLE, "te", "wikipedia_title"),
        ("ಮಾಆಛ್ಛು ಪಿಚ್ಚು", "kn", "wikipedia_title"),
    ]
    assert [n for n, _lang, _type in plan([("site-1", "Machu Picchu", QID)], found)[0].rows] == [
        TELUGU_ARTICLE_TITLE,
        "ಮಾಆಛ್ಛು ಪಿಚ್ಚು",
    ]
    # One call, not two: sitelinks ignore the languages filter, so the article titles
    # ride along with the labels (measured 2026-10-04, languages=te|en|kn returned
    # labels for exactly those three and every sitelink).
    assert len(calls) == 2  # 83 languages, 50 per call, each with the sitelinks
    assert "sitelinks" in calls[0]["props"]


def test_a_wiki_that_is_not_an_article_contributes_no_name(monkeypatch):
    """The title of a Wikivoyage entry, a Wikinews headline or a Commons file page is
    a phrase or a set of places, not the name of this one site: ruwikinews titles
    Q676203 "Мачу-Пикчу и другие исторические объекты Перу". The run over all 4,537
    curated QIDs answered with two more of this kind, a source text and a namespace:
    sourceswiki and abstractwiki (measured 2026-10-04)."""
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)
    monkeypatch.setattr(
        "pipeline.wikidata_name_backfill._http_json",
        lambda params, timeout=45: {
            "entities": {
                QID: _with_sitelinks(
                    {
                        "ruwikinews": "Мачу-Пикчу и другие исторические объекты Перу",
                        "dewikivoyage": "Machu Picchu",
                        "commonswiki": "Machu Picchu",
                        "sourceswiki": "Мачу-Пикчу",
                        "abstractwiki": "Machu Picchu",
                        "jawiki": "マチュ・ピチュ",
                    }
                )
            }
        },
    )
    found, _ = fetch_names([QID])
    assert found[QID] == [("マチュ・ピチュ", "ja", "wikipedia_title")]


def test_a_label_keeps_its_type_when_an_article_title_says_the_same(monkeypatch):
    """One name, one row: the constraint uq_usn would drop the second anyway, and the
    label is the name Wikidata itself asserts about the item."""
    monkeypatch.setattr("pipeline.wikidata_name_backfill.PACE_SECONDS", 0)

    def _fake(params: dict[str, str], timeout: int = 45) -> dict:
        entity = _entity({"ja": "マチュ・ピチュ"})
        entity["sitelinks"] = {
            "jawiki": {"site": "jawiki", "title": "マチュ・ピチュ"},
        }
        return {"entities": {QID: entity}}

    monkeypatch.setattr("pipeline.wikidata_name_backfill._http_json", _fake)
    found, _ = fetch_names([QID])
    assert found[QID] == [("マチュ・ピチュ", "ja", "wikidata_alias")]


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
    assert found[QID] == [("Machu Picchu", "de", "wikidata_alias")]


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
    assert found[QID] == [("マチュ・ピチュ", "ja", "wikidata_alias")]


def test_the_sites_own_name_is_not_asked_to_be_written_as_its_own_alias():
    found = {
        QID: [("マチュ・ピチュ", "ja", "wikidata_alias"), ("Machu Picchu", "en", "wikidata_alias")]
    }
    plans = plan([("site-1", "Machu Picchu", QID)], found)
    assert [name for name, _lang, _type in plans[0].rows] == ["マチュ・ピチュ"]


def test_a_site_without_a_label_yields_no_plan_and_asks_for_nothing_to_write():
    plans = plan(
        [("site-1", "Machu Picchu", QID), ("site-2", "Nowhere", "Q1")],
        {QID: [("マチュ・ピチュ", "ja", "wikidata_alias")]},
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
    assert "n.name_type" in sql  # the row says which kind of name it is
    assert "'wikidata_alias'" not in sql, "the type is a bind now, not a constant"
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
        [("site-1", "Machu Picchu", QID)],
        {
            QID: [
                ("マチュ・ピチュ", "ja", "wikidata_alias"),
                (TELUGU_ARTICLE_TITLE, "te", "wikipedia_title"),
            ]
        },
    )[0]
    assert store(session, plan_row) == 2
    (sql, params) = session.log[0]
    assert "INSERT INTO unified_site_names" in sql
    assert params["site_id"] == "site-1"
    assert params["canonical"] == "Machu Picchu"
    assert params["n0"] == "マチュ・ピチュ" and params["l0"] == "ja"
    assert params["t0"] == "wikidata_alias"
    assert params["n1"] == TELUGU_ARTICLE_TITLE and params["l1"] == "te"
    assert params["t1"] == "wikipedia_title"
    assert session.commits == 1, "one commit per site, so a failure keeps what it wrote"


def test_the_run_makes_the_journal_directory_itself(tmp_path, one_call, monkeypatch):
    """The production run died on this: FileNotFoundError, because the caller made
    the directory on the host and only public/data, logs and frontend are mounted
    into the container, so output/ did not exist in there (measured 2026-10-04)."""
    monkeypatch.setattr("pipeline.wikidata_name_backfill.SessionLocal", lambda: _Closed())
    monkeypatch.setattr(
        "pipeline.wikidata_name_backfill.load_sites",
        lambda *a, **k: [("site-1", "Machu Picchu", QID)],
    )
    monkeypatch.setattr(
        "pipeline.wikidata_name_backfill.store", lambda session, plan_row: len(plan_row.rows)
    )
    path = tmp_path / "remediation" / "wikidata_names" / "run.jsonl"
    assert main(["--apply", "--journal", str(path)]) == 0
    assert path.exists(), "the run has to create the directory it journals into"
    written = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["name"] for row in written] == ["Machu Picchu"]
    assert [n["name"] for n in written[0]["names"]] == ["マチュ・ピチュ", "麻丘比丘"]


class _Closed:
    """A session that closes and does nothing else; the store is mocked."""

    def close(self) -> None:
        pass


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
    found = {
        QID: [("マチュ・ピチュ", "ja", "wikidata_alias"), ("麻丘比丘", "zh", "wikidata_alias")]
    }
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
