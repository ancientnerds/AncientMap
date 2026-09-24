"""The Opus handoff directory (`scripts/remediation/opus_handoff.py`): export, answer, validate, read.

Owner order 2026-09-23: every model judgement of the remediation is answered by Opus agents of the
orchestrating session, through files. Nothing here calls a model, opens a socket or starts a process
other than the CLI's own interpreter; the answers are written by the tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import opus_handoff as OH  # noqa: E402

PROMPT = "<question>\nIs the stored value wrong?\n</question>\n\nÖtzi's cave, 3300 BC\n"
LABEL = "site-1/description"
NOW = "2026-09-23T12:00:00+00:00"


def _export(root: Path, prompt: str = PROMPT, **overrides: object) -> bool:
    kwargs: dict[str, object] = {
        "batch_id": "batch-0001",
        "stage": "finder",
        "label": LABEL,
        "field": "description",
        "prompt": prompt,
    }
    kwargs.update(overrides)
    return OH.export(root, **kwargs)  # type: ignore[arg-type]


def _answer(root: Path, text: str = "VERDICT: CORRECT\n", **overrides: object) -> bool:
    kwargs: dict[str, object] = {
        "batch_id": "batch-0001",
        "stage": "finder",
        "label": LABEL,
        "text": text,
        "answered_by": "opus-agent-1",
        "now": lambda: NOW,
    }
    kwargs.update(overrides)
    return OH.write_answer(root, **kwargs)  # type: ignore[arg-type]


def _answer_file(root: Path) -> Path:
    return root / OH.answer_relpath("batch-0001", "finder", LABEL)


def _rewrite(root: Path, **changes: object) -> None:
    path = _answer_file(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(root: Path, prompt: str = PROMPT) -> OH.Answer:
    return OH.read_answer(root, batch_id="batch-0001", stage="finder", label=LABEL, prompt=prompt)


# ------------------------------------------------------------------------------------ the model


def test_every_answer_names_the_one_pinned_opus_model() -> None:
    assert OH.OPUS_MODEL == "anthropic/claude-opus-5-5 (Claude Code agent)"
    assert "deepseek" not in OH.OPUS_MODEL.lower()


# ------------------------------------------------------------------------------------ the export


def test_an_export_writes_the_exact_prompt_and_one_manifest_line(tmp_path: Path) -> None:
    assert _export(tmp_path) is True

    prompt_file = tmp_path / "batch-0001" / "finder" / "site-1%2Fdescription.prompt.txt"
    assert prompt_file.read_bytes() == PROMPT.encode("utf-8")
    lines = (tmp_path / "batch-0001" / "MANIFEST.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {
            "batch_id": "batch-0001",
            "stage": "finder",
            "label": LABEL,
            "field": "description",
            "prompt_sha256": OH.prompt_sha256(PROMPT),
            "prompt_path": "batch-0001/finder/site-1%2Fdescription.prompt.txt",
            "answer_path": "batch-0001/finder/site-1%2Fdescription.answer.json",
            "image_path": None,
        }
    ]
    assert OH.manifest(tmp_path) == [json.loads(lines[0])]


def test_the_same_prompt_exported_twice_is_one_question(tmp_path: Path) -> None:
    assert _export(tmp_path) is True
    assert _export(tmp_path) is False
    assert len(OH.manifest(tmp_path)) == 1


def test_a_different_prompt_for_an_exported_question_is_refused_even_without_its_file(
    tmp_path: Path,
) -> None:
    """The manifest, not the prompt file, is what says a question was asked: an answer may exist."""
    _export(tmp_path)
    (tmp_path / OH.prompt_relpath("batch-0001", "finder", LABEL)).unlink()

    with pytest.raises(OH.HandoffError, match="never replaced"):
        _export(tmp_path, prompt=PROMPT + "a second version\n")
    assert not (tmp_path / OH.prompt_relpath("batch-0001", "finder", LABEL)).exists()


def test_the_finder_and_the_reviewer_of_one_field_are_two_questions(tmp_path: Path) -> None:
    _export(tmp_path)
    assert _export(tmp_path, prompt="the reviewer's question\n", stage="reviewer") is True
    assert {(row["stage"], row["label"]) for row in OH.manifest(tmp_path)} == {
        ("finder", LABEL),
        ("reviewer", LABEL),
    }


def test_an_image_is_written_with_its_question_and_is_never_replaced(tmp_path: Path) -> None:
    jpeg = b"\xff\xd8\xff\xe0 the exact bytes"
    assert _export(tmp_path, image_name="4711", image=jpeg) is True

    assert (tmp_path / "images" / "4711.jpg").read_bytes() == jpeg
    assert OH.manifest(tmp_path)[0]["image_path"] == "images/4711.jpg"
    with pytest.raises(OH.HandoffError, match="an image needs its name and its bytes"):
        _export(tmp_path, stage="other", image_name="4712")
    with pytest.raises(OH.HandoffError, match="never replaced"):
        _export(tmp_path)  # the same question without its image is another question


@pytest.mark.parametrize(
    ("batch_id", "stage"),
    [("../outside", "finder"), ("a/b", "finder"), ("images", "finder"), ("batch-1", "..")],
)
def test_a_batch_id_or_stage_that_is_not_one_plain_name_is_refused(
    tmp_path: Path, batch_id: str, stage: str
) -> None:
    with pytest.raises(OH.HandoffError):
        _export(tmp_path, batch_id=batch_id, stage=stage)
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------------------------ the answers


def test_an_answer_is_read_for_exactly_its_prompt(tmp_path: Path) -> None:
    _export(tmp_path)
    assert _answer(tmp_path) is True

    answer = _read(tmp_path)
    assert answer == OH.Answer(
        text="VERDICT: CORRECT\n", answered_by="opus-agent-1", answered_at=NOW
    )
    stored = json.loads(_answer_file(tmp_path).read_text(encoding="utf-8"))
    assert set(stored) == OH.ANSWER_KEYS
    assert stored["prompt_sha256"] == OH.prompt_sha256(PROMPT)
    assert stored["model"] == OH.OPUS_MODEL


def test_a_missing_answer_is_refused(tmp_path: Path) -> None:
    _export(tmp_path)
    with pytest.raises(OH.HandoffError, match="no answer at"):
        _read(tmp_path)


def test_an_answer_to_another_prompt_is_stale_and_refused(tmp_path: Path) -> None:
    _export(tmp_path)
    _answer(tmp_path)
    with pytest.raises(OH.HandoffError, match="stale"):
        _read(tmp_path, prompt=PROMPT + "the prompt the stage asks today\n")


def test_an_answer_by_another_model_is_refused(tmp_path: Path) -> None:
    _export(tmp_path)
    _answer(tmp_path)
    _rewrite(tmp_path, model="opencode-go/deepseek-v4.1-flash")
    with pytest.raises(OH.HandoffError, match="wrong model"):
        _read(tmp_path)


def test_an_empty_answer_is_refused(tmp_path: Path) -> None:
    _export(tmp_path)
    _answer(tmp_path)
    _rewrite(tmp_path, text="  \n")
    with pytest.raises(OH.HandoffError, match="the text is empty"):
        _read(tmp_path)


def test_an_answer_that_is_not_exactly_the_answer_shape_is_refused(tmp_path: Path) -> None:
    _export(tmp_path)
    _answer(tmp_path)
    _rewrite(tmp_path, cost_usd=0.0)
    with pytest.raises(OH.HandoffError, match="malformed"):
        _read(tmp_path)
    _rewrite(tmp_path, cost_usd=None)
    data = json.loads(_answer_file(tmp_path).read_text(encoding="utf-8"))
    del data["cost_usd"]
    data["answered_at"] = "2026-09-23T12:00:00"  # no zone: not a time anybody can order
    _answer_file(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(OH.HandoffError, match="no time zone"):
        _read(tmp_path)
    _answer_file(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(OH.HandoffError, match="not JSON"):
        _read(tmp_path)


def test_the_answer_helper_names_the_exported_prompts_own_digest(tmp_path: Path) -> None:
    """An agent never computes a digest: the helper reads it off the manifest and the prompt file."""
    with pytest.raises(OH.HandoffError, match="never exported"):
        _answer(tmp_path)
    _export(tmp_path)
    (tmp_path / OH.prompt_relpath("batch-0001", "finder", LABEL)).write_text(
        "a prompt edited after the export", encoding="utf-8"
    )
    with pytest.raises(OH.HandoffError, match="not the prompt the manifest names"):
        _answer(tmp_path)
    assert not _answer_file(tmp_path).exists()


def test_an_answer_is_written_once(tmp_path: Path) -> None:
    _export(tmp_path)
    assert _answer(tmp_path) is True
    assert _answer(tmp_path, now=lambda: "2026-09-24T08:00:00+00:00") is False  # the same text
    with pytest.raises(OH.HandoffError, match="already holds another answer"):
        _answer(tmp_path, text="VERDICT: WRONG\n")
    assert _read(tmp_path).text == "VERDICT: CORRECT\n"
    _export(tmp_path, label="site-2/description", prompt=PROMPT + "2\n")
    with pytest.raises(OH.HandoffError, match="the text is empty"):
        _answer(tmp_path, label="site-2/description", text=" ")


# ------------------------------------------------------------------------------------ the validator


def test_the_validator_reports_what_is_missing_stale_malformed_or_orphaned(tmp_path: Path) -> None:
    for number in range(1, 6):
        _export(tmp_path, label=f"site-{number}/description", prompt=f"{PROMPT}{number}\n")
    for number in (1, 2, 3):
        _answer(tmp_path, label=f"site-{number}/description")
    stale = tmp_path / OH.answer_relpath("batch-0001", "finder", "site-2/description")
    data = json.loads(stale.read_text(encoding="utf-8"))
    data["prompt_sha256"] = "0" * 64
    stale.write_text(json.dumps(data), encoding="utf-8")
    wrong = tmp_path / OH.answer_relpath("batch-0001", "finder", "site-3/description")
    data = json.loads(wrong.read_text(encoding="utf-8"))
    data["model"] = "deepseek-v4-flash-vision-exp"
    wrong.write_text(json.dumps(data), encoding="utf-8")
    edited = tmp_path / OH.prompt_relpath("batch-0001", "finder", "site-4/description")
    edited.write_text("changed after the export", encoding="utf-8")
    orphan = tmp_path / "batch-0001" / "finder" / "nobody%2Fasked.answer.json"
    orphan.write_text("{}", encoding="utf-8")

    result = OH.validate(tmp_path)

    assert not result.ok
    assert [e["label"] for e in result.answered] == ["site-1/description"]
    assert [e["label"] for e in result.stale] == ["site-2/description"]
    assert [(e["label"], e["why"][:11]) for e in result.malformed] == [
        ("site-3/description", "wrong model"),
        ("site-4/description", "the exporte"),
    ]
    assert [e["label"] for e in result.missing] == ["site-5/description"]
    assert result.orphans == ["batch-0001/finder/nobody%2Fasked.answer.json"]


def test_a_fully_answered_directory_validates(tmp_path: Path) -> None:
    _export(tmp_path)
    _export(tmp_path, stage="reviewer", prompt="the reviewer's question\n")
    _answer(tmp_path)
    _answer(tmp_path, stage="reviewer", text="REFUTED: NO\n")

    result = OH.validate(tmp_path)

    assert result.ok and len(result.answered) == 2
    assert result.to_dict()["questions"] == 2


def test_the_cli_validates_and_answers(tmp_path: Path) -> None:
    _export(tmp_path)
    script = str(REMEDIATION / "opus_handoff.py")
    env_run = {"capture_output": True, "text": True, "encoding": "utf-8", "check": False}

    first = subprocess.run([sys.executable, script, "validate", "--dir", str(tmp_path)], **env_run)
    assert first.returncode == 1 and len(json.loads(first.stdout)["missing"]) == 1

    text = tmp_path / "answer.txt"
    text.write_bytes("VERDICT: CORRECT - Ötzi\n".encode())
    argv = [
        sys.executable,
        script,
        "answer",
        "--dir",
        str(tmp_path),
        "--batch-id",
        "batch-0001",
        "--stage",
        "finder",
        "--label",
        LABEL,
        "--answered-by",
        "opus-agent-7",
        "--text-file",
        str(text),
    ]
    wrote = subprocess.run(argv, **env_run)
    assert wrote.returncode == 0, wrote.stderr
    assert _read(tmp_path).text == "VERDICT: CORRECT - Ötzi\n"

    second = subprocess.run([sys.executable, script, "validate", "--dir", str(tmp_path)], **env_run)
    assert second.returncode == 0 and json.loads(second.stdout)["ok"] is True
