"""The evidence-based quality gate, shared by the judge and auto-publish.

The judge computes `quality_score.passed` once, at write time, from the audit
it had then. Auto-publish deliberately RE-computes citation integrity against
the artifact of record ("the stored audit can be stale") — but until
2026-08-31 it still trusted that stored `passed`, which has the old audit
verdict baked into it. So a paper whose audit was repaired stayed held
forever on a flag nobody could refresh: five papers sat that way after the
citation-gate fixes made their audits pass.

One function, two callers, so the rule cannot drift between them.
"""

from __future__ import annotations


def citation_coverage_score(audit_result: dict) -> int:
    """M1 (0-15): each uncited paragraph costs 3 points."""
    return max(0, 15 - audit_result.get("uncited_paragraphs", 0) * 3)


def reference_integrity_score(audit_result: dict) -> int:
    """M2 (0-10): each invalid marker or orphaned reference costs 2 points."""
    invalid = len(audit_result.get("invalid_markers", []))
    orphaned = len(audit_result.get("orphaned_refs", []))
    return max(0, 10 - (invalid + orphaned) * 2)


def quality_gate_passed(
    *,
    audit_passed: bool,
    citation_coverage: int,
    reference_integrity: int,
    placeholder_markers: int,
    language_bleed: int,
    hallucination_final: int,
    high_contradictions: int,
    undefined_title_terms: int,
) -> bool:
    """True when the paper's citation integrity is clean enough to publish.

    Counts, not lists, so the caller may pass either a fresh audit result or
    the stored `audit_gate_failures` summary.
    """
    return bool(
        audit_passed
        and citation_coverage >= 9
        and reference_integrity == 10
        and not placeholder_markers
        and not language_bleed
        and hallucination_final == 0
        and high_contradictions == 0
        and not undefined_title_terms
    )


def recompute_quality_passed(quality_score: dict, audit_result: dict) -> bool:
    """Re-run the gate for a stored paper against a freshly computed audit.

    `quality_score` is the stored dict (audit_gate_failures); `audit_result`
    is what `validate_or_repair` just returned. Everything the audit can speak
    to is taken from the fresh result — including citation coverage and
    reference integrity, which are pure functions of the audit: until
    2026-09-24 they were read from the stored metrics, so a paper whose
    marker was repaired stayed held on the write-time score. The rest —
    hallucination and contradiction counts, which are LLM measurements that
    cannot be redone without re-running the pipeline — comes from the stored
    summary. No stored summary means no judge verdict to vouch for them.
    """
    stored = quality_score.get("audit_gate_failures")
    if not stored:
        return False
    return quality_gate_passed(
        audit_passed=bool(audit_result.get("passed")),
        citation_coverage=citation_coverage_score(audit_result),
        reference_integrity=reference_integrity_score(audit_result),
        placeholder_markers=len(audit_result.get("placeholder_markers") or []),
        language_bleed=len(audit_result.get("language_bleed") or []),
        hallucination_final=int(stored.get("hallucination_final", 0)),
        high_contradictions=int(stored.get("high_contradictions", 0)),
        undefined_title_terms=int(stored.get("undefined_title_terms", 0)),
    )
