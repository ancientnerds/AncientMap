"""Find the curated site a story is about, from what the story itself says.

The match step (site_matcher.match_sites_for_pending_items) links a story to a
site only through ``site_name_extracted``, by an exact key against every
source. Measured on prod 2026-10-20: of 2,869 public stories (significance
>= 2) 1,183 had no site at all - 840 of them without an extracted name, which
the step never even looks at - and 665 more sat on a bulk-imported site, which
has no page of its own. Search landers: 285 of 547 (52 %) landed on a story
without a site (SEO evaluation 2026-10-19, traffic-1). Only 376 of the 1,184
unlinked stories contain a curated name of four letters or more at all (SQL
over name_normalized, word-bounded, any case). Owner decision 2026-10-20 (C1):
a matcher over the story's own text, a proposal list for the stock that a
person checks line by line, and a journalled writer (story_site_link.py).

What counts as a mention: a curated ``ancient_nerds`` site (not retired) whose
name, label, Wikipedia title or Wikidata alias appears in the story as a run of
words. The fold of each word is Postgres's (``site_key_sql``: lower(unaccent)),
never a Python one - normalize_name() misses ı and ø (site_key.py). On top of
that fold the comparison tolerates what the exact key does not: a leading or
inner "the"/"of"/"a"/"an" ("Great Pyramid of Giza" = "The Great Pyramid of
Giza": 54 public stories sat on a Wikidata copy of it for want of the "The"),
hyphens and apostrophes ("Göbekli-Tepe's").

Rather no link than a wrong one, so a mention must also survive these rules:

* Capitals. A name the story writes in lower case is a common word there
  ("rock art", "temple"); only the words a spelling of the name itself writes
  in lower case may be ("Deir el-Bahari"). A one-word name needs one
  capitalised use that is neither the first word of a sentence nor part of a
  Title Case Headline, and no lower-case use anywhere in the story.
* Country and nationality words never count as a site ("Jordan", "Malta":
  NAME_TO_ISO, the region blocklist, the demonyms).
* A name several curated sites share ("Temple of Apollo": 4) counts only when
  the story names the country of exactly one of them. A name of generic words
  only ("El Castillo"), a one-word Wikidata alias that is not the distinctive
  word of the site's own name, and a name shorter than four letters need that
  country as well: Wikidata's "also known as" holds surnames and city names
  ("Newcastle" for the fort Pons Aelius).
* One site per story. The extracted name decides first; otherwise the one site
  in the headline; otherwise the one site the story names at all, in two
  sentences (or in one, when the video title names it too). Two candidates, or
  a name the story leaves unsettled, give no link. A story whose extracted name
  is some other place takes a site from its headline only ("Wadi Cemetery: 77
  tombs discovered at Giza"), and a headline that measures its subject against
  a site ("older than Sweet Track") is not about that site.

Checked against the 1,005 public stories a person or the identify step had
linked to a curated site: the matcher names a site for 760 of them and the same
one for 727 (95.7 %); most of the other 33 differ in granularity (Giza
Necropolis / The Great Pyramid of Giza) or the existing link is the error
(a "Mausoleum of Qin Shi Huang" story on the Mausoleum of the Atilii).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.lyra.site_key import site_key_sql
from pipeline.lyra.site_matcher import _GENERIC_NAME_BLOCKLIST
from pipeline.utils.country_lookup import (
    ANCIENT_CULTURE_ADJECTIVES,
    ISO_TO_DEMONYMS,
    NAME_TO_ISO,
    SUBNATIONAL_NAME_TO_ISO,
)
from pipeline.utils.public_sites import curated_page

#: raw words -> their match key. The production keyer asks Postgres
#: (postgres_keyer); the tests pass a Python fold.
Keyer = Callable[[Iterable[str]], Mapping[str, str]]

_WORD = re.compile(r"\w+")
#: A name never runs across a sentence or clause break. A full stop after
#: "St"/"Mt"/"Dr" is an abbreviation, not a break ("St. Kilda").
_BREAK = re.compile(r"[!?;:,()\[\]{}\"“”«»|\n]|(?<!\b[A-Z][a-z])\.(?=\s|$)")
#: Words a name may carry or drop without becoming another name.
STOPWORDS = frozenset({"the", "a", "an", "of"})
#: Words that set a place off inside a longer extracted name ("... at Abydos").
CONNECTORS = frozenset({"of", "at", "in", "near", "on", "from", "by", "the"})
#: Words that make a headline site a yardstick rather than the subject.
COMPARISON_CUES = frozenset(
    {
        "than",
        "predating",
        "predate",
        "predates",
        "predated",
        "before",
        "after",
        "like",
        "unlike",
        "vs",
        "versus",
        "resembles",
        "resembling",
        "rivals",
        "rivaling",
        "compared",
        "similar",
    }
)
#: Name types by weight: the site's own name first, Wikidata's aliases last.
_TYPE_RANK = {"site": 0, "label": 1, "wikipedia_title": 2, "wikidata_alias": 3}
_MIN_WORD_LEN = 4
#: A word in the names of this many curated sites is a generic word, and a
#: name made of generic words only ("El Castillo", "Roman Villa", "Great
#: Pyramid") needs the country. Measured on the 2026-10-20 lexicon: el 114,
#: villa 85, pyramid 40, great 29, castillo 18, valley 16 sites - against
#: tepe 11, stonehenge 10, kings 8, giza 6. "El Castillo", a Wikidata alias
#: of the Cave of El Castillo in Spain, otherwise linked a Chichén Itzá story.
GENERIC_SITE_COUNT = 15
#: A segment with at least this many long words, nearly all capitalised, is a
#: Title Case Headline: its capitals say nothing about proper nouns.
_TITLE_CASE_MIN_WORDS = 4
_TITLE_CASE_SHARE = 0.75

#: The fields a story is read from, in the order evidence is quoted.
STORY_FIELDS = ("headline", "summary", "facts", "post_text")
EXTRACTED = "extracted"
VIDEO_TITLE = "video_title"


@dataclass(frozen=True)
class SiteRef:
    site_id: str
    name: str
    country: str | None
    iso: str | None


@dataclass(frozen=True)
class _Entry:
    site: SiteRef
    rank: int
    alias: str
    name_type: str
    #: A one-word alias that is the one distinctive word of the site's own
    #: name: "Cholula" of "Zona Arqueológica de Cholula", "Giza" of "Giza
    #: Necropolis". It needs no country, unlike "Newcastle" for "Pons Aelius"
    #: or "Alexandria" for "Alexandria on Tigris".
    distinctive: bool = False


@dataclass
class Lexicon:
    """Curated names by their word-key tuple."""

    by_key: dict[tuple[str, ...], dict[str, _Entry]] = field(default_factory=dict)
    #: Per name, the words some spelling of it writes in lower case
    #: ("Deir el-Bahari"): a story may write them so too.
    lower_ok: dict[tuple[str, ...], tuple[bool, ...]] = field(default_factory=dict)
    #: Words in the names of at least GENERIC_SITE_COUNT curated sites.
    generic: set[str] = field(default_factory=set)
    #: Country, region and nationality phrases: never a site.
    blocked: set[tuple[str, ...]] = field(default_factory=set)
    #: Country and nationality phrases -> ISO code, for the confirmation.
    countries: dict[tuple[str, ...], str] = field(default_factory=dict)
    max_len: int = 1


@dataclass(frozen=True)
class StoryText:
    headline: str | None = None
    summary: str | None = None
    facts: list[str] | None = None
    post_text: str | None = None
    extracted: str | None = None
    video_title: str | None = None

    def fields(self) -> list[tuple[str, str]]:
        values = {
            EXTRACTED: self.extracted,
            "headline": self.headline,
            "summary": self.summary,
            "facts": "\n".join(f for f in self.facts or [] if isinstance(f, str)),
            "post_text": self.post_text,
            VIDEO_TITLE: self.video_title,
        }
        order = (EXTRACTED, *STORY_FIELDS, VIDEO_TITLE)
        return [(name, values[name]) for name in order if values[name]]


@dataclass(frozen=True)
class StoryMatch:
    site_id: str
    site_name: str
    country: str | None
    #: extracted_name | extracted_name_part | headline | repeated | video_title+text
    reason: str
    #: The curated name the story used and its type, e.g. "Gobekli Tepe (label)".
    via: str
    country_confirmed: bool
    field: str
    snippet: str


@dataclass(frozen=True)
class _Tok:
    key: str
    capital: bool
    proper: bool
    start: int
    end: int


@dataclass
class _Segment:
    field: str
    text: str
    toks: list[_Tok]
    title_case: bool
    #: The field's first clause: "Unfinished Obelisk" of "Unfinished Obelisk, Aswan".
    leading: bool

    def clause(self) -> str:
        """The clause's words, for counting distinct sentences: the summary
        repeats headline and facts word for word."""
        return " ".join(t.key for t in self.toks)


@dataclass
class _Mention:
    entries: dict[str, _Entry]
    key: tuple[str, ...]
    segment: _Segment
    first: int
    last: int

    @property
    def whole_name(self) -> bool:
        """The mention is the extracted name itself, not a part of it."""
        seg = self.segment
        return (
            seg.field == EXTRACTED
            and seg.leading
            and self.first == 0
            and self.last == len(seg.toks) - 1
        )


def _split_keys(raw_words: Iterable[str], keyer: Keyer) -> dict[str, list[str]]:
    """Each raw word -> its key words. A key can hold several words ("½" folds
    to " 1/2"); a key that leaves no word drops out."""
    words = list(dict.fromkeys(raw_words))
    keys = keyer(words)
    return {w: _WORD.findall(keys.get(w) or "") for w in words}


def _phrase(phrase: str, keys: Mapping[str, list[str]]) -> list[tuple[str, bool]]:
    """(key word, written in lower case) per word of the phrase, stopwords dropped."""
    out: list[tuple[str, bool]] = []
    for raw in _WORD.findall(phrase):
        out.extend((k, raw[0].islower()) for k in keys.get(raw, []) if k not in STOPWORDS)
    return out


def _phrase_key(phrase: str, keys: Mapping[str, list[str]]) -> tuple[str, ...]:
    return tuple(k for k, _ in _phrase(phrase, keys))


def _latin(key: tuple[str, ...]) -> bool:
    return all(word.isascii() and word.isalnum() for word in key)


def _country_phrases() -> dict[str, str]:
    """Phrase -> ISO: country names, sub-national names that hold a country
    name ("New Mexico" is the US), and modern nationality words. The ancient
    culture adjectives ("Greek", "Egyptian") name no country: a Greek temple
    stands in Türkiye as often as in Greece."""
    phrases = dict(NAME_TO_ISO)
    phrases.update(SUBNATIONAL_NAME_TO_ISO)
    for iso, demonyms in ISO_TO_DEMONYMS.items():
        for demonym in demonyms:
            if demonym not in ANCIENT_CULTURE_ADJECTIVES:
                phrases.setdefault(demonym, iso)
    return phrases


def build_lexicon(
    rows: Iterable[tuple[str, str, str | None, str, str]],
    keyer: Keyer,
) -> Lexicon:
    """rows = (site_id, site_name, country, name, name_type): every name of
    every curated site, the site's own name as type ``site``."""
    rows = list(rows)
    countries = _country_phrases()
    never = set(countries) | set(_GENERIC_NAME_BLOCKLIST) | set(ANCIENT_CULTURE_ADJECTIVES)
    raw_words = [w for row in rows for w in _WORD.findall(row[3])]
    raw_words += [w for phrase in never for w in _WORD.findall(phrase)]
    keys = _split_keys(raw_words, keyer)

    lex = Lexicon()
    lex.countries = {_phrase_key(p, keys): iso for p, iso in countries.items()}
    lex.countries.pop((), None)
    lex.blocked = {_phrase_key(p, keys) for p in never} - {()}
    own_name: dict[str, tuple[str, ...]] = {}
    for site_id, site_name, country, name, name_type in rows:
        words = _phrase(name, keys)
        key = tuple(k for k, _ in words)
        if not key or not _latin(key) or key in lex.blocked:
            continue
        iso = NAME_TO_ISO.get((country or "").strip().lower())
        entry = _Entry(
            site=SiteRef(str(site_id), site_name, country, iso),
            rank=_TYPE_RANK.get(name_type, len(_TYPE_RANK)),
            alias=name,
            name_type=name_type,
        )
        sites = lex.by_key.setdefault(key, {})
        held = sites.get(entry.site.site_id)
        if held is None or entry.rank < held.rank:
            sites[entry.site.site_id] = entry
        held_lower = lex.lower_ok.get(key, (False,) * len(key))
        lex.lower_ok[key] = tuple(a or b for a, (_, b) in zip(held_lower, words, strict=True))
        lex.max_len = max(lex.max_len, len(key))
        own_name[entry.site.site_id] = _phrase_key(site_name, keys)
    sites_by_word: dict[str, set[str]] = {}
    for key, sites in lex.by_key.items():
        for word in set(key):
            sites_by_word.setdefault(word, set()).update(sites)
    # A word that is a site's whole own name is a place, however many of its
    # parts carry it: 24 curated sites are "House of ..., Pompeii".
    place_names = {
        key[0]
        for key, sites in lex.by_key.items()
        if len(key) == 1 and any(e.rank <= _TYPE_RANK["label"] for e in sites.values())
    }
    lex.generic = {
        w for w, s in sites_by_word.items() if len(s) >= GENERIC_SITE_COUNT
    } - place_names
    plain = lex.generic | {w for phrase in lex.countries for w in phrase}
    for key, sites in lex.by_key.items():
        if len(key) != 1:
            continue
        for site_id, entry in sites.items():
            name_words = own_name[site_id]
            if key[0] in name_words and all(w in plain for w in name_words if w != key[0]):
                sites[site_id] = replace(entry, distinctive=True)
    return lex


def _segments(fields: list[tuple[str, str]], keys: Mapping[str, list[str]]) -> list[_Segment]:
    out: list[_Segment] = []
    for name, value in fields:
        pos, leading = 0, True
        for brk in [*_BREAK.finditer(value), None]:
            end = brk.start() if brk else len(value)
            seg = _segment(name, value, pos, end, keys, leading)
            if seg.toks:
                out.append(seg)
                leading = False
            pos = brk.end() if brk else end
    return out


def _segment(name: str, value: str, start: int, end: int, keys, leading: bool) -> _Segment:
    words = list(_WORD.finditer(value, start, end))
    long_words = [
        w.group() for w in words if len(w.group()) >= _MIN_WORD_LEN and w.group().isalpha()
    ]
    capitals = sum(1 for w in long_words if w[0].isupper())
    title_case = (
        len(long_words) >= _TITLE_CASE_MIN_WORDS and capitals / len(long_words) >= _TITLE_CASE_SHARE
    )
    toks: list[_Tok] = []
    for i, w in enumerate(words):
        raw = w.group()
        capital = raw[0].isupper() or raw[0].isdigit()
        for key in keys.get(raw, []):
            if key in STOPWORDS:
                continue
            toks.append(
                _Tok(
                    key=key,
                    capital=capital,
                    proper=capital and i > 0 and not title_case,
                    start=w.start(),
                    end=w.end(),
                )
            )
    return _Segment(name, value, toks, title_case, leading)


def _scan(segment: _Segment, phrases, max_len: int, fits=None):
    """Longest phrase first, left to right; a phrase consumes its words, so a
    rejected "Temple of Apollo" never leaves a bare "Apollo" behind. A phrase
    the story does not write as a name (``fits``) is no phrase there: in
    "Saqqara necropolis" the shorter "Saqqara" still counts."""
    toks, i = segment.toks, 0
    while i < len(toks):
        for length in range(min(max_len, len(toks) - i), 0, -1):
            key = tuple(t.key for t in toks[i : i + length])
            if key in phrases and (fits is None or fits(key, i, i + length - 1)):
                yield key, i, i + length - 1
                i += length
                break
        else:
            i += 1


def _snippet(segment: _Segment, first: int, last: int, width: int = 90) -> str:
    start, end = segment.toks[first].start, segment.toks[last].end
    lo, hi = max(0, start - width), min(len(segment.text), end + width)
    body = " ".join(segment.text[lo:hi].split())
    return ("…" if lo else "") + body + ("…" if hi < len(segment.text) else "")


def match_story(story: StoryText, lex: Lexicon, keyer: Keyer) -> StoryMatch | None:
    """The one curated site the story is about, or None. See the module docstring."""
    fields = story.fields()
    keys = _split_keys((w for _, v in fields for w in _WORD.findall(v)), keyer)
    segments = _segments(fields, keys)

    texts = [s for s in segments if s.field != EXTRACTED]
    lower_words = {t.key for s in texts for t in s.toks if not t.capital}
    proper_words = {t.key for s in texts for t in s.toks if t.proper}
    isos: set[str] = set()
    for seg in texts:
        for key, first, _last in _scan(seg, lex.countries, 4):
            if seg.title_case or seg.toks[first].capital:
                isos.add(lex.countries[key])

    accepted: list[_Accepted] = []
    unconfirmed: list[_Mention] = []
    for seg in segments:

        def fits(key, first, last, seg=seg):
            return _written_as_name(_Mention(lex.by_key[key], key, seg, first, last), lex)

        for key, first, last in _scan(seg, lex.by_key, lex.max_len, fits):
            mention = _Mention(lex.by_key[key], key, seg, first, last)
            verdict = _accept(mention, lex, isos, lower_words, proper_words)
            if verdict is _UNCONFIRMED:
                unconfirmed.append(mention)
            elif verdict is not None:
                accepted.append(_Accepted(mention, *verdict))
    return _choose(story, accepted, unconfirmed)


@dataclass(frozen=True)
class _Accepted:
    mention: _Mention
    entry: _Entry
    country_confirmed: bool

    @property
    def site_id(self) -> str:
        return self.entry.site.site_id

    @property
    def field(self) -> str:
        return self.mention.segment.field


#: _accept's verdict for a name the story does not tie to one site.
_UNCONFIRMED = object()


def _written_as_name(m: _Mention, lex: Lexicon) -> bool:
    """The story writes the phrase as a name: capitalised, except for the
    words some spelling of the name writes in lower case ("Deir el-Bahari").
    The extracted name is a name field whose capitals are the summarizer's:
    only the whole name is taken as written; a part of it must be a proper
    noun like anywhere else ("Roman villa near Rossett" names no villa). A
    Title Case Headline's capitals prove nothing either way."""
    if m.whole_name or m.segment.title_case:
        return True
    span = m.segment.toks[m.first : m.last + 1]
    lower_ok = lex.lower_ok[m.key]
    return any(t.capital for t in span) and all(
        t.capital or ok for t, ok in zip(span, lower_ok, strict=True)
    )


def _accept(
    m: _Mention,
    lex: Lexicon,
    isos: set[str],
    lower_words: set[str],
    proper_words: set[str],
) -> tuple[_Entry, bool] | object | None:
    """(entry, country confirmed) when the mention counts; _UNCONFIRMED for
    a name whose site the story does not settle (shared, or lacking the
    country it needs); None for no name at all."""
    if m.segment.field == EXTRACTED and not m.whole_name and not _joined_by_connector(m):
        return None
    needs_country = all(word in lex.generic for word in m.key)
    if len(m.key) == 1:
        word = m.key[0]
        if word in lower_words:
            return None
        # The extracted name is a name field: its capital is a proper use.
        if m.segment.field != EXTRACTED and word not in proper_words:
            return None
        alias_only = all(
            e.rank == _TYPE_RANK["wikidata_alias"] and not e.distinctive for e in m.entries.values()
        )
        if len(word) < _MIN_WORD_LEN or alias_only:
            needs_country = True
    entries = list(m.entries.values())
    confirmed = [e for e in entries if e.site.iso and e.site.iso in isos]
    if len(entries) > 1 or needs_country:
        if len(confirmed) != 1:
            return _UNCONFIRMED
        return confirmed[0], True
    return entries[0], bool(confirmed)


def _joined_by_connector(m: _Mention) -> bool:
    """A part of the extracted name is a place of its own only where a
    connector or a clause break sets it off: "Pyramid of Ahmose I at Abydos",
    "Black Pyramid of Dashur", "Unfinished Obelisk, Aswan". Glued to another
    proper name it is a modifier of that name: "Abri Lartet" is no "Abri"
    (a Wikidata alias of the Cro-Magnon shelter), "Renning's Wood Bone Cave"
    no "Bone Cave" in Tasmania."""
    toks, text_ = m.segment.toks, m.segment.text
    if m.first > 0:
        before = _WORD.findall(text_[toks[m.first - 1].start : toks[m.first].start])
        # Empty only inside one raw word that folds to several ("½"): glued.
        if not before or before[-1].lower() not in CONNECTORS:
            return False
    if m.last + 1 < len(toks):
        after = _WORD.findall(text_[toks[m.last].end : toks[m.last + 1].end])
        if not after or after[0].lower() not in CONNECTORS:
            return False
    return True


def _compared(m: _Mention) -> bool:
    """The mention follows a comparison word within three words. Hyphens go
    first: "pre-dating" is one word."""
    seg = m.segment
    before = _WORD.findall(re.sub(r"[-‐‑]", "", seg.text[: seg.toks[m.first].start]))[-3:]
    return any(w.lower() in COMPARISON_CUES for w in before)


def _choose(
    story: StoryText, accepted: list[_Accepted], unconfirmed: list[_Mention]
) -> StoryMatch | None:
    order = (EXTRACTED, *STORY_FIELDS, VIDEO_TITLE)

    def result(site_id: str, reason: str) -> StoryMatch:
        hits = [a for a in accepted if a.site_id == site_id]
        best = min(hits, key=lambda a: (order.index(a.field), a.entry.rank))
        m = best.mention
        return StoryMatch(
            site_id=site_id,
            site_name=best.entry.site.name,
            country=best.entry.site.country,
            reason=reason,
            via=f"{best.entry.alias} ({best.entry.name_type})",
            country_confirmed=any(a.country_confirmed for a in hits),
            field=m.segment.field,
            snippet=_snippet(m.segment, m.first, m.last),
        )

    # A headline that measures its subject against a site is not about that
    # site: "Neolithic trackway in Somerset is 1,000 years older than Sweet
    # Track", "Nabta Playa ... predating Stonehenge". Such a site drops out of
    # the story entirely. Prototype over the 2026-10-20 stock: 9 of the 32
    # headline picks for stories linked to a bulk-imported site were such
    # yardsticks.
    compared = {a.site_id for a in accepted if a.field == "headline" and _compared(a.mention)}
    accepted = [a for a in accepted if a.site_id not in compared]
    # A name the story does not tie to one site still names a place, and it
    # blocks every rule it competes with: "1,500 bodies found in Pompeii and
    # Herculaneum" with an unsettled "Pompeii" is no Herculaneum story.
    unsettled = [m for m in unconfirmed if not (m.segment.field == "headline" and _compared(m))]
    if any(m.whole_name for m in unsettled):
        return None

    in_name = {a.site_id for a in accepted if a.field == EXTRACTED}
    if in_name:
        if len(in_name) > 1:
            return None
        (site_id,) = in_name
        whole = any(a.mention.whole_name for a in accepted)
        return result(site_id, "extracted_name" if whole else "extracted_name_part")

    in_headline = {a.site_id for a in accepted if a.field == "headline"}
    if (story.extracted or "").strip():
        # The story is about another (named) place: a site in its headline is
        # where that place lies only under a name of the site's own or with the
        # country named. A one-word Wikidata alias alone is too weak there:
        # "28,000-year-old cave lion cub named Sparta found in Siberian
        # permafrost" (extracted "Saka Republic") is no story of Ancient Sparta.
        strong = {
            a.site_id
            for a in accepted
            if a.field == "headline"
            and (
                a.country_confirmed
                or len(a.mention.key) > 1
                or a.entry.rank < _TYPE_RANK["wikidata_alias"]
            )
        }
        if in_headline - strong:
            return None
    headline_unsettled = any(m.segment.field == "headline" for m in unsettled)
    if len(in_headline) == 1 and not headline_unsettled:
        return result(next(iter(in_headline)), "headline")
    if in_headline or headline_unsettled or (story.extracted or "").strip():
        # Two sites in the headline, or a story about another (named) place
        # that mentions a curated site only in its body.
        return None

    # The body alone names a site in passing as often as it names the topic
    # ("artifacts from Babylon, Nimrud, Nineveh and Dur Sharrukin"; "a
    # researcher in Newcastle" for the fort Pons Aelius). It counts only when
    # it is the one curated site the story names, under a name of its own, not
    # a Wikidata alias, and twice (or once, with the video title).
    body = [a for a in accepted if a.field in STORY_FIELDS]
    if len({a.site_id for a in body}) != 1:
        return None
    if any(m.segment.field in STORY_FIELDS for m in unsettled):
        return None
    site_id = body[0].site_id
    if all(a.entry.rank == _TYPE_RANK["wikidata_alias"] for a in body):
        return None
    if len({a.mention.segment.clause() for a in body}) >= 2:
        return result(site_id, "repeated")
    if any(a.field == VIDEO_TITLE and a.site_id == site_id for a in accepted):
        return result(site_id, "video_title+text")
    return None


# --- Postgres side -----------------------------------------------------------

_KEY_BATCH = 5000


def postgres_keyer(session: Session) -> Keyer:
    """Key words with the expression the name columns are built with
    (site_key.py), in batches, cached for the life of the keyer."""
    cache: dict[str, str] = {}

    def key(words: Iterable[str]) -> Mapping[str, str]:
        missing = sorted({w for w in words if w not in cache})
        for start in range(0, len(missing), _KEY_BATCH):
            chunk = missing[start : start + _KEY_BATCH]
            rows = session.execute(
                text(f"SELECT w, {site_key_sql('w')} FROM unnest(CAST(:words AS text[])) AS w"),
                {"words": chunk},
            ).fetchall()
            cache.update({row[0]: row[1] for row in rows})
        return cache

    return key


LEXICON_SQL = f"""
    SELECT u.id, u.name, u.country, u.name, 'site'
    FROM unified_sites u
    WHERE {curated_page("u")}
    UNION ALL
    SELECT u.id, u.name, u.country, usn.name, usn.name_type
    FROM unified_site_names usn JOIN unified_sites u ON u.id = usn.site_id
    WHERE {curated_page("u")}
"""


class StorySiteMatcher:
    """The lexicon loaded once, then one match per story."""

    def __init__(self, session: Session):
        self.keyer = postgres_keyer(session)
        rows = session.execute(text(LEXICON_SQL)).fetchall()
        self.lexicon = build_lexicon((tuple(r) for r in rows), self.keyer)

    def match(self, story: StoryText) -> StoryMatch | None:
        return match_story(story, self.lexicon, self.keyer)

    def match_item(self, item) -> StoryMatch | None:
        """A NewsItem, with the title of its video."""
        return self.match(story_text_of(item, item.video.title if item.video else None))


def story_text_of(item, video_title: str | None) -> StoryText:
    """A NewsItem's fields as the matcher reads them."""
    return StoryText(
        headline=item.headline,
        summary=item.summary,
        facts=item.facts if isinstance(item.facts, list) else None,
        post_text=item.post_text,
        extracted=item.site_name_extracted,
        video_title=video_title,
    )
