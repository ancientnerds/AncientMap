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

# Words that reveal editorial meta-voice: a caption tail talking about the
# paper/reader/image apparatus instead of the depicted artifact ("Lets the
# reader verify that...", "supports the passage's claim..."). Such tails are
# dropped entirely — a caption without a tail beats one that editorializes.
_META_VOICE_RE = re.compile(
    r"\b(?:readers?|writers?|papers?|passages?|captions?|images?|figures?|viewers?|"
    r"sections?|arguments?|claims?|verif\w*|evidence)\b",
    re.IGNORECASE,
)

# Raw Wikimedia Commons titles arrive as filenames like
# `Himmelsscheibe.jpg` or `Mexican_antiquities_(14781541291).jpg`. Strip the
# extension, any trailing 6+ digit upload-id paren group, and convert
# underscores to spaces so captions read like titles, not filenames.
_TITLE_EXT_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|tiff?|bmp)\s*$", re.IGNORECASE)
_TITLE_ID_SUFFIX_RE = re.compile(r"\s*\(\d{6,}\)\s*$")
_TITLE_UNDERSCORE_RE = re.compile(r"_+")


def _clean_title(title: str) -> str:
    """Turn a raw source title into a human-readable caption lead.

    Wikimedia Commons returns page titles verbatim ("File:Some_Thing.jpg"),
    which looks awful in a caption. We strip the image extension, drop any
    trailing `(14781541291)` upload-id tag, collapse underscores to spaces,
    and trim stray punctuation.
    """
    if not title:
        return ""
    cleaned = title.strip()
    cleaned = _TITLE_EXT_RE.sub("", cleaned)
    # Iterate in case there's more than one trailing id group
    for _ in range(3):
        new = _TITLE_ID_SUFFIX_RE.sub("", cleaned).rstrip()
        if new == cleaned:
            break
        cleaned = new
    cleaned = _TITLE_UNDERSCORE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ;,._-")
    return cleaned


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
    if not stripped or _META_VOICE_RE.search(stripped):
        return ""
    words = stripped.split()
    if len(words) <= 15:
        return stripped
    return " ".join(words[:15]) + "…"


def _sanitize_caption_field(text: str) -> str:
    """Make a caption-component safe to embed inside the outer ``*...*`` italic
    wrapper. Strips markdown delimiters that would otherwise close/reopen the
    italic mid-caption, collapses newlines and runs of whitespace to single
    spaces, and drops obvious duplication patterns coming out of Wikimedia
    Commons' wikitext attribution strings.

    Wikimedia files like ``File:Moyen_Orient_Amarna_1.png`` ship an Artist
    field that looks like ``Moyen_Orient_Amarna_1.svg: *Middle_East_topographic
    _map-blank.svg: Sémhur (talk)\\nderivative work: Zunkir (talk)\\nderivative
    work: Zunkir (talk)``. Wrapping that in ``*...*`` produces literal embedded
    ``*`` and newlines, which break the frontend's caption regex
    (``galleryParser.ts: FIGURE_RE``) and spill the whole attribution chain
    into the prose body below the image. This helper neutralises all three.
    """
    if not text:
        return ""
    # 1. Replace underscores (common in Wikimedia filenames) with spaces
    #    BEFORE we drop markdown delimiters; underscores in markdown act as
    #    italic delimiters too, so we want them gone, but `Moyen_Orient_Amarna_1`
    #    looks better as `Moyen Orient Amarna 1` than `MoyenOrientAmarna1`.
    cleaned = text.replace("_", " ")
    # 2. Drop the remaining markdown delimiters that would close the outer
    #    italic wrapper or reopen formatting mid-caption.
    cleaned = re.sub(r"[*`~]+", "", cleaned)
    # 3. Collapse all whitespace (newlines, tabs, runs of spaces) to one space.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 4. Collapse trivially repeated phrases like
    #    "derivative work: Zunkir (talk) derivative work: Zunkir (talk)" into
    #    a single occurrence. Wikimedia's wikitext attribution chains often
    #    double-up like this when a derivative is itself derived.
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"(\S(?:.{4,80}?\S)?)\s+\1(?=\s|$|[.;])", r"\1", cleaned)
    return cleaned


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
    lead = _sanitize_caption_field(_clean_title(cand.title)) or "Untitled image"

    attribution: list[str] = []
    artist_clean = _sanitize_caption_field(cand.artist or "")
    if artist_clean:
        attribution.append(artist_clean)
    attribution.append(_SOURCE_LABEL.get(cand.source, cand.source.title()))
    photo_line = " / ".join(attribution)

    tail: str = ""
    source_desc = (getattr(cand, "description", "") or "").strip()
    if source_desc and len(source_desc) <= 120:
        tail = _sanitize_caption_field(source_desc.rstrip("."))
    if not tail:
        tail = _sanitize_caption_field(_trim_relevance(rationale))

    pieces = [lead, f"Photo: {photo_line}"]
    if tail:
        pieces.append(tail)
    return "*" + ". ".join(pieces) + ".*"


def _encode_parens(url: str) -> str:
    """Percent-encode literal ``(`` and ``)`` so markdown ``[label](url)`` parsing
    doesn't truncate at the first `)` inside the URL.

    Wikimedia Commons filenames routinely contain parens, e.g.
    ``File:Mexican_antiquities_(1904)_(14781541291).jpg``. Every markdown
    parser (ours, ReactMarkdown, CommonMark) reads the first unescaped `)` as
    the link terminator, leaving the remainder of the URL as raw text in the
    prose. Encoding just these two chars fixes it without touching legitimate
    `/`, `?`, or `#` in the URL. Browsers decode %28/%29 transparently.
    """
    return url.replace("(", "%28").replace(")", "%29") if url else url


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
    alt = (_clean_title(cand.title) or "Research image").replace("]", "")
    caption = build_caption(cand, rationale)
    source_url = _encode_parens(getattr(cand, "url", "") or getattr(cand, "license_url", ""))
    src_path = _encode_parens(image_path_web)
    url_part = f"\n[Source]({source_url})" if source_url else ""
    return f"![{alt}]({src_path})\n\n{caption}{url_part}\n"


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


def _normalize_for_match(text: str) -> str:
    """Normalize prose for fuzzy anchor matching.

    Strips citation markers `[N]`, italic `*x*`, bold `**x**`, collapses
    whitespace, lowercases. Leaves alphanumerics + spaces. Used by the
    multi-strategy `insert_image_after_paragraph` to recover from minor
    rewrites between opportunity selection and embed time (most often
    `[N]` markers injected by the audit/strip pass).
    """
    if not text:
        return ""
    # Strip citation markers and emphasis runs first so they don't bleed into
    # the alphanumeric pass below.
    t = re.sub(r"\[\d+\]", " ", text)
    t = re.sub(r"\*+([^*]+)\*+", r"\1", t)
    # Lowercase + collapse non-alphanumerics to single spaces.
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return t.strip()


def insert_image_after_paragraph(
    paper_text: str,
    section_heading: str,
    anchor_text: str,
    image_md: str,
) -> tuple[str, str]:
    """Place image_md immediately after the paragraph anchored by anchor_text.

    Returns `(new_paper_text, chosen_strategy)` where `chosen_strategy` is one
    of: `exact`, `normalized`, `first_sentence`, `section_fallback`, `failed`.

    Strategy ladder (try in order, stop at first match):

      1. **exact** — verbatim `section_body.find(anchor_text.strip())`. Works
         when prose hasn't been rewritten since opportunity selection.
      2. **normalized** — strip `[N]` markers / `*emphasis*` / `**bold**`,
         collapse whitespace, lowercase both sides. Catches the common
         mutation: an `[N]` was injected mid-paragraph after selection.
      3. **first_sentence** — take the first sentence of `anchor_text`
         (split on `.?!`) and search normalized. Catches mid-paragraph
         repairs that left the opening sentence intact.
      4. **section_fallback** — insert immediately before the next `##`
         heading (or end of prose). Image still lands in the right
         section even if no paragraph match worked.

    Returns `(paper_text, "failed")` ONLY if `section_heading` itself can't
    be located. With Strategy 4 always available, anchor mismatch within a
    located section never reaches `failed`.
    """
    if not section_heading or not anchor_text:
        return paper_text, "failed"

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
        return paper_text, "failed"

    sec_start, sec_end = sec_m.span()
    section_body = paper_text[sec_start:sec_end]
    needle_raw = anchor_text.strip()

    # ----- Strategy 1: exact match -----
    if needle_raw:
        rel_idx = section_body.find(needle_raw)
        if rel_idx != -1:
            return _insert_after_anchor(
                paper_text, sec_start, section_body, rel_idx, len(needle_raw), image_md
            ), "exact"

    # ----- Strategy 2: normalized match -----
    needle_norm = _normalize_for_match(needle_raw[:60])
    if needle_norm and len(needle_norm) >= 12:
        norm_body = _normalize_for_match(section_body)
        if needle_norm in norm_body:
            # Find the anchor in the ORIGINAL section_body by walking forward
            # token-by-token until normalized prefix matches.
            rel_idx = _find_normalized(section_body, needle_norm)
            if rel_idx is not None:
                return _insert_after_anchor(
                    paper_text, sec_start, section_body, rel_idx, len(needle_raw), image_md
                ), "normalized"

    # ----- Strategy 3: first-sentence match -----
    first_sentence = re.split(r"[.?!]", needle_raw, maxsplit=1)[0].strip()
    fs_norm = _normalize_for_match(first_sentence)
    if fs_norm and len(fs_norm) >= 12:
        norm_body = _normalize_for_match(section_body)
        if fs_norm in norm_body:
            rel_idx = _find_normalized(section_body, fs_norm)
            if rel_idx is not None:
                return _insert_after_anchor(
                    paper_text, sec_start, section_body, rel_idx, len(first_sentence), image_md
                ), "first_sentence"

    # ----- Strategy 4: section-end fallback -----
    print(
        f"[probative] insert_image_after_paragraph: anchor '{needle_raw[:40]}…' not "
        f"found in section '{section_heading}', falling back to section end",
        flush=True,
    )
    body = paper_text[sec_start:sec_end].rstrip()
    replacement = f"{body}\n\n{image_md.rstrip()}\n\n"
    return paper_text[:sec_start] + replacement + paper_text[sec_end:], "section_fallback"


def _find_normalized(haystack: str, needle_norm: str) -> int | None:
    """Locate `needle_norm` (already normalized) in `haystack` (raw prose) and
    return the raw character index where the match starts. Walks character by
    character building a normalized prefix until it contains `needle_norm`.

    Returns None if no match.
    """
    # Cheap pre-check: if needle_norm doesn't even appear in the normalized
    # haystack, no point walking.
    if needle_norm not in _normalize_for_match(haystack):
        return None

    # Walk haystack, maintaining a rolling normalized window. We can't use
    # straight indexing because normalization changes lengths.
    # Strategy: for each candidate start position, test whether the
    # normalized prefix from that position contains needle_norm at its head.
    nlen = len(needle_norm)
    # Try every position; cap at reasonable length to avoid quadratic blowup
    # on huge sections.
    for start in range(len(haystack)):
        # Take a chunk roughly 3x needle length (normalization can't expand
        # text) and normalize it. If it starts with needle_norm, we found it.
        chunk = haystack[start : start + nlen * 3 + 32]
        norm_chunk = _normalize_for_match(chunk)
        if norm_chunk.startswith(needle_norm):
            return start
    return None


def _insert_after_anchor(
    paper_text: str,
    sec_start: int,
    section_body: str,
    rel_idx: int,
    anchor_len: int,
    image_md: str,
) -> str:
    """Insert image_md after the paragraph that begins at `rel_idx` in
    `section_body`. Paragraph end = next blank line, or end of section."""
    search_from = rel_idx + anchor_len
    blank_m = re.search(r"\n\s*\n", section_body[search_from:])
    if blank_m:
        para_end_rel = search_from + blank_m.start()
    else:
        para_end_rel = len(section_body.rstrip())

    insert_pos = sec_start + para_end_rel
    before = paper_text[:insert_pos].rstrip()
    after = paper_text[insert_pos:].lstrip("\n")
    return f"{before}\n\n{image_md.rstrip()}\n\n{after}"
