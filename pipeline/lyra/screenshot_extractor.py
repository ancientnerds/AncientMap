"""Extract video frame screenshots using YouTube storyboards (sprite sheets).

YouTube hosts low-bandwidth sprite sheets at i.ytimg.com/sb/... for its seek-bar
preview feature. We use them instead of downloading actual video segments.

Per video, we call yt-dlp ONCE to get the storyboard URL pattern (~1 MB Webshare,
cached in news_videos.storyboard_meta). Per screenshot, we download ONE sprite
(~50 KB) and crop the cell containing the target timestamp.

Both yt-dlp and the sprite downloads route through Webshare proxy: i.ytimg.com/sb/
returns 403 for data-center IPs even though i.ytimg.com/vi/ (regular thumbnails)
does not.

vs the old approach (3s of 240p video ~150-200 KB per screenshot), this cuts
per-screenshot Webshare bandwidth by ~75% in steady state.
"""

import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("public/data/news/screenshots")
SPRITE_CACHE_DIR = SCREENSHOTS_DIR / ".sprite_cache"
SCREENSHOT_OFFSET = 2  # Pick frame 2 seconds after the news-item timestamp
MAX_RETRIES = 3
TARGET_WIDTH = 512  # Output WebP width; height auto-scaled (16:9 → 288px)
WEBP_QUALITY = 75
SPRITE_TIMEOUT = 30
YTDLP_TIMEOUT = 45
FFMPEG_TIMEOUT = 15
# Prefer highest-resolution storyboard (sb0 = L3, 320x180 frames); fall back to
# smaller levels if not available for short videos.
_STORYBOARD_FORMAT_PRIORITY = ["sb0", "sb1", "sb2"]
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def get_proxy_url(settings: LyraSettings) -> str | None:
    """Build a proxy URL from Webshare rotating residential credentials."""
    if settings.webshare_username and settings.webshare_password:
        username = settings.webshare_username
        if not username.endswith("-rotate"):
            username = f"{username}-rotate"
        return f"http://{username}:{settings.webshare_password}@p.webshare.io:80"
    return None


def _fetch_storyboard_meta(video_id: str, proxy_url: str | None) -> dict:
    """Fetch storyboard URL pattern + grid info via yt-dlp.

    Returns a dict with url_template, fragment_duration, frame_width/height,
    rows, cols, total_fragments, format_id — or empty {} if no storyboard
    is available (very short videos sometimes have none).
    """
    if not _VIDEO_ID_RE.match(video_id):
        logger.warning(f"Invalid video_id format: {video_id!r}")
        return {}
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp", "-J", "--no-warnings", yt_url]
    if proxy_url:
        cmd.insert(1, "--proxy")
        cmd.insert(2, proxy_url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT)
        if result.returncode != 0:
            logger.warning(f"yt-dlp -J failed for {video_id}: {result.stderr.strip()[-200:]}")
            return {}
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.warning(f"yt-dlp -J error for {video_id}: {e}")
        return {}

    formats = {f.get("format_id"): f for f in data.get("formats", [])}
    chosen = next(
        (formats[fid] for fid in _STORYBOARD_FORMAT_PRIORITY if fid in formats), None
    )
    if not chosen or not chosen.get("fragments"):
        return {}

    fragments = chosen["fragments"]
    return {
        "url_template": chosen.get("url", ""),
        "fragment_duration": fragments[0]["duration"],
        "frame_width": chosen.get("width", 0),
        "frame_height": chosen.get("height", 0),
        "rows": chosen.get("rows", 1),
        "cols": chosen.get("columns", 1),
        "total_fragments": len(fragments),
        "format_id": chosen.get("format_id"),
    }


def _ensure_storyboard_meta(video: NewsVideo, proxy_url: str | None) -> dict | None:
    """Return cached storyboard meta, or fetch+cache it. None = unavailable."""
    if video.storyboard_meta is None:
        logger.info(f"  Fetching storyboard meta for {video.id}")
        video.storyboard_meta = _fetch_storyboard_meta(video.id, proxy_url)
    return video.storyboard_meta or None


def _download_sprite(
    url: str, sprite_path: Path, proxy_url: str | None
) -> bool:
    """Download sprite to a temp path then atomically rename, so parallel workers
    don't read a half-written file. Idempotent: returns True if already on disk.
    """
    if sprite_path.exists() and sprite_path.stat().st_size > 0:
        return True
    tmp_path = sprite_path.with_suffix(sprite_path.suffix + ".tmp")
    try:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        r = requests.get(url, proxies=proxies, timeout=SPRITE_TIMEOUT)
        r.raise_for_status()
        tmp_path.write_bytes(r.content)
        tmp_path.replace(sprite_path)
        return True
    except requests.RequestException as e:
        logger.warning(f"  Sprite download failed {sprite_path.name}: {e}")
        tmp_path.unlink(missing_ok=True)
        return False


def _extract_frame(
    video_id: str,
    timestamp: int,
    output_path: Path,
    meta: dict,
    proxy_url: str | None,
) -> bool:
    """Download the sprite that contains this timestamp and crop the right cell."""
    frames_per_fragment = meta["rows"] * meta["cols"]
    fragment_dur = meta["fragment_duration"]
    fragment_idx = int(timestamp / fragment_dur)
    if fragment_idx >= meta["total_fragments"]:
        logger.warning(f"  {video_id}@{timestamp}s: fragment {fragment_idx} out of range")
        return False

    time_in_fragment = timestamp - fragment_idx * fragment_dur
    cell_idx = min(
        int(time_in_fragment * frames_per_fragment / fragment_dur),
        frames_per_fragment - 1,
    )
    row, col = divmod(cell_idx, meta["cols"])
    fw, fh = meta["frame_width"], meta["frame_height"]

    # yt-dlp leaves a literal "$M" placeholder in the storyboard URL template
    sprite_url = meta["url_template"].replace("$M", str(fragment_idx))
    sprite_path = SPRITE_CACHE_DIR / f"{video_id}_{meta['format_id']}_M{fragment_idx}.jpg"

    if not _download_sprite(sprite_url, sprite_path, proxy_url):
        return False

    left, top = col * fw, row * fh
    cmd = [
        "ffmpeg",
        "-i", str(sprite_path),
        "-vf", f"crop={fw}:{fh}:{left}:{top},scale={TARGET_WIDTH}:-2:flags=lanczos",
        "-c:v", "libwebp",
        "-q:v", str(WEBP_QUALITY),
        "-y", str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
        if result.returncode != 0:
            logger.warning(f"  ffmpeg failed {video_id}@{timestamp}s: {result.stderr[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning(f"  ffmpeg timed out {video_id}@{timestamp}s")
        return False

    return output_path.exists() and output_path.stat().st_size > 0


def extract_screenshots(settings: LyraSettings) -> int:
    """Extract frame screenshots for news items that don't have one yet."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    SPRITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
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

        # Fetch storyboard metadata sequentially in the main thread (SQLAlchemy
        # writes happen here; once per unique video).
        video_meta: dict[str, dict | None] = {}
        for item in items:
            vid = item.video_id
            if vid not in video_meta:
                video_meta[vid] = _ensure_storyboard_meta(item.video, proxy_url)
        session.flush()

        # Build work list: skip items already on disk and items with no storyboard.
        item_by_id: dict[int, NewsItem] = {}
        to_extract: list[tuple[int, str, int, str, Path, dict]] = []
        for item in items:
            meta = video_meta.get(item.video_id)
            if meta is None:
                item.screenshot_attempts += MAX_RETRIES
                logger.info(f"  No storyboard for {item.video_id}, marking item {item.id} failed")
                continue

            timestamp = item.timestamp_seconds + SCREENSHOT_OFFSET
            filename = f"{item.video_id}_{timestamp}.webp"
            output_path = SCREENSHOTS_DIR / filename

            if output_path.exists() and output_path.stat().st_size > 0:
                item.screenshot_url = f"/api/news/screenshots/{filename}"
                extracted += 1
                logger.info(f"  Reused existing screenshot: {filename}")
            else:
                item_by_id[item.id] = item
                to_extract.append(
                    (item.id, item.video_id, timestamp, filename, output_path, meta)
                )

        # Parallel extraction. The on-disk sprite cache deduplicates downloads
        # when multiple items share a fragment (~89s window at L3).
        def _do(args: tuple[int, str, int, str, Path, dict]) -> tuple[int, str, str, bool]:
            item_id, vid, ts, fn, out, meta = args
            for attempt in range(MAX_RETRIES):
                if _extract_frame(vid, ts, out, meta, proxy_url):
                    return item_id, vid, fn, True
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"  Retry {attempt + 2}/{MAX_RETRIES} for {fn}")
            return item_id, vid, fn, False

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_do, task): task for task in to_extract}
            for future in as_completed(futures):
                item_id, vid, filename, success = future.result()
                if success:
                    item_by_id[item_id].screenshot_url = f"/api/news/screenshots/{filename}"
                    extracted += 1
                    logger.info(f"  Extracted: {filename}")
                else:
                    item_by_id[item_id].screenshot_attempts += MAX_RETRIES
                    logger.warning(f"  Failed: {vid}@{filename}")

        # Wipe sprite cache between runs; signatures expire and disk is cheap to refill.
        for sprite in SPRITE_CACHE_DIR.glob("*.jpg"):
            sprite.unlink(missing_ok=True)

    logger.info(f"Extracted {extracted} screenshots")
    return extracted
