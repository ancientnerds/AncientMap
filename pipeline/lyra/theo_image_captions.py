"""Deterministic caption builder + markdown inserter for probative images.

Captions are built from source metadata only. The IllustrationSpecialist's
rationale is the single LLM-written field — produced BEFORE the image was seen,
so it describes WHY the image matters for the claim, not what the image
visually contains. No generative description ever reaches the paper.
"""

from __future__ import annotations

import re

from pipeline.lyra.image_fetcher import ImageCandidate

_SOURCE_LABEL = {
    "wikimedia": "Wikimedia Commons",
    "met": "The Met / Open Access",
    "met_museum": "The Met / Open Access",
    "loc": "Library of Congress",
    "europeana": "Europeana",
    "getty": "Getty Museum",
    "getty_museum": "Getty Museum",
    "louvre": "Musée du Louvre",
    "pas": "Portable Antiquities Scheme",
}


def build_caption(cand: ImageCandidate, rationale: str) -> str:
    """Assemble the single-line caption placed below the image.

    Format: *{Title} — {Institution}. Photo: {Artist} / {Source} / {License}. {Rationale}.*
    Missing fields (e.g. Artist) are omitted rather than guessed.
    """
    parts_lead: list[str] = []
    if cand.title:
        parts_lead.append(cand.title)
    if parts_lead:
        lead = "; ".join(parts_lead)
    else:
        lead = "Untitled image"

    attribution: list[str] = []
    if cand.artist:
        attribution.append(cand.artist)
    attribution.append(_SOURCE_LABEL.get(cand.source, cand.source.title()))
    if cand.license:
        attribution.append(cand.license)

    photo_line = " / ".join(attribution)
    rationale_clean = (rationale or "").strip().rstrip(".")
    pieces = [lead, f"Photo: {photo_line}"]
    if rationale_clean:
        pieces.append(rationale_clean)
    return "*" + ". ".join(pieces) + ".*"


def image_markdown(
    cand: ImageCandidate,
    image_path_web: str,
    rationale: str,
) -> str:
    """Build the full markdown block: alt-texted image + caption line."""
    alt = (cand.title or "Research image").replace("]", "")
    caption = build_caption(cand, rationale)
    return f"![{alt}]({image_path_web})\n\n{caption}\n"


def find_section_for_claim(paper_text: str, claim_text: str) -> str | None:
    """Return the heading name of the ## section containing the claim, or None.

    Matching strategy:
    1. Look for the claim's first substantive 40-char phrase verbatim in prose.
    2. Walk back to find the nearest preceding ## heading.

    Uses literal substring match (no fuzzy matching) — claims are emitted into
    prose by the paper handler with minor edits at most; if the match fails,
    the handler just skips that opportunity rather than guessing.
    """
    if not claim_text:
        return None
    # Use the first distinctive chunk; skip short framing words
    words = claim_text.strip().split()
    if len(words) < 3:
        return None
    needle = " ".join(words[:6])[:60]
    idx = paper_text.find(needle)
    if idx == -1:
        return None
    # Walk backward to find the most recent ## heading
    heading_iter = list(re.finditer(r"^##\s+(.+)$", paper_text[:idx], re.MULTILINE))
    if not heading_iter:
        return None
    return heading_iter[-1].group(1).strip()


def find_section_for_citation(paper_text: str, citation_number: int) -> str | None:
    """Return the ## section containing `[N]`, or None if absent.

    More robust than find_section_for_claim — citation markers survive LLM
    prose rewriting intact, while the original claim text often gets
    paraphrased. Use this when the paper has been through finalize_references.

    Example: if source_id X maps to reference number 7 in the registry, and
    the paper cites [7] inside the "Sky Beings" section, this returns
    "Sky Beings".
    """
    if citation_number < 1:
        return None
    needle = f"[{citation_number}]"
    # Find the FIRST occurrence in prose, not the References section
    refs_idx = paper_text.find("## References")
    prose = paper_text[:refs_idx] if refs_idx > 0 else paper_text
    idx = prose.find(needle)
    if idx == -1:
        return None
    heading_iter = list(re.finditer(r"^##\s+(.+)$", prose[:idx], re.MULTILINE))
    if not heading_iter:
        return None
    return heading_iter[-1].group(1).strip()


def find_section_for_claim_with_registry(
    paper_text: str,
    source_ids: list[str],
    registry,
) -> str | None:
    """Preferred section resolver: uses the paper's citation markers as anchors.

    For each of the claim's source_ids, look up its reference number via the
    registry, then find the first `[N]` occurrence in prose and walk back to
    the nearest `##` heading. If any source_id resolves to a section, use it.

    Falls back to None if no source_id has a citation in the prose (e.g. the
    claim never survived verification into the final paper — in which case no
    image should be inserted anyway).
    """
    for sid in source_ids or []:
        num = registry.reference_numbers.get(sid) if registry else None
        if not num:
            continue
        section = find_section_for_citation(paper_text, int(num))
        if section:
            return section
    return None


def insert_image_after_section(
    paper_text: str,
    section_heading: str,
    image_markdown: str,
) -> str:
    """Place image_markdown at the end of the named ## section, before the next ##.

    If the named section isn't found, return paper_text unchanged.
    """
    pattern = re.compile(
        r"(^##\s+" + re.escape(section_heading) + r"\s*$)([\s\S]*?)(?=^##\s|\Z)",
        re.MULTILINE,
    )
    m = pattern.search(paper_text)
    if not m:
        return paper_text
    start, end = m.span()
    # Insert image before the next ## heading (or end-of-text)
    body = paper_text[start:end].rstrip()
    replacement = f"{body}\n\n{image_markdown.rstrip()}\n\n"
    return paper_text[:start] + replacement + paper_text[end:]
