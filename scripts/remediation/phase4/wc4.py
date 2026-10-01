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
* **The verification** (`run_verification`, `apply_verification`; owner decisions O5 and O2, the
  pilots of 2026-09-27): an independent agent verifies the kept text of every site as it would be
  published (`verify`); an UNSUPPORTED or WRONG sentence is dropped, and so is every sentence the
  verifier names as the one whose reference or meaning broke; an incoherent text with none named
  is cleared; a text a drop changed goes to a new agent (`verify2`), which keeps it only when every
  sentence is SUPPORTED and the text coherent, and clears it otherwise. Nothing is ever added back.
  Each round records the sha256 of the text its question showed (`text_sha256`, the review of
  2026-09-27): a round is read only over the text it showed, so a check that moved after a
  verifier answered is refused wherever the record is read. The record (`VERIFICATION_KEY`) is in
  the journal evidence; the check record names the verifiers and the recorded sha256 of the text
  the last one confirmed (`verified_sha256`, held to the served text's).
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
  what the evidence's decisions compose, after a passed verification (`verification_problems`),
  with the AI disclosure its recorded marking requires (`marking_record`, `disclosure_problems`;
  the writer re-derives the marking from the row's old value, `old_marking_problems`).

**Two extensions of 2026-10-01** (owner decisions "Wikipedia/Wikidata reicht" and "Neu aus
Webquellen"; runbook `docs/procedures/SENTENCE_CHECK.md` sections 11 and 12). A run may be given an
explicit list of curated sites (`wc/cli.py export --sites`), and then also asks a Phase-4 text
(`Marking.PHASE4`: lane W/S/T/R's full provenance - such a text is only kept or dropped sentence by
sentence, never trimmed, and its provenance is the old one filtered to the kept sentences,
`filtered_provenance`: the attribution and the AI mark stay true) or a text a WC check kept before
(its check record is replaced). And lane WN writes a description for a site that has none
(`Marking.NONE`, `Marking.WEB`): its sentences are written by an agent from verbatim quotes, verified
exactly as a kept March sentence is, and carry `model4.WebProvenance` (lane N, `ai: generated`).

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
#: v2 (2026-09-27): the record names the text's verifiers and the sha256 of the text they confirmed.
#: No v1 record was ever written (production held none on 2026-09-27, read-only).
CHECK_VERSION = 2
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
    """Why a sentence is not published. The first two are the checker's, the next two code's, the
    last four the verification's (`run_verification`)."""

    CONTRADICTED = "contradicted"  #: a source contradicts a claim of it
    UNSUPPORTED = "unsupported"  #: no reputable, independent source supports every claim
    UNVERIFIED = "unverified"  #: its quotes were not found on the pages after the re-ask round
    LEANS = "leans-on-dropped"  #: it leans on the sentence before it, and that one went
    #: a verifier found a claim of it supported by no source
    VERIFY_UNSUPPORTED = "verify-unsupported"
    #: a verifier found a claim of it contradicted - its quote found by code or not
    VERIFY_WRONG = "verify-wrong"
    #: a verifier named it as a sentence whose reference or meaning broke in the kept text
    VERIFY_INCOHERENT = "verify-incoherent"
    #: the verification cleared the site: an incoherent text whose broken sentence the verifier
    #: could not name, or a text a drop changed that the second verifier did not confirm
    VERIFY_CLEARED = "verify-cleared"


AGENT_REASONS = frozenset({DropReason.CONTRADICTED, DropReason.UNSUPPORTED})
VERIFY_REASONS = frozenset(
    {
        DropReason.VERIFY_UNSUPPORTED,
        DropReason.VERIFY_WRONG,
        DropReason.VERIFY_INCOHERENT,
        DropReason.VERIFY_CLEARED,
    }
)


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


# ------------------------------------------------------------------------------ the verification
#: The verification rounds, in order (owner decisions O5 and O2 of 2026-09-26: every published
#: sentence is correct). A single check lets about one error in 50-60 kept sentences through (the
#: pilots of 2026-09-27); as in lane WB (CARD_DESCRIPTIONS.md 2.1) an independent agent verifies
#: every site whose check kept a sentence (`verify`), and a new one every site whose kept text a
#: drop of `verify` changed (`verify2`). Nothing is ever added: a verification only drops.
VERIFY_STAGES = ("verify", "verify2")
#: The journal evidence's key of the verification record (`apply_verification`).
VERIFICATION_KEY = "verification"
SUPPORTED, UNSUPPORTED, WRONG = "SUPPORTED", "UNSUPPORTED", "WRONG"
#: What a verifier says of one kept sentence: the pilot judge's kept verdicts.
VERIFY_VERDICTS = (SUPPORTED, UNSUPPORTED, WRONG)


class VerifyStatus(StrEnum):
    """Where a site's verification ended."""

    #: the last verifier confirmed every kept sentence and the kept text's coherence
    VERIFIED = "verified"
    #: nothing is left: the drops took every sentence, or the verification cleared the site
    CLEARED = "cleared"
    #: the check kept nothing, so there was nothing to verify
    NOTHING_KEPT = "nothing-kept"


#: One verification round as `cli.py verify-import` records it: which agent answered which
#: question, the sentence numbers the question showed as K1..Km (`shown`), the sha256 of the text
#: those sentences composed (`text_sha256`: the text as published, markers included - the review
#: of 2026-09-27 tied a round to its text, not only to its sentence numbers), each kept sentence's
#: verdict (`VERDICT_KEYS`, with what code's quote check found), `coherent` and the K numbers the
#: verifier named as broken.
ROUND_KEYS = frozenset(
    {
        "round",
        "stage",
        "batch_id",
        "answered_by",
        "answered_at",
        "prompt_sha256",
        "answer_sha256",
        "shown",
        "text_sha256",
        "verdicts",
        "coherent",
        "broken",
        "note",
    }
)
VERDICT_KEYS = frozenset({"k", "n", "verdict", "quotes", "note", "quotes_found", "quote_results"})
_RECORD_KEYS = frozenset({"status", "before", "rounds", "kept"})


def kept_numbers(decisions: Sequence[Decision]) -> list[int]:
    """The numbers of the kept sentences, in order."""
    return [decision.n for decision in decisions if decision.kept]


def _read_round(
    index: int, given: Any, shown: Sequence[int], text: str
) -> tuple[list[str], bool, list[int]]:
    """One recorded round, strictly: its number and stage, the sentences it showed (the kept ones
    of the text at that round) and the text they composed (`text`, whose sha256 the round
    recorded), one verdict per shown sentence, and `broken` - K numbers in 1..m, ascending, none
    when the text is coherent. Returns the verdicts, `coherent` and `broken`."""
    if not isinstance(given, Mapping) or set(given) != ROUND_KEYS:
        keys = sorted(given) if isinstance(given, Mapping) else given
        raise WcError(f"verification round {index} carries {keys!r}, not {sorted(ROUND_KEYS)}")
    if index > len(VERIFY_STAGES) or (given["round"], given["stage"]) != (
        index,
        VERIFY_STAGES[index - 1],
    ):
        raise WcError(
            f"verification round {index} is recorded as round {given['round']!r}, stage "
            f"{given['stage']!r}: the rounds are {list(VERIFY_STAGES)}, in order"
        )
    if list(given["shown"]) != list(shown):
        raise WcError(
            f"verification round {index} showed sentences {given['shown']}, the text it verified "
            f"holds {list(shown)}"
        )
    if given["text_sha256"] != M.text_sha256(text):
        raise WcError(
            f"verification round {index} verified the text of sha256 {given['text_sha256']!r}, "
            f"the kept text now composes {M.text_sha256(text)!r}: the check moved after the "
            "verifier answered - a text is published only as a verifier was shown it"
        )
    verdicts = given["verdicts"]
    if not isinstance(verdicts, list) or any(
        not isinstance(v, Mapping) or set(v) != VERDICT_KEYS for v in verdicts
    ):
        raise WcError(f"verification round {index}: a verdict is not {sorted(VERDICT_KEYS)}")
    if [v["k"] for v in verdicts] != list(range(1, len(shown) + 1)) or [
        v["n"] for v in verdicts
    ] != list(shown):
        raise WcError(f"verification round {index}: not one verdict per shown sentence, in order")
    if any(v["verdict"] not in VERIFY_VERDICTS for v in verdicts):
        raise WcError(f"verification round {index}: a verdict is not one of {VERIFY_VERDICTS}")
    coherent, broken = given["coherent"], given["broken"]
    if not isinstance(coherent, bool):
        raise WcError(f"verification round {index}: coherent is true or false")
    if (
        not isinstance(broken, list)
        or any(isinstance(k, bool) or not isinstance(k, int) for k in broken)
        or broken != sorted(set(broken))
        or any(not 1 <= k <= len(shown) for k in broken)
    ):
        raise WcError(f"verification round {index}: broken {broken!r} is not ascending K numbers")
    if coherent and broken:
        raise WcError(f"verification round {index}: a coherent text names no broken sentence")
    return [v["verdict"] for v in verdicts], coherent, list(broken)


def run_verification(
    decisions: Sequence[Decision],
    quotes: Mapping[int, Sequence[Quote]],
    rounds: Sequence[Mapping[str, Any]],
) -> tuple[list[Decision], list[dict[str, Any]], VerifyStatus | None]:
    """The decisions after the recorded verification rounds, each round with what code derives
    from it - `passed`, `drops` (sentence number -> why) and `cleared` - and where the
    verification stands: `None` while a round is due. A round is read only over the text it
    showed: its `shown` sentence numbers and its `text_sha256` must be what the decisions give at
    that round (`_read_round`), so a check that moved after a verifier answered is refused.

    `decisions` are the check's (every round, the pronoun rule), `quotes` the verified quotes of
    each sentence the check kept. Per round, on the kept sentences of the text as it stands:

    * every sentence SUPPORTED and the text coherent: the site is verified, nothing moves;
    * round 1 otherwise: an UNSUPPORTED or WRONG sentence is dropped (a WRONG whether code found
      its contradicting quote or not), and so is every sentence the verifier named as broken; an
      incoherent text with no sentence named is cleared; then the pronoun rule (`follow_drops`).
      A text a drop changed and that keeps a sentence is due for round 2 (`verify2`), because a
      drop can break what stays;
    * round 2 otherwise: the site is cleared - a text is published only as a verifier confirmed it.

    Nothing is ever added back. No round follows a verified or cleared site, or round 2."""
    current = list(decisions)
    derived: list[dict[str, Any]] = []
    status = None if kept_numbers(current) else VerifyStatus.NOTHING_KEPT
    for index, given in enumerate(rounds, start=1):
        if status is not None:
            raise WcError(f"verification round {index}: the verification had ended ({status})")
        shown = kept_numbers(current)
        verdicts, coherent, broken = _read_round(
            index, given, shown, str(compose(current, quotes).description)
        )
        passed = coherent and all(verdict == SUPPORTED for verdict in verdicts)
        drops: dict[int, DropReason] = {}
        cleared = not passed and (index == len(VERIFY_STAGES) or not (coherent or broken))
        if cleared:
            drops = dict.fromkeys(shown, DropReason.VERIFY_CLEARED)
        elif not passed:
            for n, verdict in zip(shown, verdicts, strict=True):
                if verdict == WRONG:
                    drops[n] = DropReason.VERIFY_WRONG
                elif verdict == UNSUPPORTED:
                    drops[n] = DropReason.VERIFY_UNSUPPORTED
            for k in broken:
                drops.setdefault(shown[k - 1], DropReason.VERIFY_INCOHERENT)
        current = [
            dataclasses.replace(d, verdict=Verdict.DROP, remove=None, reason=drops[d.n])
            if d.n in drops
            else d
            for d in current
        ]
        if not cleared:
            current = follow_drops(current)
        derived.append(
            {
                **given,
                "passed": passed,
                "drops": {str(n): reason.value for n, reason in sorted(drops.items())},
                "cleared": cleared,
            }
        )
        if passed:
            status = VerifyStatus.VERIFIED
        elif not kept_numbers(current):
            status = VerifyStatus.CLEARED
    return current, derived, status


def apply_verification(
    decisions: Sequence[Decision],
    quotes: Mapping[int, Sequence[Quote]],
    rounds: Sequence[Mapping[str, Any]],
) -> tuple[list[Decision], dict[str, Any]]:
    """The verified decisions and the verification record (`VERIFICATION_KEY`): its status, the
    sentences the check kept (`before`), every round with what code derives from it, and the
    sentences kept after the verification. A verification still due is refused (`WcError`)."""
    current, derived, status = run_verification(decisions, quotes, rounds)
    if status is None:
        raise WcError(
            f"the verification is not finished: round {len(derived) + 1} "
            f"({VERIFY_STAGES[len(derived)]}) is due"
        )
    record = {
        "status": status.value,
        "before": kept_numbers(decisions),
        "rounds": derived,
        "kept": kept_numbers(current),
    }
    return current, record


# ------------------------------------------------------------------------------ the record
_CHECK_KEYS = frozenset(
    {
        "v",
        "run",
        "checker",
        "checked_sha256",
        "kept",
        "of",
        "trimmed",
        "sentences",
        "desc_sha256",
        "verifiers",
        "verified_sha256",
    }
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
    """`raw_data._description_check` v2: that the served text was checked sentence by sentence,
    by whom, what stayed, the text it describes (`desc_sha256`, like the provenance's), and who
    verified it (`verifiers`, one agent per verification round) and which text the last one was
    shown and confirmed (`verified_sha256`: the round's recorded `text_sha256`, which
    `run_verification` holds to what the check composes and `wc_problems` to the served text's)."""

    run: str
    checker: str
    checked_sha256: str  #: the stored March text that was checked, markers included
    kept: int
    of: int
    trimmed: int
    sentences: tuple[CheckedSentence, ...]
    desc_sha256: str
    verifiers: tuple[str, ...]  #: the agents that verified the text, one per round, in order
    verified_sha256: str  #: the recorded sha256 of the text the last verifier confirmed
    v: int = CHECK_VERSION

    def __post_init__(self) -> None:
        if self.v != CHECK_VERSION or isinstance(self.v, bool):
            raise ValueError(f"check.v: {self.v!r} is not version {CHECK_VERSION}")
        M._need_text(self.run, "check.run")
        if self.checker not in M.AI_SYSTEMS:
            raise ValueError(
                f"check.checker: {self.checker!r} is not one of {sorted(M.AI_SYSTEMS)!r}"
            )
        M._need_hex(self.checked_sha256, "check.checked_sha256")
        M._need_hex(self.desc_sha256, "check.desc_sha256")
        M._need_hex(self.verified_sha256, "check.verified_sha256")
        if (
            not isinstance(self.verifiers, tuple)
            or not 1 <= len(self.verifiers) <= len(VERIFY_STAGES)
            or len(set(self.verifiers)) != len(self.verifiers)
        ):
            raise ValueError(
                f"check.verifiers: {self.verifiers!r} is not one distinct agent per verification "
                f"round (1 to {len(VERIFY_STAGES)}): a kept text is published only verified"
            )
        for name in self.verifiers:
            M._need_text(name, "check.verifiers")
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
            "verifiers": list(self.verifiers),
            "verified_sha256": self.verified_sha256,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DescriptionCheck:
        d = M._obj(data, "check", _CHECK_KEYS)
        if not isinstance(d["sentences"], list) or not isinstance(d["verifiers"], list):
            raise ValueError("check.sentences and check.verifiers are lists")
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
            verifiers=tuple(d["verifiers"]),
            verified_sha256=d["verified_sha256"],
        )


def check_record(
    decisions: Sequence[Decision],
    composed: Composed,
    quotes: Mapping[int, Sequence[Quote]],
    *,
    run: str,
    checked: str | None,
    verification: Mapping[str, Any],
) -> DescriptionCheck:
    """The public record of a kept text: every sentence's verdict, the numbers its markers carry
    and the sha256 of each verified quote; `checked` is the stored text that was asked, and
    `verification` the site's verification record (`apply_verification`), whose verifiers and the
    recorded sha256 of the text the last one was shown (its round's `text_sha256`) the record
    names - a kept text is published only verified. A site that had no description (lane WN) was
    asked about no stored text: `checked` is `None` and `checked_sha256` the sha256 of the empty
    text."""
    if composed.description is None:
        raise WcError("a cleared site has no check record")
    if verification["status"] != VerifyStatus.VERIFIED.value:
        raise WcError(f"a kept text is published only verified, not {verification['status']!r}")
    rounds = verification["rounds"]
    return DescriptionCheck(
        run=run,
        checker=M.AI_SYSTEM,
        checked_sha256=M.text_sha256(checked or ""),
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
        verifiers=tuple(r["answered_by"] for r in rounds),
        verified_sha256=rounds[-1]["text_sha256"],
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
    #: a site-list run (2026-10-01): a Phase-4 text, lane W/S/T/R's full provenance. Its sentences
    #: are only kept or dropped (a trim could not be written into the provenance's spans), and the
    #: provenance it keeps is the old one filtered to the kept sentences (`filtered_provenance`)
    PHASE4 = "phase4"
    #: a site-list run: a text lane WN wrote (`model4.WebProvenance`); asked again, it stays lane N's
    WEB = "web"
    #: lane WN: the site has no description (NULL or blank); the text is written new, lane N's
    NONE = "none"


def is_empty(text: str | None) -> bool:
    """No description: NULL or blank - lane WN's population, and `Marking.NONE`."""
    return text is None or not text.strip()


def old_marking(site: M.PlanSite, *, listed: bool = False) -> Marking:
    """How the stored text is marked (`Marking`). A site without a description is `NONE` (it carries
    none of WC's three keys: they belong to a text). A full Phase-4 provenance, a lane-N one, a record
    that does not parse, and a text lane WC checked before are not a normal run's to check (`WcError`,
    `ValueError`); a site-list run (`listed`, 2026-10-01) asks them too - the marking is then what the
    stored provenance says (a check record beside it is replaced by the new one)."""
    raw = site.raw_data or {}
    if is_empty(site.description):
        stale = sorted(WC_KEYS & raw.keys())
        if stale:
            raise WcError(f"no description beside {stale} in raw_data: a cleared site carries none")
        return Marking.NONE
    if CHECK_KEY in raw and not listed:
        raise WcError("the stored text was checked sentence by sentence before")
    if M.PROVENANCE_KEY in raw:
        provenance = M.provenance_from_dict(raw[M.PROVENANCE_KEY])
        if isinstance(provenance, M.LegacyProvenance):
            return Marking.L
        if not listed:
            raise WcError(f"lane {provenance.lane.value} wrote this text in Phase 4")
        return Marking.WEB if isinstance(provenance, M.WebProvenance) else Marking.PHASE4
    return Marking.UNCLAIMED if legacy4.legacy_provenance(site) is None else Marking.MARCH


def marking_record(site: M.PlanSite, *, listed: bool = False) -> dict[str, Any]:
    """The journal evidence's `marking`: how the checked text was marked (`old_marking`) and what
    lane L's claim rests on - whether the site is in the pre-March snapshot and the sha256 of its
    text there (`None` when it holds none) - so the disclosure a written text needs can be asked
    of the database alone (`disclosure_problems`)."""
    snapshot = site.snapshot_description
    return {
        "old": old_marking(site, listed=listed).value,
        "in_snapshot": site.in_snapshot,
        "snapshot_sha256": None if snapshot is None else M.text_sha256(snapshot),
    }


def old_marking_problems(
    marking: Mapping[str, Any], checked: str | None, old_raw: Mapping[str, Any] | None
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
        if isinstance(provenance, M.LegacyProvenance):
            derived = Marking.L
        elif isinstance(provenance, M.WebProvenance):
            derived = Marking.WEB
        else:
            derived = Marking.PHASE4
    elif is_empty(checked):
        derived = Marking.NONE
    elif marking["in_snapshot"] and M.text_sha256(checked) != marking["snapshot_sha256"]:
        derived = Marking.MARCH
    else:
        derived = Marking.UNCLAIMED
    if marking["old"] != derived.value:
        return [f"the recorded marking {marking['old']!r} is not the pair's {derived.value!r}"]
    return []


#: The provenance a written text must carry, by the marking of the text that was asked (the others -
#: lane L's marked and unmarked March texts and the unclaimed - are `disclosure_problems`' own).
_WANTED_PROVENANCE: Mapping[str, type] = {
    Marking.PHASE4.value: M.Provenance,
    Marking.WEB.value: M.WebProvenance,
    Marking.NONE.value: M.WebProvenance,
}


def disclosure_problems(
    marking: Mapping[str, Any], description: str | None, raw_data: Mapping[str, Any] | None
) -> list[str]:
    """The AI disclosure (EU AI Act) a written pair must carry, required and not only checked where
    present (the review of 2026-09-26): a kept text of a March text (`L`, `march-unmarked`) carries
    lane L's provenance hashing it - unless the kept text is the pre-March one, which lane L's rule
    never claims (`legacy4.legacy_provenance`); every other pair - an unclaimed text (HUMAN_ONLY D7),
    a cleared site - carries none. A Phase-4 text (`PHASE4`) keeps its full provenance, a text lane
    WN wrote or wrote again (`NONE`, `WEB`) carries lane N's: required, hashing the written text."""
    wanted = _WANTED_PROVENANCE.get(marking["old"])
    if wanted is not None:
        stored = (raw_data or {}).get(M.PROVENANCE_KEY)
        if description is None:
            return ["a provenance beside a cleared description"] if stored is not None else []
        if stored is None:
            return [f"the AI disclosure is missing: a {marking['old']} text carries its provenance"]
        try:
            provenance = M.provenance_from_dict(stored)
        except ValueError as exc:
            return [f"the AI disclosure does not read: {exc}"]
        if not isinstance(provenance, wanted) or provenance.desc_sha256 != M.text_sha256(
            description
        ):
            return [
                f"the AI disclosure is not the {wanted.__name__} of the written text "
                f"(a {marking['old']} text)"
            ]
        return []
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


def filtered_provenance(
    old: M.Provenance, kept: Sequence[int], *, of: int, description: str
) -> M.Provenance:
    """The Phase-4 provenance of a text whose sentences were checked: the old one filtered to the
    kept sentences (`kept`, 1-based, of the `of` the checked text holds), `desc_sha256` the new
    text's, the sources only the kept sentences still cite, the AI system the new write's
    (`model4.AI_SYSTEM`: the same marks, the attribution and the licence stay true - what was
    selected from the pinned source is still verbatim, only fewer sentences), and the card `None`
    (its items name sentences that are no longer the text's; lane WB writes the new card).

    Refused (`WcError`): a provenance whose published sentences are not the checked sentences one
    for one (the shared splitter and a join of `JOIN_AFTER` disagree - 1 of 2,781 on 2026-10-01), a
    text with no kept sentence, and one whose attribution source no kept sentence cites."""
    if len(old.sentences) != of:
        raise WcError(
            f"the provenance lists {len(old.sentences)} published sentences, the checked text "
            f"{of}: they cannot be matched one for one"
        )
    if not kept:
        raise WcError("a provenance of nothing kept")
    wanted = set(kept)
    sentences = tuple(s for n, s in enumerate(old.sentences, start=1) if n in wanted)
    cited = {sentence.src for sentence in sentences}
    sources = tuple(source for source in old.sources if source.id in cited)
    if old.attribution.url not in {source.url for source in sources}:
        raise WcError(
            "no kept sentence cites the source the attribution names: the text no longer adapts it"
        )
    return dataclasses.replace(
        old,
        ai_system=M.AI_SYSTEM,
        sources=sources,
        sentences=sentences,
        card=None,
        desc_sha256=M.text_sha256(description),
    )


def provenance_after(
    site: M.PlanSite,
    description: str,
    *,
    kept: Sequence[int] | None = None,
    of: int | None = None,
    trimmed: int = 0,
    listed: bool = False,
) -> M.LegacyProvenance | M.Provenance | M.WebProvenance | None:
    """The provenance the kept text carries: lane L's, hashing the kept text, for a March text -
    marked by lane L, or one lane L's rule claims and no marking carries yet (`Marking.MARCH`: the
    AI footnote must not be missing from a published March text); withdrawn by
    `legacy4.legacy_provenance` should the kept text be the pre-March one. None for an unclaimed
    text (HUMAN_ONLY D7): a trimmed pre-March text is still not the March chain's. Lane N's
    (`model4.WebProvenance`) for a text lane WN wrote (`NONE`, `WEB`). For a Phase-4 text (`PHASE4`,
    site-list runs) the old provenance filtered to the kept sentences (`filtered_provenance`: `kept`
    and `of` name them; a Phase-4 text is never trimmed, `trimmed` must be 0)."""
    marking = old_marking(site, listed=listed)
    if marking is Marking.UNCLAIMED:
        return None
    if marking in (Marking.NONE, Marking.WEB):
        return M.WebProvenance(desc_sha256=M.text_sha256(description))
    if marking is Marking.PHASE4:
        if trimmed or kept is None or of is None:
            raise WcError("a Phase-4 text is only kept or dropped by sentence, never trimmed")
        old = M.provenance_from_dict((site.raw_data or {})[M.PROVENANCE_KEY])
        if not isinstance(old, M.Provenance):
            raise WcError("a Phase-4 text carries a full provenance")
        return filtered_provenance(old, kept, of=of, description=description)
    return legacy4.legacy_provenance(
        dataclasses.replace(
            site, description=description, description_sha256=M.text_sha256(description)
        )
    )


def written_raw_data(
    site: M.PlanSite,
    composed: Composed,
    check: DescriptionCheck | None,
    *,
    listed: bool = False,
) -> dict[str, Any] | None:
    """The `raw_data` a WC write leaves: the old object less the three WC keys, plus - for a kept
    text - its citations, its check record and the provenance its marking calls for (lane L's moved
    to the kept text, the filtered Phase-4 one, lane N's, or none: `provenance_after`). `None` when
    nothing remains (a cleared site whose `raw_data` held only WC's keys)."""
    new = {key: value for key, value in (site.raw_data or {}).items() if key not in WC_KEYS}
    if composed.description is not None:
        if check is None:
            raise WcError("a kept text is written with its check record")
        new[M.CITATIONS_KEY] = [dict(citation) for citation in composed.citations]
        new[CHECK_KEY] = check.to_dict()
        provenance = provenance_after(
            site,
            composed.description,
            kept=[n for n, cites in enumerate(composed.cites, start=1) if cites],
            of=len(composed.cites),
            trimmed=check.trimmed,
            listed=listed,
        )
        if provenance is not None:
            new[M.PROVENANCE_KEY] = provenance.to_dict()
    elif check is not None:
        raise WcError("a cleared site carries no check record")
    return new or None


# ------------------------------------------------------------------------------ the invariants
_CITATION_KEYS = frozenset({"n", "url", "title", "domain"})


def wc_problems(
    description: str | None,
    raw_data: Mapping[str, Any] | None,
    *,
    marking: str | None = None,
) -> list[str]:
    """What a WC-written site breaks; empty = nothing. The writer's plan, its read-back and the
    acceptance ask exactly this of the stored (or planned) pair:

    * a cleared site (description NULL) carries none of the three WC keys;
    * a kept text carries its check record, whose `desc_sha256` is the text's; lane L's provenance
      where present, whose `desc_sha256` is the text's too (D4) - or, when the recorded old
      `marking` (`marking_record`'s `old`) is a Phase-4 text's, a full provenance, and a lane-N
      text's (`none`, `web`), `model4.WebProvenance`; citations of exactly the numbers
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
    if check.verified_sha256 != digest:
        problems.append(
            "the check record's verified_sha256 is not the sha256 of the description: the served "
            "text is not the one its verifier confirmed"
        )
    if M.PROVENANCE_KEY in raw:
        try:
            provenance = M.provenance_from_dict(raw[M.PROVENANCE_KEY])
        except ValueError as exc:
            provenance = None
            problems.append(f"the provenance does not read: {exc}")
        allowed = _WANTED_PROVENANCE.get(str(marking), M.LegacyProvenance)
        if provenance is not None and not isinstance(provenance, allowed):
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
#: description the decisions compose (`description`, `None` for a clear), every sentence's final
#: decision with its decision before the verification (`checked`), the agent's quotes and what the
#: check said of each (`sentences`), the answers they came from, and the verification record
#: (`VERIFICATION_KEY`, `apply_verification`).
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
        VERIFICATION_KEY,
    }
)
EVIDENCE_DESCRIPTION = "description"
EVIDENCE_DECISION = "O5 2026-09-26: Satzweise pruefen und kuerzen"
#: Lane WN's journal evidence names the owner decision it executes (2026-10-01).
EVIDENCE_DECISION_WN = "2026-10-01: Neu aus Webquellen"


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
        if isinstance(self.evidence, dict) and VERIFICATION_KEY not in self.evidence:
            raise ValueError(
                f"{self.site_id}: the outcome carries no verification - it was built before the "
                "verify stage and is never written (verify-export, verify-import, build again)"
            )
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


def checked_of(evidence: Mapping[str, Any]) -> tuple[list[Decision], dict[int, list[Quote]]]:
    """The decisions a WC journal evidence records from before the verification (each sentence's
    `checked`: the check rounds and the pronoun rule), and the verified quotes of every sentence
    the check kept - what the verification started from (`apply_verification`)."""
    decisions: list[Decision] = []
    verified: dict[int, list[Quote]] = {}
    for entry in evidence["sentences"]:
        checked = entry["checked"]
        verdict = Verdict(checked["verdict"])
        reason = None if checked["reason"] is None else DropReason(checked["reason"])
        if reason in VERIFY_REASONS:
            raise WcError(f"S{entry['n']}: a check decision carries the verification's {reason}")
        decisions.append(
            Decision(entry["n"], entry["sentence"], verdict, checked["remove"], reason)
        )
        if verdict in KEPT:
            verified[entry["n"]] = [
                Quote(url=q["url"], title=q["title"], quote=q["quote"])
                for q in entry["quotes"]
                if q["verified"]
            ]
    return decisions, verified


def verification_problems(evidence: Mapping[str, Any], description: str | None) -> list[str]:
    """Did the site pass its verification, as the journal evidence records it? The record is there
    and is exactly what its rounds give from the check's decisions (`apply_verification`: every
    round read over the text it recorded, so a check that moved under it is refused); the
    evidence's final decisions are the verified ones; a kept text is the one the last verifier
    confirmed (`text_sha256`) and a cleared site's verification ended cleared or had nothing to
    verify; and no verifier is an agent that checked the site, none verified it twice. The writer's
    plan, `build` and the acceptance ask it: a plan built before the verify stage, or whose record
    was edited, is never written."""
    record = evidence.get(VERIFICATION_KEY)
    if not isinstance(record, Mapping) or set(record) != _RECORD_KEYS:
        return [
            "the site carries no verification record: its text was never verified (a plan "
            "built before the verify stage is never written)"
        ]
    try:
        before, quotes = checked_of(evidence)
        given = [{key: r[key] for key in ROUND_KEYS} for r in record["rounds"]]
        final, expected = apply_verification(before, quotes, given)
        recorded, _ = decisions_of(evidence)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"the verification does not read: {exc}"]
    problems: list[str] = []
    if dict(record) != expected:
        problems.append("the verification record is not what its rounds give")
    if final != recorded:
        problems.append("the evidence's decisions are not the verified ones")
    verified = expected["status"] == VerifyStatus.VERIFIED.value
    if (description is not None) != verified:
        problems.append(
            f"a {'kept' if description is not None else 'cleared'} description beside a "
            f"verification that ended {expected['status']}"
        )
    elif verified and expected["rounds"][-1]["text_sha256"] != M.text_sha256(str(description)):
        problems.append("the description is not the text the last verifier confirmed")
    checkers = {attempt["answered_by"] for attempt in evidence["answers"]}
    names = [r["answered_by"] for r in expected["rounds"]]
    for name in names:
        if name in checkers:
            problems.append(
                f"the verifier {name} checked this site: a verification is an independent agent's"
            )
    if len(set(names)) != len(names):
        problems.append("one agent verified the site twice: verify2 is a new agent's")
    return problems


def _phase4_provenance_problems(
    evidence: Mapping[str, Any], raw_data: Mapping[str, Any] | None
) -> list[str]:
    """A Phase-4 text keeps its provenance filtered to the kept sentences: one published sentence
    per kept sentence of the evidence, no card (`filtered_provenance`)."""
    try:
        provenance = M.provenance_from_dict((raw_data or {})[M.PROVENANCE_KEY])
    except (KeyError, ValueError):
        return []  # `disclosure_problems` names a missing or unreadable one
    if not isinstance(provenance, M.Provenance):
        return []
    problems = []
    if len(provenance.sentences) != evidence["kept"]:
        problems.append(
            f"the provenance lists {len(provenance.sentences)} published sentences, the evidence "
            f"kept {evidence['kept']}"
        )
    if provenance.card is not None:
        problems.append("the provenance still names a card of sentences that changed")
    return problems


def evidence_problems(
    evidence: Mapping[str, Any], description: str | None, raw_data: Mapping[str, Any] | None
) -> list[str]:
    """Is production exactly what the journal's evidence composes? The description from the
    evidence's decisions and verified quotes, its citations, the check record's verdicts, cites,
    quote digests and verifiers, the verification it passed (`verification_problems`), and the AI
    disclosure its recorded marking requires (`disclosure_problems`) - so the database alone
    re-checks every published sentence, its verification and its footnote."""
    try:
        decisions, verified = decisions_of(evidence)
        composed = compose(decisions, verified)
        disclosure = disclosure_problems(evidence["marking"], description, raw_data)
    except (KeyError, TypeError, ValueError) as exc:
        return [f"the journal evidence does not compose: {exc}"]
    problems: list[str] = list(disclosure)
    if composed.description != description:
        problems.append("the description is not what the journal evidence composes")
    if evidence["marking"]["old"] == Marking.PHASE4.value and description is not None:
        problems.extend(_phase4_provenance_problems(evidence, raw_data))
    problems.extend(verification_problems(evidence, description))
    if description is None:
        return problems
    raw = dict(raw_data or {})
    if raw.get(M.CITATIONS_KEY) != [dict(c) for c in composed.citations]:
        problems.append("the citations are not the pages of the evidence's verified quotes")
    try:
        check = DescriptionCheck.from_dict(raw.get(CHECK_KEY))
        expected = check_record(
            decisions,
            composed,
            verified,
            run=evidence["run"],
            checked=evidence["checked"],
            verification=evidence[VERIFICATION_KEY],
        )
    except (KeyError, TypeError, ValueError) as exc:
        return [*problems, f"the check record does not read: {exc}"]
    if check != expected:
        problems.append("the check record is not the one the evidence's decisions give")
    return problems
