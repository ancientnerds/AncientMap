"""ffmpeg assembly of one site short (1080×1920, 30 fps).

Timeline (spec 2026-09-16):
  approach clip → narration visuals (terrain orbit, then Ken-Burns) → black beat
  → hero reveal with name / country / rarity ribbon / credit → URL.

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

W, H, FPS = 1080, 1920, 30

APPROACH_MAX_S = 4.0
NARRATION_TAIL_S = 0.6
TERRAIN_SLACK_S = 0.5  # deficit the narration tail can absorb before we cut to images
KENBURNS_MAX_S = 5.0
BEAT_S = 1.0
REVEAL_S = 7.0
URL_AT_S = 4.5
FADE_S = 0.6
KB_ZOOM = 0.12
TERRAIN_TRIM_S = 0.3  # Mapbox's first captured frame is still fading in
REVEAL_ZOOM = 0.08
CUT_FADE_S = 0.4  # dip-to-black at clip boundaries
BAND_TOP = 1050  # where the reveal's gradient band starts fading in
NAME_WRAP_CHARS = 16

FONT_DIR = Path(__file__).resolve().parents[2] / "video-assets" / "fonts"
FONT_HEADING = FONT_DIR / "orbitron-400-latin.ttf"
FONT_BODY = FONT_DIR / "jetbrains-mono-400-latin.ttf"

# Ribbon colours mirror ancient-nerds-map/src/constants/rarity.ts.
RARITY_COLORS: dict[int, str] = {
    5: "0xFFC107",
    4: "0x9C27B0",
    3: "0x00BCD4",
    2: "0x4CAF50",
    1: "0x9E9E9E",
}

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

SegmentKind = Literal["clip", "kenburns", "black", "reveal"]


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    duration: float
    source: str | None = None
    zoom_in: bool = True
    start: float = 0.0  # seek offset into a clip source


# ---------------------------------------------------------------------------
# Pure planning
# ---------------------------------------------------------------------------


def plan_timeline(
    *,
    narration_s: float,
    images: list[Path],
    approach: tuple[Path, float] | None,
    terrain: tuple[Path, float] | None,
    terrain_start: float = 0.0,
) -> list[Segment]:
    """Lay out the segments. `images[0]` is the hero used for the reveal.

    Clip tuples carry the *usable* duration (after any trim); `terrain_start`
    is the seek offset that trim implies.

    Narration visuals cover `narration_s + NARRATION_TAIL_S`: the terrain orbit
    first (as long as its clip lasts), Ken-Burns images for whatever remains.
    A terrain deficit of up to TERRAIN_SLACK_S is absorbed by the tail rather
    than producing a sub-second image cut.
    """
    if not images:
        raise ValueError("at least one image (the hero) is required")
    segments: list[Segment] = []
    if approach is not None:
        segments.append(Segment("clip", min(approach[1], APPROACH_MAX_S), str(approach[0])))

    span = narration_s + NARRATION_TAIL_S
    remainder = span
    if terrain is not None:
        used = min(terrain[1], span)
        remainder = span - used
        if remainder <= TERRAIN_SLACK_S:
            remainder = 0.0
        segments.append(Segment("clip", used, str(terrain[0]), start=terrain_start))

    if remainder > 0:
        pool = images[1:] or images  # keep the hero fresh for the reveal when we can
        count = max(1, min(len(pool), math.ceil(remainder / KENBURNS_MAX_S)))
        each = remainder / count
        for i in range(count):
            segments.append(Segment("kenburns", each, str(pool[i]), zoom_in=(i % 2 == 0)))

    segments.append(Segment("black", BEAT_S))
    segments.append(Segment("reveal", REVEAL_S, str(images[0])))
    return segments


def wrap_lines(name: str, width: int = NAME_WRAP_CHARS) -> list[str]:
    """Wrap a site name for the heading font (no auto-wrap in drawtext)."""
    return textwrap.wrap(name, width=width, break_long_words=True) or [name]


def kenburns_filter(zoom_in: bool, duration: float) -> str:
    """Blurred-fill portrait composite with a slow zoom driven by the frame index."""
    frames = f"{FPS}*{duration:.3f}"
    z = f"1+{KB_ZOOM}*on/({frames})" if zoom_in else f"{1 + KB_ZOOM}-{KB_ZOOM}*on/({frames})"
    return (
        f"[0:v]split[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=luma_radius=40:luma_power=3,eq=brightness=-0.12[bgb];"
        f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,scale={W * 2}:{H * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
        f"format=yuv420p"
    )


def fade_alpha(start: float, fade: float = FADE_S) -> str:
    return f"if(lt(t\\,{start})\\,0\\,if(lt(t\\,{start + fade})\\,(t-{start})/{fade}\\,1))"


def write_gradient_band(path: Path) -> Path:
    """Transparent→black RGBA overlay so the reveal texts sit on a soft band."""
    from PIL import Image

    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = band.load()
    for y in range(BAND_TOP, H):
        alpha = int(190 * min(1.0, (y - BAND_TOP) / 260))
        for x in range(W):
            px[x, y] = (0, 0, 0, alpha)
    band.save(path)
    return path


def reveal_filter(*, name_lines: int, ribbon_width: int, rarity_tier: int, text_dir: Path) -> str:
    """Cover-crop hero with slow zoom, dark bottom band, texts from textfiles."""
    heading = ff_path(FONT_HEADING)
    body = ff_path(FONT_BODY)
    name_size, name_lh = 72, 86
    y_name = 1240
    y_country = y_name + name_lines * name_lh + 18
    y_ribbon = y_country + 64
    ribbon_x = (W - ribbon_width) // 2
    color = RARITY_COLORS[rarity_tier]
    t = lambda f: ff_path(text_dir / f)  # noqa: E731 - local shorthand
    return (
        f"[0:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
        f"zoompan=z='1.04+{REVEAL_ZOOM}*on/({FPS}*{REVEAL_S})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={W}x{H}:fps={FPS}[hero];"
        f"[hero][1:v]overlay=0:0,"
        f"drawtext=fontfile='{heading}':textfile='{t('name.txt')}':fontcolor=white:fontsize={name_size}:"
        f"line_spacing=14:x=(w-text_w)/2:y={y_name}:alpha='{fade_alpha(0.4)}',"
        f"drawtext=fontfile='{body}':textfile='{t('country.txt')}':fontcolor=0xBBBBBB:fontsize=34:"
        f"x=(w-text_w)/2:y={y_country}:alpha='{fade_alpha(0.8)}',"
        f"drawbox=x={ribbon_x}:y={y_ribbon}:w={ribbon_width}:h=62:color={color}@0.95:t=fill:"
        f"enable='gte(t\\,1.2)',"
        f"drawtext=fontfile='{heading}':textfile='{t('ribbon.txt')}':fontcolor=black:fontsize=32:"
        f"x=(w-text_w)/2:y={y_ribbon + 15}:enable='gte(t\\,1.2)',"
        f"drawtext=fontfile='{heading}':textfile='{t('url.txt')}':fontcolor=white:fontsize=40:"
        f"x=(w-text_w)/2:y=1700:alpha='{fade_alpha(URL_AT_S)}',"
        f"drawtext=fontfile='{body}':textfile='{t('credit.txt')}':fontcolor=white@0.75:fontsize=24:"
        f"x=(w-text_w)/2:y=1830:alpha='{fade_alpha(0.8)}',"
        f"fade=t=in:st=0:d={CUT_FADE_S},fade=t=out:st={REVEAL_S - 0.5:.3f}:d=0.5,"
        f"format=yuv420p"
    )


def credit_line(image: dict) -> str:
    author = (image.get("author") or "Unknown").strip()
    lic = (image.get("license") or "").strip()
    parts = [f"Photo: {author}"]
    if lic:
        parts.append(lic)
    parts.append("Wikimedia Commons")
    return " · ".join(parts)


def build_description(site: dict, images_used: list[dict], voice_id: str) -> str:
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
    lines += ["", f"Narration: AI-generated voice (MiniMax speech-2.8-hd, {voice_id})."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ffmpeg steps
# ---------------------------------------------------------------------------


def render_clip(
    src: Path,
    duration: float,
    out: Path,
    start: float = 0.0,
    fade_in: bool = False,
    fade_out: bool = False,
) -> Path:
    fades = ""
    if fade_in:
        fades += f",fade=t=in:st=0:d={CUT_FADE_S}"
    if fade_out:
        fades += f",fade=t=out:st={duration - CUT_FADE_S:.3f}:d={CUT_FADE_S}"
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
        f"{fades},format=yuv420p"
    )
    return run_ffmpeg(
        ["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf, *X264], out
    )


def render_kenburns(src: Path, duration: float, zoom_in: bool, out: Path) -> Path:
    filt = kenburns_filter(zoom_in, duration)
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
            "-filter_complex",
            filt,
            *X264,
        ],
        out,
    )


def render_black(duration: float, out: Path) -> Path:
    return run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}", "-t", f"{duration:.3f}", *X264],
        out,
    )


def render_reveal(site: dict, hero: dict, out: Path) -> Path:
    text_dir = out.parent / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    name_lines = wrap_lines(site["name"])
    (text_dir / "name.txt").write_text("\n".join(name_lines), encoding="utf-8")
    (text_dir / "country.txt").write_text(site["country"] or "", encoding="utf-8")
    (text_dir / "ribbon.txt").write_text(site["rarity_name"].upper(), encoding="utf-8")
    (text_dir / "url.txt").write_text("ancientnerds.com", encoding="utf-8")
    (text_dir / "credit.txt").write_text(credit_line(hero), encoding="utf-8")
    ribbon_width = 40 + 26 * len(site["rarity_name"])
    filt = reveal_filter(
        name_lines=len(name_lines),
        ribbon_width=ribbon_width,
        rarity_tier=site["rarity_tier"],
        text_dir=text_dir,
    )
    return run_ffmpeg(
        [
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{REVEAL_S:.3f}",
            "-i",
            hero["local_path"],
            "-i",
            str(write_gradient_band(text_dir / "band.png")),
            "-filter_complex",
            filt,
            *X264,
        ],
        out,
    )


def concat_and_mux(parts: list[Path], narration: Path, offset_s: float, out: Path) -> Path:
    list_file = out.parent / "concat.txt"
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    ms = int(round(offset_s * 1000))
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
            "-filter_complex",
            f"[1:a]adelay={ms}:all=1,apad[a]",
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
    """Assemble `<slug>.mp4` from the site dir's narration, images and clips."""
    narration = site_dir / "narration.mp3"
    clips = site_dir / "clips"
    approach_clip = clips / "short-approach.mp4"
    terrain_clip = clips / "short-terrain.mp4"
    approach = (approach_clip, probe_duration(approach_clip)) if approach_clip.exists() else None
    terrain = (
        (terrain_clip, probe_duration(terrain_clip) - TERRAIN_TRIM_S)
        if terrain_clip.exists()
        else None
    )
    hero = next((i for i in images if i.get("is_hero")), images[0])
    ordered = [hero, *[i for i in images if i is not hero]]

    segments = plan_timeline(
        narration_s=probe_duration(narration),
        images=[Path(i["local_path"]) for i in ordered],
        approach=approach,
        terrain=terrain,
        terrain_start=TERRAIN_TRIM_S,
    )
    offset = min(approach[1], APPROACH_MAX_S) if approach else 0.0
    work = site_dir / "render"
    work.mkdir(parents=True, exist_ok=True)
    (work / "timeline.json").write_text(
        json.dumps([asdict(s) for s in segments], indent=2), encoding="utf-8"
    )

    parts: list[Path] = []
    for n, seg in enumerate(segments):
        out = work / f"{n:02d}_{seg.kind}.mp4"
        logger.info("segment %02d %-9s %.2fs %s", n, seg.kind, seg.duration, seg.source or "")
        if seg.kind == "clip":
            render_clip(
                Path(seg.source or ""),
                seg.duration,
                out,
                start=seg.start,
                fade_in=n > 0 and segments[n - 1].kind == "clip",
                fade_out=segments[n + 1].kind in ("clip", "black"),
            )
        elif seg.kind == "kenburns":
            render_kenburns(Path(seg.source or ""), seg.duration, seg.zoom_in, out)
        elif seg.kind == "black":
            render_black(seg.duration, out)
        else:
            render_reveal(site, hero, out)
        parts.append(out)

    final = site_dir / f"{site['slug']}.mp4"
    concat_and_mux(parts, narration, offset, final)
    (site_dir / "description.txt").write_text(
        build_description(site, ordered, voice_id), encoding="utf-8"
    )
    logger.info("short written: %s (%.2fs)", final, probe_duration(final))
    return final
