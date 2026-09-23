"""T09 - the true Commons original dimensions of every image, and which hero a site could
actually carry.

`wiki_images.width`/`height` are **not** Commons dimensions. They are the pixel size of the
local `.webp` that `public/data/images/wiki/<site>/<file>` serves, and that derivative was
requested at a fixed width: `THUMB_WIDTH = 800` for the hero, `GALLERY_WIDTH = 1600` for
everything else (`pipeline/wiki_image_downloader.py:47-48`). `file_size_bytes` is the byte
size of that same local file (`wiki_image_downloader.py:725` writes
`dest_path.stat().st_size`; `scripts/reindex_wiki_images.py:95` writes
`img_path.stat().st_size`), and all 49,691 rows came through the re-index path
(`thumb_width IS NULL` on every row, plan §6.2). Two consequences decide this module:

* Comparing `file_size_bytes` with the `size` `imageinfo` reports would flag 43,020 of the
  49,028 comparable rows (87.7%) - a WebP re-encode of a downscaled derivative is almost
  always smaller than the original file (median ratio 0.137). That is a category error, not a
  defect list, so it is not reported. The measured numbers are in
  `output/remediation/t09_label_measurement.py`.
* Comparing `width`/`height` with the original is only a defect where the derivative
  *misrepresents* the file to the caller: an upscaled crop (the local file has more pixels
  than its source ever had - the project's own label set calls this "die DB-Maße täuschen
  Qualität vor"), or a hero stuck at the 800 px cap of §6.3. A 1600 px gallery crop of a
  4000 px original is deliberate (the downloader's comment: "avoids OOM on huge panoramas")
  and is therefore **not** a finding.

What the census needs from the truth is the hero decision, because §6.3 states every hero is
broken and Phase 2 item 1 repairs 3,264 of them without a single download. That number is
reproducible: "non-excluded, not the hero, `width >= 1600 AND height >= 900`" over this
snapshot yields exactly 3,264 sites, so those two thresholds are the plan's own rule rather
than a guess made here. They are also why the short side matters: a 1600x609 panorama strip
is already local and still unusable as a hero (§6.1 labels 84 such images "zu_klein").

The module answers, per site, one question with one finding - what has to happen to the hero:

    T09/hero-not-best        a local 1600x900+ image exists, the hero is a smaller one
                             -> move the flag, no download (Phase 2 item 1). Among several
                             such images the one whose stored size its own original backs
                             wins over a larger upscale - 1,122 sites have both.
    T09/no-hero-flag         such an image exists but no served row carries `is_hero`
    T09/hero-redownload      none exists locally, but an original is big enough that a
                             re-export at 1600 px would qualify -> re-fetch, not re-pick
    T09/hero-new-fetch       no original is big enough either -> a new image is needed
    T09/no-servable-image    every row is excluded -> nothing to serve, and nothing to measure
    T09/hero-undecidable     the truth is unknown for at least one row -> cannot decide
    T09/no-images            the site has no `wiki_images` row at all

plus the row-level defects the truth exposes (`commons-missing`, `unresolved`,
`no-commons-identity`, `stored-dims-missing`, `upscaled`).

**Nothing here is auto-applicable, deliberately.** The hero repair is a two-row change -
`is_hero = false` on the old row *and* `true` on the new one - and a single-field SET cannot
express it. A half-applied move is worse than none: `api/routes/sites_html.py:328` picks the
image with `ORDER BY is_hero DESC, is_lead DESC, sort_order`, and the current hero holds
`sort_order = 0`, so a lone SET on the candidate leaves the 800 px file in place while the
census would report the site as repaired. Both rows therefore go to Phase 2 as a REVIEW
finding that names the exact pair. Quality is not dimension: the largest available image is
not automatically the best hero (see T10's tier signals), and this module claims no more than
the pixel size it measured.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from census.fetch import FetchError
from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T09"
NAME = "true Commons original dimensions and hero eligibility"
DIMENSION = "images / dimensions"

#: Commons `imageinfo` batch endpoint. 50 titles per request is the unauthenticated limit.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
BATCH = 50
IIPROP = "size|url|extmetadata"
CACHE_NS = "commons"
INDEX_NAME = "commons_imageinfo.json"

#: Phase 2 item 1 ("an already-local 1600 px gallery image") and §6.1's "too small" class
#: (short side under 900). Not free parameters: this pair reproduces the plan's 3,264
#: locally-repairable heroes exactly.
HERO_MIN_WIDTH = 1600
HERO_MIN_HEIGHT = 900

log = logging.getLogger("census.t09")

#: The export caps every row of the 2026-09-20 snapshot was downloaded under. Until 2026-09-23
#: this module read them from the downloader's source, so that a changed value could not make its
#: explanation stale. That day the downloader replaced both with a fetch rule over Commons' fixed
#: thumbnail buckets (`LOCAL_MAX_WIDTH`, `fetch_plan` in `pipeline/wiki_image_downloader.py`):
#: 800 and 1600 are not buckets and answer HTTP 400. The rows this module explains were made under
#: these two values and no others, so they are pinned here as the history they are.
HISTORIC_CAPS = {"THUMB_WIDTH": 800, "GALLERY_WIDTH": 1600}


def _pipeline_widths() -> dict[str, int]:
    """The caps the census's rows were downloaded under (see `HISTORIC_CAPS`)."""
    return dict(HISTORIC_CAPS)


# --------------------------------------------------------------------------- Commons names
def _file_name_from_url(url: Any) -> str | None:
    """The Commons file name (with extension) a URL points at, or None.

    Only `upload.wikimedia.org/wikipedia/commons/**` (an original) and
    `commons.wikimedia.org/wiki/File:**` (a file page) are Commons file references. A local
    path (`/data/images/wiki/...`) is not.
    """
    if not url or not isinstance(url, str):
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = unquote(parsed.path)
    if host == "commons.wikimedia.org":
        if "/wiki/" not in path:
            return None
        name = path.rsplit("/", 1)[-1]
        return name[5:] if name[:5].lower() == "file:" else None
    if host.endswith("wikimedia.org"):
        if "/wikipedia/commons/" not in path:
            return None
        name = path.rsplit("/", 1)[-1]
        return name or None
    return None


def _commons_file_name(row: dict[str, Any]) -> str | None:
    """The Commons file this image row refers to, or None if the row has no Commons identity.

    Derived from the URLs, never from `title`: for the rows the re-index script wrote, `title`
    is the *local* file stem with underscores replaced (truncated at 100 characters by
    `scripts/reindex_wiki_images.py`), which is not a Commons title at all.
    """
    for key in ("original_url", "commons_page_url"):
        name = _file_name_from_url(row.get(key))
        if name:
            return name
    return None


# ------------------------------------------------------------------------------ collecting
def _all_names(ctx: Context) -> list[str]:
    """Every distinct Commons file name referenced by the snapshot, sorted for stability."""
    names: set[str] = set()
    for row in ctx.snap.rows("wiki_images"):
        name = _commons_file_name(row)
        if name:
            names.add(name)
    return sorted(names)


def _params(batch: list[str]) -> dict[str, Any]:
    return {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "imageinfo",
        "iiprop": IIPROP,
        "titles": "|".join(f"File:{n}" for n in batch),
        # Follow renames instead of reporting the old title as missing.
        "redirects": 1,
        # Wikimedia etiquette: answer with 503 under load rather than hammering the replica.
        "maxlag": 5,
    }


def _fetch_batch(ctx: Context, batch: list[str]) -> dict[str, Any]:
    """One batch, or a raised error. Never an empty result.

    `maxlag` is reported as HTTP 200 with an `error` object, and the Fetcher caches whatever
    came back - so a naive read would store that error as "no imageinfo for these 50 files"
    and turn a busy replica into 50 silently unverified rows. Detect it, refetch past the
    cache, and fail loudly if the API keeps refusing.
    """
    fetcher = ctx.net()
    last: str = ""
    for attempt in range(3):
        payload = fetcher.get_json(COMMONS_API, _params(batch), ns=CACHE_NS, force=attempt > 0)
        j = payload.get("json") or {}
        err = j.get("error")
        if not err:
            if "query" not in j:
                raise RuntimeError(
                    f"commons imageinfo: response without 'query' for a batch of "
                    f"{len(batch)} titles (first: {batch[0]!r})"
                )
            if j.get("warnings"):
                log.warning("commons imageinfo warnings: %s", j["warnings"])
            return j
        last = str(err)
        log.warning("commons imageinfo error (attempt %d/3): %s", attempt + 1, last)
    raise RuntimeError(f"commons imageinfo refused a batch (first title {batch[0]!r}): {last}")


def _dereference(title: str, mapping: dict[str, str]) -> str:
    """Apply the API's own `normalized`/`redirects` chains (bounded, in case of a loop)."""
    for _ in range(4):
        nxt = mapping.get(title)
        if nxt is None or nxt == title:
            break
        title = nxt
    return title


def _read_batch(batch: list[str], payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map every title of one batch to its own status - never assume the answers align.

    Commons answers only for the titles it recognises, in an order it chooses, under the name
    it normalised them to. A partial response is normal, so every requested title gets a
    record: `ok` with the original's pixel size, `missing` (the canonical source itself says
    the file does not exist), or `unresolved` (no answer - we could not find out).
    """
    query = payload.get("query") or {}
    pages: dict[str, dict[str, Any]] = {p["title"]: p for p in query.get("pages") or []}
    normalized = {e["from"]: e["to"] for e in query.get("normalized") or []}
    redirects = {e["from"]: e["to"] for e in query.get("redirects") or []}

    out: dict[str, dict[str, Any]] = {}
    for name in batch:
        title = _dereference(_dereference(f"File:{name}", normalized), redirects)
        page = pages.get(title)
        if page is None:
            out[name] = {"status": "unresolved", "canonical": None}
            continue
        canonical = page.get("title")
        if page.get("missing"):
            out[name] = {"status": "missing", "canonical": canonical}
            continue
        info = (page.get("imageinfo") or [None])[0]
        if not info or not info.get("width") or not info.get("height"):
            out[name] = {"status": "unresolved", "canonical": canonical}
            continue
        out[name] = {
            "status": "ok",
            "canonical": canonical,
            "width": info["width"],
            "height": info["height"],
            "bytes": info.get("size"),
            "url": info.get("url"),
        }
    return out


def _index_path(ctx: Context) -> Path:
    return Path(ctx.cache) / INDEX_NAME


def _entries_for(ctx: Context, batch: list[str], splits: list[int]) -> dict[str, dict[str, Any]]:
    """The truth for every title of one batch, splitting the request when Commons refuses it.

    50 long titles can exceed the request-URI limit (HTTP 414). That is the one refusal a
    smaller request fixes, so it is answered with two smaller ones - down to a single title,
    which is raised if it still fails. Every other failure is raised as it is: a transport
    error must never be retried into a hole in the census.
    """
    try:
        return _read_batch(batch, _fetch_batch(ctx, batch))
    except FetchError as exc:
        if "414" not in str(exc) or len(batch) == 1:
            raise
        mid = len(batch) // 2
        log.warning("T09: HTTP 414 on a %d-title batch, asking in two halves", len(batch))
        splits.append(len(batch))
        out = _entries_for(ctx, batch[:mid], splits)
        out.update(_entries_for(ctx, batch[mid:], splits))
        return out


def collect(ctx: Context) -> None:
    """Query `imageinfo` for every referenced file and fold the answers into one index.

    ~922 batches, cached per request by the Fetcher, so an interrupted run resumes where it
    stopped. The batches are derived from the sorted title list, so a re-run asks the identical
    questions and hits the identical cache entries.
    """
    names = _all_names(ctx)
    batches = [names[i : i + BATCH] for i in range(0, len(names), BATCH)]
    log.info("T09: %d distinct Commons files in %d batches", len(names), len(batches))

    splits: list[int] = []
    results = ctx.net().map(
        lambda b: _entries_for(ctx, b, splits), batches, desc="T09 commons imageinfo"
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        # A partial sweep must not look like a finished one: an index missing rows would turn
        # into "this file has no Commons identity" for images that were never asked about.
        raise RuntimeError(
            f"T09: {len(failures)}/{len(batches)} imageinfo batches failed; first: "
            f"{failures[0]!r}. Nothing was indexed - re-run to resume from the cache."
        )

    entries: dict[str, dict[str, Any]] = {}
    for got in results:
        entries.update(got)

    summary: dict[str, int] = {}
    for rec in entries.values():
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
    index = {
        "api": COMMONS_API,
        "iiprop": IIPROP,
        "batch": BATCH,
        "snapshot_exported_at": ctx.snap.exported_at(),
        "split_batches": len(splits),
        "summary": summary,
        "entries": entries,
    }
    path = _index_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a killed run leaves no half index
    log.info("T09: indexed %d files (%s) -> %s", len(entries), summary, path)


def _read_index(ctx: Context) -> dict[str, dict[str, Any]]:
    """The folded imageinfo index, or a clear failure - never an empty result.

    A census that answered "no findings" because the collection never happened would report a
    broken hero pipeline as clean.
    """
    path = _index_path(ctx)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing - run the collector first "
            "(`run.py --tests T09 --collect-only`), then the census against the same cache"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    exported = ctx.snap.exported_at()
    if payload.get("snapshot_exported_at") != exported:
        raise RuntimeError(
            f"{path} was collected from snapshot {payload.get('snapshot_exported_at')!r} but "
            f"the snapshot in use now is {exported!r} - re-collect before trusting the sizes"
        )
    entries: dict[str, dict[str, Any]] = payload["entries"]
    expected = set(_all_names(ctx))
    absent = expected - set(entries)
    extra = set(entries) - expected
    if absent or extra:
        raise RuntimeError(
            f"{path} does not match this snapshot: {len(absent)} referenced file(s) unindexed "
            f"(first: {sorted(absent)[:3]}), {len(extra)} indexed file(s) no longer referenced"
        )
    return entries


# --------------------------------------------------------------------- evidence builders
def _commons_evidence(rec: dict[str, Any], name: str) -> Evidence:
    """The canonical source's own answer for one file."""
    if rec["status"] == "ok":
        quote = (
            f"File:{name} -> {rec['canonical']}: {rec['width']}x{rec['height']}, "
            f"{rec['bytes']} bytes (imageinfo {IIPROP})"
        )
        return Evidence(source="commons:imageinfo", url=rec.get("url"), quote=quote)
    return Evidence(
        source="commons:imageinfo",
        url=f"{COMMONS_API}?action=query&prop=imageinfo&format=json&titles=File:{name}",
        quote=f"File:{name} -> {rec['canonical']!r}: {rec['status']}",
    )


def _row_evidence(img: dict[str, Any], **facts: Any) -> Evidence:
    extra = " ".join(f"{k}={v}" for k, v in facts.items())
    return Evidence(
        source="snapshot:wiki_images",
        quote=(
            f"id={img['id']} site_id={img['site_id']} filename={img['filename']!r} "
            f"is_hero={img['is_hero']} is_excluded={img['is_excluded']} "
            f"width={img['width']} height={img['height']} "
            f"file_size_bytes={img['file_size_bytes']} {extra}".strip()
        ),
    )


def _stored_dims(img: dict[str, Any]) -> tuple[int, int] | None:
    w, h = img.get("width"), img.get("height")
    if not w or not h:
        return None
    return int(w), int(h)


def _hero_ready(width: int, height: int) -> bool:
    """Phase 2's rule, on a stored file or on a 1600 px projection of an original."""
    return width >= HERO_MIN_WIDTH and height >= HERO_MIN_HEIGHT


def _as_derivative(rec: dict[str, Any]) -> tuple[int, int] | None:
    """The size a re-export at HERO_MIN_WIDTH would have, or None if it cannot reach it."""
    if rec["status"] != "ok":
        return None
    w, h = rec["width"], rec["height"]
    if w < HERO_MIN_WIDTH:
        return None  # re-downloading cannot invent pixels
    return HERO_MIN_WIDTH, round(h * HERO_MIN_WIDTH / w)


def _img_ref(img: dict[str, Any]) -> str:
    return f"wiki_images id={img['id']} ({img['filename']!r})"


def _is_upscale(dims: tuple[int, int] | None, truth: tuple[int, int] | None) -> bool:
    """True when the local file has more pixels than its original ever had."""
    return bool(dims and truth and truth[0] and dims[0] > truth[0])


# ------------------------------------------------------------------------------- the rows
def _row_findings(
    sid: str, img: dict[str, Any], rec: dict[str, Any] | None, caps: dict[str, int]
) -> list[Finding]:
    """The defects this row's own truth exposes. The hero decision is made per site."""
    name = _commons_file_name(img) or "?"
    dims = _stored_dims(img)

    if rec is None:
        provenance = (
            " (author and license are NULL as well)"
            if (not img.get("author") and not img.get("license"))
            else ""
        )
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/no-commons-identity",
                field="wiki_images.original_url",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "image_id": img["id"],
                    "original_url": img["original_url"],
                    "commons_page_url": img["commons_page_url"],
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note="no Commons file reference to measure against - the row carries a local path "
                "and no Commons page, so its true size is unknowable from here" + provenance,
                evidence=[_row_evidence(img, field="original_url")],
            )
        ]

    status = rec["status"]
    if status == "missing":
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/commons-missing",
                field="wiki_images.commons_page_url",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "image_id": img["id"],
                    "commons_page_url": img["commons_page_url"],
                    "original_url": img["original_url"],
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.AUTHORITATIVE,
                note="Commons reports this file as missing (deleted or renamed), so the attribution "
                f"link serves a 404. Hero row: {img['is_hero']}.",
                evidence=[_commons_evidence(rec, name), _row_evidence(img)],
            )
        ]
    if status == "unresolved":
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/unresolved",
                field="wiki_images.original_url",
                severity=Severity.COSMETIC,
                dimension=DIMENSION,
                current_value={"image_id": img["id"], "original_url": img["original_url"]},
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note="the imageinfo batch named this file and the API returned no answer for it "
                f"(canonical title {rec['canonical']!r}) - could not check, not checked clean",
                evidence=[_commons_evidence(rec, name), _row_evidence(img)],
            )
        ]

    if dims is None:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/stored-dims-missing",
                field="wiki_images.width",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "image_id": img["id"],
                    "width": img["width"],
                    "height": img["height"],
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note="the row has no local dimensions, so the pages cannot emit "
                "<img width height> (the layout-shift defect "
                "scripts/backfill_image_dimensions.py exists for) - the Commons original is "
                f"{rec['width']}x{rec['height']}",
                evidence=[_commons_evidence(rec, name), _row_evidence(img)],
            )
        ]

    stored_w, stored_h = dims
    # A hero below the export cap is reported once, by the site's hero decision, which carries
    # both numbers - not twice for one defect.
    if not img["is_hero"] and stored_w > rec["width"]:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/upscaled",
                field="wiki_images.width",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={"image_id": img["id"], "width": stored_w, "height": stored_h},
                proposal=Proposal.REVIEW,
                confidence=Confidence.AUTHORITATIVE,
                note=f"the local file is {stored_w}x{stored_h}, a "
                f"{stored_w / rec['width']:.1f}x upscale of the {rec['width']}x{rec['height']} "
                f"original: the stored dimensions claim detail the source never had "
                f"({rec['bytes']} bytes on Commons). GALLERY_WIDTH="
                f"{caps['GALLERY_WIDTH']} px is what forced the crop up.",
                evidence=[_commons_evidence(rec, name), _row_evidence(img)],
            )
        ]

    log.debug(
        "T09: %s clean against Commons %dx%d (THUMB_WIDTH=%d)",
        _img_ref(img),
        rec["width"],
        rec["height"],
        caps["THUMB_WIDTH"],
    )
    return []


def _hero_finding(
    sid: str, imgs: list[dict[str, Any]], index: dict[str, dict[str, Any]], caps: dict[str, int]
) -> list[Finding]:
    """One finding per site: what has to happen to this site's hero, and why."""
    heroes = [r for r in imgs if r["is_hero"] and not r["is_excluded"]]
    # sites_html.py orders by is_hero DESC, is_lead DESC, sort_order - the served hero.
    current = max(heroes, key=lambda r: (bool(r["is_lead"]), -(r["sort_order"] or 0)), default=None)

    def true_dims(row: dict[str, Any]) -> tuple[int, int] | None:
        name = _commons_file_name(row)
        rec = index.get(name) if name else None
        if rec is None or rec["status"] != "ok":
            return None
        return int(rec["width"]), int(rec["height"])

    candidates = []
    for row in imgs:
        if row["is_hero"] or row["is_excluded"]:
            continue
        dims = _stored_dims(row)
        if dims and _hero_ready(*dims):
            candidates.append(row)

    served_dims = _stored_dims(current) if current is not None else None
    if served_dims and _hero_ready(*served_dims):
        return []  # the hero already satisfies Phase 2's requirement

    thumb_cap = caps["THUMB_WIDTH"]

    if current is not None:
        hero_desc = f"{current['width']}x{current['height']} (image id={current['id']})"
    else:
        hero_desc = "none"

    if candidates:

        def cand_key(row: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
            dims = _stored_dims(row) or (0, 0)
            truth = true_dims(row) or (0, 0)
            # A candidate that is itself an upscaled crop promises pixels its source does not
            # have (1,383 of the 3,264 sites have such a candidate, 1,122 of them also have a
            # backed one). Prefer the backed file; among equals, the larger one.
            backed = int(not _is_upscale(dims, true_dims(row)))
            return (
                backed,
                dims[0] * dims[1],
                dims[0],
                truth[0],
                truth[1],
                -(row["sort_order"] or 0),
            )

        best = max(candidates, key=cand_key)
        best_dims = _stored_dims(best) or (0, 0)
        best_truth = true_dims(best)
        best_upscaled = _is_upscale(_stored_dims(best), best_truth)
        if current is not None:
            note = (
                f"the served hero is {hero_desc}, the THUMB_WIDTH={thumb_cap} px derivative, "
                f"while {_img_ref(best)} is already local at {best_dims[0]}x{best_dims[1]}"
                + (
                    f" (Commons original {best_truth[0]}x{best_truth[1]}"
                    + (", which makes it an upscaled crop itself" if best_upscaled else "")
                    + ")"
                    if best_truth
                    else ""
                )
                + ". Moving the flag needs both rows: is_hero=false on the old, true on the "
                "new. A lone SET keeps serving the old file, because "
                "api/routes/sites_html.py orders by is_hero DESC, is_lead DESC, sort_order "
                "and the current hero holds sort_order=0. Dimension rule only "
                f"(w>={HERO_MIN_WIDTH}, h>={HERO_MIN_HEIGHT}): content quality is T10's."
            )
            test_id = f"{TEST_ID}/hero-not-best"
        else:
            note = (
                f"{len(candidates)} image(s) are already local at {HERO_MIN_WIDTH}x"
                f"{HERO_MIN_HEIGHT}+ but no served row carries is_hero=true - the hero flag is "
                f"lost (the page then falls back to is_lead/sort_order). Best candidate: "
                f"{_img_ref(best)} at {best_dims[0]}x{best_dims[1]}."
            )
            test_id = f"{TEST_ID}/no-hero-flag"
        return [
            Finding(
                site_id=sid,
                test_id=test_id,
                field="wiki_images.is_hero",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "hero": hero_desc,
                    "replacement_image_id": best["id"],
                    "replacement": f"{best_dims[0]}x{best_dims[1]}",
                    "replacement_is_upscaled": best_upscaled,
                    "candidates": len(candidates),
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.AUTHORITATIVE,
                note=note,
                evidence=[
                    Evidence(
                        source="snapshot:wiki_images",
                        quote=f"candidate id={best['id']} site_id={sid} width={best['width']} "
                        f"height={best['height']} file_size_bytes="
                        f"{best['file_size_bytes']} is_hero={best['is_hero']} "
                        f"is_excluded={best['is_excluded']}",
                    ),
                    Evidence(
                        source="snapshot:wiki_images",
                        quote=f"hero id={current['id'] if current else None} "
                        f"width={current['width'] if current else None} "
                        f"height={current['height'] if current else None} "
                        f"sort_order={current['sort_order'] if current else None}",
                    ),
                ],
            )
        ]

    # No local image qualifies. The true originals decide what the remaining work is - the
    # number Phase 2 needs in order to size its fetches, and only knowable from imageinfo.
    if not imgs:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/no-images",
                field="wiki_images",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={"images": 0},
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note="the site has no wiki_images row at all: no local image can be its hero and "
                "there is nothing to measure. Image acquisition (Phase 2 item 5).",
                evidence=[
                    Evidence(source="snapshot:wiki_images", quote=f"0 rows for site_id={sid}")
                ],
            )
        ]

    served = [r for r in imgs if not r["is_excluded"]]
    local_sizes = sorted(
        {(r["width"], r["height"]) for r in imgs}, key=lambda t: -((t[0] or 0) * (t[1] or 0))
    )[:3]
    common = (
        f"{len(imgs)} image(s), {len(served)} not excluded, largest local "
        f"{local_sizes}, hero {hero_desc}"
    )
    snapshot_evidence = Evidence(
        source="snapshot:wiki_images",
        quote=f"site_id={sid}: {common}; none reaches {HERO_MIN_WIDTH}x{HERO_MIN_HEIGHT}",
    )

    if not served:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/no-servable-image",
                field="wiki_images.is_excluded",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={"images": len(imgs), "excluded": len(imgs), "hero": hero_desc},
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note="every image row of this site is excluded, so no existing image can be its "
                "hero - either a new image is needed or the exclusion was wrong",
                evidence=[_row_evidence(imgs[0], field="is_excluded"), snapshot_evidence],
            )
        ]

    resolved: list[tuple[dict[str, Any], dict[str, Any]]] = []
    redownloadable: list[tuple[dict[str, Any], int, int]] = []
    unknown: list[dict[str, Any]] = []
    for row in served:
        name = _commons_file_name(row)
        rec = index.get(name) if name else None
        if rec is None or rec["status"] != "ok":
            unknown.append(row)
            continue
        resolved.append((row, rec))
        projected = _as_derivative(rec)
        if projected and _hero_ready(*projected):
            redownloadable.append((row, int(rec["width"]), int(rec["height"])))

    if redownloadable:
        row, ow, oh = max(redownloadable, key=lambda t: t[1] * t[2])
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/hero-redownload",
                field="wiki_images.is_hero",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "hero": hero_desc,
                    "largest_original": f"{ow}x{oh}",
                    "redownloadable_rows": len(redownloadable),
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.AUTHORITATIVE,
                note=f"no local image qualifies as a hero ({common}), but {_img_ref(row)} has a "
                f"{ow}x{oh} original on Commons, so an export at {HERO_MIN_WIDTH} px would "
                f"give {HERO_MIN_WIDTH}x{round(oh * HERO_MIN_WIDTH / ow)} - no new image "
                "needed, raise THUMB_WIDTH/HERO_WIDTH and re-fetch (Phase 2 item 1).",
                evidence=[
                    _commons_evidence(
                        index[_commons_file_name(row) or ""], _commons_file_name(row) or "?"
                    ),
                    _row_evidence(row),
                ],
            )
        ]
    if unknown:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/hero-undecidable",
                field="wiki_images.is_hero",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={"hero": hero_desc, "unverified_rows": len(unknown)},
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note=f"no local image qualifies as a hero ({common}) and the true size of "
                f"{len(unknown)} of them is unknown, so whether a re-export would do or a new "
                "image is needed cannot be decided from here",
                evidence=[_row_evidence(unknown[0], field="unverified"), snapshot_evidence],
            )
        ]

    best_row, best_rec = max(resolved, key=lambda t: t[1]["width"] * t[1]["height"])
    proj = _as_derivative(best_rec)
    best_quote = (
        f"largest original of the site's files: File:{_commons_file_name(best_row)} "
        f"is {best_rec['width']}x{best_rec['height']}, whose {HERO_MIN_WIDTH} px "
        f"derivative would be {proj[0]}x{proj[1]} - below {HERO_MIN_HEIGHT} px high"
        if proj
        else f"largest original of the site's files: File:{_commons_file_name(best_row)} "
        f"is only {best_rec['width']}x{best_rec['height']}, narrower than "
        f"{HERO_MIN_WIDTH} px"
    )

    if resolved:
        return [
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/hero-new-fetch",
                field="wiki_images.is_hero",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value={
                    "hero": hero_desc,
                    "images": len(imgs),
                    "largest_original": f"{best_rec['width']}x{best_rec['height']}",
                },
                proposal=Proposal.REVIEW,
                confidence=Confidence.AUTHORITATIVE,
                note=f"no local image qualifies as a hero ({common}) and no original on Commons is "
                f"big enough either (checked for all {len(served)} non-excluded rows; largest "
                f"{best_rec['width']}x{best_rec['height']}): this site needs a new image, not "
                "a bigger export.",
                evidence=[
                    Evidence(source="commons:imageinfo", url=best_rec.get("url"), quote=best_quote),
                    snapshot_evidence,
                ],
            )
        ]
    # Unreachable in this shape: `unknown` is empty above, so every served row resolved.
    # Kept loud so a later refactor cannot turn this into a silent "nothing to report".
    raise AssertionError(f"site {sid}: {len(served)} servable rows, none resolved, none unknown")


def run(ctx: Context) -> list[Finding]:
    index = _read_index(ctx)
    caps = _pipeline_widths()

    findings: list[Finding] = []
    for site in ctx.sites:
        sid = str(site["id"])
        imgs = ctx.snap.images(sid)
        for img in imgs:
            name = _commons_file_name(img)
            findings.extend(_row_findings(sid, img, index.get(name) if name else None, caps))
        findings.extend(_hero_finding(sid, imgs, index, caps))
    return findings
