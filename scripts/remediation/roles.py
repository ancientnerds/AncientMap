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

The two code roles have no pool of cases (`calibration_set` is `None`): the gates and the Opus
review judge them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

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
    Role("card_writer", "claude-opus-5-5", "high", "wb_cards_accepted"),
    # Effort xhigh since 2026-10-09: at medium it failed teaser-2026-10-09 (hook_pairs ordered right
    # 0.7902 of a required 1.0, within one of the xhigh reference 1.0); Opus has no higher model
    # tier, so the orchestrator raised the effort under D8 (AUDIT_LOG 2026-10-09).
    Role("hook_rater", "claude-opus-5-5", "xhigh", "design_run_hand_drawn_60"),
    # Opus since the tier moves of 2026-10-09 (`APPLIED_ESCALATIONS`): Sonnet failed teaser-2026-10-09b.
    Role("fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    Role("web_verifier", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # Opus since the tier move of 2026-10-09 (`APPLIED_ESCALATIONS`): Sonnet failed fr-general-001.
    Role("field_researcher", "claude-opus-5-5", "high", "wd1_wd3_rounds_and_bp_set"),
    # The description writer of lane E (`wc/prompts_enrich.py`). It rode on `field_researcher` until
    # that role moved to Opus: the lane's writing was never measured on Opus and stays on Sonnet,
    # under a calibration set of its own, sealed as `enrich-writer`.
    Role("enrich_writer", "claude-sonnet-5-5", "high", "enrich-writer"),
    Role("adversarial", "claude-opus-5-5", "high", "opus_audit_934"),
    Role("image_prefilter", "claude-haiku-5-5", "low", "image_kind_135"),
    Role("image_depicts", "claude-sonnet-5-5", "medium", "gallery_audit_calibration_opus"),
    Role("code_builder", "claude-sonnet-5-5", "high", None),
    Role("code_review", "claude-opus-5-5", "high", None),
    Role("pilot_judge", "claude-opus-5-5", "xhigh", "canaries_10"),
    Role("operator", "claude-haiku-5-5", "low", "scripted_dry_run"),
)


#: The tier moves applied to `ROLES`, oldest first. A move is a record: the dict `escalation()` returns
#: for the failed verdict (`verdicts/<calibration_id>.json` of the calibration root), copied here when
#: the `ROLES` edit is committed, so the edit never stands without its calibration and its reason.
#: `check_applied_escalations` holds the registry to them at import.
APPLIED_ESCALATIONS: tuple[Mapping[str, str], ...] = (
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
)
_ESCALATION_KEYS = frozenset({"role", "from", "to", "calibration_id", "reason"})


def check_applied_escalations(
    moves: tuple[Mapping[str, str], ...], roles: Mapping[str, Role]
) -> None:
    """Refuse a record of `moves` that is not a one-tier move of a registered role with its
    calibration and reason, a chain that does not join (each move starts where the last one ended),
    and a registry that is not where the last move of its role ended."""
    ended: dict[str, str] = {}
    for move in moves:
        if set(move) != _ESCALATION_KEYS or not all(str(v).strip() for v in move.values()):
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
        if move["to"] != next_tier(move["from"]):
            raise RoleError(f"{name}: {move['from']} to {move['to']} is not one tier up")
        ended[name] = move["to"]
    for name, model in ended.items():
        if roles[name].model != model:
            raise RoleError(
                f"{name} is registered to {roles[name].model}, but its applied moves end at {model}"
            )


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


def role_sha256(name: str) -> str:
    """The digest of one role's registry entry: what a seal binds a calibration to. Changing the
    role's model, effort, pool or threshold changes it; changing another role does not."""
    entry = role(name)
    body = json.dumps(
        {
            "name": entry.name,
            "model": entry.model,
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
