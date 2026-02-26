#!/usr/bin/env python3
"""Phase 6: Import enrichment data into the card_stats table.

Reads enrichment output files and upserts metadata into card_stats:
- card_description (from enrichment_verified.json or card_descriptions.json)
- wikidata_qid, confidence_score, source_language
- heritage_designation, inception_year, best_wiki_url, commons_image

Usage:
    python scripts/enrich_import.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from pipeline.database import engine

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _ensure_columns(conn) -> None:
    """Ensure enrichment columns exist on card_stats."""
    columns = [
        ("wikidata_qid", "VARCHAR(20)"),
        ("confidence_score", "DOUBLE PRECISION"),
        ("source_language", "VARCHAR(10)"),
        ("heritage_designation", "TEXT"),
        ("inception_year", "INTEGER"),
        ("best_wiki_url", "VARCHAR(500)"),
        ("commons_image", "VARCHAR(500)"),
    ]
    for col_name, col_type in columns:
        conn.execute(text(f"""
            DO $$
            BEGIN
                ALTER TABLE card_stats ADD COLUMN {col_name} {col_type};
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
        """))
    conn.commit()


def main() -> None:
    # Load enrichment data from all available sources
    qids_data = {}
    claims_data = {}
    wiki_data = {}
    descriptions = {}

    # QIDs
    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    if qids_path.exists():
        with open(qids_path, encoding="utf-8") as f:
            qids_data = json.load(f).get("matches", {})
        print(f"Loaded {len(qids_data)} QID matches", flush=True)

    # Claims
    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    if claims_path.exists():
        with open(claims_path, encoding="utf-8") as f:
            claims_data = json.load(f).get("claims", {})
        print(f"Loaded {len(claims_data)} claim records", flush=True)

    # Wiki articles
    wiki_path = OUTPUT_DIR / "enrichment_wiki.json"
    if wiki_path.exists():
        with open(wiki_path, encoding="utf-8") as f:
            wiki_data = json.load(f).get("articles", {})
        print(f"Loaded {len(wiki_data)} wiki articles", flush=True)

    # Descriptions (try verified first, then standard)
    verified_path = OUTPUT_DIR / "enrichment_verified.json"
    desc_path = OUTPUT_DIR / "card_descriptions.json"
    if verified_path.exists():
        with open(verified_path, encoding="utf-8") as f:
            descriptions = json.load(f).get("descriptions", {})
        print(f"Loaded {len(descriptions)} verified descriptions", flush=True)
    elif desc_path.exists():
        with open(desc_path, encoding="utf-8") as f:
            descriptions = json.load(f).get("descriptions", {})
        print(f"Loaded {len(descriptions)} descriptions", flush=True)

    if not qids_data and not claims_data and not wiki_data and not descriptions:
        print("No enrichment data found. Run enrichment scripts first.")
        sys.exit(1)

    # Collect all site_ids
    all_site_ids = set()
    all_site_ids.update(qids_data.keys())
    all_site_ids.update(claims_data.keys())
    all_site_ids.update(wiki_data.keys())
    all_site_ids.update(descriptions.keys())

    print(f"\nImporting enrichment data for {len(all_site_ids)} sites...", flush=True)

    counts = {
        "description": 0,
        "wikidata_qid": 0,
        "confidence_score": 0,
        "source_language": 0,
        "heritage_designation": 0,
        "inception_year": 0,
        "best_wiki_url": 0,
        "commons_image": 0,
    }

    with engine.connect() as conn:
        _ensure_columns(conn)

        for site_id in all_site_ids:
            updates = {}

            # Description
            desc = descriptions.get(site_id)
            if desc:
                updates["card_description"] = desc

            # QID and confidence
            qid_info = qids_data.get(site_id, {})
            if qid_info.get("qid"):
                updates["wikidata_qid"] = qid_info["qid"]
            if qid_info.get("confidence") is not None:
                updates["confidence_score"] = qid_info["confidence"]

            # Claims
            claim = claims_data.get(site_id, {})
            if claim.get("heritage"):
                updates["heritage_designation"] = claim["heritage"]
            if claim.get("inception") is not None:
                updates["inception_year"] = claim["inception"]
            if claim.get("commons_image"):
                updates["commons_image"] = claim["commons_image"]

            # Wiki article
            wiki = wiki_data.get(site_id, {})
            if wiki.get("lang"):
                updates["source_language"] = wiki["lang"]
            if wiki.get("url"):
                updates["best_wiki_url"] = wiki["url"]

            if not updates:
                continue

            # Build UPDATE SET clause
            set_parts = []
            params = {"site_id": site_id}
            for col, val in updates.items():
                set_parts.append(f"{col} = :{col}")
                params[col] = val

            result = conn.execute(
                text(f"UPDATE card_stats SET {', '.join(set_parts)} WHERE site_id = :site_id"),
                params,
            )
            if result.rowcount > 0:
                for col in updates:
                    counts[col] = counts.get(col, 0) + 1

        conn.commit()

    print(f"\nImport complete!", flush=True)
    print("Updated columns:", flush=True)
    for col, count in sorted(counts.items()):
        if count > 0:
            print(f"  {col}: {count} rows", flush=True)

    # Verify
    with engine.connect() as conn:
        for col in ["wikidata_qid", "confidence_score", "source_language",
                     "heritage_designation", "inception_year", "best_wiki_url", "commons_image"]:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM card_stats WHERE {col} IS NOT NULL")
            ).scalar()
            print(f"  Total with {col}: {count}", flush=True)


if __name__ == "__main__":
    main()
