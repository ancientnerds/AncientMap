#!/usr/bin/env python3
"""Unified Database Audit & Enrichment Orchestrator.

The "one button" entry point for auditing and enriching the Ancient Nerds database.
Currently scoped to ancient_nerds source only (lyra/community to be added later).

Flow:
  sync    → Fetch latest site data from API (GeoJSON) into local DB
  Waves 0-3 → Audit & enrich locally
  package → Export cleaned data for upload via db.html
  upload  → (Manual) Open db.html, upload the package, auto-snapshot created

Waves:
  0: Mechanical fixes + country backfill (deterministic, no LLM)
  1: Wikidata enrichment pipeline + card_stats import (HTTP, no LLM)
  Apply: Write enrichment data back to unified_sites (JSON → DB)
  2: Agent verification & gap fill (prepare batches for Claude Code agents)
  3: Card descriptions (delegated to CARD_DESCRIPTIONS.md procedure)

Usage:
    python scripts/audit_enrich.py                          # Full run: sync + waves + package
    python scripts/audit_enrich.py --mode full              # Force re-audit everything
    python scripts/audit_enrich.py --phase sync             # Only: fetch API → local DB
    python scripts/audit_enrich.py --phase mechanical       # Only Wave 0
    python scripts/audit_enrich.py --phase enrich           # Only Wave 1
    python scripts/audit_enrich.py --phase apply            # Only: apply enrichment → unified_sites
    python scripts/audit_enrich.py --phase verify           # Only Wave 2 (prepare agent batches)
    python scripts/audit_enrich.py --phase agents           # Show Wave 2 batch status + handoff instructions
    python scripts/audit_enrich.py --phase merge --dry-run  # Preview merge changes without writing DB
    python scripts/audit_enrich.py --phase merge            # Merge agent results → DB
    python scripts/audit_enrich.py --phase package          # Only: export cleaned DB for db.html upload
    python scripts/audit_enrich.py --phase export           # Only: re-export static JSON
    python scripts/audit_enrich.py --phase web-links          # Prepare batches for reference link discovery
    python scripts/audit_enrich.py --phase web-links-merge    # Merge discovered reference links → DB
    python scripts/audit_enrich.py --phase deep-research      # Prepare batches for multi-source description rewrite
    python scripts/audit_enrich.py --phase deep-research-merge # Merge deep-research results → DB
    python scripts/audit_enrich.py --limit 3                # Test with 3 random sites
    python scripts/audit_enrich.py --api-url https://ancientnerds.com  # Use production API
"""

import argparse
import contextlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from pipeline.database import engine
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type
from pipeline.site_images.wikimedia_fallback import get_commons_thumb_url
from pipeline.utils.country_lookup import lookup_country
from pipeline.utils.text import categorize_period

OUTPUT_DIR = Path(__file__).parent.parent / "output"
BATCH_DIR = OUTPUT_DIR / "audit_batches"
WEBLINK_DIR = OUTPUT_DIR / "weblink_batches"
DEEP_RESEARCH_DIR = OUTPUT_DIR / "deep_research_batches"
CITED_DESC_DIR = OUTPUT_DIR / "cited_description_batches"
VERIFICATION_DIR = OUTPUT_DIR / "verification_batches"

ALL_SOURCE_IDS = ["ancient_nerds"]
DEFAULT_API_URL = "http://localhost:5175"

# Re-audit sites older than 90 days
AUDIT_FRESHNESS_DAYS = 90


# =============================================================================
# Phase: Sync from Production API
# =============================================================================


def _fetch_geojson(api_url: str, source_id: str) -> list[dict]:
    """Fetch sites from /api/v1/sites.geojson and return as flat dicts."""
    url = f"{api_url}/api/v1/sites.geojson"
    print(f"  GET {url}?source={source_id} ...", flush=True)

    resp = httpx.get(
        url,
        params={"source": source_id, "limit": 50000},
        timeout=120,
        headers={"User-Agent": "AncientNerdsAudit/1.0"},
    )
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    sites = []
    for feat in features:
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        sites.append({
            "site_id": props.get("id"),
            "source_id": props.get("source_id", source_id),
            "name": props.get("name"),
            "lon": coords[0],
            "lat": coords[1],
            "site_type": props.get("site_type"),
            "period_start": props.get("period_start"),
            "period_name": props.get("period_name"),
            "country": props.get("country"),
            "description": props.get("description"),
            "source_url": props.get("source_url"),
            "thumbnail_url": props.get("thumbnail_url"),
        })
    return sites


def sync_from_production(api_url: str, source_ids: list[str]) -> dict:
    """Fetch latest site data from production API and upsert into local DB.

    This ensures the local DB reflects manual edits made via db.html on production
    before running the audit. Without this step, the audit could overwrite
    production changes that only exist in the remote database.

    Uses a temp table + batch JOIN for speed (~5s for 5000 sites instead of minutes).
    """
    print(f"\n[SYNC] Fetching from {api_url} ...", flush=True)

    all_sites = []
    for source_id in source_ids:
        sites = _fetch_geojson(api_url, source_id)
        print(f"  {source_id}: {len(sites)} sites", flush=True)
        all_sites.extend(sites)

    if not all_sites:
        print("  WARNING: API returned 0 sites. Skipping sync.", flush=True)
        return {"synced": 0, "skipped": 0}

    # Filter out sites without IDs
    valid = [s for s in all_sites if s.get("site_id")]
    skipped = len(all_sites) - len(valid)

    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = '300s'"))
        # Create temp table
        conn.execute(text("""
            CREATE TEMP TABLE _sync_incoming (
                site_id TEXT PRIMARY KEY,
                source_id TEXT,
                name TEXT,
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION,
                site_type TEXT,
                period_start INTEGER,
                period_name TEXT,
                country TEXT,
                description TEXT,
                source_url TEXT,
                thumbnail_url TEXT
            ) ON COMMIT DROP
        """))

        # Batch insert into temp table (chunks of 500)
        for i in range(0, len(valid), 500):
            chunk = valid[i:i + 500]
            values_parts = []
            params = {}
            for j, site in enumerate(chunk):
                prefix = f"s{j}"
                values_parts.append(
                    f"(:{prefix}_id, :{prefix}_src, :{prefix}_n, :{prefix}_la, :{prefix}_lo, "
                    f":{prefix}_t, :{prefix}_p, :{prefix}_pn, :{prefix}_c, "
                    f":{prefix}_d, :{prefix}_u, :{prefix}_th)"
                )
                params[f"{prefix}_id"] = site["site_id"]
                params[f"{prefix}_src"] = site.get("source_id")
                params[f"{prefix}_n"] = site.get("name")
                params[f"{prefix}_la"] = site.get("lat")
                params[f"{prefix}_lo"] = site.get("lon")
                params[f"{prefix}_t"] = site.get("site_type")
                params[f"{prefix}_p"] = site.get("period_start")
                params[f"{prefix}_pn"] = site.get("period_name")
                params[f"{prefix}_c"] = site.get("country")
                params[f"{prefix}_d"] = site.get("description")
                params[f"{prefix}_u"] = site.get("source_url")
                params[f"{prefix}_th"] = site.get("thumbnail_url")

            conn.execute(
                text(f"INSERT INTO _sync_incoming VALUES {', '.join(values_parts)}"),
                params,
            )

        print(f"  Loaded {len(valid)} sites into temp table", flush=True)

        # Batch UPDATE existing sites from temp table
        result_upd = conn.execute(text("""
            UPDATE unified_sites us SET
                name = si.name,
                lat = si.lat,
                lon = si.lon,
                site_type = si.site_type,
                period_start = si.period_start,
                period_name = si.period_name,
                country = si.country,
                description = si.description,
                source_url = si.source_url,
                thumbnail_url = si.thumbnail_url,
                updated_at = NOW()
            FROM _sync_incoming si
            WHERE us.id::text = si.site_id
        """))
        updated = result_upd.rowcount

        # Batch INSERT new sites (exist on production but not locally)
        result_ins = conn.execute(text("""
            INSERT INTO unified_sites (
                id, source_id, name, lat, lon, geom,
                site_type, period_start, period_name,
                country, description, source_url, thumbnail_url,
                created_at, updated_at
            )
            SELECT
                si.site_id::uuid, si.source_id, si.name, si.lat, si.lon,
                ST_SetSRID(ST_MakePoint(si.lon, si.lat), 4326),
                si.site_type, si.period_start, si.period_name,
                si.country, si.description, si.source_url, si.thumbnail_url,
                NOW(), NOW()
            FROM _sync_incoming si
            LEFT JOIN unified_sites us ON us.id::text = si.site_id
            WHERE us.id IS NULL
        """))
        inserted = result_ins.rowcount

        conn.commit()

    print(f"[SYNC] Complete: {updated} updated, {inserted} inserted, {skipped} skipped", flush=True)
    return {"updated": updated, "inserted": inserted, "skipped": skipped}


# =============================================================================
# Phase: Fetch Candidates
# =============================================================================

def fetch_audit_candidates(source_ids: list[str], mode: str, limit: int | None = None) -> list[dict]:
    """Query unified_sites for audit candidates.

    In default mode, skips sites audited within the last 90 days.
    In full mode, returns all sites for the given sources.
    When limit is set, picks N random sites (ignores audit freshness).
    """
    placeholders = ", ".join(f":src_{i}" for i in range(len(source_ids)))
    params = {f"src_{i}": sid for i, sid in enumerate(source_ids)}

    date_filter = ""
    if limit is None and mode != "full":
        date_filter = f"AND (last_audited IS NULL OR last_audited < NOW() - INTERVAL '{AUDIT_FRESHNESS_DAYS} days')"

    order_clause = "ORDER BY RANDOM()" if limit else "ORDER BY source_id, name"
    limit_clause = f"LIMIT {int(limit)}" if limit else ""

    query = f"""
        SELECT
            id::text AS site_id,
            source_id,
            name,
            lat, lon,
            site_type,
            period_start,
            period_end,
            period_name,
            country,
            description,
            source_url,
            edited_by,
            last_audited
        FROM unified_sites
        WHERE source_id IN ({placeholders})
        {date_filter}
        {order_clause}
        {limit_clause}
    """

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    sites = []
    for row in rows:
        sites.append({
            "site_id": row.site_id,
            "source_id": row.source_id,
            "name": row.name,
            "lat": row.lat,
            "lon": row.lon,
            "site_type": row.site_type,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "period_name": row.period_name,
            "country": row.country,
            "description": row.description,
            "source_url": row.source_url,
            "edited_by": row.edited_by,
            "last_audited": row.last_audited.isoformat() if row.last_audited else None,
        })

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "audit_sites.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sites, f, indent=2, ensure_ascii=False)

    by_source = {}
    for s in sites:
        by_source.setdefault(s["source_id"], 0)
        by_source[s["source_id"]] += 1

    print(f"[AUDIT] Fetched {len(sites)} candidates ({mode} mode)", flush=True)
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}", flush=True)

    return sites


# =============================================================================
# Wave 0: Mechanical Fixes
# =============================================================================

def run_mechanical_fixes(sites: list[dict]) -> dict:
    """Apply deterministic fixes: site_type normalization, period recomputation,
    raw_year parsing, compound capitalization.

    Returns stats dict.
    """
    # Phrases that indicate a purely modern institution with no archaeological value.
    # These use word-boundary matching (\m...\M) to avoid false positives like
    # "Huijazoo", "Zootzen", "Zook". Only sites with type Unknown/NULL/site are
    # flagged — specific types (heritage_site, temple, fortress) are left alone.
    SUSPECT_MODERN_PHRASES = [
        r"\mwildlife sanctuary\M",
        r"\mwildlife refuge\M",
        r"\msafari park\M",
        r"\mbotanical garden\M",
        r"\mtheme park\M",
        r"\mamusement park\M",
        r"\mwater park\M",
        r"\maquarium\M",
        r"\mplanetarium\M",
    ]

    stats = {
        "suspect_modern_flagged": 0,
        "site_type_normalized": 0,
        "period_name_recomputed": 0,
        "country_filled": 0,
        "total_sites": len(sites),
    }
    sql_statements = []

    def _sql_str(v: str) -> str:
        """Escape single quotes for SQL log (double them per SQL standard)."""
        return "'" + v.replace("'", "''") + "'"

    with engine.connect() as conn:
        # Extend timeout for bulk audit operations (default 30s is too short)
        conn.execute(text("SET statement_timeout = '300s'"))

        # --- Suspect modern flagging ---
        # Detect sites whose names match modern-institution phrases.
        # Only flags sites with vague types (Unknown, NULL, site) — specific
        # archaeological types are never overwritten.
        regex_pattern = "(" + "|".join(SUSPECT_MODERN_PHRASES) + ")"
        suspects = conn.execute(
            text("""
                SELECT id::text, name, site_type
                FROM unified_sites
                WHERE name ~* :pattern
                  AND site_type != 'suspect_modern'
                  AND (site_type IS NULL OR site_type IN ('Unknown', 'site'))
            """),
            {"pattern": regex_pattern},
        ).fetchall()

        for row in suspects:
            conn.execute(
                text("""
                    UPDATE unified_sites
                    SET site_type = 'suspect_modern', edited_by = 'audit_enrich'
                    WHERE id = :sid
                """),
                {"sid": row.id},
            )
            sql_statements.append(
                f"-- SUSPECT MODERN: {row.name} (was: {row.site_type})\n"
                f"UPDATE unified_sites SET site_type = 'suspect_modern' "
                f"WHERE id = '{row.id}' AND site_type = {_sql_str(row.site_type or 'NULL')};"
            )
        stats["suspect_modern_flagged"] = len(suspects)
        if suspects:
            print(f"  Suspect modern: {len(suspects)} sites flagged for review", flush=True)
            for row in suspects:
                print(f"    - {row.name} (was: {row.site_type})", flush=True)

        # --- Site type normalization ---
        # Fetch distinct raw site_types across all sources
        raw_types = conn.execute(text(
            "SELECT DISTINCT site_type FROM unified_sites WHERE site_type IS NOT NULL"
        )).fetchall()

        for (raw,) in raw_types:
            canonical = normalize_site_type(raw)
            if canonical != raw:
                stmt = (
                    f"UPDATE unified_sites SET site_type = {_sql_str(canonical)} "
                    f"WHERE site_type = {_sql_str(raw)};"
                )
                sql_statements.append(stmt)
                result = conn.execute(
                    text("UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw"),
                    {"canonical": canonical, "raw": raw},
                )
                stats["site_type_normalized"] += result.rowcount

        # --- Period name recomputation ---
        # For sites with period_start but mismatched period_name
        rows = conn.execute(text("""
            SELECT id::text AS site_id, period_start, period_name
            FROM unified_sites
            WHERE period_start IS NOT NULL
        """)).fetchall()

        for row in rows:
            expected = categorize_period(row.period_start)
            if expected and expected != row.period_name:
                stmt = (
                    f"UPDATE unified_sites SET period_name = {_sql_str(expected)} "
                    f"WHERE id = '{row.site_id}' "
                    f"AND (period_name IS NULL OR period_name = {_sql_str(row.period_name or '')});"
                )
                sql_statements.append(stmt)
                conn.execute(
                    text(
                        "UPDATE unified_sites SET period_name = :expected "
                        "WHERE id = :site_id "
                        "AND (period_name IS NULL OR period_name = :current)"
                    ),
                    {
                        "expected": expected,
                        "site_id": row.site_id,
                        "current": row.period_name,
                    },
                )
                stats["period_name_recomputed"] += 1

        # --- Country backfill from coordinates ---
        rows = conn.execute(text("""
            SELECT id::text AS site_id, lat, lon
            FROM unified_sites
            WHERE country IS NULL AND lat IS NOT NULL AND lon IS NOT NULL
        """)).fetchall()

        if rows:
            print(f"  Country backfill: checking {len(rows)} sites with NULL country...", flush=True)
        for row in rows:
            country = lookup_country(row.lat, row.lon)
            if country:
                conn.execute(
                    text("UPDATE unified_sites SET country = :country WHERE id = :sid"),
                    {"country": country, "sid": row.site_id},
                )
                sql_statements.append(
                    f"UPDATE unified_sites SET country = {_sql_str(country)} WHERE id = '{row.site_id}';"
                )
                stats["country_filled"] += 1

        conn.commit()

    # Write SQL log
    if sql_statements:
        sql_path = OUTPUT_DIR / "audit_mechanical_fixes.sql"
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write("-- Mechanical audit fixes generated by audit_enrich.py\n")
            f.write(f"-- Generated: {datetime.now(timezone.utc).isoformat()}\n\n")
            for stmt in sql_statements:
                f.write(stmt + "\n")
        print(f"  SQL log: {sql_path} ({len(sql_statements)} statements)", flush=True)

    print(f"[WAVE 0] Mechanical fixes complete:", flush=True)
    for key, val in stats.items():
        if key != "total_sites":
            print(f"  {key}: {val}", flush=True)

    return stats


# =============================================================================
# Wave 1: Wikidata Enrichment Pipeline
# =============================================================================

def run_enrichment_pipeline(card_sites: list[dict] | None = None) -> dict:
    """Run the existing enrichment scripts in sequence.

    Calls: export_card_sites.py → enrich_reconcile.py → enrich_fetch_claims.py
           → enrich_wiki_select.py

    When card_sites is provided (--limit mode), writes card_sites.json directly
    from the candidate list and passes a site ID filter to enrich_reconcile.py.
    """
    project_root = Path(__file__).parent.parent
    site_filter_path = OUTPUT_DIR / "audit_site_filter.json"

    # In --limit mode, write card_sites.json and filter file directly
    if card_sites is not None:
        card_sites_path = OUTPUT_DIR / "card_sites.json"
        card_sites_data = [
            {
                "site_id": s["site_id"],
                "name": s["name"],
                "period_name": s.get("period_name"),
                "period_start": s.get("period_start"),
                "site_type": s.get("site_type"),
                "country": s.get("country"),
                "description": s.get("description"),
            }
            for s in card_sites
        ]
        with open(card_sites_path, "w", encoding="utf-8") as f:
            json.dump(card_sites_data, f, indent=2, ensure_ascii=False)
        print(f"  Wrote {len(card_sites_data)} sites to {card_sites_path}", flush=True)

        site_ids = [s["site_id"] for s in card_sites]
        with open(site_filter_path, "w", encoding="utf-8") as f:
            json.dump(site_ids, f)
        print(f"  Wrote site filter ({len(site_ids)} IDs) to {site_filter_path}", flush=True)

    reconcile_cmd = [sys.executable, "scripts/enrich_reconcile.py"]
    if card_sites is not None:
        reconcile_cmd += ["--site-ids-file", str(site_filter_path)]

    scripts = [
        ("Reconcile QIDs", reconcile_cmd),
        ("Fetch claims", [sys.executable, "scripts/enrich_fetch_claims.py"]),
        ("Wiki selection", [sys.executable, "scripts/enrich_wiki_select.py"]),
        ("Import to card_stats", [sys.executable, "scripts/enrich_import.py"]),
    ]
    # In normal mode, export_card_sites runs first
    if card_sites is None:
        scripts.insert(0, ("Export sites", [sys.executable, "scripts/export_card_sites.py"]))

    stats = {}

    for label, cmd in scripts:
        print(f"\n[WAVE 1] {label}...", flush=True)
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR: {label} failed (exit code {result.returncode})", flush=True)
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", flush=True)
            stats[label] = "FAILED"
        else:
            stats[label] = "OK"
            # Print last few lines of output
            lines = result.stdout.strip().split("\n")
            for line in lines[-3:]:
                print(f"  {line}", flush=True)

    # Load enrichment stats
    for fname in ["enrichment_qids.json", "enrichment_claims.json", "enrichment_wiki.json"]:
        fpath = OUTPUT_DIR / fname
        if fpath.exists():
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            if "stats" in data:
                stats[fname] = data["stats"]

    print(f"\n[WAVE 1] Enrichment pipeline complete", flush=True)
    return stats


# =============================================================================
# Apply Enrichment to unified_sites
# =============================================================================


def apply_enrichment(overwrite: bool = False) -> dict:
    """Apply Wikidata enrichment data back to unified_sites.

    Reads enrichment JSONs produced by Wave 1 and fills NULL fields.
    Only uses high-confidence matches (>= 0.8).
    When overwrite=True, also replaces existing values (skipping no-ops).
    Sets edited_by = 'audit_enrich' for tracking.
    """
    MIN_CONFIDENCE = 0.8

    # Load enrichment JSONs
    qids: dict[str, dict] = {}
    claims: dict[str, dict] = {}
    wiki: dict[str, dict] = {}

    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    if qids_path.exists():
        with open(qids_path, encoding="utf-8") as f:
            qids = json.load(f).get("matches", {})

    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            claims = json.load(f).get("claims", {})

    wiki_path = OUTPUT_DIR / "enrichment_wiki.json"
    if wiki_path.exists():
        with open(wiki_path, encoding="utf-8") as f:
            wiki = json.load(f).get("articles", {})

    if not qids:
        print("[APPLY] No QID matches found. Skipping.", flush=True)
        return {"skipped": "no_qids"}

    # Filter to high-confidence matches
    hc_site_ids = {
        sid for sid, match in qids.items()
        if match.get("confidence", 0) >= MIN_CONFIDENCE
    }
    print(f"[APPLY] {len(hc_site_ids)} sites with confidence >= {MIN_CONFIDENCE}", flush=True)

    if overwrite:
        print(f"[APPLY] Overwrite mode: will verify + correct existing values", flush=True)

    stats = {
        "period_start_filled": 0,
        "period_start_overwritten": 0,
        "period_name_filled": 0,
        "period_name_overwritten": 0,
        "thumbnail_url_filled": 0,
        "thumbnail_url_overwritten": 0,
        "source_url_filled": 0,
        "source_url_overwritten": 0,
        "source_url_fragment_upgraded": 0,
        "description_filled": 0,
        "description_overwritten": 0,
        "country_filled": 0,
        "country_overwritten": 0,
    }
    change_log: list[dict] = []

    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = '300s'"))
        for site_id in hc_site_ids:
            # Fetch current values for this site
            row = conn.execute(
                text("""
                    SELECT period_start, period_name, thumbnail_url,
                           source_url, description, country
                    FROM unified_sites WHERE id = :sid
                """),
                {"sid": site_id},
            ).fetchone()

            if not row:
                continue

            updates: dict[str, object] = {}
            site_claims = claims.get(site_id, {})
            site_wiki = wiki.get(site_id, {})

            # period_start from P571 inception
            if site_claims.get("inception") is not None and (row.period_start is None or overwrite):
                new_val = site_claims["inception"]
                old_val = row.period_start
                if old_val != new_val:
                    updates["period_start"] = new_val
                    stat_key = "period_start_overwritten" if old_val is not None else "period_start_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "period_start",
                        "old": old_val,
                        "new": new_val,
                        "source": "wikidata_P571",
                    })
                    stats[stat_key] += 1

            # period_name recomputation (after period_start fill)
            effective_period_start = updates.get("period_start", row.period_start)
            if effective_period_start is not None and (row.period_name is None or overwrite):
                new_period_name = categorize_period(effective_period_start)
                if new_period_name and new_period_name != row.period_name:
                    updates["period_name"] = new_period_name
                    stat_key = "period_name_overwritten" if row.period_name is not None else "period_name_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "period_name",
                        "old": row.period_name,
                        "new": new_period_name,
                        "source": "computed_from_period_start",
                    })
                    stats[stat_key] += 1

            # thumbnail_url from P18 commons_image
            if site_claims.get("commons_image") and (row.thumbnail_url is None or overwrite):
                thumb_url = get_commons_thumb_url(site_claims["commons_image"], width=400)
                if thumb_url != row.thumbnail_url:
                    updates["thumbnail_url"] = thumb_url
                    stat_key = "thumbnail_url_overwritten" if row.thumbnail_url is not None else "thumbnail_url_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "thumbnail_url",
                        "old": row.thumbnail_url,
                        "new": thumb_url,
                        "source": "wikidata_P18",
                    })
                    stats[stat_key] += 1

            # source_url from wiki article URL
            # Also upgrade fragment URLs (#section) to dedicated articles
            existing_is_fragment = row.source_url and "#" in row.source_url
            new_is_dedicated = site_wiki.get("url") and "#" not in site_wiki["url"]
            if site_wiki.get("url") and (
                row.source_url is None
                or overwrite
                or (existing_is_fragment and new_is_dedicated)
            ):
                new_url = site_wiki["url"]
                if new_url != row.source_url:
                    updates["source_url"] = new_url
                    if existing_is_fragment and new_is_dedicated:
                        stat_key = "source_url_fragment_upgraded"
                    elif row.source_url is not None:
                        stat_key = "source_url_overwritten"
                    else:
                        stat_key = "source_url_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "source_url",
                        "old": row.source_url,
                        "new": new_url,
                        "source": "wikipedia_article",
                    })
                    stats[stat_key] += 1

            # description from Wikipedia extract (first 500 chars)
            if site_wiki.get("extract") and (row.description is None or overwrite):
                desc = site_wiki["extract"][:500]
                if desc != row.description:
                    updates["description"] = desc
                    stat_key = "description_overwritten" if row.description is not None else "description_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "description",
                        "old": row.description,
                        "new": desc,
                        "source": "wikipedia_extract",
                    })
                    stats[stat_key] += 1

            # country from P17 (fallback when reverse geocoding missed it)
            if site_claims.get("country") and (row.country is None or overwrite):
                new_country = site_claims["country"]
                if new_country != row.country:
                    updates["country"] = new_country
                    stat_key = "country_overwritten" if row.country is not None else "country_filled"
                    change_log.append({
                        "site_id": site_id,
                        "field": "country",
                        "old": row.country,
                        "new": new_country,
                        "source": "wikidata_P17",
                    })
                    stats[stat_key] += 1

            if not updates:
                continue

            # Build UPDATE query
            updates["edited_by"] = "audit_enrich"
            set_parts = []
            params: dict[str, object] = {"sid": site_id}
            for col, val in updates.items():
                set_parts.append(f"{col} = :{col}")
                params[col] = val

            conn.execute(
                text(f"UPDATE unified_sites SET {', '.join(set_parts)} WHERE id = :sid"),
                params,
            )

        conn.commit()

    # Write change log
    log_path = OUTPUT_DIR / "audit_apply_log.json"
    log_data = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "min_confidence": MIN_CONFIDENCE,
        "overwrite": overwrite,
        "stats": stats,
        "changes": change_log,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

    print(f"[APPLY] Enrichment applied:", flush=True)
    for key, val in stats.items():
        if val > 0:
            print(f"  {key}: {val}", flush=True)
    print(f"  Change log: {log_path} ({len(change_log)} changes)", flush=True)

    return stats


# =============================================================================
# Wave 2: Prepare Agent Batches
# =============================================================================

def prepare_agent_batches(sites: list[dict]) -> dict:
    """Identify sites needing research and split into agent batches.

    Loads enrichment data to find gaps/discrepancies, then creates
    batch input files for Claude Code agents.
    """
    # Load enrichment data
    qids = {}
    claims = {}
    wiki = {}

    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    if qids_path.exists():
        with open(qids_path, encoding="utf-8") as f:
            qids = json.load(f).get("matches", {})

    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            claims = json.load(f).get("claims", {})

    wiki_path = OUTPUT_DIR / "enrichment_wiki.json"
    if wiki_path.exists():
        with open(wiki_path, encoding="utf-8") as f:
            wiki = json.load(f).get("articles", {})

    # Museum-like types exempt from P1 suspect-modern check
    MUSEUM_TYPES = {"museum", "geological interest"}

    # Identify sites needing research
    needs_research = []
    for site in sites:
        sid = site["site_id"]
        issues = []

        # Missing period_start and no Wikidata inception
        claim = claims.get(sid, {})
        if site["period_start"] is None:
            if claim.get("inception") is not None:
                issues.append(
                    f"period_start is NULL — enrichment says {claim['inception']}, verify"
                )
            else:
                issues.append("period_start is NULL — no enrichment data, needs research")

        # P1: Suspiciously modern period_start on non-museum sites
        st = site.get("site_type") or ""
        if (
            site["period_start"] is not None
            and site["period_start"] > 1500
            and st.lower() not in MUSEUM_TYPES
            and "museum" not in st.lower()
        ):
            issues.append(
                f"period_start={site['period_start']} — suspiciously modern for "
                f"a {st or 'unknown type'}, verify not a renovation/discovery date"
            )

        # Low-confidence Wikidata match excluded from auto-apply
        qid_info = qids.get(sid, {})
        if qid_info and qid_info.get("confidence", 1.0) < 0.8:
            issues.append(
                f"Wikidata match {qid_info.get('qid', '?')} at confidence "
                f"{qid_info.get('confidence', 0):.2f}, needs human verification"
            )

        # No Wikidata match at all
        if sid not in qids:
            issues.append("No Wikidata match — needs manual identification")

        # Missing country
        if not site["country"]:
            issues.append("country is NULL — needs geo-lookup or research")

        # Missing site_type
        if not st or st in ("unknown", "Unknown"):
            issues.append("site_type is unknown — needs classification")

        # Description quality: empty or very short after Wave 1
        desc = site.get("description") or ""
        wiki_extract = wiki.get(sid, {}).get("extract", "")
        if len(desc) < 20 and not wiki_extract:
            issues.append("No description and no wiki extract — needs research for context")

        # Source URL quality
        src_url = site.get("source_url") or ""
        if not src_url:
            issues.append("source_url is missing — find authoritative reference")
        elif "#" in src_url:
            issues.append(
                "source_url is a fragment link (#section) — find dedicated article"
            )

        # Thumbnail URL missing and no Wikidata P18
        if not site.get("thumbnail_url") and not claim.get("commons_image"):
            issues.append("thumbnail_url missing and no Wikidata P18 — find representative image")

        if issues:
            entry = dict(site)
            entry["enrichment"] = {
                "qid": qids.get(sid, {}).get("qid"),
                "inception": claim.get("inception"),
                "heritage": claim.get("heritage"),
            }
            entry["wiki_extract"] = wiki.get(sid, {}).get("extract", "")
            entry["needs_fix"] = issues
            needs_research.append(entry)

    if not needs_research:
        print("[WAVE 2] No sites need research -- all data complete!", flush=True)
        return {"total_needing_research": 0, "batches": 0}

    # Split into batches of ~50
    batch_size = 50
    BATCH_DIR.mkdir(parents=True, exist_ok=True)

    batches = []
    for i in range(0, len(needs_research), batch_size):
        batch_num = f"{len(batches) + 1:03d}"
        batch_sites = needs_research[i:i + batch_size]
        batch = {
            "batch_id": batch_num,
            "sites": batch_sites,
        }
        batch_path = BATCH_DIR / f"batch_{batch_num}_input.json"
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)
        batches.append(batch_num)

    # Write manifest
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "total_sites": len(needs_research),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "batches": {
            bid: {"status": "pending", "input": f"batch_{bid}_input.json"}
            for bid in batches
        },
    }
    manifest_path = BATCH_DIR / "merge_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    stats = {
        "total_needing_research": len(needs_research),
        "batches": len(batches),
        "batch_size": batch_size,
    }

    print(f"[WAVE 2] Prepared {len(batches)} batches ({len(needs_research)} sites)", flush=True)
    print(f"  Batch files: {BATCH_DIR}/batch_NNN_input.json", flush=True)
    print(f"  Manifest: {manifest_path}", flush=True)
    print(f"\n  Next: Launch agents to process each batch (see AUDIT_ENRICHMENT.md Step 3)", flush=True)

    return stats


def show_agent_status() -> None:
    """Show batch status and handoff instructions for Wave 2 agent research."""
    manifest_path = BATCH_DIR / "merge_manifest.json"
    if not manifest_path.exists():
        print("[AGENTS] No manifest found. Run --phase verify first to create batch files.", flush=True)
        return

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    batches = manifest.get("batches", {})
    total_sites = manifest.get("total_sites", 0)

    pending = [bid for bid, info in batches.items() if info.get("status") == "pending"]
    completed = [bid for bid, info in batches.items() if info.get("status") in ("merged", "completed")]
    has_results = []
    for bid in pending:
        result_path = BATCH_DIR / f"batch_{bid}_results.json"
        if result_path.exists():
            has_results.append(bid)

    print(f"  Total sites needing research: {total_sites}", flush=True)
    print(f"  Total batches: {len(batches)}", flush=True)
    print(f"  Pending: {len(pending)}", flush=True)
    print(f"  With results (ready to merge): {len(has_results)}", flush=True)
    print(f"  Already merged: {len(completed)}", flush=True)

    if pending:
        # Summarize issue types across pending batches
        issue_counts: dict[str, int] = {}
        for bid in pending:
            input_path = BATCH_DIR / f"batch_{bid}_input.json"
            if not input_path.exists():
                continue
            with open(input_path, encoding="utf-8") as f:
                batch = json.load(f)
            for site in batch.get("sites", []):
                for issue in site.get("needs_fix", []):
                    # Categorize by first phrase before " — "
                    key = issue.split(" — ")[0] if " — " in issue else issue[:40]
                    issue_counts[key] = issue_counts.get(key, 0) + 1

        if issue_counts:
            print("\n  Issue breakdown:", flush=True)
            for key, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
                print(f"    {count:>4}x  {key}", flush=True)

        if has_results:
            print(f"\n  {len(has_results)} batch(es) already have results (ready to merge).", flush=True)
            remaining = len(pending) - len(has_results)
            if remaining > 0:
                print(f"  {remaining} batch(es) still need agent research.", flush=True)

        print(f"\n  To run agent research, tell Claude Code:", flush=True)
        print(f'    "run Wave 2 agent research"', flush=True)
        print(f"\n  After agents complete, run:", flush=True)
        print(f"    python scripts/audit_enrich.py --phase merge --dry-run", flush=True)
        print(f"    python scripts/audit_enrich.py --phase merge", flush=True)
    else:
        print(f"\n  All batches merged. Nothing to do.", flush=True)


# =============================================================================
# Merge Agent Results (Post-Wave 2)
# =============================================================================

def merge_results(dry_run: bool = False) -> dict:
    """Read all batch result files and apply fixes to the database.

    Updates unified_sites and card_stats, sets last_audited timestamps.
    Validates site_type against CANONICAL_TYPES and auto-computes period_name.
    Only auto-applies high-confidence fixes; medium goes to manual review file.
    """
    manifest_path = BATCH_DIR / "merge_manifest.json"
    if not manifest_path.exists():
        print("[MERGE] No manifest found. Run --phase verify first.", flush=True)
        return {"error": "no manifest"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    ALLOWED_MERGE_FIELDS = frozenset({
        "name", "site_type", "period_start", "period_end", "period_name",
        "country", "description", "source_url", "thumbnail_url",
    })

    canonical_types_lower = {t.lower() for t in CANONICAL_TYPES}

    stats = {
        "auto_applied": 0, "verified": 0, "manual": 0, "skipped_low": 0,
        "deferred_medium": 0, "validation_warnings": 0, "batches_merged": 0,
    }
    manual_review_items: list[dict] = []

    if dry_run:
        print("[MERGE] DRY RUN -- no database writes will be made.\n", flush=True)

    ctx = engine.connect() if not dry_run else contextlib.nullcontext()
    with ctx as conn:
        for batch_id, batch_info in manifest.get("batches", {}).items():
            if batch_info.get("status") == "merged" and not dry_run:
                continue

            result_path = BATCH_DIR / f"batch_{batch_id}_results.json"
            if not result_path.exists():
                print(f"  Batch {batch_id}: no results file, skipping", flush=True)
                continue

            with open(result_path, encoding="utf-8") as f:
                results = json.load(f)

            sites_results = results.get("sites", {})
            for site_id, site_result in sites_results.items():
                status = site_result.get("status", "unknown")

                if status == "fixed":
                    raw_fixes = site_result.get("fixes", [])
                    applied_any = False

                    # Normalise fixes: accept both list-of-dicts and flat-dict formats
                    if isinstance(raw_fixes, dict):
                        # Flat dict format: {"field_name": value, ...}
                        fixes = []
                        for fld, val in raw_fixes.items():
                            fixes.append({
                                "field": fld,
                                "old": None,
                                "new": val,
                                "confidence": "high",
                            })
                    else:
                        fixes = raw_fixes

                    for fix in fixes:
                        if not isinstance(fix, dict) or "field" not in fix:
                            stats["validation_warnings"] += 1
                            continue
                        field = fix["field"]
                        confidence = fix.get("confidence", "low")

                        # Skip low-confidence fixes entirely
                        if confidence == "low":
                            stats["skipped_low"] += 1
                            continue

                        # Defer medium-confidence fixes to manual review
                        if confidence == "medium":
                            manual_review_items.append({
                                "site_id": site_id,
                                "fix": fix,
                                "batch_id": batch_id,
                                "reason": "medium confidence — needs human verification",
                            })
                            stats["deferred_medium"] += 1
                            continue

                        # Only high-confidence fixes reach here
                        if field not in ALLOWED_MERGE_FIELDS:
                            print(f"  WARNING: Skipping unknown field '{field}' for {site_id}", flush=True)
                            stats["validation_warnings"] += 1
                            continue

                        old_val = fix.get("old")
                        new_val = fix["new"]

                        # Validate site_type against CANONICAL_TYPES
                        if field == "site_type" and new_val:
                            normalized = normalize_site_type(new_val)
                            if normalized.lower() not in canonical_types_lower:
                                print(
                                    f"  WARNING: site_type '{new_val}' (normalized: '{normalized}') "
                                    f"not in CANONICAL_TYPES for {site_id}, skipping",
                                    flush=True,
                                )
                                stats["validation_warnings"] += 1
                                continue
                            new_val = normalized

                        # Auto-compute period_name when period_start is set
                        period_name_fix = None
                        if field == "period_start" and new_val is not None:
                            computed_name = categorize_period(int(new_val))
                            if computed_name:
                                period_name_fix = {
                                    "field": "period_name",
                                    "old": None,  # will use IS NULL or match
                                    "new": computed_name,
                                }

                        if dry_run:
                            print(
                                f"  [DRY] {site_id}: {field} = {old_val!r} -> {new_val!r} "
                                f"(confidence: {confidence})",
                                flush=True,
                            )
                            if period_name_fix:
                                print(
                                    f"  [DRY] {site_id}: period_name -> {period_name_fix['new']!r} (auto-computed)",
                                    flush=True,
                                )
                        else:
                            # Conditional WHERE: protect user edits
                            if old_val is None:
                                condition = f"{field} IS NULL"
                            else:
                                condition = f"{field} = :old_val"

                            update_sql = (
                                f"UPDATE unified_sites SET {field} = :new_val "
                                f"WHERE id = :site_id AND ({condition})"
                            )
                            params: dict = {"new_val": new_val, "site_id": site_id}
                            if old_val is not None:
                                params["old_val"] = old_val

                            conn.execute(text(update_sql), params)

                            # Apply auto-computed period_name (only if period_start was also updated)
                            if period_name_fix:
                                conn.execute(
                                    text(
                                        "UPDATE unified_sites SET period_name = :pname "
                                        "WHERE id = :site_id AND period_start = :ps_val"
                                    ),
                                    {
                                        "pname": period_name_fix["new"],
                                        "site_id": site_id,
                                        "ps_val": new_val,
                                    },
                                )

                        applied_any = True

                    if applied_any:
                        stats["auto_applied"] += 1

                elif status == "verified":
                    stats["verified"] += 1
                elif status == "manual":
                    manual_review_items.append({
                        "site_id": site_id,
                        "manual_notes": site_result.get("manual_notes", ""),
                        "batch_id": batch_id,
                        "reason": "agent flagged for manual review",
                    })
                    stats["manual"] += 1

                if not dry_run and conn:
                    # Update enrichment in card_stats if present
                    enrichment = site_result.get("enrichment", {})
                    if enrichment.get("confidence_score") is not None:
                        conn.execute(
                            text(
                                "UPDATE card_stats SET confidence_score = :score, last_enriched = NOW() "
                                "WHERE site_id = :site_id"
                            ),
                            {"score": enrichment["confidence_score"], "site_id": site_id},
                        )

                    # Card description (ancient_nerds only)
                    card_desc = site_result.get("card_description")
                    if card_desc:
                        conn.execute(
                            text(
                                "UPDATE card_stats SET card_description = :desc "
                                "WHERE site_id = :site_id AND (card_description IS NULL OR card_description = '')"
                            ),
                            {"desc": card_desc, "site_id": site_id},
                        )

                    # Mark as audited
                    conn.execute(
                        text("UPDATE unified_sites SET last_audited = NOW() WHERE id = :site_id"),
                        {"site_id": site_id},
                    )

            stats["batches_merged"] += 1
            if not dry_run:
                batch_info["status"] = "merged"

        if conn and not dry_run:
            conn.commit()

    # Update manifest (only if not dry run)
    if not dry_run:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Write manual review file if there are deferred items
    if manual_review_items:
        review_path = OUTPUT_DIR / "audit_manual_review.json"
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(manual_review_items, f, indent=2, ensure_ascii=False)
        print(f"\n  Manual review items: {review_path} ({len(manual_review_items)} items)", flush=True)

    prefix = "[MERGE DRY RUN]" if dry_run else "[MERGE]"
    print(f"{prefix} Complete:", flush=True)
    for key, val in stats.items():
        print(f"  {key}: {val}", flush=True)

    return stats


# =============================================================================
# Phase: Package for db.html Upload
# =============================================================================

def package_for_upload(source_ids: list[str], candidate_site_ids: set[str] | None = None) -> dict:
    """Export cleaned sites from local DB as GeoJSON files for upload via db.html.

    Creates one GeoJSON FeatureCollection per source. The user uploads the file
    in db.html which:
    1. Parses features and matches to existing sites by name
    2. Only updates the sites present in the file (like a GitHub diff)
    3. Auto-creates a snapshot before applying — always rollback-safe

    The GeoJSON format matches what db.html's exportGeoJSON() produces,
    so it round-trips cleanly.

    When candidate_site_ids is set (--limit mode), only exports those specific sites.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    stats = {}

    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = '300s'"))
        for source_id in source_ids:
            params = {"source_id": source_id}
            id_filter = ""
            if candidate_site_ids:
                id_placeholders = ", ".join(f":sid_{i}" for i in range(len(candidate_site_ids)))
                for i, sid in enumerate(candidate_site_ids):
                    params[f"sid_{i}"] = sid
                id_filter = f"AND id::text IN ({id_placeholders})"

            rows = conn.execute(
                text(f"""
                    SELECT
                        us.id::text AS site_id,
                        us.name, us.lat, us.lon,
                        us.site_type, us.period_name, us.period_start,
                        us.country, us.description, us.source_url, us.thumbnail_url,
                        cs.confidence_score,
                        cs.card_description
                    FROM unified_sites us
                    LEFT JOIN card_stats cs ON cs.site_id = us.id
                    WHERE us.source_id = :source_id
                    {id_filter}
                    ORDER BY name
                """),
                params,
            ).fetchall()

            features = []
            for row in rows:
                if row.lat is None or row.lon is None:
                    continue
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [row.lon, row.lat],
                    },
                    "properties": {
                        "id": row.site_id,
                        "name": row.name,
                        "source_id": source_id,
                        "site_type": row.site_type,
                        "period_start": row.period_start,
                        "period_name": row.period_name,
                        "country": row.country,
                        "description": row.description,
                        "source_url": row.source_url,
                        "thumbnail_url": row.thumbnail_url,
                        "confidence_score": row.confidence_score,
                        "card_description": row.card_description,
                    },
                }
                features.append(feature)

            geojson = {
                "type": "FeatureCollection",
                "metadata": {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "source_id": source_id,
                    "count": len(features),
                },
                "features": features,
            }

            out_path = OUTPUT_DIR / f"audit_upload_{source_id}.geojson"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(geojson, f, indent=2, ensure_ascii=False)

            stats[source_id] = len(features)
            print(f"  {source_id}: {len(features)} sites -> {out_path}", flush=True)

    print(f"\n[PACKAGE] Complete. Upload these files via db.html:", flush=True)
    for source_id in source_ids:
        out_path = OUTPUT_DIR / f"audit_upload_{source_id}.geojson"
        print(f"  {out_path}", flush=True)
    print("  Only sites in the file get updated (like a GitHub diff).", flush=True)
    print("  db.html auto-creates a snapshot before applying.", flush=True)

    return stats


# =============================================================================
# Export Static JSON
# =============================================================================

def export_static() -> None:
    """Re-export static JSON files after database changes."""
    print("\n[EXPORT] Re-exporting static JSON...", flush=True)
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.static_exporter", "--sites-only"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  ERROR: Export failed (exit code {result.returncode})", flush=True)
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}", flush=True)
    else:
        lines = result.stdout.strip().split("\n")
        for line in lines[-3:]:
            print(f"  {line}", flush=True)
        print("[EXPORT] Complete", flush=True)


# =============================================================================
# Web Reference Links (Claude Agent + WebSearch)
# =============================================================================

WEBLINK_AGENT_PROMPT = """\
You are discovering authoritative reference links for ancient/archaeological sites.

For each site below, use web search to find 1-5 high-quality reference links.

## SEARCH QUERY CONSTRUCTION

- Always search: "{site_name} {country} archaeological site"
- For ambiguous names, add: site_type, period, or region
  - Example: "Sun Temple Konark India ancient temple" not just "Sun Temple"
  - Example: "Troy Turkey ancient city Bronze Age" not just "Troy"
- If the site name is very common, include the period_name or period_start year
- Never search just the site name alone — always include country at minimum

## RELEVANCE VERIFICATION

Before including a link, verify the page is about THIS specific archaeological site:
- Check: does the page mention the correct country/region?
- Check: is the content about archaeology/history, not a video game/restaurant/modern building/hotel?
- Check: if the site name is shared with a modern entity (e.g. "Temple Bar" pub vs temple), does the page discuss the ancient/archaeological site?
- If the page is about a different site with the same name in a different country, EXCLUDE it
- If unsure, EXCLUDE the link — false positives are worse than missing links

## Priority order

1. Dedicated Wikipedia article (any language) — if the current source_url is a generic or fragment link
2. Official excavation/project pages (university digs, archaeological missions)
3. UNESCO World Heritage entries
4. Museum collection pages (Met, British Museum, Louvre online)
5. Quality articles from archaeology blogs, tourism sites, educational resources
6. Academic papers (open access preferred)

## EXCLUDE

- Generic travel booking sites (tripadvisor, booking.com, viator, getyourguide)
- Social media posts (facebook, instagram, twitter/x, tiktok)
- AI-generated content farms
- Paywalled content (unless JSTOR/academia with abstract)
- Pinterest, Reddit threads, Quora answers
- The site's existing source_url (already known)

For each link found, output this JSON structure:
{
  "url": "https://...",
  "title": "Page title as shown on the page",
  "domain": "example.com",
  "link_type": "article|academic|database|museum|unesco|government|project",
  "quality": "high|medium",
  "reason": "1-sentence why this is valuable"
}

Return your results as a JSON object mapping site_id to an array of links:
{
  "site_id_1": [ {link}, {link}, ... ],
  "site_id_2": [ {link}, ... ],
  ...
}

IMPORTANT: Only return high and medium quality links. Max 5 per site.
If you cannot find any good links for a site, return an empty array for it.
"""


def prepare_weblinks_batches(batch_size: int = 10, limit: int | None = None) -> dict:
    """Prepare batch input files for web reference link discovery agents.

    Queries sites and creates JSON batch files with site context for agents
    to search for authoritative reference links.
    """
    print("\n[WEB-LINKS] Preparing batches for reference link discovery...", flush=True)

    WEBLINK_DIR.mkdir(parents=True, exist_ok=True)

    with engine.connect() as conn:
        # Get sites that don't yet have reference links
        query = text("""
            SELECT
                us.id::text AS site_id,
                us.name,
                us.country,
                us.site_type,
                us.period_name,
                us.period_start,
                us.source_url,
                LEFT(us.description, 200) AS description_preview
            FROM unified_sites us
            WHERE us.source_id = 'ancient_nerds'
            AND us.id NOT IN (
                SELECT DISTINCT site_id FROM site_content_links
                WHERE content_type = 'reference'
            )
            ORDER BY us.name
        """)
        if limit:
            query = text(str(query) + f" LIMIT {limit}")

        rows = conn.execute(query).fetchall()

    if not rows:
        print("[WEB-LINKS] All sites already have reference links. Nothing to do.", flush=True)
        return {"total_sites": 0, "batches": 0}

    sites = [dict(row._mapping) for row in rows]

    # Split into batches
    batches = []
    for i in range(0, len(sites), batch_size):
        batch_num = f"{len(batches) + 1:03d}"
        batch_sites = sites[i : i + batch_size]
        batch = {
            "batch_id": batch_num,
            "prompt": WEBLINK_AGENT_PROMPT,
            "sites": batch_sites,
        }
        batch_path = WEBLINK_DIR / f"batch_{batch_num}_input.json"
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)
        batches.append(batch_num)

    # Write manifest
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "total_sites": len(sites),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "batches": {
            bid: {"status": "pending", "input": f"batch_{bid}_input.json"}
            for bid in batches
        },
    }
    manifest_path = WEBLINK_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[WEB-LINKS] Prepared {len(batches)} batches ({len(sites)} sites)", flush=True)
    print(f"  Batch files: {WEBLINK_DIR}/batch_NNN_input.json", flush=True)
    print(f"  Manifest: {manifest_path}", flush=True)
    print(f"\n  Next steps:", flush=True)
    print(f'    1. Launch agents to process each batch with WebSearch', flush=True)
    print(f"    2. Save results as batch_NNN_results.json", flush=True)
    print(f"    3. Run: python scripts/audit_enrich.py --phase web-links-merge", flush=True)

    return {"total_sites": len(sites), "batches": len(batches), "batch_size": batch_size}


def merge_weblinks(dry_run: bool = False) -> dict:
    """Merge web reference link results into site_content_links table.

    Reads batch result files, validates URLs, dedupes by domain per site,
    and INSERTs into site_content_links with content_type='reference'.
    """
    manifest_path = WEBLINK_DIR / "manifest.json"
    if not manifest_path.exists():
        print("[WEB-LINKS-MERGE] No manifest found. Run --phase web-links first.", flush=True)
        return {"error": "no manifest"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    stats = {"batches_processed": 0, "links_inserted": 0, "links_skipped": 0, "errors": 0}

    for batch_id, batch_info in manifest.get("batches", {}).items():
        if batch_info.get("status") == "merged":
            continue

        result_path = WEBLINK_DIR / f"batch_{batch_id}_results.json"
        if not result_path.exists():
            continue

        with open(result_path, encoding="utf-8") as f:
            results = json.load(f)

        # Handle both flat format {site_id: [links]} and wrapped {batch_id, sites: {site_id: [links]}}
        site_links = results.get("sites", results) if isinstance(results, dict) else results

        if dry_run:
            for site_id, links in site_links.items():
                for link in links:
                    print(
                        f"  [DRY-RUN] {site_id[:8]}.. → {link.get('domain', '?')}: {link.get('title', '?')[:60]}",
                        flush=True,
                    )
            stats["batches_processed"] += 1
            continue

        with engine.connect() as conn:
            for site_id, links in site_links.items():
                # Dedupe by domain — max 1 link per domain per site
                seen_domains: set[str] = set()
                for idx, link in enumerate(links[:5]):  # max 5 per site
                    url = link.get("url", "")
                    domain = link.get("domain", "")
                    title = link.get("title", "")
                    link_type = link.get("link_type", "article")
                    quality = link.get("quality", "medium")

                    if not url or not domain:
                        stats["links_skipped"] += 1
                        continue

                    if domain in seen_domains:
                        stats["links_skipped"] += 1
                        continue
                    seen_domains.add(domain)

                    # Compute relevance score from quality + position
                    base_score = 0.9 if quality == "high" else 0.7
                    relevance = round(base_score - (idx * 0.05), 2)

                    # Use domain+path-hash as content_id for uniqueness
                    content_id = f"{domain}:{hash(url) & 0xFFFFFFFF:08x}"

                    metadata = {
                        "domain": domain,
                        "link_type": link_type,
                        "language": "en",
                        "favicon_url": f"https://www.google.com/s2/favicons?domain={domain}&sz=16",
                    }
                    if link.get("reason"):
                        metadata["reason"] = link["reason"]

                    try:
                        conn.execute(
                            text("""
                                INSERT INTO site_content_links
                                    (site_id, content_type, content_source, content_id,
                                     title, content_url, relevance_score, link_metadata)
                                VALUES
                                    (:site_id, 'reference', 'web_search', :content_id,
                                     :title, :url, :relevance, CAST(:metadata AS jsonb))
                                ON CONFLICT (site_id, content_source, content_id) DO NOTHING
                            """),
                            {
                                "site_id": site_id,
                                "content_id": content_id,
                                "title": title[:500],
                                "url": url,
                                "relevance": relevance,
                                "metadata": json.dumps(metadata),
                            },
                        )
                        stats["links_inserted"] += 1
                    except Exception as e:
                        print(f"  [ERROR] {site_id[:8]}.. {domain}: {e}", flush=True)
                        stats["links_skipped"] += 1

            conn.commit()

        # Update manifest
        manifest["batches"][batch_id]["status"] = "merged"
        stats["batches_processed"] += 1

    # Save updated manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[WEB-LINKS-MERGE] Processed {stats['batches_processed']} batches", flush=True)
    print(f"  Links inserted: {stats['links_inserted']}", flush=True)
    print(f"  Links skipped (dupe/invalid): {stats['links_skipped']}", flush=True)

    return stats


# =============================================================================
# Deep Research: Multi-Source Description Rewrite (Claude Agent + WebFetch)
# =============================================================================

DEEP_RESEARCH_AGENT_PROMPT = """\
You are a research agent rewriting descriptions for ancient/archaeological sites using \
multiple sources. Your goal: transform single-source Wikipedia descriptions into comprehensive, \
multi-source descriptions grounded in real evidence.

## Your task

1. Read the batch input file: `output/deep_research_batches/batch_{BATCH_ID}_input.json`
2. For each site, WebFetch the top 2-3 reference URLs (prefer quality: "high")
3. Synthesize a NEW description and card_description from ALL available sources
4. Write results to: `output/deep_research_batches/batch_{BATCH_ID}_results.json`

## Description writing rules (500-1000 chars)

Structure:
- [Archaeological identity + dating] — [What the site IS and why it matters].
- [Key findings/features from specialist sources].
- [Cultural/historical significance].
- [Heritage status if applicable].

Rules:
- 500-1000 characters (hard limits)
- Ground EVERY fact in a source you can cite (Wikipedia extract, Wikidata claims, or a WebFetched URL)
- Include facts from multiple sources — don't just reword Wikipedia
- When reference URL fetches fail, lean on Wikipedia + Wikidata but mark confidence as "medium"
- No hedging language ("it is believed", "possibly", "some scholars think") unless citing a specific debate
- No generic filler ("important site", "rich history", "ancient ruins")
- Prefer concrete details: dimensions, artifact counts, inscription quotes, engineering feats
- Include heritage designations when available (UNESCO, Scheduled Monument, etc.)
- Use the site's period_start and period_name for dating context

## Card description style guide (max 200 chars)

Voice: Mix of documentary narrator and curiosity hook. National Geographic meets a trading card.

Structure:
- Start with an age/period anchor: "Built 9,600 BC", "3rd-century fortress"
- ONE outstanding fact: the single most remarkable thing
- Spark curiosity: leave the reader wanting more

When age/period is unknown:
- Skip the date opener entirely. Lead with the defining trait.
- Never write "Date unknown" or "Undated"

Rules:
- Max 200 characters (hard limit)
- Never mention the country (shown on the card already)
- Factually accurate — only facts from the sources provided
- No generic filler
- Prefer concrete details over vague adjectives

Examples:
- "Built 9,600 BC — 6,000 years before Stonehenge. Massive T-shaped pillars carved with lions, foxes, and vultures by people who hadn't yet invented pottery or farming." (170 chars)
- "Buried under 6 metres of volcanic ash when Vesuvius erupted in 79 AD. Bakeries still had loaves in the ovens. Election slogans and love notes survive on the walls." (167 chars)
- "Carved into rose-red sandstone cliffs around 300 BC by the Nabataeans. A lost trade capital that engineered flash-flood channels and cisterns to thrive in the desert." (168 chars)

Anti-examples (DON'T write like this):
- "An important archaeological site with rich history." (generic)
- "Located in Turkey, this ancient temple..." (mentions country)
- "Date unknown. A mysterious site in the desert." (says "date unknown")

## Anti-hallucination rules

1. Only include facts from: the wiki_extract, Wikidata enrichment claims, or WebFetched reference URLs
2. Every description MUST record a sources_used array listing domains/sources actually used
3. If ALL reference URL fetches fail → confidence = "medium", lean on Wikipedia + Wikidata only
4. Descriptions with < 2 sources at "high" confidence will be auto-rejected by merge

## Output format

Write this exact JSON structure to the results file:

```json
{
  "batch_id": "NNN",
  "sites": {
    "<site_id>": {
      "status": "improved|unchanged|failed",
      "description": {
        "text": "...",
        "char_count": 714,
        "sources_used": ["wikipedia", "historicengland.org.uk", "unesco.org"],
        "confidence": "high"
      },
      "card_description": {
        "text": "...",
        "char_count": 170
      },
      "corrections": [],
      "fetch_errors": ["https://example.com/dead-link — 404"]
    }
  },
  "stats": {
    "improved": 8,
    "unchanged": 1,
    "failed": 1
  }
}
```

Status values:
- "improved" — new description is better than the original (multi-source, more detail)
- "unchanged" — current description is already excellent or no new info found
- "failed" — could not produce a valid description (explain in fetch_errors)

corrections array (optional): If you discover factual errors during research, report them:
```json
{"field": "period_start", "old": 200, "new": -200, "confidence": "high", "evidence": "..."}
```

## Process each site

1. Read its current_description, wiki_extract, enrichment data, and reference_links
2. WebFetch the top 2-3 reference URLs (prefer quality: "high"). Use the WebFetch tool.
3. Extract key facts not in the Wikipedia description
4. Synthesize a new description combining all sources (500-1000 chars)
5. Write a new card_description (max 200 chars) following the style guide
6. Record sources_used and set confidence level

IMPORTANT: Every site_id from the input MUST appear in the output. Do not skip any site.

After processing all sites, count the stats and write the output file.
Print a one-line summary: "Batch {BATCH_ID} complete: X improved, Y unchanged, Z failed"
"""


def prepare_deep_research_batches(batch_size: int = 10, limit: int | None = None) -> dict:
    """Prepare batch input files for deep research description rewrite.

    Queries sites that have reference links, embeds all available context
    (description, wiki extract, enrichment data, reference links), and
    creates JSON batch files for agents to process.
    """
    print("\n[DEEP-RESEARCH] Preparing batches for multi-source description rewrite...", flush=True)

    DEEP_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # Load enrichment data files
    enrichment_qids = {}
    enrichment_claims = {}
    enrichment_wiki = {}

    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    wiki_path = OUTPUT_DIR / "enrichment_wiki.json"

    if qids_path.exists():
        with open(qids_path, encoding="utf-8") as f:
            enrichment_qids = json.load(f).get("matches", {})
        print(f"  Loaded {len(enrichment_qids)} QID matches", flush=True)

    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            enrichment_claims = json.load(f).get("claims", {})
        print(f"  Loaded {len(enrichment_claims)} claim records", flush=True)

    if wiki_path.exists():
        with open(wiki_path, encoding="utf-8") as f:
            enrichment_wiki = json.load(f).get("articles", {})
        print(f"  Loaded {len(enrichment_wiki)} wiki extracts", flush=True)

    with engine.connect() as conn:
        # Get sites that have reference links (Phase A complete) but haven't been deep-researched yet
        # Also include sites without reference links — they still benefit from Wikidata + Wikipedia rewrite
        query_str = """
            SELECT
                us.id::text AS site_id,
                us.name,
                us.country,
                us.site_type,
                us.period_name,
                us.period_start,
                us.source_url,
                us.description,
                us.raw_data
            FROM unified_sites us
            WHERE us.source_id = 'ancient_nerds'
            AND (us.raw_data IS NULL OR us.raw_data->>'description_pre_enrichment' IS NULL)
            ORDER BY us.name
        """
        if limit:
            query_str += f" LIMIT {limit}"

        rows = conn.execute(text(query_str)).fetchall()

        if not rows:
            print("[DEEP-RESEARCH] All sites already processed. Nothing to do.", flush=True)
            return {"total_sites": 0, "batches": 0}

        # Fetch reference links for all sites
        ref_rows = conn.execute(text("""
            SELECT
                site_id::text,
                title,
                content_url,
                link_metadata->>'domain' AS domain,
                link_metadata->>'link_type' AS link_type,
                CASE WHEN relevance_score >= 0.85 THEN 'high' ELSE 'medium' END AS quality
            FROM site_content_links
            WHERE content_type = 'reference'
            ORDER BY site_id, relevance_score DESC
        """)).fetchall()

        # Fetch all card descriptions in one query
        card_desc_rows = conn.execute(text("""
            SELECT site_id::text, card_description
            FROM card_stats
            WHERE site_id IN (
                SELECT id FROM unified_sites WHERE source_id = 'ancient_nerds'
            )
        """)).fetchall()

    # Group reference links by site_id
    ref_links_by_site: dict[str, list[dict]] = {}
    for ref in ref_rows:
        ref_map = dict(ref._mapping)
        sid = ref_map.pop("site_id")
        ref_links_by_site.setdefault(sid, []).append(ref_map)

    # Map card descriptions by site_id
    card_descs: dict[str, str] = {}
    for cd_row in card_desc_rows:
        card_descs[cd_row[0]] = cd_row[1]

    # Build site entries with all context
    sites = []
    for row in rows:
        r = dict(row._mapping)
        site_id = r["site_id"]
        name = r["name"]

        # Look up enrichment data by site_id
        qid_entry = enrichment_qids.get(site_id, {})
        claims_entry = enrichment_claims.get(site_id, {})
        wiki_entry = enrichment_wiki.get(site_id, {})

        # Build enrichment context
        enrichment = {}
        if qid_entry.get("qid"):
            enrichment["qid"] = qid_entry["qid"]
        if claims_entry.get("heritage"):
            enrichment["heritage"] = claims_entry["heritage"]
        if claims_entry.get("inception") is not None:
            enrichment["inception"] = claims_entry["inception"]
        if claims_entry.get("commons_image"):
            enrichment["commons_image"] = claims_entry["commons_image"]

        site_entry = {
            "site_id": site_id,
            "name": name,
            "country": r["country"],
            "site_type": r["site_type"],
            "period_start": r["period_start"],
            "period_name": r["period_name"],
            "source_url": r["source_url"],
            "current_description": r["description"],
            "current_card_description": card_descs.get(site_id),
            "enrichment": enrichment,
            "wiki_extract": wiki_entry.get("extract", ""),
            "reference_links": ref_links_by_site.get(site_id, []),
        }
        sites.append(site_entry)

    # Split into batches
    batches = []
    for i in range(0, len(sites), batch_size):
        batch_num = f"{len(batches) + 1:03d}"
        batch_sites = sites[i : i + batch_size]
        batch = {
            "batch_id": batch_num,
            "sites": batch_sites,
        }
        batch_path = DEEP_RESEARCH_DIR / f"batch_{batch_num}_input.json"
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False, default=str)
        batches.append(batch_num)

    # Write manifest
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "total_sites": len(sites),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "batches": {
            bid: {"status": "pending", "input": f"batch_{bid}_input.json"}
            for bid in batches
        },
    }
    manifest_path = DEEP_RESEARCH_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    sites_with_refs = sum(1 for s in sites if s["reference_links"])
    sites_without_refs = len(sites) - sites_with_refs

    print(f"[DEEP-RESEARCH] Prepared {len(batches)} batches ({len(sites)} sites)", flush=True)
    print(f"  Sites with reference links: {sites_with_refs}", flush=True)
    print(f"  Sites without reference links: {sites_without_refs}", flush=True)
    print(f"  Batch files: {DEEP_RESEARCH_DIR}/batch_NNN_input.json", flush=True)
    print(f"  Manifest: {manifest_path}", flush=True)
    print(f"\n  Next steps:", flush=True)
    print(f"    1. Launch agents to process each batch (10 per wave)", flush=True)
    print(f"    2. Agent writes batch_NNN_results.json", flush=True)
    print(f"    3. Run: python scripts/audit_enrich.py --phase deep-research-merge", flush=True)

    return {"total_sites": len(sites), "batches": len(batches), "batch_size": batch_size}


def merge_deep_research(dry_run: bool = False) -> dict:
    """Merge deep research results into unified_sites and card_stats.

    Reads batch result files, validates descriptions, backs up originals
    in raw_data, and writes new descriptions and card_descriptions.
    """
    manifest_path = DEEP_RESEARCH_DIR / "manifest.json"
    if not manifest_path.exists():
        print("[DEEP-RESEARCH-MERGE] No manifest found. Run --phase deep-research first.", flush=True)
        return {"error": "no manifest"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    stats = {
        "batches_processed": 0,
        "descriptions_updated": 0,
        "card_descriptions_updated": 0,
        "corrections_applied": 0,
        "skipped_validation": 0,
        "skipped_low_confidence": 0,
        "errors": 0,
    }

    for batch_id, batch_info in manifest.get("batches", {}).items():
        if batch_info.get("status") == "merged":
            continue

        result_path = DEEP_RESEARCH_DIR / f"batch_{batch_id}_results.json"
        if not result_path.exists():
            continue

        with open(result_path, encoding="utf-8") as f:
            results = json.load(f)

        site_results = results.get("sites", {})

        if dry_run:
            for site_id, site_data in site_results.items():
                status = site_data.get("status", "?")
                desc = site_data.get("description", {})
                card = site_data.get("card_description", {})
                desc_len = desc.get("char_count", len(desc.get("text", "")))
                card_len = card.get("char_count", len(card.get("text", "")))
                sources = desc.get("sources_used", [])
                conf = desc.get("confidence", "?")
                print(
                    f"  [DRY-RUN] {site_id[:8]}.. status={status} "
                    f"desc={desc_len}c card={card_len}c "
                    f"sources={len(sources)} conf={conf}",
                    flush=True,
                )
            stats["batches_processed"] += 1
            continue

        with engine.connect() as conn:
            for site_id, site_data in site_results.items():
                status = site_data.get("status")
                if status in ("unchanged", "failed"):
                    continue

                desc_data = site_data.get("description", {})
                card_data = site_data.get("card_description", {})
                desc_text = desc_data.get("text", "")
                card_text = card_data.get("text", "")
                sources_used = desc_data.get("sources_used", [])
                confidence = desc_data.get("confidence", "low")

                # Validate description length (500-1000 chars)
                if len(desc_text) < 400 or len(desc_text) > 1100:
                    print(
                        f"  [SKIP] {site_id[:8]}.. description length {len(desc_text)} "
                        f"outside 400-1100 range",
                        flush=True,
                    )
                    stats["skipped_validation"] += 1
                    continue

                # Validate card_description length (max 200 chars)
                if card_text and len(card_text) > 210:
                    print(
                        f"  [SKIP] {site_id[:8]}.. card_description length {len(card_text)} > 210",
                        flush=True,
                    )
                    stats["skipped_validation"] += 1
                    continue

                # Reject low-confidence descriptions with < 2 sources
                if confidence == "high" and len(sources_used) < 2:
                    print(
                        f"  [SKIP] {site_id[:8]}.. claims high confidence but only "
                        f"{len(sources_used)} sources",
                        flush=True,
                    )
                    stats["skipped_low_confidence"] += 1
                    continue

                # Skip low confidence entirely
                if confidence == "low":
                    stats["skipped_low_confidence"] += 1
                    continue

                # Backup original description in raw_data before overwriting
                try:
                    conn.execute(
                        text("""
                            UPDATE unified_sites
                            SET raw_data = COALESCE(raw_data, '{}'::jsonb) ||
                                jsonb_build_object('description_pre_enrichment', description)
                            WHERE id = CAST(:site_id AS uuid)
                            AND (raw_data IS NULL OR raw_data->>'description_pre_enrichment' IS NULL)
                        """),
                        {"site_id": site_id},
                    )

                    # Write new description
                    conn.execute(
                        text("""
                            UPDATE unified_sites
                            SET description = :desc, edited_by = 'deep_research'
                            WHERE id = CAST(:site_id AS uuid)
                        """),
                        {"site_id": site_id, "desc": desc_text},
                    )
                    stats["descriptions_updated"] += 1

                    # Write new card_description
                    if card_text:
                        conn.execute(
                            text("""
                                UPDATE card_stats
                                SET card_description = :card_desc
                                WHERE site_id = CAST(:site_id AS uuid)
                            """),
                            {"site_id": site_id, "card_desc": card_text[:200]},
                        )
                        stats["card_descriptions_updated"] += 1

                except Exception as e:
                    print(f"  [ERROR] {site_id[:8]}.. {e}", flush=True)
                    stats["errors"] += 1
                    continue

                # Process corrections (period_start fixes etc.)
                for correction in site_data.get("corrections", []):
                    field = correction.get("field")
                    old_val = correction.get("old")
                    new_val = correction.get("new")
                    corr_conf = correction.get("confidence", "low")

                    if corr_conf != "high" or field not in ("period_start",):
                        continue

                    try:
                        if old_val is None:
                            conn.execute(
                                text(f"""
                                    UPDATE unified_sites
                                    SET {field} = :new_val, edited_by = 'deep_research'
                                    WHERE id = CAST(:site_id AS uuid) AND {field} IS NULL
                                """),
                                {"site_id": site_id, "new_val": new_val},
                            )
                        else:
                            conn.execute(
                                text(f"""
                                    UPDATE unified_sites
                                    SET {field} = :new_val, edited_by = 'deep_research'
                                    WHERE id = CAST(:site_id AS uuid) AND {field} = :old_val
                                """),
                                {"site_id": site_id, "new_val": new_val, "old_val": old_val},
                            )
                        stats["corrections_applied"] += 1
                    except Exception as e:
                        print(f"  [ERROR] correction {site_id[:8]}.. {field}: {e}", flush=True)

            conn.commit()

        # Update manifest
        manifest["batches"][batch_id]["status"] = "merged"
        stats["batches_processed"] += 1

    # Save updated manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Update card_descriptions.json output file
    if not dry_run and stats["card_descriptions_updated"] > 0:
        _update_card_descriptions_file()

    print(f"[DEEP-RESEARCH-MERGE] Processed {stats['batches_processed']} batches", flush=True)
    print(f"  Descriptions updated: {stats['descriptions_updated']}", flush=True)
    print(f"  Card descriptions updated: {stats['card_descriptions_updated']}", flush=True)
    print(f"  Corrections applied: {stats['corrections_applied']}", flush=True)
    print(f"  Skipped (validation): {stats['skipped_validation']}", flush=True)
    print(f"  Skipped (low confidence): {stats['skipped_low_confidence']}", flush=True)
    if stats["errors"]:
        print(f"  Errors: {stats['errors']}", flush=True)

    return stats


def _update_card_descriptions_file():
    """Re-export card_descriptions.json from the database."""
    out_path = OUTPUT_DIR / "card_descriptions.json"
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT us.id::text AS site_id, us.name, cs.card_description
                FROM unified_sites us
                JOIN card_stats cs ON cs.site_id = us.id
                WHERE us.source_id = 'ancient_nerds'
                AND cs.card_description IS NOT NULL
                AND cs.card_description != ''
                ORDER BY us.name
            """)
        ).fetchall()

    descriptions = {row.site_id: {"name": row.name, "card_description": row.card_description} for row in rows}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(descriptions, f, indent=2, ensure_ascii=False)

    print(f"  Updated {out_path} ({len(descriptions)} descriptions)", flush=True)


# =============================================================================
# Cited Description Writing (Phase 2 of Verified Enrichment Pipeline)
# =============================================================================

CITED_DESC_AGENT_PROMPT = """\
You are writing verified, cited descriptions for archaeological sites.

## Your task

1. Read the batch input file: `output/cited_description_batches/batch_{BATCH_ID}_input.json`
2. For each site, you receive:
   - Current description (Wikipedia-based)
   - Reference links discovered by web search
   - Wikipedia extract
   - Wikidata enrichment data
3. WebFetch the top 3 reference URLs (prefer quality: "high")
4. Before using a fetched page, VERIFY it's about THIS specific archaeological site:
   - Does it mention the correct country/region?
   - Is it about archaeology/history (not a namesake — video game, modern building, hotel)?
   - If wrong entity, skip it and note in fetch_errors
5. Write a new description (500-800 chars, HARD LIMIT 900) with [1][2][3] citation markers
   - Count characters carefully. Descriptions over 900 chars WILL BE REJECTED.
   - Aim for 600-750 chars. Be concise. Prefer shorter sentences.
6. Every factual claim MUST have a [N] citation
7. Extract relevant excerpts from each fetched page (max 500 chars each)

## Citation rules

- [N] goes immediately after the claim it supports
- Same source can have multiple [N] for different claims
- Generic statements ("one of the most important sites") don't need citations
- If all fetches fail, use Wikipedia as [1] source
- Max 5 unique source URLs per description
- Number citations sequentially starting from [1]
- ONLY cite URLs you successfully fetched or Wikipedia. Never cite a URL that returned an error.
- If a fetch fails, add it to fetch_errors and do NOT cite it
- If you cite Wikipedia, you MUST include a Wikipedia excerpt in fetched_excerpts (use the wiki_extract from input, or WebFetch the Wikipedia page)

## Output format

Write this exact JSON structure to `output/cited_description_batches/batch_{BATCH_ID}_results.json`:

```json
{
  "batch_id": "NNN",
  "sites": {
    "<site_id>": {
      "status": "improved|unchanged|failed",
      "description": {
        "text": "Description with [1][2] citation markers...",
        "char_count": 714,
        "citations": [
          {"n": 1, "url": "https://...", "title": "Page Title", "domain": "example.com", "claim": "exact claim text this citation supports"}
        ]
      },
      "fetched_excerpts": {
        "https://example.com/page": "Relevant text extracted from this page (max 500 chars)..."
      },
      "fetch_errors": ["https://example.com/dead — 404 Not Found"]
    }
  },
  "stats": {
    "improved": 8,
    "unchanged": 1,
    "failed": 1
  }
}
```

## Status values

- "improved" — new cited description is better than the original
- "unchanged" — current description is already excellent or no sources found
- "failed" — could not produce a valid description (explain in fetch_errors)

## Process each site

1. Read its current_description, wiki_extract, enrichment data, and reference_links
2. WebFetch the top 3 reference URLs (prefer quality: "high"). Use the WebFetch tool.
3. Verify each fetched page is about THIS site (country/region/period check)
4. Write a new description (500-800 chars, HARD LIMIT 900) with [N] citation markers for every factual claim
5. Build the citations array mapping each [N] to its source URL and the exact claim text
6. Extract relevant excerpts from each fetched page (max 500 chars each) for verification

IMPORTANT: Every site_id from the input MUST appear in the output. Do not skip any site.

After processing all sites, count the stats and write the output file.
Print a one-line summary: "Batch {BATCH_ID} complete: X improved, Y unchanged, Z failed"
"""


def prepare_cited_description_batches(batch_size: int = 10, limit: int | None = None) -> dict:
    """Prepare batch input files for cited description writing agents.

    Queries ALL ancient_nerds sites, embeds current description, reference links,
    enrichment data, and wiki extract. Creates JSON batch files for agents.
    """
    print("\n[CITED-DESC] Preparing batches for cited description writing...", flush=True)

    CITED_DESC_DIR.mkdir(parents=True, exist_ok=True)

    # Load enrichment data files
    enrichment_qids = {}
    enrichment_claims = {}
    enrichment_wiki = {}

    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    wiki_path = OUTPUT_DIR / "enrichment_wiki.json"

    if qids_path.exists():
        with open(qids_path, encoding="utf-8") as f:
            enrichment_qids = json.load(f).get("matches", {})
        print(f"  Loaded {len(enrichment_qids)} QID matches", flush=True)

    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            enrichment_claims = json.load(f).get("claims", {})
        print(f"  Loaded {len(enrichment_claims)} claim records", flush=True)

    if wiki_path.exists():
        with open(wiki_path, encoding="utf-8") as f:
            enrichment_wiki = json.load(f).get("articles", {})
        print(f"  Loaded {len(enrichment_wiki)} wiki extracts", flush=True)

    with engine.connect() as conn:
        query_str = """
            SELECT
                us.id::text AS site_id,
                us.name,
                us.country,
                us.site_type,
                us.period_name,
                us.period_start,
                us.source_url,
                us.description
            FROM unified_sites us
            WHERE us.source_id = 'ancient_nerds'
            ORDER BY us.name
        """
        if limit:
            query_str += f" LIMIT {limit}"

        rows = conn.execute(text(query_str)).fetchall()

        if not rows:
            print("[CITED-DESC] No sites found. Nothing to do.", flush=True)
            return {"total_sites": 0, "batches": 0}

        # Fetch reference links for all sites
        ref_rows = conn.execute(text("""
            SELECT
                site_id::text,
                title,
                content_url,
                link_metadata->>'domain' AS domain,
                link_metadata->>'link_type' AS link_type,
                CASE WHEN relevance_score >= 0.85 THEN 'high' ELSE 'medium' END AS quality
            FROM site_content_links
            WHERE content_type = 'reference'
            ORDER BY site_id, relevance_score DESC
        """)).fetchall()

        # Fetch card descriptions
        card_desc_rows = conn.execute(text("""
            SELECT site_id::text, card_description
            FROM card_stats
            WHERE site_id IN (
                SELECT id FROM unified_sites WHERE source_id = 'ancient_nerds'
            )
        """)).fetchall()

    # Group reference links by site_id
    ref_links_by_site: dict[str, list[dict]] = {}
    for ref in ref_rows:
        ref_map = dict(ref._mapping)
        sid = ref_map.pop("site_id")
        ref_links_by_site.setdefault(sid, []).append(ref_map)

    # Map card descriptions by site_id
    card_descs: dict[str, str] = {}
    for cd_row in card_desc_rows:
        card_descs[cd_row[0]] = cd_row[1]

    # Build site entries with all context
    sites = []
    for row in rows:
        r = dict(row._mapping)
        site_id = r["site_id"]
        name = r["name"]

        # Look up enrichment data by site_id
        qid_entry = enrichment_qids.get(site_id, {})
        claims_entry = enrichment_claims.get(site_id, {})
        wiki_entry = enrichment_wiki.get(site_id, {})

        enrichment = {}
        if qid_entry.get("qid"):
            enrichment["qid"] = qid_entry["qid"]
        if claims_entry.get("heritage"):
            enrichment["heritage"] = claims_entry["heritage"]
        if claims_entry.get("inception") is not None:
            enrichment["inception"] = claims_entry["inception"]

        site_entry = {
            "site_id": site_id,
            "name": name,
            "country": r["country"],
            "site_type": r["site_type"],
            "period_start": r["period_start"],
            "period_name": r["period_name"],
            "source_url": r["source_url"],
            "current_description": r["description"],
            "current_card_description": card_descs.get(site_id),
            "enrichment": enrichment,
            "wiki_extract": wiki_entry.get("extract", ""),
            "reference_links": ref_links_by_site.get(site_id, []),
        }
        sites.append(site_entry)

    # Split into batches
    batches = []
    for i in range(0, len(sites), batch_size):
        batch_num = f"{len(batches) + 1:03d}"
        batch_sites = sites[i : i + batch_size]
        batch = {
            "batch_id": batch_num,
            "sites": batch_sites,
        }
        batch_path = CITED_DESC_DIR / f"batch_{batch_num}_input.json"
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False, default=str)
        batches.append(batch_num)

    # Write manifest
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "total_sites": len(sites),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "batches": {
            bid: {"status": "pending", "input": f"batch_{bid}_input.json"}
            for bid in batches
        },
    }
    manifest_path = CITED_DESC_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    sites_with_refs = sum(1 for s in sites if s["reference_links"])
    sites_without_refs = len(sites) - sites_with_refs

    print(f"[CITED-DESC] Prepared {len(batches)} batches ({len(sites)} sites)", flush=True)
    print(f"  Sites with reference links: {sites_with_refs}", flush=True)
    print(f"  Sites without reference links (Wikipedia-only): {sites_without_refs}", flush=True)
    print(f"  Batch files: {CITED_DESC_DIR}/batch_NNN_input.json", flush=True)
    print(f"  Manifest: {manifest_path}", flush=True)
    print(f"\n  Next steps:", flush=True)
    print(f"    1. Launch agents to process each batch (10 per wave)", flush=True)
    print(f"    2. Agent writes batch_NNN_results.json", flush=True)
    print(f"    3. Run: python scripts/audit_enrich.py --phase cited-description-merge", flush=True)

    return {"total_sites": len(sites), "batches": len(batches), "batch_size": batch_size}


# =============================================================================
# Cited Description Merge (Phase 2 — format validation only, no DB writes)
# =============================================================================


def merge_cited_descriptions(dry_run: bool = False) -> dict:
    """Validate cited description results (format only, no DB writes).

    Checks JSON structure, description char counts, citation array completeness,
    and fetched_excerpts existence. Marks batches as 'completed' (not 'merged' —
    that happens after Phase 3 verification).
    """
    manifest_path = CITED_DESC_DIR / "manifest.json"
    if not manifest_path.exists():
        print("[CITED-DESC-MERGE] No manifest found. Run --phase cited-description first.", flush=True)
        return {"error": "no manifest"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    stats = {
        "batches_validated": 0,
        "sites_improved": 0,
        "sites_unchanged": 0,
        "sites_failed": 0,
        "validation_errors": 0,
    }
    validation_errors: list[dict] = []

    for batch_id, batch_info in manifest.get("batches", {}).items():
        if batch_info.get("status") in ("completed", "merged"):
            continue

        result_path = CITED_DESC_DIR / f"batch_{batch_id}_results.json"
        if not result_path.exists():
            continue

        with open(result_path, encoding="utf-8") as f:
            results = json.load(f)

        site_results = results.get("sites", {})
        batch_valid = True

        for site_id, site_data in site_results.items():
            status = site_data.get("status", "unknown")

            if status == "improved":
                desc = site_data.get("description", {})
                desc_text = desc.get("text", "")
                citations = desc.get("citations", [])
                char_count = len(desc_text)
                fetched_excerpts = site_data.get("fetched_excerpts", {})

                errors = []

                # Validate description length (300-950 chars)
                if char_count < 300 or char_count > 950:
                    errors.append(f"description length {char_count} outside 300-950 range")

                # Validate citations array is non-empty
                if not citations:
                    errors.append("citations array is empty for improved description")

                # Validate each citation has required fields
                for cit in citations:
                    missing = [k for k in ("n", "url", "title", "domain", "claim") if k not in cit]
                    if missing:
                        errors.append(f"citation [{ cit.get('n', '?') }] missing fields: {missing}")

                # Validate fetched_excerpts exist for cited URLs
                cited_urls = {c["url"] for c in citations if "url" in c}
                fetch_error_urls = {e.split(" — ")[0] for e in site_data.get("fetch_errors", [])}
                for url in cited_urls:
                    if url not in fetched_excerpts and url not in fetch_error_urls:
                        # Wikipedia source_url citations don't need fetched excerpts
                        if "wikipedia.org" not in url:
                            errors.append(f"no fetched excerpt for cited URL: {url[:60]}")

                if errors:
                    batch_valid = False
                    stats["validation_errors"] += len(errors)
                    validation_errors.append({
                        "batch_id": batch_id,
                        "site_id": site_id,
                        "errors": errors,
                    })
                    if dry_run:
                        for err in errors:
                            print(f"  [WARN] {site_id[:8]}.. {err}", flush=True)
                else:
                    stats["sites_improved"] += 1

            elif status == "unchanged":
                stats["sites_unchanged"] += 1
            elif status == "failed":
                stats["sites_failed"] += 1

        # Mark batch as completed (ready for Phase 3) if valid
        if not dry_run and batch_valid:
            manifest["batches"][batch_id]["status"] = "completed"
        stats["batches_validated"] += 1

    # Save updated manifest
    if not dry_run:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Write validation errors if any
    if validation_errors:
        err_path = OUTPUT_DIR / "cited_description_validation_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False)
        print(f"\n  Validation errors: {err_path} ({len(validation_errors)} items)", flush=True)

    prefix = "[CITED-DESC-MERGE DRY RUN]" if dry_run else "[CITED-DESC-MERGE]"
    print(f"{prefix} Validated {stats['batches_validated']} batches", flush=True)
    print(f"  Sites improved: {stats['sites_improved']}", flush=True)
    print(f"  Sites unchanged: {stats['sites_unchanged']}", flush=True)
    print(f"  Sites failed: {stats['sites_failed']}", flush=True)
    if stats["validation_errors"]:
        print(f"  Validation errors: {stats['validation_errors']}", flush=True)

    return stats


# =============================================================================
# Independent Verification (Phase 3 of Verified Enrichment Pipeline)
# =============================================================================

VERIFICATION_AGENT_PROMPT = """\
You are an independent fact-checker for archaeological site descriptions.

## Your task

1. Read the batch input file: `output/verification_batches/batch_{BATCH_ID}_input.json`
2. Each site entry has these fields:
   - `description`: The description text with [N] citation markers
   - `citations`: Array of objects, each with {n, url, title, domain, claim}
   - `fetched_excerpts`: Dict mapping URL → extracted text from that page (max 500 chars each).
     This includes Wikipedia extracts for any cited Wikipedia URLs.
   - `site_id`: The site's unique ID
   - `source_batch`: Which Phase 2 batch this came from

## Verification rules

For each [N] citation, check:
- Is the claim actually supported by the source excerpt?
- Numbers/dates must match (exactly or approximately — "2nd century" and "120 AD" are compatible)
- Proper nouns must match
- The fact must be present or clearly implied in the excerpt
- If the source excerpt is empty or missing, the claim is unverifiable — mark for removal

## What to do with unverified claims

- If a claim is NOT supported by its source → mark for removal
- Remove the ENTIRE sentence containing the unverifiable [N]
- Renumber remaining [N] citations sequentially from [1]
- Update the citations array to match the renumbered markers
- If ALL claims fail → verdict: "fail", keep the original description

## Scoring

verification_score = verified_claims / total_claims
- score >= 0.5 → verdict: "pass" (description is usable)
- score < 0.5 → verdict: "fail" (too many unverified claims, keep original)

## Output format

Write this exact JSON structure to `output/verification_batches/batch_{BATCH_ID}_results.json`:

```json
{
  "batch_id": "NNN",
  "sites": {
    "<site_id>": {
      "verified_description": "Text with renumbered [1][2] markers...",
      "verified_citations": [
        {"n": 1, "url": "https://...", "title": "...", "domain": "...", "claim": "..."}
      ],
      "removed_claims": [
        {"original_n": 2, "claim": "The site was founded in 500 BC", "reason": "Source does not mention founding date"}
      ],
      "verification_score": 0.67,
      "verdict": "pass|fail"
    }
  },
  "stats": {
    "pass": 7,
    "fail": 3,
    "total_claims_checked": 45,
    "total_claims_verified": 30,
    "total_claims_removed": 15
  }
}
```

## Process each site

1. Read the description with [N] markers and the citations array
2. For each [N], find the corresponding citation and source excerpt
3. Check if the claim text is supported by the excerpt
4. Build lists of verified and removed claims
5. If any claims removed: reconstruct description without those sentences, renumber [N]
6. Compute verification_score and verdict
7. Output the verified (or failed) result

IMPORTANT: Every site_id from the input MUST appear in the output. Do not skip any site.

After processing all sites, count the stats and write the output file.
Print a one-line summary: "Batch {BATCH_ID} complete: X pass, Y fail, Z claims verified / W total"
"""


def prepare_verification_batches(batch_size: int = 10, limit: int | None = None) -> dict:
    """Prepare batch input files for independent citation verification.

    Reads Phase 2 completed batches, extracts description/citations/fetched_excerpts,
    and bundles into verification batches for fact-checking agents.
    """
    print("\n[VERIFY] Preparing batches for citation verification...", flush=True)

    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

    # Read Phase 2 manifest to find completed batches
    cited_manifest_path = CITED_DESC_DIR / "manifest.json"
    if not cited_manifest_path.exists():
        print("[VERIFY] No cited description manifest found. Run Phase 2 first.", flush=True)
        return {"error": "no_phase2_manifest"}

    with open(cited_manifest_path, encoding="utf-8") as f:
        cited_manifest = json.load(f)

    # Collect all improved sites from completed (but not yet merged) Phase 2 batches
    verification_sites = []
    for batch_id, batch_info in cited_manifest.get("batches", {}).items():
        if batch_info.get("status") != "completed":
            continue

        result_path = CITED_DESC_DIR / f"batch_{batch_id}_results.json"
        if not result_path.exists():
            continue

        with open(result_path, encoding="utf-8") as f:
            results = json.load(f)

        # Load Phase 2 input to get wiki_extract for Wikipedia-cited URLs
        input_path = CITED_DESC_DIR / f"batch_{batch_id}_input.json"
        wiki_extracts_by_site = {}
        if input_path.exists():
            with open(input_path, encoding="utf-8") as fi:
                input_data = json.load(fi)
            for site_entry in input_data.get("sites", []):
                if site_entry.get("wiki_extract"):
                    wiki_extracts_by_site[site_entry["site_id"]] = site_entry["wiki_extract"]

        for site_id, site_data in results.get("sites", {}).items():
            if site_data.get("status") != "improved":
                continue

            desc = site_data.get("description", {})
            if not desc.get("text") or not desc.get("citations"):
                continue

            fetched_excerpts = dict(site_data.get("fetched_excerpts", {}))

            # Inject wiki_extract as excerpt for any cited Wikipedia URL
            wiki_extract = wiki_extracts_by_site.get(site_id, "")
            if wiki_extract:
                for citation in desc["citations"]:
                    url = citation.get("url", "")
                    if "wikipedia.org" in url and url not in fetched_excerpts:
                        fetched_excerpts[url] = wiki_extract[:500]

            verification_sites.append({
                "site_id": site_id,
                "description": desc["text"],
                "citations": desc["citations"],
                "fetched_excerpts": fetched_excerpts,
                "source_batch": batch_id,
            })

    if not verification_sites:
        print("[VERIFY] No improved sites found in Phase 2 results. Nothing to verify.", flush=True)
        return {"total_sites": 0, "batches": 0}

    if limit:
        verification_sites = verification_sites[:limit]

    # Split into batches
    batches = []
    for i in range(0, len(verification_sites), batch_size):
        batch_num = f"{len(batches) + 1:03d}"
        batch_sites = verification_sites[i : i + batch_size]
        batch = {
            "batch_id": batch_num,
            "sites": batch_sites,
        }
        batch_path = VERIFICATION_DIR / f"batch_{batch_num}_input.json"
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)
        batches.append(batch_num)

    # Write manifest
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "total_sites": len(verification_sites),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "batches": {
            bid: {"status": "pending", "input": f"batch_{bid}_input.json"}
            for bid in batches
        },
    }
    manifest_path = VERIFICATION_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[VERIFY] Prepared {len(batches)} batches ({len(verification_sites)} sites)", flush=True)
    print(f"  Batch files: {VERIFICATION_DIR}/batch_NNN_input.json", flush=True)
    print(f"  Manifest: {manifest_path}", flush=True)
    print(f"\n  Next steps:", flush=True)
    print(f"    1. Launch verification agents (10 per wave)", flush=True)
    print(f"    2. Agent writes batch_NNN_results.json", flush=True)
    print(f"    3. Run: python scripts/audit_enrich.py --phase verify-citations-merge", flush=True)

    return {"total_sites": len(verification_sites), "batches": len(batches), "batch_size": batch_size}


# =============================================================================
# Verification Merge (Phase 3 — writes verified descriptions to DB)
# =============================================================================


def merge_verification(dry_run: bool = False) -> dict:
    """Merge verification results into unified_sites.

    For verdict 'pass' (score >= 0.5):
    - Backup original description in raw_data->description_pre_enrichment
    - Write verified_description to unified_sites.description
    - Write verified_citations to raw_data->description_citations

    For verdict 'fail':
    - Keep original description
    - Add to manual review list
    """
    manifest_path = VERIFICATION_DIR / "manifest.json"
    if not manifest_path.exists():
        print("[VERIFY-MERGE] No manifest found. Run --phase verify-citations first.", flush=True)
        return {"error": "no manifest"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    stats = {
        "batches_processed": 0,
        "descriptions_updated": 0,
        "kept_original": 0,
        "total_claims_removed": 0,
        "errors": 0,
    }
    failed_sites: list[dict] = []
    source_batches_consumed: set[str] = set()  # Phase 2 batch IDs consumed by verification

    for batch_id, batch_info in manifest.get("batches", {}).items():
        if batch_info.get("status") == "merged":
            continue

        result_path = VERIFICATION_DIR / f"batch_{batch_id}_results.json"
        if not result_path.exists():
            continue

        # Track which Phase 2 batches are consumed by this verification batch
        input_path = VERIFICATION_DIR / f"batch_{batch_id}_input.json"
        if input_path.exists():
            with open(input_path, encoding="utf-8") as f:
                input_data = json.load(f)
            for site in input_data.get("sites", []):
                if site.get("source_batch"):
                    source_batches_consumed.add(site["source_batch"])

        with open(result_path, encoding="utf-8") as f:
            results = json.load(f)

        site_results = results.get("sites", {})

        if dry_run:
            for site_id, site_data in site_results.items():
                verdict = site_data.get("verdict", "?")
                score = site_data.get("verification_score", 0)
                removed = len(site_data.get("removed_claims", []))
                verified_desc = site_data.get("verified_description", "")
                print(
                    f"  [DRY-RUN] {site_id[:8]}.. verdict={verdict} "
                    f"score={score:.2f} removed={removed} "
                    f"desc_len={len(verified_desc)}",
                    flush=True,
                )
            stats["batches_processed"] += 1
            continue

        with engine.connect() as conn:
            for site_id, site_data in site_results.items():
                verdict = site_data.get("verdict", "fail")
                score = site_data.get("verification_score", 0)
                removed_claims = site_data.get("removed_claims", [])
                stats["total_claims_removed"] += len(removed_claims)

                if verdict == "pass" and score >= 0.5:
                    verified_desc = site_data.get("verified_description", "")
                    verified_citations = site_data.get("verified_citations", [])

                    if not verified_desc:
                        stats["errors"] += 1
                        continue

                    try:
                        # Backup original description
                        conn.execute(
                            text("""
                                UPDATE unified_sites
                                SET raw_data = COALESCE(raw_data, '{}'::jsonb) ||
                                    jsonb_build_object('description_pre_enrichment', description)
                                WHERE id = CAST(:site_id AS uuid)
                                AND (raw_data IS NULL OR raw_data->>'description_pre_enrichment' IS NULL)
                            """),
                            {"site_id": site_id},
                        )

                        # Write verified description
                        conn.execute(
                            text("""
                                UPDATE unified_sites
                                SET description = :desc,
                                    raw_data = COALESCE(raw_data, '{}'::jsonb) ||
                                        jsonb_build_object('description_citations', CAST(:citations AS jsonb)),
                                    edited_by = 'cited_enrichment'
                                WHERE id = CAST(:site_id AS uuid)
                            """),
                            {
                                "site_id": site_id,
                                "desc": verified_desc,
                                "citations": json.dumps(verified_citations),
                            },
                        )
                        stats["descriptions_updated"] += 1

                    except Exception as e:
                        print(f"  [ERROR] {site_id[:8]}.. {e}", flush=True)
                        stats["errors"] += 1

                else:
                    # verdict == "fail" or score < 0.5 — keep original
                    stats["kept_original"] += 1
                    failed_sites.append({
                        "site_id": site_id,
                        "batch_id": batch_id,
                        "verdict": verdict,
                        "verification_score": score,
                        "removed_claims": removed_claims,
                        "reason": "verification score below threshold" if score < 0.5 else "all claims failed",
                    })

            conn.commit()

        # Update manifest
        manifest["batches"][batch_id]["status"] = "merged"
        stats["batches_processed"] += 1

    # Save updated verification manifest
    if not dry_run:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # Mark consumed Phase 2 batches as 'merged' to prevent re-verification
        if source_batches_consumed:
            cited_manifest_path = CITED_DESC_DIR / "manifest.json"
            if cited_manifest_path.exists():
                with open(cited_manifest_path, encoding="utf-8") as f:
                    cited_manifest = json.load(f)
                for src_bid in source_batches_consumed:
                    if src_bid in cited_manifest.get("batches", {}):
                        cited_manifest["batches"][src_bid]["status"] = "merged"
                with open(cited_manifest_path, "w", encoding="utf-8") as f:
                    json.dump(cited_manifest, f, indent=2, ensure_ascii=False)
                print(f"  Marked {len(source_batches_consumed)} Phase 2 batches as merged", flush=True)

    # Write failed sites for manual review
    if failed_sites:
        review_path = OUTPUT_DIR / "manual_review_failed_verification.json"
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(failed_sites, f, indent=2, ensure_ascii=False)
        print(f"\n  Failed verification review: {review_path} ({len(failed_sites)} sites)", flush=True)

    prefix = "[VERIFY-MERGE DRY RUN]" if dry_run else "[VERIFY-MERGE]"
    print(f"{prefix} Processed {stats['batches_processed']} batches", flush=True)
    print(f"  Descriptions updated: {stats['descriptions_updated']}", flush=True)
    print(f"  Kept original (failed verification): {stats['kept_original']}", flush=True)
    print(f"  Total claims removed: {stats['total_claims_removed']}", flush=True)
    if stats["errors"]:
        print(f"  Errors: {stats['errors']}", flush=True)

    return stats


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Database Audit & Enrichment Orchestrator"
    )
    parser.add_argument(
        "--mode",
        choices=["default", "full"],
        default="default",
        help="default: skip recently audited; full: re-audit everything",
    )
    parser.add_argument(
        "--source",
        choices=ALL_SOURCE_IDS,
        help="Single source only (default: all 3 AN sources)",
    )
    parser.add_argument(
        "--phase",
        choices=["sync", "mechanical", "enrich", "apply", "verify", "agents", "merge", "package", "export", "web-links", "web-links-merge", "deep-research", "deep-research-merge", "cited-description", "cited-description-merge", "verify-citations", "verify-citations-merge"],
        help="Run only a specific phase",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Production API URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Test mode: process only N random sites (skips sync and mechanical fixes)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing values with Wikidata data (default: only fill NULLs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="(merge phase) Report proposed changes without writing to DB",
    )
    args = parser.parse_args()

    source_ids = [args.source] if args.source else ALL_SOURCE_IDS
    phase = args.phase
    limit = args.limit

    print("=" * 60, flush=True)
    print("  Ancient Nerds - Audit & Enrichment Orchestrator", flush=True)
    print("=" * 60, flush=True)
    print(f"  Sources: {', '.join(source_ids)}", flush=True)
    print(f"  Mode: {args.mode}", flush=True)
    print(f"  Phase: {phase or 'all'}", flush=True)
    print(f"  API: {args.api_url}", flush=True)
    if limit:
        print(f"  Limit: {limit} random sites (test mode)", flush=True)
    if args.overwrite:
        print(f"  Overwrite: yes (verify + correct existing values)", flush=True)
    print("=" * 60, flush=True)

    # --limit mode: skip sync & mechanical, run enrichment + apply + package on N random sites
    # (but not when running web-links phases — those handle --limit themselves)
    if limit and phase not in ("web-links", "web-links-merge", "deep-research", "deep-research-merge", "cited-description", "cited-description-merge", "verify-citations", "verify-citations-merge"):
        sites = fetch_audit_candidates(source_ids, args.mode, limit=limit)
        if not sites:
            print("\n[AUDIT] No candidates found. Nothing to do.", flush=True)
            return

        candidate_site_ids = {s["site_id"] for s in sites}

        print("\n" + "=" * 40, flush=True)
        print("  WAVE 1: Wikidata Enrichment", flush=True)
        print("=" * 40, flush=True)
        run_enrichment_pipeline(card_sites=sites)

        print("\n" + "=" * 40, flush=True)
        print("  APPLY: Enrichment -> unified_sites", flush=True)
        print("=" * 40, flush=True)
        apply_enrichment(overwrite=args.overwrite)

        print("\n" + "=" * 40, flush=True)
        print("  PACKAGE: Export for db.html Upload", flush=True)
        print("=" * 40, flush=True)
        package_for_upload(source_ids, candidate_site_ids=candidate_site_ids)

        print("\n" + "=" * 60, flush=True)
        print("  Audit & Enrichment Complete", flush=True)
        print("=" * 60, flush=True)
        return

    # Step 1: Sync from production API (always first)
    if phase in (None, "sync"):
        print("\n" + "=" * 40, flush=True)
        print("  SYNC: Fetch Production -> Local DB", flush=True)
        print("=" * 40, flush=True)
        sync_from_production(args.api_url, source_ids)
        if phase == "sync":
            print("\n[SYNC] Done. Local DB now matches production.", flush=True)
            return

    # Fetch candidates for audit (unless just merging/exporting/packaging/agents/weblinks)
    if phase not in ("merge", "export", "package", "agents", "apply", "web-links", "web-links-merge", "deep-research", "deep-research-merge", "cited-description", "cited-description-merge", "verify-citations", "verify-citations-merge"):
        sites = fetch_audit_candidates(source_ids, args.mode)
        if not sites:
            print("\n[AUDIT] No candidates found. Nothing to do.", flush=True)
            return
    else:
        sites = []

    # Wave 0: Mechanical fixes
    if phase in (None, "mechanical"):
        print("\n" + "=" * 40, flush=True)
        print("  WAVE 0: Mechanical Fixes", flush=True)
        print("=" * 40, flush=True)
        run_mechanical_fixes(sites)

    # Wave 1: Wikidata enrichment
    if phase in (None, "enrich"):
        print("\n" + "=" * 40, flush=True)
        print("  WAVE 1: Wikidata Enrichment", flush=True)
        print("=" * 40, flush=True)
        run_enrichment_pipeline()

    # Apply enrichment data to unified_sites
    if phase in (None, "apply"):
        print("\n" + "=" * 40, flush=True)
        print("  APPLY: Enrichment -> unified_sites", flush=True)
        print("=" * 40, flush=True)
        apply_enrichment(overwrite=args.overwrite)

    # Wave 2: Prepare agent batches
    if phase in (None, "verify"):
        print("\n" + "=" * 40, flush=True)
        print("  WAVE 2: Agent Verification (Prepare)", flush=True)
        print("=" * 40, flush=True)
        batch_stats = prepare_agent_batches(sites)

        # In full-run mode, stop here with handoff instructions
        if phase is None and batch_stats.get("batches", 0) > 0:
            print("\n" + "=" * 60, flush=True)
            print("  [WAVE 2] Batch files prepared. To run agent research:", flush=True)
            print('    1. In Claude Code, say: "run Wave 2 agent research"', flush=True)
            print("    2. After agents complete, run:", flush=True)
            print("       python scripts/audit_enrich.py --phase merge --dry-run", flush=True)
            print("       python scripts/audit_enrich.py --phase merge", flush=True)
            print("    3. Then: python scripts/audit_enrich.py --phase package", flush=True)
            print("=" * 60, flush=True)

    # Wave 2: Show agent batch status and handoff instructions
    if phase == "agents":
        print("\n" + "=" * 40, flush=True)
        print("  WAVE 2: Agent Research Status", flush=True)
        print("=" * 40, flush=True)
        show_agent_status()

    # Merge agent results
    if phase == "merge":
        print("\n" + "=" * 40, flush=True)
        print("  Merge Agent Results", flush=True)
        print("=" * 40, flush=True)
        merge_results(dry_run=args.dry_run)

    # Mark audited sites (if running all phases or mechanical/enrich)
    if phase in (None, "mechanical", "enrich") and sites:
        site_ids = [s["site_id"] for s in sites]
        print(f"\n[AUDIT] Marking {len(site_ids)} sites as audited...", flush=True)
        with engine.connect() as conn:
            # Batch update in chunks of 500
            for i in range(0, len(site_ids), 500):
                chunk = site_ids[i:i + 500]
                placeholders = ", ".join(f":id_{j}" for j in range(len(chunk)))
                params = {f"id_{j}": sid for j, sid in enumerate(chunk)}
                conn.execute(
                    text(f"UPDATE unified_sites SET last_audited = NOW() WHERE id::text IN ({placeholders})"),
                    params,
                )
            conn.commit()
        print(f"  Done. {len(site_ids)} sites marked.", flush=True)

    # Package for db.html upload (last step before manual upload)
    if phase in (None, "package"):
        print("\n" + "=" * 40, flush=True)
        print("  PACKAGE: Export for db.html Upload", flush=True)
        print("=" * 40, flush=True)
        package_for_upload(source_ids)

    # Export static JSON
    if phase in (None, "export"):
        print("\n" + "=" * 40, flush=True)
        print("  Export Static JSON", flush=True)
        print("=" * 40, flush=True)
        export_static()

    # Web reference links: prepare batches
    if phase == "web-links":
        print("\n" + "=" * 40, flush=True)
        print("  WEB-LINKS: Prepare Reference Link Batches", flush=True)
        print("=" * 40, flush=True)
        prepare_weblinks_batches(batch_size=10, limit=limit)

    # Web reference links: merge results
    if phase == "web-links-merge":
        print("\n" + "=" * 40, flush=True)
        print("  WEB-LINKS: Merge Reference Link Results", flush=True)
        print("=" * 40, flush=True)
        merge_weblinks(dry_run=args.dry_run)

    # Deep research: prepare batches
    if phase == "deep-research":
        print("\n" + "=" * 40, flush=True)
        print("  DEEP-RESEARCH: Prepare Description Rewrite Batches", flush=True)
        print("=" * 40, flush=True)
        prepare_deep_research_batches(batch_size=10, limit=limit)

    # Deep research: merge results
    if phase == "deep-research-merge":
        print("\n" + "=" * 40, flush=True)
        print("  DEEP-RESEARCH: Merge Description Rewrite Results", flush=True)
        print("=" * 40, flush=True)
        merge_deep_research(dry_run=args.dry_run)

    # Cited description: prepare batches (Phase 2)
    if phase == "cited-description":
        print("\n" + "=" * 40, flush=True)
        print("  CITED-DESC: Prepare Cited Description Batches", flush=True)
        print("=" * 40, flush=True)
        prepare_cited_description_batches(batch_size=10, limit=limit)

    # Cited description: merge/validate results (Phase 2)
    if phase == "cited-description-merge":
        print("\n" + "=" * 40, flush=True)
        print("  CITED-DESC: Validate Cited Description Results", flush=True)
        print("=" * 40, flush=True)
        merge_cited_descriptions(dry_run=args.dry_run)

    # Verify citations: prepare batches (Phase 3)
    if phase == "verify-citations":
        print("\n" + "=" * 40, flush=True)
        print("  VERIFY: Prepare Citation Verification Batches", flush=True)
        print("=" * 40, flush=True)
        prepare_verification_batches(batch_size=10, limit=limit)

    # Verify citations: merge results to DB (Phase 3)
    if phase == "verify-citations-merge":
        print("\n" + "=" * 40, flush=True)
        print("  VERIFY: Merge Verified Citations to DB", flush=True)
        print("=" * 40, flush=True)
        merge_verification(dry_run=args.dry_run)

    print("\n" + "=" * 60, flush=True)
    print("  Audit & Enrichment Complete", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
