"""Prove the `wiki_images` row -> image file mapping on the offsite copy.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/prove_mapping.py

Writes `output/remediation/vlm_pilot/MAPPING_PROOF.json` and prints the numbers.
Nothing is written outside `output/remediation/vlm_pilot/`; the image trees and
the database are read-only here (the database not at all - the input is the
frozen snapshot `output/remediation/snapshot/wiki_images.jsonl.gz`).

Four independent checks, all on the real files:

1. **Resolution.** Every one of the 49,691 snapshot rows is resolved to
   `<offsite>/images/wiki/<site_id[:8]>/<filename>`, exact case, against a
   directory listing.
2. **Bytes.** Every resolved file's header is read: `RIFF` at 0, `WEBP` at 8,
   and size > 0.
3. **Size.** The file's size on disk against the row's own `file_size_bytes`.
4. **Second artifact.** The offsite `images/index.json` - an export of the same
   table, written by a different code path - must agree on the path for every
   entry it carries.

The seed for the 24-row hand-check sample is quoted in the output and in
METHOD.md; the sample is drawn from all rows, misses included, so it cannot
flatter the rule.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    OFFSITE_CASE_COLLISIONS,
    OFFSITE_IMAGES,
    OFFSITE_ROOT,
    OUT_DIR,
    WIKI_IMAGES_SNAPSHOT,
    build_tree,
    image_url,
    is_webp,
    read_jsonl_gz,
    shard_for,
)

PROOF_SEED = 20260921
PROOF_SAMPLE_SIZE = 24


def main() -> int:
    out_path = OUT_DIR / "MAPPING_PROOF.json"
    print(f"image tree  : {OFFSITE_IMAGES}")
    print(f"collisions  : {OFFSITE_CASE_COLLISIONS}")
    print(f"snapshot    : {WIKI_IMAGES_SNAPSHOT}")

    tree = build_tree(OFFSITE_IMAGES)
    collisions = build_tree(OFFSITE_CASE_COLLISIONS)
    disk_files = sum(len(v) for v in tree.values())
    print(f"tree        : {len(tree)} shards, {disk_files} files")
    print(f"collisions  : {len(collisions)} shards, {sum(len(v) for v in collisions.values())} files")

    rows = list(read_jsonl_gz(WIKI_IMAGES_SNAPSHOT))
    print(f"snapshot rows: {len(rows)}")

    resolved = 0
    collision_hits: list[dict[str, object]] = []
    misses: list[dict[str, object]] = []
    size_equal = size_diff = size_null = 0
    size_diffs: list[dict[str, object]] = []
    magic_bad: list[dict[str, object]] = []
    magic_checked = 0
    empty_files: list[str] = []
    used_paths: dict[tuple[str, str], list[int]] = {}

    for row in rows:
        site_id = row["site_id"]
        filename = row["filename"]
        shard = shard_for(site_id)
        used_paths.setdefault((shard, filename), []).append(row["id"])
        hit = tree.get(shard, {}).get(filename)
        if hit is None:
            alt = collisions.get(shard, {}).get(filename)
            if alt is not None:
                collision_hits.append(
                    {
                        "image_id": row["id"],
                        "site_id": site_id,
                        "filename": filename,
                        "path": str(OFFSITE_CASE_COLLISIONS / shard / filename),
                        "size": alt,
                        "db_file_size_bytes": row["file_size_bytes"],
                    }
                )
                resolved += 1
                path = OFFSITE_CASE_COLLISIONS / shard / filename
            else:
                misses.append(
                    {
                        "image_id": row["id"],
                        "site_id": site_id,
                        "shard": shard,
                        "filename": filename,
                        "db_file_size_bytes": row["file_size_bytes"],
                        "db_title": row["title"],
                        "db_original_url": row["original_url"],
                        "is_excluded": row["is_excluded"],
                    }
                )
                continue
        else:
            resolved += 1
            path = OFFSITE_IMAGES / shard / filename

        magic_checked += 1
        ok, head_hex = is_webp(path)
        if not ok:
            magic_bad.append({"image_id": row["id"], "path": str(path), "head_hex": head_hex})
        if hit == 0 or not path.stat().st_size:
            empty_files.append(str(path))
        db_size = row["file_size_bytes"]
        if db_size is None:
            size_null += 1
        elif db_size == path.stat().st_size:
            size_equal += 1
        else:
            size_diff += 1
            if len(size_diffs) < 20:
                size_diffs.append(
                    {
                        "image_id": row["id"],
                        "site_id": site_id,
                        "filename": filename,
                        "db_file_size_bytes": db_size,
                        "disk_file_size": path.stat().st_size,
                    }
                )

    duplicates = {f"{k[0]}/{k[1]}": v for k, v in used_paths.items() if len(v) > 1}

    print(f"\n[1] resolution  : {resolved}/{len(rows)} rows resolve, {len(misses)} do not")
    print(f"    of which via images-case-collisions/: {len(collision_hits)}")
    print(f"[2] webp header : {magic_checked - len(magic_bad)}/{magic_checked} are RIFF....WEBP")
    print(f"    empty files : {len(empty_files)}")
    print(
        f"[3] size        : equal {size_equal}, differ {size_diff}, "
        f"null in db {size_null} (of {resolved} resolved)"
    )
    print(f"    rows sharing one (shard, filename) pair: {len(duplicates)} pairs -> {list(duplicates)}")

    # --- Check 4: the independent index.json export -------------------------
    index_path = OFFSITE_ROOT / "images" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entries = 0
    index_path_ok = index_path_ok_shard = 0
    index_path_bad: list[str] = []
    index_in_snapshot = 0
    index_missing_on_disk: list[str] = []
    index_not_in_snapshot: list[str] = []
    snapshot_keys = {(shard_for(r["site_id"]), r["filename"]) for r in rows}
    for site_id, images in index.items():
        for img in images:
            entries += 1
            shard = shard_for(site_id)
            expected = image_url(site_id, img["f"])
            if img["p"] == expected:
                index_path_ok += 1
            else:
                if len(index_path_bad) < 5:
                    index_path_bad.append(f"{img['p']} != {expected}")
            if tree.get(shard, {}).get(img["f"]) is not None:
                index_path_ok_shard += 1
            elif len(index_missing_on_disk) < 10:
                index_missing_on_disk.append(f"{shard}/{img['f']}")
            if (shard, img["f"]) in snapshot_keys:
                index_in_snapshot += 1
            elif len(index_not_in_snapshot) < 10:
                index_not_in_snapshot.append(f"{shard}/{img['f']}")
    print(f"\n[4] images/index.json ({index_path}):")
    print(f"    {entries} entries over {len(index)} sites")
    print(f"    path field == /data/images/wiki/<site_id[:8]>/<f>: {index_path_ok}/{entries}")
    print(f"    f resolves on disk in the shard keyed by the site UUID: {index_path_ok_shard}/{entries}")
    print(f"      not on disk: {index_missing_on_disk}")
    print(f"    (site, filename) also present in the snapshot: {index_in_snapshot}/{entries}")
    print(f"      not in snapshot: {index_not_in_snapshot}")
    if index_path_bad:
        print(f"    mismatches: {index_path_bad}")

    # --- The hand-checked sample -------------------------------------------
    rng = random.Random(PROOF_SEED)  # noqa: S311 - a reproducible sample draw, not cryptography
    sample = rng.sample(sorted(rows, key=lambda r: r["id"]), PROOF_SAMPLE_SIZE)
    proof: list[dict[str, object]] = []
    for row in sample:
        site_id = row["site_id"]
        filename = row["filename"]
        shard = shard_for(site_id)
        main_path = OFFSITE_IMAGES / shard / filename
        coll_path = OFFSITE_CASE_COLLISIONS / shard / filename
        if tree.get(shard, {}).get(filename) is not None:
            path, where = main_path, "images/wiki"
        elif collisions.get(shard, {}).get(filename) is not None:
            path, where = coll_path, "images-case-collisions/wiki"
        else:
            path, where = None, "NOT RESOLVED"
        record: dict[str, object] = {
            "image_id": row["id"],
            "site_id": site_id,
            "shard": shard,
            "filename": filename,
            "db_file_size_bytes": row["file_size_bytes"],
            "resolved_path": str(path) if path else None,
            "resolved_in": where,
            "is_hero": row["is_hero"],
            "db_title": row["title"],
        }
        if path is not None:
            ok, head_hex = is_webp(path)
            record["disk_file_size"] = path.stat().st_size
            record["head12_hex"] = head_hex
            record["is_riff_webp"] = ok
            record["size_matches_db"] = path.stat().st_size == row["file_size_bytes"]
        proof.append(record)

    print(f"\n[hand-check] {PROOF_SAMPLE_SIZE} rows drawn with random.Random({PROOF_SEED}):")
    for record in proof:
        print(
            f"  image {record['image_id']} {record['shard']}/{record['filename'][:44]!r} "
            f"-> {'RESOLVED' if record['resolved_path'] else 'NOT RESOLVED'} "
            f"{record.get('head12_hex', '')[:24]} "
            f"size={record.get('disk_file_size')} db={record['db_file_size_bytes']}"
        )

    report = {
        "rule": "<offsite>/images/wiki/<site_id hex without dashes [:8]>/<wiki_images.filename>",
        "evidence": {
            "pipeline/wiki_image_downloader.py:155-157": "site_image_dir() = IMAGE_DIR / site_id[:8]",
            "pipeline/wiki_image_downloader.py:37": 'IMAGE_DIR = Path("public/data/images/wiki")',
            "pipeline/wiki_image_downloader.py:1001-1007": (
                "filename = hero.webp for the first image of a site, else the sanitised "
                "Commons file title with extension forced to .webp"
            ),
            "pipeline/wiki_image_downloader.py:1126": (
                "local_path = f'/data/images/wiki/{site_id[:8]}/{local_filename}'"
            ),
            "pipeline/static_exporter.py:569-572": (
                "'p': f'/data/images/wiki/{site_id_short}/{row.filename}' in images/index.json"
            ),
            "pipeline/sites_html_renderer.py:22-24": (
                "site_id_short(): 'First 8 hex chars of a site UUID - the on-disk image dir'"
            ),
            "scripts/reindex_wiki_images.py:77-95": (
                "reads the directory name back: short = flat_id[:8]; filename = img_path.name"
            ),
        },
        "offsite_images": str(OFFSITE_IMAGES),
        "offsite_collisions": str(OFFSITE_CASE_COLLISIONS),
        "snapshot": str(WIKI_IMAGES_SNAPSHOT),
        "disk_files_main_tree": disk_files,
        "snapshot_rows": len(rows),
        "checks": {
            "resolved_exact_case": resolved,
            "unresolved": len(misses),
            "resolved_from_collisions_tree": collision_hits,
            "magic_checked": magic_checked,
            "magic_bad": magic_bad,
            "empty_files": empty_files,
            "size_equal": size_equal,
            "size_diff": size_diff,
            "size_null_in_db": size_null,
            "size_diff_examples": size_diffs,
            "rows_sharing_one_shard_filename": duplicates,
        },
        "index_json": {
            "path": str(index_path),
            "sites": len(index),
            "entries": entries,
            "path_field_matches_rule": index_path_ok,
            "resolves_in_site_shard": index_path_ok_shard,
            "also_in_snapshot": index_in_snapshot,
            "not_on_disk": index_missing_on_disk,
            "not_in_snapshot": index_not_in_snapshot,
            "mismatch_examples": index_path_bad,
        },
        "proof_sample": {"seed": PROOF_SEED, "size": PROOF_SAMPLE_SIZE, "rows": proof},
        "unresolved_rows": misses,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
