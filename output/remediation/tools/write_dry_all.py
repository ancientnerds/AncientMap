"""Plan every batch of a run without applying one row, and collect the rows into one file.

The writer's unit is a batch directory (`--batch-dir` is required), and Martin's rule is to write in
steps of a hundred with a check after each, so the chunking has to happen above the CLI: this driver
runs the dry plan for every batch that has a review report, concatenates the planned rows into
`ALL_ROWS.jsonl` and the refusals into `ALL_REFUSED.jsonl`, and prints one line per batch so a silent
zero for a whole batch is visible as a run of zeros instead of being averaged away.

Nothing here touches the database: the dry path reads the batch's own `input.json`, `review.json`,
answer files, evidence files and `fetch.json`, and `--apply` is not passed.

Which run it plans is the lane's (`lanes.py`): the default is the mass run and `_write_dry/`, as it
always was; `--lane gap` plans `runs/gap` into `_write_dry_gap/`. `--run-dir` and `--out` override the
lane's two paths - for a measurement that must read one tree and write into another.

    ./.venv/Scripts/python.exe output/remediation/logs/write_dry_all.py
    ./.venv/Scripts/python.exe output/remediation/logs/write_dry_all.py --lane gap
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths and the one JSON-lines reader

WORKERS = 4
TIMEOUT_S = 900


def _report_from(stdout: str, batch: str) -> dict:
    """The JSON object the CLI printed, or a named error - never an empty dict read as "no rows"."""
    start = stdout.find("{")
    if start < 0:
        raise ValueError(f"{batch}: the writer printed no JSON object")
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{batch}: the writer's output is not readable JSON: {exc}") from None


def writer_env() -> dict[str, str]:
    """The writer imports `phase3` and `pipeline`, so both roots go on the child's own path."""
    return {
        **os.environ,
        "PYTHONPATH": f"{lanes.REPO}{os.pathsep}{lanes.REPO / 'scripts' / 'remediation'}",
    }


def plan_batch(
    batch: str, *, run_dir: pathlib.Path, out_root: pathlib.Path
) -> tuple[str, int, dict | None, str]:
    out = out_root / batch
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(lanes.WRITER), "--batch-dir", str(run_dir / batch), "--out", str(out)],
        env=writer_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
    )
    (out / "stdout.json").write_text(proc.stdout, encoding="utf-8")
    (out / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    report = None
    problem = ""
    if proc.returncode == 0:
        try:
            report = _report_from(proc.stdout, batch)
        except ValueError as exc:
            problem = str(exc)
    else:
        problem = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no stderr"
    return batch, proc.returncode, report, problem


def _batch_lines(path: pathlib.Path, batch: str) -> list[dict]:
    """A batch's PLAN.jsonl or REFUSED.jsonl, each record tagged with its batch.

    The writer writes both files for every batch it plans, an empty one included, so a missing file
    after a zero exit is damage, not "nothing planned".
    """
    if not path.exists():
        raise SystemExit(f"{batch}: the writer exited 0 and wrote no {path.name}")
    rows = lanes.read_jsonl(path)
    for row in rows:
        row["batch_id"] = batch
    return rows


def batches_to_plan(run_dir: pathlib.Path) -> list[str]:
    """Every batch directory of the run that carries a reviewer report, in name order."""
    if not run_dir.is_dir():
        raise SystemExit(f"{run_dir}: no such run directory")
    return sorted(
        entry.name
        for entry in run_dir.iterdir()
        if entry.is_dir() and (entry / "review.json").exists()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="write-dry-all")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    parser.add_argument("--run-dir", default=None, help="override the lane's run directory")
    parser.add_argument("--out", default=None, help="override the lane's dry-plan root")
    parser.add_argument("--workers", type=int, default=WORKERS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = lanes.lane(args.lane)
    run_dir = pathlib.Path(args.run_dir) if args.run_dir else paths.run_dir
    out_root = pathlib.Path(args.out) if args.out else paths.dry_root
    out_root.mkdir(parents=True, exist_ok=True)
    todo = batches_to_plan(run_dir)
    print(f"Lauf: {run_dir} -> {out_root}", flush=True)
    print(f"Batches mit Pruefbericht: {len(todo)}", flush=True)

    rows: list[dict] = []
    refused: list[dict] = []
    by_rule: collections.Counter[str] = collections.Counter()
    failed: list[str] = []
    planned = sites = 0
    zeros = 0

    def plan(batch: str) -> tuple[str, int, dict | None, str]:
        return plan_batch(batch, run_dir=run_dir, out_root=out_root)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for batch, code, report, problem in pool.map(plan, todo):
            if report is None:
                failed.append(f"{batch}: exit={code} {problem}")
                print(f"{batch} FEHLER exit={code} {problem}", flush=True)
                continue
            planned += report.get("rows_planned") or 0
            sites += report.get("sites_planned") or 0
            by_rule.update(report.get("refused_by_rule") or {})
            rows.extend(_batch_lines(out_root / batch / "PLAN.jsonl", batch))
            refused.extend(_batch_lines(out_root / batch / "REFUSED.jsonl", batch))
            if not report.get("rows_planned"):
                zeros += 1
            print(
                f"{batch} zeilen={report.get('rows_planned')} sites={report.get('sites_planned')} "
                f"abgelehnt={sum((report.get('refused_by_rule') or {}).values())}",
                flush=True,
            )

    lanes.write_jsonl(out_root / "ALL_ROWS.jsonl", rows)
    lanes.write_jsonl(out_root / "ALL_REFUSED.jsonl", refused)
    print(f"\nzeilen geplant: {planned} | sites: {sites} | batches ohne Zeile: {zeros}")
    print(f"abgelehnt nach Regel: {dict(by_rule.most_common())}")
    print(f"fehlgeschlagen: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
