"""The four studio workflows (.claude/workflows/*.js), run against canned agent answers.

A workflow is JavaScript for Claude Code's Workflow tool, so these tests run it through
workflow_harness.mjs under node: every agent call is answered from the scenario and the
prompts it was given are recorded. Node 22 is a studio requirement (STUDIO.md 1.1), so a
machine without it fails here instead of skipping.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".claude" / "workflows"
HARNESS = Path(__file__).with_name("workflow_harness.mjs")
VENV_STUDIO = "./.venv/Scripts/python.exe -m pipeline.studio"
PAPER = "C:/studio/papers/3b9ac686-1796-4ad4-92fa-2354c0cc21de"
EPISODE = "C:/studio/episodes/baalbek"
OPUS = "claude-opus-5-5"


def run_workflow(
    name: str, args: dict[str, Any], answers: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    node = shutil.which("node")
    assert node is not None, "node is not on PATH: the studio needs Node 22 (STUDIO.md 1.1)"
    scenario = tmp_path / f"{name}.scenario.json"
    scenario.write_text(json.dumps({"args": args, "answers": answers}), encoding="utf-8")
    done = subprocess.run(
        [node, str(HARNESS), str(WORKFLOWS / f"{name}.js"), str(scenario)],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("utf-8"))


def prompt_of(ran: dict[str, Any], label: str) -> str:
    return next(p["prompt"] for p in ran["prompts"] if p["label"] == label)


def claim_check(tdm: list[str], live_answers: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """theo-claim-check over one paragraph task that cites s1-s3, of which `tdm` are
    TDM-reserved. A source that live_answers has no answer for was saved by an earlier run."""
    task = {
        "task_id": "paragraph-aaaaaaaaaaaa",
        "kind": "paragraph",
        "ref": "p3",
        "cited": ["s1", "s2", "s3"],
        "tdm": tdm,
    }
    inventory = {
        "error": "",
        "in_verdicts_file": 0,
        "tasks": [task],
        "tdm_sources": [{"source_id": s, "live_saved": s not in live_answers} for s in tdm],
    }
    answers = {
        "inventory": inventory,
        **{f"live {sid}": answer for sid, answer in live_answers.items()},
        "verify p3": {
            "verdict": "source_missing",
            "quote": "",
            "quote_source_id": "",
            "explanation": "the page is unreachable",
            "fix_suggestion": "drop it",
            "model": OPUS,
        },
        "write 1": {"appended": ["paragraph-aaaaaaaaaaaa"], "error": ""},
    }
    return run_workflow("theo-claim-check", {"workspace": PAPER}, answers, tmp_path)


def test_a_failed_live_read_is_not_announced_as_saved(tmp_path):
    """Review of I3: liveNote listed every TDM source of the task as saved, so a verifier of a
    task with one failed live read was told that source's page text sits in live/<id>.txt
    and, in the next paragraph, that its live read failed."""
    failed = {"saved": False, "chars": 0, "detail": "HTTP 403 from https://example.org/paywall"}
    ran = claim_check(["s1", "s2"], {"s2": failed}, tmp_path)
    assert ran["error"] is None, ran["error"]
    prompt = prompt_of(ran, "verify p3")
    assert "the page text of s1 is saved in C:/studio/papers/" in prompt
    assert "s1, s2" not in prompt
    assert "The live read of s2 failed (HTTP 403 from https://example.org/paywall)" in prompt


def test_no_saved_live_text_is_announced_when_every_live_read_failed(tmp_path):
    failed = {"saved": False, "chars": 0, "detail": "timed out"}
    ran = claim_check(["s2"], {"s2": failed}, tmp_path)
    assert ran["error"] is None, ran["error"]
    prompt = prompt_of(ran, "verify p3")
    assert "is saved in" not in prompt
    assert "The live read of s2 failed (timed out)" in prompt


def test_every_saved_live_text_is_named_in_the_verifier_prompt(tmp_path):
    ran = claim_check(["s1", "s2"], {}, tmp_path)
    assert ran["error"] is None, ran["error"]
    assert "the page text of s1, s2 is saved in" in prompt_of(ran, "verify p3")


HANDOFFS = [
    # workflow, workspace, an inventory with nothing to answer, what its `next` runs
    (
        "theo-claim-check",
        PAPER,
        {"error": "", "in_verdicts_file": 0, "tasks": [], "tdm_sources": []},
        "paper claims-import 3b9ac686-1796-4ad4-92fa-2354c0cc21de",
    ),
    (
        "theo-image-check",
        PAPER,
        {"error": "", "in_verdicts_file": 0, "tasks": []},
        "paper images-import 3b9ac686-1796-4ad4-92fa-2354c0cc21de",
    ),
    (
        "studio-marker-check",
        EPISODE,
        {"error": "", "in_verdicts_file": 0, "tasks": []},
        "episode markers-import baalbek",
    ),
    (
        "studio-casefile-verify",
        EPISODE,
        {"error": "", "evidence": 0, "items": []},
        "episode check baalbek",
    ),
]


@pytest.mark.parametrize(("name", "workspace", "empty", "next_step"), HANDOFFS)
def test_the_next_step_is_a_command_that_runs_from_the_checkout(
    name, workspace, empty, next_step, tmp_path
):
    """CLAUDE.md: a bare `python` is not reliable here (pi-lens and fresh shells put a foreign
    venv in front); every command a workflow hands the session names the repo venv."""
    ran = run_workflow(name, {"workspace": workspace}, {"inventory": empty}, tmp_path)
    assert ran["error"] is None, ran["error"]
    assert ran["result"]["next"] == f"{VENV_STUDIO} {next_step}"


@pytest.mark.parametrize(
    ("name", "workspace", "export"),
    [
        ("theo-claim-check", PAPER, "paper claims-export 3b9ac686-1796-4ad4-92fa-2354c0cc21de"),
        ("theo-image-check", PAPER, "paper images-export 3b9ac686-1796-4ad4-92fa-2354c0cc21de"),
        ("studio-marker-check", EPISODE, "episode markers-export baalbek"),
    ],
)
def test_a_missing_export_names_the_command_that_writes_it(name, workspace, export, tmp_path):
    inventory = {"error": "no such file", "in_verdicts_file": 0, "tasks": [], "tdm_sources": []}
    ran = run_workflow(name, {"workspace": workspace}, {"inventory": inventory}, tmp_path)
    assert f"run `{VENV_STUDIO} {export}` first" in ran["error"]


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.js")), ids=lambda p: p.name)
def test_no_workflow_text_runs_a_bare_python(path):
    assert "python -m pipeline.studio" not in path.read_text(encoding="utf-8")
