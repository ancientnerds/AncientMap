"""Image query generator for the angle-level image research stage.

Calls MiniMax M3 with an angle's topic + description and returns 3-5 short
concrete image search queries used downstream to fan out across connectors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "angle_image_queries.txt"

_MAX_QUERIES = 5
_MAX_QUERY_LEN = 80  # hard cap to reject verbose LLM output


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


async def generate_queries_for_angle(
    angle_topic: str,
    angle_description: str,
    settings,
) -> list[str]:
    """Ask the LLM for exploratory image queries for one angle.

    Returns an empty list on failure rather than raising, so the caller can
    skip this angle and continue.
    """
    from pipeline.lyra.minimax_shared import MiniMaxTerminalError, minimax_chat_anthropic

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user_msg = f"## Angle topic\n{angle_topic}\n\n## Angle description\n{angle_description}\n"
    try:
        raw = await asyncio.to_thread(
            minimax_chat_anthropic,
            system,
            user_msg,
            1024,
            settings,
            temperature=0.2,
        )
    except MiniMaxTerminalError as exc:
        # Optional image stage — a terminally failing query call skips this
        # angle's image research instead of surfacing into the run.
        logger.warning(
            "angle_image_queries: LLM failed terminally for angle '%s': %s",
            angle_topic[:60],
            exc,
        )
        return []
    queries = parse_queries(raw)
    if not queries:
        logger.warning(
            "angle_image_queries: parse_queries returned empty for angle '%s'",
            angle_topic[:60],
        )
    return queries
