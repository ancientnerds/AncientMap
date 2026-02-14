"""Backfill parent_site_id on unified_sites using Wikidata P361 (part-of).

Targets ancient_nerds and lyra sources only.

For each site:
1. Resolve its Wikidata QID (from raw_data, source_url, or linked contribution)
2. Fetch P361 (part-of) from Wikidata
3. If the parent QID matches an existing site in our DB, set parent_site_id

Usage:
    python scripts/backfill_parent_sites.py          # dry-run (default)
    python scripts/backfill_parent_sites.py --apply   # apply changes
"""

import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from sqlalchemy import text

from pipeline.database import engine
from pipeline.utils.http import fetch_with_retry

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# Max QIDs per wbgetentities call (Wikidata limit is 50)
BATCH_SIZE = 50


def _wikipedia_url_to_title(url: str) -> str | None:
    """Extract the article title from a Wikipedia URL."""
    if not url:
        return None
    m = re.search(r"wikipedia\.org/wiki/(.+?)(?:#|\?|$)", url)
    if m:
        return urllib.parse.unquote(m.group(1)).replace("_", " ")
    return None


def _resolve_titles_to_qids(titles: list[str]) -> dict[str, str]:
    """Resolve Wikipedia article titles to Wikidata QIDs via the Wikipedia API.

    Returns {title: qid} for successfully resolved titles.
    """
    result = {}
    # Wikipedia API also has a 50-title limit per call
    for i in range(0, len(titles), BATCH_SIZE):
        batch = titles[i : i + BATCH_SIZE]
        try:
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
        except Exception as e:
            print(f"  Wikipedia API error: {e}")
            continue

        pages = data.get("query", {}).get("pages", {})
        # Build normalized-title → original-title map for matching
        normalized = data.get("query", {}).get("normalized", [])
        norm_map = {n["to"]: n["from"] for n in normalized}

        for page in pages.values():
            if page.get("missing") is not None:
                continue
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                page_title = page["title"]
                # Map back to the original title we submitted
                original = norm_map.get(page_title, page_title)
                result[original] = qid

        if i + BATCH_SIZE < len(titles):
            time.sleep(0.5)  # be nice to Wikipedia

    return result


def _fetch_p361_batch(qids: list[str]) -> dict[str, str]:
    """Fetch P361 (part-of) for a batch of Wikidata QIDs.

    Returns {qid: parent_qid} for QIDs that have P361.
    """
    result = {}
    for i in range(0, len(qids), BATCH_SIZE):
        batch = qids[i : i + BATCH_SIZE]
        try:
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
        except Exception as e:
            print(f"  Wikidata API error: {e}")
            continue

        for qid, entity in data.get("entities", {}).items():
            claims = entity.get("claims", {})
            p361 = claims.get("P361", [])
            if p361:
                parent_id = (
                    p361[0]
                    .get("mainsnak", {})
                    .get("datavalue", {})
                    .get("value", {})
                    .get("id")
                )
                if parent_id:
                    result[qid] = parent_id

        if i + BATCH_SIZE < len(qids):
            time.sleep(0.5)  # be nice to Wikidata

    return result


def _resolve_parent_qids_to_site_ids(conn, parent_qids: set[str]) -> dict[str, str]:
    """Look up parent Wikidata QIDs in unified_sites.

    Returns {parent_qid: site_id} for parents that exist in our DB.
    """
    if not parent_qids:
        return {}

    result = {}
    for qid in parent_qids:
        row = conn.execute(
            text("""
                SELECT id FROM unified_sites
                WHERE raw_data->'wikidata'->>'qid' = :qid
                   OR raw_data->>'wikidata_id' = :qid
                LIMIT 1
            """),
            {"qid": qid},
        ).fetchone()
        if row:
            result[qid] = row[0]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill parent_site_id from Wikidata P361")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    with engine.connect() as conn:
        # Step 1: Get all ancient_nerds + lyra sites without a parent
        rows = conn.execute(text("""
            SELECT id, source_id, name, source_url, raw_data
            FROM unified_sites
            WHERE source_id IN ('ancient_nerds', 'lyra')
              AND parent_site_id IS NULL
            ORDER BY source_id, name
        """)).fetchall()

        print(f"Found {len(rows)} sites without parent_site_id\n")

        # Step 2: Resolve each site to a Wikidata QID
        # site_id → qid
        site_qids: dict[str, str] = {}
        # Titles we need to resolve via Wikipedia API (ancient_nerds sites)
        titles_to_resolve: dict[str, list[str]] = {}  # title → [site_id, ...]

        for row in rows:
            site_id, source_id, name, source_url, raw_data = row
            raw = raw_data or {}

            # Try raw_data paths first
            qid = raw.get("wikidata", {}).get("qid") if isinstance(raw.get("wikidata"), dict) else None
            if not qid:
                qid = raw.get("wikidata_id")

            if qid:
                site_qids[str(site_id)] = qid
                continue

            # For ancient_nerds: resolve Wikipedia URL → title → QID
            title = _wikipedia_url_to_title(source_url)
            if title:
                titles_to_resolve.setdefault(title, []).append(str(site_id))

        # Also check user_contributions for lyra sites missing QID in raw_data
        lyra_missing = [
            str(r.id) for r in rows
            if r.source_id == "lyra" and str(r.id) not in site_qids
        ]
        if lyra_missing:
            # Resolve from user_contributions.wikidata_id via promoted_site_id
            contrib_rows = conn.execute(text("""
                SELECT promoted_site_id, wikidata_id
                FROM user_contributions
                WHERE promoted_site_id = ANY(:ids)
                  AND wikidata_id IS NOT NULL
            """), {"ids": lyra_missing}).fetchall()
            for crow in contrib_rows:
                site_qids[str(crow[0])] = crow[1]

        print(f"QIDs from raw_data/contributions: {len(site_qids)}")
        print(f"Wikipedia titles to resolve: {len(titles_to_resolve)}")

        # Step 3: Resolve Wikipedia titles → QIDs
        if titles_to_resolve:
            print("Resolving Wikipedia titles to Wikidata QIDs...")
            title_qids = _resolve_titles_to_qids(list(titles_to_resolve.keys()))
            for title, qid in title_qids.items():
                for sid in titles_to_resolve[title]:
                    site_qids[sid] = qid
            print(f"  Resolved {len(title_qids)} titles → total QIDs: {len(site_qids)}")

        if not site_qids:
            print("No QIDs to look up. Done.")
            return

        # Step 4: Fetch P361 (part-of) from Wikidata
        print(f"\nFetching P361 for {len(site_qids)} QIDs...")
        all_qids = list(set(site_qids.values()))
        p361_map = _fetch_p361_batch(all_qids)
        print(f"  Sites with P361 (part-of): {len(p361_map)}")

        if not p361_map:
            print("No sites have P361 relationships. Done.")
            return

        # Step 5: Resolve parent QIDs to existing sites in our DB
        parent_qids = set(p361_map.values())
        print(f"\nLooking up {len(parent_qids)} parent QIDs in our database...")
        parent_map = _resolve_parent_qids_to_site_ids(conn, parent_qids)
        print(f"  Parents found in DB: {len(parent_map)}")

        # Step 6: Build updates
        updates = []  # (site_id, parent_site_id, site_name, parent_qid)
        for site_id, qid in site_qids.items():
            parent_qid = p361_map.get(qid)
            if not parent_qid:
                continue
            parent_site_id = parent_map.get(parent_qid)
            if not parent_site_id:
                continue
            # Don't set a site as its own parent
            if site_id == str(parent_site_id):
                continue
            site_name = next(r.name for r in rows if str(r.id) == site_id)
            updates.append((site_id, str(parent_site_id), site_name, parent_qid))

        print(f"\n{'=' * 60}")
        print(f"Sites to update: {len(updates)}")
        print(f"{'=' * 60}\n")

        for site_id, parent_site_id, site_name, parent_qid in updates:
            parent_name = next(
                (r.name for r in rows if str(r.id) == parent_site_id),
                parent_qid,
            )
            print(f"  {site_name} → {parent_name}")

        if not updates:
            print("Nothing to update. Done.")
            return

        if not args.apply:
            print(f"\nDry run — pass --apply to write {len(updates)} updates.")
            return

        # Apply
        for site_id, parent_site_id, _, _ in updates:
            conn.execute(
                text("UPDATE unified_sites SET parent_site_id = :pid WHERE id = :sid"),
                {"pid": parent_site_id, "sid": site_id},
            )
        conn.commit()
        print(f"\nDone — updated {len(updates)} sites.")


if __name__ == "__main__":
    main()
