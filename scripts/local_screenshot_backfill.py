# SPDX-License-Identifier: AGPL-3.0-only
"""Re-extract story screenshots at 1280px from a home connection, then upload.

The VPS pulls YouTube through Webshare residential proxies, which costs
real bandwidth (~380 KB per clip, ~1.3 GB for the whole backlog). A home
connection has none of that cost and no bot-check friction, so this script
does the extraction locally and ships only the finished 85 KB WebP frames.

The container path stays authoritative: filenames encode video id and
timestamp exactly as `screenshot_extractor.parse_screenshot_filename`
expects, and frames are written with the same ffmpeg settings.

Resumable: candidates already ≥1200px on the VPS are skipped by the
listing step, and locally finished frames are skipped on restart.

Usage:
    python scripts/local_screenshot_backfill.py --list      # refresh candidates
    python scripts/local_screenshot_backfill.py             # extract + upload
    python scripts/local_screenshot_backfill.py --limit 20  # trial slice
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

SSH_HOST = "ancientnerds"
REMOTE_DIR = "/var/www/ancientnerds/public/data/news/screenshots"
WORK_DIR = Path.home() / ".an_screenshot_backfill"
CANDIDATES = WORK_DIR / "candidates.txt"
FRAMES = WORK_DIR / "frames"

# Mirrors screenshot_extractor: 720p DASH is 1280x720, Discover needs ≥1200.
YTDLP_FORMAT = "bestvideo[height<=720]/best[height<=720]/best"
MIN_WIDTH = 1200
WEBP_QUALITY = 75
UPLOAD_BATCH = 25
FILENAME_RE = re.compile(r"^([A-Za-z0-9_-]{11})_(\d+)\.webp$")

LIST_REMOTE = """
from pathlib import Path
from PIL import Image
for f in sorted(Path('public/data/news/screenshots').glob('*.webp')):
    try:
        with Image.open(f) as im:
            if im.width < 1200:
                print(f.name)
    except OSError:
        pass
"""


def refresh_candidates() -> list[str]:
    """Ask the VPS which screenshots are still below the Discover threshold."""
    result = subprocess.run(
        ["ssh", SSH_HOST, f"docker exec -i ancient_nerds_lyra python - <<'PY'\n{LIST_REMOTE}\nPY"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        sys.exit(f"listing failed: {result.stderr[-300:]}")
    names = [n.strip() for n in result.stdout.splitlines() if FILENAME_RE.match(n.strip())]
    CANDIDATES.write_text("\n".join(names), encoding="utf-8")
    return names


def extract(video_id: str, timestamp: int, out: Path) -> str:
    """One 1280px frame, or a reason it could not be produced."""
    clip = out.with_suffix(".clip.mp4")
    clip.unlink(missing_ok=True)
    dl = subprocess.run(
        [
            "yt-dlp",
            "--js-runtimes",
            "node",
            "-f",
            YTDLP_FORMAT,
            "--download-sections",
            f"*{timestamp}-{timestamp + 3}",
            "--force-keyframes-at-cuts",
            "-o",
            str(clip),
            "--no-warnings",
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if dl.returncode != 0 or not clip.exists():
        err = (dl.stderr or "").lower()
        gone = any(m in err for m in ("private video", "video unavailable", "removed by the user"))
        return "gone" if gone else "failed"
    try:
        ff = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(clip),
                "-frames:v",
                "1",
                "-c:v",
                "libwebp",
                "-q:v",
                str(WEBP_QUALITY),
                "-y",
                str(out),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if ff.returncode != 0 or not out.exists():
            return "failed"
    finally:
        clip.unlink(missing_ok=True)
    with Image.open(out) as im:
        if im.width < MIN_WIDTH:
            # 360p-only source: the existing 854px frame is still the better one.
            out.unlink(missing_ok=True)
            return "not_wider"
    return "ok"


def upload(paths: list[Path]) -> None:
    if not paths:
        return
    subprocess.run(
        ["scp", "-q", *[str(p) for p in paths], f"{SSH_HOST}:{REMOTE_DIR}/"],
        check=True,
        timeout=600,
    )
    for p in paths:
        p.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="only refresh the candidate list")
    parser.add_argument("--cached", action="store_true", help="reuse the stored list (tests)")
    parser.add_argument("--limit", type=int, default=None, help="stop after N extractions")
    args = parser.parse_args()

    WORK_DIR.mkdir(exist_ok=True)
    FRAMES.mkdir(exist_ok=True)

    # Refreshing by default IS the resume mechanism: whatever already landed
    # on the VPS at ≥1200px drops out of the list.
    if args.cached and CANDIDATES.exists():
        names = [n for n in CANDIDATES.read_text(encoding="utf-8").splitlines() if n.strip()]
        print(f"{len(names)} candidates from {CANDIDATES}")
    else:
        names = refresh_candidates()
        print(f"{len(names)} candidates below {MIN_WIDTH}px")
        if args.list:
            return

    stats = {"ok": 0, "failed": 0, "gone": 0, "not_wider": 0}
    pending: list[Path] = []

    for i, name in enumerate(names):
        if args.limit is not None and sum(stats.values()) >= args.limit:
            break
        m = FILENAME_RE.match(name)
        if not m:
            continue
        video_id, timestamp = m.group(1), int(m.group(2))
        out = FRAMES / name
        result = extract(video_id, timestamp, out)
        stats[result] += 1
        if result == "ok":
            pending.append(out)
        if len(pending) >= UPLOAD_BATCH:
            upload(pending)
            pending = []
        if i % 25 == 0:
            print(f"  {i}/{len(names)} {stats}", flush=True)

    upload(pending)
    print("=" * 60)
    print(f"done: {stats}")


if __name__ == "__main__":
    main()
