"""The period vocabulary: a period name -> `(start_year, end_year)` table, and a century reader.

**Why this table exists.** Measured on 2026-10-04 in `output/remediation/fields/wd3/DECISIONS.jsonl`:
of the 2,113 curated sites lane WD3 asked for a `period_start`, 1,338 came back `unresolved` with
`value: null`, `value_page: null` and `quotes: []` - and 792 of those name a period in their own
`reasoning` (iron age 366, roman 243, bronze age 192, neolithic 171, prehistoric 43), 677 of them
one this table can turn into years. The research was done; the answer was thrown away. The owner's
decision of 2026-10-04: a named period IS a value.

**Where the names come from.** Twice, both measured: the vocabulary of those round-0 answers, and
the 34 distinct `time period` (P2348) items of the 2,029 curated sites that still have no period
(`output/remediation/period_wave/period_labels.json`, one read-only `wbgetentities` call). A name
may be **cultural, regional or geological** - "Ancient Greece", "Romano-British period", "Maya
civilization", "Silurian". That is a property of the source statement, not a reason to refuse it: a
city, a culture and a geological age each begin and end at a defensible year, and what a reader
needs is the conventional range, not a category.

**Where the ranges come from.** The first seven entries are the Canmore ingester's own table,
moved here unchanged (see `pipeline/ingesters/canmore_scotland.py`), because that ingester's
`_map_period` takes the **first key contained in an upper-cased SITETYPE period** - so the seven
must stay in front, in this order, or "EARLY IRON AGE" stops mapping to the Iron Age. The rest are
the conventional ranges of European archaeology (the periods of the standard relative chronology),
the Near Eastern Neolithic and Chalcolithic (the "four-fold" scheme of Arslan/Tzvetkov and
Özdoğan), the dynastic periods of Egypt and the classical cultures in their own literature, and
the geological ages as the ICS International Chronostratigraphic Chart gives them. A range is
convention, not a measurement of a site: the value a site gets is the period's start, and a site
answer that rests on a period word says so in `period_name`.

The key of an entry is the **folded** name (see `fold_name`): lower case, punctuation a space, one
leading article gone. "Prehistory", "prehistory" and "the Prehistory" are one entry, and so are
"post medieval" and "post-medieval" - two spellings may not drift into two ranges.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "PERIODS",
    "PeriodError",
    "century_range",
    "fold_name",
    "period_of",
    "start_year",
    "states_period",
]


class PeriodError(ValueError):
    """A period name the vocabulary does not know, or a century it cannot read."""


#: The whole vocabulary, keyed by the folded name of the period. The value is
#: `(start_year, end_year)`, years negative for BC, as `answers.YEARS` writes them
#: (`range(-3_000_000, 2027)`).
#:
#: THE ORDER IS PART OF THE CONTRACT: the first seven are Canmore's, in its order, because
#: `CanmoreScotlandIngester._map_period` walks the table and takes the first key the upper-cased
#: SITETYPE period contains. Every value that ingester matched before it is matched to the same
#: range still; a value it did not match (a Saxon or a Georgian period) now resolves, which is the
#: point of sharing the table.
PERIODS: dict[str, tuple[int, int]] = {
    # --- Canmore's own seven, unchanged
    "prehistoric": (-10000, -800),
    "neolithic": (-4000, -2500),
    "bronze age": (-2500, -800),
    "iron age": (-800, 400),
    "roman": (43, 410),
    "early medieval": (400, 1100),
    "medieval": (1100, 1500),
    # --- the Palaeolithic and the ice ages (the earliest stone tools; the end of the Pleistocene)
    "palaeolithic": (-3000000, -10000),
    "lower palaeolithic": (-3000000, -200000),
    "middle palaeolithic": (-300000, -40000),
    "upper palaeolithic": (-50000, -10000),
    # the same three under Wikidata's spelling, which the structured rung reads as it stands
    "paleolithic": (-3000000, -10000),
    # The Lower Palaeolithic is the Oldowan through the Acheulean, c. 2.6 Ma to 300 ka: the band
    # below the Middle Palaeolithic, not a half of the Palaeolithic as early/late are elsewhere.
    "lower paleolithic": (-2600000, -300000),
    "middle paleolithic": (-300000, -40000),
    "upper paleolithic": (-50000, -10000),
    "pleistocene": (-2580000, -9700),
    "late pleistocene": (-126000, -9700),
    # --- the Holocene sequence of north-west Europe
    "mesolithic": (-10000, -6000),
    "early mesolithic": (-10000, -8500),
    "late mesolithic": (-8500, -6000),
    "early neolithic": (-4000, -3500),
    "middle neolithic": (-3500, -2900),
    "late neolithic": (-2900, -2500),
    "pre pottery neolithic b": (-8200, -6900),
    "stone age": (-3000000, -3300),
    "copper age": (-4500, -3300),
    "chalcolithic": (-4500, -3300),
    "early bronze age": (-2500, -1600),
    # Early and late split the Bronze Age in half, so a "middle" is the Central European phase
    # rather than a slot between them: c. 2000-1550 BC.
    "middle bronze age": (-2000, -1550),
    "late bronze age": (-1600, -800),
    "british bronze age": (-2500, -800),
    "early iron age": (-800, -100),
    # the same: the British Middle Iron Age, c. 400 BC to AD 100
    "middle iron age": (-400, 100),
    "late iron age": (-100, 400),
    "british iron age": (-800, 100),
    "hallstatt": (-800, -450),
    "la tene": (-450, 1),
    "prehistory": (-10000, -800),
    "late prehistoric": (-4000, -800),
    # --- the classical Mediterranean
    "roman imperial": (-27, 476),
    "roman empire": (-27, 476),
    "roman britain": (43, 410),
    "romano british period": (43, 410),
    "migration period": (300, 700),
    "ancient greece": (-800, 146),
    "archaic greece": (-800, -480),
    "classical antiquity": (-800, 500),
    "hellenistic period": (-323, -31),
    "ancient rome": (-753, 476),
    "ancient history": (-3000, 500),
    "late antiquity": (284, 641),
    "middle ages": (500, 1500),
    "high medieval": (1000, 1300),
    "fourth dynasty of egypt": (-2613, -2494),
    "eighteenth dynasty of egypt": (-1550, -1295),
    # --- the Middle Ages and after, in Britain and on the Continent
    "saxon": (450, 1066),
    "anglo saxon": (450, 1066),
    "frankish": (481, 843),
    "merovingian": (481, 751),
    "carolingian": (751, 987),
    # the Viking Age, 793 (Lindisfarne) to 1066 (Stamford Bridge)
    "viking": (793, 1066),
    "post medieval": (1500, 1800),
    "georgian": (1714, 1837),
    "victorian": (1837, 1901),
    "edwardian": (1901, 1914),
    "historic": (1000, 1800),
    # --- the Americas, the Canaries and the geological record
    "mesoamerican preclassic period": (-2000, 250),
    "maya civilization": (-2000, 1697),
    "tiwanaku": (500, 1000),
    "guanches": (-1000, 1500),
    "silurian": (-443800, -419200),
    "carboniferous": (-358900, -298900),
}

#: A name is read as its folded words: every run of punctuation or whitespace a space, accents
#: removed, one leading article gone. `Prehistory`, `prehistory` and "the  Prehistory " reach one
#: entry; so do "Romano-British period", "romano british period" and "La Tène"/"la tene".
_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)
_COMBINING = re.compile(r"[\u0300-\u036f]")
_ARTICLES = frozenset({"a", "an", "the"})

#: How a folded text writes a century, and which half of it: "the 19th century", "19TH CENTURY",
#: "5th c.", "early 19th century". The number is digits - a Roman-numeral century is the year
#: checker's own reading (`answers.ordinal_forms`), not a range of a period. The half is read
#: first: "early 19th century" holds a plain "19th century" inside it.
_CENTURY = re.compile(r"\b(?P<half>early|late)\s+(?P<number>\d{1,4})(?:st|nd|rd|th|e)?\s+"
                      r"(?P<unit>century|centuries|c|cent)\b", re.IGNORECASE)
_CENTURY_PLAIN = re.compile(r"\b(?P<number>\d{1,4})(?:st|nd|rd|th|e)?\s+"
                            r"(?P<unit>century|centuries|c|cent)\b", re.IGNORECASE)
#: The word a century may follow. Any other word qualifies the century in a way this does not read
#: ("middle 19th century", "mid-Victorian 19th century") - an unread qualifier is refused, not
#: dropped: the whole century is not the range the source gave.
_BEFORE_A_CENTURY = frozenset(
    {"", "a", "an", "the", "c", "ca", "circa", "in", "of", "from", "to", "during", "early", "late"}
)  # fmt: skip
#: A century before the present: "BC", "BCE", "B.C." ("v. Chr." and "av. J.-C." are the year
#: checker's own reading again). A century without the marker is AD - Canmore writes its periods
#: without one (84,442 of its records carry nothing but a century word, measured 2026-10-04).
_BEFORE = re.compile(r"\bb\.?\s?c\.?\s?(?:e\.?)?\b", re.IGNORECASE)


#: Every name's own folded words, and the words a text may leave out: the name without a trailing
#: "period". Dropping that word is safe ("Romano-British" names the age); dropping "age" or "era" is
#: not ("iron", "late"), so those names are quoted whole.
_FORMS: dict[str, tuple[str, ...]] = {
    key: ((key, key.removesuffix(" period").strip()) if key.endswith(" period") else (key,))
    for key in PERIODS
}


def fold_name(name: str) -> str:
    """`name` as the key it is looked up under: its words, lower case, unaccented, without a
    leading article."""
    folded = _COMBINING.sub("", unicodedata.normalize("NFKD", str(name))).lower()
    words = _SEPARATORS.sub(" ", folded).strip().split()
    if words and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def period_of(name: str) -> tuple[int, int]:
    """The `(start_year, end_year)` of the period `name` names. `PeriodError` when the vocabulary
    does not know it - naming the name and how many it does know, so a wrong name can be read
    against the list instead of guessed."""
    key = fold_name(name)
    if not key:
        raise PeriodError(f"{name!r} is not a name of a period")
    try:
        return PERIODS[key]
    except KeyError:
        raise PeriodError(
            f"{name!r} is not one of the {len(PERIODS)} names the period vocabulary knows"
        ) from None


def start_year(name: str) -> int:
    """The year a period-word answer writes: the period's own start, never an invented one."""
    return period_of(name)[0]


def states_period(quote: str, name: str) -> bool:
    """Whether `quote` names the period `name` as its own words - "an Iron Age hillfort" names the
    Iron Age, "an iron mine" does not. The year is the table's; the quote only has to carry the
    name."""
    text = fold_name(quote)
    if not text:
        return False
    return any(f" {form} " in f" {text} " for form in _FORMS.get(fold_name(name), ()))


def century_range(text: str) -> tuple[int, int] | None:
    """The years of the century `text` names, or None when it names none.

    "19th century" -> (1801, 1900): the n-th century AD runs from n x 100 - 99 to n x 100, the
    n-th century BC from -n x 100 + 1 to -(n-1) x 100 (the 3rd century BC is 299-200 BC). "early"
    and "late" split it in half ("early 19th century" -> (1801, 1850)). A century without a BC
    marker is AD, the way Canmore writes one. None for a millennium, a spelled-out number
    ("nineteenth century"), a bare number and a half the table does not read ("middle 19th
    century") - a range this cannot read is not one it may round.
    """
    found = _CENTURY.search(text) or _CENTURY_PLAIN.search(text)
    if found is None:
        return None
    head = _SEPARATORS.sub(" ", text[: found.start()]).split()
    if (head[-1] if head else "") not in _BEFORE_A_CENTURY:
        return None
    number = int(found.group("number"))
    if number < 1:
        return None
    span = (number * 100 - 99, number * 100)  # the n-th century AD
    if _BEFORE.search(text[found.end() :]) is not None:
        span = (-number * 100 + 1, -(number - 1) * 100)  # the n-th century BC
    if found.groupdict().get("half") == "early":
        return span[0], (span[0] + span[1]) // 2
    if found.groupdict().get("half") == "late":
        return (span[0] + span[1]) // 2 + 1, span[1]
    return span
