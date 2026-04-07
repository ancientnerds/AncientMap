#!/usr/bin/env python
"""Regenerate all journal entries with Theo research stages + quality assessor.

Generates new active articles for each historical week. Old inactive articles
are preserved until all new ones score 10/10.

Usage:
    python scripts/regenerate_all_journals.py
    python scripts/regenerate_all_journals.py --week 2026-03-30  # specific week only
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "15432"
os.environ["POSTGRES_USER"] = "ancient_map"
os.environ["POSTGRES_PASSWORD"] = "ancient_map_dev_password"  # noqa: S105
os.environ["POSTGRES_DB"] = "ancient_map"
os.environ["DATABASE_URL"] = (
    "postgresql://ancient_map:ancient_map_dev_password@localhost:15432/ancient_map"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# Historical weeks that have journal entries
HISTORICAL_WEEKS = [
    (datetime(2026, 2, 9, tzinfo=UTC), datetime(2026, 2, 15, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 2, 16, tzinfo=UTC), datetime(2026, 2, 22, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 2, 23, tzinfo=UTC), datetime(2026, 3, 1, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 3, 9, tzinfo=UTC), datetime(2026, 3, 15, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 3, 16, tzinfo=UTC), datetime(2026, 3, 22, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 3, 23, tzinfo=UTC), datetime(2026, 3, 29, 23, 59, 59, tzinfo=UTC)),
    (datetime(2026, 3, 30, tzinfo=UTC), datetime(2026, 4, 5, 23, 59, 59, tzinfo=UTC)),
]


def main():
    parser = argparse.ArgumentParser(description="Regenerate all journal entries")
    parser.add_argument("--week", type=str, help="Specific week start date (YYYY-MM-DD)")
    args = parser.parse_args()

    from pipeline.lyra.article_generator import generate_weekly_article
    from pipeline.lyra.config import _get_settings

    settings = _get_settings()
    if not settings.minimax_api_key:
        logger.error("No MiniMax API key")
        sys.exit(1)

    weeks = HISTORICAL_WEEKS
    if args.week:
        target = datetime.strptime(args.week, "%Y-%m-%d").replace(tzinfo=UTC)
        weeks = [(s, e) for s, e in weeks if s.date() == target.date()]
        if not weeks:
            logger.error(f"No historical week starting {args.week}")
            sys.exit(1)

    logger.info(f"Regenerating {len(weeks)} journal(s)...")

    results = {}
    for week_start, week_end in weeks:
        label = week_start.strftime("%b %d")
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Week of {label} ({week_start.date()} to {week_end.date()})")

        success = generate_weekly_article(settings, week_override=(week_start, week_end))

        if success:
            logger.info(f"Week of {label}: GENERATED")
            results[label] = "OK"
        else:
            logger.warning(f"Week of {label}: FAILED (no items or error)")
            results[label] = "FAILED"

    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    for week, status in results.items():
        logger.info(f"  {week}: {status}")


if __name__ == "__main__":
    main()
