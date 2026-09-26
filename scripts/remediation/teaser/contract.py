"""Lane WB's card contract as code: the fact basis of a site and the checks a teaser card must pass
before any checker sees it.

The contract is `docs/procedures/CARD_DESCRIPTIONS.md` (owner decisions O2-O4 and O10 of
2026-09-26). This module is its mechanical half; the claim-by-claim half is the independent Opus
checker (`prompts.checker_prompt`). Pure: no database, no network, no model, no clock.

## The fact basis (`Basis`)

A card may claim only what the site's **published description** says, plus the site's name and
country. The description is shown to the writer and to the checker as numbered sentences
(`description_sentences`): citation markers taken out (`[1]`, `[2, 3]`, `[4-6]`, with the space
before them - the frontend's `stripCitations` shape), each non-empty line split by the project's one
sentence splitter (`pipeline.lyra.text_sentences.split_sentences`, which keeps `c. 3000 BC`, `St.`
and initials whole), numbered `S1`, `S2`, ... in text order. The numbering is a pure function of the
description, so the ids the checker names are reproducible from the text the provenance hashes.

## The site's names (`name_forms`)

A card must name the site. **Precisely**: it contains, as whole words after Phase 4's one name fold
(`phase4.subject_gate.fold` via `phase4.sentences.names_in`: accents stripped, lower case, every
non-alphanumeric character a space - so `Chichén-Itzá` is found as `Chichen Itza`), one of the site's
*name forms*:

1. the stored name, always;
2. the stored name without its bracketed parts (`Eryx (Sicily)` -> `Eryx`, `Quesera (Cheeseboard)
   de Zonzamas` -> `Quesera de Zonzamas`). The bracket's content is not a form: it is a
   disambiguator as often as an alias (`Sicily`);
3. of that, the part before the first comma (`Gaer Hillfort, Trellech` -> `Gaer Hillfort`), and each
   part between a slash or a spaced dash (`Medicine Wheel/Medicine Mountain ...` -> `Medicine
   Wheel`; `The Black Pyramid- Pyramid of Amenemhat III` -> `Pyramid of Amenemhat III`);
4. each alternative name the catalogue stores for the site (`unified_site_names`) **that the
   description itself uses** (found in it by the same fold): an alias the fact basis carries;
5. each of these without a leading `The`.

A derived form (2-5) must fold to at least 3 characters; the stored name counts whatever its length
(`Ur`). The writer's prompt lists the forms, so the rule is never a guess.

## The mechanical checks (`problems`)

On the **final** card - the writer's text after the assembler's one spoken edit
(`phase4.assemble.spoken`: `c.`/`ca.` before a date -> `circa`):

* 160-190 characters (Python `len`); one line, no tab, no double space, no leading or trailing
  space; it ends in `.` or `?` (a closing quote may follow);
* one or two sentences (`split_sentences`), at most one question mark, and the question's sentence
  at most 60 characters;
* no bracket of any kind (`()[]{}<>` - citation markers included); no `!` (an exclamation is
  marketing, not mystery), `#` (a hashtag) or `*` (markdown emphasis); no superscript or other
  number sign (Unicode `No`), no emoji or pictographic symbol (Unicode `So`, `Cs`, `Co`, `Cn`, the
  zero-width joiner and the variation selectors); and no bare `c.`/`ca.` left over;
* every numeral is grounded: `phase4.scope4.numerals` - the numeral reading of the ungrounded-card
  list (`scope4.ungrounded_card`): ASCII digits with comma thousands and a decimal part, read as a
  value - of the card, each of which must be a numeral of the fact basis (the site's name and the
  description without its markers). `ungrounded_card` itself is not called: it reads only the first
  500 characters of its input, the March generator's; the fact basis here is the whole description;
* the card names the site (`name_forms`, above);
* the shorts can render it: every glyph in the brand font and every caption word within the frame
  (`phase4.verify4.card_fit` and `MAX_CAPTION_PX`, V10's own measurement - the card is narrated and
  captioned).

What the checks cannot see - a claim the description does not make, a number written in words, a
superlative, "no one knows", the tone, whether the card is about this site - is the checker's.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from phase4 import verify4 as V  # noqa: E402 - V10's font seam: card_fit, MAX_CAPTION_PX
from phase4.assemble import spoken  # noqa: E402 - the assembler's one spoken edit
from phase4.scope4 import numerals  # noqa: E402 - the ungrounded-card numeral reading
from phase4.sentences import names_in  # noqa: E402 - Phase 4's name fold, whole words
from phase4.subject_gate import fold  # noqa: E402

from pipeline.lyra.text_sentences import split_sentences  # noqa: E402
from pipeline.utils.card_provenance import text_sha256  # noqa: E402

MIN_CHARS = 160
MAX_CHARS = 190
MAX_SENTENCES = 2
MAX_QUESTIONS = 1
MAX_QUESTION_CHARS = 60
#: A derived name form (not the stored name) must fold to at least this many characters.
MIN_FORM_CHARS = 3

#: A citation marker with the horizontal space before it: `[1]`, `[2, 3]`, `[4-6]`, `[4–6]`.
_MARKER = re.compile(r"[^\S\n]*\[\d+(?:\s*[,–-]\s*\d+)*\]")
_BRACKETED = re.compile(r"\s*\([^()]*\)")
_SPLIT_PARTS = re.compile(r"\s*/\s*|\s+[-–—]\s+|(?<=\w)[-–—]\s+")
_LEADING_THE = re.compile(r"^the\s+", re.IGNORECASE)
BRACKETS = frozenset("()[]{}<>")
#: Marks no card carries: an exclamation (marketing, not mystery), a hashtag, markdown emphasis.
MARKS = frozenset("!#*")
#: Unicode categories no card may carry: other symbols (emoji, pictographs, (c), degree, arrows),
#: surrogates, private use, unassigned; and `No` (superscripts, fractions: a footnote in disguise).
_FORBIDDEN_CATEGORIES = frozenset({"So", "Cs", "Co", "Cn", "No"})
_FORBIDDEN_CHARS = frozenset({chr(0x200D), chr(0xFE0E), chr(0xFE0F)})  # ZWJ, variation selectors
_BARE_CIRCA = re.compile(r"(?<![\w.])[Cc]a?\.")
_TERMINAL = re.compile(r"[.?][\"'”’]?\Z")

#: `card_fit`'s signature: (site name, card) -> the V10 measurement.
Fit = Callable[[str, str], Any]


@dataclass(frozen=True)
class Sentence:
    """One numbered sentence of the fact basis."""

    id: str
    text: str


@dataclass(frozen=True)
class Basis:
    """A site's fact basis: the only facts its card may claim."""

    site_id: str
    name: str
    country: str
    description: str
    sentences: tuple[Sentence, ...]
    forms: tuple[str, ...]

    @property
    def desc_sha256(self) -> str:
        """The sha256 of the published description the card is written from (the provenance's)."""
        return text_sha256(self.description)

    @property
    def sentence_ids(self) -> frozenset[str]:
        return frozenset(sentence.id for sentence in self.sentences)

    def grounding(self) -> str:
        """The text every numeral of a card must come from: the name and the description."""
        return "\n".join([self.name, *(sentence.text for sentence in self.sentences)])


def description_sentences(description: str) -> tuple[Sentence, ...]:
    """The description as numbered sentences: markers out, each line split, `S1`, `S2`, ..."""
    pieces: list[str] = []
    for line in _MARKER.sub("", description).split("\n"):
        for piece in split_sentences(line.strip()):
            if piece.strip():
                pieces.append(piece.strip())
    return tuple(Sentence(f"S{number}", text) for number, text in enumerate(pieces, start=1))


def name_forms(name: str, alt_names: Iterable[str], description: str) -> tuple[str, ...]:
    """The forms a card may name the site by (module doc, "The site's names"), stored name first."""
    base = _BRACKETED.sub("", name).strip() or name
    derived = [base, base.split(",")[0].strip(), *(p.strip() for p in _SPLIT_PARTS.split(base))]
    derived += [alt for alt in sorted(set(alt_names)) if names_in(description, [alt])]
    forms: list[str] = [name]
    seen = {fold(name)}
    for candidate in [name, *derived]:
        for form in (candidate, _LEADING_THE.sub("", candidate)):
            key = fold(form)
            if len(key) >= MIN_FORM_CHARS and key not in seen:
                seen.add(key)
                forms.append(form)
    return tuple(forms)


def basis(
    *, site_id: str, name: str, country: str, description: str, alt_names: Iterable[str]
) -> Basis:
    """The fact basis of one site, from its published description."""
    if not description.strip():
        raise ValueError(f"{site_id}: no published description - a site without one gets no card")
    return Basis(
        site_id=site_id,
        name=name,
        country=country,
        description=description,
        sentences=description_sentences(description),
        forms=name_forms(name, alt_names, description),
    )


def final_card(text: str) -> str:
    """The card as it is stored and narrated: the writer's text after the spoken edit."""
    return spoken(text)


def _forbidden(card: str) -> list[str]:
    return sorted(
        {
            ch
            for ch in card
            if ch in BRACKETS
            or ch in MARKS
            or ch in _FORBIDDEN_CHARS
            or unicodedata.category(ch) in _FORBIDDEN_CATEGORIES
        }
    )


def problems(card: str, site: Basis, *, fit: Fit) -> list[str]:
    """Why `card` (final, `final_card`) breaks the mechanical contract; empty when it does not."""
    found: list[str] = []
    length = len(card)
    if not MIN_CHARS <= length <= MAX_CHARS:
        found.append(f"length: {length} characters; a card is {MIN_CHARS}-{MAX_CHARS}")
    if card != card.strip() or "  " in card or any(ch in card for ch in "\n\r\t"):
        found.append("layout: a leading or trailing space, a double space, a tab or a line break")
    if not _TERMINAL.search(card):
        found.append("ending: the card must end with '.' or '?'")
    pieces = [piece for piece in split_sentences(card) if piece.strip()]
    if len(pieces) > MAX_SENTENCES:
        found.append(f"sentences: {len(pieces)}; a card is one or two sentences")
    if card.count("?") > MAX_QUESTIONS:
        found.append(f"questions: {card.count('?')} question marks; at most one short question")
    for piece in pieces:
        if "?" in piece and len(piece.strip()) > MAX_QUESTION_CHARS:
            found.append(
                f"question: {len(piece.strip())} characters; a question is at most "
                f"{MAX_QUESTION_CHARS}"
            )
    bad = _forbidden(card)
    if bad:
        found.append(
            "characters: no brackets, citation markers, '!', '#', '*', superscripts, emojis or "
            "symbols - found " + " ".join(repr(ch) for ch in bad)
        )
    if _BARE_CIRCA.search(card):
        found.append("circa: a bare 'c.' or 'ca.' - write 'circa' before a date, or rephrase")
    given = set(numerals(site.grounding()))
    ungrounded = sorted({str(n) for n in numerals(card) if n not in given})
    if ungrounded:
        found.append(
            "numbers not in the description: " + ", ".join(ungrounded) + " - every number must "
            "be written as the description writes it"
        )
    if not names_in(card, site.forms):
        found.append(
            "name: the card names the site by none of its forms: "
            + "; ".join(repr(form) for form in site.forms)
        )
    measured = fit(site.name, card)
    if measured.missing:
        found.append(f"font: the shorts font cannot draw {''.join(measured.missing)!r}")
    if measured.px > V.MAX_CAPTION_PX:
        found.append(
            f"caption: the word {measured.widest!r} is {measured.px} px, wider than the frame"
        )
    return found


def sentence_ids(ids: Sequence[str], site: Basis, what: str) -> tuple[str, ...]:
    """`ids` as a tuple, refused unless each is one of the site's sentence ids, once."""
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError(f"{what} is not a list of sentence ids")
    unknown = [i for i in ids if i not in site.sentence_ids]
    if unknown:
        raise ValueError(f"{what} names {unknown}, not sentence ids of this description")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{what} names a sentence twice")
    return tuple(ids)
