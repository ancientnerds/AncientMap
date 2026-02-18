"""Generate news feed posts from video summaries using an LLM."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings, call_api, get_anthropic_client, parse_prefilled_json

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "tweet_template.txt"

POSTS_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "tweet": {"type": "string"},
                    "timestamp_range": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                    },
                },
                "required": ["headline", "tweet", "timestamp_range"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def generate_posts_for_video(
    video: NewsVideo, settings: LyraSettings, system_prompt: str | None = None,
) -> int:
    """Generate post text for each news item of a summarized video.

    Returns number of posts generated.
    """
    if not video.summary_json:
        return 0

    if not settings.anthropic_api_key:
        logger.error("No LLM API key configured")
        return 0

    # Check if there are items to attach posts to BEFORE calling the API
    with get_session() as session:
        item_count = session.query(NewsItem).filter(
            NewsItem.video_id == video.id,
            NewsItem.post_text.is_(None),
        ).count()
    if item_count == 0:
        logger.info(f"Video {video.id}: no DB items awaiting text — skipping API call")
        with get_session() as session:
            v = session.get(NewsVideo, video.id)
            if v:
                v.status = "posted"
        return 0

    summary_text = json.dumps(video.summary_json, indent=2)
    if system_prompt is None:
        system_prompt = _load_prompt()

    now = datetime.now(UTC)
    time_instruction = ""
    if video.published_at:
        # published_at is stored as naive UTC in the DB
        pub = video.published_at.replace(tzinfo=UTC) if video.published_at.tzinfo is None else video.published_at
        days_ago = (now - pub).days
        if days_ago == 0:
            time_instruction = "This content was published today."
        elif days_ago == 1:
            time_instruction = "This content was published yesterday."
        else:
            time_instruction = f"This content was published {days_ago} days ago."

    user_content = (
        f"Today's date: {now.strftime('%Y-%m-%d')}\n"
        f"{time_instruction}\n\n"
        f"Source Material:\n{summary_text}"
    )

    client = get_anthropic_client(settings)

    try:
        response = call_api(
            client,
            model=settings.model_post,
            max_tokens=4096,
            temperature=0.3,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": POSTS_SCHEMA,
                },
            },
            prefill="{",
        )
    except anthropic.APIError as e:
        logger.error(f"Post generation API error for {video.id}: {e}")
        return 0

    text_block = next((b.text for b in response.content if hasattr(b, "text")), None)
    if not text_block:
        logger.warning(f"Empty response content for {video.id}")
        return 0
    try:
        posts_data = parse_prefilled_json(text_block).get("posts", [])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse post generation JSON for {video.id}: {e}")
        return 0


    with get_session() as session:
        db_video = session.get(NewsVideo, video.id)
        if not db_video:
            return 0

        # Match posts to existing news items by headline
        items = session.query(NewsItem).filter(
            NewsItem.video_id == video.id,
            NewsItem.post_text.is_(None),
        ).all()

        logger.info(
            f"Video {video.id}: {len(posts_data)} LLM posts, {len(items)} DB items awaiting text"
        )
        if not items:
            logger.warning(f"Video {video.id}: no DB items to attach posts to — skipping")
            db_video.status = "posted"
            return 0

        # Build headline -> item lookup (normalized lowercase for matching)
        headline_to_item: dict[str, NewsItem] = {}
        items_by_order: list[NewsItem] = []  # Fallback: match by position
        for item in items:
            if item.headline:
                headline_to_item[item.headline.strip().lower()] = item
            items_by_order.append(item)

        matched_by_headline = 0
        matched_by_position = 0
        unmatched = 0
        fallback_idx = 0
        count = 0
        for post_data in posts_data:
            post_text = post_data.get("tweet", "")
            headline = post_data.get("headline", "")
            ts_range = post_data.get("timestamp_range")

            if not post_text:
                continue

            # Primary: match by headline
            key = headline.strip().lower()
            item = headline_to_item.pop(key, None)

            if item is not None:
                matched_by_headline += 1
            else:
                # Fallback: match by position if headline didn't match
                while fallback_idx < len(items_by_order) and items_by_order[fallback_idx].post_text is not None:
                    fallback_idx += 1
                if fallback_idx < len(items_by_order):
                    item = items_by_order[fallback_idx]
                    fallback_idx += 1
                    matched_by_position += 1
                    logger.info(f"Headline mismatch, matched by position: {headline!r} → item {item.id}")
                else:
                    unmatched += 1
                    logger.warning(f"No matching item for headline: {headline!r}")
                    continue

            item.post_text = post_text
            if ts_range:
                item.timestamp_range = ts_range
            # Placeholders — rescorer overwrites both after the verify step
            item.significance = 3
            item.news_category = "general"
            count += 1

        db_video.status = "posted"

    logger.info(
        f"Video {video.id}: {count} posts written "
        f"(headline={matched_by_headline}, position={matched_by_position}, dropped={unmatched})"
    )
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

    system_prompt = _load_prompt()
    total = 0
    for video in pending:
        try:
            total += generate_posts_for_video(video, settings, system_prompt)
        except Exception:
            logger.exception(f"Failed to generate posts for video {video.id}, skipping")

    logger.info(f"Generated {total} posts total")
    return total
