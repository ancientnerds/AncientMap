"""Lane WC's command line: the fresh read, the questions, the answers, the re-ask, the gate plan and
the pilot's independent judge. Owner decision O5 of 2026-09-26; the runbook, with every command in
order, is `docs/procedures/SENTENCE_CHECK.md`.

    PY=/c/PythonProjects/AncientMap/.venv/Scripts/python.exe
    C="$PY scripts/remediation/wc/cli.py"
    $C read               --run-dir R                    # the one read-only production SELECT
    $C export             --run-dir R --handoff H [--pilot 20 --seed S | --limit N]
                          [--exclude F] [--after R0 ...]
    $C brief              --run-dir R --handoff H --batch-id B
    $C check-answer       --run-dir R --handoff H --batch-id B --label SITE --text-file F
    $C import             --run-dir R --handoff H        # after opus_handoff.py validate
    $C export-reask       --run-dir R --handoff H2       # the sentences whose quotes failed, once
    $C verify-export      --run-dir R --handoff HV       # verify: every site that kept a sentence
    $C verify-brief       --run-dir R --handoff HV --batch-id B
    $C verify-check-answer --run-dir R --handoff HV --batch-id B --label SITE --text-file F
    $C verify-import      --run-dir R --handoff HV       # after opus_handoff.py validate
    $C verify-export      --run-dir R --handoff HV2      # verify2: the texts a drop changed, once
    $C build              --run-dir R --first-batch N    # FINAL, SUMMARY, WC4.jsonl (the gate plan)
    $C judge-export       --run-dir R --handoff HJ       # the pilot's independent judge
    $C judge-brief        --run-dir R --handoff HJ --batch-id B
    $C judge-check-answer --run-dir R --handoff HJ --batch-id B --label SITE --text-file F
    $C judge-import       --run-dir R --handoff HJ       # RESULT.json, JUDGE_EXIT=
    $C defect-sites       --run-dir R --defects D ... --out F   # a site list from WB's defects
    $C verify-void        --run-dir R [--apply] [--tag T]       # MiniMax verify answers moved aside
    $C defect-kept-sites  --run-dir R --from R0 ... --out F     # standing defect claims -> a list
    $C export --sites F --defects F.report.json --adversarial   # the adversarial second check
    $C defect-closure     --run-dir R                           # what it decided, for AUDIT_LOG
    $C minimax-sites      --run-dir R --from R0 ... --out F     # MiniMax-touched texts that stand
    $C export --sites F   ...                            # a site-list run (kind wc-list)
    $C export --wn        ...                            # lane WN: write the missing descriptions

**The population** (`population`): every curated site of the read that is not retired, carries a
description, and whose text is not Phase 4's and not one lane WC checked before - the 2026-03 AI
texts (lane L's marking, or `march-unmarked`: lane L's rule claims the text and no marking is stored)
and the `unclaimed` old texts no marking claims (HUMAN_ONLY D7; they are checked alike and still
claim nothing, `wc4.provenance_after`). Each site's `marking` is `wc4.old_marking`. Listed and never
asked, each under its reason: `retired`, `no-description`, `phase4-text` (a full Phase-4
provenance), `checked-before`, `provenance-unreadable`, `provenance-hash-differs` (D4 already
fails), `not-splittable`, `excluded` (`--exclude`), `earlier-run` (`--after`). The read is always
fresh, so the sites the Phase-4 v3 run (WA) rewrote have left the population by themselves.

**One question per site**, in batches of `--batch-size` sites (default 5) named `wc-NNNN`, stage
`check`, label the site id: the site's stored values (to identify it, not as evidence), its
sentences (`wc4.checked_sentences`) and the frozen question (`prompts.CHECK_QUESTION`). One Opus
agent per batch answers every question of its batch (`brief`), checks each answer with
`check-answer` (shape, fetch, quote check, the text it would leave) and records it with
`opus_handoff.py answer`. Batches are independent; an agent's scratch files are its batch's own
(`<handoff>-scratch/<batch>/`) and so are its fetched pages (`<handoff>/<batch>/pages/`).

**The import** (`import`) validates the round (`opus_handoff.validate`), rebuilds every exported
prompt byte for byte, parses each answer (`answers.parse_check`), fetches every quoted page once
into the run's own page store (`<run>/pages/`) and checks every quote (`answers.quote_outcomes`).
It never reads the batch agents' page stores (`<handoff>/<batch>/pages/`, which `check-answer`
fills from the agent's session and the agent could write): what counts rests only on pages the
import fetched itself, as in the acceptance (`acceptance/judge.py`, `<run>/judging/pages/`). A page
is fetched once per run, so a page that failed in round 1 stays failed in the re-ask. A kept sentence
counts only when every quote it gives is found (and none is on a copy of our text); a DROP counts
as given. A sentence that does not count - or every asked sentence of an answer that is not in
shape - is re-asked once (`export-reask`, round 2, with what failed); after that round it is dropped
(`unverified`). `build` refuses while a re-ask is due or unimported. A round is imported once, and
no check round once a verification round is exported: the verifiers were shown the text it gives.

**The verification** (`verify-*`, owner decisions O5 and O2; the pilots of 2026-09-27 let one error
in 50-60 kept sentences through a single check): after the check rounds, every site whose check kept
a sentence goes to an independent Opus verifier (stage `verify`, batches `verify-NNNN` of
`--batch-size` sites) - the judge's question, answer shape and machine quote check
(`prompts.VERIFY_QUESTION`, `answers.parse_verify`, `answers.check_quotes`) applied to the kept text
as it will be published: the trims applied, in order, the dropped sentences shown as context. Every
kept sentence is SUPPORTED (stays), UNSUPPORTED or WRONG (dropped - a WRONG whether code found its
quote or not); an incoherent text names its broken sentences (dropped), and one with none named is
cleared; then the pronoun rule. A text a drop changed goes to a new verifier once (`verify2`,
batches `verify2-NNNN`): coherent and every sentence SUPPORTED keeps it, anything else clears it
(`wc4.run_verification`). The import refuses a verifier whose name checked the site or verified it
in round 1; it fetches every quoted page once into `<run>/verify/pages/`. Nothing is added back.
Each round is tied to what its question showed (the review of 2026-09-27): the import records the
sha256 of the text as published (`text_sha256`), which every reader of the record holds to what the
check composes (`wc4.run_verification`), and `build` asks every round's question again against its
`prompt_sha256` - a check that moved after a verifier answered is never built.

**The build** (`build`): refused while a check or verification round is due. Per site, each
sentence's decision from the last round that asked it, the pronoun rule (`wc4.follow_drops`), the
verification (`wc4.apply_verification`), the composed text and citations (`wc4.compose`), the check
record naming the verifiers and the verified text's sha256, and the raw_data (`wc4.check_record`,
`wc4.written_raw_data`), the journal evidence (every decision with its decision before the
verification, the agent's quotes and what the check said of each, every answer's sha256, the
verification record), then the gate plan `WC4.jsonl` - batches of `wc4.BATCH_SIZE` sites from
`--first-batch`, marked `wc4.PLAN_MARK` - which `write_gate4.py --group WC --wc-plan` writes in
steps.

**Chunks** (`export --limit N`): the first N sites of the population in site-id order, the next
chunk naming every earlier chunk not yet written in `--after`; each chunk is its own run, imported,
built and written on its own, so the writes start while later chunks are still being answered.

**Three kinds of run** (`run_kind`, recorded by `export` in `POPULATION.json` as `kind`; a run
exported before 2026-10-01 records none and is a plain `wc` run, every prompt and brief of which is
byte for byte what it was):

* `wc` - the plain run above;
* `wc-list` (`export --sites FILE`, owner decision 2026-10-01, `docs/procedures/SENTENCE_CHECK.md`
  section 11) - the same check, verification, build and write over exactly the listed curated sites,
  whatever their text is: a March text, a Phase-4 text (`wc4.Marking.PHASE4`: kept or dropped by
  sentence, never trimmed, its provenance the old one filtered to the kept sentences; a text whose
  check keeps every sentence is not written) or a text a check kept before (its record replaced).
  `defect-sites` builds the list from WB's `DESCRIPTION_DEFECTS.jsonl` of every run;
* `wn` (`export --wn`, owner decision "Neu aus Webquellen", section 12) - lane WN: for each curated
  site without a description, round 1 is a **write** round (stage `write`, batches `wn-NNNN`, the
  question `prompts_sonnet.WRITE_QUESTION`): a Sonnet agent writes 2 to 6 sentences, each on verbatim
  quotes (`answers.parse_write`), `check-answer` machine-checks them, `import` fetches the pages itself
  and records every written sentence as a KEEP on its quotes in the check round's own format - so
  the verification (`verify`, `verify2`), the build, the judge and the writer are WC's, unchanged,
  over the sentences that were written (`DRAFTS.jsonl`, merged into `read_sites`). A site whose text
  ends empty is not planned: it stays without a description. No re-ask: a sentence whose quote is not
  found at the import is dropped (`unverified`).

**The pilot** (`export --pilot 20 --seed S`): a seeded draw of the population, run end to end; its
post-verification result is measured by a fresh Opus judge (`judge-*`: every kept sentence
SUPPORTED, UNSUPPORTED or WRONG, every dropped one DROP_OK or DROP_WRONG, the kept text coherent or
not; quotes machine-checked; a judge who checked or verified any site of the run does not count)
against the thresholds `J_THRESHOLDS`, before the mass run: `judge-import` prints `JUDGE_EXIT=0` for
a pass. The judged plan is tied to the plan the gate writes (`plan_sha256`, `pilot_approval`).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402 - the one contract every model answer goes through
import roles as RO  # noqa: E402 - the roles that answer (owner decision D6, 2026-10-08)
import run_files as RF  # noqa: E402 - the shared clock and JSON writers
from opus_audit import quotes as Q  # noqa: E402
from phase3 import write_stage as W  # noqa: E402 - the read-only psql seam
from phase3.run import read_jsonl  # noqa: E402
from phase4 import audit4, plan4, revert4, wc4  # noqa: E402 - the draw, the read, site ids, WC
from phase4 import model4 as M  # noqa: E402

from wc import answers as A  # noqa: E402
from wc import prompts as P  # noqa: E402
from wc import prompts_sonnet as P2  # noqa: E402 - the texts added 2026-10-01 (site lists, WN)
from wc import void as V  # noqa: E402 - `verify-void`: MiniMax verification answers moved aside

STAGE = "check"
JUDGE_STAGE = "judge"
#: The kinds of run (`run_kind`) and lane WN's round-1 stage, batch prefix and draft file.
KIND_WC, KIND_LIST, KIND_WN = "wc", "wc-list", "wn"
WRITE_STAGE = "write"
WRITE_PREFIX = "wn"
DRAFTS_FILE = "DRAFTS.jsonl"
#: The import's own page store, under the run (the judge's: `<run>/judge/pages/`).
PAGES_DIR = "pages"
BATCH_SIZE = 5
MAX_ROUNDS = 2  #: the first round and one re-ask round, then a failing sentence is dropped
ROWS_FILE = "ROWS.jsonl"
READ_FILE = "READ.json"
POPULATION_FILE = "POPULATION.json"
SITES_FILE = "SITES.jsonl"
ROUNDS_FILE = "ROUNDS.jsonl"
FINAL_FILE = "FINAL.jsonl"
SUMMARY_FILE = "SUMMARY.json"
PLAN_FILE = "WC4.jsonl"
JUDGE_DIR = "judge"
#: The roles that answer lane WC (`roles.ROLES`, owner decision D6 of 2026-10-08): the check rounds
#: and lane WN's write round are the fact checker's, the verification rounds the web verifier's, the
#: judge's questions the pilot judge's, the adversarial second check the adversarial role's. A
#: brief takes its `--model`, `--role` and the agent's family from the registry, and the imports
#: refuse an answer that names another role or carries another role's stamp (`_require_role`).
ROLE_CHECK, ROLE_VERIFY, ROLE_JUDGE = "fact_checker", "web_verifier", "pilot_judge"
ROLE_ADVERSARIAL = "adversarial"
#: The shared Wikipedia cache of the final repair (`tools/wiki_cache.py`): the briefs send the
#: agents to it first, so no more than a few of them fetch Wikipedia live at the same time.
WIKI_CACHE = REPO / "output" / "remediation" / "final-2026-10-08" / "wiki_cache"
#: The verification's directory under the run: `round-<n>/ROUND.json` (the export's record: its
#: handoff, batches and the sentences each question showed), `round-<n>/VERIFIED.jsonl` (the
#: import's record per site) and `pages/` (the pages the verifiers quoted, fetched by code).
VERIFY_DIR = "verify"
VERIFY_STAGES = wc4.VERIFY_STAGES
#: The lanes whose provenance is a full Phase-4 one: their text is Phase 4's, never WC's.
FULL_LANES = frozenset(lane.value for lane in M.LANE_CHANGES)
#: The pilot's pass mark, sealed with the lane (docs/procedures/SENTENCE_CHECK.md): no kept
#: sentence a judge shows WRONG with a found quote, at most 5 % of kept sentences UNSUPPORTED (a
#: WRONG whose quote was not found counts here), and no site whose kept text is incoherent.
J_THRESHOLDS = {"wrong": 0, "unsupported_share": 0.05, "incoherent": 0}
#: A WN pilot's size and its minimum sample (a design number, not an owner decision, measured on
#: no corpus): the pilot draws 20 sites - or the whole population when it is smaller - and is judged
#: only if at least half of the drawn sites ended with a text the judge could judge, and as many
#: kept sentences as that (every judged text keeps at least one). An empty site gates nothing, but a
#: pilot in which most sites ended empty measured nothing: it cannot approve a mass plan.
WN_PILOT_SITES = 20
WN_PILOT_MIN_WITH_TEXT = 0.5

#: The one production read: the columns of Phase 4's plan read (`plan4.PLAN_SQL`, so a WC site is
#: the same `PlanSite` lane L and P4 plan from) and the scope status, in one statement.
WC_SQL = plan4.PLAN_SQL.replace(
    "SELECT u.id::text AS id, ", "SELECT u.id::text AS id, u.scope_status, ", 1
)
if WC_SQL == plan4.PLAN_SQL:  # pragma: no cover - a changed plan read is a contract change
    raise ImportError("plan4.PLAN_SQL no longer opens with the site id: lane WC's read is stale")


class WcRunError(ValueError):
    """The run directory, a round or an answer is not what the lane needs: the command stops."""


# ------------------------------------------------------------------------------------ files
# The clock and the writers are the shared ones (`run_files`); a path is shown relative to the
# repository where it lies inside it, and a file's sha256 is that of its bytes as they are.
def _shown(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids(path: Path) -> set[str]:
    """One site id per line (blank lines skipped), each a lowercase, hyphenated UUID
    (`revert4.check_site`); anything else stops the command."""
    ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            ids.add(revert4.check_site(text))
        except revert4.RevertRefused as exc:
            raise WcRunError(f"{path}:{number}: {exc}") from None
    return ids


# ------------------------------------------------------------------------------------ the read
def cmd_read(run: Path, *, runner: W.SqlRunner = W.run_sql, host: str = W.SSH_HOST) -> dict:
    """The one read-only SELECT (`WC_SQL`): every curated row, as Phase 4 reads it, with its scope
    status. Written to `ROWS.jsonl`; `READ.json` records when and the file's sha256."""
    rows = W._json_rows(runner(WC_SQL, host=host))
    RF.write_jsonl(run / ROWS_FILE, rows)
    record = {"read_at": RF.now(), "rows": len(rows), "sha256": _sha256(run / ROWS_FILE)}
    RF.write_json(run / READ_FILE, record)
    return record


# ------------------------------------------------------------------------------------ the population
def population(
    rows: Sequence[Mapping[str, Any]],
    *,
    excluded: set[str],
    earlier: set[str],
    kind: str = KIND_WC,
    only: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """The sites to ask, in site-id order (each `{site_id, name, marking, sentences, plan_site}`),
    and every other curated site of the read, by the reason it is not asked. `kind` is the run's
    (`run_kind`); `only` is a site-list run's list (every other site is left out and not listed: the
    list is the population's frame)."""
    asked: list[dict[str, Any]] = []
    listed: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda row: row["id"]):
        if only is not None and row["id"] not in only:
            continue
        site_row = {key: value for key, value in row.items() if key != "scope_status"}
        site = plan4.plan_site(site_row, flags=frozenset())
        reason, marking, sentences = _classify(
            row, site, excluded=excluded, earlier=earlier, kind=kind
        )
        if reason is not None:
            listed.setdefault(reason, []).append(site.site_id)
            continue
        asked.append(
            {
                "site_id": site.site_id,
                "name": site.name,
                "marking": marking,
                "sentences": list(sentences),
                "plan_site": site.to_dict(),
            }
        )
    return asked, listed


def _classify(
    row: Mapping[str, Any],
    site: M.PlanSite,
    *,
    excluded: set[str],
    earlier: set[str],
    kind: str = KIND_WC,
) -> tuple[str | None, str | None, tuple[str, ...]]:
    if row["scope_status"] == "retired":
        return "retired", None, ()
    if kind == KIND_WN:
        return _classify_empty(site, excluded=excluded, earlier=earlier)
    if site.description is None or not site.description.strip():
        return "no-description", None, ()
    # a site-list run asks a Phase-4 text, a lane-N text and a text a check kept before as well
    listed = kind == KIND_LIST
    raw = site.raw_data or {}
    if wc4.CHECK_KEY in raw and not listed:
        return "checked-before", None, ()
    if M.PROVENANCE_KEY in raw:
        stored = raw[M.PROVENANCE_KEY]
        if not listed and isinstance(stored, dict) and stored.get("lane") in FULL_LANES:
            return "phase4-text", None, ()
        try:
            provenance = (
                M.provenance_from_dict(stored) if listed else M.LegacyProvenance.from_dict(stored)
            )
        except ValueError:
            return "provenance-unreadable", None, ()
        if provenance.desc_sha256 != M.text_sha256(site.description):
            return "provenance-hash-differs", None, ()
    if site.site_id in excluded:
        return "excluded", None, ()
    if site.site_id in earlier:
        return "earlier-run", None, ()
    try:
        sentences = wc4.checked_sentences(site.description)
    except wc4.WcError:
        return "not-splittable", None, ()
    marking = wc4.old_marking(site, listed=listed)
    if marking is wc4.Marking.PHASE4:
        # a Phase-4 text keeps its provenance filtered to the kept sentences: one published sentence
        # per checked sentence, or the two cannot be matched (`wc4.filtered_provenance`)
        published = M.Provenance.from_dict(raw[M.PROVENANCE_KEY]).sentences
        if len(published) != len(sentences):
            return "provenance-misaligned", None, ()
    return None, marking.value, sentences


def _classify_empty(
    site: M.PlanSite, *, excluded: set[str], earlier: set[str]
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Lane WN's population: a site without a description (NULL or blank, `wc4.is_empty`) that
    carries none of WC's keys (a cleared site has none; `stale-keys` is a broken state of another
    lane, never asked). Its marking is `none` and it has no sentences yet."""
    if not wc4.is_empty(site.description):
        return "has-description", None, ()
    if wc4.WC_KEYS & (site.raw_data or {}).keys():
        return "stale-keys", None, ()
    if site.site_id in excluded:
        return "excluded", None, ()
    if site.site_id in earlier:
        return "earlier-run", None, ()
    return None, wc4.Marking.NONE.value, ()


# ------------------------------------------------------------------------------------ the prompts
def _year(year: int) -> str:
    return f"{-year} BC" if year < 0 else f"AD {year}"


def site_block(site: M.PlanSite) -> str:
    period = "not stored"
    if site.period_start is not None and site.period_end is not None:
        period = f"{_year(site.period_start)} to {_year(site.period_end)}"
    elif site.period_start is not None:
        period = f"from {_year(site.period_start)}"
    elif site.period_end is not None:
        period = f"until {_year(site.period_end)}"
    lines = [
        f"name: {site.name}",
        f"other names: {', '.join(site.aliases) if site.aliases else 'none'}",
        f"country: {site.country or 'not stored'}",
        f"site type: {site.site_type or 'not stored'}",
        f"stored period: {period}",
        f"coordinates: {site.lat:.5f}, {site.lon:.5f} (latitude, longitude)",
        f"stored source: {site.source_url or 'none'}",
        f"Wikidata item: {site.wikidata_qid or 'none'}",
        f"English Wikipedia title: {site.enwiki_title or 'none'}",
        "(The stored values identify the site - above all its coordinates. They are no evidence "
        "for a sentence and may themselves be wrong.)",
    ]
    return "\n".join(lines)


def _asked_text(asked: Sequence[int]) -> str:
    return ", ".join(f"S{n}" for n in asked)


def _trims(entry: Mapping[str, Any]) -> bool:
    """May the agent trim a sentence of this site's text? Not a Phase-4 text: its provenance cannot
    follow a cut, so its sentences are kept whole or dropped (`wc4.Marking.PHASE4`)."""
    return entry["marking"] != wc4.Marking.PHASE4.value


def write_prompt(entry: Mapping[str, Any]) -> str:
    """Lane WN's question about one site: write its description from reputable web pages."""
    return P2.WRITE_QUESTION.format(
        site=site_block(M.PlanSite.from_dict(entry["plan_site"])),
        site_id=entry["site_id"],
        min_sentences=A.MIN_SENTENCES,
        max_sentences=A.MAX_SENTENCES,
        min_chars=A.MIN_SENTENCE_CHARS,
        max_chars=A.MAX_SENTENCE_CHARS,
        max_run=A.MAX_SHARED_RUN,
    )


def check_prompt(
    entry: Mapping[str, Any],
    asked: Sequence[int],
    failures: Mapping[str, Sequence[str]],
    kind: str = KIND_WC,
    adversarial: bool = False,
) -> str:
    """The exact question about one site: round 1 asks every sentence and has no failures; the
    re-ask round asks the failed ones and says what failed (`failures`: sentence number -> why). A
    site-list run asks `prompts_sonnet.CHECK_QUESTION_LISTED` (the origin of the text said as it is,
    no trim for a Phase-4 text) - an adversarial second check of it
    `prompts_sonnet.CHECK_QUESTION_ADVERSARIAL` -, lane WN's round 1 the write question
    (`write_prompt`)."""
    if kind == KIND_WN:
        return write_prompt(entry)
    site = M.PlanSite.from_dict(entry["plan_site"])
    sentences = "\n".join(f"S{n}: {text}" for n, text in enumerate(entry["sentences"], start=1))
    reask = ""
    if failures:
        lines = [f"S{n}: " + "; ".join(failures[str(n)]) for n in asked]
        reask = P.REASK_BLOCK.format(failures="\n".join(lines))
    if kind == KIND_LIST:
        return (P2.CHECK_QUESTION_ADVERSARIAL if adversarial else P2.CHECK_QUESTION_LISTED).format(
            site=site_block(site),
            sentences=sentences,
            reask=reask,
            asked=_asked_text(asked),
            site_id=entry["site_id"],
            origin=P2.ORIGINS[entry["marking"]],
            defects=defects_block(entry.get("defects")),
            trims="" if _trims(entry) else P2.NO_TRIM,
        )
    return P.CHECK_QUESTION.format(
        site=site_block(site),
        sentences=sentences,
        reask=reask,
        asked=_asked_text(asked),
        site_id=entry["site_id"],
    )


# ------------------------------------------------------------------------------------ the rounds
def run_kind(run: Path) -> str:
    """The kind of the run (`KIND_WC`, `KIND_LIST`, `KIND_WN`), as `export` recorded it. A run
    exported before 2026-10-01 records none: it is a plain WC run."""
    record = json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))
    return record.get("kind", KIND_WC)


def run_adversarial(run: Path) -> bool:
    """Is the run an adversarial second check (`export --adversarial`)? Its list run's check question
    opens as `prompts_sonnet.ADVERSARIAL_OPENING` and its check answers are the adversarial role's.
    A run exported before records none: it is not."""
    record = json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))
    return bool(record.get("adversarial", False))


def check_role(run: Path) -> str:
    """The role that answers the run's check rounds (and lane WN's write round)."""
    return ROLE_ADVERSARIAL if run_adversarial(run) else ROLE_CHECK


def _role_fields(role_name: str) -> dict[str, str]:
    """What a brief prints of the role that answers it - the family of its model, the model id, the
    role - and the note on the shared Wikipedia cache. The cache must exist: a brief that sends an
    agent to a directory that is not there would send it to the live site, which is what the cache
    is for."""
    entry = RO.role(role_name)
    index = WIKI_CACHE / "INDEX.jsonl"
    if not index.is_file():
        raise WcRunError(
            f"the shared Wikipedia cache is missing: {index} does not exist "
            "(tools/wiki_cache.py fills it)"
        )
    return {
        "family": OH.ANSWER_FAMILIES[entry.model].capitalize(),
        "model": entry.model,
        "role": role_name,
        "wiki_cache_note": P.WIKI_CACHE_NOTE.format(wiki_cache=_shown(WIKI_CACHE)),
    }


def _agent_family(role_name: str) -> str:
    """The lower-case family of the role's model: the prefix of the agent names (`sonnet-check-...`)."""
    return OH.ANSWER_FAMILIES[RO.role(role_name).model]


def _require_role(answer: OH.Answer, *, role_name: str, where: str) -> None:
    """An answer enters a lane WC round only as the round's role's, from a Claude model: never a
    MiniMax answer (owner decisions D6 and D10; master plan X6 - `verify-void` moves such an answer
    aside and the batch is answered again), never an answer given in another role, never a role's
    answer carrying another model's stamp. An answer recorded before the registry names no role and
    is valid when its stamp is a Claude one."""
    if answer.model == OH.MINIMAX_MODEL:
        raise WcRunError(
            f"{where}: answered by MiniMax ({answer.answered_by}) - a MiniMax answer is never "
            "imported (D10): `verify-void` moves it aside, a Claude agent answers the question again"
        )
    named = RO.role_of(answer.answered_by)
    if named is None and role_name == ROLE_ADVERSARIAL:
        raise WcRunError(
            f"{where}: {answer.answered_by} names no role - an adversarial second check is "
            f"answered with `answer --role {ROLE_ADVERSARIAL}` (Opus, not a recorded legacy name)"
        )
    if named is not None and named != role_name:
        raise WcRunError(
            f"{where}: {answer.answered_by} was given in role {named}, this round is {role_name}'s"
        )
    problem = RO.answer_problem(answer.answered_by, answer.model)
    if problem is not None:
        raise WcRunError(f"{where}: {problem}")


def read_sites(run: Path) -> dict[str, dict[str, Any]]:
    """Every asked site of the run, in the run's order. In a lane-WN run the sentences are the ones
    the agent wrote (`DRAFTS.jsonl`, written by the import of the write round): the sites are
    exported without any."""
    sites = {entry["site_id"]: entry for entry in read_jsonl(run / SITES_FILE)}
    drafts = run / DRAFTS_FILE
    if drafts.exists():
        for row in read_jsonl(drafts):
            sites[row["site_id"]] = {**sites[row["site_id"]], "sentences": row["sentences"]}
    return sites


def read_rounds(run: Path) -> list[dict[str, Any]]:
    path = run / ROUNDS_FILE
    return read_jsonl(path) if path.exists() else []


def round_of(run: Path, handoff: Path) -> dict[str, Any]:
    for record in read_rounds(run):
        if Path(record["handoff"]).resolve() == handoff.resolve():
            return record
    raise WcRunError(f"{handoff} is no round of {run}")


def _export_round(
    run: Path,
    handoff: Path,
    *,
    number: int,
    questions: Sequence[tuple[str, list[int], dict[str, list[str]]]],
    batch_size: int,
) -> dict[str, Any]:
    """Export the round's questions (site id, asked sentences, failures) in batches and record it."""
    if any(Path(r["handoff"]).resolve() == handoff.resolve() for r in read_rounds(run)):
        raise WcRunError(f"{handoff} is already a round of {run}")
    if handoff.exists() and any(handoff.iterdir()):
        raise WcRunError(f"{handoff} is not empty: a round takes a new handoff directory")
    sites = read_sites(run)
    kind = run_kind(run)
    adversarial = run_adversarial(run)
    stage, prefix = (WRITE_STAGE, WRITE_PREFIX) if kind == KIND_WN else (STAGE, "wc")
    batches: dict[str, list[str]] = {}
    for start in range(0, len(questions), batch_size):
        batch_id = f"{prefix}-{start // batch_size + 1:04d}"
        for site_id, asked, failures in questions[start : start + batch_size]:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=site_id,
                field="description",
                prompt=check_prompt(sites[site_id], asked, failures, kind, adversarial),
            )
            batches.setdefault(batch_id, []).append(site_id)
    record = {
        "round": number,
        "handoff": _shown(handoff),
        "exported_at": RF.now(),
        "batches": batches,
        "asked": {site_id: asked for site_id, asked, _ in questions},
        "failures": {site_id: failures for site_id, _, failures in questions if failures},
    }
    with (run / ROUNDS_FILE).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "round": number,
        "questions": len(questions),
        "batches": len(batches),
        "sentences": sum(len(asked) for _, asked, _ in questions),
    }


def _read_defects(run: Path, report: Path, sites: Path) -> dict[str, list[dict[str, Any]]]:
    """The claims of a `defect-sites` report, by site - only of the list this run asks and of the
    read this run holds: the report's `desc_sha256` matching was made against its read, and a text
    that moved since is not the defective one."""
    record = json.loads(report.read_text(encoding="utf-8"))
    if record["out"]["sha256"] != _sha256(sites):
        raise WcRunError(f"{report} was made for another site list than {sites}")
    read = json.loads((run / READ_FILE).read_text(encoding="utf-8"))["sha256"]
    if record["read"]["sha256"] != read:
        raise WcRunError(
            f"{report} was made against another read ({record['read']['sha256'][:12]}) than this "
            f"run's ({read[:12]}): run defect-sites again on this run"
        )
    return {site_id: list(claims) for site_id, claims in record["claims"].items()}


def _defects_of(
    entry: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The claims reported against one asked text. A claim that names a sentence must name one of
    the text's own, word for word (`sentence_text`): a number that points at another sentence would
    send the agent to settle the wrong one. A claim without a sentence is tied to none."""
    for claim in claims:
        number = claim["sentence"]
        if number is None:
            continue
        sentences = entry["sentences"]
        if (
            not 1 <= number <= len(sentences)
            or sentences[number - 1].strip() != (claim["sentence_text"] or "").strip()
        ):
            raise WcRunError(
                f"{entry['site_id']}: the defect names sentence {number}, which is not the text's "
                f"own ({claim['sentence_text']!r}): the report and the read do not match"
            )
    return [dict(claim) for claim in claims]


def defects_block(claims: Sequence[Mapping[str, Any]] | None) -> str:
    """What a later web check reported against the text, as the question puts it (empty without)."""
    if not claims:
        return ""
    lines = "".join(
        P2.DEFECT_LINE.format(
            where="No single sentence" if claim["sentence"] is None else f"S{claim['sentence']}",
            claim=claim["claim"],
            url=claim["url"],
            quote=claim["quote"],
            found="found" if claim["quote_outcome"] == "found" else "did not find",
        )
        for claim in claims
    )
    return P2.DEFECTS_HEAD + lines + P2.DEFECTS_TAIL


def wn_pilot_size(population: int) -> int:
    """The sites a WN pilot draws from `population` sites without a description."""
    return min(WN_PILOT_SITES, population)


def wn_pilot_minimum(drawn: int) -> int:
    """The least number of a WN pilot's drawn sites that must end with a judged text, and the least
    number of kept sentences those texts must hold (`WN_PILOT_MIN_WITH_TEXT`)."""
    return max(1, math.ceil(WN_PILOT_MIN_WITH_TEXT * drawn))


def cmd_export(
    run: Path,
    handoff: Path,
    *,
    batch_size: int,
    exclude: Path | None,
    after: Sequence[Path],
    pilot: int | None,
    seed: int | None,
    limit: int | None = None,
    sites: Path | None = None,
    wn: bool = False,
    defects: Path | None = None,
    adversarial: bool = False,
) -> dict[str, Any]:
    """Round 1: the population of the run's read, a seeded pilot draw of it, or its first `limit`
    sites in site-id order (a chunk of the mass run: the next chunk names this run in `--after`),
    one question per site. `POPULATION.json` records every count, reason and input (the run's
    `kind` among them); `SITES.jsonl` the asked sites. `sites` (a file of site ids) makes a
    site-list run: the population is those curated sites, whatever their text; `wn` lane WN's: the
    sites without a description, and round 1 is the write round. `defects` (the `.report.json` of
    `defect-sites`, a site-list run only) puts each listed site's reported claims into its question
    (`defects_block`): the check must settle them, not find the sentence's own source again.
    `adversarial` (with `defects`) makes the run the second check of a site whose reported claim the
    first check left standing: its question opens as `prompts_sonnet.ADVERSARIAL_OPENING` and the
    adversarial role answers it (`check_role`)."""
    if (run / SITES_FILE).exists():
        raise WcRunError(f"{run} was exported already: a run has one population")
    if (pilot is None) != (seed is None):
        raise WcRunError("--pilot and --seed go together")
    if defects is not None and sites is None:
        raise WcRunError("--defects names the claims of a site list: it goes with --sites")
    if adversarial and defects is None:
        raise WcRunError("--adversarial checks the claims a report names: it goes with --defects")
    if adversarial and (wn or pilot is not None):
        raise WcRunError("--adversarial is a site-list run's second check: no --wn, no --pilot")
    if limit is not None and (pilot is not None or limit < 1):
        raise WcRunError("--limit is a chunk of at least one site, never beside --pilot")
    rows = read_jsonl(run / ROWS_FILE)
    excluded = _ids(exclude) if exclude is not None else set()
    earlier: set[str] = set()
    for other in after:
        earlier |= set(read_sites(other))
    kind = KIND_WN if wn else (KIND_LIST if sites is not None else KIND_WC)
    only = _ids(sites) if sites is not None else None
    if only is not None:
        if not only:
            raise WcRunError(f"{sites}: an empty site list")
        unknown = sorted(only - {row["id"] for row in rows})
        if unknown:
            raise WcRunError(
                f"{sites}: {len(unknown)} listed site(s) are no curated row of the read "
                f"({unknown[:3]}...): a list names curated sites only"
            )
    asked, listed = population(rows, excluded=excluded, earlier=earlier, kind=kind, only=only)
    claims = _read_defects(run, defects, sites) if defects is not None and sites is not None else {}
    for entry in asked:
        if entry["site_id"] in claims:
            entry["defects"] = _defects_of(entry, claims[entry["site_id"]])
    drawn = asked
    if pilot is not None and seed is not None:
        if not 1 <= pilot <= len(asked):
            raise WcRunError(f"a pilot of {pilot} from a population of {len(asked)}")
        if kind == KIND_WN and pilot != wn_pilot_size(len(asked)):
            raise WcRunError(
                f"a WN pilot draws {wn_pilot_size(len(asked))} sites ({WN_PILOT_SITES}, or the "
                f"whole population when it is smaller), not {pilot}: a smaller one measures too little"
            )
        chosen = set(
            audit4.draw_sample([e["site_id"] for e in asked], seed=seed, count=pilot, exclude=set())
        )
        drawn = [entry for entry in asked if entry["site_id"] in chosen]
    if limit is not None:
        drawn = asked[:limit]
    if not drawn:
        raise WcRunError(f"{run}: nothing to ask - the population is empty")
    RF.write_jsonl(run / SITES_FILE, drawn)
    counts = Counter(entry["marking"] for entry in asked)
    record = {
        "read": json.loads((run / READ_FILE).read_text(encoding="utf-8")),
        "kind": kind,
        "list": None
        if sites is None
        else {"path": _shown(sites), "sha256": _sha256(sites), "sites": len(only or ())},
        "rows_sha256": _sha256(run / ROWS_FILE),
        "population": len(asked),
        "by_marking": dict(sorted(counts.items())),
        "sentences": sum(len(entry["sentences"]) for entry in asked),
        "listed": {reason: sorted(ids) for reason, ids in sorted(listed.items())},
        "listed_counts": {reason: len(ids) for reason, ids in sorted(listed.items())},
        "exclude": None
        if exclude is None
        else {"path": _shown(exclude), "sha256": _sha256(exclude)},
        "defects": None
        if defects is None
        else {"path": _shown(defects), "sha256": _sha256(defects), "sites": len(claims)},
        "after": [_shown(other) for other in after],
        "adversarial": adversarial,
        "pilot": None if pilot is None else {"sites": pilot, "seed": seed},
        "limit": limit,
        "asked": len(drawn),
    }
    RF.write_json(run / POPULATION_FILE, record)
    questions = [
        (entry["site_id"], list(range(1, len(entry["sentences"]) + 1)), {}) for entry in drawn
    ]
    summary = _export_round(run, handoff, number=1, questions=questions, batch_size=batch_size)
    return {
        **summary,
        "population": len(asked),
        "by_marking": record["by_marking"],
        "listed": record["listed_counts"],
    }


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the agent that answers one batch of one round: the fact checker's (the
    adversarial role's in an adversarial second check), recording with the role's model and role."""
    record = round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise WcRunError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    kind = run_kind(run)
    role_name = check_role(run)
    family = _agent_family(role_name)
    fields = {
        "batch": batch_id,
        "round": record["round"],
        "count": len(record["batches"][batch_id]),
        "handoff": shown,
        "scratch": f"{shown}-scratch/{batch_id}",
        "run": _shown(run),
        "python": Path(sys.executable).as_posix(),
        "repo": REPO.as_posix(),
        **_role_fields(role_name),
    }
    if kind == KIND_WN:
        return P2.WRITE_BRIEF.format(
            **fields,
            stage=WRITE_STAGE,
            batch_agent=f"{family}-write-{batch_id}",
            min_sentences=A.MIN_SENTENCES,
        )
    return P.CHECK_BRIEF.format(
        **fields, stage=STAGE, batch_agent=f"{family}-check-r{record['round']}-{batch_id}"
    )


# ------------------------------------------------------------------------------------ the check
def _agent_pages(handoff: Path, batch_id: str) -> Path:
    """The page store `check-answer` fills for one batch's agent: its aid, never the import's."""
    return handoff / batch_id / "pages"


def fetch(
    urls: Iterable[str],
    pages: Path,
    *,
    client: A.Client | None,
    pace: float,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Every URL not yet in the batch's page store, fetched once (`opus_audit/quotes.collect`)."""
    wanted = sorted(set(urls))
    if not wanted:
        return
    own = client or A.Client()
    try:
        extra = {} if sleep is None else {"sleep": sleep}
        Q.collect(wanted, pages, own, now=RF.now, pace=pace, errors=A.FETCH_ERRORS, **extra)
    finally:
        if client is None:
            own.close()


def judge_sentences(
    answers: Sequence[A.SentenceAnswer], library: Q.Library, *, label: str, checked: str
) -> dict[int, dict[str, Any]]:
    """Each answered sentence: its answer, every quote's outcome, whether it counts and why not.
    A kept sentence counts when every quote it gives is verified; a DROP counts as given."""
    out: dict[int, dict[str, Any]] = {}
    for answer in answers:
        outcomes = A.quote_outcomes(label, answer.quotes, library, checked=checked)
        failed = [o for o in outcomes if not o.verified]
        counted = answer.verdict is wc4.Verdict.DROP or not failed
        out[answer.n] = {
            "answer": answer.to_dict(),
            "quotes": [o.to_dict() for o in outcomes],
            "counted": counted,
            "why": None
            if counted
            else "; ".join(
                f"the quote on {o.quote.url} was not usable ({o.outcome}"
                + (f": {o.detail}" if o.detail else "")
                + ")"
                for o in failed
            ),
        }
    return out


def _asked(record: Mapping[str, Any], label: str) -> list[int]:
    return list(record["asked"][label])


def check_answer(
    run: Path,
    handoff: Path,
    batch_id: str,
    label: str,
    text: str,
    *,
    fetch_pages: bool = True,
    client: A.Client | None = None,
    pace: float = Q.PACE_SECONDS,
) -> tuple[bool, str]:
    """The agent's aid: the answer's shape, then (with `fetch_pages`) every quote against its page
    as the import will check it, and the text the answer would leave. (clean, report)."""
    record = round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise WcRunError(f"{batch_id}/{label} is no question of {handoff}")
    entry = read_sites(run)[label]
    written: A.WriteAnswer | None = None
    try:
        if run_kind(run) == KIND_WN:
            written = A.parse_write(text, site_id=label)
            parsed = written.as_check()
            entry = {**entry, "sentences": [sentence.text for sentence in written.sentences]}
            if not parsed:
                return True, f"no sentence: the site stays without a description ({written.note})"
        else:
            parsed = A.parse_check(
                text,
                site_id=label,
                sentences=entry["sentences"],
                asked=_asked(record, label),
                trims=_trims(entry),
            )
    except A.AnswerError as exc:
        return False, f"NOT IN SHAPE: {exc}"
    if not fetch_pages:
        return True, "in shape (no page fetched)"
    pages = _agent_pages(handoff, batch_id)
    fetch([q.url for a in parsed for q in a.quotes], pages, client=client, pace=pace)
    judged = judge_sentences(
        parsed,
        Q.Library(REPO, pages),
        label=label,
        checked=entry["plan_site"]["description"] or "",
    )
    lines = []
    for n, result in sorted(judged.items()):
        answer = result["answer"]
        state = "counts" if result["counted"] else f"DOES NOT COUNT - {result['why']}"
        lines.append(f"S{n} {answer['verdict']}: {state}")
    clean = all(result["counted"] for result in judged.values()) and all(
        quote["verified"] for result in judged.values() for quote in result["quotes"]
    )
    if record["round"] == 1:
        decisions, verified = _decisions(entry, judged)
        composed = wc4.compose(decisions, verified)
        lines.append(
            "the text this answer leaves: "
            + (
                composed.description
                if composed.description
                else "(nothing - the description is cleared)"
            )
        )
    if not clean:
        lines.append(
            "NOT CLEAN: a quote above was not found or not usable - fix it, or DROP the sentence"
        )
    return clean, "\n".join(lines)


def _decisions(
    entry: Mapping[str, Any], results: Mapping[int, Mapping[str, Any]]
) -> tuple[list[wc4.Decision], dict[int, list[wc4.Quote]]]:
    """Every sentence's final decision from its last counted result (`results`, by number), a
    missing or uncounted one dropped as unverified; then the pronoun rule."""
    decisions: list[wc4.Decision] = []
    verified: dict[int, list[wc4.Quote]] = {}
    for n, sentence in enumerate(entry["sentences"], start=1):
        result = results.get(n)
        if result is None or not result["counted"]:
            decisions.append(
                wc4.Decision(n, sentence, wc4.Verdict.DROP, None, wc4.DropReason.UNVERIFIED)
            )
            continue
        answer = result["answer"]
        verdict = wc4.Verdict(answer["verdict"])
        reason = None if answer["reason"] is None else wc4.DropReason(answer["reason"])
        decisions.append(wc4.Decision(n, sentence, verdict, answer["remove"], reason))
        if verdict in wc4.KEPT:
            verified[n] = [
                wc4.Quote(url=q["url"], title=q["title"], quote=q["quote"])
                for q in result["quotes"]
                if q["verified"]
            ]
    return wc4.follow_drops(decisions), verified


# ------------------------------------------------------------------------------------ the import
def _round_dir(run: Path, number: int) -> Path:
    return run / f"round-{number}"


def cmd_import(
    run: Path, handoff: Path, *, client: A.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """One round, once: validated, every prompt rebuilt, every answer parsed and its quotes
    checked. Refused when the round was imported (its `ANSWERS.jsonl` is there) or a verification
    round was exported: a verifier was shown the text the check rounds give, and an import run
    again would put a text no verifier saw under its verdict (the review of 2026-09-27)."""
    record = round_of(run, handoff)
    number = record["round"]
    if (_round_dir(run, number) / "ANSWERS.jsonl").exists():
        raise WcRunError(
            f"{run}: round {number} was imported; a round is imported once - a check answered "
            "again is a new run's"
        )
    if _verify_rounds(run):
        raise WcRunError(
            f"{run}: the verification was exported - the check rounds are final once a verifier "
            "was shown their text; a check answered again is a new run's"
        )
    check = OH.validate(handoff)
    if not check.ok:
        raise WcRunError(
            f"{handoff}: {len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
            "answer is validated before anything is imported"
        )
    manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
    asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
    if set(manifest) != asked:
        raise WcRunError(f"{handoff}: the manifest is not the round's record")
    sites = read_sites(run)
    kind = run_kind(run)
    adversarial = run_adversarial(run)
    stage = WRITE_STAGE if kind == KIND_WN else STAGE
    parsed: dict[str, tuple[dict[str, Any], tuple[A.SentenceAnswer, ...] | None]] = {}
    drafts: list[dict[str, Any]] = []
    urls: set[str] = set()
    for (batch_id, label), line in sorted(manifest.items()):
        entry = sites[label]
        failures = record["failures"].get(label, {})
        prompt = check_prompt(entry, _asked(record, label), failures, kind, adversarial)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise WcRunError(f"{batch_id}/{label}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=label, prompt=prompt)
        _require_role(answer, role_name=check_role(run), where=f"{batch_id}/{label}")
        attempt = {
            "round": number,
            "handoff": record["handoff"],
            "batch_id": batch_id,
            "label": label,
            "answered_by": answer.answered_by,
            "answered_at": answer.answered_at,
            "prompt_sha256": line["prompt_sha256"],
            "answer_sha256": M.text_sha256(answer.text),
            "problem": None,
        }
        if kind == KIND_WN:
            try:
                written = A.parse_write(answer.text, site_id=label)
            except A.AnswerError as exc:
                raise WcRunError(
                    f"{batch_id}/{label}: malformed answer ({exc}) - check-answer refuses it; "
                    "delete the answer file and have the batch agent answer it again"
                ) from exc
            answers = written.as_check()
            drafts.append(
                {
                    "site_id": label,
                    "sentences": [sentence.text for sentence in written.sentences],
                    "note": written.note,
                }
            )
        else:
            try:
                answers = A.parse_check(
                    answer.text,
                    site_id=label,
                    sentences=entry["sentences"],
                    asked=_asked(record, label),
                    trims=_trims(entry),
                )
            except A.AnswerError as exc:
                attempt["problem"] = str(exc)
                answers = None
        parsed[label] = (attempt, answers)
        if answers is not None:
            urls.update(q.url for a in answers for q in a.quotes)
    fetch(urls, run / PAGES_DIR, client=client, pace=pace)
    library = Q.Library(REPO, run / PAGES_DIR)
    rows: list[dict[str, Any]] = []
    reask: dict[str, dict[str, list[str]]] = {}
    for label, (attempt, answers) in sorted(parsed.items()):
        entry = sites[label]
        if answers is None:
            results = {
                n: {"answer": None, "quotes": [], "counted": False, "why": attempt["problem"]}
                for n in _asked(record, label)
            }
        else:
            results = judge_sentences(
                answers, library, label=label, checked=entry["plan_site"]["description"] or ""
            )
        failed = {str(n): [str(r["why"])] for n, r in results.items() if not r["counted"]}
        if failed and kind != KIND_WN:  # a written sentence is never re-asked: it is dropped
            reask[label] = failed
        rows.append(
            {**attempt, "results": {str(n): result for n, result in sorted(results.items())}}
        )
    out = _round_dir(run, number)
    if kind == KIND_WN:
        RF.write_jsonl(run / DRAFTS_FILE, drafts)
    RF.write_jsonl(out / "ANSWERS.jsonl", rows)
    RF.write_json(out / "REASK.json", reask)
    verdicts = Counter(
        result["answer"]["verdict"] if result["answer"] else "not in shape"
        for row in rows
        for result in row["results"].values()
    )
    return {
        "round": number,
        "answers": len(rows),
        "not_in_shape": sum(1 for row in rows if row["problem"]),
        "sentences": sum(len(row["results"]) for row in rows),
        "verdicts": dict(sorted(verdicts.items())),
        "to_reask": sum(len(v) for v in reask.values()),
        "sites_to_reask": len(reask),
        "urls": len(urls),
        **({"sites_without_sentences": sum(not d["sentences"] for d in drafts)} if drafts else {}),
    }


def _imported(run: Path) -> list[dict[str, Any]]:
    """Every round of the run with its imported answers, in round order; a round exported and not
    imported stops the command."""
    rounds = sorted(read_rounds(run), key=lambda r: r["round"])
    if not rounds:
        raise WcRunError(f"{run}: no round was exported")
    for record in rounds:
        if not (_round_dir(run, record["round"]) / "ANSWERS.jsonl").exists():
            raise WcRunError(f"{run}: round {record['round']} is exported and not imported")
    return rounds


def cmd_export_reask(run: Path, handoff: Path, *, batch_size: int) -> dict[str, Any]:
    """Round 2: the sentences of round 1 that do not count, asked once more with what failed."""
    if run_kind(run) == KIND_WN:
        raise WcRunError(
            f"{run}: a written description is not re-asked - a sentence whose quote is not found "
            "is dropped, and a site left without a sentence stays without a description"
        )
    rounds = _imported(run)
    if len(rounds) >= MAX_ROUNDS:
        raise WcRunError(f"{run}: the re-ask round was exported; a sentence is re-asked once")
    last = rounds[-1]["round"]
    reask = json.loads((_round_dir(run, last) / "REASK.json").read_text(encoding="utf-8"))
    if not reask:
        raise WcRunError(f"{run}: round {last} left nothing to re-ask")
    questions = [
        (label, sorted(int(n) for n in failures), failures)
        for label, failures in sorted(reask.items())
    ]
    return _export_round(run, handoff, number=last + 1, questions=questions, batch_size=batch_size)


# ------------------------------------------------------------------------------------ the views
def _view(
    decisions: Sequence[wc4.Decision], quotes: Mapping[int, Sequence[wc4.Quote]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """A site's kept sentences as they will be published (trimmed where they are, with the verified
    quotes their markers cite and the old sentence a piece was cut from) and its dropped sentences,
    in order - what a verifier and the pilot's judge are shown."""
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for decision in decisions:
        text = decision.text
        if text is None:
            dropped.append(decision.sentence)
            continue
        kept.append(
            {
                "text": text,
                "quotes": [{"url": q.url, "quote": q.quote} for q in quotes.get(decision.n, ())],
                "trimmed_from": decision.sentence if text != decision.sentence else None,
            }
        )
    return kept, dropped


def _kept_lines(kept: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for k, item in enumerate(kept, start=1):
        lines.append(f"K{k}: {item['text']}")
        if item["trimmed_from"] is not None:
            lines.append(f'    trimmed from: "{item["trimmed_from"]}"')
        lines.extend(f'    quote: "{q["quote"]}" - {q["url"]}' for q in item["quotes"])
    return "\n".join(lines) if lines else "(none - the description is cleared)"


def _dropped_lines(dropped: Sequence[str]) -> str:
    return "\n".join(f"D{d}: {text}" for d, text in enumerate(dropped, start=1)) or "(none)"


# ------------------------------------------------------------------------------------ the build
def _results(run: Path) -> tuple[dict[str, dict[int, dict[str, Any]]], dict[str, list[dict]]]:
    """Per site, each sentence's result from the last round that asked it, and every attempt."""
    rounds = _imported(run)
    last = rounds[-1]["round"]
    pending = json.loads((_round_dir(run, last) / "REASK.json").read_text(encoding="utf-8"))
    if pending and last < MAX_ROUNDS:
        raise WcRunError(
            f"{run}: round {last} left {sum(len(v) for v in pending.values())} sentence(s) to "
            "re-ask: export-reask, answer, validate and import it first"
        )
    results: dict[str, dict[int, dict[str, Any]]] = {}
    attempts: dict[str, list[dict]] = {}
    for record in rounds:
        for row in read_jsonl(_round_dir(run, record["round"]) / "ANSWERS.jsonl"):
            label = row["label"]
            attempts.setdefault(label, []).append(
                {key: value for key, value in row.items() if key != "results"}
            )
            results.setdefault(label, {})  # a lane-WN site may be answered with no sentence
            for n, result in row["results"].items():
                results[label][int(n)] = {**result, "round": record["round"]}
    return results, attempts


@dataclasses.dataclass(frozen=True)
class Checked:
    """One asked site after the check rounds: its entry, its decisions (every round, the pronoun
    rule), the verified quotes of each kept sentence, and every check attempt - what the
    verification starts from."""

    entry: dict[str, Any]
    results: dict[int, dict[str, Any]]
    attempts: list[dict[str, Any]]
    decisions: list[wc4.Decision]
    quotes: dict[int, list[wc4.Quote]]

    @property
    def checkers(self) -> set[str]:
        return {attempt["answered_by"] for attempt in self.attempts}


def answer_stamp(handoff: str, batch_id: str, stage: str, label: str) -> str:
    """The model stamp of one answer: the `model` of its write-once answer file in the round's
    handoff directory (`handoff` as the round recorded it, repo-relative or absolute) - the one
    source of who answered, for a round imported before 2026-10-08 as for a later one."""
    path = REPO / handoff / OH.answer_relpath(batch_id, stage, label)
    return json.loads(path.read_text(encoding="utf-8"))["model"]


def disclosure_of(checked: Checked, verifier_stamps: Iterable[str], kind: str = KIND_WC) -> str:
    """The AI disclosure of a site's new write, derived from the models that answered it: every
    check or write attempt (its answer file's stamp) and every verification round
    (`model4.ai_system_for`, owner decision D6)."""
    stage = WRITE_STAGE if kind == KIND_WN else STAGE
    stamps = [
        answer_stamp(attempt["handoff"], attempt["batch_id"], stage, attempt["label"])
        for attempt in checked.attempts
    ]
    return M.ai_system_for([*stamps, *verifier_stamps])


def checked_sites(run: Path) -> dict[str, Checked]:
    """Every asked site of the run, in the run's order, after the check rounds; refused while a
    check round is due or a site was never answered."""
    results, attempts = _results(run)
    out: dict[str, Checked] = {}
    for entry in read_sites(run).values():
        label = entry["site_id"]
        if label not in results:
            raise WcRunError(f"{label} was never answered")
        decisions, quotes = _decisions(entry, results[label])
        out[label] = Checked(entry, results[label], attempts[label], decisions, quotes)
    return out


def outcome_of(
    checked: Checked,
    rounds: Sequence[Mapping[str, Any]],
    *,
    run_name: str,
    verifier_stamps: Iterable[str],
    kind: str = KIND_WC,
) -> tuple[wc4.WcOutcome, list[wc4.Decision], dict[str, Any]]:
    """One site's outcome: its check decisions, the verification (`rounds`, the site's verification
    rounds as imported), the verified decisions, the composed text, the record, the raw_data and
    the journal evidence; and the verification record."""
    entry, results = checked.entry, checked.results
    site = M.PlanSite.from_dict(entry["plan_site"])
    listed = kind != KIND_WC
    decisions, verification = wc4.apply_verification(checked.decisions, checked.quotes, rounds)
    composed = wc4.compose(decisions, checked.quotes)
    ai_system = disclosure_of(checked, verifier_stamps, kind)
    check = (
        None
        if composed.description is None
        else wc4.check_record(
            decisions,
            composed,
            checked.quotes,
            run=run_name,
            checked=site.description,
            verification=verification,
            checker=ai_system,
        )
    )
    raw = wc4.written_raw_data(site, composed, check, listed=listed)
    sentences = []
    for before, decision in zip(checked.decisions, decisions, strict=True):
        result = results.get(decision.n)
        answer = result["answer"] if result else None
        sentences.append(
            {
                "n": decision.n,
                "sentence": decision.sentence,
                "verdict": decision.verdict.value,
                "remove": decision.remove,
                "reason": None if decision.reason is None else decision.reason.value,
                "checked": {
                    "verdict": before.verdict.value,
                    "remove": before.remove,
                    "reason": None if before.reason is None else before.reason.value,
                },
                "answered": None if answer is None else answer["verdict"],
                "note": None if answer is None else answer["note"],
                "round": None if result is None else result["round"],
                "quotes": [] if result is None else list(result["quotes"]),
            }
        )
    evidence = {
        "group": "WC",
        "decision": wc4.EVIDENCE_DECISION_WN if kind == KIND_WN else wc4.EVIDENCE_DECISION,
        "run": run_name,
        "checker": ai_system,
        "checked": site.description,
        "marking": wc4.marking_record(site, listed=listed),
        "description": composed.description,
        "kept": sum(d.kept for d in decisions),
        "of": len(decisions),
        "sentences": sentences,
        "answers": list(checked.attempts),
        wc4.VERIFICATION_KEY: verification,
    }
    outcome = wc4.WcOutcome(
        site_id=site.site_id, description=composed.description, raw_data=raw, evidence=evidence
    )
    return outcome, decisions, verification


def verification_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """A site's verification as FINAL.jsonl shows it: where it ended, the verifiers, and per round
    each shown sentence's verdict, the coherence, what it dropped and why."""
    return {
        "status": record["status"],
        "verifiers": [r["answered_by"] for r in record["rounds"]],
        "before": record["before"],
        "kept": record["kept"],
        "rounds": [
            {
                "stage": r["stage"],
                "answered_by": r["answered_by"],
                "verdicts": {str(v["n"]): v["verdict"] for v in r["verdicts"]},
                "coherent": r["coherent"],
                "broken": r["broken"],
                "passed": r["passed"],
                "drops": r["drops"],
                "cleared": r["cleared"],
                "text_sha256": r["text_sha256"],
            }
            for r in record["rounds"]
        ],
    }


def cmd_build(run: Path, *, first_batch: int, batch_size: int = wc4.BATCH_SIZE) -> dict[str, Any]:
    """Every site's outcome (`FINAL.jsonl`), the counts and each site's verification record
    (`SUMMARY.json`) and the gate plan; refused while a check round or a verification round is
    due - nothing is built from an unverified text."""
    if first_batch < wc4.FIRST_BATCH:
        raise WcRunError(f"--first-batch {first_batch}: the WC block starts at {wc4.FIRST_BATCH}")
    kind = run_kind(run)
    checked = checked_sites(run)
    inputs = _verification_inputs(run)
    stamps = _verification_stamps(run)
    for label, site in checked.items():
        _, derived, status = wc4.run_verification(
            site.decisions, site.quotes, inputs.get(label, [])
        )
        if status is None:
            raise WcRunError(
                f"{label}: verification round {len(derived) + 1} "
                f"({VERIFY_STAGES[len(derived)]}) is due - verify-export, answer, validate and "
                "verify-import it first: nothing is built from an unverified text"
            )
        _asked_again(label, site, inputs.get(label, []), kind)
    finals: list[dict[str, Any]] = []
    outcomes: list[wc4.WcOutcome] = []
    not_planned: dict[str, list[str]] = {}
    reasons: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    records: dict[str, dict[str, Any]] = {}
    decisions_by: dict[str, Sequence[wc4.Decision]] = {}
    for label, site in checked.items():
        entry = site.entry
        outcome, decisions, record = outcome_of(
            site,
            inputs.get(label, []),
            run_name=run.name,
            verifier_stamps=stamps.get(label, []),
            kind=kind,
        )
        records[label] = record
        problems = wc4.wc_problems(
            outcome.description, outcome.raw_data, marking=outcome.evidence["marking"]["old"]
        ) + wc4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data)
        if problems:
            raise WcRunError(f"{label}: the outcome breaks the lane's invariants: {problems}")
        why_not = _not_planned(kind, entry, outcome, decisions)
        if why_not is None:
            outcomes.append(outcome)
        else:
            not_planned.setdefault(why_not, []).append(label)
        verdicts.update(d.verdict.value for d in decisions)
        reasons.update(d.reason.value for d in decisions if d.reason is not None)
        final = {
            "site_id": label,
            "name": entry["name"],
            "marking": entry["marking"],
            "kept": sum(d.kept for d in decisions),
            "of": len(decisions),
            "cleared": outcome.description is None,
            "description": outcome.description,
            "decisions": [{**dataclasses.asdict(d), "text": d.text} for d in decisions],
            "verification": verification_summary(record),
            "evidence": outcome.evidence,
        }
        if kind != KIND_WC:
            final["planned"] = why_not is None
        finals.append(final)
        decisions_by[label] = decisions
    RF.write_jsonl(run / FINAL_FILE, finals)
    defects_kept = {
        label: kept
        for label, site in checked.items()
        if (kept := _defects_kept(site.entry, decisions_by[label]))
    }
    plan_batches = []
    for start in range(0, len(outcomes), batch_size):
        chunk = outcomes[start : start + batch_size]
        ordinal = first_batch + start // batch_size
        plan_batches.append(
            {
                "batch_id": f"p4-{ordinal:04d}",
                "ordinal": ordinal,
                "pass": wc4.PLAN_MARK,
                "sites": [checked[o.site_id].entry["plan_site"] for o in chunk],
                "outcomes": [o.to_dict() for o in chunk],
            }
        )
    RF.write_jsonl(run / PLAN_FILE, plan_batches)
    rounds = [r for record in records.values() for r in record["rounds"]]
    summary = {
        **(
            {
                "kind": kind,
                "not_planned": {why: sorted(ids) for why, ids in not_planned.items()},
                "defects_kept": defects_kept,
            }
            if kind != KIND_WC
            else {}
        ),
        "sites": len(finals),
        "cleared": sum(f["cleared"] for f in finals),
        "kept_whole": sum(f["kept"] == f["of"] for f in finals),
        "sentences": sum(f["of"] for f in finals),
        "sentences_kept": sum(f["kept"] for f in finals),
        "verdicts": dict(sorted(verdicts.items())),
        "drop_reasons": dict(sorted(reasons.items())),
        "verification": {
            "by_status": dict(sorted(Counter(r["status"] for r in records.values()).items())),
            "verify2_sites": sum(len(r["rounds"]) == len(VERIFY_STAGES) for r in records.values()),
            "sentences_before": sum(len(r["before"]) for r in records.values()),
            "sentences_after": sum(len(r["kept"]) for r in records.values()),
            "verdicts": {
                stage: dict(
                    sorted(
                        Counter(
                            v["verdict"]
                            for r in rounds
                            if r["stage"] == stage
                            for v in r["verdicts"]
                        ).items()
                    )
                )
                for stage in VERIFY_STAGES
            },
            "incoherent": {
                stage: sum(not r["coherent"] for r in rounds if r["stage"] == stage)
                for stage in VERIFY_STAGES
            },
            #: per site, as FINAL.jsonl shows it: where it ended, the verifiers and their verdicts
            "sites": {label: verification_summary(record) for label, record in records.items()},
        },
        "plan": {
            "path": _shown(run / PLAN_FILE),
            "sha256": _sha256(run / PLAN_FILE),
            "batches": len(plan_batches),
            "first": plan_batches[0]["batch_id"] if plan_batches else None,
            "last": plan_batches[-1]["batch_id"] if plan_batches else None,
        },
    }
    RF.write_json(run / SUMMARY_FILE, summary)
    return summary


def _defects_kept(entry: Mapping[str, Any], decisions: Sequence[wc4.Decision]) -> list[dict]:
    """The reported claims a site's check left standing: its sentence kept, or - a claim tied to no
    sentence - nothing of the text dropped. The owner's list: a defect reported on the web that the
    check did not resolve by a drop (the agent's note says why)."""
    standing = []
    for claim in entry.get("defects") or []:
        number = claim["sentence"]
        kept = (
            all(d.kept for d in decisions) if number is None else bool(decisions[number - 1].kept)
        )
        if kept:
            standing.append({"sentence": number, "claim": claim["claim"], "url": claim["url"]})
    return standing


def _not_planned(
    kind: str, entry: Mapping[str, Any], outcome: wc4.WcOutcome, decisions: Sequence[wc4.Decision]
) -> str | None:
    """Why a built site is not in the gate plan, or `None`. A plain run plans every site (a clear is
    a write). Lane WN plans only the sites that got a text: the rest stay without a description,
    nothing is written (`empty`). A site-list run does not write a Phase-4 text whose check kept
    every sentence (`unchanged`): a rewrite would only replace the pinned citations with the
    check's. One that a later web check reported a claim against and the check kept whole anyway is
    `defect-kept`: nothing is written, and the report stands for the owner (`defects_kept`)."""
    if kind == KIND_WN and outcome.description is None:
        return "empty"
    if (
        kind == KIND_LIST
        and entry["marking"] == wc4.Marking.PHASE4.value
        and all(d.kept for d in decisions)
    ):
        return "defect-kept" if entry.get("defects") else "unchanged"
    return None


# ------------------------------------------------------------------------------------ the verification
def _verify_dir(run: Path, number: int) -> Path:
    return run / VERIFY_DIR / f"round-{number}"


def _verify_rounds(run: Path) -> list[dict[str, Any]]:
    """Every verification round exported for the run, in order (`round-<n>/ROUND.json`)."""
    rounds: list[dict[str, Any]] = []
    for number in range(1, len(VERIFY_STAGES) + 1):
        path = _verify_dir(run, number) / "ROUND.json"
        if not path.exists():
            break
        rounds.append(json.loads(path.read_text(encoding="utf-8")))
    return rounds


def _verify_round_of(run: Path, handoff: Path) -> dict[str, Any]:
    for record in _verify_rounds(run):
        if Path(record["handoff"]).resolve() == handoff.resolve():
            return record
    raise WcRunError(f"{handoff} is no verification round of {run}")


def _verified_rows(
    run: Path, before: int | None = None
) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    """Every row of every imported verification round (below round `before`, when given), as
    `(round record, row)` in round order. A round exported and not imported stops the command."""
    for record in _verify_rounds(run):
        if before is not None and record["round"] >= before:
            break
        path = _verify_dir(run, record["round"]) / "VERIFIED.jsonl"
        if not path.exists():
            raise WcRunError(
                f"{run}: verification round {record['round']} ({record['stage']}) is exported and "
                "not imported"
            )
        for row in read_jsonl(path):
            yield record, row


def _verification_inputs(run: Path, *, before: int | None = None) -> dict[str, list[dict]]:
    """Per site, its record of every imported verification round (below round `before`, when
    given), in round order - what `wc4.run_verification` reads: the round's own keys, without the
    row's `site_id`."""
    inputs: dict[str, list[dict]] = {}
    for _, row in _verified_rows(run, before):
        given = {key: value for key, value in row.items() if key != "site_id"}
        inputs.setdefault(row["site_id"], []).append(given)
    return inputs


def _verification_stamps(run: Path) -> dict[str, list[str]]:
    """Per site, the stamp of the model that answered each verification round, in round order,
    read from the round's answer file (`answer_stamp`)."""
    stamps: dict[str, list[str]] = {}
    for record, row in _verified_rows(run):
        stamp = answer_stamp(record["handoff"], row["batch_id"], record["stage"], row["site_id"])
        stamps.setdefault(row["site_id"], []).append(stamp)
    return stamps


def verify_prompt(
    entry: Mapping[str, Any],
    decisions: Sequence[wc4.Decision],
    quotes: Mapping[int, Sequence[wc4.Quote]],
    kind: str = KIND_WC,
) -> str:
    """The exact question about one site's kept text, as it stands at its verification round (a
    text lane WN wrote is told so: `prompts_sonnet.VERIFY_QUESTION_WN`)."""
    kept, dropped = _view(decisions, quotes)
    return (P2.VERIFY_QUESTION_WN if kind == KIND_WN else P.VERIFY_QUESTION).format(
        site=site_block(M.PlanSite.from_dict(entry["plan_site"])),
        kept=_kept_lines(kept),
        dropped=_dropped_lines(dropped),
        site_id=entry["site_id"],
        kept_count=len(kept),
    )


def _asked_again(
    label: str, site: Checked, rounds: Sequence[Mapping[str, Any]], kind: str = KIND_WC
) -> None:
    """Every recorded verification round of a site asked the question the site's state at that
    round gives now (`verify_prompt`, byte for byte against the round's `prompt_sha256`): a check
    or a quote that moved under a round - even one that leaves the text as it was, which
    `wc4.run_verification` holds to the round's `text_sha256` - is refused, never built (the
    review of 2026-09-27)."""
    for index, given in enumerate(rounds):
        state, _, _ = wc4.run_verification(site.decisions, site.quotes, rounds[:index])
        asked = OH.prompt_sha256(verify_prompt(site.entry, state, site.quotes, kind))
        if asked != given["prompt_sha256"]:
            raise WcRunError(
                f"{label}: verification round {index + 1} ({given['stage']}) asked another "
                "question than the site's state gives: its check moved after the verifier "
                "answered - nothing is built from a text no verifier was shown"
            )


def cmd_verify_export(run: Path, handoff: Path, *, batch_size: int) -> dict[str, Any]:
    """The next verification round: `verify` asks every site whose check kept a sentence, once
    every check round is imported; `verify2` - after `verify` is imported - every site whose kept
    text a drop of `verify` changed and that still keeps a sentence. One question per site, the
    kept text as it will be published (`verify_prompt`), in batches `<stage>-NNNN`."""
    rounds = _verify_rounds(run)
    inputs = _verification_inputs(run)
    kind = run_kind(run)
    number = len(rounds) + 1
    if number > len(VERIFY_STAGES):
        raise WcRunError(
            f"{run}: both verification rounds were exported - a text a drop changed is verified "
            "once more, never twice"
        )
    if any(Path(r["handoff"]).resolve() == handoff.resolve() for r in rounds):
        raise WcRunError(f"{handoff} is already a verification round of {run}")
    if handoff.exists() and any(handoff.iterdir()):
        raise WcRunError(f"{handoff} is not empty: a round takes a new handoff directory")
    stage = VERIFY_STAGES[number - 1]
    due: list[tuple[str, Checked, list[wc4.Decision]]] = []
    for label, site in checked_sites(run).items():
        current, derived, status = wc4.run_verification(
            site.decisions, site.quotes, inputs.get(label, [])
        )
        if status is not None:
            continue
        if len(derived) != number - 1:
            raise WcRunError(
                f"{label} is due at verification round {len(derived) + 1}, not {number}: the "
                "check rounds moved after an earlier verification round was exported"
            )
        due.append((label, site, current))
    if not due:
        what = "no site's check kept a sentence" if number == 1 else "no kept text changed"
        raise WcRunError(f"{run}: nothing to verify at {stage} - {what}; build")
    batches: dict[str, list[str]] = {}
    shown: dict[str, list[int]] = {}
    for start in range(0, len(due), batch_size):
        batch_id = f"{stage}-{start // batch_size + 1:04d}"
        for label, site, current in due[start : start + batch_size]:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=label,
                field="description",
                prompt=verify_prompt(site.entry, current, site.quotes, kind),
            )
            batches.setdefault(batch_id, []).append(label)
            shown[label] = wc4.kept_numbers(current)
    RF.write_json(
        _verify_dir(run, number) / "ROUND.json",
        {
            "round": number,
            "stage": stage,
            "handoff": _shown(handoff),
            "exported_at": RF.now(),
            "batches": batches,
            "shown": shown,
        },
    )
    return {
        "round": number,
        "stage": stage,
        "questions": len(due),
        "batches": len(batches),
        "sentences": sum(len(numbers) for numbers in shown.values()),
    }


def verify_brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the web verifier that verifies one batch of one verification round."""
    record = _verify_round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise WcRunError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return P.VERIFY_BRIEF.format(
        **_role_fields(ROLE_VERIFY),
        batch=batch_id,
        round=record["round"],
        stage=record["stage"],
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        python=Path(sys.executable).as_posix(),
        repo=REPO.as_posix(),
        batch_agent=f"{_agent_family(ROLE_VERIFY)}-wc-{batch_id}",
    )


def verify_check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str
) -> str | None:
    """The verifier's aid: the answer's shape only (nothing is fetched, no verdict is judged)."""
    record = _verify_round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise WcRunError(f"{batch_id}/{label} is no question of {handoff}")
    try:
        A.parse_verify(text, site_id=label, kept=len(record["shown"][label]))
    except A.AnswerError as exc:
        return str(exc)
    return None


def cmd_verify_import(
    run: Path, handoff: Path, *, client: A.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """One verification round, once: validated; every prompt rebuilt from the site's state at this
    round and compared byte for byte; a verifier whose name checked the site - or verified it in an
    earlier round - refused; every answer parsed (`answers.parse_verify`); every quoted page fetched
    once into `<run>/verify/pages/` and every quote checked (`answers.check_quotes`, recorded: a
    WRONG drops its sentence whether its quote was found or not); the sha256 of the text each
    question showed recorded (`text_sha256`, the text as published, markers included); every
    site's round read by `wc4.run_verification` before `VERIFIED.jsonl` is written."""
    record = _verify_round_of(run, handoff)
    number, stage = record["round"], record["stage"]
    if record.get("calibration"):
        # Owner decision 2026-10-03 (O18): a calibration round holds answers written to *compare* a
        # model with the recorded ones. They are not verdicts about the sites, so no ledger may read
        # them - the calibration is a measurement, and it stays outside the run it measures.
        raise WcRunError(
            f"{run}: verification round {number} is a calibration round; a comparison is never "
            "imported"
        )
    out = _verify_dir(run, number) / "VERIFIED.jsonl"
    if out.exists():
        raise WcRunError(
            f"{run}: verification round {number} was imported; a round is imported once"
        )
    check = OH.validate(handoff)
    if not check.ok:
        raise WcRunError(
            f"{handoff}: {len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
            "answer is validated before anything is imported"
        )
    manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
    asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
    if set(manifest) != asked:
        raise WcRunError(f"{handoff}: the manifest is not the verification round's record")
    sites = checked_sites(run)
    kind = run_kind(run)
    earlier = _verification_inputs(run, before=number)
    parsed: dict[str, tuple[str, dict[str, Any], OH.Answer, A.VerifyAnswer, str]] = {}
    urls: set[str] = set()
    for (batch_id, label), line in sorted(manifest.items()):
        site = sites[label]
        current, derived, status = wc4.run_verification(
            site.decisions, site.quotes, earlier.get(label, [])
        )
        if status is not None or len(derived) != number - 1:
            raise WcRunError(f"{label} is not due at {stage}: its check or verification moved")
        if wc4.kept_numbers(current) != record["shown"][label]:
            raise WcRunError(f"{label}: the kept text is not the one {stage} showed")
        prompt = verify_prompt(site.entry, current, site.quotes, kind)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise WcRunError(f"{batch_id}/{label}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=label, prompt=prompt)
        _require_role(answer, role_name=ROLE_VERIFY, where=f"{batch_id}/{label}")
        others = site.checkers | {given["answered_by"] for given in earlier.get(label, [])}
        if answer.answered_by in others:
            raise WcRunError(
                f"{batch_id}/{label}: {answer.answered_by} checked or verified this site before - "
                "a verification is an independent agent's; have the batch answered again by a new "
                "agent under its own name"
            )
        try:
            verdict = A.parse_verify(answer.text, site_id=label, kept=len(record["shown"][label]))
        except A.AnswerError as exc:
            raise WcRunError(
                f"{batch_id}/{label}: malformed answer ({exc}) - verify-check-answer refuses it; "
                "delete the answer file and have the batch agent answer it again"
            ) from exc
        text = str(wc4.compose(current, site.quotes).description)
        parsed[label] = (batch_id, line, answer, verdict, text)
        urls.update(q.url for item in verdict.kept for q in item.quotes)
    pages = run / VERIFY_DIR / PAGES_DIR
    fetch(urls, pages, client=client, pace=pace)
    library = Q.Library(REPO, pages)
    rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    for label, (batch_id, line, answer, verdict, text) in sorted(parsed.items()):
        shown = record["shown"][label]
        given: dict[str, Any] = {
            "round": number,
            "stage": stage,
            "batch_id": batch_id,
            "answered_by": answer.answered_by,
            "answered_at": answer.answered_at,
            "prompt_sha256": line["prompt_sha256"],
            "answer_sha256": M.text_sha256(answer.text),
            "shown": shown,
            "text_sha256": M.text_sha256(text),
            "verdicts": [],
            "coherent": verdict.coherent,
            "broken": list(verdict.broken),
            "note": verdict.note,
        }
        for item in verdict.kept:
            quote_check = A.check_quotes(label, item.quotes, library)
            given["verdicts"].append(
                {
                    "k": item.number,
                    "n": shown[item.number - 1],
                    "verdict": item.verdict,
                    "quotes": [{"url": q.url, "quote": q.quote} for q in item.quotes],
                    "note": item.note,
                    "quotes_found": quote_check.counted,
                    "quote_results": list(quote_check.results),
                }
            )
            verdicts[item.verdict] += 1
        site = sites[label]
        _, _, status = wc4.run_verification(
            site.decisions, site.quotes, [*earlier.get(label, []), given]
        )
        states["due for verify2" if status is None else status.value] += 1
        rows.append({"site_id": label, **given})
    RF.write_jsonl(out, rows)
    return {
        "round": number,
        "stage": stage,
        "sites": len(rows),
        "verdicts": dict(sorted(verdicts.items())),
        "incoherent": sum(not row["coherent"] for row in rows),
        "outcomes": dict(sorted(states.items())),
        "to_verify2": states["due for verify2"],
        "urls": len(urls),
    }


# ------------------------------------------------------------------------------------ the judge
def _judge_view(final: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """A final site's kept sentences (the published text after the verification, with the verified
    quotes its markers cite) and its dropped sentences, in order (`_view`)."""
    decisions, quotes = wc4.decisions_of(final["evidence"])
    return _view(decisions, quotes)


def judge_prompt(final: Mapping[str, Any], site: M.PlanSite, kind: str = KIND_WC) -> str:
    kept, dropped = _judge_view(final)
    return (P2.JUDGE_QUESTION_WN if kind == KIND_WN else P.JUDGE_QUESTION).format(
        site=site_block(site),
        kept=_kept_lines(kept),
        dropped=_dropped_lines(dropped),
        site_id=final["site_id"],
        kept_count=len(kept),
        dropped_count=len(dropped),
    )


def _finals(run: Path) -> dict[str, dict[str, Any]]:
    return {row["site_id"]: row for row in read_jsonl(run / FINAL_FILE)}


def _judge_round(run: Path, handoff: Path) -> dict[str, Any]:
    path = run / JUDGE_DIR / "ROUND.json"
    if not path.exists():
        raise WcRunError(f"{run}: no judge round was exported")
    record = json.loads(path.read_text(encoding="utf-8"))
    if Path(record["handoff"]).resolve() != handoff.resolve():
        raise WcRunError(f"{handoff} is not {run}'s judge round")
    return record


def cmd_judge_export(
    run: Path,
    handoff: Path,
    *,
    batch_size: int,
    sample: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """The pilot's measurement: one judge question per built site, on its text after the
    verification. The round records the sha256 of the gate plan it judges (`plan_sha256`): the
    gate writes a pilot's plan only as it was judged (`pilot_approval`).

    `sample` and `seed` (owner decision D25a of 2026-10-08) make it a **sampled** judge of a chunk
    that is no pilot: `sample` sites are drawn with `seed` from the sites the chunk will write
    (`planned`; a site a list run does not write is not judged) and only they are asked. The round
    records the draw (`sample`) and so does the result; a pilot is judged whole - its verdict is the
    gate's approval of the plan - and a sampled verdict approves nothing (`pilot_approval`)."""
    if (run / JUDGE_DIR / "ROUND.json").exists():
        raise WcRunError(f"{run}: the judge round was exported")
    if (sample is None) != (seed is None):
        raise WcRunError("--sample and --seed go together")
    finals = _finals(run)
    sites = read_sites(run)
    kind = run_kind(run)
    batches: dict[str, list[str]] = {}
    # a lane-WN site whose agent wrote no sentence has nothing to judge
    labels = sorted(label for label, final in finals.items() if final["of"] or kind != KIND_WN)
    drawn: dict[str, Any] | None = None
    if sample is not None and seed is not None:
        # a list run's site that is not written (`unchanged`, `defect-kept`) has no new text to judge
        labels = [label for label in labels if finals[label].get("planned", True)]
        if json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))["pilot"] is not None:
            raise WcRunError(
                f"{run}: a pilot is judged whole - its verdict approves the plan, a sample's cannot"
            )
        if not 1 <= sample <= len(labels):
            raise WcRunError(f"a sample of {sample} from {len(labels)} judgeable site(s)")
        drawn = {"sites": sample, "seed": seed, "of": len(labels)}
        chosen = set(audit4.draw_sample(labels, seed=seed, count=sample, exclude=set()))
        labels = [label for label in labels if label in chosen]
    for start in range(0, len(labels), batch_size):
        batch_id = f"judge-{start // batch_size + 1:04d}"
        for label in labels[start : start + batch_size]:
            site = M.PlanSite.from_dict(sites[label]["plan_site"])
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=JUDGE_STAGE,
                label=label,
                field="description",
                prompt=judge_prompt(finals[label], site, kind),
            )
            batches.setdefault(batch_id, []).append(label)
    RF.write_json(
        run / JUDGE_DIR / "ROUND.json",
        {
            "handoff": _shown(handoff),
            "exported_at": RF.now(),
            "batches": batches,
            "plan_sha256": _sha256(run / PLAN_FILE),
            "sample": drawn,
        },
    )
    return {"questions": len(labels), "batches": len(batches), "sample": drawn}


def judge_brief(run: Path, handoff: Path, batch_id: str) -> str:
    record = _judge_round(run, handoff)
    if batch_id not in record["batches"]:
        raise WcRunError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return P.JUDGE_BRIEF.format(
        **_role_fields(ROLE_JUDGE),
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        python=Path(sys.executable).as_posix(),
        repo=REPO.as_posix(),
        stage=JUDGE_STAGE,
        batch_agent=f"{_agent_family(ROLE_JUDGE)}-wc-judge-{batch_id}",
    )


def _judge_counts(final: Mapping[str, Any]) -> tuple[int, int]:
    kept, dropped = _judge_view(final)
    return len(kept), len(dropped)


def judge_check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str
) -> str | None:
    record = _judge_round(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise WcRunError(f"{batch_id}/{label} is no question of {handoff}")
    kept, dropped = _judge_counts(_finals(run)[label])
    try:
        A.parse_judge(text, site_id=label, kept=kept, dropped=dropped)
    except A.AnswerError as exc:
        return str(exc)
    return None


def cmd_judge_import(
    run: Path, handoff: Path, *, client: A.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """The judge's answers: validated, parsed, quote-checked; the measurement and its verdict. The
    judge is fresh: a name that checked or verified any site of the run does not count."""
    record = _judge_round(run, handoff)
    if record.get("calibration"):
        raise WcRunError(
            f"{run}: the judge round is a calibration round; a comparison is never imported"
        )
    check = OH.validate(handoff)
    if not check.ok:
        raise WcRunError(f"{handoff}: the judge round does not validate: {check.to_dict()}")
    finals = _finals(run)
    sites = read_sites(run)
    run_of = run_kind(run)
    workers = {
        attempt["answered_by"]
        for final in finals.values()
        for attempt in final["evidence"]["answers"]
    } | {
        r["answered_by"]
        for final in finals.values()
        for r in final["evidence"][wc4.VERIFICATION_KEY]["rounds"]
    }
    judged: list[dict[str, Any]] = []
    for line in OH.manifest(handoff):
        batch_id, label = line["batch_id"], line["label"]
        site = M.PlanSite.from_dict(sites[label]["plan_site"])
        prompt = judge_prompt(finals[label], site, run_of)
        answer = OH.read_answer(
            handoff, batch_id=batch_id, stage=JUDGE_STAGE, label=label, prompt=prompt
        )
        _require_role(answer, role_name=ROLE_JUDGE, where=f"{batch_id}/{label}")
        kept, dropped = _judge_counts(finals[label])
        parsed = A.parse_judge(answer.text, site_id=label, kept=kept, dropped=dropped)
        pages = run / JUDGE_DIR / PAGES_DIR
        items = [*parsed.kept, *parsed.dropped]
        fetch([q.url for item in items for q in item.quotes], pages, client=client, pace=pace)
        library = Q.Library(REPO, pages)
        rows = []
        for kind, group in (("kept", parsed.kept), ("dropped", parsed.dropped)):
            for item in group:
                quote_check = A.check_quotes(label, item.quotes, library)
                rows.append(
                    {
                        "kind": kind,
                        **item.to_dict(),
                        "quotes_found": quote_check.counted,
                        "quote_results": list(quote_check.results),
                    }
                )
        judged.append(
            {
                "site_id": label,
                "batch_id": batch_id,
                "answered_by": answer.answered_by,
                "independent": answer.answered_by not in workers,
                "coherent": parsed.coherent,
                "note": parsed.note,
                "items": rows,
            }
        )
    if {row["site_id"] for row in judged} != {
        label for labels in record["batches"].values() for label in labels
    }:
        raise WcRunError(f"{handoff}: the manifest is not the judge round's record")
    RF.write_jsonl(run / JUDGE_DIR / "JUDGED.jsonl", judged)
    # a WN pilot must have judged half of its drawn sites; a sampled judge of a chunk judges a sample
    drawn = (
        json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))["asked"]
        if run_of == KIND_WN and record.get("sample") is None
        else None
    )
    result = {**judge_result(judged, drawn=drawn), "plan_sha256": record["plan_sha256"]}
    if record.get("sample") is not None:
        result["sample"] = record["sample"]
    RF.write_json(run / JUDGE_DIR / "RESULT.json", result)
    return result


def judge_result(
    judged: Sequence[Mapping[str, Any]], *, drawn: int | None = None
) -> dict[str, Any]:
    """The pilot's measurement and its verdict against `J_THRESHOLDS`. A judge who checked or
    verified a site of the run is not independent: such a site does not count, and the pilot
    cannot pass while one does not. `drawn` (a WN pilot: the sites it drew) adds the minimum sample
    (`wn_pilot_minimum`): too few judged texts or kept sentences is a failure, not a pass."""
    counted = [row for row in judged if row["independent"]]
    kept = [item for row in counted for item in row["items"] if item["kind"] == "kept"]
    dropped = [item for row in counted for item in row["items"] if item["kind"] == "dropped"]
    wrong = sum(item["verdict"] == "WRONG" and item["quotes_found"] for item in kept)
    unsupported = sum(
        item["verdict"] == "UNSUPPORTED"
        or (item["verdict"] == "WRONG" and not item["quotes_found"])
        for item in kept
    )
    incoherent = sum(not row["coherent"] for row in counted)
    share = unsupported / len(kept) if kept else 0.0
    measured = {
        "sites": len(judged),
        "independent": len(counted),
        "kept_sentences": len(kept),
        "dropped_sentences": len(dropped),
        "wrong": wrong,
        "unsupported": unsupported,
        "unsupported_share": round(share, 4),
        "incoherent": incoherent,
        "drop_wrong": sum(
            item["verdict"] == "DROP_WRONG" and item["quotes_found"] for item in dropped
        ),
        "drop_wrong_unverified": sum(
            item["verdict"] == "DROP_WRONG" and not item["quotes_found"] for item in dropped
        ),
    }
    failures = []
    if len(counted) != len(judged):
        failures.append(
            f"{len(judged) - len(counted)} site(s) judged by a checker or verifier of the run"
        )
    if drawn is not None:
        need = wn_pilot_minimum(drawn)
        measured["drawn"], measured["minimum"] = drawn, need
        if len(counted) < need:
            failures.append(
                f"{len(counted)} of the {drawn} drawn site(s) ended with a text the judge could "
                f"judge, at least {need} are needed: the pilot measured too little"
            )
        if len(kept) < need:
            failures.append(f"{len(kept)} kept sentence(s) judged, at least {need} are needed")
    if wrong > J_THRESHOLDS["wrong"]:
        failures.append(f"{wrong} kept sentence(s) WRONG with a found quote")
    if share > J_THRESHOLDS["unsupported_share"]:
        failures.append(f"{share:.1%} of kept sentences UNSUPPORTED, above 5 %")
    if incoherent > J_THRESHOLDS["incoherent"]:
        failures.append(f"{incoherent} site(s) whose kept text is incoherent")
    return {
        "measured": measured,
        "thresholds": J_THRESHOLDS,
        "failures": failures,
        "passed": not failures,
    }


def pilot_approval(plans: Sequence[Path]) -> list[dict[str, str]]:
    """The pilot verdict every WC plan the gate writes rests on (`write_gate4.wc_batches`; the review
    of 2026-09-26: nothing tied a mass plan to a passed pilot). Each plan is `<run>/WC4.jsonl`. The
    first plan named is a pilot run's (`export --pilot`), and every pilot run named was judged and
    passed (`judge/RESULT.json`, `passed: true`) on exactly this plan (`plan_sha256`: a plan built
    again after its judge is not the judged one): a failed pilot's outcomes are never written, and
    no chunk is written before a passed pilot. Returns each pilot run with its result's sha256.

    Each **kind of text** has its own pilot (2026-10-01): a lane-WN plan (`kind` `wn`) is approved by a
    WN pilot, every other plan (a plain run, a site-list run) by a WC pilot - the first plan named of
    each is its pilot's, and a WN mass plan is never written on a WC pilot's verdict, nor the other
    way round. The WC pilot is a **plain** run's: a site-list run (`wc-list`) is approved by it and
    can never be it, so a pilot of Phase-4 texts does not approve plain chunks of March texts (a list
    run may itself be a judged pilot, named after the plain one). Everything else is as above, for
    each."""
    if not plans:
        raise WcRunError("no WC plan named")
    approvals: list[dict[str, str]] = []
    seen: set[str] = set()
    for plan in plans:
        run = plan.parent
        population = json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))
        pilot = population["pilot"]
        kind = population.get("kind", KIND_WC)
        which = "WN" if kind == KIND_WN else "WC"
        if which not in seen:
            seen.add(which)
            if pilot is None:
                raise WcRunError(
                    f"{plan}: the first {which} plan named is the pilot's (export --pilot), "
                    "whose judge passed - this run is not a pilot"
                )
            if kind == KIND_LIST:
                raise WcRunError(
                    f"{plan}: the first WC plan named is a plain WC run's pilot, not a site-list "
                    "run's: a list of Phase-4 texts measures no March text, so it cannot approve "
                    "plain chunks - name the WC pilot first"
                )
        if pilot is None:
            continue
        if which == "WN" and pilot["sites"] != wn_pilot_size(population["population"]):
            raise WcRunError(
                f"{run}: a WN pilot of {pilot['sites']} sites from a population of "
                f"{population['population']} - it draws {wn_pilot_size(population['population'])}"
            )
        path = run / JUDGE_DIR / "RESULT.json"
        if not path.exists():
            raise WcRunError(f"{run}: the pilot was not judged (judge-import writes {path.name})")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("sample") is not None:
            raise WcRunError(
                f"{run}: the pilot was judged by a sample ({result['sample']}): a sampled verdict "
                "approves no plan - judge the pilot whole"
            )
        if result["passed"] is not True:
            raise WcRunError(
                f"{run}: the pilot's judge did not pass ({result['failures']}): its outcomes are "
                "never written - fix the cause and run a new pilot"
            )
        if which == "WN":
            need = wn_pilot_minimum(population["asked"])
            measured = result["measured"]
            if measured["independent"] < need or measured["kept_sentences"] < need:
                raise WcRunError(
                    f"{run}: the WN pilot measured too little ({measured['independent']} judged "
                    f"text(s), {measured['kept_sentences']} kept sentence(s); at least {need} of "
                    f"each for the {population['asked']} sites drawn)"
                )
        if result.get("plan_sha256") != _sha256(plan):
            raise WcRunError(
                f"{plan}: not the plan the pilot's judge judged (RESULT.json plan_sha256 "
                f"{result.get('plan_sha256')!r}): a plan is written only as it was judged"
            )
        approvals.append({"run": _shown(run), "result_sha256": _sha256(path)})
    return approvals


# ------------------------------------------------------------------------------------ the defects
#: The keys of one line of a WB run's `DESCRIPTION_DEFECTS.jsonl` (`teaser/run.description_defects`).
DEFECT_KEYS = frozenset(
    {
        "basis", "candidates", "claim", "desc_sha256", "mapped_by", "name", "owner_lane", "proven",
        "quote", "quote_outcome", "run", "sentence", "sentence_text", "site_id", "stage", "url",
        "verifier",
    }
)  # fmt: skip


#: What the report keeps of a defect line, per site: enough to put the claim, its sentence and the
#: contradicting page before the agent that checks the text again (`export --defects`).
DEFECT_CLAIM_KEYS = (
    "run", "stage", "owner_lane", "basis", "sentence", "sentence_text", "claim", "url", "quote",
    "quote_outcome", "proven",
)  # fmt: skip


def cmd_defect_sites(
    run: Path, defects: Sequence[Path], out: Path, *, proven_only: bool = False
) -> dict[str, Any]:
    """The site list of a repair run (`export --sites`) from WB's description defects: every site a
    line names whose description is still the text the line was found on (`desc_sha256` is the
    stored description's sha256 in the run's fresh read - a text WA or WC rewrote since is not the
    defective one and is left out, counted `text-changed-since`), that is a curated, not retired
    row of the read. `out` gets one site id per line; `out.report.json` the counts and, per site,
    the claims. `proven_only` keeps only the lines whose contradicting quote the machine found."""
    rows = {row["id"]: row for row in read_jsonl(run / ROWS_FILE)}
    lines = 0
    skipped: Counter[str] = Counter()
    per_site: dict[str, list[dict[str, Any]]] = {}
    for path in defects:
        for number, line in enumerate(read_jsonl(path), start=1):
            if set(line) != DEFECT_KEYS:
                raise WcRunError(
                    f"{path}:{number}: not a DESCRIPTION_DEFECTS line (keys {sorted(line)})"
                )
            lines += 1
            try:
                site_id = revert4.check_site(line["site_id"])
            except revert4.RevertRefused as exc:
                raise WcRunError(f"{path}:{number}: {exc}") from None
            row = rows.get(site_id)
            if proven_only and not line["proven"]:
                skipped["unproven"] += 1
            elif row is None:
                skipped["not-a-curated-row"] += 1
            elif row["scope_status"] == "retired":
                skipped["retired"] += 1
            elif row["description_sha256"] != line["desc_sha256"]:
                skipped["text-changed-since"] += 1
            else:
                per_site.setdefault(site_id, []).append(
                    {key: line[key] for key in DEFECT_CLAIM_KEYS}
                )
    ids = sorted(per_site)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{site_id}\n" for site_id in ids), encoding="utf-8", newline="\n")
    report = {
        "read": json.loads((run / READ_FILE).read_text(encoding="utf-8")),
        "defects": [{"path": _shown(path), "sha256": _sha256(path)} for path in defects],
        "proven_only": proven_only,
        "lines": lines,
        "sites": len(ids),
        "skipped": dict(sorted(skipped.items())),
        "by_owner_lane": dict(
            sorted(Counter(c["owner_lane"] for cs in per_site.values() for c in cs[:1]).items())
        ),
        "out": {"path": _shown(out), "sha256": _sha256(out)},
        "claims": {site_id: per_site[site_id] for site_id in ids},
    }
    RF.write_json(out.with_name(out.name + ".report.json"), report)
    return {key: value for key, value in report.items() if key != "claims"}


# ------------------------------------------------------------------------------------ the repairs
def _write_list(out: Path, ids: Sequence[str], report: Mapping[str, Any]) -> dict[str, Any]:
    """A site list (one id per line) and its `.report.json`, which records the list's sha256 - the
    shape `export --sites ... --defects` reads."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{site_id}\n" for site_id in ids), encoding="utf-8", newline="\n")
    full = {**report, "out": {"path": _shown(out), "sha256": _sha256(out)}}
    RF.write_json(out.with_name(out.name + ".report.json"), full)
    return full


def cmd_defect_kept_sites(run: Path, sources: Sequence[Path], out: Path) -> dict[str, Any]:
    """The site list of an adversarial second check (owner decision D25b, 2026-10-08): every site
    whose reported claim a built site-list run (`sources`) left standing - its sentence kept, by the
    check and by the verifier. `run` holds a fresh read, made after the sources' plans were written,
    so a site a source rewrote carries its new text: each claim's sentence is found again in the
    live text (the kept sentence as the source's FINAL decision left it, after a trim) and numbered
    as it stands now; a claim tied to no sentence stays tied to none. A site is left out, counted
    under its reason, when it is no curated row, is retired, has no description now, or no longer
    holds the kept sentence (`text-changed-since`). `out.report.json` is `defect-sites`' report for
    the adversarial export: the read, the list's sha256 and the claims."""
    rows = {row["id"]: row for row in read_jsonl(run / ROWS_FILE)}
    skipped: Counter[str] = Counter()
    per_site: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        summary = json.loads((source / SUMMARY_FILE).read_text(encoding="utf-8"))
        if "defects_kept" not in summary:
            raise WcRunError(
                f"{source}: not a built site-list run (SUMMARY.json has no defects_kept)"
            )
        asked = read_sites(source)
        finals = _finals(source)
        for site_id, standing in sorted(summary["defects_kept"].items()):
            row = rows.get(site_id)
            if row is None:
                skipped["not-a-curated-row"] += 1
            elif row["scope_status"] == "retired":
                skipped["retired"] += 1
            elif wc4.is_empty(row["description"]):
                skipped["no-description"] += 1
            else:
                current = wc4.checked_sentences(row["description"])
                for given in standing:
                    key = (given["claim"], given["url"], given["sentence"])
                    found = [
                        claim
                        for claim in asked[site_id]["defects"]
                        if (claim["claim"], claim["url"], claim["sentence"]) == key
                    ]
                    if len(found) != 1:
                        raise WcRunError(
                            f"{source}/{site_id}: the standing claim {given!r} is not one claim "
                            "of the run's report"
                        )
                    claim = dict(found[0])
                    if claim["sentence"] is not None:
                        kept_text = finals[site_id]["decisions"][claim["sentence"] - 1]["text"]
                        if kept_text is None or kept_text not in current:
                            skipped["text-changed-since"] += 1
                            continue
                        claim["sentence"] = current.index(kept_text) + 1
                        claim["sentence_text"] = kept_text
                    per_site.setdefault(site_id, []).append(claim)
    ids = sorted(per_site)
    report = _write_list(
        out,
        ids,
        {
            "read": json.loads((run / READ_FILE).read_text(encoding="utf-8")),
            "from": [{"path": _shown(s), "sha256": _sha256(s / SUMMARY_FILE)} for s in sources],
            "sites": len(ids),
            "skipped": dict(sorted(skipped.items())),
            "claims": {site_id: per_site[site_id] for site_id in ids},
        },
    )
    return {key: value for key, value in report.items() if key != "claims"}


CLOSURE_FILE = "CLOSURE.json"


def cmd_defect_closure(run: Path) -> dict[str, Any]:
    """What an adversarial second check decided, claim by claim, for the audit log: a claim whose
    sentence the adversary dropped is **resolved** (the drop is written like every WC drop); one
    whose sentence it kept is **refuted** - the report is closed on the adversary's note and quotes
    and the verifier's verdict, which the log records (`CLOSURE.json`, written once, and its markdown
    lines). Only a built adversarial run has one."""
    if not run_adversarial(run):
        raise WcRunError(f"{run}: not an adversarial second check (export --adversarial)")
    if (run / CLOSURE_FILE).exists():
        raise WcRunError(f"{run / CLOSURE_FILE} exists: a closure is written once")
    summary = json.loads((run / SUMMARY_FILE).read_text(encoding="utf-8"))
    asked = read_sites(run)
    finals = _finals(run)
    resolved: list[dict[str, Any]] = []
    refuted: list[dict[str, Any]] = []
    for site_id, entry in asked.items():
        final = finals[site_id]
        rounds = final["verification"]["rounds"]
        for claim in entry.get("defects") or []:
            number = claim["sentence"]
            decisions = final["decisions"]
            kept = (
                all(d["text"] is not None for d in decisions)
                if number is None
                else decisions[number - 1]["text"] is not None
            )
            sentence = None if number is None else final["evidence"]["sentences"][number - 1]
            line = {
                "site_id": site_id,
                "name": entry["name"],
                "sentence": number,
                "sentence_text": claim["sentence_text"],
                "claim": claim["claim"],
                "reported_url": claim["url"],
                "reported_run": claim["run"],
            }
            if not kept:
                reason = None if number is None else decisions[number - 1]["reason"]
                resolved.append(
                    {
                        **line,
                        "reason": reason,
                        "note": None if sentence is None else sentence["note"],
                        "quotes": [] if sentence is None else sentence["quotes"],
                    }
                )
                continue
            refuted.append(
                {
                    **line,
                    "adversary_note": None if sentence is None else sentence["note"],
                    "adversary_quotes": [] if sentence is None else sentence["quotes"],
                    "verifiers": [
                        {
                            "answered_by": r["answered_by"],
                            "stage": r["stage"],
                            "verdict": None if number is None else r["verdicts"].get(str(number)),
                        }
                        for r in rounds
                    ],
                }
            )
    standing = {
        site: [c["claim"] for c in claims] for site, claims in summary["defects_kept"].items()
    }
    record = {
        "run": run.name,
        "closed_at": RF.now(),
        "claims": len(resolved) + len(refuted),
        "resolved": resolved,
        "refuted": refuted,
        "standing_in_summary": standing,
    }
    RF.write_json(run / CLOSURE_FILE, record)
    return record


def closure_markdown(record: Mapping[str, Any]) -> str:
    """The closure as lines for the audit log: one per claim, the refutations with the adversary's
    note and the quotes it relied on."""
    lines = [
        f"### Adversarial second check `{record['run']}`: {len(record['resolved'])} claim(s) "
        f"resolved by a drop, {len(record['refuted'])} refuted (defect line closed)"
    ]
    for item in record["resolved"]:
        lines.append(
            f"- RESOLVED {item['name']} ({item['site_id']}) S{item['sentence']}: "
            f'"{item["claim"]}" - dropped ({item["reason"]})'
        )
    for item in record["refuted"]:
        quotes = "; ".join(f"{q['url']}" for q in item["adversary_quotes"] if q.get("verified"))
        lines.append(
            f"- REFUTED {item['name']} ({item['site_id']}) S{item['sentence']}: "
            f'"{item["claim"]}" (reported against {item["reported_url"]}) - kept: '
            f"{item['adversary_note']} [{quotes}]"
        )
    return "\n".join(lines)


def _text_rounds(run: Path, base: Path) -> list[tuple[str, Path, Mapping[str, Sequence[str]]]]:
    """`(stage, handoff, batches)` of every check, write and verification round the run exported."""
    stage = WRITE_STAGE if run_kind(run) == KIND_WN else STAGE
    rounds = [(stage, base / r["handoff"], r["batches"]) for r in read_rounds(run)]
    rounds += [(r["stage"], base / r["handoff"], r["batches"]) for r in _verify_rounds(run)]
    return rounds


def cmd_minimax_sites(
    run: Path, sources: Sequence[Path], out: Path, *, base: Path = REPO
) -> dict[str, Any]:
    """The site list of the Claude re-check of MiniMax-touched texts (owner decision D10,
    2026-10-08): every site that has an answer stamped MiniMax in a check, write or verification
    round of a source run, and whose live text (`run`'s fresh read) is still the one that source
    wrote (`_description_check` names the source and hashes the live description). The others are
    reported by reason and not asked: `cleared` (no description now: lane WN's rerun takes them),
    `rewritten-since` (another lane wrote the text), `retired`, `not-a-curated-row`. The list goes to
    `export --sites`, where a text lane WN wrote is asked again as `web`."""
    rows = {row["id"]: row for row in read_jsonl(run / ROWS_FILE)}
    touched: dict[str, set[str]] = {}
    for source in sources:
        for stage, handoff, batches in _text_rounds(source, base):
            for batch_id, labels in batches.items():
                for label in labels:
                    path = handoff / OH.answer_relpath(batch_id, stage, label)
                    if path.exists() and (
                        json.loads(path.read_text(encoding="utf-8"))["model"] == OH.MINIMAX_MODEL
                    ):
                        touched.setdefault(label, set()).add(source.name)
    holds: list[str] = []
    other: dict[str, list[str]] = {}
    for site_id in sorted(touched):
        row = rows.get(site_id)
        if row is None:
            reason = "not-a-curated-row"
        elif row["scope_status"] == "retired":
            reason = "retired"
        elif wc4.is_empty(row["description"]):
            reason = "cleared"
        else:
            check = (row["raw_data"] or {}).get(wc4.CHECK_KEY) or {}
            same = (
                check.get("run") in touched[site_id]
                and check.get("desc_sha256") == row["description_sha256"]
            )
            reason = "holds-its-text" if same else "rewritten-since"
        if reason == "holds-its-text":
            holds.append(site_id)
        else:
            other.setdefault(reason, []).append(site_id)
    report = _write_list(
        out,
        holds,
        {
            "read": json.loads((run / READ_FILE).read_text(encoding="utf-8")),
            "from": [_shown(s) for s in sources],
            "touched": len(touched),
            "sites": len(holds),
            "others": {reason: sorted(ids) for reason, ids in sorted(other.items())},
            "others_counts": {reason: len(ids) for reason, ids in sorted(other.items())},
        },
    )
    return report


# ------------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wc", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("read", "the one read-only production SELECT"),
        ("export", "round 1: the population's (or the pilot's) questions"),
        ("brief", "the instruction of one batch's Opus agent"),
        ("check-answer", "one answer's shape, quotes and the text it leaves"),
        ("import", "one round: validate, parse, fetch, check"),
        ("export-reask", "round 2: the sentences that did not count, once"),
        ("verify-export", "the next verification round: verify, then verify2 once"),
        ("verify-brief", "the instruction of one verification batch's Opus agent"),
        ("verify-check-answer", "one verifier answer's shape"),
        ("verify-import", "one verification round: validate, parse, fetch, check"),
        ("build", "the outcomes, the summary and the gate plan"),
        ("judge-export", "the pilot's independent judge questions"),
        ("judge-brief", "the instruction of one judge batch's Opus agent"),
        ("judge-check-answer", "one judge answer's shape"),
        ("judge-import", "the judge's answers, the measurement and its verdict"),
        ("defect-sites", "a site list from WB's DESCRIPTION_DEFECTS.jsonl files"),
        ("verify-void", "move the MiniMax verification answers aside (dry run unless --apply)"),
        ("defect-kept-sites", "a site list for the adversarial second check of standing claims"),
        ("defect-closure", "what an adversarial second check decided, for the audit log"),
        ("minimax-sites", "a site list: the texts MiniMax answers shaped and that still stand"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("--run-dir", required=True, type=Path)
        if name not in (
            "read",
            "build",
            "defect-sites",
            "verify-void",
            "defect-kept-sites",
            "defect-closure",
            "minimax-sites",
        ):
            command.add_argument("--handoff", required=True, type=Path)
        if name in (
            "brief",
            "check-answer",
            "verify-brief",
            "verify-check-answer",
            "judge-brief",
            "judge-check-answer",
        ):
            command.add_argument("--batch-id", required=True)
        if name in ("check-answer", "verify-check-answer", "judge-check-answer"):
            command.add_argument("--label", required=True)
            command.add_argument("--text-file", required=True, type=Path)
        if name in ("export", "export-reask", "verify-export", "judge-export"):
            command.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        if name == "judge-export":
            command.add_argument("--sample", type=int, default=None)
            command.add_argument("--seed", type=int, default=None)
        if name == "read":
            command.add_argument("--host", default=W.SSH_HOST)
        if name == "defect-sites":
            command.add_argument("--defects", type=Path, action="append", required=True)
            command.add_argument("--out", type=Path, required=True)
            command.add_argument("--proven-only", action="store_true")
        if name == "export":
            command.add_argument("--sites", type=Path, default=None)
            command.add_argument("--wn", action="store_true")
            command.add_argument("--defects", type=Path, default=None)
            command.add_argument("--adversarial", action="store_true")
            command.add_argument("--exclude", type=Path, default=None)
            command.add_argument("--after", type=Path, action="append", default=[])
            command.add_argument("--pilot", type=int, default=None)
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--seed", type=int, default=None)
        if name == "check-answer":
            command.add_argument("--no-fetch", action="store_true")
        if name == "build":
            command.add_argument("--first-batch", type=int, required=True)
        if name == "verify-void":
            command.add_argument("--apply", action="store_true")
            command.add_argument("--tag", default=None)
        if name in ("defect-kept-sites", "minimax-sites"):
            command.add_argument(
                "--from", type=Path, action="append", required=True, dest="sources"
            )
            command.add_argument("--out", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> int:
    run: Path = args.run_dir
    command = args.command
    if command == "read":
        run.mkdir(parents=True, exist_ok=True)
        _print(cmd_read(run, host=args.host))
    elif command == "export":
        _print(
            cmd_export(
                run,
                args.handoff,
                batch_size=args.batch_size,
                exclude=args.exclude,
                after=args.after,
                pilot=args.pilot,
                seed=args.seed,
                limit=args.limit,
                sites=args.sites,
                wn=args.wn,
                defects=args.defects,
                adversarial=args.adversarial,
            )
        )
    elif command == "brief":
        print(brief(run, args.handoff, args.batch_id))
    elif command == "check-answer":
        text = args.text_file.read_bytes().decode("utf-8")
        clean, report = check_answer(
            run, args.handoff, args.batch_id, args.label, text, fetch_pages=not args.no_fetch
        )
        print(report)
        return 0 if clean else 1
    elif command == "import":
        _print(cmd_import(run, args.handoff))
    elif command == "export-reask":
        _print(cmd_export_reask(run, args.handoff, batch_size=args.batch_size))
    elif command == "verify-export":
        _print(cmd_verify_export(run, args.handoff, batch_size=args.batch_size))
    elif command == "verify-brief":
        print(verify_brief(run, args.handoff, args.batch_id))
    elif command == "verify-check-answer":
        text = args.text_file.read_bytes().decode("utf-8")
        problem = verify_check_answer(run, args.handoff, args.batch_id, args.label, text)
        print(problem or "in shape")
        return 1 if problem else 0
    elif command == "verify-import":
        _print(cmd_verify_import(run, args.handoff))
    elif command == "build":
        _print(cmd_build(run, first_batch=args.first_batch))
    elif command == "judge-export":
        _print(
            cmd_judge_export(
                run, args.handoff, batch_size=args.batch_size, sample=args.sample, seed=args.seed
            )
        )
    elif command == "judge-brief":
        print(judge_brief(run, args.handoff, args.batch_id))
    elif command == "judge-check-answer":
        text = args.text_file.read_bytes().decode("utf-8")
        problem = judge_check_answer(run, args.handoff, args.batch_id, args.label, text)
        print(problem or "in shape")
        return 1 if problem else 0
    elif command == "judge-import":
        result = cmd_judge_import(run, args.handoff)
        _print(result)
        return 0 if result["passed"] else 1
    elif command == "defect-sites":
        _print(cmd_defect_sites(run, args.defects, args.out, proven_only=args.proven_only))
    elif command == "verify-void":
        _print(V.verify_void(run, base=REPO, apply=args.apply, tag=args.tag))
    elif command == "defect-kept-sites":
        _print(cmd_defect_kept_sites(run, args.sources, args.out))
    elif command == "defect-closure":
        record = cmd_defect_closure(run)
        _print({k: record[k] for k in ("run", "claims")} | {"closure": _shown(run / CLOSURE_FILE)})
        print(closure_markdown(record))
    elif command == "minimax-sites":
        _print(cmd_minimax_sites(run, args.sources, args.out))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    W.utf8_streams()
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    tag = "JUDGE" if args.command == "judge-import" else "WC"
    try:
        code = run_command(args)
    except (
        WcRunError,
        OH.HandoffError,
        wc4.WcError,
        Q.AuditError,
        A.AnswerError,
        V.VoidError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        code = 1
    print(f"{tag}_EXIT={code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
