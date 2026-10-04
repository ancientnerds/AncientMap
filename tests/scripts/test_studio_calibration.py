# SPDX-License-Identifier: AGPL-3.0-only
"""`scripts/studio_calibration.py`: the worksheet the owner reads at the source text.

Two defects on 2026-10-03 are held in place here: the worksheet asked `claims.live_text` for
every quote, which refuses any source that is not TDM-reserved and so ended the report on the
first archived-text quote; and it reported every line the owner had not judged yet as "refuted",
which reads as a finding where there is only a blank.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]


def _script():
    """`scripts/studio_calibration.py` is a script, not a package member; load it by path."""
    spec = importlib.util.spec_from_file_location(
        "studio_calibration_under_test", REPO / "scripts" / "studio_calibration.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cal = _script()

TEXTS = {
    "aaa111": "the Eighth Air Force reported the crash on 8 July 1947 and named the officer",
    "bbb222": "the recovered debris was weather-balloon material, the report concludes",
    "ccc333": "the programme ran from 2007 to 2012 at about $22 million",
}


def _dossier():
    return SimpleNamespace(
        sources={sid: {"id": sid, "url": f"https://example.test/{sid}"} for sid in TEXTS},
        texts=TEXTS,
    )


def _answer(verdict: str, sid: str = "aaa111", quote: str = "8 July 1947") -> dict:
    return {
        "verdict": verdict,
        "quote": quote,
        "quote_source_id": sid,
        "fix_suggestion": "say 8 July",
        "explanation": "because",
    }


def _row(ref: str) -> dict:
    return {"kind": "evidence", "ref": ref, "claim": f"the claim of {ref}"}


@pytest.fixture
def worksheet_parts(monkeypatch):
    """`spot_check` with the two readers of the paper stubbed, so no workspace is needed."""
    monkeypatch.setattr(cal.claims, "load_dossier", lambda ws: _dossier())
    monkeypatch.setattr(cal.claims, "source_texts", lambda ws, dossier: dict(TEXTS))
    rows = {f"evidence-{i}": _row(f"ev-{i:02d}") for i in range(1, 8)}
    lines = {
        "evidence-1": _answer("partly"),
        "evidence-2": _answer("unsupported", sid="", quote=""),
        "evidence-3": _answer("supported", sid="ccc333", quote="$22 million"),
        "evidence-4": _answer("supported", sid="bbb222", quote="weather-balloon material"),
        "evidence-5": _answer("source_missing", sid="", quote=""),
        "evidence-6": _answer("supported", sid="ccc333", quote="2007 to 2012"),
        "evidence-7": _answer("supported", sid="bbb222", quote="the report concludes"),
    }
    return rows, lines


def test_every_line_but_supported_is_a_deviation(worksheet_parts):
    rows, lines = worksheet_parts
    sheet = cal.spot_check(SimpleNamespace(), rows, lines)

    assert {line["task_id"] for line in sheet["deviations"]} == {
        "evidence-1",
        "evidence-2",
        "evidence-5",
    }
    assert len(sheet["sampled_agreements"]) == 4  # all four agreements; fewer than SPOT_AGREEMENTS
    assert all(line["answer_verdict"] == "supported" for line in sheet["sampled_agreements"])


def test_the_quote_is_read_from_the_archived_text_and_says_where_it_came_from(worksheet_parts):
    """The 2026-10-03 crash: `live_text` refuses any source that is not TDM-reserved."""
    rows, lines = worksheet_parts
    sheet = cal.spot_check(SimpleNamespace(), rows, lines)
    line = next(x for x in sheet["deviations"] if x["task_id"] == "evidence-1")

    assert line["quote_occurs_in_text"] is True
    assert line["quote_read_in"] == "texts/aaa111.txt"
    assert "8 July 1947" in line["context"]


def test_a_quote_that_is_not_in_its_source_is_reported_as_absent(worksheet_parts):
    rows, lines = worksheet_parts
    lines["evidence-1"] = _answer("partly", quote="a sentence the source never carries")
    sheet = cal.spot_check(SimpleNamespace(), rows, lines)
    line = next(x for x in sheet["deviations"] if x["task_id"] == "evidence-1")

    assert line["quote_occurs_in_text"] is False
    assert line["context"] == ""


def test_the_sample_is_repeatable(worksheet_parts):
    rows, lines = worksheet_parts
    first = cal.spot_check(SimpleNamespace(), rows, lines)["sampled_agreements"]
    second = cal.spot_check(SimpleNamespace(), rows, lines)["sampled_agreements"]

    assert [x["task_id"] for x in first] == [x["task_id"] for x in second]


def _sheet(judged: dict[str, str]) -> dict:
    return {
        "deviations": [{"task_id": "a"}, {"task_id": "b"}],
        "sampled_agreements": [{"task_id": "c"}],
    }


def test_a_line_without_a_verdict_is_unjudged_and_not_refuted(tmp_path: Path):
    path = tmp_path / "spot_check_verdicts.json"
    path.write_text(json.dumps({"a": "holds"}), encoding="utf-8")

    out = cal.with_verdicts(_sheet({}), path)

    assert out["all_judged"] is False
    assert out["judged"] == 1
    assert out["of"] == 3
    assert out["refuted"] == []
    assert out["unjudged"] == ["b", "c"]


def test_only_a_line_that_says_refuted_is_refuted(tmp_path: Path):
    path = tmp_path / "spot_check_verdicts.json"
    path.write_text(
        json.dumps({"a": "holds", "b": "refuted: the source says 8 July"}), encoding="utf-8"
    )

    out = cal.with_verdicts(_sheet({}), path)

    assert out["refuted"] == ["b"]
    assert out["unjudged"] == ["c"]
    assert out["all_judged"] is False


def test_a_complete_worksheet_of_holding_lines_passes(tmp_path: Path):
    path = tmp_path / "spot_check_verdicts.json"
    path.write_text(json.dumps({"a": "holds", "b": "holds", "c": "holds"}), encoding="utf-8")

    out = cal.with_verdicts(_sheet({}), path)

    assert out["all_judged"] is True
    assert out["refuted"] == []
    assert out["unjudged"] == []


def test_a_missing_verdict_file_leaves_the_worksheet_unjudged(tmp_path: Path):
    out = cal.with_verdicts(_sheet({}), tmp_path / "does-not-exist.json")

    assert out["verdicts"] is None
    assert out["all_judged"] is False
    assert out["unjudged"] == ["a", "b", "c"]


# --- the check types O18 has to cover (owner decision 2026-10-03) --------------------------------


def _paper(tmp_path: Path, *, image_tasks: int = 0) -> SimpleNamespace:
    """A paper workspace with `image_tasks` exported image tasks and no image verdicts."""
    root = tmp_path / "paper"
    (root / "claims_check").mkdir(parents=True)
    (root / "images").mkdir(parents=True)
    if image_tasks:
        (root / "images" / "tasks.jsonl").write_text(
            "".join(json.dumps({"task_id": f"image-{i}"}) + "\n" for i in range(image_tasks)),
            encoding="utf-8",
        )
    return SimpleNamespace(images_dir=root / "images", root=root)


def _assets(tmp_path: Path, *, marker_stamp: str = "", casefile_stamp: str = "") -> Path:
    """A studio assets tree; a stamp given is written as this model's own verdict."""
    assets = tmp_path / "assets"
    episode = assets / "episodes" / "baalbek-c5"
    if marker_stamp:
        (episode / "markers_check").mkdir(parents=True)
        (episode / "markers_check" / "verdicts.imported-0001.jsonl").write_text(
            json.dumps({"task_id": "marker-1", "verdict": "hits", "answered_by": marker_stamp}) + "\n",
            encoding="utf-8",
        )
    if casefile_stamp:
        episode.mkdir(parents=True, exist_ok=True)
        (episode / "casefile.json").write_text(
            json.dumps(
                {
                    "evidence": [
                        {"id": "e1", "verification": {"status": "verified", "by": casefile_stamp}}
                    ]
                }
            ),
            encoding="utf-8",
        )
    assets.mkdir(parents=True, exist_ok=True)
    return assets


def _recorded(n: int) -> dict[str, dict]:
    return {f"ev-{i:02d}": {"verdict": "supported"} for i in range(1, n + 1)}


def test_only_the_claim_check_has_a_reference_and_the_others_hold(tmp_path: Path):
    """The owner ruling of 2026-10-03: a check type with no recorded verdict to compare a run
    against holds. The image check holds because the paper has no images at all."""
    out = cal.check_types(_paper(tmp_path), _recorded(42), _assets(tmp_path))

    assert out["measured"] == ["claims"]
    assert out["held"] == ["images", "markers", "casefile"]
    assert out["detail"]["claims"]["reference"] == "MiniMax-M3, unchecked"
    assert out["detail"]["claims"]["reference_verdicts"] == 42


def test_the_image_check_names_what_is_missing_instead_of_staying_out(tmp_path: Path):
    out = cal.check_types(_paper(tmp_path, image_tasks=0), _recorded(42), _assets(tmp_path))

    why = out["detail"]["images"]["why"]
    assert out["detail"]["images"]["reference_verdicts"] == 0
    assert "0 exported image task" in why
    assert "0 recorded image verdict" in why


def test_an_exported_image_task_is_not_a_reference(tmp_path: Path):
    """Tasks to check are not verdicts to compare against: the model would grade its own work."""
    out = cal.check_types(_paper(tmp_path, image_tasks=3), _recorded(42), _assets(tmp_path))

    assert out["held"] == ["images", "markers", "casefile"]
    assert "3 exported image task" in out["detail"]["images"]["why"]


def test_marker_and_casefile_verdicts_the_model_wrote_itself_are_no_reference(tmp_path: Path):
    model = cal.mcode_checks.mcode.MODEL
    out = cal.check_types(
        _paper(tmp_path),
        _recorded(42),
        _assets(
            tmp_path,
            marker_stamp=f"{model} (marker check, mcode exec, exec_turn_x, marker-1)",
            casefile_stamp=f"{model} (case file check, mcode exec, exec_turn_y, e1)",
        ),
    )

    assert out["measured"] == ["claims"]
    assert "written by " + model in out["detail"]["markers"]["why"]
    assert "written by " + model in out["detail"]["casefile"]["why"]


def test_a_verdict_another_model_wrote_is_a_reference(tmp_path: Path):
    out = cal.check_types(
        _paper(tmp_path),
        _recorded(42),
        _assets(tmp_path, marker_stamp="a human, checked at the picture on 2026-10-03"),
    )

    assert "markers" in out["measured"]
    assert "markers" not in out["held"]
    assert out["detail"]["markers"]["reference"] == "a human, checked at the picture on 2026-10-03"


def _passing(agreement: bool = True) -> tuple[dict, dict, dict]:
    return (
        {"agreement_pass": agreement, "false_sources": []},
        {"all_judged": True, "refuted": []},
        {"held": []},
    )


def test_a_held_check_type_keeps_o18_from_passing():
    """O18 asks for agreement on the checks; a type that cannot be measured is not a pass."""
    measurement, worksheet, types = _passing()
    types["held"] = ["images"]

    assert cal.verdict_passed(measurement, worksheet, types) is False


def test_everything_together_passes_o18():
    assert cal.verdict_passed(*_passing()) is True


def test_low_agreement_keeps_o18_from_passing():
    measurement, worksheet, types = _passing(agreement=False)

    assert cal.verdict_passed(measurement, worksheet, types) is False
