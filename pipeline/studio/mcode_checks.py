"""The four studio checks, answered by `mcode exec` (owner decision 2026-10-03).

The checks themselves did not change; the harness did. Until 2026-10-03 they were four
JavaScript files under `.claude/workflows/`, which run only inside Claude Code's Workflow
tool. This module is their replacement, and the code does the work the workflow scripts
gave to agents:

- the inventory is a read of `pending.jsonl` (minus the tasks `verdicts.jsonl` already
  holds) - no model, no run;
- a TDM-reserved source is read live once with the archive's own reader, as before, into
  `claims_check/live/<id>.txt` - a fetch, not a judgement;
- the answer lines are appended to `verdicts.jsonl` with `prompt_sha256` copied from the
  pending row - a file append, and the driver checks it, as the workflow's append command
  did;
- the case file's `verification` blocks are written by the driver after
  `casefile.from_dict` accepted the file - a write with a parser behind it.

What still needs a model is the judgement, and only that gets a run:

- the claim check: one verifier run per task, then one *independent* skeptic run per
  `supported` answer (a fresh `mcode exec`, never the verifier's session);
- the image check, the marker check and the case-file check: one run per item.

Every run writes its answer to a file (`<handoff dir>/mcode_runs/<id>.json`) and validates
it with `python -m pipeline.studio mcode validate`, because `mcode exec --output-schema`
does not work with M3.1. The driver validates the file again itself, with the same code
path the import uses, so an answer that counts here counts on import. `answered_by` and
`skeptic_by` name the model the exec JSON reported and its run id - never a name the model
wrote about itself.

After the batch the driver checks that no tracked file changed (`mcode.guard_tree`): a run
that wrote into the repository instead of its answer file means its answers are not
counted at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.studio import handoff, markers, mcode
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import claims, images
from pipeline.studio.paper.workspace import PaperWorkspace, load_dossier

CHECKS = ("claims", "images", "markers", "casefile")
#: The venv command every check hands on as its next step (CLAUDE.md: a bare `python` is
#: not this project's interpreter).
VENV_STUDIO = "./.venv/Scripts/python.exe -m pipeline.studio"
#: Where a run writes its answer, beside the handoff files it belongs with.
ANSWER_DIR = "mcode_runs"
MAX_CAPTION_CHARS = images.MAX_CAPTION_CHARS
CASEFILE_METHODS = ("paper evidence", "archived text", "web page")
CASEFILE_STATUSES = frozenset({"verified", "refuted", "unverified"})
#: The fields a model writes per stage; the driver adds the ids and the stamps.
STAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "claims": ("verdict", "quote", "quote_source_id", "explanation", "fix_suggestion"),
    "skeptic": ("verdict", "explanation", "fix_suggestion"),
    "images": ("verdict", "depicts", "subject_box", "caption"),
    "markers": ("verdict", "explanation"),
    "casefile": ("status", "method", "explanation"),
}
#: The verdicts each stage's own AnswerSpec allows, before a task narrows them.
STAGE_VERDICTS: dict[str, frozenset[str]] = {
    "claims": frozenset(claims.VERDICTS),
    "skeptic": frozenset(claims.VERDICTS),
    "images": frozenset(images.VERDICTS),
    "markers": frozenset(markers.VERDICTS),
}
#: A coherence task judges a list of measurements and quotes no source, so it has two.
COHERENCE_VERDICTS = frozenset({"supported", "unsupported"})
#: Ported from the workflow scripts: a flattened web page is one very long line.
LONG_LINES = (
    "A text file can be one very long line (a web page is flattened to a single line), "
    "which the read tool cuts off: page through it with "
    'fold -s -w 1000 "<file>" | sed -n "1,40p" (then 41,80p and so on) and search it '
    "with the grep tool."
)
NO_FILES = "Do not create, edit or delete any file except the answer file named below."


@dataclass
class CheckResult:
    """What one check did, in the shape the session reads (and the old workflow returned)."""

    workspace: str
    answered: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    overruled_by_skeptic: int = 0
    live_reads: list[dict[str, Any]] = field(default_factory=list)
    not_answered: list[dict[str, str]] = field(default_factory=list)
    next: str = ""
    stopped: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "workspace": self.workspace,
            "answered": self.answered,
            "verdicts": self.counts,
        }
        if self.overruled_by_skeptic:
            out["overruled_by_skeptic"] = self.overruled_by_skeptic
        if self.live_reads:
            out["live_reads"] = self.live_reads
        if self.not_answered:
            out["not_answered"] = self.not_answered
        if self.stopped:
            out["stopped"] = self.stopped
        out["next"] = self.next
        return out


# --- the shared machinery ----------------------------------------------------------------------


def _answer_path(handoff_dir: Path, task_id: str) -> Path:
    return handoff_dir / ANSWER_DIR / f"{task_id}.json"


def _validate_cmd(check: str, workspace: Path, answer: Path, task_id: str, stage: str) -> str:
    return (
        f"{VENV_STUDIO} mcode validate --check {check} --stage {stage} --workspace "
        f"{workspace.as_posix()} --answer {answer.as_posix()} --task {task_id}"
    )


def _answer_block(
    check: str, workspace: Path, answer: Path, task_id: str, fields: str, stage: str | None = None
) -> str:
    """The two lines every prompt carries: where the answer goes, how it is validated."""
    return "\n".join(
        [
            f"Write your answer as one JSON object to this file: {answer.as_posix()}",
            f"Validate it with this command: {_validate_cmd(check, workspace, answer, task_id, stage or check)}",
            f"The object holds {fields}. Do not write task_id, prompt_sha256, answered_by or "
            f"skeptic_by: the driver adds them with the model id and the run id of the run "
            f"that produced your answer.",
            "While the validator prints `REJECTED`, fix the file and run the command again. "
            f"{NO_FILES}",
        ]
    )


def _ask(repo: Path, prompt: str) -> tuple[mcode.Run | None, str]:
    """One run; a failure is a reason, never an exception the pool would not see."""
    try:
        return mcode.exec(prompt, cwd=repo), ""
    except StudioError as exc:
        return None, str(exc)


def _quota_stop() -> mcode.Outcome | None:
    """The pool's stop signal when the weekly plan is at 10 % or less (owner decision O20).

    Every run asks, so a batch that runs for hours stops at the line instead of at its
    end; Lyra's probe caches the plan for a minute, so this is one HTTP call a minute.
    """
    stop = mcode.weekly_stop()
    return mcode.Outcome(item=None, stop=stop) if stop else None


def _pending(handoff_dir: Path) -> list[dict[str, Any]]:
    """`pending.jsonl` minus the tasks `verdicts.jsonl` already holds."""
    pending = handoff.read_jsonl(handoff_dir / handoff.PENDING_FILE)
    verdicts = handoff_dir / handoff.VERDICTS_FILE
    if not verdicts.exists():
        return pending
    done = {r.get("task_id") for r in handoff.read_jsonl(verdicts)}
    return [row for row in pending if row["task_id"] not in done]


def _require_export(handoff_dir: Path, command: str) -> None:
    if not (handoff_dir / handoff.TASKS_FILE).is_file():
        raise StudioError(
            f"{handoff_dir / handoff.PENDING_FILE} does not exist: run "
            f"`{VENV_STUDIO} {command}` first"
        )


def _rows(workspace: Path, check: str) -> dict[str, dict[str, Any]]:
    directory = _handoff_dir(workspace, check)
    return {r["task_id"]: r for r in handoff.read_jsonl(directory / handoff.TASKS_FILE)}


def _handoff_dir(workspace: Path, check: str) -> Path:
    if check == "claims":
        return PaperWorkspace(workspace, workspace.name).claims_dir
    if check == "images":
        return PaperWorkspace(workspace, workspace.name).images_dir
    return workspace / markers.CHECK_DIR


def _allowed_verdicts(stage: str, row: dict[str, Any], unread: bool = False) -> frozenset[str]:
    """The verdicts a stage may give this task (the workflow scripts' per-task enums)."""
    if unread:
        return frozenset({"source_missing"})
    if row.get("kind") == "coherence":
        return COHERENCE_VERDICTS
    return STAGE_VERDICTS[stage]


def _validate_object(
    stage: str, row: dict[str, Any], obj: Any, *, unread: bool = False
) -> list[str]:
    """The stage's own shape check, with the enums its prompt states."""
    if not isinstance(obj, dict):
        return ["the answer is not a JSON object"]
    problems: list[str] = []
    missing = [k for k in STAGE_FIELDS[stage] if k not in obj]
    if missing:
        return [f"missing {missing}"]
    types = {"subject_box": (list, type(None))}
    wrong = [k for k in STAGE_FIELDS[stage] if not isinstance(obj[k], types.get(k, (str,)))]
    if wrong:
        return [f"wrong type for {wrong}"]
    if stage != "casefile":
        allowed = _allowed_verdicts(stage, row, unread)
        if obj["verdict"] not in allowed:
            problems.append(f"verdict {obj['verdict']!r} is not one of {sorted(allowed)}")
    if stage == "claims":
        cited = [c["source_id"] for c in row["cited"]]
        if row["kind"] == "coherence":
            if obj["quote"] or obj["quote_source_id"]:
                problems.append(
                    "a coherence task quotes no source: quote and quote_source_id are ''"
                )
        else:
            if obj["quote_source_id"] not in ("", *cited):
                problems.append(
                    f"quote_source_id {obj['quote_source_id']!r} is not one of the task's "
                    f"cited sources {cited}"
                )
            if obj["verdict"] == "supported" and not (
                obj["quote"].strip() and obj["quote_source_id"]
            ):
                problems.append("a supported verdict needs a quote and the source it names")
        if obj["verdict"] == "supported" and not obj["explanation"].strip():
            problems.append("explanation is empty")
    if stage == "images":
        problems.extend(images.answer_check(obj, row))
    if stage == "markers" and not obj["explanation"].strip():
        problems.append("explanation is empty")
    if stage == "casefile":
        if obj["status"] not in CASEFILE_STATUSES:
            problems.append(f"status {obj['status']!r} is not one of {sorted(CASEFILE_STATUSES)}")
        if obj["method"] not in CASEFILE_METHODS:
            problems.append(f"method {obj['method']!r} is not one of {list(CASEFILE_METHODS)}")
        if not obj["explanation"].strip():
            problems.append("explanation is empty")
    return problems


def validate_answer_file(
    check: str,
    path: Path,
    *,
    task_id: str,
    ws: PaperWorkspace | None = None,
    ep_root: Path | None = None,
    stage: str | None = None,
) -> list[str]:
    """The problems in one answer file, all at once; empty means the answer counts.

    This is what the `mcode validate` command prints and what the driver re-runs on the
    file the model wrote, so the model's own ACCEPTED is a hint and this is the decision.
    `stage` is the check's own stage, or `skeptic` for the second run of a claim task.
    """
    stage = stage or check
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path} does not exist: the run wrote no answer file"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{path.name} is not JSON ({exc})"]
    if stage == "casefile":
        return _validate_object("casefile", {}, obj)
    if stage not in STAGE_FIELDS:
        return [f"unknown stage {stage!r}"]
    workspace = ws.root if ws is not None else (ep_root or Path("."))
    row = _rows(workspace, check).get(task_id)
    if row is None:
        return [f"no such task in the current export: {task_id}"]
    unread = bool(check == "claims" and _unread_sources(workspace, row))
    return _validate_object(stage, row, obj, unread=unread)


def _unread_sources(workspace: Path, row: dict[str, Any]) -> list[str]:
    """The TDM-reserved sources of a claim task whose live read did not save a text."""
    if workspace.name in ("", None):
        return []
    live = _handoff_dir(workspace, "claims") / claims.LIVE_DIR
    out: list[str] = []
    for cited in row["cited"]:
        if cited["text_status"] != "tdm_reserved" or cited["text_path"] is not None:
            continue
        if not (live / f"{cited['source_id']}.txt").is_file():
            out.append(cited["source_id"])
    return out


def _read_answer(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _stamp(run: mcode.Run, role: str, check: str, task_id: str) -> str:
    return f"{run.model} ({role}, mcode exec, {run.run_id}, {task_id})"


def _bank(
    repo: Path,
    tree: list[str],
    directory: Path,
    batch: list[mcode.Outcome],
    banked: list[Any],
) -> None:
    """Bank one wave: check the tree, then append the lines it produced, and say so.

    Per wave, not per batch: a check runs for hours, and a batch that is stopped (the quota
    stop, a 429 storm, the owner) keeps the waves it finished. The line is what makes a
    long run watchable: the 42-task calibration of 2026-10-03 answered two tasks in three
    and a half hours, and the only evidence of that was a file count.
    """
    mcode.guard_tree(repo, tree)
    lines = [o.value for o in batch if o.value is not None]
    if lines:
        _append_lines(directory, lines)
        banked.extend(lines)
    print(
        f"wave: {len(lines)} answered, {len(batch) - len(lines)} not answered, "
        f"{len(banked)} in total ({directory.name}/{handoff.VERDICTS_FILE})",
        flush=True,
    )


def _append_lines(handoff_dir: Path, lines: list[dict[str, Any]]) -> list[str]:
    """Append answer lines the way the workflow's append command did: every line is a
    pending task, `prompt_sha256` is copied from its pending row, nothing is overwritten."""
    pending = {r["task_id"]: r for r in handoff.read_jsonl(handoff_dir / handoff.PENDING_FILE)}
    verdicts = handoff_dir / handoff.VERDICTS_FILE
    old = verdicts.read_text(encoding="utf-8") if verdicts.exists() else ""
    there = {r.get("task_id") for r in handoff.read_jsonl(verdicts)} if old else set()
    bad = [r["task_id"] for r in lines if r["task_id"] not in pending or r["task_id"] in there]
    if bad:
        raise StudioError(f"not pending, or already in {handoff.VERDICTS_FILE}: {bad}")
    for row in lines:
        row["prompt_sha256"] = pending[row["task_id"]]["prompt_sha256"]
    lead = "\n" if old and not old.endswith("\n") else ""
    with verdicts.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            lead + "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in lines)
        )
    return [r["task_id"] for r in lines]


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


def _skipped(outcome: mcode.Outcome, task_id: str, ref: str) -> mcode.Outcome:
    outcome.item = {"task_id": task_id, "ref": ref}
    return outcome


# --- the claim check ---------------------------------------------------------------------------


def _tdm_ids(row: dict[str, Any]) -> list[str]:
    return [
        c["source_id"]
        for c in row["cited"]
        if c["text_status"] == "tdm_reserved" and c["text_path"] is None
    ]


def _default_live_read(ws: PaperWorkspace, source_id: str, url: str) -> str:
    """Read one TDM-reserved page with the archive's reader into live/<id>.txt.

    Returns "" when the text is saved, else the last error line. The header is the one
    `paper claims-import` checks.
    """
    import asyncio

    from pipeline.lyra.archive_completion import _client, fetch_document

    async def read():
        async with _client() as client:
            return await fetch_document(client, url)

    try:
        doc = asyncio.run(read())
    except Exception as exc:  # noqa: BLE001 - the reason is the answer, not a crash
        return f"{type(exc).__name__}: {exc}"
    at = datetime.now(UTC).isoformat(timespec="seconds")
    out = ws.root / claims.live_rel(ws, source_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="") as handle:
        handle.write(f"URL: {url}\nFetched: {at}\n\n{doc.text}\n")
    return ""


def _live_reads(
    ws: PaperWorkspace, rows: list[dict[str, Any]], live_read: Callable[[str, str], str] | None
) -> dict[str, tuple[bool, str]]:
    """One live read per TDM-reserved source of the pending tasks, before any verifier."""
    read = live_read or (lambda sid, url: _default_live_read(ws, sid, url))
    urls = {
        c["source_id"]: c["url"]
        for row in rows
        for c in row["cited"]
        if c["source_id"] in _tdm_ids(row)
    }
    out: dict[str, tuple[bool, str]] = {}
    for sid in sorted(urls):
        saved = (ws.claims_dir / claims.LIVE_DIR / f"{sid}.txt").is_file()
        if saved:
            out[sid] = (True, "kept: an earlier run saved it")
            continue
        detail = str(read(sid, urls[sid]) or "")
        if not detail and not (ws.claims_dir / claims.LIVE_DIR / f"{sid}.txt").is_file():
            detail = "the live read wrote no text file"
        out[sid] = (not detail, detail)
    return out


def _live_note(saved: list[str], directory: Path) -> str:
    """Ported from the claim-check workflow: a saved live text is named, so the verifier
    quotes from the file instead of fetching the page a second time (review of I3: only the
    sources whose read actually saved a text may be named)."""
    if not saved:
        return ""
    return (
        "The prompt asks you to read TDM-reserved sources live and save their text. The "
        f"driver has already done that: the page text of {', '.join(saved)} is saved in "
        f"{directory.as_posix()}/live/<source_id>.txt (lines 1-3 are the header "
        '"URL: ...", "Fetched: ..." and an empty line; the text starts on line 4). Read '
        "that file as the source's text and quote from it. Do not fetch the page again."
    )


def _task_head(ws: PaperWorkspace, row: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Paper workspace: {ws.root.as_posix()}",
            f"Task: {row['task_id']}",
            f"Prompt file: {ws.claims_dir.as_posix()}/{row['prompt_path']}",
        ]
    )


def _verifier_prompt(ws: PaperWorkspace, row: dict[str, Any], unread: list[tuple[str, str]]) -> str:
    coherence = row["kind"] == "coherence"
    live_dir = ws.claims_dir
    parts = [
        "You are the verifier of one claim-check task of a Theo paper (Ancient Nerds). Your "
        "answer is checked by machine on import (a quote must occur verbatim in the text of "
        "the source it names), and if you judge the claim supported, an adversarial skeptic "
        "tries to refute it.",
        _task_head(ws, row),
        "1. Read the prompt file in full. It is the exact question and its rules bind you. "
        "Its task JSON holds the paragraph, the claim and the cited sources; cited[].n is "
        "the number that source's marker [n] shows in the paragraph.",
        (
            '2. Kind coherence: judge the list of measurements in "claim". There are no '
            'source files; quote and quote_source_id are "".'
            if coherence
            else f"2. Read the text of every cited source in full: {ws.root.as_posix()}"
            "/<text_path> for each cited[].text_path. " + LONG_LINES
        ),
        _live_note(
            [sid for sid in _tdm_ids(row) if not any(u[0] == sid for u in unread)], live_dir
        ),
        (
            "The live read of "
            + "; ".join(f"{sid} failed ({detail})" for sid, detail in unread)
            + ". The only verdict you may give is therefore source_missing: say in explanation "
            "which statements rest on that source, and in fix_suggestion which other cited "
            "source could carry them, or that they must go."
            if unread
            else ""
        ),
        f"3. Judge only from these files: no web search, no outside knowledge. {NO_FILES}",
        _answer_block(
            "claims",
            ws.root,
            _answer_path(ws.claims_dir, row["task_id"]),
            row["task_id"],
            "verdict, quote, quote_source_id, explanation and fix_suggestion",
        ),
        "Answer: verdict"
        + (
            ": source_missing (see above)."
            if unread
            else ": supported, partly, unsupported or source_missing."
        )
        + " quote: the sentence that proves the claim, copied character for character from the "
        'text of quote_source_id ("" when no quote applies); quote_source_id: the id of that '
        'source ("" when none); explanation: what the sources say about the claim; '
        'fix_suggestion: how to fix the paper ("" when supported).',
    ]
    return "\n\n".join(p for p in parts if p)


def _skeptic_prompt(ws: PaperWorkspace, row: dict[str, Any], verdict: dict[str, Any]) -> str:
    coherence = row["kind"] == "coherence"
    checks = (
        [
            "1. No two measurements in the list contradict each other for the same thing: "
            "compare every pair that measures the same object or quantity, with units "
            "converted."
        ]
        if coherence
        else [
            f"1. The quote occurs verbatim, whitespace aside, in the text of quote_source_id: "
            f"{ws.root.as_posix()}/texts/<id>.txt, or for a TDM-reserved source the saved live "
            f"text {ws.claims_dir.as_posix()}/live/<id>.txt. Search for it with the grep tool.",
            "2. The source states the claim. For kind paragraph: every factual statement of "
            "the paragraph, every name, date and number, is stated by the source that its own "
            "marker [n] names (cited[].n); a statement that only another cited source states "
            "is a wrong citation.",
            "3. The paper states nothing more strongly than the source does (certainty, size, "
            "date, who said it).",
        ]
    )
    parts = [
        "You are the adversarial skeptic for one claim-check answer of a Theo paper (Ancient "
        "Nerds). A verifier judged the task below supported. That verdict stands only if you "
        "try hard to refute it and fail. When you cannot confirm a part, refute it.",
        _task_head(ws, row),
        "The verifier's answer: "
        + json.dumps(
            {
                "quote": verdict.get("quote", ""),
                "quote_source_id": verdict.get("quote_source_id", ""),
                "explanation": verdict.get("explanation", ""),
            },
            ensure_ascii=False,
        ),
        (
            'Read the prompt file in full; the list of measurements is its "claim".'
            if coherence
            else f"Read the prompt file in full, and the text of every cited source it names: "
            f"{ws.root.as_posix()}/<text_path>. " + LONG_LINES
        ),
        _live_note(_tdm_ids(row), ws.claims_dir),
        "Check:",
        "\n".join(checks),
        f"Judge only from these files: no web search, no outside knowledge. {NO_FILES}",
        _answer_block(
            "claims",
            ws.root,
            _answer_path(ws.claims_dir, f"{row['task_id']}.skeptic"),
            row["task_id"],
            "verdict, explanation and fix_suggestion",
            stage="skeptic",
        ),
        "Answer: verdict: supported when every check holds, otherwise the verdict the prompt "
        "file defines for what you found; explanation: what you checked and, when you refute, "
        'exactly what fails; fix_suggestion: how to fix the paper ("" when supported).',
    ]
    return "\n\n".join(p for p in parts if p)


def _claim_line(
    row: dict[str, Any],
    verifier: dict[str, Any],
    run: mcode.Run,
    skeptic: dict[str, Any] | None,
    srun: mcode.Run | None,
) -> dict[str, Any]:
    coherence = row["kind"] == "coherence"
    answered_by = _stamp(run, "verifier", "claims", row["task_id"])
    line: dict[str, Any] = {
        "task_id": row["task_id"],
        "verdict": verifier["verdict"],
        "quote": "" if coherence else verifier["quote"],
        "quote_source_id": "" if coherence else verifier["quote_source_id"],
        "explanation": verifier["explanation"],
        "fix_suggestion": verifier["fix_suggestion"],
        "answered_by": answered_by,
        "skeptic_by": "",
    }
    if skeptic is None or srun is None:
        return line
    skeptic_by = _stamp(srun, "skeptic", "claims", row["task_id"])
    if skeptic["verdict"] == "supported":
        return {**line, "skeptic_by": skeptic_by}
    return {
        **line,
        "verdict": skeptic["verdict"],
        "quote": "",
        "quote_source_id": "",
        "explanation": (
            f"The verifier judged it supported ({verifier['explanation']}); the skeptic "
            f"refuted that: {skeptic['explanation']}"
        ),
        "fix_suggestion": skeptic["fix_suggestion"],
        "answered_by": f"{answered_by}, overruled by {skeptic_by}",
    }


def answer_claims(
    ws: PaperWorkspace,
    *,
    repo: Path,
    live_read: Callable[[str, str], str] | None = None,
    limit: int | None = None,
) -> CheckResult:
    """Answer `claims_check/pending.jsonl`: one verifier run per task, one skeptic run per
    `supported` answer. The lines are appended to `verdicts.jsonl`; `paper claims-import`
    validates and merges them.
    """
    _require_export(ws.claims_dir, f"paper claims-export {ws.request_id}")
    rows = _pending(ws.claims_dir)
    result = CheckResult(
        workspace=ws.root.as_posix(), next=f"{VENV_STUDIO} paper claims-import {ws.request_id}"
    )
    if limit:
        rows = rows[:limit]
    live = _live_reads(ws, rows, live_read)
    result.live_reads = [
        {"source_id": sid, "saved": saved, "detail": detail}
        for sid, (saved, detail) in sorted(live.items())
    ]
    dossier = load_dossier(ws)
    stop = mcode.weekly_stop()
    if stop:
        result.stopped = stop
        result.not_answered = [
            {"task_id": r["task_id"], "ref": r["ref"], "reason": stop} for r in rows
        ]
        return result
    tree = mcode.tree_state(repo)
    handoff_dir = ws.claims_dir
    banked: list[dict[str, Any]] = []
    pool = mcode.Pool()

    def one(row: dict[str, Any]) -> mcode.Outcome:
        if (quota := _quota_stop()) is not None:
            return quota
        unread = [(sid, live[sid][1]) for sid in _tdm_ids(row) if not live[sid][0]]
        prompt = _verifier_prompt(ws, row, unread)
        run, why = _ask(repo, prompt)
        if run is None:
            return _skipped(mcode.Outcome(item=None, reason=why), row["task_id"], row["ref"])
        if run.rate_limited:
            return _skipped(
                mcode.Outcome(item=None, reason=run.error, rate_limited=True),
                row["task_id"],
                row["ref"],
            )
        answer = _answer_path(ws.claims_dir, row["task_id"])
        verdict = _read_answer(answer)
        problems = validate_answer_file("claims", answer, task_id=row["task_id"], ws=ws)
        if verdict is None or problems:
            return _skipped(
                mcode.Outcome(
                    item=None,
                    reason="; ".join(problems) or "the answer file holds no JSON object",
                    run=run,
                ),
                row["task_id"],
                row["ref"],
            )
        line = _claim_line(row, verdict, run, None, None)
        srun: mcode.Run | None = None
        if verdict["verdict"] == "supported":
            srun, swhy = _ask(repo, _skeptic_prompt(ws, row, verdict))
            if srun is None or srun.rate_limited:
                return _skipped(
                    mcode.Outcome(
                        item=None,
                        reason=swhy or srun.error if (srun or swhy) else "",
                        run=srun,
                        rate_limited=bool(srun and srun.rate_limited),
                    ),
                    row["task_id"],
                    row["ref"],
                )
            spath = _answer_path(ws.claims_dir, f"{row['task_id']}.skeptic")
            skeptic = _read_answer(spath)
            sproblems = validate_answer_file(
                "claims", spath, task_id=row["task_id"], ws=ws, stage="skeptic"
            )
            if skeptic is None or sproblems:
                return _skipped(
                    mcode.Outcome(
                        item=None,
                        reason="skeptic: " + ("; ".join(sproblems) or "no JSON object"),
                        run=srun,
                    ),
                    row["task_id"],
                    row["ref"],
                )
            line = _claim_line(row, verdict, run, skeptic, srun)
        # the import's own machine check decides, not the driver
        try:
            handoff.validate_answers(
                [{**line, "prompt_sha256": row["prompt_sha256"]}],
                {row["task_id"]: row},
                claims.ANSWER_SPEC,
                claims.quote_check(ws, dossier),
            )
        except handoff.HandoffError as exc:
            return _skipped(
                mcode.Outcome(item=None, reason=str(exc), run=run), row["task_id"], row["ref"]
            )
        return mcode.Outcome(
            item=row, value=line, run=run, rate_limited=bool(srun and srun.rate_limited)
        )

    def bank(batch: list[mcode.Outcome]) -> None:
        _bank(repo, tree, handoff_dir, batch, banked)

    outcomes = pool.map(rows, one, on_wave=bank)
    if pool.stop:
        result.stopped = pool.stop
    lines = banked
    result.not_answered = _not_answered(outcomes, rows, pool.stop)
    mcode.guard_tree(repo, tree)
    result.answered = len(lines)
    result.counts = _count([line["verdict"] for line in lines])
    result.overruled_by_skeptic = sum(1 for line in lines if "overruled by" in line["answered_by"])
    return result


# --- the image check ---------------------------------------------------------------------------


def _image_prompt(ws: PaperWorkspace, row: dict[str, Any]) -> str:
    answer = _answer_path(ws.images_dir, row["task_id"])
    return "\n\n".join(
        [
            "You check one candidate picture for a Theo paper (Ancient Nerds): does it show "
            "the reader the subject of the paragraph it would sit under?",
            "\n".join(
                [
                    f"Paper workspace: {ws.root.as_posix()}",
                    f"Task: {row['task_id']}",
                    f"Prompt file: {ws.images_dir.as_posix()}/{row['prompt_path']}",
                ]
            ),
            "1. Read the prompt file in full. It is the exact question and its rules bind you. "
            "Its task JSON holds the subject, the paragraph, image_path and the candidate's "
            "metadata (title, description, licence, source).",
            f"2. Open the picture {ws.root.as_posix()}/<image_path> (image_path from the task "
            "JSON, relative to the paper workspace) with the read tool and look at it.",
            f"3. Judge from the picture and the task JSON only: no web search. {NO_FILES}",
            _answer_block(
                "images",
                ws.root,
                answer,
                row["task_id"],
                "verdict, depicts, subject_box and caption",
            ),
            f"Answer: verdict: meaningful, weak, misleading or off_topic; depicts: what the "
            f"picture actually shows, one sentence; subject_box: [x, y, w, h] as fractions of "
            f"the picture's width and height around the subject, with x + w and y + h at most "
            f"1, or null; caption: for meaningful or weak, one plain-English sentence of at "
            f"most {MAX_CAPTION_CHARS} characters in Latin script, without [ or *, that says "
            f'what the reader sees, and "" otherwise.',
        ]
    )


def answer_images(ws: PaperWorkspace, *, repo: Path, limit: int | None = None) -> CheckResult:
    """Answer `images/pending.jsonl`: one run per candidate picture."""
    _require_export(ws.images_dir, f"paper images-export {ws.request_id}")
    rows = _pending(ws.images_dir)
    if limit:
        rows = rows[:limit]
    result = CheckResult(
        workspace=ws.root.as_posix(), next=f"{VENV_STUDIO} paper images-import {ws.request_id}"
    )
    stop = mcode.weekly_stop()
    if stop:
        result.stopped = stop
        result.not_answered = [
            {"task_id": r["task_id"], "ref": r.get("ref", ""), "reason": stop} for r in rows
        ]
        return result
    tree = mcode.tree_state(repo)
    handoff_dir = ws.images_dir
    banked: list[dict[str, Any]] = []
    pool = mcode.Pool()

    def one(row: dict[str, Any]) -> mcode.Outcome:
        if (quota := _quota_stop()) is not None:
            return quota
        run, why = _ask(repo, _image_prompt(ws, row))
        if run is None:
            return _skipped(
                mcode.Outcome(item=None, reason=why), row["task_id"], row.get("ref", "")
            )
        if run.rate_limited:
            return _skipped(
                mcode.Outcome(item=None, reason=run.error, rate_limited=True),
                row["task_id"],
                row.get("ref", ""),
            )
        answer = _answer_path(ws.images_dir, row["task_id"])
        obj = _read_answer(answer)
        problems = validate_answer_file("images", answer, task_id=row["task_id"], ws=ws)
        if obj is None or problems:
            return _skipped(
                mcode.Outcome(item=None, reason="; ".join(problems) or "no JSON object", run=run),
                row["task_id"],
                row.get("ref", ""),
            )
        line = {
            "task_id": row["task_id"],
            "verdict": obj["verdict"],
            "depicts": obj["depicts"],
            "subject_box": obj["subject_box"],
            "caption": obj["caption"].strip() if obj["verdict"] in images.KEEP else "",
            "answered_by": _stamp(run, "image check", "images", row["task_id"]),
        }
        try:
            handoff.validate_answers(
                [{**line, "prompt_sha256": row["prompt_sha256"]}],
                {row["task_id"]: row},
                images.ANSWER_SPEC,
                images.answer_check,
            )
        except handoff.HandoffError as exc:
            return _skipped(
                mcode.Outcome(item=None, reason=str(exc), run=run),
                row["task_id"],
                row.get("ref", ""),
            )
        return mcode.Outcome(item=row, value=line, run=run)

    def bank(batch: list[mcode.Outcome]) -> None:
        _bank(repo, tree, handoff_dir, batch, banked)

    outcomes = pool.map(rows, one, on_wave=bank)
    if pool.stop:
        result.stopped = pool.stop
    lines = banked
    result.not_answered = _not_answered(outcomes, rows, pool.stop)
    mcode.guard_tree(repo, tree)
    result.answered = len(lines)
    result.counts = _count([line["verdict"] for line in lines])
    return result


def _not_answered(
    outcomes: list[mcode.Outcome], rows: list[dict[str, Any]], stop: str
) -> list[dict[str, str]]:
    out = [
        {"task_id": o.item["task_id"], "ref": o.item.get("ref", ""), "reason": o.reason}
        for o in outcomes
        if o.value is None and isinstance(o.item, dict)
    ]
    done = {n["task_id"] for n in out} | {
        o.value["task_id"] for o in outcomes if o.value is not None
    }
    out.extend(
        {"task_id": r["task_id"], "ref": r.get("ref", ""), "reason": stop or "not run"}
        for r in rows
        if r["task_id"] not in done
    )
    return out


# --- the marker check --------------------------------------------------------------------------


def _marker_prompt(ep_root: Path, row: dict[str, Any]) -> str:
    from pipeline.studio.markers import CHECK_DIR

    answer = _answer_path(ep_root / CHECK_DIR, row["task_id"])
    return "\n\n".join(
        [
            "You check one marker of a Case File episode (Ancient Nerds). The video will "
            "draw a labelled marker on a box of a picture. Owner rule: every marking must hit "
            "the right object; a marker that misses is not drawn.",
            "\n".join(
                [
                    f"Episode workspace: {ep_root.as_posix()}",
                    f"Task: {row['task_id']}",
                    f"Prompt file: {(ep_root / CHECK_DIR).as_posix()}/{row['prompt_path']}",
                ]
            ),
            "1. Read the prompt file in full. It is the exact question and its rules bind you. "
            "Its task JSON holds the label, what the picture depicts, the box, crop_path and "
            "context_path.",
            f"2. Open both pictures with the read tool and look at them: "
            f"{ep_root.as_posix()}/{row['crop_path']} (the box with a 10 % margin, enlarged) "
            f"and {ep_root.as_posix()}/{row['context_path']} (the whole picture with the box "
            "outlined in red).",
            f"3. Judge from the two pictures and the task JSON only: no web search. {NO_FILES}",
            _answer_block("markers", ep_root, answer, row["task_id"], "verdict and explanation"),
            "Answer: verdict: hits or misses; explanation: what the box covers (for misses: "
            "what it actually covers and where the named object is).",
        ]
    )


def answer_markers(ep_root: Path, *, repo: Path, limit: int | None = None) -> CheckResult:
    """Answer `markers_check/pending.jsonl`: one run per marker crop."""
    from pipeline.studio.markers import CHECK_DIR

    directory = ep_root / CHECK_DIR
    _require_export(directory, f"episode markers-export {ep_root.name}")
    rows = _pending(directory)
    if limit:
        rows = rows[:limit]
    slug = ep_root.name
    result = CheckResult(
        workspace=ep_root.as_posix(), next=f"{VENV_STUDIO} episode markers-import {slug}"
    )
    stop = mcode.weekly_stop()
    if stop:
        result.stopped = stop
        result.not_answered = [
            {"task_id": r["task_id"], "ref": r.get("ref", ""), "reason": stop} for r in rows
        ]
        return result
    tree = mcode.tree_state(repo)
    handoff_dir = directory
    banked: list[dict[str, Any]] = []
    pool = mcode.Pool()

    def one(row: dict[str, Any]) -> mcode.Outcome:
        if (quota := _quota_stop()) is not None:
            return quota
        run, why = _ask(repo, _marker_prompt(ep_root, row))
        if run is None:
            return _skipped(
                mcode.Outcome(item=None, reason=why), row["task_id"], row.get("ref", "")
            )
        if run.rate_limited:
            return _skipped(
                mcode.Outcome(item=None, reason=run.error, rate_limited=True),
                row["task_id"],
                row.get("ref", ""),
            )
        answer = _answer_path(directory, row["task_id"])
        obj = _read_answer(answer)
        problems = validate_answer_file("markers", answer, task_id=row["task_id"], ep_root=ep_root)
        if obj is None or problems:
            return _skipped(
                mcode.Outcome(item=None, reason="; ".join(problems) or "no JSON object", run=run),
                row["task_id"],
                row.get("ref", ""),
            )
        line = {
            "task_id": row["task_id"],
            "verdict": obj["verdict"],
            "explanation": obj["explanation"],
            "answered_by": _stamp(run, "marker check", "markers", row["task_id"]),
        }
        try:
            handoff.validate_answers(
                [{**line, "prompt_sha256": row["prompt_sha256"]}],
                {row["task_id"]: row},
                markers.ANSWER_SPEC,
            )
        except handoff.HandoffError as exc:
            return _skipped(
                mcode.Outcome(item=None, reason=str(exc), run=run),
                row["task_id"],
                row.get("ref", ""),
            )
        return mcode.Outcome(item=row, value=line, run=run)

    def bank(batch: list[mcode.Outcome]) -> None:
        _bank(repo, tree, handoff_dir, batch, banked)

    outcomes = pool.map(rows, one, on_wave=bank)
    if pool.stop:
        result.stopped = pool.stop
    lines = banked
    result.not_answered = _not_answered(outcomes, rows, pool.stop)
    mcode.guard_tree(repo, tree)
    result.answered = len(lines)
    result.counts = _count([line["verdict"] for line in lines])
    return result


# --- the case-file check -----------------------------------------------------------------------


def default_casefile_probe(ep_root: Path, item_id: str) -> dict[str, Any]:
    """Read one case-file evidence item's source and report what its quote is checked
    against, by route: the paper's own evidence entry, an archived text, or the live page
    (the archive's reader; Wikipedia through its REST HTML)."""
    import asyncio

    from pipeline.lyra.archive_completion import _client, fetch_document, resolve_fetch_url
    from pipeline.studio.casefile import from_dict
    from pipeline.studio.episode import EpisodeWorkspace
    from pipeline.studio.paper.evidence import quote_in_text, ws_normalize
    from pipeline.studio.paper.workspace import PaperWorkspace

    ews = EpisodeWorkspace(ep_root, ep_root.name)
    data = json.loads(ews.casefile.read_text(encoding="utf-8"))
    cf = from_dict(data)
    item = next(x for x in cf.evidence if x.id == item_id)
    pws = (
        PaperWorkspace(ews.paper_dir(cf.paper.request_id), cf.paper.request_id)
        if cf.paper
        else None
    )
    out: dict[str, Any] = {
        "id": item.id,
        "kind": item.kind,
        "statement": item.statement,
        "url": item.source.url,
        "quote": item.source.quote,
    }

    def near(text: str) -> dict[str, Any]:
        norm, quote = ws_normalize(text), ws_normalize(item.source.quote)
        i = norm.find(quote) if quote else -1
        return {
            "found": i >= 0,
            "chars": len(norm),
            "context": (norm[max(0, i - 600) : i + len(quote) + 600] if i >= 0 else norm[:1500]),
        }

    if item.paper_anchor:
        entries = (
            {x["id"]: x for x in json.loads(pws.evidence.read_text(encoding="utf-8"))}
            if pws
            else {}
        )
        entry = entries.get(item.paper_anchor)
        out.update(
            route="paper evidence",
            paper_evidence=entry,
            found=bool(entry) and quote_in_text(item.source.quote, entry["quote"]),
        )
        return out
    sid = item.source.source_id
    local = (
        [p for p in (pws.text_path(sid), pws.root / claims.live_rel(pws, sid)) if p.exists()]
        if pws and sid
        else []
    )
    if local:
        out.update(
            route="archived text",
            path=local[0].as_posix(),
            **near(local[0].read_text(encoding="utf-8")),
        )
        return out
    kind, url = resolve_fetch_url(item.source.url)
    out["route"] = "web page"
    if kind == "youtube":
        out["error"] = "a YouTube source has no page text to read"
        return out

    async def read(url: str):
        async with _client() as client:
            return await fetch_document(client, url)

    doc = asyncio.run(read(url))
    out.update(final_url=doc.final_url, **near(doc.text))
    return out


def _casefile_prompt(ep_root: Path, item: dict[str, str], probe_cmd: str) -> str:
    answer = ep_root / ANSWER_DIR / f"{item['id']}.json"
    return "\n\n".join(
        [
            "You verify one evidence item of the case file of a Case File episode (Ancient "
            "Nerds): does its source really say what the item states? A script may show only "
            "verified evidence.",
            f"Episode workspace: {ep_root.as_posix()}\nEvidence item: {item['id']}",
            f"1. Run this command once, from the repository root, as one command, exactly as "
            f"written. It reads the item from casefile.json and prints its statement, its "
            f"verbatim source quote and the text the quote is checked against, by route:\n"
            f'- "paper evidence" (the item has a paper_anchor): the entry of the paper\'s '
            f"evidence.json with that id (null when there is none); found tells whether the "
            f"item's quote occurs verbatim, whitespace aside, in the entry's quote.\n"
            f'- "archived text" (the item names a source_id whose archived text, or saved live '
            f"text, the paper workspace holds): found, and the context around the quote in "
            f"that text (the start of the text when the quote is absent); path is the file.\n"
            f'- "web page" (otherwise): the page at the item\'s source url read live; found, and '
            f"the context around the quote (the start of the page when the quote is absent), "
            f"or error.\n{probe_cmd}",
            "2. Judge:\n- verified: found is true, and the quote read in its context states the "
            "statement: the statement says nothing the quote does not (names, dates, numbers, "
            'certainty). With route "paper evidence", the statement must also say no more than '
            "the entry's claim.\n- refuted: the text is readable and the quote, read in its "
            "context, says something else, or the source contradicts the statement.\n"
            "- unverified: the text cannot be checked: the command failed while reading the "
            "page (its last error line says why), the source is a YouTube video, the page is a "
            "paywall, login or cookie wall, or the quote does not occur verbatim in a "
            'readable text.\nWith route "archived text" you may read more of the file at path '
            "with the read tool. Do not search the web.",
            _answer_block(
                "casefile", ep_root, answer, item["id"], "status, method and explanation"
            ),
            'Answer: status; method: the route the command printed ("web page" when it failed '
            "while reading the page); explanation: what you found, and for refuted or "
            "unverified exactly why.",
        ]
    )


def verify_casefile(
    ep_root: Path,
    *,
    repo: Path,
    probe: Callable[[Path, str], dict[str, Any]] | None = None,
    limit: int | None = None,
) -> CheckResult:
    """Verify every evidence item of a case file that is not yet verified, one run each.

    Unlike the other three checks this one has no handoff directory: its contract is
    `casefile.json` itself. The driver writes the `verification` block of every item it
    got a verdict for, after `casefile.from_dict` accepted the result, and changes no other
    key.
    """
    from pipeline.studio.casefile import from_dict
    from pipeline.studio.episode import EpisodeWorkspace

    slug = ep_root.name
    result = CheckResult(workspace=ep_root.as_posix(), next=f"{VENV_STUDIO} episode check {slug}")
    path = EpisodeWorkspace(ep_root, slug).casefile
    if not path.is_file():
        raise StudioError(
            f"{path} does not exist: build the case file first (skill studio-casefile)"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [
        {"id": e.id, "status": e.verification.status}
        for e in from_dict(data).evidence
        if e.verification.status != "verified"
    ]
    if limit:
        items = items[:limit]
    if not items:
        return result
    read_probe = probe or default_casefile_probe
    stop = mcode.weekly_stop()
    if stop:
        result.stopped = stop
        result.not_answered = [{"id": i["id"], "reason": stop} for i in items]
        return result
    tree = mcode.tree_state(repo)
    pool = mcode.Pool()

    def one(item: dict[str, str]) -> mcode.Outcome:
        if (quota := _quota_stop()) is not None:
            return quota
        try:
            found = read_probe(ep_root, item["id"])
        except Exception as exc:  # noqa: BLE001 - an unreadable source is an answer
            return mcode.Outcome(item=item["id"], reason=f"the probe failed: {exc}")
        probe_cmd = f'The route is "{found.get("route", "web page")}"; found: {found.get("found")}.'
        run, why = _ask(repo, _casefile_prompt(ep_root, item, probe_cmd))
        if run is None:
            return mcode.Outcome(item=item["id"], reason=why)
        if run.rate_limited:
            return mcode.Outcome(item=item["id"], reason=run.error, rate_limited=True)
        answer = ep_root / ANSWER_DIR / f"{item['id']}.json"
        problems = validate_answer_file("casefile", answer, task_id=item["id"])
        obj = _read_answer(answer)
        if obj is None or problems:
            return mcode.Outcome(
                item=item["id"],
                reason="; ".join(problems) or "no JSON object",
                run=run,
            )
        return mcode.Outcome(
            item=item["id"],
            value={
                "id": item["id"],
                **obj,
                "by": _stamp(run, "case file check", "casefile", item["id"]),
            },
            run=run,
        )

    outcomes = pool.map(items, one)
    if pool.stop:
        result.stopped = pool.stop
    checked = [o for o in outcomes if o.value is not None]
    result.not_answered = [
        {"id": o.item if isinstance(o.item, str) else o.item.get("id"), "reason": o.reason}
        for o in outcomes
        if o.value is None
    ]
    result.not_answered.extend(
        {"id": i["id"], "reason": pool.stop or "not run"}
        for i in items
        if i["id"] not in {o.value["id"] for o in checked}
        and i["id"] not in {n["id"] for n in result.not_answered}
    )
    mcode.guard_tree(repo, tree)
    if checked:
        at = datetime.now(UTC).isoformat(timespec="seconds")
        by_id = {o.value["id"]: o.value for o in checked}
        for entry in data["evidence"]:
            verdict = by_id.get(entry["id"])
            if verdict is not None:
                entry["verification"] = {
                    "status": verdict["status"],
                    "by": verdict["by"],
                    "at": at,
                    "method": verdict["method"],
                }
        from_dict(data)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
        )
    result.answered = len(checked)
    result.counts = _count([o.value["status"] for o in checked])
    return result
