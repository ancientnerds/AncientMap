"""Mechanical claim gate: a paper whose citations cannot be traced is refused.

The production gate (`theo_citations.validate_paper_artifact`, `theo_publishing.check_quality`
and `check_images`) is artifact-only: marker syntax, list/prose agreement, the tier tag, the
image file's existence and a recomputed LLM verdict. The 31-paper audit
(`docs/reports/theo-paper-defects-2026-10-04.md`, 2 105 findings, 602 of them supported as
written) measured the gap: not one of those papers failed the existing gate. This module is
the missing half - the rules that need the *fetched source texts*, not just the artifact.

Eight rules, reported in this order:

===  ===========  ==========================================  =====  ==========
id    class        what it decides                            count  rule
===  ===========  ==========================================  =====  ==========
1     A, D         every [n] has a located quote in source n   561  located_sentence
2     D            a [n] whose source has no text at all       177  unreadable_marker
3     B            a number of the paragraph is not in the     858  number_exact
                     located quote
4     C            a site/accession code is in no cited source     site_code
5     E            a DOI/ISBN/PMID is in no cited source           identifier
6     E            a retraction claim whose quote lacks the        retraction
                     retraction word
7     F            a structural text defect                        sentence_defect
8     B, C, E      a specific of the paragraph is in none of      unsupported_specific
                     its cited sources
===  ===========  ==========================================  =====  ==========

Rule 8 is the aggregate behind rules 1-6: it is reported only for a sentence that no more
specific rule already reported, so one defect never becomes five issues.

**What rule 1 decides, and what it refuses to decide.** Rule 1 asks whether a marker's
source carries the paragraph's *verifiable content*: its persons, titles, dates,
measurements, quotations, institutions, numbers, site codes and record identifiers. Those
are the things a fetched text either contains or does not, and they are what
`claim_support.locate_support` scores a window against.

A paragraph with none of that is **not** a rule-1 failure. "The block rests where the
workers left it and the stone still shows the marks of the tools that cut it from the hill"
asserts nothing a reader can check against a source, so `locate_support` returns `None` for
it - and `None` here means *undecidable*, not *unsupported*. `locate_support` needs at least
two matched specifics before it accepts a window, which is the right threshold for support
and the wrong instrument for padding. Reporting it would make the gate refuse the filler a
writer pads a draft with, and a gate that fires on padding is a gate whose output stops
being read. Padding is a word count and an editor's judgement (`gate_structure`'s floor and
the writer's own eye), not a citation defect, so this module says nothing about it.

Every other reason for a `None` is still reported: a paragraph with verifiable content that
its cited source does not carry is class A, and that is the pineal scale claim on `[11]`,
the stargate session on `[1]`, and the ufos panel year on `[38]`.

Every function is a pure function of `(report, source_texts)`. No network, no database, no
model call, no file read at import time - so the same call runs in the publish gate, in a
CLI and in a test.

**Deliberately out of scope** (each exclusion is a decision, not an oversight):

- Reference numbering, list/prose agreement and the tier tag. `validate_paper_artifact`
  owns those and answers before this gate runs.
- Whether a *picture* shows what its caption says (class G). Nothing here opens an image;
  `check_images` and the `verified:no` flag own it.
- Whether a write was idempotent per input hash (class H). Not a property of the text.
- The entity-merge half of class C. This gate can see that a site code was copied, not
  that two named entities were fused; `claim_site_codes` sees strings, not identities.
- Quotations spliced out of two sentences of a source (class B, `panspermia`). Deciding
  contiguity is `claim_support.locate_support`'s contract, not a separate rule here.
- Pictures, captions and `[Source](url)` trailers as paragraphs. They are filtered out
  before any rule runs - see the paragraph walk below.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pipeline.lyra import theo_publishing
from pipeline.lyra.claim_support import (
    Located,
    claim_identifiers,
    claim_numbers,
    claim_site_codes,
    is_retraction_claim,
    locate_support,
    numbers_absent_from,
    sentence_defects,
)
from pipeline.lyra.hallucination_gate import Specific, extract_specifics, verify_against_pack
from pipeline.lyra.text_sentences import sentence_span, split_sentences

# ---------------------------------------------------------------------------
# The rules, in the order they are reported
# ---------------------------------------------------------------------------

LOCATED_SENTENCE = "located_sentence"
UNREADABLE_MARKER = "unreadable_marker"
NUMBER_EXACT = "number_exact"
SITE_CODE = "site_code"
IDENTIFIER = "identifier"
RETRACTION = "retraction"
SENTENCE_DEFECT = "sentence_defect"
UNSUPPORTED_SPECIFIC = "unsupported_specific"

#: The reporting order. `check_paper` merges its two checks' issues on this key, so the
#: combined list reads rule by rule however the walk produced them.
RULE_ORDER: tuple[str, ...] = (
    LOCATED_SENTENCE,
    UNREADABLE_MARKER,
    NUMBER_EXACT,
    SITE_CODE,
    IDENTIFIER,
    RETRACTION,
    SENTENCE_DEFECT,
    UNSUPPORTED_SPECIFIC,
)
_RULE_RANK = {rule: rank for rank, rule in enumerate(RULE_ORDER)}

#: A citation marker as the artifact writes it. Grouped markers (`[4, 7, 12]`) are already
#: expanded by `theo_citations.normalize_grouped_markers` on a final artifact and are
#: rejected by `validate_paper_artifact` if they are not, so they are not handled here.
CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")

#: The retraction vocabulary of rule 6. A source that says none of these has not retracted,
#: withdrawn, corrected, superseded or erratum'd anything, whatever the paper says.
RETRACTION_WORD_RE = re.compile(
    r"retract|withdraw|correct(?:ion|ed|ive)?|supersed|erratum|correction notice",
    re.IGNORECASE,
)

#: How much of a located quote a detail quotes back, so a reader can see what was found.
#: A defect at the end of a sentence is invisible below a full sentence, so the cap is a
#: sentence or two rather than a log line.
_QUOTE_PREVIEW = 240


@dataclass(frozen=True)
class Issue:
    """One rule failure, naming the marker or sentence it is about.

    `paragraph` is the index in `theo_publishing.report_paragraphs` (reading order over
    prose paragraphs, 0-based, images and captions already filtered out) - the same index
    space the evidence anchors and the studio's `anchors.paragraphs` use, so an issue can
    be handed straight to a writer without a second walk of the paper.
    """

    rule: str
    detail: str
    paragraph: int
    marker: str | None = None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class _CitedSource:
    """The `verify_against_pack` source shape: a title and a snippet, nothing else."""

    __slots__ = ("title", "snippet")

    def __init__(self, text: str) -> None:
        self.title = ""
        self.snippet = text


def _texts_by_number(source_texts: Mapping[str | int, str]) -> dict[str, str]:
    """Normalize the caller's keys to citation numbers as strings.

    A report's markers are strings and the studio's registry is keyed by int, so both are
    accepted. A key that is present but empty, and a key that is absent, are the same thing
    downstream: a reference with no text, which rule 2 refuses.
    """
    return {str(number): (text or "") for number, text in source_texts.items()}


def _prose_paragraphs(report: str) -> list[str]:
    """The report's prose paragraphs, in reading order.

    `theo_publishing.report_paragraphs` is the walk the publish gate, the evidence-anchor
    resolver and the studio's `anchors.paragraphs` already share: `split_artifact` drops the
    References section, and `_is_non_prose_block` drops every heading, image markdown line,
    italic caption, `[Source](url)` trailer and lone link. That last half is the report's
    measurement trap - a picture is three stored paragraphs, so a naive count calls a
    24-image paper 72 paragraphs and then reports half the paper as uncited. This gate
    inherits the filter rather than repeating the walk.
    """
    return theo_publishing.report_paragraphs(report)


def _sentences(paragraph: str) -> list[str]:
    """The paragraph's sentences, stripped, in order."""
    return [s.strip() for s in split_sentences(paragraph) if s.strip()]


def _preview(text: str) -> str:
    """A one-line, length-capped excerpt of a source quote for the detail string."""
    flat = " ".join(text.split())
    return flat if len(flat) <= _QUOTE_PREVIEW else flat[: _QUOTE_PREVIEW - 1] + "…"


def _prose_only(paragraph: str) -> str:
    """The paragraph with its citation markers removed.

    A marker is apparatus, not a claim: `[7]` must not be read as the number seven when
    rules 3-5 and 8 ask what the paragraph asserts. `locate_support` still gets the
    paragraph as written, because the locating contract is A1's and the marker is part of
    the text a reader sees.
    """
    return CITATION_MARKER_RE.sub(" ", paragraph)


def _in_any(text: str, haystacks: list[str]) -> bool:
    """True when `text` occurs in at least one source, case-folded.

    Site codes and identifiers are copied strings (rules 4 and 5); the comparison is a
    case-folded containment so `LA 11568` matches a source that writes `la 11568`.
    """
    needle = text.casefold()
    return any(needle in hay.casefold() for hay in haystacks)


def _verifiable_content(prose: str) -> tuple[str, ...]:
    """Everything in `prose` a source could carry, or fail to carry.

    The claim-specific set `claim_support.locate_support` scores a window against: a
    person, a title, a date, a measurement, a quotation, an institution, plus the numbers
    and the copied strings (site codes, DOIs) that are never part of
    `hallucination_gate.extract_specifics`. Tagged by kind so a value that repeats across
    kinds is still counted once per kind.

    Empty means the sentence asserts nothing a reader can check against the fetched text -
    "the block rests where the workers left it and the stone still shows the marks of the
    tools that cut it from the hill" - and rule 1 has nothing to decide about it.
    """
    out = [f"{specific.kind}:{specific.text}" for specific in extract_specifics(prose)]
    out += [f"number:{value}" for value in claim_numbers(prose)]
    out += [f"code:{value}" for value in claim_site_codes(prose)]
    out += [f"identifier:{value}" for value in claim_identifiers(prose)]
    return tuple(dict.fromkeys(out))


def _absent_from_source(prose: str, text: str) -> tuple[str, ...]:
    """The paragraph's hard values that the source text does not contain at all.

    A number, a date and a record identifier are the values a reader can check against
    the fetched text at a glance, and they are what a `located_sentence` detail has to
    name: "the source does not carry this" is only actionable if it says what is missing.
    `1997` where the record reads `1998` is the case the report calls out.
    """
    out: list[str] = []
    for value in numbers_absent_from(prose, text):
        out.append(value)
    for specific in extract_specifics(prose):
        if specific.kind != "date" or specific.text in out:
            continue
        if specific.text.casefold() not in text.casefold():
            out.append(specific.text)
    for identifier in claim_identifiers(prose):
        bare = identifier.split(":", 1)[-1]
        if bare not in out and bare.casefold() not in text.casefold():
            out.append(bare)
    return tuple(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Rule 1-6: the marker rules, one paragraph at a time
# ---------------------------------------------------------------------------


def _carrying_sentence(paragraph: str, position: int) -> str:
    """The sentence of `paragraph` the marker at `position` stands in.

    Rule 1 asks for a *sentence*: "a marker requires a located sentence". The
    marker itself stays paragraph-level (1,136 of 1,136 references cited, 0 of
    853 paragraphs uncited in the 31-paper corpus, and the sentence-level
    citation upgrade was declined), so the question "which text must this
    source carry" is answered on the sentence the marker sits in and not on the
    whole paragraph: a paragraph that states one claim from [1] and another from
    [2] would otherwise hold neither marker, because each is asked to carry the
    other one's specifics. Measured on the studio fixture, whose paragraph
    "The quarry stone of Baalbek is a local limestone, and the temple of Jupiter
    stands on a podium of 800 tons blocks [3] [2]." has no source carrying both
    clauses.
    """
    start, end = sentence_span(paragraph, position)
    return paragraph[start:end]


def _check_markers(paragraph: str, index: int, texts: dict[str, str]) -> list[Issue]:
    """Rules 1 and 2 for one paragraph, one issue per marker.

    An unlocated marker and an unreadable reference are the same decision taken in opposite
    order, so they share one pass and rule 2 wins: a dead link is reported as a dead link,
    not as a support failure that can be argued about.
    """
    issues: list[Issue] = []
    for match in CITATION_MARKER_RE.finditer(paragraph):
        number = match.group(1)
        marker = match.group(0)
        text = texts.get(number, "")
        if not text.strip():
            issues.append(
                Issue(
                    rule=UNREADABLE_MARKER,
                    detail=(
                        f"{marker} carries a marker, but reference {number} has no fetched "
                        f"text, so nothing in it can be located. A reference that could not "
                        f"be read may stand in the list as a bibliographic fact but may not "
                        f"carry a marker (class D)."
                    ),
                    paragraph=index,
                    marker=marker,
                )
            )
            continue
        claim = _prose_only(_carrying_sentence(paragraph, match.start()))
        support = locate_support(claim, text)
        if support is None:
            # A sentence that asserts nothing checkable makes rule 1 undecidable, not
            # failed: `locate_support` needs two matched specifics before it accepts a
            # window, so it returns None for a sentence with no specifics at all. Reporting
            # that as "this marker is not supported" would be a citation defect where the
            # truth is that there is no claim in the sentence - padding, which the word
            # count and the writer's judgement own. See the module docstring.
            if not _verifiable_content(claim):
                continue
            issues.append(
                Issue(
                    rule=LOCATED_SENTENCE,
                    detail=(
                        f"{marker} is not supported: its sentence is not located in the "
                        f"fetched text of reference {number} (class A). The marker asserts "
                        f"that this reference carries this sentence."
                        + _naming(_absent_from_source(claim, text))
                    ),
                    paragraph=index,
                    marker=marker,
                )
            )
            continue
    return issues


def _naming(values: tuple[str, ...], limit: int = 6) -> str:
    """A detail clause naming the values a source does not carry, or nothing at all.

    Empty when the source carries every value, so the detail does not promise something
    it cannot show.
    """
    if not values:
        return ""
    shown = ", ".join(values[:limit])
    if len(values) > limit:
        shown += f", and {len(values) - limit} more"
    return f" The source carries none of: {shown}."


def _sentence_locations(
    paragraph: str, texts: dict[str, str]
) -> dict[str, list[tuple[str, Located]]]:
    """Every sentence of the paragraph that each readable reference locates.

    Rules 3 and 6 ask a *sentence*-sized question, so they need a sentence-sized quote.
    Rule 1's paragraph-sized `locate_support` call cannot answer them:
    `claim_support.locate_support` requires a located window to carry **every** number,
    date and measurement of the claim, so a paragraph-scoped call is `None` for exactly
    the paragraphs rule 3 exists to catch - the claim is sharpened, so one of its numbers
    is not in the window. Passing the whole paragraph to rule 3 would therefore make it
    unreachable; passing the sentence gives the quote the reader is looking at, which is
    what "the located quote" has to mean for a number rule to be decidable at all.

    Returns marker -> the located (sentence, quote) pairs, per readable reference.
    """
    markers: dict[str, str] = {}
    for match in CITATION_MARKER_RE.finditer(paragraph):
        text = texts.get(match.group(1), "")
        if text.strip():
            markers[match.group(0)] = text
    out: dict[str, list[tuple[str, Located]]] = {marker: [] for marker in markers}
    for sentence in _sentences(paragraph):
        if not _prose_only(sentence).strip():
            continue
        for marker, text in markers.items():
            support = locate_support(sentence, text)
            if support is not None:
                out[marker].append((sentence, support))
    return out


def _check_numbers(
    paragraph: str, index: int, located: dict[str, list[tuple[str, Located]]]
) -> list[Issue]:
    """Rule 3: a number of a sentence is not in the quote its reference gives it (class B).

    A recovered or generated sentence may never be stronger than the source that carries
    it, and a number is where the sharpening shows: the source says over 50 square
    kilometres and the paper says 150. Checked per marker, so a number that one cited
    reference does not carry but another does is reported against the reference that
    should be carrying it - which is what the `squatter-man` repair did, moving the area
    onto the source that has it.

    **Known limit, stated rather than hidden: under `claim_support.locate_support`'s
    contract this rule cannot currently fire.** The function accepts a window only when it
    carries *every* number, date and measurement of the claim, so a sentence that sharpens
    a number does not locate at all - rule 1 refuses the marker first, and its detail names
    the values the source carries none of. A sentence that does locate has, by construction,
    all its numbers in the quote, and `numbers_absent_from` returns empty. The rule is wired
    and reported because it is the right rule for the class and the contract above it is what
    makes it subsumed; the audited 31 agree: 858 of the class-B findings are "unsupported",
    in no source at all, and only 79 are `contradicted`.

    A second limit: the comparison is a containment test on digits, so a wrong year that
    also occurs legitimately in the source is not separable from a right one. The
    `stargate` record reads `A 1974-2022 Systematic Review` and the paper says 2022 where
    the record's own year is 2023; the 2022 is present, so neither rule 3 nor rule 1 sees
    it. Measured over the campaign's 24 `replace_date` findings this is the common shape.
    Catching it needs a date-aware comparison, not a numeric one.
    """
    issues: list[Issue] = []
    for marker, pairs in located.items():
        for sentence, support in pairs:
            missing = numbers_absent_from(_prose_only(sentence), support.quote)
            if not missing:
                continue
            values = ", ".join(missing)
            issues.append(
                Issue(
                    rule=NUMBER_EXACT,
                    detail=(
                        f"{marker}: the located quote does not carry the sentence's "
                        f"value(s) {values} (class B). The claim is stronger than the "
                        f"source that is cited for it. Quote: “{_preview(support.quote)}” "
                        f"Sentence: “{_preview(sentence)}”"
                    ),
                    paragraph=index,
                    marker=marker,
                )
            )
    return issues


def _check_retraction(
    paragraph: str, index: int, located: dict[str, list[tuple[str, Located]]]
) -> list[Issue]:
    """Rule 6: a retraction claim whose located quote lacks the retraction word (class E).

    An assertion that a work was retracted is a claim about the bibliographic record. If
    the paragraph asserts it and the fetched text it cites does not say it, the assertion is
    not supported by that reference - the gate cannot know whether a retraction exists
    elsewhere, and does not pretend to: it checks the quote, which is the part that is
    mechanical.

    Reported once per marker that has located evidence and no retraction word in it. A
    marker with no located evidence at all is rule 1's business, and reporting it here as
    well would charge one defect twice.

    Reachable only when the paragraph locates *and* asserts a retraction. The audited
    stargate case does not: its paragraph carries six dates, and `locate_support` requires
    every one of them in the window, so the marker is refused by rule 1 before this rule is
    reached. A retraction claim nothing cites is `located_sentence`; a retraction claim the
    reference's own words sit next to is this rule.
    """
    if not is_retraction_claim(paragraph):
        return []
    sentence = next((s for s in _sentences(paragraph) if is_retraction_claim(s)), paragraph)
    issues: list[Issue] = []
    for marker, pairs in located.items():
        if not pairs:
            continue
        if any(RETRACTION_WORD_RE.search(support.quote) for _s, support in pairs):
            continue
        issues.append(
            Issue(
                rule=RETRACTION,
                detail=(
                    f"{marker}: the paragraph asserts a retraction, but the located quote "
                    f"contains no retraction word (retract, withdraw, correct, supersede, "
                    f"erratum) (class E). Sentence: “{_preview(sentence)}”"
                ),
                paragraph=index,
                marker=marker,
            )
        )
    return issues


def _check_copied_strings(
    paragraph: str,
    index: int,
    cited_texts: list[str],
    rule: str,
    values: tuple[str, ...],
    what: str,
) -> list[Issue]:
    """Rules 4 and 5: a code or identifier of the paragraph is in no cited source.

    Shared because both are the same rule about a different string: a site code, accession
    number, DOI, ISBN or PMID is copied from the fetched record and never recalled. The
    check is over the paragraph's whole readable citation set, not over one marker, because
    the value may legitimately come from any reference the paragraph cites.
    """
    if not values:
        return []
    issues: list[Issue] = []
    for value in values:
        if _in_any(value, cited_texts):
            continue
        issues.append(
            Issue(
                rule=rule,
                detail=(
                    f"{what} “{value}” is in the prose but in none of the texts of this "
                    f"paragraph's cited references. Identifiers and site codes are copied "
                    f"from the fetched record, never recalled (class "
                    f"{'C' if rule == SITE_CODE else 'E'})."
                ),
                paragraph=index,
            )
        )
    return issues


def _unsupported_sentences(
    paragraph: str, cited_texts: list[str], skip: set[str]
) -> list[tuple[str, Specific]]:
    """Rule 8's findings: a specific of the paragraph in none of its cited sources.

    The verification is `hallucination_gate.verify_against_pack`, the function the
    hallucination gate already runs, so the normalization (honorifics stripped, a person's
    last name as a fallback) is one implementation rather than two.
    """
    specifics = extract_specifics(_prose_only(paragraph))
    if not specifics or not cited_texts:
        return []
    sources = {str(i): _CitedSource(text) for i, text in enumerate(cited_texts)}
    unsupported = verify_against_pack(specifics, "", sources, "")
    found: list[tuple[str, Specific]] = []
    seen: set[tuple[str, str]] = set()
    for specific in unsupported:
        key = (specific.kind, specific.text.casefold())
        if key in seen:
            continue
        seen.add(key)
        sentence = specific.sentence or paragraph
        if sentence.casefold() in skip:
            continue
        found.append((sentence, specific))
    return found


# ---------------------------------------------------------------------------
# The public checks
# ---------------------------------------------------------------------------


def check_paragraph_markers(report: str, source_texts: Mapping[str | int, str]) -> list[Issue]:
    """Check every citation marker of every prose paragraph against its fetched text.

    Runs rules 1-6 and 8 for each paragraph in reading order, then returns the issues
    grouped by rule in `RULE_ORDER` so the output reads rule by rule rather than paragraph
    by paragraph. `paragraph` on each `Issue` is the index in `report_paragraphs`.

    A paragraph with no citation marker is not checked: with no cited source there is
    nothing to trace a claim against, and `theo_citations.validate_paper_artifact` already
    reports it as an `uncited_paragraphs` artifact defect. Skipping it here keeps rule 8
    from reporting every proper noun in an uncited paragraph as unsupported.

    A paragraph whose only markers carry a sentence with no verifiable content is also not
    checked by rule 1, for the reason in the module docstring: with nothing a source could
    carry or fail to carry, rule 1 is undecidable rather than failed. Rule 2 still applies
    there, because "this reference could not be read" is a fact about the reference, not
    about the sentence.

    Out of scope: the artifact's own rules (marker syntax, list/prose agreement, the tier
    tag) and every image question - see the module docstring.
    """
    texts = _texts_by_number(source_texts)
    issues: list[Issue] = []
    for index, paragraph in enumerate(_prose_paragraphs(report)):
        numbers = [m.group(1) for m in CITATION_MARKER_RE.finditer(paragraph)]
        if not numbers:
            continue
        # Rules 1 and 2 decide per marker, but each rule is about the whole paragraph, so a
        # paragraph with a failed marker counts as fully reported. Rules 3 and 6 name one
        # sentence, so only that sentence is held back from rule 8 - the rest of the
        # paragraph is still checked for unsupported specifics.
        marker_issues = _check_markers(paragraph, index, texts)
        sentence_locations = _sentence_locations(paragraph, texts)
        sentence_issues = _check_numbers(paragraph, index, sentence_locations)
        sentence_issues += _check_retraction(paragraph, index, sentence_locations)
        readable = [texts[number] for number in numbers if texts.get(number, "").strip()]
        prose = _prose_only(paragraph)
        copied = _check_copied_strings(
            paragraph,
            index,
            readable,
            SITE_CODE,
            claim_site_codes(prose),
            "site/accession code",
        )
        copied += _check_copied_strings(
            paragraph,
            index,
            readable,
            IDENTIFIER,
            claim_identifiers(prose),
            "identifier",
        )
        issues.extend(marker_issues)
        issues.extend(sentence_issues)
        issues.extend(copied)
        reported: set[str] = set()
        if marker_issues:
            reported |= {s.casefold() for s in _sentences(paragraph)}
            reported.add(paragraph.casefold())
        elif copied:
            reported |= {s.casefold() for s in _sentences(paragraph)}
        for sentence, specific in _unsupported_sentences(paragraph, readable, reported):
            issues.append(
                Issue(
                    rule=UNSUPPORTED_SPECIFIC,
                    detail=(
                        f"{specific.kind} “{_preview(specific.text)}” is in the prose but "
                        f"in none of the texts of this paragraph's cited references. "
                        f"Sentence: “{_preview(sentence)}”"
                    ),
                    paragraph=index,
                )
            )
    return sorted(issues, key=lambda issue: _RULE_RANK[issue.rule])


def check_sentence_structure(report: str) -> list[Issue]:
    """Rule 7: the structural text defects, forwarded from `claim_support.sentence_defects`.

    All six of the report's class-F defects shipped to live pages in the audited 31, and
    two of them were introduced by the repair pass itself - which is the reason the check
    belongs in the gate and not in a reviewer's eye. A sentence cut mid-clause, a marker
    with no full stop after it, a comma left in front of the full stop, a doubled full
    stop, a marker run that carries no clause, a replacement that swallowed its full stop.

    Each defect's `text` is the smallest fragment that shows it, anchored at `offset`, so
    the sentence around it is recovered here with `text_sentences.sentence_span` - the
    widening `claim_support` names as the caller's job. A detail that shows only ".." is
    not actionable.

    Takes no source texts: these are properties of the text alone.

    Out of scope: prose citing a reference the list does not contain. That is a
    disagreement between the prose and the References section rather than a property of a
    sentence, and `theo_citations.validate_paper_artifact` already refuses it as an
    `orphaned_refs` issue.
    """
    issues: list[Issue] = []
    for index, paragraph in enumerate(_prose_paragraphs(report)):
        for defect in sentence_defects(paragraph):
            start, end = sentence_span(paragraph, defect.offset)
            sentence = paragraph[start:end].strip()
            marker_match = CITATION_MARKER_RE.search(defect.text)
            issues.append(
                Issue(
                    rule=SENTENCE_DEFECT,
                    detail=(
                        f"{defect.kind} (class F) at offset {defect.offset} of the paragraph: "
                        f"“{_preview(defect.text)}” in the sentence "
                        f"“{_preview(sentence)}”"
                    ),
                    paragraph=index,
                    marker=marker_match.group(0) if marker_match else None,
                )
            )
    return issues


def check_paper(report: str, source_texts: Mapping[str | int, str]) -> list[Issue]:
    """Every rule, in `RULE_ORDER`: `check_paragraph_markers` then `check_sentence_structure`.

    The two checks are concatenated and stably regrouped by the rule rank, so the combined
    list reads rule 1, 2, 3, 4, 5, 6, 7, 8 even though `sentence_defect` (7) is produced by
    the second function and `unsupported_specific` (8) by the first.
    """
    issues = check_paragraph_markers(report, source_texts) + check_sentence_structure(report)
    return sorted(issues, key=lambda issue: _RULE_RANK[issue.rule])
