"""Does the phase-3 acceptance follow the journal chain - and stay strict while it does?

`output/remediation/tools/verify_writes.py` decides in a pure function (`judge`) from the plan, the
journal and the live values. These tests fabricate all three: a phase-3 write that stands, one that a
later journalled lane superseded (the B9 shape), a broken chain, a live value the journal does not
end at, and the planned fields phase 3 did not write. No database.

Added 2026-09-23: a phase-3 write its own `-rollback` reversed, and a phase-3 row outside the plan
or outside `unified_sites`, are deviations - and `main` is run against a fake psql that applies
every predicate of the SQL it receives, so a read narrowed to the planned rows goes red.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "output" / "remediation" / "tools" / "verify_writes.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("verify_writes", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_writes"] = module
    spec.loader.exec_module(module)
    return module


V = _load()

GIANTS_RING = "e0d56737-6459-4329-9ef5-1a46e8d75f10"
DAMASCUS = "17cf019a-0000-4000-8000-000000000001"
HELD = "22222222-2222-2222-2222-222222222222"
P3 = "phase3:batch-0148:chunk-0001"
UK = "2026-09-22_mechanical-uk-parts"


def planned(pk: str, column: str, old: Any) -> dict[str, Any]:
    return {"pk": pk, "column": column, "old_value": old, "site_name": f"site {pk[:4]}"}


def stored(country: str | None = None, period_start: str | None = None) -> list[str | None]:
    return ["Monument", period_start, country]  # COLUMNS order: site_type, period_start, country


def test_a_phase3_write_that_stands_is_accepted() -> None:
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("United Kingdom")},
    )
    assert verdict.deviations == [] and verdict.written == 1 and not verdict.superseded


def test_a_superseded_phase3_write_is_reported_by_stamp_not_as_a_deviation() -> None:
    """B9: phase 3 wrote `United Kingdom`, the UK lane respelled it `Northern Ireland`."""
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "United Kingdom", "Northern Ireland"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert verdict.deviations == []
    assert verdict.superseded == {UK: 1}


def test_a_broken_chain_is_a_deviation() -> None:
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "Wales", "Northern Ireland"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert len(verdict.deviations) == 1 and "BROKEN CHAIN" in verdict.deviations[0]


def test_a_live_value_the_journal_does_not_end_at_is_a_deviation() -> None:
    """The per-row check this replaces, kept: an unjournalled write after phase 3 is caught."""
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert len(verdict.deviations) == 1 and "NOT NEW" in verdict.deviations[0]


def test_a_missing_site_is_a_deviation() -> None:
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge([planned(GIANTS_RING, "country", "Ireland")], links, {})
    assert verdict.deviations == [f"  MISSING      {GIANTS_RING} (country)"]
    held = V.judge([planned(HELD, "period_start", -500)], [], {})
    assert len(held.deviations) == 1 and "MISSING" in held.deviations[0]


def test_a_held_field_that_still_holds_its_old_value_is_accepted() -> None:
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], [], {HELD: stored(period_start="-500")}
    )
    assert verdict.deviations == [] and verdict.untouched == 1


def test_a_held_field_changed_without_a_journal_row_is_a_deviation() -> None:
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], [], {HELD: stored(period_start="-43000")}
    )
    assert len(verdict.deviations) == 1 and "CHANGED ANYWAY" in verdict.deviations[0]


def test_a_held_field_a_later_lane_journalled_is_superseded() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-43000")}
    )
    assert verdict.deviations == [] and verdict.superseded == {"2026-10-01_search": 1}


def test_a_later_chain_on_a_held_field_must_start_from_the_planned_old_value() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-700", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-43000")}
    )
    assert len(verdict.deviations) == 1 and "the plan had '-500'" in verdict.deviations[0]


def test_a_later_chain_on_a_held_field_must_end_at_the_live_value() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-40000")}
    )
    assert len(verdict.deviations) == 1 and "the row holds '-40000'" in verdict.deviations[0]


def test_a_later_chain_on_a_held_field_must_be_unbroken() -> None:
    links = [
        V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000"),
        V.Link(6, "2026-10-02_search", "period_start", HELD, "-42000", "-40000"),
    ]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-40000")}
    )
    assert len(verdict.deviations) == 1 and "starts from '-42000'" in verdict.deviations[0]


def test_a_field_outside_the_three_columns_is_not_judged() -> None:
    """period_name is not a phase-3 column; the period lane's rows are not this acceptance's."""
    links = [V.Link(7, P3, "period_name", DAMASCUS, "1 - 500 AD", "1500+ AD")]
    verdict = V.judge([], links, {})
    assert verdict.deviations == [] and verdict.written == 0


# ------------------------------------------------ 2026-09-23: rollbacks and the plan's edge
P3_ROLLBACK = P3 + "-rollback"
OUTSIDE = "99999999-9999-4999-8999-999999999999"


def test_a_rolled_back_phase3_write_is_not_accepted() -> None:
    """The writer's reversal stamp starts with `phase3:batch-` too. The 2026-09-22 judge counted
    it as the phase-3 write and passed the field with no deviation and no superseded line."""
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(2, P3_ROLLBACK, "country", GIANTS_RING, "United Kingdom", "Ireland"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")], links, {GIANTS_RING: stored("Ireland")}
    )
    assert len(verdict.deviations) == 1 and "REVERTED" in verdict.deviations[0]
    assert P3_ROLLBACK in verdict.deviations[0]
    assert verdict.written == 1 and not verdict.superseded


def test_a_phase3_rollback_alone_is_not_a_phase3_write() -> None:
    """A reversal whose write the journal does not hold: the field was not written by phase 3."""
    links = [V.Link(2, P3_ROLLBACK, "country", GIANTS_RING, "United Kingdom", "Ireland")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")], links, {GIANTS_RING: stored("Ireland")}
    )
    assert verdict.written == 0 and verdict.untouched == 1
    assert len(verdict.deviations) == 1 and "BROKEN CHAIN" in verdict.deviations[0]


def test_a_phase3_rollback_on_a_field_phase3_never_wrote_is_a_deviation() -> None:
    """Even when the chain is continuous and ends at the live value, a phase-3 reversal on a field
    phase 3 did not write is no later lane's write: it is reported, never counted as superseded."""
    links = [
        V.Link(1, UK, "country", HELD, "Ireland", "Northern Ireland"),
        V.Link(2, P3_ROLLBACK, "country", HELD, "Northern Ireland", "Ireland"),
    ]
    verdict = V.judge([planned(HELD, "country", "Ireland")], links, {HELD: stored("Ireland")})
    assert len(verdict.deviations) == 1 and "phase-3 rollback" in verdict.deviations[0]
    assert not verdict.superseded


def test_a_later_lane_s_rollback_is_reported_by_its_stamp() -> None:
    """The UK lane written and reversed: the phase-3 value stands again, and the reversal is named."""
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "United Kingdom", "Northern Ireland"),
        V.Link(12, UK + "-rollback", "country", GIANTS_RING, "Northern Ireland", "United Kingdom"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")], links, {GIANTS_RING: stored("United Kingdom")}
    )
    assert verdict.deviations == [] and verdict.superseded == {UK + "-rollback": 1}


def test_a_phase3_journal_row_outside_the_plan_is_a_deviation() -> None:
    """The per-row check this replaced reported it (`FEHLT`); the chain judge must too."""
    links = [V.Link(3, P3, "country", OUTSIDE, "Ireland", "United Kingdom")]
    verdict = V.judge([], links, {OUTSIDE: stored("United Kingdom")})
    assert len(verdict.deviations) == 1 and "OUTSIDE PLAN" in verdict.deviations[0]
    assert P3 in verdict.deviations[0]


def test_a_phase3_row_of_an_unplanned_column_of_a_planned_site_is_a_deviation() -> None:
    links = [V.Link(3, P3, "site_type", GIANTS_RING, "Monument", "Cairn")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")], links, {GIANTS_RING: stored("Ireland")}
    )
    assert any("OUTSIDE PLAN" in d and "site_type" in d for d in verdict.deviations)


def test_a_phase3_row_outside_unified_sites_is_a_deviation() -> None:
    links = [V.Link(4, P3, "country", GIANTS_RING, "Ireland", "UK", table="card_stats")]
    verdict = V.judge([], links, {})
    assert len(verdict.deviations) == 1 and "OUTSIDE TABLE" in verdict.deviations[0]


def test_a_later_lane_s_row_outside_the_plan_is_not_this_acceptance_s() -> None:
    """A mechanical lane's own rows on fields phase 3 never planned are accepted by that lane."""
    links = [V.Link(5, UK, "country", OUTSIDE, "Ireland", "Northern Ireland")]
    verdict = V.judge([], links, {OUTSIDE: stored("Northern Ireland")})
    assert verdict.deviations == [] and verdict.written == 0


# ------------------------------------------------------------- main(), against a fake psql
class FakeJournalDb:
    """Answers the SQL `main` sends by applying every predicate of its WHERE clause, and refuses
    a predicate it does not know - so a query narrowed to the planned rows reads less, as the real
    database would, and a test that needs the unplanned row goes red."""

    def __init__(self, journal: list[Any], sites: dict[str, list[str | None]]) -> None:
        self.journal = journal
        self.sites = sites
        self.sent: list[str] = []

    def __call__(self, sql: str) -> list[list[str]]:
        self.sent.append(sql)
        if " FROM remediation_change_log WHERE " in sql:
            where = sql.split(" WHERE ", 1)[1].rsplit(" ORDER BY id;", 1)[0]
            rows = list(self.journal)
            for predicate in where.strip().split(" AND "):
                rows = self._filter(rows, predicate.strip())
            return [
                [
                    str(k.id),
                    k.stamp,
                    k.table,
                    k.column,
                    k.pk,
                    V.NULL if k.old is None else k.old,
                    V.NULL if k.new is None else k.new,
                ]
                for k in sorted(rows, key=lambda k: k.id)
            ]
        if sql.startswith("SELECT id, coalesce(") and " FROM unified_sites WHERE id IN " in sql:
            wanted = re.findall(r"'([0-9a-f-]{36})'", sql)
            return [
                [pk, *(V.NULL if v is None else v for v in self.sites[pk])]
                for pk in wanted
                if pk in self.sites
            ]
        raise AssertionError(f"a statement the fake does not answer: {sql[:90]!r}")

    @staticmethod
    def _filter(rows: list[Any], predicate: str) -> list[Any]:
        if m := re.fullmatch(r"run_stamp LIKE '([^%']*)%'", predicate):
            return [k for k in rows if k.stamp.startswith(m[1])]
        if m := re.fullmatch(r"table_name = '(\w+)'", predicate):
            return [k for k in rows if k.table == m[1]]
        if m := re.fullmatch(r"column_name IN \((.*)\)", predicate):
            return [k for k in rows if k.column in re.findall(r"'([^']*)'", m[1])]
        if m := re.fullmatch(r"row_pk IN \((.*)\)", predicate):
            return [k for k in rows if k.pk in re.findall(r"'([^']*)'", m[1])]
        raise AssertionError(f"a predicate the fake does not know: {predicate!r}")


def _run_main(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
    rows: list[dict[str, Any]],
    journal: list[Any],
    sites: dict[str, list[str | None]],
) -> tuple[int, str]:
    path = tmp_path / "ALL_ROWS.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(V, "psql", FakeJournalDb(journal, sites))
    code = V.main(["--rows", str(path)])
    return code, capsys.readouterr().out


def test_main_accepts_the_b9_shape_and_names_the_later_stamp(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    journal = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "United Kingdom", "Northern Ireland"),
    ]
    code, out = _run_main(
        tmp_path,
        monkeypatch,
        capsys,
        [planned(GIANTS_RING, "country", "Ireland")],
        journal,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert code == 0 and "RESULT: 0 deviation(s)" in out
    assert f"1 field(s) superseded by the later journalled write {UK}" in out
    assert "1 phase-3 field(s) journalled, 0 planned field(s) phase 3 did not write" in out


def test_main_reads_every_phase3_row_not_only_the_planned_ones(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """The 2026-09-22 main read the journal for the planned rows only (`row_pk IN (<plan>)`), so a
    phase-3 write to a site outside the plan was never seen: RESULT 0, exit 0."""
    journal = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(2, P3, "country", OUTSIDE, "Ireland", "United Kingdom"),
    ]
    code, out = _run_main(
        tmp_path,
        monkeypatch,
        capsys,
        [planned(GIANTS_RING, "country", "Ireland")],
        journal,
        {GIANTS_RING: stored("United Kingdom"), OUTSIDE: stored("United Kingdom")},
    )
    assert code == 1 and "OUTSIDE PLAN" in out and OUTSIDE in out
    assert "RESULT: 1 deviation(s)" in out


def test_main_reads_phase3_rows_of_every_table(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    journal = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(2, P3, "country", GIANTS_RING, "Ireland", "UK", table="card_stats"),
    ]
    code, out = _run_main(
        tmp_path,
        monkeypatch,
        capsys,
        [planned(GIANTS_RING, "country", "Ireland")],
        journal,
        {GIANTS_RING: stored("United Kingdom")},
    )
    assert code == 1 and "OUTSIDE TABLE  card_stats.country" in out


def test_main_reports_a_reverted_write(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    journal = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(2, P3_ROLLBACK, "country", GIANTS_RING, "United Kingdom", "Ireland"),
    ]
    code, out = _run_main(
        tmp_path,
        monkeypatch,
        capsys,
        [planned(GIANTS_RING, "country", "Ireland")],
        journal,
        {GIANTS_RING: stored("Ireland")},
    )
    assert code == 1 and "REVERTED" in out
