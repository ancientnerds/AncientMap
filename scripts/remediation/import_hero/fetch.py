"""The fetch step: which files to get, where they land, and what the manifest says.

`pipeline/wiki_image_downloader.py` fetches well - `fetch_image_metadata_batch()` answers seven
columns of `imageinfo`, `download_image()` writes the 1600 px derivative and reports its own size.
Neither knows the eleven columns `plan._fetch_changes` demands (`FETCH_COLUMNS`), and the lane
refuses a manifest entry that does not carry all eleven, because a row that shows a file must credit
that same file. This module is the join between the two, and it refuses by name rather than filling a
gap with a guess.

The local file's name follows the owner's decision of 2026-10-05 (23:45): **the Commons name
verbatim, only the extension becomes `.webp`**. Production holds two conventions - re-measured over
all 48,567 image rows of run `import-hero-2026-10-05-002` on 2026-10-05: 26,349 `filename` values
named after a readable title, 22,218 after the Commons name, and in `commons_page_url` 43,392 rows
against 4,528 (647 carry no `File%3A` page) - so the title form is the spelling the rows already
carry and the new wave follows it instead of adding a third silently. The name is public: it is the
file's path on the site page and the export's `im`.

The file lands under `<root>/<the site's first 8 hex chars>/`, the layout the image tree already uses
on disk and on the VPS. Which root is the caller's: the offsite copy is where this lane reads its
pictures from (runbook 3.2), the VPS copy is what production serves, so a fetch into the first has to
be followed into the second. That transfer is a separate, explicit step - nothing here writes to the
VPS.

One constraint on the caller: `download_image()` writes with `O_EXCL`, so a wave that is interrupted
after some hundreds of files has left those files on disk and cannot be re-run over them; a fetch that
must survive an interruption has to carry its manifest along as it goes, not at the end.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from served_image import state as ST

from import_hero.plan import (
    FETCH_COLUMNS,
    HERO_MIN_HEIGHT,
    HERO_MIN_WIDTH,
    ImportHeroError,
)

#: The Commons page of a file, percent-encoded the way the existing rows carry it (`File%3A…`).
COMMONS_FILE_PAGE = "https://commons.wikimedia.org/wiki/File%3A"

#: How many titles one `imageinfo` answer carries. The downloader takes "up to 50 images in one API
#: call" (`fetch_image_metadata_batch`'s own words), restated so the loop and the module it drives
#: cannot drift apart.
BATCH_TITLES = 50


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

    A download under the plan's hero minimum (`HERO_MIN_WIDTH` x `HERO_MIN_HEIGHT`) is refused here,
    where the size is known, instead of being installed and refused again by the next plan: the
    width alone is not the rule, because the stored derivative keeps the original's aspect ratio -
    121 of the 807 refusals of run `import-hero-2026-10-05-002` are a 1600 px panorama under 900 px
    high, and a 1600 px fetch of one returns the very same box.
    """
    filename = local_name(commons_file)
    width = int(result.width)
    height = int(result.height)
    if width < HERO_MIN_WIDTH or height < HERO_MIN_HEIGHT:
        raise FetchError(
            f"{site_id}: the download of {commons_file!r} is {width}x{height}, under the "
            f"{HERO_MIN_WIDTH}x{HERO_MIN_HEIGHT} this lane serves - the very refusal "
            f"(`local_file_too_small`) it would clear"
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
        "height": str(height),
        "file_size_bytes": str(int(result.file_size)),
    }
    missing = [column for column in FETCH_COLUMNS if not entry.get(column)]
    if missing:
        raise FetchError(
            f"{site_id}: the fetch of {commons_file!r} names no {', '.join(missing)}: the imageinfo "
            f"answer carries {', '.join(sorted(metadata))} and the download only its size - a row "
            f"that shows a file has to credit it (owner decision 2026-10-05)"
        )
    return entry


def plan_targets(
    claims: Mapping[str, Mapping[str, Any]],
    refusals: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    """The `(site id, Commons file)` pairs to fetch: the `local_file_too_small` refusals whose
    import link names a Commons file.

    A refusal whose link names no Commons file is refused by name - it is not a fetch target, and
    writing one would fetch something the plan never asked for.
    """
    targets: list[tuple[str, str]] = []
    for refusal in refusals:
        if refusal.get("reason") != "local_file_too_small":
            continue
        site_id = str(refusal.get("site_id") or "")
        claim = claims.get(site_id, {})
        commons_file = ST.file_of_url(str(claim.get("image") or "")) or ""
        if not commons_file:
            raise FetchError(
                f"{site_id}: refused as {refusal.get('reason')!r} but its import link "
                f"{claim.get('image')!r} names no Commons file - there is nothing to fetch"
            )
        targets.append((site_id, commons_file))
    if not targets:
        raise FetchError(
            "no site to fetch: no refusal of this wave is a `local_file_too_small` one"
        )
    return targets


def site_dest(root: Path, site_id: str, commons_file: str) -> Path:
    """Where one site's file goes: `<root>/<first 8 of the site id>/<local name>`."""
    return Path(root) / site_id[:8] / local_name(commons_file)


def fetch_site(site_id: str, commons_file: str, root: Path) -> dict[str, str]:
    """One site: its `imageinfo` answer, its 1600 px derivative, and the manifest entry for both.

    The file is written before the entry exists, so a manifest can never name a file that is not on
    disk; a download that fails refuses by name and leaves no entry behind. The downloader is
    imported here, not at module scope: it pulls in `pipeline`, and a lane module that only shapes
    what a download said should not make every reader pay for it.
    """
    from pipeline import wiki_image_downloader as DL

    answers = DL.fetch_image_metadata_batch([f"File:{commons_file}"])
    metadata = answers.get(f"File:{commons_file}")
    if metadata is None:
        raise FetchError(
            f"{site_id}: Commons answered no `imageinfo` for File:{commons_file} "
            f"(got {', '.join(sorted(answers)) or 'nothing'})"
        )
    dest = site_dest(root, site_id, commons_file)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = DL.download_image(metadata.get("original_url"), dest, int(metadata.get("width") or 0))
    return manifest_entry(site_id, commons_file, metadata, result)


def fetch_manifest(
    targets: Sequence[tuple[str, str]],
    root: Path,
    *,
    batch_titles: int = BATCH_TITLES,
    delay_s: float | None = None,
) -> tuple[dict[str, dict[str, str]], list[tuple[str, str, str]]]:
    """Fetch every target and return `(manifest, failures)`.

    The downloads run serially at the downloader's own pace (`WIKIPEDIA_DELAY`, the Wikimedia robot
    policy) unless the caller names one. One site that fails does not take the rest with it: the
    refusal is returned with its site and file, and the plan refuses those sites by name on the next
    run. A run where *nothing* was fetched is refused outright - the plan would then keep refusing
    every site of the wave, and a manifest of zero rows would look like a finished fetch.
    """
    from pipeline import wiki_image_downloader as DL

    pace = DL.WIKIPEDIA_DELAY if delay_s is None else delay_s
    manifest: dict[str, dict[str, str]] = {}
    failures: list[tuple[str, str, str]] = []
    for site_id, commons_file in targets:
        try:
            manifest[site_id] = fetch_site(site_id, commons_file, root)
        except (FetchError, DL.DownloadError) as exc:
            failures.append((site_id, commons_file, f"the fetch failed: {exc}"))
        time.sleep(pace)
    if not manifest:
        names = ", ".join(f"{sid} ({name})" for sid, name, _ in failures[:3])
        raise FetchError(
            f"no file of this wave could be fetched ({len(failures)} failed, first: {names}) - the "
            f"plan would then keep refusing every one of them as `local_file_too_small`"
        )
    return manifest, failures


def write_manifest(path: Path, manifest: Mapping[str, Mapping[str, str]]) -> str:
    """`FETCHED.json`, written once per run directory. Returns its sha256.

    Written once, like every other record of this remediation: a second run belongs in a new run
    directory, and overwriting a manifest would replace the list of files a plan was built from.
    """
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path = Path(path)
    if path.exists():
        raise FetchError(f"{path} already exists - a second fetch belongs in a new run directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
