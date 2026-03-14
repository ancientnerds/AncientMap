#!/usr/bin/env python3
"""Re-index wiki_images from files on disk.

Scans public/data/images/wiki/ directories, matches the 8-char directory
names back to unified_sites UUIDs, and inserts hero.webp records into
the wiki_images table.

Usage:
    # On VPS:
    cd /var/www/ancientnerds
    python3 scripts/reindex_wiki_images.py

    # Dry run (no DB changes):
    python3 scripts/reindex_wiki_images.py --dry-run

    # Custom image directory:
    python3 scripts/reindex_wiki_images.py --image-dir /path/to/images/wiki
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Re-index wiki_images from disk")
    parser.add_argument(
        "--image-dir",
        default="public/data/images/wiki",
        help="Path to wiki image directories (default: public/data/images/wiki)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB changes")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    if not image_dir.exists():
        print(f"ERROR: {image_dir} does not exist")
        sys.exit(1)

    # Collect all directories with hero.webp
    print(f"Scanning {image_dir}...")
    dirs = sorted(d for d in image_dir.iterdir() if d.is_dir())
    print(f"Found {len(dirs)} site directories")

    hero_dirs = []
    for d in dirs:
        hero = d / "hero.webp"
        if hero.exists():
            hero_dirs.append((d.name, hero))

    print(f"Found {len(hero_dirs)} directories with hero.webp")

    if not hero_dirs:
        print("Nothing to index.")
        return

    # Match short hashes to site UUIDs
    from sqlalchemy import text

    from pipeline.database import get_session

    print("Matching directory names to site UUIDs...")

    with get_session() as session:
        # Build a mapping: short_hash → (site_id, site_name)
        # The directory name is the first 8 chars of the UUID without dashes
        result = session.execute(
            text("SELECT id::text, name, replace(id::text, '-', '') AS flat_id FROM unified_sites")
        )
        hash_to_site: dict[str, tuple[str, str]] = {}
        for row in result:
            short = row.flat_id[:8]
            hash_to_site[short] = (row.id, row.name)

    matched = 0
    unmatched = 0
    inserts = []
    for short_hash, hero_path in hero_dirs:
        if short_hash in hash_to_site:
            site_id, site_name = hash_to_site[short_hash]
            file_size = hero_path.stat().st_size
            inserts.append(
                {
                    "site_id": site_id,
                    "filename": "hero.webp",
                    "original_url": f"/data/images/wiki/{short_hash}/hero.webp",
                    "title": site_name,
                    "is_hero": True,
                    "is_lead": True,
                    "sort_order": 0,
                    "source_type": "wikimedia",
                    "file_size_bytes": file_size,
                }
            )
            matched += 1
        else:
            unmatched += 1

    print(f"Matched: {matched}, Unmatched: {unmatched}")

    if args.dry_run:
        print(f"\nDRY RUN: Would insert {len(inserts)} rows into wiki_images")
        for ins in inserts[:5]:
            print(f"  {ins['site_id'][:8]}... → {ins['title']}")
        if len(inserts) > 5:
            print(f"  ... and {len(inserts) - 5} more")
        return

    # Insert into wiki_images
    print(f"\nInserting {len(inserts)} rows into wiki_images...")
    with get_session() as session:
        # Clear existing (in case of partial re-index)
        session.execute(text("DELETE FROM wiki_images"))
        session.commit()

        inserted = 0
        for i in range(0, len(inserts), args.batch_size):
            batch = inserts[i : i + args.batch_size]
            for row in batch:
                session.execute(
                    text(
                        "INSERT INTO wiki_images "
                        "(site_id, filename, original_url, title, is_hero, is_lead, "
                        "sort_order, source_type, file_size_bytes) "
                        "VALUES (CAST(:site_id AS uuid), :filename, :original_url, "
                        ":title, :is_hero, :is_lead, :sort_order, :source_type, :file_size_bytes)"
                    ),
                    row,
                )
                inserted += 1
            session.commit()
            print(f"  {inserted}/{len(inserts)}...", flush=True)

    print(f"\nDone! Inserted {inserted} hero images into wiki_images.")
    print("Sites will now show images in popups and Lyra chat.")


if __name__ == "__main__":
    main()
