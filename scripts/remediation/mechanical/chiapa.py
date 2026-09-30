"""HUMAN_ONLY Nr. 7: Chiapa de Corzo - the duplicate hide and the rename (`chiapa-hide`, `chiapa-name`).

## The decision

`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, Nr. 7, decided on 2026-09-26 under the
owner's O9 ("nach meiner Empfehlung entscheiden"): "Chiapa de Corzo" (`24aa135d`) and "Zoque Culture
Archaeological Zone" (`ed186ea9`) are one site. The empty row is hidden as a duplicate of the kept
one (`scope_status = 'retired'`, `scope_reason = 'duplicate_of:ed186ea9-...'`), and the kept row
(3 content links, 20 images, Q4384315) is renamed "Chiapa de Corzo", the English label of its
item. The pair, the names and the evidence are L5's pinned rename (`l5/population.PINNED_NAMES`,
`hidden_first`): L5's `plan` ran before the hide existed and skipped the rename
(`duplicate-not-hidden-yet`), and `name-l5`'s stamp is applied, so both cells get lanes of their own.

## Two lanes, the hide first

`chiapa-hide` fills the empty row's two scope cells, `chiapa-name` writes the kept row's name and
its key - each the shape an applied lane already is (scope-e4's scope cells; name-l5's name cells
and key invariant), with its own stamp, journal test id and directory under
`output/remediation/mechanical_chiapa/`. The order is enforced, not assumed: the rename's premise
is "the duplicates retired onto the kept row", planned as the state the hide leaves behind, so its
guard 5 refuses the rename until exactly that hide has landed (and refuses its reversal once the
hide is undone). The undo runs the other way round: the rename's ROLLBACK.sql first, then the hide's.

## What is checked before anything is planned (`build`, the first failure refuses both plans)

The empty row: it exists, is curated, is still named "Chiapa de Corzo", has no scope decision, holds
no content link and no image (its premise as Postgres prints it), and no journal row wrote its
scope cells around the journal. The kept row: it exists, is curated and not retired, lies within
100 m of the empty row (`lane.DUPLICATE_METRES`), is the survivor the scope lane's rule keeps
(`scope.survivor_rank`), still holds the planned old name with its journal ending there, and no row
is retired onto it yet. The new name: its key is computed by Postgres (`l5.plan.keys_sql`), and no
visible curated row but the empty one carries it. Neither stamp journals a row yet: a lane that has
written is never re-planned.

`--write` reads production read-only, in one snapshot (`plan.tagged_export_script`), keeps the read
as `mechanical_chiapa/READ.jsonl` and writes each lane's `PLAN.jsonl`, `PLAN.md` and `ROLLBACK.sql`.
Nothing is written to production here: `apply.py --lane chiapa-hide` and then `--lane chiapa-name`
render, rehearse, probe and run the transactions (docs/procedures/SITES_DB_REMEDIATION_2026-09.md,
"Hand-offs to WD2").
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

from l5 import plan as L5P  # noqa: E402
from l5.population import PINNED_NAMES  # noqa: E402

from mechanical import plan as P  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CHIAPA_HIDE,
    CHIAPA_NAME,
    DUPLICATE_METRES,
    EMPTY_ROW_PREMISE,
    Lane,
    duplicates_retired_onto,
    sphere_metres,
    sql_literal,
)
from mechanical.scope import survivor_rank  # noqa: E402
from pipeline.lyra.site_key import site_key_sql  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

log = logging.getLogger("mechanical.chiapa")

#: The kept row; the rest of the decision - the hidden row, its reason, both names, the evidence -
#: is L5's pinned rename, read from there and never copied.
KEPT = "ed186ea9-9ed1-415d-828b-97d9f21401d2"
RENAME = PINNED_NAMES[KEPT]
HIDDEN, HIDDEN_REASON = RENAME.hidden_first
#: Where the lanes' directories live (`apply.lane_dir`), and the read both plans rest on - in their
#: common parent, `mechanical_chiapa/`.
ROOT = REPO / "output" / "remediation"
READ_PATH = Path(CHIAPA_HIDE.out_dir_name).parent / "READ.jsonl"
DECISION_SOURCE = "output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md"
HIDE_RULE = "nr7-duplicate-hide"
STAMPS = tuple(
    stamp
    for lane in (CHIAPA_HIDE, CHIAPA_NAME)
    for stamp in (lane.run_stamp, lane.rollback_run_stamp)
)


# ------------------------------------------------------------------------------ the read
def read_parts() -> tuple[tuple[str, str], ...]:
    """What the plan reads, each part one query of one read-only snapshot."""
    ids = P.sql_ids((HIDDEN, KEPT))
    site = (
        "SELECT u.id::text AS id, u.name, u.name_normalized, u.source_id, u.scope_status, "
        "u.scope_reason, u.lat, u.lon, u.created_at::text AS created_at, "
        "(SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS links, "
        "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS images, "
        "jsonb_array_length(coalesce(u.raw_data->'description_citations', '[]'::jsonb)) "
        "AS citations, "
        "(SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) "
        "FROM site_external_ids e WHERE e.site_id = u.id) AS ext, "
        f"{CHIAPA_HIDE.premise_sql} AS hide_premise, {CHIAPA_NAME.premise_sql} AS name_premise "
        f"FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"
    )
    pair = (
        f"SELECT {sphere_metres('h', 's')} AS metres FROM unified_sites h, unified_sites s "
        f"WHERE h.id = {sql_literal(HIDDEN)} AND s.id = {sql_literal(KEPT)}"
    )
    holders = (
        "SELECT u.id::text AS id, u.name, u.scope_status FROM unified_sites u "
        "WHERE u.source_id = 'ancient_nerds' AND u.name_normalized = "
        f"{site_key_sql(sql_literal(RENAME.new))} ORDER BY u.id"
    )
    journal = (
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND row_pk IN ({ids}) AND column_name IN ('scope_status', 'scope_reason', 'name') "
        "ORDER BY id"
    )
    stamps = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN ("
        + ", ".join(sql_literal(s) for s in STAMPS)
        + ") GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (
        ("site", site),
        ("pair", pair),
        ("key", L5P.keys_sql([RENAME.new])),
        ("holder", holders),
        ("journal", journal),
        ("stamp", stamps),
    )


@dataclass(frozen=True)
class Read:
    """The production read the plans rest on."""

    sites: Mapping[str, Mapping[str, Any]]
    metres: float
    key: str
    holders: tuple[Mapping[str, Any], ...]
    journal: Mapping[tuple[str, str], tuple[P.JournalLink, ...]]
    stamps: Mapping[str, int]
    read_at: str


def parse_read(text: str) -> Read:
    """The tagged read (`plan.parse_tagged_export` refuses a line of another kind and a read
    without its one snapshot line)."""
    rows, read_at = P.parse_tagged_export(text, (kind for kind, _sql in read_parts()))
    if len(rows["pair"]) != 1 or len(rows["key"]) != 1:
        raise P.PlanError("the read names both rows once and the new name's key once")
    journal: dict[tuple[str, str], list[P.JournalLink]] = {}
    for r in rows["journal"]:
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            P.JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    return Read(
        sites={str(r["id"]): r for r in rows["site"]},
        metres=float(rows["pair"][0]["metres"]),
        key=str(rows["key"][0]["key"]),
        holders=tuple(rows["holder"]),
        journal={cell: tuple(links) for cell, links in journal.items()},
        stamps={str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"]},
        read_at=read_at,
    )


def write_read(path: Path) -> Path:
    """Read production (read-only, one snapshot) and keep the answer as it came."""
    return P.write_tagged_export(P.tagged_export_script(read_parts()), path)


# ------------------------------------------------------------------------------ the decision
def _journal_ends_at_live(read: Read, site: Mapping[str, Any], column: str) -> None:
    broken = P.journal_break(read.journal.get((str(site["id"]), column), ()), site[column])
    if broken is not None:
        raise P.PlanError(f"{site['name']} ({site['id']}) {column}: {broken[0]} - {broken[1]}")


def _row(read: Read, site_id: str, role: str) -> Mapping[str, Any]:
    row = read.sites.get(site_id)
    if row is None:
        raise P.PlanError(f"the {role} ({site_id}) is not in unified_sites")
    if row["source_id"] != P.CURATED_SOURCE:
        raise P.PlanError(f"the {role} ({site_id}) is not a curated site: {row['source_id']!r}")
    return row


def check_hidden(read: Read) -> Mapping[str, Any]:
    """The empty row, as the decision hides it - or the refusal that says why not."""
    hidden = _row(read, HIDDEN, "row to hide")
    if hidden["name"] != RENAME.new:
        raise P.PlanError(
            f"the row to hide is named {hidden['name']!r}; the decision hides {RENAME.new!r}"
        )
    if hidden["scope_status"] is not None or hidden["scope_reason"] is not None:
        raise P.PlanError(
            f"the row to hide already has a scope decision: {hidden['scope_status']!r}, "
            f"{hidden['scope_reason']!r}"
        )
    if hidden["hide_premise"] != EMPTY_ROW_PREMISE:
        raise P.PlanError(
            f"the row to hide holds {hidden['hide_premise']!r}; the decision hides an empty row "
            f"({EMPTY_ROW_PREMISE!r})"
        )
    for column in ("scope_status", "scope_reason"):
        _journal_ends_at_live(read, hidden, column)
    return hidden


def check_kept(read: Read, hidden: Mapping[str, Any]) -> Mapping[str, Any]:
    """The kept row: the survivor of the pair, still as the rename was decided on it."""
    kept = _row(read, KEPT, "kept row")
    if kept["scope_status"] == RETIRED:
        raise P.PlanError(f"the kept row is retired ({kept['scope_reason']!r})")
    if read.metres > DUPLICATE_METRES:
        raise P.PlanError(
            f"the two rows are {read.metres:.1f} m apart; one site is at most "
            f"{DUPLICATE_METRES} m (the scope lane's rule)"
        )
    if sorted((hidden, kept), key=survivor_rank)[0]["id"] != KEPT:
        raise P.PlanError("the scope lane's survivor rule keeps the empty row, not the kept one")
    if kept["name"] != RENAME.old or kept["name_normalized"] is None:
        raise P.PlanError(
            f"the kept row holds {kept['name']!r} (key {kept['name_normalized']!r}); the rename "
            f"replaces {RENAME.old!r}"
        )
    _journal_ends_at_live(read, kept, "name")
    if kept["name_premise"] != duplicates_retired_onto([]):
        raise P.PlanError(
            f"a row is retired onto the kept row already ({kept['name_premise']!r}): the plan "
            "rests on the hide it writes itself"
        )
    return kept


def check_name(read: Read) -> None:
    """After the hide, no visible curated row but the renamed one carries the new name's key."""
    visible = sorted(str(h["id"]) for h in read.holders if h["scope_status"] != RETIRED)
    others = [sid for sid in visible if sid != HIDDEN]
    if others:
        raise P.PlanError(
            f"{', '.join(others)} carries the key {read.key!r} too and stays visible: two visible "
            f"rows would be called {RENAME.new!r}"
        )


def _read_evidence(
    read: Read, hidden: Mapping[str, Any], kept: Mapping[str, Any]
) -> dict[str, Any]:
    def row(site: Mapping[str, Any]) -> str:
        return (
            f"{site['name']!r} ({site['id']}): {site['links']} content link(s), "
            f"{site['images']} image(s), external ids {site['ext'] or 'none'}"
        )

    return {
        "source": "production:unified_sites",
        "url": None,
        "quote": f"{row(hidden)}; {row(kept)}; {read.metres:.1f} m apart (read {read.read_at})",
    }


def build(read: Read, built_at: str) -> tuple[P.Plan, P.Plan]:
    """`(hide, rename)`: a pure function of the read - no network, no database, no clock."""
    written = {stamp: n for stamp, n in read.stamps.items() if n}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for these lanes: a lane that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo"
        )
    hidden = check_hidden(read)
    kept = check_kept(read, hidden)
    check_name(read)
    decision = RENAME.evidence[0]
    seen = _read_evidence(read, hidden, kept)
    rank = {
        "source": "survivor rule",
        "url": "scripts/remediation/mechanical/scope.py:survivor_rank",
        "quote": "older row, then more content links, description citations, images: "
        f"{kept['name']!r} ({kept['created_at']}, {kept['links']} links, {kept['citations']} "
        f"citations, {kept['images']} images) over {hidden['name']!r} ({hidden['created_at']}, "
        f"{hidden['links']} links, {hidden['citations']} citations, {hidden['images']} images)",
    }
    hide = tuple(
        P.Verdict(
            site_id=HIDDEN,
            site_name=str(hidden["name"]),
            ok=True,
            old_value=None,
            new_value=value,
            rule=HIDE_RULE,
            reason="",
            note=f"{column} NULL -> {value!r} (HUMAN_ONLY Nr. 7, O9 2026-09-26)",
            phase3=False,
            finding_test_id=CHIAPA_HIDE.test_id,
            evidence=(decision, seen, rank),
            premise=str(hidden["hide_premise"]),
            column=column,
        )
        for column, value in (("scope_status", RETIRED), ("scope_reason", HIDDEN_REASON))
    )
    rename = L5P.name_verdicts(
        KEPT,
        RENAME.old,
        str(kept["name_normalized"]),
        RENAME.new,
        read.key,
        (*RENAME.evidence, seen),
        "HUMAN_ONLY Nr. 7 (O9, 2026-09-26): the kept row takes its item's English label, "
        f"once {HIDDEN} is hidden as its duplicate",
        premise=duplicates_retired_onto([HIDDEN]),
    )
    return (
        _plan(hide, CHIAPA_HIDE, built_at),
        _plan(tuple(rename), CHIAPA_NAME, built_at),
    )


def _plan(changes: Sequence[P.Verdict], lane: Lane, built_at: str) -> P.Plan:
    counters = {"sites": len({v.site_id for v in changes}), "cells": len(changes)}
    return P.Plan(
        changes=tuple(changes), skipped=(), built_at=built_at, counters=counters, lane=lane
    )


# ------------------------------------------------------------------------------ the output
def _commands(lane: Lane) -> list[str]:
    run = f"$PY scripts/remediation/mechanical/apply.py --lane {lane.name}"
    return [
        f"{run} --check-primitive",
        f"{run} --verify",
        f"{run} --interests",
        f"{run} --emit",
        f"{run} --rehearse",
        f"{run} --probe-guards",
        f"{run} --apply",
        f"{run} --verify",
        f"{run} --rehearse-rollback",
    ]


_GUARDS = {
    CHIAPA_HIDE.name: [
        "guard 1: the row is a curated site",
        "guard 2: two real changes, only in `scope_status` and `scope_reason`",
        "guard 3: the row still holds the planned old values (both NULL)",
        "guard 4: the status written is `retired` and nothing else",
        f"guard 5: the row is still empty - premise `{EMPTY_ROW_PREMISE}`",
        "after the write, the survivor its reason names is a curated site, not retired, and "
        f"within {DUPLICATE_METRES} m (three checks, each probed with a row of its kind)",
        "one journal row per cell, and exactly the planned cells moved",
    ],
    CHIAPA_NAME.name: [
        "guard 1: the row is a curated site",
        "guard 2: real changes, only in `name` and `name_normalized`, each within 500 characters",
        f"guard 3: the row still holds the planned old name {RENAME.old!r} and its key",
        "guard 5: the hide has landed with exactly its reason - premise "
        f"`{duplicates_retired_onto([HIDDEN])}`; before the hide the row reads "
        f"`{duplicates_retired_onto([])}` and the rename is refused",
        "invariant 3: the key written is the key Postgres derives from the name written",
        "one journal row per cell, and exactly the planned cells moved",
    ],
}


def plan_md(plan: P.Plan, read: Read) -> str:
    lane = plan.lane
    first = lane is CHIAPA_HIDE
    lines = [
        f"# HUMAN_ONLY Nr. 7 - {'the duplicate hide' if first else 'the rename'} "
        f"(`{lane.name}`): plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/chiapa.py` from the read-only "
        f"production read of {read.read_at} (`../{READ_PATH.name}`). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, change keys "
        f"`{lane.key_prefix}:<site_id>:<column>`, premise `{lane.premise_sql}`. Decision: "
        f"`{DECISION_SOURCE}`, Nr. 7 (O9, 2026-09-26).",
        "",
        f"**{plan.counters['sites']} site, {plan.counters['cells']} cells.** "
        + (
            "Runs first: the rename (`../name/`) is refused by its guard 5 until this has landed."
            if first
            else "Runs second: refused by guard 5 until the hide (`../hide/`) has landed."
        ),
        "",
        "| site | cell | old | new |",
        "|---|---|---|---|",
    ]
    for v in plan.changes:
        old = "NULL" if v.old_value is None else f"`{v.old_value}`"
        lines.append(f"| {v.site_name} (`{v.site_id}`) | {v.column} | {old} | `{v.new_value}` |")
    lines += [
        "",
        f"Premise carried by every cell: `{plan.changes[0].premise}`.",
        "",
        "## What the transaction checks",
        "",
        *[f"* {g}" for g in _GUARDS[lane.name]],
        "",
        "## Evidence",
        "",
    ]
    for e in plan.changes[0].evidence:
        lines.append(f"* {e['source']}: {e['quote']}")
    lines += [
        "",
        "## Run (after the plan; the hide's lane first, then the rename's)",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        *_commands(lane),
        "```",
        "",
        "Undo, only as a decision: the rename's `ROLLBACK.sql` first (its guard 5 needs the hide "
        "standing), then the hide's.",
        "",
    ]
    return "\n".join(lines)


def write_plans(hide: P.Plan, rename: P.Plan, read: Read, root: Path) -> None:
    """Each lane's files in its own directory under `root` (`apply.lane_dir` for the default)."""
    for plan in (hide, rename):
        directory = root / plan.lane.out_dir_name
        directory.mkdir(parents=True, exist_ok=True)
        P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
        (directory / "PLAN.md").write_text(plan_md(plan, read), encoding="utf-8", newline="\n")
        # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo
        P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=directory / "PLAN.jsonl")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan HUMAN_ONLY Nr. 7: the hide and the rename")
    ap.add_argument("--root", type=Path, default=ROOT, help="default: output/remediation")
    ap.add_argument(
        "--write",
        action="store_true",
        help="read production (read-only) and write both lanes' PLAN.jsonl, PLAN.md, ROLLBACK.sql",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.write:
        ap.print_help()
        return 0
    try:
        path = write_read(args.root / READ_PATH)
        read = parse_read(path.read_text(encoding="utf-8"))
        hide, rename = build(read, P._now())
    except P.PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    write_plans(hide, rename, read, args.root)
    print(json.dumps({lane.lane.name: dict(lane.counters) for lane in (hide, rename)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
