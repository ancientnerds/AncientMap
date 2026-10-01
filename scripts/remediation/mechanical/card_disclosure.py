"""Lane WB's disclosure correction: `_card_provenance.ai_system` of 185 cards, Opus only -> Opus and Sonnet.

## The defect

A teaser card is AI-generated text and discloses its AI system (`pipeline/utils/card_provenance.py`,
EU AI Act Art. 50). Until 2026-09-30 every provenance named Claude Opus only
(`model4.AI_SYSTEM_OPUS`), which was true while an Opus agent wrote every card. The model census of
2026-10-01 (`output/remediation/model_census/ANSWERS_TRUE_MODEL.jsonl`: per handoff answer the agent
that recorded it, its time and - from the Claude Code transcripts - the model that really ran)
shows that the rewrite stages of lane-WB runs `wb-ws-2026-09-27-01`, `-04` and `-06` were answered
by Sonnet 5.5 agents: where a rewrite produced a card's final text (`OUTCOMES.jsonl`,
`writer.stage` in `rewrite1`, `rewrite2`, `rewrite-v`), the live provenance names a model that did
not write it. Owner decision 2026-10-01: from then on every new write discloses both models
(`model4.AI_SYSTEM`), and these provenances are corrected to the same string.

Later runs need nothing: lane WB's chunks 02 and 05 have no outcomes yet, so their provenances are
built after the stamp change (`teaser/run.outcome_rows(ai_system=model4.AI_SYSTEM)`) and already
carry `model4.AI_SYSTEM`; run 03 was answered by Opus throughout.

## The list (`build_list`, pinned)

Each site that a closed lane-WB step left a teaser provenance on (the step's `prov/PLAN.jsonl`, an
`ACCEPTED/` step not undone, the latest step winning) is joined to its run's outcome - the outcome's
provenance must be the one the step wrote - and the outcome's writer record (`answered_by`,
`answered_at`) to the census. The site is listed when the model that really wrote its final text is
not named by its provenance's `ai_system`. A writer without a census row, with two different true
models, or with a model other than the two known ones is a refusal, never a guess. The list is
deterministic (sorted by site id) and pinned in `card_disclosure_list.py` by its sha256; `list
--check` re-derives it, and every `plan` does so first.

## What a step writes (`classify`, `lane`)

`card-disclosure-sNNN`, a cell lane on `unified_sites.raw_data`, at most 100 sites per step (the
list has 185, so two steps). Exactly one key changes: `_card_provenance.ai_system`, from
`AI_SYSTEM_OPUS` to `AI_SYSTEM`. The plan lists, and does not write, a site whose live provenance is
not exactly the outcome's provenance with `AI_SYSTEM_OPUS` (`teaser-provenance-moved`), that
already names `AI_SYSTEM` (`already-corrected`), that has none, or whose raw_data is not printed
the way this planner prints JSON. The transaction's guards: guard 3 holds the whole old `raw_data`,
so no other key can have moved; guard 5 holds the provenance's identity (`run|text_sha256|
desc_sha256`) - a card replaced since is refused; the lane invariant refuses a provenance that names
neither disclosure, write and reversal alike. The read-back counts the journal rows that changed
anything but this key (0) and the sites still naming `AI_SYSTEM_OPUS`.

## Who accepts it, and for which key only

* `teaser.py accept --step N` reads a step's provenance cell as this lane left it
  (`teaser.corrected_cell`): only the correction lane's own stamp counts, only as one journal row
  from exactly the raw_data that step planned to exactly that value with this one key corrected, and
  not reversed. Anything else that moved the cell is still a deviation.
* `verify_writes4.py --lane p4|p4wc` takes a later lane by stamp pattern (`--allow-stamp`); the
  runbook names this lane's pattern, `wb-card-disclosure-s%`, never `%`. That a lane so named moved
  one key only is this lane's own read-back (above) and `accept --step N` (journal old -> new).
* `card_disclosure.py accept --step N` is this lane's own acceptance (0 deviations, once).

Runbook: docs/procedures/CARD_DESCRIPTIONS.md, "5.9 The disclosure correction".

    M=scripts/remediation/mechanical
    $M/card_disclosure.py list [--write | --check]    (offline; the census and the run outcomes)
    $M/card_disclosure.py plan --step N               (read-only; the step's sites, PLAN.md)
    $M/apply.py --lane card-disclosure-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane card-disclosure-sNNN --rehearse-rollback
    $M/card_disclosure.py accept --step N             (read-only; ACCEPT_EXIT=0 at 0 deviations)
"""

from __future__ import annotations

import argparse
import functools
import hashlib
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

from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from phase4 import model4 as M  # noqa: E402 - the two disclosures
from phase4 import write4 as W4  # noqa: E402 - the exit line

from mechanical import card_disclosure_list as LIST  # noqa: E402
from mechanical import teaser as W  # noqa: E402 - the run outcomes, the closed steps, the read seam
from mechanical.citations import canonical, reprint  # noqa: E402
from mechanical.lane import (  # noqa: E402
    CARD_DISCLOSURE_LANE,
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

ROOT_NAME = "mechanical_card_disclosure"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
CENSUS = REPO / "output" / "remediation" / "model_census" / "ANSWERS_TRUE_MODEL.jsonl"
LIST_MODULE = _HERE.with_name("card_disclosure_list.py")
ACCEPTED_DIR = "ACCEPTED"
MAX_SITES = 100
PROV = CP.CARD_PROVENANCE_KEY
OLD, NEW = M.AI_SYSTEM_OPUS, M.AI_SYSTEM
#: The two models a census row may name, as `anthropic/<id>` appears in a disclosure.
KNOWN_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})
#: The writer stages whose answer is a card's final text (`teaser/run.py`).
CENSUS_SOURCE = "output/remediation/model_census/ANSWERS_TRUE_MODEL.jsonl"
TEST_ID = "WB/card-disclosure"
RULE = "card-disclosure"

#: Guard 5: the identity of the provenance whose disclosure is corrected - the run that wrote it,
#: the card it hashes and the description it was checked against. Held by the write and its reversal
#: alike, so it names nothing the correction itself changes.
PREMISE_SQL = (
    f"coalesce(u.raw_data -> '{PROV}' ->> 'run', '') || '|' || "
    f"coalesce(u.raw_data -> '{PROV}' ->> 'text_sha256', '') || '|' || "
    f"coalesce(u.raw_data -> '{PROV}' ->> 'desc_sha256', '')"
)
_AI_SYSTEM = f"raw_data -> '{PROV}' ->> 'ai_system'"
#: Lane invariant: a planned site's provenance names neither disclosure - after the write and after
#: its reversal alike (write: `NEW`; reversal: `OLD`).
_NAMES_NEITHER = Residual(
    "planned sites whose card provenance names neither disclosure",
    f"coalesce({_AI_SYSTEM}, '') NOT IN ({sql_literal(OLD)}, {sql_literal(NEW)})",
)
_CURATED = "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "


def premise_of(provenance: Mapping[str, Any]) -> str:
    """`PREMISE_SQL` in Python."""
    return f"{provenance['run']}|{provenance['text_sha256']}|{provenance['desc_sha256']}"


# ------------------------------------------------------------------------------ the lanes
def list_sha256(site_ids: Iterable[str]) -> str:
    """The pin of a list: sha256 of its sorted site ids, one per line."""
    return hashlib.sha256("".join(f"{site_id}\n" for site_id in site_ids).encode()).hexdigest()


def step_sites(step: int) -> tuple[str, ...]:
    """The pinned list's sites of one step (at most 100, in site order)."""
    chunk = LIST.SITE_IDS[(step - 1) * MAX_SITES : step * MAX_SITES] if step >= 1 else ()
    if not chunk:
        raise PlanError(f"step {step} has no sites: the pinned list holds {len(LIST.SITE_IDS)}")
    return chunk


def disclosure_lane(step: int) -> Lane:
    """The lane of one step: its own stamp (`teaser.CORRECTION_STAMP`), key prefix and directory."""
    name = f"card-disclosure-{W.step_name(step)}"
    still_old = Residual(
        "listed sites of this step still naming the Opus-only disclosure",
        f"id IN ({sql_ids(step_sites(step))}) AND {_AI_SYSTEM} = {sql_literal(OLD)}",
    )
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{W.CORRECTION_STAMP_PREFIX}{step:03d}",
        test_id=TEST_ID,
        confidence="authoritative",
        label="card disclosure correction",
        plan_table="_card_disclosure_plan",
        out_dir_name=f"{ROOT_NAME}/{W.step_name(step)}",
        post_commit_residual=still_old,
        rehearsal_residual=still_old,
        premise_sql=PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(Column("raw_data", "jsonb"),),
        write_invariant=_NAMES_NEITHER,
    )


def lane_of(name: str) -> Lane:
    """`card-disclosure-s001` -> the lane; `KeyError` for any other name."""
    match = CARD_DISCLOSURE_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return disclosure_lane(int(match.group(1)))


@functools.cache
def disclosure_readback(lane: Lane) -> str:
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
                "curated sites whose card provenance names the Opus-only disclosure",
                _CURATED + f"{_AI_SYSTEM} = {sql_literal(OLD)}",
            ),
            (
                "curated sites whose card provenance names the Opus and Sonnet disclosure",
                _CURATED + f"{_AI_SYSTEM} = {sql_literal(NEW)}",
            ),
            (lane.post_commit_residual.metric, _CURATED + lane.post_commit_residual.predicate),
            (
                "curated sites whose card provenance names neither disclosure",
                _CURATED + f"raw_data ? '{PROV}' AND coalesce({_AI_SYSTEM}, '') NOT IN "
                f"({sql_literal(OLD)}, {sql_literal(NEW)})",
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
                "journal rows for this run whose old value did not name the Opus-only disclosure",
                journal + was_old,
            ),
        ],
    )


# ------------------------------------------------------------------------------ the list
@dataclass(frozen=True)
class Listed:
    """One site whose provenance names a model that did not write its card, with the proof."""

    site_id: str
    name: str
    run: str
    step: int
    stage: str
    answered_by: str
    answered_at: str
    true_model: str
    census_files: tuple[str, ...]
    provenance: Mapping[str, Any]
    card: str

    def row(self) -> dict[str, Any]:
        """The `LIST.jsonl` line."""
        return {
            "site_id": self.site_id,
            "name": self.name,
            "run": self.run,
            "step": self.step,
            "stage": self.stage,
            "answered_by": self.answered_by,
            "answered_at": self.answered_at,
            "true_model": self.true_model,
            "census_files": list(self.census_files),
            "ai_system": self.provenance["ai_system"],
        }


def read_census(path: Path) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    """The census rows by `(answered_by, answered_at)`."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the model census is not there")
    census: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in read_jsonl(path):
        census.setdefault((row["answered_by"], row["answered_at"]), []).append(row)
    return census


def provenances_written(root: Path) -> dict[str, tuple[int, str, Mapping[str, Any]]]:
    """Per site, the teaser provenance a closed lane-WB step left on it: `(step, run, provenance)`.

    Only a step that was accepted and not undone wrote anything that stands; a later step that
    planned the site again wins, and a step that cleared the card leaves no provenance."""
    held: dict[str, tuple[int, str, Mapping[str, Any]]] = {}
    for record in sorted(W.read_steps(root), key=lambda s: s["step"]):
        step = record["step"]
        if not W.accepted(step, root) or W.reverted(step, root):
            continue
        for row in read_jsonl(root / W.step_name(step) / W.PROV / "PLAN.jsonl"):
            raw = None if row["new_value"] is None else json.loads(row["new_value"])
            if isinstance(raw, dict) and PROV in raw:
                held[row["site_id"]] = (step, record["run"], raw[PROV])
            else:
                held.pop(row["site_id"], None)
    return held


def build_list(*, root: Path = W.ROOT, runs: Path = W.RUNS, census: Path = CENSUS) -> list[Listed]:
    """The sites to correct, sorted by site id: pure of the files it reads, deterministic."""
    answers = read_census(census)
    outcomes: dict[str, dict[str, Mapping[str, Any]]] = {}
    listed: list[Listed] = []
    for site_id, (step, run, provenance) in sorted(provenances_written(root).items()):
        if run not in outcomes:
            path = runs / run / "OUTCOMES.jsonl"
            if not path.exists():
                raise PlanError(f"{path} does not exist: step {step} was planned from it")
            outcomes[run] = {o["site_id"]: o for o in read_jsonl(path)}
        outcome = outcomes[run].get(site_id)
        if (
            outcome is None
            or outcome["status"] != W.ACCEPTED
            or outcome["provenance"] != provenance
        ):
            raise PlanError(
                f"{site_id}: step {step}'s provenance is not run {run}'s accepted outcome"
            )
        writer = outcome["writer"]
        found = answers.get((writer["answered_by"], writer["answered_at"]), [])
        models = {row["true_model"] for row in found}
        if len(models) != 1 or not models <= KNOWN_MODELS:
            raise PlanError(
                f"{site_id}: the census names {sorted(models) or 'no model'} for writer "
                f"{writer['answered_by']} at {writer['answered_at']} - never a guess"
            )
        (true,) = models
        if f"anthropic/{true}" in provenance["ai_system"]:
            continue
        if provenance["ai_system"] != OLD:
            raise PlanError(
                f"{site_id}: the provenance names {provenance['ai_system']!r}, which is neither "
                f"disclosure; this lane corrects {OLD!r} only"
            )
        listed.append(
            Listed(
                site_id=site_id,
                name=outcome["name"],
                run=run,
                step=step,
                stage=writer["stage"],
                answered_by=writer["answered_by"],
                answered_at=writer["answered_at"],
                true_model=true,
                census_files=tuple(sorted(row["file"] for row in found)),
                provenance=provenance,
                card=outcome["card"],
            )
        )
    return listed


def module_text(site_ids: Sequence[str]) -> str:
    """`card_disclosure_list.py` as `list --write` writes it (stable under `ruff format`)."""
    body = "".join(f'    "{site_id}",\n' for site_id in site_ids)
    ids = f"\n{body}" if body else ""
    return (
        '"""The sites whose card disclosure `card-disclosure-sNNN` corrects (generated, never '
        "hand-edited).\n\n"
        "`mechanical/card_disclosure.py list --write` derives them from the model census and the "
        "lane-WB\n"
        "run outcomes and rewrites this file; `list --check` re-derives them and refuses when they "
        'differ.\n"""\n\n'
        f'LIST_SHA256 = "{list_sha256(site_ids)}"\n'
        f"SITE_IDS: tuple[str, ...] = ({ids})\n"
    )


def summary(listed: Sequence[Listed]) -> dict[str, Any]:
    return {
        "sites": len(listed),
        "sha256": list_sha256(item.site_id for item in listed),
        "by_run_stage": dict(sorted(Counter(f"{i.run} {i.stage}" for i in listed).items())),
        "true_models": dict(sorted(Counter(i.true_model for i in listed).items())),
        "steps": -(-len(listed) // MAX_SITES),
    }


# ------------------------------------------------------------------------------ the read
@dataclass(frozen=True)
class Live:
    """One site as the step's export read it."""

    site_id: str
    name: str
    scope_status: str | None
    raw_data: str | None
    description: str | None
    card: str | None
    premise: str


def site_sql(site_ids: Iterable[str]) -> str:
    return (
        "SELECT u.id::text AS site_id, u.name, u.scope_status, u.raw_data::text AS raw_data, "
        f"u.description, c.card_description AS card, {PREMISE_SQL} AS premise "
        "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
        f"WHERE u.source_id = 'ancient_nerds' AND u.id::text IN ({sql_ids(site_ids)}) ORDER BY u.id"
    )


def journal_sql(site_ids: Iterable[str]) -> str:
    """Every journal row of `raw_data` of these sites."""
    return (
        "SELECT l.id, l.row_pk, l.run_stamp, coalesce(l.test_id, '') AS test_id, l.old_value, "
        "l.new_value FROM remediation_change_log l WHERE l.table_name = 'unified_sites' AND "
        f"l.column_name = 'raw_data' AND l.row_pk IN ({sql_ids(site_ids)}) ORDER BY l.id"
    )


def _live(r: Mapping[str, Any]) -> Live:
    return Live(
        site_id=str(r["site_id"]),
        name=str(r["name"]),
        scope_status=r["scope_status"],
        raw_data=r["raw_data"],
        description=r["description"],
        card=r["card"],
        premise=str(r["premise"]),
    )


def parse_export(text: str) -> tuple[dict[str, Live], dict[str, list[JournalLink]], str]:
    rows, exported_at = parse_tagged_export(text, ("site", "journal"))
    live = {str(r["site_id"]): _live(r) for r in rows["site"]}
    journal: dict[str, list[JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault(str(r["row_pk"]), []).append(
            JournalLink(
                int(r["id"]),
                str(r["run_stamp"]),
                str(r["test_id"]),
                canonical(r["old_value"]),
                canonical(r["new_value"]),
            )
        )
    return live, journal, exported_at


# ------------------------------------------------------------------------------ the decision
NOT_CURATED = "not-a-curated-site"
NO_PROVENANCE = "no-teaser-provenance"
RAW_DATA_NOT_OBJECT = "raw-data-not-an-object"
NOT_REPRINTED = "raw-data-not-reprinted"
PROVENANCE_MOVED = "teaser-provenance-moved"
ALREADY_CORRECTED = "already-corrected"
REFUSAL_MEANING = {
    NOT_CURATED: "the site is no longer a curated site",
    NO_PROVENANCE: "the site holds no teaser provenance (its card was cleared or replaced)",
    RAW_DATA_NOT_OBJECT: "raw_data is JSON but not an object",
    NOT_REPRINTED: "raw_data is not printed the way this planner prints JSON",
    PROVENANCE_MOVED: "the live teaser provenance is not the run outcome's: the card was written "
    "again since - its disclosure is that write's",
    ALREADY_CORRECTED: "the provenance already names the Opus and Sonnet disclosure",
    "journal-chain-broken": "the raw_data journal is not continuous",
    "journal-disagrees": "the raw_data journal does not end at the live value",
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
    runs = f"output/remediation/teaser/runs/{item.run}/OUTCOMES.jsonl"
    return (
        {
            "source": f"model census: {'; '.join(item.census_files)}",
            "url": CENSUS_SOURCE,
            "quote": f"answered_by {item.answered_by}, answered_at {item.answered_at}, "
            f"true_model {item.true_model}",
        },
        {
            "source": f"lane WB run {item.run}, step {item.step}: the final text was written at "
            f"stage {item.stage} by {item.answered_by}",
            "url": runs,
            "quote": item.card,
        },
        {
            "source": "scripts/remediation/phase4/model4.py",
            "url": None,
            "quote": f"the disclosure {OLD!r} names a model that did not write this card; the "
            f"corrected disclosure is {NEW!r}",
        },
    )


def classify(item: Listed, live: Live | None, journal: Sequence[JournalLink]) -> Verdict:
    """One listed site: its one-key correction, or the reason it is listed and not written."""
    name = item.name if live is None else live.name
    if live is None:
        return _refused(item, name, NOT_CURATED, "the export did not return the site")
    if live.raw_data is None:
        return _refused(item, name, NO_PROVENANCE, "raw_data is NULL")
    raw = json.loads(live.raw_data)
    if not isinstance(raw, dict):
        return _refused(item, name, RAW_DATA_NOT_OBJECT, f"raw_data is a {type(raw).__name__}")
    if reprint(raw) != live.raw_data:
        return _refused(item, name, NOT_REPRINTED, "the journal would record another spelling")
    broken = journal_break(list(journal), canonical(live.raw_data))
    if broken is not None:
        return _refused(item, name, broken[0], broken[1])
    held = raw.get(PROV)
    if not isinstance(held, dict):
        return _refused(item, name, NO_PROVENANCE, f"raw_data holds no {PROV}")
    if held == {**item.provenance, "ai_system": NEW}:
        return _refused(item, name, ALREADY_CORRECTED, "the provenance already names AI_SYSTEM")
    if held != item.provenance:
        return _refused(
            item, name, PROVENANCE_MOVED, f"the provenance is not run {item.run}'s outcome"
        )
    if live.premise != premise_of(held):
        raise PlanError(
            f"{item.site_id}: the export's premise {live.premise!r} is not the identity of the "
            "provenance it read - the export is not one snapshot"
        )
    return Verdict(
        site_id=item.site_id,
        site_name=name,
        ok=True,
        old_value=live.raw_data,
        new_value=reprint(W.correct_disclosure(raw)),
        rule=RULE,
        reason="",
        note=f"{PROV}.ai_system {OLD!r} -> {NEW!r}; every other key as it was; the card was "
        f"written by {item.true_model} (stage {item.stage})",
        phase3=False,
        finding_test_id=TEST_ID,
        evidence=_evidence(item),
        premise=live.premise,
        column="raw_data",
    )


def build_step(
    step: int,
    listed: Sequence[Listed],
    live: Mapping[str, Live],
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
        lane=disclosure_lane(step),
    )


# ------------------------------------------------------------------------------ the steps
def accepted(step: int, root: Path = ROOT) -> bool:
    return (root / ACCEPTED_DIR / f"step-{step:03d}.json").exists()


def write_step_md(plan: Plan, step: int, path: Path) -> None:
    lane = plan.lane
    lines = [
        f"# Lane WB disclosure correction, step {step:03d} (`{lane.name}`)",
        "",
        f"Planned by `scripts/remediation/mechanical/card_disclosure.py plan`. {len(plan.changes)} "
        f"site(s) written, {len(plan.skipped)} listed. Run stamp `{lane.run_stamp}`, journal test "
        f"id `{lane.test_id}`. One key changes: `{PROV}.ai_system`, `{OLD}` -> `{NEW}`.",
        "",
        "## Written",
        "",
        "| site | the card's writer | the census |",
        "|---|---|---|",
    ]
    for change in plan.changes:
        census, written = change.evidence[0], change.evidence[1]
        lines.append(
            f"| {change.site_name} (`{change.site_id}`) | {written['source']} | {census['quote']} |"
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
            f"step {step - 1} has no acceptance: `card_disclosure.py accept --step {step - 1}`"
        )
    out = root / W.step_name(step)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once (its ROLLBACK.sql may be the undo)")
    derived = build_list() if listed is None else list(listed)
    text = read(tagged_export_script([("site", site_sql(sites)), ("journal", journal_sql(sites))]))
    live, journal, _at = parse_export(text)
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
ACCEPT_JOURNAL_SQL = (
    "SELECT l.row_pk, l.column_name, l.run_stamp, l.old_value, l.new_value "
    "FROM remediation_change_log l WHERE l.run_stamp IN ({stamps}) ORDER BY l.id"
)


def deviations(
    step: int,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    lane = disclosure_lane(step)
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
        if not W.moves_one_key(row["old_value"], row["new_value"]):
            found.append(f"{site_id}: the plan changes more than the one key")
        if site is None or canonical(site.raw_data) != canonical(row["new_value"]):
            found.append(f"{site_id}: does not hold the planned value")
            continue
        if entry is None or (canonical(entry["old_value"]), canonical(entry["new_value"])) != (
            canonical(row["old_value"]),
            canonical(row["new_value"]),
        ):
            found.append(f"{site_id}: the journal row is not the plan's")
        elif not W.moves_one_key(entry["old_value"], entry["new_value"]):
            found.append(f"{site_id}: the journal row changed more than the one key")
        provenance = CP.card_provenance_of(site.raw_data)
        if provenance is None or provenance["ai_system"] != NEW:
            found.append(f"{site_id}: the provenance does not name the corrected disclosure")
        elif not CP.describes(provenance, site.card):
            found.append(f"{site_id}: the provenance does not hash the live card")
    return found


def accept_step(
    step: int, *, read: Callable[[str], str] = W.read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once."""
    lane = disclosure_lane(step)
    rows = read_jsonl(root / W.step_name(step) / "PLAN.jsonl")
    sites = [row["site_id"] for row in rows]
    listed = ", ".join(sql_literal(stamp) for stamp in (lane.run_stamp, lane.rollback_run_stamp))
    text = read(
        tagged_export_script(
            [
                ("site", site_sql(sites)),
                ("journal", ACCEPT_JOURNAL_SQL.format(stamps=listed)),
            ]
        )
    )
    parsed, exported_at = parse_tagged_export(text, ("site", "journal"))
    live = {str(r["site_id"]): _live(r) for r in parsed["site"]}
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
    listed = build_list(root=args.teaser_root, runs=args.runs, census=args.census)
    _print(summary(listed))
    ids = [item.site_id for item in listed]
    if args.check:
        if ids != list(LIST.SITE_IDS) or list_sha256(ids) != LIST.LIST_SHA256:
            print(
                f"REFUSED: the derived list ({len(ids)} sites, {list_sha256(ids)}) is not the "
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
    parser = argparse.ArgumentParser(prog="card_disclosure", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="derive the sites to correct (offline)")
    listing.add_argument(
        "--write", action="store_true", help="write LIST.jsonl and the pinned module"
    )
    listing.add_argument("--check", action="store_true", help="refuse unless the pinned list holds")
    listing.add_argument("--teaser-root", type=Path, default=W.ROOT)
    listing.add_argument("--runs", type=Path, default=W.RUNS)
    listing.add_argument("--census", type=Path, default=CENSUS)
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
