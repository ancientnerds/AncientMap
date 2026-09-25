"""T1 for the thumbnails that name a file their own site excluded - W13's first rows.

## The defect

`unified_sites.thumbnail_url` is the image the globe draws (`/api/sites/all`, field `i`) and the
one the static export and the SSR page fall back to when a site serves no gallery image
(`pipeline/static_exporter.py`, `api/routes/sites_html.py`). No image lane writes it: the liveness
lane (`gallery_audit/liveness.py`, rule L1) excludes the rows of Commons files deleted as copyright
violations and moves the hero off them, but a thumbnail that names the excluded row's local file
goes on serving it. The Lion Tombs of Dedan is that case: L1 (`img-liveness-2026-09-23-001`,
journal rows 32263-32265) excluded both of its rows and took the hero flag off 87352, whose file
`/data/images/wiki/9a9a0dca/hero.webp` its thumbnail still names.

## The rule (T1, `gallery_audit.decide.RULES`)

`thumbnail_url := '/data/images/wiki/<site_id_short>/<served filename>'`, the served image being
the page's own (`gallery_audit.worklist.served_row`: `ORDER BY is_hero DESC, is_lead DESC,
sort_order` over the rows that are not excluded); a site that serves no image gets none (NULL).
Which row is the hero is not decided here: where L1 took a hero and a live candidate existed, it
moved the flag by the hero repair's own rule (`hero_repair.plan.candidate_verdict`, `rank_key`), so
the served row already is that choice.

## Scope

Only the class whose inputs are final today: a curated site whose `thumbnail_url` is exactly the
local path of one of its **own excluded** rows, and of no live row. The rest of W13 - the
thumbnails that diverge from the served image, the broken hotlinks, the deltas of the gallery and
re-derivation lanes - waits on W11/W12 (design entry 7) and is not planned here. Measured
2026-09-25 (read-only): the class is one site, Dedan, and it has no live row.

## Commands

    thumbnail.py chunk --out output/remediation/hero_repair/thumbnail-<date>
        reads production read-only - the candidate sites, all their image rows and the journal
        rows of their excluded rows - keeps the read as READ.json and writes chunk-001/ through the
        shared image writer (journal lane `thumb-repoint`, test id `H4/thumbnail`, stamped with the
        directory's date)
    chunk_writer.py <out>/chunk-001 --check|--rehearse|--apply|--readback|--rehearse-rollback
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gallery_audit import chunk_writer as CW  # noqa: E402
from gallery_audit.worklist import served_row  # noqa: E402

from pipeline.sites_html_renderer import site_id_short  # noqa: E402

CURATED_SOURCE = "ancient_nerds"
OUT_RE = re.compile(r"thumbnail-(\d{4}-\d{2}-\d{2})")
RULE = "T1"
SERVED_RULE = "gallery_audit/worklist.py:served_row"


class ThumbnailError(CW.ChunkError):
    """A read or a plan this lane must not turn into a write. Nothing was sent."""


def local_path(site_id: str, filename: str) -> str:
    """The path a site's local image file is served under (`site_id_short` is its directory)."""
    return f"/data/images/wiki/{site_id_short(site_id)}/{filename}"


def chunk_lane(out: Path) -> CW.Lane:
    """The journal identity of a thumbnail chunk, stamped with its directory's date."""
    match = OUT_RE.fullmatch(out.name)
    if match is None:
        raise ThumbnailError(f"{out} is not a thumbnail directory (thumbnail-YYYY-MM-DD)")
    return CW.Lane(
        "thumb-repoint",
        "H4/thumbnail",
        f"thumb-repoint-{match.group(1)}",
        "authoritative",
        "thumbnail repoint",
    )


# ------------------------------------------------------------------------------- the read
#: The candidates: curated sites whose thumbnail's file name is an excluded row's of their own.
#: The name alone is matched here; the whole path, shard included, is checked in `plan_thumbnails`.
SITES_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.name, u.source_id, u.thumbnail_url FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.thumbnail_url LIKE '/data/images/wiki/%'
     AND EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id AND w.is_excluded IS TRUE
                 AND w.filename = split_part(u.thumbnail_url, '/', 6))
   ORDER BY u.id
) t;"""

IMAGES_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.filename, w.is_hero, w.is_lead, w.sort_order,
         w.is_excluded FROM wiki_images w
   WHERE w.site_id IN ({sites}) ORDER BY w.site_id, w.id
) t;"""

JOURNAL_SQL = """SELECT row_to_json(t) FROM (
  SELECT l.id, l.run_stamp, l.row_pk, l.column_name, l.old_value, l.new_value
    FROM remediation_change_log l
   WHERE l.table_name = 'wiki_images' AND l.column_name IN ('is_excluded', 'is_hero')
     AND l.row_pk IN ({rows}) ORDER BY l.id
) t;"""


def read_production() -> dict[str, Any]:
    """The candidate sites, every image row of theirs, and the journal rows of their excluded
    rows. Read-only, three statements."""
    sites = CW.pv.read_rows(SITES_SQL)
    images: list[dict[str, Any]] = []
    journal: list[dict[str, Any]] = []
    if sites:
        ids = ", ".join(f"{CW.L(str(s['id']))}::uuid" for s in sites)
        images = CW.pv.read_rows(IMAGES_SQL.replace("{sites}", ids))
        excluded = sorted({str(r["id"]) for r in images if r["is_excluded"] is True})
        if excluded:
            rows = ", ".join(CW.L(r) for r in excluded)
            journal = CW.pv.read_rows(JOURNAL_SQL.replace("{rows}", rows))
    return {
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sites": sites,
        "images": images,
        "journal": journal,
    }


# ------------------------------------------------------------------------------- the plan
def plan_thumbnails(
    sites: Sequence[Mapping[str, Any]],
    images: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
) -> tuple[list[CW.Change], list[dict[str, Any]]]:
    """`(changes, listed)`: T1 for every site whose thumbnail names one of its own excluded rows
    and no live row; every other candidate listed with its reason. Pure."""
    by_site: dict[str, list[Mapping[str, Any]]] = {str(s["id"]): [] for s in sites}
    for row in images:
        if str(row["site_id"]) not in by_site:
            raise ThumbnailError(
                f"image {row['id']} belongs to no site of the read ({row['site_id']})"
            )
        by_site[str(row["site_id"])].append(row)
    history: dict[str, list[Mapping[str, Any]]] = {}
    for entry in journal:
        history.setdefault(str(entry["row_pk"]), []).append(entry)
    changes: list[CW.Change] = []
    listed: list[dict[str, Any]] = []
    for site in sorted(sites, key=lambda s: str(s["id"])):
        site_id, thumbnail = str(site["id"]), site["thumbnail_url"]
        if site["source_id"] != CURATED_SOURCE:
            raise ThumbnailError(f"{site_id} is not an {CURATED_SOURCE} site")
        rows = by_site[site_id]
        named = [r for r in rows if local_path(site_id, str(r["filename"])) == thumbnail]
        excluded = [r for r in named if r["is_excluded"] is True]
        if not excluded:
            listed.append({"site_id": site_id, "reason": "names-no-excluded-row"})
            continue
        if len(excluded) != len(named):
            listed.append({"site_id": site_id, "reason": "the-file-is-a-live-row-s-too"})
            continue
        served = served_row(rows)
        new = None if served is None else local_path(site_id, str(served["filename"]))
        ids = ", ".join(str(r["id"]) for r in excluded)
        evidence: list[dict[str, Any]] = []
        for row in excluded:
            evidence.append(
                {
                    "source": f"wiki_images:{row['id']}",
                    "quote": f"is_excluded true; {thumbnail} is its local file",
                }
            )
            evidence += [
                {
                    "source": f"remediation_change_log:{entry['id']}",
                    "quote": f"{entry['run_stamp']}: wiki_images.{entry['column_name']} "
                    f"{entry['old_value']} -> {entry['new_value']} on row {row['id']}",
                }
                for entry in history.get(str(row["id"]), ())
            ]
        if served is None:
            evidence.append(
                {"source": SERVED_RULE, "quote": f"none of the site's {len(rows)} row(s) is live"}
            )
            reason = (
                f"the thumbnail names the local file of excluded row {ids}; the site serves no "
                "image, so it has no thumbnail (T1)"
            )
        else:
            evidence.append(
                {"source": SERVED_RULE, "quote": f"the site serves row {served['id']} ({new})"}
            )
            reason = (
                f"the thumbnail names the local file of excluded row {ids}; T1 points it at the "
                f"image the site serves, row {served['id']}"
            )
        changes.append(
            CW.Change(
                "unified_sites",
                "thumbnail_url",
                site_id,
                site_id,
                thumbnail,
                new,
                RULE,
                reason,
                evidence,
            )
        )
    return changes, listed


# ------------------------------------------------------------------------------------ CLI
def command_chunk(args: argparse.Namespace) -> int:
    out = Path(args.out)
    lane = chunk_lane(out)
    read = read_production()
    changes, listed = plan_thumbnails(read["sites"], read["images"], read["journal"])
    for entry in listed:
        print(f"listed, not planned: {entry['site_id']} ({entry['reason']})")
    if not changes:
        raise ThumbnailError("no thumbnail names an excluded row of its own site: nothing to plan")
    # The chunk first: the writer refuses to replace a delivered chunk that differs, and the read
    # it was made from must not be overwritten by one it was not.
    for directory in CW.emit_chunks(out, CW.chunk_changes(lane, changes)):
        print(f"{directory}: {len(changes)} thumbnail(s), {len(listed)} candidate(s) listed")
    (out / "READ.json").write_text(
        json.dumps(read, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    chunk = sub.add_parser("chunk", help="read production (read-only) and emit the chunk")
    chunk.add_argument(
        "--out", required=True, help="output/remediation/hero_repair/thumbnail-<date>"
    )
    args = parser.parse_args(argv)
    try:
        return command_chunk(args)
    except CW.pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
