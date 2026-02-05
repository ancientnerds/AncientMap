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

    Uses yt-dlp to get the direct stream URL (through proxy), then ffmpeg to grab
    one frame (also through proxy). Both must use the same proxy because YouTube's
    stream URLs are IP-locked.
    """
    yt_url = f"https://www.youtube.com/watch?v={video_id}"

    # Step 1: Get direct video stream URL via yt-dlp
    cmd_url = [
        "yt-dlp",
        "-f", "worst[ext=mp4]/worst",
        "-g",
        yt_url,
    ]
    if proxy_url:
        cmd_url.insert(1, "--proxy")
        cmd_url.insert(2, proxy_url)

    try:
        result = subprocess.run(cmd_url, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"yt-dlp failed for {video_id}: {result.stderr.strip()[-200:]}")
            return False
        direct_url = result.stdout.strip().split("\n")[0]
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp timed out for {video_id}")
        return False

    # Step 2: Extract frame with ffmpeg (use same proxy so IP matches the signed URL)
    cmd_ffmpeg = [
        "ffmpeg",
        "-ss", str(timestamp),
    ]
    if proxy_url:
        cmd_ffmpeg += ["-http_proxy", proxy_url]
    cmd_ffmpeg += [
        "-i", direct_url,
        "-frames:v", "1",
        "-q:v", "5",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"ffmpeg failed for {video_id}@{timestamp}s: {result.stderr[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg timed out for {video_id}@{timestamp}s")
        return False

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
            filename = f"{item.video_id}_{timestamp}.jpg"
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
