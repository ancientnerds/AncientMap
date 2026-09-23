"""Tests for the shared sentence splitter.

The regression these guard against is journal 75, which published

    "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C.,
     drawing on 425 radiocarbon dates ..."

The old inline splitter treated the period in "Kevin C." as a sentence end, so
the claim stripper deleted the fragment that began at "Nolan (Ball State), ..."
and left an amputated sentence in the article.
"""

import json
import re
from pathlib import Path

import pytest

from pipeline.lyra.text_sentences import (
    is_complete_sentence,
    sentence_span,
    split_sentences,
)

HOPEWELL = (
    "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C. Nolan "
    "(Ball State), published in American Antiquity, has redrawn Ohio Hopewell "
    "chronology. The researchers compiled 424 radiocarbon dates."
)


class TestSplitSentences:
    def test_middle_initial_is_not_a_boundary(self):
        assert split_sentences(HOPEWELL) == [
            "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C. Nolan "
            "(Ball State), published in American Antiquity, has redrawn Ohio Hopewell "
            "chronology.",
            "The researchers compiled 424 radiocarbon dates.",
        ]

    def test_circa_abbreviation_is_not_a_boundary(self):
        assert split_sentences("The site dates to ca. 2300 BCE. Millet sustained it.") == [
            "The site dates to ca. 2300 BCE.",
            "Millet sustained it.",
        ]

    def test_dotted_abbreviations_survive(self):
        for text in (
            "Pottery was found, e.g. jars and bowls. Copper art indicates contact.",
            "It ended around A.D. 400. Later phases are unclear.",
            "Finds came from the U.S. Midwest. Analysis continues.",
        ):
            assert len(split_sentences(text)) == 2, text

    def test_honorifics_survive(self):
        assert split_sentences("Dr. Smith dug at St. Albans. They published in 1999.") == [
            "Dr. Smith dug at St. Albans.",
            "They published in 1999.",
        ]

    def test_lowercase_continuation_is_not_a_boundary(self):
        # A lowercase word after a period means the period belonged to an
        # abbreviation we have not listed - never split there.
        assert split_sentences("Measured in sq. metres across the trench.") == [
            "Measured in sq. metres across the trench."
        ]

    def test_ordinary_sentences_still_split(self):
        assert split_sentences("The wall fell. Rain followed! Why? Nobody knows.") == [
            "The wall fell.",
            "Rain followed!",
            "Why?",
            "Nobody knows.",
        ]

    def test_maxsplit_is_honoured(self):
        assert split_sentences("First. Second. Third.", maxsplit=1) == ["First.", "Second. Third."]

    def test_empty_text(self):
        assert split_sentences("") == []

    def test_no_boundary_returns_whole_text(self):
        assert split_sentences("A single clause without punctuation") == [
            "A single clause without punctuation"
        ]

    def test_periods_are_restored_exactly(self):
        # The sentinel round trip must not lose or duplicate any character.
        assert "".join(split_sentences(HOPEWELL)).replace(" ", "") == HOPEWELL.replace(" ", "")


class TestSentenceSpan:
    def test_span_covers_the_containing_sentence(self):
        index = HOPEWELL.index("American Antiquity")
        start, end = sentence_span(HOPEWELL, index)
        assert HOPEWELL[start:end].startswith("A landmark 2023 study")
        assert HOPEWELL[start:end].endswith("chronology.")

    def test_span_of_second_sentence(self):
        index = HOPEWELL.index("424")
        start, end = sentence_span(HOPEWELL, index)
        assert HOPEWELL[start:end] == "The researchers compiled 424 radiocarbon dates."

    def test_initial_does_not_cut_the_span_short(self):
        index = HOPEWELL.index("Nolan")
        start, end = sentence_span(HOPEWELL, index)
        assert "Mark F. Seeman" in HOPEWELL[start:end]


class TestIsCompleteSentence:
    def test_whole_sentence(self):
        assert is_complete_sentence("The researchers compiled 424 radiocarbon dates.")

    def test_trailing_fragment_rejected(self):
        assert not is_complete_sentence("drawing on 425 radiocarbon dates.")

    def test_leading_fragment_rejected(self):
        assert not is_complete_sentence("Kevin C.")

    def test_unterminated_text_rejected(self):
        assert not is_complete_sentence("The researchers compiled 424 radiocarbon dates")

    def test_quoted_sentence_accepted(self):
        assert is_complete_sentence('"The chronology is in disarray," the authors wrote.')


class TestDateAbbreviations:
    """WB-B1 (Phases 4 and 5 design, failure_modes): a date abbreviation in front of a number or an
    era word is never a sentence end. Before the fix "built c. 2500 BC" split after "c." and
    is_complete_sentence passed both fragments. The sentences here are written for the test, in the
    shapes the 3,681-extract probe found; no article text is copied into the repository."""

    def test_circa_before_a_year_is_not_a_boundary(self):
        assert split_sentences("The temple was built c. 2500 BC by Khufu. It still stands.") == [
            "The temple was built c. 2500 BC by Khufu.",
            "It still stands.",
        ]

    def test_every_abbreviation_of_the_rule_before_a_digit(self):
        for text in (
            "The wall dates to c. 300 BC and later.",
            "The wall dates to ca. 300 BC and later.",
            "It was raised by Ramesses II (r. 1279-1213 BC) at the river.",
            "The scribe Ahmose (fl. 1550 BC) copied the text.",
            "The excavator (b. 1901) published the site.",
            "The excavator (d. 1975) published the site.",
            "The wall dates to c.300 BC and later.",
            "The wall dates to C. 300 BC and later.",
        ):
            assert split_sentences(text) == [text], text

    def test_circa_before_an_era_word_is_not_a_boundary(self):
        for text in (
            "The town was populated c. AD 750-975 by traders.",
            "The shrine was rebuilt c. BC 200 on the hill.",
            "A necropolis dates from the 6th to the 1st c. BCE outside the gate.",
            "The harbour was used c. CE 100 by the fleet.",
        ):
            assert split_sentences(text) == [text], text

    def test_the_rule_stops_at_the_abbreviations_it_names(self):
        # "b." before a word that is neither a number nor an era is an ordinary end: the grave
        # letter here closes the sentence, and the next one opens with a capital.
        assert split_sentences("The tomb held grave b. The next tomb was empty.") == [
            "The tomb held grave b.",
            "The next tomb was empty.",
        ]
        # A word that merely ends in one of the letters is not the abbreviation.
        assert split_sentences("It was built by Kc. 2500 workers came later.") == [
            "It was built by Kc.",
            "2500 workers came later.",
        ]

    def test_an_era_word_in_lower_case_is_not_an_era(self):
        assert split_sentences("They quoted grave d. Ad hoc repairs followed.") == [
            "They quoted grave d.",
            "Ad hoc repairs followed.",
        ]

    def test_the_era_forms_of_the_translated_languages_are_not_boundaries(self):
        # Phase-4 lane T selects sentences from fr, de, es, it, tr and pt articles; each of these
        # era forms cut a sentence in two before the rule.
        for text in (
            "Le temple fut construit vers 2500 av. J.-C. par des paysans.",
            "La ville fut fondée en 52 apr. J.-C. sur la colline.",
            "Der Tempel wurde um 2500 v. Chr. errichtet.",
            "Die Stadt bestand bis 300 n. Chr. als Handelsplatz.",
            "El templo fue construido hacia el 2500 a. C. por campesinos.",
            "Fue abandonado en el 400 d. C. por sus habitantes.",
            "Tapınak M.Ö. 2500 yılında inşa edildi.",
            "Il tempio fu costruito nel 2500 a.C. dai contadini.",
        ):
            assert split_sentences(text + " Next one.") == [text, "Next one."], text

    def test_a_single_letter_before_another_name_still_ends_a_sentence(self):
        assert split_sentences("They dug trench a. Carter found the gate.") == [
            "They dug trench a.",
            "Carter found the gate.",
        ]

    def test_the_span_of_a_dated_sentence_is_the_whole_sentence(self):
        text = "The temple was built c. 2500 BC by Khufu. It still stands."
        start, end = sentence_span(text, text.index("2500"))
        assert text[start:end] == "The temple was built c. 2500 BC by Khufu."

    def test_a_dated_sentence_is_complete(self):
        assert is_complete_sentence("The temple was built c. 2500 BC by Khufu.")
        assert is_complete_sentence("It was raised by Ramesses II (r. 1279-1213 BC) at the river.")


#: The Phase-3 mass run's stored Wikipedia extracts (gitignored, local only): the 366-article probe
#: of the design was run over these files.
EXTRACTS = (
    Path(__file__).resolve().parents[2]
    / "output"
    / "remediation"
    / "phase3_runner"
    / "runs"
    / "mass"
)
needs_extracts = pytest.mark.skipif(
    not any(EXTRACTS.glob("batch-*/evidence/*%2Fenwiki.txt")),
    reason=f"the Phase-3 enwiki extracts are not present ({EXTRACTS})",
)

#: A fragment that ends on one of the rule's abbreviations, and a next fragment that opens with a
#: number or an era word: exactly the break the rule removes.
_BROKEN_AT = re.compile(r"(?:^|[\s(])(?:c|ca|r|fl|b|d)\.$", re.IGNORECASE)
_OPENS_DATE = re.compile(r"(?:\d|(?:AD|BC|BCE|CE)\b)")


@needs_extracts
def test_no_extract_breaks_at_a_date_abbreviation():
    breaks = []
    for path in EXTRACTS.glob("batch-*/evidence/*%2Fenwiki.txt"):
        try:
            answer = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # a body cut at the Phase-3 byte cap is not an extract (design, S1)
        for page in answer.get("query", {}).get("pages", {}).values():
            for line in (page.get("extract") or "").split("\n"):
                parts = split_sentences(line)
                breaks += [
                    (left[-30:], right[:20])
                    for left, right in zip(parts, parts[1:], strict=False)
                    if _BROKEN_AT.search(left) and _OPENS_DATE.match(right)
                ]
    assert breaks == []
