"""Spoken vs display text: they may differ only in how numbers and units are spelled.

The narrator reads `spoken` ("about a thousand tonnes"), the captions and SRT show `display`
("about 1,000 tonnes"). `normalize_tokens` maps both to one canonical token list: number words
become digits (years such as "nineteen sixty-six" and "twenty fourteen" included), thousands
separators go, unit words and symbols become one unit token, edge punctuation and case are
ignored. Any other difference is a script error.
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
    "bc": "bc", "bce": "bc", "b.c.": "bc", "ad": "ad", "ce": "ad", "a.d.": "ad",
}  # fmt: skip
EDGE = ".,;:!?\"'()[]…—–“”‘’"
_DIGITS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_ORDINAL_DIGITS_RE = re.compile(r"^\d+(?:st|nd|rd|th)$")


def _format(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _words(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("per cent", "percent").split():
        token = raw.strip(EDGE).lower()
        if token.endswith("%") and token[:-1]:
            out.extend([token[:-1], "%"])
            continue
        out.extend(part for part in token.split("-") if part)
    return out


def _small(words: list[str], i: int) -> tuple[int, int] | None:
    """A number 0-99 at words[i] ("twenty four" counts as one); (value, next index)."""
    w = words[i]
    if w in ONES:
        return ONES[w], i + 1
    if w in TENS:
        value = TENS[w]
        if i + 1 < len(words) and words[i + 1] in ONES and ONES[words[i + 1]] < 10:
            return value + ONES[words[i + 1]], i + 2
        return value, i + 1
    return None


def _joins_after_and(words: list[str], i: int) -> bool:
    """ "and" continues a number only before a final 0-99 ("two thousand and fourteen"),
    never before a new hundred/thousand ("five hundred and one thousand" is two numbers)."""
    if i >= len(words):
        return False
    small = _small(words, i)
    if small is None:
        return False
    nxt = small[1]
    return nxt >= len(words) or (words[nxt] != "hundred" and words[nxt] not in MAGNITUDES)


def _small_continues(words: list[str], nxt: int, prev: str, last_magnitude: float) -> bool:
    """Whether a 0-99 ending before words[nxt] continues the run after `prev` (the last word
    kind the run consumed) instead of starting a new number. A 0-99 follows only "hundred",
    a magnitude or a joining "and": "between two and three", "two three-tonne" and "fifteen
    hundred two hundred" are two numbers each. After a magnitude it may open the next group
    ("one thousand five hundred") or a smaller magnitude ("one million two thousand"), never
    an equal or larger one ("two thousand three thousand" is two numbers)."""
    if prev == "":
        return True
    if prev == "small":
        return False
    if nxt < len(words) and words[nxt] == "hundred":
        return prev == "magnitude"
    if nxt < len(words) and words[nxt] in MAGNITUDES:
        return MAGNITUDES[words[nxt]] < last_magnitude
    return True


def _number_run(words: list[str], i: int) -> tuple[str, int] | None:
    """Parse the number-word run starting at words[i]; (canonical digits, next index)."""
    if (
        words[i] in ("a", "an")
        and i + 1 < len(words)
        and (words[i + 1] == "hundred" or words[i + 1] in MAGNITUDES)
    ):
        words = [*words[:i], "one", *words[i + 1 :]]
    first = _small(words, i)
    if first is None:
        return None
    # year pattern: "nineteen sixty six", "twenty fourteen", "nineteen oh five"
    a, j = first
    if 10 <= a <= 99 and j < len(words) and words[j] not in ("hundred", *MAGNITUDES):
        if words[j] == "oh" and j + 1 < len(words) and words[j + 1] in ONES:
            return str(a * 100 + ONES[words[j + 1]]), j + 2
        second = _small(words, j)
        if second is not None and second[0] >= 10:
            return str(a * 100 + second[0]), second[1]
    total, current = 0, 0
    prev = ""  # what the run consumed last: "", "small", "hundred", "magnitude" or "and"
    last_magnitude: float = math.inf  # the first magnitude may be any, later ones only smaller
    while i < len(words):
        w = words[i]
        small = _small(words, i)
        if small is not None:
            if not _small_continues(words, small[1], prev, last_magnitude):
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
        elif w == "and" and prev in ("hundred", "magnitude") and _joins_after_and(words, i + 1):
            i, prev = i + 1, "and"
        else:
            break
    value: float = total + current
    if i + 1 < len(words) and words[i] == "point" and words[i + 1] in ONES:
        digits = ""
        i += 1
        while i < len(words) and words[i] in ONES and ONES[words[i]] < 10:
            digits += str(ONES[words[i]])
            i += 1
        value = float(f"{int(value)}.{digits}")
    return _format(value), i


def normalize_tokens(text: str) -> list[str]:
    words = _words(text)
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        run = _number_run(words, i) if (w in ONES or w in TENS or w in ("a", "an")) else None
        if run is not None:
            out.append(run[0])
            i = run[1]
            continue
        if _DIGITS_RE.match(w):
            out.append(_format(float(w.replace(",", ""))))
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
