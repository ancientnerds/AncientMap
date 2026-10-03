"""The driver that replaced Claude Code's Workflow tool (O22, owner decision 2026-10-03).

`scripts/remediation/orchestration/*.js` were Workflow-tool scripts: they drove a lane by asking a
model to run the operator's commands and report a shape, and by asking one more model per
answering batch. This module takes that over in plain Python - the operator steps are the commands
themselves, computed from the files on disk, and only the answering batches are a model call.

The tests here never call a model: `McodeRunner` takes the binary, so a fake script stands in.
What is tested is the driver's own logic - the stamp it records, what it keeps of a run, the
tracked-tree guard that voids a batch, the width governor, the quota stop, the resume, and one lane
state machine.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import mcode_driver as D  # noqa: E402

# ---------------------------------------------------------------------------- a fake `mcode`
FAKE = """\
import json, os, sys
# a fake `mcode exec`: records its argv and the prompt it reads on stdin, prints one JSON line,
# touches what the test asked for
Path = __import__("pathlib").Path
argv = sys.argv[1:]
prompt = sys.stdin.read()
Path(os.environ["FAKE_LOG"]).open("a", encoding="utf-8").write(
    json.dumps({"argv": argv, "prompt": prompt}) + "\\n")
payload = {"ok": True, "label": os.environ.get("FAKE_LABEL", "batch"), "steps": 1}
if os.environ.get("FAKE_FAIL"):
    sys.stderr.write("boom\\n")
    sys.exit(3)
touch = os.environ.get("FAKE_TOUCH")
if touch:
    Path(touch).write_text("the batch edited a tracked file\\n", encoding="utf-8")
record = os.environ.get("FAKE_RECORD")
if record:
    for n in range(int(os.environ.get("FAKE_RECORD_N", "0"))):
        Path(record, f"written-{n}.answer.json").write_text('{"text": "{}"}\\n', encoding="utf-8")
print("noise before the answer")
print(json.dumps(payload))
"""


def fake_mcode(tmp_path: Path, **env: str) -> tuple[Path, dict[str, str]]:
    """The fake on disk and the environment a driver run needs to find it.

    Windows runs a command through its extension, so the fake is a `.cmd` next to the real script
    (that is also how `mcode` itself is shimmed here) rather than an extensionless file.
    """
    script = tmp_path / "fake_mcode.py"
    script.write_text(FAKE, encoding="utf-8")
    binary = tmp_path / "fake-mcode.cmd"
    binary.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    log = tmp_path / "argv.jsonl"
    full = {"PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "FAKE_LOG": str(log)}
    full.update(env)
    return binary, full


def argv_of(tmp_path: Path) -> list[dict[str, Any]]:
    log = tmp_path / "argv.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------- the stamp and the route
def test_the_answer_stamp_is_the_minimax_model_and_the_route_is_the_minimax_endpoint() -> None:
    """Two different strings, for two different programs: `opus_handoff.answer --model` takes the
    model id as the agent's own system prompt names it, `mcode exec --model` takes the provider
    route. Writing the route into an answer would name a model that never answered."""
    import opus_handoff as OH

    assert D.ANSWER_STAMP_MODEL in OH.ANSWER_MODELS
    assert D.ANSWER_STAMP_MODEL == "MiniMax-M3.1-Flash-Preview"
    assert D.EXEC_MODEL == "minimax/MiniMax-M3.1-Flash-Preview"
    assert OH.ANSWER_MODELS[D.ANSWER_STAMP_MODEL] == OH.MINIMAX_MODEL


# ---------------------------------------------------------------------------- one answering batch
def test_a_batch_keeps_its_exec_json_exit_code_and_diagnostics(tmp_path: Path) -> None:
    binary, env = fake_mcode(tmp_path, FAKE_LABEL="wd3-r0-b0007")
    diagnostics = tmp_path / "diag"
    runner = D.McodeRunner(binary=binary, repo=tmp_path, diagnostics=diagnostics, env=env)

    result = runner.run("the agent prompt", label="wd3-r0-b0007", timeout=60, max_steps=4)

    assert result.exit_code == 0
    assert result.ok is True
    assert result.payload == {"ok": True, "label": "wd3-r0-b0007", "steps": 1}
    # one diagnostics directory per batch, so a run is read one batch at a time
    assert result.diagnostics == diagnostics / "wd3-r0-b0007"
    assert result.diagnostics.is_dir()
    assert (result.diagnostics / "stdout.txt").read_text(encoding="utf-8").startswith("noise")
    # every flag `mcode exec` really has (checked against `mcode exec --help`, 2026-10-03), and the
    # prompt on stdin rather than on the command line
    (call,) = argv_of(tmp_path)
    argv = call["argv"]
    assert argv[0] == "exec"
    assert argv[argv.index("--cwd") + 1] == str(tmp_path)
    assert argv[argv.index("--model") + 1] == D.EXEC_MODEL
    assert argv[argv.index("--effort") + 1] in {"max", "high", "medium", "low"}
    assert argv[argv.index("--permission") + 1] == "full"
    assert argv[argv.index("--timeout") + 1] == "60s"  # a duration, not a bare number
    assert argv[argv.index("--max-steps") + 1] == "4"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--diagnostics-dir") + 1] == str(diagnostics / "wd3-r0-b0007")
    assert argv[argv.index("--input") + 1] == "-"
    assert "--label" not in argv  # `mcode exec` has no such flag
    assert "the agent prompt" in call["prompt"]


def test_the_mcode_command_runs_through_the_shim_this_platform_needs() -> None:
    """On Windows the `mcode` on PATH is a `.cmd`/`.ps1` shim and `CreateProcess` runs neither, so
    the command processor is asked to run it. Measured 2026-10-03: `subprocess.run(["mcode", ...])`
    answers `FileNotFoundError: [WinError 2]` - not a permissions problem, a missing interpreter.
    """
    argv = D.mcode_argv("exec", "--input", "-")

    if os.name == "nt":
        assert Path(argv[0]).name.lower() in {"cmd.exe", "cmd"}
        assert argv[1:4] == ["/d", "/c", "mcode"]
    else:
        assert argv == ["mcode", "exec", "--input", "-"]


def test_a_failed_batch_is_kept_with_its_exit_code_and_is_not_ok(tmp_path: Path) -> None:
    binary, env = fake_mcode(tmp_path, FAKE_FAIL="1")
    runner = D.McodeRunner(binary=binary, repo=tmp_path, diagnostics=tmp_path / "d", env=env)

    result = runner.run("prompt", label="b", timeout=60, max_steps=4)

    assert result.exit_code == 3
    assert result.ok is False
    assert "boom" in result.stderr


def test_a_run_that_exits_zero_but_failed_is_not_a_success(tmp_path: Path) -> None:
    """`mcode exec --output-format json` answers an `exec.result` with a `status` and no `ok`, so a
    run that failed inside - a refused permission, a step limit - exits 0. Reading only the exit
    code would count it as answered."""
    failed = D.ExecResult(
        exit_code=0,
        ok=True,
        payload={"type": "exec.result", "status": "failed", "error": "step limit reached"},
        stdout="",
        stderr="",
        diagnostics=tmp_path / "d",
    )
    assert failed.succeeded is False

    ran = D.ExecResult(
        exit_code=0,
        ok=True,
        payload={"type": "exec.result", "status": "succeeded", "output": "done"},
        stdout="",
        stderr="",
        diagnostics=tmp_path / "d",
    )
    assert ran.succeeded is True


def test_a_rate_limited_batch_is_told_apart_from_another_failure(tmp_path: Path) -> None:
    """The width governor halves on a rate limit only; a batch that failed for any other reason
    must not be mistaken for one."""
    binary, env = fake_mcode(tmp_path, FAKE_FAIL="1")
    runner = D.McodeRunner(binary=binary, repo=tmp_path, diagnostics=tmp_path / "d", env=env)
    assert runner.run("p", label="b", timeout=60, max_steps=4).rate_limited is False

    limited = D.ExecResult(
        exit_code=429,
        ok=False,
        payload={},
        stdout="",
        stderr="429 Too Many Requests: rate limit exceeded",
        diagnostics=tmp_path / "d",
    )
    assert limited.rate_limited is True
    assert (
        D.ExecResult(
            exit_code=1, ok=False, payload={}, stdout="", stderr="boom", diagnostics=tmp_path / "d"
        ).rate_limited
        is False
    )


# ---------------------------------------------------------------------------- the tracked-tree guard
def test_the_tree_guard_reports_only_tracked_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "output").mkdir(parents=True)
    D.run_git(repo, "init")
    D.run_git(repo, "config", "user.email", "driver@example.com")
    D.run_git(repo, "config", "user.name", "mcode driver test")
    (repo / "tracked.txt").write_text("a\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("scratch\n", encoding="utf-8")
    D.run_git(repo, "add", "tracked.txt")
    D.run_git(repo, "commit", "-m", "the tree the lane starts from")

    assert D.tracked_changes(repo) == ""  # an untracked scratch file is the lane's own working data

    (repo / "tracked.txt").write_text("b\n", encoding="utf-8")
    assert "tracked.txt" in D.tracked_changes(repo)


def test_a_batch_that_changed_a_tracked_file_voids_itself_and_stops(tmp_path: Path) -> None:
    """Measured 2026-10-01: an M3.1 run rewrote a check file. A batch whose agent edited a tracked
    file may have changed the lane's own rules, so its answers are not trusted and the lane stops
    before the next batch."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    D.run_git(repo, "init")
    D.run_git(repo, "config", "user.email", "driver@example.com")
    D.run_git(repo, "config", "user.name", "mcode driver test")
    tracked = repo / "scripts" / "check.py"
    tracked.write_text("original\n", encoding="utf-8")
    D.run_git(repo, "add", "scripts/check.py")
    D.run_git(repo, "commit", "-m", "the lane's own rules, committed")
    binary, env = fake_mcode(tmp_path, FAKE_TOUCH=str(tracked))
    runner = D.McodeRunner(binary=binary, repo=repo, diagnostics=tmp_path / "d", env=env)

    result = runner.run("prompt", label="b", timeout=60, max_steps=4)

    assert result.tree_clean is False
    assert "scripts/check.py" in result.tree_changed
    assert runner.voids(result) is True


# ---------------------------------------------------------------------------- did the batch answer?
def a_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    D.run_git(repo, "init")
    D.run_git(repo, "config", "user.email", "driver@example.com")
    D.run_git(repo, "config", "user.name", "mcode driver test")
    (repo / "keep.txt").write_text("a\n", encoding="utf-8")
    D.run_git(repo, "add", "keep.txt")
    D.run_git(repo, "commit", "-m", "the tree the lane starts from")
    return repo


def a_handoff(tmp_path: Path, batches: Sequence[str], labels: int, answered: int = 0) -> Path:
    """A handoff with `batches`, each `labels` questions, the first `answered` of them recorded."""
    handoff = tmp_path / "handoff"
    for batch in batches:
        stage = handoff / batch / "verify"
        stage.mkdir(parents=True, exist_ok=True)
        for n in range(labels):
            label = f"site-{n:02d}"
            (stage / f"{label}.prompt.txt").write_text("the question\n", encoding="utf-8")
            if n < answered:
                (stage / f"{label}.answer.json").write_text('{"text": "{}"}\n', encoding="utf-8")
    return handoff


def test_a_batch_that_records_nothing_is_a_failure_and_not_a_finished_batch(tmp_path: Path) -> None:
    """Measured 2026-10-03, calibration `wc-verify-01` / `verify-0001`: the model refused to answer
    (the WC tool's own round guard rejected the calibration handoff), ended its turn with
    `status: succeeded` and exit 0, and recorded nothing. Counted as a finished batch it made the
    report read 100 % agreement over half the questions."""
    handoff = a_handoff(tmp_path, ["verify-0001"], labels=5)
    binary, env = fake_mcode(tmp_path)
    runner = D.McodeRunner(
        binary=binary, repo=a_repo(tmp_path), diagnostics=tmp_path / "d", env=env
    )
    state = D.State(tmp_path / "state.json", lane="test", run="r", handoff=str(handoff))

    outcomes = D.answer_all(
        ["verify-0001"],
        prompt_for=lambda batch: f"answer {batch}",
        runner=runner,
        width=D.Width(start=2, cap=2, ram_cap=lambda: 8),
        state=state,
        timeout=60,
        max_steps=4,
        ledger=D.HandoffLedger(handoff),
    )

    (only,) = outcomes
    assert only.ok is False
    assert (only.due, only.recorded) == (5, 0)
    assert "0 of 5" in only.reason
    # a resume has to try it again: the batch was never answered
    assert state.get("answered", []) == []


def test_a_batch_that_records_part_of_its_questions_is_a_failure(tmp_path: Path) -> None:
    handoff = a_handoff(tmp_path, ["verify-0001"], labels=5)
    binary, env = fake_mcode(
        tmp_path,
        FAKE_RECORD=str(handoff / "verify-0001" / "verify"),
        FAKE_RECORD_N="2",
    )
    runner = D.McodeRunner(
        binary=binary, repo=a_repo(tmp_path), diagnostics=tmp_path / "d", env=env
    )
    state = D.State(tmp_path / "state.json", lane="test", run="r", handoff=str(handoff))

    (only,) = D.answer_all(
        ["verify-0001"],
        prompt_for=lambda batch: f"answer {batch}",
        runner=runner,
        width=D.Width(start=1, cap=1, ram_cap=lambda: 8),
        state=state,
        timeout=60,
        max_steps=4,
        ledger=D.HandoffLedger(handoff),
    )

    assert only.ok is False
    assert (only.due, only.recorded) == (5, 2)
    assert "2 of 5" in only.reason


def test_a_batch_that_owes_nothing_is_not_run_at_all(tmp_path: Path) -> None:
    """A batch whose questions are all recorded has nothing to answer. Sending an agent there
    spends quota to be told so, and its 'nothing to do' would read as a batch that recorded
    nothing."""
    handoff = a_handoff(tmp_path, ["verify-0001"], labels=5, answered=5)
    binary, env = fake_mcode(tmp_path)
    runner = D.McodeRunner(
        binary=binary, repo=a_repo(tmp_path), diagnostics=tmp_path / "d", env=env
    )
    state = D.State(tmp_path / "state.json", lane="test", run="r", handoff=str(handoff))

    (only,) = D.answer_all(
        ["verify-0001"],
        prompt_for=lambda batch: f"answer {batch}",
        runner=runner,
        width=D.Width(start=1, cap=1, ram_cap=lambda: 8),
        state=state,
        timeout=60,
        max_steps=4,
        ledger=D.HandoffLedger(handoff),
    )

    assert only.ok is True
    assert only.executed is False
    assert argv_of(tmp_path) == []  # no exec at all
    assert state.get("answered", []) == ["verify-0001"]


def test_a_stopped_batch_does_not_start_the_batches_queued_behind_it(tmp_path: Path) -> None:
    """The stop has to be a stop: a lane of 100 batches must not run 98 of them after the third
    records nothing. Only the window in flight may still finish."""
    handoff = a_handoff(tmp_path, [f"verify-{n:04d}" for n in range(1, 5)], labels=1)
    binary, env = fake_mcode(tmp_path)
    runner = D.McodeRunner(
        binary=binary, repo=a_repo(tmp_path), diagnostics=tmp_path / "d", env=env
    )
    state = D.State(tmp_path / "state.json", lane="test", run="r", handoff=str(handoff))

    outcomes = D.answer_all(
        [f"verify-{n:04d}" for n in range(1, 5)],
        prompt_for=lambda batch: f"answer {batch}",
        runner=runner,
        width=D.Width(start=2, cap=2, ram_cap=lambda: 8),
        state=state,
        timeout=60,
        max_steps=4,
        ledger=D.HandoffLedger(handoff),
    )

    assert [o.label for o in outcomes] == ["verify-0001"]
    assert len(argv_of(tmp_path)) == 2  # the window, not the lane


def test_the_ram_reader_sees_the_memory_of_this_machine() -> None:
    """Measured 2026-10-03: the reader shelled out to `wmic`, which this Windows no longer ships,
    so it answered 0.0 on every call and the width cap never bound - silently."""
    assert D.free_ram_gb() > 0


def test_the_ram_reader_parses_the_linux_meminfo_line() -> None:
    assert D._free_ram_gb_from_meminfo("MemTotal: 16000000 kB\nMemFree: 200 kB\n") == 0.0
    assert D._free_ram_gb_from_meminfo("MemAvailable: 8000000 kB\n") == pytest.approx(
        7.629, abs=1e-3
    )


class _CountingLedger:
    """A ledger that counts nothing real and remembers only when it was asked."""

    def __init__(self, order: list[tuple[str, str]]) -> None:
        self.order = order

    def open(self, batch: str) -> int:
        self.order.append(("open", batch))
        return 1

    def answered(self, batch: str) -> int:
        self.order.append(("answered", batch))
        return 0


class _RecordingRunner:
    """A runner that records only when it was asked to run."""

    def __init__(self, order: list[tuple[str, str]]) -> None:
        self.order = order

    def run(self, prompt: str, **kwargs: Any) -> D.ExecResult:
        self.order.append(("run", str(kwargs.get("label"))))
        return D.ExecResult(0, True, {}, "", "", Path("."))

    def voids(self, result: D.ExecResult) -> bool:
        return False


def test_the_answers_are_counted_before_the_batch_runs(tmp_path: Path) -> None:
    """Measured 2026-10-03, calibration `wc-verify-02`: the count of what a batch had already
    recorded was read *after* its exec was submitted. A batch that answers quickly had written its
    five files before the driver counted them, so a complete batch read as `recorded 0 of 5` - a
    false failure that stops the lane and leaves its questions unanswered."""
    order: list[tuple[str, str]] = []
    state = D.State(tmp_path / "state.json", lane="test", run="r", handoff="h")

    D.answer_all(
        ["verify-0001", "verify-0002"],
        prompt_for=lambda batch: f"answer {batch}",
        runner=_RecordingRunner(order),
        width=D.Width(start=2, cap=2, ram_cap=lambda: 8),
        state=state,
        timeout=60,
        max_steps=4,
        ledger=_CountingLedger(order),
    )

    first_run = next(i for i, entry in enumerate(order) if entry[0] == "run")
    counted_before = [entry for entry in order[:first_run] if entry[0] == "answered"]
    assert counted_before == [("answered", "verify-0001"), ("answered", "verify-0002")], (
        f"a batch was counted after it ran: {order}"
    )


# ---------------------------------------------------------------------------- the width governor
def test_the_width_starts_at_two_and_grows_by_one_per_clean_window() -> None:
    """Owner decision 2026-10-03 (O22): start at 2, add one concurrent run after each window
    without a rate-limit error, halve on the first one, cap by local RAM."""
    width = D.Width(start=2, cap=14, ram_cap=lambda: 14)
    assert width.value == 2
    assert width.next_window() == 2  # nothing ran yet
    width.window_clean()
    assert width.value == 3
    width.window_clean()
    assert width.value == 4


def test_the_width_halves_on_the_first_rate_limit_and_never_under_one() -> None:
    width = D.Width(start=4, cap=14, ram_cap=lambda: 14)
    width.rate_limited()
    assert width.value == 2
    width.rate_limited()
    assert width.value == 1
    width.rate_limited()
    assert width.value == 1  # one run at a time is the floor


def test_the_width_never_exceeds_the_ram_cap() -> None:
    width = D.Width(start=2, cap=14, ram_cap=lambda: 3)
    for _ in range(10):
        width.window_clean()
    assert width.value == 3


# ---------------------------------------------------------------------------- the quota stop
def test_the_quota_stop_reads_the_weekly_remaining_percent(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def fetch(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        return {"current_weekly_remaining_percent": 42}

    env_file = tmp_path / ".env"
    env_file.write_text("LYRA_MINIMAX_API_KEY=secret-key-value\n", encoding="utf-8")

    percent = D.quota_remaining(env_file=env_file, fetch=fetch)

    assert percent == 42
    assert seen["url"] == "https://api.minimax.io/v1/token_plan/remains"
    # `Authorization: Bearer <key>` - a bare key answers "login fail" (owner, measured 2026-10-03)
    assert seen["auth"] == "Bearer secret-key-value"
    assert D.quota_exhausted(10.0) is True  # <= 10 percent stops
    assert D.quota_exhausted(10.5) is False


def test_the_quota_key_is_read_out_of_a_crlf_quoted_env_line(tmp_path: Path) -> None:
    """`.env` is written on Windows, so its lines end CRLF, and a value may be quoted. A `\\r` left
    on the key would travel in the Authorization header; the quotes are not part of the key. Both
    would read as a wrong key to the endpoint (owner, measured 2026-10-03)."""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b'# a comment\r\nLYRA_MINIMAX_API_KEY="quoted-key"\r\nOTHER=x\r\n')
    seen: dict[str, str] = {}

    def fetch(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        seen["auth"] = headers["Authorization"]
        return {"current_weekly_remaining_percent": 77}

    assert D.quota_remaining(env_file=env_file, fetch=fetch) == 77
    assert seen["auth"] == "Bearer quoted-key"
    assert "\r" not in seen["auth"]


def test_the_quota_stop_reads_the_weekly_percent_of_the_model_the_driver_uses(
    tmp_path: Path,
) -> None:
    """The endpoint reports one entry per model, not one number (measured 2026-10-03: `general`
    at 77, `video` at 100). The driver answers with the coding model, so it reads that entry: a
    driver that read the first entry, or averaged them, would report a plan that never runs out."""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"LYRA_MINIMAX_API_KEY=key\r\n")
    seen: dict[str, str] = {}

    def fetch(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        seen["auth"] = headers["Authorization"]
        return {
            "model_remains": [
                {"model_name": "video", "current_weekly_remaining_percent": 100},
                {"model_name": "general", "current_weekly_remaining_percent": 77},
            ],
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }

    assert D.quota_remaining(env_file=env_file, fetch=fetch) == 77
    assert D.quota_exhausted(D.quota_remaining(env_file=env_file, fetch=fetch)) is False
    assert seen["auth"] == "Bearer key"


def test_a_quota_payload_without_the_model_the_driver_uses_stops_the_driver(tmp_path: Path) -> None:
    """Silently using another model's plan is the one wrong answer here, so it is a refusal."""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"LYRA_MINIMAX_API_KEY=key\r\n")

    with pytest.raises(D.DriverError, match="general"):
        D.quota_remaining(
            env_file=env_file,
            fetch=lambda *a, **k: {
                "model_remains": [{"model_name": "video", "current_weekly_remaining_percent": 100}],
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )


def test_a_missing_key_stops_the_driver_instead_of_calling_without_one() -> None:
    env_file = Path(os.devnull)
    with pytest.raises(D.DriverError, match=D.QUOTA_KEY_NAME):
        D.quota_remaining(env_file=env_file, fetch=lambda *a, **k: {})


def test_the_quota_key_is_the_one_the_lyra_pipeline_uses() -> None:
    """No second secret is involved: the same key serves the Anthropic-compatible route and the
    quota endpoint, and only the header format differs (owner, measured 2026-10-03)."""
    assert D.QUOTA_KEY_NAME == "LYRA_MINIMAX_API_KEY"
    assert D.QUOTA_AUTH_PREFIX == "Bearer "


def test_a_key_the_quota_endpoint_refuses_stops_the_driver_and_names_the_variable(
    tmp_path: Path,
) -> None:
    """Measured 2026-10-03: the repo's key is the Anthropic-compatible one, and the quota endpoint
    refuses it with `login fail`. The driver must stop - running a lane without a quota check would
    break owner decision O20 - and the refusal must name the variable to set, never its value."""
    env_file = tmp_path / ".env"
    env_file.write_text("LYRA_MINIMAX_API_KEY=not-the-key\n", encoding="utf-8")
    seen: dict[str, str] = {}

    def fetch(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        seen["auth"] = headers["Authorization"]
        return {
            "base_resp": {
                "status_code": 1004,
                "status_msg": "login fail: Please carry the API secret key in the 'Authorization' field",
            }
        }

    with pytest.raises(D.DriverError) as caught:
        D.quota_remaining(env_file=env_file, fetch=fetch)

    message = str(caught.value)
    assert D.QUOTA_KEY_NAME in message
    assert "Bearer" in message  # the header format is the thing to check
    assert "not-the-key" not in message  # the value is never in the refusal
    assert seen["auth"] == "Bearer not-the-key"  # but it did travel in the header


def test_the_quota_variable_name_can_be_chosen(tmp_path: Path) -> None:
    """A repo may hold the key under its own name; the driver asks for one."""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"MINIMAX_KEY=k\r\nOTHER_KEY=w\r\n")
    assert (
        D.quota_remaining(
            env_file=env_file,
            key_name="OTHER_KEY",
            fetch=lambda *a, **k: {"current_weekly_remaining_percent": 55},
        )
        == 55
    )


# ---------------------------------------------------------------------------- the resume
def test_a_lane_resumes_from_its_state_file(tmp_path: Path) -> None:
    state = D.State(tmp_path / "state.json", lane="wd3", run="wd3-run", handoff="fields-wd3")
    state.put("answered", ["wd3-r0-b0001", "wd3-r0-b0002"])

    again = D.State(tmp_path / "state.json", lane="wd3", run="wd3-run", handoff="fields-wd3")
    assert again.get("answered") == ["wd3-r0-b0001", "wd3-r0-b0002"]
    # a state file of another lane or another run is never reused
    other = D.State(tmp_path / "state.json", lane="wc", run="wd3-run", handoff="fields-wd3")
    assert not other.get("answered")


# ---------------------------------------------------------------------------- one lane state machine
def test_wd3_on_resume_does_not_export_again_and_answers_only_what_is_missing(
    tmp_path: Path,
) -> None:
    """The WD3 pool on resume (`wd3-handoff-pool --resume`) counts the exported round instead of
    exporting it again, then answers the batches the validate run names missing."""
    handoff = tmp_path / "fields-wd3-r0"
    for batch in ("wd3-r0-b0001", "wd3-r0-b0002", "wd3-r0-b0003"):
        (handoff / batch).mkdir(parents=True)
        (handoff / batch / "MANIFEST.jsonl").write_text("{}\n", encoding="utf-8")
    binary, env = fake_mcode(tmp_path)

    plan = D.plan_wd3(run=tmp_path / "run", handoff=tmp_path / "fields-wd3", resume=True)

    assert plan.exported is False  # no export command on resume
    assert list(plan.batches) == ["wd3-r0-b0001", "wd3-r0-b0002", "wd3-r0-b0003"]
    assert plan.validate_dir == handoff
    # the batch ids are built from the count and checked against the names on disk
    assert plan.batch_names_ok([f"wd3-r0-b{n:04d}" for n in (1, 2, 3)]) is True
    assert plan.batch_names_ok(["wd3-r0-b0001", "wd3-r0-b0002"]) is False


def test_wd3_without_resume_exports_the_first_round(tmp_path: Path) -> None:
    plan = D.plan_wd3(run=tmp_path / "run", handoff=tmp_path / "fields-wd3", resume=False)

    assert plan.exported is True
    assert plan.export_command[2] == "export"  # <python> <fields/handoff.py> export ...
    assert "--handoff" in plan.export_command
    assert plan.batches == ()  # the count comes from the export, not from the files
    assert no_model_call(plan.export_command) is True


def no_model_call(command: Sequence[str]) -> bool:
    """A plan names no model call: the operator steps are the commands themselves."""
    return not any("mcode" in part for part in command)


# ---------------------------------------------------------------------------- the answer prompt
def test_the_answer_prompt_names_the_minimax_stamp_and_its_own_working_directory(
    tmp_path: Path,
) -> None:
    """The prompt is the JS script's, with the two model strings replaced: the brief command, the
    scratch directory rule, and the stamp the answer is recorded with."""
    prompt = D.answer_prompt(
        lane="wd3",
        run="wd3-run",
        batch="wd3-r0-b0007",
        repo="C:/PythonProjects/AncientMap",
        python="C:/PythonProjects/AncientMap/.venv/Scripts/python.exe",
        brief="brief",
    )

    assert "MiniMax-M3.1-Flash-Preview" in prompt
    assert "--model claude-sonnet-5-5" not in prompt
    assert "opus_handoff.py answer" in prompt
    assert "C:/PythonProjects/AncientMap" in prompt
    assert "wd3-r0-b0007" in prompt
