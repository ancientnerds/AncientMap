"""Data model of the curated-sites census.

One `Finding` is one *claim about one field of one site*, with its evidence. It is the
only currency the audit moves in: Phase 3 (the expensive LLM stage) consumes findings,
the change journal records what happened to them, and the quality gate counts them.

Design rules taken from docs/procedures/SITES_DB_REMEDIATION_2026-09.md and
docs/procedures/ENRICHMENT_AUDIT.md:

* A finding without evidence is not a finding (anti-pattern 6: never trust a single
  source blindly). `evidence` is therefore a list and `CONFIDENCE_TWO_SOURCE` requires
  at least two entries from distinct hosts.
* An empty field beats a wrong one, so every finding names what it would *set*, and
  "clear the field" is an explicit, allowed proposal (`Proposal.CLEAR`).
* A finding never writes. It is a proposal; application goes through the journal.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal


class Severity(StrEnum):
    """How loud the error is, not how likely it is.

    severe   - would be read aloud wrong, or moves the pin/scope/title. Fix before anything ships.
    moderate - visibly wrong on an indexed page (name, country, type, period bucket).
    cosmetic - real but invisible to a visitor (URL shape, missing thumbnail, ordering).
    """

    SEVERE = "severe"
    MODERATE = "moderate"
    COSMETIC = "cosmetic"


class Confidence(StrEnum):
    """Evidence strength. Only the first two may ever be applied automatically."""

    #: Two independent sources agree with the proposal.
    TWO_SOURCE = "two_source"
    #: One authoritative source (Wikidata P625, the site's own official page, an ISO table).
    AUTHORITATIVE = "authoritative"
    #: Consistent but single-sourced, or derived from an unreliable generator.
    WEAK = "weak"
    #: Something is wrong, but no reliable replacement exists. Never applied.
    UNVERIFIABLE = "unverifiable"


class Proposal(StrEnum):
    SET = "set"      #: write the value in `proposed_value`
    CLEAR = "clear"  #: set the field to NULL - "an empty field beats a wrong one"
    REVIEW = "review"  #: a human or Phase 3 must decide; carries no value
    NONE = "none"    #: recorded for the record, nothing to change


@dataclass(frozen=True)
class Evidence:
    """One source that bears on one claim. `quote` is what makes it reviewable later."""

    source: str          #: short label, e.g. "wikidata:P625", "commons:imageinfo"
    url: str | None = None
    quote: str | None = None
    retrieved_at: str | None = None

    @property
    def host(self) -> str:
        if not self.url:
            return self.source
        h = self.url.split("//", 1)[-1].split("/", 1)[0].lower()
        return h[4:] if h.startswith("www.") else h


@dataclass
class Finding:
    """One proposed change to one field of one site."""

    site_id: str
    test_id: str                                    #: e.g. "T04/site_type-synonym"
    field: str                                      #: unified_sites column, or "wiki_images:<id>"
    severity: Severity
    dimension: str                                  #: D1..D8, IMG, SCOPE, SHORTS
    current_value: Any = None
    proposed_value: Any = None
    proposal: Proposal = Proposal.REVIEW
    confidence: Confidence = Confidence.UNVERIFIABLE
    evidence: list[Evidence] = dataclasses.field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        # Fail loudly at construction rather than writing an unevidenced claim to disk.
        if self.proposal is Proposal.SET and self.proposed_value is None:
            raise ValueError(f"{self.test_id}: Proposal.SET needs a proposed_value")
        if self.proposal is Proposal.REVIEW and self.proposed_value is not None:
            raise ValueError(f"{self.test_id}: Proposal.REVIEW must not carry a value")

    @property
    def independent_sources(self) -> int:
        """Distinct hosts (or, absent URLs, distinct source labels) backing this claim."""
        return len({e.host for e in self.evidence})

    @property
    def applicable(self) -> bool:
        """May this finding be written to the database without a further human/agent step?"""
        return (
            self.proposal in (Proposal.SET, Proposal.CLEAR)
            and self.confidence in (Confidence.TWO_SOURCE, Confidence.AUTHORITATIVE)
            and len(self.evidence) > 0
        )

    def to_json(self) -> str:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["proposal"] = self.proposal.value
        d["confidence"] = self.confidence.value
        d["evidence"] = [asdict(e) for e in self.evidence]
        d["independent_sources"] = self.independent_sources
        d["applicable"] = self.applicable
        return json.dumps(d, ensure_ascii=False, sort_keys=True, default=_default)

    @property
    def change_key(self) -> str:
        """Stable identity of the exact transition, for the conditional WHERE clause.

        Two findings with the same change key propose the same transition and may be
        deduplicated; two with different keys must both survive.
        """
        blob = json.dumps(
            [self.site_id, self.field, _default(self.current_value), _default(self.proposed_value),
             self.proposal.value],
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


@dataclass
class TestResult:
    """Per-site outcome of one test - the row that satisfies the Phase 1 acceptance criterion."""

    site_id: str
    test_id: str
    status: Literal["pass", "flagged", "not_applicable", "error"]
    detail: str = ""
    checked: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def all_findings(results: Iterable[TestResult | Finding]) -> list[Finding]:
    return [r for r in results if isinstance(r, Finding)]
