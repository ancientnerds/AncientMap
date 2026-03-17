"""LLM summarization of video transcripts -> news items."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    LyraAPIError,
    LyraSettings,
    call_api,
)
from pipeline.lyra.transcript_fetcher import extract_transcript_segment, parse_timestamp_to_seconds

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "summary.txt"
RELEVANCE_PROMPT_PATH = Path(__file__).parent / "prompts" / "relevance_gate.txt"

RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_archaeology": {"type": "boolean"},
        "is_speculative": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["is_archaeology", "reason"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "key_topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "timestamp_range": {"type": "string"},
                    "facts": {"type": "array", "items": {"type": "string"}},
                    "primary_site": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "country": {"type": "string"},
                                    "confidence": {"type": "string", "enum": ["high", "medium"]},
                                    "site_type": {
                                        "type": "string",
                                        "enum": [
                                            "settlement",
                                            "temple",
                                            "tomb",
                                            "fortification",
                                            "megalithic",
                                            "cave",
                                            "rock_art",
                                            "port",
                                            "monument",
                                            "inscription",
                                            "ruin",
                                            "archaeological_site",
                                        ],
                                    },
                                    "period": {
                                        "type": "string",
                                        "enum": [
                                            "< 4500 BC",
                                            "4500 - 3000 BC",
                                            "3000 - 1500 BC",
                                            "1500 - 500 BC",
                                            "500 BC - 1 AD",
                                            "1 - 500 AD",
                                            "500 - 1000 AD",
                                            "1000 - 1500 AD",
                                            "1500+ AD",
                                            "Unknown",
                                        ],
                                    },
                                },
                                "required": [
                                    "name",
                                    "country",
                                    "confidence",
                                    "site_type",
                                    "period",
                                ],
                                "additionalProperties": False,
                            },
                            {"type": "null"},
                        ],
                    },
                },
                "required": ["headline", "timestamp_range", "facts", "primary_site"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["key_topics"],
    "additionalProperties": False,
}


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _load_relevance_prompt() -> str:
    return RELEVANCE_PROMPT_PATH.read_text(encoding="utf-8")


def _check_relevance(
    video: NewsVideo,
    settings: LyraSettings,
    relevance_prompt: str | None = None,
) -> bool | None:
    """Quick LLM check: is this video about real archaeology?

    Returns True if relevant, False if not, None if the check failed
    (LLM unavailable / bad response).
    """
    context_parts = [f"Title: {video.title}"]
    if video.description:
        context_parts.append(f"Description: {video.description[:500]}")
    if video.tags:
        context_parts.append(f"Tags: {', '.join(video.tags)}")
    if video.transcript_text:
        context_parts.append(f"Transcript start: {video.transcript_text[:500]}")

    system_prompt = relevance_prompt or _load_relevance_prompt()
    user_content = "\n".join(context_parts)

    try:
        response = call_api(
            model=settings.model_relevance,
            max_tokens=settings.max_tokens,
            temperature=0.0,
            reasoning_effort="instant",
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "RelevanceCheck",
                    "strict": True,
                    "schema": RELEVANCE_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.error(f"Relevance gate API error for {video.id}: {e}")
        return None

    text_block = next((b.text for b in response.content if hasattr(b, "text")), None)
    if not text_block:
        logger.warning(f"Relevance gate: empty response for {video.id}")
        return None

    try:
        result = json.loads(text_block)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Relevance gate: bad JSON for {video.id}: {e}")
        return None
    if not result.get("is_archaeology", True):
        logger.info(f"Relevance gate: {video.title!r} -> NO ({result.get('reason', '')})")
    return result.get("is_archaeology", True)


def _calculate_topic_limit(
    duration_minutes: float | None,
    settings: LyraSettings,
    channel_item_count: int = 0,
    avg_items: float = 0,
) -> int:
    """Calculate how many topics to extract based on video length and channel balance."""
    if duration_minutes is None:
        duration_minutes = 15.0

    if duration_minutes <= settings.post_threshold_short:
        base_limit = settings.post_amounts_short
    elif duration_minutes <= settings.post_threshold_medium:
        base_limit = settings.post_amounts_medium
    elif duration_minutes <= settings.post_threshold_long:
        base_limit = settings.post_amounts_long
    else:
        base_limit = settings.post_amounts_very_long

    # Channel balancing: reduce topics for over-represented channels
    if avg_items > 0 and settings.channel_balance_factor > 0:
        ratio = channel_item_count / avg_items
        if ratio > settings.channel_balance_factor * 2:  # >4x avg
            original = base_limit
            base_limit = max(1, base_limit // 3)
            logger.info(
                f"Channel balance: {channel_item_count} items "
                f"({ratio:.1f}x avg) -> {base_limit} topics (was {original})"
            )
        elif ratio > settings.channel_balance_factor:  # >2x avg
            original = base_limit
            base_limit = max(1, base_limit // 2)
            logger.info(
                f"Channel balance: {channel_item_count} items "
                f"({ratio:.1f}x avg) -> {base_limit} topics (was {original})"
            )

    return base_limit


def summarize_video(
    video: NewsVideo,
    settings: LyraSettings,
    channel_item_count: int = 0,
    avg_items: float = 0,
    summary_prompt: str | None = None,
    relevance_prompt: str | None = None,
) -> bool:
    """Summarize a single video's transcript using an LLM.

    Creates NewsItem records for each key topic. Returns True on success.
    """
    if not video.transcript_text:
        logger.warning(f"No transcript for video {video.id}")
        return False

    if not settings.anthropic_api_key:
        logger.error("No LLM API key configured")
        return False

    # Relevance gate: skip non-archaeology videos
    relevance = _check_relevance(video, settings, relevance_prompt)
    if relevance is None:
        logger.warning(f"Relevance gate unavailable for {video.id}, deferring to next cycle")
        return False
    if not relevance:
        with get_session() as session:
            v = session.get(NewsVideo, video.id)
            if v:
                v.status = "skipped"
        logger.info(f"Skipped {video.id}: not archaeology ({video.title})")
        return False

    topic_limit = _calculate_topic_limit(
        video.duration_minutes, settings, channel_item_count, avg_items
    )

    # Build video context from title, description, and tags
    context_parts = [f"Video title: {video.title}"]
    if video.description:
        # Truncate description to avoid using too many tokens
        desc = video.description[:1000]
        context_parts.append(f"Video description: {desc}")
    if video.tags:
        context_parts.append(f"Video tags: {', '.join(video.tags)}")
    video_context = "\n".join(context_parts)

    system_prompt = summary_prompt or _load_prompt()

    user_content = (
        f"Extract exactly {topic_limit} key topics from this video.\n\n"
        f"{video_context}\n\n"
        f"<transcript>\n{video.transcript_text}\n</transcript>"
    )

    try:
        response = call_api(
            model=settings.model_summarize,
            max_tokens=settings.max_tokens,
            temperature=0.0,
            reasoning_effort="low",
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "VideoSummary",
                    "strict": True,
                    "schema": SUMMARY_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.error(f"LLM API error for {video.id}: {e}")
        return False

    text_block = next((b.text for b in response.content if hasattr(b, "text")), None)
    if not text_block:
        logger.warning(f"Empty response content for {video.id}")
        return False
    try:
        summary_data = json.loads(text_block)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse summary JSON for {video.id}: {e}")
        return False

    key_topics = summary_data.get("key_topics", [])
    if not key_topics:
        logger.warning(f"No key topics found for {video.id}")
        return False

    if len(key_topics) > topic_limit:
        logger.warning(
            f"LLM returned {len(key_topics)} topics for {video.id}, truncating to {topic_limit}"
        )
        key_topics = key_topics[:topic_limit]

    # Save summary JSON and create news items
    with get_session() as session:
        db_video = session.get(NewsVideo, video.id)
        if not db_video:
            return False

        db_video.summary_json = summary_data
        db_video.status = "summarized"
        db_video.processed_at = datetime.now(UTC)

        for topic in key_topics:
            if not isinstance(topic, dict):
                logger.warning(f"Malformed topic in {video.id}: {type(topic).__name__}, skipping")
                continue
            ts_range = topic.get("timestamp_range")
            ts_seconds = None
            if ts_range:
                # Normalize unicode dashes to ASCII before splitting
                normalized = (
                    ts_range.replace("\u2010", "-")
                    .replace("\u2011", "-")
                    .replace("\u2013", "-")
                    .replace("\u2014", "-")
                )
                parts = normalized.split("-")
                if parts:
                    ts_seconds = parse_timestamp_to_seconds(parts[0])

            facts = topic.get("facts", [])
            headline = topic.get("headline") or (facts[0] if facts else "Archaeological finding")
            # Truncate headline to fit DB column
            if len(headline) > 500:
                headline = headline[:497] + "..."

            # Extract primary site name if LLM provided one with high confidence
            site_name = None
            primary_site = topic.get("primary_site")
            if primary_site and isinstance(primary_site, dict):
                confidence = primary_site.get("confidence", "")
                if confidence in ("high", "medium") and primary_site.get("name"):
                    site_name = primary_site["name"][:500]

            # Extract raw transcript segment around the topic timestamp
            transcript_segment = None
            if ts_range and video.transcript_text:
                segment = extract_transcript_segment(
                    video.transcript_text, ts_range, buffer_seconds=60
                )
                if segment and len(segment) > 20:
                    transcript_segment = segment[:500]

            # Compose summary from headline + first few facts
            summary_parts = [f"{headline}."]
            for fact in facts[:3]:
                if isinstance(fact, str) and fact.strip():
                    summary_parts.append(fact.strip())
            composed_summary = " ".join(summary_parts)

            item = NewsItem(
                video_id=video.id,
                headline=headline,
                summary=composed_summary,
                facts=facts,
                timestamp_range=ts_range,
                timestamp_seconds=ts_seconds,
                site_name_extracted=site_name,
                transcript_segment=transcript_segment,
            )
            session.add(item)

    logger.info(f"Summarized {video.id}: {len(key_topics)} topics")
    return True


def summarize_pending_videos(settings: LyraSettings) -> int:
    """Summarize all videos that have transcripts but no summaries yet.

    Only processes videos published within the lookup_days window.
    Returns number of videos summarized.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.lookup_days)
    with get_session() as session:
        pending = (
            session.query(NewsVideo)
            .filter(
                NewsVideo.status == "transcribed",
                NewsVideo.published_at >= cutoff,
            )
            .all()
        )
        session.expunge_all()

    # Query channel item counts for balancing (only within the lookback window)
    with get_session() as session:
        channel_counts = dict(
            session.query(NewsVideo.channel_id, func.count(NewsItem.id))
            .join(NewsItem, NewsItem.video_id == NewsVideo.id)
            .filter(NewsItem.post_text.isnot(None), NewsVideo.published_at >= cutoff)
            .group_by(NewsVideo.channel_id)
            .all()
        )
    avg_items = sum(channel_counts.values()) / max(len(channel_counts), 1)

    summary_prompt = _load_prompt()
    relevance_prompt = _load_relevance_prompt()
    count = 0
    for video in pending:
        ch_count = channel_counts.get(video.channel_id, 0)
        try:
            if summarize_video(
                video, settings, ch_count, avg_items, summary_prompt, relevance_prompt
            ):
                count += 1
        except Exception:
            logger.exception(f"Failed to summarize video {video.id}, skipping")

    logger.info(f"Summarized {count}/{len(pending)} pending videos")
    return count
