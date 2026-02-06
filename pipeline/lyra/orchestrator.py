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
    """Run one full pipeline cycle: fetch -> summarize -> match -> posts -> verify -> dedup -> screenshots -> identify."""
    from pipeline.lyra.screenshot_extractor import extract_screenshots
    from pipeline.lyra.site_identifier import identify_and_enrich_sites
    from pipeline.lyra.site_matcher import match_sites_for_pending_items
    from pipeline.lyra.summarizer import summarize_pending_videos
    from pipeline.lyra.transcript_fetcher import backfill_video_descriptions, fetch_new_videos
    from pipeline.lyra.tweet_deduplicator import deduplicate_posts
    from pipeline.lyra.tweet_generator import generate_pending_posts
    from pipeline.lyra.tweet_verifier import verify_pending_posts

    logger.info("=== Starting pipeline cycle ===")

    # Step 1: Fetch new videos and transcripts
    new_videos = fetch_new_videos(settings)
    logger.info(f"Step 1: Fetched {new_videos} new videos")

    # Step 2: Summarize transcripts
    summarized = summarize_pending_videos(settings)
    logger.info(f"Step 2: Summarized {summarized} videos")

    # Step 3: Match extracted site names to globe sites
    matched = match_sites_for_pending_items()
    logger.info(f"Step 3: Matched {matched} news items to sites")

    # Step 4: Generate posts
    posts = generate_pending_posts(settings)
    logger.info(f"Step 4: Generated {posts} posts")

    # Step 5: Verify posts
    verified = verify_pending_posts(settings)
    logger.info(f"Step 5: Verified {verified} posts")

    # Step 6: Deduplicate
    deduped = deduplicate_posts()
    logger.info(f"Step 6: Removed {deduped} duplicates")

    # Step 7: Extract timestamp screenshots
    screenshots = extract_screenshots(settings)
    logger.info(f"Step 7: Extracted {screenshots} screenshots")

    # Step 7b: Backfill video descriptions for pre-change videos
    backfilled = backfill_video_descriptions(settings)
    logger.info(f"Step 7b: Backfilled {backfilled} video descriptions")

    # Step 8: Identify and enrich unmatched site discoveries
    identified = identify_and_enrich_sites(settings)
    logger.info(f"Step 8: Identified/enriched {identified} site discoveries")

    logger.info("=== Pipeline cycle complete ===")


def main() -> None:
    """Main entry point for the Lyra pipeline service."""
    setup_logging()
    logger.info("Lyra Wiskerbyte pipeline starting...")

    settings = LyraSettings()

    # Create tables if they don't exist, then run migrations
    from pipeline.database import create_all_tables, engine
    create_all_tables()

    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS site_match_tried BOOLEAN DEFAULT FALSE"
        ))
        # Create unified_site_names table if it doesn't exist (for alt-name matching)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS unified_site_names (
                id SERIAL PRIMARY KEY,
                site_id UUID NOT NULL REFERENCES unified_sites(id) ON DELETE CASCADE,
                name VARCHAR(500) NOT NULL,
                name_normalized VARCHAR(500) NOT NULL,
                language_code VARCHAR(10),
                name_type VARCHAR(50)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usn_name_normalized ON unified_site_names (name_normalized)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_usn_site ON unified_site_names (site_id)"
        ))
        conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE unified_site_names
                    ADD CONSTRAINT uq_usn UNIQUE (site_id, name_normalized);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$
        """))
        # Enable pg_trgm for fuzzy matching (used by discoveries API)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_usn_name_trgm
            ON unified_site_names USING gin (name_normalized gin_trgm_ops)
        """))
        # Pipeline heartbeat table (for LIVE status on frontend)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pipeline_heartbeats (
                pipeline_name VARCHAR(50) PRIMARY KEY,
                last_heartbeat TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                status VARCHAR(20) NOT NULL DEFAULT 'ok',
                last_error TEXT
            )
        """))

        # Lyra auto-discovery migrations: new columns on user_contributions
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20) DEFAULT 'pending'"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS wikidata_id VARCHAR(20)"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS wikipedia_url TEXT"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS thumbnail_url TEXT"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_start INTEGER"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_end INTEGER"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_name VARCHAR(100)"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS last_facts_hash VARCHAR(64)"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS enrichment_data JSONB"))
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS promoted_site_id UUID REFERENCES unified_sites(id) ON DELETE SET NULL"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contributions_enrichment ON user_contributions (source, enrichment_status)"))

        # New column on news_videos for RSS description
        conn.execute(text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS description TEXT"))

        # Functional index for site_identifier queries on news_items
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_items_site_name_lower ON news_items (lower(site_name_extracted))"))

        # Rename sources for branding
        conn.execute(text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Originals'
            WHERE id = 'ancient_nerds' AND name != 'ANCIENT NERDS Originals'
        """))
        conn.execute(text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Discoveries',
                category = 'Primary', priority = 1, is_primary = true
            WHERE id = 'lyra'
        """))

        # One-time resets: re-enrich discoveries processed with older prompts/logic.
        # Each reset uses a versioned flag in enrichment_data to run only once.
        # v3: improved identify prompt with caption-garbling awareness
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v3_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v3_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
        """))

        conn.commit()

    # Seed channels
    from pipeline.lyra.channels import seed_channels
    seed_channels()

    # Seed Lyra source for auto-discovered sites
    from pipeline.lyra.site_identifier import seed_lyra_source
    seed_lyra_source()

    # Import article generator
    from pipeline.lyra.article_generator import generate_weekly_article, should_generate_article

    last_pipeline_run = 0.0

    while True:
        now = time.time()

        # Run pipeline every hour
        if now - last_pipeline_run >= CYCLE_INTERVAL:
            cycle_status = "ok"
            cycle_error = None
            try:
                run_pipeline(settings)
            except Exception as exc:
                logger.exception("Pipeline cycle failed")
                cycle_status = "error"
                cycle_error = str(exc)
            last_pipeline_run = now

            # Write heartbeat so the API can report LIVE/OFFLINE
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO pipeline_heartbeats (pipeline_name, last_heartbeat, status, last_error)
                        VALUES ('lyra', NOW(), :status, :error)
                        ON CONFLICT (pipeline_name) DO UPDATE SET
                            last_heartbeat = NOW(),
                            status = EXCLUDED.status,
                            last_error = EXCLUDED.last_error
                    """), {"status": cycle_status, "error": cycle_error})
                    conn.commit()
            except Exception:
                logger.exception("Failed to write heartbeat")

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
