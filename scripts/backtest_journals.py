"""Rolling backtest for the journal pipeline.

Regenerates articles for historical weeks and runs the quality checklist.

Usage:
    # Single week
    LYRA_MINIMAX_API_KEY=sk-... python scripts/backtest_journals.py --week 2026-04-06

    # Multiple specific weeks
    LYRA_MINIMAX_API_KEY=sk-... python scripts/backtest_journals.py --weeks 2026-04-06,2026-03-30

    # All available weeks (recent first, with --min-scored filter)
    LYRA_MINIMAX_API_KEY=sk-... python scripts/backtest_journals.py --all --min-scored 8

    # Checklist-only (just check existing articles, don't regenerate)
    python scripts/backtest_journals.py --all --checklist-only

Requires Bitvise tunnel: localhost:15432 -> VPS PostgreSQL.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# ── ENV MUST BE SET BEFORE ANY PROJECT IMPORTS ──
os.environ["POSTGRES_HOST"] = "127.0.0.1"
os.environ["POSTGRES_PORT"] = "15432"
os.environ.setdefault("POSTGRES_PASSWORD", "ancient_map_dev_password")
os.environ.setdefault("LYRA_LLM_BACKEND", "minimax")
os.environ.setdefault("LYRA_ARTICLE_WEB_BACKEND", "minimax")
os.environ.setdefault("LYRA_ANTHROPIC_API_KEY", "unused")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

import pipeline.lyra.config as cfg

cfg._cached_settings = None
cfg.LyraSettings._resolve_env_fallbacks()

from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_session
from pipeline.lyra.article_checklist import ChecklistResult, run_checklist
from pipeline.lyra.article_generator import generate_weekly_article
from pipeline.lyra.config import LyraSettings


def discover_available_weeks(
    session, *, min_scored: int = 8
) -> list[tuple[datetime, datetime]]:
    """Find weeks with enough scored NewsItems for article generation."""
    rows = (
        session.query(
            func.date_trunc("week", NewsVideo.published_at).label("week"),
            func.count(
                func.nullif(NewsItem.significance, None)
            ).label("scored"),
        )
        .join(NewsVideo, NewsItem.video_id == NewsVideo.id)
        .filter(NewsItem.post_text.isnot(None))
        .group_by("week")
        .having(
            func.count(func.nullif(NewsItem.significance, None)) >= min_scored
        )
        .order_by(func.date_trunc("week", NewsVideo.published_at).desc())
        .all()
    )

    weeks = []
    for row in rows:
        ws = row.week.replace(tzinfo=UTC)
        # Align to Monday
        ws = ws - timedelta(days=ws.weekday())
        we = ws + timedelta(days=6, hours=23, minutes=59, seconds=59)
        weeks.append((ws, we))

    return weeks


def _load_article_items(session, week_start, week_end) -> list[dict]:
    """Load items for a week to pass to checklist (mirrors _collect_article_items fields)."""
    rows = (
        session.query(NewsItem, NewsVideo, NewsItem.web_sources)
        .join(NewsVideo, NewsItem.video_id == NewsVideo.id)
        .filter(
            NewsVideo.published_at >= week_start,
            NewsVideo.published_at <= week_end,
            NewsItem.significance.isnot(None),
            NewsItem.post_text.isnot(None),
        )
        .order_by(NewsItem.significance.desc())
        .limit(15)
        .all()
    )
    items = []
    for item, video, _ws in rows:
        items.append({
            "headline": item.headline,
            "video_id": video.id,
            "video_title": video.title,
            "channel_name": "",  # not loaded here, but checklist only needs video_id
            "timestamp_seconds": item.timestamp_seconds,
            "facts": item.facts or [],
        })
    return items


def _parse_sources_from_content(content: str) -> list[dict]:
    """Parse the ### Sources section from article content into source dicts."""
    import re

    sources: list[dict] = []
    src_idx = content.find("### Sources")
    if src_idx == -1:
        src_idx = content.find("## Sources")
    if src_idx == -1:
        return sources

    src_text = content[src_idx:]
    for m in re.finditer(r"^(\d+)\.\s+\[([^\]]*)\]\(([^)]*)\)", src_text, re.MULTILINE):
        sources.append({
            "citation": int(m.group(1)),
            "label": m.group(2),
            "url": m.group(3),
        })
    return sources


def run_backtest_week(
    week_start: datetime,
    week_end: datetime,
    settings: LyraSettings,
    *,
    checklist_only: bool = False,
) -> dict:
    """Run a single backtest week: delete existing, regenerate, run checklist."""
    week_label = week_start.strftime("%Y-%m-%d")
    result: dict = {
        "week": week_label,
        "success": False,
        "elapsed_seconds": 0,
        "assessment_score": None,
        "checklist": None,
        "source_counts": {},
        "content_length": 0,
        "error": None,
    }

    t0 = time.time()

    try:
        if not checklist_only:
            # Delete existing article
            with get_session() as session:
                existing = (
                    session.query(NewsArticle)
                    .filter(NewsArticle.week_start == week_start)
                    .first()
                )
                if existing:
                    logger.info("[%s] Deleting existing article: %s", week_label, existing.title[:50])
                    session.delete(existing)

            # Generate
            logger.info("[%s] Generating article...", week_label)
            success = generate_weekly_article(settings, week_override=(week_start, week_end))
            if not success:
                result["error"] = "generate_weekly_article returned False"
                result["elapsed_seconds"] = round(time.time() - t0, 1)
                return result

        # Load the article
        with get_session() as session:
            article = (
                session.query(NewsArticle)
                .filter(NewsArticle.week_start == week_start)
                .first()
            )
            if not article:
                result["error"] = "No article found after generation"
                result["elapsed_seconds"] = round(time.time() - t0, 1)
                return result

            result["content_length"] = len(article.content)
            qr = article.quality_report or {}
            result["assessment_score"] = qr.get("assessment_score")

            # If checklist was already run during generation, use it
            if qr.get("checklist"):
                result["checklist"] = qr["checklist"]
            else:
                # Run checklist manually
                items = _load_article_items(session, week_start, week_end)
                sources = _parse_sources_from_content(article.content)

                # Extract body (before Sources section)
                body = article.content
                headline = article.title
                tldr = article.summary or ""

                checklist = run_checklist(body, sources, items, headline, tldr, week_start)
                result["checklist"] = checklist.to_dict()

            # Count source types
            sources = _parse_sources_from_content(article.content)
            yt = sum(1 for s in sources if "youtu" in s.get("url", ""))
            result["source_counts"] = {
                "total": len(sources),
                "youtube": yt,
                "other": len(sources) - yt,
            }

            result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        logger.error("[%s] Backtest failed: %s", week_label, e, exc_info=True)

    result["elapsed_seconds"] = round(time.time() - t0, 1)
    return result


def print_report(results: list[dict]) -> None:
    """Print a formatted table of backtest results."""
    print()
    print("=" * 100)
    print(f"{'Week':<12} {'Score':>5} {'Checklist':<30} {'Sources':>10} {'YT':>4} {'Chars':>7} {'Time':>7} {'Error'}")
    print("-" * 100)

    for r in results:
        checklist = r.get("checklist") or {}
        cl_summary = checklist.get("summary", "N/A")[:28]
        sc = r.get("source_counts", {})

        print(
            f"{r['week']:<12} "
            f"{r.get('assessment_score', '?'):>5} "
            f"{cl_summary:<30} "
            f"{sc.get('total', 0):>10} "
            f"{sc.get('youtube', 0):>4} "
            f"{r.get('content_length', 0):>7} "
            f"{r.get('elapsed_seconds', 0):>6.0f}s "
            f"{r.get('error', '') or ''}"
        )

    print("=" * 100)

    passed = sum(1 for r in results if r.get("checklist", {}).get("passed"))
    total = len(results)
    print(f"\nChecklist: {passed}/{total} weeks passed")

    score_10 = sum(1 for r in results if r.get("assessment_score") == 10)
    print(f"Assessment 10/10: {score_10}/{total} weeks")
    print()


def main():
    parser = argparse.ArgumentParser(description="Rolling journal pipeline backtest")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--week", help="Single week to test (YYYY-MM-DD)")
    group.add_argument("--weeks", help="Comma-separated weeks (YYYY-MM-DD,YYYY-MM-DD)")
    group.add_argument("--all", action="store_true", help="Test all available weeks")
    parser.add_argument("--checklist-only", action="store_true", help="Only run checklist on existing articles")
    parser.add_argument("--min-scored", type=int, default=8, help="Min scored items per week (default 8)")
    parser.add_argument("--limit", type=int, default=0, help="Max weeks to process (0=all)")
    args = parser.parse_args()

    minimax_key = os.environ.get("LYRA_MINIMAX_API_KEY", "")
    if not minimax_key and not args.checklist_only:
        print("ERROR: Set LYRA_MINIMAX_API_KEY (or use --checklist-only)")
        sys.exit(1)

    settings = LyraSettings()
    logger.info("Backend: %s", settings.llm_backend)

    # Build week list
    if args.week:
        ws = datetime.fromisoformat(args.week).replace(tzinfo=UTC)
        we = ws + timedelta(days=6, hours=23, minutes=59, seconds=59)
        weeks = [(ws, we)]
    elif args.weeks:
        weeks = []
        for w in args.weeks.split(","):
            ws = datetime.fromisoformat(w.strip()).replace(tzinfo=UTC)
            we = ws + timedelta(days=6, hours=23, minutes=59, seconds=59)
            weeks.append((ws, we))
    else:
        with get_session() as session:
            weeks = discover_available_weeks(session, min_scored=args.min_scored)
        logger.info("Discovered %d available weeks (min_scored=%d)", len(weeks), args.min_scored)

    if args.limit:
        weeks = weeks[: args.limit]

    logger.info("Testing %d week(s)", len(weeks))

    # Run backtests
    results = []
    for i, (ws, we) in enumerate(weeks, 1):
        logger.info(
            "=== Week %d/%d: %s ===",
            i, len(weeks), ws.strftime("%Y-%m-%d"),
        )
        r = run_backtest_week(ws, we, settings, checklist_only=args.checklist_only)
        results.append(r)

        # Print incremental result
        checklist = r.get("checklist") or {}
        logger.info(
            "[%s] Done: score=%s checklist=%s sources=%s elapsed=%ss",
            r["week"],
            r.get("assessment_score", "?"),
            checklist.get("summary", "N/A"),
            r.get("source_counts", {}),
            r.get("elapsed_seconds", 0),
        )

    print_report(results)


if __name__ == "__main__":
    main()
