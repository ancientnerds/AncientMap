"""The roles of the final repair: which Claude model makes which judgement, at which effort.

Owner decision D6 of 2026-10-08 (`output/remediation/OWNER_DECISIONS_2026-10-08.md`): Claude only,
"balanced". Every judgement is made by a **role**, a role is one registered model at one effort, and
the answer stamp always names the model that really wrote it (`opus_handoff.ANSWER_MODELS`). The
model census of 2026-10-01 found 8,471 answers stamped Opus that Sonnet had written, so a role never
trusts a self-declared stamp: `opus_handoff.py answer --role R` refuses a `--model` that is not
`R`'s registered model, and an importer asks `require_stamp` / `answer_problem` before it counts an
answer as the role's.

Every role passes a calibration against already-judged cases before its first answer
(`calibrate_claude.py`): the threshold is sealed in `THRESHOLDS.json` before the run, which is why
`Role.threshold` here is `None` - the registry holds no number a run could move. A role that fails
moves up one tier (Haiku to Sonnet to Opus; `next_tier`), and the move is a record
(`escalation`), never a silent edit of this file: the move is copied into `APPLIED_ESCALATIONS` with
the commit that edits `ROLES`, and the registry is held to those records when the module is imported.

An owner decision can move a role in either direction (D36 of 2026-10-09 moved seven roles from Opus
down to Sonnet to save the weekly quota). That is a record too, an **owner move**: an entry of
`APPLIED_ESCALATIONS` with `"kind": "owner"` naming the decision, the models, the effort the role has
afterwards, the reason and the calibrations it rests on. The registry is held to the chain of tier
moves and owner moves in order. A calibration verdict that failed with a tier move can be released
under such a decision (`calibrate_claude.py release --owner-decision`) while the role is registered
to the model that verdict was made on.

The two code roles have no pool of cases (`calibration_set` is `None`): the gates and the review
judge them.

A **candidate model** trial (`candidate_model`) calibrates a role with another model without touching
the registry. Its seal binds the digest of the entry the role would have with the candidate
(`role_sha256(name, model=...)`), so the verdict stands for the role only after an owner move has
registered that model: until then the digest does not match the registry and every gate refuses it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import opus_handoff as OH

#: Effort levels the harness offers a role.
EFFORTS = frozenset({"low", "medium", "high", "xhigh"})
#: Model id -> the model id one tier up. Opus has none.
ESCALATION: Mapping[str, str] = MappingProxyType(
    {
        "claude-haiku-5-5": "claude-sonnet-5-5",
        "claude-sonnet-5-5": "claude-opus-5-5",
    }
)


class RoleError(ValueError):
    """A role that is not registered, or an answer that is not the role's. Never guessed."""


@dataclass(frozen=True)
class Role:
    """One role of owner decision D6.

    `model` is a key of `opus_handoff.ANSWER_MODELS` and a member of `NEW_ANSWER_MODELS`;
    `calibration_set` names the pool of already-judged cases the role is measured on (`None`: no
    pool, see the module docstring); `threshold` is the sealed agreement threshold, `None` until a
    seal exists (it is read from the seal, never edited here)."""

    name: str
    model: str
    effort: str
    calibration_set: str | None
    threshold: float | None = None

    def __post_init__(self) -> None:
        if self.model not in OH.NEW_ANSWER_MODELS:
            raise RoleError(f"{self.name}: {self.model!r} is not a model a new answer may name")
        if self.effort not in EFFORTS:
            raise RoleError(f"{self.name}: effort {self.effort!r} is not one of {sorted(EFFORTS)}")


def _registry(*roles: Role) -> Mapping[str, Role]:
    return MappingProxyType({role.name: role for role in roles})


#: D6, role by role. The calibration sets are named in `output/remediation/final-2026-10-08/plans/infra.md`
#: 3.1c; `calibrate_claude.py seal` binds a role to the concrete cases of its pool.
ROLES: Mapping[str, Role] = _registry(
    # Sonnet since owner decision D36 of 2026-10-09 (`APPLIED_ESCALATIONS`, owner moves): the weekly
    # quota stood at 69 % after one day, and the calibrations measured no Opus advantage. Where a
    # role stood on Opus before that, the tier move up is the earlier record of its chain.
    Role("card_writer", "claude-sonnet-5-5", "high", "wb_cards_accepted"),
    # Effort xhigh from 2026-10-09 (at medium it failed teaser-2026-10-09, hook_pairs ordered right
    # 0.7902 of a required 1.0), medium again on Sonnet under D36: it is calibrated again on Sonnet.
    Role("hook_rater", "claude-sonnet-5-5", "medium", "design_run_hand_drawn_60"),
    # Sonnet failed teaser-2026-10-09b (tier move to Opus), Opus showed no gain in teaser-2026-10-09c;
    # D36 puts the role back on Sonnet, and the failed 09b verdict is released under that decision.
    Role("fact_checker", "claude-sonnet-5-5", "high", "wb_check_verify_opus"),
    Role("web_verifier", "claude-sonnet-5-5", "high", "wb_check_verify_opus"),
    # The card lane's own checkers. Owner decision D40 (after teaser-2026-10-10, in which no Sonnet
    # checker passed and the Haiku trial was weaker) put the card checks on Opus; D45 (2026-10-17)
    # scoped it to the card lane, so `fact_checker` (lane WC) and `web_verifier` (identity, lane E,
    # image identity) stay on Sonnet. New roles, not moves: they are calibrated before first use.
    Role("card_fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    Role("card_web_verifier", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # Sonnet failed fr-general-001 at 0.8636 (tier move to Opus); Opus reached 0.871 in
    # fr-general-002; D36 puts the role back on Sonnet under a release of fr-general-001.
    Role("field_researcher", "claude-sonnet-5-5", "high", "wd1_wd3_rounds_and_bp_set"),
    # The description writer of lane E (`wc/prompts_enrich.py`). It rode on `field_researcher` until
    # that role moved to Opus: the lane's writing was never measured on Opus and stays on Sonnet,
    # under a calibration set of its own, sealed as `enrich-writer`.
    Role("enrich_writer", "claude-sonnet-5-5", "high", "enrich-writer"),
    # D36: it re-checks every wd5 write and every card, so it is calibrated on Sonnet before use.
    Role("adversarial", "claude-sonnet-5-5", "high", "opus_audit_934"),
    Role("image_prefilter", "claude-haiku-5-5", "low", "image_kind_135"),
    Role("image_depicts", "claude-sonnet-5-5", "medium", "gallery_audit_calibration_opus"),
    Role("code_builder", "claude-sonnet-5-5", "high", None),
    Role("code_review", "claude-sonnet-5-5", "high", None),
    Role("pilot_judge", "claude-opus-5-5", "xhigh", "canaries_10"),
    Role("operator", "claude-haiku-5-5", "low", "scripted_dry_run"),
)


#: The moves applied to `ROLES`, oldest first: tier moves and owner moves in one chain. A tier move
#: is a record: the dict `escalation()` returns for the failed verdict (`verdicts/<calibration_id>.json`
#: of the calibration root). An owner move (`"kind": "owner"`, see `owner_move`) is an owner decision
#: that moved a role in either direction. Both are copied here when the `ROLES` edit is committed, so
#: the edit never stands without its calibration, its decision and its reason.
#: `check_applied_escalations` holds the registry to them at import.
OWNER_KIND = "owner"
#: The calibrations owner decision D36 rests on: Sonnet against Opus on the same cases.
D36_EVIDENCE = (
    "fr-general-001",
    "fr-general-002",
    "fr-bp-001",
    "fr-bp-002",
    "teaser-2026-10-09b",
    "teaser-2026-10-09c",
)


def _d36_move(role_name: str, effort: str, why: str) -> Mapping[str, Any]:
    """One owner move of decision D36 (2026-10-09): the role goes from Opus to Sonnet."""
    return MappingProxyType(
        {
            "kind": OWNER_KIND,
            "role": role_name,
            "from": "claude-opus-5-5",
            "to": "claude-sonnet-5-5",
            "effort": effort,
            "decision": "D36",
            "reason": f"weekly Claude quota at 69 % after one day (owner, 2026-10-09): {why}",
            "evidence": D36_EVIDENCE,
        }
    )


APPLIED_ESCALATIONS: tuple[Mapping[str, Any], ...] = (
    MappingProxyType(
        {
            "role": "field_researcher",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "fr-general-001",
            "reason": "agreement 0.8636 is below the sealed threshold 0.9",
        }
    ),
    MappingProxyType(
        {
            "role": "fact_checker",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-09b",
            "reason": "failed: checker_agreement, checker_fail_again, checker_good",
        }
    ),
    MappingProxyType(
        {
            "role": "web_verifier",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-09b",
            "reason": "failed: verifier_verified",
        }
    ),
    _d36_move(
        "field_researcher",
        "high",
        "Sonnet 0.8636 against Opus 0.871 on the general pool (fr-general-001, fr-general-002), "
        "Sonnet PASS 0.92 against Opus 0.88 on the BP pool (fr-bp-001, fr-bp-002), 0 false sources",
    ),
    _d36_move(
        "fact_checker",
        "high",
        "the checker failed the same sets on Sonnet and on Opus (teaser-2026-10-09b, "
        "teaser-2026-10-09c: checker_fail_again 9/30, checker_defects 30/30 for both)",
    ),
    _d36_move(
        "web_verifier",
        "high",
        "verifier_verified failed on Sonnet and on Opus (teaser-2026-10-09b, teaser-2026-10-09c)",
    ),
    _d36_move(
        "card_writer",
        "high",
        "no Opus advantage measured in the card lane's checks; the writer is calibrated on its "
        "pilot run before its first answer",
    ),
    _d36_move(
        "hook_rater",
        "medium",
        "no Opus advantage measured; the hook rater is calibrated again on Sonnet before use",
    ),
    _d36_move(
        "adversarial",
        "high",
        "it re-checks every wd5 write and every card, so it is no small spot check; it is "
        "calibrated again on Sonnet before use",
    ),
    _d36_move(
        "code_review",
        "high",
        "a role without a pool of cases: the gates judge the code, the review runs on Sonnet",
    ),
)
_ESCALATION_KEYS = frozenset({"role", "from", "to", "calibration_id", "reason"})
_OWNER_KEYS = frozenset({"kind", "role", "from", "to", "effort", "decision", "reason", "evidence"})
_DECISION = re.compile(r"D\d+[a-z]?")


def _check_owner_move(move: Mapping[str, Any]) -> None:
    """An owner move carries exactly `_OWNER_KEYS`: a decision id, two different registered models,
    a known effort, a reason and at least one calibration it rests on - all non-blank."""
    texts = {k: v for k, v in move.items() if k != "evidence"}
    evidence = move.get("evidence")
    if (
        set(move) != _OWNER_KEYS
        or not all(isinstance(v, str) and v.strip() for v in texts.values())
        or not isinstance(evidence, tuple | list)
        or not evidence
        or not all(isinstance(e, str) and e.strip() for e in evidence)
    ):
        raise RoleError(f"an owner move carries exactly {sorted(_OWNER_KEYS)}: {dict(move)}")
    if not _DECISION.fullmatch(move["decision"]):
        raise RoleError(f"{move['role']}: {move['decision']!r} is not an owner decision id (D36)")
    for end in ("from", "to"):
        if move[end] not in OH.NEW_ANSWER_MODELS:
            raise RoleError(
                f"{move['role']}: {move[end]!r} is not a model a role may be registered to"
            )
    if move["from"] == move["to"]:
        raise RoleError(
            f"{move['role']}: an owner move from {move['from']} to itself moves nothing"
        )
    if move["effort"] not in EFFORTS:
        raise RoleError(
            f"{move['role']}: effort {move['effort']!r} is not one of {sorted(EFFORTS)}"
        )


def check_applied_escalations(
    moves: tuple[Mapping[str, Any], ...], roles: Mapping[str, Role]
) -> None:
    """Refuse a record of `moves` that is neither a one-tier move of a registered role with its
    calibration and reason nor an owner move with its decision, a chain that does not join (each
    move starts where the last one - tier or owner - ended), and a registry that is not where the
    last move of its role ended (the model, and after an owner move the effort too)."""
    ended: dict[str, str] = {}
    effort: dict[str, str] = {}
    for move in moves:
        owner = move.get("kind") == OWNER_KIND
        if owner:
            _check_owner_move(move)
        elif set(move) != _ESCALATION_KEYS or not all(str(v).strip() for v in move.values()):
            raise RoleError(
                f"an applied escalation carries exactly {sorted(_ESCALATION_KEYS)}: {dict(move)}"
            )
        name = move["role"]
        if name not in roles:
            raise RoleError(f"an applied escalation names the unregistered role {name!r}")
        if move["from"] != ended.get(name, move["from"]):
            raise RoleError(
                f"{name}: the move from {move['from']} does not start where the last one ended"
            )
        if not owner and move["to"] != next_tier(move["from"]):
            raise RoleError(f"{name}: {move['from']} to {move['to']} is not one tier up")
        ended[name] = move["to"]
        if owner:
            effort[name] = move["effort"]
    for name, model in ended.items():
        if roles[name].model != model:
            raise RoleError(
                f"{name} is registered to {roles[name].model}, but its applied moves end at {model}"
            )
    for name, level in effort.items():
        if roles[name].effort != level:
            raise RoleError(
                f"{name} is registered at effort {roles[name].effort}, but its last owner move "
                f"ends at {level}"
            )


def owner_move(name: str, decision: str) -> Mapping[str, Any] | None:
    """The last applied owner move of role `name` that names `decision`, or `None`."""
    found = [
        m
        for m in APPLIED_ESCALATIONS
        if m.get("kind") == OWNER_KIND and m["role"] == name and m["decision"] == decision
    ]
    return found[-1] if found else None


def last_move(name: str) -> Mapping[str, Any] | None:
    """The last applied move (tier or owner) of role `name`, or `None` for a role never moved."""
    found = [m for m in APPLIED_ESCALATIONS if m["role"] == name]
    return found[-1] if found else None


def require_owner_move(
    name: str, decision: str, *, model: str, calibration_id: str
) -> Mapping[str, Any]:
    """The owner move that lets a failed verdict of `calibration_id`, made on `model`, stand under
    `decision`: the role is registered to `model` now (the owner kept that tier), an applied owner
    move names the decision and ends at that model, and it lists the calibration among its evidence.
    `RoleError` naming what is missing otherwise."""
    entry = role(name)
    move = owner_move(name, decision)
    if move is None:
        raise RoleError(f"no applied owner move of role {name} names decision {decision}")
    if entry.model != model:
        raise RoleError(
            f"role {name} is registered to {entry.model}, not {model}: an owner decision releases "
            "only a verdict of the model the owner kept"
        )
    if move["to"] != model:
        raise RoleError(
            f"the owner move of {name} under {decision} ends at {move['to']}, not {model}"
        )
    if calibration_id not in move["evidence"]:
        raise RoleError(
            f"the owner move of {name} under {decision} does not rest on {calibration_id} "
            f"(its evidence: {list(move['evidence'])})"
        )
    return move


def role(name: str) -> Role:
    """The registered role, or `RoleError` - there is no default role."""
    if name not in ROLES:
        raise RoleError(f"no role {name!r}: the roles are {sorted(ROLES)}")
    return ROLES[name]


def require_model(name: str, model_id: str) -> None:
    """Refuse a model id (as `answer --model` names it) that is not the role's registered model."""
    registered = role(name).model
    if model_id != registered:
        raise RoleError(
            f"role {name} is registered to {registered}, not {model_id}: the answer would carry "
            "a model that is not the role's"
        )


def require_stamp(name: str, stamp: str) -> None:
    """Refuse an answer stamp that is not the stamp of the role's registered model."""
    registered = role(name).model
    expected = OH.ANSWER_MODELS[registered]
    if stamp != expected:
        raise RoleError(
            f"role {name} is registered to {registered} ({expected!r}), but the answer is "
            f"stamped {stamp!r}"
        )


def answered_by(name: str, agent: str) -> str:
    """`answered_by` as `answer --role` records it: `<role>:<agent>`. The agent is one plain name,
    so the role can always be read back with `role_of`."""
    role(name)
    if not agent.strip() or ":" in agent or agent != agent.strip():
        raise RoleError(f"the agent {agent!r} is not one plain name (no colon, no blank)")
    return f"{name}:{agent}"


def role_of(answered_by_value: str) -> str | None:
    """The registered role an `answered_by` names (`<role>:<agent>`), or `None` when it names none
    (an answer recorded before the registry)."""
    head, separator, _ = answered_by_value.partition(":")
    return head if separator and head in ROLES else None


def answer_problem(answered_by_value: str, stamp: str) -> str | None:
    """Why an answer is not the role's it names, or `None`. An answer that names no role is not the
    registry's to judge."""
    name = role_of(answered_by_value)
    if name is None:
        return None
    try:
        require_stamp(name, stamp)
    except RoleError as exc:
        return str(exc)
    return None


def next_tier(model_id: str) -> str:
    """The model id one tier up (Haiku to Sonnet to Opus); `RoleError` at the top and for a model
    that is on no tier."""
    if model_id == "claude-opus-5-5":
        raise RoleError(f"no higher tier than {model_id}")
    if model_id not in ESCALATION:
        raise RoleError(f"{model_id!r} is on no tier of {sorted(ESCALATION)}")
    return ESCALATION[model_id]


def escalation(name: str, *, calibration_id: str, reason: str) -> dict[str, str]:
    """The record of a role moving up one tier after a failed calibration. The registry itself does
    not move: the move is written into the verdict and applied by a committed edit of `ROLES`,
    which is then sealed and calibrated again."""
    if not calibration_id.strip() or not reason.strip():
        raise RoleError("an escalation names its calibration and its reason")
    registered = role(name).model
    return {
        "role": name,
        "from": registered,
        "to": next_tier(registered),
        "calibration_id": calibration_id,
        "reason": reason,
    }


def candidate_model(name: str, model_id: str) -> str:
    """`model_id` as a candidate for role `name`: a model a role may be registered to that is not the
    role's registered one (a trial of the registered model is no trial). `RoleError` otherwise."""
    registered = role(name).model
    if model_id not in OH.NEW_ANSWER_MODELS:
        raise RoleError(f"{model_id!r} is not a model a role may be registered to")
    if model_id == registered:
        raise RoleError(f"{model_id} is the registered model of {name}: it is no candidate")
    return model_id


def require_candidate_stamp(model_id: str, stamp: str) -> None:
    """Refuse an answer stamp that is not the stamp of the candidate model `model_id`."""
    expected = OH.ANSWER_MODELS[model_id]
    if stamp != expected:
        raise RoleError(
            f"the candidate model is {model_id} ({expected!r}), but the answer is stamped {stamp!r}"
        )


def role_sha256(name: str, *, model: str | None = None) -> str:
    """The digest of one role's registry entry: what a seal binds a calibration to. Changing the
    role's model, effort, pool or threshold changes it; changing another role does not. With `model`
    it is the digest the entry would have if the role were registered to that model (a candidate
    trial; the registry's entry is untouched)."""
    entry = role(name)
    body = json.dumps(
        {
            "name": entry.name,
            "model": entry.model if model is None else model,
            "effort": entry.effort,
            "calibration_set": entry.calibration_set,
            "threshold": entry.threshold,
        },
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def registry_sha256() -> str:
    """The sha256 of this file's bytes: the whole registry as a seal saw it."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


check_applied_escalations(APPLIED_ESCALATIONS, ROLES)
