"""The Phase-3 CLI skeleton: `plan`, `prepare`, `status` - offline, deterministic, no model.

The runner does not exist yet (`output/remediation/AUDIT_LOG.md`: "build the Phase-3 runner,
which must emit the `defect` flag and the `true_but_no_correction` verdict ... and which should
run one instrumented batch of 15 sites with real token accounting before scaling to 1,813").
This file is piece 1: the shape of the run, its input and its accounting, with every line that
would touch the network or a model deliberately absent.

* `plan`   - assign the Phase-3 worklist to batches of K (default 15, brief decision 12) and
             write them as JSONL. Deterministic by construction: the worklist's own order is
             preserved, batch ids come from the ordinal, keys are sorted, the newline is
             pinned, and **no timestamp is written**. Two runs on the same input are
             byte-identical (proved in `tests/remediation/test_phase3_runner.py` and in
             `output/remediation/phase3_runner/PIECE1.md`).
* `prepare` - materialise one input file per batch under the run directory. No fetch, no model.
* `fetch`   - collect the evidence a batch's findings buy (`phase3/fetch_stage.py`). **Offline
             unless `--live` is given**: without it the command only lists the targets and the
             URLs, so what a batch would cost is reviewable before it costs a request.
* `status` - read the run directory and the ledger and report what is actually on disk.

Fail-closed: a worklist record whose shape is not the one the run needs raises, rather than
being skipped. A silently smaller plan is the failure this whole phase is paid to avoid.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Dual use: `python -m phase3.run` and `python scripts/remediation/phase3/run.py`. The package
# is not installed, so the parent directory must be importable first.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import ledger as L  # noqa: E402
from phase3.model import Stage  # noqa: E402

#: Ratified run shape (brief decision 12): 15 sites per run, two stages per batch.
DEFAULT_BATCH_SIZE = 15

REPO = Path(__file__).resolve().parents[3]
DEFAULT_WORKLIST = REPO / "output" / "remediation" / "phase3_worklist" / "WORKLIST.jsonl"
DEFAULT_RUN_DIR = REPO / "output" / "remediation" / "phase3_runner" / "runs"
DEFAULT_PLAN = REPO / "output" / "remediation" / "phase3_runner" / "PLAN.jsonl"
DEFAULT_LEDGER = REPO / "output" / "remediation" / "phase3_runner" / "LEDGER.jsonl"


class InputError(ValueError):
    """The input is not the shape the run needs. Raised, never worked around."""


@dataclass(frozen=True)
class Batch:
    """One agent run: the sites one stage processes, in worklist order."""

    batch_id: str
    ordinal: int
    sites: tuple[dict[str, Any], ...]

    def to_json(self) -> str:
        payload = {"batch_id": self.batch_id, "ordinal": self.ordinal, "sites": list(self.sites)}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file. Every line must be a JSON object; nothing is skipped."""
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            text = raw.strip()
            if not text:
                raise InputError(f"{path}:{lineno}: empty line")
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}:{lineno}: not JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise InputError(f"{path}:{lineno}: expected a JSON object, got {type(record)}")
            records.append(record)
    return records


def select_phase3(records: list[dict[str, Any]], origin: Path) -> list[dict[str, Any]]:
    """The Phase-3 records, in file order (the worklist is already worst-first).

    A record without the `phase3` flag or without a `site_id` is not "not Phase 3" - it is a
    record this runner cannot place, so it raises.
    """
    selected: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if "phase3" not in record:
            raise InputError(f"{origin}: record {index} carries no `phase3` flag")
        if "site_id" not in record or not record["site_id"]:
            raise InputError(f"{origin}: record {index} carries no `site_id`")
        if record["phase3"] is True:
            selected.append(record)
    return selected


def assign_batches(records: list[dict[str, Any]], size: int) -> list[Batch]:
    """Chunk the worklist, preserving its order. `size` must be a positive integer."""
    if size < 1:
        raise InputError(f"batch size must be >= 1, got {size}")
    return [
        Batch(
            batch_id=f"batch-{ordinal:04d}",
            ordinal=ordinal,
            sites=tuple(records[start : start + size]),
        )
        for ordinal, start in enumerate(range(0, len(records), size), start=1)
    ]


def write_batches(path: Path, batches: list[Batch]) -> None:
    """Write the plan: one JSON object per batch, sorted keys, LF newlines, no timestamp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(batch.to_json() + "\n" for batch in batches)
    path.write_text(body, encoding="utf-8", newline="\n")


def cmd_plan(args: argparse.Namespace) -> int:
    records = read_jsonl(Path(args.worklist))
    selected = select_phase3(records, Path(args.worklist))
    batches = assign_batches(selected, args.batch_size)
    write_batches(Path(args.out), batches)
    print(
        json.dumps(
            {
                "batches": len(batches),
                "batch_size": args.batch_size,
                "out": str(args.out),
                "sites": len(selected),
                "worklist": str(args.worklist),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """Materialise the batch inputs under the run directory. No network, no model call."""
    plan = Path(args.plan)
    batches = read_jsonl(plan)
    run_dir = Path(args.run_dir)
    wanted = set(args.batch_id or [])
    written: list[str] = []
    seen: set[str] = set()
    for line_no, batch in enumerate(batches, start=1):
        batch_id = batch.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise InputError(f"{plan}:{line_no}: batch without a batch_id")
        if batch_id in seen:
            raise InputError(f"{plan}:{line_no}: duplicate batch_id {batch_id}")
        seen.add(batch_id)
        if wanted and batch_id not in wanted:
            continue
        target = run_dir / batch_id / "input.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(batch_id)
    if wanted and wanted != set(written):
        raise InputError(f"asked for batches that are not in the plan: {sorted(wanted - seen)}")
    print(
        json.dumps(
            {"batches": len(written), "run_dir": str(run_dir), "written": written},
            indent=1,
            sort_keys=True,
        )
    )
    return 0


def _run_dir_state(run_dir: Path) -> dict[str, Any]:
    if not run_dir.exists():
        raise FileNotFoundError(f"no run directory at {run_dir}: nothing has been prepared")
    prepared: list[str] = []
    results: list[str] = []
    for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if (child / "input.json").exists():
            prepared.append(child.name)
        if (child / "result.json").exists():
            results.append(child.name)
    return {"batches_with_input": prepared, "batches_with_result": results, "run_dir": str(run_dir)}


def cmd_status(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = _run_dir_state(Path(args.run_dir))
    if args.plan:
        plan = Path(args.plan)
        batches = read_jsonl(plan)
        payload["planned_batches"] = len(batches)
        payload["planned_sites"] = sum(len(b.get("sites") or []) for b in batches)
        payload["plan"] = str(plan)
    if args.ledger:
        ledger = Path(args.ledger)
        summary = L.summarise(ledger)
        payload["ledger"] = {
            "lines": summary.lines,
            "path": str(ledger),
            "stages": {stage: totals.as_dict() for stage, totals in summary.by_stage.items()},
            "total": summary.total.as_dict(),
        }
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def _single_batch(path: Path, batch_id: str) -> dict[str, Any]:
    """The one batch prepared at `path`. Not zero, not two: a missing input is not an empty run."""
    records = read_jsonl(path)
    if len(records) != 1:
        raise InputError(f"{path}: expected exactly one batch, found {len(records)}")
    if records[0].get("batch_id") != batch_id:
        raise InputError(f"{path}: holds batch {records[0].get('batch_id')!r}, not {batch_id!r}")
    return records[0]


def cmd_fetch(args: argparse.Namespace) -> int:
    """Collect evidence for one prepared batch. Nothing happens unless `--live` is passed."""
    # Imported here because `fetch_stage` imports this module's `InputError`.
    from phase3 import fetch_stage as F

    run_dir = Path(args.run_dir)
    batch_id = args.batch_id
    batch = _single_batch(run_dir / batch_id / "input.json", batch_id)
    stage = Stage(args.stage)

    if not args.live:
        targets = [t for site in batch["sites"] for t in F.targets_for_site(site)]
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "live": False,
                    "run_dir": str(run_dir),
                    "sites": len(batch["sites"]),
                    "stage": stage.value,
                    "targets": [
                        {
                            "feature": t.feature,
                            "label": t.label,
                            "reason": t.reason,
                            "url": t.url,
                        }
                        for t in targets
                    ],
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0

    fetcher = F.HttpFetcher(timeout=args.timeout)
    try:
        report = F.collect_batch(
            batch=batch,
            fetcher=fetcher,
            store=F.EvidenceStore(run_dir / batch_id / "evidence"),
            ledger=L.Ledger(Path(args.ledger)),
            stage=stage,
        )
    except F.TransportFailure as exc:
        # Fail-closed, and loud: no response means no measurement, so the batch stops here and
        # says so. Evidence already on disk stays, so a re-run resumes instead of re-paying.
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "error": str(exc),
                    "live": True,
                    "run_dir": str(run_dir),
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 2
    finally:
        fetcher.close()

    F.write_report(run_dir / batch_id / "fetch.json", report)
    payload = json.loads(report.to_json())
    payload.update({"ledger": str(args.ledger), "live": True, "run_dir": str(run_dir)})
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase3-run",
        description="Phase-3 runner: plan, prepare and report a two-stage audit run",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="assign the Phase-3 worklist to batches (offline)")
    plan.add_argument("--worklist", default=str(DEFAULT_WORKLIST))
    plan.add_argument("--out", default=str(DEFAULT_PLAN))
    plan.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    plan.set_defaults(func=cmd_plan)

    prepare = sub.add_parser("prepare", help="write one input file per batch (offline)")
    prepare.add_argument("--plan", default=str(DEFAULT_PLAN))
    prepare.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    prepare.add_argument("--batch-id", action="append", default=None)
    prepare.set_defaults(func=cmd_prepare)

    fetch = sub.add_parser(
        "fetch", help="collect evidence for one prepared batch (offline unless --live)"
    )
    fetch.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    fetch.add_argument("--batch-id", required=True)
    fetch.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    fetch.add_argument(
        "--stage",
        choices=[s.value for s in Stage],
        default=Stage.FINDER.value,
        help="which stage the ledger line belongs to (the reviewer reuses this command)",
    )
    fetch.add_argument(
        "--live",
        action="store_true",
        help="actually open sockets; without it the command only lists the targets",
    )
    fetch.add_argument("--timeout", type=float, default=40.0)
    fetch.set_defaults(func=cmd_fetch)

    status = sub.add_parser("status", help="report what is on disk, plus the ledger (offline)")
    status.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    status.add_argument("--plan", default=str(DEFAULT_PLAN))
    status.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
