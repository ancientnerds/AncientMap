from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.studio import config
from pipeline.studio.errors import StudioError

REQ = "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b"


def test_main_checkout_is_the_parent_of_the_common_git_dir():
    assert config.main_checkout_from("C:/PythonProjects/AncientMap/.git\n") == Path(
        "C:/PythonProjects/AncientMap"
    )


def test_a_common_dir_that_is_not_dot_git_is_refused():
    with pytest.raises(StudioError, match="is not a '.git' directory"):
        config.main_checkout_from("C:/somewhere/else")


def test_studio_assets_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    assert config.studio_assets() == tmp_path
    assert config.paper_dir(REQ) == tmp_path / "papers" / REQ
    assert config.episode_dir("baalbek-c5") == tmp_path / "episodes" / "baalbek-c5"


def test_a_relative_studio_assets_is_made_absolute(monkeypatch, tmp_path):
    """ffmpeg's concat lists and the node renderer (cwd video/) read workspace paths from
    elsewhere: a relative override would resolve against the wrong directory there."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STUDIO_ASSETS", "assets")
    assert config.studio_assets() == tmp_path / "assets"
    assert config.studio_assets().is_absolute()


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("git"),
        subprocess.TimeoutExpired(cmd="git", timeout=30),
        subprocess.CompletedProcess(["git"], 128, "", "fatal: not a git repository"),
    ],
)
def test_a_failing_git_is_a_studio_error(monkeypatch, failure):
    def fake_run(*_a, **_k):
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(config.subprocess, "run", fake_run)
    with pytest.raises(StudioError, match="cannot locate the main checkout"):
        config.main_checkout()


def test_default_studio_assets_live_in_the_main_checkout(monkeypatch):
    monkeypatch.delenv("STUDIO_ASSETS", raising=False)
    monkeypatch.setattr(config, "main_checkout", lambda: Path("C:/main"))
    assert config.studio_assets() == Path("C:/main/video-assets/studio")
    assert config.video_assets() == Path("C:/main/video-assets")


@pytest.mark.parametrize("bad", ["95FA3798-1C2D-4E5F-8A9B-0C1D2E3F4A5B", "../etc", "95fa3798"])
def test_request_ids_are_strict_uuids(bad):
    with pytest.raises(StudioError, match="is not a research request id"):
        config.check_request_id(bad)


@pytest.mark.parametrize("bad", ["Baalbek", "a--b", "-a", "a/b", ""])
def test_slugs_are_strict(bad):
    with pytest.raises(StudioError, match="is not a slug"):
        config.check_slug(bad)
