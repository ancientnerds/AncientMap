"""Draw the frozen 200-image measurement set, stratified by T10's tier.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/make_sample.py

Out: `output/remediation/vlm_pilot/SAMPLE.jsonl` - 200 records, 50 per tier,
sheet index 0..49 = the tile index on that tier's contact sheet.

The frame (stated, because it is a choice):

  * one row per T10 finding (`output/remediation/run_t10/findings.jsonl`, 49,691
    rows) whose tier is A, B, C or D;
  * `is_excluded` false - the excluded rows never reach a site page, and T10's
    own report prints the non-excluded population next to the total;
  * the row resolves to an existing file with exact case in the offsite tree
    (main tree first, then `images-case-collisions/`);
  * no other `wiki_images` row shares this (shard, filename) pair, so the bytes
    on disk are unambiguously this row's; and
  * the file starts with `RIFF` + `WEBP`.

Refuses to write if T10's per-tier volumes do not match the numbers its own
report prints (`output/remediation/t10_scratch/REPORT.md` section 2), so a
stale or different findings file cannot silently become the measurement set.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    OFFSITE_CASE_COLLISIONS,
    OFFSITE_IMAGES,
    OUT_DIR,
    T10_FINDINGS,
    build_tree,
    card_descriptions,
    image_rows,
    image_url,
    is_webp,
    read_jsonl,
    resolve,
    shard_for,
    site_names,
    write_jsonl,
)

SEED = 20260921
PER_TIER = 50
TIERS = ("A", "B", "C", "D")

#: T10's own measured volumes (`output/remediation/t10_scratch/REPORT.md` section 2,
#: table "tier | T10 | plan"). A mismatch means the findings file is not the run
#: the report describes, and the sample must not be drawn from it.
T10_ROW_TOTALS = {"A": 3858, "B": 9559, "C": 25569, "D": 10705}
T10_TOTAL = 49691


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(OUT_DIR / "SAMPLE.jsonl"),
        help="where to write the sample (the selftest regenerates to a temp file to prove "
        "the draw is reproducible)",
    )
    args = parser.parse_args()

    findings = list(read_jsonl(T10_FINDINGS))
    counts: dict[str, int] = {}
    for finding in findings:
        tier = finding["current_value"]["tier"]
        counts[tier] = counts.get(tier, 0) + 1
    print(f"T10 findings: {len(findings)} rows, tiers {counts}")
    if len(findings) != T10_TOTAL or counts != T10_ROW_TOTALS:
        raise SystemExit(
            "REFUSING: the findings file does not match the volumes in T10's REPORT.md - "
            f"rows {len(findings)} (report {T10_TOTAL}), tiers {counts} (report {T10_ROW_TOTALS})"
        )

    tree = build_tree(OFFSITE_IMAGES)
    collisions = build_tree(OFFSITE_CASE_COLLISIONS)
    names = site_names()
    cards = card_descriptions()
    images = image_rows()

    # (shard, filename) pairs used by more than one row: the bytes are shared, so a
    # row among them cannot own them. 3 pairs exist (two `hero.webp`, one `excluded`).
    seen: dict[tuple[str, str], int] = {}
    for finding in findings:
        key = (shard_for(finding["site_id"]), finding["current_value"]["filename"])
        seen[key] = seen.get(key, 0) + 1

    frames: dict[str, list[dict]] = {tier: [] for tier in TIERS}
    rejected: dict[str, int] = {}
    for finding in findings:
        tier = finding["current_value"]["tier"]
        if tier not in frames:
            continue
        current = finding["current_value"]
        if current["is_excluded"]:
            rejected["is_excluded"] = rejected.get("is_excluded", 0) + 1
            continue
        site_id = finding["site_id"]
        filename = current["filename"]
        if seen[(shard_for(site_id), filename)] > 1:
            rejected["filename_shared_by_rows"] = rejected.get("filename_shared_by_rows", 0) + 1
            continue
        hit = resolve(tree, site_id, filename)
        path = OFFSITE_IMAGES / shard_for(site_id) / filename
        if hit is None:
            hit = resolve(collisions, site_id, filename)
            path = OFFSITE_CASE_COLLISIONS / shard_for(site_id) / filename
        if hit is None:
            rejected["no_file_on_disk"] = rejected.get("no_file_on_disk", 0) + 1
            continue
        if not is_webp(path)[0]:
            rejected["not_webp"] = rejected.get("not_webp", 0) + 1
            continue
        frames[tier].append(
            {
                "finding": finding,
                "current": current,
                "path": path,
                "disk_size": hit[1],
                "site_id": site_id,
                "filename": filename,
            }
        )
    print(f"frame sizes per tier: { {t: len(v) for t, v in frames.items()} }")
    print(f"rows dropped from the frame: {rejected}")

    rng = random.Random(SEED)
    records: list[dict] = []
    for tier in TIERS:
        pool = sorted(frames[tier], key=lambda f: f["current"]["image_id"])
        if len(pool) < PER_TIER:
            raise SystemExit(f"REFUSING: tier {tier} frame has only {len(pool)} rows")
        drawn = sorted(rng.sample(pool, PER_TIER), key=lambda f: f["current"]["image_id"])
        for index, item in enumerate(drawn):
            current = item["current"]
            site_id = item["site_id"]
            row = images[current["image_id"]]
            records.append(
                {
                    "sheet_index": index,
                    "tier": tier,
                    "tier_label": current["tier_label"],
                    "tier_reason": current["reason"],
                    "image_id": current["image_id"],
                    "site_id": site_id,
                    "site_name": names.get(site_id, ""),
                    "filename": item["filename"],
                    "title": row.get("title"),
                    "card_text": cards.get(site_id, ""),
                    "original_url": row.get("original_url"),
                    "is_hero": current["is_hero"],
                    "shard": shard_for(site_id),
                    "shard_dir": str(item["path"].parent),
                    "local_file_path": str(item["path"]),
                    "file_size": item["disk_size"],
                    "url_path": image_url(site_id, item["filename"]),
                    "signals": current["signals"],
                    "signals_note": (
                        "T10 signals for this row: P ('in the site's P373 Commons category', "
                        "null = could not be proven), F (own site name absent from "
                        "title+filename+Commons name), S (same Commons file on a differently "
                        "named site), A (museum word), D (place token > 50 km), E (non-photo "
                        "word), B (museum city - unavailable in T10, always null)"
                    ),
                }
            )

    out = Path(args.out)
    write_jsonl(out, records)
    print(f"\nwrote {out}: {len(records)} records, seed {SEED}")
    for tier in TIERS:
        ids = [r["image_id"] for r in records if r["tier"] == tier]
        print(f"  tier {tier}: 50 images, ids {min(ids)}..{max(ids)}, sheets {tier}00..{tier}49")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
