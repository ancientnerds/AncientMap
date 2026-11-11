"""Owner moves without calibration: owner decisions D153 and D154 of 2026-11-10 and D157 of
2026-11-11, on the role registry as it is.

D153: every role answers on `claude-fable-5-2`; D157 (the Fable quota is used up): every role answers
on `claude-opus-5-5`. D154: no calibration is run - a role stands on the model by the owner's
decision, with no verdict of its own. Both are one kind of record (`roles.UNCALIBRATED_DECISIONS`):
an owner move per role, with no evidence and with `at`, the time it took effect. `roles.py` holds the
rules that follow (`owner_standing` with `standing_problem`, `answer_problem` through `model_at`,
`model_now` through `run_model_at`); every gate and every brief asks them. These tests prove the
rules, each gate that asks the first one, the recorder, and a run that began before either decision
going on with Opus.

The history of the registry up to D153 and the calibration machinery are proven on the registry as
it stood until then (`conftest.registry_until_d153`, `test_roles.py`, `test_calibrate_claude.py`).
No test here calls a model or opens a socket.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
for _path in (REPO, REMEDIATION):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import calibrate_claude as CC  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from identity import label_rounds as LR  # noqa: E402
from identity import rounds as IR  # noqa: E402
from image_roles import standing as STD  # noqa: E402
from mechanical import teaser as MT  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from served_image import state as ST  # noqa: E402
from teaser import calibrate as K  # noqa: E402
from teaser import run as R  # noqa: E402
from wc import cli as WC  # noqa: E402
from wc import enrich as E  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_teaser_shorts_run import (  # noqa: E402
    NAMES,
    judge_client,
    make_run,
    passes,
    rates,
    sid,
    step,
    verifies,
    writes,
)
from tests.remediation.test_wc import _run as wc_run  # noqa: E402
from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401

FABLE = "claude-fable-5-2"
OPUS = "claude-opus-5-5"
STANDING = "owner decision D157 (no calibration on claude-opus-5-5: D154)"
D153_AT = "2026-11-10T20:55:24+00:00"
D157_AT = "2026-11-11T16:27:38+00:00"
#: Three times an answer can have been recorded at: before D153, between the two, after D157.
BEFORE = "2026-11-10T20:00:00+00:00"
BETWEEN = "2026-11-11T10:00:00+00:00"
AFTER = "2026-11-11T18:00:00+00:00"
#: Where D153 found each role: (the model it answered on until then, its effort). The registry of
#: `test_roles.D6`, written out again on purpose: these are the stamps of the answers on record.
UNTIL_D153 = {
    "card_writer": ("claude-opus-5-5", "high"),
    "hook_rater": ("claude-opus-5-5", "medium"),
    "fact_checker": ("claude-opus-5-5", "high"),
    "web_verifier": ("claude-sonnet-5-5", "high"),
    "card_fact_checker": ("claude-opus-5-5", "high"),
    "card_web_verifier": ("claude-opus-5-5", "high"),
    "wc_web_verifier": ("claude-opus-5-5", "high"),
    "field_researcher": ("claude-sonnet-5-5", "high"),
    "enrich_writer": ("claude-sonnet-5-5", "high"),
    "adversarial": ("claude-sonnet-5-5", "high"),
    "card_adversarial": ("claude-opus-5-5", "high"),
    "wc_adversarial": ("claude-opus-5-5", "high"),
    "image_prefilter": ("claude-opus-5-5", "low"),
    "image_depicts": ("claude-opus-5-5", "medium"),
    "image_adversarial": ("claude-opus-5-5", "high"),
    "code_builder": ("claude-sonnet-5-5", "high"),
    "code_review": ("claude-sonnet-5-5", "high"),
    "pilot_judge": ("claude-opus-5-5", "xhigh"),
    "operator": ("claude-haiku-5-5", "low"),
}
ROLE_NAMES = sorted(UNTIL_D153)


# ------------------------------------------------------------------------------ the registry
def test_every_role_is_registered_to_opus_at_the_effort_it_had() -> None:
    assert {name: (r.model, r.effort) for name, r in RO.ROLES.items()} == {
        name: (OPUS, effort) for name, (_, effort) in UNTIL_D153.items()
    }
    assert RO.FABLE == FABLE and RO.NO_CALIBRATION_DECISION == "D154"
    assert {d: (m["to"], m["at"]) for d, m in RO.UNCALIBRATED_DECISIONS.items()} == {
        "D153": (FABLE, D153_AT),
        "D157": (OPUS, D157_AT),
    }
    assert RO.ROLELESS_MODEL == OPUS
    assert OH.ANSWER_MODELS[FABLE] == "anthropic/claude-fable-5-2 (Claude Code agent)"
    assert OH.NEW_ANSWER_MODELS[0] == OPUS  # the briefs' first offer


@pytest.mark.parametrize("decision", ["D153", "D157"])
def test_each_role_got_there_by_an_owner_move_of_its_own_under_each_decision(
    decision: str,
) -> None:
    """One record per role and decision: from the model it stood on to the decision's model, the
    effort unchanged, at the decision's time - and resting on no calibration (D154)."""
    moves = [m for m in RO.APPLIED_ESCALATIONS if m.get("decision") == decision]
    assert [m["role"] for m in moves] == list(RO.ROLES)  # every role, in the registry's order
    for move in moves:
        name = move["role"]
        assert RO.uncalibrated(move) and RO.owner_move(name, decision) == move
        assert (move["kind"], move["effort"]) == ("owner", UNTIL_D153[name][1])
        assert move["at"] == RO.UNCALIBRATED_DECISIONS[decision]["at"]
        assert move["evidence"] == ()
        assert "no calibration was run on" in move["reason"] and "D154" in move["reason"]
        if decision == "D153":
            assert (move["from"], move["to"]) == (UNTIL_D153[name][0], FABLE)
            assert "only Fable 5.2" in move["reason"]
        else:
            assert (move["from"], move["to"]) == (FABLE, OPUS)
            assert RO.last_move(name) == move
            assert RO.owner_tail(name) == (RO.owner_move(name, "D153"), move)
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, RO.ROLES)
    RO.check_settled_tier_moves(RO.SETTLED_TIER_MOVES, RO.APPLIED_ESCALATIONS, RO.ROLES)


def test_the_d157_moves_close_the_chain() -> None:
    moves = [m for m in RO.APPLIED_ESCALATIONS if m.get("decision") == "D157"]
    assert RO.APPLIED_ESCALATIONS[-len(moves) :] == tuple(moves)  # appended, nothing after them


def test_fable_is_on_no_tier_and_opus_is_the_top() -> None:
    with pytest.raises(RO.RoleError, match="'claude-fable-5-2' is on no tier"):
        RO.next_tier(FABLE)
    with pytest.raises(RO.RoleError, match="no higher tier than claude-opus-5-5"):
        RO.escalation("card_writer", calibration_id="cal-x", reason="failed")


def owner_move(which: str = "D157", **over: object) -> dict[str, object]:
    move: dict[str, object] = dict(RO.owner_move("operator", which) or {})
    move.update(over)
    return move


@pytest.mark.parametrize("decision", ["D153", "D157"])
def test_a_move_without_calibration_rests_on_none_and_may_not_name_one(decision: str) -> None:
    """D154: no calibration is run. The move's evidence is empty and must be - naming one would
    claim a measurement nobody made -, it ends at the decision's model and carries the decision's
    time. Every other owner move still needs the calibrations it rests on, and carries no time."""
    model = RO.UNCALIBRATED_DECISIONS[decision]["to"]
    wrong = FABLE if model == OPUS else OPUS
    RO._check_owner_move(owner_move(decision))
    with pytest.raises(RO.RoleError, match="rests on no calibration .D154"):
        RO._check_owner_move(owner_move(decision, evidence=("scripted_dry_run",)))
    with pytest.raises(RO.RoleError, match=f"a move under {decision} ends at {model}"):
        RO._check_owner_move(owner_move(decision, to=wrong))
    with pytest.raises(RO.RoleError, match=f"a move under {decision} took effect at"):
        RO._check_owner_move(owner_move(decision, at="2026-11-01T00:00:00+00:00"))
    no_time = owner_move(decision)
    del no_time["at"]
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO._check_owner_move(no_time)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO._check_owner_move(owner_move(decision, decision="D36"))  # a time, no evidence
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO._check_owner_move(owner_move(decision, evidence=None))
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO._check_owner_move(owner_move(decision, evidence=("",)))


def test_the_timed_moves_of_a_role_follow_each_other_in_time() -> None:
    swapped = tuple(
        {**m, "at": "2026-11-09T00:00:00+00:00"}
        if m["role"] == "operator" and m.get("decision") == "D157"
        else m
        for m in RO.APPLIED_ESCALATIONS
    )
    with pytest.raises(RO.RoleError, match="took effect at"):
        RO.check_applied_escalations(swapped, RO.ROLES)
    with pytest.raises(RO.RoleError, match="does not follow the decision before"):
        RO.check_uncalibrated_decisions(
            {
                "D153": {"to": FABLE, "at": D157_AT, "why": "x"},
                "D157": {"to": OPUS, "at": D153_AT, "why": "y"},
            }
        )
    with pytest.raises(RO.RoleError, match="carries no time zone"):
        RO.check_uncalibrated_decisions(
            {"D157": {"to": OPUS, "at": "2026-11-11T16:00", "why": "y"}}
        )


def test_a_registry_edit_without_its_d157_move_is_refused() -> None:
    """The ROLES edit and its record go together, as for every move before: Opus in the registry
    without the D157 move, and the move without the edit, are both refused at import."""
    without = tuple(
        m
        for m in RO.APPLIED_ESCALATIONS
        if not (m["role"] == "card_writer" and m.get("decision") == "D157")
    )
    with pytest.raises(RO.RoleError, match="card_writer is registered to claude-opus-5-5"):
        RO.check_applied_escalations(without, RO.ROLES)
    unmoved = {**RO.ROLES, "operator": RO.Role("operator", FABLE, "low", "x")}
    with pytest.raises(RO.RoleError, match="operator is registered to claude-fable-5-2"):
        RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, unmoved)
    wrong_start = (*without, owner_move(role="card_writer", **{"from": "claude-sonnet-5-5"}))
    with pytest.raises(RO.RoleError, match="does not start where the last one ended"):
        RO.check_applied_escalations(wrong_start, RO.ROLES)


def test_a_settlement_is_held_to_where_its_roles_stood_until_d153() -> None:
    """The settled tier moves record the tier chain, which D153 ended: `adversarial` stayed on
    Sonnet and `card_adversarial` took its card context on Opus. A D153 move that started somewhere
    else would say the settled role had moved after all; D157 changes nothing of that."""
    moved = tuple(
        {**m, "from": "claude-opus-5-5"}
        if m["role"] == "adversarial" and m.get("decision") == "D153"
        else m
        for m in RO.APPLIED_ESCALATIONS
    )
    with pytest.raises(
        RO.RoleError, match="adversarial stood at claude-opus-5-5 until the owner moves"
    ):
        RO.check_settled_tier_moves(RO.SETTLED_TIER_MOVES, moved, RO.ROLES)


# ------------------------------------------------------------------------------ rule 1: standing
@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_role_stands_by_the_owners_latest_decision_in_words(name: str) -> None:
    """Owner standing without a verdict: the record names the latest decision, never `passed`, and
    the time the standing began (the first move of the tail, D153's)."""
    record = RO.owner_standing(name)
    assert record == {
        "role": name,
        "model": OPUS,
        "standing": STANDING,
        "owner_decision": "D157",
        "since": D153_AT,
    }
    assert record["standing"] == RO.owner_standing_text("D157")
    assert CC.PASSED not in record.values() and CC.RELEASED not in record["standing"]
    assert "calibration_id" not in record


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_the_standing_covers_the_answers_recorded_since_it_began(name: str) -> None:
    """An answer recorded before D153 was written on a model that stood by a calibration, which a
    gate standing on the owner's decision did not ask."""
    problem = RO.standing_problem(name, BEFORE)
    assert problem is not None and "before the role's owner standing began" in problem
    assert RO.standing_problem(name, D153_AT) is None
    assert RO.standing_problem(name, BETWEEN) is None
    assert RO.standing_problem(name, AFTER) is None


def test_an_unregistered_role_stands_by_nothing() -> None:
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.owner_standing("writer")
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.model_now("writer", "claude-opus-5-5")


def test_a_role_moved_again_after_d157_stands_by_its_calibration_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decisions cover a role only while its last move is one of them: a later owner move with
    a calibration puts the gates back to asking for a verdict."""
    later = {
        "kind": "owner",
        "role": "card_writer",
        "from": OPUS,
        "to": "claude-sonnet-5-5",
        "effort": "high",
        "decision": "D199",
        "reason": "a later owner move",
        "evidence": ("cal-later",),
    }
    roles = {**RO.ROLES, "card_writer": RO.Role("card_writer", "claude-sonnet-5-5", "high", "x")}
    monkeypatch.setattr(RO, "ROLES", roles)
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, later))
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, RO.ROLES)
    assert RO.owner_tail("card_writer") == () and RO.owner_standing("card_writer") is None
    assert RO.owner_standing("hook_rater") is not None  # the others are untouched
    assert RO.model_now("card_writer", OPUS) == OPUS  # a run is moved by the tail only
    assert RO.answer_problem("card_writer:w", OH.OPUS_MODEL, answered_at=AFTER) is not None
    assert RO.answer_problem("card_writer:w", OH.FABLE_MODEL, answered_at=BETWEEN) is None
    with pytest.raises(RO.RoleError, match="does not stand by an owner decision"):
        RO.standing_problem("card_writer", AFTER)
    with pytest.raises(CC.CalibrationError, match="no passing or released verdict"):
        CC.require_passed(Path("no-such-root"), [("card_writer", "all")])


@pytest.mark.usefixtures("registry_until_d153")
def test_no_role_stood_by_an_owner_decision_before_d153() -> None:
    assert all(RO.owner_standing(name) is None for name in RO.ROLES)
    assert all(RO.owner_tail(name) == () for name in RO.ROLES)


# ------------------------------------------------------------------------------ the gates
def test_the_fields_wave_gate_names_the_decision_and_needs_no_verdict(tmp_path: Path) -> None:
    """`calibrate_claude.require_passed` (lane wd5's wave, `fields/plan.py`): an empty calibration
    root holds no verdict, and the roles stand all the same - by the decision, said in words."""
    needs = [("field_researcher", "fields-decided"), ("adversarial", "adv-known-truth")]
    assert CC.require_passed(tmp_path, needs) == [
        {
            "role": "field_researcher",
            "comparison": "fields-decided",
            "standing": STANDING,
            "owner_decision": "D157",
        },
        {
            "role": "adversarial",
            "comparison": "adv-known-truth",
            "standing": STANDING,
            "owner_decision": "D157",
        },
    ]


def test_the_wave_of_lane_wd5_records_the_decision_as_its_calibrations(tmp_path: Path) -> None:
    from fields import plan as FP
    from fields import pools as PL

    lines = FP._require_calibrated()
    assert [(line["role"], line["comparison"]) for line in lines] == list(PL.WD5_CALIBRATIONS)
    assert {line["standing"] for line in lines} == {STANDING}
    assert all("calibration_id" not in line for line in lines)


def test_the_card_lanes_standing_names_the_decision(tmp_path: Path) -> None:
    """`teaser/calibrate.py standing`: no sealed directory, no verdict file - the role stands."""
    for role in ("card_writer", "hook_rater", "card_fact_checker", "card_web_verifier"):
        assert K.standing(tmp_path / "teaser-none", role) == RO.owner_standing(role)
    assert (
        K.main(["standing", "--run-dir", str(tmp_path / "teaser-none"), "--role", "card_writer"])
        == 0
    )


def test_the_image_lanes_gate_names_the_decision_for_every_slot(tmp_path: Path) -> None:
    """`image_roles/standing.require_standing`, the gate of the three exports: the slots' roles
    (`adversarial` is the image lane's own `image_adversarial`) stand without their directories."""
    lines = STD.require_standing(["image_prefilter", "image_depicts", "adversarial"], tmp_path)
    assert [(line["slot"], line["role"]) for line in lines] == [
        ("image_prefilter", "image_prefilter"),
        ("image_depicts", "image_depicts"),
        ("adversarial", "image_adversarial"),
    ]
    assert {line["standing"] for line in lines} == {STANDING}
    assert all(line["owner_decision"] == "D157" and line["model"] == OPUS for line in lines)


def test_the_identity_gates_name_the_decision_and_ask_no_calibration_id(tmp_path: Path) -> None:
    """`identity/rounds.require_calibration` (run.py import) and `label_rounds.check_calibrated`
    (the duplicate and parent judges): no id named, no verdict read; the time the standing began
    is what `import_round` holds the answers to."""
    verdict = IR.require_calibration(tmp_path, None, "web_verifier", "scope-window-web")
    assert verdict == {
        "role": "web_verifier",
        "model": OPUS,
        "standing": STANDING,
        "owner_decision": "D157",
        "since": D153_AT,
        "calibration_id": None,
        "agreement": None,
        "decided_at": None,
    }
    assert LR.check_calibrated(["web_verifier", "adversarial"], {}, tmp_path) == [
        RO.owner_standing("adversarial"),
        RO.owner_standing("web_verifier"),
    ]


def test_the_enrichment_approval_names_the_decision_in_place_of_a_verdict(tmp_path: Path) -> None:
    """`wc/enrich.writer_standing`, what a lane-E pilot approval records for the writer: no verdict
    whose sha256 could be named."""
    assert E.writer_standing(tmp_path) == {"writer_standing": STANDING}


@pytest.mark.usefixtures("registry_until_d153")
def test_every_gate_still_refuses_a_role_that_stands_by_no_decision(tmp_path: Path) -> None:
    """The gates are not gone: on a registry without the owner moves without calibration each one
    asks its calibration exactly as before and refuses an empty calibration root."""
    with pytest.raises(CC.CalibrationError, match="no passing or released verdict"):
        CC.require_passed(tmp_path, [("field_researcher", "fields-decided")])
    with pytest.raises(K.CalibrationError, match="is not sealed"):
        K.standing(tmp_path / "teaser-none", "card_writer")
    with pytest.raises(ST.StateError, match="the image roles do not stand"):
        STD.require_standing(["image_prefilter", "image_depicts", "adversarial"], tmp_path)
    with pytest.raises(IR.RoundError, match="does not stand by an owner decision"):
        IR.require_calibration(tmp_path, None, "web_verifier", "scope-window-web")
    with pytest.raises(IR.RoundError, match="has no verdict"):
        IR.require_calibration(tmp_path, "cal-none", "web_verifier", "scope-window-web")
    with pytest.raises(LR.RoundError, match="no passed calibration of it is named"):
        LR.check_calibrated(["web_verifier"], {}, tmp_path)
    with pytest.raises(E.EnrichError, match="has no sealed passed verdict"):
        E.writer_standing(tmp_path)


# ------------------------------------------------------------------------------ rule 2: the stamps
@pytest.mark.parametrize("name", ROLE_NAMES)
def test_each_stamp_is_valid_in_its_own_window_only(name: str) -> None:
    """D153 and D157: "answers recorded earlier keep their stamp and stay valid" - the stamp of the
    model the role stood on when the answer was recorded, and no other: the earlier model's before
    D153, Fable's between the decisions, Opus's from D157 on."""
    earlier = OH.ANSWER_MODELS[UNTIL_D153[name][0]]
    by = f"{name}:agent-1"
    window = {
        BEFORE: earlier,
        BETWEEN: OH.FABLE_MODEL,
        AFTER: OH.OPUS_MODEL,
        D157_AT: OH.OPUS_MODEL,
    }
    for when, valid in window.items():
        assert RO.answer_problem(by, valid, answered_at=when) is None, when
        for stamp in set(OH.ANSWER_MODELS.values()) - {valid}:
            problem = RO.answer_problem(by, stamp, answered_at=when)
            assert problem is not None and f"role {name} is registered to" in problem, (when, stamp)
            assert stamp in problem
    assert RO.answer_problem(by, UNTIL_D153[name][0], answered_at=BEFORE) is not None  # bare id


def test_a_new_answer_under_an_earlier_model_is_refused_whatever_wrote_it() -> None:
    """The review finding on 2bc9aab: an earlier model's stamp was taken at any time. An Opus answer
    of the card verifier recorded while it stood on Fable, and a Fable one recorded after D157, are
    neither the role's - whichever recorder path wrote them."""
    by = "card_web_verifier:x"
    assert RO.answer_problem(by, OH.OPUS_MODEL, answered_at=BEFORE) is None
    assert RO.answer_problem(by, OH.OPUS_MODEL, answered_at=BETWEEN) is not None
    assert RO.answer_problem(by, OH.FABLE_MODEL, answered_at=AFTER) is not None
    assert RO.answer_problem("web_verifier:x", OH.SONNET_MODEL, answered_at=AFTER) is not None
    with pytest.raises(RO.RoleError, match="carries no time zone"):
        RO.answer_problem(by, OH.OPUS_MODEL, answered_at="2026-11-11T18:00:00")


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_new_answer_of_a_role_can_only_be_opus(name: str) -> None:
    """The recorder's check takes Opus only, and the strict stamp check (a calibration's fresh
    answers) takes Opus's stamp only."""
    RO.require_model(name, OPUS)
    RO.require_stamp(name, OH.OPUS_MODEL)
    for earlier in {UNTIL_D153[name][0], FABLE} - {OPUS}:
        with pytest.raises(RO.RoleError, match=f"role {name} is registered to {OPUS}, not"):
            RO.require_model(name, earlier)
        with pytest.raises(RO.RoleError, match=f"role {name} is registered to {OPUS}"):
            RO.require_stamp(name, OH.ANSWER_MODELS[earlier])


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_candidate_trial_cannot_take_a_model_an_owner_move_took_the_role_from(name: str) -> None:
    earlier = UNTIL_D153[name][0]
    for taken, decision in ((earlier, "D153"), (FABLE, "D157")):
        if taken == OPUS:
            continue  # the registered model is no candidate either
        with pytest.raises(RO.RoleError, match=f"owner decision {decision} took {name} from"):
            RO.candidate_model(name, taken)
    for other in set(OH.NEW_ANSWER_MODELS) - {earlier, FABLE, OPUS}:
        assert RO.candidate_model(name, other) == other


def _answer_argv(root: Path, text: Path, *extra: str, by: str = "teaser-verify-001") -> list[str]:
    return [
        sys.executable, str(REMEDIATION / "opus_handoff.py"), "answer", "--dir", str(root),
        "--batch-id", "verify-001", "--stage", "verify", "--label", "site-1",
        "--answered-by", by, "--text-file", str(text), *extra,
    ]  # fmt: skip


def _recorder(tmp_path: Path) -> tuple[Path, Path]:
    OH.export(tmp_path, batch_id="verify-001", stage="verify", label="site-1", field=None,
              prompt="Is it so?\n")  # fmt: skip
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: VERIFIED\n", encoding="utf-8")
    return tmp_path, text


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", check=False)


def test_the_recorder_takes_an_opus_answer_of_the_card_verifier(tmp_path: Path) -> None:
    """The command the briefs of wave a2's open verify batches print."""
    root, text = _recorder(tmp_path)
    done = _run(_answer_argv(root, text, "--model", OPUS, "--role", "card_web_verifier"))
    assert done.returncode == 0, done.stderr
    stored = json.loads(
        (root / OH.answer_relpath("verify-001", "verify", "site-1")).read_text("utf-8")
    )
    assert stored["model"] == OH.OPUS_MODEL
    assert stored["answered_by"] == "card_web_verifier:teaser-verify-001"
    assert (
        RO.answer_problem(stored["answered_by"], stored["model"], answered_at=stored["answered_at"])
        is None
    )
    assert OH.validate(root).ok


@pytest.mark.parametrize("model", [FABLE, "claude-sonnet-5-5", "claude-haiku-5-5"])
def test_the_recorder_refuses_a_new_answer_of_a_role_on_any_other_model(
    tmp_path: Path, model: str
) -> None:
    """A wrong-model new answer: Fable was this role's model until D157, and is refused like the
    others - nothing is written."""
    root, text = _recorder(tmp_path)
    refused = _run(_answer_argv(root, text, "--model", model, "--role", "card_web_verifier"))
    assert refused.returncode == 2
    assert f"role card_web_verifier is registered to {OPUS}, not {model}" in refused.stderr
    assert not (root / OH.answer_relpath("verify-001", "verify", "site-1")).exists()


def test_the_recorder_refuses_a_candidate_trial_of_a_model_the_role_was_moved_from(
    tmp_path: Path,
) -> None:
    root, text = _recorder(tmp_path)
    refused = _run(
        _answer_argv(
            root, text, "--model", FABLE, "--role", "card_web_verifier", "--candidate-model", FABLE
        )
    )
    assert refused.returncode == 2
    assert "owner decision D157 took card_web_verifier from claude-fable-5-2" in refused.stderr
    assert not (root / OH.answer_relpath("verify-001", "verify", "site-1")).exists()


def test_the_recorder_refuses_a_role_written_into_answered_by(tmp_path: Path) -> None:
    """The second path: `--answered-by card_web_verifier:x` without `--role` would read as the
    role's answer without the role's model ever being checked."""
    root, text = _recorder(tmp_path)
    refused = _run(_answer_argv(root, text, "--model", FABLE, by="card_web_verifier:x"))
    assert refused.returncode == 2
    assert "names role card_web_verifier" in refused.stderr
    assert not (root / OH.answer_relpath("verify-001", "verify", "site-1")).exists()


# ------------------------------------------------------------------------------ rule 3: a run
@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_run_that_recorded_an_earlier_model_goes_on_with_opus(name: str) -> None:
    earlier = UNTIL_D153[name][0]
    assert RO.model_now(name, earlier) == OPUS
    assert RO.model_now(name, FABLE) == OPUS
    # a run that recorded a model the role was not moved from is not what the decisions moved
    for other in set(OH.NEW_ANSWER_MODELS) - {earlier, FABLE, OPUS}:
        assert RO.model_now(name, other) == other
        assert RO.run_model_at(name, other, BETWEEN) == other


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_run_takes_each_model_in_its_window(name: str) -> None:
    earlier = UNTIL_D153[name][0]
    assert RO.run_model_at(name, earlier, BEFORE) == earlier
    assert RO.run_model_at(name, earlier, BETWEEN) == FABLE
    assert RO.run_model_at(name, earlier, AFTER) == OPUS
    assert RO.run_model_at(name, FABLE, BETWEEN) == FABLE
    assert RO.run_model_at(name, FABLE, AFTER) == OPUS


def wave_before_d153(tmp_path: Path) -> Path:
    """A shorts-v1 run whose RUN.json fixed its roles before D153, as wave a2's does (every role of
    the card lane on Opus then): selected as any run, then recorded with the earlier models."""
    run = make_run(tmp_path, NAMES)
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    assert {entry["model"] for entry in record["roles"].values()} == {OPUS}
    for role, entry in record["roles"].items():
        entry["model"] = UNTIL_D153[role][0]
    R.write_json(run / "RUN.json", record)
    assert {entry["model"] for entry in R.run_roles(run).values()} == {"claude-opus-5-5"}
    return run


def wave_under_d153(tmp_path: Path) -> Path:
    """A shorts-v1 run selected between D153 and D157: every role recorded on Fable."""
    run = make_run(tmp_path, NAMES)
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    for entry in record["roles"].values():
        entry["model"] = FABLE
    R.write_json(run / "RUN.json", record)
    return run


def until_verify(run: Path, tmp_path: Path, model: str, at: str) -> Path:
    """Write, rate and check answered by `model` at `at`; `verify` exported."""
    step(run, tmp_path, "write", writes(NAMES), model=model, now=lambda: at)
    step(run, tmp_path, "rate", rates(run, NAMES), model=model, now=lambda: at)
    step(run, tmp_path, "check", passes(NAMES), model=model, now=lambda: at)
    handoff = tmp_path / "handoff-verify"
    assert R.export_stage(run, "verify", handoff)["questions"] == 4
    return handoff


def put_at(handoff: Path, stage: str, batch_id: str, label: str, text: str, role: str,
           model: str, at: str) -> None:  # fmt: skip
    OH.write_answer(
        handoff, batch_id=batch_id, stage=stage, label=label, text=text,
        answered_by=RO.answered_by(role, R.agent_name(batch_id)),
        model=OH.ANSWER_MODELS[model], now=lambda: at,
    )  # fmt: skip


def answer_verify(run: Path, handoff: Path, models: dict[str, tuple[str, str]]) -> None:
    """Each site's verification under the model and at the time `models` names for it."""
    record = R._round(run, "verify")
    assert record is not None
    answers = verifies(NAMES)
    for batch_id, members in record["batches"].items():
        for site_id in members:
            model, at = models[site_id]
            put_at(handoff, "verify", batch_id, site_id, answers[site_id], "card_web_verifier",
                   model, at)  # fmt: skip


class TestAWaveThatBeganBeforeD153:
    """Wave a2 (`wb-shorts-wave-a2-2026-10-24`), stage `verify`: about 250 answers stamped Opus,
    some stamped Fable under D153, and the questions still open when D157 came."""

    def test_the_open_batches_are_briefed_with_opus(self, tmp_path: Path) -> None:
        run = wave_before_d153(tmp_path)
        handoff = until_verify(run, tmp_path, OPUS, BEFORE)
        jobs = R.agent_jobs(run, handoff)
        assert {(job["role"], job["model"], job["effort"]) for job in jobs} == {
            ("card_web_verifier", OPUS, "high")
        }
        for job in jobs:
            assert (
                "**card_web_verifier**: your model is **claude-opus-5-5**, effort high"
                in (job["brief"])
            )
            assert "--role card_web_verifier --model claude-opus-5-5" in job["brief"]
            assert FABLE not in job["brief"]
            assert R.brief(run, handoff, job["batch_id"]) == job["brief"]
        assert R.role_now(run, "card_web_verifier") == {"model": OPUS, "effort": "high"}
        assert R.run_roles(run)["card_web_verifier"]["model"] == "claude-opus-5-5"  # as recorded

    def test_a_run_under_d153_is_briefed_with_opus(self, tmp_path: Path) -> None:
        run = wave_under_d153(tmp_path)
        assert R.role_now(run, "card_writer") == {"model": OPUS, "effort": "high"}
        assert R.run_roles(run)["card_writer"]["model"] == FABLE  # as recorded

    def test_a_round_answered_by_opus_then_fable_then_opus_imports(self, tmp_path: Path) -> None:
        """validate and import accept the mixed round; each card discloses exactly the models its
        own answers carry, and the write path takes every disclosure."""
        run = wave_before_d153(tmp_path)
        handoff = until_verify(run, tmp_path, OPUS, BEFORE)
        first, second, third, fourth = NAMES
        models = {
            sid(first): (OPUS, BEFORE),
            sid(second): (FABLE, BETWEEN),
            sid(third): (FABLE, BETWEEN),
            sid(fourth): (OPUS, AFTER),
        }
        answer_verify(run, handoff, models)
        assert OH.validate(handoff).ok
        result = R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)
        assert result["verdicts"] == {"VERIFIED": 4}
        R.outcomes(run)
        rows = {r["site_id"]: r for r in R.read_outcomes(run)}
        assert {r["status"] for r in rows.values()} == {R.ACCEPTED}
        for name in (first, fourth):
            prov = CP.validate(rows[sid(name)]["provenance"])
            assert set(prov["models"].values()) == {OH.OPUS_MODEL}
            assert prov["ai_system"] == M.AI_SYSTEM_CLAUDE_OPUS
        for name in (second, third):
            prov = CP.validate(rows[sid(name)]["provenance"])
            assert prov["models"] == {
                "write": OH.OPUS_MODEL,
                "rate": OH.OPUS_MODEL,
                "check": OH.OPUS_MODEL,
                "verify": OH.FABLE_MODEL,
            }
            assert prov["ai_system"] == M.AI_SYSTEM_CLAUDE_OPUS_FABLE
            written = MT.new_raw_data({}, rows[sid(name)])
            assert written is not None
            assert written[CP.CARD_PROVENANCE_KEY]["ai_system"] == M.AI_SYSTEM_CLAUDE_OPUS_FABLE

    @pytest.mark.parametrize(
        ("model", "at"),
        [
            ("claude-sonnet-5-5", BETWEEN),
            ("claude-haiku-5-5", AFTER),
            (OPUS, BETWEEN),  # Opus while the role stood on Fable
            (FABLE, AFTER),  # Fable after D157
        ],
    )
    def test_an_answer_out_of_its_window_stops_the_import(
        self, tmp_path: Path, model: str, at: str
    ) -> None:
        run = wave_before_d153(tmp_path)
        handoff = until_verify(run, tmp_path, OPUS, BEFORE)
        models = {sid(n): (OPUS, AFTER) for n in NAMES}
        models[sid(NAMES[0])] = (model, at)
        answer_verify(run, handoff, models)
        with pytest.raises(
            R.RunError, match="role card_web_verifier is recorded as claude-opus-5-5"
        ):
            R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)

    def test_a_run_that_begins_on_opus_takes_no_fable_answer(self, tmp_path: Path) -> None:
        """A run selected since D157 records Opus for every role and refuses a Fable answer."""
        run = make_run(tmp_path, NAMES)
        assert {entry["model"] for entry in R.run_roles(run).values()} == {OPUS}
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        record = R._round(run, "write")
        assert record is not None
        answers = writes(NAMES)
        for batch_id, members in record["batches"].items():
            for site_id in members:
                put_at(handoff, "write", batch_id, site_id, answers[site_id], "card_writer",
                       FABLE, AFTER)  # fmt: skip
        with pytest.raises(R.RunError, match="role card_writer is recorded as claude-opus-5-5"):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_card_only_opus_answered_discloses_opus_alone(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        step(run, tmp_path, "check", passes(NAMES))
        step(run, tmp_path, "verify", verifies(NAMES))
        R.outcomes(run)
        for row in R.read_outcomes(run):
            prov = CP.validate(row["provenance"])
            assert set(prov["models"].values()) == {OH.OPUS_MODEL}
            assert (
                prov["ai_system"]
                == M.AI_SYSTEM_CLAUDE_OPUS
                == (
                    "Claude Opus (Anthropic): anthropic/claude-opus-5-5 (Claude Code agent), "
                    "an-sites-remediation-2026-10"
                )
            )
            assert MT.new_raw_data({}, row) is not None


# ------------------------------------------------------------------------------ the other lanes
def _answer(role: str, stamp: str, at: str = AFTER, **over: Any) -> OH.Answer:
    fields = {
        "text": "x",
        "answered_by": f"{role}:agent-1",
        "answered_at": at,
        "model": stamp,
    }
    return OH.Answer(**{**fields, **over})


def test_lane_wc_briefs_opus_and_takes_each_answer_in_its_window(tmp_path: Path) -> None:
    """Lane WC reads role, model and agent family from the registry at every brief, so an open
    round (`defects-2026-10-02`) is briefed with Opus; its import takes the Opus answers given
    before D153, the Fable ones given under it and the Opus ones that finish it, and no other."""
    run, handoff = wc_run(tmp_path)
    text = WC.brief(run, handoff, "wc-0002")
    assert "You are Opus checker wc-0002" in text
    assert "--model claude-opus-5-5 --role fact_checker" in text
    assert "--answered-by opus-check-r1-wc-0002" in text
    assert FABLE not in text and "claude-sonnet-5-5" not in text
    for role in (WC.ROLE_CHECK, WC.ROLE_VERIFY, WC.ROLE_JUDGE, WC.ROLE_ADVERSARIAL):
        WC._require_role(_answer(role, OH.OPUS_MODEL, BEFORE), role_name=role, where="here")
        WC._require_role(_answer(role, OH.FABLE_MODEL, BETWEEN), role_name=role, where="here")
        WC._require_role(_answer(role, OH.OPUS_MODEL, AFTER), role_name=role, where="here")
        with pytest.raises(WC.WcRunError, match=f"role {role} is registered to {OPUS}"):
            WC._require_role(_answer(role, OH.SONNET_MODEL), role_name=role, where="here")
        with pytest.raises(WC.WcRunError, match=f"role {role} is registered to {OPUS}"):
            WC._require_role(_answer(role, OH.FABLE_MODEL), role_name=role, where="here")
        with pytest.raises(WC.WcRunError, match="answered by MiniMax"):
            WC._require_role(_answer(role, OH.MINIMAX_MODEL), role_name=role, where="here")


def test_the_enrichment_takes_its_writers_answers_in_their_windows() -> None:
    E.require_role(_answer(E.WRITER_ROLE, OH.SONNET_MODEL, BEFORE), E.WRITER_ROLE, "here")
    E.require_role(_answer(E.WRITER_ROLE, OH.FABLE_MODEL, BETWEEN), E.WRITER_ROLE, "here")
    E.require_role(_answer(E.WRITER_ROLE, OH.OPUS_MODEL, AFTER), E.WRITER_ROLE, "here")
    with pytest.raises(E.EnrichError, match="role enrich_writer is registered to"):
        E.require_role(_answer(E.WRITER_ROLE, OH.OPUS_MODEL, BEFORE), E.WRITER_ROLE, "here")


def test_the_identity_stages_take_each_answer_in_its_window() -> None:
    """The web verifier and the shared adversarial answered on Sonnet until D153, the pilot judge
    on Opus: each stage takes its role's earlier stamp before D153, Fable's under it, Opus's after
    D157, and still no other."""
    for role, earlier, other in (
        ("web_verifier", OH.SONNET_MODEL, OH.HAIKU_MODEL),
        ("adversarial", OH.SONNET_MODEL, OH.HAIKU_MODEL),
        ("pilot_judge", OH.OPUS_MODEL, OH.SONNET_MODEL),
    ):
        assert LR.role_problem(_answer(role, earlier, BEFORE), [role]) is None
        assert LR.role_problem(_answer(role, OH.FABLE_MODEL, BETWEEN), [role]) is None
        assert LR.role_problem(_answer(role, OH.OPUS_MODEL, AFTER), [role]) is None
        assert f"is registered to {OPUS}" in str(LR.role_problem(_answer(role, other), [role]))
        assert "MiniMax" in str(LR.role_problem(_answer(role, OH.MINIMAX_MODEL), [role]))
