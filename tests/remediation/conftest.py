"""Shared fixtures of the remediation tests."""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

REMEDIATION = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import roles as RO  # noqa: E402

#: The fixture a test (or its module's `pytestmark`) asks for to run on the earlier registry.
UNTIL_D153 = "registry_until_d153"


def _is_fable_move(move: Mapping[str, Any]) -> bool:
    return move.get("kind") == RO.OWNER_KIND and move["decision"] == RO.FABLE_DECISION


@pytest.fixture(autouse=True)
def _registry_of_the_test(request: pytest.FixtureRequest) -> Iterator[None]:
    """Puts `registry_until_d153` in place before every other fixture of a test that asks for it.

    Autouse and defined here, so it runs ahead of a module's or a class's own fixtures: several of
    them build on `roles.ROLES` as they find it (one role moved, one move added), and they must find
    the earlier registry. It patches with a context of its own, so a test that undoes its
    `monkeypatch` does not put the registry back mid-test. A test that does not ask is untouched."""
    if UNTIL_D153 not in request.fixturenames:
        yield
        return
    moves = tuple(m for m in RO.APPLIED_ESCALATIONS if not _is_fable_move(m))
    stood = {m["role"]: m["from"] for m in RO.APPLIED_ESCALATIONS if _is_fable_move(m)}
    assert set(stood) == set(RO.ROLES), "D153 moved every role"
    roles = MappingProxyType(
        {name: dataclasses.replace(entry, model=stood[name]) for name, entry in RO.ROLES.items()}
    )
    RO.check_applied_escalations(moves, roles)
    RO.check_settled_tier_moves(RO.SETTLED_TIER_MOVES, moves, roles)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(RO, "ROLES", roles)
        patch.setattr(RO, "APPLIED_ESCALATIONS", moves)
        yield


@pytest.fixture
def registry_until_d153(_registry_of_the_test: None) -> Mapping[str, RO.Role]:
    """The role registry as it stood until owner decision D153 (2026-11-10) put every role on
    Fable: each role on the `from` of its D153 move, and the applied moves without the D153 ones.

    The calibration machinery - a tier move after a failed verdict, the hold at the top tier, a
    release, a candidate trial, a seal bound to a role's entry - and a stamp refused between two
    roles' models can only be exercised on a registry whose roles stand on different tiers. Fable
    is on none, and D154 runs no calibration on it. A test of that machinery asks for this fixture,
    so the machinery stays proven for a role that is moved again; a test of what D153 and D154
    changed uses the registry as it is.

    The registry is rebuilt from the chain itself (`roles.APPLIED_ESCALATIONS`), never from a second
    list here, and it is held to the same two checks `roles.py` runs at import. A subprocess a test
    starts does not see it: the recorder's own tests name Fable."""
    return RO.ROLES
