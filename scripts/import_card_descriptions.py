#!/usr/bin/env python3
"""Import generated card descriptions into the card_stats table.

Reads output/card_descriptions.json and upserts card_stats.card_description
for each site_id present. Creates a minimal card_stats row if one doesn't
exist yet (e.g. for sites without hero images that haven't had stats generated).

Usage:
    python scripts/import_card_descriptions.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from pipeline.database import engine


def main() -> None:
    desc_path = Path(__file__).parent.parent / "output" / "card_descriptions.json"

    if not desc_path.exists():
        print(f"Error: {desc_path} not found. Run card description generation first.")
        sys.exit(1)

    with open(desc_path, encoding="utf-8") as f:
        data = json.load(f)

    descriptions = data.get("descriptions", {})
    if not descriptions:
        print("No descriptions found in file.")
        sys.exit(1)

    updated = 0
    skipped = 0
    with engine.connect() as conn:
        for site_id, desc in descriptions.items():
            result = conn.execute(
                text("UPDATE card_stats SET card_description = :desc WHERE site_id = :id"),
                {"desc": desc, "id": site_id},
            )
            if result.rowcount > 0:
                updated += 1
            else:
                skipped += 1
        conn.commit()

    if skipped:
        print(f"Warning: {skipped} site_ids not found in card_stats (run generate_stats first).")
    print(f"Updated {updated} / {len(descriptions)} card descriptions.")

    # Verify
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM card_stats WHERE card_description IS NOT NULL")
        ).scalar()
        print(f"Total cards with descriptions: {count}")


if __name__ == "__main__":
    main()
