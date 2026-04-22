"""Pick a banner hero image for papers that shipped without one.

Runs `pick_hero_image()` against the paper's stored `probative_images` + title
and writes the result to `result_json.hero_image`. No external API calls, no
image regeneration — selects from the images already embedded in the paper.

Older papers predate the hero_image stage entirely; newer ones may simply have
an empty pool. Either way this script is idempotent: re-running it for a paper
that already has `hero_image` set will pick again against the same pool (stable
barring scoring tweaks).

Usage:
    python -m pipeline.lyra.backfill_hero_image --slug SLUG             # dry-run
    python -m pipeline.lyra.backfill_hero_image --slug SLUG --apply     # write
    python -m pipeline.lyra.backfill_hero_image --all --apply           # every public paper
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.lyra.hero_picker import pick_hero_image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


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


def _process(paper: dict, apply: bool) -> tuple[str, str]:
    slug = paper["slug"]
    try:
        result = json.loads(paper["result_json"]) if paper["result_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return (slug, "invalid result_json")

    probative = result.get("probative_images") or []
    title = result.get("title") or ""
    if not probative:
        return (slug, "no probative_images to pick from")

    hero = pick_hero_image(title, probative)
    if not hero:
        return (slug, "pick_hero_image returned None")

    existing = result.get("hero_image") or {}
    if existing.get("web_path") == hero.get("web_path"):
        return (slug, f"already set to {hero.get('web_path')}")

    if not apply:
        return (slug, f"would set hero to {hero.get('web_path')} (dry-run)")

    result["hero_image"] = hero
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE research_requests SET result_json = :json WHERE id = :id"),
            {"json": json.dumps(result), "id": paper["id"]},
        )
        conn.commit()
    return (slug, f"set hero to {hero.get('web_path')}")


def main() -> None:
    p = argparse.ArgumentParser(description="Pick banner hero image from stored probative images")
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
    updated = 0
    for paper in papers:
        slug, reason = _process(paper, args.apply)
        logger.info("  %s — %s", slug, reason)
        if reason.startswith("set hero") or reason.startswith("would set"):
            updated += 1

    logger.info("")
    logger.info("=== Summary ===")
    logger.info("  Heroes %s: %d", "set" if args.apply else "would set", updated)


if __name__ == "__main__":
    main()
