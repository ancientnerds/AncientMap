"""Deterministic caption builder + markdown inserter for probative images.

Captions are built from source metadata only — the illustration specialist's
rationale is only a short relevance hint appended after title/photo, capped at
15 words and stripped of argumentative openers ("this provides / supports /
demonstrates ..."). No generative image description ever reaches the paper.
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

# Leading phrases that turn a descriptive line into argumentative prose.
# Stripped from rationale before it lands in the caption.
_ARGUE_OPENER_RE = re.compile(
    r"^\s*(?:this\s+)?"
    r"(?:provides?|supports?|demonstrates?|shows?\s+that|proves?|confirms?|"
    r"illustrates?\s+(?:the\s+claim\s+that|that))\s+",
    re.IGNORECASE,
)


def _trim_relevance(rationale: str) -> str:
    """Normalise the LLM rationale into a short, descriptive caption tail.

    - Takes the first sentence only.
    - Strips argumentative openers so "This provides verifiable visual evidence
      that Egyptians encoded..." collapses to "Egyptians encoded...".
    - Hard-caps at 15 words (suffix with `…` if truncated).
    """
    if not rationale:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", rationale.strip(), maxsplit=1)[0]
    stripped = _ARGUE_OPENER_RE.sub("", first_sentence).strip().rstrip(".")
    if not stripped:
        return ""
    words = stripped.split()
    if len(words) <= 15:
        return stripped
    return " ".join(words[:15]) + "…"


def build_caption(cand: ImageCandidate, rationale: str) -> str:
    """Assemble the single-line caption placed below the image.

    Format (empty pieces are dropped):
        *{Title}. Photo: {Artist} / {Source}. {Short description or relevance}.*

    Description precedence (second position):
      1. `cand.description` from the source, if present and ≤120 chars.
      2. Otherwise `_trim_relevance(rationale)` — 15-word cap, no "this proves X".

    The image's license is tracked on ImageCandidate (needed for compliance)
    but intentionally NOT rendered — readers don't care about CC BY-SA 4.0,
    and the [Source] link below the caption takes them to the original image
    page where the license is shown in context.
    """
    lead = cand.title if cand.title else "Untitled image"

    attribution: list[str] = []
    if cand.artist:
        attribution.append(cand.artist)
    attribution.append(_SOURCE_LABEL.get(cand.source, cand.source.title()))
    photo_line = " / ".join(attribution)

    tail: str = ""
    source_desc = (getattr(cand, "description", "") or "").strip()
    if source_desc and len(source_desc) <= 120:
        tail = source_desc.rstrip(".")
    if not tail:
        tail = _trim_relevance(rationale)

    pieces = [lead, f"Photo: {photo_line}"]
    if tail:
        pieces.append(tail)
    return "*" + ". ".join(pieces) + ".*"


def image_markdown(
    cand: ImageCandidate,
    image_path_web: str,
    rationale: str,
) -> str:
    """Build the full markdown block: alt-texted image + caption line + source link.

    [Source] points to the image's origin page (cand.url) — the Wikimedia
    Commons file page, Met object page, Europeana record etc. — NOT the
    license template URL. Readers want to see where the image came from;
    license_url is only a last-resort fallback.
    """
    alt = (cand.title or "Research image").replace("]", "")
    caption = build_caption(cand, rationale)
    source_url = getattr(cand, "url", "") or getattr(cand, "license_url", "")
    url_part = f"\n[Source]({source_url})" if source_url else ""
    return f"![{alt}]({image_path_web})\n\n{caption}{url_part}\n"


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


def resolve_section_heading(paper_text: str, guess: str) -> str | None:
    """Return the actual ## heading text in `paper_text` that matches `guess`.

    Tries exact match → case-insensitive match → substring match (either
    direction). The LLM illustration specialist often returns slight variants
    ("sky beings in ancient texts" vs "Sky Beings in Ancient Texts") and
    `insert_image_after_section` requires an exact match, so resolve the
    canonical heading first.
    """
    if not guess:
        return None
    headings = re.findall(r"^##\s+(.+?)\s*$", paper_text, re.MULTILINE)
    if not headings:
        return None
    guess_s = guess.strip()
    guess_lower = guess_s.lower()
    for h in headings:
        if h.strip() == guess_s:
            return h.strip()
    for h in headings:
        if h.strip().lower() == guess_lower:
            return h.strip()
    # Substring: prefer the shortest plausible match to avoid accidental hits
    candidates = [h.strip() for h in headings if guess_lower in h.strip().lower()]
    if candidates:
        return min(candidates, key=len)
    candidates = [h.strip() for h in headings if h.strip().lower() in guess_lower]
    if candidates:
        return min(candidates, key=len)
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


def insert_image_after_paragraph(
    paper_text: str,
    section_heading: str,
    anchor_text: str,
    image_md: str,
) -> str:
    """Place image_md immediately after the paragraph anchored by anchor_text.

    Strategy:
    1. Locate the named `## section_heading` block (from its heading line up to
       the next `## ` or end-of-text).
    2. Inside that block, find `anchor_text` verbatim.
    3. Walk forward from the match to the end of that paragraph (first blank
       line after the match).
    4. Insert `\\n\\n{image_md}\\n\\n` there.

    Returns `paper_text` unchanged on any mismatch (no section, no anchor).
    Prints a diagnostic so the handler log shows which anchor dropped.
    """
    if not section_heading or not anchor_text:
        return paper_text

    sec_pattern = re.compile(
        r"(^##\s+" + re.escape(section_heading) + r"\s*$)([\s\S]*?)(?=^##\s|\Z)",
        re.MULTILINE,
    )
    sec_m = sec_pattern.search(paper_text)
    if not sec_m:
        print(
            f"[probative] insert_image_after_paragraph: section '{section_heading}' not found",
            flush=True,
        )
        return paper_text

    sec_start, sec_end = sec_m.span()
    section_body = paper_text[sec_start:sec_end]

    needle = anchor_text.strip()
    if not needle:
        return paper_text
    rel_idx = section_body.find(needle)
    if rel_idx == -1:
        print(
            f"[probative] insert_image_after_paragraph: anchor '{needle[:40]}…' not "
            f"found in section '{section_heading}'",
            flush=True,
        )
        return paper_text

    # End of paragraph = next blank line after the anchor. Fall back to end of
    # section if the paragraph runs to the section boundary.
    search_from = rel_idx + len(needle)
    blank_m = re.search(r"\n\s*\n", section_body[search_from:])
    if blank_m:
        para_end_rel = search_from + blank_m.start()
    else:
        para_end_rel = len(section_body.rstrip())

    insert_pos = sec_start + para_end_rel
    before = paper_text[:insert_pos].rstrip()
    after = paper_text[insert_pos:].lstrip("\n")
    return f"{before}\n\n{image_md.rstrip()}\n\n{after}"
