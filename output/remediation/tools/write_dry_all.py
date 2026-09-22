"""Plan every batch of the mass run without applying one row, and collect the rows into one file.

The writer's unit is a batch directory (`--batch-dir` is required), and Martin's rule is to write in
steps of a hundred with a check after each, so the chunking has to happen above the CLI: this driver
runs the dry plan for every batch that has a review report, concatenates the planned rows into
`ALL_ROWS.jsonl` and the refusals into `ALL_REFUSED.jsonl`, and prints one line per batch so a silent
zero for a whole batch is visible as a run of zeros instead of being averaged away.

Nothing here touches the database: the dry path reads the batch's own `input.json`, `review.json` and
answer files, and `--apply` is not passed.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(r"C:/PythonProjects/AncientMap")
RUN = ROOT / "output/remediation/phase3_runner/runs/mass"
OUT = ROOT / "output/remediation/logs/_write_dry"
WRITER = ROOT / "scripts/remediation/phase3/write_stage.py"
PYTHON = ROOT / ".venv/Scripts/python.exe"
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


def plan_batch(batch: str) -> tuple[str, int, dict | None, str]:
    out = OUT / batch
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(PYTHON), str(WRITER), "--batch-dir", str(RUN / batch), "--out", str(out)],
        env={**os.environ, "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT / 'scripts' / 'remediation'}"},
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


def _read_lines(path: pathlib.Path, batch: str) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: not readable JSON: {exc}") from None
        row["batch_id"] = batch
        rows.append(row)
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sorted(
        entry.name for entry in RUN.iterdir() if entry.is_dir() and (entry / "review.json").exists()
    )
    print(f"Batches mit Pruefbericht: {len(todo)}", flush=True)

    rows: list[dict] = []
    refused: list[dict] = []
    by_rule: collections.Counter[str] = collections.Counter()
    failed: list[str] = []
    planned = sites = 0
    zeros = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for batch, code, report, problem in pool.map(plan_batch, todo):
            if report is None:
                failed.append(f"{batch}: exit={code} {problem}")
                print(f"{batch} FEHLER exit={code} {problem}", flush=True)
                continue
            planned += report.get("rows_planned") or 0
            sites += report.get("sites_planned") or 0
            by_rule.update(report.get("refused_by_rule") or {})
            rows.extend(_read_lines(OUT / batch / "PLAN.jsonl", batch))
            refused.extend(_read_lines(OUT / batch / "REFUSED.jsonl", batch))
            if not report.get("rows_planned"):
                zeros += 1
            print(
                f"{batch} zeilen={report.get('rows_planned')} sites={report.get('sites_planned')} "
                f"abgelehnt={sum((report.get('refused_by_rule') or {}).values())}",
                flush=True,
            )

    _dump(OUT / "ALL_ROWS.jsonl", rows)
    _dump(OUT / "ALL_REFUSED.jsonl", refused)
    print(f"\nzeilen geplant: {planned} | sites: {sites} | batches ohne Zeile: {zeros}")
    print(f"abgelehnt nach Regel: {dict(by_rule.most_common())}")
    print(f"fehlgeschlagen: {failed}")
    return 1 if failed else 0


def _dump(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
