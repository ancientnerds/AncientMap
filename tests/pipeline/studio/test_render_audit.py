from __future__ import annotations

from pipeline.studio import render_audit

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
