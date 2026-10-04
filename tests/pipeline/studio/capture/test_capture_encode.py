"""Captured frames -> constant-rate HEVC clips on NVENC (pipeline/studio/capture/encode.py)."""

import subprocess

import pytest

from pipeline.studio.capture.encode import (
    CLIP_FILTER,
    CONCAT_CLOCK_HZ,
    clip_encode,
    concat_script,
    frame_size,
    frames_to_cfr_mp4,
    sequence_length,
    sequence_to_mp4,
    take_seconds,
)
from pipeline.studio.capture.gpu import nvenc_problem
from pipeline.studio.capture.manifest import CaptureError
from pipeline.video.media import FFMPEG_BIN, FFPROBE_BIN, probe_frames

NVENC_PROBLEM = nvenc_problem()
needs_nvenc = pytest.mark.skipif(NVENC_PROBLEM is not None, reason=str(NVENC_PROBLEM))


def test_concat_script_gives_each_frame_its_real_duration():
    script = concat_script([10.0, 10.1, 10.25], end_ts=10.5, fps=60)
    # an image file's own clock ticks in 1/25 s: each file gets a finer one
    clock = f"option framerate {CONCAT_CLOCK_HZ}"
    assert script.splitlines() == [
        "ffconcat version 1.0",
        "file 'f000000.jpg'",
        clock,
        "duration 0.100000",
        "file 'f000001.jpg'",
        clock,
        "duration 0.150000",
        "file 'f000002.jpg'",
        clock,
        "duration 0.250000",
        "file 'f000002.jpg'",
        clock,
    ]


def test_last_frame_lasts_at_least_one_output_frame():
    assert "duration 0.016667" in concat_script([5.0], end_ts=5.0, fps=60)


def test_frames_play_in_timestamp_order_and_duplicates_are_dropped():
    script = concat_script([10.0, 10.2, 10.1, 10.1], end_ts=10.3, fps=60)
    assert [line for line in script.splitlines()[1:] if not line.startswith("option")] == [
        "file 'f000000.jpg'",
        "duration 0.100000",
        "file 'f000002.jpg'",
        "duration 0.100000",
        "file 'f000001.jpg'",
        "duration 0.100000",
        "file 'f000001.jpg'",
    ]


@pytest.mark.parametrize(
    ("timestamps", "end", "message"),
    [([], 1.0, "no frames"), ([1.0, 2.0], 1.5, "before the last frame")],
)
def test_concat_script_rejects_broken_takes(timestamps, end, message):
    with pytest.raises(CaptureError, match=message):
        concat_script(timestamps, end, 60)


def test_take_seconds_runs_from_the_first_frame_to_the_end():
    assert take_seconds([10.0, 10.5], 12.0, 60) == 2.0
    assert take_seconds([10.2, 10.0], 12.0, 60) == 2.0
    assert take_seconds([10.0], 10.0, 60) == pytest.approx(1 / 60)


@pytest.mark.parametrize(
    ("timestamps", "end"),
    [([10.0, 10.5], 10.5), ([10.0, 10.25, 10.5], 10.5), ([10.0], 10.0), ([10.0, 10.5], 12.0)],
)
def test_the_cut_keeps_the_last_frame_the_concat_list_gives(timestamps, end):
    # Review of Task 25: a take that ends on its last frame's timestamp was cut there, so
    # `-t` dropped that frame although the concat list gives it one output frame
    script = concat_script(timestamps, end, 60)
    listed = sum(
        float(line.split()[1]) for line in script.splitlines() if line.startswith("duration")
    )
    assert take_seconds(timestamps, end, 60) == pytest.approx(listed, abs=1e-6)


def test_clips_are_hevc_on_nvenc_gpu_0_bt709_without_b_frames():
    encode = clip_encode(60)

    def value(flag):
        return encode[encode.index(flag) + 1]

    assert (value("-c:v"), value("-gpu"), value("-bf"), value("-tag:v")) == (
        "hevc_nvenc",
        "0",
        "0",
        "hvc1",
    )
    assert (value("-colorspace"), value("-color_range")) == ("bt709", "tv")
    assert not any(arg in ("libx264", "libx265", "h264_nvenc") for arg in encode)
    # a keyframe every second at the clip's own rate
    assert value("-g") == "60"
    assert clip_encode(30)[clip_encode(30).index("-g") + 1] == "30"
    assert "out_color_matrix=bt709" in CLIP_FILTER and "out_range=tv" in CLIP_FILTER
    assert CLIP_FILTER.startswith("sidedata=mode=delete:type=ICC_PROFILE,")


def test_frame_size_is_read_from_the_first_frame(tmp_path):
    from PIL import Image

    # Chrome caps the screencast at the display's pixel size: read, never assumed
    Image.new("RGB", (2880, 1620), "black").save(tmp_path / "f000000.jpg")
    assert frame_size(tmp_path) == (2880, 1620)


def test_sequence_length_refuses_gaps_and_strays(tmp_path):
    for i in (0, 1, 2):
        (tmp_path / f"f{i:06d}.jpg").write_bytes(b"x")
    assert sequence_length(tmp_path) == 3
    (tmp_path / "f000004.jpg").write_bytes(b"x")
    with pytest.raises(CaptureError, match="has gaps"):
        sequence_length(tmp_path)
    (tmp_path / "f000004.jpg").unlink()
    (tmp_path / "points.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CaptureError, match="not frames"):
        sequence_length(tmp_path)


def _frames(directory, count, icc=False):
    from PIL import Image, ImageCms

    # Chrome's canvas JPEGs carry an sRGB ICC profile, which ffmpeg keeps as stream side data.
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes() if icc else None
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i in range(count):
        # NVENC's smallest HEVC frame is larger than 64x36; 256x144 is safely above it.
        image = Image.new("RGB", (256, 144), colours[i % 3])
        if profile is None:
            image.save(directory / f"f{i:06d}.jpg")
        else:
            image.save(directory / f"f{i:06d}.jpg", icc_profile=profile)


@needs_nvenc
def test_screencast_frames_become_a_constant_60fps_clip(tmp_path):
    _frames(tmp_path, 3)
    out = tmp_path / "clip.mp4"
    duration = frames_to_cfr_mp4(tmp_path, [0.0, 0.25, 0.5], end_ts=1.0, out=out, fps=60)
    assert duration == pytest.approx(1.0, abs=0.02)
    assert probe_frames(out) == 60


def _rgb_frames(clip, width=256, height=144):
    """The clip's frames as RGB bytes, one entry per frame."""
    rgb = subprocess.run(
        [
            FFMPEG_BIN,
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    size = width * height * 3
    return [rgb[i : i + size] for i in range(0, len(rgb), size)]


def _colour_at_centre(frame, width=256, height=144):
    """'red', 'green' or 'blue': the primary at the frame's centre."""
    centre = ((height // 2) * width + width // 2) * 3
    r, g, b = frame[centre : centre + 3]
    return ["red", "green", "blue"][max(range(3), key=lambda k: (r, g, b)[k])]


@needs_nvenc
def test_every_frame_of_a_60fps_screencast_shows_once_in_the_clip(tmp_path):
    """The concat demuxer read each JPEG on its own 1/25 s clock, so frames 16.7 ms apart
    collapsed onto the same tick and a 60 fps screencast played at about 25 (measured
    2026-09-30: 12 of 30 frames reached the clip)."""
    from PIL import Image

    for i in range(30):
        Image.new("RGB", (256, 144), (i * 8,) * 3).save(tmp_path / f"f{i:06d}.jpg")
    out = tmp_path / "clip.mp4"
    frames_to_cfr_mp4(tmp_path, [100.0 + i / 60 for i in range(30)], 100.0 + 29 / 60, out, 60)
    centre = (72 * 256 + 128) * 3
    levels = [f[centre] for f in _rgb_frames(out)]
    # 30 frames, each brighter than the one before: every screencast frame once, in order
    assert len(levels) == 30
    assert all(b - a >= 4 for a, b in zip(levels, levels[1:], strict=False)), levels


@needs_nvenc
def test_screencast_frames_with_chromes_icc_profile_are_each_held_until_the_next(tmp_path):
    # Chrome's screencast JPEGs carry its sRGB profile; each frame shows until the next
    # one's timestamp, the last until the take's end (here its own timestamp: one frame)
    _frames(tmp_path, 3, icc=True)
    out = tmp_path / "clip.mp4"
    frames_to_cfr_mp4(tmp_path, [0.0, 0.25, 0.5], end_ts=0.5, out=out, fps=60)
    colours = [_colour_at_centre(f) for f in _rgb_frames(out)]
    assert colours == ["red"] * 15 + ["green"] * 15 + ["blue"]


@needs_nvenc
def test_an_exact_sequence_keeps_every_frame_even_with_an_icc_profile(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    _frames(frames, 90, icc=True)
    assert sequence_to_mp4(frames, 60, tmp_path / "take.mp4") == 90
    assert probe_frames(tmp_path / "take.mp4") == 90
    stream = subprocess.run(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,codec_tag_string,color_space,color_range",
            "-of",
            "csv=p=0",
            str(tmp_path / "take.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert stream == "hevc,hvc1,tv,bt709"


@needs_nvenc
def test_colours_survive_the_bt709_conversion(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    _frames(frames, 3)
    sequence_to_mp4(frames, 60, tmp_path / "take.mp4")
    rgb = subprocess.run(
        [
            FFMPEG_BIN,
            "-v",
            "error",
            "-i",
            str(tmp_path / "take.mp4"),
            "-vf",
            "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    frame = 256 * 144 * 3
    centre = (72 * 256 + 128) * 3
    red, green, blue = (rgb[i * frame + centre : i * frame + centre + 3] for i in range(3))
    assert red[0] > 240 and red[1] < 12 and red[2] < 12
    assert green[1] > 240 and green[0] < 12 and green[2] < 12
    assert blue[2] > 240 and blue[0] < 12 and blue[1] < 12
