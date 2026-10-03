"""The `mcode exec` runner: the real model stamp, the 429, the weekly quota, the git guard.

Owner decision 2026-10-03: the studio's judgements run on MiniMax Code (`mcode`, model
`MiniMax-M3.1-Flash-Preview`). These tests drive `mcode.exec` with a fake `subprocess.run`,
so they need no MiniMax account and no network.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from pipeline.studio import mcode
from pipeline.studio.errors import StudioError
from tests import git_env

OK = {
    "schemaVersion": 1,
    "type": "exec.result",
    "runId": "exec_turn_a_1",
    "sessionId": "mvs_b_2",
    "status": "succeeded",
    "output": "I read the file.",
    "model": {"providerId": "minimax", "modelId": "MiniMax-M3.1-Flash-Preview"},
    "usage": {"inputTokens": 21001, "outputTokens": 12, "totalTokens": 21013},
    "durationMs": 3189,
}


def _exe(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "mcode.cmd"
    path.write_text("@echo off\r\n", encoding="utf-8")
    monkeypatch.setenv(mcode.EXE_ENV, str(path))
    return path


class _FakeProc:
    """A `Popen` that answers at once, or that never answers at all."""

    def __init__(self, argv: list[str], returncode: int, *, hang: bool, kill_hangs: bool = False):
        self.argv = argv
        self.returncode = returncode
        self.pid = 4242
        self.killed = False
        self._hang = hang
        self._kill_hangs = kill_hangs
        self.waits: list[float | None] = []

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        if self._hang and not self.killed:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        if self._hang and self.killed and self._kill_hangs:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - the tree kill is what runs
        self.killed = True


def _calls(
    monkeypatch,
    *,
    returncode: int = 0,
    stdout: str | None = None,
    stderr: str = "",
    hang: bool = False,
    kill_hangs: bool = False,
):
    """Fake `subprocess.Popen`; returns the argv and the prompt of every call.

    The fake writes its output into the file objects the driver handed it and reads the
    prompt back out of the file it was given as stdin, so a test sees the same traffic a
    real run does.
    """
    seen: list[list[str]] = []
    fed: list[str] = []
    procs: list[_FakeProc] = []

    def fake_popen(argv, **kwargs):
        seen.append(list(argv))
        stdin, out, err = kwargs["stdin"], kwargs["stdout"], kwargs["stderr"]
        fed.append(stdin.read())
        out.write(json.dumps(OK) if stdout is None else stdout)
        err.write(stderr)
        proc = _FakeProc(
            list(argv), returncode, hang=hang, kill_hangs=kill_hangs
        )
        procs.append(proc)
        return proc

    monkeypatch.setattr(mcode.subprocess, "Popen", fake_popen)
    return _Calls(seen, fed, procs)


class _Calls:
    """The argv, the prompt and the process of every `mcode exec` the driver made."""

    def __init__(self, args: list[list[str]], fed: list[str], procs: list[_FakeProc]):
        self._args = args
        self._fed = fed
        self._procs = procs

    def __getitem__(self, index: int):
        return self._args[index]

    def __len__(self) -> int:
        return len(self._args)

    @property
    def stdin(self) -> str:
        return self._fed[0]

    @property
    def procs(self) -> list[_FakeProc]:
        return self._procs


def test_the_run_calls_mcode_with_the_owner_model_effort_and_json_output(tmp_path, monkeypatch):
    exe = _exe(tmp_path, monkeypatch)
    seen = _calls(monkeypatch)

    mcode.exec("Do the check.", cwd=tmp_path)

    argv = seen[0]
    assert argv[0] == str(exe)
    assert argv[1:4] == ["exec", "--cwd", str(tmp_path)]
    assert (
        "--model" in argv
        and argv[argv.index("--model") + 1] == "minimax/MiniMax-M3.1-Flash-Preview"
    )
    assert argv[argv.index("--effort") + 1] == "max"  # owner decision O23
    assert argv[argv.index("--permission") + 1] == "full"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--input") + 1] == "-"
    assert seen.stdin == "Do the check."


def test_a_multi_line_prompt_travels_on_stdin_never_as_an_argv_element(tmp_path, monkeypatch):
    """The `mcode.cmd` batch wrapper forwards `%*` through `CALL`, and cmd.exe ends a
    command at the first newline inside an argument - a prompt as argv reached the model
    as its first paragraph only, and the batch of 2026-10-03 13:40:12Z wrote no answer at
    all. Nothing multi-line may be an argument any more.
    """
    _exe(tmp_path, monkeypatch)
    seen = _calls(monkeypatch)
    prompt = "You are the verifier of one claim-check task.\n\nTask: evidence-ec5c850de315\nRule: 1. read it.\n"

    mcode.exec(prompt, cwd=tmp_path)

    assert seen.stdin == prompt
    assert prompt.splitlines()[0] not in seen[0]
    assert not any("\n" in arg for arg in seen[0])


def test_the_run_never_waits_on_a_pipe_a_lingering_grandchild_holds_open(tmp_path, monkeypatch):
    """Measured 2026-10-03 16:08: the three runs of one wave never returned. Their `node`
    children sat in a ~1 % CPU poll on a hung provider socket, and `subprocess.run` with
    `capture_output=True` never saw EOF: the pipes stayed open, so the timeout in its
    `communicate()` could not fire and the whole batch was frozen for three and a half
    hours. Prompt, stdout and stderr therefore travel on files, and only the process's own
    exit is waited for.
    """
    _exe(tmp_path, monkeypatch)
    seen: list[dict] = []
    fed: list[str] = []

    def fake_popen(argv, **kwargs):
        seen.append(kwargs)
        fed.append(kwargs["stdin"].read())
        kwargs["stdout"].write(json.dumps(OK))
        return _FakeProc(list(argv), 0, hang=False)

    monkeypatch.setattr(mcode.subprocess, "Popen", fake_popen)

    mcode.exec("Do the check.", cwd=tmp_path)

    handles = seen[0]
    for name in ("stdin", "stdout", "stderr"):
        handle = handles[name]
        assert hasattr(handle, "read") or hasattr(handle, "write")
        assert not isinstance(handle, int)  # never subprocess.PIPE
    assert fed == ["Do the check."]  # the whole prompt went through the file


def test_a_run_that_overruns_its_bound_kills_its_tree_and_answers_nothing(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    seen = _calls(monkeypatch, hang=True)
    killed: list[list[str]] = []

    def fake_run(args, **kwargs):
        killed.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(mcode.subprocess, "run", fake_run)

    with pytest.raises(StudioError) as exc:
        mcode.exec("Do the check.", cwd=tmp_path, timeout="30m")

    assert "did not finish" in str(exc.value)
    assert "30m" in str(exc.value)
    assert seen.procs[0].killed is False  # the tree kill did the work, not a bare kill()
    assert killed and killed[0][0] == "taskkill"
    assert "/T" in killed[0] and "/F" in killed[0]
    assert str(seen.procs[0].pid) in killed[0]


def test_a_corpse_that_will_not_die_never_blocks_the_batch(tmp_path, monkeypatch):
    """A killed process whose thread is in a kernel wait never becomes a zombie we can
    wait for; the run is still reported as unanswered instead of freezing the pool.
    """
    _exe(tmp_path, monkeypatch)
    _calls(monkeypatch, hang=True, kill_hangs=True)
    monkeypatch.setattr(
        mcode.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, "", "")
    )

    with pytest.raises(StudioError, match="did not finish"):
        mcode.exec("Do the check.", cwd=tmp_path, timeout="30m")


def test_a_normal_run_waits_once_with_the_bound_behind_the_cli_timeout(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    seen = _calls(monkeypatch)

    mcode.exec("Do the check.", cwd=tmp_path, timeout="30m")

    assert seen.procs[0].waits == [mcode._seconds("30m") + mcode.GRACE_S]


def test_the_run_stamps_the_model_the_exec_json_names_not_the_one_asked_for(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    other = dict(OK, model={"providerId": "minimax", "modelId": "MiniMax-M3-1-Flash"})
    _calls(monkeypatch, stdout=json.dumps(other))

    run = mcode.exec("Do the check.", cwd=tmp_path)

    assert run.model == "MiniMax-M3-1-Flash"
    assert run.run_id == "exec_turn_a_1"
    assert run.session_id == "mvs_b_2"
    assert run.input_tokens == 21001
    assert not run.rate_limited


def test_a_missing_executable_names_the_installed_path(tmp_path, monkeypatch):
    monkeypatch.delenv(mcode.EXE_ENV, raising=False)
    monkeypatch.setattr(mcode, "_default_exe", lambda: tmp_path / "not-installed")

    with pytest.raises(StudioError) as exc:
        mcode.exec("Do the check.", cwd=tmp_path)

    assert "not-installed" in str(exc.value)
    assert "mcode --version" in str(exc.value)


def test_a_429_is_reported_as_rate_limited_with_its_message(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    _calls(
        monkeypatch,
        returncode=1,
        stdout="",
        stderr="HTTP 429 Too Many Requests: rate limit reached",
    )

    run = mcode.exec("Do the check.", cwd=tmp_path)

    assert run.rate_limited
    assert "429" in run.error
    assert run.model == ""


def test_a_run_without_an_exec_result_is_an_error_that_names_its_tail(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    _calls(monkeypatch, returncode=1, stdout="not json at all", stderr="boom")

    with pytest.raises(StudioError) as exc:
        mcode.exec("Do the check.", cwd=tmp_path)

    assert "boom" in str(exc.value)
    assert "not json at all" in str(exc.value)


def test_a_failed_status_is_an_error_with_the_agents_own_words(tmp_path, monkeypatch):
    _exe(tmp_path, monkeypatch)
    _calls(
        monkeypatch,
        returncode=1,
        stdout=json.dumps(dict(OK, status="failed", output="I could not read it.")),
    )

    with pytest.raises(StudioError) as exc:
        mcode.exec("Do the check.", cwd=tmp_path)

    assert "I could not read it." in str(exc.value)


def test_the_weekly_stop_is_at_ten_percent(monkeypatch):
    monkeypatch.setattr(mcode, "weekly_remaining_percent", lambda: 42.0)
    assert not mcode.weekly_stop()
    monkeypatch.setattr(mcode, "weekly_remaining_percent", lambda: 10.0)
    assert mcode.weekly_stop()
    monkeypatch.setattr(mcode, "weekly_remaining_percent", lambda: 9.9)
    assert mcode.weekly_stop()


def test_an_unreadable_quota_is_not_a_stop(monkeypatch):
    """The probe returns None when the plan endpoint does not answer; the run continues."""
    monkeypatch.setattr(mcode, "weekly_remaining_percent", lambda: None)
    assert not mcode.weekly_stop()


def test_the_weekly_percent_comes_from_the_token_plan_probe(monkeypatch):
    monkeypatch.setattr(
        mcode,
        "probe_minimax_quota",
        lambda force: {"ok": True, "weekly_remaining_percent": 63.5} if force else None,
    )
    assert mcode.weekly_remaining_percent() == 63.5


# --- the tracked-file guard -------------------------------------------------------------------


def test_a_throwaway_repository_ignores_the_gate_s_git_variables(tmp_path, monkeypatch):
    """The pre-push hook exports GIT_DIR, and it wins over `git -C <throwaway>`: on
    2026-10-03 this helper's commit landed on the branch that was being pushed, staged
    `a.txt` in the real index and left the gate with 24 failures. Without the fix the whole
    branch push was blocked."""
    for name, value in (("GIT_DIR", str(tmp_path / "elsewhere")), ("GIT_WORK_TREE", str(tmp_path))):
        monkeypatch.setenv(name, value)
    assert not [name for name in git_env.own_env() if name.startswith("GIT_")]


def _git(repo: Path, monkeypatch) -> None:
    """A throwaway repository with one tracked file, in an environment of its own.

    `env=git_env.own_env()` on every call: see the test above.
    """
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=git_env.own_env())
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, env=git_env.own_env())
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a"],
        check=True,
        env=git_env.own_env(),
    )


def test_a_clean_tracked_tree_passes_the_guard(tmp_path, monkeypatch):
    _git(tmp_path / "repo", monkeypatch)
    (tmp_path / "repo" / "untracked.txt").write_text("scratch\n", encoding="utf-8")
    repo = tmp_path / "repo"
    mcode.guard_tree(repo, mcode.tree_state(repo))


def test_a_tree_the_owner_is_already_editing_is_not_a_runs_doing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _git(repo, monkeypatch)
    (repo / "a.txt").write_text("work in progress\n", encoding="utf-8")
    before = mcode.tree_state(repo)
    (repo / "a.txt").write_text("work in progress, more of it\n", encoding="utf-8")

    mcode.guard_tree(repo, before)


def test_a_changed_tracked_file_stops_the_run_and_names_it(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _git(repo, monkeypatch)
    before = mcode.tree_state(repo)
    (repo / "a.txt").write_text("changed by an agent\n", encoding="utf-8")

    with pytest.raises(StudioError) as exc:
        mcode.guard_tree(repo, before)

    assert "a.txt" in str(exc.value)


def test_a_file_a_run_committed_is_a_change_too(tmp_path, monkeypatch):
    """The agent's commit makes the line disappear from `git status`; that is a change."""
    repo = tmp_path / "repo"
    _git(repo, monkeypatch)
    (repo / "a.txt").write_text("changed by an agent\n", encoding="utf-8")
    before = mcode.tree_state(repo)
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, env=git_env.own_env())
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        check=True,
        env=git_env.own_env(),
    )

    with pytest.raises(StudioError, match="a run changed tracked files"):
        mcode.guard_tree(repo, before)


# --- the adaptive pool (owner decision O22) ------------------------------------------------------


def test_the_pool_starts_at_two_runs_rises_while_clean_and_halves_on_a_429():
    pool = mcode.Pool(start=2, cap=4, pause=0.0, pause_max=0.0)
    sizes: list[int] = []
    outcomes = [mcode.Outcome(item=i, rate_limited=False) for i in range(1, 13)]

    def worker(item):
        sizes.append(pool.limit)
        return outcomes[item - 1]

    results = pool.map(list(range(1, 13)), worker)

    assert [r.item for r in results] == list(range(1, 13))
    assert sizes[0] == 2  # the first wave is two runs
    assert pool.limit > 2  # it rose while no 429 appeared
    assert max(sizes) <= 4  # never above the cap the test set


def test_one_429_halves_the_pool():
    pool = mcode.Pool(start=4, cap=8, pause=0.0, pause_max=0.0)
    seen: list[int] = []

    def worker(item):
        seen.append(pool.limit)
        return mcode.Outcome(item=item, rate_limited=(item == 2))

    pool.map(list(range(1, 9)), worker)

    assert seen[:4] == [4, 4, 4, 4]  # the first wave runs four
    assert seen[4:6] == [2, 2]  # the 429 in it halved the next wave
    assert seen[6:] == [3, 3]  # and it rose again while the waves came back clean


def test_a_429_halves_the_pool_and_waits_before_the_next_wave(monkeypatch):
    """A 429 must not be retried the next instant: the wait doubles while they keep coming."""
    slept: list[float] = []
    monkeypatch.setattr(mcode.time, "sleep", slept.append)
    pool = mcode.Pool(start=4, cap=8, pause=20.0, pause_max=60.0)
    waves: list[int] = []

    def worker(item):
        waves.append(pool.limit)
        return mcode.Outcome(item=item, rate_limited=True)

    pool.map(list(range(1, 13)), worker)

    assert waves[:4] == [4, 4, 4, 4]
    assert waves[4:6] == [2, 2]  # halved
    assert waves[6:] == [1, 1, 1, 1, 1, 1]  # halved again, and never below one
    assert slept == [20.0, 40.0] + [60.0] * 6  # 20, doubled, then capped at 60
    assert pool.waited_s == 420.0  # 8 rate-limited waves, 4 + 2 + 6 single runs


def test_a_clean_wave_never_waits(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(mcode.time, "sleep", slept.append)
    pool = mcode.Pool(start=2, cap=4)

    pool.map(list(range(1, 5)), lambda item: mcode.Outcome(item=item))

    assert slept == []  # sleep is faked above, so a real wait would show up here


def test_the_pool_never_goes_below_one_run():
    pool = mcode.Pool(start=1, cap=8, pause=0.0, pause_max=0.0)
    pool.map(list(range(1, 5)), lambda item: mcode.Outcome(item=item, rate_limited=True))
    assert pool.limit == 1


def test_a_quota_stop_ends_the_pool_and_names_the_rest():
    pool = mcode.Pool(start=2, cap=2, pause=0.0, pause_max=0.0)
    stopped = mcode.Outcome(item=1, stop="the weekly plan has 8 % left")
    results = pool.map(
        list(range(1, 7)), lambda item: stopped if item == 1 else mcode.Outcome(item=item)
    )

    assert [r.item for r in results] == [1, 2]  # the wave that was in flight, then nothing more
    assert pool.stop == "the weekly plan has 8 % left"


# --- the hard bound: one stuck run may not freeze the batch ------------------------------------


def test_a_wave_that_overruns_the_batch_bound_reports_those_items_and_keeps_going():
    """A run that never answers must cost its own task, not the whole batch: the 42-task
    calibration of 2026-10-03 lost three and a half hours to three stuck runs."""
    pool = mcode.Pool(start=2, cap=2, pause=0.0, pause_max=0.0, hard_bound_s=0.05)

    def worker(item):
        if item == 1:
            time.sleep(0.4)  # stands in for a hung provider socket
        return mcode.Outcome(item=item)

    results = pool.map([1, 2, 3, 4], worker)

    assert [r.item for r in results] == [1, 2, 3, 4]  # the batch carried on
    assert results[0].value is None and "hard bound" in results[0].reason
    assert [r.reason for r in results[1:]] == ["", "", ""]  # everything else was answered


def test_the_batch_bound_sits_above_the_bound_one_run_gets():
    assert mcode.Pool().hard_bound_s > mcode._seconds(mcode.TIMEOUT) + mcode.GRACE_S


def test_cmd_probe_reports_the_tracked_tree_without_guessing_a_function_name(tmp_path, monkeypatch):
    """`mcode probe` named `mcode.tracked_changes`, which does not exist: the command that
    every setup check runs died with an AttributeError."""
    from pipeline.studio import cli_mcode

    monkeypatch.setattr(mcode, "exe", lambda: tmp_path / "mcode.cmd")
    monkeypatch.setattr(
        mcode.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 0, "1.2.3\n", ""),
    )
    monkeypatch.setattr(mcode, "weekly_remaining_percent", lambda: 44.0)
    monkeypatch.setattr(mcode, "tree_state", lambda repo: [" M pipeline/studio/mcode.py"])

    printed: list[dict] = []
    monkeypatch.setattr(cli_mcode, "_print", printed.append)
    monkeypatch.setattr(cli_mcode.config, "REPO", tmp_path)
    monkeypatch.setattr(cli_mcode.config, "studio_assets", lambda: tmp_path / "assets")

    assert cli_mcode.cmd_probe(monkeypatch) == 0
    assert printed[0]["tracked_changes"] == [" M pipeline/studio/mcode.py"]
    assert printed[0]["weekly_remaining_percent"] == 44.0
