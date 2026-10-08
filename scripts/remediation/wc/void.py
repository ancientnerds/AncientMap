"""`verify-void`: move the MiniMax-answered verification answers of a lane WC run aside, so that a
Claude agent answers the same questions and the round is imported again (owner decision D10 of
2026-10-08, master plan X6: a MiniMax answer is never ground truth).

A verification round is written once: `verify-export` refuses an exported round, `verify-import`
refuses an imported one, and every later round was asked about the text this one left. So a round
that holds a MiniMax answer cannot be corrected by hand; this is the one tested way to take it back:

* the first round (`verify`, `verify2`) with a MiniMax answer is **voided from there on**;
* in that round only the MiniMax answers move (to `<handoff>.void-<tag>/`, the same
  `<batch>/<stage>/<label>.answer.json` layout, byte for byte); the Claude answers of the round stay
  and are not asked again; the questions, the manifest and the prompts stay, so the same prompts
  are answered by Claude and `validate` finds exactly the missing answers;
* its `VERIFIED.jsonl`, if the round was imported, is renamed `VERIFIED.jsonl.void` - the import runs
  again over the answers, the Claude ones included;
* every later round asked about the text this round left, so it is taken back whole: its
  `ROUND.json` goes to `<run>/verify/void-<tag>/`, its `VERIFIED.jsonl` becomes `.void`, its handoff
  directory is archived as `<handoff>.void-<tag>` (the next `verify-export` names a fresh one).
  A later round that holds a Claude answer is **refused**: taking it back would archive that answer.

Each answer's stamp is read from the answer file itself (`model`, never the agent's name: the
2026-10-01 census found 8,471 answers stamped Opus that Sonnet had written, and the MiniMax answers
of 2026-10-03 to 2026-10-07 carry `opus-wc-verify-...` names). A Claude answer is never moved; an
answer file that cannot be read stops the command. A run that was built is refused: its plan rests on
the answers. The command is a dry run unless `--apply` is given; an applied void writes
`<run>/verify/VOID-<tag>.json` (what moved, with the sha256 of each file) and refuses a tag used.

    python scripts/remediation/wc/cli.py verify-void --run-dir R             # the dry run
    python scripts/remediation/wc/cli.py verify-void --run-dir R --apply [--tag T]
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_REMEDIATION = Path(__file__).resolve().parents[1]
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

import opus_handoff as OH  # noqa: E402
import run_files as RF  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
#: The verification rounds, in order (`wc4.VERIFY_STAGES`); not imported from there so that this
#: module does not pull the whole lane in, and pinned to it by `tests/remediation/test_wc_void.py`.
VERIFY_STAGES = ("verify", "verify2")
VERIFY_DIR = "verify"
ROUND_FILE = "ROUND.json"
VERIFIED_FILE = "VERIFIED.jsonl"
VOID_SUFFIX = ".void"
#: What a built run holds: its outcomes rest on the verification answers.
BUILT_FILES = ("FINAL.jsonl", "SUMMARY.json", "WC4.jsonl")
JUDGE_DIR = "judge"


class VoidError(ValueError):
    """The run cannot be voided as asked. Nothing was moved."""


@dataclass(frozen=True)
class Answer:
    """One recorded answer of a verification round, with the stamp its file carries."""

    round: int
    batch: str
    label: str
    path: Path
    model: str
    answered_by: str
    sha256: str


@dataclass(frozen=True)
class Round:
    number: int
    stage: str
    handoff: Path
    handoff_shown: str
    round_file: Path
    verified: Path
    imported: bool
    questions: int
    answers: tuple[Answer, ...]

    @property
    def minimax(self) -> tuple[Answer, ...]:
        return tuple(a for a in self.answers if a.model == OH.MINIMAX_MODEL)

    @property
    def claude(self) -> tuple[Answer, ...]:
        return tuple(a for a in self.answers if a.model != OH.MINIMAX_MODEL)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_round(run: Path, number: int, base: Path) -> Round | None:
    folder = run / VERIFY_DIR / f"round-{number}"
    round_file = folder / ROUND_FILE
    if not round_file.exists():
        return None
    record = json.loads(round_file.read_text(encoding="utf-8"))
    handoff = base / record["handoff"]
    answers: list[Answer] = []
    questions = 0
    for batch, labels in record["batches"].items():
        for label in labels:
            questions += 1
            path = handoff / OH.answer_relpath(batch, record["stage"], label)
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                model, by = data["model"], data["answered_by"]
            except (ValueError, KeyError) as exc:
                raise VoidError(
                    f"{path}: the answer file cannot be read ({exc!r}): nothing moved"
                ) from exc
            if model not in OH.ANSWER_MODELS.values():
                raise VoidError(f"{path}: stamp {model!r} is none of ANSWER_MODELS: nothing moved")
            answers.append(Answer(number, batch, label, path, model, by, _sha256(path)))
    return Round(
        number=number,
        stage=record["stage"],
        handoff=handoff,
        handoff_shown=record["handoff"],
        round_file=round_file,
        verified=folder / VERIFIED_FILE,
        imported=(folder / VERIFIED_FILE).exists(),
        questions=questions,
        answers=tuple(answers),
    )


def read_rounds(run: Path, base: Path) -> list[Round]:
    """Every verification round the run exported, in order, with the stamp of each recorded answer."""
    rounds: list[Round] = []
    for number in range(1, len(VERIFY_STAGES) + 1):
        found = _read_round(run, number, base)
        if found is None:
            break
        rounds.append(found)
    return rounds


@dataclass(frozen=True)
class Plan:
    """What voiding a run does: the rounds as read, the first round with a MiniMax answer
    (`void_from`, `None` when no round holds one), the answers of that round that move and the later
    rounds that are taken back whole."""

    run: Path
    rounds: tuple[Round, ...]
    void_from: Round | None
    moves: tuple[Answer, ...]
    taken_back: tuple[Round, ...]

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "round": r.number,
                "stage": r.stage,
                "handoff": r.handoff_shown,
                "questions": r.questions,
                "answers": len(r.answers),
                "minimax": len(r.minimax),
                "claude": len(r.claude),
                "imported": r.imported,
            }
            for r in self.rounds
        ]

    def answers_voided(self) -> list[Answer]:
        """Every answer the void takes away: the first round's MiniMax ones and all of the later rounds'."""
        return [*self.moves, *(a for r in self.taken_back for a in r.answers)]


def plan(run: Path, *, base: Path = REPO) -> Plan:
    """What voiding the run would do. Raises `VoidError` for a run that cannot be voided."""
    built = [name for name in BUILT_FILES if (run / name).exists()]
    if (run / JUDGE_DIR / ROUND_FILE).exists():
        built.append(JUDGE_DIR)
    if built:
        raise VoidError(
            f"{run} was built ({', '.join(built)}): its plan rests on the verification answers - a "
            "built run is not voided"
        )
    rounds = tuple(read_rounds(run, base))
    if not rounds:
        raise VoidError(f"{run}: no verification round was exported")
    first = next((r for r in rounds if r.minimax), None)
    if first is None:
        return Plan(run, rounds, None, (), ())
    later = tuple(r for r in rounds if r.number > first.number)
    for r in later:
        if r.claude:
            raise VoidError(
                f"round {r.number} ({r.stage}) holds {len(r.claude)} Claude answer(s): voiding round "
                f"{first.number} takes round {r.number} back whole and would archive them - a Claude "
                "answer is never voided; decide by hand which round stands"
            )
    return Plan(run, rounds, first, first.minimax, later)


def _tag(tag: str | None, now: Callable[[], str]) -> str:
    stamp = tag or datetime.fromisoformat(now()).strftime("%Y%m%dT%H%M%SZ")
    OH._component(stamp, "void tag")
    return stamp


def _archive(handoff: Path, stamp: str) -> Path:
    return handoff.with_name(f"{handoff.name}.void-{stamp}")


def verify_void(
    run: Path,
    *,
    base: Path = REPO,
    apply: bool = False,
    tag: str | None = None,
    now: Callable[[], str] = RF.now,
) -> dict[str, Any]:
    """Void the MiniMax verification answers of `run` (see the module docstring). A dry run unless
    `apply`; the dry run and the applied run report the same counts."""
    found = plan(run, base=base)
    report: dict[str, Any] = {
        "run": str(run),
        "applied": False,
        "void_from": None if found.void_from is None else found.void_from.number,
        "rounds": found.summary(),
        "answers_to_void": len(found.answers_voided()),
        "rounds_taken_back": [r.number for r in found.taken_back],
    }
    if found.void_from is None or not apply:
        return report
    stamp = _tag(tag, now)
    record_path = run / VERIFY_DIR / f"VOID-{stamp}.json"
    void_run = run / VERIFY_DIR / f"void-{stamp}"
    archives = {r.number: _archive(r.handoff, stamp) for r in (found.void_from, *found.taken_back)}
    renames = [
        r.verified.with_name(VERIFIED_FILE + VOID_SUFFIX)
        for r in (found.void_from, *found.taken_back)
    ]
    for used in (record_path, void_run, *archives.values(), *renames):
        if used.exists():
            raise VoidError(f"{used} exists: a void is taken once per round")
    record = {
        "run": str(run),
        "tag": stamp,
        "void_from": found.void_from.number,
        "rounds": found.summary(),
        "rounds_taken_back": [r.number for r in found.taken_back],
        "archives": {str(number): str(path) for number, path in sorted(archives.items())},
        "answers": [
            {
                "round": a.round,
                "batch": a.batch,
                "label": a.label,
                "model": a.model,
                "answered_by": a.answered_by,
                "sha256": a.sha256,
            }
            for a in found.answers_voided()
        ],
    }
    # the intent first, with every file's hash: a command that stops half way leaves it
    RF.write_json(record_path, {**record, "at": now(), "status": "applying"})
    first = found.void_from
    for answer in found.moves:
        target = archives[first.number] / answer.path.relative_to(first.handoff)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(answer.path), str(target))
        if _sha256(target) != answer.sha256:
            raise VoidError(f"{target}: the moved file's bytes differ from {answer.path}")
    void_run.mkdir(parents=True)
    for r in (first, *found.taken_back):
        if r.verified.exists():
            r.verified.rename(r.verified.with_name(VERIFIED_FILE + VOID_SUFFIX))
    for r in found.taken_back:
        shutil.move(str(r.round_file), str(void_run / f"round-{r.number}-{ROUND_FILE}"))
        shutil.move(str(r.handoff), str(archives[r.number]))
    RF.write_json(record_path, {**record, "at": now(), "status": "applied"})
    return {**report, "applied": True, "tag": stamp, "record": str(record_path)}
