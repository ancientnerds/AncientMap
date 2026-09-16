"""ffmpeg assembly of one site short (1080×1920, 60 fps).

Loop cut (spec 2026-09-16, revised the same evening):
  narration from t=0 over: opening clip (satellite globe → zoom → 3D orbit, 6 s)
  → full-frame stills, each panning gently → return clip (orbit → back to
  space) with the site name spoken and shown. The return clip's last frame is
  the opening's first frame, so the short loops without a visible cut.

Pure planning helpers (`plan_timeline`, `wrap_lines`, filter builders) are unit
tested; the ffmpeg calls are thin wrappers verified by ffprobe on the output.
"""

from __future__ import annotations

import json
import logging
import math
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pipeline.video.media import ff_path, probe_duration, run_ffmpeg

logger = logging.getLogger(__name__)

W, H, FPS = 1080, 1920, 60

NARRATION_TAIL_S = 0.6
OPENING_SLACK_S = 0.5  # deficit the narration tail can absorb before we cut to stills
PAN_MAX_S = 3.5  # faster cuts — 5 s per still reads as a slideshow
PAN_START = 0.3  # crop window starts 20 % off-centre …
PAN_TRAVEL = 0.4  # … and travels 40 % of the overflow, eased in and out
NAME_FADE_IN_S = 0.3
NAME_FADE_OUT_S = 0.5
NAME_END_GAP_S = 0.15  # fully gone this long before the clip ends = the loop point
NAME_AUDIO_DELAY_S = 0.2  # spoken name starts shortly after the return clip begins
NAME_WRAP_CHARS = 14
OPENING_TRIM_S = 0.1  # the opening take holds its first pose this long; the first frames after a
# jump are not fully drawn, so cutting the hold keeps frame 0 identical to the loop's end pose
# Mapbox ToS: satellite/terrain frames need attribution in the video itself;
# the DOM logo is not part of the captured canvas.
MAPBOX_CREDIT = "© Mapbox © Maxar"

FONT_DIR = Path(__file__).resolve().parents[2] / "video-assets" / "fonts"
FONT_HEADING = FONT_DIR / "orbitron-400-latin.ttf"
FONT_BODY = FONT_DIR / "jetbrains-mono-400-latin.ttf"

X264 = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "18",
    "-pix_fmt",
    "yuv420p",
    "-r",
    str(FPS),
    "-an",
]

SegmentKind = Literal["clip", "pan", "return"]


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    duration: float
    source: str | None = None
    forward: bool = True  # pan direction: left→right / top→bottom
    vertical: bool = False  # portrait stills pan vertically instead
    start: float = 0.0  # seek offset into a clip source


# ---------------------------------------------------------------------------
# Pure planning
# ---------------------------------------------------------------------------


def is_portrait(width: int, height: int) -> bool:
    """Narrower than 9:16 → the cover-scaled still is taller than the frame, so pan vertically."""
    return width * H < height * W


def plan_timeline(
    *,
    narration_s: float,
    images: list[tuple[Path, int, int]],
    opening: tuple[Path, float] | None,
    closing: tuple[Path, float] | None,
    opening_start: float = 0.0,
) -> list[Segment]:
    """Lay out the segments; each image is (path, width, height).

    The narration starts at t=0 and its visuals cover `narration_s +
    NARRATION_TAIL_S`: the opening clip first (as long as it lasts, after
    `opening_start` trim), full-frame panning stills for whatever remains. An
    opening deficit of up to OPENING_SLACK_S is absorbed by the tail rather
    than producing a sub-second still. The return clip follows, unshortened,
    because its last frame has to be the loop point.
    """
    if not images:
        raise ValueError("at least one image is required")
    segments: list[Segment] = []
    span = narration_s + NARRATION_TAIL_S
    remainder = span
    if opening is not None:
        used = min(opening[1], span)
        remainder = span - used
        if remainder <= OPENING_SLACK_S:
            remainder = 0.0
        segments.append(Segment("clip", used, str(opening[0]), start=opening_start))

    if remainder > 0:
        count = max(1, min(len(images), math.ceil(remainder / PAN_MAX_S)))
        each = remainder / count
        for i in range(count):
            path, width, height = images[i]
            segments.append(
                Segment(
                    "pan",
                    each,
                    str(path),
                    forward=(i % 2 == 0),
                    vertical=is_portrait(width, height),
                )
            )

    if closing is not None:
        segments.append(Segment("return", closing[1], str(closing[0])))
    return segments


def name_audio_at(segments: list[Segment]) -> float:
    """When the spoken name starts: shortly into the return clip, or at the end
    of the stills when no return clip was recorded."""
    before = sum(s.duration for s in segments if s.kind != "return")
    has_return = any(s.kind == "return" for s in segments)
    return before + NAME_AUDIO_DELAY_S if has_return else before


def wrap_lines(name: str, width: int = NAME_WRAP_CHARS) -> list[str]:
    """Wrap a site name for the heading font (no auto-wrap in drawtext)."""
    return textwrap.wrap(name, width=width, break_long_words=True) or [name]


def eased_progress(duration: float) -> str:
    """0→1 over `duration` seconds with smoothstep easing, as an ffmpeg expression in `t`."""
    p = f"(t/{duration:.3f})"
    return f"{p}*{p}*(3-2*{p})"


def pan_filter(duration: float, forward: bool, vertical: bool) -> str:
    """Cover-scale the still to fill 1080×1920 and move the crop window across
    the overflow axis from 30 % to 70 % (or back): horizontally for landscape
    stills, vertically for portrait ones."""
    e = eased_progress(duration)
    if forward:
        pos = f"({PAN_START}+{PAN_TRAVEL}*{e})"
    else:
        pos = f"({PAN_START + PAN_TRAVEL}-{PAN_TRAVEL}*{e})"
    window = f"x=0:y='(ih-oh)*{pos}'" if vertical else f"x='(iw-ow)*{pos}':y=0"
    return (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H}:{window},fps={FPS},format=yuv420p"
    )


def name_alpha(duration: float) -> str:
    """Fade the name in at the start and out so it is fully gone NAME_END_GAP_S
    before the clip (= loop point) ends; the last frames must match frame 0."""
    end = duration - NAME_END_GAP_S
    out_from = end - NAME_FADE_OUT_S
    return (
        f"if(lt(t\\,{NAME_FADE_IN_S})\\,t/{NAME_FADE_IN_S}\\,"
        f"if(gt(t\\,{end:.3f})\\,0\\,"
        f"if(gt(t\\,{out_from:.3f})\\,({end:.3f}-t)/{NAME_FADE_OUT_S}\\,1)))"
    )


def clip_filter(
    duration: float,
    *,
    credit_file: Path,
    name_file: Path | None = None,
    name_lines: int = 1,
) -> str:
    """Portrait cover of a recorded clip with the Mapbox credit; the return clip
    also carries the site name, centred in the upper half."""
    parts = [f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"]
    if name_file is not None:
        size, line_h = 84, 100
        y = (H - name_lines * line_h) // 2 - 140
        parts.append(
            f"drawtext=fontfile='{ff_path(FONT_HEADING)}':textfile='{ff_path(name_file)}':"
            f"fontcolor=white:fontsize={size}:line_spacing=16:x=(w-text_w)/2:y={y}:"
            f"shadowcolor=black@0.6:shadowx=3:shadowy=3:alpha='{name_alpha(duration)}'"
        )
    parts.append(
        f"drawtext=fontfile='{ff_path(FONT_BODY)}':textfile='{ff_path(credit_file)}':"
        f"fontcolor=white@0.7:fontsize=22:x=w-text_w-28:y=h-52"
    )
    parts.append("format=yuv420p")
    return ",".join(parts)


def build_description(
    site: dict, images_used: list[dict], voice_id: str, mapbox_used: bool = False
) -> str:
    lines = [
        f"{site['name']} — {site['country']}",
        "",
        site["card_text"],
        "",
        f"Rarity: {site['rarity_name']} (Tier {site['rarity_tier']}) · Power {site['total_power']}",
        f"More: https://ancientnerds.com{site['page_path']}",
        "",
        "Images (Wikimedia Commons):",
    ]
    for img in images_used:
        lines.append(
            f"- {img.get('title') or img['filename']} — {img.get('author') or 'Unknown'}"
            f" ({img.get('license') or 'license unknown'}) {img.get('commons_page_url') or img['original_url']}"
        )
    if mapbox_used:
        lines += [
            "",
            f"Globe and terrain flyover: Mapbox Satellite Streets + Terrain DEM ({MAPBOX_CREDIT}).",
        ]
    lines += ["", f"Narration: AI-generated voice (MiniMax speech-2.8-hd, {voice_id})."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ffmpeg steps
# ---------------------------------------------------------------------------


def render_clip(
    src: Path,
    duration: float,
    out: Path,
    *,
    credit_file: Path,
    start: float = 0.0,
    name_file: Path | None = None,
    name_lines: int = 1,
) -> Path:
    vf = clip_filter(duration, credit_file=credit_file, name_file=name_file, name_lines=name_lines)
    return run_ffmpeg(
        ["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf, *X264], out
    )


def render_pan(src: Path, duration: float, forward: bool, vertical: bool, out: Path) -> Path:
    return run_ffmpeg(
        [
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{duration:.3f}",
            "-i",
            str(src),
            "-vf",
            pan_filter(duration, forward, vertical),
            *X264,
        ],
        out,
    )


def concat_and_mux(
    parts: list[Path], narration: Path, name_audio: Path, name_at_s: float, out: Path
) -> Path:
    """Concatenate the segments and lay the narration (from 0) and the spoken
    name (at `name_at_s`) under them; the video defines the length."""
    list_file = out.parent / "concat.txt"
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    ms = int(round(name_at_s * 1000))
    return run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-i",
            str(narration),
            "-i",
            str(name_audio),
            "-filter_complex",
            f"[1:a]apad[v];[2:a]adelay={ms}:all=1[n];"
            f"[v][n]amix=inputs=2:duration=first:normalize=0[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
        ],
        out,
    )


def render_short(site: dict, images: list[dict], site_dir: Path, voice_id: str) -> Path:
    """Assemble `<slug>.mp4` from the site dir's narration, name audio, images and clips."""
    narration = site_dir / "narration.mp3"
    name_audio = site_dir / "name.mp3"
    clips = site_dir / "clips"
    opening_clip = clips / "short-opening.mp4"
    closing_clip = clips / "short-return.mp4"
    opening = (
        (opening_clip, probe_duration(opening_clip) - OPENING_TRIM_S)
        if opening_clip.exists()
        else None
    )
    closing = (closing_clip, probe_duration(closing_clip)) if closing_clip.exists() else None

    segments = plan_timeline(
        narration_s=probe_duration(narration),
        images=[(Path(i["local_path"]), int(i["width"]), int(i["height"])) for i in images],
        opening=opening,
        closing=closing,
        opening_start=OPENING_TRIM_S,
    )
    work = site_dir / "render"
    work.mkdir(parents=True, exist_ok=True)
    (work / "timeline.json").write_text(
        json.dumps([asdict(s) for s in segments], indent=2), encoding="utf-8"
    )
    credit_file = work / "mapbox_credit.txt"
    credit_file.write_text(MAPBOX_CREDIT, encoding="utf-8")
    name_lines = wrap_lines(site["name"])
    name_file = work / "name.txt"
    name_file.write_text("\n".join(name_lines), encoding="utf-8")

    parts: list[Path] = []
    for n, seg in enumerate(segments):
        out = work / f"{n:02d}_{seg.kind}.mp4"
        logger.info("segment %02d %-7s %.2fs %s", n, seg.kind, seg.duration, seg.source or "")
        src = Path(seg.source or "")
        if seg.kind == "clip":
            render_clip(src, seg.duration, out, credit_file=credit_file, start=seg.start)
        elif seg.kind == "pan":
            render_pan(src, seg.duration, seg.forward, seg.vertical, out)
        else:
            render_clip(
                src,
                seg.duration,
                out,
                credit_file=credit_file,
                name_file=name_file,
                name_lines=len(name_lines),
            )
        parts.append(out)

    final = site_dir / f"{site['slug']}.mp4"
    concat_and_mux(parts, narration, name_audio, name_audio_at(segments), final)
    (site_dir / "description.txt").write_text(
        build_description(site, images, voice_id, mapbox_used=opening is not None),
        encoding="utf-8",
    )
    logger.info("short written: %s (%.2fs)", final, probe_duration(final))
    return final
