#!/usr/bin/env python3
"""Re-index wiki_images from files on disk.

Scans public/data/images/wiki/ directories, matches the 8-char directory
names back to unified_sites UUIDs, and inserts records for ALL .webp files
(hero + gallery) into the wiki_images table.

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

    # Collect all directories with .webp files
    print(f"Scanning {image_dir}...")
    dirs = sorted(d for d in image_dir.iterdir() if d.is_dir())
    print(f"Found {len(dirs)} site directories")

    # Collect (dir_name, list of webp files) for each directory
    site_images: list[tuple[str, list[Path]]] = []
    total_images = 0
    for d in dirs:
        webps = sorted(d.glob("*.webp"))
        if webps:
            site_images.append((d.name, webps))
            total_images += len(webps)

    print(f"Found {len(site_images)} directories with images ({total_images} total .webp files)")

    if not site_images:
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
    for short_hash, webp_files in site_images:
        if short_hash in hash_to_site:
            site_id, site_name = hash_to_site[short_hash]
            for sort_idx, img_path in enumerate(webp_files):
                is_hero = img_path.name == "hero.webp"
                # Sort hero first (sort_order=0), then gallery by filename
                file_size = img_path.stat().st_size
                title = site_name if is_hero else img_path.stem.replace("_", " ")
                inserts.append(
                    {
                        "site_id": site_id,
                        "filename": img_path.name,
                        "original_url": f"/data/images/wiki/{short_hash}/{img_path.name}",
                        "title": title,
                        "is_hero": is_hero,
                        "is_lead": is_hero,
                        "sort_order": 0 if is_hero else sort_idx + 1,
                        "source_type": "wikimedia",
                        "file_size_bytes": file_size,
                    }
                )
            matched += 1
        else:
            unmatched += 1

    print(f"Matched: {matched}, Unmatched: {unmatched}")
    print(f"Total images to insert: {len(inserts)}")

    if args.dry_run:
        print(f"\nDRY RUN: Would insert {len(inserts)} rows into wiki_images")
        # Show a few sites with their image counts
        from collections import Counter

        site_counts = Counter(ins["site_id"][:8] for ins in inserts)
        for sid, count in list(site_counts.items())[:5]:
            title = next(ins["title"] for ins in inserts if ins["site_id"][:8] == sid and ins["is_hero"])
            print(f"  {sid}... → {title} ({count} images)")
        if len(site_counts) > 5:
            print(f"  ... and {len(site_counts) - 5} more sites")
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

    print(f"\nDone! Inserted {inserted} images ({matched} sites) into wiki_images.")
    print("Sites will now show images in popups and Lyra chat.")


if __name__ == "__main__":
    main()
