"""Restore ancient_nerds sites from a snapshot file into the database."""

import json
import sys
from pathlib import Path

from sqlalchemy import text

from pipeline.database import get_session


def main():
    snapshot_dir = Path("public/data/snapshots")
    # Use latest snapshot by default, or pass a filename as argument
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        jsons = sorted(snapshot_dir.glob("2026-*.json"))
        if not jsons:
            print("No snapshots found in", snapshot_dir)
            sys.exit(1)
        path = jsons[-1]

    print(f"Loading {path}...")
    data = json.loads(path.read_text(encoding="utf-8"))
    sites = [s for s in data["sites"] if s.get("s") == "ancient_nerds"]
    print(f"Found {len(sites)} ancient_nerds sites")

    if not sites:
        print("Nothing to restore.")
        return

    session = get_session()
    inserted = 0
    for s in sites:
        result = session.execute(
            text("""
                INSERT INTO unified_sites
                    (id, source_id, source_record_id, name, lat, lon,
                     site_type, period_start, period_name, country,
                     description, thumbnail_url, source_url, edited_by)
                VALUES
                    (:id, 'ancient_nerds', :id, :name, :lat, :lon,
                     :type, :period, :pn, :country,
                     :desc, :img, :url, :eb)
                ON CONFLICT (source_id, source_record_id) DO NOTHING
            """),
            dict(
                id=s["id"],
                name=s["n"],
                lat=s["la"],
                lon=s["lo"],
                type=s.get("t"),
                period=s.get("p"),
                pn=s.get("pn"),
                country=s.get("c"),
                desc=s.get("d"),
                img=s.get("i"),
                url=s.get("u"),
                eb=s.get("eb", "initial"),
            ),
        )
        inserted += result.rowcount
    session.commit()
    print(f"Restored {inserted} sites ({len(sites) - inserted} already existed)")


if __name__ == "__main__":
    main()
