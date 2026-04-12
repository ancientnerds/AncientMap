"""Regenerate the latest weekly article using MiniMax M2.7 for the entire pipeline.

Usage:
    LYRA_MINIMAX_API_KEY=sk-cp-... python scripts/regenerate_article_minimax.py

Deletes the existing article for the week, then runs the full article
generation pipeline with LYRA_LLM_BACKEND=minimax.
"""

from __future__ import annotations

import os
import sys

# ── ENV MUST BE SET BEFORE ANY PROJECT IMPORTS ──
# pipeline.config reads POSTGRES_* at import time via pydantic-settings
os.environ["POSTGRES_HOST"] = "127.0.0.1"
os.environ["POSTGRES_PORT"] = "15432"
os.environ.setdefault("POSTGRES_PASSWORD", "ancient_map_dev_password")
os.environ["LYRA_LLM_BACKEND"] = "minimax"
os.environ["LYRA_ARTICLE_WEB_BACKEND"] = "minimax"
os.environ.setdefault("LYRA_ANTHROPIC_API_KEY", "unused")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import UTC, datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Now safe to import project modules
import pipeline.lyra.config as cfg

cfg._cached_settings = None
cfg.LyraSettings._resolve_env_fallbacks()

from pipeline.database import NewsArticle, get_session
from pipeline.lyra.article_generator import generate_weekly_article
from pipeline.lyra.config import LyraSettings


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--week-start", default="2026-03-23")
    args = parser.parse_args()

    minimax_key = os.environ.get("LYRA_MINIMAX_API_KEY", "")
    if not minimax_key:
        print("ERROR: Set LYRA_MINIMAX_API_KEY")
        sys.exit(1)

    settings = LyraSettings()
    logger.info(f"Backend: {settings.llm_backend}")
    logger.info(f"Model: MiniMax-M2.7")
    logger.info(f"Web backend: {settings.article_web_backend}")

    week_start = datetime.fromisoformat(args.week_start).replace(tzinfo=UTC)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    logger.info(f"Week: {week_start.date()} to {week_end.date()}")

    # Delete existing article for this week
    with get_session() as session:
        existing = (
            session.query(NewsArticle)
            .filter(NewsArticle.week_start == week_start)
            .first()
        )
        if existing:
            logger.info(f"Deleting existing article {existing.id}: {existing.title}")
            session.delete(existing)
        else:
            logger.info("No existing article to delete")

    # Run full pipeline
    logger.info("=" * 60)
    logger.info("GENERATING ARTICLE WITH MINIMAX M2.7")
    logger.info("=" * 60)

    t0 = time.time()
    success = generate_weekly_article(settings, week_override=(week_start, week_end))
    elapsed = time.time() - t0

    if success:
        logger.info(f"Article generated in {elapsed:.0f}s")
        with get_session() as session:
            article = (
                session.query(NewsArticle)
                .filter(NewsArticle.week_start == week_start)
                .first()
            )
            if article:
                logger.info(f"Title: {article.title}")
                logger.info(f"Content length: {len(article.content)} chars")
                outfile = "scripts/article_minimax_generated.md"
                with open(outfile, "w", encoding="utf-8") as f:
                    f.write(f"# {article.title}\n\n{article.content}")
                logger.info(f"Saved to {outfile}")

                # Print checklist results from quality_report
                qr = article.quality_report or {}
                cl = qr.get("checklist", {})
                if cl:
                    logger.info("Checklist: %s", cl.get("summary", "N/A"))
                    for name, check in cl.get("checks", {}).items():
                        status = "PASS" if check.get("passed") else "FAIL"
                        logger.info("  %s %s: %s", status, name, check.get("message", ""))
    else:
        logger.error(f"Article generation failed after {elapsed:.0f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
