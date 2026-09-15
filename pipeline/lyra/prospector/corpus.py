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


@dataclass(frozen=True)
class StoryUnit:
    """One news item, reconstructed deterministically so offsets stay valid."""

    item_id: int
    video_id: str
    timestamp_seconds: int | None
    text: str

    @property
    def locator(self) -> str:
        url = f"https://www.youtube.com/watch?v={self.video_id}"
        return f"{url}&t={self.timestamp_seconds}s" if self.timestamp_seconds else url


def story_text(headline: str | None, summary: str | None, facts: list | None) -> str:
    """headline + summary + facts, joined with single newlines. This is THE
    stored form every story offset indexes; never change the joiner."""
    parts = [headline or "", summary or ""]
    parts.extend(f for f in (facts or []) if isinstance(f, str) and f.strip())
    return "\n".join(p.strip() for p in parts if p and p.strip())


def load_stories(
    session, *, unprospected_only: bool = True, limit: int | None = None
) -> list[StoryUnit]:
    where = "prospected_at IS NULL" if unprospected_only else "TRUE"
    rows = session.execute(
        sql(f"""
        SELECT id, video_id, timestamp_seconds, headline, summary, facts
        FROM news_items WHERE {where}
        ORDER BY id
        {"LIMIT :limit" if limit else ""}
        """),
        {"limit": limit} if limit else {},
    ).fetchall()
    return [
        StoryUnit(r.id, r.video_id, r.timestamp_seconds, story_text(r.headline, r.summary, r.facts))
        for r in rows
    ]


def mark_prospected(session, item_ids: list[int]) -> None:
    if item_ids:
        session.execute(
            sql("UPDATE news_items SET prospected_at = NOW() WHERE id = ANY(:ids)"),
            {"ids": item_ids},
        )


def paragraph_bounds(text: str, index: int) -> tuple[int, int]:
    """(start, end) of the paragraph containing `index`."""
    start = text.rfind(_PARAGRAPH_BREAK, 0, index)
    start = 0 if start == -1 else start + len(_PARAGRAPH_BREAK)
    end = text.find(_PARAGRAPH_BREAK, index)
    return start, (len(text) if end == -1 else end)
