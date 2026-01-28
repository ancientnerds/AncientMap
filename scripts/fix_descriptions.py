#!/usr/bin/env python3
"""
Fix truncated descriptions in sites/index.json by regenerating from source.
"""

import json
from pathlib import Path

# Paths
SOURCE_FILE = Path("data/raw/ancient_nerds/ancient_nerds_original.geojson")
INDEX_FILE = Path("ancient-nerds-map/public/data/sites/index.json")

def main():
    # Load source GeoJSON
    print(f"Loading source: {SOURCE_FILE}")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        source_data = json.load(f)

    # Build lookup of full descriptions by name
    descriptions = {}
    for idx, feature in enumerate(source_data.get("features", [])):
        props = feature.get("properties", {})
        name = props.get("Title", "").strip()
        desc = props.get("Description", "")
        location = props.get("Location", "")
        period = props.get("Period", "")
        source_url = props.get("Source", "")
        image_url = props.get("Images", "")

        if name:
            record_id = f"ancient_nerds_{idx:06d}"
            descriptions[record_id] = {
                "d": desc,  # Full description
                "l": location,
                "p": period,
                "u": source_url,
                "im": image_url,
            }

    print(f"Found {len(descriptions)} sites in source")

    # Load existing index.json
    print(f"Loading index: {INDEX_FILE}")
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    # Update descriptions
    updated = 0
    for site in index_data.get("sites", []):
        site_id = site.get("i", "")
        if site_id in descriptions:
            source_info = descriptions[site_id]
            # Update with full data
            if source_info["d"]:
                site["d"] = source_info["d"]  # Full description
            if source_info["l"]:
                site["l"] = source_info["l"]
            if source_info["p"]:
                site["p"] = source_info["p"]
            if source_info["u"]:
                site["u"] = source_info["u"]
            if source_info["im"]:
                site["im"] = source_info["im"]
            updated += 1

    print(f"Updated {updated} sites")

    # Save updated index
    print(f"Saving updated index: {INDEX_FILE}")
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, separators=(",", ":"), ensure_ascii=False)

    # Also update dist version if it exists
    dist_file = Path("ancient-nerds-map/dist/data/sites/index.json")
    if dist_file.exists():
        print(f"Saving to dist: {dist_file}")
        with open(dist_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, separators=(",", ":"), ensure_ascii=False)

    print("Done!")

    # Verify Inti Punku
    for site in index_data.get("sites", []):
        if "Inti Punku" in site.get("n", ""):
            desc = site.get("d", "")
            print(f"\nInti Punku description length: {len(desc)}")
            print(f"Ends with: ...{desc[-100:]}")
            break

if __name__ == "__main__":
    main()
