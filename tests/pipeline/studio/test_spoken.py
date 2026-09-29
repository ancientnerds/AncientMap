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
        ("Fifteen per cent of the stone", "15% of the stone"),
        ("Fifteen Per cent of the stone", "15% of the stone"),
        ("FIFTEEN PER CENT", "15 percent"),
        ("two point five metres long", "2.5 m long"),
        ("the fifteenth century", "the 15th century"),
        # compound ordinals are one ordinal
        ("the twenty-first dynasty", "the 21st dynasty"),
        ("the Thirty-First Dynasty", "the 31st dynasty"),
        ("the twenty-second and twenty-third days", "the 22nd and 23rd days"),
        ("the one hundred thirty-second day", "the 132nd day"),
        ("the fortieth day", "the 40th day"),
        ("the ninetieth year", "the 90th year"),
        ("twenty, first", "20, 1st"),
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
        # clause punctuation after a number word ends that number
        ("Of the forty, six were never found.", "Of the 40, 6 were never found."),
        ("groups of ten, twelve or fifteen", "groups of 10, 12 or 15"),
        ("In AD seventy, twenty thousand people fled.", "In AD 70, 20,000 people fled."),
        ("a hundred thousand, two hundred thousand", "100,000, 200,000"),
        ("They found forty. Six were lost.", "They found 40. 6 were lost."),
        ("nineteen sixty, six stones", "1960, 6 stones"),
        ("It fell in nineteen oh, five fell later", "It fell in 19 oh, 5 fell later"),
        # what follows the punctuation never decides whether the number before it goes on
        ("two thousand and five, thousand more", "2005, thousand more"),
        ("two thousand three, thousand more", "2003, thousand more"),
        ("two point five, six people", "2.5, 6 people"),
        ("forty — six", "40 6"),
        ("forty - six", "40 6"),
        ('he said "forty," six times', 'he said "40," 6 times'),
        # era abbreviations, dotted or not
        ("five hundred B.C.", "500 BC"),
        ("A.D. seventy", "AD 70"),
        ("three hundred B.C.E.", "300 BCE"),
        ("in seventy C.E.", "in 70 CE"),
        # a hundred-group after a magnitude never opens an equal or larger magnitude
        ("two hundred thousand three hundred thousand", "200,000 300,000"),
        ("three hundred thousand four hundred thousand people", "300,000 400,000 people"),
        ("a million two hundred million", "1,000,000 200,000,000"),
        ("a hundred thousand two hundred", "100,200"),
        ("a hundred thousand two hundred, thousand more", "100,200, thousand more"),
        # its 0-99 belongs to the hundred-group too
        ("a hundred thousand two hundred fifty thousand", "100,000 250,000"),
        ("three hundred thousand four hundred twenty thousand people", "300,000 420,000 people"),
        ("seven hundred eighty-one thousand three hundred ten thousand", "781,000 310,000"),
        ("one million two hundred fifty thousand", "1,250,000"),
        ("a hundred thousand two hundred fifty", "100,250"),
        ("a hundred thousand two hundred fifty, thousand more", "100,250, thousand more"),
        # nor does a year take a group that a hundred or a magnitude multiplies
        ("eighteen twelve thousand men died", "18 12,000 men died"),
        ("nineteen sixty-six thousand", "19 66,000"),
        ("nineteen oh five thousand", "19 oh 5,000"),
        ("In eighteen twelve, thousands died", "In 1812, thousands died"),
        ("nineteen, sixty stones", "19, 60 stones"),
        # decimals keep every digit, and only trailing zeros are spelling
        (
            "one thousand two hundred thirty-four point five six seven",
            "1,234.567",
        ),
        ("two point five zero metres", "2.50 m"),
        ("2.50 m", "two point five metres"),
        ("two point zero metres", "2 m"),
        # British "hundred and": one number, or two where the words allow it and the caption
        # shows two
        ("a hundred and fifty thousand tonnes", "150,000 tonnes"),
        ("two hundred and fifty thousand people", "250,000 people"),
        ("one million two hundred and fifty thousand", "1,250,000"),
        ("three hundred and thirty-five million sixty-seven thousand", "335,067,000"),
        (
            "five million three hundred and ninety-nine thousand eight hundred and fifty-seven",
            "5,399,857",
        ),
        ("between five hundred and one thousand years", "between 500 and 1,000 years"),
        ("five hundred and one thousand votes", "501,000 votes"),
        ("fifteen hundred and fifty thousand", "1,550,000"),
        # known limit: back to back with no punctuation, read like the one thousand five
        # hundred and one thousand six hundred fifty case above; a comma separates them
        ("a hundred thousand two hundred and fifty thousand", "100,200 and 50,000"),
        ("a hundred thousand, two hundred and fifty thousand", "100,000, 250,000"),
        # "point" before a word that is no digit is a word, not a decimal point
        ("At one point ten thousand people lived here", "At one point 10,000 people lived here"),
        ("At one point eleven men climbed", "At one point 11 men climbed"),
        # and before a digit word it may be either
        ("At one point five hundred men marched", "At one point 500 men marched"),
        ("At one point five thousand people lived here", "At one point 5,000 people lived here"),
        ("one point five hundred", "1.5 hundred"),
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
        # nor their sum or concatenation across a comma or a sentence end
        (
            "Of the forty, six were never found.",
            "Of the 46 were never found.",
            "token 2: spoken '40' vs display '46'",
        ),
        (
            "groups of ten, twelve or fifteen",
            "groups of 1012 or 15",
            "token 2: spoken '10' vs display '1012'",
        ),
        (
            "In AD seventy, twenty thousand people fled.",
            "In AD 7020 thousand people fled.",
            "token 2: spoken '70' vs display '7020'",
        ),
        (
            "a hundred thousand, two hundred thousand",
            "100200 thousand",
            "token 0: spoken '100000' vs display '100200'",
        ),
        ("They found forty. Six", "They found 46", "token 2: spoken '40' vs display '46'"),
        # and a number spoken whole stays whole
        ("forty-six", "40, 6", "token 0: spoken '46' vs display '40'"),
        # nor a concatenation when no comma separates the two numbers
        (
            "a hundred thousand two hundred thousand",
            "100200 thousand",
            "token 0: spoken '100000' vs display '100200'",
        ),
        (
            "eighteen twelve thousand men died",
            "1812 thousand men died",
            "token 0: spoken '18' vs display '1812'",
        ),
        # nor a hundred-group with a 0-99 split off the magnitude that multiplies it
        (
            "a hundred thousand two hundred fifty thousand",
            "100,200 50,000",
            "token 0: spoken '100000' vs display '100200'",
        ),
        (
            "three hundred thousand four hundred twenty thousand people",
            "300,400 20,000 people",
            "token 0: spoken '300000' vs display '300400'",
        ),
        (
            "seven hundred eighty-one thousand three hundred ten thousand",
            "781,300 10,000",
            "token 0: spoken '781000' vs display '781300'",
        ),
        # two numbers that differ in any digit never share a token
        (
            "one thousand two hundred thirty-four point five six seven",
            "1,234.568",
            "token 0: spoken '1234.567' vs display '1234.568'",
        ),
        (
            "twelve thousand three hundred forty-five point six seven",
            "12,345.66",
            "token 0: spoken '12345.67' vs display '12345.66'",
        ),
        (
            "1234567.5 tonnes",
            "1234571.2 tonnes",
            "token 0: spoken '1234567.5' vs display '1234571.2'",
        ),
        (
            "12345678901234567 stones",
            "12345678901234568 stones",
            "token 0: spoken '12345678901234567' vs display '12345678901234568'",
        ),
        # a display that drops the word "point" is caught
        (
            "At one point ten thousand people lived here",
            "At 1 10,000 people lived here",
            "token 2: spoken 'point' vs display '10000'",
        ),
        ("two point twelve", "2 12", "token 1: spoken 'point' vs display '12'"),
        (
            "At one point five hundred men",
            "At 1 500 men",
            "token 2: spoken 'point' vs display '500'",
        ),
        ("two point five metres", "2.6 m", "token 0: spoken '2.5' vs display '2.6'"),
        # either reading of a British "hundred and" must match the caption exactly
        (
            "two hundred and fifty thousand people",
            "250,001 people",
            "token 0: spoken '250000' vs display '250001'",
        ),
        (
            "between five hundred and one thousand years",
            "between 500 and 1,001 years",
            "token 3: spoken '1000' vs display '1001'",
        ),
        (
            "two hundred and fifty thousand people",
            "200 50,000 people",
            "token 1: spoken 'and' vs display '50000'",
        ),
        (
            "a hundred thousand two hundred and fifty thousand",
            "100,000 250,000",
            "token 0: spoken '100200' vs display '100000'",
        ),
        # a compound ordinal is never a number and an ordinal
        (
            "the twenty-first dynasty",
            "the 20 1st dynasty",
            "token 1: spoken '21st' vs display '20'",
        ),
        (
            "the twenty-first dynasty",
            "the 22nd dynasty",
            "token 1: spoken '21st' vs display '22nd'",
        ),
        # "per cent" is one unit in any case, and a caption that drops it is caught
        (
            "Fifteen Per cent of the stone",
            "15 of the stone",
            "token 1: spoken 'percent' vs display 'of'",
        ),
    ],
)
def test_real_differences_are_reported(said, shown, where):
    assert spoken.spelling_mismatch(said, shown) == where


def test_articles_stay_words():
    assert spoken.normalize_tokens("a stone and an arch") == ["a", "stone", "and", "an", "arch"]


def test_the_primary_reading_reads_a_run_as_far_as_it_goes():
    assert spoken.normalize_tokens("two hundred and fifty thousand people") == ["250000", "people"]
    assert spoken.normalize_tokens("between five hundred and one thousand") == ["between", "501000"]
