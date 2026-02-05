"""Extract video frame screenshots at news item timestamps using yt-dlp + ffmpeg."""

import logging
import subprocess
from pathlib import Path

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("public/data/news/screenshots")
SCREENSHOT_OFFSET = 2  # Grab frame 2 seconds after the timestamp


def _get_proxy_url(settings: LyraSettings) -> str | None:
    """Build yt-dlp proxy URL from Webshare rotating residential credentials."""
    if settings.webshare_username and settings.webshare_password:
        username = settings.webshare_username
        if not username.endswith("-rotate"):
            username = f"{username}-rotate"
        return f"http://{username}:{settings.webshare_password}@p.webshare.io:80"
    return None


def _extract_frame(video_id: str, timestamp: int, output_path: Path, proxy_url: str | None) -> bool:
    """Extract a single frame from a YouTube video at the given timestamp.

    Step 1: yt-dlp --download-sections downloads just a 3-second clip around the
    timestamp (DASH-aware, only fetches the needed segments — minimal bandwidth).
    Step 2: ffmpeg extracts one frame from the local clip (no network needed).
    """
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    clip_path = output_path.with_suffix(".clip.mp4")

    # Step 1: Download a tiny clip around the timestamp via yt-dlp
    cmd_clip = [
        "yt-dlp",
        "-f", "bestvideo[height<=480]/worst",
        "--download-sections", f"*{timestamp}-{timestamp + 3}",
        "--force-keyframes-at-cuts",
        "-o", str(clip_path),
        "--no-warnings",
        yt_url,
    ]
    if proxy_url:
        cmd_clip.insert(1, "--proxy")
        cmd_clip.insert(2, proxy_url)

    try:
        result = subprocess.run(cmd_clip, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(f"yt-dlp failed for {video_id}: {result.stderr.strip()[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp timed out for {video_id}@{timestamp}s")
        return False

    if not clip_path.exists() or clip_path.stat().st_size == 0:
        logger.warning(f"yt-dlp produced no clip for {video_id}@{timestamp}s")
        return False

    # Step 2: Extract first frame from local clip (no network, instant)
    cmd_ffmpeg = [
        "ffmpeg",
        "-i", str(clip_path),
        "-frames:v", "1",
        "-c:v", "libwebp",
        "-q:v", "75",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            logger.warning(f"ffmpeg failed for {video_id}@{timestamp}s: {result.stderr[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg timed out for {video_id}@{timestamp}s")
        return False
    finally:
        clip_path.unlink(missing_ok=True)

    return output_path.exists() and output_path.stat().st_size > 0


def extract_screenshots(settings: LyraSettings) -> int:
    """Extract frame screenshots for all news items that don't have one yet.

    Returns number of screenshots extracted.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    proxy_url = _get_proxy_url(settings)
    extracted = 0

    with get_session() as session:
        # Find items with a timestamp but no screenshot
        items = (
            session.query(NewsItem)
            .join(NewsVideo)
            .filter(
                NewsItem.timestamp_seconds.isnot(None),
                NewsItem.screenshot_url.is_(None),
            )
            .all()
        )

        if not items:
            logger.info("No items need screenshots")
            return 0

        logger.info(f"Extracting screenshots for {len(items)} items")

        # Group by video to avoid re-fetching the same video URL
        for item in items:
            timestamp = item.timestamp_seconds + SCREENSHOT_OFFSET
            filename = f"{item.video_id}_{timestamp}.webp"
            output_path = SCREENSHOTS_DIR / filename

            # Skip if file already exists from a previous partial run
            if output_path.exists() and output_path.stat().st_size > 0:
                item.screenshot_url = f"/api/news/screenshots/{filename}"
                extracted += 1
                logger.info(f"  Reused existing screenshot: {filename}")
                continue

            success = _extract_frame(item.video_id, timestamp, output_path, proxy_url)
            if success:
                item.screenshot_url = f"/api/news/screenshots/{filename}"
                extracted += 1
                logger.info(f"  Extracted: {filename}")
            else:
                logger.warning(f"  Failed: {item.video_id}@{timestamp}s")

    logger.info(f"Extracted {extracted} screenshots")
    return extracted
