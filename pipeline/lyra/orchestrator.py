"""Main orchestrator for the Lyra news pipeline.

Runs as a long-lived process (Docker entrypoint):
- Hourly: fetch new videos, transcribe, summarize, generate posts, verify, deduplicate
- Weekly: generate digest article

Local dev usage:
  python -m pipeline.lyra.orchestrator --once          # single full cycle
  python -m pipeline.lyra.orchestrator --step identify  # single step only
"""

import argparse
import logging
import sys
import time

from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

CYCLE_INTERVAL = 3600  # 1 hour between pipeline runs

# Step registry: name -> (function_import_path, description, needs_settings)
STEPS = {
    "fetch":       ("pipeline.lyra.transcript_fetcher", "fetch_new_videos",            True,  "Fetched {n} new videos"),
    "summarize":   ("pipeline.lyra.summarizer",         "summarize_pending_videos",     True,  "Summarized {n} videos"),
    "match":       ("pipeline.lyra.site_matcher",       "match_sites_for_pending_items", False, "Matched {n} news items to sites"),
    "posts":       ("pipeline.lyra.tweet_generator",    "generate_pending_posts",       True,  "Generated {n} posts"),
    "verify":      ("pipeline.lyra.tweet_verifier",     "verify_pending_posts",         True,  "Verified {n} posts"),
    "dedup":       ("pipeline.lyra.tweet_deduplicator", "deduplicate_posts",            False, "Removed {n} duplicates"),
    "screenshots": ("pipeline.lyra.screenshot_extractor", "extract_screenshots",        True,  "Extracted {n} screenshots"),
    "backfill":    ("pipeline.lyra.transcript_fetcher", "backfill_video_descriptions",  True,  "Backfilled {n} video descriptions"),
    "identify":    ("pipeline.lyra.site_identifier",    "identify_and_enrich_sites",    True,  "Identified/enriched {n} site discoveries"),
}

# Ordered step list matching the full pipeline sequence
STEP_ORDER = ["fetch", "summarize", "match", "posts", "verify", "dedup", "screenshots", "backfill", "identify"]


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


def _run_step(step_name: str, settings: LyraSettings) -> tuple[int, float]:
    """Run a single pipeline step. Returns (result_count, elapsed_seconds)."""
    import importlib

    module_path, func_name, needs_settings, _ = STEPS[step_name]
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)

    t0 = time.time()
    result = func(settings) if needs_settings else func()
    elapsed = time.time() - t0
    return result, elapsed


def _log_cycle_summary(step_results: dict[str, tuple[int, float]], total_elapsed: float) -> None:
    """Log a summary of what happened in this cycle."""
    from sqlalchemy import text

    from pipeline.database import engine

    # Query DB for current state
    with engine.connect() as conn:
        # Discovery counts
        rows = conn.execute(text(
            "SELECT enrichment_status, COUNT(*) FROM user_contributions "
            "WHERE source='lyra' GROUP BY enrichment_status ORDER BY enrichment_status"
        )).fetchall()
        discovery_counts = {row[0]: row[1] for row in rows}
        total_discoveries = sum(discovery_counts.values())

        # Video + news item counts
        video_count = conn.execute(text("SELECT COUNT(*) FROM news_videos")).scalar()
        news_count = conn.execute(text("SELECT COUNT(*) FROM news_items")).scalar()

    lines = ["", "=== Cycle Summary ==="]

    # Step timings
    for name in STEP_ORDER:
        if name in step_results:
            count, elapsed = step_results[name]
            _, _, _, desc_template = STEPS[name]
            desc = desc_template.format(n=count)
            lines.append(f"  {name:<12} {desc} ({elapsed:.1f}s)")

    lines.append("  ---")
    lines.append(f"  Videos: {video_count}  |  News items: {news_count}")

    # Discovery breakdown
    parts = []
    for status in ["pending", "matched", "enriched", "promoted", "rejected", "failed"]:
        if status in discovery_counts:
            parts.append(f"{discovery_counts[status]} {status}")
    lines.append(f"  Discoveries: {total_discoveries} ({', '.join(parts)})")

    lines.append(f"=== Pipeline cycle complete ({total_elapsed:.1f}s) ===")
    logger.info("\n".join(lines))


def run_pipeline(settings: LyraSettings, only_step: str | None = None) -> None:
    """Run one full pipeline cycle, or a single step if only_step is set."""
    cycle_start = time.time()
    step_results: dict[str, tuple[int, float]] = {}

    steps_to_run = [only_step] if only_step else STEP_ORDER

    if only_step:
        logger.info(f"=== Running single step: {only_step} ===")
    else:
        logger.info("=== Starting pipeline cycle ===")

    for step_name in steps_to_run:
        result, elapsed = _run_step(step_name, settings)
        step_results[step_name] = (result, elapsed)
        _, _, _, desc_template = STEPS[step_name]
        desc = desc_template.format(n=result)
        logger.info(f"  {step_name}: {desc} ({elapsed:.1f}s)")

    total_elapsed = time.time() - cycle_start
    _log_cycle_summary(step_results, total_elapsed)


def main() -> None:
    """Main entry point for the Lyra pipeline service."""
    parser = argparse.ArgumentParser(description="Lyra news pipeline orchestrator")
    parser.add_argument("--once", action="store_true", help="Run a single pipeline cycle and exit")
    parser.add_argument("--step", choices=list(STEPS.keys()), help="Run only a single named step")
    args = parser.parse_args()

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
        conn.execute(text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS corrected_name VARCHAR(500)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contributions_enrichment ON user_contributions (source, enrichment_status)"))

        # New columns on news_videos
        conn.execute(text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS tags JSONB"))

        # Functional index for site_identifier queries on news_items
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_items_site_name_lower ON news_items (lower(site_name_extracted))"))

        # Rename sources for branding
        conn.execute(text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Originals'
            WHERE id = 'ancient_nerds' AND name != 'ANCIENT NERDS Originals'
        """))
        conn.execute(text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Radar',
                category = 'Primary', priority = 1, is_primary = true
            WHERE id = 'lyra'
        """))

        # Deduplicate lyra contributions: merge rows with same lower(name)
        # into the one with highest mention_count, delete the rest.
        conn.execute(text("""
            WITH dupes AS (
                SELECT lower(name) AS lname,
                       array_agg(id ORDER BY mention_count DESC, created_at) AS ids,
                       sum(mention_count) AS total_mentions
                FROM user_contributions
                WHERE source = 'lyra'
                GROUP BY lower(name)
                HAVING count(*) > 1
            )
            UPDATE user_contributions uc
            SET mention_count = d.total_mentions
            FROM dupes d
            WHERE uc.id = d.ids[1]
              AND lower(uc.name) = d.lname
        """))
        conn.execute(text("""
            WITH dupes AS (
                SELECT lower(name) AS lname,
                       array_agg(id ORDER BY mention_count DESC, created_at) AS ids
                FROM user_contributions
                WHERE source = 'lyra'
                GROUP BY lower(name)
                HAVING count(*) > 1
            )
            DELETE FROM user_contributions
            WHERE id IN (
                SELECT unnest(ids[2:]) FROM dupes
            )
        """))

        # One-time resets: re-enrich discoveries processed with older prompts/logic.
        # Each reset uses a versioned flag in enrichment_data to run only once.
        # v4: improved prompt (new_site near-impossible) + Wikidata re-search + dedup
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching', 'matched')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v4_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v4_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
        """))

        # v5: tiered AI + country validation + tighter pg_trgm threshold
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching', 'matched')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v5_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v5_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
        """))

        # v6: re-enrich items missing wikipedia_url (Wikidata enrichment
        # for db_match was added after earlier resets already ran on VPS)
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('matched', 'failed')
              AND wikipedia_url IS NULL
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v6_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v6_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v6_reset'))
        """))

        # v7: retry — v6 flag was stamped prematurely on first deploy
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('matched', 'failed')
              AND wikipedia_url IS NULL
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v7_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v7_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v7_reset'))
        """))

        # v8: full rescan — new pipeline (AI identifies, code matches DB/Wikidata)
        # Reset ALL non-promoted items so they run through the rewritten prompt
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v8_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v8_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v8_reset'))
        """))

        # v9: AI names only — metadata now comes from Wikipedia, not AI guesses
        # Reset ALL non-promoted items for re-identification with simplified prompt
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v9_reset'))
        """))
        conn.execute(text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v9_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v9_reset'))
        """))

        # Backfill corrected_name from enrichment_data for already-processed items
        # (including promoted ones that the v9 reset doesn't touch)
        conn.execute(text("""
            UPDATE user_contributions
            SET corrected_name = enrichment_data->'identification'->>'site_name'
            WHERE source = 'lyra'
              AND corrected_name IS NULL
              AND enrichment_data IS NOT NULL
              AND enrichment_data->'identification'->>'site_name' IS NOT NULL
              AND lower(trim(enrichment_data->'identification'->>'site_name')) != lower(trim(name))
        """))

        conn.commit()

    # Seed channels
    from pipeline.lyra.channels import seed_channels
    seed_channels()

    # Seed Lyra source for auto-discovered sites
    from pipeline.lyra.site_identifier import seed_lyra_source
    seed_lyra_source()

    # --once or --step: run and exit
    if args.once or args.step:
        cycle_status = "ok"
        cycle_error = None
        try:
            run_pipeline(settings, only_step=args.step)
        except Exception as exc:
            logger.exception("Pipeline cycle failed")
            cycle_status = "error"
            cycle_error = str(exc)

        # Write heartbeat
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
        return

    # Production mode: infinite loop
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
