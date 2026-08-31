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

import logging
import re

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.meaningful_images import STRICT_VLM_PROMPT
from pipeline.lyra.minimax_shared import parse_fenced_json

logger = logging.getLogger(__name__)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 3}


def _metadata_overlap(cand: ImageCandidate, what_image_must_show: str) -> int:
    """Count of content tokens (length > 3) shared by the candidate's
    title+description and the specialist's must-show description."""
    haystack = f"{cand.title} {cand.description}".strip()
    if not haystack or not what_image_must_show:
        return 0
    return len(_tokens(haystack) & _tokens(what_image_must_show))


def metadata_gate_passes(cand: ImageCandidate, what_image_must_show: str) -> bool:
    """Cheap text-similarity check. Rejects clearly-irrelevant candidates.

    One shared content token is enough. This filter exists to keep obvious
    junk away from the expensive vision judge, NOT to decide relevance — the
    judge does that, and it sees the image while this only sees a title.

    It required 2 shared tokens plus 20% coverage until 2026-08-31, which
    made it the de-facto decider: museum and Commons titles are terse
    ("Solar flare", "Object 1983.104.2") and routinely share one word with a
    full sentence of must-show text, so 587 of 971 opportunities across 12
    papers reached the judge with nothing left to judge.

    The single-token coincidence the old rule guarded against (Run 15: a
    Nazca-lines image matched an O'Brien-book paragraph on "lines") is now
    handled where it belongs — such a candidate ranks last via
    `rank_by_metadata_overlap` and is refused by the judge on sight.
    """
    return _metadata_overlap(cand, what_image_must_show) >= 1


def rank_by_metadata_overlap(
    cands: list[ImageCandidate], what_image_must_show: str
) -> list[ImageCandidate]:
    """Best-matching candidates first, ties keeping their original order.

    The probe budget per opportunity is spent in list order, so with a
    deliberately wide pre-filter the ranking is what keeps the vision calls
    pointed at the most promising images.
    """
    return sorted(cands, key=lambda c: -_metadata_overlap(c, what_image_must_show))


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
    v = parse_fenced_json(raw, default=None, extract_object=True)
    return v if isinstance(v, dict) else None


def verdict_is_meaningful(v: dict | None) -> bool:
    """True only when the strict judge ruled the image literally depicts the claim."""
    if not v:
        return False
    return v.get("verdict") == "meaningful"


def verdict_is_accept(v: dict | None) -> bool:
    """The image literally depicts the claim — citable as visual evidence.

    Drives the `verified` flag, which decides whether the caption presents
    the picture as evidence or as an illustration.
    """
    return verdict_is_meaningful(v)


def verdict_is_safe(v: dict | None) -> bool:
    """The image may be embedded at all — as evidence OR as an illustration.

    The judge grades on three levels (meaningful / weak / misleading) and
    until 2026-08-31 both gates were the same function, so `weak` — "related
    but not literal", the judge's explicit middle — was discarded with the
    misleading ones. Across 12 papers that cost 862 of 971 opportunities
    every candidate they had, and a paper on solar superflares ended up with
    no picture of the Sun: statistical claims ("2,889 superflares on 56,450
    stars") are not LITERALLY depictable by any photograph, so science papers
    could not earn an image at all.

    `weak` therefore embeds, but never as evidence — `verdict_is_accept`
    stays False and the caption says so. `misleading` and `off_topic` are
    still dropped, whichever field carries the bad news.
    """
    if not v:
        return False
    if v.get("verdict") not in ("meaningful", "weak"):
        return False
    return v.get("match") != "off_topic"
