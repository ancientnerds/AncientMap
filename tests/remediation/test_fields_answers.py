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
        assert checked("period_start", block("replace", "-700", self.QUOTES)).decision == "replace"

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
