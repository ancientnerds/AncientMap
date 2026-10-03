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
    key_name: str = QUOTA_KEY_NAME,
) -> float:
    """The weekly quota left in percent. The key travels in the Authorization header and nowhere
    else; this function never returns or logs it.

    The key is the **MiniMax platform secret** of `api.minimax.io`, which is not the key the Lyra
    pipeline uses: `LYRA_MINIMAX_API_KEY` authenticates the Anthropic-compatible route and is
    refused here with `login fail` (measured 2026-10-03). So the variable name is a parameter, and
    the refusal names the variable to set - never its value.
    """
    key = _env_value(key_name, env_file)
    call = fetch or _http_json
    payload = call(QUOTA_URL, headers={"Authorization": key}, timeout=30.0)
    base = payload.get("base_resp") or {}
    if base.get("status_code") not in (None, 0):
        raise DriverError(
            f"{QUOTA_URL} refused the key in {key_name}: {base.get('status_msg', '')[:200]} "
            f"(status {base.get('status_code')}). That variable must hold the MiniMax platform "
            "secret of api.minimax.io, not the Anthropic-compatible key the Lyra pipeline uses. "
            "The driver stops here rather than run without a quota check."
        )
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


# ------------------------------------------------------------------------------------ the WC lane
@dataclass(frozen=True)
class WcPlan:
    """The one step lane WC takes next for one run, read off the run's own files.

    `answer_batches` is empty until a `validate` run named the missing ones: which batches still
    need an agent is the validator's answer, not this function's guess.
    """

    ok: bool
    stage: str
    command: tuple[str, ...] = ()
    answer_handoff: Path | None = None
    answer_brief: str = ""
    answer_batches: tuple[str, ...] = ()
    done: bool = False
    note: str = ""
    #: The refusal of `command` that means "there is nothing here to do", and the stage to continue
    #: at when it happens. `wc-continue.js` read this out of the command's own output; the driver
    #: cannot re-read a command it already ran, so it remembers the refusal in the state file.
    refusal_advances: str = ""


def _wc_cli(command: str, *args: str) -> tuple[str, ...]:
    return (str(PYTHON), str(REPO / "scripts" / "remediation" / "wc" / "cli.py"), command, *args)


def _reask_asks(run: Path) -> bool:
    """Whether the re-ask file of round 1 actually asks something. A run with no `REASK.json`, or an
    empty one, is past this stage - the JS script skipped to verification on the same rule."""
    path = run / "round-1" / "REASK.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True  # unreadable: ask the questions again rather than skip them
    if isinstance(data, list):
        return bool(data)
    if isinstance(data, dict):
        return any(
            bool(value) for key, value in data.items() if key in {"reask", "sentences", "ask"}
        ) or bool(data)
    return True


def _verified_rounds(run: Path) -> set[int]:
    """The verification rounds already imported.

    `wc-continue.js` looked for `R/VERIFIED.jsonl`; the runs on disk (measured 2026-10-03) hold
    `verify/round-<n>/VERIFIED.jsonl`, one file per round, every line naming its own `round`. Both
    are read: a round counts as imported when a line of that round exists anywhere under `verify/`,
    so neither a missing file nor a file of the wrong round can pass for an import.
    """
    rounds: set[int] = set()
    for path in sorted((run / "verify").glob("round-*/VERIFIED.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            number = value.get("round") if isinstance(value, dict) else None
            if isinstance(number, int):
                rounds.add(number)
    return rounds


def wc_next_step(
    run: Path,
    handoff_root: Path,
    *,
    first_batch: int,
    state: State | None = None,
) -> WcPlan:
    """Lane WC's state machine, in the order `wc-continue.js` laid out: built, round 1, re-ask,
    verification round 1, verification round 2, build. The files on disk decide; no model does."""
    run = Path(run)
    name = run.name
    handoff_r1 = handoff_root / f"wc-{name}-r1"
    handoff_r2 = handoff_root / f"wc-{name}-r2"
    handoff_v1 = handoff_root / f"wc-{name}-verify"
    handoff_v2 = handoff_root / f"wc-{name}-verify2"
    refused = set(state.get("refused", [])) if state else set()

    if (run / "WC4.jsonl").exists():
        return WcPlan(True, "built", done=True, note="WC4.jsonl exists: the run is built")

    # 1. round 1: validate, answer what is missing, import when clean
    if not (run / "round-1" / "ANSWERS.jsonl").exists():
        if not handoff_r1.is_dir():
            return WcPlan(
                False,
                "round-1",
                note=f"{handoff_r1} does not exist: nothing was exported, or the "
                "export is gone; the driver does not invent the questions",
            )
        return WcPlan(True, "round-1", answer_handoff=handoff_r1, answer_brief="brief")

    # 2. the re-ask, once
    if _reask_asks(run) and not (run / "round-2" / "ANSWERS.jsonl").exists():
        if not handoff_r2.is_dir():
            return WcPlan(
                True,
                "reask",
                command=_wc_cli(
                    "export-reask", "--run-dir", str(run), "--handoff", str(handoff_r2)
                ),
            )
        return WcPlan(True, "reask", answer_handoff=handoff_r2, answer_brief="brief")

    # 3. and 4. the two verification rounds; round 2 only when round 1 is imported
    imported = _verified_rounds(run)
    for number, handoff in ((1, handoff_v1), (2, handoff_v2)):
        stage = f"verify-{number}"
        if number == 2 and 1 not in imported:
            break
        if stage in refused:
            continue
        if not (run / "verify" / f"round-{number}" / "ROUND.json").exists():
            return WcPlan(
                True,
                stage,
                command=_wc_cli("verify-export", "--run-dir", str(run), "--handoff", str(handoff)),
                refusal_advances=stage,
            )
        if number not in imported:
            if not handoff.is_dir():
                return WcPlan(
                    False, stage, note=f"{handoff} does not exist: the round was not exported"
                )
            return WcPlan(True, stage, answer_handoff=handoff, answer_brief="verify-brief")

    # 5. the build
    return WcPlan(
        True,
        "build",
        command=_wc_cli("build", "--run-dir", str(run), "--first-batch", str(first_batch)),
    )


def wc_answer_prompt(
    *, run: Path, handoff: Path, batch: str, brief: str = "brief", repo: str = str(REPO)
) -> str:
    """One WC answering batch's instruction, from `wc-continue.js` with the model strings replaced."""
    return answer_prompt(
        lane="wc",
        run=str(run),
        batch=batch,
        repo=repo,
        brief=brief,
        brief_command=(
            f"cd {repo} && PYTHONIOENCODING=utf-8 {PYTHON} {REPO / 'scripts' / 'remediation' / 'wc' / 'cli.py'} "
            f"{brief} --run-dir {run} --handoff {handoff} --batch-id {batch}"
        ),
    )


@dataclass
class StepGuard:
    """Stops a run that stops moving. The JS script gave up after three identical steps; the
    counter is that one, and it resets the moment a step differs."""

    limit: int = 3
    counts: dict[str, int] = field(default_factory=dict)

    def seen(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def stopped(self, key: str) -> bool:
        return self.counts.get(key, 0) >= self.limit


# ------------------------------------------------------------------------------------ the operator commands
@dataclass(frozen=True)
class Command:
    """One operator command: the argv, its exit code and its own JSON output. A command that
    refuses is not retried by the driver and not worked around; its output is what stops the lane."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def json(self) -> dict[str, Any]:
        return _last_json_line(self.stdout)

    def refuses_with(self, phrase: str) -> bool:
        return phrase.lower() in f"{self.stdout}\n{self.stderr}".lower()


def run_operator(argv: Sequence[str], *, repo: Path = REPO, timeout: int = 3600) -> Command:
    """Run one lane command. Its stdout is the payload, so a refusal is read from the command's own
    output and not from a wrapper's status."""
    try:
        done = subprocess.run(
            list(argv),
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DriverError(f"{argv[0]} is not there: {exc}") from exc
    return Command(tuple(argv), done.returncode, done.stdout, done.stderr)


@dataclass(frozen=True)
class Validation:
    """What `opus_handoff.py validate` said about one handoff directory."""

    ok: bool
    missing: tuple[str, ...]  #: the batch ids that still need an agent, sorted
    missing_count: int
    problems: str = ""


def validate_handoff(handoff: Path, *, repo: Path = REPO) -> Validation:
    """Validate one exported round. `validate` exits 1 while answers are missing, which is the normal
    state of a round in progress, so the exit code is not the verdict - the JSON is."""
    command = run_operator(
        (
            str(PYTHON),
            str(REPO / "scripts" / "remediation" / "opus_handoff.py"),
            "validate",
            "--dir",
            str(handoff),
        ),
        repo=repo,
    )
    payload = command.json
    if not payload:
        raise DriverError(f"validate --dir {handoff} printed no JSON: {command.stderr[:400]}")
    missing = payload.get("missing") or []
    problems = {
        key: payload.get(key) for key in ("stale", "malformed", "orphans") if payload.get(key)
    }
    return Validation(
        ok=not problems,
        missing=tuple(sorted({row.get("batch_id", "") for row in missing if row.get("batch_id")})),
        missing_count=len(missing),
        problems=json.dumps(problems, ensure_ascii=False) if problems else "",
    )


# ------------------------------------------------------------------------------------ driving WC
NOTHING_TO_VERIFY = "nothing to verify"


def drive_wc_run(
    run: Path,
    handoff_root: Path,
    *,
    first_batch: int,
    state: State,
    runner: McodeRunner,
    width: Width,
    timeout: int,
    max_steps: int,
    steps: int = 16,
    quota_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Drive one WC run from wherever its files say it stands until it is built, or until it stops.

    One thing happens per iteration, the JS script's rule: validate, answer what is missing, import
    when clean, export the next round, build last. A step that changes nothing three times in a row
    stops the run rather than looping.
    """
    guard = StepGuard()
    log: list[dict[str, Any]] = []
    for _ in range(steps):
        plan = wc_next_step(run, handoff_root, first_batch=first_batch, state=state)
        entry: dict[str, Any] = {"stage": plan.stage, "ok": plan.ok}
        if not plan.ok:
            log.append({**entry, "stopped": plan.note})
            return {"run": run.name, "steps": log, "stopped": plan.note}
        if plan.done:
            return {"run": run.name, "steps": log, "built": True, "note": plan.note}
        key = f"stage={plan.stage} ran={plan.command[2] if plan.command else 'answer'}"
        guard.seen(key)
        if guard.stopped(key):
            log.append({**entry, "stopped": f"no progress after {guard.limit} identical steps"})
            return {"run": run.name, "steps": log, "stopped": f"no progress at {plan.stage}"}

        if plan.answer_handoff is not None:
            check = validate_handoff(plan.answer_handoff)
            if not check.ok:
                log.append({**entry, "stopped": f"validate refused: {check.problems}"})
                return {"run": run.name, "steps": log, "stopped": check.problems}
            if not check.missing:
                # nothing missing: the import is the next step's business, and the next plan will see
                # the files it left behind
                log.append({**entry, "validate": "clean, nothing missing"})
                import_argv = _wc_cli(
                    "import" if plan.answer_brief == "brief" else "verify-import",
                    "--run-dir",
                    str(run),
                    "--handoff",
                    str(plan.answer_handoff),
                )
                done = run_operator(import_argv)
                if not done.ok:
                    log.append(
                        {**entry, "stopped": f"{import_argv[2]} failed: {done.stderr[:200]}"}
                    )
                    return {"run": run.name, "steps": log, "stopped": f"{import_argv[2]} failed"}
                continue
            outcomes = answer_all(
                check.missing,
                prompt_for=lambda batch, h=plan.answer_handoff, b=plan.answer_brief: (
                    wc_answer_prompt(run=run, handoff=h, batch=batch, brief=b)
                ),
                runner=runner,
                width=width,
                state=state,
                timeout=timeout,
                max_steps=max_steps,
                quota_check=quota_check,
            )
            entry["answered"] = sum(1 for o in outcomes if o.ok)
            entry["void"] = [o.label for o in outcomes if o.void]
            log.append(entry)
            if entry["void"]:
                return {"run": run.name, "steps": log, "stopped": f"void batch {entry['void'][0]}"}
            continue

        done = run_operator(plan.command)
        entry["ran"] = plan.command[2]
        if not done.ok and plan.refusal_advances and done.refuses_with(NOTHING_TO_VERIFY):
            state.put("refused", sorted({*state.get("refused", []), plan.refusal_advances}))
            entry["refused"] = NOTHING_TO_VERIFY
            log.append(entry)
            continue
        if not done.ok:
            entry["stopped"] = f"{plan.command[2]} exited {done.exit_code}: {done.stderr[:200]}"
            log.append(entry)
            return {"run": run.name, "steps": log, "stopped": entry["stopped"]}
        entry["summary"] = done.json
        log.append(entry)
    return {"run": run.name, "steps": log, "stopped": f"step guard reached ({steps} steps)"}


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


def _quota_check() -> Callable[[], bool]:
    """The weekly quota stop, read once per batch. The key is read inside `quota_remaining`; this
    function never holds or prints it."""

    def exceeded() -> bool:
        return quota_exhausted(quota_remaining())

    return exceeded


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
    wd3.add_argument("--no-quota-check", action="store_true", help="skip the weekly quota stop")
    wd3.add_argument("--dry-run", action="store_true", help="report the plan, answer nothing")

    wc = lanes.add_parser("wc", help="lane WC (sentence check): the JS state machine, in Python")
    wc.add_argument("--runs", required=True, nargs="+", help="the run directory names under runs/")
    wc.add_argument("--runs-root", type=Path, default=RUNS)
    wc.add_argument("--handoff-root", type=Path, default=HANDOFF)
    wc.add_argument(
        "--first-batch-base",
        type=int,
        required=True,
        help="the first WC4 batch number of the first run; each later run adds 100",
    )
    wc.add_argument(
        "--first-batch-by-run",
        default="",
        help='JSON {"<run>": N} for a run whose name does not end in its chunk number',
    )
    wc.add_argument("--width", type=int, default=WIDTH_START)
    wc.add_argument("--timeout", type=int, default=3600)
    wc.add_argument("--max-steps", type=int, default=200)
    wc.add_argument("--steps", type=int, default=16)
    wc.add_argument("--no-quota-check", action="store_true", help="skip the weekly quota stop")
    wc.add_argument(
        "--dry-run", action="store_true", help="report the next step per run, do nothing"
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.lane == "wc":
        return _main_wc(args)
    return _main_wd3(args)


def _first_batch_for(args: Any, run: str, index: int) -> int:
    """A run whose name does not end in its chunk number (a site list or a WN run) needs its own
    first write batch; the JS script took it from `--firstBatchByRun`."""
    if args.first_batch_by_run:
        given = json.loads(args.first_batch_by_run)
        if run in given:
            return int(given[run])
    return args.first_batch_base + 100 * index


def _main_wc(args: Any) -> int:
    width = Width.from_start(args.width)
    runner = McodeRunner()
    quota = None if args.no_quota_check else _quota_check()
    results: list[dict[str, Any]] = []
    for index, run in enumerate(args.runs):
        run_dir = Path(args.runs_root) / run
        state = State(
            STATE_DIR / f"wc-{run}.json", lane="wc", run=run, handoff=str(args.handoff_root)
        )
        if args.dry_run:
            step = wc_next_step(
                run_dir,
                Path(args.handoff_root),
                first_batch=_first_batch_for(args, run, index),
                state=state,
            )
            results.append(
                {
                    "run": run,
                    "stage": step.stage,
                    "ok": step.ok,
                    "done": step.done,
                    "command": list(step.command),
                    "answer_handoff": str(step.answer_handoff or ""),
                    "note": step.note,
                }
            )
            continue
        try:
            results.append(
                drive_wc_run(
                    run_dir,
                    Path(args.handoff_root),
                    first_batch=_first_batch_for(args, run, index),
                    state=state,
                    runner=runner,
                    width=width,
                    timeout=args.timeout,
                    max_steps=args.max_steps,
                    steps=args.steps,
                    quota_check=quota,
                )
            )
        except DriverError as exc:
            print(json.dumps({"run": run, "stopped": str(exc)}), file=sys.stderr)
            return 2
    print(json.dumps({"runs": results}, indent=1, default=list))
    return 0 if all(r.get("built") or "stopped" not in r for r in results) else 1


def _main_wd3(args: Any) -> int:
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
            quota_check=None if args.no_quota_check else _quota_check(),
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
