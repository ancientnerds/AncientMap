"""Lane WC write batches whose WC plan is lost: a recorded, versioned account of each, built from the
production journal, that the write gate names as **closed** instead of as a batch of a plan.

Why (2026-10-24): apply batch `p4wc-4325` - the 17 texts of the lane-WN pilot `wn-2026-10-06`,
written live on 2026-10-06 and accepted as step 12 - sits in the WC apply root, but the run it was
planned from lived only in the worktree `.claude/worktrees/db-finish`, removed between 2026-10-09
and 2026-10-17: its `WC4.jsonl`, `POPULATION.json` and `judge/RESULT.json` (and the handoffs
`wn-2026-10-06-w`, `-verify`) exist nowhere any more. `write_gate4.wc_batches` refuses an apply root
that holds a write batch of a plan not named, and that plan can no longer be named - so every WC plan
was refused. Re-creating the plan is not possible (its outcomes rest on the lost run) and moving the
batch aside would take its rows out of the lane plan the acceptance reads.

So the batch is **closed by record**: what the gate needs to know about it - that it is a written,
accepted batch, which rows it wrote and that those are the rows production journals - is
reconstructed from the production journal (`remediation_change_log`, read-only) and checked against
the batch's own `PLAN.jsonl`, `APPLIED.json` and its acceptance record, which survived in the apply
root. The record names itself as reconstructed, with its provenance (the journal read, the lost
files, who reconstructed it and why). The gate (`write_gate4.wc_batches`) accepts such a batch in the
apply root only while `verify` finds nothing: the batch files are the recorded bytes, the plan's rows
are the journal's (change key, column, test id, old and new value by sha256), the batch was accepted,
nothing stopped. It is never re-planned or written again; its `PLAN.jsonl` stays in the lane plan, so
the acceptance still judges its rows against the journal. Nothing is weakened: a batch that is
neither a named plan's nor closed by a record that holds is refused as before.

The 17 texts are MiniMax-judged (the writer and the verifiers were MiniMax Code agents, the journal's
`checker` is `model4.AI_SYSTEM`): owner decision D10 and master plan X6 re-check them with Claude, and
`wc/cli.py minimax-sites --closed <record>` puts them on that list. The old pilot no longer approves
any WN plan: a new, Claude-judged WN pilot is the first WN plan the gate names (`pilot_approval`).

    closed_wc_batches.py reconstruct --batch p4wc-4325 --lost-run wn-2026-10-06 \\
        --lost-where .claude/worktrees/db-finish/output/remediation/wc_runner/runs/wn-2026-10-06 \\
        --lost-file WC4.jsonl --lost-file POPULATION.json --lost-file judge/RESULT.json \\
        --lost-handoff output/remediation/handoff/wn-2026-10-06-w \\
        --by "<who>" --reason "<why>"      # reads production read-only, writes the record once
    closed_wc_batches.py verify [--apply-root DIR]   # every record against the apply root

Exit lines: `CLOSED_EXIT=0` done, `1` a record does not hold, `2` refused input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the paths, the reader and the database seam
from phase4 import model4 as M  # noqa: E402 - the disclosure strings
from phase4 import write4 as W4  # noqa: E402 - the group's files and prefixes

#: The versioned records, one per closed batch (`<batch>.closed.json`): hand-made accounts that no
#: run can regenerate, versioned with the plan of the final repair.
RECORDS = lanes.REMEDIATION / "final-2026-10-08" / "reconstructed"
RECORD_SUFFIX = ".closed.json"
VERSION = 1
KIND = "closed-wc-batch"
GROUP = W4.Group.WC
#: The acceptance records of the apply root (`write_gate4.ACCEPTED_DIR`; not imported: the gate
#: imports this module).
ACCEPTED_DIR = "ACCEPTED"
STOPPED_FILE = "STOPPED.json"
#: The first line of `journal_sql`: how the tests' fake psql recognises the read.
JOURNAL_READ = "-- a closed WC batch: its journal rows (read-only)"
#: What a record keeps of each journal row: enough to tie every planned row to the row production
#: journals, byte for byte through the sha256 of its values and its evidence.
ROW_KEYS = (
    "id", "applied_at", "run_stamp", "test_id", "table_name", "column_name", "row_pk",
    "change_key", "old_sha256", "new_sha256", "evidence_sha256", "ev_run", "ev_checker",
    "ev_marking", "ev_answered_by", "ev_verified_by", "ev_handoffs",
)  # fmt: skip


class ClosedBatchError(ValueError):
    """A record cannot be made or does not hold. Nothing is guessed."""


def sha256_text(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal_sql(run_stamp: str) -> str:
    """Read-only: every journal row of one write batch's stamp, with the sha256 of its values and
    evidence and the evidence's run, checker, marking and answering agents."""
    return (
        f"{JOURNAL_READ}\n"
        "SELECT to_jsonb(t)::text FROM (SELECT id, applied_at, run_stamp, test_id, table_name, "
        "column_name, row_pk, change_key, "
        "CASE WHEN old_value IS NULL THEN NULL "
        "ELSE encode(sha256(convert_to(old_value, 'UTF8')), 'hex') END AS old_sha256, "
        "CASE WHEN new_value IS NULL THEN NULL "
        "ELSE encode(sha256(convert_to(new_value, 'UTF8')), 'hex') END AS new_sha256, "
        "encode(sha256(convert_to(evidence::text, 'UTF8')), 'hex') AS evidence_sha256, "
        "evidence ->> 'run' AS ev_run, evidence ->> 'checker' AS ev_checker, "
        "evidence -> 'marking' ->> 'old' AS ev_marking, "
        "(SELECT jsonb_agg(DISTINCT a ->> 'answered_by') "
        "FROM jsonb_array_elements(evidence -> 'answers') a) AS ev_answered_by, "
        "(SELECT jsonb_agg(DISTINCT r ->> 'answered_by') "
        "FROM jsonb_array_elements(evidence -> 'verification' -> 'rounds') r) AS ev_verified_by, "
        "(SELECT jsonb_agg(DISTINCT a ->> 'handoff') "
        "FROM jsonb_array_elements(evidence -> 'answers') a) AS ev_handoffs "
        f"FROM remediation_change_log WHERE run_stamp = {lanes.sql_text(run_stamp)} ORDER BY id) t;\n"
    )


def _accepted_step(apply_root: pathlib.Path, batch_id: str) -> pathlib.Path:
    """The acceptance record (`ACCEPTED/step-NNNN.json`) whose step wrote `batch_id`: exactly one."""
    found = [
        path
        for path in sorted((apply_root / ACCEPTED_DIR).glob("step-*.json"))
        if batch_id in json.loads(path.read_text(encoding="utf-8"))["batches"]
    ]
    if len(found) != 1:
        raise ClosedBatchError(
            f"{apply_root}: {len(found)} acceptance record(s) name {batch_id}: a closed batch is a "
            "written step that was accepted once"
        )
    return found[0]


def _plan_rows(batch_dir: pathlib.Path) -> list[dict[str, Any]]:
    return lanes.read_jsonl(batch_dir / W4.PLAN_FILE)


def _row_problems(
    plan: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Where the batch's planned rows and the journal's rows of its stamp disagree: one journal row
    per planned row, the same change key, site, column and test id, and old and new value by
    sha256."""
    problems: list[str] = []
    by_key = {row["change_key"]: row for row in rows}
    if len(by_key) != len(rows):
        problems.append("the journal holds a change key twice under the batch's stamp")
    if sorted(by_key) != sorted(row["change_key"] for row in plan):
        problems.append(
            f"the journal's {len(rows)} change key(s) are not the plan's {len(plan)}: not the rows "
            "this batch wrote"
        )
        return problems
    for row in plan:
        entry = by_key[row["change_key"]]
        wanted = (
            row["site_id"],
            row["column"],
            row["test_id"],
            sha256_text(row["old_value"]),
            sha256_text(row["new_value"]),
        )
        found = (
            entry["row_pk"],
            entry["column_name"],
            entry["test_id"],
            entry["old_sha256"],
            entry["new_sha256"],
        )
        if wanted != found:
            problems.append(f"{row['change_key']}: the journal row is not the planned row")
    return problems


def reconstruct(
    batch_dir: pathlib.Path,
    journal: Sequence[Mapping[str, Any]],
    *,
    lost: Mapping[str, Any],
    by: str,
    reason: str,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="seconds"),
) -> dict[str, Any]:
    """The record of one closed batch, from its surviving batch files and the production journal of
    its stamp (`journal_sql`). Refused: a batch that is not an applied WC batch, a stopped one, one
    not accepted, a journal that is not exactly the batch's planned rows, an empty `by` or
    `reason`, and a `lost` account without its run and its files."""
    if not by.strip() or not reason.strip():
        raise ClosedBatchError("a reconstruction names who made it and why (--by, --reason)")
    if not lost.get("run") or not lost.get("files"):
        raise ClosedBatchError("a reconstruction names the lost run and the lost files")
    batch_id = batch_dir.name
    if re.fullmatch(rf"{W4.GROUP_PREFIX[GROUP]}-[0-9]{{4,}}", batch_id) is None:
        raise ClosedBatchError(f"{batch_dir}: {batch_id!r} is no WC write batch")
    applied_path = batch_dir / W4.APPLIED_FILE
    if not applied_path.exists():
        raise ClosedBatchError(f"{batch_dir}: no {W4.APPLIED_FILE}: only a written batch is closed")
    if (batch_dir / STOPPED_FILE).exists():
        raise ClosedBatchError(f"{batch_dir}: a stopped batch is read by a person, not closed")
    applied = json.loads(applied_path.read_text(encoding="utf-8"))
    if applied["group"] != GROUP.value or applied["batch_id"] != batch_id:
        raise ClosedBatchError(f"{applied_path}: not the WC batch {batch_id}")
    plan = _plan_rows(batch_dir)
    W4.validate_rows(GROUP, [W4.Row4.from_dict(row) for row in plan])
    rows = [{key: entry[key] for key in ROW_KEYS} for entry in journal]
    stamps = {row["run_stamp"] for row in rows}
    if stamps != {applied["run_stamp"]}:
        raise ClosedBatchError(
            f"the journal read names the stamps {sorted(stamps)}, the batch wrote "
            f"{applied['run_stamp']}"
        )
    problems = _row_problems(plan, rows)
    if problems:
        raise ClosedBatchError(f"{batch_id}: " + "; ".join(problems))
    accepted = _accepted_step(batch_dir.parent, batch_id)
    sites: dict[str, dict[str, Any]] = {}
    for row in plan:
        site = sites.setdefault(
            row["site_id"],
            {
                "site_id": row["site_id"],
                "name": row["site_name"],
                "run": row["evidence"]["run"],
                "marking_old": row["evidence"]["marking"]["old"],
                "checker": row["evidence"]["checker"],
                "description_sha256": None,
            },
        )
        if row["column"] == "description":
            site["description_sha256"] = sha256_text(row["new_value"])
    for entry in rows:
        site = sites[entry["row_pk"]]
        site["answered_by"] = sorted(entry["ev_answered_by"] or [])
        site["verified_by"] = sorted(entry["ev_verified_by"] or [])
        site["handoffs"] = sorted(entry["ev_handoffs"] or [])
    for site in sites.values():
        # `model4.ai_system_for` returns the combined string exactly when a MiniMax stamp answered
        site["minimax"] = site["checker"] == M.AI_SYSTEM
    return {
        "v": VERSION,
        "kind": KIND,
        "reconstructed": True,
        "batch_id": batch_id,
        "group": GROUP.value,
        "run_stamp": applied["run_stamp"],
        "write_round": applied["write_round"],
        "rows": len(plan),
        "sites": len(sites),
        "reconstructed_at": now(),
        "reconstructed_by": by,
        "reason": reason,
        "lost": dict(lost),
        "batch_files": {
            W4.PLAN_FILE: sha256_file(batch_dir / W4.PLAN_FILE),
            W4.APPLIED_FILE: sha256_file(applied_path),
        },
        "accepted": {"file": accepted.name, "sha256": sha256_file(accepted)},
        "journal": {
            "source": "remediation_change_log (production, read-only SELECT)",
            "read_sha256": hashlib.sha256(
                journal_sql(applied["run_stamp"]).encode("utf-8")
            ).hexdigest(),
            "rows": rows,
        },
        "site_list": sorted(sites.values(), key=lambda site: site["site_id"]),
    }


def record_path(root: pathlib.Path, batch_id: str) -> pathlib.Path:
    return root / f"{batch_id}{RECORD_SUFFIX}"


def write_record(root: pathlib.Path, record: Mapping[str, Any]) -> pathlib.Path:
    """The record, written once (UTF-8, LF, sorted keys)."""
    path = record_path(root, record["batch_id"])
    if path.exists():
        raise ClosedBatchError(f"{path} exists: a reconstruction is written once")
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Batch id -> its record, for every record under `root` (none: an empty mapping)."""
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob(f"*{RECORD_SUFFIX}")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("kind") != KIND or record.get("v") != VERSION:
            raise ClosedBatchError(f"{path}: not a closed-batch record of version {VERSION}")
        if path.name != f"{record['batch_id']}{RECORD_SUFFIX}":
            raise ClosedBatchError(f"{path}: named for another batch than {record['batch_id']}")
        records[record["batch_id"]] = record
    return records


def verify(record: Mapping[str, Any], apply_root: pathlib.Path) -> list[str]:
    """Why the closed batch of `record` is not what the record says in `apply_root`; empty = it
    is: its `PLAN.jsonl` and `APPLIED.json` are the recorded bytes, its plan's rows are the
    recorded journal's, it was accepted on the recorded acceptance and nothing stopped."""
    batch_dir = apply_root / record["batch_id"]
    if not batch_dir.is_dir():
        return [f"{batch_dir}: the closed batch is not in the apply root"]
    problems: list[str] = []
    for name, digest in record["batch_files"].items():
        path = batch_dir / name
        if not path.exists() or sha256_file(path) != digest:
            problems.append(f"{path}: not the bytes the record was reconstructed from")
    if (batch_dir / STOPPED_FILE).exists():
        problems.append(f"{batch_dir}: a {STOPPED_FILE} stands beside the closed batch")
    if problems:
        return problems
    problems.extend(_row_problems(_plan_rows(batch_dir), record["journal"]["rows"]))
    try:
        accepted = _accepted_step(apply_root, record["batch_id"])
    except ClosedBatchError as exc:
        return [*problems, str(exc)]
    if (accepted.name, sha256_file(accepted)) != (
        record["accepted"]["file"],
        record["accepted"]["sha256"],
    ):
        problems.append(f"{accepted}: not the acceptance the record names")
    return problems


def minimax_sites(record: Mapping[str, Any]) -> dict[str, str]:
    """Site id -> the lost run, for every site of the record whose text a MiniMax agent shaped:
    what `wc/cli.py minimax-sites --closed` adds to the D10 list."""
    return {site["site_id"]: site["run"] for site in record["site_list"] if site["minimax"]}


# ------------------------------------------------------------------------------------------ CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="closed-wc-batches", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("reconstruct", help="read the journal (read-only), write the record once")
    make.add_argument("--batch", required=True)
    make.add_argument("--lost-run", required=True)
    make.add_argument("--lost-where", required=True)
    make.add_argument("--lost-file", action="append", required=True, default=[])
    make.add_argument("--lost-handoff", action="append", default=[])
    make.add_argument("--by", required=True)
    make.add_argument("--reason", required=True)
    check = sub.add_parser("verify", help="every record against the apply root")
    for command in (make, check):
        command.add_argument(
            "--apply-root", type=pathlib.Path, default=lanes.lane("p4wc").apply_root
        )
        command.add_argument("--records", type=pathlib.Path, default=RECORDS)
        command.add_argument("--host", default=lanes.HOST)
    return parser


def _run(argv: list[str] | None, run: Callable[[str], str] | None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "reconstruct":
        batch_dir = args.apply_root / args.batch
        applied = json.loads((batch_dir / W4.APPLIED_FILE).read_text(encoding="utf-8"))
        sql = journal_sql(applied["run_stamp"])
        text = run(sql) if run is not None else lanes.psql(sql, host=args.host)
        record = reconstruct(
            batch_dir,
            lanes.json_rows(text),
            lost={
                "run": args.lost_run,
                "where": args.lost_where,
                "files": list(args.lost_file),
                "handoffs": list(args.lost_handoff),
            },
            by=args.by,
            reason=args.reason,
        )
        path = write_record(args.records, record)
        print(
            f"closed batch {record['batch_id']}: {record['rows']} row(s) at {record['sites']} "
            f"site(s), {sum(s['minimax'] for s in record['site_list'])} MiniMax-shaped; record "
            f"{path} (sha256 {sha256_file(path)})"
        )
        return 0
    records = load(args.records)
    failed = 0
    for batch_id, record in records.items():
        problems = verify(record, args.apply_root)
        print(f"{batch_id}: " + ("holds" if not problems else "; ".join(problems)))
        failed += bool(problems)
    print(f"{len(records)} record(s), {failed} that do not hold")
    return 1 if failed else 0


def main(argv: list[str] | None = None, *, run: Callable[[str], str] | None = None) -> int:
    try:
        code = _run(argv, run)
    except ClosedBatchError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        code = 2
    print(f"CLOSED_EXIT={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
