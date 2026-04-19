"""Web query generator for news item web verification stage.

Calls MiniMax M2.7 with a news item's post_text + facts and returns 3-5 short
concrete web search queries used downstream to find authoritative sources.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_web_queries.txt"

_MAX_QUERIES = 5
_MAX_QUERY_LEN = 80


def parse_queries(raw: str) -> list[str]:
    """Parse the generator's JSON output into a deduplicated, capped list.

    Filters empty strings and anything longer than 80 chars. Preserves the
    input order. Caps at 5 queries. Returns [] on any parse failure.
    """
    if not raw or not raw.strip():
        return []
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return []
    raw_queries = data.get("queries")
    if not isinstance(raw_queries, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for q in raw_queries:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or len(q) > _MAX_QUERY_LEN:
            continue
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= _MAX_QUERIES:
            break
    return out


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
