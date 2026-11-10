"""Owner-decided retirements through the scope-window lane (`mechanical/scope_owner.py`, D138).

DB-less: the live read is a fixture, each refusal asserted by what it produces.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import scope_owner as S  # noqa: E402
from mechanical.identity_lanes import scope_window_lane  # noqa: E402
from mechanical.plan import PlanError  # noqa: E402

D138 = S.OWNER_RETIREMENTS["D138"]
CAUS = "1d54b3ce-6157-41bd-bd2f-4a42cf175919"
AYAZINI = "3f16cff5-f53f-4a81-9813-c80214933fd5"
LANE = scope_window_lane("2026-11-07")


def live(site_id: str, **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id,
        "source_id": "ancient_nerds",
        "name": D138.sites[site_id],
        "scope_status": None,
        "scope_reason": None,
        "premise": f"{D138.sites[site_id]} | x | 1 | 2 | England | NULL | NULL",
    }
    base.update(over)
    return base


def candidate(site_id: str) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "status": "scope-hold",
        "source_kind": "enwiki-lead",
        "epoch": "medieval",
        "url": "https://en.wikipedia.org/wiki/X",
        "quote": "a medieval castle",
        "scope": "a start of 1000 lies outside the D58 window",
    }


CANDIDATES = {CAUS: candidate(CAUS), AYAZINI: candidate(AYAZINI)}


def test_each_named_site_is_retired_with_the_owner_s_reason() -> None:
    changes, skipped = S.build(D138, {CAUS: live(CAUS), AYAZINI: live(AYAZINI)}, CANDIDATES, LANE)
    assert not skipped
    assert {(c.site_id, c.column, c.old_value, c.new_value) for c in changes} == {
        (sid, column, None, value)
        for sid in (CAUS, AYAZINI)
        for column, value in (("scope_status", "retired"), ("scope_reason", "D138 owner: medieval, out of scope"))
    }
    assert all("D138" in c.evidence[0]["source"] and c.premise for c in changes)
    assert all(c.finding_test_id == LANE.test_id and c.rule == "d138-owner-retire" for c in changes)


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"source_id": "lyra"}, "not-curated"),
        ({"name": "Caus Castle (renamed)"}, "renamed"),
        ({"scope_status": "retired", "scope_reason": "x"}, "already-retired"),
    ],
)
def test_a_site_that_moved_since_the_decision_is_skipped(over: dict[str, Any], reason: str) -> None:
    changes, skipped = S.build(D138, {CAUS: live(CAUS, **over), AYAZINI: live(AYAZINI)}, CANDIDATES, LANE)
    assert {c.site_id for c in changes} == {AYAZINI}
    assert [(s["site_id"], s["reason"]) for s in skipped] == [(CAUS, reason)]


def test_a_gone_site_is_skipped() -> None:
    changes, skipped = S.build(D138, {AYAZINI: live(AYAZINI)}, CANDIDATES, LANE)
    assert [(s["site_id"], s["reason"]) for s in skipped] == [(CAUS, "gone")]


def test_a_site_without_its_candidate_row_stops_the_plan() -> None:
    with pytest.raises(PlanError):
        S.build(D138, {CAUS: live(CAUS), AYAZINI: live(AYAZINI)}, {CAUS: candidate(CAUS)}, LANE)
