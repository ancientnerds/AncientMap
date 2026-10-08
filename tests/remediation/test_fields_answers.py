"""WD1's answer parser and its page-free checks (`scripts/remediation/fields/answers.py`)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from acceptance.answers import AnswerError  # noqa: E402
from fields import answers as A  # noqa: E402

WIKI = "https://en.wikipedia.org/wiki/Temple_of_Hephaestus"
REGISTER = "https://www.odysseus.culture.gr/h/2/eh255.jsp?obj_id=912"


def line(**fields: Any) -> dict[str, Any]:
    stored = {
        "coordinates": "37.9755, 23.7215",
        "period_start": -449,
        "site_type": "Temple",
        "source_url": WIKI,
    }
    stored.update(fields)
    return {
        "site_id": "0025b0ba-fd74-4c08-96e3-acc17956aa44",
        "name": "Temple of Hephaestus",
        "fields": {name: {"stored": value} for name, value in stored.items()},
    }


def block(
    decision: str, value: Any, quotes: list[tuple[str, str]], reasoning: str = "sources"
) -> dict[str, Any]:
    return {
        "decision": decision,
        "value": value,
        "quotes": [{"url": u, "quote": q} for u, q in quotes],
        "reasoning": reasoning,
    }


def text(**fields: dict[str, Any]) -> str:
    return json.dumps({"fields": fields})


def checked(field: str, answer: dict[str, Any], **stored: Any) -> Any:
    return A.check_shape(text(**{field: answer}), [field], line(**stored))[field]


class TestTheShape:
    def test_the_answer_names_exactly_the_asked_fields(self) -> None:
        with pytest.raises(AnswerError, match="not the asked"):
            A.parse(text(site_type=block("clear", None, [])), ["site_type", "period_start"])
        with pytest.raises(AnswerError, match="not one JSON object"):
            A.parse("```json\n{}\n```", ["site_type"])

    def test_one_malformed_field_costs_only_itself(self) -> None:
        parsed = A.parse(
            text(site_type=block("maybe", None, []), period_start=block("clear", None, [])),
            ["site_type", "period_start"],
        )
        assert isinstance(parsed["site_type"], str) and "decision 'maybe'" in parsed["site_type"]
        assert isinstance(parsed["period_start"], A.FieldAnswer)

    def test_clear_and_unresolved_carry_nothing(self) -> None:
        bad = checked("site_type", block("clear", "Temple", []))
        assert "carries no value and no quote" in bad
        assert "is not one of" in checked("coordinates", block("clear", None, []))
        assert "is not one of" in checked("site_type", block("unresolved", None, []))
        assert checked("coordinates", block("unresolved", None, [])).decision == "unresolved"

    def test_keep_and_replace_rest_on_two_families(self) -> None:
        one_family = [
            (WIKI, "a temple 449 BC"),
            ("https://de.wikipedia.org/wiki/Hephaisteion", "ein Tempel 449 v. Chr."),
        ]
        problem = checked("period_start", block("keep", "-449", one_family))
        assert "two independent source families" in problem
        assert "reasoning" in checked("period_start", block("clear", None, [], reasoning=" "))


class TestCoordinates:
    def test_keep_is_within_a_kilometre_and_every_quote_holds_the_point(self) -> None:
        quotes = [(WIKI, "37.9755°N 23.7215°E"), (REGISTER, "37.9756, 23.7214")]
        assert checked("coordinates", block("keep", "37.9755, 23.7215", quotes)).decision == "keep"

    def test_replace_moves_more_than_a_kilometre(self) -> None:
        quotes = [(WIKI, "37.99°N 23.75°E"), (REGISTER, "37.9900, 23.7500")]
        assert (
            checked("coordinates", block("replace", "37.99, 23.75", quotes)).decision == "replace"
        )
        near = [(WIKI, "37.9756°N 23.7216°E"), (REGISTER, "37.9756, 23.7216")]
        assert "within 1.0 km it is the stored point" in checked(
            "coordinates", block("replace", "37.9756, 23.7216", near)
        )

    def test_a_quote_without_a_point_or_far_from_the_value_is_refused(self) -> None:
        prose = [(WIKI, "on the Agoraios Kolonos hill"), (REGISTER, "37.9756, 23.7214")]
        assert "holds no point" in checked("coordinates", block("keep", "37.9755, 23.7215", prose))
        far = [(WIKI, "38.1°N 23.7215°E"), (REGISTER, "37.9756, 23.7214")]
        assert "km from the value" in checked("coordinates", block("keep", "37.9755, 23.7215", far))

    def test_a_coarse_quote_is_read_within_its_own_digits(self) -> None:
        coarse = [(WIKI, "38°N 24°E"), (REGISTER, "37.9756, 23.7214")]
        assert "whole degrees: too coarse" in checked(
            "coordinates", block("keep", "37.9755, 23.7215", coarse)
        )
        minutes = [(WIKI, "37°59′N 23°43′E"), (REGISTER, "37.9756, 23.7214")]
        assert checked("coordinates", block("keep", "37.9755, 23.7215", minutes)).decision == "keep"
        tenth = [(WIKI, "37.98, 23.72"), (REGISTER, "37.9756, 23.7214")]
        assert checked("coordinates", block("keep", "37.9755, 23.7215", tenth)).decision == "keep"


class TestPeriod:
    QUOTES = [(WIKI, "built in 449 BC"), (REGISTER, "5th century BC")]

    def test_keep_is_the_stored_bucket_and_replace_another(self) -> None:
        assert checked("period_start", block("keep", "-449", self.QUOTES)).decision == "keep"
        assert "that is replace" in checked("period_start", block("keep", "-700", self.QUOTES))
        assert "that is keep" in checked("period_start", block("replace", "-400", self.QUOTES))
        older = [(WIKI, "a sanctuary from c. 700 BC"), (REGISTER, "the 7th century BC")]
        assert checked("period_start", block("replace", "-700", older)).decision == "replace"
        # the quotes date 449 BC: they do not source a start in 700 BC
        assert "no quote states -700" in checked(
            "period_start", block("replace", "-700", self.QUOTES)
        )

    def test_an_empty_field_is_filled_by_replace_only(self) -> None:
        assert "that is replace" in checked(
            "period_start", block("keep", "-449", self.QUOTES), period_start=None
        )
        assert (
            checked(
                "period_start", block("replace", "-449", self.QUOTES), period_start=None
            ).decision
            == "replace"
        )

    def test_every_quote_carries_a_date(self) -> None:
        undated = [(WIKI, "built in 449 BC"), (REGISTER, "a Doric temple")]
        assert "carries no date" in checked("period_start", block("keep", "-449", undated))
        worded = [(WIKI, "built in 449 BC"), (REGISTER, "au Ve siècle av. J.-C.")]
        assert checked("period_start", block("keep", "-449", worded)).decision == "keep"

    def test_a_quote_states_the_value_itself(self) -> None:
        # any digit is no date of this value: the review's counter-example passed before
        loose = [(WIKI, "The site covers 12 hectares."), (REGISTER, "It lies 3 km from the coast.")]
        assert "no quote states" in checked(
            "period_start", block("replace", "-3000", loose), period_start=None
        )
        stated = [
            "It was founded c. 3,000 BC.",
            "gegründet um 3.000 v. Chr.",
            "a village of the 30th century BC",
            "founded in the 3rd millennium BC",
            "fondé au IIIe millénaire av. J.-C.",
            "it dates to the third millennium BC",
            "del 3. Jahrtausend v. Chr.",
        ]
        for quote in stated:
            quotes = [(WIKI, quote), (REGISTER, "a 12th-century chapel beside it")]
            answer = checked("period_start", block("replace", "-3000", quotes), period_start=None)
            assert not isinstance(answer, str), quote

    def test_a_century_is_read_with_its_word_and_its_number(self) -> None:
        assert A.states_year("the 5th or 4th century BC", -449)
        assert A.states_year("siglo V a.C.", -449)
        assert A.states_year("the 2nd century AD", 101)
        assert not A.states_year("the 5th stone of the 4th row", -449)
        assert not A.states_year("the 6th century BC", -449)
        assert not A.states_year("built in 1449", -449)
        assert A.states_year("in 449 BC", -449)

    def test_a_year_is_an_integer_a_site_can_start_in(self) -> None:
        assert "is not an integer year" in checked(
            "period_start", block("keep", "c. 449 BC", self.QUOTES)
        )
        assert "not a year a site can start in" in checked(
            "period_start", block("replace", "3000", self.QUOTES)
        )


class TestSiteType:
    def test_a_canonical_type_with_its_word_in_a_quote(self) -> None:
        quotes = [(WIKI, "a Doric peripteral temple"), (REGISTER, "Hephaisteion")]
        assert checked("site_type", block("keep", "Temple", quotes)).decision == "keep"
        mound = [(WIKI, "the tumuli of the plain"), (REGISTER, "burial ground")]
        assert checked("site_type", block("replace", "Mound/tumulus", mound)).decision == "replace"

    def test_a_type_that_is_not_canonical_or_not_quoted_is_refused(self) -> None:
        quotes = [(WIKI, "a Doric peripteral temple"), (REGISTER, "Hephaisteion")]
        assert "not a canonical type" in checked("site_type", block("replace", "temple", quotes))
        assert "no quote holds a word" in checked("site_type", block("replace", "Stadium", quotes))
        assert "that is keep" in checked("site_type", block("replace", "Temple", quotes))

    def test_a_type_word_is_read_where_a_word_begins(self) -> None:
        # "temp" inside "contemporary" is no temple (the review's counter-example passed before)
        inside = [(WIKI, "contemporary with the Bronze Age"), (REGISTER, "a contemporary site")]
        assert "no quote holds a word" in checked("site_type", block("keep", "Temple", inside))
        german = [(WIKI, "eine Tempelanlage des 5. Jahrhunderts"), (REGISTER, "Hephaisteion")]
        assert checked("site_type", block("keep", "Temple", german)).decision == "keep"

    def test_the_stems_of_a_type(self) -> None:
        assert A.type_stems("Mound/tumulus") == ["moun", "tumul"]
        assert A.type_stems("Necropolis/tombs complex") == ["necropol", "tomb"]
        assert A.type_stems("Theater") == ["theat"]


class TestSourceUrl:
    def test_the_value_s_own_page_is_quoted_and_names_the_site(self) -> None:
        quotes = [(WIKI, "The Temple of Hephaestus is a Doric temple"), (REGISTER, "Hephaisteion")]
        assert checked("source_url", block("keep", WIKI, quotes)).decision == "keep"

    def test_what_a_source_url_value_may_not_be(self) -> None:
        quotes = [(WIKI, "The Temple of Hephaestus"), (REGISTER, "the Hephaestus temple")]
        assert "not a public page" in checked(
            "source_url", block("replace", "https://www.google.com/search?q=x", quotes)
        )
        assert "not the stored URL" in checked("source_url", block("keep", REGISTER, quotes))
        other = "https://www.britannica.com/topic/Hephaesteum"
        assert "no quote is from the value's own page" in checked(
            "source_url", block("replace", other, quotes)
        )
        unnamed = [(REGISTER, "a Doric temple"), (WIKI, "a Doric temple on the hill")]
        assert "no quote names the site" in checked(
            "source_url", block("replace", REGISTER, unnamed)
        )

    def test_a_value_is_written_percent_encoded_and_without_a_fragment(self) -> None:
        # httpx sends and records a non-ASCII path percent-encoded; the value is written that way,
        # so what is written is what was fetched (and what the other 4,884 stored URLs look like)
        raw = "https://de.wikipedia.org/wiki/Hephaistos-Tempel_(Athen)_Ä"
        quotes = [(raw, "Der Tempel des Hephaistos"), (REGISTER, "the Hephaisteion")]
        problem = checked("source_url", block("replace", raw, quotes))
        assert "percent-encoded" in problem
        assert "https://de.wikipedia.org/wiki/Hephaistos-Tempel_(Athen)_%C3%84" in problem
        section = WIKI + "#History"
        quotes = [(section, "The Temple of Hephaestus"), (REGISTER, "the Hephaisteion")]
        assert "a section link" in checked("source_url", block("replace", section, quotes))

    def test_a_quote_on_the_value_s_page_may_spell_its_url_either_way(self) -> None:
        encoded = "https://de.wikipedia.org/wiki/Hephaisteion_%C3%84"
        quotes = [
            (
                "https://de.wikipedia.org/wiki/Hephaisteion_Ä",
                "Das Hephaisteion, der Tempel des Hephaestus",
            ),
            (REGISTER, "the Hephaisteion"),
        ]
        assert checked("source_url", block("replace", encoded, quotes)).decision == "replace"

    def test_a_name_without_a_distinctive_word_is_named_whole(self) -> None:
        # "Huaca del Sol" has no distinctive word: a correct keep was refused as naming nothing
        wiki = "https://en.wikipedia.org/wiki/Huaca_del_Sol"
        quotes = [
            (wiki, "The Huaca del Sol is an adobe brick temple"),
            ("https://www.britannica.com/place/Huaca-del-Sol", "Huaca del Sol, a Moche pyramid"),
        ]
        site = {**line(source_url=wiki), "name": "Huaca del Sol"}
        answer = text(source_url=block("keep", wiki, quotes))
        assert A.check_shape(answer, ["source_url"], site)["source_url"].decision == "keep"

    def test_another_name_of_the_site_does_not_name_it(self) -> None:
        # the item's labels are not read (they come from the item the stored URL gave): a quote
        # names the site by its stored name
        quotes = [(REGISTER, "the Hephaisteion"), (WIKI, "The Hephaisteion stands on a hill")]
        assert "no quote names the site" in checked(
            "source_url", block("replace", REGISTER, quotes)
        )


class TestTheBpReader:
    """Lane wd5 (D12): a quote that dates a site in years before the present states a year -
    1950 minus the number - within one unit of the number's last significant digit, and at least
    76 years (the gap between 1950 and 2026)."""

    def test_years_ago_and_bp_state_a_year(self) -> None:
        assert A.states_year("the cave was occupied about 40,000 years ago", -38050)
        assert A.states_year("a hearth dated to 12,000 BP", -10050)
        assert A.states_year("dated to 12,000 cal BP", -10050)
        assert A.states_year("dated to 12,000 cal. BP", -10050)
        assert A.states_year("a charcoal date of 3,450 yr BP", -1500)

    def test_ka_and_ma_are_thousands_and_millions_of_years(self) -> None:
        assert A.states_year("the earliest layer is 45 ka", -43050)
        assert A.states_year("the earliest layer is 45 kya", -43050)
        assert A.states_year("artefacts of 12.5 ka BP", -10550)
        assert A.states_year("hominin remains of 1.2 Ma", -1_198_050)
        assert A.states_year("hominin remains of 1.2 mya", -1_198_050)
        assert A.states_year("tools from 250 thousand years ago", -248_050)
        assert A.states_year("stone tools 2 million years ago", -1_998_050)

    def test_a_range_states_each_end(self) -> None:
        quote = "occupied between 12,000 and 10,000 years ago"
        assert A.states_year(quote, -10050)
        assert A.states_year(quote, -8050)
        assert A.states_year("occupied 12,000-10,000 BP", -10050)
        assert A.states_year("occupied 12,000-10,000 BP", -8050)

    def test_the_tolerance_is_one_unit_of_the_last_significant_digit(self) -> None:
        # 12,000: the last significant digit is the thousands
        assert A.states_year("12,000 BP", -10050 + 1000)
        assert A.states_year("12,000 BP", -10050 - 1000)
        assert not A.states_year("12,000 BP", -10050 + 1001)
        # 4,500: the hundreds
        assert A.states_year("4,500 years ago", -2550 + 100)
        assert not A.states_year("4,500 years ago", -2550 + 101)
        # 1.2 Ma = 1,200,000: the hundred thousands
        assert not A.states_year("hominin remains of 1.2 Ma", -1_198_050 - 100_001)

    def test_an_abbreviated_circa_and_a_fraction_are_read(self) -> None:
        assert A.states_year("dated c.4500 BP", -2550)
        assert A.bp_dates("1.5 Ma") == [(-1_498_050, 100_000)]

    def test_a_precise_number_still_has_the_gap_between_1950_and_now(self) -> None:
        # 4,321 BP is 2371 BC: one unit is 1 year, the floor is 76
        assert A.states_year("4,321 BP", -2371 + 76)
        assert A.states_year("4,321 BP", -2371 - 76)
        assert not A.states_year("4,321 BP", -2371 + 77)

    def test_a_number_older_than_6450_bp_states_the_edge_of_the_first_bucket(self) -> None:
        """The bucket edge: 6,450 BP is 4500 BC, the first year of "4500 - 3000 BC"; older is
        "< 4500 BC", whose year is the band's nearest, 4501 BC (`bucket_edge`)."""
        edge = -4501
        # 6,600 years ago is 4650 BC, 149 years from the edge, beyond its tolerance of 100: only
        # the bucket rule states it
        assert A.states_year("a house of 6,600 years ago", edge)
        assert A.states_year("40,000 years ago", edge)
        # 6,300 BP is 4350 BC, in "4500 - 3000 BC", 151 years from the edge: not stated
        assert not A.states_year("6,300 BP", edge)
        # 6,450 BP itself is 4500 BC: within the floor of 76 years of the edge, not by the bucket
        assert A.states_year("6,450 BP", edge)
        assert not A.states_year("6,450 BP", edge - 100)

    def test_the_bucket_edge_is_stated_only_for_that_year(self) -> None:
        assert not A.states_year("40,000 years ago", -4600)
        assert not A.states_year("40,000 years ago", -4502)

    def test_a_quote_without_a_unit_states_nothing(self) -> None:
        for quote in (
            "about 12,000 people lived there",
            "a site of 40000 square metres",
            "discovered 40 years later",
            "occupied for 12,000 years",
            "BP was the sponsor of the dig",
            "12 Mac computers",
            "an ago of 12000",
            "a pressure of 120 bp",
        ):
            assert not A.states_year(quote, -10050), quote

    def test_years_ago_without_a_number_before_it_states_nothing(self) -> None:
        assert not A.states_year("many years ago", -10050)
        assert not A.states_year("excavated years ago", 1950)

    def test_a_year_that_the_text_gives_directly_is_still_read(self) -> None:
        assert A.states_year("in 449 BC", -449)
        assert A.bp_dates("founded in 449 BC") == []

    def test_bp_dates_lists_each_stated_year_with_its_tolerance(self) -> None:
        assert A.bp_dates("12,000 cal BP and 3,321 years ago") == [(-10050, 1000), (-1371, 76)]

    def test_a_bp_quote_carries_a_replace_answer(self) -> None:
        quotes = [(WIKI, "the cave was inhabited about 40,000 years ago"), (REGISTER, "40 ka")]
        answer = checked("period_start", block("replace", "-38050", quotes), period_start=None)
        assert not isinstance(answer, str)

    def test_a_bp_quote_for_another_year_does_not(self) -> None:
        quotes = [(WIKI, "the cave was inhabited about 40,000 years ago"), (REGISTER, "40 ka")]
        answer = checked("period_start", block("replace", "-2000", quotes), period_start=None)
        assert isinstance(answer, str) and "no quote states -2000 itself" in answer
