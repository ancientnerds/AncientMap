"""S5 VERIFY: the independent verifier, rules V1-V15 (WB-C2).

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` ("Phases 4 and
5, final design"), section verification, "DETERMINISTIC VERIFIER", and
`docs/procedures/PHASE4_CONTRACTS.md` sections 2-5. `verify_site` re-derives every published byte
of one site from the pinned source files, the provenance and the published strings; every rule
that fails becomes one `model4.Hold` under its rule id (`HoldReason.V1` ... `V15`). An empty
result means V1-V15 pass.

Independence
------------
This module never imports `phase4/assemble.py` and was written without reading it (an AST scan in
`tests/remediation/test_phase4_verify.py` proves the first half). The span finder and the closed
edit list below are this module's own reading of the design text; `phase4/sentences.py` (WB-B2)
and `phase4/assemble.py` (WB-B3) hold the other reading. Before the pilot the orchestrator runs
both finders over the same pools (`offered_spans` here); any difference is a contract bug, fixed
in the reading, never by importing one from the other.

The reading, spelled out (offsets are `str` indices into the pinned text, ranges half-open)
------------------------------------------------------------------------------------------
Final punctuation of a sentence: the trailing run `[.!?]+` plus any closing quotes after it.

Deletable spans, each range exactly what is removed (contract section 3: "edit 1 is remove the
range"), only at bracket depth 0 for the comma and dash kinds:

* `p` - a balanced `( ... )`, with the one space before it; at the sentence start, with the one
  space after it; with neither, the bare parenthesis.
* `a` - a paired-comma insertion `, X,` between two consecutive delimiter commas (a comma followed
  by whitespace, so `2,500` is no delimiter), both commas included: `S, X, lies` -> `S lies`.
  A paired-dash insertion ` - X -` (en or em dash, spaced on both sides), from the space before
  the first dash through the second dash. An unspaced `-X-` pair is not offered: removing it
  cannot leave a space between the words it joined.
* `t` - the last comma segment: from the last delimiter comma to the final punctuation, which
  stays. The design's own example, `a1=", whose tomb lies nearby"`, is this range; which kind
  letter it carries does not matter to V4, which compares ranges.
* `l` - a leading phrase of at most 6 whitespace tokens before the first delimiter comma, with
  that comma and the one whitespace character after it.

A span that contains a protected token (`model4.PROTECTED_TOKENS`) is never offered. A token
matches case-insensitively as a whole word (`(?<!\\w)` before, `(?!\\w)` after); `stem*` matches
any word that starts with the stem; a phrase matches its words separated by whitespace; `c.` and
`ca.` match with their full stop and no word character before them, so `B.C.` carries `c.`.

The closed edit list: (1) remove every drop range, (2) collapse runs of spaces to one, (3) `' ,'`
-> `','`, (4) when a drop starts at the sentence start, upper-case the first character, (5) insert
`' [n]'` before the final punctuation. Edits 2 and 3 apply to the whole sentence, not only at a
cut. Published sentences are joined by one space. A card item is edits 1-4 on its own (full)
drop list, then the spoken form `c.`/`ca.` before a number -> `circa ` (`Circa ` for a capital);
items are joined by one space and carry no marker.

What the verifier cannot see
----------------------------
`verify_site` gets the raw `src.<id>.meta` objects, the pinned texts and the quotes, not the
Wikidata entity, so V6's "Wikidata labels count for a strong own verdict" is read as the article
title only (a stricter name set). T03 parses English, so V11's year comparison by interval runs
for lane R (English pages); lane T compares numerals only. V10's "unattributed" superlative has
no attribution rule in the design; every listed superlative is refused (stricter).

Card scope
----------
V10, the card half of V4, V13 and V15 hold the card only (`HoldScope.CARD`): the description
can still be written, with a provenance whose `card` is null, which this module then verifies
again. Everything else holds the site.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from census.model import Severity
from census.tests import t03_years_in_text as T03
from census.tests import t08_citation_markers as T08
from phase3 import discover_stage as DS
from phase3 import fetch_stage as F
from phase3.run import InputError, _single_batch
from rapidfuzz import fuzz

from phase4 import model4 as M
from pipeline.lyra.text_sentences import is_complete_sentence
from pipeline.utils.country_lookup import NAME_TO_ISO, country_name_variants
from pipeline.utils.text import normalize_for_search, normalize_name
from pipeline.video import shorts_audit, shorts_brand
from pipeline.video.shorts_render import W as FRAME_WIDTH

# --------------------------------------------------------------------------------------------
# The design's numbers
# --------------------------------------------------------------------------------------------

#: V5: a published sentence (without its marker) is 25-400 characters long.
SENTENCE_MIN, SENTENCE_MAX = 25, 400
#: V9: the description without markers is 200-1,100 characters and at least half the stored one.
DESCRIPTION_MIN, DESCRIPTION_MAX = 200, 1100
STORED_FLOOR = 0.5
#: V9's floor is waived where Phase 3 or T03 proved the stored text defective.
FLOOR_WAIVERS = frozenset({M.SiteFlag.CLEARED_DESCRIPTION_DEFECT, M.SiteFlag.T03_SEVERE})
#: V10: 80-200 characters (the S2 floor and the varchar(200) column).
CARD_MIN, CARD_MAX = 80, 200
#: V10: every caption word fits 1080 - 2 x 40 px (S3).
MAX_CAPTION_PX = FRAME_WIDTH - 2 * shorts_audit.CAPTION_MARGIN
#: V6: the directional name match, rapidfuzz `partial_ratio` on the normalised name.
NAME_MATCH = 90
#: V11: no run of this many words shared with a restricted page.
NO_COPY_WORDS = 8
#: V1: the one licence W, S and T may publish from.
WIKIPEDIA_LICENCE = M.Licence.CC_BY_SA_4

#: V5: the artefacts of a bad extract or a bad cut.
ARTEFACTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("'=='", re.compile(r"==")),
    ("'listen'", re.compile(r"(?<!\w)listen(?!\w)", re.IGNORECASE)),
    ("an empty '()'", re.compile(r"\(\s*\)")),
    ("'( ;'", re.compile(r"\(\s*;")),
    ("'displaystyle'", re.compile(r"displaystyle", re.IGNORECASE)),
    ("doubled punctuation", re.compile(r"[,;:]\s*[,;:.!?]|(?<!\.)\.\.(?!\.)|[!?]{2,}")),
)
#: V10: the closed list of evaluative superlatives.
SUPERLATIVES = (
    "one of the most",
    "most important",
    "most significant",
    "most famous",
    "most remarkable",
    "finest",
    "best-known",
)
#: V15: the injection tells.
INJECTION_TELLS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+previous",
        r"(?<!\w)as\s+an\s+AI(?!\w)",
        r"system\s+prompt",
        r"(?<!\w)instructions(?!\w)",
    )
)
#: V14: a sentence that says where the site is.
LOCATION_VERB = re.compile(
    r"(?<!\w)(?:located|situated|lie|lies|lay|lying|stand|stands|stood|sit|sits)(?!\w)",
    re.IGNORECASE,
)

#: The rule ids, in the order the rules run.
V_REASONS = (
    M.HoldReason.V1,
    M.HoldReason.V2,
    M.HoldReason.V3,
    M.HoldReason.V4,
    M.HoldReason.V5,
    M.HoldReason.V6,
    M.HoldReason.V7,
    M.HoldReason.V8,
    M.HoldReason.V9,
    M.HoldReason.V10,
    M.HoldReason.V11,
    M.HoldReason.V12,
    M.HoldReason.V13,
    M.HoldReason.V14,
    M.HoldReason.V15,
)

#: V14's report for the A3/B2 lanes, one V14 hold per line, beside `holds.jsonl`. A report, never a
#: write. Proposed for `model4`'s run-directory names (WB-00 owns them).
FIELD_CONFLICTS_FILE = "field_conflicts.jsonl"

SITE = M.HoldScope.SITE
CARD = M.HoldScope.CARD

# --------------------------------------------------------------------------------------------
# The span finder (this module's own; see the module docstring)
# --------------------------------------------------------------------------------------------

_FINAL = re.compile(r"[.!?]+[\"'”’»]*\Z")
_DASHES = "–—"


def final_start(text: str, start: int, end: int) -> int:
    """Where the final punctuation of `text[start:end]` begins; `end` when it has none."""
    match = _FINAL.search(text, start, end)
    return match.start() if match else end


def _parentheses_and_depth(
    text: str, start: int, end: int
) -> tuple[list[tuple[int, int]], list[int]]:
    """The balanced `(`...`)` pairs of the sentence, and the bracket depth at every index.

    `[` and `]` count for the depth but offer no span. A closing bracket without its opener is
    ignored, so an unbalanced sentence offers fewer spans, never a range that cuts a bracket.
    """
    pairs: list[tuple[int, int]] = []
    depth: list[int] = []
    stack: list[tuple[str, int]] = []
    for index in range(start, end):
        char = text[index]
        if char in "([":
            stack.append((char, index))
        elif char in ")]" and stack and stack[-1][0] == ("(" if char == ")" else "["):
            opener, at = stack.pop()
            if opener == "(":
                pairs.append((at, index))
        depth.append(len(stack))
    return pairs, depth


def candidate_spans(text: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    """Every p/a/t/l range of the sentence `text[start:end]`, protected or not, sorted."""
    final = final_start(text, start, end)
    pairs, depth = _parentheses_and_depth(text, start, end)
    found: set[tuple[int, int]] = set()

    for opener, closer in pairs:
        if opener > start and text[opener - 1] == " ":
            found.add((opener - 1, closer + 1))
        elif opener == start and closer + 1 < end and text[closer + 1] == " ":
            found.add((opener, closer + 2))
        else:
            found.add((opener, closer + 1))

    commas = [
        i
        for i in range(start, final)
        if text[i] == "," and i + 1 < end and text[i + 1].isspace() and depth[i - start] == 0
    ]
    for first, second in zip(commas, commas[1:], strict=False):
        if text[first + 1 : second].strip():
            found.add((first, second + 1))

    dashes = [
        i
        for i in range(start + 1, final - 1)
        if text[i] in _DASHES
        and text[i - 1] == " "
        and text[i + 1] == " "
        and depth[i - start] == 0
    ]
    for first, second in zip(dashes, dashes[1:], strict=False):
        if text[first + 1 : second].strip():
            found.add((first - 1, second + 1))

    if commas:
        last = commas[-1]
        if text[last + 1 : final].strip():
            found.add((last, final))
        first = commas[0]
        tokens = text[start:first].split()
        if 1 <= len(tokens) <= 6 and first + 2 < final:
            found.add((start, first + 2))
    return tuple(sorted(found))


def _protected_pattern(entry: str) -> re.Pattern[str]:
    if entry.endswith("*"):
        body, tail = re.escape(entry[:-1]) + r"\w*", ""
    elif entry.endswith("."):
        body, tail = re.escape(entry), ""
    else:
        body, tail = r"\s+".join(re.escape(word) for word in entry.split()), r"(?!\w)"
    return re.compile(r"(?<!\w)" + body + tail, re.IGNORECASE)


_PROTECTED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (entry, _protected_pattern(entry))
    for entries in M.PROTECTED_TOKENS.values()
    for entry in entries
)


def protected_in(span_text: str) -> tuple[str, ...]:
    """The protected-token entries `span_text` contains (hedges, negations, contrast, ...)."""
    return tuple(entry for entry, pattern in _PROTECTED if pattern.search(span_text))


def offered_spans(text: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    """The ranges the selector may drop from the sentence `text[start:end]`: the parity surface
    the orchestrator compares with `phase4/sentences.py` before the pilot."""
    return tuple(
        (low, high)
        for low, high in candidate_spans(text, start, end)
        if not protected_in(text[low:high])
    )


# --------------------------------------------------------------------------------------------
# The closed edit list (this module's own)
# --------------------------------------------------------------------------------------------

_SPACES = re.compile(r" {2,}")
_CIRCA = re.compile(r"(?<![\w.])([Cc])a?\.\s*(?=\d)")


def edited(text: str, start: int, end: int, drop: Sequence[tuple[int, int]]) -> str:
    """Edits 1-4 on the sentence `text[start:end]` with its (sorted) drop ranges."""
    pieces: list[str] = []
    position = start
    for low, high in drop:
        pieces.append(text[position:low])
        position = high
    pieces.append(text[position:end])
    out = _SPACES.sub(" ", "".join(pieces))
    out = out.replace(" ,", ",")
    if drop and drop[0][0] == start and out[:1].islower():
        out = out[0].upper() + out[1:]
    return out


def marked(sentence: str, n: int) -> str | None:
    """Edit 5: `' [n]'` before the final punctuation; `None` when the sentence has none."""
    match = _FINAL.search(sentence)
    if match is None or match.start() == 0:
        return None
    return f"{sentence[: match.start()]} [{n}]{sentence[match.start() :]}"


def spoken(text: str) -> str:
    """The card's one non-source edit: `c.`/`ca.` before a number -> `circa ` (V10)."""
    return _CIRCA.sub(lambda m: "Circa " if m.group(1) == "C" else "circa ", text)


@dataclass(frozen=True)
class Segment:
    """One published sentence as the description carries it: body, marker number, final."""

    body: str
    n: int
    final: str

    @property
    def text(self) -> str:
        """The sentence without its marker."""
        return self.body + self.final


_SEGMENT = re.compile(
    r"(?P<body>.+?) \[(?P<n>[1-9][0-9]*)\](?P<final>[.!?]+[\"'”’»]*)(?= |\Z)",
    re.DOTALL,
)


def split_published(description: str) -> tuple[Segment, ...] | None:
    """The description as marker-terminated sentences joined by one space; `None` when it is not
    that shape (a sentence without a marker, a marker not before final punctuation)."""
    segments: list[Segment] = []
    position = 0
    while position < len(description):
        match = _SEGMENT.match(description, position)
        if match is None:
            return None
        segments.append(Segment(match["body"], int(match["n"]), match["final"]))
        position = match.end() + (1 if match.end() < len(description) else 0)
    return tuple(segments) if segments else None


_MARKERS = re.compile(r"\s?\[\d+\]")


def without_markers(text: str) -> str:
    """The text a reader measures: every `[n]` marker and the space before it removed."""
    return _MARKERS.sub("", text)


# --------------------------------------------------------------------------------------------
# Names, headings and countries
# --------------------------------------------------------------------------------------------


def name_in(name: str, text: str) -> bool:
    """Directional: the normalised `name` lies inside the normalised `text` (partial_ratio >= 90
    with the name the shorter side). `token_set_ratio` is never used: a bare 'Kilmartin' must
    not match 'Kilmartin Glen standing stones' the other way round."""
    needle, haystack = normalize_for_search(name), normalize_for_search(text)
    if not needle or len(needle) > len(haystack):
        return False
    return fuzz.partial_ratio(needle, haystack) >= NAME_MATCH


_HEADING = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$", re.MULTILINE)


def heading_before(text: str, position: int) -> str | None:
    """The section heading (`== History ==` in a TextExtracts plain text) a position sits under."""
    heading = None
    for match in _HEADING.finditer(text, 0, position):
        heading = match.group(2)
    return heading


_COUNTRY = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(name) for name in sorted(NAME_TO_ISO, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)


def countries_named(text: str) -> list[str]:
    """Country names (`country_lookup.NAME_TO_ISO`) written as proper nouns, longest first."""
    return [m.group(0) for m in _COUNTRY.finditer(text) if m.group(0)[0].isupper()]


def _iso(name: str | None) -> str | None:
    return NAME_TO_ISO.get(name.strip().lower()) if name else None


# --------------------------------------------------------------------------------------------
# V10's font seam: the card measured as the short renders it
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CardFit:
    """S3 and S4 of the shorts gate for one card."""

    missing: tuple[str, ...]  #: characters the heading font cannot draw
    widest: str  #: the widest caption word, as shown
    px: int  #: its width in pixels, outline included


def card_fit(name: str, card: str) -> CardFit:
    """The card through the shorts' own helpers: the heading font for name + card
    (`shorts_brand.heading_font`), its missing glyphs, and `shorts_audit.widest_word_px` over the
    caption words (`card.split()`, as `shorts_captions` aligns them). Needs the brand fonts
    (`video-assets/fonts`, gitignored; `shorts_brand.ensure_fonts` fetches them once)."""
    shown = f"{name} {card}"
    font = shorts_brand.heading_font(shown)
    missing = shorts_brand.missing_glyphs(shown, shorts_brand.font_cmap(font))
    widest, px = shorts_audit.widest_word_px(card.split(), shorts_audit.caption_font(font))
    return CardFit(missing=tuple(missing), widest=widest, px=px)


# --------------------------------------------------------------------------------------------
# One site's case
# --------------------------------------------------------------------------------------------

Problem = tuple[M.HoldScope, str]


@dataclass(frozen=True)
class _Case:
    site: M.PlanSite
    assembly: M.Assembly
    metas: Mapping[str, Mapping[str, Any]]
    texts: Mapping[str, str]
    quotes: tuple[str, ...]
    new_raw_data: Any
    segments: tuple[Segment, ...] | None

    @property
    def provenance(self) -> M.Provenance:
        return self.assembly.provenance

    @property
    def sentences(self) -> tuple[M.PublishedSentence, ...]:
        return self.assembly.provenance.sentences

    @property
    def lane(self) -> M.Lane:
        return self.assembly.provenance.lane

    @property
    def published(self) -> tuple[Segment, ...] | None:
        """The published sentences, when the description splits into exactly one per provenance
        sentence; `None` otherwise (V3 and V8 say so, and the per-sentence rules cannot run)."""
        if self.segments is None or len(self.segments) != len(self.sentences):
            return None
        return self.segments

    def text_of(self, source_id: str) -> str | None:
        return self.texts.get(source_id)

    def gate(self, source_id: str) -> Mapping[str, Any] | None:
        meta = self.metas.get(source_id)
        gate = meta.get("subject_gate") if isinstance(meta, Mapping) else None
        return gate if isinstance(gate, Mapping) else None

    def card_sentence_items(self) -> list[tuple[M.CardItem, M.PublishedSentence]]:
        card = self.provenance.card
        if card is None:
            return []
        return [(item, self.sentences[item.sentence]) for item in card.items]


def _strong_own(gate: Mapping[str, Any] | None) -> bool:
    """V6: the article title counts only for a strong 'own' verdict: QID + coordinates + not a
    place-level item."""
    return (
        gate is not None
        and gate.get("verdict") == M.SubjectVerdict.OWN.value
        and gate.get("qid_match") is True
        and gate.get("km") is not None
        and gate.get("place_item") is False
    )


# --------------------------------------------------------------------------------------------
# V1 pin
# --------------------------------------------------------------------------------------------


def _deny_family(url: str) -> str | None:
    """Track A's deny list (`phase4/licences.py`, WB-A2): the family that denies `url`, or `None`.

    Imported here, not at the top: the verifier is built in parallel with Track A, and a module
    that cannot be imported would take every lane's verification down with lane R's."""
    from phase4 import licences

    return licences.deny_family(url)


def is_permalink(url: Any, *, lang: str, revid: Any) -> bool:
    """`https://<lang>.wikipedia.org/w/index.php?title=<T>&oldid=<revid>`: exactly those two
    parameters, a non-empty title and the pinned revision."""
    if not isinstance(url, str) or type(revid) is not int:
        return False
    parts = urlsplit(url)
    try:
        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.netloc == f"{lang}.wikipedia.org"
        and parts.path == "/w/index.php"
        and not parts.fragment
        and set(query) == {"title", "oldid"}
        and len(query["title"]) == 1
        and bool(query["title"][0].strip())
        and query["oldid"] == [str(revid)]
    )


_LANE_KINDS: Mapping[M.Lane, frozenset[M.SourceKind]] = {
    M.Lane.W: frozenset({M.SourceKind.W}),
    M.Lane.S: frozenset({M.SourceKind.W}),
    M.Lane.T: frozenset({M.SourceKind.T}),
    M.Lane.R: frozenset({M.SourceKind.R}),
}


def _v1(c: _Case) -> list[Problem]:
    problems: list[str] = []
    kinds = {M.source_kind(ref.id) for ref in c.provenance.sources}
    if kinds != _LANE_KINDS[c.lane]:
        problems.append(
            f"lane {c.lane.value} cites {sorted(k.value for k in kinds)}, it publishes from "
            f"{sorted(k.value for k in _LANE_KINDS[c.lane])} only"
        )
    for ref in c.provenance.sources:
        meta, text = c.metas.get(ref.id), c.texts.get(ref.id)
        if not isinstance(meta, Mapping) or text is None:
            problems.append(f"{ref.id}: no pinned meta and text in the store")
            continue
        pinned = meta.get("sha256_text")
        if meta.get("id") != ref.id:
            problems.append(f"{ref.id}: the meta names source {meta.get('id')!r}")
        if M.text_sha256(text) != pinned:
            problems.append(
                f"{ref.id}: the stored text hashes to {M.text_sha256(text)[:16]}, the meta pins "
                f"{str(pinned)[:16]}"
            )
        if ref.text_sha256 != pinned:
            problems.append(f"{ref.id}: provenance pins {ref.text_sha256[:16]}, the meta another")
        if meta.get("licence") != ref.licence.value:
            problems.append(f"{ref.id}: provenance says {ref.licence.value}, the meta otherwise")
        if M.source_kind(ref.id) is M.SourceKind.R:
            problems.extend(_v1_restricted(ref, meta))
        else:
            problems.extend(_v1_wikipedia(ref, meta))
    attributed = [ref for ref in c.provenance.sources if ref.url == c.provenance.attribution.url]
    if attributed and M.source_kind(attributed[0].id) is not M.SourceKind.R:
        title = c.metas.get(attributed[0].id, {}).get("title")
        if c.provenance.attribution.title != title:
            problems.append(
                f"attribution names {c.provenance.attribution.title!r}, the article is {title!r}"
            )
    return [(SITE, problem) for problem in problems]


def _v1_wikipedia(ref: M.SourceRef, meta: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    revid, lastrevid = meta.get("revid"), meta.get("lastrevid")
    if type(revid) is not int or type(lastrevid) is not int:
        problems.append(f"{ref.id}: revid {revid!r} / lastrevid {lastrevid!r} is not an integer")
    elif revid != lastrevid:
        problems.append(f"{ref.id}: revid {revid} is not lastrevid {lastrevid}")
    lang = "en" if ref.id == "W" else ref.id[2:]
    permalink = meta.get("permalink")
    if not is_permalink(permalink, lang=lang, revid=revid):
        problems.append(f"{ref.id}: {permalink!r} is not the oldid permalink of revision {revid}")
    if ref.url != permalink:
        problems.append(f"{ref.id}: provenance links {ref.url!r}, not the pinned permalink")
    if ref.revid != revid or ref.rev_timestamp != meta.get("rev_timestamp"):
        problems.append(f"{ref.id}: provenance pins another revision than the meta")
    if meta.get("licence") != WIKIPEDIA_LICENCE.value:
        problems.append(
            f"{ref.id}: licence {meta.get('licence')!r}; lanes W, S and T publish from "
            f"{WIKIPEDIA_LICENCE.value} Wikipedia only"
        )
    return problems


def _v1_restricted(ref: M.SourceRef, meta: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if meta.get("licence") != M.Licence.RESTRICTED.value:
        problems.append(f"{ref.id}: licence {meta.get('licence')!r}; lane R pages are restricted")
    final_url = meta.get("final_url")
    if ref.url != final_url:
        problems.append(f"{ref.id}: provenance links {ref.url!r}, the page ended at {final_url!r}")
    if ref.revid is not None:
        problems.append(f"{ref.id}: a restricted page has no revision, provenance pins one")
    for url in (meta.get("url"), final_url):
        if not isinstance(url, str):
            problems.append(f"{ref.id}: {url!r} is not a URL")
            continue
        family = _deny_family(url)
        if family is not None:
            problems.append(f"{ref.id}: {url} is on the deny list ({family})")
    return problems


# --------------------------------------------------------------------------------------------
# V2 quote, V3 assembly, V4 drop legality
# --------------------------------------------------------------------------------------------


def _v2(c: _Case) -> list[Problem]:
    problems: list[str] = []
    if len(c.quotes) != len(c.sentences):
        problems.append(f"{len(c.quotes)} quote(s) for {len(c.sentences)} published sentence(s)")
        return [(SITE, problem) for problem in problems]
    for index, (sentence, quote) in enumerate(zip(c.sentences, c.quotes, strict=True), 1):
        text = c.text_of(sentence.src)
        if text is None:
            problems.append(f"sentence {index}: no pinned text for {sentence.src}")
            continue
        if sentence.end > len(text):
            problems.append(f"sentence {index}: [{sentence.start}:{sentence.end}) leaves the text")
            continue
        if unicodedata.normalize("NFC", text[sentence.start : sentence.end]) != quote:
            problems.append(f"sentence {index}: the source slice is not the quote {quote[:60]!r}")
        if not DS.quote_occurs(quote, text):
            problems.append(f"sentence {index}: the quote does not occur in {sentence.src}")
    return [(SITE, problem) for problem in problems]


def expected_sentences(c: _Case) -> list[str | None]:
    """Lanes W and S: every published sentence as this module's own edit list builds it."""
    out: list[str | None] = []
    for sentence in c.sentences:
        text = c.text_of(sentence.src)
        if text is None:
            out.append(None)
            continue
        out.append(marked(edited(text, sentence.start, sentence.end, sentence.drop), sentence.n))
    return out


def _v3(c: _Case) -> list[Problem]:
    problems: list[str] = []
    if c.published is None:
        found = "no" if c.segments is None else str(len(c.segments))
        problems.append(
            f"the description splits into {found} marker-terminated sentence(s), provenance "
            f"lists {len(c.sentences)}"
        )
        return [(SITE, problem) for problem in problems]
    if c.lane in (M.Lane.W, M.Lane.S):
        expected = expected_sentences(c)
        for index, (want, got) in enumerate(zip(expected, c.published, strict=True), 1):
            if want is None:
                problems.append(f"sentence {index}: cannot be rebuilt (no text, no final stop)")
            elif want != got.body + f" [{got.n}]" + got.final:
                problems.append(
                    f"sentence {index}: published {got.text[:60]!r}, rebuilt {want[:60]!r}"
                )
    if c.lane is M.Lane.R:
        for index, sentence in enumerate(c.sentences, 1):
            if sentence.drop:
                problems.append(f"sentence {index}: lane R restates a quote, it drops nothing")
    return [(SITE, problem) for problem in problems]


def _drop_problems(
    text: str, sentence: M.PublishedSentence, drop: Sequence[tuple[int, int]], what: str
) -> list[str]:
    problems: list[str] = []
    candidates = candidate_spans(text, sentence.start, sentence.end)
    for low, high in drop:
        if (low, high) not in candidates:
            problems.append(
                f"{what}: drop [{low}:{high}) {text[low:high]!r} is not an offered span"
            )
        hit = protected_in(text[low:high])
        if hit:
            problems.append(f"{what}: drop [{low}:{high}) removes the protected {list(hit)}")
    return problems


def _v4(c: _Case) -> list[Problem]:
    problems: list[Problem] = []
    for index, sentence in enumerate(c.sentences, 1):
        text = c.text_of(sentence.src)
        if text is None:
            continue  # V1 and V2 hold a sentence without its text
        for problem in _drop_problems(text, sentence, sentence.drop, f"sentence {index}"):
            problems.append((SITE, problem))
    for item, sentence in c.card_sentence_items():
        text = c.text_of(sentence.src)
        if text is None:
            continue
        what = f"card item {item.sentence}"
        for problem in _drop_problems(text, sentence, item.drop, what):
            problems.append((CARD, problem))
        for low, high in sentence.drop:
            if not any(a <= low and high <= b for a, b in item.drop):
                problems.append(
                    (CARD, f"{what}: the description's drop [{low}:{high}) is not removed")
                )
    return problems


# --------------------------------------------------------------------------------------------
# V5 well-formed, V6 anaphora and naming, V7 subject
# --------------------------------------------------------------------------------------------

_QUOTE_PAIRS = (("“", "”"), ("«", "»"))


def balanced(text: str) -> bool:
    """Parentheses and brackets nest; straight double quotes pair up; curly and guillemet quotes
    open as often as they close."""
    stack: list[str] = []
    for char in text:
        if char in "([":
            stack.append(char)
        elif char in ")]":
            if not stack or stack.pop() != ("(" if char == ")" else "["):
                return False
    if stack or text.count('"') % 2:
        return False
    return all(text.count(opener) == text.count(closer) for opener, closer in _QUOTE_PAIRS)


_STARTS = re.compile(r"[\"'“‘«]|[^\W\d_]|\d")


def _v5(c: _Case) -> list[Problem]:
    if c.published is None:
        return []
    problems: list[str] = []
    for index, segment in enumerate(c.published, 1):
        text = segment.text
        where = f"sentence {index}"
        if not is_complete_sentence(segment.body + f" [{segment.n}]" + segment.final):
            problems.append(f"{where}: not a complete sentence: {text[:60]!r}")
        if not balanced(text):
            problems.append(f"{where}: unbalanced brackets or quotes")
        first = text[:1]
        if not _STARTS.match(first) or (first.isalpha() and not first.isupper()):
            problems.append(f"{where}: starts with {first!r}, not a capital, digit or quote")
        if not SENTENCE_MIN <= len(text) <= SENTENCE_MAX:
            problems.append(f"{where}: {len(text)} characters, not {SENTENCE_MIN}-{SENTENCE_MAX}")
        for label, pattern in ARTEFACTS:
            if pattern.search(text):
                problems.append(f"{where}: artefact {label}")
    return [(SITE, problem) for problem in problems]


_PRONOUN = re.compile(
    r"^(?:"
    + "|".join(re.escape(p) for p in sorted(M.PRONOUN_OPENERS, key=len, reverse=True))
    + r")(?![^\W\d_])"
)


def opens_with_pronoun(text: str) -> bool:
    """V6/V10: the text opens with a word of the closed pronoun list, as written there."""
    return bool(_PRONOUN.match(text))


def _names(c: _Case, source_id: str) -> list[str]:
    names = [c.site.name, *c.site.aliases]
    if _strong_own(c.gate(source_id)):
        title = c.metas[source_id].get("title")
        if isinstance(title, str) and title.strip():
            names.append(title)
    return names


def _v6(c: _Case) -> list[Problem]:
    if c.published is None:
        return []
    problems: list[str] = []
    for index, segment in enumerate(c.published):
        if not opens_with_pronoun(segment.body):
            continue
        sentence = c.sentences[index]
        previous = c.sentences[index - 1] if index else None
        text = c.text_of(sentence.src)
        adjacent = (
            previous is not None
            and previous.src == sentence.src
            and text is not None
            and previous.end <= sentence.start
            and not text[previous.end : sentence.start].strip()
        )
        if not adjacent:
            problems.append(
                f"sentence {index + 1} opens with a pronoun and its source predecessor is not "
                "the sentence published before it"
            )
    first = c.published[0].text
    names = _names(c, c.sentences[0].src)
    if not any(name_in(name, first) for name in names):
        problems.append(f"sentence 1 names none of {names}")
    return [(SITE, problem) for problem in problems]


#: V7: the subject-gate verdict each lane requires of its source.
LANE_VERDICT: Mapping[M.Lane, M.SubjectVerdict] = {
    M.Lane.W: M.SubjectVerdict.OWN,
    M.Lane.S: M.SubjectVerdict.SHARED,
    M.Lane.T: M.SubjectVerdict.OWN,
}


def _v7(c: _Case) -> list[Problem]:
    problems: list[str] = []
    wanted = LANE_VERDICT.get(c.lane)
    if wanted is not None:
        for ref in c.provenance.sources:
            gate = c.gate(ref.id)
            verdict = None if gate is None else gate.get("verdict")
            if verdict != wanted.value:
                problems.append(
                    f"{ref.id}: subject-gate verdict {verdict!r}, lane {c.lane.value} needs "
                    f"{wanted.value!r}"
                )
    if c.lane is M.Lane.S and c.published is not None:
        names = [c.site.name, *c.site.aliases]
        for index, (segment, sentence) in enumerate(zip(c.published, c.sentences, strict=True), 1):
            if any(name_in(name, segment.text) for name in names):
                continue
            text = c.text_of(sentence.src)
            heading = None if text is None else heading_before(text, sentence.start)
            if heading is not None and any(
                name_in(name, heading) or name_in(heading, name) for name in names
            ):
                continue
            problems.append(f"sentence {index}: lane S, no stored name and no matching section")
    return [(SITE, problem) for problem in problems]


# --------------------------------------------------------------------------------------------
# V8 markers, V9 length, V10 card
# --------------------------------------------------------------------------------------------


def _v8(c: _Case) -> list[Problem]:
    problems: list[str] = []
    site_id = c.site.site_id
    citations = [citation.to_dict() for citation in c.assembly.citations]
    sequence = T08.marker_sequence(c.assembly.description)
    declared = [entry["n"] for entry in T08.entries(citations, site_id)]
    cited = set(sequence)
    if sorted(cited - set(declared)):
        problems.append(f"markers {sorted(cited - set(declared))} have no citation")
    if sorted(set(declared) - cited):
        problems.append(f"citations {sorted(set(declared) - cited)} are cited by no marker")
    if declared != list(range(1, len(declared) + 1)):
        problems.append(f"the citations are numbered {declared}, not 1..{len(declared)}")
    if cited != set(range(1, len(cited) + 1)):
        problems.append(f"the markers are {sorted(cited)}, not 1..{len(cited)} without a gap")
    if c.published is None:
        problems.append("the description does not carry exactly one marker per sentence")
    else:
        for index, segment in enumerate(c.published, 1):
            count = len(T08.marker_sequence(segment.body + f" [{segment.n}]"))
            if count != 1:
                problems.append(f"sentence {index} carries {count} markers")
            if segment.n != c.sentences[index - 1].n:
                problems.append(
                    f"sentence {index} is marked [{segment.n}], provenance says "
                    f"[{c.sentences[index - 1].n}]"
                )
    numbering: dict[str, int] = {}
    for index, sentence in enumerate(c.sentences, 1):
        expected = numbering.setdefault(sentence.src, len(numbering) + 1)
        if sentence.n != expected:
            problems.append(
                f"sentence {index} ({sentence.src}) is [{sentence.n}]; by first appearance it "
                f"is [{expected}]"
            )
    by_n = {citation.n: citation for citation in c.assembly.citations}
    for source_id, n in numbering.items():
        citation, meta = by_n.get(n), c.metas.get(source_id)
        if citation is None or not isinstance(meta, Mapping):
            continue
        kind = M.source_kind(source_id)
        pinned = meta.get("final_url") if kind is M.SourceKind.R else meta.get("permalink")
        if citation.url != pinned:
            problems.append(f"[{n}] links {citation.url!r}, its source {source_id} is {pinned!r}")
        if kind is not M.SourceKind.R and citation.title != f"Wikipedia: {meta.get('title')}":
            problems.append(f"[{n}] is titled {citation.title!r}, not 'Wikipedia: <title>'")
        if citation.domain != urlsplit(citation.url).netloc:
            problems.append(f"[{n}] names the domain {citation.domain!r} of another URL")
        if citation.license.value != meta.get("licence"):
            problems.append(f"[{n}] carries licence {citation.license.value}, its source another")
    return [(SITE, problem) for problem in problems]


def _v9(c: _Case) -> list[Problem]:
    problems: list[str] = []
    length = len(without_markers(c.assembly.description))
    if not DESCRIPTION_MIN <= length <= DESCRIPTION_MAX:
        problems.append(
            f"the description has {length} characters, not {DESCRIPTION_MIN}-{DESCRIPTION_MAX}"
        )
    stored = len(without_markers(c.site.description or ""))
    if length < STORED_FLOOR * stored and not (c.site.flags & FLOOR_WAIVERS):
        problems.append(
            f"the description has {length} characters, under half the stored {stored}, and "
            "neither Phase 3 nor T03 proved the stored text defective"
        )
    return [(SITE, problem) for problem in problems]


def expected_card(c: _Case) -> str | None:
    """The card as this module's own edit list builds it from the provenance's card items."""
    items: list[str] = []
    for item, sentence in c.card_sentence_items():
        text = c.text_of(sentence.src)
        if text is None:
            return None
        items.append(spoken(edited(text, sentence.start, sentence.end, item.drop)))
    return " ".join(items) if items else None


def card_countries(card: str, stored: str | None) -> list[str]:
    """V10: the country names a card carries - every `NAME_TO_ISO` name and the stored country's
    own variants (`country_name_variants`), written as proper nouns."""
    named = countries_named(card)
    for variant in country_name_variants(stored or ""):
        for match in re.finditer(
            r"(?<!\w)" + re.escape(variant) + r"(?!\w)", card, flags=re.IGNORECASE
        ):
            if match.group(0)[0].isupper() and match.group(0) not in named:
                named.append(match.group(0))
    return named


def _v10(c: _Case) -> list[Problem]:
    card = c.assembly.card
    if card is None:
        return []
    problems: list[str] = []
    if not CARD_MIN <= len(card) <= CARD_MAX:
        problems.append(f"the card has {len(card)} characters, not {CARD_MIN}-{CARD_MAX}")
    want = expected_card(c)
    if want is None:
        problems.append("the card cannot be rebuilt from its provenance items")
    elif card != want:
        problems.append(f"the card is not its items minus offered spans: rebuilt {want[:60]!r}")
    if T08.marker_sequence(card):
        problems.append("the card carries a citation marker")
    if "(" in card or ")" in card:
        problems.append("the card carries parentheses")
    for index, (item, sentence) in enumerate(c.card_sentence_items(), 1):
        text = c.text_of(sentence.src)
        if text is not None and opens_with_pronoun(
            spoken(edited(text, sentence.start, sentence.end, item.drop))
        ):
            problems.append(f"card item {index} opens with a pronoun")
    named = card_countries(card, c.site.country)
    if named:
        problems.append(f"the card names a country: {named}")
    lowered = card.lower()
    found = [phrase for phrase in SUPERLATIVES if phrase in lowered]
    if found:
        problems.append(f"the card carries the evaluative superlative(s) {found}")
    fit = card_fit(c.site.name, card)
    if fit.missing:
        problems.append(
            "the heading font cannot draw " + " ".join(f"U+{ord(ch):04X}" for ch in fit.missing)
        )
    if fit.px > MAX_CAPTION_PX:
        problems.append(f"the caption word {fit.widest!r} is {fit.px} px, over {MAX_CAPTION_PX}")
    return [(CARD, problem) for problem in problems]


# --------------------------------------------------------------------------------------------
# V11 closure (T and R), V12 raw_data, V13 hashes, V14 dates, V15 injection
# --------------------------------------------------------------------------------------------

#: A thousands separator between digit groups: comma, full stop, apostrophe, space, no-break
#: space, narrow no-break space and thin space (English, French, German and Swiss usage).
_THOUSANDS = re.compile(r"(?<=\d)[,.'\u0020\u00a0\u202f\u2009](?=\d{3}(?!\d))")
_DIGITS = re.compile(r"\d+")
_WORD = re.compile(r"[^\W\d_][\w'’-]*")


def numerals(text: str) -> set[str]:
    """Every digit run of `text`, thousands separators removed (`10,000` and `10 000` agree)."""
    return set(_DIGITS.findall(_THOUSANDS.sub("", text)))


def fold(text: str) -> str:
    """Accents off and casefolded, through the project's own `normalize_name`."""
    return normalize_name(text, remove_parentheses=False, remove_brackets=False).casefold()


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def _v11(c: _Case) -> list[Problem]:
    if c.lane not in (M.Lane.T, M.Lane.R) or c.published is None:
        return []
    problems: list[str] = []
    for index, (segment, sentence) in enumerate(zip(c.published, c.sentences, strict=True), 1):
        text = c.text_of(sentence.src)
        if text is None:
            continue  # V1 and V2 hold a sentence without its text
        # Lane T translates the trimmed source sentence, so that is what it may state; lane R
        # restates its verbatim quote.
        quote = text[sentence.start : sentence.end]
        if c.lane is M.Lane.T:
            quote = edited(text, sentence.start, sentence.end, sentence.drop)
        where = f"sentence {index}"
        missing = sorted(numerals(segment.text) - numerals(quote))
        if missing:
            problems.append(f"{where}: the numbers {missing} are not in its quote")
        folded = fold(quote)
        tokens = _WORD.findall(segment.text)[1:]
        absent = [
            token
            for token in tokens
            if token[0].isupper()
            and not re.search(r"(?<!\w)" + re.escape(fold(token)) + r"(?!\w)", folded)
        ]
        if absent:
            problems.append(f"{where}: {absent} are not in its quote")
        if c.lane is M.Lane.R:
            problems.extend(_v11_restricted(c, index, segment, sentence, quote, text))
    return [(SITE, problem) for problem in problems]


def _v11_restricted(
    c: _Case,
    index: int,
    segment: Segment,
    sentence: M.PublishedSentence,
    quote: str,
    page: str,
) -> list[str]:
    """Lane R's three more: the years by interval (T03 reads the English page), the R quote the
    model returned is on the stored page (`discover_stage.claim_problems`), and no 8-word run of
    the page is copied."""
    problems: list[str] = []
    where = f"sentence {index}"
    wanted = {(m.lo, m.hi) for m in T03.mentions(quote) if m.marked}
    for mention in T03.mentions(segment.text):
        if mention.marked and (mention.lo, mention.hi) not in wanted:
            problems.append(f"{where}: the year {mention.raw!r} is not its quote's")
    ref = next(ref for ref in c.provenance.sources if ref.id == sentence.src)
    if index > len(c.quotes):
        problems.append(f"{where}: no R quote to check against {ref.url}")
    else:
        claim = DS.SourceClaim(url=ref.url, quote=c.quotes[index - 1])
        problems.extend(f"{where}: {p}" for p in DS.claim_problems([claim], {ref.url: page}))
    words, page_words = _words(segment.text), _words(page)
    runs = {
        tuple(page_words[i : i + NO_COPY_WORDS]) for i in range(len(page_words) - NO_COPY_WORDS + 1)
    }
    for i in range(len(words) - NO_COPY_WORDS + 1):
        if tuple(words[i : i + NO_COPY_WORDS]) in runs:
            problems.append(f"{where}: copies {' '.join(words[i : i + NO_COPY_WORDS])!r}")
            break
    return problems


def _v12(c: _Case) -> list[Problem]:
    problems: list[str] = []
    new = c.new_raw_data
    if not isinstance(new, Mapping):
        return [(SITE, f"the new raw_data is {type(new).__name__}, not a JSON object")]
    old = c.site.raw_data or {}
    replaced = {M.CITATIONS_KEY, M.PROVENANCE_KEY}
    if set(new) != set(old) | replaced:
        problems.append(
            f"the new raw_data keys differ from the old ones: added "
            f"{sorted(set(new) - set(old) - replaced)}, lost {sorted(set(old) - set(new))}"
        )
    changed = sorted(key for key in set(old) & set(new) - replaced if new[key] != old[key])
    if changed:
        problems.append(f"the new raw_data changes {changed}")
    citations = new.get(M.CITATIONS_KEY)
    if not citations:
        problems.append("description_citations is empty: the api/main.py re-seed could fire")
    elif citations != [citation.to_dict() for citation in c.assembly.citations]:
        problems.append("description_citations is not the assembly's citations")
    if new.get(M.PROVENANCE_KEY) != c.provenance.to_dict():
        problems.append("_description_provenance is not the assembly's provenance")
    return [(SITE, problem) for problem in problems]


def _v13(c: _Case) -> list[Problem]:
    problems: list[Problem] = []
    if c.provenance.desc_sha256 != M.text_sha256(c.assembly.description):
        problems.append((SITE, "desc_sha256 is not the sha256 of the description"))
    card, pinned = c.assembly.card, c.provenance.card
    if (card is None) != (pinned is None):
        problems.append((CARD, "the card and provenance.card disagree on whether there is one"))
    elif card is not None and pinned is not None and pinned.text_sha256 != M.text_sha256(card):
        problems.append((CARD, "card.text_sha256 is not the sha256 of the card"))
    return problems


@dataclass(frozen=True)
class _Snapshot:
    cards: Mapping[str, list[dict[str, Any]]]

    def by(self, table: str) -> Mapping[str, list[dict[str, Any]]]:
        return self.cards if table == "card_stats" else {}


@dataclass(frozen=True)
class _T03Context:
    """The two things `T03.run` reads of a census context: the sites and their card rows."""

    sites: list[dict[str, Any]]
    snap: _Snapshot


def _v14(c: _Case) -> list[Problem]:
    problems: list[str] = []
    site_id = c.site.site_id
    row = {
        "id": site_id,
        "period_start": c.site.period_start,
        "period_name": None,  # the plan carries period_start, the Phase-3-verified bucket key
        "description": c.assembly.description,
    }
    cards = {site_id: [{"card_description": c.assembly.card or ""}]}
    for finding in T03.run(_T03Context(sites=[row], snap=_Snapshot(cards))):
        if finding.severity is Severity.SEVERE:
            problems.append(f"T03 severe ({finding.test_id}): {finding.note}")
    stored_iso = _iso(c.site.country)
    for index, segment in enumerate(c.published or (), 1):
        if not LOCATION_VERB.search(segment.text):
            continue
        for name in countries_named(segment.text):
            same = (
                _iso(name) == stored_iso
                if stored_iso
                else name.lower() == (c.site.country or "").lower()
            )
            if not same:
                problems.append(
                    f"sentence {index} places the site in {name}, the stored country is "
                    f"{c.site.country!r}"
                )
    return [(SITE, problem) for problem in problems]


def _v15(c: _Case) -> list[Problem]:
    problems: list[Problem] = []
    texts = [(SITE, f"sentence {i}", s.text) for i, s in enumerate(c.published or (), 1)]
    if c.published is None:
        texts.append((SITE, "the description", c.assembly.description))
    if c.assembly.card is not None:
        texts.append((CARD, "the card", c.assembly.card))
    for scope, where, text in texts:
        for tell in INJECTION_TELLS:
            if tell.search(text):
                problems.append((scope, f"{where} matches the injection tell {tell.pattern!r}"))
    return problems


_RULES: tuple[tuple[M.HoldReason, Callable[[_Case], list[Problem]]], ...] = (
    (M.HoldReason.V1, _v1),
    (M.HoldReason.V2, _v2),
    (M.HoldReason.V3, _v3),
    (M.HoldReason.V4, _v4),
    (M.HoldReason.V5, _v5),
    (M.HoldReason.V6, _v6),
    (M.HoldReason.V7, _v7),
    (M.HoldReason.V8, _v8),
    (M.HoldReason.V9, _v9),
    (M.HoldReason.V10, _v10),
    (M.HoldReason.V11, _v11),
    (M.HoldReason.V12, _v12),
    (M.HoldReason.V13, _v13),
    (M.HoldReason.V14, _v14),
    (M.HoldReason.V15, _v15),
)


def verify_site(
    site: M.PlanSite,
    assembly: M.Assembly,
    *,
    metas: Mapping[str, Mapping[str, Any]],
    texts: Mapping[str, str],
    quotes: Sequence[str],
    new_raw_data: Mapping[str, Any],
) -> tuple[M.Hold, ...]:
    """V1-V15 for one site: one `Hold` per failing rule and scope, empty when every rule passes.

    `metas` are the raw `src.<id>.meta` objects, `texts` the pinned texts, `quotes` the quote per
    published sentence (the store slice in a batch, the journal's at acceptance) and
    `new_raw_data` the `raw_data` that is (to be) written (`write4.new_raw_data`, or production's
    read-back at acceptance).
    """
    if assembly.site_id != site.site_id:
        raise ValueError(f"the assembly of {assembly.site_id} is not the site {site.site_id}")
    case = _Case(
        site=site,
        assembly=assembly,
        metas=metas,
        texts=texts,
        quotes=tuple(quotes),
        new_raw_data=new_raw_data,
        segments=split_published(assembly.description),
    )
    holds: list[M.Hold] = []
    for reason, rule in _RULES:
        by_scope: dict[M.HoldScope, list[str]] = {}
        for scope, detail in rule(case):
            by_scope.setdefault(scope, []).append(detail)
        for scope, details in by_scope.items():
            holds.append(
                M.Hold(site_id=site.site_id, scope=scope, reason=reason, detail="; ".join(details))
            )
    return tuple(holds)


# --------------------------------------------------------------------------------------------
# The batch
# --------------------------------------------------------------------------------------------


def read_store(store: F.EvidenceStore, site_id: str, source_id: str) -> tuple[Any, str | None]:
    """(the raw meta object, the pinned text) of one source; `None` for a file that is absent.

    The text is the file's bytes decoded as UTF-8, never read in text mode: offsets index into
    exactly those characters, and a newline translation would move every one of them. Public for
    the acceptance (`output/remediation/tools/verify_writes4.py`), which reads the same store."""
    meta_path = store.path_for(site_id, M.source_feature(source_id, "meta"))
    text_path = store.path_for(site_id, M.source_feature(source_id, "txt"))
    meta = M.parse_json(meta_path.read_bytes().decode("utf-8")) if meta_path.exists() else None
    text = text_path.read_bytes().decode("utf-8") if text_path.exists() else None
    return meta, text


@dataclass(frozen=True)
class BatchInputs:
    """What S5 reads of one batch: the plan's sites, the lanes S1b assigned, the assemblies."""

    sites: dict[str, M.PlanSite]
    lanes: dict[str, M.LaneAssignment]
    assemblies: list[M.Assembly]


def read_batch(batch_dir: Path) -> BatchInputs:
    """`input.json`, `lanes.jsonl` and `assembly.jsonl` of one batch, each record through its
    `model4` reader. Raises `FileNotFoundError`, `InputError` or `ValueError`; never skips."""
    batch = _single_batch(batch_dir / M.INPUT_FILE, batch_dir.name)
    return BatchInputs(
        sites={s.site_id: s for s in (M.PlanSite.from_dict(d) for d in batch["sites"])},
        lanes={a.site_id: a for a in M.load_jsonl(batch_dir / M.LANES_FILE, M.LaneAssignment)},
        assemblies=M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly),
    )


def _write_atomic(path: Path, body: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(body.encode("utf-8"))
    tmp.replace(path)


def _lane_holds(assembly: M.Assembly, assignment: M.LaneAssignment) -> list[M.Hold]:
    """V7 against the lane S1b assigned: a site never changes lane, nor cites outside it."""
    problems: list[str] = []
    provenance = assembly.provenance
    if provenance.lane is not assignment.lane:
        problems.append(
            f"provenance says lane {provenance.lane.value}, S1b assigned {assignment.lane.value}"
        )
    outside = sorted({ref.id for ref in provenance.sources} - set(assignment.sources))
    if outside:
        problems.append(f"cites {outside}, outside the lane's sources {list(assignment.sources)}")
    if not problems:
        return []
    return [
        M.Hold(
            site_id=assembly.site_id,
            scope=SITE,
            reason=M.HoldReason.V7,
            detail="; ".join(problems),
        )
    ]


def verify_batch(batch_dir: Path) -> int:
    """S5 over one batch: every site of `assembly.jsonl` through `verify_site`.

    The V-holds replace this stage's earlier ones in `holds.jsonl` (the other stages' lines stay
    byte for byte), so a re-verification after the review leaves no stale hold behind; V14's holds
    are also written to `field_conflicts.jsonl`. `0` when every assembled site reached an outcome,
    `2` when the batch cannot be read (the run must stop).
    """
    batch_dir = Path(batch_dir)
    try:
        inputs = read_batch(batch_dir)
    except (FileNotFoundError, InputError, ValueError) as exc:
        print(f"verify4: {batch_dir}: {exc}", file=sys.stderr)
        return 2
    sites, lanes, assemblies = inputs.sites, inputs.lanes, inputs.assemblies
    unknown = sorted({a.site_id for a in assemblies} - set(sites))
    unrouted = sorted({a.site_id for a in assemblies} - set(lanes))
    if unknown or unrouted:
        print(
            f"verify4: {batch_dir}: assemblies for sites outside the batch {unknown} or without "
            f"a lane {unrouted}",
            file=sys.stderr,
        )
        return 2

    # Imported here: `write4` (WB-D2) calls this module, so a top-level import would be a cycle.
    from phase4 import write4

    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    found: list[M.Hold] = []
    for assembly in assemblies:
        site = sites[assembly.site_id]
        metas: dict[str, Any] = {}
        texts: dict[str, str] = {}
        for ref in assembly.provenance.sources:
            meta, text = read_store(store, site.site_id, ref.id)
            if meta is not None:
                metas[ref.id] = meta
            if text is not None:
                texts[ref.id] = text
        quotes = [
            texts[s.src][s.start : s.end] if s.src in texts else ""
            for s in assembly.provenance.sentences
        ]
        found.extend(_lane_holds(assembly, lanes[site.site_id]))
        found.extend(
            verify_site(
                site,
                assembly,
                metas=metas,
                texts=texts,
                quotes=quotes,
                new_raw_data=write4.new_raw_data(site.raw_data, assembly),
            )
        )

    holds_path = batch_dir / M.HOLDS_FILE
    kept: list[str] = []
    if holds_path.exists():
        for number, line in enumerate(holds_path.read_bytes().decode("utf-8").splitlines(), 1):
            try:
                reason = M.Hold.from_json(line).reason
            except ValueError as exc:
                print(f"verify4: {holds_path}:{number}: not a hold: {exc}", file=sys.stderr)
                return 2
            if reason not in V_REASONS:
                kept.append(line + "\n")
    _write_atomic(holds_path, "".join(kept) + M.dump_jsonl(found))
    conflicts = [hold for hold in found if hold.reason is M.HoldReason.V14]
    _write_atomic(batch_dir / FIELD_CONFLICTS_FILE, M.dump_jsonl(conflicts))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="verify4", description="S5: V1-V15 over one batch")
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args(argv)
    code = verify_batch(args.batch_dir)
    print(f"STAGE_EXIT={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
