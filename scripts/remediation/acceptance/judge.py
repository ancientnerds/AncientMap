"""Phase 6 acceptance, sections 6-9 of the sealed protocol: the judging of the drawn sites.

`output/remediation/acceptance/PROTOCOL.md`, run over a draw directory (`draw.py`'s output). No model
is called here: every judgement is an Opus agent of the orchestrating session answering through the
handoff directory (`scripts/remediation/opus_handoff.py`), one agent per batch. Production is only
read: `deterministic` (one read-only transaction and a public GET of `/api/sites/all`) and `result`
(the journal above the draw's high-water mark, read-only).

The orchestrator's sequence (run from the repository root; `J=scripts/remediation/acceptance/judge.py`,
`R=output/remediation/acceptance/draw-<date>`, `H=output/remediation/handoff/acceptance-<date>`):

    $J export-stage1 --run-dir $R --handoff $H-s1         every question of section 5, batched
    $J brief --run-dir $R --handoff $H-s1 --batch-id B     the instruction of batch B's Opus agent
        (the agent answers each question through `opus_handoff.py answer`)
    opus_handoff.py validate --dir $H-s1                   every answer in, in shape, by Opus
    $J import-stage1 --run-dir $R                          parse, fetch every cited page once,
                                                           quote-check: STAGE1.jsonl, REASK_S1.json
    $J export-reask --run-dir $R --stage s1 --handoff $H-s1-r1   (at most twice, each into a new
        directory; answer, validate, import-stage1 again)
    $J export-stage2 --run-dir $R --handoff $H-s2          every counted stage-1 WRONG
    $J import-stage2 --run-dir $R                          (re-asks as for stage 1)
    $J export-stage3 --run-dir $R --handoff $H-s3          every stage-2 UNDECIDED
    $J import-stage3 --run-dir $R
    $J deterministic --run-dir $R                          D1-D6, once: DETERMINISTIC.json
    $J result --run-dir $R                                 V1-V3, A1-A3: RESULT.json, RESULT.md

**The run's files** live in `<run>/judging/` (gitignored until the result: the questions carry the
canary values, and next to the committed SAMPLE.jsonl they would give the key away): QUESTIONS.jsonl
(the stage-1 questions, nothing marking a canary), ROUNDS.jsonl (every exported round, its directory
and batches), STAGE<n>.jsonl (every attempt of every question: the answer as written, its parse, each
quote's outcome, whether it counted, and the question's final verdict), REASK_S<n>.json, PAGES.jsonl
and `pages/` (each cited URL fetched once, the raw bytes and their sha256 - `opus_audit/quotes.py`).

**What counts** (sections 6-7): a verdict in its stage's exact shape (`answers.py`) whose every quote
is found, given by a judge who answered no other question of the site in any stage or round (the
agent's name, `answered_by`). A question without a counted verdict goes to a new judge (`export-reask`)
at most twice, then stands UNVERIFIABLE (stage 1) or UNDECIDED (stages 2 and 3). Each round's
questions are the exact prompts of its stage: import regenerates every prompt and refuses one that is
not the prompt the manifest names.

**The canary key** (`CANARIES.jsonl`, pinned by DRAW.json) is read twice: by `export-stage1`, for the
values it plants, and by `result`, to score. Nothing in between knows which question is a canary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (
    ROOT,
    ROOT / "scripts" / "remediation",
    ROOT / "scripts" / "remediation" / "gallery_audit",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import persist_verdicts as pv  # noqa: E402
from mechanical.lane import sql_literal  # noqa: E402
from mechanical.plan import PlanError, parse_tagged_export  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from prod_write import send  # noqa: E402
from run_files import now as _now  # noqa: E402 - the shared clock and JSON writers
from run_files import write_json as _write_json  # noqa: E402
from run_files import write_jsonl as _write_jsonl  # noqa: E402

from acceptance import answers as A  # noqa: E402
from acceptance import checks as C  # noqa: E402
from acceptance import questions as QN  # noqa: E402
from acceptance import score as S  # noqa: E402

STAGES = ("s1", "s2", "s3")
#: Round 0 and two re-asks (section 6: "at most twice").
MAX_ROUND = 2
EXHAUSTED = {"s1": "UNVERIFIABLE", "s2": "UNDECIDED", "s3": "UNDECIDED"}
JUDGING = "judging"


class JudgeError(ValueError):
    """The step must not run on this state. Nothing was written by it."""


def _resolve(path: Path) -> Path:
    """A path as given, relative ones taken from the repository root."""
    return path if path.is_absolute() else ROOT / path


def _shown(path: Path) -> str:
    try:
        return _resolve(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_lf(path)).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _lf(path).decode("utf-8").split("\n") if line]


# ------------------------------------------------------------------------------ the draw's files
def _pinned(run: Path, name: str) -> list[dict[str, Any]]:
    """A draw file, refused unless its LF bytes are the ones DRAW.json pins."""
    draw = json.loads((run / "DRAW.json").read_text(encoding="utf-8"))
    path = run / name
    if _sha256(path) != draw["sha256"][name]:
        raise JudgeError(f"{path} is not the {name} that DRAW.json pins")
    return _read_jsonl(path)


def read_sample(run: Path) -> list[dict[str, Any]]:
    return _pinned(run, "SAMPLE.jsonl")


def read_questions(run: Path) -> dict[str, QN.Question]:
    rows = _read_jsonl(run / JUDGING / "QUESTIONS.jsonl")
    return {row["label"]: QN.Question(**row) for row in rows}


def read_rounds(run: Path) -> list[dict[str, Any]]:
    path = run / JUDGING / "ROUNDS.jsonl"
    return _read_jsonl(path) if path.exists() else []


def _round_of(run: Path, handoff: Path) -> dict[str, Any]:
    wanted = _resolve(handoff).resolve()
    for record in read_rounds(run):
        if _resolve(Path(record["handoff"])).resolve() == wanted:
            return record
    raise JudgeError(f"{handoff} is not the directory of an exported round of {run}")


# ------------------------------------------------------------------------------ the contexts
@dataclass(frozen=True)
class Context:
    """What one question of a stage is asked from."""

    question: QN.Question
    claim: QN.Claim | None = None
    first: QN.Reasoning | None = None
    second: QN.Reasoning | None = None


def _counted_answer(record: Mapping[str, Any]) -> dict[str, Any] | None:
    attempt = record["final"]["attempt"]
    return None if attempt is None else record["attempts"][attempt]["answer"]


def _claim(record: Mapping[str, Any]) -> QN.Claim:
    answer = _counted_answer(record)
    assert answer is not None  # a WRONG final is a counted one: exhausted stage 1 is UNVERIFIABLE
    disputed = dict.fromkeys(q["claim"] for q in answer["quotes"] if q["claim"])
    return QN.Claim(answer["right_value"], answer["severity"], tuple(disputed))


def _reasoning(record: Mapping[str, Any]) -> QN.Reasoning | None:
    answer = _counted_answer(record)
    if answer is None:
        return None
    quotes = tuple((q["url"], q["quote"]) for q in answer["quotes"])
    return QN.Reasoning(answer["reasoning"], quotes)


def _final_records(run: Path, stage: str) -> dict[str, dict[str, Any]]:
    """A finished stage's records: every round imported, no question waiting for a re-ask."""
    number = stage[1]
    rounds = [r["round"] for r in read_rounds(run) if r["stage"] == stage]
    reask = run / JUDGING / f"REASK_S{number}.json"
    if not rounds or not reask.exists():
        raise JudgeError(f"stage {number} is not finished: not exported or not imported")
    waiting = json.loads(reask.read_text(encoding="utf-8"))
    if waiting["after_round"] != max(rounds):
        raise JudgeError(f"stage {number} is not finished: round {max(rounds)} is not imported")
    if waiting["labels"]:
        raise JudgeError(
            f"stage {number} is not finished: {len(waiting['labels'])} question(s) wait for a "
            "re-ask"
        )
    return {row["label"]: row for row in _read_jsonl(run / JUDGING / f"STAGE{number}.jsonl")}


def _contexts(run: Path, stage: str) -> dict[str, Context]:
    questions = read_questions(run)
    if stage == "s1":
        return {label: Context(question) for label, question in questions.items()}
    first = _final_records(run, "s1")
    wrong = {label: r for label, r in first.items() if r["final"]["verdict"] == A.WRONG}
    if stage == "s2":
        return {label: Context(questions[label], _claim(r)) for label, r in wrong.items()}
    if not wrong:
        return {}
    second = _final_records(run, "s2")
    if set(second) != set(wrong):
        raise JudgeError("stage 2 did not judge exactly the stage-1 WRONGs")
    return {
        label: Context(
            questions[label], _claim(wrong[label]), _reasoning(wrong[label]), _reasoning(record)
        )  # fmt: skip
        for label, record in second.items()
        if record["final"]["verdict"] == A.UNDECIDED
    }


def _prompt(stage: str, context: Context, rows: Mapping[str, QN.Row], patterns: str) -> str:
    if stage == "s1":
        return QN.stage1_prompt(context.question, rows, patterns)
    assert context.claim is not None
    if stage == "s2":
        return QN.stage2_prompt(context.question, context.claim, rows, patterns)
    assert context.first is not None
    return QN.stage3_prompt(
        context.question, context.claim, context.first, context.second, rows, patterns
    )


def _parse(stage: str, context: Context, text: str) -> A.Answer1 | A.Answer2 | A.Answer3:
    if stage == "s1":
        return A.parse_stage1(text, context.question.field, context.question.value)
    if stage == "s2":
        assert context.claim is not None
        return A.parse_stage2(text, context.question.field, context.claim.severity)
    return A.parse_stage3(text)


# ------------------------------------------------------------------------------ export
def _export_round(
    run: Path,
    stage: str,
    number: int,
    handoff: Path,
    contexts: Mapping[str, Context],
) -> dict[str, Any]:
    """One round of one stage into a directory of its own, and its record in ROUNDS.jsonl."""
    rounds = read_rounds(run)
    if any(r["stage"] == stage and r["round"] == number for r in rounds):
        raise JudgeError(f"stage {stage[1]} round {number} is already exported")
    target = _resolve(handoff)
    if any(_resolve(Path(r["handoff"])).resolve() == target.resolve() for r in rounds):
        raise JudgeError(f"{handoff} holds another round: a round gets a directory of its own")
    if target.exists() and any(target.iterdir()):
        raise JudgeError(f"{handoff} is not empty: a round gets a directory of its own")
    rows, patterns = QN.read_protocol(), QN.read_patterns()
    groups = QN.batches([c.question for c in contexts.values()], f"{stage}r{number}")
    for batch_id, group in groups:
        for question in group:
            OH.export(
                target,
                batch_id=batch_id,
                stage=stage,
                label=question.label,
                field=question.field,
                prompt=_prompt(stage, contexts[question.label], rows, patterns),
            )
    record = {
        "stage": stage,
        "round": number,
        "handoff": handoff.as_posix(),
        "batches": {batch_id: [q.label for q in group] for batch_id, group in groups},
        "exported_at": _now(),
    }
    _write_jsonl(run / JUDGING / "ROUNDS.jsonl", [*rounds, record])
    return {
        "stage": stage,
        "round": number,
        "handoff": handoff.as_posix(),
        "questions": len(contexts),
        "batches": {batch_id: len(group) for batch_id, group in groups},
    }


def export_stage1(run: Path, handoff: Path) -> dict[str, Any]:
    """Every non-empty field of every drawn site; the canary values planted from the key."""
    questions = QN.stage1_questions(read_sample(run), _pinned(run, "CANARIES.jsonl"))
    path = run / JUDGING / "QUESTIONS.jsonl"
    rows = [asdict(q) for q in questions]
    if path.exists() and _read_jsonl(path) != rows:
        raise JudgeError(f"{path} holds other questions")
    _write_jsonl(path, rows)
    return _export_round(run, "s1", 0, handoff, _contexts(run, "s1"))


def export_reask(run: Path, stage: str, handoff: Path) -> dict[str, Any]:
    """The questions of `stage` without a counted verdict, to new judges, the exact same prompts."""
    number = stage[1]
    rounds = [r["round"] for r in read_rounds(run) if r["stage"] == stage]
    reask = run / JUDGING / f"REASK_S{number}.json"
    if not rounds:
        raise JudgeError(f"stage {number} was never exported")
    if not reask.exists() or json.loads(reask.read_text("utf-8"))["after_round"] != max(rounds):
        raise JudgeError(f"import stage {number} round {max(rounds)} before a re-ask")
    labels = json.loads(reask.read_text(encoding="utf-8"))["labels"]
    if not labels:
        raise JudgeError(f"stage {number}: nothing to ask again")
    contexts = _contexts(run, stage)
    return _export_round(run, stage, max(rounds) + 1, handoff, {l: contexts[l] for l in labels})


def _export_later(run: Path, stage: str, handoff: Path) -> dict[str, Any]:
    contexts = _contexts(run, stage)
    if not contexts:
        return {"stage": stage, "questions": 0, "note": "nothing to ask: no round is recorded"}
    return _export_round(run, stage, 0, handoff, contexts)


def export_stage2(run: Path, handoff: Path) -> dict[str, Any]:
    """Every counted stage-1 WRONG, canaries included, to a second judge (section 7)."""
    return _export_later(run, "s2", handoff)


def export_stage3(run: Path, handoff: Path) -> dict[str, Any]:
    """Every stage-2 UNDECIDED to a third judge who sees both reasonings (section 7)."""
    return _export_later(run, "s3", handoff)


# ------------------------------------------------------------------------------ import
def _earlier_judges(run: Path, stage: str) -> dict[str, set[str]]:
    """Per site, every judge of an earlier stage - they are not independent of it any more."""
    seen: dict[str, set[str]] = {}
    for earlier in STAGES[: STAGES.index(stage)]:
        path = run / JUDGING / f"STAGE{earlier[1]}.jsonl"
        for row in _read_jsonl(path) if path.exists() else []:
            for attempt in row["attempts"]:
                seen.setdefault(row["site_id"], set()).add(attempt["answered_by"])
    return seen


def _collect(urls: Sequence[str], pages: Path, client: httpx.Client | None, pace: float) -> None:
    if client is not None:
        Q.collect(urls, pages, client, now=_now, pace=pace)
        return
    with Q.http_client() as own:
        Q.collect(urls, pages, own, now=_now, pace=pace)


def _page_index(run: Path) -> None:
    urls = sorted(
        {
            quote["url"]
            for stage in STAGES
            if (run / JUDGING / f"STAGE{stage[1]}.jsonl").exists()
            for row in _read_jsonl(run / JUDGING / f"STAGE{stage[1]}.jsonl")
            for attempt in row["attempts"]
            if attempt["answer"] is not None
            for quote in attempt["answer"]["quotes"]
        }
    )
    _write_jsonl(run / JUDGING / "PAGES.jsonl", Q.page_index(urls, run / JUDGING / "pages"))


def import_stage(
    run: Path, stage: str, *, client: httpx.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """Every answer of every round of `stage`: validated, parsed, quote-checked, decided."""
    number = stage[1]
    contexts = _contexts(run, stage)
    rounds = sorted((r for r in read_rounds(run) if r["stage"] == stage), key=lambda r: r["round"])
    if not rounds:
        raise JudgeError(f"stage {number} was never exported")
    rows, patterns = QN.read_protocol(), QN.read_patterns()
    items: dict[str, list[tuple[dict[str, Any], Any]]] = {label: [] for label in contexts}
    for record in rounds:
        handoff = _resolve(Path(record["handoff"]))
        check = OH.validate(handoff)
        if not check.ok:
            raise JudgeError(
                f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
                f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - "
                "every answer is validated before anything is imported"
            )
        manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
        asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
        if set(manifest) != asked:
            raise JudgeError(f"{record['handoff']}: the manifest is not the round's record")
        for (batch_id, label), line in sorted(manifest.items()):
            if label not in contexts:
                raise JudgeError(f"{label} is no question of stage {number}")
            prompt = _prompt(stage, contexts[label], rows, patterns)
            if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
                raise JudgeError(f"{batch_id}/{label}: the exported prompt is not this question's")
            answer = OH.read_answer(handoff, batch_id=batch_id, stage=stage, label=label,
                                    prompt=prompt)  # fmt: skip
            attempt: dict[str, Any] = {
                "round": record["round"],
                "handoff": record["handoff"],
                "batch_id": batch_id,
                "answered_by": answer.answered_by,
                "answered_at": answer.answered_at,
                "prompt_sha256": line["prompt_sha256"],
                "text": answer.text,
            }
            try:
                parsed = _parse(stage, contexts[label], answer.text)
                attempt["answer"], attempt["problem"] = parsed.to_dict(), None
            except A.AnswerError as exc:
                parsed = None
                attempt["answer"], attempt["problem"] = None, str(exc)
            items[label].append((attempt, parsed))

    pages = run / JUDGING / "pages"
    urls = sorted({q.url for pairs in items.values() for _, p in pairs if p for q in p.quotes})
    _collect(urls, pages, client, pace)
    library = Q.Library(ROOT, pages)

    judges = _earlier_judges(run, stage)
    order = sorted(
        ((attempt["round"], attempt["answered_at"], label, index)
         for label, pairs in items.items() for index, (attempt, _) in enumerate(pairs)),
    )  # fmt: skip
    for _round, _at, label, index in order:
        attempt, parsed = items[label][index]
        site = contexts[label].question.site_id
        name = attempt["answered_by"]
        if name in judges.setdefault(site, set()):
            check = A.QuoteCheck(False, f"not an independent judge: {name} judged this site", ())
        elif parsed is None:
            check = A.QuoteCheck(False, f"malformed: {attempt['problem']}", ())
        else:
            check = A.check_quotes(label, parsed.quotes, library)
        judges[site].add(name)
        attempt["counted"], attempt["reason"], attempt["quotes"] = (
            check.counted,
            check.reason,
            list(check.results),
        )

    records, waiting = [], []
    for label in sorted(items):
        pairs = sorted(items[label], key=lambda pair: pair[0]["round"])
        if [attempt["round"] for attempt, _ in pairs] != list(range(len(pairs))):
            raise JudgeError(f"{label}: asked in rounds {[a['round'] for a, _ in pairs]}")
        counted = [i for i, (attempt, _) in enumerate(pairs) if attempt["counted"]]
        if counted and counted[0] != len(pairs) - 1:
            raise JudgeError(f"{label}: asked again after a counted verdict")
        if counted:
            final: dict[str, Any] | None = {
                "verdict": pairs[counted[0]][1].verdict,
                "via": "counted",
                "attempt": counted[0],
            }
        elif len(pairs) == MAX_ROUND + 1:
            final = {"verdict": EXHAUSTED[stage], "via": "exhausted", "attempt": None}
        else:
            final = None
            waiting.append(label)
        question = contexts[label].question
        records.append(
            {
                "label": label,
                "site_id": question.site_id,
                "field": question.field,
                "stage": stage,
                "attempts": [attempt for attempt, _ in pairs],
                "final": final,
            }
        )
    after = max(r["round"] for r in rounds)
    _write_jsonl(run / JUDGING / f"STAGE{number}.jsonl", records)
    _write_json(
        run / JUDGING / f"REASK_S{number}.json",
        {"stage": stage, "after_round": after, "labels": waiting},
    )
    _page_index(run)
    finals = Counter(r["final"]["verdict"] for r in records if r["final"] is not None)
    reasons = Counter(
        attempt["reason"].split(":")[0]
        for r in records
        for attempt in r["attempts"]
        if not attempt["counted"]
    )
    return {
        "stage": stage,
        "rounds": after + 1,
        "questions": len(records),
        "final": dict(sorted(finals.items())),
        "exhausted": sum(1 for r in records if r["final"] and r["final"]["via"] == "exhausted"),
        "pending": len(waiting),
        "not_counted": dict(sorted(reasons.items())),
        "urls": len(urls),
    }


# ------------------------------------------------------------------------------ the agent's aids
def check_answer(run: Path, handoff: Path, batch_id: str, label: str, text: str) -> str | None:
    """The shape problem of an answer text, or None - no page is fetched, no verdict judged."""
    record = _round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise JudgeError(f"{batch_id}/{label} is no question of {handoff}")
    try:
        _parse(record["stage"], _contexts(run, record["stage"])[label], text)
    except A.AnswerError as exc:
        return str(exc)
    return None


BRIEF = """You are Opus judge {batch} of the Phase-6 acceptance test (stage {number}). You answer \
{count} question(s), each about another site. Answer each one on its own, as if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the repository - \
no other batch, nothing else under output/ or docs/, no database, no git history. Your evidence is your \
own web research, as each prompt says.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide, exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   ./.venv/Scripts/python.exe scripts/remediation/acceptance/judge.py check-answer --run-dir {run} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    """The instruction of the Opus agent that answers one batch."""
    record = _round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise JudgeError(f"{batch_id} is no batch of {handoff}")
    shown = _shown(handoff)
    return BRIEF.format(
        batch=batch_id,
        number=record["stage"][1],
        stage=record["stage"],
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
    )


# ------------------------------------------------------------------------------ section 8
def _read_production(script: str) -> str:
    proc = send(script, rows=True, timeout=900)
    if proc.returncode != 0:
        raise JudgeError(
            f"the read-only export failed (psql exit {proc.returncode}): {proc.stderr}"
        )
    return proc.stdout


def deterministic(
    run: Path,
    *,
    read_export: Callable[[str], str] = _read_production,
    read_served: Callable[[set[str]], tuple[set[str], dict[str, Any]]] = C.served_ids,
) -> dict[str, Any]:
    """D1-D6, once: the frozen values, one read-only transaction, the public `/api/sites/all`."""
    out = run / "DETERMINISTIC.json"
    if out.exists():
        raise JudgeError(f"D1-D6 are run once: {out} exists")
    sample = read_sample(run)
    text = read_export(C.export_script(sample))
    (run / "DETERMINISTIC_EXPORT.jsonl").write_text(text, encoding="utf-8", newline="\n")
    try:
        rows, exported_at = parse_tagged_export(text, C.EXPORT_KINDS)
        sources = {str(row["source_id"]) for row in rows["retired"]}
        served, api = read_served(sources) if sources else (set(), {"note": "no retired site"})
        checks = C.evaluate(sample, rows, served)
    except (PlanError, ValueError) as exc:
        raise JudgeError(str(exc)) from exc
    result = {
        "checked_at": _now(),
        "exported_at": exported_at,
        "sample_sha256": _sha256(run / "SAMPLE.jsonl"),
        "export_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "api": api,
        **checks,
    }
    _write_json(out, result)
    return result


# ------------------------------------------------------------------------------ section 9
def _journal_after(mark: int, site_ids: list[str]) -> list[dict[str, Any]]:
    """Journal rows above the draw's high-water mark on a drawn site - read-only."""
    listed = ", ".join(f"{sql_literal(site_id)}::uuid" for site_id in site_ids)
    sql = (
        "\\set QUIET on\nBEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        "SELECT row_to_json(t) FROM (SELECT id, site_id_ref::text AS site_id_ref, run_stamp, "
        "table_name, column_name, applied_at::text AS applied_at FROM remediation_change_log "
        f"WHERE id > {int(mark)} AND site_id_ref IN ({listed}) ORDER BY id) t;\nCOMMIT;\n"
    )
    return pv.read_rows(sql)


def _finals(records: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        label: {
            "verdict": record["final"]["verdict"],
            "via": record["final"]["via"],
            "answer": _counted_answer(record),
        }
        for label, record in records.items()
    }


RESULT_FILES = (
    "DRAW.json", "SAMPLE.jsonl", "CANARIES.jsonl", "DETERMINISTIC.json",
    "DETERMINISTIC_EXPORT.jsonl", "judging/QUESTIONS.jsonl", "judging/ROUNDS.jsonl",
    "judging/STAGE1.jsonl", "judging/STAGE2.jsonl", "judging/STAGE3.jsonl",
    "judging/REASK_S1.json", "judging/REASK_S2.json", "judging/REASK_S3.json",
    "judging/PAGES.jsonl",
)  # fmt: skip


def result(
    run: Path, *, read_journal: Callable[[int, list[str]], list[dict[str, Any]]] = _journal_after
) -> dict[str, Any]:
    """Section 9 on a finished run, once: RESULT.json and RESULT.md."""
    out = run / "RESULT.json"
    if out.exists():
        raise JudgeError(f"the result is written once: {out} exists")
    if not (run / "DETERMINISTIC.json").exists():
        raise JudgeError("DETERMINISTIC.json is missing: run `deterministic` first")
    deterministic_result = json.loads((run / "DETERMINISTIC.json").read_text(encoding="utf-8"))
    questions = list(read_questions(run).values())
    first = _final_records(run, "s1")
    second = _final_records(run, "s2") if _contexts(run, "s2") else {}
    third = _final_records(run, "s3") if second and _contexts(run, "s3") else {}
    try:
        results = S.outcomes(questions, _finals(first), _finals(second), _finals(third))
        canaries = S.canary_labels(questions, _pinned(run, "CANARIES.jsonl"))
    except S.ScoreError as exc:
        raise JudgeError(str(exc)) from exc
    draw = json.loads((run / "DRAW.json").read_text(encoding="utf-8"))
    sample = read_sample(run)
    mark = int(draw["journal_at_draw"]["max_id"])
    journal = read_journal(mark, sorted(str(site["site_id"]) for site in sample))
    scored = S.score(
        results,
        canary_labels=canaries,
        deterministic=deterministic_result,
        journal_after_draw=journal,
        sites=len(sample),
    )
    written = {
        "draw": run.name,
        "written_at": _now(),
        "protocol_sha256": QN.PROTOCOL_SHA256,
        "journal_mark": mark,
        **scored,
        "files": {name: _sha256(run / name) for name in RESULT_FILES if (run / name).exists()},
    }
    _write_json(out, written)
    (run / "RESULT.md").write_text(S.markdown(written), encoding="utf-8", newline="\n")
    return written


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
    commands: dict[str, argparse.ArgumentParser] = {}
    for name, helps in (
        ("export-stage1", "every question of section 5 into a new handoff directory"),
        ("import-stage1", "parse, fetch and quote-check every stage-1 answer"),
        ("export-reask", "the questions without a counted verdict, to new judges"),
        ("export-stage2", "every counted stage-1 WRONG, to a second judge"),
        ("import-stage2", "parse, fetch and quote-check every stage-2 answer"),
        ("export-stage3", "every stage-2 UNDECIDED, to a third judge"),
        ("import-stage3", "parse, fetch and quote-check every stage-3 answer"),
        ("check-answer", "the shape of one answer text, before it is recorded"),
        ("brief", "the instruction of one batch's Opus agent"),
        ("deterministic", "D1-D6, once (read-only)"),
        ("result", "V1-V3 and A1-A3, once: RESULT.json and RESULT.md"),
    ):
        commands[name] = sub.add_parser(name, help=helps)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    for name in ("export-stage1", "export-reask", "export-stage2", "export-stage3",
                 "check-answer", "brief"):  # fmt: skip
        commands[name].add_argument("--handoff", required=True, type=Path)
    commands["export-reask"].add_argument("--stage", required=True, choices=STAGES)
    for name in ("check-answer", "brief"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", required=True, type=Path)
    args = parser.parse_args(argv)
    run = _resolve(args.run_dir)
    try:
        if args.command == "export-stage1":
            _print(export_stage1(run, args.handoff))
        elif args.command.startswith("import-stage"):
            _print(import_stage(run, f"s{args.command[-1]}"))
        elif args.command == "export-reask":
            _print(export_reask(run, args.stage, args.handoff))
        elif args.command == "export-stage2":
            _print(export_stage2(run, args.handoff))
        elif args.command == "export-stage3":
            _print(export_stage3(run, args.handoff))
        elif args.command == "check-answer":
            text = _resolve(args.text_file).read_bytes().decode("utf-8")
            problem = check_answer(run, args.handoff, args.batch_id, args.label, text)
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        elif args.command == "brief":
            print(brief(run, args.handoff, args.batch_id))
        elif args.command == "deterministic":
            _print(deterministic(run))
        else:
            _print(result(run))
    except (JudgeError, QN.QuestionError, OH.HandoffError, Q.AuditError, pv.PersistError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
