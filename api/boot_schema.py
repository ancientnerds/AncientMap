# SPDX-License-Identifier: AGPL-3.0-only
"""The API's startup schema steps, and the retrying per-step transaction they run in.

Runs from ``api.main.lifespan`` on api AND api2 at every deploy, right after
``Base.metadata.create_all`` (which creates missing tables but never adds a column to an
existing one). Every step is a ``BootDDL`` (pipeline/utils/boot_ddl.py): a pg_catalog query
decides and the idempotent statement runs only when its object is missing. Until
2026-09-23 each of these 29 statements ran unconditionally, and 28 of them took their table
lock before looking - ACCESS EXCLUSIVE on unified_sites, card_stats, research_requests, ... -
on both instances, racing Lyra's own boot migrations. On an up-to-date schema a boot now
issues no DDL at all (tests/pipeline/test_boot_ddl.py).

unified_sites ALTERs normally live in pipeline/lyra/orchestrator.py's migrations; the three
here exist because the API needs the columns for /sites/all even when Lyra has not booted.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import partial

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from pipeline.utils.boot_ddl import (
    BootDDL,
    add_column,
    add_constraint,
    create_index,
    ensure,
    set_varchar_length,
)

logger = logging.getLogger(__name__)

# FK policy (2026-08-17): every FK onto unified_sites is SET NULL
# except the site-owned tables (unified_site_names,
# site_content_links, wiki_images, site_external_ids) and
# card_stats (regenerated derived data). The models said SET NULL
# for years; existing DBs kept CASCADE because create_all never
# alters constraints — the duplicate-merge audit would have
# cascaded into user data.
# A site-owned table whose site_id sits in its PRIMARY KEY cannot
# have NOT NULL dropped: site_external_ids crash-looped the API on
# deploy (2026-09-15) until it was listed here. Every new
# site-owned CASCADE table goes into this tuple AND into
# tests/api/test_fk_policy_exemptions.py.
_CASCADE_FKS_ONTO_SITES = """
    SELECT tc.table_name, tc.constraint_name, ccu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.referential_constraints rc
        ON rc.constraint_name = tc.constraint_name
    JOIN information_schema.key_column_usage ccu
        ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND rc.unique_constraint_name IN (
          SELECT constraint_name FROM information_schema.table_constraints
          WHERE table_name = 'unified_sites' AND constraint_type = 'PRIMARY KEY')
      AND rc.delete_rule = 'CASCADE'
      AND tc.table_name NOT IN (
          'unified_site_names', 'site_content_links', 'wiki_images', 'card_stats',
          'site_external_ids')
"""

# The rewrite loops over exactly the rows the check counts: one query, two uses, so the check
# cannot pass while the loop would still find work (or the other way round).
FK_POLICY = BootDDL(
    label="FK policy: ON DELETE SET NULL onto unified_sites",
    ddl=(
        "DO $$ DECLARE r RECORD; BEGIN\n"
        "    FOR r IN " + _CASCADE_FKS_ONTO_SITES + "\n"
        "    LOOP\n"
        "        EXECUTE format('ALTER TABLE %I ALTER COLUMN %I DROP NOT NULL',\n"
        "                       r.table_name, r.column_name);\n"
        "        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.table_name, r.constraint_name);\n"
        "        EXECUTE format(\n"
        "            'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) '\n"
        "            'REFERENCES unified_sites(id) ON DELETE SET NULL',\n"
        "            r.table_name, r.constraint_name, r.column_name);\n"
        "    END LOOP;\n"
        "END $$"
    ),
    satisfied_sql="SELECT NOT EXISTS (" + _CASCADE_FKS_ONTO_SITES + ")",
)

#: Columns that models define but create_all won't add to existing tables, in boot order.
API_BOOT_SCHEMA: tuple[BootDDL, ...] = (
    add_constraint(
        "discord_users",
        "credits_non_negative",
        "CHECK (credits >= 0)",
        duplicate=("duplicate_object",),
    ),
    add_column("expedition_progress", "last_stage_played_at", "TIMESTAMP"),
    add_column("card_player_stats", "feature_flags", "JSONB DEFAULT '{}'"),
    add_column("card_player_stats", "daily_streak", "INTEGER NOT NULL DEFAULT 0"),
    add_column("card_player_stats", "last_daily", "TIMESTAMP"),
    # Ensure unified_sites columns exist (normally added by orchestrator, but API needs them for /sites/all)
    add_column("unified_sites", "edited_by", "VARCHAR(20) NOT NULL DEFAULT 'initial'"),
    add_column("unified_sites", "updated_at", "TIMESTAMP"),
    add_column("unified_sites", "last_audited", "TIMESTAMP"),
    # Ensure card_stats enrichment columns exist (model defines them but create_all won't add to existing table).
    # Keep this block in CardStats declaration order — a missing entry here
    # breaks every query that loads the entity, not just the new column.
    add_column("card_stats", "wikidata_qid", "VARCHAR(20)"),
    add_column("card_stats", "confidence_score", "FLOAT"),
    add_column("card_stats", "source_language", "VARCHAR(10)"),
    add_column("card_stats", "heritage_designation", "TEXT"),
    add_column("card_stats", "inception_year", "INTEGER"),
    add_column("card_stats", "best_wiki_url", "VARCHAR(500)"),
    add_column("card_stats", "commons_image", "VARCHAR(500)"),
    # Ensure db_snapshots has source_id column (added after initial table creation)
    add_column("db_snapshots", "source_id", "VARCHAR(50)"),
    # Widen grant_period from varchar(7) to varchar(10) — "one_time" sentinel is 8 chars
    set_varchar_length("credit_grants", "grant_period", 10),
    # Ensure site_content_links unique constraint exists (needed for ON CONFLICT upsert).
    # duplicate_table: ADD CONSTRAINT UNIQUE raises 42P07 for the backing
    # index when the constraint already exists, not duplicate_object
    add_constraint(
        "site_content_links",
        "uq_content_link",
        "UNIQUE (site_id, content_source, content_id)",
        duplicate=("duplicate_object", "duplicate_table"),
    ),
    # Ensure token_usage_logs has web_search_requests column
    add_column("token_usage_logs", "web_search_requests", "INTEGER NOT NULL DEFAULT 0"),
    # (Orphan-citation strip moved to migrations/0011 — it scanned
    # 750K rows on every boot and was silently skipped on timeout.)
    # Theo research: approval tracking, debug log, LLM call count
    add_column("research_requests", "approved_by", "VARCHAR(100)"),
    add_column("research_requests", "approved_at", "TIMESTAMP"),
    add_column("research_requests", "debug_log", "JSONB"),
    add_column("research_requests", "llm_calls", "INTEGER DEFAULT 0"),
    # Theo batch pacing: batch flag + actual run-start timestamp (created_at
    # is queue-insert time, useless for start-to-start pacing)
    add_column("research_requests", "is_batch", "BOOLEAN NOT NULL DEFAULT FALSE"),
    add_column("research_requests", "started_at", "TIMESTAMP"),
    # Thinking layer: curator-facing question + outcome on research_nodes (2026-08-04)
    add_column("research_nodes", "question", "TEXT"),
    add_column("research_nodes", "outcome", "VARCHAR(20)"),
    create_index("uq_knowledge_claim_norm_text", "knowledge_claims", "(norm_text)", unique=True),
    FK_POLICY,
)


def is_contention_error(exc: Exception) -> bool:
    """True only for lock (55P03) / statement (57014) timeouts and
    deadlocks (40P01).

    Those are EXPECTED when the Lyra orchestrator migrates the same
    tables during a simultaneous boot and may be skipped after the
    retries below (the next boot completes them). Every other error
    used to be swallowed as "lock contention" too, leaving silent
    schema drift while the API started healthy (audit 2026-08-05,
    M5) — now it aborts startup so the deploy health check fails
    loudly.
    """
    pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
    return pgcode in ("55P03", "57014", "40P01")


def run_boot_step(
    engine: Engine, work: Callable[[Connection], object], label: str = "Migration"
) -> None:
    """``work(conn)`` in its own transaction, retried on contention.

    api and lyra boot together on deploys that rebuild both, and both
    migrate unified_sites — a deadlock (40P01) kills whichever boot
    PostgreSQL picks as victim. Every step here is idempotent (a schema
    step re-reads the catalog on each attempt), so wait out the other
    booter and retry before giving up.
    """
    for attempt in (1, 2, 3):
        try:
            with engine.begin() as conn:
                # LOCAL: scoped to this transaction. Plain SET stuck
                # to the pooled session, so every later request on
                # that connection inherited the 5 s lock limit
                # (seen as 500s during the 2026-09-17 Lyra crash loop).
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("SET LOCAL statement_timeout = '30s'"))
                work(conn)
            return
        except Exception as mig_err:
            if not is_contention_error(mig_err):
                logger.error(f"[STARTUP] {label} FAILED (aborting startup): {mig_err}")
                raise
            if attempt < 3:
                logger.warning(
                    f"[STARTUP] {label} hit lock contention "
                    f"(attempt {attempt}/3) — retrying in {2 * attempt}s"
                )
                time.sleep(2 * attempt)
                continue
            logger.warning(
                f"[STARTUP] {label} skipped after 3 contention retries "
                f"(next boot completes it): {mig_err}"
            )


def run_api_boot_schema(engine: Engine) -> None:
    """Every ``API_BOOT_SCHEMA`` step, each in its own retried transaction."""
    for step in API_BOOT_SCHEMA:
        run_boot_step(engine, partial(ensure, step=step), label=f"Migration ({step.label})")
