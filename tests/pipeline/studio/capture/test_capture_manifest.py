"""The capture manifest contract (plan C C7; pipeline/studio/capture/manifest.py)."""

import subprocess

import pytest

from pipeline.studio.capture.manifest import (
    CaptureError,
    as_int,
    as_number,
    build_manifest,
    capture_id,
    event,
    require_kind,
    tool_failure,
)
from pipeline.studio.errors import StudioError

KEYS = {"id", "kind", "path", "fps", "duration_s", "width", "height", "events", "credits"}


@pytest.fixture
def episode(tmp_path):
    (tmp_path / "captures").mkdir()
    return tmp_path


def _media(episode, name="platform-01.mp4"):
    path = episode / "captures" / name
    path.write_bytes(b"x")
    return path


def _args(episode, **changes):
    args = {
        "episode_dir": episode,
        "cid": "platform-01",
        "kind": "platform",
        "path": _media(episode),
        "fps": 60,
        "duration_s": 10.0,
        "width": 1920,
        "height": 1080,
        "events": [],
        "credits": [],
    }
    args.update(changes)
    return args


def test_capture_errors_are_studio_errors():
    assert issubclass(CaptureError, StudioError)


def test_capture_id_is_a_safe_slug():
    assert capture_id({"id": "platform-01"}) == "platform-01"
    for bad in ("", "PF1", "../x", "a b", None, "x" * 49):
        with pytest.raises(CaptureError):
            capture_id({"id": bad})


def test_require_kind_checks_the_spec_kind():
    assert require_kind({"id": "g1", "kind": "globe"}, "globe") == "g1"
    with pytest.raises(CaptureError, match="takes kind 'globe', not 'globe-flyto'"):
        require_kind({"id": "g1", "kind": "globe-flyto"}, "globe")


def test_event_rounds_and_accepts_only_known_extras():
    assert event(1.23456, "place", x=100.04, y=20, target="p1", label="Baalbek") == {
        "t": 1.235,
        "name": "place",
        "x": 100.0,
        "y": 20.0,
        "target": "p1",
        "label": "Baalbek",
    }
    assert event(0, "pin", lat=33.999171234, lng=36.2)["lat"] == 33.999171
    assert event(0, "highlight", box=[1, 2, 3, 4])["box"] == [1.0, 2.0, 3.0, 4.0]
    with pytest.raises(CaptureError, match="unknown fields"):
        event(0, "x", colour="red")
    with pytest.raises(CaptureError, match=r"not \[x, y, w, h\]"):
        event(0, "x", box=[1, 2, 0, 4])


def test_a_place_event_keeps_its_pixel_in_every_frame():
    ev = event(3.5, "place", target="p1", x=960, y=540, track=[[960.04, 540], None, [961, 539.96]])
    assert ev["track"] == [[960.0, 540.0], None, [961.0, 540.0]]
    with pytest.raises(CaptureError, match=r"track point \[1\] is not \[x, y\]"):
        event(0, "place", track=[[1]])


def test_spec_values_must_be_numbers():
    assert (as_number(3, "zoom"), as_number(2.5, "zoom"), as_int(1280, "width")) == (3.0, 2.5, 1280)
    for bad in ("3", True, None, float("nan")):
        with pytest.raises(CaptureError, match="zoom must be a number"):
            as_number(bad, "zoom")
    with pytest.raises(CaptureError, match="width must be an integer"):
        as_int(1280.5, "width")


def test_a_failed_tool_names_itself_its_exit_code_and_its_stderr():
    exc = subprocess.CalledProcessError(
        1, ["C:/ffmpeg/bin/ffmpeg.exe", "-i", "x"], stderr="\nNo NVENC capable devices found\n"
    )
    assert str(tool_failure("g1", exc)) == (
        "g1: ffmpeg.exe failed (exit 1): No NVENC capable devices found"
    )


def test_a_clip_manifest_is_exactly_the_contract(episode):
    m = build_manifest(
        **_args(episode, duration_s=12.3456, events=[event(0.5, "search", x=10, y=20)])
    )
    assert set(m) == KEYS
    assert (m["path"], m["fps"], m["duration_s"]) == ("captures/platform-01.mp4", 60, 12.346)


def test_a_still_has_neither_fps_nor_duration(episode):
    m = build_manifest(
        **_args(
            episode,
            cid="td1",
            kind="mapbox_topdown",
            path=_media(episode, "td1.jpg"),
            fps=None,
            duration_s=None,
            width=2560,
            height=1441,
            events=[event(0, "pin", x=1, y=2)],
        )
    )
    assert (m["fps"], m["duration_s"], m["height"]) == (None, None, 1441)
    with pytest.raises(CaptureError, match="a clip has fps and duration_s, a still neither"):
        build_manifest(**_args(episode, fps=None, duration_s=2.0))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"kind": "globe-flyto"}, "unknown capture kind"),
        ({"width": 1921}, "must be even"),
        ({"fps": 0}, "must be positive"),
        ({"events": [event(5, "a"), event(1, "b")]}, "out of order"),
        ({"events": [event(99, "late")]}, "outside"),
        ({"credits": [" "]}, "empty credit"),
    ],
)
def test_build_manifest_rejects_defects(episode, changes, message):
    with pytest.raises(CaptureError, match=message):
        build_manifest(**_args(episode, **changes))


def test_media_must_exist_directly_in_captures(episode, tmp_path):
    elsewhere = tmp_path / "elsewhere.mp4"
    elsewhere.write_bytes(b"x")
    with pytest.raises(CaptureError, match="not directly inside"):
        build_manifest(**_args(episode, path=elsewhere))
    with pytest.raises(CaptureError, match="does not exist"):
        build_manifest(**_args(episode, path=episode / "captures" / "gone.mp4"))
