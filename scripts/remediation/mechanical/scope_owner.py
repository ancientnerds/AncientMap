"""Owner-decided retirements through the scope-window lane (D138, 2026-11-07).

## The decision it carries out

D138 (owner, 2026-11-07): "die 2 mittelalter deaktivieren" - Caus Castle and Ayazini Kaya Church, the
two `scope-hold` rows of the D137 refine (`output/remediation/fields/epoch_bands/CANDIDATES.jsonl`:
their only epoch is medieval, which lies outside the D58 window or on its label border), are retired as
out of scope, through the journalled scope-retire lane. No model judges here: the owner did, per site.

## The write

`scope-window-<wave>` (`mechanical/identity_lanes.scope_window_lane`, the D58/D20 retire lane):
`scope_status` NULL -> `retired` and `scope_reason` NULL -> the decision's reason, two cells per site in
one transaction, the premise the entry the owner decided (name, type, point, country, dates: guard 5
refuses a site that changed since the plan). A retired site leaves every public reader through
`pipeline/utils/public_sites.not_retired()`: its page answers 410 (`api/routes/sites_html.py`), the
sitemap and the static export drop it.

    M=scripts/remediation/mechanical
    $M/scope_owner.py plan   --wave W --decision D138     (read-only; PLAN.jsonl, ROLLBACK.sql)
    $M/apply.py --lane scope-window-W --emit | --rehearse | --probe-guards | --apply | --rehearse-rollback
    $M/scope_owner.py verify --wave W                     (read-only; 0 deviations)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import plan_files, scope_judge, verify  # noqa: E402

from mechanical import plan as MP  # noqa: E402
from mechanical.apply import lane_dir  # noqa: E402
from mechanical.identity_lanes import scope_window_lane  # noqa: E402
from mechanical.lane import D50_DISPUTED_SITES, Lane  # noqa: E402
from mechanical.period_fix import D138_QUOTE  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

DECISIONS_FILE = "output/remediation/OWNER_DECISIONS_2026-10-08.md"
CANDIDATES = "output/remediation/fields/epoch_bands/CANDIDATES.jsonl"


@dataclass(frozen=True)
class OwnerRetirement:
    """One owner decision that retires named sites with one reason."""

    decision: str
    quote: str
    reason: str
    #: site id -> the name the owner decided on (a row renamed since is refused, not followed)
    sites: Mapping[str, str]
    #: where each site's own evidence for the decision lies (its candidate row)
    evidence_file: str


OWNER_RETIREMENTS: Mapping[str, OwnerRetirement] = {
    "D138": OwnerRetirement(
        decision="D138",
        quote=D138_QUOTE,
        reason="D138 owner: medieval, out of scope",
        sites={
            "1d54b3ce-6157-41bd-bd2f-4a42cf175919": "Caus Castle",
            "3f16cff5-f53f-4a81-9813-c80214933fd5": "Ayazini Kaya Church",
        },
        evidence_file=CANDIDATES,
    ),
}


def candidate_rows(path: Path, site_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """The candidate row of each named site (its epoch quote, URL and the D58 note)."""
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["site_id"] in site_ids:
                rows[r["site_id"]] = r
    return rows


def build(
    retirement: OwnerRetirement,
    live: Mapping[str, Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    lane: Lane,
) -> tuple[list[MP.Verdict], list[dict[str, Any]]]:
    """The cells of every named site that can be retired, and the skips with their reasons. Pure."""
    changes: list[MP.Verdict] = []
    skipped: list[dict[str, Any]] = []
    for sid, name in sorted(retirement.sites.items()):

        def skip(reason: str, note: str, sid: str = sid, name: str = name) -> None:
            skipped.append({"site_id": sid, "name": name, "reason": reason, "note": note})

        now = live.get(sid)
        if now is None:
            skip("gone", "the site is no longer in unified_sites")
            continue
        if now["source_id"] != MP.CURATED_SOURCE:
            skip("not-curated", f"a {now['source_id']} row")
            continue
        if now["name"] != name:
            skip("renamed", f"the owner decided {name!r}, production holds {now['name']!r}")
            continue
        if now["scope_status"] == RETIRED:
            skip("already-retired", f"retired: {now['scope_reason']!r}")
            continue
        if sid in D50_DISPUTED_SITES:
            skip("d50-disputed", "D50 shows it as a disputed site (`lane.D50_NOT_RETIRED`)")
            continue
        row = candidates.get(sid)
        if row is None:
            raise MP.PlanError(f"{sid}: no candidate row in {retirement.evidence_file}")
        evidence = (
            {
                "source": f"owner decision {retirement.decision} (2026-11-07)",
                "url": DECISIONS_FILE,
                "quote": retirement.quote,
            },
            {
                "source": f"{row.get('source_kind')}: epoch {row.get('epoch')!r} ({retirement.evidence_file})",
                "url": str(row.get("url")),
                "quote": str(row.get("quote")),
            },
            {
                "source": f"D58 precheck ({retirement.evidence_file}, status {row['status']!r})",
                "url": retirement.evidence_file,
                "quote": str(row.get("scope")),
            },
        )
        for column, value in (("scope_status", RETIRED), ("scope_reason", retirement.reason)):
            changes.append(
                MP.Verdict(
                    site_id=sid,
                    site_name=str(now["name"]),
                    ok=True,
                    old_value=now[column],
                    new_value=value,
                    rule=f"{retirement.decision.lower()}-owner-retire",
                    reason="",
                    note=f"{column} {now[column]!r} -> {value!r}",
                    phase3=False,
                    finding_test_id=lane.test_id,
                    evidence=evidence,
                    premise=str(now["premise"]),
                    column=column,
                )
            )
    return changes, skipped


def plan(
    wave: str,
    decision: str,
    *,
    read: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    retirement = OWNER_RETIREMENTS[decision]
    lane = scope_window_lane(wave)
    reader = read or MP.psql_json_reader(read_only=True)
    ids = sorted(retirement.sites)
    live = {str(r["site_id"]): r for r in reader(scope_judge.live_sql(ids))}
    candidates = candidate_rows(REPO / retirement.evidence_file, ids)
    changes, skipped = build(retirement, live, candidates, lane)
    counters = {
        "sites": len({c.site_id for c in changes}),
        "cells": len(changes),
        "skipped": len(skipped),
    }
    mech = MP.Plan(
        tuple(changes), (), built_at=datetime.now(UTC).isoformat(), counters=counters, lane=lane
    )
    lines = [
        *plan_files.header_lines(
            mech, f"{decision} owner retirement", "scripts/remediation/mechanical/scope_owner.py"
        ),
        *[
            f"* **{c.site_name}** (`{c.site_id}`): {c.old_value!r} -> {c.new_value!r}"
            for c in changes
            if c.column == "scope_reason"
        ],
        *plan_files.skipped_lines(skipped),
        "",
    ]
    out = lane_dir(lane)
    plan_files.write_cell_plan(mech, skipped, out, "\n".join(lines))
    return {**counters, "lane": lane.name, "dir": str(out)}


def verify_wave(
    wave: str, *, read: Callable[[str], list[dict[str, Any]]] | None = None
) -> dict[str, Any]:
    """The planned cells against production now (read-only)."""
    out = lane_dir(scope_window_lane(wave))
    cells = verify.planned_cells(out / "PLAN.jsonl")
    columns = sorted({c["column"] for c in cells})
    reader = read or MP.psql_json_reader(read_only=True)
    rows = reader(verify.live_cells_sql([c["site_id"] for c in cells], columns))
    deviations = verify.cell_deviations(cells, {str(r["site_id"]): r for r in rows})
    return verify.wave_report(deviations, len(cells))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--wave", required=True)
    p.add_argument("--decision", required=True, choices=sorted(OWNER_RETIREMENTS))
    v = sub.add_parser("verify")
    v.add_argument("--wave", required=True)
    args = ap.parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(plan(args.wave, args.decision), indent=1, sort_keys=True))
            return 0
        report = verify_wave(args.wave)
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0 if report["accepted"] else 1
    except (MP.PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
