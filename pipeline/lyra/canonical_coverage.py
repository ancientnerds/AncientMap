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


_MIN_SUBQ_WORDS = 6
# An "interrogative anchor" — at least one real question word/phrase the
# fragment is actually asking about. Without one of these, the regex was
# happily lifting "(c. 1200 BCE)?" out of a perfectly normal question and
# spawning a research angle named after a parenthetical date.
_INTERROGATIVE_RE = re.compile(
    r"\b(?:what|why|how|where|when|which|who|whether|whose|can|could|"
    r"do|does|did|is|are|were|will|would|should|might|may)\b",
    re.IGNORECASE,
)


def extract_user_subquestions(question: str) -> list[str]:
    """Return the sub-questions embedded in the user's original question.

    Heuristic: any sentence ending with "?" OR containing a trigger phrase
    is returned as a standalone sub-question string. Fragments that are
    too short or contain no actual interrogative are skipped — those are
    almost always parentheticals like "(c. 1200 BCE)?" that the
    sentence-splitter lifted out of a perfectly normal question. Run #15
    surfaced exactly this: the trailing "1200 BCE)?" became a research
    angle that 5 specialists then spent 14 minutes researching.
    """
    if not question:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", question)
    out: list[str] = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        # Skip fragments that have neither enough content nor an
        # interrogative — those are sentence-splitter artifacts.
        word_count = len(re.findall(r"\b\w+\b", s))
        if word_count < _MIN_SUBQ_WORDS:
            continue
        if not _INTERROGATIVE_RE.search(s):
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
        # MiniMax M3 occasionally returns an empty string when interleaved
        # thinking consumes the entire output budget. That's a known failure
        # mode, not a parse bug — short-circuit it as a clean "no result"
        # instead of logging json.JSONDecodeError noise on every run.
        raw_stripped = (raw or "").strip()
        if not raw_stripped:
            return []
        canonical = json.loads(raw_stripped).get("canonical_subtopics", [])
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
        raw_stripped = (raw or "").strip()
        if not raw_stripped:
            return []
        missing = json.loads(raw_stripped).get("missing_subtopics", [])
    except Exception as exc:
        logger.warning("canonical_coverage gap check failed: %s", exc)
        return []

    # Keep only entries that actually appeared in the canonical list
    canonical_set = set(canonical)
    return [m for m in missing if m in canonical_set]
