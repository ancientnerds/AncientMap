"""Shared helpers for meaningful-image selection.

Used by both offline tooling (scripts/pick_meaningful_gallery.py,
scripts/apply_meaningful_gallery.py) and any future production paths that
want primary-source artifact illustrations instead of thematically-relevant
stock images.

Three responsibilities:
  1. Fetch structured metadata from The Met + Wikimedia Commons APIs.
  2. Assemble a deterministic caption from that metadata — no LLM prose.
  3. Build the strict VLM prompt that asks whether an image LITERALLY depicts
     the paragraph's primary entity (not "thematically adjacent").

Intentionally sidesteps pipeline.lyra.image_fetcher.ImageCandidate because
that fetcher is wired for the lenient probative-images flow. This module is
source-API-first: we ask the museum for what it has, we don't scrape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote as _q
from urllib.parse import unquote

import httpx

UA = "AncientNerds-MeaningfulImages/1.0 (contact@ancientnerds.com)"


# ---------------------------------------------------------------------------
# Metadata container.
# ---------------------------------------------------------------------------


@dataclass
class SourceMetadata:
    kind: str  # "met" | "wikimedia" | "unknown"
    ok: bool
    title: str = ""
    artist: str = ""
    date: str = ""
    period: str = ""
    culture: str = ""
    medium: str = ""
    dimensions: str = ""
    classification: str = ""
    country: str = ""
    prose_description: str = ""  # curator paragraph or commons description
    primary_image_url: str = ""
    license: str = ""
    raw: dict = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# The Met — `/public/collection/v1/objects/{id}` returns structured fields.
# ---------------------------------------------------------------------------


async def fetch_met_metadata(client: httpx.AsyncClient, source_url: str) -> SourceMetadata:
    """Resolve a Met object page URL to its API record."""
    m = re.search(r"/search/(\d+)", source_url)
    if not m:
        return SourceMetadata(kind="met", ok=False, error=f"no object id in {source_url}")
    oid = m.group(1)
    try:
        r = await client.get(
            f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}",
            timeout=20.0,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        return SourceMetadata(kind="met", ok=False, error=f"met api: {e!r}")

    return SourceMetadata(
        kind="met",
        ok=True,
        title=d.get("title", "") or "",
        artist=d.get("artistDisplayName", "") or "",
        date=d.get("objectDate", "") or "",
        period=d.get("period", "") or "",
        culture=d.get("culture", "") or "",
        medium=d.get("medium", "") or "",
        dimensions=d.get("dimensions", "") or "",
        classification=d.get("classification", "") or "",
        country=d.get("country", "") or "",
        prose_description="",  # Met API has no curator prose field.
        primary_image_url=d.get("primaryImageSmall") or d.get("primaryImage", ""),
        license="CC0" if d.get("isPublicDomain") else "Met rights-reserved",
        raw={
            k: d.get(k)
            for k in (
                "objectID",
                "accessionNumber",
                "dynasty",
                "reign",
                "artistRole",
                "region",
                "subRegion",
                "locale",
            )
        },
    )


# ---------------------------------------------------------------------------
# Wikimedia Commons — imageinfo + extmetadata.
# ---------------------------------------------------------------------------


async def fetch_wikimedia_metadata(client: httpx.AsyncClient, source_url: str) -> SourceMetadata:
    """Resolve a Commons File: page URL to its extmetadata block."""
    # urlparse strips ';' as path-parameters — several Commons filenames
    # contain literal semicolons. Split on the literal "File:" marker.
    if "File:" not in source_url:
        return SourceMetadata(kind="wikimedia", ok=False, error=f"no File: segment in {source_url}")
    after = source_url.split("File:", 1)[1]
    after = after.split("?", 1)[0].split("#", 1)[0]
    file_title = "File:" + unquote(after)

    api_url = (
        "https://commons.wikimedia.org/w/api.php?action=query"
        f"&titles={_q(file_title, safe=':')}"
        "&prop=imageinfo&iiprop=url%7Cextmetadata%7Cmediatype"
        "&format=json&iiextmetadatamultilang=0&iiextmetadatalanguage=en"
    )
    try:
        r = await client.get(
            api_url,
            timeout=20.0,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return SourceMetadata(kind="wikimedia", ok=False, error=f"commons api: {e!r}")

    pages = data.get("query", {}).get("pages", {}) or {}
    if not pages:
        return SourceMetadata(kind="wikimedia", ok=False, error="no pages returned")
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        return SourceMetadata(
            kind="wikimedia",
            ok=False,
            error=f"no imageinfo; page={page.get('title')}",
        )
    info = page["imageinfo"][0]
    ext = info.get("extmetadata", {}) or {}

    def v(key: str) -> str:
        x = ext.get(key, {})
        raw = x.get("value", "") if isinstance(x, dict) else ""
        # Some Commons records still return language-keyed dicts even with
        # multilang=0 — fish out 'en' or fall back to the first value.
        if isinstance(raw, dict):
            raw = raw.get("en") or next(iter(raw.values()), "")
        stripped = re.sub(r"<[^>]+>", " ", str(raw))
        return re.sub(r"\s{2,}", " ", stripped).strip()

    # Commons ObjectName sometimes contains `label QS:Lxx,"..."` multilang
    # dumps or other junk. Use the bare filename when ObjectName is abusive.
    raw_name = v("ObjectName")
    if not raw_name or "label QS:" in raw_name or len(raw_name) > 160:
        raw_name = file_title.replace("File:", "")
    return SourceMetadata(
        kind="wikimedia",
        ok=True,
        title=raw_name,
        artist=v("Artist"),
        date=v("DateTimeOriginal") or v("DateTime"),
        period="",
        culture="",
        medium=v("ObjectType"),
        dimensions="",
        classification=v("GenreInformation"),
        country="",
        prose_description=v("ImageDescription"),
        primary_image_url=info.get("url", ""),
        license=v("LicenseShortName") or v("UsageTerms"),
        raw={
            "credit": v("Credit"),
            "attribution": v("Attribution"),
            "categories": v("Categories"),
        },
    )


# ---------------------------------------------------------------------------
# Image download.
# ---------------------------------------------------------------------------


async def download_bytes(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        r = await client.get(
            url,
            timeout=40.0,
            follow_redirects=True,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"  ! download failed ({url}): {e!r}")
        return None


# ---------------------------------------------------------------------------
# Deterministic caption — structured metadata only, no LLM prose.
# ---------------------------------------------------------------------------


def clean_title(t: str) -> str:
    """Strip file extension, upload-id parens, and underscores from a title.

    Mirrors `pipeline.lyra.theo_image_captions._clean_title` so Commons-sourced
    captions match the production style.
    """
    if not t:
        return ""
    s = t.strip()
    s = re.sub(r"\.(?:jpe?g|png|gif|webp|svg|tiff?|bmp)\s*$", "", s, flags=re.IGNORECASE)
    for _ in range(3):
        new = re.sub(r"\s*\(\d{6,}\)\s*$", "", s).rstrip()
        if new == s:
            break
        s = new
    s = re.sub(r"_+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ;,._-")
    return s


def build_deterministic_caption(meta: SourceMetadata) -> str:
    """Assemble a caption from structured metadata only.

    Shape (empty fields dropped):
        *{Title}, {date}. {artist/culture}. {medium}. {source} / {license}.*

    If the only date we have is ambiguous (an accession year, or an empty
    string), we drop it rather than making up a date. Same for artist — we
    only include one if the source structured it.
    """
    if not meta.ok:
        return f"*[metadata unavailable: {meta.error}]*"

    pieces: list[str] = []
    lead = clean_title(meta.title)
    if meta.date and re.search(r"\d", meta.date):
        lead = f"{lead}, {meta.date.strip()}" if lead else meta.date.strip()
    if lead:
        pieces.append(lead)

    attribution: list[str] = []
    if meta.artist and meta.artist.lower() not in {"unknown", "anonymous"}:
        attribution.append(meta.artist.strip())
    if meta.culture:
        attribution.append(meta.culture.strip())
    elif meta.period:
        attribution.append(meta.period.strip())
    if attribution:
        pieces.append(", ".join(attribution))

    descriptors: list[str] = []
    if meta.medium:
        descriptors.append(meta.medium.strip())
    if meta.classification and meta.classification.lower() not in {meta.medium.lower()}:
        descriptors.append(meta.classification.strip())
    if descriptors:
        pieces.append(" — ".join(descriptors))

    source_label = "The Met / Open Access" if meta.kind == "met" else "Wikimedia Commons"
    tail = source_label
    if meta.license:
        tail = f"{source_label} ({meta.license})"
    pieces.append(tail)

    # Preserve one short prose sentence if the source gave us one.
    if meta.prose_description and 20 < len(meta.prose_description) < 240:
        # Skip if it's the "Title - painting by X (MET, accession)" template
        if not re.fullmatch(r".+?\s-\s.+?\(MET,\s[^)]+\)", meta.prose_description.strip()):
            pieces.append(meta.prose_description.strip().rstrip("."))

    return "*" + ". ".join(p.rstrip(".") for p in pieces if p) + ".*"


# ---------------------------------------------------------------------------
# Source page URL reconstruction.
# ---------------------------------------------------------------------------


def source_page_url(meta: SourceMetadata) -> str:
    """Canonical viewer-facing URL for a metadata record."""
    if meta.kind == "met":
        oid = meta.raw.get("objectID") or ""
        return f"https://www.metmuseum.org/art/collection/search/{oid}" if oid else ""
    if meta.kind == "wikimedia":
        seg = meta.title if meta.title.startswith("File:") else f"File:{meta.title}"
        return f"https://commons.wikimedia.org/wiki/{seg.replace(' ', '_')}"
    return ""


# ---------------------------------------------------------------------------
# Strict VLM prompt — tighter than the historical probative-images gate.
# ---------------------------------------------------------------------------


STRICT_VLM_PROMPT = (
    "You are a strict factual-illustration judge for a research paper. "
    "Given an image and a paragraph claim, decide whether the image LITERALLY depicts "
    "the primary subject of the claim.\n\n"
    "Reject when the image shows a different artifact, different culture, different "
    "period, or a visually similar but unrelated subject (e.g. a European Renaissance "
    "portrait passed off as an illustration of a 20th-century psychologist). "
    "A generic period artifact is NOT an acceptable illustration for a claim about a "
    "specific named entity, theory, or event.\n\n"
    "EXTRA REJECTION RULES:\n"
    "- If the image is a generic diagram (Jungian archetypes, alchemical symbols, "
    "architectural schematics), it must depict the EXACT subject named in the text. "
    "Text about the 'wise old man' archetype + a 'wounded healer' archetype diagram = REJECT.\n"
    "- Reject decorative modern reproductions when an original artifact would be "
    "available for this subject. Pub signs, tourist replicas, fan art, and modern "
    "illustrations: REJECT unless the text is specifically about modern depictions. "
    "Period artifacts, museum-quality diagrams, and archaeological context photos: ACCEPT.\n\n"
    'Respond with STRICTLY valid JSON: {"primary_entity_in_claim": "...", '
    '"what_image_actually_shows": "...", "match": "exact|related|off_topic", '
    '"verdict": "meaningful|weak|misleading", "reason": "one sentence"}. '
    "Output only JSON, no prose around it."
)


def build_strict_vlm_prompt(paragraph: str, current_caption: str = "") -> str:
    return (
        f"{STRICT_VLM_PROMPT}\n\n"
        f"PARAGRAPH CLAIM:\n{paragraph}\n\n"
        f"CURRENT CAPTION (for reference, may be wrong):\n{current_caption or '(no caption)'}\n\n"
        "Now examine the attached image."
    )
