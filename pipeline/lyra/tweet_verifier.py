"""Fact verification for generated posts using an LLM."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pipeline.database import NewsItem, NewsVideo, get_session
from pipeline.lyra.config import (
    LyraAPIError,
    LyraSettings,
    _get_settings,
    call_api,
)
from pipeline.lyra.transcript_fetcher import extract_transcript_segment, parse_timestamp_to_seconds

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "verify_tweets.txt"
WEB_VERIFY_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_web_verify.txt"

_DESC_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Correct spellings of site names, researcher names, culture names",
        },
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs to papers, articles, or references about the topic (not social media, merch, courses)",
        },
    },
    "required": ["names", "source_urls"],
    "additionalProperties": False,
}


def _extract_from_description(
    description: str, headline: str, settings: LyraSettings
) -> tuple[list[str], list[str]]:
    """Use LLM to extract correct names and source URLs from a YouTube description.

    Returns (names, source_urls).
    """
    try:
        response = call_api(
            model=settings.model_relevance,
            max_tokens=1024,
            temperature=0.0,
            system=(
                "Extract from this YouTube video description:\n"
                "1. Correct spellings of archaeological site names, researcher names, and culture names\n"
                "2. URLs that link to papers, news articles, or academic sources about the topic\n\n"
                "IGNORE: social media links, merch/shop links, course links, Patreon, "
                "subscribe prompts, affiliate links, hashtags, timestamps.\n"
                "Only extract names and URLs relevant to archaeology/history content."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Topic: {headline}\n\nDescription:\n{description[:1500]}",
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "DescriptionExtract",
                    "strict": True,
                    "schema": _DESC_EXTRACT_SCHEMA,
                },
            },
        )
    except LyraAPIError:
        return [], []

    text = response.text
    if not text:
        return [], []
    try:
        data = json.loads(text)
        # Double-encoded string fallback
        if isinstance(data.get("names"), str):
            data["names"] = json.loads(data["names"])
        if isinstance(data.get("source_urls"), str):
            data["source_urls"] = json.loads(data["source_urls"])
        return data.get("names", []), data.get("source_urls", [])
    except (json.JSONDecodeError, ValueError):
        return [], []


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
    model: str,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    video_title: str | None = None,
    video_tags: list[str] | None = None,
    desc_names: list[str] | None = None,
) -> dict | None:
    """Verify a single post against the transcript.

    Returns verification result dict or None on failure.
    """
    if not item.post_text:
        return {"verification_level": "SKIP", "reason": "no_post_text"}

    # Extract transcript around the timestamp, fall back to start of transcript
    if item.timestamp_range:
        segment = extract_transcript_segment(transcript_text, item.timestamp_range)
    else:
        segment = None
    if not segment and transcript_text:
        segment = transcript_text[:3000]
    if not segment:
        logger.warning(f"Item {item.id}: no transcript segment, marking as unverifiable")
        return {"verification_level": "SKIP", "reason": "no_transcript_segment"}

    if system_prompt is None:
        system_prompt = _load_prompt()

    # Build context with video metadata for proper noun checking
    metadata_lines = []
    if video_title:
        metadata_lines.append(f"Video title: {video_title}")
    if video_tags:
        metadata_lines.append(f"Video tags: {', '.join(t for t in video_tags if t)}")
    if desc_names:
        metadata_lines.append(f"Correct names from description: {', '.join(desc_names)}")
    metadata_block = "\n".join(metadata_lines)

    ts_label = item.timestamp_range or "start of video"
    user_content = (
        f"Tweet to verify:\n{item.post_text}\n\n"
        f"{metadata_block}\n\n"
        f"Relevant transcript segment (roughly from {ts_label}):\n"
        f"<transcript_segment>\n{segment}\n</transcript_segment>"
    )

    try:
        _max_tokens = max_tokens if max_tokens is not None else _get_settings().max_tokens
        response = call_api(
            model=model,
            max_tokens=_max_tokens,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "FactVerification",
                    "strict": True,
                    "schema": VERIFY_SCHEMA,
                },
            },
        )
    except LyraAPIError as e:
        logger.warning(f"Verification API error for item {item.id}: {e}")
        return None

    text_block = response.text or None
    if not text_block:
        logger.warning(f"Empty verification response for item {item.id}")
        return None
    try:
        return json.loads(text_block)
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse verification result for item %s", item.id)
        return None


def verify_video_posts(
    video: NewsVideo,
    settings: LyraSettings,
    system_prompt: str | None = None,
) -> int:
    """Verify all posts for a video against its transcript.

    Applies modifications or clears rejected posts.
    Returns number of items verified.
    """
    if not video.transcript_text:
        return 0

    if not settings.anthropic_api_key:
        return 0
    if system_prompt is None:
        system_prompt = _load_prompt()

    with get_session() as session:
        items = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.isnot(None),
                NewsItem.verified_at.is_(None),
            )
            .all()
        )

        if not items:
            # All items already verified — transition the video if needed
            v = session.get(NewsVideo, video.id)
            if v and v.status == "posted":
                v.status = "verified"
                logger.info(
                    f"Video {video.id}: all items already verified, transitioning to 'verified'"
                )
            return 0

        # Extract names + source URLs from description once per video
        desc_names: list[str] = []
        desc_source_urls: list[str] = []
        if video.description:
            desc_names, desc_source_urls = _extract_from_description(
                video.description, video.title or "", settings
            )

        verified = 0
        skipped = 0
        for item in items:
            result = verify_single_post(
                item,
                video.transcript_text,
                settings.model_verify,
                system_prompt,
                max_tokens=settings.max_tokens,
                video_title=video.title,
                video_tags=video.tags,
                desc_names=desc_names,
            )
            if not result:
                skipped += 1
                continue

            level = result.get("verification_level", "")

            if level == "SKIP":
                # Deterministic failure — mark verified to prevent infinite retry
                item.verified_at = datetime.now(UTC)
                logger.info(f"Auto-verified item {item.id}: {result.get('reason', 'unverifiable')}")
                verified += 1
                continue

            if level == "REJECT":
                item.news_category = "unverified"
                item.significance = 1
                logger.info(f"Unverified item {item.id} (claims not supported by transcript)")
            elif level == "MODIFY":
                mod = result.get("suggested_modification", {})
                modified = mod.get("modified_text", "") if mod else ""
                if modified:
                    # Extract name corrections by comparing old and new text
                    # Apply them to headline, facts, and summary too
                    old_text = item.post_text or ""
                    item.post_text = modified

                    # Find words that changed between old and new post_text
                    old_words = set(old_text.split())
                    new_words = set(modified.split())
                    # Look for capitalized words that appeared in new but not old
                    for new_w in new_words - old_words:
                        if not new_w[0].isupper() or len(new_w) < 3:
                            continue
                        # Find the old word it likely replaced (same prefix)
                        for old_w in old_words - new_words:
                            if not old_w[0].isupper() or len(old_w) < 3:
                                continue
                            # Simple heuristic: first 3 chars match = likely same name
                            if old_w[:3].lower() == new_w[:3].lower() and old_w != new_w:
                                if item.headline:
                                    item.headline = item.headline.replace(old_w, new_w)
                                if item.summary:
                                    item.summary = item.summary.replace(old_w, new_w)
                                if item.facts:
                                    item.facts = [
                                        f.replace(old_w, new_w) if isinstance(f, str) else f
                                        for f in item.facts
                                    ]
                                logger.info(f"Name fix in item {item.id}: {old_w} -> {new_w}")

                    logger.info(
                        f"Modified post for item {item.id}: {mod.get('changes_explained', '')}"
                    )

            # Update timestamp if verification found a more precise one
            ts = result.get("timestamp")
            if ts:
                secs = parse_timestamp_to_seconds(ts)
                if secs is not None:
                    item.timestamp_seconds = secs

            # Save description source URLs (deduped with any existing web sources)
            if desc_source_urls:
                existing = item.web_sources or []
                seen = {s["url"] for s in existing if isinstance(s, dict)}
                for url in desc_source_urls:
                    if url not in seen:
                        from urllib.parse import urlparse

                        domain = urlparse(url).netloc.replace("www.", "")
                        existing.append(
                            {"title": domain, "url": url, "snippet": "Linked in video description"}
                        )
                        seen.add(url)
                item.web_sources = existing

            item.verified_at = datetime.now(UTC)
            verified += 1

        session.flush()

        # Count remaining unverified items for this video
        remaining = (
            session.query(NewsItem)
            .filter(
                NewsItem.video_id == video.id,
                NewsItem.post_text.isnot(None),
                NewsItem.verified_at.is_(None),
            )
            .count()
        )

        v = session.get(NewsVideo, video.id)
        if v:
            if remaining == 0:
                v.status = "verified"
            else:
                logger.warning(
                    f"Video {video.id}: {remaining} items still unverified, keeping 'posted' for retry"
                )

    logger.info(f"Verified {verified}/{len(items)} posts for video {video.id} ({skipped} skipped)")
    return verified


def _web_verify_items(items: list[NewsItem], settings: LyraSettings) -> int:
    """Web fact-check high-significance items using MiniMax search.

    Only processes items with significance >= story_web_verify_min_significance.
    Returns number of items web-checked.
    """
    min_sig = getattr(settings, "story_web_verify_min_significance", 5)
    if min_sig <= 0:
        return 0

    eligible = [i for i in items if i.significance and i.significance >= min_sig and i.post_text]
    if not eligible:
        return 0

    try:
        from pipeline.lyra.minimax_shared import (
            create_minimax_client,
            minimax_chat,
            minimax_search,
        )
    except ImportError:
        logger.warning("MiniMax shared module not available, skipping web verification")
        return 0

    if not settings.minimax_api_key:
        return 0

    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)
    web_prompt = WEB_VERIFY_PROMPT_PATH.read_text(encoding="utf-8")
    checked = 0

    for item in eligible:
        # Use post_text (truncated to 150 chars) — has specific names, dates, details
        # Full post_text is too long for search; headline alone is too vague
        query = (item.post_text or item.headline or "")[:150]
        results = minimax_search(client, query)
        if not results:
            continue

        # Filter blocked domains
        from urllib.parse import urlparse

        from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS

        results = [
            r for r in results if urlparse(r.url).netloc.replace("www.", "") not in BLOCKED_DOMAINS
        ]
        if not results:
            continue

        # Save web search sources IMMEDIATELY — don't wait for LLM verdict
        existing = item.web_sources or []
        seen = {s["url"] for s in existing if isinstance(s, dict)}
        for r in results[:5]:
            if r.url not in seen:
                existing.append({"title": r.title, "url": r.url, "snippet": r.snippet})
                seen.add(r.url)
        item.web_sources = existing

        search_text = "\n".join(f"- [{r.title}]({r.url}): {r.snippet}" for r in results[:5])
        facts_text = "\n".join(f"- {f}" for f in (item.facts or [])[:5])

        user_msg = (
            f"Post: {item.post_text or ''}\n\n"
            f"Key facts claimed:\n{facts_text}\n\n"
            f"Web search results:\n{search_text}"
        )

        try:
            response_text = minimax_chat(client, "MiniMax-M2.7", web_prompt, user_msg, 4096)
        except Exception as e:
            logger.warning(f"Web verify failed for item {item.id}: {e}")
            checked += 1
            continue

        if not response_text:
            checked += 1
            continue

        # Parse JSON — handle markdown fencing
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            result = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse web verify response for item {item.id}")
            checked += 1
            continue

        if not isinstance(result, dict):
            logger.warning(
                f"Web verify returned {type(result).__name__} for item {item.id}, skipping"
            )
            checked += 1
            continue

        verdict = result.get("verdict", "")

        if verdict == "CORRECTED" and result.get("corrected_text"):
            logger.info(f"Web verify corrected item {item.id}: {result.get('reason', '')}")
            item.post_text = result["corrected_text"]
        elif verdict == "REJECT":
            logger.info(f"Web verify unverified item {item.id}: {result.get('reason', '')}")
            item.news_category = "unverified"
            item.significance = 1
        checked += 1

    if checked:
        logger.info(f"Web-verified {checked} high-significance items")
    return checked


def verify_pending_posts(settings: LyraSettings) -> int:
    """Verify posts for all videos in 'posted' status.

    Returns total number of items verified.
    """
    with get_session() as session:
        videos = session.query(NewsVideo).filter(NewsVideo.status == "posted").all()
        session.expunge_all()

    system_prompt = _load_prompt()
    total = 0
    for video in videos:
        try:
            total += verify_video_posts(video, settings, system_prompt)
        except Exception:
            logger.exception(f"Failed to verify video {video.id}, skipping")

    logger.info(f"Verified {total} posts total")
    return total
