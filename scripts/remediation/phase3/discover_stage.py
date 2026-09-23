"""Stage "model" of the discover pass: one call per (site, field), one question per field.

Piece 5 of the Phase-3 runner. `phase3/snapshot_plan.py` builds the plan - one record per snapshot
site, whose findings are the site's own stored values - and this module buys the judgements. Brief
§8 settles §5's open decision: **one call per (site, field), and that field's own question**, not
one call per site asking about five values at once. The reasons are the two that already hold here:

* `model_stage`'s finder and reviewer each ask exactly one question per call, and the pilot's
  `PILOT.jsonl` is one record per (site, field) with `test_id = "P3/<field>"`. A five-field call
  would make one answer carry five verdicts, which is the shape the parser does not have and the
  shape a later piece would have to invent.
* The evidence is bought **once per site** either way: `fetch_stage.EvidenceStore` is keyed by
  `(site, feature)`, and the five fields of one site share two features (the article, and the
  Wikidata item when the record carries a qid). Five calls reuse those same files; the call count
  is the only line that multiplies.

What that costs, from the brief's own measured figures (§8): ~$0.000486 per call and ~437 tokens of
fixed per-call overhead. 17 sites x 5 fields = 85 calls (~$0.041); the whole snapshot, 5,004 sites x
5 = 25,020 calls (~$12.16) - `PIECE5.md` reports the dry run's call counts and prompt sizes next to
those numbers rather than instead of them.

The question has to be answerable for a field that stores **nothing**. Three of the 24 truth
entries have `stored_value: null`, and a question that only asked "is this value wrong?" would read
an empty field as nothing to report. So two things are structural here: `FIELD_QUESTION` says what
`WRONG` means for an empty field (`or the field stores no value where one belongs`), and
`site_field_block` marks the value `stored="absent"`. Across the snapshot this is not a corner:
7 `card_description` and 15 `period_start` values are empty (measured 2026-09-21, of 25,020 planned
(site, field) pairs), and none of the 17 truth sites has one - the 3 that a value question cannot
reach are `scope` entries, which are not a column at all (`snapshot_plan` reports that cap).

Two failure modes are bounded by **that site's own outcome**, never by the batch's life (brief §4):

* a site whose readable evidence is over `model_stage.MAX_EVIDENCE_CHARS` - `plan_site` records the
  whole site `unverifiable`, with the arithmetic, and the other sites are judged;
* a field whose evidence was never fetched - no call is bought, the reason is recorded, and the
  batch continues.

Evidence that is missing with **no** record of why still stops the batch: `plan_site` calls
`model_stage.evidence_excerpts`, which raises for exactly that case (piece 4's guard, unchanged).

`plan_batch` is also the dry run's own path, so the preview a caller reads and the live run cannot
disagree about which calls a batch buys - the only difference is that a preview marks a not-yet
fetched file `absent` instead of refusing it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Dual use: `python -m phase3.discover_stage` and `python scripts/remediation/phase3/run.py`. The
# package is not installed, so the parent directory must be importable first (same shim as
# `run.py`).
if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402  - the evidence store this stage reads
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402  - the seam this stage builds its calls through
from phase3 import search_evidence as SE  # noqa: E402  - a search plan's `rerun_fields`
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second
from phase3.snapshot_plan import DISCOVER_FIELDS  # noqa: E402  - the fields the plan was built for

#: The stage of a discover call, pinned rather than a parameter. The question below is the
#: **finder's** question ("is the stored value right?"), and the reviewer's is a different one
#: ("can this finder's finding be refuted?"), which needs a finder finding a discover batch does not
#: carry - `run._judge_discover` refuses `--stage reviewer` for that reason.
STAGE = M.Stage.FINDER

#: What an empty field looks like in the prompt. `stored="absent"` is the attribute the question
#: refers to; this is the value body, so `None` and `""` cannot be read as the string "null" or as
#: a value someone forgot to print.
ABSENT_VALUE_TEXT = "no value is stored in this field"

#: What a field's own contract says, so a question can tell a wrong value from a missing one without
#: the model having to guess the project's conventions. One clause per planned field; the key set is
#: asserted equal to `DISCOVER_FIELDS` by `tests/remediation/test_phase3_discover.py`.
FIELD_CLAUSE: dict[str, str] = {
    "description": (
        "`unified_sites.description` is the site's own prose and the card shows it. A description "
        "that describes something else - the deity, the region, the excavator - is wrong for this "
        "site; a site that stores none shows no text of its own."
    ),
    "period_start": (
        "`unified_sites.period_start` is an integer year, negative for BC, and the card buckets it "
        "for display. The buckets are the site's own `categorizePeriod`, and each one runs from its "
        "first year up to but **not including** its second: below -4500 is `< 4500 BC`; -4500 up to "
        "but not including -3000 is `4500 - 3000 BC`; -3000 up to but not including -1500 is "
        "`3000 - 1500 BC`; -1500 up to but not including -500 is `1500 - 500 BC`; -500 up to but "
        "not including 1 is `500 BC - 1 AD`; 1 up to but not including 500 is `1 - 500 AD`; 500 up "
        "to but not including 1000 is `500 - 1000 AD`; 1000 up to but not including 1500 is "
        "`1000 - 1500 AD`; 1500 and later is `1500+ AD`. So -1500 belongs to `1500 - 500 BC` and "
        "-500 belongs to `500 BC - 1 AD`, not to the bucket whose name begins with them. The "
        "evidence often names a century rather than a year, and the direction of BC years is easy to "
        "invert: the 2nd century BC is -200 up to but not including -101, and the 4th century BC is "
        "-400 up to but not including -301, so **both of those centuries fall in `500 BC - 1 AD` "
        "and neither is in `1500 - 500 BC`**. Most sites "
        "sit on a bucket lower bound. Work out **which span each of the two values falls in**, "
        "state both, and then compare: they are `WRONG` when the spans differ, and a round value "
        "alone is not an error."
    ),
    "site_type": (
        "`unified_sites.site_type` is the catalogue's own type and is drawn from a fixed list of "
        "{n} values: {vocabulary}. It has to survive the project's normaliser. The evidence will "
        "almost never use one of these words, so decide **which of the catalogue's values the "
        "evidence describes** - `Gate/archway/bridge` holds a triumphal arch, `Fortress/citadel` "
        "holds a hill fort, `Castle/palace` holds a folly castle. A stored value is `WRONG` only "
        "when the evidence describes something no catalogue value can hold, or when the stored "
        "value names a different kind of thing; never because the evidence's own wording differs "
        "from the bucket."
    ),
    "country": (
        "`unified_sites.country` is at most 100 characters and is read aloud on the card. "
        "`England`, `Scotland` and `Wales` in place of `United Kingdom` are deliberate project "
        "design, and a compound value like `Chile, Easter Island` is allowed. Under that design "
        "`England` and `United Kingdom` are **the same answer**, and so is `Türkiye` for `Turkey`: "
        "a `WRONG` verdict must never rest on that difference, however the evidence words it."
    ),
    "card_description": (
        "`card_stats.card_description` is the card's own text, at most 200 characters, and it is "
        "generated from the site's data rather than written by hand. A compound sentence the "
        "sources contradict in part is wrong in that part."
    ),
}

#: The question's fixed body: what a verdict means, and the three cases a value question tends to
#: lose - an empty field where a value belongs; evidence that is silent being read as agreement; and
#: a verdict contradicted by the finder's own sentence. `{field}` and `{clause}` are the only format
#: slots.
#:
#: The evidence statement is asked for **before** the verdict line on purpose. The first live run
#: (`runs/gold`, 2026-09-21) answered `VERDICT: CORRECT` after writing a sentence that placed the
#: site's real dating in a different bucket from the stored one - the prompt's own rule, stated and
#: then ignored, because the verdict was written first. Recall was 5 of 19 known-wrong fields.
#:
#: The second run (8 of 19) added the precedence sentence below. Its rewrite said `Only the
#: evidence in this message decides`, and the model then flagged `England` as `WRONG` because the
#: evidence wrote `United Kingdom` - citing the clause that allows exactly that and overriding it
#: in the same sentence ("under the allowed design England is acceptable, yet ... the stored value
#: differs"). An absolute-sounding rule demoted the per-field clause to a subordinate paragraph,
#: so the precedence is now stated rather than left to be inferred. The same run showed the other
#: half: without the catalogue's own value list, all four `site_type` flags were wrong, each by
#: reading the evidence's phrase as if it were the catalogue's bucket.
QUESTION_TEMPLATE = (
    "You are the finder in a two-stage factual audit. **No census check flagged this site**: "
    "nothing points at it and its stored values have never been questioned. This call is about one "
    "field - `{field}` - and about no other; the record below carries that field's stored value and "
    "the evidence fetched for the site.\n"
    "\n"
    "{clause}\n"
    "\n"
    "**The clause above defines what `matches` means for this field, and it beats the general rules "
    "below wherever the two disagree.**\n"
    "\n"
    "Answer in this order, and keep it short:\n"
    "\n"
    "1. One sentence saying what the evidence in this message gives for this field - the value it "
    "states, or the word `silent` if it states nothing about this field.\n"
    "2. Then the verdict line.\n"
    "\n"
    "VERDICT: CORRECT | WRONG | UNVERIFIABLE\n"
    "\n"
    "* `CORRECT` - the evidence **states** this field's value and it matches the stored value.\n"
    "* `WRONG` - the evidence states **a different value**; or the field stores no value where one "
    "belongs; or a claim the stored value itself makes is contradicted by the evidence. The sentence "
    "must say which of these it is, and a `WRONG` verdict **carries the value the field should hold "
    "and the page it comes from**, on two more lines:\n"
    "\n"
    "PROPOSED: <the value this field should hold, in the field's own shape>\n"
    'SOURCE: <a url that appears in the evidence below> - "<a sentence you copied word for word '
    'from that page>"\n'
    "\n"
    "* `UNVERIFIABLE` - the evidence states nothing about this field's value. **Silence is not "
    'agreement**: "I looked and the evidence says nothing about this" is `UNVERIFIABLE`, never '
    "`CORRECT`, and `PROPOSED`/`SOURCE` are not written for it. Never invent a value the evidence "
    "does not give.\n"
    "\n"
    "The `SOURCE` line is not decoration: it must name a page that is in the evidence below, and the "
    "quoted sentence must occur in that page, word for word in that order - your quotation marks "
    "and spacing are your own, the words are not. A correction whose page the run did not fetch, "
    "or whose sentence is not in it, is thrown away. Use up to three `SOURCE` lines when one claim "
    "rests on more than one page. Never write `PROPOSED` or `SOURCE` for `CORRECT` or "
    "`UNVERIFIABLE`.\n"
    "\n"
    "**Only the evidence in this message decides.** Your own knowledge of the subject is not "
    "evidence: it cannot uphold the stored value, and the sentence may not cite it.\n"
    "\n"
    "If your own sentence puts the site's real value anywhere other than the stored value - a "
    'different bucket, century, era, type or place - then the verdict is `WRONG`, and saying "this '
    'is consistent" in the same breath does not change it.\n'
    "\n"
    "A field whose `stored` attribute is `absent` holds nothing: no text, no number, not the string "
    '"null". If the evidence shows a value belongs in that field, that is `WRONG`; if the evidence '
    "gives no value for it either, that is `UNVERIFIABLE`.\n"
    "\n"
    "You propose; you do not write."
)


def _compose(field: str, vocabulary: Sequence[str]) -> str:
    """One field's question, with its clause filled in.

    A clause may carry `{n}`/`{vocabulary}` because it cannot be answered without the catalogue's own
    value list (see `FIELD_CLAUSE['site_type']`). An empty vocabulary is **refused** rather than
    quietly producing a question that asks which catalogue value the evidence describes while listing
    none: that failure would read as a thinner answer, not as an error.
    """
    clause = FIELD_CLAUSE[field]
    if "{vocabulary}" in clause:
        if not vocabulary:
            raise InputError(
                f"the {field!r} clause names the catalogue's own value list, and none was supplied; "
                "a question that asks which catalogue value the evidence describes, while listing "
                "no catalogue values, cannot be answered"
            )
        clause = clause.replace("{n}", str(len(vocabulary)))
        clause = clause.replace("{vocabulary}", ", ".join(f"`{value}`" for value in vocabulary))
    return QUESTION_TEMPLATE.format(field=field, clause=clause)


def field_question(field: str, vocabulary: Sequence[str] = ()) -> str:
    """The question for this field. A field the pass does not ask about raises.

    Built per call rather than at import, because one clause's text depends on the snapshot the plan
    was built from. `vocabulary` is only read for the clause that asks for it.
    """
    if field not in FIELD_CLAUSE:
        raise InputError(
            f"no discover question for field {field!r}; the plan is built for "
            f"{list(DISCOVER_FIELDS)} and each of them has one question"
        )
    return _compose(field, vocabulary)


def field_finding(site: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    """The plan's own finding for this field: its stored value, severity and test_id."""
    site_id = str(site.get("site_id") or "")
    rows = site.get("findings")
    if not isinstance(rows, list) or not rows:
        raise InputError(f"{site_id}: site record carries no findings")
    for row in rows:
        if row.get("field") == field:
            return row
    raise InputError(f"{site_id}: site record carries no finding for field {field!r}")


def site_field_block(site: Mapping[str, Any], site_id: str, field: str) -> str:
    """The site's own record for the one field this call judges, with its absence marked.

    `stored="absent"` is the fact the question's empty-field paragraph refers to: a value that is
    `None` or empty text is **not** the string "null" and not a value at all, and a prompt that left
    that to the reader's eye would let an empty field be answered as "nothing wrong here".
    """
    name = site.get("name")
    if not isinstance(name, str) or not name:
        raise InputError(f"{site_id}: site record carries no name")
    row = field_finding(site, field)
    value = row.get("current_value")
    absent = value is None or (isinstance(value, str) and not value.strip())
    body = ABSENT_VALUE_TEXT if absent else _render(value)
    return (
        f'<site id="{site_id}" name="{name}">\n'
        f'<field name="{field}" test_id="{row.get("test_id")}" '
        f'severity="{row.get("severity")}" stored="{"absent" if absent else "present"}">'
        f"{body}</field>\n"
        f"<note>{row.get('note', '')}</note>\n"
        "</site>"
    )


def _render(value: Any) -> str:
    """A stored value as text: strings as they stand, everything else as JSON (booleans included)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def unverifiable_field_finding(
    site: Mapping[str, Any], *, site_id: str, field: str, reason: str
) -> M.Finding:
    """One field's `Verdict.UNVERIFIABLE` finding: the answer this pass did not buy, and why.

    `defect` is derived from the verdict (`model.Finding.defect`), so this can never be read as "no
    defect found": it says the question was not answered, and `note` says why.
    """
    row = field_finding(site, field)
    return M.Finding(
        site_id=site_id,
        field=field,
        verdict=M.Verdict.UNVERIFIABLE,
        severity=M.Severity(str(row["severity"])),
        test_id=str(row["test_id"]),
        current_value=row.get("current_value"),
        note=reason,
    )


@dataclass
class DiscoverPlan:
    """What one batch (or one site) buys: the calls, and the calls it will not buy."""

    calls: list[MS.PreparedCall] = field(default_factory=list)
    #: Sites/fields that buy no call, each with its reason and the `unverifiable` findings it
    #: leaves. Recorded here rather than raised, because both cases are that record's own outcome.
    skipped: list[MS.SkippedSite] = field(default_factory=list)

    def extend(self, other: DiscoverPlan) -> None:
        self.calls.extend(other.calls)
        self.skipped.extend(other.skipped)


def plan_site(
    *,
    batch_id: str,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    vocabulary: Sequence[str],
    allow_absent: bool = False,
    failures: Mapping[str, str] | None = None,
) -> DiscoverPlan:
    """The calls one site buys: one per field, or its own unverifiable outcome if it is too big.

    The evidence is read **once** per site (`model_stage.evidence_excerpts`) and the bound is
    checked **once** (`model_stage.check_evidence_bound`), so all five prompts of a site quote the
    same bytes and the same arithmetic. An over-bound site is recorded as five skipped fields with
    that one reason - the site's own outcome - and the batch carries on.

    `vocabulary` is the catalogue's own `site_type` list, which one field's question cannot be built
    without; it is a required keyword so that no caller can ask that question unarmed.

    A site record of a search plan carries `rerun_fields` (`search_evidence.rerun_fields` validates
    them: a non-empty subset of `DISCOVER_FIELDS`), and only those fields buy a call - and only those
    are recorded unverifiable when the site's evidence, search hits included, is over the bound. The
    fields a search plan does not rerun were decided in the mass run and must not lose that decision
    to a bigger evidence set. A record without `rerun_fields` asks all five, as before.
    """
    site_id = str(site.get("site_id") or "")
    if not site_id:
        raise InputError(f"batch {batch_id}: a site record carries no site_id")
    rerun = SE.rerun_fields(site)
    fields = DISCOVER_FIELDS if rerun is None else rerun
    excerpts = MS.evidence_excerpts(
        site_id=site_id, site=site, store=store, allow_absent=allow_absent, failures=failures
    )
    try:
        MS.check_evidence_bound(site_id, excerpts)
    except MS.EvidenceOverBound as exc:
        skipped = [_over_bound_skip(site, field=name, exc=exc) for name in fields]
        return DiscoverPlan(skipped=skipped)

    calls = [
        MS.PreparedCall(
            call=MS.ModelCall(
                stage=STAGE,
                batch_id=batch_id,
                site_id=site_id,
                field=name,
                prompt=_prompt(site, site_id, name, excerpts, vocabulary).render(),
            ),
            excerpts=excerpts,
        )
        for name in fields
    ]
    return DiscoverPlan(calls=calls)


def _prompt(
    site: Mapping[str, Any],
    site_id: str,
    field: str,
    excerpts: Sequence[MS.EvidenceExcerpt],
    vocabulary: Sequence[str],
) -> MS.Prompt:
    """One field's prompt: the site's record for that field, then the evidence, all of it."""
    return MS.Prompt(
        stage=STAGE,
        system=field_question(field, vocabulary),
        user="\n".join(
            [
                site_field_block(site, site_id, field),
                MS.evidence_block(list(excerpts)),
                MS.failed_target_block(list(excerpts)),
            ]
        ),
    )


def _over_bound_skip(
    site: Mapping[str, Any], *, field: str, exc: MS.EvidenceOverBound
) -> MS.SkippedSite:
    reason = (
        f"{exc.site_id}: the evidence is {exc.total} characters, over the {exc.bound}-character "
        "bound, so no bounded prompt exists for any of this site's fields; the whole record is "
        "recorded unverifiable and the batch carries on"
    )
    return MS.SkippedSite(
        site_id=exc.site_id,
        field=field,
        reason=reason,
        findings=[
            unverifiable_field_finding(site, site_id=exc.site_id, field=field, reason=reason)
        ],
    )


def plan_batch(
    *,
    batch: Mapping[str, Any],
    store: F.EvidenceStore,
    vocabulary: Sequence[str],
    allow_absent: bool = False,
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> DiscoverPlan:
    """Every call the batch buys, in batch order and then in field order.

    `failures` is `model_stage.read_fetch_failures`'s whole result (keyed by site), not one site's
    slice. A site whose evidence is missing **with** a recorded failure is still planned: the prompt
    carries that failure, and `judge_discover_batch` records the field as not attempted only when
    nothing at all was readable.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    recorded = failures or {}
    plan = DiscoverPlan()
    for site in sites:
        plan.extend(
            plan_site(
                batch_id=batch_id,
                site=site,
                store=store,
                vocabulary=vocabulary,
                allow_absent=allow_absent,
                failures=recorded.get(str(site.get("site_id") or "")),
            )
        )
    return plan


def judge_discover_batch(
    *,
    batch: Mapping[str, Any],
    runner: MS.ModelRunner,
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    ledger: L.Ledger,
    vocabulary: Sequence[str],
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> MS.BatchModelReport:
    """Buy one call per (site, field) that has evidence, and record every call not bought.

    Three ways a call is not bought, all recorded with their own reason and all leaving the batch
    alive: the site's evidence is over the bound (`plan_batch`, before anything is spent), no call
    for that field was planned, or no evidence for the site was readable at all - a site whose
    targets were asked and failed, which is not the same fact as a site nobody asked about.

    A fourth way the batch survives: a call that **was** bought and came back as an unreadable
    stream. It is recorded as a `MS.FailedCall` beside the judgements - `site_id`, `field`, reason,
    and no verdict - and the remaining calls are still bought. Before 2026-09-21 that one call threw
    out of this loop and ended the batch, answers already on disk included (`output/remediation/logs/
    mass/batch-0143.judge.log`, where 4 of 334 batches died this way).

    Nothing else is caught: a missing evidence file **with no recorded failure** still propagates
    out of `plan_batch` (`model_stage.evidence_excerpts`), so a batch that cannot account for its
    evidence fails loudly instead of judging a page nobody has a record of.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    plan = plan_batch(batch=batch, store=store, vocabulary=vocabulary, failures=failures)
    by_id = {
        str(site.get("site_id") or ""): site
        for site in (batch.get("sites") or [])
        if isinstance(site, dict)
    }
    judgements: list[MS.SiteJudgement] = []
    skipped: list[MS.SkippedSite] = list(plan.skipped)
    named_failures: list[MS.FailedCall] = []
    for item in plan.calls:
        site_id = item.call.site_id
        field_name = str(item.call.field or "")
        if not any(e.present for e in item.excerpts):
            reason = MS.no_evidence_reason(item)
            skipped.append(
                MS.SkippedSite(
                    site_id=site_id,
                    field=field_name,
                    reason=reason,
                    findings=[
                        unverifiable_field_finding(
                            by_id[site_id], site_id=site_id, field=field_name, reason=reason
                        )
                    ],
                )
            )
            continue
        try:
            judged = MS.judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)
        except MS.UnreadableStream as exc:
            named_failures.append(
                MS.FailedCall(site_id=site_id, field=field_name or None, reason=str(exc))
            )
            continue
        usage = judged.answer.usage
        judgements.append(
            MS.SiteJudgement(
                site_id=site_id,
                label=item.call.label,
                answer_chars=len(judged.answer.text),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=usage.cost_usd,
                wrote=judged.wrote,
                field=field_name or None,
            )
        )
    return MS.BatchModelReport(
        batch_id=batch_id,
        stage=STAGE,
        site_ids=[str(site.get("site_id") or "") for site in (batch.get("sites") or [])],
        judgements=judgements,
        skipped=skipped,
        failures=named_failures,
    )


#: The answer's shape, parsed. The verdict expression is the recall scorer's own rule, stated once
#: here so the two cannot drift: five round-3 answers write the verdict inline
#: (`2. VERDICT: UNVERIFIABLE`), and a rule anchored to the start of a line under-counted them.
VERDICT_RE = re.compile(r"VERDICT:\s*(CORRECT|WRONG|UNVERIFIABLE)")
PROPOSED_RE = re.compile(r"^\s*PROPOSED:\s*(?P<value>\S.*?)\s*$", re.MULTILINE)
SOURCE_RE = re.compile(
    r"^\s*SOURCE:\s*(?P<url>https?://\S+)\s*[-\u2013\u2014]?\s*[\"\u201c](?P<quote>.+?)[\"\u201d]\s*$",
    re.MULTILINE,
)

#: A `SOURCE:` line that does not match `SOURCE_RE` (no URL, no quoted sentence) is a problem too,
#: so its presence is counted by its prefix rather than inferred from the number of matches.
SOURCE_PREFIX = "SOURCE:"
EVIDENCE_PREFIX = "EVIDENCE:"

#: The line prefixes that mark the answer's structure. `QUESTION_TEMPLATE` asks for the reason
#: sentence before the verdict line and marks it with nothing, so the parser reads the first line that
#: is neither empty nor one of these. 3 of the 1777 answers of the first mass-run batches spelled it
#: `EVIDENCE:` anyway; that spelling is read as the same sentence rather than thrown away.
MARKER_PREFIXES = (EVIDENCE_PREFIX, SOURCE_PREFIX, "VERDICT:", "PROPOSED:")

#: How many pages one correction may cite. More are a problem rather than a bonus: the writer stores
#: them in the journal's `evidence`, and a human reads that.
MAX_SOURCES = 3


@dataclass(frozen=True)
class SourceClaim:
    """One page the answer cites, and the sentence it says is on that page."""

    url: str
    quote: str


@dataclass(frozen=True)
class DiscoverAnswer:
    """One parsed answer. `problems` is empty exactly when the answer is shaped as asked.

    A problem is **recorded, not raised**: the call was bought and paid for, and the batch's job is
    to report what came back. What refuses is the *write* (piece 6) - a `WRONG` verdict with no
    proposed value, or with a source that cannot be found in the page the run fetched, must not
    reach the database.
    """

    evidence: str
    verdict: str | None
    proposed: str | None
    sources: tuple[SourceClaim, ...]
    problems: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True when nothing about the answer's shape is wrong."""
        return not self.problems


def parse_answer(text: str) -> DiscoverAnswer:
    """Read one answer. Every deviation lands in `problems`, naming what was missing.

    The reason is the first line that is neither empty nor a marker line. That is what the question
    asks for - one sentence about what the evidence gives, before the verdict line - and it asks for
    no marker in front of it. Demanding one made the reviewer find nothing to review in the round-6
    gold run, whose 75 answers all carry the sentence unmarked.
    """
    problems: list[str] = []
    verdict_match = VERDICT_RE.search(text)
    verdict = verdict_match.group(1) if verdict_match else None
    if verdict is None:
        problems.append("no `VERDICT:` line naming CORRECT, WRONG or UNVERIFIABLE")

    evidence = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith(EVIDENCE_PREFIX):
            evidence = stripped.split(":", 1)[1].strip()
            break
        if not stripped.upper().startswith(MARKER_PREFIXES):
            evidence = stripped
            break
    if not evidence:
        problems.append("no sentence saying what the evidence gives")

    proposed_hits = [m.group("value") for m in PROPOSED_RE.finditer(text)]
    if len(proposed_hits) > 1:
        problems.append(f"{len(proposed_hits)} `PROPOSED:` lines; one field carries one value")
    proposed = proposed_hits[0] if proposed_hits else None

    sources = tuple(
        SourceClaim(url=m.group("url"), quote=m.group("quote")) for m in SOURCE_RE.finditer(text)
    )
    source_lines = sum(
        1 for line in text.splitlines() if line.strip().upper().startswith(SOURCE_PREFIX)
    )
    if source_lines != len(sources):
        problems.append(
            f"{source_lines} `SOURCE:` line(s), {len(sources)} carrying both a url and a quoted "
            'sentence; each needs `SOURCE: <url> - "<sentence>"`'
        )
    if len(sources) > MAX_SOURCES:
        problems.append(
            f"{len(sources)} sources; at most {MAX_SOURCES} are kept and the rest are dropped"
        )
        sources = sources[:MAX_SOURCES]

    if verdict == "WRONG":
        if proposed is None:
            problems.append("a `WRONG` verdict with no `PROPOSED:` value")
        if not sources:
            problems.append("a `WRONG` verdict with no `SOURCE:` page to answer for it")
    elif verdict is not None and (proposed is not None or sources):
        problems.append(
            f"a `{verdict}` verdict carrying a correction (`PROPOSED`/`SOURCE` belong to `WRONG`)"
        )
    return DiscoverAnswer(
        evidence=evidence,
        verdict=verdict,
        proposed=proposed,
        sources=sources,
        problems=tuple(problems),
    )


#: What a retyped quotation legitimately changes: whitespace runs, quote marks, dash characters and
#: non-breaking spaces. Case is folded too, because a sentence lifted from mid-paragraph is
#: legitimately recased. What is **not** folded: the words, their order, punctuation and digits.
_QUOTE_FOLD = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


#: The JSON escapes that occur in an evidence file (`\uXXXX`, `\n`, `\"`, `\/`). Undone on both
#: sides of the comparison - `normalise_quote` says why.
_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[ntr\"'/\\bf])")
_ESCAPE_CHARS = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "'": "'",
    "/": "/",
    "\\": "\\",
    "b": "\b",
    "f": "\f",
}


def _unescape_match(match: re.Match[str]) -> str:
    body = match.group(1)
    if body[0] in "uU":
        return chr(int(body[1:], 16))
    return _ESCAPE_CHARS[body]


def normalise_quote(text: str) -> str:
    """The form in which a quote and a page are compared.

    JSON escapes are undone first. The evidence files for `enwiki` and `wikidata_entity` are the
    APIs' **JSON responses**, and `model_stage.evidence_block` puts that text into the prompt
    verbatim - so the page spells a line break `\\n` and `Ávila` `\\u00c1vila` exactly where the model
    reads a break and an `Á`. Comparing raw bytes would report every honest quote as missing, and the
    metric would then be about JSON escaping instead of about citations.

    What is still required: the words, their order, punctuation and digits. What is folded: case,
    whitespace runs, the quote and dash characters a retyping may change, and those escapes.
    """
    unescaped = _ESCAPE_RE.sub(_unescape_match, text)
    return " ".join(unescaped.translate(_QUOTE_FOLD).split()).casefold()


def quote_occurs(quote: str, page: str) -> bool:
    """True when the page carries the sentence, up to the differences a retyping may have."""
    needle = normalise_quote(quote)
    return bool(needle) and needle in normalise_quote(page)


def pages_from_excerpts(excerpts: Iterable[MS.EvidenceExcerpt]) -> dict[str, str]:
    """The pages behind one call's evidence: url -> the text we stored, for the pages we have."""
    return {e.url: e.text for e in excerpts if e.text is not None}


def claim_problems(sources: Iterable[SourceClaim], pages: Mapping[str, str]) -> tuple[str, ...]:
    """What is wrong with a set of cited pages, judged against the pages the run fetched.

    This is the line that makes "with sources" a property rather than a claim: a page the run did
    not fetch cannot be checked, and a quoted sentence that does not occur in the page we stored is
    a fabricated citation. Either one is recorded here, and the finding that carries it is not
    written.

    Split out of `source_problems` on 2026-09-21 so the **reviewer's** refutations go through the
    same code as the finder's corrections: an invented citation is the same defect in both roles,
    and two spellings of this check would be two chances to drift.
    """
    problems: list[str] = []
    for claim in sources:
        page = pages.get(claim.url)
        if page is None:
            problems.append(f"cited page was not fetched by this run: {claim.url}")
            continue
        if not quote_occurs(claim.quote, page):
            problems.append(f"quote does not occur in {claim.url}: {claim.quote!r}")
    return tuple(problems)


def source_problems(answer: DiscoverAnswer, pages: Mapping[str, str]) -> tuple[str, ...]:
    """`claim_problems` for a finder's answer."""
    return claim_problems(answer.sources, pages)
