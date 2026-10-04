"""The period vocabulary of `pipeline/periods.py`.

The table exists because the research was done and thrown away: measured on 2026-10-04 in
`output/remediation/fields/wd3/DECISIONS.jsonl`, 792 of the 1,338 `unresolved` period_start
answers name a period in their own reasoning (iron age 366, roman 243, bronze age 192, neolithic
171, prehistoric 43) and 677 of them name one a table can turn into years. The owner's decision of
2026-10-04: a named period IS a value.

The names the vocabulary must know are measured twice over: the round-0 answers above, and the 34
distinct `time period` (P2348) items of the 2,029 curated sites that still have no period
(`output/remediation/period_wave/period_labels.json`, resolved with one read-only `wbgetentities`).
They are written out here because `output/` is a gitignored snapshot: a test that reads it would
pass in this checkout and fail in a clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import periods as P
from pipeline.ingesters import canmore_scotland as CS
from pipeline.utils.text import PERIOD_BUCKETS

#: The 34 P2348 labels measured 2026-10-04, as the labels are spelled in Wikidata.
WIKIDATA_LABELS = (
    "Ancient Greece", "Romano-British period", "Roman Empire", "British Iron Age", "Bronze Age",
    "Iron Age", "Classical Antiquity", "Neolithic", "Middle Paleolithic", "Chalcolithic",
    "Fourth Dynasty of Egypt", "British Bronze Age", "Paleolithic", "Ancient Rome",
    "Hellenistic period", "Pre-Pottery Neolithic B", "Late Pleistocene", "Pleistocene", "Tiwanaku",
    "Silurian", "Carboniferous", "Archaic Greece", "Middle Ages", "Stone Age",
    "Mesoamerican Preclassic period", "Upper Paleolithic", "Ancient history", "Late antiquity",
    "Roman Britain", "Maya civilization", "Eighteenth Dynasty of Egypt", "Mesolithic",
    "prehistory", "Guanches",
)

#: The names round 0's dropped answers used, in the spelling the brief lists them.
ANSWER_NAMES = (
    "palaeolithic", "upper palaeolithic", "mesolithic", "early mesolithic", "late mesolithic",
    "neolithic", "early neolithic", "middle neolithic", "late neolithic", "chalcolithic",
    "copper age", "bronze age", "early bronze age", "late bronze age", "iron age",
    "early iron age", "late iron age", "hallstatt", "la tene", "roman", "roman imperial",
    "migration period", "saxon", "anglo-saxon", "frankish", "merovingian", "carolingian",
    "early medieval", "high medieval", "medieval", "post medieval", "post-medieval", "georgian",
    "victorian", "edwardian", "prehistoric", "late prehistoric",
    # The four names the dropped round-0 answers used that the first pass of this table refused.
    # Measured 2026-10-04 by reading all 1,338 unresolved period answers: "middle bronze age" and
    # "middle iron age" are not slots between the early/late halves this table splits into, and
    # "lower paleolithic" and "viking" were simply missing. A name the vocabulary refuses is refused
    # by name, which costs the answer: the agent has to fall back to the parent period, so the four
    # belong here.
    "middle bronze age", "middle iron age", "lower paleolithic", "viking",
)

#: Canmore's own seven, with the ranges its `PERIOD_DATES` held before the move (the ingester's
#: result must not move: a pipeline run is a write of `unified_sites`).
CANMORE = {
    "PREHISTORIC": (-10000, -800),
    "NEOLITHIC": (-4000, -2500),
    "BRONZE AGE": (-2500, -800),
    "IRON AGE": (-800, 400),
    "ROMAN": (43, 410),
    "EARLY MEDIEVAL": (400, 1100),
    "MEDIEVAL": (1100, 1500),
}


class TestTheTable:
    @pytest.mark.parametrize("label", WIKIDATA_LABELS)
    def test_every_wikidata_time_period_resolves(self, label: str) -> None:
        start, end = P.period_of(label)
        assert isinstance(start, int) and isinstance(end, int) and start <= end

    def test_a_name_the_vocabulary_does_not_know_is_refused_by_name(self) -> None:
        with pytest.raises(P.PeriodError) as raised:
            P.period_of("Klingon Age")
        assert "Klingon Age" in str(raised.value)
        assert f"the {len(P.PERIODS)} names" in str(raised.value)
        with pytest.raises(P.PeriodError, match="not a name"):
            P.period_of("   ")

    def test_two_names_may_share_a_range_and_each_maps_to_exactly_one(self) -> None:
        assert P.period_of("chalcolithic") == P.period_of("copper age")
        assert P.period_of("saxon") == P.period_of("anglo-saxon")
        for name, (start, end) in P.PERIODS.items():
            assert isinstance(start, int) and isinstance(end, int), name
            assert start <= end, name
            assert -3_000_000 <= start and end <= 2026, name  # answers.YEARS' own bounds

    def test_the_start_is_the_year_a_period_word_writes(self) -> None:
        assert P.start_year("iron age") == -800
        assert P.start_year("neolithic") == -4000
        assert P.start_year("victorian") == 1837

    def test_no_bucket_label_is_a_period_name(self) -> None:
        # `period_name` is an archaeological or geological word, never one of the nine bands the
        # curated database holds: an answer that named a band would only restate what is stored
        for label, _, _ in PERIOD_BUCKETS:
            assert P.fold_name(label) not in P.PERIODS, label


class TestTheQuote:
    def test_a_quote_states_the_period_it_names(self) -> None:
        assert P.states_period("an Iron Age hillfort", "iron age")
        assert P.states_period("a hillfort of the BRITISH iron age", "british iron age")
        assert P.states_period("designed in the 19th century", "victorian") is False

    def test_a_period_word_inside_another_word_is_no_period(self) -> None:
        # "iron" alone is not the Iron Age: a quarry is not a period
        assert not P.states_period("an iron mine", "iron age")
        assert not P.states_period("a Romano-British fort of the 2nd century", "roman britain")
        assert P.states_period("a Romano-British fort", "romano-british period")

    def test_an_unknown_name_states_nothing(self) -> None:
        assert not P.states_period("an Iron Age hillfort", "klingon age")


class TestTheCentury:
    def test_a_century_is_the_hundred_years_it_names(self) -> None:
        assert P.century_range("19th century") == (1801, 1900)
        assert P.century_range("the 2nd century AD") == (101, 200)
        assert P.century_range("3rd century BC") == (-299, -200)
        assert P.century_range("5th c. BC") == (-499, -400)
        # Canmore writes its periods in caps without a marker: 84,442 of its records carry only
        # such a century word (measured 2026-10-04, data/raw/canmore_scotland), and a century
        # without a BC marker is AD
        assert P.century_range("19TH CENTURY") == (1801, 1900)
        assert P.century_range("3RD C") == (201, 300)

    def test_its_first_or_second_half(self) -> None:
        assert P.century_range("early 19th century") == (1801, 1850)
        assert P.century_range("late 19th century") == (1851, 1900)
        assert P.century_range("early 3rd century BC") == (-299, -250)

    def test_what_is_not_a_century_is_none(self) -> None:
        for text in ("nineteenth century", "the Iron Age", "3rd millennium BC", "century", "19th"):
            assert P.century_range(text) is None, text
        # a half the vocabulary does not know is refused, not rounded to a whole century
        assert P.century_range("middle 19th century") is None
        assert P.century_range("0th century") is None


INGESTER = CS.CanmoreScotlandIngester


def mapped(period: str) -> tuple[int | None, int | None]:
    return INGESTER._map_period(INGESTER, period)


class TestTheIngester:
    def test_canmore_reads_the_ranges_it_defined_before(self) -> None:
        for period, (start, end) in CANMORE.items():
            assert CS.PERIOD_DATES[period.lower()] == (start, end)
            assert mapped(period) == (start, end)

    def test_the_table_lives_once(self) -> None:
        assert CS.PERIOD_DATES is P.PERIODS
        source = Path(CS.__file__).read_text(encoding="utf-8")
        assert "PERIOD_DATES = {" not in source  # the ingester names the table, the module owns it

    def test_the_general_period_wins_a_qualified_raw_value_as_it_did_before(self) -> None:
        # Canmore's loop takes the first table key contained in the upper-cased period, so the
        # seven keys it had must stay in front: "EARLY IRON AGE" mapped to the Iron Age range
        assert mapped("EARLY IRON AGE") == (-800, 400)
        assert mapped("LATE BRONZE AGE") == (-2500, -800)
        assert mapped("PREHISTORIC") == (-10000, -800)
        assert mapped("19TH CENTURY") == (None, None)
