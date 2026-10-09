"""The period vocabulary: a period name -> `(start_year, end_year)` table, and a century reader.

**Why this table exists.** Measured on 2026-10-04 in `output/remediation/fields/wd3/DECISIONS.jsonl`:
of the 2,113 curated sites lane WD3 asked for a `period_start`, 1,338 came back `unresolved` with
`value: null`, `value_page: null` and `quotes: []` - and 792 of those name a period in their own
`reasoning` (iron age 366, roman 243, bronze age 192, neolithic 171, prehistoric 43), 677 of them
one this table can turn into years. The research was done; the answer was thrown away. The owner's
decision of 2026-10-04: a named period IS a value.

**Where the names come from.** Three times, all measured: the vocabulary of those round-0 answers, the
34 distinct `time period` (P2348) items of the 2,029 curated sites that still have no period
(`output/remediation/period_wave/period_labels.json`, one read-only `wbgetentities` call), and the
1,849 dropped answers of lane WD3 - the names *they* used that this table did not hold, each added
with the conventional span the source its comment names gives. A name
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
"post medieval" and "post-medieval" - two spellings may not drift into two ranges. One word more is
read, on the name as well as on the quote: a trailing " period" is added and removed, so a bare
"Hellenistic" is the era the key `hellenistic period` holds and the era keeps one key (see `_key_of`).
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
    # --- the names lane WD3's own 1,849 dropped answers used and this table did not hold, added
    # 2026-10-04. Every range is the conventional span of the period or culture, read on the source
    # its comment names; a name whose start could not be sourced was left out and stays refused by
    # name (`archaic` -> `archaic greece`, `celtic` -> `hallstatt`/`la tene`, `persian` ->
    # `achaemenid`, `roman british` -> `romano british period`). `modern` is absent on purpose: it
    # would date modern institutions, which is the owner's call. So is every `site_type` - a
    # `hillfort`, `broch`, `oppidum`, `motte` or `clava cairn` is site_type's own value.
    # the Near East and the Mediterranean
    "achaemenid": (-550, -330),  # the Achaemenid Empire, 550 BC (Cyrus) to 330 BC (Alexander)
    # the Phoenician city-states, c. 1500-332 BC, to Alexander's conquest
    "phoenician": (-1500, -332),
    # the Nabataean Kingdom, independent from the mid-3rd c. BC, annexed AD 106
    "nabataean": (-250, 106),
    "byzantine": (330, 1453),  # the Byzantine Empire, 330-1453, to the fall of Constantinople
    # the Ottoman Empire, c. 1299 (Osman I's beylik) to the sultanate's end, 1922
    "ottoman": (1299, 1922),
    # Safavid Iran, 1501-1736; some place the end at 1722, when Isfahan fell
    "safavid": (1501, 1736),
    "inca": (1438, 1533),  # the Inca state, c. 1438-1533; the last Inca state fell in 1572
    # the Chanka of Peru, the 13th to the 15th century AD, after the fall of Wari
    "chanka": (1200, 1500),
    # the Aegean and Italy
    # Classical Greece, 510 BC (the last Athenian tyrant) to 323 BC (Alexander)
    "classical": (-510, -323),
    "geometric": (-900, -700),  # the Geometric period of Greek art, c. 900-700 BC
    "helladic": (-3200, -1050),  # the Helladic chronology of mainland Greece, c. 3200-1050 BC
    # the same range as `middle bronze age` above: the Greek Middle Bronze Age under its own name
    "middle helladic": (-2000, -1550),  # the Middle Helladic, c. 2000-1550 BC
    # Mycenaean Greece, c. 1750-1050 BC, the last phase of its Bronze Age
    "mycenaean": (-1750, -1050),
    "minoan": (-3100, -1100),  # the Minoan civilization, c. 3100-1100 BC
    "etruscan": (-900, -27),  # the Etruscan culture from c. 900 BC, incorporated into Rome by 27 BC
    "iberian": (-700, -100),  # the Iberian people and language, 7th to at least the 1st century BC
    # Egypt, India and China
    "old kingdom": (-2686, -2181),  # the Old Kingdom of Egypt, the Third to the Sixth dynasty
    # from the 18th-dynasty start this table holds above to the end of the 20th, 1069 BC
    "new kingdom": (-1550, -1069),
    "harappan": (-2600, -1900),  # the Mature Harappan phase of the Indus civilisation, 2600-1900 BC
    "indus valley": (-3300, -1300),  # the Indus Valley civilisation whole, 3300-1300 BC
    "han": (-202, 220),  # the Han dynasty, the Western Han from 202 BC to AD 220
    # northern and Atlantic Europe
    "funnelbeaker": (-4100, -2800),  # the Funnelbeaker culture, c. 4100-2800 BC
    # the Nuragic civilization, the 18th c. BC to Roman colonisation, 238 BC
    "nuragic": (-1800, -238),
    # the same era as `viking` above: the source's own span is c. 800-1050, the event span 793-1066
    "viking age": (793, 1066),
    "late middle ages": (1300, 1500),  # the Late Middle Ages, 1300-1500 AD
    # a conventional span, the source names no fixed boundary for either end
    "early modern": (1500, 1800),
    "slavic": (500, 1000),  # the early Slavs, c. the 5th to the 10th century AD
    # --- the regional chronologies lane WD5 needed (2026-10-09). Measured on the 14,616 period
    # texts of the earlier lanes' answers (wd1, wd3, wd4, wd5-pilot): the Maya and Andean sequences,
    # the Aegean Bronze Age and the Kushan, Roman and Seleucid eras were named hundreds of times and
    # were not names of this table, so a source that plainly said "dates from the Early Classic"
    # could not be read and a rule-made start was cleared to `Undated` (D12). Every start is the
    # one the source named in its comment gives; where the literature disagrees the line says so.
    # A name that two regions use for different spans stays out (`archaic`, `early dynastic`, `late
    # period`, `formative`): `tests/pipeline/test_periods.py::REFUSED` names each and why.
    #
    # Mesoamerica: the periodisation of Sharer and Traxler, The Ancient Maya (6th ed., 2006), and
    # Evans, Ancient Mexico and Central America (3rd ed., 2013). "Preclassic" is the Formative.
    "preclassic": (-2000, 250),  # the same era as `mesoamerican preclassic period` above
    "early preclassic": (-2000, -1000),
    "middle preclassic": (-1000, -400),
    "late preclassic": (-400, 250),
    "classic": (250, 900),  # the Classic period; read only capitalised (`_PROPER`)
    "early classic": (250, 600),
    "late classic": (600, 900),
    # the Terminal Classic overlaps the Late Classic's end: c. AD 800-1000 in the Maya lowlands
    "terminal classic": (800, 1000),
    "postclassic": (900, 1521),  # to the Spanish conquest of Tenochtitlan
    "early postclassic": (900, 1200),
    "late postclassic": (1200, 1521),
    # The Andes: Moseley, The Incas and Their Ancestors (2nd ed., 2001), after Rowe's horizons and
    # intermediate periods. `inca` above is the state, c. 1438-1533; the Late Horizon is Rowe's
    # 1476-1532.
    # read only capitalised (`_PROPER`): "the initial period" of a dig is not it
    "initial period": (-1800, -900),
    "early horizon": (-900, -200),  # Chavin's horizon, 900-200 BC (Burger 1992, Chavin)
    "early intermediate period": (-200, 600),
    "middle horizon": (600, 1000),
    "late intermediate period": (1000, 1476),
    "late horizon": (1476, 1532),
    "chavin": (-900, -200),  # Chavin de Huantar, 900-200 BC (Burger 1992)
    "wari": (600, 1100),  # the Wari state, c. AD 600 to 1100 (the Middle Horizon ends at 1000)
    "moche": (100, 800),  # the Moche culture of the north coast, c. AD 100-800
    # Eastern North America: Fagan, Ancient North America (4th ed., 2005); the Woodland period and
    # its three stages as the Wikipedia article `Woodland period` gives them.
    "woodland": (-1000, 1000),
    "early woodland": (-1000, -200),
    "middle woodland": (-200, 500),
    "late woodland": (500, 1000),
    # the Mississippian period proper, c. AD 1000 to the 16th century; the Emergent Mississippian
    # of AD 800-1000 is not counted
    "mississippian": (1000, 1600),
    # Egypt: the chronology of Shaw (ed.), The Oxford History of Ancient Egypt (2000), which
    # `old kingdom` and `new kingdom` above already follow.
    "predynastic": (-5300, -3000),
    "first intermediate period": (-2181, -2055),
    "middle kingdom": (-2055, -1650),
    "second intermediate period": (-1650, -1550),
    "third intermediate period": (-1069, -664),
    "ptolemaic": (-305, -30),  # from Ptolemy I's kingship (305 BC) to the death of Cleopatra VII
    # The Aegean Bronze Age: the conventional dates of Warren and Hankey, Aegean Bronze Age
    # Chronology (1989) and Shelmerdine (ed.), The Cambridge Companion to the Aegean Bronze Age
    # (2008); the Cyclades after Renfrew, The Emergence of Civilisation (1972). The three Minoan
    # and Helladic names join `minoan` and `helladic` above, which hold the whole span.
    "early minoan": (-3100, -2100),
    "middle minoan": (-2100, -1600),
    "late minoan": (-1600, -1100),
    "early helladic": (-3200, -2000),
    "late helladic": (-1600, -1050),
    "early cycladic": (-3200, -2000),
    "middle cycladic": (-2000, -1600),
    "late cycladic": (-1600, -1050),
    # The Near East: Van de Mieroop, A History of the Ancient Near East (3rd ed., 2016), the
    # middle chronology; Rothman (ed.), Uruk Mesopotamia and its Neighbors (2001) for Uruk;
    # Bryce, The Kingdom of the Hittites (2005) for the Hittites.
    "uruk": (-4000, -3100),
    "jemdet nasr": (-3100, -2900),
    "akkadian": (-2334, -2154),  # the Akkadian Empire, Sargon to the Gutian conquest
    "ur iii": (-2112, -2004),  # the Third Dynasty of Ur
    # the period after the Ur III collapse to the Hittite sack of Babylon, middle chronology; the
    # First Dynasty of Babylon alone begins c. 1894 BC
    "old babylonian": (-2004, -1595),
    "neo assyrian": (-911, -609),  # Adad-nirari II to the fall of Harran
    "neo babylonian": (-626, -539),  # Nabopolassar to Cyrus's conquest
    "hittite": (-1650, -1178),  # Labarna's Old Kingdom to the collapse of the empire
    "seleucid": (-312, -63),  # the Seleucid Empire, to Pompey's annexation of Syria
    "parthian": (-247, 224),  # the Arsacid dynasty, to Ardashir I
    "sasanian": (224, 651),  # Ardashir I to the fall of Yazdegerd III
    "sassanid": (224, 651),  # the same era, spelt as older English does
    # South and East Asia. India: Thapar, Early India (2002), Gupta and Kushan after Wikipedia's
    # Kushan Empire and Gupta Empire (30-375, 320-550), the standard dates of the cited histories.
    # China: Shaughnessy (ed.), The Cambridge History of Ancient China (1999). Japan: Habu,
    # Ancient Jomon of Japan (2004); the Yayoi and the Kofun bounds are the handbooks' usual
    # 300 BC-AD 300 and AD 300-538. Korea: the traditional foundation years of Silla (57 BC), Goguryeo (37 BC) and
    # Baekje (18 BC), as the Samguk sagi gives them.
    "mauryan": (-322, -185),
    "kushan": (30, 375),
    "kushana": (30, 375),  # the same era, in the spelling the Archaeological Survey of India uses
    "gupta": (320, 550),  # from the Gupta era's own epoch, AD 319/320 (Chandragupta I)
    "zhou": (-1046, -256),
    "jomon": (-14000, -300),
    "yayoi": (-300, 300),
    "kofun": (300, 538),
    "three kingdoms of korea": (-57, 668),
    "silla": (-57, 935),
    "goguryeo": (-37, 668),
    "koguryo": (-37, 668),  # the same state in the older romanisation
    "baekje": (-18, 660),
    # Rome beyond `roman imperial` above: the Republic, and the two reigns named most often.
    "roman republic": (-509, -27),
    "augustan": (-27, 14),
    "flavian": (69, 96),
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
_CENTURY = re.compile(
    r"\b(?P<half>early|late)\s+(?P<number>\d{1,4})(?:st|nd|rd|th|e)?\s+"
    r"(?P<unit>century|centuries|c|cent)\b",
    re.IGNORECASE,
)
_CENTURY_PLAIN = re.compile(
    r"\b(?P<number>\d{1,4})(?:st|nd|rd|th|e)?\s+"
    r"(?P<unit>century|centuries|c|cent)\b",
    re.IGNORECASE,
)
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
#: not ("iron", "late"), so those names are quoted whole. `_key_of` reads a *name* the same way for
#: a lookup, so the word has one reading and one place in this module.
#: The names that are ordinary English words when written small: "the initial period of the dig", "a
#: classic example", "ancient woodland". A quote names them only capitalised in its own spelling
#: ("the Initial Period", "the Classic period", "Late Classic", "the Woodland period"); the folded
#: comparison below would read both. A sentence begins with a capital too: there the name needs its
#: next word capitalised as well ("Classic Maya", "Initial Period"), so "Classic examples of" and
#: "Woodland pottery" are not it. Their forms stay whole, so "initial" alone is not the Initial
#: Period.
_PROPER = frozenset({"classic", "initial period", "woodland"})
_FORMS: dict[str, tuple[str, ...]] = {
    key: (
        (key, key.removesuffix(" period").strip())
        if key.endswith(" period") and key not in _PROPER
        else (key,)
    )
    for key in PERIODS
}
_CAPITALISED: dict[str, re.Pattern[str]] = {
    key: re.compile(
        r"(?<![^\W_])"
        + re.escape(key.split()[0].capitalize())
        + "".join(r"[\s-]+(?i:" + re.escape(word) + ")" for word in key.split()[1:])
        + r"(?![^\W_])"
    )
    for key in _PROPER
}


_SENTENCE_START: dict[str, re.Pattern[str]] = {
    key: re.compile(
        r"[\s-]+".join(word.capitalize() for word in key.split())
        + (r"[\s-]+[A-Z]" if len(key.split()) == 1 else "")
    )
    for key in _PROPER
}


def _names_capitalised(key: str, quote: str) -> bool:
    """Whether `quote` prints the `_PROPER` name `key` capitalised: anywhere inside a sentence, at
    the start of one only with the next word capitalised."""
    for found in _CAPITALISED[key].finditer(quote):
        before = quote[: found.start()].rstrip()
        inside_sentence = bool(before) and before[-1] not in ".!?"
        if inside_sentence or _SENTENCE_START[key].match(quote, found.start()):
            return True
    return False


def fold_name(name: str) -> str:
    """`name` as the key it is looked up under: its words, lower case, unaccented, without a
    leading article."""
    folded = _COMBINING.sub("", unicodedata.normalize("NFKD", str(name))).lower()
    words = _SEPARATORS.sub(" ", folded).strip().split()
    if words and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def _key_of(name: str) -> str | None:
    """The key `name` is read under, or None when this vocabulary does not know it. The folded name
    as it is, the same name with " period" appended, the same name with a trailing " period" removed:
    four keys carry that word ("romano british period", "migration period", "hellenistic period",
    "mesoamerican preclassic period") and an agent that sends the bare word names an era the table
    holds, so it is read rather than refused and the era keeps one key. " period" is the only word
    read this way - "age" and "era" are not dropped, because "iron" and "late" are names of their
    own - and a name no form reaches stays refused, by name."""
    key = fold_name(name)
    for form in (key, f"{key} period", key.removesuffix(" period").strip()):
        if form in PERIODS:
            return form
    return None


def period_of(name: str) -> tuple[int, int]:
    """The `(start_year, end_year)` of the period `name` names. `PeriodError` when the vocabulary
    does not know it - naming the name and how many it does know, so a wrong name can be read
    against the list instead of guessed."""
    if not fold_name(name):
        raise PeriodError(f"{name!r} is not a name of a period")
    key = _key_of(name)
    if key is None:
        raise PeriodError(
            f"{name!r} is not one of the {len(PERIODS)} names the period vocabulary knows"
        )
    return PERIODS[key]


def start_year(name: str) -> int:
    """The year a period-word answer writes: the period's own start, never an invented one."""
    return period_of(name)[0]


def states_period(quote: str, name: str) -> bool:
    """Whether `quote` names the period `name` as its own words - "an Iron Age hillfort" names the
    Iron Age, "an iron mine" does not. The year is the table's; the quote only has to carry the
    name. The name is read through `_key_of` like `period_of` reads it, because the one answer this
    gates reads both: a bare "Hellenistic" that resolves to years but is not a key of its own would
    pass the year and then fail here."""
    text = fold_name(quote)
    if not text:
        return False
    key = _key_of(name)
    if key is None:
        return False
    if key in _PROPER and not _names_capitalised(key, quote):
        return False
    return any(f" {form} " in f" {text} " for form in _FORMS[key])


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
