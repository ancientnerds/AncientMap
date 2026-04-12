"""Licensed image enrichment for Theo research papers.

Searches ONLY legally-licensed image sources (Wikimedia Commons CC, Met Museum CC0)
and injects relevant images with mandatory attribution into paper sections.

LICENSING POLICY:
- Every image MUST have a verified license in ALLOWED_LICENSES.
- No license = no image. No exceptions.
- We NEVER extract images from arbitrary web pages.

Usage:
    from pipeline.lyra.research_images import (
        search_wikimedia_images,
        search_museum_images,
        inject_source_images,
    )

    images = search_wikimedia_images("Gobekli Tepe", ["archaeology", "neolithic"])
    images += search_museum_images("Gobekli Tepe", ["archaeology", "neolithic"])
    paper = inject_source_images(paper_text, images, max_images=4)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# License allowlist — ONLY these are legal to embed
# ---------------------------------------------------------------------------

ALLOWED_LICENSES = frozenset(
    {
        "CC0",
        "CC0 1.0",
        "Public domain",
        "Public Domain",
        "CC BY 1.0",
        "CC BY 2.0",
        "CC BY 2.5",
        "CC BY 3.0",
        "CC BY 4.0",
        "CC BY-SA 1.0",
        "CC BY-SA 2.0",
        "CC BY-SA 2.5",
        "CC BY-SA 3.0",
        "CC BY-SA 4.0",
    }
)

# Normalized prefix check for license variants (e.g. "CC BY-SA 4.0 International")
_LICENSE_PREFIXES = (
    "cc0",
    "public domain",
    "cc by 1",
    "cc by 2",
    "cc by 3",
    "cc by 4",
    "cc by-sa 1",
    "cc by-sa 2",
    "cc by-sa 3",
    "cc by-sa 4",
)

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
MET_API_URL = "https://collectionapi.metmuseum.org/public/collection/v1"

_USER_AGENT = "AncientNerds/1.0 (https://ancientnerds.com) python-httpx"


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------


@dataclass
class SourceImage:
    """An image from a verified open-license source."""

    url: str  # Direct image URL (thumbnail preferred)
    alt_text: str  # Descriptive text from metadata
    attribution: str  # "Author, Source, License" — ALWAYS displayed
    source_url: str  # Commons page or museum page URL
    license: str  # MUST pass _is_license_allowed()
    keywords: set[str] = field(default_factory=set)
    quality_score: int = 1  # 1-3 for selection ranking
    author: str = ""


# ---------------------------------------------------------------------------
# License validation
# ---------------------------------------------------------------------------


def _is_license_allowed(license_str: str) -> bool:
    """Check if a license string matches our allowlist."""
    if not license_str:
        return False
    if license_str in ALLOWED_LICENSES:
        return True
    # Fuzzy match for variants like "CC BY-SA 4.0 International"
    normalized = license_str.lower().strip()
    return any(normalized.startswith(prefix) for prefix in _LICENSE_PREFIXES)


def _significant_keywords(text: str) -> set[str]:
    """Extract keywords (4+ chars, lowercased) for fuzzy matching."""
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 4}


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# Wikimedia Commons search
# ---------------------------------------------------------------------------


def search_wikimedia_images(topic: str, keywords: list[str]) -> list[SourceImage]:
    """Search Wikimedia Commons for licensed images matching the topic.

    Uses the MediaWiki API with generator search in the File namespace.
    Makes follow-up calls to get license/author metadata via extmetadata.

    Returns at most 5 images, all with verified open licenses.
    """
    query = topic
    if keywords:
        query = f"{topic} {' '.join(keywords[:3])}"

    # Step 1: Search for images
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",  # File namespace
        "gsrlimit": "8",  # Fetch more than we need, filter by license
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "600",  # Thumbnail width
        "iiextmetadatafilter": "LicenseShortName|Artist|ImageDescription",
    }

    try:
        resp = httpx.get(
            COMMONS_API_URL,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=30.0,
        )
        if resp.status_code != 200:
            logger.warning("Wikimedia Commons search failed: %s", resp.status_code)
            return []

        data = resp.json()
        pages = data.get("query", {}).get("pages", {})

    except Exception as exc:
        logger.warning("Wikimedia Commons search error: %s", exc)
        return []

    # Step 2: Parse results, filter by license
    results: list[SourceImage] = []

    for page_id, page in pages.items():
        if page_id == "-1":
            continue

        imageinfo = page.get("imageinfo", [{}])[0]
        if not imageinfo:
            continue

        # Only accept actual images
        mime = imageinfo.get("mime", "")
        if not mime.startswith("image/"):
            continue

        # Extract metadata
        extmeta = imageinfo.get("extmetadata", {})
        license_name = extmeta.get("LicenseShortName", {}).get("value", "")
        artist_html = extmeta.get("Artist", {}).get("value", "")
        description_html = extmeta.get("ImageDescription", {}).get("value", "")

        # HARD FILTER: reject unlicensed images
        if not _is_license_allowed(license_name):
            logger.debug(
                "Skipping unlicensed image: %s (license: %s)", page.get("title", ""), license_name
            )
            continue

        # Clean HTML from metadata fields
        author = _strip_html_tags(artist_html) if artist_html else "Unknown"
        description = _strip_html_tags(description_html) if description_html else ""

        # Prefer thumbnail URL
        thumb_url = imageinfo.get("thumburl", imageinfo.get("url", ""))
        if not thumb_url:
            continue

        # Build alt text from description or filename
        title = page.get("title", "").replace("File:", "").replace("_", " ")
        alt_text = description[:200] if description else title.rsplit(".", 1)[0]

        # Commons page URL
        source_url = f"https://commons.wikimedia.org/wiki/{page.get('title', '').replace(' ', '_')}"

        # Attribution line
        attribution = f"{author}, Wikimedia Commons, {license_name}"

        # Quality score: with description = 3, without = 1
        quality = 3 if description else 1

        results.append(
            SourceImage(
                url=thumb_url,
                alt_text=alt_text,
                attribution=attribution,
                source_url=source_url,
                license=license_name,
                keywords=_significant_keywords(f"{alt_text} {title} {description}"),
                quality_score=quality,
                author=author,
            )
        )

        if len(results) >= 5:
            break

    logger.info("Wikimedia Commons: %d licensed images for '%s'", len(results), topic[:50])
    return results


# ---------------------------------------------------------------------------
# Met Museum search
# ---------------------------------------------------------------------------


def search_museum_images(topic: str, keywords: list[str]) -> list[SourceImage]:
    """Search Met Museum for public domain artifact images.

    All Met Open Access images are CC0 — no license ambiguity.
    Uses the Met's free REST API (no auth required).

    Returns at most 3 images.
    """
    query = topic
    if keywords:
        query = f"{topic} {' '.join(keywords[:2])}"

    try:
        # Step 1: Search for object IDs
        resp = httpx.get(
            f"{MET_API_URL}/search",
            params={"q": query, "hasImages": "true", "isPublicDomain": "true"},
            headers={"User-Agent": _USER_AGENT},
            timeout=15.0,
        )
        if resp.status_code != 200:
            logger.warning("Met Museum search failed: %s", resp.status_code)
            return []

        data = resp.json()
        object_ids = data.get("objectIDs") or []

        if not object_ids:
            return []

        # Step 2: Fetch details for top objects (limit API calls)
        results: list[SourceImage] = []
        for obj_id in object_ids[:6]:  # Check up to 6, keep up to 3
            if len(results) >= 3:
                break

            try:
                obj_resp = httpx.get(
                    f"{MET_API_URL}/objects/{obj_id}",
                    headers={"User-Agent": _USER_AGENT},
                    timeout=10.0,
                )
                if obj_resp.status_code != 200:
                    continue

                obj = obj_resp.json()
            except Exception:
                continue

            # Only public domain
            if not obj.get("isPublicDomain"):
                continue

            image_url = obj.get("primaryImageSmall") or obj.get("primaryImage")
            if not image_url:
                continue

            title = obj.get("title", "Untitled")
            artist = obj.get("artistDisplayName", "")
            date = obj.get("objectDate", "")
            department = obj.get("department", "")
            culture = obj.get("culture", "")
            medium = obj.get("medium", "")

            # Build descriptive alt text
            parts = [title]
            if culture:
                parts.append(culture)
            if date:
                parts.append(date)
            if medium:
                parts.append(medium)
            alt_text = ", ".join(parts)

            # Source URL
            source_url = obj.get(
                "objectURL", f"https://www.metmuseum.org/art/collection/search/{obj_id}"
            )

            # Attribution (always CC0)
            attribution = "Metropolitan Museum of Art, Public Domain (CC0)"

            results.append(
                SourceImage(
                    url=image_url,
                    alt_text=alt_text,
                    attribution=attribution,
                    source_url=source_url,
                    license="CC0",
                    keywords=_significant_keywords(f"{title} {culture} {department} {artist}"),
                    quality_score=2,
                    author=artist or "Metropolitan Museum of Art",
                )
            )

            # Be polite to the API
            time.sleep(0.1)

    except Exception as exc:
        logger.warning("Met Museum search error: %s", exc)
        return []

    logger.info("Met Museum: %d public domain images for '%s'", len(results), topic[:50])
    return results


# ---------------------------------------------------------------------------
# Image injection into paper
# ---------------------------------------------------------------------------


def inject_source_images(
    paper_text: str,
    images: list[SourceImage],
    max_images: int = 4,
) -> str:
    """Inject source images into research paper at relevant sections.

    Uses keyword overlap between image metadata and paper paragraphs
    to place images at the most topically relevant locations.

    Every injected image includes a mandatory attribution line.
    Images are never placed in Abstract, Sources, or References sections.
    """
    if not images:
        return paper_text

    # Final license validation — belt and suspenders
    safe_images = [img for img in images if _is_license_allowed(img.license)]
    if not safe_images:
        return paper_text

    # Sort by quality_score descending, take top candidates
    safe_images.sort(key=lambda img: img.quality_score, reverse=True)
    candidates = safe_images[: max_images * 2]  # Keep extras for matching

    # Split paper into paragraphs with section awareness
    _SKIP_SECTIONS = frozenset({"abstract", "introduction", "references", "sources"})
    lines = paper_text.split("\n")

    # Find paragraph blocks and their section context
    paragraphs: list[dict] = []  # {text, line_idx, section, keywords}
    current_section = ""

    i = 0
    while i < len(lines):
        line = lines[i]
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            current_section = heading_match.group(1).strip().lower()
            i += 1
            continue

        # Collect paragraph (non-empty lines until blank)
        if line.strip() and current_section not in _SKIP_SECTIONS:
            para_lines = []
            start_idx = i
            while i < len(lines) and lines[i].strip():
                para_lines.append(lines[i])
                i += 1
            para_text = "\n".join(para_lines)
            # Only consider substantial paragraphs (>80 chars)
            if len(para_text) > 80 and not para_text.startswith("!["):
                paragraphs.append(
                    {
                        "text": para_text,
                        "line_idx": start_idx,
                        "section": current_section,
                        "keywords": _significant_keywords(para_text),
                    }
                )
        else:
            i += 1

    if not paragraphs:
        return paper_text

    # Match images to paragraphs via keyword overlap
    placements: list[tuple[int, SourceImage]] = []  # (line_idx_after, image)
    used_paragraphs: set[int] = set()
    used_images: set[str] = set()

    for img in candidates:
        if len(placements) >= max_images:
            break
        if img.url in used_images:
            continue

        best_score = 0
        best_para_idx = -1

        for pi, para in enumerate(paragraphs):
            if pi in used_paragraphs:
                continue
            overlap = len(img.keywords & para["keywords"])
            if overlap > best_score:
                best_score = overlap
                best_para_idx = pi

        # Require minimum 2 keyword overlap
        if best_score >= 2 and best_para_idx >= 0:
            para = paragraphs[best_para_idx]
            # Find the end of this paragraph in the original lines
            end_idx = para["line_idx"]
            while end_idx < len(lines) and lines[end_idx].strip():
                end_idx += 1

            placements.append((end_idx, img))
            used_paragraphs.add(best_para_idx)
            used_images.add(img.url)

    if not placements:
        return paper_text

    # Sort placements by line index (descending) to insert bottom-up
    placements.sort(key=lambda p: p[0], reverse=True)

    for line_idx, img in placements:
        image_md = f"\n![{img.alt_text}]({img.url})\n*{img.attribution}*\n"
        lines.insert(line_idx, image_md)

    return "\n".join(lines)
