"""Run the reviewer stage over every finder batch of a run that has no review yet.

The finder's $10.63 is already on disk in 160 batch directories, and the reviewer's unit is the
finding, not the site: the dry run over all of them says 2,165 calls and 9,835 unreviewable records
with the finder's own reason. This driver spends exactly that, four batches at a time, and is
resumable for free - `review.json` is the marker, so a rerun only picks up what is missing.

The money guard is a ledger sum, read between batches rather than after the run: the reviewer writes
its own stage into the ledger (`run.py judge --stage reviewer`), so the sum is the reviewer's own bill.
A ledger line that does not parse is counted and reported, never silently treated as a zero cost - a
guard that under-counts is a guard that lets the run past its ceiling.

**The ceiling is this invocation's spend, not the ledger's history** (2026-09-22). The ledger is one
file for every run, and it already carries the mass run's $4.65 of reviewer calls; a ceiling compared
with the whole sum would stop a second lane (the gap run) after $3.35 of an $8 budget and read the
first lane's bill as its own. The sum is therefore taken once before the first batch and the guard
compares the difference - the same correction `mass_run.py` needed for its own ceiling.

**A STOP stops.** Until 2026-09-22 the loop printed `STOP` and broke out of `pool.map` - which had
already queued every batch, and the pool's shutdown then ran them all: the ceiling was a message, not a
stop (a test with a fake batch measures it: 10 of 10 batches ran after a STOP at the third). Batches
are now handed to the pool at most `--workers` at a time, the ceiling is read after each one finishes,
and after a STOP only the ones already running finish; the ones never started are named.

Which run it reviews is the lane's (`lanes.py`): the default is the mass run and `logs/review/`, as
it always was; `--lane gap` reviews `runs/gap` into `logs/review_gap/`.

    ./.venv/Scripts/python.exe output/remediation/tools/review_all.py --lane gap
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths

#: The ceiling for one pass. The reviewer's own calls are cheaper than the finder's (~16 k characters
#: of prompt instead of ~55 k), so ~2,165 calls should land near $4; 8 is the stop, not the estimate.
CAP_USD = 8.0
WORKERS = 4
TIMEOUT_S = 1800


def reviewer_spend(ledger: pathlib.Path) -> tuple[float, int]:
    """(cost of the reviewer's ledger rows, rows the sum had to leave out).

    Two kinds of row are left out and both are counted, never silently read as zero cost: a line that
    is not JSON (expected while four writers append to one file) and a `cost_usd` literal too large
    for a float. A guard that under-counts is a guard that lets the run past its ceiling, so the
    number is always reported next to the number of rows it does not include.
    """
    cost = 0.0
    unreadable = 0
    if not ledger.exists():
        return 0.0, 0
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
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


def run_one(
    batch: str, *, run_dir: pathlib.Path, ledger: pathlib.Path, log_dir: pathlib.Path
) -> tuple[str, int]:
    out = log_dir / f"{batch}.json"
    log = log_dir / f"{batch}.log"
    proc = subprocess.run(
        [
            sys.executable,
            str(lanes.RUNNER),
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            batch,
            "--ledger",
            str(ledger),
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


def batches_to_review(run_dir: pathlib.Path) -> tuple[list[str], int]:
    """(batches without a `review.json`, batches that already have one), for one run directory."""
    if not run_dir.is_dir():
        raise SystemExit(f"{run_dir}: no such run directory")
    entries = [entry for entry in run_dir.iterdir() if entry.is_dir()]
    todo = sorted(entry.name for entry in entries if not (entry / "review.json").exists())
    return todo, len(entries) - len(todo)


def over_cap(spent_now: float, baseline: float, cap: float) -> bool:
    """True once this invocation's own reviewer spend passes the ceiling."""
    return spent_now - baseline > cap


def review_batches(
    todo: list[str],
    *,
    run: Callable[[str], tuple[str, int]],
    spend: Callable[[], tuple[float, int]],
    cap: float,
    workers: int,
) -> tuple[list[str], list[str]]:
    """Review `todo`, stopping between batches once this pass's spend is over `cap`.

    Returns (failed batches, batches never started). At most `workers` batches are ever handed to the
    pool, and the next one only after the ceiling was read: a queue handed over whole cannot be
    stopped, only watched.
    """
    baseline, _ = spend()
    print(
        f"reviewer spend in the ledger before this pass: {baseline:.4f} (the ceiling counts from here)"
    )
    failed: list[str] = []
    queue = list(todo)
    pending: dict[Future[tuple[str, int]], str] = {}
    number = 0
    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue or pending:
            while queue and not stopped and len(pending) < workers:
                batch = queue.pop(0)
                pending[pool.submit(run, batch)] = batch
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                batch = pending.pop(future)
                _, code = future.result()
                number += 1
                cost, unreadable = spend()
                print(
                    f"{number}/{len(todo)} {batch} exit={code} "
                    f"reviewer_usd={cost - baseline:.4f} unreadable={unreadable}",
                    flush=True,
                )
                if code != 0:
                    failed.append(batch)
                if not stopped and over_cap(cost, baseline, cap):
                    stopped = True
                    print(
                        f"STOP: {cost - baseline:.4f} over the ceiling {cap}; no further "
                        f"batch, {len(pending)} still running finish",
                        flush=True,
                    )
    return failed, queue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review-all")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    parser.add_argument("--run-dir", default=None, help="override the lane's run directory")
    parser.add_argument("--log-dir", default=None, help="override the lane's reviewer log dir")
    parser.add_argument("--ledger", default=str(lanes.LEDGER))
    parser.add_argument("--cap-usd", type=float, default=CAP_USD)
    parser.add_argument("--workers", type=int, default=WORKERS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = lanes.lane(args.lane)
    run_dir = pathlib.Path(args.run_dir) if args.run_dir else paths.run_dir
    log_dir = pathlib.Path(args.log_dir) if args.log_dir else paths.review_logs
    ledger = pathlib.Path(args.ledger)
    log_dir.mkdir(parents=True, exist_ok=True)
    todo, done = batches_to_review(run_dir)
    print(f"run: {run_dir} | batches with a review: {done} | open: {len(todo)}", flush=True)
    if not todo:
        return 0

    def one(batch: str) -> tuple[str, int]:
        return run_one(batch, run_dir=run_dir, ledger=ledger, log_dir=log_dir)

    failed, not_reached = review_batches(
        todo,
        run=one,
        spend=lambda: reviewer_spend(ledger),
        cap=args.cap_usd,
        workers=args.workers,
    )
    remaining, _ = batches_to_review(run_dir)
    print(
        f"done | failed: {failed} | never started: {len(not_reached)} "
        f"| without review.json: {len(remaining)}"
    )
    return 1 if failed or remaining else 0


if __name__ == "__main__":
    sys.exit(main())
