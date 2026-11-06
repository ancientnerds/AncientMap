"""Gap 3 (2026-10-24): which role re-checks a hero, and what the image calibration's seal binds.

Settled for the close-out under D45/D51, moved by D103: every image hero re-check (D15's served-image
recheck, the D17 C3 re-check, the D10 re-check of the MiniMax picks) was the shared role `adversarial`
(Sonnet 5.5 high since D36), calibrated **for this lane** in `image-roles-v1`. It failed there
(agreement 0.86 of 0.95, tier move to Opus); following D45 the image lane got a role of its own,
`image_adversarial` (Opus high), which settles that move (`roles.SETTLED_TIER_MOVES`) and answers
the calibration's re-check slot `adversarial` in `image-roles-v2`. The shared role stays on Sonnet for
the fields and identity lanes. A new role of another lane must not touch the image seal; a move of the
image lane's role must void it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import roles as RO  # noqa: E402
from image_roles import calibrate as CAL  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from served_image import vision as V  # noqa: E402

ROLE = "image_adversarial"
SLOT = "adversarial"
SHARED = "adversarial"


def test_every_image_hero_recheck_is_the_image_lane_s_own_role() -> None:
    assert V.RECHECK_ROLE == ROLE
    assert HR.SPEC.role == ROLE
    assert HR.spec_for_round(3).role == ROLE
    assert CAL.ROLE_SPECS[SLOT].role == ROLE and CAL.slot_role(SLOT) == ROLE


def test_the_image_role_is_opus_high_and_the_shared_role_stays_sonnet_as_d36_left_it() -> None:
    entry = RO.role(ROLE)
    assert (entry.model, entry.effort) == ("claude-opus-5-5", "high")
    assert RO.last_move(ROLE) is None  # a new role, not a move
    shared = RO.role(SHARED)
    assert (shared.model, shared.effort) == ("claude-sonnet-5-5", "high")
    move = RO.last_move(SHARED)
    assert move is not None and move.get("decision") == "D36"
    settled = RO.settled_tier_move(SHARED, "image-roles-v1")
    assert settled is not None and settled["settled_by"] == ROLE


def test_the_image_calibration_measures_the_slot_and_seals_its_role_s_entry(
    tmp_path: Path,
) -> None:
    assert SLOT in CAL.MEASURED and SLOT in CAL.THRESHOLDS["roles"]
    assert CAL.THRESHOLDS["version"] == "image-roles-v1"
    CAL.seal(tmp_path)
    document, _, _ = CAL.sealed(tmp_path)
    assert document["role_registry"][SLOT] == {
        "role": ROLE,
        "model": "claude-opus-5-5",
        "effort": "high",
        "role_sha256": RO.role_sha256(ROLE),
    }


def test_a_new_card_role_leaves_the_image_seal_standing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CAL.seal(tmp_path)
    added = dict(RO.ROLES)
    added["card_adversarial"] = RO.Role("card_adversarial", "claude-opus-5-5", "high", "teaser")
    monkeypatch.setattr(RO, "ROLES", MappingProxyType(added))
    CAL.sealed(tmp_path)  # the seal binds each image role's own entry, not the whole registry


def test_a_move_of_the_image_role_voids_the_image_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CAL.seal(tmp_path)
    moved = dict(RO.ROLES)
    moved[ROLE] = RO.Role(ROLE, "claude-opus-5-5", "xhigh", RO.role(ROLE).calibration_set)
    monkeypatch.setattr(RO, "ROLES", MappingProxyType(moved))
    with pytest.raises(CAL.CalibrationError, match="changed after the seal"):
        CAL.sealed(tmp_path)


def test_the_seal_of_image_roles_v1_bound_the_shared_role_and_no_longer_stands() -> None:
    """image-roles-v1 was sealed with the slot answered by the shared role (no `role` key): read as
    that role, it no longer matches the slot's role, so its seal is void (`sealed`)."""
    assert CAL.sealed_role(SLOT, {"role_sha256": "x"}) == SHARED != CAL.slot_role(SLOT)
