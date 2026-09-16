"""Thin ffmpeg/ffprobe wrappers shared by the video modules."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")


def probe_duration(path: Path) -> float:
    """Return the container duration in seconds (ffprobe, format section)."""
    out = subprocess.run(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(out)


def run_ffmpeg(args: list[str], out_path: Path) -> Path:
    """Run ffmpeg with `args`, overwriting `out_path`. Raises on non-zero exit."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-y", *args, str(out_path)]
    logger.debug("ffmpeg: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def ff_path(path: Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter option.

    Filter options are colon-separated, so the drive colon on Windows must be
    escaped; backslashes are replaced by forward slashes, which ffmpeg accepts
    on every platform.
    """
    return str(path).replace("\\", "/").replace(":", "\\:")
