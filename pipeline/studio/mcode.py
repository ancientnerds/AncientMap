"""One `mcode exec` run per judgement: the harness the studio runs on.

Owner decision 2026-10-03: MiniMax Code (`mcode`, model `MiniMax-M3.1-Flash-Preview`,
M Plan login) replaces Claude Code in this project. This module is the only place that
shells out to it. A judgement is never made in this process: a run is a prompt in, one
exec JSON out, and the caller decides what to do with the model's own answer file.

    run = mcode.exec("Answer ...", cwd=repo)
    run.model        # the model the exec JSON names, the only model a stamp may carry
    run.run_id       # the run a stamp names next to the model

Four owner decisions shape it:
- O23: every run on `--effort max`.
- O22: as much parallelism as possible without a 429. `Pool` starts at 2, rises by one
  per clean wave, halves on the first rate-limited run and never exceeds 14 (the local
  RAM ceiling of docs/procedures/PROJECT_LESSONS.md).
- O20: a batch stops when the weekly plan is at 10 % or less (`/v1/token_plan/remains`,
  through Lyra's `probe_minimax_quota`, which reads the key from the repo `.env`; this
  module never prints it) and resumes after the reset.
- The "no tracked file changed" guard of the plan: after a batch, a changed tracked file
  means a run wrote into the repository instead of its answer file, and the batch stops.

`mcode exec --output-schema` does not work with M3.1, so the model writes its answer to a
file and a validator script decides whether it counts; the driver in
`pipeline/studio/mcode_checks.py` builds both.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.lyra.minimax_shared import probe_minimax_quota
from pipeline.studio.errors import StudioError
from pipeline.utils import git_env

#: The model every studio judgement runs on, exactly as the exec JSON names it.
MODEL = "MiniMax-M3.1-Flash-Preview"
#: What `mcode exec --model` takes.
MODEL_REF = f"minimax/{MODEL}"
#: The tool, as a paper's writer record and a ledger row name it.
TOOL = "mcode"
EFFORT = "max"  # O23
PERMISSION = "full"
#: A verifier reads several source texts, greps them and writes a file; 30 minutes is the
#: smallest time that does not cut a long source read in half.
TIMEOUT = "30m"
#: O22: the first wave, and the ceiling the local RAM sets.
START_CONCURRENCY = 2
MAX_CONCURRENCY = 14
#: O20: a batch stops at or below this weekly remaining percent.
WEEKLY_STOP_PERCENT = 10.0
#: After a rate-limited wave: the wait before the next one, and its ceiling.
PAUSE_AFTER_429_S = 20.0
PAUSE_MAX_S = 300.0
#: Where `mcode` lives, overridable for a machine that installed it elsewhere.
EXE_ENV = "MCODE_EXE"
#: What the driver waits beyond the CLI's own `--timeout` before it gives the run up: the
#: CLI still has to shut down, print its JSON and exit.
GRACE_S = 120.0
#: How long the driver waits for a killed run's tree to go, before it leaves the corpse to
#: the OS. A run whose thread sits in a hung socket never becomes reapable, and the batch
#: must not wait for it (see `exec`).
KILL_GRACE_S = 20.0
#: Only a non-zero exit says "rate limited": a check that reads a page quoting "HTTP 429"
#: must not halve the pool.
RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "too many requests")
_DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smh])$")
_TAIL_CHARS = 800
#: A run gets its own process group, so one Ctrl-C in the studio's console cannot cut a
#: half-written answer file in half from the outside. Windows-only; POSIX uses a session.
_POPEN_KWARGS: dict[str, Any] = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.name == "nt"
    else {"start_new_session": True}
)


def _default_exe() -> Path:
    """`%USERPROFILE%/.minimax-code/mcode.cmd` (or the POSIX install of the same name)."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    base = home / ".minimax-code"
    for name in ("mcode.cmd", "mcode.exe", "bin/mcode", "mcode"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return base / "mcode.cmd"


def exe() -> Path:
    """The CLI to run; a missing install is a setup error, never a silent fallback."""
    override = os.environ.get(EXE_ENV, "").strip()
    path = Path(override) if override else _default_exe()
    if not path.is_file():
        raise StudioError(
            f"{path} does not exist: install the MiniMax Code CLI and check it with "
            f"`mcode --version` (owner memory reference-minimax-code-cli); "
            f"set {EXE_ENV} to point at it"
        )
    return path


def _seconds(timeout: str) -> int:
    """`30m` -> 1800, the hard kill behind `mcode exec --timeout`."""
    match = _DURATION_RE.match(timeout.strip())
    if match is None:
        raise StudioError(f"--timeout {timeout!r} is not a duration like 30s, 20m or 2h")
    value = int(match.group("value"))
    return value * {"s": 1, "m": 60, "h": 3600}[match.group("unit")]


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _TAIL_CHARS else f"...{text[-_TAIL_CHARS:]}"


def _result_of(stdout: str) -> dict[str, Any] | None:
    """The exec JSON: the last line that parses, so a warning line before it is ignored."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("type") == "exec.result":
            return data
    return None


@dataclass(frozen=True)
class Run:
    """One finished `mcode exec`: its ids, the model that ran, the tokens it cost."""

    run_id: str
    session_id: str
    status: str
    model: str
    output: str
    duration_ms: int
    input_tokens: int
    output_tokens: int
    rate_limited: bool = False
    error: str = ""

    def __post_init__(self) -> None:
        if not self.model and not self.rate_limited:
            raise StudioError(f"run {self.run_id} named no model; its stamp would be a guess")


def _await(proc: subprocess.Popen[Any], timeout: str) -> int:
    """The run's exit code, or a StudioError that names the bound and the tree that went.

    This is the only place a run is waited for, and it is bounded: a provider that never
    answers again costs one task, never the batch.
    """
    try:
        return proc.wait(timeout=_seconds(timeout) + GRACE_S)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise StudioError(
            f"mcode exec did not finish within {timeout} plus the {GRACE_S:g} s grace; its "
            f"process tree was killed and this task is not answered, the batch continues"
        ) from None


def _drop(work: Path) -> None:
    """Remove a run's scratch directory; a file a killed run still holds is left behind."""
    try:
        for path in sorted(work.rglob("*"), reverse=True):
            path.unlink()
        work.rmdir()
    except OSError:
        return


def _kill_tree(proc: subprocess.Popen[Any]) -> None:
    """Kill a stuck run and everything it started, then stop waiting for it.

    `proc.kill()` only reaches `mcode.cmd`; the `node` process underneath it is what holds
    the run open, and on Windows a process whose thread sits in a hung socket can refuse
    to die for minutes. So the whole tree goes, and a corpse that outlives `KILL_GRACE_S`
    is left to the OS: the caller is told the run is unanswered, which is true either way.

    A pid the kernel does not know has no tree left to kill, and `proc.kill()` on it would
    raise `ProcessLookupError` out of the timeout handler: the batch would die with a
    confusing error instead of the "not answered, the batch continues" it is owed. That is
    why the POSIX branch has no bare-kill fallback (measured on the Linux CI runner, 2026-10-03).
    """
    if os.name == "nt":
        try:
            subprocess.run(  # noqa: S603 - a fixed argv; the pid is ours
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            # taskkill itself could not run: the process goes, its tree may survive.
            _kill_quietly(proc)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
    try:
        proc.wait(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        return


def _kill_quietly(proc: subprocess.Popen[Any]) -> None:
    """`proc.kill()` for the one case that reaches it: the tree kill could not be attempted."""
    try:
        proc.kill()
    except OSError:
        return


def exec(prompt: str, *, cwd: Path, timeout: str = TIMEOUT) -> Run:
    """Run one judgement. Raises StudioError unless the run produced a usable result.

    The prompt goes in on stdin (`--input -`), never as an argv element: the installed
    `%USERPROFILE%/.minimax-code/mcode.cmd` is a batch wrapper that forwards `%*` through
    `CALL`, and cmd.exe ends a command at the first newline inside an argument, so a
    multi-line prompt as argv reached the model as its first paragraph only. Every studio
    judgement prompt is multi-line by construction, which left the whole batch of
    2026-10-03 13:40:12Z with its role but no task, and no answer file at all.

    Prompt, stdout and stderr travel on files, and the driver waits for the process and
    nothing else. Measured 2026-10-03 16:08: three runs of a wave never returned. Their
    `node` children sat in a ~1 % CPU poll on a hung provider socket, and a pipe-based read
    never saw EOF because those children still held the write end open, so the timeout in
    `subprocess.communicate()` could not fire and the whole 42-task calibration stood still
    for three and a half hours. A file is closed by its owner, never by a grandchild.
    """
    argv = [
        str(exe()),
        "exec",
        "--cwd",
        str(cwd),
        "--model",
        MODEL_REF,
        "--effort",
        EFFORT,
        "--permission",
        PERMISSION,
        "--timeout",
        timeout,
        "--output-format",
        "json",
        "--input",
        "-",
    ]
    work = Path(tempfile.mkdtemp(prefix="mcode-exec-"))
    try:
        (work / "prompt.txt").write_text(prompt, encoding="utf-8")
        try:
            with (
                (work / "prompt.txt").open("r", encoding="utf-8") as feed,
                (work / "stdout.txt").open("w", encoding="utf-8") as out,
                (work / "stderr.txt").open("w", encoding="utf-8") as err,
            ):
                proc = subprocess.Popen(  # noqa: S603 - a fixed argv, the prompt is a file
                    argv,
                    stdin=feed,
                    stdout=out,
                    stderr=err,
                    **_POPEN_KWARGS,
                )
                returncode = _await(proc, timeout)
        except OSError as exc:  # the CLI vanished between exe() and the call
            raise StudioError(f"running {argv[0]} failed: {exc}") from exc
        stdout = (work / "stdout.txt").read_text(encoding="utf-8", errors="replace")
        stderr = (work / "stderr.txt").read_text(encoding="utf-8", errors="replace")
    finally:
        _drop(work)

    blob = f"{stdout}\n{stderr}".strip()
    if returncode != 0:
        lowered = blob.lower()
        if any(marker in lowered for marker in RATE_LIMIT_MARKERS):
            return Run(
                run_id="",
                session_id="",
                status="rate_limited",
                model="",
                output="",
                duration_ms=0,
                input_tokens=0,
                output_tokens=0,
                rate_limited=True,
                error=_tail(blob),
            )
        data = _result_of(stdout)
        words = (data or {}).get("output") or _tail(blob)
        raise StudioError(f"mcode exec exited {returncode}: {_tail(str(words))}")

    data = _result_of(stdout)
    if data is None:
        raise StudioError(f"mcode exec printed no exec.result JSON: {_tail(blob)}")
    if data.get("status") != "succeeded":
        raise StudioError(
            f"mcode exec status {data.get('status')!r}: {_tail(str(data.get('output', '')))}"
        )
    usage = data.get("usage") or {}
    return Run(
        run_id=str(data.get("runId", "")),
        session_id=str(data.get("sessionId", "")),
        status=str(data.get("status", "")),
        model=str((data.get("model") or {}).get("modelId", "")),
        output=str(data.get("output", "")),
        duration_ms=int(data.get("durationMs", 0) or 0),
        input_tokens=int(usage.get("inputTokens", 0) or 0),
        output_tokens=int(usage.get("outputTokens", 0) or 0),
    )


def weekly_remaining_percent() -> float | None:
    """The weekly plan's remaining percent, or None when the endpoint did not answer.

    Lyra's own probe reads `/v1/token_plan/remains` with the key from the repo `.env`; the
    key is never printed here. An unreadable quota is not a stop: the driver says so and
    keeps working, because a plan endpoint that 404s must not silently park the studio.
    """
    data = probe_minimax_quota(force=True)
    if not data.get("ok"):
        return None
    value = data.get("weekly_remaining_percent")
    return None if value is None else float(value)


def weekly_stop() -> str:
    """Empty while the plan has more than 10 % left, else the sentence that names the stop."""
    percent = weekly_remaining_percent()
    if percent is None or percent > WEEKLY_STOP_PERCENT:
        return ""
    return (
        f"the weekly MiniMax plan has {percent:g} % left (stop at {WEEKLY_STOP_PERCENT:g} %, "
        f"owner decision O20); the run resumes after the reset"
    )


def tree_state(repo: Path) -> list[str]:
    """Every tracked change git reports, one line each; untracked files are not listed.

    The snapshot a batch takes before its first run, so the guard can tell a run's own
    writes from the work the owner had in the tree already.
    """
    done = git_env.run_git(repo, "status", "--porcelain", "--untracked-files=no")
    if done.returncode != 0:
        raise StudioError(f"git status in {repo} failed: {_tail(done.stderr)}")
    return [line.rstrip() for line in done.stdout.splitlines() if line.strip()]


def guard_tree(repo: Path, before: Sequence[str] | None = None) -> None:
    """Refuse the batch when a run left a tracked file changed (the plan's guard).

    `before` is the `tree_state` of the same tree before the first run: a working tree the
    owner is already editing is not a run's doing, a change that appeared or disappeared
    during the batch is.
    """
    after = tree_state(repo)
    was = list(before) if before is not None else []
    changed = sorted({*after} - {*was}) + sorted({*was} - {*after})
    if changed:
        raise StudioError(
            f"a run changed tracked files in {repo}: {changed}; an answer belongs in its "
            f"answer file, so the batch is not counted (revert them, then run again)"
        )


@dataclass
class Outcome:
    """What one worker did with one item: a value, or the reason there is none."""

    item: Any
    value: Any = None
    reason: str = ""
    run: Run | None = None
    rate_limited: bool = False
    stop: str = ""


@dataclass
class Pool:
    """`map` over items with the parallelism of owner decision O22.

    A rate-limited wave halves the parallelism *and* pauses: the next wave starts after
    `pause` seconds, which double up to `pause_max`. Retrying a 429 the next instant is
    how a rate limit becomes a ban, so the wait grows while the limits keep coming.
    """

    start: int = START_CONCURRENCY
    cap: int = MAX_CONCURRENCY
    pause: float = PAUSE_AFTER_429_S
    pause_max: float = PAUSE_MAX_S
    hard_bound_s: float = field(default_factory=lambda: _seconds(TIMEOUT) + 300.0)
    limit: int = field(init=False)
    stop: str = ""
    waited_s: float = 0.0

    def __post_init__(self) -> None:
        self.limit = min(max(1, self.start), max(1, self.cap))

    def map(
        self,
        items: Sequence[Any],
        worker: Callable[[Any], Outcome],
        on_wave: Callable[[list[Outcome]], None] | None = None,
    ) -> list[Outcome]:
        """One wave of `limit` runs at a time; the next wave follows the wave's result.

        `on_wave` is called with each wave's outcomes as soon as that wave is done, so a
        long batch can bank its answers (and re-check the tree) before the next wave
        starts: a batch that is stopped after three hours keeps those three hours.
        """
        results: list[Outcome] = []
        queue = list(items)
        pause = self.pause
        while queue and not self.stop:
            wave, queue = queue[: self.limit], queue[self.limit :]
            batch = self._wave(wave, worker)
            results.extend(batch)
            if on_wave is not None:
                on_wave(batch)
            stops = [o for o in batch if o.stop]
            if stops:
                self.stop = stops[0].stop
            elif any(o.rate_limited for o in batch):
                self.limit = max(1, self.limit // 2)
                time.sleep(pause)
                self.waited_s += pause
                pause = min(self.pause_max, pause * 2)
            else:
                self.limit = min(self.cap, self.limit + 1)
        return results

    def _wave(self, wave: Sequence[Any], worker: Callable[[Any], Outcome]) -> list[Outcome]:
        """Run one wave and give up on whatever is still running after `hard_bound_s`.

        A worker is bounded by `exec`, so this is the second lock on the same door: a bug
        in a worker, or a thread that will not return, costs its own task instead of
        standing the whole batch still. The unfinished tasks are reported with the reason,
        and a re-run answers them, because a check only counts an answered task.
        """
        pool = ThreadPoolExecutor(max_workers=len(wave))
        futures = {pool.submit(worker, item): item for item in wave}
        done: set[Future[Outcome]]
        pending: set[Future[Outcome]]
        try:
            done, pending = wait(futures, timeout=self.hard_bound_s)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        reason = f"the run exceeded the batch's hard bound of {self.hard_bound_s:g} s and was not answered"
        return [
            future.result() if future in done else Outcome(item=futures[future], reason=reason)
            for future in futures
        ]
