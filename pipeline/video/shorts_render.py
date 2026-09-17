"""ffmpeg assembly of one site short (1080×1920, 60 fps).

Loop cut (spec 2026-09-16, revised the same evening):
  narration from t=0 over: opening clip (satellite globe → zoom → 3D orbit, 6 s)
  → full-frame stills with a slow push-in, hard-cut under a camera flash → return
  clip (orbit → back to space) with the site name spoken and shown. The return
  clip's last frame is the opening's first frame, so the short loops without a
  visible cut.

Pure planning helpers (`plan_timeline`, `stills_graph`, filter builders) are
unit tested; the ffmpeg calls are thin wrappers verified by ffprobe on the output.
"""

from __future__ import annotations

import json
import logging
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pipeline.video.media import ff_path, probe_duration, probe_frames, run_ffmpeg
from pipeline.video.shorts_brand import FONT_BODY, FONT_HEADING, ensure_fonts, heading_font
from pipeline.video.shorts_captions import Word, caption_words, display_text, spoken_at, srt_text
from pipeline.video.shorts_select import focus_of
from pipeline.video.shorts_tts import specific_place

logger = logging.getLogger(__name__)

W, H, FPS = 1080, 1920, 60

NARRATION_TAIL_S = 0.6
OPENING_SLACK_S = 0.5  # deficit the narration tail can absorb before we cut to stills
# Stills cut on the narration: a still arrives CUT_LEAD_S before the word it
# illustrates is spoken, but never sooner than MIN_STILL_S after the previous
# cut — the pace must not turn into a flicker (user, 17.09.). A still pushed
# later than CUT_MAX_LATE_S by that rule is placed as a filler instead.
MIN_STILL_S = 2.2
CUT_LEAD_S = 0.2
CUT_MAX_LATE_S = 1.0
PUSH_IN = 0.06  # every still zooms from 100 % to 106 % over its nominal duration
# The zoom is rendered by zoompan on a SUPER× supersampled still and scaled
# down per frame: at 1080 px the integer scale sizes and even-aligned crops
# quantised the motion to whole pixels (measured: every third frame jumped,
# the others stood still — "ruckelt"); at 4× a step is a quarter pixel.
SUPER = 4
NAME_FADE_IN_S = 0.3
NAME_FADE_OUT_S = 0.5
NAME_END_GAP_S = 0.15  # fully gone this long before the clip ends = the loop point
NAME_AUDIO_DELAY_S = 0.2  # spoken name starts shortly after the return clip begins
NAME_WRAP_CHARS = 14
FLAG_W = 180  # flag under the name (3:2 → 120 px tall)
# Word-by-word captions: one word at a time, lower third. Like the site's
# hero title: white heading font with a black outline, no box (user, 17.09.).
CAPTION_SIZE = 92
CAPTION_Y = 1230
CAPTION_BORDER = 5
NAME_BORDER = 3
FLAG_GAP = 72  # 34 had the flag glued to the name (user, 17.09.)
# Camera flash at the start of every still (user, 17.09.): white at FLASH_PEAK
# on the first frame, gone after FLASH_S. The times go to render/flashes.json
# so a shutter sound can sit exactly on them (`flash` audio, when present).
FLASH_S = 0.28
FLASH_PEAK = 0.85
FLASH_GAIN_DB = -12.0  # user 17.09.: quieter
# Whoosh at the opening's zoom-in (ROTATE_S into the take, video/scenes/site-short.ts)
# and at the start of the return flight.
OPENING_ZOOM_AT_S = 1.0
WHOOSH_GAIN_DB = -14.0  # user 17.09.: quieter
OPENING_TRIM_S = 0.1  # the opening take holds its first pose this long; the first frames after a
# jump are not fully drawn, so cutting the hold keeps frame 0 identical to the loop's end pose
# Mapbox ToS: satellite/terrain frames need attribution in the video itself;
# the DOM logo is not part of the captured canvas.
MAPBOX_CREDIT = "© Mapbox © Maxar"

# Music bed: looped under the whole short, faded in at the start and out
# before the loop point so the video loops cleanly; MUSIC_GAIN_DB sits it
# under the voice (the loudness gain is measured on the full mix).
MUSIC_GAIN_DB = -8.0  # level in the pauses; under the voice the ducking takes it down further
# Ducking: the music is compressed with the voice as the side-chain, so it
# breathes up in the pauses and steps back while the narrator speaks.
# Measured on Machu Picchu: about 8 dB under the voice, back up within a sentence gap.
DUCK = "threshold=0.04:ratio=2:attack=40:release=500:detection=rms"
MUSIC_FADE_IN_S = 1.0
MUSIC_FADE_OUT_S = 3.0  # a full song needs a long tail; 1.2 s sounded chopped (user, Olympia)
MUSIC_END_GAP_S = 0.3  # silent before the loop point (audit: silent_loop_point)

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
PEAK_LIMIT = (
    0.75  # ≈ -2.5 dB sample peak; AAC adds inter-sample overshoot (Giza measured -0.5 dBTP at 0.84)
)
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


def stills_window(narration_s: float, opening_s: float | None) -> tuple[float, float]:
    """(start, end) of the stills in video time. The narration starts at t=0 and
    its visuals cover `narration_s + NARRATION_TAIL_S`: the opening clip first
    (as long as it lasts), stills for whatever remains. An opening deficit of
    up to OPENING_SLACK_S is absorbed by the tail rather than producing a
    sub-second still (then start == end)."""
    span = narration_s + NARRATION_TAIL_S
    if opening_s is None:
        return 0.0, span
    used = min(opening_s, span)
    if span - used <= OPENING_SLACK_S:
        return used, used
    return used, span


@dataclass(frozen=True)
class StillPick:
    path: str
    score: float
    anchor: float | None = None  # when the phrase this still illustrates is spoken (video time)


def cut_stills(start: float, end: float, picks: list[StillPick]) -> list[tuple[str, float]]:
    """(path, duration) for the stills window [start, end); durations sum to
    end - start. The best still that is already "due" (its phrase was spoken
    before the window, or it has none) opens; every still whose phrase falls
    inside the window cuts in CUT_LEAD_S before its word, never sooner than
    MIN_STILL_S after the previous cut (a little late is accepted, later than
    CUT_MAX_LATE_S it is skipped here); the remaining stills, best first, fill
    any gap that holds two minimum stills — at their own word if that lies in
    the gap, else in the middle."""
    if not picks:
        raise ValueError("no stills")
    if end - start <= 0:
        return []
    by_score = sorted(picks, key=lambda p: -p.score)

    def placeable(p: StillPick) -> bool:
        return p.anchor is not None and p.anchor - CUT_LEAD_S >= start + MIN_STILL_S

    due = [p for p in by_score if not placeable(p)]
    first = due[0] if due else min(by_score, key=lambda p: p.anchor or 0.0)
    cuts: list[tuple[StillPick, float]] = [(first, start)]
    remaining = [p for p in by_score if p is not first]
    prev = start
    for p in sorted((p for p in remaining if placeable(p)), key=lambda p: p.anchor or 0.0):
        at = (p.anchor or 0.0) - CUT_LEAD_S
        if at < prev + MIN_STILL_S:
            if prev + MIN_STILL_S - at > CUT_MAX_LATE_S:
                continue
            at = prev + MIN_STILL_S
        if at > end - MIN_STILL_S:
            continue
        cuts.append((p, at))
        remaining.remove(p)
        prev = at
    while remaining:
        starts = [at for _, at in cuts] + [end]
        size, i = max((starts[i + 1] - starts[i], i) for i in range(len(cuts)))
        if size < 2 * MIN_STILL_S:
            break
        p = remaining.pop(0)
        lo, hi = starts[i] + MIN_STILL_S, starts[i + 1] - MIN_STILL_S
        own = (p.anchor or 0.0) - CUT_LEAD_S
        at = own if p.anchor is not None and lo <= own <= hi else (starts[i] + starts[i + 1]) / 2
        cuts.insert(i + 1, (p, at))
    starts = [at for _, at in cuts] + [end]
    return [(p.path, starts[i + 1] - starts[i]) for i, (p, _) in enumerate(cuts)]


def plan_timeline(
    *,
    narration_s: float,
    cuts: list[tuple[str, float]],
    opening: tuple[Path, float] | None,
    closing: tuple[Path, float] | None,
    opening_start: float = 0.0,
) -> list[Segment]:
    """Lay out the segments: the opening clip (after `opening_start` trim) for
    the start of the stills window, the stills as cut by `cut_stills`, then
    the return clip, unshortened, because its last frame has to be the loop
    point."""
    start, end = stills_window(narration_s, opening[1] if opening else None)
    segments: list[Segment] = []
    if opening is not None:
        segments.append(Segment("clip", start, str(opening[0]), start=opening_start))
    if end > start:
        if not cuts:
            raise ValueError("at least one still is required")
        if abs(sum(d for _, d in cuts) - (end - start)) > 1e-3:
            raise ValueError("still durations do not fill the stills window")
        segments.extend(Segment("still", d, path) for path, d in cuts)
    if closing is not None:
        segments.append(Segment("return", closing[1], str(closing[0])))
    return segments


def segment_starts(segments: list[Segment], clip_frames: list[int] | None = None) -> list[float]:
    """Start time of every segment, counted in frames: the concat boundary sits
    on a frame, not on the fractional second. Stills are rendered with exactly
    round(duration × FPS) frames; a trimmed clip may come out a frame short of
    that, so `clip_frames` carries the rendered clip parts' real counts (in
    order)."""
    starts: list[float] = []
    frames = 0
    clips = iter(clip_frames or [])
    for seg in segments:
        starts.append(frames / FPS)
        if seg.kind == "still":
            frames += round(seg.duration * FPS)
        else:
            frames += next(clips, round(seg.duration * FPS))
    return starts


def flash_times(segments: list[Segment], clip_frames: list[int] | None = None) -> list[float]:
    """When each still starts — the photo is "taken" there."""
    starts = segment_starts(segments, clip_frames)
    return [t for seg, t in zip(segments, starts, strict=True) if seg.kind == "still"]


def name_audio_at(segments: list[Segment], name_s: float) -> float:
    """When the spoken name starts: shortly into the return clip, or at the end
    of the stills when no return clip was recorded — but never so late that a
    long name (Gochang, Hwasun and Ganghwa Dolmen Sites: 6 s) runs past the
    loop point; then it starts early, over the last stills."""
    total = sum(s.duration for s in segments)
    before = sum(s.duration for s in segments if s.kind != "return")
    has_return = any(s.kind == "return" for s in segments)
    natural = before + NAME_AUDIO_DELAY_S if has_return else before
    latest = total - name_s - NAME_END_GAP_S
    return max(0.0, min(natural, latest))


def wrap_lines(name: str, width: int = NAME_WRAP_CHARS) -> list[str]:
    """Wrap a site name for the heading font (no auto-wrap in drawtext)."""
    return textwrap.wrap(name, width=width, break_long_words=True) or [name]


# (wrap width, font size, line height) from large to small; the first layout
# that needs at most NAME_MAX_LINES lines wins, the smallest is the floor.
NAME_LAYOUTS: tuple[tuple[int, int, int], ...] = ((14, 84, 100), (20, 64, 78), (26, 52, 64))
NAME_MAX_LINES = 3
NAME_PREFERRED_LINES = 2


def name_layout(name: str) -> tuple[list[str], int, int]:
    """(lines, font size, line height) for the name overlay: the largest font
    that fits the name in at most two lines ("Archaeological Site / of
    Olympia", not a lone "Olympia" on a third line); three lines only when
    even the smallest layout needs them."""
    for width, size, line_h in NAME_LAYOUTS:
        lines = wrap_lines(name, width)
        if len(lines) <= NAME_PREFERRED_LINES:
            return lines, size, line_h
    width, size, line_h = NAME_LAYOUTS[-1]
    return wrap_lines(name, width), size, line_h


def pushin_filter(
    duration_s: float, focus: tuple[float, float] = (0.5, 0.5), *, push_out: bool = False
) -> str:
    """Cover-scale the still to SUPER× the frame, cut the 9:16 window around
    the subject's focal point (clamped to the picture), then zoompan the
    still's frames around the centre: in, from 100 % to 1+PUSH_IN, or out,
    from 1+PUSH_IN back to 100 %, over the still's duration. The still is
    decoded once; zoompan does one downscale per frame."""
    fx, fy = focus
    sw, sh = W * SUPER, H * SUPER
    frames = round(duration_s * FPS)
    z = f"1+{PUSH_IN}*(1-on/{frames})" if push_out else f"1+{PUSH_IN}*on/{frames}"
    window = (
        f"x='min(max(iw*{fx:.3f}-{sw / 2:.0f}\\,0)\\,iw-{sw})':"
        f"y='min(max(ih*{fy:.3f}-{sh / 2:.0f}\\,0)\\,ih-{sh})'"
    )
    return (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh}:{window},"
        f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={W}x{H}:fps={FPS},setsar=1,format=yuv420p"
    )


def stills_graph(durations: list[float], focuses: list[tuple[float, float]] | None = None) -> str:
    """filter_complex for a run of stills, hard-cut one after the other (the
    camera flash in the final pass is the transition). `focuses` (one (x, y)
    per still) moves each crop window onto its subject; the stills alternate
    push-in and push-out for rhythm."""
    n = len(durations)
    if n == 0:
        raise ValueError("no stills")
    focuses = focuses or [(0.5, 0.5)] * n
    chains = [
        f"[{i}:v]" + pushin_filter(durations[i], focuses[i], push_out=bool(i % 2)) + f"[v{i}]"
        for i in range(n)
    ]
    if n == 1:
        return chains[0].replace("[v0]", "[out]")
    inputs = "".join(f"[v{i}]" for i in range(n))
    return ";".join(chains) + f";{inputs}concat=n={n}:v=1:a=0[out]"


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


def name_block_top(name_lines: int, line_h: int) -> int:
    """Top of the name block: centred in the upper half of the frame."""
    return (H - name_lines * line_h) // 2 - 140


def return_overlays_graph(duration: float, name_lines: int, line_h: int) -> str:
    """filter_complex tail for the return clip: the flag (input 1) centred under
    the name block, fading in and out with the name."""
    top = name_block_top(name_lines, line_h)
    end = duration - NAME_END_GAP_S
    y = top + name_lines * line_h + FLAG_GAP
    return (
        f"[1:v]format=rgba,scale={FLAG_W}:-1,"
        f"fade=t=in:st=0:d={NAME_FADE_IN_S}:alpha=1,"
        f"fade=t=out:st={end - NAME_FADE_OUT_S:.3f}:d={NAME_FADE_OUT_S}:alpha=1[flag];"
        f"[base][flag]overlay=x=(W-w)/2:y={y}:shortest=1[out]"
    )


def clip_filter(
    duration: float,
    *,
    credit_file: Path,
    name_file: Path | None = None,
    name_lines: int = 1,
    name_size: int = 84,
    name_line_h: int = 100,
    font: Path = FONT_HEADING,
) -> str:
    """Portrait cover of a recorded clip with the Mapbox credit; the return clip
    also carries the site name, centred in the upper half, white with a black
    outline like the site's hero title."""
    parts = [f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"]
    if name_file is not None:
        size, line_h = name_size, name_line_h
        y = name_block_top(name_lines, line_h)
        parts.append(
            f"drawtext=fontfile='{ff_path(font)}':textfile='{ff_path(name_file)}':"
            f"fontcolor=white:fontsize={size}:line_spacing=16:x=(w-text_w)/2:y={y}:"
            f"borderw={NAME_BORDER}:bordercolor=black:"
            f"shadowcolor=black@0.6:shadowx=3:shadowy=3:alpha='{name_alpha(duration)}'"
        )
    parts.append(
        f"drawtext=fontfile='{ff_path(FONT_BODY)}':textfile='{ff_path(credit_file)}':"
        f"fontcolor=white@0.7:fontsize=22:x=w-text_w-28:y=h-52"
    )
    parts.append("format=yuv420p")
    return ",".join(parts)


def hashtag(text: str) -> str:
    """ "Machu Picchu" → "#MachuPicchu"."""
    return "#" + "".join(ch for ch in text.title() if ch.isalnum())


def hashtags(site: dict) -> list[str]:
    """Fixed channel tags first (YouTube shows the first three above the
    title), then the place and the site."""
    tags = ["#Shorts", "#archaeology", "#ancienthistory"]
    for text in (specific_place(site.get("country")), site["name"]):
        tag = hashtag(text)
        if len(tag) > 1 and tag not in tags:
            tags.append(tag)
    return tags


def build_comment(site: dict) -> str:
    """Pinned comment for the upload step: a question (comments are the
    strongest signal) and the one place the site link lives."""
    return (
        f"Have you been to {site['name']}? Explore it on the interactive globe, "
        f"with sources and photos: https://ancientnerds.com{site['page_path']}\n"
    )


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
    lines += ["", " ".join(hashtags(site))]
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
    name_size: int = 84,
    name_line_h: int = 100,
) -> Path:
    vf = clip_filter(
        duration,
        credit_file=credit_file,
        name_file=name_file,
        name_lines=name_lines,
        name_size=name_size,
        name_line_h=name_line_h,
    )
    return run_ffmpeg(
        ["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}", "-vf", vf, *X264], out
    )


def render_return(
    src: Path,
    duration: float,
    out: Path,
    *,
    credit_file: Path,
    name_file: Path,
    name_lines: int,
    name_size: int,
    name_line_h: int,
    flag: Path | None,
    font: Path = FONT_HEADING,
) -> Path:
    """The return clip: name overlay (clip_filter) plus the flag under the name."""
    base = clip_filter(
        duration,
        credit_file=credit_file,
        name_file=name_file,
        name_lines=name_lines,
        name_size=name_size,
        name_line_h=name_line_h,
        font=font,
    )
    if flag is None:
        return run_ffmpeg(["-i", str(src), "-t", f"{duration:.3f}", "-vf", base, *X264], out)
    tail = return_overlays_graph(duration, name_lines, name_line_h)
    return run_ffmpeg(
        [
            "-i",
            str(src),
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(flag),
            "-t",
            f"{duration:.3f}",
            "-filter_complex",
            f"[0:v]{base}[base];{tail}",
            "-map",
            "[out]",
            *X264,
        ],
        out,
    )


def render_stills(
    stills: list[Segment], out: Path, focuses: list[tuple[float, float]] | None = None
) -> Path:
    """One dissolving sequence for a run of consecutive still segments. Each
    still is a single-frame input; zoompan generates its frames."""
    graph = stills_graph([s.duration for s in stills], focuses)
    args: list[str] = []
    for seg in stills:
        args += ["-i", str(seg.source)]
    return run_ffmpeg([*args, "-filter_complex", graph, "-map", "[out]", *X264], out)


STEREO = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"


def _sound_at(
    parts: list[str], extras: list[str], src: int, tag: str, times: list[float], gain_db: float
) -> None:
    """Copy input `src` to every time in `times` (asplit + adelay) at `gain_db`."""
    n = len(times)
    parts.append(
        f"[{src}:a]{STEREO},volume={gain_db}dB,asplit={n}"
        + "".join(f"[{tag}{i}]" for i in range(n))
    )
    for i, t in enumerate(times):
        parts.append(f"[{tag}{i}]adelay={int(round(t * 1000))}:all=1[{tag}d{i}]")
        extras.append(f"[{tag}d{i}]")


def mix_graph(
    name_at_s: float,
    total_s: float,
    music: bool = False,
    flashes: list[float] | None = None,
    whooshes: list[float] | None = None,
) -> str:
    """filter_complex for the pre-mix: inputs 0 = narration, 1 = spoken name,
    2 = music (looped by the caller), then the flash sound when `flashes`
    (its times) is given, then the whoosh when `whooshes` is given. The
    voices are processed and mixed; the music is trimmed to the short, faded
    in/out (silent MUSIC_END_GAP_S before the loop point), lowered by
    MUSIC_GAIN_DB and ducked under the voice; each effect is copied to its
    times; everything is bounded to exactly `total_s`."""
    ms = int(round(name_at_s * 1000))
    tail = f"apad=whole_dur={total_s:.3f},atrim=duration={total_s:.3f}[a]"
    parts = [
        f"[0:a]{VOICE_CHAIN},{STEREO}[d0]",
        f"[1:a]{VOICE_CHAIN},adelay={ms}:all=1,{STEREO}[d1]",
        "[d0][d1]amix=inputs=2:duration=longest:normalize=0[v]",
    ]
    voice = "[v]"
    extras: list[str] = []
    if music:
        fade_out_at = total_s - MUSIC_END_GAP_S - MUSIC_FADE_OUT_S
        parts += [
            # the side-chain is padded to the full length so the music is never cut
            # short when the voice ends first
            f"[v]apad=whole_dur={total_s:.3f},asplit[vm][vsc]",
            f"[2:a]{STEREO},atrim=duration={total_s - MUSIC_END_GAP_S:.3f},"
            f"afade=t=in:st=0:d={MUSIC_FADE_IN_S},"
            f"afade=t=out:st={fade_out_at:.3f}:d={MUSIC_FADE_OUT_S},"
            f"volume={MUSIC_GAIN_DB}dB[m]",
            f"[m][vsc]sidechaincompress={DUCK}[md]",
        ]
        voice, extras = "[vm]", ["[md]"]
    src = 2 + int(music)
    if flashes:
        _sound_at(parts, extras, src, "s", flashes, FLASH_GAIN_DB)
        src += 1
    if whooshes:
        _sound_at(parts, extras, src, "w", whooshes, WHOOSH_GAIN_DB)
    if extras:
        parts.append(
            f"{voice}{''.join(extras)}amix=inputs={1 + len(extras)}:duration=longest:normalize=0,"
            f"{tail}"
        )
    else:
        parts.append(f"{voice}{tail}")
    return ";".join(parts)


def premix(
    narration: Path,
    name_audio: Path,
    name_at_s: float,
    total_s: float,
    out: Path,
    music: Path | None = None,
    flash: Path | None = None,
    flashes: list[float] | None = None,
    music_start: float = 0.0,
    whoosh: Path | None = None,
    whooshes: list[float] | None = None,
) -> Path:
    """`music_start` seeks that far into the track before the loop begins
    (the user's pick of where the song gets going)."""
    music_args = (
        ["-stream_loop", "-1", "-ss", f"{music_start:.3f}", "-i", str(music)] if music else []
    )
    flash_args = ["-i", str(flash)] if flash and flashes else []
    whoosh_args = ["-i", str(whoosh)] if whoosh and whooshes else []
    return run_ffmpeg(
        [
            "-i",
            str(narration),
            "-i",
            str(name_audio),
            *music_args,
            *flash_args,
            *whoosh_args,
            "-filter_complex",
            mix_graph(
                name_at_s,
                total_s,
                music=music is not None,
                flashes=flashes if flash else None,
                whooshes=whooshes if whoosh else None,
            ),
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


def captions_filter(words: list[Word], text_dir: Path, font: Path = FONT_HEADING) -> str:
    """One drawtext per word, shown exactly between its start and end: white
    heading font with a black outline (the site's title style), no box, no
    edge punctuation. Words go to text files (no escaping of apostrophes,
    commas or percent signs); a token that is punctuation only (a dash) gets
    no caption."""
    text_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, word in enumerate(words):
        shown = display_text(word.text)
        if not shown:
            continue
        f = text_dir / f"w{i:03d}.txt"
        f.write_text(shown, encoding="utf-8", newline=chr(10))
        parts.append(
            f"drawtext=fontfile='{ff_path(font)}':textfile='{ff_path(f)}':"
            f"fontcolor=white:fontsize={CAPTION_SIZE}:x=(w-text_w)/2:y={CAPTION_Y}:"
            f"borderw={CAPTION_BORDER}:bordercolor=black:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
            f"enable='between(t\\,{word.start:.3f}\\,{word.end:.3f})'"
        )
    return ",".join(parts)


def overlays_filter(words: list[Word], work: Path, font: Path = FONT_HEADING) -> str:
    """The final-pass text layer: the word-by-word captions, drawn after the
    look filter so the text stays clean."""
    return captions_filter(words, work / "captions", font)


def final_graph(gain: float, overlays: str = "", flashes: list[float] | None = None) -> str:
    """filter_complex for the final pass: graded picture, a camera flash at
    every still start (a white layer that decays over FLASH_S), the text layer
    on top; pre-mixed voice lifted by a fixed gain with a true-peak limiter as
    the only dynamic element."""
    parts: list[str] = []
    src, stage = "[0:v]", LOOK_FILTER
    n = 0
    for t in flashes or []:
        parts.append(f"{src}{stage}[g{n}]")
        parts.append(
            f"color=c=white@{FLASH_PEAK}:s={W}x{H}:r={FPS}:d={FLASH_S},format=rgba,"
            f"fade=t=out:st=0:d={FLASH_S}:alpha=1,setpts=PTS+{t:.3f}/TB[f{n}]"
        )
        src = f"[g{n}][f{n}]"
        # half a frame early so the boundary frame itself is inside the window
        t0 = t - 0.5 / FPS
        stage = rf"overlay=eof_action=pass:enable='between(t\,{t0:.3f}\,{t0 + FLASH_S:.3f})'"
        n += 1
    if overlays:
        stage = f"{stage},{overlays}"
    parts.append(f"{src}{stage}[vout]")
    parts.append(f"[1:a]volume={gain:.2f}dB,alimiter=limit={PEAK_LIMIT}:level=false[a]")
    return ";".join(parts)


def concat_and_mux(
    parts: list[Path],
    mix: Path,
    gain: float,
    out: Path,
    overlays: str = "",
    flashes: list[float] | None = None,
) -> Path:
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
            final_graph(gain, overlays, flashes),
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


def render_short(
    site: dict,
    stills: list[dict],
    site_dir: Path,
    voice_id: str,
    *,
    flag: Path | None = None,
    music: Path | None = None,
    flash: Path | None = None,
    music_start: float = 0.0,
    whoosh: Path | None = None,
) -> Path:
    """Assemble `<slug>.mp4` from the site dir's narration, name audio, selected
    stills and clips; `flag` goes under the name, `music` (from `music_start`
    seconds into the track) under everything, `flash` (a shutter sound) on
    every still start, `whoosh` on the zoom-in and the return flight."""
    ensure_fonts()
    font = heading_font(site["name"] + " " + site["card_text"])
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
    work = site_dir / "render"
    work.mkdir(parents=True, exist_ok=True)
    words = caption_words(site["card_text"], narration)
    (work / "captions.json").write_text(
        json.dumps([w.__dict__ for w in words], indent=1), encoding="utf-8"
    )
    (site_dir / "captions.srt").write_text(srt_text(words), encoding="utf-8", newline=chr(10))
    start, end = stills_window(narration_s, opening[1] if opening else None)
    picks = [
        StillPick(
            st["local_path"],
            st["score"],
            spoken_at(site["card_text"], (st.get("verdict") or {}).get("illustrates") or "", words),
        )
        for st in stills
    ]
    cuts = cut_stills(start, end, picks) if end > start else []
    segments = plan_timeline(
        narration_s=narration_s,
        cuts=cuts,
        opening=opening,
        closing=closing,
        opening_start=OPENING_TRIM_S,
    )
    (work / "timeline.json").write_text(
        json.dumps([asdict(s) for s in segments], indent=2), encoding="utf-8"
    )
    credit_file = work / "mapbox_credit.txt"
    credit_file.write_text(MAPBOX_CREDIT, encoding="utf-8")
    name_lines, name_size, name_line_h = name_layout(site["name"])
    name_file = work / "name.txt"
    # LF only: on Windows write_text would emit CR LF and drawtext renders the CR as an empty line
    name_file.write_text(chr(10).join(name_lines), encoding="utf-8", newline=chr(10))

    focus_by_path = {st["local_path"]: focus_of(st.get("verdict")) for st in stills}
    parts: list[Path] = []
    clip_frames: list[int] = []  # real frame counts of the rendered clip parts, for the flashes
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
            render_stills(run, out, [focus_by_path.get(s.source or "", (0.5, 0.5)) for s in run])
            n += len(run)
        else:
            logger.info("%-7s %.2fs %s", seg.kind, seg.duration, seg.source)
            src = Path(seg.source or "")
            if seg.kind == "clip":
                render_clip(src, seg.duration, out, credit_file=credit_file, start=seg.start)
                clip_frames.append(probe_frames(out))
            else:
                render_return(
                    src,
                    seg.duration,
                    out,
                    credit_file=credit_file,
                    name_file=name_file,
                    name_lines=len(name_lines),
                    name_size=name_size,
                    name_line_h=name_line_h,
                    flag=flag,
                    font=font,
                )
            n += 1
        parts.append(out)

    used = [s for s in stills if any(seg.source == s["local_path"] for seg in segments)]
    final = site_dir / f"{site['slug']}.mp4"
    total_s = sum(s.duration for s in segments)
    name_at = name_audio_at(segments, probe_duration(name_audio))
    starts = segment_starts(segments, clip_frames)
    flashes = [t for seg, t in zip(segments, starts, strict=True) if seg.kind == "still"]
    whooshes = ([OPENING_ZOOM_AT_S] if opening is not None else []) + [
        t for seg, t in zip(segments, starts, strict=True) if seg.kind == "return"
    ]
    (work / "sfx.json").write_text(
        json.dumps({"flashes": flashes, "whooshes": whooshes}), encoding="utf-8"
    )
    mix = premix(
        narration,
        name_audio,
        name_at,
        total_s,
        work / "mix.wav",
        music=music,
        flash=flash,
        flashes=flashes,
        music_start=music_start,
        whoosh=whoosh,
        whooshes=whooshes,
    )
    lufs = measure_lufs(mix)
    logger.info("voice mix %.1f LUFS → gain %+.1f dB", lufs, gain_db(lufs))
    concat_and_mux(parts, mix, gain_db(lufs), final, overlays_filter(words, work, font), flashes)
    (site_dir / "description.txt").write_text(
        build_description(site, used, voice_id, mapbox_used=opening is not None),
        encoding="utf-8",
    )
    (site_dir / "comment.txt").write_text(build_comment(site), encoding="utf-8")
    logger.info("short written: %s (%.2fs)", final, probe_duration(final))
    return final
