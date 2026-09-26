"""Lane WB's write: a run's teaser outcomes as journalled mechanical lanes, in steps of 100 sites.

The cards are decided by `scripts/remediation/teaser/run.py` (writer, independent checker, up to two
rewrites; `OUTCOMES.jsonl`). This module plans their write and nothing else; `mechanical/apply.py`
renders, rehearses, probes, applies and reads back every statement, as for every other mechanical
lane. Contract and runbook: `docs/procedures/CARD_DESCRIPTIONS.md`.

## Why a mechanical lane and not `write_gate4.py --group P5`

The P5 writer is built around the Phase-4 plan: it writes the card of a site whose `PLAN4.jsonl`
assembly carries one, pins the card to `_description_provenance.card` (an extractive card: sentence
items and drops), refuses every site outside `SCOPE4`, and its code lives in `phase4/`, whose
package hash the Phase-4 mass runs check before every batch (lane WA runs there). A teaser card has
no items, comes from a lane-WB run, covers every curated site, and needs a provenance of its own
(`pipeline.utils.card_provenance`). Generalising P5 would change a writer mid-flight; a mechanical
lane already offers the whole write discipline - plan-pinned statements, the rollback rendered
before the apply, rehearsal, guard probes, conditional writes through `apply_remediation_change()`,
the read-back - and needs only the one extension this lane brings: a column that may be **cleared**
(`lane.Column.clears`), for the card of a site that gets none.

## Two lanes per step

`card_stats.card_description` and `unified_sites.raw_data` are two tables; a lane writes one. Each
step of at most 100 sites is therefore two lanes, written in this order:

1. **`teaser-prov-sNNN`** (`unified_sites.raw_data`): the site's `_card_provenance` (the checked
   card's hash, the description's hash, the checker's verdict and claims), and
   `_description_provenance.card` set to `null` where a Phase-5 extractive card key is left - the
   card it names is being replaced, and acceptance D4 would otherwise fail. For a cleared card the
   row removes a teaser provenance and nulls that key, and is planned only when there is one to
   remove. Premise (guard 5): the sha256 of the description, as the outcome's `desc_sha256` names
   it - a description changed after the check refuses the write.
2. **`teaser-card-sNNN`** (`card_stats.card_description`): the new card, or `NULL`. Premise: the
   teaser provenance's card hash and description hash and the description's live hash
   (`text|desc|desc`), so the card is written only onto the provenance step 1 wrote and while the
   description is the one checked; a clear's premise is `||<desc>`, no teaser provenance left.

Between the two applies the old card is live and marked by nothing (its Phase-5 key is nulled, and
the teaser provenance hashes the new card): a window of minutes in which the site claims less, never
more. Undo runs the other way: the card lane's `ROLLBACK.sql` first, then the provenance lane's.

## Files and gates

`output/remediation/mechanical_teaser/`: `STEPS.jsonl` (every planned step, its run and sites),
`sNNN/PLAN.md`, `sNNN/SKIPPED.jsonl`, `sNNN/export.jsonl` (the read-only production read the step
was planned from), `sNNN/prov/` and `sNNN/card/` (each lane's `PLAN.jsonl`, `ROLLBACK.sql`, and after
`apply.py --emit` its `APPLY.sql`), `ACCEPTED/step-NNN.json` and `REVERTED/step-NNN.json`. A step is
**closed** by either record. `plan --step N` refuses while step N-1 is not closed; `accept --step N`
re-reads production (read-only) and records the acceptance only at 0 deviations, and never for a
step closed as undone. A step that was undone (its `ROLLBACK.sql` files run) - after its acceptance
or before it - or planned and never applied, is closed by `close-reverted --step N` on production's
proof that none of its writes stands (every planned cell holds its value from before the step, every
write it had is reversed by its inverse). Its `REVERTED` record stands beside an acceptance the step
had (which it copies as `superseded_acceptance`), and a later step plans its sites again.
`card-file` expects the cards of an undone step at their values from before it.

    M=scripts/remediation/mechanical
    $M/teaser.py plan --run <run> --step N      (read-only; the next <=100 sites of the run;
                                                 <run> is the run's directory or its bare name)
    $M/apply.py --lane teaser-prov-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane teaser-card-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane teaser-card-sNNN --rehearse-rollback ; then teaser-prov-sNNN
    $M/teaser.py accept --step N                (read-only; ACCEPT_EXIT=0 at 0 deviations)
    $M/teaser.py close-reverted --step N        (read-only; after an undo: its sites are planned again)
    $M/teaser.py card-file --steps A-B          (read-only; renders the card file from production)
    $M/teaser.py stale                          (read-only; teaser cards whose description moved)
"""

from __future__ import annotations

import argparse
import functools
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

from phase3 import write_stage as WS  # noqa: E402 - the psql seam card_json reads through
from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from phase4 import card_json as CJ  # noqa: E402 - the card file's one renderer
from phase4 import write4 as W4  # noqa: E402 - the exit line
from prod_write import send  # noqa: E402

from mechanical.citations import canonical, premise_of, reprint  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_STATS,
    LOCK_TIMEOUT,
    ORPHAN_CITATIONS,
    PROVENANCE_HASH_DIFFERS,
    STATEMENT_TIMEOUT,
    TEASER_LANE,
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

ROOT_NAME = "mechanical_teaser"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
#: `teaser/run.py`'s RUNS, ACCEPTED and CLEARED: the outcomes this module reads are that CLI's
#: (a test pins the spellings; this module does not import the `teaser` package, whose name its own
#: file shares when it runs as a script).
RUNS = REPO / "output" / "remediation" / "teaser" / "runs"
MAX_SITES = 100
PROV, CARD = "prov", "card"
DESCRIPTION_PROVENANCE_KEY = "_description_provenance"
RETIRED = "retired"
ACCEPTED, CLEARED = "accepted", "cleared"
#: The two closing records of a step (directories under the root): written as planned (`accept`),
#: or undone (`close-reverted`) - after an acceptance, beside it, or instead of one.
ACCEPTED_DIR, REVERTED_DIR = "ACCEPTED", "REVERTED"

#: Guard 5 of the provenance lane: the description's sha256, as Postgres computes it - the
#: orphan-citations lane's premise, the same text (`citations.premise_of` is its Python half).
PROV_PREMISE_SQL = ORPHAN_CITATIONS.premise_sql
#: Guard 5 of the card lane: the teaser provenance's card and description hashes, and the live
#: description's hash.
CARD_PREMISE_SQL = (
    "coalesce(u.raw_data -> '_card_provenance' ->> 'text_sha256', '') || '|' || "
    "coalesce(u.raw_data -> '_card_provenance' ->> 'desc_sha256', '') || '|' || "
    f"{PROV_PREMISE_SQL}"
)
#: The teaser provenances that do not describe their site's live card, or whose description moved.
_TEASER_NOT_LIVE = (
    "raw_data ? '_card_provenance' AND NOT EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = "
    "unified_sites.id AND encode(sha256(convert_to(cs.card_description, 'UTF8')), 'hex') = "
    "unified_sites.raw_data -> '_card_provenance' ->> 'text_sha256')"
)
_TEASER_STALE = (
    "raw_data ? '_card_provenance' AND encode(sha256(convert_to(coalesce(description, ''), "
    "'UTF8')), 'hex') IS DISTINCT FROM raw_data -> '_card_provenance' ->> 'desc_sha256'"
)
_RESIDUAL = Residual(
    "curated sites whose teaser provenance does not hash their live card", _TEASER_NOT_LIVE
)
#: D4's card half: a Phase-5 card key that does not hash the live card.
_P5_KEY_NOT_LIVE = (
    "jsonb_typeof(raw_data -> '_description_provenance' -> 'card') = 'object' AND NOT EXISTS "
    "(SELECT 1 FROM card_stats cs WHERE cs.site_id = unified_sites.id AND "
    "encode(sha256(convert_to(cs.card_description, 'UTF8')), 'hex') = "
    "unified_sites.raw_data -> '_description_provenance' -> 'card' ->> 'text_sha256')"
)
_CURATED = "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "


# ------------------------------------------------------------------------------ the lanes
def step_name(step: int) -> str:
    if not 1 <= step <= 999:
        raise ValueError(f"step {step} is not 1-999")
    return f"s{step:03d}"


def teaser_lane(kind: str, step: int) -> Lane:
    """The lane of one kind (`prov` or `card`) of one step: its own stamp, key prefix and directory."""
    name = f"teaser-{kind}-{step_name(step)}"
    common: dict[str, Any] = {
        "name": name,
        "key_prefix": name,
        "run_stamp": f"wb-{name}",
        "confidence": "opus-checked",
        "out_dir_name": f"{ROOT_NAME}/{step_name(step)}/{kind}",
        "post_commit_residual": _RESIDUAL,
        "rehearsal_residual": _RESIDUAL,
        "lock_timeout": LOCK_TIMEOUT,
        "statement_timeout": STATEMENT_TIMEOUT,
    }
    if kind == PROV:
        return Lane(
            **common,
            test_id="WB/card-provenance",
            label="teaser card provenance",
            plan_table="_teaser_prov_plan",
            premise_sql=PROV_PREMISE_SQL,
            target=UNIFIED_SITES,
            cells=(Column("raw_data", "jsonb", fills_null=True),),
        )
    if kind == CARD:
        return Lane(
            **common,
            test_id="WB/teaser-card",
            label="teaser card",
            plan_table="_teaser_card_plan",
            premise_sql=CARD_PREMISE_SQL,
            target=CARD_STATS,
            cells=(
                Column(
                    "card_description",
                    "character varying",
                    max_chars=CJ.W4.CARD_MAX_CHARS,
                    fills_null=True,
                    clears=True,
                ),
            ),
        )
    raise ValueError(f"{kind!r} is not a lane-WB lane kind ({PROV}, {CARD})")


def lane_of(name: str) -> Lane:
    """`teaser-prov-s001` / `teaser-card-s001` -> the lane; `KeyError` for any other name."""
    match = TEASER_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return teaser_lane(match.group(1), int(match.group(2)))


@functools.cache
def teaser_readback(lane: Lane) -> str:
    """The read-only verification of one lane-WB lane, before and after its write."""
    return journal_readback(
        lane,
        [
            (
                "curated sites carrying a teaser provenance",
                _CURATED + "raw_data ? '_card_provenance'",
            ),
            (_RESIDUAL.metric, _CURATED + _TEASER_NOT_LIVE),
            (
                "curated sites whose teaser card is stale (description moved)",
                _CURATED + _TEASER_STALE,
            ),
            (
                "curated sites whose Phase-5 card key does not hash the live card",
                _CURATED + _P5_KEY_NOT_LIVE,
            ),
            (
                "curated rows whose description is not the one its provenance hashes",
                _CURATED + PROVENANCE_HASH_DIFFERS,
            ),
            (
                "curated sites with a card",
                "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id WHERE "
                "u.source_id = 'ancient_nerds' AND cs.card_description IS NOT NULL",
            ),
        ],
    )


# ------------------------------------------------------------------------------ the read
def site_sql(site_ids: Iterable[str]) -> str:
    return (
        "SELECT u.id::text AS site_id, u.name, u.description, u.scope_status, "
        "u.raw_data::text AS raw_data, (c.site_id IS NOT NULL) AS has_card_row, "
        "c.card_description AS card FROM unified_sites u LEFT JOIN card_stats c ON "
        f"c.site_id = u.id WHERE u.source_id = 'ancient_nerds' AND u.id::text IN "
        f"({sql_ids(site_ids)}) ORDER BY u.id"
    )


def journal_sql(site_ids: Iterable[str]) -> str:
    """Every journal row of the two cells this lane writes, for these sites."""
    return (
        "SELECT l.id, l.row_pk, l.table_name, l.column_name, l.run_stamp, "
        "coalesce(l.test_id, '') AS test_id, l.old_value, l.new_value FROM remediation_change_log l "
        "WHERE ((l.table_name = 'unified_sites' AND l.column_name = 'raw_data') OR "
        "(l.table_name = 'card_stats' AND l.column_name = 'card_description')) "
        f"AND l.row_pk IN ({sql_ids(site_ids)}) ORDER BY l.id"
    )


def export_script(site_ids: Sequence[str]) -> str:
    return tagged_export_script([("site", site_sql(site_ids)), ("journal", journal_sql(site_ids))])


def read_production(script: str) -> str:
    """Send a read-only export to production and return its output as it came."""
    proc = send(script, rows=True, timeout=900)
    if proc.returncode != 0:
        raise PlanError(f"the read-only export failed (psql exit {proc.returncode}): {proc.stderr}")
    return proc.stdout


@dataclass(frozen=True)
class Live:
    """One site as the step's export read it."""

    site_id: str
    name: str
    description: str | None
    scope_status: str | None
    raw_data: str | None
    has_card_row: bool
    card: str | None


def _live(r: Mapping[str, Any]) -> Live:
    return Live(
        site_id=str(r["site_id"]),
        name=str(r["name"]),
        description=r["description"],
        scope_status=r["scope_status"],
        raw_data=r["raw_data"],
        has_card_row=bool(r["has_card_row"]),
        card=r["card"],
    )


def parse_export(text: str) -> tuple[dict[str, Live], dict[tuple[str, str], list[JournalLink]]]:
    rows, _at = parse_tagged_export(text, ("site", "journal"))
    live = {str(r["site_id"]): _live(r) for r in rows["site"]}
    journal: dict[tuple[str, str], list[JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            JournalLink(int(r["id"]), r["run_stamp"], r["test_id"], r["old_value"], r["new_value"])
        )
    return live, journal


# ------------------------------------------------------------------------------ the decision
STALE_DESCRIPTION = "stale-description"
SITE_RETIRED = "retired"
NO_CARD_ROW = "no-card-row"
NOT_CURATED = "not-a-curated-site"
RAW_DATA_NOT_OBJECT = "raw-data-not-an-object"
NOT_REPRINTED = "raw-data-not-reprinted"
NOTHING_TO_CHANGE = "nothing-to-change"
REFUSAL_MEANING = {
    STALE_DESCRIPTION: "the description changed after the card was checked: run lane WB again",
    SITE_RETIRED: "the site was retired after the run: its card is never drawn",
    NO_CARD_ROW: "no card_stats row to write the card into",
    NOT_CURATED: "the site is no longer a curated site",
    RAW_DATA_NOT_OBJECT: "raw_data is JSON but not an object",
    NOT_REPRINTED: "raw_data is not printed the way this planner prints JSON",
    "journal-chain-broken": "a cell's journal is not continuous",
    "journal-disagrees": "a cell's journal does not end at the live value",
    NOTHING_TO_CHANGE: "the site already holds exactly this card and provenance",
}


def new_raw_data(
    raw: Mapping[str, Any] | None, outcome: Mapping[str, Any]
) -> dict[str, Any] | None:
    """The raw_data a step writes: the teaser provenance set (accepted) or removed (cleared), and a
    Phase-5 card key of the description provenance set to null; every other key as it was. A NULL
    raw_data stays NULL unless a provenance is written into it."""
    if raw is None and outcome["status"] != ACCEPTED:
        return None
    out = {key: value for key, value in (raw or {}).items() if key != CP.CARD_PROVENANCE_KEY}
    described = out.get(DESCRIPTION_PROVENANCE_KEY)
    if isinstance(described, dict) and described.get("card") is not None:
        out[DESCRIPTION_PROVENANCE_KEY] = {**described, "card": None}
    if outcome["status"] == ACCEPTED:
        out[CP.CARD_PROVENANCE_KEY] = CP.validate(outcome["provenance"])
    return out


def card_premise(raw: Mapping[str, Any] | None, description: str | None) -> str:
    """`CARD_PREMISE_SQL` in Python, over the raw_data the provenance lane leaves behind."""
    teaser = None if raw is None else raw.get(CP.CARD_PROVENANCE_KEY)
    text, desc = ("", "") if teaser is None else (teaser["text_sha256"], teaser["desc_sha256"])
    return f"{text}|{desc}|{premise_of(description)}"


def _refused(site_id: str, name: str, reason: str, note: str) -> Verdict:
    return Verdict(
        site_id=site_id,
        site_name=name,
        ok=False,
        old_value=None,
        new_value=None,
        rule="",
        reason=reason,
        note=note,
        phase3=False,
        finding_test_id="WB/teaser-card",
    )


def _evidence(outcome: Mapping[str, Any], run: str) -> tuple[dict[str, Any], ...]:
    source = f"output/remediation/teaser/runs/{run}/OUTCOMES.jsonl"
    if outcome["status"] == ACCEPTED:
        check = outcome["provenance"]["check"]
        claims = "; ".join(f"{c['claim']} [{', '.join(c['support'])}]" for c in check["claims"])
        return (
            {
                "source": f"lane WB run {run}: writer {outcome['writer']['answered_by']}",
                "url": source,
                "quote": outcome["card"],
            },
            {
                "source": f"lane WB run {run}: checker {check['by']} ({check['stage']}), PASS",
                "url": source,
                "quote": claims,
            },
        )
    reasons = "; ".join(r for f in outcome["findings"] for r in f["reasons"]) or outcome["reason"]
    return ({"source": f"lane WB run {run}: {outcome['reason']}", "url": source, "quote": reasons},)


def classify(
    outcome: Mapping[str, Any],
    live: Live | None,
    journal: Mapping[tuple[str, str], Sequence[JournalLink]],
    run: str,
) -> tuple[Verdict | None, Verdict | None] | Verdict:
    """One site's two cells - (provenance, card), either `None` when it needs no change - or the
    refusal that lists it."""
    site_id, name = outcome["site_id"], outcome["name"]
    if live is None:
        return _refused(site_id, name, NOT_CURATED, "the export did not return the site")
    if live.scope_status == RETIRED:
        return _refused(site_id, name, SITE_RETIRED, "retired since the run")
    if not live.has_card_row:
        return _refused(site_id, name, NO_CARD_ROW, "no card_stats row")
    if premise_of(live.description) != outcome["desc_sha256"]:
        return _refused(
            site_id, name, STALE_DESCRIPTION, "the live description is not the one checked"
        )
    raw = None if live.raw_data is None else json.loads(live.raw_data)
    if raw is not None and not isinstance(raw, dict):
        return _refused(site_id, name, RAW_DATA_NOT_OBJECT, f"raw_data is a {type(raw).__name__}")
    if live.raw_data is not None and reprint(raw) != live.raw_data:
        return _refused(site_id, name, NOT_REPRINTED, "the journal would record another spelling")
    for column, value in (("raw_data", canonical(live.raw_data)), ("card_description", live.card)):
        links = journal.get((site_id, column), ())
        if column == "raw_data":
            links = [
                JournalLink(
                    link.id,
                    link.run_stamp,
                    link.test_id,
                    canonical(link.old_value),
                    canonical(link.new_value),
                )
                for link in links
            ]
        broken = journal_break(list(links), value)
        if broken is not None:
            return _refused(site_id, name, broken[0], f"{column}: {broken[1]}")
    new_raw = new_raw_data(raw, outcome)
    new_raw_text = None if new_raw is None else reprint(new_raw)
    rule = "teaser-card" if outcome["status"] == ACCEPTED else f"card-clear-{outcome['reason']}"
    evidence = _evidence(outcome, run)
    common = {
        "site_id": site_id,
        "site_name": name,
        "ok": True,
        "reason": "",
        "phase3": False,
        "evidence": evidence,
    }
    prov = None
    if canonical(new_raw_text) != canonical(live.raw_data):
        prov = Verdict(
            **common,
            old_value=live.raw_data,
            new_value=new_raw_text,
            rule=rule,
            note="raw_data._card_provenance "
            + ("set" if outcome["status"] == ACCEPTED else "removed")
            + "; a Phase-5 card key of _description_provenance nulled; every other key as it was",
            finding_test_id="WB/card-provenance",
            premise=premise_of(live.description),
            column="raw_data",
        )
    card = None
    if outcome["card"] != live.card:
        card = Verdict(
            **common,
            old_value=live.card,
            new_value=outcome["card"],
            rule=rule,
            note=(
                f"teaser card, {len(outcome['card'])} characters, checked PASS"
                if outcome["status"] == ACCEPTED
                else f"card cleared ({outcome['reason']})"
            ),
            finding_test_id="WB/teaser-card",
            premise=card_premise(new_raw, live.description),
            column="card_description",
        )
    if prov is None and card is None:
        return _refused(site_id, name, NOTHING_TO_CHANGE, "card and provenance already hold")
    return prov, card


@dataclass(frozen=True)
class StepPlan:
    step: int
    run: str
    sites: tuple[str, ...]
    prov: Plan
    card: Plan
    skipped: tuple[Verdict, ...]


def build_step(
    step: int,
    run: str,
    outcomes: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Mapping[tuple[str, str], Sequence[JournalLink]],
    *,
    built_at: str,
) -> StepPlan:
    """The two lane plans of one step over `outcomes` (at most 100 sites). Pure."""
    if len(outcomes) > MAX_SITES:
        raise PlanError(f"a step writes at most {MAX_SITES} sites, not {len(outcomes)}")
    prov: list[Verdict] = []
    card: list[Verdict] = []
    skipped: list[Verdict] = []
    for outcome in sorted(outcomes, key=lambda o: o["site_id"]):
        decided = classify(outcome, live.get(outcome["site_id"]), journal, run)
        if isinstance(decided, Verdict):
            skipped.append(decided)
            continue
        if decided[0] is not None:
            prov.append(decided[0])
        if decided[1] is not None:
            card.append(decided[1])
    counters = Counter(v.reason for v in skipped)

    def plan(kind: str, changes: list[Verdict]) -> Plan:
        return Plan(
            changes=tuple(changes),
            skipped=tuple(skipped) if kind == CARD else (),
            built_at=built_at,
            counters={"cells": len(changes), **dict(sorted(counters.items()))},
            lane=teaser_lane(kind, step),
        )

    return StepPlan(
        step=step,
        run=run,
        sites=tuple(sorted({v.site_id for v in [*prov, *card]})),
        prov=plan(PROV, prov),
        card=plan(CARD, card),
        skipped=tuple(skipped),
    )


# ------------------------------------------------------------------------------ the steps
def read_steps(root: Path = ROOT) -> list[dict[str, Any]]:
    path = root / "STEPS.jsonl"
    if not path.exists():
        return []
    return read_jsonl(path)


def _closing(kind: str, step: int, root: Path) -> Path:
    """The path of a step's closing record of one kind (`ACCEPTED_DIR` or `REVERTED_DIR`)."""
    return root / kind / f"step-{step:03d}.json"


def accepted(step: int, root: Path = ROOT) -> bool:
    """Whether the step was accepted as written (`accept`) - it may have been undone since."""
    return _closing(ACCEPTED_DIR, step, root).exists()


def reverted(step: int, root: Path = ROOT) -> bool:
    """Whether the step was closed as undone: none of its writes stands, its sites are planned
    again."""
    return _closing(REVERTED_DIR, step, root).exists()


def closed(step: int, root: Path = ROOT) -> bool:
    """Whether the step is settled - accepted as written, or closed as undone - so the next step
    may be planned and the card file may name it."""
    return accepted(step, root) or reverted(step, root)


def _record_closing(kind: str, step: int, root: Path, record: Mapping[str, Any]) -> None:
    """A step's closing record of one kind; each kind is written once."""
    path = _closing(kind, step, root)
    if path.exists():
        raise PlanError(f"step {step} has its {kind} record already ({path})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"step": step, **record}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_name(value: str) -> str:
    """The run `plan --run` names: its bare name, or its directory as `teaser/run.py --run` takes
    it (relative to the repository or absolute), which must lie directly under `RUNS`."""
    path = Path(value)
    if len(path.parts) == 1:
        return value
    resolved = (path if path.is_absolute() else REPO / path).resolve()
    if resolved.parent != RUNS.resolve():
        raise PlanError(f"{value} is not a run directory (a run lies directly under {RUNS})")
    return resolved.name


def next_outcomes(
    run: str,
    outcomes: Sequence[Mapping[str, Any]],
    steps: Sequence[Mapping[str, Any]],
    undone: frozenset[int] = frozenset(),
) -> list[Mapping[str, Any]]:
    """The run's outcomes no earlier step planned - a step closed as undone (`undone`) plans
    nothing - in site order, at most 100."""
    done = {
        site
        for step in steps
        if step["run"] == run and step["step"] not in undone
        for site in step["outcomes"]
    }
    return [o for o in sorted(outcomes, key=lambda o: o["site_id"]) if o["site_id"] not in done][
        :MAX_SITES
    ]


def write_step_md(plan: StepPlan, path: Path) -> None:
    lines = [
        f"# Lane WB step {plan.step:03d} (run `{plan.run}`)",
        "",
        f"Planned by `scripts/remediation/mechanical/teaser.py plan`. {len(plan.sites)} site(s): "
        f"{len(plan.prov.changes)} provenance cell(s) (`{plan.prov.lane.name}`, stamp "
        f"`{plan.prov.lane.run_stamp}`), {len(plan.card.changes)} card cell(s) "
        f"(`{plan.card.lane.name}`, stamp `{plan.card.lane.run_stamp}`); {len(plan.skipped)} "
        "listed.",
        "",
        "Apply the provenance lane first, then the card lane; undo the card lane first.",
        "",
        "## Cards",
        "",
    ]
    for change in plan.card.changes:
        lines.append(f"- {change.site_name} (`{change.site_id[:8]}`): {change.new_value!r}")
    lines += ["", "## Listed, not written", "", "| reason | sites | meaning |", "|---|---|---|"]
    for reason, count in sorted(Counter(v.reason for v in plan.skipped).items()):
        lines.append(f"| `{reason}` | {count} | {REFUSAL_MEANING.get(reason, '')} |")
    for v in plan.skipped:
        lines.append(f"- {v.site_name} (`{v.site_id}`): `{v.reason}` - {v.note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _read_outcomes(run: str) -> list[dict[str, Any]]:
    path = RUNS / run / "OUTCOMES.jsonl"
    if not path.exists():
        raise PlanError(f"{path} does not exist - run `teaser/run.py outcomes` first")
    return read_jsonl(path)


def plan_step(
    run: str,
    step: int,
    *,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
    outcomes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan step `step` from the run's next outcomes and a fresh read-only production read."""
    steps = read_steps(root)
    expected = max((s["step"] for s in steps), default=0) + 1
    if step != expected:
        raise PlanError(f"the next step is {expected}, not {step}")
    if step > 1 and not closed(step - 1, root):
        raise PlanError(
            f"step {step - 1} has no acceptance: `teaser.py accept --step {step - 1}` (or "
            "`close-reverted` after an undo)"
        )
    undone = frozenset(s["step"] for s in steps if reverted(s["step"], root))
    todo = next_outcomes(run, _read_outcomes(run) if outcomes is None else outcomes, steps, undone)
    if not todo:
        raise PlanError(f"run {run}: every outcome is planned")
    out = root / step_name(step)
    if out.exists():
        raise PlanError(f"{out} exists but STEPS.jsonl has no step {step}: settle it by hand")
    text = read(export_script([o["site_id"] for o in todo]))
    live, journal = parse_export(text)
    plan = build_step(step, run, todo, live, journal, built_at=datetime.now(UTC).isoformat())
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    lanes: dict[str, Any] = {}
    for kind, lane_plan in ((PROV, plan.prov), (CARD, plan.card)):
        lane_out = out / kind
        lane_out.mkdir()
        write_plan_jsonl(lane_plan, lane_out / "PLAN.jsonl")
        if lane_plan.changes:
            write_rollback_sql(
                lane_plan, lane_out / "ROLLBACK.sql", plan_path=lane_out / "PLAN.jsonl"
            )
        lanes[kind] = {"lane": lane_plan.lane.name, "cells": len(lane_plan.changes)}
    write_skipped_jsonl(plan.card, out / "SKIPPED.jsonl")
    write_step_md(plan, out / "PLAN.md")
    record = {
        "step": step,
        "run": run,
        "outcomes": [o["site_id"] for o in todo],
        "sites": list(plan.sites),
        "planned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **lanes,
        "skipped": dict(sorted(Counter(v.reason for v in plan.skipped).items())),
    }
    root.mkdir(parents=True, exist_ok=True)
    with (root / "STEPS.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


# ------------------------------------------------------------------------------ the acceptance
ACCEPT_JOURNAL_SQL = (
    "SELECT l.row_pk, l.column_name, l.run_stamp, l.old_value, l.new_value "
    "FROM remediation_change_log l WHERE l.run_stamp IN ({stamps}) ORDER BY l.id"
)


def deviations(
    step: Mapping[str, Any],
    prov_rows: Sequence[Mapping[str, Any]],
    card_rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
    outcomes: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    for kind, rows in ((PROV, prov_rows), (CARD, card_rows)):
        lane = teaser_lane(kind, step["step"])
        written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
        undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
        if undone:
            found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
        by_site = {j["row_pk"]: j for j in written}
        if len(by_site) != len(written) or set(by_site) != {r["site_id"] for r in rows}:
            found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned")
        for row in rows:
            site = live[row["site_id"]]
            entry = by_site.get(row["site_id"])
            if kind == PROV:
                held = canonical(site.raw_data) == canonical(row["new_value"])
                same = entry is not None and canonical(entry["new_value"]) == canonical(
                    row["new_value"]
                )
            else:
                held = site.card == row["new_value"]
                same = entry is not None and entry["new_value"] == row["new_value"]
            if not held:
                found.append(f"{lane.name} {row['site_id']}: does not hold the planned value")
            if not same:
                found.append(f"{lane.name} {row['site_id']}: the journal row is not the plan's")
    for site_id in step["sites"]:
        site, outcome = live[site_id], outcomes[site_id]
        raw = {} if site.raw_data is None else json.loads(site.raw_data)
        teaser = CP.card_provenance_of(raw)
        described = raw.get(DESCRIPTION_PROVENANCE_KEY)
        if isinstance(described, dict) and described.get("card") is not None:
            found.append(f"{site_id}: _description_provenance still names a card")
        if outcome["status"] == ACCEPTED:
            if teaser is None or not CP.describes(teaser, site.card):
                found.append(f"{site_id}: no teaser provenance hashes the live card")
            elif CP.stale(teaser, site.description):
                found.append(f"{site_id}: the teaser provenance is stale")
            if site.card != outcome["card"]:
                found.append(f"{site_id}: the live card is not the accepted one")
        else:
            if site.card is not None or teaser is not None:
                found.append(f"{site_id}: a cleared card or its provenance is still there")
    return found


def _step_read(
    step: int, read: Callable[[str], str], root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Live], list, str]:
    """A planned step's record and plans, and one read-only production read of its sites and of
    the journal rows of its four stamps (the two lanes' writes and reversals)."""
    record = next((s for s in read_steps(root) if s["step"] == step), None)
    if record is None:
        raise PlanError(f"step {step} was never planned")
    out = root / step_name(step)
    prov_rows = read_jsonl(out / PROV / "PLAN.jsonl")
    card_rows = read_jsonl(out / CARD / "PLAN.jsonl")
    listed = ", ".join(
        sql_literal(stamp)
        for kind in (PROV, CARD)
        for stamp in (teaser_lane(kind, step).run_stamp, teaser_lane(kind, step).rollback_run_stamp)
    )
    text = read(
        tagged_export_script(
            [
                ("site", site_sql(record["sites"])),
                ("journal", ACCEPT_JOURNAL_SQL.format(stamps=listed)),
            ]
        )
    )
    rows, exported_at = parse_tagged_export(text, ("site", "journal"))
    live = {str(r["site_id"]): _live(r) for r in rows["site"]}
    return record, prov_rows, card_rows, live, rows["journal"], exported_at


def accept_step(
    step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once:
    a closed step is only re-read, and a step closed as undone is never accepted."""
    record, prov_rows, card_rows, live, journal, exported_at = _step_read(step, read, root)
    outcomes = {o["site_id"]: o for o in _read_outcomes(record["run"])}
    found = deviations(record, prov_rows, card_rows, live, journal, outcomes)
    if reverted(step, root):
        found.insert(0, f"step {step} is closed as undone ({REVERTED_DIR}): it is never accepted")
    if not found and not closed(step, root):
        _record_closing(
            ACCEPTED_DIR,
            step,
            root,
            {
                "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "read_at": exported_at,
                "sites": len(record["sites"]),
                "prov_cells": len(prov_rows),
                "card_cells": len(card_rows),
            },
        )
    return (0 if not found else 1), found


def standing_writes(
    step: int,
    prov_rows: Sequence[Mapping[str, Any]],
    card_rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> tuple[list[str], int]:
    """Why a step's writes are not all undone - empty when every planned cell holds its value from
    before the step and every write of it has exactly one reversal, its inverse - and how many
    cells were written and reversed. Pure."""
    found: list[str] = []
    reversed_cells = 0
    for kind, rows in ((PROV, prov_rows), (CARD, card_rows)):
        lane = teaser_lane(kind, step)
        same = canonical if kind == PROV else (lambda value: value)
        for row in rows:
            site_id = row["site_id"]
            site = live[site_id]
            held = site.raw_data if kind == PROV else site.card
            writes = [
                j for j in journal if j["row_pk"] == site_id and j["run_stamp"] == lane.run_stamp
            ]
            undos = [
                j
                for j in journal
                if j["row_pk"] == site_id and j["run_stamp"] == lane.rollback_run_stamp
            ]
            if same(held) != same(row["old_value"]):
                found.append(f"{lane.name} {site_id}: does not hold its value from before the step")
            if len(writes) > 1 or len(undos) != len(writes):
                found.append(
                    f"{lane.name} {site_id}: {len(writes)} write(s), {len(undos)} reversal(s)"
                )
            elif undos:
                undo = undos[0]
                inverse = (same(undo["old_value"]), same(undo["new_value"])) == (
                    same(row["new_value"]),
                    same(row["old_value"]),
                )
                if not inverse:
                    found.append(f"{lane.name} {site_id}: the reversal is not the write's inverse")
                reversed_cells += 1
    return found, reversed_cells


def close_reverted(
    step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    """Close an undone (or never applied) step on production's proof that none of its writes
    stands; its sites are then planned again by a later step. Read-only. A step accepted before
    its undo keeps its acceptance as history: the `REVERTED` record copies it
    (`superseded_acceptance`) and is what `plan`, `accept` and `card-file` read from then on."""
    _record, prov_rows, card_rows, live, journal, exported_at = _step_read(step, read, root)
    found, reversed_cells = standing_writes(step, prov_rows, card_rows, live, journal)
    acceptance = _closing(ACCEPTED_DIR, step, root)
    if not found:
        _record_closing(
            REVERTED_DIR,
            step,
            root,
            {
                "closed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "superseded_acceptance": (
                    json.loads(acceptance.read_text(encoding="utf-8"))
                    if acceptance.exists()
                    else None
                ),
                "read_at": exported_at,
                "sites": len(live),
                "reversed_cells": reversed_cells,
                "unwritten_cells": len(prov_rows) + len(card_rows) - reversed_cells,
            },
        )
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the card file
def card_file(
    path: Path,
    steps: Sequence[int],
    *,
    run_sql: Callable[[str], str] = WS.run_sql,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Render `public/data/card_descriptions.json` from production (read-only) after a sitting.

    The API boot imports the file into `card_stats` (FIELD_CONTRACT 2.3), so after the card writes
    the file must be the database's before it is pushed - immediately. `card_json`'s own renderer
    (`file_from_cards`, `canonical`, the existing key order, new keys in UUID order, cleared keys
    removed) renders it; this refuses unless every one of the named steps is closed, every key it
    changes is a card cell of those steps, and production holds each such cell as the steps left
    it: an accepted step's planned card, an undone step's card from before the step (5.6 of the
    runbook: after an undo the file is rendered back the same way, never `git revert`-ed). Where
    two named steps planned the same site - an undone step's site planned again - the later step's
    expectation wins. `card_json.py --check` (`ACCEPT_EXIT=0`) is the acceptance of the file that
    follows."""
    for step in steps:
        if not closed(step, root):
            raise PlanError(
                f"step {step} has no acceptance: the file follows closed steps only (`accept`, or "
                "`close-reverted` after an undo)"
            )
    planned: dict[str, str | None] = {}
    for step in sorted(steps):
        undone = reverted(step, root)
        for row in read_jsonl(root / step_name(step) / CARD / "PLAN.jsonl"):
            planned[row["site_id"]] = row["old_value"] if undone else row["new_value"]
    current = CJ.read_cards(path)
    live = CJ.production_cards(run_sql)
    moved = {
        site_id
        for site_id in set(current) | {s for s, card in live.items() if card is not None}
        if current.get(site_id) != live.get(site_id)
    }
    foreign = sorted(site_id for site_id in moved if site_id not in planned)
    if foreign:
        raise PlanError(
            f"{len(foreign)} card(s) differ between the file and production that the named steps "
            f"did not write (first: {foreign[:3]}) - run `card_json.py --check` and settle them first"
        )
    unwritten = sorted(site_id for site_id, card in planned.items() if live.get(site_id) != card)
    if unwritten:
        raise PlanError(
            f"{len(unwritten)} card(s) of the named steps: production does not hold them as the "
            f"steps left them (first: {unwritten[:3]})"
        )
    text = CJ.canonical(CJ.file_from_cards(current, live))
    path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "file": str(path),
        "cards": len(json.loads(text)[CJ.TOP_KEY]),
        "changed": sum(1 for s in moved if live.get(s) is not None),
        "removed": sum(1 for s in moved if live.get(s) is None),
    }


# ------------------------------------------------------------------------------ stale cards
STALE_SQL = (
    "SELECT u.id::text AS site_id, u.name, "
    "(encode(sha256(convert_to(coalesce(u.description, ''), 'UTF8')), 'hex') IS DISTINCT FROM "
    "u.raw_data -> '_card_provenance' ->> 'desc_sha256') AS stale, "
    "(encode(sha256(convert_to(coalesce(c.card_description, ''), 'UTF8')), 'hex') IS DISTINCT FROM "
    "u.raw_data -> '_card_provenance' ->> 'text_sha256') AS card_moved "
    "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    "WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired' "
    "AND u.raw_data ? '_card_provenance' ORDER BY u.id"
)


def stale(*, read: Callable[[str], str] = read_production) -> dict[str, Any]:
    """Read-only: the teaser cards whose description changed since their check (not shorts-eligible
    until lane WB runs for them again - `run.py select` takes them as candidates) and those whose
    card is no longer the one the provenance hashes (written by another path)."""
    rows, exported_at = parse_tagged_export(
        read(tagged_export_script([("site", STALE_SQL)])), ("site",)
    )
    moved = [r for r in rows["site"] if r["card_moved"]]
    old = [r for r in rows["site"] if r["stale"]]
    return {
        "read_at": exported_at,
        "teasers": len(rows["site"]),
        "stale": len(old),
        "card_moved": len(moved),
        "stale_sites": [f"{r['site_id']} {r['name']}" for r in old],
        "card_moved_sites": [f"{r['site_id']} {r['name']}" for r in moved],
    }


# ------------------------------------------------------------------------------ the CLI
def _steps(value: str) -> list[int]:
    first, _, last = value.partition("-")
    return list(range(int(first), int(last or first) + 1))


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _run(args: argparse.Namespace) -> int:
    if args.command == "plan":
        _print(plan_step(run_name(args.run), args.step))
        return 0
    if args.command == "accept":
        code, found = accept_step(args.step)
        for line in found:
            print(f"  {line}")
        print(f"RESULT: {len(found)} deviation(s)")
        return code
    if args.command == "close-reverted":
        code, found = close_reverted(args.step)
        for line in found:
            print(f"  {line}")
        print(f"RESULT: {len(found)} write(s) still standing")
        return code
    if args.command == "card-file":
        _print(card_file(args.file, _steps(args.steps)))
        return 0
    _print(stale())
    return 0


def main(argv: list[str] | None = None) -> int:
    """`accept` and `close-reverted` print `ACCEPT_EXIT=`, every other command `WRITE_EXIT=`. All
    of them are read-only on production; they write only their files: the step's plans, the closing
    record, the card file."""
    parser = argparse.ArgumentParser(prog="teaser", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="plan the next step of a run (read-only)")
    plan.add_argument("--run", required=True, help="the run's directory or its bare name")
    plan.add_argument("--step", required=True, type=int)
    accept = sub.add_parser("accept", help="re-read one written step; record it at 0 deviations")
    accept.add_argument("--step", required=True, type=int)
    close = sub.add_parser("close-reverted", help="close an undone step (read-only)")
    close.add_argument("--step", required=True, type=int)
    cards = sub.add_parser("card-file", help="render the card file from production (read-only)")
    cards.add_argument("--steps", required=True, help="the sitting's steps: N or A-B")
    cards.add_argument("--file", type=Path, default=CJ.CARD_FILE)
    sub.add_parser("stale", help="teaser cards whose description or card moved (read-only)")
    args = parser.parse_args(argv)
    tag = "ACCEPT" if args.command in ("accept", "close-reverted") else "WRITE"

    def body() -> int:
        try:
            return _run(args)
        except PlanError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1

    return W4.exit_line(tag, body)


if __name__ == "__main__":
    raise SystemExit(main())
