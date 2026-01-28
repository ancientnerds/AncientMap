#!/usr/bin/env python3
"""
Re-import Ancient Nerds categories from original GeoJSON.

This script restores the original compound category names (e.g., "City/town/settlement",
"Megalithic stones", "Pyramid complex") that were lost during the initial import due to
category simplification.

The script:
1. Fetches the original GeoJSON from GitHub
2. Builds a mapping of coordinates to original categories
3. Updates the sites JSON with the original compound categories

Usage:
    python scripts/reimport_ancient_nerds.py
"""

import json
import urllib.request
from pathlib import Path
from collections import Counter

# Source URL for original Ancient Nerds data
GEOJSON_URL = "https://raw.githubusercontent.com/matt-cavana/ancient-map/main/cleaned_historical_sites_no_nan.geojson"

# Paths
SITES_JSON_PATH = Path("ancient-nerds-map/public/data/sites/index.json")


def clean_category(cat: str) -> str:
    """
    Clean a category string by fixing common data quality issues.

    Args:
        cat: Raw category string from GeoJSON

    Returns:
        Cleaned category string
    """
    if not cat:
        return "Unknown"

    # Strip whitespace
    cat = cat.strip()

    # Remove trailing commas
    cat = cat.rstrip(",")

    # Fix known typos
    typo_fixes = {
        "City/town/settlemen": "City/town/settlement",
        "Rock Art": "Rock art",
        "Cave structures": "Cave Structures",
        "4th ml. BC": "Unknown",  # Data error
    }

    if cat in typo_fixes:
        cat = typo_fixes[cat]

    return cat if cat else "Unknown"


def fetch_original_geojson() -> dict:
    """
    Fetch the original Ancient Nerds GeoJSON from GitHub.

    Returns:
        Parsed GeoJSON data
    """
    print(f"Fetching original GeoJSON from {GEOJSON_URL}...")

    request = urllib.request.Request(
        GEOJSON_URL,
        headers={"User-Agent": "AncientNerds/1.0"}
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    print(f"  Downloaded {len(data.get('features', []))} features")
    return data


def build_category_map(geojson_data: dict) -> dict:
    """
    Build a mapping from (lat, lon) coordinates to original categories.

    Uses rounded coordinates as keys since the exported JSON rounds to 5 decimal places.

    Args:
        geojson_data: Original GeoJSON data

    Returns:
        Dictionary mapping (lat, lon) tuples to cleaned category names
    """
    print("Building coordinate to category mapping...")

    category_map = {}
    category_counts = Counter()

    for feature in geojson_data.get("features", []):
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        if geometry.get("type") != "Point":
            continue

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue

        lon, lat = coords[0], coords[1]

        # Round to 5 decimal places to match exported JSON
        lat_rounded = round(lat, 5)
        lon_rounded = round(lon, 5)

        # Get and clean the category
        raw_category = properties.get("Category", "")
        cleaned_category = clean_category(raw_category)

        # Store mapping
        key = (lat_rounded, lon_rounded)
        category_map[key] = cleaned_category
        category_counts[cleaned_category] += 1

    print(f"  Found {len(category_counts)} unique categories after cleaning:")
    for cat, count in category_counts.most_common(20):
        print(f"    {cat}: {count}")
    if len(category_counts) > 20:
        print(f"    ... and {len(category_counts) - 20} more")

    return category_map


def update_sites_json(category_map: dict) -> dict:
    """
    Update the sites JSON with original compound categories.

    Args:
        category_map: Mapping from (lat, lon) to category names

    Returns:
        Statistics about the update
    """
    print(f"\nReading sites from {SITES_JSON_PATH}...")

    with open(SITES_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    sites = data["sites"]
    print(f"  Total sites: {len(sites)}")

    # Track statistics
    stats = {
        "total_ancient_nerds": 0,
        "updated": 0,
        "not_found": 0,
        "old_categories": Counter(),
        "new_categories": Counter(),
    }

    # Update ancient_nerds sites
    for site in sites:
        if site.get("s") != "ancient_nerds":
            continue

        stats["total_ancient_nerds"] += 1

        lat = site.get("la")
        lon = site.get("lo")
        old_type = site.get("t", "")

        stats["old_categories"][old_type] += 1

        # Look up original category
        key = (lat, lon)
        if key in category_map:
            new_type = category_map[key]
            site["t"] = new_type
            stats["updated"] += 1
            stats["new_categories"][new_type] += 1
        else:
            stats["not_found"] += 1
            stats["new_categories"][old_type] += 1

    # Save updated JSON
    print(f"\nSaving updated sites to {SITES_JSON_PATH}...")
    with open(SITES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    return stats


def print_summary(stats: dict):
    """Print a summary of the update."""
    print("\n" + "=" * 60)
    print("UPDATE SUMMARY")
    print("=" * 60)

    print(f"\nAncient Nerds sites: {stats['total_ancient_nerds']}")
    print(f"Successfully updated: {stats['updated']}")
    print(f"Not found (kept old): {stats['not_found']}")

    print(f"\nOld categories ({len(stats['old_categories'])} unique):")
    for cat, count in stats["old_categories"].most_common(10):
        print(f"  {cat}: {count}")

    print(f"\nNew categories ({len(stats['new_categories'])} unique):")
    for cat, count in stats["new_categories"].most_common(20):
        print(f"  {cat}: {count}")
    if len(stats["new_categories"]) > 20:
        print(f"  ... and {len(stats['new_categories']) - 20} more")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Re-importing Ancient Nerds Original Categories")
    print("=" * 60)

    # Step 1: Fetch original data
    geojson_data = fetch_original_geojson()

    # Step 2: Build category mapping
    category_map = build_category_map(geojson_data)

    # Step 3: Update sites JSON
    stats = update_sites_json(category_map)

    # Step 4: Print summary
    print_summary(stats)

    print("\nDone! Run 'npm run build' in ancient-nerds-map to verify.")


if __name__ == "__main__":
    main()
