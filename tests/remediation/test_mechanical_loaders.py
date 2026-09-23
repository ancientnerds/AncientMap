"""Do the planners read production the way their decisions assume?

The classify tests build their candidates and journal links by hand, so nothing there notices a
loader that reads the wrong column's journal, drops `ORDER BY id`, or computes a premise in Python
instead of taking the one the database printed - the premise guard 5 later compares against the
database's own text. These tests drive the four loaders (`plan.load_journal`,
`uk_parts.load_candidates`, `period_name.load_rows`, `site_type_shape.load_rows`) with one fake
reader that answers the SQL they send the way production would, and refuses SQL it does not know.

Added 2026-09-23 (review of the mechanical lanes): none of the four had a test.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

from mechanical import period_name as PN  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical import site_type_shape as S  # noqa: E402
from mechanical import uk_parts as U  # noqa: E402

A_SITE = "037e3715-f5f7-4345-8216-8aa26f404009"
B_SITE = "e0d56737-6459-4329-9ef5-1a46e8d75f10"
OTHER = "0060e6c0-8388-4762-bf51-9a3f88807899"

JOURNAL_SELECT = (
    "SELECT id, row_pk, run_stamp, coalesce(test_id, '') AS test_id, old_value, new_value "
    "FROM remediation_change_log WHERE "
)
QID_SELECT = (
    "SELECT site_id::text AS site_id, value FROM site_external_ids "
    "WHERE kind = 'wikidata_qid' AND site_id::text IN ("
)


def link(id_: int, pk: str, column: str, old: str | None, new: str | None) -> dict[str, Any]:
    return {
        "id": id_,
        "table_name": "unified_sites",
        "column_name": column,
        "row_pk": pk,
        "run_stamp": f"stamp-{id_}",
        "test_id": f"test-{id_}",
        "old_value": old,
        "new_value": new,
    }


#: Stored out of id order on purpose: a reader that forgets `ORDER BY id` gets them this way.
JOURNAL = [
    link(9, A_SITE, "country", "United Kingdom", "Northern Ireland"),
    link(3, A_SITE, "country", "Ireland", "United Kingdom"),
    link(5, A_SITE, "site_type", "Monument", "suspect_modern"),
    link(7, B_SITE, "country", "Wales", "England"),
    link(8, OTHER, "country", "Georgia (country)", "Georgia"),
    link(4, A_SITE, "period_name", "< 4500 BC", "4500 - 3000 BC"),
    link(2, A_SITE, "period_start", "-5000", "-4000"),
]


class FakeReader:
    """`psql_json_reader()` as production answers it: rows as JSON objects, per the SQL's own
    predicates. A query shape or predicate it does not know is an error, never an empty answer."""

    def __init__(self, rows: dict[str, list[dict[str, Any]]], journal: list[dict[str, Any]]):
        self.rows = rows
        self.journal = journal
        self.sent: list[str] = []

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.sent.append(sql)
        if sql in self.rows:
            return [dict(r) for r in self.rows[sql]]
        if sql.startswith(QID_SELECT):
            wanted = re.findall(r"'([0-9a-f-]{36})'", sql)
            got = [{"site_id": pk, "value": f"Q{n}"} for n, pk in enumerate(wanted, start=100)]
            return sorted(got, key=lambda r: r["value"])
        if sql.startswith(JOURNAL_SELECT):
            where = sql[len(JOURNAL_SELECT) :]
            ordered = where.endswith(" ORDER BY id")
            rows = list(self.journal)
            for predicate in where.removesuffix(" ORDER BY id").split(" AND "):
                rows = self._filter(rows, predicate)
            if ordered:
                rows.sort(key=lambda r: r["id"])
            keys = ("id", "row_pk", "run_stamp", "test_id", "old_value", "new_value")
            return [{k: r[k] for k in keys} for r in rows]
        raise AssertionError(f"a statement the fake does not answer: {sql[:90]!r}")

    @staticmethod
    def _filter(rows: list[dict[str, Any]], predicate: str) -> list[dict[str, Any]]:
        if m := re.fullmatch(r"(table_name|column_name) = '(\w+)'", predicate):
            return [r for r in rows if r[m[1]] == m[2]]
        if m := re.fullmatch(r"row_pk IN \((.*)\)", predicate):
            return [r for r in rows if r["row_pk"] in re.findall(r"'([^']*)'", m[1])]
        raise AssertionError(f"a predicate the fake does not know: {predicate!r}")


# ---------------------------------------------------------------------------- the journal
def test_load_journal_reads_one_column_oldest_first() -> None:
    reader = FakeReader({}, JOURNAL)
    got = P.load_journal(reader, "country", [A_SITE, B_SITE])
    assert set(got) == {A_SITE, B_SITE}
    assert [k.id for k in got[A_SITE]] == [3, 9], "one column, in id order"
    assert (got[A_SITE][0].old_value, got[A_SITE][-1].new_value) == ("Ireland", "Northern Ireland")
    assert [k.id for k in got[B_SITE]] == [7]
    assert OTHER not in got
    assert got[A_SITE][0] == P.JournalLink(3, "stamp-3", "test-3", "Ireland", "United Kingdom")


def test_load_journal_reads_nothing_for_no_sites() -> None:
    reader = FakeReader({}, JOURNAL)
    assert P.load_journal(reader, "country", []) == {}
    assert reader.sent == []


# ---------------------------------------------------------------------------- the UK lane
UK_ROWS = [
    {
        "id": A_SITE,
        "name": "Boa Island",
        "country": "United Kingdom",
        "lat": "54.5168",
        "lon": "-7.8333",
        "source_id": "ancient_nerds",
        "premise": "the point as the database printed it",
    },
    {
        "id": B_SITE,
        "name": "Somewhere",
        "country": "Ireland",
        "lat": None,
        "lon": None,
        "source_id": "ancient_nerds",
        "premise": None,
    },
]


def test_the_uk_candidates_carry_the_database_s_premise_qids_and_country_chain() -> None:
    reader = FakeReader({U.CANDIDATE_SQL: UK_ROWS}, JOURNAL)
    candidates = {c.site.site_id: c for c in U.load_candidates(reader)}
    boa = candidates[A_SITE]
    assert boa.premise == "the point as the database printed it"
    assert (boa.site.lat, boa.site.lon, boa.site.country) == (54.5168, -7.8333, "United Kingdom")
    assert [k.id for k in boa.journal] == [3, 9]
    assert boa.qids == ("Q100",)
    assert candidates[B_SITE].site.lat is None and candidates[B_SITE].premise is None
    assert reader.sent[0] == U.CANDIDATE_SQL


def test_no_uk_candidate_is_refused_not_planned_empty() -> None:
    with pytest.raises(P.PlanError, match="nothing to plan"):
        U.load_candidates(FakeReader({U.CANDIDATE_SQL: []}, JOURNAL))


# ------------------------------------------------------------------------- the period lane
PERIOD_ROWS = [
    {
        "id": A_SITE,
        "name": "Boa Island",
        "source_id": "ancient_nerds",
        "period_name": "4500 - 3000 BC",
        "period_start": -4000,
        "premise": "-4000 as printed",
    }
]


def test_the_period_rows_carry_both_journals_and_the_printed_year() -> None:
    reader = FakeReader({PN.ROW_SQL: PERIOD_ROWS}, JOURNAL)
    (row,) = PN.load_rows(reader)
    assert row.premise == "-4000 as printed" and row.period_start == -4000
    assert [k.id for k in row.name_journal] == [4]
    assert [k.id for k in row.start_journal] == [2]
    assert (row.name_journal[0].new_value, row.start_journal[0].new_value) == (
        "4500 - 3000 BC",
        "-4000",
    )


def test_no_period_row_is_refused() -> None:
    with pytest.raises(P.PlanError, match="empty set"):
        PN.load_rows(FakeReader({PN.ROW_SQL: []}, JOURNAL))


# ---------------------------------------------------------------------- the site_type lane
def test_the_site_type_rows_carry_their_own_journal() -> None:
    rows = [{"id": A_SITE, "name": "Boa Island", "source_id": "ancient_nerds", "site_type": "x_y"}]
    (row,) = S.load_rows(FakeReader({S.ROW_SQL: rows}, JOURNAL))
    assert row.site_type == "x_y"
    assert [k.id for k in row.journal] == [5]
    assert row.journal[0].old_value == "Monument"
