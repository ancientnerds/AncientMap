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
    multi = handoff.Task("paragraph", "Paragraph:\nLine two.\r\nLine three.\n", {"ref": "p9"})
    tasks = [*_tasks(), multi]
    counts = handoff.export_tasks(tmp_path, tasks)
    assert counts == {"tasks": 3, "pending": 3, "accepted": 0}
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    assert [r["ref"] for r in rows] == ["p0", "p1", "p9"]
    for row, task in zip(rows, tasks, strict=True):
        raw = (tmp_path / row["prompt_path"]).read_bytes()
        assert raw == task.prompt.encode("utf-8")
        assert handoff.prompt_sha256(raw.decode("utf-8")) == row["prompt_sha256"]
    for name in ("tasks.jsonl", "pending.jsonl"):
        assert b"\r" not in (tmp_path / name).read_bytes()


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
    assert handoff.read_jsonl(tmp_path / "verdicts.jsonl") == bad  # left to be corrected
    assert not list(tmp_path.glob("verdicts.imported-*.jsonl"))


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
    assert b"\r" not in (tmp_path / "accepted.json").read_bytes()


def _append(path, answer):
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(answer) + "\n")


def test_an_imported_round_is_moved_aside_so_the_next_round_can_append(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    first = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    for row in first:
        _append(tmp_path / "verdicts.jsonl", _answer(row))
    handoff.import_answers(tmp_path, SPEC)
    assert not (tmp_path / "verdicts.jsonl").exists()
    assert handoff.read_jsonl(tmp_path / "verdicts.imported-0001.jsonl") == [
        _answer(r) for r in first
    ]
    fixed = [_tasks()[0], handoff.Task("paragraph", "Check paragraph two, fixed.", {"ref": "p1"})]
    assert handoff.export_tasks(tmp_path, fixed)["pending"] == 1
    second = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    _append(tmp_path / "verdicts.jsonl", _answer(second[1]))
    accepted = handoff.import_answers(tmp_path, SPEC)
    assert sorted(accepted) == sorted(r["task_id"] for r in second)
    assert handoff.read_jsonl(tmp_path / "verdicts.imported-0002.jsonl") == [_answer(second[1])]
    with pytest.raises(handoff.HandoffError, match="run the workflow on pending.jsonl"):
        handoff.import_answers(tmp_path, SPEC)


def test_import_leaves_only_the_unanswered_tasks_pending(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    rows = handoff.read_jsonl(tmp_path / "tasks.jsonl")
    handoff.write_jsonl(tmp_path / "verdicts.jsonl", [_answer(rows[0])])
    handoff.import_answers(tmp_path, SPEC)
    assert handoff.read_jsonl(tmp_path / "pending.jsonl") == [rows[1]]


def test_import_without_verdicts_file_says_what_to_do(tmp_path):
    handoff.export_tasks(tmp_path, _tasks())
    with pytest.raises(handoff.HandoffError, match="run the workflow on pending.jsonl"):
        handoff.import_answers(tmp_path, SPEC)
