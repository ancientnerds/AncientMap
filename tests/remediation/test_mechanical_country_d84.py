"""Does a `country-d84-<wave>` lane empty exactly the country D84 takes away - and refuse everything else?

Owner decisions D84 (2026-11-05) and D149 (2026-11-10): the Baltic Sea Anomaly lies in
international waters, holds no country and is shown on the globe only - no country page, no
`/sites/` route. `country_d84.classify` decides the row from its live state and its journal; the
lane (`identity_lanes.country_d84_lane`) writes NULL into one cell and proves inside the
transaction that a planned site holds no country afterwards and is one D84 names. The invariant's
predicate runs in SQLite over the rows it must refuse and the row it must let through. The site
is written while it is retired, and the premise holds that: the lane's reversal refuses a shown
site, and a write that was undone is planned again under the next wave label. Nothing here opens
a socket or touches a database (`mechanical/mutation_sweep.py "d84"`).
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
from mechanical import identity_lanes as IL  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

BALTIC = "c8d2c13e-fd9a-466c-9fdc-fc26ee798ded"
YONAGUNI = "01296632-a2a1-4610-a4a9-d0c3be77b788"
#: The row as production holds it (read-only, 2026-11-11): retired, 'Baltic Sea', never journalled.
PREMISE = "Baltic Sea Anomaly | 61.37676947509479 | 18.448311841356542 | retired"
WAVE = "2026-11-11"
LANE = IL.country_d84_lane(WAVE)
#: The wave a write that was undone is made again under.
REDO = IL.country_d84_lane("2026-11-11b")


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
        assert LANE.name == LANE.key_prefix == "country-d84-2026-11-11"
        assert LANE.run_stamp == "2026-11-11_mechanical-country-d84"
        assert LANE.test_id == "D84/country"
        assert LANE.out_dir_name == "mechanical_country_d84/2026-11-11"
        assert LANE.target is L.UNIFIED_SITES and LANE.columns == ("country",)
        (cell,) = LANE.cells
        assert cell.clears and not cell.fills_null and cell.allowed_new_values == ()
        assert (cell.sql_type, cell.max_chars) == ("character varying", 100)
        assert LANE.premise_sql == IL.COUNTRY_D84_PREMISE_SQL

    def test_a_wave_has_a_stamp_keys_and_a_directory_of_its_own(self) -> None:
        """A stamp is applied once (`apply.py` refuses a stamp that journals rows): one fixed
        stamp would leave D84 unwritable after its first undo (review of 2026-11-11)."""
        assert REDO.name == "country-d84-2026-11-11b"
        assert REDO.run_stamp == "2026-11-11b_mechanical-country-d84"
        assert REDO.out_dir_name == "mechanical_country_d84/2026-11-11b"
        for of in (
            lambda lane: lane.run_stamp,
            lambda lane: lane.rollback_run_stamp,
            lambda lane: lane.probe_run_stamp,
            lambda lane: lane.change_key(BALTIC, "country"),
            lambda lane: lane.rollback_change_key(BALTIC, "country"),
            A.lane_dir,
        ):
            assert of(REDO) != of(LANE)
        assert (REDO.test_id, REDO.cells, REDO.site_invariants, REDO.premise_sql) == (
            LANE.test_id,
            LANE.cells,
            LANE.site_invariants,
            LANE.premise_sql,
        )
        for label in ("", "tomorrow", "2026-11-11-2", "2026-11-11B"):
            with pytest.raises(ValueError, match="is not a wave label"):
                IL.country_d84_lane(label)

    def test_apply_resolves_it_and_reads_it_back(self) -> None:
        assert L.resolve_lane("country-d84-2026-11-11") == LANE
        assert L.resolve_lane("country-d84-2026-11-11b") == REDO
        assert "country-d84" not in L.LANES, "no lane of one fixed stamp"
        for bad in ("country-d84", "country-d84-x", "country-d84-2026-11-11-1"):
            with pytest.raises(KeyError):
                L.resolve_lane(bad)
        readback = A.readback_for(LANE)
        assert readback == IL.country_d84_readback(LANE)
        assert f"'{REDO.run_stamp}'" in A.readback_for(REDO)
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

    def premise_now(self, scope_status: str | None) -> str:
        """The lane's premise as the database prints it for the row in `scope_status` (SQLite
        reads the SQL without the `::text` casts; `concat_ws` is Postgres': NULL parts skipped)."""
        db = sqlite3.connect(":memory:")
        db.create_function(
            "concat_ws", -1, lambda sep, *parts: sep.join(p for p in parts if p is not None)
        )
        db.execute("CREATE TABLE unified_sites (name TEXT, lat TEXT, lon TEXT, scope_status TEXT)")
        db.execute(
            "INSERT INTO unified_sites VALUES ('Baltic Sea Anomaly', '61.37676947509479', "
            "'18.448311841356542', ?)",
            (scope_status,),
        )
        sql = f"SELECT {LANE.premise_sql.replace('::text', '')} FROM unified_sites u"
        return db.execute(sql).fetchone()[0]

    def test_the_premise_holds_the_scope_status_so_the_reversal_refuses_a_shown_site(self) -> None:
        """Review of 2026-11-11: the site invariant runs on the write only, so `ROLLBACK.sql` gave
        'Baltic Sea' back to whatever the site was - run before the un-retire wave's own
        `ROLLBACK.sql`, to a shown site (a `/sites/baltic-sea/...` page and a country hub, against
        D84 and D149). Guard 5 runs on the reversal too, and the premise now holds the status the
        plan read: retired."""
        assert self.premise_now("retired") == PREMISE
        assert self.premise_now("in_scope") == PREMISE.replace("| retired", "| in_scope")
        assert self.premise_now(None) == PREMISE.replace("| retired", "| NULL")
        undo = P.render_rollback_sql([record()], site_ids={BALTIC}, lane=LANE)
        guard5 = undo.split("scope guard 5")[1].split("the only writer")[0]
        assert f"({LANE.premise_sql}) IS DISTINCT FROM p.premise" in guard5
        assert f"'{PREMISE}'" in undo, "the reversal carries the premise the plan read"
        apply = A.render_transaction([record()], site_ids={BALTIC}, lane=LANE)
        assert f"({LANE.premise_sql}) IS DISTINCT FROM p.premise" in apply

    def test_the_invariant_has_its_probe(self) -> None:
        foreign = {"id": "11111111-1111-1111-1111-111111111111", "name": "x", "premise": "p"}
        probes = {case[0]: case[2] for case in A.probe_cases([record()], LANE, foreign)}
        assert {"invariant-country", "guard5-premise", "guard3-foreign-old-value"} <= set(probes)
        assert probes["invariant-country"][0].new_value == "Sweden"
        assert A.unprobed_invariants([record()], LANE) == []


class TestTheInvariantInSql:
    """The lane's site invariant over the written row `u`: TRUE refuses the whole write."""

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
            ({"scope_status": "in_scope"}, "row-not-retired"),
            ({"scope_status": None}, "row-not-retired"),
            ({"scope_status": "in_scope", "country": None}, "already-empty"),
        ],
    )
    def test_each_check_refuses_on_its_own(self, change: dict[str, Any], reason: str) -> None:
        v = C.classify(BALTIC, row(**change), ())
        assert not v.ok and v.reason == reason, v
        assert v.premise is None and v.rule == "" and v.evidence == ()

    def test_a_shown_row_is_not_planned_its_reversal_would_show_it_with_a_country(self) -> None:
        v = C.classify(BALTIC, row(scope_status="in_scope"), ())
        assert "scope_status is 'in_scope'" in v.note and "while it is retired" in v.note

    def test_a_journal_that_does_not_end_at_the_live_value_refuses(self) -> None:
        link = P.JournalLink(1, "2026-09-21_x", "T05", "Baltic", "Ostsee")
        v = C.classify(BALTIC, row(), (link,))
        assert not v.ok and v.reason == "journal-disagrees"
        ends_here = P.JournalLink(1, "2026-09-21_x", "T05", "Ostsee", "Baltic Sea")
        assert C.classify(BALTIC, row(), (ends_here,)).ok


class TestThePlan:
    def test_the_read_is_one_read_only_snapshot_of_the_decided_row(self) -> None:
        script = P.tagged_export_script(C.read_parts(LANE))
        assert "REPEATABLE READ READ ONLY" in script
        for verb in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE"):
            assert verb not in script.upper(), verb
        parts = dict(C.read_parts(LANE))
        assert f"'{BALTIC}'" in parts["site"] and f"{LANE.premise_sql} AS premise" in parts["site"]
        assert "u.scope_status, " in parts["site"]
        assert "column_name = 'country'" in parts["journal"]
        for stamp in (LANE.run_stamp, LANE.rollback_run_stamp):
            assert f"'{stamp}'" in parts["stamp"]
            assert f"'{stamp}'" not in dict(C.read_parts(REDO))["stamp"]

    def test_the_plan_is_the_one_cell_and_its_counters(self) -> None:
        plan = C.build_plan(read_text(), built_at="t", lane=LANE)
        assert plan.lane is LANE and plan.skipped == ()
        assert plan.counters == {"candidates": 1, "changes": 1, "skipped": 0}
        (change,) = plan.changes
        assert (change.site_id, change.old_value, change.new_value) == (BALTIC, "Baltic Sea", None)
        emptied = C.build_plan(read_text([row(country=None)]), built_at="t", lane=LANE)
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
        plan = C.build_plan(read_text(journal=[wrote_other]), built_at="t", lane=LANE)
        assert [v.reason for v in plan.skipped] == ["journal-disagrees"]

    def test_a_row_the_read_lost_and_a_wave_that_has_written_stop_the_plan(self) -> None:
        with pytest.raises(P.PlanError, match=f"Baltic Sea Anomaly .{BALTIC}. is not in"):
            C.build_plan(read_text([]), built_at="t", lane=LANE)
        for stamp in (LANE.run_stamp, LANE.rollback_run_stamp):
            with pytest.raises(P.PlanError, match="a wave that has written is never re-planned"):
                C.build_plan(
                    read_text(stamps=[{"run_stamp": stamp, "n": 1}]), built_at="t", lane=LANE
                )

    def test_a_write_that_was_undone_is_planned_again_under_the_next_label(self) -> None:
        """Review of 2026-11-11: after the un-retire wave's `ROLLBACK.sql` and this lane's, the row
        is retired and holds 'Baltic Sea' again, and both stamps of the first wave hold a row. The
        first wave is never re-planned; the next label plans the same cell from the same state."""
        undone = [
            {
                "id": 700, "row_pk": BALTIC, "run_stamp": LANE.run_stamp, "test_id": "D84/country",
                "old_value": "Baltic Sea", "new_value": None,
            },
            {
                "id": 900, "row_pk": BALTIC, "run_stamp": LANE.rollback_run_stamp,
                "test_id": "D84/country", "old_value": None, "new_value": "Baltic Sea",
            },
        ]  # fmt: skip
        first = [{"run_stamp": s, "n": 1} for s in (LANE.run_stamp, LANE.rollback_run_stamp)]
        with pytest.raises(P.PlanError, match="planned again under the next wave label"):
            C.build_plan(read_text(journal=undone, stamps=first), built_at="t", lane=LANE)
        # the next wave's read asks for its own stamps, which hold nothing
        plan = C.build_plan(read_text(journal=undone), built_at="t", lane=REDO)
        assert plan.lane is REDO and plan.run_stamp == "2026-11-11b_mechanical-country-d84"
        (change,) = plan.changes
        assert (change.old_value, change.new_value, change.premise) == ("Baltic Sea", None, PREMISE)
        # while the first wave's write stands there is nothing to plan
        standing = C.build_plan(
            read_text([row(country=None)], journal=undone[:1]), built_at="t", lane=REDO
        )
        assert [v.reason for v in standing.skipped] == ["already-empty"]


class TestTheFiles:
    def test_write_keeps_the_read_and_delivers_the_plan_with_its_undo(self, tmp_path: Path) -> None:
        sent: list[str] = []

        def read(script: str) -> str:
            sent.append(script)
            return read_text()

        root = tmp_path / "mechanical_country_d84"
        out = root / WAVE
        result = C.write(root, WAVE, read=read, built_at="2026-11-11T07:00:00+00:00")
        assert result == {
            "candidates": 1,
            "changes": 1,
            "skipped": 0,
            "lane": "country-d84-2026-11-11",
            "dir": str(out),
        }
        assert sent == [P.tagged_export_script(C.read_parts(LANE))]
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
        assert "| `Baltic Sea` | NULL |" in plan_md
        assert "--lane country-d84-2026-11-11 --probe-guards" in plan_md
        assert "guard 5 refuses it while the site is shown" in plan_md
        with pytest.raises(P.PlanError, match="a delivered plan is never replaced"):
            C.write(root, WAVE, read=read, built_at="t")
        assert len(sent) == 1, "a delivered plan is refused before production is read"
        # the next wave has a directory of its own, and its statements carry its own stamp
        C.write(root, "2026-11-11b", read=read, built_at="t")
        redo = A.load_records(root / "2026-11-11b" / "PLAN.jsonl")
        assert f"'{REDO.run_stamp}'" in A.apply_statement(redo, REDO)
        assert f"'{REDO.rollback_run_stamp}'" in (root / "2026-11-11b" / "ROLLBACK.sql").read_text(
            encoding="utf-8"
        )
        assert A.load_records(out / "PLAN.jsonl") == records, "the first wave's plan is untouched"

    def test_a_read_that_leaves_nothing_to_write_delivers_no_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        emptied = read_text([row(country=None)])
        with pytest.raises(
            P.PlanError, match="nothing to write - Baltic Sea Anomaly: already-empty"
        ):
            C.write(tmp_path / "out", WAVE, read=lambda _script: emptied, built_at="t")
        assert not (tmp_path / "out").exists()
        monkeypatch.setattr(C, "read_production", lambda _script: emptied)
        assert C.main(["--write", "--wave", WAVE, "--out", str(tmp_path / "cli")]) == 1
        assert "REFUSED: the read leaves nothing to write" in capsys.readouterr().err

    def test_the_cli_writes_a_named_wave_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(C, "read_production", lambda _script: read_text())
        for argv in (["--write"], ["--write", "--wave", "tomorrow"]):
            with pytest.raises(SystemExit) as stopped:
                C.main([*argv, "--out", str(tmp_path)])
            assert stopped.value.code == 2
        assert "--write needs --wave" in capsys.readouterr().err
        assert not any(tmp_path.iterdir())
        assert C.main(["--write", "--wave", "2026-11-12", "--out", str(tmp_path)]) == 0
        assert (tmp_path / "2026-11-12" / "PLAN.jsonl").is_file()
        assert '"lane": "country-d84-2026-11-12"' in capsys.readouterr().out


class TestTheRunbooks:
    def test_the_card_runbook_points_at_the_section_that_holds_the_country_lane(self) -> None:
        """Review of 2026-11-11: CARD_DESCRIPTIONS.md 5.11 sent the driver to "section 4" of the
        scope runbook, which lists tests; the lane's commands and the undo order are in 2.2."""
        procedures = REPO / "docs" / "procedures"
        cards = (procedures / "CARD_DESCRIPTIONS.md").read_text(encoding="utf-8")
        scope = (procedures / "WD2_SERVED_IMAGE_AND_SCOPE.md").read_text(encoding="utf-8")
        d50_clear = cards.split("\n### 5.11 ")[1].split("\n## ")[0]
        assert "`WD2_SERVED_IMAGE_AND_SCOPE.md` section 2.2" in d50_clear
        assert "`WD2_SERVED_IMAGE_AND_SCOPE.md` section 4" not in d50_clear
        named = scope.split("\n### 2.2 ")[1].split("\n## ")[0]
        for needle in (
            "country_d84.py",
            "$PY $C --write --wave $W",
            "--lane country-d84-$W --apply",
            "**Undo, in this order:**",
        ):
            assert needle in named, needle
        tests = scope.split("\n## 4. ")[1].split("\n## ")[0]
        assert "--write --wave" not in tests and "--lane country-d84" not in tests
