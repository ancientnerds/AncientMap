from __future__ import annotations

import json
from pathlib import Path

from pipeline.studio import render_audit
from pipeline.video.shorts_audit import longest_frozen_run

#: shorts_audit._frame_diffs of three real takes as render.ts encodes them (provenance inside)
REFERENCE = json.loads(
    Path(__file__).with_name("frozen_reference_diffs.json").read_text(encoding="utf-8")
)
TIMELINE = {"fps": 60, "width": 1920, "height": 1080, "durationInFrames": 3600}
GOOD = {
    "width": 1920,
    "height": 1080,
    "fps": 60,
    "frames": 3600,
    "longest_black_s": 0.25,
    "longest_frozen_frames": 120,
    "lufs": -14.3,
    "peak_dbfs": -1.6,
}


def test_longest_black_run_on_the_limited_range():
    # BT.709 limited range: black is Y 16, the NERV background Y 28 (not black)
    samples = [(0.0, 16.0), (0.25, 17.0), (0.5, 80.0), (0.75, 20.0)]
    assert render_audit.longest_black_s(samples) == 0.5
    assert render_audit.longest_black_s([(0.0, 28.0), (0.25, 28.0)]) == 0.0
    # a whole vector globe facing an ocean, against black space, is not black
    assert render_audit.longest_black_s([(0.0, 22.0), (0.25, 21.5), (0.5, 22.4)]) == 0.0
    assert render_audit.longest_black_s([(0.0, 16.2), (0.25, 17.3), (0.5, 16.0)]) == 0.75


def test_black_runs_are_counted_by_the_shorts_run_counter(monkeypatch):
    # one run counter (shorts_audit.longest_frozen_run), imported, not a copy of its loop
    seen = []

    def counter(values, threshold):
        seen.append((values, threshold))
        return 3

    monkeypatch.setattr(render_audit, "longest_frozen_run", counter)
    assert render_audit.longest_black_s([(0.0, 16.0), (0.25, 30.0)]) == 0.75
    assert seen == [([16.0, 30.0], render_audit.BLACK_YAVG_TV)]


def _scene(sid, start, frames, props):
    return {"id": sid, "from": start, "durationInFrames": frames, "props": props}


def test_static_card_scenes_are_not_frozen():
    clip = {"clip": {"id": "platform-01", "fps": 60, "src": "captures/platform-01.mp4"}}
    timeline = {
        **TIMELINE,
        "scenes": [
            _scene("b01", 0, 600, {"evidence": {"id": "e1"}}),
            _scene("b02", 600, 300, clip),
        ],
    }
    diffs = [0.0] * 600 + [1.0] * 299
    assert render_audit.clip_scenes(timeline) == [(600, 900)]
    assert render_audit.longest_frozen_in_clips(diffs, timeline) == 0
    diffs = [1.0] * 600 + [0.0] * 299
    assert render_audit.longest_frozen_in_clips(diffs, timeline) == 299
    assert render_audit.longest_frozen_in_clips([0.0] * 899, {**timeline, "scenes": []}) == 0


def _one_clip(frames):
    clip = {"clip": {"id": "g1", "fps": 60, "src": "captures/g1.mp4"}}
    return {**TIMELINE, "scenes": [_scene("b01", 0, frames, clip)]}


def test_frozen_threshold_on_real_studio_takes():
    # frame diffs of real takes (2026-09-29, render_audit's docstring): the slowest legitimate
    # turn of the globe dips below FROZEN_DIFF for one frame at most ...
    for take, most in (("turn_12n", 1), ("turn_37s", 0)):
        diffs = REFERENCE[take]["diffs"]
        assert render_audit.longest_frozen_in_clips(diffs, _one_clip(len(diffs) + 1)) == most
    # ... while a held pose stays below it for 4.67 s, which the check fails
    held = REFERENCE["held"]["diffs"]
    run = render_audit.longest_frozen_in_clips(held, _one_clip(len(held) + 1))
    assert run == 280
    frozen = {**GOOD, "frames": TIMELINE["durationInFrames"], "longest_frozen_frames": run}
    assert [c.ok for c in render_audit.evaluate(frozen, TIMELINE) if c.name == "frozen"] == [False]
    # a threshold under the encoders' keyframe spikes would cut that stall into short runs
    assert longest_frozen_run(held, 0.005) == 109
    assert longest_frozen_run(held, 0.005) <= render_audit.FROZEN_MAX_S * TIMELINE["fps"]


def test_good_measurements_pass():
    assert all(c.ok for c in render_audit.evaluate(GOOD, TIMELINE))


def test_each_check_fails_on_its_own_measurement():
    bad = {
        **GOOD,
        "frames": 3599,
        "longest_black_s": 1.0,
        "longest_frozen_frames": 241,
        "lufs": -16.2,
        "peak_dbfs": -0.4,
        "fps": 30,
    }
    failed = {c.name for c in render_audit.evaluate(bad, TIMELINE) if not c.ok}
    assert failed == {"format", "duration", "black_frames", "frozen", "loudness", "true_peak"}
