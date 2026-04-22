"""Reflow probative images into paragraph-anchored positions.

Strips every inline image block from the stored paper, then re-inserts each
stored probative image immediately after the paragraph it illustrates (anchored
by `paragraph_text[:60]` inside `section_heading`). The cover image block at
the very top is left untouched.

Also dedupes stored `probative_images` by `source_url` — the live pipeline's
per-claim loop used to allow the same image (e.g. Dendera zodiac) to embed
twice. We collapse duplicates here and rewrite the stored list so future
backfills see the cleaned state.

No external API calls — uses stored metadata only.

Usage:
    python -m pipeline.lyra.reflow_images --slug SLUG             # dry-run
    python -m pipeline.lyra.reflow_images --slug SLUG --apply     # write
    python -m pipeline.lyra.reflow_images --all --apply           # every public paper
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_image_captions import (
    image_markdown,
    insert_image_after_paragraph,
    resolve_section_heading,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# Matches every inline image block under /data/research-images/ and its
# optional caption + [Source] trailer. Strips the legacy AI cover block too
# (alt "Cover" or path ending /cover.png) — the hero banner is now picked
# from probative_images at render time, not stored in the markdown.
_STRIP_RE = re.compile(
    r"(?<!\S)"  # not preceded by non-whitespace (avoid matching inside prose)
    r"!\[(?P<alt>[^\]]*)\]\((?P<path>/data/research-images/[^)]+)\)"
    r"(?:\s*\n+\*(?P<caption>[^*\n][^*]*?)\*"
    r"(?:\s*\n\[Source\]\((?P<src>[^)]+)\))?)?"
    r"\s*\n*",
    re.MULTILINE,
)


def _cand_from_entry(entry: dict) -> ImageCandidate:
    """Reconstruct an ImageCandidate from a stored probative_images entry."""
    return ImageCandidate(
        url=entry.get("source_url", "") or "",
        source=entry.get("source_name", "") or "",
        title=entry.get("title", "") or "",
        description=entry.get("description", "") or "",
        artist=entry.get("artist", "") or "",
        license=entry.get("license", "") or "",
        license_url=entry.get("license_url", "") or "",
    )


def _strip_inline_images(report: str) -> tuple[str, int]:
    """Remove every inline image block. Returns (new_text, removed_count)."""
    removed = 0

    def _sub(_: re.Match) -> str:
        nonlocal removed
        removed += 1
        return ""

    new = _STRIP_RE.sub(_sub, report)
    # Collapse runs of 3+ newlines left behind by removed blocks
    new = re.sub(r"\n{3,}", "\n\n", new)
    return new, removed


def _dedupe_probative(entries: list[dict]) -> tuple[list[dict], int]:
    """Collapse entries that share a `source_url`.

    Keep the first occurrence (which, post-sort, is the earliest section +
    paragraph_index). Entries without a source_url are kept as-is.
    """
    seen: set[str] = set()
    out: list[dict] = []
    dropped = 0
    for e in entries:
        url = (e.get("source_url") or "").strip()
        if not url:
            out.append(e)
            continue
        if url in seen:
            dropped += 1
            continue
        seen.add(url)
        out.append(e)
    return out, dropped


def _sort_key(entry: dict) -> tuple[str, int]:
    """Place earlier sections first, then by paragraph_index inside each."""
    return (entry.get("section_heading") or "", int(entry.get("paragraph_index") or 0))


def _reflow_report(report: str, probative_images: list[dict]) -> tuple[str, dict]:
    """Strip old image blocks, re-insert surviving probative images in order.

    Returns (new_report, stats) where stats carries counts of removed blocks,
    deduped entries, reflowed images, and anchor-missing images.
    """
    stripped, removed = _strip_inline_images(report)
    entries = list(probative_images or [])
    entries.sort(key=_sort_key)
    deduped, dropped = _dedupe_probative(entries)

    reflowed = 0
    no_anchor = 0
    placed_paths: set[str] = set()
    current = stripped
    surviving: list[dict] = []

    for entry in deduped:
        web_path = entry.get("web_path") or ""
        if not web_path or web_path in placed_paths:
            continue
        section = entry.get("section_heading") or ""
        if section in ("[inline]",):
            # Writer-placed markers have no section anchor in the stored
            # report — skip cleanly. The writer-placed paragraph is gone too
            # because strip nuked the image marker.
            surviving.append(entry)
            continue

        anchor = (entry.get("paragraph_text") or "")[:60].strip()
        if not anchor:
            no_anchor += 1
            continue

        canonical = resolve_section_heading(current, section) or section
        cand = _cand_from_entry(entry)
        rationale = entry.get("rationale") or ""
        md = image_markdown(cand, web_path, rationale)

        new_current = insert_image_after_paragraph(current, canonical, anchor, md)
        if new_current == current:
            no_anchor += 1
            continue

        current = new_current
        placed_paths.add(web_path)
        reflowed += 1
        surviving.append(entry)

    stats = {
        "stripped": removed,
        "duplicates_collapsed": dropped,
        "reflowed": reflowed,
        "anchor_missing": no_anchor,
        "surviving_probative": surviving,
    }
    return current, stats


def _fetch_papers(slug: str | None) -> list[dict]:
    with engine.connect() as conn:
        if slug:
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE slug = :slug AND is_public = TRUE AND status = 'completed'"
                ),
                {"slug": slug},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    "SELECT id::text, slug, result_json FROM research_requests "
                    "WHERE is_public = TRUE AND status = 'completed' "
                    "ORDER BY published_at DESC"
                )
            ).fetchall()
    return [{"id": r.id, "slug": r.slug, "result_json": r.result_json} for r in rows]


def _process(paper: dict, apply: bool) -> tuple[str, dict, str]:
    slug = paper["slug"]
    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, {}, "invalid result_json")

    report = result.get("report", "") or ""
    probative = result.get("probative_images") or []
    if not report:
        return (slug, {}, "empty report")
    if not probative:
        return (slug, {}, "no probative_images to reflow")

    new_report, stats = _reflow_report(report, probative)
    if stats["reflowed"] == 0 and stats["duplicates_collapsed"] == 0:
        return (
            slug,
            stats,
            f"no change (stripped={stats['stripped']}, anchor_missing={stats['anchor_missing']})",
        )

    if not apply:
        return (
            slug,
            stats,
            f"would reflow {stats['reflowed']} image(s), "
            f"collapse {stats['duplicates_collapsed']} dup(s), "
            f"{stats['anchor_missing']} missing anchors (dry-run)",
        )

    result["report"] = new_report
    result["probative_images"] = stats["surviving_probative"]
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper["id"]},
        )
        conn.commit()
    return (
        slug,
        stats,
        f"reflowed {stats['reflowed']} image(s), "
        f"collapsed {stats['duplicates_collapsed']} dup(s), "
        f"{stats['anchor_missing']} missing anchors",
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Reflow probative images into paragraph anchors")
    p.add_argument("--slug", type=str, default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    if not args.slug and not args.all:
        logger.error("Refusing to run without --slug or --all")
        return

    if not args.apply:
        logger.info("DRY RUN — no changes written (use --apply to confirm)")

    papers = _fetch_papers(args.slug)
    if not papers:
        logger.info("No papers found.")
        return

    logger.info("Found %d paper(s)", len(papers))
    totals = {"reflowed": 0, "duplicates_collapsed": 0, "anchor_missing": 0}
    for paper in papers:
        slug, stats, reason = _process(paper, args.apply)
        logger.info("  %s — %s", slug, reason)
        for k in totals:
            totals[k] += int(stats.get(k, 0)) if stats else 0

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("  Images %s: %d", "reflowed" if args.apply else "would reflow", totals["reflowed"])
    logger.info("  Duplicates collapsed: %d", totals["duplicates_collapsed"])
    logger.info("  Anchor missing: %d", totals["anchor_missing"])


if __name__ == "__main__":
    main()
