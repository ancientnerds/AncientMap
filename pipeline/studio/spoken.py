"""Spoken vs display text: they may differ only in how numbers and units are spelled.

The narrator reads `spoken` ("about a thousand tonnes"), the captions and SRT show `display`
("about 1,000 tonnes"). `normalize_tokens` maps both to one canonical token list: number words
become digits (years such as "nineteen sixty-six" and "twenty fourteen" included), ordinal
words become digit ordinals ("twenty-first" is 21st), thousands separators go, unit words and
symbols become one unit token, edge punctuation and case are ignored. Clause punctuation after a
number word (, ; : . ! ? … or a dash) still ends that number: "forty, six" is 40 and 6,
never 46. Any other difference is a script error.

Where the words allow two readings, both stand and `spelling_mismatch` accepts a display that
shows either: the British "two hundred and fifty thousand" is 250,000, "between five hundred
and one thousand" is 500 and 1,000; "one point five" is 1.5, but in "at one point five
hundred men" it is 1, "point" and 500. `normalize_tokens` gives the primary reading, every
number run read as far as it goes. Known limit: two numbers spoken back to back with no
punctuation between them, the second a British "hundred and" group, read like the plan's
"one thousand five hundred and one thousand six hundred fifty" (1,500 and 1,650), so "a
hundred thousand two hundred and fifty thousand" is 100,200 and 50,000; a comma after the
first number makes it 100,000 and 250,000.
"""

from __future__ import annotations

import math
import re

ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}  # fmt: skip
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
MAGNITUDES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
# the plural tens words name a decade: "the sixties" is the 60s, "the nineteen-sixties" the 1960s
DECADES = {f"{w[:-1]}ies": v for w, v in TENS.items()}
ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
    "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
    "eleventh": "11th", "twelfth": "12th", "thirteenth": "13th", "fourteenth": "14th",
    "fifteenth": "15th", "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th", "thirtieth": "30th", "fortieth": "40th",
    "fiftieth": "50th", "sixtieth": "60th", "seventieth": "70th", "eightieth": "80th",
    "ninetieth": "90th",
}  # fmt: skip
# the ordinals that end a compound one after a tens word: "twenty-first" is "21st"
UNIT_ORDINALS = {w: int(o[:-2]) for w, o in ORDINALS.items() if int(o[:-2]) < 10}
UNITS = {
    "t": "t", "tonne": "t", "tonnes": "t", "ton": "t", "tons": "t",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "km": "km", "kilometre": "km", "kilometres": "km", "kilometer": "km", "kilometers": "km",
    "cm": "cm", "centimetre": "cm", "centimetres": "cm", "centimeter": "cm", "centimeters": "cm",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ft": "ft", "foot": "ft", "feet": "ft",
    "%": "percent", "percent": "percent",
    # dotted forms without their last full stop: _words strips it as edge punctuation
    "bc": "bc", "bce": "bc", "b.c": "bc", "b.c.e": "bc",
    "ad": "ad", "ce": "ad", "a.d": "ad", "c.e": "ad",
}  # fmt: skip
EDGE = ".,;:!?\"'()[]…—–“”‘’"
STOPS = ",;:.!?…—–"  # trailing punctuation that closes a clause, and with it a spoken number
_DIGITS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_ORDINAL_DIGITS_RE = re.compile(r"^\d+(?:st|nd|rd|th)$")
_DECADE_DIGITS_RE = re.compile(r"^(\d*0)['’]?s$")  # "1960s", "1960's", "60s" ("'60s" unquoted)
_POSSESSIVE_RE = re.compile(r"^(.*\D)(['’]s)$")  # "II's" is "ii" and "'s"; "1960's" is a decade
_ROMAN = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
    (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)  # fmt: skip
_PER_CENT_RE = re.compile(r"\bper\s+cent\b", re.IGNORECASE)  # "Per cent" is "percent" too


def _format(integer: int, fraction: str = "") -> str:
    """The canonical digits of `integer`.`fraction`, exact at any length: two numbers that
    differ in any digit get different tokens. Only trailing zeros of the fraction are spelling
    ("2.50" is "2.5", "2.0" is "2"); no float is involved, since one would round them away."""
    fraction = fraction.rstrip("0")
    return f"{integer}.{fraction}" if fraction else str(integer)


def _scaled(integer: int, fraction: str, magnitude: int) -> str:
    """The canonical digits of `integer`.`fraction` times `magnitude`, exact like `_format`:
    1.5 million is "1500000"."""
    scale = 10 ** len(fraction)
    product = (integer * scale + int(fraction or "0")) * magnitude
    return _format(product // scale, str(product % scale).zfill(len(fraction)))


def _roman(n: int) -> str:
    """`n` (1-3999) in lower-case Roman numerals: 23 is "xxiii"."""
    out = ""
    for value, letters in _ROMAN:
        count, n = divmod(n, value)
        out += letters * count
    return out


def _words(text: str) -> tuple[list[str], set[int]]:
    """The lower-cased words without edge punctuation, and the indices of the words that close
    a clause. That punctuation is the only sign that "forty, six" is two numbers, so the number
    parser never reads past such a word. A split token ("sixty-six," or "15%,") hands the
    stop to its last part; a free-standing dash or comma ("forty — six") to the word before.
    A possessive "'s" is a word of its own, so "the Second's" and "II's" differ only in the
    number."""
    out: list[str] = []
    stops: set[int] = set()
    for raw in _PER_CENT_RE.sub("percent", text).split():
        closes = raw.strip("-") == "" or any(ch in STOPS for ch in raw[len(raw.rstrip(EDGE)) :])
        token = raw.strip(EDGE).lower()
        possessive = _POSSESSIVE_RE.match(token)
        if possessive:
            token = possessive[1]
        if token.endswith("%") and token[:-1]:
            out.extend([token[:-1], "%"])
        else:
            out.extend(part for part in token.split("-") if part)
        if possessive:
            out.append(possessive[2])
        if closes and out:
            stops.add(len(out) - 1)
    return out, stops


def _small(words: list[str], stops: set[int], i: int) -> tuple[int, int] | None:
    """A number 0-99 at words[i] ("twenty four" counts as one, "twenty, four" does not);
    (value, next index)."""
    w = words[i]
    if w in ONES:
        return ONES[w], i + 1
    if w in TENS:
        value = TENS[w]
        if (
            i not in stops
            and i + 1 < len(words)
            and words[i + 1] in ONES
            and ONES[words[i + 1]] < 10
        ):
            return value + ONES[words[i + 1]], i + 2
        return value, i + 1
    return None


def _multiplied(words: list[str], stops: set[int], nxt: int) -> bool:
    """Whether the group ending before words[nxt] is multiplied by a "hundred" or a magnitude
    that follows it. A group that closes a clause is final whatever follows it."""
    return (
        nxt < len(words)
        and nxt - 1 not in stops
        and (words[nxt] == "hundred" or words[nxt] in MAGNITUDES)
    )


def _joins_after_and(words: list[str], stops: set[int], i: int) -> bool:
    """ "and" surely continues a number only before a final 0-99 ("two thousand and
    fourteen"); before a 0-99 that a hundred or a magnitude multiplies it does so only in the
    British reading of `_british_and`. A 0-99 that closes a clause is final whatever follows
    it."""
    if i >= len(words):
        return False
    small = _small(words, stops, i)
    if small is None:
        return False
    return not _multiplied(words, stops, small[1])


def _british_and(words: list[str], stops: set[int], i: int, last_magnitude: float) -> bool:
    """Whether the "and" at words[i], after "hundred", may join a 0-99 that a magnitude smaller
    than the run's last one multiplies, as British English does: "two hundred and fifty
    thousand" is 250,000. The same words may be two numbers ("between five hundred and one
    thousand" is 500 and 1,000), so the run keeps its end before the "and" as a second
    reading."""
    small = _small(words, stops, i + 1) if i + 1 < len(words) else None
    if small is None or not _multiplied(words, stops, small[1]):
        return False
    after = words[small[1]]
    return after in MAGNITUDES and MAGNITUDES[after] < last_magnitude


def _group_magnitude(words: list[str], stops: set[int], h: int) -> int:
    """The magnitude that multiplies the hundred-group whose "hundred" is words[h], or 0 when
    none does. The group runs on through its 0-99: "two hundred fifty thousand" is multiplied
    by a thousand, just as "two hundred thousand" is. A word that closes a clause ends the
    group, and so does any word that is neither a 0-99 nor a magnitude."""
    if h in stops:
        return 0
    j = h + 1
    small = _small(words, stops, j) if j < len(words) else None
    if small is not None:
        if small[1] - 1 in stops:
            return 0
        j = small[1]
    return MAGNITUDES[words[j]] if j < len(words) and words[j] in MAGNITUDES else 0


def _small_continues(
    words: list[str], stops: set[int], nxt: int, prev: str, last_magnitude: float
) -> bool:
    """Whether a 0-99 ending before words[nxt] continues the run after `prev` (the last word
    kind the run consumed) instead of starting a new number. A 0-99 follows only "hundred",
    a magnitude or a joining "and": "between two and three", "two three-tonne" and "fifteen
    hundred two hundred" are two numbers each. After a magnitude it may open the next group
    ("one thousand five hundred") or a smaller magnitude ("one million two thousand"), never
    an equal or larger one ("two thousand three thousand" is two numbers). The same holds
    past a whole hundred-group, its 0-99 included: "one million two hundred fifty thousand"
    goes on, "a hundred thousand two hundred thousand" and "a hundred thousand two hundred
    fifty thousand" are two numbers each. A 0-99 or a hundred that closes a clause is the
    run's last group, so the word after it decides nothing."""
    if prev == "":
        return True
    if prev == "small":
        return False
    if nxt - 1 in stops:
        return True
    if nxt < len(words) and words[nxt] == "hundred":
        return prev == "magnitude" and _group_magnitude(words, stops, nxt) < last_magnitude
    if nxt < len(words) and words[nxt] in MAGNITUDES:
        return MAGNITUDES[words[nxt]] < last_magnitude
    return True


def _number_run(words: list[str], stops: set[int], i: int) -> list[tuple[str, int]] | None:
    """Parse the number-word run starting at words[i]: its readings as (canonical digits, next
    index), the run read as far as it goes first, then each earlier end the words also allow
    (before a British "and", see `_british_and`, or a decimal "point"). The run ends at the
    first word that closes a clause."""
    if (
        words[i] in ("a", "an")
        and i not in stops
        and i + 1 < len(words)
        and (words[i + 1] == "hundred" or words[i + 1] in MAGNITUDES)
    ):
        words = [*words[:i], "one", *words[i + 1 :]]
    first = _small(words, stops, i)
    if first is None:
        return None
    a, j = first
    # a decade or a century spoken as a plural: "nineteen-sixties" is the 1960s and "fifteen
    # hundreds" the 1500s
    if j - 1 not in stops and j < len(words):
        if 10 <= a <= 99 and words[j] in DECADES:
            return [(f"{a * 100 + DECADES[words[j]]}s", j + 1)]
        if a >= 1 and words[j] == "hundreds":
            return [(f"{a * 100}s", j + 1)]
    # year pattern: "nineteen sixty six", "twenty fourteen", "nineteen oh five"; never when a
    # hundred or a magnitude multiplies the second group ("eighteen twelve thousand" is 18 and
    # 12000, not 1812 and a stray "thousand")
    if (
        10 <= a <= 99
        and j - 1 not in stops
        and j < len(words)
        and words[j] not in ("hundred", *MAGNITUDES)
    ):
        if (
            words[j] == "oh"
            and j not in stops
            and j + 1 < len(words)
            and words[j + 1] in ONES
            and not _multiplied(words, stops, j + 2)
        ):
            return [(str(a * 100 + ONES[words[j + 1]]), j + 2)]
        second = _small(words, stops, j)
        if second is not None and second[0] >= 10 and not _multiplied(words, stops, second[1]):
            return [(str(a * 100 + second[0]), second[1])]
    total, current = 0, 0
    prev = ""  # what the run consumed last: "", "small", "hundred", "magnitude" or "and"
    last_magnitude: float = math.inf  # the first magnitude may be any, later ones only smaller
    ends: list[tuple[str, int]] = []  # the earlier ends of the second readings
    while i < len(words):
        w = words[i]
        small = _small(words, stops, i)
        if small is not None:
            if not _small_continues(words, stops, small[1], prev, last_magnitude):
                break
            current += small[0]
            i, prev = small[1], "small"
        elif w == "hundred" and prev == "small":
            current *= 100
            i, prev = i + 1, "hundred"
        elif w in MAGNITUDES and prev in ("small", "hundred") and MAGNITUDES[w] < last_magnitude:
            total += current * MAGNITUDES[w]
            current, last_magnitude = 0, MAGNITUDES[w]
            i, prev = i + 1, "magnitude"
        elif (
            w == "and"
            and i not in stops
            and prev in ("hundred", "magnitude")
            and _joins_after_and(words, stops, i + 1)
        ):
            i, prev = i + 1, "and"
        elif (
            w == "and"
            and i not in stops
            and prev == "hundred"
            and _british_and(words, stops, i, last_magnitude)
        ):
            ends.append((_format(total + current), i))
            i, prev = i + 1, "and"
        else:
            break
        if i - 1 in stops:
            break
    # a run that ends on a tens word may end on a unit ordinal: "twenty-first" is 21st and
    # "one hundred thirty-second" 132nd, never 20 and 1st. "second" is a time unit as well,
    # so "a thirty-second exposure" may be a 30-second one: that end is a second reading
    if (
        prev == "small"
        and words[i - 1] in TENS
        and i - 1 not in stops
        and i < len(words)
        and words[i] in UNIT_ORDINALS
    ):
        if words[i] == "second":
            ends.append((_format(total + current), i))
        ordinal = f"{total + current + UNIT_ORDINALS[words[i]]}{ORDINALS[words[i]][-2:]}"
        return [(ordinal, i + 1), *ends]
    # a fraction: "four and a half" is 4.5, and the whole number before a word "and" is a
    # second reading. A decimal needs a digit word after "point": "one point ten thousand" is
    # 1, "point" and 10,000, never 1 with "point" swallowed. Before a digit word the "point"
    # may still be a word, "at one point five hundred men" is 1, "point" and 500 too: that end
    # is a second reading
    digits = ""
    if (
        prev == "small"
        and i - 1 not in stops
        and words[i : i + 3] == ["and", "a", "half"]
        and i not in stops
        and i + 1 not in stops
    ):
        ends.append((_format(total + current), i))
        digits, i = "5", i + 3
    elif (
        i - 1 not in stops
        and i not in stops
        and i + 1 < len(words)
        and words[i] == "point"
        and words[i + 1] in ONES
        and ONES[words[i + 1]] < 10
    ):
        ends.append((_format(total + current), i))
        i += 1
        while i < len(words) and words[i] in ONES and ONES[words[i]] < 10:
            digits += str(ONES[words[i]])
            i += 1
            if i - 1 in stops:
                break
    # a decimal takes a magnitude after it like a whole number does: "one point five
    # million" is 1,500,000
    if (
        digits
        and i - 1 not in stops
        and i < len(words)
        and words[i] in MAGNITUDES
        and MAGNITUDES[words[i]] < last_magnitude
    ):
        return [(_scaled(total + current, digits, MAGNITUDES[words[i]]), i + 1), *ends]
    return [(_format(total + current, digits), i), *ends]


def _readings(words: list[str], stops: set[int], i: int) -> list[tuple[str, int]]:
    """The tokens that words[i] can start, each with the index after it, the primary reading
    first. Only a number, and "the" before an ordinal, can have more than one."""
    w = words[i]
    if w == "the" and i not in stops and i + 1 < len(words) and words[i + 1] != "the":
        # a regnal number: "Ramesses the Second" is "Ramesses II"
        regnal = [
            (_roman(int(token[:-2])), nxt)
            for token, nxt in _readings(words, stops, i + 1)
            if _ORDINAL_DIGITS_RE.match(token) and 0 < int(token[:-2]) < 4000
        ]
        return [(w, i + 1), *regnal]
    if w in ONES or w in TENS or w in ("a", "an"):
        run = _number_run(words, stops, i)
        if run is not None:
            return run
    if _DIGITS_RE.match(w):
        whole, _, fraction = w.replace(",", "").partition(".")
        plain = (_format(int(whole), fraction), i + 1)
        # digits before a magnitude word are the digits and a word, as where a spoken run
        # cannot take that magnitude ("two thousand million" is 2000 and "million"), or one
        # number: "6 million" is 6,000,000 too
        if i not in stops and i + 1 < len(words) and words[i + 1] in MAGNITUDES:
            return [plain, (_scaled(int(whole), fraction, MAGNITUDES[words[i + 1]]), i + 2)]
        return [plain]
    decade = _DECADE_DIGITS_RE.match(w)
    if decade:
        return [(f"{int(decade[1])}s", i + 1)]
    if w in DECADES:
        return [(f"{DECADES[w]}s", i + 1)]
    if _ORDINAL_DIGITS_RE.match(w):
        return [(w, i + 1)]
    if w in ORDINALS:
        return [(ORDINALS[w], i + 1)]
    if w in UNITS:
        return [(UNITS[w], i + 1)]
    return [(w, i + 1)]


def _primary(words: list[str], stops: set[int], i: int) -> list[str]:
    """The tokens of words[i:] in the primary reading, every number run read as far as it goes."""
    out: list[str] = []
    while i < len(words):
        token, i = _readings(words, stops, i)[0]
        out.append(token)
    return out


def normalize_tokens(text: str) -> list[str]:
    """The canonical tokens of `text` in its primary reading."""
    words, stops = _words(text)
    return _primary(words, stops, 0)


def spelling_mismatch(spoken: str, display: str) -> str | None:
    """None when some reading of `spoken` has the tokens of some reading of `display`, so the
    two differ only in number/unit spelling; else where they diverge. Nearly every text has one
    reading; where the words allow two (a British "hundred and", a "point" that may be a word),
    the display shows which one the narrator meant. The report follows the readings that agree longest, each continued in
    its primary reading, so for a text with one reading it names the first differing token."""
    a_words, a_stops = _words(spoken)
    b_words, b_stops = _words(display)
    # both token streams in step: every (spoken index, display index) pair that k equal tokens
    # reach, in the order of the primary readings
    front, k = [(0, 0)], 0
    while True:
        reached: list[tuple[int, int]] = []
        for i, j in front:
            if i == len(a_words) and j == len(b_words):
                return None
            if i == len(a_words) or j == len(b_words):
                continue
            shown = _readings(b_words, b_stops, j)
            for token, i_next in _readings(a_words, a_stops, i):
                for other, j_next in shown:
                    if token == other and (i_next, j_next) not in reached:
                        reached.append((i_next, j_next))
        if not reached:
            break
        front, k = reached, k + 1
    a = _primary(a_words, a_stops, front[0][0])
    b = _primary(b_words, b_stops, front[0][1])
    if a and b:
        return f"token {k}: spoken {a[0]!r} vs display {b[0]!r}"
    return f"spoken has {k + len(a)} tokens, display {k + len(b)}"
