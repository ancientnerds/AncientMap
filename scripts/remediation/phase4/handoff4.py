"""The answering side of `mass4`'s handoff rounds: a batch agent's brief, one answer's check, and the
batches ready to import.

Owner order 2026-09-23 ("everything with Opus") and decision O11 of 2026-09-26 ("geh doch mal lieber
auf 16 agenten"): the selector (S3) and reviewer (S6) questions a `mass4.py --handoff-export` round
wrote are answered by Opus agents of the orchestrating session, many at once, one agent per batch of
the stage's handoff directory. Batches are independent - a batch's questions name only its own sites,
its answers go into its own folder (`opus_handoff`'s layout), and every agent keeps its scratch files
in its own directory - so any number of agents may answer different batches of one directory at the
same time. What the orchestrator runs in between stays sequential: `opus_handoff.py validate`, then
one `mass4.py --only <ready batches> --handoff-import` round at a time.

    handoff4.py brief        --run-dir R --handoff H --batch-id B
    handoff4.py check-answer --run-dir R --handoff H --batch-id B --label L --text-file F
    handoff4.py ready        --handoff H [--batch B ...]

* `brief` prints the whole instruction of the agent that answers batch B: which files it may read,
  where it writes its drafts (`<handoff>-scratch/<batch>/`), how it checks and records each answer,
  and its own `--answered-by` name (`opus-<handoff directory name>-<batch>`).
* `check-answer` reads one draft through the stage's own parser - `select_stage.parse_selection`
  over the batch's own candidate pool, `review4.parse_review` over the batch's own assembly - so an
  answer the import would refuse (`selection-refused`, `review-unparseable`) is named before it is
  recorded. It first rebuilds the question's prompt from the batch directory and refuses when it is
  no longer the exported one (the batch moved since the export: nothing it says would be what the
  question showed). The review is also checked whole: one line for every shown sentence and one
  CARD line when a card is shown - the import reads a missing line as a DROP, which is its
  fail-closed reading, never a shape an agent should give. It judges no content: the finding is the
  agent's.
* `ready` reads `opus_handoff.validate` per batch: the batches whose every question is answered in
  shape (0 missing, stale, malformed) can be imported alone; stale or malformed answers anywhere, or
  answer files no question asks for, fail it.

Only lanes W and S are open (the translate and restricted stages ask nothing while T and R stay
closed), so only the selector's and the reviewer's questions have a brief. Nothing here calls a
model, opens a socket or writes a file: the agent writes its drafts, and `opus_handoff.py answer`
records them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import opus_handoff as OH  # noqa: E402 - the handoff directory's contract

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402

OPUS_HANDOFF = Path(OH.__file__).resolve()
HANDOFF4 = Path(__file__).resolve()


class HandoffCheckError(ValueError):
    """The question cannot be checked here: not a question of this batch, or not the one exported."""


@dataclass(frozen=True)
class Kind:
    """One model stage whose questions have a brief: its label field and what it asks."""

    field: str
    stage: str
    role: str
    task: str


SELECT = Kind(
    field=B.SELECT_FIELD,
    stage="finder",
    role="the selector (S3)",
    task=(
        "pick, by id, the sentences of the pinned Wikipedia text (and the spans to drop) that "
        "form the site's description and card, or ABSTAIN, exactly as the question says"
    ),
)
REVIEW = Kind(
    field=B.REVIEW_FIELD,
    stage="reviewer",
    role="the reviewer (S6)",
    task=(
        "KEEP or DROP each published sentence and the card, exactly as the question says; the "
        "review can only remove"
    ),
)
KINDS: Mapping[str, Kind] = {kind.field: kind for kind in (SELECT, REVIEW)}


# ------------------------------------------------------------------------------------ the batch


def batch_questions(handoff: Path, batch_id: str) -> list[dict[str, Any]]:
    """The batch's manifest lines, in file order, all of one stage with a brief. A batch that is
    not in the directory, or mixes stages, is refused: one handoff directory per stage per run."""
    lines = list(OH.read_manifest(handoff, batch_id).values())
    if not lines:
        raise HandoffCheckError(f"{batch_id} has no question in {handoff}")
    fields = {line["field"] for line in lines}
    if len(fields) != 1 or next(iter(fields)) not in KINDS:
        raise HandoffCheckError(
            f"{handoff}/{batch_id} asks {sorted(map(str, fields))}: a brief is for one stage of "
            f"{sorted(KINDS)} per handoff directory"
        )
    return lines


def kind_of(lines: Sequence[Mapping[str, Any]]) -> Kind:
    return KINDS[lines[0]["field"]]


def agent_name(handoff: Path, batch_id: str) -> str:
    """The `--answered-by` of the batch's agent: the directory's name and the batch, so every
    answer names the round and the batch it was given (the mass run's `opus-p4m-select-p4-NNNN`)."""
    return f"opus-{handoff.resolve().name}-{batch_id}"


def scratch_dir(handoff: Path, batch_id: str) -> Path:
    """The agent's own drafts: beside the handoff directory, one folder per batch."""
    root = handoff.resolve()
    return root.parent / f"{root.name}-scratch" / batch_id


# ------------------------------------------------------------------------------------ the brief

BRIEF = """You are Opus agent {agent}, {role} of the Phase-4 run {run} (AncientMap sites remediation).
You answer the {count} question(s) of batch {batch}, each about another site: {task}. Answer each
one on its own, as if it were the only one.

Owner order: every model judgement is answered by Opus - you - and your answers are read by the
pipeline's own strict parser and checked by deterministic gates afterwards.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the
repository - no other batch, no answer of another agent, no other file under output/ or docs/, no
database, no git history - and no web page: each prompt holds all the evidence its question may use.

For each line of the manifest:
1. Read {handoff}/<prompt_path> completely (it can be up to about 60 KB: read it in parts, all of it).
2. Answer exactly the question it asks, in exactly the answer format it gives - every line it asks
   for, in its order, nothing else: no preamble, no explanation, no markdown fences.
3. Write the answer text to a new UTF-8 file of your own: {scratch}/<site id>.txt, where <site id> is
   the label's part before "/" (create the directory).
4. Check its shape (the stage's own parser; nothing is judged):
   {python} {handoff4} check-answer --run-dir {run_dir} --handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<site id>.txt
   It prints {{"ok": true}} or the problem. Fix the shape, never the finding. If it says REFUSED,
   stop and report it: the question is not the one you were given.
5. Record it - an answer is written once:
   {python} {opus_handoff} answer --dir {handoff} --batch-id {batch} --stage {stage} --label <label> --answered-by {agent} --text-file {scratch}/<site id>.txt
   It must print "wrote": true. If it refuses, read why and fix your file; never delete or edit an
   answer file, a prompt or a manifest.

Change no other file. When every question of the batch is recorded, report one line per manifest
line: <label> - answered | failed (<reason>).
"""


def brief(run_dir: Path, handoff: Path, batch_id: str) -> str:
    """The whole instruction of the Opus agent that answers one batch of a stage's handoff."""
    lines = batch_questions(handoff, batch_id)
    kind = kind_of(lines)
    batch_dir = run_dir / batch_id
    if not (batch_dir / M.INPUT_FILE).exists():
        raise HandoffCheckError(
            f"{batch_dir}: no batch of the run - check-answer could not read it"
        )
    return BRIEF.format(
        agent=agent_name(handoff, batch_id),
        role=kind.role,
        run=run_dir.resolve().name,
        count=len(lines),
        batch=batch_id,
        task=kind.task,
        handoff=handoff.resolve().as_posix(),
        scratch=scratch_dir(handoff, batch_id).as_posix(),
        python=Path(sys.executable).resolve().as_posix(),
        handoff4=HANDOFF4.as_posix(),
        opus_handoff=OPUS_HANDOFF.as_posix(),
        run_dir=run_dir.resolve().as_posix(),
        stage=kind.stage,
    )


# ------------------------------------------------------------------------------------ the check


def _question(handoff: Path, batch_id: str, label: str) -> dict[str, Any]:
    lines = [line for line in batch_questions(handoff, batch_id) if line["label"] == label]
    if len(lines) != 1:
        raise HandoffCheckError(f"{batch_id}/{label} is no question of {handoff}")
    return lines[0]


def _exported(line: Mapping[str, Any], prompt: str) -> None:
    if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
        raise HandoffCheckError(
            f"{line['batch_id']}/{line['label']}: the batch directory no longer builds the exported "
            "prompt (it moved since the export); nothing checked against it would be what the "
            "question showed"
        )


def check_selection(
    batch_dir: Path, line: Mapping[str, Any], site_id: str, text: str
) -> str | None:
    """The selector's answer through `select_stage.parse_selection` over the site's own pool."""
    _, sites = B.read_batch(batch_dir)
    by_id = {site.site_id: site for site in sites}
    if site_id not in by_id:
        raise HandoffCheckError(f"{batch_dir.name}: {site_id} is no site of the batch")
    site = by_id[site_id]
    lane = B.read_lanes(batch_dir, sites)[site_id]
    source_id, meta, source_text, pool = SEL.site_pool(batch_dir, site, lane)
    prompt = SEL.site_selector_prompt(batch_dir, site, source_id, meta, pool, source_text)
    _exported(line, prompt.render())
    try:
        SEL.parse_selection(site_id, text, pool)
    except M.SelectionRefused as exc:
        return f"selection-refused: {exc}"
    return None


def review_lines_problem(verdict: RV.Verdict, *, sentences: int, card: bool) -> str | None:
    """A review read whole: one line per shown sentence and one CARD line when a card is shown. The
    import reads a missing or a second line as a DROP (fail-closed); an agent gives neither."""
    numbers: list[int] = []
    cards = 0
    for line in verdict.lines:
        found = RV._LINE.fullmatch(line)
        if found is None:
            return f"a line in no contract shape: {line[:120]!r}"
        if found["card"] is not None:
            cards += 1
        else:
            numbers.append(int(found["number"]))
    wanted = list(range(1, sentences + 1))
    if sorted(numbers) != wanted:
        return f"the lines name sentences {sorted(numbers)}; give R1 .. R{sentences}, each once"
    if cards != (1 if card else 0):
        return f"{cards} CARD line(s); give {'exactly one' if card else 'none (no card is shown)'}"
    return None


def check_review(batch_dir: Path, line: Mapping[str, Any], site_id: str, text: str) -> str | None:
    """The reviewer's answer through `review4.parse_review` over the site's own assembly."""
    _, inputs = A.batch_inputs(batch_dir)
    found = [item for item in inputs if item.site.site_id == site_id]
    if len(found) != 1:
        raise HandoffCheckError(f"{batch_dir.name}: {site_id} is no assembled site of the batch")
    built = A.build_site(found[0], run=B.run_name(batch_dir))
    _exported(line, RV.reviewer_prompt(found[0], built).render())
    card = built.assembly.card is not None
    try:
        verdict = RV.parse_review(text, sentences=len(built.sentences), card=card)
    except RV.ReviewUnparseable as exc:
        return f"review-unparseable: {exc}"
    return review_lines_problem(verdict, sentences=len(built.sentences), card=card)


def check_answer(run_dir: Path, handoff: Path, batch_id: str, label: str, text: str) -> str | None:
    """The shape problem of one answer text, or `None`. Refused (`HandoffCheckError`): a label that
    is no question of the batch, a batch the run does not have, a question whose prompt the batch
    no longer builds."""
    line = _question(handoff, batch_id, label)
    site_id, _, field = label.partition("/")
    if field != line["field"]:
        raise HandoffCheckError(f"{label}: the label's field is not the question's {line['field']}")
    batch_dir = run_dir / batch_id
    if not (batch_dir / M.INPUT_FILE).exists():
        raise HandoffCheckError(f"{batch_dir}: no batch of the run")
    if not text.strip():
        return "an empty answer is not an answer"
    if line["field"] == SELECT.field:
        return check_selection(batch_dir, line, site_id, text)
    return check_review(batch_dir, line, site_id, text)


# ------------------------------------------------------------------------------------ ready


def ready(handoff: Path, batches: Sequence[str] = ()) -> dict[str, Any]:
    """Per batch of the directory: its questions and what `opus_handoff.validate` says of them. A
    batch is ready when every question is answered in shape; `ok` is false while any answer is
    stale or malformed, an answer file no question asks for lies there, or a named batch is not
    ready (or not there)."""
    result = OH.validate(handoff)
    per: dict[str, dict[str, int]] = {}
    for status, entries in (
        ("answered", result.answered),
        ("missing", result.missing),
        ("stale", result.stale),
        ("malformed", result.malformed),
    ):
        for entry in entries:
            counts = per.setdefault(
                entry["batch_id"], {"answered": 0, "missing": 0, "stale": 0, "malformed": 0}
            )
            counts[status] += 1
    done = sorted(b for b, c in per.items() if c["missing"] == c["stale"] == c["malformed"] == 0)
    unknown = sorted(set(batches) - set(per))
    waiting = sorted(set(batches) - set(done))
    return {
        "ok": not (result.stale or result.malformed or result.orphans or waiting),
        "ready": done,
        "not_ready": {b: c for b, c in sorted(per.items()) if b not in done},
        "named_not_ready": waiting,
        "named_unknown": unknown,
        "stale": result.stale,
        "malformed": result.malformed,
        "orphans": result.orphans,
    }


# ------------------------------------------------------------------------------------ the CLI


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="handoff4", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("brief", "the whole instruction of one batch's Opus agent"),
        ("check-answer", "the shape of one answer text, before it is recorded"),
    ):
        command = sub.add_parser(name, help=text)
        command.add_argument("--run-dir", required=True, type=Path)
        command.add_argument("--handoff", required=True, type=Path)
        command.add_argument("--batch-id", required=True)
    sub.choices["check-answer"].add_argument("--label", required=True)
    sub.choices["check-answer"].add_argument("--text-file", required=True, type=Path)
    batches = sub.add_parser("ready", help="the batches whose every question is answered in shape")
    batches.add_argument("--handoff", required=True, type=Path)
    batches.add_argument("--batch", action="append", default=[], help="a batch that must be ready")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """0: the brief, a clean answer, every named batch ready. 1: a shape problem or a batch not
    ready. 2: refused (`REFUSED:` on stderr) - the question cannot be checked here."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "brief":
            print(brief(args.run_dir, args.handoff, args.batch_id))
            return 0
        if args.command == "check-answer":
            text = args.text_file.read_bytes().decode("utf-8")
            problem = check_answer(args.run_dir, args.handoff, args.batch_id, args.label, text)
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        payload = ready(args.handoff, args.batch)
        _print(payload)
        return 0 if payload["ok"] else 1
    except (HandoffCheckError, OH.HandoffError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
