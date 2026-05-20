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
class NumericClaim:
    """A measurement extracted from prose: 'The shaft descends 25-30 m...'."""

    section: str
    value_text: str  # raw match, e.g. "25-30 m"
    unit: str
    surrounding_sentence: str


@dataclass
class NumericConflict:
    """Two sections of the same paper assert measurably different values for
    what the LLM judges to be the same entity."""

    entity: str
    section_a: str
    value_a: str
    section_b: str
    value_b: str
    suggested_resolution: str
    severity: Literal["high", "medium", "low"]


@dataclass
class CoherenceResult:
    contradictions: list[Contradiction] = field(default_factory=list)
    title_terms: list[str] = field(default_factory=list)
    title_terms_defined_in_body: dict[str, bool] = field(default_factory=dict)
    numeric_claims: list[NumericClaim] = field(default_factory=list)
    numeric_conflicts: list[NumericConflict] = field(default_factory=list)


# Reuses the spirit of hallucination_gate's measurement regex, but with broader
# unit coverage including paleoclimate / archaeology contexts (cal BP, kyr, BCE).
_MEASUREMENT_RE = re.compile(
    r"\b(?P<value>\d{1,5}(?:[.,]\d+)?(?:\s*[-–—]\s*\d{1,5}(?:[.,]\d+)?)?)"
    r"\s*"
    r"(?P<unit>m\b|meters?|km|miles?|feet|ft\b|cm|mm|kg|tons?|years?|kyr|ka\b|Ma\b|"
    r"cal\s*(?:yr\s*)?BP|BCE|BC\b|CE\b|AD\b|°C|°F|%|g/m²)",
    re.IGNORECASE,
)

# A heading marks a section. We accept ## and ### (anything deeper is rare).
_SECTION_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Return [(section_title, section_text), ...] in document order.

    Prose before the first heading is grouped under "(intro)".
    """
    headings = list(_SECTION_HEADING_RE.finditer(body))
    if not headings:
        return [("(intro)", body)]

    out: list[tuple[str, str]] = []
    if headings[0].start() > 0:
        intro = body[: headings[0].start()].strip()
        if intro:
            out.append(("(intro)", intro))
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        out.append((h.group(1).strip(), body[start:end].strip()))
    return out


# Sentence split — simple but good enough for measurement extraction. Splits on
# `. `, `? `, `! ` followed by a capital letter or end of string.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def extract_numeric_claims(body: str) -> list[NumericClaim]:
    """Walk the body section-by-section and capture every numeric measurement.

    Output is the raw signal the LLM uses to reason about conflicts — we don't
    try to group or normalize here. Grouping ("is this the shaft depth or the
    water table depth?") needs semantic context the LLM provides.
    """
    claims: list[NumericClaim] = []
    for section_title, section_text in _split_sections(body):
        if not section_text:
            continue
        sentences = _SENTENCE_SPLIT_RE.split(section_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            for m in _MEASUREMENT_RE.finditer(sentence):
                value = m.group("value").strip()
                unit = m.group("unit").strip()
                claims.append(
                    NumericClaim(
                        section=section_title,
                        value_text=f"{value} {unit}",
                        unit=unit,
                        surrounding_sentence=sentence[:240],
                    )
                )
    return claims


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


def _format_numeric_claims_for_prompt(claims: list[NumericClaim]) -> str:
    """Render extracted claims as a compact bullet list the LLM can scan."""
    if not claims:
        return "(none extracted)"
    lines = []
    for c in claims[:80]:  # cap to keep prompt manageable
        lines.append(f"- [{c.section}] {c.value_text} — “{c.surrounding_sentence}”")
    if len(claims) > 80:
        lines.append(f"... and {len(claims) - 80} more")
    return "\n".join(lines)


async def run_coherence_pass(
    title: str,
    body: str,
    llm_call,
    settings,
) -> CoherenceResult:
    """Run LLM coherence check. Safe on LLM failure — returns local-only
    title-term check + extracted numeric claims with empty conflicts so the
    paper still ships."""
    title_terms = extract_title_terms(title)
    local_defs = check_title_terms_in_body(title_terms, body)
    numeric_claims = extract_numeric_claims(body)

    prompt_template = (_PROMPTS / "coherence_pass.txt").read_text(encoding="utf-8")
    prompt_filled = (
        prompt_template.replace("{title}", title)
        .replace("{body}", body[:8000])
        .replace("{numeric_claims}", _format_numeric_claims_for_prompt(numeric_claims))
    )

    try:
        raw = await llm_call(prompt_filled, "", 2048, settings, 0.2)
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("coherence_pass LLM failure: %s", exc)
        return CoherenceResult(
            contradictions=[],
            title_terms=title_terms,
            title_terms_defined_in_body=local_defs,
            numeric_claims=numeric_claims,
            numeric_conflicts=[],
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
    numeric_conflicts = [
        NumericConflict(
            entity=c.get("entity", ""),
            section_a=c.get("section_a", ""),
            value_a=c.get("value_a", ""),
            section_b=c.get("section_b", ""),
            value_b=c.get("value_b", ""),
            suggested_resolution=c.get("suggested_resolution", ""),
            severity=c.get("severity", "low"),
        )
        for c in data.get("numeric_conflicts", [])
        if c.get("entity") and c.get("value_a") and c.get("value_b")
    ]
    # Local substring check is authoritative for title-term definitions.
    # The LLM may claim a term is defined based on paraphrase; we require the
    # exact phrase from the title to appear.
    defs = {t: bool(local_defs.get(t, False)) for t in title_terms}
    return CoherenceResult(
        contradictions=contradictions,
        title_terms=title_terms,
        title_terms_defined_in_body=defs,
        numeric_claims=numeric_claims,
        numeric_conflicts=numeric_conflicts,
    )
