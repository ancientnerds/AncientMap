"""Generate news feed posts from video summaries using an LLM."""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    LyraAPIError,
    LyraSettings,
    call_api,
)

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
    video: NewsVideo,
    settings: LyraSettings,
    system_prompt: str | None = None,
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
        item_count = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.is_(None),
            )
            .count()
        )
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
        pub = (
            video.published_at.replace(tzinfo=UTC)
            if video.published_at.tzinfo is None
            else video.published_at
        )
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

    try:
        response = call_api(
            model=settings.model_post,
            max_tokens=settings.max_tokens,
            temperature=0.3,
            reasoning_effort="low",
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "NewsPosts",
                    "strict": True,
                    "schema": POSTS_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.error(f"Post generation API error for {video.id}: {e}")
        return 0

    text_block = response.text or None
    if not text_block:
        logger.warning(f"Empty response content for {video.id}")
        return 0
    try:
        posts_data = json.loads(text_block).get("posts", [])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse post generation JSON for {video.id}: {e}")
        return 0

    with get_session() as session:
        db_video = session.get(NewsVideo, video.id)
        if not db_video:
            return 0

        # Match posts to existing news items by headline
        items = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.is_(None),
            )
            .all()
        )

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

        def _normalize_headline(h: str) -> str:
            """Strip punctuation and extra spaces for fuzzy headline matching."""
            return re.sub(r"[^a-z0-9 ]", "", h.lower()).strip()

        matched_by_headline = 0
        matched_by_position = 0
        unmatched = 0
        fallback_idx = 0
        count = 0
        for post_data in posts_data:
            if not isinstance(post_data, dict):
                logger.warning(f"Malformed post data: {type(post_data).__name__}, skipping")
                continue
            post_text = post_data.get("tweet", "")
            headline = post_data.get("headline", "")
            ts_range = post_data.get("timestamp_range")

            if not post_text:
                continue

            # Primary: exact headline match
            key = headline.strip().lower()
            item = headline_to_item.pop(key, None)

            # Secondary: normalized headline match (strip punctuation)
            if item is None and headline:
                norm_key = _normalize_headline(headline)
                for db_key, db_item in list(headline_to_item.items()):
                    if _normalize_headline(db_key) == norm_key:
                        item = headline_to_item.pop(db_key)
                        break

            if item is not None:
                matched_by_headline += 1
            else:
                # Fallback: match by position if headline didn't match
                while (
                    fallback_idx < len(items_by_order)
                    and items_by_order[fallback_idx].post_text is not None
                ):
                    fallback_idx += 1
                if fallback_idx < len(items_by_order):
                    item = items_by_order[fallback_idx]
                    fallback_idx += 1
                    matched_by_position += 1
                    logger.info(
                        f"Headline mismatch, matched by position: {headline!r} → item {item.id}"
                    )
                else:
                    unmatched += 1
                    logger.warning(f"No matching item for headline: {headline!r}")
                    continue

            # Strip any hashtags the LLM sneaks in despite the prompt
            post_text = re.sub(r"#\w+", "", post_text).strip()
            # Strip timestamp ranges the LLM includes in the text (e.g. "(08:58-11:48)")
            post_text = re.sub(r"\s*\(\d{1,2}:\d{2}\s*[-–—]\s*\d{1,2}:\d{2}\)", "", post_text)
            post_text = re.sub(r"  +", " ", post_text)
            item.post_text = post_text
            if ts_range:
                item.timestamp_range = ts_range
            # NULL significance signals "not yet scored" — the rescorer
            # fills it after the verify step.  Using 3 as a placeholder
            # caused infinite rescore loops (startup migration mistook
            # legitimately-scored-3 items for unscored ones).
            item.significance = None
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
        pending = session.query(NewsVideo).filter(NewsVideo.status == "summarized").all()
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
