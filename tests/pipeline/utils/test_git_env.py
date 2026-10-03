# SPDX-License-Identifier: AGPL-3.0-only
"""`pipeline.utils.git_env`: a `git -C <repo>` that means `<repo>`.

On 2026-10-03 the pre-push gate ran the suite with the hook's `GIT_DIR` exported, and eight
tests failed because production code that named a repository with `-C` was redirected into
the checkout being pushed. These tests hold the fix in place.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pipeline.utils import git_env
from tests import git_env as test_git_env

#: `-c user.*`, so a throwaway repository needs no global git identity.
IDENT = ("-c", "user.name=t", "-c", "user.email=t@example.com")


def _repo(tmp_path: Path, name: str, subject: str) -> Path:
    """A repository with one commit of its own, so its HEAD differs from every other one's."""
    repo = tmp_path / name
    repo.mkdir()
    git_env.run_git(repo, "init", "-q")
    (repo / f"{name}.txt").write_text(f"{subject}\n", encoding="utf-8")
    git_env.run_git(repo, "add", "-A")
    git_env.run_git(repo, *IDENT, "commit", "-qm", subject)
    assert git_env.run_git(repo, "rev-parse", "HEAD").returncode == 0
    return repo


def test_own_env_drops_every_git_variable_and_keeps_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_DIR", "/somewhere/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/somewhere")
    monkeypatch.setenv("GIT_INDEX_FILE", "/somewhere/index")
    monkeypatch.setenv("LYRA_TEST_KEEP", "1")

    env = git_env.own_env()

    assert [name for name in env if name.startswith("GIT_")] == []
    assert env["LYRA_TEST_KEEP"] == "1"
    assert env["PATH"] == os.environ["PATH"]


def test_the_tests_helper_is_this_helper() -> None:
    """One implementation: the tests' throwaway repositories and the production code strip the
    same variables, so a second copy could drift from the first."""
    assert test_git_env.own_env is git_env.own_env


def test_run_git_reports_the_repository_it_was_named_and_not_the_shells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wanted = _repo(tmp_path, "wanted", "the wanted commit")
    other = _repo(tmp_path, "other", "the other commit")
    wanted_head = git_env.run_git(wanted, "rev-parse", "HEAD").stdout.strip()
    other_head = git_env.run_git(other, "rev-parse", "HEAD").stdout.strip()
    assert wanted_head != other_head

    # What the pre-push hook exports: `GIT_DIR` wins over `-C`.
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    naive = subprocess.run(
        ["git", "-C", str(wanted), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert naive.stdout.strip() == other_head, (
        "the shell no longer redirects - drop this test's premise"
    )

    assert git_env.run_git(wanted, "rev-parse", "HEAD").stdout.strip() == wanted_head


def test_run_git_writes_through_to_the_repository_it_was_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half of 2026-10-03 that cost a commit: a write that landed in the pushed repository."""
    wanted = _repo(tmp_path, "wanted", "the wanted commit")
    other = _repo(tmp_path, "other", "the other commit")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))

    (wanted / "second.txt").write_text("only here\n", encoding="utf-8")
    git_env.run_git(wanted, *IDENT, "add", "-A")
    assert (
        git_env.run_git(wanted, *IDENT, "commit", "-qm", "only in the wanted repository").returncode
        == 0
    )

    assert git_env.run_git(wanted, "log", "--format=%s").stdout.splitlines() == [
        "only in the wanted repository",
        "the wanted commit",
    ]
    assert git_env.run_git(other, "log", "--format=%s").stdout.splitlines() == ["the other commit"]


def test_run_git_returns_a_completed_process_and_never_raises_on_a_failing_command(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, "repo", "a commit")

    done = git_env.run_git(repo, "rev-parse", "not-a-ref")

    assert done.returncode != 0
    assert "not-a-ref" in done.stderr + done.stdout


def test_run_git_decodes_the_output_as_utf_8(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "umlaut", "a commit")
    (repo / "b.txt").write_text("Grüße\n", encoding="utf-8")
    git_env.run_git(repo, "add", "-A")
    git_env.run_git(repo, *IDENT, "commit", "-qm", "Grüße aus dem Norden")

    log = git_env.run_git(repo, "log", "-1", "--format=%s")

    assert log.stdout.strip() == "Grüße aus dem Norden"
