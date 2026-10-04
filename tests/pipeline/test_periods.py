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

#: The names the table did not know, measured 2026-10-04 by reading all 1,849 `unresolved` answers of
#: lane WD3 (`output/remediation/fields/wd3/DECISIONS.jsonl`): `(name, range, mentions)`. A name is
#: here because the run's own answers used it as the period, and its range is the conventional span
#: of that period or culture - read on the source `pipeline/periods.py` names in its comment. The
#: counts are written out because `output/` is a gitignored snapshot.
DEMANDED = (
    ("achaemenid", (-550, -330), 2),
    ("byzantine", (330, 1453), 10),
    ("chanka", (1200, 1500), 9),
    ("classical", (-510, -323), 5),
    ("early modern", (1500, 1800), 1),
    ("etruscan", (-900, -27), 1),
    ("funnelbeaker", (-4100, -2800), 2),
    ("geometric", (-900, -700), 2),
    ("han", (-202, 220), 2),
    ("harappan", (-2600, -1900), 4),
    ("helladic", (-3200, -1050), 7),
    ("iberian", (-700, -100), 1),
    ("inca", (1438, 1533), 56),
    ("indus valley", (-3300, -1300), 2),
    ("late middle ages", (1300, 1500), 2),
    ("middle helladic", (-2000, -1550), 3),
    ("minoan", (-3100, -1100), 10),
    ("mycenaean", (-1750, -1050), 10),
    ("nabataean", (-250, 106), 2),
    ("new kingdom", (-1550, -1069), 2),
    ("nuragic", (-1800, -238), 1),
    ("old kingdom", (-2686, -2181), 1),
    ("ottoman", (1299, 1922), 2),
    ("phoenician", (-1500, -332), 3),
    ("safavid", (1501, 1736), 1),
    ("slavic", (500, 1000), 1),
    ("viking age", (793, 1066), 1),
)

#: The names the same answers used that are NOT periods, and how often: a `site_type` is another
#: field's value, a people and a dynasty word name no span, and `modern` would date modern
#: institutions - a decision for the owner, not for this table (owner decision 2026-10-04).
NOT_PERIODS = {
    "hillfort": 112, "hill fort": 66, "broch": 13, "oppidum": 2, "motte": 2, "clava cairn": 1,
    "modern": 35, "greek": 16, "dynasty": 5,
}

#: The demanded names that stay refused by name, and why. A missing name is safe - the agent is
#: told the name and falls back to the period its own quote carries - a wrong year is not.
REFUSED = {
    "archaic": "the table holds `archaic greece`, which starts at the same year (-800)",
    "celtic": "no conventional start of its own: the Iron Age phases it names are `hallstatt` and "
              "`la tene`, and the span it would get is `iron age`'s",
    "celts": "a people, not a period - the same word as `celtic`",
    "persian": "two empires share the word, the Achaemenid from 550 BC and the Sasanian from "
               "AD 224; `achaemenid` is the name this table knows",
    "roman british": "`romano british period` is the name this table holds",
    "thracian": "no conventionally cited start for a 'Thracian period'; the state would be the "
                "Odrysian kingdom, which is another name",
}


class TestTheTolerantLookup:
    """Four keys carry a trailing " period", so an agent that sends the bare word names an era the
    table knows and was refused for it: "Hellenistic" (21 mentions), "Romano-British" (13),
    "Migration", and - now that `inca` is a name - "the Inca period" (7)."""

    #: (the name an agent sends, the key the table holds) - one era, one name in each spelling
    BARE = (
        ("Hellenistic", "hellenistic period"),
        ("Romano-British", "romano british period"),
        ("Migration", "migration period"),
        ("Mesoamerican Preclassic", "mesoamerican preclassic period"),
        ("Inca period", "inca"),
    )

    @pytest.mark.parametrize(("sent", "key"), BARE)
    def test_the_bare_word_and_the_keyed_name_are_one_period(self, sent: str, key: str) -> None:
        assert P.period_of(sent) == P.period_of(key)
        assert P.start_year(sent) == P.period_of(key)[0]

    def test_a_quote_may_state_the_period_the_bare_name_names(self) -> None:
        # the one reader that decides a period answer: a bare name that resolves to years but is
        # not in the table under that spelling would pass the year and fail the quote
        assert P.states_period("a Hellenistic fortress on the hill", "Hellenistic")
        assert P.states_period("a fortress of the 3rd century BC", "Hellenistic") is False

    def test_only_the_word_period_is_read_both_ways(self) -> None:
        # "age" and "era" are not dropped: "iron", "late" and "migration age" would be eras
        for name in ("iron", "late", "migration age", "Klingon period"):
            with pytest.raises(P.PeriodError, match="not one of"):
                P.period_of(name)

    def test_a_name_the_table_does_not_know_stays_refused_by_name(self) -> None:
        with pytest.raises(P.PeriodError, match="Klingon period"):
            P.period_of("Klingon period")
        assert not P.states_period("a hillfort of the Iron Age", "Klingon period")


class TestTheNamesTheRunUsed:
    @pytest.mark.parametrize(("name", "span", "mentions"), DEMANDED)
    def test_a_demanded_name_gets_its_conventional_span(
        self, name: str, span: tuple[int, int], mentions: int
    ) -> None:
        assert P.period_of(name) == span, name
        assert P.start_year(name) == span[0], name
        assert mentions > 0  # the count the run's own 1,849 answers gave the name

    def test_a_new_name_does_not_disturb_a_name_it_shares_a_range_with(self) -> None:
        # two names one era is the table's habit, not a new fact about it
        assert P.period_of("viking age") == P.period_of("viking")
        assert P.period_of("harappan") == (-2600, -1900) != P.period_of("indus valley")

    @pytest.mark.parametrize(("name", "why"), sorted(REFUSED.items()))
    def test_a_name_without_a_defensible_start_stays_refused(self, name: str, why: str) -> None:
        assert why  # the reason travels with the name
        with pytest.raises(P.PeriodError, match="not one of"):
            P.period_of(name)
        assert not P.states_period("a site of that period", name)

    @pytest.mark.parametrize(("name", "mentions"), sorted(NOT_PERIODS.items()))
    def test_a_word_that_is_no_period_is_no_name(self, name: str, mentions: int) -> None:
        # a site_type is site_type's value, and `modern` would date modern institutions
        assert P.fold_name(name) not in P.PERIODS, f"{name} ({mentions} mentions)"
        with pytest.raises(P.PeriodError):
            P.period_of(name)


class TestTheTable:
    def test_canmore_s_own_seven_stay_first_and_in_his_order(self) -> None:
        # the ingester walks the table and takes the first key its upper-cased SITETYPE contains,
        # so a name added in front of these seven would move a range a pipeline run has written
        assert list(P.PERIODS)[: len(CANMORE)] == [k.lower() for k in CANMORE]

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
