"""A lane-WC write batch whose WC plan is lost, closed by a versioned record from the production
journal (2026-10-24: `p4wc-4325`, the WN pilot of the removed worktree `db-finish`).

`output/remediation/tools/closed_wc_batches.py` (reconstruct, verify, load, `minimax_sites`) and its
use in `write_gate4.wc_batches`: the gate refuses an apply root holding a batch of a plan it is not
told (as before), and accepts it only as closed - by a record that still holds against the batch
files, the journal rows and the acceptance. The fake psql is `phase4_write_fixtures.FakeDb`; the
journal read of a reconstruction is answered from its journal with the sha256 the real SELECT
computes. Also the real record of `p4wc-4325`, against the journal rows it pins.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import closed_wc_batches as CB  # noqa: E402
import lanes  # noqa: E402
import write_gate4 as G  # noqa: E402

from tests.remediation import phase4_write_fixtures as PFX  # noqa: E402
from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M  # noqa: E402
from tests.remediation.test_phase4_wc_write import (  # noqa: E402
    _accept_step,
    _answers,
    _db,
    _rows,
)
from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401 - the autouse fixture

NEW_SITE = "0e000000-0000-4000-8000-0000000000e1"


def _sha(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode("utf-8")).hexdigest()


def _journal_answer(db: PFX.FakeDb, apply_root: Path):
    """The fake production's answer to `journal_sql`: the journal rows of the stamp, shaped as the
    SELECT shapes them (the evidence is the lane plan's, as `test_phase4_wc_write._production`)."""
    evidence = {row["change_key"]: row["evidence"] for row in _lane_rows(apply_root)}

    def run(sql: str) -> str:
        assert sql.startswith(CB.JOURNAL_READ)
        stamp = sql.split("WHERE run_stamp = '")[1].split("'")[0]
        lines = []
        for entry in db.journal:
            if entry["run_stamp"] != stamp:
                continue
            found = evidence[entry["change_key"]]
            lines.append(
                json.dumps(
                    {
                        "id": entry["id"],
                        "applied_at": "2026-10-06T17:59:16+00:00",
                        "run_stamp": entry["run_stamp"],
                        "test_id": entry["test_id"],
                        "table_name": entry["table_name"],
                        "column_name": entry["column_name"],
                        "row_pk": entry["row_pk"],
                        "change_key": entry["change_key"],
                        "old_sha256": _sha(entry["old_value"]),
                        "new_sha256": _sha(entry["new_value"]),
                        "evidence_sha256": _sha(json.dumps(found, sort_keys=True)),
                        "ev_run": found["run"],
                        "ev_checker": found["checker"],
                        "ev_marking": found["marking"]["old"],
                        "ev_answered_by": sorted({a["answered_by"] for a in found["answers"]}),
                        "ev_verified_by": sorted(
                            {r["answered_by"] for r in found["verification"]["rounds"]}
                        ),
                        "ev_handoffs": sorted({a["handoff"] for a in found["answers"]}),
                    }
                )
            )
        return "\n".join(lines) + "\n"

    return run


def _lane_rows(apply_root: Path) -> list[dict[str, Any]]:
    return [
        row
        for plan in sorted(apply_root.glob(f"*/{W4.PLAN_FILE}"))
        for row in lanes.read_jsonl(plan)
    ]


def _written_and_lost(tmp_path, capsys, monkeypatch) -> tuple[PFX.FakeDb, Path, Path]:
    """A pilot plan written and accepted (batch p4wc-4001), then its run deleted: the plan is
    lost. Returns the database, the apply root and a second pilot's plan (another site)."""
    run, plan = FX.build_run(tmp_path / "lost", _rows(), _answers(), name="wc-lost")
    new_row = FX.row(NEW_SITE, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A), name="Tarxien E")
    db = PFX.FakeDb(
        {
            row["id"]: PFX.Site(description=row["description"], raw_data=row["raw_data"])
            for row in [*_rows(), new_row]
        }
    )
    apply_root = tmp_path / "apply"
    args = ["--group", "WC", "--wc-plan", str(plan), "--apply-root", str(apply_root)]
    assert G.main([*args, "--apply"], runner=db) == 0
    _accept_step(tmp_path, capsys, monkeypatch, db)
    for path in sorted(run.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    run.rmdir()
    second = FX.build_run(
        tmp_path / "next",
        [new_row],
        {NEW_SITE: FX.answer(NEW_SITE, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.drop(3)])},
        name="wc-next",
        first_batch=4002,
    )[1]
    return db, apply_root, second


def _reconstruct(db: PFX.FakeDb, apply_root: Path, records: Path, batch: str = "p4wc-4001") -> int:
    return CB.main(
        [
            "reconstruct", "--batch", batch, "--apply-root", str(apply_root),
            "--records", str(records), "--lost-run", "wc-lost", "--lost-where", "runs/wc-lost",
            "--lost-file", "WC4.jsonl", "--lost-file", "POPULATION.json", "--by", "test",
            "--reason", "the run directory was deleted",
        ],
        run=_journal_answer(db, apply_root),
    )  # fmt: skip


def _gate(apply_root: Path, plan: Path, records: Path, *extra: str) -> list[str]:
    return ["--group", "WC", "--wc-plan", str(plan), "--apply-root", str(apply_root),
            "--closed-batches", str(records), *extra]  # fmt: skip


def test_a_lost_plans_batch_blocks_the_gate_until_a_record_closes_it(
    tmp_path, capsys, monkeypatch
) -> None:
    db, apply_root, second = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    capsys.readouterr()
    assert G.main(_gate(apply_root, second, records), runner=db) == 1
    assert "['p4wc-4001']" in capsys.readouterr().err  # as before: not named, nothing planned
    assert _reconstruct(db, apply_root, records) == 0
    assert "closed batch p4wc-4001: 7 row(s) at 4 site(s)" in capsys.readouterr().out
    record = json.loads((records / "p4wc-4001.closed.json").read_text(encoding="utf-8"))
    assert record["reconstructed"] is True and record["lost"]["run"] == "wc-lost"
    assert [row["change_key"] for row in record["journal"]["rows"]] == [
        entry["change_key"] for entry in db.journal
    ]
    assert G.main(_gate(apply_root, second, records), runner=db) == 0
    out = capsys.readouterr().out
    assert "closed batch p4wc-4001: written and accepted, its WC plan lost" in out
    assert "never planned again" in out and "1 batches" in out
    lane_plan = lanes.read_jsonl(apply_root / "p4wc-4001" / W4.PLAN_FILE)
    assert G.main([*_gate(apply_root, second, records), "--apply"], runner=db) == 0
    assert db.sites[NEW_SITE].description != FX.TEXT_A  # the next plan is written
    assert lanes.read_jsonl(apply_root / "p4wc-4001" / W4.PLAN_FILE) == lane_plan
    written = lanes.read_jsonl(apply_root / G.LANE_PLAN_FILE)
    assert {row["change_key"] for row in lane_plan} <= {row["change_key"] for row in written}


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (lambda root: (root / "p4wc-4001" / W4.PLAN_FILE).write_text("", encoding="utf-8"),
         "not the bytes the record was reconstructed from"),
        (lambda root: (root / "p4wc-4001" / G.STOPPED_FILE).write_text("{}", encoding="utf-8"),
         "STOPPED.json stands beside the closed batch"),
        (lambda root: [p.unlink() for p in (root / G.ACCEPTED_DIR).glob("*.json")],
         "0 acceptance record(s) name p4wc-4001"),
    ],
)  # fmt: skip
def test_a_record_that_no_longer_holds_stops_the_gate(
    tmp_path, capsys, monkeypatch, break_it, message
) -> None:
    db, apply_root, second = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    assert _reconstruct(db, apply_root, records) == 0
    break_it(apply_root)
    capsys.readouterr()
    assert G.main(_gate(apply_root, second, records), runner=db) == 1
    err = capsys.readouterr().err
    assert "closed batch p4wc-4001: the record does not hold" in err and message in err


def test_a_record_whose_journal_rows_are_not_the_plans_does_not_hold(
    tmp_path, capsys, monkeypatch
) -> None:
    db, apply_root, _ = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    assert _reconstruct(db, apply_root, records) == 0
    path = records / "p4wc-4001.closed.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["journal"]["rows"][0]["new_sha256"] = "0" * 64
    assert any("is not the planned row" in p for p in CB.verify(record, apply_root))
    record["journal"]["rows"] = record["journal"]["rows"][1:]
    assert any("not the rows this batch wrote" in p for p in CB.verify(record, apply_root))


def test_a_reconstruction_is_refused_when_the_journal_is_not_the_batch(
    tmp_path, capsys, monkeypatch
) -> None:
    db, apply_root, _ = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    db.journal[0]["new_value"] = "tampered"
    capsys.readouterr()
    assert _reconstruct(db, apply_root, records) == 2
    assert "the journal row is not the planned row" in capsys.readouterr().err
    assert not records.exists()
    db.journal[0]["new_value"] = None
    with pytest.raises(CB.ClosedBatchError, match="who made it and why"):
        CB.reconstruct(apply_root / "p4wc-4001", [], lost={"run": "r", "files": ["x"]}, by=" ",
                       reason="r")  # fmt: skip
    with pytest.raises(CB.ClosedBatchError, match="no APPLIED.json"):
        CB.reconstruct(apply_root / "p4wc-4999", [], lost={"run": "r", "files": ["x"]}, by="b",
                       reason="r")  # fmt: skip


def test_a_closed_batch_a_named_plan_plans_again_is_refused(tmp_path, capsys, monkeypatch) -> None:
    db, apply_root, _ = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    assert _reconstruct(db, apply_root, records) == 0
    again = FX.build_run(tmp_path / "again", _rows(), _answers(), name="wc-again")[1]
    capsys.readouterr()
    assert G.main(_gate(apply_root, again, records), runner=db) == 1
    assert "closed by record" in capsys.readouterr().err


def test_a_record_is_written_once_and_names_its_minimax_shaped_sites(
    tmp_path, capsys, monkeypatch
) -> None:
    db, apply_root, _ = _written_and_lost(tmp_path, capsys, monkeypatch)
    records = tmp_path / "records"
    assert _reconstruct(db, apply_root, records) == 0
    assert _reconstruct(db, apply_root, records) == 2
    assert "is written once" in capsys.readouterr().err
    (record,) = CB.load(records).values()
    assert CB.minimax_sites(record) == {}  # the fixtures' answers are Claude's
    record["site_list"][0]["checker"] = M.AI_SYSTEM
    record["site_list"][0]["minimax"] = True
    assert CB.minimax_sites(record) == {record["site_list"][0]["site_id"]: "wc-lost"}
    (records / "p4wc-4002.closed.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(CB.ClosedBatchError, match="named for another batch"):
        CB.load(records)


def test_a_text_whose_checker_names_minimax_is_named_for_the_d10_recheck(
    tmp_path, capsys, monkeypatch
) -> None:
    """The record derives `minimax` from the journal evidence's checker: `model4.ai_system_for`
    names the combined disclosure (`model4.AI_SYSTEM`) exactly when a MiniMax stamp answered."""
    db, apply_root, _ = _written_and_lost(tmp_path, capsys, monkeypatch)
    plan = apply_root / "p4wc-4001" / W4.PLAN_FILE
    rows = lanes.read_jsonl(plan)
    for row in rows:
        if row["site_id"] == FX.SITE_A:
            row["evidence"] = {**row["evidence"], "checker": M.AI_SYSTEM}
    lanes.write_jsonl(plan, rows)
    records = tmp_path / "records"
    assert _reconstruct(db, apply_root, records) == 0
    (record,) = CB.load(records).values()
    assert CB.minimax_sites(record) == {FX.SITE_A: "wc-lost"}


# ------------------------------------------------------------------------------ the real record
REAL = CB.RECORDS / "p4wc-4325.closed.json"


def test_the_record_of_p4wc_4325_closes_the_lost_wn_pilot_and_names_its_17_minimax_texts() -> None:
    """The versioned record (reconstructed 2026-10-24 from the production journal, read-only): 34
    rows at 17 sites under `phase4wc:p4wc-4325:chunk-0001`, the lost run `wn-2026-10-06`, every text
    lane N's and MiniMax-shaped (`model4.AI_SYSTEM`), so all 17 go to the D10 re-check."""
    record = json.loads(REAL.read_text(encoding="utf-8"))
    assert (record["batch_id"], record["run_stamp"], record["rows"], record["sites"]) == (
        "p4wc-4325", "phase4wc:p4wc-4325:chunk-0001", 34, 17
    )  # fmt: skip
    assert record["reconstructed"] is True and record["lost"]["run"] == "wn-2026-10-06"
    assert "db-finish" in record["lost"]["where"]
    rows = record["journal"]["rows"]
    assert len(rows) == 34 and {row["run_stamp"] for row in rows} == {record["run_stamp"]}
    assert len({row["change_key"] for row in rows}) == 34
    assert {row["test_id"] for row in rows} == {W4.TEST_WC_DESCRIPTION, W4.TEST_WC_RAW_DATA}
    assert {site["marking_old"] for site in record["site_list"]} == {"none"}
    assert {site["run"] for site in record["site_list"]} == {"wn-2026-10-06"}
    assert len(CB.minimax_sites(record)) == 17
    assert (
        record["journal"]["read_sha256"]
        == hashlib.sha256(CB.journal_sql(record["run_stamp"]).encode("utf-8")).hexdigest()
    )


def test_the_record_of_p4wc_4325_holds_against_the_apply_root_where_it_is_present() -> None:
    """Where the gitignored apply root is present (the main checkout), the record holds; elsewhere
    (a worktree, CI) there is nothing to hold it against."""
    root = REPO / "output" / "remediation" / "logs" / "_write_apply_p4wc"
    if not (root / "p4wc-4325").is_dir():
        pytest.skip(f"the gitignored WC apply root is not in this checkout ({root})")
    assert CB.verify(json.loads(REAL.read_text(encoding="utf-8")), root) == []
