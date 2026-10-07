"""The vision answers of this lane, one `mcode exec` run per question.

Owner decision 2026-10-03: every model judgement of the remediation runs on MiniMax Code
(`mcode`, model `MiniMax-M3.1-Flash-Preview`). Measured on 2026-10-04 23:50: a run opens the
picture a question names with its own Read tool and reads it - the probe's answer for
`replace-g-58627.jpg` ("19th-century watercolor of travellers, a rider and a dog at a desert
waystation building") is the same reading the orchestrating session makes. So a run's own context
holds the pictures, and the 244 questions do not have to fit into one session.

Nothing here judges. A run is a prompt in and an answer file out; `vision.parse` decides whether
that file is an answer to *this* question, and `opus_handoff.write_answer` records it stamped with
the model the run's own JSON names - never with a constant. A run that names another model, or left
no file, is reported as unanswered and nothing is recorded.

`pipeline.studio.mcode` is used as it is: the run, the parallelism (O22), the weekly stop (O20)
and the guard that a run wrote into the repository instead of into its answer file. None of that
is reimplemented here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402 - the handoff that records the answer

from pipeline.studio import mcode  # noqa: E402 - the one place that shells out to mcode
from pipeline.studio.errors import StudioError  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

#: The prompt of one run. It points at the question's own prompt file, its pictures and the one
#: file the answer belongs in; no other file of the repository is to be read or written.
ANSWER_PROMPT = """You answer one question of the served-image check ({stage}). You run as \
{answer_model}. Answer it on your own.

1. Read {prompt_path} with your Read tool. It is the question, verbatim.
2. Open every picture it names with your Read tool, which shows it to you. Open no other file of
   the repository and change no file in it. Where the question allows it, research on the web.
3. Write your answer - only the JSON object the question specifies, nothing else - to this file,
   UTF-8, as its whole content: {answer_path}
4. Check the shape with this command and fix the shape if it names a problem (never the finding):
   {check}
5. Reply with one line saying how many candidates you judged. The file is what counts.
"""


@dataclass(frozen=True)
class Job:
    """One question, ready for one run: the question itself, the prompt file the handoff wrote,
    the manifest line, and where this run's answer belongs."""

    label: str
    batch_id: str
    stage: str
    question: Any
    prompt_path: Path
    answer_path: Path


def scratch_dir(handoff: Path, batch_id: str) -> Path:
    """Where a batch's answer files go: beside the handoff, so nothing is written into the repo."""
    return handoff.parent / f"{handoff.name}-scratch" / batch_id


def check_command(run: Path, handoff: Path, job: Job) -> str:
    """The shape check the run itself runs, spelled as this lane's own CLI spells it."""
    return (
        f"./.venv/Scripts/python.exe scripts/remediation/served_image/run.py check-answer "
        f"--run-dir {run.as_posix()} --handoff {handoff.as_posix()} "
        f"--batch-id {job.batch_id} --label {job.label} --text-file {job.answer_path.as_posix()}"
    )


def answer_prompt(job: Job, check: str) -> str:
    """The prompt of one run. The question's own text is read from the handoff, never restated."""
    return ANSWER_PROMPT.format(
        stage=job.stage,
        answer_model=V.ANSWER_MODEL,
        prompt_path=job.prompt_path.as_posix(),
        answer_path=job.answer_path.as_posix(),
        check=check,
    )


def jobs(run: Path, handoff: Path, labels: list[str] | None = None) -> list[Job]:
    """The stage of this handoff's questions that are not answered yet, in batch order."""
    stage = V.stage_of(run, handoff)
    questions = V._questions(run, stage)
    answered = {
        str(line["label"])
        for line in OH.manifest(handoff)
        if (handoff / line["answer_path"]).exists()
    }
    out: list[Job] = []
    for line in OH.manifest(handoff):
        label = str(line["label"])
        key = (str(line["batch_id"]), label)
        if key not in questions or label in answered:
            continue
        if labels is not None and label not in labels:
            continue
        out.append(
            Job(
                label=label,
                batch_id=key[0],
                stage=stage,
                question=questions[key],
                prompt_path=handoff / line["prompt_path"],
                answer_path=scratch_dir(handoff, key[0]) / f"{label}.json",
            )
        )
    return out


def stamp_of(run_model: str) -> str:
    """The handoff's own stamp for the model a run named. An unknown model is refused."""
    if run_model not in OH.ANSWER_MODELS:
        raise ST.StateError(
            f"the run named model {run_model!r}, which is no key of opus_handoff.ANSWER_MODELS "
            f"({sorted(OH.ANSWER_MODELS)}); its answer would be stamped with a model that did not "
            "write it"
        )
    return OH.ANSWER_MODELS[run_model]


def record(job: Job, handoff: Path, text: str, run_model: str) -> dict[str, Any]:
    """One answer, parsed by the lane and recorded through the handoff.

    Raises `ST.StateError` for a model the handoff does not know, `V.AnswerError` for an answer the
    lane does not accept for this question, and `OH.HandoffError` for a second answer to a question
    already answered. Nothing is written unless all three pass.
    """
    stamp = stamp_of(run_model)
    parsed = V.parse(job.stage, job.question, text)
    wrote = OH.write_answer(
        handoff,
        batch_id=job.batch_id,
        stage=job.stage,
        label=job.label,
        text=text,
        answered_by=f"mcode/{job.label[:8]}",
        model=stamp,
    )
    return {"label": job.label, "wrote": wrote, "pick": parsed.get("pick", parsed.get("verdict"))}


def _one(job: Job, run: Path, handoff: Path) -> mcode.Outcome:
    """One job: the run, then the answer's own check and record. Never raises."""
    stop = mcode.weekly_stop()
    if stop:
        return mcode.Outcome(job, reason=stop, stop=stop)
    job.answer_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = mcode.exec(answer_prompt(job, check_command(run, handoff, job)), cwd=ROOT)
    except StudioError as exc:
        return mcode.Outcome(job, reason=str(exc))
    if result.rate_limited:
        return mcode.Outcome(job, reason="rate limited", run=result, rate_limited=True)
    if not job.answer_path.exists():
        return mcode.Outcome(job, reason="the run wrote no answer file", run=result)
    text = job.answer_path.read_bytes().decode("utf-8")
    try:
        return mcode.Outcome(job, value=record(job, handoff, text, result.model), run=result)
    except (ST.StateError, OH.HandoffError, V.AnswerError, ValueError) as exc:
        return mcode.Outcome(job, reason=f"{type(exc).__name__}: {exc}", run=result)


def answer(
    run: Path,
    handoff: Path,
    labels: list[str] | None = None,
    pool: mcode.Pool | None = None,
) -> dict[str, Any]:
    """Answer the stage's open questions through `mcode exec`, and report each one by label.

    The batch stops on the first wave in which a run left a tracked file changed, on the weekly
    stop (O20), and on a rate limit (which the pool answers with less parallelism and a pause).
    """
    wanted = jobs(run, handoff, labels)
    batch = pool if pool is not None else mcode.Pool()
    before = mcode.tree_state(ROOT)

    def on_wave(wave: list[mcode.Outcome]) -> None:
        mcode.guard_tree(ROOT, before)

    outcomes = batch.map(wanted, lambda job: _one(job, run, handoff), on_wave=on_wave)
    return {
        "run": str(run),
        "handoff": str(handoff),
        "asked": len(wanted),
        "recorded": sum(1 for o in outcomes if o.value is not None),
        "unanswered": {o.item.label: o.reason for o in outcomes if o.value is None},
        "stop": batch.stop,
        "waited_s": batch.waited_s,
    }
