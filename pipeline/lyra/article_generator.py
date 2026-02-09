"""Weekly article generation from video summaries."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anthropic

from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_session
from pipeline.lyra.config import LyraSettings, get_anthropic_client

logger = logging.getLogger(__name__)

HEADLINE_PROMPT_PATH = Path(__file__).parent / "prompts" / "headline.txt"
PARAGRAPH_PROMPT_PATH = Path(__file__).parent / "prompts" / "summary_paragraph.txt"
FACT_CHECK_PROMPT_PATH = Path(__file__).parent / "prompts" / "fact_check.txt"


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _get_week_range() -> tuple[datetime, datetime]:
    """Get the start (Monday) and end (Sunday) of the current week."""
    now = datetime.now(UTC)
    start = now - timedelta(days=now.weekday())  # Monday
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def _generate_paragraphs(
    videos: list[NewsVideo],
    client: anthropic.Anthropic,
    model: str,
    prompt_template: str | None = None,
) -> list[dict]:
    """Generate summary paragraphs for each video."""
    paragraphs = []
    if prompt_template is None:
        prompt_template = _load_prompt(PARAGRAPH_PROMPT_PATH)

    for video in videos:
        if not video.summary_json:
            continue

        summary_text = json.dumps(video.summary_json, indent=2)
        prompt = prompt_template.format(content=summary_text)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": "You are an archaeological news writer.",
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": prompt}],
            )
            paragraph = response.content[0].text.strip()
            paragraphs.append({
                "video_id": video.id,
                "title": video.title,
                "channel_name": video.channel.name if video.channel else "Unknown",
                "paragraph": paragraph,
            })
        except anthropic.APIError as e:
            logger.warning(f"Failed to generate paragraph for {video.id}: {e}")

    return paragraphs


def _fact_check_paragraph(
    paragraph: str,
    client: anthropic.Anthropic,
    model: str,
    prompt_template: str | None = None,
) -> str:
    """Fact-check a paragraph and return the verified version."""
    if prompt_template is None:
        prompt_template = _load_prompt(FACT_CHECK_PROMPT_PATH)
    prompt = prompt_template.format(paragraph=paragraph)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": "You are a fact-checking expert for archaeological content.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Extract verified paragraph
        match = re.search(r"\[START_VERIFIED\](.*?)\[END_VERIFIED\]", text, re.DOTALL)
        if match:
            return match.group(1).strip()
    except anthropic.APIError as e:
        logger.warning(f"Fact-check failed: {e}")

    return paragraph  # Return original if fact-check fails


def _generate_headline(
    content: str,
    client: anthropic.Anthropic,
    model: str,
    prompt_template: str | None = None,
) -> tuple[str, str, list[str]]:
    """Generate headline, TLDR, and subheadings."""
    if prompt_template is None:
        prompt_template = _load_prompt(HEADLINE_PROMPT_PATH)
    prompt = prompt_template.format(content=content)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": "You are an archaeological news editor.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Parse structured response
        headline = ""
        tldr = ""
        subheads: list[str] = []

        headline_match = re.search(r"\[HEADLINE\]\s*(.*?)(?:\n\n|\[TLDR\])", text, re.DOTALL)
        if headline_match:
            headline = headline_match.group(1).strip()

        tldr_match = re.search(r"\[TLDR\]\s*(.*?)(?:\n\n|\[SUBHEADS\])", text, re.DOTALL)
        if tldr_match:
            tldr = tldr_match.group(1).strip()

        subheads_match = re.search(r"\[SUBHEADS\]\s*(.*)", text, re.DOTALL)
        if subheads_match:
            for line in subheads_match.group(1).strip().split("\n"):
                line = re.sub(r"^\d+\.\s*", "", line.strip())
                if line:
                    subheads.append(line)

        return headline, tldr, subheads

    except anthropic.APIError as e:
        logger.warning(f"Headline generation failed: {e}")
        return "Weekly Archaeological Digest", "", []


def generate_weekly_article(settings: LyraSettings) -> bool:
    """Generate a weekly article from the past week's video summaries.

    Returns True if an article was created.
    """
    if not settings.anthropic_api_key:
        logger.error("No Anthropic API key configured")
        return False

    week_start, week_end = _get_week_range()

    # Check if article already exists for this week
    with get_session() as session:
        existing = session.query(NewsArticle).filter(
            NewsArticle.week_start == week_start,
        ).first()
        if existing:
            logger.info("Article for this week already exists")
            return False

    # Get summarized videos from this week
    with get_session() as session:
        videos = session.query(NewsVideo).filter(
            NewsVideo.published_at >= week_start,
            NewsVideo.published_at <= week_end,
            NewsVideo.status.in_(["summarized", "rescored"]),
            NewsVideo.summary_json.isnot(None),
        ).order_by(NewsVideo.published_at).all()

        if not videos:
            logger.info("No summarized videos this week for article")
            return False

        # Need to access relationships within session
        client = get_anthropic_client(settings)

        # Load prompts once
        paragraph_prompt = _load_prompt(PARAGRAPH_PROMPT_PATH)
        fact_check_prompt = _load_prompt(FACT_CHECK_PROMPT_PATH)
        headline_prompt = _load_prompt(HEADLINE_PROMPT_PATH)

        # Generate paragraphs for each video
        paragraphs = _generate_paragraphs(videos, client, settings.model_article, paragraph_prompt)

        if not paragraphs:
            return False

        # Fact-check each paragraph (skip empty ones to avoid wasting API calls)
        for para in paragraphs:
            if not para["paragraph"].strip():
                continue
            para["paragraph"] = _fact_check_paragraph(
                para["paragraph"], client, settings.model_verify, fact_check_prompt
            )

        # Build article content
        all_content = "\n\n".join(p["paragraph"] for p in paragraphs)

        # Generate headline and structure
        headline, tldr, subheads = _generate_headline(all_content, client, settings.model_article, headline_prompt)

        # Assemble final article markdown
        sections = []
        if tldr:
            sections.append(f"*{tldr}*\n")

        for i, para in enumerate(paragraphs):
            subhead = subheads[i] if i < len(subheads) else para["title"]
            source_line = f"*Source: {para['channel_name']}*"
            sections.append(f"## {subhead}\n\n{para['paragraph']}\n\n{source_line}")

        article_content = "\n\n---\n\n".join(sections)
        video_ids = [v.id for v in videos]

        # Save article
        article = NewsArticle(
            title=headline or "Weekly Archaeological Digest",
            content=article_content,
            summary=tldr,
            week_start=week_start,
            week_end=week_end,
            video_ids=video_ids,
            published_at=datetime.now(UTC),
        )
        session.add(article)

    logger.info(f"Generated weekly article: {headline}")
    return True


def should_generate_article() -> bool:
    """Check if it's time to generate a weekly article (Sunday evening)."""
    now = datetime.now(UTC)
    return now.weekday() == 6 and now.hour >= 20  # Sunday 8 PM UTC
