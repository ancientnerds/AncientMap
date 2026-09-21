"""Check the measurement artifacts against the things they claim.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/selftest.py

    # against another directory (that is how the teeth are shown, see METHOD.md):
    ... selftest.py --dir /tmp/corrupted

It exits non-zero with the list of failures. What it checks, all on the real
files:

  SAMPLE.jsonl   200 records, 50 per tier, `sheet_index` 0..49, 200 distinct
                 image ids, every `local_file_path` present, non-empty and
                 `RIFF....WEBP`, the recorded `file_size` equal to the file's
                 size, `shard == site_id[:8]`, and the same draw reproducible
                 (make_sample.py is re-run with the same seed into a temp file
                 and the two must be byte-identical).
  SHEETS.json    the tile list agrees with SAMPLE.jsonl on every image_id and
                 index, and the four sheet PNGs plus the 200 zoom tiles exist.
  LABELS.template.jsonl  one blank label row per image, same ids.
  VLM.jsonl      one record per sampled image in sample order, `kind` either in
                 the prompt's enum or null **with** an error recorded, the raw
                 response kept, and the per-row cost equal to the token counts.
  MAPPING_PROOF.json and REJECTED_KINDS.jsonl  present and internally consistent.

Nothing here decides a label; it only refuses to let an unverified claim pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import OUT_DIR, read_jsonl, shard_for  # noqa: E402

TIERS = ("A", "B", "C", "D")
KINDS = ("site_photo", "artifact", "map_or_document", "painting_or_artwork", "people", "other")

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=str(OUT_DIR), help="artifact directory to check")
    parser.add_argument("--skip-regen", action="store_true")
    args = parser.parse_args()
    out = Path(args.dir)

    sample = list(read_jsonl(out / "SAMPLE.jsonl"))
    check(len(sample) == 200, f"SAMPLE.jsonl has {len(sample)} records, expected 200")
    check(len({r['image_id'] for r in sample}) == len(sample), "duplicate image_id in SAMPLE.jsonl")
    for tier in TIERS:
        rows = [r for r in sample if r["tier"] == tier]
        check(len(rows) == 50, f"tier {tier} has {len(rows)} records, expected 50")
        check(
            sorted(r["sheet_index"] for r in rows) == list(range(50)),
            f"tier {tier} sheet indices are not 0..49",
        )
    for row in sample:
        check(row["shard"] == shard_for(row["site_id"]), f"image {row['image_id']}: shard mismatch")
        check(
            row["url_path"] == f"/data/images/wiki/{row['shard']}/{row['filename']}",
            f"image {row['image_id']}: url_path does not follow the mapping rule",
        )
        path = Path(row["local_file_path"])
        check(path.is_file(), f"image {row['image_id']}: missing {path}")
        if path.is_file():
            check(path.stat().st_size == row["file_size"], f"image {row['image_id']}: size differs")
            with open(path, "rb") as handle:
                head = handle.read(12)
            check(
                head[0:4] == b"RIFF" and head[8:12] == b"WEBP",
                f"image {row['image_id']}: not RIFF....WEBP ({head.hex()})",
            )

    if not args.skip_regen:
        target = Path(tempfile.gettempdir()) / "vlm_pilot_selftest_sample.jsonl"
        script = Path(__file__).resolve().parent / "make_sample.py"
        result = subprocess.run(
            [sys.executable, str(script), "--out", str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        check(result.returncode == 0, f"make_sample.py --out {target} failed: {result.stderr[-400:]}")
        if result.returncode == 0:
            check(
                target.read_bytes() == (out / "SAMPLE.jsonl").read_bytes(),
                "the regenerated sample is not byte-identical to SAMPLE.jsonl (not reproducible)",
            )
        target.unlink(missing_ok=True)

    sheets = json.loads((out / "SHEETS.json").read_text(encoding="utf-8"))
    for tier in TIERS:
        block = sheets["tiers"].get(tier)
        check(block is not None, f"SHEETS.json has no tier {tier}")
        if block is None:
            continue
        tiles = block["tiles"]
        check(len(tiles) == 50, f"SHEETS.json tier {tier} has {len(tiles)} tiles")
        sample_tier = {r["sheet_index"]: r for r in sample if r["tier"] == tier}
        for tile in tiles:
            row = sample_tier.get(tile["index"])
            check(row is not None and row["image_id"] == tile["image_id"],
                  f"SHEETS.json tier {tier} tile {tile['index']} disagrees with SAMPLE.jsonl")
            check(tile["label"] == f"{tier}{tile['index']:02d}", f"tile label {tile['label']!r}")
            zoom = out / "tiles" / tier / f"{tile['label']}.jpg"
            check(zoom.is_file(), f"zoom tile missing: {zoom}")
        sheet_file = Path(block["sheet"])
        check(sheet_file.is_file(), f"sheet missing: {sheet_file}")
        if sheet_file.is_file():
            with open(sheet_file, "rb") as handle:
                check(handle.read(8) == b"\x89PNG\r\n\x1a\n", f"{sheet_file} is not a PNG")

    labels = list(read_jsonl(out / "LABELS.template.jsonl"))
    check(len(labels) == 200, f"LABELS.template.jsonl has {len(labels)} rows")
    check(
        {r["image_id"] for r in labels} == {r["image_id"] for r in sample},
        "LABELS.template.jsonl ids differ from SAMPLE.jsonl",
    )
    check(all(r["human_kind"] is None for r in labels), "LABELS.template.jsonl already carries labels")

    vlm_path = out / "VLM.jsonl"
    if not vlm_path.is_file():
        failures.append("VLM.jsonl missing - run ask_vlm.py (this check is part of the artifact set)")
    else:
        vlm = list(read_jsonl(vlm_path))
        check(len(vlm) == len(sample), f"VLM.jsonl has {len(vlm)} records, expected {len(sample)}")
        check(
            [r["image_id"] for r in vlm] == [r["image_id"] for r in sample],
            "VLM.jsonl order/ids differ from SAMPLE.jsonl",
        )
        for record in vlm:
            if record["kind"] is None:
                check(bool(record.get("error")),
                      f"VLM.jsonl image {record['image_id']}: no kind and no error")
            else:
                check(record["kind"] in KINDS,
                      f"VLM.jsonl image {record['image_id']}: out-of-enum kind {record['kind']!r}")
            check(bool(record.get("raw_response")) or record["kind"] is None,
                  f"VLM.jsonl image {record['image_id']}: kind without a raw response")
            totals = record["usage_totals"]
            expected = (
                max(totals["prompt_tokens"] - totals["cached_tokens"], 0) * 0.15
                + totals["cached_tokens"] * 0.003
                + totals["completion_tokens"] * 0.60
            ) / 1_000_000
            check(
                abs(round(expected, 8) - record["cost_usd"]) < 1e-8,
                f"VLM.jsonl image {record['image_id']}: cost {record['cost_usd']} != recomputed "
                f"{expected:.8f}",
            )

    proof_path = out / "MAPPING_PROOF.json"
    check(proof_path.is_file(), "MAPPING_PROOF.json missing")
    if proof_path.is_file():
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        checks = proof["checks"]
        check(
            checks["resolved_exact_case"] + checks["unresolved"] == proof["snapshot_rows"],
            "MAPPING_PROOF.json resolution counts do not add up",
        )
        check(
            checks["resolved_exact_case"] - len(checks["resolved_from_collisions_tree"])
            + len(checks["unresolved"])
            == proof["snapshot_rows"],
            "MAPPING_PROOF.json collision accounting is inconsistent",
        )
        check(not checks["magic_bad"] or all("head_hex" in b for b in checks["magic_bad"]),
              "MAPPING_PROOF.json lists a bad-magic file without its header")

    rejected_path = out / "REJECTED_KINDS.jsonl"
    check(rejected_path.is_file(), "REJECTED_KINDS.jsonl missing")
    if rejected_path.is_file():
        rejected = list(read_jsonl(rejected_path))
        check(len(rejected) == 30, f"REJECTED_KINDS.jsonl has {len(rejected)} rows, expected 30")
        for record in rejected:
            check(record["verdict"] in ("PROVEN", "AMBIGUOUS", "UNPROVABLE"),
                  f"unknown verdict {record['verdict']!r}")
            check(bool(record["evidence"]), f"{record['filename']}: no evidence recorded")
            if record["verdict"] == "PROVEN":
                check(record["image_id"] is not None, f"{record['filename']}: PROVEN without an id")
                check(bool(record.get("resolved_path")), f"{record['filename']}: PROVEN file missing")

    print(f"checked {out}")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
