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

**Regional starts (owner decision D101, 2026-11-06).** A period that began at different times in
different regions - the Neolithic, the Chalcolithic, the Bronze and Iron Ages and their phases, the
Roman period of each province - writes its start in the site's own country (`REGIONAL_STARTS`,
`start_year(name, country=...)`), each value cited where it is defined; a country without a cited
start gets no year. `PERIODS` keeps the conventional ranges the ingesters and span readers use.

**Coarse words (owner decision D111, 2026-11-06).** "Stone Age", a "Palaeolithic" without its
phase, "prehistoric", "ancient history", "classical antiquity" and a bare "Bronze Age" where the
table divides it give no year (`COARSE`, `SUBPHASE_REQUIRED`). D113 added the country and epoch
starts the D99 pilot's sources needed, and names in comments the ones Wikipedia gives no single
start for.

**Epoch bands (owner decision D136, 2026-11-07).** A site whose only dating is an epoch word is
written as a band, not as a year of its own: the predefined period band
(`pipeline.utils.text.PERIOD_BUCKETS`) in which the epoch begins - in the site's country where
`REGIONAL_STARTS` has a value, else at the conventional `PERIODS` start - stored as the band's edge
(`bucket_edge`), as the 511 band rows of 2026-10-04 were (`epoch_band`). The D111 refusals are
refusals of an exact year: `start_year` keeps them, and a coarse word or a bare Bronze Age gets a
band by its start.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

from pipeline.utils.text import bucket_edge, categorize_period

__all__ = [
    "COARSE",
    "PERIODS",
    "EpochBand",
    "REGIONAL_STARTS",
    "SUBPHASE_REQUIRED",
    "PeriodError",
    "century_range",
    "country_key",
    "epoch_band",
    "fold_name",
    "is_regional",
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
    # --- the epochs the D99 pilot's sources named without a row (owner decision D113 item 3,
    # 2026-11-06): each span is the English Wikipedia article's own, read through the MediaWiki API
    # on 2026-11-06 (the words in quotes are the article's). Read in the cached sources of the 615
    # undated sites (`output/remediation/fields/wd5x/`) and left out: `talaiotic` (the article gives
    # "around 1500 BCE" and "around 1000 BCE" for its first manifestations), `orientalizing` (its
    # start is "the later part of the 8th century BC", no year), `gojoseon` (2333 BCE is the
    # Samguk yusa's legend), `mousterian` and `dilmun` (see `REFUSED` in the tests).
    # `Chimor`: "The culture arose about 900 CE ... conquered by the Inca emperor Topa Inca Yupanqui
    # around 1470"
    "chimu": (900, 1470),
    # `Later Roman Empire`: "traditionally covering the period from 284 CE to 641 CE" - the span of
    # `late antiquity` above, under the name the Italian and Maltese sources use
    "late roman": (284, 641),
    # `Vinča culture`: "a Neolithic archaeological culture of Southeast Europe, dated to the period
    # 5400-4500 BC"
    "vinca": (-5400, -4500),
}


# ------------------------------------------------------------------------- the regional starts
# Owner decision D101 (2026-11-06): a period word that began at different times in different parts
# of the world is no one year. "Neolithic" was -4000 for every site - Britain's start - so a
# Neolithic tell in Jordan, begun some six thousand years earlier, was written into the wrong
# band. For the names below, the year a period-word answer writes is the start of that period in
# the site's own country; a country this table gives no start for is refused by name, never
# given another country's year. A year the same source states for the site beats the period word
# altogether (the answer checks of `scripts/remediation/fields/answers.py` hold that rule).
#
# `PERIODS` keeps its conventional ranges: Canmore's ingester and the readers that compare spans
# use them, and a name absent below starts at the same year everywhere.
#
# Every value is the start the cited English Wikipedia article states for that region (each
# article's text read through the MediaWiki API on 2026-11-06; the words in quotes are the
# article's own). Where an article gives the region's own scheme it is used as a whole (Iberia,
# the Near East, Britain); where it gives a range, its first year. A country is keyed by its
# folded spelling (`country_key`), every spelling the curated rows use or a researcher may send.

_BRITAIN = ("england", "scotland", "wales", "northern ireland", "united kingdom",
            "great britain", "isle of man")  # fmt: skip
_IRELAND = ("ireland", "republic of ireland")
_TURKIYE = ("turkiye", "turkey")
_LEVANT = ("syria", "syrian arab republic", "lebanon", "israel", "palestine", "state of palestine",
           "palestinian territories", "jordan")  # fmt: skip
_IRAN = ("iran", "islamic republic of iran")
_CAUCASUS = ("georgia", "armenia", "azerbaijan")
_SCANDINAVIA = ("denmark", "sweden", "norway")
_CENTRAL_EUROPE = ("germany", "austria", "switzerland", "czechia", "czech republic", "slovakia",
                   "poland")  # fmt: skip
_LOW_COUNTRIES = ("netherlands", "belgium", "luxembourg")
_IBERIA = ("spain", "portugal")
#: The Starcevo-Koros-Cris complex: "an archaeological culture of Southeastern Europe", with sites
#: and samples from Serbia, Croatia, Romania and Hungary (`Starčevo culture`).
_STARCEVO = ("serbia", "republic of serbia", "kosovo", "croatia", "romania", "hungary",
             "bosnia and herzegovina", "north macedonia", "macedonia", "bulgaria")  # fmt: skip
#: Southeastern Europe in the sense of `Iron Age` ("In Anatolia and the Caucasus, or Southeast
#: Europe, the Iron Age began c. 1300 BC") - Greece has a start of its own (`_GREEK_IRON_AGE`).
_SOUTHEAST_EUROPE = ("bulgaria", "romania", "serbia", "republic of serbia", "kosovo",
                     "north macedonia", "macedonia", "albania", "montenegro",
                     "bosnia and herzegovina")  # fmt: skip


def _each(countries: tuple[str, ...], year: int) -> dict[str, int]:
    return dict.fromkeys(countries, year)


#: The start of the Neolithic per country.
_NEOLITHIC: dict[str, int] = {
    # `Pre-Pottery Neolithic A`: "c. 12,000 - c. 10,800 years ago, that is, 10,000-8800 BCE" - the
    # Levant, Anatolia and upper Mesopotamia
    **_each((*_TURKIYE, *_LEVANT, "iraq"), -10000),
    # `Ganj Dareh` (Zagros): "c. 8200 BC, and have yielded the earliest evidence for goat
    # domestication in the world"
    **_each(_IRAN, -8200),
    # `Prehistoric Cyprus`: "The oldest evidence of Neolithic settlement is dated to 8800-8600 BC."
    "cyprus": -8800,
    # `Prehistoric Egypt`: "Neolithic (c. 6000-4000 BC)"
    "egypt": -6000,
    # `Neolithic Europe`: farming from "6500 BCE at Knossos, Franchthi Cave, and a number of
    # mainland sites in Thessaly"
    "greece": -6500,
    # `Starčevo culture`: "dating to the Neolithic period between c. 6200 and 4500 BCE"
    **_each(_STARCEVO, -6200),
    # `Cardium pottery`: "Settlements then appear in Albania and Dalmatia on the eastern Adriatic
    # coast dating to between 6100 and 5900 BC."
    **_each(("albania", "montenegro"), -6100),
    # `Cardium pottery`: "The earliest date in Italy comes from Coppa Nevigata ... perhaps as early
    # as 6000 cal B.C."
    "italy": -6000,
    # `History of Malta`: "Neolithic farmers from Sicily around 5400 BC"
    "malta": -5400,
    # `Prehistoric Iberia`: "Neolithic (c. 5.6 - 3.2 ka BC)"
    **_each(_IBERIA, -5600),
    # `Linear Pottery culture`: "began conventionally at 5500 BC"; `Prehistoric France`: "the
    # Linear Pottery culture (c. 5500 - c. 4500 BC)"
    **_each((*_CENTRAL_EUROPE, "france"), -5500),
    # `Linear Pottery culture`: "its arrival in the Netherlands at about 5200 BC" (the Belgian
    # sites Darion and Remicourt belong to the same spread)
    **_each(_LOW_COUNTRIES, -5200),
    # `Shulaveri-Shomu culture`: "from around the end of the seventh millennium BC"
    **_each(_CAUCASUS, -6000),
    # `Neolithic in China`: "Neolithization ... mainly occurred between 7000 and 5000 BCE"
    "china": -7000,
    # `Mehrgarh`: "a small farming village dated from 7000 BCE"
    "pakistan": -7000,
    # D113 item 3 (2026-11-06), the same reading:
    # `History of Finland`: "By 5300 BC, pottery was present in Finland. ... This marks the
    # beginning of the Neolithic period for Finland"
    "finland": -5300,
    # `Narva culture`: "a European Neolithic archaeological culture in present-day Estonia, Latvia,
    # Lithuania ... The culture spanned from c. 5300 to 1750 BC."
    **_each(("estonia", "latvia", "lithuania"), -5300),
    # `Neolithic`, "Northwestern Africa": "The neolithization of Northwestern Africa was initiated
    # by Iberian, Levantine (and perhaps Sicilian) migrants around 5500-5300 BC."
    **_each(("morocco", "algeria", "tunisia"), -5500),
    # `Dapenkeng culture`: "an early Neolithic culture that appeared in northern Taiwan between 4000
    # and 3000 BC"
    "taiwan": -4000,
    # Left without a year: India - `South Asian Stone Age` gives c. 7000 BCE in the north-west
    # (Mehrgarh, Pakistan), "after 3000 BCE" in South India and "after mid-3rd millennium BCE" in the
    # Ganges Plain, so one country holds starts four millennia apart.
    # `Funnelbeaker culture` (4100-2800 BCE) and `Archaeology of Northern Europe`: "The transition
    # to the Neolithic is characterized by the Funnelbeaker culture in the 4th millennium BC."
    **_each(_SCANDINAVIA, -4000),
    # `Neolithic British Isles`: "Around 4000 BC, migrants began arriving from Central Europe";
    # `Prehistoric Ireland`: "Neolithic (4000-2500 BC)"
    **_each((*_BRITAIN, *_IRELAND), -4000),
}

#: The start of the Chalcolithic (Copper Age) per country.
_CHALCOLITHIC: dict[str, int] = {
    # `Neolithic`: "It lasted in West Asia until the transitional period of the Chalcolithic (Copper
    # Age) from about 6,500 years ago (4500 BC)"
    **_each((*_TURKIYE, *_LEVANT, "iraq", *_IRAN), -4500),
    # `Prehistoric Cyprus`: "around 3500 BC with appearance of the first metalwork and the beginning
    # of the Chalcolithic"
    "cyprus": -3500,
    # `Chalcolithic Europe`: "5000 BC to 3000 BC, copper started being used first in Southeast
    # Europe" - Varna, Gumelnita and Vinca
    **_each(("bulgaria", "romania", "serbia", "republic of serbia"), -5000),
    # `Prehistoric Iberia`: "Chalcolithic or Copper Age (c. 3.2 - 1.9 ka BC)"
    **_each(_IBERIA, -3200),
    # `Bronze Age Britain`: "The period from 2500 BC to 2000 BC has been called the 'Late
    # Neolithic/Early Bronze Age'" - the Beaker copper phase of Great Britain and Ireland
    **_each((*_BRITAIN, *_IRELAND), -2500),
}

#: The start of the Bronze Age per country.
_BRONZE_AGE: dict[str, int] = {
    # `Bronze Age`, "Near East Bronze Age divisions": "Early Bronze Age (EBA or EB): 3300-2100 BC"
    **_each((*_TURKIYE, *_LEVANT), -3300),
    # `Bronze Age`: "The Mesopotamian Bronze Age began c. 3500 BC"
    "iraq": -3500,
    # `Bronze Age`: "In Ancient Egypt, the Bronze Age began in the Protodynastic Period c. 3150 BC."
    "egypt": -3150,
    # `Bronze Age`: "The Aegean Bronze Age began c. 3200 BC"
    "greece": -3200,
    # `Prehistoric Cyprus`: "The new era was introduced by people from Anatolia who came to Cyprus
    # around 2400 BC."
    "cyprus": -2400,
    # `Bronze Age`: "The Bronze Age on the Indian subcontinent began c. 3300 BC with the beginning
    # of the Indus Valley Civilization."
    **_each(("pakistan", "india"), -3300),
    # `Kura-Araxes culture`: "existed from about 4000 BC until about 2000 BC"
    **_each(_CAUCASUS, -4000),
    # `Bronze Age Britain`: "Early Bronze Age (EBA), c. 2500-1500 BC" - Great Britain and Ireland
    **_each((*_BRITAIN, *_IRELAND), -2500),
    # `Bronze Age Europe`: "In Central Europe, the early Bronze Age Unetice culture (2300-1600 BC)"
    **_each(_CENTRAL_EUROPE, -2300),
    # `Prehistoric France`: "the Early Bronze Age Rhone culture (c. 2300-1600 BC)"
    "france": -2300,
    # `Bronze Age Europe`: "The Early Bronze Age (2300-1700 BC)" of Italy
    "italy": -2300,
    # `Prehistoric Iberia`: "Bronze Age (c. 1.9 ka - 750 BC)"
    **_each(_IBERIA, -1900),
    # `Nordic Bronze Age`: "a period of Scandinavian prehistory from c. 2000/1750-500 BC"
    **_each(_SCANDINAVIA, -2000),
    # D113 item 3 (2026-11-06), the same reading:
    # `History of Finland`: "The Finnish Bronze Age started in approximately 1500 BC"
    "finland": -1500,
    # `Prehistory of the Netherlands`: "The Bronze Age probably started somewhere around 2000 BC
    # and lasted until around 800 BC." (Belgium and Luxembourg are not in the article)
    "netherlands": -2000,
    # `History of Malta`: "Their civilization collapsed in around 2350 BC; the islands were
    # repopulated by Bronze Age people soon afterwards." and its section "Bronze Age (2350 BC-700 BC)"
    "malta": -2350,
    # Left without a year: China - `Bronze Age`: "there is no universally accepted definition or
    # chronological boundary for the Bronze Age in the context of Chinese prehistory"; Korea -
    # `Bronze Age` says "began c. 1000-800 BC", `Mumun pottery period` that "local bronze production
    # is not proven to have occurred until approximately the 13th century BCE" and the term "may be
    # misleading"; Serbia, Bulgaria, Croatia and the other Balkan countries - `Prehistory of
    # Southeast Europe` heads its Bronze Age "3,500 - 1,100 BCE", starts its Early Bronze Age in the
    # "20th ... centuries BCE" and says it "begins late, around 1800 BCE" in the central and eastern
    # part: three starts, 1,700 years apart.
}

#: The start of the Middle Bronze Age per country.
_MIDDLE_BRONZE_AGE: dict[str, int] = {
    # `Bronze Age`: "Middle Bronze Age (MBA or MB) or Intermediate Bronze Age (IBA or IB): 2100-1550
    # BC"
    **_each((*_TURKIYE, *_LEVANT), -2100),
    # `Helladic chronology`: the Early Helladic III ends "c.2200-2000 BC"
    "greece": -2000,
    # `Bronze Age Britain`: "Middle Bronze Age (MBA), 1500-1000 BC"
    **_each((*_BRITAIN, *_IRELAND), -1500),
    # `Prehistoric France`: "the Middle Bronze Age Tumulus culture (c. 1600-1200 BC)"
    "france": -1600,
    # `Bronze Age Europe`: Italy's "Middle Bronze Age (1700-1350 BC)"
    "italy": -1700,
}

#: The start of the Late Bronze Age per country.
_LATE_BRONZE_AGE: dict[str, int] = {
    # `Bronze Age`: "Late Bronze Age (LBA or LB): 1550-1200 BC"
    **_each((*_TURKIYE, *_LEVANT), -1550),
    # `Helladic chronology`: "The Late Helladic (c. 1550 - c. 1050 BC)"
    "greece": -1550,
    # `Bronze Age Britain`: "Late Bronze Age (LBA), 1000-700 BC"
    **_each((*_BRITAIN, *_IRELAND), -1000),
    # `Bronze Age Europe`: Italy's "Recent Bronze Age (1350-1150 BC)", the first of its two late
    # phases
    "italy": -1350,
}

#: The start of the Iron Age per country.
_IRON_AGE: dict[str, int] = {
    # `Iron Age`: "In Anatolia and the Caucasus, or Southeast Europe, the Iron Age began c. 1300 BC."
    **_each((*_TURKIYE, *_CAUCASUS, *_SOUTHEAST_EUROPE), -1300),
    # `Iron Age`: "In the ancient Near East, this transition occurred simultaneously with the Late
    # Bronze Age collapse, during the 12th century BC."
    **_each((*_LEVANT, "iraq", *_IRAN), -1200),
    # `Helladic chronology`: the Bronze Age of Greece ends with the Late Helladic, "c. 1050 BC";
    # `Prehistoric Cyprus`: "The Iron Age follows the Submycenean period (1125-1050 BC)"
    **_each(("greece", "cyprus"), -1050),
    # `Villanovan culture`: "(c. 900-700 BCE) ... the earliest Iron Age culture of Italy"
    "italy": -900,
    # `Prehistoric Iberia`: "Iron Age (c. 750 - 218 BC)"
    **_each(_IBERIA, -750),
    # `Iron Age`: "In Central and Western Europe, the Iron Age lasted from c. 800 BC to c. 1 BC"
    **_each((*_CENTRAL_EUROPE, "hungary", "france", *_LOW_COUNTRIES), -800),
    # `Nordic Bronze Age`: "Around the 5th century BC, the Nordic Bronze Age was succeeded by the
    # Pre-Roman Iron Age"
    **_each(_SCANDINAVIA, -500),
    # `British Iron Age`: "The Iron Age in Great Britain spanned from c. 800 BC"
    **_each(_BRITAIN, -800),
    # `Bronze Age Britain`: "In Ireland ... iron metallurgy does not appear until about 550 BC."
    **_each(_IRELAND, -550),
    # `Iron Age`: "The Iron Age in India is stated as beginning with the ironworking Painted Grey
    # Ware culture, dating from c. 1200 BC"
    "india": -1200,
    # `Iron Age in India`: "The protohistoric Early Iron Age in Sri Lanka lasted from 1000 BC"
    "sri lanka": -1000,
    # D113 item 3 (2026-11-06), the same reading:
    # `History of Finland`: "The Iron Age in Finland is considered to have lasted from c. 500 BC
    # until c. 1300 AD."
    "finland": -500,
    # `Iron Age`: '"Iron Age" in the context of China is used sometimes for the transitional period
    # of c. 900 BC to 100 BC during which ferrous metallurgy was present even if not dominant.'
    "china": -900,
    # Left without a year: Egypt - neither `Iron Age` (its "Egypt" section dates no start) nor
    # `Ancient Egypt` gives one.
}

#: The year Roman rule begins in the province a country lay in: the invasion or annexation the
#: cited article dates. Italy has none - it was Rome's own land, conquered over centuries, not a
#: province - and neither have Ireland, Northern Ireland and Scandinavia, which Rome never ruled.
_ROMAN: dict[str, int] = {
    # `Roman Britain`: "The occupation lasted from 43 AD to 410 AD."
    "england": 43,
    # `Wales in the Roman era`: "The Roman era in the area of modern Wales began in 48 AD"
    "wales": 48,
    # `Scotland during the Roman Empire`: "Roman legions arrived in the territory of modern Scotland
    # around AD 71"
    "scotland": 71,
    # `Hispania`: "Roman armies invaded the Iberian Peninsula in 218 BC"
    **_each(_IBERIA, -218),
    # `History of Malta`: the Carthaginians "ruled the islands until they fell in 218 BC to the
    # Roman Republic"
    "malta": -218,
    # `Gallia Narbonensis`: "The area became a Roman province in 121 BC."
    "france": -121,
    # `Gallia Belgica`: "In 57 BC, Julius Caesar led the conquest of northern Gaul"
    **_each(("belgium", "luxembourg"), -57),
    # `Raetia`: the Raetians "retained their independence until their subjugation in 15 BC by
    # Tiberius and Drusus"
    "austria": -15,
    # `Achaia (Roman province)`: "annexed by the Roman Republic in 146 BC following the sack of
    # Corinth"
    "greece": -146,
    # `Asia (Roman province)`: "created following the Roman Republic's annexation of the Attalid
    # Kingdom in 133 BC"
    **_each(_TURKIYE, -133),
    # `Roman Syria`: "annexed to the Roman Republic in 64 BCE by Pompey"
    **_each(("syria", "syrian arab republic", "lebanon"), -64),
    # `Siege of Jerusalem (63 BC)`: Pompey "had spent the years of 64 and 63 BC in bringing Roman
    # law and order to the region"; Jerusalem fell in 63 BC
    **_each(
        ("israel", "palestine", "state of palestine", "palestinian territories", "jordan"), -63
    ),
    # `Roman Egypt`: "from the time it was conquered by Roman forces in 30 BC"
    "egypt": -30,
    # `Africa (Roman province)`: "It was established in 146 BC"
    "tunisia": -146,
    # `Numidia`: "Caesar annexed eastern Numidia into the Roman province of Africa Nova" (46 BC)
    "algeria": -46,
    # `Mauretania Tingitana`: "in about 44 AD Roman Emperor Claudius annexed the kingdom"
    "morocco": 44,
    # `Roman Cyprus`: "Cyprus was annexed by the Romans in 58 BC"
    "cyprus": -58,
    # `Roman Dacia`: "a province of the Roman Empire from 106"
    "romania": 106,
    # `Pannonia`: "Illyricum was divided into Dalmatia ... and Pannonia ... in 8 or 9 AD"
    "hungary": 9,
    # D113 item 3 (2026-11-06): `History of Albania`: the Illyrian Wars "eventually resulted in
    # defeat for the Illyrians by 168 BC and the end of Illyrian independence"; "In the early 2nd
    # century BC, the area was annexed by Rome"
    "albania": -168,
    # Left without a year, like Germany, the Netherlands and Switzerland (owner decision D113): a
    # country Rome reached at very different times. Serbia - `History of Serbia`: "conquered parts
    # of modern-day Serbia in the 2nd century BC, in 167 BC ... the rest of Central Serbia in 75 BC
    # ... Srem was conquered by 9 BC and Bačka and Banat in 106 AD". Croatia - `History of Croatia`:
    # "In 168 BC, the Roman Republic established a protectorate south of the Neretva river. The area
    # north of the Neretva was slowly incorporated ... c. 32-27 BC". Bulgaria - `History of
    # Bulgaria`: "In 188 BC, the Romans invaded Thrace, and warfare continued until 46 AD", its
    # north in Moesia. Bosnia and Herzegovina and North Macedonia lay in two provinces each
    # (Dalmatia and Pannonia; Macedonia, created "in 146 BC", and Moesia Superior). Slovakia lay
    # beyond the frontier.
}

#: The Roman eras whose start is a fixed year in Rome itself: in a province they begin when that
#: province's Roman period does, if later. Rome's own Italy is in the Empire from 27 BC
#: (`Roman Republic`: "ending in 27 BC with the establishment of the Roman Empire").
_EMPIRE_START = -27
_ROMAN_EMPIRE = {"italy": _EMPIRE_START, **{c: max(_EMPIRE_START, y) for c, y in _ROMAN.items()}}
#: A province annexed after 27 BC has no Republican period: it is absent, not given a year.
_ROMAN_REPUBLIC = {c: y for c, y in _ROMAN.items() if y < _EMPIRE_START}

#: `{period key: {folded country: start year}}`. A key here is a key of `PERIODS`; `start_year`
#: reads this table for it and refuses a country it does not list. The early phase of a period
#: starts with the period. The middle and late phases of the British Neolithic and Iron Age keep
#: the years this vocabulary held before D101 (the British sequence they were written for) and are
#: refused elsewhere, where the same words name other centuries.
REGIONAL_STARTS: dict[str, dict[str, int]] = {
    "neolithic": _NEOLITHIC,
    "early neolithic": _NEOLITHIC,
    "middle neolithic": _each(_BRITAIN, PERIODS["middle neolithic"][0]),
    "late neolithic": _each(_BRITAIN, PERIODS["late neolithic"][0]),
    "chalcolithic": _CHALCOLITHIC,
    "copper age": _CHALCOLITHIC,
    "bronze age": _BRONZE_AGE,
    "early bronze age": _BRONZE_AGE,
    "middle bronze age": _MIDDLE_BRONZE_AGE,
    "late bronze age": _LATE_BRONZE_AGE,
    "iron age": _IRON_AGE,
    "early iron age": _IRON_AGE,
    "middle iron age": _each(_BRITAIN, PERIODS["middle iron age"][0]),
    "late iron age": _each(_BRITAIN, PERIODS["late iron age"][0]),
    # the Neolithic-to-Iron-Age span of British usage ("late prehistoric" -4000 to -800)
    "late prehistoric": _each(_BRITAIN, PERIODS["late prehistoric"][0]),
    "roman": _ROMAN,
    "ancient rome": _ROMAN,
    "roman empire": _ROMAN_EMPIRE,
    "roman imperial": _ROMAN_EMPIRE,
    "roman republic": _ROMAN_REPUBLIC,
}

#: Owner decision D111 (2026-11-06, the D99 pilot): the period words too coarse to date a site.
#: "Stone Age" and "Palaeolithic" span three million years and wrote the table's edge (Čertova pec,
#: confirmed at -3,000,000; Rock Carvings at Åsli, proposed at it for ice-covered Arctic Norway);
#: "prehistoric", "prehistory", "ancient history" and "classical antiquity" name no start a site
#: has. They stay names of `PERIODS` - Canmore and the span readers read their ranges - but a
#: period-word answer that names one gets no year (`start_year`); its named phases ("lower",
#: "middle", "upper palaeolithic") keep theirs. "ancient" and "antiquity" alone are no names of
#: the table at all and stay refused by name.
COARSE: frozenset[str] = frozenset(
    {"stone age", "palaeolithic", "paleolithic", "prehistoric", "prehistory", "ancient history",
     "classical antiquity"}
)  # fmt: skip

#: Owner decision D111: "Bronze Age without a sub-phase where the table needs one" gives no year.
#: The table needs one where it divides the period for the country - where it holds a middle or a
#: late Bronze Age start of its own (Britain and Ireland, Türkiye and the Levant, Greece, France,
#: Italy): there the bare word is the start of 1,400 to 2,100 years, and a site of one phase was
#: written at the first (Bant's Carn, "built = Middle Bronze Age", proposed at -2500). The Iron Age
#: is divided only for Britain, where it runs from 800 BC to the Roman conquest, and owner decision
#: D112 writes a bare British Iron Age (Moel y Gest, Wales, -800): it needs no sub-phase anywhere.
SUBPHASE_REQUIRED: dict[str, frozenset[str]] = {
    "bronze age": frozenset({*_MIDDLE_BRONZE_AGE, *_LATE_BRONZE_AGE}),
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


def country_key(country: str) -> str:
    """`country` as `REGIONAL_STARTS` keys it: the text after its last comma ("Cusco, Peru" is
    Peru, as `pipeline.normalizers.dates.country_key` reads a country), folded like a period name -
    "Türkiye" and "turkiye" are one key."""
    return fold_name(str(country).rsplit(",", 1)[-1])


def is_regional(name: str) -> bool:
    """Whether the period `name` names starts at a different year in different countries (D101), so
    that its start needs the site's country. `PeriodError` for a name the vocabulary does not know."""
    period_of(name)
    return _key_of(name) in REGIONAL_STARTS


def start_year(name: str, *, country: str | None) -> int:
    """The year a period-word answer writes: the period's own start, never an invented one.

    For a period of `REGIONAL_STARTS` (owner decision D101) that is its start in the site's
    `country`; `PeriodError` when the country is not given or the table has no start for it - a
    Neolithic site in a country without a cited Neolithic start gets no year, never Britain's. A
    period that starts at one year everywhere ("victorian", "hellenistic period") ignores
    `country`. A coarse word (`COARSE`) gives no year anywhere, and a bare Bronze Age none in a
    country whose table divides it (`SUBPHASE_REQUIRED`) - owner decision D111."""
    start = period_of(name)[0]
    key = _key_of(name)
    if key in COARSE:
        raise PeriodError(
            f"{name!r} is too coarse a period word to date a site (D111): only a named phase "
            '("Middle Palaeolithic", "Late Neolithic") or a year from a source answers'
        )
    regional = REGIONAL_STARTS.get(key) if key is not None else None
    if regional is None:
        return start
    if country is None or not country_key(country):
        raise PeriodError(
            f"{name!r} began at different times in different regions (D101): its start needs the "
            "site's country"
        )
    if country_key(country) in SUBPHASE_REQUIRED.get(key, frozenset()):
        raise PeriodError(
            f"{name!r} in {country!r} needs its sub-phase (D111): the table divides it there, so "
            "only the early, middle or late phase a source names, or a year, answers"
        )
    found = regional.get(country_key(country))
    if found is None:
        raise PeriodError(
            f"{name!r} has no cited start for {country!r} (D101): the regional table holds it for "
            f"{len(regional)} country spellings, and another region's year is never used"
        )
    return found


class EpochBand(NamedTuple):
    """The band an epoch word writes (D136): its `label` (one of `PERIOD_BUCKETS`), the `edge` year
    stored for it (`bucket_edge`), the epoch's `start` the band was read from, and whether that start
    is the country's own (`regional`) or the conventional one of `PERIODS`."""

    label: str
    edge: int
    start: int
    regional: bool


def epoch_band(name: str, *, country: str | None) -> EpochBand:
    """The period band an epoch word dates a site to (owner decision D136).

    The band is the one in which the epoch begins: for a period of `REGIONAL_STARTS` its start in
    the site's `country` where the table holds one, otherwise the conventional start of `PERIODS`
    (a Roman site in Germany, a Neolithic one in Sudan). The year written is the band's edge, never
    the start itself: a band says when, to the band, and nothing finer. The D111 refusals do not
    apply - they refuse an *exact* year (`start_year`), and a coarse word ("Stone Age",
    "prehistoric") or a bare Bronze Age is placed by its start like every other epoch.
    `PeriodError` for a word the vocabulary does not know."""
    start = period_of(name)[0]
    key = str(_key_of(name))  # `period_of` has refused a name without a key
    found = REGIONAL_STARTS.get(key, {}).get(country_key(country)) if country else None
    if found is not None:
        start = found
    label = categorize_period(start)
    assert label is not None  # a year always has a bucket
    return EpochBand(label=label, edge=bucket_edge(label), start=start, regional=found is not None)


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
