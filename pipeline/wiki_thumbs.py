# SPDX-License-Identifier: AGPL-3.0-only
"""Gallery thumbnails of the wiki images: a small copy beside every large one.

The site-page gallery loaded each wiki image at full size as its "thumbnail":
1600 px files of 0.4-1.2 MB, 12.7 MB on the Göbekli Tepe page and a mobile
LCP of 9.8 s in PageSpeed Insights (SEO audit 2026-10-08). This module writes
a THUMB_WIDTH px copy of every image wider than that into a tree of its own,

    public/data/images/wiki/<id8>/<filename>        (the image, untouched)
    public/data/images/wiki-thumbs/<id8>/<filename> (its thumbnail)

keyed by the same id and filename. It is a separate root on purpose: the
image waves of the sites remediation accept each wave by counting and
byte-checking the files of the wiki tree, and a thumb inside it would break
those counts (db-final session, 2026-10-09).

nginx serves /data/images/wiki-thumbs/ from disk and, for a file this module
has not written yet - an image narrower than THUMB_WIDTH, or one a wave added
since the last run - the image itself (ancientnerds-nginx-config). A missing
thumbnail therefore costs bytes, never a broken picture.

Idempotent: sync() writes a thumbnail that is missing or older than its
image, and deletes thumbnails whose image is gone. Run it after every image
wave, inside the API container (the only one that mounts the wiki tree):

    docker exec ancient_nerds_api nice -n 19 python -m pipeline.wiki_thumbs
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

WIKI_DIR = Path("public/data/images/wiki")
THUMB_DIR = Path("public/data/images/wiki-thumbs")
#: Two gallery columns on a 3x phone, three on a desktop: 480 px is sharp in both.
THUMB_WIDTH = 480
QUALITY = 72


@dataclass(frozen=True)
class SyncResult:
    written: int
    unchanged: int
    narrow: int
    removed: int
    #: Images Pillow cannot read, by path: named so they can be fixed, and they
    #: keep no thumbnail (nginx answers with the image itself). The first full
    #: run on 2026-10-09 met a ".webp" that is a PNG with a text chunk over
    #: Pillow's MAX_TEXT_CHUNK.
    unreadable: tuple[str, ...] = ()


def thumb_for(image: Path, wiki_dir: Path = WIKI_DIR, thumb_dir: Path = THUMB_DIR) -> Path:
    """The thumbnail path of an image: the same <id8>/<filename> under the thumb root."""
    return thumb_dir / image.relative_to(wiki_dir)


def write_thumb(image: Path, thumb: Path) -> bool:
    """Write the thumbnail of one image. False when the image is not wider than
    THUMB_WIDTH: nginx serves the image itself then, a copy would only add bytes,
    and a thumbnail left from a wider image of the same name would show the old
    picture - so it goes."""
    with Image.open(image) as im:
        if im.width <= THUMB_WIDTH:
            thumb.unlink(missing_ok=True)
            return False
        height = round(im.height * THUMB_WIDTH / im.width)
        small = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").resize(
            (THUMB_WIDTH, height), Image.Resampling.LANCZOS
        )
    thumb.parent.mkdir(parents=True, exist_ok=True)
    tmp = thumb.with_name(thumb.name + ".tmp")
    small.save(tmp, "WEBP", quality=QUALITY, method=6)
    tmp.replace(thumb)
    return True


def _job(paths: tuple[str, str]) -> str:
    image, thumb = Path(paths[0]), Path(paths[1])
    try:
        return "written" if write_thumb(image, thumb) else "narrow"
    except (OSError, ValueError) as exc:
        logger.warning("wiki thumbs: cannot read %s: %s", image, exc)
        thumb.unlink(missing_ok=True)
        return f"unreadable:{image}"


def sync(wiki_dir: Path = WIKI_DIR, thumb_dir: Path = THUMB_DIR, workers: int = 2) -> SyncResult:
    """Bring the thumb tree in line with the wiki tree (module docstring)."""
    images = sorted(p for p in wiki_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".webp")
    todo: list[tuple[str, str]] = []
    unchanged = 0
    for image in images:
        thumb = thumb_for(image, wiki_dir, thumb_dir)
        if thumb.exists() and thumb.stat().st_mtime >= image.stat().st_mtime:
            unchanged += 1
        else:
            todo.append((str(image), str(thumb)))
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(_job, todo, chunksize=32))
    else:
        outcomes = [_job(paths) for paths in todo]
    written = outcomes.count("written")
    narrow = outcomes.count("narrow")
    unreadable = tuple(o.split(":", 1)[1] for o in outcomes if o.startswith("unreadable:"))
    removed = 0
    wanted = {thumb_for(i, wiki_dir, thumb_dir) for i in images}
    if thumb_dir.exists():
        for thumb in thumb_dir.rglob("*"):
            if thumb.is_file() and thumb not in wanted:
                thumb.unlink()
                removed += 1
    result = SyncResult(
        written=written, unchanged=unchanged, narrow=narrow, removed=removed, unreadable=unreadable
    )
    logger.info("wiki thumbs: %s", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(sync(workers=args.workers))


if __name__ == "__main__":
    main()
