"""Encoding captured frames into clips the renderer can decode.

Every clip is HEVC from hevc_nvenc on GPU 0 (spec 4.11: H.264/HEVC encodes run on
NVENC, never in software), BT.709 limited range, constant 60 fps, a keyframe every
second, no B-frames, `hvc1` tag, faststart. Not H.264: @remotion/media decodes a clip
with Chrome's VideoDecoder, and h264_nvenc writes no VUI bitstream_restriction, so
Mediabunny infers num_reorder_frames = MaxDpbFrames (up to 16, mediabunny
codec-data.js) and the decoder holds its frames back; every renderMedia over an
h264_nvenc clip timed out ("Timeout while extracting frame at time 0.1sec"), while
libx264 (which writes max_num_reorder_frames) and hevc_nvenc clips rendered
(measured 2026-09-26, Remotion 4.0.529, 1080p and 2880x1620). An HEVC SPS always
carries sps_max_num_reorder_pics (0 here). The capture frames are sRGB JPEGs (BT.601
full range once decoded, with Chrome's sRGB ICC profile attached): CLIP_FILTER drops
the profile and converts them to the BT.709 limited range the renderer's decoder
assumes, and the stream is tagged so.

Two sources:
* the platform take's CDP screencast: frames arrive at a variable rate with their own
  timestamps (frames_to_cfr_mp4 holds each frame until the next one);
* the recorder's exact frames (globe and Mapbox takes): one JPEG per output frame,
  f000000.jpg, f000001.jpg, ... (sequence_to_mp4).
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.studio.capture.manifest import CaptureError
from pipeline.video.media import probe_duration, probe_frames, run_ffmpeg

CLIP_FILTER = (
    "sidedata=mode=delete:type=ICC_PROFILE,"
    "scale=in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,"
    "format=yuv420p"
)
CLIP_ENCODE = [
    "-c:v",
    "hevc_nvenc",
    "-gpu",
    "0",
    "-preset",
    "p5",
    "-tune",
    "hq",
    "-rc",
    "vbr",
    "-cq",
    "16",
    "-b:v",
    "0",
    "-bf",
    "0",
    "-g",
    "60",
    "-pix_fmt",
    "yuv420p",
    "-tag:v",
    "hvc1",
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
    "-movflags",
    "+faststart",
    "-an",
]
FRAME_RE = re.compile(r"^f(\d{6})\.jpg$")


def concat_script(timestamps: list[float], end_ts: float, fps: int) -> str:
    """ffconcat list over the frames f<i:06>.jpg (i = arrival order, timestamps[i] its time).

    CDP frame timestamps are not strictly monotonic (two frames arrived 4.7 ms out of
    order in a real take, 2026-09-26), so the frames are played in timestamp order and a
    frame with the same timestamp as its predecessor is dropped. Each frame lasts until
    the next one; the last until `end_ts` (at least one output frame). The concat
    demuxer ignores the duration of the final entry, so the last file is listed twice.
    """
    if not timestamps:
        raise CaptureError("the screencast delivered no frames")
    ordered: list[tuple[float, int]] = []
    for ts, i in sorted((ts, i) for i, ts in enumerate(timestamps)):
        if not ordered or ts > ordered[-1][0]:
            ordered.append((ts, i))
    if end_ts < ordered[-1][0]:
        raise CaptureError(f"take end {end_ts} lies before the last frame {ordered[-1][0]}")
    lines = ["ffconcat version 1.0"]
    for k, (ts, i) in enumerate(ordered):
        nxt = ordered[k + 1][0] if k + 1 < len(ordered) else max(end_ts, ts + 1 / fps)
        lines.append(f"file 'f{i:06d}.jpg'")
        lines.append(f"duration {nxt - ts:.6f}")
    lines.append(f"file 'f{ordered[-1][1]:06d}.jpg'")
    return "\n".join(lines) + "\n"


def take_seconds(timestamps: list[float], end_ts: float, fps: int) -> float:
    """Length of the take from the earliest frame to its end (at least one output frame)."""
    return max(end_ts - min(timestamps), 1 / fps)


def frames_to_cfr_mp4(
    frames_dir: Path, timestamps: list[float], end_ts: float, out: Path, fps: int
) -> float:
    """Variable-rate screencast frames -> constant-rate clip; returns its duration in seconds.

    `-t` cuts the output at the take's end: the repeated last concat entry would
    otherwise add its duration a second time.
    """
    script = frames_dir / "frames.ffconcat"
    script.write_text(concat_script(timestamps, end_ts, fps), encoding="utf-8")
    seconds = take_seconds(timestamps, end_ts, fps)
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(script),
            "-vf",
            f"fps={fps},{CLIP_FILTER}",
            "-t",
            f"{seconds:.6f}",
            *CLIP_ENCODE,
        ],
        out,
    )
    return probe_duration(out)


def frame_size(frames_dir: Path) -> tuple[int, int]:
    """Pixel size of the first frame f000000.jpg of a take. A platform take's screencast is
    capped at the display's pixel size (2880x1620 on the workstation, measured 2026-09-26)
    and a recorder take must hold its scene's size, so it is read, never assumed."""
    from PIL import Image

    with Image.open(frames_dir / "f000000.jpg") as first:
        return first.size


def sequence_length(frames_dir: Path) -> int:
    """Number of frames f000000.jpg .. f<n-1>.jpg; a gap or a stray file is an error."""
    names = sorted(p.name for p in frames_dir.iterdir())
    indices = [int(m.group(1)) for m in map(FRAME_RE.match, names) if m]
    if len(indices) != len(names):
        raise CaptureError(f"{frames_dir} holds files that are not frames")
    if indices != list(range(len(indices))):
        raise CaptureError(f"{frames_dir}: the frame sequence has gaps")
    return len(indices)


def sequence_to_mp4(frames_dir: Path, fps: int, out: Path) -> int:
    """Exact frames (one JPEG per output frame) -> constant-rate clip; returns the frame count."""
    count = sequence_length(frames_dir)
    if count == 0:
        raise CaptureError(f"{frames_dir} holds no frames")
    run_ffmpeg(
        [
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "f%06d.jpg"),
            "-vf",
            CLIP_FILTER,
            *CLIP_ENCODE,
        ],
        out,
    )
    encoded = probe_frames(out)
    if encoded != count:
        raise CaptureError(f"{out}: {encoded} frames encoded from {count}")
    return count
