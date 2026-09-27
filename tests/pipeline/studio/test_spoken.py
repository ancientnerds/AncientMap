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
        ("fourteen hundred and ninety-two", "1492"),
        ("a thousand and one nights", "1,001 nights"),
        ("three hundred and sixty-five days", "365 days"),
        ("one hundred twenty thousand", "120,000"),
        ("one million two hundred thousand", "1,200,000"),
        ("one million two thousand", "1,002,000"),
        # separate numbers stay separate: no sum, no concatenation
        ("between two and three metres", "between 2 and 3 m"),
        ("between five and six tonnes", "between 5 and 6 t"),
        ("ten and twelve metres", "10 and 12 m"),
        ("two three-tonne blocks", "2 3-tonne blocks"),
        ("one, two, three", "1, 2, 3"),
        ("In two thousand, three thousand people lived there", "In 2000, 3,000 people lived there"),
        ("fifteen hundred, two hundred men", "1500, 200 men"),
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
        # a caption must not show the sum of numbers the narrator said separately
        ("between two and three metres", "between 5 m", "token 1: spoken '2' vs display '5'"),
        ("between five and six tonnes", "between 11 t", "token 1: spoken '5' vs display '11'"),
        ("two three-tonne blocks", "5 t blocks", "token 0: spoken '2' vs display '5'"),
        ("one, two, three", "6", "token 0: spoken '1' vs display '6'"),
        ("nineteen five", "24", "token 0: spoken '19' vs display '24'"),
        ("two thousand three thousand", "5,000", "token 0: spoken '2000' vs display '5000'"),
    ],
)
def test_real_differences_are_reported(said, shown, where):
    assert spoken.spelling_mismatch(said, shown) == where


def test_articles_stay_words():
    assert spoken.normalize_tokens("a stone and an arch") == ["a", "stone", "and", "an", "arch"]
