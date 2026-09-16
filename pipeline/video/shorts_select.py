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

`select_stills` / `order_by_narration` are pure and unit tested;
`hash_image` / `judge_all` do the I/O.
"""

from __future__ import annotations

import io
import logging
import math
import re
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
 "vertical_crop_ok": true | false}}
kind: site_photo = the site, its structures or landscape photographed on location; artifact = an object in a museum or studio; map_or_document = maps, drawings, scans, diagrams, book pages; people = a person or crowd is the subject.
people_prominent: people are large or central (small distant figures are fine).
text_or_overlay: captions, watermarks, signage, borders or frames inside the picture.
quality: 5 = sharp, well exposed, striking; 3 = usable; 1 = blurry, dark, damaged or a low-resolution scan.
relevance: 5 = shows exactly what the narration describes; 3 = shows the site in general; 1 = unrelated to the narration.
illustrates: copy the phrase verbatim from the narration; empty if relevance is below 3.
vertical_crop_ok: cropping the centre of the picture to a tall 9:16 frame still shows the subject."""


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


def order_by_narration(
    items: list[T], card_text: str, verdict_of: Callable[[T], dict | None]
) -> list[T]:
    """Items in the order their `illustrates` phrase occurs in the card text;
    items without a matching phrase keep their incoming (score) order at the
    end. Applied by the renderer to the stills that made the cut, so ordering
    never pushes a high-scoring still out of the available slots."""
    text = card_text.lower()

    def position(item: T) -> int:
        phrase = ((verdict_of(item) or {}).get("illustrates") or "").strip().lower()
        at = text.find(phrase) if phrase else -1
        return at if at >= 0 else len(text) + 1

    return sorted(items, key=position)  # sorted() is stable → score order among ties


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


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


def judge_all(paths: list[Path], site_name: str, card_text: str) -> list[dict | None]:
    settings = _get_settings()
    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)
    prompt = VLM_PROMPT.format(site=site_name, card_text=card_text)
    verdicts: list[dict | None] = []
    try:
        for path in paths:
            raw = minimax_vlm(client, vlm_bytes(path), prompt)
            verdict = parse_fenced_json(raw, default=None, extract_object=True)
            verdicts.append(verdict if isinstance(verdict, dict) else None)
            logger.info("vlm %s → %s", path.name, verdicts[-1])
    finally:
        client.close()
    return verdicts
