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
    ... the same for check, rewrite1, check1, rewrite2, check2, verify, rewrite-v, check-v, verify2
        (a stage nobody is due for is skipped: `export` says so; the import of a verify stage
        fetches every cited page once and checks every quote by machine - a page whose fetch
        failed for a reason that may pass is tried again at every import, and the import lists
        those still failing as `transient_failures`: import again before the next export)
    $T status --run R                                      who is due where, accepted, cleared
    $T outcomes --run R                                    OUTCOMES.jsonl, DESCRIPTION_DEFECTS.jsonl
    $T judge-export --run R --handoff $H-judge             pilot gate: a fresh independent web judge
    $T judge-import --run R                                quotes fetched and checked: JUDGE.md

## The stages

`write` asks every candidate; `check` asks a different agent about every card that passed the
mechanical checks (`contract.problems`), one checker per writer batch; a card that failed either goes
to `rewrite1` with its findings and is checked by a new checker in `check1`; once more in `rewrite2`
and `check2`; after that the site gets no card (cleared, `failed-after-two-rewrites`).

Every card a checker accepted is then **verified** on the web (`verify`, owner O2: "natuerlich
muessen sie inhaltlich stimmen"): an independent web judge - the pilot judge's prompt, answer shape
and machine quote check - decides each claim SUPPORTED / CONTRADICTED / UNVERIFIABLE against a page
it quotes, 5 cards per batch, listing at least as many claims as the accepting check did
(`claims_floor`). A quote proves a claim only when the machine found it on a page lane WC's source
rule admits (`prove_claims`: never an AI aggregator, a Wikipedia mirror, a blocked domain or this
project's site - such a page is not even fetched). The card is VERIFIED when no claim is
contradicted (proven or not), at most `CP.MAX_UNPROVEN_CLAIMS` claim lacks a proving quote and the
central claim (the verifier's first) has one; CONTRADICTED when any claim is contradicted; else
UNPROVEN (`card_verification`). A card not VERIFIED gets one rewrite (`rewrite-v`: the writer sees
the contradicted claims with their pages and quotes, and may correct one only from the description
or a web fact - a contradicting quote the machine found on an admitted page, never of the central
claim), the ordinary check (`check-v`) and a new verifier (`verify2`); a card still not VERIFIED
clears the site (`contradicted-after-verify`, `unproven-after-verify`; a rewrite that fails the
mechanical checks or `check-v`: `failed-after-verify-rewrite`). Each stage's round is exported once,
into a handoff directory of its own; the import rebuilds every prompt from the run's files and
refuses an answer to any other.

**The records tie every judgement to its card**: each check and verification records the card it
judged, and a site's state counts it only for the card of the writer record it follows
(`judging`); an import that would record another card under a later stage's judgement (a stage
imported again with other answers) is refused before it writes. The provenance repeats the tie:
its `verify.text_sha256` is the text the verifier judged, which `card_provenance.validate` holds to
the card's.

**Independence is a process rule, kept by the orchestrator**: every batch of every stage (and of the
judge) is answered by a new agent, and the brief tells an agent that answered another batch of lane
WB to stop. The import cannot see an agent - `answered_by` is the batch's name, `teaser-<batch_id>`,
and batch ids carry their stage - so its refusal of a checker or verifier whose name wrote, checked
or verified the site before (and of a pilot judge whose name answered anything in the run) catches a
reused or mistyped name, never one agent reused under two batch names.

## The run's files (`output/remediation/teaser/runs/<run>/`, gitignored: they hold description text)

`EXPORT.jsonl` (the read-only production export `select` read), `RUN.json` (the selection, pinned by
sha256), `SITES.jsonl` (each candidate's fact basis inputs), `LISTED.jsonl` (every curated site that
is not a candidate, and why), `ROUNDS.jsonl`, `STAGE-<stage>.jsonl`, `pages/` (each admitted page a
verifier or judge cited, fetched once - again only after a failure that may pass, `may_pass`),
`OUTCOMES.jsonl`, `OUTCOMES.md` and `DESCRIPTION_DEFECTS.jsonl`; for
the pilot `JUDGE.jsonl` and `JUDGE.md`.
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
from wc.answers import url_problem  # noqa: E402 - lane WC's source rule, by code

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
#: Cards per web judge batch: a verifier's (stages verify, verify2) and the pilot judge's.
JUDGE_BATCH_SIZE = 5
#: The checker rounds: a writer stage, then its checker stage.
CHECK_ROUNDS = (("write", "check"), ("rewrite1", "check1"), ("rewrite2", "check2"))
#: The web verification of every accepted card, and its one rewrite round.
FIRST_VERIFY, SECOND_VERIFY = CP.FIRST_VERIFY, CP.SECOND_VERIFY
VERIFY_REWRITE, VERIFY_CHECK = "rewrite-v", CP.VERIFY_REWRITE_CHECK
WRITER_STAGES = (*(writer for writer, _ in CHECK_ROUNDS), VERIFY_REWRITE)
CHECKER_STAGES = (*(checker for _, checker in CHECK_ROUNDS), VERIFY_CHECK)
VERIFY_STAGES = (FIRST_VERIFY, SECOND_VERIFY)
STAGES = (
    *(stage for pair in CHECK_ROUNDS for stage in pair),
    FIRST_VERIFY,
    VERIFY_REWRITE,
    VERIFY_CHECK,
    SECOND_VERIFY,
)
JUDGE_STAGE = "judge"
#: A card's verification (`card_verification`): VERIFIED is the provenance's; the other two send
#: the card to the one rewrite round, or clear the site after it.
VERIFIED = CP.VERIFIED
CONTRADICTED = "CONTRADICTED"
UNPROVEN = "UNPROVEN"
#: Why a site the run asked is cleared (OUTCOMES.jsonl "reason").
FAILED_REWRITES = "failed-after-two-rewrites"
FAILED_VERIFY_REWRITE = "failed-after-verify-rewrite"
CONTRADICTED_AFTER_VERIFY = "contradicted-after-verify"
UNPROVEN_AFTER_VERIFY = "unproven-after-verify"
#: Whose text a contradicted description sentence is (DESCRIPTION_DEFECTS.jsonl "owner_lane"): a
#: Phase-4 text is lane WA's (Phase 4, scope v3), a sentence-checked March text lane WC's.
OWNER_LANE = {**dict.fromkeys(sorted(BASIS_LANES), "WA"), SENTENCE_CHECKED: "WC"}
#: The web requests of the verify imports and of the pilot judge's: the lanes' one User-Agent, no
#: personal data. The bare `AncientMapRemediation/1.0 (research)` drew 403 from Wikimedia through
#: httpx on every page of pilot wb-pilot-2026-09-26 (its robot policy wants a contact; the project
#: URL is one).
USER_AGENT = research_web.USER_AGENT
#: The pilot gate (sealed with the runbook), on the pilot's final (VERIFIED) cards, by a fresh judge
#: who is no verifier of the run: no claim CONTRADICTED - with a proving quote or without one - and
#: at most this share of all claims left without a proving quote (UNVERIFIABLE, or a quote the
#: machine did not find).
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
        "contract": {
            "min_chars": C.MIN_CHARS,
            "max_chars": C.MAX_CHARS,
            "max_unproven_claims": CP.MAX_UNPROVEN_CLAIMS,
        },
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
    """Where one site stands: due at a stage, accepted, or cleared - with its failed cards. `writer`
    and `check` are the records of the card at hand, `verified` the site's verifications so far (the
    first one's claims drive the rewrite after it), `reason` why a cleared site is cleared."""

    status: str
    stage: str | None
    findings: tuple[P.Finding, ...] = ()
    writer: Mapping[str, Any] | None = None
    check: Mapping[str, Any] | None = None
    verified: tuple[Mapping[str, Any], ...] = ()
    reason: str | None = None

    @property
    def card(self) -> str | None:
        return None if self.writer is None else self.writer["card"]

    @property
    def verify(self) -> Mapping[str, Any] | None:
        """The last verification of the site."""
        return self.verified[-1] if self.verified else None


DUE = "due"
ACCEPTED = "accepted"
CLEARED = "cleared"


def judging(
    site_id: str, judged: Mapping[str, Any] | None, written: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    """`judged` - a check or a verification of the site, or `None` - refused unless it judged the
    very card the writer record before it holds. The records alone tie a check and a verification to
    their card: a stage imported again with other answers once a later stage judged the old card
    (the import refuses that, `import_stage`), or a file edited by hand, would otherwise let the
    judgement of one text count for another."""
    if judged is not None and judged["card"] != written["card"]:
        raise RunError(
            f"{site_id}: STAGE-{judged['stage']} judged another card than STAGE-{written['stage']} "
            f"holds - {written['stage']} was imported again with other answers after "
            f"{judged['stage']} judged its card; the earlier record's answer (`written`) is the one "
            "the later stages judged"
        )
    return judged


def progress(site_id: str, records: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Progress:
    """The site's state, derived from the imported records alone (module doc, "The stages"); every
    check and verification on the path judged the card of the writer record it follows
    (`judging`)."""
    findings: list[P.Finding] = []
    for writer_stage, checker_stage in CHECK_ROUNDS:
        written = records[writer_stage].get(site_id)
        if written is None:
            return Progress(DUE, writer_stage, tuple(findings))
        if written["problems"]:
            findings.append(P.Finding(written["card"], P.findings_of(written)))
            continue
        checked = judging(site_id, records[checker_stage].get(site_id), written)
        if checked is None:
            return Progress(DUE, checker_stage, tuple(findings), writer=written)
        if checked["verdict"] == A.PASSED:
            return verification_progress(site_id, records, findings, written, checked)
        findings.append(P.Finding(written["card"], P.findings_of(checked)))
    return Progress(CLEARED, None, tuple(findings), reason=FAILED_REWRITES)


def verification_progress(
    site_id: str,
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    findings: list[P.Finding],
    written: Mapping[str, Any],
    checked: Mapping[str, Any],
) -> Progress:
    """A card the checker accepted: verified on the web; a card not VERIFIED gets one rewrite
    (`rewrite-v`), its check (`check-v`) and a new verifier (`verify2`), else the site is cleared."""
    first = judging(site_id, records[FIRST_VERIFY].get(site_id), written)
    if first is None:
        return Progress(DUE, FIRST_VERIFY, tuple(findings), written, checked)
    if first["verdict"] == VERIFIED:
        return Progress(ACCEPTED, FIRST_VERIFY, tuple(findings), written, checked, (first,))
    findings = [*findings, P.Finding(written["card"], P.findings_of(first))]
    rewritten = records[VERIFY_REWRITE].get(site_id)
    if rewritten is None:
        return Progress(DUE, VERIFY_REWRITE, tuple(findings), written, checked, (first,))
    cleared = {"verified": (first,), "reason": FAILED_VERIFY_REWRITE}
    if rewritten["problems"]:
        findings.append(P.Finding(rewritten["card"], P.findings_of(rewritten)))
        return Progress(CLEARED, None, tuple(findings), **cleared)
    rechecked = judging(site_id, records[VERIFY_CHECK].get(site_id), rewritten)
    if rechecked is None:
        return Progress(DUE, VERIFY_CHECK, tuple(findings), rewritten, None, (first,))
    if rechecked["verdict"] != A.PASSED:
        findings.append(P.Finding(rewritten["card"], P.findings_of(rechecked)))
        return Progress(CLEARED, None, tuple(findings), **cleared)
    second = judging(site_id, records[SECOND_VERIFY].get(site_id), rewritten)
    if second is None:
        return Progress(DUE, SECOND_VERIFY, tuple(findings), rewritten, rechecked, (first,))
    if second["verdict"] == VERIFIED:
        return Progress(
            ACCEPTED, SECOND_VERIFY, tuple(findings), rewritten, rechecked, (first, second)
        )
    findings.append(P.Finding(rewritten["card"], P.findings_of(second)))
    reason = (
        CONTRADICTED_AFTER_VERIFY if second["verdict"] == CONTRADICTED else UNPROVEN_AFTER_VERIFY
    )
    return Progress(CLEARED, None, tuple(findings), verified=(first, second), reason=reason)


def states(run: Path) -> dict[str, Progress]:
    records = stage_records(run)
    return {site_id: progress(site_id, records) for site_id in bases(run)}


# ------------------------------------------------------------------------------ the verification
def proves(claim: Mapping[str, Any]) -> bool:
    """Whether a judged claim is proven: SUPPORTED, with a quote the machine found on its page - a
    page lane WC's source rule admits (`prove_claims`)."""
    return claim["verdict"] == "SUPPORTED" and claim["proven"]


def card_verification(claims: Sequence[Mapping[str, Any]]) -> str:
    """A card's verification from its judged claims (CARD_DESCRIPTIONS.md, section 2.1):
    CONTRADICTED when any claim is contradicted - with a proving quote or without one (a page that
    refused the machine, a PDF, a quote mis-copied): a contradiction is never waved through as
    merely unproven; else VERIFIED when at most `CP.MAX_UNPROVEN_CLAIMS` claim lacks a proving quote
    and the central claim - the judge's first, what the site is (`prompts.judge_prompt`) - has one;
    else UNPROVEN."""
    if any(claim["verdict"] == CONTRADICTED for claim in claims):
        return CONTRADICTED
    unproven = [claim for claim in claims if not proves(claim)]
    if len(unproven) > CP.MAX_UNPROVEN_CLAIMS or not proves(claims[0]):
        return UNPROVEN
    return VERIFIED


def contradicted_claims(verified: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The claims a verifier found contradicted, proven or not, in its order."""
    return [claim for claim in verified["claims"] if claim["verdict"] == CONTRADICTED]


def unproven_claims(verified: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The claims a verifier neither proved nor contradicted (UNVERIFIABLE, or SUPPORTED with a
    quote the machine did not find), in its order."""
    return [
        claim
        for claim in verified["claims"]
        if claim["verdict"] != CONTRADICTED and not proves(claim)
    ]


def web_facts(verified: Mapping[str, Any]) -> tuple[C.WebFact, ...]:
    """What the rewrite after a failed verification may correct a claim with, beside the
    description: each quote of a CONTRADICTED claim that the machine found on its page - `proven`,
    so from a page lane WC's source rule admits (`prove_claims`) - numbered `W1`, `W2`, ... in the
    verifier's order. Never one of the central claim (the verifier's first: what the site is, and
    where): a page that says the site is something else may describe a namesake, so the identity is
    never corrected from the web. Whether the page is reputable beyond the source rule is the
    checker's decision (`prompts.REPUTABLE`); a web fact the checker's claims cite is recorded in
    the provenance (`web_facts`)."""
    usable = [
        claim
        for claim in verified["claims"][1:]
        if claim["verdict"] == CONTRADICTED and claim["proven"]
    ]
    return tuple(
        C.WebFact(f"W{number}", claim["url"], claim["quote"])
        for number, claim in enumerate(usable, start=1)
    )


def recorded_web_facts(record: Mapping[str, Any], state: Progress) -> tuple[C.WebFact, ...]:
    """The web facts a `rewrite-v` or `check-v` record was asked with (recorded at its import),
    refused unless the first verification still offers exactly these: a change of the code that
    offers them between two imports (a merge) would renumber the W ids, and the provenance would
    record a quote the checker never saw under its id."""
    recorded = tuple(C.WebFact(**fact) for fact in record["web_facts"])
    if recorded != web_facts(state.verified[0]):
        raise RunError(
            f"{record['site_id']}: STAGE-{record['stage']} was asked with web facts "
            f"{[fact.id for fact in recorded]} that the first verification no longer offers as "
            "they were - the code that offers them changed since; restore it for this run"
        )
    return recorded


def basis_at(stage: str, site: C.Basis, state: Progress) -> C.Basis:
    """The fact basis a stage's question shows: with the first verification's web facts in the
    rewrite after it and, as that rewrite's record holds them, in its check; the description alone
    everywhere else."""
    if stage == VERIFY_REWRITE:
        return site.with_web(web_facts(state.verified[0]))
    if stage == VERIFY_CHECK:
        assert state.writer is not None
        return site.with_web(recorded_web_facts(state.writer, state))
    return site


def prompt_for(stage: str, site: C.Basis, state: Progress) -> str:
    """The exact question of one site at one stage."""
    shown = basis_at(stage, site, state)
    if stage == "write":
        return P.writer_prompt(site)
    if stage == VERIFY_REWRITE:
        assert state.card is not None
        first = state.verified[0]
        return P.verify_rewrite_prompt(
            shown, state.card, contradicted_claims(first), unproven_claims(first)
        )
    if stage in WRITER_STAGES:
        return P.rewrite_prompt(site, state.findings)
    assert state.card is not None
    if stage in VERIFY_STAGES:
        return P.judge_prompt(site.name, site.country, state.card)
    return P.checker_prompt(shown, state.card)


# ------------------------------------------------------------------------------ export
def _batches(stage: str, due: Mapping[str, Progress]) -> list[tuple[str, list[str]]]:
    """Batches of one stage: writer stages by site id in chunks of 15, verify stages in chunks of 5
    (each card researched on the web); a checker stage keeps each writer batch together, so one
    checker checks one writer's cards."""
    if stage in WRITER_STAGES or stage in VERIFY_STAGES:
        size = JUDGE_BATCH_SIZE if stage in VERIFY_STAGES else BATCH_SIZE
        ordered = sorted(due)
        groups = [ordered[i : i + size] for i in range(0, len(ordered), size)]
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
    """Every name that wrote, checked or verified the site before `stage` (a reused or mistyped
    name is refused by it; one agent under two batch names is not visible here)."""
    return {
        records[earlier][site_id]["answered_by"]
        for earlier in STAGES[: STAGES.index(stage)]
        if site_id in records[earlier]
    }


def parse_answer(
    stage: str, site: C.Basis, state: Progress, text: str, *, fit: C.Fit
) -> dict[str, Any]:
    """The record of one answer: a writer's card and its mechanical problems (after a failed
    verification also the description sentences its contradicted claims repeat), or a check - in
    the rewrite after a failed verification and its check with the web facts the question showed
    (`web_facts`). A verifier's answer needs its pages: `import_stage` records it
    (`verify_record`)."""
    shown = basis_at(stage, site, state)
    offered = [asdict(fact) for fact in shown.web]
    if stage in WRITER_STAGES:
        if stage == VERIFY_REWRITE:
            contradicted = len(contradicted_claims(state.verified[0]))
            written = A.parse_verify_writer(text, shown, contradicted)
        else:
            written = A.parse_writer(text, shown)
        record: dict[str, Any] = {
            "kind": "write",
            "written": written.text,
            "card": written.card,
            "basis": list(written.basis),
            "problems": C.problems(written.card, shown, fit=fit),
        }
        if stage == VERIFY_REWRITE:
            record.update(repeats=list(written.repeats), web_facts=offered)
        return record
    checked = A.parse_checker(text, shown)
    assert state.writer is not None
    record = {"kind": "check", "card": state.card, **checked.to_dict()}
    if stage == VERIFY_CHECK:
        record["web_facts"] = offered
    return record


#: The quote outcome of a page lane WC's source rule refuses (`wc.answers.url_problem`: this
#: project's site, an AI aggregator, a Wikipedia mirror, a blocked domain, a URL with utm_
#: tracking) - never fetched, and never a proof: such a page may repeat the very text under test.
SOURCE_REFUSED = "source refused"


def cited_pages(claims: Iterable[A.Judged]) -> list[str]:
    """The pages web judges' claims cite that may prove anything - those lane WC's source rule
    admits; only these are fetched."""
    return sorted({j.url for j in claims if j.url is not None and url_problem(j.url) is None})


def prove_claims(
    site_id: str, claims: Sequence[A.Judged], library: Q.Library
) -> list[dict[str, Any]]:
    """Each claim of a web judge with its quote checked by machine on the page it cites (the Opus
    re-verification's check, `opus_audit/quotes.py`): `proven` only when the page holds the quote
    and lane WC's source rule admits the page (`SOURCE_REFUSED` else)."""
    results = []
    for judged in claims:
        if judged.url is None:
            outcome = None
        elif (refused := url_problem(judged.url)) is not None:
            outcome = f"{SOURCE_REFUSED}: {refused}"
        else:
            outcome = Q.check_quote(
                {"source": judged.url, "quote": judged.quote},
                {"change_key": site_id, "evidence_files": []},
                library,
            ).outcome
        proven = outcome == Q.FOUND
        results.append({**asdict(judged), "quote_outcome": outcome, "proven": proven})
    return results


#: The HTTP status of a rate limit: like no answer at all and a 5xx server error, a failure that
#: may pass (`may_pass`).
TOO_MANY_REQUESTS = 429


def may_pass(meta: Mapping[str, Any]) -> bool:
    """Whether a kept fetch failed for a reason that may pass: no answer at all (a timeout, a
    refused connection), a rate limit (429) or a server error (5xx). Any other status is the page's
    own answer (a 404, a 403 of a register that refuses automated readers) and is kept."""
    status = meta["status"]
    return status is None or status == TOO_MANY_REQUESTS or status >= 500


def failing_pages(urls: Iterable[str], pages: Path) -> list[str]:
    """The cited pages whose kept fetch failed for a reason that may pass (`may_pass`)."""
    failing = []
    for url in sorted({Q.canonical_url(u)[0] for u in urls}):
        record = pages / f"{Q.url_key(url)}.json"
        if record.exists() and may_pass(json.loads(record.read_text(encoding="utf-8"))):
            failing.append(url)
    return failing


def fetch_pages(
    run: Path, urls: Iterable[str], client: httpx.Client | None, pace: float
) -> tuple[Q.Library, list[str]]:
    """Every cited page fetched into `pages/` - once, except a fetch that failed for a reason that
    may pass (`may_pass`), which every import tries again - and the library the quote check reads
    them from, with the pages still failing that way (the import prints them: run it again before
    the next stage is exported). `verify`, `verify2` and the pilot judge share `pages/`."""
    pages = run / "pages"
    wanted = sorted(set(urls))
    for url in failing_pages(wanted, pages):
        key = Q.url_key(url)
        (pages / f"{key}.json").unlink()  # the record first: a record always names a body
        (pages / f"{key}.body").unlink()
    own = client is None
    http = judge_client() if client is None else client
    try:
        Q.collect(wanted, pages, http, now=_now, pace=pace)
    finally:
        if own:
            http.close()
    return Q.Library(ROOT, pages), failing_pages(wanted, pages)


def claims_floor(listed: int, floor: int) -> str | None:
    """Why a web judge's answer covers too few claims - fewer than the check that accepted the card
    listed (CARD_DESCRIPTIONS.md 2.1: a verifier that lists only the central claim would VERIFY a
    card whose other claims nobody researched) - or `None`. The judge sees only the number."""
    if listed < floor:
        return (
            f"the answer lists {listed} claim(s); the card makes at least {floor} (another "
            "agent's count): list every claim of the text, each fact on its own"
        )
    return None


def verify_record(card: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    """The record of one verification: the card, each claim proven or not, and the verdict."""
    return {
        "kind": "verify",
        "card": card,
        "claims": claims,
        "verdict": card_verification(claims),
        "unproven": sum(1 for claim in claims if not proves(claim)),
    }


def import_stage(
    run: Path,
    stage: str,
    *,
    fit: C.Fit = V.card_fit,
    client: httpx.Client | None = None,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Every answer of one stage's round: validated, prompt-matched, parsed, recorded - refused,
    with nothing written, when a later stage's record judged another card than this import
    records (`judging`). A verify stage's import refuses an answer that lists fewer claims than the
    accepting check (`claims_floor`), fetches every cited page the source rule admits
    (`fetch_pages`: `client`, the lanes' User-Agent; a failure that may pass is tried again at the
    next import and printed as `transient_failures`) and checks every quote by machine."""
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
    judged: dict[str, tuple[A.Judged, ...]] = {}
    for (batch_id, site_id), line in sorted(manifest.items(), key=lambda kv: kv[0][1]):
        state = current[site_id]
        if state.status != DUE or state.stage != stage:
            raise RunError(f"{site_id} is not due at {stage}: it is {state.status} {state.stage}")
        prompt = prompt_for(stage, sites[site_id], state)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise RunError(f"{batch_id}/{site_id}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=site_id,
                                prompt=prompt)  # fmt: skip
        if stage in CHECKER_STAGES or stage in VERIFY_STAGES:
            others = _earlier_agents(site_id, stage, records)
            if answer.answered_by in others:
                raise RunError(
                    f"{batch_id}/{site_id}: {answer.answered_by} wrote or checked this site before "
                    "- a check or verification is an independent agent's; have the batch answered "
                    "again under its own name"
                )
        try:
            if stage in VERIFY_STAGES:
                judged[site_id] = A.parse_judge(answer.text)
                assert state.check is not None
                short = claims_floor(len(judged[site_id]), len(state.check["claims"]))
                if short is not None:
                    raise A.AnswerError(short)
                parsed: dict[str, Any] = {}
            else:
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
    failing: list[str] = []
    if stage in VERIFY_STAGES:
        urls = cited_pages(j for claims in judged.values() for j in claims)
        library, failing = fetch_pages(run, urls, client, pace)
        for row in rows:
            site_id = row["site_id"]
            card = current[site_id].card
            assert card is not None
            row.update(verify_record(card, prove_claims(site_id, judged[site_id], library)))
    # the later stages' records must still judge the cards this import records (`judging`): a stage
    # imported again with another card after a later stage judged the old one is refused here,
    # before anything is written
    settled = {**stage_records(run), stage: {row["site_id"]: row for row in rows}}
    for site_id in sites:
        progress(site_id, settled)
    write_jsonl(run / f"STAGE-{stage}.jsonl", rows)
    if stage in WRITER_STAGES:
        failed = sum(1 for row in rows if row["problems"])
        return {"stage": stage, "answers": len(rows), "mechanical_failures": failed}
    verdicts = Counter(row["verdict"] for row in rows)
    result: dict[str, Any] = {
        "stage": stage,
        "answers": len(rows),
        "verdicts": dict(sorted(verdicts.items())),
    }
    if stage in VERIFY_STAGES:
        result["transient_failures"] = failing
    return result


# ------------------------------------------------------------------------------ the agent's aids
def judge_floor(run: Path, stage: str, site_id: str) -> int:
    """The fewest claims a web judge of the site may list (`claims_floor`): as many as the check
    that accepted its card listed - the check the verifier follows, or the pilot judge's final
    card's (its provenance)."""
    if stage == JUDGE_STAGE:
        accepted = {r["site_id"]: r for r in read_outcomes(run) if r["status"] == ACCEPTED}
        return len(accepted[site_id]["provenance"]["check"]["claims"])
    state = progress(site_id, stage_records(run, before=stage))
    assert state.check is not None
    return len(state.check["claims"])


def check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str, *, fit: C.Fit = V.card_fit
) -> dict[str, Any]:
    """The shape of one answer, and for a card its mechanical problems - nothing is recorded."""
    record = _round_of_handoff(run, handoff)
    stage = record["stage"]
    if label not in record["batches"].get(batch_id, []):
        raise RunError(f"{batch_id}/{label} is no question of {handoff}")
    if stage == JUDGE_STAGE or stage in VERIFY_STAGES:
        try:
            claims = A.parse_judge(text)
        except A.AnswerError as exc:
            return {"ok": False, "problems": [str(exc)]}
        short = claims_floor(len(claims), judge_floor(run, stage, label))
        return {"ok": short is None, "problems": [] if short is None else [short]}
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
    "verifier": (
        "You are Opus verifier {batch} of lane WB (teaser cards). You check {count} card(s) "
        "written and checked by other agents against sources on the web, each on its own. Every "
        "verdict rests on a page you opened and quote."
    ),
    "judge": (
        "You are Opus judge {batch} of the lane-WB pilot. You check {count} card(s) against "
        "sources on the web, each on its own. Every verdict rests on a page you opened and quote."
    ),
}

BRIEF = """{head}

This batch needs an agent that has answered no other batch of lane WB (no card written, checked, \
verified or judged): if you have, stop now and say so - the independence of every check rests on \
it.

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
    "verifier": "Research on the web and decide each claim, exactly as the prompt asks.",
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
    "verifier": (
        "It prints the shape problem, if any - or that you listed fewer claims than the card "
        "makes: then list every claim, each fact on its own. Fix the shape, never the finding."
    ),
    "judge": (
        "It prints the shape problem, if any - or that you listed fewer claims than the card "
        "makes: then list every claim, each fact on its own. Fix the shape, never the finding."
    ),
}


def _kind(stage: str) -> str:
    """Which agent a stage's batch needs: its brief's head, task and fix."""
    if stage == JUDGE_STAGE:
        return "judge"
    if stage in VERIFY_STAGES:
        return "verifier"
    return "writer" if stage in WRITER_STAGES else "checker"


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the Opus agent that answers one batch."""
    record = _round_of_handoff(run, handoff)
    if batch_id not in record["batches"]:
        raise RunError(f"{batch_id} is no batch of {handoff}")
    stage = record["stage"]
    kind = _kind(stage)
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


_VERIFICATION_KEYS = (
    "stage",
    "batch_id",
    "answered_by",
    "answered_at",
    "card",
    "verdict",
    "unproven",
    "claims",
)


def _provenance(run: Path, site: C.Basis, state: Progress, ai_system: str) -> dict[str, Any]:
    """The provenance of an accepted card: its accepting check, its VERIFIED verification (with the
    sha256 of the text it judged) and the web facts its check's claims cite - those the check was
    asked with (a rewrite after a failed verification only)."""
    writer, check, verify = state.writer, state.check, state.verify
    assert writer is not None and check is not None and verify is not None
    cited = {s for claim in check["claims"] for s in claim["support"] if s.startswith("W")}
    offered = recorded_web_facts(check, state) if check["stage"] == VERIFY_CHECK else ()
    return CP.build(
        run=run.name,
        ai_system=ai_system,
        card=writer["card"],
        description=site.description,
        stage=check["stage"],
        checker=check["answered_by"],
        checked_at=check["answered_at"],
        claims=check["claims"],
        verify={
            "verdict": verify["verdict"],
            "stage": verify["stage"],
            "by": verify["answered_by"],
            "at": verify["answered_at"],
            "claims": len(verify["claims"]),
            "unproven": verify["unproven"],
            "text_sha256": CP.text_sha256(verify["card"]),
        },
        web_facts=[asdict(fact) for fact in offered if fact.id in cited],
    )


def outcome_rows(run: Path, *, ai_system: str = M.AI_SYSTEM) -> list[dict[str, Any]]:
    """The final result of every site of the run: an accepted - checked and VERIFIED - card with
    its provenance, or a clear - a failed site, or a listed site without a description whose card
    is to be cleared. Each row carries its verification state (`verification`: the last
    verification's verdict, `None` for a card never verified) and every verification in full."""
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
            "verification": None if state.verify is None else state.verify["verdict"],
            "verifications": [
                {key: verified[key] for key in _VERIFICATION_KEYS} for verified in state.verified
            ],
        }
        if state.status == ACCEPTED:
            writer = state.writer
            assert writer is not None
            rows.append(
                {
                    **common,
                    "status": ACCEPTED,
                    "reason": None,
                    "card": writer["card"],
                    "writer": {k: writer[k] for k in ("stage", "answered_by", "answered_at")},
                    "provenance": _provenance(run, site, state, ai_system),
                }
            )
        else:
            rows.append(
                {
                    **common,
                    "status": CLEARED,
                    "reason": state.reason,
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
                    "verification": None,
                    "verifications": [],
                    "status": CLEARED,
                    "reason": NO_DESCRIPTION,
                    "card": None,
                    "writer": None,
                    "provenance": None,
                }
            )
    return sorted(rows, key=lambda r: r["site_id"])


def description_defects(run: Path) -> list[dict[str, Any]]:
    """Every contradicted claim (proven or not) that repeats the site's description: the input of a
    later description repair by the lane whose text it is (`owner_lane`).

    - the first verifier's: each claim the rewrite's writer mapped to a sentence (`repeats`) - its
      `sentence`, and `candidates` that one id; a claim mapped to no sentence is the card's own
      departure (a lane-WB fault, in OUTCOMES), not the text's;
    - the second verifier's: each contradicted claim of a card `check-v` accepted, which rests on
      the sentences that check cited - no writer maps it, so `sentence` is null and `candidates` are
      those sentence ids; a card whose claims rest on web facts alone says nothing of the
      description, and its contradiction is no defect.
    """
    sites = bases(run)
    basis = {
        row["site_id"]: row["basis"] for row in _pinned_jsonl(run, "SITES.jsonl", "sites_sha256")
    }
    records = stage_records(run)
    rows: list[dict[str, Any]] = []

    def defect(
        site_id: str,
        verified: Mapping[str, Any],
        claim: Mapping[str, Any],
        sentence: str | None,
        candidates: list[str],
        mapped_by: str | None,
    ) -> None:
        site = sites[site_id]
        text = {s.id: s.text for s in site.sentences}
        rows.append(
            {
                "run": run.name,
                "site_id": site_id,
                "name": site.name,
                "basis": basis[site_id],
                "owner_lane": OWNER_LANE[basis[site_id]],
                "desc_sha256": site.desc_sha256,
                "stage": verified["stage"],
                "sentence": None if sentence is None else int(sentence[1:]),
                "sentence_text": None if sentence is None else text[sentence],
                "candidates": candidates,
                "claim": claim["claim"],
                "url": claim["url"],
                "quote": claim["quote"],
                "quote_outcome": claim["quote_outcome"],
                "proven": claim["proven"],
                "verifier": verified["answered_by"],
                "mapped_by": mapped_by,
            }
        )

    for site_id, state in sorted(states(run).items()):
        if not state.verified or state.verified[0]["verdict"] == VERIFIED:
            continue
        first, rewritten = state.verified[0], records[VERIFY_REWRITE][site_id]
        for claim, repeat in zip(contradicted_claims(first), rewritten["repeats"], strict=True):
            if repeat is None:
                continue
            defect(site_id, first, claim, repeat, [repeat], rewritten["answered_by"])
        if len(state.verified) == 2:
            rechecked = records[VERIFY_CHECK][site_id]
            cited = {s for c in rechecked["claims"] for s in c["support"] if s.startswith("S")}
            candidates = sorted(cited, key=lambda s: int(s[1:]))
            if not candidates:
                continue
            for claim in contradicted_claims(state.verified[1]):
                defect(site_id, state.verified[1], claim, None, candidates, None)
    return rows


def outcomes_markdown(
    run: Path, rows: Sequence[Mapping[str, Any]], defects: Sequence[Mapping[str, Any]]
) -> str:
    accepted = [r for r in rows if r["status"] == ACCEPTED]
    lengths = [len(r["card"]) for r in accepted]
    attempts = Counter(r["attempts"] for r in accepted)
    reasons = Counter(r["reason"] for r in rows if r["status"] == CLEARED)
    at_stage = Counter(r["provenance"]["verify"]["stage"] for r in accepted)
    finals = [r["verifications"][-1] for r in accepted]
    claims = sum(len(v["claims"]) for v in finals)
    unproven = sum(v["unproven"] for v in finals)
    lines = [
        f"# Lane WB run `{run.name}` - outcomes",
        "",
        f"Written {_now()} by `scripts/remediation/teaser/run.py outcomes`. Only an accepted card "
        "is written: checked against its description and VERIFIED on the web (no claim "
        f"contradicted, at most {CP.MAX_UNPROVEN_CLAIMS} without a proving quote and never the "
        "central one).",
        "",
        f"- sites: {len(rows)}; **accepted {len(accepted)}**, cleared "
        f"{len(rows) - len(accepted)} ({dict(sorted(reasons.items()))})",
        f"- accepted at attempt 1/2/3/4: {attempts.get(1, 0)}/{attempts.get(2, 0)}/"
        f"{attempts.get(3, 0)}/{attempts.get(4, 0)}",
        f"- VERIFIED at the first verification {at_stage.get(FIRST_VERIFY, 0)}, after the rewrite "
        f"{at_stage.get(SECOND_VERIFY, 0)}; the accepted cards' final verifications: {claims} "
        f"claims, {unproven} without a proving quote "
        f"({unproven / claims if claims else 0:.1%})",
        f"- description sentences the web contradicts: {len(defects)} "
        "(`DESCRIPTION_DEFECTS.jsonl`, for the lane whose text it is)",
    ]
    if lengths:
        lines.append(
            f"- card length: min {min(lengths)}, median {statistics.median(lengths)}, max "
            f"{max(lengths)} characters"
        )
    lines += ["", "## Every contradiction the verifiers found", ""]
    contradictions = [
        (r, v, claim)
        for r in rows
        for v in r["verifications"]
        for claim in v["claims"]
        if claim["verdict"] == CONTRADICTED
    ]
    for r, v, claim in contradictions:
        mark = "CONTRADICTED" if claim["proven"] else "CONTRADICTED (not proven)"
        lines.append(
            f"- {r['name']} (`{r['site_id'][:8]}`, {v['stage']}, now {r['status']}) {mark}: "
            f"{claim['claim']} - {claim['url']} ({claim['quote_outcome']})"
        )
    if not contradictions:
        lines.append("None.")
    lines += ["", "| site | status | verification | card |", "|---|---|---|---|"]
    for r in rows:
        card = (r["card"] or "").replace("|", "\\|")
        state = r["verification"] or "-"
        lines.append(f"| {r['name']} (`{r['site_id'][:8]}`) | {r['status']} | {state} | {card} |")
    return "\n".join(lines) + "\n"


def outcomes(run: Path) -> dict[str, Any]:
    rows = outcome_rows(run)
    defects = description_defects(run)
    digest = write_jsonl(run / "OUTCOMES.jsonl", rows)
    write_jsonl(run / "DESCRIPTION_DEFECTS.jsonl", defects)
    (run / "OUTCOMES.md").write_text(
        outcomes_markdown(run, rows, defects), encoding="utf-8", newline="\n"
    )
    counts = Counter(f"{r['status']} {r['reason']}" if r["reason"] else r["status"] for r in rows)
    return {
        "outcomes": len(rows),
        "sha256": digest,
        "counts": dict(sorted(counts.items())),
        "description_defects": len(defects),
    }


def read_outcomes(run: Path) -> list[dict[str, Any]]:
    path = run / "OUTCOMES.jsonl"
    if not path.exists():
        raise RunError(f"{path} does not exist - run `outcomes` first")
    return read_jsonl(path)


# ------------------------------------------------------------------------------ the pilot judge
def export_judge(run: Path, handoff: Path) -> dict[str, Any]:
    """Every accepted card of the run - its final, VERIFIED card, the one to be written - to fresh
    independent web judges (the pilot gate, runbook 5.2)."""
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
    """The HTTP client of the verify imports and the pilot judge's: the audit's
    (`quotes.http_client`) under the lanes' one User-Agent, no personal data."""
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
    """Every judge answer: parsed, each cited page fetched once, each quote checked by machine. The
    pilot's judge is fresh: a name that answered any question of the run - a writer, a checker or a
    verifier of any card - is refused."""
    record = _round(run, JUDGE_STAGE)
    if record is None:
        raise RunError("the judge round was never exported")
    handoff = _resolve(Path(record["handoff"]))
    check = OH.validate(handoff)
    if not check.ok:
        raise RunError(f"{record['handoff']}: not every judge answer is in, in shape, by Opus")
    sites = bases(run)
    accepted = {r["site_id"]: r for r in read_outcomes(run) if r["status"] == ACCEPTED}
    cards = {site_id: row["card"] for site_id, row in accepted.items()}
    workers = {row["answered_by"] for rows in stage_records(run).values() for row in rows.values()}
    parsed: dict[str, tuple[Any, tuple[A.Judged, ...]]] = {}
    for batch_id, members in record["batches"].items():
        for site_id in members:
            site = sites[site_id]
            prompt = P.judge_prompt(site.name, site.country, cards[site_id])
            answer = OH.read_answer(handoff, batch_id=batch_id, stage=JUDGE_STAGE, label=site_id,
                                    prompt=prompt)  # fmt: skip
            if answer.answered_by in workers:  # a reused name; the agent: module doc
                raise RunError(
                    f"{site_id}: the judge {answer.answered_by} answered a question of this run "
                    "(a writer, checker or verifier) - the pilot's judge is fresh"
                )
            try:
                parsed[site_id] = (answer, A.parse_judge(answer.text))
                floor = len(accepted[site_id]["provenance"]["check"]["claims"])
                short = claims_floor(len(parsed[site_id][1]), floor)
                if short is not None:
                    raise A.AnswerError(short)
            except A.AnswerError as exc:
                raise RunError(f"{batch_id}/{site_id}: malformed judge answer ({exc})") from exc
    urls = cited_pages(j for _, claims in parsed.values() for j in claims)
    library, failing = fetch_pages(run, urls, client, pace)
    tally = JudgeTally()
    rows = []
    for site_id in sorted(parsed):
        answer, claims = parsed[site_id]
        results = prove_claims(site_id, claims, library)
        for result in results:
            tally.claims += 1
            if proves(result):
                tally.supported += 1
            elif result["verdict"] == CONTRADICTED and result["proven"]:
                tally.contradicted += 1
                if site_id not in tally.wrong_cards:
                    tally.wrong_cards.append(site_id)
            else:
                tally.unproven += 1
                if result["verdict"] == CONTRADICTED:
                    tally.contradicted_unproven += 1
                    if site_id not in tally.disputed_cards:
                        tally.disputed_cards.append(site_id)
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
        "transient_failures": failing,
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
        f"Written {_now()} by `run.py judge-import`, on the pilot's final (VERIFIED) cards, by a "
        "judge who answered nothing else in the run. Gate: no claim CONTRADICTED - with a proving "
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
        ("import", "validate, parse and record one stage's answers (verify: pages, quotes)"),
        ("check-answer", "the shape (and a card's mechanical checks) of one answer"),
        ("brief", "the instruction of one batch's Opus agent"),
        ("status", "where every site of the run stands"),
        ("outcomes", "OUTCOMES.jsonl/.md and DESCRIPTION_DEFECTS.jsonl, every site settled"),
        ("judge-export", "the pilot gate: its final cards to a fresh web judge"),
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
