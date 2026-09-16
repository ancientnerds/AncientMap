"""Download a site's Commons images at original resolution for video use.

Goes through `pipeline.lyra.image_fetcher.download_candidate`, which carries the
Wikimedia throttle, the SSRF guard and the size cap. `original_url` is the
full-resolution upload — the 800 px thumbnails the web pages use are never
touched.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PIL import Image

from pipeline.lyra.image_fetcher import ImageCandidate, download_candidate

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def local_image_name(index: int, filename: str, original_url: str = "") -> str:
    """Stable, filesystem-safe name: `03_Some_File.jpg`.

    `wiki_images.filename` carries the web thumbnail's `.webp` suffix; the
    bytes we download are the Commons original, so the extension comes from
    `original_url` when given.
    """
    stem = _UNSAFE.sub("_", Path(filename).stem).strip("_") or "image"
    ext = Path(original_url).suffix.lower() if original_url else Path(filename).suffix.lower()
    return f"{index:02d}_{stem[:80]}{ext}"


async def download_site_images(site: dict, out_dir: Path, limit: int = 8) -> list[dict]:
    """Download up to `limit` images (hero first). Returns the image dicts that
    landed on disk, each extended with `local_path`, `width`, `height`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    landed: list[dict] = []
    for index, img in enumerate(site["images"][:limit]):
        cand = ImageCandidate(
            url=img["commons_page_url"] or img["original_url"],
            source="wikimedia",
            title=img["title"] or img["filename"],
            artist=img["author"] or "",
            license=img["license"] or "",
            license_url=img["license_url"] or "",
            thumbnail_url=img["original_url"],
        )
        target = out_dir / local_image_name(index, img["filename"], img["original_url"])
        if not target.exists() and not await download_candidate(cand, target):
            logger.warning("skipping %s (download failed)", img["filename"])
            continue
        with Image.open(target) as im:
            width, height = im.size
        landed.append({**img, "local_path": str(target), "width": width, "height": height})
        logger.info("image %s: %dx%d", target.name, width, height)
    return landed
