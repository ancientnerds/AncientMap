#!/usr/bin/env python3
"""Generate downscaled basemap texture tiers for the globe.

The frontend ships a 16383x8192 basemap (`*_high.webp`). That single texture
costs ~512 MB to decode and upload on the GPU, which crashes memory-constrained
tablets (iPad Safari per-tab limit; Android/Galaxy GPUs whose MAX_TEXTURE_SIZE is
below 16384) during the loading splash. This script derives smaller tiers from
the existing high-res files so `useTextureLoading.ts` can serve a device-
appropriate size. Desktop keeps the high tier untouched.

Tiers (width x height):
  high    16383x8192  (existing, not regenerated here)
  medium   8192x4096  (~1/4 the memory; safe on essentially all tablets)
  low      4096x2048  (~1/16; fallback for old/low GPUs)

Run from the repo root:  python scripts/gen_basemap_tiers.py
Idempotent: overwrites the medium/low outputs each run.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# The high-res source is larger than Pillow's decompression-bomb guard. The
# inputs are our own trusted assets, so disable the guard for this script.
Image.MAX_IMAGE_PIXELS = None

BASEMAP_DIR = Path(__file__).resolve().parent.parent / "public" / "data" / "basemaps"

# Source (high) basenames -> nothing special; we read "<name>_high.webp".
SOURCES = ["gray_dark", "satellite"]

# tier suffix -> target width (height is always width // 2 for an equirect map)
TIERS = {
    "med": 8192,
    "low": 4096,
}

# WebP encode settings: method=6 = slowest/best compression, quality tuned to
# keep files small while staying visually clean on a sphere.
WEBP_QUALITY = 82
WEBP_METHOD = 6


def main() -> None:
    for name in SOURCES:
        src = BASEMAP_DIR / f"{name}_high.webp"
        if not src.exists():
            raise SystemExit(f"Missing source basemap: {src}")
        print(f"Loading {src.name} ...", flush=True)
        with Image.open(src) as img:
            img = img.convert("RGB")
            for suffix, width in TIERS.items():
                height = width // 2
                out = BASEMAP_DIR / f"{name}_{suffix}.webp"
                resized = img.resize((width, height), Image.LANCZOS)
                resized.save(out, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
                size_mb = out.stat().st_size / (1024 * 1024)
                print(f"  -> {out.name}  {width}x{height}  {size_mb:.2f} MiB", flush=True)


if __name__ == "__main__":
    main()
