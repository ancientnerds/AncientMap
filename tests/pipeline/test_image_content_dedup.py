"""Content-level dedup for images embedded into a research paper.

URL and subject dedup both existed already; neither compares pixels, so the
published solar-superflares paper carried the same 194x110 Europeana frame
twice (byte-identical, two catalogue IDs one digit apart) and the Petrie
paper used one photo as evidence for two different claims in two sections.
"""

from __future__ import annotations

import io

from PIL import Image

from pipeline.lyra.handlers.probative_images import _claim_image_content


class _Ctx:
    """Minimal stand-in for the fields _claim_image_content touches."""

    def __init__(self):
        self.placed_content_hashes = set()
        self.placed_dhashes = []


def _img_bytes(seed: int, size=(160, 120), quality=95) -> bytes:
    img = Image.new("RGB", (160, 120))
    px = img.load()
    for x in range(160):
        for y in range(120):
            px[x, y] = ((x * seed) % 256, (y * seed * 3) % 256, (x + y + seed) % 256)
    if size != (160, 120):
        img = img.resize(size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def test_first_image_is_claimed():
    ctx = _Ctx()
    assert _claim_image_content(ctx, _img_bytes(7)) is True


def test_byte_identical_image_is_rejected():
    """The Kepler case: same file, two Europeana catalogue entries."""
    ctx = _Ctx()
    data = _img_bytes(7)
    assert _claim_image_content(ctx, data) is True
    assert _claim_image_content(ctx, data) is False


def test_rescaled_copy_is_rejected():
    """The Pontic-Caspian case: same picture, different encoding/size."""
    ctx = _Ctx()
    assert _claim_image_content(ctx, _img_bytes(7)) is True
    assert _claim_image_content(ctx, _img_bytes(7, size=(80, 60), quality=70)) is False


def test_different_image_is_claimed():
    """Dedup must not cost the paper genuinely distinct pictures."""
    ctx = _Ctx()
    assert _claim_image_content(ctx, _img_bytes(7)) is True
    assert _claim_image_content(ctx, _img_bytes(23)) is True


def test_rejected_image_does_not_poison_the_registry():
    """A duplicate is not registered twice — a later distinct image still fits."""
    ctx = _Ctx()
    _claim_image_content(ctx, _img_bytes(7))
    _claim_image_content(ctx, _img_bytes(7))
    assert len(ctx.placed_dhashes) == 1
    assert _claim_image_content(ctx, _img_bytes(23)) is True


def test_undecodable_bytes_are_claimed_not_crashed():
    """A non-image body must not take the run down; it just isn't deduped."""
    ctx = _Ctx()
    assert _claim_image_content(ctx, b"not an image at all") is True
