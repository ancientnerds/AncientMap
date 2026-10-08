"""The calibration of lane WC's roles (`wc/calibration.py`, owner decision D6, 2026-10-08), on top of
`calibrate_claude.py`: KEEP and KEEP_TRIMMED agree as one verdict, a known error the pilots' judges
found must be found again, a judge pool is registrable, and a fresh judge may call WRONG one sentence
more than the recorded one did. No socket, no model, no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import calibrate_claude as CC  # noqa: E402
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


def test_the_known_errors_are_what_the_pilots_judges_found_wrong_or_incoherent(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    # site A keeps sentences 1, 2 (trimmed) and 3: the judge's third kept sentence is sentence 3
    assert K.expectations("check", [run]) == [
        {"label": FX.SITE_A, "unit": "sentence-3", "must_not_be": ["KEEP"]}
    ]
    assert K.expectations("judge", [run]) == [
        {"label": FX.SITE_A, "unit": "kept-3", "must_be": ["WRONG"]},
        {"label": FX.SITE_B, "unit": "coherent", "must_be": ["False"]},
    ]
    with pytest.raises(K.WcCalibrationError, match="none of check, judge"):
        K.expectations("verify", [run])


def _sealed_check(tmp_path: Path, run: Path) -> tuple[Path, Path]:
    root = tmp_path / "calibration"
    handoff = tmp_path / "handoff" / "wc-test-r1"
    CC.seal(
        root, calibration_id="wc-check-c1", role="fact_checker", handoff=handoff,
        batches=["wc-0001"], threshold=0.9, now=lambda: NOW,
    )  # fmt: skip
    prepared = CC.prepare(root, calibration_id="wc-check-c1", run=run)
    return root, Path(prepared["prepared"])


def test_the_check_pool_agrees_with_keep_and_trimmed_as_one_and_misses_a_known_error(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root, out = _sealed_check(tmp_path, run)
    known = K.expectations("check", [run])
    # the fresh role keeps sentence 2 whole (the recorded one trimmed it) and keeps the known error
    fresh = {
        FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "KEEP"),
        FX.SITE_B: _check(FX.SITE_B, "KEEP", "KEEP"),
        FX.SITE_C: _check(FX.SITE_C, "DROP", "DROP"),
    }
    FX.record_answers(out, fresh, by="fact_checker:sonnet-check-r1", model=OH.SONNET_MODEL)
    report = K.compare(root, calibration_id="wc-check-c1", merge_check=True, known=known)
    assert report["agreement"] == 1.0 and report["merged"] is True
    assert report["extra_wrong"] == 0
    assert report["lane_failures"] and "known error" in report["lane_failures"][0]
    assert report["known"][0]["fresh"] == "KEEP" and report["known"][0]["missed"] is True
    result = CC.verdict(root, calibration_id="wc-check-c1", false_sources=0, now=lambda: NOW)
    assert result["passed"] is False and result["tier_move"]["to"] == "claude-opus-5-5"
    assert "known error" in result["tier_move"]["reason"]


def test_without_the_merge_a_trimmed_sentence_the_role_keeps_whole_is_a_disagreement(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root, out = _sealed_check(tmp_path, run)
    fresh = {
        FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "DROP"),
        FX.SITE_B: _check(FX.SITE_B, "KEEP", "KEEP"),
        FX.SITE_C: _check(FX.SITE_C, "DROP", "DROP"),
    }
    FX.record_answers(out, fresh, by="fact_checker:sonnet-check-r1", model=OH.SONNET_MODEL)
    report = K.compare(root, calibration_id="wc-check-c1", known=K.expectations("check", [run]))
    assert report["merged"] is False and report["lane_failures"] == []
    assert [d["unit"] for d in report["disagreements"]] == ["sentence-2", "sentence-3"]
    # the same answers, merged: only the sentence the role dropped differs
    again = _pilot(tmp_path / "again")
    root2, out2 = _sealed_check(tmp_path / "again", again)
    FX.record_answers(out2, fresh, by="fact_checker:sonnet-check-r1", model=OH.SONNET_MODEL)
    merged = K.compare(root2, calibration_id="wc-check-c1", merge_check=True)
    assert [d["unit"] for d in merged["disagreements"]] == ["sentence-3"]


def test_an_expectation_about_a_label_outside_the_pool_stops_the_command(tmp_path: Path) -> None:
    run = _pilot(tmp_path)
    root, out = _sealed_check(tmp_path, run)
    FX.record_answers(
        out, {FX.SITE_A: _check(FX.SITE_A, "KEEP", "KEEP", "DROP")}, by="x", model=OH.SONNET_MODEL
    )
    with pytest.raises(K.WcCalibrationError, match="not in the pool"):
        K.compare(
            root,
            calibration_id="wc-check-c1",
            known=[{"label": "zzz", "unit": "sentence-1", "must_not_be": ["KEEP"]}],
        )


# ------------------------------------------------------------------------------ a judge pool
def _sealed_judge(tmp_path: Path, run: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "calibration"
    handoff = tmp_path / "handoff" / "wc-test-judge"
    CC.seal(
        root, calibration_id="wc-judge-c1", role="pilot_judge", handoff=handoff,
        batches=["judge-0001"], threshold=0.9, now=lambda: NOW,
    )  # fmt: skip
    prepared = CC.prepare(
        root, calibration_id="wc-judge-c1", run=run, register=K.register_judge_pool
    )
    return root, Path(prepared["prepared"]), Path(prepared["calibration_run"])


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


def test_a_judge_pool_is_registered_so_that_the_judge_briefs_and_checks_its_answers(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    root, out, calibration_run = _sealed_judge(tmp_path, run)
    record = json.loads((calibration_run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    assert record["calibration"] is True and list(record["batches"]) == ["judge-0001"]
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


def test_a_fresh_judge_must_find_the_known_findings_again_and_may_add_one_wrong(
    tmp_path: Path,
) -> None:
    run = _pilot(tmp_path)
    known = K.expectations("judge", [run])
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
        base = tmp_path / name
        root = base / "calibration"
        handoff = tmp_path / "handoff" / "wc-test-judge"
        CC.seal(
            root, calibration_id="j", role="pilot_judge", handoff=handoff,
            batches=["judge-0001"], threshold=0.5, now=lambda: NOW,
        )  # fmt: skip
        out = Path(
            CC.prepare(root, calibration_id="j", run=run, register=K.register_judge_pool)[
                "prepared"
            ]
        )
        FX.record_answers(out, answers, by="pilot_judge:opus-judge", model=OH.OPUS_MODEL)
        return K.compare(root, calibration_id="j", known=known)

    passing = run_case("ok", fresh(extra_wrong=1))  # site C: one extra WRONG, allowed
    assert passing["extra_wrong"] == 1 and passing["lane_failures"] == []
    too_many = run_case("many", fresh(extra_wrong=2))
    assert too_many["extra_wrong"] == 2 and "extra WRONG" in too_many["lane_failures"][0]
    missed = run_case("missed", fresh(extra_wrong=0, find=False))
    assert [row["missed"] for row in missed["known"]] == [True, True]
    assert len(missed["lane_failures"]) == 2


def test_the_command_line_prints_the_expectations_and_refuses_with_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _pilot(tmp_path)
    assert K.main(["known", "--kind", "check", "--run", str(run)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == [{"label": FX.SITE_A, "unit": "sentence-3", "must_not_be": ["KEEP"]}]
    assert K.main(["compare", "--root", str(tmp_path / "nowhere"), "--id", "nope"]) == 2
    assert "REFUSED" in capsys.readouterr().err
