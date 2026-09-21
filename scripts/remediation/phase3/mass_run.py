"""Piece 7 of the runner: walk a plan and drive every batch through prepare, fetch and judge.

A **script**, not a subagent lane, and that is a measured decision rather than a preference: the
30-minute ceiling binds lanes, not `bg_run` scripts, and two lanes this session were killed at that
ceiling while the workflow receipt reported work they had not done. A script writing to files it owns
cannot lose its evidence that way.

What it is careful about - every one of these has a test and a mutation behind it:

* **Resumable by construction.** `fetch` and `judge` both skip what is already on disk (the evidence
  file is the record; a re-judged answer comes back `wrote=False`), so a re-run pays only for what is
  missing. A batch counts as done when its artefacts parse *and* every answer it recorded is on disk:
  a half-written `model.json` is not evidence, and the batch goes back through `judge`.
* **A budget checked between batches**, in calls and in provider-reported dollars, both read from the
  ledger. Reaching a ceiling stops the run between batches and names what it did not reach. With
  `--jobs N` up to `N` batches may already be in flight at that moment, which is stated here rather
  than discovered later.
* **A circuit breaker**: N consecutive batch failures stop the run instead of burning 300 batches
  against a broken assumption.
* **A progress file a human can read while the run is going**, rewritten atomically (temp file plus
  replace), never only at the end.
* **One writer per tree**: the phase-3 sources are hashed at the start and compared before every
  batch. `fetch` and `judge` are separate processes, so an edit mid-run would make two batches execute
  two versions of the code - a hazard this session has already produced once.
* **Dry run by default**, and the dry run writes **no ledger line**. The test asserts on the ledger,
  never on "nothing was raised".
* **No database and no writes.** This piece produces findings; piece 6 turns confirmed findings into
  guarded writes, and keeping the two apart is what makes findings safe to produce in bulk.

Usage:

    # what would happen - buys nothing
    ./.venv/Scripts/python.exe scripts/remediation/phase3/mass_run.py --jobs 4

    # for real, with ceilings
    ./.venv/Scripts/python.exe scripts/remediation/phase3/mass_run.py --live --jobs 4 \
        --max-calls 25020 --max-usd 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[3]

# Dual use: `python -m phase3.mass_run` and `python scripts/remediation/phase3/mass_run.py`. Same
# shim as `run.py`, because the package is not installed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402

DEFAULT_PLAN = REPO / "output" / "remediation" / "phase3_runner" / "PLAN.jsonl"
DEFAULT_RUN_DIR = REPO / "output" / "remediation" / "phase3_runner" / "runs" / "mass1"
DEFAULT_LEDGER = REPO / "output" / "remediation" / "phase3_runner" / "LEDGER.jsonl"
DEFAULT_LOG_DIR = REPO / "output" / "remediation" / "logs" / "massrun"
RUNNER = REPO / "scripts" / "remediation" / "phase3" / "run.py"
PACKAGE = REPO / "scripts" / "remediation" / "phase3"

#: One batch holds 15 sites and the discover pass asks five questions per site.
DEFAULT_JOBS = 4
DEFAULT_FAILURES_BEFORE_STOP = 3
DEFAULT_STAGE_TIMEOUT = 5400.0
FIELDS_PER_SITE = 5
#: The measured cost of a discover call (round 6, `model.json` of `runs/gold6`). A projection, not a
#: ceiling: the ceilings are read from the ledger's provider-reported numbers.
MEASURED_COST_PER_CALL = 0.000825
STAGES = ("prepare", "fetch", "judge")
DONE, PARTIAL, BROKEN, ABSENT = "done", "partial", "broken", "absent"


class PlanError(ValueError):
    """The plan is not a plan: refusing beats walking half of it."""


class LedgerDamage(ValueError):
    """The ledger has an unparsable line *inside* it: a charge may have gone unrecorded."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def python_executable() -> Path:
    """The project interpreter, or this one when there is no venv to point at."""
    for candidate in (
        REPO / ".venv" / "Scripts" / "python.exe",
        REPO / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return Path(sys.executable)


@dataclass(frozen=True)
class PlannedBatch:
    """One line of the plan, as `snapshot_plan` writes it: `{batch_id, ordinal, sites}`."""

    batch_id: str
    ordinal: int
    sites: int

    @property
    def expected_calls(self) -> int:
        return self.sites * FIELDS_PER_SITE


def read_plan(path: Path) -> list[PlannedBatch]:
    """The whole plan, or nothing: a plan that cannot be read in full is refused, not walked."""
    if not path.exists():
        raise PlanError(f"{path}: no plan; run `run.py plan --from-snapshot` first")
    batches: list[PlannedBatch] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PlanError(f"{path}:{number}: {exc}") from None
        try:
            batch_id = str(record["batch_id"])
            ordinal = int(record["ordinal"])
        except (KeyError, TypeError, ValueError) as exc:
            # Loud either way; this spelling says *which line* of which file, and a plan is input.
            raise PlanError(
                f"{path}:{number}: a plan line without a batch id and an ordinal: {exc}"
            ) from None
        sites = record.get("sites")
        if not isinstance(sites, list) or not sites:
            raise PlanError(f"{path}:{number}: a batch with no sites is not a batch")
        batches.append(PlannedBatch(batch_id=batch_id, ordinal=ordinal, sites=len(sites)))
    if not batches:
        raise PlanError(f"{path}: no batches")
    seen = {batch.batch_id for batch in batches}
    if len(seen) != len(batches):
        raise PlanError(f"{path}: a batch id appears twice; the progress file keys on it")
    return batches


@dataclass
class Spend:
    """What the ledger says has been bought. Read from the ledger, never computed from a price table."""

    calls: int = 0
    cost_usd: float = 0.0
    fetch_lines: int = 0
    torn_lines: int = 0

    @classmethod
    def from_ledger(cls, path: Path) -> Spend:
        """Sum the ledger. A **trailing** partial line is named, an inner one raises.

        The trailing case is real: a kill lands between `write` and `flush` and leaves half a line.
        Counting it as `torn_lines` keeps the loss visible. An unparsable line *inside* the file means
        something was written over or truncated after the fact, and a charge may be missing - that is
        a stop, not a shrug.
        """
        spend = cls()
        if not path.exists():
            return spend
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for number, line in enumerate(lines, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if number == len(lines):
                    spend.torn_lines += 1
                    break
                raise LedgerDamage(
                    f"{path}:{number}: a ledger line inside the file does not parse"
                ) from None
            kind = row.get("kind")
            if kind == L.LedgerKind.MODEL_CALL.value:
                spend.calls += 1
            elif kind == L.LedgerKind.FETCH.value:
                spend.fetch_lines += 1
            cost = row.get("cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                spend.cost_usd += float(cost)
        return spend

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "cost_usd": round(self.cost_usd, 6),
            "fetch_lines": self.fetch_lines,
            "torn_lines": self.torn_lines,
        }


@dataclass(frozen=True)
class Budget:
    """Hard ceilings, checked between batches. `None` means "no ceiling in that dimension"."""

    max_calls: int | None = None
    max_usd: float | None = None

    def stop_reason(self, spend: Spend) -> str | None:
        if self.max_calls is not None and spend.calls >= self.max_calls:
            return f"call ceiling reached: {spend.calls} >= {self.max_calls}"
        if self.max_usd is not None and spend.cost_usd >= self.max_usd:
            return f"dollar ceiling reached: {spend.cost_usd:.6f} >= {self.max_usd:.6f}"
        return None

    def as_text(self) -> str:
        return (
            f"calls<={self.max_calls if self.max_calls is not None else 'unbounded'}, "
            f"usd<={self.max_usd if self.max_usd is not None else 'unbounded'}"
        )


def package_digest(root: Path = PACKAGE) -> str:
    """One digest over the phase-3 sources: the guard against two versions in one run."""
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def batch_state(run_dir: Path, batch_id: str) -> tuple[str, str]:
    """`(state, reason)`: `done` only when the artefacts parse and every written answer is on disk."""
    root = run_dir / batch_id
    if not (root / "input.json").exists():
        return ABSENT, "no input.json (prepare has not run)"
    model: dict[str, Any] = {}
    for name in ("fetch.json", "model.json"):
        path = root / name
        if not path.exists():
            return PARTIAL, f"no {name}"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # A truncated artefact is not evidence: the batch is redone, and a re-run is cheap
            # because fetch and judge both skip what is already on disk.
            return BROKEN, f"{name} does not parse: {exc}"
        if name == "model.json":
            model = payload
    calls = model.get("totals", {}).get("calls")
    judgements = model.get("judgements")
    if not isinstance(calls, int) or not isinstance(judgements, list):
        return BROKEN, "model.json carries no totals.calls or no judgements"
    if len(judgements) != calls:
        return BROKEN, f"model.json claims {calls} calls but carries {len(judgements)} judgements"
    answers = root / "answers"
    for row in judgements:
        if not row.get("wrote"):
            continue
        slug = F.EvidenceStore.slug(str(row["site_id"]), str(row["field"]))
        if not (answers / f"{slug}.txt").exists():
            return BROKEN, f"answer missing for {row['site_id']}/{row['field']}"
    return DONE, f"{calls} answers on disk"


@dataclass
class Progress:
    """The file a human reads while the run is going. Rewritten atomically, never appended to."""

    plan: str
    run_dir: str
    live: bool
    jobs: int
    batches_total: int
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    batches_done: int = 0
    batches_skipped: int = 0
    batches_failed: int = 0
    in_flight: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    not_reached: list[str] = field(default_factory=list)
    spend: dict[str, Any] = field(default_factory=dict)
    stopped: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "run_dir": self.run_dir,
            "live": self.live,
            "jobs": self.jobs,
            "batches_total": self.batches_total,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "batches_done": self.batches_done,
            "batches_skipped": self.batches_skipped,
            "batches_failed": self.batches_failed,
            "in_flight": sorted(self.in_flight),
            "failed": dict(sorted(self.failed.items())),
            "not_reached": self.not_reached,
            "spend": self.spend,
            "stopped": self.stopped,
        }

    def write(self, path: Path) -> None:
        self.updated_at = utc_now()
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text + "\n", encoding="utf-8")
        os.replace(temporary, path)  # atomic on POSIX and on Windows


class BatchRunner(Protocol):
    """The seam `run_mass` drives: one batch in, `(ok, detail)` out.

    A protocol rather than a class, the same way `fetch_stage.Fetcher` is one: the tests stand a stub
    here and no subprocess starts, and the driver still runs against the real `StageRunner`.
    """

    run_dir: Path

    def batch(self, planned: PlannedBatch) -> tuple[bool, str]: ...


class StageRunner:
    """Runs `prepare`, `fetch` and `judge` for one batch, with the logs in files the driver owns."""

    def __init__(
        self,
        *,
        run_dir: Path,
        ledger: Path,
        log_dir: Path,
        live: bool,
        stage_timeout: float = DEFAULT_STAGE_TIMEOUT,
        request_timeout: float | None = None,
        python: Path | None = None,
        runner: Path = RUNNER,
    ) -> None:
        self.run_dir = run_dir
        self.ledger = ledger
        self.log_dir = log_dir
        self.live = live
        self.stage_timeout = stage_timeout
        self.request_timeout = request_timeout
        self.python = python or python_executable()
        self.runner = runner

    def argv(self, stage: str, batch_id: str) -> list[str]:
        argv = [
            str(self.python),
            str(self.runner),
            stage,
            "--run-dir",
            str(self.run_dir),
            "--batch-id",
            batch_id,
            "--ledger",
            str(self.ledger),
        ]
        if self.live:
            argv.append("--live")
        if stage != "prepare" and self.request_timeout is not None:
            argv += ["--timeout", f"{self.request_timeout:g}"]
        return argv

    def call(self, stage: str, batch_id: str) -> int:
        """One stage of one batch. The log is opened before the call, so a crash still leaves why."""
        argv = self.argv(stage, batch_id)
        log_path = self.log_dir / f"{batch_id}.{stage}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # the judge's prompts carry non-ASCII
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n$ {' '.join(argv)}\n")
            log.flush()
            try:
                done = subprocess.run(  # noqa: S603 - our own runner, our own argv, no shell
                    argv,
                    cwd=REPO,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    timeout=self.stage_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                log.write(f"\n! {stage} exceeded {self.stage_timeout:.0f}s and was killed\n")
                return -9
        return done.returncode

    def batch(self, planned: PlannedBatch) -> tuple[bool, str]:
        """All three stages for one batch. Returns `(ok, detail)`; `detail` says where it stands."""
        for stage in STAGES:
            code = self.call(stage, planned.batch_id)
            if code != 0:
                return False, f"{stage} exited {code}"
        state, reason = batch_state(self.run_dir, planned.batch_id)
        if state != DONE:
            return False, f"after all three stages: {state} - {reason}"
        return True, reason


def run_mass(
    *,
    batches: list[PlannedBatch],
    runner: BatchRunner,
    budget: Budget,
    ledger: Path,
    progress: Progress,
    progress_path: Path,
    failures_before_stop: int = DEFAULT_FAILURES_BEFORE_STOP,
    jobs: int = DEFAULT_JOBS,
    plan_digest: str | None = None,
    digest_of: Callable[[], str] = package_digest,
    on_event: Callable[[str], None] | None = None,
) -> int:
    """Walk the plan. Returns 0 when everything asked for is done, 1 when something stopped it."""
    queue = list(batches)
    consecutive = 0
    pending: dict[Future[tuple[bool, str]], PlannedBatch] = {}

    def announce(message: str) -> None:
        print(message, flush=True)
        if on_event is not None:
            on_event(message)

    def guard() -> str | None:
        """Everything that must be true *between* batches, checked before each one is started."""
        reason = budget.stop_reason(Spend.from_ledger(ledger))
        if reason:
            return reason
        if consecutive >= failures_before_stop:
            return f"circuit breaker: {consecutive} consecutive batch failures"
        if plan_digest is not None and digest_of() != plan_digest:
            return "the phase-3 sources changed while the run was going"
        return None

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while (queue or pending) and progress.stopped is None:
            while queue and len(pending) < jobs and progress.stopped is None:
                reason = guard()
                if reason is not None:
                    progress.stopped = reason
                    progress.not_reached = [b.batch_id for b in queue]
                    break
                planned = queue.pop(0)
                state, why = batch_state(runner.run_dir, planned.batch_id)
                if state == DONE:
                    progress.batches_skipped += 1
                    announce(f"{planned.batch_id}: already done ({why})")
                    continue
                pending[pool.submit(runner.batch, planned)] = planned
                progress.in_flight = [b.batch_id for b in pending.values()]
                progress.spend = Spend.from_ledger(ledger).to_dict()
                progress.write(progress_path)
            if not pending:
                break
            finished, _ = wait(set(pending), return_when=FIRST_COMPLETED)
            for future in finished:
                planned = pending.pop(future)
                ok, detail = future.result()
                if ok:
                    consecutive = 0
                    progress.batches_done += 1
                    announce(f"{planned.batch_id}: done ({detail})")
                else:
                    consecutive += 1
                    progress.batches_failed += 1
                    progress.failed[planned.batch_id] = detail
                    announce(f"{planned.batch_id}: FAILED - {detail} ({consecutive} in a row)")
            progress.in_flight = [b.batch_id for b in pending.values()]
            progress.spend = Spend.from_ledger(ledger).to_dict()
            progress.write(progress_path)

    if progress.stopped is None:
        progress.not_reached = []
    progress.spend = Spend.from_ledger(ledger).to_dict()
    progress.write(progress_path)
    return 1 if (progress.stopped or progress.batches_failed) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase3-mass-run",
        description="Drive every batch of a plan through prepare, fetch and judge (dry run default)",
    )
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--progress", default=None, help="default: <log-dir>/progress.json")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--live", action="store_true", help="actually run the stages")
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--max-usd", type=float, default=None)
    parser.add_argument("--failures-before-stop", type=int, default=DEFAULT_FAILURES_BEFORE_STOP)
    parser.add_argument("--stage-timeout", type=float, default=DEFAULT_STAGE_TIMEOUT)
    parser.add_argument("--request-timeout", type=float, default=None)
    parser.add_argument("--only", default=None, help="comma-separated batch ids")
    parser.add_argument("--limit", type=int, default=None, help="stop after N batches of the plan")
    parser.add_argument(
        "--no-digest-guard",
        action="store_true",
        help="do not hash the phase-3 sources at start (only for a deliberately edited run)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan_path, run_dir, ledger = Path(args.plan), Path(args.run_dir), Path(args.ledger)
    log_dir = Path(args.log_dir)
    progress_path = Path(args.progress) if args.progress else log_dir / "progress.json"
    batches = read_plan(plan_path)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        known = {b.batch_id for b in batches}
        unknown = sorted(wanted - known)
        if unknown:
            raise PlanError(f"--only names batches the plan does not have: {unknown}")
        batches = [b for b in batches if b.batch_id in wanted]
    if args.limit is not None:
        batches = batches[: args.limit]
    if args.jobs < 1:
        raise PlanError(f"--jobs {args.jobs}: at least one batch at a time")
    if args.failures_before_stop < 1:
        raise PlanError("--failures-before-stop 0 would stop before the first batch")

    sites = sum(b.sites for b in batches)
    spend = Spend.from_ledger(ledger)
    digest = None if args.no_digest_guard else package_digest()
    print(f"plan          {plan_path}")
    print(f"run dir       {run_dir}")
    print(f"ledger        {ledger}")
    print(f"batches       {len(batches)} ({sites} sites)")
    print(f"expected      {sites * FIELDS_PER_SITE} calls at {FIELDS_PER_SITE} per site")
    print(
        f"projected     ${sites * FIELDS_PER_SITE * MEASURED_COST_PER_CALL:.2f} "
        f"at the measured ${MEASURED_COST_PER_CALL} per call"
    )
    print(f"budget        {Budget(args.max_calls, args.max_usd).as_text()}")
    print(f"already spent {spend.calls} calls, ${spend.cost_usd:.6f}")
    print(f"jobs          {args.jobs}")
    print(f"live          {args.live}")
    if digest is not None:
        print(f"sources       {digest[:16]}")
    if not args.live:
        done = sum(1 for b in batches if batch_state(run_dir, b.batch_id)[0] == DONE)
        print(f"dry run       {done} of {len(batches)} batches already done; nothing was bought")
        return 0

    progress = Progress(
        plan=str(plan_path),
        run_dir=str(run_dir),
        live=True,
        jobs=args.jobs,
        batches_total=len(batches),
        spend=spend.to_dict(),
    )
    progress.write(progress_path)
    runner = StageRunner(
        run_dir=run_dir,
        ledger=ledger,
        log_dir=log_dir,
        live=True,
        stage_timeout=args.stage_timeout,
        request_timeout=args.request_timeout,
    )
    return run_mass(
        batches=batches,
        runner=runner,
        budget=Budget(args.max_calls, args.max_usd),
        ledger=ledger,
        progress=progress,
        progress_path=progress_path,
        failures_before_stop=args.failures_before_stop,
        jobs=args.jobs,
        plan_digest=digest,
    )


if __name__ == "__main__":
    sys.exit(main())
