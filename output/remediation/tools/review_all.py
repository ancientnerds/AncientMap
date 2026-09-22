"""Run the reviewer stage over every finder batch that has no review yet.

The finder's $10.63 is already on disk in 160 batch directories, and the reviewer's unit is the
finding, not the site: the dry run over all of them says 2,165 calls and 9,835 unreviewable records
with the finder's own reason. This driver spends exactly that, four batches at a time, and is
resumable for free - `review.json` is the marker, so a rerun only picks up what is missing.

The money guard is a ledger sum, read between batches rather than after the run: the reviewer writes
its own stage into the ledger (`run.py judge --stage reviewer`), so the sum is the reviewer's own bill
and not the run's history. A ledger line that does not parse is counted and reported, never silently
treated as a zero cost - a guard that under-counts is a guard that lets the run past its ceiling.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(r"C:/PythonProjects/AncientMap")
RUN = ROOT / "output/remediation/phase3_runner/runs/mass"
LEDGER = ROOT / "output/remediation/phase3_runner/LEDGER.jsonl"
LOGS = ROOT / "output/remediation/logs/review"
PYTHON = ROOT / ".venv/Scripts/python.exe"

#: The ceiling for this pass. The reviewer's own calls are cheaper than the finder's (~16 k characters
#: of prompt instead of ~55 k), so ~2,165 calls should land near $4; 8 is the stop, not the estimate.
CAP_USD = 8.0
WORKERS = 4
TIMEOUT_S = 1800


def reviewer_spend() -> tuple[float, int]:
    """(cost of the reviewer's ledger rows, rows the sum had to leave out).

    Two kinds of row are left out and both are counted, never silently read as zero cost: a line that
    is not JSON (expected while four writers append to one file) and a `cost_usd` literal too large
    for a float. A guard that under-counts is a guard that lets the run past its ceiling, so the
    number is always reported next to the number of rows it does not include.
    """
    cost = 0.0
    unreadable = 0
    if not LEDGER.exists():
        return 0.0, 0
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            unreadable += 1
            continue
        if row.get("stage") != "reviewer":
            continue
        value = row.get("cost_usd")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        try:
            cost += float(value)
        except OverflowError:
            unreadable += 1
    return cost, unreadable


def run_one(batch: str) -> tuple[str, int]:
    out = LOGS / f"{batch}.json"
    log = LOGS / f"{batch}.log"
    proc = subprocess.run(
        [
            str(PYTHON),
            str(ROOT / "scripts/remediation/phase3/run.py"),
            "judge",
            "--run-dir",
            str(RUN),
            "--batch-id",
            batch,
            "--ledger",
            str(LEDGER),
            "--stage",
            "reviewer",
            "--live",
            "--timeout",
            "240",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
    )
    out.write_text(proc.stdout, encoding="utf-8")
    log.write_text(proc.stderr, encoding="utf-8")
    return batch, proc.returncode


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    todo = sorted(
        pathlib.Path(entry).name
        for entry in RUN.iterdir()
        if entry.is_dir() and not (entry / "review.json").exists()
    )
    done = sum(1 for entry in RUN.iterdir() if (entry / "review.json").exists())
    print(f"Batches mit Pruefbericht: {done} | offen: {len(todo)}", flush=True)
    if not todo:
        return 0

    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for number, (batch, code) in enumerate(pool.map(run_one, todo), start=1):
            cost, unreadable = reviewer_spend()
            print(
                f"{number}/{len(todo)} {batch} exit={code} prueferkosten={cost:.4f} "
                f"ohne_summe={unreadable}",
                flush=True,
            )
            if code != 0:
                failed.append(batch)
            if cost > CAP_USD:
                print(
                    f"STOP: {cost:.4f} ueber der Grenze {CAP_USD}; kein weiterer Batch", flush=True
                )
                break

    cost, unreadable = reviewer_spend()
    print(f"fertig | fehlgeschlagen: {failed} | prueferkosten={cost:.4f} | ohne_summe={unreadable}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
