"""The post-render audit (spec 4.9): format, exact duration, black frames, frozen runs,
loudness and true peak, with the shorts audit's probes and thresholds where they are generic.

`evaluate` is pure (measurements + timeline -> checks); `measure` runs the ffmpeg/ffprobe
probes of pipeline/video/shorts_audit.py; `audit` writes render/audit.json.

Black frames: render.ts writes BT.709 limited range, where black decodes to Y 16; the threshold
BLACK_YAVG_TV sits 2 above it, below the darkest legitimate frames (a whole vector globe against
black space, about Y 22-27 in video mode; the NERV background #0a0e14, Y 28). Frozen runs are measured inside clip scenes only (a scene whose
props carry a captured clip with an fps): stills, cards and infographics hold still by design
once their entrance ends, but a clip that holds one picture for more than FROZEN_MAX_S is a
stalled take (cut to a card instead).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pipeline.video.shorts_audit import (
    LOUDNESS_TOL,
    PEAK_MAX_DBFS,
    Check,
    _ffprobe_stream,
    _frame_diffs,
    _loudness,
    _luma_samples,
    longest_frozen_run,
)
from pipeline.video.shorts_render import TARGET_LUFS

LUMA_STEP_S = 0.25
BLACK_MAX_S = 0.5
FROZEN_MAX_S = 4.0
#: Limited-range black (Y 16) plus 2; the darkest legitimate frames stay above it: a whole
#: vector globe against black space (about Y 22-27 in video mode) and the NERV background
#: (Y 28).
BLACK_YAVG_TV = 18.0


def longest_black_s(samples: list[tuple[float, float]], step_s: float = LUMA_STEP_S) -> float:
    """The longest run of luma samples below BLACK_YAVG_TV, in seconds."""
    return longest_frozen_run([yavg for _t, yavg in samples], BLACK_YAVG_TV) * step_s


def clip_scenes(timeline: dict[str, Any]) -> list[tuple[int, int]]:
    """[from, end) of every scene that plays a captured clip (props.clip with an fps)."""
    out = []
    for scene in timeline["scenes"]:
        clip = scene["props"].get("clip")
        if isinstance(clip, dict) and clip.get("fps") is not None:
            out.append((scene["from"], scene["from"] + scene["durationInFrames"]))
    return out


def longest_frozen_in_clips(diffs: list[float], timeline: dict[str, Any]) -> int:
    """The longest run of unchanged frames inside any clip scene (diffs[i]: frame i -> i+1)."""
    runs = [longest_frozen_run(diffs[start : end - 1]) for start, end in clip_scenes(timeline)]
    return max(runs, default=0)


def evaluate(m: dict[str, Any], timeline: dict[str, Any]) -> list[Check]:
    fps = timeline["fps"]
    frozen_max = int(FROZEN_MAX_S * fps)
    return [
        Check(
            "format",
            (m["width"], m["height"], m["fps"]) == (timeline["width"], timeline["height"], fps),
            f"{m['width']}x{m['height']}@{m['fps']}",
        ),
        Check(
            "duration",
            m["frames"] == timeline["durationInFrames"],
            f"{m['frames']} frames, timeline {timeline['durationInFrames']}",
        ),
        Check("black_frames", m["longest_black_s"] <= BLACK_MAX_S, f"{m['longest_black_s']:.2f} s"),
        Check(
            "frozen",
            m["longest_frozen_frames"] <= frozen_max,
            f"{m['longest_frozen_frames']} frames (max {frozen_max})",
        ),
        Check(
            "loudness",
            abs(m["lufs"] - TARGET_LUFS) <= LOUDNESS_TOL,
            f"{m['lufs']:.1f} LUFS (target {TARGET_LUFS:.0f})",
        ),
        Check("true_peak", m["peak_dbfs"] <= PEAK_MAX_DBFS, f"{m['peak_dbfs']:.1f} dBFS"),
    ]


def measure(video: Path, timeline: dict[str, Any]) -> dict[str, Any]:
    stream = _ffprobe_stream(video)
    lufs, peak = _loudness(video)
    return {
        **stream,
        "longest_black_s": longest_black_s(_luma_samples(video, LUMA_STEP_S)),
        "longest_frozen_frames": longest_frozen_in_clips(_frame_diffs(video), timeline),
        "lufs": lufs,
        "peak_dbfs": peak,
    }


def audit(video: Path, timeline: dict[str, Any], out: Path) -> tuple[bool, list[Check]]:
    measurements = measure(video, timeline)
    checks = evaluate(measurements, timeline)
    ok = all(c.ok for c in checks)
    out.write_text(
        json.dumps(
            {"ok": ok, "checks": [asdict(c) for c in checks], "measurements": measurements},
            indent=2,
        ),
        encoding="utf-8",
    )
    return ok, checks
