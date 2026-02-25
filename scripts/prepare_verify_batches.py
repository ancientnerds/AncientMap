#!/usr/bin/env python3
"""Prepare batch files for Phase 2 verification agents."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

NUM_BATCHES = 10


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    with open(OUTPUT / "card_descriptions.json", encoding="utf-8") as f:
        descs = json.load(f)["descriptions"]

    with open(OUTPUT / "card_sites.json", encoding="utf-8") as f:
        sites_list = json.load(f)
    sites = {s["site_id"]: s for s in sites_list}

    with open(OUTPUT / "verification_flags.json", encoding="utf-8") as f:
        flags = json.load(f)

    flagged_ids = set(flags["flagged"].keys())
    all_ids = list(descs.keys())

    # Split into batches
    batch_size = len(all_ids) // NUM_BATCHES
    batches = []
    for i in range(NUM_BATCHES):
        start = i * batch_size
        end = start + batch_size if i < NUM_BATCHES - 1 else len(all_ids)
        batches.append(all_ids[start:end])

    # Write batch files
    for i, batch_ids in enumerate(batches):
        batch_data = {
            "batch_index": i,
            "banned_openers": list(flags["banned_openers"].keys()),
            "overused_4grams": list(flags["overused_4grams"].keys()),
            "sites": [],
        }

        flagged_in_batch = 0
        clean_in_batch = 0

        for sid in batch_ids:
            site = sites.get(sid, {})
            entry = {
                "site_id": sid,
                "name": site.get("name", "?"),
                "period_name": site.get("period_name", "?"),
                "period_start": site.get("period_start", 0),
                "site_type": site.get("site_type", "?"),
                "country": site.get("country", "?"),
                "wiki_text": site.get("description", ""),
                "current_description": descs.get(sid, ""),
                "flagged": sid in flagged_ids,
                "issues": flags["flagged"][sid]["issues"] if sid in flagged_ids else [],
            }
            batch_data["sites"].append(entry)

            if sid in flagged_ids:
                flagged_in_batch += 1
            else:
                clean_in_batch += 1

        out_path = OUTPUT / f"verify_batch_{i:02d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)

        print(f"Batch {i}: {len(batch_ids)} sites ({flagged_in_batch} flagged, {clean_in_batch} clean) → {out_path.name}")

    print(f"\nTotal: {len(all_ids)} sites across {NUM_BATCHES} batches")


if __name__ == "__main__":
    main()
