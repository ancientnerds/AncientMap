"""Main orchestrator for the Lyra news pipeline.

Runs as a long-lived process (Docker entrypoint):
- Hourly: fetch new videos, transcribe, summarize, generate posts, verify, deduplicate
- Weekly: generate digest article

Local dev usage:
  python -m pipeline.lyra.orchestrator --once              # single full cycle
  python -m pipeline.lyra.orchestrator --step identify     # single step only
  python -m pipeline.lyra.orchestrator --once --group news  # run only news steps
"""

import argparse
import concurrent.futures
import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path

from sqlalchemy import text

from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

CYCLE_INTERVAL = 3600  # 1 hour between pipeline runs
MAX_ARTICLE_ATTEMPTS = 3  # Stop retrying after 3 failures per week


def _bust_radar_cache():
    """Tell the API to drop cached radar responses after pipeline updates."""
    import os
    import urllib.request

    try:
        req = urllib.request.Request("http://api:8000/radar/cache-bust", method="POST")
        admin_key = os.getenv("LYRA_ADMIN_KEY", "")
        if admin_key:
            req.add_header("Authorization", f"Bearer {admin_key}")
        urllib.request.urlopen(req, timeout=5)
        logger.info("Radar cache busted")
    except Exception as e:
        logger.debug(f"Radar cache-bust failed (API may be down): {e}")


# Step registry: name -> (function_import_path, description, needs_settings)
STEPS = {
    "fetch": (
        "pipeline.lyra.transcript_fetcher",
        "fetch_new_videos",
        True,
        "Fetched {n} new videos",
    ),
    "retry": (
        "pipeline.lyra.transcript_fetcher",
        "retry_failed_videos",
        True,
        "Retried {n} failed videos",
    ),
    "summarize": (
        "pipeline.lyra.summarizer",
        "summarize_pending_videos",
        True,
        "Summarized {n} videos",
    ),
    "match": (
        "pipeline.lyra.site_matcher",
        "match_sites_for_pending_items",
        False,
        "Matched {n} news items to sites",
    ),
    "posts": (
        "pipeline.lyra.tweet_generator",
        "generate_pending_posts",
        True,
        "Generated {n} posts",
    ),
    "verify": ("pipeline.lyra.tweet_verifier", "verify_pending_posts", True, "Verified {n} posts"),
    "rescore": (
        "pipeline.lyra.significance_scorer",
        "rescore_pending_items",
        True,
        "Re-scored {n} items",
    ),
    "dedup": (
        "pipeline.lyra.tweet_deduplicator",
        "deduplicate_posts",
        True,
        "Removed {n} duplicates",
    ),
    "screenshots": (
        "pipeline.lyra.screenshot_extractor",
        "extract_screenshots",
        True,
        "Extracted {n} screenshots",
    ),
    "backfill": (
        "pipeline.lyra.transcript_fetcher",
        "backfill_video_descriptions",
        True,
        "Backfilled {n} video descriptions",
    ),
    "identify": (
        "pipeline.lyra.site_identifier",
        "identify_and_enrich_sites",
        True,
        "Identified/enriched {n} site discoveries",
    ),
}

# Ordered step list matching the full pipeline sequence
STEP_ORDER = [
    "fetch",
    "retry",
    "summarize",
    "match",
    "posts",
    "verify",
    "rescore",
    "dedup",
    "screenshots",
    "backfill",
    "identify",
]

# Steps that run less often than every cycle. Value = run every N cycles.
# Unlisted steps run every cycle. With CYCLE_INTERVAL=3600, 24 ≈ daily.
STEP_INTERVALS: dict[str, int] = {
    "backfill": 24,
}

# Named groups for --group CLI flag
STEP_GROUPS: dict[str, list[str]] = {
    "news": [
        "fetch",
        "retry",
        "summarize",
        "match",
        "posts",
        "verify",
        "rescore",
        "dedup",
        "screenshots",
        "backfill",
    ],
    "radar": ["identify"],
}

# Tracks how many cycles have elapsed (reset on container restart is fine)
_cycle_count = 0


def setup_logging() -> None:
    """Configure logging for the Lyra pipeline."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Write to file so the API /news/logs endpoint can read it
    log_dir = Path("/app/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ancient_nerds_lyra.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(file_handler)

    logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


STEP_TIMEOUT = 900  # 15 minutes max per step


def _run_step(step_name: str, settings: LyraSettings) -> tuple[int, float]:
    """Run a single pipeline step. Returns (result_count, elapsed_seconds)."""
    import importlib

    module_path, func_name, needs_settings, _ = STEPS[step_name]
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)

    t0 = time.time()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func, settings) if needs_settings else executor.submit(func)
    try:
        result = future.result(timeout=STEP_TIMEOUT)
    except concurrent.futures.TimeoutError:
        # shutdown(wait=False) so we don't block on the hung thread
        executor.shutdown(wait=False, cancel_futures=True)
        logger.error(f"Step '{step_name}' timed out after {STEP_TIMEOUT}s — skipping")
        return -1, time.time() - t0
    else:
        executor.shutdown(wait=False)
    elapsed = time.time() - t0
    return result, elapsed


def _log_cycle_summary(
    step_results: dict[str, tuple[int, float, str | None]], total_elapsed: float
) -> None:
    """Log a summary of what happened in this cycle."""
    from pipeline.database import engine

    # Query DB for current state
    with engine.connect() as conn:
        # Discovery counts
        rows = conn.execute(
            text(
                "SELECT enrichment_status, COUNT(*) FROM user_contributions "
                "WHERE source='lyra' GROUP BY enrichment_status ORDER BY enrichment_status"
            )
        ).fetchall()
        discovery_counts = {row[0]: row[1] for row in rows}
        total_discoveries = sum(discovery_counts.values())

        # Video + news item counts
        video_count = conn.execute(text("SELECT COUNT(*) FROM news_videos")).scalar()
        news_count = conn.execute(text("SELECT COUNT(*) FROM news_items")).scalar()

    lines = ["", "=== Cycle Summary ==="]

    # Step timings
    for name in STEP_ORDER:
        if name in step_results:
            count, elapsed, _err = step_results[name]
            if count < 0:
                lines.append(f"  {name:<12} FAILED")
            else:
                _, _, _, desc_template = STEPS[name]
                desc = desc_template.format(n=count)
                lines.append(f"  {name:<12} {desc} ({elapsed:.1f}s)")

    lines.append("  ---")
    lines.append(f"  Videos: {video_count}  |  News items: {news_count}")

    # Discovery breakdown
    parts = []
    for status in [
        "pending",
        "matched",
        "enriched",
        "promoted",
        "not_a_site",
        "rejected",
        "failed",
    ]:
        if status in discovery_counts:
            parts.append(f"{discovery_counts[status]} {status}")
    lines.append(f"  Discoveries: {total_discoveries} ({', '.join(parts)})")

    lines.append(f"=== Pipeline cycle complete ({total_elapsed:.1f}s) ===")
    logger.info("\n".join(lines))


def _build_step_data(
    step_results: dict[str, tuple[int, float, str | None]],
    running_step: str | None = None,
) -> dict:
    """Build the step_data dict from accumulated results."""
    step_data: dict = {}
    for name in STEP_ORDER:
        if name == running_step:
            step_data[name] = {"count": 0, "elapsed": 0, "status": "run"}
        elif name in step_results:
            count, elapsed, error = step_results[name]
            step_data[name] = {
                "count": count,
                "elapsed": round(elapsed, 1),
                "status": "fail" if count < 0 else "done",
                "error": error,
            }
        elif name in STEP_INTERVALS and _cycle_count % STEP_INTERVALS[name] != 0:
            step_data[name] = {"count": 0, "elapsed": 0, "status": "skip"}
    return step_data


def _write_step_heartbeat(
    step_results: dict[str, tuple[int, float, str | None]],
    running_step: str,
    cycle_start: float,
) -> None:
    """Write incremental step data to heartbeat so the frontend sees live progress."""
    from pipeline.database import engine

    step_data = _build_step_data(step_results, running_step=running_step)
    step_data["_total_elapsed"] = round(time.time() - cycle_start, 1)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE pipeline_heartbeats
                    SET last_heartbeat = NOW(),
                        status = 'ok',
                        step_data = CAST(:step_data AS jsonb)
                    WHERE pipeline_name = 'lyra'
                """),
                {"step_data": json.dumps(step_data)},
            )
            conn.commit()
    except Exception:
        logger.debug("Failed to write incremental heartbeat", exc_info=True)


def run_pipeline(
    settings: LyraSettings, only_step: str | None = None, only_group: str | None = None
) -> dict | None:
    """Run one full pipeline cycle, a single step, or a named group of steps."""
    global _cycle_count

    # Re-seed channels every cycle so new entries in channels.json are picked up
    # without restarting the container.
    from pipeline.lyra.channels import seed_channels

    seed_channels()

    cycle_start = time.time()
    step_results: dict[str, tuple[int, float, str | None]] = {}

    if only_step:
        steps_to_run = [only_step]
    elif only_group:
        group_steps = STEP_GROUPS[only_group]
        steps_to_run = [s for s in STEP_ORDER if s in group_steps]
    else:
        steps_to_run = list(STEP_ORDER)

    if only_step:
        logger.info(f"=== Running single step: {only_step} ===")
    elif only_group:
        logger.info(f"=== Running group '{only_group}': {', '.join(steps_to_run)} ===")
    else:
        _cycle_count += 1
        logger.info(f"=== Starting pipeline cycle #{_cycle_count} ===")

    for step_name in steps_to_run:
        # Skip steps that have a longer interval (unless --step forces it)
        if not only_step and step_name in STEP_INTERVALS:
            interval = STEP_INTERVALS[step_name]
            if _cycle_count % interval != 0:
                continue

        # Mark step as running and write incremental progress
        _write_step_heartbeat(step_results, step_name, cycle_start)

        try:
            result, elapsed = _run_step(step_name, settings)
            step_results[step_name] = (result, elapsed, None)
            _, _, _, desc_template = STEPS[step_name]
            desc = desc_template.format(n=result)
            logger.info(f"  {step_name}: {desc} ({elapsed:.1f}s)")
        except Exception as exc:
            logger.exception(f"  {step_name}: FAILED — continuing to next step")
            step_results[step_name] = (-1, 0.0, str(exc)[:500])

    total_elapsed = time.time() - cycle_start
    _log_cycle_summary(step_results, total_elapsed)

    step_data = _build_step_data(step_results)
    step_data["_total_elapsed"] = round(total_elapsed, 1)
    return step_data


def _run_migrations(engine) -> None:
    """Run all database migrations (schema + data) for the Lyra pipeline."""
    with engine.connect() as conn:
        # Prevent ALTER TABLE from blocking reads on busy tables.
        # If a lock can't be acquired in 5s, the statement fails fast
        # instead of queuing and blocking all API SELECTs.
        conn.execute(text("SET lock_timeout = '5s'"))
        conn.execute(
            text(
                "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS site_match_tried BOOLEAN DEFAULT FALSE"
            )
        )
        conn.execute(text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS significance INTEGER"))
        conn.execute(
            text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS news_category VARCHAR(50)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_news_items_significance ON news_items (significance)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_news_items_news_category ON news_items (news_category)"
            )
        )
        conn.execute(
            text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS speculative_tag VARCHAR(50)")
        )
        # One-time backfill: re-rescore videos with untagged speculative items
        # so the updated prompt assigns speculative_tag subcategories.
        # Naturally idempotent — no-op once all speculative items have tags.
        conn.execute(
            text("""
            UPDATE news_videos SET status = 'verified'
            WHERE status = 'rescored'
            AND id IN (
                SELECT DISTINCT video_id FROM news_items
                WHERE news_category = 'speculative'
                AND speculative_tag IS NULL
                AND post_text IS NOT NULL
            )
        """)
        )
        # Backfill any items that have post_text but no significance (e.g. from errors or old code)
        conn.execute(
            text("""
            UPDATE news_items SET significance = 3, news_category = 'general'
            WHERE post_text IS NOT NULL AND significance IS NULL
        """)
        )
        # Create unified_site_names table if it doesn't exist (for alt-name matching)
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS unified_site_names (
                id SERIAL PRIMARY KEY,
                site_id UUID NOT NULL REFERENCES unified_sites(id) ON DELETE CASCADE,
                name VARCHAR(500) NOT NULL,
                name_normalized VARCHAR(500) NOT NULL,
                language_code VARCHAR(10),
                name_type VARCHAR(50)
            )
        """)
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_usn_name_normalized ON unified_site_names (name_normalized)"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_usn_site ON unified_site_names (site_id)")
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                ALTER TABLE unified_site_names
                    ADD CONSTRAINT uq_usn UNIQUE (site_id, name_normalized);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$
        """)
        )
        # Enable pg_trgm for fuzzy matching (used by discoveries API)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_usn_name_trgm
            ON unified_site_names USING gin (name_normalized gin_trgm_ops)
        """)
        )
        # Pipeline heartbeat table (for LIVE status on frontend)
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS pipeline_heartbeats (
                pipeline_name VARCHAR(50) PRIMARY KEY,
                last_heartbeat TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                status VARCHAR(20) NOT NULL DEFAULT 'ok',
                last_error TEXT
            )
        """)
        )

        # Lyra auto-discovery migrations: new columns on user_contributions
        conn.execute(
            text(
                "ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20) DEFAULT 'pending'"
            )
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS wikidata_id VARCHAR(20)")
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS wikipedia_url TEXT")
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS thumbnail_url TEXT")
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_start INTEGER")
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_end INTEGER")
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS period_name VARCHAR(100)")
        )
        conn.execute(
            text(
                "ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS last_facts_hash VARCHAR(64)"
            )
        )
        conn.execute(
            text("ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS enrichment_data JSONB")
        )
        conn.execute(
            text(
                "ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS promoted_site_id UUID REFERENCES unified_sites(id) ON DELETE SET NULL"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE user_contributions ADD COLUMN IF NOT EXISTS corrected_name VARCHAR(500)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_contributions_enrichment ON user_contributions (source, enrichment_status)"
            )
        )

        # New columns on news_videos
        conn.execute(text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS tags JSONB"))
        conn.execute(
            text("ALTER TABLE news_videos ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMP")
        )

        # Functional index for site_identifier queries on news_items
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_news_items_site_name_lower ON news_items (lower(site_name_extracted))"
            )
        )

        # Lyra RAG enrichment columns on news_items
        conn.execute(
            text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS transcript_segment TEXT")
        )
        conn.execute(text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS entities JSONB"))
        conn.execute(text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS tags JSONB"))

        # Add updated_at column to unified_sites for edit tracking
        conn.execute(
            text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP")
        )

        # Rename sources for branding
        conn.execute(
            text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Originals'
            WHERE id = 'ancient_nerds' AND name != 'ANCIENT NERDS Originals'
        """)
        )
        conn.execute(
            text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Radar',
                category = 'Primary', priority = 1, is_primary = true
            WHERE id = 'lyra'
        """)
        )
        conn.execute(
            text("""
            UPDATE source_meta SET name = 'ANCIENT NERDS Community',
                category = 'Primary', priority = 2, is_primary = true
            WHERE id = 'ancient_nerds_community'
        """)
        )

        # Update source categories (grouped for filter panel)
        conn.execute(
            text("""
            UPDATE source_meta SET category = 'Archaeological Databases'
            WHERE id IN ('pleiades','dare','topostext','unesco','wikidata','geonames',
                         'osm_historic','open_context','eamena')
              AND category != 'Archaeological Databases'
        """)
        )
        conn.execute(
            text("""
            UPDATE source_meta SET category = 'Regional Surveys'
            WHERE id IN ('canmore_scotland','coflein_wales','historic_england','ireland_nms',
                         'mycenaean_atlas','luwian_atlas','radiocarbon_paleo',
                         'arachne','vici_org','rock_art','peru_amazon')
              AND category != 'Regional Surveys'
        """)
        )
        conn.execute(
            text("""
            UPDATE source_meta SET category = 'Inscriptions & Coins'
            WHERE id IN ('inscriptions_edh','list_inscriptions','coins_nomisma')
              AND category != 'Inscriptions & Coins'
        """)
        )
        conn.execute(
            text("""
            UPDATE source_meta SET category = 'Natural Events'
            WHERE id IN ('volcanic_holvol','earth_impacts','ncei_earthquakes','ncei_tsunamis',
                         'ncei_tsunami_obs','ncei_volcanoes')
              AND category != 'Natural Events'
        """)
        )

        # Remove megalithic_portal (ToS prohibits redistribution)
        conn.execute(
            text("""
            UPDATE news_items SET site_id = NULL
            WHERE site_id IN (SELECT id FROM unified_sites WHERE source_id = 'megalithic_portal')
        """)
        )
        conn.execute(text("DELETE FROM unified_sites WHERE source_id = 'megalithic_portal'"))
        conn.execute(text("DELETE FROM source_meta WHERE id = 'megalithic_portal'"))

        # Deduplicate lyra contributions: merge rows with same lower(name)
        # into the one with highest mention_count, delete the rest.
        conn.execute(
            text("""
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
        """)
        )
        conn.execute(
            text("""
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
        """)
        )

        # One-time resets: re-enrich discoveries processed with older prompts/logic.
        # Each reset uses a versioned flag in enrichment_data to run only once.
        # v4: improved prompt (new_site near-impossible) + Wikidata re-search + dedup
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching', 'matched')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v4_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v4_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
        """)
        )

        # v5: tiered AI + country validation + tighter pg_trgm threshold
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching', 'matched')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v5_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v5_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
        """)
        )

        # v6: re-enrich items missing wikipedia_url (Wikidata enrichment
        # for db_match was added after earlier resets already ran on VPS)
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('matched', 'failed')
              AND wikipedia_url IS NULL
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v6_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v6_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v6_reset'))
        """)
        )

        # v7: retry — v6 flag was stamped prematurely on first deploy
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('matched', 'failed')
              AND wikipedia_url IS NULL
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v7_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v7_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v7_reset'))
        """)
        )

        # v8: full rescan — new pipeline (AI identifies, code matches DB/Wikidata)
        # Reset ALL non-promoted items so they run through the rewritten prompt
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v8_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v8_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v8_reset'))
        """)
        )

        # v9: AI names only — metadata now comes from Wikipedia, not AI guesses
        # Reset ALL non-promoted items for re-identification with simplified prompt
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v9_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v9_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v9_reset'))
        """)
        )

        # Backfill corrected_name from enrichment_data for already-processed items
        # (including promoted ones that the v9 reset doesn't touch)
        conn.execute(
            text("""
            UPDATE user_contributions
            SET corrected_name = enrichment_data->'identification'->>'site_name'
            WHERE source = 'lyra'
              AND corrected_name IS NULL
              AND enrichment_data IS NOT NULL
              AND enrichment_data->'identification'->>'site_name' IS NOT NULL
              AND lower(trim(enrichment_data->'identification'->>'site_name')) != lower(trim(name))
        """)
        )

        # Fix period_name: re-bucket from period_start using canonical 500-year buckets
        # Runs once via fix_period_buckets_v1 flag in enrichment_data
        conn.execute(
            text("""
            UPDATE user_contributions
            SET period_name = CASE
                WHEN period_start < -4500 THEN '< 4500 BC'
                WHEN period_start < -3000 THEN '4500 - 3000 BC'
                WHEN period_start < -1500 THEN '3000 - 1500 BC'
                WHEN period_start < -500  THEN '1500 - 500 BC'
                WHEN period_start < 1     THEN '500 BC - 1 AD'
                WHEN period_start < 500   THEN '1 - 500 AD'
                WHEN period_start < 1000  THEN '500 - 1000 AD'
                WHEN period_start < 1500  THEN '1000 - 1500 AD'
                ELSE '1500+ AD'
            END
            WHERE source = 'lyra'
              AND period_start IS NOT NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'fix_period_buckets_v1'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"fix_period_buckets_v1": true}'::jsonb
            WHERE source = 'lyra'
              AND period_start IS NOT NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'fix_period_buckets_v1'))
        """)
        )

        # v10: re-enrich items missing period_start or site_type so Wikipedia
        # enrichment can fill them in (badges show gray/missing without these)
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching')
              AND promoted_site_id IS NULL
              AND (period_start IS NULL OR site_type IS NULL)
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v10_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v10_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v10_reset'))
        """)
        )

        # v11: retry country_mismatch rejections — comparison now normalizes name variants
        # (e.g. "United States" vs "United States of America" no longer mismatches)
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status = 'rejected'
              AND promoted_site_id IS NULL
              AND enrichment_data->'rejected_match'->>'reason' = 'country_mismatch'
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v11_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v11_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v11_reset'))
              AND enrichment_data->'rejected_match'->>'reason' = 'country_mismatch'
        """)
        )

        # v12: re-enrich items with non-canonical period_name (comma-formatted numbers
        # like "11,000+" weren't parsed by extract_period_from_text, leaving period_start NULL
        # and raw freetext in period_name). The fixed parser can now handle these.
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching')
              AND promoted_site_id IS NULL
              AND period_name IS NOT NULL
              AND period_name NOT IN (
                  '< 4500 BC', '4500 - 3000 BC', '3000 - 1500 BC',
                  '1500 - 500 BC', '500 BC - 1 AD', '1 - 500 AD',
                  '500 - 1000 AD', '1000 - 1500 AD', '1500+ AD', 'Unknown'
              )
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v12_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v12_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v12_reset'))
        """)
        )

        # Also fix promoted unified_sites that have period_start but non-canonical period_name
        conn.execute(
            text("""
            UPDATE unified_sites
            SET period_name = CASE
                WHEN period_start < -4500 THEN '< 4500 BC'
                WHEN period_start < -3000 THEN '4500 - 3000 BC'
                WHEN period_start < -1500 THEN '3000 - 1500 BC'
                WHEN period_start < -500  THEN '1500 - 500 BC'
                WHEN period_start < 1     THEN '500 BC - 1 AD'
                WHEN period_start < 500   THEN '1 - 500 AD'
                WHEN period_start < 1000  THEN '500 - 1000 AD'
                WHEN period_start < 1500  THEN '1000 - 1500 AD'
                ELSE '1500+ AD'
            END
            WHERE source_id = 'lyra'
              AND period_start IS NOT NULL
              AND period_name NOT IN (
                  '< 4500 BC', '4500 - 3000 BC', '3000 - 1500 BC',
                  '1500 - 500 BC', '500 BC - 1 AD', '1 - 500 AD',
                  '500 - 1000 AD', '1000 - 1500 AD', '1500+ AD'
              )
        """)
        )

        # Data quality patches (countries, periods, aliases) — see data_patches.py
        from pipeline.lyra.data_patches import run_data_patches

        run_data_patches(conn)

        # v12b: fix promoted items where period_start is NULL but period_name has
        # parseable text (e.g. "Pre-Pottery Neolithic (11,000+ years ago)").
        # These can't be reset to pending since they're already promoted — run the
        # fixed Python parser directly to set period_start + canonical period_name.
        from pipeline.utils.text import categorize_period, extract_period_from_text

        canonical_periods = (
            "< 4500 BC",
            "4500 - 3000 BC",
            "3000 - 1500 BC",
            "1500 - 500 BC",
            "500 BC - 1 AD",
            "1 - 500 AD",
            "500 - 1000 AD",
            "1000 - 1500 AD",
            "1500+ AD",
            "Unknown",
        )

        # Fix unified_sites
        rows = conn.execute(
            text("""
            SELECT id, period_name FROM unified_sites
            WHERE source_id = 'lyra'
              AND period_start IS NULL
              AND period_name IS NOT NULL
        """)
        ).fetchall()
        for row in rows:
            if row.period_name in canonical_periods:
                continue
            period_start = extract_period_from_text(row.period_name)
            if period_start is not None:
                conn.execute(
                    text(
                        "UPDATE unified_sites SET period_name = :pname, period_start = :pstart WHERE id = :id"
                    ),
                    {
                        "pname": categorize_period(period_start),
                        "pstart": period_start,
                        "id": row.id,
                    },
                )

        # Fix user_contributions (promoted ones the v12 reset skipped)
        rows = conn.execute(
            text("""
            SELECT id, period_name FROM user_contributions
            WHERE source = 'lyra'
              AND promoted_site_id IS NOT NULL
              AND period_start IS NULL
              AND period_name IS NOT NULL
        """)
        ).fetchall()
        for row in rows:
            if row.period_name in canonical_periods:
                continue
            period_start = extract_period_from_text(row.period_name)
            if period_start is not None:
                conn.execute(
                    text(
                        "UPDATE user_contributions SET period_name = :pname, period_start = :pstart WHERE id = :id"
                    ),
                    {
                        "pname": categorize_period(period_start),
                        "pstart": period_start,
                        "id": row.id,
                    },
                )

        # v13: external source matches should create radar cards (not be hidden as "matched").
        # Re-process items that were matched to external sources (not AN Originals, not promoted).
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status = 'matched'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v13_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v13_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v13_reset'))
        """)
        )

        # v14: Fix garbled site names in news_items text fields.
        # Replace site_name_extracted with canonical unified_sites.name
        # in headline, post_text, and summary for already-matched items.
        # IMPORTANT: skip when extracted name is a substring of canonical name,
        # otherwise REPLACE expands on every restart (e.g. "Calico" inside
        # "Calico Early Man Site" causes exponential growth).
        conn.execute(
            text("""
            UPDATE news_items ni
            SET headline = REPLACE(ni.headline, ni.site_name_extracted, us.name),
                post_text = REPLACE(ni.post_text, ni.site_name_extracted, us.name),
                summary = REPLACE(ni.summary, ni.site_name_extracted, us.name)
            FROM unified_sites us
            WHERE ni.site_id = us.id
              AND ni.site_name_extracted IS NOT NULL
              AND ni.site_name_extracted != us.name
              AND us.name NOT LIKE '%' || ni.site_name_extracted || '%'
              AND (ni.headline LIKE '%' || ni.site_name_extracted || '%'
                   OR ni.post_text LIKE '%' || ni.site_name_extracted || '%'
                   OR ni.summary LIKE '%' || ni.site_name_extracted || '%')
        """)
        )
        # Also fix facts (JSONB array of strings): replace garbled name in each element
        conn.execute(
            text("""
            UPDATE news_items ni
            SET facts = (
                SELECT jsonb_agg(
                    to_jsonb(REPLACE(elem #>> '{}', ni.site_name_extracted, us.name))
                )
                FROM jsonb_array_elements(ni.facts) AS elem
            )
            FROM unified_sites us
            WHERE ni.site_id = us.id
              AND ni.site_name_extracted IS NOT NULL
              AND ni.site_name_extracted != us.name
              AND us.name NOT LIKE '%' || ni.site_name_extracted || '%'
              AND ni.facts IS NOT NULL
              AND ni.facts::text LIKE '%' || ni.site_name_extracted || '%'
        """)
        )

        # v14b: Repair items corrupted by v14's substring expansion bug.
        # The v14 REPLACE(text, extracted, canonical) runs on every restart.
        # When extracted is a substring of canonical, each restart expands:
        #   Prefix case: "Calico" in "Calico Early Man Site" → suffix repeats
        #   Suffix case: "Fajada Butte" in "Chaco Culture NHP- Fajada Butte" → prefix repeats
        # Fix: collapse by replacing (prefix + canonical) and (canonical + suffix)
        # with canonical until stable.
        import json as _json

        corrupted = conn.execute(
            text("""
            SELECT ni.id, us.name AS cname, ni.site_name_extracted AS extracted,
                   ni.headline, ni.post_text, ni.summary, ni.facts
            FROM news_items ni
            JOIN unified_sites us ON ni.site_id = us.id
            WHERE ni.site_name_extracted IS NOT NULL
              AND ni.site_name_extracted != us.name
              AND us.name LIKE '%' || ni.site_name_extracted || '%'
        """)
        ).fetchall()
        _ALLOWED_COLLAPSE_COLS = {"headline", "post_text", "summary", "facts"}
        for row in corrupted:
            idx = row.cname.index(row.extracted)
            prefix = row.cname[:idx]  # e.g. "Chaco Culture NHP- "
            suffix = row.cname[idx + len(row.extracted) :]  # e.g. " Early Man Site"
            # Build the two bloated patterns to collapse
            patterns = []
            if prefix:
                patterns.append((prefix + row.cname, row.cname))
            if suffix:
                patterns.append((row.cname + suffix, row.cname))
            if not patterns:
                continue

            def _collapse(val: str, patterns=patterns) -> str:
                # Terminates: bloated is strictly longer than clean
                for bloated, clean in patterns:
                    while bloated in val:
                        val = val.replace(bloated, clean)
                return val

            fields = {"headline": row.headline, "post_text": row.post_text, "summary": row.summary}
            updates = {}
            for col, val in fields.items():
                if not val:
                    continue
                fixed = _collapse(val)
                if fixed != val:
                    updates[col] = fixed
            if row.facts:
                fixed_facts = [_collapse(f) for f in row.facts]
                if fixed_facts != list(row.facts):
                    updates["facts"] = _json.dumps(fixed_facts)
            if updates:
                for k in updates:
                    if k not in _ALLOWED_COLLAPSE_COLS:
                        raise ValueError(f"Unexpected column in collapse migration: {k}")
                sets = ", ".join(
                    f"{k} = CAST(:{k} AS jsonb)" if k == "facts" else f"{k} = :{k}" for k in updates
                )
                updates["id"] = row.id
                conn.execute(text(f"UPDATE news_items SET {sets} WHERE id = :id"), updates)

        # v15: retry all failed discoveries now that API has rate throttle + retry backoff
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status = 'failed'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v15_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v15_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND enrichment_status IN ('pending', 'failed')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v15_reset'))
        """)
        )

        # v16: rescore with recency-aware prompt — old discoveries were scored 7-9
        conn.execute(
            text("""
            UPDATE news_videos
            SET status = 'verified'
            WHERE status = 'rescored'
              AND id IN (
                  SELECT DISTINCT video_id FROM news_items
                  WHERE post_text IS NOT NULL AND significance >= 6
              )
              AND (tags IS NULL OR NOT (tags @> '"__rescore_v16"'::jsonb))
        """)
        )
        conn.execute(
            text("""
            UPDATE news_videos
            SET tags = COALESCE(tags, '[]'::jsonb) || '["__rescore_v16"]'::jsonb
            WHERE (tags IS NULL OR NOT (tags @> '"__rescore_v16"'::jsonb))
              AND status IN ('verified', 'rescored')
              AND id IN (
                  SELECT DISTINCT video_id FROM news_items
                  WHERE post_text IS NOT NULL AND significance >= 6
              )
        """)
        )

        # v_research: re-process ALL non-promoted items through the new deep
        # research pipeline (pre-research + multi-source search + gap-fill)
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'failed')
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v_research_reset'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v_research_reset": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v_research_reset'))
        """)
        )

        # v_no_ai_guess: re-enrich AI-path items that got gap-fill/pre-research
        # data applied (now disabled). Clear AI-guessed fields so only verified
        # sources (Wikidata, Wikipedia, GeoNames, DB match) populate them.
        # Only affects items without Wikidata enrichment (AI-only path).
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'enriching')
              AND promoted_site_id IS NULL
              AND wikidata_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v_no_ai_guess'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v_no_ai_guess": true}'::jsonb
            WHERE source = 'lyra'
              AND promoted_site_id IS NULL
              AND wikidata_id IS NULL
              AND (enrichment_data IS NULL OR NOT (enrichment_data ? 'v_no_ai_guess'))
        """)
        )

        # v_an_dedup: re-enrich contributions that share a normalized name
        # with AN Originals sites — the new name-based AN check will match them
        conn.execute(
            text("""
            UPDATE user_contributions uc
            SET enrichment_status = 'pending', last_facts_hash = NULL
            FROM unified_sites us
            WHERE uc.source = 'lyra'
              AND uc.enrichment_status NOT IN ('matched', 'failed', 'not_a_site')
              AND uc.promoted_site_id IS NULL
              AND us.source_id = 'ancient_nerds'
              AND us.name_normalized = lower(trim(COALESCE(uc.corrected_name, uc.name)))
              AND (uc.enrichment_data IS NULL OR NOT (uc.enrichment_data ? 'v_an_dedup'))
        """)
        )
        conn.execute(
            text("""
            UPDATE user_contributions uc
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || '{"v_an_dedup": true}'::jsonb
            FROM unified_sites us
            WHERE uc.source = 'lyra'
              AND uc.promoted_site_id IS NULL
              AND us.source_id = 'ancient_nerds'
              AND us.name_normalized = lower(trim(COALESCE(uc.corrected_name, uc.name)))
              AND (uc.enrichment_data IS NULL OR NOT (uc.enrichment_data ? 'v_an_dedup'))
        """)
        )

        # Wiki images table for self-hosted Wikipedia/Commons images
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS wiki_images (
                id SERIAL PRIMARY KEY,
                site_id UUID NOT NULL REFERENCES unified_sites(id) ON DELETE CASCADE,
                filename VARCHAR(500) NOT NULL,
                original_url TEXT NOT NULL,
                commons_page_url TEXT,
                thumb_width INTEGER,
                author TEXT,
                author_url TEXT,
                license VARCHAR(50),
                license_url TEXT,
                title TEXT,
                is_hero BOOLEAN DEFAULT FALSE,
                is_lead BOOLEAN DEFAULT FALSE,
                sort_order INTEGER DEFAULT 0,
                source_type VARCHAR(20) DEFAULT 'wikimedia',
                file_size_bytes INTEGER,
                width INTEGER,
                height INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_wiki_images_site ON wiki_images (site_id)")
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                ALTER TABLE wiki_images
                    ADD CONSTRAINT uq_wiki_image_site_url UNIQUE (site_id, original_url);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$
        """)
        )

        # Source version pins table (per-source snapshot pinning for public globe)
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS source_version_pins (
                source_id VARCHAR(50) PRIMARY KEY,
                snapshot_date VARCHAR(30),
                pinned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                pinned_by VARCHAR(50) NOT NULL
            )
        """)
        )

        # Fix wikipedia_url / wikidata_id swap: rows where wikipedia_url
        # points to wikidata.org should have the QID in wikidata_id instead
        conn.execute(
            text("""
            UPDATE user_contributions
            SET wikidata_id = substring(wikipedia_url from 'Q\\d+'),
                wikipedia_url = NULL
            WHERE wikipedia_url LIKE '%wikidata.org%'
              AND (wikidata_id IS NULL OR wikidata_id = '')
        """)
        )

        # One-time fix: re-fetch real published_at from YouTube API for videos
        # where datetime.now(UTC) fallback corrupted the date.
        # Done inline with conn (get_session has a shorter statement timeout).
        _dates_fixed = conn.execute(
            text("""
            SELECT 1 FROM news_videos
            WHERE tags IS NOT NULL AND tags @> '"__dates_fixed"'::jsonb
            LIMIT 1
        """)
        ).fetchone()
        if not _dates_fixed:
            from datetime import datetime as _dt

            from pipeline.lyra.config import LyraSettings as _LS

            _api_key = _LS().youtube_api_key
            if _api_key:
                from pipeline.utils.http import fetch_with_retry as _fetch

                _all_ids = [
                    r[0] for r in conn.execute(text("SELECT id FROM news_videos")).fetchall()
                ]
                _fixed = 0
                for _i in range(0, len(_all_ids), 50):
                    _batch = _all_ids[_i : _i + 50]
                    try:
                        _resp = _fetch(
                            "https://www.googleapis.com/youtube/v3/videos",
                            params={"id": ",".join(_batch), "part": "snippet", "key": _api_key},
                        )
                        _data = _resp.json()
                    except Exception as _e:
                        logger.warning(f"YouTube API date fix batch failed: {_e}")
                        continue
                    for _item in _data.get("items", []):
                        _pub = _item.get("snippet", {}).get("publishedAt", "")
                        try:
                            _real = _dt.fromisoformat(_pub.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            continue
                        conn.execute(
                            text("UPDATE news_videos SET published_at = :d WHERE id = :id"),
                            {"d": _real, "id": _item["id"]},
                        )
                        _fixed += 1
                logger.info(f"Fixed published_at for {_fixed} videos")
            # Stamp sentinel so this doesn't run again
            conn.execute(
                text("""
                UPDATE news_videos SET tags = COALESCE(tags, '[]'::jsonb) || '["__dates_fixed"]'::jsonb
                WHERE id = (SELECT id FROM news_videos LIMIT 1)
            """)
            )

        # Missing columns on unified_sites that models define but were never migrated
        conn.execute(text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS raw_data JSONB"))
        conn.execute(text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS period_end INTEGER"))

        # Site hierarchy: parent_site_id for "part of" relationships
        # (e.g. Great Sphinx → Giza Necropolis)
        conn.execute(
            text(
                "ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS parent_site_id UUID REFERENCES unified_sites(id) ON DELETE SET NULL"
            )
        )

        # Edit tracking: who last edited the row
        conn.execute(
            text(
                "ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS edited_by VARCHAR(20) NOT NULL DEFAULT 'initial'"
            )
        )

        # Normalize ALL site_type values through the canonical normalizer.
        # Runs every startup but only UPDATEs rows where the value actually changes.
        from pipeline.normalizers.site_type import normalize_site_type as _norm_type

        _raw_types = conn.execute(
            text("SELECT DISTINCT site_type FROM unified_sites WHERE site_type IS NOT NULL")
        ).fetchall()
        for (raw,) in _raw_types:
            canonical = _norm_type(raw)
            if canonical != raw:
                conn.execute(
                    text("UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw"),
                    {"canonical": canonical, "raw": raw},
                )

        _raw_types_uc = conn.execute(
            text("SELECT DISTINCT site_type FROM user_contributions WHERE site_type IS NOT NULL")
        ).fetchall()
        for (raw,) in _raw_types_uc:
            canonical = _norm_type(raw)
            if canonical != raw:
                conn.execute(
                    text(
                        "UPDATE user_contributions SET site_type = :canonical WHERE site_type = :raw"
                    ),
                    {"canonical": canonical, "raw": raw},
                )

        # Pipeline efficiency: per-item verification tracking
        conn.execute(text("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP"))
        # Backfill: mark items in already-verified videos so they don't re-run
        conn.execute(
            text("""
            UPDATE news_items SET verified_at = NOW()
            WHERE post_text IS NOT NULL
              AND verified_at IS NULL
              AND video_id IN (SELECT id FROM news_videos WHERE status IN ('verified', 'rescored'))
        """)
        )

        # Pipeline efficiency: cap screenshot retry attempts across cycles
        conn.execute(
            text(
                "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS screenshot_attempts INTEGER DEFAULT 0"
            )
        )

        # is_unlimited flag: decoupled from credits balance
        conn.execute(
            text(
                "ALTER TABLE discord_users ADD COLUMN IF NOT EXISTS is_unlimited BOOLEAN DEFAULT FALSE"
            )
        )
        # Migrate legacy credits=-1 to the new flag
        conn.execute(
            text("UPDATE discord_users SET is_unlimited = TRUE, credits = 0 WHERE credits = -1")
        )

        # Role-based credit system: monthly grants with accumulation
        conn.execute(
            text("ALTER TABLE discord_users ADD COLUMN IF NOT EXISTS grant_anchor_date TIMESTAMP")
        )
        conn.execute(
            text("ALTER TABLE credit_grants ADD COLUMN IF NOT EXISTS grant_period VARCHAR(7)")
        )
        conn.execute(
            text("""
            DO $$ BEGIN
                ALTER TABLE credit_grants
                    ADD CONSTRAINT uq_credit_grants_user_reason_period
                    UNIQUE (user_id, reason, grant_period);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$
        """)
        )

        # The UNIQUE(user_id, reason, grant_period) constraint does NOT prevent
        # duplicate one-time grants because NULL != NULL in PostgreSQL.
        # Add a partial unique index covering the grant_period IS NULL case.

        # Deduplicate one-time grants before adding the unique index.
        # Keep the oldest row (smallest created_at) per (user_id, reason).
        conn.execute(
            text("""
            DELETE FROM credit_grants a
            USING credit_grants b
            WHERE a.user_id = b.user_id
              AND a.reason = b.reason
              AND a.grant_period IS NULL
              AND b.grant_period IS NULL
              AND a.created_at > b.created_at
        """)
        )

        conn.execute(
            text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_grants_one_time
            ON credit_grants (user_id, reason)
            WHERE grant_period IS NULL
        """)
        )

        # Migrate one-time grants from NULL to "one_time" sentinel so the
        # regular unique constraint (user_id, reason, grant_period) can prevent
        # duplicates. Previously NULL was used, but NULL != NULL in PostgreSQL.
        conn.execute(
            text("""
            UPDATE credit_grants
            SET grant_period = 'one_time'
            WHERE grant_period IS NULL
        """)
        )

        # Card descriptions column for Forgotten Worlds card game
        conn.execute(
            text("ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS card_description VARCHAR(150)")
        )
        conn.execute(text("ALTER TABLE card_stats ALTER COLUMN card_description TYPE VARCHAR(200)"))

        # Audit & enrichment tracking columns
        conn.execute(
            text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS last_audited TIMESTAMP")
        )
        conn.execute(
            text("ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS last_enriched TIMESTAMP")
        )

        # Snapshot source tracking: which database a snapshot belongs to
        conn.execute(
            text("ALTER TABLE db_snapshots ADD COLUMN IF NOT EXISTS source_id VARCHAR(50)")
        )

        # --- Data migrations (idempotent) ---

        # Backfill AN Originals into unified_site_names so _fetch_db_candidates()
        # can find them.  Inserts a 'label' row for every unified_sites entry
        # that doesn't already have a matching normalized name.
        conn.execute(
            text(
                """
                INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
                SELECT id, name, COALESCE(name_normalized, lower(name)), 'label'
                FROM unified_sites us
                WHERE NOT EXISTS (
                    SELECT 1 FROM unified_site_names usn
                    WHERE usn.site_id = us.id
                      AND usn.name_normalized = COALESCE(us.name_normalized, lower(us.name))
                )
                """
            )
        )

        # Strip diacritics from unified_site_names.name_normalized so trigram
        # search treats accented and unaccented forms identically.  The backfill
        # migration used lower(name) which keeps accents (e.g. 'sacsayhuamán'),
        # while normalize_name() strips them — causing AN Originals entries
        # to rank below accent-free external sources in fuzzy matches.
        conn.execute(
            text("""
            UPDATE unified_site_names
            SET name_normalized = left(lower(unaccent(name_normalized)), 500)
            WHERE name_normalized IS DISTINCT FROM lower(unaccent(name_normalized))
        """)
        )

        # Also fix unified_sites.name_normalized for the same reason
        conn.execute(
            text("""
            UPDATE unified_sites
            SET name_normalized = left(lower(unaccent(name)), 500)
            WHERE name_normalized IS NULL
               OR name_normalized IS DISTINCT FROM lower(unaccent(name_normalized))
        """)
        )

        # Delete stale AI-generated research_alias entries that cause false
        # matches (e.g. Stonehenge → Avebury).  Code no longer creates these;
        # they were replaced by wikidata_alias.
        conn.execute(text("DELETE FROM unified_site_names WHERE name_type = 'research_alias'"))

        # Re-score videos that lost significance: reset 'rescored' → 'verified'
        # when their items have post_text but NULL significance (never scored).
        # NOTE: Do NOT include "significance = 3" — the LLM legitimately assigns
        # 3 as a score.  Including it caused infinite rescore loops (flip-flopping).
        conn.execute(
            text(
                """
                UPDATE news_videos SET status = 'verified'
                WHERE status = 'rescored'
                  AND id IN (
                    SELECT DISTINCT video_id FROM news_items
                    WHERE post_text IS NOT NULL
                      AND significance IS NULL
                  )
                """
            )
        )

        # v_postgen: Reset videos whose news_items have NULL post_text back to
        # 'summarized' so the tweet_generator re-runs.  Videos advanced past
        # summarized before post generation ran, leaving 68 items with no text.
        conn.execute(
            text("""
            UPDATE news_videos SET status = 'summarized'
            WHERE status IN ('posted', 'verified', 'rescored')
              AND id IN (
                SELECT DISTINCT video_id FROM news_items
                WHERE post_text IS NULL
                  AND news_category IS DISTINCT FROM 'rejected'
                  AND news_category IS DISTINCT FROM 'duplicate'
              )
              AND summary_json IS NOT NULL
        """)
        )

        # Reset discoveries wrongly classified as not_a_site due to prompt
        # confusion (LLM interpreted "site" as "website").  Idempotent: once
        # reprocessed, status changes and this no longer matches.
        conn.execute(
            text("""
            UPDATE user_contributions SET enrichment_status = 'pending', last_facts_hash = NULL
            WHERE name = 'Bees Bejisultan Huyek'
              AND enrichment_status = 'not_a_site'
        """)
        )

        # Delete broken article #7 (2026-03-16 week, saved with empty body
        # before pipeline was fixed). Will be regenerated next Sunday cycle.
        conn.execute(text("DELETE FROM news_articles WHERE id = 7"))

        # Add step_data column to heartbeats for per-step timing persistence
        conn.execute(
            text("ALTER TABLE pipeline_heartbeats ADD COLUMN IF NOT EXISTS step_data JSONB")
        )

        # Theo specialist options: force_include / force_exclude
        conn.execute(
            text("ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS specialist_options JSONB")
        )

        # Theo public research library
        conn.execute(
            text("ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE")
        )
        conn.execute(
            text("ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
        )
        conn.execute(
            text("ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS published_by VARCHAR(100)")
        )
        conn.execute(
            text("ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS slug VARCHAR(300)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_research_requests_public ON research_requests (is_public, published_at)")
        )

        conn.commit()


def main() -> None:
    """Main entry point for the Lyra pipeline service."""
    parser = argparse.ArgumentParser(description="Lyra news pipeline orchestrator")
    parser.add_argument("--once", action="store_true", help="Run a single pipeline cycle and exit")
    parser.add_argument("--step", choices=list(STEPS.keys()), help="Run only a single named step")
    parser.add_argument(
        "--group", choices=list(STEP_GROUPS.keys()), help="Run only steps in a named group"
    )
    args = parser.parse_args()

    setup_logging()
    logger.info("Lyra Whiskerbyte pipeline starting...")

    settings = LyraSettings()

    # Create tables if they don't exist, then run migrations
    from pipeline.database import create_all_tables, engine

    create_all_tables()
    try:
        _run_migrations(engine)
    except Exception as mig_err:
        logger.warning(f"[STARTUP] Migrations skipped (lock contention): {mig_err}")

    # Seed channels
    from pipeline.lyra.channels import seed_channels

    seed_channels()

    # Seed Lyra source for auto-discovered sites
    from pipeline.lyra.site_identifier import seed_lyra_source

    seed_lyra_source()

    # Seed Community source for user contributions
    from pipeline.database import SourceMeta, get_session

    with get_session() as session:
        if not session.get(SourceMeta, "ancient_nerds_community"):
            session.add(
                SourceMeta(
                    id="ancient_nerds_community",
                    name="ANCIENT NERDS Community",
                    color="#22c55e",
                    category="Primary",
                    priority=2,
                    enabled=True,
                    enabled_by_default=False,
                    is_primary=True,
                    record_count=0,
                )
            )
            session.commit()

    # --once or --step or --group: run and exit
    if args.once or args.step or args.group:
        cycle_status = "ok"
        cycle_error = None
        step_data = None
        try:
            step_data = run_pipeline(settings, only_step=args.step, only_group=args.group)
        except Exception as exc:
            logger.exception("Pipeline cycle failed")
            cycle_status = "error"
            cycle_error = str(exc)

        _bust_radar_cache()

        # Write heartbeat
        with engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO pipeline_heartbeats (pipeline_name, last_heartbeat, status, last_error, step_data)
                VALUES ('lyra', NOW(), :status, :error, CAST(:step_data AS jsonb))
                ON CONFLICT (pipeline_name) DO UPDATE SET
                    last_heartbeat = NOW(),
                    status = EXCLUDED.status,
                    last_error = EXCLUDED.last_error,
                    step_data = EXCLUDED.step_data
            """),
                {
                    "status": cycle_status,
                    "error": cycle_error,
                    "step_data": json.dumps(step_data) if step_data else None,
                },
            )
            conn.commit()
        return

    # Production mode: infinite loop
    from pipeline.lyra.article_generator import generate_weekly_article, should_generate_article

    last_pipeline_run = 0.0
    article_attempts = 0
    article_week_tracked: str | None = None  # ISO date of the week we're tracking

    while True:
        now = time.time()

        # Run pipeline every hour
        if now - last_pipeline_run >= CYCLE_INTERVAL:
            cycle_status = "ok"
            cycle_error = None
            step_data = None
            try:
                step_data = run_pipeline(settings)
            except Exception as exc:
                logger.exception("Pipeline cycle failed")
                cycle_status = "error"
                cycle_error = str(exc)
            last_pipeline_run = now

            _bust_radar_cache()

            # Write heartbeat so the API can report LIVE/OFFLINE
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO pipeline_heartbeats (pipeline_name, last_heartbeat, status, last_error, step_data)
                        VALUES ('lyra', NOW(), :status, :error, CAST(:step_data AS jsonb))
                        ON CONFLICT (pipeline_name) DO UPDATE SET
                            last_heartbeat = NOW(),
                            status = EXCLUDED.status,
                            last_error = EXCLUDED.last_error,
                            step_data = EXCLUDED.step_data
                    """),
                        {
                            "status": cycle_status,
                            "error": cycle_error,
                            "step_data": json.dumps(step_data) if step_data else None,
                        },
                    )
                    conn.commit()
            except Exception:
                logger.exception("Failed to write heartbeat")

        # Weekly article generation (with retry limit)
        if should_generate_article():
            current_week = time.strftime("%Y-W%W", time.gmtime())
            if current_week != article_week_tracked:
                article_attempts = 0
                article_week_tracked = current_week

            if article_attempts < MAX_ARTICLE_ATTEMPTS:
                article_attempts += 1
                try:
                    success = generate_weekly_article(settings)
                    if success:
                        logger.info(
                            "Article generated successfully on attempt %d", article_attempts
                        )
                        article_attempts = MAX_ARTICLE_ATTEMPTS  # stop retrying
                    else:
                        logger.warning(
                            "Article generation returned False (attempt %d/%d)",
                            article_attempts,
                            MAX_ARTICLE_ATTEMPTS,
                        )
                except Exception:
                    logger.exception(
                        "Article generation failed with exception (attempt %d/%d)",
                        article_attempts,
                        MAX_ARTICLE_ATTEMPTS,
                    )

        # Sleep before next check
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    main()
