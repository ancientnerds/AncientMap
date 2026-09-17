"""ffmpeg assembly of one site short (1080×1920, 60 fps).

Loop cut (spec 2026-09-16, revised the same evening):
  narration from t=0 over: opening clip (satellite globe → zoom → 3D orbit, 6 s)
  → full-frame stills with a slow push-in, dissolving into each other → return
  clip (orbit → back to space) with the site name spoken and shown. The return
  clip's last frame is the opening's first frame, so the short loops without a
  visible cut.

Pure planning helpers (`plan_timeline`, `stills_graph`, filter builders) are
unit tested; the ffmpeg calls are thin wrappers verified by ffprobe on the output.
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
from pipeline.video.shorts_select import order_by_narration

logger = logging.getLogger(__name__)

W, H, FPS = 1080, 1920, 60

NARRATION_TAIL_S = 0.6
OPENING_SLACK_S = 0.5  # deficit the narration tail can absorb before we cut to stills
STILL_MAX_S = 3.5  # faster cuts — 5 s per still reads as a slideshow
PUSH_IN = 0.06  # every still zooms from 100 % to 106 % over its nominal duration
DISSOLVE_S = 0.4  # cross-dissolve between stills; the timeline length is unchanged
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

# Voice: 48 kHz float, gentle high-pass, a soft 1.8:1 compressor (slow, wide
# knee) so the level evens out without pumping. No reverb (user, 2026-09-16).
# Loudness is not regulated dynamically: the mix is measured once and lifted
# by a fixed gain to TARGET_LUFS with a true-peak limiter as the only safety net.
VOICE_CHAIN = (
    "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,"
    "highpass=f=80,"
    "acompressor=threshold=-24dB:ratio=1.8:attack=20:release=250:makeup=2:knee=6"
)
TARGET_LUFS = -14.0  # YouTube
PEAK_LIMIT = 0.75  # ≈ -2.5 dB sample peak; AAC adds inter-sample overshoot (Giza measured -0.5 dBTP at 0.84)
# "Historical" look for a homogeneous film: slightly desaturated and warm,
# lifted blacks / softened whites, vignette, fine grain. Applied once, over
# the whole concatenated picture, so globe and photos match.
LOOK_FILTER = (
    "eq=saturation=0.78:contrast=1.06,"
    "colorbalance=rs=0.06:gs=0.02:bs=-0.06:rm=0.04:bm=-0.05,"
    "curves=all='0/0.03 0.5/0.5 1/0.97',"
    "vignette=angle=PI/4.5,"
    "noise=alls=4:allf=t+u"
)

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

SegmentKind = Literal["clip", "still", "return"]


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    duration: float
    source: str | None = None
    start: float = 0.0  # seek offset into a clip source


# ---------------------------------------------------------------------------
# Pure planning
# ---------------------------------------------------------------------------


def plan_timeline(
    *,
    narration_s: float,
    images: list[Path],
    opening: tuple[Path, float] | None,
    closing: tuple[Path, float] | None,
    opening_start: float = 0.0,
) -> list[Segment]:
    """Lay out the segments. `images` is the selected stills in display order.

    The narration starts at t=0 and its visuals cover `narration_s +
    NARRATION_TAIL_S`: the opening clip first (as long as it lasts, after
    `opening_start` trim), full-frame stills for whatever remains. An opening
    deficit of up to OPENING_SLACK_S is absorbed by the tail rather than
    producing a sub-second still. The return clip follows, unshortened,
    because its last frame has to be the loop point.
    """
    if not images:
        raise ValueError("at least one still is required")
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
        count = max(1, min(len(images), math.ceil(remainder / STILL_MAX_S)))
        each = remainder / count
        segments.extend(Segment("still", each, str(images[i])) for i in range(count))

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


def pushin_filter(nominal_s: float) -> str:
    """Cover-scale the still to fill 1080×1920, then zoom linearly to 1+PUSH_IN
    over its nominal duration (continuing at the same rate through a dissolve
    tail), always cropping the centre."""
    z = f"(1+{PUSH_IN}*t/{nominal_s:.3f})"
    return (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"scale=eval=frame:w='iw*{z}':h='ih*{z}',crop={W}:{H},fps={FPS},format=yuv420p"
    )


def stills_graph(durations: list[float]) -> tuple[list[float], str]:
    """Input lengths and the filter_complex for a dissolving stills sequence.

    Every still but the last is fed DISSOLVE_S longer than its slot, and each
    xfade starts at the cumulative slot boundary, so the sequence is exactly
    sum(durations) long. A single still has no dissolve.
    """
    n = len(durations)
    if n == 0:
        raise ValueError("no stills")
    lengths = [d + DISSOLVE_S for d in durations[:-1]] + [durations[-1]]
    chains = [f"[{i}:v]{pushin_filter(durations[i])}[v{i}]" for i in range(n)]
    if n == 1:
        return lengths, chains[0].replace("[v0]", "[out]")
    xfades = []
    offset = 0.0
    prev = "[v0]"
    for i in range(1, n):
        offset += durations[i - 1]
        label = "[out]" if i == n - 1 else f"[x{i}]"
        xfades.append(
            f"{prev}[v{i}]xfade=transition=fade:duration={DISSOLVE_S}:offset={offset:.3f}{label}"
        )
        prev = label
    return lengths, ";".join(chains + xfades)


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


def render_stills(stills: list[Segment], out: Path) -> Path:
    """One dissolving sequence for a run of consecutive still segments."""
    lengths, graph = stills_graph([s.duration for s in stills])
    args: list[str] = []
    for seg, length in zip(stills, lengths, strict=True):
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", str(seg.source)]
    return run_ffmpeg([*args, "-filter_complex", graph, "-map", "[out]", *X264], out)


def mix_graph(name_at_s: float, total_s: float) -> str:
    """filter_complex for the voice pre-mix: inputs 0 = narration, 1 = spoken
    name. Both voices are processed, mixed, and bounded to exactly `total_s`."""
    ms = int(round(name_at_s * 1000))
    return (
        f"[0:a]{VOICE_CHAIN}[d0];"
        f"[1:a]{VOICE_CHAIN},adelay={ms}:all=1[d1];"
        f"[d0][d1]amix=inputs=2:duration=longest:normalize=0,"
        f"apad=whole_dur={total_s:.3f},atrim=duration={total_s:.3f}[a]"
    )


def premix(narration: Path, name_audio: Path, name_at_s: float, total_s: float, out: Path) -> Path:
    return run_ffmpeg(
        [
            "-i",
            str(narration),
            "-i",
            str(name_audio),
            "-filter_complex",
            mix_graph(name_at_s, total_s),
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
        ],
        out,
    )


def measure_lufs(audio: Path) -> float:
    """Integrated loudness (EBU R128) of a file, from ffmpeg's ebur128 summary."""
    import re
    import subprocess

    from pipeline.video.media import FFMPEG_BIN

    proc = subprocess.run(
        [
            FFMPEG_BIN,
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio),
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Integrated loudness:\s*I:\s*(-?[\d.]+) LUFS", proc.stderr)
    if not match:
        raise RuntimeError(f"ebur128 gave no integrated loudness for {audio}: {proc.stderr[-400:]}")
    return float(match.group(1))


def gain_db(measured_lufs: float, target_lufs: float = TARGET_LUFS) -> float:
    return target_lufs - measured_lufs


def final_graph(gain: float) -> str:
    """filter_complex for the final pass: graded picture; pre-mixed voice lifted
    by a fixed gain with a true-peak limiter as the only dynamic element."""
    return (
        f"[0:v]{LOOK_FILTER}[vout];"
        f"[1:a]volume={gain:.2f}dB,alimiter=limit={PEAK_LIMIT}:level=false[a]"
    )


def concat_and_mux(parts: list[Path], mix: Path, gain: float, out: Path) -> Path:
    """Concatenate the segments, grade the picture, and lay the pre-mixed voice
    under them. The mix is already exactly as long as the picture, so no
    -shortest: that flag cut the buffered tail (the spoken name) in an earlier cut."""
    list_file = out.parent / "concat.txt"
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    return run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-i",
            str(mix),
            "-filter_complex",
            final_graph(gain),
            "-map",
            "[vout]",
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
            "-movflags",
            "+faststart",
        ],
        out,
    )


def render_short(site: dict, stills: list[dict], site_dir: Path, voice_id: str) -> Path:
    """Assemble `<slug>.mp4` from the site dir's narration, name audio, selected stills and clips."""
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

    narration_s = probe_duration(narration)
    plan = {"opening": opening, "closing": closing, "opening_start": OPENING_TRIM_S}
    # First pass sizes the slots; the stills that fit (best scores first) are
    # then shown in narration order, and the plan is rebuilt with that order.
    draft = plan_timeline(
        narration_s=narration_s, images=[Path(i["local_path"]) for i in stills], **plan
    )
    slots = sum(1 for s in draft if s.kind == "still")
    chosen = order_by_narration(stills[:slots], site["card_text"], lambda s: s.get("verdict"))
    segments = plan_timeline(
        narration_s=narration_s, images=[Path(i["local_path"]) for i in chosen], **plan
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
    n = 0
    while n < len(segments):
        seg = segments[n]
        out = work / f"{n:02d}_{seg.kind}.mp4"
        if seg.kind == "still":
            run = [s for s in segments[n:] if s.kind == "still"]
            run = run[
                : next((i for i, s in enumerate(segments[n:]) if s.kind != "still"), len(run))
            ]
            for s in run:
                logger.info("still   %.2fs %s", s.duration, s.source)
            render_stills(run, out)
            n += len(run)
        else:
            logger.info("%-7s %.2fs %s", seg.kind, seg.duration, seg.source)
            render_clip(
                Path(seg.source or ""),
                seg.duration,
                out,
                credit_file=credit_file,
                start=seg.start,
                name_file=name_file if seg.kind == "return" else None,
                name_lines=len(name_lines),
            )
            n += 1
        parts.append(out)

    used = [s for s in stills if any(seg.source == s["local_path"] for seg in segments)]
    final = site_dir / f"{site['slug']}.mp4"
    total_s = sum(s.duration for s in segments)
    mix = premix(narration, name_audio, name_audio_at(segments), total_s, work / "mix.wav")
    lufs = measure_lufs(mix)
    logger.info("voice mix %.1f LUFS → gain %+.1f dB", lufs, gain_db(lufs))
    concat_and_mux(parts, mix, gain_db(lufs), final)
    (site_dir / "description.txt").write_text(
        build_description(site, used, voice_id, mapbox_used=opening is not None),
        encoding="utf-8",
    )
    logger.info("short written: %s (%.2fs)", final, probe_duration(final))
    return final
