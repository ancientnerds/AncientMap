"""Lane WC: the March descriptions that stay are checked sentence by sentence and trimmed.

Owner decision O5 of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`, "Satzweise pruefen
und kuerzen"): a curated description that is still 2026-03 AI text after the Phase-4 runs - lane L's
marking, or an unmarked old text - is checked sentence by sentence by Opus agents against sources on
the web. A sentence stays only on a verbatim quote from a reputable, independent source that code
has found on the fetched page; a contradicted or unsupported one goes; one clause may be cut out of
an otherwise supported sentence. Nothing kept: the description is cleared. The research, the
answers and the quote check live in `scripts/remediation/wc/`; the write is the writer's group WC
(`phase4/write4.py`, `write_gate4.py --group WC`), accepted by `verify_writes4.py --lane p4wc`. The
runbook is `docs/procedures/SENTENCE_CHECK.md`.

This module is the lane's deterministic core, pure (no file, no network, no clock), shared by the
research CLI, the writer and the acceptance so the three cannot read a checked text differently:

* **The question's sentences** (`checked_sentences`): the stored text with its `[N]` markers taken
  out (the frontend's marker shape, `seo/text.ts` `stripCitations`), split by Phase 4's own sentence
  splitter (`phase4/sentences.split_source`, which numbers the whole text from 1), a piece that ends
  on an abbreviation the splitter does not know (`JOIN_AFTER`: "Rev.", "Col.", ...) joined to the
  next; the text between two sentences must be whitespace, or the split lost words and the site is
  not asked.
* **A trim** (`trim`): exactly one exact substring removed, whose edges fall between words
  (`cuts_token`); never one that is nothing but protected tokens or a hedge frame (a bare hedge,
  negation or restriction, "It is likely that " - `bare_modifier`), nor one that takes a qualifier
  off what stays (`qualifier_problem`: a telling or doubt of the sentence, a report of it outside
  its own figure, a cut into a negation's clause); the capital restored when the piece opened the
  sentence (Phase 4's edit 4), and the rest must not have a problem of `sentence_problems` the
  sentence did not have, its opening and its end asked apart. Code repairs nothing else: a piece
  that leaves a double space or a dangling comma is refused and the agent names a cleaner one.
* **The pronoun rule** (`follow_drops`): a kept sentence that leans on the sentence before it
  (`sentences.leans_on_predecessor`, Phase 4's own reading of V6) goes when that sentence goes.
* **The text** (`compose`): the kept sentences in their order, each followed by one marker per
  distinct page its verified quotes come from (`with_markers`: `' [n]'` before the final punctuation,
  Phase 4's edit 5), numbered by first appearance; `description_citations` is rebuilt from those pages
  (`n`, `url`, `title`, `domain` - `assemble.domain_of`), so D1 holds by construction.
* **The raw_data** (`written_raw_data`): the old object without `description_citations`,
  `_description_provenance` and `_description_check`, then - for a kept text - the new citations,
  the check record (`DescriptionCheck`, key `_description_check`) and, for a March text, lane L's
  provenance hashing the new text (`provenance_after`: the old text carried lane L's marking, or
  lane L's own rule claims it and no marking was stored yet; `legacy4.legacy_provenance` also
  withdraws the claim if the kept text were the pre-March one). An unclaimed old text (HUMAN_ONLY
  D7: its origin is not provable) gets no provenance. A cleared site keeps none of the three keys,
  and `raw_data` is NULL when nothing else remains, so D1 and D4 hold on the NULL description too.
* **The invariants** (`wc_problems`) the writer's plan, its read-back and the acceptance ask of a
  written site, and **the journal evidence** (`evidence_problems`): production must be exactly
  what the evidence's decisions compose, with the AI disclosure its recorded marking requires
  (`marking_record`, `disclosure_problems`; the writer re-derives the marking from the row's old
  value, `old_marking_problems`).

The check record is public (`/api/sites/{id}` serves `raw_data` whole; the leading underscore keeps
it out of the popup's field panel). It therefore carries each quote's sha256 and never its words:
the verbatim quotes of restricted pages are kept in the journal only, as Phase 4 keeps lane R's
(`write4.journal_evidence`). The API renders the checked text exactly as before: lane L's
`ai: generated` shows the existing AI footnote (`api/services/description_provenance.py`).
"""

from __future__ import annotations

import dataclasses
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from census.tests.t08_citation_markers import entries, marker_sequence  # noqa: E402

from phase4 import assemble as A  # noqa: E402 - the marker edit and the citation domain
from phase4 import legacy4  # noqa: E402 - lane L's claim, one spelling
from phase4 import model4 as M  # noqa: E402
from phase4 import sentences as S  # noqa: E402 - the splitter, the protected tokens, the pronouns
from pipeline.lyra.text_sentences import ends_like_a_sentence, opens_like_a_sentence  # noqa: E402

#: The `raw_data` key of the check record. The leading underscore keeps it out of the popup's
#: generic field panel (`ancient-nerds-map/src/config/sourceFields.ts`), as for the provenance.
CHECK_KEY = "_description_check"
CHECK_VERSION = 1
#: The keys a WC write replaces (or, for a cleared site, removes): nothing else of `raw_data` moves.
WC_KEYS = frozenset({M.CITATIONS_KEY, M.PROVENANCE_KEY, CHECK_KEY})
#: The WC gate plan's batches carry this in `pass` (a P4 plan's carry none, lane L's
#: `legacy4.PLAN_MARK`), so one is never read as another.
PLAN_MARK = "phase4-wc"
#: The first plan batch number of the WC block: past lane L's p4-1001 .. p4-1334 and the blocks
#: REPAIR_TEXTS_2026-09-26 reserved for scope v3 (p4-2001 ..) and group C (p4-3001 ..). A journal
#: stamp names its batch (`phase4wc:p4wc-NNNN:chunk-NNNN`), so a run's plan starts past every
#: batch an earlier WC plan numbered (`build --first-batch`).
FIRST_BATCH = 4001
#: Sites per write batch: five write batches are one step of 100 sites.
BATCH_SIZE = 20
#: The frontend's marker, with the horizontal whitespace before it (`seo/text.ts` stripCitations,
#: `/[^\S\n]*\[\d+\]/g`; the dangling-markers lane's `_RUN`).
_MARKER = re.compile(r"[^\S\n]*\[\d+\]")
#: A trimmed sentence is at least this long: V5's lower bound for a published Phase-4 sentence.
MIN_TRIMMED_CHARS = S.MIN_SENTENCE_CHARS
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s[.,;:!?)]")
_DANGLING_PUNCTUATION = re.compile(r"[,;:(]\s*[.,;:!?)]")
_EMPTY_PARENTHESES = re.compile(r"\(\s*\)")
#: A word or a number as the trim reads it: letters and digits, joined by a hyphen, an apostrophe or
#: a number's group or decimal separator (`3,500`, `2.5`, `Hal-Saflieni`, `Zammit's`). A cut never
#: falls inside one (`cuts_token`): what is left would be a token no source wrote.
_TOKEN = re.compile(r"[^\W_]+(?:[-'’.,][^\W_]+)*")
#: Words that report what stands beside them as someone's belief, telling or supposition: V4's
#: reporting hedges (`model4.PROTECTED_TOKENS`: believed, thought, claimed, alleged*, reportedly,
#: suggest*, suppos*, reputed*, purported*, presum*, assum*) and their forms V4 does not list
#: (believe, belief, think, say, said, says, considered, regarded, report*, argu*). Such a word may go
#: only as the inner clause of the figure it reports (`reports_its_own_figure`).
_REPORTING = re.compile(
    r"\b(?:believ\w*|belief\w*|thought|think\w*|claim\w*|alleg\w*|report\w*|suggest\w*|suppos\w*|"
    r"reputed\w*|purport\w*|presum\w*|assum\w*|said|says|say|considered|regarded|argu\w*)\b",
    re.IGNORECASE,
)
#: Words that put the whole sentence under a source's telling, wherever they stand: "according
#: to", legend, tradition (V4's), myth, folklore (the review of 2026-09-26). A piece with one never
#: goes: what stays would be stated as fact.
_SENTENCE_FRAME = re.compile(r"\b(?:according|legend\w*|tradition\w*|myth\w*|folklor\w*)\b", re.I)
#: V4's refutation words (disputed, uncertain, unknown, attributed, theor*, ...): a piece with one
#: never goes either - the doubt may be about what stays.
_REFUTATION = S.protected_pattern("refutation")
#: V4's negations (not, no, never, neither, nor, without, cannot, *n't): a cut inside a negation's
#: clause widens or inverts what it says ("never excavated by Evans" -> "never excavated").
_NEGATION = S.protected_pattern("negations")
#: What closes a clause: a comma, a semicolon, a colon, a bracket or a dash.
_CLAUSE_BREAK = re.compile(r"[,;:()\[\]–—]")
#: The words a hedge frame is built of around the claim that stays ("It is likely that ",
#: ", it seems,", "It has been suggested that ", "It is uncertain whether "): pronouns,
#: auxiliaries, articles, the linking words and the frame's reporting nouns and verbs. A piece of
#: nothing but these, V4's words and `_REPORTING`'s hedges what stays and carries no claim of its
#: own (`bare_modifier`).
_FRAME_WORDS = re.compile(
    r"\b(?:it|its|this|there|is|was|are|were|be|been|being|has|have|had|that|which|who|whether|"
    r"if|to|the|a|an|by|as|of|so|told|tells|held|holds|widely|generally|commonly|often|long|many|"
    r"most|scholars|historians|archaeologists|researchers|experts|locals|people|sources|accounts|"
    r"myths?|folklore|lore|stor(?:y|ies)|tales?|local|popular|folk|oral)\b",
    re.IGNORECASE,
)
#: Abbreviations the shared splitter (`pipeline.lyra.text_sentences`, through Phase 4's
#: `sentences.split_source`) does not protect, so it ends a sentence after them. Measured on the
#: population of 2026-09-26 (3,937 texts, 15,141 pieces): 8 such breaks in 7 sites - "Rev." (2),
#: "Col." (2, one after "Lt."), "Lt." (1), "cal." (2), "(no." (1); every join a whole sentence -
#: plus the ranks and titles of the same kind. A piece whose last word is one of these is joined
#: to the next piece (15,133 sentences), so no question shows half a sentence. The shared
#: splitter itself stays as it is: it is Phase 4's parity-tested split (sentence ids of written
#: provenance) and Lyra's.
JOIN_AFTER = frozenset(
    {"Rev.", "Revd.", "Lt.", "Col.", "Gen.", "Maj.", "Capt.", "Sgt.", "Gov.", "(no.", "cal."}
)
#: What may close a sentence after its final . ! or ? (a quotation, a bracket).
CLOSERS = "\"'”’»)]"


class WcError(ValueError):
    """A WC record, text or plan is not what the lane's contract says: never guessed around."""


class Verdict(StrEnum):
    """The answer about one sentence (the question's three) and what code makes of it."""

    KEEP = "KEEP"
    KEEP_TRIMMED = "KEEP_TRIMMED"
    DROP = "DROP"


KEPT = frozenset({Verdict.KEEP, Verdict.KEEP_TRIMMED})


class DropReason(StrEnum):
    """Why a sentence is not published. The first two are the agent's, the last two code's."""

    CONTRADICTED = "contradicted"  #: a source contradicts a claim of it
    UNSUPPORTED = "unsupported"  #: no reputable, independent source supports every claim
    UNVERIFIED = "unverified"  #: its quotes were not found on the pages after the re-ask round
    LEANS = "leans-on-dropped"  #: it leans on the sentence before it, and that one went


AGENT_REASONS = frozenset({DropReason.CONTRADICTED, DropReason.UNSUPPORTED})


# ------------------------------------------------------------------------------ the sentences
def strip_markers(text: str) -> str:
    """The text without its `[N]` markers and the whitespace before each."""
    return _MARKER.sub("", text)


def checked_sentences(description: str) -> tuple[str, ...]:
    """The numbered sentences a description is asked in: markers out, then Phase 4's split, with a
    piece that ends on an abbreviation of `JOIN_AFTER` joined to the next one.

    Refused (`WcError`): a text that still carries a marker once the plain ones are out (a grouped
    or range form, which the census expands - none is stored today, measured 2026-09-26), a text
    with no sentence, and a split that dropped anything but whitespace between two sentences.
    """
    text = strip_markers(description)
    if marker_sequence(text):
        raise WcError("a grouped or range citation marker is left once the plain ones are out")
    pieces = S.split_source("W", text)
    if not pieces:
        raise WcError("the text holds no sentence")
    cursor = 0
    for piece in pieces:
        if text[cursor : piece.start].strip():
            raise WcError(f"the split lost {text[cursor : piece.start].strip()[:40]!r}")
        cursor = piece.end
    if text[cursor:].strip():
        raise WcError(f"the split lost {text[cursor:].strip()[:40]!r}")
    ranges: list[tuple[int, int]] = []
    for piece in pieces:
        if ranges and text[ranges[-1][0] : ranges[-1][1]].split()[-1] in JOIN_AFTER:
            ranges[-1] = (ranges[-1][0], piece.end)
        else:
            ranges.append((piece.start, piece.end))
    return tuple(text[start:end] for start, end in ranges)


def with_markers(sentence: str, numbers: Sequence[int]) -> str:
    """The published sentence with one `' [n]'` per citation number, in order: in front of the
    final . ! or ? (Phase 4's edit 5, `assemble.with_marker`); after the closing quotation mark or
    bracket that follows it, so the marker stays outside the quotation (`of the City." [1]`); and
    for a sentence that ends without . ! or ? (a stored text's last sentence, measured 4 of 15,133
    on 2026-09-26), after the sentence with a full stop behind the markers - the one character code
    adds to a stored sentence."""
    if not numbers:
        raise WcError("a published sentence carries at least one marker")
    if sentence[-1] in A.TERMINAL:
        for number in numbers:
            sentence = A.with_marker(sentence, number)
        return sentence
    tail = "".join(f" [{number}]" for number in numbers)
    opened = sentence.rstrip(CLOSERS)
    if opened != sentence and opened[-1:] and opened[-1] in A.TERMINAL:
        return sentence + tail
    return sentence + tail + "."


def sentence_problems(sentence: str) -> list[str]:
    """What keeps a trimmed sentence from being published as it stands; empty = nothing."""
    problems: list[str] = []
    if sentence != sentence.strip():
        problems.append("it has leading or trailing whitespace")
    if len(sentence) < MIN_TRIMMED_CHARS:
        problems.append(f"it is {len(sentence)} characters, under {MIN_TRIMMED_CHARS}")
    # The two halves of `is_complete_sentence`, apart: a stored sentence that lacks one (a capital
    # outside ASCII) must still keep the other through a trim (the review of 2026-09-26).
    if not opens_like_a_sentence(sentence):
        problems.append("it does not open with a capital or a digit")
    if not ends_like_a_sentence(sentence):
        problems.append("it does not end with . ! or ? (a sentence end, not an abbreviation)")
    if S.garbled(sentence):
        problems.append("it is garbled (a full stop before a lower-case word, or 'of,')")
    if "  " in sentence:
        problems.append("it has a double space")
    if _SPACE_BEFORE_PUNCTUATION.search(sentence):
        problems.append("it has a space before punctuation")
    if _DANGLING_PUNCTUATION.search(sentence):
        problems.append("it has dangling punctuation (', .', ',,', '(,')")
    if _EMPTY_PARENTHESES.search(sentence) or sentence.count("(") != sentence.count(")"):
        problems.append("its parentheses are empty or unbalanced")
    return problems


def cuts_token(sentence: str, at: int) -> bool:
    """Does a cut at offset `at` fall inside a word or a number (`_TOKEN`: letters and digits, and
    the hyphen, apostrophe or separator that joins them - `3,500`, `2.5`, `Hal-Saflieni`)? A piece
    copied one character short (` c. 3000 BC` of ` c. 3000 BCE.`) or cut from inside a number (`5`
    of `3500`) leaves a token no source wrote (`builtE`, `300 BC`), and no sentence check sees it."""
    return any(token.start() < at < token.end() for token in _TOKEN.finditer(sentence))


def bare_modifier(piece: str) -> bool:
    """Is the piece nothing but hedge, negation, contrast, refutation or restriction words (Phase
    4's V4 list, `sentences.PROTECTED`), reporting words (`_REPORTING`), the words of a hedge frame
    (`_FRAME_WORDS`) and punctuation? Cutting such a piece strips the modifier off a claim that
    stays (`probably `, ` not`, `only `, `approximately `, `It is likely that `, `, it seems,`). A
    piece that takes a whole clause with its own modifier (` (c. 3000 BC)`, `, probably a tomb,`)
    leaves nothing the modifier bore: it may go. Phase 4 refuses every span with such a word, since
    its spans cut Wikipedia sentences a reader trusts; here the cut is the check's answer to an
    unsupported clause, and 2,476 of the population's 15,133 sentences (16.4 %, measured
    2026-09-26) carry a hedged number - the March texts' commonest invention (`draw-2026-09-25b`) -
    which the stricter rule could only DROP whole.
    """
    if not (S.carries_protected_token(piece) or _REPORTING.search(piece)):
        return False
    rest = _FRAME_WORDS.sub("", _REPORTING.sub("", S.PROTECTED.sub("", piece)))
    return not any(character.isalnum() for character in rest)


def reports_its_own_figure(sentence: str, at: int, end: int) -> bool:
    """May the piece `sentence[at:end]`, which carries a reporting word (`_REPORTING`), go? Only as
    the inner clause of the figure it reports (`, believed to date to about 10,000 BC,`): it neither
    opens nor closes the sentence - an opening or closing report is a frame of what stays
    ("Believed to date to 3000 BC, ...", "..., as was reported in 1990.") - and every reporting word
    in it is followed, inside the piece, by the infinitive of its claim (`believed to`, `said to`)
    or is an adverb before its claim (`reportedly raised`), with a number or date after it in the
    piece. ", as Evans believed in 1920," reports the rest and stays; so does ", believed to be the
    oldest in Malta,", which reports no figure - code cannot tell what else a report covers."""
    if at == 0 or not sentence[end:].strip(CLOSERS + A.TERMINAL + " "):
        return False
    piece = sentence[at:end]
    for word in _REPORTING.finditer(piece):
        after = piece[word.end() :]
        joined = re.match(r"\s+to\s+\w", after) or (
            word.group().lower().endswith("ly") and re.match(r"\s+\w", after)
        )
        if not joined or not any(character.isdigit() for character in after):
            return False
    return True


def ends_a_clause(sentence: str, end: int) -> bool:
    """Does a piece that ends at `end` end its clause - its own last character, or the next one
    after the space, a clause break (`_CLAUSE_BREAK`), or nothing but the final mark after it?"""
    piece_end = sentence[:end].rstrip()[-1:]
    after = sentence[end:].lstrip()
    return (
        bool(_CLAUSE_BREAK.match(piece_end))
        or bool(_CLAUSE_BREAK.match(after[:1]))
        or not after.strip(CLOSERS + A.TERMINAL)
    )


def qualifier_problem(sentence: str, at: int, end: int) -> str | None:
    """Why the piece `sentence[at:end]` would take a qualifier off what stays, or `None` (the review
    of 2026-09-26: the mass run has no judge, so code is the guard against a trim that states a
    report, a doubt or a negated claim as plain fact).

    * a telling or doubt of the whole sentence (`_SENTENCE_FRAME`, `_REFUTATION`) never goes;
    * a reporting word goes only as the inner clause of its own figure (`reports_its_own_figure`);
    * a negation in the piece goes only with the rest of its clause (`ends_a_clause`), and the piece
      may not stand inside the clause of a negation that stays before it ("The site was never
      excavated by Evans" - " by Evans" widens the "never")."""
    piece = sentence[at:end]
    if _SENTENCE_FRAME.search(piece) or _REFUTATION.search(piece):
        return (
            "the piece carries a sentence hedge - a telling or a doubt (according to, legend, "
            "tradition, myth, folklore, disputed, uncertain, unknown, attributed, ...): what stays "
            "would be stated as fact - DROP the sentence instead"
        )
    if _REPORTING.search(piece) and not reports_its_own_figure(sentence, at, end):
        return (
            "the piece carries a reporting hedge (believed, thought, said, claimed, reportedly, "
            "considered, ...) that is not the inner clause of the number or date it reports "
            "(', believed to date to about 3000 BC,'): removing it would state as fact what a "
            "source only reports - DROP the sentence, or cut that whole inner clause"
        )
    if _NEGATION.search(piece) and not ends_a_clause(sentence, end):
        return (
            "the piece carries a negation whose clause goes on after it: what stays would say "
            "something else - cut the negation with the whole of its clause, or DROP the sentence"
        )
    before = sentence[:at]
    negations = list(_NEGATION.finditer(before))
    if negations and not _CLAUSE_BREAK.search(before[negations[-1].end() :]):
        return (
            f"the piece stands in the clause of the negation {negations[-1].group()!r}, which "
            "stays: removing it widens or inverts what the negation says ('never excavated by "
            "Evans' -> 'never excavated') - DROP the sentence instead"
        )
    return None


def trim(sentence: str, remove: str) -> str:
    """`sentence` without the one exact substring `remove`, or `WcError` naming why not.

    The piece's edges fall between words (`cuts_token`); it is no bare modifier or hedge frame
    (`bare_modifier`) and takes no qualifier off what stays (`qualifier_problem`: a telling or doubt
    of the sentence, a report of it, a negation's clause); it takes no end of a sentence stored
    without its final mark. The rest must not have a problem (`sentence_problems`) the sentence did
    not have - the opening and the end asked apart: a trim may leave a stored oddity as it was - a
    name that opens with a capital outside ASCII (`Židovar`, which `opens_like_a_sentence` does not
    know as a capital), a closing initial (`Mrauk U.`) - but never add one."""
    if not remove.strip():
        raise WcError("the piece to remove is empty")
    if sentence.count(remove) != 1:
        raise WcError(
            f"the piece to remove occurs {sentence.count(remove)} times in the sentence, not once "
            "(copy it exactly, with the comma or space that goes with it)"
        )
    if remove.strip() == sentence.strip():
        raise WcError("the piece to remove is the whole sentence: that is a DROP")
    at = sentence.index(remove)
    end = at + len(remove)
    if cuts_token(sentence, at) or cuts_token(sentence, end):
        raise WcError(
            f"the piece {remove!r} cuts a word or number: it must begin and end between words "
            "(copy the whole word or number, e.g. ' c. 3000 BCE', not ' c. 3000 BC')"
        )
    if bare_modifier(remove):
        raise WcError(
            "the piece is only a hedge, negation, contrast or restriction word (the V4 list), or a "
            "hedge frame around the rest ('It is likely that ', ', it is said,'): removing it "
            "would change what the rest says - DROP the sentence instead"
        )
    why = qualifier_problem(sentence, at, end)
    if why is not None:
        raise WcError(why)
    if end == len(sentence) and not ends_like_a_sentence(sentence):
        raise WcError(
            "the sentence is stored without its final mark (. ! or ?): a piece may not take its "
            "end, or what stays ends on a fragment"
        )
    rest = sentence[:at] + sentence[end:]
    if at == 0:
        rest = rest[:1].upper() + rest[1:]
    stored = sentence_problems(sentence)
    problems = [problem for problem in sentence_problems(rest) if problem not in stored]
    if problems:
        raise WcError(f"the trimmed sentence {rest!r}: " + "; ".join(problems))
    return rest


# ------------------------------------------------------------------------------ the decisions
@dataclass(frozen=True)
class Quote:
    """A verbatim quote, the page it is on and that page's title as the agent read it."""

    url: str
    title: str
    quote: str

    def to_dict(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title, "quote": self.quote}


@dataclass(frozen=True)
class Decision:
    """The final decision on one sentence of the checked text (after every round).

    `quotes` of a kept sentence are the machine-verified ones its markers cite; a dropped sentence
    carries none here (the journal keeps what the agent gave, and what the check said of it).
    """

    n: int
    sentence: str
    verdict: Verdict
    remove: str | None
    reason: DropReason | None

    def __post_init__(self) -> None:
        if self.n < 1:
            raise WcError(f"sentence number {self.n} is not 1-based")
        if (self.verdict is Verdict.KEEP_TRIMMED) != (self.remove is not None):
            raise WcError(f"S{self.n}: a piece to remove belongs to KEEP_TRIMMED, and only there")
        if (self.verdict is Verdict.DROP) != (self.reason is not None):
            raise WcError(f"S{self.n}: a drop reason belongs to DROP, and only there")

    @property
    def kept(self) -> bool:
        return self.verdict in KEPT

    @property
    def text(self) -> str | None:
        """The published sentence (trimmed where it is), `None` for a dropped one."""
        if self.verdict is Verdict.DROP:
            return None
        if self.remove is None:
            return self.sentence
        return trim(self.sentence, self.remove)


def follow_drops(decisions: Sequence[Decision]) -> list[Decision]:
    """Phase 4's pronoun rule: a kept sentence that leans on the sentence before it
    (`sentences.leans_on_predecessor`) is dropped when that sentence is dropped - in order, so a
    drop carries on down a chain of such sentences. The first sentence leans on nothing."""
    out: list[Decision] = []
    for index, decision in enumerate(decisions):
        text = decision.text
        if index and text is not None and not out[index - 1].kept and S.leans_on_predecessor(text):
            decision = dataclasses.replace(
                decision, verdict=Verdict.DROP, remove=None, reason=DropReason.LEANS
            )
        out.append(decision)
    return out


# ------------------------------------------------------------------------------ the text
@dataclass(frozen=True)
class Composed:
    """What a checked site's description becomes: `None` when nothing is kept."""

    description: str | None
    citations: tuple[dict[str, Any], ...]
    #: per decision, in order: the citation numbers its markers carry (empty for a drop)
    cites: tuple[tuple[int, ...], ...]


def compose(decisions: Sequence[Decision], quotes: Mapping[int, Sequence[Quote]]) -> Composed:
    """The kept sentences in their order, each with one marker per distinct page of its verified
    quotes (`quotes`, by sentence number), numbered by the pages' first appearance; the citations
    of exactly those pages. A kept sentence without a verified quote is a contract breach."""
    numbers: dict[str, int] = {}
    titles: dict[str, str] = {}
    published: list[str] = []
    cites: list[tuple[int, ...]] = []
    for decision in decisions:
        text = decision.text
        if text is None:
            cites.append(())
            continue
        own = quotes.get(decision.n, ())
        if not own:
            raise WcError(f"S{decision.n} is kept without a verified quote")
        numbered: list[int] = []
        for quote in own:
            if quote.url not in numbers:
                numbers[quote.url] = len(numbers) + 1
                titles[quote.url] = quote.title
            if numbers[quote.url] not in numbered:
                numbered.append(numbers[quote.url])
        # ascending within the sentence ("[1] [2]"): a sentence's new numbers are larger than every
        # number before it, so the order of first use stays 1..N
        numbered.sort()
        published.append(with_markers(text, numbered))
        cites.append(tuple(numbered))
    citations = tuple(
        {"n": number, "url": url, "title": titles[url], "domain": A.domain_of(url)}
        for url, number in numbers.items()
    )
    return Composed(
        description=" ".join(published) if published else None,
        citations=citations,
        cites=tuple(cites),
    )


# ------------------------------------------------------------------------------ the record
_CHECK_KEYS = frozenset(
    {"v", "run", "checker", "checked_sha256", "kept", "of", "trimmed", "sentences", "desc_sha256"}
)
_SENTENCE_KEYS = frozenset({"n", "verdict", "reason", "cites", "quote_sha256"})


@dataclass(frozen=True)
class CheckedSentence:
    """One sentence of the checked text in the public record: its verdict, the citation numbers
    its markers carry and the sha256 of each verified quote (the words stay in the journal)."""

    n: int
    verdict: Verdict
    reason: DropReason | None
    cites: tuple[int, ...]
    quote_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        M._need_int(self.n, "check sentence n", minimum=1)
        M._need_member(self.verdict, Verdict, f"check sentence {self.n}: verdict")
        kept = self.verdict in KEPT
        if kept == (self.reason is not None):
            raise ValueError(f"check sentence {self.n}: a reason belongs to a dropped sentence")
        if self.reason is not None:
            M._need_member(self.reason, DropReason, f"check sentence {self.n}: reason")
        if kept != bool(self.cites) or kept != bool(self.quote_sha256):
            raise ValueError(
                f"check sentence {self.n}: a kept sentence cites and has verified quotes, a "
                "dropped one neither"
            )
        for number in self.cites:
            M._need_int(number, f"check sentence {self.n}: cite", minimum=1)
        if len(set(self.cites)) != len(self.cites):
            raise ValueError(f"check sentence {self.n}: a citation number repeats")
        for digest in self.quote_sha256:
            M._need_hex(digest, f"check sentence {self.n}: quote_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "verdict": self.verdict.value,
            "reason": None if self.reason is None else self.reason.value,
            "cites": list(self.cites),
            "quote_sha256": list(self.quote_sha256),
        }

    @classmethod
    def from_dict(cls, data: Any) -> CheckedSentence:
        d = M._obj(data, "check sentence", _SENTENCE_KEYS)
        if not isinstance(d["cites"], list) or not isinstance(d["quote_sha256"], list):
            raise ValueError("check sentence: cites and quote_sha256 are lists")
        return cls(
            n=d["n"],
            verdict=Verdict(d["verdict"]),
            reason=None if d["reason"] is None else DropReason(d["reason"]),
            cites=tuple(d["cites"]),
            quote_sha256=tuple(d["quote_sha256"]),
        )


@dataclass(frozen=True)
class DescriptionCheck:
    """`raw_data._description_check` v1: that the served text was checked sentence by sentence,
    by whom, what stayed, and the text it describes (`desc_sha256`, like the provenance's)."""

    run: str
    checker: str
    checked_sha256: str  #: the stored March text that was checked, markers included
    kept: int
    of: int
    trimmed: int
    sentences: tuple[CheckedSentence, ...]
    desc_sha256: str
    v: int = CHECK_VERSION

    def __post_init__(self) -> None:
        if self.v != CHECK_VERSION or isinstance(self.v, bool):
            raise ValueError(f"check.v: {self.v!r} is not version {CHECK_VERSION}")
        M._need_text(self.run, "check.run")
        if self.checker != M.AI_SYSTEM:
            raise ValueError(f"check.checker: {self.checker!r} is not {M.AI_SYSTEM!r}")
        M._need_hex(self.checked_sha256, "check.checked_sha256")
        M._need_hex(self.desc_sha256, "check.desc_sha256")
        if [s.n for s in self.sentences] != list(range(1, len(self.sentences) + 1)):
            raise ValueError("check.sentences: not numbered 1..m in order")
        kept = [s for s in self.sentences if s.verdict in KEPT]
        trimmed = [s for s in kept if s.verdict is Verdict.KEEP_TRIMMED]
        if (self.kept, self.of, self.trimmed) != (len(kept), len(self.sentences), len(trimmed)):
            raise ValueError(
                f"check: kept {self.kept} of {self.of}, trimmed {self.trimmed} is not what its "
                f"sentences say ({len(kept)} of {len(self.sentences)}, {len(trimmed)})"
            )
        if not kept:
            raise ValueError("check: a record describes a kept text; nothing kept is a clear")

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "run": self.run,
            "checker": self.checker,
            "checked_sha256": self.checked_sha256,
            "kept": self.kept,
            "of": self.of,
            "trimmed": self.trimmed,
            "sentences": [sentence.to_dict() for sentence in self.sentences],
            "desc_sha256": self.desc_sha256,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DescriptionCheck:
        d = M._obj(data, "check", _CHECK_KEYS)
        if not isinstance(d["sentences"], list):
            raise ValueError("check.sentences is not a list")
        for key in ("kept", "of", "trimmed"):
            M._need_int(d[key], f"check.{key}", minimum=0)
        return cls(
            v=d["v"],
            run=d["run"],
            checker=d["checker"],
            checked_sha256=d["checked_sha256"],
            kept=d["kept"],
            of=d["of"],
            trimmed=d["trimmed"],
            sentences=tuple(CheckedSentence.from_dict(s) for s in d["sentences"]),
            desc_sha256=d["desc_sha256"],
        )


def check_record(
    decisions: Sequence[Decision],
    composed: Composed,
    quotes: Mapping[int, Sequence[Quote]],
    *,
    run: str,
    checked: str,
) -> DescriptionCheck:
    """The public record of a kept text: every sentence's verdict, the numbers its markers carry
    and the sha256 of each verified quote; `checked` is the stored text that was asked."""
    if composed.description is None:
        raise WcError("a cleared site has no check record")
    return DescriptionCheck(
        run=run,
        checker=M.AI_SYSTEM,
        checked_sha256=M.text_sha256(checked),
        kept=sum(d.kept for d in decisions),
        of=len(decisions),
        trimmed=sum(d.verdict is Verdict.KEEP_TRIMMED for d in decisions),
        sentences=tuple(
            CheckedSentence(
                n=d.n,
                verdict=d.verdict,
                reason=d.reason,
                cites=cites,
                quote_sha256=tuple(M.text_sha256(q.quote) for q in quotes.get(d.n, ()))
                if d.kept
                else (),
            )
            for d, cites in zip(decisions, composed.cites, strict=True)
        ),
        desc_sha256=M.text_sha256(composed.description),
    )


# ------------------------------------------------------------------------------ the raw_data
class Marking(StrEnum):
    """What the stored text is, as far as the AI disclosure goes."""

    #: lane L's provenance: a March text, marked
    L = "L"
    #: no provenance, yet lane L's own rule (`legacy4.legacy_provenance`: the text differs from the
    #: pre-March snapshot) says the March chain wrote it - a site whose P4 write a revert took back
    #: (the revert restores the raw_data from before lane L), or one lane L never reached
    MARCH = "march-unmarked"
    #: HUMAN_ONLY D7: the text is the pre-March one, or the site is not in the snapshot - nothing
    #: proves where it came from, so nothing is claimed
    UNCLAIMED = "unclaimed"


def old_marking(site: M.PlanSite) -> Marking:
    """How the stored text is marked (`Marking`). A full Phase-4 provenance, a record that does not
    parse, and a text lane WC checked before are not WC's to check (`WcError`, `ValueError`)."""
    raw = site.raw_data or {}
    if CHECK_KEY in raw:
        raise WcError("the stored text was checked sentence by sentence before")
    if M.PROVENANCE_KEY in raw:
        provenance = M.provenance_from_dict(raw[M.PROVENANCE_KEY])
        if not isinstance(provenance, M.LegacyProvenance):
            raise WcError(f"lane {provenance.lane.value} wrote this text in Phase 4")
        return Marking.L
    return Marking.UNCLAIMED if legacy4.legacy_provenance(site) is None else Marking.MARCH


def marking_record(site: M.PlanSite) -> dict[str, Any]:
    """The journal evidence's `marking`: how the checked text was marked (`old_marking`) and what
    lane L's claim rests on - whether the site is in the pre-March snapshot and the sha256 of its
    text there (`None` when it holds none) - so the disclosure a written text needs can be asked
    of the database alone (`disclosure_problems`)."""
    snapshot = site.snapshot_description
    return {
        "old": old_marking(site).value,
        "in_snapshot": site.in_snapshot,
        "snapshot_sha256": None if snapshot is None else M.text_sha256(snapshot),
    }


def old_marking_problems(
    marking: Mapping[str, Any], checked: str, old_raw: Mapping[str, Any] | None
) -> list[str]:
    """Is the recorded old marking the one the checked pair carries? Lane L's provenance in the
    old `raw_data` is `L`; without one, lane L's rule on the snapshot record decides - the checked
    text differs from the pre-March one: `march-unmarked`, else `unclaimed`. The writer asks this
    of the row's own old value, so a recorded marking cannot excuse a missing footnote."""
    stored = (old_raw or {}).get(M.PROVENANCE_KEY)
    if stored is not None:
        try:
            provenance = M.provenance_from_dict(stored)
        except ValueError as exc:
            return [f"the checked text's provenance does not read: {exc}"]
        if not isinstance(provenance, M.LegacyProvenance):
            return ["the checked text carries a Phase-4 provenance: it is not WC's"]
        derived = Marking.L
    elif marking["in_snapshot"] and M.text_sha256(checked) != marking["snapshot_sha256"]:
        derived = Marking.MARCH
    else:
        derived = Marking.UNCLAIMED
    if marking["old"] != derived.value:
        return [f"the recorded marking {marking['old']!r} is not the pair's {derived.value!r}"]
    return []


def disclosure_problems(
    marking: Mapping[str, Any], description: str | None, raw_data: Mapping[str, Any] | None
) -> list[str]:
    """The AI disclosure (EU AI Act) a written pair must carry, required and not only checked where
    present (the review of 2026-09-26): a kept text of a March text (`L`, `march-unmarked`) carries
    lane L's provenance hashing it - unless the kept text is the pre-March one, which lane L's rule
    never claims (`legacy4.legacy_provenance`); every other pair - an unclaimed text (HUMAN_ONLY D7),
    a cleared site - carries none."""
    claims = (
        description is not None
        and marking["old"] in (Marking.L.value, Marking.MARCH.value)
        and marking["in_snapshot"]
        and M.text_sha256(description) != marking["snapshot_sha256"]
    )
    stored = (raw_data or {}).get(M.PROVENANCE_KEY)
    if not claims and stored is not None:
        return ["a provenance beside a text that claims no March AI origin"]
    if not claims:
        return []
    if stored is None:
        return ["the AI disclosure is missing: a checked March text carries lane L's provenance"]
    try:
        provenance = M.provenance_from_dict(stored)
    except ValueError as exc:
        return [f"the AI disclosure does not read: {exc}"]
    digest = M.text_sha256(str(description))
    if not isinstance(provenance, M.LegacyProvenance) or provenance.desc_sha256 != digest:
        return ["the AI disclosure is not lane L's provenance of the written text"]
    return []


def provenance_after(site: M.PlanSite, description: str) -> M.LegacyProvenance | None:
    """The provenance the kept text carries: lane L's, hashing the kept text, for a March text -
    marked by lane L, or one lane L's rule claims and no marking carries yet (`Marking.MARCH`: the
    AI footnote must not be missing from a published March text); withdrawn by
    `legacy4.legacy_provenance` should the kept text be the pre-March one. None for an unclaimed
    text (HUMAN_ONLY D7): a trimmed pre-March text is still not the March chain's."""
    if old_marking(site) is Marking.UNCLAIMED:
        return None
    return legacy4.legacy_provenance(
        dataclasses.replace(
            site, description=description, description_sha256=M.text_sha256(description)
        )
    )


def written_raw_data(
    site: M.PlanSite,
    composed: Composed,
    check: DescriptionCheck | None,
) -> dict[str, Any] | None:
    """The `raw_data` a WC write leaves: the old object less the three WC keys, plus - for a kept
    text - its citations, its check record and lane L's moved provenance where the old text had
    one. `None` when nothing remains (a cleared site whose `raw_data` held only WC's keys)."""
    new = {key: value for key, value in (site.raw_data or {}).items() if key not in WC_KEYS}
    if composed.description is not None:
        if check is None:
            raise WcError("a kept text is written with its check record")
        new[M.CITATIONS_KEY] = [dict(citation) for citation in composed.citations]
        new[CHECK_KEY] = check.to_dict()
        legacy = provenance_after(site, composed.description)
        if legacy is not None:
            new[M.PROVENANCE_KEY] = legacy.to_dict()
    elif check is not None:
        raise WcError("a cleared site carries no check record")
    return new or None


# ------------------------------------------------------------------------------ the invariants
_CITATION_KEYS = frozenset({"n", "url", "title", "domain"})


def wc_problems(description: str | None, raw_data: Mapping[str, Any] | None) -> list[str]:
    """What a WC-written site breaks; empty = nothing. The writer's plan, its read-back and the
    acceptance ask exactly this of the stored (or planned) pair:

    * a cleared site (description NULL) carries none of the three WC keys;
    * a kept text carries its check record, whose `desc_sha256` is the text's; lane L's provenance
      where present, whose `desc_sha256` is the text's too (D4); citations of exactly the numbers
      its markers use, numbered 1..N by first use, each `{n, url, title, domain}` with the URL's
      host as the domain (D1); and the check record's kept sentences cite those same numbers.
    """
    raw = dict(raw_data or {})
    if description is None:
        present = sorted(WC_KEYS & raw.keys())
        return [f"a cleared description beside {present} in raw_data"] if present else []
    problems: list[str] = []
    digest = M.text_sha256(description)
    try:
        check = DescriptionCheck.from_dict(raw.get(CHECK_KEY))
    except (ValueError, KeyError) as exc:
        return [f"the check record does not read: {exc}"]
    if check.desc_sha256 != digest:
        problems.append("the check record's desc_sha256 is not the sha256 of the description")
    if M.PROVENANCE_KEY in raw:
        try:
            provenance = M.provenance_from_dict(raw[M.PROVENANCE_KEY])
        except ValueError as exc:
            provenance = None
            problems.append(f"the provenance does not read: {exc}")
        if provenance is not None and not isinstance(provenance, M.LegacyProvenance):
            problems.append(f"a lane-{provenance.lane.value} provenance beside a checked text")
        elif provenance is not None and provenance.desc_sha256 != digest:
            problems.append("the provenance's desc_sha256 is not the sha256 of the description")
    try:
        listed = entries(raw.get(M.CITATIONS_KEY), "wc")
    except ValueError as exc:
        return [*problems, str(exc)]
    for entry in listed:
        if set(entry) != _CITATION_KEYS:
            problems.append(f"citation {entry.get('n')} carries {sorted(entry)}")
        elif entry["domain"] != A.domain_of(entry["url"]):
            problems.append(f"citation {entry['n']}: domain {entry['domain']!r} is not its host")
    sequence = marker_sequence(description)
    first_use = list(dict.fromkeys(sequence))
    numbers = [entry["n"] for entry in listed]
    if first_use != list(range(1, len(first_use) + 1)):
        problems.append(f"the markers {first_use} are not numbered 1..N by first use")
    if sorted(numbers) != sorted(set(first_use)) or len(set(numbers)) != len(numbers):
        problems.append(f"the markers {first_use} and the citations {numbers} disagree (D1)")
    cited = sorted({n for sentence in check.sentences for n in sentence.cites})
    if cited != sorted(set(first_use)):
        problems.append(f"the check record cites {cited}, the markers {sorted(set(first_use))}")
    return problems


# ------------------------------------------------------------------------------ the evidence
#: The journal evidence's keys (one dict for both rows of a site, like Phase 4's p_evidence): the
#: stored text that was asked (`checked`) and how it was marked (`marking`, `marking_record`), the
#: description the decisions compose (`description`, `None` for a clear), every sentence's decision
#: with the agent's quotes and what the check said of each (`sentences`), and the answers they came
#: from.
EVIDENCE_KEYS = frozenset(
    {
        "group",
        "decision",
        "run",
        "checker",
        "checked",
        "marking",
        "description",
        "kept",
        "of",
        "sentences",
        "answers",
    }
)
EVIDENCE_DESCRIPTION = "description"
EVIDENCE_DECISION = "O5 2026-09-26: Satzweise pruefen und kuerzen"


@dataclass(frozen=True)
class WcOutcome:
    """One checked site in the WC gate plan: what its description and raw_data become, and the
    journal evidence both rows carry (`EVIDENCE_KEYS`)."""

    site_id: str
    description: str | None
    raw_data: dict[str, Any] | None
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        M._need_text(self.site_id, "outcome.site_id")
        M._need_opt_text(self.description, f"{self.site_id}: outcome.description")
        if self.raw_data is not None and not isinstance(self.raw_data, dict):
            raise ValueError(f"{self.site_id}: outcome.raw_data is not an object or null")
        if not isinstance(self.evidence, dict) or set(self.evidence) != EVIDENCE_KEYS:
            keys = sorted(self.evidence) if isinstance(self.evidence, dict) else self.evidence
            raise ValueError(f"{self.site_id}: outcome.evidence carries {keys}")
        if self.evidence[EVIDENCE_DESCRIPTION] != self.description:
            raise ValueError(f"{self.site_id}: the evidence names another description")

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "description": self.description,
            "raw_data": self.raw_data,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: Any) -> WcOutcome:
        d = M._obj(data, "outcome", frozenset({"site_id", "description", "raw_data", "evidence"}))
        return cls(
            site_id=d["site_id"],
            description=d["description"],
            raw_data=d["raw_data"],
            evidence=d["evidence"],
        )


def decisions_of(evidence: Mapping[str, Any]) -> tuple[list[Decision], dict[int, list[Quote]]]:
    """The final decisions and verified quotes a WC journal evidence records."""
    decisions: list[Decision] = []
    verified: dict[int, list[Quote]] = {}
    for entry in evidence["sentences"]:
        verdict = Verdict(entry["verdict"])
        decisions.append(
            Decision(
                n=entry["n"],
                sentence=entry["sentence"],
                verdict=verdict,
                remove=entry["remove"],
                reason=None if entry["reason"] is None else DropReason(entry["reason"]),
            )
        )
        if verdict in KEPT:
            verified[entry["n"]] = [
                Quote(url=q["url"], title=q["title"], quote=q["quote"])
                for q in entry["quotes"]
                if q["verified"]
            ]
    return decisions, verified


def evidence_problems(
    evidence: Mapping[str, Any], description: str | None, raw_data: Mapping[str, Any] | None
) -> list[str]:
    """Is production exactly what the journal's evidence composes? The description from the
    evidence's decisions and verified quotes, its citations, the check record's verdicts, cites and
    quote digests, and the AI disclosure its recorded marking requires (`disclosure_problems`) - so
    the database alone re-checks every published sentence and its footnote."""
    try:
        decisions, verified = decisions_of(evidence)
        composed = compose(decisions, verified)
        disclosure = disclosure_problems(evidence["marking"], description, raw_data)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"the journal evidence does not compose: {exc}"]
    problems: list[str] = list(disclosure)
    if composed.description != description:
        problems.append("the description is not what the journal evidence composes")
    if description is None:
        return problems
    raw = dict(raw_data or {})
    if raw.get(M.CITATIONS_KEY) != [dict(c) for c in composed.citations]:
        problems.append("the citations are not the pages of the evidence's verified quotes")
    try:
        check = DescriptionCheck.from_dict(raw.get(CHECK_KEY))
        expected = check_record(
            decisions, composed, verified, run=evidence["run"], checked=evidence["checked"]
        )
    except (KeyError, ValueError) as exc:
        return [*problems, f"the check record does not read: {exc}"]
    if check != expected:
        problems.append("the check record is not the one the evidence's decisions give")
    return problems
