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
        choices=["sync", "mechanical", "enrich", "apply", "verify", "agents", "merge", "package", "export"],
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
    if limit:
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

    # Fetch candidates for audit (unless just merging/exporting/packaging/agents)
    if phase not in ("merge", "export", "package", "agents", "apply"):
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

    print("\n" + "=" * 60, flush=True)
    print("  Audit & Enrichment Complete", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
