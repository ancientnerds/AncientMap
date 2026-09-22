"""The write and acceptance instruments (`output/remediation/tools/`), tested without a database.

These scripts wrote and accepted the 994 production rows of 2026-09-22 and had no tests of their own.
Three things are pinned here, each by a test that goes red when its guard is removed:

* **lanes** - a second run (the gap run) must never be read as the mass run: its batches are planned
  from its own directory, and a batch applied in the mass lane cannot suppress a gap batch. The
  default lane is still exactly the mass run's paths.
* **the write gate's stale-plan guard** - the per-row apply addresses rows by position in the writer's
  plan, so a rows file built before a new writer rule must be refused, not written by position.
* **the acceptance follows the journal chain** - a phase-3 row superseded by a later journalled lane is
  reported as superseded, a broken chain is a deviation, and everything the per-row check caught is
  still caught.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "output" / "remediation" / "tools"
for path in (TOOLS, REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lanes  # noqa: E402
import make_holds  # noqa: E402
import review_all  # noqa: E402
import verify_writes as V  # noqa: E402
import write_dry_all  # noqa: E402
import write_gate  # noqa: E402

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


def test_an_unknown_lane_is_refused_rather_than_given_a_guessed_prefix() -> None:
    with pytest.raises(SystemExit, match="unknown lane"):
        lanes.lane("gapp")


def test_every_tool_defaults_to_the_mass_lane() -> None:
    """No `--lane` means what it meant before lanes existed."""
    assert write_dry_all.build_parser().parse_args([]).lane == "mass"
    assert review_all.build_parser().parse_args([]).lane == "mass"


# ── the write gate ───────────────────────────────────────────────────────────────────────────────


def _row(batch: str, key: str) -> dict:
    return {"batch_id": batch, "change_key": key, "column": "site_type", "site_id": SITE}


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


def test_the_dry_plan_driver_reads_only_batches_with_a_review(tmp_path: Path) -> None:
    for name, reviewed in (("gap-0001", True), ("gap-0002", False)):
        (tmp_path / name).mkdir()
        if reviewed:
            (tmp_path / name / "review.json").write_text("{}", encoding="utf-8")
    assert write_dry_all.batches_to_plan(tmp_path) == ["gap-0001"]


def test_a_writer_that_exited_zero_without_its_plan_file_is_damage(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="wrote no PLAN.jsonl"):
        write_dry_all._batch_lines(tmp_path / "PLAN.jsonl", "gap-0001")


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


# ── the hold list's pin ──────────────────────────────────────────────────────────────────────────


def test_the_hold_list_refuses_a_rows_file_whose_lines_moved() -> None:
    rows = [{"change_key": f"phase3:{n}"} for n in range(3)]
    with pytest.raises(SystemExit, match="would now name other rows"):
        make_holds.assert_pinned(rows)
    assert make_holds.keys_digest(rows) == make_holds.keys_digest(list(rows))
    assert make_holds.keys_digest(rows) != make_holds.keys_digest(rows[::-1])


# ── the acceptance follows the journal chain ────────────────────────────────────────────────────


def _planned(pk: str, column: str, old: str, new: str) -> dict:
    return {"pk": pk, "column": column, "old_value": old, "new_value": new, "site_name": pk[:8]}


def _link(id_: int, pk: str, column: str, old: str | None, new: str | None, stamp: str) -> V.Link:
    return V.Link(id=id_, table=V.TABLE, column=column, pk=pk, old=old, new=new, stamp=stamp)


PHASE3 = "phase3:batch-0002:chunk-0001"
UK = "2026-09-23_mechanical-uk-parts"


def _accept(
    planned: list[dict], lane: list[V.Link], others: list[V.Link], live: dict
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
    )


def test_a_write_that_holds_its_value_is_carried() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [],
        {("country", SITE): "United Kingdom"},
    )
    assert (result.carried, dict(result.superseded), result.deviations) == (1, {}, [])


def test_a_write_superseded_by_a_later_journalled_lane_is_reported_not_a_deviation() -> None:
    """The five phase-3 'United Kingdom' rows the Northern-Ireland lane re-spells."""
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "United Kingdom", "Northern Ireland", UK)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [later],
        {("country", SITE): "Northern Ireland"},
    )
    assert result.deviations == []
    assert result.carried == 0
    assert dict(result.superseded) == {UK: 1}


def test_a_broken_chain_is_a_deviation_even_when_the_live_value_matches_its_end() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "England", "Northern Ireland", UK)  # does not start at UK
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [later],
        {("country", SITE): "Northern Ireland"},
    )
    assert any(line.startswith("KETTE GERISSEN") for line in result.deviations)


def test_a_live_value_that_is_not_the_chains_last_value_is_a_deviation() -> None:
    write = _link(1, SITE, "country", "Ireland", "United Kingdom", PHASE3)
    later = _link(2, SITE, "country", "United Kingdom", "Northern Ireland", UK)
    result = _accept(
        [_planned(SITE, "country", "Ireland", "United Kingdom")],
        [write],
        [later],
        {("country", SITE): "United Kingdom"},  # the later lane's journal says otherwise
    )
    assert any(line.startswith("NICHT NEU") for line in result.deviations)


def test_a_planned_row_the_lane_did_not_write_must_still_hold_its_old_value() -> None:
    held = _planned(OTHER, "site_type", "Temple", "Ruin")
    untouched = _accept([held], [], [], {("site_type", OTHER): "Temple"})
    assert (untouched.untouched, untouched.deviations) == (1, [])
    silently = _accept([held], [], [], {("site_type", OTHER): "Ruin"})
    assert any(line.startswith("DOCH GEAENDERT") for line in silently.deviations)


def test_a_planned_row_another_lane_changed_is_moved_by_that_lane_and_checked() -> None:
    held = _planned(OTHER, "country", "Ireland", "United Kingdom")
    other = _link(5, OTHER, "country", "Ireland", "Northern Ireland", UK)
    moved = _accept([held], [], [other], {("country", OTHER): "Northern Ireland"})
    assert (dict(moved.moved), moved.deviations) == ({UK: 1}, [])
    foreign = _link(5, OTHER, "country", "Scotland", "Northern Ireland", UK)
    unrelated = _accept([held], [], [foreign], {("country", OTHER): "Northern Ireland"})
    assert any(line.startswith("FREMDE KETTE") for line in unrelated.deviations)


def test_a_lane_journal_row_outside_the_plan_is_a_deviation() -> None:
    write = _link(1, SITE, "site_type", "Temple", "Ruin", PHASE3)
    result = _accept([], [write], [], {("site_type", SITE): "Ruin"})
    assert any(line.startswith("AUSSERHALB") for line in result.deviations)


def test_a_planned_site_missing_from_the_database_is_a_deviation() -> None:
    held = _planned(OTHER, "site_type", "Temple", "Ruin")
    result = V.accept(planned=[held], lane_links=[], chains={}, live={}, present=set())
    assert any(line.startswith("FEHLT") for line in result.deviations)


def test_the_lane_query_leaves_out_reversals_but_the_chain_query_reads_every_stamp() -> None:
    lane_sql = V.lane_journal_sql("phase3:batch-%")
    assert "run_stamp LIKE 'phase3:batch-%'" in lane_sql and "'%-rollback'" in lane_sql
    chain_sql = V.chain_sql([SITE])
    assert "run_stamp" not in chain_sql.split("WHERE", 1)[1]
    assert f"'{SITE}'" in chain_sql and "ORDER BY id" in chain_sql


def test_the_database_reads_are_parsed_as_json_lines_and_damage_is_refused() -> None:
    rows = V.json_rows(json.dumps({"id": 1}) + "\n\n" + json.dumps({"id": 2}) + "\n")
    assert [row["id"] for row in rows] == [1, 2]
    with pytest.raises(SystemExit, match="not JSON"):
        V.json_rows("1|a|b\n")
