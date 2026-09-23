"""S2 sentences: every numbered sentence of a pinned text, the spans each offers, and the pool.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, pipeline "S2
SENTENCES" and writer "ASSEMBLY"; the contracts are `docs/procedures/PHASE4_CONTRACTS.md` section
3. Work item WB-B2. Deterministic: no network, no model, no clock.

The text is the pinned `src.<id>.txt` of a Wikipedia source (`W` or `T.<lang>`): TextExtracts plain
text, NFC, `\\n` line ends, section headings on their own line as `== History ==`. Each line that is
not a heading is split with `pipeline.lyra.text_sentences.split_sentences` (after the WB-B1 fix), and
each piece is found again in its line, so a sentence carries exact `[start, end)` offsets into the
pinned text. The index counts the whole split from 1: `W12` is the twelfth sentence of `src.W` and
keeps that id whatever the pool keeps.

Spans (Track B's reading of the design, recorded in the contracts document)
--------------------------------------------------------------------------
A span's range is exactly the text the prompt shows after its id and exactly what the assembler
removes (edit 1); edits 2-5 run after it. Every range carries the delimiter the removal must take
with it. "Top level" means outside every parenthesis; a sentence whose parentheses do not balance
offers no span at all. A *delimiter comma* is a top-level comma followed by a space, so the comma
of `4,500` never delimits anything. Spans are offered only on a sentence that ends in `.`, `!` or
`?`, the punctuation edit 5 puts the marker in front of.

* `p` - a top-level balanced parenthesis `(...)` with the space in front of it: `" (c. 30 m)"`. At
  the start of the sentence the space after it instead (`"(...) "`); with no space on either side,
  the parenthesis alone.
* `a` - a paired insertion: from a delimiter comma through the next delimiter comma, `", built by
  Khufu,"`, or from the space before a spaced dash (` - ` as en or em dash) through the next one.
  The pair is the insertion's delimiter, so both marks go: `A, X, B` becomes `A B`, never the
  broken `A, B` that removing one comma would leave.
* `l` - a leading phrase of at most 6 tokens before the first delimiter comma, with that comma and
  the space after it: `"In 1900, "`. Edit 4 restores the capital of what follows.
* `t` - the last comma segment: from the last delimiter comma up to, not including, the final
  punctuation: `", whose tomb lies nearby"`.

No span whose range contains a protected token (`model4.PROTECTED_TOKENS`: hedges, negations,
contrast, refutation, restriction) is offered. Spans of different kinds may overlap - an `a` and the
`t` after it share a comma - and a pick that drops two partially overlapping spans is refused by
`select_stage.parse_selection`; a span nested in another is fine (the outer one is the range).

The pool
--------
`candidate_pool` offers the lead and the first 6 sentences of each section that is not excluded,
counting only sentences that can be published: a complete sentence (`is_complete_sentence`) that
ends in `.`, `!` or `?` and is 25-400 characters long. Lane S first keeps only sentences that carry a
stored name or alias, or sit under a heading that carries one. The pool stops before the 121st
sentence or the 24,001st character, and stays in source order.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# `phase4` appends the repository root to the path, so `pipeline.*` resolves after it.
from phase4 import model4 as M  # noqa: E402
from pipeline.lyra.text_sentences import is_complete_sentence, split_sentences  # noqa: E402

#: A heading line of a TextExtracts plain-text extract: `== History ==`, `=== Middle Ages ===`.
HEADING = re.compile(r"(?P<marks>={2,})[ \t]*(?P<title>\S.*?)[ \t]*(?P=marks)")

#: Sections whose text is never offered: reference apparatus and popular culture. Compared after
#: casefolding. A subsection is excluded by its own title (the apparatus titles recur at level 3).
EXCLUDED_SECTIONS = frozenset(
    {
        "see also", "references", "notes", "footnotes", "citations", "sources", "bibliography",
        "further reading", "external links", "gallery", "literature", "works cited",
        "notes and references", "references and notes", "explanatory notes",
        "in popular culture", "popular culture",
    }
)  # fmt: skip

SENTENCES_PER_SECTION = 6
MAX_POOL_SENTENCES = 120
MAX_POOL_CHARS = 24_000
#: What a published sentence may be (V5 bounds it at 25-400 characters); a longer or shorter one
#: is not offered at all, so a pick of it cannot hold the whole site.
MIN_SENTENCE_CHARS = 25
MAX_SENTENCE_CHARS = 400
#: How long a leading phrase (`l`) may be, in whitespace tokens.
MAX_LEADING_TOKENS = 6
TERMINAL = ".!?"
DASHES = "–—"  # en dash, em dash


def _protected_pattern() -> re.Pattern[str]:
    """One regex for every entry of `model4.PROTECTED_TOKENS`, by the list's own entry rules.

    Whole words, case-insensitive; a trailing `*` matches any word that starts with the rest; an
    entry with a space is a phrase of consecutive words; `c.` and `ca.` carry their full stop.
    """
    alternatives = []
    for entries in M.PROTECTED_TOKENS.values():
        for entry in entries:
            if entry.endswith("*"):
                alternatives.append(rf"\b{re.escape(entry[:-1])}\w*")
            elif entry.endswith("."):
                alternatives.append(rf"\b{re.escape(entry)}")
            else:
                words = r"\s+".join(re.escape(word) for word in entry.split())
                alternatives.append(rf"\b{words}\b")
    return re.compile("|".join(alternatives), re.IGNORECASE)


PROTECTED = _protected_pattern()


def carries_protected_token(text: str) -> bool:
    """True when `text` contains a hedge, negation, contrast, refutation or restriction word."""
    return PROTECTED.search(text) is not None


# ------------------------------------------------------------------------------------ the split


def split_source(source_id: str, text: str) -> tuple[M.Sentence, ...]:
    """Every sentence of the pinned text, numbered from 1, with its section and offered spans."""
    sentences: list[M.Sentence] = []
    section: str | None = None
    line_start = 0
    for line in text.split("\n"):
        heading = HEADING.fullmatch(line.strip())
        if heading is not None:
            section = heading.group("title")
        else:
            cursor = 0
            for part in split_sentences(line):
                piece = part.strip()
                if not piece:
                    continue
                at = line.find(piece, cursor)
                if at < 0:
                    raise ValueError(f"{source_id}: the splitter returned text not in its line")
                cursor = at + len(piece)
                start = line_start + at
                end = start + len(piece)
                sentences.append(
                    M.Sentence(
                        src=source_id,
                        index=len(sentences) + 1,
                        section=section,
                        start=start,
                        end=end,
                        spans=find_spans(text, start, end),
                    )
                )
        line_start += len(line) + 1
    return tuple(sentences)


def sentence_text(text: str, sentence: M.Sentence) -> str:
    return text[sentence.start : sentence.end]


# ------------------------------------------------------------------------------------ the spans


def _top_level(s: str) -> tuple[list[tuple[int, int]], list[bool]] | None:
    """The top-level parenthesis groups of `s` and a per-character top-level mask, or `None` when
    the parentheses do not balance."""
    groups: list[tuple[int, int]] = []
    mask = [False] * len(s)
    depth = 0
    opened = 0
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                opened = i
            depth += 1
        elif ch == ")":
            if depth == 0:
                return None
            depth -= 1
            if depth == 0:
                groups.append((opened, i + 1))
        elif depth == 0:
            mask[i] = True
    if depth != 0:
        return None
    return groups, mask


def _candidates(s: str) -> list[tuple[M.SpanKind, int, int]]:
    """Every span of the sentence `s` by the four rules, relative offsets, before any filter."""
    if not s or s[-1] not in TERMINAL:
        return []
    parsed = _top_level(s)
    if parsed is None:
        return []
    groups, top = parsed
    found: list[tuple[M.SpanKind, int, int]] = []
    for low, high in groups:
        if low > 0 and s[low - 1] == " ":
            found.append((M.SpanKind.P, low - 1, high))
        elif low == 0 and high < len(s) and s[high] == " ":
            found.append((M.SpanKind.P, 0, high + 1))
        else:
            found.append((M.SpanKind.P, low, high))
    commas = [
        i for i, ch in enumerate(s) if ch == "," and top[i] and i + 1 < len(s) and s[i + 1] == " "
    ]
    for first, second in zip(commas, commas[1:], strict=False):
        if s[first + 1 : second].strip():
            found.append((M.SpanKind.A, first, second + 1))
    dashes = [
        i
        for i, ch in enumerate(s)
        if ch in DASHES and top[i] and 0 < i < len(s) - 1 and s[i - 1] == " " and s[i + 1] == " "
    ]
    for first, second in zip(dashes, dashes[1:], strict=False):
        if s[first + 1 : second - 1].strip():
            found.append((M.SpanKind.A, first - 1, second + 1))
    if commas:
        lead = commas[0]
        if 1 <= len(s[:lead].split()) <= MAX_LEADING_TOKENS and s[lead + 2 :].strip():
            found.append((M.SpanKind.L, 0, lead + 2))
        last = commas[-1]
        if s[last + 1 : len(s) - 1].strip():
            found.append((M.SpanKind.T, last, len(s) - 1))
    return found


def find_spans(text: str, start: int, end: int) -> tuple[M.Span, ...]:
    """The spans the sentence `text[start:end]` offers, with absolute offsets, in text order."""
    s = text[start:end]
    kept: dict[tuple[int, int], M.SpanKind] = {}
    for kind, low, high in _candidates(s):
        if carries_protected_token(s[low:high]):
            continue
        kept.setdefault((low, high), kind)
    numbers: dict[M.SpanKind, int] = {}
    spans: list[M.Span] = []
    for (low, high), kind in sorted(kept.items()):
        numbers[kind] = numbers.get(kind, 0) + 1
        spans.append(
            M.Span(
                id=f"{kind.value}{numbers[kind]}", kind=kind, start=start + low, end=start + high
            )
        )
    return tuple(spans)


def span_text(text: str, span: M.Span) -> str:
    """How the prompt shows a span: its exact range, as a JSON string (`a1=", whose tomb..."`)."""
    return json.dumps(text[span.start : span.end], ensure_ascii=False)


# ------------------------------------------------------------------------------------- the pool


def fold(value: str) -> str:
    """Casefolded, accents stripped, whitespace collapsed: how a name is looked for in a text."""
    decomposed = unicodedata.normalize("NFKD", value)
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(bare.casefold().split())


def names_in(value: str, names: Sequence[str]) -> bool:
    """True when one of `names` occurs in `value` as whole words (both folded)."""
    folded = fold(value)
    for name in names:
        needle = fold(name)
        if needle and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", folded):
            return True
    return False


def publishable(text: str, sentence: M.Sentence) -> bool:
    """Can this sentence be offered at all: complete, terminated, 25-400 characters."""
    s = sentence_text(text, sentence)
    return (
        MIN_SENTENCE_CHARS <= len(s) <= MAX_SENTENCE_CHARS
        and s[-1] in TERMINAL
        and is_complete_sentence(s)
    )


def excluded(section: str | None) -> bool:
    return section is not None and section.casefold() in EXCLUDED_SECTIONS


def candidate_pool(
    sentences: Sequence[M.Sentence],
    *,
    lane: M.Lane,
    names: Sequence[str],
    text: str,
) -> tuple[M.Sentence, ...]:
    """The sentences the selector is shown: the lead plus the first 6 of each section, bounded.

    `text` is the pinned text the sentences index into (the contract's signature lacked it; lane S
    cannot find a name without it). `names` are the stored name and the `unified_site_names`
    aliases. Lane S keeps only sentences carrying one of them or sitting under a heading that does.
    """
    if lane not in (M.Lane.W, M.Lane.S, M.Lane.T):
        raise ValueError(f"lane {lane.value} selects no sentences")
    pool: list[M.Sentence] = []
    chars = 0
    taken_in_section = 0
    current: object = object()  # no sentence's section is this sentinel
    for sentence in sentences:
        if sentence.section != current:
            current = sentence.section
            taken_in_section = 0
        if excluded(sentence.section) or not publishable(text, sentence):
            continue
        if lane is M.Lane.S and not (
            names_in(sentence_text(text, sentence), names)
            or (sentence.section is not None and names_in(sentence.section, names))
        ):
            continue
        if sentence.section is not None and taken_in_section >= SENTENCES_PER_SECTION:
            continue
        length = sentence.end - sentence.start
        if len(pool) >= MAX_POOL_SENTENCES or chars + length > MAX_POOL_CHARS:
            break
        pool.append(sentence)
        chars += length
        taken_in_section += 1
    return tuple(pool)
