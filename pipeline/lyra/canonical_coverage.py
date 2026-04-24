"""Canonical-subtopic coverage for Theo decomposition.

Given a research question and the angles the LLM proposed, extract the set
of canonical subtopics a serious paper on this topic must address, and
return the gaps. Gaps become additional required angles so a paper on
ancient-astronaut topics always covers Watchers / Giza / Dendera / Dogon
even if the LLM's initial angle proposal missed them.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).resolve().parent / "prompts"

_SUBQ_TRIGGERS = (
    "could they",
    "what if",
    "is it possible",
    "can these",
    "might they",
)


def extract_user_subquestions(question: str) -> list[str]:
    """Return the sub-questions embedded in the user's original question.

    Heuristic: any sentence ending with "?" OR containing a trigger phrase
    is returned as a standalone sub-question string.
    """
    if not question:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", question)
    out: list[str] = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        lower = s.lower()
        if s.endswith("?") or any(t in lower for t in _SUBQ_TRIGGERS):
            out.append(s)
    return out


async def find_coverage_gaps(
    question: str,
    proposed_angle_topics: list[str],
    llm_call,
    settings,
) -> list[str]:
    """Return canonical subtopics not covered by the proposed angles.

    Two LLM calls: (1) enumerate canonical subtopics for this question,
    (2) identify which aren't covered by proposed angles. Both are
    best-effort — any failure returns an empty list so decomposition
    proceeds with whatever angles it already has.
    """
    enum_prompt = (_PROMPTS / "canonical_coverage.txt").read_text(encoding="utf-8")
    try:
        raw = await llm_call(enum_prompt, question, 1024, settings, 0.2)
        canonical = json.loads(raw).get("canonical_subtopics", [])
    except Exception as exc:
        logger.warning("canonical_coverage enumeration failed: %s", exc)
        return []

    if not canonical:
        return []

    gap_prompt = (
        "Here are canonical subtopics for a research question:\n"
        + "\n".join(f"- {c}" for c in canonical)
        + "\n\nHere are the research angles already proposed:\n"
        + "\n".join(f"- {t}" for t in proposed_angle_topics)
        + "\n\nReturn JSON listing canonical subtopics not covered by any "
        "proposed angle. Use the EXACT strings from the canonical list.\n\n"
        '{"missing_subtopics": ["..."]}'
    )
    try:
        raw = await llm_call(gap_prompt, question, 512, settings, 0.2)
        missing = json.loads(raw).get("missing_subtopics", [])
    except Exception as exc:
        logger.warning("canonical_coverage gap check failed: %s", exc)
        return []

    # Keep only entries that actually appeared in the canonical list
    canonical_set = set(canonical)
    return [m for m in missing if m in canonical_set]
