"""Cross-section coherence pass for Theo research papers.

Reads the full assembled paper with an LLM and returns:
  - Contradictions: same entity treated with opposite stances in different
    sections without being framed as opposing viewpoints.
  - Title-term definitions: every multi-word phrase in the title must
    appear in the body.

If any contradictions or missing title terms surface, the caller can send
the paper back to the writer for a repair pass. This module only produces
the report; wiring and repair live in handlers/paper.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).resolve().parent / "prompts"
# Connector words inside a title fragment — splitting on these turns
# "Luminous Beings in Ancient Mythology" into the matchable phrases
# ["Luminous Beings", "Ancient Mythology"] rather than one fused string.
_CONNECTORS = frozenset(
    {"and", "or", "in", "of", "for", "with", "vs", "versus", "between", "from", "to"}
)
# Pure filler — words that have zero semantic weight when counting content
# words in a phrase.
_FILLER = frozenset({"a", "an", "the"})


@dataclass
class Contradiction:
    entity: str
    stance_a: str
    section_a: str
    stance_b: str
    section_b: str
    severity: Literal["high", "medium", "low"]


@dataclass
class CoherenceResult:
    contradictions: list[Contradiction] = field(default_factory=list)
    title_terms: list[str] = field(default_factory=list)
    title_terms_defined_in_body: dict[str, bool] = field(default_factory=dict)


def extract_title_terms(title: str) -> list[str]:
    """Extract every phrase from the title that the body must define.

    Strategy:
      1. Split the title on hard separators (`:`, `,`, `;`).
      2. Within each fragment, split on connector words (`and`, `or`, `in`,
         `of`, ...) so a compound like "Luminous Beings in Ancient Mythology"
         contributes both "Luminous Beings" and "Ancient Mythology", not a
         joined "Luminous Beings Ancient Mythology" that never appears
         verbatim in prose.
      3. Drop pure filler (`a`, `an`, `the`) from each phrase.
      4. Keep phrases of >= 2 content words; deduplicate while preserving
         first-occurrence order.
    """
    if not title:
        return []

    fragments = re.split(r"[:,;]", title)
    out: list[str] = []
    seen: set[str] = set()
    for frag in fragments:
        frag = frag.strip()
        if not frag:
            continue

        # Split on connectors (case-insensitive whole-word match)
        connector_re = re.compile(
            r"\s+(?:" + "|".join(re.escape(c) for c in _CONNECTORS) + r")\s+",
            re.IGNORECASE,
        )
        sub_phrases = connector_re.split(frag)

        for phrase in sub_phrases:
            words = [w for w in phrase.split() if w.lower() not in _FILLER]
            # Strip any leading/trailing connectors that survived (e.g.
            # "and Human Genius" after a comma split → "Human Genius").
            while words and words[0].lower() in _CONNECTORS:
                words.pop(0)
            while words and words[-1].lower() in _CONNECTORS:
                words.pop()
            if len(words) >= 2:
                joined = " ".join(words)
                lower = joined.lower()
                if lower not in seen:
                    seen.add(lower)
                    out.append(joined)
    return out


def check_title_terms_in_body(terms: list[str], body: str) -> dict[str, bool]:
    """Case-insensitive substring check for each term."""
    body_lc = body.lower()
    return {t: (t.lower() in body_lc) for t in terms}


async def run_coherence_pass(
    title: str,
    body: str,
    llm_call,
    settings,
) -> CoherenceResult:
    """Run LLM coherence check. Safe on LLM failure — returns local-only
    title-term check with empty contradictions so the paper still ships."""
    title_terms = extract_title_terms(title)
    local_defs = check_title_terms_in_body(title_terms, body)

    prompt_template = (_PROMPTS / "coherence_pass.txt").read_text(encoding="utf-8")
    prompt_filled = prompt_template.replace("{title}", title).replace("{body}", body[:8000])

    try:
        raw = await llm_call(prompt_filled, "", 2048, settings, 0.2)
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("coherence_pass LLM failure: %s", exc)
        return CoherenceResult(
            contradictions=[],
            title_terms=title_terms,
            title_terms_defined_in_body=local_defs,
        )

    contradictions = [
        Contradiction(
            entity=c.get("entity", ""),
            stance_a=c.get("stance_a", ""),
            section_a=c.get("section_a", ""),
            stance_b=c.get("stance_b", ""),
            section_b=c.get("section_b", ""),
            severity=c.get("severity", "low"),
        )
        for c in data.get("contradictions", [])
        if c.get("entity")
    ]
    # Local substring check is authoritative for title-term definitions.
    # The LLM may claim a term is defined based on paraphrase; we require the
    # exact phrase from the title to appear.
    defs = {t: bool(local_defs.get(t, False)) for t in title_terms}
    return CoherenceResult(
        contradictions=contradictions,
        title_terms=title_terms,
        title_terms_defined_in_body=defs,
    )
