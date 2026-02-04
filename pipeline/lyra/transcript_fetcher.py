"""Fetch YouTube transcripts via RSS + youtube-transcript-api, store in PostgreSQL."""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta, timezone

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from pipeline.database import NewsChannel, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.transcript_cleaner import clean_segments

logger = logging.getLogger(__name__)

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/xml, text/xml, */*",
}


def get_recent_videos(channel: NewsChannel, lookup_days: int) -> list[dict]:
    """Fetch recent videos from a channel's RSS feed."""
    url = YOUTUBE_RSS_URL.format(channel_id=channel.id)
    try:
        resp = requests.get(url, headers=RSS_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch RSS for {channel.name}: {e}")
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse RSS XML for {channel.name}: {e}")
        return []

    cutoff = datetime.now(UTC) - timedelta(days=lookup_days)
    videos = []

    for entry in root.findall("atom:entry", ATOM_NS):
        video_id_el = entry.find("yt:videoId", ATOM_NS)
        title_el = entry.find("atom:title", ATOM_NS)
        published_el = entry.find("atom:published", ATOM_NS)

        if video_id_el is None or title_el is None or published_el is None:
            continue

        video_id = video_id_el.text
        title = title_el.text
        published_str = published_el.text

        # Parse ISO 8601 date
        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if published < cutoff:
            continue

        # Skip trailers and premieres
        if title and any(skip in title.lower() for skip in ["trailer", "premiere", "teaser", "promo"]):
            continue

        # Get thumbnail
        media_group = entry.find("media:group", ATOM_NS)
        thumbnail_url = None
        if media_group is not None:
            thumb = media_group.find("media:thumbnail", ATOM_NS)
            if thumb is not None:
                thumbnail_url = thumb.get("url")

        videos.append({
            "id": video_id,
            "title": title,
            "published_at": published,
            "thumbnail_url": thumbnail_url,
        })

    return videos


def fetch_transcript(video_id: str, trim_start: int = 120) -> tuple[str | None, float | None]:
    """Fetch and clean a YouTube transcript. Returns (transcript_text, duration_minutes)."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "en-US", "en-GB"]
        )
    except Exception as e:
        logger.warning(f"No transcript for {video_id}: {e}")
        return None, None

    if not transcript_list:
        return None, None

    # Calculate duration from last segment
    last_seg = transcript_list[-1]
    duration_seconds = last_seg.get("start", 0) + last_seg.get("duration", 0)
    duration_minutes = duration_seconds / 60.0

    # Trim intro segments
    trimmed = [seg for seg in transcript_list if seg.get("start", 0) >= trim_start]
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

    channels = get_enabled_channels()
    total_new = 0

    for channel in channels:
        videos = get_recent_videos(channel, settings.lookup_days)
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
                    video_info["id"], settings.transcript_trim_start
                )

                status = "transcribed" if transcript_text else "failed"

                video = NewsVideo(
                    id=video_info["id"],
                    channel_id=channel.id,
                    title=video_info["title"],
                    published_at=video_info["published_at"],
                    duration_minutes=duration,
                    thumbnail_url=video_info.get("thumbnail_url"),
                    transcript_text=transcript_text,
                    status=status,
                )
                session.add(video)
                total_new += 1
                logger.info(f"  -> {status} ({duration:.1f} min)" if duration else f"  -> {status}")

    logger.info(f"Fetched {total_new} new videos total")
    return total_new


def _parse_timestamp(ts: str) -> int | None:
    """Parse 'MM:SS' to seconds."""
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

    start_secs = _parse_timestamp(parts[0].strip())
    end_secs = _parse_timestamp(parts[1].strip())
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
            line_secs = _parse_timestamp(m.group(1))
            if line_secs is not None and start_secs <= line_secs <= end_secs:
                segment_lines.append(line)

    return "\n".join(segment_lines) if segment_lines else transcript_text[:2000]
