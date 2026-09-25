"""Phase 6 acceptance, section 9: the thresholds and the reported numbers (`acceptance/score.py`).

Only a CONFIRMED field is an error; its class is stage 1's unless stage 2 names a lower one. VOID
unless V1-V3 hold, then PASS only with A1-A3. The canary key is read here and nowhere earlier.
Offline; the journal read is faked. The mutation cases are `acceptance judge: ...` in
`scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests" / "remediation"
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from acceptance import judge as J  # noqa: E402
from acceptance import questions as QN  # noqa: E402
from acceptance import score as S  # noqa: E402
from test_acceptance_judge import (  # noqa: E402
    _import,
    answer_all,
    canary,
    make_run,
    s2_answer,
    unverifiable,
    wrong_country,
)


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


# ------------------------------------------------------------------------------ Clopper-Pearson
def test_clopper_pearson_is_the_exact_binomial_interval() -> None:
    """Reference values: scipy.stats.beta.ppf, computed 2026-09-26 (scipy is no project dependency)."""
    for (k, n), (lo, hi) in {
        (0, 60): (0.0, 0.059629),
        (32, 60): (0.399965, 0.663301),
        (3, 60): (0.010432, 0.139243),
        (60, 60): (0.940371, 1.0),
        (7, 643): (0.004388, 0.022301),
    }.items():
        got = S.clopper_pearson(k, n)
        assert got == pytest.approx((lo, hi), abs=2e-6), (k, n)
    with pytest.raises(ValueError):
        S.clopper_pearson(3, 2)


# ------------------------------------------------------------------------------ the outcomes
def _final(verdict: str, via: str = "counted", **answer: Any) -> dict[str, Any]:
    return {"verdict": verdict, "via": via, "answer": answer or None}


def _question(n: int, field: str = "name", value: str = "Temple", site: int | None = None):
    return QN.Question(label=f"q{n:016x}", site_id=_uuid(site if site is not None else n),
                       field=field, value=value, name="Temple", country="Peru",
                       point="1, 2")  # fmt: skip


def test_only_a_confirmed_field_is_an_error_and_stage2_may_only_lower_its_class() -> None:
    q1, q2, q3, q4 = (_question(n) for n in (1, 2, 3, 4))
    s1 = {
        q1.label: _final("WRONG", severity="severe"),
        q2.label: _final("WRONG", severity="severe"),
        q3.label: _final("WRONG", severity="severe"),
        q4.label: _final("UNVERIFIABLE", "exhausted"),
    }
    s2 = {
        q1.label: _final("CONFIRMED", severity=None),
        q2.label: _final("CONFIRMED", severity="cosmetic"),
        q3.label: _final("UNDECIDED"),
    }
    s3 = {q3.label: _final("REFUTED")}
    got = {o.label: o for o in S.outcomes([q1, q2, q3, q4], s1, s2, s3)}
    assert (got[q1.label].confirmed, got[q1.label].severity) == (True, "severe")
    assert (got[q2.label].confirmed, got[q2.label].severity) == (True, "cosmetic")
    assert got[q3.label].confirmed is False and got[q3.label].stage3 == "REFUTED"
    assert got[q4.label].confirmed is False and got[q4.label].stage1 == "UNVERIFIABLE"


def test_an_unfinished_chain_refuses() -> None:
    q1 = _question(1)
    with pytest.raises(S.ScoreError, match="stage 1"):
        S.outcomes([q1], {}, {}, {})
    with pytest.raises(S.ScoreError, match="stage 2"):
        S.outcomes([q1], {q1.label: _final("WRONG", severity="severe")}, {}, {})
    with pytest.raises(S.ScoreError, match="stage 3"):
        S.outcomes([q1], {q1.label: _final("WRONG", severity="severe")},
                   {q1.label: _final("UNDECIDED")}, {})  # fmt: skip
    with pytest.raises(S.ScoreError, match="not a stage-1 WRONG"):
        S.outcomes([q1], {q1.label: _final("CORRECT")}, {q1.label: _final("REFUTED")}, {})


# ------------------------------------------------------------------------------ the thresholds
def _scored(
    confirmed_real: list[tuple[int, str]],
    canaries_confirmed: int = 10,
    deterministic: bool = True,
    journal: list[dict] | None = None,
) -> dict[str, Any]:
    """60 sites with one real name question each; 10 canary country questions on sites 1-10."""
    outcomes = []
    for n in range(1, 61):
        hit = dict(confirmed_real).get(n)
        outcomes.append(S.Outcome(label=f"r{n}", site_id=_uuid(n), field="name", value="x",
                                  stage1="WRONG" if hit else "CORRECT", stage1_via="counted",
                                  stage2="CONFIRMED" if hit else None, stage3=None,
                                  confirmed=bool(hit), severity=hit))  # fmt: skip
    keys = []
    for n in range(1, 11):
        yes = n <= canaries_confirmed
        outcomes.append(S.Outcome(label=f"c{n}", site_id=_uuid(n), field="country",
                                  value="Japan", stage1="WRONG", stage1_via="counted",
                                  stage2="CONFIRMED" if yes else "REFUTED", stage3=None,
                                  confirmed=yes, severity="severe" if yes else None))  # fmt: skip
        keys.append(f"c{n}")
    return S.score(
        outcomes,
        canary_labels=set(keys),
        deterministic={"all_hold": deterministic},
        journal_after_draw=journal or [],
        sites=60,
    )


def test_a_clean_valid_run_passes() -> None:
    result = _scored([])
    assert result["outcome"] == "PASS"
    assert result["validity"]["valid"] is True
    assert result["reported"]["canaries"]["stage2_recall"] == {"k": 10, "n": 10}


def test_one_confirmed_severe_error_fails_a1() -> None:
    result = _scored([(12, "severe")])
    assert result["outcome"] == "FAIL" and result["acceptance"]["A1"]["holds"] is False


def test_four_sites_with_an_error_fail_a2_and_three_do_not() -> None:
    three = _scored([(12, "moderate"), (13, "cosmetic"), (14, "moderate")])
    assert three["outcome"] == "PASS" and three["acceptance"]["A2"]["sites"] == 3
    four = _scored([(12, "moderate"), (13, "cosmetic"), (14, "moderate"), (15, "moderate")])
    assert four["outcome"] == "FAIL" and four["acceptance"]["A2"]["holds"] is False


def test_a_canary_error_never_counts_against_the_database() -> None:
    result = _scored([])
    assert result["acceptance"]["A1"]["severe"] == 0 and result["acceptance"]["A2"]["sites"] == 0


def test_a_failed_deterministic_check_fails_a3() -> None:
    assert _scored([], deterministic=False)["outcome"] == "FAIL"


def test_nine_canaries_are_valid_and_eight_void_the_run() -> None:
    assert _scored([], canaries_confirmed=9)["outcome"] == "PASS"
    void = _scored([(12, "severe")], canaries_confirmed=8)
    assert void["outcome"] == "VOID" and void["validity"]["V2"]["holds"] is False


def test_a_write_on_a_drawn_site_after_the_draw_voids_the_run() -> None:
    row = {"id": 73181, "site_id_ref": _uuid(3), "run_stamp": "x"}
    void = _scored([], journal=[row])
    assert void["outcome"] == "VOID" and void["validity"]["V3"]["rows"] == [row]


def test_the_reported_numbers() -> None:
    result = _scored([(12, "moderate"), (13, "severe")])
    reported = result["reported"]
    assert reported["confirmed_errors"] == {"name": {"moderate": 1, "severe": 1}}
    assert reported["site_error_rate"]["k"] == 2 and reported["site_error_rate"]["n"] == 60
    assert reported["site_error_rate"]["assessment"]["k"] == 32
    assert reported["unverifiable"]["overall"]["k"] == 0
    assert reported["stage2_refutation"]["all"] == {"refuted": 0, "stage2": 12}
    assert reported["canaries"]["stage1_recall"] == {"k": 10, "n": 10}


def test_the_canary_labels_are_found_by_site_field_and_value() -> None:
    questions = [
        _question(1, "country", "Japan", site=1),
        _question(2, "country", "Peru", site=1),
        _question(3, "coordinates", "56.178882, -1.826215", site=2),
    ]
    key = [
        {"site_id": _uuid(1), "field": "country", "canary_value": "Japan"},
        {"site_id": _uuid(2), "field": "coordinates", "canary_value": "56.178882,-1.826215432"},
    ]
    assert S.canary_labels(questions, key) == {questions[0].label, questions[2].label}
    with pytest.raises(S.ScoreError, match="canary"):
        S.canary_labels(questions[1:], key)


# ------------------------------------------------------------------------------ the whole run
def test_the_result_is_written_once_from_a_finished_run(tmp_path: Path) -> None:
    run = make_run(tmp_path, n_sites=10, canaries=[canary(n) for n in range(1, 11)])
    J.export_stage1(run, tmp_path / "s1")
    japan = {q.label for q in J.read_questions(run).values() if q.value == "Japan"}
    answer_all(tmp_path / "s1", lambda line: wrong_country() if line["label"] in japan
               else unverifiable())  # fmt: skip
    _import(run, "s1")
    with pytest.raises(J.JudgeError, match="DETERMINISTIC"):
        J.result(run, read_journal=lambda mark, ids: [])
    (run / "DETERMINISTIC.json").write_text(json.dumps({"all_hold": True}), encoding="utf-8")
    with pytest.raises(J.JudgeError, match="stage 2"):
        J.result(run, read_journal=lambda mark, ids: [])
    J.export_stage2(run, tmp_path / "s2")
    answer_all(tmp_path / "s2", lambda line: s2_answer())
    _import(run, "s2")
    seen: list[tuple[int, list[str]]] = []

    def journal(mark: int, ids: list[str]) -> list[dict]:
        seen.append((mark, ids))
        return []

    result = J.result(run, read_journal=journal)
    assert seen == [(100, sorted(_uuid(n) for n in range(1, 11)))]
    assert result["outcome"] == "PASS"
    assert result["questions"] == {"total": 110, "real": 100, "canary": 10}
    assert result["validity"]["V2"]["confirmed"] == 10
    stored = json.loads((run / "RESULT.json").read_text(encoding="utf-8"))
    assert stored == result
    assert "PASS" in (run / "RESULT.md").read_text(encoding="utf-8")
    for name in ("QUESTIONS.jsonl", "STAGE1.jsonl", "STAGE2.jsonl", "CANARIES.jsonl"):
        assert name in json.dumps(result["files"])
    with pytest.raises(J.JudgeError, match="once"):
        J.result(run, read_journal=journal)
