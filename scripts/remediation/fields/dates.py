"""The dates a quote states, in the language the page prints them (lane WD5, 2026-10-09).

`answers.states_year` used to read an English-shaped quote: the year's digits anywhere, a century
word and its number. It looked at no era marker at all - "AD 449" stated -449 - and it could not
read a page that is not in English. The WD5 pilot (Opus spot check, 2026-10-09) found four of ten
`unresolved` fields where a source plainly stated the value and only a machine reader failed, one of
them the Hungarian Wikipedia's "már az i. e. 7. században is lakták a várost" (inhabited already in
the 7th century BC), and for a rule-made start an `unresolved` answer clears the value to
`Undated` (D12). This module reads what a quote states, with its era:

* a **year** - "449 BC", "AD 449", "um 3.000 v. Chr.", "en 449 av. J.-C.", "i. e. 776-ban",
  "776 г. до н. э.", "start date -330", a run or range of them ("3000 to 2500 cal BC", "31 e il 25
  a.C."), and a decade or century of years ("the 50s BCE", "AD 1600s", "600-talet f.Kr.");
* a **century** or **millennium** - an Arabic, Roman or (English) spelled number beside the unit
  word ("5th century BC", "V secolo a.C.", "siglo IV a. C.", "5. Jahrhundert v. Chr.", "Ve siècle
  av. J.-C.", "5. století př. n. l.", "w V wieku p.n.e.", "V веке до н. э.", "MÖ 7. yüzyıl", "3.
  Jahrtausend v. Chr.", "IIIe millénaire"), also as a range ("the 5th or 4th century BC", "secoli
  XV-XIV a.C.", "the 8th century to the seventh century BC").

The languages: English, German, Dutch, French, Spanish, Catalan, Italian, Portuguese, Romanian,
Swedish, Danish, Norwegian, Finnish, Polish, Czech, Slovak, Slovene, Croatian/Serbian (Latin and
Cyrillic), Macedonian, Bulgarian, Russian, Ukrainian, Hungarian, Greek, Turkish and Indonesian
(`SM`). The quote stays verbatim in its language: nothing is translated, a unit word and an era
marker are found where they are printed.

**The era is read, not assumed.** A statement carries `BC`, `AD` or no marker. A number with no
marker is an AD statement: a year in a sentence about a modern event ("2009-ben ásatták", "im Jahr
1958") states +2009 and +1958 and never -2009, and a bare "5th century" is the 5th century AD. So a
negative year needs its BC marker on the page - beside the number, after the unit word, before the
number (Turkish "MÖ 7. yüzyıl", Hungarian "i. e. 7. század", the other sign in English "AD 449"), a
minus sign ("-330"), or the next statement's ("the 8th century to the 7th century BC") - and a
positive year is not stated by a quote that marks it BC. The n-th century BC runs from n x 100 BC to
(n-1) x 100 + 1 BC, as the prompt's "the 8th century BC -> -800" has it; a year inside it is stated
by the century. A bare number below 100 is no year at all ("Table 12").

A number that can be read two ways stays unread rather than guessed (CLAUDE.md): a lone "I" is a
Roman one only next to a unit word, "ad" and "ce" are markers only in capitals (French "ce" is
"this"), a Roman numeral is written in capitals unless it stands against the unit word ("ve
siècle"), "i. e." (Hungarian BC, English "that is") is read only before a Hungarian century or a
number with a Hungarian ending, an abbreviated unit ("c.", "s.", "w.", "в.") only with a marker
after it, and a sentence that says only "the 4th c." or "the third millennium" dates nothing.

Years before the present in other languages ("vor 12.000 Jahren", "il y a 12 000 ans", "hace 12.000
años", "12.000 anni fa", "há 12 mil anos", "12 000 лет назад") are read by `bp_ages`: it hands
`answers.bp_dates` the ages, whose tolerance is `answers`' own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal

BC, AD = "BC", "AD"
CENTURY, MILLENNIUM, YEAR = "century", "millennium", "year"

#: "12.000", "12,000", "12 000" (also no-break and thin spaces): one to three digits and groups of
#: exactly three. A longer first group ("1958 120") is two numbers; "c.30,000" is "c." and 30,000.
_GROUPED = re.compile(r"(?<![\d,])(?<!\d\.)\d{1,3}(?:[,.\u00a0\u202f\u2009 ]\d{3})+(?!\d)")
_COMBINING = re.compile(r"[\u0300-\u036f]")
_TOKEN = re.compile(r"\d+|[^\W\d_]+")
_HYPHENS = "-\u2010\u2011\u2013\u2014"
_MINUS = "-\u2212"


def group_thousands(text: str) -> str:
    """`text` with the thousands separators of every grouped number removed ("3.000 v. Chr." ->
    "3000 v. Chr.")."""
    return _GROUPED.sub(lambda m: re.sub(r"\D", "", m.group(0)), text)


def plain_text(text: str) -> str:
    """`text` with its accents removed: the string the offsets of `tokens` index."""
    return _COMBINING.sub("", unicodedata.normalize("NFKD", text))


@dataclass(frozen=True)
class Token:
    raw: str  #: as printed, accents removed
    low: str  #: case-folded
    start: int
    end: int
    dot: bool  #: a full stop follows directly: "7."
    hyphen: bool  #: a hyphen or dash follows directly: "776-ban"
    minus: bool  #: a minus sign stands directly before it, itself after a space: "start date -330"


def tokens(text: str) -> list[Token]:
    """The numbers and the words of `text`, accents removed ("siècle" -> "siecle", "př." ->
    "pr"). Digits and letters are separate tokens, so "5th" is "5" and "th", "449BC" is "449" and
    "BC"."""
    plain = plain_text(text)
    out = []
    for match in _TOKEN.finditer(plain):
        start, end = match.span()
        after = plain[end : end + 1]
        minus = (
            match.group().isdigit()
            and start > 0
            and plain[start - 1] in _MINUS
            and (start == 1 or not (plain[start - 2].isalnum() or plain[start - 2] in _HYPHENS))
        )
        out.append(
            Token(
                match.group(),
                match.group().casefold(),
                start,
                end,
                after == ".",
                after != "" and after in _HYPHENS,
                minus,
            )
        )
    return out


# ------------------------------------------------------------------------------------- vocabulary
def _words(text: str) -> tuple[str, ...]:
    return tuple(t.low for t in tokens(text))


#: The unit words, as prefixes of the folded word (the inflected forms: Hungarian "században",
#: Russian "веке", Croatian "stoljeću", Turkish "yüzyılda"). A prefix is only safe where no other
#: common word begins with it.
CENTURY_PREFIXES = (
    "century", "centuries", "siecle", "secol", "secul", "jahrhundert", "stulec", "stolet",
    "storoc", "stolj", "szazad", "αιωνα", "αιωνε", "столет", "століт", "yuzyil", "yuzyıl",
    "arhundr", "vuosisad", "stoletj",
)  # fmt: skip
#: The short or ambiguous unit words, whole: "wiek" begins "większy" (bigger), "αιων" "αιώνιος"
#: (eternal).
CENTURY_FORMS = frozenset(
    {"wiek", "wieku", "wieki", "wiekow", "wiekach", "wiekiem", "wiekami",
     "vekovi", "vijek", "vijeka", "vijeku", "vijekovi", "век", "века", "веке", "веку", "веком",
     "веков", "веки", "веках", "eeuw", "eeuwen", "siglo", "siglos", "segle", "segles", "seklet",
     "seklene"}
)  # fmt: skip
#: Serbian "vek" (century) is Czech and Slovak "věk" (age, "bronzový věk") once the accents are
#: folded: it is a century only against a number and an era marker, like an abbreviation.
CENTURY_OR_AGE_FORMS = frozenset({"vek", "veka", "veku"})
MILLENNIUM_PREFIXES = (
    "millennium", "millennia", "millenaire", "millenn", "milenio", "milenij", "jahrtausend",
    "evezred", "tysiacleci", "tisicilet", "tisucljec", "χιλιετ", "тысячелет", "тисячоліт",
    "хилядолет", "tuhatluku", "tusenar", "tusinde", "binyil", "binyıl",
)  # fmt: skip
#: Abbreviations of the unit word: "5th c. BC", "V w. p.n.e.", "V в. до н. э.", "XIXe s.", "IV
#: sec. a.C.", "5. Jh. v. Chr.". Too common as letters to mean a century unless an era marker
#: follows, and never glued to the number ("1600s" is a decade).
CENTURY_ABBREVIATIONS = frozenset(
    {"c", "cent", "jh", "jhd", "jhdt", "w", "s", "sec", "в", "вв", "ст", "stol"}
)
#: "IV тис. до н. е." (Ukrainian), "V тыс. до н. э." (Russian): the 4th and 5th millennium BC.
MILLENNIUM_ABBREVIATIONS = frozenset({"тис", "тыс"})

#: Words that join the numbers of one statement: "the 5th or 4th century", "5. und 4. Jahrhundert",
#: "V e IV secolo", "с V по IV век", "6000 и 5200". "i" (Polish/Czech/Croatian "and") is handled
#: apart; "a" is also Spanish "to" ("6,000 a 5,000 a.C.").
CONNECTORS = frozenset(
    {"or", "and", "to", "und", "oder", "bis", "et", "ou", "y", "e", "o", "od", "ili", "ve", "po",
     "и", "или", "ya", "a", "till", "til", "och", "og", "ja", "do", "ta", "en"}
)  # fmt: skip
DETERMINERS = frozenset(
    {"the", "il", "lo", "la", "le", "les", "el", "los", "las", "der", "die", "das", "dem", "den",
     "des", "du", "de", "het", "l", "gli", "un", "una", "une", "ein", "eine", "an"}
)  # fmt: skip
#: Words that qualify a number or a unit without changing which one it is: "late 1st or early 2nd
#: century", "the end of the 1st and the beginning of the 2nd", "c. 3300 - c. 1900 BC".
QUALIFIERS = frozenset(
    {"early", "late", "mid", "middle", "earlier", "later", "end", "beginning", "start", "of",
     "from", "between", "c", "ca", "circa", "around", "about", "approximately", "approx",
     "roughly", "probably", "von", "zwischen", "entre", "desde", "hacia", "vers", "environ", "um",
     "etwa", "verso", "fra", "tra", "dal", "dall", "fin", "fine", "inizio"}
)  # fmt: skip
JOINTS = CONNECTORS | DETERMINERS | QUALIFIERS
#: The connectors that make a plain year one end of a range with the date after it: "from 800 to the
#: 7th century BC". "and" is not among them for a year - "In 1998 and the 3rd century BC walls" are
#: two things - though it joins two centuries.
YEAR_RANGE_WORDS = frozenset(
    {"to", "bis", "od", "do", "po", "till", "til", "a", "au", "al", "ate", "hasta", "по", "до"}
)
#: What ends a range in the text between two statements: a comma, a semicolon, a colon, a bracket
#: or a sentence stop - but not the full stop of "c." or "ca." in "c. 3300".
_BREAKS = re.compile(r"[,;:()\[\]{}!?.]")
_ABBREVIATION_DOT = re.compile(r"\b(?:c|ca|approx)\.")
#: The most joint words that may stand between two numbers of one statement.
MAX_JOINTS = 4
#: A word that may stand between a number or a unit and its era marker: "2921 cal. BC", "4-3
#: millennium of BC", "700 years BC", "800 años a. C.", "776 г. до н. э.", "1800ish BCE".
FILLERS = frozenset(
    {"cal", "calibrated", "uncal", "uncalibrated", "of", "year", "years", "ish", "г", "гг", "год",
     "года", "году", "рік", "року", "рр", "yil", "yili", "yilinda", "yıl", "rok", "roku", "jahr",
     "jahre", "jahren", "an", "ans", "annee", "annees", "anno", "anni", "ano", "anos", "ar", "aar",
     "jaar", "lat", "let", "ev", "talet", "tallet", "talen", "godine", "godina", "године", "година"}
)  # fmt: skip

ORDINAL_WORDS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
    "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
    "seventeenth", "eighteenth", "nineteenth", "twentieth",
)  # fmt: skip
_ORDINAL_VALUE = {word: n for n, word in enumerate(ORDINAL_WORDS, start=1)}
#: The letters glued to an Arabic ordinal: "5th", "5e", "5er", "5ο"; "5-й" is not glued.
ORDINAL_SUFFIXES = frozenset(
    {"st", "nd", "rd", "th", "e", "er", "re", "eme", "me", "o", "a", "de", "te", "ste", "os", "οσ",
     "η", "ο", "ой", "ий", "ый", "ая", "ое", "я", "й", "ya", "yi", "inci", "nci", "uncu", "ncu"}
)  # fmt: skip


def _to_roman(number: int) -> str:
    out = ""
    for value, letters in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
        (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):  # fmt: skip
        while number >= value:
            out += letters
            number -= value
    return out


#: The Roman numerals a century or a millennium is written with, 1 to 40.
ROMAN = {_to_roman(n): n for n in range(1, 41)}
_ROMAN_SUFFIXES = ("", "e", "er", "eme")

# Era markers, written as printed and read through `tokens`.
_BC_MARKERS = (
    "BC", "BCE", "B.C.", "B.C.E.", "before Christ", "before the common era", "before common era",
    "before the current era", "before our era",
    # German, Dutch
    "v. Chr.", "vor Chr.", "vor Christus", "vor Christi Geburt", "v. u. Z.", "vor unserer "
    "Zeitrechnung", "v. d. Z.", "voor Christus", "voor Chr.", "v.C.",
    # French, Romanian
    "av. J.-C.", "avant J.-C.", "avant Jésus-Christ", "av. n. è.", "avant notre ère", "avant JC",
    "av. JC", "î.Hr.", "înainte de Hristos",
    # Spanish, Catalan, Italian, Portuguese
    "a. C.", "a. de C.", "antes de Cristo", "a. e. c.", "a. n. e.", "aC", "avanti Cristo",
    "prima di Cristo", "antes de nuestra era", "antes de la era común", "a.C.n.",
    "antes de J.C.", "antes de Jesucristo", "antes de Jesus Cristo", "antes da nossa era",
    "antes da era comum", "a. J.C.", "avant l'ère chrétienne", "avant l'ère commune",
    # Swedish, Danish, Norwegian, Finnish, Estonian, Latvian, Indonesian
    "f.Kr.", "före Kristus", "før Kristus", "f.v.t.", "fvt", "før vor tidsregning", "eaa.",
    "ennen ajanlaskun alkua", "eKr.", "p.m.ē.", "SM",
    # Hungarian, Polish, Czech, Slovak, Slovene, Croatian, Serbian
    "Kr. e.", "Krisztus előtt", "p.n.e.", "przed Chr.", "przed naszą erą", "př. n. l.",
    "př. Kr.", "pr. n. l.", "pr. Kr.", "pr. n. št.", "pre nove ere", "prije Krista", "pre Hrista",
    "przed Kr.", "před Kristem", "před Kr.", "pred Kristom", "prije Kr.", "pred n. št.",
    "pred našim štetjem", "prije nove ere",
    # Greek, Russian, Ukrainian, Bulgarian, Macedonian, Serbian Cyrillic
    "π.Χ.", "προ Χριστού", "π.Κ.Ε.", "до н. э.", "до н. е.", "до нашей эры", "до нашої ери",
    "до Р. Х.", "до Рождества Христова", "пр. н. е.", "пр. Хр.", "п.н.е.", "пред нашата ера",
    "пре нове ере", "пре Христа", "преди Христа", "преди нашата ера",
    # Turkish
    "M.Ö.", "MÖ", "İ.Ö.", "İÖ", "Milattan önce",
)  # fmt: skip
_AD_MARKERS = (
    "AD", "A.D.", "CE", "C.E.", "Anno Domini", "Common Era", "current era", "our era",
    "n. Chr.", "nach Chr.", "nach Christus", "nach Christi Geburt", "n. u. Z.", "n. d. Z.",
    "na Christus", "na Chr.", "ap. J.-C.", "après J.-C.", "après Jésus-Christ", "ap. n. è.",
    "apres JC", "ap. JC", "d.Hr.", "după Hristos", "d. C.", "d. de C.", "después de Cristo",
    "dopo Cristo", "depois de Cristo", "dC", "e.Kr.", "efter Kristus", "efter vor tidsregning",
    "e.v.t.", "jaa.", "jKr.", "pKr.", "Kr. u.", "Krisztus után", "i. sz.", "n.e.", "po Chr.",
    "n. l.", "po Kr.", "nove ere", "μ.Χ.", "μετά Χριστόν", "н. э.", "н. е.", "нашей эры",
    "нашої ери", "р. Х.", "сл. Хр.", "нове ере", "M.S.", "MS", "Milattan sonra",
)  # fmt: skip
#: Markers that count in capitals only (`Token.raw`): they are ordinary words or letters otherwise
#: ("ad", "ce", French "ms"). "bc" and "bce" are not among them: "around 700 bc" is a date.
_UPPER_ONLY = frozenset(
    {("ad",), ("a", "d"), ("ce",), ("c", "e"), ("mo",), ("m", "o"), ("io",), ("i", "o"), ("ms",),
     ("m", "s"), ("sm",)}
)  # fmt: skip
#: The words that mean "before" ahead of an era: an AD abbreviation right after one of them is the
#: end of a BC phrase ("450 przed n. e.", "450 prije n. l.", "450 пре н. е."), never AD. The common
#: phrases are in `_BC_MARKERS`; this reads the ones the table lacks.
_BEFORE_WORDS = frozenset(
    {"przed", "pred", "pr", "prije", "pre", "пре", "пред", "преди", "до", "antes", "avant",
     "prima", "vor", "voor", "before"}
)  # fmt: skip
#: Hungarian "i. e." (before Christ) is English "i.e." ("that is"): read only before a Hungarian
#: century or millennium, or a number with a Hungarian ending ("776-ban").
_HUNGARIAN_ONLY = frozenset({("i", "e")})
_MARKERS: dict[tuple[str, ...], str] = {}
for _text in _BC_MARKERS:
    _MARKERS[_words(_text)] = BC
for _text in _AD_MARKERS:
    _MARKERS[_words(_text)] = AD
_MARKERS[("i", "e")] = BC  # i. e. - see `_HUNGARIAN_ONLY`
#: The lengths of the markers, and one more for each: a "before" word ahead of an AD marker.
_MARKER_LENGTHS = sorted({n for key in _MARKERS for n in (len(key), len(key) + 1)}, reverse=True)
#: The case endings Hungarian hangs on a year with a hyphen: "i. e. 776-ban" (in 776 BC).
_HUNGARIAN_ENDINGS = frozenset(
    {"ban", "ben", "ig", "ra", "re", "tol", "bol", "nal", "nel", "val", "vel", "hoz", "hez"}
)  # fmt: skip
#: "600-talet f.Kr.": the century of years (Swedish, Danish, Norwegian), not a year.
_DECADE_WORDS = frozenset({"talet", "tallet", "talen", "tal", "tals"})


@dataclass(frozen=True)
class Statement:
    """What a quote states: `kind` of `number` in `era` (None: no marker, read as AD), the years
    `lo`..`hi` it covers (negative for BC)."""

    kind: str
    number: int
    era: str | None
    lo: int
    hi: int
    last_century: bool = False


def span(kind: str, number: int, era: str | None, width: int = 0) -> tuple[int, int]:
    """The years a century, millennium or year covers: the n-th century BC from n x 100 BC to (n-1)
    x 100 + 1 BC, the n-th AD from (n-1) x 100 + 1 to n x 100; a year is itself, or - for "the 50s"
    - itself to `width` years on."""
    if kind == YEAR:
        lo, hi = number, number + width
    else:
        size = 100 if kind == CENTURY else 1000
        lo, hi = (number - 1) * size + 1, number * size
    return (-hi, -lo) if era == BC else (lo, hi)


# ------------------------------------------------------------------------------------- the parser
@dataclass(frozen=True)
class _Number:
    first: int  #: index of its first token
    last: int  #: index of its last token (a glued ordinal suffix is a token of its own)
    value: int
    arabic: bool
    ordinal: bool  #: written as an ordinal: a suffix, a full stop, a Roman or a spelled number
    dot: bool
    last_century: bool = False  #: "the last century BC"


def _roman_value(token: Token, adjacent: bool) -> int | None:
    """A Roman numeral, capitalised (or small beside the unit word: "ve siècle"), with the suffix
    a French or Dutch ordinal adds ("Ve", "XIXe"). A lone "i" is a connector."""
    for suffix in _ROMAN_SUFFIXES:
        if suffix and not token.low.endswith(suffix):
            continue
        letters = token.raw[: len(token.raw) - len(suffix)]
        if not letters:
            continue
        if letters.isupper() and letters in ROMAN:
            return ROMAN[letters]
        if adjacent and letters.upper() in ROMAN and letters != "i":
            return ROMAN[letters.upper()]
    return None


def _unit(tok: Token) -> tuple[str, bool] | None:
    """`(kind, abbreviated)` when `tok` is a century or millennium word."""
    word = tok.low
    if word in CENTURY_ABBREVIATIONS or word in CENTURY_OR_AGE_FORMS:
        return CENTURY, True
    if word in MILLENNIUM_ABBREVIATIONS:
        return MILLENNIUM, True
    if word in CENTURY_FORMS or word.startswith(CENTURY_PREFIXES):
        return CENTURY, False
    if word.startswith(MILLENNIUM_PREFIXES):
        return MILLENNIUM, False
    return None


def has_unit_word(quote: str) -> bool:
    """Whether `quote` holds a century or millennium word (not an abbreviation)."""
    return any((u := _unit(t)) is not None and not u[1] for t in tokens(quote))


_Raw = tuple[int, int, Statement]


class _Quote:
    """One quote, tokenised: its numbers, unit words and era markers, and the statements they make."""

    def __init__(self, quote: str) -> None:
        grouped = group_thousands(quote)
        self.plain = plain_text(grouped)
        self.toks = tokens(grouped)
        self.units = {i: u for i, t in enumerate(self.toks) if (u := _unit(t)) is not None}
        self.nums = self._numbers()
        self.by_last = {n.last: n for n in self.nums.values()}
        self.claimed: set[int] = set()

    # ---- the numbers
    def _numbers(self) -> dict[int, _Number]:
        toks, found = self.toks, {}
        for i, tok in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            beside_unit = (i + 1 in self.units) or (i - 1 in self.units)
            if tok.low.isdecimal() and tok.low.isascii():
                last = i
                if nxt is not None and nxt.start == tok.end and nxt.low in ORDINAL_SUFFIXES:
                    last = i + 1
                found[i] = _Number(i, last, int(tok.low), True, last != i or tok.dot, tok.dot)
            elif (value := _roman_value(tok, beside_unit)) is not None:
                found[i] = _Number(i, i, value, False, True, tok.dot)
            elif tok.low in _ORDINAL_VALUE:
                found[i] = _Number(i, i, _ORDINAL_VALUE[tok.low], False, True, False)
            elif tok.low in ("last", "final") and i + 1 in self.units:
                found[i] = _Number(i, i, 1, False, True, False, last_century=True)
        return found

    # ---- markers
    def _marker_at(self, i: int, hungarian: bool) -> tuple[str, int] | None:
        """`(era, length)` of the era marker that begins at token `i`, longest first. A "before"
        word and an AD marker after it make a BC one."""
        found = self._table_marker_at(i, hungarian)
        if found is None and self.toks[i].low in _BEFORE_WORDS and i + 1 < len(self.toks):
            after = self._table_marker_at(i + 1, hungarian)
            if after is not None and after[0] == AD:
                return BC, after[1] + 1
        return found

    def _table_marker_at(self, i: int, hungarian: bool) -> tuple[str, int] | None:
        for length in _MARKER_LENGTHS:
            if i + length > len(self.toks):
                continue
            key = tuple(t.low for t in self.toks[i : i + length])
            era = _MARKERS.get(key)
            if era is None:
                continue
            if key in _UPPER_ONLY and not all(t.raw.isupper() for t in self.toks[i : i + length]):
                continue
            if key in _HUNGARIAN_ONLY and not hungarian:
                continue
            return era, length
        return None

    def _marker_after(self, i: int, hungarian: bool) -> tuple[str, int, int] | None:
        """`(era, first token, length)` of a marker at token `i`, or at `i + 1` when a filler word
        ("cal.", "years", "of") stands between."""
        for at in (i, i + 1):
            if at >= len(self.toks) or at in self.claimed:
                continue
            if at == i + 1 and self.toks[i].low not in FILLERS:
                break
            found = self._marker_at(at, hungarian)
            if found is not None:
                return found[0], at, found[1]
        return None

    def _marker_before(self, i: int, hungarian: bool) -> tuple[str, int, int] | None:
        """`(era, first token, length)` of a marker that ends at token `i - 1`."""
        for length in _MARKER_LENGTHS:
            if i - length < 0 or (i - length) in self.claimed:
                continue
            found = self._marker_at(i - length, hungarian)
            if found is not None and found[1] == length:
                return found[0], i - length, length
        return None

    # ---- the runs of numbers beside a unit word
    def _left_run(self, unit: int) -> list[_Number]:
        """The numbers right before the unit word, joined by connectors: "5th or 4th", "from the 1st
        to the 4th", "late 1st or early 2nd". Joined numbers are ordinals; adjacent ones may be
        plain ("4-3 millennium")."""
        run: list[_Number] = []
        k, gap = unit - 1, 0
        while k >= 0:
            number = self.by_last.get(k)
            if number is not None:
                if run and gap and not number.ordinal:
                    break
                run.insert(0, number)
                k, gap = number.first - 1, 0
            elif run and self._joint(k, unit) and gap < MAX_JOINTS:
                k, gap = k - 1, gap + 1
            else:
                break
        return run

    def _right_segments(self, unit: int) -> list[tuple[list[_Number], tuple[str, int, int] | None]]:
        """Roman numerals after the unit word, each run with the marker that closes it: "siglo V
        a. C.", "secoli XV-XIV a.C.", "siglos VII y V antes de Cristo", "siglos I a.C.- VI d.C."."""
        segments: list[tuple[list[_Number], tuple[str, int, int] | None]] = []
        k = unit + 1
        while True:
            run: list[_Number] = []
            gap = 0
            while k < len(self.toks) and self._marker_at(k, False) is None:
                number = self.nums.get(k)
                if number is not None and not number.arabic:
                    run.append(number)
                    k, gap = number.last + 1, 0
                elif run and self._joint(k, unit) and gap < MAX_JOINTS:
                    k, gap = k + 1, gap + 1
                else:
                    break
            if not run:
                return segments
            found = self._marker_after(run[-1].last + 1, False)
            segments.append((run, found))
            if found is None:
                return segments
            k, skipped = found[1] + found[2], 0
            while k < len(self.toks) and self._joint(k, unit) and skipped < MAX_JOINTS:
                k, skipped = k + 1, skipped + 1

    def _joint(self, k: int, unit: int) -> bool:
        tok = self.toks[k]
        if tok.low == "i":  # Roman one beside a unit word, "and" elsewhere
            return abs(k - unit) > 1
        return tok.low in JOINTS

    # ---- the statements
    def statements(self) -> list[Statement]:
        raw = sorted(self._unit_statements() + self._year_statements(), key=lambda r: r[0])
        # "the 8th century to the seventh century BC": a statement without a marker takes the next
        # one's when a range stands between them (`_only_joints`)
        for i in range(len(raw) - 2, -1, -1):
            (first, end, s), (start, _, nxt) = raw[i], raw[i + 1]
            if s.era is None and nxt.era is not None and self._only_joints(s, end, start):
                width = s.hi - s.lo if s.kind == YEAR else 0
                lo, hi = span(s.kind, s.number, nxt.era, width)
                raw[i] = (first, end, replace(s, era=nxt.era, lo=lo, hi=hi))
        return [s for _, _, s in raw if not (s.last_century and s.era != BC)]

    def _only_joints(self, statement: Statement, end: int, start: int) -> bool:
        """Whether the statement that ends at token `end` and the one that begins at token `start`
        are the two ends of one range: joint words between them with a range word among them, or a
        dash and nothing else, and no comma, bracket, colon or full stop in the text between. A
        determiner alone is no range ("In 1998 the 3rd century BC walls"), and a year does not take
        the era of an ancient date after it unless a range word says they belong together."""
        between = self.toks[end:start]
        if len(between) > MAX_JOINTS or not all(t.low in JOINTS for t in between):
            return False
        if start <= end:
            return True
        return self._joined(end, start, CONNECTORS if statement.kind != YEAR else YEAR_RANGE_WORDS)

    def _joined(self, end: int, start: int, words: frozenset[str]) -> bool:
        """Whether the joint words from token `end` up to token `start` make the numbers on either
        side the ends of one range: a dash between them, or one of `words` - and in either case no
        comma, bracket, colon or full stop in the text between ("In 1962, a 300 BC temple")."""
        gap = _ABBREVIATION_DOT.sub("", self.plain[self.toks[end - 1].end : self.toks[start].start])
        if _BREAKS.search(gap):
            return False
        if any(c in _HYPHENS or c in _MINUS for c in gap):
            return True
        return any(t.low in words for t in self.toks[end:start])

    def _unit_statements(self) -> list[_Raw]:
        out: list[_Raw] = []
        for u, (kind, abbreviated) in self.units.items():
            tok = self.toks[u]
            hungarian = tok.low.startswith(("szazad", "evezred"))
            run = self._left_run(u)
            if abbreviated and run and tok.start == self.toks[u - 1].end:
                continue  # "1600s": glued to its number, a decade
            if run:
                found = self._marker_after(u + 1, hungarian) or self._marker_before(
                    run[0].first, hungarian
                )
                segments = [(run, found)]
            elif not abbreviated:
                segments = self._right_segments(u)
            else:
                continue
            for run, found in segments:
                if abbreviated and found is None:
                    continue
                self._emit_unit(out, kind, u, run, found)
        return out

    def _emit_unit(
        self,
        out: list[_Raw],
        kind: str,
        unit: int,
        run: list[_Number],
        found: tuple[str, int, int] | None,
    ) -> None:
        era = found[0] if found else None
        limit = 40 if kind == CENTURY else 12
        after = max(unit + 1, run[-1].last + 1)
        start, end = min(run[0].first, unit), after
        if found:
            start, end = min(start, found[1]), max(end, found[1] + found[2])
        accepted = False
        for number in run:
            if not 1 <= number.value <= limit:
                continue
            lo, hi = span(kind, number.value, era)
            statement = Statement(kind, number.value, era, lo, hi, number.last_century)
            out.append((start, end, statement))
            accepted = True
        if accepted:
            self.claimed.update(range(run[0].first, after))
            if found:
                self.claimed.update(range(found[1], found[1] + found[2]))

    def _year_statements(self) -> list[_Raw]:
        """The plain years: an Arabic number without an ordinal suffix, alone or in a run joined by
        connectors ("3000 to 2500 BC"), with its marker after the run (one filler word may stand
        between) or before it; a minus sign before it is BC."""
        toks, out, i = self.toks, [], 0
        while i < len(toks):
            number = self.nums.get(i)
            if number is None or not number.arabic or i in self.claimed:
                i += 1
                continue
            run, k, gap = [number], number.last + 1, 0
            while k < len(toks):
                nxt = self.nums.get(k)
                if nxt is not None and nxt.arabic and k not in self.claimed:
                    run.append(nxt)
                    k, gap = nxt.last + 1, 0
                elif (
                    toks[k].low in JOINTS
                    and gap < MAX_JOINTS
                    and self._marker_at(k, False) is None
                    and (at := self._number_follows(k)) is not None
                    and self._joined(k - gap, at, CONNECTORS)
                ):
                    k, gap = k + 1, gap + 1
                else:
                    break
            if self._decade_width(run[-1]):
                k += 1  # the "s" of "50s" or the "talet" of "600-talet"
            hungarian = any(self._hungarian_ending(n.last) for n in run)
            found = self._marker_after(k, hungarian)
            if found is None:
                found = self._marker_before(run[0].first, hungarian)
            start, end = run[0].first, k
            if found:
                start, end = min(start, found[1]), max(end, found[1] + found[2])
            for n in run:
                if n.ordinal and n.last != n.first:
                    continue  # "5th": an ordinal, not a year
                era = BC if toks[n.first].minus else (found[0] if found else None)
                if era is None and not 100 <= n.value <= 2026:
                    continue  # "Table 12" is no year
                if n.value > 3_000_000:
                    continue
                lo, hi = span(YEAR, n.value, era, self._decade_width(n))
                out.append((start, end, Statement(YEAR, n.value, era, lo, hi)))
            if found:
                self.claimed.update(range(found[1], found[1] + found[2]))
            i = max(k, i + 1)
        return out

    def _decade_width(self, n: _Number) -> int:
        """The years a "50s", "AD 1600s" or "600-talet" runs on from its number: 9 for a decade, 99
        for a century of years, 0 for a plain year."""
        toks = self.toks
        after = toks[n.last + 1] if n.last + 1 < len(toks) else None
        if after is None:
            return 0
        glued_s = after.low == "s" and after.start == toks[n.last].end
        talet = toks[n.last].hyphen and after.low in _DECADE_WORDS
        if not (glued_s or talet):
            return 0
        return 99 if n.value % 100 == 0 else 9 if n.value % 10 == 0 else 0

    def _number_follows(self, k: int) -> int | None:
        """The index of the unclaimed number that comes after the joint words that start at token
        `k`."""
        for at in range(k, min(k + MAX_JOINTS + 1, len(self.toks))):
            if at in self.nums and self.nums[at].arabic and at not in self.claimed:
                return at
            if self.toks[at].low not in JOINTS:
                return None
        return None

    def _hungarian_ending(self, index: int) -> bool:
        toks = self.toks
        return (
            toks[index].hyphen
            and index + 1 < len(toks)
            and toks[index + 1].low in _HUNGARIAN_ENDINGS
        )


def statements(quote: str) -> list[Statement]:
    """Every year, century and millennium `quote` states, with the era it prints."""
    return _Quote(quote).statements()


def states_year(quote: str, year: int) -> bool:
    """Whether `quote` states `year`: its year with the right era, or the century or millennium it
    lies in (with the right era). A number with no marker is AD."""
    if year == 0:
        return False
    return any(s.lo <= year <= s.hi for s in statements(quote))


# --------------------------------------------------------------------------- years before present
_THOUSAND = r"tausend|mille|mil|mila|tys\.?|tysi[eę]cy|тыс\.?|тысяч|тисяч|ezer"
_MILLION = (
    r"millionen|mio\.?|millions?|millones|milioni|milh[oõ]es|miljoen|milion[oó]w|млн\.?|"
    r"миллион(?:ов|а)?|мільйон(?:ів)?"
)
_NUMBER = r"(?P<n1>\d+(?:[.,]\d+)?)(?:\s*(?:-|–|—|bis|und|à|y|a|e|do|и)\s*(?P<n2>\d+(?:[.,]\d+)?))?"
_SCALE = rf"(?:\s*(?P<scale>{_THOUSAND}|{_MILLION})(?:\s+(?:de|di|d['’]|von))?)?"
_QUALIFIER = (
    r"(?:(?:etwa|ca\.?|circa|rund|ungef[äa]hr|[üu]ber|mehr\s+als|environ|pr[èe]s\s+de|plus\s+de|"
    r"unos|aproximadamente|casi|m[aá]s\s+de|cerca\s+de|mais\s+de)\s+)?"
)
_FOREIGN_BP = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # German: vor 12.000 Jahren
        rf"\bvor\s+{_QUALIFIER}{_NUMBER}{_SCALE}\s*Jahren?\b",
        # French: il y a 12 000 ans
        rf"\bil\s+y\s+a\s+{_QUALIFIER}{_NUMBER}{_SCALE}\s*(?:ans|ann[ée]es)\b",
        # Spanish: hace 12.000 años
        rf"\bhace\s+{_QUALIFIER}{_NUMBER}{_SCALE}\s*a[nñ]os\b",
        # Portuguese: há 12 mil anos
        rf"\bh[áa]\s+{_QUALIFIER}{_NUMBER}{_SCALE}\s*anos\b",
        # Italian "12.000 anni fa", Portuguese/Spanish "12 mil anos atrás"
        rf"\b{_NUMBER}{_SCALE}\s*anni\s+fa\b",
        rf"\b{_NUMBER}{_SCALE}\s*(?:anos|años)\s+atr[áa]s\b",
        # Dutch, Polish, Russian
        rf"\b{_NUMBER}{_SCALE}\s*jaar\s+geleden\b",
        rf"\b{_NUMBER}{_SCALE}\s*lat\s+temu\b",
        rf"\b{_NUMBER}{_SCALE}\s*лет\s+(?:тому\s+)?назад\b",
        # "years before the present" spelt out, and the radiocarbon abbreviations AP and v. h.
        rf"\b{_NUMBER}{_SCALE}\s*(?:jahren?|ans|a[nñ]os|anni|anos)\s+"
        r"(?:vor\s+heute|avant\s+(?:le\s+)?pr[ée]sent|antes\s+del?\s+presente|"
        r"antes\s+do\s+presente|prima\s+del\s+presente|(?-i:AP))\b",
        rf"\b{_NUMBER}{_SCALE}\s*(?:cal\.?\s*(?-i:AP)|(?-i:v\.\s?h\.))",
    )
)


def bp_ages(quote: str) -> list[tuple[Decimal, ...]]:
    """The ages in years a quote states in a language other than English ("vor 12.000 Jahren", "il
    y a 12 000 ans", "hace 40 mil años", "1,2 Mio. Jahren", "12.000 anni fa", "12 000 лет назад",
    "12.000 ans AP"): one tuple of one or two ages (a range) per phrase. `answers.bp_dates` turns
    each into a year and a tolerance, exactly as it does for "12,000 BP"."""
    text = group_thousands(quote)
    out: list[tuple[Decimal, ...]] = []
    for pattern in _FOREIGN_BP:
        for match in pattern.finditer(text):
            scale = (match.group("scale") or "").casefold()
            factor = 1
            if scale:
                factor = 1_000_000 if re.fullmatch(_MILLION, scale, re.IGNORECASE) else 1000
            out.append(
                tuple(
                    Decimal(n.replace(",", ".")) * factor
                    for n in (match.group("n1"), match.group("n2"))
                    if n is not None
                )
            )
    return out
