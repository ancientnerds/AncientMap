"""D25: `parent_site_id` for component sites - the waves and the plan of lane `parent-<wave>`.

Owner decision D25 of 2026-10-08: "parent_site_id for component sites". `identity/parent_judge.py`
decides which shown sites are components of which (`PARENT_DECISIONS.jsonl`: PART with a quote,
confirmed by an adversarial recheck); this module writes it down, a wave at a time:

1. **`waves`** - the decided children in waves of at most `MAX_CHILDREN` (a lane: its own stamp and
   directory, applied once); each wave's `CHILDREN.json` in `output/remediation/mechanical_parent/
   <wave>/`. A child decided against two parents (`conflict`) is not in any wave.
2. **`plan`** - the plan, from one read-only production snapshot: per child one cell,
   `parent_site_id` NULL -> the parent's id (`lane.PARENT_CELLS`; the column is NULL on every row
   before the first wave). A pair is **held back** unless: both rows are curated and still named as
   the decision names them, the child shows and names no parent yet, the parent shows (not retired,
   not a duplicate loser, not a site a decided MERGE retires), both lie in one country within 5 km,
   and the depth stays one - the parent names no parent, the child is no parent of anything, and
   neither is a child or a parent elsewhere in the wave. The transaction proves the same again
   (`lane.parent_invariants`).

The order is after D14: a merged loser must never be a parent (`MergedLosers` below reads
`DUP_DECISIONS.jsonl`), and a parent that a merge retires would leave its children pointing at a hidden
page.

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/mechanical/parent.py waves --date 2026-10-12
    $PY scripts/remediation/mechanical/parent.py plan --wave 2026-10-12 --write
    $PY scripts/remediation/mechanical/apply.py --lane parent-2026-10-12 --emit --rehearse \\
        --probe-guards --apply --rehearse-rollback
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import plan as P  # noqa: E402
from mechanical.lane import (  # noqa: E402
    DUPLICATE_PREFIX,
    PARENT_METRES,
    PARENT_ROOT,
    REMEDIATION_ROOT,
    Lane,
    check_wave,
    parent_lane,
    sphere_metres,
    sql_literal,
)
from pipeline.utils.public_sites import RETIRED  # noqa: E402

log = logging.getLogger("mechanical.parent")

#: A wave writes at most this many sites (owner decision D8: every step <= 100 sites).
MAX_CHILDREN = 100
RULE = "d25-parent-site"
CHILDREN_FILE = "CHILDREN.json"
READ_FILE = "READ.jsonl"
HELD_FILE = "HELD.jsonl"


@dataclass(frozen=True)
class WaveChild:
    """One child of a wave and the decision that made it: what the plan cites as evidence."""

    child: str
    parent: str
    child_name: str
    parent_name: str
    p361: bool
    why: str
    quotes: tuple[Mapping[str, str], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "child": self.child,
            "parent": self.parent,
            "child_name": self.child_name,
            "parent_name": self.parent_name,
            "p361": self.p361,
            "why": self.why,
            "quotes": [dict(q) for q in self.quotes],
        }


def children_path(wave: str, root: Path | None = None) -> Path:
    check_wave(wave)
    return (root or REMEDIATION_ROOT) / PARENT_ROOT / wave / CHILDREN_FILE


def decided_children(decisions: Sequence[Mapping[str, Any]]) -> list[WaveChild]:
    """Every child `PARENT_DECISIONS.jsonl` decided (status `decided`), in child order."""
    return [
        WaveChild(
            child=d["child"],
            parent=d["parent"],
            child_name=d["child_name"],
            parent_name=d["parent_name"],
            p361=bool(d["p361"]),
            why=d["why"],
            quotes=tuple(d["quotes"]),
        )
        for d in sorted(decisions, key=lambda d: d["child"])
        if d["status"] == "decided"
    ]


def split_waves(
    children: Sequence[WaveChild], max_children: int = MAX_CHILDREN
) -> list[list[WaveChild]]:
    """Waves of whole families: the children of one parent stay in one wave, so the depth check
    sees them together; a wave holds at most `max_children` children."""
    by_parent: dict[str, list[WaveChild]] = {}
    for c in children:
        by_parent.setdefault(c.parent, []).append(c)
    waves: list[list[WaveChild]] = []
    current: list[WaveChild] = []
    for family in by_parent.values():
        if len(family) > max_children:
            raise P.PlanError(
                f"{family[0].parent}: {len(family)} children, a wave holds {max_children}"
            )
        if current and len(current) + len(family) > max_children:
            waves.append(current)
            current = []
        current.extend(family)
    if current:
        waves.append(current)
    return waves


def wave_labels(date: str, count: int) -> list[str]:
    letters = "bcdefghijklmnopqrstuvwxyz"
    if count > len(letters) + 1:
        raise P.PlanError(f"{count} waves under one date: split the date")
    labels = [date] + [f"{date}{letters[i]}" for i in range(count - 1)]
    for label in labels:
        check_wave(label)
    return labels


def write_wave(wave: str, children: Sequence[WaveChild], root: Path | None = None) -> Path:
    path = children_path(wave, root)
    if path.exists():
        raise P.PlanError(f"{path} exists: a wave is planned once - take a new label")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"wave": wave, "children": [c.to_json() for c in children]},
                   ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    return path


def load_wave(wave: str, root: Path | None = None) -> list[WaveChild]:
    path = children_path(wave, root)
    if not path.exists():
        raise P.PlanError(f"{path} does not exist - run `waves` first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("wave") != wave:
        raise P.PlanError(f"{path} is the file of wave {data.get('wave')!r}, not {wave!r}")
    return [
        WaveChild(
            child=c["child"],
            parent=c["parent"],
            child_name=c["child_name"],
            parent_name=c["parent_name"],
            p361=bool(c["p361"]),
            why=c["why"],
            quotes=tuple(c["quotes"]),
        )  # fmt: skip
        for c in data["children"]
    ]


# ------------------------------------------------------------------------------------ the read
def read_parts(children: Sequence[WaveChild], lane: Lane) -> tuple[tuple[str, str], ...]:
    """What the plan reads, each part one query of one read-only snapshot."""
    ids = P.sql_ids([i for c in children for i in (c.child, c.parent)])
    site = (
        "SELECT u.id::text AS id, u.name, u.country, u.source_id, u.scope_status, u.scope_reason, "
        "u.lat, u.lon, u.parent_site_id::text AS parent_site_id, "
        "(SELECT count(*) FROM unified_sites k WHERE k.parent_site_id = u.id) AS n_children, "
        f"({lane.premise_sql}) AS premise FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"
    )
    values = ", ".join(f"({sql_literal(c.child)}, {sql_literal(c.parent)})" for c in children)
    metres = (
        f"SELECT q.child AS child, {sphere_metres('c', 'p')} AS metres "
        f"FROM (VALUES {values}) AS q(child, parent) "
        "JOIN unified_sites c ON c.id::text = q.child JOIN unified_sites p ON p.id::text = "
        "q.parent ORDER BY q.child"
    )
    stamp = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN "
        f"({sql_literal(lane.run_stamp)}, {sql_literal(lane.rollback_run_stamp)}) "
        "GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (("site", site), ("metres", metres), ("stamp", stamp))


@dataclass(frozen=True)
class Read:
    sites: Mapping[str, Mapping[str, Any]]
    metres: Mapping[str, float]
    stamps: Mapping[str, int]
    read_at: str


def parse_read(text: str, children: Sequence[WaveChild], lane: Lane) -> Read:
    rows, read_at = P.parse_tagged_export(text, [k for k, _ in read_parts(children, lane)])
    return Read(
        sites={str(r["id"]): r for r in rows["site"]},
        metres={str(r["child"]): float(r["metres"]) for r in rows["metres"]},
        stamps={str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"]},
        read_at=read_at,
    )


def write_read(path: Path, children: Sequence[WaveChild], lane: Lane) -> Path:
    return P.write_tagged_export(P.tagged_export_script(read_parts(children, lane)), path)


# -------------------------------------------------------------------------------- the checks
class Held(Exception):
    """A child the plan cannot carry; the message is why. It is listed, never written."""


def check_child(
    read: Read, c: WaveChild, wave_children: set[str], wave_parents: set[str], losers: set[str]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """`(child, parent)` as the decision has them - or the `Held` that says why not."""
    child, parent = read.sites.get(c.child), read.sites.get(c.parent)
    for role, row, wanted, site in (
        ("child", child, c.child_name, c.child),
        ("parent", parent, c.parent_name, c.parent),
    ):
        if row is None:
            raise Held(f"the {role} ({site}) is not in unified_sites")
        if row["source_id"] != P.CURATED_SOURCE:
            raise Held(f"the {role} is not a curated site: {row['source_id']!r}")
        if row["name"] != wanted:
            raise Held(f"the {role} is named {row['name']!r}; the decision names {wanted!r}")
        if row["scope_status"] == RETIRED:
            raise Held(f"the {role} is retired ({row['scope_reason']!r})")
    assert child is not None and parent is not None
    if c.child == c.parent:
        raise Held("a site is not its own parent")
    if (
        c.parent in losers
        or c.child in losers
        or str(parent["scope_reason"] or "").startswith(DUPLICATE_PREFIX)
    ):
        raise Held("a site a merge retires is neither a child nor a parent")
    if child["parent_site_id"] is not None:
        raise Held(f"the child names a parent already ({child['parent_site_id']})")
    if child["country"] != parent["country"]:
        raise Held(f"another country: {child['country']!r} / {parent['country']!r}")
    metres = read.metres.get(c.child)
    if metres is None:
        raise Held("the read holds no distance of the pair")
    if metres > PARENT_METRES:
        raise Held(
            f"the two rows are {metres:.1f} m apart; a parent is at most {PARENT_METRES} m away"
        )
    if parent["parent_site_id"] is not None:
        raise Held("the parent is a component itself - depth one only")
    if int(child["n_children"]) > 0:
        raise Held(f"the child is the parent of {child['n_children']} site(s) - depth one only")
    if c.parent in wave_children:
        raise Held("the parent is a child in this wave - depth one only")
    if c.child in wave_parents:
        raise Held("the child is a parent in this wave - depth one only")
    return child, parent


def build(
    read: Read, children: Sequence[WaveChild], lane: Lane, losers: set[str], built_at: str
) -> tuple[P.Plan, list[dict[str, Any]]]:
    """The plan of the wave - a pure function of the read - and the children it holds back."""
    written = {s: n for s, n in read.stamps.items() if n}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for this lane: a lane that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo"
        )
    wave_children = {c.child for c in children}
    wave_parents = {c.parent for c in children}
    changes: list[P.Verdict] = []
    held: list[dict[str, Any]] = []
    for c in children:
        try:
            child, parent = check_child(read, c, wave_children, wave_parents, losers)
        except Held as exc:
            held.append(
                {"child": c.child, "parent": c.parent, "name": c.child_name, "reason": str(exc)}
            )
            continue
        evidence = (
            {"source": "identity/parent_judge.py", "url": None,
             "quote": f"{c.child_name!r} is part of {c.parent_name!r}: {c.why}"},
            *(dict(q) | ({"url": q["source"]} if "url" not in q else {}) for q in c.quotes),
            {"source": "production:unified_sites", "url": None,
             "quote": f"same country {child['country']!r}; {read.metres[c.child]:.1f} m apart; "
             f"wikidata P361 proves it: {c.p361} (read {read.read_at})"},
        )  # fmt: skip
        changes.append(
            P.Verdict(
                site_id=c.child,
                site_name=str(child["name"]),
                ok=True,
                old_value=None,
                new_value=c.parent,
                rule=RULE,
                reason="",
                note=f"parent_site_id NULL -> {parent['name']!r} ({c.parent}) (D25: {c.why})",
                phase3=False,
                finding_test_id=lane.test_id,
                evidence=evidence,
                premise=str(child["premise"]),
                column="parent_site_id",
            )
        )
    if not changes:
        raise P.PlanError(
            "no child of the wave can be planned: nothing to plan"
            + "".join(f"\n  - {h['name']} ({h['child']}): {h['reason']}" for h in held)
        )
    plan = P.Plan(changes=tuple(changes), skipped=(), built_at=built_at,
                  counters={"sites": len(changes), "cells": len(changes), "held": len(held)}, lane=lane)  # fmt: skip
    return plan, held


def plan_md(plan: P.Plan, held: Sequence[Mapping[str, Any]], read: Read) -> str:
    lane = plan.lane
    lines = [
        f"# D25 parents `{lane.name}`: plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/parent.py` from the read-only "
        f"production read of {read.read_at} (`{READ_FILE}`). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, premise `{lane.premise_sql}`.",
        "",
        "Counters: " + ", ".join(f"{k} {v}" for k, v in plan.counters.items()),
        "",
        "| child | parent | metres |",
        "|---|---|---|",
        *[
            f"| {v.site_name} (`{v.site_id}`) | `{v.new_value}` | {read.metres[v.site_id]:.0f} |"
            for v in plan.changes
        ],
        "",
    ]
    if held:
        lines += [
            "## Held back (not planned, not written)",
            "",
            *[f"* {h['name']} (`{h['child']}`): {h['reason']}" for h in held],
            "",
        ]
    lines += [
        "## Run",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        *[
            f"$PY scripts/remediation/mechanical/apply.py --lane {lane.name} {flag}"
            for flag in (
                "--check-primitive",
                "--verify",
                "--interests",
                "--emit",
                "--rehearse",
                "--probe-guards",
                "--apply",
                "--verify",
                "--rehearse-rollback",
            )  # fmt: skip
        ],
        "```",
        "",
        "Undo, only as a decision: `ROLLBACK.sql` sets each `parent_site_id` back to NULL.",
        "",
    ]
    return "\n".join(lines)


def write_plan(plan: P.Plan, held: Sequence[Mapping[str, Any]], read: Read, root: Path) -> Path:
    directory = root / plan.lane.out_dir_name
    directory.mkdir(parents=True, exist_ok=True)
    P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    (directory / "PLAN.md").write_text(plan_md(plan, held, read), encoding="utf-8", newline="\n")
    (directory / HELD_FILE).write_text(
        "".join(json.dumps(h, ensure_ascii=False, sort_keys=True) + "\n" for h in held),
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=directory / "PLAN.jsonl")
    return directory


# ------------------------------------------------------------------------------------------ CLI
def merged_losers(run: Path) -> set[str]:
    """The sites a decided MERGE retires (`DUP_DECISIONS.jsonl`). The file must exist: a merged
    loser is no parent and no child, and a plan made without knowing them is made blind."""
    from identity import common

    path = run / "DUP_DECISIONS.jsonl"
    if not path.exists():
        raise P.PlanError(f"{path} does not exist: the parents come after the duplicates (D14)")

    return {m["site_id"] for r in common.read_jsonl(path) for m in r["merges"]}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D25: waves and plan of the parent_site_id fill")
    ap.add_argument("--root", type=Path, default=None, help="main checkout of the run data")
    ap.add_argument("--out", type=Path, default=None, help="default: output/remediation")
    sub = ap.add_subparsers(dest="command", required=True)
    waves = sub.add_parser(
        "waves", help="split PARENT_DECISIONS.jsonl into waves (CHILDREN.json each)"
    )
    waves.add_argument("--date", required=True, help="the first wave's label, e.g. 2026-10-12")
    waves.add_argument("--max-children", type=int, default=MAX_CHILDREN)
    plan = sub.add_parser("plan")
    plan.add_argument("--wave", required=True)
    plan.add_argument(
        "--write", action="store_true", help="read production (read-only), write the plan"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from identity import common

    try:
        run = common.run_dir(args.root)
        if args.command == "waves":
            decided = decided_children(common.read_jsonl(run / "PARENT_DECISIONS.jsonl"))
            if not decided:
                raise P.PlanError("PARENT_DECISIONS.jsonl holds no decided child")
            groups = split_waves(decided, args.max_children)
            labels = wave_labels(args.date, len(groups))
            summary = {
                label: {"children": len(group), "file": str(write_wave(label, group, args.out))}
                for label, group in zip(labels, groups, strict=True)
            }
            print(json.dumps(summary, indent=1))
            return 0
        children = load_wave(args.wave, args.out)
        lane = parent_lane(args.wave)
        if not args.write:
            print(
                f"{lane.name}: {len(children)} child(ren); add --write to read production and write the plan"
            )
            return 0
        root = args.out or REMEDIATION_ROOT
        read_path = write_read((root / lane.out_dir_name) / READ_FILE, children, lane)
        read = parse_read(read_path.read_text(encoding="utf-8"), children, lane)
        built, held = build(read, children, lane, merged_losers(run), P._now())
        write_plan(built, held, read, root)
        print(json.dumps({"lane": lane.name, **dict(built.counters)}, indent=1))
    except (P.PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
