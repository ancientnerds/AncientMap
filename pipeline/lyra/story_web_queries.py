"""Web query generator for news item web verification stage.

Calls MiniMax M3 with a news item's post_text + facts and returns 3-5 short
concrete web search queries used downstream to find authoritative sources.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Single canonical query-list parser shared with the angle image stage
# (identical copy lived here until audit P7-17).
from pipeline.lyra.angle_image_queries import parse_queries

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_web_queries.txt"


def generate_queries_for_item(
    post_text: str,
    facts: list[str],
    settings,
) -> list[str]:
    """Ask the LLM for web search queries for one news item.

    Returns an empty list on failure rather than raising, so the caller can
    fall back to the raw post_text query.
    """
    from pipeline.lyra.minimax_shared import minimax_chat_anthropic

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    facts_text = "\n".join(f"- {f}" for f in (facts or [])[:5])
    user_msg = f"## News item facts\n{facts_text}\n\n## Post text\n{post_text[:300]}\n"
    raw = minimax_chat_anthropic(
        system,
        user_msg,
        1024,
        settings,
        temperature=0.2,
    )
    queries = parse_queries(raw)
    if not queries:
        logger.warning(
            "story_web_queries: parse_queries returned empty for post_text '%s...'",
            post_text[:60],
        )
    return queries
