"""Backfill cover images for existing published research papers.

Regenerates the cover image + inserts it into the paper markdown for any
public completed paper that doesn't already have a cover image embedded.

Usage:
    python -m pipeline.lyra.backfill_cover_images          # dry run (default)
    python -m pipeline.lyra.backfill_cover_images --apply   # actually do it
    python -m pipeline.lyra.backfill_cover_images --apply --slug SLUG   # single paper
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

# Ensure pipeline is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.lyra.theo_images import generate_cover_image, insert_cover_image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

IMAGES_DIR = Path(__file__).parent.parent.parent / "public" / "data" / "research-images"


def _has_cover(report: str) -> bool:
    """Check if paper already has a cover image embedded."""
    return bool(re.search(r"!\[[Cc]over\]", report))


def _fetch_papers(slug: str | None = None) -> list[dict]:
    """Fetch public completed papers, optionally filtered by slug."""
    with engine.connect() as conn:
        if slug:
            rows = conn.execute(
                text("""
                    SELECT id::text, slug, result_json
                    FROM research_requests
                    WHERE slug = :slug AND is_public = TRUE AND status = 'completed'
                """),
                {"slug": slug},
            ).fetchall()
        else:
            rows = conn.execute(
                text("""
                    SELECT id::text, slug, result_json
                    FROM research_requests
                    WHERE is_public = TRUE AND status = 'completed'
                    ORDER BY published_at DESC
                """)
            ).fetchall()
        return [{"id": r.id, "slug": r.slug, "result_json": r.result_json} for r in rows]


async def _process_paper(paper: dict, emit) -> tuple[str, bool, str]:
    """Generate + embed cover image for one paper. Returns (slug, changed, reason)."""
    slug = paper["slug"]
    paper_id = paper["id"]

    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, False, "invalid result_json (skipping)")

    report = result.get("report", "")

    if _has_cover(report):
        return (slug, False, "already has cover image")

    if not report:
        return (slug, False, "empty report (skipping)")

    cover_url = await generate_cover_image(paper_id, report, emit)

    if not cover_url:
        return (slug, False, "cover generation failed or skipped (check MiniMax quota)")

    new_report = insert_cover_image(report, cover_url)
    result["report"] = new_report

    # Update result_json in DB
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper_id},
        )
        conn.commit()

    return (slug, True, f"cover generated and embedded: {cover_url}")


async def backfill(slugs: list[str] | None, apply: bool, emit=None) -> None:
    """Run the backfill."""
    if not apply:
        logger.info("DRY RUN — no changes will be written (use --apply to confirm)")
        logger.info("")

    emit = emit or (lambda e: None)

    # Fetch papers
    if slugs:
        papers = []
        for s in slugs:
            papers.extend(_fetch_papers(s))
    else:
        papers = _fetch_papers()

    if not papers:
        logger.info("No papers found.")
        return

    logger.info(f"Found {len(papers)} paper(s) to check")

    results: list[tuple[str, bool, str]] = []

    for paper in papers:
        slug = paper["slug"]
        logger.info(f"Checking: {slug}")
        result = await _process_paper(paper, emit)
        results.append(result)
        status = "CHANGED" if result[1] else result[2].upper()
        logger.info(f"  -> {status}")
        if result[1]:
            logger.info(f"     {result[2]}")

    # Summary
    changed = [r for r in results if r[1]]
    skipped = [r for r in results if not r[1] and "already" in r[2]]
    failed = [r for r in results if not r[1] and "already" not in r[2]]

    logger.info("")
    logger.info("=== Summary ===")
    logger.info(f"  Total checked: {len(results)}")
    logger.info(f"  Images added: {len(changed)}")
    logger.info(f"  Already had cover: {len(skipped)}")
    logger.info(f"  Skipped/failed: {len(failed)}")

    if changed:
        logger.info("")
        logger.info("Papers updated:")
        for slug, _, msg in changed:
            logger.info(f"  - {slug}: {msg}")

    if not apply and changed:
        logger.info("")
        logger.info("Run with --apply to write these changes to the database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill cover images for existing papers")
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default is dry-run)")
    parser.add_argument("--slug", type=str, default=None, help="Process only this slug")
    args = parser.parse_args()

    slugs = [args.slug] if args.slug else None

    asyncio.run(backfill(slugs=slugs, apply=args.apply))
