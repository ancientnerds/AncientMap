"""The Opus handoff: every model judgement of the remediation is answered by an Opus agent of the
orchestrating Claude Code session, through files - never by a model API called from this code.

Owner order, 2026-09-23 (Martin): "no DeepSeek any more - everything with Opus". Until then the
Phase-3 finder and reviewer, the Phase-4 selector, translator, restricted-lane and reviewer calls
and the gallery vision questions were bought from `opencode-go/deepseek-v4.1-flash` (one Pi process
per call) and `deepseek-v4-flash-vision-exp` (the opencode gateway). Both transports are gone. A
stage now runs in two halves with the answering in between, done by the orchestrator:

    export   the stage computes the calls it would buy - the exact prompt text, unchanged, so the
             frozen questions stay frozen - and writes them here. No model is called.
    answer   Opus agents read `<batch>/<stage>/<label>.prompt.txt` (and the image, for vision) and
             write `<label>.answer.json`, normally through `answer` below.
    validate every exported question has an answer of the right shape, for the exact prompt, by
             `OPUS_MODEL` - checked before anything is imported.
    import   the stage runs again and reads each answer instead of buying it; every other rule of
             the stage (ledger line first, write-once answers, holds, gates) is unchanged.

The directory, one per round (it may be shared across batches and stages):

    <dir>/<batch_id>/MANIFEST.jsonl                    one line per exported question
    <dir>/<batch_id>/<stage>/<label>.prompt.txt        the exact prompt, UTF-8
    <dir>/<batch_id>/<stage>/<label>.answer.json       the answer (`ANSWER_KEYS`)
    <dir>/images/<name>.jpg                            the vision lane's exact image bytes

`<label>` is the call's label escaped as the evidence store escapes it (`quote(label, safe="")`,
`phase3.fetch_stage.EvidenceStore.slug`). The stage is a path component because the Phase-3 finder
and reviewer ask about the same `<site>/<field>` label. A manifest line is
`{batch_id, stage, label, field, prompt_sha256, prompt_path, answer_path, image_path}`, the paths
relative to `<dir>` with `/`. One manifest per batch, so parallel exports of different batches never
write one file.

Usage (the orchestrator's side):

    python scripts/remediation/opus_handoff.py validate --dir DIR
    python scripts/remediation/opus_handoff.py answer --dir DIR --batch-id B --stage S --label L \\
        --answered-by AGENT --text-file ANSWER.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase3.fetch_stage import write_once  # noqa: E402 - the evidence store's one write rule
from phase3.ledger import utc_now  # noqa: E402 - the ledger's clock, at the ledger's precision

#: The model every answer, ledger line and disclosure of the remediation names from 2026-09-23 on.
#: One string, pinned by a test: the Opus agents of the orchestrating Claude Code session.
OPUS_MODEL = "anthropic/claude-opus-5-5 (Claude Code agent)"

MANIFEST_FILE = "MANIFEST.jsonl"
PROMPT_SUFFIX = ".prompt.txt"
ANSWER_SUFFIX = ".answer.json"
#: The vision lane's images live beside the batches, so no batch may take this name.
IMAGES_DIR = "images"
IMAGE_SUFFIX = ".jpg"

ANSWER_KEYS = frozenset({"prompt_sha256", "text", "model", "answered_at", "answered_by"})
MANIFEST_KEYS = frozenset(
    {
        "batch_id",
        "stage",
        "label",
        "field",
        "prompt_sha256",
        "prompt_path",
        "answer_path",
        "image_path",
    }
)

#: A batch id, a stage and an image name become path components, so they are refused unless they
#: are one plain name: no separator, no `..`, nothing a path could climb out through.
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class HandoffError(ValueError):
    """The handoff directory cannot give this answer, or cannot take this export. Never guessed."""


def prompt_sha256(prompt: str) -> str:
    """The sha256 of the exact prompt text, UTF-8: what an answer names to say which prompt it read."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _component(value: str, what: str) -> str:
    if not _COMPONENT.fullmatch(value) or ".." in value:
        raise HandoffError(f"{what} {value!r} is not one plain path name")
    return value


def _batch_component(batch_id: str) -> str:
    _component(batch_id, "batch id")
    if batch_id == IMAGES_DIR:
        raise HandoffError(f"batch id {batch_id!r} is the vision lane's image directory")
    return batch_id


def _relative(batch_id: str, stage: str, label: str, suffix: str) -> str:
    if not label:
        raise HandoffError("a question needs its label")
    escaped = quote(label, safe="")
    return f"{_batch_component(batch_id)}/{_component(stage, 'stage')}/{escaped}{suffix}"


def prompt_relpath(batch_id: str, stage: str, label: str) -> str:
    return _relative(batch_id, stage, label, PROMPT_SUFFIX)


def answer_relpath(batch_id: str, stage: str, label: str) -> str:
    return _relative(batch_id, stage, label, ANSWER_SUFFIX)


def image_relpath(name: str) -> str:
    return f"{IMAGES_DIR}/{_component(name, 'image name')}{IMAGE_SUFFIX}"


# ------------------------------------------------------------------------------------ the manifest


def _manifest_line(row: Any, where: str) -> dict[str, Any]:
    """One manifest line, in exactly its shape."""
    if not isinstance(row, dict) or set(row) != MANIFEST_KEYS:
        raise HandoffError(f"{where}: not a manifest line: {row!r}")
    for key in ("batch_id", "stage", "label", "prompt_sha256", "prompt_path", "answer_path"):
        if not isinstance(row[key], str) or not row[key]:
            raise HandoffError(f"{where}: {key} is not a non-empty string")
    if row["field"] is not None and not isinstance(row["field"], str):
        raise HandoffError(f"{where}: field is neither a string nor null")
    if row["image_path"] is not None and not isinstance(row["image_path"], str):
        raise HandoffError(f"{where}: image_path is neither a string nor null")
    if not _SHA256.fullmatch(row["prompt_sha256"]):
        raise HandoffError(f"{where}: prompt_sha256 is not a sha256")
    if row["prompt_path"] != prompt_relpath(row["batch_id"], row["stage"], row["label"]):
        raise HandoffError(f"{where}: prompt_path is not the path of its own label")
    if row["answer_path"] != answer_relpath(row["batch_id"], row["stage"], row["label"]):
        raise HandoffError(f"{where}: answer_path is not the path of its own label")
    return row


def read_manifest(root: Path, batch_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """`(stage, label) -> manifest line` of one batch. Absent is empty; a damaged line raises."""
    path = root / _batch_component(batch_id) / MANIFEST_FILE
    if not path.exists():
        return {}
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        where = f"{path}:{number}"
        try:
            row = _manifest_line(json.loads(raw), where)
        except json.JSONDecodeError as exc:
            raise HandoffError(f"{where}: not JSON: {exc}") from exc
        if row["batch_id"] != batch_id:
            raise HandoffError(f"{where}: a line of batch {row['batch_id']!r} in {batch_id}'s")
        key = (row["stage"], row["label"])
        if key in lines:
            raise HandoffError(f"{where}: {key} is listed twice")
        lines[key] = row
    return lines


def manifest(root: Path) -> list[dict[str, Any]]:
    """Every manifest line of the directory, batch by batch in name order, each in file order."""
    if not root.is_dir():
        raise HandoffError(f"{root} is not a handoff directory")
    rows: list[dict[str, Any]] = []
    for batch in sorted(p for p in root.iterdir() if p.is_dir() and p.name != IMAGES_DIR):
        rows.extend(read_manifest(root, batch.name).values())
    return rows


def export(
    root: Path,
    *,
    batch_id: str,
    stage: str,
    label: str,
    field: str | None,
    prompt: str,
    image_name: str | None = None,
    image: bytes | None = None,
) -> bool:
    """Write one question: its prompt file (and image), then its manifest line. No model call.

    Idempotent: the same prompt for the same `(batch, stage, label)` again is a no-op (`False`). A
    different prompt for a question already exported is refused - an answer on disk may be the
    answer to the first one - and so are different bytes over an exported prompt or image
    (`write_once`). `True` when a new line was written.
    """
    if not prompt.strip():
        raise HandoffError(f"{batch_id}/{stage}/{label}: an empty prompt is no question")
    if (image_name is None) != (image is None):
        raise HandoffError(f"{batch_id}/{stage}/{label}: an image needs its name and its bytes")
    digest = prompt_sha256(prompt)
    prompt_path = prompt_relpath(batch_id, stage, label)
    image_path = None if image_name is None else image_relpath(image_name)
    existing = read_manifest(root, batch_id).get((stage, label))
    if existing is not None and (
        existing["prompt_sha256"] != digest or existing["image_path"] != image_path
    ):
        raise HandoffError(
            f"{batch_id}/{stage}/{label} was exported with prompt {existing['prompt_sha256'][:16]} "
            f"and image {existing['image_path']!r}; this export has {digest[:16]} and "
            f"{image_path!r}. An exported question is never replaced: use a new handoff directory"
        )
    write_once(root / prompt_path, prompt.encode("utf-8"), source=f"the export of {label}")
    if image_path is not None and image is not None:
        write_once(root / image_path, image, source=f"the export of {label}")
    if existing is not None:
        return False
    line = {
        "batch_id": batch_id,
        "stage": stage,
        "label": label,
        "field": field,
        "prompt_sha256": digest,
        "prompt_path": prompt_path,
        "answer_path": answer_relpath(batch_id, stage, label),
        "image_path": image_path,
    }
    path = root / batch_id / MANIFEST_FILE
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return True


# ------------------------------------------------------------------------------------- the answers


@dataclass(frozen=True)
class Answer:
    """One answer as the stage reads it: the text, verbatim, and who wrote it when."""

    text: str
    answered_by: str
    answered_at: str


def _answer_problem(data: Any, digest: str) -> str | None:
    """Why `data` is not an answer to the prompt whose sha256 is `digest`, or `None`."""
    if not isinstance(data, dict) or set(data) != ANSWER_KEYS:
        keys = sorted(data) if isinstance(data, dict) else type(data).__name__
        return f"malformed: carries {keys}, not {sorted(ANSWER_KEYS)}"
    for key in sorted(ANSWER_KEYS):
        if not isinstance(data[key], str):
            return f"malformed: {key} is not a string"
    if not data["text"].strip():
        return "malformed: the text is empty - an empty answer is not an answer"
    if not data["answered_by"].strip():
        return "malformed: answered_by names nobody"
    try:
        when = datetime.fromisoformat(data["answered_at"])
    except ValueError:
        return f"malformed: answered_at {data['answered_at']!r} is not an ISO 8601 time"
    if when.tzinfo is None:
        return f"malformed: answered_at {data['answered_at']!r} carries no time zone"
    if data["model"] != OPUS_MODEL:
        return f"wrong model: answered by {data['model']!r}, not {OPUS_MODEL!r}"
    if data["prompt_sha256"] != digest:
        return (
            f"stale: the answer names prompt {data['prompt_sha256'][:16]}, the question is "
            f"{digest[:16]}"
        )
    return None


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HandoffError(f"{path}: malformed: not JSON ({exc})") from exc


def read_answer(root: Path, *, batch_id: str, stage: str, label: str, prompt: str) -> Answer:
    """The answer to exactly `prompt`, or `HandoffError` naming why there is none.

    Refused: no answer file; a file that is not the answer shape (`ANSWER_KEYS`, strings, an ISO
    time with a zone); an empty text; a model that is not `OPUS_MODEL`; an answer to another prompt
    (its `prompt_sha256` is not the sha256 of `prompt`). Nothing is defaulted.
    """
    path = root / answer_relpath(batch_id, stage, label)
    if not path.exists():
        raise HandoffError(
            f"{batch_id}/{stage}/{label}: no answer at {path} - export it, have it answered, "
            "validate, then import"
        )
    data = _load(path)
    problem = _answer_problem(data, prompt_sha256(prompt))
    if problem is not None:
        raise HandoffError(f"{path}: {problem}")
    return Answer(
        text=data["text"], answered_by=data["answered_by"], answered_at=data["answered_at"]
    )


def write_answer(
    root: Path,
    *,
    batch_id: str,
    stage: str,
    label: str,
    text: str,
    answered_by: str,
    now: Callable[[], str] = utc_now,
) -> bool:
    """Write the answer to an exported question, naming the prompt file's own sha256.

    The helper the Opus agents answer through, so no agent has to compute a digest: the question
    must be in the manifest, its prompt file must still hash to the manifest's digest, and the
    answer is write-once (`False` for the identical answer again; different bytes are refused -
    delete the file to answer again).
    """
    line = read_manifest(root, batch_id).get((stage, label))
    if line is None:
        raise HandoffError(f"{batch_id}/{stage}/{label} was never exported to {root}")
    prompt = (root / line["prompt_path"]).read_bytes().decode("utf-8")
    if prompt_sha256(prompt) != line["prompt_sha256"]:
        raise HandoffError(f"{root / line['prompt_path']} is not the prompt the manifest names")
    data = {
        "prompt_sha256": line["prompt_sha256"],
        "text": text,
        "model": OPUS_MODEL,
        "answered_at": now(),
        "answered_by": answered_by,
    }
    problem = _answer_problem(data, line["prompt_sha256"])
    if problem is not None:
        raise HandoffError(f"{batch_id}/{stage}/{label}: {problem}")
    path = root / line["answer_path"]
    if path.exists():
        stored = _load(path)
        if _answer_problem(stored, line["prompt_sha256"]) is None and stored["text"] == text:
            return False
        raise HandoffError(
            f"{path} already holds another answer; an answer is written once - delete the file "
            "to answer this question again"
        )
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    return write_once(path, body.encode("utf-8"), source=f"the answer of {answered_by}")


# ------------------------------------------------------------------------------------ the validator


@dataclass
class Validation:
    """What the orchestrator checks after the agents wrote and before anything is imported."""

    answered: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)
    malformed: list[dict[str, Any]] = field(default_factory=list)
    #: Answer files no manifest line asks for: an answer to a question nobody exported here.
    orphans: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.stale or self.malformed or self.orphans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "questions": len(self.answered)
            + len(self.missing)
            + len(self.stale)
            + len(self.malformed),
            "answered": len(self.answered),
            "missing": self.missing,
            "stale": self.stale,
            "malformed": self.malformed,
            "orphans": self.orphans,
        }


def _entry(line: Mapping[str, Any], why: str | None = None) -> dict[str, Any]:
    entry = {
        key: line[key]
        for key in ("batch_id", "stage", "label", "prompt_path", "answer_path", "image_path")
    }
    if why is not None:
        entry["why"] = why
    return entry


def validate(root: Path) -> Validation:
    """Every manifest line against its files: the prompt as exported, the image, the answer."""
    result = Validation()
    asked: set[str] = set()
    for line in manifest(root):
        asked.add(line["answer_path"])
        prompt = root / line["prompt_path"]
        if (
            not prompt.exists()
            or prompt_sha256(prompt.read_bytes().decode("utf-8")) != line["prompt_sha256"]
        ):
            result.malformed.append(_entry(line, "the exported prompt file is missing or changed"))
            continue
        if line["image_path"] is not None and not (root / line["image_path"]).exists():
            result.malformed.append(_entry(line, "the exported image is missing"))
            continue
        path = root / line["answer_path"]
        if not path.exists():
            result.missing.append(_entry(line))
            continue
        try:
            problem = _answer_problem(_load(path), line["prompt_sha256"])
        except HandoffError as exc:
            problem = str(exc)
        if problem is None:
            result.answered.append(_entry(line))
        elif problem.startswith("stale"):
            result.stale.append(_entry(line, problem))
        else:
            result.malformed.append(_entry(line, problem))
    for path in sorted(root.glob(f"*/*/*{ANSWER_SUFFIX}")):
        relative = path.relative_to(root).as_posix()
        if relative not in asked:
            result.orphans.append(relative)
    return result


# ------------------------------------------------------------------------------------------ the CLI


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="opus-handoff", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="every exported question answered, in shape, by Opus")
    check.add_argument("--dir", required=True)
    answer = sub.add_parser("answer", help="write one answer to an exported question")
    answer.add_argument("--dir", required=True)
    answer.add_argument("--batch-id", required=True)
    answer.add_argument("--stage", required=True)
    answer.add_argument("--label", required=True)
    answer.add_argument("--answered-by", required=True, help="the answering agent's name")
    answer.add_argument("--text-file", required=True, help="the answer text, UTF-8, verbatim")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.dir)
    if args.command == "validate":
        result = validate(root)
        _print(result.to_dict())
        return 0 if result.ok else 1
    wrote = write_answer(
        root,
        batch_id=args.batch_id,
        stage=args.stage,
        label=args.label,
        text=Path(args.text_file).read_bytes().decode("utf-8"),
        answered_by=args.answered_by,
    )
    _print({"answer_path": answer_relpath(args.batch_id, args.stage, args.label), "wrote": wrote})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
