"""Fetch YouTube transcripts via YouTube Data API + youtube-transcript-api, store in PostgreSQL."""

import logging
import re
from datetime import UTC, datetime, timedelta

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from pipeline.database import NewsChannel, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.transcript_cleaner import clean_segments

logger = logging.getLogger(__name__)

# Error messages that mean the video will never have a transcript
_PERMANENT_PATTERNS = ["members-only content", "channel's members on level", "video is private"]


class PermanentVideoError(Exception):
    """Video is permanently unavailable (members-only, private, etc.)."""


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


def get_recent_videos(channel: NewsChannel, lookup_days: int, api_key: str) -> list[dict]:
    """Fetch recent videos using the YouTube Data API v3 playlistItems endpoint.

    Derives the channel's "uploads" playlist ID from the channel ID
    (replace 2nd char 'C' -> 'U'). Costs 1 quota unit per call.
    """
    from pipeline.utils.http import fetch_with_retry

    # Every YouTube channel has an uploads playlist: UC... -> UU...
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
            logger.warning(f"Malformed publishedAt '{published_str}' for video {video_id}, skipping")
            continue

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


def fetch_transcript(video_id: str, settings: LyraSettings) -> tuple[str | None, float | None]:
    """Fetch and clean a YouTube transcript. Returns (transcript_text, duration_minutes)."""
    ytt_api = _build_ytt_api(settings)
    try:
        transcript = ytt_api.fetch(video_id, languages=["en", "en-US", "en-GB"])
    except Exception as e:
        msg = str(e)
        if any(p in msg for p in _PERMANENT_PATTERNS):
            raise PermanentVideoError(msg) from e
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


def fetch_new_videos(settings: LyraSettings) -> int:
    """Fetch new videos from all enabled channels and store transcripts in DB.

    Returns number of new videos processed.
    """
    from pipeline.lyra.channels import get_enabled_channels

    if not settings.youtube_api_key:
        logger.error("LYRA_YOUTUBE_API_KEY is not configured")
        return 0

    channels = get_enabled_channels()
    total_new = 0

    for channel in channels:
        videos = get_recent_videos(channel, settings.lookup_days, settings.youtube_api_key)
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
                try:
                    transcript_text, duration = fetch_transcript(
                        video_info["id"], settings
                    )
                except PermanentVideoError as e:
                    logger.info(f"  -> skipped (permanently unavailable: {e!s:.80s})")
                    session.add(NewsVideo(
                        id=video_info["id"],
                        channel_id=channel.id,
                        title=video_info["title"],
                        description=video_info.get("description"),
                        published_at=video_info["published_at"],
                        thumbnail_url=video_info.get("thumbnail_url"),
                        status="skipped",
                    ))
                    continue

                # Skip short videos BEFORE fetching metadata (saves an API call)
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

                metadata = _fetch_metadata_youtube_api(video_info["id"], settings.youtube_api_key)
                tags = metadata["tags"] if metadata else None

                # Prefer full API description over playlist snippet
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
            try:
                transcript_text, duration = fetch_transcript(video.id, settings)
            except PermanentVideoError as e:
                video.status = "skipped"
                logger.info(f"    -> permanently unavailable, skipping: {e!s:.80s}")
                continue

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
        Extracted segment text, or empty string if timestamps can't be parsed.
    """
    parts = timestamp_range.split("-")
    if len(parts) != 2:
        return ""

    start_secs = parse_timestamp_to_seconds(parts[0].strip())
    end_secs = parse_timestamp_to_seconds(parts[1].strip())
    if start_secs is None or end_secs is None:
        return ""

    start_secs = max(0, start_secs - buffer_seconds)
    end_secs = end_secs + buffer_seconds

    lines = transcript_text.split("\n")
    segment_lines = []
    ts_pattern = re.compile(r"\[(\d+:\d{2}(?::\d{2})?)\]")

    for line in lines:
        m = ts_pattern.match(line)
        if m:
            line_secs = parse_timestamp_to_seconds(m.group(1))
            if line_secs is not None and start_secs <= line_secs <= end_secs:
                segment_lines.append(line)

    return "\n".join(segment_lines)


def backfill_video_descriptions(settings: LyraSettings, max_per_cycle: int = 10) -> int:
    """Backfill descriptions and tags for existing videos via YouTube Data API.

    Videos fetched before the description/tags-parsing change have NULL values.
    Returns number of videos backfilled.
    """
    if not settings.youtube_api_key:
        logger.error("LYRA_YOUTUBE_API_KEY is not configured")
        return 0

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
            metadata = _fetch_metadata_youtube_api(video.id, settings.youtube_api_key)
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
                logger.info(f"  API failed: {video.title} (will retry next cycle)")

    logger.info(f"Backfilled {backfilled} videos")
    return backfilled
