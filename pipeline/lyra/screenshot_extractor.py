"""Extract video frame screenshots at news item timestamps using yt-dlp + ffmpeg.

Per screenshot, yt-dlp downloads a 3-second clip (DASH-aware, ≤720p) around the
timestamp through the proxy and ffmpeg extracts one native-res frame locally.
Quality decision 2026-08-01: the storyboard-sprite approach (2026-05-25,
f5d4ef0) saved ~75% Webshare bandwidth but its 320×180 source cells upscaled
to 512px looked visibly blurry — reverted to clips after the Data-API
prefilter freed up the traffic budget. Resolution decision 2026-08-17: 480p
frames (854×480) are below Google Discover's ≥1200px width requirement, so
clips now fetch ≤720p (16:9 → 1280×720) at roughly 2-3x the clip size.

URLs are written with the /data/ prefix (2026-08-17): the files live in
public/data/news/screenshots/ and nginx serves /data/news/ directly from
there — no reason to route images through /api/, which robots.txt disallows.
The old /api/news/screenshots/ mount in api/main.py stays for URLs already
cached by Google/Discord.

Backfill: ``python -m pipeline.lyra.screenshot_extractor --backfill-hires``
re-extracts existing screenshots narrower than 1200px at the new resolution.
Runs in the lyra container (yt-dlp + ffmpeg + Pillow + proxy credentials).
"""

import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("public/data/news/screenshots")
# nginx `location /data/news/` serves public/data/news/ directly (correct MIME,
# no API hop, crawlable — robots.txt disallows /api/).
SCREENSHOT_URL_PREFIX = "/data/news/screenshots"
SCREENSHOT_OFFSET = 2  # Pick frame 2 seconds after the news-item timestamp
MAX_RETRIES = 3
WEBP_QUALITY = 75
YTDLP_TIMEOUT = 60
FFMPEG_TIMEOUT = 15
# Google Discover requires images ≥1200px wide; 720p DASH video is 1280×720.
# The best[height<=720] fallback covers videos with only combined formats.
YTDLP_FORMAT = "bestvideo[height<=720]/best[height<=720]/best"
MIN_HIRES_WIDTH = 1200
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_FILENAME_RE = re.compile(r"([A-Za-z0-9_-]{11})_(\d+)\.webp$")

# yt-dlp stderr markers for videos that are permanently gone (deleted, private,
# terminated channel). Retrying those through new proxy IPs is pointless.
_GONE_MARKERS = (
    "video unavailable",
    "private video",
    "has been removed",
    "account associated with this video has been terminated",
    "no longer available",
)

ExtractStatus = Literal["ok", "gone", "failed"]


def screenshot_url_for(filename: str) -> str:
    """Public URL for a screenshot file in SCREENSHOTS_DIR."""
    return f"{SCREENSHOT_URL_PREFIX}/{filename}"


def parse_screenshot_filename(url_or_filename: str) -> tuple[str, int] | None:
    """Parse ``{video_id}_{timestamp}.webp`` (optionally with any path prefix)
    into (video_id, timestamp). Returns None if the name doesn't match."""
    match = _FILENAME_RE.search(url_or_filename.rsplit("/", 1)[-1])
    if not match:
        return None
    return match.group(1), int(match.group(2))


def is_video_gone(stderr: str) -> bool:
    """True when yt-dlp stderr says the video is permanently unavailable."""
    lowered = stderr.lower()
    return any(marker in lowered for marker in _GONE_MARKERS)


def should_replace(new_width: int, old_width: int) -> bool:
    """Replace an existing screenshot only when the new frame is strictly
    wider — a re-extracted 854px frame from a 480p-only video must never
    clobber (or pointlessly rewrite) what's already there."""
    return new_width > old_width


def get_proxy_url(settings: LyraSettings) -> str | None:
    """Proxy URL for YouTube video-clip requests.

    LYRA_PROXY_URL (home-IP exit via Tailscale) takes precedence; otherwise
    Webshare rotating residential credentials.
    """
    if settings.proxy_url:
        return settings.proxy_url
    if settings.webshare_username and settings.webshare_password:
        username = settings.webshare_username
        if not username.endswith("-rotate"):
            username = f"{username}-rotate"
        return f"http://{username}:{settings.webshare_password}@p.webshare.io:80"
    return None


def _image_width(path: Path) -> int:
    """Width in pixels of an image file; 0 when missing or unreadable
    (both mean: the hi-res backfill should extract a fresh frame)."""
    # Pillow is only in the lyra image for the backfill — keep the import out
    # of the orchestrator's normal extraction path.
    from PIL import Image

    try:
        with Image.open(path) as img:
            return img.width
    except OSError:
        return 0


def _extract_frame(
    video_id: str, timestamp: int, output_path: Path, proxy_url: str | None
) -> ExtractStatus:
    """Extract a single frame from a YouTube video at the given timestamp.

    Step 1: yt-dlp --download-sections downloads just a 3-second clip around the
    timestamp (DASH-aware, only fetches the needed segments — minimal bandwidth).
    Step 2: ffmpeg extracts one frame from the local clip (no network needed).

    Returns "ok" on success, "gone" when the video is permanently unavailable
    (deleted/private — do not retry), "failed" for everything else.
    """
    if not _VIDEO_ID_RE.match(video_id):
        logger.warning(f"Invalid video_id format: {video_id!r}")
        return "failed"
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    clip_path = output_path.with_suffix(".clip.mp4")

    # Step 1: Download a tiny clip around the timestamp via yt-dlp
    cmd_clip = [
        "yt-dlp",
        # yt-dlp needs a JS runtime to solve YouTube's player signatures.
        # Only deno is enabled by default; the image ships nodejs. Without it
        # YouTube offers SABR-only formats and every segment answers 403
        # (verified 2026-08-18: 0/10 downloads without, 1280x720 with).
        "--js-runtimes",
        "node",
        "-f",
        YTDLP_FORMAT,
        "--download-sections",
        f"*{timestamp}-{timestamp + 3}",
        "--force-keyframes-at-cuts",
        "-o",
        str(clip_path),
        "--no-warnings",
        yt_url,
    ]
    if proxy_url:
        cmd_clip.insert(1, "--proxy")
        cmd_clip.insert(2, proxy_url)
    try:
        result = subprocess.run(cmd_clip, capture_output=True, text=True, timeout=YTDLP_TIMEOUT)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if is_video_gone(stderr):
                logger.info(f"Video gone (deleted/private): {video_id}")
                return "gone"
            logger.warning(f"yt-dlp failed for {video_id}: {stderr[-200:]}")
            return "failed"
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp timed out for {video_id}@{timestamp}s")
        return "failed"

    if not clip_path.exists() or clip_path.stat().st_size == 0:
        logger.warning(f"yt-dlp produced no clip for {video_id}@{timestamp}s")
        return "failed"

    # Step 2: Extract first frame from local clip at native resolution
    cmd_ffmpeg = [
        "ffmpeg",
        "-i",
        str(clip_path),
        "-frames:v",
        "1",
        "-c:v",
        "libwebp",
        "-q:v",
        str(WEBP_QUALITY),
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
        if result.returncode != 0:
            logger.warning(f"ffmpeg failed for {video_id}@{timestamp}s: {result.stderr[-200:]}")
            return "failed"
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg timed out for {video_id}@{timestamp}s")
        return "failed"
    finally:
        clip_path.unlink(missing_ok=True)

    if output_path.exists() and output_path.stat().st_size > 0:
        return "ok"
    return "failed"


def extract_screenshots(settings: LyraSettings) -> int:
    """Extract frame screenshots for news items that don't have one yet."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    proxy_url = get_proxy_url(settings)
    extracted = 0

    with get_session() as session:
        items = (
            session.query(NewsItem)
            .join(NewsVideo)
            .filter(
                NewsItem.timestamp_seconds.isnot(None),
                NewsItem.screenshot_url.is_(None),
                NewsItem.screenshot_attempts < 9,
            )
            .limit(100)
            .all()
        )

        if not items:
            logger.info("No items need screenshots")
            return 0

        logger.info(f"Extracting screenshots for {len(items)} items")

        # Build work list, skipping items that already have a file on disk.
        # Only immutable data goes to worker threads; ORM objects stay here.
        item_by_id: dict[int, NewsItem] = {}
        to_extract: list[tuple[int, str, int, str, Path]] = []
        for item in items:
            timestamp = item.timestamp_seconds + SCREENSHOT_OFFSET
            filename = f"{item.video_id}_{timestamp}.webp"
            output_path = SCREENSHOTS_DIR / filename

            if output_path.exists() and output_path.stat().st_size > 0:
                item.screenshot_url = screenshot_url_for(filename)
                extracted += 1
                logger.info(f"  Reused existing screenshot: {filename}")
            else:
                item_by_id[item.id] = item
                to_extract.append((item.id, item.video_id, timestamp, filename, output_path))

        def _do_extract(args: tuple[int, str, int, str, Path]) -> tuple[int, str, str, bool]:
            item_id, video_id, ts, fn, out = args
            for attempt in range(MAX_RETRIES):
                status = _extract_frame(video_id, ts, out, proxy_url)
                if status == "ok":
                    return item_id, video_id, fn, True
                if status == "gone":
                    break  # deleted/private — a new proxy IP won't bring it back
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"  Retry {attempt + 2}/{MAX_RETRIES} for {fn} (new proxy IP)")
            return item_id, video_id, fn, False

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_do_extract, task): task for task in to_extract}
            for future in as_completed(futures):
                item_id, video_id, filename, success = future.result()
                if success:
                    item_by_id[item_id].screenshot_url = screenshot_url_for(filename)
                    extracted += 1
                    logger.info(f"  Extracted: {filename}")
                else:
                    item_by_id[item_id].screenshot_attempts += MAX_RETRIES
                    logger.warning(f"  Failed: {video_id}@{filename}")

    logger.info(f"Extracted {extracted} screenshots")
    return extracted


def backfill_hires(
    settings: LyraSettings,
    *,
    min_width: int = MIN_HIRES_WIDTH,
    sleep_seconds: float = 3.0,
    limit: int | None = None,
) -> dict[str, int]:
    """Re-extract existing screenshots that are narrower than ``min_width``.

    Resumable by design: the width check IS the resume marker — files already
    ≥min_width are skipped, so an interrupted run just continues where it
    stopped. Sequential with a pause between videos (YouTube rate limits).
    The old file is only replaced after the new frame is on disk AND wider
    (deleted/private videos keep their small screenshot — better than none).
    DB rows are not touched; the URL prefix migration is a separate SQL.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    proxy_url = get_proxy_url(settings)
    stats = {
        "rows": 0,
        "already_hires": 0,
        "duplicate_rows": 0,
        "bad_filename": 0,
        "upgraded": 0,
        "not_wider": 0,
        "gone": 0,
        "failed": 0,
    }

    with get_session() as session:
        rows = (
            session.query(NewsItem.id, NewsItem.screenshot_url)
            .filter(NewsItem.screenshot_url.isnot(None))
            .order_by(NewsItem.id)
            .all()
        )

    logger.info(f"Hi-res backfill: {len(rows)} rows with a screenshot_url (min width {min_width})")
    seen_filenames: set[str] = set()
    attempted = 0

    for item_id, screenshot_url in rows:
        if limit is not None and attempted >= limit:
            logger.info(f"Limit of {limit} extraction attempts reached — stopping")
            break
        stats["rows"] += 1

        parsed = parse_screenshot_filename(screenshot_url)
        if parsed is None:
            stats["bad_filename"] += 1
            logger.warning(f"Item {item_id}: unparseable screenshot_url {screenshot_url!r}")
            continue
        video_id, timestamp = parsed
        filename = f"{video_id}_{timestamp}.webp"

        if filename in seen_filenames:
            stats["duplicate_rows"] += 1
            continue
        seen_filenames.add(filename)

        output_path = SCREENSHOTS_DIR / filename
        old_width = _image_width(output_path)
        if old_width >= min_width:
            stats["already_hires"] += 1
            continue

        attempted += 1
        tmp_path = output_path.with_suffix(".new.webp")
        status: ExtractStatus = "failed"
        for attempt in range(MAX_RETRIES):
            status = _extract_frame(video_id, timestamp, tmp_path, proxy_url)
            if status != "failed":
                break
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  Retry {attempt + 2}/{MAX_RETRIES} for {filename} (new proxy IP)")

        if status == "ok":
            new_width = _image_width(tmp_path)
            if should_replace(new_width, old_width):
                os.replace(tmp_path, output_path)
                stats["upgraded"] += 1
                logger.info(f"  Upgraded {filename}: {old_width}px -> {new_width}px")
            else:
                tmp_path.unlink(missing_ok=True)
                stats["not_wider"] += 1
                logger.info(
                    f"  Source is low-res, kept old file {filename}: "
                    f"{old_width}px vs new {new_width}px"
                )
        elif status == "gone":
            tmp_path.unlink(missing_ok=True)
            stats["gone"] += 1
        else:
            tmp_path.unlink(missing_ok=True)
            stats["failed"] += 1
            logger.warning(f"  Extraction failed for {filename}, kept old file")

        if attempted % 25 == 0:
            logger.info(f"Progress after {attempted} extraction attempts: {stats}")
        time.sleep(sleep_seconds)

    logger.info(f"Hi-res backfill done: {stats}")
    return stats


def _main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Screenshot maintenance CLI (regular extraction runs in the Lyra orchestrator)"
    )
    parser.add_argument(
        "--backfill-hires",
        action="store_true",
        help=f"re-extract existing screenshots narrower than {MIN_HIRES_WIDTH}px at 720p",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after N extraction attempts (smoke test)"
    )
    parser.add_argument(
        "--sleep", type=float, default=3.0, help="pause between videos in seconds (default 3)"
    )
    args = parser.parse_args()
    if not args.backfill_hires:
        parser.error("nothing to do — pass --backfill-hires")
    backfill_hires(LyraSettings(), sleep_seconds=args.sleep, limit=args.limit)


if __name__ == "__main__":
    _main()
