"""Calibration C1 (`scripts/remediation/gallery_audit/calibrate.py`): sealed before the first call,
measured after the last, and admitting a trigger only when every number its threshold names holds.
Offline: the verdicts are ledger lines written here, the labels are the tracked sets.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

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
    vision.write_jobs(tmp_path / "JOBS.jsonl", [_job(1)])
    early = _line(1, judged_at="2026-09-23T09:59:59Z")
    (tmp_path / "VERDICTS.jsonl").write_text(
        json.dumps(early.line, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(calibrate.CalibrationError, match="judged before the seal"):
        calibrate.command_evaluate(tmp_path, None)


def _c1_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, drop: int | None = None
) -> tuple[Path, Path]:
    """A sealed C1 run directory over small label sets, with its ledger and W8-style eye labels.

    The repository root is `tmp_path` (the eye labels must be a repository file), the thresholds
    are the real sealed ones. `drop` leaves one gallery verdict out of the ledger (T0 fails).
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
    definitions = calibrate.THRESHOLDS["definitions"]
    ids = [1, 2, 11, 12, *definitions["gold_foreign"], *definitions["gold_correct"]]
    vision.write_jobs(run / "JOBS.jsonl", [_job(i) for i in ids] + [_job(1, vision.HERO)])
    lines = [_line(i).line for i in ids if i != drop] + [_line(1, vision.HERO).line]
    (run / "VERDICTS.jsonl").write_text(
        "".join(vision.line_text(line) + "\n" for line in lines), encoding="utf-8", newline="\n"
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
    ledger = CALIBRATION / "VERDICTS.jsonl"
    if ledger.exists():  # the pilot transport's run, after the seal: no verdict of it counts today
        lines = vision.Ledger(ledger).lines
        assert all(str(e.line["judged_at"]) >= sealed_at for e in lines)
        if any(e.ok for e in lines):
            with pytest.raises(vision.VisionError, match="answered by"):
                vision.verdicts_by_image(lines, vision.GALLERY_PROMPT_ID)
