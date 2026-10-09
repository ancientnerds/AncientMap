"""The name writes the identity package shares: a rename with its key, and the old name as an alias.

D13 (a re-targeted record takes the ancient site's name) and D23 (a broken or foreign name becomes
the English name) end in the same two writes, both through the shared writers and both journalled:

* **the rename** - the mechanical cell lane `retarget-name-<wave>` or `name-clean-<wave>`
  (`mechanical/identity_lanes.py`): `name` and `name_normalized` in one transaction, the key computed
  by Postgres from the new name in the plan's own read (`l5.plan.keys_sql`, never Python), the
  external ids the new name is attested by as the premise, and the lane's write invariant refusing a
  site whose key is not its name's key;
* **the old name as an alias** - one chunk of the shared writer (`gallery_audit/chunk_writer.py`,
  lane `<kind>-alias-<wave>`, one per rename lane): the `unified_site_names` row that holds the old name turns from
  `label` into `alias`, the only transition that writer allows for `name_type`. The search reads
  `name_type <> 'label'` (`api/routes/sites.py`), so a renamed site stays findable under its old
  name; Lyra's boot adds the new name as a `label` row. A site whose old name is already an alias
  (or any non-label row) needs nothing; a site with no row for its old name is listed, not guessed.

The plan of a wave is a pure function of the decisions and one live read (`Live`); every skip is
listed with its reason, and nothing is written for a site whose state moved since it was asked.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1]), str(REPO / "output" / "remediation" / "tools")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from gallery_audit import chunk_writer as CW  # noqa: E402
from l5 import plan as L5P  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.identity_lanes import WAVE, name_lane  # noqa: E402
from mechanical.lane import Lane, sql_literal  # noqa: E402

from identity import plan_files as PF  # noqa: E402
from identity.waves import SITES_PER_WAVE  # noqa: E402

LABEL, ALIAS = CW.NAME_TYPE_TRANSITION


def name_rows_sql(site_ids: Sequence[str]) -> str:
    """The name rows of the sites, read-only: which row holds a site's old name, and as what."""
    return (
        "SELECT n.id, n.site_id::text AS site_id, n.name, n.name_normalized, n.name_type "
        "FROM unified_site_names n WHERE n.site_id IN ("
        + ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(site_ids))
        + ") ORDER BY n.site_id, n.id"
    )


RENAME_KINDS = ("retarget-name", "name-clean")


def alias_lane(kind: str, wave: str) -> CW.Lane:
    """The old names of one rename lane's wave: their `label` rows turned into `alias` rows by the
    chunk writer. The stamp carries the lane (`retarget-name-alias-<wave>`, `name-clean-alias-<wave>`):
    both lanes may use the same date label, and a journal stamp is written once."""
    if kind not in RENAME_KINDS:
        raise ValueError(f"{kind!r} is not a rename lane: {', '.join(RENAME_KINDS)}")
    if re.fullmatch(WAVE, wave) is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-12 or 2026-10-12b")
    return CW.Lane(
        name=f"{kind}-alias-{wave}",
        test_id="D23/name-alias",
        stamp=f"{kind}-alias-{wave}",
        confidence="authoritative",
        label="D23 name alias",
    )


@dataclass
class NamePlan:
    """What a wave renames: the verdicts of its cells, the alias changes, and what it left out."""

    lane: Lane
    verdicts: list[MP.Verdict] = field(default_factory=list)
    aliases: list[CW.Change] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    already_searchable: list[str] = field(default_factory=list)

    @property
    def sites(self) -> list[str]:
        return sorted({v.site_id for v in self.verdicts})


def old_name_row(
    rows: Sequence[Mapping[str, Any]], old_key: str | None
) -> Mapping[str, Any] | None:
    """The name row of a site that holds its old name: the one whose key is the name's key."""
    found = [r for r in rows if r["name_normalized"] == old_key]
    return found[0] if found else None


def plan_rename(
    plan: NamePlan,
    *,
    site_id: str,
    live: Mapping[str, Any],
    new_name: str,
    new_key: str,
    holders: Sequence[Mapping[str, Any]],
    name_rows: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    note: str,
    wave: str,
    rule: str,
    finding_test_id: str,
) -> None:
    """One site's rename and alias into `plan`, or one skip with its reason.

    `holders` are the visible curated rows (other than this one) whose key already is `new_key`:
    two rows named alike is a duplicate question, never a rename."""

    def skip(reason: str, text: str) -> None:
        plan.skipped.append(
            {"site_id": site_id, "name": live["name"], "reason": reason, "note": text}
        )

    if new_name == live["name"]:
        skip("name-unchanged", "the stored name is already the planned name")
        return
    others = [h for h in holders if str(h["site_id"]) != site_id]
    if others:
        named = ", ".join(f"{h['name']} ({h['site_id']})" for h in others)
        skip("name-key-taken", f"{new_key!r} is already the key of {named}: a duplicate question")
        return
    old_row = old_name_row(name_rows, live["name_normalized"])
    if old_row is None and new_key != live["name_normalized"]:
        skip(
            "no-old-name-row",
            f"unified_site_names holds no row for the old key {live['name_normalized']!r}: the "
            "old name would not stay searchable - the owner list",
        )
        return
    plan.verdicts += L5P.name_verdicts(
        site_id,
        str(live["name"]),
        live["name_normalized"],
        new_name,
        new_key,
        [{"source": e["source"], "url": e["url"], "quote": e["quote"]} for e in evidence],
        note,
        premise=str(live["premise"]),
        rule=rule,
        finding_test_id=finding_test_id,
    )
    if old_row is None or new_key == live["name_normalized"]:
        return  # the key does not move: the old name is the new name's row
    if old_row["name_type"] != LABEL:
        plan.already_searchable.append(site_id)
        return
    plan.aliases.append(
        CW.Change(
            table="unified_site_names",
            column="name_type",
            row_key=str(old_row["id"]),
            site_id=site_id,
            old_value=LABEL,
            new_value=ALIAS,
            rule=rule,
            reason=f"{live['name']!r} stays searchable after the rename to {new_name!r}",
            evidence=[dict(e) for e in evidence],
        )
    )


def name_plan(plan: NamePlan, built_at: str) -> MP.Plan:
    if len(plan.sites) > SITES_PER_WAVE:
        raise MP.PlanError(f"{len(plan.sites)} renames exceed one wave of {SITES_PER_WAVE} sites")
    return MP.Plan(
        changes=tuple(plan.verdicts),
        skipped=(),
        built_at=built_at,
        counters={
            "sites": len(plan.sites),
            "cells": len(plan.verdicts),
            "aliases": len(plan.aliases),
            "already_searchable": len(plan.already_searchable),
            "skipped": len(plan.skipped),
        },
        lane=plan.lane,
    )


def write_name_plan(plan: NamePlan, built_at: str, out: Path) -> MP.Plan:
    """PLAN.jsonl, SKIPPED.jsonl, PLAN.md and ROLLBACK.sql of the rename lane into `out`; the
    alias chunk is written beside it by `write_alias_chunk`."""
    mech = name_plan(plan, built_at)
    lines = [
        *PF.header_lines(mech, plan.lane.label, "scripts/remediation/identity/"),
        "| site | old name | new name | new key |",
        "| --- | --- | --- | --- |",
    ]
    by_site: dict[str, dict[str, MP.Verdict]] = {}
    for v in mech.changes:
        by_site.setdefault(v.site_id, {})[str(v.column)] = v
    for sid, cells in sorted(by_site.items()):
        key = cells.get("name_normalized")
        shown = "unchanged" if key is None else f"`{key.new_value}`"
        lines.append(
            f"| `{sid}` | {cells['name'].old_value} | {cells['name'].new_value} | {shown} |"
        )
    lines += ["", "## Evidence", ""]
    for sid, cells in sorted(by_site.items()):
        lines.append(f"* **{cells['name'].new_value}** (`{sid}`): {cells['name'].note}")
        lines += [f"  * {e['source']}: {e['quote']}" for e in cells["name"].evidence]
    lines += PF.skipped_lines(plan.skipped)
    lines.append("")
    PF.write_cell_plan(mech, plan.skipped, out, "\n".join(lines))
    return mech


def write_alias_chunk(plan: NamePlan, kind: str, wave: str, out: Path) -> list[Path]:
    """The wave's alias chunk of the rename lane `kind` (one chunk: a wave is at most 100 sites), or
    nothing."""
    if not plan.aliases:
        return []
    chunks = CW.chunk_changes(alias_lane(kind, wave), plan.aliases)
    return CW.emit_chunks(out, chunks)


def rename_lane(kind: str, wave: str) -> Lane:
    """`name-clean` or `retarget-name`: the cell lane of a wave's renames."""
    return name_lane(kind, wave)
