from __future__ import annotations

import pytest

from pipeline.studio import spoken


@pytest.mark.parametrize(
    ("said", "shown"),
    [
        ("This stone weighs about a thousand tonnes.", "This stone weighs about 1,000 tonnes."),
        (
            "between one thousand five hundred and one thousand six hundred fifty tonnes",
            "between 1,500 and 1,650 t",
        ),
        ("In nineteen sixty-six, a manuscript vanished.", "In 1966, a manuscript vanished."),
        ("It was cut in twenty fourteen.", "It was cut in 2014."),
        ("It was cut in two thousand and fourteen.", "It was cut in 2014."),
        ("Fifteen percent of the stone", "15% of the stone"),
        ("two point five metres long", "2.5 m long"),
        ("the fifteenth century", "the 15th century"),
        ("an eight hundred-tonne block", "an 800-tonne block"),
        ("nineteen oh five", "1905"),
        ("twenty-four blocks", "24 blocks"),
        ("about 1,000 tonnes", "about 1000 t"),
    ],
)
def test_equivalent_spellings(said, shown):
    assert spoken.spelling_mismatch(said, shown) is None


@pytest.mark.parametrize(
    ("said", "shown", "where"),
    [
        (
            "about a thousand tonnes",
            "about 1,200 tonnes",
            "token 1: spoken '1000' vs display '1200'",
        ),
        ("This stone weighs", "That stone weighs", "token 0: spoken 'this' vs display 'that'"),
        ("a thousand tonnes", "1,000 tonnes of rock", "spoken has 2 tokens, display 4"),
    ],
)
def test_real_differences_are_reported(said, shown, where):
    assert spoken.spelling_mismatch(said, shown) == where


def test_articles_stay_words():
    assert spoken.normalize_tokens("a stone and an arch") == ["a", "stone", "and", "an", "arch"]
