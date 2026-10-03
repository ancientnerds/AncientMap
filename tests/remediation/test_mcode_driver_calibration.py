"""Owner decision 2026-10-03 (O18): the calibration.

Before any lane writes a MiniMax answer to production, the lane type is measured: 2-3
already-answered batches are copied into a *separate* handoff directory, re-answered through the
driver, and compared with the recorded answers. Pass is >= 90 % agreement and 0 false sources.

These tests never call a model. `copy_for_calibration` and `compare_answers` are the two halves
that decide the verdict, and they are pure functions over files and JSON - the part that has to be
right whether or not an agent is in the loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import mcode_driver as D  # noqa: E402

SITE = "1f3c04f4-4025-4779-9968-6aa298127478"
OTHER_SITE = "1f9d65ff-7a7d-4885-85d4-2d581dbc3081"


def check_answer(*verdicts: str) -> str:
    return json.dumps(
        {
            "site_id": SITE,
            "sentences": [
                {
                    "n": n,
                    "verdict": verdict,
                    "quotes": [{"url": f"https://example.org/{n}", "quote": f"q{n}"}],
                }
                for n, verdict in enumerate(verdicts, start=1)
            ],
            "coherent": True,
        }
    )


def verify_answer(*verdicts: str, coherent: bool = True) -> str:
    return json.dumps(
        {
            "site_id": SITE,
            "kept": [
                {"k": k, "verdict": verdict, "quotes": [{"url": f"https://example.org/k{k}"}]}
                for k, verdict in enumerate(verdicts, start=1)
            ],
            "coherent": coherent,
            "broken": [],
        }
    )


def a_handoff(tmp_path: Path, *, batches: tuple[str, ...] = ("wc-0001", "wc-0002")) -> Path:
    """An answered handoff: batch folders, a MANIFEST, a prompt and an answer per label."""
    handoff = tmp_path / "handoff"
    for batch in batches:
        stage = handoff / batch / "check"
        stage.mkdir(parents=True)
        (stage / f"{SITE}.prompt.txt").write_text("the question\n", encoding="utf-8")
        (stage / f"{SITE}.answer.json").write_text(
            json.dumps({"text": check_answer("KEEP", "KEEP_TRIMMED"), "model": "m"}) + "\n",
            encoding="utf-8",
        )
        (handoff / batch / "MANIFEST.jsonl").write_text("{}\n", encoding="utf-8")
    return handoff


# ---------------------------------------------------------------------------- the copy
def test_the_copy_omits_the_answers_of_the_calibrated_batches_only(tmp_path: Path) -> None:
    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"

    recorded = D.copy_for_calibration(handoff, out, ["wc-0001"])

    assert sorted(recorded) == [SITE]
    assert not (out / "wc-0001" / "check" / f"{SITE}.answer.json").exists()
    # the prompt and the manifest came along, so the lane's own brief runs unchanged
    assert (out / "wc-0001" / "check" / f"{SITE}.prompt.txt").exists()
    assert (out / "wc-0001" / "MANIFEST.jsonl").exists()
    # a batch that was not calibrated keeps its answer: the lane sees a round in progress
    assert (out / "wc-0002" / "check" / f"{SITE}.answer.json").exists()
    assert handoff.joinpath("wc-0001", "check", f"{SITE}.answer.json").exists()  # source untouched


def test_the_copy_records_only_the_calibrated_batches_and_by_label(tmp_path: Path) -> None:
    """The answers are filed under the site id, so a batch is a list of labels to compare, never
    one label. A recorded file of every answer in the handoff would be hundreds of judgements nobody
    compares - and the batch id is not a label, so comparing on it compares one site's answer with
    another's."""
    handoff = a_handoff(tmp_path)
    (handoff / "wc-0002" / "check" / f"{OTHER_SITE}.prompt.txt").write_text("q\n", encoding="utf-8")
    (handoff / "wc-0002" / "check" / f"{OTHER_SITE}.answer.json").write_text(
        json.dumps({"text": check_answer("KEEP")}) + "\n", encoding="utf-8"
    )
    out = tmp_path / "calibration"

    recorded = D.copy_for_calibration(handoff, out, ["wc-0001"])

    assert sorted(recorded) == [SITE]  # the calibrated batch's label, not wc-0001, not wc-0002
    assert OTHER_SITE not in recorded
    # the non-calibrated batch keeps its answer in the copy
    assert (out / "wc-0002" / "check" / f"{OTHER_SITE}.answer.json").exists()


def test_a_calibration_copy_is_written_once(tmp_path: Path) -> None:
    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wc-0001"])

    with pytest.raises(D.DriverError, match="written once"):
        D.copy_for_calibration(handoff, out, ["wc-0001"])


# ---------------------------------------------------------------------------- the comparison
def test_the_same_answers_agree_completely(tmp_path: Path) -> None:
    answer = check_answer("KEEP", "KEEP_TRIMMED")
    report = D.compare_answers("wc-check", [SITE], {SITE: answer}, {SITE: answer})

    assert report.agreement == 1.0
    assert report.disagreements == ()
    assert report.unanswered == ()
    assert report.units == 3  # two sentences and the coherent flag


def test_one_wrong_verdict_of_three_units_is_counted_as_a_disagreement() -> None:
    report = D.compare_answers(
        "wc-check",
        [SITE],
        {SITE: check_answer("KEEP", "KEEP_TRIMMED")},
        {SITE: check_answer("KEEP", "DROP")},
    )

    assert report.agreement == pytest.approx(2 / 3)
    (only,) = report.disagreements
    assert (only.unit, only.recorded, only.fresh) == ("sentence-2", "KEEP_TRIMMED", "DROP")
    # the disagreement carries the sources of both sides, so the brief's spot-check can be done
    assert only.recorded_sources == ("https://example.org/1", "https://example.org/2")
    assert only.fresh_sources == ("https://example.org/1", "https://example.org/2")


def test_the_coherent_flag_is_a_judged_unit_of_its_own() -> None:
    """A verification answer that keeps its claim but says the text does not read coherently is not
    the same answer as one that says it does. Counting only the claims would call it agreement."""
    report = D.compare_answers(
        "wc-verify",
        [SITE],
        {SITE: verify_answer("SUPPORTED", coherent=True)},
        {SITE: verify_answer("SUPPORTED", coherent=False)},
    )

    assert report.units == 2  # the one claim and the coherence
    assert report.agreement == pytest.approx(0.5)
    assert {d.unit for d in report.disagreements} == {"coherent"}


def test_a_verification_answer_is_compared_on_its_kept_claims() -> None:
    report = D.compare_answers(
        "wc-verify",
        [SITE],
        {SITE: verify_answer("SUPPORTED", "SUPPORTED")},
        {SITE: verify_answer("SUPPORTED", "NOT SUPPORTED")},
    )

    assert report.units == 3
    assert (report.disagreements[0].unit, report.disagreements[0].fresh) == (
        "kept-2",
        "NOT SUPPORTED",
    )


def test_an_unanswered_label_is_never_agreement() -> None:
    report = D.compare_answers("wc-check", [SITE], {SITE: check_answer("KEEP")}, {})

    assert report.unanswered == (SITE,)
    assert report.agreement == 0.0
    assert report.units == 0


def test_an_answer_of_an_unreadable_shape_is_never_agreement() -> None:
    report = D.compare_answers(
        "wc-check", [SITE], {SITE: check_answer("KEEP")}, {SITE: "the agent gave prose"}
    )

    assert report.unanswered == (SITE,)


def test_the_report_states_the_verdict_the_brief_asks_for() -> None:
    report = D.compare_answers(
        "wc-check",
        [SITE],
        {SITE: check_answer("KEEP", "KEEP")},
        {SITE: check_answer("KEEP", "DROP")},
    ).to_dict()

    assert report["lane"] == "wc-check"
    assert report["units"] == 3 and report["agreed"] == 2
    assert report["agreement"] == pytest.approx(0.6667, abs=1e-4)
    assert len(report["disagreements"]) == 1
    assert report["disagreements"][0]["fresh"] == "DROP"
    assert isinstance(report["disagreements"][0]["fresh_sources"], list)


# ---------------------------------------------------------------------------- the command line
def test_the_calibrate_subcommand_is_reachable_and_keeps_its_lane_type(tmp_path: Path) -> None:
    """The subcommand name and `--lane` (the lane *type* being calibrated) are two different
    strings. Measured 2026-10-03: sharing one argparse dest made `--lane wc-verify` overwrite the
    subcommand name, and the driver fell through to the WD3 lane instead of calibrating."""
    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"

    code = D.main(
        [
            "calibrate",
            "--lane",
            "wc-check",
            "--handoff",
            str(handoff),
            "--out",
            str(out),
            "--run",
            str(tmp_path / "run"),
            "--batches",
            "wc-0001",
            "--prepare-only",
        ]
    )

    assert code == 0
    assert (out / "RECORDED.json").exists()
    assert (out / "wc-0001" / "check" / f"{SITE}.prompt.txt").exists()
    assert not (out / "wc-0001" / "check" / f"{SITE}.answer.json").exists()


def test_an_unknown_lane_type_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        D.main(
            [
                "calibrate",
                "--lane",
                "wb-image",
                "--handoff",
                str(tmp_path / "h"),
                "--out",
                str(tmp_path / "o"),
                "--run",
                str(tmp_path / "r"),
                "--batches",
                "b1",
                "--prepare-only",
            ]
        )
