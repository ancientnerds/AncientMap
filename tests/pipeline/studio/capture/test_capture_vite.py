"""Token, tools, the awake display and the local site of the captures (capture/vite.py)."""

import os

import pytest

from pipeline.studio.capture import vite
from pipeline.studio.capture.manifest import CaptureError


def test_the_mapbox_token_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", " pk.test ")
    assert vite.require_mapbox_token() == "pk.test"
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "")
    with pytest.raises(CaptureError, match="loads the main checkout's .env"):
        vite.require_mapbox_token()


def test_a_missing_tool_is_named(monkeypatch):
    monkeypatch.setattr(vite.shutil, "which", lambda name: None)
    with pytest.raises(CaptureError, match="npm not found on PATH"):
        vite.require_tool("npm")


def test_the_frontend_lives_next_to_the_pipeline():
    assert (vite.FRONTEND_DIR / "package.json").is_file()
    assert (vite.FRONTEND_DIR / "video" / "record.ts").is_file()


def test_the_analytics_tracker_is_recognised_on_every_host():
    for url in ("https://ancientnerds.com/pulse.js", "http://localhost:5198/pulse.js?x=1"):
        assert vite.ANALYTICS_URL_RE.match(url), url
    for url in (
        "https://ancientnerds.com/data/sources.json",
        "https://ancientnerds.com/research/x",
    ):
        assert not vite.ANALYTICS_URL_RE.match(url), url


@pytest.mark.skipif(os.name != "nt", reason="SetThreadExecutionState exists only on Windows")
def test_display_awake_holds_the_display_for_the_take():
    with vite.display_awake():
        pass


@pytest.mark.skipif(os.name == "nt", reason="the refusal is for systems other than Windows")
def test_display_awake_refuses_other_systems():
    with pytest.raises(CaptureError, match="captures run on the Windows workstation"):
        with vite.display_awake():
            pass
