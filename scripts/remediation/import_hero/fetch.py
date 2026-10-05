"""The fetch step's manifest: what a 1600 px download must deliver to the lane.

`pipeline/wiki_image_downloader.py` fetches well - `fetch_image_metadata_batch()` answers seven
columns of `imageinfo`, `download_image()` writes the 1600 px derivative and reports its own size.
Neither knows the eleven columns `plan._fetch_changes` demands (`FETCH_COLUMNS`), and the lane
refuses a manifest entry that does not carry all eleven, because a row that shows a file must credit
that same file. This module is the join between the two, and it refuses by name rather than filling a
gap with a guess.

The local file's name follows the owner's decision of 2026-10-05 (23:45): **the Commons name
verbatim, only the extension becomes `.webp`**. Production holds two conventions - measured over all
48,567 image rows on 2026-10-05: 26,027 rows named after a readable title, 18,746 after the Commons
name - and the new wave picks one instead of adding a third silently. The name is public: it is the
file's path on the site page and the export's `im`.

Nothing here fetches. The downloader does; this only shapes what a finished download says.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from import_hero.plan import FETCH_COLUMNS, ImportHeroError

#: The lane's minimum: `local_file_too_small` refused every site below it, so a fetch that delivers
#: less would put the site back where it started. `pipeline.wiki_image_downloader.LOCAL_MAX_WIDTH`
#: is the same number and the downloader's own reason for picking its bucket.
MIN_WIDTH = 1600

#: The Commons page of a file, percent-encoded the way the existing rows carry it (`File%3A…`).
COMMONS_FILE_PAGE = "https://commons.wikimedia.org/wiki/File%3A"


class FetchError(ImportHeroError):
    """A download cannot become a manifest entry. Named, never repaired."""


def local_name(commons_file: str) -> str:
    """The file's local name: the Commons name verbatim, only the extension becomes `.webp`.

    Refuses a name with no extension - there is nothing to swap, and guessing `.webp` on a name
    that has none would write a file the DB cannot name.
    """
    stem, dot, extension = commons_file.rpartition(".")
    if not dot or not stem or not extension:
        raise FetchError(f"{commons_file!r} has no extension to swap for .webp")
    return f"{stem}.webp"


def manifest_entry(
    site_id: str,
    commons_file: str,
    metadata: Mapping[str, Any],
    result: Any,
) -> dict[str, str]:
    """The eleven columns of one fetched file, as strings.

    `metadata` is one entry of `fetch_image_metadata_batch()`; `result` is what `download_image()`
    returned for it. The site's id is named in every refusal, because a manifest is read per site
    and a message that does not say which one cost a whole wave to find.
    """
    filename = local_name(commons_file)
    width = int(getattr(result, "width", 0) or 0)
    if width < MIN_WIDTH:
        raise FetchError(
            f"{site_id}: the download of {commons_file!r} is {width}px wide, under the {MIN_WIDTH}px "
            f"this lane serves - the very refusal ({'local_file_too_small'}) it would clear"
        )
    entry = {
        "filename": filename,
        "title": filename.rsplit(".", 1)[0],
        "commons_page_url": COMMONS_FILE_PAGE + quote(commons_file, safe=""),
        "original_url": str(metadata.get("original_url") or ""),
        "author": str(metadata.get("author") or ""),
        "author_url": str(metadata.get("author_url") or ""),
        "license": str(metadata.get("license") or ""),
        "license_url": str(metadata.get("license_url") or ""),
        "width": str(width),
        "height": str(int(getattr(result, "height", 0) or 0)),
        "file_size_bytes": str(int(getattr(result, "file_size", 0) or 0)),
    }
    missing = [column for column in FETCH_COLUMNS if not entry.get(column)]
    if missing:
        raise FetchError(
            f"{site_id}: the fetch of {commons_file!r} names no {', '.join(missing)}: the imageinfo "
            f"answer carries {', '.join(sorted(metadata))} and the download only its size - a row "
            f"that shows a file has to credit it (owner decision 2026-10-05)"
        )
    return entry
