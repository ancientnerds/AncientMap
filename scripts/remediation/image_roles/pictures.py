"""The pictures the image roles are shown: production's convention at the size a role needs.

`pipeline.video.shorts_select.vlm_bytes` is the one downscale of the project (RGB, longest side
1280 px, JPEG quality 85) and the "shows this site" role is shown exactly that. The prefilter looks
at the kind of a picture, not at its detail (map owner decision D6: Haiku at 640 px), so it gets the
same bytes made smaller; nothing else about the conversion differs.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

from pipeline.video.shorts_select import VLM_JPEG_QUALITY, vlm_bytes

#: The prefilter's longest side (D6 / map 3 C1) and the depicts role's (`vlm_bytes`' own).
PREFILTER_SIDE = 640
DEPICTS_SIDE = 1280


def downscale(data: bytes, side: int) -> bytes:
    """`data` (a JPEG) with its longest side at most `side` px, re-encoded at the project's quality.
    A picture already within the side is returned as it is."""
    with Image.open(io.BytesIO(data)) as image:
        if max(image.size) <= side:
            return data
        image = image.convert("RGB")
        image.thumbnail((side, side))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=VLM_JPEG_QUALITY)
        return out.getvalue()


def picture_bytes(path: Path, side: int) -> bytes:
    """The file at `path` as the project hands a picture to a vision judge, at most `side` px."""
    return downscale(vlm_bytes(path), side)


def image_name(prefix: str, *parts: str) -> str:
    """A handoff image name: `<prefix>-<24 hex of the sha256 of the parts>`. Stable for the same
    parts, so exporting a candidate twice writes one file."""
    digest = hashlib.sha256("\t".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"
