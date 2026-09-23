"""The journal-chain rule both the mechanical planners and the phase-3 acceptance judge with.

`scripts/remediation/journal_chain.py` holds the one continuity check (`first_break`) and the one
spelling of a reversal's stamp (`ROLLBACK_SUFFIX`). These tests pin the rule, and pin that every
writer's reversal stamp really ends in that suffix - a writer that named its undo differently would
be read as a write by the acceptance.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import journal_chain as J  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402


def test_a_continuous_chain_has_no_break() -> None:
    assert J.first_break([]) is None
    assert J.first_break([("a", "b")]) is None
    assert J.first_break([("a", "b"), ("b", "c"), ("c", None), (None, "d")]) is None


def test_a_link_that_starts_elsewhere_breaks_the_chain_at_its_index() -> None:
    assert J.first_break([("a", "b"), ("x", "c")]) == 1
    assert J.first_break([("a", "b"), ("b", "c"), ("b", "d"), ("q", "r")]) == 2


def test_null_and_the_empty_string_are_different_values() -> None:
    assert J.first_break([("a", None), ("", "b")]) == 1


def test_every_writer_names_its_reversal_with_the_suffix() -> None:
    from phase3 import write_stage

    assert write_stage.ROLLBACK_KEY_SUFFIX == J.ROLLBACK_SUFFIX
    for lane in L.LANES.values():
        assert J.is_rollback(lane.rollback_run_stamp)
        assert not J.is_rollback(lane.run_stamp)


def test_the_planners_use_the_shared_rule() -> None:
    """`plan.journal_break` names the link `first_break` found, and the one before it."""
    links = (
        P.JournalLink(1, "phase3:a", "P3/country", "Ireland", "United Kingdom"),
        P.JournalLink(2, "x", "t", "United Kingdom", "Northern Ireland"),
        P.JournalLink(7, "y", "t", "Wales", "England"),
    )
    reason, note = P.journal_break(links, "England") or ("", "")
    assert reason == "journal-chain-broken"
    assert "journal row 7 starts from 'Wales'" in note and "(2) ended at 'Northern Ireland'" in note
    assert P.journal_break(links[:2], "Northern Ireland") is None
    assert P.journal_break(links[:2], "Ireland") == (
        "journal-disagrees",
        "the last journal row (2, x) wrote 'Northern Ireland', the row holds 'Ireland' - "
        "something wrote it without the journal",
    )
