"""Claude AI summarization of video transcripts -> news items."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "summary.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _calculate_topic_limit(duration_minutes: float | None, settings: LyraSettings) -> int:
    """Calculate how many topics to extract based on video length."""
    if duration_minutes is None:
        duration_minutes = 15.0

    if duration_minutes <= settings.post_threshold_short:
        return settings.post_amounts_short
    elif duration_minutes <= settings.post_threshold_medium:
        return settings.post_amounts_medium
    elif duration_minutes <= settings.post_threshold_long:
        return settings.post_amounts_long
    else:
        return settings.post_amounts_very_long


def _parse_timestamp_to_seconds(ts: str) -> int | None:
    """Parse 'MM:SS' to seconds."""
    m = re.match(r"(\d+):(\d{2})", ts.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def summarize_video(video: NewsVideo, settings: LyraSettings) -> bool:
    """Summarize a single video's transcript using Claude AI.

    Creates NewsItem records for each key topic. Returns True on success.
    """
    if not video.transcript_text:
        logger.warning(f"No transcript for video {video.id}")
        return False

    if not settings.anthropic_api_key:
        logger.error("No Anthropic API key configured")
        return False

    topic_limit = _calculate_topic_limit(video.duration_minutes, settings)

    # Build video context from title, description, and tags
    context_parts = [f"Video title: {video.title}"]
    if video.description:
        # Truncate description to avoid using too many tokens
        desc = video.description[:1000]
        context_parts.append(f"Video description: {desc}")
    if video.tags:
        context_parts.append(f"Video tags: {', '.join(video.tags)}")
    video_context = "\n".join(context_parts)

    prompt_template = _load_prompt()
    prompt = prompt_template.format(
        topic_limit=topic_limit,
        video_context=video_context,
        content=video.transcript_text,
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.model_summarize,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for {video.id}: {e}")
        return False

    response_text = response.content[0].text

    # Extract JSON from response
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not json_match:
        logger.warning(f"No JSON in summary response for {video.id}")
        return False

    try:
        summary_data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in summary for {video.id}: {e}")
        return False

    key_topics = summary_data.get("key_topics", [])
    if not key_topics:
        logger.warning(f"No key topics found for {video.id}")
        return False

    # Save summary JSON and create news items
    with get_session() as session:
        db_video = session.get(NewsVideo, video.id)
        if not db_video:
            return False

        db_video.summary_json = summary_data
        db_video.status = "summarized"
        db_video.processed_at = datetime.utcnow()

        for topic in key_topics:
            ts_range = topic.get("timestamp_range")
            ts_seconds = None
            if ts_range:
                parts = ts_range.split("-")
                if parts:
                    ts_seconds = _parse_timestamp_to_seconds(parts[0])

            facts = topic.get("facts", [])
            headline = facts[0] if facts else "Archaeological finding"
            # Truncate headline to fit DB column
            if len(headline) > 500:
                headline = headline[:497] + "..."

            summary_text = "\n".join(f"- {f}" for f in facts)

            # Extract primary site name if LLM provided one with high confidence
            site_name = None
            primary_site = topic.get("primary_site")
            if primary_site and isinstance(primary_site, dict):
                confidence = primary_site.get("confidence", "")
                if confidence == "high" and primary_site.get("name"):
                    site_name = primary_site["name"][:500]

            item = NewsItem(
                video_id=video.id,
                headline=headline,
                summary=summary_text,
                facts=facts,
                timestamp_range=ts_range,
                timestamp_seconds=ts_seconds,
                site_name_extracted=site_name,
            )
            session.add(item)

    logger.info(f"Summarized {video.id}: {len(key_topics)} topics")
    return True


def summarize_pending_videos(settings: LyraSettings) -> int:
    """Summarize all videos that have transcripts but no summaries yet.

    Returns number of videos summarized.
    """
    with get_session() as session:
        pending = session.query(NewsVideo).filter(
            NewsVideo.status == "transcribed"
        ).all()
        session.expunge_all()

    count = 0
    for video in pending:
        if summarize_video(video, settings):
            count += 1

    logger.info(f"Summarized {count}/{len(pending)} pending videos")
    return count
