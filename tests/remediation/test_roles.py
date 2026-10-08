"""The roles registry (`scripts/remediation/roles.py`), owner decision D6 of 2026-10-08.

Every model judgement of the final repair is made by a role, and a role is one registered model at
one effort. The registry is a constant, the answer stamp always names the real model, and a role
answered by any other model is refused. No test here calls a model or opens a socket.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402

#: D6, role by role: (model id, effort).
D6 = {
    "card_writer": ("claude-opus-5-5", "high"),
    "hook_rater": ("claude-opus-5-5", "medium"),
    "fact_checker": ("claude-sonnet-5-5", "high"),
    "web_verifier": ("claude-sonnet-5-5", "high"),
    "field_researcher": ("claude-sonnet-5-5", "high"),
    "adversarial": ("claude-opus-5-5", "high"),
    "image_prefilter": ("claude-haiku-5-5", "low"),
    "image_depicts": ("claude-sonnet-5-5", "medium"),
    "code_builder": ("claude-sonnet-5-5", "high"),
    "code_review": ("claude-opus-5-5", "high"),
    "pilot_judge": ("claude-opus-5-5", "xhigh"),
    "operator": ("claude-haiku-5-5", "low"),
}


def test_the_registry_is_exactly_the_twelve_roles_of_decision_d6() -> None:
    assert {name: (r.model, r.effort) for name, r in RO.ROLES.items()} == D6
    assert all(name == role.name for name, role in RO.ROLES.items())


def test_every_registered_model_is_one_a_new_answer_may_name() -> None:
    """A role can never be registered to a model `answer --model` refuses (MiniMax, or a typo)."""
    for role in RO.ROLES.values():
        assert role.model in OH.NEW_ANSWER_MODELS, role.name
        assert role.model in OH.ANSWER_MODELS


def test_no_threshold_is_sealed_in_the_registry() -> None:
    """A sealed threshold lives in `calibrate_claude`'s THRESHOLDS.json, written before the run; the
    registry says `None` until a seal exists, so no role starts out calibrated."""
    assert all(role.threshold is None for role in RO.ROLES.values())


def test_a_role_carries_the_calibration_set_it_is_measured_on() -> None:
    """D6: every role passes a calibration. The two code roles are judged by the gates and by the
    Opus review, not by a pool of cases, and say so with `None`."""
    judged_by_gates = {name for name, r in RO.ROLES.items() if r.calibration_set is None}
    assert judged_by_gates == {"code_builder", "code_review"}
    sets = [r.calibration_set for r in RO.ROLES.values() if r.calibration_set is not None]
    assert all(isinstance(s, str) and s for s in sets)


def test_the_registry_is_read_only() -> None:
    with pytest.raises(TypeError):
        RO.ROLES["card_writer"] = RO.ROLES["operator"]  # type: ignore[index]
    with pytest.raises(AttributeError):
        RO.ROLES["card_writer"].model = "claude-haiku-5-5"  # type: ignore[misc]


# ------------------------------------------------------------------------------ the stamp check
def test_a_role_accepts_the_stamp_of_its_registered_model() -> None:
    for name, role in RO.ROLES.items():
        RO.require_stamp(name, OH.ANSWER_MODELS[role.model])


@pytest.mark.parametrize(
    "stamp",
    [OH.SONNET_MODEL, OH.MINIMAX_MODEL, "", "claude-opus-5-5", "anthropic/claude-opus-5-5"],
)
def test_a_role_refuses_every_other_stamp(stamp: str) -> None:
    """`card_writer` is Opus: a Sonnet stamp, a MiniMax stamp, the bare model id (the CLI maps it to
    the stamp) and a half-spelled stamp are all refused."""
    with pytest.raises(RO.RoleError, match="card_writer"):
        RO.require_stamp("card_writer", stamp)


def test_an_unregistered_role_is_refused_not_defaulted() -> None:
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.require_stamp("writer", OH.OPUS_MODEL)
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.require_model("writer", "claude-opus-5-5")


def test_the_model_id_of_the_cli_is_checked_against_the_registry() -> None:
    RO.require_model("fact_checker", "claude-sonnet-5-5")
    with pytest.raises(RO.RoleError, match="fact_checker.*claude-sonnet-5-5.*claude-opus-5-5"):
        RO.require_model("fact_checker", "claude-opus-5-5")


# ----------------------------------------------------------------------------- answered_by
def test_answered_by_names_the_role_before_the_agent() -> None:
    assert RO.answered_by("card_writer", "teaser-w-001") == "card_writer:teaser-w-001"
    assert RO.role_of("card_writer:teaser-w-001") == "card_writer"
    assert RO.role_of("teaser-w-001") is None  # an answer recorded before the registry
    assert RO.role_of("not_a_role:x") is None


@pytest.mark.parametrize("agent", ["", " ", "a:b"])
def test_the_agent_part_is_one_plain_name(agent: str) -> None:
    with pytest.raises(RO.RoleError):
        RO.answered_by("card_writer", agent)


def test_an_answer_naming_a_role_must_carry_that_roles_stamp() -> None:
    assert RO.answer_problem("card_writer:b1", OH.OPUS_MODEL) is None
    problem = RO.answer_problem("card_writer:b1", OH.SONNET_MODEL)
    assert problem is not None and "card_writer" in problem and OH.SONNET_MODEL in problem
    # an answer that names no role is not the registry's to judge
    assert RO.answer_problem("teaser-w-001", OH.SONNET_MODEL) is None


# ------------------------------------------------------------------------------- escalation
def test_the_escalation_path_is_haiku_sonnet_opus_and_ends_there() -> None:
    assert RO.next_tier("claude-haiku-5-5") == "claude-sonnet-5-5"
    assert RO.next_tier("claude-sonnet-5-5") == "claude-opus-5-5"
    with pytest.raises(RO.RoleError, match="no higher tier"):
        RO.next_tier("claude-opus-5-5")
    with pytest.raises(RO.RoleError):
        RO.next_tier("MiniMax-M3.1-Flash-Preview")


def test_an_escalation_is_a_record_never_a_silent_change() -> None:
    record = RO.escalation("image_prefilter", calibration_id="cal-img-1", reason="agreement 0.71")
    assert record == {
        "role": "image_prefilter",
        "from": "claude-haiku-5-5",
        "to": "claude-sonnet-5-5",
        "calibration_id": "cal-img-1",
        "reason": "agreement 0.71",
    }
    # the registry itself did not move
    assert RO.ROLES["image_prefilter"].model == "claude-haiku-5-5"


def test_an_escalation_needs_its_reason_and_its_calibration() -> None:
    with pytest.raises(RO.RoleError):
        RO.escalation("image_prefilter", calibration_id="", reason="x")
    with pytest.raises(RO.RoleError):
        RO.escalation("image_prefilter", calibration_id="c", reason=" ")


def test_the_top_tier_has_nothing_to_escalate_to() -> None:
    with pytest.raises(RO.RoleError, match="no higher tier"):
        RO.escalation("card_writer", calibration_id="c", reason="failed")


# ------------------------------------------------------------------------------- the digests
def test_a_role_digest_changes_with_any_field_of_the_role() -> None:
    base = RO.role_sha256("card_writer")
    assert base == RO.role_sha256("card_writer")
    assert base != RO.role_sha256("hook_rater")
    body = json.dumps(
        {
            "name": "card_writer",
            "model": RO.ROLES["card_writer"].model,
            "effort": RO.ROLES["card_writer"].effort,
            "calibration_set": RO.ROLES["card_writer"].calibration_set,
            "threshold": None,
        },
        sort_keys=True,
    )
    assert base == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_the_registry_file_digest_is_the_sha256_of_roles_py() -> None:
    assert (
        RO.registry_sha256() == hashlib.sha256((REMEDIATION / "roles.py").read_bytes()).hexdigest()
    )


# --------------------------------------------------------------------------------- the CLI
def _handoff_with_a_question(root: Path) -> None:
    OH.export(
        root,
        batch_id="batch-0001",
        stage="check",
        label="site-1",
        field=None,
        prompt="Is it so?\n",
    )


def _answer_argv(root: Path, text: Path, *extra: str) -> list[str]:
    return [
        sys.executable,
        str(REMEDIATION / "opus_handoff.py"),
        "answer",
        "--dir",
        str(root),
        "--batch-id",
        "batch-0001",
        "--stage",
        "check",
        "--label",
        "site-1",
        "--answered-by",
        "agent-7",
        "--text-file",
        str(text),
        *extra,
    ]


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", check=False)


def _stored(root: Path) -> dict[str, str]:
    path = root / OH.answer_relpath("batch-0001", "check", "site-1")
    return json.loads(path.read_text(encoding="utf-8"))


def test_answer_with_a_role_records_the_role_in_answered_by(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    done = _run(
        _answer_argv(tmp_path, text, "--model", "claude-sonnet-5-5", "--role", "fact_checker")
    )

    assert done.returncode == 0, done.stderr
    stored = _stored(tmp_path)
    assert stored["answered_by"] == "fact_checker:agent-7"
    assert stored["model"] == OH.SONNET_MODEL
    assert set(stored) == OH.ANSWER_KEYS  # the frozen shape did not grow


def test_answer_with_a_role_refuses_a_model_that_is_not_the_registered_one(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    refused = _run(
        _answer_argv(tmp_path, text, "--model", "claude-opus-5-5", "--role", "fact_checker")
    )

    assert refused.returncode == 2
    assert "fact_checker" in refused.stderr and "claude-sonnet-5-5" in refused.stderr
    assert not (tmp_path / OH.answer_relpath("batch-0001", "check", "site-1")).exists()


def test_answer_with_an_unknown_role_is_refused(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    refused = _run(_answer_argv(tmp_path, text, "--model", "claude-opus-5-5", "--role", "poet"))

    assert refused.returncode == 2 and "poet" in refused.stderr


def test_answer_without_a_role_keeps_the_agent_name_as_given(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    done = _run(_answer_argv(tmp_path, text, "--model", "claude-haiku-5-5"))

    assert done.returncode == 0, done.stderr
    assert _stored(tmp_path)["answered_by"] == "agent-7"
    assert _stored(tmp_path)["model"] == OH.HAIKU_MODEL
