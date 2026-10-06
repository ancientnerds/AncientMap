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

One constraint on the caller, and it is why `run_fetch` exists next to `fetch_manifest`:
`download_image()` writes with `O_EXCL`, so a wave that is interrupted after some hundreds of files has
left those files on disk and cannot be re-run over them. `fetch_manifest` hands the whole wave over at
the end - the right shape for a test, the wrong one for 800 downloads against a host that may drop the
link. `run_fetch` writes `FETCHED.json` after every file (atomically, through a temporary file), skips
what the manifest already carries and records a failed site by name for the next run to retry.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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


#: What a file name may not carry. Windows forbids `<>:"/\|?*` and the C0 controls, POSIX `/` and
#: NUL; the offsite tree and the VPS tree both live on such a file system, so a title carrying one
#: of these cannot be written at all. Production carries **no** row whose filename has one (measured
#: 2026-10-06 over the read's 48,567 rows), so refusing these few keeps the one convention the pages
#: already serve instead of adding a percent-encoded spelling for three sites.
ILLEGAL_IN_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def local_name(commons_file: str) -> str:
    """The file's local name: the Commons name verbatim, only the extension becomes `.webp`.

    Refuses a name with no extension - there is nothing to swap, and guessing `.webp` on a name
    that has none would write a file the DB cannot name - and a name carrying a character the file
    system refuses (`ILLEGAL_IN_NAME`), for the same reason: the row would name a file that cannot
    exist. Three of the 807 refusals of run `import-hero-2026-10-05-002` are such titles
    (measured 2026-10-06).
    """
    stem, dot, extension = commons_file.rpartition(".")
    if not dot or not stem or not extension:
        raise FetchError(f"{commons_file!r} has no extension to swap for .webp")
    name = f"{stem}.webp"
    forbidden = ILLEGAL_IN_NAME.search(name)
    if forbidden:
        raise FetchError(
            f"{name!r} cannot be stored as a local file name: {forbidden.group()!r} is a character "
            f"the filesystem refuses in a name, and the rule is the Commons name verbatim - refused "
            f"by name, not renamed"
        )
    return name


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
    *,
    reasons: Sequence[str] = ("local_file_too_small",),
) -> list[tuple[str, str]]:
    """The `(site id, Commons file)` pairs to fetch: the refusals of the named classes whose import
    link names a Commons file.

    `reasons` says which wave this is. `local_file_too_small` is the hero wave: the row exists and
    only its file is under the floor. `no_target_row` is the INSERT wave: the site's rows exist but
    hold no file of the import, and the row that would show it is a statement this lane cannot make
    - the file still has to be fetched, because a row cannot name a file that is not there. Every
    other reason is never a target.

    A refusal whose link names no Commons file is refused by name - it is not a fetch target, and
    writing one would fetch something the plan never asked for.
    """
    targets: list[tuple[str, str]] = []
    for refusal in refusals:
        if refusal.get("reason") not in reasons:
            continue
        site_id = str(refusal.get("site_id") or "")
        claim = claims.get(site_id, {})
        commons_file = ST.file_of_url(str(claim.get("image") or "")) or ""
        if not commons_file:
            if refusal.get("reason") == "local_file_too_small":
                # The hero wave's own invariant: a site it refuses for its file size must have a
                # file to fetch, or the plan and the fetch disagree about what the wave is.
                raise FetchError(
                    f"{site_id}: refused as 'local_file_too_small' but its import link "
                    f"{claim.get('image')!r} names no Commons file - there is nothing to fetch"
                )
            # The INSERT wave: a site whose import link names no Commons file has no picture to
            # put in a row - measured 2026-10-06, 37 of the 326 (en.wikipedia, UNESCO, blogs,
            # a Twitter image). It is not a target and not a defect of this wave.
            continue
        targets.append((site_id, commons_file))
    if not targets:
        raise FetchError(
            f"no site to fetch: no refusal of this wave is one of {', '.join(reasons)}"
        )
    return targets


def site_dest(root: Path, site_id: str, commons_file: str) -> Path:
    """Where one site's file goes: `<root>/<first 8 of the site id>/<local name>`."""
    return Path(root) / site_id[:8] / local_name(commons_file)


@dataclass(frozen=True)
class StoredFile:
    """What `download_image` reports back, read from the file itself instead.

    A file on disk without an entry in the manifest is the state an interruption leaves behind, and
    `O_EXCL` will not let the lane write over it. The entry it still needs - the pixels, the byte
    count - is exactly what the file already states, so the step reads them back instead of asking
    for a download that would be refused.
    """

    width: int
    height: int
    file_size: int


def stored_file(dest: Path) -> StoredFile:
    """The stored derivative's own size, from the file. A file that is not an image refuses by name."""
    from PIL import Image, UnidentifiedImageError

    dest = Path(dest)
    try:
        with Image.open(dest) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise FetchError(
            f"{dest} is on disk but is not a picture ({exc}) - it refuses the download that would "
            "replace it (`download_image` writes with O_EXCL), so it has to be looked at by hand"
        ) from exc
    return StoredFile(width=width, height=height, file_size=dest.stat().st_size)


def fetch_site(site_id: str, commons_file: str, root: Path) -> dict[str, str]:
    """One site: its `imageinfo` answer, its 1600 px derivative, and the manifest entry for both.

    Four cases, decided before anything is written, because `download_image()` opens with `O_EXCL`
    and refuses to replace a file - which is the file this wave came to replace:

    * the stored file already reaches the hero minimum: it is measured and adopted. That is what
      makes a second run over the same run directory a continuation instead of a collision, and it
      is the case an interruption leaves behind (the file landed, the manifest entry did not).
    * the stored file is 1600 px wide and under 900 px high: refused by name, without a download.
      `download_image` keeps the original's aspect ratio, so a 1600 px fetch of a panorama returns
      the very same box - 121 of the 807 refusals of run `import-hero-2026-10-05-002` are one.
    * the Commons original is narrower than the hero minimum: refused by name. `imageinfo` states
      its width before the download, and a fetch cannot deliver more pixels than the original has.
    * anything else: the 1600 px derivative is fetched into a temporary name in the site's own
      directory and swapped in with `os.replace`, then measured and refused by name if it still
      falls short. The swap is atomic and the pixels are the same picture the row already showed, so
      a reader never sees a missing or half-written file - only a larger copy of the same image
      between the fetch and the wave that writes the row's new size.

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
    original_url = str(metadata.get("original_url") or "")
    original_width = int(metadata.get("width") or 0)
    if dest.is_file():
        existing = stored_file(dest)
        if existing.width >= HERO_MIN_WIDTH and existing.height >= HERO_MIN_HEIGHT:
            return manifest_entry(site_id, commons_file, metadata, existing)
        if existing.width >= HERO_MIN_WIDTH:
            raise FetchError(
                f"{site_id}: the stored file is {existing.width}x{existing.height} - a panorama at "
                f"least {HERO_MIN_WIDTH} px wide but under {HERO_MIN_HEIGHT} px high, and "
                "`download_image` keeps the aspect ratio, so a 1600 px fetch of it returns the same "
                "box. This site needs a different picture, not a bigger one"
            )
    if not original_url or original_width <= 0:
        # Commons answers a page it does not have with no `imageinfo` at all, and the batch reader
        # turns that into an entry whose fields are all None - indistinguishable from a file
        # without an original until you look at the page. Measured 2026-10-06 with one API call
        # over all 9 such refusals of the INSERT wave: every one answers `missing` (e.g.
        # File:Thul Hairo Khan.jpg). The 2025 import links pictures Commons does not host, and
        # the old message hid that behind "not an upload.wikimedia.org original: None".
        raise FetchError(
            f"{site_id}: the imageinfo answer for File:{commons_file} carries neither an "
            f"original URL nor a size (original_url={metadata.get('original_url')!r}, "
            f"width={metadata.get('width')!r}) - Commons hosts no file of this name (measured "
            f"2026-10-06: the page answers `missing`), so the 2025 import links a picture that is "
            f"not there. No fetch can deliver it"
        )
    if 0 < original_width < HERO_MIN_WIDTH:
        raise FetchError(
            f"{site_id}: the Commons original of {commons_file!r} is {original_width} px wide, "
            f"under the {HERO_MIN_WIDTH} px this lane serves - a fetch cannot deliver more pixels "
            "than the original holds"
        )
    # The other half of that floor, and it is the one that costs a download: a 1600 px wide file
    # that is under 900 px high keeps its aspect ratio and comes back that very box, so it is
    # named before anything is downloaded - and nothing is left on disk that no manifest would
    # name. (From main, commit 7600f1d, merged 2026-10-06.)
    original_height = int(metadata.get("height") or 0)
    stored_width, stored_height = DL.stored_size(original_width, original_height)
    if stored_width < HERO_MIN_WIDTH or stored_height < HERO_MIN_HEIGHT:
        raise FetchError(
            f"{site_id}: the original of {commons_file!r} is {original_width}x{original_height} "
            f"and stores as {stored_width}x{stored_height}, under the "
            f"{HERO_MIN_WIDTH}x{HERO_MIN_HEIGHT} this lane serves - a {HERO_MIN_WIDTH} px fetch "
            "keeps the aspect ratio and returns that very box, so there is nothing to download"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.fetching")
    if tmp.exists():
        tmp.unlink()
    result = DL.download_image(original_url, tmp, original_width)
    os.replace(tmp, dest)
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
        except (FetchError, DL.DownloadError, OSError) as exc:
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


# --------------------------------------------------------------------------- the resumable run
@dataclass(frozen=True)
class FetchRun:
    """What one `run_fetch` did: how many targets it had, how many files it wrote, how many the
    manifest already carried, and every site it refused with the downloader's own wording."""

    targets: int
    fetched: int
    already: int
    manifest_sha256: str
    failures: list[tuple[str, str, str]]

    def as_json(self) -> dict[str, Any]:
        by_reason: dict[str, int] = {}
        for _, _, why in self.failures:
            key = why.split(":", 1)[0]
            by_reason[key] = by_reason.get(key, 0) + 1
        return {
            "targeted": self.targets,
            "fetched": self.fetched,
            "already_in_the_manifest": self.already,
            "manifest_sha256": self.manifest_sha256,
            "failed": len(self.failures),
            "failures": by_reason,
        }


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    """The manifest an interrupted fetch left behind, or an empty one.

    A manifest that is not readable JSON is refused by name rather than treated as empty: a fetch
    that starts again from nothing would re-download files `download_image`'s `O_EXCL` refuses to
    overwrite, and the run would die on the first of them with a message about a lock.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(
            f"{path} is not readable JSON ({exc}) - it is the record of the files already on disk, "
            "so a fresh fetch over it would collide with `download_image`'s O_EXCL"
        ) from exc
    if not isinstance(data, dict):
        raise FetchError(
            f"{path} holds a {type(data).__name__}, not the {{site id: manifest entry}} mapping the "
            "plan reads"
        )
    return {str(site): dict(entry) for site, entry in data.items()}


def save_manifest(path: Path, manifest: Mapping[str, Mapping[str, str]]) -> str:
    """`FETCHED.json`, replaced atomically after **every** site, and its sha256 returned.

    This is the counterpart to `write_manifest`'s once-per-run rule, and the reason the module's own
    docstring names: `download_image()` opens with `O_EXCL`, so a wave interrupted after some
    hundred files has left those files on disk and cannot be run over them again. Carrying the
    manifest along is what makes the second run a continuation and not a collision. The replacement
    goes through a temporary file, so an interruption in the middle of a write cannot leave a
    half-written manifest behind either.
    """
    text = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _append_refusal(path: Path, site_id: str, commons_file: str, why: str) -> None:
    """One refusal per line, appended: a site that failed is retried by the next run, never skipped."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"site_id": site_id, "commons_file": commons_file, "why": why},
        ensure_ascii=False,
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{line}\n")


def run_fetch(
    targets: Sequence[tuple[str, str]],
    root: Path,
    manifest_path: Path,
    *,
    failures_path: Path | None = None,
    delay_s: float | None = None,
    on_site: Any = None,
) -> FetchRun:
    """Fetch every target, carrying `FETCHED.json` along after each file, so the run can be continued.

    `fetch_manifest` holds the whole wave in memory and hands it over at the end, which is the right
    shape for a test and the wrong one for 800 downloads against a host that may drop the link. This
    is the same loop with three differences, each forced by `O_EXCL`: a target the manifest already
    carries is skipped (its file is on disk), a site that fails is recorded by name and left for the
    next run, and the manifest is written the moment a file lands.

    A run that ends with an empty manifest is refused outright, manifest and failures alike: the
    plan would keep refusing every one of those sites as `local_file_too_small`.
    """
    from pipeline import wiki_image_downloader as DL

    pace = DL.WIKIPEDIA_DELAY if delay_s is None else delay_s
    manifest = load_manifest(manifest_path)
    failures: list[tuple[str, str, str]] = []
    fetched = 0
    skipped = 0
    digest = ""
    for site_id, commons_file in targets:
        if site_id in manifest:
            skipped += 1
            continue
        try:
            entry = fetch_site(site_id, commons_file, root)
        except (FetchError, DL.DownloadError, OSError) as exc:
            why = f"the fetch failed: {exc}"
            failures.append((site_id, commons_file, why))
            if failures_path is not None:
                _append_refusal(failures_path, site_id, commons_file, why)
            time.sleep(pace)
            continue
        manifest[site_id] = entry
        digest = save_manifest(manifest_path, manifest)
        fetched += 1
        if on_site is not None:
            on_site(site_id, entry)
        time.sleep(pace)
    if not manifest:
        names = ", ".join(f"{sid} ({name})" for sid, name, _ in failures[:3])
        raise FetchError(
            f"no file of this wave could be fetched ({len(failures)} failed, first: {names}) - the "
            f"plan would then keep refusing every one of them as `local_file_too_small`"
        )
    return FetchRun(
        targets=len(targets),
        fetched=fetched,
        already=skipped,
        manifest_sha256=digest
        or hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        failures=failures,
    )
