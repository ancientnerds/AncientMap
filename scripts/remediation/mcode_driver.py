"""The driver that took over what Claude Code's Workflow tool did (O22, owner decision 2026-10-03).

`output/remediation/orchestration/*.js` drove a lane by asking a model to run the operator's
commands and report a JSON shape, and by asking one more model per answering batch. The Workflow
tool cannot be resumed here, so this module does the same work in plain Python:

* an **operator step is a command**, run as a subprocess, and the numbers the JS script asked its
  operator model to count are counted here from the files on disk. No model decides whether a
  chunk is finished.
* an **answering batch is one `mcode exec`**, carrying the same agent prompt the JS script used,
  with the answer stamp the run actually answers under (`MiniMax-M3.1-Flash-Preview`, owner
  decision 2026-10-03; before that `claude-sonnet-5-5`).
* after every batch the **tracked tree must be unchanged**. A batch whose agent edited a tracked
  file may have changed the lane's own rules, so it is void and the lane stops (measured
  2026-10-01: an M3.1 run rewrote a check file).
* the **width governor** (O22): start at 2, one more after each window without a rate-limit error,
  halve on the first one, cap by local RAM.
* the **quota stop** (O20): before each batch read the weekly remaining percent and stop at <= 10.
* a **state file** per run, so a stopped lane resumes where it stopped.

Usage:

    python scripts/remediation/mcode_driver.py wd3 --run RUN --handoff DIR [--pilot] [--resume]
    python scripts/remediation/mcode_driver.py wc --runs RUN [RUN ...] --first-batch-base N

A lane's arguments are the arguments of the JS script it replaces.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path("C:/PythonProjects/AncientMap")
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
#: The model id an answer is recorded with (`opus_handoff.answer --model`): exactly as the
#: answering agent's own system prompt names it.
ANSWER_STAMP_MODEL = "MiniMax-M3.1-Flash-Preview"
#: The route `mcode exec --model` takes. A different string from the one above on purpose: the
#: route is not the model id, and an answer must never name the route.
EXEC_MODEL = "minimax/MiniMax-M3.1-Flash-Preview"
EXEC_EFFORT = "max"
#: Owner decision 2026-10-03 (O22): the weekly quota below which the driver stops.
QUOTA_URL = "https://api.minimax.io/v1/token_plan/remains"
QUOTA_KEY_NAME = "LYRA_MINIMAX_API_KEY"
QUOTA_FLOOR_PERCENT = 10.0
WIDTH_START = 2
WIDTH_CAP = 14
HANDOFF = REPO / "output" / "remediation" / "handoff"
RUNS = REPO / "output" / "remediation" / "wc_runner" / "runs"
FIELDS = REPO / "output" / "remediation" / "fields"
ORCHESTRATION = REPO / "output" / "remediation" / "orchestration"
STATE_DIR = REPO / "output" / "remediation" / "mcode_driver"
#: The User-Agent every research agent of this remediation sends (no personal data).
USER_AGENT = "AncientMapRemediation/1.0 (research; https://ancientnerds.com)"

EFFORTS = {"max", "high", "medium", "low"}


class DriverError(RuntimeError):
    """The driver refuses to continue: a lane stops on this, it is never worked around."""


# ------------------------------------------------------------------------------------ subprocesses
def run_git(repo: Path, *args: str, check: bool = True) -> str:
    """One git command in `repo`, its stdout. `check=False` for the calls whose exit code is the
    answer (a `status` is 0 either way)."""
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False
    )
    if check and done.returncode != 0:
        raise DriverError(f"git {' '.join(args)} in {repo} failed: {done.stderr.strip()[:400]}")
    return done.stdout


def tracked_changes(repo: Path) -> str:
    """`git status --porcelain` of **tracked** files only. A lane writes its own untracked scratch
    (the brief names a scratch directory), so untracked paths are not drift; a modified tracked
    file is.

    Only the trailing newline is removed: a porcelain line starts with a two-character status and
    a space, and stripping the line would move the path by one.
    """
    return run_git(repo, "status", "--porcelain", "--untracked-files=no", check=False).rstrip()


def free_ram_gb() -> float:
    """Free RAM in GB, for the width cap. 0.0 when it cannot be read: the cap then does not bind,
    which is the safe direction (too narrow a cap would stall a lane on a healthy machine)."""
    try:
        info = os.popen(  # noqa: S605 - a fixed command, no interpolation
            "wmic OS get FreePhysicalMemory /value"
        ).read()
    except OSError:
        return 0.0
    for line in info.splitlines():
        if line.lower().startswith("freephysicalmemory="):
            return int(line.split("=", 1)[1].strip()) / 1024 / 1024
    return 0.0


# ------------------------------------------------------------------------------------ one mcode exec
@dataclass(frozen=True)
class ExecResult:
    """What one `mcode exec` left behind: its exit code, the last stdout line parsed as JSON, the
    raw streams, and where its diagnostics were written. The diagnostics stay on disk: a run that
    has to be explained a week later is read from them, not from a summary."""

    exit_code: int
    ok: bool
    payload: dict[str, Any]
    stdout: str
    stderr: str
    diagnostics: Path
    tree_changed: tuple[str, ...] = ()

    @property
    def rate_limited(self) -> bool:
        """Whether this failure is the one the width governor reacts to: a rate limit, not any
        other refusal. Matched on the code and on the text, because a gateway may answer 200 with a
        rate-limit body."""
        text = f"{self.stdout}\n{self.stderr}".lower()
        return (
            self.exit_code == 429
            or "429" in text
            or "rate limit" in text
            or "too many requests" in text
        )

    @property
    def tree_clean(self) -> bool:
        return not self.tree_changed


class McodeRunner:
    """One `mcode exec` at a time. `binary` is the command to call, so a test passes a fake."""

    def __init__(
        self,
        *,
        binary: str | Path = "mcode",
        repo: Path = REPO,
        diagnostics: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.binary = str(binary)
        self.repo = Path(repo)
        self.diagnostics = Path(diagnostics) if diagnostics else STATE_DIR / "diagnostics"
        #: Added to this process's environment, never a replacement of it: `mcode` needs PATH and
        #: its own configuration, and a replaced environment would run it with neither.
        self.extra_env = dict(env) if env else {}

    def run(
        self,
        prompt: str,
        *,
        label: str,
        timeout: int,
        max_steps: int,
        effort: str = EXEC_EFFORT,
    ) -> ExecResult:
        """Run one batch. The tracked tree is sampled before and after, so the result carries what
        the batch changed - or nothing, which is the normal case."""
        if effort not in EFFORTS:
            raise DriverError(f"effort {effort!r} is not one of {sorted(EFFORTS)}")
        target = self.diagnostics / label
        target.mkdir(parents=True, exist_ok=True)
        before = tracked_changes(self.repo)
        argv = [
            self.binary,
            "exec",
            "--cwd",
            str(self.repo),
            "--model",
            EXEC_MODEL,
            "--effort",
            effort,
            "--permission",
            "full",
            "--timeout",
            str(timeout),
            "--max-steps",
            str(max_steps),
            "--output-format",
            "json",
            "--diagnostics-dir",
            str(target),
            "--label",
            label,
            "--prompt",
            prompt,
        ]
        try:
            done = subprocess.run(
                argv,
                cwd=self.repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 120,
                env={**os.environ, **self.extra_env} if self.extra_env else None,
                check=False,
            )
            code, out, err = done.returncode, done.stdout, done.stderr
        except FileNotFoundError as exc:
            raise DriverError(f"{self.binary} is not on PATH: {exc}") from exc
        (target / "stdout.txt").write_text(out, encoding="utf-8")
        (target / "stderr.txt").write_text(err, encoding="utf-8")
        changed = _changed_since(before, tracked_changes(self.repo))
        payload = _last_json_line(out)
        return ExecResult(
            exit_code=code,
            ok=code == 0 and bool(payload.get("ok", True)),
            payload=payload,
            stdout=out,
            stderr=err,
            diagnostics=target,
            tree_changed=changed,
        )

    def voids(self, result: ExecResult) -> bool:
        """Whether this batch may not be counted: it failed, or it edited a tracked file."""
        return not result.ok or not result.tree_clean


def _last_json_line(stdout: str) -> dict[str, Any]:
    """The last stdout line that is a JSON object: the exec's own result, after whatever the agent
    printed before it. A line that is not JSON is not the result, so it is skipped, not guessed."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _changed_since(before: str, after: str) -> tuple[str, ...]:
    """The tracked paths that are dirty now and were not before: what one batch changed."""
    was = {_porcelain_path(line) for line in before.splitlines() if line.strip()}
    now = {_porcelain_path(line) for line in after.splitlines() if line.strip()}
    return tuple(sorted(now - was))


def _porcelain_path(line: str) -> str:
    """The path of a `git status --porcelain` line: two status characters, a space, the path."""
    return line[3:].rstrip()


# ------------------------------------------------------------------------------------ the width
@dataclass
class Width:
    """The concurrency governor (O22). It only ever answers "how many at once"."""

    start: int = WIDTH_START
    cap: int = WIDTH_CAP
    ram_cap: Callable[[], float] = free_ram_gb
    value: int = field(default=0)
    rate_limits: int = 0

    def __post_init__(self) -> None:
        if self.value == 0:
            self.value = self.start

    @classmethod
    def from_start(cls, start: int = WIDTH_START) -> Width:
        return cls(start=start)

    def next_window(self) -> int:
        return self.value

    def window_clean(self) -> None:
        """One more concurrent run after a window without a rate-limit error, never above the cap
        or above what the machine has free."""
        limit = min(self.cap, max(1, int(self.ram_cap())))
        self.value = min(self.value + 1, limit)

    def rate_limited(self) -> None:
        self.rate_limits += 1
        self.value = max(1, self.value // 2)

    def waited(self) -> None:
        """A limit that did not stop us: wait before the next window instead of growing."""
        time.sleep(30)


# ------------------------------------------------------------------------------------ the quota
def _env_value(name: str, env_file: Path) -> str:
    """One value of the repo's `.env`. Read, never printed, never logged."""
    if not env_file.exists():
        raise DriverError(f"{name} is not set: {env_file} is missing")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise DriverError(f"{name} is not set in {env_file}")


def quota_remaining(
    *,
    env_file: Path = REPO / ".env",
    fetch: Callable[..., dict[str, Any]] | None = None,
) -> float:
    """The weekly quota left in percent. The key travels in the Authorization header and nowhere
    else; this function never returns or logs it."""
    key = _env_value(QUOTA_KEY_NAME, env_file)
    call = fetch or _http_json
    payload = call(QUOTA_URL, headers={"Authorization": key}, timeout=30.0)
    value = payload.get("current_weekly_remaining_percent")
    if not isinstance(value, (int, float)):
        raise DriverError(f"{QUOTA_URL} returned no current_weekly_remaining_percent: {payload!r}")
    return float(value)


def quota_exhausted(percent: float, floor: float = QUOTA_FLOOR_PERCENT) -> bool:
    """Owner decision 2026-10-03 (O20): stop at 10 percent or below, resume after the reset."""
    return percent <= floor


def _http_json(url: str, *, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=dict(headers))  # noqa: S310 - a fixed https URL
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DriverError(f"{url} did not answer: {exc}") from exc


# ------------------------------------------------------------------------------------ the state file
@dataclass
class State:
    """A lane's own state file, so a stopped lane resumes instead of starting over. A file of
    another lane or another run is never reused: it is a different lane's history."""

    path: Path
    lane: str
    run: str
    handoff: str
    data: dict[str, Any] = field(default_factory=dict)

    def __init__(self, path: Path, *, lane: str, run: str, handoff: str) -> None:
        self.path = Path(path)
        self.lane, self.run, self.handoff = lane, run, handoff
        self.data = {}
        if self.path.exists():
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            same = (stored.get("lane"), stored.get("run"), stored.get("handoff")) == (
                lane,
                run,
                handoff,
            )
            self.data = stored.get("data", {}) if same else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"lane": self.lane, "run": self.run, "handoff": self.handoff, "data": self.data}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.path)


# ------------------------------------------------------------------------------------ the answer prompt
_OPERATOR_RULES = (
    "Never search the file system: no find over /, output/ or any large directory - open exactly "
    "the paths named here (ls of one named directory is fine). Never pipe a command into head or "
    "tail -n (on Windows the producer keeps running after head exits and piles up). Modify no "
    "file outside the scratch directory named here. No personal data in any web request; "
    f"User-Agent '{USER_AGENT}'. If web search is exhausted, search via curl (Wikipedia/Wikidata "
    "APIs, https://html.duckduckgo.com/html/?q=..., Nominatim)."
)


def answer_prompt(
    *,
    lane: str,
    run: str,
    batch: str,
    repo: str = str(REPO),
    python: str = str(PYTHON),
    brief: str = "brief",
    brief_command: str = "",
) -> str:
    """The answering agent's whole instruction, from the JS script of the same lane with the model
    strings replaced. The brief command is the agent's full instruction; everything after it is how
    to obey it."""
    command = brief_command or f"{repo} && PYTHONIOENCODING=utf-8 {python} {lane}/cli.py {brief}"
    return (
        f"You are a fresh research agent of lane {lane.upper()} of the AncientMap remediation, "
        f"run {run}, batch {batch} ({brief}). You worked on no other batch and judged no other "
        f"site of this run. Work in {repo} (cd there). Run and read it completely - it is your "
        f"full instruction:\n  {command}\n"
        f"Follow it exactly: research on the web yourself, quote verbatim from the pages you cite "
        f"(reputable, independent sources; never ancientnerds.com, AI content farms or mirrors of "
        f"the site's own text), check every answer with the brief's own check command until it "
        f"passes, then record it with opus_handoff.py answer as the brief says (write-once; skip "
        f"labels already recorded).\n"
        f"Scratch files only in {run}-{brief}-scratch/{batch}/ . {_OPERATOR_RULES}\n"
        f"Record every answer with --model {ANSWER_STAMP_MODEL} (the model you run as). "
        f'Final answer (one line): "{batch}: N recorded, M skipped, K failed (reasons)".'
    )


# ------------------------------------------------------------------------------------ the WD3 lane
@dataclass(frozen=True)
class Plan:
    """What the operator step of a lane decided, before anything is run: the batches to answer and
    the command that reported them. No model is involved in this decision."""

    batches: tuple[str, ...]
    exported: bool
    export_command: tuple[str, ...]
    validate_dir: Path
    round_name: str = "r0"

    def batch_names_ok(self, names: Sequence[str]) -> bool:
        """Whether the batch names on disk are the ones the lane's own naming scheme makes, so a
        directory that holds something else is refused instead of half-driven."""
        return tuple(names) == batch_ids(self.round_name, len(self.batches))


def batch_folders(handoff: Path) -> tuple[str, ...]:
    """The batch folders of a handoff directory, in sorted order: every subdirectory that holds a
    MANIFEST.jsonl. Counted here, not asked of a model (2026-10-01: 327 ids came back as one
    string "wd3-r0-b0001 through wd3-r0-b0327")."""
    if not handoff.is_dir():
        return ()
    return tuple(
        sorted(p.name for p in handoff.iterdir() if p.is_dir() and (p / "MANIFEST.jsonl").exists())
    )


def batch_ids(round_name: str, count: int) -> tuple[str, ...]:
    return tuple(f"wd3-{round_name}-b{n:04d}" for n in range(1, count + 1))


def plan_wd3(*, run: Path, handoff: Path, resume: bool) -> Plan:
    """The WD3 pool's first operator step. With `resume` the round was exported before, so the step
    counts what is there; without it, the step exports. The export command is returned rather than
    run, so the caller runs exactly one thing per step."""
    fields = str(FIELDS / "handoff.py")
    export = (
        str(PYTHON),
        fields,
        "export",
        "--run",
        str(run),
        "--handoff",
        f"{handoff}-r0",
    )
    if not resume:
        return Plan((), True, export, Path(f"{handoff}-r0"))
    made = batch_folders(Path(f"{handoff}-r0"))
    return Plan(made, False, export, Path(f"{handoff}-r0"))


def check_batch_names(plan: Plan, names: Sequence[str]) -> bool:
    """`plan.batch_names_ok`, named for the caller that checks an externally built id list."""
    return plan.batch_names_ok(names)


# ------------------------------------------------------------------------------------ the driver loop
@dataclass
class BatchOutcome:
    label: str
    ok: bool
    void: bool
    rate_limited: bool
    exit_code: int
    diagnostics: str
    tree_changed: tuple[str, ...] = ()


def answer_all(
    labels: Sequence[str],
    *,
    prompt_for: Callable[[str], str],
    runner: McodeRunner,
    width: Width,
    state: State,
    timeout: int,
    max_steps: int,
    effort: str = EXEC_EFFORT,
    quota_check: Callable[[], bool] | None = None,
    on_void: Callable[[BatchOutcome], None] | None = None,
) -> list[BatchOutcome]:
    """Answer every batch label, `width` at a time, and stop the lane the moment a batch is void.

    The void rule is the point of the whole guard: a batch whose agent edited a tracked file may
    have changed the lane's own rules, so its answers are not counted and the next batch is not
    started. Every batch's outcome is written to the state file before the next one starts, so a
    stop loses at most the batch in flight.
    """
    done: set[str] = set(state.get("answered", []))
    outcomes: list[BatchOutcome] = []
    remaining = [label for label in labels if label not in done]
    with ThreadPoolExecutor(max_workers=max(1, width.next_window())) as pool:
        futures = {}
        for label in remaining:
            if quota_check is not None and quota_check():
                outcomes.append(BatchOutcome(label, False, True, False, 0, "", ("quota",)))
                break
            width.rate_limits = width.rate_limits
            futures[label] = pool.submit(
                runner.run,
                prompt_for(label),
                label=label,
                timeout=timeout,
                max_steps=max_steps,
                effort=effort,
            )
        for label, future in futures.items():
            result = future.result()
            void = runner.voids(result)
            outcome = BatchOutcome(
                label=label,
                ok=not void,
                void=void,
                rate_limited=result.rate_limited,
                exit_code=result.exit_code,
                diagnostics=str(result.diagnostics),
                tree_changed=result.tree_changed,
            )
            outcomes.append(outcome)
            state.put("outcomes", {**(state.get("outcomes", {})), label: outcome.__dict__})
            if not void:
                done.add(label)
                state.put("answered", sorted(done))
            if result.rate_limited:
                width.rate_limited()
            if void:
                if on_void is not None:
                    on_void(outcome)
                break
    if outcomes and all(o.ok for o in outcomes) and not any(o.rate_limited for o in outcomes):
        width.window_clean()
    return outcomes


# ------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcode-driver", description=__doc__.splitlines()[0])
    lanes = parser.add_subparsers(dest="lane", required=True)

    wd3 = lanes.add_parser("wd3", help="lane WD3 (structured-field fill): the JS pool, in Python")
    wd3.add_argument("--run", required=True, type=Path)
    wd3.add_argument("--handoff", required=True)
    wd3.add_argument("--pilot", action="store_true")
    wd3.add_argument("--resume", action="store_true")
    wd3.add_argument("--width", type=int, default=WIDTH_START)
    wd3.add_argument("--timeout", type=int, default=3600)
    wd3.add_argument("--max-steps", type=int, default=200)
    wd3.add_argument("--dry-run", action="store_true", help="report the plan, answer nothing")

    args = parser.parse_args(list(argv) if argv is not None else None)
    plan = plan_wd3(run=args.run, handoff=Path(args.handoff), resume=args.resume)
    if not plan.batches:
        print(json.dumps({"batches": [], "exported": plan.exported, "note": "nothing exported"}))
        return 1
    if not check_batch_names(
        plan, [f"wd3-{plan.round_name}-b{n:04d}" for n in range(1, len(plan.batches) + 1)]
    ):
        print(
            json.dumps(
                {"ok": False, "error": f"batch names in {plan.validate_dir} are not the lane's"}
            )
        )
        return 1
    if args.dry_run:
        print(json.dumps({"batches": list(plan.batches), "exported": plan.exported}, indent=1))
        return 0

    state = State(
        STATE_DIR / f"wd3-{args.run.name}.json",
        lane="wd3",
        run=str(args.run),
        handoff=args.handoff,
    )
    width = Width.from_start(args.width)
    runner = McodeRunner()

    def prompt(label: str) -> str:
        return answer_prompt(
            lane="fields",
            run=str(args.run),
            batch=label,
            brief_command=(
                f"cd {REPO} && PYTHONIOENCODING=utf-8 {PYTHON} {FIELDS / 'handoff.py'} brief "
                f"--run {args.run} --handoff {plan.validate_dir} --batch-id {label}"
            ),
        )

    try:
        outcomes = answer_all(
            plan.batches,
            prompt_for=prompt,
            runner=runner,
            width=width,
            state=state,
            timeout=args.timeout,
            max_steps=args.max_steps,
            quota_check=lambda: quota_exhausted(quota_remaining()),
            on_void=lambda outcome: print(
                json.dumps(
                    {
                        "stopped": "void batch",
                        "label": outcome.label,
                        "tree_changed": list(outcome.tree_changed),
                    }
                ),
                file=sys.stderr,
            ),
        )
    except DriverError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "answered": sum(1 for o in outcomes if o.ok),
                "outcomes": [o.__dict__ for o in outcomes],
            },
            indent=1,
            default=list,
        )
    )
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
