"""Automated quality audit of one rendered site short.

Checks the things a viewer would notice and a batch would silently get wrong:
container/format, clip completeness, black frames, the loop seam, the audio
timeline (voice from 0, spoken name in its window, silence at the loop point),
loudness, and the selection. Writes `audit.json` next to the short; the
`evaluate` helpers are pure and unit tested, `audit_site` does the probing.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFont, ImageStat

from pipeline.video.media import FFMPEG_BIN, FFPROBE_BIN, probe_duration
from pipeline.video.shorts_brand import font_cmap, heading_font, missing_glyphs
from pipeline.video.shorts_captions import display_text
from pipeline.video.shorts_export import country_code_for, flag_path
from pipeline.video.shorts_render import (
    CAPTION_BORDER,
    CAPTION_SIZE,
    FPS,
    MIN_STILL_S,
    NAME_AUDIO_DELAY_S,
    NAME_END_GAP_S,
    NARRATION_TAIL_S,
    TARGET_LUFS,
    H,
    Segment,
    W,
    name_audio_at,
    name_layout,
)

logger = logging.getLogger(__name__)

OPENING_TAKE_S = 6.1  # matches ancient-nerds-map/video/scenes/site-short.ts
MIN_CLIP_FRAME_RATIO = 0.94  # MediaRecorder drops a few frames even with the yield
BLACK_YAVG = 12.0  # 8-bit luma average below which a frame counts as black
LOOP_SEAM_MAX = 3.0  # mean abs luma difference first vs last frame
LOUDNESS_TOL = 1.0
PEAK_MAX_DBFS = -1.0
VOICE_MIN_DB = -20.0  # a voice window must peak above this
SILENCE_MAX_DB = -45.0  # the loop point must be below this
FROZEN_DIFF = 0.05  # mean abs luma difference below which two frames count as identical
MAX_FROZEN_FRAMES = 10  # the return flight holds its end pose ~6 frames; more is a stall
MIN_STILLS = 2
MAX_NAME_LINES = 3
CAPTION_MARGIN = 40  # a caption word must stay this far from both frame edges


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    value: str


# ---------------------------------------------------------------------------
# Pure evaluation
# ---------------------------------------------------------------------------


def evaluate(m: dict) -> list[Check]:
    """Turn raw measurements into pass/fail checks. `m` keys are documented by
    `measure_site`; missing clips or audio simply fail their checks."""
    checks: list[Check] = []
    checks.append(
        Check(
            "video_format",
            m["width"] == W and m["height"] == H and m["fps"] == FPS,
            f"{m['width']}x{m['height']}@{m['fps']}",
        )
    )
    expected = m["narration_s"] + NARRATION_TAIL_S + m["return_s"]
    checks.append(
        Check(
            "duration",
            abs(m["duration"] - expected) <= 0.35,
            f"{m['duration']:.2f}s (expected ≈{expected:.2f}s)",
        )
    )
    checks.append(
        Check(
            "opening_clip",
            m["opening_frames"] >= OPENING_TAKE_S * FPS * MIN_CLIP_FRAME_RATIO,
            f"{m['opening_frames']} frames",
        )
    )
    checks.append(
        Check(
            "return_clip",
            m["return_s"] > 0 and m["return_frames"] >= m["return_s"] * FPS * MIN_CLIP_FRAME_RATIO,
            f"{m['return_frames']} frames for {m['return_s']:.1f} s",
        )
    )
    dark = [t for t, y in m["luma_samples"] if y < BLACK_YAVG]
    checks.append(
        Check(
            "no_black_frames",
            not dark,
            f"{len(dark)} dark samples" + (f" at {dark[:4]}" if dark else ""),
        )
    )
    checks.append(
        Check("loop_seam", m["loop_seam"] <= LOOP_SEAM_MAX, f"{m['loop_seam']:.2f} mean luma diff")
    )
    checks.append(
        Check(
            "no_frozen_frames",
            m["frozen_run"] <= MAX_FROZEN_FRAMES,
            f"longest run of identical frames: {m['frozen_run']} ({m['frozen_run'] / FPS:.2f}s)",
        )
    )
    checks.append(
        Check("loudness", abs(m["lufs"] - TARGET_LUFS) <= LOUDNESS_TOL, f"{m['lufs']:.1f} LUFS")
    )
    checks.append(Check("true_peak", m["peak_dbfs"] <= PEAK_MAX_DBFS, f"{m['peak_dbfs']:.1f} dBFS"))
    checks.append(
        Check(
            "voice_from_start",
            m["voice_start_db"] > VOICE_MIN_DB,
            f"{m['voice_start_db']:.1f} dB in 0–2 s",
        )
    )
    checks.append(
        Check(
            "name_spoken",
            m["name_window_db"] > VOICE_MIN_DB,
            f"{m['name_window_db']:.1f} dB at {m['name_at']:.1f}s",
        )
    )
    checks.append(
        Check(
            "silent_loop_point",
            m["tail_db"] < SILENCE_MAX_DB,
            f"{m['tail_db']:.1f} dB in last 0.3 s",
        )
    )
    checks.append(
        Check(
            "stills_selected",
            m["stills_kept"] >= MIN_STILLS,
            f"{m['stills_kept']} kept, {m['stills_rejected']} rejected, {m['stills_used']} used",
        )
    )
    checks.append(
        Check("name_fits", m["name_lines"] <= MAX_NAME_LINES, f"{m['name_lines']} line(s)")
    )
    checks.append(
        Check(
            "captions_fit",
            m["max_caption_w"] <= W - 2 * CAPTION_MARGIN,
            f"widest word {m['max_caption_w']} px ({m['widest_caption']!r})",
        )
    )
    checks.append(Check("flag_present", m["flag_exists"], m["flag"] or "no country code"))
    checks.append(
        Check(
            "glyphs_covered",
            not m["missing_glyphs"],
            f"all characters in {m['heading_font']}"
            if not m["missing_glyphs"]
            else "missing " + " ".join(f"U+{ord(c):04X}" for c in m["missing_glyphs"]),
        )
    )
    checks.append(
        Check(
            "return_covers_name",
            m["return_s"] >= m["return_needed_s"],
            f"return {m['return_s']:.2f} s, spoken name needs {m['return_needed_s']:.2f} s",
        )
    )
    checks.append(
        Check(
            "stills_pace",
            m["min_still_s"] >= MIN_STILL_S - 0.01,
            f"shortest still {m['min_still_s']:.2f} s",
        )
    )
    checks.append(
        Check(
            "captions_timed",
            m["caption_words"] == m["card_words"] and m["captions_end"] <= m["name_at"],
            f"{m['caption_words']}/{m['card_words']} words, last ends {m['captions_end']:.2f}s",
        )
    )
    return checks


def passed(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def _ffprobe_stream(path: Path) -> dict:
    out = subprocess.run(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {
        "width": int(s["width"]),
        "height": int(s["height"]),
        "fps": round(int(num) / int(den)),
        "frames": int(s["nb_read_frames"]),
    }


def _widest_caption(captions: list[dict], font_path: Path) -> tuple[str, int]:
    """The caption word that renders widest (as shown: edge punctuation off,
    outline included) and its width in pixels."""
    font = ImageFont.truetype(str(font_path), CAPTION_SIZE)
    widest, max_w = "", 0
    for word in captions:
        shown = display_text(word["text"])
        w = int(font.getlength(shown)) + 2 * CAPTION_BORDER if shown else 0
        if w > max_w:
            widest, max_w = shown, w
    return widest, max_w


def _frames(path: Path) -> int:
    return _ffprobe_stream(path)["frames"] if path.exists() else 0


def _seconds(path: Path) -> float:
    return probe_duration(path) if path.exists() else 0.0


def _luma_samples(video: Path, step_s: float = 0.25) -> list[tuple[float, float]]:
    out = subprocess.run(
        [
            FFMPEG_BIN,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            f"select='not(mod(n,{int(round(step_s * FPS))}))',signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stdout
    times = re.findall(r"pts_time:([\d.]+)", out)
    yavgs = re.findall(r"YAVG=([\d.]+)", out)
    return [(round(float(t), 2), float(y)) for t, y in zip(times, yavgs, strict=False)]


def longest_frozen_run(diffs: list[float], threshold: float = FROZEN_DIFF) -> int:
    """Longest run of consecutive frames that do not differ from their
    predecessor. A stalled recorder (throttled Chrome, a hung tile wait) writes
    the same picture over and over; brightness, loudness and the loop seam all
    stay fine, so nothing else notices."""
    longest = run = 0
    for diff in diffs:
        run = run + 1 if diff < threshold else 0
        longest = max(longest, run)
    return longest


def _frame_diffs(video: Path) -> list[float]:
    """Mean absolute luma difference between consecutive frames, on a small
    grayscale copy (the whole short is a few MB at this size)."""
    import numpy as np

    width, height = 54, 96
    raw = subprocess.run(
        [
            FFMPEG_BIN,
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"scale={width}:{height},format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, height, width).astype(np.int16)
    return [float(np.abs(frames[i + 1] - frames[i]).mean()) for i in range(len(frames) - 1)]


def _frame(video: Path, at: str, out: Path) -> Path:
    """Extract one frame at `at` seconds; a negative `at` means "the true last
    frame" (decode the tail and keep the final image), because seeking with
    -sseof to within a frame or two of the end yields nothing at 60 fps."""
    if at.startswith("-"):
        args = ["-sseof", "-0.25", "-i", str(video), "-vf", "scale=540:-1", "-update", "1"]
    else:
        args = ["-ss", at, "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-1"]
    subprocess.run([FFMPEG_BIN, "-v", "error", "-y", *args, str(out)], check=True)
    return out


def _loop_seam(video: Path, work: Path) -> float:
    first = Image.open(_frame(video, "0", work / "audit_first.png")).convert("L")
    last = Image.open(_frame(video, "-", work / "audit_last.png")).convert("L")
    return ImageStat.Stat(ImageChops.difference(first, last)).mean[0]


def _loudness(video: Path) -> tuple[float, float]:
    err = subprocess.run(
        [
            FFMPEG_BIN,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", err)
    return float(lufs[-1]), float(peak[-1])


def _max_volume(video: Path, start: float, length: float) -> float:
    err = subprocess.run(
        [
            FFMPEG_BIN,
            "-hide_banner",
            "-nostats",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(video),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", err)
    return float(m.group(1)) if m else -91.0


def measure_site(site_dir: Path) -> dict:
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    selection = json.loads((site_dir / "selection.json").read_text(encoding="utf-8"))
    timeline = json.loads((site_dir / "render" / "timeline.json").read_text(encoding="utf-8"))
    video = site_dir / f"{site['slug']}.mp4"
    stream = _ffprobe_stream(video)
    duration = probe_duration(video)
    narration_s = probe_duration(site_dir / "narration.mp3")
    segments = [
        Segment(s["kind"], s["duration"], s.get("source"), s.get("start", 0.0)) for s in timeline
    ]
    name_s = probe_duration(site_dir / "name.mp3")
    name_at = name_audio_at(segments, name_s)
    captions = json.loads((site_dir / "render" / "captions.json").read_text(encoding="utf-8"))
    widest, max_w = _widest_caption(captions, heading_font(site["name"] + " " + site["card_text"]))
    code = country_code_for(site.get("country"))
    lufs, peak = _loudness(video)
    return {
        "site": site["name"],
        "slug": site["slug"],
        "video": str(video),
        "width": stream["width"],
        "height": stream["height"],
        "fps": stream["fps"],
        "duration": duration,
        "narration_s": narration_s,
        "opening_frames": _frames(site_dir / "clips" / "short-opening.mp4"),
        "return_frames": _frames(site_dir / "clips" / "short-return.mp4"),
        "return_s": _seconds(site_dir / "clips" / "short-return.mp4"),
        "luma_samples": _luma_samples(video),
        "frozen_run": longest_frozen_run(_frame_diffs(video)),
        "loop_seam": _loop_seam(video, site_dir / "render"),
        "lufs": lufs,
        "peak_dbfs": peak,
        "voice_start_db": _max_volume(video, 0.0, 2.0),
        "name_at": name_at,
        "name_window_db": _max_volume(video, name_at, 1.4),
        "tail_db": _max_volume(video, max(duration - 0.3, 0.0), 0.3),
        "stills_kept": len(selection["stills"]),
        "stills_rejected": len(selection["rejected"]),
        "stills_used": sum(1 for s in timeline if s["kind"] == "still"),
        "name_lines": len(name_layout(site["name"])[0]),
        "widest_caption": widest,
        "max_caption_w": max_w,
        "flag": code,
        "flag_exists": bool(code) and flag_path(code).exists(),
        "heading_font": heading_font(site["name"] + " " + site["card_text"]).name,
        "missing_glyphs": missing_glyphs(
            site["name"] + " " + site["card_text"],
            font_cmap(heading_font(site["name"] + " " + site["card_text"])),
        ),
        "return_needed_s": name_s + NAME_AUDIO_DELAY_S + NAME_END_GAP_S,
        "min_still_s": min((s["duration"] for s in timeline if s["kind"] == "still"), default=0.0),
        "card_words": len(site["card_text"].split()),
        "caption_words": len(captions),
        "captions_end": max((w["end"] for w in captions), default=0.0),
    }


def audit_site(site_dir: Path) -> tuple[bool, list[Check], dict]:
    m = measure_site(site_dir)
    checks = evaluate(m)
    ok = passed(checks)
    (site_dir / "audit.json").write_text(
        json.dumps(
            {
                "ok": ok,
                "checks": [asdict(c) for c in checks],
                "measurements": {k: v for k, v in m.items() if k != "luma_samples"},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for c in checks:
        logger.info("%s %-18s %s", "PASS" if c.ok else "FAIL", c.name, c.value)
    logger.info("audit %s: %s", m["site"], "PASS" if ok else "FAIL")
    return ok, checks, m
