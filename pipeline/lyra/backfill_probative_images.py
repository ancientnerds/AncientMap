"""Backfill probative inline images for existing published research papers.

Runs `embed_probative_images()` against the stored `result_json.report` of
completed public papers that have no inline images yet. Because we no longer
have the original `image_candidate_pool` / `angles` / `registry` in storage,
every opportunity falls through to the on-demand `fetch_candidates` path —
slower than the live pipeline but behaves identically from the writer's POV.

`--replace` re-does papers that already HAVE images: their blocks are
stripped, the pipeline runs again, the hero is re-picked and files the new
set no longer references are deleted. Written for the 2026-08-31 image
rework — recovering the judge's middle verdict, widening the pre-filter and
flooring the hero size — which only takes effect on a fresh embed.

Usage:
    python -m pipeline.lyra.backfill_probative_images --slug SLUG            # dry run
    python -m pipeline.lyra.backfill_probative_images --slug SLUG --apply    # write
    python -m pipeline.lyra.backfill_probative_images --slug SLUG --apply --replace
    python -m pipeline.lyra.backfill_probative_images --apply                # ALL missing

Safety:
    Defaults to dry-run. When no slug is provided the command refuses to run
    unless `--all` is also passed, because probative embedding is
    LLM-expensive (one opportunity = several MiniMax calls). A paper that
    embeds nothing is left exactly as it was, `--replace` included.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

# Ensure pipeline is on path when invoked as a script
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.lyra.handlers.probative_images import embed_probative_images
from pipeline.lyra.hero_picker import pick_hero_image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


_INLINE_IMG_RE = re.compile(r"!\[(?!\s*[Cc]over\b)[^\]]*\]\(/data/research-images/[^)]+\)")


def _has_inline_images(report: str) -> bool:
    """True if the paper markdown already has inline probative images
    (excluding the cover).
    """
    return bool(_INLINE_IMG_RE.search(report))


def _strip_inline_images(report: str) -> str:
    """Remove every probative image block, leaving prose and references.

    Reuses the two regexes that already describe these shapes rather than
    inventing a third: `_BLOCK_RE` for an image with its caption, and the
    renderer's `_ORPHAN_CAPTION_RE` for captions detached from any image.
    The second is not optional — galleries stack several captions under one
    image, so a block-anchored sweep alone leaves the later ones behind.

    The cover is not a probative image and stays.
    """
    from pipeline.lyra.clean_image_titles import _BLOCK_RE
    from pipeline.research_html_renderer import _ORPHAN_CAPTION_RE

    def _drop_block(m: re.Match) -> str:
        alt = m.group("alt") or ""
        return m.group(0) if alt.strip().lower().startswith("cover") else ""

    out = _BLOCK_RE.sub(_drop_block, report)
    out = _ORPHAN_CAPTION_RE.sub("", out)
    # Collapse the blank-line runs the removals leave behind.
    return re.sub(r"\n{3,}", "\n\n", out)


def _fetch_papers(slug: str | None = None) -> list[dict]:
    """Fetch public completed papers, optionally filtered by slug."""
    with engine.connect() as conn:
        if slug:
            rows = conn.execute(
                text(
                    """
                    SELECT id::text, slug, question, result_json
                    FROM research_requests
                    WHERE slug = :slug AND is_public = TRUE AND status = 'completed'
                    """
                ),
                {"slug": slug},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    """
                    SELECT id::text, slug, question, result_json
                    FROM research_requests
                    WHERE is_public = TRUE AND status = 'completed'
                    ORDER BY published_at DESC
                    """
                )
            ).fetchall()
        return [
            {
                "id": r.id,
                "slug": r.slug,
                "question": r.question,
                "result_json": r.result_json,
            }
            for r in rows
        ]


def _delete_unreferenced_images(paper_id: str, embedded: list[dict]) -> int:
    """Delete image files the replaced paper no longer references.

    Replace mode re-downloads under fresh names, so the previous set would
    otherwise linger on disk forever. Only this paper's own directory is
    touched, and only files absent from the new set.
    """
    from pipeline.lyra.handlers.probative_images import IMAGES_DIR

    paper_dir = IMAGES_DIR / paper_id
    if not paper_dir.is_dir():
        return 0
    keep = {Path(e.get("web_path", "")).name for e in embedded if e.get("web_path")}
    removed = 0
    for f in paper_dir.iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


async def _process_paper(paper: dict, apply: bool, replace: bool = False) -> tuple[str, bool, str]:
    """Embed probative images for one paper. Returns (slug, changed, reason)."""
    slug = paper["slug"]
    paper_id = paper["id"]
    question = paper.get("question", "") or ""

    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, False, "invalid result_json (skipping)")

    report = result.get("report", "")
    if not report:
        return (slug, False, "empty report (skipping)")
    if _has_inline_images(report):
        if not replace:
            return (slug, False, "already has inline images")
        report = _strip_inline_images(report)

    if not apply:
        # Dry-run: we don't want to burn LLM + MiniMax calls just to report.
        return (slug, False, "WOULD BACKFILL (dry-run)")

    new_report, embedded, diversity, _strategy_counts, _skip_reasons = await embed_probative_images(
        paper_id=paper_id,
        paper_text=report,
        question=question,
        angles=[],  # not persisted — forces on-demand fetch fallback
        registry=None,
        image_candidate_pool={},  # empty pool — same effect
    )

    if not embedded:
        # In replace mode the old images are already stripped from `report`,
        # but `result` is only written below — a paper that produced nothing
        # keeps exactly what it had.
        return (slug, False, "no images embedded (on-demand fetch returned no safe candidates)")

    result["report"] = new_report
    if replace:
        result["probative_images"] = list(embedded)
        # The old hero points into the set we just replaced; leaving it would
        # reference a file no longer in the paper. Both keys matter: a
        # published paper renders `published_hero_image` (api/routes/theo.py).
        hero = pick_hero_image(result.get("title") or question, embedded)
        result["hero_image"] = hero
        if "published_hero_image" in result:
            result["published_hero_image"] = hero
        _delete_unreferenced_images(paper_id, embedded)
    else:
        result.setdefault("probative_images", []).extend(embedded)
    result["probative_images_diversity"] = diversity

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper_id},
        )
        conn.commit()

    return (
        slug,
        True,
        f"embedded {len(embedded)} images "
        f"(sources: {', '.join(diversity.get('sources', [])) or 'n/a'})",
    )


async def backfill(slug: str | None, apply: bool, process_all: bool, replace: bool = False) -> None:
    """Run the backfill."""
    if replace:
        logger.info("REPLACE MODE — existing images are stripped and re-embedded")
    if not apply:
        logger.info("DRY RUN — no changes written (use --apply to confirm)")

    if slug:
        papers = _fetch_papers(slug)
    elif process_all:
        papers = _fetch_papers()
    else:
        logger.error(
            "Refusing to run without --slug or --all. Probative embedding is LLM-expensive."
        )
        return

    if not papers:
        logger.info("No papers found.")
        return

    logger.info("Found %d paper(s) to check", len(papers))

    results: list[tuple[str, bool, str]] = []
    for paper in papers:
        logger.info("Checking: %s", paper["slug"])
        result = await _process_paper(paper, apply, replace=replace)
        results.append(result)
        status = "CHANGED" if result[1] else result[2].upper()
        logger.info("  -> %s", status)
        if result[1]:
            logger.info("     %s", result[2])

    changed = [r for r in results if r[1]]
    skipped = [r for r in results if not r[1] and "already" in r[2]]
    would = [r for r in results if not r[1] and "WOULD" in r[2]]
    failed = [r for r in results if not r[1] and "already" not in r[2] and "WOULD" not in r[2]]

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("  Total checked: %d", len(results))
    logger.info("  Images added: %d", len(changed))
    logger.info("  Already had inline images: %d", len(skipped))
    if not apply:
        logger.info("  Would backfill on --apply: %d", len(would))
    logger.info("  Skipped/failed: %d", len(failed))

    if not apply and would:
        logger.info("")
        logger.info("Run with --apply to embed images in these papers:")
        for s, _, _ in would:
            logger.info("  - %s", s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill probative inline images")
    parser.add_argument("--slug", type=str, default=None, help="Process only this slug")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every missing paper (required when --slug not given)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes to DB (default is dry-run)"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Strip the paper's existing images and re-embed from scratch, "
            "re-picking the hero. Without this, papers that already have "
            "images are skipped."
        ),
    )
    args = parser.parse_args()

    asyncio.run(
        backfill(slug=args.slug, apply=args.apply, process_all=args.all, replace=args.replace)
    )
