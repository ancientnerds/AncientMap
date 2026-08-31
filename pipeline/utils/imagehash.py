"""Perceptual image hashing — shared by attribution matching and image dedup.

Lived in `pipeline/image_attribution_backfill.py` until 2026-08-31, where it
proved a Commons hero image matched a stored one. The research image pipeline
needs the same test for a different question — "did this picture already land
in this paper?" — so it moved here rather than being written twice.

Calibration is empirical (2026-08-17, Commons thumbnails): distance <= 6 on
re-encoded or re-scaled copies of one photo, typically > 20 between different
photos of the same subject.
"""

from __future__ import annotations

from PIL import Image

# Keep in sync with the calibration note above before changing.
DHASH_MAX_DISTANCE = 6


def dhash(image) -> int:
    """64-bit difference hash of a PIL image (9x8 grayscale gradient)."""
    gray = image.convert("L").resize((9, 8), Image.LANCZOS)
    pixels = list(gray.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
