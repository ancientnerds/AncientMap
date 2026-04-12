"""Re-score significance of news items using a dedicated LLM call.

Runs after the verify step. Each item gets an independent significance score
based on full video context (title, channel, facts, post text), not just
the tweet the LLM wrote. Items scored 1 (not archaeology) have their
post_text set to NULL, removing them from the feed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline.database import NewsChannel, NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    VALID_CATEGORIES,
    VALID_SPECULATIVE_TAGS,
    LyraAPIError,
    LyraSettings,
    call_api,
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
            "anyOf": [
                {"type": "string", "enum": sorted(VALID_SPECULATIVE_TAGS)},
                {"type": "null"},
            ],
        },
        "reason": {"type": "string"},
        "entities": {
            "type": "object",
            "properties": {
                "sites": {"type": "array", "items": {"type": "string"}},
                "people": {"type": "array", "items": {"type": "string"}},
                "cultures": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["sites", "people", "cultures"],
            "additionalProperties": False,
        },
    },
    "required": ["significance", "news_category", "speculative_tag", "reason", "entities"],
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

    system_prompt = _load_prompt()
    total_rescored = 0

    for video in videos:
        with get_session() as session:
            items = (
                session.query(NewsItem)
                .filter(
                    NewsItem.video_id == video.id,
                    NewsItem.post_text.isnot(None),
                    NewsItem.significance.is_(None),  # Skip already-rescored items
                )
                .all()
            )

            if not items:
                # All items already rescored (or none to score) — transition video
                v = session.get(NewsVideo, video.id)
                if v:
                    v.status = "rescored"
                    logger.info(
                        f"Video {video.id}: all items already rescored, transitioning to 'rescored'"
                    )
                continue

            # Load channel name (video is detached, so query directly)
            ch = session.get(NewsChannel, video.channel_id)
            channel_name = ch.name if ch else video.channel_id

            rescored_count = 0
            skipped = 0
            for item in items:
                result = _rescore_item(item, video, channel_name, system_prompt, settings)
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

                # Save editorial judgment
                item.score_reason = result.get("reason")

                # Save extracted entities and tags
                entities = result.get("entities")
                if entities and isinstance(entities, dict):
                    item.entities = entities
                if new_sig == 1:
                    logger.info(
                        f"Rescore item {item.id}: {old_sig} -> 1 (flagged) — {result['reason']}"
                    )
                elif old_sig != new_sig:
                    logger.info(
                        f"Rescore item {item.id}: {old_sig} -> {new_sig} [{new_cat}] — {result['reason']}"
                    )

                rescored_count += 1

            # Web fact-check high-significance items (now that significance is set)
            # Wrapped in try/except so web verify failures can't roll back rescore writes
            try:
                from pipeline.lyra.tweet_verifier import _web_verify_items

                _web_verify_items(items, settings)
            except Exception:
                logger.exception(
                    f"Web verify failed for video {video.id}, rescore writes preserved"
                )

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
            model=settings.model_rescore,
            max_tokens=settings.max_tokens,
            temperature=0.0,
            reasoning_effort="low",
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "SignificanceScore",
                    "strict": True,
                    "schema": RESCORE_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.warning(f"Rescore API error for item {item.id}: {e}")
        return None

    text_block = response.text or None
    if not text_block:
        logger.warning(
            f"Empty rescore response for item {item.id}: "
            f"stop_reason={response.stop_reason}, "
            f"blocks={[type(b).__name__ for b in response.content]}"
        )
        return None
    try:
        return json.loads(text_block)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Bad rescore JSON for item {item.id}: {e}")
        return None
