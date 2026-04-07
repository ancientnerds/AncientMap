#!/usr/bin/env python
"""Retroactively assess and fix all existing journal entries.

Usage:
    # Dry run — show scores without fixing
    python scripts/reassess_journals.py --dry-run

    # Fix all journals
    python scripts/reassess_journals.py

    # Fix a specific article
    python scripts/reassess_journals.py --id 28

Requires:
    - DB tunnel on localhost:15432 (or local DB on 5432)
    - LYRA_MINIMAX_API_KEY set in .env
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use tunnel port if available
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = (
        "postgresql://ancient_map:ancient_map_dev_password@localhost:15432/ancient_map"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Reassess and fix journal entries")
    parser.add_argument("--dry-run", action="store_true", help="Score only, don't fix")
    parser.add_argument("--id", type=int, help="Fix a specific article ID")
    args = parser.parse_args()

    from pipeline.database import NewsArticle, get_session
    from pipeline.lyra.config import _get_settings
    from pipeline.lyra.journal_assessor import assess_and_fix

    settings = _get_settings()
    if not settings.minimax_api_key:
        logger.error("No MiniMax API key — set LYRA_MINIMAX_API_KEY in .env")
        sys.exit(1)

    with get_session() as session:
        if args.id:
            articles = [session.query(NewsArticle).get(args.id)]
            if not articles[0]:
                logger.error(f"Article #{args.id} not found")
                sys.exit(1)
        else:
            articles = session.query(NewsArticle).order_by(NewsArticle.created_at.asc()).all()

        logger.info(f"Reassessing {len(articles)} journal(s)...")
        results: dict[int, tuple[int, int]] = {}

        for article in articles:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Article #{article.id}: {article.title[:60]}")
            logger.info(f"Week: {article.week_start} to {article.week_end}")

            # Parse sources from the ### Sources section
            content = article.content
            sources = _parse_sources_from_content(content)
            logger.info(f"Parsed {len(sources)} sources")

            # Run assessment with convergence
            fixed_body, result = assess_and_fix(
                content,
                sources,
                week_start=article.week_start,
                settings=settings,
                max_iterations=1 if args.dry_run else 3,
            )

            before_score = (
                result.score
                if args.dry_run
                else (
                    result.score - len(result.fixes_applied)
                    if result.fixes_applied
                    else result.score
                )
            )
            after_score = result.score
            results[article.id] = (before_score, after_score)

            # Show dimension details
            for dim, passed in sorted(result.dimensions.items()):
                status = "PASS" if passed else "FAIL"
                logger.info(f"  {dim}: {status}")

            if args.dry_run:
                logger.info(f"Score: {after_score}/10 (dry run, no fixes applied)")
            elif fixed_body != content:
                article.content = fixed_body
                # Update summary if D9 fixed it
                for fix in result.fixes_applied:
                    if fix.get("dimension") == "D9" and fix.get("corrected_summary"):
                        article.summary = fix["corrected_summary"]
                logger.info(
                    f"FIXED: {after_score}/10 "
                    f"({len(result.fixes_applied)} fixes in {result.iteration} iterations)"
                )
            else:
                logger.info(f"No changes needed: {after_score}/10")

        # Summary
        logger.info(f"\n{'=' * 60}")
        logger.info("SUMMARY")
        logger.info(f"{'=' * 60}")
        all_perfect = True
        for aid, (before, after) in sorted(results.items()):
            arrow = "→" if before != after else "="
            status = "✓" if after == 10 else "✗"
            logger.info(f"  {status} Article #{aid}: {before}/10 {arrow} {after}/10")
            if after < 10:
                all_perfect = False

        if all_perfect:
            logger.info("\nAll journals at 10/10!")
        else:
            failing = sum(1 for _, (_, a) in results.items() if a < 10)
            logger.info(f"\n{failing} journal(s) below 10/10")


def _parse_sources_from_content(content: str) -> list[dict]:
    """Extract sources list from journal content's ### Sources section."""
    import re

    idx = content.find("### Sources")
    if idx == -1:
        return []

    sources_text = content[idx:]
    sources = []
    for line in sources_text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d+)\.\s+\[(.+?)\]\((https?://\S+?)\)", line)
        if m:
            sources.append(
                {
                    "citation": int(m.group(1)),
                    "label": m.group(2),
                    "url": m.group(3),
                    "type": "youtube" if "youtu" in m.group(3) else "news",
                }
            )
        else:
            # Source without URL
            m2 = re.match(r"^(\d+)\.\s+(.+)", line)
            if m2:
                sources.append(
                    {
                        "citation": int(m2.group(1)),
                        "label": m2.group(2),
                        "url": "",
                        "type": "unknown",
                    }
                )
    return sources


if __name__ == "__main__":
    main()
