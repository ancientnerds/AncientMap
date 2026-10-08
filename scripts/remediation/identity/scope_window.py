"""D20: the sites the E3 window may not cover - the population, with where each period came from.

The scope rule E3 (`pipeline/normalizers/dates.py`): a site is in scope when the date of its last
period is not past its region's cutoff (500 AD, 1500 AD for the Americas and Oceania). The window is
tested in SQL by `mechanical.lane.outside_e3_window` (`export.SHOWN_SQL` carries it as
`outside_window`), never re-typed here. The population:

* `outside_window`   - shown sites past the cutoff (127 on 2026-10-08: 110 undecided, 15 museums
                       already `in_scope`, 2 pending);
* `pending`          - the five sites a scope review left `pending`, in the window or not;
* `hadrians_wall_path` - a footpath opened in 2003, never decided.

A museum among them (22: 15 already `in_scope`, 7 undecided) is flagged `museum_question`: scope
rule (d) asks whether its exhibits are ancient, a different question from the period's.

Each site carries its **period provenance** from the change journal: the last write of
`period_start`, `period_end` and `period_name` (stamp, family, confidence, old and new value, the
models the write's evidence names), and `origin`: the family of the last `period_start` write, or
`import` when the journal never touched it. A period written by the Phase-3 field lanes WD3/WD4
(`fields-wd3`, `fields-wd4`) is `recheck_d10`: those waves were partly answered by MiniMax with no
recorded release, and the owner's D10 re-checks them before any of them decides a retirement.

Output `SCOPE_WINDOW.jsonl`, sorted by name.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import common, export  # noqa: E402

OUTPUT = "SCOPE_WINDOW.jsonl"
HADRIANS_WALL_PATH_NAME = "Hadrian's Wall Path"
ORIGIN_IMPORT = "import"
#: The families whose period is re-checked first (D10).
RECHECK_FAMILIES = ("fields-wd3", "fields-wd4")


def stamp_family(run_stamp: str) -> str:
    """The lane a journal stamp belongs to, without its date prefix and its step number:
    `2026-09-26d_fields-wd1-s018` is `fields-wd1`, `phase3:batch-0288:chunk-0001` is `phase3`."""
    if run_stamp.startswith("phase3:"):
        return "phase3"
    return re.sub(r"^\d{4}-\d{2}-\d{2}[a-z]?_", "", re.sub(r"-s\d+$", "", run_stamp))


def date_used(row: Mapping[str, Any]) -> int | None:
    """The date the window tests: `period_end` unless it is missing or 0, else `period_start`."""
    return row["period_end"] if row["period_end"] else row["period_start"]


def groups_of(row: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    if row["outside_window"]:
        found.append("outside_window")
    if row["scope_status"] == "pending":
        found.append("pending")
    if row["id"].startswith(export.HADRIANS_WALL_PATH_PREFIX):
        found.append("hadrians_wall_path")
    return found


def provenance(journal: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The last journalled write per period column of one site."""
    out: dict[str, dict[str, Any]] = {}
    for entry in journal:
        out[entry["column_name"]] = {
            "run_stamp": entry["run_stamp"],
            "family": stamp_family(entry["run_stamp"]),
            "confidence": entry["confidence"],
            "old": entry["old_value"],
            "new": entry["new_value"],
            "applied_at": entry["applied_at"],
            "models": entry["models"],
        }
    return out


def build(exported: export.Export) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    journal: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for entry in exported.period_journal:
        journal[entry["site_id"]].append(entry)
    hadrian = [r for r in exported.shown if r["id"].startswith(export.HADRIANS_WALL_PATH_PREFIX)]
    if len(hadrian) != 1 or hadrian[0]["name"] != HADRIANS_WALL_PATH_NAME:
        raise common.IdentityError(
            f"{export.HADRIANS_WALL_PATH_PREFIX} is not one shown site named "
            f"{HADRIANS_WALL_PATH_NAME!r}: {[r['name'] for r in hadrian]}"
        )

    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in exported.shown:
        found = groups_of(row)
        if not found:
            continue
        written = provenance(journal.get(row["id"], []))
        start = written.get("period_start")
        origin = start["family"] if start else ORIGIN_IMPORT
        for group in found:
            counts["group_" + group] += 1
        counts["origin_" + origin] += 1
        counts["recheck_d10"] += origin in RECHECK_FAMILIES
        counts["museum_question"] += row["site_type"] == "Museum"
        counts["museum_undecided"] += row["site_type"] == "Museum" and row["scope_status"] is None
        records.append(
            {
                "id": row["id"],
                "name": row["name"],
                "country": row["country"],
                "site_type": row["site_type"],
                "lat": row["lat"],
                "lon": row["lon"],
                "groups": found,
                "museum_question": row["site_type"] == "Museum",
                "scope_status": row["scope_status"],
                "scope_reason": row["scope_reason"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "period_name": row["period_name"],
                "date_used": date_used(row),
                "origin": origin,
                "recheck_d10": origin in RECHECK_FAMILIES,
                "period_writes": written,
                "description_lane": row["description_lane"],
                "description": row["description"][:300],
                "source_url": row["source_url"],
                "images": row["images"],
            }
        )
    records.sort(key=lambda r: (r["name"].casefold(), r["id"]))
    counts["population"] = len(records)
    status = Counter(
        (r["scope_status"] or "undecided") for r in records if "outside_window" in r["groups"]
    )
    out: dict[str, Any] = dict(sorted(counts.items()))
    out["outside_window_by_status"] = dict(sorted(status.items()))
    out["shown"] = len(exported.shown)
    return records, out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D20 scope window population.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    args = parser.parse_args(argv)
    run = common.run_dir(args.root)
    exported = export.load_export(run / common.EXPORT_FILE)
    records, counts = build(exported)
    common.write_jsonl(run / OUTPUT, records)
    common.record_counts(run, "scope_window", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
