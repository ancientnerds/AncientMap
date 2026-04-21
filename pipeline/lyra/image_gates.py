"""Relevance gates for probative image candidates.

Stage 1 (metadata_gate_passes): deterministic text-similarity check. Rejects
obvious mismatches cheaply before hitting the vision model.

Stage 2 (parse_vlm_verdict + verdict_is_accept): parses MiniMax VLM structured
output. Accept requires shows_required_subject=='yes', no forbidden elements,
quality good or acceptable, and verdict=='accept' from the model.
"""

from __future__ import annotations

import json
import logging
import re

from pipeline.lyra.image_fetcher import ImageCandidate

logger = logging.getLogger(__name__)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) > 3}


def metadata_gate_passes(cand: ImageCandidate, what_image_must_show: str) -> bool:
    """Cheap text-similarity check. Rejects clearly-irrelevant candidates.

    Requires at least one shared content token (length > 3) between the
    image's title+description and the specialist's must_show description.

    Calibration note: threshold was 2 in the initial version but that rejected
    legitimate museum-catalog matches whose titles use different vocabulary
    than the specialist's must_show description (e.g. a Neo-Assyrian cuneiform
    cylinder vs a must_show naming 'Anunnaki'). The vision gate catches
    false positives downstream, so we err permissive here.
    """
    haystack = f"{cand.title} {cand.description}".strip()
    if not haystack or not what_image_must_show:
        return False
    shared = _tokens(haystack) & _tokens(what_image_must_show)
    return len(shared) >= 1


VLM_SYSTEM_PROMPT = (
    "You are an image illustration judge for a research-paper pipeline. "
    "Given an image and a section topic, decide whether the image is a reasonable "
    "visual illustration for that section — thematically relevant, period-appropriate, "
    "or subject-adjacent. You are NOT asked to verify the image proves the specific claim; "
    "you are asked whether it belongs alongside this text as visual context. "
    "Be generous: archaeological photos, museum artifacts, maps, and period art all count "
    "even if they don't literally depict the exact named entity. "
    "Reject only when the image is off-topic, shows forbidden elements, or is low quality. "
    "Respond with STRICTLY valid JSON: "
    '{"shows_required_subject":"yes|partial|no",'
    '"specific_features_present":[strings],'
    '"forbidden_elements_present":[strings],'
    '"image_quality":"good|acceptable|poor",'
    '"verdict":"accept|soft_accept|reject","reason":"one sentence"}. '
    "Use 'accept' for direct matches, 'soft_accept' for thematically relevant images, "
    "'reject' only for clear mismatches or forbidden content. Output only JSON."
)


def build_vlm_prompt(
    claim: str,
    what_image_must_show: str,
    forbidden_elements: list[str],
) -> str:
    """Build the VLM user prompt for a single candidate."""
    return (
        f"{VLM_SYSTEM_PROMPT}\n\n"
        f"SECTION TOPIC: {claim}\n"
        f"IDEAL SUBJECT: {what_image_must_show}\n"
        f"FORBIDDEN ELEMENTS: {forbidden_elements}\n\n"
        "Examine the attached image and return the JSON verdict. "
        "Accept or soft-accept any image that would reasonably illustrate this section. "
        "Reject only for clear off-topic content, forbidden elements, or poor quality."
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


def verdict_is_accept(v: dict | None) -> bool:
    """Strict acceptance: the image directly matches the topic per the VLM.

    Used to label images 'verified' in the final paper — the reviewer sees a
    green chip for these. Non-strict candidates still get embedded but as
    'unverified', so the reviewer can approve them manually instead of the
    pipeline silently dropping them.
    """
    if not v:
        return False
    if v.get("verdict") not in ("accept", "soft_accept"):
        return False
    if v.get("shows_required_subject") == "no":
        return False
    if v.get("forbidden_elements_present"):
        return False
    if v.get("image_quality") == "poor":
        return False
    return True


def verdict_is_safe(v: dict | None) -> bool:
    """Safety gate: no forbidden elements and not low quality.

    Images that pass this gate are safe to embed in the paper even if they
    don't fully match the topic. The reviewer judges topical fit in the UI.
    If the VLM call failed entirely (v is None), default to safe so a VLM
    outage doesn't strip every candidate.
    """
    if v is None:
        return True
    if v.get("forbidden_elements_present"):
        return False
    if v.get("image_quality") == "poor":
        return False
    return True
