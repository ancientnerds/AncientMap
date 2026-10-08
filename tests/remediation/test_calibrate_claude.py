"""The Claude calibration helper (`scripts/remediation/calibrate_claude.py`), owner decision D6.

A role is calibrated against already-judged cases with a threshold sealed before the run; a failing
role moves up one tier. `seal`, `prepare`, `compare` and `verdict` are pure functions over files and
JSON: these tests answer every question themselves and never call a model or open a socket.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import calibrate_claude as CC  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402

NOW = "2026-10-08T09:00:00+00:00"
SITE_A = "1f3c04f4-4025-4779-9968-6aa298127478"
SITE_B = "1f9d65ff-7a7d-4885-85d4-2d581dbc3081"
SITE_C = "2a9d65ff-7a7d-4885-85d4-2d581dbc3082"


def check_answer(site: str, *verdicts: str) -> str:
    return json.dumps(
        {
            "site_id": site,
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


def put_answer(
    handoff: Path,
    batch: str,
    site: str,
    text: str,
    *,
    model: str = OH.OPUS_MODEL,
    answered_by: str = "opus-agent",
) -> None:
    stage = handoff / batch / "check"
    stage.mkdir(parents=True, exist_ok=True)
    (stage / f"{site}.prompt.txt").write_text(f"the question of {site}\n", encoding="utf-8")
    body = {
        "prompt_sha256": hashlib.sha256(f"the question of {site}\n".encode()).hexdigest(),
        "text": text,
        "model": model,
        "answered_at": NOW,
        "answered_by": answered_by,
    }
    (stage / f"{site}.answer.json").write_text(json.dumps(body) + "\n", encoding="utf-8")
    (handoff / batch / "MANIFEST.jsonl").write_text("{}\n", encoding="utf-8")


def an_answered_handoff(tmp_path: Path, **kwargs: Any) -> Path:
    handoff = tmp_path / "handoff"
    put_answer(handoff, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"), **kwargs)
    put_answer(handoff, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"), **kwargs)
    put_answer(handoff, "wc-0003", SITE_C, check_answer(SITE_C, "DROP"), **kwargs)
    return handoff


def sealed(tmp_path: Path, handoff: Path | None = None, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "calibration_id": "cal-fact-1",
        "role": "fact_checker",
        "handoff": handoff or an_answered_handoff(tmp_path),
        "batches": ["wc-0001", "wc-0002"],
        "threshold": 0.9,
        "now": lambda: NOW,
    }
    kwargs.update(overrides)
    return CC.seal(tmp_path / "calibration", **kwargs)


# --------------------------------------------------------------------------------------- seal
def test_seal_writes_the_cases_the_pool_digest_the_registry_digests_and_the_threshold(
    tmp_path: Path,
) -> None:
    seal = sealed(tmp_path)

    path = tmp_path / "calibration" / CC.THRESHOLDS_FILE
    assert json.loads(path.read_text(encoding="utf-8"))["cal-fact-1"] == seal
    assert seal["role"] == "fact_checker"
    assert seal["model"] == "claude-sonnet-5-5" and seal["effort"] == "high"
    assert seal["threshold"] == 0.9 and seal["max_false_sources"] == 0
    assert seal["case_ids"] == [f"wc-0001/{SITE_A}", f"wc-0002/{SITE_B}"]
    assert seal["batches"] == ["wc-0001", "wc-0002"]
    assert seal["sealed_at"] == NOW
    assert seal["role_sha256"] == RO.role_sha256("fact_checker")
    assert seal["roles_sha256"] == RO.registry_sha256()
    assert len(seal["pool_sha256"]) == 64


def test_the_pool_digest_follows_the_recorded_answers(tmp_path: Path) -> None:
    handoff = an_answered_handoff(tmp_path)
    before = CC.pool_sha256(handoff, ["wc-0001", "wc-0002"])
    assert before == CC.pool_sha256(handoff, ["wc-0001", "wc-0002"])
    assert before != CC.pool_sha256(handoff, ["wc-0001"])
    put_answer(handoff, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "KEEP"))
    assert before != CC.pool_sha256(handoff, ["wc-0001", "wc-0002"])


def test_seal_is_written_once_per_calibration(tmp_path: Path) -> None:
    sealed(tmp_path)
    with pytest.raises(CC.CalibrationError, match="already sealed"):
        sealed(tmp_path, threshold=0.5)
    other = sealed(tmp_path, calibration_id="cal-fact-2")
    assert other["threshold"] == 0.9
    stored = json.loads((tmp_path / "calibration" / CC.THRESHOLDS_FILE).read_text("utf-8"))
    assert sorted(stored) == ["cal-fact-1", "cal-fact-2"]


def test_seal_refuses_once_a_verdict_exists(tmp_path: Path) -> None:
    """A threshold is sealed before the run: a verdict file for this id means it was not."""
    verdicts = tmp_path / "calibration" / CC.VERDICTS_DIR
    verdicts.mkdir(parents=True)
    (verdicts / "cal-fact-1.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(CC.CalibrationError, match="verdict"):
        sealed(tmp_path)


def test_seal_refuses_once_the_calibration_copy_exists(tmp_path: Path) -> None:
    (tmp_path / "calibration" / "cal-fact-1").mkdir(parents=True)
    with pytest.raises(CC.CalibrationError, match="already begun"):
        sealed(tmp_path)


@pytest.mark.parametrize("threshold", [0, 0.0, -0.1, 1.01, True, "0.9", None])
def test_seal_needs_a_threshold_between_zero_and_one(tmp_path: Path, threshold: Any) -> None:
    with pytest.raises(CC.CalibrationError, match="threshold"):
        sealed(tmp_path, threshold=threshold)


def test_seal_refuses_an_unregistered_role(tmp_path: Path) -> None:
    with pytest.raises(RO.RoleError, match="no role"):
        sealed(tmp_path, role="poet")


def test_seal_refuses_a_batch_the_handoff_does_not_have(tmp_path: Path) -> None:
    with pytest.raises(CC.CalibrationError, match="wc-0099"):
        sealed(tmp_path, batches=["wc-0001", "wc-0099"])


def test_seal_refuses_a_pool_with_no_answer(tmp_path: Path) -> None:
    handoff = tmp_path / "empty"
    (handoff / "wc-0001").mkdir(parents=True)
    with pytest.raises(CC.CalibrationError, match="no recorded answer"):
        sealed(tmp_path, handoff=handoff, batches=["wc-0001"])


def test_seal_refuses_minimax_answers_as_ground_truth(tmp_path: Path) -> None:
    """Master plan X6: a MiniMax answer is never ground truth - D10 re-checks all of them."""
    handoff = an_answered_handoff(tmp_path, model=OH.MINIMAX_MODEL)
    with pytest.raises(CC.CalibrationError, match="MiniMax"):
        sealed(tmp_path, handoff=handoff)


def test_seal_refuses_an_answer_without_a_known_stamp(tmp_path: Path) -> None:
    handoff = an_answered_handoff(tmp_path, model="m")
    with pytest.raises(CC.CalibrationError, match="stamp"):
        sealed(tmp_path, handoff=handoff)


# ------------------------------------------------------------------------------------ prepare
def a_source_run(tmp_path: Path, batches: tuple[str, ...]) -> Path:
    """A run whose ROUNDS.jsonl registers the handoff, so the calibration run can copy the round."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "SITES.jsonl").write_text(
        "".join(json.dumps({"site_id": s}) + "\n" for s in (SITE_A, SITE_B, SITE_C)),
        encoding="utf-8",
    )
    record = {
        "round": 1,
        "handoff": str((tmp_path / "handoff").resolve()),
        "batches": {"wc-0001": [SITE_A], "wc-0002": [SITE_B], "wc-0003": [SITE_C]},
    }
    (run / "ROUNDS.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return run


def test_prepare_copies_the_pool_without_its_answers_and_records_them(tmp_path: Path) -> None:
    sealed(tmp_path)
    run = a_source_run(tmp_path, ("wc-0001", "wc-0002"))

    report = CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)

    out = tmp_path / "calibration" / "cal-fact-1"
    assert report["prepared"] == str(out)
    assert report["questions"] == 2
    assert not (out / "wc-0001" / "check" / f"{SITE_A}.answer.json").exists()
    assert (out / "wc-0001" / "check" / f"{SITE_A}.prompt.txt").exists()
    # a batch that is not in the pool keeps its answer, as in the O18 copy
    assert (out / "wc-0003" / "check" / f"{SITE_C}.answer.json").exists()
    recorded = json.loads((out / "RECORDED.json").read_text(encoding="utf-8"))
    assert sorted(recorded) == [SITE_A, SITE_B]
    assert (tmp_path / "calibration" / "cal-fact-1-run" / "ROUNDS.jsonl").exists()


def test_prepare_needs_the_seal_first(tmp_path: Path) -> None:
    an_answered_handoff(tmp_path)
    run = a_source_run(tmp_path, ())
    with pytest.raises(CC.CalibrationError, match="not sealed"):
        CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)


def test_prepare_refuses_a_pool_that_changed_after_the_seal(tmp_path: Path) -> None:
    handoff = an_answered_handoff(tmp_path)
    sealed(tmp_path, handoff=handoff)
    put_answer(handoff, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "KEEP"))
    run = a_source_run(tmp_path, ())
    with pytest.raises(CC.CalibrationError, match="pool"):
        CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)


def test_prepare_refuses_a_role_that_changed_after_the_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sealed(tmp_path)
    run = a_source_run(tmp_path, ())
    monkeypatch.setattr(RO, "role_sha256", lambda name: "0" * 64)
    with pytest.raises(CC.CalibrationError, match="registry"):
        CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)


def test_prepare_writes_the_copy_once(tmp_path: Path) -> None:
    sealed(tmp_path)
    run = a_source_run(tmp_path, ())
    CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)
    with pytest.raises(CC.CalibrationError, match="exists"):
        CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)


# ------------------------------------------------------------------------------------ compare
def prepared(tmp_path: Path) -> Path:
    sealed(tmp_path)
    run = a_source_run(tmp_path, ())
    CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)
    return tmp_path / "calibration" / "cal-fact-1"


def fresh(out: Path, batch: str, site: str, text: str, **kwargs: Any) -> None:
    kwargs.setdefault("model", OH.SONNET_MODEL)
    kwargs.setdefault("answered_by", f"fact_checker:{batch}")
    put_answer(out, batch, site, text, **kwargs)


def test_compare_counts_agreement_per_judged_unit(tmp_path: Path) -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "KEEP"))  # sentence 2 differs
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))

    report = CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")

    assert report["units"] == 6  # two sentences and the coherent flag, twice
    assert report["agreed"] == 5
    assert report["agreement"] == round(5 / 6, 4)
    assert [d["unit"] for d in report["disagreements"]] == ["sentence-2"]
    assert report["disagreements"][0]["fresh_sources"] == [
        "https://example.org/1",
        "https://example.org/2",
    ]
    assert report["unanswered"] == []
    stored = json.loads((out / "COMPARISON.json").read_text(encoding="utf-8"))
    assert stored == report


def test_compare_counts_a_missing_fresh_answer_as_unanswered(tmp_path: Path) -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"))

    report = CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")

    assert report["unanswered"] == [SITE_B]


def test_compare_refuses_a_fresh_answer_of_the_wrong_model(tmp_path: Path) -> None:
    """Calibrating `fact_checker` (Sonnet) with an Opus answer would measure another model."""
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"), model=OH.OPUS_MODEL)
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    with pytest.raises(RO.RoleError, match="fact_checker"):
        CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")
    assert not (out / "COMPARISON.json").exists()


def test_compare_refuses_a_fresh_answer_recorded_under_another_role(tmp_path: Path) -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"), answered_by="card_writer:x")
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    with pytest.raises(CC.CalibrationError, match="card_writer"):
        CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")


def test_compare_needs_the_prepared_copy(tmp_path: Path) -> None:
    sealed(tmp_path)
    with pytest.raises(CC.CalibrationError, match="not prepared"):
        CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")


def test_compare_is_written_once(tmp_path: Path) -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"))
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")
    with pytest.raises(CC.CalibrationError, match="exists"):
        CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")


# ------------------------------------------------------------------------------------ verdict
def compared(tmp_path: Path, second: str = "KEEP") -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", second))
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")


def test_verdict_passes_at_the_sealed_threshold_with_no_false_source(tmp_path: Path) -> None:
    compared(tmp_path, second="DROP")  # full agreement

    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )

    assert result["passed"] is True and result["tier_move"] is None
    assert result["agreement"] == 1.0 and result["threshold"] == 0.9
    assert result["false_sources"] == 0
    stored = tmp_path / "calibration" / CC.VERDICTS_DIR / "cal-fact-1.json"
    assert json.loads(stored.read_text(encoding="utf-8")) == result


def test_verdict_fails_below_the_sealed_threshold_and_moves_the_role_up_one_tier(
    tmp_path: Path,
) -> None:
    compared(tmp_path, second="KEEP")  # 5 of 6 = 0.8333 < 0.9

    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )

    assert result["passed"] is False
    assert result["tier_move"] == {
        "role": "fact_checker",
        "from": "claude-sonnet-5-5",
        "to": "claude-opus-5-5",
        "calibration_id": "cal-fact-1",
        "reason": result["tier_move"]["reason"],
    }
    assert "0.8333" in result["tier_move"]["reason"] and "0.9" in result["tier_move"]["reason"]


def test_one_false_source_fails_a_calibration_that_agrees_everywhere(tmp_path: Path) -> None:
    compared(tmp_path, second="DROP")
    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=1, now=lambda: NOW
    )
    assert result["passed"] is False
    assert "false source" in result["tier_move"]["reason"]


def test_an_unanswered_question_fails_the_calibration(tmp_path: Path) -> None:
    out = prepared(tmp_path)
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"))
    CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")

    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )

    assert result["passed"] is False and result["unanswered"] == [SITE_B]


def test_a_failing_opus_role_has_no_tier_to_move_to_and_is_held(tmp_path: Path) -> None:
    sealed(tmp_path, role="adversarial")
    run = a_source_run(tmp_path, ())
    CC.prepare(tmp_path / "calibration", calibration_id="cal-fact-1", run=run)
    out = tmp_path / "calibration" / "cal-fact-1"
    by = "adversarial:wc"
    fresh(
        out,
        "wc-0001",
        SITE_A,
        check_answer(SITE_A, "KEEP", "KEEP"),
        model=OH.OPUS_MODEL,
        answered_by=by,
    )
    fresh(
        out,
        "wc-0002",
        SITE_B,
        check_answer(SITE_B, "DROP", "DROP"),
        model=OH.OPUS_MODEL,
        answered_by=by,
    )
    CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")

    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )

    assert result["passed"] is False
    assert result["tier_move"] is None
    assert result["held"] == "no higher tier than claude-opus-5-5: the owner decides"


def test_verdict_is_written_once(tmp_path: Path) -> None:
    compared(tmp_path, second="DROP")
    CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )
    with pytest.raises(CC.CalibrationError, match="exists"):
        CC.verdict(
            tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
        )


def test_verdict_needs_the_comparison_and_a_counted_false_source_figure(tmp_path: Path) -> None:
    prepared(tmp_path)
    with pytest.raises(CC.CalibrationError, match="not compared"):
        CC.verdict(
            tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
        )
    compared_dir = tmp_path / "calibration" / "cal-fact-1"
    fresh(compared_dir, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"))
    fresh(compared_dir, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    CC.compare(tmp_path / "calibration", calibration_id="cal-fact-1")
    for bad in (-1, True, None, 1.5):
        with pytest.raises(CC.CalibrationError, match="false_sources"):
            CC.verdict(
                tmp_path / "calibration",
                calibration_id="cal-fact-1",
                false_sources=bad,  # type: ignore[arg-type]
                now=lambda: NOW,
            )


def test_verdict_refuses_a_role_that_changed_after_the_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared(tmp_path, second="DROP")
    monkeypatch.setattr(RO, "role_sha256", lambda name: "0" * 64)
    with pytest.raises(CC.CalibrationError, match="registry"):
        CC.verdict(
            tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
        )


# ----------------------------------------------------------------------------------------- CLI
def test_the_cli_runs_the_four_steps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    handoff = an_answered_handoff(tmp_path)
    run = a_source_run(tmp_path, ())
    root = str(tmp_path / "calibration")

    assert (
        CC.main(
            ["seal", "--root", root, "--id", "cal-fact-1", "--role", "fact_checker",
             "--handoff", str(handoff), "--batches", "wc-0001", "wc-0002", "--threshold", "0.9"]
        )
        == 0
    )  # fmt: skip
    assert json.loads(capsys.readouterr().out)["role"] == "fact_checker"

    assert CC.main(["prepare", "--root", root, "--id", "cal-fact-1", "--run", str(run)]) == 0
    assert json.loads(capsys.readouterr().out)["questions"] == 2

    out = tmp_path / "calibration" / "cal-fact-1"
    fresh(out, "wc-0001", SITE_A, check_answer(SITE_A, "KEEP", "DROP"))
    fresh(out, "wc-0002", SITE_B, check_answer(SITE_B, "KEEP", "KEEP"))
    assert CC.main(["compare", "--root", root, "--id", "cal-fact-1"]) == 0
    assert json.loads(capsys.readouterr().out)["agreement"] == 1.0

    assert CC.main(["verdict", "--root", root, "--id", "cal-fact-1", "--false-sources", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_the_cli_exits_one_when_the_calibration_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    compared(tmp_path, second="KEEP")
    code = CC.main(
        ["verdict", "--root", str(tmp_path / "calibration"), "--id", "cal-fact-1",
         "--false-sources", "0"]
    )  # fmt: skip
    assert code == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False


def test_the_cli_exits_two_on_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = CC.main(["compare", "--root", str(tmp_path / "calibration"), "--id", "nope"])
    assert code == 2
    assert "REFUSED" in capsys.readouterr().err


def test_a_condition_the_lane_named_in_its_comparison_fails_the_calibration(tmp_path: Path) -> None:
    """`lane_failures` is how a lane adds a condition of its own (lane WC: a known error the role
    missed): the agreement can be complete and the calibration still fails, with the lane's words."""
    compared(tmp_path, second="DROP")  # full agreement
    comparison = tmp_path / "calibration" / "cal-fact-1" / CC.COMPARISON_FILE
    report = json.loads(comparison.read_text(encoding="utf-8"))
    comparison.write_text(
        json.dumps({**report, "lane_failures": ["known error s/sentence-2 missed"]}),
        encoding="utf-8",
    )
    result = CC.verdict(
        tmp_path / "calibration", calibration_id="cal-fact-1", false_sources=0, now=lambda: NOW
    )
    assert result["passed"] is False and result["agreement"] == 1.0
    assert "known error s/sentence-2 missed" in result["tier_move"]["reason"]


def test_prepare_registers_the_calibration_run_with_the_register_it_is_given(
    tmp_path: Path,
) -> None:
    sealed(tmp_path)
    run = a_source_run(tmp_path, ("wc-0001", "wc-0002"))
    seen: list[tuple[Path, ...]] = []

    def register(source_run: Path, handoff: Path, out: Path, batches: Any) -> Path:
        seen.append((source_run, handoff, out))
        return tmp_path / "registered"

    report = CC.prepare(
        tmp_path / "calibration", calibration_id="cal-fact-1", run=run, register=register
    )
    assert report["calibration_run"] == str(tmp_path / "registered")
    assert seen == [(run, tmp_path / "handoff", tmp_path / "calibration" / "cal-fact-1")]
    assert not (tmp_path / "calibration" / "cal-fact-1-run").exists()  # the default did not run
