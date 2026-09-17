"""Pick the stills for a short.

Three explicit stages:
  1. aspect — panoramas (wider than PANORAMA_ASPECT) are out; the rest rank by
     closeness to 9:16 so portrait shots lead.
  2. VLM judgement — MiniMax's coding-plan VLM (the endpoint the paper pipeline
     already uses) sees the card text and labels kind, subject, people, text,
     quality, relevance to the narration, the phrase it illustrates, and whether
     a centre 9:16 crop keeps the subject. Maps, documents, artefacts, crowds,
     text overlays and off-topic shots are out.
  3. duplicates — pixel-near copies by dhash (as in the paper pipeline) and
     same-subject shots by the VLM label; the better-scoring one stays.

The renderer then orders the stills that fit the timeline by where their
phrase appears in the card text, so the pictures follow the narration.

`select_stills` is pure and unit tested;
`hash_image` / `judge_all` do the I/O.
"""

from __future__ import annotations

import io
import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from PIL import Image

from pipeline.lyra.config import _get_settings
from pipeline.lyra.minimax_shared import create_minimax_client, minimax_vlm, parse_fenced_json
from pipeline.utils.imagehash import DHASH_MAX_DISTANCE, dhash, hamming

logger = logging.getLogger(__name__)

T = TypeVar("T")

TARGET_ASPECT = 9 / 16
PANORAMA_ASPECT = 2.0
MIN_QUALITY = 3
MIN_RELEVANCE = 2
VLM_MAX_SIDE = 1280
VLM_JPEG_QUALITY = 85

VLM_PROMPT = """You judge whether a photo can carry a vertical (9:16) short video about the archaeological site "{site}".
The narration of the video is:
"{card_text}"

Return JSON only, no prose:
{{"kind": "site_photo" | "artifact" | "map_or_document" | "people" | "other",
 "subject": "<2-4 words naming what the photo shows>",
 "people_prominent": true | false,
 "text_or_overlay": true | false,
 "quality": 1-5,
 "relevance": 1-5,
 "illustrates": "<the exact phrase of the narration this photo shows best, or an empty string>",
 "focus": {{"x": 0.0-1.0, "y": 0.0-1.0}},
 "vertical_crop_ok": true | false}}
kind: site_photo = the site, its structures or landscape photographed on location; artifact = an object in a museum or studio; map_or_document = maps, drawings, scans, diagrams, book pages; people = a person or crowd is the subject.
people_prominent: people are large or central (small distant figures are fine).
text_or_overlay: captions, watermarks, signage, borders or frames inside the picture.
quality: 5 = sharp, well exposed, striking; 3 = usable; 1 = blurry, dark, damaged or a low-resolution scan.
relevance: 5 = shows exactly what the narration describes; 3 = shows the site in general; 1 = unrelated to the narration.
illustrates: copy the phrase verbatim from the narration; empty if relevance is below 3.
focus: where the main subject sits in the picture, as fractions of width (x, 0 = left edge) and height (y, 0 = top); the video crops a tall 9:16 window around this point.
vertical_crop_ok: cropping a tall 9:16 window around the focus still shows the subject."""


@dataclass
class Candidate:
    image: dict  # entry from images.json (carries local_path, attribution, …)
    width: int
    height: int
    dhash: int = 0
    verdict: dict | None = None

    @property
    def aspect(self) -> float:
        return self.width / self.height


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


def aspect_penalty(width: int, height: int) -> float:
    """0 for a perfect 9:16 frame, growing symmetrically for wider or taller pictures."""
    return abs(math.log((width / height) / TARGET_ASPECT))


def is_panorama(width: int, height: int) -> bool:
    return width / height > PANORAMA_ASPECT


def normalize_subject(subject: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (subject or "").lower()).strip()


def _number(value) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def reject_reason(cand: Candidate, *, require_verdict: bool) -> str | None:
    """Why a candidate cannot carry the short, or None if it can."""
    if is_panorama(cand.width, cand.height):
        return "panorama"
    v = cand.verdict
    if v is None:
        return "no VLM verdict" if require_verdict else None
    if v.get("kind") != "site_photo":
        return f"kind={v.get('kind')}"
    if v.get("people_prominent"):
        return "people prominent"
    if v.get("text_or_overlay"):
        return "text or overlay"
    if _number(v.get("quality")) < MIN_QUALITY:
        return f"quality={v.get('quality')}"
    if _number(v.get("relevance")) < MIN_RELEVANCE:
        return f"relevance={v.get('relevance')}"
    if not v.get("vertical_crop_ok"):
        return "subject lost in 9:16 crop"
    return None


def focus_of(verdict: dict | None) -> tuple[float, float]:
    """Focal point (x, y) in 0..1 from a verdict; the centre when absent or malformed."""
    f = (verdict or {}).get("focus")
    if not isinstance(f, dict):
        return 0.5, 0.5
    try:
        x, y = float(f.get("x", 0.5)), float(f.get("y", 0.5))
    except (TypeError, ValueError):
        return 0.5, 0.5
    return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)


def score(cand: Candidate) -> float:
    """Higher is better. Relevance to the narration dominates (one relevance
    point outweighs two quality points), then how close the frame is to 9:16,
    then VLM quality."""
    v = cand.verdict or {}
    return (
        _number(v.get("relevance")) * 3
        + _number(v.get("quality"))
        - aspect_penalty(cand.width, cand.height) * 2
    )


def select_stills(
    cands: list[Candidate], *, require_verdict: bool = True
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """Return (kept in score order, rejected with reasons). Duplicates are judged
    against what was already kept, so the better-scoring copy survives."""
    kept: list[Candidate] = []
    rejected: list[tuple[Candidate, str]] = []
    for cand in sorted(cands, key=score, reverse=True):
        reason = reject_reason(cand, require_verdict=require_verdict)
        if reason is None and any(hamming(cand.dhash, k.dhash) <= DHASH_MAX_DISTANCE for k in kept):
            reason = "duplicate (hash)"
        if reason is None and cand.verdict is not None:
            subject = normalize_subject(cand.verdict.get("subject", ""))
            if subject and any(
                k.verdict is not None and normalize_subject(k.verdict.get("subject", "")) == subject
                for k in kept
            ):
                reason = f"duplicate (subject: {subject})"
        if reason is not None:
            rejected.append((cand, reason))
        else:
            kept.append(cand)
    return kept, rejected


def hash_image(path: Path) -> int:
    with Image.open(path) as im:
        return dhash(im)


def vlm_bytes(path: Path) -> bytes:
    """Downscaled JPEG for the VLM; the originals are 3–5 MB and go base64 into JSON."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((VLM_MAX_SIDE, VLM_MAX_SIDE))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=VLM_JPEG_QUALITY)
        return buf.getvalue()


VLM_ATTEMPTS = 3
VLM_RETRY_WAIT_S = 8.0


def judge_all(paths: list[Path], site_name: str, card_text: str) -> list[dict | None]:
    """One verdict per image. A call that returns nothing (HTTP error, SSL
    reset, unparsable JSON) is retried VLM_ATTEMPTS times with a pause; an
    image that still has no verdict stays None and is rejected downstream.
    If *no* image got a verdict the VLM is unreachable and we stop instead of
    silently selecting nothing."""
    settings = _get_settings()
    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)
    prompt = VLM_PROMPT.format(site=site_name, card_text=card_text)
    verdicts: list[dict | None] = []
    try:
        for path in paths:
            verdict: dict | None = None
            for attempt in range(1, VLM_ATTEMPTS + 1):
                raw = minimax_vlm(client, vlm_bytes(path), prompt)
                parsed = parse_fenced_json(raw, default=None, extract_object=True)
                if isinstance(parsed, dict):
                    verdict = parsed
                    break
                logger.warning(
                    "vlm %s: no verdict (attempt %d/%d)", path.name, attempt, VLM_ATTEMPTS
                )
                if attempt < VLM_ATTEMPTS:
                    time.sleep(VLM_RETRY_WAIT_S)
            verdicts.append(verdict)
            logger.info("vlm %s → %s", path.name, verdict)
    finally:
        client.close()
    if paths and all(v is None for v in verdicts):
        raise RuntimeError(
            f"MiniMax VLM returned no verdict for any of {len(paths)} images — network or quota"
        )
    return verdicts
