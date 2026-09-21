"""The Phase-3 finding schema: three verdict kinds, and the rules on what may be proposed.

One `Finding` is one *judgement about one field of one site*: the stored value is wrong
(`Verdict.DEFECT`), it looks odd but is right (`Verdict.TRUE_BUT_NO_CORRECTION`), or the
evidence cannot settle it (`Verdict.UNVERIFIABLE`). The third kind is new to this package:
the census vocabulary has `proposal` but no way to say "known defect, no replacement
exists", and `output/remediation/AUDIT_LOG.md` records that gap as a producer gap that the
Phase-3 runner must close (brief decisions 2 and 11).

The enums `Severity`, `Confidence`, `Proposal` and the `Evidence` record are the census's
(`scripts/remediation/census/model.py`), imported rather than re-declared: the finder brief
says "same schema as the census", and a second spelling of the same vocabulary would let
the two drift apart.

Two rules are enforced here because they decide whether a proposal is a correction at all:

1. **Text fields are report-only in Phase 3** (brief decision 5), and the two reasons differ.
   `card_description` is re-derived on every API boot from the JSON file
   (`api/main.py:506` -> `api/services/card_descriptions.py:35-48`, upserting into
   `card_stats`), so a DB-only `set` is reverted. `unified_sites.description` has **no** boot
   overwriter; it is report-only because text regeneration belongs to Phase 5, not to a SQL
   update. Both are refused here, so the refusal cannot depend on which brief a stage read.
2. **A `site_type` write must be a fixed point of its own boot producer**
   (`pipeline/lyra/orchestrator.py:1476-1488`): a value that `normalize_site_type()` would
   rewrite is not a correction but a temporary edit. The check imports the producer itself,
   so there is no second spelling of the normalisation.

What this layer does **not** check, stated so it is not mistaken for covered:
`unified_sites.name_normalized`'s fixed point needs Postgres `unaccent`
(`left(lower(unaccent(value)), 500)`, `FIELD_CONTRACT.md` §2.2) and is therefore unverified
here, and `unified_sites.country` is not re-derived by `run_data_patches` for
`source_id='ancient_nerds'` rows — `pipeline/lyra/data_patches.py:54-64` guards that UPDATE
with `source_id = 'lyra' AND country IS NULL`.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from census.model import Confidence, Evidence, Proposal, Severity

#: Fields that may only be *reported*, never `set` (brief decision 5). The two reasons are in
#: the module docstring: a boot overwriter for `card_description`, the phase split for
#: `description`.
REPORT_ONLY_FIELDS = frozenset({"description", "card_description"})


class Verdict(StrEnum):
    """What the evidence says about the stored value."""

    #: The stored value is wrong.
    DEFECT = "defect"
    #: The stored value looks odd (or a census lead flagged it) but is right, so no write.
    TRUE_BUT_NO_CORRECTION = "true_but_no_correction"
    #: The evidence cannot settle it: neither a correction nor a clean bill of health.
    UNVERIFIABLE = "unverifiable"


class Stage(StrEnum):
    """The two stages. A reviewer never sees the finder's context (brief decision 10)."""

    FINDER = "finder"
    REVIEWER = "reviewer"


class StageStatus(StrEnum):
    """How a stage ended. `ERROR` is a recorded outcome, never turned into "clean"."""

    COMPLETE = "complete"
    ERROR = "error"


#: Verdicts that must not carry a proposed write.
_NO_WRITE_VERDICTS = (Verdict.TRUE_BUT_NO_CORRECTION, Verdict.UNVERIFIABLE)


def _coerce(enum_cls: type[StrEnum], value: Any, what: str) -> Any:
    """Turn a raw JSON value into its enum member, refusing anything not in the vocabulary."""
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValueError(f"{what}: {value!r} is not one of {[m.value for m in enum_cls]}") from exc


def site_type_fixed_point(value: str) -> bool:
    """Would `value` survive the boot normalizer?

    Uses the boot producer itself (`pipeline.normalizers.site_type.normalize_site_type`,
    called from `pipeline/lyra/orchestrator.py:1476-1488` on every start).
    """
    from pipeline.normalizers.site_type import normalize_site_type

    return normalize_site_type(value) == value


@dataclass
class Finding:
    """One judgement about one field of one site, with the evidence that carries it."""

    site_id: str
    field: str  #: the column the judgement is about, e.g. "period_start", "lat/lon"
    verdict: Verdict
    severity: Severity
    test_id: str  #: e.g. "P3/period", "T03/all-outside" for a census lead
    dimension: str = "phase3"
    current_value: Any = None
    proposed_value: Any = None
    proposal: Proposal = Proposal.REVIEW
    confidence: Confidence = Confidence.UNVERIFIABLE
    evidence: list[Evidence] = dataclasses.field(default_factory=list)
    census_cross_reference: str | None = None  #: the census finding's own `(test_id, field)`
    note: str = ""

    def __post_init__(self) -> None:
        self.verdict = _coerce(Verdict, self.verdict, "verdict")
        self.severity = _coerce(Severity, self.severity, "severity")
        self.proposal = _coerce(Proposal, self.proposal, "proposal")
        self.confidence = _coerce(Confidence, self.confidence, "confidence")

        if not self.site_id:
            raise ValueError(f"{self.test_id}: a finding needs a site_id")
        if not self.field:
            raise ValueError(f"{self.test_id}: a finding needs a field")
        if self.verdict is Verdict.DEFECT and self.proposal is Proposal.NONE:
            raise ValueError(f"{self.test_id}: Verdict.DEFECT cannot carry proposal=none")

        if self.verdict in _NO_WRITE_VERDICTS:
            if self.proposal not in (Proposal.REVIEW, Proposal.NONE):
                raise ValueError(
                    f"{self.test_id}: verdict={self.verdict} is 'no write', "
                    f"but proposal={self.proposal}"
                )
            if self.proposed_value is not None:
                raise ValueError(
                    f"{self.test_id}: verdict={self.verdict} must not carry a proposed_value"
                )

        # The census rule, kept: `set` names a value, `review` names none.
        if self.proposal is Proposal.SET and self.proposed_value is None:
            raise ValueError(f"{self.test_id}: Proposal.SET needs a proposed_value")
        if self.proposal in (Proposal.REVIEW, Proposal.NONE) and self.proposed_value is not None:
            raise ValueError(f"{self.test_id}: Proposal.{self.proposal} must not carry a value")

        if self.proposal in (Proposal.SET, Proposal.CLEAR):
            if self.field in REPORT_ONLY_FIELDS:
                raise ValueError(
                    f"{self.test_id}: {self.field} is report-only in Phase 3 "
                    "(boot overwriter for card_description, phase split for description)"
                )
            if not self.evidence:
                raise ValueError(f"{self.test_id}: a proposed write needs evidence")
            if self.confidence is Confidence.UNVERIFIABLE:
                raise ValueError(
                    f"{self.test_id}: confidence=unverifiable cannot carry a "
                    f"proposal={self.proposal}"
                )

        if (
            self.field == "site_type"
            and self.proposal in (Proposal.SET, Proposal.CLEAR)
            and isinstance(self.proposed_value, str)
            and not site_type_fixed_point(self.proposed_value)
        ):
            raise ValueError(
                f"{self.test_id}: {self.proposed_value!r} is not a site_type fixed point - "
                "the boot normalizer would rewrite it"
            )

    @property
    def defect(self) -> bool:
        """The required boolean both briefs ask for (decision 2), derived from the verdict.

        Derived rather than stored: the flag and the verdict cannot then disagree, and
        `defect: false` with `proposal: review` cannot be used to hide a known defect.
        """
        return self.verdict is Verdict.DEFECT

    @property
    def independent_sources(self) -> int:
        """Distinct hosts (or, absent URLs, distinct source labels) backing this judgement."""
        return len({e.host for e in self.evidence})

    def to_json(self) -> str:
        payload = asdict(self)
        payload["verdict"] = self.verdict.value
        payload["severity"] = self.severity.value
        payload["proposal"] = self.proposal.value
        payload["confidence"] = self.confidence.value
        payload["evidence"] = [asdict(e) for e in self.evidence]
        payload["defect"] = self.defect
        payload["independent_sources"] = self.independent_sources
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass
class StageResult:
    """What one stage did with one batch. A crash is a result, not a missing row."""

    stage: Stage
    batch_id: str
    site_ids: list[str]
    findings: list[Finding] = dataclasses.field(default_factory=list)
    status: StageStatus = StageStatus.COMPLETE
    error: str | None = None
    started_at: str | None = None
    ended_at: str | None = None

    def __post_init__(self) -> None:
        self.stage = _coerce(Stage, self.stage, "stage")
        self.status = _coerce(StageStatus, self.status, "status")
        if not self.batch_id:
            raise ValueError("a stage result needs a batch_id")
        if not self.site_ids:
            raise ValueError(f"{self.batch_id}: a stage result needs the sites it covered")
        if len(set(self.site_ids)) != len(self.site_ids):
            raise ValueError(f"{self.batch_id}: duplicate site_id in the batch")
        foreign = sorted({f.site_id for f in self.findings} - set(self.site_ids))
        if foreign:
            raise ValueError(f"{self.batch_id}: findings for sites not in this batch: {foreign}")
        if self.status is StageStatus.ERROR and not self.error:
            raise ValueError(f"{self.batch_id}: status=error needs the error that happened")
        if self.status is StageStatus.COMPLETE and self.error is not None:
            raise ValueError(f"{self.batch_id}: status=complete cannot carry an error")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["status"] = self.status.value
        payload["findings"] = [json.loads(f.to_json()) for f in self.findings]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
