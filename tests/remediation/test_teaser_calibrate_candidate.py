"""The candidate-model trial of the card lane's calibration (`teaser/calibrate.py`), owner decision D36.

D36 has the fact checker tried on Haiku: `seal --candidate-role fact_checker --candidate-model M`
calibrates the role with another model WITHOUT changing the registry. The seal records the candidate,
`export`, `agents` and `evaluate` are told it again, the agents record with `--candidate-model`, the
verdict names the model that passed, and no gate accepts it for the registered role until an owner
move has registered the candidate. Also the explicit batch size of an export.
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

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from teaser import calibrate as K  # noqa: E402

from tests.remediation.test_teaser_calibrate import (  # noqa: E402
    ALL_FAIL,
    TINY,
    answer_role,
    fixed_dir,
    sealed_dir,
    wiki_cache,  # noqa: F401 - the autouse fixture: a web role is exported with a cache
)

HAIKU = "claude-haiku-5-5"
TRIAL = {"fact_checker": HAIKU}


def test_a_candidate_seal_records_the_candidate_beside_the_registered_entry(
    tmp_path: Path,
) -> None:
    run_dir = sealed_dir(tmp_path, candidates=TRIAL)
    registry = json.loads((run_dir / K.THRESHOLDS_FILE).read_text(encoding="utf-8"))["registry"]

    entry = registry["fact_checker"]
    assert entry["model"] == HAIKU and entry["candidate"] is True
    assert entry["registered_model"] == "claude-sonnet-5-5"
    assert entry["sha256"] == RO.role_sha256("fact_checker", model=HAIKU)
    assert entry["registered_sha256"] == RO.role_sha256("fact_checker")
    assert entry["effort"] == RO.ROLES["fact_checker"].effort
    # the other roles are sealed as themselves
    assert "candidate" not in registry["web_verifier"]
    assert registry["web_verifier"]["sha256"] == RO.role_sha256("web_verifier")
    assert RO.ROLES["fact_checker"].model == "claude-sonnet-5-5"


def test_a_seal_without_a_trial_is_the_seal_it_always_was(tmp_path: Path) -> None:
    registry = json.loads((sealed_dir(tmp_path) / K.THRESHOLDS_FILE).read_text(encoding="utf-8"))[
        "registry"
    ]
    assert all("candidate" not in entry for entry in registry.values())
    assert set(registry["fact_checker"]) == {"model", "effort", "sha256"}


@pytest.mark.parametrize(
    ("candidates", "message"),
    [
        ({"fact_checker": "claude-sonnet-5-5"}, "is the registered model of fact_checker"),
        ({"fact_checker": "MiniMax-M3.1-Flash-Preview"}, "not a model a role may be registered to"),
        ({"pilot_judge": HAIKU}, "no calibrated role of the table"),
        ({"writer": HAIKU}, "no calibrated role of the table"),
    ],
)
def test_a_trial_needs_a_calibrated_role_and_another_registrable_model(
    tmp_path: Path, candidates: dict[str, str], message: str
) -> None:
    with pytest.raises((K.CalibrationError, RO.RoleError), match=message):
        sealed_dir(tmp_path, candidates=candidates)
    assert not (tmp_path / "calibration" / "teaser-test" / K.THRESHOLDS_FILE).exists()


def test_a_trial_role_is_exported_only_with_its_candidate_model(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    with pytest.raises(K.CalibrationError, match="sealed as a trial of claude-haiku-5-5"):
        K.export_role(run_dir, "fact_checker", tmp_path / "h")
    with pytest.raises(
        K.CalibrationError, match=r"sealed as a trial of claude-haiku-5-5.*not claude-opus"
    ):
        K.export_role(run_dir, "fact_checker", tmp_path / "h", candidate_model="claude-opus-5-5")
    assert not (run_dir / K.HANDOFFS_FILE).exists()


def test_a_role_sealed_as_itself_is_not_given_a_candidate(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    with pytest.raises(K.CalibrationError, match="sealed as itself, not as a candidate trial"):
        K.export_role(run_dir, "web_verifier", tmp_path / "h", candidate_model=HAIKU)


def test_the_agents_of_a_trial_are_briefed_with_the_candidate(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    answer_role(run_dir, "fact_checker", ALL_FAIL, candidate_model=HAIKU)

    job = K.agent_jobs(run_dir, "fact_checker", candidate_model=HAIKU)[0]

    assert (job["role"], job["model"]) == ("fact_checker", HAIKU)
    assert f"--model {HAIKU} --candidate-model {HAIKU}" in job["brief"]
    assert f"your model is **{HAIKU}**" in job["brief"]
    with pytest.raises(K.CalibrationError, match="sealed as a trial"):
        K.agent_jobs(run_dir, "fact_checker")


def test_the_agents_of_a_role_that_is_no_trial_are_briefed_as_always(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    K.export_role(run_dir, "web_verifier", tmp_path / "h")
    job = K.agent_jobs(run_dir, "web_verifier")[0]
    assert "--candidate-model" not in job["brief"] and job["model"] == "claude-sonnet-5-5"


def test_a_trial_is_evaluated_on_the_candidates_stamp_and_moves_nobody(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    answer_role(run_dir, "fact_checker", ALL_FAIL, candidate_model=HAIKU)

    verdict = K.evaluate(run_dir, "fact_checker", candidate_model=HAIKU)

    assert verdict["passed"] is False  # a checker that fails every card misses the good ones
    assert verdict["model"] == HAIKU and verdict["candidate_model"] == HAIKU
    assert verdict["registered_model"] == "claude-sonnet-5-5"
    assert verdict["tier_move"] is None and "held" not in verdict


def test_a_trial_refuses_an_answer_of_the_registered_model(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    answer_role(run_dir, "fact_checker", ALL_FAIL, candidate_model=HAIKU, model="claude-sonnet-5-5")
    with pytest.raises(K.CalibrationError, match=f"role fact_checker is sealed to {HAIKU}"):
        K.evaluate(run_dir, "fact_checker", candidate_model=HAIKU)


def test_a_trial_is_evaluated_only_with_its_candidate_model(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path, candidates=TRIAL)
    answer_role(run_dir, "fact_checker", ALL_FAIL, candidate_model=HAIKU)
    with pytest.raises(K.CalibrationError, match="sealed as a trial of claude-haiku-5-5"):
        K.evaluate(run_dir, "fact_checker")
    assert not (run_dir / K.VERDICT_FILE.format(role="fact_checker")).exists()


def a_passed_trial(tmp_path: Path) -> Path:
    """The verdict file of a trial that passed, as `K.evaluate` writes it."""
    run_dir = sealed_dir(tmp_path, candidates=TRIAL)
    _, digest = K.integrity(run_dir)
    body = {
        "calibration_id": run_dir.name,
        "role": "fact_checker",
        "model": HAIKU,
        "effort": "high",
        "candidate_model": HAIKU,
        "registered_model": "claude-sonnet-5-5",
        "sets": {},
        "passed": True,
        "tier_move": None,
        "thresholds_sha256": digest,
        "decided_at": "2026-10-09T12:00:00Z",
    }
    (run_dir / K.VERDICT_FILE.format(role="fact_checker")).write_text(
        json.dumps(body), encoding="utf-8"
    )
    return run_dir


def test_no_gate_accepts_a_trial_for_the_registered_role(tmp_path: Path) -> None:
    run_dir = a_passed_trial(tmp_path)
    with pytest.raises(K.CalibrationError, match="trial of claude-haiku-5-5.*owner move"):
        K.standing(run_dir, "fact_checker")


def test_a_registry_edit_without_an_owner_move_does_not_make_a_trial_stand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = a_passed_trial(tmp_path)
    changed = dict(RO.ROLES)
    changed["fact_checker"] = RO.Role("fact_checker", HAIKU, "high", "wb_check_verify_opus")
    monkeypatch.setattr(RO, "ROLES", changed)
    with pytest.raises(K.CalibrationError, match="owner move"):
        K.standing(run_dir, "fact_checker")


def test_a_trial_stands_once_an_owner_move_registered_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = a_passed_trial(tmp_path)
    changed = dict(RO.ROLES)
    changed["fact_checker"] = RO.Role("fact_checker", HAIKU, "high", "wb_check_verify_opus")
    move = {
        **RO._d36_move("fact_checker", "high", "a test"),
        "from": "claude-sonnet-5-5",
        "to": HAIKU,
    }
    monkeypatch.setattr(RO, "ROLES", changed)
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, move))

    assert K.standing(run_dir, "fact_checker")["standing"] == "passed"


def test_a_registry_that_moved_to_another_model_breaks_the_trial_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = a_passed_trial(tmp_path)
    changed = dict(RO.ROLES)
    changed["fact_checker"] = RO.Role(
        "fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"
    )
    monkeypatch.setattr(RO, "ROLES", changed)
    with pytest.raises(K.CalibrationError, match="registry entry of role fact_checker changed"):
        K.standing(run_dir, "fact_checker")


def test_a_trial_is_never_released(tmp_path: Path) -> None:
    run_dir = a_passed_trial(tmp_path)
    path = run_dir / K.VERDICT_FILE.format(role="fact_checker")
    body = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**body, "passed": False}), encoding="utf-8")
    evidence = tmp_path / "e.md"
    evidence.write_text("x\n", encoding="utf-8")
    with pytest.raises(K.CalibrationError, match="owner move"):
        K.release_role(
            run_dir, "fact_checker", decided_by="x", reason="y", evidence=[evidence],
            owner_decision="D36",
        )  # fmt: skip


def test_the_cli_seals_exports_and_evaluates_a_trial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "calibration" / "teaser-cli"
    assert K.main(
        ["seal", "--run-dir", str(run_dir), "--candidate-role", "fact_checker",
         "--candidate-model", HAIKU]
    ) == 0  # fmt: skip
    sealed_registry = json.loads((run_dir / K.THRESHOLDS_FILE).read_text(encoding="utf-8"))[
        "registry"
    ]
    assert sealed_registry["fact_checker"]["candidate"] is True
    capsys.readouterr()


@pytest.mark.parametrize(
    "args", [["--candidate-role", "fact_checker"], ["--candidate-model", HAIKU]]
)
def test_a_trial_names_its_role_and_its_model_together(
    tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "calibration" / "teaser-cli"
    assert K.main(["seal", "--run-dir", str(run_dir), *args]) == 2
    assert "go together" in capsys.readouterr().err
    assert not (run_dir / K.THRESHOLDS_FILE).exists()


def test_the_table_the_cli_seals_has_no_trial_by_default(tmp_path: Path) -> None:
    run_dir = tmp_path / "calibration" / "teaser-cli"
    assert K.main(["seal", "--run-dir", str(run_dir)]) == 0
    registry = json.loads((run_dir / K.THRESHOLDS_FILE).read_text(encoding="utf-8"))["registry"]
    assert not any("candidate" in entry for entry in registry.values())
    assert set(registry) == {*K.THRESHOLDS["roles"], "pilot_judge"}


# ------------------------------------------------------------------------------ the batch size
def test_a_role_is_exported_at_the_size_named_and_the_export_records_it(tmp_path: Path) -> None:
    run_dir = fixed_dir(tmp_path)
    summary = K.export_role(run_dir, "fact_checker", tmp_path / "h", batch_size=3)
    assert summary["batch_size"] == 3
    batches = K._handoffs(run_dir)["fact_checker"]
    assert batches["batch_size"] == 3 and max(len(k) for k in batches["batches"].values()) <= 3


def test_the_default_sizes_are_fifteen_for_a_text_role_and_eight_for_a_web_role(
    tmp_path: Path,
) -> None:
    assert (K.BATCH_SIZE, K.WEB_BATCH_SIZE) == (15, 8)
    run_dir = fixed_dir(tmp_path)
    assert K.export_role(run_dir, "fact_checker", tmp_path / "a")["batch_size"] == 15
    assert K.export_role(run_dir, "web_verifier", tmp_path / "b")["batch_size"] == 8


def test_the_sealed_table_is_the_one_the_trial_tests_use() -> None:
    assert TINY["roles"].keys() >= {"fact_checker", "web_verifier"}
    assert OH.ANSWER_MODELS[HAIKU]


def test_a_tier_move_that_registered_the_candidate_is_no_owner_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = sealed_dir(tmp_path, candidates={"fact_checker": "claude-opus-5-5"})
    _, digest = K.integrity(run_dir)
    body = {
        "calibration_id": run_dir.name, "role": "fact_checker", "model": "claude-opus-5-5",
        "effort": "high", "candidate_model": "claude-opus-5-5",
        "registered_model": "claude-sonnet-5-5", "sets": {}, "passed": True, "tier_move": None,
        "thresholds_sha256": digest, "decided_at": "2026-10-09T12:00:00Z",
    }  # fmt: skip
    (run_dir / K.VERDICT_FILE.format(role="fact_checker")).write_text(
        json.dumps(body), encoding="utf-8"
    )
    changed = dict(RO.ROLES)
    changed["fact_checker"] = RO.Role(
        "fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"
    )
    tier = {
        "role": "fact_checker", "from": "claude-sonnet-5-5", "to": "claude-opus-5-5",
        "calibration_id": "x", "reason": "failed",
    }  # fmt: skip
    monkeypatch.setattr(RO, "ROLES", changed)
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, tier))
    with pytest.raises(K.CalibrationError, match="owner move has registered the candidate"):
        K.standing(run_dir, "fact_checker")
