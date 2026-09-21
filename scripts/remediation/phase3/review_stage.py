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
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: The stage of a review call, pinned rather than a parameter: the question below is the reviewer's,
#: and a caller that could pass `finder` here would be asking the finder's question of a finding.
STAGE = M.Stage.REVIEWER

#: The only finder verdict that proposes a change, and so the only one a reviewer is asked about.
REVIEWED_VERDICT = "WRONG"

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
    question the finder could not have answered.
    """
    site_id = str(site.get("site_id") or "")
    if not site_id:
        raise InputError(f"batch {batch_id}: a site record carries no site_id")
    plan = ReviewPlan()
    findings: list[tuple[str, str]] = []
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
        findings.append((name, text))
    if not findings:
        return plan

    excerpts = MS.evidence_excerpts(
        site_id=site_id, site=site, store=store, allow_absent=allow_absent, failures=failures
    )
    # Raises `EvidenceOverBound` rather than recording a skip: a site with finder answers cannot be
    # over the bound (the finder would not have been asked either), so this firing means the two
    # stages disagree about what the evidence is - and a disagreement is not a batch outcome.
    MS.check_evidence_bound(site_id, excerpts)
    for name, text in findings:
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
