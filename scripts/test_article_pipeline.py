"""
End-to-end article pipeline test using REAL pipeline data.

Finds 5 transcribed videos that don't have news items yet, runs the real
summarizer on them, scores significance, then generates a weekly article.

Usage (run inside the api container):
    docker exec ancient_nerds_lyra python scripts/test_article_pipeline.py
    docker exec ancient_nerds_lyra python scripts/test_article_pipeline.py --cleanup
    docker exec ancient_nerds_lyra python scripts/test_article_pipeline.py --list

--list     Show available transcribed videos without running anything.
--limit N  How many videos to process (default: 5).
--cleanup  Delete news items + article created in the last test run, then exit.
           (Identified by video status='test_summarized' set by this script.)
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_article_pipeline")

MARKER_STATUS = "test_summarized"  # status we stamp on processed videos for cleanup


def find_candidate_videos(session, limit: int) -> list:
    """Find transcribed videos that have no news items yet."""
    from pipeline.database import NewsItem, NewsVideo

    # Get videos with transcripts and no existing news items
    subq = session.query(NewsItem.video_id).distinct().subquery()
    candidates = (
        session.query(NewsVideo)
        .filter(
            NewsVideo.status == "transcribed",
            NewsVideo.transcript_text.isnot(None),
            ~NewsVideo.id.in_(subq),
        )
        .order_by(NewsVideo.published_at.desc())
        .limit(limit * 3)  # fetch extra so we have room to skip irrelevant ones
        .all()
    )
    session.expunge_all()
    return candidates[:limit]


def run_summarize(videos: list, settings) -> list[str]:
    """Run real summarizer on each video. Returns list of video IDs that succeeded."""
    from pipeline.lyra.summarizer import summarize_video

    succeeded = []
    for video in videos:
        logger.info(f"Summarizing: {video.id} — {video.title[:70]}")
        ok = summarize_video(video, settings)
        if ok:
            succeeded.append(video.id)
            logger.info(f"  ✓ Created news items for {video.id}")
        else:
            logger.warning(f"  ✗ Summarizer skipped/failed for {video.id}")
    return succeeded


def score_items(video_ids: list[str], session, settings) -> int:
    """Score significance for news items from the given videos."""
    from pipeline.database import NewsItem
    from pipeline.lyra.significance_scorer import _rescore_item, _load_prompt

    prompt = _load_prompt()
    total = 0
    for vid_id in video_ids:
        items = (
            session.query(NewsItem)
            .filter(NewsItem.video_id == vid_id, NewsItem.significance.is_(None))
            .all()
        )
        for item in items:
            score = _rescore_item(item, prompt, settings)
            if score is not None:
                item.significance = score
                total += 1
                logger.info(f"  scored [{score}] {item.headline[:60]}")
    session.flush()
    return total


def generate_article(settings, force: bool = False) -> bool:
    """Generate article. If force=True, delete existing article for this week first."""
    from pipeline.database import NewsArticle, get_session
    from pipeline.lyra.article_generator import _get_week_range, generate_weekly_article

    if force:
        week_start, _ = _get_week_range()
        with get_session() as s:
            existing = s.query(NewsArticle).filter(NewsArticle.week_start == week_start).first()
            if existing:
                s.delete(existing)
                logger.info("Deleted existing article for this week (--force)")

    return generate_weekly_article(settings)


def print_article(settings) -> None:
    from pipeline.database import NewsArticle, get_session
    from pipeline.lyra.article_generator import _get_week_range

    week_start, _ = _get_week_range()
    with get_session() as s:
        article = s.query(NewsArticle).filter(NewsArticle.week_start == week_start).first()
        if not article:
            print("No article found for this week.")
            return
        print("\n" + "=" * 72)
        print(f"TITLE:   {article.title}")
        print(f"SUMMARY: {article.summary}")
        print(f"WEEK:    {article.week_start.date()} → {article.week_end.date()}")
        print(f"ID:      {article.id}")
        print("=" * 72)
        print(article.content)
        print("=" * 72)


def cleanup(session) -> None:
    from pipeline.database import NewsArticle, NewsItem, NewsVideo
    from pipeline.lyra.article_generator import _get_week_range

    # Remove news items created from test videos (status == MARKER_STATUS)
    test_videos = session.query(NewsVideo).filter(NewsVideo.status == MARKER_STATUS).all()
    vids = [v.id for v in test_videos]

    if vids:
        deleted = (
            session.query(NewsItem)
            .filter(NewsItem.video_id.in_(vids))
            .delete(synchronize_session=False)
        )
        logger.info(f"Deleted {deleted} news items from test videos")

        # Restore status to transcribed so the real pipeline can pick them up
        for v in test_videos:
            v.status = "transcribed"
        logger.info(f"Restored {len(test_videos)} videos to status='transcribed'")

    # Remove article for this week if it only references test video IDs
    week_start, _ = _get_week_range()
    article = session.query(NewsArticle).filter(NewsArticle.week_start == week_start).first()
    if article:
        session.delete(article)
        logger.info(f"Deleted article ID={article.id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--list", action="store_true", help="List candidates only")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--force", action="store_true", help="Delete existing week article first")
    args = parser.parse_args()

    from pipeline.database import get_session
    from pipeline.lyra.config import LyraSettings

    settings = LyraSettings()

    # --- cleanup ---
    if args.cleanup:
        with get_session() as session:
            cleanup(session)
        print("Cleanup done.")
        return

    # --- list ---
    with get_session() as session:
        candidates = find_candidate_videos(session, args.limit)

    if args.list or not candidates:
        if not candidates:
            print("No transcribed videos without news items found.")
        else:
            print(f"\n{len(candidates)} candidate videos:\n")
            for v in candidates:
                print(f"  {v.id:20s}  {(v.title or '')[:60]}")
        return

    if not settings.anthropic_api_key:
        print("ERROR: LYRA_ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    print(f"\nProcessing {len(candidates)} videos through real pipeline...\n")

    # --- summarize ---
    succeeded_ids = run_summarize(candidates, settings)

    if not succeeded_ids:
        print("No videos were summarized successfully. Check logs.")
        sys.exit(1)

    # Mark them so --cleanup can find them later
    with get_session() as session:
        from pipeline.database import NewsVideo
        for vid_id in succeeded_ids:
            v = session.get(NewsVideo, vid_id)
            if v:
                v.status = MARKER_STATUS

    # --- score significance ---
    logger.info(f"\nScoring significance for {len(succeeded_ids)} videos...")
    with get_session() as session:
        scored = score_items(succeeded_ids, session, settings)
    logger.info(f"Scored {scored} news items")

    # --- generate article ---
    logger.info("\nGenerating weekly article...")
    created = generate_article(settings, force=args.force)

    if not created:
        print(
            "\nArticle generation returned False.\n"
            "Either no items scored >= 7, or an article for this week already exists.\n"
            "Re-run with --force to replace an existing article."
        )
        # Still show any items we created
        with get_session() as session:
            from pipeline.database import NewsItem
            items = (
                session.query(NewsItem)
                .filter(NewsItem.video_id.in_(succeeded_ids))
                .order_by(NewsItem.significance.desc().nullslast())
                .all()
            )
            if items:
                print(f"\nCreated {len(items)} news items:\n")
                for it in items:
                    print(f"  [{it.significance or '?':>2}] {it.headline[:65]}")
        return

    print_article(settings)


if __name__ == "__main__":
    main()
