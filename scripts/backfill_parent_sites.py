"""Backfill parent_site_id and validate metadata on unified_sites using Wikidata.

Targets ancient_nerds and lyra sources only.

For each site with a resolvable Wikidata QID:
1. Fetch claims: P361 (part-of), P571/P580/P582 (dates), P31 (instance-of)
2. Fill missing period and site_type from Wikidata
3. Link child sites to parents via P361

Usage:
    python scripts/backfill_parent_sites.py                    # dry-run (default)
    python scripts/backfill_parent_sites.py --apply            # apply all fixes
    python scripts/backfill_parent_sites.py --only-parents     # only backfill parent_site_id
    python scripts/backfill_parent_sites.py --only-metadata    # only validate/fix metadata
"""

import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from sqlalchemy import text

from pipeline.database import engine
from pipeline.utils.http import fetch_with_retry

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# Max QIDs per wbgetentities call (Wikidata limit is 50)
BATCH_SIZE = 50

# Max concurrent API requests (respects Wikidata/Wikipedia rate limits)
MAX_WORKERS = 3


# ── Wikidata helpers ─────────────────────────────────────────────────


def _parse_wikidata_time(time_str: str) -> int | None:
    """Parse Wikidata ISO time format to year integer."""
    if not time_str:
        return None
    match = re.match(r"^([+-])0*(\d+)-", time_str)
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    year = int(match.group(2))
    return sign * year if year != 0 else None


def _wikipedia_url_to_title(url: str) -> str | None:
    """Extract the article title from a Wikipedia URL."""
    if not url:
        return None
    m = re.search(r"wikipedia\.org/wiki/(.+?)(?:#|\?|$)", url)
    if m:
        return urllib.parse.unquote(m.group(1)).replace("_", " ")
    return None


def _resolve_titles_to_qids(titles: list[str]) -> dict[str, str]:
    """Resolve Wikipedia article titles to Wikidata QIDs.

    Returns {title: qid} for successfully resolved titles.
    """
    batches = [titles[i : i + BATCH_SIZE] for i in range(0, len(titles), BATCH_SIZE)]

    def fetch_batch(batch):
        resp = fetch_with_retry(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": "|".join(batch),
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "format": "json",
            },
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        normalized = data.get("query", {}).get("normalized", [])
        norm_map = {n["to"]: n["from"] for n in normalized}

        batch_result = {}
        for page in pages.values():
            if page.get("missing") is not None:
                continue
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                page_title = page["title"]
                original = norm_map.get(page_title, page_title)
                batch_result[original] = qid
        return batch_result

    result = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_batch, b) for b in batches]
        for future in as_completed(futures):
            try:
                result.update(future.result())
            except Exception as e:
                print(f"  Wikipedia API error: {e}")
    return result


def _fetch_qid_labels(qids: list[str]) -> dict[str, str]:
    """Fetch English labels for Wikidata QIDs. Returns {qid: label}."""
    batches = [qids[i : i + BATCH_SIZE] for i in range(0, len(qids), BATCH_SIZE)]

    def fetch_batch(batch):
        resp = fetch_with_retry(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
        )
        data = resp.json()
        batch_result = {}
        for qid in batch:
            entity = data.get("entities", {}).get(qid, {})
            label = entity.get("labels", {}).get("en", {}).get("value")
            if label:
                batch_result[qid] = label
        return batch_result

    result = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_batch, b) for b in batches]
        for future in as_completed(futures):
            try:
                result.update(future.result())
            except Exception as e:
                print(f"  Wikidata labels error: {e}")
    return result


def _fetch_wikidata_claims(qids: list[str]) -> dict[str, dict]:
    """Fetch claims for a batch of Wikidata QIDs.

    Returns {qid: parsed_data} where parsed_data contains:
    - part_of_qid: str | None  (P361)
    - lat, lon: float | None   (P625)
    - country_qid: str | None  (P17)
    - inception_year: int | None  (P571 or P580)
    - end_year: int | None        (P582)
    - instance_of: list[str]      (P31 QIDs)
    """
    batches = [qids[i : i + BATCH_SIZE] for i in range(0, len(qids), BATCH_SIZE)]

    def fetch_batch(batch):
        resp = fetch_with_retry(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "claims",
                "format": "json",
            },
        )
        data = resp.json()
        batch_result = {}

        for qid, entity in data.get("entities", {}).items():
            claims = entity.get("claims", {})
            parsed = {}

            # P361: part of
            p361 = claims.get("P361", [])
            if p361:
                val = p361[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if val:
                    parsed["part_of_qid"] = val

            # P625: coordinates
            p625 = claims.get("P625", [])
            if p625:
                coords = p625[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if "latitude" in coords and "longitude" in coords:
                    parsed["lat"] = coords["latitude"]
                    parsed["lon"] = coords["longitude"]

            # P17: country
            p17 = claims.get("P17", [])
            if p17:
                country_id = p17[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if country_id:
                    parsed["country_qid"] = country_id

            # P571: inception / P580: start time
            for prop in ("P571", "P580"):
                entries = claims.get(prop, [])
                if entries and "inception_year" not in parsed:
                    time_val = entries[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                    year = _parse_wikidata_time(time_val.get("time", ""))
                    if year is not None:
                        parsed["inception_year"] = year

            # P582: end time
            p582 = claims.get("P582", [])
            if p582:
                time_val = p582[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                year = _parse_wikidata_time(time_val.get("time", ""))
                if year is not None:
                    parsed["end_year"] = year

            # P31: instance of
            p31 = claims.get("P31", [])
            instance_ids = []
            for claim in p31:
                val = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if val:
                    instance_ids.append(val)
            if instance_ids:
                parsed["instance_of"] = instance_ids

            if parsed:
                batch_result[qid] = parsed

        return batch_result

    result = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_batch, b) for b in batches]
        for future in as_completed(futures):
            try:
                result.update(future.result())
            except Exception as e:
                print(f"  Wikidata API error: {e}")
    return result


# ── QID resolution ───────────────────────────────────────────────────


def _resolve_site_qids(conn, rows) -> dict[str, str]:
    """Resolve all sites to Wikidata QIDs. Returns {site_id_str: qid}."""
    site_qids: dict[str, str] = {}
    titles_to_resolve: dict[str, list[str]] = {}

    for row in rows:
        site_id, source_id, name, source_url, raw_data = (
            row.id, row.source_id, row.name, row.source_url, row.raw_data,
        )
        raw = raw_data or {}

        # Try raw_data paths
        qid = raw.get("wikidata", {}).get("qid") if isinstance(raw.get("wikidata"), dict) else None
        if not qid:
            qid = raw.get("wikidata_id")
        if qid:
            site_qids[str(site_id)] = qid
            continue

        # Resolve Wikipedia URL → title
        title = _wikipedia_url_to_title(source_url)
        if title:
            titles_to_resolve.setdefault(title, []).append(str(site_id))

    # Check user_contributions for lyra sites missing QID
    lyra_missing = [
        str(r.id) for r in rows
        if r.source_id == "lyra" and str(r.id) not in site_qids
    ]
    if lyra_missing:
        contrib_rows = conn.execute(text("""
            SELECT promoted_site_id, wikidata_id
            FROM user_contributions
            WHERE promoted_site_id = ANY(CAST(:ids AS uuid[]))
              AND wikidata_id IS NOT NULL
        """), {"ids": lyra_missing}).fetchall()
        for crow in contrib_rows:
            site_qids[str(crow[0])] = crow[1]

    print(f"  QIDs from raw_data/contributions: {len(site_qids)}")
    print(f"  Wikipedia titles to resolve: {len(titles_to_resolve)}")

    if titles_to_resolve:
        print("  Resolving Wikipedia titles to Wikidata QIDs...")
        title_qids = _resolve_titles_to_qids(list(titles_to_resolve.keys()))
        for title, qid in title_qids.items():
            for sid in titles_to_resolve[title]:
                site_qids[sid] = qid
        print(f"  Resolved {len(title_qids)} titles -> total QIDs: {len(site_qids)}")

    return site_qids


# ── Parent backfill ──────────────────────────────────────────────────


def _resolve_parent_qids_to_site_ids(conn, parent_qids: set[str]) -> dict[str, str]:
    """Look up parent Wikidata QIDs in unified_sites. Returns {qid: site_id}."""
    if not parent_qids:
        return {}
    qid_list = list(parent_qids)
    rows = conn.execute(
        text("""
            SELECT COALESCE(raw_data->'wikidata'->>'qid', raw_data->>'wikidata_id'),
                   id
            FROM unified_sites
            WHERE raw_data->'wikidata'->>'qid' = ANY(CAST(:qids AS text[]))
               OR raw_data->>'wikidata_id' = ANY(CAST(:qids AS text[]))
        """),
        {"qids": qid_list},
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _run_parent_backfill(conn, rows, site_qids, claims_map, apply: bool) -> None:
    """Backfill parent_site_id from Wikidata P361."""
    print("\n" + "=" * 60)
    print("PARENT SITE BACKFILL (P361)")
    print("=" * 60)

    # Collect all parent QIDs
    parent_qids = set()
    for qid, data in claims_map.items():
        if "part_of_qid" in data:
            parent_qids.add(data["part_of_qid"])

    if not parent_qids:
        print("  No P361 relationships found.")
        return

    print(f"  Looking up {len(parent_qids)} parent QIDs in database...")
    parent_map = _resolve_parent_qids_to_site_ids(conn, parent_qids)
    print(f"  Parents found in DB: {len(parent_map)}")

    rows_by_id = {str(r.id): r for r in rows}
    updates = []
    for site_id_str, qid in site_qids.items():
        data = claims_map.get(qid, {})
        parent_qid = data.get("part_of_qid")
        if not parent_qid:
            continue
        parent_site_id = parent_map.get(parent_qid)
        if not parent_site_id:
            continue
        if site_id_str == str(parent_site_id):
            continue
        row = rows_by_id.get(site_id_str)
        if not row:
            continue
        parent_row = rows_by_id.get(str(parent_site_id))
        parent_name = parent_row.name if parent_row else parent_qid
        updates.append((site_id_str, str(parent_site_id), row.name, parent_name))

    print(f"\n  Sites to link: {len(updates)}")
    for _, _, name, parent_name in updates:
        print(f"    {name}  ->  {parent_name}")

    if updates and apply:
        for site_id_str, parent_site_id, _, _ in updates:
            conn.execute(
                text("UPDATE unified_sites SET parent_site_id = :pid WHERE id = :sid"),
                {"pid": parent_site_id, "sid": site_id_str},
            )
        print(f"  Applied {len(updates)} parent links.")


# ── Metadata validation ──────────────────────────────────────────────


def _run_metadata_validation(conn, rows, site_qids, claims_map, labels: dict, apply: bool) -> list:
    """Validate and optionally fix metadata for ancient_nerds + lyra sites.

    Returns the list of fixes (for the gaps report to account for).
    """
    from pipeline.normalizers.site_type import normalize_site_type
    from pipeline.utils.text import categorize_period

    print("\n" + "=" * 60)
    print("METADATA VALIDATION")
    print("=" * 60)

    rows_by_id = {str(r.id): r for r in rows}

    # Track all discrepancies
    fixes = []  # (site_id, field, old_value, new_value, site_name)
    info_lines = []  # non-actionable notes

    for site_id_str, qid in site_qids.items():
        data = claims_map.get(qid)
        if not data:
            continue
        row = rows_by_id.get(site_id_str)
        if not row:
            continue

        name = row.name

        # ── Period ───────────────────────────────────────────────
        wd_year = data.get("inception_year")
        if wd_year is not None:
            if row.period_start is None:
                # Skip museum/modern founding dates (e.g. Ephesus Museum: 1964)
                # Exception: allow if DB already has a post-1500 period_start
                if wd_year <= 1500:
                    wd_period_name = categorize_period(wd_year)
                    fixes.append((site_id_str, "period_start", None, wd_year, name))
                    if wd_period_name and not row.period_name:
                        fixes.append((site_id_str, "period_name", None, wd_period_name, name))
            else:
                # Flag if Wikidata says a very different period
                db_bucket = categorize_period(row.period_start)
                wd_bucket = categorize_period(wd_year)
                if db_bucket != wd_bucket:
                    info_lines.append(
                        f"  PERIOD  {name}: DB={row.period_start} ({db_bucket}) "
                        f"WD={wd_year} ({wd_bucket})"
                    )

        # ── Site type ────────────────────────────────────────────
        instance_ids = data.get("instance_of", [])
        if instance_ids and not row.site_type:
            for inst_qid in instance_ids:
                label = labels.get(inst_qid)
                if label:
                    resolved = normalize_site_type(label)
                    # normalize_site_type returns title-cased original if unmapped
                    if resolved != label.replace("_", " ").title():
                        fixes.append((site_id_str, "site_type", None, resolved, name))
                        break

    # ── Report ───────────────────────────────────────────────────
    # Group fixes by type
    fix_types: dict[str, list] = {}
    for site_id_str, field, old, new, name in fixes:
        fix_types.setdefault(field, []).append((site_id_str, old, new, name))

    if info_lines:
        print(f"\n  Discrepancies (info only, not auto-fixed):")
        for line in info_lines:
            print(line)

    total_fixes = len(fixes)
    if not total_fixes:
        print("\n  No metadata fixes needed!")
        return fixes

    print(f"\n  Fixes to apply: {total_fixes}")
    for field, items in sorted(fix_types.items()):
        print(f"\n  {field.upper()} ({len(items)} fixes):")
        for site_id_str, old, new, name in items[:30]:
            if old is None:
                print(f"    {name}: (empty) -> {new}")
            else:
                print(f"    {name}: {old} -> {new}")
        if len(items) > 30:
            print(f"    ... and {len(items) - 30} more")

    if not apply:
        return fixes

    # Apply fixes
    applied = 0
    for site_id_str, field, old, new, name in fixes:
        conn.execute(
            text(f"UPDATE unified_sites SET {field} = :val WHERE id = :sid"),
            {"val": new, "sid": site_id_str},
        )
        applied += 1
    print(f"\n  Applied {applied} metadata fixes.")
    return fixes


# ── Gaps report ──────────────────────────────────────────────────────


def _run_gaps_report(rows, site_qids, claims_map, fixes_applied: list | None) -> None:
    """Report sites still missing key metadata after backfill.

    These are candidates for LLM research (MiniMax).
    """
    print("\n" + "=" * 60)
    print("REMAINING GAPS (candidates for AI research)")
    print("=" * 60)

    # If fixes were applied, simulate the new state
    applied_fixes: dict[str, dict] = {}  # site_id -> {field: new_value}
    if fixes_applied:
        for site_id_str, field, _old, new, _name in fixes_applied:
            applied_fixes.setdefault(site_id_str, {})[field] = new

    fields = ["country", "period_start", "site_type"]
    no_qid = []
    no_wikidata_data = []
    gaps: dict[str, list] = {f: [] for f in fields}

    for row in rows:
        sid = str(row.id)

        # Effective values: DB value overridden by pending fix
        effective = {}
        for f in fields:
            db_val = getattr(row, f)
            fix_val = applied_fixes.get(sid, {}).get(f)
            effective[f] = fix_val if fix_val is not None else db_val

        # Sites we couldn't even resolve to a QID
        if sid not in site_qids:
            missing = [f for f in fields if not effective[f]]
            if missing:
                no_qid.append((row.name, row.source_id, missing))
            continue

        # Sites where Wikidata had no data
        qid = site_qids[sid]
        if qid not in claims_map:
            missing = [f for f in fields if not effective[f]]
            if missing:
                no_wikidata_data.append((row.name, row.source_id, missing))
            continue

        # Sites still missing fields after Wikidata backfill
        for f in fields:
            if not effective[f]:
                gaps[f].append((row.name, row.source_id))

    # Print report
    total_gaps = sum(len(v) for v in gaps.values()) + len(no_qid) + len(no_wikidata_data)

    if not total_gaps:
        print("  All sites fully populated!")
        return

    if no_qid:
        print(f"\n  NO WIKIDATA QID ({len(no_qid)} sites — no Wikipedia URL):")
        for name, source, missing in no_qid[:20]:
            print(f"    [{source}] {name}  missing: {', '.join(missing)}")
        if len(no_qid) > 20:
            print(f"    ... and {len(no_qid) - 20} more")

    if no_wikidata_data:
        print(f"\n  QID RESOLVED BUT NO CLAIMS ({len(no_wikidata_data)} sites):")
        for name, source, missing in no_wikidata_data[:20]:
            print(f"    [{source}] {name}  missing: {', '.join(missing)}")
        if len(no_wikidata_data) > 20:
            print(f"    ... and {len(no_wikidata_data) - 20} more")

    for field, items in gaps.items():
        if items:
            print(f"\n  STILL MISSING {field.upper()} ({len(items)} sites — Wikidata has no value):")
            for name, source in items[:20]:
                print(f"    [{source}] {name}")
            if len(items) > 20:
                print(f"    ... and {len(items) - 20} more")

    print(f"\n  Total gaps: {total_gaps}")
    print("  These sites need AI research (MiniMax) to fill remaining fields.")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill parent_site_id and validate metadata from Wikidata"
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--only-parents", action="store_true", help="Only backfill parent_site_id")
    parser.add_argument("--only-metadata", action="store_true", help="Only validate/fix metadata")
    args = parser.parse_args()

    do_parents = not args.only_metadata
    do_metadata = not args.only_parents

    with engine.connect() as conn:
        # Step 1: Get all ancient_nerds + lyra sites
        rows = conn.execute(text("""
            SELECT id, source_id, name, source_url, raw_data,
                   lat, lon, country, period_start, period_end,
                   period_name, site_type, parent_site_id
            FROM unified_sites
            WHERE source_id IN ('ancient_nerds', 'lyra')
            ORDER BY source_id, name
        """)).fetchall()

        print(f"Total sites: {len(rows)}")

        # Step 2: Resolve QIDs
        print("\nResolving Wikidata QIDs...")
        site_qids = _resolve_site_qids(conn, rows)

        if not site_qids:
            print("No QIDs resolved. Done.")
            return

        # Step 3: Fetch claims from Wikidata
        unique_qids = list(set(site_qids.values()))
        print(f"\nFetching Wikidata claims for {len(unique_qids)} QIDs...")
        claims_map = _fetch_wikidata_claims(unique_qids)
        print(f"  Got data for {len(claims_map)} entities")

        # Step 4: Pre-compute label QIDs, then overlap label fetch with parent backfill
        metadata_fixes = []

        # Collect QIDs that need label resolution (instance-of types for site_type)
        label_qids = set()
        for data in claims_map.values():
            for qid in data.get("instance_of", []):
                label_qids.add(qid)

        label_qid_list = list(label_qids)
        print(f"\n  Resolving {len(label_qid_list)} QID labels (instance-of types)...")

        # Kick off label fetch in background while parent backfill runs
        with ThreadPoolExecutor(max_workers=1) as pool:
            label_future = pool.submit(_fetch_qid_labels, label_qid_list) if label_qid_list else None

            if do_parents:
                parent_qids = {
                    sid: qid for sid, qid in site_qids.items()
                    if any(str(r.id) == sid and r.parent_site_id is None for r in rows)
                }
                _run_parent_backfill(conn, rows, parent_qids, claims_map, args.apply)

            labels = label_future.result() if label_future else {}

        if do_metadata:
            metadata_fixes = _run_metadata_validation(conn, rows, site_qids, claims_map, labels, args.apply)

        # Step 5: Gaps report — what's still missing after Wikidata?
        _run_gaps_report(rows, site_qids, claims_map, metadata_fixes)

        if args.apply:
            conn.commit()
            print("\nAll changes committed.")
        else:
            print(f"\nDry run — pass --apply to write changes.")


if __name__ == "__main__":
    main()
