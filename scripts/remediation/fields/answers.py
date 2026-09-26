"""WD1: the strict parser of an Opus answer, and the machine checks that need no page.

An answer is one JSON object `{"fields": {<field>: {...}, ...}}` whose `fields` holds exactly the
fields the question asked (`load_object`: no code fence, no prose, no key twice, no NaN - the
acceptance's reader). Each field is parsed on its own, so one malformed field costs only itself:

    {"decision": "keep" | "replace" | "clear" | "unresolved",
     "value": <string> | null,
     "quotes": [{"url": "https://...", "quote": "verbatim text"}, ...],
     "reasoning": "<non-empty>"}

**keep** and **replace** carry a value and rest on at least two quotes from at least two independent
source families (`acceptance.answers.source_family`: one Wikipedia article in any language, its
Wikidata item and Commons are one family, `wikimedia`; otherwise the registrable domain). **clear**
empties the field (owner decision O6, "replace only with a sourced value, else empty the field") and
**unresolved** is the coordinates' answer when no two sources can be quoted - the point is NOT NULL
and cannot be emptied (FIELD_CONTRACT section 3): both carry no value and no quote.

Per field, beyond the shape (every rule here needs no page - `check_shape`):

* **coordinates** - the value is `"lat, lon"` in decimal degrees. keep: within `KEEP_KM` of the stored
  point; replace: farther than that. Every quote must hold exactly two coordinates the owner-case
  web-witness parser reads (`bcases.web_witness.parse_coordinates`: signed decimals or degrees with a
  hemisphere letter, nothing but labels around them), within `KEEP_KM` of the value - or within
  half the grid the page's own digits are written on (`bcases.classify.grid_of`), which may be no
  coarser than whole arcminutes (`MAX_GRID`).
* **period_start** - an integer year, negative for BC. keep: the stored value's bucket
  (`categorize_period`); replace: another bucket, or any year when the stored value is empty. Every
  quote must carry a date - a digit, or a century or millennium word (`DATE_WORDS`) - and at
  least one must state the value itself (`states_year`: its year, or its century or millennium).
* **site_type** - one canonical type (`CANONICAL_TYPES`, a fixed point of `normalize_site_type`).
  keep: the stored type; replace: another. At least one quote must hold a word of the type
  (`type_stems`: each word of the type cut to its stem, found where a word of the folded quote
  begins - `holds_stem`).
* **source_url** - an http(s) URL that is public, not production, not a search or translation URL
  (`harvest.url_kind`), without a `#fragment` (a section link), written as httpx sends it
  (`classify.url_form`: percent-encoded, the host in lower case). keep: the stored URL; replace: another. At least one quote is from the
  value's page itself, and at least one quote names the site (`classify.names_it`: a distinctive
  word of the name, or the whole name - or its core without a generic frame - when it has none).

What needs the pages - every quote found verbatim (`opus_audit/quotes.py`), and the value page of a
source_url served and not redirected elsewhere - is `handoff.import_rounds`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from acceptance.answers import AnswerError, _point, _quotes, _year, load_object, source_family
from bcases.classify import fold, grid_name, grid_of
from bcases.web_witness import Rejected, parse_coordinates
from census.tests.t01_wikidata_claims import METRES_PER_DEGREE
from opus_audit import quotes as Q

from fields import classify as C
from fields import harvest as H
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type
from pipeline.utils.geo import haversine_distance

KEEP, REPLACE, CLEAR, UNRESOLVED = "keep", "replace", "clear", "unresolved"
DECISIONS = {
    "coordinates": (KEEP, REPLACE, UNRESOLVED),
    "period_start": (KEEP, REPLACE, CLEAR),
    "site_type": (KEEP, REPLACE, CLEAR),
    "source_url": (KEEP, REPLACE, CLEAR),
}
ANSWER_KEYS = frozenset({"fields"})
FIELD_KEYS = frozenset({"decision", "value", "quotes", "reasoning"})
QUOTE_KEYS = frozenset({"url", "quote"})
#: A point within this distance of the stored one is the stored point (the acceptance's F3 row:
#: "within 1 km is right").
KEEP_KM = 1.0
#: The coarsest digits a coordinate quote may be written in: whole arcminutes (about 1.9 km of
#: latitude a step, half of it the rounding). A whole degree or a tenth cannot place a site.
MAX_GRID = 1 / 60
#: The years a period_start may name: the oldest curated site is dated -1,400,000 (Atapuerca), and
#: nothing in the database starts after the present.
YEARS = range(-3_000_000, 2027)
#: A quote that dates something carries a digit or one of these words (a Roman-numeral century has
#: its word beside it). Case-folded, compared as whole words.
DATE_WORDS = frozenset(
    {
        "century", "centuries", "millennium", "millennia", "siecle", "siecles", "millenaire",
        "secolo", "secoli", "millennio", "siglo", "siglos", "milenio", "seculo", "seculos",
        "jahrhundert", "jahrhunderts", "jahrtausend", "eeuw", "wiek", "tysiaclecie",
    }
)  # fmt: skip
#: Words of a canonical type that name no kind of site.
TYPE_STOPWORDS = frozenset({"and", "of", "the", "complex", "structures"})
#: The words that make a number a century or a millennium, folded (`fold`: no accents, no case,
#: no punctuation): "the 5th century BC", "au Ve siecle", "siglo V", "das 3. Jahrtausend". "c" and
#: "cent" are the abbreviations "5th c." and "5th cent.".
CENTURY_WORDS = frozenset(
    {
        "century", "centuries", "c", "cent", "siecle", "siecles", "secolo", "secoli", "siglo",
        "siglos", "seculo", "seculos", "jahrhundert", "jahrhunderts", "eeuw", "wiek",
    }
)  # fmt: skip
MILLENNIUM_WORDS = frozenset(
    {
        "millennium", "millennia", "millenaire", "millenaires", "millennio", "millenni",
        "milenio", "milenios", "jahrtausend", "jahrtausends", "tysiaclecie",
    }
)  # fmt: skip
#: A number of a century or millennium may stand this many words before its word ("the 5th or
#: 4th century") or one word after it ("siglo V").
ORDINAL_REACH = 3
ORDINAL_WORDS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
    "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
    "seventeenth", "eighteenth", "nineteenth", "twentieth",
)  # fmt: skip
ORDINAL_SUFFIXES = ("", "st", "nd", "rd", "th", "e", "er", "eme", "o", "a")
_ROMAN = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
    (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)  # fmt: skip
#: A digit group separator between thousands: "3,000", "3.000", "3 000" (also no-break spaces).
_THOUSANDS = re.compile(r"(?<=\d)[,.\u00a0\u202f\u2009 ](?=\d{3}(?!\d))")


@dataclass(frozen=True)
class FieldAnswer:
    field: str
    decision: str
    value: str | None
    quotes: tuple[tuple[str, str], ...]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------------------ the shape
def _block(field: str, data: Any) -> FieldAnswer:
    if not isinstance(data, dict) or set(data) != FIELD_KEYS:
        shown = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"{field}: carries {shown}, not {sorted(FIELD_KEYS)}")
    decision = data["decision"]
    if decision not in DECISIONS[field]:
        raise AnswerError(f"{field}: decision {decision!r} is not one of {DECISIONS[field]}")
    reasoning = data["reasoning"]
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise AnswerError(f"{field}: the reasoning is not a non-empty string")
    quotes = _quotes(data["quotes"], QUOTE_KEYS)
    value = data["value"]
    if decision in (CLEAR, UNRESOLVED):
        if value is not None or quotes:
            raise AnswerError(f"{field}: {decision} carries no value and no quote")
        return FieldAnswer(field, decision, None, (), reasoning)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnswerError(f"{field}: {decision} needs its value as a trimmed, non-empty string")
    if len(quotes) < 2 or len({source_family(q.url) for q in quotes}) < 2:
        raise AnswerError(
            f"{field}: {decision} rests on at least two quotes from two independent source "
            "families (one Wikipedia article, its Wikidata item and Commons are one family)"
        )
    return FieldAnswer(field, decision, value, tuple((q.url, q.quote) for q in quotes), reasoning)


def parse(text: str, fields: Sequence[str]) -> dict[str, FieldAnswer | str]:
    """Each asked field's answer, or the problem that makes it not one. A text that is not the
    answer object at all raises `AnswerError`."""
    data = load_object(text, ANSWER_KEYS)["fields"]
    if not isinstance(data, dict) or set(data) != set(fields):
        shown = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"`fields` carries {shown}, not the asked {sorted(fields)}")
    out: dict[str, FieldAnswer | str] = {}
    for field in fields:
        try:
            out[field] = _block(field, data[field])
        except AnswerError as exc:
            out[field] = str(exc)
    return out


# ------------------------------------------------------------------------------ the values
def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return haversine_distance(a[0], a[1], b[0], b[1])


def _stored_point(line: Mapping[str, Any]) -> tuple[float, float]:
    lat, lon = str(line["fields"]["coordinates"]["stored"]).split(", ")
    return float(lat), float(lon)


def quote_point_km(quote: str, value: tuple[float, float]) -> float:
    """How far the one point a coordinate quote holds lies from `value`, less half the grid its
    digits are written on - `Rejected` when the quote holds no such point, `AnswerError` when its
    digits are coarser than `MAX_GRID` and cannot place a site."""
    lat, lon = parse_coordinates(quote)
    step = grid_of(lat, lon)
    if step > MAX_GRID * (1 + 1e-9):
        raise AnswerError(f"{quote!r} is written in {grid_name(step)}: too coarse to place a site")
    slack = step * METRES_PER_DEGREE / 2.0 / 1000.0
    return max(0.0, _km((lat, lon), value) - slack)


def dated(quote: str) -> bool:
    if re.search(r"\d", quote):
        return True
    return bool(set(fold(quote, keep_parentheses=True).split()) & DATE_WORDS)


def _roman(number: int) -> str:
    out = ""
    for value, letters in _ROMAN:
        while number >= value:
            out += letters
            number -= value
    return out


def ordinal_forms(number: int) -> frozenset[str]:
    """How a folded text writes the n-th century or millennium: `5`, `5th`, `5e`, `v`, `ve`,
    `fifth`."""
    forms = {f"{number}{suffix}" for suffix in ORDINAL_SUFFIXES}
    forms |= {_roman(number) + suffix for suffix in ("", "e", "er", "eme")}
    if number <= len(ORDINAL_WORDS):
        forms.add(ORDINAL_WORDS[number - 1])
    return frozenset(forms)


def _names_ordinal(words: Sequence[str], number: int, unit: frozenset[str]) -> bool:
    forms = ordinal_forms(number)
    for at, word in enumerate(words):
        if word not in forms:
            continue
        after = words[at + 1 : at + 1 + ORDINAL_REACH]
        if unit & set(after) or (at and words[at - 1] in unit):
            return True
    return False


def states_year(quote: str, year: int) -> bool:
    """Whether the quote states `year` itself: the year as a whole number (thousands separators
    read), or its century or millennium - a number (arabic, Roman, an English ordinal word) beside
    a century or millennium word. The n-th century BC runs from n x 100 BC to (n-1) x 100 + 1 BC
    (the prompt's "the 8th century BC" -> -800), the n-th AD from (n-1) x 100 + 1."""
    number = abs(year)
    digits = _THOUSANDS.sub("", quote)
    if number and re.search(rf"(?<!\d){number}(?!\d)", digits):
        return True
    words = fold(quote, keep_parentheses=True).split()
    century = max(1, (number - 1) // 100 + 1)
    millennium = max(1, (number - 1) // 1000 + 1)
    return _names_ordinal(words, century, CENTURY_WORDS) or _names_ordinal(
        words, millennium, MILLENNIUM_WORDS
    )


def type_stems(site_type: str) -> list[str]:
    """The stems of the words of a canonical type: `Mound/tumulus` -> `moun`, `tumul`."""
    words = [w for w in re.split(r"[/, ]+", site_type.casefold()) if w]
    return [w[: max(4, len(w) - 2)] for w in words if w not in TYPE_STOPWORDS]


def holds_stem(quote: str, stem: str) -> bool:
    """Whether a word of the folded quote begins with `stem` ("temp" in "Tempelanlage", not in
    "contemporary")."""
    return re.search(r"(?<!\w)" + re.escape(stem), fold(quote, keep_parentheses=True)) is not None


def _check_coordinates(answer: FieldAnswer, line: Mapping[str, Any]) -> None:
    value = _point(str(answer.value))
    distance = _km(value, _stored_point(line))
    if answer.decision == KEEP and distance > KEEP_KM:
        raise AnswerError(
            f"coordinates: keep, but the value is {distance:.2f} km from the stored point"
        )
    if answer.decision == REPLACE and distance <= KEEP_KM:
        raise AnswerError(
            f"coordinates: replace, but the value is {distance:.2f} km from the stored point - "
            f"within {KEEP_KM} km it is the stored point: keep"
        )
    for url, quote in answer.quotes:
        try:
            off = quote_point_km(quote, value)
        except Rejected as exc:
            raise AnswerError(f"coordinates: the quote on {url} holds no point: {exc}") from exc
        except AnswerError as exc:
            raise AnswerError(f"coordinates: the quote on {url}: {exc}") from exc
        if off > KEEP_KM:
            raise AnswerError(f"coordinates: the quote on {url} is {off:.2f} km from the value")


def _check_period(answer: FieldAnswer, line: Mapping[str, Any]) -> None:
    year = _year(str(answer.value))
    if year not in YEARS:
        raise AnswerError(f"period_start: {year} is not a year a site can start in")
    stored = line["fields"]["period_start"]["stored"]
    same = stored is not None and C.bucket(year) == C.bucket(int(stored))
    if answer.decision == KEEP and not same:
        raise AnswerError(
            f"period_start: keep, but {year} is not in the stored value's bucket - that is replace"
        )
    if answer.decision == REPLACE and same:
        raise AnswerError(
            f"period_start: replace, but {year} is in the stored value's bucket - that is keep"
        )
    for url, quote in answer.quotes:
        if not dated(quote):
            raise AnswerError(f"period_start: the quote on {url} carries no date")
    if not any(states_year(quote, year) for _, quote in answer.quotes):
        raise AnswerError(
            f"period_start: no quote states {year} itself - its year, or its century or "
            "millennium with that word"
        )


def _check_site_type(answer: FieldAnswer, line: Mapping[str, Any]) -> None:
    value = str(answer.value)
    if value not in CANONICAL_TYPES or normalize_site_type(value) != value:
        raise AnswerError(f"site_type: {value!r} is not a canonical type")
    stored = line["fields"]["site_type"]["stored"]
    if answer.decision == KEEP and value != stored:
        raise AnswerError(f"site_type: keep, but {value!r} is not the stored {stored!r}")
    if answer.decision == REPLACE and value == stored:
        raise AnswerError(f"site_type: replace, but {value!r} is the stored type - that is keep")
    stems = type_stems(value)
    if not any(holds_stem(q, s) for _, q in answer.quotes for s in stems):
        raise AnswerError(f"site_type: no quote holds a word of {value!r} ({', '.join(stems)})")


def _page_of(url: str) -> str:
    """The page a quote URL or a value names: `&amp;` read as `&`, then httpx's form."""
    return C.url_form(Q.canonical_url(url)[0])


def _check_source_url(answer: FieldAnswer, line: Mapping[str, Any]) -> None:
    value = str(answer.value)
    if H.url_kind(value) not in (H.URL_WIKIPEDIA, H.URL_WEB) or Q.not_fetchable(value):
        raise AnswerError(f"source_url: {value!r} is not a public page about a site")
    fragment = urlsplit(value).fragment
    if fragment:
        raise AnswerError(
            f"source_url: {value!r} is a section link - give the page's own URL, without "
            f"#{fragment}"
        )
    if C.url_form(value) != value:
        raise AnswerError(
            "source_url: write the URL as it is sent, percent-encoded (a non-ASCII character or a "
            f"space as %XX, the host in lower case): {C.url_form(value)}"
        )
    stored = line["fields"]["source_url"]["stored"]
    if answer.decision == KEEP and value != stored:
        raise AnswerError(f"source_url: keep, but {value!r} is not the stored URL")
    if answer.decision == REPLACE and value == stored:
        raise AnswerError("source_url: replace, but the value is the stored URL - that is keep")
    if not any(_page_of(url) == value for url, _ in answer.quotes):
        raise AnswerError("source_url: no quote is from the value's own page")
    if not any(C.names_it(str(line["name"]), q) for _, q in answer.quotes):
        raise AnswerError(f"source_url: no quote names the site ({line['name']!r})")


CHECKS = {
    "coordinates": _check_coordinates,
    "period_start": _check_period,
    "site_type": _check_site_type,
    "source_url": _check_source_url,
}


def check_shape(text: str, fields: Sequence[str], line: Mapping[str, Any]) -> dict[str, Any]:
    """Every field's answer after every check that needs no page: `{field: FieldAnswer | problem}`.
    A text that is not the answer object raises `AnswerError`."""
    out: dict[str, Any] = {}
    for field, answer in parse(text, fields).items():
        if isinstance(answer, str) or answer.decision in (CLEAR, UNRESOLVED):
            out[field] = answer
            continue
        try:
            CHECKS[field](answer, line)
        except AnswerError as exc:
            out[field] = str(exc)
        else:
            out[field] = answer
    return out
