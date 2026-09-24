"""The vision stage of the gallery audit: frozen prompts, the ledger, the current tiers, the label
sets and the sealed rule table (`scripts/remediation/gallery_audit/{vision,worklist,labels,decide}.py`).

Offline: the answers are Opus-handoff answer files the tests write (owner order 2026-09-23; no
model is called), the images are real files written here, and the tiers run through T10's own
functions. Tests that need the gitignored snapshot or label file skip with a reason.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import string
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from gallery_audit import decide, labels, liveness, planned, vision, worklist  # noqa: E402

from pipeline.video.shorts_select import VLM_PROMPT, vlm_bytes  # noqa: E402

SNAPSHOT = REPO / "output" / "remediation" / "snapshot"
CACHE = REPO / "output" / "remediation" / "cache"
T10_FINDINGS = REPO / "output" / "remediation" / "run_t10" / "findings.jsonl"
HERO_MOVES = REPO / "output" / "remediation" / "hero_repair" / "PLAN.jsonl"
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "wiki_images.jsonl.gz").exists(),
    reason=f"{SNAPSHOT} is gitignored working data and not on this checkout",
)
needs_state = pytest.mark.skipif(
    not all(
        p.exists()
        for p in (
            SNAPSHOT / "wiki_images.jsonl.gz",
            CACHE / "gallery_signals.json",
            T10_FINDINGS,
            HERO_MOVES,
        )
    ),
    reason="the snapshot, T10's signal index and findings and the hero plan are gitignored working data",
)
needs_label_source = pytest.mark.skipif(
    not labels.LABELS_SOURCE.exists() or not (SNAPSHOT / "wiki_images.jsonl.gz").exists(),
    reason=f"{labels.LABELS_SOURCE} and the snapshot are local-only and not on this checkout",
)

GALLERY_SHA = "b9a91ed10d1cba6dff89e394b85a9a03139f1056818b8b56f9a044aa2873c9f8"
HERO_SHA = "56adb6fbe0f82541423a722740636995a2b9744ce9d4b7063d8d24062a30849b"
RULES_SHA = "2380f7a0c286dbd5eef72231eab4eb37c6b31c0c296194495b31feca8a4ed523"

SITE = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
SHARD = "0a1b2c3d"


# ======================================================================= frozen prompts
def test_the_frozen_prompts_hash_to_their_pins() -> None:
    assert vision.prompt_sha256(vision.GALLERY_PROMPT) == GALLERY_SHA
    assert vision.prompt_sha256(vision.HERO_PROMPT) == HERO_SHA


def _line_starting(text: str, prefix: str) -> str:
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"{prefix!r} occurs {len(lines)} times"
    return lines[0]


def test_the_kind_vocabulary_and_definitions_are_the_shorts_prompts_byte_for_byte() -> None:
    assert _line_starting(vision.GALLERY_PROMPT, "kind: ") == _line_starting(VLM_PROMPT, "kind: ")
    assert _line_starting(vision.GALLERY_PROMPT, '{{"kind": ') == _line_starting(
        VLM_PROMPT, '{{"kind": '
    )
    enum = re.findall(r'"([^"]+)"', _line_starting(vision.GALLERY_PROMPT, '{{"kind": '))[1:]
    assert tuple(enum) == vision.KINDS


def test_the_gallery_prompt_carries_no_card_text_and_only_its_five_inputs() -> None:
    assert "card_text" not in vision.GALLERY_PROMPT and "narration" not in vision.GALLERY_PROMPT
    for template in (vision.GALLERY_PROMPT, vision.HERO_PROMPT):
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        assert fields == {"site", "site_type", "country", "title", "categories"}


def test_other_site_is_defined_strictly_and_the_hero_rule_names_what_is_false() -> None:
    assert (
        "including a neighbouring monument, a nearby modern park, town or zoo"
        in vision.GALLERY_PROMPT
    )
    assert "does not count" not in vision.GALLERY_PROMPT
    assert (
        "Empty fields, hillsides, coastlines, roads, sky, modern buildings, engravings, drawings and maps are false."
        in vision.HERO_PROMPT
    )


def _job(
    image_id: int = 1, pass_: str = vision.GALLERY, filename: str = "Temple.webp", **kw: Any
) -> vision.Job:
    base: dict[str, Any] = {
        "image_id": image_id,
        "site_id": SITE,
        "filename": filename,
        "pass_": pass_,
        "stage": "G3",
        "site_name": "Temple of Test",
        "country": "Greece",
        "site_type": "Temple",
        "title": "Temple of Test east front",
        "title_source": "commons",
        "categories": ("Category:Temple of Test", "Category:CC-BY-SA-4.0"),
        "tier": "B",
    }
    base.update(kw)
    return vision.Job(**base)


def test_a_prompt_is_filled_from_the_job_and_nothing_else() -> None:
    text = vision.prompt_for(_job())
    assert '"Temple of Test" (Temple, Greece)' in text
    assert 'The file\'s Commons categories are: "CC-BY-SA-4.0"; "Temple of Test"' in text
    assert vision.prompt_for(_job(categories=None)).count(vision.CATEGORIES_UNKNOWN) == 1
    assert vision.prompt_for(_job(categories=())).count(vision.CATEGORIES_NONE) == 1


def test_a_job_survives_its_json_line_and_a_file_that_asks_twice_is_refused(tmp_path: Path) -> None:
    job = _job()
    assert vision.Job.from_json(json.loads(json.dumps(job.as_json()))) == job
    path = tmp_path / "JOBS.jsonl"
    vision.write_jobs(path, [job, _job(2)])
    assert [j.image_id for j in vision.read_jobs(path)] == [1, 2]
    vision.write_jobs(path, [job, _job(1, stage="G2")])
    with pytest.raises(vision.VisionError, match="twice"):
        vision.read_jobs(path)


# ======================================================================= verdict validation
@pytest.mark.parametrize(
    ("parsed", "problem"),
    [
        (None, "unparsable"),
        (
            {"kind": "photo", "other_site": False, "other_place": "", "subject": "x"},
            "out of vocabulary",
        ),
        (
            {"kind": "other", "other_site": "false", "other_place": "", "subject": "x"},
            "not a boolean",
        ),
        ({"kind": "other", "other_site": False, "subject": "x"}, "'other_place' is not a string"),
        (
            {"kind": "other", "other_site": False, "other_place": "", "subject": 5},
            "'subject' is not a string",
        ),
    ],
)
def test_a_gallery_answer_that_is_not_exactly_a_verdict_is_no_verdict(
    parsed: Any, problem: str
) -> None:
    verdict, why = vision.validate(vision.GALLERY, parsed)
    assert verdict is None and problem in str(why)


def test_a_hero_answer_needs_real_booleans() -> None:
    ok, _ = vision.validate(
        vision.HERO,
        {"shows_archaeology": True, "structure": "stone row", "generic_landscape": False, "x": 1},
    )
    assert ok == {"shows_archaeology": True, "structure": "stone row", "generic_landscape": False}
    bad, why = vision.validate(
        vision.HERO, {"shows_archaeology": 1, "structure": "", "generic_landscape": False}
    )
    assert bad is None and "not a boolean" in str(why)
    bad, why = vision.validate(
        vision.HERO, {"shows_archaeology": True, "structure": None, "generic_landscape": False}
    )
    assert bad is None and "'structure' is not a string" in str(why)


# ======================================================================= the judge
def _image_tree(root: Path, *names: str) -> Path:
    shard = root / SHARD
    shard.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(names):
        buf = io.BytesIO()
        Image.new("RGB", (64 + i, 48), (120, 90 + i, 60)).save(buf, format="WEBP")
        (shard / name).write_bytes(buf.getvalue())
    return root


GOOD = json.dumps(
    {"kind": "site_photo", "other_site": False, "other_place": "", "subject": "temple front"}
)


def _images(tmp_path: Path) -> vision.Images:
    main = _image_tree(tmp_path / "wiki", "Temple.webp")
    collisions = _image_tree(tmp_path / "collisions", "Gate.webp")
    return vision.Images((main, collisions))


def _answered(tmp_path: Path, job: vision.Job, text: str) -> Path:
    """Export the job through the stage's own export and answer it as an Opus agent would."""
    handoff = tmp_path / "handoff"
    ledger = vision.Ledger(tmp_path / "unused" / "VERDICTS.jsonl")
    counts, missing = vision.export_jobs([job], ledger, _images(tmp_path), handoff, dry_run=False)
    assert missing == [] and counts["exported"] + counts["already"] == 1
    OH.write_answer(
        handoff,
        batch_id=job.stage,
        stage=vision.HANDOFF_STAGE,
        label=vision.job_label(job),
        text=text,
        answered_by="test-agent",
        now=lambda: "2026-09-23T12:00:00+00:00",
    )
    return handoff


def _judge(tmp_path: Path) -> vision.Judge:
    return vision.Judge(
        handoff=tmp_path / "handoff",
        images=_images(tmp_path),
        now=lambda: "2026-09-23T10:00:00Z",
    )


def test_a_verdict_line_records_the_bytes_the_prompt_and_the_opus_answer(tmp_path: Path) -> None:
    _answered(tmp_path, _job(), GOOD)
    line = _judge(tmp_path)(_job())
    assert line["status"] == "ok" and line["verdict"]["kind"] == "site_photo"
    data = (tmp_path / "wiki" / SHARD / "Temple.webp").read_bytes()
    assert line["image_sha256"] == hashlib.sha256(data).hexdigest()
    assert line["image_file"] == f"{SHARD}/Temple.webp"
    assert line["prompt"] == vision.prompt_for(_job())
    assert line["prompt_sha256"] == GALLERY_SHA
    assert line["model"] == "anthropic/claude-opus-5-5 (Claude Code agent)"
    assert (line["metering"], line["cost_usd"]) == ("unmetered", 0.0)
    assert line["raw_response"] == GOOD and line["answered_by"] == "test-agent"


def test_the_case_collision_tree_is_searched_by_exact_name(tmp_path: Path) -> None:
    _answered(tmp_path, _job(filename="Gate.webp"), GOOD)
    judge = _judge(tmp_path)
    assert judge(_job(filename="Gate.webp"))["image_file"] == f"{SHARD}/Gate.webp"
    missing = judge(_job(filename="gate.webp"))  # a case-insensitive probe would accept this
    assert missing["status"] == "failed" and missing["error"].startswith("image: no offsite file")


@pytest.mark.parametrize(
    "answer",
    ["I think it is a temple", '{"kind": "ruin"}', "", '{"kind": "other", "other_site": "no"}'],
)
def test_an_answer_that_is_no_in_vocabulary_verdict_is_a_failed_line_never_other(
    tmp_path: Path, answer: str
) -> None:
    handoff = tmp_path / "handoff"
    if answer:
        _answered(tmp_path, _job(), answer)
        line = _judge(tmp_path)(_job())
        assert line["status"] == "failed" and line["verdict"] is None
        assert "other" not in json.dumps(line["verdict"]) and line["error"]
        assert line["raw_response"] == answer  # the answer is kept, never re-asked
    else:  # an empty answer is no answer at all: the helper refuses to write it
        vision.export_jobs(
            [_job()], vision.Ledger(tmp_path / "x"), _images(tmp_path), handoff, dry_run=False
        )
        with pytest.raises(OH.HandoffError, match="the text is empty"):
            OH.write_answer(
                handoff,
                batch_id="G3",
                stage=vision.HANDOFF_STAGE,
                label=vision.job_label(_job()),
                text=answer,
                answered_by="test-agent",
            )


def test_an_answer_about_other_bytes_than_todays_jpeg_is_a_failed_line(tmp_path: Path) -> None:
    """The answer was given about the exported JPEG: an image replaced since is not what it judged."""
    handoff = _answered(tmp_path, _job(), GOOD)
    (handoff / "images" / "1.jpg").write_bytes(b"\xff\xd8\xff another picture")
    line = _judge(tmp_path)(_job())
    assert line["status"] == "failed" and "is not today's JPEG" in line["error"]


def test_an_image_that_cannot_be_read_is_a_failed_line_and_costs_no_call(tmp_path: Path) -> None:
    judge = _judge(tmp_path)
    (tmp_path / "wiki" / SHARD / "Broken.webp").write_bytes(b"not an image")
    judge.images = vision.Images((tmp_path / "wiki",))
    line = judge(_job(filename="Broken.webp"))  # no answer exists: none is read
    assert line["status"] == "failed" and "cannot be read as an image" in line["error"]


def test_the_export_hands_off_the_exact_jpeg_the_pilot_sent_and_the_import_writes_the_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _image_tree(tmp_path / "wiki", "Temple.webp")
    real = vision.Images
    monkeypatch.setattr(vision, "Images", lambda: real((root,)))
    jobs = tmp_path / "JOBS.jsonl"
    handoff = tmp_path / "handoff"
    vision.write_jobs(jobs, [_job(1), _job(1, pass_=vision.HERO)])
    base = ["--jobs", str(jobs), "--run-dir", str(tmp_path / "run"), "--handoff", str(handoff)]

    assert vision.main(["import", *base]) == vision.EXIT_INPUT  # nothing handed off yet
    assert not (tmp_path / "run" / "VERDICTS.jsonl").exists()
    assert vision.main(["export", *base]) == vision.EXIT_OK
    jpeg = vlm_bytes(root / SHARD / "Temple.webp")
    assert (handoff / "images" / "1.jpg").read_bytes() == jpeg  # RGB, 1280, q85: the pilot's
    lines = OH.manifest(handoff)
    assert [(line["label"], line["field"]) for line in lines] == [
        ("1/gallery-v1", "gallery"),
        ("1/hero-v1", "hero"),
    ]
    assert (handoff / lines[1]["prompt_path"]).read_text(encoding="utf-8") == vision.prompt_for(
        _job(1, pass_=vision.HERO)
    )
    answers = {
        "gallery": GOOD,
        "hero": '```json\n{"shows_archaeology": true, "structure": "temple", '
        '"generic_landscape": false}\n```',
    }
    for line in lines:
        OH.write_answer(
            handoff,
            batch_id=line["batch_id"],
            stage=line["stage"],
            label=line["label"],
            text=answers[line["field"]],
            answered_by="test-agent",
        )
    assert OH.validate(handoff).ok
    assert vision.main(["import", *base]) == vision.EXIT_OK
    ledger = vision.Ledger(tmp_path / "run" / "VERDICTS.jsonl")
    assert [e.line["status"] for e in ledger.lines] == ["ok", "ok"]
    assert set(vision.verdicts_by_image(ledger.lines, vision.HERO_PROMPT_ID)) == {1}
    assert vision.main(["export", *base]) == vision.EXIT_OK  # nothing left to hand off
    assert "2 already in the ledger, 0 handed off" in capsys.readouterr().out.splitlines()[-1]


# ======================================================================= ledger and run
def _ok_line(
    image_id: int, cost: float = 0.001, prompt: str = vision.GALLERY, **verdict: Any
) -> dict[str, Any]:
    prompt_id, template = vision.PROMPTS[prompt]
    default = (
        {"kind": "site_photo", "other_site": False, "other_place": "", "subject": "x"}
        if prompt == vision.GALLERY
        else {"shows_archaeology": True, "structure": "ruin", "generic_landscape": False}
    )
    default.update(verdict)
    return {
        "image_id": image_id,
        "site_id": SITE,
        "pass": prompt,
        "stage": "G3",
        "tier": "B",
        "model": vision.MODEL,
        "prompt_id": prompt_id,
        "prompt_sha256": vision.prompt_sha256(template),
        "image_sha256": f"img{image_id}",
        "status": "ok",
        "verdict": default,
        "error": None,
        "cost_usd": cost,
        "latency_ms": 1000,
        "judged_at": "2026-09-23T10:00:00Z",
    }


def test_a_verdict_id_is_the_sha256_of_its_line_and_a_torn_line_stops_the_reader(
    tmp_path: Path,
) -> None:
    ledger = vision.Ledger(tmp_path / "VERDICTS.jsonl")
    entry = ledger.append(_ok_line(1))
    text = (tmp_path / "VERDICTS.jsonl").read_text(encoding="utf-8").rstrip("\n")
    assert entry.verdict_id == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert [e.verdict_id for e in vision.Ledger(tmp_path / "VERDICTS.jsonl").lines] == [
        entry.verdict_id
    ]
    with open(tmp_path / "VERDICTS.jsonl", "a", encoding="utf-8") as handle:
        handle.write('{"image_id": 2, "status": "ok"\n')
    with pytest.raises(vision.VisionError, match="damaged ledger line"):
        vision.Ledger(tmp_path / "VERDICTS.jsonl")


def _scripted(results: dict[int, str]):
    def judge(job: vision.Job) -> dict[str, Any]:
        line = _ok_line(job.image_id)
        if results.get(job.image_id) == "fail":
            line.update(status="failed", verdict=None, error="unparsable JSON in the response")
        return line

    return judge


def test_a_failed_judgement_stops_new_calls_and_exits_3(tmp_path: Path) -> None:
    ledger = vision.Ledger(tmp_path / "VERDICTS.jsonl")
    jobs = [_job(i) for i in range(1, 6)]
    result = vision.run_jobs(jobs, ledger, _scripted({2: "fail"}), workers=1, budget_usd=75)
    assert result.judged == 2 and result.exit_code == vision.EXIT_NO_VERDICT
    assert [e.line["image_id"] for e in ledger.lines] == [1, 2] and not ledger.lines[1].ok


def test_the_budget_is_read_from_the_ledger_and_stops_before_the_next_call(tmp_path: Path) -> None:
    ledger = vision.Ledger(tmp_path / "VERDICTS.jsonl")
    ledger.append({**_ok_line(99, cost=0.6), "status": "failed", "verdict": None})
    ledger.append(_ok_line(98, cost=0.4))
    resumed = vision.Ledger(tmp_path / "VERDICTS.jsonl")
    assert resumed.spent_usd == pytest.approx(1.0)  # the failed line's cost counts too
    result = vision.run_jobs([_job(1), _job(2)], resumed, _scripted({}), workers=2, budget_usd=1.0)
    assert result.judged == 0 and result.budget_stop and result.exit_code == vision.EXIT_BUDGET
    more = vision.run_jobs(
        [_job(1), _job(2), _job(3)], resumed, _scripted({}), workers=1, budget_usd=1.0015
    )
    # 1.000 and 1.001 are below the budget, so jobs 1 and 2 start; at 1.002 job 3 does not
    assert more.judged == 2 and more.budget_stop and more.exit_code == vision.EXIT_BUDGET
    last = vision.run_jobs([_job(3)], resumed, _scripted({}), workers=1, budget_usd=5)
    assert last.judged == 1 and not last.budget_stop and last.exit_code == vision.EXIT_OK


def test_a_resumed_run_asks_no_question_the_ledger_already_answered(tmp_path: Path) -> None:
    ledger = vision.Ledger(tmp_path / "VERDICTS.jsonl")
    vision.run_jobs([_job(1), _job(2)], ledger, _scripted({2: "fail"}), workers=1, budget_usd=75)
    asked: list[int] = []

    def judge(job: vision.Job) -> dict[str, Any]:
        asked.append(job.image_id)
        return _ok_line(job.image_id)

    result = vision.run_jobs(
        [_job(1), _job(2), _job(1, pass_=vision.HERO)],
        vision.Ledger(tmp_path / "VERDICTS.jsonl"),
        judge,
        workers=1,
        budget_usd=75,
    )
    assert asked == [2, 1] and result.skipped_done == 1


def test_a_verdict_counts_only_under_the_frozen_prompt_and_the_pilot_model() -> None:
    lines = [vision.LedgerLine(str(i), _ok_line(i)) for i in (1, 2)]
    assert set(vision.verdicts_by_image(lines, vision.GALLERY_PROMPT_ID)) == {1, 2}
    other_prompt = [vision.LedgerLine("x", {**_ok_line(3), "prompt_sha256": "0" * 64})]
    with pytest.raises(vision.VisionError, match="another gallery-v1"):
        vision.verdicts_by_image(other_prompt, vision.GALLERY_PROMPT_ID)
    # The pilot's transport answered the calibration before the owner order; those count no more.
    other_model = [vision.LedgerLine("y", {**_ok_line(3), "model": "deepseek-v4-flash-vision-exp"})]
    with pytest.raises(vision.VisionError, match="answered by"):
        vision.verdicts_by_image(other_model, vision.GALLERY_PROMPT_ID)
    twice = [vision.LedgerLine("a", _ok_line(4)), vision.LedgerLine("b", _ok_line(4))]
    with pytest.raises(vision.VisionError, match="two ok verdicts"):
        vision.verdicts_by_image(twice, vision.GALLERY_PROMPT_ID)


# ======================================================================= worklist
def _row(image_id: int, site: str = SITE, tier: str = "C", **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": image_id,
        "site_id": site,
        "filename": f"File {image_id}.webp",
        "title": f"File {image_id}",
        "original_url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/File_{image_id}.jpg",
        "commons_page_url": f"https://commons.wikimedia.org/wiki/File%3AFile%20{image_id}.jpg",
        "is_hero": False,
        "is_lead": False,
        "sort_order": image_id,
        "is_excluded": False,
        "source_type": "wikimedia",
        "license": "CC BY-SA 4.0",
        "author": "Someone",
        "width": 1600,
        "height": 1067,
        "_tier": tier,
        "_tier_reason": "",
        "_commons": f"File_{image_id}.jpg",
        "_categories": ["Category:Temple"],
        "image_kind": None,  # `build_state` gives every row the column (NULL before G0)
    }
    row.update(kw)
    return row


def _state(rows: list[dict[str, Any]], sites: list[str] | None = None) -> worklist.State:
    sites = sites or sorted({r["site_id"] for r in rows})
    return worklist.State(
        sites=[
            {
                "id": s,
                "name": f"Site {s[:4]}",
                "country": "Greece",
                "site_type": "Temple",
                "source_id": "ancient_nerds",
            }
            for s in sites
        ],
        by_site={s: [r for r in rows if r["site_id"] == s] for s in sites},
        exported_at="x",
    )


def test_the_served_image_is_the_pages_own_order_with_nulls_last() -> None:
    rows = [
        _row(5, sort_order=None),
        _row(3, sort_order=2),
        _row(4, sort_order=2),
        _row(9, is_lead=True, sort_order=9),
    ]
    assert worklist.served_row(rows)["id"] == 9
    rows.append(_row(11, is_hero=True, sort_order=50))
    assert worklist.served_row(rows)["id"] == 11
    rows[-1]["is_excluded"] = True
    assert worklist.served_row(rows)["id"] == 9
    assert (
        worklist.served_row(
            [_row(5, sort_order=None), _row(3, sort_order=2), _row(4, sort_order=2)]
        )["id"]
        == 3
    )
    assert worklist.served_row([_row(1, is_excluded=True)]) is None


def _retier(
    rows: list[dict[str, Any]],
    moves: dict[int, tuple[bool, bool]],
    census: dict[int, str],
    tiers: dict[int, str],
):
    return worklist.retier(
        [{"id": SITE}], {SITE: rows}, moves, census, lambda row, sid: (tiers[int(row["id"])], "t")
    )


def test_retiering_is_proven_against_the_census_for_every_unmoved_row() -> None:
    rows = [_row(1, is_hero=True), _row(2), _row(3)]
    moves = {1: (True, False), 2: (False, True)}
    out, report = _retier(rows, moves, {1: "A", 2: "D", 3: "C"}, {1: "B", 2: "D", 3: "C"})
    assert [(r["id"], r["is_hero"], r["_tier"]) for r in out[SITE]] == [
        (1, False, "B"),
        (2, True, "A"),
        (3, False, "C"),
    ]
    assert report == {"promoted": 1, "demoted": 1, "demoted_retiered": {"B": 1}}
    with pytest.raises(worklist.WorklistError, match="not T10's"):
        _retier(rows, moves, {1: "A", 2: "D", 3: "D"}, {1: "B", 2: "D", 3: "C"})


def test_a_hero_move_that_does_not_fit_the_snapshot_or_the_repair_is_refused() -> None:
    rows = [_row(1, is_hero=True), _row(2)]
    with pytest.raises(worklist.WorklistError, match="expects is_hero=False"):
        _retier(rows, {1: (False, True)}, {1: "A", 2: "C"}, {1: "C", 2: "C"})
    with pytest.raises(worklist.WorklistError, match="promoted to hero from census tier B"):
        _retier(rows, {1: (True, False), 2: (False, True)}, {1: "A", 2: "B"}, {1: "C", 2: "B"})
    with pytest.raises(worklist.WorklistError, match="demoted from census tier C"):
        _retier([_row(1, is_hero=True)], {1: (True, False)}, {1: "C"}, {1: "C"})
    with pytest.raises(worklist.WorklistError, match="does not hold"):
        _retier(rows, {7: (True, False)}, {1: "A", 2: "C"}, {1: "C", 2: "C"})


def test_the_hero_plan_is_read_strictly(tmp_path: Path) -> None:
    path = tmp_path / "PLAN.jsonl"
    path.write_text(
        json.dumps({"image_id": 1, "old_is_hero": True, "new_is_hero": False}) + "\n",
        encoding="utf-8",
    )
    assert worklist.load_hero_moves(path) == {1: (True, False)}
    path.write_text(
        json.dumps({"image_id": 1, "old_is_hero": "true", "new_is_hero": False}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(worklist.WorklistError, match="not a hero move"):
        worklist.load_hero_moves(path)
    line = json.dumps({"image_id": 1, "old_is_hero": True, "new_is_hero": False})
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(worklist.WorklistError, match="moved twice"):
        worklist.load_hero_moves(path)


def test_the_stage_builders_pick_what_the_design_names() -> None:
    other = "ffffffff-0000-4000-8000-000000000000"
    rows = [
        _row(1, tier="A", is_hero=True),
        _row(2, tier="B"),
        _row(3, tier="B", is_excluded=True),
        _row(4, tier="C"),
        _row(5, tier="C"),
        _row(6, tier="C"),
        _row(7, tier="C"),
        _row(8, tier="D"),
        _row(20, site=other, tier="C", title=None, _commons=None, _categories=None),
    ]
    state = _state(rows, [SITE, other])
    assert [j.image_id for j in worklist.g3_jobs(state)] == [1, 20]
    assert [j.image_id for j in worklist.g2_jobs(state)] == [2]
    probes = worklist.g4_jobs(state)
    assert len([j for j in probes if j.site_id == SITE]) == 3 and {j.image_id for j in probes} <= {
        4,
        5,
        6,
        7,
        20,
    }
    ranked = sorted([4, 5, 6, 7], key=lambda i: worklist.probe_rank(worklist.G4_SEED, i))[:3]
    assert [j.image_id for j in probes if j.site_id == SITE] == ranked
    assert [j.image_id for j in worklist.escalation_jobs(state, [SITE])] == [1, 2, 4, 5, 6, 7, 8]
    strict = worklist.strict_jobs(
        state, {1: {"kind": "site_photo"}, 2: {"kind": "artifact"}}, [1, 2, 4], worklist.G3_STRICT
    )
    assert [(j.image_id, j.pass_) for j in strict] == [(1, vision.HERO)]
    job = worklist.g3_jobs(state, [other])[0]
    assert (
        job.title_source == "wiki_images.title"
        and job.categories is None
        and job.title == "File 20"
    )
    assert worklist.g3_jobs(state, [SITE])[0].title == "File 1"


def test_chunks_are_100_sites_in_export_order() -> None:
    sites = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(250, 0, -1)]
    state = _state([], sites)
    got = worklist.chunks(state)
    assert [len(c) for c in got] == [100, 100, 50] and got[0][0] == sites[0]


@pytest.fixture(scope="module")
def snapshot_state() -> worklist.State:
    """The snapshot plus the hero moves - about 25 s, so built once per module."""
    return worklist.build_state(SNAPSHOT, CACHE, HERO_MOVES, T10_FINDINGS)


@needs_state
def test_the_current_state_reproduces_the_census_and_the_measured_tiers(
    snapshot_state: worklist.State,
) -> None:
    counts = worklist.tier_counts(snapshot_state)
    assert counts["promoted"] == counts["demoted"] == 2719
    assert counts["live_rows_by_tier"]["B"] == 9884 and counts["sites_serving_an_image"] == 3992
    # T10 reads "own name in the filename" from the local file name, and every demoted hero is
    # called hero.webp - so none of them can be tier D (the design's estimate said 2,146).
    assert counts["demoted_retiered"] == {"B": 383, "C": 2336}


LIVENESS_STORE = REPO / "output" / "remediation" / "gallery_audit" / "liveness-2026-09-23"
G0_PLAN = REPO / "output" / "remediation" / "gallery_audit" / "PLAN.jsonl"
DEAD_ROWS = {107331, 97070, 80453, 87352, 87351, 70233}


@needs_state
def test_the_snapshot_state_is_refused_once_the_liveness_write_exists(
    snapshot_state: worklist.State,
) -> None:
    lines = liveness.load_store(LIVENESS_STORE / "NOT_LIVE.jsonl")
    with pytest.raises(worklist.WorklistError, match="fold the liveness write in"):
        worklist.liveness_blocked(lines, snapshot_state.by_site)


@needs_state
def test_the_liveness_write_and_g0_fold_into_the_current_state() -> None:
    state = worklist.build_state(
        SNAPSHOT,
        CACHE,
        HERO_MOVES,
        T10_FINDINGS,
        kinds_from=[G0_PLAN],
        applied=[LIVENESS_STORE / "PLANNED.jsonl"],
    )
    lines = liveness.load_store(LIVENESS_STORE / "NOT_LIVE.jsonl")
    assert set(worklist.liveness_blocked(lines, state.by_site)) == DEAD_ROWS
    assert all(state.row(i)["is_excluded"] and not state.row(i)["is_hero"] for i in DEAD_ROWS)
    assert state.row(75145)["_commons"] == "Forum_Romanum_-_panoramio_(3).jpg"
    assert sum(1 for rows in state.by_site.values() for r in rows if r["image_kind"]) == 105
    counts = worklist.tier_counts(state)
    # Dedan's two images were both deleted: the site serves nothing; every other count holds
    assert counts["sites_serving_an_image"] == 3991
    assert counts["live_rows_by_tier"] == {"A": 3857, "B": 9884, "C": 25925, "D": 9360}


# ======================================================================= labels
def _keyed(*rows: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {**r, "_keys": [labels.norm(r["filename"]), labels.norm(r.get("title") or "")]}
        for r in rows
    ]


def test_an_entry_is_matched_to_the_longest_name_it_starts_with() -> None:
    rows = _keyed(
        _row(
            1,
            filename="Berlín_-_Pergamon_-_Porta_d'Ishtar_-_Lleons.webp",
            title="Berlín - Pergamon - Porta d'Ishtar - Lleons",
        ),
        _row(2, filename="Berlín,_Museo_de_Pérgamo_05.webp", title="Berlín, Museo de Pérgamo 05"),
    )
    rest = "Berlín - Pergamon - Porta d'Ishtar - Lleons - Kat. 'Striding Lions from Babylon' - Museumsaufnahme Berlin."
    assert labels.match_entry(rows, rest, False)["id"] == 1


def test_the_hero_mark_breaks_a_tie_and_an_ambiguous_hint_matches_nothing() -> None:
    rows = _keyed(
        _row(1, filename="hero.webp", title="Gamzigrad", is_hero=True),
        _row(2, filename="Gamzigrad.webp", title="Gamzigrad"),
    )
    assert labels.match(rows, "Gamzigrad", hero=True)["id"] == 1
    assert labels.match(rows, "Gamzigrad", hero=False)["id"] == 2
    assert labels.match(rows, "Gamzigrad") is None


def test_the_tracked_fixture_carries_the_measured_counts() -> None:
    rows = labels.load_labelled()
    assert len(rows) == 652 and len({r.site_id for r in rows}) == 40
    assert sum(r.foreign for r in rows) == 64 >= 60  # T-X1 asks for 60 of the plan's 65
    assert sum(r.non_photo for r in rows) == 64
    meta = json.loads(labels.FIXTURE_META.read_text(encoding="utf-8"))
    fixture_text = labels.FIXTURE.read_text(encoding="utf-8")  # LF, whatever the checkout did
    assert meta["fixture_sha256"] == hashlib.sha256(fixture_text.encode("utf-8")).hexdigest()
    assert meta["rows"] == 652 and len(meta["unresolved_entries"]) == 6


@needs_label_source
def test_the_fixture_is_derived_byte_for_byte_and_every_collection_span_is_verbatim(
    tmp_path: Path,
) -> None:
    from census.snapshot import Snapshot

    lines, meta = labels.derive(labels.LABELS_SOURCE, Snapshot(SNAPSHOT))
    out = tmp_path / "labels.jsonl"
    labels.write_fixture(lines, meta, out, tmp_path / "labels.meta.json")
    assert out.read_text(encoding="utf-8") == labels.FIXTURE.read_text(encoding="utf-8")
    entries = [
        p
        for block in json.loads(labels.LABELS_SOURCE.read_text(encoding="utf-8"))
        for p in block["problems"]
    ]
    for collection in labels.COLLECTIONS:
        entry = next(e for e in entries if e.startswith(collection.entry_start))
        assert all(member.span in entry for member in collection.members)


class _Snap:
    """The three things `derive` reads from a snapshot."""

    def __init__(self, sites: list[dict[str, Any]], images: list[dict[str, Any]]) -> None:
        self.sites = sites
        self._images = images

    def images(self, site_id: str) -> list[dict[str, Any]]:
        return [row for row in self._images if row["site_id"] == site_id]

    def exported_at(self) -> str:
        return "2026-09-20T20:20:01+02:00"


def _cobata(tmp_path: Path, problems: list[str], checked: int) -> tuple[Path, _Snap]:
    source = tmp_path / "labels.json"
    block = {"name": "La Cobata", "checked": checked, "usable": 0, "problems": problems}
    source.write_text(json.dumps([block]), encoding="utf-8")
    rows = [
        _row(1, filename="San_Lorenzo_Colossal_Head_10.webp", title="San Lorenzo Colossal Head 10"),
        _row(2, filename="Olmec2.webp", title="Olmec2"),
        _row(3, filename="Old.webp", title="Old", is_excluded=True),
    ]
    return source, _Snap([{"id": SITE, "name": "La Cobata"}], rows)


def test_derive_resolves_single_entries_and_refuses_a_span_its_entry_does_not_hold(
    tmp_path: Path,
) -> None:
    source, snap = _cobata(tmp_path, ["karte_oder_plan: Olmec2.webp - a map"], 2)
    lines, meta = labels.derive(source, snap)
    assert [(line["image_id"], line["labels"]) for line in lines] == [
        (1, []),
        (2, ["karte_oder_plan"]),
    ]
    assert meta["rows"] == 2 and meta["matched"] == {"single": 1}
    source, snap = _cobata(
        tmp_path, ["fremde_staette: San_Lorenzo_Colossal_Head_10.webp - no list here"], 2
    )
    with pytest.raises(labels.LabelError, match="is not in its entry"):
        labels.derive(source, snap)


def test_derive_refuses_a_checked_count_that_is_not_the_live_rows(tmp_path: Path) -> None:
    source, snap = _cobata(tmp_path, [], 3)  # 3 rows, one of them excluded: 2 were checked
    with pytest.raises(labels.LabelError, match="checked population"):
        labels.derive(source, snap)


def test_a_collection_member_must_name_exactly_one_row() -> None:
    rows = _keyed(
        _row(1, filename="Thesanctuary.webp"), _row(2, filename="ThesanctuaryWilliamStukeley.webp")
    )
    with pytest.raises(labels.LabelError, match="matches 2 rows"):
        labels._member_row(rows, labels.Member("x", "thesanctuary"))
    assert labels._member_row(rows, labels.Member("x", "thesanctuary", "exact"))["id"] == 1


def test_the_gold_rows_are_named_verbatim_by_their_records() -> None:
    notes = labels.gold_notes()
    assert set(notes) == set(labels.GOLD_SITE_IDS)
    for gold in labels.GOLD_ROWS:
        assert gold.quote in notes[gold.site_id], gold
    assert (
        sum(g.foreign for g in labels.GOLD_ROWS) == 12
        and sum(not g.foreign for g in labels.GOLD_ROWS) == 13
    )


@needs_snapshot
def test_the_gold_rows_are_the_snapshot_rows_they_claim() -> None:
    rows = {}
    with gzip.open(SNAPSHOT / "wiki_images.jsonl.gz", "rt", encoding="utf-8") as handle:
        for text in handle:
            row = json.loads(text)
            if row["site_id"] in labels.GOLD_SITE_IDS:
                rows[row["id"]] = row
    assert len(rows) == 42
    for gold in labels.GOLD_ROWS:
        assert (rows[gold.image_id]["site_id"], rows[gold.image_id]["filename"]) == (
            gold.site_id,
            gold.filename,
        )


def test_the_pilot_tiles_are_200_with_their_pilot_kinds() -> None:
    tiles = labels.pilot_tiles()
    assert len(tiles) == 200 and {t.tier for t in tiles} == {"A", "B", "C", "D"}
    assert sum(t.tier == "A" for t in tiles) == 50 and all(
        t.pilot_kind in vision.KINDS for t in tiles
    )


def test_eye_labels_are_refused_outside_the_sample_or_the_vocabulary(tmp_path: Path) -> None:
    tiles = labels.pilot_tiles()
    path = tmp_path / "LABELS.jsonl"
    first = tiles[0].image_id
    path.write_text(
        json.dumps({"image_id": first, "human_kind": "site_photo", "shows_archaeology": True})
        + "\n",
        encoding="utf-8",
    )
    assert labels.load_eye_labels(path, tiles)[first].shows_archaeology is True
    for bad, why in (
        ({"image_id": 1, "human_kind": None}, "not a pilot tile"),
        ({"image_id": first, "human_kind": "photo"}, "not one of the six"),
        ({"image_id": first, "human_kind": None, "shows_archaeology": "yes"}, "not a boolean"),
    ):
        path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with pytest.raises(labels.LabelError, match=why):
            labels.load_eye_labels(path, tiles)


# ======================================================================= decide
def test_the_rule_table_is_sealed() -> None:
    assert decide.rules_sha256() == RULES_SHA
    assert set(decide.RULES) == {
        "K1",
        "K2",
        "X1",
        "X2",
        "X3",
        "H1",
        "R1",
        "A1",
        "A2",
        "A3",
        "A4",
        "L1",
        "L2",
        "T1",
    }


def _v(image_id: int, prompt: str = vision.GALLERY, **verdict: Any) -> vision.Verdict:
    line = _ok_line(image_id, prompt=prompt, **verdict)
    return vision.Verdict(f"vid{image_id}{prompt[0]}", dict(line["verdict"]), line)


def _admission(
    kind: bool = False, strict: bool = False, x1: bool = False, x2: bool = False, x3: bool = False
) -> decide.Admission:
    return decide.Admission(kind, strict, x1, x2, x3, thresholds_sha256="t", admission_sha256="adm")


ALL = _admission(kind=True, strict=True, x1=True, x2=True, x3=True)
NONE = _admission()
TRUTH_BIG = {"status": "ok", "width": 4000, "height": 3000}


def _truth(*ids: int, record: dict[str, Any] = TRUTH_BIG) -> dict[str, dict[str, Any]]:
    return {f"File_{i}.jpg": dict(record) for i in ids}


def test_nothing_is_written_that_calibration_did_not_admit() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2)]}
    gallery = {1: _v(1, kind="people"), 2: _v(2, kind="map_or_document", other_site=True)}
    planned, _ = decide.plan_vision(rows, {}, gallery, {}, NONE, _truth(1, 2), {})
    assert planned == []


def test_kind_writes_need_admission_and_never_overwrite_a_recorded_kind() -> None:
    rows = {SITE: [_row(1, tier="B"), _row(2, tier="B"), _row(3, tier="B")]}
    gallery = {1: _v(1, kind="artifact"), 2: _v(2, kind="artifact"), 3: _v(3, kind="site_photo")}
    only_kind = _admission(kind=True)
    planned, listed = decide.plan_vision(
        rows, {2: "site_photo"}, gallery, {3: _v(3, vision.HERO)}, only_kind, {}, {}
    )
    assert [(p.key, p.column, p.old, p.new, p.rule) for p in planned] == [
        (1, "image_kind", None, "artifact", "K1")
    ]
    assert "not overwritten" in listed[0]["why"]
    planned, _ = decide.plan_vision(rows, {}, gallery, {3: _v(3, vision.HERO)}, ALL, {}, {})
    assert ("image_kind", "site_photo", "K2") in {
        (p.column, p.new, p.rule) for p in planned if p.key == 3
    }
    planned, _ = decide.plan_vision(
        rows, {}, gallery, {3: _v(3, vision.HERO, shows_archaeology=False)}, ALL, {}, {}
    )
    assert not [p for p in planned if p.key == 3]  # an unconfirmed site_photo stays NULL


def test_exclusions_spare_manual_rows_and_artifacts_and_take_the_heros_flag_with_them() -> None:
    rows = {
        SITE: [_row(1, is_hero=True, tier="A"), _row(2, source_type="manual"), _row(3), _row(4)]
    }
    gallery = {
        1: _v(1, other_site=True),
        2: _v(2, kind="people"),
        3: _v(3, kind="artifact"),
        4: _v(4, kind="other"),
    }
    no_kind = _admission(x1=True, x2=True, x3=True)
    planned, _ = decide.plan_vision(rows, {}, gallery, {}, no_kind, {}, {})
    got = {(p.key, p.column, p.rule, p.role) for p in planned}
    assert got == {
        (1, "is_excluded", "X1", "exclude"),
        (1, "is_hero", "X1", "hero-drop"),
        (4, "is_excluded", "X3", "exclude"),
    }
    evidence = next(p for p in planned if p.key == 1).evidence
    assert (
        evidence["verdict_id"] == "vid1g"
        and evidence["prompt_sha256"] == GALLERY_SHA
        and evidence["rules_sha256"] == RULES_SHA
        and evidence["admission_sha256"] == "adm"  # the admission that allowed X1
    )


def test_the_hero_moves_to_the_best_strict_confirmed_candidate() -> None:
    rows = {
        SITE: [
            _row(1, is_hero=True, tier="A"),
            _row(2, tier="C"),
            _row(3, tier="D"),
            _row(4, tier="D"),
            _row(5, tier="D", license="CC BY 4.0", author=None),
        ]
    }
    gallery = {i: _v(i) for i in (2, 3, 4, 5)} | {1: _v(1, kind="painting_or_artwork")}
    hero = {i: _v(i, vision.HERO) for i in (2, 3, 4, 5)}
    # 4 and 5 outrank 3 on true area, so only their refusals keep them out: 4's 1600 px derivative
    # is 600 px high, and 5 lacks the author its licence needs
    truth = _truth(1, 2, 3) | {
        "File_4.jpg": {"status": "ok", "width": 8000, "height": 3000},
        "File_5.jpg": {"status": "ok", "width": 6000, "height": 4500},
    }
    planned, _ = decide.plan_vision(
        rows, {}, gallery, hero, _admission(kind=True, strict=True), truth, {}
    )
    moves = [(p.key, p.old, p.new, p.role) for p in planned if p.column == "is_hero"]
    assert moves == [(1, True, False, "hero-demote"), (3, False, True, "hero-promote")]
    decide.check_plan(planned, rows)


def test_no_hero_moves_unless_calibration_admitted_the_strict_pass() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="D")]}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2)}
    hero = {2: _v(2, vision.HERO)}  # G3-strict writes hero verdicts whether or not T-strict passed
    planned_rows, _ = decide.plan_vision(
        rows, {}, gallery, hero, _admission(kind=True), _truth(1, 2), {}
    )
    assert [p for p in planned_rows if p.column == "is_hero"] == []
    assert decide.plan_vision(
        rows, {}, gallery, hero, _admission(kind=True, strict=True), _truth(1, 2), {}
    )[0]  # the same verdicts move the hero once T-strict is admitted


def test_h1_never_promotes_a_photo_the_first_pass_placed_elsewhere() -> None:
    # X1 is not admitted, so the neighbour's mound (other_site=true) stays live - the Agri case
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="D"), _row(3, tier="C")]}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2, other_site=True), 3: _v(3)}
    hero = {2: _v(2, vision.HERO), 3: _v(3, vision.HERO)}
    planned_rows, _ = decide.plan_vision(
        rows, {}, gallery, hero, _admission(kind=True, strict=True), _truth(1, 2, 3), {}
    )
    assert [(p.key, p.new) for p in planned_rows if p.column == "is_hero"] == [
        (1, False),
        (3, True),
    ]


def test_a_failing_served_image_without_a_candidate_keeps_its_hero_and_is_listed() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="C")]}
    gallery = {1: _v(1), 2: _v(2)}
    hero = {
        1: _v(1, vision.HERO, shows_archaeology=False),
        2: _v(2, vision.HERO, shows_archaeology=False),
    }
    planned, listed = decide.plan_vision(rows, {}, gallery, hero, ALL, _truth(1, 2), {})
    assert [p for p in planned if p.column == "is_hero"] == []
    assert any("no strict-confirmed candidate" in item["why"] for item in listed)


def _live_line(name: str, cls: str, ids: list[int], **kw: Any) -> dict[str, Any]:
    line: dict[str, Any] = dict.fromkeys(liveness.LINE_KEYS)
    line.update({"file": name, "class": cls, "image_ids": ids, "requested_title": f"File:{name}"})
    line.update(kw)
    return line


def test_a_deleted_file_is_excluded_and_its_hero_replaced_by_the_repairs_own_rule() -> None:
    rows = {
        SITE: [
            _row(1, is_hero=True, tier="A", width=800, height=533),
            _row(2, tier="C"),
            _row(3, tier="D", width=1600, height=1200),
        ]
    }
    line = _live_line(
        "File_1.jpg",
        liveness.DELETED_COPYVIO,
        [1],
        log={"logid": 7, "type": "delete", "action": "delete"},
    )
    planned, listed = decide.plan_liveness([line], rows, _truth(2, 3))
    assert [(p.key, p.column, p.new, p.role) for p in planned] == [
        (1, "is_excluded", True, "exclude"),
        (1, "is_hero", False, "hero-drop"),
        (3, "is_hero", True, "hero-promote"),
    ]
    assert (
        planned[0].evidence["liveness_sha256"] == liveness.line_sha256(line)
        and planned[0].evidence["logid"] == 7
    )
    decide.check_plan(planned, rows)


def test_a_moved_file_gets_both_urls_of_its_live_target_unless_a_sibling_holds_them() -> None:
    target_url = (
        "https://upload.wikimedia.org/wikipedia/commons/1/12/Forum_Romanum_-_panoramio_(3).jpg"
    )
    line = _live_line(
        "Old.jpg",
        liveness.MOVED_WITHOUT_REDIRECT,
        [1],
        log={"logid": 9},
        move_target={
            "title": "File:Forum Romanum - panoramio (3).jpg",
            "class": liveness.LIVE,
            "url": target_url,
        },
    )
    rows = {SITE: [_row(1), _row(2)]}
    planned, _ = decide.plan_liveness([line], rows, {})
    assert {(p.column, p.new) for p in planned} == {
        ("original_url", target_url),
        # the downloader's spelling of a page URL: the title with its spaces, quoted
        (
            "commons_page_url",
            "https://commons.wikimedia.org/wiki/File%3AForum%20Romanum%20-%20panoramio%20%283%29.jpg",
        ),
    }
    rows[SITE][1]["original_url"] = target_url
    planned, listed = decide.plan_liveness([line], rows, {})
    assert planned == [] and "already carries the target URL" in listed[0]["why"]
    dead = _live_line(
        "Old.jpg",
        liveness.MOVED_WITHOUT_REDIRECT,
        [1],
        move_target={"title": "File:X.jpg", "class": "missing", "url": None},
    )
    assert "is not a live file" in decide.plan_liveness([dead], {SITE: [_row(1)]}, {})[1][0]["why"]
    redirected = _live_line(
        "Old.jpg",
        liveness.MOVED_WITHOUT_REDIRECT,
        [1],
        move_target={
            "title": "File:X.jpg",
            "class": liveness.MOVED_WITH_REDIRECT,  # the target itself only redirects now
            "url": "https://upload.wikimedia.org/wikipedia/commons/1/12/Y.jpg",
        },
    )
    planned, listed = decide.plan_liveness([redirected], {SITE: [_row(1)]}, {})
    assert planned == [] and "is not a live file" in listed[0]["why"]


def test_a_plan_that_breaks_the_hero_invariants_is_refused() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2)]}
    promote = decide.PlannedRow(
        "wiki_images", 2, SITE, "is_hero", False, True, "H1", "hero-promote", {}
    )
    with pytest.raises(decide.DecideError, match="2 heroes"):
        decide.check_plan([promote], rows)
    exclude = decide.PlannedRow(
        "wiki_images", 1, SITE, "is_excluded", False, True, "X1", "exclude", {}
    )
    with pytest.raises(decide.DecideError, match="hero is excluded"):
        decide.check_plan([exclude], rows)
    with pytest.raises(decide.DecideError, match="planned twice"):
        decide.check_plan([exclude, exclude], rows)
    kind = decide.PlannedRow("wiki_images", 2, SITE, "image_kind", None, "photo", "K1", "kind", {})
    with pytest.raises(decide.DecideError, match="outside the vocabulary"):
        decide.check_plan([kind], rows)


def test_the_served_image_state_names_every_case() -> None:
    gallery = {1: _v(1), 2: _v(2, other_site=True), 3: _v(3), 4: _v(4)}
    hero = {3: _v(3, vision.HERO), 4: _v(4, vision.HERO, shows_archaeology=False)}
    state = decide.served_state
    assert state(1, {1}, gallery, hero) == decide.FAILS
    assert state(9, set(), gallery, hero) == decide.UNJUDGED
    assert state(1, set(), gallery, hero) == decide.PENDING
    assert state(2, set(), gallery, hero) == decide.FAILS
    assert state(3, set(), gallery, hero) == decide.PASSES
    assert state(4, set(), gallery, hero) == decide.FAILS


def test_reselection_asks_the_next_question_of_the_top_three_static_candidates() -> None:
    small = {"status": "ok", "width": 1200, "height": 900}
    rows = [
        _row(1, is_hero=True, tier="A"),
        _row(2, tier="D"),
        _row(3, tier="D"),
        _row(4, tier="C"),
        _row(5, tier="C"),
        _row(6, tier="B"),
        _row(7, tier="D"),
    ]
    state = _state(rows)
    truth = _truth(1, 2, 3, 4, 5, 6) | {"File_7.jpg": small}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2), 3: _v(3, kind="artifact")}
    jobs = decide.reselection_jobs(state, [SITE], gallery, {}, truth)
    assert [(j.image_id, j.pass_, j.stage) for j in jobs] == [
        (2, vision.HERO, worklist.H_RESELECT),
        (4, vision.GALLERY, worklist.H_RESELECT),
    ]
    passing = {1: _v(1)}
    assert decide.reselection_jobs(state, [SITE], passing, {1: _v(1, vision.HERO)}, truth) == []


def test_a_planned_row_must_cite_a_ledger_verdict_about_todays_bytes(tmp_path: Path) -> None:
    root = _image_tree(tmp_path / "wiki", "Temple.webp")
    images = vision.Images((root,))
    data = (root / SHARD / "Temple.webp").read_bytes()
    line = {**_ok_line(1, kind="artifact"), "image_file": f"{SHARD}/Temple.webp"}
    line["image_sha256"] = hashlib.sha256(data).hexdigest()
    text = vision.line_text(line)
    entry = vision.LedgerLine(vision.verdict_id(text), line)
    verdict = vision.Verdict(entry.verdict_id, dict(line["verdict"]), line)
    rows = {SITE: [_row(1, tier="B")]}
    only_kind = _admission(kind=True)
    planned, _ = decide.plan_vision(rows, {}, {1: verdict}, {}, only_kind, {}, {})
    assert [p.rule for p in planned] == ["K1"]
    assert decide.verify_evidence(planned, [entry], images) == []
    assert "is not in the ledger" in decide.verify_evidence(planned, [], images)[0]
    (root / SHARD / "Temple.webp").write_bytes(data + b"changed")
    assert "offsite file changed" in decide.verify_evidence(planned, [entry], images)[0]


def test_a_commons_title_keeps_everything_but_its_extension() -> None:
    state = _state([_row(1, _commons="A:_detail_of_the.v2_frieze.jpg")])
    assert worklist.g3_jobs(state)[0].title == "A: detail of the.v2 frieze"


# ======================================================================= applied plans
def _planned(key: int, column: str, old: Any, new: Any, site: str = SITE) -> planned.PlannedRow:
    return planned.PlannedRow("wiki_images", key, site, column, old, new, "L1", "exclude", {})


def _tier_of(tiers: dict[int, str]):
    return lambda row, sid: (tiers[int(row["id"])], "t")


def test_a_plan_round_trips_and_a_record_that_is_not_a_planned_row_is_refused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "PLANNED.jsonl"
    rows = [_planned(1, "is_excluded", False, True), _planned(1, "is_hero", True, False)]
    planned.write_plan(path, rows)
    assert planned.read_plan(path) == rows
    record = {**rows[0].as_json(), "note": "hand-edited"}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(planned.PlanError, match="not a planned row"):
        planned.read_plan(path)
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(planned.PlanError, match="holds no planned row"):
        planned.read_plan(path)


def test_a_kinds_plan_is_read_as_image_kind_rows_only(tmp_path: Path) -> None:
    path = tmp_path / "PLAN.jsonl"
    g0 = {
        "table": "wiki_images",
        "column": "image_kind",
        "image_id": 7,
        "site_id": SITE,
        "old_value": None,
        "new_value": "site_photo",
        "test_id": "G0/vlm-kind",
        "change_key": "g0-vlm-kind:7",
    }
    path.write_text(json.dumps(g0) + "\n", encoding="utf-8")
    (row,) = planned.read_kinds_plan(path)
    assert (row.key, row.column, row.old, row.new) == (7, "image_kind", None, "site_photo")
    path.write_text(json.dumps({**g0, "column": "is_excluded"}) + "\n", encoding="utf-8")
    with pytest.raises(planned.PlanError, match="not an image_kind write"):
        planned.read_kinds_plan(path)
    shapeless = {k: v for k, v in g0.items() if k != "old_value"}
    path.write_text(json.dumps(shapeless) + "\n", encoding="utf-8")
    with pytest.raises(planned.PlanError, match="not an image_kind plan record"):
        planned.read_kinds_plan(path)


def test_an_applied_plan_moves_the_state_and_retiers_the_rows_it_moved() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="C"), _row(3, tier="B")]}
    plan = [
        _planned(1, "is_excluded", False, True),
        _planned(1, "is_hero", True, False),
        _planned(2, "is_hero", False, True),
        _planned(3, "original_url", rows[SITE][2]["original_url"], "https://upload.x/New.jpg"),
        _planned(3, "image_kind", None, "artifact"),
    ]
    counts = worklist.fold_applied(
        rows, [(Path("PLANNED.jsonl"), plan)], _tier_of({1: "C", 2: "C", 3: "D"})
    )
    assert counts == {"PLANNED.jsonl": 5}
    got = [(r["id"], r["is_hero"], r["is_excluded"], r["_tier"]) for r in rows[SITE]]
    assert got == [(1, False, True, "C"), (2, True, False, "A"), (3, False, False, "D")]
    assert rows[SITE][2]["original_url"] == "https://upload.x/New.jpg"
    assert rows[SITE][2]["image_kind"] == "artifact"


def test_an_applied_plan_is_folded_only_onto_the_old_values_it_names() -> None:
    def state() -> dict[str, list[dict[str, Any]]]:
        return {SITE: [_row(1, is_hero=True, tier="A"), _row(2)]}

    def fold(rows: dict[str, list[dict[str, Any]]], *plan: planned.PlannedRow) -> None:
        worklist.fold_applied(rows, [(Path("PLANNED.jsonl"), list(plan))], _tier_of({}))

    rows = state()
    fold(rows, _planned(1, "is_excluded", False, True))
    with pytest.raises(worklist.WorklistError, match="is True in the state, the applied plan"):
        fold(rows, _planned(1, "is_excluded", False, True))  # the same plan folded twice
    other = "ffffffff-0000-4000-8000-000000000000"
    with pytest.raises(worklist.WorklistError, match="is not a row of site"):
        fold(state(), _planned(1, "is_excluded", False, True, other))
    with pytest.raises(worklist.WorklistError, match="is not a row of site"):
        fold(state(), _planned(9, "is_excluded", False, True))
    with pytest.raises(worklist.WorklistError, match="not a column a gallery plan writes"):
        fold(state(), _planned(2, "license", "CC BY-SA 4.0", "CC0"))


def _liveness_store() -> list[dict[str, Any]]:
    return [
        _live_line("Dead.jpg", liveness.DELETED_COPYVIO, [1], log={"logid": 7}),
        _live_line(
            "Old.jpg",
            liveness.MOVED_WITHOUT_REDIRECT,
            [2],
            move_target={
                "title": "File:New.jpg",
                "class": liveness.LIVE,
                "url": "https://u/New.jpg",
            },
        ),
        _live_line("Redirected.jpg", liveness.MOVED_WITH_REDIRECT, [3]),
        _live_line("Gone.jpg", liveness.MISSING_NO_LOG, [4]),
    ]


def test_a_state_that_has_not_folded_the_liveness_write_in_is_refused() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2), _row(3), _row(4)]}
    with pytest.raises(worklist.WorklistError, match="fold the liveness write in"):
        worklist.liveness_blocked(_liveness_store(), rows)
    rows[SITE][0].update(is_excluded=True, is_hero=False)
    assert worklist.liveness_blocked(_liveness_store(), rows) == {
        1: liveness.DELETED_COPYVIO,
        2: liveness.MOVED_WITHOUT_REDIRECT,  # not repointed yet
        4: liveness.MISSING_NO_LOG,
    }
    rows[SITE][1]["original_url"] = "https://u/New.jpg"  # L2 applied: live again
    assert set(worklist.liveness_blocked(_liveness_store(), rows)) == {1, 4}
    with pytest.raises(worklist.WorklistError, match="which the state does not hold"):
        worklist.liveness_blocked([_live_line("X.jpg", liveness.DELETED_OTHER, [99])], rows)


def test_no_vision_rule_plans_on_a_row_whose_file_is_not_live() -> None:
    rows = {SITE: [_row(1, tier="B"), _row(2, tier="B")]}
    gallery = {1: _v(1, kind="people", other_site=True), 2: _v(2, kind="artifact")}
    planned_rows, listed = decide.plan_vision(
        rows, {}, gallery, {}, ALL, {}, {1: liveness.MISSING_NO_LOG}
    )
    assert {(p.key, p.column) for p in planned_rows} == {(2, "image_kind")}
    assert any(item.get("image_id") == 1 and "missing-no-log" in item["why"] for item in listed)


def test_h1_never_promotes_a_row_whose_file_is_not_live() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="D"), _row(3, tier="C")]}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2), 3: _v(3)}
    hero = {2: _v(2, vision.HERO), 3: _v(3, vision.HERO)}
    planned_rows, _ = decide.plan_vision(
        rows, {}, gallery, hero, ALL, _truth(1, 2, 3), {2: liveness.MISSING_NO_LOG}
    )
    moves = [(p.key, p.new) for p in planned_rows if p.column == "is_hero"]
    assert moves == [(1, False), (3, True)]  # 2 outranks 3 (tier D), but its file is gone


def test_h1_leaves_a_hero_whose_file_is_not_live_to_the_liveness_lane() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="D")]}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2)}
    hero = {2: _v(2, vision.HERO)}
    planned_rows, listed = decide.plan_vision(
        rows, {}, gallery, hero, ALL, _truth(1, 2), {1: liveness.MISSING_NO_LOG}
    )
    assert [p for p in planned_rows if p.column == "is_hero"] == []
    assert any("the liveness lane owns it" in item["why"] for item in listed)


def test_l1_never_hands_the_hero_to_another_file_that_is_not_live() -> None:
    rows = {
        SITE: [
            _row(1, is_hero=True, tier="A", width=800, height=533),
            _row(2, tier="D", width=1600, height=1200),
            _row(3, tier="C", width=1600, height=1200),
        ]
    }
    lines = [
        _live_line("File_1.jpg", liveness.DELETED_COPYVIO, [1], log={"logid": 7}),
        _live_line("File_2.jpg", liveness.PAGE_WITHOUT_FILE, [2]),
    ]
    planned_rows, _ = decide.plan_liveness(lines, rows, _truth(2, 3))
    assert [p.key for p in planned_rows if p.role == "hero-promote"] == [3]


def test_the_job_builder_refuses_a_state_behind_the_liveness_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "store"
    liveness.write_store(store, [_liveness_store()[0]], {"snapshot_exported_at": "x"})
    state = _state([_row(1, is_hero=True, tier="A"), _row(2)])
    monkeypatch.setattr(worklist, "state_from_args", lambda args: state)
    argv = ["jobs", "--stage", "G3", "--liveness-store", str(store), "--out", str(tmp_path / "J")]
    with pytest.raises(worklist.WorklistError, match="fold the liveness write in"):
        worklist.main(argv)
    state.by_site[SITE][0].update(is_excluded=True, is_hero=False)
    assert worklist.main(argv) == 0
    assert [j.image_id for j in vision.read_jobs(tmp_path / "J")] == [2]


def test_decide_refuses_to_plan_vision_on_a_state_behind_the_liveness_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "store"
    liveness.write_store(store, [_liveness_store()[0]], {"snapshot_exported_at": "x"})
    state = _state([_row(1, is_hero=True, tier="A"), _row(2)])
    monkeypatch.setattr(worklist, "state_from_args", lambda args: state)
    monkeypatch.setattr(decide, "load_truth", lambda path: {})
    argv = ["vision", "--run-dir", str(tmp_path / "run"), "--calibration", str(tmp_path / "C1")]
    argv += ["--liveness-store", str(store), "--chunk", "0"]
    with pytest.raises(worklist.WorklistError, match="fold the liveness write in"):
        decide.main(argv)


# ======================================================================= guards, one test each
def test_a_job_line_with_other_keys_or_an_unknown_pass_is_no_job() -> None:
    line = _job().as_json()
    with pytest.raises(vision.VisionError, match="is not a job"):
        vision.Job.from_json({**line, "prompt": "an extra key"})
    with pytest.raises(vision.VisionError, match="unknown pass 'strict'"):
        vision.Job.from_json({**line, "pass": "strict"})


def test_a_ledger_line_that_is_no_verdict_line_stops_the_reader(tmp_path: Path) -> None:
    path = tmp_path / "VERDICTS.jsonl"
    for line in ({"image_id": 1, "verdict": None}, {"image_id": 1, "status": "ok"}):
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        with pytest.raises(vision.VisionError, match="not a verdict line"):
            vision.Ledger(path)


def test_a_judgement_that_crashes_is_raised_not_swallowed(tmp_path: Path) -> None:
    ledger = vision.Ledger(tmp_path / "VERDICTS.jsonl")

    def judge(job: vision.Job) -> dict[str, Any]:
        raise RuntimeError("a bug inside a judgement, e.g. PIL's DecompressionBombError")

    with pytest.raises(RuntimeError, match="a bug inside a judgement"):
        vision.run_jobs([_job(1), _job(2)], ledger, judge, workers=1, budget_usd=75)
    assert ledger.lines == []


def test_the_dry_run_exits_3_when_an_image_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _image_tree(tmp_path / "wiki", "Temple.webp")
    real = vision.Images
    monkeypatch.setattr(vision, "Images", lambda: real((root,)))
    jobs = tmp_path / "JOBS.jsonl"
    argv = ["export", "--jobs", str(jobs), "--run-dir", str(tmp_path / "run")]
    argv += ["--handoff", str(tmp_path / "handoff"), "--dry-run"]
    vision.write_jobs(jobs, [_job(1)])
    assert vision.main(argv) == vision.EXIT_OK
    vision.write_jobs(jobs, [_job(1), _job(2, filename="Missing.webp")])
    assert vision.main(argv) == vision.EXIT_NO_VERDICT


def test_a_plan_row_without_a_change_or_outside_the_table_is_refused() -> None:
    rows = {SITE: [_row(1), _row(2)]}
    same = decide.PlannedRow("wiki_images", 2, SITE, "is_excluded", False, False, "X1", "x", {})
    with pytest.raises(decide.DecideError, match="planned without a change"):
        decide.check_plan([same], rows)
    unknown = decide.PlannedRow("wiki_images", 2, SITE, "is_excluded", False, True, "Z9", "x", {})
    with pytest.raises(decide.DecideError, match="rule 'Z9' is not in the table"):
        decide.check_plan([unknown], rows)


def _cited_verdict(tmp_path: Path) -> tuple[vision.Images, vision.LedgerLine, decide.PlannedRow]:
    """A K1 row planned from a verdict about the offsite file as it is now."""
    root = _image_tree(tmp_path / "wiki", "Temple.webp")
    data = (root / SHARD / "Temple.webp").read_bytes()
    line = {**_ok_line(1, kind="artifact"), "image_file": f"{SHARD}/Temple.webp"}
    line["image_sha256"] = hashlib.sha256(data).hexdigest()
    entry = vision.LedgerLine(vision.verdict_id(vision.line_text(line)), line)
    verdict = vision.Verdict(entry.verdict_id, dict(line["verdict"]), line)
    rows = {SITE: [_row(1, tier="B")]}
    (row,) = decide.plan_vision(rows, {}, {1: verdict}, {}, _admission(kind=True), {}, {})[0]
    return vision.Images((root,)), entry, row


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"status": "failed"}, "is not an ok verdict of"),
        ({"model": "another-vision-model"}, "is not an ok verdict of"),
        ({"prompt_sha256": "0" * 64}, "was asked with another gallery-v1"),
    ],
)
def test_a_cited_verdict_must_be_an_ok_verdict_of_the_frozen_question(
    tmp_path: Path, change: dict[str, Any], problem: str
) -> None:
    images, entry, row = _cited_verdict(tmp_path)
    assert decide.verify_evidence([row], [entry], images) == []
    altered = vision.LedgerLine(entry.verdict_id, {**entry.line, **change})
    (found,) = decide.verify_evidence([row], [altered], images)
    assert problem in found


def test_a_planned_row_must_repeat_the_hashes_of_the_verdict_it_cites(tmp_path: Path) -> None:
    images, entry, row = _cited_verdict(tmp_path)
    other = decide.PlannedRow(
        **{**row.as_json(), "evidence": {**row.evidence, "image_sha256": "0" * 64}}
    )
    (found,) = decide.verify_evidence([other], [entry], images)
    assert "does not repeat its verdict's hashes" in found


def test_an_excluded_row_is_not_excluded_again() -> None:
    rows = {SITE: [_row(1, is_excluded=True), _row(2)]}
    gallery = {1: _v(1, other_site=True, kind="people"), 2: _v(2)}
    planned_rows, _ = decide.plan_vision(
        rows, {}, gallery, {}, _admission(x1=True, x2=True), {}, {}
    )
    assert planned_rows == []


def test_l1_leaves_a_row_that_is_already_excluded_alone() -> None:
    rows = {SITE: [_row(1, is_excluded=True), _row(2)]}
    line = _live_line("File_1.jpg", liveness.DELETED_OTHER, [1], log={"logid": 3})
    assert decide.plan_liveness([line], rows, {}) == ([], [])
    stranger = _live_line("X.jpg", liveness.DELETED_OTHER, [99], log={"logid": 4})
    with pytest.raises(worklist.WorklistError, match="which the state does not hold"):
        decide.plan_liveness([stranger], rows, {})


def test_h1_never_promotes_a_row_outside_the_accepted_tiers() -> None:
    rows = {SITE: [_row(1, is_hero=True, tier="A"), _row(2, tier="B")]}
    gallery = {1: _v(1, kind="painting_or_artwork"), 2: _v(2)}
    hero = {2: _v(2, vision.HERO)}
    planned_rows, listed = decide.plan_vision(rows, {}, gallery, hero, ALL, _truth(1, 2), {})
    assert [p for p in planned_rows if p.column == "is_hero"] == []
    assert any("no strict-confirmed candidate qualifies" in item["why"] for item in listed)


def test_the_labelled_set_is_refused_with_an_unknown_class_or_an_image_twice(
    tmp_path: Path,
) -> None:
    path = tmp_path / "labels.jsonl"
    line = {"site_id": SITE, "image_id": 1, "labels": ["fremde_staette"]}
    path.write_text(json.dumps(line) + "\n" + json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="image 1 twice"):
        labels.load_labelled(path)
    path.write_text(json.dumps({**line, "labels": ["kaputt"]}) + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="unknown label class"):
        labels.load_labelled(path)


def test_an_image_labelled_twice_by_eye_is_refused(tmp_path: Path) -> None:
    tiles = labels.pilot_tiles()
    path = tmp_path / "LABELS.jsonl"
    line = json.dumps({"image_id": tiles[0].image_id, "human_kind": "site_photo"})
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="labelled twice"):
        labels.load_eye_labels(path, tiles)


def test_the_pilot_tiles_need_a_kind_and_a_verdict_each_and_no_image_twice(
    tmp_path: Path,
) -> None:
    sample, vlm = tmp_path / "SAMPLE.jsonl", tmp_path / "VLM.jsonl"
    tile = json.dumps({"image_id": 1, "site_id": SITE, "tier": "A"})
    sample.write_text(tile + "\n", encoding="utf-8")
    vlm.write_text(json.dumps({"image_id": 1, "kind": "site_photo"}) + "\n", encoding="utf-8")
    assert labels.pilot_tiles(sample, vlm) == [labels.PilotTile(1, SITE, "A", "site_photo")]
    vlm.write_text(json.dumps({"image_id": 1, "kind": "photo"}) + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="has no pilot kind"):
        labels.pilot_tiles(sample, vlm)
    vlm.write_text(json.dumps({"image_id": 2, "kind": "site_photo"}) + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="has no verdict for sampled image 1"):
        labels.pilot_tiles(sample, vlm)
    vlm.write_text(json.dumps({"image_id": 1, "kind": "site_photo"}) + "\n", encoding="utf-8")
    sample.write_text(tile + "\n" + tile + "\n", encoding="utf-8")
    with pytest.raises(labels.LabelError, match="samples one image twice"):
        labels.pilot_tiles(sample, vlm)


def test_derive_refuses_an_unknown_class_and_a_site_name_it_cannot_place(tmp_path: Path) -> None:
    source, snap = _cobata(tmp_path, ["gibt_es_nicht: Olmec2.webp - x"], 2)
    with pytest.raises(labels.LabelError, match="unknown label class 'gibt_es_nicht'"):
        labels.derive(source, snap)
    source, snap = _cobata(tmp_path, [], 2)
    snap.sites.append({"id": "ffffffff-0000-4000-8000-000000000000", "name": "La Cobata"})
    with pytest.raises(labels.LabelError, match="names 2 snapshot sites"):
        labels.derive(source, snap)


def test_a_row_without_a_title_is_no_wildcard_for_the_loose_match() -> None:
    rows = _keyed(_row(1, filename="Temple front.webp", title=None), _row(2, filename="Altar.webp"))
    assert labels.match(rows, "Completely unrelated file name.webp") is None
    assert labels.match(rows, "Temple front, east side")["id"] == 1  # a real prefix still counts


def test_the_l2_page_url_is_the_projects_own_spelling_of_a_file_title() -> None:
    from census.tests import t06_url_shape

    from pipeline import commons_urls

    assert decide.commons_page_url_for is commons_urls.commons_page_url_for
    assert t06_url_shape.commons_page_url_for is commons_urls.commons_page_url_for
    with pytest.raises(decide.DecideError, match="is not a File: title"):
        decide.commons_page_url("Forum Romanum - panoramio (3).jpg")


def test_an_empty_hero_plan_and_a_row_without_a_census_tier_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "PLAN.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(worklist.WorklistError, match="holds no hero move"):
        worklist.load_hero_moves(path)
    with pytest.raises(worklist.WorklistError, match="image 2 has no census tier"):
        _retier([_row(1), _row(2)], {}, {1: "C"}, {1: "C", 2: "C"})
