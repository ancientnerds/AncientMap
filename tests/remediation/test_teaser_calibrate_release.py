"""The release of a held verdict of the card lane (`teaser/calibrate.py release`, `standing`).

A role that fails at the top tier has no tier to move to: `evaluate` writes `held` and the owner
decides. The orchestrator's decision (D8, 2026-10-09) is a release - a record bound to the verdict,
the seal, the role's registry entry and the evidence - that `standing` counts like a pass.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import calibrate_claude as CC  # noqa: E402
import roles as RO  # noqa: E402
from teaser import calibrate as K  # noqa: E402
from teaser import run as R  # noqa: E402

from tests.remediation.test_teaser_calibrate import sealed_dir  # noqa: E402
from tests.remediation.test_teaser_shorts_run import MP, make_run  # noqa: E402

NOW = "2026-10-09T12:00:00Z"
HELD = "no higher tier than claude-opus-5-5: the owner decides"
#: A failed verdict of a Sonnet role carries this (no registered role is on a lower tier now).
A_MOVE = {
    "role": "fact_checker",
    "from": "claude-sonnet-5-5",
    "to": "claude-opus-5-5",
    "calibration_id": "teaser-test",
    "reason": "failed: x",
}


def verdict_file(run_dir: Path, role: str = "hook_rater", **over: Any) -> Path:
    """The verdict `K.evaluate` writes for a role that failed at the top tier."""
    _, digest = K.integrity(run_dir)
    body: dict[str, Any] = {
        "calibration_id": run_dir.name,
        "role": role,
        "model": RO.role(role).model,
        "effort": RO.role(role).effort,
        "sets": {"hook_pairs": {"passed": False, "ordered_right": 0.9161}},
        "passed": False,
        "tier_move": None,
        "held": HELD,
        "thresholds_sha256": digest,
        "decided_at": NOW,
    }
    body.update(over)
    path = run_dir / K.VERDICT_FILE.format(role=role)
    path.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    return path


def evidence(tmp_path: Path, name: str = "hook-rater.md", text: str = "within one\n") -> Path:
    path = tmp_path / "evidence" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def release(run_dir: Path, tmp_path: Path, role: str = "hook_rater", **over: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "decided_by": "orchestrator (D8)",
        "reason": "it only orders variants that each passed the fact check",
        "evidence": [evidence(tmp_path)],
        "now": lambda: NOW,
    }
    kwargs.update(over)
    return K.release_role(run_dir, role, **kwargs)


def test_a_release_binds_the_verdict_the_thresholds_the_role_and_the_evidence(
    tmp_path: Path,
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict = verdict_file(run_dir)
    proof = evidence(tmp_path)

    record = release(run_dir, tmp_path, evidence=[verdict, proof])

    stored = run_dir / K.RELEASE_FILE.format(role="hook_rater")
    assert json.loads(stored.read_text(encoding="utf-8")) == record
    assert record["calibration_id"] == run_dir.name and record["role"] == "hook_rater"
    assert record["verdict_sha256"] == hashlib.sha256(verdict.read_bytes()).hexdigest()
    assert record["thresholds_sha256"] == K.integrity(run_dir)[1]
    assert record["role_sha256"] == RO.role_sha256("hook_rater")
    assert record["decided_by"] == "orchestrator (D8)" and record["decided_at"] == NOW
    assert [e["path"] for e in record["evidence"]] == [str(verdict.resolve()), str(proof.resolve())]
    assert record["evidence"][1]["sha256"] == hashlib.sha256(proof.read_bytes()).hexdigest()


def test_a_release_is_written_once(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    release(run_dir, tmp_path)
    with pytest.raises(K.CalibrationError, match="exists"):
        release(run_dir, tmp_path, reason="another")


def test_a_pass_is_not_released(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, passed=True, held=None)
    with pytest.raises(K.CalibrationError, match="passed"):
        release(run_dir, tmp_path)


def test_a_verdict_with_a_tier_move_is_moved_not_released(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    move = A_MOVE
    verdict_file(run_dir, "fact_checker", tier_move=move, held=None)
    with pytest.raises(K.CalibrationError, match="tier move"):
        release(run_dir, tmp_path, "fact_checker")


def test_a_failed_verdict_that_is_not_held_is_not_released(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, held=None)
    with pytest.raises(K.CalibrationError, match="held"):
        release(run_dir, tmp_path)


def test_a_missing_verdict_is_not_released(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    with pytest.raises(K.CalibrationError, match="no verdict"):
        release(run_dir, tmp_path)


def test_an_unsealed_directory_is_not_released(tmp_path: Path) -> None:
    with pytest.raises(K.CalibrationError, match="is not sealed"):
        release(tmp_path / "nowhere", tmp_path)


@pytest.mark.parametrize("field", ["decided_by", "reason"])
def test_a_release_names_who_decided_and_why(tmp_path: Path, field: str) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    with pytest.raises(K.CalibrationError, match=field.replace("_", " ")):
        release(run_dir, tmp_path, **{field: "  "})
    assert not (run_dir / K.RELEASE_FILE.format(role="hook_rater")).exists()


def test_a_release_needs_evidence_that_exists_once_each(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    with pytest.raises(K.CalibrationError, match="evidence"):
        release(run_dir, tmp_path, evidence=[])
    with pytest.raises(K.CalibrationError, match="is not a file"):
        release(run_dir, tmp_path, evidence=[tmp_path / "nowhere.md"])
    one = evidence(tmp_path)
    with pytest.raises(K.CalibrationError, match="twice"):
        release(run_dir, tmp_path, evidence=[one, one])


def test_a_verdict_of_another_role_than_the_file_names_is_not_released(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    path = verdict_file(run_dir)
    body = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**body, "role": "adversarial"}), encoding="utf-8")
    with pytest.raises(K.CalibrationError, match="adversarial"):
        release(run_dir, tmp_path)


def test_a_verdict_that_does_not_rest_on_the_sealed_thresholds_is_not_released(
    tmp_path: Path,
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, thresholds_sha256="0" * 64)
    with pytest.raises(K.CalibrationError, match="thresholds"):
        release(run_dir, tmp_path)


def test_a_role_that_changed_after_the_seal_is_not_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    monkeypatch.setattr(RO, "role_sha256", lambda name: "moved")
    with pytest.raises(K.CalibrationError, match="registry entry of role hook_rater"):
        release(run_dir, tmp_path)


# ------------------------------------------------------------------------------ the standing
def test_a_passed_verdict_stands_as_passed(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, passed=True, held=None)
    assert K.standing(run_dir, "hook_rater") == {
        "role": "hook_rater",
        "calibration_id": run_dir.name,
        "standing": "passed",
    }


def test_a_released_verdict_stands_as_released_and_names_who_decided(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    release(run_dir, tmp_path)
    assert K.standing(run_dir, "hook_rater") == {
        "role": "hook_rater",
        "calibration_id": run_dir.name,
        "standing": "released",
        "decided_by": "orchestrator (D8)",
    }


def test_a_held_verdict_without_its_release_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    with pytest.raises(K.CalibrationError, match="hook_rater.*no passing verdict and no release"):
        K.standing(run_dir, "hook_rater")


def test_a_failed_verdict_with_a_tier_move_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    move = A_MOVE
    verdict_file(run_dir, "fact_checker", tier_move=move, held=None)
    with pytest.raises(K.CalibrationError, match="no passing verdict and no release"):
        K.standing(run_dir, "fact_checker")


def test_a_role_without_a_verdict_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    with pytest.raises(K.CalibrationError, match="no verdict"):
        K.standing(run_dir, "adversarial")


def test_a_role_edited_after_the_seal_does_not_stand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, passed=True, held=None)
    monkeypatch.setattr(RO, "role_sha256", lambda name: "moved")
    with pytest.raises(K.CalibrationError, match="registry entry of role hook_rater"):
        K.standing(run_dir, "hook_rater")


def test_a_verdict_not_resting_on_the_seal_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, passed=True, held=None, thresholds_sha256="0" * 64)
    with pytest.raises(K.CalibrationError, match="thresholds"):
        K.standing(run_dir, "hook_rater")


@pytest.mark.parametrize("what", ["verdict", "thresholds", "evidence", "gone"])
def test_a_release_whose_binding_changed_is_refused_by_name(tmp_path: Path, what: str) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict = verdict_file(run_dir)
    proof = evidence(tmp_path)
    release(run_dir, tmp_path, evidence=[proof])
    if what == "verdict":
        body = json.loads(verdict.read_text(encoding="utf-8"))
        verdict.write_text(json.dumps({**body, "decided_at": "later"}), encoding="utf-8")
    elif what == "thresholds":
        path = run_dir / K.RELEASE_FILE.format(role="hook_rater")
        record = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**record, "thresholds_sha256": "0" * 64}), encoding="utf-8")
    elif what == "evidence":
        proof.write_text("changed\n", encoding="utf-8")
    else:
        proof.unlink()
    expected = {"verdict": "verdict", "thresholds": "thresholds", "evidence": "evidence",
                "gone": "evidence"}[what]  # fmt: skip
    with pytest.raises(K.CalibrationError, match=f"release of hook_rater.*{expected}"):
        K.standing(run_dir, "hook_rater")


def forged_release(
    run_dir: Path, tmp_path: Path, file_role: str = "hook_rater", **over: Any
) -> None:
    """A release not made by `K.release_role`: hand-written with the right sha256 of the verdict,
    the thresholds and the role."""
    proof = evidence(tmp_path)
    record: dict[str, Any] = {
        "calibration_id": run_dir.name,
        "role": file_role,
        "verdict_sha256": CC.sha256_file(run_dir / K.VERDICT_FILE.format(role=file_role)),
        "thresholds_sha256": K.integrity(run_dir)[1],
        "role_sha256": RO.role_sha256(file_role),
        "decided_by": "someone",
        "reason": "a hand-written record",
        "evidence": CC.evidence_records([proof]),
        "decided_at": NOW,
    }
    record.update(over)
    (run_dir / K.RELEASE_FILE.format(role=file_role)).write_text(
        json.dumps(record), encoding="utf-8"
    )


def test_a_hand_written_release_of_a_held_verdict_stands(tmp_path: Path) -> None:
    """The control of the forged cases below."""
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    forged_release(run_dir, tmp_path)
    assert K.standing(run_dir, "hook_rater")["standing"] == "released"


def test_a_release_beside_a_verdict_with_a_tier_move_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, "fact_checker", tier_move=A_MOVE)
    forged_release(run_dir, tmp_path, "fact_checker")
    with pytest.raises(K.CalibrationError, match="no passing verdict and no release"):
        K.standing(run_dir, "fact_checker")


def test_a_release_beside_a_failed_verdict_that_is_not_held_does_not_stand(
    tmp_path: Path,
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, held=None)
    forged_release(run_dir, tmp_path)
    with pytest.raises(K.CalibrationError, match="no passing verdict and no release"):
        K.standing(run_dir, "hook_rater")


def test_a_release_with_no_evidence_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    forged_release(run_dir, tmp_path, evidence=[])
    with pytest.raises(K.CalibrationError, match="release of hook_rater.*no evidence"):
        K.standing(run_dir, "hook_rater")


@pytest.mark.parametrize("field", ["calibration_id", "role"])
def test_a_release_naming_another_calibration_or_role_does_not_stand(
    tmp_path: Path, field: str
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    forged_release(run_dir, tmp_path, **{field: "other"})
    with pytest.raises(K.CalibrationError, match="release of hook_rater.*another calibration"):
        K.standing(run_dir, "hook_rater")


def test_a_release_beside_a_pass_is_not_read(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, passed=True, held=None)
    (run_dir / K.RELEASE_FILE.format(role="hook_rater")).write_text("not json", encoding="utf-8")
    assert K.standing(run_dir, "hook_rater")["standing"] == "passed"


def test_a_released_verdict_has_no_tier_move_to_apply(tmp_path: Path) -> None:
    """`run.py escalate` moves a role that failed with a tier move; a release is no such verdict."""
    run_dir = sealed_dir(tmp_path)
    verdict = verdict_file(run_dir)
    release(run_dir, tmp_path)
    run = make_run(tmp_path, [MP])
    with pytest.raises(R.RunError, match="not a failed calibration of role hook_rater"):
        R.escalate_role(run, "hook_rater", verdict)


# ------------------------------------------------------------------------------ the CLI
def test_the_cli_releases_and_reports_the_standing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    proof = evidence(tmp_path)

    code = K.main(
        ["release", "--run-dir", str(run_dir), "--role", "hook_rater",
         "--decided-by", "orchestrator", "--reason", "within one", "--evidence", str(proof)]
    )  # fmt: skip
    assert code == 0
    assert json.loads(capsys.readouterr().out)["role"] == "hook_rater"

    assert K.main(["standing", "--run-dir", str(run_dir), "--role", "hook_rater"]) == 0
    assert json.loads(capsys.readouterr().out)["standing"] == "released"


def test_the_cli_refuses_a_standing_that_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    assert K.main(["standing", "--run-dir", str(run_dir), "--role", "hook_rater"]) == 2
    assert "REFUSED" in capsys.readouterr().err


# ------------------------------------------------------------------ the release under an owner decision
#: Owner decision D36 moved `fact_checker` back to Sonnet: a verdict that failed on Sonnet with a tier
#: move to Opus (teaser-2026-10-09b) is released under it. The test directory is not one of the
#: calibrations the real move rests on, so the move is applied for it here.
@pytest.fixture
def d36_move_for_the_test_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    move = {**RO._d36_move("fact_checker", "high", "a test"), "evidence": ("teaser-test",)}
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, move))


def moved_verdict(run_dir: Path, role: str = "fact_checker", **over: Any) -> Path:
    over.setdefault("tier_move", {**A_MOVE, "role": role})
    over.setdefault("held", None)
    return verdict_file(run_dir, role, **over)


def owner_release(run_dir: Path, tmp_path: Path, **over: Any) -> dict[str, Any]:
    over.setdefault("owner_decision", "D36")
    return release(run_dir, tmp_path, "fact_checker", **over)


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_an_owner_decision_releases_a_verdict_with_a_tier_move(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)

    record = owner_release(run_dir, tmp_path)

    assert record["owner_decision"] == "D36" and record["role"] == "fact_checker"
    stored = run_dir / K.RELEASE_FILE.format(role="fact_checker")
    assert json.loads(stored.read_text(encoding="utf-8")) == record


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_a_plain_release_carries_no_decision(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir)
    assert "owner_decision" not in release(run_dir, tmp_path)


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_standing_says_released_under_the_owner_decision(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    owner_release(run_dir, tmp_path)

    assert K.standing(run_dir, "fact_checker") == {
        "role": "fact_checker",
        "calibration_id": run_dir.name,
        "standing": "released (owner decision D36)",
        "owner_decision": "D36",
        "decided_by": "orchestrator (D8)",
    }


def test_a_verdict_with_a_tier_move_is_not_released_without_a_decision(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    with pytest.raises(K.CalibrationError, match="tier move"):
        release(run_dir, tmp_path, "fact_checker")


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_an_owner_decision_releases_only_a_verdict_with_a_tier_move(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    verdict_file(run_dir, "fact_checker")  # held, no tier move
    with pytest.raises(K.CalibrationError, match="carries no tier move"):
        owner_release(run_dir, tmp_path)
    run_dir_two = sealed_dir(tmp_path / "two")
    verdict_file(run_dir_two, "fact_checker", passed=True, held=None)
    with pytest.raises(K.CalibrationError, match="passed"):
        owner_release(run_dir_two, tmp_path)


def test_an_owner_decision_the_registry_does_not_hold_releases_nothing(tmp_path: Path) -> None:
    """The real D36 moves rest on the 2026-10-09 calibrations, not on this directory."""
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    with pytest.raises(K.CalibrationError, match="does not rest on teaser-test"):
        owner_release(run_dir, tmp_path)
    with pytest.raises(K.CalibrationError, match="names decision D37"):
        owner_release(run_dir, tmp_path, owner_decision="D37")
    assert not (run_dir / K.RELEASE_FILE.format(role="fact_checker")).exists()


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_an_owner_decision_releases_only_the_model_the_owner_kept(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir, model="claude-opus-5-5")
    with pytest.raises(
        K.CalibrationError, match="registered to claude-sonnet-5-5, not claude-opus"
    ):
        owner_release(run_dir, tmp_path)


@pytest.mark.usefixtures("d36_move_for_the_test_directory")
def test_a_forged_owner_release_is_checked_again_when_the_verdict_stands(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    forged_release(run_dir, tmp_path, "fact_checker", owner_decision="D36")
    assert K.standing(run_dir, "fact_checker")["standing"] == "released (owner decision D36)"

    forged_release(run_dir, tmp_path, "fact_checker", owner_decision="D37")
    with pytest.raises(K.CalibrationError, match="release of fact_checker.*names decision D37"):
        K.standing(run_dir, "fact_checker")


def test_a_release_without_a_decision_beside_a_tier_move_does_not_stand(tmp_path: Path) -> None:
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    forged_release(run_dir, tmp_path, "fact_checker")
    with pytest.raises(K.CalibrationError, match="no passing verdict and no release"):
        K.standing(run_dir, "fact_checker")


def test_the_cli_releases_under_an_owner_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    move = {**RO._d36_move("fact_checker", "high", "a test"), "evidence": ("teaser-test",)}
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, move))
    run_dir = sealed_dir(tmp_path)
    moved_verdict(run_dir)
    proof = evidence(tmp_path)
    code = K.main(
        ["release", "--run-dir", str(run_dir), "--role", "fact_checker", "--decided-by", "me",
         "--reason", "no gain on Opus", "--evidence", str(proof), "--owner-decision", "D36"]
    )  # fmt: skip
    assert code == 0 and json.loads(capsys.readouterr().out)["owner_decision"] == "D36"
    assert K.main(["standing", "--run-dir", str(run_dir), "--role", "fact_checker"]) == 0
    assert "released (owner decision D36)" in capsys.readouterr().out
