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
# a fake `mcode exec`: records its argv, prints one JSON line, touches what the test asked for
argv = sys.argv[1:]
Path = __import__("pathlib").Path
Path(os.environ["FAKE_LOG"]).open("a", encoding="utf-8").write(json.dumps(argv) + "\\n")
payload = {"ok": True, "label": os.environ.get("FAKE_LABEL", "batch"), "steps": 1}
if os.environ.get("FAKE_FAIL"):
    sys.stderr.write("boom\\n")
    sys.exit(3)
touch = os.environ.get("FAKE_TOUCH")
if touch:
    Path(touch).write_text("the batch edited a tracked file\\n", encoding="utf-8")
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


def argv_of(tmp_path: Path) -> list[list[str]]:
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
    # every flag the Workflow tool used, and the two model strings of their own
    (call,) = argv_of(tmp_path)
    assert "--cwd" in call and str(tmp_path) in call
    assert call[call.index("--model") + 1] == D.EXEC_MODEL
    assert call[call.index("--effort") + 1] in {"max", "high", "medium", "low"}
    assert call[call.index("--permission") + 1] == "full"
    assert call[call.index("--timeout") + 1] == "60"
    assert call[call.index("--max-steps") + 1] == "4"
    assert call[call.index("--output-format") + 1] == "json"
    assert call[call.index("--diagnostics-dir") + 1] == str(diagnostics / "wd3-r0-b0007")
    assert "the agent prompt" in call[call.index("--prompt") + 1]


def test_a_failed_batch_is_kept_with_its_exit_code_and_is_not_ok(tmp_path: Path) -> None:
    binary, env = fake_mcode(tmp_path, FAKE_FAIL="1")
    runner = D.McodeRunner(binary=binary, repo=tmp_path, diagnostics=tmp_path / "d", env=env)

    result = runner.run("prompt", label="b", timeout=60, max_steps=4)

    assert result.exit_code == 3
    assert result.ok is False
    assert "boom" in result.stderr


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
    assert "secret-key-value" in seen["auth"]  # the key goes in the header, nowhere else
    assert D.quota_exhausted(10.0) is True  # <= 10 percent stops
    assert D.quota_exhausted(10.5) is False


def test_a_missing_key_stops_the_driver_instead_of_calling_without_one() -> None:
    env_file = Path(os.devnull)
    with pytest.raises(D.DriverError, match="LYRA_MINIMAX_API_KEY"):
        D.quota_remaining(env_file=env_file, fetch=lambda *a, **k: {})


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
