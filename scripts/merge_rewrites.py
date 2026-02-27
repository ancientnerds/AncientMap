#!/usr/bin/env python3
"""Phase 3: Merge rewrite outputs into card_descriptions.json, then re-validate.

Reads:  output/rewrite_output_00..09.json
Reads:  output/card_descriptions.json (original)
Writes: output/card_descriptions.json (updated)

Then re-runs Phase 1 verification to confirm no new issues.
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

NUM_BATCHES = 10


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    # Load original descriptions
    with open(OUTPUT / "card_descriptions.json", encoding="utf-8") as f:
        original = json.load(f)
    descs = original["descriptions"]
    print(f"Original: {len(descs)} descriptions")

    # Collect all rewrites
    all_rewrites = {}
    missing_batches = []
    batch_stats = []

    for i in range(NUM_BATCHES):
        path = OUTPUT / f"rewrite_output_{i:02d}.json"
        if not path.exists():
            missing_batches.append(i)
            continue

        with open(path, encoding="utf-8") as f:
            result = json.load(f)

        rewrites = result.get("rewrites", {})
        batch_stats.append(f"  Batch {i}: {len(rewrites)} rewrites")
        all_rewrites.update(rewrites)

    if missing_batches:
        print(f"WARNING: Missing batch files: {missing_batches}")

    print(f"\nCollected {len(all_rewrites)} rewrites from {NUM_BATCHES - len(missing_batches)} batches:")
    for s in batch_stats:
        print(s)

    # Validate rewrites before applying
    errors = []
    for sid, new_desc in all_rewrites.items():
        if sid not in descs:
            errors.append(f"Unknown site_id: {sid}")
            continue
        if len(new_desc) > 200:
            errors.append(f"TOO LONG ({len(new_desc)} chars): {sid}: {new_desc[:80]}...")
        if not new_desc.rstrip()[-1:] in '.!?\'"':
            errors.append(f"BAD ENDING: {sid} ends with '{new_desc[-1:]}'")

    if errors:
        print(f"\nValidation errors ({len(errors)}):")
        for e in errors[:30]:
            print(f"  {e}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more")

    # Apply rewrites
    applied = 0
    for sid, new_desc in all_rewrites.items():
        if sid in descs and len(new_desc) <= 200:
            descs[sid] = new_desc
            applied += 1

    print(f"\nApplied {applied} rewrites (skipped {len(all_rewrites) - applied})")

    # Write updated file
    original["descriptions"] = descs
    with open(OUTPUT / "card_descriptions.json", "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False, indent=2)

    print(f"Wrote updated card_descriptions.json with {len(descs)} descriptions")

    # Copy to public/data/ so the API startup import picks it up
    public_path = ROOT / "public" / "data" / "card_descriptions.json"
    shutil.copy2(OUTPUT / "card_descriptions.json", public_path)
    print(f"Copied to {public_path}")

    # Re-run Phase 1 verification
    print("\n" + "=" * 60)
    print("Re-running Phase 1 verification on updated descriptions...")
    print("=" * 60)

    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_descriptions.py")],
        capture_output=True, text=True, encoding="utf-8"
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)


if __name__ == "__main__":
    main()
