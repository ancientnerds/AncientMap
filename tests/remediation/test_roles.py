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

#: D6 as amended by owner decision D36 of 2026-10-09 (quota: Sonnet instead of Opus), role by role:
#: (model id, effort). `field_researcher`, `fact_checker` and `web_verifier` went to Opus by tier move
#: and back to Sonnet by owner move; `card_writer`, `hook_rater`, `adversarial` and `code_review` went
#: to Sonnet by owner move (the hook rater at medium); `pilot_judge` is the small spot check that
#: stays on Opus; `enrich_writer` is the lane E writer that never left Sonnet. D40 as scoped by D45
#: (2026-10-17) added the card lane's own checkers on Opus.
D6 = {
    "card_writer": ("claude-sonnet-5-5", "high"),
    "hook_rater": ("claude-opus-5-5", "medium"),
    "fact_checker": ("claude-sonnet-5-5", "high"),
    "web_verifier": ("claude-sonnet-5-5", "high"),
    "card_fact_checker": ("claude-opus-5-5", "high"),
    "card_web_verifier": ("claude-opus-5-5", "high"),
    "field_researcher": ("claude-sonnet-5-5", "high"),
    "enrich_writer": ("claude-sonnet-5-5", "high"),
    "adversarial": ("claude-sonnet-5-5", "high"),
    "image_prefilter": ("claude-haiku-5-5", "low"),
    "image_depicts": ("claude-sonnet-5-5", "medium"),
    "code_builder": ("claude-sonnet-5-5", "high"),
    "code_review": ("claude-sonnet-5-5", "high"),
    "pilot_judge": ("claude-opus-5-5", "xhigh"),
    "operator": ("claude-haiku-5-5", "low"),
}


def test_the_registry_is_exactly_the_roles_of_decision_d6_and_the_enrich_writer() -> None:
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
    """`pilot_judge` is Opus: a Sonnet stamp, a MiniMax stamp, the bare model id (the CLI maps it to
    the stamp) and a half-spelled stamp are all refused."""
    with pytest.raises(RO.RoleError, match="pilot_judge"):
        RO.require_stamp("pilot_judge", stamp)


def test_an_unregistered_role_is_refused_not_defaulted() -> None:
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.require_stamp("writer", OH.OPUS_MODEL)
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.require_model("writer", "claude-opus-5-5")


def test_the_model_id_of_the_cli_is_checked_against_the_registry() -> None:
    RO.require_model("enrich_writer", "claude-sonnet-5-5")
    with pytest.raises(RO.RoleError, match="enrich_writer.*claude-sonnet-5-5.*claude-opus-5-5"):
        RO.require_model("enrich_writer", "claude-opus-5-5")
    RO.require_model("fact_checker", "claude-sonnet-5-5")  # back on Sonnet by owner move D36
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
    assert RO.answer_problem("pilot_judge:b1", OH.OPUS_MODEL) is None
    problem = RO.answer_problem("pilot_judge:b1", OH.SONNET_MODEL)
    assert problem is not None and "pilot_judge" in problem and OH.SONNET_MODEL in problem
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


def test_the_applied_moves_are_records_and_the_registry_stands_where_they_end() -> None:
    """Three tier moves, oldest first, each copied from the failed verdict that named it
    (`verdicts/fr-general-001.json`, `VERDICT-fact_checker.json` and `VERDICT-web_verifier.json` of
    teaser-2026-10-09b), then the seven owner moves of D36 (`test_the_owner_moves_of_d36...`), then the
    hook rater's tier move of teaser-2026-10-10 (`VERDICT-hook_rater.json`)."""
    moves = [dict(move) for move in RO.APPLIED_ESCALATIONS[:3]]
    assert moves == [
        {
            "role": "field_researcher",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "fr-general-001",
            "reason": "agreement 0.8636 is below the sealed threshold 0.9",
        },
        {
            "role": "fact_checker",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-09b",
            "reason": "failed: checker_agreement, checker_fail_again, checker_good",
        },
        {
            "role": "web_verifier",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-09b",
            "reason": "failed: verifier_verified",
        },
    ]
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, RO.ROLES)
    assert all(m.get("kind") == "owner" for m in RO.APPLIED_ESCALATIONS[3:-1])
    assert dict(RO.APPLIED_ESCALATIONS[-1]) == {
        "role": "hook_rater",
        "from": "claude-sonnet-5-5",
        "to": "claude-opus-5-5",
        "calibration_id": "teaser-2026-10-10",
        "reason": "failed: hook_pairs",
    }


def test_a_registry_that_moved_without_its_record_is_refused() -> None:
    """The ROLES edit and its record go together: an edit of the model alone, a record alone, a move
    of more than one tier, a chain that does not join, and a thin record are all refused."""
    moves = RO.APPLIED_ESCALATIONS[:3]
    moved = dict(RO.ROLES)
    moved["field_researcher"] = RO.Role(
        "field_researcher", "claude-sonnet-5-5", "high", "wd1_wd3_rounds_and_bp_set"
    )
    with pytest.raises(RO.RoleError, match="field_researcher is registered to claude-sonnet-5-5"):
        RO.check_applied_escalations(moves, moved)
    two_tiers = ({**moves[0], "from": "claude-haiku-5-5"},)
    with pytest.raises(RO.RoleError, match="not one tier up"):
        RO.check_applied_escalations(two_tiers, RO.ROLES)
    with pytest.raises(RO.RoleError, match="does not start where the last one ended"):
        RO.check_applied_escalations(
            (*moves, {**moves[0], "from": "claude-haiku-5-5", "to": "claude-sonnet-5-5"}), RO.ROLES
        )
    with pytest.raises(RO.RoleError, match="unregistered role 'writer'"):
        RO.check_applied_escalations(({**moves[0], "role": "writer"},), RO.ROLES)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations(({**moves[0], "reason": " "},), RO.ROLES)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations(
            ({k: v for k, v in moves[0].items() if k != "calibration_id"},), RO.ROLES
        )


def test_the_enrich_writer_stays_on_sonnet_under_its_own_calibration_set() -> None:
    """Lane E's writer was never measured on Opus: it does not follow the field researcher's move."""
    writer = RO.ROLES["enrich_writer"]
    assert (writer.model, writer.effort, writer.calibration_set) == (
        "claude-sonnet-5-5",
        "high",
        "enrich-writer",
    )
    assert writer.threshold is None
    assert RO.role_sha256("enrich_writer") != RO.role_sha256("field_researcher")


def test_the_top_tier_has_nothing_to_escalate_to() -> None:
    with pytest.raises(RO.RoleError, match="no higher tier"):
        RO.escalation("pilot_judge", calibration_id="c", reason="failed")


# ----------------------------------------------------------------------------- the owner moves
D36_ROLES = {
    "field_researcher": "high",
    "fact_checker": "high",
    "web_verifier": "high",
    "card_writer": "high",
    "hook_rater": "medium",
    "adversarial": "high",
    "code_review": "high",
}


def owner_move(**over: object) -> dict[str, object]:
    move: dict[str, object] = {
        "kind": "owner",
        "role": "image_depicts",
        "from": "claude-sonnet-5-5",
        "to": "claude-haiku-5-5",
        "effort": "low",
        "decision": "D40",
        "reason": "a test move",
        "evidence": ("cal-1",),
    }
    move.update(over)
    return move


def test_the_owner_moves_of_d36_put_seven_roles_from_opus_to_sonnet() -> None:
    owner = [m for m in RO.APPLIED_ESCALATIONS if m.get("kind") == "owner"]
    assert {m["role"]: m["effort"] for m in owner} == D36_ROLES
    assert len(owner) == len(D36_ROLES)
    for move in owner:
        assert (move["from"], move["to"], move["decision"]) == (
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "D36",
        )
        assert move["evidence"] and move["reason"].startswith("weekly Claude quota at 69 %")
        # the hook rater moved on up one tier after D36 (teaser-2026-10-10); its move ends there
        if move["role"] != "hook_rater":
            assert RO.ROLES[move["role"]].model == "claude-sonnet-5-5"
        assert RO.ROLES[move["role"]].effort == move["effort"]
    # the roles D36 left alone carry no owner move
    for name in ("pilot_judge", "enrich_writer", "image_prefilter", "image_depicts", "operator"):
        assert RO.owner_move(name, "D36") is None
    assert RO.ROLES["pilot_judge"].model == "claude-opus-5-5"


def test_the_chain_of_a_role_with_a_tier_move_and_an_owner_move_joins() -> None:
    """field_researcher: Sonnet to Opus (tier), Opus back to Sonnet (owner), in that order."""
    chain = [m for m in RO.APPLIED_ESCALATIONS if m["role"] == "field_researcher"]
    assert [(m["from"], m["to"], m.get("kind")) for m in chain] == [
        ("claude-sonnet-5-5", "claude-opus-5-5", None),
        ("claude-opus-5-5", "claude-sonnet-5-5", "owner"),
    ]
    assert RO.last_move("field_researcher") == chain[-1]
    assert RO.last_move("pilot_judge") is None
    # in the other order the chain still joins, but it ends at Opus: the registry is not there
    with pytest.raises(RO.RoleError, match="applied moves end at claude-opus-5-5"):
        RO.check_applied_escalations((chain[1], chain[0]), RO.ROLES)
    with pytest.raises(RO.RoleError, match="does not start where the last one ended"):
        RO.check_applied_escalations((chain[0], chain[0]), RO.ROLES)


def test_an_owner_move_may_go_down_or_up_by_any_number_of_tiers() -> None:
    roles = dict(RO.ROLES)
    roles["image_depicts"] = RO.Role("image_depicts", "claude-haiku-5-5", "low", "x")
    RO.check_applied_escalations((owner_move(),), roles)  # Sonnet to Haiku
    roles["image_depicts"] = RO.Role("image_depicts", "claude-opus-5-5", "low", "x")
    RO.check_applied_escalations(
        (owner_move(**{"from": "claude-haiku-5-5", "to": "claude-opus-5-5"}),), roles
    )  # two tiers up: no tier rule binds an owner move


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"decision": "decision 40"}, "not an owner decision id"),
        ({"decision": ""}, "carries exactly"),
        ({"reason": " "}, "carries exactly"),
        ({"evidence": ()}, "carries exactly"),
        ({"evidence": ("",)}, "carries exactly"),
        ({"evidence": "cal-1"}, "carries exactly"),
        ({"to": "claude-sonnet-5-5"}, "to itself moves nothing"),
        ({"to": "MiniMax-M3.1-Flash-Preview"}, "not a model a role may be registered to"),
        ({"effort": "extreme"}, "effort 'extreme'"),
        ({"role": "writer"}, "unregistered role 'writer'"),
    ],
)
def test_a_thin_or_unknown_owner_move_is_refused(over: dict[str, object], message: str) -> None:
    roles = dict(RO.ROLES)
    roles["image_depicts"] = RO.Role("image_depicts", "claude-haiku-5-5", "low", "x")
    with pytest.raises(RO.RoleError, match=message):
        RO.check_applied_escalations((owner_move(**over),), roles)


def test_an_owner_move_lacking_a_key_or_carrying_an_extra_one_is_refused() -> None:
    move = owner_move()
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations(({k: v for k, v in move.items() if k != "effort"},), RO.ROLES)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations(({**move, "extra": "x"},), RO.ROLES)


def test_a_registry_that_left_its_owner_move_is_refused_in_model_and_in_effort() -> None:
    moves = RO.APPLIED_ESCALATIONS
    other_model = dict(RO.ROLES)
    other_model["card_writer"] = RO.Role(
        "card_writer", "claude-opus-5-5", "high", "wb_cards_accepted"
    )
    with pytest.raises(RO.RoleError, match="card_writer is registered to claude-opus-5-5"):
        RO.check_applied_escalations(moves, other_model)
    other_effort = dict(RO.ROLES)
    other_effort["hook_rater"] = RO.Role(
        "hook_rater", "claude-opus-5-5", "xhigh", "design_run_hand_drawn_60"
    )
    with pytest.raises(RO.RoleError, match="hook_rater is registered at effort xhigh"):
        RO.check_applied_escalations(moves, other_effort)


def test_an_owner_move_that_does_not_follow_the_chain_is_refused() -> None:
    with pytest.raises(RO.RoleError, match="does not start where the last one ended"):
        RO.check_applied_escalations(
            (
                *RO.APPLIED_ESCALATIONS,
                owner_move(role="card_writer", **{"from": "claude-opus-5-5"}),
            ),
            RO.ROLES,
        )


def test_require_owner_move_names_what_is_missing() -> None:
    move = RO.require_owner_move(
        "field_researcher", "D36", model="claude-sonnet-5-5", calibration_id="fr-general-001"
    )
    assert move["role"] == "field_researcher" and move["decision"] == "D36"
    with pytest.raises(
        RO.RoleError, match="no applied owner move of role fact_checker names decision D37"
    ):
        RO.require_owner_move(
            "fact_checker", "D37", model="claude-sonnet-5-5", calibration_id="teaser-2026-10-09b"
        )
    with pytest.raises(RO.RoleError, match="no applied owner move of role pilot_judge"):
        RO.require_owner_move(
            "pilot_judge", "D36", model="claude-opus-5-5", calibration_id="fr-general-001"
        )
    with pytest.raises(RO.RoleError, match="registered to claude-sonnet-5-5, not claude-opus-5-5"):
        RO.require_owner_move(
            "fact_checker", "D36", model="claude-opus-5-5", calibration_id="teaser-2026-10-09c"
        )
    with pytest.raises(RO.RoleError, match="does not rest on cal-x"):
        RO.require_owner_move(
            "fact_checker", "D36", model="claude-sonnet-5-5", calibration_id="cal-x"
        )


# ---------------------------------------------------------------------- the candidate model
def test_a_candidate_is_a_registrable_model_that_is_not_the_registered_one() -> None:
    assert RO.candidate_model("fact_checker", "claude-haiku-5-5") == "claude-haiku-5-5"
    with pytest.raises(RO.RoleError, match="is the registered model of fact_checker"):
        RO.candidate_model("fact_checker", "claude-sonnet-5-5")
    with pytest.raises(RO.RoleError, match="not a model a role may be registered to"):
        RO.candidate_model("fact_checker", "MiniMax-M3.1-Flash-Preview")
    with pytest.raises(RO.RoleError, match="no role"):
        RO.candidate_model("writer", "claude-haiku-5-5")


def test_a_candidate_digest_is_the_entry_with_the_candidate_and_leaves_the_registry_alone() -> None:
    registered = RO.role_sha256("fact_checker")
    candidate = RO.role_sha256("fact_checker", model="claude-haiku-5-5")
    assert candidate != registered
    assert RO.role_sha256("fact_checker", model="claude-sonnet-5-5") == registered
    assert RO.ROLES["fact_checker"].model == "claude-sonnet-5-5"
    entry = RO.ROLES["fact_checker"]
    body = json.dumps(
        {
            "name": "fact_checker",
            "model": "claude-haiku-5-5",
            "effort": entry.effort,
            "calibration_set": entry.calibration_set,
            "threshold": None,
        },
        sort_keys=True,
    )
    assert candidate == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_a_candidate_stamp_is_the_stamp_of_the_candidate_only() -> None:
    RO.require_candidate_stamp("claude-haiku-5-5", OH.ANSWER_MODELS["claude-haiku-5-5"])
    with pytest.raises(RO.RoleError, match="candidate model is claude-haiku-5-5"):
        RO.require_candidate_stamp("claude-haiku-5-5", OH.SONNET_MODEL)


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
        _answer_argv(tmp_path, text, "--model", "claude-sonnet-5-5", "--role", "enrich_writer")
    )

    assert done.returncode == 0, done.stderr
    stored = _stored(tmp_path)
    assert stored["answered_by"] == "enrich_writer:agent-7"
    assert stored["model"] == OH.SONNET_MODEL
    assert set(stored) == OH.ANSWER_KEYS  # the frozen shape did not grow


def test_answer_with_a_role_refuses_a_model_that_is_not_the_registered_one(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    refused = _run(
        _answer_argv(tmp_path, text, "--model", "claude-opus-5-5", "--role", "enrich_writer")
    )

    assert refused.returncode == 2
    assert "enrich_writer" in refused.stderr and "claude-sonnet-5-5" in refused.stderr
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


# ------------------------------------------------------------- the candidate trial's recorder
def test_answer_of_a_candidate_trial_records_the_role_and_the_candidates_stamp(
    tmp_path: Path,
) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: SUPPORTED\n", encoding="utf-8")

    done = _run(
        _answer_argv(
            tmp_path, text, "--model", "claude-haiku-5-5", "--role", "fact_checker",
            "--candidate-model", "claude-haiku-5-5",
        )
    )  # fmt: skip

    assert done.returncode == 0, done.stderr
    stored = _stored(tmp_path)
    assert stored["answered_by"] == "fact_checker:agent-7"
    assert stored["model"] == OH.ANSWER_MODELS["claude-haiku-5-5"]
    assert set(stored) == OH.ANSWER_KEYS
    # a trial answer is not the registered role's: the registry's own stamp check says so
    assert RO.answer_problem(stored["answered_by"], stored["model"]) is not None


def test_a_candidate_trial_answer_needs_a_role(tmp_path: Path) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("x\n", encoding="utf-8")
    refused = _run(
        _answer_argv(
            tmp_path, text, "--model", "claude-haiku-5-5", "--candidate-model", "claude-haiku-5-5"
        )
    )
    assert refused.returncode == 2 and "name it with --role" in refused.stderr


@pytest.mark.parametrize(
    ("model", "candidate", "message"),
    [
        ("claude-sonnet-5-5", "claude-sonnet-5-5", "is the registered model of fact_checker"),
        ("claude-sonnet-5-5", "claude-haiku-5-5", "is not the candidate model claude-haiku-5-5"),
    ],
)
def test_a_candidate_trial_answer_names_a_candidate_that_is_not_the_registered_model(
    tmp_path: Path, model: str, candidate: str, message: str
) -> None:
    _handoff_with_a_question(tmp_path)
    text = tmp_path / "a.txt"
    text.write_text("x\n", encoding="utf-8")
    refused = _run(
        _answer_argv(
            tmp_path, text, "--model", model, "--role", "fact_checker",
            "--candidate-model", candidate,
        )
    )  # fmt: skip
    assert refused.returncode == 2 and message in refused.stderr
    assert not (tmp_path / OH.answer_relpath("batch-0001", "check", "site-1")).exists()


def test_an_owner_decision_does_not_reach_past_a_later_move_of_the_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D36 put `fact_checker` on Sonnet; if a later tier move took it to Opus, a verdict made on Opus
    is not the model the decision kept, whatever the registry holds."""
    later = {
        "role": "fact_checker",
        "from": "claude-sonnet-5-5",
        "to": "claude-opus-5-5",
        "calibration_id": "teaser-2026-10-09b",
        "reason": "failed again",
    }
    roles = dict(RO.ROLES)
    roles["fact_checker"] = RO.Role(
        "fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"
    )
    monkeypatch.setattr(RO, "ROLES", roles)
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, later))
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, roles)
    assert RO.last_move("fact_checker") == later
    with pytest.raises(RO.RoleError, match="ends at claude-sonnet-5-5, not claude-opus-5-5"):
        RO.require_owner_move(
            "fact_checker", "D36", model="claude-opus-5-5", calibration_id="teaser-2026-10-09b"
        )
