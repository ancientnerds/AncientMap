"""Lane WB: the teaser cards, from the fact basis to checked outcomes, through the Opus handoff.

Owner decisions O2-O4 and O10 of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`); the
contract and the whole runbook are `docs/procedures/CARD_DESCRIPTIONS.md`. No model is called here:
every card is written by one Opus agent and checked by another, each answering one batch through the
handoff directory (`scripts/remediation/opus_handoff.py`). Production is only read (`select`). The
write is `scripts/remediation/mechanical/teaser.py` (plan) and `mechanical/apply.py` (journalled).

    T=scripts/remediation/teaser/run.py
    R=output/remediation/teaser/runs/<run>    H=output/remediation/handoff/teaser-<run>
    $T select --run R [--pilot 20 --seed N] [--sites FILE] [--basis WC ...] [--exclude-run R0 ...]
        (read-only)
    $T export --run R --stage write --handoff $H-write     one question per site, batches of 15
    $T brief --run R --handoff $H-write --batch-id B       the instruction of batch B's agent
        (the agent drafts, runs `check-answer` until it is clean, and records with
        `opus_handoff.py answer --answered-by teaser-B`)
    opus_handoff.py validate --dir $H-write                every answer in, in shape, by Opus
    $T import --run R --stage write                        parse, mechanical checks: STAGE-write
    ... the same for check, rewrite1, check1, rewrite2, check2 (a stage nobody is due for is
        skipped: `export` says so)
    $T status --run R                                      who is due where, accepted, cleared
    $T outcomes --run R                                    OUTCOMES.jsonl, once every site settled
    $T judge-export --run R --handoff $H-judge             pilot: an independent web judge
    $T judge-import --run R                                quotes fetched and checked: JUDGE.md

## The stages

`write` asks every candidate; `check` asks a different agent about every card that passed the
mechanical checks (`contract.problems`), one checker per writer batch; a card that failed either goes
to `rewrite1` with its findings and is checked by a new checker in `check1`; once more in `rewrite2`
and `check2`; after that the site gets no card (cleared). Each stage's round is exported once, into a
handoff directory of its own; the import rebuilds every prompt from the run's files and refuses an
answer to any other.

**Independence is a process rule, kept by the orchestrator**: every batch of every stage (and of the
judge) is answered by a new agent, and the brief tells an agent that answered another batch of lane
WB to stop. The import cannot see an agent - `answered_by` is the batch's name, `teaser-<batch_id>`,
and batch ids carry their stage - so its refusal of a checker (or judge) whose name wrote or checked
the site before catches a reused or mistyped name, never one agent reused under two batch names.

## The run's files (`output/remediation/teaser/runs/<run>/`, gitignored: they hold description text)

`EXPORT.jsonl` (the read-only production export `select` read), `RUN.json` (the selection, pinned by
sha256), `SITES.jsonl` (each candidate's fact basis inputs), `LISTED.jsonl` (every curated site that
is not a candidate, and why), `ROUNDS.jsonl`, `STAGE-<stage>.jsonl`, `OUTCOMES.jsonl` and
`OUTCOMES.md`; for the pilot `JUDGE.jsonl`, `JUDGE.md` and `pages/` (each cited page, fetched once).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
from mechanical.plan import (  # noqa: E402
    PlanError,
    parse_tagged_export,
    tagged_export_script,
    write_tagged_export,
)
from opus_audit import quotes as Q  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from phase4 import model4 as M  # noqa: E402 - AI_SYSTEM, the disclosure's model string
from phase4 import verify4 as V  # noqa: E402 - card_fit, V10's font measurement

from pipeline.utils import card_provenance as CP  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402

RUNS = ROOT / "output" / "remediation" / "teaser" / "runs"
CURATED_SOURCE = "ancient_nerds"
RETIRED = "retired"
#: The description provenances a teaser may be written from: the Phase-4 lanes, whose text is
#: assembled from a pinned source (W, S) or restated from one (T, R). Lane L alone is the March text
#: (unverified), and a text without provenance is unclaimed (HUMAN_ONLY D7): both wait for lane WC.
BASIS_LANES = frozenset({"W", "S", "T", "R"})
#: Lane WC's sentence check (owner decision O5): `raw_data._description_check`, whose `desc_sha256`
#: hashes the text that stayed after every sentence was checked against a quoted source. Such a text
#: keeps lane L's provenance (its hash moved) or none, so the check record is what makes it a basis.
#: The spelling is `phase4/wc4.py:CHECK_KEY` of `wip/wc`; the merge of lane WC replaces this literal
#: with an import of it (CARD_DESCRIPTIONS.md, "Merging").
CHECK_KEY = "_description_check"
#: The basis a candidate's description is (`SITES.jsonl` "basis"): a Phase-4 lane, or lane WC's check.
SENTENCE_CHECKED = "WC"
#: What `select --basis` may restrict a run to.
BASES = tuple(sorted(BASIS_LANES | {SENTENCE_CHECKED}))
BATCH_SIZE = 15
JUDGE_BATCH_SIZE = 5
WRITER_STAGES = ("write", "rewrite1", "rewrite2")
CHECKER_STAGES = ("check", "check1", "check2")
ROUNDS = tuple(zip(WRITER_STAGES, CHECKER_STAGES, strict=True))
STAGES = tuple(stage for pair in ROUNDS for stage in pair)
JUDGE_STAGE = "judge"
#: The web requests of the pilot judge's import: the lanes' one User-Agent, no personal data. The
#: bare `AncientMapRemediation/1.0 (research)` drew 403 from Wikimedia through httpx on every page of
#: pilot wb-pilot-2026-09-26 (its robot policy wants a contact; the project URL is one).
USER_AGENT = research_web.USER_AGENT
#: The pilot gate (sealed with the runbook): no claim CONTRADICTED - with a proving quote or
#: without one - and at most this share of all claims left without a proving quote (UNVERIFIABLE,
#: or a quote the machine did not find).
PILOT_MAX_UNPROVEN_SHARE = 0.10

#: Why a curated site is not a candidate (LISTED.jsonl).
NO_DESCRIPTION = "no-description"
NOT_FINAL = "not-final"
CURRENT = "current"
NO_CARD_ROW = "no-card-row"
ASKED_BEFORE = "asked-before"
OTHER_BASIS = "other-basis"
NOT_DRAWN = "not-drawn"
NOT_LISTED = "not-in-sites-file"


class RunError(ValueError):
    """The step must not run on this state. Nothing was written by it."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _shown(path: Path) -> str:
    try:
        return _resolve(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def jsonl_text(rows: Iterable[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = jsonl_text(rows)
    path.write_text(text, encoding="utf-8", newline="\n")
    return CP.text_sha256(text)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ------------------------------------------------------------------------------ select
SITES_SQL = (
    "SELECT u.id::text AS site_id, u.name, u.country, u.description, u.scope_status, "
    "u.raw_data -> '_description_provenance' ->> 'lane' AS lane, "
    "u.raw_data -> '_description_provenance' ->> 'desc_sha256' AS provenance_desc_sha256, "
    f"u.raw_data -> '{CHECK_KEY}' ->> 'desc_sha256' AS check_desc_sha256, "
    "u.raw_data -> '_card_provenance' AS card_provenance, "
    "(c.site_id IS NOT NULL) AS has_card_row, c.card_description AS card, "
    "coalesce((SELECT json_agg(n.name ORDER BY n.name) FROM unified_site_names n "
    "WHERE n.site_id = u.id), '[]'::json) AS alt_names "
    "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    f"WHERE u.source_id = '{CURATED_SOURCE}' ORDER BY u.id"
)


def export_script() -> str:
    """One read-only repeatable-read snapshot of every curated site's card inputs."""
    return tagged_export_script([("site", SITES_SQL)])


def basis_of(row: Mapping[str, Any]) -> str | None:
    """What makes the row's description a fact basis: its Phase-4 lane (`W`, `S`, `T`, `R`) while
    that provenance hashes exactly this text, else lane WC's sentence check (`WC`) while the check
    record hashes it; `None` for a text neither describes (lane L alone, no provenance, a text
    changed since either record was written)."""
    digest = CP.text_sha256(row["description"])
    if row["lane"] in BASIS_LANES and row["provenance_desc_sha256"] == digest:
        return str(row["lane"])
    if row["check_desc_sha256"] == digest:
        return SENTENCE_CHECKED
    return None


def classify(row: Mapping[str, Any]) -> tuple[str | None, str]:
    """`(reason, detail)` a curated row is not a candidate for; `(None, '')` for a candidate."""
    if row["scope_status"] == RETIRED:
        return RETIRED, "retired (E4): its page answers 410 and its card is never drawn"
    if not row["has_card_row"]:
        return NO_CARD_ROW, "no card_stats row: nothing to write a card into"
    description = row["description"]
    if description is None or not description.strip():
        return NO_DESCRIPTION, "no published description: the card is cleared"
    teaser = CP.validate(row["card_provenance"]) if row["card_provenance"] is not None else None
    if (
        teaser is not None
        and CP.describes(teaser, row["card"])
        and not CP.stale(teaser, description)
    ):
        return CURRENT, "its teaser card is live and checked against this description"
    if basis_of(row) is None:
        return NOT_FINAL, (
            f"not a sourced text: no lane-{'/'.join(sorted(BASIS_LANES))} provenance and no "
            f"sentence check hashes it (provenance lane {row['lane']!r})"
        )
    return None, ""


def _site_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "site_id": row["site_id"],
        "name": row["name"],
        "country": row["country"],
        "description": row["description"],
        "alt_names": list(row["alt_names"]),
        "card": row["card"],
        "lane": row["lane"],
        "basis": basis_of(row),
        "desc_sha256": CP.text_sha256(row["description"]),
    }


@dataclass(frozen=True)
class Selection:
    sites: list[dict[str, Any]]
    listed: list[dict[str, Any]]


def select_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    earlier: Mapping[str, str],
    sites: set[str] | None,
    pilot: tuple[int, int] | None,
    basis: set[str] | None = None,
) -> Selection:
    """The candidates of a run and the listing of every other curated site. Pure.

    `earlier` maps a site asked in an earlier run to the description sha256 it was asked with: it is
    asked again only when its description changed since. `sites` restricts the run to a list;
    `basis` to the candidates of these bases (`BASES`: the pilot of the sentence-checked texts asks
    `WC` alone); `pilot` = (n, seed) then draws n candidates at random with that seed.
    """
    candidates: list[dict[str, Any]] = []
    listed: list[dict[str, Any]] = []

    def listing(row: Mapping[str, Any], reason: str, detail: str) -> None:
        listed.append(
            {
                "site_id": row["site_id"],
                "name": row["name"],
                "reason": reason,
                "detail": detail,
                "card": row["card"],
                # the text as it was read: a clear's premise (`mechanical/teaser.py classify`)
                "desc_sha256": CP.text_sha256(row["description"] or ""),
            }
        )

    for row in sorted(rows, key=lambda r: str(r["site_id"])):
        reason, detail = classify(row)
        if reason is not None:
            listing(row, reason, detail)
        elif earlier.get(row["site_id"]) == CP.text_sha256(row["description"]):
            listing(row, ASKED_BEFORE, "asked in an earlier run with this description")
        elif sites is not None and row["site_id"] not in sites:
            listing(row, NOT_LISTED, "not in the run's sites file")
        elif basis is not None and basis_of(row) not in basis:
            listing(row, OTHER_BASIS, f"basis {basis_of(row)} is not asked (--basis)")
        else:
            candidates.append(_site_row(row))
    if sites is not None:
        missing = sorted(sites - {row["site_id"] for row in rows})
        if missing:
            raise RunError(f"{len(missing)} listed site(s) are no curated site: {missing[:5]}")
    if pilot is not None:
        n, seed = pilot
        if n > len(candidates):
            raise RunError(f"a pilot of {n} from {len(candidates)} candidate(s)")
        draw = random.Random(seed).sample(candidates, n)  # noqa: S311 - a seeded draw
        drawn = {site["site_id"] for site in draw}
        for site in candidates:
            if site["site_id"] not in drawn:
                listing(site, NOT_DRAWN, f"not drawn for the pilot (seed {seed})")
        candidates = [site for site in candidates if site["site_id"] in drawn]
        listed.sort(key=lambda r: r["site_id"])
    return Selection(candidates, listed)


def earlier_sites(runs: Sequence[Path]) -> dict[str, str]:
    """Every site asked in the given runs, with the description sha256 it was asked with."""
    asked: dict[str, str] = {}
    for run in runs:
        for site in read_jsonl(_resolve(run) / "SITES.jsonl"):
            asked[site["site_id"]] = site["desc_sha256"]
    return asked


def select(
    run: Path,
    *,
    read: Callable[[Path], None],
    sites_file: Path | None,
    pilot: tuple[int, int] | None,
    exclude: Sequence[Path],
    basis: set[str] | None = None,
) -> dict[str, Any]:
    """Read production once (read-only) and fix the run's candidates. Once per run."""
    if (run / "RUN.json").exists():
        raise RunError(f"{run} is selected already: a run's sites are fixed once")
    export = run / "EXPORT.jsonl"
    read(export)
    text = export.read_text(encoding="utf-8")
    try:
        parsed, exported_at = parse_tagged_export(text, ("site",))
    except PlanError as exc:
        raise RunError(str(exc)) from exc
    wanted = None
    if sites_file is not None:
        wanted = {
            line.strip() for line in sites_file.read_text("utf-8").splitlines() if line.strip()
        }
    selection = select_rows(
        parsed["site"], earlier=earlier_sites(exclude), sites=wanted, pilot=pilot, basis=basis
    )
    if not selection.sites:
        raise RunError("no candidate: nothing to ask")
    record = {
        "run": run.name,
        "selected_at": _now(),
        "exported_at": exported_at,
        "export_sha256": CP.text_sha256(text),
        "sites": len(selection.sites),
        "sites_sha256": write_jsonl(run / "SITES.jsonl", selection.sites),
        "listed_sha256": write_jsonl(run / "LISTED.jsonl", selection.listed),
        "listed": dict(sorted(Counter(r["reason"] for r in selection.listed).items())),
        "basis_lanes": sorted(BASIS_LANES),
        "basis": dict(sorted(Counter(site["basis"] for site in selection.sites).items())),
        "basis_asked": None if basis is None else sorted(basis),
        "pilot": None if pilot is None else {"n": pilot[0], "seed": pilot[1]},
        "sites_file": None if sites_file is None else _shown(sites_file),
        "excluded_runs": [_shown(path) for path in exclude],
        "contract": {"min_chars": C.MIN_CHARS, "max_chars": C.MAX_CHARS},
    }
    write_json(run / "RUN.json", record)
    return record


# ------------------------------------------------------------------------------ the run's state
def _pinned_jsonl(run: Path, name: str, key: str) -> list[dict[str, Any]]:
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    path = run / name
    if CP.text_sha256(path.read_bytes().decode("utf-8").replace("\r\n", "\n")) != record[key]:
        raise RunError(f"{path} is not the file RUN.json pins")
    return read_jsonl(path)


def bases(run: Path) -> dict[str, C.Basis]:
    """Every candidate's fact basis, from the pinned SITES.jsonl."""
    out: dict[str, C.Basis] = {}
    for row in _pinned_jsonl(run, "SITES.jsonl", "sites_sha256"):
        out[row["site_id"]] = C.basis(
            site_id=row["site_id"],
            name=row["name"],
            country=row["country"],
            description=row["description"],
            alt_names=row["alt_names"],
        )
    return out


def read_rounds(run: Path) -> list[dict[str, Any]]:
    path = run / "ROUNDS.jsonl"
    return read_jsonl(path) if path.exists() else []


def _round(run: Path, stage: str) -> dict[str, Any] | None:
    found = [r for r in read_rounds(run) if r["stage"] == stage]
    return found[0] if found else None


def _round_of_handoff(run: Path, handoff: Path) -> dict[str, Any]:
    wanted = _resolve(handoff).resolve()
    for record in read_rounds(run):
        if _resolve(Path(record["handoff"])).resolve() == wanted:
            return record
    raise RunError(f"{handoff} is not the directory of an exported round of {run}")


def stage_records(run: Path, before: str | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Every imported stage's records, by stage and site - only those of the stages before `before`
    when it is given: the state that stage's questions were asked from, whether or not it (or a
    later stage) has been imported since."""
    cut = len(STAGES) if before is None else STAGES.index(before)
    out: dict[str, dict[str, dict[str, Any]]] = {stage: {} for stage in STAGES}
    for stage in STAGES[:cut]:
        path = run / f"STAGE-{stage}.jsonl"
        if path.exists():
            out[stage] = {row["site_id"]: row for row in read_jsonl(path)}
    return out


@dataclass(frozen=True)
class Progress:
    """Where one site stands: due at a stage, accepted, or cleared - with its failed cards."""

    status: str
    stage: str | None
    findings: tuple[P.Finding, ...] = ()
    writer: Mapping[str, Any] | None = None
    check: Mapping[str, Any] | None = None

    @property
    def card(self) -> str | None:
        return None if self.writer is None else self.writer["card"]


DUE = "due"
ACCEPTED = "accepted"
CLEARED = "cleared"


def progress(site_id: str, records: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Progress:
    """The site's state, derived from the imported records alone (module doc, "The stages")."""
    findings: list[P.Finding] = []
    for writer_stage, checker_stage in ROUNDS:
        written = records[writer_stage].get(site_id)
        if written is None:
            return Progress(DUE, writer_stage, tuple(findings))
        if written["problems"]:
            findings.append(P.Finding(written["card"], P.findings_of(written)))
            continue
        checked = records[checker_stage].get(site_id)
        if checked is None:
            return Progress(DUE, checker_stage, tuple(findings), writer=written)
        if checked["verdict"] == A.PASSED:
            return Progress(ACCEPTED, checker_stage, tuple(findings), written, checked)
        findings.append(P.Finding(written["card"], P.findings_of(checked)))
    return Progress(CLEARED, None, tuple(findings))


def states(run: Path) -> dict[str, Progress]:
    records = stage_records(run)
    return {site_id: progress(site_id, records) for site_id in bases(run)}


def prompt_for(stage: str, site: C.Basis, state: Progress) -> str:
    """The exact question of one site at one stage."""
    if stage == "write":
        return P.writer_prompt(site)
    if stage in WRITER_STAGES:
        return P.rewrite_prompt(site, state.findings)
    assert state.card is not None
    return P.checker_prompt(site, state.card)


# ------------------------------------------------------------------------------ export
def _batches(stage: str, due: Mapping[str, Progress]) -> list[tuple[str, list[str]]]:
    """Batches of one stage: writer stages by site id in chunks; a checker stage keeps each writer
    batch together, so one checker checks one writer's cards."""
    if stage in WRITER_STAGES:
        ordered = sorted(due)
        groups = [ordered[i : i + BATCH_SIZE] for i in range(0, len(ordered), BATCH_SIZE)]
    else:
        by_writer: dict[str, list[str]] = {}
        for site_id in sorted(due):
            writer = due[site_id].writer
            assert writer is not None
            by_writer.setdefault(writer["batch_id"], []).append(site_id)
        groups = [
            members[i : i + BATCH_SIZE]
            for _batch, members in sorted(by_writer.items())
            for i in range(0, len(members), BATCH_SIZE)
        ]
    return [(f"{stage}-{n:03d}", group) for n, group in enumerate(groups, start=1)]


def export_stage(run: Path, stage: str, handoff: Path) -> dict[str, Any]:
    """One stage's round into a handoff directory of its own; refused while an earlier one waits."""
    if stage not in STAGES:
        raise RunError(f"{stage!r} is no stage of lane WB")
    if _round(run, stage) is not None:
        raise RunError(f"stage {stage} is exported already: a stage is asked once per run")
    target = _resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise RunError(f"{handoff} is not empty: a round gets a directory of its own")
    current = states(run)
    earlier = STAGES[: STAGES.index(stage)]
    waiting = Counter(p.stage for p in current.values() if p.status == DUE and p.stage in earlier)
    if waiting:
        raise RunError(f"earlier stages still wait for their import: {dict(waiting)}")
    due = {site: p for site, p in current.items() if p.status == DUE and p.stage == stage}
    if not due:
        return {"stage": stage, "questions": 0, "note": "nobody is due: no round, next stage"}
    sites = bases(run)
    groups = _batches(stage, due)
    for batch_id, members in groups:
        for site_id in members:
            OH.export(
                target,
                batch_id=batch_id,
                stage=stage,
                label=site_id,
                field="card_description",
                prompt=prompt_for(stage, sites[site_id], due[site_id]),
            )
    record = {
        "stage": stage,
        "handoff": _shown(handoff),
        "batches": dict(groups),
        "exported_at": _now(),
    }
    write_jsonl(run / "ROUNDS.jsonl", [*read_rounds(run), record])
    return {
        "stage": stage,
        "handoff": _shown(handoff),
        "questions": len(due),
        "batches": {batch_id: len(members) for batch_id, members in groups},
    }


# ------------------------------------------------------------------------------ import
def agent_name(batch_id: str) -> str:
    """The name a batch's agent answers under: unique per stage and batch by construction. It names
    the batch, not the agent - that each batch has a new agent is the orchestrator's rule (module
    doc, "Independence")."""
    return f"teaser-{batch_id}"


def _earlier_agents(
    site_id: str, stage: str, records: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> set[str]:
    """Every name that wrote or checked the site before `stage` (a reused or mistyped name is
    refused by it; one agent under two batch names is not visible here)."""
    return {
        records[earlier][site_id]["answered_by"]
        for earlier in STAGES[: STAGES.index(stage)]
        if site_id in records[earlier]
    }


def parse_answer(
    stage: str, site: C.Basis, state: Progress, text: str, *, fit: C.Fit
) -> dict[str, Any]:
    """The record of one answer: a writer's card and its mechanical problems, or a check."""
    if stage in WRITER_STAGES:
        written = A.parse_writer(text, site)
        return {
            "kind": "write",
            "written": written.text,
            "card": written.card,
            "basis": list(written.basis),
            "problems": C.problems(written.card, site, fit=fit),
        }
    checked = A.parse_checker(text, site)
    assert state.writer is not None
    return {"kind": "check", "card": state.card, **checked.to_dict()}


def import_stage(run: Path, stage: str, *, fit: C.Fit = V.card_fit) -> dict[str, Any]:
    """Every answer of one stage's round: validated, prompt-matched, parsed, recorded."""
    record = _round(run, stage)
    if record is None:
        raise RunError(f"stage {stage} was never exported")
    handoff = _resolve(Path(record["handoff"]))
    check = OH.validate(handoff)
    if not check.ok:
        raise RunError(
            f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
            "answer is validated before anything is imported"
        )
    manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
    asked = {(b, site) for b, members in record["batches"].items() for site in members}
    if set(manifest) != asked:
        raise RunError(f"{record['handoff']}: the manifest is not the round's record")
    sites = bases(run)
    records = stage_records(run, before=stage)
    current = {site: progress(site, records) for site in sites}
    rows: list[dict[str, Any]] = []
    for (batch_id, site_id), line in sorted(manifest.items(), key=lambda kv: kv[0][1]):
        state = current[site_id]
        if state.status != DUE or state.stage != stage:
            raise RunError(f"{site_id} is not due at {stage}: it is {state.status} {state.stage}")
        prompt = prompt_for(stage, sites[site_id], state)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise RunError(f"{batch_id}/{site_id}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=site_id,
                                prompt=prompt)  # fmt: skip
        if stage in CHECKER_STAGES:
            others = _earlier_agents(site_id, stage, records)
            if answer.answered_by in others:
                raise RunError(
                    f"{batch_id}/{site_id}: {answer.answered_by} wrote or checked this site before "
                    "- a check is an independent agent's; have the batch answered again under its "
                    "own name"
                )
        try:
            parsed = parse_answer(stage, sites[site_id], state, answer.text, fit=fit)
        except A.AnswerError as exc:
            raise RunError(
                f"{batch_id}/{site_id}: malformed answer ({exc}) - `check-answer` refuses it; "
                "delete the answer file and have the batch agent answer it again"
            ) from exc
        rows.append(
            {
                "site_id": site_id,
                "stage": stage,
                "batch_id": batch_id,
                "handoff": record["handoff"],
                "answered_by": answer.answered_by,
                "answered_at": answer.answered_at,
                "prompt_sha256": line["prompt_sha256"],
                **parsed,
            }
        )
    write_jsonl(run / f"STAGE-{stage}.jsonl", rows)
    if stage in WRITER_STAGES:
        failed = sum(1 for row in rows if row["problems"])
        return {"stage": stage, "answers": len(rows), "mechanical_failures": failed}
    verdicts = Counter(row["verdict"] for row in rows)
    return {"stage": stage, "answers": len(rows), "verdicts": dict(sorted(verdicts.items()))}


# ------------------------------------------------------------------------------ the agent's aids
def check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str, *, fit: C.Fit = V.card_fit
) -> dict[str, Any]:
    """The shape of one answer, and for a card its mechanical problems - nothing is recorded."""
    record = _round_of_handoff(run, handoff)
    stage = record["stage"]
    if label not in record["batches"].get(batch_id, []):
        raise RunError(f"{batch_id}/{label} is no question of {handoff}")
    if stage == JUDGE_STAGE:
        try:
            A.parse_judge(text)
        except A.AnswerError as exc:
            return {"ok": False, "problems": [str(exc)]}
        return {"ok": True, "problems": []}
    site = bases(run)[label]
    state = progress(label, stage_records(run, before=stage))
    try:
        parsed = parse_answer(stage, site, state, text, fit=fit)
    except A.AnswerError as exc:
        return {"ok": False, "problems": [str(exc)]}
    if parsed["kind"] == "write":
        return {
            "ok": not parsed["problems"],
            "problems": parsed["problems"],
            "card": parsed["card"],
            "length": len(parsed["card"]),
        }
    return {"ok": True, "problems": [], "verdict": parsed["verdict"]}


_BRIEF_HEAD = {
    "writer": (
        "You are Opus writer {batch} of lane WB (teaser cards). You write {count} card(s), each for "
        "another site. Write each one on its own, as if it were the only one. Everything a card may "
        "say is in its prompt: no web research, no memory of the site."
    ),
    "checker": (
        "You are Opus checker {batch} of lane WB (teaser cards). You check {count} card(s) written "
        "by another agent, each for another site. Check each one on its own, only against the "
        "sentences in its prompt - not against what you know about the site."
    ),
    "judge": (
        "You are Opus judge {batch} of the lane-WB pilot. You check {count} card(s) against "
        "sources on the web, each on its own. Every verdict rests on a page you opened and quote."
    ),
}

BRIEF = """{head}

This batch needs an agent that has answered no other batch of lane WB (no card written, checked \
or judged): if you have, stop now and say so - the independence of every check rests on it.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the \
repository - no other batch, nothing else under output/ or docs/, no database, no git history.

Skip every question whose "answer_path" (in the manifest, relative to {handoff}) exists already: an earlier agent of this batch recorded it, and an answer is written once.

For each other question:
1. Read {handoff}/<prompt_path>.
2. {task}
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it (nothing is recorded by this):
   ./.venv/Scripts/python.exe scripts/remediation/teaser/run.py check-answer --run {run} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   {fix}
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {agent} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""

_BRIEF_TASK = {
    "writer": "Write the card exactly as the prompt asks.",
    "checker": "List the card's claims and decide, exactly as the prompt asks.",
    "judge": "Research on the web and decide each claim, exactly as the prompt asks.",
}
_BRIEF_FIX = {
    "writer": (
        'It prints "ok" and the card\'s final text and length, or the problems (length, numbers '
        "that are not in the description, the site's name, forbidden characters, ...). Rewrite "
        'the card until it prints "ok": true - still only from the prompt\'s sentences.'
    ),
    "checker": (
        "It prints the shape problem, if any: fix the shape (for example a PASS with an "
        "unsupported claim is a FAIL), never your finding."
    ),
    "judge": "It prints the shape problem, if any: fix the shape, never the finding.",
}


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the Opus agent that answers one batch."""
    record = _round_of_handoff(run, handoff)
    if batch_id not in record["batches"]:
        raise RunError(f"{batch_id} is no batch of {handoff}")
    stage = record["stage"]
    kind = "judge" if stage == JUDGE_STAGE else ("writer" if stage in WRITER_STAGES else "checker")
    shown = _shown(handoff)
    return BRIEF.format(
        head=_BRIEF_HEAD[kind].format(batch=batch_id, count=len(record["batches"][batch_id])),
        task=_BRIEF_TASK[kind],
        fix=_BRIEF_FIX[kind],
        batch=batch_id,
        stage=stage,
        agent=agent_name(batch_id),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
    )


# ------------------------------------------------------------------------------ status, outcomes
def status(run: Path) -> dict[str, Any]:
    current = states(run)
    counts = Counter(
        f"{p.status} {p.stage}" if p.status == DUE else p.status for p in current.values()
    )
    return {
        "run": run.name,
        "sites": len(current),
        "states": dict(sorted(counts.items())),
        "rounds": [r["stage"] for r in read_rounds(run)],
    }


def outcome_rows(run: Path, *, ai_system: str = M.AI_SYSTEM) -> list[dict[str, Any]]:
    """The final result of every site of the run: an accepted card with its provenance, or a
    clear - a failed site, or a listed site without a description whose card is to be cleared."""
    sites = bases(run)
    current = states(run)
    due = sorted(site for site, p in current.items() if p.status == DUE)
    if due:
        raise RunError(f"{len(due)} site(s) are still due: {due[:3]} - finish every stage first")
    rows: list[dict[str, Any]] = []
    for site_id in sorted(sites):
        site, state = sites[site_id], current[site_id]
        common = {
            "site_id": site_id,
            "name": site.name,
            "desc_sha256": site.desc_sha256,
            "attempts": len(state.findings) + (1 if state.status == ACCEPTED else 0),
            "findings": [{"card": f.card, "reasons": list(f.reasons)} for f in state.findings],
        }
        if state.status == ACCEPTED:
            writer, check = state.writer, state.check
            assert writer is not None and check is not None
            rows.append(
                {
                    **common,
                    "status": ACCEPTED,
                    "reason": None,
                    "card": writer["card"],
                    "writer": {k: writer[k] for k in ("stage", "answered_by", "answered_at")},
                    "provenance": CP.build(
                        run=run.name,
                        ai_system=ai_system,
                        card=writer["card"],
                        description=site.description,
                        stage=check["stage"],
                        checker=check["answered_by"],
                        checked_at=check["answered_at"],
                        claims=check["claims"],
                    ),
                }
            )
        else:
            rows.append(
                {
                    **common,
                    "status": CLEARED,
                    "reason": "failed-after-two-rewrites",
                    "card": None,
                    "writer": None,
                    "provenance": None,
                }
            )
    for listed in _pinned_jsonl(run, "LISTED.jsonl", "listed_sha256"):
        if listed["reason"] == NO_DESCRIPTION and listed["card"] is not None:
            rows.append(
                {
                    "site_id": listed["site_id"],
                    "name": listed["name"],
                    "desc_sha256": listed["desc_sha256"],
                    "attempts": 0,
                    "findings": [],
                    "status": CLEARED,
                    "reason": NO_DESCRIPTION,
                    "card": None,
                    "writer": None,
                    "provenance": None,
                }
            )
    return sorted(rows, key=lambda r: r["site_id"])


def outcomes_markdown(run: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    accepted = [r for r in rows if r["status"] == ACCEPTED]
    lengths = [len(r["card"]) for r in accepted]
    attempts = Counter(r["attempts"] for r in accepted)
    reasons = Counter(r["reason"] for r in rows if r["status"] == CLEARED)
    lines = [
        f"# Lane WB run `{run.name}` - outcomes",
        "",
        f"Written {_now()} by `scripts/remediation/teaser/run.py outcomes`.",
        "",
        f"- sites: {len(rows)}; **accepted {len(accepted)}**, cleared "
        f"{len(rows) - len(accepted)} ({dict(sorted(reasons.items()))})",
        f"- accepted at attempt 1/2/3: {attempts.get(1, 0)}/{attempts.get(2, 0)}/"
        f"{attempts.get(3, 0)}",
    ]
    if lengths:
        lines.append(
            f"- card length: min {min(lengths)}, median {statistics.median(lengths)}, max "
            f"{max(lengths)} characters"
        )
    lines += ["", "| site | status | card |", "|---|---|---|"]
    for r in rows:
        card = (r["card"] or "").replace("|", "\\|")
        lines.append(f"| {r['name']} (`{r['site_id'][:8]}`) | {r['status']} | {card} |")
    return "\n".join(lines) + "\n"


def outcomes(run: Path) -> dict[str, Any]:
    rows = outcome_rows(run)
    digest = write_jsonl(run / "OUTCOMES.jsonl", rows)
    (run / "OUTCOMES.md").write_text(outcomes_markdown(run, rows), encoding="utf-8", newline="\n")
    counts = Counter(f"{r['status']} {r['reason']}" if r["reason"] else r["status"] for r in rows)
    return {"outcomes": len(rows), "sha256": digest, "counts": dict(sorted(counts.items()))}


def read_outcomes(run: Path) -> list[dict[str, Any]]:
    path = run / "OUTCOMES.jsonl"
    if not path.exists():
        raise RunError(f"{path} does not exist - run `outcomes` first")
    return read_jsonl(path)


# ------------------------------------------------------------------------------ the pilot judge
def export_judge(run: Path, handoff: Path) -> dict[str, Any]:
    """Every accepted card of the run to independent web judges (the pilot's measurement)."""
    if _round(run, JUDGE_STAGE) is not None:
        raise RunError("the judge round is exported already")
    target = _resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise RunError(f"{handoff} is not empty: a round gets a directory of its own")
    sites = bases(run)
    accepted = [r for r in read_outcomes(run) if r["status"] == ACCEPTED]
    ordered = sorted(r["site_id"] for r in accepted)
    cards = {r["site_id"]: r["card"] for r in accepted}
    groups = [
        (f"{JUDGE_STAGE}-{n:03d}", ordered[i : i + JUDGE_BATCH_SIZE])
        for n, i in enumerate(range(0, len(ordered), JUDGE_BATCH_SIZE), start=1)
    ]
    for batch_id, members in groups:
        for site_id in members:
            site = sites[site_id]
            OH.export(
                target,
                batch_id=batch_id,
                stage=JUDGE_STAGE,
                label=site_id,
                field="card_description",
                prompt=P.judge_prompt(site.name, site.country, cards[site_id]),
            )
    record = {
        "stage": JUDGE_STAGE,
        "handoff": _shown(handoff),
        "batches": dict(groups),
        "exported_at": _now(),
    }
    write_jsonl(run / "ROUNDS.jsonl", [*read_rounds(run), record])
    return {"judge_questions": len(ordered), "batches": {b: len(m) for b, m in groups}}


def judge_client() -> httpx.Client:
    """The pilot import's HTTP client: the audit's (`quotes.http_client`) under lane WB's own
    User-Agent, no personal data."""
    return Q.http_client(USER_AGENT)


@dataclass
class JudgeTally:
    """The pilot's count. `contradicted` has a proving quote; `contradicted_unproven` does not (a
    page that refused the machine, a PDF, a quote not found) and still fails the pilot until the
    card is fixed: a contradiction is never waved through as merely unproven."""

    claims: int = 0
    supported: int = 0
    contradicted: int = 0
    contradicted_unproven: int = 0
    unproven: int = 0
    wrong_cards: list[str] = field(default_factory=list)
    disputed_cards: list[str] = field(default_factory=list)

    @property
    def unproven_share(self) -> float:
        return self.unproven / self.claims if self.claims else 0.0

    @property
    def passed(self) -> bool:
        no_contradiction = self.contradicted == 0 and self.contradicted_unproven == 0
        return no_contradiction and self.unproven_share <= PILOT_MAX_UNPROVEN_SHARE


def import_judge(
    run: Path, *, client: httpx.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """Every judge answer: parsed, each cited page fetched once, each quote checked by machine."""
    record = _round(run, JUDGE_STAGE)
    if record is None:
        raise RunError("the judge round was never exported")
    handoff = _resolve(Path(record["handoff"]))
    check = OH.validate(handoff)
    if not check.ok:
        raise RunError(f"{record['handoff']}: not every judge answer is in, in shape, by Opus")
    sites = bases(run)
    cards = {r["site_id"]: r["card"] for r in read_outcomes(run) if r["status"] == ACCEPTED}
    writers = {site: set() for site in sites}  # every agent that wrote or checked the card
    for rows in stage_records(run).values():
        for site_id, row in rows.items():
            writers[site_id].add(row["answered_by"])
    parsed: dict[str, tuple[Any, tuple[A.Judged, ...]]] = {}
    for batch_id, members in record["batches"].items():
        for site_id in members:
            site = sites[site_id]
            prompt = P.judge_prompt(site.name, site.country, cards[site_id])
            answer = OH.read_answer(handoff, batch_id=batch_id, stage=JUDGE_STAGE, label=site_id,
                                    prompt=prompt)  # fmt: skip
            if answer.answered_by in writers[site_id]:  # a reused name; the agent: module doc
                raise RunError(f"{site_id}: the judge {answer.answered_by} worked on this card")
            try:
                parsed[site_id] = (answer, A.parse_judge(answer.text))
            except A.AnswerError as exc:
                raise RunError(f"{batch_id}/{site_id}: malformed judge answer ({exc})") from exc
    pages = run / "pages"
    urls = sorted({j.url for _, claims in parsed.values() for j in claims if j.url})
    own = client is None
    http = judge_client() if client is None else client
    try:
        Q.collect(urls, pages, http, now=_now, pace=pace)
    finally:
        if own:
            http.close()
    library = Q.Library(ROOT, pages)
    tally = JudgeTally()
    rows = []
    for site_id in sorted(parsed):
        answer, claims = parsed[site_id]
        results = []
        for judged in claims:
            tally.claims += 1
            outcome = None
            if judged.url is not None:
                outcome = Q.check_quote(
                    {"source": judged.url, "quote": judged.quote},
                    {"change_key": site_id, "evidence_files": []},
                    library,
                ).outcome
            proven = outcome == Q.FOUND
            if judged.verdict == "SUPPORTED" and proven:
                tally.supported += 1
            elif judged.verdict == "CONTRADICTED" and proven:
                tally.contradicted += 1
                if site_id not in tally.wrong_cards:
                    tally.wrong_cards.append(site_id)
            else:
                tally.unproven += 1
                if judged.verdict == "CONTRADICTED":
                    tally.contradicted_unproven += 1
                    if site_id not in tally.disputed_cards:
                        tally.disputed_cards.append(site_id)
            results.append({**asdict(judged), "quote_outcome": outcome, "proven": proven})
        rows.append(
            {
                "site_id": site_id,
                "name": sites[site_id].name,
                "card": cards[site_id],
                "judge": answer.answered_by,
                "claims": results,
            }
        )
    write_jsonl(run / "JUDGE.jsonl", rows)
    summary = {
        "cards": len(rows),
        "claims": tally.claims,
        "supported": tally.supported,
        "contradicted": tally.contradicted,
        "contradicted_unproven": tally.contradicted_unproven,
        "unproven": tally.unproven,
        "unproven_share": round(tally.unproven_share, 4),
        "wrong_cards": tally.wrong_cards,
        "disputed_cards": tally.disputed_cards,
        "pilot": "PASS" if tally.passed else "FAIL",
    }
    (run / "JUDGE.md").write_text(
        judge_markdown(run, rows, summary), encoding="utf-8", newline="\n"
    )
    return summary


def judge_markdown(run: Path, rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> str:
    lines = [
        f"# Lane WB pilot `{run.name}` - the independent web judge",
        "",
        f"Written {_now()} by `run.py judge-import`. Gate: no claim CONTRADICTED - with a proving "
        "quote or without one (a page that refused the machine, a PDF, a quote not found) - and "
        f"at most {PILOT_MAX_UNPROVEN_SHARE:.0%} of all claims without a proving quote.",
        "",
        f"**PILOT: {summary['pilot']}** - {summary['cards']} cards, {summary['claims']} claims: "
        f"{summary['supported']} supported, {summary['contradicted']} contradicted with a proving "
        f"quote, {summary['contradicted_unproven']} contradicted without a proving quote, "
        f"{summary['unproven']} unproven in all ({summary['unproven_share']:.1%}).",
        "",
        "## Every contradiction (read each before anything else)",
        "",
    ]
    contradictions = [
        (row, claim)
        for row in rows
        for claim in row["claims"]
        if claim["verdict"] == "CONTRADICTED"
    ]
    for row, claim in contradictions:
        mark = "CONTRADICTED" if claim["proven"] else "CONTRADICTED (not proven)"
        lines.append(
            f"- {row['name']} (`{row['site_id'][:8]}`) {mark}: {claim['claim']} - {claim['url']} "
            f"({claim['quote_outcome']})"
        )
    if not contradictions:
        lines.append("None.")
    lines.append("")
    for row in rows:
        lines += [f"## {row['name']} (`{row['site_id'][:8]}`)", "", f"> {row['card']}", ""]
        for claim in row["claims"]:
            mark = claim["verdict"] if claim["proven"] else f"{claim['verdict']} (not proven)"
            source = f" - {claim['url']} ({claim['quote_outcome']})" if claim["url"] else ""
            lines.append(f"- **{mark}**: {claim['claim']}{source}")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _read_production(path: Path) -> None:
    write_tagged_export(export_script(), path)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands: dict[str, argparse.ArgumentParser] = {}
    for name, helps in (
        ("select", "read production (read-only) and fix the run's candidates"),
        ("export", "one stage's questions into a new handoff directory"),
        ("import", "validate, parse and record one stage's answers"),
        ("check-answer", "the shape (and a card's mechanical checks) of one answer"),
        ("brief", "the instruction of one batch's Opus agent"),
        ("status", "where every site of the run stands"),
        ("outcomes", "OUTCOMES.jsonl and OUTCOMES.md, once every site is settled"),
        ("judge-export", "the pilot's cards to independent web judges"),
        ("judge-import", "the judges' answers, quotes fetched and checked: JUDGE.md"),
    ):
        commands[name] = sub.add_parser(name, help=helps)
        commands[name].add_argument("--run", required=True, type=Path)
    for name in ("export", "check-answer", "brief", "judge-export"):
        commands[name].add_argument("--handoff", required=True, type=Path)
    for name in ("export", "import"):
        commands[name].add_argument("--stage", required=True, choices=STAGES)
    for name in ("check-answer", "brief"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", required=True, type=Path)
    commands["select"].add_argument("--sites", type=Path, help="restrict to these site ids")
    commands["select"].add_argument("--pilot", type=int, help="draw this many candidates")
    commands["select"].add_argument("--seed", type=int, help="the pilot draw's seed")
    commands["select"].add_argument("--exclude-run", type=Path, action="append", default=[])
    commands["select"].add_argument(
        "--basis", action="append", choices=BASES, help="ask only candidates of these bases"
    )
    args = parser.parse_args(argv)
    run = _resolve(args.run)
    try:
        if args.command == "select":
            if (args.pilot is None) != (args.seed is None):
                raise RunError("a pilot needs both --pilot and --seed")
            _print(
                select(
                    run,
                    read=_read_production,
                    sites_file=None if args.sites is None else _resolve(args.sites),
                    pilot=None if args.pilot is None else (args.pilot, args.seed),
                    exclude=args.exclude_run,
                    basis=None if args.basis is None else set(args.basis),
                )
            )
        elif args.command == "export":
            _print(export_stage(run, args.stage, args.handoff))
        elif args.command == "import":
            _print(import_stage(run, args.stage))
        elif args.command == "check-answer":
            text = _resolve(args.text_file).read_bytes().decode("utf-8")
            result = check_answer(run, args.handoff, args.batch_id, args.label, text)
            _print(result)
            return 0 if result["ok"] else 1
        elif args.command == "brief":
            print(brief(run, args.handoff, args.batch_id))
        elif args.command == "status":
            _print(status(run))
        elif args.command == "outcomes":
            _print(outcomes(run))
        elif args.command == "judge-export":
            _print(export_judge(run, args.handoff))
        else:
            result = import_judge(run)
            _print(result)
            return 0 if result["pilot"] == "PASS" else 1
    except (RunError, OH.HandoffError, Q.AuditError, PlanError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
