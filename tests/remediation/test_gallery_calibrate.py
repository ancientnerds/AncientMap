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

from gallery_audit import calibrate, labels, vision, worklist  # noqa: E402

THRESHOLDS_SHA = "1040cd59353181c6928640b3ef51148454cdcbf13b2b31179ca57f3f8b55c99b"
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
