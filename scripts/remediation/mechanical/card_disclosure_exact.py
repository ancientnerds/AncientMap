"""Lane WB's exact-disclosure correction (D56): `_card_provenance.ai_system` of the all-Opus version-3 cards.

## The defect

A version-3 (shorts-v1) card provenance names the model that answered each stage (`models`: write,
rate, check, verify) and discloses them in `ai_system` (`pipeline/utils/card_provenance.py`, EU AI
Act Art. 50). Until 2026-10-24 `model4.ai_system_for` returned the Opus-and-Sonnet string
(`model4.AI_SYSTEM_CLAUDE`) for any Opus and/or Sonnet chain, so the cards of the shorts pilots 2
and 3 (`wb-shorts-pilot2-2026-10-19`, `wb-shorts-pilot3-2026-10-20`), whose every stage Opus answered,
name Sonnet, which wrote none of them. Owner decision D56 (2026-10-24): the disclosure names exactly
the models whose answers a write rests on - `ai_system_for` now returns the Opus-only string
`model4.AI_SYSTEM_CLAUDE_OPUS` for an all-Opus chain - and those live cards get one journalled
correction before wave A.

## The list (`build_list`, pinned)

Each site that a closed lane-WB step left a version-3 teaser provenance on (the step's
`prov/PLAN.jsonl`, an `ACCEPTED/` step not undone, the latest step winning:
`card_disclosure.written_rows`) is listed when the disclosure `model4.ai_system_for` derives from the
provenance's own `models` is not the one it holds. The provenance is its own proof: no census and no
run outcome is read. A mismatch of any other pair than `AI_SYSTEM_CLAUDE` held and
`AI_SYSTEM_CLAUDE_OPUS` derived is a refusal, never a guess. A version-2 provenance names no models
and is not this lane's (the census lane `card_disclosure.py` decided those). The list is
deterministic (sorted by site id) and pinned in `card_disclosure_exact_list.py` by its sha256;
`list --check` re-derives it, and every `plan` does so first.

## What a step writes (`classify`, `exact_lane`)

`card-exact-sNNN`, a cell lane on `unified_sites.raw_data`, at most 100 sites per step (the list of
2026-10-24 holds 43, one step). Exactly one key changes: `_card_provenance.ai_system`, from
`AI_SYSTEM_CLAUDE` to `AI_SYSTEM_CLAUDE_OPUS` (`teaser.EXACT_CORRECTION`). The plan lists, and does
not write, a site whose live provenance is not exactly the listed one (`teaser-provenance-moved`),
that already names the Opus-only string (`already-corrected`), that has none, whose live models no
longer derive the Opus-only string (`models-moved`), or whose raw_data is not printed the way this
planner prints JSON. The transaction's guards: guard 3 holds the whole old `raw_data` (the old-value
guard: no key can have moved, `ai_system` included); guard 5 holds the provenance's identity
(`run|text_sha256|desc_sha256`, `card_disclosure.PREMISE_SQL`) - a card replaced since is refused;
the lane invariant refuses a provenance that names neither disclosure, write and reversal alike. The
read-back counts the journal rows that changed anything but this key (0), those whose old value did
not name `AI_SYSTEM_CLAUDE` (0), and the listed sites still naming it.

## Who accepts it, and for which key only

* `teaser.py accept --step N` (steps 36 and 37, the pilots' writes) reads a step's provenance cell as
  this lane left it (`teaser.corrected_cell` over `teaser.CORRECTIONS`): only this lane's own stamp
  counts, only as one journal row from exactly the raw_data that step planned to exactly that value
  with this one key corrected, and not reversed.
* `verify_writes4.py --lane p4|p4wc --allow-stamp 'wb-card-exact-s%'` supersedes by this lane's
  stamp for its one key only (`teaser.moves_disclosure_key`).
* `card_disclosure_exact.py accept --step N` is this lane's own acceptance (0 deviations, once).

Runbook: docs/procedures/CARD_DESCRIPTIONS.md, "5.10 The exact disclosure (D56)".

    M=scripts/remediation/mechanical
    $M/card_disclosure_exact.py list [--write | --check]   (offline; the closed steps' plans)
    $M/card_disclosure_exact.py plan --step N              (read-only; the step's sites, PLAN.md)
    $M/apply.py --lane card-exact-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane card-exact-sNNN --rehearse-rollback
    $M/card_disclosure_exact.py accept --step N            (read-only; ACCEPT_EXIT=0 at 0 deviations)
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections import Counter
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

from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from phase4 import model4 as M  # noqa: E402 - the disclosure the models derive
from phase4 import write4 as W4  # noqa: E402 - the exit line

from mechanical import card_disclosure as C  # noqa: E402 - the read, the premise, the list pin
from mechanical import card_disclosure_exact_list as LIST  # noqa: E402
from mechanical import teaser as W  # noqa: E402 - the closed steps, the correction pair, the read
from mechanical.citations import canonical, reprint  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_EXACT_LANE,
    LOCK_TIMEOUT,
    PROVENANCE_HASH_DIFFERS,
    STATEMENT_TIMEOUT,
    UNIFIED_SITES,
    Column,
    Lane,
    Residual,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
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
from pipeline.utils import card_provenance as CP  # noqa: E402

ROOT_NAME = "mechanical_card_exact"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
LIST_MODULE = _HERE.with_name("card_disclosure_exact_list.py")
ACCEPTED_DIR = "ACCEPTED"
MAX_SITES = 100
PROV = CP.CARD_PROVENANCE_KEY
#: The pair this lane owns (`teaser.EXACT_CORRECTION`): pinned to the string production holds and
#: the one `ai_system_for` derives for an all-Opus chain since D56 - never to an alias.
CORRECTION = W.EXACT_CORRECTION
OLD, NEW = CORRECTION.old, CORRECTION.new
TEST_ID = "WB/card-disclosure-exact"
RULE = "card-disclosure-exact"
DECISION = "owner decision D56 (2026-10-24, OWNER_DECISIONS_2026-10-08.md)"

_AI_SYSTEM = f"raw_data -> '{PROV}' ->> 'ai_system'"
#: Lane invariant: a planned site's provenance names neither disclosure - after the write and after
#: its reversal alike (write: `NEW`; reversal: `OLD`).
_NAMES_NEITHER = Residual(
    "planned sites whose card provenance names neither disclosure",
    f"coalesce({_AI_SYSTEM}, '') NOT IN ({sql_literal(OLD)}, {sql_literal(NEW)})",
)
_CURATED = "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "


def derived_of(provenance: Mapping[str, Any]) -> str:
    """The disclosure a version-3 provenance's own `models` derive (`model4.ai_system_for`)."""
    return M.ai_system_for(m for m in provenance["models"].values() if m is not None)


# ------------------------------------------------------------------------------ the lanes
def step_sites(step: int) -> tuple[str, ...]:
    """The pinned list's sites of one step (at most 100, in site order)."""
    chunk = LIST.SITE_IDS[(step - 1) * MAX_SITES : step * MAX_SITES] if step >= 1 else ()
    if not chunk:
        raise PlanError(f"step {step} has no sites: the pinned list holds {len(LIST.SITE_IDS)}")
    return chunk


def exact_lane(step: int) -> Lane:
    """The lane of one step: its own stamp (`teaser.EXACT_STAMP`), key prefix and directory."""
    name = f"card-exact-{W.step_name(step)}"
    still_old = Residual(
        "listed sites of this step still naming the Opus and Sonnet disclosure",
        f"id IN ({sql_ids(step_sites(step))}) AND {_AI_SYSTEM} = {sql_literal(OLD)}",
    )
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{CORRECTION.prefix}{step:03d}",
        test_id=TEST_ID,
        confidence="authoritative",
        label="card exact disclosure correction",
        plan_table="_card_exact_plan",
        out_dir_name=f"{ROOT_NAME}/{W.step_name(step)}",
        post_commit_residual=still_old,
        rehearsal_residual=still_old,
        premise_sql=C.PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(Column("raw_data", "jsonb"),),
        write_invariant=_NAMES_NEITHER,
    )


def lane_of(name: str) -> Lane:
    """`card-exact-s001` -> the lane; `KeyError` for any other name."""
    match = CARD_EXACT_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return exact_lane(int(match.group(1)))


@functools.cache
def exact_readback(lane: Lane) -> str:
    """The read-only verification of one step, before and after its write."""
    stamp = sql_literal(lane.run_stamp)
    journal = f"FROM remediation_change_log l WHERE l.run_stamp = {stamp} AND "
    moved = (
        "CASE WHEN l.column_name = 'raw_data' THEN jsonb_set(l.old_value::jsonb, "
        f"'{{{PROV},ai_system}}', to_jsonb({sql_literal(NEW)}::text)) IS DISTINCT FROM "
        "l.new_value::jsonb ELSE true END"
    )
    was_old = (
        "CASE WHEN l.column_name = 'raw_data' THEN "
        f"(l.old_value::jsonb -> '{PROV}' ->> 'ai_system') IS DISTINCT FROM {sql_literal(OLD)} "
        "ELSE true END"
    )
    return journal_readback(
        lane,
        [
            (
                "curated sites whose card provenance names the Opus and Sonnet disclosure",
                _CURATED + f"{_AI_SYSTEM} = {sql_literal(OLD)}",
            ),
            (
                "curated sites whose card provenance names the Opus-only disclosure of D56",
                _CURATED + f"{_AI_SYSTEM} = {sql_literal(NEW)}",
            ),
            (lane.post_commit_residual.metric, _CURATED + lane.post_commit_residual.predicate),
            (
                "curated version-3 card provenances naming Sonnet that no stage of theirs names",
                _CURATED + f"raw_data -> '{PROV}' ->> 'v' = '3' AND {_AI_SYSTEM} = "
                f"{sql_literal(OLD)} AND (raw_data -> '{PROV}' -> 'models')::text NOT LIKE "
                "'%claude-sonnet%'",
            ),
            (W._RESIDUAL.metric, _CURATED + W._RESIDUAL.predicate),
            (
                "curated rows whose description is not the one its provenance hashes",
                _CURATED + PROVENANCE_HASH_DIFFERS,
            ),
            (
                "journal rows for this run that changed anything but the card provenance's "
                "ai_system",
                journal + moved,
            ),
            (
                "journal rows for this run whose old value did not name the Opus and Sonnet "
                "disclosure",
                journal + was_old,
            ),
        ],
    )


# ------------------------------------------------------------------------------ the list
@dataclass(frozen=True)
class Listed:
    """One site whose version-3 provenance names models its `models` do not, with the proof."""

    site_id: str
    name: str
    run: str
    step: int
    provenance: Mapping[str, Any]

    def row(self) -> dict[str, Any]:
        """The `LIST.jsonl` line."""
        return {
            "site_id": self.site_id,
            "name": self.name,
            "run": self.run,
            "step": self.step,
            "models": dict(self.provenance["models"]),
            "ai_system": self.provenance["ai_system"],
            "derived": derived_of(self.provenance),
        }


def build_list(*, root: Path = W.ROOT) -> list[Listed]:
    """The sites to correct, sorted by site id: pure of the files it reads, deterministic."""
    listed: list[Listed] = []
    for site_id, (step, run, row) in sorted(C.written_rows(root).items()):
        provenance = json.loads(row["new_value"])[PROV]
        if provenance.get("v") != CP.VERSION_3:
            continue
        held, derived = provenance["ai_system"], derived_of(provenance)
        if held == derived:
            continue
        if (held, derived) != (OLD, NEW):
            raise PlanError(
                f"{site_id}: step {step}'s provenance names {held!r} where its models derive "
                f"{derived!r}; this lane corrects {OLD!r} -> {NEW!r} only - never a guess"
            )
        listed.append(
            Listed(
                site_id=site_id, name=row["site_name"], run=run, step=step, provenance=provenance
            )
        )
    return listed


def module_text(site_ids: Sequence[str]) -> str:
    """`card_disclosure_exact_list.py` as `list --write` writes it (stable under `ruff format`)."""
    body = "".join(f'    "{site_id}",\n' for site_id in site_ids)
    ids = f"\n{body}" if body else ""
    return (
        '"""The sites whose card disclosure `card-exact-sNNN` corrects (generated, never '
        "hand-edited).\n\n"
        "`mechanical/card_disclosure_exact.py list --write` derives them from the closed lane-WB "
        "steps'\n"
        "provenance plans and rewrites this file; `list --check` re-derives them and refuses when "
        'they differ.\n"""\n\n'
        f'LIST_SHA256 = "{C.list_sha256(site_ids)}"\n'
        f"SITE_IDS: tuple[str, ...] = ({ids})\n"
    )


def summary(listed: Sequence[Listed]) -> dict[str, Any]:
    return {
        "sites": len(listed),
        "sha256": C.list_sha256(item.site_id for item in listed),
        "by_run": dict(sorted(Counter(i.run for i in listed).items())),
        "steps": -(-len(listed) // MAX_SITES),
    }


# ------------------------------------------------------------------------------ the decision
MODELS_MOVED = "models-moved"
REFUSAL_MEANING = {
    **C.REFUSAL_MEANING,
    C.ALREADY_CORRECTED: "the provenance already names the Opus-only disclosure of D56",
    MODELS_MOVED: "the live provenance's models no longer derive the Opus-only disclosure",
}


def _refused(item: Listed, name: str, reason: str, note: str) -> Verdict:
    return Verdict(
        site_id=item.site_id,
        site_name=name,
        ok=False,
        old_value=None,
        new_value=None,
        rule="",
        reason=reason,
        note=note,
        phase3=False,
        finding_test_id=TEST_ID,
    )


def _evidence(item: Listed) -> tuple[dict[str, Any], ...]:
    models = ", ".join(f"{stage}: {m}" for stage, m in item.provenance["models"].items())
    return (
        {
            "source": f"lane WB run {item.run}, step {item.step}: the version-3 provenance's models",
            "url": f"output/remediation/mechanical_teaser/{W.step_name(item.step)}/prov/PLAN.jsonl",
            "quote": models,
        },
        {
            "source": f"scripts/remediation/phase4/model4.py ai_system_for, {DECISION}",
            "url": None,
            "quote": f"the disclosure {OLD!r} names a model that answered no stage of this card; "
            f"its models derive {NEW!r}",
        },
    )


def classify(item: Listed, live: C.Live | None, journal: Sequence[JournalLink]) -> Verdict:
    """One listed site: its one-key correction, or the reason it is listed and not written."""
    name = item.name if live is None else live.name
    if live is None:
        return _refused(item, name, C.NOT_CURATED, "the export did not return the site")
    if live.raw_data is None:
        return _refused(item, name, C.NO_PROVENANCE, "raw_data is NULL")
    raw = json.loads(live.raw_data)
    if not isinstance(raw, dict):
        return _refused(item, name, C.RAW_DATA_NOT_OBJECT, f"raw_data is a {type(raw).__name__}")
    if reprint(raw) != live.raw_data:
        return _refused(item, name, C.NOT_REPRINTED, "the journal would record another spelling")
    broken = journal_break(list(journal), canonical(live.raw_data))
    if broken is not None:
        return _refused(item, name, broken[0], broken[1])
    held = raw.get(PROV)
    if not isinstance(held, dict):
        return _refused(item, name, C.NO_PROVENANCE, f"raw_data holds no {PROV}")
    if held == {**item.provenance, "ai_system": NEW}:
        return _refused(item, name, C.ALREADY_CORRECTED, "the provenance already names NEW")
    if held != item.provenance:
        return _refused(item, name, C.PROVENANCE_MOVED, f"the provenance is not step {item.step}'s")
    if derived_of(held) != NEW:
        return _refused(item, name, MODELS_MOVED, f"the models derive {derived_of(held)!r}")
    if live.premise != C.premise_of(held):
        raise PlanError(
            f"{item.site_id}: the export's premise {live.premise!r} is not the identity of the "
            "provenance it read - the export is not one snapshot"
        )
    return Verdict(
        site_id=item.site_id,
        site_name=name,
        ok=True,
        old_value=live.raw_data,
        new_value=reprint(W.rewrite_disclosure(raw, CORRECTION)),
        rule=RULE,
        reason="",
        note=f"{PROV}.ai_system {OLD!r} -> {NEW!r}; every other key as it was; every stage of the "
        f"card was answered by Opus ({DECISION})",
        phase3=False,
        finding_test_id=TEST_ID,
        evidence=_evidence(item),
        premise=live.premise,
        column="raw_data",
    )


def build_step(
    step: int,
    listed: Sequence[Listed],
    live: Mapping[str, C.Live],
    journal: Mapping[str, Sequence[JournalLink]],
    *,
    built_at: str,
) -> Plan:
    """The plan of one step over its pinned sites. Pure."""
    sites = step_sites(step)
    by_site = {item.site_id: item for item in listed}
    if sorted(by_site) != sorted(set(LIST.SITE_IDS)) or len(by_site) != len(listed):
        raise PlanError("the derived list is not the pinned list (`list --check`)")
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    for site_id in sites:
        verdict = classify(by_site[site_id], live.get(site_id), journal.get(site_id, ()))
        (changes if verdict.ok else skipped).append(verdict)
    counters = Counter(v.reason for v in skipped)
    return Plan(
        changes=tuple(changes),
        skipped=tuple(skipped),
        built_at=built_at,
        counters={"cells": len(changes), **dict(sorted(counters.items()))},
        lane=exact_lane(step),
    )


# ------------------------------------------------------------------------------ the steps
def accepted(step: int, root: Path = ROOT) -> bool:
    return (root / ACCEPTED_DIR / f"step-{step:03d}.json").exists()


def write_step_md(plan: Plan, step: int, path: Path) -> None:
    lane = plan.lane
    lines = [
        f"# Lane WB exact disclosure correction (D56), step {step:03d} (`{lane.name}`)",
        "",
        f"Planned by `scripts/remediation/mechanical/card_disclosure_exact.py plan`. "
        f"{len(plan.changes)} site(s) written, {len(plan.skipped)} listed. Run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`. One key changes: "
        f"`{PROV}.ai_system`, `{OLD}` -> `{NEW}`.",
        "",
        "## Written",
        "",
        "| site | the card's run and step | its models |",
        "|---|---|---|",
    ]
    for change in plan.changes:
        models = change.evidence[0]
        lines.append(
            f"| {change.site_name} (`{change.site_id}`) | {models['source']} | {models['quote']} |"
        )
    lines += ["", "## Listed, not written", "", "| reason | sites | meaning |", "|---|---|---|"]
    for reason, count in sorted(Counter(v.reason for v in plan.skipped).items()):
        lines.append(f"| `{reason}` | {count} | {REFUSAL_MEANING.get(reason, '')} |")
    for v in plan.skipped:
        lines.append(f"- {v.site_name} (`{v.site_id}`): `{v.reason}` - {v.note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def plan_step(
    step: int,
    *,
    read: Callable[[str], str] = W.read_production,
    root: Path = ROOT,
    listed: Sequence[Listed] | None = None,
) -> dict[str, Any]:
    """Plan one step from the pinned list and a fresh read-only production read."""
    sites = step_sites(step)
    if step > 1 and not accepted(step - 1, root):
        raise PlanError(
            f"step {step - 1} has no acceptance: `card_disclosure_exact.py accept --step {step - 1}`"
        )
    out = root / W.step_name(step)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once (its ROLLBACK.sql may be the undo)")
    derived = build_list() if listed is None else list(listed)
    text = read(
        tagged_export_script([("site", C.site_sql(sites)), ("journal", C.journal_sql(sites))])
    )
    live, journal, _at = C.parse_export(text)
    plan = build_step(step, derived, live, journal, built_at=datetime.now(UTC).isoformat())
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    write_plan_jsonl(plan, out / "PLAN.jsonl")
    if plan.changes:
        write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    write_step_md(plan, step, out / "PLAN.md")
    return {
        "step": step,
        "lane": plan.lane.name,
        "sites": len(sites),
        "cells": len(plan.changes),
        "skipped": dict(sorted(Counter(v.reason for v in plan.skipped).items())),
    }


# ------------------------------------------------------------------------------ the acceptance
def deviations(
    step: int,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, C.Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    lane = exact_lane(step)
    written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
    undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
    if undone:
        found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
    by_site = {j["row_pk"]: j for j in written}
    if len(by_site) != len(written) or set(by_site) != {r["site_id"] for r in rows}:
        found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned")
    for row in rows:
        site_id = row["site_id"]
        site = live.get(site_id)
        entry = by_site.get(site_id)
        if not W.moves_disclosure_key(row["old_value"], row["new_value"], CORRECTION):
            found.append(f"{site_id}: the plan changes more than the one key")
        if site is None or canonical(site.raw_data) != canonical(row["new_value"]):
            found.append(f"{site_id}: does not hold the planned value")
            continue
        if entry is None or (canonical(entry["old_value"]), canonical(entry["new_value"])) != (
            canonical(row["old_value"]),
            canonical(row["new_value"]),
        ):
            found.append(f"{site_id}: the journal row is not the plan's")
        elif not W.moves_disclosure_key(entry["old_value"], entry["new_value"], CORRECTION):
            found.append(f"{site_id}: the journal row changed more than the one key")
        provenance = CP.card_provenance_of(site.raw_data)
        if provenance is None or provenance["ai_system"] != NEW:
            found.append(f"{site_id}: the provenance does not name the corrected disclosure")
        elif derived_of(provenance) != NEW:
            found.append(
                f"{site_id}: the provenance's models do not derive the disclosure it names"
            )
        elif not CP.describes(provenance, site.card):
            found.append(f"{site_id}: the provenance does not hash the live card")
    return found


def accept_step(
    step: int, *, read: Callable[[str], str] = W.read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once."""
    lane = exact_lane(step)
    rows = read_jsonl(root / W.step_name(step) / "PLAN.jsonl")
    sites = [row["site_id"] for row in rows]
    listed = ", ".join(sql_literal(stamp) for stamp in (lane.run_stamp, lane.rollback_run_stamp))
    text = read(
        tagged_export_script(
            [
                ("site", C.site_sql(sites)),
                ("journal", C.ACCEPT_JOURNAL_SQL.format(stamps=listed)),
            ]
        )
    )
    parsed, exported_at = parse_tagged_export(text, ("site", "journal"))
    live = {str(r["site_id"]): C._live(r) for r in parsed["site"]}
    found = deviations(step, rows, live, parsed["journal"])
    path = root / ACCEPTED_DIR / f"step-{step:03d}.json"
    if not found and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "step": step,
                    "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "read_at": exported_at,
                    "sites": len(sites),
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _list(args: argparse.Namespace) -> int:
    listed = build_list(root=args.teaser_root)
    _print(summary(listed))
    ids = [item.site_id for item in listed]
    if args.check:
        if ids != list(LIST.SITE_IDS) or C.list_sha256(ids) != LIST.LIST_SHA256:
            print(
                f"REFUSED: the derived list ({len(ids)} sites, {C.list_sha256(ids)}) is not the "
                f"pinned one ({len(LIST.SITE_IDS)} sites, {LIST.LIST_SHA256})",
                file=sys.stderr,
            )
            return 1
        print(f"the pinned list holds: {len(ids)} sites, sha256 {LIST.LIST_SHA256}")
    if args.write:
        args.root.mkdir(parents=True, exist_ok=True)
        (args.root / "LIST.jsonl").write_text(
            "".join(json.dumps(item.row(), ensure_ascii=False) + "\n" for item in listed),
            encoding="utf-8",
            newline="\n",
        )
        LIST_MODULE.write_text(module_text(ids), encoding="utf-8", newline="\n")
        print(f"wrote {args.root / 'LIST.jsonl'} and {LIST_MODULE}")
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "list":
        return _list(args)
    if args.command == "plan":
        _print(plan_step(args.step, root=args.root))
        return 0
    code, found = accept_step(args.step, root=args.root)
    for line in found:
        print(f"  {line}")
    print(f"RESULT: {len(found)} deviation(s)")
    return code


def main(argv: list[str] | None = None) -> int:
    """`accept` prints `ACCEPT_EXIT=`, `plan` `WRITE_EXIT=`, `list` `LIST_EXIT=`; all read-only on
    production."""
    parser = argparse.ArgumentParser(
        prog="card_disclosure_exact", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="derive the sites to correct (offline)")
    listing.add_argument(
        "--write", action="store_true", help="write LIST.jsonl and the pinned module"
    )
    listing.add_argument("--check", action="store_true", help="refuse unless the pinned list holds")
    listing.add_argument("--teaser-root", type=Path, default=W.ROOT)
    plan = sub.add_parser("plan", help="plan one step (read-only on production)")
    plan.add_argument("--step", required=True, type=int)
    accept = sub.add_parser("accept", help="re-read one written step; record it at 0 deviations")
    accept.add_argument("--step", required=True, type=int)
    args = parser.parse_args(argv)
    tag = {"list": "LIST", "plan": "WRITE", "accept": "ACCEPT"}[args.command]

    def body() -> int:
        try:
            return _run(args)
        except PlanError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1

    return W4.exit_line(tag, body)


if __name__ == "__main__":
    raise SystemExit(main())
