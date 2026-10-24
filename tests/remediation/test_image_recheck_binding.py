"""Gap 3 (2026-10-24): which role re-checks a hero, and what the image calibration's seal binds.

Settled for the close-out under D45/D51: every image hero re-check (D15's served-image recheck, the
D17 C3 re-check, the D10 re-check of the MiniMax picks) is the shared role `adversarial`, registered to
Sonnet 5.5 high since D36 and calibrated **for this lane** in `image-roles-v1`; it moves up one tier
only when that calibration fails (D51). The failed tier move of `teaser-2026-10-10` belongs to the
card lane, which gets a role of its own (`card_adversarial`) - adding that role must not touch the
image seal, and a move of the shared role must void it.
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

ROLE = "adversarial"


def test_every_image_hero_recheck_is_the_shared_adversarial_role() -> None:
    assert V.RECHECK_ROLE == ROLE
    assert HR.SPEC.role == ROLE
    assert HR.spec_for_round(3).role == ROLE
    assert CAL.ROLE_SPECS[ROLE].role == ROLE


def test_the_shared_role_is_sonnet_high_as_d36_left_it() -> None:
    entry = RO.role(ROLE)
    assert (entry.model, entry.effort) == ("claude-sonnet-5-5", "high")
    move = RO.last_move(ROLE)
    assert move is not None and move.get("decision") == "D36"


def test_the_image_calibration_measures_the_role_and_seals_its_entry(tmp_path: Path) -> None:
    assert ROLE in CAL.MEASURED and ROLE in CAL.THRESHOLDS["roles"]
    assert CAL.THRESHOLDS["version"] == "image-roles-v1"
    CAL.seal(tmp_path)
    document, _, _ = CAL.sealed(tmp_path)
    assert document["role_registry"][ROLE] == {
        "model": "claude-sonnet-5-5",
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


def test_a_move_of_the_shared_role_voids_the_image_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CAL.seal(tmp_path)
    moved = dict(RO.ROLES)
    moved[ROLE] = RO.Role(ROLE, "claude-opus-5-5", "high", RO.role(ROLE).calibration_set)
    monkeypatch.setattr(RO, "ROLES", MappingProxyType(moved))
    with pytest.raises(CAL.CalibrationError, match="changed after the seal"):
        CAL.sealed(tmp_path)
