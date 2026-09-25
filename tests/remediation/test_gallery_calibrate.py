"""Calibration C1 (`scripts/remediation/gallery_audit/calibrate.py`): sealed before the first call,
measured after the last, and admitting a trigger only when every number its threshold names holds.
Offline: the verdicts are ledger lines written here, the labels are the tracked sets.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from gallery_audit import calibrate, decide, labels, vision, worklist  # noqa: E402

#: Today's sealed thresholds. They name the model the verdicts must be by (`vision.MODEL`), so the
#: owner order of 2026-09-23 (Opus instead of DeepSeek) moved this pin from the one below.
THRESHOLDS_SHA = "e65604571e5b6717a4c13982039fa94c3d5646101f36b6d53eecde3cdddc61a2"
#: The thresholds `calibration-2026-09-23/` was sealed with, naming the pilot's DeepSeek transport.
DEEPSEEK_THRESHOLDS_SHA = "1040cd59353181c6928640b3ef51148454cdcbf13b2b31179ca57f3f8b55c99b"
SITE = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"


def test_the_sealed_thresholds_are_the_designs_numbers() -> None:
    t = calibrate.THRESHOLDS
    assert (t["T-kind"]["pilot_agreement_min"], t["T-kind"]["non_photo_precision_min"]) == (
        0.90,
        0.90,
    )
    x1 = t["T-X1"]
    assert (
        x1["foreign_rows_resolved_min"],
        x1["precision_min"],
        x1["recall_min"],
        x1["gold_correct_flagged_max"],
    ) == (60, 0.85, 0.70, 1)
    assert (
        (t["T-X2"]["precision_min"], t["T-X2"]["flags_min"])
        == (t["T-X3"]["precision_min"], t["T-X3"]["flags_min"])
        == (0.85, 10)
    )
    assert (
        t["T-strict"]["precision_min"],
        t["T-strict"]["recall_min"],
        t["T-strict"]["tiles"],
    ) == (0.90, 0.60, 50)
    assert t["final_acceptance"]["seed"] == 20260923 and t["early_gate"]["after_sites"] == 300
    assert hashlib.sha256(calibrate.thresholds_text().encode("utf-8")).hexdigest() == THRESHOLDS_SHA


def test_the_seal_is_written_and_logged_before_any_verdict_exists(tmp_path: Path) -> None:
    digest = calibrate.seal(tmp_path, now=lambda: "2026-09-23T10:00:00Z")
    assert digest == THRESHOLDS_SHA
    assert (tmp_path / "THRESHOLDS.json").read_text(encoding="utf-8") == calibrate.thresholds_text()
    thresholds, sealed_digest, sealed_at = calibrate.sealed(tmp_path)
    assert (
        sealed_digest == digest
        and sealed_at == "2026-09-23T10:00:00Z"
        and thresholds == calibrate.THRESHOLDS
    )
    late = tmp_path / "late"
    late.mkdir()
    (late / "VERDICTS.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(calibrate.CalibrationError, match="sealed before the first call"):
        calibrate.seal(late)


def test_thresholds_changed_after_the_seal_are_refused(tmp_path: Path) -> None:
    calibrate.seal(tmp_path)
    path = tmp_path / "THRESHOLDS.json"
    path.write_text(path.read_text(encoding="utf-8").replace("0.85", "0.5"), encoding="utf-8")
    with pytest.raises(calibrate.CalibrationError, match="changed after they were sealed"):
        calibrate.sealed(tmp_path)
    with pytest.raises(calibrate.CalibrationError, match="never rewritten"):
        calibrate.seal(tmp_path)


def test_the_first_seal_counts_and_a_log_with_two_hashes_is_refused(tmp_path: Path) -> None:
    calibrate.seal(tmp_path, now=lambda: "2026-09-23T10:00:00Z")
    calibrate.seal(tmp_path, now=lambda: "2026-09-23T10:05:00Z")  # the same thresholds again
    assert calibrate.sealed(tmp_path)[2] == "2026-09-23T10:00:00Z"
    with open(tmp_path / "SEAL.jsonl", "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"thresholds_sha256": "0" * 64, "sealed_at": "2026-09-23T10:06:00Z"}) + "\n"
        )
    with pytest.raises(calibrate.CalibrationError, match="more than one thresholds hash"):
        calibrate.sealed(tmp_path)


def test_nothing_runs_on_an_unsealed_directory(tmp_path: Path) -> None:
    with pytest.raises(calibrate.CalibrationError, match="is not sealed"):
        calibrate.sealed(tmp_path)


def _line(
    image_id: int,
    prompt: str = vision.GALLERY,
    judged_at: str = "2026-09-23T11:00:00Z",
    **verdict: Any,
) -> vision.LedgerLine:
    prompt_id, template = vision.PROMPTS[prompt]
    base = (
        {"kind": "site_photo", "other_site": False, "other_place": "", "subject": "x"}
        if prompt == vision.GALLERY
        else {"shows_archaeology": True, "structure": "", "generic_landscape": False}
    )
    base.update(verdict)
    line = {
        "image_id": image_id,
        "site_id": SITE,
        "pass": prompt,
        "stage": "C1",
        "tier": None,
        "model": vision.MODEL,
        "prompt_id": prompt_id,
        "prompt_sha256": vision.prompt_sha256(template),
        "image_sha256": "i",
        "status": "ok",
        "verdict": base,
        "error": None,
        "cost_usd": 0.001,
        "latency_ms": 900,
        "judged_at": judged_at,
    }
    return vision.LedgerLine(
        hashlib.sha256(json.dumps(line, sort_keys=True).encode()).hexdigest(), line
    )


def _job(image_id: int, pass_: str = vision.GALLERY) -> vision.Job:
    return vision.Job(
        image_id,
        SITE,
        f"{image_id}.webp",
        pass_,
        "C1",
        "Site",
        "Greece",
        "Temple",
        "t",
        "commons",
        (),
        None,
    )


def _scenario() -> dict[str, Any]:
    """A small C1 where kind, X1, X2 and the strict pass hold, and X3 does not."""
    thresholds = copy.deepcopy(calibrate.THRESHOLDS)
    thresholds["T-X1"]["foreign_rows_resolved_min"] = 5
    thresholds["T-X2"]["flags_min"] = thresholds["T-X3"]["flags_min"] = 2
    thresholds["T-strict"]["tiles"] = 2
    thresholds["definitions"]["gold_foreign"] = [41, 42]
    thresholds["definitions"]["gold_correct"] = [43, 44]
    tiles = [
        labels.PilotTile(1, SITE, "A", "site_photo"),
        labels.PilotTile(2, SITE, "A", "site_photo"),
        labels.PilotTile(3, SITE, "B", "artifact"),
        labels.PilotTile(4, SITE, "C", "site_photo"),
    ]
    labelled = [
        labels.LabelledRow(
            SITE,
            i,
            frozenset({labels.FOREIGN})
            if i <= 15
            else frozenset({"karte_oder_plan"})
            if i <= 18
            else frozenset(),
        )
        for i in range(11, 31)
    ]
    ledger = [_line(1), _line(2), _line(3, kind="artifact"), _line(4)]
    ledger += [
        _line(
            i,
            other_site=True,
            kind="people" if i in (11, 12) else "other" if i == 13 else "site_photo",
        )
        for i in range(11, 16)
    ]
    ledger += [_line(i, kind="map_or_document") for i in (16, 17, 18)]
    ledger += [_line(i, kind="other" if i == 19 else "site_photo") for i in range(19, 31)]
    ledger += [_line(41, other_site=True), _line(42, other_site=True), _line(43), _line(44)]
    ledger += [_line(1, vision.HERO), _line(2, vision.HERO, shows_archaeology=False)]
    jobs = [_job(i) for i in [1, 2, 3, 4, *range(11, 31), 41, 42, 43, 44]] + [
        _job(1, vision.HERO),
        _job(2, vision.HERO),
    ]
    eye = {
        1: labels.EyeLabel(1, "site_photo", True, None),
        2: labels.EyeLabel(2, "site_photo", False, None),
    }
    return {
        "thresholds": thresholds,
        "jobs": jobs,
        "ledger": ledger,
        "tiles": tiles,
        "labelled": labelled,
        "eye": eye,
    }


def _evaluate(s: dict[str, Any]) -> dict[str, Any]:
    return calibrate.evaluate(
        s["thresholds"],
        s["jobs"],
        s["ledger"],
        s["tiles"],
        s["labelled"],
        s["eye"],
        calibrate._clopper_pearson(),
    )


def test_each_trigger_is_admitted_only_by_its_own_numbers() -> None:
    result = _evaluate(_scenario())
    assert result["admitted"] == {"kind": True, "strict": True, "x1": True, "x2": True, "x3": False}
    m = result["metrics"]
    assert m["T-kind"]["pilot_agreement"]["k"] == 4 and m["T-X1"]["recall"] == {
        **m["T-X1"]["recall"],
        "k": 5,
        "n": 5,
    }
    assert m["T-X3"]["precision"]["k"] == 1 and m["T-X3"]["precision"]["n"] == 2
    lo, hi = m["T-X1"]["precision"]["ci95"]
    assert lo < 1.0 == hi  # an interval, never a bare 5/5 = 100 %


BASE = {"kind": True, "strict": True, "x1": True, "x2": True, "x3": False}


def _with(s: dict[str, Any], image_id: int, prompt: str = vision.GALLERY, **verdict: Any) -> None:
    """Replace one verdict of the scenario's ledger."""
    prompt_id = vision.PROMPTS[prompt][0]
    s["ledger"] = [
        e for e in s["ledger"] if (e.line["image_id"], e.line["prompt_id"]) != (image_id, prompt_id)
    ] + [_line(image_id, prompt, **verdict)]


def _pilot_disagrees(s: dict[str, Any]) -> None:
    _with(s, 4, kind="other")  # 3 of 4 pilot kinds agree: 0.75 < 0.90


def _a_map_that_is_none(s: dict[str, Any]) -> None:
    _with(s, 20, kind="map_or_document")  # 3 of 4 called maps are maps: 0.75 < 0.90


def _too_few_foreign_rows(s: dict[str, Any]) -> None:
    s["thresholds"]["T-X1"]["foreign_rows_resolved_min"] = 6  # 5 resolve


def _a_clean_row_flagged(s: dict[str, Any]) -> None:
    _with(s, 25, other_site=True)  # precision 5 of 6: 0.83 < 0.85


def _two_foreign_rows_missed(s: dict[str, Any]) -> None:
    _with(s, 14)
    _with(s, 15)  # recall 3 of 5: 0.60 < 0.70


def _both_gold_correct_rows_flagged(s: dict[str, Any]) -> None:
    _with(s, 43, other_site=True)
    _with(s, 44, other_site=True)  # 2 > 1


def _too_few_people(s: dict[str, Any]) -> None:
    s["thresholds"]["T-X2"]["flags_min"] = 3  # 2 people flags


def _a_person_on_a_clean_row(s: dict[str, Any]) -> None:
    _with(s, 20, kind="people")  # X2 precision 2 of 3: 0.67 < 0.85


def _strict_says_yes_to_a_no(s: dict[str, Any]) -> None:
    _with(s, 2, vision.HERO, shows_archaeology=True)  # precision 1 of 2 < 0.90


def _strict_misses_a_yes(s: dict[str, Any]) -> None:
    s["eye"][2] = labels.EyeLabel(2, "site_photo", True, None)  # recall 1 of 2 < 0.60


@pytest.mark.parametrize(
    ("change", "dropped"),
    [
        (_pilot_disagrees, "kind"),
        (_a_map_that_is_none, "kind"),
        (_too_few_foreign_rows, "x1"),
        (_a_clean_row_flagged, "x1"),
        (_two_foreign_rows_missed, "x1"),
        (_both_gold_correct_rows_flagged, "x1"),
        (_too_few_people, "x2"),
        (_a_person_on_a_clean_row, "x2"),
        (_strict_says_yes_to_a_no, "strict"),
        (_strict_misses_a_yes, "strict"),
    ],
)
def test_each_threshold_leg_alone_refuses_its_trigger(change: Any, dropped: str) -> None:
    scenario = _scenario()
    change(scenario)
    assert _evaluate(scenario)["admitted"] == {**BASE, dropped: False}


def test_a_job_without_a_verdict_admits_nothing() -> None:
    scenario = _scenario()
    scenario["ledger"] = [e for e in scenario["ledger"] if e.line["image_id"] != 30]
    result = _evaluate(scenario)
    assert result["admitted"] == dict.fromkeys(("kind", "strict", "x1", "x2", "x3"), False)
    assert result["metrics"]["T0"]["without_verdict"] == 1


def test_one_unflagged_gold_foreign_row_drops_x1() -> None:
    scenario = _scenario()
    scenario["ledger"] = [e for e in scenario["ledger"] if e.line["image_id"] != 42] + [_line(42)]
    assert _evaluate(scenario)["admitted"]["x1"] is False


def test_the_strict_pass_is_not_admitted_without_eye_labels() -> None:
    scenario = _scenario()
    scenario["eye"] = None
    result = _evaluate(scenario)
    assert (
        result["admitted"]["strict"] is False
        and result["metrics"]["T-strict"]["evaluable"] is False
    )


def test_a_verdict_judged_before_the_seal_is_refused(tmp_path: Path) -> None:
    calibrate.seal(tmp_path, now=lambda: "2026-09-23T10:00:00Z")
    calibrate.fix_jobs(tmp_path, [_job(1)], now=lambda: "2026-09-23T10:01:00Z")
    early = _line(1, judged_at="2026-09-23T09:59:59Z")
    (tmp_path / "VERDICTS.jsonl").write_text(
        json.dumps(early.line, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(calibrate.CalibrationError, match="judged before the seal"):
        calibrate.command_evaluate(tmp_path, None)


def _c1_ids() -> list[int]:
    definitions = calibrate.THRESHOLDS["definitions"]
    return [1, 2, 11, 12, *definitions["gold_foreign"], *definitions["gold_correct"]]


def _c1_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    drop: int | None = None,
    ledger: bool = True,
) -> tuple[Path, Path]:
    """A sealed C1 run directory over small label sets, with its ledger and W8-style eye labels.

    The repository root is `tmp_path` (the eye labels must be a repository file), the thresholds
    are the real sealed ones and the sample is fixed through `fix_jobs`, as `calibrate.py jobs`
    fixes it. `drop` leaves one gallery verdict out of the ledger (T0 fails); `ledger=False` writes
    none, for a round that has yet to be answered.
    """
    monkeypatch.setattr(calibrate, "ROOT", tmp_path)
    tiles = [
        labels.PilotTile(1, SITE, "A", "site_photo"),
        labels.PilotTile(2, SITE, "B", "artifact"),
    ]
    labelled = [
        labels.LabelledRow(SITE, 11, frozenset({labels.FOREIGN})),
        labels.LabelledRow(SITE, 12, frozenset()),
    ]
    monkeypatch.setattr(labels, "pilot_tiles", lambda: tiles)
    monkeypatch.setattr(labels, "load_labelled", lambda: labelled)
    run = tmp_path / "calibration"
    calibrate.seal(run, now=lambda: "2026-09-23T10:00:00Z")
    ids = _c1_ids()
    calibrate.fix_jobs(
        run, [_job(i) for i in ids] + [_job(1, vision.HERO)], now=lambda: "2026-09-23T10:01:00Z"
    )
    if ledger:
        lines = [_line(i).line for i in ids if i != drop] + [_line(1, vision.HERO).line]
        (run / "VERDICTS.jsonl").write_text(
            "".join(vision.line_text(line) + "\n" for line in lines),
            encoding="utf-8",
            newline="\n",
        )
    eye = tmp_path / "LABELS.jsonl"
    eye.write_text(
        json.dumps(
            {
                "image_id": 1,
                "human_kind": "site_photo",
                "shows_archaeology": True,
                "other_site": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return run, eye


def test_a_genuine_admission_is_re_derived_and_decide_cites_its_sha256(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    written = calibrate.command_evaluate(run, eye)
    assert written["eye_labels"] == "LABELS.jsonl" and len(written["eye_labels_sha256"]) == 64
    assert (
        written["ledger_sha256"]
        == hashlib.sha256((run / "VERDICTS.jsonl").read_bytes()).hexdigest()
    )
    text = (run / "ADMISSION.json").read_text(encoding="utf-8")
    record, digest = calibrate.verify_admission(run)
    assert record == written and digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    admission = decide.load_admission(run)
    assert admission.admission_sha256 == digest
    assert {k: getattr(admission, k) for k in written["admitted"]} == written["admitted"]
    calibrate.command_evaluate(run, eye)  # the same inputs give the same bytes
    assert (run / "ADMISSION.json").read_text(encoding="utf-8") == text


def test_a_hand_edited_admission_switches_nothing_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    written = calibrate.command_evaluate(run, eye)
    path = run / "ADMISSION.json"
    for forged in (
        {**written, "admitted": dict.fromkeys(written["admitted"], True)},
        {**written, "thresholds_sha256": "0" * 64},
    ):
        path.write_text(calibrate.admission_text(forged), encoding="utf-8", newline="\n")
        with pytest.raises(calibrate.CalibrationError, match="is not what the sealed calibration"):
            calibrate.verify_admission(run)
        with pytest.raises(calibrate.CalibrationError, match="is not what the sealed calibration"):
            decide.load_admission(run)


def test_an_admission_measured_on_another_ledger_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    calibrate.command_evaluate(run, eye)
    ledger = run / "VERDICTS.jsonl"
    # the same verdicts, another cost: no metric moves, only the ledger's bytes do
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace('"cost_usd": 0.001', '"cost_usd": 0.002', 1),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(calibrate.CalibrationError, match=r"differs in \['ledger_sha256'\]"):
        calibrate.verify_admission(run)


def test_an_admission_measured_on_other_eye_labels_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    calibrate.command_evaluate(run, eye)
    # other_site is no input of any metric: only the labels' bytes move
    eye.write_text(
        eye.read_text(encoding="utf-8").replace('"other_site": null', '"other_site": true'),
        encoding="utf-8",
    )
    with pytest.raises(calibrate.CalibrationError, match=r"differs in \['eye_labels_sha256'\]"):
        calibrate.verify_admission(run)


def test_an_admission_whose_t0_failed_is_refused_to_decide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch, drop=12)
    written = calibrate.command_evaluate(run, eye)
    assert written["metrics"]["T0"]["pass"] is False
    with pytest.raises(calibrate.CalibrationError, match="T0 failed"):
        calibrate.verify_admission(run)


def test_evaluate_names_its_eye_labels_or_says_it_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _c1_dir(tmp_path, monkeypatch)
    with pytest.raises(calibrate.CalibrationError, match="does not exist - name the eye labels"):
        calibrate.command_evaluate(run, tmp_path / "LABELS-typo.jsonl")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jsonl"
    outside.write_text("", encoding="utf-8")
    with pytest.raises(calibrate.CalibrationError, match="not a file of this repository"):
        calibrate.command_evaluate(run, outside)
    with pytest.raises(SystemExit):
        calibrate.main(["evaluate", "--run-dir", str(run)])
    assert calibrate.main(["evaluate", "--run-dir", str(run), "--no-eye-labels"]) == 0
    record, _ = calibrate.verify_admission(run)
    assert record["eye_labels"] is None and record["eye_labels_sha256"] is None
    assert record["metrics"]["T-strict"]["evaluable"] is False


def test_evaluate_and_its_verification_need_their_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    with pytest.raises(calibrate.CalibrationError, match="run `calibrate.py evaluate` first"):
        calibrate.verify_admission(run)
    (run / "VERDICTS.jsonl").unlink()
    with pytest.raises(calibrate.CalibrationError, match="run the C1 vision run first"):
        calibrate.command_evaluate(run, eye)


def test_the_c1_jobs_ask_each_image_once_and_the_strict_question_of_tier_a() -> None:
    gold = {
        sid: [{"id": 900 + n, "site_id": sid} for n in range(i * 2, i * 2 + 2)]
        for i, sid in enumerate(labels.GOLD_SITE_IDS)
    }
    rows = {SITE: [{"id": i, "site_id": SITE} for i in (1, 2, 3)]} | gold
    for site_rows in rows.values():
        for row in site_rows:
            row.update(
                {
                    "filename": f"{row['id']}.webp",
                    "title": "t",
                    "_commons": None,
                    "_categories": None,
                    "_tier": "C",
                }
            )
    sites = [{"id": sid, "name": "n", "country": "c", "site_type": "s"} for sid in rows]
    state = worklist.State(sites=sites, by_site=rows, exported_at="x")
    tiles = [labels.PilotTile(1, SITE, "A", "site_photo"), labels.PilotTile(2, SITE, "B", "other")]
    labelled = [labels.LabelledRow(SITE, 2, frozenset()), labels.LabelledRow(SITE, 3, frozenset())]
    jobs = calibrate.c1_jobs(state, tiles, labelled)
    assert [(j.image_id, j.pass_) for j in jobs] == [
        (1, vision.GALLERY),
        (2, vision.GALLERY),
        (3, vision.GALLERY),
        (900, vision.GALLERY),
        (901, vision.GALLERY),
        (902, vision.GALLERY),
        (903, vision.GALLERY),
        (904, vision.GALLERY),
        (905, vision.GALLERY),
        (1, vision.HERO),
    ]


CALIBRATION = REPO / "output" / "remediation" / "gallery_audit" / "calibration-2026-09-23"
#: The DeepSeek run of 2026-09-23 in that directory: four questions, each refused by the opencode
#: gateway with HTTP 401 three times, then the run stopped (exit 3). Evidence of a failed attempt,
#: kept beside the seal - never the directory's ledger.
FAILED_ATTEMPT = CALIBRATION / "failed-deepseek-401" / "VERDICTS.jsonl"
FAILED_ATTEMPT_SHA = "23eaea0b6ebd068726eb3d9024ab396d6cca45d2f7f2b197912a59fdd673f258"


def test_the_deepseek_c1_attempt_produced_no_verdict_and_is_kept_apart_from_the_seal() -> None:
    assert not (CALIBRATION / "VERDICTS.jsonl").exists()
    assert hashlib.sha256(FAILED_ATTEMPT.read_bytes()).hexdigest() == FAILED_ATTEMPT_SHA
    _, _, sealed_at = calibrate.sealed(CALIBRATION)
    lines = vision.Ledger(FAILED_ATTEMPT).lines
    assert [e.line["image_id"] for e in lines] == [60052, 59615, 59966, 60529]
    assert {e.line["model"] for e in lines} == {"deepseek-v4-flash-vision-exp"}
    for entry in lines:
        line = entry.line
        assert not entry.ok and line["verdict"] is None and line["parsed"] is None
        assert line["http_status"] == 401 and "Invalid credential" in line["error"]
        assert [a["http_status"] for a in line["attempts_detail"]] == [401, 401, 401]
        assert line["cost_usd"] == 0 and str(line["judged_at"]) >= sealed_at


def test_the_versioned_c1_directory_is_the_deepseek_seal_and_admits_no_opus_verdict() -> None:
    """History, untouched: the C1 directory was sealed for the pilot's DeepSeek transport.

    The owner order of 2026-09-23 changed nothing in the thresholds but the model they name, and
    `vision.verdicts_by_image` refuses a verdict by any other model than today's - so the DeepSeek
    ledger written into that directory can admit no trigger, and an Opus calibration is sealed in a
    directory of its own (`calibrate.py seal`, then `jobs`) before its first question is handed off.
    """
    thresholds, digest, sealed_at = calibrate.sealed(CALIBRATION)
    assert digest == DEEPSEEK_THRESHOLDS_SHA != THRESHOLDS_SHA
    assert thresholds["definitions"]["model"] == "deepseek-v4-flash-vision-exp"
    today = json.loads(json.dumps(calibrate.THRESHOLDS))
    today["definitions"]["model"] = thresholds["definitions"]["model"]
    assert thresholds == today  # the model is the only difference
    # the bytes on disk, not only the text: `.gitattributes` pins calibration-*/* to LF, so a
    # sha256sum of the checkout agrees with the seal and with the reported jobs digest
    assert hashlib.sha256((CALIBRATION / "THRESHOLDS.json").read_bytes()).hexdigest() == (
        DEEPSEEK_THRESHOLDS_SHA
    )
    assert hashlib.sha256((CALIBRATION / "JOBS.jsonl").read_bytes()).hexdigest() == (
        "f0c4ccd6833f2de456e2d1ca110d2520ae6772cd9c3ebd4ec789a032de70e5c9"
    )
    jobs = vision.read_jobs(CALIBRATION / "JOBS.jsonl")
    assert len(jobs) == 939 and sum(job.pass_ == vision.HERO for job in jobs) == 50
    assert {job.stage for job in jobs} == {calibrate.C1}
    assert str(sealed_at) == "2026-09-23T04:10:40Z"


# ======================================================================= the fixed C1 sample
def _sealed(tmp_path: Path) -> Path:
    run = tmp_path / "calibration"
    calibrate.seal(run, now=lambda: "2026-09-25T10:00:00Z")
    return run


def _log(run: Path) -> list[dict[str, Any]]:
    text = (run / "SEAL.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_the_c1_sample_is_fixed_in_the_seal_log_after_the_thresholds(tmp_path: Path) -> None:
    run = tmp_path / "calibration"
    with pytest.raises(calibrate.CalibrationError, match="is not sealed"):
        calibrate.fix_jobs(run, [_job(1)])
    run = _sealed(tmp_path)
    digest = calibrate.fix_jobs(run, [_job(1), _job(2)], now=lambda: "2026-09-25T10:05:00Z")
    assert digest == hashlib.sha256((run / "JOBS.jsonl").read_bytes()).hexdigest()
    assert _log(run) == [
        {"thresholds_sha256": THRESHOLDS_SHA, "sealed_at": "2026-09-25T10:00:00Z"},
        {"jobs_sha256": digest, "jobs": 2, "fixed_at": "2026-09-25T10:05:00Z"},
    ]
    # the seal is still the thresholds', and the sample reads back as it was fixed
    assert calibrate.sealed(run)[1:] == (THRESHOLDS_SHA, "2026-09-25T10:00:00Z")
    jobs, fixed = calibrate.sealed_jobs(run)
    assert fixed == digest and [job.image_id for job in jobs] == [1, 2]
    # the same sample again changes nothing, not even the log
    assert calibrate.fix_jobs(run, [_job(1), _job(2)]) == digest
    assert len(_log(run)) == 2


def test_a_fixed_sample_is_never_rewritten_and_not_read_once_edited(tmp_path: Path) -> None:
    run = _sealed(tmp_path)
    calibrate.fix_jobs(run, [_job(1), _job(2)])
    with pytest.raises(calibrate.CalibrationError, match="never rewritten"):
        calibrate.fix_jobs(run, [_job(1)])
    assert len(_log(run)) == 2
    (run / "JOBS.jsonl").write_text(vision.jobs_text([_job(1)]), encoding="utf-8", newline="\n")
    with pytest.raises(calibrate.CalibrationError, match="changed after it was fixed"):
        calibrate.sealed_jobs(run)


def test_the_sample_is_fixed_once_and_before_the_first_answer(tmp_path: Path) -> None:
    run = _sealed(tmp_path)
    with pytest.raises(calibrate.CalibrationError, match="run `calibrate.py jobs`"):
        calibrate.sealed_jobs(run)  # sealed, but no sample fixed yet
    calibrate.fix_jobs(run, [_job(1)])
    with open(run / "SEAL.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"jobs_sha256": "0" * 64, "jobs": 1, "fixed_at": "x"}) + "\n")
    with pytest.raises(calibrate.CalibrationError, match="fixes 2 C1 samples"):
        calibrate.sealed_jobs(run)
    late = _sealed(tmp_path / "late")
    (late / "VERDICTS.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(calibrate.CalibrationError, match="fixed before the first call"):
        calibrate.fix_jobs(late, [_job(1)])
    assert not (late / "JOBS.jsonl").exists()


def test_a_seal_log_line_that_is_neither_seal_nor_sample_is_refused(tmp_path: Path) -> None:
    run = _sealed(tmp_path)
    with open(run / "SEAL.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"note": "answered by Opus"}) + "\n")
    with pytest.raises(calibrate.CalibrationError, match="neither"):
        calibrate.sealed(run)


def _deepseek_copy(tmp_path: Path) -> Path:
    run = tmp_path / "deepseek"
    run.mkdir()
    for name in ("THRESHOLDS.json", "SEAL.jsonl", "JOBS.jsonl"):
        shutil.copyfile(CALIBRATION / name, run / name)
    return run


def test_a_directory_sealed_for_another_model_is_never_fixed_asked_or_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`calibration-2026-09-23/` names the pilot's DeepSeek model: no Opus question comes from it."""
    run = _deepseek_copy(tmp_path)
    before = {p.name: p.read_bytes() for p in run.iterdir()}
    refused = "sealed for 'deepseek-v4-flash-vision-exp'"
    with pytest.raises(calibrate.CalibrationError, match=refused):
        calibrate.fix_jobs(run, [_job(1)])
    handoff = tmp_path / "handoff"
    for half in ("--handoff-export", "--handoff-import"):
        with pytest.raises(calibrate.CalibrationError, match=refused):
            calibrate.main(["vision", "--run-dir", str(run), half, str(handoff)])
    (run / "VERDICTS.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(calibrate.CalibrationError, match=refused):
        calibrate.command_evaluate(run, None)
    (run / "VERDICTS.jsonl").unlink()

    def no_state(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the state is built only for a directory its sample may be fixed in")

    monkeypatch.setattr(worklist, "build_state", no_state)
    with pytest.raises(calibrate.CalibrationError, match=refused):
        calibrate.main(["jobs", "--run-dir", str(run)])
    assert not handoff.exists()
    assert {p.name: p.read_bytes() for p in run.iterdir()} == before


OPUS_CALIBRATION = REPO / "output" / "remediation" / "gallery_audit" / "calibration-2026-09-25-opus"
#: The sample the DeepSeek seal fixed on 2026-09-23 (its JOBS.jsonl, 939 questions).
DEEPSEEK_JOBS_SHA = "f0c4ccd6833f2de456e2d1ca110d2520ae6772cd9c3ebd4ec789a032de70e5c9"


def test_the_opus_c1_directory_was_sealed_for_opus_and_fixed_its_sample_before_any_answer() -> None:
    """The Opus calibration (owner order 2026-09-23): today's thresholds and the C1 sample, each
    hashed into SEAL.jsonl before the first question was handed off - the very 939 questions the
    DeepSeek seal fixed, rebuilt from the same inputs byte for byte."""
    thresholds, digest, sealed_at = calibrate.sealed_for_model(OPUS_CALIBRATION)
    assert digest == THRESHOLDS_SHA and thresholds["definitions"]["model"] == vision.MODEL
    assert thresholds == json.loads(calibrate.thresholds_text())
    assert hashlib.sha256((OPUS_CALIBRATION / "THRESHOLDS.json").read_bytes()).hexdigest() == (
        THRESHOLDS_SHA
    )
    jobs, fixed = calibrate.sealed_jobs(OPUS_CALIBRATION)
    assert hashlib.sha256((OPUS_CALIBRATION / "JOBS.jsonl").read_bytes()).hexdigest() == fixed
    assert fixed == DEEPSEEK_JOBS_SHA
    assert len(jobs) == 939 and sum(job.pass_ == vision.HERO for job in jobs) == 50
    log = _log(OPUS_CALIBRATION)
    assert [sorted(entry) for entry in log] == [
        ["sealed_at", "thresholds_sha256"],
        ["fixed_at", "jobs", "jobs_sha256"],
    ]
    assert sealed_at == log[0]["sealed_at"] <= log[1]["fixed_at"] and log[1]["jobs"] == 939
    note = (OPUS_CALIBRATION / "README.md").read_text(encoding="utf-8")
    for words in (
        vision.MODEL,
        "opus_handoff.py",
        "2026-09-23",
        "everything with Opus",
        "failed-deepseek-401/VERDICTS.jsonl",
        "produced no verdict",
    ):
        assert words in note, words
    ledger = OPUS_CALIBRATION / "VERDICTS.jsonl"
    if ledger.exists():  # the answers come after the seal and the fixed sample, and by Opus only
        for entry in vision.Ledger(ledger).lines:
            assert str(entry.line["judged_at"]) >= log[1]["fixed_at"]
            assert entry.line["model"] == vision.MODEL


def test_the_jobs_command_fixes_the_sample_it_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _sealed(tmp_path)
    monkeypatch.setattr(worklist, "build_state", lambda *args: "state")
    monkeypatch.setattr(labels, "pilot_tiles", lambda: [])
    monkeypatch.setattr(labels, "load_labelled", lambda: [])
    monkeypatch.setattr(calibrate, "c1_jobs", lambda state, tiles, labelled: [_job(7), _job(8)])
    assert calibrate.main(["jobs", "--run-dir", str(run)]) == 0
    jobs, digest = calibrate.sealed_jobs(run)
    assert [job.image_id for job in jobs] == [7, 8]
    assert _log(run)[1]["jobs_sha256"] == digest


# ======================================================================= the C1 handoff round
SHARD = SITE[:8]
GALLERY_ANSWER = json.dumps(
    {"kind": "site_photo", "other_site": False, "other_place": "", "subject": "stone row"}
)
HERO_ANSWER = '{"shows_archaeology": true, "structure": "stone row", "generic_landscape": false}'


def _offsite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: list[int]) -> None:
    """One real image per job (`_job` names `<id>.webp` on SITE), as the offsite copy lays it out."""
    root = tmp_path / "offsite"
    (root / SHARD).mkdir(parents=True)
    for n, image_id in enumerate(ids):
        buf = io.BytesIO()
        Image.new("RGB", (40 + n, 30), (100, 80 + n, 60)).save(buf, format="WEBP")
        (root / SHARD / f"{image_id}.webp").write_bytes(buf.getvalue())
    real = vision.Images
    monkeypatch.setattr(vision, "Images", lambda: real((root,)))


def test_the_c1_questions_go_through_the_handoff_and_are_measured_by_the_sealed_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export -> an Opus agent answers each question -> validate -> import -> evaluate."""
    run, eye = _c1_dir(tmp_path, monkeypatch, ledger=False)
    _offsite(tmp_path, monkeypatch, _c1_ids())
    jobs, digest = calibrate.sealed_jobs(run)
    handoff = tmp_path / "handoff"
    ask = ["vision", "--run-dir", str(run)]
    with pytest.raises(SystemExit):
        calibrate.main(ask)  # one half of the round, named: never a silent default
    assert calibrate.main([*ask, "--handoff-import", str(handoff)]) == vision.EXIT_INPUT
    assert not (run / "VERDICTS.jsonl").exists()  # nothing was answered: nothing is written

    assert calibrate.main([*ask, "--handoff-export", str(handoff)]) == vision.EXIT_OK
    lines = OH.manifest(handoff)
    assert [line["label"] for line in lines] == [vision.job_label(job) for job in jobs]
    assert {line["batch_id"] for line in lines} == {calibrate.C1}
    assert len(list((handoff / OH.IMAGES_DIR).iterdir())) == len(_c1_ids())
    report = OH.validate(handoff)
    assert (len(report.answered), len(report.missing)) == (0, len(jobs))
    for line in lines:
        OH.write_answer(
            handoff,
            batch_id=line["batch_id"],
            stage=line["stage"],
            label=line["label"],
            text=GALLERY_ANSWER if line["field"] == vision.GALLERY else HERO_ANSWER,
            answered_by="test-agent",
        )
    assert OH.validate(handoff).ok

    assert calibrate.main([*ask, "--handoff-import", str(handoff)]) == vision.EXIT_OK
    ledger = vision.Ledger(run / "VERDICTS.jsonl").lines
    assert len(ledger) == len(jobs)
    assert all(e.ok and e.line["model"] == vision.MODEL for e in ledger)
    assert {e.line["answered_by"] for e in ledger} == {"test-agent"}
    record = calibrate.command_evaluate(run, eye)
    assert record["metrics"]["T0"] == {**record["metrics"]["T0"], "pass": True, "jobs": len(jobs)}
    assert record["jobs_sha256"] == digest


def test_a_sample_edited_after_it_was_fixed_is_neither_asked_nor_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, eye = _c1_dir(tmp_path, monkeypatch)
    calibrate.command_evaluate(run, eye)
    jobs, _ = calibrate.sealed_jobs(run)
    (run / "JOBS.jsonl").write_text(vision.jobs_text(jobs[:-1]), encoding="utf-8", newline="\n")
    handoff = tmp_path / "handoff"
    for half in ("--handoff-export", "--handoff-import"):
        with pytest.raises(calibrate.CalibrationError, match="changed after it was fixed"):
            calibrate.main(["vision", "--run-dir", str(run), half, str(handoff)])
    assert not handoff.exists()
    with pytest.raises(calibrate.CalibrationError, match="changed after it was fixed"):
        calibrate.command_evaluate(run, eye)
    with pytest.raises(calibrate.CalibrationError, match="changed after it was fixed"):
        calibrate.verify_admission(run)
