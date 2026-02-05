"""Fact verification for generated posts using Claude AI."""

import json
import logging
import re
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.transcript_fetcher import extract_transcript_segment

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "verify_tweets.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def verify_single_post(
    item: NewsItem,
    transcript_text: str,
    client: anthropic.Anthropic,
    model: str,
) -> dict | None:
    """Verify a single post against the transcript.

    Returns verification result dict or None on failure.
    """
    if not item.post_text or not item.timestamp_range:
        return None

    segment = extract_transcript_segment(transcript_text, item.timestamp_range)
    if not segment:
        return None

    prompt_template = _load_prompt()
    prompt = prompt_template.format(
        tweet_content=item.post_text,
        timestamp=item.timestamp_range,
        transcript_segment=segment,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.warning(f"Verification API error for item {item.id}: {e}")
        return None

    response_text = response.content[0].text

    # Parse JSON response
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not json_match:
        return None

    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return None


def _parse_timestamp_to_seconds(ts: str) -> int | None:
    """Parse 'MM:SS' to seconds."""
    m = re.match(r"(\d+):(\d{2})", ts.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def verify_video_posts(video: NewsVideo, settings: LyraSettings) -> int:
    """Verify all posts for a video against its transcript.

    Applies modifications or clears rejected posts.
    Returns number of items verified.
    """
    if not video.transcript_text:
        return 0

    if not settings.anthropic_api_key:
        return 0

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with get_session() as session:
        items = session.query(NewsItem).filter(
            NewsItem.video_id == video.id,
            NewsItem.post_text.isnot(None),
        ).all()

        verified = 0
        for item in items:
            result = verify_single_post(item, video.transcript_text, client, settings.model_verify)
            if not result:
                continue

            level = result.get("verification_level", "")

            if level == "REJECT":
                session.delete(item)
                logger.info(f"Rejected and deleted item {item.id}")
            elif level == "MODIFY":
                mod = result.get("suggested_modification", {})
                modified = mod.get("modified_text", "") if mod else ""
                if modified and len(modified) <= 280:
                    item.post_text = modified
                    logger.info(f"Modified post for item {item.id}: {mod.get('changes_explained', '')}")
                elif modified:
                    logger.warning(f"Discarded modification for item {item.id}: {len(modified)} chars exceeds 280 limit")

            # Update timestamp if verification found a more precise one
            ts = result.get("timestamp")
            if ts:
                secs = _parse_timestamp_to_seconds(ts)
                if secs is not None:
                    item.timestamp_seconds = secs

            verified += 1

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

    total = 0
    for video in videos:
        total += verify_video_posts(video, settings)

    logger.info(f"Verified {total} posts total")
    return total
