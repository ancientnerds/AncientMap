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
* **A *start* failure is retried, bounded and loud.** Measured 2026-09-21: twice the host had a few
  seconds in which no process could be started at all - `judge exited 2` with the child's own report
  saying `'pi.cmd' could not be started`, and `prepare exited 3221225794` (`STATUS_DLL_INIT_FAILED`).
  Up to `MAX_SPAWN_ATTEMPTS` starts, one line per retry in the stage log, the count in
  `progress.json`, and a stage that recovers is neither a failed batch nor a circuit-breaker count.
  Every other failure - a failed call, a timeout, a parse error - is returned on its first exit.
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

    # the search lane (block A3): a search plan, its own run directory, a search ceiling
    ./.venv/Scripts/python.exe scripts/remediation/phase3/mass_run.py --live --jobs 4 \
        --plan output/remediation/phase3_runner/PLAN.search.jsonl \
        --run-dir output/remediation/phase3_runner/runs/search1 --stages prepare,search,judge \
        --max-calls 4500 --max-usd 8 --max-searches 4600

A search batch's `search` stage gates itself on the MiniMax quota and exits `run.STOP_RUN_EXIT` when
the gate refuses or a stop-class error arrives; the driver then stops the whole run (`stop_of`), with
the reason the stage printed at the top level of its own report. The quota readings each batch's
`search.json` holds - one entry per run of the stage that probed, carried forward across resumes - are
copied into `progress.json` under `quota`, seeded from every existing report when the run starts, so
a resumed run's progress file still holds what earlier runs measured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
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
from phase3 import model_stage as MS  # noqa: E402  - one spelling for a named failure's shape
from phase3 import search_evidence as SE  # noqa: E402  - a search plan's rerun fields
from phase3 import search_stage as SS  # noqa: E402  - the search report's quota readings
from phase3.run import STOP_RUN_EXIT, InputError  # noqa: E402  - search's "stop the run" exit

DEFAULT_PLAN = REPO / "output" / "remediation" / "phase3_runner" / "PLAN.jsonl"
DEFAULT_RUN_DIR = REPO / "output" / "remediation" / "phase3_runner" / "runs" / "mass1"
DEFAULT_LEDGER = REPO / "output" / "remediation" / "phase3_runner" / "LEDGER.jsonl"
DEFAULT_LOG_DIR = REPO / "output" / "remediation" / "logs" / "massrun"
#: The machine-local pace directory every batch this driver starts shares. Passed to `fetch`
#: explicitly rather than left to that command's default, and the default there has to stay empty: a
#: lone `run.py fetch --live` has nobody to pace against, while a shared default would let a test or a
#: second run take a host's lock and hold a live run up. Same path as `run.DEFAULT_PACING_DIR` (a test
#: asserts the two agree).
DEFAULT_PACING_DIR = REPO / "output" / "remediation" / "logs" / "pacing"
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
#: The first NTSTATUS value. An exit code at or above it means Windows never gave the child a process:
#: `0xC0000142` (`STATUS_DLL_INIT_FAILED`) and its neighbours arrive here as the unsigned DWORD
#: measured on 2026-09-21 as `prepare exited 3221225794`. The runner's own codes sit far below it, and
#: so does the timeout sentinel `-9`.
NTSTATUS_START_FAILURE = 0xC0000000
#: How often one stage may be *started*. Bounded on purpose: a retry that hides real breakage is worse
#: than the stop. Measured 2026-09-22 00:09: three attempts five seconds apart were **not** enough - four
#: batches exhausted them while the host still could not start a process, after six other retries had
#: already recovered. Hence six starts.
MAX_SPAWN_ATTEMPTS = 6
#: How long to wait between those starts. Long enough to outlast the measured hiccup: six starts fifteen
#: seconds apart cover 75 s. Everything that is *not* a start failure still returns on its first exit.
SPAWN_RETRY_WAIT_SECONDS = 15.0
#: The child's own words when a program *it* started never came up (`model_stage.ModelCallFailed`,
#: its `OSError` branch). A child that did run says so in the `error` of its own JSON report.
UNSTARTABLE_PROGRAM = "could not be started"
#: How a child report's own `error` line opens: `run.py` prints its reports with `indent=1`, so a
#: top-level key sits behind exactly one space and a nested one behind more (`report_error`).
TOP_LEVEL_ERROR = ' "error":'
STAGES = ("prepare", "fetch", "judge")
#: The search lane's sequence (block A3): the evidence is the mass run's, copied by `prepare`, plus
#: MiniMax search hits - so `search` takes `fetch`'s place.
SEARCH_STAGES = ("prepare", "search", "judge")
STAGE_SEQUENCES: dict[str, tuple[str, ...]] = {
    ",".join(STAGES): STAGES,
    ",".join(SEARCH_STAGES): SEARCH_STAGES,
}
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
    """One line of the plan, as `snapshot_plan` writes it: `{batch_id, ordinal, sites}`.

    A search plan's line (`phase3/search_plan.py`) names the fields it reruns per site; then
    `rerun_fields` is their count and `searches` the searches they buy. `None` is the snapshot plan,
    whose every site is asked all five fields.
    """

    batch_id: str
    ordinal: int
    sites: int
    rerun_fields: int | None = None
    searches: int = 0

    @property
    def search(self) -> bool:
        return self.rerun_fields is not None

    @property
    def expected_calls(self) -> int:
        if self.rerun_fields is not None:
            return self.rerun_fields
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
        try:
            rerun = [SE.rerun_fields(site) for site in sites]
            searches = sum(len(SE.search_slots(site)) for site in sites)
            for site, fields in zip(sites, rerun, strict=True):
                if fields is not None:
                    # What the search stage and the reviewer read, checked before anything is
                    # bought: a plan built before these keys existed is refused here, not later.
                    SE.unwritten_proposals(site)
                    SS.query_values(site)
        except InputError as exc:
            raise PlanError(f"{path}:{number}: {exc}") from None
        if any(fields is None for fields in rerun) and any(fields is not None for fields in rerun):
            raise PlanError(f"{path}:{number}: some sites name rerun_fields and some do not")
        batches.append(
            PlannedBatch(
                batch_id=batch_id,
                ordinal=ordinal,
                sites=len(sites),
                rerun_fields=None
                if rerun[0] is None
                else sum(len(fields or ()) for fields in rerun),
                searches=searches,
            )
        )
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
    #: The fetch lines of the search lane: one per MiniMax search request, retries included, told
    #: apart by their label `<site>/minimax_search.<key>` (`phase3/search_stage.py`).
    searches: int = 0

    @classmethod
    def from_ledger(cls, path: Path) -> Spend:
        """Sum the ledger. A **trailing** partial line is named, an inner one raises.

        The trailing case is real: a kill lands between `write` and `flush` and leaves half a line.
        Counting it as `torn_lines` keeps the loss visible. An unparsable line *inside* the file means
        something was written over or truncated after the fact, and a charge may be missing - that is
        a stop, not a shrug.

        A `cost_usd` that is present and is not a finite, non-negative number raises for that same
        reason: this sum is what the money ceiling is measured against, so a cost silently skipped as
        zero would under-count the spend and let a run past its ceiling. A missing or `null` cost is
        the normal case for a row that has no charge and stays zero. The `OverflowError` is the case
        of a literal integer in the ledger too large for a float; it is a damaged ledger, not a cost.
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
                if f"/{SE.SEARCH_FEATURE_PREFIX}" in str(row.get("label") or ""):
                    spend.searches += 1
            cost = row.get("cost_usd")
            if cost is not None:
                if isinstance(cost, bool) or not isinstance(cost, (int, float)):
                    raise LedgerDamage(
                        f"{path}:{number}: cost_usd is {type(cost).__name__}, which is not a cost"
                    )
                try:
                    value = float(cost)
                except OverflowError:
                    raise LedgerDamage(
                        f"{path}:{number}: cost_usd is an integer too large to be a cost"
                    ) from None
                if not math.isfinite(value) or value < 0:
                    raise LedgerDamage(
                        f"{path}:{number}: cost_usd is {cost!r}, which is not a cost"
                    )
                spend.cost_usd += value
        return spend

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "cost_usd": round(self.cost_usd, 6),
            "fetch_lines": self.fetch_lines,
            "searches": self.searches,
            "torn_lines": self.torn_lines,
        }


@dataclass(frozen=True)
class Budget:
    """Hard ceilings, checked between batches. `None` means "no ceiling in that dimension"."""

    max_calls: int | None = None
    max_usd: float | None = None
    #: MiniMax search requests this run may make (the search lane's `--max-searches`).
    max_searches: int | None = None

    def stop_reason(self, spend: Spend, baseline: Spend | None = None) -> str | None:
        """The ceiling is for **this run**, counted from the ledger as it was when the run started.

        The ledger is shared with the pilot and with six recall rounds, 465 model calls of it. An
        absolute ceiling would therefore make `--max-calls 25020` stop 465 calls early and quietly
        mean something other than what it says - the same defect class as a migration label that
        asks a different question than it answers. Both numbers are named, so the ledger's total
        stays in view instead of being hidden by the subtraction.
        """
        bought = spend.calls - (baseline.calls if baseline is not None else 0)
        spent = spend.cost_usd - (baseline.cost_usd if baseline is not None else 0.0)
        if self.max_calls is not None and bought >= self.max_calls:
            return (
                f"call ceiling reached: {bought} >= {self.max_calls} calls this run "
                f"(the ledger holds {spend.calls})"
            )
        if self.max_usd is not None and spent >= self.max_usd:
            return (
                f"dollar ceiling reached: {spent:.6f} >= {self.max_usd:.6f} this run "
                f"(the ledger holds {spend.cost_usd:.6f})"
            )
        searched = spend.searches - (baseline.searches if baseline is not None else 0)
        if self.max_searches is not None and searched >= self.max_searches:
            return (
                f"search ceiling reached: {searched} >= {self.max_searches} search requests this "
                f"run (the ledger holds {spend.searches})"
            )
        return None

    def as_text(self) -> str:
        return (
            f"calls<={self.max_calls if self.max_calls is not None else 'unbounded'}, "
            f"usd<={self.max_usd if self.max_usd is not None else 'unbounded'}, "
            f"searches<={self.max_searches if self.max_searches is not None else 'unbounded'}"
            " per run"
        )


def package_digest(root: Path = PACKAGE) -> str:
    """One digest over the phase-3 sources: the guard against two versions in one run."""
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def search_state(root: Path) -> tuple[str, str] | None:
    """What a search batch's `search.json` says against "done", or `None` when it says nothing.

    A batch without the file is not a search batch (or its search has not run, which the stage
    sequence catches). With the file, a batch is done only when every search is on disk: a failed or
    stopped search leaves it partial, so the driver retries the searches before the judge - whose
    answers, once written, would be reused and never see the evidence a retried search adds.
    """
    path = root / MS.SEARCH_REPORT_NAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return BROKEN, f"search.json does not parse: {exc}"
    totals = payload.get("totals") if isinstance(payload, dict) else None
    failed = totals.get("failed") if isinstance(totals, dict) else None
    if not isinstance(failed, int) or isinstance(failed, bool) or "stopped" not in payload:
        return BROKEN, "search.json carries no totals.failed or no stopped"
    if payload["stopped"] is not None or failed:
        return PARTIAL, f"search incomplete: {failed} failed, stopped={payload['stopped']!r}"
    return None


def search_quota(run_dir: Path, batch_id: str) -> list[dict[str, Any]] | None:
    """Every quota reading a search batch's `search.json` holds, or `None` when it has none yet.

    The list is the report's own (`search_stage.read_quota`): one entry per run of the stage that
    probed, carried forward across resumes. A damaged report raises there.
    """
    path = run_dir / batch_id / MS.SEARCH_REPORT_NAME
    if not path.exists():
        return None
    return SS.read_quota(path)


def batch_state(run_dir: Path, batch_id: str) -> tuple[str, str]:
    """`(state, reason)`: `done` only when the artefacts parse and every written answer is on disk."""
    root = run_dir / batch_id
    if not (root / "input.json").exists():
        return ABSENT, "no input.json (prepare has not run)"
    search = search_state(root)
    if search is not None:
        return search
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
    # A named failure (`model_stage.FailedCall`) is a call the runner bought and could not read an
    # answer out of. It is settled - the call happened - but only *in its recorded shape*:
    # `site_id`, `field`, `reason` and nothing else. A list of bare strings, or an entry that grew a
    # `verdict` or a `proposed` value, is not credited, so the check still cannot be satisfied by
    # writing something else into the file. "A truncated artefact is not evidence" holds here too.
    named = model.get("failures", [])
    if not isinstance(named, list) or not all(MS.is_named_failure(row) for row in named):
        return BROKEN, "model.json carries a failures list that is not a set of named failures"
    if len(judgements) + len(named) != calls:
        return BROKEN, (
            f"model.json claims {calls} calls but carries {len(judgements)} judgements"
            + (f" and {len(named)} named failures" if named else "")
        )
    answers = root / "answers"
    for row in judgements:
        if not row.get("wrote"):
            continue
        slug = F.EvidenceStore.slug(str(row["site_id"]), str(row["field"]))
        if not (answers / f"{slug}.txt").exists():
            return BROKEN, f"answer missing for {row['site_id']}/{row['field']}"
    if named:
        # Done, and honest about the holes: the batch is never re-run for them (a re-run re-buys
        # every call of a discover batch and would only hit the recorded bytes as a conflict).
        return DONE, (
            f"{calls} calls accounted for: {len(judgements)} answers on disk, "
            f"{len(named)} unreadable stream(s)"
        )
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
    spawn_retries: int = 0
    in_flight: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    not_reached: list[str] = field(default_factory=list)
    spend: dict[str, Any] = field(default_factory=dict)
    stopped: str | None = None
    #: A search batch's MiniMax quota readings keyed by batch id: `search.json`'s own `quota` list,
    #: one `{before, after, requests}` entry per run of the stage that probed. `weekly_remains_tokens`
    #: across them is the plan's cost signal, an upper bound when Lyra or Theo spend in parallel.
    quota: dict[str, Any] = field(default_factory=dict)

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
            "spawn_retries": self.spawn_retries,
            "in_flight": sorted(self.in_flight),
            "failed": dict(sorted(self.failed.items())),
            "not_reached": self.not_reached,
            "quota": dict(sorted(self.quota.items())),
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


def report_error(text: str) -> str | None:
    """The `error` string of the child's own JSON report, or `None` when the child wrote none.

    `run.py` prints that report to stdout, which the driver sends to the stage log, so the log is the
    only place a failed spawn *inside* the child is visible. The report is indented (`json.dumps(...,
    indent=1, sort_keys=True)`), so its key's line is read rather than the whole document: the value
    is a JSON string, and only a line that opens with the report's **own** `"error"` key counts - one
    space of indentation, the top level. A nested `error` (the search report's
    `sites[].outcomes[].attempts[].error`, null for every answered request) sorts after the top-level
    one and would otherwise be read first from the bottom up, turning the stop reason into `None`.
    """
    for line in reversed(text.splitlines()):
        if not line.startswith(TOP_LEVEL_ERROR):
            continue
        try:
            error = json.loads(line[len(TOP_LEVEL_ERROR) :].strip().rstrip(","))
        except json.JSONDecodeError:
            continue
        return error if isinstance(error, str) else None
    return None


def spawn_failure(code: int, output: str) -> bool:
    """Did the process fail to *start*, rather than fail at the work?

    Two shapes, and only these two: (a) the exit code is an NTSTATUS, so Windows never ran the child;
    (b) the child ran and its own report names a program that "could not be started" - the spawn that
    failed was inside the child. A failed model call, a parse error and a timeout are the work's own
    outcomes and are **not** retried.
    """
    if code >= NTSTATUS_START_FAILURE:
        return True
    error = report_error(output)
    return error is not None and UNSTARTABLE_PROGRAM in error


class BatchRunner(Protocol):
    """The seam `run_mass` drives: one batch in, `(ok, detail)` out.

    A protocol rather than a class, the same way `fetch_stage.Fetcher` is one: the tests stand a stub
    here and no subprocess starts, and the driver still runs against the real `StageRunner`.
    """

    run_dir: Path
    #: How often a stage was started again after a failed start, carried into `progress.json`. Part of
    #: the seam because the driver writes that file; a stub that never retries reports 0.
    spawn_retries: int

    def batch(self, planned: PlannedBatch) -> tuple[bool, str]: ...


class StageRunner:
    """Runs `prepare`, `fetch` and `judge` for one batch, with the logs in files the driver owns."""

    def __init__(
        self,
        *,
        plan: Path,
        run_dir: Path,
        ledger: Path,
        log_dir: Path,
        live: bool,
        stage_timeout: float = DEFAULT_STAGE_TIMEOUT,
        request_timeout: float | None = None,
        pacing_dir: Path | None = DEFAULT_PACING_DIR,
        python: Path | None = None,
        runner: Path = RUNNER,
        stages: tuple[str, ...] = STAGES,
    ) -> None:
        if stages not in STAGE_SEQUENCES.values():
            raise PlanError(f"stages {stages!r} are not one of {sorted(STAGE_SEQUENCES)}")
        self.plan = plan
        self.run_dir = run_dir
        self.ledger = ledger
        self.log_dir = log_dir
        self.live = live
        self.stage_timeout = stage_timeout
        self.request_timeout = request_timeout
        self.pacing_dir = pacing_dir
        self.python = python or python_executable()
        self.runner = runner
        self.stages = stages
        #: Counted here and carried into `progress.json`: a retry nobody can see is indistinguishable
        #: from a run that never needed one.
        self.spawn_retries = 0
        #: Set when a stage asked the whole run to stop (`run.STOP_RUN_EXIT`: the search stage's
        #: quota gate refused, or an auth, budget, rate-cap or contract error arrived). `run_mass`
        #: reads it between batches through its `stop_of` hook.
        self.stop_reason: str | None = None

    def argv(self, stage: str, batch_id: str) -> list[str]:
        """The argv of one stage, built from what that stage of `run.py` actually accepts.

        `prepare` is the odd one out: it takes the **plan**, and it has no ledger and no `--live`.
        That matters more than it looks - without `--plan` it would prepare the *default* worklist
        batch under a batch id that exists in both plans, and the run would then fetch and judge the
        wrong sites with nothing raising. Found on 2026-09-21 by feeding this argv to the real
        `run.build_parser()`; the unit tests up to then had stubbed `subprocess.run` and only ever
        inspected `fetch`, so they proved the stub, not the driver.
        """
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
            return [*argv, "--plan", str(self.plan)]
        argv += ["--ledger", str(self.ledger)]
        if self.live:
            argv.append("--live")
        if stage == "fetch" and self.pacing_dir is not None:
            # Only `fetch` opens sockets, and with `--jobs N` the batches are separate *processes*, so
            # an in-memory limiter would multiply the per-host rate by N - the politeness a pacer
            # exists to keep. Hence a shared directory of lock files, and hence the driver being the
            # one that names it: the driver is what creates concurrency.
            argv += ["--pacing-dir", str(self.pacing_dir)]
        if stage == "search":
            # A search is always paced (`run.py search` defaults to the shared directory), so the
            # driver can only name the directory, never switch the pace off. Its client carries its
            # own timeout (`minimax_shared.MINIMAX_SEARCH_TIMEOUT`); `--timeout` is not its flag.
            if self.pacing_dir is not None:
                argv += ["--pacing-dir", str(self.pacing_dir)]
            return argv
        if self.request_timeout is not None:
            argv += ["--timeout", f"{self.request_timeout:g}"]
        return argv

    def call(self, stage: str, batch_id: str) -> int:
        """One stage of one batch. The log is opened before the call, so a crash still leaves why.

        A *start* failure (`spawn_failure`) is retried up to `MAX_SPAWN_ATTEMPTS` starts, with one
        line per retry in this stage's own log. Every other failure comes back on its first exit.
        """
        argv = self.argv(stage, batch_id)
        log_path = self.log_dir / f"{batch_id}.{stage}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # the judge's prompts carry non-ASCII
        attempt = 1
        with log_path.open("a", encoding="utf-8") as log:
            while True:
                log.write(f"\n$ {' '.join(argv)}\n")
                log.flush()
                # A byte count, taken after the flush: only what *this* attempt writes is read back,
                # so a report an earlier attempt left in the log is never mistaken for this one's.
                attempted_at = log_path.stat().st_size
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
                log.flush()
                code = done.returncode
                if code == 0 or attempt >= MAX_SPAWN_ATTEMPTS:
                    return code
                written = log_path.read_bytes()[attempted_at:].decode("utf-8", errors="replace")
                if not spawn_failure(code, written):
                    return code
                self.spawn_retries += 1
                log.write(
                    f"\n! {stage} did not start (exit {code}); attempt {attempt + 1} of "
                    f"{MAX_SPAWN_ATTEMPTS} after {SPAWN_RETRY_WAIT_SECONDS:.0f}s\n"
                )
                log.flush()
                time.sleep(SPAWN_RETRY_WAIT_SECONDS)
                attempt += 1

    def batch(self, planned: PlannedBatch) -> tuple[bool, str]:
        """All three stages for one batch. Returns `(ok, detail)`; `detail` says where it stands."""
        for stage in self.stages:
            log = self.log_dir / f"{planned.batch_id}.{stage}.log"
            # The log is appended to across runs; only what this call writes may name its stop.
            start = log.stat().st_size if log.exists() else 0
            code = self.call(stage, planned.batch_id)
            if code == STOP_RUN_EXIT and stage == "search":
                written = log.read_bytes()[start:].decode("utf-8", errors="replace")
                why = report_error(written)
                self.stop_reason = f"{planned.batch_id}: {stage} stopped the run: {why}"
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
    stop_of: Callable[[], str | None] | None = None,
) -> int:
    """Walk the plan. Returns 0 when everything asked for is done, 1 when something stopped it.

    `stop_of` is read before every batch: a reason there stops the run like a ceiling does. The
    driver passes `StageRunner.stop_reason`, so a search stage that met the quota floor, a dead key,
    the budget or the plan's rate cap ends the run instead of feeding the next batch into it.
    """
    queue = list(batches)
    consecutive = 0
    pending: dict[Future[tuple[bool, str]], PlannedBatch] = {}
    # What earlier runs measured, including batches this run will skip as done: a resumed run's
    # progress file must not lose the readings a first run took.
    for planned in batches:
        earlier = search_quota(runner.run_dir, planned.batch_id)
        if earlier is not None:
            progress.quota[planned.batch_id] = earlier
    # What the ledger holds *now* is not this run's spend: the pilot and six recall rounds are in
    # there too. The ceilings are measured from here.
    baseline = Spend.from_ledger(ledger)

    def announce(message: str) -> None:
        print(message, flush=True)
        if on_event is not None:
            on_event(message)

    def guard() -> str | None:
        """Everything that must be true *between* batches, checked before each one is started."""
        reason = budget.stop_reason(Spend.from_ledger(ledger), baseline=baseline)
        if reason:
            return reason
        stop = stop_of() if stop_of is not None else None
        if stop:
            return stop
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
                quota = search_quota(runner.run_dir, planned.batch_id)
                if quota is not None:
                    progress.quota[planned.batch_id] = quota
                if ok:
                    consecutive = 0
                    progress.batches_done += 1
                    announce(f"{planned.batch_id}: done ({detail})")
                else:
                    consecutive += 1
                    progress.batches_failed += 1
                    progress.failed[planned.batch_id] = detail
                    announce(f"{planned.batch_id}: FAILED - {detail} ({consecutive} in a row)")
            progress.spawn_retries = runner.spawn_retries
            progress.in_flight = [b.batch_id for b in pending.values()]
            progress.spend = Spend.from_ledger(ledger).to_dict()
            progress.write(progress_path)

    if progress.stopped is None and stop_of is not None:
        # The batch that asked for the stop may have been the last one started, so no later guard
        # read it; the progress file still has to say why the run ended.
        progress.stopped = stop_of()
    if progress.stopped is None:
        progress.not_reached = []
    progress.spawn_retries = runner.spawn_retries
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
    parser.add_argument(
        "--max-searches",
        type=int,
        default=None,
        help="MiniMax search requests this run may make, retries included (the search lane)",
    )
    parser.add_argument(
        "--stages",
        default=",".join(STAGES),
        choices=sorted(STAGE_SEQUENCES),
        help="prepare,fetch,judge for a snapshot plan; prepare,search,judge for a search plan",
    )
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
    stages = STAGE_SEQUENCES[args.stages]
    searching = "search" in stages
    mismatched = [b.batch_id for b in batches if b.search != searching]
    if mismatched:
        raise PlanError(
            f"--stages {args.stages} does not fit {len(mismatched)} batch(es) of this plan (first: "
            f"{mismatched[0]}): a search plan names rerun_fields and runs prepare,search,judge; a "
            "snapshot plan names none and runs prepare,fetch,judge"
        )

    sites = sum(b.sites for b in batches)
    calls = sum(b.expected_calls for b in batches)
    spend = Spend.from_ledger(ledger)
    digest = None if args.no_digest_guard else package_digest()
    budget = Budget(args.max_calls, args.max_usd, args.max_searches)
    print(f"plan          {plan_path}")
    print(f"run dir       {run_dir}")
    print(f"ledger        {ledger}")
    print(f"stages        {args.stages}")
    print(f"batches       {len(batches)} ({sites} sites)")
    if searching:
        print(f"expected      {calls} calls, one per rerun field")
        print(f"searches      {sum(b.searches for b in batches)} (before retries)")
    else:
        print(f"expected      {sites * FIELDS_PER_SITE} calls at {FIELDS_PER_SITE} per site")
    print(
        f"projected     ${calls * MEASURED_COST_PER_CALL:.4f} "
        f"at the measured ${MEASURED_COST_PER_CALL} per call"
    )
    print(f"budget        {budget.as_text()}")
    print(
        f"already spent {spend.calls} calls, ${spend.cost_usd:.6f} (the ceilings count from here)"
    )
    print(f"jobs          {args.jobs}")
    print(f"live          {args.live}")
    print(f"pace          {DEFAULT_PACING_DIR}")
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
        plan=plan_path,
        run_dir=run_dir,
        ledger=ledger,
        log_dir=log_dir,
        live=True,
        stage_timeout=args.stage_timeout,
        request_timeout=args.request_timeout,
        stages=stages,
    )
    return run_mass(
        batches=batches,
        runner=runner,
        budget=budget,
        ledger=ledger,
        progress=progress,
        progress_path=progress_path,
        failures_before_stop=args.failures_before_stop,
        jobs=args.jobs,
        plan_digest=digest,
        stop_of=lambda: runner.stop_reason,
    )


if __name__ == "__main__":
    sys.exit(main())
