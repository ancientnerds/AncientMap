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


# --- Image budget (2026-08-31) ---------------------------------------------
# Recovering the judge's middle verdict took the solar-superflares paper from
# 7 images to 89: 52 opportunities that used to yield nothing now yield up to
# three each. A paper is not a slideshow.

from pipeline.lyra.handlers.probative_images import (  # noqa: E402
    _limit_tagged,
    _release_image_slot,
    _reserve_image_slot,
)


class _BudgetCtx:
    def __init__(self, max_images=24, placed=0):
        self.max_images = max_images
        self.images_placed = placed


def test_reserve_slot_stops_at_the_paper_budget():
    ctx = _BudgetCtx(max_images=2)
    assert _reserve_image_slot(ctx) is True
    assert _reserve_image_slot(ctx) is True
    assert _reserve_image_slot(ctx) is False
    assert ctx.images_placed == 2


def test_released_slot_is_reusable():
    """A failed download must give its slot back, or the budget leaks."""
    ctx = _BudgetCtx(max_images=1)
    assert _reserve_image_slot(ctx) is True
    _release_image_slot(ctx)
    assert _reserve_image_slot(ctx) is True


def test_release_never_goes_negative():
    ctx = _BudgetCtx(max_images=5)
    _release_image_slot(ctx)
    assert ctx.images_placed == 0


def test_limit_tagged_keeps_only_one_illustration():
    """Illustrations support a passage, they don't prove it — stacking three
    under one paragraph is decoration."""
    tagged = [("a", False), ("b", False), ("c", False)]
    assert _limit_tagged(tagged, 3) == [("a", False)]


def test_limit_tagged_puts_evidence_first():
    tagged = [("illustration", False), ("evidence", True)]
    assert _limit_tagged(tagged, 3) == [("evidence", True), ("illustration", False)]


def test_limit_tagged_respects_the_per_opportunity_cap():
    tagged = [("e1", True), ("e2", True), ("e3", True), ("i1", False)]
    assert _limit_tagged(tagged, 3) == [("e1", True), ("e2", True), ("e3", True)]


def test_limit_tagged_keeps_all_evidence_below_the_cap():
    tagged = [("e1", True), ("i1", False), ("i2", False)]
    assert _limit_tagged(tagged, 3) == [("e1", True), ("i1", False)]
