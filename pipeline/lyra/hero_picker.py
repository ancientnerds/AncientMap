"""Pick the best inline probative image to use as the paper's banner hero.

No external API calls, no AI image generation — selects from the images that
the probative-image handler already embedded in the paper. Scoring factors:

- **Title relevance**: overlap of keywords between the paper title and the
  image's title/rationale/section_heading. Images whose metadata echoes the
  headline beat generic period-art shots.
- **Aspect ratio**: banner crops work best on landscape images; we read the
  image file from disk and prefer anything ≥ 1.4:1 wide.
- **Section position**: earlier sections carry the headline argument, so an
  image pulled from the introduction beats one from a late appendix.
- **Source quality**: museum sources (Met, Louvre, PAS) rank above generic
  Wikimedia Commons photography.

Returns the picked entry enriched with `src`, `title`, `caption`, `sourceUrl`
fields ready for the frontend, or `None` if no probative image exists.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_image_captions import _clean_title, build_caption

logger = logging.getLogger(__name__)

# Stored probative_images entries use web paths like
# /data/research-images/<id>/... . Resolve to local disk for aspect sniff.
_IMAGES_ROOT = Path(__file__).parent.parent.parent / "public"

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "on",
    "to",
    "for",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "were",
    "be",
    "been",
    "that",
    "this",
    "it",
    "its",
    "at",
    "but",
    "not",
    "are",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "can",
    "could",
    "should",
    "may",
    "might",
    "investigating",
    "analysis",
    "study",
    "studies",
    "research",
    "paper",
    "about",
    "into",
    "through",
    "ancient",
    "their",
    "what",
    "how",
    "why",
}

# Source-quality ranking. Higher = better for a banner image.
_SOURCE_RANK = {
    "met_museum": 5,
    "met": 5,
    "louvre": 5,
    "getty_museum": 5,
    "getty": 5,
    "loc": 4,
    "europeana": 4,
    "pas": 4,
    "wikimedia": 2,
}


@dataclass
class HeroCandidate:
    entry: dict
    score: float
    reason: str


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _aspect_ratio(web_path: str) -> float:
    """Return width/height for the image file backing `web_path`, or 0.0 on failure.

    We don't want to hard-require Pillow just for hero-picking, so we try
    importing lazily and fall back to 0.0 if unavailable. A zero ratio means
    the landscape-bonus component drops to 0 but the pick still works.
    """
    if not web_path.startswith("/data/"):
        return 0.0
    local = _IMAGES_ROOT / web_path.lstrip("/")
    if not local.exists():
        return 0.0
    try:
        from PIL import Image  # type: ignore

        with Image.open(local) as img:
            w, h = img.size
            return (w / h) if h else 0.0
    except Exception:
        return 0.0


def _cand_from_entry(entry: dict) -> ImageCandidate:
    return ImageCandidate(
        url=entry.get("source_url", "") or "",
        source=entry.get("source_name", "") or "",
        title=entry.get("title", "") or "",
        description=entry.get("description", "") or "",
        artist=entry.get("artist", "") or "",
        license=entry.get("license", "") or "",
        license_url=entry.get("license_url", "") or "",
    )


def _score_entry(entry: dict, title_tokens: set[str], position_index: int) -> HeroCandidate:
    # Title relevance: tokens shared between headline and image metadata.
    meta_text = " ".join(
        str(entry.get(k, "") or "")
        for k in ("title", "rationale", "section_heading", "description")
    )
    meta_tokens = _tokenize(meta_text)
    overlap = len(title_tokens & meta_tokens)
    relevance = overlap * 3.0  # strong signal; boost by 3 per shared keyword

    # Aspect ratio: prefer landscape.
    ratio = _aspect_ratio(entry.get("web_path", "") or "")
    if ratio >= 1.6:
        aspect_bonus = 2.5
    elif ratio >= 1.35:
        aspect_bonus = 1.5
    elif ratio >= 1.1:
        aspect_bonus = 0.5
    else:
        aspect_bonus = 0.0

    # Position: earlier = more headline-relevant. position_index is 0 for
    # the first embedded image.
    position_bonus = max(0.0, 2.0 - position_index * 0.25)

    # Source quality.
    source_bonus = float(_SOURCE_RANK.get(entry.get("source_name", ""), 1))

    # Writer-placed images (section_heading == "[inline]") were chosen by the
    # paper writer to illustrate a specific passage — bump them up.
    writer_bonus = 1.5 if entry.get("section_heading") == "[inline]" else 0.0

    score = relevance + aspect_bonus + position_bonus + source_bonus + writer_bonus
    reason = (
        f"overlap={overlap} aspect={ratio:.2f} pos={position_index} "
        f"src={entry.get('source_name', '?')} writer={int(writer_bonus > 0)}"
    )
    return HeroCandidate(entry=entry, score=score, reason=reason)


def pick_hero_image(
    paper_title: str,
    probative_images: list[dict],
) -> dict | None:
    """Pick the best banner hero from the paper's probative images.

    Returns a dict with keys `{src, title, caption, sourceUrl, web_path,
    source_name, rationale}` ready for the frontend, or None if the input
    is empty.
    """
    if not probative_images:
        return None

    title_tokens = _tokenize(paper_title)
    ranked: list[HeroCandidate] = []
    for idx, entry in enumerate(probative_images):
        if not entry.get("web_path"):
            continue
        ranked.append(_score_entry(entry, title_tokens, idx))

    if not ranked:
        return None

    ranked.sort(key=lambda c: c.score, reverse=True)
    best = ranked[0]

    logger.info(
        "[hero] picked %s (score=%.2f, %s)",
        best.entry.get("web_path"),
        best.score,
        best.reason,
    )

    cand = _cand_from_entry(best.entry)
    rationale = best.entry.get("rationale") or ""
    caption = build_caption(cand, rationale)
    # build_caption wraps in asterisks — strip for the frontend payload
    # (the hero renders plain text, not markdown).
    caption_text = caption.strip("*").rstrip(".")

    return {
        "src": best.entry.get("web_path", ""),
        "title": _clean_title(best.entry.get("title", "")) or "",
        "caption": caption_text,
        "sourceUrl": best.entry.get("source_url", "") or "",
        "web_path": best.entry.get("web_path", ""),
        "source_name": best.entry.get("source_name", ""),
        "rationale": rationale,
    }
