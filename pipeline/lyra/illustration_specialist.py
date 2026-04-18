"""Runs the Illustration Specialist LLM pass that picks probative images.

Given a paper's moderated claims, returns a list of image opportunities.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "illustration_specialist.txt"

_REQUIRED_FIELDS = (
    "claim_index",
    "needs_image",
    "search_query",
    "what_image_must_show",
    "forbidden_elements",
    "rationale",
)


def parse_opportunities(raw: str) -> list[dict]:
    """Parse the specialist LLM output into a list of opportunities.

    - Strips markdown fences if present.
    - Drops entries missing required fields.
    - Drops entries where needs_image is false (they add nothing downstream).
    - Returns [] on any parse failure.
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
        # Try to extract the first {...} block
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return []
    opps = data.get("opportunities", [])
    out: list[dict] = []
    for o in opps:
        if not all(k in o for k in _REQUIRED_FIELDS):
            continue
        if not o.get("needs_image"):
            continue
        out.append(o)
    return out


async def select_opportunities(
    claims: list[dict],
    settings,
) -> list[dict]:
    """Call MiniMax M2.7 to pick which claims merit probative images.

    `claims` is the flat list produced by `_collect_all_claims()` in paper.py
    (each with keys claim, citations, confidence, source_ids, type).
    """
    from pipeline.lyra.minimax_shared import minimax_chat_anthropic

    system = _PROMPT_PATH.read_text(encoding="utf-8")

    numbered = "\n".join(
        f"{i}. [{c.get('confidence', 'medium')}] {c.get('claim', '')}" for i, c in enumerate(claims)
    )
    user_msg = f"## Claims\n\n{numbered}\n"

    raw = await asyncio.to_thread(
        minimax_chat_anthropic,
        system,
        user_msg,
        4096,
        settings,
        temperature=0.1,
    )
    return parse_opportunities(raw)
