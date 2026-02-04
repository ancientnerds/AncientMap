"""Main orchestrator for the Lyra news pipeline.

Runs as a long-lived process (Docker entrypoint):
- Hourly: fetch new videos, transcribe, summarize, generate posts, verify, deduplicate
- Weekly: generate digest article
"""

import logging
import sys
import time

from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

CYCLE_INTERVAL = 3600  # 1 hour between pipeline runs


def setup_logging() -> None:
    """Configure logging for the Lyra pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def run_pipeline(settings: LyraSettings) -> None:
    """Run one full pipeline cycle: fetch -> transcribe -> summarize -> posts -> verify -> dedup."""
    from pipeline.lyra.transcript_fetcher import fetch_new_videos
    from pipeline.lyra.summarizer import summarize_pending_videos
    from pipeline.lyra.tweet_generator import generate_pending_posts
    from pipeline.lyra.tweet_verifier import verify_pending_posts
    from pipeline.lyra.tweet_deduplicator import deduplicate_posts

    logger.info("=== Starting pipeline cycle ===")

    # Step 1: Fetch new videos and transcripts
    new_videos = fetch_new_videos(settings)
    logger.info(f"Step 1: Fetched {new_videos} new videos")

    # Step 2: Summarize transcripts
    summarized = summarize_pending_videos(settings)
    logger.info(f"Step 2: Summarized {summarized} videos")

    # Step 3: Generate posts
    posts = generate_pending_posts(settings)
    logger.info(f"Step 3: Generated {posts} posts")

    # Step 4: Verify posts
    verified = verify_pending_posts(settings)
    logger.info(f"Step 4: Verified {verified} posts")

    # Step 5: Deduplicate
    deduped = deduplicate_posts()
    logger.info(f"Step 5: Removed {deduped} duplicates")

    logger.info("=== Pipeline cycle complete ===")


def main() -> None:
    """Main entry point for the Lyra pipeline service."""
    setup_logging()
    logger.info("Lyra Wiskerbyte pipeline starting...")

    settings = LyraSettings()

    # Create tables if they don't exist
    from pipeline.database import create_all_tables
    create_all_tables()

    # Seed channels
    from pipeline.lyra.channels import seed_channels
    seed_channels()

    # Import article generator
    from pipeline.lyra.article_generator import generate_weekly_article, should_generate_article

    last_pipeline_run = 0.0

    while True:
        now = time.time()

        # Run pipeline every hour
        if now - last_pipeline_run >= CYCLE_INTERVAL:
            try:
                run_pipeline(settings)
            except Exception:
                logger.exception("Pipeline cycle failed")
            last_pipeline_run = now

        # Weekly article generation
        if should_generate_article():
            try:
                generate_weekly_article(settings)
            except Exception:
                logger.exception("Article generation failed")

        # Sleep before next check
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    main()
