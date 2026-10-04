"""The post-render audit (spec 4.9): format, exact duration, black frames, frozen runs,
loudness and true peak, with the shorts audit's probes and thresholds where they are generic.

`evaluate` is pure (measurements + timeline -> checks); `measure` runs the ffmpeg/ffprobe
probes of pipeline/video/shorts_audit.py; `audit` writes render/audit.json.

Black frames: render.ts writes BT.709 limited range, where black decodes to Y 16; the threshold
BLACK_YAVG_TV sits 2 above it, below the darkest legitimate frames (a whole vector globe against
black space, about Y 22-27 in video mode; the NERV background #0a0e14, Y 28).

Frozen runs are measured inside clip scenes only (a scene whose props carry a captured clip with
an fps): stills, cards and infographics hold still by design once their entrance ends, but a
clip scene that holds one picture for more than FROZEN_MAX_S (frozen_max_frames) is dead air, a
stalled take or a still the script planned (cut to a card instead). `episode check` refuses the
planned ones with this same limit before the render (script.py, owner Q16: a fly-to's hold after
its arrival, a fixed pose, a Mapbox orbit that does not turn); this check catches the rest,
after it. A GlobeShot pin lighting up does not end a planned hold there: estimated off-render on
2026-09-30 (its dot, glow and ring drawn at 1080p and scaled as _frame_diffs scales, not
measured through render.ts), a pin reads 0.03 over a grey Y 80 and 0.07 over the NERV
background, and its label's boot-in 0.03 or less per frame, so this check sees a pin on a dark
globe and misses it on a lighter one. A frame counts as unchanged when its mean
luma difference to the next (shorts_audit._frame_diffs) is below the shorts' FROZEN_DIFF, 0.05,
measured on studio takes on 2026-09-29 (recorded on the NVIDIA by capture.globe.record_globe,
encoded as render.ts encodes: h264_nvenc, 16M, no B-frames;
tests/pipeline/studio/frozen_reference_diffs.json). A distribution's turn of 360 degrees in 30 s
with the whole globe in frame (the slowest turn a distribution makes) reads 0.049-0.29 per frame
(camera at 12 N; 0.052-0.19 at 37 S, a view of mostly ocean), so it stays below 0.05 for one
frame at most; a places sweep of 3 degrees/s at distance 1.8 reads 0.33 or more. Slower motion
was not measured, and the capture validators accept it (a places sweep of any non-zero
sweep_lng_deg, a Mapbox orbit of any bearing range): it can read as frozen. A held picture reads
0 between keyframes, but keyframes of the two encodes (hevc_nvenc every 60 frames for the
capture, h264_nvenc every 250 for the render) add single-frame spikes of 0.005-0.066. A
threshold low enough to sit under those spikes would cut a stall into short runs: the
reference's held pose (a fixed-pose places take of 6 s, standing in for a stall) reads 280
frames at 0.05 but 109 at 0.005, which the check would pass. A spike above 0.05 still ends a
run, so an unplanned stall of about 4-8 s that crosses a render keyframe can read as two runs
within the limit.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pipeline.studio.errors import StudioError
from pipeline.video.shorts_audit import (
    FROZEN_DIFF,
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


def frozen_max_frames(fps: int) -> int:
    """The longest run of unchanged frames a clip scene may hold: FROZEN_MAX_S at `fps` (the
    audit's limit, and `episode check`'s for a still the script plans)."""
    return int(FROZEN_MAX_S * fps)


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
    runs = [
        longest_frozen_run(diffs[start : end - 1], FROZEN_DIFF)
        for start, end in clip_scenes(timeline)
    ]
    return max(runs, default=0)


def evaluate(m: dict[str, Any], timeline: dict[str, Any]) -> list[Check]:
    fps = timeline["fps"]
    frozen_max = frozen_max_frames(fps)
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
    samples = _luma_samples(video, LUMA_STEP_S)
    diffs = _frame_diffs(video)
    if not samples or not diffs:
        # The shorts' probes return [] when ffmpeg fails: nothing measured would read as a
        # video without black frames or frozen runs.
        raise StudioError(
            f"ffmpeg decoded no frames of {video.name} for the black and frozen checks"
        )
    return {
        **stream,
        "longest_black_s": longest_black_s(samples),
        "longest_frozen_frames": longest_frozen_in_clips(diffs, timeline),
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
