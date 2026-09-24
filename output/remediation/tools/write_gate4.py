"""The Phase-4/5 write gate: plan a row group, rehearse it, write it one step of 100 sites at a time.

Design entry [6], production_write ("CHUNK = ONE STEP = 100 SITES", "Around each chunk") and work
item WB-D2. The writer is `scripts/remediation/phase4/write4.py`; this is the driver that reads a
phase-4 run, asks production the few read-only questions the plan depends on, renders every write
batch's statements, and runs them.

    write_gate4.py --group P4 --run pilot --open-lanes W,S                  # dry run: plan + render
    write_gate4.py --group P4 --run pilot --open-lanes W,S --rehearse       # APPLY ending in ROLLBACK
    write_gate4.py --group P4 --run pilot --open-lanes W,S --apply --step 100
    write_gate4.py --group P4 --run pilot --accept accept-step-1.log         # after verify_writes4
    write_gate4.py --group P5 --run mass --close-reverted                   # after revert4 of it
    write_gate4.py --group P5 --run mass --apply --round 2                  # write it again

**Dry run by default**: nothing is sent to production except the read-only questions a group needs
(L and P5: which sites carry a live Phase-4 provenance; `--round 2` and up: whether the round
before is reverted), and the report says so.

`--rehearse` runs each open batch's `REHEARSE.sql` (the exact write, ending in `ROLLBACK`) against
the live rows and proves afterwards that every row is still at its old value and the stamp journals
nothing.

`--apply` walks the open batches in plan order. Per batch: the pinned statements, a read-only
preflight (every row still holds its old value, the stamp journals nothing yet), the write, the
per-row read-back with the journal in both directions and the two sha256 invariants, and the inverse
proof (`ROLLBACK.sql` run as-is, ending in `ROLLBACK`). A batch that passes gets `APPLIED.json`; any
disagreement leaves `STOPPED.json` and ends the run with `WRITE_EXIT=1`, and a later run refuses a
stopped batch until a person has read it. **One step per invocation**: a batch is written only while
it still fits into `--step` sites; then the gate stops with `WRITE_EXIT=0` and prints the acceptance
command to run (`verify_writes4.py --lane --plan --run`, 0 deviations).

**The next step needs that acceptance** - the owner's "after every hundred, a check, and only then
continue" as a precondition, not a promise. Every written batch is recorded in `STEP.json` (and the
lane's plan in `LANE_PLAN.jsonl`); while `STEP.json` exists, `--apply` writes nothing. `--accept
<file>` reads the saved output of `verify_writes4.py` and records `ACCEPTED/step-NNNN.json` only when
it ends in `ACCEPT_EXIT=0`, says `RESULT: 0 deviation(s)`, has one lane line of the step's lane
whose stamps cover the step's, read at least the rows written so far under those stamps (every
round, the reverted ones too: their rows stay in the journal), and accepted no earlier step
(`acceptance_problems`).

**Write rounds** (the chunk number of the stamp). A batch taken back by `revert4` is written again
as its next round: `--apply --round 2` re-opens a batch applied in round 1 only when production
proves, read-only, that every row round 1 wrote has its own reversal kept (`revert4.reversal_read`,
`prove_reverted`); round 1's `APPLIED.json` is then kept beside its statements in
`chunks/chunk-0001/` with that proof (`REVERTED.json`), and chunk-0002 is rendered and written. A
round the batch cannot take - round 3 over a live round 1, round 2 for a batch never written, round
1 again for a re-opened one - is refused with `WRITE_EXIT=1`, never skipped. A step that was
reverted before its acceptance can never be accepted (every link it wrote has a later one);
`--close-reverted` records it in `CLOSED/step-NNNN.json` on the same proof, and its batches are
frozen until then.

A written batch keeps the plan it was written from: re-planning it to different rows is refused.
Which lanes may write (`--open-lanes`) is the pilot's verdict, and lanes T and R need the independent
audit's cleared list (`--audited`, one site id per line). The verifier is `phase4.verify4`
(`verify_site`, V1-V15), imported when group P4 is planned.

**Every group plans under the owner's defect scope** (decision 2026-09-23, `phase4/scope4.py`):
`SCOPE4.json`, read only when its bytes hash to the pin in `scope4.SCOPE_SHA256`. A site outside it
is refused (`outside-defect-scope`, counted on the "refused by rule" line) in P4, L and P5 alike.
There is no flag to switch it off: it is the owner's standing decision, and a new scope is a new
pinned version, never an option of this tool.

Every run prints its own `WRITE_EXIT=` line; that line is what is read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths, the JSON-lines reader and the database seam
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import write_stage as W  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import revert4 as R  # noqa: E402 - the reversal read: what "reverted" means
from phase4 import scope4 as S  # noqa: E402 - the owner's defect scope
from phase4 import write4 as W4  # noqa: E402

APPLIED_FILE = "APPLIED.json"
STOPPED_FILE = "STOPPED.json"
#: A reverted round's proof, kept with its `APPLIED.json` beside its statements (`chunks/<label>/`).
REVERTED_FILE = "REVERTED.json"
#: One record per step closed by its reversal instead of accepted (`step-NNNN.json`).
CLOSED_DIR = "CLOSED"
#: The written step that awaits its acceptance, in the apply root: its batches, stamps and counts.
STEP_FILE = "STEP.json"
#: One record per accepted step (`step-NNNN.json`), with the acceptance output it was accepted on.
ACCEPTED_DIR = "ACCEPTED"
#: Every rendered write batch's plan rows, in batch order: the `--plan` the acceptance reads.
LANE_PLAN_FILE = "LANE_PLAN.jsonl"
#: The acceptance CLI (Track C, WB-C3) and the lines of its output `--accept` reads.
VERIFY_TOOL = "output/remediation/tools/verify_writes4.py"
ACCEPT_OK = "ACCEPT_EXIT=0"
ACCEPT_CLEAN = "RESULT: 0 deviation(s)"
_ACCEPT_LANE = re.compile(
    r"lane (?P<lane>\S+) \| stamps (?P<stamps>\S+) \| planned rows \d+ \| "
    r"lane journal rows (?P<journal>\d+) \|"
)
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


def _defect_scope() -> S.DefectScope:
    """The owner's defect scope: the pinned `SCOPE4.json` and no other. A file that is not the pin
    ends the run (`WRITE_EXIT=1`) before anything is planned."""
    try:
        return S.load_scope()
    except S.ScopeError as exc:
        raise SystemExit(str(exc)) from None


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


def render(
    apply_root: pathlib.Path,
    plan: W4.WritePlan4,
    *,
    write_round: int,
    frozen: frozenset[str],
    runner: W.SqlRunner | None,
    host: str,
) -> Planned:
    """Render one write batch into `<apply root>/<batch>/` for its write round `write_round`.

    A batch applied in this round keeps its plan: a re-plan to other rows is refused, never written
    over the record of what was written. A batch applied in the round before is re-opened only on
    production's word that that round is reverted (`prove_reverted`), and never while it belongs to
    the step that awaits its acceptance (`frozen`); its record is kept beside its statements. Any
    other round is refused: the rounds of a batch follow its reverted rounds one by one.
    """
    out = apply_root / plan.batch_id
    chunk = W4.chunk_for(plan, write_round=write_round)
    if (out / APPLIED_FILE).exists():
        record = _read(out / APPLIED_FILE)
        if record["write_round"] == write_round:
            stored = W4.read_plan(out, group=plan.group)
            if [row.change_key for row in stored] != [row.change_key for row in plan.rows]:
                raise SystemExit(
                    f"{out}: this batch was written from another plan; a written batch keeps the "
                    "plan it was written from (read its APPLIED.json and the journal before "
                    "anything else)"
                )
            return Planned(out=out, plan=plan, chunk=chunk)
        if record["write_round"] != write_round - 1:
            raise SystemExit(
                f"{out}: was written in round {record['write_round']}; --round {write_round} "
                f"re-writes a batch whose round {write_round - 1} is reverted"
            )
        if out.name in frozen:
            raise SystemExit(
                f"{out}: this batch belongs to the written step that awaits its acceptance; accept "
                "that step (--accept), or close it after its revert (--close-reverted), before "
                "the batch is written again"
            )
        archive_round(out, record, prove_reverted(record, runner=runner, host=host))
    elif chunk is not None and write_round != reverted_round(out) + 1:
        raise SystemExit(
            f"{out}: its next write is round {reverted_round(out) + 1}, not --round {write_round}"
        )
    W4.write_plan_files(out, plan, chunk)
    if chunk is None:
        drop_unwritten_statements(out, write_round=write_round)
    return Planned(out=out, plan=plan, chunk=chunk)


def drop_unwritten_statements(out: pathlib.Path, *, write_round: int) -> None:
    """A plan of the batch without a row: the statements an earlier plan rendered for this round
    are not this plan's, and beside an empty `PLAN.jsonl` they would still write the old rows by
    hand. They go - never a round's record (`APPLIED.json`, `REVERTED.json`) nor a stopped batch's
    statements, which are what was attempted."""
    directory = out / W4.CHUNKS_DIR / f"chunk-{write_round:04d}"
    kept = (directory / APPLIED_FILE, directory / REVERTED_FILE, out / STOPPED_FILE)
    if not directory.is_dir() or any(path.exists() for path in kept):
        return
    for name in (W4.APPLY_FILE, W4.REHEARSE_FILE, W4.ROLLBACK_FILE):
        (directory / name).unlink()
    directory.rmdir()


def _read(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mark(out: pathlib.Path, name: str, payload: Mapping[str, Any]) -> None:
    (out / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ---------------------------------------------------------------------------------- write rounds
def reverted_round(out: pathlib.Path) -> int:
    """The batch's last reverted write round, 0 when none: the rounds kept with a `REVERTED.json`."""
    return max(
        (_read(path)["write_round"] for path in out.glob(f"{W4.CHUNKS_DIR}/*/{REVERTED_FILE}")),
        default=0,
    )


def prove_reverted(
    record: Mapping[str, Any], *, runner: W.SqlRunner | None, host: str
) -> dict[str, Any]:
    """Read-only: production holds the reversal of every row the round of `record` (its
    `APPLIED.json`) wrote - as many journalled writes under its stamp as it wrote, each with its own
    reversal kept, by `revert4`'s own definition (`reversal_read`). The proof, or a refusal."""
    stamp = record["run_stamp"]
    matched, kept = R.reversal_counts(stamp, runner=runner, host=host)
    if matched != record["rows_written"] or kept != matched:
        raise SystemExit(
            f"{stamp}: round {record['write_round']} is not reverted in production - {matched} "
            f"journalled write(s) under its stamp, {record['rows_written']} written, {kept} with "
            f"their own reversal kept. Revert it first (revert4.py --stamp-like '{stamp}')."
        )
    return {
        "run_stamp": stamp,
        "write_round": record["write_round"],
        "rows_written": record["rows_written"],
        "journalled_writes": matched,
        "reversals_kept": kept,
    }


def archive_round(out: pathlib.Path, record: Mapping[str, Any], proof: Mapping[str, Any]) -> None:
    """Keep a reverted round's record beside its statements (`chunks/<label>/`): the proof first,
    then its `APPLIED.json` moved there. The batch is open for its next round."""
    directory = out / W4.CHUNKS_DIR / record["chunk"]
    _mark(directory, REVERTED_FILE, proof)
    (out / APPLIED_FILE).replace(directory / APPLIED_FILE)


def written_rounds(apply_root: pathlib.Path) -> list[dict[str, Any]]:
    """Every round this apply root wrote: each batch's live `APPLIED.json` and the one kept with
    each reverted round (a reverted round's rows stay in the journal, under its stamp)."""
    paths = [
        *apply_root.glob(f"*/{APPLIED_FILE}"),
        *apply_root.glob(f"*/{W4.CHUNKS_DIR}/*/{APPLIED_FILE}"),
    ]
    return [_read(path) for path in sorted(paths)]


def close_reverted_step(apply_root: pathlib.Path, *, runner: W.SqlRunner | None, host: str) -> int:
    """`--close-reverted`: close the pending step by its reversal instead of its acceptance.

    A step `revert4` took back before its acceptance can never be accepted - every link it wrote
    has a later one - and is not live any more. On production's word that every round it wrote is
    reverted (`prove_reverted`, each batch), the step is recorded in `CLOSED/step-NNNN.json` with the
    proofs, its batches are re-opened for their next round and `STEP.json` is removed. Nothing is
    recorded or re-opened while one of its rows is live. 0 = closed."""
    step = pending_step(apply_root)
    if step is None:
        raise SystemExit(f"{apply_root}: no written step awaits its acceptance")
    rounds = []
    for batch, stamp in zip(step["batches"], step["stamps"], strict=True):
        out = apply_root / batch
        record = _read(out / APPLIED_FILE)
        if record["run_stamp"] != stamp:
            raise SystemExit(f"{out}: APPLIED.json names {record['run_stamp']}, the step {stamp}")
        rounds.append((out, record, prove_reverted(record, runner=runner, host=host)))
    for out, record, proof in rounds:
        archive_round(out, record, proof)
    closed = apply_root / CLOSED_DIR
    closed.mkdir(exist_ok=True)
    number = len(list(closed.glob("step-*.json"))) + 1
    _mark(closed, f"step-{number:04d}.json", {**step, "proofs": [p for _, _, p in rounds]})
    (apply_root / STEP_FILE).unlink()
    print(
        f"CLOSED step {number} by its reversal: {step['sites']} site(s) in "
        f"{len(step['batches'])} batch(es); write them again with --apply --round <next round>"
    )
    return 0


# ------------------------------------------------------------------------------ the acceptance
def pending_step(apply_root: pathlib.Path) -> dict[str, Any] | None:
    """The written step that awaits its acceptance, or `None` when every written step is accepted."""
    path = apply_root / STEP_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_lane_plan(apply_root: pathlib.Path) -> pathlib.Path:
    """Every rendered write batch's `PLAN.jsonl`, in batch order, as one file: the plan the
    acceptance compares the lane's whole journal against (a journal row outside it is a deviation,
    a planned row not written yet is a later step)."""
    lines: list[str] = []
    for plan in sorted(apply_root.glob(f"*/{W4.PLAN_FILE}")):
        lines.extend(line for line in plan.read_text(encoding="utf-8").splitlines() if line)
    path = apply_root / LANE_PLAN_FILE
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    return path


def _record_step(apply_root: pathlib.Path, *, lane: str, written: Sequence[Planned]) -> None:
    """`STEP.json` for the batches this invocation wrote - rewritten after every batch, so a run that
    stops half-way still leaves the batches it did write awaiting their acceptance."""
    chunks = [item.chunk for item in written if item.chunk is not None]
    _mark(
        apply_root,
        STEP_FILE,
        {
            "lane": lane,
            "batches": [chunk.batch_id for chunk in chunks],
            "stamps": [chunk.stamp for chunk in chunks],
            "sites": sum(len(chunk.site_ids) for chunk in chunks),
            "rows": sum(len(chunk.rows) for chunk in chunks),
        },
    )
    write_lane_plan(apply_root)


def _accepted(apply_root: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((apply_root / ACCEPTED_DIR).glob("step-*.json"))
    ]


def like_matches(pattern: str, stamp: str) -> bool:
    """SQL `LIKE` (`%` any run, `_` one character, everything else literal) over one stamp."""
    regex = "".join(
        ".*" if char == "%" else "." if char == "_" else re.escape(char) for char in pattern
    )
    return re.fullmatch(regex, stamp, flags=re.DOTALL) is not None


def acceptance_problems(
    text: str, *, step: Mapping[str, Any], written: Sequence[Mapping[str, Any]], used: set[str]
) -> list[str]:
    """Why `text` (the output of one `verify_writes4.py` run) does not accept `step`; empty = it
    does. It must end in `ACCEPT_EXIT=0` with 0 deviations, be the step's own lane, match every stamp
    the step wrote, have read at least every row written so far under the stamps it read - every
    round in `written`, the reverted ones too (so it was run after this step, not before it, not
    even between a revert and the round written after it) - and not be an output an earlier step was
    accepted on."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    problems: list[str] = []
    if not lines or lines[-1] != ACCEPT_OK:
        problems.append(f"the output does not end in {ACCEPT_OK}")
    if ACCEPT_CLEAN not in lines:
        problems.append(f"the output does not say {ACCEPT_CLEAN!r}")
    heads = [found for line in lines if (found := _ACCEPT_LANE.match(line))]
    if len(heads) != 1:
        problems.append(f"the output has {len(heads)} lane line(s), not one")
        return problems
    head = heads[0]
    if head["lane"] != step["lane"]:
        problems.append(f"the output accepts lane {head['lane']}, the step is lane {step['lane']}")
    missed = [stamp for stamp in step["stamps"] if not like_matches(head["stamps"], stamp)]
    if missed:
        problems.append(f"the stamps {head['stamps']} do not cover {missed[:5]}")
    written_rows = sum(
        int(record["rows_written"])
        for record in written
        if like_matches(head["stamps"], record["run_stamp"])
    )
    if int(head["journal"]) < written_rows:
        problems.append(
            f"the output read {head['journal']} lane journal row(s), {written_rows} are written: "
            "it was run before this step"
        )
    if hashlib.sha256(text.encode("utf-8")).hexdigest() in used:
        problems.append("an earlier step was accepted on this very output")
    return problems


def accept_step(apply_root: pathlib.Path, output: pathlib.Path) -> int:
    """`--accept`: record the acceptance of the pending step, or refuse and say why. 0 = accepted."""
    step = pending_step(apply_root)
    if step is None:
        raise SystemExit(f"{apply_root}: no written step awaits its acceptance")
    text = output.read_text(encoding="utf-8")
    accepted = _accepted(apply_root)
    problems = acceptance_problems(
        text,
        step=step,
        written=written_rounds(apply_root),
        used={record["output_sha256"] for record in accepted},
    )
    if problems:
        for problem in problems:
            print(f"NOT ACCEPTED: {problem}")
        return 1
    number = len(accepted) + 1
    (apply_root / ACCEPTED_DIR).mkdir(exist_ok=True)
    _mark(
        apply_root / ACCEPTED_DIR,
        f"step-{number:04d}.json",
        {
            **step,
            "output": str(output),
            "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "output_lines": text.splitlines(),
        },
    )
    (apply_root / STEP_FILE).unlink()
    print(f"ACCEPTED step {number}: {step['sites']} site(s) in {len(step['batches'])} batch(es)")
    return 0


# ------------------------------------------------------------------------------------ running
def run_batches(
    planned: Sequence[Planned],
    *,
    rehearse: bool,
    step: int,
    runner: W.SqlRunner | None,
    host: str,
    apply_root: pathlib.Path,
    lane: str,
    run_dir: pathlib.Path,
) -> int:
    """Rehearse every open batch, or write open batches while the next one still fits into `step`
    sites. 0 = done (or the step is complete), 1 = stopped; a stop leaves `STOPPED.json` and
    writes nothing more.

    A write needs every earlier step accepted: while `STEP.json` names a written step without its
    acceptance (`--accept`), `--apply` writes nothing. Every batch written here is recorded in a
    fresh `STEP.json` before the next one starts.
    """
    stopped = [item.out.name for item in planned if item.stopped]
    if stopped:
        print(
            f"STOP: {len(stopped)} batch(es) stopped in an earlier run and were never marked "
            f"applied: {stopped[:5]}. Read their STOPPED.json and run verify_writes4.py first."
        )
        return 1
    if not rehearse:
        waiting = pending_step(apply_root)
        if waiting is not None:
            print(
                f"STOP: the step of {waiting['sites']} site(s) written before ({waiting['batches']}) "
                f"has no acceptance. Run {VERIFY_TOOL} on it and hand its output to --accept first "
                "(or, once revert4 took the step back, close it with --close-reverted)."
            )
            return 1
    written: list[Planned] = []
    written_sites = 0
    for item in planned:
        if item.chunk is None or item.applied:
            continue
        sites = len(item.chunk.site_ids)
        if not rehearse and written_sites + sites > step:
            if not written:
                print(f"STOP at {item.out.name}: {sites} sites in one batch; the step is {step}")
                return 1
            break
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
        written.append(item)
        written_sites += sites
        _record_step(apply_root, lane=lane, written=written)
    if rehearse:
        print("every open batch rehearsed")
        return 0
    print(
        f"STEP COMPLETE: {written_sites} site(s) written in {len(written)} batch(es). Accept it "
        f"before the next step: {VERIFY_TOOL} --lane {lane} --plan {apply_root / LANE_PLAN_FILE} "
        f"--run {run_dir} (0 deviations), then --accept <its output>."
        if written
        else "done: no open batch left to write"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="write-gate4")
    parser.add_argument("--group", required=True, choices=[group.value for group in W4.Group])
    parser.add_argument("--run", required=True, help="the phase-4 run directory's name")
    parser.add_argument("--run-root", default=None, help="override phase4_runner/runs")
    parser.add_argument("--batch", action="append", default=[], help="only these plan batches")
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="the write round: 1, or N to write again the batches whose round N-1 revert4 took back",
    )
    parser.add_argument("--apply-root", default=None, help="override the lane's apply root")
    parser.add_argument("--open-lanes", default="", help="P4: lanes whose pilot passed, e.g. W,S")
    parser.add_argument("--audited", default=None, help="P4: the audit's cleared ids (T and R)")
    parser.add_argument("--phase3-refused", default=str(lanes.lane().refused))
    parser.add_argument("--phase3-run", default=str(lanes.lane().run_dir))
    parser.add_argument("--step", type=int, default=100, help="sites per step (--apply)")
    parser.add_argument("--host", default=lanes.HOST)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rehearse", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument(
        "--accept", default=None, help="record the pending step's acceptance: verify_writes4 output"
    )
    mode.add_argument(
        "--close-reverted",
        action="store_true",
        help="close the pending step that revert4 took back (proven read-only), instead of --accept",
    )
    return parser


def unclaimed_by_reason(planned: Sequence[Planned]) -> dict[str, int]:
    """The sites lane L makes no claim for (HUMAN_ONLY D7), counted by reason - never one sum."""
    counts = Counter(entry.reason.value for item in planned for entry in item.plan.unclaimed)
    return dict(sorted(counts.items()))


def _run(argv: list[str] | None, runner: W.SqlRunner | None) -> int:
    args = build_parser().parse_args(argv)
    group = W4.Group(args.group)
    lane = lanes.lane(W4.GROUP_PREFIX[group])
    run_dir = pathlib.Path(args.run_root or lane.run_dir) / args.run
    apply_root = pathlib.Path(args.apply_root) if args.apply_root else lane.apply_root
    if args.step < 1:
        raise SystemExit("--step: at least one site per step")
    if args.accept:
        return accept_step(apply_root, pathlib.Path(args.accept))
    if args.close_reverted:
        return close_reverted_step(apply_root, runner=runner, host=args.host)
    batches = [W4.load_batch(path) for path in batch_dirs(run_dir, args.batch)]
    site_ids = [site.site_id for batch in batches for site in batch.sites]
    scope = _defect_scope()
    print(f"group {group.value} | run {run_dir} | apply root {apply_root} | {len(batches)} batches")
    print(
        f"defect scope: {scope.label}, {len(scope.sites)} sites (owner decision 2026-09-23): "
        f"{sum(site_id in scope for site_id in site_ids)} of the run's {len(site_ids)} sites"
    )

    options: dict[str, Any] = {"scope": scope}
    if group is W4.Group.P4:
        options["open_lanes"] = open_lanes(args.open_lanes)
        if not options["open_lanes"]:
            raise SystemExit("--open-lanes: P4 writes only lanes whose pilot passed; name them")
        options["audited"] = read_audited(pathlib.Path(args.audited) if args.audited else None)
        options["verify"] = _verifier()
        # The run's own ledger and no other: pilots reuse the batch ids p4-0001 .., so a ledger
        # shared across runs would put one pilot's calls into another's journal evidence.
        options["ledger"] = read_jsonl(run_dir / M.LEDGER_FILE)
    else:
        live = written_sites(site_ids, run=lambda sql: W._exec(runner, sql, host=args.host))
        options["written"] = live
        print(f"live phase-4 provenance: {len(live)} of {len(site_ids)} planned sites (read-only)")
        if group is W4.Group.P5:
            options["card_findings"] = phase3_card_findings(
                pathlib.Path(args.phase3_refused), pathlib.Path(args.phase3_run)
            )

    waiting = pending_step(apply_root)
    frozen = frozenset(waiting["batches"]) if waiting is not None else frozenset()
    planned = [
        render(
            apply_root,
            W4.plan_writes(batch, group=group, **options),
            write_round=args.round,
            frozen=frozen,
            runner=runner,
            host=args.host,
        )
        for batch in batches
    ]
    rows = sum(len(item.plan.rows) for item in planned)
    refused: dict[str, int] = {}
    for item in planned:
        for rule, count in item.plan.refusals_by_rule().items():
            refused[rule] = refused.get(rule, 0) + count
    open_items = [item for item in planned if item.chunk is not None and not item.applied]
    print(
        f"rows planned: {rows} | refused by rule: {refused} | unclaimed by reason (HUMAN_ONLY "
        f"D7): {unclaimed_by_reason(planned)} | open batches: {len(open_items)} | "
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
        planned,
        rehearse=args.rehearse,
        step=args.step,
        runner=runner,
        host=args.host,
        apply_root=apply_root,
        lane=lane.name,
        run_dir=run_dir,
    )


def main(argv: list[str] | None = None, *, runner: W.SqlRunner | None = None) -> int:
    return W4.exit_line("WRITE", lambda: _run(argv, runner))


if __name__ == "__main__":
    sys.exit(main())
