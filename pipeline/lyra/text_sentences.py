"""Sentence splitting that survives abbreviations and initials.

Every caller used to inline ``re.split(r"(?<=[.!?])\\s+", text)``. That pattern
treats the period in "Kevin C. Nolan" as a sentence end, which is harmless when
the caller only reads the pieces but destructive when it deletes one: journal 75
shipped

    "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C., drawing
     on 425 radiocarbon dates ..."

because ``_strip_unsupported_claims`` removed the fragment that began at
"Nolan (Ball State), published in American Antiquity, ..." - the amputated half
of a real sentence.

Design bias: when a period is ambiguous we do NOT split. Under-splitting merges
two sentences, which stays readable; over-splitting invents a boundary in the
middle of a name and lets deletions cut a sentence in half.
"""

from __future__ import annotations

import re

# Sentinel that stands in for a protected period while we split. NUL never
# occurs in LLM prose, so a round trip cannot collide with real content.
_DOT = "\x00"

# Multi-dot forms: "e.g.", "i.e.", "A.D.", "B.C.E.", "U.S.".
_DOTTED_RE = re.compile(r"\b(?:[A-Za-z]\.){2,}")

# A lone capital followed by a period is an initial ("Mark F. Seeman"), never a
# sentence end in the prose this pipeline produces.
_INITIAL_RE = re.compile(r"(?<![A-Za-z])[A-Z]\.")

# Abbreviations that routinely carry a period mid-sentence. Case-insensitive
# entries are ones that are never a whole word on their own; the case-sensitive
# list holds titles and label words whose lowercase form is an ordinary word
# ("no", "ed") and must keep splitting normally.
_ABBREV_CI_RE = re.compile(
    r"\b(?:ca|cf|approx|fig|figs|vol|vols|eds|pp|etc|vs|al|inc|ltd|univ|dept)\.",
    re.IGNORECASE,
)
_ABBREV_CS_RE = re.compile(r"\b(?:St|Mt|Dr|Prof|Mr|Mrs|Ms|Jr|Sr|Ed|No|Nos|Vol|Fig|Op)\.")

# Date abbreviations in front of a number or an era: "c. 2500 BC", "ca. 300", "r. 1279-1213
# BC", "fl. 1200", "b. 1900", "d. 1950", "c. AD 750", "the 5th c. BCE". Without this rule "The
# temple was built c. 2500 BC by Khufu." split after "c." - the next word opens like a sentence -
# and is_complete_sentence passed both fragments (Phases 4 and 5 design, failure_modes). Measured
# 2026-09-23 over the 3,681 local Wikipedia extracts: 1,249 such breaks in 490 articles before,
# 26 in 14 after (mostly "b." for "bin" before a name, which is left alone). The era words
# are matched in capitals only: "d." or "b." elsewhere stays an ordinary word end.
_DATE_ABBREV_RE = re.compile(
    r"\b(?:c|ca|r|fl|b|d)\.(?=\s?(?:\d|(?-i:AD|BC|BCE|CE)\b))", re.IGNORECASE
)

# The same break in the era forms of the other Wikipedia languages the Phase-4 lane T selects from
# (fr, de, es, tr): "2500 av. J.-C. par", "um 2500 v. Chr. errichtet", "hacia el 2500 a. C. por",
# "M.Ö. 2500". The word in front of the era is never a sentence end, and "M.Ö." is one abbreviation
# (its "Ö" is outside the ASCII initial rule). Italian and Portuguese "a.C." are dotted forms already.
_ERA_ABBREV_RE = re.compile(r"\b(?:av|apr|v|n|a|d)\.(?=\s(?:J\.-C\.|Chr\.|C\.))|\bM\.Ö\.")

# Split only where a terminal mark is followed by whitespace AND the next
# sentence opens the way a sentence does - capital, digit, quote or bracket.
# A lowercase continuation means the period almost certainly belonged to an
# abbreviation we did not list.
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[«]?[A-Z0-9])")


def _protect(text: str) -> str:
    """Replace periods that are not sentence ends with the sentinel."""
    for pattern in (
        _DOTTED_RE,
        _ABBREV_CI_RE,
        _ABBREV_CS_RE,
        _DATE_ABBREV_RE,
        _ERA_ABBREV_RE,
        _INITIAL_RE,
    ):
        text = pattern.sub(lambda m: m.group(0).replace(".", _DOT), text)
    return text


def split_sentences(text: str, *, maxsplit: int = 0) -> list[str]:
    """Split ``text`` into sentences without breaking abbreviations or initials.

    Args:
        text: Prose to split. Returned unchanged (as a single element) when it
            holds no sentence boundary.
        maxsplit: Passed through to :func:`re.split`; 0 means unlimited.

    Returns:
        The sentences, in order, with original spacing inside each one.
    """
    if not text:
        return []
    parts = _SPLIT_RE.split(_protect(text), maxsplit=maxsplit)
    return [p.replace(_DOT, ".") for p in parts]


def sentence_span(text: str, index: int) -> tuple[int, int]:
    """Return the ``(start, end)`` offsets of the sentence containing ``index``.

    Offsets refer to ``text`` itself: :func:`_protect` swaps each protected
    period for a single sentinel character, so positions are preserved exactly.
    """
    protected = _protect(text)
    start, end = 0, len(text)
    for m in _SPLIT_RE.finditer(protected):
        if m.end() <= index:
            start = m.end()
        else:
            end = m.start()
            break
    return start, end


_OPENS_RE = re.compile(r"[\"'(\[«]?[A-Z0-9]")


def opens_like_a_sentence(text: str) -> bool:
    """True when ``text`` opens the way a sentence does: a capital or a digit, after at most one
    quotation mark or bracket. A trailing fragment opens mid-clause ("drawing on 425 dates.")."""
    return _OPENS_RE.match(text.strip()) is not None


def ends_like_a_sentence(text: str) -> bool:
    """True when ``text`` ends on a real terminator - ``.``, ``!`` or ``?``, before any closing
    quotation mark or bracket - and not on an abbreviation ("... and Kevin C."). :func:`_protect`
    is what tells those apart: it masks exactly the periods that are not sentence ends, so a masked
    final period means the unit was cut mid-sentence."""
    stripped = text.strip()
    return bool(stripped) and _protect(stripped).rstrip("\"')]»").endswith((".", "!", "?"))


def is_complete_sentence(text: str) -> bool:
    """True when ``text`` looks like a whole sentence rather than a fragment.

    Used as a safety net before deleting prose: removing a fragment cannot take
    the offending claim out cleanly, it only leaves ungrammatical debris.

    Two shapes are rejected, each by its own half (lane WC asks the halves apart):

    * a trailing fragment, which opens mid-clause (:func:`opens_like_a_sentence`)
    * a leading fragment, which ends on an abbreviation rather than a real
      terminator (:func:`ends_like_a_sentence`).
    """
    return opens_like_a_sentence(text) and ends_like_a_sentence(text)
