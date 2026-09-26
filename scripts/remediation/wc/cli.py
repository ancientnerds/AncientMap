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
    $C build              --run-dir R --first-batch N    # FINAL, SUMMARY, WC4.jsonl (the gate plan)
    $C judge-export       --run-dir R --handoff HJ       # the pilot's independent judge
    $C judge-brief        --run-dir R --handoff HJ --batch-id B
    $C judge-check-answer --run-dir R --handoff HJ --batch-id B --label SITE --text-file F
    $C judge-import       --run-dir R --handoff HJ       # RESULT.json, JUDGE_EXIT=

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
(`unverified`). `build` refuses while a re-ask is due or unimported.

**The build** (`build`): per site, each sentence's decision from the last round that asked it, the
pronoun rule (`wc4.follow_drops`), the composed text and citations (`wc4.compose`), the check record
and the raw_data (`wc4.check_record`, `wc4.written_raw_data`), the journal evidence (every decision
with the agent's quotes and what the check said of each, every answer's sha256), then the gate plan
`WC4.jsonl` - batches of `wc4.BATCH_SIZE` sites from `--first-batch`, marked `wc4.PLAN_MARK` - which
`write_gate4.py --group WC --wc-plan` writes in steps.

**Chunks** (`export --limit N`): the first N sites of the population in site-id order, the next
chunk naming every earlier chunk not yet written in `--after`; each chunk is its own run, imported,
built and written on its own, so the writes start while later chunks are still being answered.

**The pilot** (`export --pilot 20 --seed S`): a seeded draw of the population, run end to end; its
result is measured by an independent Opus judge (`judge-*`: every kept sentence SUPPORTED,
UNSUPPORTED or WRONG, every dropped one DROP_OK or DROP_WRONG, the kept text coherent or not;
quotes machine-checked; a judge who answered a check question of the site does not count) against
the thresholds `J_THRESHOLDS`, before the mass run: `judge-import` prints `JUDGE_EXIT=0` for a pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402 - the one contract every model answer goes through
from opus_audit import quotes as Q  # noqa: E402
from phase3 import write_stage as W  # noqa: E402 - the read-only psql seam
from phase3.run import read_jsonl  # noqa: E402
from phase4 import audit4, plan4, wc4  # noqa: E402 - the seeded draw, the plan read, lane WC
from phase4 import model4 as M  # noqa: E402

from wc import answers as A  # noqa: E402
from wc import prompts as P  # noqa: E402

STAGE = "check"
JUDGE_STAGE = "judge"
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
#: The lanes whose provenance is a full Phase-4 one: their text is Phase 4's, never WC's.
FULL_LANES = frozenset(lane.value for lane in M.LANE_CHANGES)
#: The pilot's pass mark, sealed with the lane (docs/procedures/SENTENCE_CHECK.md): no kept
#: sentence a judge shows WRONG with a found quote, at most 5 % of kept sentences UNSUPPORTED (a
#: WRONG whose quote was not found counts here), and no site whose kept text is incoherent.
J_THRESHOLDS = {"wrong": 0, "unsupported_share": 0.05, "incoherent": 0}

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
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _shown(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids(path: Path) -> set[str]:
    """One site id per line (blank lines skipped); anything else stops the command."""
    ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if text and not wc_id(text):
            raise WcRunError(f"{path}:{number}: {text!r} is not a site id")
        if text:
            ids.add(text)
    return ids


def wc_id(text: str) -> bool:
    return len(text) == 36 and text.count("-") == 4 and text == text.lower()


# ------------------------------------------------------------------------------------ the read
def cmd_read(run: Path, *, runner: W.SqlRunner = W.run_sql, host: str = W.SSH_HOST) -> dict:
    """The one read-only SELECT (`WC_SQL`): every curated row, as Phase 4 reads it, with its scope
    status. Written to `ROWS.jsonl`; `READ.json` records when and the file's sha256."""
    rows = W._json_rows(runner(WC_SQL, host=host))
    _write_jsonl(run / ROWS_FILE, rows)
    record = {"read_at": _now(), "rows": len(rows), "sha256": _sha256(run / ROWS_FILE)}
    _write_json(run / READ_FILE, record)
    return record


# ------------------------------------------------------------------------------------ the population
def population(
    rows: Sequence[Mapping[str, Any]], *, excluded: set[str], earlier: set[str]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """The sites to ask, in site-id order (each `{site_id, name, marking, sentences, plan_site}`),
    and every other curated site of the read, by the reason it is not asked."""
    asked: list[dict[str, Any]] = []
    listed: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda row: row["id"]):
        site_row = {key: value for key, value in row.items() if key != "scope_status"}
        site = plan4.plan_site(site_row, flags=frozenset())
        reason, marking, sentences = _classify(row, site, excluded=excluded, earlier=earlier)
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
    row: Mapping[str, Any], site: M.PlanSite, *, excluded: set[str], earlier: set[str]
) -> tuple[str | None, str | None, tuple[str, ...]]:
    if row["scope_status"] == "retired":
        return "retired", None, ()
    if site.description is None or not site.description.strip():
        return "no-description", None, ()
    raw = site.raw_data or {}
    if wc4.CHECK_KEY in raw:
        return "checked-before", None, ()
    if M.PROVENANCE_KEY in raw:
        stored = raw[M.PROVENANCE_KEY]
        if isinstance(stored, dict) and stored.get("lane") in FULL_LANES:
            return "phase4-text", None, ()
        try:
            provenance = M.LegacyProvenance.from_dict(stored)
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
    return None, wc4.old_marking(site).value, sentences


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


def check_prompt(
    entry: Mapping[str, Any], asked: Sequence[int], failures: Mapping[str, Sequence[str]]
) -> str:
    """The exact question about one site: round 1 asks every sentence and has no failures; the
    re-ask round asks the failed ones and says what failed (`failures`: sentence number -> why)."""
    site = M.PlanSite.from_dict(entry["plan_site"])
    sentences = "\n".join(f"S{n}: {text}" for n, text in enumerate(entry["sentences"], start=1))
    reask = ""
    if failures:
        lines = [f"S{n}: " + "; ".join(failures[str(n)]) for n in asked]
        reask = P.REASK_BLOCK.format(failures="\n".join(lines))
    return P.CHECK_QUESTION.format(
        site=site_block(site),
        sentences=sentences,
        reask=reask,
        asked=_asked_text(asked),
        site_id=entry["site_id"],
    )


# ------------------------------------------------------------------------------------ the rounds
def read_sites(run: Path) -> dict[str, dict[str, Any]]:
    return {entry["site_id"]: entry for entry in read_jsonl(run / SITES_FILE)}


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
    batches: dict[str, list[str]] = {}
    for start in range(0, len(questions), batch_size):
        batch_id = f"wc-{start // batch_size + 1:04d}"
        for site_id, asked, failures in questions[start : start + batch_size]:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=STAGE,
                label=site_id,
                field="description",
                prompt=check_prompt(sites[site_id], asked, failures),
            )
            batches.setdefault(batch_id, []).append(site_id)
    record = {
        "round": number,
        "handoff": _shown(handoff),
        "exported_at": _now(),
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
) -> dict[str, Any]:
    """Round 1: the population of the run's read, a seeded pilot draw of it, or its first `limit`
    sites in site-id order (a chunk of the mass run: the next chunk names this run in `--after`),
    one question per site. `POPULATION.json` records every count, reason and input; `SITES.jsonl`
    the asked sites."""
    if (run / SITES_FILE).exists():
        raise WcRunError(f"{run} was exported already: a run has one population")
    if (pilot is None) != (seed is None):
        raise WcRunError("--pilot and --seed go together")
    if limit is not None and (pilot is not None or limit < 1):
        raise WcRunError("--limit is a chunk of at least one site, never beside --pilot")
    rows = read_jsonl(run / ROWS_FILE)
    excluded = _ids(exclude) if exclude is not None else set()
    earlier: set[str] = set()
    for other in after:
        earlier |= set(read_sites(other))
    asked, listed = population(rows, excluded=excluded, earlier=earlier)
    drawn = asked
    if pilot is not None and seed is not None:
        if not 1 <= pilot <= len(asked):
            raise WcRunError(f"a pilot of {pilot} from a population of {len(asked)}")
        chosen = set(
            audit4.draw_sample([e["site_id"] for e in asked], seed=seed, count=pilot, exclude=set())
        )
        drawn = [entry for entry in asked if entry["site_id"] in chosen]
    if limit is not None:
        drawn = asked[:limit]
    if not drawn:
        raise WcRunError(f"{run}: nothing to ask - the population is empty")
    _write_jsonl(run / SITES_FILE, drawn)
    counts = Counter(entry["marking"] for entry in asked)
    record = {
        "read": json.loads((run / READ_FILE).read_text(encoding="utf-8")),
        "rows_sha256": _sha256(run / ROWS_FILE),
        "population": len(asked),
        "by_marking": dict(sorted(counts.items())),
        "sentences": sum(len(entry["sentences"]) for entry in asked),
        "listed": {reason: sorted(ids) for reason, ids in sorted(listed.items())},
        "listed_counts": {reason: len(ids) for reason, ids in sorted(listed.items())},
        "exclude": None
        if exclude is None
        else {"path": _shown(exclude), "sha256": _sha256(exclude)},
        "after": [_shown(other) for other in after],
        "pilot": None if pilot is None else {"sites": pilot, "seed": seed},
        "limit": limit,
        "asked": len(drawn),
    }
    _write_json(run / POPULATION_FILE, record)
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
    """The instruction of the Opus agent that answers one batch of one round."""
    record = round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise WcRunError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return P.CHECK_BRIEF.format(
        batch=batch_id,
        round=record["round"],
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        python=Path(sys.executable).as_posix(),
        repo=REPO.as_posix(),
        stage=STAGE,
        batch_agent=f"opus-check-r{record['round']}-{batch_id}",
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
        Q.collect(wanted, pages, own, now=_now, pace=pace, errors=A.FETCH_ERRORS, **extra)
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
    try:
        parsed = A.parse_check(
            text, site_id=label, sentences=entry["sentences"], asked=_asked(record, label)
        )
    except A.AnswerError as exc:
        return False, f"NOT IN SHAPE: {exc}"
    if not fetch_pages:
        return True, "in shape (no page fetched)"
    pages = _agent_pages(handoff, batch_id)
    fetch([q.url for a in parsed for q in a.quotes], pages, client=client, pace=pace)
    judged = judge_sentences(
        parsed, Q.Library(REPO, pages), label=label, checked=entry["plan_site"]["description"]
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
    """One round: validated, every prompt rebuilt, every answer parsed and its quotes checked."""
    record = round_of(run, handoff)
    number = record["round"]
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
    parsed: dict[str, tuple[dict[str, Any], tuple[A.SentenceAnswer, ...] | None]] = {}
    urls: set[str] = set()
    for (batch_id, label), line in sorted(manifest.items()):
        entry = sites[label]
        failures = record["failures"].get(label, {})
        prompt = check_prompt(entry, _asked(record, label), failures)
        if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
            raise WcRunError(f"{batch_id}/{label}: the exported prompt is not this question's")
        answer = OH.read_answer(handoff, batch_id=batch_id, stage=STAGE, label=label, prompt=prompt)
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
        try:
            answers = A.parse_check(
                answer.text,
                site_id=label,
                sentences=entry["sentences"],
                asked=_asked(record, label),
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
                answers, library, label=label, checked=entry["plan_site"]["description"]
            )
        failed = {str(n): [str(r["why"])] for n, r in results.items() if not r["counted"]}
        if failed:
            reask[label] = failed
        rows.append(
            {**attempt, "results": {str(n): result for n, result in sorted(results.items())}}
        )
    out = _round_dir(run, number)
    _write_jsonl(out / "ANSWERS.jsonl", rows)
    _write_json(out / "REASK.json", reask)
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
            for n, result in row["results"].items():
                results.setdefault(label, {})[int(n)] = {**result, "round": record["round"]}
    return results, attempts


def outcome_of(
    entry: Mapping[str, Any],
    results: Mapping[int, Mapping[str, Any]],
    attempts: Sequence[Mapping[str, Any]],
    *,
    run_name: str,
) -> tuple[wc4.WcOutcome, list[wc4.Decision]]:
    """One site's outcome: its decisions, the composed text, the record, the raw_data, the
    journal evidence."""
    site = M.PlanSite.from_dict(entry["plan_site"])
    decisions, verified = _decisions(entry, results)
    composed = wc4.compose(decisions, verified)
    check = (
        None
        if composed.description is None
        else wc4.check_record(
            decisions, composed, verified, run=run_name, checked=str(site.description)
        )
    )
    raw = wc4.written_raw_data(site, composed, check)
    sentences = []
    for decision in decisions:
        result = results.get(decision.n)
        answer = result["answer"] if result else None
        sentences.append(
            {
                "n": decision.n,
                "sentence": decision.sentence,
                "verdict": decision.verdict.value,
                "remove": decision.remove,
                "reason": None if decision.reason is None else decision.reason.value,
                "answered": None if answer is None else answer["verdict"],
                "note": None if answer is None else answer["note"],
                "round": None if result is None else result["round"],
                "quotes": [] if result is None else list(result["quotes"]),
            }
        )
    evidence = {
        "group": "WC",
        "decision": wc4.EVIDENCE_DECISION,
        "run": run_name,
        "checker": M.AI_SYSTEM,
        "checked": site.description,
        "marking": wc4.marking_record(site),
        "description": composed.description,
        "kept": sum(d.kept for d in decisions),
        "of": len(decisions),
        "sentences": sentences,
        "answers": list(attempts),
    }
    return (
        wc4.WcOutcome(
            site_id=site.site_id,
            description=composed.description,
            raw_data=raw,
            evidence=evidence,
        ),
        decisions,
    )


def cmd_build(run: Path, *, first_batch: int, batch_size: int = wc4.BATCH_SIZE) -> dict[str, Any]:
    """Every site's outcome (`FINAL.jsonl`), the counts (`SUMMARY.json`) and the gate plan."""
    if first_batch < wc4.FIRST_BATCH:
        raise WcRunError(f"--first-batch {first_batch}: the WC block starts at {wc4.FIRST_BATCH}")
    results, attempts = _results(run)
    sites = read_jsonl(run / SITES_FILE)
    finals: list[dict[str, Any]] = []
    outcomes: list[wc4.WcOutcome] = []
    reasons: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    for entry in sites:
        label = entry["site_id"]
        if label not in results:
            raise WcRunError(f"{label} was never answered")
        outcome, decisions = outcome_of(entry, results[label], attempts[label], run_name=run.name)
        problems = wc4.wc_problems(outcome.description, outcome.raw_data) + wc4.evidence_problems(
            outcome.evidence, outcome.description, outcome.raw_data
        )
        if problems:
            raise WcRunError(f"{label}: the outcome breaks the lane's invariants: {problems}")
        outcomes.append(outcome)
        verdicts.update(d.verdict.value for d in decisions)
        reasons.update(d.reason.value for d in decisions if d.reason is not None)
        finals.append(
            {
                "site_id": label,
                "name": entry["name"],
                "marking": entry["marking"],
                "kept": sum(d.kept for d in decisions),
                "of": len(decisions),
                "cleared": outcome.description is None,
                "description": outcome.description,
                "decisions": [{**dataclasses.asdict(d), "text": d.text} for d in decisions],
                "evidence": outcome.evidence,
            }
        )
    _write_jsonl(run / FINAL_FILE, finals)
    by_site = {entry["site_id"]: entry for entry in sites}
    records = []
    for start in range(0, len(outcomes), batch_size):
        chunk = outcomes[start : start + batch_size]
        ordinal = first_batch + start // batch_size
        records.append(
            {
                "batch_id": f"p4-{ordinal:04d}",
                "ordinal": ordinal,
                "pass": wc4.PLAN_MARK,
                "sites": [by_site[o.site_id]["plan_site"] for o in chunk],
                "outcomes": [o.to_dict() for o in chunk],
            }
        )
    _write_jsonl(run / PLAN_FILE, records)
    summary = {
        "sites": len(finals),
        "cleared": sum(f["cleared"] for f in finals),
        "kept_whole": sum(f["kept"] == f["of"] for f in finals),
        "sentences": sum(f["of"] for f in finals),
        "sentences_kept": sum(f["kept"] for f in finals),
        "verdicts": dict(sorted(verdicts.items())),
        "drop_reasons": dict(sorted(reasons.items())),
        "plan": {
            "path": _shown(run / PLAN_FILE),
            "sha256": _sha256(run / PLAN_FILE),
            "batches": len(records),
            "first": records[0]["batch_id"] if records else None,
            "last": records[-1]["batch_id"] if records else None,
        },
    }
    _write_json(run / SUMMARY_FILE, summary)
    return summary


# ------------------------------------------------------------------------------------ the judge
def _judge_view(final: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """A final site's kept sentences (the published text, with the verified quotes its markers
    cite) and its dropped sentences, in order."""
    kept, dropped = [], []
    for entry in final["evidence"]["sentences"]:
        decision = next(d for d in final["decisions"] if d["n"] == entry["n"])
        if decision["text"] is None:
            dropped.append(entry["sentence"])
        else:
            quotes = [q for q in entry["quotes"] if q["verified"]]
            trimmed = entry["sentence"] if decision["text"] != entry["sentence"] else None
            kept.append({"text": decision["text"], "quotes": quotes, "trimmed_from": trimmed})
    return kept, dropped


def judge_prompt(final: Mapping[str, Any], site: M.PlanSite) -> str:
    kept, dropped = _judge_view(final)
    kept_lines = []
    for k, item in enumerate(kept, start=1):
        kept_lines.append(f"K{k}: {item['text']}")
        if item["trimmed_from"] is not None:
            kept_lines.append(f'    trimmed from: "{item["trimmed_from"]}"')
        kept_lines.extend(f'    quote: "{q["quote"]}" - {q["url"]}' for q in item["quotes"])
    return P.JUDGE_QUESTION.format(
        site=site_block(site),
        kept="\n".join(kept_lines) if kept_lines else "(none - the description is cleared)",
        dropped="\n".join(f"D{d}: {text}" for d, text in enumerate(dropped, start=1)) or "(none)",
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


def cmd_judge_export(run: Path, handoff: Path, *, batch_size: int) -> dict[str, Any]:
    """The pilot's measurement: one judge question per built site."""
    if (run / JUDGE_DIR / "ROUND.json").exists():
        raise WcRunError(f"{run}: the judge round was exported")
    finals = _finals(run)
    sites = read_sites(run)
    batches: dict[str, list[str]] = {}
    labels = sorted(finals)
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
                prompt=judge_prompt(finals[label], site),
            )
            batches.setdefault(batch_id, []).append(label)
    _write_json(
        run / JUDGE_DIR / "ROUND.json",
        {"handoff": _shown(handoff), "exported_at": _now(), "batches": batches},
    )
    return {"questions": len(labels), "batches": len(batches)}


def judge_brief(run: Path, handoff: Path, batch_id: str) -> str:
    record = _judge_round(run, handoff)
    if batch_id not in record["batches"]:
        raise WcRunError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return P.JUDGE_BRIEF.format(
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        python=Path(sys.executable).as_posix(),
        repo=REPO.as_posix(),
        stage=JUDGE_STAGE,
        batch_agent=f"opus-wc-judge-{batch_id}",
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
    """The judge's answers: validated, parsed, quote-checked; the measurement and its verdict."""
    record = _judge_round(run, handoff)
    check = OH.validate(handoff)
    if not check.ok:
        raise WcRunError(f"{handoff}: the judge round does not validate: {check.to_dict()}")
    finals = _finals(run)
    sites = read_sites(run)
    checkers = {
        label: {attempt["answered_by"] for attempt in final["evidence"]["answers"]}
        for label, final in finals.items()
    }
    judged: list[dict[str, Any]] = []
    for line in OH.manifest(handoff):
        batch_id, label = line["batch_id"], line["label"]
        site = M.PlanSite.from_dict(sites[label]["plan_site"])
        prompt = judge_prompt(finals[label], site)
        answer = OH.read_answer(
            handoff, batch_id=batch_id, stage=JUDGE_STAGE, label=label, prompt=prompt
        )
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
                "independent": answer.answered_by not in checkers[label],
                "coherent": parsed.coherent,
                "note": parsed.note,
                "items": rows,
            }
        )
    if {row["site_id"] for row in judged} != {
        label for labels in record["batches"].values() for label in labels
    }:
        raise WcRunError(f"{handoff}: the manifest is not the judge round's record")
    _write_jsonl(run / JUDGE_DIR / "JUDGED.jsonl", judged)
    result = judge_result(judged)
    _write_json(run / JUDGE_DIR / "RESULT.json", result)
    return result


def judge_result(judged: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The pilot's measurement and its verdict against `J_THRESHOLDS`. A judge who answered a
    check question of the site is not independent: such a site does not count, and the pilot
    cannot pass while one does not."""
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
        failures.append(f"{len(judged) - len(counted)} site(s) judged by one of their checkers")
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
    passed (`judge/RESULT.json`, `passed: true`): a failed pilot's outcomes are never written, and
    no chunk is written before a passed pilot. Returns each pilot run with its result's sha256."""
    if not plans:
        raise WcRunError("no WC plan named")
    approvals: list[dict[str, str]] = []
    for index, plan in enumerate(plans):
        run = plan.parent
        pilot = json.loads((run / POPULATION_FILE).read_text(encoding="utf-8"))["pilot"]
        if index == 0 and pilot is None:
            raise WcRunError(
                f"{plan}: the first WC plan named is the pilot's (export --pilot), whose judge "
                "passed - this run is not a pilot"
            )
        if pilot is None:
            continue
        path = run / JUDGE_DIR / "RESULT.json"
        if not path.exists():
            raise WcRunError(f"{run}: the pilot was not judged (judge-import writes {path.name})")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["passed"] is not True:
            raise WcRunError(
                f"{run}: the pilot's judge did not pass ({result['failures']}): its outcomes are "
                "never written - fix the cause and run a new pilot"
            )
        approvals.append({"run": _shown(run), "result_sha256": _sha256(path)})
    return approvals


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
        ("build", "the outcomes, the summary and the gate plan"),
        ("judge-export", "the pilot's independent judge questions"),
        ("judge-brief", "the instruction of one judge batch's Opus agent"),
        ("judge-check-answer", "one judge answer's shape"),
        ("judge-import", "the judge's answers, the measurement and its verdict"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("--run-dir", required=True, type=Path)
        if name not in ("read", "build"):
            command.add_argument("--handoff", required=True, type=Path)
        if name in ("brief", "check-answer", "judge-brief", "judge-check-answer"):
            command.add_argument("--batch-id", required=True)
        if name in ("check-answer", "judge-check-answer"):
            command.add_argument("--label", required=True)
            command.add_argument("--text-file", required=True, type=Path)
        if name in ("export", "export-reask", "judge-export"):
            command.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        if name == "read":
            command.add_argument("--host", default=W.SSH_HOST)
        if name == "export":
            command.add_argument("--exclude", type=Path, default=None)
            command.add_argument("--after", type=Path, action="append", default=[])
            command.add_argument("--pilot", type=int, default=None)
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--seed", type=int, default=None)
        if name == "check-answer":
            command.add_argument("--no-fetch", action="store_true")
        if name == "build":
            command.add_argument("--first-batch", type=int, required=True)
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
    elif command == "build":
        _print(cmd_build(run, first_batch=args.first_batch))
    elif command == "judge-export":
        _print(cmd_judge_export(run, args.handoff, batch_size=args.batch_size))
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
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    W.utf8_streams()
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    tag = "JUDGE" if args.command == "judge-import" else "WC"
    try:
        code = run_command(args)
    except (WcRunError, OH.HandoffError, wc4.WcError, Q.AuditError, A.AnswerError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        code = 1
    print(f"{tag}_EXIT={code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
