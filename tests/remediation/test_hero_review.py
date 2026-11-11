"""The Opus review of a hero-moves plan (served_image/hero_review.py): export one question per
planned site with its pictures, the answer check, and an all-or-nothing import into the
REVIEW.jsonl that `hero_moves.py emit --review` reads. DB-less and offline."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
from served_image import hero_moves as HM  # noqa: E402
from served_image import hero_review as HR  # noqa: E402

from tests.remediation import test_hero_moves as T  # noqa: E402


def _planned_run(tmp_path: Path) -> Path:
    run, served = T._fixture(tmp_path)
    HM.write_plan(run, [served], [])
    return run


def _pictures(tmp_path: Path):
    folder = tmp_path / "offsite"
    folder.mkdir(exist_ok=True)

    def path_of(site_id: str, filename: str) -> Path:
        path = folder / f"{site_id}-{filename}.png"
        if not path.exists():
            Image.new("RGB", (40, 30), (len(filename) * 20 % 255, 80, 120)).save(path)
        return path

    return path_of


def _answer_all(
    handoff: Path, run: Path, *, model: str = "claude-opus-5-5", text: str | None = None
):
    planned = HM._jsonl(run / HM.PLANNED)
    for index, line in enumerate(planned):
        body = text or json.dumps(
            {
                "decision": "accept",
                "shows": "The city walls.",
                "reason": "Shows the site; credited.",
            }
        )
        OH.write_answer(
            handoff, batch_id=HR.batch_of(index), stage=HR.STAGE, label=line["site_id"],
            text=body, answered_by="hero-review-01", model=OH.ANSWER_MODELS[model],
        )  # fmt: skip


def test_export_writes_one_question_per_planned_site_with_both_pictures(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    out = HR.export(run, handoff, _pictures(tmp_path))
    assert out["planned"] == 1 and out["exported"] == 1 and out["batches"] == ["review-01"]
    [line] = OH.manifest(handoff)
    prompt = (handoff / line["prompt_path"]).read_text(encoding="utf-8")
    new_name, old_name = HR.image_names(HM._jsonl(run / HM.PLANNED)[0])
    assert line["image_path"] == OH.image_relpath(new_name)
    assert old_name is not None and (handoff / OH.image_relpath(old_name)).is_file()
    assert "licence URL: https://creativecommons.org/licenses/by-sa/4.0" in prompt
    assert "CURRENT HERO (replaced): image 1" in prompt
    # a second export of the same plan is a no-op, never a second question
    assert HR.export(run, handoff, _pictures(tmp_path))["exported"] == 0


def test_a_small_plan_is_asked_whether_the_current_hero_is_the_better_picture(
    tmp_path: Path,
) -> None:
    """D82: a small-hero move gains only size, so the reviewer is told to veto a worse picture."""
    run, served = T._small_site_run(tmp_path)
    HM.write_plan(run, [served], [T._check_run(tmp_path, target="B.jpg")])
    [line] = HM._jsonl(run / HM.PLANNED)
    prompt = HR.prompt_for(line, HM.load_read(run))
    assert "Why the site is planned: small -> hero moved" in prompt
    for text in (*HR.SMALL_WHY, *HR.SMALL_RULE):
        assert text + "\n" in prompt
    assert "Veto it when the current hero is" in HR.SMALL_RULE[0]
    assert prompt.index(HR.SMALL_WHY[0]) < prompt.index("PLANNED NEW HERO")
    assert prompt.index("Open the picture(s) and decide") < prompt.index(HR.SMALL_RULE[0])
    assert prompt.index(HR.SMALL_RULE[-1]) < prompt.index("Answer with exactly one JSON object")


def test_a_plan_of_another_kind_is_asked_what_it_was_asked_before(tmp_path: Path) -> None:
    """The import rebuilds the prompt byte for byte: a review of a D48/D49 plan exported before
    the small heroes were planned must still be importable (pinned on the fixture's strip)."""
    run = _planned_run(tmp_path)
    [line] = HM._jsonl(run / HM.PLANNED)
    prompt = HR.prompt_for(line, HM.load_read(run))
    assert HR.SMALL_WHY[0] not in prompt and HR.SMALL_RULE[0] not in prompt
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == (
        "e50c62417a64401819b5fd705a3555f30091b405f48bca9649b7d9868d904e8b"
    )


def test_an_opus_review_imports_into_the_file_emit_reads(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    HR.export(run, handoff, _pictures(tmp_path))
    _answer_all(handoff, run)
    out = HR.import_review(run, handoff)
    assert out["accept"] == 1 and out["veto"] == 0
    record = HM.emit(run, run / HR.REVIEW_FILE)
    assert record["accepted_sites"] == 1 and record["chunks"] == 1
    with pytest.raises(HR.HeroReviewError, match="written once"):
        HR.import_review(run, handoff)


def test_a_fable_review_imports_as_an_opus_one_does(tmp_path: Path) -> None:
    """Owner decision D153 (2026-11-10): every answer is Fable's from then on, so a review answered
    since carries the Fable stamp; `emit` takes it as a Claude answer stamp's."""
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    HR.export(run, handoff, _pictures(tmp_path))
    _answer_all(handoff, run, model="claude-fable-5-2")
    out = HR.import_review(run, handoff)
    assert out["accept"] == 1 and out["veto"] == 0
    [line] = HM._jsonl(run / HR.REVIEW_FILE)
    assert line["by"] == OH.FABLE_MODEL
    record = HM.emit(run, run / HR.REVIEW_FILE)
    assert record["accepted_sites"] == 1 and record["chunks"] == 1


def test_a_veto_passes_through_to_vetoed(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    HR.export(run, handoff, _pictures(tmp_path))
    veto = json.dumps({"decision": "veto", "shows": "A plan.", "reason": "A plan, not the site."})
    _answer_all(handoff, run, text=veto)
    assert HR.import_review(run, handoff)["veto"] == 1
    assert HM.emit(run, run / HR.REVIEW_FILE)["vetoed_sites"] == 1


def test_a_sonnet_answer_is_no_review_here(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    HR.export(run, handoff, _pictures(tmp_path))
    _answer_all(handoff, run, model="claude-sonnet-5-5")
    with pytest.raises(HR.HeroReviewError, match="this review is"):
        HR.import_review(run, handoff)
    assert not (run / HR.REVIEW_FILE).exists()


def test_a_missing_answer_imports_nothing(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    handoff = tmp_path / "handoff"
    HR.export(run, handoff, _pictures(tmp_path))
    with pytest.raises(OH.HandoffError, match="no answer"):
        HR.import_review(run, handoff)
    assert not (run / HR.REVIEW_FILE).exists()


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"decision": "accept", "shows": "x", "reason": "y"}\n```',
        '{"decision": "maybe", "shows": "x", "reason": "y"}',
        '{"decision": "accept", "shows": "x"}',
        '{"decision": "veto", "shows": "x", "reason": " "}',
    ],
)
def test_the_answer_check_refuses_every_other_shape(text: str) -> None:
    with pytest.raises(HR.HeroReviewError):
        HR.parse_answer(text)


def test_a_changed_plan_is_not_exported(tmp_path: Path) -> None:
    run = _planned_run(tmp_path)
    (run / HM.PLANNED).write_text((run / HM.PLANNED).read_text() + "{}\n", encoding="utf-8")
    with pytest.raises(HR.HeroReviewError, match="changed after the plan"):
        HR.export(run, tmp_path / "handoff", _pictures(tmp_path))
