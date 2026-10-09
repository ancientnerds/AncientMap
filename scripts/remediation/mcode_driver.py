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
import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
if __package__ in (None, ""):
    sys.path.insert(0, str(_HERE.parent))
#: The repository root, so the driver can share the one git helper with the pipeline
#: (`pipeline/utils/git_env.py`). A git call that names a repository is only about that
#: repository when it runs without an inherited `GIT_DIR`; see `run_git`.
if str(_HERE.parents[2]) not in sys.path:
    sys.path.insert(0, str(_HERE.parents[2]))

from pipeline.utils.git_env import run_git as _git_without_git_env  # noqa: E402

REPO = Path("C:/PythonProjects/AncientMap")
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
#: The checkout that holds *this file*, and with it the code a lane runs and an answering agent
#: obeys. It is not `REPO`: the driver is written and run in a worktree, and only the data stays
#: behind in the data root. Every path the driver names for *code* comes from here, an answering
#: agent is sent into here, and the tracked-tree guard watches here and nowhere else - the guard
#: can only attribute a change to a batch if the tree it watches is the tree the batch ran in.
#: Measured 2026-10-04 11:43: the guard watched the data root, a second session was working in it,
#: and its six committed files voided a batch that had answered 8 sites.
WORKTREE = _HERE.parents[2]
#: The model id an answer is recorded with (`opus_handoff.answer --model`): exactly as the
#: answering agent's own system prompt names it.
ANSWER_STAMP_MODEL = "MiniMax-M3.1-Flash-Preview"
#: The route `mcode exec --model` takes. A different string from the one above on purpose: the
#: route is not the model id, and an answer must never name the route.
EXEC_MODEL = "minimax/MiniMax-M3.1-Flash-Preview"
EXEC_EFFORT = "max"
#: Owner decision 2026-10-03 (O20): the weekly quota below which the driver stops, read from
#: `https://api.minimax.io/v1/token_plan/remains` with the key the Lyra pipeline already uses.
#: The endpoint wants an `Authorization: Bearer <key>` header - a bare key answers `login fail`
#: (status 1004), which is what the driver sent before 2026-10-03 and what cost a lane its quota
#: check.
QUOTA_URL = "https://api.minimax.io/v1/token_plan/remains"
QUOTA_KEY_NAME = "LYRA_MINIMAX_API_KEY"
QUOTA_AUTH_PREFIX = "Bearer "
#: The quota is reported per model. The driver answers with the coding model, so it reads that
#: entry and not the first one: the payload also carries `video`, which is a different plan and
#: would report 100 percent while the plan the lane spends is the one that runs out.
QUOTA_MODEL_NAME = "general"
QUOTA_FLOOR_PERCENT = 10.0
#: How long past the agent's own `--timeout` the driver waits before it takes the run back. The
#: runtime gets its deadline plus this much to wind down and print its JSON; after that the driver
#: kills the tree and counts the batch unanswered, whatever state it is in.
EXEC_OVERHEAD_S = 120
#: How long a killed tree is given to be gone before the driver answers without it. It is the
#: bound on the one wait that must not be open-ended: the driver took a process away and does not
#: stand there until it agrees to die.
KILL_GRACE_S = 10
#: Owner decision 2026-10-03 (O18): a lane type is calibrated before it writes a MiniMax answer to
#: production, and it passes at this share of judged units agreeing with the recorded answers.
AGREEMENT_FLOOR = 0.9
WIDTH_START = 2
WIDTH_CAP = 14
HANDOFF = REPO / "output" / "remediation" / "handoff"
RUNS = REPO / "output" / "remediation" / "wc_runner" / "runs"
#: The fields lane's tool directory, **not** its data directory. `output/remediation/fields/` holds
#: the run; the CLI that reads it is `scripts/remediation/fields/handoff.py`. Measured 2026-10-03:
#: this constant pointed at the data directory, so every field-fill brief named a file that is not
#: there and every answering batch started with a command that failed. It is the tool of the
#: checkout the driver runs in, so the questions a batch answers are the ones that checkout's tool
#: asked.
FIELDS = WORKTREE / "scripts" / "remediation" / "fields"
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
    answer (a `status` is 0 either way).

    The call runs without `GIT_*` (`pipeline/utils/git_env.py`, the one place that knows this).
    Git reads the repository from the environment before it looks at the command line, and the
    pre-push hook exports `GIT_DIR` for the checkout it pushes while the test suite runs inside
    that hook - so `cwd=<repo>` alone answers about *that* repository, and answers successfully
    about it (measured 2026-10-03: a test's `commit` landed on the branch being pushed). A tree
    guard built on a redirected `status` sees a clean tree in a repository it never asked about.
    """
    done = _git_without_git_env(repo, *args)
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


def _free_ram_gb_from_meminfo(text: str) -> float:
    """`/proc/meminfo`'s `MemAvailable` in GB, 0.0 when the line is not in it."""
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return 0.0


def free_ram_gb() -> float:
    """Free RAM in GB, for the width cap. 0.0 when it cannot be read: the cap then does not bind,
    which is the safe direction (too narrow a cap would stall a lane on a healthy machine).

    Measured 2026-10-03: this shelled out to `wmic OS get FreePhysicalMemory`, which this Windows
    no longer ships. The command processor answered `wMic is not recognized` on stderr, the reader
    found no line, and the cap read that as "no cap" - the width governor grew unbounded on the
    machine that was supposed to hold it back. `GlobalMemoryStatusEx` is the API behind it, in the
    standard library, with nothing to go missing.
    """
    if os.name == "nt":

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            # `ullAvailPhys` is bytes. The kilobyte figure this replaced was divided by 1024 twice.
            return status.ullAvailPhys / 1024**3
        return 0.0
    try:
        return _free_ram_gb_from_meminfo(Path("/proc/meminfo").read_text(encoding="utf-8"))
    except OSError:
        return 0.0


# ------------------------------------------------------------------------------------ one mcode exec
def _own_process_group() -> dict[str, bool]:
    """A child in a process group of its own, so a kill can reach everything under it.

    POSIX only: `killpg` needs a group, and the group is the child's alone only when the child was
    started into one. Windows walks the parent-child tree instead (`taskkill /T`), which needs no
    flag and follows the runtime's `node` under the command processor.
    """
    return {} if os.name == "nt" else {"start_new_session": True}


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Every process under `process`, not only the one this driver started.

    The one this driver started is the command processor (`mcode` on PATH is a `.cmd` shim, and
    `CreateProcess` runs neither). Killing only that leaves the runtime's `node` running with the
    answer half-written - measured 2026-10-03, three `node` children on ~1 % CPU on a socket that
    would never answer again.
    """
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - a fixed argv, `taskkill` on PATH
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=KILL_GRACE_S,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        # the group is already gone: the deadline and this kill raced the process's own exit
        process.kill()


def _reap(process: subprocess.Popen[bytes], grace: int = KILL_GRACE_S) -> int:
    """The exit code of a killed process, or -1 when it outlived its own kill. A driver that waits
    for a process that will not stop is the defect this replaces; it answers without one."""
    try:
        return process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        return -1


def mcode_argv(*args: str, binary: str = "mcode") -> list[str]:
    """The command that runs `mcode` here.

    On Windows the `mcode` on PATH is a `.cmd`/`.ps1` shim, and `CreateProcess` runs neither, so
    the command processor is asked to run the shim. Measured 2026-10-03:
    `subprocess.run(["mcode", ...])` answers `FileNotFoundError: [WinError 2]`.
    """
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", binary, *args]
    return [binary, *args]


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
    #: Whether the driver took this run back at its own deadline. Not the same as a failure the
    #: run reported, and not derivable from the exit code: the code is whatever the kill left.
    timed_out: bool = False

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

    @property
    def succeeded(self) -> bool:
        """Whether the run itself succeeded. `mcode exec --output-format json` answers an
        `exec.result` with a `status` ("succeeded", "failed", ...) and no `ok`, so a run that failed
        while exiting 0 - a refused permission, a step limit - is not a success. A run the driver
        had to kill is not one either, whatever exit code the kill left behind."""
        if self.timed_out or self.exit_code != 0:
            return False
        status = self.payload.get("status")
        if isinstance(status, str):
            return status == "succeeded"
        return bool(self.payload.get("ok", True))


class McodeRunner:
    """One `mcode exec` at a time. `binary` is the command to call, so a test passes a fake."""

    def __init__(
        self,
        *,
        binary: str | Path = "mcode",
        repo: Path = WORKTREE,
        diagnostics: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.binary = str(binary)
        self.repo = Path(repo)
        self.diagnostics = Path(diagnostics) if diagnostics else STATE_DIR / "diagnostics"
        #: Added to this process's environment, never a replacement of it: `mcode` needs PATH and
        #: its own configuration, and a replaced environment would run it with neither.
        self.extra_env = dict(env) if env else {}

    def _free_diagnostics(self, label: str) -> Path:
        """An empty diagnostics directory for this attempt at `label`: `<label>`, then `<label>-2`,
        `<label>-3`, ...

        Measured 2026-10-03: `mcode exec` refuses a diagnostics directory that is not empty
        ("Diagnostics directory must be empty"). One directory per batch therefore means a batch can
        never be retried - and a stopped lane is resumed, always onto the directory the failed
        attempt left behind. Each attempt gets its own, and the earlier one keeps its evidence: a
        run that has to be explained a week later is read from those files.
        """
        target = self.diagnostics / label
        attempt = 1
        while target.is_dir() and any(target.iterdir()):
            attempt += 1
            target = self.diagnostics / f"{label}-{attempt}"
        return target

    def run(
        self,
        prompt: str,
        *,
        label: str,
        timeout: int,
        max_steps: int,
        effort: str = EXEC_EFFORT,
        overhead: int = EXEC_OVERHEAD_S,
    ) -> ExecResult:
        """Run one batch. The tracked tree is sampled before and after, so the result carries what
        the batch changed - or nothing, which is the normal case. The tree is `self.repo`, the
        checkout the agent is sent into, and never the data root: a dirty tracked file there is
        another session's work, and the lane stops for its own agent's changes only."""
        if effort not in EFFORTS:
            raise DriverError(f"effort {effort!r} is not one of {sorted(EFFORTS)}")
        target = self._free_diagnostics(label)
        target.mkdir(parents=True, exist_ok=True)
        before = tracked_changes(self.repo)
        last_message = target / "last-message.txt"
        # The prompt goes in over stdin, never on this command line: it is a long multi-line text
        # with quotes, and on Windows the command line would go through `cmd`'s argument parsing.
        # It is a file and not a pipe, like the two output streams - and beside the run, not in it:
        # `mcode exec` refuses a diagnostics directory that is not empty.
        prompt_file = self.diagnostics / "prompts" / f"{target.name}.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt, encoding="utf-8")
        # `--timeout` takes a duration ("3600s"), not a bare number, and there is no `--label`: the
        # batch's own name is what this directory is called, and the agent's last message is kept
        # beside it.
        argv = mcode_argv(
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
            f"{timeout}s",
            "--max-steps",
            str(max_steps),
            "--output-format",
            "json",
            "--diagnostics-dir",
            str(target),
            "--output-last-message",
            str(last_message),
            "--input",
            "-",
            binary=self.binary,
        )
        code, out, err, timed_out = self._exec(
            argv, prompt_file, target, deadline=timeout + overhead
        )
        changed = _changed_since(before, tracked_changes(self.repo))
        payload = _last_json_line(out)
        result = ExecResult(
            exit_code=code,
            ok=False,  # the run's own verdict, from the exec result's `status`, set below
            payload=payload,
            stdout=out,
            stderr=err,
            diagnostics=target,
            tree_changed=changed,
            timed_out=timed_out,
        )
        return replace(result, ok=result.succeeded)

    def _exec(
        self, argv: Sequence[str], prompt: Path, target: Path, *, deadline: int
    ) -> tuple[int, str, str, bool]:
        """One `mcode exec` with all three streams on files and the process owned by this driver.

        The files are the point. With pipes, `subprocess.run(..., timeout=…)` kills the process it
        started - the command processor - and then drains the pipes, which the `node` underneath
        still holds open: the call never returns, however long the timeout was (measured on this
        machine 2026-10-03: a deadline of 121 s, still blocked at 170 s; the studio lost 3.5 h to
        it). With files there is nothing to drain, so the deadline can be kept: the whole tree is
        killed, given `KILL_GRACE_S` to be gone, and whatever the run left on disk is the answer.
        A run that does not die counts as unanswered - which is true either way.

        The two output files are written **beside** the diagnostics directory and moved into it
        afterwards. `mcode exec` refuses a diagnostics directory that is not empty (measured
        2026-10-03), so a stream opened into it before the run starts is a run that never starts.
        """
        out_path = target.with_name(f"{target.name}.stdout.txt")
        err_path = target.with_name(f"{target.name}.stderr.txt")
        with (
            prompt.open("rb") as stdin,
            out_path.open("wb") as out,
            err_path.open("wb") as err,
        ):
            try:
                process = subprocess.Popen(  # noqa: S603 - argv built here, `mcode` on PATH
                    list(argv),
                    cwd=self.repo,
                    stdin=stdin,
                    stdout=out,
                    stderr=err,
                    env={**os.environ, **self.extra_env} if self.extra_env else None,
                    **_own_process_group(),
                )
            except FileNotFoundError as exc:
                raise DriverError(f"{self.binary} is not on PATH: {exc}") from exc
            timed_out = False
            try:
                code = process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(process)
                code = _reap(process)
                if process.poll() is None:
                    # What a run that outlives its own kill leaves behind. The driver does not wait
                    # for a process that will not stop; the evidence goes to disk instead.
                    err.write(
                        f"mcode_driver: pid {process.pid} was still running {KILL_GRACE_S}s after "
                        f"the tree kill at {deadline}s\n".encode()
                    )
                    err.flush()
        return (
            code,
            _read_and_keep(out_path, target / "stdout.txt"),
            _read_and_keep(err_path, target / "stderr.txt"),
            timed_out,
        )

    def voids(self, result: ExecResult) -> bool:
        """Whether this batch may not be counted: it failed, or it edited a tracked file."""
        return not result.ok or not result.tree_clean


def _read_and_keep(staged: Path, into: Path) -> str:
    """What the run wrote, and the file itself beside the rest of its diagnostics.

    The text is read first: a run's stdout is read a week later out of the diagnostics directory
    the run was given, not out of the scratch its streams needed while it was still running.
    """
    text = staged.read_text(encoding="utf-8", errors="replace")
    staged.replace(into)
    return text


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
    """One value of the repo's `.env`. Read, never printed, never logged.

    `.env` is written on Windows and therefore has CRLF line endings, and a value may be quoted.
    A `\r` left on the key would be part of the Authorization header and the endpoint answers
    `login fail`; the quotes are not part of the key either.
    """
    if not env_file.exists():
        raise DriverError(f"{name} is not set: {env_file} is missing")
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip("\r\n").strip()
        if not line or line.startswith("#") or not line.startswith(f"{name}="):
            continue
        value = line.split("=", 1)[1].strip().strip("\r\n").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        value = value.strip().strip("\r\n")
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

    The header is `Authorization: Bearer <key>` (owner, measured 2026-10-03: a bare key answers
    `login fail` / status 1004; with the prefix the same key returns the percent). The key is the
    one the Lyra pipeline already uses - no second secret is involved - and the variable name
    stays a parameter for a repo that stores it elsewhere.
    """
    key = _env_value(key_name, env_file)
    call = fetch or _http_json
    payload = call(QUOTA_URL, headers={"Authorization": f"{QUOTA_AUTH_PREFIX}{key}"}, timeout=30.0)
    base = payload.get("base_resp") or {}
    if base.get("status_code") not in (None, 0):
        raise DriverError(
            f"{QUOTA_URL} refused the request: {base.get('status_msg', '')[:200]} (status "
            f"{base.get('status_code')}), with the key of {key_name} read from {env_file}. The "
            f"header is Authorization: {QUOTA_AUTH_PREFIX}<key>; a bare key answers 'login fail'. "
            "The driver stops here rather than run a lane without a quota check."
        )
    value = payload.get("current_weekly_remaining_percent")
    if not isinstance(value, (int, float)):
        value = _weekly_percent_of(payload, QUOTA_MODEL_NAME)
    if not isinstance(value, (int, float)):
        raise DriverError(
            f"{QUOTA_URL} returned no weekly percent for {QUOTA_MODEL_NAME!r}: {payload!r}"
        )
    return float(value)


def _weekly_percent_of(payload: Mapping[str, Any], model: str) -> float | None:
    """The weekly percent of one model's plan. The endpoint reports a list, one entry per model
    (measured 2026-10-03: `general` at 77, `video` at 100), and a driver that read the first
    entry or averaged them would stop on the wrong plan."""
    entries = payload.get("model_remains")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("model_name") == model:
            value = entry.get("current_weekly_remaining_percent")
            return float(value) if isinstance(value, (int, float)) else None
    return None


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


def record_round(state: State, check: Validation, *, batches: int, done: bool) -> None:
    """Write the round's completeness into the state file, so a reader can tell a finished run from
    a stopped one without running the lane.

    `missing` is what the run still owes in *questions*; `done` is whether this driver has anything
    left to do for it. The two are not the same thing, and the difference cost a night: measured
    2026-10-04, lane WC's three runs answered 13, 22 and 99 batches, validated clean, and every
    import then stopped on "reading a PDF page needs pdftotext on PATH" - a run with no questions
    left and no import. For the fields lane the driver answers and stops, so nothing missing is
    finished; for lane WC the driver imports and builds after that, and only the plan says when the
    run is done.

    The driver used to write nothing at all on the "nothing missing" path - it printed the note and
    returned 0 - so a finished round and a lane that died mid-batch left the same state file.
    """
    state.put("batches", batches)
    state.put("missing", list(check.missing))
    state.put("done", done)


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
    repo: str = str(WORKTREE),
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
    #: The lane the round's batch ids belong to, read from those ids (`wd4-r0-b0001` is wd4). It
    #: names the state file and the batch-name check. A round that has not been exported yet is
    #: nothing to answer, and keeps the driver's own name.
    lane: str = "wd3"

    def batch_names_ok(self, names: Sequence[str]) -> bool:
        """Whether the batch names on disk are the ones the lane's own naming scheme makes, so a
        directory that holds something else is refused instead of half-driven."""
        return tuple(names) == batch_ids(self.lane, self.round_name, len(self.batches))


def batch_folders(handoff: Path) -> tuple[str, ...]:
    """The batch folders of a handoff directory, in sorted order: every subdirectory that holds a
    MANIFEST.jsonl. Counted here, not asked of a model (2026-10-01: 327 ids came back as one
    string "wd3-r0-b0001 through wd3-r0-b0327")."""
    if not handoff.is_dir():
        return ()
    return tuple(
        sorted(p.name for p in handoff.iterdir() if p.is_dir() and (p / "MANIFEST.jsonl").exists())
    )


def batch_ids(lane: str, round_name: str, count: int) -> tuple[str, ...]:
    """The batch ids a round of `lane` is made of, the way the exporting tool names them."""
    return tuple(f"{lane}-{round_name}-b{n:04d}" for n in range(1, count + 1))


def lane_of(name: str, round_name: str) -> str:
    """The lane a batch id belongs to: `wd4-r0-b0001` in round `r0` is lane `wd4`.

    Empty when the name is not a batch id of that round, which is the case the caller has to refuse
    rather than read a lane out of a folder name.
    """
    head, marker, tail = name.partition(f"-{round_name}-b")
    return head if marker and tail.isdigit() else ""


def lanes_of(names: Sequence[str], round_name: str) -> str:
    """The one lane every batch id of a round belongs to, or a refusal naming what does not fit.

    Two lanes' rounds in one directory would have to be picked between, and picking is guessing.
    """
    lanes: dict[str, str] = {}
    for name in names:
        lanes.setdefault(lane_of(name, round_name), name)
    if "" in lanes:
        raise DriverError(
            f"{lanes['']!r} in this round's directory is not a batch id of round {round_name!r} "
            f"(the lane's own are {batch_ids('<lane>', round_name, 2)[0]} ...), so it has no brief "
            f"and cannot be answered"
        )
    if len(lanes) > 1:
        raise DriverError(
            f"one round's directory holds {len(lanes)} lanes "
            f"({', '.join(repr(v) for v in lanes.values())}); naming one of them would be a guess"
        )
    return next(iter(lanes))


def plan_wd3(*, run: Path, handoff: Path, resume: bool, round_index: int = 0) -> Plan:
    """The WD3 pool's first operator step, for one round. With `resume` the round was exported
    before, so the step counts what is there; without it, the step exports. The export command is
    returned rather than run, so the caller runs exactly one thing per step.

    Round 0 is the run's own population (`export`); every round after it is a re-ask of the fields
    that had no counted answer (`export-reask`, runbook step 10, at most two of them). Each round has
    its own handoff directory and its own batch names, because a question is answered as it was
    asked: a round's answers belong to that round's prompts.
    """
    round_name = f"r{round_index}"
    fields = str(FIELDS / "handoff.py")
    export = (
        str(PYTHON),
        fields,
        "export" if round_index == 0 else "export-reask",
        "--run",
        str(run),
        "--handoff",
        f"{handoff}-{round_name}",
    )
    if not resume:
        return Plan((), True, export, Path(f"{handoff}-{round_name}"), round_name=round_name)
    made = batch_folders(Path(f"{handoff}-{round_name}"))
    return Plan(
        made,
        False,
        export,
        Path(f"{handoff}-{round_name}"),
        round_name=round_name,
        lane=lanes_of(made, round_name) if made else "wd3",
    )


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


#: `wc/cli.py` names the answer it refuses as `REFUSED: <batch-id>/<stage>/<label>: <why>`, followed
#: by what to do about it. The batch id is what the driver needs; a refusal without one is about
#: something else and is not guessed at.
_REFUSED = re.compile(r"^REFUSED:\s+([A-Za-z0-9._-]+)/", re.MULTILINE)


def refused_batch(text: str) -> str:
    """The batch an operator command refused an answer of, or `""` when it refused no answer."""
    found = _REFUSED.search(text or "")
    return found.group(1) if found else ""


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
    *, run: Path, handoff: Path, batch: str, brief: str = "brief", repo: str = str(WORKTREE)
) -> str:
    """One WC answering batch's instruction, from `wc-continue.js` with the model strings replaced."""
    return answer_prompt(
        lane="wc",
        run=str(run),
        batch=batch,
        repo=repo,
        brief=brief,
        brief_command=(
            f"cd {repo} && PYTHONIOENCODING=utf-8 {PYTHON} "
            f"{WORKTREE / 'scripts' / 'remediation' / 'wc' / 'cli.py'} "
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
        """The command's own JSON payload. The tools print it in two shapes and both are real: an
        operator command (`opus_handoff.py validate`, the WC CLI) pretty-prints it across many lines
        and it is the whole stdout, while an `mcode exec` prints one object on the last line after
        whatever the agent wrote before it. Whichever shape it is, the payload is read; a shape that
        is not there is not guessed."""
        try:
            whole = json.loads(self.stdout)
        except json.JSONDecodeError:
            return _last_json_line(self.stdout)
        return whole if isinstance(whole, dict) else {}

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
    state of a round in progress, so the exit code is not the verdict - the JSON is.

    The tool is the one of the checkout the driver runs in, because it is that checkout's brief
    that wrote the questions and the answers have to pass its checker. `repo` stays the data root:
    the command runs there, because a tool that resolves `output/` against its working directory
    has to find the run and not a copy of it."""
    command = run_operator(
        (
            str(PYTHON),
            str(WORKTREE / "scripts" / "remediation" / "opus_handoff.py"),
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
            record_round(
                state,
                check,
                batches=len(batch_folders(plan.answer_handoff)),
                done=plan.done,
            )
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
                    # A refusal that names a batch is about one of its answers, and an answer the
                    # lane's own checker will not accept is not a finished batch. The state file
                    # marked it answered because the agent wrote its files, so a resume would skip
                    # it, the validator would keep naming it missing, and the run would stop with
                    # "no progress" instead of asking for the question again. Put it back, and say
                    # which file to delete: an answer is write-once (`opus_handoff.write_answer`
                    # refuses different bytes), so the retry only lands once the bad file is gone.
                    refusal = f"{done.stdout}\n{done.stderr}"
                    batch = refused_batch(refusal)
                    if batch:
                        state.put("answered", [b for b in state.get("answered", []) if b != batch])
                        state.put(
                            "outcomes",
                            {k: v for k, v in state.get("outcomes", {}).items() if k != batch},
                        )
                    log.append({**entry, "stopped": f"{import_argv[2]} failed: {refusal.strip()}"})
                    return {
                        "run": run.name,
                        "steps": log,
                        "stopped": f"{import_argv[2]} failed",
                        **({"rejected_batch": batch} if batch else {}),
                    }
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
                ledger=HandoffLedger(plan.answer_handoff),
            )
            entry["answered"] = sum(1 for o in outcomes if o.ok)
            entry["void"] = [o.label for o in outcomes if o.void]
            entry["unanswered_batches"] = [
                {"label": o.label, "reason": o.reason} for o in outcomes if not o.ok
            ]
            log.append(entry)
            if any(not o.ok for o in outcomes):
                first = next(o for o in outcomes if not o.ok)
                return {
                    "run": run.name,
                    "steps": log,
                    "stopped": first.reason or f"void batch {first.label}",
                }
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
@dataclass(frozen=True)
class HandoffLedger:
    """What a batch still owes and what it has recorded, counted from the files the tool itself
    writes: `<batch>/<stage>/<label>.prompt.txt` and the answer file of the same name.

    The count is the only honest witness that a batch did its work. An `mcode exec` that ends with
    exit 0 and `status: succeeded` says the *turn* ended, not that an answer was written: measured
    2026-10-03, a model that refused to answer (the WC tool's own round guard rejected the
    calibration handoff) ended exactly like that, and the lane counted the batch as done.
    """

    handoff: Path

    def _files(self, batch: str, suffix: str) -> set[str]:
        directory = self.handoff / batch
        if not directory.is_dir():
            return set()
        return {p.name[: -len(suffix)] for p in directory.rglob(f"*{suffix}")}

    def open(self, batch: str) -> int:
        """The questions of `batch` that carry a prompt and no answer."""
        return len(self._files(batch, ".prompt.txt") - self._files(batch, ".answer.json"))

    def answered(self, batch: str) -> int:
        return len(self._files(batch, ".answer.json"))


@dataclass
class BatchOutcome:
    label: str
    ok: bool
    void: bool
    rate_limited: bool
    exit_code: int
    diagnostics: str
    tree_changed: tuple[str, ...] = ()
    due: int = 0
    recorded: int = 0
    reason: str = ""
    executed: bool = True


def answer_all(
    labels: Sequence[str],
    *,
    prompt_for: Callable[[str], str],
    runner: McodeRunner,
    width: Width,
    state: State,
    timeout: int,
    max_steps: int,
    ledger: HandoffLedger,
    effort: str = EXEC_EFFORT,
    quota_check: Callable[[], bool] | None = None,
    on_void: Callable[[BatchOutcome], None] | None = None,
) -> list[BatchOutcome]:
    """Answer every batch label and stop the lane the moment a batch does not deliver.

    Two stops, both measured. A batch whose agent edited a tracked file may have changed the lane's
    own rules, so its answers are not counted (*void*). A batch that owed questions and recorded
    none of them did not do its work, whatever its exit code said - the reason names the count.
    Either way the batches behind it are not started: the pool holds one window, not the lane, so
    a stop costs at most the window in flight.

    Every batch's outcome is written to the state file before the next one starts, so a stop loses
    at most the batch in flight, and a batch that did not deliver is not marked answered: a resume
    tries it again (the answers it did write are write-once, so the retry only fills the gap).
    """
    done: set[str] = set(state.get("answered", []))
    outcomes: list[BatchOutcome] = []
    remaining = [label for label in labels if label not in done]
    index = 0
    while index < len(remaining):
        size = max(1, width.next_window())
        window = remaining[index : index + size]
        if quota_check is not None and quota_check():
            outcomes.append(BatchOutcome(window[0], False, True, False, 0, "", ("quota",)))
            break
        due = {label: ledger.open(label) for label in window}
        # What a batch had recorded is read *before* it is submitted: an exec that answers quickly
        # writes its files while the driver is still setting the window up, and a count taken
        # afterwards reads a full batch as `recorded 0 of 5`.
        owed = {label: ledger.answered(label) for label in window}
        owes = [label for label in window if due[label] > 0]
        index += size
        for label in [label for label in window if due[label] == 0]:
            outcomes.append(
                BatchOutcome(label, True, False, False, 0, "", (), 0, 0, "", executed=False)
            )
            done.add(label)
            state.put("answered", sorted(done))
        if not owes:
            width.window_clean()
            continue
        stopped = False
        clean = True
        with ThreadPoolExecutor(max_workers=len(owes)) as pool:
            futures = {
                label: pool.submit(
                    runner.run,
                    prompt_for(label),
                    label=label,
                    timeout=timeout,
                    max_steps=max_steps,
                    effort=effort,
                )
                for label in owes
            }
            for label, future in futures.items():
                result = future.result()
                recorded = ledger.answered(label) - owed[label]
                void = runner.voids(result)
                stalled = recorded < due[label]
                outcome = BatchOutcome(
                    label=label,
                    ok=not void and not stalled,
                    void=void,
                    rate_limited=result.rate_limited,
                    exit_code=result.exit_code,
                    diagnostics=str(result.diagnostics),
                    tree_changed=result.tree_changed,
                    due=due[label],
                    recorded=recorded,
                    reason="" if not stalled else f"recorded {recorded} of {due[label]}",
                )
                outcomes.append(outcome)
                state.put("outcomes", {**(state.get("outcomes", {})), label: outcome.__dict__})
                if outcome.ok:
                    done.add(label)
                    state.put("answered", sorted(done))
                else:
                    clean = False
                if result.rate_limited:
                    width.rate_limited()
                if void or stalled:
                    if on_void is not None:
                        on_void(outcome)
                    stopped = True
                    break
        if stopped:
            break
        if clean:
            width.window_clean()
    return outcomes


def _quota_check() -> Callable[[], bool]:
    """The weekly quota stop, read once per batch. The key is read inside `quota_remaining`; this
    function never holds or prints it."""

    def exceeded() -> bool:
        return quota_exhausted(quota_remaining())

    return exceeded


# ------------------------------------------------------------------------------------ calibration
@dataclass(frozen=True)
class Disagreement:
    """One unit of judgement the two answers do not share, with the sources either side cited. The
    brief's bar is "spot-check every cited URL/quote of disagreements yourself", so a disagreement
    that does not carry them cannot be spot-checked."""

    label: str
    unit: str
    recorded: str
    fresh: str
    recorded_sources: tuple[str, ...]
    fresh_sources: tuple[str, ...]


@dataclass(frozen=True)
class Calibration:
    """What one calibration run measured. `agreement` is per judged unit (a sentence for a check
    answer, a kept claim for a verification answer), not per site: that is the level a disagreement
    is judged at, and the level the spot-check reads."""

    lane: str
    labels: tuple[str, ...]
    units: int
    agreed: int
    disagreements: tuple[Disagreement, ...]
    unanswered: tuple[str, ...]

    @property
    def agreement(self) -> float:
        """The share of judged units both answers agree on.

        No units means nothing was measured, and that is 0, not 1: a run whose agent answered
        nothing would otherwise report perfect agreement, which is the one outcome the calibration
        exists to catch.
        """
        return 0.0 if self.units == 0 else self.agreed / self.units

    @property
    def passed(self) -> bool:
        """Owner decision 2026-10-03 (O18): the lane type passes at >= 90 % agreement **and** every
        calibrated question answered. An unanswered question is not agreement, so a run that could
        only answer half of them has not measured the lane it is supposed to clear."""
        return not self.unanswered and self.units > 0 and self.agreement >= AGREEMENT_FLOOR

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "labels": list(self.labels),
            "units": self.units,
            "agreed": self.agreed,
            "agreement": round(self.agreement, 4),
            "passed": self.passed,
            "unanswered": list(self.unanswered),
            "disagreements": [
                {
                    **d.__dict__,
                    "recorded_sources": list(d.recorded_sources),
                    "fresh_sources": list(d.fresh_sources),
                }
                for d in self.disagreements
            ],
        }


def _verdicts(text: str) -> tuple[tuple[str, str], ...] | None:
    """The judged units of one answer as `(unit, verdict)` pairs, or `None` when the text is not
    that shape. Three shapes exist: a check answer carries `sentences`, a verification answer
    `kept`, a field-fill answer a `fields` object; the first two also carry a `coherent` flag, read
    as its own unit."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("fields"), dict):
        return _fill_units(data["fields"])
    identity = _identity_units(data)
    if identity is not None:
        return identity
    if isinstance(data.get("sentences"), list):
        pairs = [(f"sentence-{row.get('n')}", str(row.get("verdict"))) for row in data["sentences"]]
    elif isinstance(data.get("kept"), list):
        pairs = [(f"kept-{row.get('k')}", str(row.get("verdict"))) for row in data["kept"]]
    else:
        return None
    return tuple(pairs) + (("coherent", str(data.get("coherent"))),)


#: The identity stages' answers (`identity/dup_judge.py`, `identity/parent_judge.py`): a list of
#: `members` (the duplicate verdict and its recheck) or `children` (the parent question), one row per
#: site, each with a `verdict` or a `decision` and - when it names one - a `survivor`, `parent` or
#: `target`. The unit is the site, the verdict what the lane would act on: `MERGE:<survivor>` says
#: which record survives, so a different survivor is a disagreement.
_IDENTITY_LISTS = ("members", "children")
_IDENTITY_TARGETS = ("survivor", "parent", "target")


def _identity_units(data: Mapping[str, Any]) -> tuple[tuple[str, str], ...] | None:
    key = next((k for k in _IDENTITY_LISTS if isinstance(data.get(k), list)), None)
    if key is None:
        return None
    units: list[tuple[str, str]] = []
    for row in data[key]:
        if not isinstance(row, dict) or "site_id" not in row:
            return None
        verdict = row.get("verdict", row.get("decision"))
        if verdict is None:
            return None
        target = next((row[t] for t in _IDENTITY_TARGETS if row.get(t)), None)
        units.append((str(row["site_id"]), f"{verdict}:{target}" if target else str(verdict)))
    return tuple(units)


def _fill_units(fields: Any) -> tuple[tuple[str, str], ...] | None:
    """The field-fill shape as one unit per field: what the lane would write into it.

    Measured 2026-10-03: a field-fill answer carries none of the two shapes above, so every one of
    the 24 answers of `fields-02` counted as unreadable and the comparison reported 0 units. The
    unit is the cell, and what the import writes for it is the decision - only `replace` puts a
    value into the field. A `keep` writes nothing, so its value is not compared at all: the field's
    own rule does not even require it to be the stored one (`fields/answers.py`: `keep, but the
    year is not in the stored value's bucket` for `period_start`, `KEEP_KM` for `coordinates`), and
    comparing it would have counted a `keep: 42.0465` against a `keep: 42.046332` as a
    disagreement - the harness inventing a difference instead of the model making a judgement. Only
    the whitespace around a value is normalised, because that is what the lane trims before it
    stores (`fields/answers.py`: "a trimmed, non-empty string"); whitespace *inside* a value is part
    of the value and stays a difference.
    """
    if not isinstance(fields, dict):
        return None
    units: list[tuple[str, str]] = []
    for name, row in fields.items():
        if not isinstance(row, dict) or "decision" not in row:
            return None
        decision = str(row["decision"])
        value = str(row.get("value") or "").strip() if decision == "replace" else ""
        units.append((str(name), f"{decision}: {value}" if value else decision))
    return tuple(units)


def _sources(text: str) -> tuple[str, ...]:
    """Every URL the answer cites, in the order it cites them."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ()
    urls: list[str] = []
    fields = data.get("fields")
    for group in (
        data.get("sentences"),
        data.get("kept"),
        data.get("members"),
        data.get("children"),
        (list(fields.values()) if isinstance(fields, dict) else None),
        [data],
    ):
        for row in group or []:
            for quote in (row.get("quotes") if isinstance(row, dict) else None) or []:
                # the older lanes cite a `url`, the identity stages a `source` (the URL of the page)
                url = (quote.get("url") or quote.get("source")) if isinstance(quote, dict) else None
                if isinstance(url, str) and url not in urls:
                    urls.append(url)
    return tuple(urls)


def copy_for_calibration(handoff: Path, out: Path, batches: Sequence[str]) -> dict[str, str]:
    """Copy `handoff` to `out` without the answers of `batches`, and return the recorded answer
    text per **label** (the site id the answer file is named after) of those batches.

    The copy is a real handoff directory, so the answering agent's own brief runs unchanged; only
    the answers of the calibrated batches are absent, which is what makes the re-answer a
    measurement. Answers of the *other* batches come along, so the lane's own `validate` sees a
    directory in progress exactly as a real one does.

    Only the calibrated batches' answers are recorded: a report of every answer in the handoff would
    be a file of hundreds of judgements nobody compares, and the batch id is not the label the
    answers are filed under.
    """
    if out.exists():
        raise DriverError(f"{out} exists: a calibration copy is written once")
    out.mkdir(parents=True)
    wanted = set(batches)
    recorded: dict[str, str] = {}
    for batch in sorted(p for p in handoff.iterdir() if p.is_dir()):
        target = out / batch.name
        target.mkdir()
        for file in sorted(batch.rglob("*")):
            if not file.is_file():
                continue
            relative = file.relative_to(batch)
            if file.name.endswith(".answer.json") and batch.name in wanted:
                recorded[file.name[: -len(".answer.json")]] = json.loads(
                    file.read_text(encoding="utf-8")
                )["text"]
                continue  # the calibrated batch is re-answered, not copied
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            (target / relative).write_bytes(file.read_bytes())
    return recorded


def compare_answers(
    lane: str, labels: Sequence[str], recorded: Mapping[str, str], fresh: Mapping[str, str]
) -> Calibration:
    """Compare the recorded answers with the fresh ones, unit by unit.

    A label whose fresh answer is missing is counted as unanswered, never as agreement: an agent
    that did not answer has not agreed with anything.
    """
    units = agreed = 0
    disagreements: list[Disagreement] = []
    unanswered: list[str] = []
    for label in labels:
        new_text = fresh.get(label)
        if new_text is None:
            unanswered.append(label)
            continue
        old_pairs = _verdicts(recorded[label]) if label in recorded else None
        new_pairs = _verdicts(new_text)
        if old_pairs is None or new_pairs is None:
            unanswered.append(label)
            continue
        old_map = dict(old_pairs)
        for unit, verdict in new_pairs:
            units += 1
            if old_map.get(unit) == verdict:
                agreed += 1
                continue
            disagreements.append(
                Disagreement(
                    label=label,
                    unit=unit,
                    recorded=old_map.get(unit, "<none>"),
                    fresh=verdict,
                    recorded_sources=_sources(recorded[label]),
                    fresh_sources=_sources(new_text),
                )
            )
    return Calibration(lane, tuple(labels), units, agreed, tuple(disagreements), tuple(unanswered))


# ------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcode-driver", description=__doc__.splitlines()[0])
    # `dest="command"`, not "lane": the `calibrate` subcommand has its own `--lane` (the lane *type*
    # being calibrated), and one dest for both would silently overwrite the subcommand name.
    lanes = parser.add_subparsers(dest="command", required=True)

    wd3 = lanes.add_parser("wd3", help="lane WD3 (structured-field fill): the JS pool, in Python")
    wd3.add_argument("--run", required=True, type=Path)
    wd3.add_argument("--handoff", required=True)
    wd3.add_argument("--pilot", action="store_true")
    wd3.add_argument("--resume", action="store_true")
    # Round 0 is the run's own population; 1 and 2 are the runbook's re-asks (step 10), each on its
    # own handoff and its own state file.
    wd3.add_argument("--round", type=int, default=0, help="0 = the population, 1 or 2 = a re-ask")
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

    cal = lanes.add_parser(
        "calibrate",
        help="O18: re-answer already-answered batches in a copy and compare (never in production)",
    )
    cal.add_argument("--lane", required=True, choices=("wc-check", "wc-verify", "fields"))
    cal.add_argument("--handoff", required=True, type=Path, help="an already-answered handoff dir")
    cal.add_argument("--out", required=True, type=Path, help="the copy to answer into")
    cal.add_argument("--batches", required=True, nargs="+", help="the batch ids to re-answer")
    cal.add_argument("--run", required=True, type=Path, help="the run the handoff belongs to")
    cal.add_argument("--width", type=int, default=WIDTH_START)
    cal.add_argument("--timeout", type=int, default=3600)
    cal.add_argument("--max-steps", type=int, default=200)
    cal.add_argument("--prepare-only", action="store_true", help="make the copy, answer nothing")
    cal.add_argument("--no-quota-check", action="store_true", help="skip the weekly quota stop")

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "wc":
        return _main_wc(args)
    if args.command == "calibrate":
        return _main_calibrate(args)
    return _main_wd3(args)


def calibration_run(out: Path) -> Path:
    """Where the calibration's own run lives - a function of the copy's path, so both halves of the
    calibration (`--prepare-only` and the answering run) name the same directory."""
    return out.with_name(out.name + "-run")


def _shown(path: Path) -> str:
    """The path as the records and the briefs write it: inside the repo relative with forward
    slashes, outside it absolute. The tool resolves a round record's handoff against the working
    directory, and every brief runs its command from the repo root."""
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def calibration_run_ready(run_dir: Path) -> bool:
    """Whether `run_dir` is a run whose round record the WC tool will read: a verification round in
    `verify/round-1/ROUND.json`, a check round in `ROUNDS.jsonl`. Measured 2026-10-03: the check
    calibration refused to start because the check looked for the verification file only - and the
    refusal was right, the round it had written is the other one."""
    return (run_dir / "verify" / "round-1" / "ROUND.json").exists() or (
        run_dir / "ROUNDS.jsonl"
    ).exists()


def _source_round(source_run: Path, source_handoff: Path) -> tuple[dict[str, Any], Path]:
    """The round record of `source_run` that registered `source_handoff`, and the file the run keeps
    it in: the check rounds in `ROUNDS.jsonl`, the verification rounds in `verify/round-N/ROUND.json`.
    The calibration run has to be written where the tool reads it from, or the guard refuses it the
    same way it refused the unregistered copy."""
    rounds = source_run / "ROUNDS.jsonl"
    if rounds.exists():
        for line in rounds.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if Path(record["handoff"]).resolve() == source_handoff.resolve():
                return record, rounds
    for round_dir in sorted((source_run / "verify").glob("round-*")):
        path = round_dir / "ROUND.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if Path(record["handoff"]).resolve() == source_handoff.resolve():
            return record, path
    raise DriverError(f"{source_handoff} is no round of {source_run}")


def register_calibration_run(
    source_run: Path, source_handoff: Path, out: Path, batches: Sequence[str]
) -> Path:
    """The run the calibration answers into: a directory of its own holding the source round's
    record, and return its path.

    Measured 2026-10-03: the WC tool accepts an answer only into a handoff that one of a run's
    rounds registers (`wc/cli.py:round_of` for a check, `_verify_round_of` for a verification). A
    calibration copy has no run, so the model refused to answer and reported the block - right of it,
    and the reason the report read 100 % over half its questions. Registering the copy as a round of
    the *production* run is no option: that run's import would read the comparison answers as
    verdicts about the sites.

    So the calibration gets a run of its own, with the same stage, the same questions and the same
    shown sentence numbers, and nothing but the calibrated batches in it: the copy holds every
    answered batch of the source, and the comparison must not touch the others. The round is marked
    `calibration`, which the import refuses, so a measurement can never reach a ledger.
    """
    record, where = _source_round(source_run, source_handoff)
    wanted = [batch for batch in batches if batch not in record["batches"]]
    if wanted:
        raise DriverError(
            f"{source_handoff}: no batch {', '.join(wanted)} in round {record['round']} of "
            f"{source_run}"
        )

    run_dir = calibration_run(out)
    if run_dir.exists():
        raise DriverError(f"{run_dir} exists: a calibration run is written once")
    run_dir.mkdir(parents=True)
    population = source_run / "POPULATION.json"
    kind = "wc"
    if population.exists():
        kind = json.loads(population.read_text(encoding="utf-8")).get("kind", kind)
    (run_dir / "POPULATION.json").write_text(
        json.dumps({"kind": kind}, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    labels = [label for batch in batches for label in record["batches"][batch]]
    calibration_round: dict[str, Any] = {
        "round": 1,
        "handoff": _shown(out),
        "exported_at": record.get("exported_at", ""),
        "batches": {batch: list(record["batches"][batch]) for batch in batches},
        "calibration": True,
        "calibrated_from": {
            "run": _shown(source_run),
            "handoff": _shown(source_handoff),
            "batches": list(batches),
        },
    }
    # A verification round names its stage and the sentence numbers it showed; a check round names
    # neither, and a fields round names the fields it asked per label. Each tool reads what its own
    # rounds carry, so the calibration round carries the same optional keys and nothing else.
    for key in ("stage", "shown", "fields"):
        if key in record:
            calibration_round[key] = (
                {label: list(record[key][label]) for label in labels}
                if key in ("shown", "fields")
                else record[key]
            )
    if where.name == "ROUNDS.jsonl":
        (run_dir / "ROUNDS.jsonl").write_text(
            json.dumps(calibration_round, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    else:
        (run_dir / "verify" / "round-1").mkdir(parents=True)
        (run_dir / "verify" / "round-1" / "ROUND.json").write_text(
            json.dumps(calibration_round, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    # A check round's answer check (`wc/cli.py:check_answer`) reads the run's sites, so the
    # calibration carries the sites of its own questions and nothing else. A verification round does
    # not read them: its check reads the round record alone.
    sites = source_run / "SITES.jsonl"
    if where.name == "ROUNDS.jsonl" and "fields" not in record and sites.exists():
        (run_dir / "SITES.jsonl").write_text(_labels_of(sites, labels), encoding="utf-8")
    # The field fill's own check reads the rule the run was built under and the classified sites, and
    # its round record names the fields per label. Copy what the calibration's own questions need.
    if "fields" in record:
        (run_dir / "RUN.json").write_bytes((source_run / "RUN.json").read_bytes())
        (run_dir / "CLASSIFIED.jsonl").write_text(
            _labels_of(source_run / "CLASSIFIED.jsonl", labels), encoding="utf-8"
        )
    return run_dir


def _labels_of(path: Path, labels: Sequence[str]) -> str:
    """The lines of a jsonl file whose `site_id` is one of `labels`, in the file's own order."""
    wanted = set(labels)
    return "".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line.strip() and json.loads(line).get("site_id") in wanted
    )


def fields_answer_prompt(*, run: str, handoff: str, batch: str) -> str:
    """One field-fill answering batch's instruction, from `fields/handoff.py brief`."""
    return answer_prompt(
        lane="fields",
        run=run,
        batch=batch,
        brief_command=(
            f"cd {WORKTREE} && PYTHONIOENCODING=utf-8 {PYTHON} {FIELDS / 'handoff.py'} brief "
            f"--run {run} --handoff {handoff} --batch-id {batch}"
        ),
    )


def calibration_prompt(*, lane: str, run: Path, handoff: Path, batch: str) -> str:
    """The prompt of one calibration batch, from the tool that owns the lane's questions.

    Measured 2026-10-03: the calibration built the WC brief for every lane type. For the field fill
    that is the wrong tool with the wrong arguments, and the agent is refused by the fields tool
    exactly as the WC calibration was on its first day.
    """
    if lane == "fields":
        return fields_answer_prompt(run=str(run), handoff=str(handoff), batch=batch)
    brief = "verify-brief" if lane == "wc-verify" else "brief"
    return wc_answer_prompt(run=run, handoff=handoff, batch=batch, brief=brief)


def _main_calibrate(args: Any) -> int:
    """Owner decision 2026-10-03 (O18): before any lane writes a MiniMax answer to production, the
    lane type must be calibrated. 2-3 already-answered batches are copied into a separate handoff
    directory, re-answered through the driver, and compared with the recorded answers. Pass is
    >= 90 % agreement and 0 false sources; a failing lane holds and goes to the owner."""
    cal_run = calibration_run(args.out)
    if args.prepare_only:
        recorded = copy_for_calibration(args.handoff, args.out, args.batches)
        (args.out / "RECORDED.json").write_text(
            json.dumps(recorded, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "prepared": str(args.out),
                    "calibration_run": str(
                        register_calibration_run(args.run, args.handoff, args.out, args.batches)
                    ),
                    "batches": list(args.batches),
                    "labels": sorted(recorded),
                    "questions": len(recorded),
                },
                indent=1,
            )
        )
        return 0

    recorded_path = args.out / "RECORDED.json"
    if not recorded_path.exists():
        print(
            json.dumps(
                {"ok": False, "error": f"{recorded_path} is missing: run this with --prepare-only"}
            ),
            file=sys.stderr,
        )
        return 1
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    if not calibration_run_ready(cal_run):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{cal_run} is missing: run this with --prepare-only, so the copy is a "
                    "round a registered run owns",
                }
            ),
            file=sys.stderr,
        )
        return 1

    width = Width.from_start(args.width)
    runner = McodeRunner(diagnostics=STATE_DIR / "calibration" / args.out.name)
    state = State(
        STATE_DIR / f"calibration-{args.out.name}.json",
        lane=f"calibration:{args.lane}",
        run=str(cal_run),
        handoff=str(args.out),
    )
    outcomes = answer_all(
        args.batches,
        prompt_for=lambda batch: calibration_prompt(
            lane=args.lane, run=cal_run, handoff=args.out, batch=batch
        ),
        runner=runner,
        width=width,
        state=state,
        timeout=args.timeout,
        max_steps=args.max_steps,
        quota_check=None if args.no_quota_check else _quota_check(),
        ledger=HandoffLedger(args.out),
    )
    # The comparison is per answer, not per batch: the answers are filed under the site id, so a
    # batch is a list of labels to compare, never one label itself.
    fresh: dict[str, str] = {}
    for batch in args.batches:
        for path in sorted((args.out / batch).rglob("*.answer.json")):
            fresh[path.name[: -len(".answer.json")]] = json.loads(path.read_text(encoding="utf-8"))[
                "text"
            ]
    report = compare_answers(args.lane, sorted(recorded), recorded, fresh).to_dict()
    report["batches"] = [
        {
            "batch": o.label,
            "due": o.due,
            "recorded": o.recorded,
            "executed": o.executed,
            "ok": o.ok,
            **({"reason": o.reason} if o.reason else {}),
        }
        for o in outcomes
    ]
    report["passed"] = bool(report["passed"]) and not any(not o.ok for o in outcomes)
    print(json.dumps(report, indent=1))
    return 0 if report["passed"] else 1


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
    plan = plan_wd3(
        run=args.run, handoff=Path(args.handoff), resume=args.resume, round_index=args.round
    )
    if not plan.batches:
        print(json.dumps({"batches": [], "exported": plan.exported, "note": "nothing exported"}))
        return 1
    if not check_batch_names(
        plan,
        [f"{plan.lane}-{plan.round_name}-b{n:04d}" for n in range(1, len(plan.batches) + 1)],
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

    # Which batches still owe an answer is the validator's answer, not the folders on disk: the
    # round was exported before, and 249 of its 327 batches are already answered (measured
    # 2026-10-03). `plan.batches` counts what exists, so answering it would re-answer every
    # answered batch and overwrite the answers the earlier rounds recorded. Lane WC reads it the
    # same way, and a handoff with stale, malformed or orphaned answers is refused here too.
    check = validate_handoff(plan.validate_dir)
    if not check.ok:
        print(json.dumps({"stopped": f"validate refused: {check.problems}"}), file=sys.stderr)
        return 1
    state = State(
        # One state file per round: round 0's answered batches are not round 1's, and a shared file
        # would make a re-ask resume past the questions it still owes. The lane is the round's own
        # (`wd4-r0-b0001` is wd4), so a wd4 run's history is not filed as a wd3 run's.
        STATE_DIR / f"{plan.lane}-{args.run.name}-{plan.round_name}.json",
        lane=plan.lane,
        run=str(args.run),
        handoff=args.handoff,
    )
    record_round(state, check, batches=len(plan.batches), done=not check.missing)
    if not check.missing:
        print(json.dumps({"batches": [], "note": "nothing missing"}))
        return 0

    width = Width.from_start(args.width)
    runner = McodeRunner()

    def prompt(label: str) -> str:
        return answer_prompt(
            lane="fields",
            run=str(args.run),
            batch=label,
            brief_command=(
                f"cd {WORKTREE} && PYTHONIOENCODING=utf-8 {PYTHON} {FIELDS / 'handoff.py'} brief "
                f"--run {args.run} --handoff {plan.validate_dir} --batch-id {label}"
            ),
        )

    try:
        outcomes = answer_all(
            check.missing,
            prompt_for=prompt,
            runner=runner,
            width=width,
            state=state,
            timeout=args.timeout,
            max_steps=args.max_steps,
            quota_check=None if args.no_quota_check else _quota_check(),
            ledger=HandoffLedger(plan.validate_dir),
            on_void=lambda outcome: print(
                json.dumps(
                    {
                        "stopped": outcome.reason or "void batch",
                        "label": outcome.label,
                        "due": outcome.due,
                        "recorded": outcome.recorded,
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
