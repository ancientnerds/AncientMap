"""The calibration of lane WC's roles (`wc/calibration.py`, owner decision D6, 2026-10-08), on top of
`calibrate_claude.py`: KEEP and KEEP_TRIMMED agree as one verdict, a known error the pilots' judges
found must be found again, a judge pool is registrable, and a fresh judge may call WRONG one sentence
more than the recorded one did. No socket, no model, no database.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import calibrate_claude as CC  # noqa: E402
import roles as RO  # noqa: E402
from wc import calibration as K  # noqa: E402
from wc import cli as C  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.test_wc_verify import _answers, _rows  # noqa: E402
from tests.remediation.wc_fixtures import OH, wiki_cache  # noqa: E402,F401

NOW = "2026-10-09T09:00:00+00:00"
Q_DATE_J = {"url": FX.WIKI, "quote": "They date to approximately 3150 BC."}


def _check(site: str, *verdicts: str) -> str:
    return json.dumps(
        {
            "site_id": site,
            "sentences": [
                {"n": n, "verdict": v, "remove": None, "reason": None, "quotes": [], "note": "x"}
                for n, v in enumerate(verdicts, start=1)
            ],
        }
    )


def test_a_trimmed_sentence_counts_as_kept_and_nothing_else_changes() -> None:
    merged = json.loads(K.merge(_check("s", "KEEP", "KEEP_TRIMMED", "DROP")))
    assert [r["verdict"] for r in merged["sentences"]] == ["KEEP", "KEEP", "DROP"]
    verify = json.dumps({"kept": [{"k": 1, "verdict": "SUPPORTED"}], "coherent": True})
    assert K.merge(verify) == verify and K.merge("not json") == "not json"


# ------------------------------------------------------------------------------ a check pool
def _pilot(tmp_path: Path) -> Path:
    """A pilot of three sites whose judge found site A's sentence 3 WRONG (a found quote) and
    site B's kept text incoherent."""
    run, _ = FX.build_run(tmp_path, _rows(), _answers(), pilot=True, judged=False)
    handoff = tmp_path / "handoff" / "wc-test-judge"
    C.cmd_judge_export(run, handoff, batch_size=5)
    answers = {}
    for site_id, final in C._finals(run).items():
        kept, dropped = C._judge_counts(final)
        wrong = site_id == FX.SITE_A
        answers[site_id] = json.dumps(
            {
                "site_id": site_id,
                "kept": [
                    {
                        "k": k,
                        "verdict": "WRONG" if wrong and k == kept else "SUPPORTED",
                        "quotes": [Q_DATE_J] if wrong and k == kept else [],
                        "note": "judged",
                    }
                    for k in range(1, kept + 1)
                ],
                "dropped": [
                    {"d": d, "verdict": "DROP_OK", "quotes": [], "note": "judged"}
                    for d in range(1, dropped + 1)
                ],
                "coherent": site_id != FX.SITE_B,
                "note": "judged",
            }
        )
    FX.record_answers(handoff, answers, by="opus-judge")
    C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    return run


def _handoff(tmp_path: Path, name: str) -> Path:
    return tmp_path / "handoff" / f"wc-test-{name}"


#: The pool of each kind in a `_pilot` run: the handoff's name and its batches.
POOLS = {
    "check": ("r1", ["wc-0001"]),
    "verify": ("verify", ["verify-0001"]),
    "judge": ("judge", ["judge-0001"]),
}


def _seal(
    tmp_path: Path,
    run: Path,
    kind: str,
    *,
    cid: str = "c1",
    threshold: float = 0.9,
    root: Path | None = None,
) -> Path:
    """Seal a pool of the pilot with its known errors; returns the calibration root."""
    name, batches = POOLS[kind]
    root = root or tmp_path / "calibration"
    K.seal(
        root, calibration_id=cid, kind=kind, handoff=_handoff(tmp_path, name), batches=batches,
        threshold=threshold, runs=[run], now=lambda: NOW,
    )  # fmt: skip
    return root


def _prepare(root: Path, run: Path, cid: str = "c1") -> Path:
    return Path(K.prepare(root, calibration_id=cid, run=run)["prepared"])


def test_the_known_errors_are_what_the_pilots_judges_found_wrong_or_incoherent(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    # site A keeps sentences 1, 2 (trimmed) and 3: the judge's third kept sentence is sentence 3; a
    # sentence the judge found WRONG may be neither kept whole nor kept trimmed; site B's text was
    # incoherent, which a check answer can only repeat or not repeat
    assert K.expectations("check", [run]) == [
        {"label": FX.SITE_A, "unit": "sentence-3", "must_not_be": ["KEEP", "KEEP_TRIMMED"]},
        {"label": FX.SITE_B, "unit": "kept-text", "must_differ_from_recorded": True},
    ]
    assert K.expectations("judge", [run]) == [
        {"label": FX.SITE_A, "unit": "kept-3", "must_be": ["WRONG"]},
        {"label": FX.SITE_B, "unit": "coherent", "must_be": ["False"]},
    ]
    # the verification shows the same sentences: sentence 3 is its third
    assert K.expectations("verify", [run], handoff=_handoff(tmp_path, "verify")) == [
        {"label": FX.SITE_A, "unit": "kept-3", "must_be": ["UNSUPPORTED", "WRONG"]},
        {"label": FX.SITE_B, "unit": "coherent", "must_be": ["False"]},
    ]
    assert K.expectations("judge", [run], labels={FX.SITE_B}) == [
        {"label": FX.SITE_B, "unit": "coherent", "must_be": ["False"]}
    ]
    with pytest.raises(K.WcCalibrationError, match="names the verification round"):
        K.expectations("verify", [run])
    with pytest.raises(K.WcCalibrationError, match="none of check, verify, judge"):
        K.expectations("dispute", [run])


def test_a_judged_sentence_the_verification_did_not_show_stops_the_command(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    path = run / "verify" / "round-1" / "ROUND.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["shown"][FX.SITE_A] = [1, 2]
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(K.WcCalibrationError, match="not among the sentences"):
        K.expectations("verify", [run], handoff=_handoff(tmp_path, "verify"))


def test_a_known_error_kept_in_trimmed_form_is_still_kept() -> None:
    known = [{"label": "s", "unit": "sentence-3", "must_not_be": sorted(K.MERGED)}]
    recorded = {"s": _check("s", "KEEP", "KEEP", "KEEP")}
    for verdict, missed in (("KEEP", True), ("KEEP_TRIMMED", True), ("DROP", False)):
        rows, failures = K._known(known, {"s": _check("s", "KEEP", "KEEP", verdict)}, recorded)
        assert rows[0]["missed"] is missed and bool(failures) is missed


def test_a_check_that_repeats_the_verdicts_which_built_an_incoherent_text_has_missed_it() -> None:
    known = [{"label": "s", "unit": "kept-text", "must_differ_from_recorded": True}]
    recorded = {"s": _check("s", "KEEP_TRIMMED", "DROP", "KEEP")}
    for fresh, missed in (
        ({"s": _check("s", "KEEP_TRIMMED", "DROP", "KEEP")}, True),
        ({"s": _check("s", "KEEP_TRIMMED", "DROP", "DROP")}, False),
        ({}, True),
    ):
        rows, failures = K._known(known, fresh, recorded)
        assert rows[0]["missed"] is missed and bool(failures) is missed


def test_the_check_pool_agrees_with_keep_and_trimmed_as_one_and_misses_a_known_error(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "check")
    assert CC._sealed(root, "c1")["lane"]["merge"] is True
    out = _prepare(root, run)
    # the fresh role keeps sentence 2 whole (the recorded one trimmed it) and keeps the known error
    fresh = {
        FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "KEEP"),
        FX.SITE_B: _check(FX.SITE_B, "KEEP", "KEEP"),
        FX.SITE_C: _check(FX.SITE_C, "DROP", "DROP"),
    }
    FX.record_answers(out, fresh, by="fact_checker:opus-check-r1", model=OH.OPUS_MODEL)
    report = K.compare(root, calibration_id="c1")
    assert report["agreement"] == 1.0 and report["merged"] is True and report["kind"] == "check"
    assert report["extra_wrong"] == 0
    assert report["lane_failures"] and "known error" in report["lane_failures"][0]
    assert report["known"][0]["fresh"] == "KEEP" and report["known"][0]["missed"] is True
    result = CC.verdict(root, calibration_id="c1", false_sources=0, now=lambda: NOW)
    # the fact checker is on Opus since the tier move of wc-fc-1: a miss is held for the owner
    assert result["passed"] is False and result["model"] == "claude-opus-5-5"
    assert result["tier_move"] is None and "no higher tier" in result["held"]


def test_a_check_pool_that_finds_every_known_error_passes_and_only_a_dropped_sentence_differs(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "check")
    out = _prepare(root, run)
    recorded = json.loads((out / CC.RECORDED_FILE).read_text(encoding="utf-8"))
    fresh = {
        FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "DROP"),
        # a different pattern than the recorded one at site B, whose text came out incoherent
        FX.SITE_B: _check(FX.SITE_B, "DROP", "KEEP"),
        FX.SITE_C: _check(FX.SITE_C, "DROP", "DROP"),
    }
    assert K._sentences(fresh[FX.SITE_B]) != K._sentences(recorded[FX.SITE_B])
    FX.record_answers(out, fresh, by="fact_checker:opus-check-r1", model=OH.OPUS_MODEL)
    report = K.compare(root, calibration_id="c1")
    assert report["lane_failures"] == []
    assert [d["unit"] for d in report["disagreements"]][0] == "sentence-3"


def test_the_pass_conditions_are_the_seals_and_no_other_command_compares_a_lane_pool(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    handoff = _handoff(tmp_path, "r1")
    with pytest.raises(CC.CalibrationError, match="lane WC pool"):
        CC.seal(
            tmp_path / "plain", calibration_id="p", role="fact_checker", handoff=handoff,
            batches=["wc-0001"], threshold=0.9, now=lambda: NOW,
        )  # fmt: skip
    assert not (tmp_path / "plain").exists()
    root = _seal(tmp_path, run, "check")
    out = _prepare(root, run)
    FX.record_answers(
        out, {FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "DROP")}, by="x", model=OH.SONNET_MODEL
    )
    with pytest.raises(CC.CalibrationError, match="lane's own command"):
        CC.compare(root, calibration_id="c1")
    # a comparison that did not come from the lane's command cannot close the calibration
    CC._write_once(
        out / CC.COMPARISON_FILE, {"agreement": 1.0, "units": 3, "agreed": 3, "unanswered": []}
    )
    with pytest.raises(CC.CalibrationError, match="carries no `lane_failures`"):
        CC.verdict(root, calibration_id="c1", false_sources=0, now=lambda: NOW)


def test_a_pool_sealed_without_the_lanes_conditions_or_with_them_changed_is_refused(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    copied = tmp_path / "handoff" / "plain-r1"
    shutil.copytree(_handoff(tmp_path, "r1"), copied)
    root = tmp_path / "calibration"
    CC.seal(
        root, calibration_id="bare", role="fact_checker", handoff=copied, batches=["wc-0001"],
        threshold=0.9, now=lambda: NOW,
    )  # fmt: skip
    with pytest.raises(K.WcCalibrationError, match="sealed without the lane's conditions"):
        K.prepare(root, calibration_id="bare", run=run)
    sealed = _seal(tmp_path, run, "check", cid="edited")
    path = sealed / CC.THRESHOLDS_FILE
    seals = json.loads(path.read_text(encoding="utf-8"))
    seals["edited"]["lane"]["expectations"] = []
    path.write_text(json.dumps(seals), encoding="utf-8")
    with pytest.raises(K.WcCalibrationError, match="were changed"):
        K.prepare(sealed, calibration_id="edited", run=run)


def test_a_known_error_of_a_site_outside_the_pool_is_named_in_the_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _pilot(tmp_path)
    real = K.expectations

    def with_stranger(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            *real(*args, **kwargs),
            {"label": "zzz", "unit": "sentence-1", "must_not_be": ["KEEP"]},
        ]

    monkeypatch.setattr(K, "expectations", with_stranger)
    root = _seal(tmp_path, run, "check")
    lane = CC._sealed(root, "c1")["lane"]
    assert lane["outside_pool"] == ["zzz"] and all(
        e["label"] != "zzz" for e in lane["expectations"]
    )
    assert lane["expectations_sha256"] == K._sha256(lane["expectations"])


def test_an_expectation_about_a_label_outside_the_pool_stops_the_comparison() -> None:
    with pytest.raises(K.WcCalibrationError, match="not in the pool"):
        K._known([{"label": "zzz", "unit": "sentence-1", "must_not_be": ["KEEP"]}], {}, {"a": "x"})


def test_the_kind_fixes_the_role_and_whether_the_verdicts_merge(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    for kind, role, merged in (
        ("check", "fact_checker", True),
        ("verify", "wc_web_verifier", False),
        ("judge", "pilot_judge", False),
    ):
        sealed = K.seal(
            tmp_path / f"cal-{kind}", calibration_id="c1", kind=kind,
            handoff=_handoff(tmp_path, POOLS[kind][0]), batches=POOLS[kind][1], threshold=0.9,
            runs=[run], now=lambda: NOW,
        )  # fmt: skip
        assert sealed["role"] == role and sealed["lane"]["merge"] is merged
        assert sealed["model"] == "claude-opus-5-5"  # all three lane WC roles stand on Opus now


# ------------------------------------------------------------------------------ a verify pool
def test_a_fresh_verification_must_not_support_what_the_judge_found_wrong(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "verify", threshold=0.5)
    out = _prepare(root, run)
    fresh = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "SUPPORTED"]),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED", "SUPPORTED"]),
    }
    FX.record_answers(out, fresh, by="wc_web_verifier:opus-wc", model=OH.OPUS_MODEL)
    report = K.compare(root, calibration_id="c1")
    assert [row["missed"] for row in report["known"]] == [
        True,
        True,
    ]  # kept-3 supported; B coherent
    assert len(report["lane_failures"]) == 2
    assert (
        CC.verdict(root, calibration_id="c1", false_sources=0, now=lambda: NOW)["passed"] is False
    )


def test_a_fresh_verification_that_finds_both_known_errors_passes(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "verify", threshold=0.5)
    out = _prepare(root, run)
    fresh = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "UNSUPPORTED"]),
        FX.SITE_B: FX.verification(
            FX.SITE_B, ["SUPPORTED", "SUPPORTED"], coherent=False, broken=[2]
        ),
    }
    FX.record_answers(out, fresh, by="wc_web_verifier:opus-wc", model=OH.OPUS_MODEL)
    report = K.compare(root, calibration_id="c1")
    assert report["lane_failures"] == [] and report["merged"] is False
    assert CC.verdict(root, calibration_id="c1", false_sources=0, now=lambda: NOW)["passed"] is True


# ------------------------------------------------------------------------------ a judge pool
def test_a_judge_pool_is_registered_so_that_the_judge_briefs_and_checks_its_answers(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    # the pilots' judge rounds were exported before a round recorded its plan: a calibration is tied to none
    path = run / "judge" / "ROUND.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    del record["plan_sha256"]
    path.write_text(json.dumps(record), encoding="utf-8")
    root = _seal(tmp_path, run, "judge")
    prepared = K.prepare(root, calibration_id="c1", run=run)
    out, calibration_run = Path(prepared["prepared"]), Path(prepared["calibration_run"])
    record = json.loads((calibration_run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    assert record["calibration"] is True and list(record["batches"]) == ["judge-0001"]
    assert "plan_sha256" not in record
    text = C.judge_brief(calibration_run, out, "judge-0001")
    assert "--role pilot_judge" in text and "You are Opus judge" in text
    final = C._finals(calibration_run)[FX.SITE_A]
    kept, dropped = C._judge_counts(final)
    problem = C.judge_check_answer(
        calibration_run,
        out,
        "judge-0001",
        FX.SITE_A,
        _judgement(FX.SITE_A, ["SUPPORTED"] * kept, dropped),
    )
    assert problem is None
    with pytest.raises(C.WcRunError, match="a calibration round"):
        C.cmd_judge_import(calibration_run, out, client=FX.FakeClient(), pace=0.0)


def _judgement(site: str, kept: list[str], dropped: int, coherent: bool = True) -> str:
    return json.dumps(
        {
            "site_id": site,
            "kept": [
                {"k": k, "verdict": v, "quotes": [Q_DATE_J] if v == "WRONG" else [], "note": "j"}
                for k, v in enumerate(kept, start=1)
            ],
            "dropped": [
                {"d": d, "verdict": "DROP_OK", "quotes": [], "note": "j"}
                for d in range(1, dropped + 1)
            ],
            "coherent": coherent,
            "note": "j",
        }
    )


def test_a_fresh_judge_must_find_the_known_findings_again_and_may_add_one_wrong(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    finals = C._finals(run)
    sizes = {s: C._judge_counts(f) for s, f in finals.items()}

    def fresh(extra_wrong: int, find: bool = True) -> dict[str, str]:
        out = {}
        for site, (kept, dropped) in sizes.items():
            verdicts = ["SUPPORTED"] * kept
            if site == FX.SITE_A and find:
                verdicts[-1] = "WRONG"
            elif site == FX.SITE_C and extra_wrong:
                verdicts[:extra_wrong] = ["WRONG"] * extra_wrong
            out[site] = _judgement(
                site, verdicts, dropped, coherent=not (find and site == FX.SITE_B)
            )
        return out

    def run_case(name: str, answers: dict[str, str]) -> dict[str, Any]:
        base = tmp_path / name / "calibration"
        root = _seal(tmp_path, run, "judge", threshold=0.5, root=base)
        out = _prepare(root, run)
        FX.record_answers(out, answers, by="pilot_judge:opus-judge", model=OH.OPUS_MODEL)
        return K.compare(root, calibration_id="c1")

    passing = run_case("ok", fresh(extra_wrong=1))  # site C: one extra WRONG, allowed
    assert passing["extra_wrong"] == 1 and passing["lane_failures"] == []
    too_many = run_case("many", fresh(extra_wrong=2))
    assert too_many["extra_wrong"] == 2 and "extra WRONG" in too_many["lane_failures"][0]
    missed = run_case("missed", fresh(extra_wrong=0, find=False))
    assert [row["missed"] for row in missed["known"]] == [True, True]
    assert len(missed["lane_failures"]) == 2


def test_the_command_line_seals_prints_the_expectations_and_refuses_with_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _pilot(tmp_path)
    assert K.main(["known", "--kind", "check", "--run", str(run)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [(e["label"], e["unit"]) for e in printed] == [
        (FX.SITE_A, "sentence-3"),
        (FX.SITE_B, "kept-text"),
    ]
    root = tmp_path / "cal"
    sealed = [
        "seal", "--root", str(root), "--id", "cli", "--kind", "check",
        "--handoff", str(_handoff(tmp_path, "r1")), "--batches", "wc-0001",
        "--threshold", "0.9", "--run", str(run),
    ]  # fmt: skip
    assert K.main(sealed) == 0
    assert len(json.loads(capsys.readouterr().out)["lane"]["expectations"]) == 2
    assert K.main(["compare", "--root", str(tmp_path / "nowhere"), "--id", "nope"]) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert K.main(["compare", "--root", str(root), "--id", "cli"]) == 2  # sealed, not prepared
    assert "is not prepared" in capsys.readouterr().err


# ---------------------------------------- the roles lane WC's pools calibrate (D45, D51; 2026-10-24)
@pytest.mark.parametrize(
    ("kind", "by", "model", "match"),
    [
        ("verify", "web_verifier:sonnet-wc", OH.SONNET_MODEL, "recorded under role web_verifier"),
        ("verify", "wc_web_verifier:sonnet-wc", OH.SONNET_MODEL, "registered to claude-opus-5-5"),
        ("check", "fact_checker:sonnet-check-r1", OH.SONNET_MODEL, "registered to claude-opus-5-5"),
    ],
)
def test_a_fresh_answer_of_the_shared_verifier_or_on_sonnet_is_not_the_pools_role(
    tmp_path: Path, kind: str, by: str, model: str, match: str
) -> None:
    """A verify pool measures lane WC's own `wc_web_verifier`, a check pool the fact checker, both on
    Opus: a fresh answer of the shared `web_verifier`, or a Sonnet answer under either role, is never
    counted as the role's."""
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, kind, threshold=0.5)
    out = _prepare(root, run)
    if kind == "verify":
        fresh = {
            FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "UNSUPPORTED"]),
            FX.SITE_B: FX.verification(
                FX.SITE_B, ["SUPPORTED", "SUPPORTED"], coherent=False, broken=[2]
            ),
        }
    else:
        fresh = {FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "DROP")}
    FX.record_answers(out, fresh, by=by, model=model)
    # another role's answer is the calibration's refusal, a wrong stamp the registry's
    with pytest.raises((CC.CalibrationError, RO.RoleError), match=match):
        K.compare(root, calibration_id="c1")
    assert not (out / CC.COMPARISON_FILE).exists()


def test_a_verify_pool_calibrates_wc_web_verifier_and_its_brief_prints_that_role(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "verify", threshold=0.5)
    sealed = CC._sealed(root, "c1")
    assert (sealed["role"], sealed["model"], sealed["effort"]) == (
        "wc_web_verifier",
        "claude-opus-5-5",
        "high",
    )
    assert sealed["role_sha256"] == RO.role_sha256("wc_web_verifier")
    prepared = K.prepare(root, calibration_id="c1", run=run)
    text = C.verify_brief(
        Path(prepared["calibration_run"]), Path(prepared["prepared"]), "verify-0001"
    )
    assert "--model claude-opus-5-5 --role wc_web_verifier" in text
    assert "--answered-by opus-wc-verify-0001" in text


def _foreign_run(tmp_path: Path, **population: object) -> Path:
    run = tmp_path / "runs" / f"foreign-{len(list(tmp_path.glob('runs/foreign-*')))}"
    run.mkdir(parents=True)
    (run / C.POPULATION_FILE).write_text(json.dumps(population), encoding="utf-8")
    return run


@pytest.mark.parametrize(
    ("kind", "population", "answered_in"),
    [
        ("check", {"kind": "wc-list", "adversarial": True}, "adversarial"),
        ("check", {"kind": "wn-enrich"}, "enrich_writer"),
        ("verify", {"kind": "wn-enrich"}, "web_verifier"),
    ],
)
def test_a_pool_whose_run_answers_its_rounds_in_another_role_is_refused(
    tmp_path: Path, kind: str, population: dict[str, object], answered_in: str
) -> None:
    """An adversarial run's check rounds are the adversarial role's, an enrichment run's check and
    verification rounds lane E's: as a lane WC pool they would calibrate a role that never answers
    them. `seal` refuses such a run among the pilots it reads, `prepare` such a source run."""
    foreign = _foreign_run(tmp_path, **population)
    name, batches = POOLS[kind]
    with pytest.raises(K.WcCalibrationError, match=f"answered as {answered_in}"):
        K.seal(
            tmp_path / "cal-seal", calibration_id="c1", kind=kind,
            handoff=_handoff(tmp_path, name), batches=batches, threshold=0.9, runs=[foreign],
            now=lambda: NOW,
        )  # fmt: skip
    assert not (tmp_path / "cal-seal").exists()
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, kind)
    with pytest.raises(K.WcCalibrationError, match=f"answered as {answered_in}"):
        K.prepare(root, calibration_id="c1", run=foreign)
    assert not (root / "c1").exists()
    assert K.round_role(kind, run) == K.KIND_ROLE[kind]  # the pilot's own rounds are the role's


def test_the_kinds_are_bound_to_the_roles_the_lanes_rounds_answer_in() -> None:
    assert (
        K.KIND_ROLE
        == {
            "check": C.ROLE_CHECK,
            "verify": C.ROLE_VERIFY,
            "judge": C.ROLE_JUDGE,
        }
        == {"check": "fact_checker", "verify": "wc_web_verifier", "judge": "pilot_judge"}
    )


# ------------------------------------------- the seal binds the question (X15, 2026-10-25)
#: The judge question as it stood before X15 in the one respect these tests need: without the
#: coherence step. A pilot exported under it holds questions the code no longer builds.
def _without_the_coherence_step(question: str) -> str:
    start, end = question.index("STEP 3 - coherence"), question.index("Sources follow the same")
    return question[:start] + question[end:]


def _pilot_under_an_older_question(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from wc import prompts as P

    with monkeypatch.context() as patch:
        patch.setattr(P, "JUDGE_QUESTION", _without_the_coherence_step(P.JUDGE_QUESTION))
        return _pilot(tmp_path)


def test_a_seal_binds_the_kinds_texts_and_a_judge_pool_is_asked_the_current_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seal records the sha256 of the question, the brief and the cache note of its kind; the
    judge pool's copy asks the question as the code builds it now - not as the pilot's round asked
    it - while the recorded answers stay the gold."""
    run = _pilot_under_an_older_question(tmp_path, monkeypatch)
    root = _seal(tmp_path, run, "judge")
    lane = CC._sealed(root, "c1")["lane"]
    assert lane["templates"] == K.templates("judge")
    assert sorted(lane["templates"]) == [
        "JUDGE_BRIEF",
        "JUDGE_QUESTION",
        "JUDGE_QUESTION_ENRICH",
        "JUDGE_QUESTION_WN",
        "WIKI_CACHE_NOTE",
    ]
    prepared = K.prepare(root, calibration_id="c1", run=run)
    out, calibration_run = Path(prepared["prepared"]), Path(prepared["calibration_run"])
    source = _handoff(tmp_path, "judge")
    finals, sites = C._finals(calibration_run), C.read_sites(calibration_run)
    for line in OH.manifest(out):
        asked = (out / line["prompt_path"]).read_text(encoding="utf-8")
        site = C.M.PlanSite.from_dict(sites[line["label"]]["plan_site"])
        assert asked == C.judge_prompt(finals[line["label"]], site)
        assert line["prompt_sha256"] == OH.prompt_sha256(asked)
        assert "STEP 3 - coherence" in asked
        assert "STEP 3 - coherence" not in (source / line["prompt_path"]).read_text(
            encoding="utf-8"
        )
    recorded = json.loads((out / CC.RECORDED_FILE).read_text(encoding="utf-8"))
    assert sorted(recorded) == sorted(C._finals(run))
    # answered under the current question, the pool compares as before
    answers = {
        site: _judgement(site, ["SUPPORTED"] * C._judge_counts(final)[0], C._judge_counts(final)[1])
        for site, final in finals.items()
    }
    FX.record_answers(out, answers, by="pilot_judge:opus-judge", model=OH.OPUS_MODEL)
    assert K.compare(root, calibration_id="c1")["units"] > 0


def test_a_question_changed_after_the_seal_refuses_its_prepare_and_its_compare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt edit after the seal: the agents would answer, or answered, another prompt than the
    sealed one, so neither prepare nor compare measures them."""
    from wc import prompts as P

    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "judge", cid="early")
    _seal(tmp_path, run, "judge", cid="late", root=root)
    out = _prepare(root, run, cid="late")
    finals = C._finals(run)
    FX.record_answers(
        out,
        {s: _judgement(s, ["SUPPORTED"] * C._judge_counts(f)[0], C._judge_counts(f)[1])
         for s, f in finals.items()},
        by="pilot_judge:opus-judge", model=OH.OPUS_MODEL,
    )  # fmt: skip
    monkeypatch.setattr(P, "JUDGE_QUESTION", _without_the_coherence_step(P.JUDGE_QUESTION))
    with pytest.raises(K.WcCalibrationError, match="JUDGE_QUESTION changed after early"):
        K.prepare(root, calibration_id="early", run=run)
    assert not (root / "early").exists()
    with pytest.raises(K.WcCalibrationError, match="JUDGE_QUESTION changed after late"):
        K.compare(root, calibration_id="late")
    assert not (out / CC.COMPARISON_FILE).exists()


def test_a_copy_that_asks_the_pilots_old_question_is_not_compared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge pool copied as the pilot's round asked it - before the copy was asked the current
    question - is refused by compare, and so is a fresh answer to that old question."""
    run = _pilot_under_an_older_question(tmp_path, monkeypatch)
    root = _seal(tmp_path, run, "judge")
    out = _prepare(root, run)
    source = _handoff(tmp_path, "judge")
    batch = POOLS["judge"][1][0]
    shutil.copyfile(source / batch / OH.MANIFEST_FILE, out / batch / OH.MANIFEST_FILE)
    for line in OH.manifest(out):
        shutil.copyfile(source / line["prompt_path"], out / line["prompt_path"])
    with pytest.raises(K.WcCalibrationError, match="is not the one the code builds now"):
        K.compare(root, calibration_id="c1")
    assert not (out / CC.COMPARISON_FILE).exists()


def test_a_fresh_judge_answer_to_another_prompt_is_stale(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "judge")
    out = _prepare(root, run)
    line = OH.manifest(out)[0]
    finals = C._finals(run)
    kept, dropped = C._judge_counts(finals[line["label"]])
    body = {
        "prompt_sha256": "0" * 64,
        "text": _judgement(line["label"], ["SUPPORTED"] * kept, dropped),
        "model": OH.OPUS_MODEL,
        "answered_at": NOW,
        "answered_by": "pilot_judge:opus-judge-judge-0001",
    }
    (out / line["answer_path"]).write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(OH.HandoffError, match="stale"):
        K.compare(root, calibration_id="c1")


@pytest.mark.parametrize(("kind", "stands"), [("check", True), ("verify", True), ("judge", False)])
def test_a_seal_made_before_the_texts_were_bound_binds_the_texts_of_its_day(
    tmp_path: Path, kind: str, stands: bool
) -> None:
    """Every lane WC seal of 2026-10-24 carries no `templates`: it binds `TEMPLATES_BEFORE_X15`. The
    check and verify texts are unchanged, so wc-fc-*o and wc-wv-*o stand; the judge question and
    brief were sharpened, so a pilot judge seal of that day (wc-pj-1/2) is refused - its agents
    answered the old question. The re-run is sealed anew (wc-pj-1o/2o)."""
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, kind)
    path = root / CC.THRESHOLDS_FILE
    seals = json.loads(path.read_text(encoding="utf-8"))
    del seals["c1"]["lane"]["templates"]
    path.write_text(json.dumps(seals), encoding="utf-8")
    moved = sorted(
        name
        for name, digest in K.TEMPLATES_BEFORE_X15[kind].items()
        if K.templates(kind)[name] != digest
    )
    assert moved == ([] if stands else ["JUDGE_BRIEF", "JUDGE_QUESTION", "JUDGE_QUESTION_WN"])
    if stands:
        assert K.prepare(root, calibration_id="c1", run=run)["questions"] > 0
    else:
        with pytest.raises(
            K.WcCalibrationError, match="JUDGE_BRIEF, JUDGE_QUESTION, JUDGE_QUESTION_WN changed"
        ):
            K.prepare(root, calibration_id="c1", run=run)


def test_the_bound_texts_of_each_kind_are_its_question_its_brief_and_the_cache_note() -> None:
    assert set(K.KIND_TEMPLATES) == set(K.KIND_ROLE) == set(K.TEMPLATES_BEFORE_X15)
    for kind, names in K.KIND_TEMPLATES.items():
        assert set(K.TEMPLATES_BEFORE_X15[kind]) == set(names)
        assert "WIKI_CACHE_NOTE" in names and any(n.endswith("_BRIEF") for n in names)


def test_a_judge_seal_binds_the_judge_question_of_every_kind_of_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seal does not know which run will be prepared, and `register_judge_pool` asks the judge
    question of that run's kind (WC, WN or lane E): an edit of lane WN's or lane E's judge question
    after the seal refuses the prepare as an edit of WC's does."""
    from wc import prompts_enrich as PE
    from wc import prompts_sonnet as P2

    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "judge")
    for module, name in ((P2, "JUDGE_QUESTION_WN"), (PE, "JUDGE_QUESTION_ENRICH")):
        with monkeypatch.context() as patch:
            patch.setattr(module, name, getattr(module, name) + " ")
            with pytest.raises(K.WcCalibrationError, match=f"{name} changed after c1"):
                K.prepare(root, calibration_id="c1", run=run)
    assert not (root / "c1").exists()
    assert K.prepare(root, calibration_id="c1", run=run)["questions"] > 0


def test_a_judge_question_that_cannot_be_built_refuses_before_the_copy_is_written(
    tmp_path: Path,
) -> None:
    """Every question the copy will be asked is built before anything is written: a site of the pool
    without its site record refuses the prepare, and the calibration id stays free - no copy that is
    written once is left with half its questions replaced."""
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "judge")
    sites = run / C.SITES_FILE
    rows = sites.read_text(encoding="utf-8").splitlines(keepends=True)
    sites.write_text(
        "".join(row for row in rows if json.loads(row)["site_id"] != FX.SITE_A), encoding="utf-8"
    )
    with pytest.raises(K.WcCalibrationError, match="question of the calibration cannot be built"):
        K.prepare(root, calibration_id="c1", run=run)
    assert not (root / "c1").exists() and not (root / "c1-run").exists()


def test_the_copy_is_asked_its_new_questions_only_once_all_are_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`register_judge_pool` builds every question before it replaces the first: a build that fails
    on the last label leaves every question of the copy as it was."""
    run = _pilot(tmp_path)
    root = _seal(tmp_path, run, "judge")
    built, preflight = K._judge_prompt, K._current_questions
    last = sorted(C._finals(run))[-1]
    state = {"preflight_done": False}

    def fails_on_the_last(finals: Any, sites: Any, kind: str, label: str) -> str:
        if label == last and state["preflight_done"]:
            raise RuntimeError("build failed")
        return built(finals, sites, kind, label)

    def after_the_preflight(record: Any, run_: Path, handoff: Path, batches: Any) -> Any:
        asked = preflight(record, run_, handoff, batches)
        state["preflight_done"] = True  # prepare's own build passed; register's build fails
        return asked

    monkeypatch.setattr(K, "_judge_prompt", fails_on_the_last)
    monkeypatch.setattr(K, "_current_questions", after_the_preflight)
    with pytest.raises(RuntimeError, match="build failed"):
        K.prepare(root, calibration_id="c1", run=run)
    out, source = root / "c1", _handoff(tmp_path, "judge")
    batch = POOLS["judge"][1][0]
    assert (out / batch / OH.MANIFEST_FILE).read_bytes() == (
        source / batch / OH.MANIFEST_FILE
    ).read_bytes()
    for line in OH.manifest(out):
        assert (out / line["prompt_path"]).read_bytes() == (
            source / line["prompt_path"]
        ).read_bytes()
