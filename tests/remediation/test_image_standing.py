"""How an image role comes to stand (`image_roles/standing.py`): the gold's audit trail (D127), the
re-score of existing answers (D128) and the release of a held verdict (D125, D126).

Offline: the cases and answers are invented, the interval is a stub.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from image_roles import calibrate as CAL  # noqa: E402
from image_roles import clean_gold as CG  # noqa: E402
from image_roles import run as CLI  # noqa: E402
from image_roles import standing as STD  # noqa: E402
from served_image import state as ST  # noqa: E402

#: Proven on the role registry as it stood until owner decision D153 (2026-11-10) put every role on
#: Fable: a tier move, the hold at the top tier, a release, a candidate trial and a stamp refused
#: between two roles' models all need roles on different tiers, and no calibration is run on Fable
#: (D154). `conftest.registry_until_d153` rebuilds that registry from the applied moves; what D153
#: and D154 changed is tested on the registry as it is (`test_roles_fable.py`).
pytestmark = pytest.mark.usefixtures("registry_until_d153")

SEALED = "2026-11-06T01:00:00Z"
FIXED = "2026-11-06T03:00:00Z"
ANSWERED = "2026-11-06T04:00:00+00:00"
LATER = "2026-11-07T09:00:00Z"


def cp(k: int, n: int) -> tuple[float, float]:
    return (0.0, 1.0)


def _case(cid: str, truth: str) -> dict[str, Any]:
    return {"case_id": cid, "role": "adversarial", "group": "museum", "site": {"site_id": cid},
            "file": f"{cid}.webp", "path": f"/x/{cid}.webp", "truth": truth}  # fmt: skip


def _answer(cid: str, verdict: str) -> dict[str, Any]:
    return {"answered_at": ANSWERED, "batch_id": "rck-01-001", "label": cid, "verdict": verdict,
            "meta": {"site_id": cid, "file": f"{cid}.webp", "round": 1}}  # fmt: skip


def _directory(tmp_path: Path, answers: dict[str, str]) -> Path:
    """A sealed clean-gold directory: 20 re-check cases, half depicts, the answers recorded."""
    d = tmp_path / "image-roles-v3"
    CG.seal(d, CG.DEPICTS_KIND, now=lambda: SEALED)
    cases = [_case(f"rck-{i:02d}", "depicts" if i < 10 else "not_depicts") for i in range(20)]
    CAL.fix_gold(d, cases, now=lambda: FIXED)
    rows = [
        _answer(c["case_id"], answers.get(c["case_id"], "depicts" if c["truth"] == "depicts"
                else "other_site"))
        for c in cases
    ]  # fmt: skip
    (d / CAL.ROLE_SPECS["adversarial"].result_file).write_text(
        ST.jsonl_text(rows), encoding="utf-8"
    )
    return d


def _held_verdict(d: Path, **extra: Any) -> Path:
    """The verdict `clean_gold.evaluate` writes for a failure on Opus."""
    verdict = {"role": "image_adversarial", "slot": "adversarial", "model": "claude-opus-5-5",
               "passed": False, "failures": ["agreement 0.9 is below 0.95"], "tier_move": None,
               "held": "no higher tier than claude-opus-5-5: the owner decides", **extra}  # fmt: skip
    path = d / CAL.VERDICTS_DIR / "adversarial.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ST.json_text(verdict), encoding="utf-8")
    return path


def _evidence(tmp_path: Path) -> Path:
    path = tmp_path / "evidence.md"
    path.write_text("the owner's answer D125\n", encoding="utf-8")
    return path


class TestTheAuditTrail:
    def test_a_correction_is_a_line_of_the_trail_and_the_gold_stays_sealed(
        self, tmp_path: Path
    ) -> None:
        d = _directory(tmp_path, {})
        before = (d / CAL.GOLD_FILE).read_text(encoding="utf-8")
        row = STD.correct(d, case_id="rck-12", truth="depicts", decision="D127",
                          reason="an architectural part of the site", now=lambda: LATER)  # fmt: skip
        assert (row["from"], row["to"], row["decision"]) == ("not_depicts", "depicts", "D127")
        assert (d / CAL.GOLD_FILE).read_text(encoding="utf-8") == before
        cases, _ = STD.corrected_gold(d)
        assert next(c for c in cases if c["case_id"] == "rck-12")["truth"] == "depicts"
        CAL.fixed_gold(d)  # the sealed gold still verifies

    def test_a_case_is_corrected_once_and_only_to_another_truth(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        with pytest.raises(STD.StandingError, match="nothing to correct"):
            STD.correct(d, case_id="rck-01", truth="depicts", decision="D127", reason="r")
        with pytest.raises(STD.StandingError, match="not a case"):
            STD.correct(d, case_id="rck-99", truth="depicts", decision="D127", reason="r")
        with pytest.raises(STD.StandingError, match="decision and its reason"):
            STD.correct(d, case_id="rck-12", truth="depicts", decision="D127", reason=" ")
        STD.correct(d, case_id="rck-12", truth="depicts", decision="D127", reason="r")
        with pytest.raises(STD.StandingError, match="corrected once"):
            STD.correct(d, case_id="rck-12", truth="not_depicts", decision="D127", reason="r")

    def test_a_trail_made_on_another_gold_is_refused(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        STD.correct(d, case_id="rck-12", truth="depicts", decision="D127", reason="r")
        text = (d / STD.GOLD_AUDIT).read_text(encoding="utf-8")
        (d / STD.GOLD_AUDIT).write_text(text.replace(STD._gold_sha(d), "0" * 64), encoding="utf-8")
        with pytest.raises(STD.StandingError, match="another gold"):
            STD.corrected_gold(d)


class TestTheRescore:
    def test_the_existing_answers_are_measured_against_the_corrected_gold(
        self, tmp_path: Path
    ) -> None:
        # the role kept two non-depicts cases; the owner's rule makes one of them depicts
        d = _directory(tmp_path, {"rck-12": "depicts", "rck-13": "depicts"})
        STD.correct(d, case_id="rck-12", truth="depicts", decision="D127", reason="r")
        verdict = STD.rescore(d, "adversarial", decision="D127", now=lambda: LATER, cp=cp)
        assert verdict["metrics"]["agreement"]["k"] == 19
        assert verdict["metrics"]["confirmed_false"] == ["rck-13"]
        assert verdict["corrections"] == ["rck-12"] and verdict["new_answers"] == 0
        assert verdict["passed"] is True
        assert (d / CAL.VERDICTS_DIR / "adversarial.D127.json").is_file()
        with pytest.raises(ST.StateError, match="written once"):
            STD.rescore(d, "adversarial", decision="D127", now=lambda: LATER, cp=cp)

    def test_a_failure_on_opus_is_held_for_the_owner(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {f"rck-{i}": "depicts" for i in (12, 13, 14)})
        STD.correct(d, case_id="rck-02", truth="not_depicts", decision="D127", reason="r")
        verdict = STD.rescore(d, "adversarial", decision="D127", cp=cp)
        assert verdict["passed"] is False and verdict["tier_move"] is None
        assert "the owner decides" in verdict["held"]

    def test_no_rescore_without_a_correction_of_the_decision(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        with pytest.raises(STD.StandingError, match="no correction of D127"):
            STD.rescore(d, "adversarial", decision="D127", cp=cp)


class TestTheRelease:
    def test_a_held_verdict_is_released_and_then_stands(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        verdict = _held_verdict(d)
        with pytest.raises(STD.StandingError, match="does not stand"):
            STD.standing(d, "adversarial")
        record = STD.release(d, "adversarial", verdict=verdict, decided_by="owner (D128)",
                             reason="r", evidence=[_evidence(tmp_path)], now=lambda: LATER)  # fmt: skip
        assert record["verdict_sha256"] == ST.file_sha256(verdict)
        assert STD.standing(d, "adversarial")["standing"] == "released"
        with pytest.raises(ST.StateError, match="written once"):
            STD.release(d, "adversarial", verdict=verdict, decided_by="owner", reason="r",
                        evidence=[_evidence(tmp_path)])  # fmt: skip

    @pytest.mark.parametrize(
        ("extra", "message"),
        [
            ({"passed": True}, "nothing to release"),
            ({"tier_move": {"to": "x"}}, "tier move"),
            ({"held": None}, "not held"),
        ],
    )
    def test_only_a_held_failure_is_released(
        self, tmp_path: Path, extra: dict[str, Any], message: str
    ) -> None:
        d = _directory(tmp_path, {})
        verdict = _held_verdict(d, **extra)
        with pytest.raises(STD.StandingError, match=message):
            STD.release(d, "adversarial", verdict=verdict, decided_by="owner", reason="r",
                        evidence=[_evidence(tmp_path)])  # fmt: skip

    def test_a_release_without_who_or_why_is_refused(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        verdict = _held_verdict(d)
        with pytest.raises(STD.StandingError, match="decided by is empty"):
            STD.release(d, "adversarial", verdict=verdict, decided_by=" ", reason="r",
                        evidence=[_evidence(tmp_path)])  # fmt: skip
        with pytest.raises(STD.StandingError, match="reason is empty"):
            STD.release(d, "adversarial", verdict=verdict, decided_by="owner", reason="",
                        evidence=[_evidence(tmp_path)])  # fmt: skip

    def test_a_release_falls_when_its_verdict_or_evidence_moves(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        verdict = _held_verdict(d)
        evidence = _evidence(tmp_path)
        STD.release(d, "adversarial", verdict=verdict, decided_by="owner", reason="r",
                    evidence=[evidence])  # fmt: skip
        evidence.write_text("changed\n", encoding="utf-8")
        with pytest.raises(STD.StandingError, match="evidence"):
            STD.standing(d, "adversarial")
        evidence.write_text("the owner's answer D125\n", encoding="utf-8")
        verdict.write_text(verdict.read_text(encoding="utf-8") + " \n", encoding="utf-8")
        with pytest.raises(STD.StandingError, match="the verdict changed"):
            STD.standing(d, "adversarial")

    def test_a_correction_after_the_release_leaves_it_standing(self, tmp_path: Path) -> None:
        """A correction does not move the sealed gold: the release still stands on it."""
        d = _directory(tmp_path, {})
        verdict = _held_verdict(d)
        STD.release(d, "adversarial", verdict=verdict, decided_by="owner", reason="r",
                    evidence=[_evidence(tmp_path)])  # fmt: skip
        STD.correct(d, case_id="rck-12", truth="depicts", decision="D127", reason="r")
        assert STD.standing(d, "adversarial")["standing"] == "released"

    def test_a_passing_verdict_stands_without_a_release(self, tmp_path: Path) -> None:
        d = _directory(tmp_path, {})
        _held_verdict(d, passed=True, held=None, failures=[])
        assert STD.standing(d, "adversarial")["standing"] == "passed"


class TestTheGate:
    def test_the_lane_s_export_refuses_a_role_that_does_not_stand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "calibration"
        root.mkdir()
        _directory(root, {})  # image-roles-v3 without a verdict
        monkeypatch.setattr(STD, "calibration_root", lambda: root)
        run = tmp_path / "run"
        run.mkdir()
        code = CLI.main(["recheck-export", "--run-dir", str(run), "--handoff", str(tmp_path / "h")])
        assert code == 1
        assert "the image roles do not stand: adversarial" in capsys.readouterr().err
        assert not (tmp_path / "h").exists()

    def test_require_standing_names_every_slot_that_does_not_stand(self, tmp_path: Path) -> None:
        _directory(tmp_path, {})
        with pytest.raises(STD.StandingError) as caught:
            STD.require_standing(["image_depicts", "adversarial"], tmp_path)
        assert "image_depicts:" in str(caught.value) and "adversarial:" in str(caught.value)
        assert json.loads(json.dumps(STD.STANDING))["adversarial"] == "image-roles-v3"
