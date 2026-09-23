"""The Phase-4/5 write gate: plan a row group, rehearse it, write it one step of 100 sites at a time.

Design entry [6], production_write ("CHUNK = ONE STEP = 100 SITES", "Around each chunk") and work
item WB-D2. The writer is `scripts/remediation/phase4/write4.py`; this is the driver that reads a
phase-4 run, asks production the few read-only questions the plan depends on, renders every write
batch's statements, and runs them.

    write_gate4.py --group P4 --run pilot --open-lanes W,S                  # dry run: plan + render
    write_gate4.py --group P4 --run pilot --open-lanes W,S --rehearse       # APPLY ending in ROLLBACK
    write_gate4.py --group P4 --run pilot --open-lanes W,S --apply --step 100

**Dry run by default**: nothing is sent to production except the read-only questions a group needs
(L and P5: which sites carry a live Phase-4 provenance), and the report says so.

`--rehearse` runs each open batch's `REHEARSE.sql` (the exact write, ending in `ROLLBACK`) against
the live rows and proves afterwards that every row is still at its old value and the stamp journals
nothing.

`--apply` walks the open batches in plan order. Per batch: the pinned statements, a read-only
preflight (every row still holds its old value, the stamp journals nothing yet), the write, the
per-row read-back with the journal in both directions and the two sha256 invariants, and the inverse
proof (`ROLLBACK.sql` run as-is, ending in `ROLLBACK`). A batch that passes gets `APPLIED.json`; any
disagreement leaves `STOPPED.json` and ends the run with `WRITE_EXIT=1`, and a later run refuses a
stopped batch until a person has read it. **One step per invocation**: once `--step` sites are
written the gate stops with `WRITE_EXIT=0` and names the acceptance to run (`verify_writes4.py`,
0 deviations) before the next step is started - the owner's "after every hundred, a check, and only
then continue" as a sequence of commands, not a promise inside one.

A written batch keeps the plan it was written from: re-planning it to different rows is refused.
Which lanes may write (`--open-lanes`) is the pilot's verdict, and lanes T and R need the independent
audit's cleared list (`--audited`, one site id per line). The verifier is `phase4.verify4`
(`verify_site`, V1-V15), imported when group P4 is planned.

Every run prints its own `WRITE_EXIT=` line; that line is what is read.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths, the JSON-lines reader and the database seam
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import write_stage as W  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import write4 as W4  # noqa: E402

APPLIED_FILE = "APPLIED.json"
STOPPED_FILE = "STOPPED.json"
#: The Phase-3 refusal rule under which the reviewer-cleared text defects were set aside.
PHASE3_REPORT_ONLY = "report-only-field"


# ------------------------------------------------------------------------------------ reading
def batch_dirs(run_dir: pathlib.Path, wanted: Sequence[str]) -> list[pathlib.Path]:
    """The run's plan batches in plan order (`p4-NNNN`), or exactly the named ones."""
    if not run_dir.is_dir():
        raise SystemExit(f"{run_dir}: no such run directory")
    found = sorted(
        path for path in run_dir.iterdir() if path.is_dir() and (path / M.INPUT_FILE).exists()
    )
    if not wanted:
        return found
    by_name = {path.name: path for path in found}
    missing = [name for name in wanted if name not in by_name]
    if missing:
        raise SystemExit(f"{run_dir}: no batch {missing}")
    return [by_name[name] for name in wanted]


def read_audited(path: pathlib.Path | None) -> frozenset[str]:
    """The independent audit's cleared site ids (lanes T and R): one UUID per line."""
    if path is None:
        return frozenset()
    ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            uuid.UUID(text)
        except ValueError:
            raise SystemExit(f"{path}:{number}: {text!r} is not a site id") from None
        ids.add(text)
    return frozenset(ids)


def open_lanes(value: str) -> frozenset[M.Lane]:
    """`--open-lanes W,S`: the lanes whose pilot passed. Only lanes S1b can assign that publish."""
    chosen: set[M.Lane] = set()
    for part in value.split(","):
        name = part.strip()
        if not name:
            continue
        lane = M.Lane(name)
        if lane not in M.LANE_CHANGES:
            raise SystemExit(f"--open-lanes: lane {name} publishes nothing")
        chosen.add(lane)
    return frozenset(chosen)


def written_sql(site_ids: Sequence[str]) -> str:
    """Read-only: the lane and card digest of each named site's live provenance."""
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, "
        f"raw_data -> {W._sql_text(M.PROVENANCE_KEY)} ->> 'lane' AS lane, "
        f"raw_data -> {W._sql_text(M.PROVENANCE_KEY)} -> 'card' ->> 'text_sha256' AS card "
        f"FROM unified_sites WHERE id IN ({', '.join(f'{lanes.sql_text(s)}::uuid' for s in site_ids)})"
        ") t;\n"
    )


def written_sites(site_ids: Sequence[str], *, run: Any, window: int = 200) -> dict[str, str | None]:
    """Site id -> the live provenance's `card.text_sha256` (`None` without a card), for every named
    site whose `raw_data` carries a full (W/S/T/R) provenance. What production says, not a file."""
    full = {lane.value for lane in M.LANE_CHANGES}
    found: dict[str, str | None] = {}
    for start in range(0, len(site_ids), window):
        for row in lanes.json_rows(run(written_sql(site_ids[start : start + window]))):
            if row["lane"] in full:
                found[str(row["id"])] = row["card"]
    return found


def phase3_card_findings(
    refused: pathlib.Path, run_dir: pathlib.Path
) -> dict[str, list[dict[str, Any]]]:
    """The Phase-3 reviewer-cleared card defects (the 709), by site: the refusal record, the
    finder's answer and the reviewer's verdict - the evidence a card clear is journalled with."""
    findings: dict[str, list[dict[str, Any]]] = {}
    reviews: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for record in lanes.read_jsonl(refused):
        if record["rule"] != PHASE3_REPORT_ONLY or record["field"] != "card_description":
            continue
        batch, site = record["batch_id"], record["site_id"]
        answer = F.EvidenceStore(run_dir / batch / "answers").path_for(site, "card_description")
        if batch not in reviews:
            review = json.loads((run_dir / batch / "review.json").read_text(encoding="utf-8"))
            reviews[batch] = {(v["site_id"], v["field"]): v for v in review["verdicts"]}
        findings.setdefault(site, []).append(
            {
                "refusal": record,
                "finder_answer": answer.read_text(encoding="utf-8"),
                "reviewer": reviews[batch][(site, "card_description")],
            }
        )
    return findings


def _verifier() -> W4.Verifier:
    """`phase4.verify4.verify_site` (V1-V15), Track C's verifier. Imported here, when a P4 plan
    needs it, so the dry run of L and P5 does not depend on it."""
    from phase4 import verify4

    return verify4.verify_site


# ------------------------------------------------------------------------------------ planning
@dataclass
class Planned:
    """One write batch: where it lives, its plan, its chunk (or none), and whether it is done."""

    out: pathlib.Path
    plan: W4.WritePlan4
    chunk: W4.Chunk4 | None

    @property
    def applied(self) -> bool:
        return (self.out / APPLIED_FILE).exists()

    @property
    def stopped(self) -> bool:
        return (self.out / STOPPED_FILE).exists()


def plan_batch(
    batch: W4.BatchInputs,
    *,
    group: W4.Group,
    options: Mapping[str, Any],
) -> W4.WritePlan4:
    if group is W4.Group.P4:
        return W4.plan_p4(
            batch,
            open_lanes=options["open_lanes"],
            audited=options["audited"],
            verify=options["verify"],
            ledger=options["ledger"],
        )
    if group is W4.Group.L:
        return W4.plan_legacy(batch, written=options["written"])
    return W4.plan_cards(batch, written=options["written"], card_findings=options["card_findings"])


def render(apply_root: pathlib.Path, plan: W4.WritePlan4, *, write_round: int) -> Planned:
    """Render one write batch into `<apply root>/<batch>/`. A batch already applied keeps its plan:
    a re-plan to other rows is refused, never written over the record of what was written."""
    out = apply_root / plan.batch_id
    chunk = W4.chunk_for(plan, write_round=write_round)
    if (out / APPLIED_FILE).exists():
        stored = W4.read_plan(out, group=plan.group)
        if [row.change_key for row in stored] != [row.change_key for row in plan.rows]:
            raise SystemExit(
                f"{out}: this batch was written from another plan; a written batch keeps the plan "
                "it was written from (read its APPLIED.json and the journal before anything else)"
            )
        return Planned(out=out, plan=plan, chunk=chunk)
    W4.write_plan_files(out, plan, chunk)
    return Planned(out=out, plan=plan, chunk=chunk)


def _mark(out: pathlib.Path, name: str, payload: Mapping[str, Any]) -> None:
    (out / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ------------------------------------------------------------------------------------ running
def run_batches(
    planned: Sequence[Planned],
    *,
    rehearse: bool,
    step: int,
    runner: W.SqlRunner | None,
    host: str,
) -> int:
    """Rehearse every open batch, or write open batches until `step` sites are written. 0 = done
    (or the step is complete), 1 = stopped; a stop leaves `STOPPED.json` and writes nothing more."""
    stopped = [item.out.name for item in planned if item.stopped]
    if stopped:
        print(
            f"STOP: {len(stopped)} batch(es) stopped in an earlier run and were never marked "
            f"applied: {stopped[:5]}. Read their STOPPED.json and run verify_writes4.py first."
        )
        return 1
    written_sites = 0
    for item in planned:
        if item.chunk is None or item.applied:
            continue
        try:
            outcome = W4.apply_chunk(
                item.chunk, out=item.out, rehearse=rehearse, runner=runner, host=host
            )
        except W.WriteRefused as exc:
            if not rehearse:
                _mark(item.out, STOPPED_FILE, {"batch_id": item.out.name, "error": str(exc)})
            print(f"STOP at {item.out.name}: {exc}")
            return 1
        report = outcome.to_dict()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
        if not outcome.ok:
            if not rehearse:
                _mark(item.out, STOPPED_FILE, report)
            print(f"STOP at {item.out.name}: " + "; ".join(outcome.blocked))
            return 1
        if rehearse:
            continue
        _mark(item.out, APPLIED_FILE, report)
        written_sites += len(item.chunk.site_ids)
        if written_sites >= step:
            print(
                f"STEP COMPLETE: {written_sites} site(s) written. Run the acceptance now "
                "(verify_writes4.py, 0 deviations) before the next step."
            )
            return 0
    print("every open batch rehearsed" if rehearse else f"done: {written_sites} site(s) written")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="write-gate4")
    parser.add_argument("--group", required=True, choices=[group.value for group in W4.Group])
    parser.add_argument("--run", required=True, help="the phase-4 run directory's name")
    parser.add_argument("--run-root", default=None, help="override phase4_runner/runs")
    parser.add_argument("--batch", action="append", default=[], help="only these plan batches")
    parser.add_argument("--round", type=int, default=1, help="the write round (1 unless redone)")
    parser.add_argument("--apply-root", default=None, help="override the lane's apply root")
    parser.add_argument("--open-lanes", default="", help="P4: lanes whose pilot passed, e.g. W,S")
    parser.add_argument("--audited", default=None, help="P4: the audit's cleared ids (T and R)")
    parser.add_argument("--ledger", default=str(lanes.PHASE4_LEDGER))
    parser.add_argument("--phase3-refused", default=str(lanes.lane().refused))
    parser.add_argument("--phase3-run", default=str(lanes.lane().run_dir))
    parser.add_argument("--step", type=int, default=100, help="sites per step (--apply)")
    parser.add_argument("--host", default=lanes.HOST)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rehearse", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def _run(argv: list[str] | None, runner: W.SqlRunner | None) -> int:
    args = build_parser().parse_args(argv)
    group = W4.Group(args.group)
    lane = lanes.lane(W4.GROUP_PREFIX[group])
    run_dir = pathlib.Path(args.run_root or lane.run_dir) / args.run
    apply_root = pathlib.Path(args.apply_root) if args.apply_root else lane.apply_root
    if args.step < 1:
        raise SystemExit("--step: at least one site per step")
    batches = [W4.load_batch(path) for path in batch_dirs(run_dir, args.batch)]
    site_ids = [site.site_id for batch in batches for site in batch.sites]
    print(f"group {group.value} | run {run_dir} | apply root {apply_root} | {len(batches)} batches")

    options: dict[str, Any] = {}
    if group is W4.Group.P4:
        options["open_lanes"] = open_lanes(args.open_lanes)
        if not options["open_lanes"]:
            raise SystemExit("--open-lanes: P4 writes only lanes whose pilot passed; name them")
        options["audited"] = read_audited(pathlib.Path(args.audited) if args.audited else None)
        options["verify"] = _verifier()
        options["ledger"] = read_jsonl(pathlib.Path(args.ledger))
    else:
        live = written_sites(site_ids, run=lambda sql: W._exec(runner, sql, host=args.host))
        options["written"] = live
        print(f"live phase-4 provenance: {len(live)} of {len(site_ids)} planned sites (read-only)")
        if group is W4.Group.P5:
            options["card_findings"] = phase3_card_findings(
                pathlib.Path(args.phase3_refused), pathlib.Path(args.phase3_run)
            )

    planned = [
        render(apply_root, plan_batch(batch, group=group, options=options), write_round=args.round)
        for batch in batches
    ]
    rows = sum(len(item.plan.rows) for item in planned)
    refused: dict[str, int] = {}
    for item in planned:
        for rule, count in item.plan.refusals_by_rule().items():
            refused[rule] = refused.get(rule, 0) + count
    unclaimed = sum(len(item.plan.unclaimed) for item in planned)
    open_items = [item for item in planned if item.chunk is not None and not item.applied]
    print(
        f"rows planned: {rows} | refused by rule: {refused} | unclaimed (HUMAN_ONLY): {unclaimed} "
        f"| open batches: {len(open_items)} | "
        + (
            "REHEARSING"
            if args.rehearse
            else "WRITING"
            if args.apply
            else "dry run, nothing is sent"
        )
    )
    if not (args.rehearse or args.apply):
        return 0
    return run_batches(
        planned, rehearse=args.rehearse, step=args.step, runner=runner, host=args.host
    )


def main(argv: list[str] | None = None, *, runner: W.SqlRunner | None = None) -> int:
    return W4.exit_line("WRITE", lambda: _run(argv, runner))


if __name__ == "__main__":
    sys.exit(main())
