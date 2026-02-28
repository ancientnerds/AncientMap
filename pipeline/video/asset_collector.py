"""Phase 3: Asset Collector — downloads YouTube clips, screenshots, and WikiImages.

Uses yt-dlp + FFmpeg for YouTube clips, HTTP for screenshots and Wikimedia images.
"""

import logging
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Max clip duration in seconds (fair use)
MAX_CLIP_DURATION = 15


def _download_clip(video_id: str, start: int, duration: int, output_path: Path) -> bool:
    """Download a segment of a YouTube video using yt-dlp.

    Args:
        video_id: YouTube video ID.
        start: Start timestamp in seconds.
        duration: Clip duration in seconds (capped at MAX_CLIP_DURATION).
        output_path: Where to save the clip.

    Returns:
        True if download succeeded.
    """
    duration = min(duration, MAX_CLIP_DURATION)
    end = start + duration
    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--download-sections",
        f"*{start}-{end}",
        "--merge-output-format",
        "mp4",
        "-o",
        str(output_path),
        "--no-playlist",
        "--quiet",
        url,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        logger.info(f"Downloaded clip: {video_id} [{start}s-{end}s]")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"yt-dlp failed for {video_id}: {e.stderr.decode()[:200]}")
        return False
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp timed out for {video_id}")
        return False


def _download_image(url: str, output_path: Path) -> bool:
    """Download an image from a URL."""
    if not url:
        return False
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            return True
    except httpx.HTTPError as e:
        logger.warning(f"Image download failed for {url}: {e}")
        return False


def collect_assets(script: dict, output_dir: Path, api_base_url: str = "") -> dict:
    """Collect all media assets referenced in the video script.

    Args:
        script: Video script JSON from script_adapter.
        output_dir: Base directory for downloaded assets.
        api_base_url: Base URL for screenshot downloads (e.g. "https://ancientnerds.com").

    Returns:
        Asset manifest dict with paths to all downloaded files.
    """
    clips_dir = output_dir / "clips"
    images_dir = output_dir / "images"
    gallery_dir = output_dir / "site_gallery"
    clips_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    gallery_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "clips": {},
        "screenshots": {},
        "wiki_images": {},
    }

    seen_clips: set[str] = set()

    for i, segment in enumerate(script.get("segments", [])):
        visuals = segment.get("visuals", {})
        if not visuals:
            continue

        # Download YouTube clip
        clip_info = visuals.get("clip", {})
        video_id = clip_info.get("video_id")
        if video_id:
            start = clip_info.get("start", 0) or 0
            duration = clip_info.get("duration", MAX_CLIP_DURATION)
            clip_key = f"{video_id}_{start}"

            if clip_key not in seen_clips:
                clip_path = clips_dir / f"{clip_key}.mp4"
                if _download_clip(video_id, start, duration, clip_path):
                    manifest["clips"][clip_key] = str(clip_path)
                seen_clips.add(clip_key)

        # Download additional clips
        for extra in segment.get("additional_clips", []):
            vid = extra.get("video_id")
            if vid:
                st = extra.get("start", 0) or 0
                dur = extra.get("duration", MAX_CLIP_DURATION)
                key = f"{vid}_{st}"
                if key not in seen_clips:
                    path = clips_dir / f"{key}.mp4"
                    if _download_clip(vid, st, dur, path):
                        manifest["clips"][key] = str(path)
                    seen_clips.add(key)

        # Download screenshot
        screenshot_url = visuals.get("screenshot_url")
        if screenshot_url:
            full_url = (
                f"{api_base_url}{screenshot_url}"
                if screenshot_url.startswith("/")
                else screenshot_url
            )
            screenshot_path = images_dir / f"screen_{i:02d}.jpg"
            if _download_image(full_url, screenshot_path):
                manifest["screenshots"][f"segment_{i}"] = str(screenshot_path)

        # Download WikiImages for B-roll
        for j, wiki_img in enumerate(visuals.get("wiki_images", [])):
            img_url = wiki_img.get("original_url", "")
            if img_url:
                img_filename = wiki_img.get("filename", f"wiki_{i}_{j}.jpg")
                img_path = gallery_dir / img_filename
                if _download_image(img_url, img_path):
                    manifest["wiki_images"][f"seg{i}_wiki{j}"] = str(img_path)

    clip_count = len(manifest["clips"])
    screen_count = len(manifest["screenshots"])
    wiki_count = len(manifest["wiki_images"])
    logger.info(
        f"Assets collected: {clip_count} clips, {screen_count} screenshots, {wiki_count} wiki images"
    )

    return manifest
