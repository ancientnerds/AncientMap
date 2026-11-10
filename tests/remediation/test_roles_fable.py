"""Fable only: owner decisions D153 and D154 of 2026-11-10, on the role registry as it is.

D153: every role answers on `claude-fable-5-2` from now on; the answers recorded before keep their
stamp and stay valid. D154: no calibration is run on Fable - a role stands on it by the owner's
decision, with no verdict of its own. `roles.py` holds the three rules that follow (`owner_standing`,
`answer_problem`, `model_now`); every gate and every brief asks them. These tests prove the rules,
each gate that asks the first one, and a run that began before the decision going on with Fable.

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
    put,
    rates,
    sid,
    step,
    verifies,
    writes,
)
from tests.remediation.test_wc import _run as wc_run  # noqa: E402
from tests.remediation.wc_fixtures import wiki_cache  # noqa: E402,F401

FABLE = "claude-fable-5-2"
STANDING = "owner decision D153 (no calibration on claude-fable-5-2: D154)"
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
def test_every_role_is_registered_to_fable_at_the_effort_it_had() -> None:
    assert {name: (r.model, r.effort) for name, r in RO.ROLES.items()} == {
        name: (FABLE, effort) for name, (_, effort) in UNTIL_D153.items()
    }
    assert RO.FABLE == FABLE and (RO.FABLE_DECISION, RO.NO_CALIBRATION_DECISION) == ("D153", "D154")
    assert OH.ANSWER_MODELS[FABLE] == "anthropic/claude-fable-5-2 (Claude Code agent)"


def test_each_role_got_there_by_an_owner_move_of_its_own_under_d153() -> None:
    """One record per role, the last of its chain: from the model it stood on, to Fable, the effort
    unchanged, under D153 - and resting on no calibration (D154), which the reason says plainly."""
    moves = [m for m in RO.APPLIED_ESCALATIONS if m.get("decision") == "D153"]
    assert [m["role"] for m in moves] == list(RO.ROLES)  # every role, in the registry's order
    assert RO.APPLIED_ESCALATIONS[-len(moves) :] == tuple(moves)  # appended, nothing after them
    for move in moves:
        name = move["role"]
        assert RO.last_move(name) == move == RO.fable_move(name) == RO.owner_move(name, "D153")
        assert (move["kind"], move["to"]) == ("owner", FABLE)
        assert (move["from"], move["effort"]) == UNTIL_D153[name]
        assert move["evidence"] == ()
        assert "no calibration was run on Fable" in move["reason"] and "D154" in move["reason"]
        assert "only Fable 5.2" in move["reason"]
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, RO.ROLES)
    RO.check_settled_tier_moves(RO.SETTLED_TIER_MOVES, RO.APPLIED_ESCALATIONS, RO.ROLES)


def test_fable_is_on_no_tier_so_nothing_moves_a_role_up_from_it() -> None:
    with pytest.raises(RO.RoleError, match="'claude-fable-5-2' is on no tier"):
        RO.next_tier(FABLE)
    with pytest.raises(RO.RoleError, match="is on no tier"):
        RO.escalation("card_writer", calibration_id="cal-x", reason="failed")


def d153_move(**over: object) -> dict[str, object]:
    move: dict[str, object] = dict(RO.fable_move("operator") or {})
    move.update(over)
    return move


def test_a_d153_move_rests_on_no_calibration_and_may_not_name_one() -> None:
    """D154: no calibration is run on Fable. The move's evidence is empty and must be - naming one
    would claim a measurement nobody made - and a move under D153 ends at Fable. Every other owner
    move still needs the calibrations it rests on."""
    roles = dict(RO.ROLES)
    RO.check_applied_escalations((d153_move(),), roles)
    with pytest.raises(RO.RoleError, match="rests on no calibration .D154"):
        RO.check_applied_escalations((d153_move(evidence=("scripted_dry_run",)),), roles)
    with pytest.raises(RO.RoleError, match="a move under D153 ends at claude-fable-5-2"):
        RO.check_applied_escalations((d153_move(to="claude-opus-5-5"),), roles)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations((d153_move(decision="D36"),), roles)  # no evidence, not D153
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations((d153_move(evidence=None),), roles)
    with pytest.raises(RO.RoleError, match="carries exactly"):
        RO.check_applied_escalations((d153_move(evidence=("",)),), roles)


def test_a_registry_edit_without_its_d153_move_is_refused() -> None:
    """The ROLES edit and its record go together, as for every move before: Fable in the registry
    without the D153 move, and the move without the edit, are both refused at import."""
    without = tuple(
        m
        for m in RO.APPLIED_ESCALATIONS
        if not (m["role"] == "card_writer" and m.get("decision") == "D153")
    )
    with pytest.raises(RO.RoleError, match="card_writer is registered to claude-fable-5-2"):
        RO.check_applied_escalations(without, RO.ROLES)
    unmoved = {**RO.ROLES, "operator": RO.Role("operator", "claude-haiku-5-5", "low", "x")}
    with pytest.raises(RO.RoleError, match="operator is registered to claude-haiku-5-5"):
        RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, unmoved)
    wrong_start = (*without, d153_move(role="card_writer", **{"from": "claude-sonnet-5-5"}))
    with pytest.raises(RO.RoleError, match="does not start where the last one ended"):
        RO.check_applied_escalations(wrong_start, RO.ROLES)


def test_a_settlement_is_held_to_where_its_roles_stood_until_d153() -> None:
    """The settled tier moves record the tier chain, which D153 ended: `adversarial` stayed on
    Sonnet and `card_adversarial` took its card context on Opus. A D153 move that started somewhere
    else would say the settled role had moved after all."""
    moved = tuple(
        {**m, "from": "claude-opus-5-5"}
        if m["role"] == "adversarial" and m.get("decision") == "D153"
        else m
        for m in RO.APPLIED_ESCALATIONS
    )
    with pytest.raises(RO.RoleError, match="adversarial stood at claude-opus-5-5 until D153"):
        RO.check_settled_tier_moves(RO.SETTLED_TIER_MOVES, moved, RO.ROLES)


# ------------------------------------------------------------------------------ rule 1: standing
@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_role_on_fable_stands_by_the_owners_decision_in_words(name: str) -> None:
    """Owner standing without a verdict: the record names the decision and never says `passed`."""
    record = RO.owner_standing(name)
    assert record == {
        "role": name,
        "model": FABLE,
        "standing": STANDING,
        "owner_decision": "D153",
    }
    assert record["standing"] == RO.OWNER_STANDING
    assert CC.PASSED not in record.values() and CC.RELEASED not in record["standing"]
    assert "calibration_id" not in record


def test_an_unregistered_role_stands_by_nothing() -> None:
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.owner_standing("writer")
    with pytest.raises(RO.RoleError, match="no role 'writer'"):
        RO.model_now("writer", "claude-opus-5-5")


def test_a_role_moved_again_after_d153_stands_by_its_calibration_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decision covers a role only while its D153 move is its last one: a later owner move puts
    the gates back to asking for a verdict, and the earlier stamp is no longer the role's."""
    later = {
        "kind": "owner",
        "role": "card_writer",
        "from": FABLE,
        "to": "claude-opus-5-5",
        "effort": "high",
        "decision": "D199",
        "reason": "a later owner move",
        "evidence": ("cal-later",),
    }
    roles = {**RO.ROLES, "card_writer": RO.Role("card_writer", "claude-opus-5-5", "high", "x")}
    monkeypatch.setattr(RO, "ROLES", roles)
    monkeypatch.setattr(RO, "APPLIED_ESCALATIONS", (*RO.APPLIED_ESCALATIONS, later))
    RO.check_applied_escalations(RO.APPLIED_ESCALATIONS, RO.ROLES)
    assert RO.fable_move("card_writer") is None and RO.owner_standing("card_writer") is None
    assert RO.owner_standing("hook_rater") is not None  # the others are untouched
    assert RO.model_now("card_writer", "claude-opus-5-5") == "claude-opus-5-5"
    assert RO.answer_problem("card_writer:w", OH.FABLE_MODEL) is not None
    with pytest.raises(CC.CalibrationError, match="no passing or released verdict"):
        CC.require_passed(Path("no-such-root"), [("card_writer", "all")])


@pytest.mark.usefixtures("registry_until_d153")
def test_no_role_stood_by_an_owner_decision_before_d153() -> None:
    assert all(RO.owner_standing(name) is None for name in RO.ROLES)
    assert all(RO.fable_move(name) is None for name in RO.ROLES)


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
            "owner_decision": "D153",
        },
        {
            "role": "adversarial",
            "comparison": "adv-known-truth",
            "standing": STANDING,
            "owner_decision": "D153",
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
    assert all(line["owner_decision"] == "D153" and line["model"] == FABLE for line in lines)


def test_the_identity_gates_name_the_decision_and_ask_no_calibration_id(tmp_path: Path) -> None:
    """`identity/rounds.require_calibration` (run.py import) and `label_rounds.check_calibrated`
    (the duplicate and parent judges): no id named, no verdict read, no time an answer could
    precede."""
    verdict = IR.require_calibration(tmp_path, None, "web_verifier", "scope-window-web")
    assert verdict == {
        "role": "web_verifier",
        "model": FABLE,
        "standing": STANDING,
        "owner_decision": "D153",
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
    """The gates are not gone: on a registry without the D153 moves each one asks its calibration
    exactly as before and refuses an empty calibration root."""
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
def test_an_answer_recorded_before_the_move_keeps_its_stamp_and_stays_valid(name: str) -> None:
    """D153: "answers recorded earlier keep their stamp and stay valid". The role's own earlier
    model, and Fable - no other stamp, whatever model it names."""
    earlier = OH.ANSWER_MODELS[UNTIL_D153[name][0]]
    by = f"{name}:agent-1"
    assert RO.answer_problem(by, earlier) is None
    assert RO.answer_problem(by, OH.FABLE_MODEL) is None
    for stamp in set(OH.ANSWER_MODELS.values()) - {earlier, OH.FABLE_MODEL}:
        problem = RO.answer_problem(by, stamp)
        assert problem is not None and f"role {name} is registered to {FABLE}" in problem
        assert stamp in problem
    assert RO.answer_problem(by, UNTIL_D153[name][0]) is not None  # the bare id is no stamp


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_new_answer_of_a_role_can_only_be_fables(name: str) -> None:
    """What makes an earlier stamp an earlier answer: the recorder's check takes Fable only, and
    the strict stamp check (a calibration's fresh answers) takes Fable's stamp only."""
    RO.require_model(name, FABLE)
    RO.require_stamp(name, OH.FABLE_MODEL)
    earlier = UNTIL_D153[name][0]
    with pytest.raises(RO.RoleError, match=f"role {name} is registered to {FABLE}, not {earlier}"):
        RO.require_model(name, earlier)
    with pytest.raises(RO.RoleError, match=f"role {name} is registered to {FABLE}"):
        RO.require_stamp(name, OH.ANSWER_MODELS[earlier])


def _answer_argv(root: Path, text: Path, *extra: str) -> list[str]:
    return [
        sys.executable, str(REMEDIATION / "opus_handoff.py"), "answer", "--dir", str(root),
        "--batch-id", "verify-001", "--stage", "verify", "--label", "site-1",
        "--answered-by", "teaser-verify-001", "--text-file", str(text), *extra,
    ]  # fmt: skip


def _recorder(tmp_path: Path) -> tuple[Path, Path]:
    OH.export(tmp_path, batch_id="verify-001", stage="verify", label="site-1", field=None,
              prompt="Is it so?\n")  # fmt: skip
    text = tmp_path / "a.txt"
    text.write_text("VERDICT: VERIFIED\n", encoding="utf-8")
    return tmp_path, text


def test_the_recorder_takes_a_fable_answer_of_the_card_verifier(tmp_path: Path) -> None:
    """The command the briefs of wave a2's open verify batches print."""
    root, text = _recorder(tmp_path)
    done = subprocess.run(
        _answer_argv(root, text, "--model", FABLE, "--role", "card_web_verifier"),
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    stored = json.loads(
        (root / OH.answer_relpath("verify-001", "verify", "site-1")).read_text("utf-8")
    )
    assert stored["model"] == OH.FABLE_MODEL
    assert stored["answered_by"] == "card_web_verifier:teaser-verify-001"
    assert RO.answer_problem(stored["answered_by"], stored["model"]) is None
    assert OH.validate(root).ok


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"])
def test_the_recorder_refuses_a_new_answer_of_a_role_on_any_earlier_model(
    tmp_path: Path, model: str
) -> None:
    """A wrong-model new answer: Opus was this role's model until D153, and is refused like the
    others - nothing is written."""
    root, text = _recorder(tmp_path)
    refused = subprocess.run(
        _answer_argv(root, text, "--model", model, "--role", "card_web_verifier"),
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    assert refused.returncode == 2
    assert f"role card_web_verifier is registered to {FABLE}, not {model}" in refused.stderr
    assert not (root / OH.answer_relpath("verify-001", "verify", "site-1")).exists()


# ------------------------------------------------------------------------------ rule 3: a run
@pytest.mark.parametrize("name", ROLE_NAMES)
def test_a_run_that_recorded_the_roles_earlier_model_goes_on_with_fable(name: str) -> None:
    earlier = UNTIL_D153[name][0]
    assert RO.model_now(name, earlier) == FABLE
    assert RO.model_now(name, FABLE) == FABLE
    # a run that recorded a model the role was not moved from is not what D153 moved
    for other in set(OH.NEW_ANSWER_MODELS) - {earlier, FABLE}:
        assert RO.model_now(name, other) == other


def wave_before_d153(tmp_path: Path) -> Path:
    """A shorts-v1 run whose RUN.json fixed its roles before D153, as wave a2's does (every role of
    the card lane on Opus then): selected as any run, then recorded with the earlier models."""
    run = make_run(tmp_path, NAMES)
    record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
    assert {entry["model"] for entry in record["roles"].values()} == {FABLE}
    for role, entry in record["roles"].items():
        entry["model"] = UNTIL_D153[role][0]
    R.write_json(run / "RUN.json", record)
    assert {entry["model"] for entry in R.run_roles(run).values()} == {"claude-opus-5-5"}
    return run


def opus_until_verify(run: Path, tmp_path: Path) -> Path:
    """Write, rate and check answered by Opus, as before the decision; `verify` exported."""
    opus = "claude-opus-5-5"
    step(run, tmp_path, "write", writes(NAMES), model=opus)
    step(run, tmp_path, "rate", rates(run, NAMES), model=opus)
    step(run, tmp_path, "check", passes(NAMES), model=opus)
    handoff = tmp_path / "handoff-verify"
    assert R.export_stage(run, "verify", handoff)["questions"] == 4
    return handoff


def answer_verify(run: Path, handoff: Path, models: dict[str, str]) -> None:
    """Each site's verification under the model `models` names for it."""
    record = R._round(run, "verify")
    assert record is not None
    answers = verifies(NAMES)
    for batch_id, members in record["batches"].items():
        for site_id in members:
            put(handoff, "verify", batch_id, site_id, answers[site_id], "card_web_verifier",
                models[site_id])  # fmt: skip


class TestAWaveThatBeganBeforeD153:
    """Wave a2 (`wb-shorts-wave-a2-2026-10-24`), stage `verify`: about 250 answers stamped Opus and
    about 40 questions open on the evening of D153."""

    def test_the_open_batches_are_briefed_with_fable(self, tmp_path: Path) -> None:
        run = wave_before_d153(tmp_path)
        handoff = opus_until_verify(run, tmp_path)
        jobs = R.agent_jobs(run, handoff)
        assert {(job["role"], job["model"], job["effort"]) for job in jobs} == {
            ("card_web_verifier", FABLE, "high")
        }
        for job in jobs:
            assert (
                "**card_web_verifier**: your model is **claude-fable-5-2**, effort high"
                in (job["brief"])
            )
            assert "--role card_web_verifier --model claude-fable-5-2" in job["brief"]
            assert "claude-opus-5-5" not in job["brief"]
            assert R.brief(run, handoff, job["batch_id"]) == job["brief"]
        assert R.role_now(run, "card_web_verifier") == {"model": FABLE, "effort": "high"}
        assert R.run_roles(run)["card_web_verifier"]["model"] == "claude-opus-5-5"  # as recorded

    def test_a_round_answered_partly_by_opus_and_partly_by_fable_imports(
        self, tmp_path: Path
    ) -> None:
        """validate and import accept the mixed round; each card discloses exactly the models its
        own answers carry, and the write path takes both disclosures."""
        run = wave_before_d153(tmp_path)
        handoff = opus_until_verify(run, tmp_path)
        before, after = NAMES[:2], NAMES[2:]
        models = {
            **{sid(n): "claude-opus-5-5" for n in before},
            **{sid(n): FABLE for n in after},
        }
        answer_verify(run, handoff, models)
        assert OH.validate(handoff).ok
        result = R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)
        assert result["verdicts"] == {"VERIFIED": 4}
        R.outcomes(run)
        rows = {r["site_id"]: r for r in R.read_outcomes(run)}
        assert {r["status"] for r in rows.values()} == {R.ACCEPTED}
        for name in before:
            prov = CP.validate(rows[sid(name)]["provenance"])
            assert set(prov["models"].values()) == {OH.OPUS_MODEL}
            assert prov["ai_system"] == M.AI_SYSTEM_CLAUDE_OPUS
        for name in after:
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

    @pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5"])
    def test_an_answer_of_a_third_model_stops_the_import(self, tmp_path: Path, model: str) -> None:
        run = wave_before_d153(tmp_path)
        handoff = opus_until_verify(run, tmp_path)
        models = {sid(n): FABLE for n in NAMES}
        models[sid(NAMES[0])] = model
        answer_verify(run, handoff, models)
        with pytest.raises(
            R.RunError, match="role card_web_verifier is recorded as claude-opus-5-5"
        ):
            R.import_stage(run, "verify", fit=T.fit, client=judge_client(), pace=0)

    def test_a_run_that_begins_on_fable_takes_no_earlier_stamp(self, tmp_path: Path) -> None:
        """Only the run that recorded Opus keeps taking Opus: a run selected since D153 records
        Fable for every role and refuses an Opus-stamped answer."""
        run = make_run(tmp_path, NAMES)
        assert {entry["model"] for entry in R.run_roles(run).values()} == {FABLE}
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        record = R._round(run, "write")
        assert record is not None
        answers = writes(NAMES)
        for batch_id, members in record["batches"].items():
            for site_id in members:
                put(handoff, "write", batch_id, site_id, answers[site_id], "card_writer",
                    "claude-opus-5-5")  # fmt: skip
        with pytest.raises(R.RunError, match="role card_writer is recorded as claude-fable-5-2"):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_card_only_fable_answered_discloses_fable_alone(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, NAMES)
        step(run, tmp_path, "write", writes(NAMES))
        step(run, tmp_path, "rate", rates(run, NAMES))
        step(run, tmp_path, "check", passes(NAMES))
        step(run, tmp_path, "verify", verifies(NAMES))
        R.outcomes(run)
        for row in R.read_outcomes(run):
            prov = CP.validate(row["provenance"])
            assert set(prov["models"].values()) == {OH.FABLE_MODEL}
            assert (
                prov["ai_system"]
                == M.AI_SYSTEM_CLAUDE_FABLE
                == (
                    "Claude Fable (Anthropic): anthropic/claude-fable-5-2 (Claude Code agent), "
                    "an-sites-remediation-2026-11"
                )
            )
            assert MT.new_raw_data({}, row) is not None


# ------------------------------------------------------------------------------ the other lanes
def _answer(role: str, stamp: str, **over: Any) -> OH.Answer:
    fields = {
        "text": "x",
        "answered_by": f"{role}:agent-1",
        "answered_at": "2026-11-10T20:00:00+00:00",
        "model": stamp,
    }
    return OH.Answer(**{**fields, **over})


def test_lane_wc_briefs_fable_and_takes_the_answers_its_open_rounds_hold(
    tmp_path: Path,
) -> None:
    """Lane WC reads role, model and agent family from the registry at every brief, so an open
    round (`defects-2026-10-02`) is briefed with Fable; its import takes the Opus answers the
    round already holds and the Fable ones that finish it, and no third model's."""
    run, handoff = wc_run(tmp_path)
    text = WC.brief(run, handoff, "wc-0002")
    assert "You are Fable checker wc-0002" in text
    assert "--model claude-fable-5-2 --role fact_checker" in text
    assert "--answered-by fable-check-r1-wc-0002" in text
    assert "claude-opus-5-5" not in text and "claude-sonnet-5-5" not in text
    for role in (WC.ROLE_CHECK, WC.ROLE_VERIFY, WC.ROLE_JUDGE, WC.ROLE_ADVERSARIAL):
        WC._require_role(_answer(role, OH.OPUS_MODEL), role_name=role, where="here")
        WC._require_role(_answer(role, OH.FABLE_MODEL), role_name=role, where="here")
        with pytest.raises(WC.WcRunError, match=f"role {role} is registered to {FABLE}"):
            WC._require_role(_answer(role, OH.SONNET_MODEL), role_name=role, where="here")
        with pytest.raises(WC.WcRunError, match="answered by MiniMax"):
            WC._require_role(_answer(role, OH.MINIMAX_MODEL), role_name=role, where="here")


def test_the_enrichment_takes_its_writers_earlier_answers_and_fables() -> None:
    E.require_role(_answer(E.WRITER_ROLE, OH.SONNET_MODEL), E.WRITER_ROLE, "here")
    E.require_role(_answer(E.WRITER_ROLE, OH.FABLE_MODEL), E.WRITER_ROLE, "here")
    with pytest.raises(E.EnrichError, match="role enrich_writer is registered to"):
        E.require_role(_answer(E.WRITER_ROLE, OH.OPUS_MODEL), E.WRITER_ROLE, "here")


def test_the_identity_stages_take_the_earlier_answers_and_fables() -> None:
    """The web verifier and the shared adversarial answered on Sonnet until D153, the pilot judge
    on Opus: each stage takes its role's earlier stamp and Fable's, and still no other."""
    for role, earlier, other in (
        ("web_verifier", OH.SONNET_MODEL, OH.OPUS_MODEL),
        ("adversarial", OH.SONNET_MODEL, OH.HAIKU_MODEL),
        ("pilot_judge", OH.OPUS_MODEL, OH.SONNET_MODEL),
    ):
        assert LR.role_problem(_answer(role, earlier), [role]) is None
        assert LR.role_problem(_answer(role, OH.FABLE_MODEL), [role]) is None
        assert f"is registered to {FABLE}" in str(LR.role_problem(_answer(role, other), [role]))
        assert "MiniMax" in str(LR.role_problem(_answer(role, OH.MINIMAX_MODEL), [role]))
