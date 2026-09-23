"""The vision stage of the gallery audit: frozen prompts, the ledger, the current tiers, the label
sets and the sealed rule table (`scripts/remediation/gallery_audit/{vision,worklist,labels,decide}.py`).

Offline: the gateway is a fake that refuses what the real one refuses (a body that is not a JPEG,
a prompt that is not text), the images are real files written here, and the tiers run through
T10's own functions. Tests that need the gitignored snapshot or label file skip with a reason.
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

import httpx
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from gallery_audit import decide, labels, liveness, planned, vision, worklist  # noqa: E402

from pipeline.video.shorts_select import VLM_PROMPT  # noqa: E402

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


# ======================================================================= the judge
def _image_tree(root: Path, *names: str) -> Path:
    shard = root / SHARD
    shard.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(names):
        buf = io.BytesIO()
        Image.new("RGB", (64 + i, 48), (120, 90 + i, 60)).save(buf, format="WEBP")
        (shard / name).write_bytes(buf.getvalue())
    return root


class FakeGateway:
    """`ask_once`'s contract: text prompt, a session, a JPEG body; answers as scripted."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, client: Any, session: str, prompt: str, jpeg: bytes) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt or not isinstance(session, str) or not session:
            raise AssertionError(
                "the gateway refuses a request without a text prompt and a session"
            )
        if not jpeg.startswith(b"\xff\xd8\xff"):
            raise AssertionError("the gateway refuses an image that is not a JPEG")
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _answer(content: str, status: int = 200) -> dict[str, Any]:
    return {
        "http_status": status,
        "latency_ms": 1200,
        "raw_response": content,
        "finish_reason": "stop",
        "body_text": content,
        "usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
    }


GOOD = json.dumps(
    {"kind": "site_photo", "other_site": False, "other_place": "", "subject": "temple front"}
)


def _judge(tmp_path: Path, gateway: FakeGateway, sleeps: list[float] | None = None) -> vision.Judge:
    main = _image_tree(tmp_path / "wiki", "Temple.webp")
    collisions = _image_tree(tmp_path / "collisions", "Gate.webp")
    return vision.Judge(
        transport=gateway,
        client=None,
        session="session-1",
        images=vision.Images((main, collisions)),
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
        now=lambda: "2026-09-23T10:00:00Z",
    )


def test_a_verdict_line_records_the_bytes_the_prompt_and_the_cost(tmp_path: Path) -> None:
    gateway = FakeGateway(_answer(GOOD))
    line = _judge(tmp_path, gateway)(_job())
    assert line["status"] == "ok" and line["verdict"]["kind"] == "site_photo"
    data = (tmp_path / "wiki" / SHARD / "Temple.webp").read_bytes()
    assert line["image_sha256"] == hashlib.sha256(data).hexdigest()
    assert line["image_file"] == f"{SHARD}/Temple.webp"
    assert line["prompt"] == gateway.prompts[0] == vision.prompt_for(_job())
    assert line["prompt_sha256"] == GALLERY_SHA and line["model"] == "deepseek-v4-flash-vision-exp"
    assert line["cost_usd"] == pytest.approx((1000 * 0.15 + 2000 * 0.60) / 1e6)
    assert line["attempts"] == 1 and line["session_id"] == "session-1"


def test_the_case_collision_tree_is_searched_by_exact_name(tmp_path: Path) -> None:
    judge = _judge(tmp_path, FakeGateway(_answer(GOOD)))
    assert judge(_job(filename="Gate.webp"))["image_file"] == f"{SHARD}/Gate.webp"
    missing = judge(_job(filename="gate.webp"))  # a case-insensitive probe would accept this
    assert missing["status"] == "failed" and missing["error"].startswith("image: no offsite file")


def test_no_parseable_verdict_after_three_attempts_is_a_failure_never_other(tmp_path: Path) -> None:
    sleeps: list[float] = []
    gateway = FakeGateway(
        _answer("I think it is a temple"), _answer('{"kind": "ruin"}'), _answer("", 500)
    )
    line = _judge(tmp_path, gateway, sleeps)(_job())
    assert line["status"] == "failed" and line["verdict"] is None and line["attempts"] == 3
    assert "other" not in json.dumps(line["verdict"]) and line["error"].startswith("http 500")
    assert sleeps == [8.0, 8.0]
    assert line["cost_usd"] == pytest.approx(3 * (1000 * 0.15 + 2000 * 0.60) / 1e6)


def test_a_transport_failure_is_retried_and_a_later_verdict_counts(tmp_path: Path) -> None:
    gateway = FakeGateway(httpx.ConnectError("reset"), _answer(GOOD))
    line = _judge(tmp_path, gateway)(_job())
    assert line["status"] == "ok" and line["attempts"] == 2
    assert line["attempts_detail"][0]["transport_error"].startswith("ConnectError")


def test_an_image_that_cannot_be_read_is_a_failed_line_and_costs_no_call(tmp_path: Path) -> None:
    gateway = FakeGateway()
    judge = _judge(tmp_path, gateway)
    (tmp_path / "wiki" / SHARD / "Broken.webp").write_bytes(b"not an image")
    judge.images = vision.Images((tmp_path / "wiki",))
    line = judge(_job(filename="Broken.webp"))
    assert line["status"] == "failed" and "cannot be read as an image" in line["error"]
    assert gateway.prompts == []


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
    other_model = [vision.LedgerLine("y", {**_ok_line(3), "model": "another-vision-model"})]
    with pytest.raises(vision.VisionError, match="answered by"):
        vision.verdicts_by_image(other_model, vision.GALLERY_PROMPT_ID)
    twice = [vision.LedgerLine("a", _ok_line(4)), vision.LedgerLine("b", _ok_line(4))]
    with pytest.raises(vision.VisionError, match="two ok verdicts"):
        vision.verdicts_by_image(twice, vision.GALLERY_PROMPT_ID)


def test_more_than_four_workers_need_a_clean_ramp_probe() -> None:
    clean = [vision.LedgerLine(str(i), _ok_line(i)) for i in range(500)]
    assert vision.ramp_allows([], 4)[0]
    assert not vision.ramp_allows(clean[:499], 8)[0]
    assert vision.ramp_allows(clean, 8)[0]
    dirty = [*clean[:499], vision.LedgerLine("f", {**_ok_line(1), "status": "failed"})]
    assert not vision.ramp_allows(dirty, 8)[0]
    slow = [vision.LedgerLine(str(i), {**_ok_line(i), "latency_ms": 45_000}) for i in range(500)]
    assert not vision.ramp_allows(slow, 8)[0]


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


ALL = decide.Admission(kind=True, strict=True, x1=True, x2=True, x3=True, thresholds_sha256="t")
NONE = decide.Admission(
    kind=False, strict=False, x1=False, x2=False, x3=False, thresholds_sha256="t"
)
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
    only_kind = decide.Admission(
        kind=True, strict=False, x1=False, x2=False, x3=False, thresholds_sha256="t"
    )
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
    no_kind = decide.Admission(
        kind=False, strict=False, x1=True, x2=True, x3=True, thresholds_sha256="t"
    )
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
        rows, {}, gallery, hero, decide.Admission(True, True, False, False, False, "t"), truth, {}
    )
    moves = [(p.key, p.old, p.new, p.role) for p in planned if p.column == "is_hero"]
    assert moves == [(1, True, False, "hero-demote"), (3, False, True, "hero-promote")]
    decide.check_plan(planned, rows)


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


def test_an_admission_file_must_name_every_trigger_with_a_boolean(tmp_path: Path) -> None:
    path = tmp_path / "ADMISSION.json"
    path.write_text(
        json.dumps(
            {
                "thresholds_sha256": "t",
                "admitted": {"kind": True, "strict": False, "x1": True, "x2": False},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(decide.DecideError, match="kind/strict/x1/x2/x3"):
        decide.load_admission(path)
    path.write_text(
        json.dumps(
            {
                "thresholds_sha256": "t",
                "admitted": dict.fromkeys(("kind", "strict", "x1", "x2", "x3"), "yes"),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(decide.DecideError, match="not a boolean"):
        decide.load_admission(path)


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
    only_kind = decide.Admission(True, False, False, False, False, "t")
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
    argv = ["vision", "--run-dir", str(tmp_path / "run"), "--admission", str(tmp_path / "A")]
    argv += ["--liveness-store", str(store), "--chunk", "0"]
    with pytest.raises(worklist.WorklistError, match="fold the liveness write in"):
        decide.main(argv)
