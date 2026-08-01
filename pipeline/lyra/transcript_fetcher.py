"""Fetch YouTube transcripts via YouTube Data API + youtube-transcript-api, store in PostgreSQL."""

import concurrent.futures
import logging
import re
from datetime import UTC, datetime, timedelta

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

from pipeline.database import NewsChannel, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.transcript_cleaner import clean_segments

logger = logging.getLogger(__name__)

# Error messages that mean the video will never have a transcript
_PERMANENT_PATTERNS = ["members-only content", "channel's members on level", "video is private"]

# Error messages that mean the video isn't available YET (scheduled premiere).
# Don't create a DB row — re-fetch next cycle when it goes live.
_PREMIERE_PATTERNS = ["premieres in", "live event will begin"]

# Max age (hours since publication) to keep retrying failed transcripts.
# After this, mark 'skipped' to stop wasting proxy API quota on videos
# that never get auto-captions (e.g., silent drone clips).
_MAX_RETRY_AGE_HOURS = 24


class PermanentVideoError(Exception):
    """Video is permanently unavailable (members-only, private, etc.)."""


class PremiereNotReadyError(Exception):
    """Video is a scheduled premiere that hasn't aired yet."""


def _build_ytt_api(settings: LyraSettings) -> YouTubeTranscriptApi:
    """Build a YouTubeTranscriptApi instance, optionally with a proxy.

    LYRA_PROXY_URL (home-IP exit) takes precedence over Webshare. No
    blocked-retries on the generic proxy: the home IP is static until the
    daily Telekom reconnect, so retrying a block would not change the IP.
    """
    if settings.proxy_url:
        proxy_config = GenericProxyConfig(
            http_url=settings.proxy_url,
            https_url=settings.proxy_url,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)
    if settings.webshare_username and settings.webshare_password:
        proxy_config = WebshareProxyConfig(
            proxy_username=settings.webshare_username,
            proxy_password=settings.webshare_password,
            # Library default is 10 rotate-and-retry attempts per blocked IP —
            # each one costs residential traffic. 3 is plenty for a rotating pool.
            retries_when_blocked=3,
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
            logger.warning(
                f"Malformed publishedAt '{published_str}' for video {video_id}, skipping"
            )
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

        videos.append(
            {
                "id": video_id,
                "title": title,
                "published_at": published,
                "thumbnail_url": thumbnail_url,
                "description": snippet.get("description"),
            }
        )

    logger.info(f"YouTube API found {len(videos)} recent videos for {channel.name}")
    return videos


def fetch_transcript(video_id: str, settings: LyraSettings) -> tuple[str | None, float | None]:
    """Fetch and clean a YouTube transcript. Returns (transcript_text, duration_minutes)."""
    ytt_api = _build_ytt_api(settings)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(ytt_api.fetch, video_id, languages=["en", "en-US", "en-GB"])
        transcript = future.result(timeout=settings.transcript_fetch_timeout)
    except concurrent.futures.TimeoutError:
        # shutdown(wait=False) so we don't block on the hung thread
        executor.shutdown(wait=False, cancel_futures=True)
        logger.warning(
            f"Transcript fetch timed out after {settings.transcript_fetch_timeout}s for {video_id}"
        )
        return None, None
    except Exception as e:
        executor.shutdown(wait=False)
        msg = str(e)
        msg_lower = msg.lower()
        if any(p in msg_lower for p in _PREMIERE_PATTERNS):
            raise PremiereNotReadyError(msg) from e
        if any(p in msg for p in _PERMANENT_PATTERNS):
            raise PermanentVideoError(msg) from e
        logger.warning(f"No transcript for {video_id}: {e}")
        return None, None
    else:
        executor.shutdown(wait=False)

    # v1.x returns snippet objects with .text/.start/.duration attributes — convert to dicts
    transcript_list = [
        {"text": s.text, "start": s.start, "duration": s.duration} for s in transcript
    ]

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


_ISO8601_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_iso8601_duration_minutes(value: str | None) -> float | None:
    """Parse an ISO 8601 duration ("PT1H2M3S") to minutes.

    Livestreams/premieres report "P0D" or no duration at all — both return
    None here, which callers must NOT treat as "too short".
    """
    if not value:
        return None
    m = _ISO8601_DURATION_RE.fullmatch(value)
    if not m:
        return None
    h, mn, s = (int(g) if g else 0 for g in m.groups())
    return (h * 3600 + mn * 60 + s) / 60.0


def _fetch_videos_metadata_batch(video_ids: list[str], api_key: str) -> dict[str, dict] | None:
    """Batch-fetch metadata via videos.list — 1 quota unit per 50 IDs, no proxy.

    IDs missing from the result are private/members-only/deleted (the API
    silently omits them). Returns None if the API call fails, so the caller
    can fall back to unfiltered transcript fetching.
    """
    from pipeline.utils.http import fetch_with_retry

    result: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        try:
            resp = fetch_with_retry(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "id": ",".join(chunk),
                    "part": "snippet,contentDetails",
                    "key": api_key,
                },
            )
            data = resp.json()
        except Exception as e:
            logger.warning(f"YouTube API batch metadata failed ({len(chunk)} ids): {e}")
            return None
        for item in data.get("items", []):
            vid = item.get("id")
            if not vid:
                continue
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            result[vid] = {
                "duration_minutes": _parse_iso8601_duration_minutes(content.get("duration")),
                "live_broadcast_content": snippet.get("liveBroadcastContent", "none"),
                "description": snippet.get("description", "").strip() or None,
                "tags": snippet.get("tags") or None,
            }
    return result


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
                v.id
                for v in session.query(NewsVideo.id)
                .filter(NewsVideo.channel_id == channel.id)
                .all()
            }

            new_videos = [v for v in videos if v["id"] not in existing_ids]
            if not new_videos:
                continue

            # Data-API prefilter BEFORE any watch-page goes through the proxy
            # (~0.3 MB Webshare traffic per fetch_transcript call): shorts,
            # private/members-only IDs and unaired premieres never reach the
            # proxy. None = API failure -> unfiltered old behavior.
            batch_meta = _fetch_videos_metadata_batch(
                [v["id"] for v in new_videos], settings.youtube_api_key
            )

            for video_info in new_videos:
                meta = batch_meta.get(video_info["id"]) if batch_meta is not None else None

                if batch_meta is not None:
                    if meta is None:
                        # videos.list silently omits private/members-only/deleted IDs
                        logger.info(
                            f"  -> skipped (not in Data API response): {video_info['title']}"
                        )
                        session.add(
                            NewsVideo(
                                id=video_info["id"],
                                channel_id=channel.id,
                                title=video_info["title"],
                                description=video_info.get("description"),
                                published_at=video_info["published_at"],
                                thumbnail_url=video_info.get("thumbnail_url"),
                                status="skipped",
                            )
                        )
                        continue

                    if meta["live_broadcast_content"] in ("upcoming", "live"):
                        # Premiere/livestream not aired — defer without a DB row
                        # (re-checked next cycle), no watch-page burned.
                        logger.info(
                            f"  -> deferring ({meta['live_broadcast_content']}): "
                            f"{video_info['title']}"
                        )
                        continue

                    api_duration = meta["duration_minutes"]
                    # 0/None = livestream/premiere artifact (PT0S/P0D) — must
                    # NOT count as "too short", only 0 < duration < min skips.
                    if api_duration is not None and 0 < api_duration < settings.min_video_minutes:
                        logger.info(
                            f"  -> skipped ({api_duration:.1f} min < "
                            f"{settings.min_video_minutes} min minimum): {video_info['title']}"
                        )
                        session.add(
                            NewsVideo(
                                id=video_info["id"],
                                channel_id=channel.id,
                                title=video_info["title"],
                                description=video_info.get("description"),
                                published_at=video_info["published_at"],
                                duration_minutes=api_duration,
                                thumbnail_url=video_info.get("thumbnail_url"),
                                status="skipped",
                            )
                        )
                        continue

                logger.info(f"Fetching transcript for: {video_info['title']}")
                try:
                    transcript_text, duration = fetch_transcript(video_info["id"], settings)
                except PremiereNotReadyError as e:
                    # Scheduled premiere — don't create a DB row. It'll be
                    # re-fetched next cycle, and once it airs we'll process it.
                    logger.info(f"  -> deferring (premiere not aired: {e!s:.60s})")
                    continue
                except PermanentVideoError as e:
                    logger.info(f"  -> skipped (permanently unavailable: {e!s:.80s})")
                    session.add(
                        NewsVideo(
                            id=video_info["id"],
                            channel_id=channel.id,
                            title=video_info["title"],
                            description=video_info.get("description"),
                            published_at=video_info["published_at"],
                            thumbnail_url=video_info.get("thumbnail_url"),
                            status="skipped",
                        )
                    )
                    continue

                # API duration (actual video length) beats the transcript-derived
                # estimate (end of last caption, underestimates)
                if meta is not None and meta["duration_minutes"]:
                    duration = meta["duration_minutes"]

                # Skip short videos BEFORE fetching metadata (saves an API call)
                if duration is not None and duration < settings.min_video_minutes:
                    logger.info(
                        f"  -> skipped ({duration:.1f} min < {settings.min_video_minutes} min minimum)"
                    )
                    session.add(
                        NewsVideo(
                            id=video_info["id"],
                            channel_id=channel.id,
                            title=video_info["title"],
                            description=video_info.get("description"),
                            published_at=video_info["published_at"],
                            duration_minutes=duration,
                            thumbnail_url=video_info.get("thumbnail_url"),
                            status="skipped",
                        )
                    )
                    continue

                if meta is not None:
                    # Enrichment from the prefilter call — no extra videos.list
                    # request per video needed.
                    tags = meta["tags"]
                    description = meta["description"] or video_info.get("description")
                else:
                    metadata = _fetch_metadata_youtube_api(
                        video_info["id"], settings.youtube_api_key
                    )
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
                (NewsVideo.last_attempted_at.is_(None))
                | (NewsVideo.last_attempted_at < retry_after),
            )
            .all()
        )

        if not failed_videos:
            logger.info("No failed videos eligible for retry")
            return 0

        logger.info(f"Retrying transcript fetch for {len(failed_videos)} failed videos")

        now = datetime.now(UTC)
        max_retry_age = timedelta(hours=_MAX_RETRY_AGE_HOURS)

        for video in failed_videos:
            logger.info(f"  Retrying: {video.title} ({video.id})")
            try:
                transcript_text, duration = fetch_transcript(video.id, settings)
            except PremiereNotReadyError as e:
                # Still a scheduled premiere — bump last_attempted_at and
                # keep 'failed' status so the next cycle retries.
                video.last_attempted_at = now
                logger.info(f"    -> premiere not aired yet: {e!s:.60s}")
                continue
            except PermanentVideoError as e:
                video.status = "skipped"
                logger.info(f"    -> permanently unavailable, skipping: {e!s:.80s}")
                continue

            if transcript_text:
                video.duration_minutes = duration
                video.last_attempted_at = now

                if duration is not None and duration < settings.min_video_minutes:
                    video.status = "skipped"
                    logger.info(
                        f"    -> skipped ({duration:.1f} min < {settings.min_video_minutes} min minimum)"
                    )
                    continue

                video.status = "transcribed"
                video.transcript_text = transcript_text
                retried += 1
                logger.info(
                    f"    -> transcribed ({duration:.1f} min)" if duration else "    -> transcribed"
                )
            else:
                video.last_attempted_at = now
                # Give up on videos that have been failing for a while — they
                # almost certainly have no auto-captions (silent clips, etc.).
                # published_at is stored naive; coerce to UTC for comparison.
                pub = video.published_at
                if pub is not None and pub.tzinfo is None:
                    pub = pub.replace(tzinfo=UTC)
                if pub and (now - pub) > max_retry_age:
                    video.status = "skipped"
                    logger.info(f"    -> giving up after {_MAX_RETRY_AGE_HOURS}h, marking skipped")
                else:
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


def extract_transcript_segment(
    transcript_text: str, timestamp_range: str, buffer_seconds: int = 10
) -> str:
    """Extract a segment of transcript around a timestamp range.

    Args:
        transcript_text: Full transcript with [MM:SS] timestamps
        timestamp_range: Range like "02:34-03:44"
        buffer_seconds: Extra seconds before/after range to include

    Returns:
        Extracted segment text, or empty string if timestamps can't be parsed.
    """
    # Normalize unicode dashes (en-dash, em-dash, non-breaking hyphen) to ASCII
    normalized_range = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "-", timestamp_range)
    parts = normalized_range.split("-")
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
                (NewsVideo.description.is_(None))
                | (NewsVideo.description == "")
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
