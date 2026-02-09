"""Re-score significance of news items using a dedicated Haiku call.

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
from pipeline.lyra.config import VALID_CATEGORIES, LyraSettings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "rescore_significance.txt"

RESCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "significance": {"type": "integer", "minimum": 1, "maximum": 10},
        "news_category": {
            "type": "string",
            "enum": sorted(VALID_CATEGORIES),
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
        logger.error("No Anthropic API key configured")
        return 0

    # Find verified videos that haven't been rescored yet
    with get_session() as session:
        videos = session.query(NewsVideo).filter(
            NewsVideo.status == "verified",
        ).all()
        session.expunge_all()

    if not videos:
        return 0

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)
    system_prompt = _load_prompt()
    total_rescored = 0

    for video in videos:
        with get_session() as session:
            items = session.query(NewsItem).filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.isnot(None),
            ).all()

            if not items:
                # No items to rescore — mark video as rescored
                v = session.get(NewsVideo, video.id)
                if v:
                    v.status = "rescored"
                continue

            # Load channel name
            channel_name = video.channel_id
            if video.channel:
                channel_name = video.channel.name
            else:
                from pipeline.database import NewsChannel
                ch = session.get(NewsChannel, video.channel_id)
                if ch:
                    channel_name = ch.name

            rescored_count = 0
            for item in items:
                result = _rescore_item(item, video, channel_name, client, system_prompt, settings)
                if result is None:
                    continue

                new_sig = max(1, min(10, result["significance"]))
                new_cat = result["news_category"]
                if new_cat not in VALID_CATEGORIES:
                    new_cat = "general"

                old_sig = item.significance
                item.significance = new_sig
                item.news_category = new_cat

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

            # Mark video as rescored
            v = session.get(NewsVideo, video.id)
            if v:
                v.status = "rescored"

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
    """Call Haiku to re-score a single item. Returns parsed result or None."""
    facts_text = "\n".join(f"- {f}" for f in (item.facts or []))

    user_content = (
        f"VIDEO: {video.title}\n"
        f"CHANNEL: {channel_name}\n"
        f"FACTS:\n{facts_text}\n"
        f"POST: {item.post_text}"
    )

    try:
        response = client.messages.create(
            model=settings.model_rescore,
            max_tokens=256,
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
                    "schema": RESCORE_SCHEMA,
                },
            },
        )
    except anthropic.APIError as e:
        logger.warning(f"Rescore API error for item {item.id}: {e}")
        return None

    return json.loads(response.content[0].text)
