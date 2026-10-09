"""Lane WB: the teaser cards, from the fact basis to checked outcomes, through the Opus handoff.

Owner decisions O2-O4 and O10 of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`); the
contract and the whole runbook are `docs/procedures/CARD_DESCRIPTIONS.md`. No model is called here:
every card is written by one agent and checked by another, each answering one batch through the
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
    opus_handoff.py validate --dir $H-write                every answer in, in shape
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

and for the contracts after v1 (`select --contract shorts-v1`; see "The contracts"):

    $T agents --run R --handoff $H-write                   one workflow job per batch: role, fixed
        model id, effort, brief, how many may run at once (JSON)
    $T void-batch --run R --handoff $H-check --batch-id B  set aside the answers of a batch whose
        checker passed its seeded-defect card (the batch is asked again by a new agent)
    $T seed-live --run R --provenance-run RUN0             record the live cards of RUN0 (the MiniMax
        gap run) as a re-check run (contract recheck-v1, owner decision D10)
    $T escalate --run R --role ROLE --verdict V.json       move a role up one tier after its failed
        calibration (before its first round), recorded in RUN.json

## The stages

`write` asks every candidate; `check` asks a different agent about every card that passed the
mechanical checks (`contract.problems`), one checker per writer batch; a card that failed either goes
to `rewrite1` with its findings and is checked by a new checker in `check1`; once more in `rewrite2`
and `check2`; after that the site gets no card (cleared, `failed-after-two-rewrites`).

A writer of `write`, `rewrite1` or `rewrite2` may instead answer that no card can be written:
`{"card": null, "basis": [], "undrawable": true}` (`answers.Declined`). The parse accepts it only
where the contract proves it (`contract.undrawable_proof`): every name form of the site contains a
glyph the shorts font cannot draw, so no card can pass both the name and the font check. The site is
then cleared at once (`name-undrawable`) and no later stage asks it; `import` and `check-answer`
refuse the decline for a site with a drawable name form.

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

## The contracts

A run's contract is `RUN.json["contract"]` (`contract_of`). The chain above is contract **v1**: a run
selected before the contracts were named holds an object there (its limits). Two more chains run
through the same files and the same import (`Spec`, `SPECS`):

* **shorts-v1** (`shorts_v1.py`, owner decisions D1-D6 of 2026-10-08): the nameless Shorts card.
  The writer answers three variants (`write`, `rewrite1`, `rewrite2`), a hook rater rates the
  variants that passed the mechanical rules (`rate`, `rate1`, `rate2`; its best variant needs a
  rating of `AS.HOOK_FLOOR`, else the round fails and the site is written again), a checker checks the
  best one (`check`, `check1`, `check2`), a web verifier verifies it (`verify`) and a failed
  verification gets the one rewrite of v1 (`rewrite-v`, `check-v`, `verify2`). A site whose
  chain fails, or whose writer declined its thin description, **keeps its card** (D5): its outcome is
  `kept`, never a clear. Every answer is given in the role of its stage (`roles.ROLES`, recorded in
  `RUN.json["roles"]`): the import refuses an answer whose `answered_by` names another role or whose
  stamp is not that role's model. Every check batch carries one seeded-defect canary
  (`shorts_v1.canary_card`); a batch whose checker passes it is void (`void-batch`).
* **recheck-v1** (owner decision D10): the Claude re-check of the cards another model wrote
  (`seed-live` records the live cards as the `write` stage): `check`, `verify`, `adversarial`. A card
  that passes all three is `confirmed` and stands; any failure clears it (`recheck-<reason>`, a
  journalled `card-clear-recheck-<reason>`).

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
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
import roles as RO  # noqa: E402 - the registry: which model gives which answer (owner decision D6)
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
from teaser import answers_shorts as AS  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

RUNS = ROOT / "output" / "remediation" / "teaser" / "runs"
CURATED_SOURCE = "ancient_nerds"
RETIRED = "retired"
#: The description provenances a teaser may be written from: the Phase-4 lanes, whose text is
#: assembled from a pinned source (W, S) or restated from one (T, R), and lane E, a W or S text that
#: the enrichment lane extended with web-sourced sentences, each quoted, checked and verified
#: (`wc4.EnrichedProvenance`, orchestrator decision X1). Lane L alone is the March text
#: (unverified), and a text without provenance is unclaimed (HUMAN_ONLY D7): both wait for lane WC.
BASIS_LANES = frozenset({"W", "S", "T", "R", "E"})
#: Lane WC's sentence check (owner decision O5): `raw_data._description_check`, whose `desc_sha256`
#: hashes the text that stayed after every sentence was checked against a quoted source. Such a text
#: keeps lane L's provenance (its hash moved) or none, so the check record is what makes it a basis.
#: The spelling is `phase4/wc4.py:CHECK_KEY` of `wip/wc`; the merge of lane WC replaces this literal
#: with an import of it (CARD_DESCRIPTIONS.md, "Merging").
CHECK_KEY = "_description_check"
#: Lane E's record for a checked March text or a lane-N text that was enriched
#: (`phase4/wc4.py:ENRICH_KEY`): it replaces the check record, and its `desc_sha256` hashes the whole
#: new text, so it is the basis exactly as the check record's was (`SITES_SQL`, `basis_of`).
ENRICH_KEY = "_description_enrichment"
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
NAME_UNDRAWABLE = "name-undrawable"
#: The writer stages whose writer may decline a site that no card can be written for: all but the
#: rewrite after a web verification, whose card passed the name and font checks already.
DECLINING_STAGES = tuple(writer for writer, _ in CHECK_ROUNDS)
#: Whose text a contradicted description sentence is (DESCRIPTION_DEFECTS.jsonl "owner_lane"): a
#: Phase-4 text is lane WA's (Phase 4, scope v3), a sentence-checked March text lane WC's, an enriched
#: Phase-4 text (lane E) the enrichment lane's (WE).
OWNER_LANE = {
    **dict.fromkeys(sorted(BASIS_LANES - {"E"}), "WA"),
    "E": "WE",
    SENTENCE_CHECKED: "WC",
}
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


class CanaryPassed(RunError):
    """The checker of these batches passed the batch's seeded-defect card: the batches are void."""

    def __init__(self, batches: Sequence[str]) -> None:
        self.batches = tuple(batches)
        super().__init__(
            "the checker of batch(es) " + ", ".join(batches) + " passed the seeded-defect card: "
            "the batch is void - `void-batch` it and have it answered again by a new agent"
        )


# ------------------------------------------------------------------------------ the contracts
V1 = "v1"
SHORTS = SV.CONTRACT
RECHECK = "recheck-v1"
CONTRACTS = (V1, SHORTS, RECHECK)
#: The rounds of contract shorts-v1: the writer, the hook rater, the checker.
SHORTS_ROUNDS = (
    ("write", "rate", "check"),
    ("rewrite1", "rate1", "check1"),
    ("rewrite2", "rate2", "check2"),
)
ADVERSARIAL = "adversarial"
#: The seeded stage of a re-check run: the live cards, recorded as if a writer had answered them.
SEEDED_WRITE = "write"
SEED_BATCH = "seed-live"
#: A site's outcome besides accepted and cleared: its card stays (owner decision D5, contract
#: shorts-v1) and a re-checked card that passed every check (owner decision D10).
KEPT = "kept"
CONFIRMED = "confirmed"
THIN_DECLINED = "thin-declined"
RECHECK_MECHANICAL = "recheck-mechanical"
RECHECK_CHECK_FAILED = "recheck-check-failed"
RECHECK_CONTRADICTED = "recheck-contradicted"
RECHECK_UNPROVEN = "recheck-unproven"
RECHECK_ADVERSARIAL_FAILED = "recheck-adversarial-failed"
#: Questions per rater batch, per adversarial batch.
RATE_BATCH_SIZE = 25
JUDGE_ROLE = "pilot_judge"


@dataclass(frozen=True)
class Spec:
    """A contract's chain: which stages it has, which of them write, rate, check, verify or argue,
    which are seeded instead of asked, the role that answers each (empty for v1, whose answers
    carry no role) and the stages whose batches carry a canary."""

    name: str
    stages: tuple[str, ...]
    rounds: tuple[tuple[str, ...], ...]
    writers: tuple[str, ...]
    raters: tuple[str, ...]
    checkers: tuple[str, ...]
    verifiers: tuple[str, ...]
    adversarial: tuple[str, ...]
    seeded: tuple[str, ...]
    roles: Mapping[str, str]
    canary: tuple[str, ...]

    @property
    def independent(self) -> tuple[str, ...]:
        """The stages whose agent must be new to the site: a rater, checker, verifier or reviewer."""
        return (*self.raters, *self.checkers, *self.verifiers, *self.adversarial)


V1_SPEC = Spec(
    name=V1,
    stages=STAGES,
    rounds=CHECK_ROUNDS,
    writers=WRITER_STAGES,
    raters=(),
    checkers=CHECKER_STAGES,
    verifiers=VERIFY_STAGES,
    adversarial=(),
    seeded=(),
    roles=MappingProxyType({}),
    canary=(),
)
_SHORTS_CHECKERS = (*(checker for _, _, checker in SHORTS_ROUNDS), VERIFY_CHECK)
SHORTS_SPEC = Spec(
    name=SHORTS,
    stages=(
        *(stage for group in SHORTS_ROUNDS for stage in group),
        FIRST_VERIFY,
        VERIFY_REWRITE,
        VERIFY_CHECK,
        SECOND_VERIFY,
    ),
    rounds=SHORTS_ROUNDS,
    writers=(*(writer for writer, _, _ in SHORTS_ROUNDS), VERIFY_REWRITE),
    raters=tuple(rater for _, rater, _ in SHORTS_ROUNDS),
    checkers=_SHORTS_CHECKERS,
    verifiers=VERIFY_STAGES,
    adversarial=(),
    seeded=(),
    roles=MappingProxyType(
        {
            **dict.fromkeys((*(w for w, _, _ in SHORTS_ROUNDS), VERIFY_REWRITE), "card_writer"),
            **dict.fromkeys((r for _, r, _ in SHORTS_ROUNDS), "hook_rater"),
            **dict.fromkeys(_SHORTS_CHECKERS, "fact_checker"),
            **dict.fromkeys(VERIFY_STAGES, "web_verifier"),
        }
    ),
    canary=_SHORTS_CHECKERS,
)
RECHECK_SPEC = Spec(
    name=RECHECK,
    stages=(SEEDED_WRITE, "check", FIRST_VERIFY, ADVERSARIAL),
    rounds=(),
    writers=(SEEDED_WRITE,),
    raters=(),
    checkers=("check",),
    verifiers=(FIRST_VERIFY,),
    adversarial=(ADVERSARIAL,),
    seeded=(SEEDED_WRITE,),
    roles=MappingProxyType(
        {"check": "fact_checker", FIRST_VERIFY: "web_verifier", ADVERSARIAL: "adversarial"}
    ),
    canary=("check",),
)
SPECS: Mapping[str, Spec] = MappingProxyType(
    {V1: V1_SPEC, SHORTS: SHORTS_SPEC, RECHECK: RECHECK_SPEC}
)
#: Every stage name of any chain, for the command line.
ALL_STAGES = tuple(dict.fromkeys(stage for spec in SPECS.values() for stage in spec.stages))


def contract_of(run: Path) -> str:
    """The contract a run was selected under (`RUN.json["contract"]`): a run of v1 recorded its
    limits there as an object, a later contract records its name."""
    value = json.loads((run / "RUN.json").read_text(encoding="utf-8"))["contract"]
    if isinstance(value, dict):
        return V1
    if value not in (SHORTS, RECHECK):
        raise RunError(f"{run / 'RUN.json'} names the contract {value!r}, not one of {CONTRACTS}")
    return str(value)


def spec_of(run: Path) -> Spec:
    return SPECS[contract_of(run)]


def stage_role(spec: Spec, stage: str) -> str:
    """The role that answers a stage of a role-bound contract; the pilot judge for `judge`."""
    if stage == JUDGE_STAGE:
        return JUDGE_ROLE
    if stage not in spec.roles:
        raise RunError(f"stage {stage} of contract {spec.name} has no role")
    return spec.roles[stage]


def roles_record(spec: Spec) -> dict[str, dict[str, str]]:
    """The registry's entries for the roles of this contract's stages and the pilot judge, as a
    run fixes them at its start (`RUN.json["roles"]`): later changes of `roles.ROLES` do not move a
    run that began - an escalation is a record of its own (`escalate_role`)."""
    names = sorted({*spec.roles.values(), JUDGE_ROLE})
    return {name: {"model": RO.role(name).model, "effort": RO.role(name).effort} for name in names}


def run_roles(run: Path) -> dict[str, dict[str, str]]:
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    if "roles" not in record:
        raise RunError(
            f"{run / 'RUN.json'} records no roles: a role-bound run records them at its start"
        )
    return dict(record["roles"])


def role_problem(
    roles: Mapping[str, Mapping[str, str]], role: str, answered_by: str, stamp: str
) -> str | None:
    """Why an answer is not the role's: it names another role, or its stamp is not the stamp of the
    model the run recorded for the role. `None` when it is."""
    named = RO.role_of(answered_by)
    if named != role:
        return (
            f"{answered_by!r} did not answer as role {role} (record it with `opus_handoff.py "
            f"answer --role {role}`)"
        )
    expected = OH.ANSWER_MODELS[roles[role]["model"]]
    if stamp != expected:
        return (
            f"role {role} is recorded as {roles[role]['model']} ({expected!r}), but the answer "
            f"is stamped {stamp!r}"
        )
    return None


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
_SITES_HEAD = (
    "SELECT u.id::text AS site_id, u.name, u.country, u.description, u.scope_status, "
    "u.raw_data -> '_description_provenance' ->> 'lane' AS lane, "
    "u.raw_data -> '_description_provenance' ->> 'desc_sha256' AS provenance_desc_sha256, "
    f"coalesce(u.raw_data -> '{ENRICH_KEY}' ->> 'desc_sha256', "
    f"u.raw_data -> '{CHECK_KEY}' ->> 'desc_sha256') AS check_desc_sha256, "
    "u.raw_data -> '_card_provenance' AS card_provenance, "
    "(c.site_id IS NOT NULL) AS has_card_row, c.card_description AS card, "
    "coalesce((SELECT json_agg(n.name ORDER BY n.name) FROM unified_site_names n "
    "WHERE n.site_id = u.id), '[]'::json) AS alt_names "
)
_SITES_TAIL = (
    "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    f"WHERE u.source_id = '{CURATED_SOURCE}' ORDER BY u.id"
)
SITES_SQL = _SITES_HEAD + _SITES_TAIL
#: What contract shorts-v1 reads beyond a v1 run: how many usable images a site has (the Shorts
#: selector's rules: not excluded, short side at least 900 px, aspect at most 2.0) and up to twelve
#: of their Commons titles, the hero first - hints for the photo anchors, never a fact.
_POOL_IMAGES = (
    "w.site_id = u.id AND NOT w.is_excluded AND least(w.width, w.height) >= 900 "
    "AND greatest(w.width, w.height) <= 2.0 * least(w.width, w.height)"
)
SHORTS_SITES_SQL = (
    _SITES_HEAD.rstrip()
    + f", (SELECT count(*) FROM wiki_images w WHERE {_POOL_IMAGES}) AS pool_images, "
    "coalesce((SELECT json_agg(t.title ORDER BY t.is_hero DESC, t.sort_order, t.id) FROM "
    "(SELECT w.title, w.is_hero, w.sort_order, w.id FROM wiki_images w WHERE "
    f"{_POOL_IMAGES} AND w.title IS NOT NULL ORDER BY w.is_hero DESC, w.sort_order, w.id "
    "LIMIT 12) t), '[]'::json) AS image_titles " + _SITES_TAIL
)


def export_script(contract: str = V1) -> str:
    """One read-only repeatable-read snapshot of every curated site's card inputs."""
    sql = SHORTS_SITES_SQL if contract == SHORTS else SITES_SQL
    return tagged_export_script([("site", sql)])


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


def current_for(teaser: Mapping[str, Any], contract: str) -> bool:
    """Whether a live teaser provenance already is the card `contract` would write: any card for
    v1 (as before); for shorts-v1 only a version-3 card of that contract - the 2,830 version-2 cards
    name their site and are candidates again."""
    if contract == SHORTS:
        return teaser["v"] == CP.VERSION_3 and teaser["contract"] == contract
    return True


def classify(row: Mapping[str, Any], contract: str = V1) -> tuple[str | None, str]:
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
        and current_for(teaser, contract)
    ):
        return CURRENT, "its teaser card is live and checked against this description"
    if basis_of(row) is None:
        return NOT_FINAL, (
            f"not a sourced text: no lane-{'/'.join(sorted(BASIS_LANES))} provenance and no "
            f"sentence check hashes it (provenance lane {row['lane']!r})"
        )
    return None, ""


def _site_row(row: Mapping[str, Any], contract: str = V1) -> dict[str, Any]:
    found = {
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
    if contract == SHORTS:
        found["pool_images"] = int(row["pool_images"])
        found["image_titles"] = list(row["image_titles"])
    return found


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
    contract: str = V1,
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
        reason, detail = classify(row, contract)
        if reason is not None:
            listing(row, reason, detail)
        elif earlier.get(row["site_id"]) == CP.text_sha256(row["description"]):
            listing(row, ASKED_BEFORE, "asked in an earlier run with this description")
        elif sites is not None and row["site_id"] not in sites:
            listing(row, NOT_LISTED, "not in the run's sites file")
        elif basis is not None and basis_of(row) not in basis:
            listing(row, OTHER_BASIS, f"basis {basis_of(row)} is not asked (--basis)")
        else:
            candidates.append(_site_row(row, contract))
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


def earlier_sites(runs: Sequence[Path], contract: str = V1) -> dict[str, str]:
    """Every site asked in the given runs of `contract`, with the description sha256 it was asked
    with. A run of another contract is refused, never skipped: what a v1 run asked, a shorts-v1 run
    asks again, so a v1 (or a re-check) run does not belong to a shorts-v1 `--exclude-run`."""
    asked: dict[str, str] = {}
    for run in runs:
        other = contract_of(_resolve(run))
        if other != contract:
            raise RunError(
                f"--exclude-run {run} is a run of contract {other}, not {contract}: only runs of "
                "the contract being selected are excluded"
            )
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
    contract: str = V1,
) -> dict[str, Any]:
    """Read production once (read-only) and fix the run's candidates. Once per run."""
    if contract not in (V1, SHORTS):
        raise RunError(f"a run of contract {contract} is not selected, it is seeded (`seed-live`)")
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
        parsed["site"],
        earlier=earlier_sites(exclude, contract),
        sites=wanted,
        pilot=pilot,
        basis=basis,
        contract=contract,
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
    if contract != V1:
        record["contract"] = contract
        record["limits"] = {
            "min_chars": C.MIN_CHARS,
            "max_chars": C.MAX_CHARS,
            "max_unproven_claims": CP.MAX_UNPROVEN_CLAIMS,
            "sentence_1_chars": [SV.S1_MIN, SV.S1_MAX],
            "max_numerals": SV.MAX_NUMERALS,
            "max_digits": SV.MAX_DIGITS,
            "narration_max_s": SV.NARRATION_MAX_S,
            "hook_floor": AS.HOOK_FLOOR,
        }
        record["roles"] = roles_record(SPECS[contract])
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
    """Every candidate's fact basis, from the pinned SITES.jsonl: a `ShortsBasis` (names, usable
    images) for contract shorts-v1, the v1 basis for the others."""
    shorts = contract_of(run) == SHORTS
    out: dict[str, C.Basis] = {}
    for row in _pinned_jsonl(run, "SITES.jsonl", "sites_sha256"):
        fields = {
            "site_id": row["site_id"],
            "name": row["name"],
            "country": row["country"],
            "description": row["description"],
            "alt_names": row["alt_names"],
        }
        out[row["site_id"]] = (
            SV.shorts_basis(
                **fields, pool_images=row["pool_images"], image_titles=row["image_titles"]
            )
            if shorts
            else C.basis(**fields)
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
    spec = spec_of(run)
    cut = len(spec.stages) if before is None else spec.stages.index(before)
    out: dict[str, dict[str, dict[str, Any]]] = {stage: {} for stage in spec.stages}
    for stage in spec.stages[:cut]:
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
    #: The adversarial review of a re-check run (contract recheck-v1), once it was answered.
    adversarial: Mapping[str, Any] | None = None

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


def progress(
    site_id: str,
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    spec: Spec = V1_SPEC,
) -> Progress:
    """The site's state, derived from the imported records alone (module doc, "The stages"); every
    check and verification on the path judged the card of the writer record it follows
    (`judging`). `spec` is the contract's chain (`spec_of`)."""
    if spec.name == SHORTS:
        return shorts_progress(site_id, records)
    if spec.name == RECHECK:
        return recheck_progress(site_id, records)
    findings: list[P.Finding] = []
    for writer_stage, checker_stage in CHECK_ROUNDS:
        written = records[writer_stage].get(site_id)
        if written is None:
            return Progress(DUE, writer_stage, tuple(findings))
        if written["card"] is None:  # declined: the contract proved no card can be written
            return Progress(CLEARED, None, tuple(findings), writer=written, reason=NAME_UNDRAWABLE)
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


def chosen_view(written: Mapping[str, Any], rated: Mapping[str, Any]) -> dict[str, Any]:
    """The card of a shorts-v1 round - the variant the rater chose - as the writer record of the
    stages after it: the card, what the writer said of it (basis, anchors, reserve, hook type) and
    the rating it won. Refused when the variant is not the one the rating judged (the write stage
    was imported again with other answers after the rating)."""
    variant = next(v for v in written["variants"] if v["number"] == rated["chosen"])
    if variant["card"] != rated["card"]:
        raise RunError(
            f"{written['site_id']}: STAGE-{rated['stage']} rated another card than "
            f"STAGE-{written['stage']} holds - {written['stage']} was imported again with other "
            "answers after it was rated"
        )
    return {
        "site_id": written["site_id"],
        "stage": written["stage"],
        "kind": "write",
        "batch_id": written["batch_id"],
        "answered_by": written["answered_by"],
        "answered_at": written["answered_at"],
        "model": written["model"],
        "written": variant["written"],
        "card": variant["card"],
        "basis": variant["basis"],
        "anchors": variant["anchors"],
        "reserve": variant["reserve"],
        "hook_type": variant["hook_type"],
        "variant": variant["number"],
        "problems": [],
        "rate": rated,
    }


def rate_findings(rated: Mapping[str, Any]) -> list[P.Finding]:
    """What a failed rating tells the next round: every opening the rater saw with its rating when
    the best of them was below the floor, and the diversity finding of the chosen card."""
    found: list[P.Finding] = []
    below = rated["best_rating"] < AS.HOOK_FLOOR
    for shown in rated["shown"]:
        rating = next(r for r in rated["ratings"] if r["variant"] == shown["number"])
        reasons: list[str] = []
        if below:
            reasons.append(
                f"The hook rater rated its opening {rating['hook']}/5 ({rating['first5']!r}); the "
                f"best opening of a round needs at least {AS.HOOK_FLOOR}."
            )
        if shown["number"] == rated["chosen"]:
            reasons.extend(rated["problems"])
        if reasons:
            found.append(P.Finding(shown["card"], tuple(reasons)))
    return found


def shorts_progress(
    site_id: str, records: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> Progress:
    """A site's state under contract shorts-v1: each round is the writer's three variants, the
    rater's choice of the best and its checking; the chain after it is v1's (`verification_progress`)."""
    findings: list[P.Finding] = []
    for writer_stage, rate_stage, checker_stage in SHORTS_ROUNDS:
        written = records[writer_stage].get(site_id)
        if written is None:
            return Progress(DUE, writer_stage, tuple(findings))
        if written["thin"]:
            return Progress(CLEARED, None, tuple(findings), writer=written, reason=THIN_DECLINED)
        clean = [v for v in written["variants"] if not v["problems"]]
        if not clean:
            findings.extend(P.Finding(v["card"], tuple(v["problems"])) for v in written["variants"])
            continue
        rated = records[rate_stage].get(site_id)
        if rated is None:
            return Progress(DUE, rate_stage, tuple(findings), writer=written)
        if rated["problems"] or rated["best_rating"] < AS.HOOK_FLOOR:
            findings.extend(rate_findings(rated))
            continue
        view = chosen_view(written, rated)
        checked = judging(site_id, records[checker_stage].get(site_id), view)
        if checked is None:
            return Progress(DUE, checker_stage, tuple(findings), writer=view)
        if checked["verdict"] != A.PASSED:
            findings.append(P.Finding(view["card"], PS.findings_of(checked)))
            continue
        return verification_progress(site_id, records, findings, view, checked)
    return Progress(CLEARED, None, tuple(findings), reason=FAILED_REWRITES)


def recheck_progress(
    site_id: str, records: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> Progress:
    """A site's state under contract recheck-v1: the seeded live card, its check, its web
    verification and the adversarial review. Every failure clears; all three passed confirms."""
    written = records[SEEDED_WRITE].get(site_id)
    if written is None:
        raise RunError(f"{site_id}: no seeded card - a re-check run seeds every site (`seed-live`)")
    if written["problems"]:
        found = (P.Finding(written["card"], P.findings_of(written)),)
        return Progress(CLEARED, None, found, writer=written, reason=RECHECK_MECHANICAL)
    checked = judging(site_id, records["check"].get(site_id), written)
    if checked is None:
        return Progress(DUE, "check", (), writer=written)
    if checked["verdict"] != A.PASSED:
        found = (P.Finding(written["card"], P.findings_of(checked)),)
        return Progress(CLEARED, None, found, written, checked, reason=RECHECK_CHECK_FAILED)
    verified = judging(site_id, records[FIRST_VERIFY].get(site_id), written)
    if verified is None:
        return Progress(DUE, FIRST_VERIFY, (), written, checked)
    if verified["verdict"] != VERIFIED:
        found = (P.Finding(written["card"], P.findings_of(verified)),)
        reason = RECHECK_CONTRADICTED if verified["verdict"] == CONTRADICTED else RECHECK_UNPROVEN
        return Progress(CLEARED, None, found, written, checked, (verified,), reason=reason)
    reviewed = judging(site_id, records[ADVERSARIAL].get(site_id), written)
    if reviewed is None:
        return Progress(DUE, ADVERSARIAL, (), written, checked, (verified,))
    if reviewed["verdict"] != A.PASSED:
        found = (P.Finding(written["card"], P.findings_of(reviewed)),)
        return Progress(
            CLEARED,
            None,
            found,
            written,
            checked,
            (verified,),
            RECHECK_ADVERSARIAL_FAILED,
            reviewed,
        )
    return Progress(ACCEPTED, ADVERSARIAL, (), written, checked, (verified,), adversarial=reviewed)


def states(run: Path) -> dict[str, Progress]:
    spec = spec_of(run)
    records = stage_records(run)
    return {site_id: progress(site_id, records, spec) for site_id in bases(run)}


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


def basis_at(stage: str, site: C.Basis, state: Progress, spec: Spec = V1_SPEC) -> C.Basis:
    """The fact basis a stage's question shows: with the first verification's web facts in the
    rewrite after it and, as that rewrite's record holds them, in its check; the description alone
    everywhere else. A re-check run shows every stage the web facts the seeded card's provenance
    recorded (`seed_record`): a claim of the live card may rest on one, as in v1's `check-v`."""
    if spec.name == RECHECK:
        assert state.writer is not None
        return site.with_web(C.WebFact(**fact) for fact in state.writer["web_facts"])
    if stage == VERIFY_REWRITE:
        return site.with_web(web_facts(state.verified[0]))
    if stage == VERIFY_CHECK:
        assert state.writer is not None
        return site.with_web(recorded_web_facts(state.writer, state))
    return site


def shown_variants(written: Mapping[str, Any]) -> list[tuple[int, str]]:
    """The variants of a shorts-v1 writer record the rater is asked about: those that passed the
    mechanical rules, as `(number, final card)`."""
    return [(v["number"], v["card"]) for v in written["variants"] if not v["problems"]]


def contract_prompt(spec: Spec, stage: str, site: C.Basis, state: Progress) -> str:
    """The exact question of one site at one stage of a contract other than v1."""
    shown = basis_at(stage, site, state, spec)
    if spec.name == RECHECK:
        assert state.card is not None
        if stage in spec.checkers:
            return P.checker_prompt(shown, state.card)
        if stage in spec.verifiers:
            return P.judge_prompt(site.name, site.country, state.card)
        assert state.check is not None and state.verify is not None
        return PS.adversarial_prompt(shown, state.card, state.check, state.verify)
    assert isinstance(site, SV.ShortsBasis) and isinstance(shown, SV.ShortsBasis)
    if stage == "write":
        return PS.writer_prompt(site)
    if stage == VERIFY_REWRITE:
        assert state.card is not None
        first = state.verified[0]
        return PS.verify_rewrite_prompt(
            shown, state.card, contradicted_claims(first), unproven_claims(first)
        )
    if stage in spec.writers:
        return PS.rewrite_prompt(site, state.findings)
    assert state.writer is not None
    if stage in spec.raters:
        return PS.rate_prompt(site.name, site.country, shown_variants(state.writer))
    assert state.card is not None
    if stage in spec.verifiers:
        return PS.judge_prompt(site.name, site.country, state.card)
    return PS.checker_prompt(shown, state.card, state.writer["anchors"])


def prompt_for(stage: str, site: C.Basis, state: Progress, spec: Spec = V1_SPEC) -> str:
    """The exact question of one site at one stage."""
    if spec.name != V1:
        return contract_prompt(spec, stage, site, state)
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
def _batches(
    stage: str, due: Mapping[str, Progress], spec: Spec = V1_SPEC
) -> list[tuple[str, list[str]]]:
    """Batches of one stage: writer stages by site id in chunks of 15, verify stages in chunks of 5
    (each card researched on the web; so is an adversarial review), a rating stage in chunks of 25;
    a checker stage keeps each writer batch together, so one checker checks one writer's cards. A
    round of a canary-bearing stage that would be one batch is split in two: the canary of each
    batch is made from a site of the other, so that no site is asked twice in a batch."""
    if stage in spec.writers or stage in (*spec.verifiers, *spec.adversarial, *spec.raters):
        size = BATCH_SIZE
        if stage in (*spec.verifiers, *spec.adversarial):
            size = JUDGE_BATCH_SIZE
        if stage in spec.raters:
            size = RATE_BATCH_SIZE
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
    if stage in spec.canary and len(groups) == 1 and len(groups[0]) > 1:
        half = (len(groups[0]) + 1) // 2  # a blind canary needs a site outside the batch
        groups = [groups[0][:half], groups[0][half:]]
    return [(f"{stage}-{n:03d}", group) for n, group in enumerate(groups, start=1)]


def export_stage(run: Path, stage: str, handoff: Path) -> dict[str, Any]:
    """One stage's round into a handoff directory of its own; refused while an earlier one waits."""
    spec = spec_of(run)
    if stage not in spec.stages:
        raise RunError(f"{stage!r} is no stage of lane WB contract {spec.name}: {spec.stages}")
    if stage in spec.seeded:
        raise RunError(f"stage {stage} is seeded (`seed-live`), never asked")
    if _round(run, stage) is not None:
        raise RunError(f"stage {stage} is exported already: a stage is asked once per run")
    target = _resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise RunError(f"{handoff} is not empty: a round gets a directory of its own")
    current = states(run)
    earlier = spec.stages[: spec.stages.index(stage)]
    waiting = Counter(p.stage for p in current.values() if p.status == DUE and p.stage in earlier)
    if waiting:
        raise RunError(f"earlier stages still wait for their import: {dict(waiting)}")
    due = {site: p for site, p in current.items() if p.status == DUE and p.stage == stage}
    if not due:
        return {"stage": stage, "questions": 0, "note": "nobody is due: no round, next stage"}
    sites = bases(run)
    groups = _batches(stage, due, spec)
    canaries = canary_questions(spec, stage, groups, sites, due)
    for batch_id, members in groups:
        questions = [
            (site_id, prompt_for(stage, sites[site_id], due[site_id], spec)) for site_id in members
        ]
        if batch_id in canaries:  # at a random place: the last question is no giveaway
            canary = canaries[batch_id]
            canary_at = random.SystemRandom().randrange(len(questions) + 1)
            questions.insert(
                canary_at,
                (
                    canary["label"],
                    canary_prompt(
                        spec, stage, sites[canary["site_id"]], due[canary["site_id"]], canary
                    ),
                ),
            )
        for label, prompt in questions:
            OH.export(
                target,
                batch_id=batch_id,
                stage=stage,
                label=label,
                field="card_description",
                prompt=prompt,
            )
    record = {
        "stage": stage,
        "handoff": _shown(handoff),
        "batches": dict(groups),
        "exported_at": _now(),
    }
    if canaries:
        record["canaries"] = canaries
    write_jsonl(run / "ROUNDS.jsonl", [*read_rounds(run), record])
    return {
        "stage": stage,
        "handoff": _shown(handoff),
        "questions": len(due),
        "batches": {batch_id: len(members) for batch_id, members in groups},
        "canaries": len(canaries),
    }


# ------------------------------------------------------------------------------ the canary
def canary_questions(
    spec: Spec,
    stage: str,
    groups: Sequence[tuple[str, list[str]]],
    sites: Mapping[str, C.Basis],
    due: Mapping[str, Progress],
) -> dict[str, dict[str, Any]]:
    """One seeded-defect question for every batch of a checking stage that carries a canary
    (`Spec.canary`): the card of a site OUTSIDE the batch - the first of the next batch - with one
    flaw added (`shorts_v1.canary_card`), asked beside the real questions under a random label that
    has the shape of a site id. The question must be blind: no label, path or repeated site tells a
    checker which question is the seeded one (the mapping lives in `ROUNDS.jsonl` alone). A round
    that holds one site has no other site to take (the card is that site's own, flawed: two
    questions the checker must read to tell apart). A checker that passes it did not read the card:
    the batch is void (`import_stage`, `void_batch`)."""
    if stage not in spec.canary:
        return {}
    found: dict[str, dict[str, Any]] = {}
    for index, (batch_id, _members) in enumerate(groups):
        donor = groups[(index + 1) % len(groups)][1][0]  # one batch: its only site
        card = due[donor].card
        assert card is not None
        kind, defective = SV.canary_card(card, sites[donor], index)
        found[batch_id] = {
            "label": str(uuid.uuid4()),
            "site_id": donor,
            "kind": kind,
            "card": defective,
        }
    return found


def canary_prompt(
    spec: Spec, stage: str, site: C.Basis, state: Progress, canary: Mapping[str, Any]
) -> str:
    """The checker's question about a canary: the batch's own question with the defective card."""
    assert state.writer is not None
    flawed = replace(state, writer={**state.writer, "card": canary["card"]})
    return prompt_for(stage, site, flawed, spec)


# ------------------------------------------------------------------------------ import
def agent_name(batch_id: str) -> str:
    """The name a batch's agent answers under: unique per stage and batch by construction. It names
    the batch, not the agent - that each batch has a new agent is the orchestrator's rule (module
    doc, "Independence")."""
    return f"teaser-{batch_id}"


def _earlier_agents(
    site_id: str,
    stage: str,
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    spec: Spec = V1_SPEC,
) -> set[str]:
    """Every name that wrote, checked or verified the site before `stage` (a reused or mistyped
    name is refused by it; one agent under two batch names is not visible here)."""
    return {
        records[earlier][site_id]["answered_by"]
        for earlier in spec.stages[: spec.stages.index(stage)]
        if site_id in records[earlier]
    }


def parse_contract_answer(
    spec: Spec, stage: str, site: C.Basis, state: Progress, text: str, *, fit: C.Fit
) -> dict[str, Any]:
    """The record of one answer under a contract other than v1: shorts-v1's three variants (each
    with its mechanical problems) or thin decline, the rater's choice, the checker's wider verdict
    and the rewrite after a failed verification; a re-check run's checker and reviewer give v1's
    checker shape."""
    shown = basis_at(stage, site, state, spec)
    offered = [asdict(fact) for fact in shown.web]
    if spec.name == RECHECK:
        record = {"kind": "check", "card": state.card, **A.parse_checker(text, shown).to_dict()}
        return record
    assert isinstance(shown, SV.ShortsBasis)
    if stage == VERIFY_REWRITE:
        rewritten = AS.parse_verify_writer(text, shown, len(contradicted_claims(state.verified[0])))
        variant = rewritten.variant
        return {
            "kind": "write",
            **variant.to_dict(),
            "problems": SV.problems_shorts(
                variant.card, shown, variant.anchors, variant.reserve, fit, basis=variant.basis
            ),
            "repeats": list(rewritten.repeats),
            "web_facts": offered,
        }
    if stage in spec.writers:
        written = AS.parse_writer(text, shown)
        if isinstance(written, AS.Thin):
            return {"kind": "write", "thin": True, "reason": written.reason, "variants": []}
        return {
            "kind": "write",
            "thin": False,
            "variants": [
                {
                    **v.to_dict(),
                    "problems": SV.problems_shorts(
                        v.card, shown, v.anchors, v.reserve, fit, basis=v.basis
                    ),
                }
                for v in written
            ],
        }
    if stage in spec.raters:
        assert state.writer is not None
        offered_cards = shown_variants(state.writer)
        rated = AS.parse_rater(text, offered_cards)
        return {
            "kind": "rate",
            "shown": [{"number": n, "card": c} for n, c in offered_cards],
            **rated.to_dict(),
            "best_rating": rated.best_rating,
            "chosen": rated.best,
            "card": dict(offered_cards)[rated.best],
            "problems": [],
        }
    checked = AS.parse_checker(text, shown)
    record = {"kind": "check", "card": state.card, **checked.to_dict()}
    if stage == VERIFY_CHECK:
        record["web_facts"] = offered
    return record


def parse_answer(
    stage: str, site: C.Basis, state: Progress, text: str, *, fit: C.Fit, spec: Spec = V1_SPEC
) -> dict[str, Any]:
    """The record of one answer: a writer's card and its mechanical problems (after a failed
    verification also the description sentences its contradicted claims repeat), or a check - in
    the rewrite after a failed verification and its check with the web facts the question showed
    (`web_facts`). A verifier's answer needs its pages: `import_stage` records it
    (`verify_record`)."""
    if spec.name != V1:
        return parse_contract_answer(spec, stage, site, state, text, fit=fit)
    shown = basis_at(stage, site, state)
    offered = [asdict(fact) for fact in shown.web]
    if stage in WRITER_STAGES:
        if stage == VERIFY_REWRITE:
            contradicted = len(contradicted_claims(state.verified[0]))
            written = A.parse_verify_writer(text, shown, contradicted)
        else:
            written = A.parse_writer(text, shown)
            if isinstance(written, A.Declined):
                try:
                    proof = C.undrawable_proof(shown, fit=fit)
                except ValueError as exc:
                    raise A.AnswerError(str(exc)) from exc
                return {
                    "kind": "write",
                    "written": None,
                    "card": None,
                    "basis": [],
                    "problems": [],
                    "undrawable": {form: list(glyphs) for form, glyphs in proof.items()},
                }
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
    spec = spec_of(run)
    handoff = _resolve(Path(record["handoff"]))
    check = OH.validate(handoff)
    if not check.ok:
        raise RunError(
            f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
            "answer is validated before anything is imported"
        )
    manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
    canaries = record.get("canaries", {})
    asked = {(b, site) for b, members in record["batches"].items() for site in members}
    asked |= {(batch, canary["label"]) for batch, canary in canaries.items()}
    if set(manifest) != asked:
        raise RunError(f"{record['handoff']}: the manifest is not the round's record")
    sites = bases(run)
    records = stage_records(run, before=stage)
    current = {site: progress(site, records, spec) for site in sites}
    roles = run_roles(run) if spec.roles else {}
    rows: list[dict[str, Any]] = []
    judged: dict[str, tuple[A.Judged, ...]] = {}
    seeded = {(batch, canary["label"]) for batch, canary in canaries.items()}
    for (batch_id, site_id), line in sorted(manifest.items(), key=lambda kv: kv[0][1]):
        if (batch_id, site_id) in seeded:
            continue  # read below, once the real questions are known to be in order
        state = current[site_id]
        if state.status != DUE or state.stage != stage:
            raise RunError(f"{site_id} is not due at {stage}: it is {state.status} {state.stage}")
        prompt = prompt_for(stage, sites[site_id], state, spec)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise RunError(f"{batch_id}/{site_id}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=site_id,
                                prompt=prompt)  # fmt: skip
        if spec.roles:
            why = role_problem(roles, spec.roles[stage], answer.answered_by, answer.model)
            if why is not None:
                raise RunError(f"{batch_id}/{site_id}: {why}")
        if stage in spec.independent:
            others = _earlier_agents(site_id, stage, records, spec)
            if answer.answered_by in others:
                raise RunError(
                    f"{batch_id}/{site_id}: {answer.answered_by} wrote or checked this site before "
                    "- a check or verification is an independent agent's; have the batch answered "
                    "again under its own name"
                )
        try:
            if stage in spec.verifiers:
                judged[site_id] = A.parse_judge(answer.text)
                assert state.check is not None
                short = claims_floor(len(judged[site_id]), len(state.check["claims"]))
                if short is not None:
                    raise A.AnswerError(short)
                parsed: dict[str, Any] = {}
            else:
                parsed = parse_answer(stage, sites[site_id], state, answer.text, fit=fit, spec=spec)
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
                "model": answer.model,
                "prompt_sha256": line["prompt_sha256"],
                **parsed,
            }
        )
    if canaries:
        read_canaries(handoff, stage, spec, roles, canaries, sites, current, fit)
    if stage in spec.raters:
        rate_diversity(rows, records, spec, len(sites))
    failing: list[str] = []
    if stage in spec.verifiers:
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
        progress(site_id, settled, spec)
    write_jsonl(run / f"STAGE-{stage}.jsonl", rows)
    if spec.name == SHORTS and stage in spec.writers and stage != VERIFY_REWRITE:
        return {
            "stage": stage,
            "answers": len(rows),
            "mechanical_failures": sum(
                1 for row in rows if any(v["problems"] for v in row["variants"])
            ),
            "thin": sum(1 for row in rows if row["thin"]),
        }
    if stage in spec.writers:
        return {
            "stage": stage,
            "answers": len(rows),
            "mechanical_failures": sum(1 for row in rows if row["problems"]),
            "undrawable": sum(1 for row in rows if row["card"] is None),
        }
    if stage in spec.raters:
        return {
            "stage": stage,
            "answers": len(rows),
            "best_below_floor": sum(1 for row in rows if row["best_rating"] < AS.HOOK_FLOOR),
            "diversity_failures": sum(1 for row in rows if row["problems"]),
        }
    verdicts = Counter(row["verdict"] for row in rows)
    result: dict[str, Any] = {
        "stage": stage,
        "answers": len(rows),
        "verdicts": dict(sorted(verdicts.items())),
    }
    if stage in spec.verifiers:
        result["transient_failures"] = failing
    if canaries:
        result["canaries"] = len(canaries)
    return result


def rate_diversity(
    rows: list[dict[str, Any]],
    records: Mapping[str, Mapping[str, Mapping[str, Any]]],
    spec: Spec,
    total: int,
) -> None:
    """C16 at the import of a rating: each chosen card against the cards the run has already fixed
    (the ratings of the earlier rounds of other sites, and this import's sites before it in site
    order); a repeated opening is the rating's finding and sends the site to a rewrite."""
    asking = {row["site_id"] for row in rows}
    taken = {
        site_id: rated["card"]
        for stage in spec.raters
        for site_id, rated in records[stage].items()
        if site_id not in asking
    }
    for row in sorted(rows, key=lambda r: r["site_id"]):
        row["problems"] = SV.diversity_problems(row["card"], taken, total)
        taken[row["site_id"]] = row["card"]


def read_canaries(
    handoff: Path,
    stage: str,
    spec: Spec,
    roles: Mapping[str, Mapping[str, str]],
    canaries: Mapping[str, Mapping[str, Any]],
    sites: Mapping[str, C.Basis],
    current: Mapping[str, Progress],
    fit: C.Fit,
) -> None:
    """Every canary answer of a round: in the role's shape, and a FAIL. A checker that passes its
    batch's seeded-defect card did not read the cards - the import is refused with nothing written,
    and the batch is voided and asked again by a new agent (`void_batch`)."""
    passed: list[str] = []
    for batch_id, canary in sorted(canaries.items()):
        site_id = canary["site_id"]
        prompt = canary_prompt(spec, stage, sites[site_id], current[site_id], canary)
        answer = OH.read_answer(
            handoff, batch_id=batch_id, stage=stage, label=canary["label"], prompt=prompt
        )
        if spec.roles:
            why = role_problem(roles, spec.roles[stage], answer.answered_by, answer.model)
            if why is not None:
                raise RunError(f"{batch_id}/{canary['label']}: {why}")
        try:
            parsed = parse_contract_answer(
                spec, stage, sites[site_id], current[site_id], answer.text, fit=fit
            )
        except A.AnswerError as exc:
            raise RunError(
                f"{batch_id}/{canary['label']}: malformed canary answer ({exc})"
            ) from exc
        if parsed["verdict"] == A.PASSED:
            passed.append(batch_id)
    if passed:
        raise CanaryPassed(passed)


# ------------------------------------------------------------------------------ the agent's aids
def judge_floor(run: Path, stage: str, site_id: str) -> int:
    """The fewest claims a web judge of the site may list (`claims_floor`): as many as the check
    that accepted its card listed - the check the verifier follows, or the pilot judge's final
    card's (its provenance)."""
    if stage == JUDGE_STAGE:
        accepted = {r["site_id"]: r for r in read_outcomes(run) if r["status"] == ACCEPTED}
        return len(accepted[site_id]["provenance"]["check"]["claims"])
    state = progress(site_id, stage_records(run, before=stage), spec_of(run))
    assert state.check is not None
    return len(state.check["claims"])


def check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str, *, fit: C.Fit = V.card_fit
) -> dict[str, Any]:
    """The shape of one answer, and for a card its mechanical problems - nothing is recorded."""
    record = _round_of_handoff(run, handoff)
    stage = record["stage"]
    spec = spec_of(run)
    canary = record.get("canaries", {}).get(batch_id)
    asked_label = label if canary is None or label != canary["label"] else canary["site_id"]
    if label not in record["batches"].get(batch_id, []) and asked_label == label:
        raise RunError(f"{batch_id}/{label} is no question of {handoff}")
    if stage == JUDGE_STAGE or stage in spec.verifiers:
        try:
            claims = A.parse_judge(text)
        except A.AnswerError as exc:
            return {"ok": False, "problems": [str(exc)]}
        short = claims_floor(len(claims), judge_floor(run, stage, label))
        return {"ok": short is None, "problems": [] if short is None else [short]}
    site = bases(run)[asked_label]
    state = progress(asked_label, stage_records(run, before=stage), spec)
    try:
        parsed = parse_answer(stage, site, state, text, fit=fit, spec=spec)
    except A.AnswerError as exc:
        return {"ok": False, "problems": [str(exc)]}
    if parsed["kind"] == "rate":
        return {"ok": True, "problems": [], "best": parsed["best"], "hook": parsed["best_rating"]}
    if parsed["kind"] == "write" and spec.name == SHORTS and "variants" in parsed:
        if parsed["thin"]:
            return {"ok": True, "problems": [], "thin": True}
        found = [f"variant {v['number']}: {p}" for v in parsed["variants"] for p in v["problems"]]
        return {
            "ok": not found,
            "problems": found,
            "variants": [
                {"number": v["number"], "length": len(v["card"]), "card": v["card"]}
                for v in parsed["variants"]
            ],
        }
    if parsed["kind"] == "write":
        if parsed["card"] is None:  # declined, and the contract proved it
            return {"ok": True, "problems": [], "card": None, "undrawable": parsed["undrawable"]}
        return {
            "ok": not parsed["problems"],
            "problems": parsed["problems"],
            "card": parsed["card"],
            "length": len(parsed["card"]),
        }
    return {"ok": True, "problems": [], "verdict": parsed["verdict"]}


#: The model ids the recorder accepts, as the brief lists them: an agent names the one it actually
#: runs as, and the list is built from `opus_handoff.NEW_ANSWER_MODELS` so it can never offer an id
#: the recorder would refuse. The brief must never name a narrower set than the one the owner runs
#: (fixed 2026-10-07: this lane still offered only the two Claude ids after MiniMax Code replaced
#: Claude Code on 2026-10-03, so an agent was told to stamp a model that had written nothing); since
#: owner decision D6 (2026-10-08) that set is the three Claude ids again.
MODEL_IDS = " or ".join(OH.NEW_ANSWER_MODELS)

_BRIEF_HEAD = {
    "writer": (
        "You are writer {batch} of lane WB (teaser cards). You write {count} card(s), each for "
        "another site. Write each one on its own, as if it were the only one. Everything a card may "
        "say is in its prompt: no web research, no memory of the site."
    ),
    "checker": (
        "You are checker {batch} of lane WB (teaser cards). You check {count} card(s) written "
        "by another agent, each for another site. Check each one on its own, only against the "
        "sentences in its prompt - not against what you know about the site."
    ),
    "verifier": (
        "You are verifier {batch} of lane WB (teaser cards). You check {count} card(s) "
        "written and checked by other agents against sources on the web, each on its own. Every "
        "verdict rests on a page you opened and quote."
    ),
    "judge": (
        "You are judge {batch} of the lane-WB pilot. You check {count} card(s) against "
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
--model <the model id you run as, exactly as your own system prompt names you: \
{MODEL_IDS}> \
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


#: What the writer of a `DECLINING_STAGES` batch is also told (appended to its fix): the one answer
#: that is not a card, and when it applies. The question's own prompt is unchanged - an export's
#: prompts are pinned by sha256 - so the option lives here, in the agent's instruction.
_BRIEF_UNDRAWABLE = (
    "\n   ONE EXCEPTION, for a site that can have no card: when every one of its NAME FORMS "
    "contains a character the shorts font cannot draw (for example U+02BF ʿ in 'Jabal al-ʿHayn'), "
    "no card can be written: a card with the site's name is refused for that character (a font "
    "problem), a card without the name is refused for the name (a name problem). "
    'Answer that site with exactly {"card": null, "basis": [], "undrawable": true} instead of '
    "the object the prompt specifies, and check it: check-answer accepts it only when it is "
    "true of every name form, and never for a site with a name form the font can draw - it then "
    "lists the forms that can be drawn: write the card with one of them."
)


def _kind(stage: str) -> str:
    """Which agent a stage's batch needs: its brief's head, task and fix."""
    if stage == JUDGE_STAGE:
        return "judge"
    if stage in VERIFY_STAGES:
        return "verifier"
    return "writer" if stage in WRITER_STAGES else "checker"


_ROLE_HEAD = {
    "writer": (
        "You are writer {batch} of lane WB, contract shorts-v1 (nameless teaser cards for "
        "YouTube Shorts). You write {count} site(s), each answered with three variants of its "
        "card. Write each site on its own, as if it were the only one. Everything a card may say "
        "is in its prompt: no web research, no memory of the site."
    ),
    "rewriter": (
        "You are writer {batch} of lane WB, contract shorts-v1. You write {count} card(s) again "
        "after a web check did not verify them, each for another site. Everything a card may say "
        "is in its prompt: no web research, no memory of the site."
    ),
    "rater": (
        "You are hook rater {batch} of lane WB, contract shorts-v1. You rate the openings of the "
        "cards of {count} site(s), each on its own. The prompt shows you only the openings and "
        "the site's name: you do not know and must not look up whether anything is true."
    ),
    "checker": (
        "You are checker {batch} of lane WB. You check {count} card(s) written by another agent, "
        "each for another site. Check each one on its own, only against the sentences in its "
        "prompt - not against what you know about the site."
    ),
    "verifier": (
        "You are verifier {batch} of lane WB. You check {count} card(s) written and checked by "
        "other agents against sources on the web, each on its own. Every verdict rests on a page "
        "you opened and quote."
    ),
    "adversary": (
        "You are the adversarial reviewer {batch} of lane WB's re-check of the cards another model "
        "wrote. You review {count} card(s) that are public today, each on its own, only against "
        "the sentences and the evidence in its prompt."
    ),
    "judge": (
        "You are judge {batch} of the lane-WB pilot. You check {count} card(s) against "
        "sources on the web, each on its own. Every verdict rests on a page you opened and quote."
    ),
}
_ROLE_TASK = {
    "writer": "Write the three variants exactly as the prompt asks.",
    "rewriter": "Write the card exactly as the prompt asks.",
    "rater": "Rate every variant shown, exactly as the prompt asks.",
    "checker": "List the card's claims and decide, exactly as the prompt asks.",
    "verifier": "Research on the web and decide each claim, exactly as the prompt asks.",
    "adversary": "List the card's claims and decide, exactly as the prompt asks.",
    "judge": "Research on the web and decide each claim, exactly as the prompt asks.",
}
_ROLE_FIX = {
    "writer": (
        'It prints "ok" with each variant\'s final text and length, or the problems of each '
        "(length, numbers, the name, the country, the opener, anchors, the reserve, ...). Rewrite "
        'the variants until it prints "ok": true - still only from the prompt\'s sentences. '
        "For a thin description it accepts the decline the prompt offers."
    ),
    "rewriter": (
        'It prints "ok" and the card\'s final text and length, or the problems. Rewrite the card '
        'until it prints "ok": true - still only from the prompt\'s sentences and web facts.'
    ),
    "rater": "It prints the shape problem, if any: fix the shape, never your ratings.",
    "checker": (
        "It prints the shape problem, if any: fix the shape (for example a PASS with an "
        "unsupported claim is a FAIL), never your finding."
    ),
    "verifier": (
        "It prints the shape problem, if any - or that you listed fewer claims than the card "
        "makes: then list every claim, each fact on its own. Fix the shape, never the finding."
    ),
    "adversary": (
        "It prints the shape problem, if any: fix the shape (for example a PASS with an "
        "unsupported claim is a FAIL), never your finding."
    ),
    "judge": (
        "It prints the shape problem, if any - or that you listed fewer claims than the card "
        "makes: then list every claim, each fact on its own. Fix the shape, never the finding."
    ),
}
#: Added to the brief of a web agent (a verifier, the pilot's judge): the site's Wikipedia text is
#: cached once for all lanes (`wiki_cache/INDEX.jsonl`), the other pages are fetched live, and
#: Wikimedia throttles this office IP at four parallel readers (memory 2026-10-07).
WIKI_CACHE = "output/remediation/final-2026-10-08/wiki_cache"
_WEB_NOTE = (
    "\nWEB RESEARCH. Read the site's Wikipedia text from the shared cache first: the label of "
    "each question is the site id; find its lines in {cache}/INDEX.jsonl (site_id, lang, title, "
    "file - the file is relative to {cache}); the page file is JSON with resolved_title, revid and "
    "text. Fetch every other source live, at most a few requests per site. A 403 or 429 is NEVER a "
    "finding: try the page yourself with curl, or quote another page. A quote you give is checked "
    "by a machine against the live page."
)

BRIEF_ROLE = """{head}

You answer as the role **{role}**: your model is **{model_id}**, effort {effort}. If your own \
system prompt names another model, stop now and say so - an answer stamped with any other model is \
refused at import.

This batch needs an agent that has answered no other batch of lane WB (no card written, rated, \
checked, verified or judged): if you have, stop now and say so - the independence of every check \
rests on it.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the \
repository{web_files} - no other batch, nothing else under output/ or docs/, no database, no git \
history.

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
--batch-id {batch} --stage {stage} --label <label> --answered-by {agent} --role {role} \
--model {model_id} --text-file {scratch}/<label>.json
{web_note}
When every question of the batch is recorded, report how many answers you recorded.
"""


def _role_kind(spec: Spec, stage: str) -> str:
    """Which agent a stage of a role-bound contract needs: the key of its brief's head."""
    if stage == JUDGE_STAGE:
        return "judge"
    if stage == VERIFY_REWRITE:
        return "rewriter"
    if stage in spec.writers:
        return "writer"
    if stage in spec.raters:
        return "rater"
    if stage in spec.verifiers:
        return "verifier"
    if stage in spec.adversarial:
        return "adversary"
    return "checker"


def role_brief(run: Path, spec: Spec, record: Mapping[str, Any], batch_id: str) -> str:
    """The instruction of the agent that answers one batch of a role-bound contract: the role, the
    model id the registry fixed for it and the effort - and the `--role`/`--model` flags that
    record the answer under them."""
    stage = record["stage"]
    role = stage_role(spec, stage)
    fixed = run_roles(run)[role]
    kind = _role_kind(spec, stage)
    shown = _shown(Path(record["handoff"]))
    web = kind in WEB_KINDS
    return BRIEF_ROLE.format(
        head=_ROLE_HEAD[kind].format(batch=batch_id, count=len(record["batches"][batch_id])),
        role=role,
        model_id=fixed["model"],
        effort=fixed["effort"],
        task=_ROLE_TASK[kind],
        fix=_ROLE_FIX[kind],
        batch=batch_id,
        stage=stage,
        agent=agent_name(batch_id),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        web_files=" except the Wikipedia cache named below" if web else "",
        web_note=_WEB_NOTE.format(cache=WIKI_CACHE) if web else "",
    )


#: The agents that may read the web: the verifier, the pilot's judge and the adversarial reviewer.
WEB_KINDS = ("verifier", "judge", "adversary")
#: A web agent reads at most this many pages at the same time (Wikimedia throttles this office IP
#: from four parallel readers).
MAX_PARALLEL_WEB = 3


def agent_jobs(run: Path, handoff: Path) -> list[dict[str, Any]]:
    """The workflow-ready jobs of one exported round of a role-bound contract: for each batch the
    agent that answers it - role, the fixed model id, effort, the brief it is given and how many
    such agents may run at the same time. A workflow starts one fresh agent per job
    (`agent(brief, {model, effort})`), waits for them, then `opus_handoff.py validate` and
    `run.py import`."""
    spec = spec_of(run)
    if not spec.roles:
        raise RunError(f"contract {spec.name} has no roles: its answers are not role-bound")
    record = _round_of_handoff(run, handoff)
    stage = record["stage"]
    role = stage_role(spec, stage)
    fixed = run_roles(run)[role]
    web = _role_kind(spec, stage) in WEB_KINDS
    return [
        {
            "batch_id": batch_id,
            "stage": stage,
            "role": role,
            "model": fixed["model"],
            "effort": fixed["effort"],
            "questions": len(members),
            "max_parallel": MAX_PARALLEL_WEB if web else None,
            "brief": role_brief(run, spec, record, batch_id),
        }
        for batch_id, members in sorted(record["batches"].items())
    ]


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the agent that answers one batch."""
    record = _round_of_handoff(run, handoff)
    if batch_id not in record["batches"]:
        raise RunError(f"{batch_id} is no batch of {handoff}")
    spec = spec_of(run)
    if spec.roles:
        return role_brief(run, spec, record, batch_id)
    stage = record["stage"]
    kind = _kind(stage)
    shown = _shown(handoff)
    return BRIEF.format(
        head=_BRIEF_HEAD[kind].format(batch=batch_id, count=len(record["batches"][batch_id])),
        task=_BRIEF_TASK[kind],
        fix=_BRIEF_FIX[kind] + (_BRIEF_UNDRAWABLE if stage in DECLINING_STAGES else ""),
        batch=batch_id,
        stage=stage,
        agent=agent_name(batch_id),
        MODEL_IDS=MODEL_IDS,
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


def _answering_models(site_id: str, *records: Mapping[str, Any]) -> list[str]:
    """The stamps of the answers an accepted card rests on. A record imported before 2026-10-08
    kept no stamp, and the disclosure is never guessed from nothing."""
    stamps = []
    for record in records:
        if "model" not in record:
            raise RunError(
                f"{site_id}: the {record['stage']} record names no model (imported before the stamp "
                "was kept): the card's AI disclosure cannot be derived from it"
            )
        stamps.append(record["model"])
    return stamps


def _provenance(run: Path, site: C.Basis, state: Progress) -> dict[str, Any]:
    """The provenance of an accepted card: its accepting check, its VERIFIED verification (with the
    sha256 of the text it judged) and the web facts its check's claims cite - those the check was
    asked with (a rewrite after a failed verification only). Its `ai_system` is derived from the
    models that wrote, checked and verified it (`model4.ai_system_for`, owner decision D6)."""
    if spec_of(run).name == SHORTS:
        assert isinstance(site, SV.ShortsBasis)
        return _provenance_v3(run, site, state)
    writer, check, verify = state.writer, state.check, state.verify
    assert writer is not None and check is not None and verify is not None
    ai_system = M.ai_system_for(_answering_models(site.site_id, writer, check, verify))
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


def _provenance_v3(run: Path, site: SV.ShortsBasis, state: Progress) -> dict[str, Any]:
    """The version-3 provenance of an accepted shorts-v1 card: the version-2 shape plus the contract,
    the stamp of the model that answered each stage, the hook (declared type, the rater's rating,
    the variant it was), the anchors and the reserve. `shorts_ready` is a site that can be a Short
    whose card also names a reserve and an anchor to cut a picture on. A rewrite after a failed
    verification was not rated: its rating and variant are `None`."""
    writer, check, verify = state.writer, state.check, state.verify
    assert writer is not None and check is not None and verify is not None
    rated = writer.get("rate")
    models = {
        "write": writer["model"],
        "rate": None if rated is None else rated["model"],
        "check": check["model"],
        "verify": verify["model"],
    }
    ai_system = M.ai_system_for(
        _answering_models(site.site_id, *(r for r in (writer, rated, check, verify) if r))
    )
    cited = {s for claim in check["claims"] for s in claim["support"] if s.startswith("W")}
    offered = recorded_web_facts(check, state) if check["stage"] == VERIFY_CHECK else ()
    return CP.build_v3(
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
        models=models,
        hook={
            "type": writer["hook_type"],
            "rating": None if rated is None else rated["best_rating"],
            "variant": None if rated is None else writer["variant"],
        },
        anchors=writer["anchors"],
        reserve=writer["reserve"],
        shorts_ready=(
            site.shorts_eligible and writer["reserve"] is not None and bool(writer["anchors"])
        ),
    )


def outcome_rows(run: Path) -> list[dict[str, Any]]:
    """The final result of every site of the run: an accepted - checked and VERIFIED - card with
    its provenance, or a clear - a failed site, or a listed site without a description whose card
    is to be cleared. Each row carries its verification state (`verification`: the last
    verification's verdict, `None` for a card never verified) and every verification in full."""
    spec = spec_of(run)
    sites = bases(run)
    current = states(run)
    due = sorted(site for site, p in current.items() if p.status == DUE)
    if due:
        raise RunError(f"{len(due)} site(s) are still due: {due[:3]} - finish every stage first")
    seeded_run = (
        json.loads((run / "RUN.json").read_text(encoding="utf-8"))["provenance_run"]
        if spec.name == RECHECK
        else None
    )
    rows: list[dict[str, Any]] = []
    for site_id in sorted(sites):
        site, state = sites[site_id], current[site_id]
        findings = [{"card": f.card, "reasons": list(f.reasons)} for f in state.findings]
        if state.reason == NAME_UNDRAWABLE:  # no card was tried: the proof is the finding
            assert state.writer is not None
            proof = C.undrawable_reason(state.writer["undrawable"])
            findings.append({"card": None, "reasons": [proof]})
        common = {
            "site_id": site_id,
            "name": site.name,
            "desc_sha256": site.desc_sha256,
            "attempts": len(state.findings) + (1 if state.status == ACCEPTED else 0),
            "findings": findings,
            "verification": None if state.verify is None else state.verify["verdict"],
            "verifications": [
                {key: verified[key] for key in _VERIFICATION_KEYS} for verified in state.verified
            ],
        }
        if spec.name == RECHECK:
            # the card this outcome judged and the run that wrote it: the planner clears only that
            # card (`mechanical/teaser.py` `classify`), never a newer one written since the seed
            assert state.writer is not None
            common["seeded_card_sha256"] = CP.text_sha256(state.writer["card"])
            common["seeded_run"] = seeded_run
        if state.status == ACCEPTED:
            writer = state.writer
            assert writer is not None
            rows.append(
                {
                    **common,
                    "status": CONFIRMED if spec.name == RECHECK else ACCEPTED,
                    "reason": None,
                    "card": writer["card"],
                    "writer": {k: writer[k] for k in ("stage", "answered_by", "answered_at")},
                    "provenance": None if spec.name == RECHECK else _provenance(run, site, state),
                }
            )
        else:
            rows.append(
                {
                    **common,
                    "status": KEPT if spec.name == SHORTS else CLEARED,
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
                    "status": KEPT if spec.name == SHORTS else CLEARED,
                    "reason": NO_DESCRIPTION,
                    "card": None,
                    "writer": None,
                    "provenance": None,
                    **(
                        {"seeded_card_sha256": CP.text_sha256(listed["card"]), "seeded_run": None}
                        if spec.name == RECHECK
                        else {}
                    ),
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
    if spec_of(run).name == RECHECK:
        return []  # a re-check run rewrites nothing, so no claim is mapped to a sentence
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
    if spec_of(run).name == RECHECK:
        return recheck_markdown(run, rows)
    accepted = [r for r in rows if r["status"] == ACCEPTED]
    lengths = [len(r["card"]) for r in accepted]
    attempts = Counter(r["attempts"] for r in accepted)
    reasons = Counter(r["reason"] for r in rows if r["status"] != ACCEPTED)
    unaccepted = KEPT if any(r["status"] == KEPT for r in rows) else CLEARED
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
        f"- sites: {len(rows)}; **accepted {len(accepted)}**, {unaccepted} "
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


def recheck_markdown(run: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    """OUTCOMES.md of a re-check run (owner decision D10): the cards that passed every check and the
    cards cleared, each with the finding that cleared it."""
    confirmed = [r for r in rows if r["status"] == CONFIRMED]
    cleared = [r for r in rows if r["status"] == CLEARED]
    reasons = Counter(r["reason"] for r in cleared)
    lines = [
        f"# Lane WB re-check `{run.name}` - outcomes",
        "",
        f"Written {_now()} by `scripts/remediation/teaser/run.py outcomes`. A card is **confirmed** "
        "when the checker passed it, the web verification VERIFIED it and the adversarial reviewer "
        "passed it; it stands. Any other card is cleared (`card-clear-<reason>`).",
        "",
        f"- sites: {len(rows)}; **confirmed {len(confirmed)}**, cleared {len(cleared)} "
        f"({dict(sorted(reasons.items()))})",
        "",
        "## Cleared",
        "",
    ]
    for r in cleared:
        found = "; ".join(reason for f in r["findings"] for reason in f["reasons"])
        lines.append(f"- {r['name']} (`{r['site_id'][:8]}`) `{r['reason']}`: {found}")
    if not cleared:
        lines.append("None.")
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
def judge_prompt_for(run: Path, name: str, country: str, card: str) -> str:
    """The pilot judge's question: the contract's web judge (`prompts_shorts.judge_prompt` asks for
    the identity-bearing claim of a nameless card first)."""
    if contract_of(run) == SHORTS:
        return PS.judge_prompt(name, country, card)
    return P.judge_prompt(name, country, card)


def export_judge(run: Path, handoff: Path) -> dict[str, Any]:
    """Every accepted card of the run - its final, VERIFIED card, the one to be written - to fresh
    independent web judges (the pilot gate, runbook 5.2)."""
    if spec_of(run).name == RECHECK:
        raise RunError("a re-check run has no pilot judge: its cards are confirmed or cleared")
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
                prompt=judge_prompt_for(run, site.name, site.country, cards[site_id]),
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
    spec = spec_of(run)
    roles = run_roles(run) if spec.roles else {}
    sites = bases(run)
    accepted = {r["site_id"]: r for r in read_outcomes(run) if r["status"] == ACCEPTED}
    cards = {site_id: row["card"] for site_id, row in accepted.items()}
    workers = {row["answered_by"] for rows in stage_records(run).values() for row in rows.values()}
    parsed: dict[str, tuple[Any, tuple[A.Judged, ...]]] = {}
    for batch_id, members in record["batches"].items():
        for site_id in members:
            site = sites[site_id]
            prompt = judge_prompt_for(run, site.name, site.country, cards[site_id])
            answer = OH.read_answer(handoff, batch_id=batch_id, stage=JUDGE_STAGE, label=site_id,
                                    prompt=prompt)  # fmt: skip
            if spec.roles:
                why = role_problem(roles, JUDGE_ROLE, answer.answered_by, answer.model)
                if why is not None:
                    raise RunError(f"{batch_id}/{site_id}: {why}")
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


# ------------------------------------------------------------------------------ the re-check run
NOT_OF_RUN = "not-of-run"
CARD_CHANGED = "card-changed"


def seed_reason(row: Mapping[str, Any], provenance_run: str) -> tuple[str, str] | None:
    """Why a curated row is not re-checked: retired, no card, no description, a card of another
    run, or a card that is no longer the one its provenance hashes. `None` for a card to re-check."""
    if row["scope_status"] == RETIRED:
        return RETIRED, "retired (E4): its page answers 410 and its card is never drawn"
    if not row["has_card_row"] or row["card"] is None:
        return NO_CARD_ROW, "no card to re-check"
    if row["description"] is None or not row["description"].strip():
        return NO_DESCRIPTION, "no published description: nothing to check the card against"
    teaser = None if row["card_provenance"] is None else CP.validate(row["card_provenance"])
    if teaser is None or teaser["run"] != provenance_run:
        return NOT_OF_RUN, f"its card was not written by run {provenance_run}"
    if not CP.describes(teaser, row["card"]):
        return CARD_CHANGED, "the live card is not the one its provenance hashes"
    return None


def seed_record(
    row: Mapping[str, Any], provenance_run: str, seeded_at: str, fit: C.Fit
) -> dict[str, Any]:
    """The `write` record of a live card: the card as the writer's answer, its basis the sentences
    its provenance's claims cite, the web facts that provenance recorded (a claim of the card may
    rest on one, and the re-check shows them to every stage) and the mechanical problems v1's
    contract finds in it today. The
    writer's model is MiniMax's: the gap run was answered by MiniMax in every stage (AUDIT_LOG
    2026-10-07), which is why it is re-checked (owner decision D10)."""
    teaser = CP.validate(row["card_provenance"])
    site = C.basis(
        site_id=row["site_id"],
        name=row["name"],
        country=row["country"],
        description=row["description"],
        alt_names=row["alt_names"],
    ).with_web(C.WebFact(**fact) for fact in teaser["web_facts"])
    cited = {s for claim in teaser["check"]["claims"] for s in claim["support"] if s[0] == "S"}
    return {
        "site_id": row["site_id"],
        "stage": SEEDED_WRITE,
        "batch_id": SEED_BATCH,
        "handoff": "",
        "kind": "write",
        "answered_by": f"{SEED_BATCH}:{provenance_run}",
        "answered_at": seeded_at,
        "model": OH.MINIMAX_MODEL,
        "prompt_sha256": CP.text_sha256(row["card"]),
        "written": row["card"],
        "card": row["card"],
        "basis": sorted(cited, key=lambda s: int(s[1:])),
        "web_facts": [dict(fact) for fact in teaser["web_facts"]],
        "problems": C.problems(row["card"], site, fit=fit),
        "seeded": True,
    }


def seed_live(
    run: Path,
    *,
    read: Callable[[Path], None],
    provenance_run: str,
    fit: C.Fit = V.card_fit,
) -> dict[str, Any]:
    """Read production once (read-only) and fix a re-check run (contract recheck-v1, owner decision
    D10) over the live cards written by `provenance_run`: each is recorded as the run's `write`
    stage (`STAGE-write.jsonl`, seeded - never asked), so `check`, `verify` and `adversarial` can
    run over it. Once per run."""
    if (run / "RUN.json").exists():
        raise RunError(f"{run} is selected already: a run's sites are fixed once")
    export = run / "EXPORT.jsonl"
    read(export)
    text = export.read_text(encoding="utf-8")
    try:
        parsed, exported_at = parse_tagged_export(text, ("site",))
    except PlanError as exc:
        raise RunError(str(exc)) from exc
    sites: list[dict[str, Any]] = []
    seeded: list[dict[str, Any]] = []
    listed: list[dict[str, Any]] = []
    for row in sorted(parsed["site"], key=lambda r: str(r["site_id"])):
        why = seed_reason(row, provenance_run)
        if why is not None:
            listed.append(
                {
                    "site_id": row["site_id"],
                    "name": row["name"],
                    "reason": why[0],
                    "detail": why[1],
                    "card": row["card"],
                    "desc_sha256": CP.text_sha256(row["description"] or ""),
                }
            )
            continue
        sites.append(_site_row(row, RECHECK))
        seeded.append(seed_record(row, provenance_run, _now(), fit))
    if not sites:
        raise RunError(f"no live card was written by run {provenance_run}: nothing to re-check")
    record = {
        "run": run.name,
        "selected_at": _now(),
        "exported_at": exported_at,
        "export_sha256": CP.text_sha256(text),
        "sites": len(sites),
        "sites_sha256": write_jsonl(run / "SITES.jsonl", sites),
        "listed_sha256": write_jsonl(run / "LISTED.jsonl", listed),
        "listed": dict(sorted(Counter(r["reason"] for r in listed).items())),
        "seeded_sha256": write_jsonl(run / f"STAGE-{SEEDED_WRITE}.jsonl", seeded),
        "provenance_run": provenance_run,
        "contract": RECHECK,
        "roles": roles_record(RECHECK_SPEC),
        "limits": {"max_unproven_claims": CP.MAX_UNPROVEN_CLAIMS},
    }
    write_json(run / "RUN.json", record)
    return {k: record[k] for k in ("run", "sites", "listed", "provenance_run", "contract")}


def void_batch(
    run: Path, handoff: Path, batch_id: str, *, fit: C.Fit = V.card_fit
) -> dict[str, Any]:
    """Set aside the answers of a batch whose checker passed the batch's seeded-defect card (the
    import named it void): its answer files move to `<handoff>-void/<batch>-<n>/`, evidence kept,
    and the batch can be answered again by a new agent. Refused for a batch that carries no canary
    or whose checker caught it."""
    record = _round_of_handoff(run, handoff)
    stage = record["stage"]
    spec = spec_of(run)
    canary = record.get("canaries", {}).get(batch_id)
    if canary is None:
        raise RunError(f"batch {batch_id} of {handoff} carries no canary: nothing makes it void")
    sites = bases(run)
    current = {site: progress(site, stage_records(run, before=stage), spec) for site in sites}
    roles = run_roles(run) if spec.roles else {}
    try:
        read_canaries(
            _resolve(handoff), stage, spec, roles, {batch_id: canary}, sites, current, fit
        )
    except CanaryPassed:
        pass
    else:
        raise RunError(f"the checker of batch {batch_id} caught its canary: the batch stands")
    root = _resolve(handoff)
    void_root = root.with_name(root.name + "-void")
    number = 1
    while (void_root / f"{batch_id}-{number}").exists():
        number += 1
    target = void_root / f"{batch_id}-{number}"
    moved = 0
    for line in OH.read_manifest(root, batch_id).values():
        answer = root / line["answer_path"]
        if answer.exists():
            destination = target / line["answer_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            answer.replace(destination)
            moved += 1
    return {"voided": batch_id, "answers_moved": moved, "to": _shown(target)}


def escalate_role(run: Path, role: str, verdict_file: Path) -> dict[str, Any]:
    """Move one role of a run up one tier after its calibration failed (owner decision D6): the
    verdict (`calibrate_claude.py verdict` or `teaser/calibrate.py evaluate`) names the tier move;
    it is written into `RUN.json["roles"]` and `["escalations"]`. Refused for a verdict of another
    role or one that did not fail, for a move other than one tier up, while `roles.ROLES` still
    names the old model (the recorder `opus_handoff.py answer --role R --model M` checks the
    registry: commit the `ROLES` edit first - `roles.py` - then escalate the runs that have not
    begun the role), and once a stage of the role was exported - its answers were given by the
    model the run recorded."""
    spec = spec_of(run)
    verdict = json.loads(_resolve(verdict_file).read_text(encoding="utf-8"))
    move = verdict.get("tier_move")
    if verdict.get("role") != role or verdict.get("passed") is not False or move is None:
        raise RunError(
            f"{verdict_file} is not a failed calibration of role {role} with a tier move"
        )
    recorded = run_roles(run)
    if role not in recorded:
        raise RunError(f"role {role} answers no stage of this run (its roles: {sorted(recorded)})")
    if move["from"] != recorded[role]["model"] or move["to"] != RO.next_tier(move["from"]):
        raise RunError(
            f"the tier move {move['from']} -> {move['to']} does not follow the model recorded "
            f"for role {role} ({recorded[role]['model']}) by one tier"
        )
    if RO.role(role).model != move["to"]:
        raise RunError(
            f"role {role} is registered to {RO.role(role).model}, not {move['to']}: the recorder "
            "(`opus_handoff.py answer --role`) would refuse the escalated model - commit the "
            "edit of `roles.ROLES` first (a registry change is sealed and calibrated again)"
        )
    begun = [r["stage"] for r in read_rounds(run) if spec.roles.get(r["stage"]) == role]
    if begun or (role == JUDGE_ROLE and _round(run, JUDGE_STAGE) is not None):
        raise RunError(f"role {role} has answered rounds already ({begun}): it is not moved")
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    record["roles"][role] = {**recorded[role], "model": move["to"]}
    record.setdefault("escalations", []).append(
        {**move, "at": _now(), "verdict": _shown(verdict_file)}
    )
    write_json(run / "RUN.json", record)
    return {"role": role, "model": move["to"], "from": move["from"]}


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _read_production(path: Path, contract: str = V1) -> None:
    write_tagged_export(export_script(contract), path)


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
        ("agents", "the workflow jobs of an exported round: role, model, effort, brief"),
        ("void-batch", "set aside a batch whose checker passed its seeded-defect card"),
        ("seed-live", "record the live cards of a run as a re-check run (read-only)"),
        ("escalate", "move a role up one tier after a failed calibration"),
    ):
        commands[name] = sub.add_parser(name, help=helps)
        commands[name].add_argument("--run", required=True, type=Path)
    for name in ("export", "check-answer", "brief", "judge-export", "agents", "void-batch"):
        commands[name].add_argument("--handoff", required=True, type=Path)
    for name in ("export", "import"):
        commands[name].add_argument("--stage", required=True, choices=ALL_STAGES)
    for name in ("check-answer", "brief", "void-batch"):
        commands[name].add_argument("--batch-id", required=True)
    commands["seed-live"].add_argument("--provenance-run", required=True)
    commands["escalate"].add_argument("--role", required=True, choices=sorted(RO.ROLES))
    commands["escalate"].add_argument("--verdict", required=True, type=Path)
    commands["select"].add_argument(
        "--contract",
        choices=(V1, SHORTS),
        default=V1,
        help="the contract of the run: v1 (named cards) or shorts-v1 (nameless Shorts cards)",
    )
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
                    read=lambda path: _read_production(path, args.contract),
                    sites_file=None if args.sites is None else _resolve(args.sites),
                    pilot=None if args.pilot is None else (args.pilot, args.seed),
                    exclude=args.exclude_run,
                    basis=None if args.basis is None else set(args.basis),
                    contract=args.contract,
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
        elif args.command == "agents":
            _print(agent_jobs(run, args.handoff))
        elif args.command == "void-batch":
            _print(void_batch(run, args.handoff, args.batch_id))
        elif args.command == "seed-live":
            _print(
                seed_live(
                    run,
                    read=lambda path: _read_production(path, RECHECK),
                    provenance_run=args.provenance_run,
                )
            )
        elif args.command == "escalate":
            _print(escalate_role(run, args.role, args.verdict))
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
