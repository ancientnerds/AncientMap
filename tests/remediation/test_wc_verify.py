"""Lane WC's verification (owner decisions O5 and O2 of 2026-09-26; the pilots of 2026-09-27): does
every site whose check kept a sentence go to an independent verifier before the build, is every
sentence the verifier does not confirm dropped, is a text a drop changed verified once more by a new
agent - and cleared when that agent does not confirm it - and does nothing unverified reach the gate
plan or the pilot's judge?

The pure rules are `scripts/remediation/phase4/wc4.py` (`run_verification`, `apply_verification`,
`verification_problems`); the stage is `scripts/remediation/wc/cli.py` (`verify-export`,
`verify-brief`, `verify-check-answer`, `verify-import`), the answer shape `wc/answers.parse_verify`.
The writer's refusal of an unverified plan is tested in `test_phase4_wc_write.py`. The mutation cases
are `WC_VERIFY_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py`. No socket, no model, no
database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from wc import answers as A  # noqa: E402
from wc import cli as C  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.wc_fixtures import (  # noqa: E402
    OH,
    WC4,
    M,
    wiki_cache,  # noqa: E402,F401 - the autouse fixture
)

#: Site B: its second sentence leans on its first ("It was carved ...").
TEXT_B = "The Hypogeum lies in Paola. It was carved about 4000 BC."
#: Site C: the check keeps nothing, so there is nothing to verify.
TEXT_C = "Giants built it in one night. It glows at dusk."


def _rows() -> list[dict]:
    return [
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)),
        FX.row(FX.SITE_B, TEXT_B, raw_data=None, name="Hal Saflieni"),
        FX.row(FX.SITE_C, TEXT_C, raw_data=FX.legacy_raw(TEXT_C), name="Ggantija"),
    ]


def _answers() -> dict[str, str]:
    return {
        FX.SITE_A: FX.answer(FX.SITE_A, [
            FX.keep(1, FX.Q_COMPLEX),
            FX.trimmed(2, ", and they were built by giants", FX.Q_DATE),
            FX.keep(3, FX.Q_ZAMMIT),
        ]),
        FX.SITE_B: FX.answer(FX.SITE_B, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE)]),
        FX.SITE_C: FX.answer(FX.SITE_C, [FX.drop(1), FX.drop(2)]),
    }  # fmt: skip


def _checked(tmp_path: Path, *, pilot: bool = True) -> Path:
    """A run whose check round is imported: A keeps 3 (one trimmed), B keeps 2, C nothing."""
    run, handoff = tmp_path / "runs" / "wc-v", tmp_path / "handoff" / "wc-v-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    draw = {"pilot": 3, "seed": 1} if pilot else {"pilot": None, "seed": None}
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], **draw)
    FX.record_answers(handoff, _answers())
    C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    return run


def _hv(tmp_path: Path, stage: str = "verify") -> Path:
    return tmp_path / "handoff" / f"wc-v-{stage}"


def _verify(run: Path, handoff: Path, answers: dict[str, str], *, by: str = "opus-verify") -> dict:
    FX.record_answers(handoff, answers, by=by)
    return C.cmd_verify_import(run, handoff, client=FX.FakeClient(), pace=0.0)


def _prompt(handoff: Path, label: str) -> str:
    (line,) = [line for line in OH.manifest(handoff) if line["label"] == label]
    return (handoff / line["prompt_path"]).read_text(encoding="utf-8")


def _rename(handoff: Path, label: str, name: str) -> None:
    """Record an answer under another agent's name (as a reused or mislabelled agent would)."""
    for line in OH.manifest(handoff):
        if line["label"] == label:
            stored = json.loads((handoff / line["answer_path"]).read_text(encoding="utf-8"))
            stored["answered_by"] = name
            (handoff / line["answer_path"]).write_text(json.dumps(stored), encoding="utf-8")


# ------------------------------------------------------------------------------ the pure rules
def _decisions() -> list[WC4.Decision]:
    return [
        WC4.Decision(1, "The Tarxien Temples are in Malta.", WC4.Verdict.KEEP, None, None),
        WC4.Decision(2, "It dates to about 3150 BC.", WC4.Verdict.KEEP, None, None),
        WC4.Decision(3, "The site was excavated in 1915.", WC4.Verdict.KEEP, None, None),
    ]


def _quotes() -> dict[int, list[WC4.Quote]]:
    page = WC4.Quote(FX.WIKI, "Tarxien Temples", "a quote the check verified")
    return {1: [page], 2: [page], 3: [page]}


def _round(shown: list[int], **change) -> dict:
    """A recorded round over the pure tests' decisions: the text it showed keeps `shown`."""
    return FX.passed_round(shown, text=FX.shown_text(_decisions(), _quotes(), shown), **change)


def test_a_text_every_sentence_of_which_the_verifier_confirms_is_verified_as_it_stands() -> None:
    decisions, record = WC4.apply_verification(_decisions(), _quotes(), [_round([1, 2, 3])])
    assert decisions == _decisions()
    assert (record["status"], record["before"], record["kept"]) == (
        "verified",
        [1, 2, 3],
        [1, 2, 3],
    )
    (derived,) = record["rounds"]
    assert derived["passed"] and not derived["cleared"] and derived["drops"] == {}
    composed = WC4.compose(decisions, _quotes())
    assert derived["text_sha256"] == WC4.M.text_sha256(composed.description)


@pytest.mark.parametrize(
    ("verdicts", "reason"),
    [(["SUPPORTED", "SUPPORTED", "WRONG"], "verify-wrong"),
     (["SUPPORTED", "SUPPORTED", "UNSUPPORTED"], "verify-unsupported")],
)  # fmt: skip
def test_a_wrong_or_unsupported_sentence_is_dropped_and_the_changed_text_is_due_again(
    verdicts, reason
) -> None:
    round_1 = _round([1, 2, 3], verdicts=verdicts)
    decisions, rounds, status = WC4.run_verification(_decisions(), _quotes(), [round_1])
    assert status is None  # verify2 is due: a drop can break what stays
    assert [(d.verdict.value, d.reason) for d in decisions][2] == ("DROP", reason)
    assert rounds[0]["drops"] == {"3": reason} and not rounds[0]["passed"]
    with pytest.raises(WC4.WcError, match=r"round 2 \(verify2\) is due"):
        WC4.apply_verification(_decisions(), _quotes(), [round_1])
    round_2 = _round([1, 2], number=2, answered_by="opus-wc-verify2-0001")
    final, record = WC4.apply_verification(_decisions(), _quotes(), [round_1, round_2])
    assert (record["status"], record["kept"]) == ("verified", [1, 2])
    assert WC4.compose(final, _quotes()).description == (
        "The Tarxien Temples are in Malta [1]. It dates to about 3150 BC [1]."
    )


def test_a_sentence_that_leans_on_a_dropped_one_goes_with_it() -> None:
    round_1 = _round([1, 2, 3], verdicts=["UNSUPPORTED", "SUPPORTED", "SUPPORTED"])
    decisions, _, status = WC4.run_verification(_decisions(), _quotes(), [round_1])
    assert [d.reason for d in decisions] == ["verify-unsupported", "leans-on-dropped", None]
    assert status is None and WC4.kept_numbers(decisions) == [3]


def test_an_incoherent_text_drops_the_named_sentence_and_one_with_none_named_is_cleared() -> None:
    named = _round([1, 2, 3], coherent=False, broken=[3])
    decisions, _, status = WC4.run_verification(_decisions(), _quotes(), [named])
    assert [d.reason for d in decisions] == [None, None, "verify-incoherent"] and status is None
    unnamed = _round([1, 2, 3], coherent=False)
    decisions, record = WC4.apply_verification(_decisions(), _quotes(), [unnamed])
    assert record["status"] == "cleared" and record["rounds"][0]["cleared"]
    assert {d.reason for d in decisions} == {WC4.DropReason.VERIFY_CLEARED}


def test_a_drop_that_leaves_nothing_clears_the_site_without_a_second_round() -> None:
    every = _round([1, 2, 3], verdicts=["WRONG", "SUPPORTED", "UNSUPPORTED"])
    decisions, record = WC4.apply_verification(_decisions(), _quotes(), [every])
    assert record["status"] == "cleared" and record["kept"] == []
    assert WC4.compose(decisions, _quotes()).description is None


@pytest.mark.parametrize(
    "round_2",
    [_round([1, 2], number=2, verdicts=["SUPPORTED", "UNSUPPORTED"]),
     _round([1, 2], number=2, coherent=False, broken=[2]),
     _round([1, 2], number=2, coherent=False)],
    ids=["unsupported", "incoherent-named", "incoherent"],
)  # fmt: skip
def test_a_second_verification_that_does_not_confirm_the_text_clears_the_site(round_2) -> None:
    round_1 = _round([1, 2, 3], verdicts=["SUPPORTED", "SUPPORTED", "WRONG"])
    decisions, record = WC4.apply_verification(_decisions(), _quotes(), [round_1, round_2])
    assert record["status"] == "cleared" and record["kept"] == []
    assert [d.reason for d in decisions] == ["verify-cleared", "verify-cleared", "verify-wrong"]


def test_nothing_the_check_kept_is_nothing_to_verify() -> None:
    dropped = [WC4.Decision(1, "A temple.", WC4.Verdict.DROP, None, WC4.DropReason.UNSUPPORTED)]
    assert WC4.apply_verification(dropped, {}, [])[1]["status"] == "nothing-kept"
    with pytest.raises(WC4.WcError, match="had ended"):
        WC4.run_verification(dropped, {}, [_round([])])


@pytest.mark.parametrize(
    ("rounds", "message"),
    [
        ([_round([1, 2])], "showed sentences"),
        ([_round([1, 2, 3], number=2)], "recorded as round 2"),
        ([{**_round([1, 2, 3]), "extra": 1}], "carries"),
        ([_round([1, 2, 3], broken=[1])], "names no broken sentence"),
        ([_round([1, 2, 3], coherent=False, broken=[4])], "ascending K numbers"),
        ([_round([1, 2, 3], coherent=False, broken=[2, 1])], "ascending K numbers"),
        ([_round([1, 2, 3], verdicts=["SUPPORTED", "FINE", "SUPPORTED"])], "not one of"),
        ([_round([1, 2, 3]), _round([1, 2, 3], number=2)], "had ended"),
        # the review of 2026-09-27: a round is tied to the text it showed, not only to its numbers
        ([{**_round([1, 2, 3]), "text_sha256": "c" * 64}], "the check moved after"),
        ([{k: v for k, v in _round([1, 2, 3]).items() if k != "text_sha256"}], "carries"),
        ([_round([1, 2, 3], verdicts=["SUPPORTED", "SUPPORTED", "WRONG"]),
          _round([1, 2], number=2, verdicts=["SUPPORTED", "WRONG"]),
          _round([1], number=3)], "had ended"),
    ],
)  # fmt: skip
def test_a_recorded_round_is_read_strictly(rounds, message) -> None:
    with pytest.raises(WC4.WcError, match=message):
        WC4.run_verification(_decisions(), _quotes(), rounds)


def test_a_round_is_tied_to_the_text_it_showed_not_only_to_its_sentence_numbers() -> None:
    """The review of 2026-09-27: a round recorded over one text is never read over another text of
    the same sentence numbers - a trim that moved after the verifier answered. `verified_sha256`
    is the recorded text's sha256, not one recomputed from whatever the check composes now."""
    trimmed = [
        *_decisions()[:2],
        WC4.Decision(
            3,
            "The site was excavated in 1915 by Zammit.",
            WC4.Verdict.KEEP_TRIMMED,
            " in 1915",
            None,
        ),
    ]
    with pytest.raises(WC4.WcError, match="the check moved after the verifier answered"):
        WC4.run_verification(trimmed, _quotes(), [_round([1, 2, 3])])
    shown = FX.shown_text(trimmed, _quotes(), [1, 2, 3])
    assert shown.endswith("The site was excavated by Zammit [1].")
    final, record = WC4.apply_verification(
        trimmed, _quotes(), [FX.passed_round([1, 2, 3], text=shown)]
    )
    assert record["status"] == "verified" and final == trimmed
    assert record["rounds"][0]["text_sha256"] == WC4.M.text_sha256(shown)


# ------------------------------------------------------------------------------ the answers
def _verify_answer(**change) -> str:
    data = json.loads(FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"]))
    return json.dumps({**data, **change})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_verify_answer(broken=[1]), "names no broken sentence"),
        (_verify_answer(coherent=False, broken=[3]), "ascending k numbers in 1..2"),
        (_verify_answer(coherent=False, broken=[2, 1]), "ascending k numbers"),
        (_verify_answer(coherent=False, broken=[True]), "ascending k numbers"),
        (_verify_answer(coherent="no"), "true or false"),
        (_verify_answer(site_id=FX.SITE_B), "names site"),
        (json.dumps({k: v for k, v in json.loads(_verify_answer()).items() if k != "broken"}),
         "broken"),
        (_verify_answer(kept=[{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": "x"}]),
         "kept covers"),
        (_verify_answer(kept=[{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": "x"},
                              {"k": 2, "verdict": "WRONG", "quotes": [], "note": "x"}]),
         "WRONG rests on at least one quote"),
        (_verify_answer(dropped=[]), "dropped"),
    ],
)  # fmt: skip
def test_a_verifier_answer_out_of_shape_is_refused_and_says_why(text, message) -> None:
    with pytest.raises(A.AnswerError, match=message):
        A.parse_verify(text, site_id=FX.SITE_A, kept=2)


def test_an_incoherent_text_may_name_no_broken_sentence() -> None:
    parsed = A.parse_verify(_verify_answer(coherent=False), site_id=FX.SITE_A, kept=2)
    assert (parsed.coherent, parsed.broken) == (False, ())
    parsed = A.parse_verify(_verify_answer(coherent=False, broken=[2]), site_id=FX.SITE_A, kept=2)
    assert parsed.broken == (2,)


# ------------------------------------------------------------------------------ the stage
def test_verify_asks_every_site_whose_check_kept_a_sentence_with_its_text_as_published(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    summary = C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    assert (summary["round"], summary["stage"], summary["questions"]) == (1, "verify", 2)
    lines = OH.manifest(_hv(tmp_path))  # site C kept nothing: it is not asked
    assert {(line["batch_id"], line["stage"], line["label"]) for line in lines} == {
        ("verify-0001", "verify", FX.SITE_A),
        ("verify-0001", "verify", FX.SITE_B),
    }
    prompt = _prompt(_hv(tmp_path), FX.SITE_A)
    assert "K1: The Tarxien Temples are an archaeological complex in Tarxien, Malta." in prompt
    assert "K2: They date to approximately 3150 BC." in prompt
    assert (
        '    trimmed from: "They date to approximately 3150 BC, and they were built by giants."'
        in prompt
    )
    assert f'    quote: "They date to approximately 3150 BC." - {FX.WIKI}' in prompt
    assert "(3 kept)" in prompt and '"broken": []' in prompt and "[1]" not in prompt
    record = C._verify_round_of(run, _hv(tmp_path))
    assert record["shown"] == {FX.SITE_A: [1, 2, 3], FX.SITE_B: [1, 2]}
    brief = C.verify_brief(run, _hv(tmp_path), "verify-0001")
    assert "--answered-by sonnet-wc-verify-0001" in brief and "--stage verify " in brief
    # the web verifier is Sonnet, high, in every kind of run (owner decision D6, 2026-10-08)
    assert "--model claude-sonnet-5-5 --role web_verifier" in brief
    assert "wc/cli.py verify-check-answer" in brief and "2 site(s)" in brief
    with pytest.raises(C.WcRunError, match="no batch"):
        C.verify_brief(run, _hv(tmp_path), "verify-0009")


def test_nothing_is_built_before_the_verification_is_imported(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    with pytest.raises(C.WcRunError, match=r"round 1 \(verify\) is due"):
        C.cmd_build(run, first_batch=4001)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    with pytest.raises(C.WcRunError, match="exported and not imported"):
        C.cmd_build(run, first_batch=4001)
    with pytest.raises(C.WcRunError, match="exported and not imported"):
        C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)


def test_verify_waits_for_every_check_round(tmp_path: Path) -> None:
    run, handoff = tmp_path / "runs" / "wc-v", tmp_path / "handoff" / "wc-v-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    answers = {**_answers(), FX.SITE_A: FX.answer(FX.SITE_A, [
        FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE),
        FX.keep(3, FX.quote(FX.MUSEUM, "Zammit dug at Tarxien in the year 1915."))])}  # fmt: skip
    FX.record_answers(handoff, answers)
    C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    with pytest.raises(C.WcRunError, match="re-ask"):
        C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)


def test_a_text_the_verifier_confirms_is_built_verified_and_needs_no_second_round(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    summary = _verify(run, _hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    })  # fmt: skip
    assert summary["outcomes"] == {"verified": 2} and summary["to_verify2"] == 0
    with pytest.raises(C.WcRunError, match="nothing to verify at verify2"):
        C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    with pytest.raises(C.WcRunError, match="imported once"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    built = C.cmd_build(run, first_batch=4001)
    assert built["verification"]["by_status"] == {"nothing-kept": 1, "verified": 2}
    final = C._finals(run)[FX.SITE_A]
    assert final["verification"]["status"] == "verified"
    assert final["verification"]["verifiers"] == ["opus-verify-verify-0001"]
    check = final["evidence"]["description"] and WC4.DescriptionCheck.from_dict(
        json.loads((run / C.PLAN_FILE).read_text("utf-8").splitlines()[0])["outcomes"][0][
            "raw_data"][WC4.CHECK_KEY])  # fmt: skip
    assert check.verifiers == ("opus-verify-verify-0001",)
    assert check.verified_sha256 == WC4.M.text_sha256(final["description"])
    assert final["evidence"]["sentences"][1]["checked"] == {
        "verdict": "KEEP_TRIMMED", "remove": ", and they were built by giants", "reason": None
    }  # fmt: skip
    assert C._finals(run)[FX.SITE_C]["verification"]["status"] == "nothing-kept"


def test_a_wrong_or_unsupported_sentence_is_dropped_and_the_changed_text_verified_again(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    summary = _verify(run, _hv(tmp_path), {
        # a WRONG whose contradicting quote code does not find still drops its sentence
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["UNSUPPORTED", "SUPPORTED"]),
    })  # fmt: skip
    assert summary["outcomes"] == {"cleared": 1, "due for verify2": 1}
    assert summary["to_verify2"] == 1 and summary["verdicts"]["WRONG"] == 1
    (row_a,) = [
        row
        for row in (run / "verify" / "round-1" / "VERIFIED.jsonl").read_text("utf-8").splitlines()
        if FX.SITE_A in row
    ]
    assert json.loads(row_a)["verdicts"][2]["quotes_found"] is False
    with pytest.raises(C.WcRunError, match=r"round 2 \(verify2\) is due"):
        C.cmd_build(run, first_batch=4001)

    second = C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    assert (second["round"], second["stage"], second["questions"]) == (2, "verify2", 1)
    (line,) = OH.manifest(_hv(tmp_path, "verify2"))
    assert (line["batch_id"], line["stage"], line["label"]) == (
        "verify2-0001",
        "verify2",
        FX.SITE_A,
    )
    prompt = _prompt(_hv(tmp_path, "verify2"), FX.SITE_A)
    assert "(2 kept)" in prompt and "D1: The site was excavated by Themistocles Zammit" in prompt
    # one question serves both rounds: it says nothing that is untrue of verify2 (the review of
    # 2026-09-27) - a broken sentence goes, and what remains is published only as confirmed
    assert "verified again" not in prompt
    assert "what remains is published only if a verifier confirms it" in prompt
    assert "--answered-by sonnet-wc-verify2-0001" in C.verify_brief(
        run, _hv(tmp_path, "verify2"), "verify2-0001"
    )
    _verify(run, _hv(tmp_path, "verify2"),
            {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"])},
            by="opus-verify2")  # fmt: skip
    with pytest.raises(C.WcRunError, match="both verification rounds"):
        C.cmd_verify_export(run, tmp_path / "handoff" / "wc-v-verify3", batch_size=5)
    built = C.cmd_build(run, first_batch=4001)
    finals = C._finals(run)
    assert finals[FX.SITE_A]["description"] == (
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
        "They date to approximately 3150 BC [1]."
    )
    assert [d["reason"] for d in finals[FX.SITE_A]["decisions"]] == [None, None, "verify-wrong"]
    assert finals[FX.SITE_A]["verification"]["verifiers"] == [
        "opus-verify-verify-0001", "opus-verify2-verify2-0001"
    ]  # fmt: skip
    assert finals[FX.SITE_B]["cleared"] is True
    assert [d["reason"] for d in finals[FX.SITE_B]["decisions"]] == [
        "verify-unsupported", "leans-on-dropped"
    ]  # fmt: skip
    assert built["verification"]["verify2_sites"] == 1
    assert (built["verification"]["sentences_before"], built["verification"]["sentences_after"]) == (
        5, 2
    )  # fmt: skip
    assert built["verification"]["verdicts"]["verify"] == {
        "SUPPORTED": 3, "UNSUPPORTED": 1, "WRONG": 1
    }  # fmt: skip
    # the summary carries each site's verification record, as FINAL.jsonl shows it
    by_site = built["verification"]["sites"]
    assert by_site == {label: final["verification"] for label, final in finals.items()}
    assert by_site[FX.SITE_A]["verifiers"] == [
        "opus-verify-verify-0001", "opus-verify2-verify2-0001"
    ]  # fmt: skip
    assert [r["verdicts"] for r in by_site[FX.SITE_A]["rounds"]] == [
        {"1": "SUPPORTED", "2": "SUPPORTED", "3": "WRONG"}, {"1": "SUPPORTED", "2": "SUPPORTED"}
    ]  # fmt: skip
    assert by_site[FX.SITE_C] == {
        "status": "nothing-kept", "verifiers": [], "before": [], "kept": [], "rounds": []
    }  # fmt: skip
    assert json.loads((run / C.SUMMARY_FILE).read_text("utf-8")) == built


def test_the_nyons_case_drops_the_sentence_whose_reference_broke(tmp_path: Path) -> None:
    """Pilot 2 (2026-09-27, Nyons): a trim of sentence 1 left sentence 2's "the ancient name"
    pointing at another referent. The verifier names K2; it goes; the rest is verified again."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    _verify(run, _hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3, coherent=False, broken=[2]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2, coherent=False),
    })  # fmt: skip
    C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    assert [line["label"] for line in OH.manifest(_hv(tmp_path, "verify2"))] == [FX.SITE_A]
    _verify(run, _hv(tmp_path, "verify2"),
            {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"])},
            by="opus-verify2")  # fmt: skip
    C.cmd_build(run, first_batch=4001)
    finals = C._finals(run)
    assert [d["reason"] for d in finals[FX.SITE_A]["decisions"]] == [
        None, "verify-incoherent", None
    ]  # fmt: skip
    # site B: incoherent, no sentence named - the description is cleared
    assert finals[FX.SITE_B]["cleared"] is True
    assert {d["reason"] for d in finals[FX.SITE_B]["decisions"]} == {"verify-cleared"}


def test_a_changed_text_the_second_verifier_does_not_confirm_is_cleared(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    _verify(run, _hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "UNSUPPORTED"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    })  # fmt: skip
    C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    summary = _verify(run, _hv(tmp_path, "verify2"),
                      {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "UNSUPPORTED"])},
                      by="opus-verify2")  # fmt: skip
    assert summary["outcomes"] == {"cleared": 1}
    C.cmd_build(run, first_batch=4001)
    final = C._finals(run)[FX.SITE_A]
    assert final["cleared"] is True and final["verification"]["status"] == "cleared"
    assert C._finals(run)[FX.SITE_B]["verification"]["status"] == "verified"


def test_a_verifier_who_checked_the_site_or_verified_it_before_is_refused(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    answers = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    }
    FX.record_answers(_hv(tmp_path), answers, by="opus-verify")
    _rename(_hv(tmp_path), FX.SITE_B, "opus-check-wc-0001")  # site B's checker
    with pytest.raises(C.WcRunError, match="checked or verified this site before"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()
    _rename(_hv(tmp_path), FX.SITE_B, "opus-verify-verify-0001")
    C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    FX.record_answers(_hv(tmp_path, "verify2"),
                      {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 2)},
                      by="opus-verify2")  # fmt: skip
    _rename(_hv(tmp_path, "verify2"), FX.SITE_A, "opus-verify-verify-0001")  # round 1's verifier
    with pytest.raises(C.WcRunError, match="checked or verified this site before"):
        C.cmd_verify_import(run, _hv(tmp_path, "verify2"), client=FX.FakeClient(), pace=0.0)


def test_a_verification_round_is_imported_only_when_it_validates_and_asks_its_own_question(
    tmp_path: Path, monkeypatch
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(_hv(tmp_path), {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3)})
    with pytest.raises(C.WcRunError, match="1 missing"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    FX.record_answers(_hv(tmp_path), {FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2)})
    monkeypatch.setattr(C.P, "VERIFY_QUESTION", C.P.VERIFY_QUESTION.replace("DECIDE", "DECIDE:"))
    with pytest.raises(C.WcRunError, match="not this question's"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)


def test_a_malformed_verifier_answer_stops_the_import(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    _broken = json.dumps({**json.loads(FX.verification(FX.SITE_B, ["SUPPORTED"] * 2)),
                          "broken": [1]})  # fmt: skip
    FX.record_answers(_hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3), FX.SITE_B: _broken})  # fmt: skip
    with pytest.raises(C.WcRunError, match="malformed answer"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)


def _both_answers() -> dict[str, str]:
    return {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    }


def _edit_check(run: Path, label: str, n: int, change) -> None:
    """Change a site's recorded check result of sentence `n` (round 1) by hand: the import is
    write-once, so this is what a check that moved under a verification looks like."""
    path = run / "round-1" / "ANSWERS.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["label"] == label:
            change(row["results"][str(n)])
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _drop(result: dict) -> None:
    result["answer"].update(verdict="DROP", remove=None, reason="unsupported")


def _untrim(result: dict) -> None:
    result["answer"].update(verdict="KEEP", remove=None)


def test_a_check_round_is_imported_once_and_never_after_the_verification_is_exported(
    tmp_path: Path,
) -> None:
    """The review of 2026-09-27: an import run again overwrote `round-<n>/ANSWERS.jsonl`, so a
    text no verifier saw could reach the build. A check round is imported once, and no check round
    after a verifier was shown its text."""
    run = _checked(tmp_path)
    handoff = tmp_path / "handoff" / "wc-v-r1"
    answers = run / "round-1" / "ANSWERS.jsonl"
    before = answers.read_bytes()
    with pytest.raises(C.WcRunError, match="round 1 was imported; a round is imported once"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert answers.read_bytes() == before
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    answers.unlink()  # taken away by hand, to import the round again
    with pytest.raises(C.WcRunError, match="the verification was exported"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not answers.exists()


@pytest.mark.parametrize(
    ("label", "n", "change", "message"),
    [
        (FX.SITE_A, 3, _drop, "the kept text is not the one verify showed"),
        # site B's second sentence leans on its first: dropping S1 leaves nothing to verify
        (FX.SITE_B, 1, _drop, "is not due at verify"),
        (FX.SITE_A, 2, _untrim, "the exported prompt is not this question's"),
    ],
    ids=["another-kept-set", "nothing-kept", "another-trim"],
)
def test_a_check_that_moved_between_verify_export_and_import_is_refused(
    tmp_path: Path, label, n, change, message
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(_hv(tmp_path), _both_answers(), by="opus-verify")
    _edit_check(run, label, n, change)
    with pytest.raises(C.WcRunError, match=message):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()


def test_a_check_that_moved_after_the_verification_is_never_built(tmp_path: Path) -> None:
    """The review of 2026-09-27: `verify-import` records the sha256 of the text each question
    showed; a check that composes another text afterwards is refused by the build (and wherever the
    record is read), so a text no verifier saw never gets a record saying `verified`."""
    run = _checked(tmp_path)
    FX.verify_all(run, _hv(tmp_path))
    rows = {
        row["site_id"]: row
        for row in (
            json.loads(line)
            for line in (run / "verify" / "round-1" / "VERIFIED.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    assert rows[FX.SITE_A]["text_sha256"] == WC4.M.text_sha256(
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
        "They date to approximately 3150 BC [1]. "
        "The site was excavated by Themistocles Zammit in 1915 [2]."
    )
    _edit_check(run, FX.SITE_A, 2, _untrim)  # the trim taken back after the verifier answered
    with pytest.raises(WC4.WcError, match="the check moved after the verifier answered"):
        C.cmd_build(run, first_batch=4001)
    assert not (run / C.PLAN_FILE).exists()


def test_a_verified_round_whose_question_the_check_no_longer_gives_is_never_built(
    tmp_path: Path,
) -> None:
    """The recorded `prompt_sha256` is asked again at build: a check that moved under a round
    without changing the text (a quote the verifier was shown, replaced) is refused too."""
    run = _checked(tmp_path)
    FX.verify_all(run, _hv(tmp_path))
    _edit_check(
        run, FX.SITE_A, 1, lambda r: r["quotes"][0].update(quote="Another quote of that page.")
    )
    with pytest.raises(C.WcRunError, match="asked another question than the site's state gives"):
        C.cmd_build(run, first_batch=4001)
    assert not (run / C.PLAN_FILE).exists()


def test_each_verification_round_takes_a_new_empty_handoff_and_names_only_its_own(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    _verify(run, _hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    })  # fmt: skip
    with pytest.raises(C.WcRunError, match="is already a verification round"):
        C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    stray = _hv(tmp_path, "verify2") / "notes.txt"
    stray.parent.mkdir(parents=True)
    stray.write_text("an earlier attempt", encoding="utf-8")
    with pytest.raises(C.WcRunError, match="is not empty"):
        C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    assert not (run / "verify" / "round-2").exists()
    nowhere = tmp_path / "handoff" / "wc-v-nowhere"
    for call in (
        lambda: C.verify_brief(run, nowhere, "verify-0001"),
        lambda: C.verify_check_answer(run, nowhere, "verify-0001", FX.SITE_A, "{}"),
        lambda: C.cmd_verify_import(run, nowhere, client=FX.FakeClient(), pace=0.0),
    ):
        with pytest.raises(C.WcRunError, match="is no verification round"):
            call()


def test_a_manifest_that_is_not_the_verification_rounds_record_is_refused(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(_hv(tmp_path), _both_answers(), by="opus-verify")
    path = run / "verify" / "round-1" / "ROUND.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["batches"]["verify-0001"].remove(FX.SITE_B)
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="the manifest is not the verification round's record"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()


def test_a_calibration_round_is_never_imported(tmp_path: Path) -> None:
    """Owner decision 2026-10-03 (O18): the calibration re-answers recorded questions so a model can
    be measured against them. Those answers are a comparison, not a verdict, and no ledger may ever
    read them - so the round carries the mark and the import refuses it."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(_hv(tmp_path), _both_answers(), by="opus-verify")
    path = run / "verify" / "round-1" / "ROUND.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["calibration"] = True
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(C.WcRunError, match="calibration round"):
        C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()


def test_verify_check_answer_reads_the_shape_only(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    good = FX.verification(FX.SITE_B, ["SUPPORTED", "WRONG"], coherent=False, broken=[2])
    assert C.verify_check_answer(run, _hv(tmp_path), "verify-0001", FX.SITE_B, good) is None
    short = FX.verification(FX.SITE_B, ["SUPPORTED"])
    assert "kept covers" in C.verify_check_answer(run, _hv(tmp_path), "verify-0001", FX.SITE_B,
                                                  short)  # fmt: skip
    with pytest.raises(C.WcRunError, match="no question"):
        C.verify_check_answer(run, _hv(tmp_path), "verify-0001", FX.SITE_C, good)


def test_the_command_line_runs_the_verification_stage(tmp_path: Path, capsys) -> None:
    run = _checked(tmp_path)
    code = C.main(["verify-export", "--run-dir", str(run), "--handoff", str(_hv(tmp_path))])
    out = capsys.readouterr().out
    assert code == 0 and out.strip().endswith("WC_EXIT=0") and '"stage": "verify"' in out
    answer = tmp_path / "answer.json"
    answer.write_text(FX.verification(FX.SITE_B, ["SUPPORTED"]), encoding="utf-8")
    code = C.main(["verify-check-answer", "--run-dir", str(run), "--handoff", str(_hv(tmp_path)),
                   "--batch-id", "verify-0001", "--label", FX.SITE_B, "--text-file", str(answer)])  # fmt: skip
    assert code == 1 and "kept covers" in capsys.readouterr().out


# ------------------------------------------------------------------------------ the record
def _built(tmp_path: Path) -> dict:
    """Site A after verify (K3 WRONG) and verify2 (confirmed): its FINAL row."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    _verify(run, _hv(tmp_path), {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    })  # fmt: skip
    C.cmd_verify_export(run, _hv(tmp_path, "verify2"), batch_size=5)
    _verify(run, _hv(tmp_path, "verify2"),
            {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 2)}, by="opus-verify2")  # fmt: skip
    C.cmd_build(run, first_batch=4001)
    return C._finals(run)[FX.SITE_A]


def _edit(evidence: dict, change) -> dict:
    copy = json.loads(json.dumps(evidence))
    change(copy)
    return copy


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda e: e.pop("verification"), "no verification record"),
        (lambda e: e["verification"]["rounds"][0].update(answered_by="opus-check-wc-0001"),
         "checked this site"),
        (lambda e: e["verification"]["rounds"][1].update(answered_by="opus-verify-verify-0001"),
         "verified the site twice"),
        (lambda e: e["verification"].update(status="verified", kept=[1, 2, 3]),
         "not what its rounds give"),
        (lambda e: e["verification"]["rounds"][0].update(drops={}), "not what its rounds give"),
        (lambda e: e["verification"]["rounds"].pop(), "not finished"),
        (lambda e: e["verification"]["rounds"][0]["verdicts"][2].update(verdict="SUPPORTED"),
         "had ended"),  # round 1 passed, so the recorded round 2 cannot follow it
        # the final decisions say the WRONG sentence stays: the verification says it goes
        (lambda e: e["sentences"][2].update(verdict="KEEP", reason=None),
         "decisions are not the verified ones"),
        (lambda e: e["sentences"][2]["checked"].update(reason="verify-wrong", verdict="DROP"),
         "the verification's"),
        # the review of 2026-09-27: the trim taken back under the recorded rounds - the evidence
        # composes the whole sentence, the verifiers saw the trimmed one
        (lambda e: (e["sentences"][1]["checked"].update(verdict="KEEP", remove=None),
                    e["sentences"][1].update(verdict="KEEP", remove=None)),
         "the check moved after"),
    ],
)  # fmt: skip
def test_the_verification_the_evidence_records_is_asked_again_from_its_rounds(
    tmp_path: Path, change, message
) -> None:
    final = _built(tmp_path)
    evidence, description = final["evidence"], final["description"]
    assert WC4.verification_problems(evidence, description) == []
    problems = WC4.verification_problems(_edit(evidence, change), description)
    assert problems and any(
        any(part in problem for part in message.split("|")) for problem in problems
    ), problems


def test_a_kept_text_is_published_only_as_its_last_verifier_confirmed_it(tmp_path: Path) -> None:
    final = _built(tmp_path)
    evidence = final["evidence"]
    # a record whose second verifier did not confirm the text, beside the text it did not confirm
    round_1 = {k: evidence["verification"]["rounds"][0][k] for k in WC4.ROUND_KEYS}
    text = FX.shown_text(*WC4.checked_of(evidence), [1, 2])
    refused = FX.passed_round([1, 2], text=text, number=2, verdicts=["SUPPORTED", "WRONG"])
    _, cleared = WC4.apply_verification(*WC4.checked_of(evidence), [round_1, refused])
    problems = WC4.verification_problems(
        {**evidence, "verification": cleared}, final["description"]
    )
    assert "a kept description beside a verification that ended cleared" in problems
    other = final["description"].replace("Malta", "Gozo")
    assert "the description is not the text the last verifier confirmed" in (
        WC4.verification_problems(evidence, other)
    )


def test_a_check_record_is_made_only_for_a_verified_text() -> None:
    round_1 = _round([1, 2, 3], verdicts=["WRONG", "UNSUPPORTED", "WRONG"])
    _, cleared = WC4.apply_verification(_decisions(), _quotes(), [round_1])
    composed = WC4.compose(_decisions(), _quotes())
    with pytest.raises(WC4.WcError, match="published only verified, not 'cleared'"):
        WC4.check_record(
            _decisions(),
            composed,
            _quotes(),
            run="r",
            checked="old",
            verification=cleared,
            checker=M.AI_SYSTEM,
        )


def test_the_evidence_recheck_asks_the_verification_too(tmp_path: Path) -> None:
    """The acceptance re-checks a written site from its journal evidence alone
    (`wc4.evidence_problems`): a verification record that does not hold is a deviation there."""
    _built(tmp_path)
    plan = tmp_path / "runs" / "wc-v" / C.PLAN_FILE
    outcome = WC4.WcOutcome.from_dict(
        json.loads(plan.read_text("utf-8").splitlines()[0])["outcomes"][0]
    )
    assert WC4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data) == []
    dependent = _edit(
        outcome.evidence,
        lambda e: e["verification"]["rounds"][1].update(answered_by="opus-check-wc-0001"),
    )
    problems = WC4.evidence_problems(dependent, outcome.description, outcome.raw_data)
    assert any("opus-check-wc-0001 checked this site" in problem for problem in problems)


def test_the_evidence_recheck_takes_the_written_disclosure_of_its_time(tmp_path: Path) -> None:
    """A text written before 2026-10-01 names `AI_SYSTEM_OPUS` as its checker, truthfully: the
    acceptance re-derives the check record with the written record's own checker (one of
    `AI_SYSTEMS`), so such a site re-checks clean (the 19 deviations of 2026-10-01 were this), and a
    checker outside `AI_SYSTEMS` is still refused."""
    _built(tmp_path)
    plan = tmp_path / "runs" / "wc-v" / C.PLAN_FILE
    outcome = WC4.WcOutcome.from_dict(
        json.loads(plan.read_text("utf-8").splitlines()[0])["outcomes"][0]
    )
    assert outcome.raw_data[WC4.CHECK_KEY]["checker"] == M.AI_SYSTEM_CLAUDE

    def with_checker(name: str) -> dict:
        raw = json.loads(json.dumps(outcome.raw_data))
        raw[WC4.CHECK_KEY]["checker"] = name
        return raw

    written_before = with_checker(M.AI_SYSTEM_OPUS)
    assert WC4.evidence_problems(outcome.evidence, outcome.description, written_before) == []
    foreign = with_checker("opencode-go/deepseek-v4.1-flash")
    problems = WC4.evidence_problems(outcome.evidence, outcome.description, foreign)
    assert any("the check record does not read" in problem for problem in problems)


def test_the_judge_sees_the_text_after_the_verification_and_no_verifier_judges(
    tmp_path: Path,
) -> None:
    final = _built(tmp_path)
    run = tmp_path / "runs" / "wc-v"
    handoff = tmp_path / "handoff" / "wc-v-judge"
    C.cmd_judge_export(run, handoff, batch_size=5)
    prompt = _prompt(handoff, FX.SITE_A)
    assert "K2: They date to approximately 3150 BC." in prompt and "K3" not in prompt
    assert "D1: The site was excavated by Themistocles Zammit in 1915." in prompt
    assert "(2 kept, 1 dropped)" in prompt and final["kept"] == 2
    record = json.loads((run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    assert record["plan_sha256"] == C._sha256(run / C.PLAN_FILE)
    answers = {}
    for site_id, row in C._finals(run).items():
        kept, dropped = C._judge_counts(row)
        answers[site_id] = json.dumps({
            "site_id": site_id,
            "kept": [{"k": k, "verdict": "SUPPORTED", "quotes": [], "note": "j"}
                     for k in range(1, kept + 1)],
            "dropped": [{"d": d, "verdict": "DROP_OK", "quotes": [], "note": "j"}
                        for d in range(1, dropped + 1)],
            "coherent": True, "note": "j",
        })  # fmt: skip
    FX.record_answers(handoff, answers, by="opus-judge")
    _rename(handoff, FX.SITE_C, "opus-verify2-verify2-0001")  # a verifier of site A, not of C
    result = C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not result["passed"] and result["measured"]["independent"] == 2
    assert result["plan_sha256"] == record["plan_sha256"]
