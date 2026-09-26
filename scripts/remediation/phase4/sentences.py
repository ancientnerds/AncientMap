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
The exact rules are PHASE4_CONTRACTS.md section 7, which verify4's own finder implements too; the
cases both must agree on are `tests/remediation/p4_span_cases.py`.

A span's range is exactly the text the prompt shows after its id and exactly what the assembler
removes (edit 1); edits 2-5 run after it. Every range carries the delimiter the removal must take
with it. "Top level" means outside every parenthesis; a sentence whose parentheses do not balance
(or close one before they open it) offers no span at all. A *delimiter comma* is a top-level comma
followed by a space, so the comma of `4,500` never delimits anything. Spans are offered only on a
sentence of an English source (`W`) that ends in `.`, `!` or `?`, the punctuation edit 5 puts the
marker in front of; a `T.<lang>` sentence offers none (the protected tokens are English words).

* `p` - a top-level balanced parenthesis `(...)` with the space in front of it: `" (c. 30 m)"`. At
  the start of the sentence the space after it instead (`"(...) "`); with no space on either side,
  the parenthesis alone.
* `a` - a paired insertion: from a delimiter comma through the next delimiter comma, `", built by
  Khufu,"`, unless the pair is a link of a list or a conjunct (`_list_links`) or shares a comma
  with another such insertion pair (`, bavn, in Bavnehøj,`: neither is offered); or from the space
  before a spaced dash (` - ` as en or em dash) through the next one, the dashes paired in order
  (first with second, third with fourth, none on an odd count), never a pair with a range dash (a
  digit beside it) or a top-level `;` between them. The pair is the insertion's delimiter, so both
  marks go: `A, X, B` becomes `A B`, never the broken `A, B` that removing one comma would leave.
* `l` - a leading phrase of at most 6 tokens before the first delimiter comma, with that comma and
  the space after it: `"In 1900, "`. Edit 4 restores the capital of what follows. Never when that
  comma separates list items or conjuncts (the first comma pair is a list link, or the text after
  the comma opens with `and`/`or`): what stands before it is a list's head and first item.
* `t` - the last comma segment: from the last delimiter comma up to, not including, the final
  punctuation: `", whose tomb lies nearby"`.

No span whose range contains a protected token (`model4.PROTECTED_TOKENS`: hedges, negations,
contrast, refutation, restriction) is offered. Spans of different kinds may overlap - an `a` and the
`t` after it share a comma - and a pick that drops two partially overlapping spans is refused by
`select_stage.parse_selection`; a span nested in another is fine (the outer one is the range).

The pool
--------
`candidate_pool` offers the lead and the first 6 sentences of each section that is not excluded
(the English apparatus, and the same in the languages lane T reads), counting only sentences that
can be published: a complete sentence (`is_complete_sentence`) that ends in `.`, `!` or `?`, is
25-400 characters long and is not `garbled` - a full stop before a lowercase word, or a
preposition directly before a comma, the two garbles V5 holds (pilot 2, T5: Bassae, Vindobala).
Lane S first keeps only sentences that carry a stored name or alias, or sit
under a heading that carries one, both folded by `subject_gate.fold`. The pool stops before the
121st sentence or the 24,001st character, and stays in source order.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# `phase4` appends the repository root to the path, so `pipeline.*` resolves after it.
from phase4 import model4 as M  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402
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
#: The same apparatus in the languages lane T reads (the design's unanchored other-language
#: articles: fr, it, es, de, tr, pt, ca).
FOREIGN_EXCLUDED_SECTIONS = frozenset(
    {
        # de
        "siehe auch", "literatur", "weblinks", "einzelnachweise", "anmerkungen", "quellen",
        "belege", "fußnoten",
        # fr
        "voir aussi", "notes et références", "références", "bibliographie", "liens externes",
        "articles connexes", "dans la culture populaire",
        # es
        "véase también", "referencias", "notas", "bibliografía", "enlaces externos",
        "notas y referencias", "fuentes", "en la cultura popular",
        # it
        "note", "bibliografia", "voci correlate", "altri progetti", "collegamenti esterni",
        "fonti", "nella cultura di massa",
        # pt
        "ver também", "referências", "ligações externas", "fontes", "notas e referências",
        "na cultura popular",
        # tr
        "kaynakça", "kaynaklar", "dış bağlantılar", "ayrıca bakınız", "notlar",
        "popüler kültürde",
        # ca
        "vegeu també", "referències", "enllaços externs",
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
#: A list item and a list's tail, in whitespace tokens (`_list_links`).
LIST_ITEM_TOKENS = 3
LIST_TAIL_TOKENS = 6
_COORDINATOR = re.compile(r"\b(?:and|or)\b", re.IGNORECASE)
_OPENS_WITH_COORDINATOR = re.compile(r"(?:and|or)\b", re.IGNORECASE)


def protected_pattern(*groups: str) -> re.Pattern[str]:
    """One regex for every entry of `model4.PROTECTED_TOKENS` - or of the named groups only
    (`hedges`, `negations`, `contrast`, `refutation`, `restriction`; lane WC reads the negations
    and the refutation words apart) - by the list's own entry rules.

    Whole words, case-insensitive; a trailing `*` matches any word that starts with the rest, a
    leading `*` any word that ends with it; an entry with a space is a phrase of consecutive words;
    `c.` and `ca.` carry their full stop.
    """
    unknown = sorted(set(groups) - set(M.PROTECTED_TOKENS))
    if unknown:
        raise ValueError(f"no protected-token group {unknown}")
    alternatives = []
    for group in groups or tuple(M.PROTECTED_TOKENS):
        for entry in M.PROTECTED_TOKENS[group]:
            if entry.endswith("*"):
                alternatives.append(rf"\b{re.escape(entry[:-1])}\w*")
            elif entry.startswith("*"):
                alternatives.append(rf"\b\w*{re.escape(entry[1:])}\b")
            elif entry.endswith("."):
                alternatives.append(rf"\b{re.escape(entry)}")
            else:
                words = r"\s+".join(re.escape(word) for word in entry.split())
                alternatives.append(rf"\b{words}\b")
    return re.compile("|".join(alternatives), re.IGNORECASE)


PROTECTED = protected_pattern()


def carries_protected_token(text: str) -> bool:
    """True when `text` contains a hedge, negation, contrast, refutation or restriction word."""
    return PROTECTED.search(text) is not None


# ------------------------------------------------------------------------------------ the split


def split_source(source_id: str, text: str) -> tuple[M.Sentence, ...]:
    """Every sentence of the pinned text, numbered from 1, with its section and offered spans.

    Only an English source (`W`) offers spans. The protected tokens are English words, so a span
    of a `T.<lang>` sentence could carry a hedge or a negation no entry names (`vermutlich`,
    `n'est ... pas`) and be dropped before the translator ever saw it: lane T selects whole
    sentences.
    """
    offers_spans = M.source_kind(source_id) is M.SourceKind.W
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
                        spans=find_spans(text, start, end) if offers_spans else (),
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


def _range_dash(s: str, at: int) -> bool:
    """A dash with a digit as the nearest character that is not whitespace (`str.isspace`: also an
    NBSP or a thin space) on either side: `1800 – 500`."""
    before = s[:at].rstrip()
    after = s[at + 1 :].lstrip()
    return bool(before and before[-1].isdigit()) or bool(after and after[0].isdigit())


def _list_links(s: str, commas: Sequence[int]) -> list[bool]:
    """Per pair of consecutive delimiter commas: is it a link of a list rather than an insertion?

    `inner` is the text between the pair's commas, `tail` the text after its second comma up to
    the next delimiter comma or the final punctuation. A pair is a list link when `tail` opens with
    `and`/`or` (a serial list's last link: `A, B, and C`); or when `inner` is at most 3 tokens and
    `tail` is at most 6 tokens and carries `and`/`or` (`A, B, C and D`); or when `inner` is at most
    3 tokens and the next pair is a list link (the run before it); or when `inner` is at most 3
    tokens and `tail`, the sentence's last segment, is too (`Constantine I, Theodosius I, Tiberius
    Nero`, `Clovelly, Devon, England`); or when `inner` opens with `and`/`or` (a conjunct: `A, B,
    and C, D`). Dropping a link joins two list items into a false one; dropping a conjunct hangs
    what follows it on the item before it (Sparta W58: `sculptures founded by Stamatakis`).
    """
    if len(commas) < 2:
        return []
    ends = [*commas[1:], len(s) - 1]
    tails = [s[comma + 1 : end] for comma, end in zip(commas, ends, strict=True)]
    pairs = len(commas) - 1
    links = [False] * pairs
    for k in reversed(range(pairs)):
        short = len(tails[k].split()) <= LIST_ITEM_TOKENS
        tail = tails[k + 1]
        links[k] = (
            _OPENS_WITH_COORDINATOR.match(tail.lstrip()) is not None
            or _OPENS_WITH_COORDINATOR.match(tails[k].lstrip()) is not None
            or (
                short
                and len(tail.split()) <= LIST_TAIL_TOKENS
                and _COORDINATOR.search(tail) is not None
            )
            or (short and k + 1 < pairs and links[k + 1])
            or (short and k + 1 == pairs and len(tail.split()) <= LIST_ITEM_TOKENS)
        )
    return links


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
    links = _list_links(s, commas)
    insertions = [
        bool(s[first + 1 : second].strip()) and not link
        for (first, second), link in zip(zip(commas, commas[1:], strict=False), links, strict=True)
    ]
    for k, insertion in enumerate(insertions):
        # Two insertion pairs that share a comma leave no reading of which two commas enclose the
        # insertion (Agri Bavnehøj W11: ", bavn," beside ", in Bavnehøj,"): neither is offered.
        shares = (k > 0 and insertions[k - 1]) or (k + 1 < len(insertions) and insertions[k + 1])
        if insertion and not shares:
            found.append((M.SpanKind.A, commas[k], commas[k + 1] + 1))
    dashes = [
        i
        for i, ch in enumerate(s)
        if ch in DASHES and top[i] and 0 < i < len(s) - 1 and s[i - 1] == " " and s[i + 1] == " "
    ]
    # Dashes pair in order, the first with the second and the third with the fourth; an odd count
    # leaves no reading of which two enclose an insertion.
    if len(dashes) % 2 == 0:
        for first, second in zip(dashes[::2], dashes[1::2], strict=True):
            if (
                s[first + 1 : second - 1].strip()
                and not _range_dash(s, first)
                and not _range_dash(s, second)
                and not any(s[i] == ";" and top[i] for i in range(first + 1, second))
            ):
                found.append((M.SpanKind.A, first - 1, second + 1))
    if commas:
        lead = commas[0]
        # A first comma that separates list items or conjuncts has a list's head and its first
        # item before it, not a leading phrase (Babylon W204: "Coins from the Parthian, ").
        opens_list = bool(links) and links[0]
        opens_conjunct = _OPENS_WITH_COORDINATOR.match(s[lead + 1 :].lstrip()) is not None
        if (
            1 <= len(s[:lead].split()) <= MAX_LEADING_TOKENS
            and s[lead + 2 :].strip()
            and not opens_list
            and not opens_conjunct
        ):
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


def names_in(value: str, names: Sequence[str]) -> bool:
    """True when one of `names` occurs in `value` as whole words, both folded by Phase 4's one name
    fold (`subject_gate.fold`: accents stripped, lower case, every non-alphanumeric character a
    space), the fold the subject gate accepted the article by: `Chichén-Itzá` is found in `Chichen
    Itza`, `St. Kilda` in `St Kilda`."""
    folded = SG.fold(value)
    for name in names:
        needle = SG.fold(name)
        if needle and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", folded):
            return True
    return False


#: A full stop, whitespace and the next word character, with the run of non-space characters the
#: stop ends (`garbled`).
_STOP_THEN_WORD = re.compile(r"(\S*)\.\s+(\w)")
#: A word of `model4.PREPOSITIONS_NO_COMMA`, lower case and whole, directly before a comma.
_PREPOSITION_THEN_COMMA = re.compile(
    r"(?<![\w'’-])(?:" + "|".join(re.escape(word) for word in M.PREPOSITIONS_NO_COMMA) + r"),"
)
#: What may open the word a full stop ends, before the word itself: a bracket or a quote.
_OPENERS = "([\"'“‘«"


def garbled(s: str) -> bool:
    """Pilot 2 (T5): a sentence the selector is never offered because V5 would hold it.

    Either a full stop inside the sentence, then whitespace, then a lowercase word (Bassae: "...
    Cotylion Mountain. near the village") - unless the word the stop ends is a single letter or has
    a full stop of its own (an initialism: `B.C. and`, `i.e. the`, `a.m. and`) - or a preposition
    of `model4.PREPOSITIONS_NO_COMMA` directly before a comma (Vindobala: "the hamlet of,
    Rudchester"). S2's reading of V5's two rules, in its own code; `verify4.ill_formed` is V5's."""
    for match in _STOP_THEN_WORD.finditer(s):
        word = match.group(1).lstrip(_OPENERS)
        abbreviation = "." in word or (len(word) == 1 and word.isalpha())
        if match.group(2).islower() and not abbreviation:
            return True
    return _PREPOSITION_THEN_COMMA.search(s) is not None


#: A word as the pronoun rule reads it: a run of word characters, apostrophes and hyphens (`it's`
#: and `self-it` are one word each, and neither is `it`).
_WORD = re.compile(r"[\w'’-]+")


def leans_on_predecessor(s: str) -> bool:
    """Pilot 3 (T1, T4, T8): does the published sentence `s` lean on the sentence before it in its
    source? It opens with a word of `model4.PRONOUN_OPENERS` that no letter follows; or its first
    word of `model4.PERSONAL_PRONOUNS` (any case) is one of `model4.SUBJECT_PRONOUNS` and stands
    right after the sentence's first comma, or right after the word `that` with no word of
    `model4.ARTICLES` before it. The review's reading of V6's rule, in its own code (the review
    drops such a sentence with a dropped predecessor, `review4.follow_drops`); `verify4.
    leaning_pronoun` is V6's, and a parity test holds the two together."""
    for opener in M.PRONOUN_OPENERS:
        if s.startswith(opener) and not s[len(opener) : len(opener) + 1].isalpha():
            return True
    words = list(_WORD.finditer(s))
    for index, word in enumerate(words):
        if word.group().lower() not in M.PERSONAL_PRONOUNS:
            continue
        if word.group().lower() not in M.SUBJECT_PRONOUNS:
            return False
        head = s[: word.start()]
        if head.endswith(", ") and head.find(", ") == len(head) - 2:
            return True
        before = words[index - 1].group() if index else ""
        return (
            before.lower() == "that"
            and head.endswith(f"{before} ")
            and not any(w.group().lower() in M.ARTICLES for w in words[:index])
        )
    return False


def publishable(text: str, sentence: M.Sentence) -> bool:
    """Can this sentence be offered at all: complete, terminated, 25-400 characters, and not
    `garbled` (V5 holds a published sentence that is)."""
    s = sentence_text(text, sentence)
    return (
        MIN_SENTENCE_CHARS <= len(s) <= MAX_SENTENCE_CHARS
        and s[-1] in TERMINAL
        and is_complete_sentence(s)
        and not garbled(s)
    )


def excluded(section: str | None) -> bool:
    if section is None:
        return False
    title = section.casefold()
    return title in EXCLUDED_SECTIONS or title in FOREIGN_EXCLUDED_SECTIONS


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
