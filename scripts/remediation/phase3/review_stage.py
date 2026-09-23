"""Stage "reviewer" of the discover pass: one finder's finding in, one verdict on it out.

Why this stage exists, as one measurement: the discover pass asks the finder's question and nothing
else, so **the finder's precision is the pipeline's precision** - and the census measured the
false-negative rate at 60 % (24 of the 40 errors a blinded check found were not flagged). The answer
to that is a second, differently-asked question, not a better finder. The pilot's reviewer refuted
61 % of the findings it looked at, which is why a finding that survives it is worth writing.

Three things this module is **not**:

* it does not write to the database. It produces verdicts; the writer applies them, applying only
  `refuted = false`, with a conditional WHERE clause and a journal entry (plan Phase 3).
* it does not invent. A refutation that cites a page must quote a sentence that occurs in the page
  the run fetched, checked by the **same** `discover_stage.claim_problems` the finder's citations go
  through - an invented source is the same defect in both roles, and two spellings of that check
  would be two chances to drift.
* it does not review a finding that proposes nothing. A verdict of `CORRECT` or `UNVERIFIABLE` has
  no change a writer could apply, so reviewing it would spend a call to produce a verdict nobody can
  act on. Those findings are recorded as `unreviewable` **with the finder's own reason** - which is
  also the honest producer of "there is no correction here" that the wave-6 gap named.
* it does not re-open a decision. In the search lane a rerun field can be a planned write the mass
  lane did not write (held by hand, `HUMAN_ONLY.md` B7, or stopped by the boundary check, B8; the
  plan carries it under `rerun_unwritten`). A rerun answer that proposes that same value again is
  recorded as `unreviewable` naming the decision, and never reaches the writer: whether a new
  source changes the decision is Martin's call, not the lane's.

The finding the reviewer reads is the finder's answer **verbatim**, next to the same stored value and
the same evidence files the finder had. It judges the finding that was actually made; a re-rendered
copy would be a different finding.

Resumption: a review answer already in `reviews/` is re-read, never re-bought, and the report says
how many were `resumed`. The discover stage cannot do that, because its `model.json` numbers come
from the calls themselves - a partially judged discover batch re-buys its answered calls, which is
recorded in `AUDIT_LOG.md` rather than hidden.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Dual use: `python -m phase3.review_stage` and `python scripts/remediation/phase3/run.py`. The
# package is not installed, so the parent directory must be importable first (same shim as `run.py`).
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402  - the finder's answers and citation check
from phase3 import fetch_stage as F  # noqa: E402  - the evidence store both stages read
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402  - the seam this stage builds its calls through
from phase3 import search_evidence as SE  # noqa: E402  - the proposals the mass lane did not write
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: The stage of a review call, pinned rather than a parameter: the question below is the reviewer's,
#: and a caller that could pass `finder` here would be asking the finder's question of a finding.
STAGE = M.Stage.REVIEWER

#: The only finder verdict that proposes a change, and so the only one a reviewer is asked about.
REVIEWED_VERDICT = "WRONG"

#: The decision behind each kind of unwritten proposal (`search_evidence.UNWRITTEN_KINDS`), named in
#: the refusal of a rerun answer that repeats one.
UNWRITTEN_DECISION: dict[str, str] = {
    "held": "held by hand; HUMAN_ONLY.md B7, decided 2026-09-21: not written",
    "write_gate": (
        "stopped by write_gate.py's country-boundary check; HUMAN_ONLY.md B8, decided 2026-09-21: "
        "such rows are not written"
    ),
}
if set(UNWRITTEN_DECISION) != set(SE.UNWRITTEN_KINDS):
    raise InputError(f"every unwritten kind {SE.UNWRITTEN_KINDS} needs its decision named here")

#: The answer's shape, parsed. One refutation per finding, and a refutation that cannot be read is a
#: problem rahter than a `False`: "unreadable" and "not refuted" must not be the same value.
#: The question numbers its answer steps, and the model mirrors the numbering: one measured answer
#: opened the verdict line with a literal "2. " and the strict pattern read no verdict at all, which
#: silently turned a grounded refutation into `UNRESOLVED` and dropped a source line into the
#: wrong-verdict check. A leading list marker is part of the shape now. The guards are untouched:
#: exactly one hit, and the value has to be one of `REFUTED_VALUES`.
REFUTED_RE = re.compile(r"^\s*(?:\d+[.)]\s*)?REFUTED:\s*(?P<value>\S+)\s*$", re.MULTILINE)
WHY_PREFIX = "WHY:"

#: What a `REFUTED:` line may say. `UNRESOLVED` is neither: the evidence does not settle it, and the
#: writer treats an unresolved finding exactly like a refuted one (it is not applied).
#:
#: The three-state value is why the comparisons below and in `ReviewVerdict` use `is True` / `is
#: False` rather than truthiness: `if refuted:` would collapse a **recorded** `UNRESOLVED` into "not
#: refuted", which is the one confusion this stage exists to prevent. A linter that reads the
#: identity operators as a mistake is reporting its own rubric, and the adjudication is in
#: `AUDIT_LOG.md` (judge-checker table).
REFUTED_VALUES: dict[str, bool | None] = {"YES": True, "NO": False, "UNRESOLVED": None}

REFUTED_SHAPE = ", ".join(REFUTED_VALUES)

#: A run of up to four words between a subject ("stored", "proposed") and its verb, none of which
#: starts a second clause or names the other half: "the stored `Temple complex` is not shown wrong"
#: matches, "the stored -1500 is contradicted and -1000 is not contradicted" does not.
_SAME_CLAUSE = (
    r"(?: (?!(?:is|was|are|and|or|but|while|so|whereas|proposed|proposal|stored|not|also)\b)"
    r"[^\s,;:.\u2014\u2013]+){0,4}"
)

#: A half's name may stand in quotes or backticks: `the "reason" half fails` (batch-0053, a hand hold,
#: `REFUTED: NO`; the run's two other such sentences are `YES` answers).
_OPEN_QUOTE = r"[`\"'\u201c\u2018]?"
_CLOSE_QUOTE = r"[`\"'\u201d\u2019]?"

#: Whose proposal a "neither the reason nor <owner> proposed value is contradicted" sentence names -
#: the half that **holds** (batch-0237: "neither the finding's reason nor its proposed value is
#: contradicted"). Each is one fixed-width lookbehind, because `re` allows no other kind.
_NOR_OWNERS: tuple[str, ...] = (
    "its",
    "the finding['\u2019]s",
    "the finder['\u2019]s",
    "finding['\u2019]s",
    "finder['\u2019]s",
)

#: The phrases by which a `WHY:` line names a half of the finding that **fails**. The frozen question
#: (`model_stage.REVIEWER_QUESTION`) asks for "one sentence naming the half that fails, or that both
#: hold", and `REFUTED: NO` is defined there as "both halves hold" - so a `NO` whose own sentence
#: names a failing half contradicts itself, and the writer holds it
#: (`write_stage.RULE_REVIEW_CONTRADICTS`). The search pilot met the class twice (Lake Mungo:
#: "Neither half holds ...", Odeon: "the stored text is not shown wrong", both `REFUTED: NO`), and the
#: mass lane met it by hand in the 72 held rows.
#:
#: Derived from the reviewer's own answers, not from a grammar: every phrase below is how the 4,579
#: answers in `runs/mass/batch-*/reviews` (2,202 `YES`, 2,204 `NO`, 173 other) say that a half fails.
#: Fourteen of the eighteen turn up mostly in `YES` answers, which is what makes them a refutation's
#: words in a `NO`; four do not ("neither half holds" 75 `NO` / 33 `YES`, "the evidence supports the
#: stored value" 13 / 9, "neither half is established" 7 / 2, "the proposal fails" 2 / 2) - the
#: reviewer uses them against its own verdict line, and they are kept because what they say is a
#: failing half, which is all a `NO` may not say. Each is bound to its subject: a phrase about the
#: *stored* value failing names the reason half, one about the *proposed* value failing names the
#: value half, and the same words about the other value ("the proposed -1000 is not contradicted",
#: "neither the reason nor the proposal fails") are the half that holds and are not matched.
#:
#: Measured 2026-09-23 with `output/remediation/tools/measure_review_holds.py` on the mass lane:
#: it holds 51 of the 72 hand-held rows and 77 of the 994 rows that were written and accepted. Read
#: one by one, about 10 of those 77 use a phrase against their own content (the sentence goes on to
#: say the stored value is wrong), 5 to 8 say both, and 60 to 62 do say the stored value is not shown
#: wrong or the proposal is contradicted - the class the hand-read held 72 of and missed there (three
#: readings: the builder's 62/10/5, the review's about 61/8/8, the fixer's 60/10/7). The false holds
#: sit under four phrases, and a row those four hold goes to the hand-read (`HAND_READ_PHRASES`).
#: Deterministic and deliberately literal: a sentence that says the same thing in other words is not
#: caught, and the hand holds also hold rows for reasons no phrase names (a finer stored type, a
#: bucket nudge), so this is a floor under the hand-read, not a replacement for it.
#:
#: Narrowed 2026-09-23 by the fixer's review, with the count unchanged: "the proposed value is
#: contradicted" matched three `NO` sentences that say the value half **holds** ("neither the
#: finding's reason nor its proposed value is contradicted", "contradicted neither by Wikipedia nor
#: Wikidata", "contradicted by the evidence? No") and one conditional ("contradicted only if"); and a
#: half's name may stand in quotes (`the "reason" half fails`, batch-0053, whose hand hold that phrase
#: had caught by the misreading). Recall stays 51 of 72, written holds 77 of 994.
FAILING_HALF_PHRASES: tuple[tuple[str, str], ...] = (
    ("neither half holds", r"\bneither half holds\b"),
    ("neither half is established", r"\bneither half is (?:established|shown|supported)\b"),
    ("both halves fail", r"\bboth halves fail\b"),
    (
        "the half that fails is named",
        r"\bthe half that fails is the (?:reason|value|proposal|proposed value)\b",
    ),
    (
        "the reason half fails",
        r"\bthe " + _OPEN_QUOTE + r"(?:reason|first)" + _CLOSE_QUOTE + r" half fails\b(?! only if)",
    ),
    (
        "the value half fails",
        r"\bthe "
        + _OPEN_QUOTE
        + r"(?:value|second|proposal|proposed[- ]value)"
        + _CLOSE_QUOTE
        + r" half fails\b(?! only if)",
    ),
    (
        "the reason fails",
        r"(?<!nor )\bthe (?:finding'?s |finder'?s )?reason(?:ing)? fails\b(?! only if)",
    ),
    ("the proposal fails", r"(?<!nor )\bthe proposal fails\b(?! only if)"),
    (
        "the reason does not hold",
        r"\breason(?:ing)? (?:half )?(?:does not|doesn't|did not) hold\b",
    ),
    (
        "the stored value is not shown wrong",
        r"\bstored" + _SAME_CLAUSE + r" (?:is|was|are) not shown (?:to be )?wrong\b",
    ),
    (
        # Added 2026-09-23 from the re-review of the 77 contradicting rows: Huandacareo's WHY opened
        # "The stored value is not wrong" under REFUTED: NO. Over the mass run's reviewer answers it
        # occurs 23 times under YES (consistent) and 4 under NO, each of the 4 a contradiction.
        "the stored value is not wrong",
        r"\bstored" + _SAME_CLAUSE + r" (?:is|was|are) not wrong\b",
    ),
    (
        "does not show the stored value wrong",
        r"\b(?:does|do|did) not show (?!(?:that )?the propos)[^.;:\u2014\u2013]{0,50}?\bwrong\b",
    ),
    (
        "nothing shows the stored value wrong",
        r"\bnothing (?:in the evidence |here )?shows (?:that )?(?:the stored|-?\d)"
        r"[^.;:\u2014\u2013]{0,40}?\bwrong\b",
    ),
    (
        "does not make the stored value wrong",
        r"\b(?:does|do) not make the (?:finer |more specific )?stored\b"
        r"[^.;:\u2014\u2013]{0,30}?\bwrong\b",
    ),
    (
        "does not establish that the stored value is wrong",
        r"\b(?:does|do) not (?:establish|support) (?:that )?the stored\b"
        r"[^.;:\u2014\u2013]{0,30}?\bwrong\b",
    ),
    (
        "the stored value is not contradicted",
        r"\bstored" + _SAME_CLAUSE + r" (?:is|was|are) not contradicted\b",
    ),
    (
        "does not contradict the stored value",
        r"\b(?:does|do) not contradict the (?:finer |more specific )?stored\b",
    ),
    (
        "the evidence supports the stored value",
        r"(?<!no )(?<!nothing in the )(?<!nor )\bevidence supports the stored "
        r"(?:value|[`\"'\u201c][^`\"'\u201d]+[`\"'\u201d])(?!'s? being| being| is wrong| was wrong)",
    ),
    (
        "the proposed value is contradicted",
        r"(?<!nor the )(?<!nor )(?<!if the )(?<!whether the )"
        + "".join(f"(?<!nor {owner} )" for owner in _NOR_OWNERS)
        + r"\bpropos(?:ed|al)"
        + _SAME_CLAUSE
        + r" (?:is|was|are) "
        r"contradicted\b(?! (?:by|in) (?:neither|nothing|none|no)\b)"
        r"(?! neither\b)"
        r"(?! only if\b)"
        r"(?![^.,;:!?\u2014\u2013]{0,40}\?)",
    ),
)
_FAILING_HALF_RE: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in FAILING_HALF_PHRASES
)

#: The phrases whose hold the mass lane's **written** rows showed misfiring: `phrase -> (false holds,
#: written rows it would hold)`. A false hold is a sentence that uses the phrase against its own
#: content and goes on to argue for the write ("Neither half holds - ... the stored `Settlement` is
#: contradicted and `Archaeological site` is supported", Presa-Tusiu). Read one by one on 2026-09-23
#: by the fixer's review, from `measure_review_holds.py`'s list of the 77 written rows the hold would
#: hold: 10 false holds, all under these four phrases; 7 more say both, 60 do name a failing half.
#: The hold stays - weakening a check is not the answer to a measured false-hold rate - but a row
#: held by one of these phrases is not a settled refusal: the writer marks it for the hand-read
#: (`write_stage.HAND_READ_NOTE`, `HUMAN_ONLY.md` B12). The other fourteen phrases held no written
#: row falsely (mixed: "the proposed value is contradicted" 4 of 12, "the stored value is not shown
#: wrong" 2 of 12, "the reason half fails" 1 of 3).
#: Every key is a `FAILING_HALF_PHRASES` name (`test_phase3_review.py` pins it; a check at import time
#: would keep the mutation sweep from deleting a phrase and watching its own test fail).
HAND_READ_PHRASES: dict[str, tuple[int, int]] = {
    "neither half holds": (4, 7),
    "the stored value is not contradicted": (4, 9),
    "the reason fails": (1, 4),
    "does not show the stored value wrong": (1, 10),
}


def failing_half(reason: str) -> str | None:
    """The first `FAILING_HALF_PHRASES` entry the `WHY:` sentence carries, or `None`.

    Read by the writer for a verdict that cleared the finding (`REFUTED: NO`): a name here means the
    reviewer's own sentence says a half of the finding fails, so the verdict line and the reason
    disagree and the row is not written. Only the reason is read - the sentence the frozen question
    asks for - and it is read as the parser stored it.
    """
    for name, pattern in _FAILING_HALF_RE:
        if pattern.search(reason):
            return name
    return None


@dataclass(frozen=True)
class ReviewAnswer:
    """One parsed review. `problems` is empty exactly when the answer is shaped as asked.

    A problem is **recorded, not raised**: the call was bought and paid for. What refuses is the
    writer - a refutation whose page was never fetched, or whose quote is not in that page, must not
    be allowed to unmake a finding any more than a fabricated correction may be written.
    """

    #: `True` refuted, `False` not refuted, `None` unresolved. `None` is also "unreadable", so the
    #: two are told apart by `problems`, never by the value alone.
    refuted: bool | None
    reason: str
    sources: tuple[DS.SourceClaim, ...]
    problems: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True when nothing about the answer's shape is wrong."""
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "refuted": self.refuted,
            "reason": self.reason,
            "sources": [{"url": s.url, "quote": s.quote} for s in self.sources],
            "problems": list(self.problems),
        }


def parse_review(text: str) -> ReviewAnswer:
    """Read one review. Every deviation lands in `problems`, naming what was missing."""
    problems: list[str] = []
    hits = [m.group("value") for m in REFUTED_RE.finditer(text)]
    refuted: bool | None = None
    if len(hits) != 1:
        problems.append(f"{len(hits)} `REFUTED:` line(s); one finding carries one verdict")
    elif hits[0].upper() not in REFUTED_VALUES:
        problems.append(f"`REFUTED: {hits[0]}` is not one of {REFUTED_SHAPE}")
    else:
        refuted = REFUTED_VALUES[hits[0].upper()]

    reason = ""
    for line in text.splitlines():
        if line.strip().upper().startswith(WHY_PREFIX):
            reason = line.split(":", 1)[1].strip()
            break
    if not reason:
        problems.append("no `WHY:` sentence naming the claim that failed, or that none did")

    sources = tuple(
        DS.SourceClaim(url=m.group("url"), quote=m.group("quote"))
        for m in DS.SOURCE_RE.finditer(text)
    )
    source_lines = sum(
        1 for line in text.splitlines() if line.strip().upper().startswith(DS.SOURCE_PREFIX)
    )
    if source_lines != len(sources):
        problems.append(
            f"{source_lines} `SOURCE:` line(s), {len(sources)} carrying both a url and a quoted "
            'sentence; each needs `SOURCE: <url> - "<sentence>"`'
        )
    if len(sources) > DS.MAX_SOURCES:
        problems.append(
            f"{len(sources)} sources; at most {DS.MAX_SOURCES} are kept and the rest are dropped"
        )
        sources = sources[: DS.MAX_SOURCES]

    # A `REFUTED: YES` needs no `SOURCE:`. Phase 3 asks stage 2 to refute "using its own research -
    # not by re-reading stage 1's evidence", and a reviewer with no fetch step of its own can only
    # refute from what it knows; demanding a page for every refutation would forbid exactly the
    # refuter the plan asks for, and would strand the strongest verdict in `UNRESOLVED` - the one
    # value that never lets a state change. Any `SOURCE:` it does give is still checked word for word
    # against the pages this run fetched, in `judge_review_batch`.
    if refuted is not True and sources:
        problems.append(
            "a `SOURCE:` page belongs to `REFUTED: YES`, not to a referee's own opinion"
        )
    return ReviewAnswer(refuted=refuted, reason=reason, sources=sources, problems=tuple(problems))


@dataclass(frozen=True)
class ReviewVerdict:
    """One finding's fate: what the reviewer said about it, or why nobody was asked.

    `unreviewable is None` **and** `refuted is False` **and** no `problems` is exactly the state in
    which a writer may act - `applies` names it, so the rule lives in one place instead of in every
    caller's `if`.
    """

    site_id: str
    field: str
    refuted: bool | None
    reason: str
    sources: tuple[DS.SourceClaim, ...] = ()
    problems: tuple[str, ...] = ()
    #: Why no question was asked (None when one was). An empty plan for a whole pass is a mistake,
    #: not a finding, so this is never empty-and-silent.
    unreviewable: str | None = None

    @property
    def asked(self) -> bool:
        """True when a call was bought for this finding."""
        return self.unreviewable is None

    @property
    def applies(self) -> bool:
        """True exactly when the writer may act on this field: asked, not refuted, nothing wrong."""
        return self.asked and self.refuted is False and not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "field": self.field,
            "asked": self.asked,
            "applies": self.applies,
            "refuted": self.refuted,
            "reason": self.reason,
            "sources": [{"url": s.url, "quote": s.quote} for s in self.sources],
            "problems": list(self.problems),
            "unreviewable": self.unreviewable,
        }


@dataclass
class ReviewPlan:
    """What one batch (or one site) buys: the calls, and the findings nobody was asked about."""

    calls: list[MS.PreparedCall] = field(default_factory=list)
    unreviewable: list[ReviewVerdict] = field(default_factory=list)

    def extend(self, other: ReviewPlan) -> None:
        self.calls.extend(other.calls)
        self.unreviewable.extend(other.unreviewable)


def finding_block(*, site: Mapping[str, Any], site_id: str, field: str, answer_text: str) -> str:
    """The finder's finding for one field: the stored value, then the finder's own words.

    The answer travels **verbatim**: the reviewer judges the finding that was made, including how it
    was phrased, and re-rendering it from parsed fields would substitute a different finding for the
    one on record. The stored-value block is the same one the finder saw (`site_field_block`), so
    both questions are asked about the same bytes.
    """
    return "\n".join(
        [
            DS.site_field_block(site, site_id, field),
            "",
            f'<finder-answer for="{field}">',
            answer_text.strip(),
            "</finder-answer>",
        ]
    )


def _field_rank(field: str) -> tuple[int, str]:
    """The plan's own field order, so a report reads in the order the plan was built in."""
    try:
        return (DS.DISCOVER_FIELDS.index(field), field)
    except ValueError:  # a field the plan does not know keeps a stable place at the end
        return (len(DS.DISCOVER_FIELDS), field)


def _prompt(
    *,
    site: Mapping[str, Any],
    site_id: str,
    field: str,
    answer_text: str,
    excerpts: Sequence[MS.EvidenceExcerpt],
) -> MS.Prompt:
    """One review's prompt: the finding, then the same evidence the finder had, all of it."""
    return MS.Prompt(
        stage=STAGE,
        system=MS.REVIEWER_QUESTION,
        user="\n".join(
            [
                finding_block(site=site, site_id=site_id, field=field, answer_text=answer_text),
                MS.evidence_block(list(excerpts)),
                MS.failed_target_block(list(excerpts)),
            ]
        ),
    )


def _unreviewable(site_id: str, field: str, reason: str) -> ReviewVerdict:
    return ReviewVerdict(
        site_id=site_id, field=field, refuted=None, reason=reason, unreviewable=reason
    )


def plan_site(
    *,
    batch_id: str,
    site: Mapping[str, Any],
    answers: F.EvidenceStore,
    store: F.EvidenceStore,
    allow_absent: bool = False,
    failures: Mapping[str, str] | None = None,
) -> ReviewPlan:
    """The calls one site's findings buy, and the findings that buy none.

    A field is reviewed only when the finder's answer exists, parses to `WRONG`, and carries no
    problem of its own. Everything else is a recorded `unreviewable` verdict with the finder's own
    reason, so a batch of findings that propose nothing is visibly that, instead of a silent zero.

    The evidence and its bound are the finder's own (`evidence_excerpts`, `check_evidence_bound`):
    the reviewer must not see more of a page than the finder did, or it would be answering a
    question the finder could not have answered. The one addition is the page behind a search hit a
    finding cites (`phase3/hit_stage.py`, 2026-09-23): the finder saw the hit's snippet, and a
    snippet is not a page - the pilot's finder quoted a snippet about another site. Such a page must
    have been fetched or recorded as failed before a finding that cites it is reviewed
    (`model_stage.cited_hit_pages` raises otherwise), and it is shown within the same bound.
    """
    site_id = str(site.get("site_id") or "")
    if not site_id:
        raise InputError(f"batch {batch_id}: a site record carries no site_id")
    plan = ReviewPlan()
    findings: list[tuple[str, str, DS.DiscoverAnswer]] = []
    unwritten = SE.unwritten_proposals(site)
    for name in DS.DISCOVER_FIELDS:
        path = answers.path_for(site_id, name)
        if not path.exists():
            plan.unreviewable.append(
                _unreviewable(
                    site_id,
                    name,
                    f"the finder bought no call for this field ({path.name} is not on disk), so "
                    "there is no finding to refute",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        answer = DS.parse_answer(text)
        if answer.verdict != REVIEWED_VERDICT:
            plan.unreviewable.append(
                _unreviewable(
                    site_id,
                    name,
                    f"the finder's verdict is {answer.verdict!r}, which proposes no change for a "
                    "reviewer to refute or confirm",
                )
            )
            continue
        if answer.problems:
            plan.unreviewable.append(
                _unreviewable(
                    site_id,
                    name,
                    "the finding is not usable as it stands, so there is nothing to refute: "
                    + "; ".join(answer.problems),
                )
            )
            continue
        repeat = unwritten.get(name)
        if repeat is not None and SE.same_value(str(answer.proposed), repeat.proposed):
            plan.unreviewable.append(
                _unreviewable(
                    site_id,
                    name,
                    f"the rerun proposes {answer.proposed!r} again, the proposal the mass lane did "
                    f"not write ({UNWRITTEN_DECISION[repeat.kind]}; {repeat.change_key}); a repeat "
                    "is recorded for Martin and never cleared by this lane",
                )
            )
            continue
        findings.append((name, text, answer))
    if not findings:
        return plan

    excerpts = MS.evidence_excerpts(
        site_id=site_id,
        site=site,
        store=store,
        hit_pages=True,
        allow_absent=allow_absent,
        failures=failures,
    )
    # Raises `EvidenceOverBound` rather than recording a skip: a site with finder answers cannot be
    # over the bound (the finder would not have been asked either), so this firing means the two
    # stages disagree about what the evidence is - and a disagreement is not a batch outcome.
    MS.check_evidence_bound(site_id, excerpts)
    for name, _, answer in findings:
        # Raises when a cited search hit's page was never fetched or recorded: the reviewer is not
        # asked about a hit nobody tried to verify.
        MS.cited_hit_pages(
            [claim.url for claim in answer.sources], excerpts, where=f"{site_id}/{name}"
        )
    for name, text, _ in findings:
        plan.calls.append(
            MS.PreparedCall(
                call=MS.ModelCall(
                    stage=STAGE,
                    batch_id=batch_id,
                    site_id=site_id,
                    field=name,
                    prompt=_prompt(
                        site=site,
                        site_id=site_id,
                        field=name,
                        answer_text=text,
                        excerpts=excerpts,
                    ).render(),
                ),
                excerpts=excerpts,
            )
        )
    return plan


def plan_batch(
    *,
    batch: Mapping[str, Any],
    answers: F.EvidenceStore,
    store: F.EvidenceStore,
    allow_absent: bool = False,
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> ReviewPlan:
    """Every call the batch buys, in batch order and then in field order."""
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    recorded = failures or {}
    plan = ReviewPlan()
    for site in sites:
        plan.extend(
            plan_site(
                batch_id=batch_id,
                site=site,
                answers=answers,
                store=store,
                allow_absent=allow_absent,
                failures=recorded.get(str(site.get("site_id") or "")),
            )
        )
    return plan


@dataclass
class ReviewReport:
    """The reviewer's own report, written as `review.json`.

    Deliberately not the finder's `model.json`: a batch directory is the finder's record, and a
    second stage writing over its numbers would destroy the evidence of what the finder cost and
    said. `resumed` counts the answers re-read from disk instead of re-bought.
    """

    batch_id: str
    stage: str
    calls: int
    resumed: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    verdicts: list[ReviewVerdict]

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "stage": self.stage,
            "calls": self.calls,
            "resumed": self.resumed,
            "cost_usd": round(self.cost_usd, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "applies": sum(1 for v in self.verdicts if v.applies),
            "refuted": sum(1 for v in self.verdicts if v.refuted is True),
            "unresolved": sum(1 for v in self.verdicts if v.asked and v.refuted is None),
            "unreviewable": sum(1 for v in self.verdicts if not v.asked),
            "with_problems": sum(1 for v in self.verdicts if v.problems),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True)


def write_report(path: Path, report: ReviewReport) -> None:
    """Write the report atomically: a reader sees the whole file or the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(report.to_json(), encoding="utf-8")
    tmp.replace(path)


def judge_review_batch(
    *,
    batch: Mapping[str, Any],
    runner: MS.ModelRunner,
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    reviews: F.EvidenceStore,
    ledger: L.Ledger,
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> ReviewReport:
    """Buy one review per usable finding, and record every finding nobody was asked about.

    An answer already in `reviews/` is re-read rather than re-bought, so a second pass over a batch
    costs nothing and cannot silently pay twice for the same question. The report says how many were
    `resumed`, because a zero-cost call and a skipped call must not look the same.

    Nothing is caught here: a call that fails propagates as `model_stage.ModelCallFailed`, exactly as
    in the finder, so a batch that cannot measure its calls stops loudly.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    plan = plan_batch(
        batch=batch,
        answers=answers,
        store=store,
        allow_absent=False,
        failures=failures,
    )
    verdicts: list[ReviewVerdict] = list(plan.unreviewable)
    pages_by_site: dict[str, dict[str, str]] = {}
    calls = 0
    resumed = 0
    cost = 0.0
    input_tokens = 0
    output_tokens = 0
    for item in plan.calls:
        site_id = item.call.site_id
        field_name = str(item.call.field or "")
        pages = pages_by_site.get(site_id)
        if pages is None:
            pages = DS.pages_from_excerpts(item.excerpts)
            pages_by_site[site_id] = pages
        path = reviews.path_for(site_id, field_name)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            resumed += 1
        else:
            judged = MS.judge_site(prepared=item, runner=runner, ledger=ledger, answers=reviews)
            text = judged.answer.text
            usage = judged.answer.usage
            calls += 1
            cost += usage.cost_usd
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
        answer = parse_review(text)
        problems = answer.problems + DS.claim_problems(answer.sources, pages)
        verdicts.append(
            ReviewVerdict(
                site_id=site_id,
                field=field_name,
                refuted=answer.refuted,
                reason=answer.reason,
                sources=answer.sources,
                problems=problems,
            )
        )
    return ReviewReport(
        batch_id=batch_id,
        stage=STAGE.value,
        calls=calls,
        resumed=resumed,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        # Sorted by the plan's field order rather than left in the order they happened to be
        # produced: the report must read the same whether or not a finding turned out reviewable.
        verdicts=sorted(verdicts, key=lambda v: (_field_rank(v.field), v.site_id)),
    )
