"""Mechanical support location and claim hygiene for Theo paper prose.

A marker ``[n]`` is an assertion that *this* reference carries *this* sentence.
The audit of the 31 live papers (``docs/reports/theo-paper-defects-2026-10-04.md``)
shows what that assertion is worth when it is not checked: 2 105 findings, 602
(28.6 %) supported as written, and the largest correctable class is not
fabrication but the **wrong marker on a true sentence** (class A, 384
``misattributed``). This module is the mechanical half of the researcher's
rule "a marker requires a located sentence": it finds the sentence in a
*fetched* source text that carries a claim, and it reports the claim
properties that may never be invented, sharpened or merged.

What is checked here, and what each function refuses to decide:

* :func:`locate_support` - the claim's specifics must be found in a contiguous
  run of at most ``window`` sentences of the source. The returned
  :class:`Located.quote` is always a verbatim slice of the source, so a
  quotation spliced out of two sentences (class B, ``panspermia``) cannot be
  produced. Out of scope: whether the located sentence *means* the claim.
  Paraphrase, hedging and irony are a reader's judgement, not this module's.
* :func:`claim_numbers` / :func:`numbers_absent_from` - the number, its
  magnitude word, its currency symbol, its percent or its unit.
  ``hallucination_gate._MEASUREMENT_RE`` only knows Hz/kg/tonnes/km/m/ft/mm/cm
  and therefore never sees ``$20 million`` - the figure the report names as
  present in no source of the stargate paper. Out of scope: spelled-out counts
  ("nine", "five codenames", the mogollon ten-vs-nine), ordinals, and
  scientific notation with an exponent (``9 x 10**-26**).
* :func:`claim_site_codes` / :func:`claim_identifiers` - the codes and
  identifiers that must be copied from the record, never inferred or recalled
  (class C, class E). Out of scope: a code whose prefix is not in the accepted
  lists below; such a token is not guessed.
* :func:`is_retraction_claim` - the vocabulary of a claim about a work's status
  in the bibliographic record (class E). It does not decide whether the
  retraction exists; the report's rule is that Crossref, OpenAlex or Europe PMC
  does, before the sentence is written.
* :func:`sentence_defects` - the six structural defects of class F that all
  shipped to a live page. Deliberately conservative: a marker run at the end of
  a paragraph is this project's accepted citation unit (owner's decision
  04.10.2026) and is not reported.

No network, no database, no model call, no file read: every function is pure
and takes its text as arguments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.lyra.hallucination_gate import extract_specifics
from pipeline.lyra.text_sentences import opens_like_a_sentence, split_sentences

# ---------------------------------------------------------------------------
# Shared text helpers
# ---------------------------------------------------------------------------

# A citation marker, singular: "[4]", "[7, 12]". A run of them is handled by
# _MARKER_RUN_RE; the two are kept apart because a run is one citation decision
# and its defects are judged on the run, not on each marker in it.
_MARKER_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_MARKER_RUN_RE = re.compile(r"(?:\[\d+(?:\s*,\s*\d+)*\][ \t]*)+")

_WHITESPACE_RE = re.compile(r"\s+")
# The full stop a claim arrives with, which the source sentence continues past.
_TRAILING_TERMINATOR_RE = re.compile(r"[.!?…][\"'”’)\]]*$")


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace runs, for containment tests only."""
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def _collapse(text: str) -> tuple[str, tuple[int, ...]]:
    """Lowercase ``text`` with whitespace runs collapsed to one space.

    Returns the collapsed string and, for each of its characters, the offset
    of the character in ``text`` it came from. Used only where an offset into
    the original text is needed, which is the one place a normalized search
    could silently report a position that does not exist.
    """
    chars: list[str] = []
    offsets: list[int] = []
    after_space = True
    for index, char in enumerate(text):
        if char.isspace():
            if not after_space:
                chars.append(" ")
                offsets.append(index)
            after_space = True
            continue
        chars.append(char.lower())
        offsets.append(index)
        after_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return "".join(chars), tuple(offsets)


def _contains_word(haystack: str, needle: str) -> bool:
    """True when ``needle`` occurs in ``haystack`` on word boundaries.

    Both sides must already be normalized. Word boundaries matter: the plasma
    paper's "Worlds in Collision" must not be reported as carried by a source
    that spells it "Worlds in Collisions", which contains it as a bare
    substring.
    """
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _blank_markers(text: str) -> str:
    """Replace every citation marker with spaces, preserving every offset.

    Structural prose is tested with the markers removed, because a sentence
    that ends on "consensus [11]" ends on a word, not on a marker.
    """
    return _MARKER_RE.sub(lambda m: " " * len(m.group(0)), text)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every sentence ``split_sentences`` returns.

    ``split_sentences`` yields verbatim slices of its input in order, so the
    spans are found by walking the slices forward. A slice that cannot be
    found is an invariant break in the splitter, not a data problem, and says
    so instead of returning a wrong offset.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for sentence in split_sentences(text):
        if not sentence.strip():
            cursor += len(sentence)
            continue
        found = text.find(sentence, cursor)
        if found < 0:
            raise ValueError("split_sentences returned a slice that is not a substring of its input")
        spans.append((found, found + len(sentence)))
        cursor = found + len(sentence)
    return spans


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

# "k" needs its word boundary: without it "150 km²" would read as the
# magnitude "k" plus the unit "m²" and normalize to "150 k m".
_MAGNITUDE_ALTERNATION = r"thousands|million|millions|billion|billions|trillion|trillions|k\b"

# Surface forms the number scanner accepts after a number. Kept small and
# explicit on purpose: an open "any word" unit would swallow the next word of
# the sentence ("1950 Immanuel Velikovsky" -> "1950 immanuel").
_UNITS = (
    # length, with the superscript forms the corpus uses for area and for the
    # SI magnetic moment (A.m2/kg)
    "km²|km2|square kilometres|square kilometers|square kilometre|square kilometer|"
    "sq km|km|kilometres|kilometers|kilometre|kilometer|"
    "m²|m2|square metres|square meters|square metre|square meter|sq m|"
    "m|metres|meters|metre|meter|cm|centimetres|centimeters|centimetre|centimeter|"
    "mm|millimetres|millimeters|millimetre|millimeter|ft|feet|foot|inches|inch",
    # mass
    "kg|kilograms|kilogram|g|grams|gram|tonnes|tons|tonne|ton",
    # frequency
    "hz|khz|mhz|ghz",
    # duration
    "years|year|months|month|weeks|week|days|day|hours|hour|minutes|minute|seconds|second",
    # counted things the papers actually count
    "items|item|structures|structure|houses|house|rooms|room|pithouses|pithouse|"
    "sherds|sherd|contexts|context|elements|element|sites|site|children|"
    "degrees|degree|percentage|percent|per cent",
)

# Spellings of one unit are folded together. Everything not listed here is kept
# exactly as written, which is what the interface asks for ("1650 tons" ->
# "1650 tons"); a claim in "tons" against a quote in "tonnes" is therefore
# reported as absent, and that is deliberate - the unit is part of the claim
# (class B: "a number keeps its unit, its epoch and its uncertainty").
_UNIT_ALIASES = {
    "km²": "km",
    "km2": "km",
    "square kilometre": "km",
    "square kilometres": "km",
    "square kilometer": "km",
    "square kilometers": "km",
    "sq km": "km",
    "m²": "m",
    "m2": "m",
    "square metre": "m",
    "square metres": "m",
    "square meter": "m",
    "square meters": "m",
    "sq m": "m",
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "per cent": "%",
    "degrees": "degree",
}

_CURRENCY_SYMBOLS = "$€£¥₹₽"
_CURRENCY_WORDS = (
    "dollars|dollar|euros|euro|pounds|pound|yen|yuan|rupees|rupee|"
    "francs|franc|marks|mark|reichsmarks|reichsmark"
)

_NUMBER_RE = re.compile(
    r"(?<![\w.])"
    rf"(?:[{_CURRENCY_SYMBOLS}][ \t]*)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:[ \t]*(?:[-‐‑‒–—]|[ \t]to[ \t]|[ \t]and[ \t])[ \t]*"
    r"(?P<num2>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?))?"
    rf"[ \t]*(?P<mag>{_MAGNITUDE_ALTERNATION})?"
    rf"[ \t-]*(?P<unit>%|(?:{'|'.join(_UNITS)}))?"
    rf"[ \t]*(?:{_CURRENCY_WORDS})?"
    r"(?![\w])",
    re.IGNORECASE,
)


def _canonical_unit(surface: str | None) -> str:
    if not surface:
        return ""
    folded = " ".join(surface.lower().split())
    return _UNIT_ALIASES.get(folded, folded)


def claim_numbers(text: str) -> tuple[str, ...]:
    """Every number in ``text`` as ``"<digits> <magnitude-or-unit>"``.

    Normalized: thousands separators are dropped, a currency symbol is
    dropped, and an area or percent spelling is folded into one canonical
    form. So ``"$20 million"`` -> ``"20 million"``, ``"1650 tons"`` ->
    ``"1650 tons"``, ``"150 km²"`` -> ``"150 km"``, ``"40%"`` -> ``"40%"``,
    ``"1,650"`` -> ``"1650"``, and a bare ``"9"`` -> ``"9"``. A range keeps its
    trailing unit on its last number only (``"700 to 950 km"`` -> ``"700"``,
    ``"950 km"``), so both spellings of the same range agree. Order is textual,
    duplicates are collapsed.

    The currency is deliberately not part of the key, in either the symbol or
    the spelled-out form, because the interface specifies the symbol's
    removal. A figure quoted in the wrong currency is therefore not caught
    here. Spelled-out counts, ordinals, exponents (``9 × 10⁻²⁶``) and era
    markers (``900 BC``) are out of scope; a date is
    ``hallucination_gate``'s ``date`` specific, not a number key.
    """
    if not text:
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        magnitude = (match.group("mag") or "").lower()
        unit = _canonical_unit(match.group("unit"))
        tail = " ".join(part for part in (magnitude, unit) if part)
        for group in ("num", "num2"):
            digits = match.group(group)
            if digits is None:
                continue
            key = digits.replace(",", "")
            if tail:
                # A percent sign is written against its number, everything
                # else takes a space: "40%" but "20 million". A range's unit
                # belongs to its last number only, so both spellings of the
                # range agree and a claim that drops the range cannot pass for
                # its source.
                key = f"{key}{unit}" if unit == "%" and not magnitude else f"{key} {tail}"
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return tuple(out)


def numbers_absent_from(claim: str, quote: str) -> tuple[str, ...]:
    """The claim's numbers that the quote does not contain.

    The mechanical half of "never sharpen a source" (class B): a number in a
    claim that is not in its supporting quote is a defect, whether it was
    inflated (the squatter man's ``> 50 km²`` published as ``150``), rounded
    or invented (``$20 million``). A number that is absent from the *whole*
    source, not just the quote, is :attr:`Located.missing`'s business.
    """
    in_quote = set(claim_numbers(quote))
    out: list[str] = []
    seen: set[str] = set()
    for key in claim_numbers(claim):
        if key in in_quote or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return tuple(out)


# ---------------------------------------------------------------------------
# locate_support
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Located:
    """The evidence found for a claim, and the evidence that was not.

    ``quote`` is a verbatim slice of the source text between ``start`` and
    ``end``; it is never a concatenation of two separated stretches, so it can
    be checked with ``quote in source_text`` and it can be re-read by a
    reader. ``matched`` are the claim's specifics inside the quote, ``missing``
    those absent from the whole source text (class D: the source does not carry
    them at all).
    """

    quote: str
    start: int
    end: int
    matched: tuple[str, ...]
    missing: tuple[str, ...]


# A located window must carry at least this many of the claim's specifics, or
# all of them when the claim has fewer. One matched specific is not a sentence:
# a lone number inside a long source sentence is a coincidence, not support.
_MIN_MATCHED = 2

# Kinds that may not be satisfied by "somewhere in the source" but have to be
# inside the located window: the hedged number and the recalled date are the
# two findings classes (B: 858, E) the gate exists for.
_HARD_KINDS = frozenset({"date", "measurement", "number"})


def _claim_specifics(claim: str) -> tuple[tuple[str, str], ...]:
    """The claim's specifics as ``(kind, text)``, in order, deduplicated.

    ``extract_specifics`` covers persons, titles, dates, measurements, quotes
    and institutions. Its measurement regex does not see a magnitude word, a
    currency or a percent, so the claim's numbers are added here as
    ``number`` specifics - that is the gap that let ``$20 million`` through.

    Deduplication is on the text, keeping the kind that was found first, so a
    year that ``extract_specifics`` reports as a ``date`` is not also reported
    as a bare number: it keeps the ``date`` kind, which is the one that has to
    be inside the located window.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for specific in extract_specifics(claim):
        folded = _normalize(specific.text)
        if not folded or folded in seen:
            continue
        seen.add(folded)
        out.append((specific.kind, specific.text))
    for number in claim_numbers(claim):
        if number in seen:
            continue
        seen.add(number)
        out.append(("number", number))
    return tuple(out)


def _carried(kind: str, text: str, haystack: str, numbers: frozenset[str]) -> bool:
    """True when the source text ``haystack`` carries the specific ``text``.

    A ``number`` specific is compared against the source's normalized numbers
    (its key has already dropped thousands separators, so ``1,650`` in the
    source has to be read as the key ``1650``); every other kind is matched as
    a word on word boundaries.
    """
    if kind == "number":
        return text in numbers
    return _contains_word(haystack, _normalize(text))


def _locate_by_containment(
    claim: str, source_text: str, spans: list[tuple[int, int]]
) -> Located | None:
    """Locate a claim that has no specifics at all, by its own text.

    A claim with no person, no date, no number and no number-word is only
    locatable if the claim itself is in the source. Its trailing full stop is
    dropped first, because a claim arrives with one and the source sentence
    continues past it, and the match has to end on a word boundary. The
    collapsed match is mapped back through its offset table, and the evidence
    is the run of sentences that covers it - never more than ``window``
    sentences, because a claim that needs more room than the caller allowed is
    not located.
    """
    needle, _ = _collapse(_TRAILING_TERMINATOR_RE.sub("", claim).strip())
    if not needle:
        return None
    haystack, offsets = _collapse(source_text)
    position = haystack.find(needle)
    if position < 0:
        return None
    after = position + len(needle)
    if after < len(haystack) and haystack[after].isalnum():
        # "bodies" is not "body": the claim's last word has to end here.
        return None
    raw_start = offsets[position]
    raw_end = offsets[position + len(needle) - 1] + 1
    first = None
    for index, (begin, _finish) in enumerate(spans):
        if begin <= raw_start:
            first = index
    last = next((i for i, (_s, e) in enumerate(spans) if raw_end <= e), None)
    if first is None or last is None:
        return None
    return Located(
        quote=source_text[spans[first][0] : spans[last][1]],
        start=spans[first][0],
        end=spans[last][1],
        matched=(),
        missing=(),
    )


def locate_support(claim: str, source_text: str, *, window: int = 2) -> Located | None:
    """Find the sentence in ``source_text`` that carries ``claim``.

    The source is split with :func:`split_sentences`, every contiguous run of
    at most ``window`` sentences is scored by how many of the claim's
    specifics it contains, and the best run is returned as a :class:`Located`.
    ``window`` is the maximum number of consecutive sentences the quote may
    span; shorter runs are scored too, so the tightest evidence wins.

    A run is accepted only when all three hold, and the thresholds are the
    point of the function:

    1. it is non-empty - it carries at least one of the claim's specifics;
    2. it carries **every** ``date``, ``measurement`` and ``number`` specific
       of the claim. These are the class B and class E findings, and a
       sentence that states the right year and the wrong area does not carry
       the claim;
    3. it carries at least :data:`_MIN_MATCHED` specifics, or all of them when
       the claim has fewer than that.

    ``None`` means the claim is not carried by this source. It never means
    "probably carried": an unlocated claim must be re-sourced, narrowed or
    dropped (report rule 1, classes A and D). A claim with no specifics at all
    is located only if its own text is in the source.

    What this cannot decide: whether a located sentence supports the claim in
    meaning, and whether a hedge was dropped (class B is only half
    mechanical). It says where the evidence is; a reader says whether it says
    the claim.
    """
    if window < 1:
        raise ValueError(f"window must be at least 1, got {window}")
    if not claim.strip() or not source_text.strip():
        return None
    spans = _sentence_spans(source_text)
    if not spans:
        return None
    claim_text = _MARKER_RE.sub(" ", claim)
    specifics = _claim_specifics(claim_text)
    if not specifics:
        located = _locate_by_containment(claim_text, source_text, spans)
        if located is None:
            return None
        first, last = located.start, located.end
        covering = [
            index for index, (begin, finish) in enumerate(spans) if begin >= first and finish <= last
        ]
        if len(covering) > window:
            return None
        return located

    source_norm = _normalize(source_text)
    # A number key is normalized ("1,650" -> "1650"), so it can only be found
    # by comparing it with the source's own numbers, not by searching the raw
    # text for a string the source never contains.
    source_numbers = frozenset(claim_numbers(source_text))
    missing = tuple(
        text
        for kind, text in specifics
        if not _carried(kind, text, source_norm, source_numbers)
    )

    best: tuple[tuple[int, int, int], int, int, tuple[str, ...]] | None = None
    for start_index, (start, _end) in enumerate(spans):
        for length in range(1, window + 1):
            last_index = start_index + length - 1
            if last_index >= len(spans):
                break
            end = spans[last_index][1]
            window_norm = _normalize(source_text[start:end])
            window_numbers = frozenset(claim_numbers(source_text[start:end]))
            matched = tuple(
                text
                for kind, text in specifics
                if _carried(kind, text, window_norm, window_numbers)
            )
            if not matched:
                continue
            if any(
                kind in _HARD_KINDS and text not in matched for kind, text in specifics
            ):
                continue
            if len(matched) < _MIN_MATCHED and len(specifics) > 1:
                continue
            rank = (len(matched), -(end - start), -start)
            if best is None or rank > best[0]:
                best = (rank, start, end, matched)
    if best is None:
        return None
    _rank, start, end, matched = best
    return Located(
        quote=source_text[start:end], start=start, end=end, matched=matched, missing=missing
    )


# ---------------------------------------------------------------------------
# Codes and identifiers (class C and class E: copied, never inferred)
# ---------------------------------------------------------------------------

# Museum and archive accession prefixes seen in this corpus. A code-shaped
# token with a prefix that is not on this list is not decided here: guessing an
# accession number is the failure the rule exists to stop.
_ACCESSION_PREFIXES = ("USNM", "NMNH", "AMNH", "PMNH", "SAM", "QVM", "BM", "AM", "MS", "PP", "NA", "AC")
_ACCESSION_RE = re.compile(
    rf"\b(?:{'|'.join(_ACCESSION_PREFIXES)})[ .-]?\d{{2,7}}(?:-[A-Za-z0-9]{{1,4}})?\b"
)

# US state and territory codes that are also English words are left out, so
# that "IN 1905" or "US 30" is not read as an inventory number.
_POSTAL_CODES = tuple(
    code
    for code in (
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
        "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI AA AE AP"
    ).split()
    if code not in {"IN", "AS", "AT", "BE", "DO", "GO", "HE", "IF", "ME", "MY", "NO", "OF", "ON", "OR", "PA", "US"}
)
_STATE_INVENTORY_RE = re.compile(rf"\b(?:{'|'.join(_POSTAL_CODES)})\s?\d{{3,7}}\b")

# A short capital token naming a site: the "SU Site" form.
_SITE_WORD_RE = re.compile(r"\b[A-Z]{2,3}\s(?:Site|Sites|Ruin|Village|Canyon|Ware)\b")


def claim_site_codes(text: str) -> tuple[str, ...]:
    """Site and archive codes in ``text`` that must be copied, not inferred.

    Three accepted shapes, each listed because the report names its case:

    * a US state or territory code plus three to seven digits - ``LA 11568``,
      the mogollon paper's Mogollon Village, which the writer merged with the
      SU Site and with a count of "ten" where the source says nine (class C);
    * a museum or archive accession prefix plus digits - ``MS 3304-a``,
      Haury's Smithsonian report on the same site;
    * two or three capitals directly followed by a site word - ``SU Site``,
      the excavation the paper folded into the type site.

    Out of scope, and said so rather than guessed: a designation this module
    cannot place (``Mogollon 1:15``, a UK scheduled-monument number, a grid
    reference), and a code whose prefix is not in the two lists above.
    """
    if not text:
        return ()
    found: list[tuple[int, int, str]] = []
    for pattern in (_STATE_INVENTORY_RE, _ACCESSION_RE, _SITE_WORD_RE):
        for match in pattern.finditer(text):
            found.append((match.start(), match.end(), " ".join(match.group(0).split())))
    # Longest match wins where two patterns overlap: "MS 3304-a" is a
    # Smithsonian accession, and "MS" is also Mississippi's postal code.
    found.sort(key=lambda item: (item[0], -item[1]))
    out: list[str] = []
    covered = -1
    for begin, finish, code in found:
        if begin < covered:
            continue
        out.append(code)
        covered = finish
    return tuple(out)


_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>,;)\]]+", re.IGNORECASE)
_ISBN_LABELLED_RE = re.compile(r"\bISBN(?:\s*[:\-]?\s*)((?:97[89][\s-]?)?(?:\d[\s-]?){9}[\dXx])\b", re.IGNORECASE)
_PMID_RE = re.compile(r"\bPMID:?\s*(\d{5,9})\b", re.IGNORECASE)
_PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{5,9})", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\barXiv:?\s*(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)


def claim_identifiers(text: str) -> tuple[str, ...]:
    """Record identifiers in ``text``, each tagged with its kind.

    DOIs, ISBNs, PMIDs and arXiv ids, in the forms ``doi:``, ``isbn:``,
    ``pmid:`` and ``arxiv:``. A DOI is lowercased because DOIs are
    case-insensitive, and trailing punctuation is stripped from a DOI because
    a sentence's full stop is not part of it. Order is textual, duplicates are
    collapsed.

    Out of scope: any other record number (an accession number is a site code
    and belongs to :func:`claim_site_codes`, a CAS or RRID identifier is not
    recognised here), and an identifier that is merely plausible - these are
    what the report means by "copied from the fetched record, never from
    memory": a guessed DOI is the single most common cause of a dead link.
    """
    if not text:
        return ()
    out: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        if value not in seen:
            seen.add(value)
            out.append(value)

    for match in _DOI_RE.finditer(text):
        _add("doi:" + match.group(0).rstrip(".,;:)]}").lower())
    for match in _ISBN_LABELLED_RE.finditer(text):
        _add("isbn:" + re.sub(r"[\s-]", "", match.group(1)))
    for match in _PMID_RE.finditer(text):
        _add("pmid:" + match.group(1))
    for match in _PUBMED_URL_RE.finditer(text):
        _add("pmid:" + match.group(1))
    for pattern in (_ARXIV_RE, _ARXIV_URL_RE):
        for match in pattern.finditer(text):
            _add("arxiv:" + match.group(1))

    return tuple(out)


# ---------------------------------------------------------------------------
# Retraction claims (class E)
# ---------------------------------------------------------------------------

# The bibliographic-status vocabulary. A plain "correction" is not on this
# list: in prose it is an ordinary word ("a correction to the map"), and the
# report's failures are records that must be checked, not prose.
_RETRACTION_RE = re.compile(
    r"\b(?:retract(?:ed|ing|ion|ions)|withdrawn|withdrawal|withdraws|withdraw|"
    r"erratum|corrigendum|expression of concern|retraction notice|supersed(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)
_WORK_RE = re.compile(
    r"\b(?:paper|papers|article|articles|study|studies|report|reports|book|books|"
    r"chapter|letter|letters|manuscript|manuscripts|publication|publications|published|"
    r"work|works|journal|journals|preprint|preprints|thesis|dissertation|"
    r"trial|review|analysis|entry|record|records)\b",
    re.IGNORECASE,
)


def is_retraction_claim(text: str) -> bool:
    """True when ``text`` makes an assertion about a work's record status.

    A retraction, withdrawal, erratum, expression of concern or supersession
    of a paper, article, report or other named work. The stargate paper wrote
    that Bem's "Feeling the Future" paper "was retracted"; the report refuted
    the retraction through Crossref, OpenAlex and Europe PMC, which is a
    claim about the bibliographic record and not about the prose.

    Polarity is not judged: "was not retracted" is the same kind of claim
    about the record and is flagged too, because the check that decides it is
    the same one. A withdrawal of money or a correction to a map is not
    flagged - a work noun has to be there as well.
    """
    if not text:
        return False
    return _RETRACTION_RE.search(text) is not None and _WORK_RE.search(text) is not None


# ---------------------------------------------------------------------------
# Structural sentence defects (class F)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SentenceDefect:
    """One structural defect of class F, anchored in the input text.

    ``text`` is the smallest contiguous fragment that shows the defect - the
    citation marker for the three marker defects, ``".."``, ``",."`` or the
    dangling tail - and ``offset`` is where that fragment starts in the string
    that was checked. A caller that wants the whole sentence widens it with
    :func:`pipeline.lyra.text_sentences.sentence_span`.
    """

    kind: str
    text: str
    offset: int


# A line that is not prose: a heading, an image block, an italic caption, a
# "[Source](url)" credit. A defect in one of them is not a prose defect, and
# the gate has its own rules for images.
_NOT_PROSE_RE = re.compile(r"\A\s*(?:#{1,6}[\s#]|!\[|\*|\[Source\]\()")

# "roughly 16 months.." - two stops, but never the three of an ellipsis.
_DOUBLE_STOP_RE = re.compile(r"(?<!\.)\.\.(?!\.)")
# "rather than consensus [11],." - a comma in front of the full stop.
_COMMA_BEFORE_STOP_RE = re.compile(r",[ \t]*\.(?!\.)")
# A URL is a bibliographic fact, not prose: an ADS bibcode
# (1950PA.....58..278P) carries a ".." that no reader reads as a full stop.
_URL_RE = re.compile(r"https?://\S+")

# The last word of a sentence plus its terminator. \Z so a trailing space (the
# last sentence of a block) still matches.
_TAIL_RE = re.compile(r"([\w'’\-]+)([.!?])([\"'”’)\]]*)\s*\Z")

# The report's rule: "no sentence may end on a preposition, a conjunction or a
# definite article". The list is closed, and it deliberately does **not** carry
# the personal, possessive or demonstrative pronouns: the corpus has 66
# sentences ending on "it", 25 on "them" and 13 on "one", and every one that
# was sampled is correct English ("...rather than exceeding it.", "...than the
# one before."). The report's other cargo-cults example, "attack the people
# they.", ends on such a pronoun and is therefore not reported - the rule as
# the report states it does not reach it, and widening the list to reach it
# costs about 110 false positives across the 31 papers. Relativizers are kept
# ("...the person whom."), because a relative clause cannot end a sentence.
_FUNCTION_WORDS = frozenset(
    {
        # prepositions, without the six particles that read as adverbs
        # (above, below, over, out, up, down): real sentences end on those
        "about", "across", "after", "against", "along", "among", "around",
        "at", "before", "behind", "beneath", "beside", "between", "beyond",
        "by", "concerning", "despite", "during", "except", "for", "from",
        "in", "inside", "into", "like", "near", "of", "on", "onto",
        "outside", "per", "through", "throughout", "till", "to",
        "toward", "under", "until", "unto", "upon", "versus", "via", "with",
        "within", "without",
        # coordinating and subordinating conjunctions ("for" and "since" are
        # already above; both are prepositions before a date and conjunctions
        # here, and a membership test cannot tell the two apart)
        "and", "as", "because", "but", "if", "nor", "or", "since",
        "so", "than", "that", "though", "unless", "when", "whenever",
        "where", "wherever", "whether", "while", "yet",
        # relativizers
        "which", "who", "whom", "whose",
        # definite and indefinite articles
        "a", "an", "the",
    }
)

# A marker run's left neighbour counts as a sentence terminator only when the
# closing quote or bracket that may sit after it is stepped over first: the
# reference list ends every line with "[Academic]", and that is not a sentence.
_CLOSERS = "\"”’)]»"
_TERMINATORS = (".", "!", "?")


def _left_is_terminated(left: str) -> bool:
    """True when the text before a marker run ends on a sentence terminator."""
    stripped = left.rstrip()
    while stripped and stripped[-1] in _CLOSERS:
        stripped = stripped[:-1].rstrip()
    return bool(stripped) and stripped[-1] in _TERMINATORS


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, line)`` for every line, ends exclusive of the newline."""
    spans: list[tuple[int, int, str]] = []
    position = 0
    for line in text.split("\n"):
        spans.append((position, position + len(line), line))
        position += len(line) + 1
    return spans


def _prose_blocks(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every run of consecutive non-blank prose lines."""
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    end = 0
    for line_start, line_end, line in _line_spans(text):
        if not line.strip() or _NOT_PROSE_RE.match(line):
            if start is not None:
                blocks.append((start, end))
                start = None
            continue
        if start is None:
            start = line_start
        end = line_end
    if start is not None:
        blocks.append((start, end))
    return blocks


def sentence_defects(text: str) -> tuple[SentenceDefect, ...]:
    """The six structural defects of class F that shipped to a live page.

    ``kind`` is one of:

    ``no_terminator``
        A marker run inside a running sentence with no terminator on its left:
        the sentence has no full stop where it needs one
        (``... from a nearly aligned initial state [52] The evidence resolves``).
    ``ends_on_function_word``
        A sentence whose last word is a preposition, a conjunction, an article
        or a pronoun (``... a pattern of colonial violence that.``, ``... attack
        the people they.``). The word list is closed and documented above; the
        six particles that read as adverbs are excluded.
    ``double_stop``
        Two full stops in a row that are not an ellipsis (``... roughly 16
        months..``).
    ``comma_before_stop``
        A comma in front of the full stop (``... rather than consensus [11],.``).
    ``no_clause_after_marker``
        A marker run that ends a sentence inside a paragraph and is followed by
        another sentence: the run carries no clause, and the sentence after it
        is uncited. Measured over the 31 papers this is ~2 per paper, against
        thousands of runs at the end of a paragraph, which are this project's
        accepted citation unit and are not reported.
    ``fragment_after_marker``
        A marker run glued to the preceding word, with no space and no
        terminator: a replacement sentence that swallowed its full stop
        (``... comparable to known monoamine neurotransmitters[7].``). 95 of
        these are in the corpus, 6 of them in the pineal-dmt paper alone, where
        the repair pass wrote them.

    Headings, image blocks, italic captions and ``[Source](url)`` lines are
    skipped: they are not prose. Reference lines are *not* skipped - a doubled
    stop in one is a defect a reader sees, and the reincarnation paper has one.
    A ``..`` inside a URL is not a prose defect either: an ADS bibcode
    (``1950PA.....58..278P``) carries one.

    What this costs, measured over the 31 papers' ``live.md`` and
    ``corrected.md`` (62 files): 142 ``no_clause_after_marker``, 67
    ``ends_on_function_word``, 64 ``fragment_after_marker``, 11
    ``comma_before_stop`` and 2 ``double_stop`` - about nine findings a paper.
    Three of those kinds are defects and two are review flags, and the docstring
    above says which. In particular ``ends_on_function_word`` fires on
    idiomatic stranded particles ("...built his hypothesis on.", "...not the
    other way around.") as well as on real fragments ("...a pattern of
    colonial violence that."): a mechanical check cannot tell those apart, and
    the preposition members of the list are where the noise is.

    Deliberately conservative: this reports punctuation a machine can decide.
    A missing clause, a hedge that was dropped or a marker on the wrong
    sentence is not in this list, and a clean paragraph returns an empty
    tuple rather than a guess.
    """
    if not text:
        return ()
    defects: list[SentenceDefect] = []
    for start, end in _prose_blocks(text):
        block = text[start:end]
        # Every rule is applied per line. A marker never spans a line in this
        # corpus, and the reference list is one block of consecutive lines whose
        # lines all end in "[Academic]" - judging a marker against the previous
        # line's end would report the whole bibliography.
        for line_start, line_end, _line in _line_spans(block):
            line = block[line_start:line_end]
            blanked = _blank_markers(line)

            for run in _MARKER_RUN_RE.finditer(line):
                before = line[: run.start()]
                tail = line[run.end() :].lstrip(" \t")
                glued = bool(before) and before[-1].isalnum()
                terminated = _left_is_terminated(before)
                if glued and not terminated:
                    defects.append(
                        SentenceDefect(
                            "fragment_after_marker", run.group(0).rstrip(), start + line_start + run.start()
                        )
                    )
                elif terminated and opens_like_a_sentence(tail):
                    defects.append(
                        SentenceDefect(
                            "no_clause_after_marker", run.group(0).rstrip(), start + line_start + run.start()
                        )
                    )
                elif before.strip() and not glued and opens_like_a_sentence(tail):
                    defects.append(
                        SentenceDefect(
                            "no_terminator", run.group(0).rstrip(), start + line_start + run.start()
                        )
                    )

            for pattern, kind in (
                (_DOUBLE_STOP_RE, "double_stop"),
                (_COMMA_BEFORE_STOP_RE, "comma_before_stop"),
            ):
                for match in pattern.finditer(blanked):
                    if any(url.start() <= match.start() < url.end() for url in _URL_RE.finditer(line)):
                        continue
                    defects.append(
                        SentenceDefect(kind, match.group(0), start + line_start + match.start())
                    )

            for sentence, (sentence_start, _sentence_end) in zip(
                split_sentences(blanked), _sentence_spans(blanked), strict=True
            ):
                tail_match = _TAIL_RE.search(sentence)
                if tail_match is None:
                    continue
                word = tail_match.group(1).lower().rstrip("'s")
                if word in _FUNCTION_WORDS:
                    defects.append(
                        SentenceDefect(
                            "ends_on_function_word",
                            tail_match.group(0),
                            start + line_start + sentence_start + tail_match.start(),
                        )
                    )

    return tuple(sorted(defects, key=lambda defect: (defect.offset, defect.kind)))
