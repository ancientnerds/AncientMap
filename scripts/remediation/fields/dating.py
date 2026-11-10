"""D70: the dating extractor - a site's start, read by machine from what its sources state.

Owner decision D70 (2026-10-25): before any further model research, a deterministic extractor finds a
site's dating whenever a source states one, measured on a sealed gold set first (D71: written without
a model check at >= 95 % precision, every cell with a verbatim quote and its URL; D72: only the 615
undated sites are filled, the dated ones give a conflict list; D73: the rest stays `Undated` and goes
to the owner). The design is `output/remediation/final-2026-10-08/D70_EXTRACTOR_DESIGN.md`; the
orchestrator's decisions O1 (write the start only; the source range goes into the evidence; a start
that moves the site out of the D58 window is listed, not written) and O2 (the 105 adversarially
rejected cells enter like any other) are in `OWNER_DECISIONS_2026-10-08.md`.

**No model, no guess.** Every candidate is a statement a source prints, quoted verbatim with the
URL of the revision it was read in. The readers are the lane's own and nothing is added to them:
`dates.located` (a year, century or millennium with its era, in 25+ languages), `answers.bp_dates`
(an age before the present) and `pipeline.periods` (a named period is its conventional start).

**The tiers** (`TIERS`; the order breaks ties and a lower tier never silently overrides a higher one):

1. the English article's infobox fields (`built`, `founded`, `established`, `epochs`, `periods`,
   `cultures`), read from the wikitext at the cached revision;
2. the English article's prose: the lead and the History/Archaeology/Description/Dating sections;
3. the item's other Wikipedias (`harvest.READ_LANGS`), the same rules, the quote in its language;
4. the non-Wikipedia pages earlier answers cited (`harvest.cached_pages`), forbidden families refused;
5. Wikidata: P571/P580/P1249 (a P31 of park, museum or reserve vetoes P571), P2348 (a period item,
   through `pipeline.periods`), P793 with P585 when the event is a construction or founding;
6. Pleiades, through P1584 only: the description's prose, then `minDate` as the last resort.

Never used: a site_type rule, our own descriptions, a proximity match, a model's reasoning.

**What a prose sentence must be** (`sentence_candidates`): in a section the extractor reads; free of
a hedge ("possibly", "said to be", "resemblance", "wahrscheinlich", ...: abstained, not lowered);
**anchored** - it names the site (a Wikidata label or alias in any language, the article title, the
stored name), or a deictic ("the site", "it", "the fort", ...) stands in a paragraph that named it,
and no other proper name stands before the anchor as the sentence's subject (the sub-site trap:
"Horvat Midras dates to the 10th century BCE" in the article of the reserve around it); and a
statement is a start only when the cue nearest to it is a **start cue** (built, founded, settled,
dates to, ... and their equivalents in the readable languages), not an event cue (excavated,
destroyed, restored, mentioned, ...). A statement counts when it carries an era marker, is a century
or millennium, or is an unmarked year of three or four digits right after a date preposition; a
number with a unit after it ("263 m", "1,200 ewes") is never a year. A period word counts without a
cue unless an event cue is nearest; a prefix or a negation vetoes it ("pre-Inca", "non-Roman") and so
do the compounds that are not periods ("Roman Catholic"). Starts after 1500 AD are dropped.

**The decision** (`decide`, D70 and O1): a collective entity (a village, a reserve, a region - by
its P31 classes, or the X8 list) abstains; no candidate abstains; two different starts in one
sentence of the deciding tier abstain. Otherwise the written start is the earliest candidate of the
highest tier present, every candidate goes into the evidence, and the decision is `single` when all
candidates lie in one period bucket and `range` when they do not (the range's ends are both quoted;
only the start is written, O1). A decision that rests on a period word alone, or on Pleiades'
`minDate` alone, is emitted only when `CONFIG["solo"]` allows it - a switch that only a measured gold
can turn on (a code change, a new seal). A start that would move the site out of the D58 window
(`passes_date_cutoff`), or make it a label borderline case, is held for the owner (`scope-hold`).

    dating.py run    --run RUN --harvest ROOT [--fields-dir DIR] [--collectives FILE]
                     DECISIONS.jsonl, REASK.json (empty), EXTRACT.json, REST.jsonl, OWNER_SCOPE.jsonl
    dating.py verify --run RUN [--pace S]   each quote fetched from its permalink, serially; a
                     decisive quote not found makes its decision unresolved; VERIFIED.json pins it
    dating.py show   --run RUN --n 30 --seed S     OWNER_SHOW.md and OWNER_SHOW.json (D71/O3)
    dating.py shown  --run RUN --checks FILE --by TEXT   OWNER_SHOWN.json from the three checks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import answers as A  # noqa: E402
from fields import dates as D  # noqa: E402
from fields import rule as R  # noqa: E402
from pipeline import periods as P  # noqa: E402
from pipeline.normalizers.dates import label_borderline, passes_date_cutoff  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

# ------------------------------------------------------------------------------ the configuration
#: The extractor's switches. Part of the code: its sha256 is pinned beside the modules' by the gold
#: seal (`dating_gold.py freeze`), so a switch turned on after a measurement needs a new gold round.
CONFIG: Mapping[str, Any] = {
    "version": 2,
    #: the latest start the extractor writes (the scope rule: nothing after 1500 AD is a start)
    "year_cap": 1500,
    #: the tiers that yield candidates; a tier the gold measures below 0.95 is taken out here.
    #: DEV round 1 (2026-11-06, gold round-01's DEV: 300 dev + 412 dev-hard sites): tier 3 decided
    #: 11 of 15 in the gold's bucket, tier 4 20 of 28, tier 5 6 of 9, tier 6 1 of 3 - taken out
    #: (a disabled tier is not read at all); tier 1 23 of 27 and tier 2 206 of 232 stay, the best
    #: the extractor has, and the sealed gold judges them
    "tiers": [1, 2],
    #: whether a decision may rest on this kind alone (design section 5): a period word, Pleiades'
    #: minDate. Pleiades' minDate is attestation, not a dated statement: off until a gold passes it.
    "solo": {"period": True, "pleiades": False},
    #: whether a decision whose candidates lie in two or more buckets (a `range`, O1) is written:
    #: off - on DEV round 1 (2026-11-06) the earliest start of a range was in the gold's bucket in
    #: 24 of 40 decisions (0.60); a range goes to the rest list with its candidates (D73)
    "write_ranges": False,
}
TIERS = {
    1: "enwiki infobox",
    2: "enwiki prose",
    3: "other-language Wikipedia prose",
    4: "cited non-Wikipedia page",
    5: "Wikidata",
    6: "Pleiades",
}
YEAR, CENTURY, MILLENNIUM, BP, PERIOD = "year", "century", "millennium", "bp", "period"
WIKIDATA, PLEIADES = "wikidata", "pleiades"
#: The modules whose behaviour is the extractor: pinned by the gold seal with `CONFIG`.
CODE_FILES = (
    "scripts/remediation/fields/dating.py",
    "scripts/remediation/fields/dates.py",
    "scripts/remediation/fields/answers.py",
    "pipeline/periods.py",
)

SINGLE, RANGE, ABSTAIN, SCOPE_HOLD = "single", "range", "abstain", "scope-hold"
# why a site abstains (REST.jsonl, the D73 list)
NO_SOURCE, NO_CANDIDATE, HEDGED_ONLY = "no-source", "no-candidate", "hedged-only"
COLLECTIVE, TWO_STARTS, SOLO_REFUSED = "collective-entity", "two-starts-in-one-sentence", "solo-kind"
# why a statement is seen and not taken (a note, not an abstention)
SEVERAL_PERIODS, BUCKET_EDGE = "several-periods", "bucket-edge"
SOURCES_DISAGREE = "sources-disagree"
DECISIONS_FILE, REASK_FILE, EXTRACT_FILE = "DECISIONS.jsonl", "REASK.json", "EXTRACT.json"
REST_FILE, SCOPE_FILE = "REST.jsonl", "OWNER_SCOPE.jsonl"
VERIFIED_FILE, SHOW_MD, SHOW_JSON, SHOWN_FILE = (
    "VERIFIED.json",
    "OWNER_SHOW.md",
    "OWNER_SHOW.json",
    "OWNER_SHOWN.json",
)
UNVERIFIED = "unverified"
#: O3: at most this many of the shown cells may be wrong for the wave to go.
SHOWN_MAX_WRONG = 1
SHOWN_CELLS = 30


class DatingError(ValueError):
    """The extractor's inputs are not what it needs: it stops and says which."""


def code_hashes(repo: Path = REPO) -> dict[str, str]:
    """sha256 of each module of `CODE_FILES` (LF text) and of `CONFIG`: what the gold seal pins."""
    out = {
        name: hashlib.sha256((repo / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in CODE_FILES
    }
    out["CONFIG"] = hashlib.sha256(
        json.dumps(CONFIG, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return out


def code_stamp(hashes: Mapping[str, str]) -> str:
    """The twelve characters `answered_by` names the extractor's version with."""
    joined = "".join(f"{k}={hashes[k]}" for k in sorted(hashes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------------------ the vocabulary
def fold(text: str) -> str:
    """Lower case, accents removed - the form every cue, hedge and name is compared in."""
    return D.plain_text(text).casefold()


def _words_re(words: Iterable[str]) -> re.Pattern[str]:
    """A word-bounded, case-folded alternation; a trailing `*` makes a word a prefix."""
    parts = []
    for word in sorted(set(words), key=len, reverse=True):
        stem = word.rstrip("*")
        body = r"[\W_]+".join(re.escape(w) for w in stem.split())
        parts.append(body + (r"\w*" if word.endswith("*") else ""))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)")


#: A start: the site was made, founded, first lived in, or dates from. Folded forms, `*` a prefix.
START_CUES = _words_re(
    [
        # English
        "built", "build", "constructed", "construction of", "erected", "founded", "foundation of",
        "established", "settled", "settlement began", "occupied", "occupation", "inhabited",
        "habitation", "dates", "dated", "dating", "date from", "date to", "date back",
        "carved", "painted", "first phase", "earliest phase", "originated", "origins",
        "goes back", "go back", "began", "begun", "raised", "laid out", "created", "made",
        # German
        "gegrundet", "erbaut", "errichtet", "entstand*", "besiedelt", "besiedlung", "datiert",
        "stammt", "stammen", "angelegt", "gebaut", "geht zuruck", "reicht zuruck",
        # French
        "fonde*", "construit*", "bati*", "edifie*", "erige*", "date*", "remonte*", "occupe*",
        "habite*", "amenage*",
        # Spanish, Portuguese, Catalan
        "fundad*", "construid*", "construi*", "edificad*", "erigid*", "datad*", "data de",
        "datan de", "se remonta*", "remonta*", "habitad*", "ocupad*", "ocupacion", "construccion",
        "fundacion", "fundat*", "construit*",
        # Italian
        "fondat*", "costruit*", "edificat*", "eretto", "eretta", "risale", "risalgono", "datat*",
        "abitat*",
        # Dutch, Scandinavian, Finnish
        "gesticht", "gebouwd", "opgericht", "dateert", "bewoond", "grundad", "byggd", "daterad",
        "grundlagt", "bygget", "dateret", "grunnlagt", "bygd", "datert", "perustettiin",
        "rakennettiin", "ajoitettu",
        # Polish, Czech, Slovak, Slovene, Croatian/Serbian
        "zalozon*", "zbudowan*", "wzniesion*", "datowan*", "pochodzi", "pochodza",
        "zamieszkan*", "zalozen*", "postaven*", "vybudovan*", "datovan*", "pochazi", "osidlen*",
        "osnovan*", "sagraden*", "izgraden*", "datira*", "potjece", "potjecu", "naselj*",
        # Russian, Ukrainian, Bulgarian, Macedonian
        "основан*", "построен*", "возведен*", "датирует*", "датирован*", "относит*", "восходит",
        "заснован*", "побудован*", "датует*", "изграден*", "датира*",
        # Hungarian, Greek, Turkish, Romanian, Indonesian
        "alapit*", "epult", "epitett*", "datal*", "laktak", "lakott", "ιδρυθηκε", "χτιστηκε",
        "κατασκευαστηκε", "χρονολογειται", "kuruldu", "insa", "yapildi", "tarihlen*", "datat*",
        "didirikan", "dibangun",
    ]
)  # fmt: skip
#: Something happened to the site that is not its start: the date belongs to the event.
EVENT_CUES = _words_re(
    [
        "excavated", "excavation*", "refounded", "re founded", "refoundation", "discovered", "discovery", "found", "unearthed", "destroyed",
        "destruction", "sacked", "abandoned", "abandonment", "restored", "restoration", "rebuilt",
        "reconstructed", "renovated", "listed", "declared", "designated", "scheduled", "museum",
        "opened", "mentioned", "attested", "recorded", "visited", "described", "surveyed",
        "conquered", "captured", "burned", "burnt", "damaged", "acquired", "purchased", "died",
        "reign*", "ruled",
        # DEV round 1 (2026-11-06): a capture, a siege, a heyday - the date is the event's
        "taken", "besieged", "siege", "battle", "invaded", "peak", "flourished", "heyday",
        "zenith", "apogee", "invasion",
        "ausgegraben", "entdeckt", "zerstort", "verlassen", "restauriert", "erwahnt",
        "fouille*", "decouvert*", "detruit*", "abandonne*", "restaure*", "mentionne*",
        "excavad*", "descubiert*", "destruid*", "abandonad*", "restaurad*", "mencionad*",
        "scavat*", "scopert*", "distrutt*", "abbandonat*", "restaurat*", "menzionat*",
        "otkriven*", "unisten*", "razoren*", "obnovljen*", "spominje*", "odkryt*", "zniszczon*",
        "раскопан*", "обнаружен*", "разрушен*", "восстановлен*", "упоминает*",
    ]
)  # fmt: skip
#: A statement the source itself is not sure of: abstained, never lowered.
HEDGES = _words_re(
    [
        "possibly", "perhaps", "maybe", "may", "might", "could", "believed", "thought to",
        "thought that", "supposed", "supposedly", "allegedly", "reputedly", "said to",
        "resemblance", "resembles", "resembling", "presumably", "probably", "likely", "unclear",
        "uncertain", "unknown", "legend", "legendary", "traditionally", "tradition holds",
        "speculated", "conjectured", "suggested", "suggests", "perhaps",
        "possible", "suggest", "suggesting", "apparently", "appears to", "appear to", "seems",
        "seem to", "would have",
        "wahrscheinlich", "vermutlich", "moglicherweise", "vielleicht", "soll", "sollen", "angeblich",
        "peut etre", "probablement", "sans doute", "suppose*", "aurait", "auraient", "legende",
        "posiblemente", "probablemente", "quizas", "quiza", "se cree", "supuestamente", "leyenda",
        "forse", "probabilmente", "si ritiene", "presumibilmente", "leggenda",
        "possivelmente", "provavelmente", "talvez", "lenda",
        "mogelijk", "waarschijnlijk", "vermoedelijk",
        "prawdopodobnie", "byc moze", "przypuszczalnie", "vjerojatno", "mozda", "moguce",
        "pravdepodobne", "mozna", "mozno", "verjetno",
        "возможно", "вероятно", "предположительно", "можливо", "ймовірно",
    ]
)  # fmt: skip
#: A word that, standing before the number, makes an unmarked three- or four-digit number a year.
DATE_PREPOSITIONS = frozenset(
    {"in", "around", "about", "c", "ca", "circa", "by", "from", "since", "until", "before",
     "after", "year", "im", "um", "seit", "ab", "jahr", "jahre", "en", "vers", "depuis", "hacia",
     "desde", "nel", "dal", "intorno", "em", "por", "w", "roku", "od", "u", "godine", "в", "году",
     "с", "evvel", "ok", "kb", "ano", "anno", "annee"}
)  # fmt: skip
#: Units: a number with one of these after it is a measure, not a year.
UNITS = frozenset(
    {"m", "km", "cm", "mm", "ft", "feet", "foot", "ha", "hectare", "hectares", "acre", "acres",
     "metre", "metres", "meter", "meters", "mile", "miles", "kg", "t", "tonne", "tonnes", "ton",
     "tons", "people", "inhabitants", "residents", "persons", "ewes", "sheep", "cattle",
     "stadia", "stades", "steps", "stones", "graves", "tombs", "rooms", "houses", "sq", "square",
     "yards", "yd", "m2", "km2", "masl", "asl", "einwohner", "metros", "metri", "habitants", "habitantes", "abitanti", "mieszkancow", "stanovnika", "жителей", "м", "км"}
)  # fmt: skip
def _flexible(words: str) -> str:
    """A folded phrase as a pattern over the reading text: any run of non-letters between words."""
    return r"(?<!\w)" + r"[\W_]+".join(re.escape(w) for w in words.split()) + r"(?!\w)"


#: Words before a period word that make it no period of the site ("pre-Inca", "non-Roman", "not
#: Roman"), read in the case-folded reading text up to the name.
PERIOD_PREFIXES = re.compile(
    r"(?:(?<!\w)(?:pre|post|non|sub|proto|neo|anti|vor|nach)[\W_]*|"
    r"(?<!\w)(?:not|no|never|nicht|kein|keine|pas)\s+(?:an?\s+|the\s+)?)\Z"
)
#: The compounds that are not periods: a period word inside them dates nothing.
PERIOD_COMPOUNDS = re.compile(
    "|".join(
        _flexible(c)
        for c in (
            "roman catholic", "holy roman", "roman numeral", "roman numerals", "greek orthodox",
            "byzantine rite", "classical music", "classic example", "neo classical",
            "victorian era", "georgian era", "romanesque",
            # DEV round 1 (2026-11-06): an administration or an event, not the site's start
            "roman province", "roman invasion", "roman conquest",
        )
    )
)  # fmt: skip
#: What a period word right before it dates instead of the site: a find ("Roman coins", "Iron Age
#: pottery", "Bronze Age axes"). Matched at the end of the period's name in the reading text.
FINDS = re.compile(
    r"[\W_]+(?:\w+[\W_]+)?(?:coins?|pottery|potsherds?|sherds?|finds?|artefacts?|artifacts?|"
    r"objects?|burials?|graves?|hoards?|tools?|axes?|inscriptions?|statues?|remains|material|"
    r"ceramics?|vessels?|weapons?|jewel(?:le)?ry|brooch(?:es)?|fibulae?|bronzes|figurines?)(?!\w)"
)
#: Names in the vocabulary too broad to place a site in one period bucket.
BROAD_PERIODS = frozenset(
    {"prehistoric", "prehistory", "late prehistoric", "ancient history", "historic",
     "classical antiquity", "stone age", "middle ages", "classical", "classic", "ancient greece",
     "ancient rome", "guanches", "maya civilization", "woodland", "medieval", "early medieval",
     "early modern", "post medieval", "georgian", "victorian", "edwardian", "pleistocene"}
)  # fmt: skip

#: The subject a deictic stands for, when a paragraph named the site: folded, whole phrases.
DEICTICS = _words_re(
    [
        "it", "its", "the site", "this site", "the settlement", "the fort", "the fortress",
        "the hillfort", "the temple", "the tomb", "the cave", "the city", "the town",
        "the monument", "the complex", "the structure", "the building", "the sanctuary",
        "the palace", "the villa", "the mound", "the tumulus", "the dolmen", "the menhir",
        "the circle", "the henge", "the barrow", "the cairn", "the shrine", "the pyramid",
        "the citadel", "the acropolis", "the enclosure", "the camp", "the colony", "the oppidum",
        "the necropolis", "the cemetery", "the ruins", "the stones", "the stone", "the walls",
        "the castro", "the broch", "the nuraghe", "the stupa", "the theatre", "the theater",
        "the amphitheatre", "the aqueduct", "the bridge", "the church", "the monastery",
        # German, French, Spanish, Italian, Portuguese, Croatian/Serbian
        "die anlage", "die siedlung", "der ort", "die stadt", "der tempel", "die burg",
        "das grab", "die hohle", "der fundplatz", "le site", "la ville", "le temple", "la cite",
        "le village", "l oppidum", "el sitio", "la ciudad", "el templo", "el asentamiento",
        "el yacimiento", "la zona arqueologica", "il sito", "la citta", "il tempio",
        "l insediamento", "o sitio", "a cidade", "o templo", "njegov*", "njezin*", "grad",
        "naselje",
    ]
)  # fmt: skip
#: Capitalised words that stand before a site's name without being another subject.
_SUBJECT_EXEMPT = frozenset(
    {"in", "the", "a", "an", "during", "by", "after", "before", "its", "it", "from", "since",
     "around", "about", "at", "on", "according", "between", "under", "while", "when", "although",
     "this", "these", "those", "there", "here", "today", "now", "until", "some", "many", "most",
     "both", "of", "and", "or", "as", "with", "early", "late", "middle", "first", "second",
     "third", "old", "new", "great", "upper", "lower", "north", "south", "east", "west",
     "northern", "southern", "eastern", "western", "central", "century", "centuries",
     "millennium", "age", "period", "era", "empire", "kingdom", "dynasty", "culture",
     "civilization", "civilisation", "bc", "bce", "ad", "ce", "b", "c", "e", "d", "cal",
     "january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december", "romans", "greeks", "etruscans", "phoenicians", "celts",
     "incas", "mayas", "egyptians", "persians", "carthaginians", "iberians", "illyrians",
     "thracians", "dacians", "scythians", "hittites", "assyrians", "babylonians", "sumerians",
     "nabataeans", "parthians", "bronze", "iron", "stone", "copper", "neolithic", "paleolithic",
     "palaeolithic", "mesolithic", "chalcolithic", "roman", "greek", "celtic", "inca", "maya",
     "aztec", "olmec", "pre", "post", "unesco", "world", "heritage"}
)  # fmt: skip
#: Languages whose capitals mark proper names only: the subject veto reads them (German
#: capitalises every noun, so a capital there says nothing about a subject).
SUBJECT_VETO_LANGS = frozenset(
    {"en", "fr", "es", "it", "pt", "nl", "ca", "ro", "pl", "cs", "sk", "sl", "hr", "sr", "sh",
     "bs", "hu", "sv", "da", "no", "fi", "id", "tr"}
)  # fmt: skip

# ------------------------------------------------------------------------------ the sections
#: A section the extractor reads (its folded heading contains one of these); the lead is always read.
READ_SECTIONS = (
    "histor", "geschicht", "archaeolog", "archeolog", "archäolog", "arqueolog", "arheolog",
    "arkeolog", "regeszet", "descri", "beschreib", "beschrijv", "opis", "popis", "datier",
    "datation", "datacion", "datazione", "dating", "datowan", "datiran", "chronolog",
    "construction", "origin", "foundation", "sejarah", "storia", "dejiny", "povijest",
    "tortenet", "tarih", "istori", "ιστορ", "αρχαιολ", "истор", "істор", "археол", "описан",
    "датиров", "periods", "prehistor", "antiquity", "antiquite", "antiguedad", "antichita",
    "the site", "site",
)  # fmt: skip
_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")


def readable_paragraphs(text: str) -> list[tuple[str, bool, str]]:
    """The paragraphs of an article's plain text (`== Heading ==` lines between them) that the
    extractor reads, as `(section, is_lead, paragraph)`: the lead and the sections `READ_SECTIONS`
    names - a subsection inherits its section's reading unless its own heading names one."""
    out: list[tuple[str, bool, str]] = []
    stack: list[tuple[int, str, bool]] = []
    section, reading, lead = "", True, True
    for line in text.splitlines():
        heading = _HEADING.match(line.strip())
        if heading:
            level, name = len(heading.group(1)), heading.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            own = any(word in fold(name) for word in READ_SECTIONS)
            inherited = stack[-1][2] if stack else False
            reading = own or inherited
            stack.append((level, name, reading))
            section, lead = name, False
            continue
        if line.strip() and reading:
            out.append((section, lead, line.strip()))
    return out


# ------------------------------------------------------------------------------ the sentences
#: Tokens whose full stop never ends a sentence: titles, "c.", the era abbreviations' first parts.
_NO_STOP = frozenset(
    {"r", "c", "ca", "fl", "b", "d", "st", "mt", "ft", "dr", "mr", "mrs", "ms", "no", "nos",
     "vol", "vols", "fig", "figs", "approx", "cf", "eg", "ie", "etc", "vs", "jh", "jhd", "jhdt",
     "v", "n", "pr", "av", "ap", "a", "j", "p", "gen", "lit", "s", "ss",
     "sec", "sv", "bzw", "vgl", "ok", "tzw", "np", "itd", "tj", "tzn", "op", "ed", "eds",
     "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "km",
     "pl", "ul", "ff", "ibid", "inc", "co", "ltd", "jr", "sr", "nr", "hl", "sta", "sto",
     "gr", "lat", "engl", "dt", "frz", "ital", "span", "u", "z", "e", "w", "m", "t",
     "g", "г", "гг", "в", "вв", "н", "э", "е", "до", "пр", "хр", "ст", "м", "т", "i"}
)  # fmt: skip
_ERA_END = re.compile(r"(?<!\w)(?:B\.\s?C(?:\.\s?E)?|A\.\s?D|C\.\s?E)\Z")
_STOP = re.compile(r"[.!?…](?:[\"'”’)\]]*)\s+(?=[\"'“‘(\[]?[A-ZÀ-ÞĀ-ſΑ-ΩА-Я0-9])")


def split_sentences(paragraph: str) -> list[str]:
    """The sentences of a paragraph, abbreviation-aware: no stop after `_NO_STOP` tokens ("(r.
    486-465 BC).", "pr. Kr.", "v. Chr.") or after a number of one or two digits (the German and
    Croatian ordinal "5. Jahrhundert", "4. stoljeća"); a stop needs a capital or a digit after it."""
    out, begin = [], 0
    for match in _STOP.finditer(paragraph):
        head = paragraph[begin : match.start()]
        last = re.search(r"([^\W_]+)\W*\Z", head)
        token = last.group(1) if last else ""
        era_end = _ERA_END.search(head) is not None  # "300 B.C. The city": the stop of a marker
        if paragraph[match.start()] == "." and not era_end and (
            fold(token) in _NO_STOP or (token.isdigit() and len(token) <= 2)
        ):
            continue
        out.append(paragraph[begin : match.start() + 1].strip())
        begin = match.end()
    tail = paragraph[begin:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


# ------------------------------------------------------------------------------ the candidates
@dataclass(frozen=True)
class Candidate:
    """A start a source states: `start` is the year written (the wd5 convention: the low end of what
    the statement covers, 8th century BC -> -800), `lo`..`hi` what the statement covers."""

    start: int
    lo: int
    hi: int
    kind: str
    tier: int
    source: str
    url: str
    quote: str
    revision: Any
    cue: str
    detail: str
    sentence: str = ""  #: an id of the sentence it came from (two starts in one sentence)

    @property
    def bucket(self) -> str:
        return str(categorize_period(self.start))


@dataclass(frozen=True)
class Note:
    """A statement the extractor saw and did not take, and why (it goes into the evidence)."""

    tier: int
    url: str
    quote: str
    reason: str


@dataclass
class Found:
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)

    def extend(self, other: Found) -> None:
        self.candidates.extend(other.candidates)
        self.notes.extend(other.notes)


def name_forms(names: Iterable[str | None]) -> list[str]:
    """The folded names a sentence may name the site by: each name, its parenthesised
    disambiguation dropped, at least four characters."""
    out = set()
    for name in names:
        if not name:
            continue
        for variant in (name, re.sub(r"\s*\(.*?\)\s*", " ", name)):
            folded = " ".join(re.sub(r"[^\w]+", " ", fold(variant)).split())
            if len(folded) >= 4:
                out.add(folded)
    return sorted(out, key=len, reverse=True)


def _folded_words(text: str) -> str:
    return " " + " ".join(re.sub(r"[^\w]+", " ", fold(text)).split()) + " "


def names_site(sentence: str, forms: Sequence[str]) -> bool:
    words = _folded_words(sentence)
    return any(f" {form} " in words for form in forms)


#: "the city of Rhodes": a deictic followed by a named thing is that thing, not the site.
_NAMED_AFTER = re.compile(r"\s+(?:of|de|del|della|di|du|des|von|van)\s+(?:the\s+|la\s+|le\s+)?[A-ZÀ-Þ]")


def deictic_match(norm: str) -> re.Match[str] | None:
    """The first deictic of the reading text `norm` that stands for the site: one followed by "of"
    and a capitalised name ("the city of Rhodes") names that other place (DEV round 1, 2026-11-06:
    Lindus's "when the city of Rhodes was built")."""
    low = norm.casefold()
    for match in DEICTICS.finditer(low):
        if _NAMED_AFTER.match(norm, match.end()):
            continue
        return match
    return None


def _anchor_offset(norm: str, forms: Sequence[str]) -> int | None:
    """Where in the reading text the sentence first names the site or a deictic stands."""
    low = norm.casefold()
    best: int | None = None
    for form in forms:
        pattern = r"(?<!\w)" + r"[\W_]+".join(re.escape(w) for w in form.split()) + r"(?!\w)"
        found = re.search(pattern, low)
        if found and (best is None or found.start() < best):
            best = found.start()
    deictic = deictic_match(norm)
    if deictic and (best is None or deictic.start() < best):
        best = deictic.start()
    return best


def other_subject(
    norm: str, forms: Sequence[str], anchor: int | None, *, sentence_start: bool = True
) -> str | None:
    """A capitalised proper name standing before the anchor that is not the site: the sentence is
    about something else (a sub-site, a neighbour) - or None. `sentence_start`: `norm` begins a
    sentence (its first word is capitalised anyway)."""
    head = norm if anchor is None else norm[:anchor]
    name_words = {w for form in forms for w in form.split()}
    for index, match in enumerate(re.finditer(r"[^\W\d_]+", head)):
        word = match.group(0)
        if not word[0].isupper() or len(word) < 3 or word.isupper():
            continue
        low = word.casefold()
        if index == 0 and sentence_start and not re.match(r"[^\W\d_]+\s+[A-Z]", head):
            continue  # a sentence's first word is capitalised anyway: a name only before a capital
        if low in _SUBJECT_EXEMPT or low in name_words or low.rstrip("s") in name_words:
            continue
        if any(low == w or low.rstrip("s") == w for key in P.PERIODS for w in key.split()):
            continue
        if low in D.ROMAN or word in D.ROMAN:
            continue
        return word
    return None


def _anchors(norm: str, forms: Sequence[str]) -> list[int]:
    """Every offset of the reading text where the site is named or a deictic stands for it."""
    low = norm.casefold()
    out = []
    for form in forms:
        pattern = r"(?<!\w)" + r"[\W_]+".join(re.escape(w) for w in form.split()) + r"(?!\w)"
        out += [m.start() for m in re.finditer(pattern, low)]
    out += [m.start() for m in DEICTICS.finditer(low) if not _NAMED_AFTER.match(norm, m.end())]
    return sorted(out)


def cue_owner(norm: str, forms: Sequence[str], cue: int) -> str | None:
    """The other proper name a start cue belongs to, or None. The cue's clause - reaching back over
    a relative pronoun to the noun it refers to - names a capitalised name that is not the site,
    and neither that stretch nor the rest of the cue's clause names the site ("Previous to 408 BCE,
    when the city of Rhodes was built, Lindus ...", "... de la ciudad de Rodas, que fue fundada en
    el 408 a. C.": the founding is Rhodes's - DEV round 1, 2026-11-06). A name after "by" is the
    builder, not the thing built ("built by Augustus")."""
    low = norm.casefold()
    bounds = [m.end() for m in _CLAUSE.finditer(low[:cue])]
    begin = bounds[-1] if bounds else 0
    if _RELATIVE.match(low, begin) and len(bounds) > 1:
        begin = bounds[-2]
    elif _RELATIVE.match(low, begin):
        begin = 0
    tail = _CLAUSE.search(low, cue + 1)
    end = tail.start() if tail else len(norm)
    anchors = _anchors(norm, forms)
    if any(cue <= a < end for a in anchors):
        return None
    before = [a for a in anchors if begin <= a < cue]
    if before:  # the name search starts after the site's last naming before the cue
        named = re.match(r"[^\W\d_]+", norm[before[-1] :])
        begin = before[-1] + (named.end() if named else 0)
    segment = _AGENT.sub(lambda m: " " * len(m.group(0)), norm[begin:cue])
    return other_subject(segment, forms, None, sentence_start=begin == 0)


#: A relative pronoun opening a clause: the clause is about the noun before it.
_RELATIVE = re.compile(
    r"[\W_]*(?:que|which|who|whose|that|where|qui|dont|ou|che|cui|dove|donde|die|der|das|"
    r"welche\w*|wo|ktor\w*|kde|koji\w*|ktery\w*)(?!\w)"
)
#: The agent of a passive ("built by Augustus", "fondee par ...", "erbaut von ..."): a builder.
_AGENT = re.compile(r"(?<!\w)(?:by|par|por|von|da|door|przez|od)\s+(?:[A-Z][\w'’-]*\s*)+")


#: What separates two clauses: a cue beyond one governs another statement ("settled in the 4th
#: century BC and refounded in AD 35").
_CLAUSE = re.compile(r"[,;:()]|(?<!\w)(?:and|but|while|whereas|und|aber|et|mais|y|pero|e|ma|i|a)(?!\w)")


def _nearest_cue(low: str, start: int, end: int) -> tuple[str, str, int] | None:
    """The cue that governs the span `start`..`end` of the folded reading text, as `(kind, word,
    offset)`:
    the nearest cue of the same clause (one before the span wins a tie), else the nearest at all."""
    best: tuple[tuple[bool, int, bool], str, str, int] | None = None
    for kind, pattern in (("start", START_CUES), ("event", EVENT_CUES)):
        for match in pattern.finditer(low):
            if match.end() <= start:
                between, after = low[match.end() : start], False
            elif match.start() >= end:
                between, after = low[end : match.start()], True
            else:
                between, after = "", False
            score = (_CLAUSE.search(between) is not None, len(between), after)
            if best is None or score < best[0]:
                best = (score, kind, match.group(0), match.start())
    return None if best is None else (best[1], best[2], best[3])


def _word_before(low: str, offset: int) -> str:
    found = re.search(r"([^\W_]+)[\W_]*\Z", low[:offset])
    return found.group(1) if found else ""


def _word_after(low: str, offset: int) -> str:
    found = re.match(r"[\s ]*([^\W\d_]+\d?)", low[offset:])
    return found.group(1) if found else ""


#: The word after an unmarked number that makes it a count: an English plural noun.
_COUNTED = re.compile(r"(?!(?:this|thus|does|goes|whereas|perhaps)\Z)[a-z]{2,}[^s\W]s")


def acceptable(located: D.Located, low: str, *, date_field: bool = False) -> str | None:
    """Why a located statement is no date the extractor reads, or None when it is one: a unit after
    it, or an unmarked year that is not three or four digits after a date preposition (or in a
    date field of an infobox)."""
    s = located.statement
    if _word_after(low, located.end) in UNITS:
        return "unit"
    if s.era is not None or s.kind in (D.CENTURY, D.MILLENNIUM):
        return None
    if not 100 <= s.number <= 9999:
        return "unmarked-number"
    if _COUNTED.fullmatch(_word_after(low, located.end)):
        # "about 100 images", "around 300 houses": a count of things (DEV round 1, 2026-11-06)
        return "count"
    if date_field or _word_before(low, located.start) in DATE_PREPOSITIONS:
        return None
    return "unmarked-number"


def _range_groups(items: list[tuple[D.Located, str]], low: str) -> list[list[D.Located]]:
    """The located statements of a sentence, those of one range together: sharing a span ("3000 to
    2500 BC" is two statements of one span), or joined by only a range word or a dash."""
    groups: list[list[D.Located]] = []
    for located, _ in sorted(items, key=lambda i: i[0].start):
        if groups:
            last = groups[-1][-1]
            between = low[last.end : located.start]
            if located.start < last.end or re.fullmatch(
                r"[\s ]*(?:[-‐-―]|to|until|till|and|bis|au|a|al|hasta|ate|do|по|до)?"
                r"[\s ]*(?:the|c\.?|ca\.?|circa)?[\s ]*",
                between,
            ):
                groups[-1].append(located)
                continue
        groups.append([located])
    return groups


def sentence_candidates(
    sentence: str,
    *,
    lang: str,
    forms: Sequence[str],
    context_named: bool,
    tier: int,
    source: str,
    url: str,
    revision: Any,
    sentence_id: str,
    anchored_doc: bool = False,
    year_cap: int | None = None,
) -> Found:
    """The start candidates one sentence yields (module docstring), with a note for each it saw and
    did not take."""
    cap = CONFIG["year_cap"] if year_cap is None else year_cap
    found = Found()
    norm = D.reading_text(sentence)
    low = norm.casefold()
    located = D.located(sentence)
    bps = [(y, t) for y, t in A.bp_dates(sentence)]
    # the period vocabulary is English: read in another language it matches words that are no
    # periods (Turkish "Han ilcesi", Catalan "s'han", Finnish "silla") - DEV round 1, 2026-11-06
    periods = _period_mentions(sentence, forms) if lang == "en" else []
    if not located and not bps and not periods:
        return found
    if HEDGES.search(low):
        found.notes.append(Note(tier, url, sentence, "hedged"))
        return found
    named = names_site(sentence, forms)
    anchor = _anchor_offset(norm, forms)
    deictic = deictic_match(norm) is not None
    if not (named or anchored_doc or (context_named and deictic)):
        found.notes.append(Note(tier, url, sentence, "no-anchor"))
        return found
    if lang in SUBJECT_VETO_LANGS and not anchored_doc:
        other = other_subject(norm, forms, anchor)
        if other is not None:
            found.notes.append(Note(tier, url, sentence, f"other-subject: {other}"))
            return found
    taken: list[tuple[D.Located, str]] = []
    for item in located:
        why = acceptable(item, low)
        if why is not None:
            continue
        cue = _nearest_cue(low, item.start, item.end)
        if cue is None or cue[0] != "start":
            continue
        if lang in SUBJECT_VETO_LANGS and not anchored_doc:
            owner = cue_owner(norm, forms, cue[2])
            if owner is not None:
                found.notes.append(Note(tier, url, sentence, f"cue-of-other: {owner}"))
                continue
        taken.append((item, cue[1]))
    cues = {id(item): cue for item, cue in taken}
    out: list[Candidate] = []
    for group in _range_groups(taken, low):
        lo = min(g.statement.lo for g in group)
        hi = max(g.statement.hi for g in group)
        if lo > cap:
            continue
        first = group[0].statement
        out.append(
            Candidate(lo, lo, hi, first.kind, tier, source, url, sentence, revision,
                      cues[id(group[0])], f"{first.kind} {first.number} {first.era or 'no marker'}"
                      f" ({lo} to {hi})", sentence_id)  # fmt: skip
        )
    start_cue = START_CUES.search(low)
    if bps and start_cue is not None and EVENT_CUES.search(low) is None:
        for year, tolerance in bps:
            if year <= cap:
                out.append(
                    Candidate(year, year - tolerance, year + tolerance, BP, tier, source, url,
                              sentence, revision, start_cue.group(0),
                              f"bp {1950 - year} years before present", sentence_id)  # fmt: skip
                )
    named_periods = [k for k, offset, end in periods if not FINDS.match(low, end)]
    if len({categorize_period(P.PERIODS[k][0]) for k in named_periods}) > 1:
        # "a Bronze Age and Iron Age hillfort", "used in the Hellenistic, Roman and Byzantine
        # periods": a list of periods is a history, not a start (DEV round 1, 2026-11-06)
        found.notes.append(Note(tier, url, sentence, SEVERAL_PERIODS))
        periods = []
    seen: set[str] = set()
    for key, offset, end in periods:
        if key in seen or FINDS.match(low, end):
            continue  # "Roman coins were found": the period of a find, not of the site
        seen.add(key)
        cue = _nearest_cue(low, offset, end)
        if cue is not None and cue[0] == "event":
            # "at its peak in the Late Classic", "the Roman invasion": the period of an event
            found.notes.append(Note(tier, url, sentence, f"event-cue: {cue[1]}"))
            continue
        lo, hi = P.PERIODS[key]
        if lo > cap:
            continue
        out.append(
            Candidate(lo, lo, hi, PERIOD, tier, source, url, sentence, revision,
                      cue[1] if cue else "", f"period {key!r} ({lo} to {hi})",
                      sentence_id)  # fmt: skip
        )
    dated = [c for c in out if c.kind != PERIOD]
    if len({c.bucket for c in dated}) > 1:
        found.notes.append(Note(tier, url, sentence, TWO_STARTS))
        return found
    if dated:  # a stated year says more than a period word in the same sentence
        out = dated
    found.candidates.extend(out)
    return found


#: A name the sentence gives ("commonly known as the Inca Gallows", "called Roman Camp"): a period
#: word inside it names the thing, not its period (DEV round 1, 2026-11-06: Pachat'aqa).
_GIVEN_NAME = re.compile(
    r"(?:known as|called|named|nicknamed)\s+(?:the\s+)?((?:[A-Z][\w'’-]*\s*)+)"
)


def _period_mentions(sentence: str, forms: Sequence[str] = ()) -> list[tuple[str, int, int]]:
    """The periods `sentence` names as the site's (`pipeline.periods.states_period`), each with its
    span in the case-folded reading text (`dates.reading_text`, where the cues are found): none
    inside a non-period compound ("Roman Catholic"), after a prefix or a negation ("pre-Inca", "not
    Roman"), or too broad to bucket (`BROAD_PERIODS`). A name inside a longer one ("iron age" in
    "early iron age") counts once, as the longer. A period word inside the site's own name (`forms`:
    "Inca" of "Inca Uyo") names the site, not its period."""
    low = D.reading_text(sentence).casefold()
    compounds = [m.span() for m in PERIOD_COMPOUNDS.finditer(low)]
    compounds += [m.span() for form in forms for m in re.finditer(_flexible(form), low)]
    compounds += [m.span(1) for m in _GIVEN_NAME.finditer(D.reading_text(sentence))]
    hits: list[tuple[str, int, int]] = []
    for key in P.PERIODS:
        if key in BROAD_PERIODS or not P.states_period(sentence, key):
            continue
        for form in {key, key.removesuffix(" period").strip()}:
            for match in re.finditer(_flexible(form), low):
                a, b = match.span()
                if any(x <= a < y for x, y in compounds) or PERIOD_PREFIXES.search(low[:a]):
                    continue
                hits.append((key, a, b))
    out: set[tuple[str, int, int]] = set()
    covered: list[tuple[int, int]] = []
    for key, a, b in sorted(hits, key=lambda h: (-(h[2] - h[1]), h[1], h[0])):
        if any(x <= a and b <= y for x, y in covered):
            continue
        covered.append((a, b))
        out.add((key, a, b))
    return sorted(out, key=lambda h: (h[1], h[0]))


def from_prose(
    text: str,
    *,
    lang: str,
    forms: Sequence[str],
    tier: int,
    source: str,
    url: str,
    revision: Any,
    sections: bool = True,
    anchored_doc: bool = False,
) -> Found:
    """Every candidate of an article's (or a page's) prose. `sections`: the text has `== Heading ==`
    lines and only the lead and `READ_SECTIONS` are read; otherwise the whole text is one section
    and each line a paragraph."""
    found = Found()
    if sections:
        paragraphs = readable_paragraphs(text)
    else:
        paragraphs = [("", True, line.strip()) for line in text.splitlines() if line.strip()]
    lead_named = False
    for number, (_section, is_lead, paragraph) in enumerate(paragraphs):
        sentences = split_sentences(paragraph)
        named = False
        for index, sentence in enumerate(sentences):
            context = named or (is_lead and lead_named)
            found.extend(
                sentence_candidates(
                    sentence, lang=lang, forms=forms, context_named=context, tier=tier,
                    source=source, url=url, revision=revision,
                    sentence_id=f"{url}#p{number}s{index}", anchored_doc=anchored_doc,
                )
            )  # fmt: skip
            if names_site(sentence, forms):
                named = True
                if is_lead:
                    lead_named = True
    return found


# ------------------------------------------------------------------------------ the infobox
#: The infoboxes of a site's article and the fields that state its start (folded names).
INFOBOX_FIELDS = {
    "infobox ancient site": ("built", "founded", "established", "epochs", "periods", "cultures"),
    "infobox archaeological site": ("built", "founded", "established", "epochs", "periods",
                                    "cultures"),  # fmt: skip
    "infobox settlement": ("established_date", "founded"),
    "infobox historic site": ("built", "founded", "established"),
    "infobox military structure": ("built",),
}
_PERIOD_FIELDS = frozenset({"epochs", "periods", "cultures"})


def _template_end(text: str, begin: int) -> int:
    """The offset after the `}}` that closes the template opened at `begin` (nesting counted)."""
    depth, i = 0, begin
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth, i = depth + 1, i + 2
            continue
        if pair == "}}":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
            continue
        i += 1
    return len(text)


def infobox_params(wikitext: str) -> list[tuple[str, str, str]]:
    """`(infobox, field, raw)` for every start field of every known infobox: `raw` is the field's
    text exactly as the wikitext prints it ("| built = c. 3000 BC"), the quote."""
    out = []
    for match in re.finditer(r"\{\{\s*([Ii]nfobox[ _][^|}\n]*)", wikitext):
        name = " ".join(match.group(1).replace("_", " ").split()).casefold()
        if name not in INFOBOX_FIELDS:
            continue
        end = _template_end(wikitext, match.start())
        body = wikitext[match.start() + 2 : end - 2]
        depth, start, parts = 0, 0, []
        i = 0
        while i < len(body):
            pair = body[i : i + 2]
            if pair in ("{{", "[["):
                depth, i = depth + 1, i + 2
                continue
            if pair in ("}}", "]]"):
                depth, i = depth - 1, i + 2
                continue
            if body[i] == "|" and depth == 0:
                parts.append((start, i))
                start = i
            i += 1
        parts.append((start, len(body)))
        for a, b in parts[1:]:
            raw = body[a:b].rstrip()
            key, sep, _value = raw[1:].partition("=")
            if sep and key.strip().casefold() in INFOBOX_FIELDS[name]:
                out.append((name, key.strip().casefold(), raw.strip()))
    return out


def clean_wikitext(value: str) -> str:
    """An infobox value as a reader reads it: references and comments gone, links as their text,
    the date templates spelt out ("{{circa|3000 BC}}" -> "c. 3000 BC", "{{BCE|500}}" -> "500 BCE"),
    any other template dropped."""
    text = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", "; ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    for _ in range(3):
        text = re.sub(r"\{\{\s*(?:circa|c\.|ca\.?|c)\s*\|\s*([^{}|]*)\}\}", r"c. \1", text, flags=re.I)
        text = re.sub(r"\{\{\s*(BCE|BC)\s*\|\s*([^{}|]*)\}\}", r"\2 \1", text)
        text = re.sub(r"\{\{\s*(CE|AD)\s*\|\s*([^{}|]*)\}\}", r"\2 \1", text)
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return " ".join(text.split())


def from_infobox(wikitext: str, *, url: str, revision: Any) -> Found:
    """Tier 1: the start fields of the article's infobox. A date field reads an unmarked year of
    three or four digits as an AD year; a list of periods ("Bronze Age, Iron Age") gives its earliest
    as one candidate; two dated starts in one field are two starts in one sentence."""
    found = Found()
    cap = CONFIG["year_cap"]
    for infobox, name, raw in infobox_params(wikitext):
        value = clean_wikitext(raw.partition("=")[2])
        if not value:
            continue
        sentence_id = f"{url}#{infobox}/{name}"
        if name in _PERIOD_FIELDS:
            spans = [P.PERIODS[k] for k, _, _ in _period_mentions(value)]
            spans = [s for s in spans if s[0] <= cap]
            if len({categorize_period(s[0]) for s in spans}) > 1:
                found.notes.append(Note(1, url, raw, SEVERAL_PERIODS))
                continue
            if spans:
                lo = min(s[0] for s in spans)
                found.candidates.append(
                    Candidate(lo, lo, max(s[1] for s in spans), PERIOD, 1, TIERS[1], url, raw,
                              revision, name, f"{infobox} {name}: {value}", sentence_id)  # fmt: skip
                )
            continue
        low = D.reading_text(value).casefold()
        items = [
            (loc, name)
            for loc in D.located(value)
            if acceptable(loc, low, date_field=True) is None
        ]
        starts = []
        for group in _range_groups(items, low):
            lo = min(g.statement.lo for g in group)
            hi = max(g.statement.hi for g in group)
            if lo <= cap:
                starts.append((lo, hi, group[0].statement))
        for year, tolerance in A.bp_dates(value):
            if year <= cap:
                starts.append((year, year + tolerance, None))
        if len({categorize_period(s[0]) for s in starts}) > 1:
            found.notes.append(Note(1, url, raw, TWO_STARTS))
            continue
        for lo, hi, statement in starts:
            kind = BP if statement is None else statement.kind
            found.candidates.append(
                Candidate(lo, lo, hi, kind, 1, TIERS[1], url, raw, revision, name,
                          f"{infobox} {name}: {value}", sentence_id)  # fmt: skip
            )
    return found


# ------------------------------------------------------------------------------ Wikidata
#: P31 class labels whose item is no archaeological site but a collective of things (a village, a
#: reserve, a region): the dates its pages give belong to something inside it (design section 5).
COLLECTIVE_CLASS_WORDS = (
    "village", "nature reserve", "protected area", "region", "landscape", "municipality",
    "commune", "national park", "natural park", "park", "valley", "mountain", "hill", "island",
    "parish", "civil parish", "county", "district", "province", "neighbourhood", "neighborhood",
    "quarter", "suburb", "hamlet", "town", "city", "human settlement", "locality",
    "geographic region", "cultural landscape", "archipelago", "peninsula", "lake", "river",
)  # fmt: skip
#: P31 class labels that make an item an ancient site even when a collective class stands beside.
ANCIENT_CLASS_WORDS = (
    "archaeological", "ancient", "ruin", "hillfort", "fort", "temple", "tomb", "megalith",
    "megalithic", "dolmen", "menhir", "stone circle", "cave", "rock art", "petroglyph", "tell",
    "tumulus", "archaeological site", "ancient city",
    "barrow", "cairn", "henge", "oppidum", "castro", "pyramid", "necropolis", "sanctuary",
    "nuraghe", "broch", "stupa", "citadel", "acropolis", "villa", "settlement mound",
    "world heritage", "geoglyph", "earthwork", "monument", "shell midden", "midden",
)  # fmt: skip
#: P31 class labels whose item's inception is a modern founding: P571 is vetoed (the park trap).
MODERN_FOUNDING_WORDS = (
    "park", "museum", "reserve", "protected area", "organization", "organisation", "company",
    "society", "school", "university", "geopark", "foundation", "monument of", "zoo", "garden",
)  # fmt: skip
#: P793 event items whose P585 is a start: their English labels.
START_EVENTS = frozenset({"construction", "founding", "foundation", "establishment", "building"})
TIME_PROPS = ("P571", "P580", "P1249")


def class_labels(entity: Mapping[str, Any], classes: Mapping[str, Any]) -> list[str]:
    """The English labels of the item's P31 classes (`harvest` CLASSES.json)."""
    out = []
    for qid in _item_ids(entity, "P31"):
        label = (classes.get(qid) or {}).get("label")
        if label:
            out.append(str(label).casefold())
    return out


def _claims(entity: Mapping[str, Any], prop: str) -> list[Mapping[str, Any]]:
    return [c for c in (entity.get("claims") or {}).get(prop, []) if c.get("rank") != "deprecated"]


def _item_ids(entity: Mapping[str, Any], prop: str) -> list[str]:
    out = []
    for claim in _claims(entity, prop):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(str(value["id"]))
    return out


def collective_reason(labels: Sequence[str]) -> str | None:
    """Why an item is a collective entity, by its P31 labels - None when one of them is an ancient
    site's or none is a collective's."""
    if any(
        re.search(r"(?<!\w)" + re.escape(w) + r"(?:s|es)?(?!\w)", label)
        for label in labels
        for w in ANCIENT_CLASS_WORDS
    ):
        return None
    hits = [label for label in labels if any(
        re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", label) for w in COLLECTIVE_CLASS_WORDS)]
    return f"P31 {', '.join(hits)}" if hits else None


def wikidata_time(value: Mapping[str, Any]) -> tuple[int, int] | None:
    """A Wikidata time value as `(lo, hi)`: a year (precision 9), a decade (8), a century (7) or a
    millennium (6), by Wikidata's historical numbering (no year 0; "-0750" is 750 BC). A coarser
    precision dates nothing here."""
    time_text = str(value.get("time") or "")
    found = re.match(r"([+-])(\d+)-", time_text)
    precision = int(value.get("precision") or 0)
    if found is None or precision < 6:
        return None
    year = int(found.group(2))
    era = D.BC if found.group(1) == "-" else None
    if year == 0:
        return None
    if precision >= 8:
        lo, hi = D.span(D.YEAR, year, era, 9 if precision == 8 else 0)
        return (lo, hi) if era is None else (-year, -year + (9 if precision == 8 else 0))
    kind, size = (D.CENTURY, 100) if precision == 7 else (D.MILLENNIUM, 1000)
    number = -(-year // size)
    return D.span(kind, number, era)


def wikidata_url(qid: str, entity: Mapping[str, Any]) -> str:
    return f"https://www.wikidata.org/w/index.php?title={qid}&oldid={entity.get('lastrevid')}"


def from_wikidata(
    qid: str,
    entity: Mapping[str, Any],
    *,
    classes: Mapping[str, Any],
    item_labels: Mapping[str, Any],
) -> Found:
    """Tier 5: the item's own date claims (module docstring). The quote is the claim as the entity
    prints it; the URL is the item at the revision read."""
    found = Found()
    cap = CONFIG["year_cap"]
    url = wikidata_url(qid, entity)
    revision = entity.get("lastrevid")
    labels = class_labels(entity, classes)
    modern = [label for label in labels if any(w in label for w in MODERN_FOUNDING_WORDS)]
    for prop in TIME_PROPS:
        for claim in _claims(entity, prop):
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if not isinstance(value, dict):
                continue
            quote = f"{prop}: {value.get('time')} (precision {value.get('precision')})"
            if prop == "P571" and modern:
                found.notes.append(Note(5, url, quote, f"P571 of a {modern[0]}: a modern founding"))
                continue
            span = wikidata_time(value)
            if span is None or span[0] > cap:
                continue
            found.candidates.append(
                Candidate(span[0], span[0], span[1], WIKIDATA, 5, f"{TIERS[5]} {prop}", url,
                          quote, revision, prop, f"{prop} {value.get('time')}",
                          f"{url}#{prop}")  # fmt: skip
            )
    for period in _item_ids(entity, "P2348"):
        label = str((item_labels.get(period) or {}).get("label") or "")
        try:
            lo, hi = P.period_of(label)
        except P.PeriodError:
            found.notes.append(Note(5, url, f"P2348: {period} ({label})", "period not in vocabulary"))
            continue
        if P.fold_name(label) in BROAD_PERIODS or lo > cap:
            continue
        found.candidates.append(
            Candidate(lo, lo, hi, PERIOD, 5, f"{TIERS[5]} P2348", url,
                      f"P2348: {period} ({label})", revision, "P2348", f"period {label!r}",
                      f"{url}#P2348")  # fmt: skip
        )
    for claim in _claims(entity, "P793"):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        event = str(value.get("id")) if isinstance(value, dict) else ""
        label = str((item_labels.get(event) or {}).get("label") or "").casefold()
        if label not in START_EVENTS:
            continue
        for qualifier in (claim.get("qualifiers") or {}).get("P585", []):
            when = (qualifier.get("datavalue") or {}).get("value")
            span = wikidata_time(when) if isinstance(when, dict) else None
            if span is None or span[0] > cap:
                continue
            found.candidates.append(
                Candidate(span[0], span[0], span[1], WIKIDATA, 5, f"{TIERS[5]} P793", url,
                          f"P793: {event} ({label}) P585: {when.get('time')}", revision, "P793",
                          f"{label} {when.get('time')}", f"{url}#P793")  # fmt: skip
            )
    return found


# ------------------------------------------------------------------------------ Pleiades
PLEIADES_URL = "https://pleiades.stoa.org/places/{id}"


def from_pleiades(row: Mapping[str, Any], *, forms: Sequence[str]) -> Found:
    """Tier 6, through the item's P1584 only: the description's prose (the description is about the
    place, so it is anchored), then `minDate` with `timePeriodsKeys` (attestation, the weakest)."""
    url = PLEIADES_URL.format(id=row["id"])
    found = from_prose(
        str(row.get("description") or ""), lang="en", forms=forms, tier=6,
        source=f"{TIERS[6]} description", url=url, revision=row.get("modified"),
        sections=False, anchored_doc=True,
    )  # fmt: skip
    keys = str(row.get("timePeriodsKeys") or "")
    raw = str(row.get("minDate") or "").strip()
    if keys and re.fullmatch(r"-?\d+(?:\.0)?", raw):
        year = int(float(raw))
        if year <= CONFIG["year_cap"]:
            found.candidates.append(
                Candidate(year, year, year, PLEIADES, 6, f"{TIERS[6]} minDate", url,
                          f"timePeriodsKeys: {keys}", row.get("modified"), "minDate",
                          f"minDate {raw}", f"{url}#minDate")  # fmt: skip
            )
    return found


# ------------------------------------------------------------------------------ the decision
@dataclass
class Decision:
    site_id: str
    kind: str
    start: int | None = None
    lo: int | None = None
    hi: int | None = None
    tier: int | None = None
    decisive: Candidate | None = None
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    reason: str = ""


#: The years where one period bucket ends and the next begins (`PERIOD_BUCKETS`).
BUCKET_EDGES = frozenset(lo for _label, lo, _hi in PERIOD_BUCKETS[1:])


def on_bucket_edge(c: Candidate) -> bool:
    """A round year exactly on a bucket edge ("c. 3000 BC", "built 1000"): a round number is an
    approximation, and on the edge it cannot say which of the two buckets the start lies in (DEV
    round 1, 2026-11-06: three Neolithic tombs "c. 3000 BC" whose start lies before 3000 BC). A
    century or millennium is a span inside one bucket and stays."""
    return c.kind == YEAR and c.lo == c.hi and c.start in BUCKET_EDGES and c.start % 100 == 0


def scope_problem(site: Mapping[str, Any], start: int) -> str | None:
    """Why a start would take the site out of the D58 window or make it a label borderline case
    (O1: listed for the owner, not written) - None when it stays in."""
    record = {
        "lat": site.get("lat"),
        "lon": site.get("lon"),
        "country": site.get("country"),
        "period_start": start,
        "period_end": None,
    }
    if not passes_date_cutoff(record):
        return f"a start of {start} lies outside the D58 window for {site.get('country')!r}"
    if label_borderline(record):
        return f"a start of {start} makes the site a D58 label borderline case ({site.get('country')!r})"
    return None


def decide(
    site: Mapping[str, Any],
    found: Found,
    *,
    collective: str | None = None,
    has_source: bool = True,
) -> Decision:
    """The site's start (module docstring: D70 and O1)."""
    sid = str(site["site_id"])
    enabled = set(CONFIG["tiers"])
    notes = list(found.notes)
    candidates = []
    for c in found.candidates:
        if c.tier not in enabled:
            continue
        if on_bucket_edge(c):
            notes.append(Note(c.tier, c.url, c.quote, BUCKET_EDGE))
            continue
        candidates.append(c)
    if collective is not None:
        return Decision(sid, ABSTAIN, candidates=candidates, notes=notes, reason=f"{COLLECTIVE}: {collective}")
    if not candidates:
        if not has_source:
            reason = NO_SOURCE
        elif any(n.reason == "hedged" for n in notes):
            reason = HEDGED_ONLY
        else:
            reason = NO_CANDIDATE
        return Decision(sid, ABSTAIN, candidates=[], notes=notes, reason=reason)
    tier = min(c.tier for c in candidates)
    if any(n.reason == TWO_STARTS and n.tier <= tier for n in notes):
        return Decision(sid, ABSTAIN, candidates=candidates, notes=notes, tier=tier,
                        reason=TWO_STARTS)  # fmt: skip
    deciding = sorted((c for c in candidates if c.tier == tier), key=lambda c: c.start)
    decisive = deciding[0]
    solo = CONFIG["solo"]
    if decisive.kind == PLEIADES and not solo["pleiades"]:
        return Decision(sid, ABSTAIN, candidates=candidates, notes=notes, tier=tier,
                        decisive=decisive, reason=f"{SOLO_REFUSED}: pleiades minDate alone")  # fmt: skip
    if all(c.kind in (PERIOD, PLEIADES) for c in candidates) and not solo["period"]:
        return Decision(sid, ABSTAIN, candidates=candidates, notes=notes, tier=tier,
                        decisive=decisive, reason=f"{SOLO_REFUSED}: a period word alone")  # fmt: skip
    starts = [c.start for c in candidates if not (c.kind == PLEIADES and c is not decisive)]
    lo, hi = min(starts), max(starts)
    buckets = {categorize_period(s) for s in starts}
    kind = SINGLE if len(buckets) == 1 else RANGE
    if kind == RANGE and not CONFIG["write_ranges"]:
        return Decision(sid, ABSTAIN, None, lo, hi, tier, decisive, candidates, notes,
                        reason=f"{SOURCES_DISAGREE}: {len(buckets)} buckets")  # fmt: skip
    decision = Decision(sid, kind, decisive.start, lo, hi, tier, decisive, candidates, notes)
    problem = scope_problem(site, decisive.start)
    if problem is not None:
        decision.kind, decision.reason = SCOPE_HOLD, problem
    return decision


# ------------------------------------------------------------------------------ one site's sources
@dataclass(frozen=True)
class Sources:
    """Where the extractor reads a site's sources: the harvest root (`harvest.py fetch` and
    `fetch-dating`), the Wikipedia cache, the cited pages and the Pleiades table."""

    harvest: Path
    wiki_cache: Path
    fields_dir: Path
    pleiades_csv: Path

    def load(self) -> _Loaded:
        from fields import harvest as H
        from fields import wiki as W

        sites = {s["site_id"]: s for s in H.read_sites(self.harvest)}
        classes_path = self.harvest / H.CLASSES_FILE
        labels_path = self.harvest / H.ITEM_LABELS_FILE
        if not labels_path.exists():
            raise DatingError(f"{labels_path} is missing - run `harvest.py fetch-dating` first")
        return _Loaded(
            self,
            sites,
            W.WikiCache(self.wiki_cache),
            json.loads(classes_path.read_text(encoding="utf-8")),
            json.loads(labels_path.read_text(encoding="utf-8")),
            H.cited_page_refs(self.fields_dir),
            read_pleiades(self.pleiades_csv),
        )


def read_pleiades(path: Path) -> dict[str, dict[str, str]]:
    """The Pleiades places table by id (`data/raw/pleiades/pleiades-places.csv`)."""
    import csv

    if not path.exists():
        raise DatingError(f"{path} is missing: the Pleiades table is not on this machine")
    with path.open(encoding="utf-8", newline="") as handle:
        return {str(row["id"]): row for row in csv.DictReader(handle)}


@dataclass
class _Loaded:
    sources: Sources
    sites: Mapping[str, Mapping[str, Any]]
    wiki: Any
    classes: Mapping[str, Any]
    item_labels: Mapping[str, Any]
    pages: Mapping[str, list[dict[str, Any]]]
    pleiades: Mapping[str, Mapping[str, str]]

    def found(self, site_id: str, *, skip_urls: frozenset[str] = frozenset()) -> tuple[Found, str | None, bool]:
        """Every candidate of the site's sources, the collective reason of its item, and whether it
        has any source the enabled tiers read (`CONFIG["tiers"]`: a disabled tier's source is not
        read at all). `skip_urls`: cited pages not to read (the gold's own citations)."""
        from fields import harvest as H

        site = self.sites.get(site_id)
        if site is None:
            raise DatingError(f"{site_id} is not a site of {self.sources.harvest / H.SITES_FILE}")
        qid = site["qid"]
        entity = H.load_entity(self.sources.harvest, qid) if qid else {}
        names = [site["name"], site.get("enwiki_title")]
        for block in ("labels", "aliases"):
            for value in (entity.get(block) or {}).values():
                for item in value if isinstance(value, list) else [value]:
                    names.append(item.get("value"))
        forms = [f for f in name_forms(names) if not is_period_name(f)]
        found = Found()
        has_source = False
        enabled = set(CONFIG["tiers"])
        for page in self.wiki.pages(site_id):
            if page.get("missing"):
                continue
            if is_period_name(str(page.get("resolved_title") or page["title"])):
                # the cache holds a period's article for the site ("Iron Age" for Yarrows Broch,
                # DEV round 1, 2026-11-06): it dates the period, not the site
                found.notes.append(Note(2, str(page.get("title")), "", "period-article"))
                continue
            lang, revid = str(page["lang"]), page.get("revid")
            title = str(page.get("resolved_title") or page["title"])
            tier = 2 if lang == "en" else 3
            if tier in enabled:
                has_source = True
                found.extend(from_prose(str(page["text"]), lang=lang,
                                        forms=name_forms([*forms, title]), tier=tier,
                                        source=f"{lang}wiki prose",
                                        url=permalink(lang, title, revid), revision=revid))  # fmt: skip
            if lang == "en" and 1 in enabled:
                text = H.load_wikitext(self.sources.harvest, lang, revid)
                if text is not None:
                    has_source = True
                    found.extend(from_infobox(text, url=raw_permalink(lang, title, revid),
                                              revision=revid))  # fmt: skip
        if qid and 3 in enabled:
            cached = frozenset(str(p["lang"]) for p in self.wiki.pages(site_id))
            for lang, record in H.load_wikis(self.sources.harvest, qid, entity, skip=cached):
                if record.get("missing"):
                    continue
                has_source = True
                title = str(record["title"])
                found.extend(from_prose(str(record["text"]), lang=lang,
                                        forms=name_forms([*forms, title]), tier=3,
                                        source=f"{lang}wiki prose",
                                        url=permalink(lang, title, record["revid"]),
                                        revision=record["revid"]))  # fmt: skip
        if qid and 5 in enabled:
            has_source = has_source or bool(entity)
            found.extend(from_wikidata(qid, entity, classes=self.classes, item_labels=self.item_labels))
        if qid and 6 in enabled:
            for pid in _string_values(entity, "P1584"):
                row = self.pleiades.get(pid)
                if row is not None:
                    has_source = True
                    found.extend(from_pleiades(row, forms=forms))
        for page in self.pages.get(site_id, ()) if 4 in enabled else ():
            if page["url"] in skip_urls:
                continue
            text = H.page_text(page)
            if text is None:
                continue
            has_source = True
            found.extend(from_prose(text, lang="en", forms=forms, tier=4,
                                    source=f"cited page {urlsplit(page['url']).hostname}",
                                    url=page["url"], revision=page.get("fetched_at"),
                                    sections=False))  # fmt: skip
        collective = collective_reason(class_labels(entity, self.classes)) if entity else None
        return found, collective, has_source

    def decide(self, site_id: str, *, collectives: Mapping[str, str] | None = None,
               skip_urls: frozenset[str] = frozenset()) -> Decision:  # fmt: skip
        found, collective, has_source = self.found(site_id, skip_urls=skip_urls)
        if collectives and site_id in collectives:
            collective = collectives[site_id]
        return decide(self.sites[site_id], found, collective=collective, has_source=has_source)


def is_period_name(name: str) -> bool:
    """Whether `name` is a period of the vocabulary ("Iron Age"), not a site's name."""
    return P.fold_name(name) in P.PERIODS or P.fold_name(name) + " period" in P.PERIODS


def _string_values(entity: Mapping[str, Any], prop: str) -> list[str]:
    out = []
    for claim in _claims(entity, prop):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, str):
            out.append(value)
    return out


def permalink(lang: str, title: str, revid: Any) -> str:
    """The article at the revision read (the address the quote is checked against)."""
    return (
        f"https://{lang}.wikipedia.org/w/index.php?title="
        f"{url_quote(title.replace(' ', '_'), safe='/:@!$()*,;-._~')}&oldid={revid}"
    )


def raw_permalink(lang: str, title: str, revid: Any) -> str:
    """The wikitext at the revision read (an infobox quote is a line of it)."""
    return permalink(lang, title, revid) + "&action=raw"


# ------------------------------------------------------------------------------ the run's files
def _candidate_quote(c: Candidate, outcome: str = UNVERIFIED) -> dict[str, Any]:
    return {
        "source": c.url,
        "quote": c.quote,
        "outcome": outcome,
        "detail": f"tier {c.tier} {c.source}; {c.detail}; cue {c.cue or '-'}",
        "tier": c.tier,
        "kind": c.kind,
        "start": c.start,
    }


def decision_row(site: Mapping[str, Any], decision: Decision, stamp: str) -> dict[str, Any]:
    """The DECISIONS.jsonl row of a site (design section 8: the shape of a DERIVED row with real
    quotes). A written start (`single`, `range`) is `replace`; an abstention and a scope hold are
    `unresolved` with the candidates as their evidence."""
    ordered = sorted(decision.candidates, key=lambda c: (c is not decision.decisive, c.tier, c.start))
    listed = "; ".join(f"t{c.tier} {c.kind} {c.start}" for c in ordered) or "none"
    writes = decision.kind in (SINGLE, RANGE)
    if writes:
        reasoning = (
            f"deterministic extractor: rule {decision.kind}; start {decision.start} from tier "
            f"{decision.tier} ({decision.decisive.source if decision.decisive else ''}); range of "
            f"the candidates {decision.lo}..{decision.hi}; candidates [{listed}]"
        )
    else:
        reasoning = f"deterministic extractor: {decision.kind} ({decision.reason}); candidates [{listed}]"
    return {
        "site_id": decision.site_id,
        "name": site["name"],
        "field": "period_start",
        "decision": A.REPLACE if writes else A.UNRESOLVED,
        "value": str(decision.start) if writes else None,
        "stored": None,
        "status": "MISSING",
        "via": "extracted",
        "round": 0,
        "counted_rounds": [0],
        "answered_by": f"extractor:dating@{stamp}",
        "model": None,
        "quotes": [_candidate_quote(c) for c in ordered],
        "reasoning": reasoning,
        "value_page": None,
        "extract": {
            "kind": decision.kind,
            "start": decision.start,
            "lo": decision.lo,
            "hi": decision.hi,
            "tier": decision.tier,
            "reason": decision.reason,
            "notes": [asdict(n) for n in decision.notes][:40],
        },
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


def read_collectives(path: Path | None) -> dict[str, str]:
    """`--collectives FILE`: JSON lines `{"site_id", "reason"}` (the X8 list)."""
    if path is None:
        return {}
    out = {}
    for row in _read_jsonl(path):
        if set(row) != {"site_id", "reason"} or not str(row["reason"]).strip():
            raise DatingError(f"{path}: a line is not {{site_id, reason}}: {row}")
        out[str(row["site_id"])] = str(row["reason"])
    return out


def run(run_dir: Path, loaded: _Loaded, *, collectives: Mapping[str, str]) -> dict[str, Any]:
    """The extractor over the run's population (CLASSIFIED.jsonl, every site asked period_start):
    DECISIONS.jsonl, an empty REASK.json, EXTRACT.json, REST.jsonl (D73) and OWNER_SCOPE.jsonl (O1)."""
    from fields import classify as C

    if R.read_rule(run_dir) is not R.EXTRACT:
        raise DatingError(f"{run_dir} is not a run of the extract rule (its RUN.json)")
    if (run_dir / DECISIONS_FILE).exists():
        raise DatingError(f"{run_dir / DECISIONS_FILE} exists: the extractor runs once per run")
    lines = _read_jsonl(run_dir / C.CLASSIFIED_FILE)
    asked = [line for line in lines if "period_start" in line["asked"]]
    hashes = code_hashes()
    stamp = code_stamp(hashes)
    rows, rest, scope = [], [], []
    counts: Counter[str] = Counter()
    for line in sorted(asked, key=lambda line: line["site_id"]):
        sid = str(line["site_id"])
        decision = loaded.decide(sid, collectives=collectives)
        site = loaded.sites[sid]
        rows.append(decision_row(site, decision, stamp))
        counts[f"kind:{decision.kind}"] += 1
        if decision.kind in (SINGLE, RANGE, SCOPE_HOLD) and decision.decisive is not None:
            counts[f"tier:{decision.tier}"] += 1
            counts[f"decisive:{decision.decisive.kind}"] += 1
        if decision.kind == ABSTAIN:
            counts[f"abstain:{decision.reason.split(':')[0]}"] += 1
            rest.append({"site_id": sid, "name": site["name"], "reason": decision.reason})
        if decision.kind == SCOPE_HOLD:
            scope.append({"site_id": sid, "name": site["name"], "country": site["country"],
                          "start": decision.start, "reason": decision.reason,
                          "quote": decision.decisive.quote if decision.decisive else None,
                          "url": decision.decisive.url if decision.decisive else None})  # fmt: skip
    _write_jsonl(run_dir / DECISIONS_FILE, rows)
    _write_json(run_dir / REASK_FILE, {"fields": {}})
    _write_jsonl(run_dir / REST_FILE, rest)
    _write_jsonl(run_dir / SCOPE_FILE, scope)
    result = {
        "sites": len(rows),
        "written": counts[f"kind:{SINGLE}"] + counts[f"kind:{RANGE}"],
        "counts": dict(sorted(counts.items())),
        "code": hashes,
        "stamp": stamp,
        "config": dict(CONFIG),
        "decisions_sha256": _sha256(run_dir / DECISIONS_FILE),
        "inputs": {
            "harvest": str(loaded.sources.harvest),
            "wiki_cache": str(loaded.sources.wiki_cache),
            "fields_dir": str(loaded.sources.fields_dir),
            "pleiades": str(loaded.sources.pleiades_csv),
            "collectives": len(collectives),
        },
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(run_dir / EXTRACT_FILE, result)
    return {k: result[k] for k in ("sites", "written", "counts", "stamp")}


# ------------------------------------------------------------------------------ verify
def verify_quote(quote: Mapping[str, Any], fetch: Callable[[str], Any]) -> str:
    """Whether a candidate's quote stands at its permalink, read now: `found` or `not found` (or why
    it could not be read). Prose and infobox lines are matched character for character after the
    footnote-marker tolerance of `opus_audit/quotes.normalise`; a Wikidata claim is read in the
    entity of that revision."""
    from opus_audit import quotes as Q

    url = str(quote["source"])
    if quote.get("kind") == PLEIADES:
        return "not fetched: a Pleiades CSV field is read from the dump, not the live page"
    if quote.get("tier") == 5:
        found = re.search(r"title=(Q\d+)&oldid=(\d+)", url)
        if found is None:
            return "not found: no item revision in the URL"
        body = fetch(
            f"https://www.wikidata.org/wiki/Special:EntityData/{found.group(1)}.json"
            f"?revision={found.group(2)}"
        )
        if isinstance(body, str):
            return body
        claim_text = str(quote["quote"]).split(" (precision")[0].split(" P585:")[0]
        prop, _, value = claim_text.partition(": ")
        text = json.dumps(body, ensure_ascii=False)
        return "found" if (f'"{prop}"' in text and value.split(" (")[0] in text) else "not found"
    page = fetch(url)
    if isinstance(page, str):
        return page
    content_type, data = page
    source = Q.page_source(content_type, data)
    if source.failure:
        return f"{source.failure}: {source.detail}"
    wanted = Q.normalise(str(quote["quote"]))
    return "found" if any(wanted in text for _, text in source.texts) else "not found"


def verify(run_dir: Path, fetch: Callable[[str], Any]) -> dict[str, Any]:
    """Every quote of the run's decisions read at its permalink, serially (`fetch` paces): a
    written decision whose decisive (first) quote is not found becomes `unresolved` with the reason
    named. DECISIONS.jsonl is rewritten and VERIFIED.json pins it."""
    path = run_dir / DECISIONS_FILE
    if (run_dir / VERIFIED_FILE).exists():
        raise DatingError(f"{run_dir / VERIFIED_FILE} exists: a run is verified once")
    extract = json.loads((run_dir / EXTRACT_FILE).read_text(encoding="utf-8"))
    if _sha256(path) != extract["decisions_sha256"]:
        raise DatingError(f"{path} is not the file the extractor wrote (EXTRACT.json)")
    rows = _read_jsonl(path)
    counts: Counter[str] = Counter()
    for row in rows:
        for quote in row["quotes"]:
            quote["outcome"] = verify_quote(quote, fetch)
            counts[quote["outcome"].split(":")[0]] += 1
        if row["decision"] == A.REPLACE and row["quotes"][0]["outcome"] != "found":
            row["extract"]["unverified_value"] = row["value"]
            row["decision"], row["value"] = A.UNRESOLVED, None
            row["reasoning"] += f" | verify: the decisive quote is {row['quotes'][0]['outcome']}"
            counts["withdrawn"] += 1
    _write_jsonl(path, rows)
    result = {
        "decisions_sha256": _sha256(path),
        "extract_decisions_sha256": extract["decisions_sha256"],
        "quotes": dict(sorted(counts.items())),
        "written": sum(1 for r in rows if r["decision"] == A.REPLACE),
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(run_dir / VERIFIED_FILE, result)
    return result


def http_fetcher(pages: Path, *, pace: float) -> Callable[[str], Any]:
    """`verify`'s fetch: one GET at a time with `harvest.USER_AGENT`, at least `pace` seconds apart
    (Wikimedia throttles parallel clients), each body kept under `pages` (`opus_audit/quotes`)."""
    from opus_audit import quotes as Q

    from fields import harvest as H

    if pace < 1.0:
        raise DatingError(f"--pace {pace}: Wikimedia is asked at most once a second")
    client = H.open_client()
    last = [0.0]

    def fetch(url: str) -> Any:
        meta = pages / f"{Q.url_key(url)}.json"
        if not meta.exists():
            wait = last[0] + pace - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.monotonic()
            Q.collect([url], pages, client, now=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      pace=pace)  # fmt: skip
        if not meta.exists():
            return f"not fetched: {Q.not_fetchable(url)}"
        record = json.loads(meta.read_text(encoding="utf-8"))
        if record.get("error") or record.get("status") != 200:
            return f"fetch failed: {record.get('status')} {record.get('error')}"
        body = (pages / f"{Q.url_key(url)}.body").read_bytes()
        if "Special:EntityData" in url:
            return json.loads(body.decode("utf-8"))
        return str(record.get("content_type") or ""), body

    return fetch


# ------------------------------------------------------------------------------ show (D71, O3)
def choose_shown(rows: Sequence[Mapping[str, Any]], n: int, seed: int) -> list[Mapping[str, Any]]:
    """`n` written cells for the D71 look: ranges and period words over-represented (a third each,
    as far as there are), the rest drawn across the tiers in turn; seeded."""
    written = sorted((r for r in rows if r["decision"] == A.REPLACE), key=lambda r: r["site_id"])
    rng = random.Random(seed)  # noqa: S311 - a seeded draw, not a key
    ranges = [r for r in written if r["extract"]["kind"] == RANGE]
    periods = [r for r in written if r["quotes"][0]["kind"] == PERIOD and r not in ranges]
    chosen: list[Mapping[str, Any]] = []
    for pool in (ranges, periods):
        rng.shuffle(pool)
        chosen.extend(pool[: n // 3])
    by_tier: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for r in written:
        if r not in chosen:
            by_tier[int(r["extract"]["tier"])].append(r)
    for pool in by_tier.values():
        rng.shuffle(pool)
    while len(chosen) < n and any(by_tier.values()):
        for tier in sorted(by_tier):
            if by_tier[tier] and len(chosen) < n:
                chosen.append(by_tier[tier].pop())
    return sorted(chosen, key=lambda r: r["site_id"])


def show(run_dir: Path, n: int, seed: int) -> dict[str, Any]:
    """OWNER_SHOW.md and OWNER_SHOW.json: the cells shown before the wave (D71; O3 while the owner
    is away: three independent adversarial checks of the same cells)."""
    verified = json.loads((run_dir / VERIFIED_FILE).read_text(encoding="utf-8"))
    if _sha256(run_dir / DECISIONS_FILE) != verified["decisions_sha256"]:
        raise DatingError("DECISIONS.jsonl is not the verified file")
    rows = _read_jsonl(run_dir / DECISIONS_FILE)
    chosen = choose_shown(rows, n, seed)
    lines = [
        "# D70 extractor: the cells shown before the wave (D71)",
        "",
        f"Run `{run_dir}`, {len(chosen)} of {verified['written']} written cells, seed {seed}. "
        "Each row: the site, the start the extractor writes, and every quote it rests on.",
        "",
    ]
    for r in chosen:
        e = r["extract"]
        lines += [
            f"## {r['name']} (`{r['site_id']}`)",
            "",
            f"start **{r['value']}** ({categorize_period(int(r['value']))}), rule {e['kind']}, "
            f"tier {e['tier']}, candidates {e['lo']}..{e['hi']}",
            "",
        ]
        for q in r["quotes"]:
            lines.append(f"- [{q['outcome']}] {q['detail']} - {q['source']}")
            lines.append(f"  > {q['quote'][:600]}")
        lines.append("")
    (run_dir / SHOW_MD).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    record = {
        "decisions_sha256": verified["decisions_sha256"],
        "seed": seed,
        "cells": [r["site_id"] for r in chosen],
    }
    _write_json(run_dir / SHOW_JSON, record)
    return {"shown": len(chosen), "of": verified["written"]}


#: What a check says of a shown cell.
CHECK_VERDICTS = ("right", "wrong", "unclear")


def shown(run_dir: Path, checks: Path, by: str) -> dict[str, Any]:
    """OWNER_SHOWN.json from the checks of the shown cells (`checks`: JSON lines `{"site_id",
    "verdicts": [{"model", "verdict", "reason"}, ...]}`, three per cell under O3, or one owner
    line). A cell is wrong when most of its checks say so; the wave goes (`go`) only with at most
    `SHOWN_MAX_WRONG` wrong cells and every shown cell checked."""
    from opus_handoff import NEW_ANSWER_MODELS

    record = json.loads((run_dir / SHOW_JSON).read_text(encoding="utf-8"))
    lines = {str(r["site_id"]): r for r in _read_jsonl(checks)}
    missing = sorted(set(record["cells"]) - set(lines))
    if missing:
        raise DatingError(f"{len(missing)} shown cell(s) have no check: {missing[:3]}")
    wrong, cells = 0, []
    for sid in record["cells"]:
        verdicts = lines[sid]["verdicts"]
        for v in verdicts:
            if v["verdict"] not in CHECK_VERDICTS:
                raise DatingError(f"{sid}: verdict {v['verdict']!r} is not one of {CHECK_VERDICTS}")
            if v["model"] not in (*NEW_ANSWER_MODELS, "owner"):
                raise DatingError(f"{sid}: {v['model']!r} may not answer (D6: {NEW_ANSWER_MODELS})")
        bad = sum(1 for v in verdicts if v["verdict"] == "wrong")
        is_wrong = bad * 2 > len(verdicts)
        wrong += is_wrong
        cells.append({"site_id": sid, "wrong": is_wrong, "verdicts": verdicts})
    result = {
        "decisions_sha256": record["decisions_sha256"],
        "shown_by": by,
        "cells": cells,
        "n": len(cells),
        "wrong": wrong,
        "go": wrong <= SHOWN_MAX_WRONG and len(cells) >= SHOWN_CELLS,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(run_dir / SHOWN_FILE, result)
    return {k: result[k] for k in ("n", "wrong", "go")}


# ------------------------------------------------------------------------------ the CLI
def default_sources(harvest: Path, fields_dir: Path) -> Sources:
    from fields import wiki as W

    return Sources(harvest, W.WIKI_CACHE, fields_dir,
                   REPO / "data" / "raw" / "pleiades" / "pleiades-places.csv")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {name: sub.add_parser(name) for name in ("run", "verify", "show", "shown")}
    for command in commands.values():
        command.add_argument("--run", type=Path, required=True)
    commands["run"].add_argument("--harvest", type=Path, required=True)
    commands["run"].add_argument("--fields-dir", type=Path,
                                 default=REPO / "output" / "remediation" / "fields")  # fmt: skip
    commands["run"].add_argument("--collectives", type=Path)
    commands["verify"].add_argument("--pace", type=float, default=1.0)
    commands["show"].add_argument("--n", type=int, default=SHOWN_CELLS)
    commands["show"].add_argument("--seed", type=int, required=True)
    commands["shown"].add_argument("--checks", type=Path, required=True)
    commands["shown"].add_argument("--by", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            loaded = default_sources(args.harvest, args.fields_dir).load()
            result: Any = run(args.run, loaded, collectives=read_collectives(args.collectives))
        elif args.command == "verify":
            result = verify(args.run, http_fetcher(args.run / "verify_pages", pace=args.pace))
        elif args.command == "show":
            result = show(args.run, args.n, args.seed)
        else:
            result = shown(args.run, args.checks, args.by)
    except (DatingError, R.RuleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
