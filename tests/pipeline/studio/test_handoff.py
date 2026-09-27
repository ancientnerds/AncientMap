from __future__ import annotations

import json

import pytest

from pipeline.studio import handoff

SPEC = handoff.AnswerSpec(
    fields={"verdict": (str,), "explanation": (str,)},
    enums={"verdict": frozenset({"supported", "unsupported"})},
)


def _tasks():
    return [
        handoff.Task("paragraph", "Check paragraph one.", {"ref": "p0"}),
        handoff.Task("paragraph", "Check paragraph two.", {"ref": "p1"}),
    ]


def _answer(row, **over):
    base = {
        "task_id": row["task_id"],
        "prompt_sha256": row["prompt_sha256"],
        "answered_by": "claude-opus-5-5 (Claude Code agent)",
        "verdict": "supported",
        "explanation": "ok",
    }
    base.update(over)
    return base


def test_task_ids_derive_from_the_prompt_hash():
    t = handoff.Task("evidence", "prompt", {})
    assert t.task_id == "evidence-" + handoff.prompt_sha256("prompt")[:12]


def test_export_writes_tasks_pending_and_prompts(tmp_path):
    counts = handoff.export_tasks(tmp_path, _tasks())
    assert counts == {"tasks": 2, "pending": 2, "accepted": 0}
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    assert [r["ref"] for r in rows] == ["p0", "p1"]
    prompt = (tmp_path / rows[0]["prompt_path"]).read_text(encoding="utf-8")
    assert prompt == "Check paragraph one."
    assert handoff.prompt_sha256(prompt) == rows[0]["prompt_sha256"]


def test_duplicate_prompts_are_refused(tmp_path):
    same = handoff.Task("paragraph", "same", {})
    with pytest.raises(handoff.HandoffError, match="share a prompt"):
        handoff.export_tasks(tmp_path, [same, same])


def test_import_merges_and_re_export_only_leaves_new_tasks_pending(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    handoff.write_jsonl(tmp_path / "verdicts.jsonl", [_answer(rows[0])])
    accepted = handoff.import_answers(tmp_path, SPEC)
    assert list(accepted) == [rows[0]["task_id"]]
    new = [_tasks()[0], handoff.Task("paragraph", "Check paragraph three.", {"ref": "p2"})]
    counts = handoff.export_tasks(tmp_path, new)
    assert counts == {"tasks": 2, "pending": 1, "accepted": 1}
    pending = handoff.read_jsonl(tmp_path / "pending.jsonl")
    assert [p["ref"] for p in pending] == ["p2"]
    assert len(list((tmp_path / "prompts").glob("*.txt"))) == 2


def test_import_reports_every_problem(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    bad = [
        _answer(rows[0], prompt_sha256="0" * 64),
        _answer(rows[1], verdict="maybe"),
        {"task_id": "paragraph-000000000000"},
        _answer(rows[1], answered_by="  "),
    ]
    handoff.write_jsonl(tmp_path / "verdicts.jsonl", bad)
    with pytest.raises(handoff.HandoffError) as exc:
        handoff.import_answers(tmp_path, SPEC)
    message = str(exc.value)
    assert "prompt_sha256 does not match" in message
    assert "not allowed: [\"verdict='maybe'\"]" in message
    assert "missing" in message
    assert "answered_by is empty" in message
    assert not (tmp_path / "accepted.json").exists()


def test_answers_for_tasks_that_left_the_export_are_dropped_from_accepted(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    handoff.write_jsonl(tmp_path / "verdicts.jsonl", [_answer(r) for r in rows])
    handoff.import_answers(tmp_path, SPEC)
    handoff.export_tasks(tmp_path, [_tasks()[1]])
    handoff.write_jsonl(tmp_path / "verdicts.jsonl", [])
    accepted = handoff.import_answers(tmp_path, SPEC)
    assert list(accepted) == [rows[1]["task_id"]]
    stored = json.loads((tmp_path / "accepted.json").read_text(encoding="utf-8"))
    assert list(stored) == [rows[1]["task_id"]]


def test_import_without_verdicts_file_says_what_to_do(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    with pytest.raises(handoff.HandoffError, match="run the workflow on pending.jsonl"):
        handoff.import_answers(tmp_path, SPEC)
