"""Does the `country-d84` lane empty exactly the country D84 takes away - and refuse everything else?

Owner decisions D84 (2026-11-05) and D149 (2026-11-10): the Baltic Sea Anomaly lies in
international waters, holds no country and is shown on the globe only - no country page, no
`/sites/` route. `country_d84.classify` decides the row from its live state and its journal; the
lane (`lane.COUNTRY_D84`) writes NULL into one cell and proves inside the transaction that a
planned site holds no country afterwards and is one D84 names. The invariant's predicate runs in
SQLite over the rows it must refuse and the row it must let through. Nothing here opens a socket
or touches a database (`mechanical/mutation_sweep.py "d84"`).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mechanical import apply as A  # noqa: E402
from mechanical import country_d84 as C  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

BALTIC = "c8d2c13e-fd9a-466c-9fdc-fc26ee798ded"
YONAGUNI = "01296632-a2a1-4610-a4a9-d0c3be77b788"
#: The row as production holds it (read-only, 2026-11-11): retired, 'Baltic Sea', never journalled.
PREMISE = "Baltic Sea Anomaly | 61.37676947509479 | 18.448311841356542"
LANE = L.COUNTRY_D84


def row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": BALTIC,
        "name": "Baltic Sea Anomaly",
        "country": "Baltic Sea",
        "source_id": "ancient_nerds",
        "scope_status": "retired",
        "premise": PREMISE,
    }
    base.update(over)
    return base


def read_text(
    sites: list[dict[str, Any]] | None = None,
    journal: list[dict[str, Any]] | None = None,
    stamps: list[dict[str, Any]] | None = None,
) -> str:
    """The text of `read_parts`' tagged export."""
    lines = [json.dumps({"kind": "site", "row": r}) for r in ([row()] if sites is None else sites)]
    lines += [json.dumps({"kind": "journal", "row": r}) for r in journal or []]
    lines += [json.dumps({"kind": "stamp", "row": r}) for r in stamps or []]
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-11-11 07:00:00+00"}}))
    return "\n".join(lines) + "\n"


def record(old: str | None = "Baltic Sea", new: str | None = None, **over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": BALTIC,
        "site_name": "Baltic Sea Anomaly",
        "old_value": old,
        "new_value": new,
        "rule": C.RULE,
        "condition": "c",
        "reason": "r",
        "evidence": ({"source": "s", "quote": "q"},),
        "premise": PREMISE,
        "column": "country",
    }
    base.update(over)
    return A.ChangeRecord(**base)


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_its_identity_and_its_one_emptied_cell(self) -> None:
        assert (LANE.name, LANE.run_stamp) == ("country-d84", "2026-11-11_mechanical-country-d84")
        assert (LANE.test_id, LANE.out_dir_name) == ("D84/country", "mechanical_country_d84")
        assert LANE.target is L.UNIFIED_SITES and LANE.columns == ("country",)
        (cell,) = LANE.cells
        assert cell.clears and not cell.fills_null and cell.allowed_new_values == ()
        assert (cell.sql_type, cell.max_chars) == ("character varying", 100)
        assert LANE.premise_sql == L.COUNTRY_D84_PREMISE_SQL

    def test_apply_resolves_it_and_reads_it_back(self) -> None:
        assert L.resolve_lane("country-d84") is LANE and L.LANES["country-d84"] is LANE
        readback = A.readback_for(LANE)
        assert readback == L.COUNTRY_D84_READBACK
        for metric in (
            "curated rows D84 leaves without a country that still hold one",
            "curated rows without a country",
            "curated shown rows without a country that D84 does not name",
            "rows country = ''Baltic Sea''",
            "card_stats rows whose civilization differs from the site country",
            "journal rows for this run stamp",
        ):
            assert metric in readback, metric
        assert f"'{LANE.run_stamp}'" in readback and f"'{BALTIC}'" in readback

    def test_the_sites_d84_names_are_d50_sites_with_the_country_they_held(self) -> None:
        assert L.D84_NO_COUNTRY_SITES == {BALTIC: ("Baltic Sea Anomaly", "Baltic Sea")}
        for site_id, (name, _held) in L.D84_NO_COUNTRY_SITES.items():
            assert L.D50_DISPUTED_SITES[site_id] == name
        assert L.d84_site_sql("u") == f"CAST(u.id AS text) IN ('{BALTIC}')"

    def test_the_clear_and_its_reversal_are_valid_and_nothing_fills_a_null(self) -> None:
        A.validate_records([record()], lane=LANE)
        A.validate_records([record(None, "Baltic Sea")], lane=LANE, rollback=True)
        with pytest.raises(P.PlanError, match="is not a column this lane fills"):
            A.validate_records([record(None, "Sweden")], lane=LANE)
        with pytest.raises(P.PlanError, match="NULL to NULL"):
            A.validate_records([record(None, None)], lane=LANE)
        with pytest.raises(P.PlanError, match="is not a column this lane writes"):
            A.validate_records([record(column="name")], lane=LANE)
        with pytest.raises(P.PlanError, match="carries no premise"):
            A.validate_records([record(premise=None)], lane=LANE)

    def test_the_transaction_carries_the_guards_and_the_invariant(self) -> None:
        sql = A.render_transaction([record()], site_ids={BALTIC}, lane=LANE)
        guard2 = sql.split("scope guard 2")[1].split("scope guard 3")[0]
        assert "p.old_value IS NULL" in guard2 and "p.new_value IS NULL" not in guard2
        assert "scope guard 5" in sql and LANE.premise_sql in sql
        (invariant,) = LANE.site_invariants
        assert invariant.predicate in sql and invariant.says in sql
        assert "'unified_sites', r.column_name, 'id'" in sql
        undo = P.render_rollback_sql([record()], site_ids={BALTIC}, lane=LANE)
        assert f"'{LANE.rollback_run_stamp}'" in undo and invariant.predicate not in undo

    def test_the_invariant_has_its_probe(self) -> None:
        foreign = {"id": "11111111-1111-1111-1111-111111111111", "name": "x", "premise": "p"}
        probes = {case[0]: case[2] for case in A.probe_cases([record()], LANE, foreign)}
        assert {"invariant-country", "guard5-premise", "guard3-foreign-old-value"} <= set(probes)
        assert probes["invariant-country"][0].new_value == "Sweden"
        assert A.unprobed_invariants([record()], LANE) == []


class TestTheInvariantInSql:
    """`COUNTRY_D84`'s site invariant over the written row `u`: TRUE refuses the whole write."""

    def violators(self, rows: list[tuple[str, str | None]]) -> set[str]:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, country TEXT)")
        db.executemany("INSERT INTO unified_sites VALUES (?, ?)", rows)
        (invariant,) = LANE.site_invariants
        return {
            r[0]
            for r in db.execute(f"SELECT u.id FROM unified_sites u WHERE {invariant.predicate}")
        }

    def test_a_planned_site_holds_no_country_and_is_one_d84_names(self) -> None:
        assert self.violators([(BALTIC, None)]) == set()
        assert self.violators([(BALTIC, "Sweden")]) == {BALTIC}, "the probe's value"
        assert self.violators([(BALTIC, "Baltic Sea")]) == {BALTIC}
        assert self.violators([(BALTIC, "")]) == {BALTIC}, "an empty string is not no country"
        assert self.violators([(YONAGUNI, None)]) == {YONAGUNI}, "D84 names one site"

    def test_the_residual_counts_a_d84_site_that_still_holds_a_country(self) -> None:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, source_id TEXT, country TEXT)")
        sql = (
            "SELECT count(*) FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
            + LANE.post_commit_residual.predicate
        )
        db.execute("INSERT INTO unified_sites VALUES (?, 'ancient_nerds', 'Baltic Sea')", (BALTIC,))
        db.execute("INSERT INTO unified_sites VALUES (?, 'ancient_nerds', 'Japan')", (YONAGUNI,))
        assert db.execute(sql).fetchone() == (1,)
        db.execute("UPDATE unified_sites SET country = NULL WHERE id = ?", (BALTIC,))
        assert db.execute(sql).fetchone() == (0,)
        assert LANE.rehearsal_residual is LANE.post_commit_residual


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_the_retired_row_is_emptied_on_its_name_and_point(self) -> None:
        v = C.classify(BALTIC, row(), ())
        assert v.ok, v.note
        assert (v.old_value, v.new_value, v.column, v.rule) == (
            "Baltic Sea",
            None,
            "country",
            "d84-no-country",
        )
        assert v.premise == PREMISE and v.finding_test_id == "D84/country"
        assert [e["source"] for e in v.evidence] == [C.DECISION_SOURCE, C.DECISION_SOURCE]
        assert v.evidence[0]["quote"].startswith("D84 (2026-11-05): ")
        assert v.evidence[1]["quote"].startswith("D149 (2026-11-10): ")
        assert C.classify(BALTIC, row(scope_status="in_scope"), ()).ok, "shown or not: no country"

    def test_the_decisions_are_quoted_as_the_decisions_file_words_them(self) -> None:
        text = (REPO / C.DECISION_SOURCE).read_text(encoding="utf-8")
        for needle in (
            "| D84 | D50 country of the Baltic Sea Anomaly | **Empty / international waters, no "
            "country page** (rec). |",
            "| D149 | Baltic Sea Anomaly without a country (D84) has no /sites/ page at all | "
            "**Globe only** (rec): no route without a country. |",
        ):
            assert needle in text
        quotes = " ".join(d["quote"] for d in C.DECISIONS)
        assert "Empty / international waters, no country page (rec)." in quotes
        assert "Globe only (rec): no route without a country." in quotes

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"source_id": "lyra"}, "row-not-in-curated-source"),
            ({"name": "Baltic Sea anomaly (sonar image)"}, "name-moved"),
            ({"country": None}, "already-empty"),
            ({"country": "Sweden"}, "stored-value-moved"),
        ],
    )
    def test_each_check_refuses_on_its_own(self, change: dict[str, Any], reason: str) -> None:
        v = C.classify(BALTIC, row(**change), ())
        assert not v.ok and v.reason == reason, v
        assert v.premise is None and v.rule == "" and v.evidence == ()

    def test_a_journal_that_does_not_end_at_the_live_value_refuses(self) -> None:
        link = P.JournalLink(1, "2026-09-21_x", "T05", "Baltic", "Ostsee")
        v = C.classify(BALTIC, row(), (link,))
        assert not v.ok and v.reason == "journal-disagrees"
        ends_here = P.JournalLink(1, "2026-09-21_x", "T05", "Ostsee", "Baltic Sea")
        assert C.classify(BALTIC, row(), (ends_here,)).ok


class TestThePlan:
    def test_the_read_is_one_read_only_snapshot_of_the_decided_row(self) -> None:
        script = P.tagged_export_script(C.read_parts())
        assert "REPEATABLE READ READ ONLY" in script
        for verb in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE"):
            assert verb not in script.upper(), verb
        parts = dict(C.read_parts())
        assert f"'{BALTIC}'" in parts["site"] and f"{LANE.premise_sql} AS premise" in parts["site"]
        assert "column_name = 'country'" in parts["journal"]
        for stamp in (LANE.run_stamp, LANE.rollback_run_stamp):
            assert f"'{stamp}'" in parts["stamp"]

    def test_the_plan_is_the_one_cell_and_its_counters(self) -> None:
        plan = C.build_plan(read_text(), built_at="t")
        assert plan.lane is LANE and plan.skipped == ()
        assert plan.counters == {"candidates": 1, "changes": 1, "skipped": 0}
        (change,) = plan.changes
        assert (change.site_id, change.old_value, change.new_value) == (BALTIC, "Baltic Sea", None)
        emptied = C.build_plan(read_text([row(country=None)]), built_at="t")
        assert emptied.changes == ()
        assert emptied.counters == {
            "candidates": 1,
            "changes": 0,
            "skipped": 1,
            "skip:already-empty": 1,
        }

    def test_the_journal_of_the_cell_reaches_the_decision(self) -> None:
        wrote_other = {
            "id": 7, "row_pk": BALTIC, "run_stamp": "s", "test_id": "", "old_value": None,
            "new_value": "Ostsee",
        }  # fmt: skip
        plan = C.build_plan(read_text(journal=[wrote_other]), built_at="t")
        assert [v.reason for v in plan.skipped] == ["journal-disagrees"]

    def test_a_row_the_read_lost_and_a_lane_that_has_written_stop_the_plan(self) -> None:
        with pytest.raises(P.PlanError, match=f"Baltic Sea Anomaly .{BALTIC}. is not in"):
            C.build_plan(read_text([]), built_at="t")
        for stamp in (LANE.run_stamp, LANE.rollback_run_stamp):
            with pytest.raises(P.PlanError, match="a lane that has written is never re-planned"):
                C.build_plan(read_text(stamps=[{"run_stamp": stamp, "n": 1}]), built_at="t")


class TestTheFiles:
    def test_write_keeps_the_read_and_delivers_the_plan_with_its_undo(self, tmp_path: Path) -> None:
        sent: list[str] = []

        def read(script: str) -> str:
            sent.append(script)
            return read_text()

        out = tmp_path / "mechanical_country_d84"
        result = C.write(out, read=read, built_at="2026-11-11T07:00:00+00:00")
        assert result == {
            "candidates": 1,
            "changes": 1,
            "skipped": 0,
            "lane": "country-d84",
            "dir": str(out),
        }
        assert sent == [P.tagged_export_script(C.read_parts())]
        assert (out / "READ.jsonl").read_text(encoding="utf-8") == read_text()
        records = A.load_records(out / "PLAN.jsonl")
        A.validate_records(records, lane=LANE)
        assert [(r.site_id, r.column, r.old_value, r.new_value, r.premise) for r in records] == [
            (BALTIC, "country", "Baltic Sea", None, PREMISE)
        ]
        assert (out / "SKIPPED.jsonl").read_text(encoding="utf-8") == ""
        P.verify_pinned(
            out / "ROLLBACK.sql",
            plan_path=out / "PLAN.jsonl",
            expected=A.rollback_statement(records, LANE),
        )
        assert A.emit(records, out, LANE, plan_path=out / "PLAN.jsonl") == 1
        plan_md = (out / "PLAN.md").read_text(encoding="utf-8")
        assert (
            "| `Baltic Sea` | NULL |" in plan_md and "--lane country-d84 --probe-guards" in plan_md
        )
        with pytest.raises(P.PlanError, match="a delivered plan is never replaced"):
            C.write(out, read=read, built_at="t")
        assert len(sent) == 1, "a delivered plan is refused before production is read"

    def test_a_read_that_leaves_nothing_to_write_delivers_no_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        emptied = read_text([row(country=None)])
        with pytest.raises(
            P.PlanError, match="nothing to write - Baltic Sea Anomaly: already-empty"
        ):
            C.write(tmp_path / "out", read=lambda _script: emptied, built_at="t")
        assert not (tmp_path / "out").exists()
        monkeypatch.setattr(C, "read_production", lambda _script: emptied)
        assert C.main(["--write", "--out", str(tmp_path / "cli")]) == 1
        assert "REFUSED: the read leaves nothing to write" in capsys.readouterr().err
