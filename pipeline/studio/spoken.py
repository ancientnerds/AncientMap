"""Spoken vs display text: they may differ only in how numbers and units are spelled.

The narrator reads `spoken` ("about a thousand tonnes"), the captions and SRT show `display`
("about 1,000 tonnes"). `normalize_tokens` maps both to one canonical token list: number words
become digits (years such as "nineteen sixty-six" and "twenty fourteen" included), thousands
separators go, unit words and symbols become one unit token, edge punctuation and case are
ignored. Clause punctuation after a number word (, ; : . ! ? … or a dash) still ends that
number: "forty, six" is 40 and 6, never 46. Any other difference is a script error.
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
ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
    "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
    "eleventh": "11th", "twelfth": "12th", "thirteenth": "13th", "fourteenth": "14th",
    "fifteenth": "15th", "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th", "thirtieth": "30th",
}  # fmt: skip
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


def _format(integer: int, fraction: str = "") -> str:
    """The canonical digits of `integer`.`fraction`, exact at any length: two numbers that
    differ in any digit get different tokens. Only trailing zeros of the fraction are spelling
    ("2.50" is "2.5", "2.0" is "2"); no float is involved, since one would round them away."""
    fraction = fraction.rstrip("0")
    return f"{integer}.{fraction}" if fraction else str(integer)


def _words(text: str) -> tuple[list[str], set[int]]:
    """The lower-cased words without edge punctuation, and the indices of the words that close
    a clause. That punctuation is the only sign that "forty, six" is two numbers, so the number
    parser never reads past such a word. A split token ("sixty-six," or "15%,") hands the
    stop to its last part; a free-standing dash or comma ("forty — six") to the word before."""
    out: list[str] = []
    stops: set[int] = set()
    for raw in text.replace("per cent", "percent").split():
        closes = raw.strip("-") == "" or any(ch in STOPS for ch in raw[len(raw.rstrip(EDGE)) :])
        token = raw.strip(EDGE).lower()
        if token.endswith("%") and token[:-1]:
            out.extend([token[:-1], "%"])
        else:
            out.extend(part for part in token.split("-") if part)
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
    """ "and" continues a number only before a final 0-99 ("two thousand and fourteen"),
    never before a new hundred/thousand ("five hundred and one thousand" is two numbers). A
    0-99 that closes a clause is final whatever follows it."""
    if i >= len(words):
        return False
    small = _small(words, stops, i)
    if small is None:
        return False
    return not _multiplied(words, stops, small[1])


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


def _number_run(words: list[str], stops: set[int], i: int) -> tuple[str, int] | None:
    """Parse the number-word run starting at words[i]; (canonical digits, next index). The run
    ends at the first word that closes a clause."""
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
    # year pattern: "nineteen sixty six", "twenty fourteen", "nineteen oh five"; never when a
    # hundred or a magnitude multiplies the second group ("eighteen twelve thousand" is 18 and
    # 12000, not 1812 and a stray "thousand")
    a, j = first
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
            return str(a * 100 + ONES[words[j + 1]]), j + 2
        second = _small(words, stops, j)
        if second is not None and second[0] >= 10 and not _multiplied(words, stops, second[1]):
            return str(a * 100 + second[0]), second[1]
    total, current = 0, 0
    prev = ""  # what the run consumed last: "", "small", "hundred", "magnitude" or "and"
    last_magnitude: float = math.inf  # the first magnitude may be any, later ones only smaller
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
        else:
            break
        if i - 1 in stops:
            break
    # a decimal needs a digit word after "point": "one point ten thousand" is 1, "point" and
    # 10,000, never 1 with "point" swallowed
    digits = ""
    if (
        i - 1 not in stops
        and i not in stops
        and i + 1 < len(words)
        and words[i] == "point"
        and words[i + 1] in ONES
        and ONES[words[i + 1]] < 10
    ):
        i += 1
        while i < len(words) and words[i] in ONES and ONES[words[i]] < 10:
            digits += str(ONES[words[i]])
            i += 1
            if i - 1 in stops:
                break
    return _format(total + current, digits), i


def normalize_tokens(text: str) -> list[str]:
    words, stops = _words(text)
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        run = _number_run(words, stops, i) if (w in ONES or w in TENS or w in ("a", "an")) else None
        if run is not None:
            out.append(run[0])
            i = run[1]
            continue
        if _DIGITS_RE.match(w):
            whole, _, fraction = w.replace(",", "").partition(".")
            out.append(_format(int(whole), fraction))
        elif _ORDINAL_DIGITS_RE.match(w):
            out.append(w)
        elif w in ORDINALS:
            out.append(ORDINALS[w])
        elif w in UNITS:
            out.append(UNITS[w])
        else:
            out.append(w)
        i += 1
    return out


def spelling_mismatch(spoken: str, display: str) -> str | None:
    """None when the two differ only in number/unit spelling; else where they diverge."""
    a, b = normalize_tokens(spoken), normalize_tokens(display)
    if a == b:
        return None
    for k, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return f"token {k}: spoken {x!r} vs display {y!r}"
    return f"spoken has {len(a)} tokens, display {len(b)}"
