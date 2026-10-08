"""One handoff stage of an image role: export the questions, brief the agents, check and import.

The served-image lane wrote this transport twice (`served_image/vision.py`: a check and a
replacement stage, each with its own export, brief, answer check and import). The image roles of
D17 add five more - the identity verifier and researcher, the prefilter, the "shows this site"
judge and the hero re-check - and each is the same four halves around a different question. This
module is that transport once; a stage module (`prefilter.py`, `depicts.py`, `hero_recheck.py`,
`identity.py`) supplies only a `Spec` (its name, its D6 role, its parser) and its questions.

    export   the stage writes `<handoff>/<batch>/<stage>/<label>.prompt.txt` and the pictures under
             `<handoff>/images/`; the questions are recorded in the run (`Spec.questions_file`,
             written once, the exact prompt text included)
    brief    the instruction of one batch's agent: which files to read, how to check the shape of an
             answer, how to record it - `opus_handoff.py answer --role <the stage's role>`
    check    the shape problem of one answer text, nothing recorded
    import   `opus_handoff.validate` clean, every prompt as exported, every picture as shown, every
             answer recorded in the stage's role by that role's registered model (`roles`), parsed
             by the stage's own parser into `Spec.result_file` (written once)

A stage never calls a model: the agents are the orchestrator's, as for every lane of the repair.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from phase3.fetch_stage import write_once  # noqa: E402
from served_image import state as ST  # noqa: E402

#: Characters of free text an answer field may hold (a note, a basis): long enough for a sentence
#: with a URL, short enough that an agent cannot answer with an essay.
MAX_TEXT = 600


class StageError(ST.StateError):
    """A stage cannot take this step. The problem is printed, never repaired."""


class AnswerShapeError(StageError):
    """An answer that is not in the stage's exact shape."""


@dataclass(frozen=True)
class Image:
    """A picture a question shows: its name, its path relative to the handoff and its sha256."""

    name: str
    path: str
    sha256: str


@dataclass(frozen=True)
class Question:
    """One question: where it sits in the handoff, its exact prompt, what the parser needs to know
    about it (`meta`, JSON) and the pictures it shows."""

    batch_id: str
    label: str
    prompt: str
    meta: Mapping[str, Any] = field(default_factory=dict)
    images: tuple[Image, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "label": self.label,
            "prompt": self.prompt,
            "meta": dict(self.meta),
            "images": [vars(image) for image in self.images],
        }

    @classmethod
    def from_json(cls, record: Mapping[str, Any]) -> Question:
        return cls(
            batch_id=record["batch_id"],
            label=record["label"],
            prompt=record["prompt"],
            meta=dict(record["meta"]),
            images=tuple(Image(**image) for image in record["images"]),
        )


@dataclass(frozen=True)
class Spec:
    """A stage: its handoff stage name, the D6 role that answers it, its files and its parser.

    `parse(meta, text)` returns the parsed answer or raises `AnswerShapeError`; `what` finishes the
    sentence "agent B of the <stage> (...)" in the brief; `web` says whether the agent may research
    on the web (the prompt decides how)."""

    name: str
    role: str
    prompt_id: str
    questions_file: str
    export_file: str
    result_file: str
    parse: Callable[[Mapping[str, Any], str], dict[str, Any]]
    what: str
    web: bool = False


def image_ref(name: str, data: bytes) -> Image:
    """A picture's handoff path and the sha256 of the bytes shown (`OH.image_relpath`)."""
    return Image(name, OH.image_relpath(name), hashlib.sha256(data).hexdigest())


def write_image(handoff: Path, name: str, data: bytes) -> Image:
    """A picture beside the handoff's own images, written once (`write_once`: the same bytes again
    are a no-op, other bytes are refused)."""
    image = image_ref(name, data)
    write_once(handoff / image.path, data, source=f"the export of {name}")
    return image


# ------------------------------------------------------------------------------------ export
def export(
    run: Path,
    handoff: Path,
    spec: Spec,
    questions: Sequence[Question],
    pictures: Mapping[str, bytes],
) -> dict[str, Any]:
    """Write the questions and their pictures. `pictures` is `{image name: bytes}`; every image a
    question names must be in it. Returns the summary also recorded in `spec.export_file`."""
    RO.role(spec.role)
    labels = [(q.batch_id, q.label) for q in questions]
    if len(set(labels)) != len(labels):
        raise StageError(f"{spec.name}: a question is exported twice")
    for question in questions:
        for image in question.images:
            if image.name not in pictures:
                raise StageError(f"{question.batch_id}/{question.label}: no bytes for {image.name}")
            written = write_image(handoff, image.name, pictures[image.name])
            if written != image:
                raise StageError(f"{image.name}: the question names other bytes than were given")
        OH.export(
            handoff,
            batch_id=question.batch_id,
            stage=spec.name,
            label=question.label,
            field=spec.name,
            prompt=question.prompt,
        )
    digest = ST.write_text_once(
        run / spec.questions_file, ST.jsonl_text(q.as_json() for q in questions)
    )
    batches: dict[str, list[str]] = {}
    for question in questions:
        batches.setdefault(question.batch_id, []).append(question.label)
    summary = {
        "handoff": str(handoff),
        "stage": spec.name,
        "role": spec.role,
        "prompt_id": spec.prompt_id,
        "questions": len(questions),
        "questions_sha256": digest,
        "batches": batches,
    }
    ST.write_text_once(run / spec.export_file, ST.json_text(summary))
    return {k: v for k, v in summary.items() if k != "batches"} | {"batches": len(batches)}


def load_questions(run: Path, spec: Spec) -> dict[tuple[str, str], Question]:
    """The recorded questions by `(batch id, label)`."""
    path = run / spec.questions_file
    if not path.is_file():
        raise StageError(f"{path} does not exist - export the stage first")
    out: dict[tuple[str, str], Question] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            question = Question.from_json(json.loads(line))
            out[(question.batch_id, question.label)] = question
    return out


def _record(run: Path, spec: Spec) -> dict[str, Any]:
    path = run / spec.export_file
    if not path.is_file():
        raise StageError(f"{path} does not exist - export the stage first")
    return json.loads(path.read_text(encoding="utf-8"))


# -------------------------------------------------------------------------------- the agent's aids
BRIEF = """You are agent {batch} of the {stage} stage ({what}), running as {model} in the role {role} at effort {effort}. You answer {count} question(s). Answer each one on its own.

Read ONLY your own files: {handoff}/{batch}/MANIFEST.jsonl lists your questions, one JSON line each with its "label" and its "prompt_path" (relative to {handoff}). Each prompt names its picture files under {handoff}/images/ - open every picture with your Read tool, which shows it to you. Open no other file of the repository: no other batch, nothing else under output/ or docs/, no database{named}. {web}

For each question:
1. Read {handoff}/<prompt_path> and look at every picture it names.
2. Decide exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is judged):
   ./.venv/Scripts/python.exe scripts/remediation/image_roles/run.py check-answer --run-dir {run} --handoff {handoff} --stage {stage} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} --stage {stage} --label <label> --answered-by {batch} --model {model} --role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""

WEB_ALLOWED = (
    "Where the prompt asks for it, research on the web - a few requests at most; a 403 or 429 is "
    "never a finding, say so and try another source."
)
CACHE_FILES = " except the cached Wikipedia pages (JSON files) your prompts name"
NO_WEB = "Do not use the web: the pictures and the prompt are all you need."


def _shown(path: Path) -> str:
    return path.resolve().as_posix()


def brief(run: Path, handoff: Path, spec: Spec, batch_id: str) -> str:
    """The instruction of one batch's agent, running as the stage's role (`roles.ROLES`)."""
    _record(run, spec)
    labels = [label for batch, label in load_questions(run, spec) if batch == batch_id]
    if not labels:
        raise StageError(f"{batch_id} is no batch of {spec.name}")
    entry = RO.role(spec.role)
    shown = _shown(handoff)
    return BRIEF.format(
        batch=batch_id,
        stage=spec.name,
        what=spec.what,
        model=entry.model,
        role=spec.role,
        effort=entry.effort,
        count=len(labels),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        web=WEB_ALLOWED if spec.web else NO_WEB,
        named=CACHE_FILES if spec.web else "",
    )


def check_answer(
    run: Path, handoff: Path, spec: Spec, batch_id: str, label: str, text: str
) -> str | None:
    """The shape problem of one answer text, or None. Nothing is recorded."""
    record = _record(run, spec)
    if Path(record["handoff"]).resolve() != handoff.resolve():
        raise StageError(f"{handoff} is not the handoff {spec.name} was exported to")
    question = load_questions(run, spec).get((batch_id, label))
    if question is None:
        raise StageError(f"{batch_id}/{label} is no question of {spec.name}")
    try:
        spec.parse(question.meta, text)
    except AnswerShapeError as exc:
        return str(exc)
    return None


# ------------------------------------------------------------------------------------- import
def import_answers(run: Path, handoff: Path, spec: Spec) -> dict[str, Any]:
    """Every answer of the stage, validated and parsed, into `spec.result_file` (written once).

    Refused, by name: a handoff other than the exported one, a questions file that is not the one
    exported, a validation with missing/stale/malformed/orphan answers, a prompt the manifest does
    not name, a picture that is not the one shown, an answer that is not the stage's role's (its
    `answered_by` names another role or carries another model's stamp) and any answer out of shape
    - all the shape problems at once, none of them repaired."""
    record = _record(run, spec)
    if Path(record["handoff"]).resolve() != handoff.resolve():
        raise StageError(f"{handoff} is not the handoff {spec.name} was exported to")
    if ST.file_sha256(run / spec.questions_file) != record["questions_sha256"]:
        raise StageError(f"{run / spec.questions_file} is not the file the export recorded")
    validation = OH.validate(handoff)
    if not validation.ok:
        raise StageError(
            f"{handoff} does not validate: {len(validation.missing)} missing, "
            f"{len(validation.stale)} stale, {len(validation.malformed)} malformed, "
            f"{len(validation.orphans)} orphan answers - `opus_handoff.py validate --dir {handoff}`"
        )
    manifest = {(m["batch_id"], m["label"]): m for m in OH.manifest(handoff)}
    out: list[dict[str, Any]] = []
    problems: list[str] = []
    for (batch_id, label), question in load_questions(run, spec).items():
        line = manifest.get((batch_id, label))
        if line is None or line["prompt_sha256"] != OH.prompt_sha256(question.prompt):
            raise StageError(f"{batch_id}/{label}: the manifest does not name this prompt")
        for image in question.images:
            shown = handoff / image.path
            if hashlib.sha256(shown.read_bytes()).hexdigest() != image.sha256:
                raise StageError(f"{shown} is not the picture the question showed")
        answer = OH.read_answer(
            handoff, batch_id=batch_id, stage=spec.name, label=label, prompt=question.prompt
        )
        wrong = RO.answer_problem(answer.answered_by, answer.model)
        if wrong is not None:
            raise StageError(f"{batch_id}/{label}: {wrong}")
        if RO.role_of(answer.answered_by) != spec.role:
            raise StageError(
                f"{batch_id}/{label}: answered by {answer.answered_by!r}, not in the role {spec.role}"
            )
        try:
            parsed = spec.parse(question.meta, answer.text)
        except AnswerShapeError as exc:
            problems.append(f"{batch_id}/{label}: {exc}")
            continue
        out.append(
            {
                "batch_id": batch_id,
                "label": label,
                "prompt_id": spec.prompt_id,
                "prompt_sha256": line["prompt_sha256"],
                "answered_by": answer.answered_by,
                "answered_at": answer.answered_at,
                "model": answer.model,
                "meta": dict(question.meta),
                **parsed,
            }
        )
    if problems:
        raise StageError(
            f"{len(problems)} answer(s) are not in shape - delete them and have them answered "
            "again: " + "; ".join(problems[:5])
        )
    digest = ST.write_text_once(run / spec.result_file, ST.jsonl_text(out))
    return {"answers": len(out), "sha256": digest}


def read_results(run: Path, spec: Spec) -> list[dict[str, Any]]:
    """The imported answers of the stage."""
    path = run / spec.result_file
    if not path.is_file():
        raise StageError(f"{path} does not exist - import the stage first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ------------------------------------------------------------------------------------ parsing
def text_field(value: Any, key: str, *, longest: int = MAX_TEXT) -> str:
    """A non-empty string of at most `longest` characters."""
    if not isinstance(value, str) or not value.strip() or len(value) > longest:
        raise AnswerShapeError(
            f"'{key}' must be a non-empty string of at most {longest} characters"
        )
    return value.strip()


def json_object(text: str, keys: frozenset[str]) -> dict[str, Any]:
    """The one JSON object of an answer, with exactly `keys`."""
    from gallery_audit.vision import pilot

    data = pilot.extract_json(text)
    if data is None:
        raise AnswerShapeError("no JSON object in the answer")
    if set(data) != keys:
        raise AnswerShapeError(f"the answer carries {sorted(data)}, not {sorted(keys)}")
    return data
