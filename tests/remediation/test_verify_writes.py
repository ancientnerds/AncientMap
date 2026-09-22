"""Does the phase-3 acceptance follow the journal chain - and stay strict while it does?

`output/remediation/tools/verify_writes.py` decides in a pure function (`judge`) from the plan, the
journal and the live values. These tests fabricate all three: a phase-3 write that stands, one that a
later journalled lane superseded (the B9 shape), a broken chain, a live value the journal does not
end at, and the planned fields phase 3 did not write. No database.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "output" / "remediation" / "tools" / "verify_writes.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("verify_writes", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_writes"] = module
    spec.loader.exec_module(module)
    return module


V = _load()

GIANTS_RING = "e0d56737-6459-4329-9ef5-1a46e8d75f10"
DAMASCUS = "17cf019a-0000-4000-8000-000000000001"
HELD = "22222222-2222-2222-2222-222222222222"
P3 = "phase3:batch-0148:chunk-0001"
UK = "2026-09-22_mechanical-uk-parts"


def planned(pk: str, column: str, old: Any) -> dict[str, Any]:
    return {"pk": pk, "column": column, "old_value": old, "site_name": f"site {pk[:4]}"}


def stored(country: str | None = None, period_start: str | None = None) -> list[str | None]:
    return ["Monument", period_start, country]  # COLUMNS order: site_type, period_start, country


def test_a_phase3_write_that_stands_is_accepted() -> None:
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("United Kingdom")},
    )
    assert verdict.deviations == [] and verdict.written == 1 and not verdict.superseded


def test_a_superseded_phase3_write_is_reported_by_stamp_not_as_a_deviation() -> None:
    """B9: phase 3 wrote `United Kingdom`, the UK lane respelled it `Northern Ireland`."""
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "United Kingdom", "Northern Ireland"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert verdict.deviations == []
    assert verdict.superseded == {UK: 1}


def test_a_broken_chain_is_a_deviation() -> None:
    links = [
        V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom"),
        V.Link(9, UK, "country", GIANTS_RING, "Wales", "Northern Ireland"),
    ]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert len(verdict.deviations) == 1 and "BROKEN CHAIN" in verdict.deviations[0]


def test_a_live_value_the_journal_does_not_end_at_is_a_deviation() -> None:
    """The per-row check this replaces, kept: an unjournalled write after phase 3 is caught."""
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge(
        [planned(GIANTS_RING, "country", "Ireland")],
        links,
        {GIANTS_RING: stored("Northern Ireland")},
    )
    assert len(verdict.deviations) == 1 and "NOT NEW" in verdict.deviations[0]


def test_a_missing_site_is_a_deviation() -> None:
    links = [V.Link(1, P3, "country", GIANTS_RING, "Ireland", "United Kingdom")]
    verdict = V.judge([planned(GIANTS_RING, "country", "Ireland")], links, {})
    assert verdict.deviations == [f"  MISSING      {GIANTS_RING} (country)"]
    held = V.judge([planned(HELD, "period_start", -500)], [], {})
    assert len(held.deviations) == 1 and "MISSING" in held.deviations[0]


def test_a_held_field_that_still_holds_its_old_value_is_accepted() -> None:
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], [], {HELD: stored(period_start="-500")}
    )
    assert verdict.deviations == [] and verdict.untouched == 1


def test_a_held_field_changed_without_a_journal_row_is_a_deviation() -> None:
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], [], {HELD: stored(period_start="-43000")}
    )
    assert len(verdict.deviations) == 1 and "CHANGED ANYWAY" in verdict.deviations[0]


def test_a_held_field_a_later_lane_journalled_is_superseded() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-43000")}
    )
    assert verdict.deviations == [] and verdict.superseded == {"2026-10-01_search": 1}


def test_a_later_chain_on_a_held_field_must_start_from_the_planned_old_value() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-700", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-43000")}
    )
    assert len(verdict.deviations) == 1 and "the plan had '-500'" in verdict.deviations[0]


def test_a_later_chain_on_a_held_field_must_end_at_the_live_value() -> None:
    links = [V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000")]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-40000")}
    )
    assert len(verdict.deviations) == 1 and "the row holds '-40000'" in verdict.deviations[0]


def test_a_later_chain_on_a_held_field_must_be_unbroken() -> None:
    links = [
        V.Link(5, "2026-10-01_search", "period_start", HELD, "-500", "-43000"),
        V.Link(6, "2026-10-02_search", "period_start", HELD, "-42000", "-40000"),
    ]
    verdict = V.judge(
        [planned(HELD, "period_start", -500)], links, {HELD: stored(period_start="-40000")}
    )
    assert len(verdict.deviations) == 1 and "starts from '-42000'" in verdict.deviations[0]


def test_a_field_outside_the_three_columns_is_not_judged() -> None:
    """period_name is not a phase-3 column; the period lane's rows are not this acceptance's."""
    links = [V.Link(7, P3, "period_name", DAMASCUS, "1 - 500 AD", "1500+ AD")]
    verdict = V.judge([], links, {})
    assert verdict.deviations == [] and verdict.written == 0
