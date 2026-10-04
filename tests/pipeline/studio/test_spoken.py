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
        # "second" is a time unit too: a duration compound keeps its tens word
        ("a thirty-second exposure", "a 30-second exposure"),
        ("a twenty-second pause", "a 20-second pause"),
        ("a sixty-second clip", "a 60-second clip"),
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
        # digits before a magnitude word are one number, and so is a spoken decimal
        ("about six million tonnes", "about 6 million tonnes"),
        ("two million years ago", "2 million years ago"),
        ("2 million years ago", "two million years ago"),
        ("twelve thousand years", "12 thousand years"),
        ("about six million tonnes", "about 6,000,000 tonnes"),
        ("three point three million years ago", "3.3 million years ago"),
        ("one point five million years", "1,500,000 years"),
        ("two point five thousand", "2,500"),
        ("At one point five million people lived here", "At one point 5 million people lived here"),
        # a magnitude the run cannot take stays a word on both sides
        ("By two thousand million people lived there", "By 2000 million people lived there"),
        # decades and centuries spoken as a plural
        ("In the nineteen-sixties, excavators arrived.", "In the 1960s, excavators arrived."),
        ("the nineteen sixties", "the 1960's"),
        ("the twenty-twenties", "the 2020s"),
        ("in the sixties", "in the '60s"),
        ("the fifteen hundreds", "the 1500s"),
        ("the fifteen-hundreds", "the 1500s"),
        ("the eight hundreds BC", "the 800s BC"),
        ("hundreds of stones", "hundreds of stones"),
        ("in the early two thousands", "in the early 2000s"),
        ("in the two-thousands", "in the 2000s"),
        ("in the twenty-tens", "in the 2010s"),
        ("in the twenty tens", "in the 2010s"),
        ("the nineteen-tens", "the 1910s"),
        ("thousands of stones", "thousands of stones"),
        ("tens of thousands of people", "tens of thousands of people"),
        # a regnal number: "the" and an ordinal is a Roman numeral, possessive included
        ("Ramesses the Second built it.", "Ramesses II built it."),
        ("Thutmose the Third", "Thutmose III"),
        ("Seti the First and Ramesses the Eleventh", "Seti I and Ramesses XI"),
        ("Ptolemy the Fifteenth", "Ptolemy XV"),
        ("Pope John the Twenty-Third", "Pope John XXIII"),
        ("Ramesses the Second's temple", "Ramesses II's temple"),
        ("Ramesses II's temple", "Ramesses the Second's temple"),
        ("the second pylon", "the 2nd pylon"),
        # an upper-case Roman numeral is its number, cardinal or ordinal
        (
            "during World War Two, the site was bombed",
            "during World War II, the site was bombed",
        ),
        ("after World War One", "after World War I"),
        ("WORLD WAR TWO", "WORLD WAR II"),
        ("Troy Six", "Troy VI"),
        ("Troy Six's walls", "Troy VI's walls"),
        ("TROY SIX'S WALLS", "TROY VI'S WALLS"),
        ("Dynasty Nineteen", "Dynasty XIX"),
        ("the Nineteenth Dynasty", "the XIX Dynasty"),
        ("the Twenty-First Dynasty", "the XXI Dynasty"),
        ("Legio Twenty", "Legio XX"),
        ("Troy VI", "Troy VI"),
        # known limit: the pronoun "I" is an upper-case Roman numeral too
        ("one said", "I said"),
        # "and a half" is a decimal .5, and takes a magnitude after it
        ("four and a half metres", "4.5 m"),
        ("twenty-one and a half metres", "21.5 m"),
        ("four and a half metres", "4 and a half metres"),
        ("two and a half thousand years ago", "2,500 years ago"),
        ("four and a half billion years", "4.5 billion years"),
        ("between two and a half and three metres", "between 2.5 and 3 m"),
        # a British "hundred and" before an ordinal is one ordinal
        ("the one hundred and first day", "the 101st day"),
        ("the one hundred and twentieth year", "the 120th year"),
        ("the one hundred and twenty-first year", "the 121st year"),
        ("the two thousand and fifth year", "the 2005th year"),
        # "hundredth" and an ordinal magnitude end a run as the ordinal of all they multiply
        ("the hundredth anniversary", "the 100th anniversary"),
        (
            "the hundredth anniversary of the tomb's discovery",
            "the 100th anniversary of the tomb's discovery",
        ),
        ("the one hundredth day", "the 100th day"),
        ("the two hundredth year", "the 200th year"),
        ("the fifteen hundredth anniversary", "the 1500th anniversary"),
        ("the one thousand two hundredth year", "the 1,200th year"),
        ("the one hundred and fiftieth year", "the 150th year"),
        ("the thousandth visitor", "the 1000th visitor"),
        ("the thousandth visitor", "the 1,000th visitor"),
        ("the ten thousandth visitor", "the 10,000th visitor"),
        ("the five hundred thousandth visitor", "the 500,000th visitor"),
        ("the two hundred fifty thousandth visitor", "the 250,000th visitor"),
        ("the two hundred and fifty thousandth visitor", "the 250,000th visitor"),
        ("the one million two hundred thousandth", "the 1,200,000th"),
        ("the millionth visitor", "the 1,000,000th visitor"),
        ("the two millionth visitor", "the 2000000th visitor"),
        ("the billionth", "the 1,000,000,000th"),
        # an ordinal magnitude never grows a run past an equal or larger magnitude
        ("two thousand three thousandth", "2,000 3,000th"),
        ("a hundred thousand two hundred thousandth", "100,000 200,000th"),
        ("eighteen twelve thousandth", "18 12,000th"),
        # a day ordinal right after its month name may show as the bare day
        (
            "on February twenty-second and October twenty-second",
            "on February 22 and October 22",
        ),
        ("at the summer solstice, June twenty-first", "at the summer solstice, June 21"),
        ("June twenty-first", "June 21st"),
        ("on March first", "on March 1"),
        ("December thirty-first", "December 31"),
        ("on the fifth of June", "on the 5th of June"),
        ("June the twenty-first", "June the 21st"),
        # and so is "the" and a day ordinal in a date, in the British order too
        ("June the twenty-first", "June 21"),
        ("June the twenty-first", "June 21st"),
        ("on the twenty-first of December", "on 21 December"),
        ("on the twenty-first of June.", "on 21st June."),
        (
            "twice a year, on the twenty-second of February and the twenty-second of October",
            "twice a year, on 22 February and 22 October",
        ),
        ("the first of May", "1 May"),
        (
            "from the twenty-first of June to the twenty-first of December",
            "from 21 June to 21 December",
        ),
        # a range written with a dash is its two numbers and "to"
        ("some twelve to fifteen metres", "some 12–15 m"),
        ("some twelve to fifteen metres", "some 12-15 m"),
        ("eight hundred to a thousand tonnes", "800–1,000 tonnes"),
        ("ten to twenty metres", "10-20 m"),
        ("fifteen to twenty percent", "15–20%"),
        ("two point five to three metres,", "2.5–3 m,"),
        ("from nineteen sixty-six to nineteen seventy", "from 1966–1970"),
        # British "nought", areas and volumes
        ("nought point five metres", "0.5 m"),
        ("four thousand square metres", "4,000 m²"),
        ("two square kilometres", "2 km²"),
        ("twelve hectares", "12 ha"),
        ("one hectare", "1 ha"),
        ("thirty cubic metres of stone", "30 m³ of stone"),
        # millimetres and degrees, a glued degree sign included
        ("joints no wider than two millimetres", "joints no wider than 2 mm"),
        ("five millimeters", "5 mm"),
        ("four hundred square millimetres", "400 mm²"),
        ("aligned at twenty-three degrees", "aligned at 23°"),
        ("aligned at twenty-three degrees", "aligned at 23 degrees"),
        ("one degree", "1°"),
        ("twenty-three point five degrees, then", "23.5°, then"),
        ("between twenty and thirty degrees", "between 20 and 30°"),
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
        # a duration compound is the tens word and "second", never another number
        (
            "a thirty-second exposure",
            "a 32-second exposure",
            "token 1: spoken '32nd' vs display '32'",
        ),
        (
            "a thirty-second exposure",
            "a 40-second exposure",
            "token 1: spoken '32nd' vs display '40'",
        ),
        # digits before a magnitude word must still show the spoken number
        (
            "about six million tonnes",
            "about 7 million tonnes",
            "token 1: spoken '6000000' vs display '7'",
        ),
        (
            "two million years ago",
            "2 thousand years ago",
            "token 0: spoken '2000000' vs display '2'",
        ),
        (
            "one point five million years",
            "1.6 million years",
            "token 0: spoken '1500000' vs display '1.6'",
        ),
        (
            "6 million years ago",
            "six thousand years ago",
            "token 0: spoken '6' vs display '6000'",
        ),
        # a decade is neither another decade nor its first year
        ("the nineteen-sixties", "the 1970s", "token 1: spoken '1960s' vs display '1970s'"),
        ("the nineteen-sixties", "the 1960", "token 1: spoken '1960s' vs display '1960'"),
        ("the fifteen hundreds", "the 1600s", "token 1: spoken '1500s' vs display '1600s'"),
        ("the fifteen hundreds", "the 15th century", "token 1: spoken '1500s' vs display '15th'"),
        ("nineteen, sixties", "1960s", "token 0: spoken '19' vs display '1960s'"),
        ("the two thousands", "the 2010s", "token 1: spoken '2000s' vs display '2010s'"),
        ("the two thousands", "the 2000", "token 1: spoken '2000s' vs display '2000'"),
        ("the twenty-tens", "the 2020s", "token 1: spoken '2010s' vs display '2020s'"),
        ("the twenty-tens", "the 2000s", "token 1: spoken '2010s' vs display '2000s'"),
        ("two, thousands", "2000s", "token 0: spoken '2' vs display '2000s'"),
        # a regnal number is exactly its ordinal
        ("Ramesses the Second", "Ramesses III", "token 1: spoken 'the' vs display 'iii'"),
        ("Thutmose the Third", "Thutmose IV", "token 1: spoken 'the' vs display 'iv'"),
        (
            "Ramesses the Second's temple",
            "Ramesses II temple",
            "token 2: spoken \"'s\" vs display 'temple'",
        ),
        # an upper-case Roman numeral is exactly its number, and in lower case a word
        ("World War Two", "World War III", "token 2: spoken '2' vs display 'iii'"),
        ("Troy Six", "Troy VII", "token 1: spoken '6' vs display 'vii'"),
        ("World War Two", "World War ii", "token 2: spoken '2' vs display 'ii'"),
        ("the Nineteenth Dynasty", "the XX Dynasty", "token 1: spoken '19th' vs display 'xx'"),
        ("the Nineteenth Dynasty", "the xix Dynasty", "token 1: spoken '19th' vs display 'xix'"),
        ("forty metres", "XL metres", "token 0: spoken '40' vs display 'xl'"),
        ("Troy Six", "Troy 6th", "token 1: spoken '6' vs display '6th'"),
        # "and a half" is exactly .5, and a caption that drops it is caught
        ("four and a half metres", "4.6 m", "token 0: spoken '4.5' vs display '4.6'"),
        ("four and a half metres", "4 m", "token 1: spoken 'and' vs display 'm'"),
        (
            "two and a half thousand years",
            "2,000 years",
            "token 0: spoken '2500' vs display '2000'",
        ),
        ("four, and a half", "4.5", "token 0: spoken '4' vs display '4.5'"),
        # and that ordinal is never the hundred and another ordinal
        (
            "the one hundred and first day",
            "the 100 and 1st day",
            "token 1: spoken '101st' vs display '100'",
        ),
        (
            "the one hundred and first day",
            "the 102nd day",
            "token 1: spoken '101st' vs display '102nd'",
        ),
        ("one hundred, and first", "101st", "token 0: spoken '100' vs display '101st'"),
        # an ordinal hundred or magnitude is exactly the ordinal of all it multiplies
        (
            "the hundredth anniversary",
            "the 101st anniversary",
            "token 1: spoken '100th' vs display '101st'",
        ),
        (
            "the hundredth anniversary",
            "the 1000th anniversary",
            "token 1: spoken '100th' vs display '1000th'",
        ),
        (
            "the two hundredth year",
            "the 200 th year",
            "token 1: spoken '200th' vs display '200'",
        ),
        ("the two hundredth year", "the 2 100th year", "token 1: spoken '200th' vs display '2'"),
        (
            "the thousandth visitor",
            "the 1,001st visitor",
            "token 1: spoken '1000th' vs display '1001st'",
        ),
        (
            "the five hundred thousandth visitor",
            "the 500 1000th visitor",
            "token 1: spoken '500000th' vs display '500'",
        ),
        ("hundredth, year", "100", "token 0: spoken '100th' vs display '100'"),
        ("two, hundredth", "200th", "token 0: spoken '2' vs display '200th'"),
        # a day after its month name is exactly its day, and only a day is ever bare
        ("June twenty-first", "June 22", "token 1: spoken '21st' vs display '22'"),
        ("June twenty-first", "June 20 1", "token 1: spoken '21st' vs display '20'"),
        (
            "on February twenty-second",
            "on February 23",
            "token 2: spoken '22nd' vs display '23'",
        ),
        ("on February twenty-second", "on February 20", "spoken has 4 tokens, display 3"),
        ("in June, twenty-first", "in June, 21", "token 2: spoken '21st' vs display '21'"),
        ("the twenty-first dynasty", "the 21 dynasty", "token 1: spoken '21st' vs display '21'"),
        ("June fortieth", "June 40", "token 1: spoken '40th' vs display '40'"),
        (
            "June one hundred and first",
            "June 101",
            "token 1: spoken '101st' vs display '101'",
        ),
        ("June 21st", "June twenty-one", "token 1: spoken '21st' vs display '21'"),
        # and so is "the" and a day ordinal in a date, which needs its month
        ("June the twenty-first", "June 22", "token 1: spoken 'the' vs display '22'"),
        ("the twenty-first of June", "22 June", "token 0: spoken 'the' vs display '22'"),
        ("the twenty-first of June", "21 July", "token 1: spoken 'june' vs display 'july'"),
        ("the twenty-first of June", "21 of June", "token 1: spoken 'june' vs display 'of'"),
        ("the twenty-first, of June", "21 June", "token 0: spoken 'the' vs display '21'"),
        ("the fortieth of June", "40 June", "token 0: spoken 'the' vs display '40'"),
        ("the first of many", "1 many", "token 0: spoken 'the' vs display '1'"),
        ("in June, the first", "in June, 1", "token 2: spoken 'the' vs display '1'"),
        # a dash range must show both numbers, its unit, and a "between ... and" as it is said
        ("some twelve to fifteen metres", "some 12–16 m", "token 3: spoken '15' vs display '16'"),
        ("some twelve to fifteen metres", "some 12–15 km", "token 4: spoken 'm' vs display 'km'"),
        ("twelve to fifteen metres", "12-16 m", "token 2: spoken '15' vs display '16'"),
        ("twelve to fifteen metres", "1215 m", "token 0: spoken '12' vs display '1215'"),
        (
            "between twelve and fifteen metres",
            "between 12–15 m",
            "token 2: spoken 'and' vs display 'to'",
        ),
        ("fifteen to twenty percent", "15–20 m", "token 3: spoken 'percent' vs display 'm'"),
        # an area is never a length: "four metres square" is 16 m²
        ("four thousand square metres", "4,000 m", "token 1: spoken 'm²' vs display 'm'"),
        ("four metres square", "4 m²", "token 1: spoken 'm' vs display 'm²'"),
        ("two square kilometres", "2 m²", "token 1: spoken 'km²' vs display 'm²'"),
        ("thirty cubic metres", "30 m²", "token 1: spoken 'm³' vs display 'm²'"),
        # a millimetre is no centimetre, and a degree keeps its number and its sign
        ("two millimetres", "2 cm", "token 1: spoken 'mm' vs display 'cm'"),
        ("two square millimetres", "2 mm", "token 1: spoken 'mm²' vs display 'mm'"),
        ("twenty-three degrees", "24°", "token 0: spoken '23' vs display '24'"),
        ("twenty-three degrees", "23", "spoken has 2 tokens, display 1"),
        ("twenty-three percent", "23°", "token 1: spoken 'percent' vs display '°'"),
        (
            "between twenty and thirty degrees",
            "between 20° and 30°",
            "token 2: spoken 'and' vs display '°'",
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
