"""Split the prod sample exports into agent batch files for the inventory workflow."""

import json
import pathlib

OUT = pathlib.Path("output/audit_inventory")
QUOTA = {5: 5, 4: 10, 3: 18, 2: 17, 1: 10}  # 60 sites, tier-4/5 oversampled

sites = json.loads(OUT.joinpath("_all_sites.json").read_text(encoding="utf-8"))
print(f"loaded {len(sites)} sites")

picked, seen = [], {t: 0 for t in QUOTA}
for s in sites:
    tier = s.get("rarity_tier")
    if tier in QUOTA and seen[tier] < QUOTA[tier]:
        seen[tier] += 1
        picked.append(s)
print("tier distribution:", seen, "total", len(picked))

# round-robin across the tier-ordered list so every batch is tier-mixed
batches = [picked[i::12] for i in range(12)]
for i, b in enumerate(batches, 1):
    p = OUT / f"sites_batch_{i:02d}.json"
    p.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{p}: {len(b)} sites -> {[x['name'] for x in b]}")

imgs = json.loads(OUT.joinpath("_images.json").read_text(encoding="utf-8"))
img_batches = [imgs[i::5] for i in range(5)]
for i, b in enumerate(img_batches, 1):
    p = OUT / f"images_batch_{i:02d}.json"
    p.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{p}: {len(b)} sites")
