"""Relevance gates for probative image candidates.

Stage 1 (metadata_gate_passes): deterministic text-similarity check. Rejects
obvious mismatches cheaply before hitting the vision model.

Stage 2 (parse_vlm_verdict + verdict_is_accept/is_safe): parses MiniMax VLM
structured output. Uses the STRICT illustration-judge schema — only images
that LITERALLY depict the paragraph's primary subject pass. Thematically-
adjacent images (generic period artifacts, "looks like something from the
right era") are rejected.

Verdict schema:
    {
      "primary_entity_in_claim": "...",
      "what_image_actually_shows": "...",
      "match": "exact" | "related" | "off_topic",
      "verdict": "meaningful" | "weak" | "misleading",
      "reason": "one sentence"
    }
"""

from __future__ import annotations

import json
import logging
import re

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.meaningful_images import STRICT_VLM_PROMPT

logger = logging.getLogger(__name__)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 3}


def metadata_gate_passes(cand: ImageCandidate, what_image_must_show: str) -> bool:
    """Cheap text-similarity check. Rejects clearly-irrelevant candidates.

    Requires at least 2 shared content tokens (length > 3) between the
    image's title+description and the specialist's must_show description,
    AND at least 20% coverage of the must-show tokens. The 2-token rule
    catches generic single-word coincidences (Run 15: a Nazca-lines image
    matched an O'Brien-book paragraph because both contained "lines"); the
    20% rule scales the bar with prompt specificity. VLM still runs as the
    strict downstream gate.
    """
    haystack = f"{cand.title} {cand.description}".strip()
    if not haystack or not what_image_must_show:
        return False
    h_tokens = _tokens(haystack)
    m_tokens = _tokens(what_image_must_show)
    if not m_tokens:
        return False
    shared = h_tokens & m_tokens
    return len(shared) >= 2 and (len(shared) / len(m_tokens)) >= 0.20


# Re-export for the handful of callers (handlers/probative_images.py and dev
# e2e scripts) that imported the old name from this module.
VLM_SYSTEM_PROMPT = STRICT_VLM_PROMPT


def build_vlm_prompt(
    claim: str,
    what_image_must_show: str,
    forbidden_elements: list[str] | None = None,
) -> str:
    """Build the VLM user prompt for a single candidate.

    Signature preserved for backward compat with `handlers/probative_images.py`;
    `forbidden_elements` is now advisory (the strict judge catches off-topic
    images regardless). `claim` is the paragraph text the image illustrates;
    `what_image_must_show` is the specialist's ideal-subject hint included as
    extra grounding for the judge.
    """
    ideal = what_image_must_show or "(not specified)"
    forbidden = ", ".join(forbidden_elements or []) or "(none specified)"
    return (
        f"{STRICT_VLM_PROMPT}\n\n"
        f"PARAGRAPH CLAIM:\n{claim}\n\n"
        f"IDEAL SUBJECT (hint):\n{ideal}\n\n"
        f"AVOID:\n{forbidden}\n\n"
        "Now examine the attached image and return the JSON verdict."
    )


def parse_vlm_verdict(raw: str) -> dict | None:
    """Parse the VLM response JSON. Returns None on any failure."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        s = s.rsplit("```", 1)[0].strip()
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None


def verdict_is_meaningful(v: dict | None) -> bool:
    """True only when the strict judge ruled the image literally depicts the claim."""
    if not v:
        return False
    return v.get("verdict") == "meaningful"


# Backward-compat aliases. Under the strict schema, a candidate is either
# meaningful (keep, tag as verified) or not (drop entirely) — there's no
# "safe but unverified" middle ground like the old lenient soft_accept.
def verdict_is_accept(v: dict | None) -> bool:
    return verdict_is_meaningful(v)


def verdict_is_safe(v: dict | None) -> bool:
    return verdict_is_meaningful(v)
