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

#: The owner's floor for the sites whose linked picture is smaller than the lane's (2026-10-06):
#: *"Untergrenze für diese Fälle auf 800 px senken: das vorhandene Bild wird Hero."* It is a
#: **run parameter**, never a second constant: `plan(..., floor=...)` and the fetch take the same
#: pair, so a wave either serves at 1600x900 or at the floor the owner named, and the default is
#: the lane's own. Measured for that decision: all 26 of the sites concerned hold a row of at least
#: 800 px width, none below, so the *height* is what the floor has to move (800x337 is the smallest
#: of them). The floor is written into the run directory as `FLOOR.json`, and the acceptance asks
#: production with it.
OWNER_FLOOR_WIDTH = 800
OWNER_FLOOR_HEIGHT = 300


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
    URL first, the folded title second, first hit wins. Ambiguity is reported, not resolved.

    **An empty key is no key.** 49 curated sites carry no `source_url`, and 111 of the import's
    5,995 features carry no `Source` (measured 2026-10-06); keying those under `""` put them in one
    bucket, and a site without a URL inherited that bucket's first feature - the church
    `Iglesia de San Antoni de l'Aldosa` in Cardona, claimed for sites in Ukraine, Peru, Sweden and
    Australia alike. Nothing was written from it (the plan refuses such a site as `no_target_row`
    before a claim can become a change), but the premise was wrong. A feature without a source and
    a site without one are now both outside the URL arm, where the folded title decides - or, when
    the title does not match either, no feature at all, which the plan reads as "the import links no
    image" and leaves the site's own state standing.
    """
    by_url: dict[str, list[Mapping[str, Any]]] = {}
    by_title: dict[str, list[Mapping[str, Any]]] = {}
    for feature in features:
        key = url_key(str(feature["source_url"]))
        if key:
            by_url.setdefault(key, []).append(feature)
        by_title.setdefault(fold(str(feature["title"])), []).append(feature)

    out: dict[str, dict[str, Any]] = {}
    for sid, site in state.sites.items():
        site_key = url_key(str(site.get("source_url") or ""))
        hits = by_url.get(site_key, []) if site_key else []
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


#: Where a plan that refuses **every** site writes its refusals. Its own file, because
#: `IMPORT_HERO_REFUSALS.jsonl` is what a run prepared for the INSERT lane reads back as the seeded
#: record, and a plan that wrote over it would erase that.
PLAN_REFUSALS = "PLAN_REFUSALS.jsonl"


def _write_refusals(path: Path, refusals: Sequence[Refusal]) -> None:
    path.write_text(
        "".join(
            json.dumps(r.as_json(), ensure_ascii=False, sort_keys=True) + "\n" for r in refusals
        ),
        encoding="utf-8",
        newline="\n",
    )


def _target_row(
    state: ST.State, sid: str, image: str, fetch: Mapping[str, Any] | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """The row of the site that holds the import file, live or hidden, and why there is none.

    **The title in the URL is not the file's identity.** Three of the 147 files the INSERT fetch
    downloaded (measured 2026-10-06, run `import-hero-2026-10-06-006`) were refused here as
    `no_target_row` although the site *does* hold the file: the import's link carries a slightly
    different slug than the stored row - `The_East_Facade_pf_the_Parthenon…` for `…_of_the_…`,
    `East_Terrace_(4961323529).jpg` for `Mount_Nemrut_-_East_Terrace_(4961323529).jpg`, and one
    title that gained `zyklopenhaftes` - while both resolve to the same `original_url`. So when the
    fetch has resolved the import's link to its upload URL, that URL is the identity the plan
    matches on: it is the same key the unique constraint `(site_id, original_url)` holds.
    """
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
    resolved = str((fetch or {}).get("original_url") or "")
    if resolved:
        for row in rows:
            if str(row.get("original_url") or "") == resolved:
                return row, None
    return None, (
        f"the import's file {wanted!r} is no row of the site: giving it a row needs an insert, "
        "which this writer (conditional UPDATEs through apply_remediation_change) cannot do"
    )


@dataclass(frozen=True)
class Planned:
    """The planned rows, the sites the plan refuses by name, and the sites a chunk may leave
    without an image.

    `may_empty` is the writer's own mechanism for "this site shows nothing today": the import's
    file is its *first* picture, so unhiding the row is not a hero move, and a rollback that
    restores "no image" is a faithful reversal the guard would otherwise refuse. The chunk header
    then names those sites, so the exception is on the record instead of hidden in the guard.
    """

    changes: list[Change]
    refusals: list[Refusal]
    may_empty: list[str]


def plan(
    state: ST.State,
    claims: Mapping[str, Mapping[str, Any]],
    *,
    dimensions: Mapping[int, tuple[int | None, int | None]],
    fetched: Mapping[str, Mapping[str, Any]] | None = None,
    floor: tuple[int, int] | None = None,
) -> Planned:
    """What the wave writes, what it refuses, and what a chunk may leave without an image.

    `fetched` maps a site id to the 1600 px derivative a fetch step wrote for it
    (`filename`, `width`, `height`, `file_size_bytes` and the attribution of that file); a target
    row whose local file is too small is planned only when its fetch is in that manifest, and
    refused otherwise.

    `floor` is the `(width, height)` a local file must reach for this run; the lane's own
    1600x900 by default. The owner lowered it to 800x300 for the sites whose linked picture is
    smaller than the floor (2026-10-06), and a wave that runs at that floor must say so in its
    acceptance - which is why the pair travels with the plan instead of living in two constants.
    """
    ready = fetched or {}
    min_width, min_height = floor or (HERO_MIN_WIDTH, HERO_MIN_HEIGHT)
    changes: list[Change] = []
    refusals: list[Refusal] = []
    may_empty: list[str] = []
    for sid in sorted(claims):
        claim = claims[sid]
        image = claim.get("image")
        if not image:
            continue  # the import links no image: the site's own state stands, nothing to write
        if sid not in state.sites:
            refusals.append(Refusal(sid, "retired", "the site is not in the read"))
            continue
        fetch = ready.get(sid)
        row, problem = _target_row(state, sid, str(image), fetch)
        if row is None:
            refusals.append(Refusal(sid, "no_target_row", str(problem)))
            continue

        row_id = int(row["id"])
        width, height = dimensions.get(row_id, (None, None))
        # the file the page serves **after** this wave. It is the fetched name only where this wave
        # actually renames the row (ih5 below); a site whose row already holds the file keeps its own
        # name, and taking the fetch's name there pointed the thumbnail at a file that was never
        # fetched (measured 2026-10-06, run `import-hero-2026-10-06-007`: the acceptance refused all
        # three, and the globe popup would have asked for a file that does not exist).
        served_name = str(row["filename"])
        if width is None or height is None or width < min_width or height < min_height:
            if fetch is None:
                refusals.append(
                    Refusal(
                        sid,
                        "local_file_too_small",
                        f"row {row_id} holds {width}x{height} locally, under "
                        f"{min_width}x{min_height}: the 1600 px derivative has to be "
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
            served_name = str(fetch["filename"])
        if row.get("is_excluded"):
            # A site whose every row is excluded shows no image at all today: unhiding this row
            # gives it its first picture, so the chunk has to name it (see `Planned.may_empty`).
            if not any(not other.get("is_excluded") for other in state.rows.get(sid, ())):
                may_empty.append(sid)
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
        # The thumbnail has to name the file the page will serve **after this wave**, not the one
        # the read found: `ih5` may be renaming this very row's file, and the read still holds the
        # old name. Measured 2026-10-06 on run `import-hero-2026-10-06-004`: the write landed right
        # and the acceptance still refused all 228 sites on this one question - the page served the
        # fetched 1600 px file, the globe popup still asked for `hero.webp`.
        wanted_thumb = local_path(sid, served_name)
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
    return Planned(changes=changes, refusals=refusals, may_empty=sorted(set(may_empty)))


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

#: The three credit columns `wiki_images` holds as NULL when the file names nothing for them
#: (measured 2026-10-09 over the curated rows: every empty value is NULL, none is ''). A manifest
#: entry carries a missing one as the empty string and every writer stores NULL for it (owner
#: decision D18 with orchestrator decision X4; `fetch.credit_columns` says which of them a licence
#: demands).
NULLABLE_FETCH_COLUMNS = ("author", "author_url", "license_url")


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
        value: str | None = fetch[column]
        if column in ("width", "height", "file_size_bytes"):
            value = str(int(value))
        elif column in NULLABLE_FETCH_COLUMNS and str(value) == "":
            value = None
        else:
            value = str(value)
        old = row.get(column)
        if value is None:
            if old is None:
                continue
        elif old is None or str(old) == value:
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
    floor: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """The chunks, the refusals and the counts. Nothing is written outside `out`."""
    planned = plan(state, claims, dimensions=dimensions, fetched=fetched, floor=floor)
    if not planned.changes:
        # A wave that refuses every site is the one case where the refusals are the whole result,
        # so they are written before this raises. They go into `PLAN_REFUSALS.jsonl` and not into
        # `IMPORT_HERO_REFUSALS.jsonl`: that file is what a run prepared for the INSERT lane reads,
        # and a plan that writes its own refusals over it would erase the seeded record. Measured
        # 2026-10-07, run `import-hero-2026-10-07-010`: 37 sites seeded, all 37 refused, and the run
        # could not say why any of them was.
        out.mkdir(parents=True, exist_ok=True)
        _write_refusals(out / PLAN_REFUSALS, planned.refusals)
        by_reason = {
            reason: sum(1 for r in planned.refusals if r.reason == reason)
            for reason in sorted({r.reason for r in planned.refusals})
        }
        raise ImportHeroError(
            "the plan holds no row: the join found no import image on a curated site, or every "
            f"candidate was refused. {len(planned.refusals)} site(s) are refused by name in "
            f"{out / PLAN_REFUSALS}: {by_reason}"
        )
    lane = chunk_lane(run_stamp)
    written = emit_chunks(
        out,
        chunk_changes(
            lane,
            planned.changes,
            sites_per_chunk=sites_per_chunk,
            may_empty=tuple(planned.may_empty),
        ),
    )
    summary = {
        "run_stamp": run_stamp,
        "read_sha256": state.sha256,
        "floor": {
            "min_width": (floor or (HERO_MIN_WIDTH, HERO_MIN_HEIGHT))[0],
            "min_height": (floor or (HERO_MIN_WIDTH, HERO_MIN_HEIGHT))[1],
        },
        "sites_with_an_import_image": sum(1 for c in claims.values() if c.get("image")),
        "planned_rows": len(planned.changes),
        "planned_sites": len({c.site_id for c in planned.changes}),
        "may_empty_sites": len(planned.may_empty),
        "refused_sites": len(planned.refusals),
        "refusals": {
            reason: sum(1 for r in planned.refusals if r.reason == reason)
            for reason in sorted({r.reason for r in planned.refusals})
        },
        "chunks": len(written),
    }
    (out / "IMPORT_HERO_REFUSALS.jsonl").write_text(
        "".join(
            json.dumps(r.as_json(), ensure_ascii=False, sort_keys=True) + "\n"
            for r in planned.refusals
        ),
        encoding="utf-8",
    )
    (out / "IMPORT_HERO_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
