"""Can a period band be written as a year? A band writes the edge of its bucket.

`period_start` holds one year, and the acceptance compares `period_name` against
`categorize_period(period_start)` (`mechanical/lane.py`), so a band may only be written as a year
that reads back as that band. Measured 2026-10-04 on the 511 `via: "band"` rows of
`output/remediation/fields/wd3/DERIVED.jsonl`: every one of them is the edge of its own bucket,
and 20 of them come from a band that is open on one side - "< 4500 BC" as -4501, "> 1500 AD" as
1500. Two measuring scripts of that day read the boundary as "a value outside the band" and
concluded an open band has no year at all; the owner's answer the same day: "if something is
Neolithic then it is < 4500 BC, that is logical". An open band carries its edge, so the rule is
named here and those 20 values rest on it instead of on a number somebody typed.
"""

from __future__ import annotations

import pytest

from pipeline.utils.text import PERIOD_BUCKETS, bucket_edge, categorize_period

#: Every bucket except the two that are open on one side, with the year it begins at.
CLOSED = [
    ("4500 - 3000 BC", -4500),
    ("3000 - 1500 BC", -3000),
    ("1500 - 500 BC", -1500),
    ("500 BC - 1 AD", -500),
    ("1 - 500 AD", 1),
    ("500 - 1000 AD", 500),
    ("1000 - 1500 AD", 1000),
]


@pytest.mark.parametrize(("label", "edge"), CLOSED)
def test_a_closed_band_writes_its_own_beginning(label: str, edge: int) -> None:
    assert bucket_edge(label) == edge


def test_a_band_open_below_writes_the_nearest_year_it_still_contains() -> None:
    """4500 BC is the first year of the *next* bucket, so "< 4500 BC" writes 4501 BC."""
    assert bucket_edge("< 4500 BC") == -4501
    assert categorize_period(-4501) == "< 4500 BC"
    assert categorize_period(-4500) == "4500 - 3000 BC"


def test_a_band_open_above_writes_its_first_year() -> None:
    assert bucket_edge("1500+ AD") == 1500
    assert categorize_period(1500) == "1500+ AD"


@pytest.mark.parametrize("label", [label for label, _, _ in PERIOD_BUCKETS])
def test_every_band_writes_a_year_that_reads_back_as_that_band(label: str) -> None:
    """The acceptance compares the name against `categorize_period(period_start)`, so a band that
    does not round-trip would be refused in production, not here."""
    assert categorize_period(bucket_edge(label)) == label


def test_the_edge_is_the_year_nearest_the_present_that_the_band_holds() -> None:
    """The rule in one line, checked against the table rather than against a list of answers: for
    every bucket but the first the edge is its own lower bound, and the first bucket's -999999 is a
    range-filter bound (`categorize_period`), so its edge is the year before its upper bound."""
    edges = {label: bucket_edge(label) for label, _, _ in PERIOD_BUCKETS}
    for index, (label, lo, hi) in enumerate(PERIOD_BUCKETS):
        assert edges[label] == (hi - 1 if index == 0 else lo), label


def test_a_period_name_is_not_a_band_and_is_refused_by_name() -> None:
    """The buckets are the nine band labels; "Iron Age" is one of the 99 period names and belongs
    to the other table, so it is refused instead of guessed into a year."""
    with pytest.raises(ValueError, match="Iron Age"):
        bucket_edge("Iron Age")
