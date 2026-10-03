"""Lane WC's state machine, in the driver's own terms.

`wc-continue.js` let a model decide, per run, which of six stages the chunk stands in by inspecting
the run's files. The driver does it with code: `wc_next_step` reads the same files and returns the
one step to take next. These tests build a run tree at a known stage and assert the step.

The stage order is the JS script's: round 1 -> re-ask (once) -> verification round 1 -> verification
round 2 (once, only for texts a drop changed) -> build. `WC4.jsonl` existing means built, whatever
else is on disk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import mcode_driver as D  # noqa: E402

RUN = "mass-2026-09-27-01"


def a_run(root: Path, run: str = RUN, *, handoffs: tuple[str, ...] = ()) -> Path:
    """An empty run directory. `handoffs` names the handoff directories that exist."""
    run_dir = root / "runs" / run
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in handoffs:
        (root / "handoff" / name).mkdir(parents=True, exist_ok=True)
    return run_dir


def write(path: Path, text: str = "{}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def plan(root: Path, run: Path, **kwargs: Any) -> D.WcPlan:
    return D.wc_next_step(run, root / "handoff", **kwargs)


# ---------------------------------------------------------------------------- the six stages
def test_a_built_run_is_done_and_runs_nothing(tmp_path: Path) -> None:
    run = a_run(tmp_path)
    write(run / "WC4.jsonl")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.done is True
    assert result.command == ()
    assert result.answer_batches == ()


def test_a_run_whose_round_1_handoff_does_not_exist_is_refused(tmp_path: Path) -> None:
    """The JS script set ok=false here. A run with no exported round 1 is not a run to continue:
    something exported it and it is gone, and the driver does not invent the questions."""
    run = a_run(tmp_path)

    result = plan(tmp_path, run, first_batch=4200)

    assert result.done is False
    assert result.ok is False
    assert "wc-mass-2026-09-27-01-r1" in result.note


def test_round_1_is_imported_before_anything_else_happens(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.ok is True
    assert result.command[2] == "export-reask" or result.command[2] == "verify-export"


def test_a_round_1_that_was_never_imported_is_validated_first(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))

    result = plan(tmp_path, run, first_batch=4200)

    assert result.ok is True
    assert result.stage == "round-1"
    assert result.answer_handoff is not None
    assert result.answer_handoff.name == "wc-mass-2026-09-27-01-r1"
    assert result.answer_brief == "brief"
    assert result.answer_batches == ()  # the batches come from `validate`, not from the files
    assert result.command == ()  # nothing to run: the answers come first


def test_the_reask_is_skipped_when_round_2_is_imported(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl", json.dumps({"sentences": [1]}) + "\n")
    write(run / "round-2" / "ANSWERS.jsonl")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage != "reask"


def test_a_reask_whose_export_is_missing_exports_it_and_returns(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl", json.dumps({"sentences": [1]}) + "\n")
    write(run / "round-1" / "REASK.json", json.dumps({"reask": [{"n": 2}]}) + "\n")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.ok is True
    assert result.stage == "reask"
    assert result.command[2] == "export-reask"
    assert result.command[-1].endswith("wc-mass-2026-09-27-01-r2")


def test_verification_round_1_is_exported_before_it_is_answered(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage == "verify-1"
    assert result.command[2] == "verify-export"
    assert result.command[-1].endswith("wc-mass-2026-09-27-01-verify")


def test_a_verification_export_that_refused_advances_to_the_next_stage(tmp_path: Path) -> None:
    """`verify-export` answers "nothing to verify" when no text changed - the JS script read that
    refusal and went on in the same step. The driver cannot re-read a command it already ran, so the
    refusal is remembered in the state file and the next plan starts after it."""
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")
    state = D.State(tmp_path / "state.json", lane="wc", run=RUN, handoff="wc")
    state.put("refused", ["verify-1"])

    result = plan(tmp_path, run, first_batch=4200, state=state)

    assert result.stage != "verify-1"
    assert result.ok is True


def test_a_verified_round_is_answered_with_the_verification_brief(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1", "wc-mass-2026-09-27-01-verify"))
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")
    write(run / "verify" / "round-1" / "ROUND.json")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage == "verify-1"
    assert result.answer_handoff is not None
    assert result.answer_handoff.name == "wc-mass-2026-09-27-01-verify"
    assert result.answer_brief == "verify-brief"


def test_the_build_is_the_last_stage_and_carries_the_first_batch_number(tmp_path: Path) -> None:
    run = a_run(tmp_path, handoffs=("wc-mass-2026-09-27-01-r1",))
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")
    write(run / "verify" / "round-1" / "ROUND.json")
    write(run / "verify" / "round-1" / "VERIFIED.jsonl", json.dumps({"round": 1}) + "\n")
    write(run / "verify" / "round-2" / "ROUND.json")
    write(run / "verify" / "round-2" / "VERIFIED.jsonl", json.dumps({"round": 2}) + "\n")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage == "build"
    assert result.command[2] == "build"
    assert "4200" in result.command


def test_a_verified_round_is_read_from_the_round_directory_not_the_run_root(tmp_path: Path) -> None:
    """`wc-continue.js` looked for `R/VERIFIED.jsonl`. The runs hold
    `verify/round-<n>/VERIFIED.jsonl` (measured 2026-10-03 on mass-01..05), so a machine that
    follows the script would answer a round that is already imported - and WC's rounds are written
    once, so that costs the round."""
    run = a_run(
        tmp_path,
        handoffs=(
            "wc-mass-2026-09-27-01-r1",
            "wc-mass-2026-09-27-01-verify",
            "wc-mass-2026-09-27-01-verify2",
        ),
    )
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")
    write(run / "verify" / "round-1" / "ROUND.json")
    write(run / "verify" / "round-1" / "VERIFIED.jsonl", json.dumps({"round": 1}) + "\n")
    write(run / "verify" / "round-2" / "ROUND.json")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage == "verify-2"
    assert result.answer_handoff is not None
    assert result.answer_handoff.name == "wc-mass-2026-09-27-01-verify2"


def test_round_2_is_not_touched_while_round_1_is_still_open(tmp_path: Path) -> None:
    """Verification round 2 asks about the texts a round-1 drop changed. Without an imported
    round 1 there is nothing to re-check, so the lane must not export or answer round 2."""
    run = a_run(
        tmp_path,
        handoffs=(
            "wc-mass-2026-09-27-01-r1",
            "wc-mass-2026-09-27-01-verify",
            "wc-mass-2026-09-27-01-verify2",
        ),
    )
    write(run / "round-1" / "ANSWERS.jsonl")
    write(run / "round-2" / "ANSWERS.jsonl")
    write(run / "verify" / "round-1" / "ROUND.json")

    result = plan(tmp_path, run, first_batch=4200)

    assert result.stage == "verify-1"


# ---------------------------------------------------------------------------- the loop guard
def test_three_identical_steps_stop_the_lane(tmp_path: Path) -> None:
    """The JS script stopped a run after three identical steps, because a step that decides nothing
    would otherwise loop forever. The driver counts the same way: the third identical step stops."""
    guard = D.StepGuard(limit=3)

    assert guard.seen("stage=round-1 ran=validate") == 1
    assert guard.stopped("stage=round-1 ran=validate") is False
    assert guard.seen("stage=round-1 ran=validate") == 2
    assert guard.stopped("stage=round-1 ran=validate") is False
    assert guard.seen("stage=round-1 ran=validate") == 3
    assert guard.stopped("stage=round-1 ran=validate") is True

    # a step that differs resets nothing and is not stopped
    assert guard.seen("stage=build ran=build") == 1
    assert guard.stopped("stage=build ran=build") is False


# ---------------------------------------------------------------------------- the answer prompt
def test_a_wc_answer_prompt_names_the_verify_brief_and_its_own_run_dir(tmp_path: Path) -> None:
    prompt = D.wc_answer_prompt(
        run=tmp_path / "runs" / RUN,
        handoff=tmp_path / "handoff" / "wc-mass-2026-09-27-01-verify",
        batch="wc-0001",
        brief="verify-brief",
    )

    assert "verify-brief" in prompt
    assert "wc-mass-2026-09-27-01-verify" in prompt
    assert "--model MiniMax-M3.1-Flash-Preview" in prompt
    # the brief command names the lane's own CLI, with this platform's separators
    flat = prompt.replace("\\", "/")
    assert "wc/cli.py verify-brief" in flat
