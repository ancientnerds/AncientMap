"""The sentence-level evidence card: which source carries which sentence, as an audit artefact.

Owner decision, 2026-10-04: the paragraph stays the citation unit and the rendered paper gains
nothing. Measured over the 31 published papers, 1136/1136 reference entries are cited and 0 of
853 prose paragraphs carry no marker, while only 530 of 4261 sentences carry a marker of their
own (12.4 %); the sentence-level upgrade was declined. What a new paper does get is this card,
stored in `result_json` under "sentence_evidence": one entry per sentence of every prose
paragraph, the `[N]` markers of that sentence's paragraph, and a quote **located mechanically**
in the text of one of those sources (`pipeline.lyra.claim_support.locate_support`). The reader
sees the same paper; a reviewer reads which source supports which sentence without redoing the
research (docs/reports/theo-paper-defects-2026-10-04.md, classes A and D).

Two rules make the card honest:

* Nothing here is a model's word. A quote is a contiguous span of a fetched source text or it
  is not recorded. A sentence whose paragraph cites sources but whose text is in none of them
  is **unlocated** - listed in `unlocated` with the refs that failed - never omitted and never
  marked supported. That list, not the located count, is what a reviewer reads first: it is
  where the misattributed citations of the audit campaign (384) and the citations to sources
  that could never be read (177) show up before a paper ships.
* The markdown is read, never written. `anchors.paragraphs` is the walk, so image blocks,
  italic captions, `[Source](url)` trailers, headings and the References list contribute no
  sentence - the measurement trap of the defect report, where a naive paragraph count treats
  each picture's three stored blocks as prose and then reports half the paper as uncited. A
  piece that is nothing but a paragraph's marker run is no sentence either, for the same
  reason: it would put one empty row per paragraph into the list a reviewer reads first.

Out of scope: markers in the rendered paper, a verdict on whether a quote proves the sentence
(a located quote means the text carries the words, nothing more), a check of the reference list,
and any I/O. A pure function of the report and the texts it is given.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pipeline.lyra.claim_support import locate_support
from pipeline.lyra.text_sentences import sentence_span, split_sentences
from pipeline.studio.paper.anchors import MARKER_RE, Paragraph, paragraphs

#: The shape version stored with the card. Bump it when a field changes meaning; readers of an
#: old `result_json` keep the old meaning under the old number.
VERSION = 1


@dataclass(frozen=True)
class SentenceSupport:
    """One sentence of the paper and what the card can say about it.

    paragraph: index in reading order, the same index `anchors.paragraphs` and the publish
        gate's `report_paragraphs` give (0 is the hook, before the first h2).
    section: the h2 text as written, "" for the hook.
    sentence: the sentence with its citation markers removed and its whitespace collapsed -
        the text to check against a source, and the key `claim_task_ids` is keyed by.
    offset: the sentence's first character in the report, so a reader can go to it in the text.
    refs: the `[N]` markers of the sentence's **paragraph**, as the numbers the markers show
        ("7"). Paragraph level is the accepted unit; the card does not invent sentence markers.
    quote: the contiguous verbatim span of the named source's text, "" when none was located.
    quote_source: the `[N]` whose text carries the quote, "" when none was located.
    quote_start: where the quote starts in that source's text, -1 when none was located.
    claim_task_id: the claim-check task that judged this sentence, "" when none does.
    """

    paragraph: int
    section: str
    sentence: str
    offset: int
    refs: tuple[str, ...]
    quote: str
    quote_source: str
    quote_start: int
    claim_task_id: str

    def as_json(self) -> dict[str, Any]:
        """The entry as `result_json` stores it: the same fields, `refs` as a JSON list."""
        return {
            "paragraph": self.paragraph,
            "section": self.section,
            "sentence": self.sentence,
            "offset": self.offset,
            "refs": list(self.refs),
            "quote": self.quote,
            "quote_source": self.quote_source,
            "quote_start": self.quote_start,
            "claim_task_id": self.claim_task_id,
        }


def _plain(text: str) -> str:
    """Text without its citation markers, whitespace collapsed - the rule `paper/gates.py`
    applies to a paragraph's plain text, on one sentence instead of a whole block.

    A marker between two words leaves a space (so `in[1]the` reads `in the`); a marker
    anywhere else leaves nothing, because a marker written on a word - the pineal paper's
    "the top of the cerebellum[42]." - is part of that word's sentence, not a break in it.
    """

    def blank(match: re.Match[str]) -> str:
        before = text[match.start() - 1 : match.start()]
        after = text[match.end() : match.end() + 1]
        return " " if before.isalnum() and after.isalnum() else ""

    return " ".join(MARKER_RE.sub(blank, text).split())


def _refs(paragraph_text: str) -> tuple[str, ...]:
    """The paragraph's citation markers in the order they appear, without repeats: each
    marker's inner text, so `[7]` and `[S:0123456789ab]` give "7" and "S:0123456789ab"."""
    return tuple(dict.fromkeys(match[1:-1] for match in MARKER_RE.findall(paragraph_text)))


def _sentences(paragraph_text: str) -> list[tuple[int, str]]:
    """Every sentence of the paragraph as (offset within the block, text without its markers).

    The split is `lyra.text_sentences.split_sentences`, so abbreviations and initials stay
    inside their sentence; `sentence_span` gives each one's extent in the block itself.

    A piece that carries no words once its markers are removed is not a sentence and gets no
    entry. Every audited paper writes its paragraph-level markers as a run after the last
    full stop, which the splitter cuts off as a piece of its own - 32 such pieces in the
    baalbek paper alone - and a reader who works through `unlocated` first must not find
    one empty row per paragraph. The markers themselves are in `refs`, so nothing is lost.
    """
    out: list[tuple[int, str]] = []
    cursor = 0
    for part in split_sentences(paragraph_text):
        if not part:
            continue
        # A split part is a slice of the block; searching from the end of the previous
        # sentence keeps a repeated sentence on its own place.
        start = paragraph_text.find(part, cursor)
        if start < 0:
            raise ValueError(f"a sentence is not a slice of its paragraph: {part[:60]!r}")
        begin, end = sentence_span(paragraph_text, start)
        cursor = end
        plain = _plain(paragraph_text[begin:end])
        if plain:
            out.append((begin, plain))
    return out


def _support(
    para: Paragraph,
    offset: int,
    sentence: str,
    refs: tuple[str, ...],
    source_texts: Mapping[str, str],
    claim_task_ids: Mapping[str, str],
) -> SentenceSupport:
    """The entry for one sentence: its paragraph's refs, and the first of them whose text
    carries the sentence. `sentence` is never empty - `_sentences` drops a piece that is
    nothing but markers - and a ref the caller holds no text for is skipped rather than
    reported as unlocatable: the caller knows which sources it could not fetch, the card
    knows only what it was given.
    """
    quote = quote_source = ""
    quote_start = -1
    for ref in refs:
        text = source_texts.get(ref)
        if text is None:
            continue
        found = locate_support(sentence, text)
        if found is not None:
            quote, quote_source, quote_start = found.quote, ref, found.start
            break
    return SentenceSupport(
        paragraph=para.index,
        section=para.section,
        sentence=sentence,
        offset=offset,
        refs=refs,
        quote=quote,
        quote_source=quote_source,
        quote_start=quote_start,
        claim_task_id=claim_task_ids.get(sentence, ""),
    )


def build_evidence_card(
    report: str,
    source_texts: Mapping[str, str],
    *,
    claim_task_ids: Mapping[str, str] | None = None,
) -> dict:
    """The sentence-level evidence card of `report`, the artefact `result_json` keeps under
    "sentence_evidence".

    Args:
        report: The paper's markdown, read and never written.
        source_texts: The text of each cited source, keyed by the number its marker shows in
            this paper ("7" for `[7]`) - not by source id; the caller maps ids to numbers with
            `numbering.CitationRegistry.reference_numbers`. A ref with no entry here is a
            source whose text nobody holds, and every sentence of the paragraph citing it is
            unlocated.
        claim_task_ids: The claim-check task that judges each sentence, keyed by the sentence
            text exactly as the card records it (markers removed, whitespace collapsed). A
            task id is `kind-<prompt hash>` (`studio.handoff.Task.task_id`), so it is the
            caller's to look up; "" when a sentence answers no task.

    Returns:
        {
          "version": 1,
          "paragraphs": [{"index": int, "section": str, "sentences": [SentenceSupport...]}],
          "counts": {"sentences": int, "with_refs": int, "located": int, "unlocated": int,
                     "sentences_without_refs": int},
          "unlocated": [{"paragraph": int, "sentence": str, "refs": [str...]}],
        }
        with `refs` a list, the rest as written. `counts` holds `with_refs` =
        `located` + `unlocated` and `sentences` = `with_refs` + `sentences_without_refs` by
        construction. `unlocated` names every sentence whose paragraph cites a source and no
        quote was located in any of them: the report a reviewer reads first.

    Offsets are character offsets into `report` with CRLF folded to LF, the form
    `anchors.paragraphs` walks; a stored report is LF, so they are offsets into the report.
    """
    tasks: Mapping[str, str] = claim_task_ids or {}
    normalized = report.replace("\r\n", "\n")
    out: list[dict[str, Any]] = []
    unlocated: list[dict[str, Any]] = []
    sentences = located = without_refs = 0
    cursor = 0
    for para in paragraphs(normalized):
        # The paragraph's text is a contiguous slice of the report; each one is found after
        # the previous, so a repeated paragraph keeps its own place.
        start = normalized.find(para.text, cursor)
        if start < 0:
            raise ValueError(
                f"paragraph {para.index} is not a slice of the report: {para.text[:60]!r}"
            )
        cursor = start + len(para.text)
        refs = _refs(para.text)
        rows: list[dict[str, Any]] = []
        for begin, sentence in _sentences(para.text):
            entry = _support(para, start + begin, sentence, refs, source_texts, tasks)
            rows.append(entry.as_json())
            sentences += 1
            if not refs:
                without_refs += 1
            elif entry.quote:
                located += 1
            else:
                unlocated.append(
                    {"paragraph": para.index, "sentence": entry.sentence, "refs": list(entry.refs)}
                )
        out.append({"index": para.index, "section": para.section, "sentences": rows})
    return {
        "version": VERSION,
        "paragraphs": out,
        "counts": {
            "sentences": sentences,
            "with_refs": sentences - without_refs,
            "located": located,
            "unlocated": len(unlocated),
            "sentences_without_refs": without_refs,
        },
        "unlocated": unlocated,
    }
