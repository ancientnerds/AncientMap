"""
Markdown preparation for the public research papers.

The paper pages themselves render through React since the react-ssr
cutover (Task 12; Task 16 deleted the full-document renderers that lived
here). What stays Python is the stored-markdown massaging shared by the
paper route and its Medium copy (api/routes/research_html.py): reference
reflow, leading-title stripping and the Medium-safe caption rewrite.
"""

import re

from pipeline.lyra.theo_image_captions import _META_VOICE_RE

# What makes a paper public: reviewed and released, finished, and addressable.
# The one definition, shared by the SEO pages (api/routes/research_html.py)
# and the homepage hub snapshot (pipeline/static_exporter.py) so a paper
# cannot be listed in one place and 404 in the other. Expects the
# research_requests alias `r`.
PUBLIC_PAPER_WHERE = "r.is_public = TRUE AND r.status = 'completed' AND r.slug IS NOT NULL"

_REFERENCES_HEADING_RE = re.compile(
    r"^#{1,3}\s*(References|Sources|Bibliography)\b.*$", re.M | re.I
)
_BARE_URL_RE = re.compile(r"(?<![(<\[])(https?://[^\s<>()\[\]]+)")
_DOI_RE = re.compile(r"\bDOI:\s*(10\.\S+?)(?=[\s,;]|$)")


def format_references_md(content_md: str) -> str:
    """
    Rework the References section of a paper for clean rendering.

    Theo emits references as consecutive '[N] ...' lines with bare URLs —
    markdown collapses those into one giant paragraph with dead links.
    This gives each reference its own paragraph and turns bare URLs and
    DOIs into clickable links. Only text after the References heading is
    touched; the paper body stays untouched.
    """
    m = _REFERENCES_HEADING_RE.search(content_md)
    if not m:
        return content_md
    body, refs = content_md[: m.end()], content_md[m.end() :]
    refs = re.sub(r"\n(?=\[\d+\]\s)", "\n\n", refs)
    refs = _DOI_RE.sub(r"DOI: [\1](https://doi.org/\1)", refs)
    refs = _BARE_URL_RE.sub(r"<\1>", refs)
    return body + refs


# Image block as Theo stores it: image line, blank line, italic caption
# line, [Source](...) line.
_FIGURE_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<img>[^)\s]+)\)\s*\n\s*\n"
    r"\*(?P<cap>[^*\n]+)\*\s*\n"
    r"\[Source\]\((?P<src>[^)]+)\)"
)

# Editorial meta-voice that older papers baked into caption tails ("Lets the
# reader verify that...", "Image placed by the paper writer..."). The caption
# builder no longer emits these (theo_image_captions._META_VOICE_RE), but
# published papers carry them in stored markdown — scrub at render time.
_CAPTION_LEAK_RE = re.compile(
    r"\s*(?:Lets?\s+the\s+reader\s+verify\b|Allows?\s+the\s+reader\b|"
    r"Image\s+placed\s+by\s+the\s+paper\s+writer\b)[^*]*$",
    re.IGNORECASE,
)

# Caption + Source block WITHOUT a preceding image (reflow sometimes detaches
# writer-image captions). "Photo:" is required so normal italic emphasis in
# prose is never touched.
_ORPHAN_CAPTION_RE = re.compile(
    r"\*(?P<cap>[^*\n]*Photo:[^*\n]+)\*\s*\n\[Source\]\((?P<src>[^)]+)\)"
)

# Structural caption split: "{lead}. Photo: {artist} / {SOURCE_LABEL}. {tail}".
# The attribution always ends with a known source label; the tail (LLM
# rationale) never contains one — verified across all 10 published papers
# (2026-07-31). Greedy head = split at the LAST label, so artists like
# "Internet Archive Book Images" can't cut the attribution short.
_ATTRIBUTION_SPLIT_RE = re.compile(
    r"^(?P<head>.*Photo:.*"
    r"(?:Wikimedia Commons|Europeana|Open Access|Internet Archive|Getty Museum|"
    r"Musée du Louvre|Portable Antiquities Scheme|The Met|Smithsonian))"
    r"\.\s*(?P<tail>.+)$",
    re.S,
)


_LEADING_HEADING_RE = re.compile(r"^\s*(#{1,3})\s+([^\n]+)\n+")


def strip_leading_title_heading(content_md: str, title: str) -> str:
    """Papers begin with their own title as a markdown heading — 7 of 10
    stored papers use '## Title', 3 use '# Title' (checked 2026-07-31). The
    paper page and the Medium copy template render the title themselves, so
    the leading heading is stripped when it's an H1 (always the title in
    these papers) or when its text matches the paper title. A genuine
    section heading like '## Introduction' is never touched."""
    m = _LEADING_HEADING_RE.match(content_md)
    if not m:
        return content_md

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", s.casefold())

    if m.group(1) == "#" or norm(m.group(2)) == norm(title or ""):
        return content_md[m.end() :]
    return content_md


def _scrub_caption(raw_cap: str) -> str:
    """Scrub editorial meta-voice out of a stored caption.

    Generic scrub: drop any rationale tail after the attribution that talks
    about the paper/reader/evidence apparatus instead of the artifact (28
    leaked captions across 9 of 10 published papers, many phrasings —
    pattern lists don't scale).
    """
    cap = _CAPTION_LEAK_RE.sub("", raw_cap).strip()
    m = _ATTRIBUTION_SPLIT_RE.match(cap)
    if m and _META_VOICE_RE.search(m.group("tail")):
        cap = m.group("head")
    cap = cap.replace("Unknown authorUnknown author", "Unknown author")
    return cap.strip().rstrip(".")


# The reflow step sometimes splits a caption block INTO a sentence — the
# stored markdown then continues with "\n. The excitement was..." right
# after [Source](...). Consumed together with the caption block so no
# orphaned "." starts the following paragraph.
_STRAY_PERIOD = r"(?P<stray>\s*\n\.\s*)?"


def format_image_captions_medium(content_md: str) -> str:
    """
    Medium-paste-safe variant: Medium's editor DROPS figcaption content when
    pasting (images lost their captions entirely — observed 2026-07-31), but
    keeps italic text paragraphs. Rewrite caption blocks as scrubbed markdown:
    image, then '*caption.* [Source](url)' as its own paragraph.
    """

    def _cap_md(raw_cap: str, src: str) -> str:
        cap = _scrub_caption(raw_cap)
        lead = f"*{cap}.* " if cap else ""
        return f"{lead}[Source]({src})"

    def _fig(m: re.Match) -> str:
        alt = m.group("alt").split("|")[-1].strip()
        return f"![{alt}]({m.group('img')})\n\n{_cap_md(m.group('cap'), m.group('src'))}\n\n"

    result = _figure_re_with_stray().sub(_fig, content_md)

    def _orphan(m: re.Match) -> str:
        return f"{_cap_md(m.group('cap'), m.group('src'))}\n\n"

    return _orphan_re_with_stray().sub(_orphan, result)


def _figure_re_with_stray() -> re.Pattern:
    return re.compile(_FIGURE_BLOCK_RE.pattern + _STRAY_PERIOD)


def _orphan_re_with_stray() -> re.Pattern:
    return re.compile(_ORPHAN_CAPTION_RE.pattern + _STRAY_PERIOD)
