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

A tier move that a failed verdict named but that was never applied to its role, because a lane got a
role of its own on the higher tier instead (D45), is a **settled tier move** (`SETTLED_TIER_MOVES`):
the move as the verdict named it, the role that took the context over and the decision. The role it
names stays where it was.

The two code roles have no pool of cases (`calibration_set` is `None`): the gates and the review
judge them.

A **candidate model** trial (`candidate_model`) calibrates a role with another model without touching
the registry. Its seal binds the digest of the entry the role would have with the candidate
(`role_sha256(name, model=...)`), so the verdict stands for the role only after an owner move has
registered that model: until then the digest does not match the registry and every gate refuses it.

**Owner moves without calibration** (`UNCALIBRATED_DECISIONS`). An owner decision can put every
role on one model and, by owner decision D154 of 2026-11-10, run no calibration on it: D153
(2026-11-10, "only Fable 5.2": `claude-fable-5-2`) and D157 (2026-11-11, the Fable quota used up:
`claude-opus-5-5`). Each role then has an owner move of its own under that decision
(`_uncalibrated_move`): it rests on no calibration (its `evidence` is empty, and must be), keeps the
role's effort, ends at the decision's model and records `at`, the time the registry took the move.
The role's trailing run of such moves (`owner_tail`) is what one rule set reads, each rule stated
once, here:

* `owner_standing` - a role whose last applied move is such a move stands by owner decision. Every
  gate that asks a role's calibration asks this first and says so in what it returns; a role moved
  again afterwards stands by its calibration again. `standing_problem` holds an answer passing such
  a gate to the window of the standing: an answer recorded before its first move was written on a
  model that stood by a calibration the gate did not ask.
* `answer_problem` - an answer is the role's when its stamp is the model the role stood on when the
  answer was recorded (`model_at`, from the moves' `at` and the answer's `answered_at`). An answer
  recorded before a move keeps the earlier model's stamp and stays valid; one recorded after it
  must carry the new model's. `require_model` (the recorder, `opus_handoff.py answer --role`) takes
  the registered model only, and `candidate_model` refuses a model such a move took the role from.
* `model_now` - a run or round that fixed a role's model when it was exported goes on with the
  role's current model when one of those moves took the role from exactly that model: its briefs
  name the current model, its imports accept each model in its window (`run_model_at`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
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
#: Owner decision D153 of 2026-11-10 ("only Fable 5.2"). Fable is on no tier of `ESCALATION` -
#: nothing moves a role up from it, a failing verdict would be held.
FABLE = "claude-fable-5-2"
#: Owner decision D154 of 2026-11-10: no calibration is run. A role an owner move of
#: `UNCALIBRATED_DECISIONS` put on its model stands there by the owner's decision, with no verdict
#: of its own (`owner_standing`).
NO_CALIBRATION_DECISION = "D154"
#: The owner decisions that moved every role without a calibration (D154), oldest first: the
#: decision -> the model it put every role on, the time the move took effect (`at`, copied into each
#: move) and why. D153's `at` is its registry commit 2bc9aab; D157's is the commit that recorded the
#: decision (1bece71) - the Fable quota was used up before it, so no Fable answer follows it. An
#: answer recorded before `at` keeps the earlier model's stamp; one recorded at or after it carries
#: the new model's (`model_at`).
UNCALIBRATED_DECISIONS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "D153": MappingProxyType(
            {
                "to": FABLE,
                "at": "2026-11-10T20:55:24+00:00",
                "why": "only Fable 5.2 from now on (owner, 2026-11-10)",
            }
        ),
        "D157": MappingProxyType(
            {
                "to": "claude-opus-5-5",
                "at": "2026-11-11T16:27:38+00:00",
                "why": "the Fable 5.2 quota is used up, go on with Opus 5.5 (owner, 2026-11-11)",
            }
        ),
    }
)
#: The model the latest of those decisions put every role on: what a brief that names no role
#: offers as the model to record with (`opus_handoff.py answer --model`).
ROLELESS_MODEL = list(UNCALIBRATED_DECISIONS.values())[-1]["to"]


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
    # Opus 5.5 since owner decision D157 of 2026-11-11 (the Fable quota was used up), Fable 5.2
    # before it since D153 of 2026-11-10 - every role, each by an owner move of its own under each
    # decision (`APPLIED_ESCALATIONS`), effort and pool unchanged, and with no calibration on either
    # (D154, `owner_standing`). The comments below tell how each role came to stand where D153
    # found it: on the `from` of its D153 move, the model its earlier answers are stamped with.
    # Sonnet since owner decision D36 of 2026-10-09 (`APPLIED_ESCALATIONS`, owner moves): the weekly
    # quota stood at 69 % after one day, and the calibrations measured no Opus advantage. Where a
    # role stood on Opus before that, the tier move up is the earlier record of its chain.
    # Opus since owner decision D46 of 2026-10-19: on Sonnet the checker passed 23 of 39 first
    # drafts of pilot wb-shorts-pilot-2026-10-18 (59 %, gate 70 %); the second pilot measures Opus.
    Role("card_writer", "claude-opus-5-5", "high", "wb_cards_accepted"),
    # Effort xhigh from 2026-10-09 (at medium it failed teaser-2026-10-09, hook_pairs ordered right
    # 0.7902 of a required 1.0), medium again on Sonnet under D36. Sonnet failed teaser-2026-10-10
    # (0.8601), so the D6 rule moves it up one tier to Opus, calibrated again in teaser-2026-10-18.
    Role("hook_rater", "claude-opus-5-5", "medium", "design_run_hand_drawn_60"),
    # Sonnet failed teaser-2026-10-09b (tier move to Opus), Opus showed no gain in teaser-2026-10-09c;
    # D36 put the role back on Sonnet. It answers lane WC only (the check rounds of every WC run kind
    # and lane WN's write round, `wc/cli.py check_role`), and on Sonnet it failed lane WC's own
    # calibrations of 2026-10-24: wc-fc-1 (0.9216, but a known error kept) and wc-fc-2
    # (0.8841, a known error missed). D51 (a role that fails its calibration moves to Opus, the D6
    # tier rule) applies the tier move of wc-fc-1 (`APPLIED_ESCALATIONS`); wc-fc-2 named the same
    # move. A move, not a new role: no other lane answers as `fact_checker`. Calibrated again on Opus
    # (wc-fc-1o, -2o, -3o) before its next answer.
    Role("fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # The shared web verifier: identity, lane E (`wc/prompts_enrich.VERIFIER_ROLE`) and image
    # identity, each calibrated on its own pools (D45). Lane WC's verification has its own role,
    # `wc_web_verifier`, since the WC calibrations wc-wv-1/2 failed it (`SETTLED_TIER_MOVES`).
    Role("web_verifier", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # The card lane's own checkers. Owner decision D40 (after teaser-2026-10-10, in which no Sonnet
    # checker passed and the Haiku trial was weaker) put the card checks on Opus; D45 (2026-10-17)
    # scoped it to the card lane, so `fact_checker` (lane WC) and `web_verifier` (identity, lane E,
    # image identity) stayed on Sonnet then (lane WC's own calibrations moved `fact_checker` on
    # 2026-10-24, see above). New roles, not moves: they are calibrated before first use.
    Role("card_fact_checker", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    Role("card_web_verifier", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # Lane WC's own web verifier: the verification rounds `verify` and `verify2` of every WC run kind
    # but lane E's (plain, site-list, WN, the D10 re-check, the defect runs; `wc/cli.py verify_role`).
    # As `web_verifier` it failed lane WC's calibrations on Sonnet (wc-wv-1 0.8193 and wc-wv-2 0.8986
    # of a sealed 0.95, tier moves to Opus); following D45 the WC context gets a role of its own on
    # Opus (D51/D6: a failing role moves up) instead of moving the shared one. A new role, not a
    # move: it is calibrated on the WC verify pools (wc-wv-1o, wc-wv-2o) before its first answer.
    Role("wc_web_verifier", "claude-opus-5-5", "high", "wc_verify_rounds"),
    # Sonnet failed fr-general-001 at 0.8636 (tier move to Opus); Opus reached 0.871 in
    # fr-general-002; D36 puts the role back on Sonnet under a release of fr-general-001.
    Role("field_researcher", "claude-opus-5-5", "high", "wd1_wd3_rounds_and_bp_set"),
    # The description writer of lane E (`wc/prompts_enrich.py`). It rode on `field_researcher` until
    # that role moved to Opus: the lane's writing was never measured on Opus and stays on Sonnet,
    # under a calibration set of its own, sealed as `enrich-writer`.
    Role("enrich_writer", "claude-opus-5-5", "high", "enrich-writer"),
    # D36: it re-checks every wd5 write, so it is calibrated on Sonnet before use. The shared role of
    # the fields, identity and image lanes (D45, D51: it passed adv-truth-002 on Sonnet, 0.96); it no
    # longer reviews cards - see `card_adversarial` and `SETTLED_TIER_MOVES`.
    Role("adversarial", "claude-opus-5-5", "high", "opus_audit_934"),
    # The card lane's own adversarial reviewer: the last stage of the D10 re-check of the cards
    # another model wrote (contract recheck-v1). As `adversarial` it failed the card calibration on
    # Sonnet (teaser-2026-10-10, 0.7907 of 0.9, tier move to Opus) and on Opus before the contradiction
    # rule and DISPUTED were tuned in (teaser-2026-10-09c, 0.72). Following D45 the card context gets
    # a role of its own on Opus (D51/D6: a failing role moves up) instead of moving the shared one; a
    # new role, not a move: it is calibrated on the 50 card cases before its first answer.
    Role("card_adversarial", "claude-opus-5-5", "high", "wb_check_verify_opus"),
    # Lane WC's own adversarial second check (`wc/cli.py export --adversarial`, D25b): a description
    # sentence a later web check reported contradicted and that the check and the verifier both kept
    # (Leominster eebdcbf3 and the other defects_kept of defects-a1-2026-11-06). The shared
    # `adversarial` (Sonnet) was never calibrated for lane WC, and owner decision D134 of 2026-11-07
    # calibrates the WC context on Opus (~30-50 answers); following D45 the lane gets a role of its
    # own instead of moving the shared one, which stays on Sonnet for the fields and identity lanes.
    # A new role, not a move: it is calibrated on WC's adjudicated defect checks
    # (`wc/calibration.py`, kind `adversarial`) before its first answer.
    Role("wc_adversarial", "claude-opus-5-5", "high", "wc_defect_adversarial"),
    # Owner decision D103 (2026-11-06) applies the tier moves of the failed image calibration
    # image-roles-v1 (2026-10-25): the prefilter moves from Haiku to Sonnet (photo agreement 0.9167
    # of 0.92, depicts-capable recall 0.9265 of 0.98), the depicts judge from Sonnet to Opus
    # (sensitivity 0.7267, precision 0.843, false depicts 0.1116, 25 foreign rows called depicts).
    # Both are calibrated again one tier up on the same sealed gold (image-roles-v2) before use.
    # The prefilter failed v2 on Sonnet too (photo agreement 0.9033, recall 0.848); D118 tested it
    # at Opus first (the probe, 0.9267 and 0.9167 on v2's flawed gold; 10 of its 17 drops a
    # picture of a surviving kind judged not usable, which v2's kind gold does not label) and the
    # tier move v2 named is applied: Opus low, calibrated on the clean kind gold image-roles-v3p.
    Role("image_prefilter", "claude-opus-5-5", "low", "image_kind_135"),
    Role("image_depicts", "claude-opus-5-5", "medium", "gallery_audit_calibration_opus"),
    # The image lane's own hero re-check (D15's served-image recheck, D17 C3, the D10 re-check of the
    # MiniMax picks). As the shared `adversarial` it failed image-roles-v1 on Sonnet (agreement 0.86
    # of 0.95, tier move to Opus); following D45 the image context gets a role of its own on Opus
    # (D51/D103: a failing role moves up) instead of moving the shared one, which stays on Sonnet for
    # the fields and identity lanes. A new role, not a move: it is calibrated on the 200 re-check
    # cases of image-roles-v1 (image-roles-v2) before its first answer.
    Role("image_adversarial", "claude-opus-5-5", "high", "image_roles_recheck_200"),
    Role("code_builder", "claude-opus-5-5", "high", None),
    Role("code_review", "claude-opus-5-5", "high", None),
    Role("pilot_judge", "claude-opus-5-5", "xhigh", "canaries_10"),
    Role("operator", "claude-opus-5-5", "low", "scripted_dry_run"),
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


def _uncalibrated_move(decision: str, role_name: str, was: str, effort: str) -> Mapping[str, Any]:
    """One owner move of a decision of `UNCALIBRATED_DECISIONS`: the role goes from `was`, the model
    it answered on until then, to the decision's model at the decision's `at`; the effort stays. It
    rests on no calibration (D154), so its evidence is empty - the one kind of owner move that may
    be (`_check_owner_move`)."""
    made = UNCALIBRATED_DECISIONS[decision]
    return MappingProxyType(
        {
            "kind": OWNER_KIND,
            "role": role_name,
            "from": was,
            "to": made["to"],
            "effort": effort,
            "decision": decision,
            "at": made["at"],
            "reason": f"{made['why']}; no calibration was run on {made['to']}, by owner decision "
            f"{NO_CALIBRATION_DECISION}: the role stands on it by the decision alone, with no "
            "verdict of its own",
            "evidence": (),
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
    MappingProxyType(
        {
            "role": "hook_rater",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-10",
            "reason": "failed: hook_pairs",
        }
    ),
    MappingProxyType(
        {
            "kind": OWNER_KIND,
            "role": "card_writer",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "effort": "high",
            "decision": "D46",
            "reason": "owner, 2026-10-19 (spare weekly quota): the Sonnet writer of pilot "
            "wb-shorts-pilot-2026-10-18 had 23 of 39 first drafts pass the Opus checker (59 %, "
            "gate 70 %), its findings real writer faults; the checkers are never lowered",
            "evidence": ("wb-shorts-pilot-2026-10-18",),
        }
    ),
    MappingProxyType(
        {
            # `verdicts/wc-fc-1.json` (2026-10-24, Sonnet: agreement 0.9216 of 0.9, the known error
            # missed); wc-fc-2 named the same move (0.8841, a known error missed). D51.
            "role": "fact_checker",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "wc-fc-1",
            "reason": "known error 5facc061-8835-4129-9e3c-7b17ebf2d5e8/sentence-4 missed: the "
            "fresh answer says 'KEEP', expected not ['KEEP', 'KEEP_TRIMMED']",
        }
    ),
    MappingProxyType(
        {
            # `image-roles-v1/verdicts/image_prefilter.json` (2026-10-25, Haiku low); applied under
            # owner decision D103 of 2026-11-06.
            "role": "image_prefilter",
            "from": "claude-haiku-5-5",
            "to": "claude-sonnet-5-5",
            "calibration_id": "image-roles-v1",
            "reason": "photo_agreement 0.9167 is below 0.92; depicts_capable_recall 0.9265 is "
            "below 0.98",
        }
    ),
    MappingProxyType(
        {
            # `image-roles-v1/verdicts/image_depicts.json` (2026-10-25, Sonnet medium); applied
            # under owner decision D103 of 2026-11-06.
            "role": "image_depicts",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "image-roles-v1",
            "reason": "sensitivity 0.7267 is below 0.9; precision 0.843 is below 0.95; "
            "false_depicts 0.1116 is above 0.03; 25 foreign row(s) called depicts",
        }
    ),
    MappingProxyType(
        {
            # `image-roles-v2/verdicts/image_prefilter.json` (2026-11-06, Sonnet low); applied
            # under owner decision D118 of 2026-11-06 on the evidence of the Opus probe
            # (`calibration/prefilter-probe-d118/PROBE.json`, 2026-11-07: v2's five questions byte
            # for byte, photo agreement 0.9267, depicts-capable recall 0.9167 against Sonnet's
            # 0.9033 and 0.848). Calibrated again on Opus on the clean kind gold image-roles-v3p.
            "role": "image_prefilter",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "image-roles-v2",
            "reason": "photo_agreement 0.9033 is below 0.92; depicts_capable_recall 0.848 is "
            "below 0.98",
        }
    ),
    # Owner decision D153 of 2026-11-10: every role, in the order of `ROLES`, from the model the
    # chain above (or, for a role never moved, its first registration) left it on.
    _uncalibrated_move("D153", "card_writer", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "hook_rater", "claude-opus-5-5", "medium"),
    _uncalibrated_move("D153", "fact_checker", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "web_verifier", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "card_fact_checker", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "card_web_verifier", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "wc_web_verifier", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "field_researcher", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "enrich_writer", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "adversarial", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "card_adversarial", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "wc_adversarial", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "image_prefilter", "claude-opus-5-5", "low"),
    _uncalibrated_move("D153", "image_depicts", "claude-opus-5-5", "medium"),
    _uncalibrated_move("D153", "image_adversarial", "claude-opus-5-5", "high"),
    _uncalibrated_move("D153", "code_builder", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "code_review", "claude-sonnet-5-5", "high"),
    _uncalibrated_move("D153", "pilot_judge", "claude-opus-5-5", "xhigh"),
    _uncalibrated_move("D153", "operator", "claude-haiku-5-5", "low"),
    # Owner decision D157 of 2026-11-11: every role, in the order of `ROLES`, from Fable to Opus.
    _uncalibrated_move("D157", "card_writer", FABLE, "high"),
    _uncalibrated_move("D157", "hook_rater", FABLE, "medium"),
    _uncalibrated_move("D157", "fact_checker", FABLE, "high"),
    _uncalibrated_move("D157", "web_verifier", FABLE, "high"),
    _uncalibrated_move("D157", "card_fact_checker", FABLE, "high"),
    _uncalibrated_move("D157", "card_web_verifier", FABLE, "high"),
    _uncalibrated_move("D157", "wc_web_verifier", FABLE, "high"),
    _uncalibrated_move("D157", "field_researcher", FABLE, "high"),
    _uncalibrated_move("D157", "enrich_writer", FABLE, "high"),
    _uncalibrated_move("D157", "adversarial", FABLE, "high"),
    _uncalibrated_move("D157", "card_adversarial", FABLE, "high"),
    _uncalibrated_move("D157", "wc_adversarial", FABLE, "high"),
    _uncalibrated_move("D157", "image_prefilter", FABLE, "low"),
    _uncalibrated_move("D157", "image_depicts", FABLE, "medium"),
    _uncalibrated_move("D157", "image_adversarial", FABLE, "high"),
    _uncalibrated_move("D157", "code_builder", FABLE, "high"),
    _uncalibrated_move("D157", "code_review", FABLE, "high"),
    _uncalibrated_move("D157", "pilot_judge", FABLE, "xhigh"),
    _uncalibrated_move("D157", "operator", FABLE, "low"),
)
_ESCALATION_KEYS = frozenset({"role", "from", "to", "calibration_id", "reason"})
_OWNER_KEYS = frozenset({"kind", "role", "from", "to", "effort", "decision", "reason", "evidence"})
#: An owner move of `UNCALIBRATED_DECISIONS` carries the time it took effect besides.
_UNCALIBRATED_KEYS = frozenset({*_OWNER_KEYS, "at"})
_DECISION = re.compile(r"D\d+[a-z]?")

#: How lane WC's failed verify calibrations were settled (`SETTLED_TIER_MOVES`, wc-wv-1 and -2).
_WC_VERIFY_SETTLED = (
    "the failure is lane WC's: lane WC's verification rounds (verify, verify2) moved to the new role "
    "wc_web_verifier on Opus (D45: a shared role is not moved for one lane, the lane gets a role of "
    "its own; D51: a failing role moves to Opus), calibrated on the same WC verify pools; the shared "
    "web_verifier stays on Sonnet for identity, lane E and image identity, which calibrate it on "
    "pools of their own"
)

#: The tier moves a failed verdict named that were never applied to the role it named, each with how
#: it was settled instead: the verdict's `tier_move` copied (as `APPLIED_ESCALATIONS` copies an
#: applied one), the role that took the context over (`settled_by`, registered at the move's `to`),
#: the decision it rests on and why. The named role stays where it was: such a move is never also an
#: applied one, and `check_settled_tier_moves` holds the registry to both at import.
SETTLED_TIER_MOVES: tuple[Mapping[str, Any], ...] = (
    MappingProxyType(
        {
            # `VERDICT-adversarial.json` of teaser-2026-10-10 (Sonnet: clean 14/18, contradicted
            # 20/25, agreement 0.7907 of 0.9).
            "role": "adversarial",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "teaser-2026-10-10",
            "reason": "failed: adversarial_agreement",
            "settled_by": "card_adversarial",
            "decision": "D45",
            "how": "the failure is the card context's: the card lane's adversarial review moved to "
            "the new role card_adversarial on Opus (D45: the card lane gets roles of its own; D51: a "
            "failing role moves to Opus), calibrated on the same card cases; the shared adversarial "
            "stays on Sonnet for the fields, identity and image lanes, where it passed adv-truth-002",
        }
    ),
    MappingProxyType(
        {
            # `verdicts/wc-wv-1.json` (2026-10-24, Sonnet: the pilot-27c verification, 68 of 83 units).
            "role": "web_verifier",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "wc-wv-1",
            "reason": "agreement 0.8193 is below the sealed threshold 0.95",
            "settled_by": "wc_web_verifier",
            "decision": "D45",
            "how": _WC_VERIFY_SETTLED,
        }
    ),
    MappingProxyType(
        {
            # `verdicts/wc-wv-2.json` (2026-10-24, Sonnet: the mass-02 verification, 62 of 69 units).
            "role": "web_verifier",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "wc-wv-2",
            "reason": "agreement 0.8986 is below the sealed threshold 0.95",
            "settled_by": "wc_web_verifier",
            "decision": "D45",
            "how": _WC_VERIFY_SETTLED,
        }
    ),
    MappingProxyType(
        {
            # `image-roles-v1/verdicts/adversarial.json` (2026-10-25, Sonnet high: the 200 hero
            # re-check cases, 172 agreed).
            "role": "adversarial",
            "from": "claude-sonnet-5-5",
            "to": "claude-opus-5-5",
            "calibration_id": "image-roles-v1",
            "reason": "agreement 0.86 is below 0.95",
            "settled_by": "image_adversarial",
            "decision": "D45",
            "how": "the failure is the image lane's: its hero re-checks (served_image recheck, "
            "hero_recheck, the calibration's re-check slot) moved to the new role "
            "image_adversarial on Opus (D45: a shared role is not moved for one lane; D51 and D103 "
            "of 2026-11-06: a failing role moves up one tier), calibrated on the same 200 cases in "
            "image-roles-v2; the shared adversarial stays on Sonnet for the fields and identity "
            "lanes, where it passed adv-truth-002",
        }
    ),
)
_SETTLED_KEYS = frozenset({*_ESCALATION_KEYS, "settled_by", "decision", "how"})


def uncalibrated(move: Mapping[str, Any]) -> bool:
    """Whether `move` is an owner move of a decision of `UNCALIBRATED_DECISIONS`."""
    return move.get("kind") == OWNER_KIND and move["decision"] in UNCALIBRATED_DECISIONS


def _until_uncalibrated(
    moves: tuple[Mapping[str, Any], ...], roles: Mapping[str, Role]
) -> dict[str, str]:
    """Role -> the model it stood on until the first owner move without calibration took it away:
    the `from` of its first such move in `moves`, and for a role without one the model it is
    registered to."""
    stood = {name: entry.model for name, entry in roles.items()}
    seen: set[str] = set()
    for move in moves:
        if uncalibrated(move) and move["role"] not in seen:
            seen.add(move["role"])
            stood[move["role"]] = move["from"]
    return stood


def check_settled_tier_moves(
    settled: tuple[Mapping[str, Any], ...],
    moves: tuple[Mapping[str, Any], ...],
    roles: Mapping[str, Role],
) -> None:
    """Refuse a settled tier move that carries other keys or a blank one, that is not one tier up,
    whose role is not registered where the move started (it moved after all: that is an applied
    move), that `moves` applies too, or whose `settled_by` is not another registered role standing
    at the model the move named.

    A settlement is a record of the tier chain, and that chain ended when owner decision D153 took
    every role to Fable without a calibration. So "where a role stands" is here where it stood until
    then (`_until_uncalibrated`: the `from` of its first such move): the settled role on the model
    the move started from, the role that took the context over on the model the move named."""
    applied = {(m["role"], m.get("calibration_id")) for m in moves if m.get("kind") != OWNER_KIND}
    stood = _until_uncalibrated(moves, roles)
    for move in settled:
        if set(move) != _SETTLED_KEYS or not all(
            isinstance(v, str) and v.strip() for v in move.values()
        ):
            raise RoleError(
                f"a settled tier move carries exactly {sorted(_SETTLED_KEYS)}: {dict(move)}"
            )
        name, taker = move["role"], move["settled_by"]
        if _DECISION.fullmatch(move["decision"]) is None:
            raise RoleError(f"{name}: {move['decision']!r} is not an owner decision id (D45)")
        if name not in roles or taker not in roles:
            raise RoleError(f"a settled tier move names an unregistered role: {name!r}, {taker!r}")
        if move["to"] != next_tier(move["from"]):
            raise RoleError(f"{name}: {move['from']} to {move['to']} is not one tier up")
        if stood[name] != move["from"]:
            raise RoleError(
                f"{name} stood at {stood[name]} until the owner moves without calibration, not at "
                f"{move['from']}: a "
                "role that moved has an applied move, not a settled one"
            )
        if (name, move["calibration_id"]) in applied:
            raise RoleError(
                f"{name}: the tier move of {move['calibration_id']} is applied and settled at once"
            )
        if taker == name or stood[taker] != move["to"]:
            raise RoleError(
                f"{name}: the tier move of {move['calibration_id']} is settled by {taker}, which is "
                f"not another role that stood at {move['to']} until the owner moves without calibration"
            )


def settled_tier_move(name: str, calibration_id: str) -> Mapping[str, Any] | None:
    """The settlement of the tier move a failed verdict of role `name` in `calibration_id` named,
    or `None` when it was not settled."""
    found = [
        m for m in SETTLED_TIER_MOVES if m["role"] == name and m["calibration_id"] == calibration_id
    ]
    return found[-1] if found else None


def _check_owner_move(move: Mapping[str, Any]) -> None:
    """An owner move carries exactly `_OWNER_KEYS`: a decision id, two different registered models,
    a known effort, a reason and at least one calibration it rests on - all non-blank.

    A move under a decision of `UNCALIBRATED_DECISIONS` is the one exception, by D154: no
    calibration is run on its model, so it rests on none. Its evidence is empty and must be (such a
    move that named a calibration would claim a measurement nobody made), it ends at the decision's
    model, and it carries `at`, the decision's time (`_UNCALIBRATED_KEYS`)."""
    texts = {k: v for k, v in move.items() if k != "evidence"}
    evidence = move.get("evidence")
    without = uncalibrated(move)
    keys = _UNCALIBRATED_KEYS if without else _OWNER_KEYS
    if (
        set(move) != keys
        or not all(isinstance(v, str) and v.strip() for v in texts.values())
        or not isinstance(evidence, tuple | list)
        or (not evidence and not without)
        or not all(isinstance(e, str) and e.strip() for e in evidence)
    ):
        raise RoleError(f"an owner move carries exactly {sorted(keys)}: {dict(move)}")
    if not _DECISION.fullmatch(move["decision"]):
        raise RoleError(f"{move['role']}: {move['decision']!r} is not an owner decision id (D36)")
    if without:
        made = UNCALIBRATED_DECISIONS[move["decision"]]
        if evidence:
            raise RoleError(
                f"{move['role']}: a move under {move['decision']} rests on no calibration "
                f"({NO_CALIBRATION_DECISION}: none is run on {made['to']}), but it names "
                f"{list(evidence)}"
            )
        if move["to"] != made["to"]:
            raise RoleError(
                f"{move['role']}: a move under {move['decision']} ends at {made['to']}, not at "
                f"{move['to']}"
            )
        if move["at"] != made["at"]:
            raise RoleError(
                f"{move['role']}: a move under {move['decision']} took effect at {made['at']}, "
                f"not at {move['at']}"
            )
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
    last move of its role ended (the model, and after an owner move the effort too). The timed
    moves of a role (`uncalibrated`) follow each other in time."""
    ended: dict[str, str] = {}
    effort: dict[str, str] = {}
    timed: dict[str, datetime] = {}
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
        if uncalibrated(move):
            at = _time(move["at"])
            if name in timed and at <= timed[name]:
                raise RoleError(
                    f"{name}: the move under {move['decision']} at {move['at']} does not follow "
                    "the role's earlier timed move"
                )
            timed[name] = at
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


# ------------------------------------------- owner moves without calibration (D153, D154, D157)
def _time(value: str) -> datetime:
    """An ISO 8601 time with a zone (`answered_at`, a move's `at`), or `RoleError`."""
    try:
        when = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise RoleError(f"{value!r} is not an ISO 8601 time") from exc
    if when.tzinfo is None:
        raise RoleError(f"{value!r} carries no time zone")
    return when


def owner_standing_text(decision: str) -> str:
    """How a gate says that a role stands by owner decision `decision` of
    `UNCALIBRATED_DECISIONS`, in place of `passed` or `released`."""
    model = UNCALIBRATED_DECISIONS[decision]["to"]
    return f"owner decision {decision} (no calibration on {model}: {NO_CALIBRATION_DECISION})"


def owner_tail(name: str) -> tuple[Mapping[str, Any], ...]:
    """The trailing run of owner moves without calibration of role `name`, oldest first: empty
    when its last applied move is another kind (a role moved again by a calibration afterwards
    stands where that put it) or when it was never moved."""
    role(name)
    mine = [m for m in APPLIED_ESCALATIONS if m["role"] == name]
    tail: list[Mapping[str, Any]] = []
    for move in reversed(mine):
        if not uncalibrated(move):
            break
        tail.insert(0, move)
    return tuple(tail)


def owner_standing(name: str) -> dict[str, str] | None:
    """How role `name` stands when it stands by the owner's decision and not by a calibration, or
    `None` when it does not.

    It does when its last applied move is an owner move without calibration (`owner_tail`): the
    decision registered it to its model and D154 says no calibration is run, so there is no verdict
    to ask for. Every gate that requires a role's calibration asks this first and hands the record
    on in place of a verdict's: it names the decision in words and never says `passed`, and
    `since` is when the first move of the tail took effect - the answers the standing covers are
    the ones recorded since then (`standing_problem`). Where this returns `None` - a role moved
    again since, or one never moved so - the gate asks the calibration exactly as it did before."""
    entry = role(name)
    tail = owner_tail(name)
    if not tail:
        return None
    decision = str(tail[-1]["decision"])
    return {
        "role": name,
        "model": entry.model,
        "standing": owner_standing_text(decision),
        "owner_decision": decision,
        "since": str(tail[0]["at"]),
    }


def standing_problem(name: str, answered_at: str) -> str | None:
    """Why an answer of role `name` recorded at `answered_at` cannot pass a gate on the role's
    owner standing, or `None`. The standing covers what was answered since the first owner move
    without calibration of the role's tail: an answer recorded before it was written on the model
    the role stood on by a calibration, which a gate standing on the owner's decision did not ask.
    `RoleError` for a role that does not stand by owner decision."""
    standing = owner_standing(name)
    if standing is None:
        raise RoleError(f"role {name} does not stand by an owner decision")
    if _time(answered_at) < _time(standing["since"]):
        return (
            f"recorded at {answered_at}, before the role's owner standing began "
            f"({standing['since']}): it was answered on a model that stood by a calibration, "
            "which this gate did not ask"
        )
    return None


def run_model_at(name: str, recorded: str, answered_at: str | None) -> str:
    """The model that answered role `name` at `answered_at` (`None`: now) in a run or round that
    fixed `recorded` for it when it was exported.

    `recorded`, unless an owner move of the role's tail (`owner_tail`) took it from exactly that
    model: from that move on, each move of the tail that had taken effect by `answered_at` gives
    its model. Every role answers on the model of the latest decision from then on, a run that had
    begun included; what the run was answered before keeps its stamp. A run that recorded another
    model is not what those decisions moved and keeps what it recorded."""
    tail = owner_tail(name)
    start = next((i for i, m in enumerate(tail) if m["from"] == recorded), None)
    if start is None:
        return recorded
    model = recorded
    for move in tail[start:]:
        if answered_at is None or _time(answered_at) >= _time(move["at"]):
            model = str(move["to"])
    return model


def model_now(name: str, recorded: str) -> str:
    """The model that answers role `name` now in a run or round that fixed `recorded` for it when
    it was exported (`run_model_at` at no time: every move of the tail has taken effect)."""
    return run_model_at(name, recorded, None)


def model_at(name: str, answered_at: str) -> str:
    """The model role `name` stood on at `answered_at`, as far as the registry records times: the
    registered model, unless a timed move (`uncalibrated`) of the role took effect after
    `answered_at` - then the `from` of the first such move. Moves without a time (tier moves,
    calibrated owner moves) carry no date, so before a role's first timed move the model is that
    move's `from`, as the registry's checks always held it."""
    role(name)
    when = _time(answered_at)
    for move in APPLIED_ESCALATIONS:
        if move["role"] == name and uncalibrated(move) and when < _time(move["at"]):
            return str(move["from"])
    return role(name).model


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


def answer_problem(answered_by_value: str, stamp: str, *, answered_at: str) -> str | None:
    """Why an answer is not the role's it names, or `None`. An answer that names no role is not the
    registry's to judge.

    Its stamp must be the stamp of the model the role stood on when it was recorded (`model_at`):
    an answer the role gave before an owner move without calibration carries the stamp of the
    model it answered on until then and stays valid (D153, D157: "answers recorded earlier keep
    their stamp"); one recorded at or after the move carries the new model's, whatever recorded it
    (`opus_handoff.py answer --role` or `--candidate-model`, or an `answered_by` written by hand)."""
    name = role_of(answered_by_value)
    if name is None:
        return None
    model = model_at(name, answered_at)
    expected = OH.ANSWER_MODELS[model]
    if stamp != expected:
        return (
            f"role {name} is registered to {model} ({expected!r}) for an answer recorded at "
            f"{answered_at}, but the answer is stamped {stamp!r}"
        )
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
    taken = [m for m in owner_tail(name) if m["from"] == model_id]
    if taken:
        raise RoleError(
            f"owner decision {taken[-1]['decision']} took {name} from {model_id} with no "
            f"calibration ({NO_CALIBRATION_DECISION}): an answer of the role on {model_id} is one "
            "recorded before that move, a new one is no trial"
        )
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


def check_uncalibrated_decisions(decisions: Mapping[str, Mapping[str, str]]) -> None:
    """Refuse a table of owner decisions without calibration that is not a decision id -> a model a
    role may be registered to, a time with a zone and a reason, in time order."""
    last: datetime | None = None
    for decision, made in decisions.items():
        if _DECISION.fullmatch(decision) is None or set(made) != {"to", "at", "why"}:
            raise RoleError(f"{decision}: not an owner decision without calibration: {dict(made)}")
        if made["to"] not in OH.NEW_ANSWER_MODELS or not made["why"].strip():
            raise RoleError(
                f"{decision}: {made['to']!r} is not a model a role may be registered to"
            )
        at = _time(made["at"])
        if last is not None and at <= last:
            raise RoleError(
                f"{decision}: its time {made['at']} does not follow the decision before"
            )
        last = at


check_uncalibrated_decisions(UNCALIBRATED_DECISIONS)
check_applied_escalations(APPLIED_ESCALATIONS, ROLES)
check_settled_tier_moves(SETTLED_TIER_MOVES, APPLIED_ESCALATIONS, ROLES)
