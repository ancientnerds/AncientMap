"""Does `categorize_period` answer exactly what the site's own `categorizePeriod` shows?

`period_name` is displayed next to a globe colour computed from `period_start` by the frontend
(`ancient-nerds-map/src/data/sites.ts`), so the Python bucket is only right when it is the
frontend's bucket. The frontend compares upper bounds only; the comparisons are read from the
TypeScript source here, never copied, so a change on either side fails this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.utils.text import PERIOD_BUCKETS, categorize_period

REPO = Path(__file__).resolve().parents[2]
SITES_TS = REPO / "ancient-nerds-map" / "src" / "data" / "sites.ts"


def frontend_bucket(year: int) -> str:
    source = SITES_TS.read_text(encoding="utf-8")
    body = source.split("export function categorizePeriod", 1)[1].split("\n}", 1)[0]
    steps = re.findall(r"if \(start < (-?\d+)\) return '([^']+)'", body)
    last = re.search(r"\n  return '([^']+)'", body)
    assert steps and last, "categorizePeriod's comparisons were not found in sites.ts"
    for bound, label in steps:
        if year < int(bound):
            return label
    return last.group(1)


@pytest.mark.parametrize(
    "year",
    [
        -1_400_000,  # Atapuerca: below the table's -999999 floor
        -1_000_000,
        -999_999,
        -45_000,
        -4501,
        -4500,
        -3001,
        -3000,
        -1500,
        -501,
        -500,
        -1,
        0,
        1,
        499,
        500,
        999,
        1000,
        1499,
        1500,
        1760,  # Bayer's Lake Mystery Walls
        2014,
        999_999,
        1_000_000,
    ],
)
def test_the_python_bucket_is_the_frontend_bucket(year: int) -> None:
    assert categorize_period(year) == frontend_bucket(year)


def test_a_year_below_the_table_floor_is_the_deep_past() -> None:
    """Before 2026-09-22 this returned "1500+ AD": `lo <= year` failed and the loop fell through."""
    assert categorize_period(-1_400_000) == "< 4500 BC"


def test_no_year_is_no_bucket() -> None:
    assert categorize_period(None) is None


def test_every_bucket_is_reachable_and_there_are_no_others() -> None:
    labels = {label for label, _, _ in PERIOD_BUCKETS}
    reached = {categorize_period(hi - 1) for _, _, hi in PERIOD_BUCKETS}
    assert reached == labels
