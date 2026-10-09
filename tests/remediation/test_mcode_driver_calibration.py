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

from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401 - the autouse fixture

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
                {
                    "k": k,
                    "verdict": verdict,
                    "quotes": [
                        {"url": f"https://example.org/k{k}", "quote": f"page {k} says so, in full"}
                    ],
                    "note": "the page says it",
                }
                for k, verdict in enumerate(verdicts, start=1)
            ],
            "coherent": coherent,
            "broken": [],
            "note": "the kept text reads as one description",
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


# ---------------------------------------------------------------------------- the calibration run
def a_source_run(
    tmp_path: Path, handoff: Path, batches: tuple[str, ...] = ("wc-0001", "wc-0002")
) -> Path:
    """A WC run whose verification round 1 registered `handoff`, with the questions it asked."""
    run = tmp_path / "run"
    (run / "verify" / "round-1").mkdir(parents=True)
    (run / "POPULATION.json").write_text(json.dumps({"kind": "wc"}) + "\n", encoding="utf-8")
    record = {
        "round": 1,
        "stage": "verify",
        "handoff": str(handoff),
        "exported_at": "2026-10-01T18:00:00+00:00",
        "batches": {batch: [f"{batch}-site-{n}" for n in range(2)] for batch in batches},
        "shown": {f"{batch}-site-{n}": [1] for batch in batches for n in range(2)},
    }
    (run / "verify" / "round-1" / "ROUND.json").write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8"
    )
    return run


def test_the_calibration_answers_into_a_registered_run_of_its_own(tmp_path: Path) -> None:
    """Measured 2026-10-03: the WC tool accepts a verification answer only into a handoff that one
    of the run's rounds registers (`wc/cli.py:_verify_round_of`). The calibration copy had no run,
    so the model refused to answer and reported the block - correctly. Registering the copy as a
    round of the *production* run is no option: that run's import would read the comparison answers
    as verdicts. So the calibration gets a run of its own."""
    from wc import cli as C  # the tool whose guard refused the copy

    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wc-0001"])

    cal_run = D.register_calibration_run(a_source_run(tmp_path, handoff), handoff, out, ["wc-0001"])

    assert cal_run != tmp_path / "run"  # not the production run
    brief = C.verify_brief(cal_run, out, "wc-0001")
    assert "wc-0001" in brief
    label = C._verify_round_of(cal_run, out)["batches"]["wc-0001"][0]
    answer = json.loads(verify_answer("SUPPORTED"))
    answer["site_id"] = label
    assert C.verify_check_answer(cal_run, out, "wc-0001", label, json.dumps(answer)) is None
    # a batch that is not calibrated is no question of the calibration run
    with pytest.raises(C.WcRunError, match="no batch"):
        C.verify_brief(cal_run, out, "wc-0002")


def test_a_calibration_run_is_written_once_and_names_what_it_was_calibrated_from(
    tmp_path: Path,
) -> None:
    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wc-0001"])
    source = a_source_run(tmp_path, handoff)

    cal_run = D.register_calibration_run(source, handoff, out, ["wc-0001"])
    record = json.loads((cal_run / "verify" / "round-1" / "ROUND.json").read_text(encoding="utf-8"))

    assert record["calibration"] is True
    assert record["calibrated_from"]["batches"] == ["wc-0001"]
    with pytest.raises(D.DriverError, match="written once"):
        D.register_calibration_run(source, handoff, out, ["wc-0001"])


def test_a_batch_the_source_run_never_exported_cannot_be_calibrated(tmp_path: Path) -> None:
    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wc-0001"])

    with pytest.raises(D.DriverError, match="no batch"):
        D.register_calibration_run(a_source_run(tmp_path, handoff), handoff, out, ["wc-0099"])


def a_check_run(tmp_path: Path, handoff: Path, batch: str = "wc-0001") -> Path:
    """A WC run whose *check* round registered `handoff` - the check rounds live in the run's
    `ROUNDS.jsonl`, not in a `verify/round-N/ROUND.json`, and they carry neither a stage nor the
    shown sentence numbers a verification round carries. The sites come with the run: the check's own
    answer check reads them."""
    run = tmp_path / "check-run"
    run.mkdir(parents=True)
    (run / "POPULATION.json").write_text(json.dumps({"kind": "wc"}) + "\n", encoding="utf-8")
    record = {
        "round": 1,
        "handoff": str(handoff),
        "exported_at": "2026-09-28T12:00:00+00:00",
        "asked": {f"{batch}-site-{n}": [1, 2] for n in range(2)},
        "batches": {batch: [f"{batch}-site-{n}" for n in range(2)]},
        "failures": {},
    }
    (run / "ROUNDS.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (run / "SITES.jsonl").write_text(
        "".join(
            json.dumps({"site_id": f"{batch}-site-{n}", "sentences": ["a", "b"]}) + "\n"
            for n in range(2)
        )
        + json.dumps({"site_id": "other-site", "sentences": ["c"]})
        + "\n",
        encoding="utf-8",
    )
    return run


def test_a_check_calibration_is_registered_in_rounds_jsonl_too(tmp_path: Path) -> None:
    """The check stage keeps its rounds in the run's ROUNDS.jsonl, so the calibration run has to
    carry its round there; a calibration written only under `verify/` would be refused exactly the
    way the verification one was."""
    from wc import cli as C

    handoff = a_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wc-0001"])

    cal_run = D.register_calibration_run(a_check_run(tmp_path, handoff), handoff, out, ["wc-0001"])

    assert "wc-0001" in C.brief(cal_run, out, "wc-0001")
    assert not (cal_run / "verify").exists()
    (line,) = (cal_run / "ROUNDS.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["calibration"] is True
    # the answer check of a check round reads the run's sites: the calibration brings its own and
    # nothing else
    assert sorted(C.read_sites(cal_run)) == ["wc-0001-site-0", "wc-0001-site-1"]


def test_a_calibration_run_counts_as_ready_in_either_layout(tmp_path: Path) -> None:
    """Measured 2026-10-03: the check calibration refused to start because the readiness check looked
    for `verify/round-1/ROUND.json` only. A check lane's round lives in `ROUNDS.jsonl`, and refusing
    there was right: the file the check had written is the other one."""
    handoff = a_handoff(tmp_path)
    check_out = tmp_path / "check-calibration"
    D.copy_for_calibration(handoff, check_out, ["wc-0001"])
    check_run = D.register_calibration_run(
        a_check_run(tmp_path, handoff), handoff, check_out, ["wc-0001"]
    )
    verify_out = tmp_path / "verify-calibration"
    D.copy_for_calibration(handoff, verify_out, ["wc-0001"])
    verify_run = D.register_calibration_run(
        a_source_run(tmp_path, handoff), handoff, verify_out, ["wc-0001"]
    )

    assert D.calibration_run_ready(check_run) is True
    assert D.calibration_run_ready(verify_run) is True
    assert D.calibration_run_ready(tmp_path / "nothing") is False


def a_fields_handoff(tmp_path: Path, batch: str = "wd3-r0-b0001") -> Path:
    """An answered fields handoff: batch folders with a `wd3/` stage, a prompt and an answer per site."""
    handoff = tmp_path / "fields-handoff"
    stage = handoff / batch / "wd3"
    stage.mkdir(parents=True)
    for label in ("site-a", "site-b"):
        (stage / f"{label}.prompt.txt").write_text("the question\n", encoding="utf-8")
        (stage / f"{label}.answer.json").write_text(
            json.dumps({"text": field_answer(), "model": "m"}) + "\n", encoding="utf-8"
        )
    (handoff / batch / "MANIFEST.jsonl").write_text("{}\n", encoding="utf-8")
    return handoff


def field_answer() -> str:
    return json.dumps(
        {
            "site_id": "site-a",
            "fields": {"period_start": {"value": "Archaic", "note": "the page says so"}},
            "note": "filled from the stored source",
        }
    )


def a_fields_run(tmp_path: Path, handoff: Path, batch: str = "wd3-r0-b0001") -> Path:
    """A fields run: the rule it was built under, the round that registered `handoff` (with the
    per-label field names), and the classified sites the round's own check reads."""
    run = tmp_path / "fields-run"
    run.mkdir(parents=True)
    (run / "RUN.json").write_text(
        json.dumps({"rule": "one-family", "stage": "wd3"}) + "\n", encoding="utf-8"
    )
    (run / "ROUNDS.jsonl").write_text(
        json.dumps(
            {
                "round": 0,
                "handoff": str(handoff),
                "exported_at": "2026-10-01T18:12:14+00:00",
                "batches": {batch: ["site-a", "site-b"]},
                "fields": {"site-a": ["period_start"], "site-b": ["period_start"]},
                "notes": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "CLASSIFIED.jsonl").write_text(
        "".join(
            json.dumps({"site_id": label, "name": label, "fields": {"period_start": {}}}) + "\n"
            for label in ("site-a", "site-b", "site-c")
        ),
        encoding="utf-8",
    )
    return run


def test_a_fields_calibration_is_registered_with_the_rule_and_its_own_sites(tmp_path: Path) -> None:
    """Measured 2026-10-03: the fields tool refuses the copy for the same reason the WC tool does -
    `handoff.py brief` answers "is not the directory of an exported round of <run>" - so the field
    fill, the lane that finds the missing `period_start` of 618 sites, could not be calibrated at
    all. Its round lives in `ROUNDS.jsonl` as well, but it carries the per-label field names, the
    rule the run was built under, and the classified sites its own check reads."""
    from fields import handoff as FH

    handoff = a_fields_handoff(tmp_path)
    out = tmp_path / "calibration"
    D.copy_for_calibration(handoff, out, ["wd3-r0-b0001"])

    cal_run = D.register_calibration_run(
        a_fields_run(tmp_path, handoff), handoff, out, ["wd3-r0-b0001"]
    )

    assert "wd3-r0-b0001" in FH.brief(cal_run, out, "wd3-r0-b0001")
    assert D.calibration_run_ready(cal_run) is True
    assert sorted(FH.read_classified(cal_run)) == [
        "site-a",
        "site-b",
    ]  # its own sites, not the run's
    (line,) = (cal_run / "ROUNDS.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["fields"] == {"site-a": ["period_start"], "site-b": ["period_start"]}
    assert record["calibration"] is True


def test_a_fields_calibration_prompt_names_the_fields_tool_and_its_own_run(tmp_path: Path) -> None:
    """The driver's calibration built the *WC* brief for every lane type. For the field fill that is
    the wrong tool, the wrong arguments and the wrong rule - the agent would run a WC brief against
    a fields handoff and be refused, exactly as the WC calibration was on its first day."""
    prompt = D.calibration_prompt(
        lane="fields",
        run="output/remediation/calibration/fields-01-run",
        handoff=Path("h"),
        batch="b",
    )

    assert "fields" in prompt and "handoff.py" in prompt
    assert "wc/cli.py" not in prompt
    assert "output/remediation/calibration/fields-01-run" in prompt


def fill_answer(*fields: tuple[str, str, str]) -> str:
    """A field-fill answer: `period_start` replaced with "201", `site_type` unresolved, ..."""
    return json.dumps(
        {
            "fields": {
                name: {
                    "decision": decision,
                    "value": value,
                    "quotes": [{"url": f"https://example.org/{name}", "quote": "page says so"}],
                    "reasoning": "the page says so",
                }
                for name, decision, value in fields
            }
        }
    )


def test_a_field_fill_answer_is_compared_per_field_with_its_value() -> None:
    """The field fill's answer has a third shape: a `fields` object per site, one decision and value
    per field. Measured 2026-10-03: `fields-02` answered 24 of 24 questions and the comparison
    reported **0 units** and every label unanswered - it knew only the check and the verification
    shape, so a filled field counted as nothing to compare."""
    same = fill_answer(("period_start", "replace", "201"), ("site_type", "unresolved", ""))
    report = D.compare_answers("fields", [SITE], {SITE: same}, {SITE: same})

    assert report.unanswered == ()
    assert report.units == 2  # one unit per filled field, no coherent flag in this shape
    assert report.agreement == 1.0


def test_a_field_that_resolves_to_a_different_value_is_a_disagreement() -> None:
    report = D.compare_answers(
        "fields",
        [SITE],
        {SITE: fill_answer(("period_start", "unresolved", ""))},
        {SITE: fill_answer(("period_start", "replace", "201"))},
    )

    (only,) = report.disagreements
    assert (only.unit, only.recorded, only.fresh) == ("period_start", "unresolved", "replace: 201")
    assert only.fresh_sources == ("https://example.org/period_start",)


def test_a_value_that_differs_only_in_surrounding_whitespace_is_the_same_value() -> None:
    """The comparison reads what the lane would write, and the lane trims a value before it stores
    it (`fields/answers.py`: "a trimmed, non-empty string"). Whitespace *inside* a value is part of
    the value and stays a difference - normalising more than the lane does would hide a real one."""
    report = D.compare_answers(
        "fields",
        [SITE],
        {SITE: fill_answer(("coordinates", "replace", " 41.148, 24.389 "))},
        {SITE: fill_answer(("coordinates", "replace", "41.148, 24.389"))},
    )

    assert report.agreement == 1.0
    assert report.disagreements == ()

    spaced = D.compare_answers(
        "fields",
        [SITE],
        {SITE: fill_answer(("coordinates", "replace", "41.148, 24.389"))},
        {SITE: fill_answer(("coordinates", "replace", "41.148,24.389"))},
    )
    assert spaced.units == 1 and spaced.agreed == 0  # inside the value: a real difference


def test_a_kept_field_is_compared_by_its_decision_not_by_its_value() -> None:
    """`keep` writes nothing, so its value is not part of what the lane would do - and the field's
    own rule says it need not even be the stored one: `period_start` accepts any year in the stored
    value's bucket and `coordinates` any point within `KEEP_KM`
    (`fields/answers.py`: "keep, but the year is not in the stored value's bucket"). Measured
    2026-10-03: `fields-02` counted a `keep: 42.0465` against a `keep: 42.046332` as a
    disagreement - that is the harness inventing a difference, not a model judgement."""
    report = D.compare_answers(
        "fields",
        [SITE],
        {SITE: fill_answer(("period_start", "keep", "201"))},
        {SITE: fill_answer(("period_start", "keep", "199"))},
    )

    assert report.units == 1
    assert report.agreement == 1.0
    assert report.disagreements == ()


def test_a_kept_field_against_a_replaced_one_is_a_disagreement() -> None:
    """The decision is the whole unit for a `keep`: keeping and replacing the same cell are
    opposite verdicts even when the value is the same string."""
    report = D.compare_answers(
        "fields",
        [SITE],
        {SITE: fill_answer(("site_type", "keep", "temple"))},
        {SITE: fill_answer(("site_type", "replace", "temple"))},
    )

    (only,) = report.disagreements
    assert (only.unit, only.recorded, only.fresh) == ("site_type", "keep", "replace: temple")


# ---------------------------------------------------------------------------- the verdict
def test_a_calibration_with_an_unanswered_question_does_not_pass() -> None:
    """Owner decision 2026-10-03 (O18) asks for >= 90 % agreement. A question the model never
    answered is not agreement, and a lane measured on half its questions has not been measured."""
    report = D.compare_answers(
        "wc-verify",
        [SITE, OTHER_SITE],
        {SITE: verify_answer("SUPPORTED")},
        {SITE: verify_answer("SUPPORTED")},
    )

    assert report.passed is False
    assert report.to_dict()["passed"] is False


def test_the_verdict_is_the_agreement_floor_the_owner_decided() -> None:
    assert (
        D.compare_answers(
            "wc-verify",
            [SITE],
            {SITE: verify_answer("SUPPORTED")},
            {SITE: verify_answer("SUPPORTED")},
        ).passed
        is True
    )
    # 10 of 11 judged units (one claim of ten in a different verdict): 0.909, over the floor
    ten = verify_answer(*["SUPPORTED"] * 10)
    nine = verify_answer(*["SUPPORTED"] * 9, "NOT SUPPORTED")
    assert D.compare_answers("wc-verify", [SITE], {SITE: ten}, {SITE: nine}).passed is True
    # 9 of 11: 0.818, under it
    assert (
        D.compare_answers(
            "wc-verify",
            [SITE],
            {SITE: ten},
            {SITE: verify_answer(*["SUPPORTED"] * 8, "NOT SUPPORTED", "NOT SUPPORTED")},
        ).passed
        is False
    )
    assert D.AGREEMENT_FLOOR == 0.9


def test_no_questions_measured_is_not_a_pass() -> None:
    assert D.compare_answers("wc-verify", [SITE], {SITE: verify_answer("KEEP")}, {}).passed is False


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
            str(a_source_run(tmp_path, handoff)),
            "--batches",
            "wc-0001",
            "--prepare-only",
        ]
    )

    assert code == 0
    assert (out / "RECORDED.json").exists()
    assert (out / "wc-0001" / "check" / f"{SITE}.prompt.txt").exists()
    assert not (out / "wc-0001" / "check" / f"{SITE}.answer.json").exists()
    # the copy is a round of a run of its own, so the tool's own helpers accept it
    assert (tmp_path / "calibration-run" / "verify" / "round-1" / "ROUND.json").exists()


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


class TestAOneVerdictAnswerIsMeasuredOnTheValueItWrites:
    """The identity questions (D13, D20, D23): the verdict is a unit, and so is every value the
    answer asks to be written. A role that picks the right verdict and another value has not agreed."""

    @staticmethod
    def answer(verdict: str, **extra: Any) -> str:
        return json.dumps({"site_id": SITE, "verdict": verdict, "why": "w", **extra})

    @staticmethod
    def target(qid: str) -> dict[str, Any]:
        return {"qid": {"value": qid, "quotes": []}, "name": {"value": "n", "quotes": []}}

    def test_each_written_value_is_a_unit_next_to_the_verdict(self) -> None:
        assert D._verdicts(self.answer("KEEP")) == (("verdict", "KEEP"),)
        assert D._verdicts(self.answer("RETARGET", target=self.target("Q200"))) == (
            ("verdict", "RETARGET"),
            ("target.qid", "Q200"),
        )
        assert D._verdicts(self.answer("RENAME", new_name="Kydonia", attested_as="label")) == (
            ("verdict", "RENAME"),
            ("new_name", "Kydonia"),
        )
        assert D._verdicts(self.answer("PERIOD_WRONG", period_start=-500, found_start=-300)) == (
            ("verdict", "PERIOD_WRONG"),
            ("period_start", "-500"),
            ("found_start", "-300"),
        )
        assert D._verdicts(self.answer("SPEAK", spoken="Kydonia")) == (
            ("verdict", "SPEAK"),
            ("spoken", "Kydonia"),
        )
        assert D._verdicts(self.answer("MERGE", merge_with="x")) == (
            ("verdict", "MERGE"),
            ("merge_with", "x"),
        )

    @pytest.mark.parametrize(
        ("recorded", "fresh"),
        [
            (("RETARGET", {"target": {"qid": {"value": "Q200"}}}), ("RETARGET", {"target": {"qid": {"value": "Q300"}}})),
            (("RENAME", {"new_name": "Kydonia"}), ("RENAME", {"new_name": "Cydonia"})),
            (("PERIOD_WRONG", {"period_start": -500}), ("PERIOD_WRONG", {"period_start": -400})),
            (("SPEAK", {"spoken": "Kydonia"}), ("SPEAK", {"spoken": "Chania"})),
        ],
    )  # fmt: skip
    def test_the_right_verdict_with_another_value_is_a_disagreement(
        self, recorded: tuple[str, dict], fresh: tuple[str, dict]
    ) -> None:
        got = D.compare_answers(
            "x", [SITE], {SITE: self.answer(recorded[0], **recorded[1])},
            {SITE: self.answer(fresh[0], **fresh[1])},
        )  # fmt: skip
        assert (got.units, got.agreed) == (2, 1)
        assert got.disagreements[0].unit != "verdict"
