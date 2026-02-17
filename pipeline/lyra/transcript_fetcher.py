"""Fetch YouTube transcripts via yt-dlp + youtube-transcript-api, store in PostgreSQL."""

import json
import logging
import re
import subprocess
from datetime import UTC, datetime, timedelta

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from pipeline.database import NewsChannel, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.transcript_cleaner import clean_segments

logger = logging.getLogger(__name__)


def _build_ytt_api(settings: LyraSettings) -> YouTubeTranscriptApi:
    """Build a YouTubeTranscriptApi instance, optionally with Webshare proxy."""
    if settings.webshare_username and settings.webshare_password:
        proxy_config = WebshareProxyConfig(
            proxy_username=settings.webshare_username,
            proxy_password=settings.webshare_password,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)
    return YouTubeTranscriptApi()

SKIP_TITLE_KEYWORDS = ["trailer", "premiere", "teaser", "promo"]


def _get_recent_videos_api(channel: NewsChannel, lookup_days: int, api_key: str) -> list[dict]:
    """Fetch recent videos using the YouTube Data API v3 playlistItems endpoint.

    Derives the channel's "uploads" playlist ID from the channel ID
    (replace 2nd char 'C' → 'U'). Costs 1 quota unit per call.
    """
    from pipeline.utils.http import fetch_with_retry

    # Every YouTube channel has an uploads playlist: UC... → UU...
    uploads_playlist_id = "UU" + channel.id[2:]
    cutoff = datetime.now(UTC) - timedelta(days=lookup_days)

    try:
        resp = fetch_with_retry(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "playlistId": uploads_playlist_id,
                "part": "snippet",
                "maxResults": 15,
                "key": api_key,
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"YouTube API playlist fetch failed for {channel.name}: {e}")
        return []

    videos = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId")
        title = snippet.get("title", "")

        if not video_id or not title:
            continue

        # Parse ISO 8601 publishedAt
        published_str = snippet.get("publishedAt", "")
        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published = datetime.now(UTC)

        if published < cutoff:
            continue

        if any(skip in title.lower() for skip in SKIP_TITLE_KEYWORDS):
            continue

        # Best available thumbnail
        thumbs = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbs.get("high", {}).get("url")
            or thumbs.get("medium", {}).get("url")
            or thumbs.get("default", {}).get("url")
            or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        )

        videos.append({
            "id": video_id,
            "title": title,
            "published_at": published,
            "thumbnail_url": thumbnail_url,
            "description": snippet.get("description"),
        })

    logger.info(f"YouTube API found {len(videos)} recent videos for {channel.name}")
    return videos


def _get_recent_videos_ytdlp(channel: NewsChannel, lookup_days: int, proxy_url: str | None) -> list[dict]:
    """Fetch recent videos using yt-dlp --flat-playlist (fallback when no API key)."""
    channel_url = f"https://www.youtube.com/channel/{channel.id}/videos"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--playlist-items", "1:15",
        channel_url,
    ]
    if proxy_url:
        cmd.insert(1, "--proxy")
        cmd.insert(2, proxy_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp playlist timed out for {channel.name}")
        return []

    if result.returncode != 0:
        logger.warning(f"yt-dlp playlist failed for {channel.name}: {result.stderr.strip()[-200:]}")
        return []

    cutoff = datetime.now(UTC) - timedelta(days=lookup_days)
    videos = []

    for line in result.stdout.strip().splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        video_id = data.get("id")
        title = data.get("title")
        upload_date = data.get("upload_date")  # YYYYMMDD

        if not video_id or not title:
            continue

        # Parse upload_date (YYYYMMDD) to datetime
        if upload_date:
            try:
                published = datetime(
                    int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8]),
                    tzinfo=UTC,
                )
            except (ValueError, IndexError):
                published = datetime.now(UTC)
        else:
            published = datetime.now(UTC)

        if published < cutoff:
            continue

        if any(skip in title.lower() for skip in SKIP_TITLE_KEYWORDS):
            continue

        thumbnails = data.get("thumbnails")
        if thumbnails and isinstance(thumbnails, list):
            thumbnail_url = thumbnails[-1].get("url")
        else:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        videos.append({
            "id": video_id,
            "title": title,
            "published_at": published,
            "thumbnail_url": thumbnail_url,
            "description": data.get("description"),
        })

    logger.info(f"yt-dlp found {len(videos)} recent videos for {channel.name}")
    return videos


def get_recent_videos(channel: NewsChannel, lookup_days: int, proxy_url: str | None,
                      api_key: str | None = None) -> list[dict]:
    """Fetch recent videos from a channel.

    Prefers the YouTube Data API (fast, reliable, 1 quota unit per call).
    Falls back to yt-dlp scraping when no API key is configured.
    """
    if api_key:
        return _get_recent_videos_api(channel, lookup_days, api_key)
    return _get_recent_videos_ytdlp(channel, lookup_days, proxy_url)


def fetch_transcript(video_id: str, settings: LyraSettings) -> tuple[str | None, float | None]:
    """Fetch and clean a YouTube transcript. Returns (transcript_text, duration_minutes)."""
    ytt_api = _build_ytt_api(settings)
    try:
        transcript = ytt_api.fetch(video_id, languages=["en", "en-US", "en-GB"])
    except Exception as e:
        logger.warning(f"No transcript for {video_id}: {e}")
        return None, None

    # v1.x returns snippet objects with .text/.start/.duration attributes — convert to dicts
    transcript_list = [{"text": s.text, "start": s.start, "duration": s.duration} for s in transcript]

    if not transcript_list:
        return None, None

    # Calculate duration from last segment
    last_seg = transcript_list[-1]
    duration_seconds = last_seg["start"] + last_seg["duration"]
    duration_minutes = duration_seconds / 60.0

    # Trim intro segments
    trim_start = settings.transcript_trim_start
    trimmed = [seg for seg in transcript_list if seg["start"] >= trim_start]
    if not trimmed:
        trimmed = transcript_list  # Don't trim if nothing would remain

    # Clean segments
    cleaned = clean_segments(trimmed)

    # Build timestamped text
    lines = []
    for seg in cleaned:
        start = seg.get("start", 0)
        minutes = int(start // 60)
        seconds = int(start % 60)
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

    transcript_text = "\n".join(lines)
    return transcript_text, duration_minutes


def fetch_new_videos(settings: LyraSettings) -> int:
    """Fetch new videos from all enabled channels and store transcripts in DB.

    Returns number of new videos processed.
    """
    from pipeline.lyra.channels import get_enabled_channels
    from pipeline.lyra.screenshot_extractor import get_proxy_url

    channels = get_enabled_channels()
    proxy_url = get_proxy_url(settings)
    total_new = 0

    for channel in channels:
        videos = get_recent_videos(channel, settings.lookup_days, proxy_url,
                                   api_key=settings.youtube_api_key or None)
        if not videos:
            continue

        with get_session() as session:
            # Get already-processed video IDs
            existing_ids = {
                v.id for v in session.query(NewsVideo.id)
                .filter(NewsVideo.channel_id == channel.id)
                .all()
            }

            for video_info in videos:
                if video_info["id"] in existing_ids:
                    continue

                logger.info(f"Fetching transcript for: {video_info['title']}")
                transcript_text, duration = fetch_transcript(
                    video_info["id"], settings
                )

                # Skip short videos BEFORE fetching yt-dlp metadata (saves a subprocess call)
                if duration is not None and duration < settings.min_video_minutes:
                    logger.info(f"  -> skipped ({duration:.1f} min < {settings.min_video_minutes} min minimum)")
                    session.add(NewsVideo(
                        id=video_info["id"],
                        channel_id=channel.id,
                        title=video_info["title"],
                        description=video_info.get("description"),
                        published_at=video_info["published_at"],
                        duration_minutes=duration,
                        thumbnail_url=video_info.get("thumbnail_url"),
                        status="skipped",
                    ))
                    continue

                # Fetch tags + description (prefer YouTube API, fall back to yt-dlp)
                if settings.youtube_api_key:
                    metadata = _fetch_metadata_youtube_api(video_info["id"], settings.youtube_api_key)
                else:
                    metadata = _fetch_metadata_ytdlp(video_info["id"], proxy_url)
                tags = metadata["tags"] if metadata else None

                # Prefer yt-dlp description over RSS if available
                description = video_info.get("description")
                if metadata and metadata["description"]:
                    description = metadata["description"]

                status = "transcribed" if transcript_text else "failed"

                video = NewsVideo(
                    id=video_info["id"],
                    channel_id=channel.id,
                    title=video_info["title"],
                    description=description,
                    published_at=video_info["published_at"],
                    duration_minutes=duration,
                    thumbnail_url=video_info.get("thumbnail_url"),
                    tags=tags,
                    transcript_text=transcript_text,
                    status=status,
                    last_attempted_at=datetime.now(UTC) if status == "failed" else None,
                )
                session.add(video)
                total_new += 1
                logger.info(f"  -> {status} ({duration:.1f} min)" if duration else f"  -> {status}")

    logger.info(f"Fetched {total_new} new videos total")
    return total_new


def retry_failed_videos(settings: LyraSettings) -> int:
    """Retry transcript fetching for videos that previously failed (e.g. livestreams
    where captions weren't ready yet).

    Only retries videos still within the lookup_days window and whose last attempt
    was at least retry_delay_hours ago. Returns number of successfully retried videos.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.lookup_days)
    retry_after = datetime.now(UTC) - timedelta(hours=settings.retry_delay_hours)
    retried = 0

    with get_session() as session:
        failed_videos = (
            session.query(NewsVideo)
            .filter(
                NewsVideo.status == "failed",
                NewsVideo.published_at > cutoff,
                (NewsVideo.last_attempted_at.is_(None)) | (NewsVideo.last_attempted_at < retry_after),
            )
            .all()
        )

        if not failed_videos:
            logger.info("No failed videos eligible for retry")
            return 0

        logger.info(f"Retrying transcript fetch for {len(failed_videos)} failed videos")

        for video in failed_videos:
            logger.info(f"  Retrying: {video.title} ({video.id})")
            transcript_text, duration = fetch_transcript(video.id, settings)

            if transcript_text:
                video.duration_minutes = duration
                video.last_attempted_at = datetime.now(UTC)

                if duration is not None and duration < settings.min_video_minutes:
                    video.status = "skipped"
                    logger.info(f"    -> skipped ({duration:.1f} min < {settings.min_video_minutes} min minimum)")
                    continue

                video.status = "transcribed"
                video.transcript_text = transcript_text
                retried += 1
                logger.info(f"    -> transcribed ({duration:.1f} min)" if duration else "    -> transcribed")
            else:
                video.last_attempted_at = datetime.now(UTC)
                logger.info("    -> still no transcript, will retry later")

    logger.info(f"Retried {retried} videos successfully")
    return retried


def parse_timestamp_to_seconds(ts: str) -> int | None:
    """Parse 'MM:SS' or 'HH:MM:SS' to seconds."""
    m = re.match(r"(\d+):(\d{2}):(\d{2})", ts)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"(\d+):(\d{2})", ts)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def extract_transcript_segment(transcript_text: str, timestamp_range: str, buffer_seconds: int = 10) -> str:
    """Extract a segment of transcript around a timestamp range.

    Args:
        transcript_text: Full transcript with [MM:SS] timestamps
        timestamp_range: Range like "02:34-03:44"
        buffer_seconds: Extra seconds before/after range to include

    Returns:
        Extracted segment text
    """
    parts = timestamp_range.split("-")
    if len(parts) != 2:
        return transcript_text[:2000]  # Fallback: return beginning

    start_secs = parse_timestamp_to_seconds(parts[0].strip())
    end_secs = parse_timestamp_to_seconds(parts[1].strip())
    if start_secs is None or end_secs is None:
        return transcript_text[:2000]

    start_secs = max(0, start_secs - buffer_seconds)
    end_secs = end_secs + buffer_seconds

    lines = transcript_text.split("\n")
    segment_lines = []
    ts_pattern = re.compile(r"\[(\d{2}:\d{2})\]")

    for line in lines:
        m = ts_pattern.match(line)
        if m:
            line_secs = parse_timestamp_to_seconds(m.group(1))
            if line_secs is not None and start_secs <= line_secs <= end_secs:
                segment_lines.append(line)

    return "\n".join(segment_lines) if segment_lines else transcript_text[:2000]


def _fetch_metadata_youtube_api(video_id: str, api_key: str) -> dict | None:
    """Fetch video metadata using the YouTube Data API v3.

    No cookies or OAuth needed — just an API key. Free tier: 10,000 units/day
    (this call costs 1 unit). Returns dict with 'description' and 'tags' keys.
    """
    from pipeline.utils.http import fetch_with_retry

    try:
        resp = fetch_with_retry(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "id": video_id,
                "part": "snippet",
                "key": api_key,
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"YouTube API metadata failed for {video_id}: {e}")
        return None

    items = data.get("items", [])
    if not items:
        return None

    snippet = items[0].get("snippet", {})
    return {
        "description": snippet.get("description", "").strip() or None,
        "tags": snippet.get("tags") or None,
    }


def _fetch_metadata_ytdlp(video_id: str, proxy_url: str | None) -> dict | None:
    """Fetch video metadata using yt-dlp (no video download).

    Fallback for when no YouTube API key is configured.
    Returns dict with 'description' and 'tags' keys, or None on failure.
    """
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-warnings",
        yt_url,
    ]
    if proxy_url:
        cmd.insert(1, "--proxy")
        cmd.insert(2, proxy_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"yt-dlp metadata failed for {video_id}: {result.stderr.strip()[-200:]}")
            return None

        data = json.loads(result.stdout)
        return {
            "description": data.get("description", "").strip() or None,
            "tags": data.get("tags") or None,
        }
    except subprocess.TimeoutExpired:
        logger.warning(f"yt-dlp metadata timed out for {video_id}")
        return None
    except (json.JSONDecodeError, KeyError):
        logger.warning(f"yt-dlp returned invalid JSON for {video_id}")
        return None


def backfill_video_descriptions(settings: LyraSettings, max_per_cycle: int = 10) -> int:
    """Backfill descriptions and tags for existing videos using yt-dlp.

    Videos fetched before the description/tags-parsing change have NULL values.
    This fetches them via yt-dlp metadata extraction (no video download needed).

    Returns number of videos backfilled.
    """
    from pipeline.lyra.screenshot_extractor import get_proxy_url

    proxy_url = get_proxy_url(settings)
    backfilled = 0

    with get_session() as session:
        # Videos missing description OR tags (backfill both)
        videos = (
            session.query(NewsVideo)
            .filter(
                (NewsVideo.description.is_(None)) | (NewsVideo.description == "")
                | (NewsVideo.tags.is_(None)),
                NewsVideo.status != "skipped",
            )
            .limit(max_per_cycle)
            .all()
        )

        if not videos:
            logger.info("No videos need metadata backfill")
            return 0

        logger.info(f"Backfilling metadata for {len(videos)} videos")

        for video in videos:
            if settings.youtube_api_key:
                metadata = _fetch_metadata_youtube_api(video.id, settings.youtube_api_key)
            else:
                metadata = _fetch_metadata_ytdlp(video.id, proxy_url)
            if metadata:
                updated = False
                if metadata["description"] and not video.description:
                    video.description = metadata["description"]
                    updated = True
                if metadata["tags"] and not video.tags:
                    video.tags = metadata["tags"]
                    updated = True
                if updated:
                    backfilled += 1
                    logger.info(f"  Backfilled: {video.title}")
                else:
                    logger.info(f"  No new metadata: {video.title}")
            else:
                logger.info(f"  yt-dlp failed: {video.title} (will retry next cycle)")

    logger.info(f"Backfilled {backfilled} videos")
    return backfilled
