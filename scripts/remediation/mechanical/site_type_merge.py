"""Owner decision D25 "merge the site_type vocabulary": the site_type merge lane (Phase 8).

## The defect

The curated sites carry two spellings of one type side by side: the curated import's compound
types (`City/town/settlement`, `Fortress/citadel`, `Cave Structures`) and the bare words other lanes
and the 2025 import wrote (`Settlement`, `Fortress`, `Cave`). Both are canonical
(`pipeline/normalizers/site_type.py:CANONICAL_TYPES`, the keys of the globe's `CATEGORY_COLORS`), so
no normaliser joins them, and the filter, the cards' `mystery` (which counts `(site_type,
period_name)` pairs) and the page titles treat one kind of site as two. Measured on production
2026-10-24: 212 curated rows in 15 such values (`report`); the decided map (orchestrator decision X14,
adversarially checked) merges 16 values - City and Castle added, Megalithic kept - over 308 rows.

## The map (`site_type_merge.json`, pinned by `MAP_SHA256`)

Each alias is a canonical type that names what the compound type of **its own category group**
names (`api/cardgame/constants.py`, `_GROUP_DEFINITIONS`); a pair across two groups (Bridge vs
Gate/archway/bridge, Aqueduct vs Reservoir/aqueduct/canal) is refused when the map is read, and so
is a target that is not canonical, not a fixed point of `normalize_site_type` (the Lyra container
normalises at every boot) or itself an alias. The vocabulary lists stay as they are - only the data
moves (`plans/fields.md` item 8 and trap 10). The map is a proposal until its `decision` names who
decided it (fields.md item 8: Opus high decides, plus an adversarial check): `report` reads an
undecided map, `wave` refuses one.

## How a row is decided (`classify`, first failure refuses)

1. the row still exists and is curated; 2. it still holds an alias of the map (a row a later lane
moved is listed, not written); 3. its `site_type` journal ends at the live value
(`plan.journal_break`) - otherwise something wrote it around the journal. Then the row is written
to the alias's target. Retired rows are merged too: the vocabulary is one for every curated row, and
a row the scope lane takes back carries the merged type.

## The write

`site-type-merge-<wave>-sNNN`, a column lane on `unified_sites.site_type` of at most 100 sites a
step (owner decision D8), one journalled cell a site, under its own run stamp. Guard 3 holds the
alias the plan read, guard 4 the map's targets. A type write changes every `mystery` share of both
types and voids every earlier card_stats wave's `ROLLBACK.sql`: run the lane after the last wd5 wave
and before the final card_stats wave (`FIELDS_WD5.md` section 13).

## The P31 table moves after the data (`table`)

`fields/p31_site_types.json` lists the types each Wikidata class is consistent with, and
`fields/classify.py` holds a stored type that no listed class names as an identity doubt or a
site_type CONFLICT. So the table keeps every alias while any curated row still holds one: a table
without them would flag the unmerged rows of every classify run before the merge, and a table tied
to an undecided map is wrong when the decision drops a pair. Once the map is decided and the last
wave accepted, `table --write` replaces each alias by its target in the table (refused while the map
is undecided or a curated row still holds an alias, read-only from production) and prints the new
sha256; that file and `classify.TABLE_SHA256` are committed together, before the next field wave
(plans/fields.md item 8: otherwise a later wave proposes the old names again).

    M=scripts/remediation/mechanical
    $M/site_type_merge.py report                    (read-only: the map and its counts)
    $M/site_type_merge.py wave   --wave W           (read-only; WAVE.json: the alias rows, steps of 100)
    $M/site_type_merge.py step   --wave W --step N  (read-only; PLAN.jsonl, PLAN.md, ROLLBACK.sql)
    $M/apply.py --lane site-type-merge-W-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane site-type-merge-W-sNNN --rehearse-rollback
    $M/site_type_merge.py accept --wave W --step N  (read-only; 0 deviations)
    $M/site_type_merge.py table [--write]           (read-only production read; after the last
                                                     accept: the P31 table without the aliases)
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import classify as FC  # noqa: E402 - the P31 table and its pin

from mechanical.field_prov import read_production, sha256_file, step_name  # noqa: E402
from mechanical.lane import (  # noqa: E402
    _CURATED_ROWS,
    LOCK_TIMEOUT,
    SITE_TYPE_MERGE_LANE,
    STATEMENT_TIMEOUT,
    Lane,
    Residual,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    journal_break,
    parse_tagged_export,
    sql_ids,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type  # noqa: E402

MAP_FILE = _HERE.with_name("site_type_merge.json")
#: sha256 of the map's LF text. The map is reviewed data: a changed map is refused until this pin is
#: moved with it, in one reviewed commit (the rule of `fields/classify.TABLE_SHA256`).
MAP_SHA256 = "56418e49a550e57e71e5c1f9f713e3c97d777ffc2c707969f49afa94cc8e257e"
MAP_KEYS = frozenset({"_about", "decision", "aliases", "not_merged"})
DECISION_KEYS = frozenset({"by", "at", "check"})
ROOT_NAME = "mechanical_site_type_merge"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
MAX_SITES = 100
WAVE_FILE, WAVE_PIN_FILE, ACCEPTED_FILE = "WAVE.json", "WAVE.sha256", "ACCEPTED.json"
RETIRED = "retired"
CONSTANTS = REPO / "api" / "cardgame" / "constants.py"


# ------------------------------------------------------------------------------ the map
@functools.cache
def category_group() -> Mapping[str, str]:
    """The card game's category group of every canonical type (`CATEGORY_GROUP`), read from
    `api/cardgame/constants.py` without importing the API package (`api/__init__.py` builds the
    whole app) - the way `pipeline/generate_shared_data.py` reads the same module."""
    spec = importlib.util.spec_from_file_location("_site_type_merge_constants", CONSTANTS)
    if spec is None or spec.loader is None:
        raise PlanError(f"{CONSTANTS} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.CATEGORY_GROUP)


@dataclass(frozen=True)
class Merge:
    alias: str
    target: str
    why: str


@dataclass(frozen=True)
class MergeMap:
    """The decided (or proposed) aliases and the values considered and kept."""

    merges: Mapping[str, Merge]
    not_merged: Mapping[str, str]
    decision: Mapping[str, str] | None
    sha256: str

    @property
    def aliases(self) -> tuple[str, ...]:
        return tuple(sorted(self.merges))

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(sorted({m.target for m in self.merges.values()}))


def parse_map(text: str, sha256: str) -> MergeMap:
    """The map, every pair checked: both canonical, the target a fixed point of the boot
    normaliser and no alias itself, both in one category group."""
    data = json.loads(text)
    if set(data) != MAP_KEYS:
        raise PlanError(f"the map holds the keys {sorted(data)}, not {sorted(MAP_KEYS)}")
    groups = category_group()
    merges: dict[str, Merge] = {}
    for alias, entry in data["aliases"].items():
        if set(entry) != {"target", "why"} or not str(entry["why"]).strip():
            raise PlanError(f"{alias!r}: {entry!r} is not a map entry (target and why)")
        target = entry["target"]
        if alias not in CANONICAL_TYPES:
            raise PlanError(f"{alias!r} is no canonical type: the map merges vocabulary words")
        if target not in CANONICAL_TYPES or normalize_site_type(target) != target:
            raise PlanError(
                f"{alias!r} -> {target!r}: the target is not a canonical type that "
                "normalize_site_type keeps as it is (the Lyra boot normaliser would rewrite it)"
            )
        if target == alias or target in data["aliases"]:
            raise PlanError(f"{alias!r} -> {target!r}: a target is never an alias itself")
        if groups[alias] != groups[target]:
            raise PlanError(
                f"{alias!r} ({groups[alias]}) -> {target!r} ({groups[target]}): a merge never "
                "crosses a category group"
            )
        merges[alias] = Merge(alias, target, str(entry["why"]))
    if not merges:
        raise PlanError("the map merges nothing")
    kept = {str(k): str(v) for k, v in data["not_merged"].items()}
    both = sorted(set(kept) & set(merges))
    if both:
        raise PlanError(f"{both} are merged and listed as not merged")
    decision = data["decision"]
    if decision is not None and (
        set(decision) != DECISION_KEYS or not all(str(decision[k]).strip() for k in DECISION_KEYS)
    ):
        raise PlanError(f"the decision {decision!r} names no `by`, `at` and `check`")
    return MergeMap(merges, kept, decision, sha256)


def load_map(path: Path = MAP_FILE, *, pin: str = MAP_SHA256) -> MergeMap:
    digest = sha256_file(path)
    if digest != pin:
        raise PlanError(
            f"{path} is not the pinned map (sha256 {digest[:16]}, pinned {pin[:16]}): review the "
            "change and move MAP_SHA256 with it"
        )
    return parse_map(path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"), digest)


def _values_sql(values: Iterable[str]) -> str:
    return ", ".join(sql_literal(v) for v in sorted(values))


def alias_residual(merge_map: MergeMap) -> Residual:
    return Residual(
        "curated rows whose site_type is a merged alias",
        f"site_type IN ({_values_sql(merge_map.aliases)})",
    )


# ------------------------------------------------------------------------------ the lanes
def merge_lane(wave: str, step: int, merge_map: MergeMap) -> Lane:
    """The lane of one step: its own stamp, key prefix and directory; it owns the map's targets."""
    name = f"site-type-merge-{wave}-{step_name(step)}"
    if SITE_TYPE_MERGE_LANE.match(name) is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-25 or 2026-10-25b")
    residual = alias_residual(merge_map)
    return Lane(
        name=name,
        column="site_type",
        max_chars=100,
        key_prefix=name,
        run_stamp=f"{wave}_mechanical-site-type-merge-{step_name(step)}",
        test_id="D25/site-type-merge",
        confidence="authoritative",
        label="D25 site_type merge",
        plan_table="_site_type_merge_plan",
        out_dir_name=f"{ROOT_NAME}/{wave}/{step_name(step)}",
        post_commit_residual=residual,
        rehearsal_residual=residual,
        allowed_new_values=merge_map.targets,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
    )


def lane_of(name: str) -> Lane:
    """`site-type-merge-2026-10-25-s001` -> the lane (over the pinned map); `KeyError` otherwise."""
    match = SITE_TYPE_MERGE_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return merge_lane(match.group(1), int(match.group(2)), load_map())


@functools.cache
def readback(lane: Lane) -> str:
    """The read-only verification of one step, before and after its write."""
    merge_map = load_map()
    stamp = sql_literal(lane.run_stamp)
    journal = f"FROM remediation_change_log WHERE run_stamp = {stamp} AND "
    return journal_readback(
        lane,
        [
            (lane.post_commit_residual.metric, _CURATED_ROWS + lane.post_commit_residual.predicate),
            (
                "curated rows of a merge target",
                _CURATED_ROWS + f"site_type IN ({_values_sql(merge_map.targets)})",
            ),
            (
                "journal rows for this run whose old value is no merged alias",
                journal + f"old_value NOT IN ({_values_sql(merge_map.aliases)})",
            ),
            (
                "journal rows for this run that write another target than the alias's",
                journal
                + "CASE "
                + " ".join(
                    f"WHEN old_value = {sql_literal(m.alias)} THEN new_value <> {sql_literal(m.target)}"
                    for m in sorted(merge_map.merges.values(), key=lambda m: m.alias)
                )
                + " ELSE true END",
            ),
        ],
    )


# ------------------------------------------------------------------------------ the read
def candidates_sql(merge_map: MergeMap) -> str:
    return (
        "SELECT u.id::text AS site_id FROM unified_sites u WHERE u.source_id = "
        f"{sql_literal(CURATED_SOURCE)} AND u.site_type IN ({_values_sql(merge_map.aliases)}) "
        "ORDER BY u.id"
    )


def site_sql(site_ids: Iterable[str]) -> str:
    return (
        "SELECT u.id::text AS site_id, u.name, u.source_id, u.scope_status, u.site_type "
        f"FROM unified_sites u WHERE u.id::text IN ({sql_ids(site_ids)}) ORDER BY u.id"
    )


def journal_sql(site_ids: Iterable[str]) -> str:
    return (
        "SELECT l.id, l.row_pk, l.run_stamp, coalesce(l.test_id, '') AS test_id, l.old_value, "
        "l.new_value FROM remediation_change_log l WHERE l.table_name = 'unified_sites' AND "
        f"l.column_name = 'site_type' AND l.row_pk IN ({sql_ids(site_ids)}) ORDER BY l.id"
    )


def counts_sql(values: Iterable[str]) -> str:
    return (
        "SELECT u.site_type, count(*) AS curated, count(*) FILTER (WHERE u.scope_status = "
        f"{sql_literal(RETIRED)}) AS retired FROM unified_sites u WHERE u.source_id = "
        f"{sql_literal(CURATED_SOURCE)} AND u.site_type IN ({_values_sql(values)}) "
        "GROUP BY u.site_type ORDER BY u.site_type"
    )


@dataclass(frozen=True)
class Live:
    site_id: str
    name: str
    source_id: str
    scope_status: str | None
    site_type: str | None


def parse_export(text: str) -> tuple[dict[str, Live], dict[str, list[JournalLink]]]:
    rows, _at = parse_tagged_export(text, ("site", "journal"))
    live = {
        str(r["site_id"]): Live(
            str(r["site_id"]),
            str(r["name"]),
            str(r["source_id"]),
            r["scope_status"],
            r["site_type"],
        )
        for r in rows["site"]
    }
    journal: dict[str, list[JournalLink]] = {}
    for r in rows["journal"]:
        journal.setdefault(str(r["row_pk"]), []).append(
            JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    return live, journal


# ------------------------------------------------------------------------------ the decision
def classify(
    site_id: str, site: Live | None, links: Sequence[JournalLink], merge_map: MergeMap
) -> Verdict:
    """Decide one row. Every check is named, and the first failure is the reason."""

    def verdict(ok: bool, reason: str, note: str, **kw: Any) -> Verdict:
        return Verdict(
            site_id=site_id,
            site_name=site.name if site is not None else "",
            ok=ok,
            old_value=site.site_type if site is not None else None,
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=any(link.run_stamp.startswith("phase3:") for link in links),
            finding_test_id="live:unified_sites.site_type",
            evidence=tuple(kw.get("evidence", ())),
        )

    if site is None:
        return verdict(False, "site-gone", "the wave listed the site; production no longer has it")
    if site.source_id != CURATED_SOURCE:
        return verdict(
            False,
            "row-not-in-curated-source",
            f"the row belongs to source_id={site.source_id!r}; this lane writes curated sites only",
        )
    merge = merge_map.merges.get(site.site_type or "")
    if merge is None:
        return verdict(
            False,
            "not-an-alias",
            f"the row holds {site.site_type!r}, no alias of the map: a lane moved it since the wave",
        )
    broken = journal_break(links, site.site_type)
    if broken is not None:
        return verdict(False, *broken)
    last = links[-1] if links else None
    evidence = [
        {
            "source": f"scripts/remediation/mechanical/site_type_merge.json (sha256 {merge_map.sha256})",
            "url": "scripts/remediation/mechanical/site_type_merge.json",
            "quote": f"{merge.alias!r} -> {merge.target!r}: {merge.why}",
        },
        {
            "source": "pipeline/normalizers/site_type.py:CANONICAL_TYPES",
            "url": "pipeline/normalizers/site_type.py",
            "quote": f"{merge.target!r} is canonical and normalize_site_type({merge.target!r}) = "
            f"{merge.target!r}; group {category_group()[merge.target]!r} as {merge.alias!r}",
        },
    ]
    if last is not None:
        evidence.append(
            {
                "source": f"remediation_change_log:{last.id}",
                "url": "remediation_change_log",
                "quote": f"{last.run_stamp} ({last.test_id}): {last.old_value!r} -> "
                f"{last.new_value!r}",
            }
        )
    return verdict(
        True,
        "",
        f"{merge.alias!r} -> {merge.target!r} (D25 vocabulary merge)",
        new_value=merge.target,
        rule="merge-alias",
        evidence=evidence,
    )


@dataclass(frozen=True)
class StepPlan:
    plan: Plan


def build_step(
    wave: str,
    step: int,
    sites: Sequence[str],
    live: Mapping[str, Live],
    journal: Mapping[str, Sequence[JournalLink]],
    merge_map: MergeMap,
    *,
    built_at: str,
) -> StepPlan:
    """The lane plan of one step over `sites` (at most 100). Pure."""
    if len(sites) > MAX_SITES:
        raise PlanError(f"a step writes at most {MAX_SITES} sites, not {len(sites)}")
    verdicts = [classify(s, live.get(s), journal.get(s, ()), merge_map) for s in sorted(sites)]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters: dict[str, int] = {
        "cells": len(changes),
        **{f"skip:{k}": n for k, n in sorted(Counter(v.reason for v in skipped).items())},
        **{
            f"merge:{k}": n
            for k, n in sorted(Counter(f"{v.old_value} -> {v.new_value}" for v in changes).items())
        },
    }
    plan = Plan(
        changes=changes,
        skipped=skipped,
        built_at=built_at,
        counters=counters,
        lane=merge_lane(wave, step, merge_map),
    )
    return StepPlan(plan)


# ------------------------------------------------------------------------------ the report
def report(merge_map: MergeMap, *, read: Callable[[str], str] = read_production) -> dict[str, Any]:
    """The map and the counts it would move, read-only: per alias the curated and retired rows,
    the target's own rows today, the values considered and kept, and the alias rows whose journal
    does not end at their live value (the plan would refuse them)."""
    values = set(merge_map.aliases) | set(merge_map.targets) | set(merge_map.not_merged)
    text = read(tagged_export_script([("count", counts_sql(values))]))
    rows, at = parse_tagged_export(text, ("count",))
    counts = {str(r["site_type"]): (int(r["curated"]), int(r["retired"])) for r in rows["count"]}
    ids_text = read(tagged_export_script([("site", candidates_sql(merge_map))]))
    ids = [str(r["site_id"]) for r in parse_tagged_export(ids_text, ("site",))[0]["site"]]
    refused: Counter[str] = Counter()
    if ids:
        live, journal = parse_export(
            read(tagged_export_script([("site", site_sql(ids)), ("journal", journal_sql(ids))]))
        )
        for site in ids:
            v = classify(site, live.get(site), journal.get(site, ()), merge_map)
            if not v.ok:
                refused[v.reason] += 1
    groups = category_group()
    aliases = {
        m.alias: {
            "target": m.target,
            "group": groups[m.alias],
            "curated": counts.get(m.alias, (0, 0))[0],
            "retired": counts.get(m.alias, (0, 0))[1],
            "shown": counts.get(m.alias, (0, 0))[0] - counts.get(m.alias, (0, 0))[1],
        }
        for m in sorted(merge_map.merges.values(), key=lambda m: m.alias)
    }
    return {
        "read_at": at,
        "map_sha256": merge_map.sha256,
        "decided": merge_map.decision is not None,
        "aliases": aliases,
        "rows": sum(a["curated"] for a in aliases.values()),
        "shown_rows": sum(a["shown"] for a in aliases.values()),
        "targets_before": {t: counts.get(t, (0, 0))[0] for t in merge_map.targets},
        "not_merged": {v: counts.get(v, (0, 0))[0] for v in sorted(merge_map.not_merged)},
        "refused": dict(sorted(refused.items())),
    }


# ------------------------------------------------------------------------------ the wave
def wave_dir(wave: str, root: Path = ROOT) -> Path:
    return root / wave


def build_wave(
    wave: str,
    *,
    merge_map: MergeMap,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:
    """WAVE.json: the curated rows that hold an alias, in steps of 100, and the map's sha256 -
    from one read-only production read. Refused while the map is a proposal."""
    merge_lane(wave, 1, merge_map)  # refuses a wave label no lane resolves
    if merge_map.decision is None:
        raise PlanError(
            "the map is a proposal: record who decided it in site_type_merge.json `decision` (by, "
            "at, check - fields.md item 8: Opus high decides, plus an adversarial check) and move "
            "MAP_SHA256 with it"
        )
    target = wave_dir(wave, root)
    if (target / WAVE_FILE).exists():
        raise PlanError(f"{target / WAVE_FILE} exists: a wave is planned once")
    rows, at = parse_tagged_export(
        read(tagged_export_script([("site", candidates_sql(merge_map))])), ("site",)
    )
    sites = sorted(str(r["site_id"]) for r in rows["site"])
    steps = [sites[i : i + MAX_SITES] for i in range(0, len(sites), MAX_SITES)]
    record = {
        "wave": wave,
        "read_at": at,
        "map_sha256": merge_map.sha256,
        "sites": len(sites),
        "steps": steps,
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / WAVE_FILE).write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    (target / WAVE_PIN_FILE).write_text(
        sha256_file(target / WAVE_FILE) + "\n", encoding="utf-8", newline="\n"
    )
    return {"wave": wave, "sites": len(sites), "steps": len(steps)}


def read_wave(wave: str, root: Path = ROOT) -> dict[str, Any]:
    """A wave's WAVE.json - refused when it is not the file its pin names."""
    target = wave_dir(wave, root)
    path = target / WAVE_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `site_type_merge.py wave` first")
    if sha256_file(path) != (target / WAVE_PIN_FILE).read_text(encoding="utf-8").strip():
        raise PlanError(f"{path} is not the pinned wave: it was edited")
    return json.loads(path.read_text(encoding="utf-8"))


def _step_dir(wave: str, step: int, root: Path) -> Path:
    return wave_dir(wave, root) / step_name(step)


def write_plan_md(plan: Plan, path: Path) -> None:
    lane = plan.lane
    lines = [
        f"# D25 site_type merge - {lane.name}",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/site_type_merge.py`. Run stamp "
        f"`{lane.run_stamp}`, test id `{lane.test_id}`, change keys `{lane.key_prefix}:<site_id>`.",
        "",
        f"**{len(plan.changes)} row(s) merged, {len(plan.skipped)} refused** (`SKIPPED.jsonl`).",
        "",
        "| alias -> target | rows |",
        "|---|---|",
        *(
            f"| {k.removeprefix('merge:')} | {n} |"
            for k, n in plan.counters.items()
            if k.startswith("merge:")
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def plan_step(
    wave: str,
    step: int,
    *,
    merge_map: MergeMap,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Plan step `step` from the pinned wave and a fresh read-only production read - never a step
    before the one before it is accepted, never over another map than the wave's."""
    record = read_wave(wave, root)
    if record["map_sha256"] != merge_map.sha256:
        raise PlanError(
            f"wave {wave} was built over the map {record['map_sha256'][:16]}, this map is "
            f"{merge_map.sha256[:16]}: plan a new wave"
        )
    if not 1 <= step <= len(record["steps"]):
        raise PlanError(f"wave {wave} has steps 1..{len(record['steps'])}, not {step}")
    if step > 1 and not (_step_dir(wave, step - 1, root) / ACCEPTED_FILE).exists():
        raise PlanError(
            f"step {step - 1} is not accepted: `site_type_merge.py accept --step {step - 1}`"
        )
    out = _step_dir(wave, step, root)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once")
    sites = record["steps"][step - 1]
    text = read(tagged_export_script([("site", site_sql(sites)), ("journal", journal_sql(sites))]))
    live, journal = parse_export(text)
    built = build_step(
        wave, step, sites, live, journal, merge_map, built_at=datetime.now(UTC).isoformat()
    )
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    write_skipped_jsonl(built.plan, out / "SKIPPED.jsonl")
    write_plan_md(built.plan, out / "PLAN.md")
    if built.plan.changes:
        write_plan_jsonl(built.plan, out / "PLAN.jsonl")
        write_rollback_sql(built.plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return {"step": step, "lane": built.plan.lane.name, **built.plan.counters}


# ------------------------------------------------------------------------------ the acceptance
def deviations(
    lane: Lane,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
    undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
    if undone:
        found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
    by_site = {j["row_pk"]: j for j in written}
    if len(by_site) != len(written) or set(by_site) != {r["site_id"] for r in rows}:
        found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned")
    for row in rows:
        site = live.get(row["site_id"])
        entry = by_site.get(row["site_id"])
        if site is None or site.site_type != row["new_value"]:
            found.append(f"{row['site_id']}: site_type does not hold the planned value")
        if entry is None or (entry["old_value"], entry["new_value"]) != (
            row["old_value"],
            row["new_value"],
        ):
            found.append(f"{row['site_id']}: the journal row is not the plan's")
    return found


def accept_step(
    wave: str,
    step: int,
    *,
    merge_map: MergeMap,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> tuple[int, list[str]]:
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once."""
    lane = merge_lane(wave, step, merge_map)
    out = _step_dir(wave, step, root)
    plan_path = out / "PLAN.jsonl"
    rows = (
        [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines() if line]
        if plan_path.exists()
        else []
    )
    stamps = ", ".join(sql_literal(s) for s in (lane.run_stamp, lane.rollback_run_stamp))
    parts = [
        (
            "journal",
            "SELECT l.row_pk, l.run_stamp, l.old_value, l.new_value FROM remediation_change_log l "
            f"WHERE l.run_stamp IN ({stamps}) ORDER BY l.id",
        )
    ]
    if rows:
        parts.insert(0, ("site", site_sql(r["site_id"] for r in rows)))
    parsed, at = parse_tagged_export(read(tagged_export_script(parts)), ("site", "journal"))
    live = {
        str(r["site_id"]): Live(
            str(r["site_id"]),
            str(r["name"]),
            str(r["source_id"]),
            r["scope_status"],
            r["site_type"],
        )
        for r in parsed["site"]
    }
    found = deviations(lane, rows, live, parsed["journal"])
    accepted = out / ACCEPTED_FILE
    if not found and not accepted.exists():
        accepted.write_text(
            json.dumps(
                {
                    "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "read_at": at,
                    "cells": len(rows),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the P31 table
#: The sentence of the table's `about` the merge note goes in front of.
TABLE_PIN_NOTE = "; pinned by fields/classify.py TABLE_SHA256."


def merged_table(text: str, merge_map: MergeMap) -> tuple[str, int]:
    """The P31 table's text with every alias of the map replaced by its target (a type a class
    then lists twice is kept once, in its first place), and the number of classes changed. Pure.
    Written the table's own way (`indent=1`, UTF-8 unescaped), so only the moved types differ."""
    data = json.loads(text)
    changed = 0
    for row in data["classes"].values():
        types: list[str] = []
        for name in row["types"]:
            merged = merge_map.merges[name].target if name in merge_map.merges else name
            if merged not in types:
                types.append(merged)
        if types != row["types"]:
            row["types"] = types
            changed += 1
    if not changed:
        raise PlanError("the table offers no alias of the map: it is merged already")
    if data["about"].count(TABLE_PIN_NOTE) != 1:
        raise PlanError(f"the table's about does not end in {TABLE_PIN_NOTE!r}")
    data["about"] = data["about"].replace(
        TABLE_PIN_NOTE,
        f"; without the site_type aliases the merge map (mechanical/site_type_merge.json, sha256 "
        f"{merge_map.sha256[:16]}) moved into their targets{TABLE_PIN_NOTE}",
    )
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n", changed


def table(
    merge_map: MergeMap,
    *,
    read: Callable[[str], str] = read_production,
    path: Path = FC.TABLE,
    write: bool = False,
) -> dict[str, Any]:
    """The P31 table without the aliases, once the merge is in production: refused while the map
    is undecided or a curated row (shown or retired) still holds an alias. `write` replaces the
    file (LF); the caller moves `classify.TABLE_SHA256` to the printed sha256 in the same commit."""
    if merge_map.decision is None:
        raise PlanError(
            "the map is undecided: the P31 table moves with the decided merge, after its last "
            "wave is accepted"
        )
    rows, at = parse_tagged_export(
        read(tagged_export_script([("site", candidates_sql(merge_map))])), ("site",)
    )
    if rows["site"]:
        raise PlanError(
            f"{len(rows['site'])} curated row(s) still hold an alias (read {at}): the P31 table "
            "moves after the last merge wave is accepted"
        )
    text, changed = merged_table(
        path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"), merge_map
    )
    FC.parse_table(text)  # the merged table is still a table: canonical types, none twice
    if write:
        path.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "read_at": at,
        "classes_changed": changed,
        "table_sha256": digest,
        "written": write,
        "next": f'move fields/classify.py TABLE_SHA256 to "{digest}" in the same commit',
    }


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report")
    sub.add_parser("table").add_argument(
        "--write", action="store_true", help="replace fields/p31_site_types.json"
    )
    for name in ("wave", "step", "accept"):
        command = sub.add_parser(name)
        command.add_argument(
            "--wave", required=True, help="a date label: 2026-10-25 or 2026-10-25b"
        )
        if name != "wave":
            command.add_argument("--step", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        merge_map = load_map()
        if args.command == "report":
            _print(report(merge_map))
        elif args.command == "table":
            _print(table(merge_map, write=args.write))
        elif args.command == "wave":
            _print(build_wave(args.wave, merge_map=merge_map))
        elif args.command == "step":
            _print(plan_step(args.wave, args.step, merge_map=merge_map))
        else:
            code, found = accept_step(args.wave, args.step, merge_map=merge_map)
            _print({"deviations": found})
            print(f"ACCEPT_EXIT={code}")
            return code
    except (PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
