"""Corpus units for the prospector: what text the extractor is shown.

A unit is (source_table, source_pk, text, locator). The stored text is the
ground truth every evidence offset indexes, so NOTHING here deletes
characters: regions the model must not read (the reference list, markdown
image markup with its museum-caption noise) are MASKED with spaces of the
same length. An offset into the masked window is an offset into the stored
text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text as sql

from pipeline.lyra.theo_citations import _REFS_HEADING_RE

# Markdown image: ![alt text](/data/research-images/...). Alt text is where
# "The Jordan Museum, Amman" lives — masked, never shown to the model.
_FIGURE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_ENWIKI_URL_RE = re.compile(r"https?://en\.wikipedia\.org/wiki/[^\s)\]>\"']+")
_PARAGRAPH_BREAK = "\n\n"

WINDOW_CHARS = 8000


@dataclass(frozen=True)
class PaperUnit:
    request_id: str
    slug: str
    text: str  # the stored published_report, verbatim

    @property
    def locator_base(self) -> str:
        return f"/research/{self.slug}"


@dataclass(frozen=True)
class Window:
    """A slice of a unit's masked text, with its absolute start offset."""

    abs_start: int
    text: str


def load_public_papers(session, *, slug: str | None = None) -> list[PaperUnit]:
    """Published papers as units. Only rows that carry `published_report`
    (25 on prod; the 3 unpublished rows have only `report` and are skipped
    on purpose — the public page renders published_report, see the
    published-report-trap note)."""
    where = "r.is_public AND r.result_json::jsonb ? 'published_report'"
    params: dict = {}
    if slug:
        where += " AND r.slug = :slug"
        params["slug"] = slug
    rows = session.execute(
        sql(f"""
        SELECT r.id::text AS id, r.slug, r.result_json::jsonb->>'published_report' AS body
        FROM research_requests r
        WHERE {where}
        ORDER BY r.published_at DESC NULLS LAST
        """),
        params,
    ).fetchall()
    return [PaperUnit(r.id, r.slug, r.body) for r in rows if r.body]


def mask_paper(body: str) -> tuple[str, str]:
    """Return (masked_body, references_region).

    The references region starts at the LAST `## References` / `## Sources`
    heading (final artifacts split on the last one, mirroring the frontend's
    splitBodyAndRefs). It is masked from the model's view and returned
    separately so its Wikipedia URLs can be harvested for free.
    """
    refs_start = None
    for m in _REFS_HEADING_RE.finditer(body):
        refs_start = m.start()
    refs = body[refs_start:] if refs_start is not None else ""
    masked = body if refs_start is None else body[:refs_start] + " " * len(refs)
    masked = _FIGURE_RE.sub(lambda m: " " * len(m.group(0)), masked)
    return masked, refs


def harvest_wiki_urls(refs: str) -> list[str]:
    """Distinct English-Wikipedia article URLs cited in the references."""
    return list(dict.fromkeys(_ENWIKI_URL_RE.findall(refs)))


def windows(masked: str, size: int = WINDOW_CHARS) -> list[Window]:
    """Split on paragraph boundaries into windows of at most `size` chars.

    A single paragraph longer than `size` is split at the last newline or
    space before the limit, so no window ever cuts inside a word. Windows
    that are whitespace-only (a fully masked region) are dropped.
    """
    out: list[Window] = []
    pos = 0
    n = len(masked)
    while pos < n:
        end = min(pos + size, n)
        if end < n:
            cut = masked.rfind(_PARAGRAPH_BREAK, pos, end)
            if cut <= pos:
                cut = masked.rfind("\n", pos, end)
            if cut <= pos:
                cut = masked.rfind(" ", pos, end)
            if cut > pos:
                end = cut
        chunk = masked[pos:end]
        if chunk.strip():
            out.append(Window(pos, chunk))
        pos = end
        while pos < n and masked[pos] in " \n":
            pos += 1
    return out


def paragraph_bounds(text: str, index: int) -> tuple[int, int]:
    """(start, end) of the paragraph containing `index`."""
    start = text.rfind(_PARAGRAPH_BREAK, 0, index)
    start = 0 if start == -1 else start + len(_PARAGRAPH_BREAK)
    end = text.find(_PARAGRAPH_BREAK, index)
    return start, (len(text) if end == -1 else end)
