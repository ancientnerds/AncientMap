# SPDX-License-Identifier: AGPL-3.0-only
"""Small copies of the wiki images: 480 px for the gallery, 800 px for the page hero.

The site-page gallery loaded each wiki image at full size as its "thumbnail":
1600 px files of 0.4-1.2 MB, 12.7 MB on the Göbekli Tepe page and a mobile
LCP of 9.8 s in PageSpeed Insights (SEO audit 2026-10-08). The page hero did
the same on phones: a 1600 px file of 552-575 KB shown 412 px wide, which
Lighthouse counted as 534-557 KiB wasted (SEO audit 2026-10-19, cwv-6). This
module writes a copy of every image wider than a tree's width into a tree of
its own,

    public/data/images/wiki/<id8>/<filename>        (the image, untouched)
    public/data/images/wiki-thumbs/<id8>/<filename> (480 px, the gallery tile)
    public/data/images/wiki-800/<id8>/<filename>    (800 px, the hero on a phone)

keyed by the same id and filename. They are separate roots on purpose: the
image waves of the sites remediation accept each wave by counting and
byte-checking the files of the wiki tree, and a copy inside it would break
those counts (db-final session, 2026-10-09).

nginx serves both trees from disk and, for a file this module has not written
yet - an image not wider than the tree's width, or one a wave added since the
last run - the image itself (ancientnerds-nginx-config). A missing copy
therefore costs bytes, never a broken picture.

Idempotent: sync() writes a copy that is missing or older than its image, and
deletes copies whose image is gone. Run it after every image wave, inside the
API container (the only one that mounts the wiki tree); main() syncs both
trees:

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
HERO_DIR = Path("public/data/images/wiki-800")
#: The hero on a phone: 412 CSS px at PageSpeed's 1.75x is 721 px. Measured on the
#: VPS 2026-10-20 at QUALITY: Göbekli Tepe 552 -> 95 KiB, Beit el-Wali 575 -> 118 KiB,
#: Pompeii 566 -> 102 KiB; 300 random images 438 -> 83 KiB on average.
HERO_WIDTH = 800
#: The trees main() keeps in line with the wiki tree: (width, root).
TREES = ((THUMB_WIDTH, THUMB_DIR), (HERO_WIDTH, HERO_DIR))
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


def write_thumb(image: Path, thumb: Path, width: int = THUMB_WIDTH) -> bool:
    """Write the `width` px copy of one image. False when the image is not wider
    than that: nginx serves the image itself then, a copy would only add bytes,
    and a copy left from a wider image of the same name would show the old
    picture - so it goes."""
    with Image.open(image) as im:
        if im.width <= width:
            thumb.unlink(missing_ok=True)
            return False
        height = round(im.height * width / im.width)
        small = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").resize(
            (width, height), Image.Resampling.LANCZOS
        )
    thumb.parent.mkdir(parents=True, exist_ok=True)
    tmp = thumb.with_name(thumb.name + ".tmp")
    small.save(tmp, "WEBP", quality=QUALITY, method=6)
    tmp.replace(thumb)
    return True


def _job(task: tuple[str, str, int]) -> str:
    image, thumb, width = Path(task[0]), Path(task[1]), task[2]
    try:
        return "written" if write_thumb(image, thumb, width) else "narrow"
    except (OSError, ValueError) as exc:
        logger.warning("wiki thumbs: cannot read %s: %s", image, exc)
        thumb.unlink(missing_ok=True)
        return f"unreadable:{image}"


def sync(
    wiki_dir: Path = WIKI_DIR,
    thumb_dir: Path = THUMB_DIR,
    workers: int = 2,
    width: int = THUMB_WIDTH,
) -> SyncResult:
    """Bring the `width` px tree at thumb_dir in line with the wiki tree (module docstring)."""
    images = sorted(p for p in wiki_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".webp")
    todo: list[tuple[str, str, int]] = []
    unchanged = 0
    for image in images:
        thumb = thumb_for(image, wiki_dir, thumb_dir)
        if thumb.exists() and thumb.stat().st_mtime >= image.stat().st_mtime:
            unchanged += 1
        else:
            todo.append((str(image), str(thumb), width))
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
    logger.info("wiki thumbs %d px: %s", width, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for width, root in TREES:
        print(width, sync(WIKI_DIR, root, workers=args.workers, width=width))


if __name__ == "__main__":
    main()
