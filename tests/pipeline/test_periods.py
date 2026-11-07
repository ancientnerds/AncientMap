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

import ast
from pathlib import Path

import pytest

from pipeline import periods as P
from pipeline.ingesters import canmore_scotland as CS
from pipeline.utils.text import PERIOD_BUCKETS, bucket_edge, categorize_period

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
    # lane WD5 (2026-10-09): the regional names that two regions spell alike or that have no one
    # start, kept out when the regional chronologies went in
    "early dynastic": "Egypt's Early Dynastic Period starts c. 3000 BC, Mesopotamia's c. 2900 BC "
                      "and a quote that says only the two words does not say which",
    "late period": "Egypt's Late Period (664 BC) and every other region's 'late period' share the "
                   "words",
    "formative": "the Mesoamerican Formative (2000 BC, = Preclassic) and the Andean (Initial "
                 "Period and Early Horizon, 1800 BC) are not one span",
    "preceramic": "the Andean Preceramic, the Near Eastern Pre-Pottery Neolithic and the "
                  "Archaic of the Americas share no start",
    "islamic": "the conquest reached each region in another century",
    "mousterian": "the start of a lithic industry differs by region and dating method: a "
                  "calendar or BP date is the reader's job, not a table row",
    "aurignacian": "as `mousterian`",
    "magdalenian": "as `mousterian`",
    "dilmun": "no conventional start was sourced for the Gulf civilisation",
    "hohokam": "no conventional start was sourced",
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
        assert P.start_year(sent, country=None) == P.period_of(key)[0]

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
        assert P.start_year(name, country=None) == span[0], name
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
        # a period of one start everywhere ignores the country; a regional one reads it (D101)
        assert P.start_year("victorian", country=None) == 1837
        assert P.start_year("victorian", country="Wales") == 1837
        assert P.start_year("iron age", country="England") == -800
        assert P.start_year("neolithic", country="England") == -4000

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


#: The regional names lane WD5 added (2026-10-09), the span the source its comment in
#: `pipeline/periods.py` names gives: `(name, (start, end), a quote that names it)`. The quote is
#: the kind of sentence a page prints, so the table is held to what a source can state.
REGIONAL = (
    ("preclassic", (-2000, 250), "Kaminaljuyu is a Preclassic site"),
    ("early preclassic", (-2000, -1000), "an Early Preclassic village"),
    ("middle preclassic", (-1000, -400), "occupied from the Middle Preclassic period"),
    ("late preclassic", (-400, 250), "a Late Preclassic temple platform"),
    ("classic", (250, 900), "the city flourished in the Classic period"),
    ("early classic", (250, 600),
     "Chitinamit dates from the Early Classic through to the Late Postclassic periods"),
    ("late classic", (600, 900), "its stelae are Late Classic"),
    ("terminal classic", (800, 1000), "a Terminal Classic reoccupation"),
    ("postclassic", (900, 1521), "a Postclassic fortified town"),
    ("early postclassic", (900, 1200), "the Early Postclassic phase"),
    ("late postclassic", (1200, 1521),
     "Chitinamit dates from the Early Classic through to the Late Postclassic periods"),
    ("initial period", (-1800, -900), "a ceremonial centre of the Initial Period"),
    ("early horizon", (-900, -200), "Early Horizon pottery"),
    ("early intermediate period", (-200, 600), "a cemetery of the Early Intermediate Period"),
    ("middle horizon", (600, 1000), "a Middle Horizon administrative centre"),
    ("late intermediate period", (1000, 1476), "built in the Late Intermediate period"),
    ("late horizon", (1476, 1532), "two Andean settlements of the Late Horizon"),
    ("chavin", (-900, -200), "a Chavin temple"),
    ("wari", (600, 1100), "a Wari outpost"),
    ("moche", (100, 800), "a Moche pyramid"),
    ("woodland", (-1000, 1000), "a Woodland period burial mound"),
    ("early woodland", (-1000, -200), "an Early Woodland camp"),
    ("middle woodland", (-200, 500), "a Middle Woodland earthwork"),
    ("late woodland", (500, 1000), "a Late Woodland village"),
    ("mississippian", (1000, 1600), "a Mississippian town"),
    ("predynastic", (-5300, -3000), "a Predynastic cemetery"),
    ("first intermediate period", (-2181, -2055), "tombs of the First Intermediate Period"),
    ("middle kingdom", (-2055, -1650), "a Middle Kingdom fortress"),
    ("second intermediate period", (-1650, -1550), "the Second Intermediate Period capital"),
    ("third intermediate period", (-1069, -664), "Third Intermediate Period burials"),
    ("ptolemaic", (-305, -30), "a Ptolemaic temple"),
    ("early minoan", (-3100, -2100), "an Early Minoan tomb"),
    ("middle minoan", (-2100, -1600), "Middle Minoan pottery"),
    ("late minoan", (-1600, -1100), "a Late Minoan villa"),
    ("early helladic", (-3200, -2000), "an Early Helladic settlement"),
    ("late helladic", (-1600, -1050), "a Late Helladic chamber tomb"),
    ("early cycladic", (-3200, -2000), "an Early Cycladic cemetery"),
    ("middle cycladic", (-2000, -1600), "a Middle Cycladic phase"),
    ("late cycladic", (-1600, -1050), "a Late Cycladic phase"),
    ("uruk", (-4000, -3100), "an Uruk period outpost"),
    ("jemdet nasr", (-3100, -2900), "Jemdet Nasr tablets"),
    ("akkadian", (-2334, -2154), "an Akkadian palace"),
    ("ur iii", (-2112, -2004), "an Ur III temple"),
    ("old babylonian", (-2004, -1595), "an Old Babylonian house"),
    ("neo assyrian", (-911, -609), "a Neo-Assyrian palace"),
    ("neo babylonian", (-626, -539), "a Neo-Babylonian temple"),
    ("hittite", (-1650, -1178), "a Hittite fortress"),
    ("seleucid", (-312, -63), "a Seleucid foundation"),
    ("parthian", (-247, 224), "a Parthian fort"),
    ("sasanian", (224, 651), "a Sasanian fire temple"),
    ("sassanid", (224, 651), "a Sassanid fort"),
    ("mauryan", (-322, -185), "a Mauryan pillar"),
    ("kushan", (30, 375), "a Kushan stupa"),
    ("kushana", (30, 375), "a Kushana monastery"),
    ("gupta", (320, 550), "a Gupta temple"),
    ("zhou", (-1046, -256), "a Zhou tomb"),
    ("jomon", (-14000, -300), "a Jomon shell midden"),
    ("yayoi", (-300, 300), "a Yayoi settlement"),
    ("kofun", (300, 538), "a Kofun burial mound"),
    ("three kingdoms of korea", (-57, 668), "a fortress of the Three Kingdoms of Korea"),
    ("silla", (-57, 935), "a Silla tomb"),
    ("goguryeo", (-37, 668), "a Goguryeo fortress"),
    ("koguryo", (-37, 668), "a Koguryo mural tomb"),
    ("baekje", (-18, 660), "a Baekje capital"),
    ("roman republic", (-509, -27), "a Roman Republic colony"),
    ("augustan", (-27, 14), "an Augustan theatre"),
    ("flavian", (69, 96), "a Flavian amphitheatre"),
)


class TestTheRegionalChronologies:
    @pytest.mark.parametrize(("name", "span", "quote"), REGIONAL)
    def test_a_regional_name_has_its_span_and_a_quote_states_it(
        self, name: str, span: tuple[int, int], quote: str
    ) -> None:
        assert P.period_of(name) == span, name
        if not P.is_regional(name):  # a regional start needs the country (D101): see below
            assert P.start_year(name, country=None) == span[0]
        # the quote of a source names the period; the name an agent sends may be the bare word
        assert P.states_period(quote, name), (name, quote)

    def test_the_chitinamit_sentence_is_a_period_the_table_reads(self) -> None:
        # the WD5 pilot's 'Chitinamit': three Wikipedias said it, and the table did not hold the name
        quote = "Chitinamit dates from the Early Classic through to the Late Postclassic periods"
        assert P.start_year("Early Classic", country=None) == 250
        assert P.states_period(quote, "Early Classic period")
        assert P.states_period(quote, "late postclassic")
        assert not P.states_period(quote, "late classic")  # a neighbour is not named

    def test_a_name_is_spelled_once_in_the_table(self) -> None:
        # a dict literal that holds a key twice keeps the last value without a word
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        literal = next(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "PERIODS"
        )
        keys = [k.value for k in literal.keys if isinstance(k, ast.Constant)]
        assert len(keys) == len(set(keys)) == len(P.PERIODS)
        assert all(P.fold_name(k) == k for k in keys), "a key is its own folded spelling"

    def test_every_regional_start_is_a_year_an_answer_can_carry(self) -> None:
        for name, (start, end), _ in REGIONAL:
            assert -3_000_000 <= start <= end <= 2026, name

    def test_the_new_names_leave_canmore_s_old_mapping_alone(self) -> None:
        # the ingester takes the first key its period contains: the new names are all behind the
        # first seven, so a value that mapped before maps to the same range
        for period, span in CANMORE.items():
            assert mapped(period) == span
        assert mapped("EARLY BRONZE AGE") == (-2500, -800)  # `bronze age` still comes first


class TestTheOrdinaryWordsThatAreAlsoNames:
    """`classic` and `initial period` are English words when small: only the capitalised spelling
    of a source names the Mesoamerican and the Andean period."""

    def test_the_capitalised_spelling_names_the_period(self) -> None:
        assert P.states_period("the Classic period city of Tikal", "classic")
        assert P.states_period("an Early Classic temple", "early classic")
        assert P.states_period("a ceremonial centre of the Initial Period", "Initial Period")
        assert P.states_period("a village of the Initial period", "initial period")
        assert P.states_period("a village of the Initial period", "Initial")  # the bare word, read
        assert P.states_period("a Woodland period camp in Ohio", "woodland")
        assert P.states_period("Classic Maya cities rose", "classic")  # a sentence start, named whole
        assert P.states_period("Initial Period ceramics", "initial period")
        assert P.states_period("It is old. Woodland Period pottery was found.", "woodland")

    @pytest.mark.parametrize(
        ("quote", "name"),
        [
            ("a classic example of a platform mound", "classic"),
            ("in the initial period of the excavation", "initial period"),
            ("the initial period of occupation", "initial"),
            ("the CLASSIC trench", "classic"),  # not the spelling of a source naming an era
            ("a Classical temple", "classic"),  # another word that begins alike
            ("The hillfort lies within ancient woodland above the river", "woodland"),
            ("a woodland clearing with a barrow", "woodland"),
            # a sentence begins with a capital: the name needs its next word capitalised too
            ("Classic examples of the type are known.", "classic"),
            ("Initial period of occupation was short.", "initial period"),
            ("Woodland pottery was found in the ditch.", "woodland"),
            ("It is old. Woodland pottery was found.", "woodland"),
        ],
    )
    def test_the_small_spelling_and_a_longer_word_name_nothing(self, quote: str, name: str) -> None:
        assert not P.states_period(quote, name)

    def test_the_whole_of_the_name_is_needed_for_the_initial_period(self) -> None:
        assert not P.states_period("an Initial design", "initial period")
        assert not P.states_period("an Initial Perio", "initial period")


class TestTheRegionalStarts:
    """Owner decision D101 (2026-11-06): a bare period word maps to the start of that period in the
    site's own region, never to one fixed year. "Neolithic" was -4000 - Britain's start - for every
    site, so a Neolithic settlement in Jordan or Syria (Palmyra, D57) was written six millennia late
    and into the wrong band."""

    def test_the_near_eastern_neolithic_begins_with_the_pre_pottery_neolithic_a(self) -> None:
        for country in ("Jordan", "Syria", "Israel", "Iraq", "Türkiye", "Turkey", "Lebanon"):
            assert P.start_year("neolithic", country=country) == -10000, country
        assert P.start_year("Neolithic", country="Iran") == -8200
        assert P.start_year("early neolithic", country="Jordan") == -10000
        # a bucket the map shows: "< 4500 BC", not Britain's "4500 - 3000 BC"
        assert categorize_period(P.start_year("neolithic", country="Jordan")) == "< 4500 BC"

    def test_the_british_neolithic_keeps_its_start(self) -> None:
        for country in ("England", "Scotland", "Wales", "Northern Ireland", "Ireland"):
            assert P.start_year("neolithic", country=country) == -4000, country
        assert categorize_period(-4000) == "4500 - 3000 BC"

    def test_europe_is_read_country_by_country(self) -> None:
        assert P.start_year("neolithic", country="Greece") == -6500
        assert P.start_year("neolithic", country="Germany") == -5500
        assert P.start_year("neolithic", country="Denmark") == -4000
        # a bare "Bronze Age" in Greece is too coarse since D111 (see TestTheCoarseWords); its
        # early phase starts where the Bronze Age does
        assert P.start_year("early bronze age", country="Greece") == -3200
        assert P.start_year("bronze age", country="Denmark") == -2000
        assert P.start_year("iron age", country="Italy") == -900
        assert P.start_year("iron age", country="Sweden") == -500
        assert P.start_year("chalcolithic", country="Bulgaria") == -5000
        assert P.start_year("copper age", country="Spain") == P.start_year(
            "chalcolithic", country="Spain"
        )

    def test_roman_is_the_roman_period_of_the_province(self) -> None:
        assert P.start_year("roman", country="England") == 43
        assert P.start_year("roman", country="Wales") == 48
        assert P.start_year("roman", country="Scotland") == 71
        assert P.start_year("Roman", country="Spain") == -218
        assert P.start_year("roman", country="Portugal") == -218
        assert P.start_year("roman", country="Egypt") == -30
        # Roman Britain and Roman Hispania lie in different bands of the map
        assert categorize_period(43) == "1 - 500 AD"
        assert categorize_period(-218) == "500 BC - 1 AD"

    def test_the_roman_eras_follow_the_province(self) -> None:
        # the Empire begins in 27 BC, in a later province when that province's Roman period does
        assert P.start_year("roman empire", country="Italy") == -27
        assert P.start_year("roman empire", country="Spain") == -27
        assert P.start_year("roman imperial", country="England") == 43
        # a province annexed after the Republic ended has no Republican period
        assert P.start_year("roman republic", country="Spain") == -218
        with pytest.raises(P.PeriodError, match="no cited start for 'England'"):
            P.start_year("roman republic", country="England")

    def test_a_regional_period_needs_the_country(self) -> None:
        for country in (None, "", "  "):
            with pytest.raises(P.PeriodError, match="needs the site's country"):
                P.start_year("neolithic", country=country)

    def test_a_country_without_a_cited_start_gets_no_year(self) -> None:
        # never another region's year: Italy was Rome's own land, not a province; Ireland was
        # never Roman; Peru has no Neolithic in this sense
        for name, country in (("roman", "Italy"), ("roman", "Ireland"), ("neolithic", "Peru")):
            with pytest.raises(P.PeriodError, match=f"no cited start for '{country}'"):
                P.start_year(name, country=country)
        # the British sub-phases are British
        with pytest.raises(P.PeriodError, match="no cited start"):
            P.start_year("late neolithic", country="Jordan")
        assert P.start_year("late neolithic", country="England") == -2900

    def test_a_country_is_read_as_its_last_comma_part_folded(self) -> None:
        assert P.country_key("Cusco, Peru") == "peru"
        assert P.country_key("Türkiye") == "turkiye"
        assert P.start_year("neolithic", country="The Netherlands") == -5200

    def test_a_non_regional_period_is_one_year_everywhere(self) -> None:
        assert not P.is_regional("victorian")
        assert P.is_regional("Neolithic") and P.is_regional("roman")
        assert P.start_year("hellenistic", country="Peru") == -323

    def test_the_regional_table_is_part_of_the_vocabulary(self) -> None:
        for key, table in P.REGIONAL_STARTS.items():
            assert key in P.PERIODS, key
            assert table, key
            for country, year in table.items():
                assert P.fold_name(country) == country, (key, country)
                assert -3_000_000 <= year <= 2026, (key, country)

    def test_canmore_still_reads_the_conventional_ranges(self) -> None:
        # the ingester maps a Scottish SITETYPE period on PERIODS, which D101 leaves alone
        assert P.PERIODS["neolithic"] == (-4000, -2500)
        assert P.period_of("roman") == (43, 410)


class TestTheCoarseWords:
    """Owner decision D111 (2026-11-06, the D99 pilot): a coarse period word gives no year. "Stone
    Age" and "Palaeolithic" were the table edge -3,000,000 (Čertova pec was confirmed at it, Rock
    Carvings at Åsli in ice-covered Arctic Norway were proposed at it), "prehistoric", "ancient" and
    "antiquity" name no start a site has, and a bare "Bronze Age" in a country whose table divides
    it into phases took the start of two millennia for a site of one phase (Bant's Carn, "built =
    Middle Bronze Age")."""

    COARSE = (
        "stone age", "Stone Age", "palaeolithic", "Paleolithic", "the Palaeolithic period",
        "prehistoric", "Prehistory", "ancient history", "Classical Antiquity",
    )  # fmt: skip

    @pytest.mark.parametrize("name", COARSE)
    def test_a_coarse_word_gives_no_year(self, name: str) -> None:
        for country in (None, "England", "Czechia", "Norway", "Peru"):
            with pytest.raises(P.PeriodError, match="too coarse"):
                P.start_year(name, country=country)
        # the span stays in the vocabulary: Canmore and the span readers read it
        assert P.period_of(name)

    def test_a_named_phase_of_the_palaeolithic_keeps_its_year(self) -> None:
        assert P.start_year("lower palaeolithic", country=None) == -3000000
        assert P.start_year("Middle Paleolithic", country="Czechia") == -300000
        assert P.start_year("upper palaeolithic", country="England") == -50000

    def test_a_bare_bronze_age_needs_its_phase_where_the_table_divides_it(self) -> None:
        for country in ("England", "Wales", "Ireland", "Greece", "Türkiye", "Jordan", "France",
                        "Italy"):  # fmt: skip
            with pytest.raises(P.PeriodError, match="sub-phase"):
                P.start_year("bronze age", country=country)
        assert P.start_year("middle bronze age", country="England") == -1500
        assert P.start_year("early bronze age", country="Türkiye") == -3300
        # one undivided Bronze Age keeps its start
        assert P.start_year("bronze age", country="Denmark") == -2000
        assert P.start_year("bronze age", country="Spain") == -1900
        assert P.start_year("bronze age", country="Germany") == -2300
        assert P.start_year("bronze age", country="Egypt") == -3150

    def test_a_bare_iron_age_keeps_its_year(self) -> None:
        # D112 writes Moel y Gest at Wales' Iron Age start: the British Iron Age (800 BC - AD 43)
        # is a precise enough epoch, its middle/late phases keep their own years (D113 item 5)
        assert P.start_year("iron age", country="Wales") == -800
        assert P.start_year("late iron age", country="England") == -100

    def test_the_coarse_words_are_names_of_the_vocabulary(self) -> None:
        for key in P.COARSE:
            assert key in P.PERIODS, key
        for key, countries in P.SUBPHASE_REQUIRED.items():
            assert key in P.REGIONAL_STARTS, key
            assert countries <= set(P.REGIONAL_STARTS[key]), key


class TestTheD113Fills:
    """Owner decision D113 item 3 (2026-11-06): the country and epoch starts the dating lanes hit
    without one, each cited from the English Wikipedia article its comment in `pipeline/periods.py`
    names. A country whose articles give no single start, or contradict each other, stays without
    a year: Italy and Germany/Netherlands/Switzerland "Roman" (D113 items 1-2), and the others
    below, each for the reason its comment gives."""

    FILLED = (
        ("neolithic", "Finland", -5300),
        ("neolithic", "Estonia", -5300),
        ("neolithic", "Latvia", -5300),
        ("neolithic", "Lithuania", -5300),
        ("neolithic", "Morocco", -5500),
        ("neolithic", "Algeria", -5500),
        ("neolithic", "Tunisia", -5500),
        ("neolithic", "Taiwan", -4000),
        ("bronze age", "Finland", -1500),
        ("bronze age", "Netherlands", -2000),
        ("bronze age", "Malta", -2350),
        ("iron age", "Finland", -500),
        ("iron age", "China", -900),
        ("roman", "Albania", -168),
    )

    @pytest.mark.parametrize(("name", "country", "year"), FILLED)
    def test_a_filled_country_gets_its_cited_start(
        self, name: str, country: str, year: int
    ) -> None:
        assert P.start_year(name, country=country) == year

    UNFILLED = (
        ("roman", "Italy"), ("roman", "Germany"), ("roman", "Netherlands"),
        ("roman", "Switzerland"), ("roman", "Serbia"), ("roman", "Croatia"), ("roman", "Bulgaria"),
        ("roman", "Bosnia and Herzegovina"), ("roman", "North Macedonia"), ("roman", "Slovakia"),
        ("bronze age", "China"), ("bronze age", "Serbia"), ("bronze age", "Bulgaria"),
        ("bronze age", "Croatia"), ("bronze age", "South Korea"), ("bronze age", "Belgium"),
        ("neolithic", "India"), ("iron age", "Egypt"), ("chalcolithic", "Italy"),
    )  # fmt: skip

    @pytest.mark.parametrize(("name", "country"), UNFILLED)
    def test_a_country_without_one_cited_start_stays_without_a_year(
        self, name: str, country: str
    ) -> None:
        with pytest.raises(P.PeriodError, match="no cited start"):
            P.start_year(name, country=country)

    def test_italy_roman_imperial_starts_with_the_empire(self) -> None:
        assert P.start_year("roman imperial", country="Italy") == -27

    EPOCHS = (
        ("Chimú", (900, 1470), "the first stage of the Chimú culture"),
        ("late Roman", (284, 641), "catacombs of the late Roman to Byzantine period"),
        ("Vinča", (-5400, -4500), "a tell of the Vinča culture"),
    )

    @pytest.mark.parametrize(("name", "span", "quote"), EPOCHS)
    def test_a_missing_epoch_gets_its_cited_span(
        self, name: str, span: tuple[int, int], quote: str
    ) -> None:
        assert P.period_of(name) == span
        assert P.start_year(name, country="Peru") == span[0]  # one start everywhere
        assert P.states_period(quote, name)

    def test_the_new_epochs_leave_canmore_s_old_mapping_alone(self) -> None:
        assert mapped("LATE ROMAN") == (43, 410)  # `roman` still comes first


class TestTheEpochBands:
    """Owner decision D136 (2026-11-07): an epoch word maps to the predefined period band in which
    the epoch begins - in the site's country where `REGIONAL_STARTS` has a value, else at the
    conventional `PERIODS` start - and the stored year is that band's edge (`bucket_edge`)."""

    def test_a_regional_epoch_takes_the_band_of_its_start_in_the_country(self) -> None:
        band = P.epoch_band("Neolithic", country="Jordan")
        assert (band.label, band.edge, band.start, band.regional) == (
            "< 4500 BC", -4501, -10000, True
        )
        assert P.epoch_band("Neolithic", country="England").label == "4500 - 3000 BC"
        assert P.epoch_band("Neolithic", country="England").edge == -4500

    def test_a_country_without_a_regional_value_takes_the_conventional_start(self) -> None:
        band = P.epoch_band("Neolithic", country="Sudan")
        assert (band.start, band.regional, band.label) == (-4000, False, "4500 - 3000 BC")
        assert P.epoch_band("Roman", country="Italy").start == P.PERIODS["roman"][0]
        assert P.epoch_band("Roman", country="Germany").regional is False

    def test_a_country_is_not_needed_for_a_band(self) -> None:
        assert P.epoch_band("Neolithic", country=None).start == -4000
        assert P.epoch_band("Hellenistic", country=None).label == "500 BC - 1 AD"

    @pytest.mark.parametrize(
        "name", ["Stone Age", "Palaeolithic", "prehistoric", "Mesolithic", "Prehistory"]
    )
    def test_the_coarse_words_of_d111_give_a_band_by_their_start(self, name: str) -> None:
        band = P.epoch_band(name, country="Norway")
        assert (band.label, band.edge) == ("< 4500 BC", -4501)

    def test_ancient_history_and_classical_antiquity_map_by_their_start(self) -> None:
        assert P.epoch_band("ancient history", country=None).label == "3000 - 1500 BC"
        assert P.epoch_band("classical antiquity", country=None).label == "1500 - 500 BC"

    def test_a_bare_bronze_age_takes_its_regional_start_where_d111_wanted_a_phase(self) -> None:
        # D123 left these without a year; D136 bands them by the regional Bronze Age start
        assert P.epoch_band("Bronze Age", country="England").label == "3000 - 1500 BC"
        assert P.epoch_band("Bronze Age", country="Greece").label == "4500 - 3000 BC"
        assert P.epoch_band("Bronze Age", country="Finland").label == "1500 - 500 BC"

    def test_the_edge_is_the_bucket_edge_of_the_band(self) -> None:
        for name in P.PERIODS:
            band = P.epoch_band(name, country=None)
            assert band.label == categorize_period(band.start)
            assert band.edge == bucket_edge(band.label)

    def test_start_year_keeps_its_exact_year_refusals(self) -> None:
        with pytest.raises(P.PeriodError, match="too coarse"):
            P.start_year("Stone Age", country="Norway")
        with pytest.raises(P.PeriodError, match="sub-phase"):
            P.start_year("Bronze Age", country="England")
        with pytest.raises(P.PeriodError, match="no cited start"):
            P.start_year("Neolithic", country="Sudan")

    def test_an_unknown_word_is_refused_by_name(self) -> None:
        with pytest.raises(P.PeriodError, match="not one of"):
            P.epoch_band("Atlantean", country=None)


class TestTheMonumentTypes:
    """Owner decision D137 (2026-11-07): a coarse word ("prehistoric", "Stone Age") is read together
    with the site's own monument type, where the type names its epoch."""

    @pytest.mark.parametrize(
        ("text", "epoch"),
        [
            ("Stone circle", "neolithic"),
            ("a pair of prehistoric stone circles", "neolithic"),
            ("Henge", "neolithic"),
            ("Dolmen", "neolithic"),
            ("West Lanyon Quoit", "neolithic"),
            ("Long barrow", "neolithic"),
            ("chambered tomb", "neolithic"),
            ("Huntersquoy Chambered Cairn", "neolithic"),
            ("Rubha an Dùnain Passage Grave", "neolithic"),
            ("a passage tomb", "neolithic"),
            ("Menhir du Camp de César", "neolithic"),
            ("Standing stone", "neolithic"),
            ("the Dorset Cursus", "neolithic"),
            ("a causewayed enclosure", "neolithic"),
            ("a round barrow", "bronze age"),
            ("a bowl barrow", "bronze age"),
            ("a bell barrow", "bronze age"),
            ("Cairn", "bronze age"),
            ("Calf of Eday Cairns", "bronze age"),
            ("a prehistoric stone row and cairn circle", "bronze age"),
            ("a burnt mound", "bronze age"),
            ("Eggardon Hill is a prehistoric hillfort", "iron age"),
            ("a hill fort", "iron age"),
            ("an oppidum", "iron age"),
            ("Broch of Gurness", "iron age"),
            ("a crannog", "iron age"),
            ("Souterrain", "iron age"),
        ],
    )
    def test_a_type_names_its_epoch(self, text: str, epoch: str) -> None:
        found = P.monument_epoch(text)
        assert found is not None and found[1] == epoch, text

    def test_the_earliest_type_named_decides(self) -> None:
        assert P.monument_epoch("Stone circle", "a round barrow beside it") == (
            "stone circle", "neolithic"
        )

    @pytest.mark.parametrize(
        "text",
        ["Fortress/citadel", "Barrow", "Mound/tumulus", "Cave Structures", "Cairnpapple Hill",
         "Stonehenged", "Prehistoric Fortress Straževica (Dragaljevo)", "", None],
    )  # fmt: skip
    def test_no_type_without_one_of_the_named_monuments(self, text: str | None) -> None:
        assert P.monument_epoch(text) is None

    def test_the_type_band_takes_the_site_s_regional_start(self) -> None:
        assert P.epoch_band("neolithic", country="England").label == "4500 - 3000 BC"
        assert P.epoch_band("bronze age", country="England").label == "3000 - 1500 BC"
        assert P.epoch_band("iron age", country="England").label == "1500 - 500 BC"

    def test_the_words_a_type_reads(self) -> None:
        assert {"prehistoric", "prehistory", "stone age", "palaeolithic", "paleolithic",
                "mesolithic"} == P.TYPED_COARSE  # fmt: skip


class TestTheLatePhase:
    """D137: "the late Copper Age" is not the start of the Copper Age. Where the vocabulary has no
    `late ...` key of its own, the late phase lies at the epoch's end - the regional start of the
    epoch that follows it, else the conventional end of `PERIODS`."""

    def test_a_late_copper_age_in_spain_ends_where_the_spanish_bronze_age_begins(self) -> None:
        band = P.late_band("copper age", country="Spain")
        assert (band.label, band.start, band.regional) == ("3000 - 1500 BC", -1900, True)
        assert P.late_band("chalcolithic", country="Portugal").label == "3000 - 1500 BC"

    def test_without_a_regional_successor_the_conventional_end_is_read(self) -> None:
        band = P.late_band("inca", country="Peru")
        assert (band.start, band.regional) == (1533, False)
        assert band.label == categorize_period(1533)

    def test_a_late_phase_the_vocabulary_holds_is_not_read_here(self) -> None:
        with pytest.raises(P.PeriodError, match="late neolithic"):
            P.late_band("neolithic", country="England")
