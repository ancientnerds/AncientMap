"""Fact verification for generated posts using an LLM."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    LyraAPIError,
    LyraSettings,
    _get_settings,
    call_api,
)
from pipeline.lyra.transcript_fetcher import extract_transcript_segment, parse_timestamp_to_seconds

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "verify_tweets.txt"

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verification_level": {"type": "string", "enum": ["VERIFY_AS_IS", "MODIFY", "REJECT"]},
        "timestamp": {"type": "string"},
        "suggested_modification": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "modified_text": {"type": "string"},
                        "changes_explained": {"type": "string"},
                    },
                    "required": ["modified_text", "changes_explained"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ],
        },
    },
    "required": ["verification_level", "timestamp", "suggested_modification"],
    "additionalProperties": False,
}


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def verify_single_post(
    item: NewsItem,
    transcript_text: str,
    model: str,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
) -> dict | None:
    """Verify a single post against the transcript.

    Returns verification result dict or None on failure.
    """
    if not item.post_text:
        return None

    # Extract transcript around the timestamp, fall back to start of transcript
    if item.timestamp_range:
        segment = extract_transcript_segment(transcript_text, item.timestamp_range)
    else:
        segment = None
    if not segment and transcript_text:
        segment = transcript_text[:3000]
    if not segment:
        logger.warning(f"Skipping item {item.id}: no transcript text available")
        return None

    if system_prompt is None:
        system_prompt = _load_prompt()

    ts_label = item.timestamp_range or "start of video"
    user_content = (
        f"Tweet to verify:\n{item.post_text}\n\n"
        f"Relevant transcript segment (roughly from {ts_label}):\n"
        f"<transcript_segment>\n{segment}\n</transcript_segment>"
    )

    try:
        _max_tokens = max_tokens if max_tokens is not None else _get_settings().max_tokens
        response = call_api(
            model=model,
            max_tokens=_max_tokens,
            temperature=0.0,
            reasoning_effort="medium",
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "FactVerification",
                    "strict": True,
                    "schema": VERIFY_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.warning(f"Verification API error for item {item.id}: {e}")
        return None

    text_block = next((b.text for b in response.content if hasattr(b, "text")), None)
    if not text_block:
        logger.warning(f"Empty verification response for item {item.id}")
        return None
    try:
        return json.loads(text_block)
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse verification result for item %s", item.id)
        return None


def verify_video_posts(
    video: NewsVideo,
    settings: LyraSettings,
    system_prompt: str | None = None,
) -> int:
    """Verify all posts for a video against its transcript.

    Applies modifications or clears rejected posts.
    Returns number of items verified.
    """
    if not video.transcript_text:
        return 0

    if not settings.anthropic_api_key:
        return 0
    if system_prompt is None:
        system_prompt = _load_prompt()

    with get_session() as session:
        items = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.isnot(None),
                NewsItem.verified_at.is_(None),
            )
            .all()
        )

        if not items:
            # All items already verified — transition the video if needed
            v = session.get(NewsVideo, video.id)
            if v and v.status == "posted":
                v.status = "verified"
                logger.info(
                    f"Video {video.id}: all items already verified, transitioning to 'verified'"
                )
            return 0

        verified = 0
        skipped = 0
        for item in items:
            result = verify_single_post(
                item,
                video.transcript_text,
                settings.model_verify,
                system_prompt,
                max_tokens=settings.max_tokens,
            )
            if not result:
                skipped += 1
                continue

            level = result.get("verification_level", "")

            if level == "REJECT":
                item.post_text = None
                item.news_category = "rejected"
                logger.info(f"Rejected item {item.id} (soft-delete)")
            elif level == "MODIFY":
                mod = result.get("suggested_modification", {})
                modified = mod.get("modified_text", "") if mod else ""
                if modified:
                    item.post_text = modified
                    logger.info(
                        f"Modified post for item {item.id}: {mod.get('changes_explained', '')}"
                    )

            # Update timestamp if verification found a more precise one
            ts = result.get("timestamp")
            if ts:
                secs = parse_timestamp_to_seconds(ts)
                if secs is not None:
                    item.timestamp_seconds = secs

            item.verified_at = datetime.now(UTC)
            verified += 1

        session.flush()

        # Count remaining unverified items for this video
        remaining = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.isnot(None),
                NewsItem.verified_at.is_(None),
            )
            .count()
        )

        v = session.get(NewsVideo, video.id)
        if v:
            if remaining == 0:
                v.status = "verified"
            else:
                logger.warning(
                    f"Video {video.id}: {remaining} items still unverified, keeping 'posted' for retry"
                )

    logger.info(f"Verified {verified}/{len(items)} posts for video {video.id} ({skipped} skipped)")
    return verified


def verify_pending_posts(settings: LyraSettings) -> int:
    """Verify posts for all videos in 'posted' status.

    Returns total number of items verified.
    """
    with get_session() as session:
        videos = session.query(NewsVideo).filter(NewsVideo.status == "posted").all()
        session.expunge_all()

    system_prompt = _load_prompt()
    total = 0
    for video in videos:
        try:
            total += verify_video_posts(video, settings, system_prompt)
        except Exception:
            logger.exception(f"Failed to verify video {video.id}, skipping")

    logger.info(f"Verified {total} posts total")
    return total
