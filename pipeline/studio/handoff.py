"""The file seam between studio code and Claude: export tasks, validate answers, import.

No model is called from here. A step exports one task per question:

    <dir>/tasks.jsonl            every current task (payload + task_id + prompt_path + prompt_sha256)
    <dir>/pending.jsonl          the tasks without an accepted answer (what the workflow answers)
    <dir>/prompts/<task_id>.txt  the exact prompt text, UTF-8

A workflow (.claude/workflows/theo-claim-check.js, theo-image-check.js) reads pending.jsonl,
answers each task by reading its prompt file, and writes `<dir>/verdicts.jsonl`, one JSON
object per line, echoing `task_id` and `prompt_sha256`. `import_answers` validates the whole
file (shape, enums, known task ids, prompt hashes, answered_by) and merges it into
`<dir>/accepted.json`. A task id is derived from its prompt hash, so a task whose paragraph,
sources or instructions changed is a new task, and an old answer can never vouch for it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.studio.errors import StudioError
from pipeline.utils.card_provenance import text_sha256 as prompt_sha256

#: A step's own rule on top of the shape check: (answer, task) -> problems.
ExtraCheck = Callable[[dict[str, Any], dict[str, Any]], list[str]]

PROMPTS_DIR = "prompts"
TASKS_FILE = "tasks.jsonl"
PENDING_FILE = "pending.jsonl"
VERDICTS_FILE = "verdicts.jsonl"
ACCEPTED_FILE = "accepted.json"


class HandoffError(StudioError):
    """An answer file cannot be accepted; the message lists every problem."""


@dataclass(frozen=True)
class Task:
    kind: str
    prompt: str
    payload: dict[str, Any]

    @property
    def prompt_sha256(self) -> str:
        return prompt_sha256(self.prompt)

    @property
    def task_id(self) -> str:
        return f"{self.kind}-{self.prompt_sha256[:12]}"


@dataclass(frozen=True)
class AnswerSpec:
    """What a valid answer line carries: field -> allowed Python types, plus enums."""

    fields: dict[str, tuple[type, ...]]
    enums: dict[str, frozenset[str]]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HandoffError(f"{path.name}:{lineno}: not JSON ({exc})") from exc
        if not isinstance(row, dict):
            raise HandoffError(f"{path.name}:{lineno}: not a JSON object")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def load_accepted(out_dir: Path) -> dict[str, dict[str, Any]]:
    path = out_dir / ACCEPTED_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def task_rows(tasks: list[Task]) -> list[dict[str, Any]]:
    rows = []
    for task in tasks:
        rows.append(
            {
                **task.payload,
                "task_id": task.task_id,
                "kind": task.kind,
                "prompt_path": f"{PROMPTS_DIR}/{task.task_id}.txt",
                "prompt_sha256": task.prompt_sha256,
            }
        )
    return rows


def export_tasks(out_dir: Path, tasks: list[Task]) -> dict[str, int]:
    """Write tasks.jsonl, pending.jsonl and the prompt files; return the counts."""
    ids = [t.task_id for t in tasks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise HandoffError(f"two tasks share a prompt (ids {dupes}); make each question unique")
    prompts = out_dir / PROMPTS_DIR
    prompts.mkdir(parents=True, exist_ok=True)
    wanted = {f"{t.task_id}.txt" for t in tasks}
    for stale in prompts.glob("*.txt"):
        if stale.name not in wanted:
            stale.unlink()
    for task in tasks:
        (prompts / f"{task.task_id}.txt").write_text(task.prompt, encoding="utf-8")
    rows = task_rows(tasks)
    accepted = load_accepted(out_dir)
    pending = [r for r in rows if r["task_id"] not in accepted]
    write_jsonl(out_dir / TASKS_FILE, rows)
    write_jsonl(out_dir / PENDING_FILE, pending)
    return {"tasks": len(rows), "pending": len(pending), "accepted": len(rows) - len(pending)}


def validate_answers(
    answers: list[dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    spec: AnswerSpec,
    extra_check: ExtraCheck | None = None,
) -> dict[str, dict[str, Any]]:
    """Every problem in the answer lines, all at once; the valid answers by task id."""
    problems: list[str] = []
    out: dict[str, dict[str, Any]] = {}
    required = {"task_id": (str,), "prompt_sha256": (str,), "answered_by": (str,), **spec.fields}
    for n, answer in enumerate(answers, start=1):
        where = f"answer {n} ({answer.get('task_id', '?')})"
        missing = [k for k in required if k not in answer]
        if missing:
            problems.append(f"{where}: missing {missing}")
            continue
        wrong = [k for k, types in required.items() if not isinstance(answer[k], types)]
        if wrong:
            problems.append(f"{where}: wrong type for {wrong}")
            continue
        task = tasks.get(answer["task_id"])
        if task is None:
            problems.append(f"{where}: no such task in the current export")
            continue
        if answer["prompt_sha256"] != task["prompt_sha256"]:
            problems.append(f"{where}: prompt_sha256 does not match the exported prompt")
            continue
        if not answer["answered_by"].strip():
            problems.append(f"{where}: answered_by is empty")
            continue
        bad_enum = [
            f"{k}={answer[k]!r}" for k, allowed in spec.enums.items() if answer[k] not in allowed
        ]
        if bad_enum:
            problems.append(f"{where}: not allowed: {bad_enum}")
            continue
        if answer["task_id"] in out:
            problems.append(f"{where}: second answer for the same task")
            continue
        if extra_check is not None:
            extra = extra_check(answer, task)
            if extra:
                problems.extend(f"{where}: {p}" for p in extra)
                continue
        out[answer["task_id"]] = answer
    if problems:
        raise HandoffError("; ".join(problems))
    return out


def import_answers(
    out_dir: Path, spec: AnswerSpec, extra_check: ExtraCheck | None = None
) -> dict[str, dict[str, Any]]:
    """Validate verdicts.jsonl against tasks.jsonl and merge it into accepted.json."""
    verdicts = out_dir / VERDICTS_FILE
    if not verdicts.exists():
        raise HandoffError(f"{verdicts} does not exist: run the workflow on pending.jsonl first")
    tasks = {r["task_id"]: r for r in read_jsonl(out_dir / TASKS_FILE)}
    valid = validate_answers(read_jsonl(verdicts), tasks, spec, extra_check)
    accepted = {k: v for k, v in load_accepted(out_dir).items() if k in tasks}
    accepted.update(valid)
    (out_dir / ACCEPTED_FILE).write_text(
        json.dumps(accepted, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return accepted
