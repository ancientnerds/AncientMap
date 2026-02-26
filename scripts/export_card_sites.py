#!/usr/bin/env python3
"""Export Ancient Nerds sites for card description generation.

Queries all ancient_nerds sites that have a description, exports to
output/card_sites.json with the fields needed for description generation.

Usage:
    python scripts/export_card_sites.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from pipeline.database import engine


def main() -> None:
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "card_sites.json"

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                us.id::text AS site_id,
                us.name,
                us.period_name,
                us.period_start,
                us.site_type,
                us.country,
                LEFT(us.description, 500) AS description
            FROM unified_sites us
            WHERE us.source_id = 'ancient_nerds'
              AND us.description IS NOT NULL
              AND us.description != ''
            ORDER BY us.name
        """)).fetchall()

    sites = []
    for row in rows:
        sites.append({
            "site_id": row.site_id,
            "name": row.name,
            "period_name": row.period_name,
            "period_start": row.period_start,
            "site_type": row.site_type,
            "country": row.country,
            "description": row.description,
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sites, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(sites)} card sites to {output_path}")


if __name__ == "__main__":
    main()
