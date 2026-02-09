"""Fact verification for generated posts using Claude AI."""

import json
import logging
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings, get_anthropic_client
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
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str | None = None,
) -> dict | None:
    """Verify a single post against the transcript.

    Returns verification result dict or None on failure.
    """
    if not item.post_text:
        return None

    # If no timestamp, use first 3000 chars of transcript as context
    if not item.timestamp_range:
        segment = transcript_text[:3000] if transcript_text else None
    else:
        segment = extract_transcript_segment(transcript_text, item.timestamp_range)
    if not segment:
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
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0.0,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": VERIFY_SCHEMA,
                },
            },
        )
    except anthropic.APIError as e:
        logger.warning(f"Verification API error for item {item.id}: {e}")
        return None

    return json.loads(response.content[0].text)


def verify_video_posts(
    video: NewsVideo, settings: LyraSettings, system_prompt: str | None = None,
) -> int:
    """Verify all posts for a video against its transcript.

    Applies modifications or clears rejected posts.
    Returns number of items verified.
    """
    if not video.transcript_text:
        return 0

    if not settings.anthropic_api_key:
        return 0

    client = get_anthropic_client(settings)
    if system_prompt is None:
        system_prompt = _load_prompt()

    with get_session() as session:
        items = session.query(NewsItem).filter(
            NewsItem.video_id == video.id,
            NewsItem.post_text.isnot(None),
        ).all()

        verified = 0
        for item in items:
            result = verify_single_post(item, video.transcript_text, client, settings.model_verify, system_prompt)
            if not result:
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
                    logger.info(f"Modified post for item {item.id}: {mod.get('changes_explained', '')}")

            # Update timestamp if verification found a more precise one
            ts = result.get("timestamp")
            if ts:
                secs = parse_timestamp_to_seconds(ts)
                if secs is not None:
                    item.timestamp_seconds = secs

            verified += 1

        # Transition video so it won't be re-verified next cycle
        v = session.get(NewsVideo, video.id)
        if v:
            v.status = "verified"

    logger.info(f"Verified {verified} posts for video {video.id}")
    return verified


def verify_pending_posts(settings: LyraSettings) -> int:
    """Verify posts for all videos in 'posted' status.

    Returns total number of items verified.
    """
    with get_session() as session:
        videos = session.query(NewsVideo).filter(
            NewsVideo.status == "posted"
        ).all()
        session.expunge_all()

    system_prompt = _load_prompt()
    total = 0
    for video in videos:
        total += verify_video_posts(video, settings, system_prompt)

    logger.info(f"Verified {total} posts total")
    return total
