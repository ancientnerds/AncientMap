"""Tests for the shared sentence splitter.

The regression these guard against is journal 75, which published

    "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C.,
     drawing on 425 radiocarbon dates ..."

The old inline splitter treated the period in "Kevin C." as a sentence end, so
the claim stripper deleted the fragment that began at "Nolan (Ball State), ..."
and left an amputated sentence in the article.
"""

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
