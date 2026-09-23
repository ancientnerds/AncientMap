"""The Phase-4 mass run: every batch of `PLAN4.jsonl` through the stages, with Phase 3's guards.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, pipeline
"DRIVER" (`--max-usd 15`, `--max-searches 700`, resume by answer existence) and
volumes_cost_runtime. Work item WB-B4.

What is reused from `phase3/mass_run.py`, by import and never copied: the loop with its ceilings,
its circuit breaker and its progress file (`run_mass`, `Budget`, `Spend`, `Progress`), and the
stage process with its bounded spawn retry (`StageRunner.call`). What is Phase 4's own:

* **The stages** are `run4.py`'s `prepare, sources, routes, select, assemble, verify, review`, one
  process each, and what is read is the process's own `STAGE_EXIT=` line, never its exit status. A
  stage that printed no line died before it finished: the batch failed (the circuit breaker counts
  it). A stage that printed a non-zero line could not complete its batch, which by the contracts'
  rule stops the whole run (`stop_reason`).
* **Done** is Phase 4's own state (`batch_done`): the review wrote `review4.json` over the
  `assembly.jsonl` that is on disk, and every site of the batch is either in it or held. A done
  batch is not started again; any other batch runs every stage, which costs only what is missing
  (every model answer and every fetched page is reused from disk).
* **The digest** is over `phase4/` (`package_digest(root=<phase4>)`), passed as its own root.
* **Searches** are bounded per run: each `routes` stage is told how many of the run's
  `--max-searches` are left, and the budget stops the run between batches. The routes stages of
  parallel batches take turns (`search_turn`), so no two are told the same remainder.
* **A revision younger than 48 h defers the site to a later batch** (design S1). S1 and S1b hold
  such a site `revision-too-fresh`, and the hold is final for its batch directory (the stored
  answer is judged again on a re-run). The driver defers it: a site whose latest batch held it so is
  re-queued, once 48 h have passed since the answer that held it (`sources_stage.fresh_until`),
  into a new batch of `REQUEUE4.jsonl` in the run directory - PLAN4's line shape and numbering
  (`p4-NNNN`, after the last ordinal of the plan and of earlier re-queues, 15 sites a batch), so
  `run4 prepare` copies it like a plan line. The re-queued batches run after the plan's; a site not
  ready yet is re-queued by a later invocation. Its latest batch is then the one that counts
  (`run4.aggregate_holds` drops the holds of the batches it left).

Dry by default: without `--live` nothing is started, no ledger line and no re-queue is written. At
the end the driver writes `HOLDS4.jsonl` beside the batches (`run4.aggregate_holds`).

    ./.venv/Scripts/python.exe scripts/remediation/phase4/mass4.py \\
        --run-dir output/remediation/phase4_runner/runs/pilot --live --jobs 4
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import mass_run as MR  # noqa: E402
from phase3 import run as R3  # noqa: E402
from phase3.run import InputError, read_jsonl  # noqa: E402

from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4 as P4  # noqa: E402
from phase4 import run4 as R4  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402

PHASE4_DIR = Path(__file__).resolve().parent
RUN4 = PHASE4_DIR / "run4.py"
REPO = PHASE4_DIR.parents[2]
DEFAULT_LOG_DIR = REPO / "output" / "remediation" / "logs" / "phase4_mass"
STAGES4 = ("prepare", "sources", "routes", "select", "assemble", "verify", "review")
#: The stages that buy something and therefore take `--live`.
LIVE_STAGES = frozenset({"sources", "routes", "select", "review"})
#: The stages that open sockets, and so share the machine's per-host pace.
PACED_STAGES = frozenset({"sources", "routes"})
DEFAULT_MAX_USD = 15.0
DEFAULT_MAX_SEARCHES = 700
#: The run directory's re-queue plan: the batches of sites deferred for a too fresh revision.
REQUEUE_FILE = "REQUEUE4.jsonl"

#: One exit line. The child writes its log in text mode, so on Windows the line ends in `\r\n`.
_EXIT_LINE = re.compile(rf"^{R4.STAGE_EXIT}(?P<code>-?[0-9]+)\r?$", re.MULTILINE)


@dataclass(frozen=True)
class PlanLine:
    """One line of `PLAN4.jsonl` or `REQUEUE4.jsonl`: a batch and its sites."""

    batch_id: str
    ordinal: int
    sites: tuple[M.PlanSite, ...]

    def planned(self) -> MR.PlannedBatch:
        return MR.PlannedBatch(batch_id=self.batch_id, ordinal=self.ordinal, sites=len(self.sites))

    def to_json(self) -> str:
        """The plan's own line shape (`phase3.run.Batch`), which `run4 prepare` copies."""
        sites = tuple(site.to_dict() for site in self.sites)
        return R3.Batch(batch_id=self.batch_id, ordinal=self.ordinal, sites=sites).to_json()


def read_plan4_lines(path: Path) -> list[PlanLine]:
    """The whole plan, or nothing: every line a `p4-` batch of `PlanSite`s, no id twice."""
    lines: list[PlanLine] = []
    site_ids: set[str] = set()
    for number, row in enumerate(read_jsonl(path), start=1):
        batch_id = row.get("batch_id")
        ordinal = row.get("ordinal")
        if not isinstance(batch_id, str) or not batch_id.startswith(R4.BATCH_PREFIX):
            raise MR.PlanError(f"{path}:{number}: {batch_id!r} is not a Phase-4 batch id")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise MR.PlanError(f"{path}:{number}: {batch_id} carries no integer ordinal")
        sites = R4.plan_line_sites(row, f"{path}:{number}")
        for plan_site in sites:
            if plan_site.site_id in site_ids:
                raise MR.PlanError(f"{path}:{number}: {plan_site.site_id} is planned twice")
            site_ids.add(plan_site.site_id)
        lines.append(PlanLine(batch_id=batch_id, ordinal=ordinal, sites=tuple(sites)))
    if not lines:
        raise MR.PlanError(f"{path}: no batches")
    if len({line.batch_id for line in lines}) != len(lines):
        raise MR.PlanError(f"{path}: a batch id appears twice; the progress file keys on it")
    return lines


def read_plan4(path: Path) -> list[MR.PlannedBatch]:
    return [line.planned() for line in read_plan4_lines(path)]


# ---------------------------------------------------------------------------- the re-queue


def read_requeue(run_dir: Path, plan: Sequence[PlanLine]) -> list[PlanLine]:
    """The run's re-queued batches (`REQUEUE4.jsonl`; a run that never re-queued has none): each
    the batch `p4-<ordinal>` of an ordinal after every line before it, of planned sites, each once."""
    path = run_dir / REQUEUE_FILE
    if not path.exists():
        return []
    planned = {site.site_id for line in plan for site in line.sites}
    taken = {line.batch_id for line in plan}
    last = max(line.ordinal for line in plan)
    lines: list[PlanLine] = []
    for number, row in enumerate(read_jsonl(path), start=1):
        where = f"{path}:{number}"
        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal <= last:
            raise MR.PlanError(f"{where}: ordinal {ordinal!r} does not follow ordinal {last}")
        batch_id = f"{P4.BATCH_PREFIX}-{ordinal:04d}"
        if row.get("batch_id") != batch_id or batch_id in taken:
            raise MR.PlanError(f"{where}: {row.get('batch_id')!r} is not the new batch {batch_id}")
        sites = R4.plan_line_sites(row, where)
        ids = [site.site_id for site in sites]
        if len(set(ids)) != len(ids) or not set(ids) <= planned:
            raise MR.PlanError(f"{where}: a re-queued batch carries planned sites, each once")
        taken.add(batch_id)
        last = ordinal
        lines.append(PlanLine(batch_id=batch_id, ordinal=ordinal, sites=tuple(sites)))
    return lines


@dataclass(frozen=True)
class Deferred:
    """A site its latest batch held `revision-too-fresh`, and when it may be asked again."""

    site: M.PlanSite
    held_in: str
    ready_at: datetime


def deferred_sites(run_dir: Path, lines: Sequence[PlanLine]) -> list[Deferred]:
    """Every site whose latest batch - the last line that lists it - held it `revision-too-fresh`:
    48 h after the answer that held it, it goes into a later batch (design S1)."""
    latest: dict[str, tuple[str, M.PlanSite]] = {}
    for line in lines:
        for site in line.sites:
            latest[site.site_id] = (line.batch_id, site)
    fresh: dict[str, dict[str, M.Hold]] = {}
    deferred: list[Deferred] = []
    for site_id, (batch_id, site) in latest.items():
        if batch_id not in fresh:
            fresh[batch_id] = {
                hold.site_id: hold
                for hold in B.read_holds(run_dir / batch_id)
                if hold.scope is M.HoldScope.SITE and hold.reason is M.HoldReason.REVISION_TOO_FRESH
            }
        hold = fresh[batch_id].get(site_id)
        if hold is not None:
            deferred.append(Deferred(site, batch_id, S1.fresh_until(hold.detail)))
    return deferred


def requeue_lines(
    lines: Sequence[PlanLine], deferred: Sequence[Deferred], *, now: datetime
) -> list[PlanLine]:
    """The deferred sites whose 48 h have passed, in new batches of `plan4.BATCH_SIZE` numbered
    after every line of the plan and of earlier re-queues."""
    ready = [item.site for item in deferred if item.ready_at <= now]
    first = max(line.ordinal for line in lines) + 1
    return [
        PlanLine(
            batch_id=f"{P4.BATCH_PREFIX}-{first + k:04d}",
            ordinal=first + k,
            sites=tuple(ready[start : start + P4.BATCH_SIZE]),
        )
        for k, start in enumerate(range(0, len(ready), P4.BATCH_SIZE))
    ]


def append_requeue(run_dir: Path, new: Sequence[PlanLine]) -> None:
    """Append the new batches to `REQUEUE4.jsonl`; the lines already there are never rewritten."""
    path = run_dir / REQUEUE_FILE
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    B.write_text_atomic(path, before + "".join(line.to_json() + "\n" for line in new))


def stage_exit(output: str) -> int | None:
    """The code of the last `STAGE_EXIT=` line a stage printed, or `None` when it printed none."""
    codes = [int(match["code"]) for match in _EXIT_LINE.finditer(output)]
    return codes[-1] if codes else None


def batch_done(run_dir: Path, batch_id: str) -> tuple[bool, str]:
    """Done: `review4.json` finished over the `assembly.jsonl` on disk, and every site of the
    batch is in that file or held. Anything else - absent, torn, changed since - is not done."""
    root = run_dir / batch_id
    report = root / B.REVIEW_REPORT
    if not (root / M.INPUT_FILE).exists():
        return False, "no input.json"
    if not report.exists():
        return False, "no review4.json"
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"review4.json does not parse: {exc}"
    if payload.get("error") is not None:
        return False, f"the review stopped: {payload['error']}"
    assembly = root / M.ASSEMBLY_FILE
    if not assembly.exists() or payload.get("assembly_sha256") != B.sha256_file(assembly):
        return False, "assembly.jsonl is not the one the review wrote"
    _, sites = B.read_batch(root)
    written = {a.site_id for a in M.load_jsonl(assembly, M.Assembly)}
    held = B.site_held(B.read_holds(root))
    loose = sorted({s.site_id for s in sites} - written - held)
    if loose:
        return False, f"{len(loose)} site(s) neither written nor held, first {loose[0]}"
    return True, f"{len(written)} assembled, {len(held - written)} held"


class Phase4StageRunner(MR.StageRunner):
    """`mass_run.StageRunner` with Phase 4's stages: its `call` (log file, stage timeout, bounded
    spawn retry) is used as it is; the argv, the exit line and the done state are Phase 4's."""

    def __init__(
        self,
        *,
        plan: Path,
        run_dir: Path,
        ledger: Path,
        log_dir: Path,
        live: bool,
        budget: MR.Budget,
        stage_timeout: float = MR.DEFAULT_STAGE_TIMEOUT,
        pacing_dir: Path | None = MR.DEFAULT_PACING_DIR,
        python: Path | None = None,
        requeued: Collection[str] = (),
    ) -> None:
        # `StageRunner` checks its stage names against Phase 3's sequences; its default passes, and
        # the stages this runner walks are `stages4`.
        super().__init__(
            plan=plan,
            run_dir=run_dir,
            ledger=ledger,
            log_dir=log_dir,
            live=live,
            stage_timeout=stage_timeout,
            pacing_dir=pacing_dir,
            python=python,
            runner=RUN4,
        )
        self.stages4 = STAGES4
        self.budget = budget
        #: The batches `prepare` copies from the run's `REQUEUE4.jsonl` instead of the plan.
        self.requeued = frozenset(requeued)
        #: The ledger as it was when this run started: the search allowance counts from here.
        self.baseline = MR.Spend.from_ledger(ledger)
        #: Held by a routes stage from its argv to its exit, so the stages of parallel batches take
        #: turns: each is told what the run has left once the one before it has spent, and the
        #: allowances handed out can never add up to more than `--max-searches`.
        self.search_turn = threading.Lock()

    def searches_left(self) -> int:
        if self.budget.max_searches is None:
            raise InputError("a Phase-4 run needs --max-searches: routes buys MiniMax searches")
        spent = MR.Spend.from_ledger(self.ledger).searches - self.baseline.searches
        return max(0, self.budget.max_searches - spent)

    def argv(self, stage: str, batch_id: str) -> list[str]:
        argv = [
            str(self.python),
            str(self.runner),
            stage,
            "--run-dir",
            str(self.run_dir),
            "--batch-id",
            batch_id,
        ]
        if stage == "prepare":
            plan = self.run_dir / REQUEUE_FILE if batch_id in self.requeued else self.plan
            return [*argv, "--plan", str(plan)]
        argv += ["--ledger", str(self.ledger)]
        if self.live and stage in LIVE_STAGES:
            argv.append("--live")
        if stage in PACED_STAGES and self.pacing_dir is not None:
            argv += ["--pacing-dir", str(self.pacing_dir)]
        if stage == "routes":
            argv += ["--max-searches", str(self.searches_left())]
        return argv

    def batch(self, planned: MR.PlannedBatch) -> tuple[bool, str]:
        done, why = batch_done(self.run_dir, planned.batch_id)
        if done:
            return True, f"already done: {why}"
        for stage in self.stages4:
            log = self.log_dir / f"{planned.batch_id}.{stage}.log"
            start = log.stat().st_size if log.exists() else 0
            if stage == "routes":
                with self.search_turn:
                    code = self.call(stage, planned.batch_id)
            else:
                code = self.call(stage, planned.batch_id)
            written = log.read_bytes()[start:].decode("utf-8", errors="replace")
            said = stage_exit(written)
            if said is None:
                return False, f"{stage} printed no {R4.STAGE_EXIT} line (process exit {code})"
            if said != 0:
                why = MR.report_error(written)
                self.stop_reason = (
                    f"{planned.batch_id}: {stage} could not complete its batch "
                    f"({R4.STAGE_EXIT}{said}): {why}"
                )
                return False, f"{stage} {R4.STAGE_EXIT}{said}"
        done, why = batch_done(self.run_dir, planned.batch_id)
        return done, why if done else f"after every stage: {why}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase4-mass", description=__doc__.splitlines()[0])
    parser.add_argument("--plan", default=str(R4.DEFAULT_PLAN))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--ledger", default=str(R4.DEFAULT_LEDGER))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--progress", default=None, help="default: <log-dir>/progress.json")
    parser.add_argument("--jobs", type=int, default=MR.DEFAULT_JOBS)
    parser.add_argument("--live", action="store_true", help="actually run the stages")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    parser.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES)
    parser.add_argument("--failures-before-stop", type=int, default=MR.DEFAULT_FAILURES_BEFORE_STOP)
    parser.add_argument("--stage-timeout", type=float, default=MR.DEFAULT_STAGE_TIMEOUT)
    parser.add_argument("--only", default=None, help="comma-separated batch ids")
    parser.add_argument("--limit", type=int, default=None, help="the first N batches of the plan")
    return parser


def main(argv: list[str] | None = None) -> int:
    R4.utf8_streams()
    args = build_parser().parse_args(argv)
    code = drive(args)
    print(f"{R4.STAGE_EXIT}{code}", flush=True)
    return code


def drive(args: argparse.Namespace) -> int:
    plan, run_dir, ledger = Path(args.plan), Path(args.run_dir), Path(args.ledger)
    log_dir = Path(args.log_dir)
    planned = read_plan4_lines(plan)
    requeued = read_requeue(run_dir, planned)
    deferred = deferred_sites(run_dir, [*planned, *requeued])
    now = datetime.now(UTC)
    new = requeue_lines([*planned, *requeued], deferred, now=now)
    waiting = sorted(item.ready_at for item in deferred if item.ready_at > now)
    if args.live and new:
        append_requeue(run_dir, new)
        requeued += new
    batches = [line.planned() for line in [*planned, *requeued]]
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        unknown = sorted(wanted - {b.batch_id for b in batches})
        if unknown:
            raise MR.PlanError(f"--only names batches the plan does not have: {unknown}")
        batches = [b for b in batches if b.batch_id in wanted]
    if args.limit is not None:
        batches = batches[: args.limit]
    if args.jobs < 1 or args.failures_before_stop < 1:
        raise MR.PlanError("--jobs and --failures-before-stop are at least 1")
    budget = MR.Budget(max_calls=None, max_usd=args.max_usd, max_searches=args.max_searches)
    digest = MR.package_digest(root=PHASE4_DIR)
    spend = MR.Spend.from_ledger(ledger)
    print(f"plan          {plan}")
    print(f"run dir       {run_dir}")
    print(f"ledger        {ledger}")
    print(f"stages        {','.join(STAGES4)}")
    print(f"batches       {len(batches)} ({sum(b.sites for b in batches)} sites)")
    print(
        f"re-queue      {len(requeued)} batch(es) in {REQUEUE_FILE}; "
        f"{sum(len(line.sites) for line in new)} site(s) ready "
        f"{'re-queued now' if args.live else '(written by a live run)'}, {len(waiting)} waiting"
        + (f" (the first until {S1.iso_utc(waiting[0])})" if waiting else "")
    )
    print(f"budget        {budget.as_text()}")
    print(f"already spent {spend.calls} calls, ${spend.cost_usd:.6f}, {spend.searches} searches")
    print(f"sources       phase4 {digest[:16]}")
    if not args.live:
        done = sum(1 for b in batches if batch_done(run_dir, b.batch_id)[0])
        print(f"dry run       {done} of {len(batches)} batches already done; nothing was bought")
        return 0
    progress_path = Path(args.progress) if args.progress else log_dir / "progress.json"
    progress = MR.Progress(
        plan=str(plan),
        run_dir=str(run_dir),
        live=True,
        jobs=args.jobs,
        batches_total=len(batches),
        spend=spend.to_dict(),
    )
    progress.write(progress_path)
    runner = Phase4StageRunner(
        plan=plan,
        run_dir=run_dir,
        ledger=ledger,
        log_dir=log_dir,
        live=True,
        budget=budget,
        stage_timeout=args.stage_timeout,
        requeued=[line.batch_id for line in requeued],
    )
    code = MR.run_mass(
        batches=batches,
        runner=runner,
        budget=budget,
        ledger=ledger,
        progress=progress,
        progress_path=progress_path,
        failures_before_stop=args.failures_before_stop,
        jobs=args.jobs,
        plan_digest=digest,
        digest_of=lambda: MR.package_digest(root=PHASE4_DIR),
        stop_of=lambda: runner.stop_reason,
    )
    holds = R4.aggregate_holds(run_dir)
    B.write_text_atomic(run_dir / R4.HOLDS4_FILE, M.dump_jsonl(holds))
    print(f"holds         {len(holds)} in {run_dir / R4.HOLDS4_FILE}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
