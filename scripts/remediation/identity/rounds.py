"""Rounds of identity questions: export, brief, shape check and import, for every stage of the
identity package (final repair 2026-10-08: D13 modern-town records, D20 scope window, D23 names).

Every model judgement goes through `opus_handoff.py` (owner, 2026-09-23; D6, 2026-10-08: Claude
only, one role per stage). A **stage** (`StageSpec`) is one kind of question with the role that
answers it: the web verifier (Sonnet) researches and proposes, the adversarial reviewer (Opus)
re-checks what would be written. This module is the engine L5's `handoff.py` is for links, with the
stage's own parts injected:

    render   the exact prompt of a question (a pure function of its stored context and, for a
             re-ask, why the earlier answer was held), so the import rebuilds it and refuses an
             answer to any other prompt;
    parse    the exact answer shape and the rules the answer itself can break (nothing fetched);
    decide   the machine checks that need the pages (quotes found, titles resolved, items placed);
    cited    the URLs the checks read, fetched once each;
    titles   the English Wikipedia titles the checks resolve.

**A round** is one export into its own handoff directory (an exported question is never replaced):
round `r1` asks every site of the stage's population; a re-ask round `r<n>` asks the sites whose
latest answer was held, each prompt carrying why. The rounds are recorded in `ROUNDS.jsonl`, the
stored contexts in `contexts/<round>.jsonl`; a round is imported once `answers/<round>.jsonl`
exists. Only the newest round is imported, and there are at most `MAX_ROUNDS` rounds: round 1 and
two re-asks.

**The import** refuses, with nothing written, an answer that is not the stage's role's: the
`answered_by` carries `<role>:<agent>` (`opus_handoff.py answer --role`), and the stamp must be the
role's registered model's (`roles.answer_problem`). It writes `answers/<round>.jsonl` (every answer as
decided or held), merges `DECISIONS.jsonl` (per site, the decision of its latest imported round),
`TITLES.json` and `PAGES.jsonl`; the page bytes stay under `pages/`, not versioned.

**Calibration first.** `require_calibration` refuses a role whose calibration (`calibrate_claude.py`)
has no passed verdict, or whose verdict was reached under another registry entry: a role that has
not passed is not a role to write from (D6).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from l5 import web  # noqa: E402 - the project's User-Agent and the title resolution
from opus_audit import quotes as Q  # noqa: E402

from identity import common  # noqa: E402

ROUNDS_FILE = "ROUNDS.jsonl"
DECISIONS_FILE = "DECISIONS.jsonl"
TITLES_FILE = "TITLES.json"
PAGES_FILE = "PAGES.jsonl"
PAGES_DIR = "pages"
ANSWERS_DIR = "answers"
CONTEXTS_DIR = "contexts"
#: Round 1 and at most two re-asks; what is held after them stays held.
MAX_ROUNDS = 3
DECIDED, HELD = "decided", "held"
VERDICTS_DIR = "verdicts"
THRESHOLDS_FILE = "THRESHOLDS.json"


class RoundError(ValueError):
    """A round that cannot be exported or imported as asked. Nothing was written."""


class AnswerError(ValueError):
    """The answer is not in its exact shape, or breaks a rule it can break on its own."""


@dataclass(frozen=True)
class Question:
    """One question: the site it is about and the JSON-able context its prompt is a function of."""

    site_id: str
    context: Mapping[str, Any]


@dataclass(frozen=True)
class Outcome:
    """What the machine checks made of one parsed answer: `decided` or `held` (with why), and the
    stage's own record of the answer (`data`: verdicts, cells, quote outcomes, facts)."""

    status: str
    reason: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class Env:
    """What a stage's `decide` reads: the quote library over the fetched pages and the resolved
    English Wikipedia titles."""

    library: Q.Library
    titles: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class StageSpec:
    """One kind of question and its parts (see the module docstring)."""

    lane: str
    stage: str
    role: str
    render: Callable[[Mapping[str, Any], str | None], str]
    parse: Callable[[str, Mapping[str, Any]], Any]
    decide: Callable[[Any, Mapping[str, Any], Env], Outcome]
    cited: Callable[[Any, Mapping[str, Any]], set[str]]
    titles: Callable[[Any, Mapping[str, Any]], set[str]]
    per_batch: int = 5
    guidance: str = ""

    @property
    def model(self) -> str:
        """The model id the role is registered to: what `answer --model` must say."""
        return RO.role(self.role).model


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def stage_dir(run: Path, spec: StageSpec) -> Path:
    """Where a stage keeps its rounds, contexts, answers and decisions."""
    return run / spec.lane / spec.stage


# ------------------------------------------------------------------------------------ the files
def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    common.write_jsonl(path, records)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return common.read_jsonl(path) if path.exists() else []


def _write_once(path: Path, text: str) -> None:
    if path.exists():
        raise RoundError(f"{path} exists: a round file is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------ the rounds
@dataclass(frozen=True)
class Round:
    name: str
    handoff: str
    exported_at: str
    batches: dict[str, list[str]]
    #: site id -> why its answer of the round before was held (re-ask rounds only)
    earlier: dict[str, str]

    @property
    def sites(self) -> list[str]:
        return [sid for batch in self.batches.values() for sid in batch]


def _round_of(record: Mapping[str, Any]) -> Round:
    """A round from its record. A calibration run's record (`mcode_driver.register_calibration_run`)
    numbers its round (`round: 1`) instead of naming it and carries the copy's own keys."""
    return Round(
        name=record["name"] if "name" in record else f"r{record['round']}",
        handoff=record["handoff"],
        exported_at=record["exported_at"],
        batches=record["batches"],
        earlier=record["earlier"] if "earlier" in record else {},
    )


def load_rounds(out: Path) -> list[Round]:
    return [_round_of(r) for r in _read_jsonl(out / ROUNDS_FILE)]


def find_round(out: Path, name: str) -> Round:
    for r in load_rounds(out):
        if r.name == name:
            return r
    raise RoundError(f"no round {name!r} in {out / ROUNDS_FILE}")


def imported(out: Path, name: str) -> bool:
    return (out / ANSWERS_DIR / f"{name}.jsonl").exists()


def load_decisions(out: Path) -> list[dict[str, Any]]:
    return _read_jsonl(out / DECISIONS_FILE)


def decisions_by_site(out: Path) -> dict[str, dict[str, Any]]:
    return {d["site_id"]: d for d in load_decisions(out)}


def load_contexts(out: Path) -> dict[str, Mapping[str, Any]]:
    """The context of every site ever asked: the stored contexts of the rounds in order, a later
    round's (a re-ask's) over an earlier one's."""
    merged: dict[str, Mapping[str, Any]] = {}
    for record in load_rounds(out):
        merged.update(_contexts(out, record.name))
    return merged


def agreement(first: Path, second: Path) -> dict[str, Any]:
    """The verdicts of two imports of the same questions side by side - a pilot answered by the
    stage's role and again by the pilot judge (`--as-role pilot_judge`, a stage directory of its own)."""
    a, b = decisions_by_site(first), decisions_by_site(second)
    shared = sorted(set(a) & set(b))
    pairs = [(sid, a[sid]["data"].get("verdict"), b[sid]["data"].get("verdict")) for sid in shared]
    return {
        "shared": len(shared),
        "agree": sum(1 for _, x, y in pairs if x == y),
        "disagree": [{"site_id": sid, "first": x, "second": y} for sid, x, y in pairs if x != y],
        "only_first": sorted(set(a) - set(b)),
        "only_second": sorted(set(b) - set(a)),
    }


def latest_imported(out: Path, doing: str) -> list[Round]:
    """The rounds, only if the newest one is imported: `doing` would otherwise read decisions older
    than the answers already exported, and those answers could never be written."""
    rounds = load_rounds(out)
    if not rounds:
        raise RoundError(f"no round is exported yet - {doing} reads the imported answers")
    if not imported(out, rounds[-1].name):
        raise RoundError(
            f"round {rounds[-1].name} is exported but not imported - import it before {doing}"
        )
    return rounds


def held_sites(out: Path) -> dict[str, str]:
    """The sites whose latest decision is held, with the reason a re-ask shows."""
    return {d["site_id"]: d["reason"] for d in load_decisions(out) if d["status"] == HELD}


def reask_sites(out: Path) -> dict[str, str]:
    """The held sites a new round asks, with their reasons - once the newest round is imported, and
    only while fewer than `MAX_ROUNDS` rounds are out."""
    rounds = latest_imported(out, "a re-ask")
    if len(rounds) >= MAX_ROUNDS:
        raise RoundError(
            f"{len(rounds)} rounds are out: a held site is asked at most twice more - what stays "
            "held goes to the owner list"
        )
    return held_sites(out)


def batches(site_ids: Sequence[str], round_name: str, per_batch: int) -> dict[str, list[str]]:
    """`<round>-bNN -> site ids`, in site order, at most `per_batch` each."""
    if per_batch < 1:
        raise RoundError("a batch holds at least one question")
    ordered = sorted(site_ids)
    return {
        f"{round_name}-b{i // per_batch + 1:02d}": ordered[i : i + per_batch]
        for i in range(0, len(ordered), per_batch)
    }


def _contexts(out: Path, round_name: str) -> dict[str, Mapping[str, Any]]:
    path = out / CONTEXTS_DIR / f"{round_name}.jsonl"
    if not path.exists():
        raise RoundError(f"{path} does not exist - the round's contexts were never stored")
    return {r["site_id"]: r["context"] for r in common.read_jsonl(path)}


def export_round(
    out: Path,
    spec: StageSpec,
    handoff: Path,
    questions: Sequence[Question],
    *,
    earlier: Mapping[str, str] | None = None,
    now: Callable[[], str] = now_utc,
) -> Round:
    """Export one round of questions into a new handoff directory and record it. Round 1 asks the
    questions it is given; a later round asks only the held sites of the round before (`earlier`)."""
    earlier = dict(earlier or {})
    if not questions:
        raise RoundError("no question to ask - nothing to export")
    ids = [q.site_id for q in questions]
    if len(set(ids)) != len(ids):
        raise RoundError("a site is asked twice in one round")
    if handoff.exists() and any(handoff.iterdir()):
        raise RoundError(f"{handoff} is not empty: a round is exported into a new directory")
    known = load_rounds(out)
    number = len(known) + 1
    if number == 1 and earlier:
        raise RoundError("round 1 re-asks nothing")
    if number > 1:
        if number > MAX_ROUNDS:
            raise RoundError(f"{len(known)} rounds are out: at most {MAX_ROUNDS}")
        latest_imported(out, "a re-ask")
        if set(earlier) != set(ids) or not set(ids) <= set(held_sites(out)):
            raise RoundError("a re-ask round asks exactly the held sites, each with its reason")
    name = f"r{number}"
    grouped = batches(ids, name, spec.per_batch)
    by_id = {q.site_id: q for q in questions}
    handoff.mkdir(parents=True, exist_ok=True)
    for batch_id, sids in grouped.items():
        for sid in sids:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=spec.stage,
                label=sid,
                field=None,
                prompt=spec.render(by_id[sid].context, earlier.get(sid)),
            )
    _write_once(
        out / CONTEXTS_DIR / f"{name}.jsonl",
        "".join(
            json.dumps(
                {"site_id": q.site_id, "context": q.context}, ensure_ascii=False, sort_keys=True
            )
            + "\n"
            for q in sorted(questions, key=lambda q: q.site_id)
        ),
    )
    record = Round(name, handoff.as_posix(), now(), grouped, earlier)
    with (out / ROUNDS_FILE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return record


# ------------------------------------------------------------------------------ the agent's aids
BRIEF = """You are agent {batch} of the identity pass of the Ancient Nerds final repair (lane \
{lane}, stage {stage}, round {round}), running as the role {role}. You answer {count} question(s), \
each about another curated site of the map. Answer each one on its own.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no other file of \
the repository, no database, no git history - except the cached Wikipedia pages a prompt names: \
read the site's Wikipedia text from that cache first, and fetch other sources live (a few requests \
at most; a 403 or 429 is a refusal of the server, never a finding - test it yourself with curl \
before you write that a page cannot be read). The machine fetches every URL you cite with a plain \
HTTP GET and looks for your quote in what it serves (for an HTML page: its visible text; for \
Special:EntityData/<QID>.json: the JSON's strings) - quote verbatim, cite the page you quote, never \
a search result page. Keep each quote short (one clause, about 5 to 25 words) and never let it run \
across a footnote marker such as [1], a table cell or a list item.
{guidance}
For each question:
1. Read {handoff}/<prompt_path>.
2. Research and decide, exactly as the prompt's rules say.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   {python} {run} --lane {lane} check-answer --stage {stage} --stage-dir {stage_dir} \
--round {round} --batch-id {batch} \
--label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once, under your role:
   {python} {handoff_tool} answer --dir {handoff} --batch-id {batch} --stage {stage} \
--label <label> --answered-by {batch} --role {role} --model {model} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(out: Path, spec: StageSpec, round_name: str, batch_id: str) -> str:
    """The instruction of the agent that answers one batch of one round."""
    record = find_round(out, round_name)
    if batch_id not in record.batches:
        raise RoundError(f"{batch_id} is no batch of round {round_name}")
    return BRIEF.format(
        batch=batch_id,
        lane=spec.lane,
        stage=spec.stage,
        round=round_name,
        role=spec.role,
        model=spec.model,
        count=len(record.batches[batch_id]),
        handoff=record.handoff,
        scratch=f"{record.handoff}-scratch/{batch_id}",
        guidance=("\n" + spec.guidance + "\n") if spec.guidance else "",
        stage_dir=out.resolve().as_posix(),
        python="./.venv/Scripts/python.exe",
        run="scripts/remediation/identity/run.py",
        handoff_tool="scripts/remediation/opus_handoff.py",
    )


def check_answer(
    out: Path, spec: StageSpec, round_name: str, batch_id: str, label: str, text: str
) -> str | None:
    """The shape problem of an answer text, or None - no page is fetched, no verdict judged."""
    record = find_round(out, round_name)
    if label not in record.batches.get(batch_id, []):
        raise RoundError(f"{batch_id}/{label} is no question of round {round_name}")
    context = _contexts(out, round_name)[label]
    try:
        spec.parse(text, context)
    except AnswerError as exc:
        return str(exc)
    return None


# ------------------------------------------------------------------------------ the calibration
def require_calibration(root: Path, calibration_id: str, role: str) -> dict[str, Any]:
    """The passed verdict of `calibration_id` for `role`, or `RoundError`.

    The verdict must exist and have passed, name this role and the model the registry holds for it
    now, and its seal must have been made under the role's current registry entry
    (`roles.role_sha256`): a role moved up a tier after a failed calibration is calibrated again."""
    verdict_path = root / VERDICTS_DIR / f"{calibration_id}.json"
    if not verdict_path.exists():
        raise RoundError(
            f"calibration {calibration_id} has no verdict at {verdict_path}: seal it, re-answer "
            f"the pool as role {role}, compare, and take the verdict first (calibrate_claude.py)"
        )
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    if not verdict["passed"]:
        raise RoundError(f"calibration {calibration_id} did not pass: {verdict.get('tier_move')}")
    if verdict["role"] != role:
        raise RoundError(
            f"calibration {calibration_id} measured role {verdict['role']}, not {role}"
        )
    registered = RO.role(role)
    if verdict["model"] != registered.model:
        raise RoundError(
            f"calibration {calibration_id} measured {verdict['model']}, the registry holds "
            f"{registered.model} for {role} now: calibrate again"
        )
    thresholds = root / THRESHOLDS_FILE
    seals = json.loads(thresholds.read_text(encoding="utf-8")) if thresholds.exists() else {}
    seal = seals.get(calibration_id)
    if seal is None or seal["role_sha256"] != RO.role_sha256(role):
        raise RoundError(
            f"calibration {calibration_id} was sealed under another registry entry of {role}: "
            "calibrate again"
        )
    return verdict


# ------------------------------------------------------------------------------------ the import
def load_titles(out: Path) -> dict[str, dict[str, Any]]:
    path = out / TITLES_FILE
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8"))["titles"])


def _role_problems(spec: StageSpec, answers: Mapping[str, OH.Answer]) -> list[str]:
    problems = []
    for sid, answer in sorted(answers.items()):
        named = RO.role_of(answer.answered_by)
        if named != spec.role:
            problems.append(
                f"{sid}: recorded under {named or 'no role'} ({answer.answered_by!r}), the stage "
                f"asks role {spec.role}"
            )
            continue
        why = RO.answer_problem(answer.answered_by, answer.model)
        if why is not None:
            problems.append(f"{sid}: {why}")
    return problems


def import_round(
    out: Path,
    spec: StageSpec,
    round_name: str,
    *,
    http: Callable[[], httpx.Client] = web.client,
    resolver: Callable[[list[str], httpx.Client], dict[str, dict[str, Any]]] = web.resolve_titles,
    now: Callable[[], str] = now_utc,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Parse, fetch, resolve and decide every answer of one round; merge the decisions."""
    record = find_round(out, round_name)
    newest = load_rounds(out)[-1].name
    if record.name != newest:
        raise RoundError(
            f"round {round_name} is not the newest ({newest}): its answers would overwrite the "
            "newer round's decisions"
        )
    if imported(out, round_name):
        raise RoundError(f"round {round_name} is imported already")
    root = Path(record.handoff)
    check = OH.validate(root)
    if not check.ok:
        raise RoundError(
            f"{root} does not validate ({len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed, {len(check.orphans)} orphan(s)) - run "
            "`opus_handoff.py validate` and have the questions answered first"
        )
    contexts = _contexts(out, round_name)
    raw: dict[str, OH.Answer] = {}
    for batch_id, sids in record.batches.items():
        for sid in sids:
            raw[sid] = OH.read_answer(
                root,
                batch_id=batch_id,
                stage=spec.stage,
                label=sid,
                prompt=spec.render(contexts[sid], record.earlier.get(sid)),
            )
    problems = _role_problems(spec, raw)
    if problems:
        raise RoundError(
            f"{len(problems)} answer(s) are not the stage's role's - delete them from {root} and "
            f"have them answered again: " + "; ".join(problems[:5])
        )

    parsed: dict[str, Any] = {}
    held: dict[str, Outcome] = {}
    for sid, answer in raw.items():
        try:
            parsed[sid] = spec.parse(answer.text, contexts[sid])
        except AnswerError as exc:
            held[sid] = Outcome(HELD, f"shape: {exc}", {})

    pages = out / PAGES_DIR
    urls = sorted({u for sid, p in parsed.items() for u in spec.cited(p, contexts[sid])})
    titles = load_titles(out)
    wanted = sorted(
        {t for sid, p in parsed.items() for t in spec.titles(p, contexts[sid])} - set(titles)
    )
    with http() as client:
        fetched = Q.collect(urls, pages, client, now=now, pace=pace)
        resolved_at = now()
        if wanted:
            titles.update(
                {t: {**r, "resolved_at": resolved_at} for t, r in resolver(wanted, client).items()}
            )
    missing = [t for t in wanted if t not in titles]
    if missing:
        raise RoundError(f"{len(missing)} title(s) came back unresolved: {missing[:3]}")

    env = Env(Q.Library(common.REPO, pages), titles)
    outcomes: dict[str, Outcome] = dict(held)
    for sid, p in parsed.items():
        outcomes[sid] = spec.decide(p, contexts[sid], env)
    records = [
        {
            "site_id": sid,
            "status": o.status,
            "reason": o.reason,
            "round": round_name,
            "answered_by": raw[sid].answered_by,
            "model": raw[sid].model,
            "answered_at": raw[sid].answered_at,
            "data": dict(o.data),
        }
        for sid, o in sorted(outcomes.items())
    ]
    write_jsonl(out / ANSWERS_DIR / f"{round_name}.jsonl", records)
    merged = {d["site_id"]: d for d in load_decisions(out)}
    merged.update({r["site_id"]: r for r in records})
    write_jsonl(out / DECISIONS_FILE, [merged[s] for s in sorted(merged)])
    (out / TITLES_FILE).write_text(
        json.dumps({"titles": titles}, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    known = {r["url"]: r for r in _read_jsonl(out / PAGES_FILE)}
    known.update({r["url"]: r for r in Q.page_index(urls, pages)})
    write_jsonl(out / PAGES_FILE, [known[u] for u in sorted(known)])
    statuses = Counter(r["status"] for r in records)
    return {
        "round": round_name,
        "answers": len(records),
        "decided": statuses.get(DECIDED, 0),
        "held": statuses.get(HELD, 0),
        "held_reasons": dict(
            Counter(r["reason"].split(":")[0] for r in records if r["status"] == HELD)
        ),
        "pages": fetched,
        "titles_resolved": len(wanted),
        "sites_decided_overall": sum(1 for d in merged.values() if d["status"] == DECIDED),
        "sites_held_overall": sum(1 for d in merged.values() if d["status"] == HELD),
    }
