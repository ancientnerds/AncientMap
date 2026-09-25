"""Phase 6 item 6: the acceptance draw - frame, exclusions, the seeded 60, the canaries, the values.

The protocol is `output/remediation/acceptance/PROTOCOL.md`; this module is its section "The draw",
executable, and sealed with it (sha256 of both in AUDIT_LOG before any judging). Run it once, after
the last write of the remediation - never before, never twice into the same directory:

    draw.py --out output/remediation/acceptance/draw-<date> \\
            --phase4-audit-samples <file> [<file> ...]

It reads production read-only (four statements) and writes, into a directory that must not exist:

    FRAME.jsonl       the frame: every shown curated site with a forward journal write on a judged
                      column (id, name, country, lat, lon), sorted by id
    EXCLUDED.json     per exclusion source: path, sha256 of the file read, site ids it removed
    SAMPLE.jsonl      the 60 drawn sites with every value the judges are shown, frozen at the draw
    CANARIES.jsonl    the answer key of the 10 canary questions - never shown to a judge
    DRAW.json         seed, sizes, and the sha256 of the four files above

Nothing here computes a verdict, a key or a score. The draw itself is `phase4.audit4.draw_sample`
(the project's seeded draw: `random.Random(seed).sample` over the sorted, de-duplicated ids that are
not excluded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (
    ROOT,
    ROOT / "scripts" / "remediation",
    ROOT / "scripts" / "remediation" / "gallery_audit",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import persist_verdicts as pv  # noqa: E402
from phase4.audit4 import draw_sample  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402

SEED = 20260925
SAMPLE_SIZE = 60
#: Canaries: (field, count). A country canary carries the country of a frame site at least
#: `COUNTRY_CANARY_MIN_KM` away with another country; a coordinate canary moves the point 5 degrees
#: of latitude (about 556 km) - both wrong whatever the stored value's own quality.
CANARY_PLAN = (("country", 5), ("coordinates", 5))
COUNTRY_CANARY_MIN_KM = 3000.0
COORDINATE_SHIFT_DEG = 5.0

#: The columns whose forward journal write puts a site in the frame: every judged field's column
#: (PROTOCOL.md "The fields"), the served image's two flags included. site_external_ids is internal.
JUDGED_WRITES: tuple[tuple[str, str], ...] = (
    *(
        ("unified_sites", column)
        for column in (
            "name",
            "country",
            "lat",
            "lon",
            "site_type",
            "period_start",
            "period_name",
            "description",
            "raw_data",
            "source_url",
            "thumbnail_url",
            "scope_status",
            "scope_reason",
        )
    ),
    ("card_stats", "card_description"),
    ("wiki_images", "is_hero"),
    ("wiki_images", "is_excluded"),
)

#: The pilot sets and samples fixed before this protocol was sealed. Every UUID in the file that is
#: a frame site is excluded. The Phase-4 audit's mid-run samples and final 60 are drawn during the
#: mass run and are passed as `--phase4-audit-samples` (at least one file).
FIXED_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("assessment-pilot-60", "output/remediation/acceptance/EXCLUDE_ASSESSMENT_PILOT.txt"),
    ("gold-standard-36", "output/remediation/gold_standard/sample.json"),
    ("phase3-pilot-5", "output/remediation/phase3_pilot/PILOT.jsonl"),
    ("phase4-pilot-1", "output/remediation/phase4_runner/PILOT.jsonl"),
    ("phase4-pilot-2", "output/remediation/phase4_runner/PILOT2.jsonl"),
    ("opus-audit-keep-sample", "output/remediation/acceptance/EXCLUDE_OPUS_KEEP_SAMPLE.txt"),
    ("vlm-pilot", "output/remediation/vlm_pilot/SAMPLE.jsonl"),
    (
        "gallery-c1-sample",
        "output/remediation/gallery_audit/calibration-2026-09-25-opus/JOBS.jsonl",
    ),
    ("sitelink-pilot", "output/remediation/sitelink/pilot/questions.json"),
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class DrawError(pv.PersistError):
    """A draw that must not be taken. Nothing was written."""


# ------------------------------------------------------------------------------------ the reads
def _judged_pairs() -> str:
    return ", ".join(f"('{table}', '{column}')" for table, column in JUDGED_WRITES)


FRAME_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS site_id, u.name, u.country, u.lat, u.lon
    FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
     AND EXISTS (SELECT 1 FROM remediation_change_log l
                  WHERE l.site_id_ref = u.id
                    AND l.run_stamp NOT LIKE '%-rollback' AND l.run_stamp NOT LIKE '%-probe'
                    AND (l.table_name, l.column_name) IN ({_judged_pairs()}))
   ORDER BY u.id
) t;"""

#: Every value a judge is shown, as the public surfaces serve it at the draw. The served image is
#: the page's (`gallery_audit.worklist.served_row`: hero, then lead, then sort order, never an
#: excluded row).
VALUES_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS site_id, u.name, u.name_normalized, u.country, u.lat, u.lon, u.site_type,
         u.period_start, u.period_end, u.period_name, u.description,
         u.raw_data -> 'description_citations' AS description_citations,
         u.raw_data -> '_description_provenance' AS description_provenance,
         u.source_url, u.thumbnail_url, u.scope_status, u.scope_reason,
         cs.card_description, cs.civilization,
         (SELECT row_to_json(w) FROM (
            SELECT wi.id, wi.filename, wi.title, wi.commons_page_url, wi.original_url, wi.author,
                   wi.license
              FROM wiki_images wi
             WHERE wi.site_id = u.id AND wi.is_excluded IS NOT TRUE
             ORDER BY wi.is_hero DESC, wi.is_lead DESC, wi.sort_order, wi.id LIMIT 1) w
         ) AS served_image
    FROM unified_sites u LEFT JOIN card_stats cs ON cs.site_id = u.id
   WHERE u.id IN ({ids})
   ORDER BY u.id
) t;"""


#: The journal's high-water mark at the draw: a remediation write after it touches values the
#: judges were shown frozen, and PROTOCOL.md voids the run for it.
JOURNAL_SQL = """SELECT row_to_json(t) FROM (
  SELECT max(id) AS max_id, max(applied_at)::text AS max_applied_at, count(*) AS rows
    FROM remediation_change_log
) t;"""


def read_journal_mark() -> dict[str, Any]:
    (row,) = pv.read_rows(JOURNAL_SQL)
    return row


def read_frame() -> list[dict[str, Any]]:
    return pv.read_rows(FRAME_SQL)


def read_values(site_ids: Sequence[str]) -> list[dict[str, Any]]:
    ids = ", ".join(f"'{site_id}'::uuid" for site_id in site_ids)
    return pv.read_rows(VALUES_SQL.replace("{ids}", ids))


# ------------------------------------------------------------------------------ the exclusions
def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_in(path: Path) -> set[str]:
    """Every UUID in the file's text, lower-cased."""
    return set(UUID_RE.findall(path.read_text(encoding="utf-8", errors="replace").lower()))


def exclusions(
    frame_ids: set[str], sources: Sequence[tuple[str, Path]]
) -> tuple[set[str], list[dict[str, Any]]]:
    """The frame ids every source names, and one record per source. A missing file refuses."""
    excluded: set[str] = set()
    records: list[dict[str, Any]] = []
    for label, path in sources:
        if not path.is_file():
            raise DrawError(f"exclusion source {label} does not exist: {path}")
        removed = sorted(ids_in(path) & frame_ids)
        excluded.update(removed)
        records.append(
            {
                "label": label,
                "path": path.as_posix(),
                "sha256": sha256_of(path),
                "frame_ids_removed": removed,
            }
        )
    return excluded, records


# ---------------------------------------------------------------------------------- the canaries
def _eligible(row: Mapping[str, Any]) -> bool:
    return bool(row.get("country")) and row.get("lat") is not None and row.get("lon") is not None


def country_donor(site: Mapping[str, Any], frame: Sequence[Mapping[str, Any]], drawn: set[str]):
    """The frame site of lowest id, not drawn, with another country, at least
    COUNTRY_CANARY_MIN_KM away - its country is the canary value."""
    for row in sorted(frame, key=lambda r: str(r["site_id"])):
        if str(row["site_id"]) in drawn or not _eligible(row):
            continue
        if row["country"] == site["country"]:
            continue
        distance = haversine_distance(
            float(site["lat"]), float(site["lon"]), float(row["lat"]), float(row["lon"])
        )
        if distance >= COUNTRY_CANARY_MIN_KM:
            return row, distance
    raise DrawError(f"{site['site_id']}: no frame site qualifies as a country donor")


def shifted_point(lat: float, lon: float) -> tuple[float, float]:
    """The point COORDINATE_SHIFT_DEG north, or south where north would pass 85 degrees."""
    moved = (
        lat + COORDINATE_SHIFT_DEG
        if lat + COORDINATE_SHIFT_DEG <= 85.0
        else lat - COORDINATE_SHIFT_DEG
    )
    return round(moved, 6), lon


def canaries(
    sample: Sequence[Mapping[str, Any]], frame: Sequence[Mapping[str, Any]], *, seed: int = SEED
) -> list[dict[str, Any]]:
    """The canary answer key: `sum(count)` distinct drawn sites, picked with Random(seed + 1) from
    the eligible drawn ids in sorted order, each with a value that is wrong by construction."""
    drawn = {str(row["site_id"]) for row in sample}
    eligible = sorted(str(row["site_id"]) for row in sample if _eligible(row))
    total = sum(count for _, count in CANARY_PLAN)
    if len(eligible) < total:
        raise DrawError(f"{len(eligible)} drawn sites carry a country and a point; {total} needed")
    picks = random.Random(seed + 1).sample(eligible, total)  # noqa: S311 - a seeded draw
    by_id = {str(row["site_id"]): row for row in sample}
    out: list[dict[str, Any]] = []
    position = 0
    for field, count in CANARY_PLAN:
        for site_id in picks[position : position + count]:
            site = by_id[site_id]
            if field == "country":
                donor, distance = country_donor(site, frame, drawn)
                out.append(
                    {
                        "site_id": site_id,
                        "field": "country",
                        "true_stored": site["country"],
                        "canary_value": donor["country"],
                        "why_wrong": f"the country of frame site {donor['site_id']}, "
                        f"{distance:.0f} km away",
                    }
                )
            else:
                lat, lon = shifted_point(float(site["lat"]), float(site["lon"]))
                out.append(
                    {
                        "site_id": site_id,
                        "field": "coordinates",
                        "true_stored": f"{site['lat']},{site['lon']}",
                        "canary_value": f"{lat},{lon}",
                        "why_wrong": f"the stored point moved {COORDINATE_SHIFT_DEG} degrees of "
                        "latitude (about 556 km)",
                    }
                )
        position += count
    return out


# --------------------------------------------------------------------------------------- the draw
def _jsonl(rows: Iterable[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def take_draw(
    frame: Sequence[Mapping[str, Any]], sources: Sequence[tuple[str, Path]]
) -> dict[str, Any]:
    """The whole draw from a frame read and the exclusion sources, before any value is read."""
    frame_ids = {str(row["site_id"]) for row in frame}
    if len(frame_ids) != len(frame):
        raise DrawError("the frame read carries a site twice")
    excluded, records = exclusions(frame_ids, sources)
    pool = frame_ids - excluded
    if len(pool) < SAMPLE_SIZE:
        raise DrawError(
            f"{len(pool)} frame sites remain after the exclusions; {SAMPLE_SIZE} needed"
        )
    drawn = draw_sample(sorted(frame_ids), seed=SEED, count=SAMPLE_SIZE, exclude=excluded)
    return {"frame_ids": frame_ids, "excluded": excluded, "records": records, "drawn": drawn}


def command_draw(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        raise DrawError(f"{out} exists - a draw is taken once, into a new directory")
    if not args.phase4_audit_samples:
        raise DrawError("the Phase-4 audit's samples are an exclusion source: pass them")
    sources = [(label, ROOT / path) for label, path in FIXED_EXCLUSIONS]
    sources += [
        (f"phase4-audit-sample-{n}", Path(p)) for n, p in enumerate(args.phase4_audit_samples, 1)
    ]
    journal = read_journal_mark()
    frame = read_frame()
    draw = take_draw(frame, sources)
    values = read_values(draw["drawn"])
    if sorted(str(v["site_id"]) for v in values) != draw["drawn"]:
        raise DrawError("the value read does not return exactly the drawn sites")
    canary_rows = canaries(values, frame)
    out.mkdir(parents=True)
    files = {
        "FRAME.jsonl": _jsonl(sorted(frame, key=lambda r: str(r["site_id"]))),
        "EXCLUDED.json": json.dumps(draw["records"], ensure_ascii=False, indent=1) + "\n",
        "SAMPLE.jsonl": _jsonl(values),
        "CANARIES.jsonl": _jsonl(canary_rows),
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "drawn_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "frame": len(draw["frame_ids"]),
        "excluded": len(draw["excluded"]),
        "pool": len(draw["frame_ids"] - draw["excluded"]),
        "canaries": len(canary_rows),
        "journal_at_draw": journal,
        "sha256": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in files.items()
        },
        "draw_py_sha256": sha256_of(_HERE),
    }
    (out / "DRAW.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", required=True, help="output/remediation/acceptance/draw-<date>")
    parser.add_argument(
        "--phase4-audit-samples",
        nargs="+",
        default=[],
        help="the id files of the Phase-4 audit's mid-run samples and its final 60",
    )
    args = parser.parse_args(argv)
    try:
        return command_draw(args)
    except pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
