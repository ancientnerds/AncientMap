"""Contract `shorts-v1`: the card as the voice-over of a Short that reveals the site only at the end.

Owner decisions D1-D5 and D35 of 2026-10-08 (`output/remediation/OWNER_DECISIONS_2026-10-08.md`),
the rules C1-C20 of the design digest (`output/remediation/state-2026-10-08/teaser_design_digest.md`,
section JUDGE) and `output/remediation/final-2026-10-08/plans/cards.md` section 3.1. This module is
the mechanical half of the contract (C3-C16); the judgement half (the claims, the hook, the tone,
whether the card is this site) is the checker's (`prompts_shorts.checker_prompt`). Pure: no
database, no network, no model, no clock.

It is a sibling of `contract.py`, which stays byte-frozen: prompts are pinned by sha256 in every
export, so editing the v1 files would make runs 01-06, the gap run and the pilots unimportable (they
are also the calibration material). The v1 helpers are imported, never edited. `RUN.json["contract"]`
selects the contract of a run (`run.contract_of`).

## What changes against v1

A v1 card names its site and may ask one question. A shorts-v1 card is **nameless** (D1): the Short
shows the country from its first frame and reveals "Name, Country." at the end, so the card holds no
form of the name, no alias, no distinctive word of the name and no country or demonym (C7, C8).
It is exactly two sentences (C5); sentence 1 plays over the six-second globe flight, so it is 40-85
characters, opens on its most surprising concrete detail and is no address (C8, C9). The whole card is
narrated in at most 14.0 seconds (C6), holds at most two numerals (C3), no question, no "you" and no
call to action (C10), and every caption word fits the frame (C13). The writer also names the photo
anchors the Short cuts its stills on (C14) and the description sentence that pays the open thread off
on the site page, the **reserve** (C15).

## The rules, in code (`problems_shorts`)

* C3 numbers: at most `MAX_NUMERALS` numerals and `MAX_DIGITS` digits, at most `MAX_S1_DIGITS` in
  sentence 1, no Roman numeral (a regnal number is spelled out), every numeral grounded as in v1.
* C4 the v1 mechanical contract (`contract.problems`) with its name, sentence-count and question
  rules left to the rules below: 160-190 characters, layout, characters, circa, grounded numerals and
  the font. The font is measured on the card alone - the drawn name is the Short's own concern
  (owner decision D23, `spoken_name`).
* C5 exactly two sentences, each ending in a full stop; sentence 1 is `S1_MIN`-`S1_MAX` characters.
* C6 the narration estimate `6.04 + 0.0334 x characters + 0.318 x digits` (fitted on the 16 rendered
  Shorts) is at most `NARRATION_MAX_S` seconds.
* C7 `name_problems`: no form of the stored name, no `unified_site_names` alias, no distinctive token
  of the name. C8: no country name or demonym (`COUNTRY_TERMS`), no administrative word in sentence 1.
* C9 sentence 1 opens on no location preposition (unless a numeral follows), no `BAD_OPENERS` word and
  no "A/An/The" followed within three words by a site-type noun.
* C10 no `?`, `!`, `...`, `you`/`your`, no call-to-action word.
* C11 a mystery or superlative word only where the description has the same stem.
* C13 every caption word at most `COMMON_WORD_PX`; a proper noun of the description at most
  `PROPER_WORD_PX`.
* C14 the anchors, only for a Shorts-eligible site (`ShortsBasis.shorts_eligible`).
* C15 the reserve: description sentence ids the card does not use, or `reveal`; `None` means the
  card is not `shorts_ready`.
* C16 `diversity_problems`, asked at the import of the rating (`run.import_stage`).

C12 (a present-state word) is a flag, not a refusal: `present_state_words` hands the words to the
checker, who decides. The seeded-defect canary (`seed_defect`) is the run's check on its checkers.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from phase4.scope4 import numerals  # noqa: E402 - the numeral reading of v1
from phase4.sentences import names_in  # noqa: E402 - Phase 4's name fold, whole words
from phase4.subject_gate import fold  # noqa: E402

from pipeline.lyra.text_sentences import split_sentences  # noqa: E402
from pipeline.utils import card_provenance as CP  # noqa: E402
from teaser import contract as C  # noqa: E402 - the v1 mechanical contract, imported never edited

#: The name of the contract in `RUN.json["contract"]` and in the card provenance (v3).
CONTRACT = CP.CONTRACT_SHORTS

MAX_NUMERALS = 2
MAX_DIGITS = 8
MAX_S1_DIGITS = 4
SENTENCES = 2
S1_MIN, S1_MAX = 40, 85
#: C6: the narration, `a + b x characters + c x digits` seconds, fitted on the 16 rendered Shorts
#: (R^2 0.77, mean error 0.78 s; refit after every 20 rendered Shorts).
NARRATION_FIT = (6.04, 0.0334, 0.318)
NARRATION_MAX_S = 14.0
#: C13: the widest caption word, in pixels (Orbitron 700 at 92 px, outline included).
COMMON_WORD_PX = 696
PROPER_WORD_PX = 1000
#: C14.
MAX_ANCHORS = CP.MAX_ANCHORS
ANCHOR_S1_TAIL = 25
ANCHOR_LATER_START = 95
ANCHOR_GAP = 28
#: A site is Shorts-eligible with this many usable images (non-excluded, short side >= 900, aspect
#: <= 2.0) and this many raw description characters.
MIN_POOL_IMAGES = 6
MIN_ELIGIBLE_CHARS = 300
#: D3: a description shorter than this (raw characters, markers included) is thin; a writer may
#: decline it instead of padding (C19).
THIN_CHARS = 300
#: The variants a writer answers, and the hook types they declare (R5: an object, an act, a person, a
#: number, the meaning of the name, a stated absence).
VARIANTS = 3
HOOK_TYPES = CP.HOOK_TYPES
#: C16: no opening of three words occurs in more than this share of a run's cards (one occurrence is
#: always allowed), and no opening of five words repeats.
OPENING_SHARE = 0.01
REVEAL = CP.REVEAL

# ------------------------------------------------------------------------------ the words
#: Words that name what a site is or does, or glue a name together: a name made only of them is
#: exempt from the distinctive-token rule (the 13 shown names such as `Roman Walls`, `Great Bath`),
#: and a single-word alias in this set is a common English word, not a name. Compared after `fold`,
#: with one trailing `s` taken off.
GENERIC_WORDS = frozenset(
    """a an and of the in on at by to for from with de del della di da do dos das du des la le les el
    los las lo al der die das den von van zu st saint sainte santa san santo sao ste mount mt
    site settlement town city village hamlet fort fortress fortified fortification hillfort hill
    camp castle tomb grave burial cairn barrow mound dolmen temple monument complex ruin ruined
    chamber passage church chapel abbey monastery cathedral priory palace villa enclosure wall gate
    tower bridge road bath theatre theater amphitheatre amphitheater forum arch aqueduct mine cave
    rock shelter stone circle standing row alignment ring henge earthwork ditch bank rampart hall
    house farm field valley mountain river lake island coast bay cliff headland promontory
    roman greek great ancient old new big small large little upper lower north south east west
    northern southern eastern western central inner outer first second third entrance sanctuary
    shrine altar platform terrace plaza court pyramid tumulus tumuli menhir stele obelisk statue
    geoglyph petroglyph archaeological park national historic area necropolis cemetery group
    mosque minaret tell tepe huaca anta gaer din dun caer castro pa""".split()
)

#: C8: the country as written in the data and the words that name its people, by country. A card
#: never names its own country: the Short shows it from frame 0. A country that is not here is
#: matched by its own name alone. The table covers every country of the 4,900 shown sites
#: (measured 2026-10-09, read-only).
COUNTRY_TERMS: Mapping[str, tuple[str, ...]] = {
    "England": ("English",),
    "Greece": ("Greek", "Greeks"),
    "Peru": ("Peruvian",),
    "Spain": ("Spanish", "Spaniard", "Spaniards"),
    "Italy": ("Italian", "Italians"),
    "Türkiye": ("Turkey", "Turkiye", "Turkish", "Turk", "Turks"),
    "France": ("French",),
    "Mexico": ("Mexican", "Mexicans"),
    "Wales": ("Welsh",),
    "Egypt": ("Egyptian", "Egyptians"),
    "Portugal": ("Portuguese",),
    "Germany": ("German", "Germans"),
    "Pakistan": ("Pakistani",),
    "Scotland": ("Scottish", "Scots", "Scot", "Scotsman"),
    "Bulgaria": ("Bulgarian", "Bulgarians"),
    "Guatemala": ("Guatemalan",),
    "Serbia": ("Serbian", "Serbs"),
    "Croatia": ("Croatian", "Croats"),
    "Cyprus": ("Cypriot", "Cypriots"),
    "Ireland": ("Irish",),
    "Ukraine": ("Ukrainian",),
    "Malta": ("Maltese",),
    "Azerbaijan": ("Azerbaijani",),
    "Sweden": ("Swedish", "Swede", "Swedes"),
    "India": ("Indian", "Indians"),
    "Algeria": ("Algerian",),
    "Saudi Arabia": ("Saudi", "Arabia"),
    "Iraq": ("Iraqi",),
    "Belize": ("Belizean",),
    "Australia": ("Australian",),
    "Denmark": ("Danish", "Dane", "Danes"),
    "Georgia": ("Georgian", "Georgians"),
    "Poland": ("Polish", "Pole", "Poles"),
    "Lebanon": ("Lebanese",),
    "Albania": ("Albanian",),
    "USA": ("America", "American", "Americans", "United States"),
    "Northern Ireland": ("Northern Irish", "Ulster"),
    "Switzerland": ("Swiss",),
    "Afghanistan": ("Afghan", "Afghans"),
    "Israel": ("Israeli",),
    "Austria": ("Austrian",),
    "North Macedonia": ("Macedonia", "Macedonian"),
    "Iran": ("Iranian",),
    "Armenia": ("Armenian",),
    "Tunisia": ("Tunisian",),
    "South Korea": ("Korea", "Korean"),
    "Bolivia": ("Bolivian",),
    "Netherlands": ("Dutch", "Holland"),
    "Kazakhstan": ("Kazakh",),
    "Syria": ("Syrian",),
    "Jordan": ("Jordanian",),
    "Norway": ("Norwegian",),
    "Bahrain": ("Bahraini",),
    "Belgium": ("Belgian",),
    "Chile": ("Chilean",),
    "Finland": ("Finnish", "Finn", "Finns"),
    "Taiwan": ("Taiwanese",),
    "Honduras": ("Honduran",),
    "Libya": ("Libyan",),
    "Ethiopia": ("Ethiopian",),
    "Indonesia": ("Indonesian",),
    "Bosnia and Herzegovina": ("Bosnia", "Herzegovina", "Bosnian"),
    "North Korea": ("Korea", "Korean"),
    "China": ("Chinese",),
    "Thailand": ("Thai",),
    "Morocco": ("Moroccan",),
    "Slovakia": ("Slovak",),
    "Panama": ("Panamanian",),
    "Romania": ("Romanian",),
    "Greenland": ("Greenlandic",),
    "Mongolia": ("Mongolian",),
    "Brazil": ("Brazilian",),
    "Eritrea": ("Eritrean",),
    "Costa Rica": ("Costa Rican",),
    "Myanmar": ("Burma", "Burmese"),
    "Canada": ("Canadian",),
    "Mauritania": ("Mauritanian",),
    "Hungary": ("Hungarian",),
    "Russia": ("Russian",),
    "Sudan": ("Sudanese",),
    "Republic of The Gambia": ("Gambia", "Gambian"),
    "Yemen": ("Yemeni",),
    "Japan": ("Japanese",),
    "Cambodia": ("Cambodian",),
    "United Arab Emirates": ("Emirates", "Emirati"),
    "Paraguay": ("Paraguayan",),
    "Ecuador": ("Ecuadorian",),
    "Sri Lanka": ("Sri Lankan",),
    "Northern Mariana Islands": ("Mariana",),
    "Venezuela": ("Venezuelan",),
    "Laos": ("Laotian", "Lao"),
}

ADMIN_WORDS = (
    "district",
    "province",
    "region",
    "county",
    "oblast",
    "municipality",
    "department",
    "governorate",
    "parish",
)
#: C9: what a first sentence does not open with.
LOCATION_PREPOSITIONS = frozenset(
    """on at in near above below beside inside within beneath under between along across atop
    outside overlooking""".split()
)
BAD_OPENERS = frozenset(
    """located situated set nestled perched standing lying this these here it its they and but
    so""".split()
)
ARTICLES = frozenset({"a", "an", "the"})
SITE_TYPE_NOUNS = frozenset(
    """site settlement town city fort hillfort camp tomb grave cairn barrow dolmen temple monument
    complex ruin ruins""".split()
)
#: C10: a call to action or a word about the video itself; matched as whole words.
CTA_PHRASES = (
    "link",
    "description",
    "comment",
    "subscribe",
    "guess",
    "find out",
    "discover",
    "learn more",
    "watch",
    "click",
    "video",
    "below us",
    "from up here",
)
#: C11: mystery and superlative stems, as regular expressions on a lower-case word (or phrase). A
#: card may use one only where the description holds a match of the same stem.
CLAIM_STEMS: Mapping[str, str] = {
    "mystery": r"\bmyster\w*",
    "enigma": r"\benigm\w*",
    "riddle": r"\briddl\w*",
    "secret": r"\bsecret\w*",
    "unknown": r"\bunknown\b",
    "unexplained": r"\bunexplain\w*",
    "unsolved": r"\bunsolved\b",
    "puzzle": r"\bpuzzl\w*",
    "legend": r"\blegend\w*",
    "lost": r"\blost\b",
    "forgotten": r"\bforgot\w*",
    "hidden": r"\bhidden\b",
    "vanished": r"\bvanish\w*",
    "nobody": r"\bnobody\b",
    "no one": r"\bno one\b",
    "strange": r"\bstrange\w*",
    "eerie": r"\beerie\b",
    "magic": r"\bmagic\w*",
    "curse": r"\bcurs(?:e|ed|es)\b",
    "oldest": r"\boldest\b",
    "largest": r"\blargest\b",
    "first": r"\bfirst\b",
    "only": r"\bonly\b",
    "unique": r"\bunique\b",
    "rare": r"\brare\b",
    "most": r"\bmost\b",
}
#: C12: words that state the present of a site; the checker asks the description for that state.
PRESENT_STATE = (
    r"\bstill\b",
    r"\btoday\b",
    r"\bnow\b",
    r"\bcan see\b",
    r"\bremains? visible\b",
    r"\bwaits? to be seen\b",
)
_ROMAN = re.compile(r"\b[IVXL]{2,}\b")
_FIRST_WORD = re.compile(r"^[^\w]*([\w'’-]+)")


# ------------------------------------------------------------------------------ the site
@dataclass(frozen=True)
class ShortsBasis(C.Basis):
    """A v1 fact basis with what the shorts-v1 rules need beyond the description: every name the
    catalogue stores for the site (`aliases`, C7), how many usable images it has (`pool_images`,
    C14) and up to twelve of their Commons titles, hints for the photo anchors and never a fact."""

    aliases: tuple[str, ...] = ()
    pool_images: int = 0
    image_titles: tuple[str, ...] = ()

    @property
    def shorts_eligible(self) -> bool:
        """C14: the site can be a Short - enough usable images and a long enough description."""
        return eligible(self.pool_images, self.description)

    @property
    def thin(self) -> bool:
        """D3: the description is too short for a card without padding."""
        return len(self.description) < THIN_CHARS


def eligible(pool_images: int, description: str) -> bool:
    """Whether a site with this many usable images and this description can be a Short."""
    return pool_images >= MIN_POOL_IMAGES and len(description) >= MIN_ELIGIBLE_CHARS


def shorts_basis(
    *,
    site_id: str,
    name: str,
    country: str,
    description: str,
    alt_names: Sequence[str],
    pool_images: int,
    image_titles: Sequence[str],
) -> ShortsBasis:
    """The shorts-v1 basis of one site: the v1 basis (`contract.basis`) plus its names and images."""
    base = C.basis(
        site_id=site_id, name=name, country=country, description=description, alt_names=alt_names
    )
    return ShortsBasis(
        site_id=base.site_id,
        name=base.name,
        country=base.country,
        description=base.description,
        sentences=base.sentences,
        forms=base.forms,
        aliases=tuple(sorted(set(alt_names))),
        pool_images=pool_images,
        image_titles=tuple(image_titles),
    )


def thin_proof(site: ShortsBasis) -> None:
    """Refuse a thin decline for a site that is not thin: a writer may decline instead of padding
    (C19), never to avoid a description with enough in it."""
    if not site.thin:
        raise ValueError(
            f"the description is {len(site.description)} characters, at least {THIN_CHARS}: a card "
            "can be written - declining is only for a thin description"
        )


# ------------------------------------------------------------------------------ small readers
def words(text: str) -> list[str]:
    """The words of a text as the captions show them: split on spaces."""
    return text.split()


def first_word(text: str) -> str:
    """The first word of a sentence, lower case, without the quotes and marks before it."""
    found = _FIRST_WORD.match(text)
    return "" if found is None else found.group(1).lower()


def opening(card: str, count: int) -> str:
    """The first `count` words of a card after the name fold: what C16 and the rater compare."""
    return " ".join(fold(card).split()[:count])


def card_sentences(card: str) -> list[str]:
    return [piece.strip() for piece in split_sentences(card) if piece.strip()]


def narration_seconds(card: str) -> float:
    """C6: the estimated narration of `card`, in seconds."""
    base, per_char, per_digit = NARRATION_FIT
    return base + per_char * len(card) + per_digit * sum(ch.isdigit() for ch in card)


def present_state_words(card: str) -> list[str]:
    """C12: the present-state words of the card, for the checker to ask the description about."""
    lowered = card.lower()
    return sorted({m.group(0) for pattern in PRESENT_STATE for m in re.finditer(pattern, lowered)})


def _generic(token: str) -> bool:
    return token in GENERIC_WORDS or token.rstrip("s") in GENERIC_WORDS


def distinctive_tokens(name: str) -> list[str]:
    """The tokens of a name that identify it (C7): alphabetic, three letters or more, not generic.
    A name made only of generic words (`Roman Walls`) has none."""
    tokens = fold(name).split()
    return [t for t in tokens if t.isalpha() and len(t) >= 3 and not _generic(t)]


def country_terms(country: str) -> tuple[str, ...]:
    """C8: the country and the words naming its people."""
    return (country, *COUNTRY_TERMS.get(country, ()))


def name_problems(card: str, name: str, aliases: Sequence[str], country: str) -> list[str]:
    """C7 and C8's country: every way `card` gives the site away. Run at the writer's check, on the
    pilot's cards and again at plan time against the live name and aliases (a name changed since)."""
    found: list[str] = []
    forms = C.name_forms(name, [], "")
    hit = [form for form in forms if names_in(card, [form])]
    if hit:
        found.append("name: the card holds the site's name: " + "; ".join(repr(f) for f in hit))
    for alias in sorted(set(aliases)):
        key = fold(alias)
        if not key or key in {fold(form) for form in forms}:
            continue
        if len(key.split()) == 1 and _generic(key):
            continue  # a single common word, not a name
        if names_in(card, [alias]):
            found.append(f"name: the card holds the alias {alias!r}")
    card_tokens = set(fold(card).split())
    leaked = [t for t in distinctive_tokens(name) if t in card_tokens]
    if leaked:
        found.append("name: the card holds a word of the site's name: " + ", ".join(leaked))
    named = [term for term in country_terms(country) if names_in(card, [term])]
    if named:
        found.append(
            "country: the card holds the country or its people (" + ", ".join(named) + "); the "
            "Short shows the country from its first frame"
        )
    return found


# ------------------------------------------------------------------------------ the rules
def _proper_nouns(site: C.Basis) -> frozenset[str]:
    """The capitalised words of the description that do not open a sentence: a name may be wide."""
    found: set[str] = set()
    for sentence in site.sentences:
        for token in sentence.text.split()[1:]:
            bare = token.strip(".,;:!?\"'()[]“”‘’")
            if bare[:1].isupper():
                found.add(bare)
    return frozenset(found)


def _sentence_problems(pieces: Sequence[str]) -> list[str]:
    found: list[str] = []
    if len(pieces) != SENTENCES:
        found.append(f"sentences: {len(pieces)}; a card is exactly {SENTENCES} sentences")
    for number, piece in enumerate(pieces, start=1):
        if not piece.endswith("."):
            found.append(f"sentences: sentence {number} does not end with a full stop")
    if pieces and not S1_MIN <= len(pieces[0]) <= S1_MAX:
        found.append(f"sentence 1: {len(pieces[0])} characters; it is {S1_MIN}-{S1_MAX}")
    return found


def _number_problems(card: str, s1: str) -> list[str]:
    found: list[str] = []
    count = len(numerals(card))
    digits = sum(ch.isdigit() for ch in card)
    if count > MAX_NUMERALS:
        found.append(f"numbers: {count} numerals; at most {MAX_NUMERALS}")
    if digits > MAX_DIGITS:
        found.append(f"numbers: {digits} digits; at most {MAX_DIGITS}")
    s1_digits = sum(ch.isdigit() for ch in s1)
    if s1_digits > MAX_S1_DIGITS:
        found.append(f"numbers: {s1_digits} digits in sentence 1; at most {MAX_S1_DIGITS}")
    if _ROMAN.search(card):
        found.append("numbers: a Roman numeral - spell a regnal number out ('the Third')")
    return found


def _opener_problems(s1: str) -> list[str]:
    found: list[str] = []
    tokens = s1.split()
    head = first_word(s1)
    following = tokens[1].lstrip("([“\"'") if len(tokens) > 1 else ""
    if head in LOCATION_PREPOSITIONS and not following[:1].isdigit():
        found.append(f"opener: sentence 1 opens with the location word {head!r}")
    if head in BAD_OPENERS:
        found.append(f"opener: sentence 1 opens with {head!r}")
    if head in ARTICLES:
        near = [fold(t) for t in tokens[1:4]]
        typed = [t for t in near if t in SITE_TYPE_NOUNS]
        if typed:
            found.append(f"opener: sentence 1 opens with a bare type label ({head} ... {typed[0]})")
    return found


def _administrative(s1: str) -> list[str]:
    hits = [w for w in ADMIN_WORDS if re.search(rf"\b{w}\b", s1, re.IGNORECASE)]
    if hits:
        return ["address: sentence 1 holds an administrative word: " + ", ".join(hits)]
    return []


def _address_marks(card: str) -> list[str]:
    found: list[str] = []
    if any(mark in card for mark in ("?", "!", "...", "…")):
        found.append("marks: no '?', '!' or ellipsis")
    lowered = card.lower()
    if re.search(r"\byou(?:r|rs|rself)?\b", lowered):
        found.append("address: the card talks to the viewer ('you')")
    called = [p for p in CTA_PHRASES if re.search(rf"\b{re.escape(p)}\b", lowered)]
    if called:
        found.append("cta: no call to action or word about the video: " + ", ".join(called))
    return found


def _claim_word_problems(card: str, description: str) -> list[str]:
    lowered, source = card.lower(), description.lower()
    unsupported = [
        word
        for word, pattern in CLAIM_STEMS.items()
        if re.search(pattern, lowered) and not re.search(pattern, source)
    ]
    if unsupported:
        return [
            "claims: a mystery or superlative word the description does not use: "
            + ", ".join(unsupported)
        ]
    return []


def _caption_problems(card: str, site: C.Basis, fit: C.Fit) -> list[str]:
    proper = _proper_nouns(site)
    found: list[str] = []
    seen: dict[str, int] = {}
    for token in words(card):
        bare = token.strip(".,;:!?\"'()[]“”‘’")
        if not bare or bare in seen:
            continue
        seen[bare] = int(fit("", bare).px)
        limit = PROPER_WORD_PX if bare in proper else COMMON_WORD_PX
        if seen[bare] > limit:
            found.append(
                f"caption: the word {bare!r} is {seen[bare]} px wide, at most {limit} "
                f"({'a proper noun of the description' if bare in proper else 'a common word'})"
            )
    return found


def anchor_problems(card: str, anchors: Sequence[str], site: ShortsBasis) -> list[str]:
    """C14: the photo anchors, copied from the card, in the places the Short cuts its stills."""
    if not site.shorts_eligible:
        return ["anchors: the site is not Shorts-eligible; the anchors are []"] if anchors else []
    if not 1 <= len(anchors) <= MAX_ANCHORS:
        return [f"anchors: {len(anchors)}; a Shorts-eligible card names 1-{MAX_ANCHORS}"]
    found: list[str] = []
    s1 = card_sentences(card)[0] if card_sentences(card) else card
    starts: list[int] = []
    for number, anchor in enumerate(anchors, start=1):
        if card.count(anchor) != 1:
            found.append(f"anchors: anchor {number} ({anchor!r}) is not once in the card verbatim")
            continue
        starts.append(card.index(anchor))
    if found:
        return found
    if starts != sorted(starts):
        found.append("anchors: the anchors are not in the order of the card")
    end = starts[0] + len(anchors[0])
    if not len(s1) - ANCHOR_S1_TAIL <= end <= len(s1):
        found.append(
            f"anchors: anchor 1 ends at character {end}; it ends in the last {ANCHOR_S1_TAIL} "
            f"characters of sentence 1 (characters {len(s1) - ANCHOR_S1_TAIL}-{len(s1)})"
        )
    for number, start in enumerate(starts[1:], start=2):
        if start < ANCHOR_LATER_START:
            found.append(
                f"anchors: anchor {number} starts at character {start}, not before "
                f"{ANCHOR_LATER_START}"
            )
    for before, after in zip(starts, starts[1:], strict=False):
        if after - before < ANCHOR_GAP:
            found.append(
                f"anchors: two anchors start {after - before} characters apart, at least "
                f"{ANCHOR_GAP}"
            )
    return found


def reserve_problems(
    reserve: Sequence[str] | None, basis: Sequence[str], site: C.Basis
) -> list[str]:
    """C15: the reserve is `None` (the card is not `shorts_ready`), or description sentence ids the
    card does not use, or `reveal`, once each."""
    if reserve is None:
        return []
    if not isinstance(reserve, list | tuple) or not reserve:
        return ["reserve: it is null or a non-empty list of sentence ids and 'reveal'"]
    found: list[str] = []
    if len(set(reserve)) != len(reserve):
        found.append("reserve: it names an entry twice")
    for entry in reserve:
        if entry == REVEAL:
            continue
        if entry not in site.described_ids:
            found.append(f"reserve: {entry!r} is not a sentence id of the description")
        elif entry in basis:
            found.append(
                f"reserve: {entry} is a sentence the card rests on; the reserve is held back"
            )
    return found


def problems_shorts(
    card: str,
    site: ShortsBasis,
    anchors: Sequence[str],
    reserve: Sequence[str] | None,
    fit: C.Fit,
    *,
    basis: Sequence[str],
) -> list[str]:
    """Why `card` (final, `contract.final_card`) breaks the mechanical half of shorts-v1; empty
    when it does not. `basis` is the sentence ids the writer says the card rests on."""
    inverted = ("name:", "sentences:", "questions:", "question:")
    found = [
        p
        for p in C.problems(card, site, fit=lambda _name, text: fit("", text))
        if not p.startswith(inverted)
    ]
    pieces = card_sentences(card)
    s1 = pieces[0] if pieces else card
    found += _sentence_problems(pieces)
    found += _number_problems(card, s1)
    if narration_seconds(card) > NARRATION_MAX_S:
        found.append(
            f"narration: about {narration_seconds(card):.1f} s; at most {NARRATION_MAX_S} s "
            "(fewer characters or digits)"
        )
    found += name_problems(card, site.name, site.aliases, site.country)
    found += _administrative(s1)
    found += _opener_problems(s1)
    found += _address_marks(card)
    found += _claim_word_problems(card, site.description)
    found += _caption_problems(card, site, fit)
    found += anchor_problems(card, anchors, site)
    found += reserve_problems(reserve, basis, site)
    return found


def diversity_problems(card: str, taken: Mapping[str, str], total: int) -> list[str]:
    """C16: `card` against the cards the run has already fixed (`taken`: site id -> card) in a run
    of `total` sites: no opening of five words repeats, and no opening of three words occurs in more
    than `OPENING_SHARE` of the run's cards (one occurrence is always allowed)."""
    found: list[str] = []
    five, three = opening(card, 5), opening(card, 3)
    others = list(taken.values())
    if any(opening(other, 5) == five for other in others):
        found.append(f"diversity: another card of the run opens with {five!r}")
    allowed = max(1, int(OPENING_SHARE * total))
    if 1 + sum(1 for other in others if opening(other, 3) == three) > allowed:
        found.append(f"diversity: more than {allowed} card(s) of this run open with {three!r}")
    return found


# ------------------------------------------------------------------------------ the canary
#: The seeded defects of the canary and of the checker's calibration: each adds one flaw a checker
#: must not pass - a removed hedge, an invented superlative, an implied unknown, a wrong period, a
#: word of the name.
DEFECT_KINDS = ("hedge", "superlative", "unknown", "period", "name")
_HEDGES = (
    "possibly",
    "probably",
    "perhaps",
    "believed to be",
    "believed",
    "by one estimate",
    "roughly",
    "about",
    "around",
    "circa",
    "some",
)


def seed_defect(card: str, site: C.Basis, kind: str) -> str:
    """`card` with one seeded flaw of `kind`; `ValueError` when the card has nothing to flaw that
    way (no hedge to remove, no numeral to move)."""
    if kind == "hedge":
        for hedge in _HEDGES:
            pattern = re.compile(rf"\b{re.escape(hedge)}\b ?", re.IGNORECASE)
            if pattern.search(card):
                return pattern.sub("", card, count=1)
        raise ValueError("no hedge in the card to remove")
    if kind == "superlative":
        return f"{card} It is the oldest known example of its kind in the world."
    if kind == "unknown":
        return f"{card} No one knows who built it or why."
    if kind == "period":
        match = re.search(r"\d[\d,]*", card)
        if match is None:
            raise ValueError("no numeral in the card to move")
        moved = str(int(match.group(0).replace(",", "")) + 1000)
        return card[: match.start()] + moved + card[match.end() :]
    if kind == "name":
        token = (distinctive_tokens(site.name) or [site.name])[0]
        return f"{token.capitalize()} stands apart. {card}"
    raise ValueError(f"{kind!r} is not a seeded defect: {DEFECT_KINDS}")


def canary_card(card: str, site: C.Basis, index: int) -> tuple[str, str]:
    """`(kind, defective card)` for the canary question: the defect kinds are tried in a rotation
    that starts at `index`, and the first that applies to the card is used."""
    for step in range(len(DEFECT_KINDS)):
        kind = DEFECT_KINDS[(index + step) % len(DEFECT_KINDS)]
        try:
            return kind, seed_defect(card, site, kind)
        except ValueError:
            continue
    raise ValueError("no seeded defect applies to the card")
