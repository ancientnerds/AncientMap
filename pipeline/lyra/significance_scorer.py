"""Re-score significance of news items using a dedicated LLM call.

Runs after the verify step. Each item gets an independent significance score
based on full video context (title, channel, facts, post text), not just
the tweet the LLM wrote. Items scored 1 (not archaeology) have their
post_text set to NULL, removing them from the feed.
"""

import json
import logging
from pathlib import Path

import anthropic

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    VALID_CATEGORIES,
    VALID_SPECULATIVE_TAGS,
    LyraSettings,
    call_api,
    get_anthropic_client,
    parse_prefilled_json,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "rescore_significance.txt"

RESCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "significance": {"type": "integer"},
        "news_category": {
            "type": "string",
            "enum": sorted(VALID_CATEGORIES),
        },
        "speculative_tag": {
            "type": "string",
            "enum": sorted(VALID_SPECULATIVE_TAGS),
        },
        "reason": {"type": "string"},
    },
    "required": ["significance", "news_category", "reason"],
    "additionalProperties": False,
}


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def rescore_pending_items(settings: LyraSettings) -> int:
    """Re-score significance for items from verified videos that haven't been rescored.

    Returns number of items rescored.
    """
    if not settings.anthropic_api_key:
        logger.error("No LLM API key configured")
        return 0

    # Find verified videos that haven't been rescored yet
    with get_session() as session:
        videos = (
            session.query(NewsVideo)
            .filter(
                NewsVideo.status == "verified",
            )
            .all()
        )
        session.expunge_all()

    if not videos:
        return 0

    client = get_anthropic_client(settings)
    system_prompt = _load_prompt()
    total_rescored = 0

    for video in videos:
        with get_session() as session:
            items = (
                session.query(NewsItem)
                .filter(
                    NewsItem.video_id == video.id,
                    NewsItem.post_text.isnot(None),
                )
                .all()
            )

            if not items:
                # No items to rescore — mark video as rescored
                v = session.get(NewsVideo, video.id)
                if v:
                    v.status = "rescored"
                continue

            # Load channel name (video is detached, so query directly)
            from pipeline.database import NewsChannel

            ch = session.get(NewsChannel, video.channel_id)
            channel_name = ch.name if ch else video.channel_id

            rescored_count = 0
            skipped = 0
            for item in items:
                result = _rescore_item(item, video, channel_name, client, system_prompt, settings)
                if result is None:
                    skipped += 1
                    continue

                new_sig = max(1, min(10, result["significance"]))
                new_cat = result["news_category"]
                if new_cat not in VALID_CATEGORIES:
                    new_cat = "general"

                old_sig = item.significance
                item.significance = new_sig
                item.news_category = new_cat

                # Save speculative subcategory tag (only when category is speculative)
                if new_cat == "speculative":
                    tag = result.get("speculative_tag")
                    item.speculative_tag = tag if tag in VALID_SPECULATIVE_TAGS else None
                else:
                    item.speculative_tag = None

                if new_sig == 1:
                    # Not archaeology — remove from feed
                    item.post_text = None
                    logger.info(
                        f"Rescore item {item.id}: {old_sig} -> 1 (removed) — {result['reason']}"
                    )
                elif old_sig != new_sig:
                    logger.info(
                        f"Rescore item {item.id}: {old_sig} -> {new_sig} [{new_cat}] — {result['reason']}"
                    )

                rescored_count += 1

            # Only transition if all items were processed
            v = session.get(NewsVideo, video.id)
            if v:
                if skipped == 0:
                    v.status = "rescored"
                else:
                    logger.warning(
                        f"Video {video.id}: {skipped} items skipped, keeping 'verified' for retry"
                    )

            total_rescored += rescored_count

    logger.info(f"Re-scored {total_rescored} items from {len(videos)} videos")
    return total_rescored


def _rescore_item(
    item: NewsItem,
    video: NewsVideo,
    channel_name: str,
    client: anthropic.Anthropic,
    system_prompt: str,
    settings: LyraSettings,
) -> dict | None:
    """Call the LLM to re-score a single item. Returns parsed result or None."""
    facts_text = "\n".join(f"- {f}" for f in (item.facts or []))

    pub_date = video.published_at.strftime("%Y-%m-%d") if video.published_at else "Unknown"

    user_content = (
        f"VIDEO: {video.title}\n"
        f"CHANNEL: {channel_name}\n"
        f"PUBLISHED: {pub_date}\n"
        f"FACTS:\n{facts_text}\n"
        f"POST: {item.post_text}"
    )

    try:
        response = call_api(
            client,
            model=settings.model_rescore,
            max_tokens=settings.max_tokens,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": RESCORE_SCHEMA,
                },
            },
            prefill="{",
        )
    except anthropic.APIError as e:
        logger.warning(f"Rescore API error for item {item.id}: {e}")
        return None

    text_block = next((b.text for b in response.content if hasattr(b, "text")), None)
    if not text_block:
        logger.warning(
            f"Empty rescore response for item {item.id}: "
            f"stop_reason={response.stop_reason}, "
            f"blocks={[type(b).__name__ for b in response.content]}"
        )
        return None
    try:
        return parse_prefilled_json(text_block)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Bad rescore JSON for item {item.id}: {e}")
        return None
