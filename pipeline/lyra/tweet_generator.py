"""Generate news feed posts from video summaries using Claude AI."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "tweet_template.txt"

VALID_CATEGORIES = {
    "excavation", "artifact", "architecture", "bioarchaeology", "dating",
    "remote_sensing", "underwater", "epigraphy", "conservation", "heritage",
    "theory", "technology", "survey", "art", "general",
}


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _format_attribution(video_id: str, channel_name: str, timestamp: str | None) -> str:
    """Format the attribution line for a post."""
    ts_part = f" at {timestamp}'" if timestamp else ""
    return f"\n\nvia {channel_name}{ts_part}"


def generate_posts_for_video(video: NewsVideo, settings: LyraSettings) -> int:
    """Generate post text for each news item of a summarized video.

    Returns number of posts generated.
    """
    if not video.summary_json:
        return 0

    if not settings.anthropic_api_key:
        logger.error("No Anthropic API key configured")
        return 0

    summary_text = json.dumps(video.summary_json, indent=2)
    prompt_template = _load_prompt()

    now = datetime.utcnow()
    time_instruction = ""
    if video.published_at:
        days_ago = (now - video.published_at).days
        if days_ago == 0:
            time_instruction = "This content was published today."
        elif days_ago == 1:
            time_instruction = "This content was published yesterday."
        else:
            time_instruction = f"This content was published {days_ago} days ago."

    prompt = prompt_template.format(
        current_date=now.strftime("%Y-%m-%d"),
        time_instruction=time_instruction,
        summary=summary_text,
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.model_post,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error(f"Post generation API error for {video.id}: {e}")
        return 0

    response_text = response.content[0].text

    # Extract JSON array from response
    json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if not json_match:
        logger.warning(f"No JSON array in post response for {video.id}")
        return 0

    try:
        posts_data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in post response for {video.id}: {e}")
        return 0

    if not isinstance(posts_data, list):
        return 0

    with get_session() as session:
        db_video = session.get(NewsVideo, video.id)
        if not db_video:
            return 0

        # Match posts to existing news items
        items = session.query(NewsItem).filter(
            NewsItem.video_id == video.id,
            NewsItem.post_text.is_(None),
        ).order_by(NewsItem.id).all()

        count = 0
        for i, post_data in enumerate(posts_data):
            post_text = post_data.get("tweet", "")
            ts_range = post_data.get("timestamp_range")

            if not post_text:
                continue

            # Validate significance and category
            sig = post_data.get("significance")
            cat = post_data.get("category", "general")

            # Match to a news item if possible
            if i < len(items):
                items[i].post_text = post_text
                if ts_range:
                    items[i].timestamp_range = ts_range
                items[i].significance = max(1, min(10, int(sig))) if sig is not None else 3
                items[i].news_category = cat if cat in VALID_CATEGORIES else "general"
                count += 1

        db_video.status = "posted"

    logger.info(f"Generated {count} posts for video {video.id}")
    return count


def generate_pending_posts(settings: LyraSettings) -> int:
    """Generate posts for all summarized videos that don't have posts yet.

    Returns number of posts generated.
    """
    with get_session() as session:
        pending = session.query(NewsVideo).filter(
            NewsVideo.status == "summarized"
        ).all()
        session.expunge_all()

    total = 0
    for video in pending:
        total += generate_posts_for_video(video, settings)

    logger.info(f"Generated {total} posts total")
    return total
