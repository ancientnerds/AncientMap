"""L5's decisions as journalled writes: link steps and the name lane.

**Links** (`site_external_ids`, and `source_url` where the refresh's fixed point needs it) go
through the tool of the external-id waves 1-4 (`output/remediation/tools/qid_repair.py`,
`render_split(removals=True)`): `site_external_ids` is keyed `(site_id, kind, value)`, which
`apply_remediation_change()` cannot address (qid_repair's docstring), so each row is written by its
full key and journalled in the same transaction, `source_url` through the primitive. Steps of at most
100 sites, each its own run stamp (`2026-09-26_l5-links-NNN`) and directory
(`output/remediation/qid_repair/l5/step-NNN/`: PLAN.jsonl, APPLY.sql, ROLLBACK.sql, PLAN.md).

**Names** go through the mechanical cell lane `name-l5` (`mechanical/lane.py`): `name` and its match
key in one transaction, the key computed by Postgres from the new name in the plan's read
(`left(lower(unaccent(name)), 500)`, FIELD_CONTRACT 2.2). The pinned rename of HUMAN_ONLY Nr. 7 is
planned with them. `apply.py --lane name-l5` then emits, rehearses, probes, applies and verifies.

A decided site is written only as it was asked: a site whose stored links, `source_url`, name or
scope changed since the question's read is skipped, and so is a replacement item another curated
site carries (a duplicate candidate - WD2's, not a link). Every skip is listed with its reason.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import qid_repair as QR  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.lane import NAME_L5, sql_literal  # noqa: E402

from l5 import population as POP  # noqa: E402
from l5.decide import DECIDED  # noqa: E402
from pipeline.lyra.site_key import site_key_sql  # noqa: E402

STEPS = QR.OUT / "l5"
RUN_PREFIX = "2026-09-26_l5-links"
RESEARCH = "L5 link pass 2026-09-26 (Opus reading, quotes machine-checked)"
SITES_PER_STEP = 100
CONFIDENCE = "authoritative"
KINDS = ("wikidata_qid", "enwiki_title")


def step_wave(number: int) -> QR.Wave:
    """The journal identity of one link step: qid_repair's `Wave`, one per step."""
    if not 1 <= number <= 999:
        raise MP.PlanError(f"step {number} is not a step number")
    return QR.Wave(
        5,
        (),
        f"{RUN_PREFIX}-{number:03d}",
        STEPS / f"step-{number:03d}",
        RESEARCH,
        None,
    )


def statements(rows: list[QR.Change], wave: QR.Wave) -> dict[str, str]:
    """Every SQL file a step's runbook sends: L5's form of `render_split`."""
    return {
        "APPLY.sql": QR.render_split(rows, reversal=False, wave=wave, removals=True),
        "REHEARSAL.sql": QR.render_split(
            rows, reversal=False, rehearsal=True, wave=wave, removals=True
        ),
        "ROLLBACK.sql": QR.render_split(rows, reversal=True, wave=wave, removals=True),
    }


# ------------------------------------------------------------------------------ the live read
def live_sql(site_ids: Sequence[str]) -> str:
    return POP.sites_sql(site_ids)


def holders_sql(qids: Sequence[str]) -> str:
    return (
        "SELECT e.value AS qid, u.id::text AS site_id, u.name FROM site_external_ids e "
        "JOIN unified_sites u ON u.id = e.site_id WHERE e.kind = 'wikidata_qid' AND "
        "u.source_id = 'ancient_nerds' AND e.value IN ("
        + ", ".join(sql_literal(q) for q in sorted(qids))
        + ") ORDER BY e.value, u.id"
    )


def keys_sql(names: Sequence[str]) -> str:
    """Postgres's match key of each new name - the key is never computed in Python."""
    values = ", ".join(f"({sql_literal(n)})" for n in sorted(set(names)))
    return f"SELECT n AS name, {site_key_sql('n')} AS key FROM (VALUES {values}) AS v(n) ORDER BY n"


@dataclass(frozen=True)
class Live:
    """What production holds now for the decided sites, read-only."""

    sites: Mapping[str, Mapping[str, Any]]
    holders: Mapping[str, list[Mapping[str, Any]]]
    keys: Mapping[str, str]


def read_live(
    decisions: Sequence[Mapping[str, Any]],
    pinned: Mapping[str, POP.PinnedName],
    reader: Callable[[str], list[dict[str, Any]]],
) -> Live:
    ids = sorted({d["site_id"] for d in decisions} | set(pinned))
    sites = {str(r["site_id"]): r for r in reader(live_sql(ids))} if ids else {}
    new_items = sorted(
        {
            d["cells"]["wikidata_qid"]["new"]
            for d in decisions
            if d["cells"]["wikidata_qid"]["verdict"] == "REPLACE"
        }
    )
    holders: dict[str, list[Mapping[str, Any]]] = {}
    for row in reader(holders_sql(new_items)) if new_items else []:
        holders.setdefault(str(row["qid"]), []).append(row)
    names = [p.new for p in pinned.values()] + [
        d["cells"]["name"]["new"]
        for d in decisions
        if "name" in d["cells"] and d["cells"]["name"]["verdict"] == "RENAME"
    ]
    keys = {str(r["name"]): str(r["key"]) for r in reader(keys_sql(names))} if names else {}
    return Live(sites, holders, keys)


# ------------------------------------------------------------------------------ the plan
@dataclass
class L5Plan:
    links: list[QR.Change] = field(default_factory=list)
    names: list[MP.Verdict] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        link_sites = {c.site_id for c in self.links}
        kinds = Counter(
            f"link:{c.table}.{c.kind}:{'remove' if c.new_value is None else 'replace'}"
            for c in self.links
        )
        return {
            "link_rows": len(self.links),
            "link_sites": len(link_sites),
            "link_steps": -(-len(link_sites) // SITES_PER_STEP),
            "name_sites": len({v.site_id for v in self.names}),
            "skipped": len(self.skipped),
            **dict(sorted(kinds.items())),
            **{
                f"skip:{k}": n
                for k, n in sorted(Counter(s["reason"] for s in self.skipped).items())
            },
        }


def _evidence(decision: Mapping[str, Any], key: str) -> tuple[str, ...]:
    cell = decision["cells"][key]
    lines = [
        f"L5 reading ({decision['round']}, {decision['answered_by']}): {key} {cell['verdict']} "
        f"- {cell['why']}"
    ]
    lines += [f'{q["source"]}: "{q["quote"]}"' for q in cell["quotes"]]
    if cell["note"]:
        lines.append(f"machine check: {cell['note']}")
    return tuple(lines)


def _change(
    decision: Mapping[str, Any], table: str, kind: str, old: str | None, new: str | None
) -> QR.Change:
    sid, test_id = str(decision["site_id"]), f"L5/{kind}"
    key = "source_url" if table == QR.SITES_TABLE else kind
    return QR.Change(
        site_id=sid,
        name=str(decision["name"]),
        kind=kind,
        old_value=old,
        new_value=new,
        test_id=test_id,
        confidence=CONFIDENCE,
        evidence=_evidence(decision, key),
        change_key=QR.change_key(sid, kind, old, new, test_id, table=table),
        table=table,
    )


def _name_verdicts(
    sid: str,
    name: str,
    old_key: str | None,
    new_name: str,
    new_key: str,
    evidence: Sequence[dict[str, Any]],
    note: str,
) -> list[MP.Verdict]:
    return [
        MP.Verdict(
            site_id=sid,
            site_name=name,
            ok=True,
            old_value=old,
            new_value=new,
            rule="l5-name",
            reason="",
            note=note,
            phase3=False,
            finding_test_id="B1/name-l5",
            evidence=tuple(evidence),
            column=column,
        )
        for column, old, new in (("name", name, new_name), ("name_normalized", old_key, new_key))
    ]


def _same_as_asked(asked: Mapping[str, Any], now: Mapping[str, Any]) -> str | None:
    for key in ("ext", "source_url", "name", "scope_status"):
        if asked[key] != now[key]:
            return f"{key} changed since the question's read: {asked[key]!r} -> {now[key]!r}"
    return None


def build(
    decisions: Sequence[Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
    live: Live,
    *,
    pinned: Mapping[str, POP.PinnedName] = POP.PINNED_NAMES,
) -> L5Plan:
    """A pure function of the decisions, the question's read and the live read."""
    plan = L5Plan()

    def skip(decision: Mapping[str, Any], reason: str, note: str) -> None:
        plan.skipped.append(
            {
                "site_id": decision["site_id"],
                "name": decision["name"],
                "reason": reason,
                "note": note,
            }
        )

    for decision in sorted(decisions, key=lambda d: str(d["site_id"])):
        if decision["status"] != DECIDED:
            raise MP.PlanError(f"{decision['site_id']} is not decided - DECISIONS.jsonl is stale")
        sid = str(decision["site_id"])
        now = live.sites.get(sid)
        if now is None:
            skip(decision, "gone", "the site is no longer in unified_sites")
            continue
        changed = _same_as_asked(asked[sid], now)
        if changed is not None:
            skip(decision, "changed-since-the-question", changed)
            continue
        cells = decision["cells"]
        item = cells["wikidata_qid"]
        if item["verdict"] == "REPLACE":
            others = [h for h in live.holders.get(item["new"], []) if h["site_id"] != sid]
            if others:
                named = ", ".join(f"{h['name']} ({h['site_id']})" for h in others)
                skip(decision, "item-carried-by-another-site", f"{item['new']} is {named}'s")
                continue
        for kind in KINDS:
            cell = cells[kind]
            if cell["new"] != cell["old"]:
                plan.links.append(_change(decision, QR.TABLE, kind, cell["old"], cell["new"]))
        url = cells["source_url"]
        if url["new"] != url["old"]:
            plan.links.append(
                _change(decision, QR.SITES_TABLE, QR.URL_COLUMN, url["old"], url["new"])
            )
        name = cells.get("name")
        if name is not None and name["verdict"] == "RENAME" and sid not in pinned:
            evidence = [
                {"source": q["source"], "url": q["source"], "quote": q["quote"]}
                for q in name["quotes"]
            ]
            plan.names += _name_verdicts(
                sid,
                str(now["name"]),
                now["name_normalized"],
                str(name["new"]),
                live.keys[str(name["new"])],
                evidence,
                f"L5 reading ({decision['round']}, {decision['answered_by']}): {name['why']}",
            )
    for sid, rename in sorted(pinned.items()):
        now = live.sites.get(sid)
        if now is None or now["name"] != rename.old:
            plan.skipped.append(
                {
                    "site_id": sid,
                    "name": rename.old,
                    "reason": "pinned-name-moved",
                    "note": f"the row holds {None if now is None else now['name']!r}",
                }
            )
            continue
        plan.names += _name_verdicts(
            sid,
            rename.old,
            now["name_normalized"],
            rename.new,
            live.keys[rename.new],
            rename.evidence,
            "HUMAN_ONLY Nr. 7 (O9, 2026-09-26): the kept row takes its item's English label",
        )
    return plan


def steps(links: Sequence[QR.Change]) -> list[list[QR.Change]]:
    """The link rows in steps of at most `SITES_PER_STEP` whole sites, in site order."""
    by_site: dict[str, list[QR.Change]] = {}
    for change in links:
        by_site.setdefault(change.site_id, []).append(change)
    order = sorted(by_site)
    return [
        [c for sid in order[i : i + SITES_PER_STEP] for c in by_site[sid]]
        for i in range(0, len(order), SITES_PER_STEP)
    ]


# ------------------------------------------------------------------------------ the files
def step_markdown(rows: Sequence[QR.Change], wave: QR.Wave) -> str:
    lines = [
        f"# L5 link step {wave.out.name} - planned, not applied",
        "",
        f"{len(rows)} row change(s) at {len({r.site_id for r in rows})} site(s), run stamp "
        f"`{wave.run_stamp}` (rollback `{wave.rollback_stamp}`). Rendered by "
        "`scripts/remediation/l5/plan.py` through `qid_repair.render_split(removals=True)`; a new "
        "value `(removed)` deletes the row or clears the column.",
        "",
        "| site | table.kind | old | new |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        new = "(removed)" if r.new_value is None else f"`{r.new_value}`"
        lines.append(f"| {r.name} (`{r.site_id}`) | {r.table}.{r.kind} | `{r.old_value}` | {new} |")
    lines += ["", "## Evidence", ""]
    for r in rows:
        lines.append(f"* **{r.name}** {r.kind}")
        lines += [f"  * {e}" for e in r.evidence]
    lines.append("")
    return "\n".join(lines)


def write_step(wave: QR.Wave, rows: list[QR.Change]) -> None:
    """One step's files. A step directory that holds another plan is never overwritten: its
    ROLLBACK.sql may be the only undo of a write that has landed."""
    body = "".join(row.to_json_line() + "\n" for row in rows)
    plan_path = wave.out / "PLAN.jsonl"
    if plan_path.exists():
        if plan_path.read_text(encoding="utf-8") != body:
            raise MP.PlanError(
                f"{wave.out} holds another plan - a delivered step is never replaced; move it "
                "aside only if its run stamp has no journal row"
            )
        return
    wave.out.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(body, encoding="utf-8", newline="\n")
    rendered = statements(rows, wave)
    # the undo first: a process that dies between the two leaves an undo and no write
    for name in ("ROLLBACK.sql", "APPLY.sql"):
        (wave.out / name).write_text(rendered[name], encoding="utf-8", newline="\n")
    (wave.out / "PLAN.md").write_text(step_markdown(rows, wave), encoding="utf-8", newline="\n")


def load_step(wave: QR.Wave) -> list[QR.Change]:
    path = wave.out / "PLAN.jsonl"
    if not path.exists():
        raise MP.PlanError(f"{path} does not exist - run `run.py plan` first")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            rows.append(QR.Change(**{**record, "evidence": tuple(record["evidence"])}))
    return rows


def name_plan(plan: L5Plan, built_at: str) -> MP.Plan:
    sites = {v.site_id for v in plan.names}
    if len(sites) > SITES_PER_STEP:
        raise MP.PlanError(f"{len(sites)} renames exceed one step of {SITES_PER_STEP} sites")
    return MP.Plan(
        changes=tuple(plan.names),
        skipped=(),
        built_at=built_at,
        counters={"sites": len(sites), "cells": len(plan.names)},
        lane=NAME_L5,
    )


def write_names(plan: MP.Plan, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    MP.write_plan_jsonl(plan, out / "PLAN.jsonl")
    MP.write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    lines = [
        "# L5 name lane (`name-l5`) - planned, not applied",
        "",
        f"Built {plan.built_at} by `scripts/remediation/l5/plan.py`: {plan.counters['sites']} "
        f"site(s), {plan.counters['cells']} cell(s) (`name` and its match key, the key computed by "
        "Postgres from the new name). Run stamp "
        f"`{NAME_L5.run_stamp}`, journal test id `{NAME_L5.test_id}`.",
        "",
        "| site | old name | new name | new key |",
        "| --- | --- | --- | --- |",
    ]
    by_site: dict[str, dict[str, MP.Verdict]] = {}
    for v in plan.changes:
        by_site.setdefault(v.site_id, {})[str(v.column)] = v
    for sid, cells in sorted(by_site.items()):
        lines.append(
            f"| `{sid}` | {cells['name'].old_value} | {cells['name'].new_value} | "
            f"`{cells['name_normalized'].new_value}` |"
        )
    lines += ["", "## Evidence", ""]
    for sid, cells in sorted(by_site.items()):
        lines.append(f"* **{cells['name'].new_value}** (`{sid}`): {cells['name'].note}")
        lines += [f"  * {e['source']}: {e['quote']}" for e in cells["name"].evidence]
    lines += [
        "",
        "Run: `apply.py --lane name-l5 --emit`, `--rehearse`, `--probe-guards`, `--apply`, "
        "`--verify`, `--rehearse-rollback` (docs/procedures/SITES_DB_REMEDIATION_2026-09.md, WE "
        "lanes). On its next boot Lyra adds each new name to `unified_site_names` as a 'label' row "
        "(`_run_migrations`, the backfill); the old name stays there, so an exact search finds both.",
        "",
    ]
    (out / "PLAN.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    MP.write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
