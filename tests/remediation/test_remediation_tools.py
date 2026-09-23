"""The write and acceptance instruments (`output/remediation/tools/`), tested without a database.

These scripts wrote and accepted the 994 production rows of 2026-09-22 and had no tests of their own.
What is pinned here, each by a test that goes red when its guard is removed:

* **lanes** - a second run (the gap run) must never be read as the mass run: its batches are planned
  from its own directory, and a batch applied in the mass lane cannot suppress a gap batch. The
  default lane is still exactly the mass run's paths. The database is reached through the writer's
  own seam, parser and quoting, and a written lane's plan is pinned.
* **the write gate** - a rows file built before a new writer rule is refused, not written by
  position, *in `main`* and not only in the comparator; a hold that names no planned row is refused;
  a writer call that wrote less than it was handed stops the wave and never marks its batch applied;
  a read-back deviation stops the wave.
* **the acceptance** - it follows the journal chain, but only an operator-listed stamp may change a
  lane's row after it; a lane write must carry the planned values; a planned row that is neither
  withheld nor written is a deviation, never "unchanged".
* **the plan a lane wrote from** - the dry planner refuses to overwrite it, the acceptance and the
  hold list refuse any other file.
* **the external-id repair** - every guard and invariant is in the statement, and `check`/`verify`
  refuse a statement on disk that is not byte for byte the rendered one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "output" / "remediation" / "tools"
for path in (TOOLS, REPO / "scripts" / "remediation", REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lanes  # noqa: E402
import make_holds  # noqa: E402
import measure_review_holds  # noqa: E402
import qid_repair  # noqa: E402
import review_all  # noqa: E402
import verify_writes as V  # noqa: E402
import write_dry_all  # noqa: E402
import write_gate  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

from pipeline.lyra.prospector.wiki import TitleResolution  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

SITE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


# ── lanes ────────────────────────────────────────────────────────────────────────────────────────


def test_the_default_lane_is_the_mass_run_the_tools_always_used() -> None:
    mass = lanes.lane()
    base = REPO / "output" / "remediation"
    assert mass.run_dir == base / "phase3_runner" / "runs" / "mass"
    assert mass.rows == base / "logs" / "_write_dry" / "ALL_ROWS.jsonl"
    assert mass.apply_root == base / "logs" / "_write_apply"
    assert mass.holds == base / "logs" / "_write_apply" / "HOLDS.jsonl"
    assert mass.review_logs == base / "logs" / "review"
    assert mass.stamp_like == "phase3:batch-%"


def test_the_gap_lane_shares_no_path_and_no_stamp_with_the_mass_lane() -> None:
    mass, gap = lanes.lane("mass"), lanes.lane("gap")
    assert gap.run_dir.name == "gap" and gap.stamp_like == "phase3:gap-%"
    for attribute in ("run_dir", "dry_root", "apply_root", "review_logs", "stamp_like"):
        assert getattr(gap, attribute) != getattr(mass, attribute), attribute


def test_the_sitelink_lane_is_a_phase_three_lane_with_its_own_paths_and_stamp() -> None:
    """`slk-NNNN` batches write `phase3:slk-...` stamps; its pilot's `slkg` is no lane and never
    writes (`sitelink_plan.py`)."""
    mass, sitelink = lanes.lane("mass"), lanes.lane("sitelink")
    assert lanes.PHASE3_BATCH_PREFIX["sitelink"] == "slk"
    assert sitelink.run_dir.name == "sitelink" and sitelink.stamp_like == "phase3:slk-%"
    for attribute in ("run_dir", "dry_root", "apply_root", "review_logs", "stamp_like"):
        assert getattr(sitelink, attribute) != getattr(mass, attribute), attribute
    assert "slkg" not in lanes.BATCH_PREFIX.values()


def test_an_unknown_lane_is_refused_rather_than_given_a_guessed_prefix() -> None:
    with pytest.raises(SystemExit, match="unknown lane"):
        lanes.lane("gapp")


def test_every_tool_defaults_to_the_mass_lane() -> None:
    """No `--lane` means what it meant before lanes existed."""
    assert write_dry_all.build_parser().parse_args([]).lane == "mass"
    assert review_all.build_parser().parse_args([]).lane == "mass"


def test_the_tools_reach_the_database_through_the_writers_seam(monkeypatch: Any) -> None:
    """One psql seam, one parser, one quoting - the writer's - and a refusal becomes a named exit."""
    sent: list[tuple[str, str]] = []

    def fake_run_sql(sql: str, *, host: str) -> str:
        sent.append((sql, host))
        return json.dumps({"id": 1}) + "\n"

    monkeypatch.setattr(W, "run_sql", fake_run_sql)
    assert lanes.json_rows(lanes.psql("SELECT 1;", host="somewhere")) == [{"id": 1}]
    assert sent == [("SELECT 1;", "somewhere")]
    assert lanes.HOST == W.SSH_HOST and lanes.sql_text is W._sql_text

    def refusing(sql: str, *, host: str) -> str:
        raise W.WriteRefused("psql exited 2")

    monkeypatch.setattr(W, "run_sql", refusing)
    with pytest.raises(SystemExit, match="did not answer: psql exited 2"):
        lanes.psql("SELECT 1;")


def test_a_database_answer_that_is_not_one_object_per_line_stops_the_tool() -> None:
    rows = lanes.json_rows(json.dumps({"id": 1}) + "\n\n" + json.dumps({"id": 2}) + "\n")
    assert [row["id"] for row in rows] == [1, 2]
    with pytest.raises(SystemExit, match="not JSON"):
        lanes.json_rows("1|a|b\n")
    with pytest.raises(SystemExit, match="not a JSON object"):
        lanes.json_rows("[1, 2]\n")  # valid JSON, and still not a row
    assert lanes.sql_literals(["a", "O'Brien"]) == "'a', 'O''Brien'"


# ── the plan a written lane was applied from ───────────────────────────────────────────────────


def _keys(*keys: str) -> list[dict]:
    return [{"change_key": key} for key in keys]


def test_a_written_lanes_rows_file_must_be_the_pinned_plan(tmp_path: Path) -> None:
    rows = _keys("phase3:a", "phase3:b")
    assert lanes.keys_digest(rows) != lanes.keys_digest(rows[::-1])  # order is part of the pin
    with pytest.raises(SystemExit, match="not the plan the production rows were reviewed"):
        lanes.assert_reviewed_plan(lanes.MASS, rows, path=tmp_path / "ALL_ROWS.jsonl")
    lanes.assert_reviewed_plan("gap", rows, path=tmp_path / "ALL_ROWS.jsonl")  # nothing written yet
    assert lanes.REVIEWED_PLAN_KEYS_SHA256[lanes.MASS].startswith("0b7ad95d")


def test_the_hold_list_refuses_a_rows_file_whose_lines_moved(
    tmp_path: Path, monkeypatch: Any
) -> None:
    rows = _keys("phase3:0", "phase3:1", "phase3:2")
    with pytest.raises(SystemExit, match="not the plan the production rows were reviewed"):
        make_holds.assert_pinned(rows)
    moved = tmp_path / "ALL_ROWS.jsonl"
    lanes.write_jsonl(moved, rows)
    monkeypatch.setattr(make_holds, "ROWS", moved)
    monkeypatch.setattr(make_holds, "OUT", tmp_path / "apply")
    with pytest.raises(SystemExit, match="not the plan"):
        make_holds.main()  # the wiring: main checks before it writes a line
    assert not (tmp_path / "apply" / "HOLDS.jsonl").exists()


def _lane(tmp_path: Path, name: str = "gap") -> lanes.Lane:
    return lanes.Lane(
        name=name,
        run_dir=tmp_path / "runs" / name,
        dry_root=tmp_path / f"_write_dry_{name}",
        apply_root=tmp_path / f"_write_apply_{name}",
        review_logs=tmp_path / f"review_{name}",
        stamp_like=f"phase3:{name}-%",
    )


def test_the_dry_planner_refuses_to_replace_the_plan_a_lane_has_written_from(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A re-plan of the mass lane turned 1,074 rows into 1,028 and 44 correct writes into deviations."""
    lane = _lane(tmp_path)
    write_dry_all.assert_plan_replaceable(lane, lane.dry_root)  # nothing written: re-plan freely
    (lane.apply_root / "gap-0001").mkdir(parents=True)
    (lane.apply_root / "gap-0001" / "APPLIED.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="has written"):
        write_dry_all.assert_plan_replaceable(lane, lane.dry_root)
    write_dry_all.assert_plan_replaceable(
        lane, tmp_path / "scratch"
    )  # a measurement goes elsewhere
    # the wiring: main refuses before it plans or writes anything
    monkeypatch.setattr(write_dry_all.lanes, "lane", lambda name: lane)
    with pytest.raises(SystemExit, match="has written"):
        write_dry_all.main(["--lane", "gap"])
    assert not lane.rows.exists()


# ── the write gate ───────────────────────────────────────────────────────────────────────────────


def _row(batch: str, key: str, *, site: str = SITE, column: str = "site_type") -> dict:
    return {
        "batch_id": batch,
        "change_key": key,
        "column": column,
        "site_id": site,
        "pk": site,
        "site_name": f"site {key}",
        "old_value": "Temple",
        "new_value": "Ruin",
    }


def test_a_batch_applied_in_the_mass_lane_does_not_suppress_a_gap_batch(tmp_path: Path) -> None:
    """139 of the 149 batches that hold a gap field have an APPLIED.json in the mass lane's root."""
    run_dir = tmp_path / "runs" / "gap"
    (run_dir / "gap-0001").mkdir(parents=True)
    mass_root, gap_root = tmp_path / "_write_apply", tmp_path / "_write_apply_gap"
    for root, batch in ((mass_root, "gap-0001"), (mass_root, "batch-0001")):
        (root / batch).mkdir(parents=True)
        (root / batch / "APPLIED.json").write_text("{}", encoding="utf-8")
    rows = [_row("gap-0001", "k1")]
    verdicts = {"k1": (True, "")}

    todo = write_gate.open_batches(rows, verdicts, run_dir=run_dir, apply_root=gap_root)
    assert [batch for batch, _, _ in todo] == ["gap-0001"]
    # ...while the lane's own marker still means "done"
    (gap_root / "gap-0001").mkdir(parents=True)
    (gap_root / "gap-0001" / "APPLIED.json").write_text("{}", encoding="utf-8")
    assert write_gate.open_batches(rows, verdicts, run_dir=run_dir, apply_root=gap_root) == []


def test_rows_of_another_run_are_refused_before_anything_is_planned(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "gap"
    run_dir.mkdir(parents=True)
    with pytest.raises(SystemExit, match="not in"):
        write_gate.open_batches(
            [_row("batch-0007", "k1")],
            {"k1": (True, "")},
            run_dir=run_dir,
            apply_root=tmp_path / "apply",
        )


def test_a_rows_file_that_is_not_the_writers_plan_today_is_refused() -> None:
    """One row the writer now refuses moves every later position onto a different row."""
    rows = [_row("gap-0001", key) for key in ("k1", "k2", "k3")]
    write_gate.assert_same_plan("gap-0001", rows, ["k1", "k2", "k3"])  # the same plan passes
    with pytest.raises(SystemExit, match="first differ at position 2"):
        write_gate.assert_same_plan("gap-0001", rows, ["k1", "k3"])
    with pytest.raises(SystemExit, match="stale"):
        write_gate.assert_same_plan("gap-0001", rows, ["k1", "k2", "k3", "k4"])


def _gate_tree(tmp_path: Path, batches: dict[str, list[str]]) -> tuple[Path, Path, Path]:
    """A run dir with the batches, a rows file naming their keys, and an apply root."""
    run_dir = tmp_path / "runs" / "gap"
    rows = []
    for batch, keys in batches.items():
        (run_dir / batch).mkdir(parents=True)
        rows.extend(_row(batch, key, site=f"site-{key}") for key in keys)
    rows_path = tmp_path / "ALL_ROWS.jsonl"
    lanes.write_jsonl(rows_path, rows)
    return run_dir, rows_path, tmp_path / "_write_apply_gap"


def _gate_args(run_dir: Path, rows_path: Path, apply_root: Path, *extra: str) -> list[str]:
    return [
        "--lane",
        "gap",
        "--run-dir",
        str(run_dir),
        "--rows",
        str(rows_path),
        "--apply-root",
        str(apply_root),
        "--hold",
        str(apply_root / "HOLDS.jsonl"),
        *extra,
    ]


def _no_database(monkeypatch: Any) -> None:
    monkeypatch.setattr(write_gate, "coordinates", lambda site_ids, host: {})
    monkeypatch.setattr(
        write_gate, "gate", lambda rows, positions: {row["change_key"]: (True, "") for row in rows}
    )


def _no_write(monkeypatch: Any) -> list[str]:
    calls: list[str] = []

    def write_batch(batch: str, *args: Any, **kwargs: Any) -> dict:
        calls.append(batch)
        return {"written": 1, "sites": 1, "matched_0": 0, "journal": 1}

    monkeypatch.setattr(write_gate, "write_batch", write_batch)
    return calls


@pytest.mark.parametrize("apply", [False, True])
def test_main_refuses_a_stale_rows_file_before_the_first_write(
    tmp_path: Path, monkeypatch: Any, apply: bool
) -> None:
    """The guard is only a guard if `main` calls it - in the dry run (the report is the proof) and
    before the first row of a real wave."""
    run_dir, rows_path, apply_root = _gate_tree(tmp_path, {"gap-0001": ["k1", "k2"]})
    _no_database(monkeypatch)
    calls = _no_write(monkeypatch)
    asked: list[Path] = []

    def replan(batch: str, *, run_dir: Path, scratch: Path) -> list[str]:
        asked.append(run_dir / batch)
        return ["k2"]  # the writer's plan of today lost k1: every position moved

    monkeypatch.setattr(write_gate, "replan_keys", replan)
    extra = ("--apply",) if apply else ()
    with pytest.raises(SystemExit, match="stale"):
        write_gate.main(_gate_args(run_dir, rows_path, apply_root, *extra))
    assert asked == [run_dir / "gap-0001"] and calls == []


def test_the_replan_asks_the_writer_about_this_lanes_own_batch_directory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    run_dir = tmp_path / "runs" / "gap"
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen.append(command)
        out = Path(command[command.index("--out") + 1])
        lanes.write_jsonl(out / W.PLAN_FILE, _keys("k1", "k2"))
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(write_gate.subprocess, "run", fake_run)
    keys = write_gate.replan_keys("gap-0003", run_dir=run_dir, scratch=tmp_path / "replan")
    assert keys == ["k1", "k2"]
    command = seen[0]
    assert command[command.index("--batch-dir") + 1] == str(run_dir / "gap-0003")
    assert "--apply" not in command


def test_a_hold_that_names_no_planned_row_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    """One character off in a hand-typed key would hold nothing and let the held row through."""
    rows = [_row("gap-0001", "phase3:" + "a" * 64)]
    holds = tmp_path / "HOLDS.jsonl"
    lanes.write_jsonl(holds, [{"change_key": "phase3:" + "a" * 63, "hold_reason": "typed by hand"}])
    with pytest.raises(SystemExit, match="name no planned row"):
        write_gate.load_holds(holds, rows)
    lanes.write_jsonl(holds, [{"change_key": rows[0]["change_key"], "hold_reason": "read"}])
    assert write_gate.load_holds(holds, rows) == {rows[0]["change_key"]: "read"}
    assert write_gate.load_holds(tmp_path / "none.jsonl", rows) == {}
    # the wiring: main reads the holds through the refusal, before any plan is checked
    run_dir, rows_path, apply_root = _gate_tree(tmp_path / "wave", {"gap-0001": ["k1"]})
    lanes.write_jsonl(apply_root / "HOLDS.jsonl", [{"change_key": "k9", "hold_reason": "typo"}])
    _no_database(monkeypatch)
    monkeypatch.setattr(write_gate, "replan_keys", lambda *a, **k: pytest.fail("planned"))
    with pytest.raises(SystemExit, match="name no planned row"):
        write_gate.main(_gate_args(run_dir, rows_path, apply_root))


def test_a_held_row_is_withheld_whatever_the_boundary_says(monkeypatch: Any) -> None:
    rows = [_row("gap-0001", "k1"), _row("gap-0001", "k2")]
    monkeypatch.setattr(
        write_gate, "gate", lambda rows, positions: {row["change_key"]: (True, "") for row in rows}
    )
    verdicts = write_gate.withheld(rows, positions={}, holds={"k2": "reason"})
    assert verdicts["k1"] == (True, "") and verdicts["k2"][0] is False


def _report(**values: Any) -> dict:
    report = {
        "dry_run": False,
        "rows_written": 2,
        "rows_matched_0": 0,
        "rows_matched_0_reasons": [],
        "journal_rows_added": 2,
        "chunk_results": [{"chunk": "chunk-0001", "skipped": None}],
    }
    report.update(values)
    return report


def test_a_writer_report_that_is_not_every_row_written_and_journalled_is_a_problem() -> None:
    assert write_gate.call_problems(_report(), expected=2) == []
    skipped = _report(
        rows_written=0,
        rows_matched_0=1,
        journal_rows_added=0,
        chunk_results=[{"chunk": "chunk-0001", "skipped": "1 of 2 row(s) no longer hold"}],
    )
    problems = write_gate.call_problems(skipped, expected=2)
    assert any("0 row(s) written, 2 handed" in p for p in problems)
    assert any("no longer held" in p for p in problems)
    assert any("chunk chunk-0001 skipped" in p for p in problems)
    assert write_gate.call_problems(_report(dry_run=True), expected=2)
    assert write_gate.call_problems(_report(journal_rows_added=1), expected=2)
    assert write_gate.call_problems(_report(rows_written=1, journal_rows_added=1), expected=2)


def _fake_writer(monkeypatch: Any, reports: list[dict]) -> list[list[str]]:
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(reports[len(seen) - 1]), stderr=""
        )

    monkeypatch.setattr(write_gate.subprocess, "run", fake_run)
    return seen


def test_a_chunk_the_writer_skipped_stops_the_wave_and_is_never_marked_applied(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The writer exits 0 when its pre-flight finds a moved row and writes none of the chunk."""
    rows = [_row("gap-0003", "k1"), _row("gap-0003", "k2", site=OTHER)]
    skipped = _report(
        rows_written=0,
        rows_matched_0=1,
        journal_rows_added=0,
        chunk_results=[{"chunk": "chunk-0001", "skipped": "1 of 2 row(s) moved"}],
    )
    _fake_writer(monkeypatch, [skipped])
    apply_root = tmp_path / "apply"
    with pytest.raises(SystemExit, match="STOP at gap-0003 all"):
        write_gate.write_batch(
            "gap-0003", rows, [1, 2], host="h", run_dir=tmp_path, apply_root=apply_root
        )
    assert not (apply_root / "gap-0003" / "APPLIED.json").exists()
    stopped = json.loads((apply_root / "gap-0003" / "STOPPED.json").read_text(encoding="utf-8"))
    assert stopped["stopped_at_call"] == "all" and stopped["report"]["rows_written"] == 0
    # a later wave does not walk past it
    (tmp_path / "gap-0003").mkdir()
    with pytest.raises(SystemExit, match="stopped in an earlier wave"):
        write_gate.open_batches(
            rows, {"k1": (True, ""), "k2": (True, "")}, run_dir=tmp_path, apply_root=apply_root
        )


def test_a_batch_whose_calls_all_wrote_what_they_were_handed_is_marked_applied(
    tmp_path: Path, monkeypatch: Any
) -> None:
    rows = [_row("gap-0004", key, site=f"s{key}") for key in ("k1", "k2", "k3")]
    one = _report(rows_written=1, journal_rows_added=1)
    seen = _fake_writer(monkeypatch, [one, one])
    outcome = write_gate.write_batch(
        "gap-0004", rows, [1, 3], host="h", run_dir=tmp_path, apply_root=tmp_path / "apply"
    )
    assert [command[command.index("--chunk") + 1] for command in seen] == ["1", "3"]
    assert outcome == {"written": 2, "sites": 2, "matched_0": 0, "journal": 2}
    applied = json.loads((tmp_path / "apply" / "gap-0004" / "APPLIED.json").read_text("utf-8"))
    assert applied == {"batch_id": "gap-0004", "rows_written": 2, "sites": 2}


def test_a_step_read_back_with_deviations_stops_the_wave(tmp_path: Path, monkeypatch: Any) -> None:
    run_dir, rows_path, apply_root = _gate_tree(tmp_path, {"gap-0001": ["k1"], "gap-0002": ["k2"]})
    _no_database(monkeypatch)
    calls = _no_write(monkeypatch)
    monkeypatch.setattr(
        write_gate,
        "replan_keys",
        lambda batch, **kwargs: ["k1"] if batch == "gap-0001" else ["k2"],
    )
    monkeypatch.setattr(write_gate, "read_back", lambda rows, host: ["site k1.site_type: planned"])
    with pytest.raises(SystemExit, match="STOP after 1 sites"):
        write_gate.main(_gate_args(run_dir, rows_path, apply_root, "--apply", "--step", "1"))
    assert calls == ["gap-0001"]
    # no step reached: the final read-back's deviations are the wave's exit code
    calls.clear()
    args = _gate_args(run_dir, rows_path, apply_root, "--apply", "--step", "100")
    assert write_gate.main(args) == 1
    assert calls == ["gap-0001", "gap-0002"]
    monkeypatch.setattr(write_gate, "read_back", lambda rows, host: [])
    assert write_gate.main(args) == 0


# ── the reviewer driver's ceiling ────────────────────────────────────────────────────────────────


def test_the_reviewer_ceiling_counts_this_pass_and_really_stops_the_queue() -> None:
    """The ledger already holds the mass run's bill; and a STOP must cancel what is queued."""
    ledger = {"cost": 4.65}  # the mass lane's reviewer spend, already in the ledger
    started: list[str] = []

    def run(batch: str) -> tuple[str, int]:
        started.append(batch)
        ledger["cost"] += 1.0
        return batch, 0

    todo = [f"gap-{n:04d}" for n in range(1, 11)]
    failed, not_reached = review_all.review_batches(
        todo, run=run, spend=lambda: (ledger["cost"], 0), cap=2.5, workers=1
    )
    assert failed == []
    # 4.65 of history is not this pass's: it runs until its own spend passes 2.5, i.e. 3 batches,
    # and the other 7 are never started.
    assert len(started) == 3
    assert not_reached == todo[3:]


# ── the dry planner ──────────────────────────────────────────────────────────────────────────────


def test_the_dry_plan_driver_reads_only_batches_with_a_review(tmp_path: Path) -> None:
    for name, reviewed in (("gap-0001", True), ("gap-0002", False)):
        (tmp_path / name).mkdir()
        if reviewed:
            (tmp_path / name / "review.json").write_text("{}", encoding="utf-8")
    assert write_dry_all.batches_to_plan(tmp_path) == ["gap-0001"]


def test_a_writer_that_exited_zero_without_its_plan_file_is_damage(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="wrote no PLAN.jsonl"):
        write_dry_all._batch_lines(tmp_path / "PLAN.jsonl", "gap-0001")


# ── the acceptance follows the journal chain ────────────────────────────────────────────────────


def _planned(pk: str, column: str, old: str, new: str, *, key: str | None = None) -> dict:
    return {
        "pk": pk,
        "column": column,
        "old_value": old,
        "new_value": new,
        "site_name": pk[:8],
        "change_key": key or f"key-{pk[:8]}-{column}",
    }


def _link(id_: int, pk: str, column: str, old: str | None, new: str | None, stamp: str) -> V.Link:
    return V.Link(id=id_, table=V.TABLE, column=column, pk=pk, old=old, new=new, stamp=stamp)


PHASE3 = "phase3:batch-0002:chunk-0001"
UK = "2026-09-23_mechanical-uk-parts"


def _accept(
    planned: list[dict],
    lane: list[V.Link],
    others: list[V.Link],
    live: dict,
    *,
    withheld: set[str] = frozenset(),  # type: ignore[assignment]
    allowed: set[str] = frozenset(),  # type: ignore[assignment]
) -> V.Acceptance:
    chains: dict = {}
    for link in sorted(lane + others, key=lambda link: link.id):
        chains.setdefault(link.key, []).append(link)
    return V.accept(
        planned=planned,
        lane_links=lane,
        chains=chains,
        live=live,
        present={pk for _column, pk in live},
        withheld=withheld,
        allowed=allowed,
    )


def _starts(result: V.Acceptance, label: str) -> bool:
    return any(line.startswith(label) for line in result.deviations)


def test_a_write_that_holds_its_value_is_carried() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [],
        {("country", SITE): "United Kingdom"},
    )
    assert (result.carried, dict(result.superseded), result.deviations) == (1, {}, [])


def test_a_write_superseded_by_a_listed_later_lane_is_reported_not_a_deviation() -> None:
    """The five phase-3 'United Kingdom' rows the Northern-Ireland lane re-spells."""
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "United Kingdom", "Northern Ireland", UK)
    planned = [_planned(SITE, "country", "Ireland", "United Kingdom")]
    live = {("country", SITE): "Northern Ireland"}
    result = _accept(planned, [write], [later], live, allowed={UK})
    assert result.deviations == []
    assert result.carried == 0
    assert dict(result.superseded) == {UK: 1}
    # ...and the same later write by a stamp nobody listed is a deviation, not "superseded"
    unlisted = _accept(planned, [write], [later], live)
    assert _starts(unlisted, "CHANGED LATER BY AN UNLISTED STAMP")
    assert dict(unlisted.superseded) == {}


def test_a_lane_write_of_a_value_nobody_planned_is_a_deviation() -> None:
    """The plan said Temple -> Ruin; the journal says the lane wrote Tomb -> Monastery."""
    write = _link(1, SITE, "site_type", "Tomb", "Monastery", PHASE3)
    result = _accept(
        [_planned(SITE, "site_type", "Temple", "Ruin")],
        [write],
        [],
        {("site_type", SITE): "Monastery"},
    )
    assert _starts(result, "OTHER VALUE")


def test_a_lane_that_wrote_one_row_twice_is_a_deviation() -> None:
    first = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    second = _link(2, SITE, "country", "United Kingdom", "France", "phase3:batch-0009:chunk-0001")
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [first, second],
        [],
        {("country", SITE): "France"},
    )
    assert _starts(result, "WRITTEN TWICE")
    assert dict(result.superseded) == {}


def test_a_withheld_row_the_lane_wrote_is_a_deviation() -> None:
    row = _planned(SITE, "site_type", "Temple", "Ruin")
    write = _link(1, SITE, "site_type", "Temple", "Ruin", PHASE3)
    result = _accept(
        [row], [write], [], {("site_type", SITE): "Ruin"}, withheld={row["change_key"]}
    )
    assert _starts(result, "WRITTEN THOUGH WITHHELD")


def test_a_broken_chain_is_a_deviation_even_when_the_live_value_matches_its_end() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "England", "Northern Ireland", UK)  # does not start at UK
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [later],
        {("country", SITE): "Northern Ireland"},
        allowed={UK},
    )
    assert _starts(result, "BROKEN CHAIN")


def test_a_lane_row_missing_from_its_own_chain_is_a_deviation() -> None:
    """The chain read and the lane read disagree - a window lost, or a filter dropped a row."""
    write = _link(7, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    result = V.accept(
        planned=[_planned(SITE, "country", "Ireland", "United Kingdom")],
        lane_links=[write],
        chains={},
        live={("country", SITE): "United Kingdom"},
        present={SITE},
        withheld=set(),
        allowed=set(),
    )
    assert _starts(result, "CHAIN INCOMPLETE")
    assert result.carried == 0


def test_a_live_value_that_is_not_the_chains_last_value_is_a_deviation() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "United Kingdom", "Northern Ireland", UK)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [later],
        {("country", SITE): "United Kingdom"},  # the later lane's journal says otherwise
        allowed={UK},
    )
    assert _starts(result, "NOT NEW")


def test_a_planned_row_neither_withheld_nor_written_is_a_deviation_not_unchanged() -> None:
    """A chunk the writer skipped, a wave that stopped: its rows must not read as 'unchanged'."""
    row = _planned(OTHER, "site_type", "Temple", "Ruin")
    result = _accept([row], [], [], {("site_type", OTHER): "Temple"})
    assert _starts(result, "NOT WRITTEN") and result.untouched == 0


def test_a_withheld_row_must_still_hold_its_old_value() -> None:
    held = _planned(OTHER, "site_type", "Temple", "Ruin")
    untouched = _accept(
        [held], [], [], {("site_type", OTHER): "Temple"}, withheld={held["change_key"]}
    )
    assert (untouched.untouched, untouched.deviations) == (1, [])
    silently = _accept(
        [held], [], [], {("site_type", OTHER): "Ruin"}, withheld={held["change_key"]}
    )
    assert _starts(silently, "CHANGED ANYWAY")


def test_a_withheld_row_another_lane_changed_is_moved_only_for_a_listed_stamp() -> None:
    held = _planned(OTHER, "country", "Ireland", "United Kingdom")
    other = _link(5, OTHER, "country", "Ireland", "Northern Ireland", UK)
    live = {("country", OTHER): "Northern Ireland"}
    moved = _accept([held], [], [other], live, withheld={held["change_key"]}, allowed={UK})
    assert (dict(moved.moved), moved.deviations) == ({UK: 1}, [])
    unlisted = _accept([held], [], [other], live, withheld={held["change_key"]})
    assert _starts(unlisted, "CHANGED BY AN UNLISTED STAMP")
    foreign = _link(5, OTHER, "country", "Scotland", "Northern Ireland", UK)
    unrelated = _accept([held], [], [foreign], live, withheld={held["change_key"]}, allowed={UK})
    assert _starts(unrelated, "FOREIGN CHAIN")
    # history before the planned state is not a change after it
    before = _link(3, OTHER, "country", "Eire", "Ireland", "2026-09-20_mechanical")
    history = _accept(
        [held], [], [before], {("country", OTHER): "Ireland"}, withheld={held["change_key"]}
    )
    assert (history.untouched, history.deviations) == (1, [])


def test_a_lane_journal_row_outside_the_plan_is_a_deviation() -> None:
    write = _link(1, SITE, "site_type", "Temple", "Ruin", PHASE3)
    result = _accept([], [write], [], {("site_type", SITE): "Ruin"})
    assert _starts(result, "OUTSIDE THE PLAN")


def test_a_planned_site_missing_from_the_database_is_a_deviation() -> None:
    held = _planned(OTHER, "site_type", "Temple", "Ruin")
    result = V.accept(
        planned=[held],
        lane_links=[],
        chains={},
        live={},
        present=set(),
        withheld={held["change_key"]},
        allowed=set(),
    )
    assert _starts(result, "MISSING")


# Ported 2026-09-23 from the mechanical lane's own acceptance tests (tests/remediation/
# test_verify_writes.py on wip/mech-lane-fix), whose `judge()` API this merged acceptance replaced:
# the scenarios this file did not yet pin, rewritten against `accept()` and no weaker.
def test_a_lane_row_outside_the_three_fields_is_a_deviation_not_dropped() -> None:
    """A phase-3 writer writes site_type, period_start and country of unified_sites only. A lane row
    elsewhere must be reported; the first merged version of main filtered it out before accept()."""
    elsewhere = V.Link(
        id=9, table="card_stats", column="card_description", pk=SITE, old="a", new="b", stamp=PHASE3
    )
    other_field = _link(10, SITE, "period_name", "1 - 500 AD", "1500+ AD", PHASE3)
    result = _accept([], [elsewhere, other_field], [], {})
    assert [line.split(" ")[0:4] for line in result.deviations] == [
        ["OUTSIDE", "THE", "THREE", "FIELDS"]
    ] * 2
    assert result.carried == 0


def test_a_later_chain_on_a_withheld_row_must_end_at_the_live_value() -> None:
    held = _planned(OTHER, "period_start", "-500", "-450")
    later = _link(5, OTHER, "period_start", "-500", "-43000", UK)
    result = _accept(
        [held],
        [],
        [later],
        {("period_start", OTHER): "-40000"},
        withheld={held["change_key"]},
        allowed={UK},
    )
    assert _starts(result, "NOT NEW")
    assert dict(result.moved) == {UK: 1}  # the move is counted, and the mismatch is still reported


def test_the_acceptance_judges_chains_by_the_planners_rule_and_reports_every_break() -> None:
    import journal_chain

    assert V.first_break is journal_chain.first_break
    assert V.ROLLBACK_SUFFIX == journal_chain.ROLLBACK_SUFFIX
    chain = [
        _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3),
        _link(2, SITE, "country", "Wales", "England", UK),  # break 1
        _link(3, SITE, "country", "Scotland", "Northern Ireland", UK),  # break 2
    ]
    problems, last = V.check_chain(
        (V.TABLE, "country", SITE), chain, "Northern Ireland", missing=False
    )
    assert [line.split(":")[0] for line in problems] == [f"BROKEN CHAIN {SITE} country"] * 2
    assert "journal row 2" in problems[0] and "journal row 3" in problems[1]
    assert last == "Northern Ireland"


def test_a_later_chain_on_a_withheld_row_must_be_unbroken() -> None:
    held = _planned(OTHER, "period_start", "-500", "-450")
    first = _link(5, OTHER, "period_start", "-500", "-43000", UK)
    second = _link(6, OTHER, "period_start", "-42000", "-40000", UK)  # does not start at -43000
    result = _accept(
        [held],
        [],
        [first, second],
        {("period_start", OTHER): "-40000"},
        withheld={held["change_key"]},
        allowed={UK},
    )
    assert _starts(result, "BROKEN CHAIN")


def test_a_rolled_back_lane_write_is_not_carried() -> None:
    """The writer's reversal stamp shares the lane's prefix. The lane read leaves reversals out, so the
    reversal is a later link of an unlisted stamp - reported, never counted as carried or superseded."""
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    reversal = _link(2, SITE, "country", "United Kingdom", "Ireland", PHASE3 + V.ROLLBACK_SUFFIX)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [reversal],
        {("country", SITE): "Ireland"},
    )
    assert _starts(result, "CHANGED LATER BY AN UNLISTED STAMP")
    assert PHASE3 + V.ROLLBACK_SUFFIX in result.deviations[0]
    assert (result.carried, dict(result.superseded)) == (0, {})


def test_a_reversal_without_its_write_is_no_write_of_the_lane() -> None:
    """A reversal whose write the journal does not hold: the planned row was not written by the lane,
    and the chain does not start at the planned old value's successor."""
    row = _planned(SITE, "country", "Ireland", "United Kingdom")
    reversal = _link(2, SITE, "country", "United Kingdom", "Ireland", PHASE3 + V.ROLLBACK_SUFFIX)
    result = _accept([row], [], [reversal], {("country", SITE): "Ireland"})
    assert _starts(result, "NOT WRITTEN") and result.carried == 0


def test_the_lane_query_leaves_out_reversals_but_the_chain_query_reads_every_stamp() -> None:
    lane_sql = V.lane_journal_sql("phase3:batch-%")
    assert "run_stamp LIKE 'phase3:batch-%'" in lane_sql and "'%-rollback'" in lane_sql
    chain_sql = V.chain_sql([SITE])
    assert "run_stamp" not in chain_sql.split("WHERE", 1)[1]
    assert f"'{SITE}'" in chain_sql and "ORDER BY id" in chain_sql


def _journal_line(link: V.Link) -> str:
    return json.dumps(
        {
            "id": link.id,
            "table_name": link.table,
            "column_name": link.column,
            "row_pk": link.pk,
            "old_value": link.old,
            "new_value": link.new,
            "run_stamp": link.stamp,
        }
    )


def test_the_database_read_windows_the_rows_and_orders_every_chain_by_id() -> None:
    pks = [f"{n:08d}-0000-4000-8000-000000000000" for n in range(450)]
    first, last = pks[0], pks[-1]
    calls: list[str] = []

    def run(sql: str) -> str:
        calls.append(sql)
        if "run_stamp LIKE" in sql:
            return _journal_line(_link(9, last, "site_type", "Temple", "Ruin", PHASE3)) + "\n"
        if "FROM remediation_change_log" in sql:
            lines = []
            if f"'{last}'" in sql:  # returned out of id order on purpose
                lines.append(_link(9, last, "site_type", "Temple", "Ruin", PHASE3))
                lines.append(_link(3, last, "site_type", "Tomb", "Temple", "2026-09-20_x"))
            return "".join(_journal_line(link) + "\n" for link in lines)
        window = [pk for pk in pks if f"'{pk}'" in sql]
        return "".join(
            json.dumps({"id": pk, "site_type": "Ruin", "period_start": -500, "country": None})
            + "\n"
            for pk in window
        )

    lane_links, chains, live, present = V.read_database(pks, stamp_like="phase3:batch-%", run=run)
    assert len(calls) == 1 + 3 * 2  # the lane's journal, then 3 windows of chain + live
    assert present == set(pks)
    assert [link.id for link in chains[(V.TABLE, "site_type", last)]] == [3, 9]
    assert live[("period_start", first)] == "-500" and live[("country", first)] is None
    assert [link.id for link in lane_links] == [9]


def test_main_accepts_a_lane_from_what_the_database_answers(
    tmp_path: Path, monkeypatch: Any
) -> None:
    written = _planned(SITE, "site_type", "Temple", "Ruin", key="k-written")
    held = _planned(OTHER, "site_type", "Temple", "Ruin", key="k-held")
    rows_path = tmp_path / "ALL_ROWS.jsonl"
    lanes.write_jsonl(rows_path, [written, held])
    holds = tmp_path / "HOLDS.jsonl"
    lanes.write_jsonl(holds, [{"change_key": "k-held", "hold_reason": "read by hand"}])
    monkeypatch.setattr(write_gate, "coordinates", lambda site_ids, host: {})
    monkeypatch.setattr(
        write_gate, "gate", lambda rows, positions: {row["change_key"]: (True, "") for row in rows}
    )
    link = _link(1, SITE, "site_type", "Temple", "Ruin", "phase3:gap-0001:chunk-0001")
    live = {SITE: "Ruin", OTHER: "Temple"}

    def psql(sql: str, *, host: str) -> str:
        if "run_stamp LIKE" in sql or "FROM remediation_change_log" in sql:
            return _journal_line(link) + "\n"
        return "".join(
            json.dumps({"id": pk, "site_type": value, "period_start": None, "country": None}) + "\n"
            for pk, value in live.items()
        )

    monkeypatch.setattr(lanes, "psql", psql)
    args = ["--lane", "gap", "--rows", str(rows_path), "--hold", str(holds)]
    assert V.main(args) == 0
    # without the hold, the second row is a planned row nobody wrote
    assert V.main(["--lane", "gap", "--rows", str(rows_path), "--hold", str(tmp_path / "x")]) == 1
    # the mass lane refuses a rows file that is not the plan it was written from
    with pytest.raises(SystemExit, match="not the plan"):
        V.main(["--rows", str(rows_path), "--hold", str(holds)])
    # a lane row outside the three fields reaches the acceptance and fails it (it was dropped in main)
    stray = V.Link(
        id=2,
        table="card_stats",
        column="card_description",
        pk=SITE,
        old="a",
        new="b",
        stamp="phase3:gap-0001:chunk-0001",
    )

    def psql_with_stray(sql: str, *, host: str) -> str:
        if "run_stamp LIKE" in sql:
            return _journal_line(link) + "\n" + _journal_line(stray) + "\n"
        return psql(sql, host=host)

    monkeypatch.setattr(lanes, "psql", psql_with_stray)
    assert V.main(args) == 1


# ── the site_external_ids repair (rendered, never applied here) ─────────────────────────────────


def test_the_repair_changes_only_settled_sites_and_never_the_unresolved_one() -> None:
    rows = qid_repair.changes()
    unresolved = {site.site_id for site in qid_repair.SITES if site.rule == "unresolved"}
    assert unresolved and not unresolved & {row.site_id for row in rows}
    assert all(row.old_value != row.new_value for row in rows)
    assert len({(row.site_id, row.kind) for row in rows}) == len(rows)
    for site in qid_repair.SITES:
        mine = {row.kind: row for row in rows if row.site_id == site.site_id}
        if site.rule == "unresolved":
            continue
        assert mine["wikidata_qid"].old_value == site.old_qid
        assert mine["wikidata_qid"].confidence == (
            "two_source" if site.rule == "A" else "authoritative"
        )
        assert ("enwiki_title" in mine) == (site.new_title is not None)


def test_a_site_planned_twice_or_an_unresolved_site_with_a_value_is_refused() -> None:
    site = qid_repair.SITES[0]
    with pytest.raises(SystemExit, match="planned twice"):
        qid_repair.changes((site, site))
    bad = qid_repair.Site(site.site_id, site.name, "unresolved", "Q1", "Q2", "T", None, ())
    with pytest.raises(SystemExit, match="cannot carry a new value"):
        qid_repair.changes((bad,))


def test_the_repair_statement_is_guarded_journalled_and_pinned() -> None:
    rows = qid_repair.changes()
    apply_sql = qid_repair.render(rows, reversal=False)
    assert f"{qid_repair.DIGEST_HEADER}{qid_repair.plan_digest(rows)}" in apply_sql
    assert apply_sql.rstrip().count("COMMIT;") == 1 and "\nROLLBACK;" not in apply_sql
    # the conditional update names the full key, and exactly one row must match
    assert "WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;" in apply_sql
    assert "IF n <> 1 THEN" in apply_sql
    # the journal row is written in the same transaction, and checked in both directions
    assert "INSERT INTO remediation_change_log" in apply_sql
    assert "outside the plan" in apply_sql and "no matching journal row" in apply_sql
    assert f"'{qid_repair.RUN_STAMP}'" in apply_sql
    rehearsal = qid_repair.render(rows, reversal=False, rehearsal=True)
    assert "\nROLLBACK;" in rehearsal and "COMMIT;" not in rehearsal


def test_every_guard_and_invariant_of_the_repair_statement_raises() -> None:
    """Each check is a predicate and a RAISE; both halves are pinned, so deleting either is red."""
    sql = qid_repair.render(qid_repair.changes(), reversal=False)
    # guard 1: only curated sites that still exist
    assert "WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';" in sql
    assert "RAISE EXCEPTION 'external-id repair: % row(s) are not curated sites', bad;" in sql
    # guard 2: exactly one row of the kind, and it holds the planned old value
    assert (
        "     WHERE (SELECT count(*) FROM site_external_ids e\n"
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1\n"
        "        OR NOT EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = p.site_id\n"
        "                          AND e.kind = p.kind AND e.value = p.old_value);"
    ) in sql
    assert "no longer hold the planned old value', bad;" in sql
    # the count of changed rows
    assert "IF moved <> expected THEN" in sql and "row(s) changed, % planned'" in sql
    # invariant 1: every row holds the new value, and only one row of the kind is left
    assert (
        "             AND e.kind = p.kind AND e.value = p.new_value) <> 1\n"
        "        OR (SELECT count(*) FROM site_external_ids e\n"
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1;"
    ) in sql
    assert "row(s) do not hold the new value', bad;" in sql
    # invariant 2: journal and plan agree in both directions
    assert "     WHERE l.id IS NULL;" in sql
    assert "AND NOT EXISTS (SELECT 1 FROM _ext_plan p WHERE p.change_key = l.change_key);" in sql


def test_the_undo_swaps_the_values_and_journals_under_its_own_stamp() -> None:
    rows = qid_repair.changes()[:1]
    undo = qid_repair.render(rows, reversal=True)
    row = rows[0]
    assert f"'{row.new_value}', '{row.old_value}', '{row.change_key}-rollback'" in undo
    assert f"'{qid_repair.ROLLBACK_STAMP}'" in undo and f"'{qid_repair.RUN_STAMP}'" not in undo


def test_the_pre_flight_and_the_acceptance_compare_the_full_row() -> None:
    row = qid_repair.changes()[0]
    key = (row.site_id, row.kind)
    assert qid_repair.compare([row], {key: [row.old_value]}, want="old") == []
    assert qid_repair.compare([row], {key: [row.new_value]}, want="new") == []
    assert qid_repair.compare([row], {key: [row.old_value, row.new_value]}, want="new")
    assert qid_repair.compare([row], {}, want="old")


RESEARCH = REPO / "output" / "remediation" / "bcases" / "qid_research.jsonl"


def test_wave_two_is_every_open_wrong_link_the_research_names_and_nothing_else() -> None:
    research = {r["site_id"]: r["suggestion"] for r in lanes.read_jsonl(RESEARCH)}
    wave2 = qid_repair.WAVE2_SITES
    assert {site.site_id for site in wave2} == set(research)
    assert not {site.site_id for site in wave2} & {site.site_id for site in qid_repair.SITES}
    for site in wave2:
        if site.rule != "unresolved":
            assert (site.rule, site.new_qid) == (
                research[site.site_id]["rule"],
                research[site.site_id]["qid"],
            )
    # a research lead may be refused by hand, with its reason - never invented
    refused = [
        s.name
        for s in wave2
        if s.rule == "unresolved" and research[s.site_id]["rule"] != "unresolved"
    ]
    assert refused == ["Ramesses III Temple"]
    assert all(site.evidence for site in wave2)


def _research_distance(record: dict[str, Any], site: Any) -> float:
    """The metres the research measured for a settled site's position proof: rule B's candidate
    P625, rule A's candidate P625 or - where Wikidata points elsewhere - the article's coordinates."""
    candidate = next(c for c in record["candidates"] if c["qid"] == site.new_qid)
    if site.rule == "B" or (
        candidate["distance_m"] is not None and candidate["distance_m"] <= 1000
    ):
        return float(candidate["distance_m"])
    page = record["enwiki_page"]
    lat, lon = record["stored_point"]
    return haversine_distance(lat, lon, page["lat"], page["lon"]) * 1000.0


def test_every_wave_two_gate_is_the_distance_the_research_measured() -> None:
    """`gate_m` is typed by hand; the 1 km gate in `changes()` is only as good as that number, so it
    is read back against the research record it was copied from (to the 0.1 m the record keeps)."""
    research = {r["site_id"]: r for r in lanes.read_jsonl(RESEARCH)}
    settled = [s for s in qid_repair.WAVE2_SITES if s.rule != "unresolved"]
    assert len(settled) == 12
    for site in settled:
        measured = _research_distance(research[site.site_id], site)
        assert site.gate_m == pytest.approx(measured, abs=0.05), (site.name, site.gate_m, measured)
        assert measured <= qid_repair.GATE_M


def test_the_delivered_wave_two_statements_are_the_rendered_ones() -> None:
    wave = qid_repair.WAVE2
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    delivered = [
        qid_repair.Change(**{**r, "evidence": tuple(r["evidence"])})
        for r in lanes.read_jsonl(wave.out / "PLAN.jsonl")
    ]
    assert delivered == rows
    rendered = qid_repair.statements(rows, wave)
    for name in ("APPLY.sql", "ROLLBACK.sql"):
        assert (wave.out / name).read_text(encoding="utf-8") == rendered[name], name
    evidence_source = f'"source": "{wave.research}"'
    assert evidence_source in rendered["APPLY.sql"]
    assert f'"source": "{qid_repair.WAVE1.research}"' not in rendered["APPLY.sql"]


def test_a_wave_two_replacement_without_its_position_proof_is_refused() -> None:
    site = next(s for s in qid_repair.WAVE2_SITES if s.rule == "B")
    for gate in (None, qid_repair.GATE_M + 1.0):
        with pytest.raises(SystemExit, match="position proof"):
            qid_repair.changes((replace(site, gate_m=gate),), gate_m=qid_repair.GATE_M)
    assert qid_repair.changes((site,), gate_m=qid_repair.GATE_M)
    # wave 1's rules predate the gate: its entries carry no distance and still render
    assert qid_repair.changes() and all(s.gate_m is None for s in qid_repair.SITES)


def test_wave_two_renders_under_its_own_stamp_and_wave_one_is_what_was_applied() -> None:
    wave = qid_repair.WAVE2
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    sql = qid_repair.render(rows, reversal=False, wave=wave)
    assert f"'{wave.run_stamp}'" in sql and f"'{qid_repair.RUN_STAMP}'" not in sql
    assert f"{qid_repair.DIGEST_HEADER}{qid_repair.plan_digest(rows)}" in sql
    undo = qid_repair.render(rows, reversal=True, wave=wave)
    assert f"'{wave.rollback_stamp}'" in undo and f"'{wave.run_stamp}'" not in undo
    applied = (REPO / "output" / "remediation" / "qid_repair" / "APPLY.sql").read_text(
        encoding="utf-8"
    )
    assert applied == qid_repair.render(qid_repair.changes(), reversal=False)


def test_wave_two_check_and_verify_read_their_own_rows_and_stamp(
    tmp_path: Path, monkeypatch: Any
) -> None:
    wave = qid_repair.WAVE2
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    out = ["--wave", "2", "--dir", str(tmp_path)]
    assert qid_repair.main(["render", *out]) == 0

    def database(*, state: str, journal: bool) -> None:
        def psql(sql: str, *, host: str) -> str:
            if "FROM remediation_change_log" in sql:
                assert f"run_stamp = '{wave.run_stamp}'" in sql
                keys = [row.change_key for row in rows] if journal else []
                return "".join(json.dumps({"change_key": key}) + "\n" for key in keys)
            asked = set(re.findall(r"'([0-9a-f-]{36})'", sql))
            return "".join(
                json.dumps(
                    {
                        "site_id": row.site_id,
                        "kind": row.kind,
                        "value": row.old_value if state == "old" else row.new_value,
                    }
                )
                + "\n"
                for row in rows
                if row.site_id in asked
            )

        monkeypatch.setattr(lanes, "psql", psql)

    database(state="old", journal=False)
    assert qid_repair.main(["check", *out]) == 0
    assert qid_repair.main(["verify", *out]) == 1
    database(state="new", journal=True)
    assert qid_repair.main(["verify", *out]) == 0
    database(state="new", journal=False)
    assert qid_repair.main(["verify", *out]) == 1


# ── wave 3: the kept names on a generic or shared link ───────────────────────────────────────

SUSPECTS = REPO / "output" / "remediation" / "bcases" / "qid_research_suspects.jsonl"


def _as_committed(path: Path) -> bytes:
    """A delivered file as git stores it: this Windows checkout writes the plan files that
    `.gitattributes` does not pin to LF with CRLF, and their blobs hold LF (no CR of their own)."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_waves_one_and_two_still_render_byte_for_byte_what_is_committed(tmp_path: Path) -> None:
    for wave in (qid_repair.WAVE1, qid_repair.WAVE2):
        out = tmp_path / str(wave.number)
        qid_repair.write_files(out, wave)
        for name in ("PLAN.jsonl", "PLAN.md", "APPLY.sql", "ROLLBACK.sql"):
            assert (out / name).read_bytes() == _as_committed(wave.out / name), (wave.number, name)
        for name in ("APPLY.sql", "ROLLBACK.sql"):
            assert (out / name).read_bytes() == (wave.out / name).read_bytes(), (wave.number, name)


def test_wave_three_is_every_suspect_the_research_names_and_nothing_else() -> None:
    research = {r["site_id"]: r for r in lanes.read_jsonl(SUSPECTS)}
    wave3 = qid_repair.WAVE3_SITES
    assert len(wave3) == 39 and {site.site_id for site in wave3} == set(research)
    earlier = {site.site_id for site in (*qid_repair.SITES, *qid_repair.WAVE2_SITES)}
    assert not {site.site_id for site in wave3} & earlier
    for site in wave3:
        suggestion = research[site.site_id]["suggestion"]
        assert site.old_qid == research[site.site_id]["old_qid"], site.name
        if site.rule in ("A", "B"):
            assert (site.rule, site.new_qid) == (suggestion["rule"], suggestion["qid"])
    # a research lead may be refused by hand, with its reason - never invented
    refused = sorted(
        s.name
        for s in wave3
        if s.rule not in ("A", "B") and research[s.site_id]["suggestion"]["rule"] != "unresolved"
    )
    assert refused == ["Caesarea Philippi", "Madain Saleh"]
    assert all(site.evidence for site in wave3)
    assert qid_repair.outcome_counts(wave3) == {
        "replace": 2,
        "keep-type": 3,
        "duplicate-candidate": 23,
        "link-right": 5,
        "unresolved": 6,
    }


def test_every_wave_three_gate_is_the_distance_the_research_measured() -> None:
    research = {r["site_id"]: r for r in lanes.read_jsonl(SUSPECTS)}
    settled = [s for s in qid_repair.WAVE3_SITES if s.rule in ("A", "B")]
    assert [s.name for s in settled] == ["Ancient Theatre of Megalopolis", "Siega Verde"]
    for site in settled:
        measured = _research_distance(research[site.site_id], site)
        assert site.gate_m == pytest.approx(measured, abs=0.05), (site.name, site.gate_m, measured)
        assert measured <= qid_repair.GATE_M


def test_the_delivered_wave_three_files_are_the_rendered_ones(tmp_path: Path) -> None:
    wave = qid_repair.WAVE3
    assert wave.out == REPO / "output" / "remediation" / "qid_repair" / "wave3"
    assert wave.research == "qid-repair research 2026-09-23 (wave 3)"
    rows = qid_repair.write_files(tmp_path, wave)
    assert [(r.name, r.kind, r.old_value, r.new_value) for r in rows] == [
        ("Ancient Theatre of Megalopolis", "wikidata_qid", "Q823721", "Q22681531"),
        ("Siega Verde", "wikidata_qid", "Q552106", "Q2717874"),
    ]
    for name in ("PLAN.jsonl", "PLAN.md", "APPLY.sql", "ROLLBACK.sql"):
        assert (tmp_path / name).read_bytes() == _as_committed(wave.out / name), name
    apply_sql = (wave.out / "APPLY.sql").read_text(encoding="utf-8")
    assert f'"source": "{wave.research}"' in apply_sql
    assert f'"source": "{qid_repair.WAVE2.research}"' not in apply_sql


def test_the_wave_three_plan_names_every_site_once_under_its_outcome() -> None:
    wave = qid_repair.WAVE3
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    markdown = qid_repair.MARKDOWN[3](rows)
    assert markdown.startswith("# External-id repair, wave 3 (2026-09-23) - planned, not applied")
    assert (
        "2 row changes at 2 sites (run stamp `2026-09-23_external-id-repair-wave3`); the other 37 "
        "sites keep their rows exactly as they are: 3 keep-type, 23 duplicate-candidate, "
        "5 link-right, 6 unresolved."
    ) in markdown
    table = [line for line in markdown.splitlines() if line.startswith("| ") and "(`" in line]
    assert len(table) == len(wave.sites)
    for site in wave.sites:
        [line] = [line for line in table if f"(`{site.site_id}`)" in line]
        label = f"replace ({site.rule})" if site.rule in ("A", "B") else site.rule
        assert line.split(" | ")[1] == label, site.name


def test_a_kept_wave_three_site_carries_no_value_and_an_unknown_rule_is_refused() -> None:
    site = next(s for s in qid_repair.WAVE3_SITES if s.rule == "keep-type")
    for rule in qid_repair.UNCHANGED:
        assert qid_repair.changes((replace(site, rule=rule),), gate_m=qid_repair.GATE_M) == []
    with pytest.raises(SystemExit, match="cannot carry a new value"):
        qid_repair.changes((replace(site, new_qid="Q1"),), gate_m=qid_repair.GATE_M)
    with pytest.raises(SystemExit, match="rule 'keep'"):
        qid_repair.changes((replace(site, rule="keep"),), gate_m=qid_repair.GATE_M)


def test_a_wave_three_replacement_without_its_position_proof_is_refused() -> None:
    wave = qid_repair.WAVE3
    assert wave.gate_m == qid_repair.GATE_M
    site = next(s for s in wave.sites if s.rule == "B")
    for gate in (None, qid_repair.GATE_M + 1.0):
        with pytest.raises(SystemExit, match="position proof"):
            qid_repair.changes((replace(site, gate_m=gate),), gate_m=wave.gate_m)


def test_wave_three_renders_under_its_own_stamp() -> None:
    wave = qid_repair.WAVE3
    assert (wave.run_stamp, wave.rollback_stamp) == (
        "2026-09-23_external-id-repair-wave3",
        "2026-09-23_external-id-repair-wave3-rollback",
    )
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    sql = qid_repair.render(rows, reversal=False, wave=wave)
    assert f"'{wave.run_stamp}'" in sql and f"{qid_repair.DIGEST_HEADER}" in sql
    for earlier in (qid_repair.RUN_STAMP, qid_repair.WAVE2.run_stamp):
        assert earlier not in sql
    undo = qid_repair.render(rows, reversal=True, wave=wave)
    assert f"'{wave.rollback_stamp}'" in undo and f"'{wave.run_stamp}'" not in undo


def test_wave_three_check_and_verify_read_their_own_rows_and_stamp(
    tmp_path: Path, monkeypatch: Any
) -> None:
    wave = qid_repair.WAVE3
    rows = qid_repair.changes(wave.sites, gate_m=wave.gate_m)
    out = ["--wave", "3", "--dir", str(tmp_path)]
    assert qid_repair.main(["render", *out]) == 0

    def database(*, state: str, journal: bool) -> None:
        def psql(sql: str, *, host: str) -> str:
            if "FROM remediation_change_log" in sql:
                assert f"run_stamp = '{wave.run_stamp}'" in sql
                keys = [row.change_key for row in rows] if journal else []
                return "".join(json.dumps({"change_key": key}) + "\n" for key in keys)
            asked = set(re.findall(r"'([0-9a-f-]{36})'", sql))
            assert asked == {row.site_id for row in rows}
            return "".join(
                json.dumps(
                    {
                        "site_id": row.site_id,
                        "kind": row.kind,
                        "value": row.old_value if state == "old" else row.new_value,
                    }
                )
                + "\n"
                for row in rows
            )

        monkeypatch.setattr(lanes, "psql", psql)

    database(state="old", journal=False)
    assert qid_repair.main(["check", *out]) == 0
    assert qid_repair.main(["verify", *out]) == 1
    database(state="new", journal=True)
    assert qid_repair.main(["verify", *out]) == 0


def _repair_database(monkeypatch: Any, *, state: str, journal: bool) -> None:
    rows = qid_repair.changes()

    def psql(sql: str, *, host: str) -> str:
        if "FROM remediation_change_log" in sql:
            keys = [row.change_key for row in rows] if journal else []
            return "".join(json.dumps({"change_key": key}) + "\n" for key in keys)
        return "".join(
            json.dumps(
                {
                    "site_id": row.site_id,
                    "kind": row.kind,
                    "value": row.old_value if state == "old" else row.new_value,
                }
            )
            + "\n"
            for row in rows
        )

    monkeypatch.setattr(lanes, "psql", psql)


def test_check_and_verify_read_the_database_and_refuse_an_edited_statement(
    tmp_path: Path, monkeypatch: Any
) -> None:
    out = ["--dir", str(tmp_path)]
    assert qid_repair.main(["render", *out]) == 0
    _repair_database(monkeypatch, state="old", journal=False)
    assert qid_repair.main(["check", *out]) == 0
    assert qid_repair.main(["verify", *out]) == 1  # nothing applied yet: the old values are there
    _repair_database(monkeypatch, state="new", journal=True)
    assert qid_repair.main(["verify", *out]) == 0
    _repair_database(monkeypatch, state="new", journal=False)
    assert qid_repair.main(["verify", *out]) == 1  # the rows moved, but nobody journalled it
    # a hand edit to the body, under an untouched digest header, is refused before any read
    apply_sql = tmp_path / "APPLY.sql"
    text = apply_sql.read_text(encoding="utf-8")
    apply_sql.write_text(text.replace("IF n <> 1 THEN", "IF n < 0 THEN"), encoding="utf-8")
    monkeypatch.setattr(lanes, "psql", lambda sql, host: pytest.fail("read an edited plan"))
    with pytest.raises(SystemExit, match="APPLY.sql is not the statement this plan renders"):
        qid_repair.main(["check", *out])
    (tmp_path / "REHEARSAL.sql").unlink()
    apply_sql.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match="REHEARSAL.sql does not exist"):
        qid_repair.main(["check", *out])


# ── measure_review_holds: the two writer rules of 2026-09-23 on the rows already decided ─────


def _decided(key: str, column: str, old: str, new: str, reason: str) -> dict[str, Any]:
    """One row of a lane's plan, as far as the measurement reads it."""
    return {
        "change_key": key,
        "batch_id": "batch-0001",
        "site_id": SITE,
        "site_name": f"Site {key}",
        "column": column,
        "old_value": old,
        "new_value": new,
        "verdict": {"reason": reason},
    }


def test_the_measurement_counts_holds_false_holds_and_bucket_moves_with_the_writers_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        # held by hand, and named by the rule: its own sentence says a half fails
        _decided("k1", "site_type", "Temple", "Ruin", "Both halves fail: the stored type holds."),
        # held by hand, a bucket nudge the rule cannot name but the bucket gate refuses
        _decided("k2", "period_start", "-3000", "-2999", "Both halves hold - it moved a year."),
        # held by hand, and named by the rule in the value half's words
        _decided("k6", "site_type", "Tomb", "Dolmen", "The proposed `Dolmen` is contradicted."),
        # written, cleanly cleared
        _decided("k3", "period_start", "-1500", "-600", "Both halves hold - founded c. 600 BC."),
        # written, and the rule would have held it
        _decided("k4", "country", "Spain", "France", "The stored value is not shown wrong."),
        # stopped at the boundary check
        _decided("k5", "country", "Peru", "Chile", "Both halves hold - the page says Chile."),
    ]
    rows_path = tmp_path / "ALL_ROWS.jsonl"
    lanes.write_jsonl(rows_path, rows)
    holds = [{"change_key": key} for key in ("k1", "k2", "k6")]
    lanes.write_jsonl(tmp_path / "HOLDS.jsonl", holds)
    (tmp_path / "written.txt").write_text("k3\nk4\n", encoding="utf-8")
    journal = [{"change_key": "k3", "old_value": "-1500", "new_value": "-600"}]
    lanes.write_jsonl(tmp_path / "journal.jsonl", journal)
    review = tmp_path / "run" / "batch-0001" / "reviews" / "s%2Fcountry.txt"
    review.parent.mkdir(parents=True)
    review.write_text("WHY: Neither half holds.\nREFUTED: NO\n", encoding="utf-8")
    monkeypatch.setitem(lanes.REVIEWED_PLAN_KEYS_SHA256, lanes.MASS, lanes.keys_digest(rows))

    argv = ["--rows", str(rows_path), "--holds", str(tmp_path / "HOLDS.jsonl")]
    argv += ["--run-dir", str(tmp_path / "run"), "--written-keys", str(tmp_path / "written.txt")]
    argv += ["--out-dir", str(tmp_path / "logs" / "review_holds")]
    assert measure_review_holds.main([*argv, "--journal", str(tmp_path / "journal.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "plan rows 6: held 3, written 2, boundary 1" in out
    assert "recall on the hand holds: 2/3" in out
    assert "false holds on written rows: 1/2" in out
    assert "held: 1 of 1 period_start rows" in out  # -3000 -> -2999 stays in 4500 - 3000 BC
    assert "written: 1 of 1 period_start rows" in out  # -1500 -> -600 stays in 1500 - 500 BC
    assert "hand holds caught by the bucket gate or the contradiction hold: 3" in out
    assert "production journal: 1 of 1 period_start rows inside the stored bucket" in out
    assert "neither half holds" in out and "{'NO': 1}" in out
    # the rows Martin decides on (HUMAN_ONLY.md B11): written rows the hold would hold, and written
    # period_start rows that stayed in their bucket, each with its key, values and reason
    out_dir = tmp_path / "logs" / "review_holds"
    held = lanes.read_jsonl(out_dir / measure_review_holds.WRITTEN_HELD_FILE)
    assert [(r["change_key"], r["phrase"], r["reason"]) for r in held] == [
        ("k4", "the stored value is not shown wrong", "The stored value is not shown wrong.")
    ]
    bucket = lanes.read_jsonl(out_dir / measure_review_holds.WRITTEN_BUCKET_FILE)
    assert [(r["change_key"], r["old_value"], r["new_value"], r["bucket"]) for r in bucket] == [
        ("k3", "-1500", "-600", "1500 - 500 BC")
    ]
    table = (out_dir / measure_review_holds.WRITTEN_HELD_FILE).with_suffix(".md")
    assert "| k4 |" in table.read_text(encoding="utf-8")
    assert "| k3 |" in (out_dir / measure_review_holds.WRITTEN_BUCKET_FILE).with_suffix(
        ".md"
    ).read_text(encoding="utf-8")
    # the measurement refuses a plan that is not the lane's reviewed one
    monkeypatch.setitem(lanes.REVIEWED_PLAN_KEYS_SHA256, lanes.MASS, "0" * 64)
    with pytest.raises(SystemExit, match="not the plan the production rows"):
        measure_review_holds.main(argv)


# ── wave 4: the curated source_url values that hold two URLs ─────────────────────────────────

MEGA = "https://www.megalithic.co.uk/article.php?sid="
WIKI = "https://en.wikipedia.org/wiki/"
KHAN = "https://www.khanacademy.org/humanities/petra"
KHAN_REAL = (
    "https://www.khanacademy.org/humanities/ap-art-history/west-and-central-asia-apahh/"
    "west-asia/a/petra-rock-cut-facades"
)
W4_SITES = {
    "alpha": "00000000-0000-4000-8000-0000000000a1",
    "petra": "00000000-0000-4000-8000-0000000000a2",
    "blog": "00000000-0000-4000-8000-0000000000a3",
    "taken": "00000000-0000-4000-8000-0000000000a4",
    "nopage": "00000000-0000-4000-8000-0000000000a5",
    "disamb": "00000000-0000-4000-8000-0000000000a6",
    "twin1": "00000000-0000-4000-8000-0000000000a7",
    "twin2": "00000000-0000-4000-8000-0000000000a8",
    "import": "00000000-0000-4000-8000-0000000000a9",
    "three": "00000000-0000-4000-8000-0000000000aa",
    "clean": "00000000-0000-4000-8000-0000000000ab",
    "town": "00000000-0000-4000-8000-0000000000ac",
    "cityish": "00000000-0000-4000-8000-0000000000ad",
}
HOLDER = "00000000-0000-4000-8000-0000000000ff"


def _w4_site(key: str, name: str, url: str, source: str = "ancient_nerds", **ids: list[str]):
    return {
        "site_id": W4_SITES[key],
        "name": name,
        "source_id": source,
        "source_url": url,
        "created": "2026-03-04",
        "external_ids": dict(ids),
    }


def _res(title: str | None, qid: str | None, *, disambiguation: bool = False) -> dict:
    return {
        "canonical_title": title,
        "qid": qid,
        "disambiguation": disambiguation,
        "redirected": False,
    }


def _w4_record() -> dict:
    """Every shape the wave meets: the 19 Mesoamerican one (Alpha), Petra, a blog second URL, an
    item another curated site carries, no page, a disambiguation page, two sites on one item, a
    row that is not curated, three URLs, a clean title already stored, an article about the
    municipality (Town), and one whose item carries the real Petra's P31 set (Cityish, with a
    broken stored title)."""
    return {
        "read_at": "2026-09-23T10:00:00Z",
        "resolved_at": "2026-09-23T10:00:05Z",
        "scope": qid_repair.SCOPE_SQL,
        "sites": [
            _w4_site("alpha", "Alpha", f"{MEGA}1\n{WIKI}Alpha_(site)"),
            _w4_site("petra", "Petra", f"{WIKI}Petra\n{KHAN}", enwiki_title=[f"Petra\n{KHAN}"]),
            _w4_site("blog", "Blogged", f"{MEGA}3\nhttps://rockart.blogspot.com/x.html"),
            _w4_site("taken", "Taken", f"{MEGA}4\n{WIKI}Taken"),
            _w4_site("nopage", "Nopage", f"{MEGA}5\n{WIKI}Nopage"),
            _w4_site("disamb", "Disamb", f"{MEGA}6\n{WIKI}Disamb"),
            _w4_site("twin1", "Twin one", f"{MEGA}7\n{WIKI}Twin_one"),
            _w4_site("twin2", "Twin two", f"{MEGA}8\n{WIKI}Twin_two"),
            _w4_site("import", "Imported", f"{MEGA}9\n{WIKI}Imported", source="megalithic"),
            _w4_site("three", "Three", f"{MEGA}10\n{WIKI}Three\n{MEGA}11"),
            _w4_site("clean", "Clean", f"{MEGA}12\n{WIKI}Clean", enwiki_title=["Clean site"]),
            _w4_site("town", "Town site", f"{MEGA}13\n{WIKI}Town"),
            _w4_site(
                "cityish", "Cityish", f"{WIKI}Cityish\n{KHAN}", enwiki_title=[f"Cityish\n{KHAN}"]
            ),
        ],
        "resolutions": {
            "Alpha (site)": _res("Alpha", "Q1"),
            "Petra": _res("Petra", "Q5788"),
            "Taken": _res("Taken", "Q4"),
            "Nopage": _res(None, None),
            "Disamb": _res("Disamb", "Q6", disambiguation=True),
            "Twin one": _res("Twin", "Q7"),
            "Twin two": _res("Twin", "Q7"),
            "Imported": _res("Imported", "Q9"),
            "Clean": _res("Clean", "Q12"),
            "Town": _res("Town", "Q20"),
            "Cityish": _res("Cityish", "Q21"),
        },
        "qid_holders": {
            "Q1": [],
            "Q4": [{"site_id": HOLDER, "name": "Holder", "source_url": f"{WIKI}Taken"}],
            "Q5788": [],
            "Q7": [],
            "Q9": [],
            "Q12": [],
            "Q20": [],
            "Q21": [],
        },
        "p31": {
            "Q1": ["archaeological site", "Maya site in Mexico"],
            "Q4": ["archaeological site"],
            "Q5788": ["ancient city", "archaeological site"],
            "Q6": ["Wikimedia disambiguation page"],
            "Q7": ["archaeological site"],
            "Q9": ["archaeological site"],
            "Q12": ["archaeological site"],
            "Q20": ["municipality of Mexico"],
            "Q21": ["ancient city", "city", "archaeological site"],
        },
    }


def _w4_plan() -> Any:
    return qid_repair.split_plan(_w4_record(), hand_read=())


def test_wave_four_keeps_the_first_url_and_stores_the_article_as_the_boot_refresh_would() -> None:
    rows = _w4_plan().rows
    alpha = [(r.table, r.kind, r.old_value, r.new_value) for r in rows if r.name == "Alpha"]
    assert alpha == [
        ("unified_sites", "source_url", f"{MEGA}1\n{WIKI}Alpha_(site)", f"{MEGA}1"),
        ("site_external_ids", "enwiki_title", None, "Alpha"),
        ("site_external_ids", "wikidata_qid", None, "Q1"),
    ]
    by_kind = {r.kind: r for r in rows if r.name == "Alpha"}
    assert (by_kind["source_url"].test_id, by_kind["source_url"].confidence) == (
        "EXT/source_url",
        "authoritative",
    )
    assert by_kind["source_url"].row_pk == W4_SITES["alpha"]
    assert by_kind["source_url"].column == "source_url"
    assert by_kind["wikidata_qid"].row_pk == f"{W4_SITES['alpha']}/wikidata_qid"
    assert by_kind["wikidata_qid"].column == "value"
    assert {r.confidence for r in rows if r.table == "site_external_ids"} == {"two_source"}
    assert "no other curated site carries Q1" in by_kind["wikidata_qid"].evidence[-1]


def test_petras_broken_title_is_corrected_and_its_item_added() -> None:
    petra = [
        (r.table, r.kind, r.old_value, r.new_value) for r in _w4_plan().rows if r.name == "Petra"
    ]
    assert petra == [
        ("unified_sites", "source_url", f"{WIKI}Petra\n{KHAN}", f"{WIKI}Petra"),
        ("site_external_ids", "enwiki_title", f"Petra\n{KHAN}", "Petra"),
        ("site_external_ids", "wikidata_qid", None, "Q5788"),
    ]


def test_what_the_rules_do_not_write_is_left_with_its_reason() -> None:
    plan = _w4_plan()
    left = {(item.name, item.what): item.reason for item in plan.left}
    assert left == {
        ("Blogged", "external ids"): "neither URL is an English Wikipedia article",
        ("Taken", "external ids"): (
            f"{WIKI}Taken: Q4 is already carried by the curated site Holder ({HOLDER})"
        ),
        ("Nopage", "external ids"): f"{WIKI}Nopage: no English Wikipedia page by that title",
        ("Disamb", "external ids"): f"{WIKI}Disamb: 'Disamb' is a disambiguation page",
        ("Twin one", "external ids"): (
            f"{WIKI}Twin_one: Q7 is the item of Twin two ({W4_SITES['twin2']}) too"
        ),
        ("Twin two", "external ids"): (
            f"{WIKI}Twin_two: Q7 is the item of Twin one ({W4_SITES['twin1']}) too"
        ),
        ("Imported", "source_url"): "a megalithic row, not curated",
        ("Three", "source_url"): "not two URLs joined by one newline",
        ("Clean", "enwiki_title"): "the site already carries ['Clean site']",
        ("Town site", "external ids"): (
            f"{WIKI}Town: Q20 is a place, not the site (P31: municipality of Mexico)"
        ),
        ("Cityish", "external ids"): (
            f"{WIKI}Cityish: Q21 is a place, not the site (P31: ancient city, city, archaeological site)"
        ),
    }
    # a left site's source_url is still split where it is curated and two URLs; nothing else moves
    written = {(r.name, r.kind) for r in plan.rows}
    assert {name for name, kind in written if kind == "source_url"} == {
        "Alpha",
        "Petra",
        "Blogged",
        "Taken",
        "Nopage",
        "Disamb",
        "Twin one",
        "Twin two",
        "Clean",
        "Town site",
        "Cityish",
    }
    assert ("Clean", "wikidata_qid") in written and ("Clean", "enwiki_title") not in written
    for name in ("Taken", "Nopage", "Disamb", "Twin one", "Twin two", "Blogged", "Town site"):
        assert not {kind for n, kind in written if n == name} - {"source_url"}, name


def test_a_record_without_the_resolution_a_site_needs_is_refused() -> None:
    record = _w4_record()
    del record["resolutions"]["Alpha (site)"]
    with pytest.raises(SystemExit, match="run `resolve` again"):
        qid_repair.split_plan(record, hand_read=())


def test_a_control_character_is_spelled_outside_the_quotes() -> None:
    assert qid_repair.sql_value("a\nb'c") == "('a' || chr(10) || 'b''c')"
    assert qid_repair.sql_value("\ta") == "(chr(9) || 'a')"
    for plain in ("Petra", "O'Brien", None):
        assert qid_repair.sql_value(plain) == lanes.sql_text(plain)


def _w4_rows() -> list[Any]:
    return _w4_plan().rows


def test_wave_four_writes_source_url_through_the_primitive_and_new_rows_only_where_none_is() -> (
    None
):
    sql = qid_repair.render_split(_w4_rows(), reversal=False)
    # the source_url rows: the journal primitive, under the wave's stamp
    assert "moved := moved + apply_remediation_change(" in sql
    assert (
        "            'unified_sites', 'source_url', 'id', r.site_id::text, r.old_value, r.new_value,\n"
        "            r.test_id, '2026-09-23_source-url-split-wave4', r.change_key, r.confidence, "
        "r.evidence, r.site_id);"
    ) in sql
    # a two-URL value never stands raw in the file
    assert f"'{MEGA}1' || chr(10) || '{WIKI}Alpha_(site)'" in sql
    assert f"{MEGA}1\n" not in sql
    # guard 2: the source_url still holds the old value
    assert "     WHERE u.source_url IS DISTINCT FROM p.old_value;" in sql
    assert "source_url value(s) no longer hold the planned old value', bad;" in sql
    # guard 3: a row with an old value is the one row of its kind and holds it
    assert "     WHERE p.old_value IS NOT NULL\n" in sql
    assert "external-id row(s) no longer hold the planned old value', bad;" in sql
    # guard 4: a row planned as new is new
    assert (
        "     WHERE p.old_value IS NULL\n"
        "       AND EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = p.site_id "
        "AND e.kind = p.kind);"
    ) in sql
    assert "already hold a row of a kind planned as new', bad;" in sql
    # guard 5: no other curated site carries a planned item
    assert (
        "      JOIN site_external_ids e ON e.kind = p.kind AND e.value = p.new_value "
        "AND e.site_id <> p.site_id"
    ) in sql
    assert (
        "      JOIN unified_sites u ON u.id = e.site_id AND u.source_id = 'ancient_nerds'\n"
        "     WHERE p.kind = 'wikidata_qid';"
    ) in sql
    assert "planned item(s) are carried by another curated site', bad;" in sql
    # the writes: an insert where the old value is NULL, else a conditional update - no DELETE
    assert "        IF r.old_value IS NULL THEN\n            INSERT INTO site_external_ids" in sql
    assert "WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;" in sql
    assert "DELETE" not in sql
    assert "IF n <> 1 THEN" in sql and "IF moved <> expected THEN" in sql
    # invariants: new values held, the one row of its kind, the journal both ways
    assert "source_url value(s) do not hold the new value', bad;" in sql
    assert "external-id row(s) do not hold the new value', bad;" in sql
    assert "row(s) have no matching journal row', bad;" in sql
    assert "journalled % row(s) outside the plan'" in sql
    assert sql.rstrip().endswith(
        "FROM remediation_change_log WHERE run_stamp = '2026-09-23_source-url-split-wave4';"
    )
    assert "\nCOMMIT;\n" in sql and "\nROLLBACK;\n" not in sql
    rehearsal = qid_repair.render_split(_w4_rows(), reversal=False, rehearsal=True)
    assert "\nROLLBACK;\n" in rehearsal and "\nCOMMIT;\n" not in rehearsal


def test_the_reversal_deletes_exactly_the_inserted_rows_and_puts_every_old_value_back() -> None:
    rows = _w4_rows()
    undo = qid_repair.render_split(rows, reversal=True)
    assert (
        "        ELSIF r.new_value IS NULL THEN\n"
        "            DELETE FROM site_external_ids\n"
        "             WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;"
    ) in undo
    assert "'2026-09-23_source-url-split-wave4-rollback'" in undo
    assert "'2026-09-23_source-url-split-wave4'" not in undo
    new_qid = next(r for r in rows if r.name == "Alpha" and r.kind == "wikidata_qid")
    assert (
        f"'{new_qid.site_id}'::uuid, 'wikidata_qid', 'Q1', NULL, '{new_qid.change_key}-rollback'"
    ) in undo
    title = next(r for r in rows if r.name == "Petra" and r.kind == "enwiki_title")
    assert f"'Petra', ('Petra' || chr(10) || '{KHAN}'), '{title.change_key}-rollback'" in undo
    url = next(r for r in rows if r.name == "Alpha" and r.kind == "source_url")
    assert f"'{MEGA}1', ('{MEGA}1' || chr(10) || '{WIKI}Alpha_(site)')" in undo
    assert url.change_key + "-rollback" in undo
    assert "migration 0023 is applied, its CHECK refuses the two-URL source_url" in undo


def test_a_statement_is_refused_for_a_new_value_with_a_control_character() -> None:
    row = replace(_w4_rows()[0], new_value="a\nb")
    with pytest.raises(SystemExit, match="control character"):
        qid_repair.render_split([row], reversal=False)


def test_the_plan_line_of_waves_one_to_three_carries_no_table_key() -> None:
    row = qid_repair.changes()[0]
    assert "table" not in json.loads(row.to_json_line())
    url = next(r for r in _w4_rows() if r.table == "unified_sites")
    assert json.loads(url.to_json_line())["table"] == "unified_sites"
    # the key of an external-id row is the one waves 1-3 computed
    assert qid_repair.change_key(
        row.site_id, row.kind, row.old_value, row.new_value, row.test_id
    ) == (row.change_key)


def test_waves_one_to_three_still_render_byte_for_byte_beside_wave_four(tmp_path: Path) -> None:
    for wave in (qid_repair.WAVE1, qid_repair.WAVE2, qid_repair.WAVE3):
        out = tmp_path / str(wave.number)
        qid_repair.write_files(out, wave)
        for name in ("PLAN.jsonl", "PLAN.md", "APPLY.sql", "ROLLBACK.sql"):
            assert (out / name).read_bytes() == _as_committed(wave.out / name), (wave.number, name)


def test_the_delivered_wave_four_files_are_the_rendered_ones(tmp_path: Path) -> None:
    wave = qid_repair.WAVE4
    assert (wave.run_stamp, wave.out) == (
        "2026-09-23_source-url-split-wave4",
        REPO / "output" / "remediation" / "qid_repair" / "wave4",
    )
    (tmp_path / qid_repair.RESOLUTION).write_bytes(_as_committed(wave.out / qid_repair.RESOLUTION))
    rows = qid_repair.write_files(tmp_path, wave)
    for name in ("PLAN.jsonl", "PLAN.md", "APPLY.sql", "ROLLBACK.sql"):
        assert (tmp_path / name).read_bytes() == _as_committed(wave.out / name), name
    counts = {}
    for row in rows:
        what = (
            "source_url"
            if row.table == "unified_sites"
            else ("new" if row.old_value is None else "corrected")
        )
        counts[what] = counts.get(what, 0) + 1
    assert counts == {"source_url": 20, "new": 29, "corrected": 1}
    plan = qid_repair.split_plan(
        qid_repair.load_resolution(wave.out), hand_read=qid_repair.WAVE4_HAND_READ
    )
    left = {item.name: item.reason for item in plan.left}
    assert sorted(left) == [
        "Acanceh",
        "Atzompa",
        "Cantil de las animas",
        "Cerro De Trincheras",
        "Chiapa de Corzo",
    ]
    assert all(item.what == "external ids" for item in plan.left)
    for name, qid in (
        ("Acanceh", "Q8186545"),
        ("Atzompa", "Q3846612"),
        ("Cerro De Trincheras", "Q1434929"),
    ):
        assert f"{qid} is a place, not the site" in left[name], name
    assert (
        "Q4384315 is already carried by the curated site Zoque Culture" in left["Chiapa de Corzo"]
    )
    assert [(d["name"], d["qid"], d["others"][0]["site_id"]) for d in plan.duplicates] == [
        ("Chiapa de Corzo", "Q4384315", "ed186ea9-9ed1-415d-828b-97d9f21401d2")
    ]


def test_resolve_reads_production_and_asks_only_for_the_article_titles() -> None:
    sent: list[str] = []
    asked: list[list[str]] = []

    def run(sql: str) -> str:
        sent.append(sql)
        if sql == qid_repair.SCOPE_SQL:
            rows = [
                {k: v for k, v in s.items() if k != "external_ids"}
                for s in _w4_record()["sites"][:3]
            ]
            return "".join(json.dumps(r) + "\n" for r in rows)
        if "FROM site_external_ids WHERE site_id::text IN" in sql:
            return (
                json.dumps(
                    {
                        "site_id": W4_SITES["petra"],
                        "kind": "enwiki_title",
                        "value": f"Petra\n{KHAN}",
                    }
                )
                + "\n"
            )
        assert "e.kind = 'wikidata_qid' AND u.source_id = 'ancient_nerds'" in sql
        assert set(re.findall(r"'(Q\d+)'", sql)) == {"Q1", "Q5788"}
        assert sql.startswith(
            "SELECT to_jsonb(t)::text FROM (SELECT e.value AS qid, e.site_id::text AS site_id, "
            "u.name, u.source_url "
        )
        holder = {"qid": "Q1", "site_id": HOLDER, "name": "Holder", "source_url": f"{WIKI}A"}
        return json.dumps(holder) + "\n"

    def resolve(titles: list[str]) -> dict:
        asked.append(titles)
        return {
            t: TitleResolution(t, t.removesuffix(" (site)"), q, None, None, False, False)
            for t, q in (("Alpha (site)", "Q1"), ("Petra", "Q5788"))
        }

    classed: list[list[str]] = []

    def classes(qids: list[str]) -> dict[str, list[str]]:
        classed.append(qids)
        return {"Q1": ["archaeological site"], "Q5788": ["ancient city", "city"]}

    record = qid_repair.resolve_split(run, resolve=resolve, classes=classes, now=lambda: "T")
    assert asked == [["Alpha (site)", "Petra"]]
    assert classed == [["Q1", "Q5788"]]
    assert record["p31"] == {"Q1": ["archaeological site"], "Q5788": ["ancient city", "city"]}
    assert r"source_url ~ '[\x00-\x1f\x7f]'" in sent[0]
    assert record["sites"][1]["external_ids"] == {"enwiki_title": [f"Petra\n{KHAN}"]}
    assert record["sites"][0]["external_ids"] == {}
    assert record["qid_holders"] == {
        "Q1": [{"site_id": HOLDER, "name": "Holder", "source_url": f"{WIKI}A"}],
        "Q5788": [],
    }
    assert record["resolutions"]["Petra"] == _res("Petra", "Q5788")
    with pytest.raises(SystemExit, match="only wave 4 is resolved"):
        qid_repair.main(["resolve", "--wave", "3"])


def test_wave_four_check_and_verify_read_both_tables(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(qid_repair, "WAVE4_HAND_READ", ())
    qid_repair.write_resolution(tmp_path, _w4_record())
    out = ["--wave", "4", "--dir", str(tmp_path)]
    assert qid_repair.main(["render", *out]) == 0
    rows = _w4_rows()

    def database(*, state: str, journal: bool) -> None:
        def psql(sql: str, *, host: str) -> str:
            if "FROM remediation_change_log" in sql:
                assert "run_stamp = '2026-09-23_source-url-split-wave4'" in sql
                keys = [row.change_key for row in rows] if journal else []
                return "".join(json.dumps({"change_key": key}) + "\n" for key in keys)
            asked = set(re.findall(r"'([0-9a-f-]{36})'", sql))
            lines = []
            for row in rows:
                value = row.old_value if state == "old" else row.new_value
                if row.site_id not in asked or value is None:
                    continue
                if row.table == "unified_sites" and "FROM unified_sites WHERE id IN" in sql:
                    assert f"'{row.site_id}'::uuid" in sql
                    lines.append({"site_id": row.site_id, "value": value})
                if row.table == "site_external_ids" and "FROM site_external_ids" in sql:
                    lines.append({"site_id": row.site_id, "kind": row.kind, "value": value})
            return "".join(json.dumps(line) + "\n" for line in lines)

        monkeypatch.setattr(lanes, "psql", psql)

    database(state="old", journal=False)
    assert qid_repair.main(["check", *out]) == 0
    assert qid_repair.main(["verify", *out]) == 1
    database(state="new", journal=True)
    assert qid_repair.main(["verify", *out]) == 0
    assert qid_repair.main(["check", *out]) == 1


def test_a_new_row_is_compared_as_no_row() -> None:
    row = next(r for r in _w4_rows() if r.old_value is None)
    key = (row.site_id, row.kind)
    assert qid_repair.compare([row], {}, want="old") == []
    assert qid_repair.compare([row], {key: [row.new_value]}, want="old")
    assert qid_repair.compare([row], {key: [row.new_value]}, want="new") == []


def test_a_place_level_item_is_refused_for_both_kinds_and_the_source_url_is_still_split() -> None:
    """Orchestrator decision 2026-09-23: no link to a town or municipality (the defect waves 1-3
    repaired). The gate is waves 2-3's own, `bcases.qid_research.is_site_kind`, not a copy."""
    rows = _w4_rows()
    for name, first in (("Town site", f"{MEGA}13"), ("Cityish", f"{WIKI}Cityish")):
        mine = [(r.kind, r.new_value) for r in rows if r.name == name]
        assert mine == [("source_url", first)], name
    # the real Petra's P31 set carries plain "city" beside "ancient city": the gate refuses it,
    # so a broken stored title stays and PLAN.md says so
    plan = _w4_plan()
    markdown = qid_repair.wave4_markdown(plan)
    assert (
        "* Cityish keeps its stored enwiki_title value with a control character: the wave refuses "
        "the article's resolution"
    ) in markdown
    assert (
        "The manual `--all` path reads every curated site whose `source_url` is an English "
        "Wikipedia article, and would write the ids this wave refuses for Cityish"
    ) in markdown
    from bcases import qid_research

    assert qid_repair.is_site_kind is qid_research.is_site_kind  # imported, not copied
    # a record without the item's classes cannot be judged
    record = _w4_record()
    del record["p31"]["Q20"]
    with pytest.raises(SystemExit, match="no P31 of Q20"):
        qid_repair.split_plan(record, hand_read=())


def test_a_shared_item_is_listed_as_a_duplicate_candidate_with_its_evidence() -> None:
    plan = _w4_plan()
    assert [(d["name"], d["qid"], [o["name"] for o in d["others"]]) for d in plan.duplicates] == [
        ("Taken", "Q4", ["Holder"]),
        ("Twin one", "Q7", ["Twin two"]),
        ("Twin two", "Q7", ["Twin one"]),
    ]
    markdown = qid_repair.wave4_markdown(plan)
    assert "## Duplicate candidates (the owner's merge, not a link)" in markdown
    assert (
        f"| Taken (`{W4_SITES['taken']}`) | Holder (`{HOLDER}`) | `Q4` | this site's article "
        f"{WIKI}Taken resolves to `Q4`, the item the other row carries; the other row's "
        f"source_url is `{WIKI}Taken` - the same article |"
    ) in markdown
    # a place-level item two sites share is no duplicate: both link a town, not each other
    record = _w4_record()
    record["resolutions"]["Twin one"] = _res("Twin", "Q20")
    record["resolutions"]["Twin two"] = _res("Twin", "Q20")
    assert [d["name"] for d in qid_repair.split_plan(record, hand_read=()).duplicates] == ["Taken"]


def test_the_class_read_refuses_a_class_it_cannot_name(monkeypatch: Any) -> None:
    class Net:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> Net:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr(qid_repair, "Fetcher", Net)
    monkeypatch.setattr(
        qid_repair.bcases_collect,
        "fetch_claims",
        lambda net, qids: {"Q1": {"p31": ["Q839954", "Q3024240"]}, "Q2": {"p31": ["Q515"]}},
    )
    labels = {"Q839954": "archaeological site", "Q3024240": "historical country", "Q515": "city"}
    monkeypatch.setattr(qid_repair.bcases_collect, "fetch_labels", lambda net, qids: dict(labels))
    assert qid_repair.item_classes(["Q1", "Q2"]) == {
        "Q1": ["archaeological site", "historical country"],
        "Q2": ["city"],
    }
    labels["Q515"] = None
    with pytest.raises(SystemExit, match="no English label for the P31 class"):
        qid_repair.item_classes(["Q1", "Q2"])


def _petra_rows(plan: Any) -> list[tuple[str, str | None, str]]:
    return [(r.kind, r.old_value, r.new_value) for r in plan.rows if r.name == "Petra"]


def test_petra_is_written_by_its_hand_read_entry_and_refused_without_it() -> None:
    """Orchestrator decision 2026-09-23: Petra is a hand-read entry, not a looser rule."""
    record = qid_repair.load_resolution(qid_repair.WAVE4.out)
    without = qid_repair.split_plan(record, hand_read=())
    assert _petra_rows(without) == [
        ("source_url", f"{WIKI}Petra\n{KHAN_REAL}", f"{WIKI}Petra"),
    ]
    assert {item.name: item.reason for item in without.left}["Petra"] == (
        f"{WIKI}Petra: Q5788 is a place, not the site (P31: ancient city, city, archaeological site)"
    )
    plan = qid_repair.split_plan(record, hand_read=qid_repair.WAVE4_HAND_READ)
    assert _petra_rows(plan) == [
        ("source_url", f"{WIKI}Petra\n{KHAN_REAL}", f"{WIKI}Petra"),
        ("enwiki_title", f"Petra\n{KHAN_REAL}", "Petra"),
        ("wikidata_qid", None, "Q5788"),
    ]
    assert "Petra" not in {item.name for item in plan.left}
    (entry,) = qid_repair.WAVE4_HAND_READ
    qid_row = next(r for r in plan.rows if r.name == "Petra" and r.kind == "wikidata_qid")
    assert f"hand-read, overriding: {entry.overrides}" in qid_row.evidence
    assert set(entry.evidence) <= set(qid_row.evidence)
    # the quoted evidence names what was read: the classes, the heritage listing, the article
    quoted = " ".join(entry.evidence)
    for fact in ("Q839954", "Q15661340", "Q515", "P1435", "Q9259", "P757", "326", "exact title"):
        assert fact in quoted, fact
    markdown = qid_repair.wave4_markdown(plan)
    assert "## Hand-read (a refusal of the rule overridden by quoted evidence)" in markdown
    assert f"| Petra (`{entry.site_id}`) | {entry.overrides} | " in markdown


def _hand(key: str, overrides: str, *evidence: str) -> Any:
    return qid_repair.HandRead(W4_SITES[key], key, overrides, evidence or ("read by hand",))


def test_a_hand_entry_must_name_the_refusal_it_overrides() -> None:
    record = _w4_record()
    refusal = "Q21 is a place, not the site (P31: ancient city, city, archaeological site)"
    plan = qid_repair.split_plan(record, hand_read=(_hand("cityish", refusal),))
    assert [(r.kind, r.new_value) for r in plan.rows if r.name == "Cityish"] == [
        ("source_url", f"{WIKI}Cityish"),
        ("enwiki_title", "Cityish"),
        ("wikidata_qid", "Q21"),
    ]
    for hand, says in (
        # another reason than the rule's
        (_hand("cityish", "Q21 is a disambiguation page"), "names the refusal it overrides"),
        # a site the rule did not refuse
        (_hand("alpha", "Q1 is a place, not the site (P31: x)"), "names the refusal it overrides"),
        # a refusal that is not the rule's to override: another curated site carries the item
        (
            _hand("taken", f"Q4 is already carried by the curated site Holder ({HOLDER})"),
            "names the refusal it overrides",
        ),
        # a site whose article the wave never resolves
        (_hand("blog", "neither URL is an English Wikipedia article"), "resolves no article"),
    ):
        with pytest.raises(SystemExit, match=says):
            qid_repair.split_plan(record, hand_read=(hand,))
    empty = qid_repair.HandRead(W4_SITES["cityish"], "cityish", refusal, ())
    with pytest.raises(SystemExit, match="quotes no evidence"):
        qid_repair.split_plan(record, hand_read=(empty,))
