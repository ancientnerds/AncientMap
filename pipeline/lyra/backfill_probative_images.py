"""Backfill probative inline images for existing published research papers.

Runs `embed_probative_images()` against the stored `result_json.report` of
completed public papers that have no inline images yet. Because we no longer
have the original `image_candidate_pool` / `angles` / `registry` in storage,
every opportunity falls through to the on-demand `fetch_candidates` path —
slower than the live pipeline but behaves identically from the writer's POV.

Usage:
    python -m pipeline.lyra.backfill_probative_images --slug SLUG            # dry run
    python -m pipeline.lyra.backfill_probative_images --slug SLUG --apply    # write
    python -m pipeline.lyra.backfill_probative_images --apply                # ALL missing

Safety:
    Defaults to dry-run. When no slug is provided the command refuses to run
    unless `--all` is also passed, because probative embedding is
    LLM-expensive (one opportunity = several MiniMax calls).
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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


_INLINE_IMG_RE = re.compile(r"!\[(?!\s*[Cc]over\b)[^\]]*\]\(/data/research-images/[^)]+\)")


def _has_inline_images(report: str) -> bool:
    """True if the paper markdown already has inline probative images
    (excluding the cover).
    """
    return bool(_INLINE_IMG_RE.search(report))


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


async def _process_paper(paper: dict, apply: bool) -> tuple[str, bool, str]:
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
        return (slug, False, "already has inline images")

    if not apply:
        # Dry-run: we don't want to burn LLM + MiniMax calls just to report.
        return (slug, False, "WOULD BACKFILL (dry-run)")

    new_report, embedded, diversity = await embed_probative_images(
        paper_id=paper_id,
        paper_text=report,
        question=question,
        angles=[],  # not persisted — forces on-demand fetch fallback
        registry=None,
        image_candidate_pool={},  # empty pool — same effect
    )

    if not embedded:
        return (slug, False, "no images embedded (on-demand fetch returned no safe candidates)")

    result["report"] = new_report
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


async def backfill(slug: str | None, apply: bool, process_all: bool) -> None:
    """Run the backfill."""
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
        result = await _process_paper(paper, apply)
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
    args = parser.parse_args()

    asyncio.run(backfill(slug=args.slug, apply=args.apply, process_all=args.all))
