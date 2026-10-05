"""The 2025 import's linked image takes the hero flag (WD2/IH, owner decision 2026-10-05).

The owner's source is `data/raw/ancient_nerds/ancient_nerds_original.geojson` (2025-12-18): its
`Images` property is the image the hand linked per site, and the loader wrote it into
`unified_sites.thumbnail_url` (`pipeline/unified_loader.py:1200`). Owner decision 2026-10-05,
17:43: *everything the import links wins as hero*, and 17:54: of the 1,980 promotions the 427
whose local file is smaller than 1600x900 are to be fetched at 1600 px first.

This module is the plan for the part that needs no new infrastructure: the target file is
already a row of the site, so the write is the hero flag, the flag it takes from, the row's
`is_excluded` where the page hid it, and the thumbnail that must follow the served image. Every
other class is **refused by name** with the reason, never counted into the plan:

* a local file under 1600x900 whose 1600 px derivative has not been fetched (`fetched` manifest);
* a site whose import image is no row of the site at all - that needs a row this writer cannot
  create (`chunk_writer` writes conditional UPDATEs through `apply_remediation_change()`);
* an import link that names no Commons file, which no row can hold.

The writer's own transaction proves the rest: at most one hero per touched site, no hero on an
excluded row, every planned row still holding its old value, the journal agreeing both ways.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation", _HERE.parent.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gallery_audit.chunk_writer import (  # noqa: E402
    CURATED_SOURCE,
    Change,
    ChunkError,
    Lane,
    chunk_changes,
    emit_chunks,
)
from hero_repair.thumbnail import local_path  # noqa: E402
from served_image import state as ST  # noqa: E402

#: The import file of 2025-12-18, the only surviving copy of the hand-linked images. It is passed
#: in, never guessed: the data root is the main checkout's, and a worktree holds no `data/`
#: (the period lane measured the same gap, GOAL_PERIODS.md).
IMPORT_FILE_NAME = "ancient_nerds_original.geojson"

#: The hero flag moves to the import's file.
RULE_HERO = "ih1"
#: The row that held the flag gives it up (at most one hero per site, T09's invariant).
RULE_DEMOTE = "ih2"
#: A row the page hid (`is_excluded`) becomes visible again, so it can carry the flag at all.
RULE_UNHIDE = "ih3"
#: The thumbnail follows the served image - the hero repair's T1 target.
RULE_THUMBNAIL = "ih4"
#: The fetched 1600 px file's own columns: pixels, caption, author and licence together.
RULE_FETCH = "ih5"

#: The local derivative a hero must reach, from `census.tests.t09_commons_dimensions`.
HERO_MIN_WIDTH = 1600
HERO_MIN_HEIGHT = 900


class ImportHeroError(ChunkError):
    """A read, a join or a claim this lane must not turn into a write. Nothing was sent."""


# --------------------------------------------------------------------------- the join
def fold(text: str) -> str:
    """Compare names the way the pipeline does: accents folded, case and spacing ignored."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def url_key(url: str) -> str:
    url = str(url or "").strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    url = re.sub(r"^https?://", "", url)
    return url.rstrip("/").replace("_", " ")


def read_import(path: Path) -> list[dict[str, Any]]:
    """The import's features, each with the image it links (`Images`) and the keys it joins on."""
    if not path.is_file():
        raise ImportHeroError(
            f"{path} does not exist - the 2025 import is the only surviving copy of the "
            "hand-linked images (the database kept neither, see GOAL_PERIODS.md). Pass the "
            f"main checkout's data/raw/ancient_nerds/{IMPORT_FILE_NAME}."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ImportHeroError(f"{path} holds no feature")
    out = []
    for number, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        image = str(props.get("Images") or "").strip()
        out.append(
            {
                "feature": number,
                "title": str(props.get("Title") or "").strip(),
                "source_url": str(props.get("Source") or "").strip(),
                "image": image or None,
                "image_host": (urlsplit(image).hostname or "").lower() if image else None,
            }
        )
    return out


def join_import(
    state: ST.State, features: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """The import feature of every curated site, on the key the period lane proved: the source
    URL first, the folded title second, first hit wins. Ambiguity is reported, not resolved."""
    by_url: dict[str, list[Mapping[str, Any]]] = {}
    by_title: dict[str, list[Mapping[str, Any]]] = {}
    for feature in features:
        by_url.setdefault(url_key(str(feature["source_url"])), []).append(feature)
        by_title.setdefault(fold(str(feature["title"])), []).append(feature)

    out: dict[str, dict[str, Any]] = {}
    for sid, site in state.sites.items():
        hits = by_url.get(url_key(str(site.get("source_url") or "")), [])
        matched_on = "url"
        if not hits:
            hits = by_title.get(fold(str(site.get("name") or "")), [])
            matched_on = "title"
        out[sid] = {
            "matched_on": matched_on if hits else None,
            "ambiguous": len(hits) > 1,
            "image": str(hits[0]["image"]) if hits and hits[0]["image"] else None,
            "image_host": hits[0]["image_host"] if hits else None,
            "import_title": hits[0]["title"] if hits else None,
            "features": len(hits),
        }
    return out


# --------------------------------------------------------------------------- the plan
@dataclass(frozen=True)
class Refusal:
    site_id: str
    reason: str
    detail: str

    def as_json(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "reason": self.reason, "detail": self.detail}


def _target_row(state: ST.State, sid: str, image: str) -> tuple[dict[str, Any] | None, str | None]:
    """The row of the site that holds the import file, live or hidden, and why there is none."""
    wanted = ST.file_of_url(image)
    if wanted is None:
        return None, f"the import links {image!r}, which names no Commons file: no row can hold it"
    rows = state.rows.get(sid, ())
    for row in rows:
        if ST.file_of_row(row) == wanted and not row.get("is_excluded"):
            return row, None
    for row in rows:
        if ST.file_of_row(row) == wanted:
            return row, None
    return None, (
        f"the import's file {wanted!r} is no row of the site: giving it a row needs an insert, "
        "which this writer (conditional UPDATEs through apply_remediation_change) cannot do"
    )


def plan(
    state: ST.State,
    claims: Mapping[str, Mapping[str, Any]],
    *,
    dimensions: Mapping[int, tuple[int | None, int | None]],
    fetched: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[Change], list[Refusal]]:
    """The planned rows, and every curated site the plan refuses by name.

    `fetched` maps a site id to the 1600 px derivative a fetch step wrote for it
    (`filename`, `width`, `height`, `file_size_bytes`); a target row whose local file is too
    small is planned only when its fetch is in that manifest, and refused otherwise.
    """
    ready = fetched or {}
    changes: list[Change] = []
    refusals: list[Refusal] = []
    for sid in sorted(claims):
        claim = claims[sid]
        image = claim.get("image")
        if not image:
            continue  # the import links no image: the site's own state stands, nothing to write
        if sid not in state.sites:
            refusals.append(Refusal(sid, "retired", "the site is not in the read"))
            continue
        row, problem = _target_row(state, sid, str(image))
        if row is None:
            refusals.append(Refusal(sid, "no_target_row", str(problem)))
            continue

        row_id = int(row["id"])
        width, height = dimensions.get(row_id, (None, None))
        fetch = ready.get(sid)
        if width is None or height is None or width < HERO_MIN_WIDTH or height < HERO_MIN_HEIGHT:
            if fetch is None:
                refusals.append(
                    Refusal(
                        sid,
                        "local_file_too_small",
                        f"row {row_id} holds {width}x{height} locally, under "
                        f"{HERO_MIN_WIDTH}x{HERO_MIN_HEIGHT}: the 1600 px derivative has to be "
                        "fetched before the flag can move (owner decision 2026-10-05 17:54)",
                    )
                )
                continue
            changes.extend(
                _fetch_changes(
                    state,
                    sid,
                    row,
                    fetch,
                    reason=(
                        f"the 1600 px derivative of the import's file, fetched because the local "
                        f"file was {width}x{height}"
                    ),
                )
            )
        if row.get("is_excluded"):
            changes.append(
                Change(
                    table="wiki_images",
                    column="is_excluded",
                    row_key=str(row_id),
                    site_id=sid,
                    old_value="true",
                    new_value="false",
                    rule=RULE_UNHIDE,
                    reason=(
                        "the page hid this row (is_excluded), so the import's own image could "
                        "not be served; the owner decided on 2026-10-05 that it wins as hero"
                    ),
                    evidence=_evidence(state, sid, row, image),
                )
            )
        if not row.get("is_hero"):
            changes.append(
                Change(
                    table="wiki_images",
                    column="is_hero",
                    row_key=str(row_id),
                    site_id=sid,
                    old_value="false",
                    new_value="true",
                    rule=RULE_HERO,
                    reason=(
                        "the 2025 import links this file for the site; the owner's decision of "
                        "2026-10-05 is that the import's image wins as hero"
                    ),
                    evidence=_evidence(state, sid, row, image),
                )
            )
        for other in state.rows.get(sid, ()):
            if int(other["id"]) == row_id or not other.get("is_hero"):
                continue
            changes.append(
                Change(
                    table="wiki_images",
                    column="is_hero",
                    row_key=str(int(other["id"])),
                    site_id=sid,
                    old_value="true",
                    new_value="false",
                    rule=RULE_DEMOTE,
                    reason=(
                        "at most one hero per site: the flag moves to the file the 2025 import "
                        "links"
                    ),
                    evidence=_evidence(state, sid, other, image),
                )
            )
        wanted_thumb = local_path(sid, str(row["filename"]))
        current = state.sites[sid].get("thumbnail_url")
        if current != wanted_thumb:
            changes.append(
                Change(
                    table="unified_sites",
                    column="thumbnail_url",
                    row_key=sid,
                    site_id=sid,
                    old_value=str(current) if current else None,
                    new_value=wanted_thumb,
                    rule=RULE_THUMBNAIL,
                    reason=(
                        "the globe popup serves the thumbnail, which must name the file the page "
                        "now serves (the hero repair's T1 target)"
                    ),
                    evidence=_evidence(state, sid, row, image),
                )
            )
    return changes, refusals


#: The columns a fetched file brings with it. Every one of them names the *same* file: the
#: caption and the licence as much as the pixels, so a row can never end up crediting one file
#: while showing another. The downloader delivers all of them in one `imageinfo` answer.
FETCH_COLUMNS = (
    "filename",
    "original_url",
    "commons_page_url",
    "title",
    "author",
    "author_url",
    "license",
    "license_url",
    "width",
    "height",
    "file_size_bytes",
)


def _fetch_changes(
    state: ST.State,
    sid: str,
    row: Mapping[str, Any],
    fetch: Mapping[str, Any],
    *,
    reason: str,
) -> list[Change]:
    """The row's file columns, pointed at the 1600 px derivative a fetch step wrote.

    A manifest that names no attribution for the file is refused: a fetch that wrote the pixels
    but not the licence would leave the row crediting the previous file.
    """
    missing = [column for column in FETCH_COLUMNS if fetch.get(column) is None]
    if missing:
        raise ImportHeroError(
            f"the fetch of {sid} names no {', '.join(missing)}: a row must credit the file it "
            "shows (owner decision 2026-10-05, and the writer's licence columns), so the fetch "
            "step has to deliver the downloader's whole imageinfo answer."
        )
    row_id = str(int(row["id"]))
    absent = [column for column in FETCH_COLUMNS if column not in row]
    if absent:
        raise ImportHeroError(
            f"the read of {sid} names no {', '.join(absent)} for row {row_id}: the plan cannot state "
            "the old value a fetch would overwrite, and skipping the column silently would leave "
            "the row crediting the previous file. The lane's read must carry every column the "
            "fetch writes."
        )
    evidence = _evidence(state, sid, row, str(fetch.get("image") or ""))
    out = []
    for column in FETCH_COLUMNS:
        value = fetch[column]
        if column in ("width", "height", "file_size_bytes"):
            value = str(int(value))
        else:
            value = str(value)
        old = row.get(column)
        if old is None or str(old) == value:
            continue
        out.append(
            Change(
                table="wiki_images",
                column=column,
                row_key=row_id,
                site_id=sid,
                old_value=str(old),
                new_value=value,
                rule=RULE_FETCH,
                reason=reason,
                evidence=evidence,
            )
        )
    return out


def _evidence(
    state: ST.State, sid: str, row: Mapping[str, Any], image: str
) -> list[dict[str, Any]]:
    site = state.sites[sid]
    return [
        {
            "source": "ancient_nerds_original.geojson:Images",
            "url": "data/raw/ancient_nerds/ancient_nerds_original.geojson",
            "quote": f"the 2025 import links {image!r} for {site.get('name')!r}",
        },
        {
            "source": "snapshot:wiki_images",
            "url": f"wiki_images.id={int(row['id'])}",
            "quote": (
                f"id={int(row['id'])} site_id={sid} filename={row.get('filename')!r} "
                f"is_hero={row.get('is_hero')} is_excluded={row.get('is_excluded')}"
            ),
        },
        {
            "source": "owner decision",
            "url": "output/remediation/GOAL_IMAGES.md",
            "quote": (
                "2026-10-05: everything the 2025 import links wins as hero; the 427 whose local "
                "file is under 1600x900 are fetched at 1600 px first"
            ),
        },
    ]


def chunk_lane(stamp: str, name: str = "import-hero") -> Lane:
    """The journal identity of this lane's chunks. `stamp` is the run stamp every journal row of
    the wave carries, and `label` the string the writer's RAISE messages name - which is why it
    holds nothing but letters, digits, spaces, dots, slashes, dashes and underscores
    (`hero_repair.apply.LABEL_RE`)."""
    return Lane(
        name=name,
        test_id="import-hero/owner-2026-10-05",
        stamp=stamp,
        confidence="authoritative",
        label=f"import-hero {stamp} - the import image takes the hero flag",
    )


def write_chunks(
    out: Path,
    state: ST.State,
    claims: Mapping[str, Mapping[str, Any]],
    *,
    run_stamp: str,
    dimensions: Mapping[int, tuple[int | None, int | None]],
    fetched: Mapping[str, Mapping[str, Any]] | None = None,
    sites_per_chunk: int = 100,
) -> dict[str, Any]:
    """The chunks, the refusals and the counts. Nothing is written outside `out`."""
    changes, refusals = plan(state, claims, dimensions=dimensions, fetched=fetched)
    if not changes:
        raise ImportHeroError(
            "the plan holds no row: the join found no import image on a curated site, or every "
            "candidate was refused"
        )
    lane = chunk_lane(run_stamp)
    written = emit_chunks(out, chunk_changes(lane, changes, sites_per_chunk=sites_per_chunk))
    summary = {
        "run_stamp": run_stamp,
        "read_sha256": state.sha256,
        "sites_with_an_import_image": sum(1 for c in claims.values() if c.get("image")),
        "planned_rows": len(changes),
        "planned_sites": len({c.site_id for c in changes}),
        "refused_sites": len(refusals),
        "refusals": {
            reason: sum(1 for r in refusals if r.reason == reason)
            for reason in sorted({r.reason for r in refusals})
        },
        "chunks": len(written),
    }
    (out / "IMPORT_HERO_REFUSALS.jsonl").write_text(
        "".join(
            json.dumps(r.as_json(), ensure_ascii=False, sort_keys=True) + "\n" for r in refusals
        ),
        encoding="utf-8",
    )
    (out / "IMPORT_HERO_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
