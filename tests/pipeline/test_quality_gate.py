"""The shared publish gate, and its recomputation for stored papers.

Auto-publish re-derives citation integrity from the artifact of record but
used to trust the judge's stored `passed`, which has the OLD audit baked in.
Five papers stayed held on that stale flag after their audits were repaired.
"""

from __future__ import annotations

from pipeline.lyra.quality_gate import (
    citation_coverage_score,
    quality_gate_passed,
    recompute_quality_passed,
    reference_integrity_score,
)


def _clean(**over):
    args = {
        "audit_passed": True,
        "citation_coverage": 15,
        "reference_integrity": 10,
        "placeholder_markers": 0,
        "language_bleed": 0,
        "hallucination_final": 0,
        "high_contradictions": 0,
        "undefined_title_terms": 0,
    }
    args.update(over)
    return args


def test_clean_paper_passes():
    assert quality_gate_passed(**_clean()) is True


def test_every_condition_can_block_on_its_own():
    for blocker in (
        {"audit_passed": False},
        {"citation_coverage": 8},
        {"reference_integrity": 9},
        {"placeholder_markers": 1},
        {"language_bleed": 1},
        {"hallucination_final": 1},
        {"high_contradictions": 1},
        {"undefined_title_terms": 1},
    ):
        assert quality_gate_passed(**_clean(**blocker)) is False, blocker


def test_citation_coverage_boundary_is_nine():
    assert quality_gate_passed(**_clean(citation_coverage=9)) is True
    assert quality_gate_passed(**_clean(citation_coverage=8)) is False


_STORED = {
    "metrics": {"citation_coverage": 15, "reference_integrity": 10},
    "audit_gate_failures": {
        "audit_passed": False,  # stale — this is the flag that used to stick
        "hallucination_final": 0,
        "high_contradictions": 0,
        "undefined_title_terms": 0,
    },
    "passed": False,
}


def test_repaired_audit_lifts_a_stored_paper():
    """The exact case: stored quality says False because the audit did."""
    fresh = {"passed": True, "placeholder_markers": [], "language_bleed": []}
    assert recompute_quality_passed(_STORED, fresh) is True


def test_still_failing_audit_keeps_the_paper_held():
    fresh = {"passed": False, "placeholder_markers": [], "language_bleed": []}
    assert recompute_quality_passed(_STORED, fresh) is False


def test_fresh_language_bleed_blocks_even_with_a_passing_audit():
    """Defence in depth: the audit's own `passed` is not the only signal."""
    fresh = {"passed": True, "placeholder_markers": [], "language_bleed": ["实验"]}
    assert recompute_quality_passed(_STORED, fresh) is False


def test_stored_llm_measurements_still_count():
    """Hallucination and contradiction counts cannot be recomputed without
    re-running the pipeline, so the stored numbers must keep their veto."""
    stored = {
        **_STORED,
        "audit_gate_failures": {**_STORED["audit_gate_failures"], "hallucination_final": 2},
    }
    fresh = {"passed": True, "placeholder_markers": [], "language_bleed": []}
    assert recompute_quality_passed(stored, fresh) is False


def test_missing_metrics_do_not_pass_by_accident():
    """An empty stored score must not read as a clean one."""
    fresh = {"passed": True, "placeholder_markers": [], "language_bleed": []}
    assert recompute_quality_passed({}, fresh) is False


def test_stale_stored_metrics_do_not_hold_a_repaired_paper():
    """Coverage and integrity are functions of the audit, so they must follow
    the fresh one. 80c629b4 stayed held with integrity 8 stored from one
    invalid marker at write time — after the marker was fixed, the stored 8
    still failed the `== 10` rule, and nothing could ever lift it."""
    stored = {**_STORED, "metrics": {"citation_coverage": 6, "reference_integrity": 8}}
    fresh = {
        "passed": True,
        "uncited_paragraphs": 0,
        "invalid_markers": [],
        "orphaned_refs": [],
        "placeholder_markers": [],
        "language_bleed": [],
    }
    assert recompute_quality_passed(stored, fresh) is True


def test_fresh_uncited_paragraphs_block_despite_clean_stored_metrics():
    fresh = {
        "passed": True,
        "uncited_paragraphs": 3,
        "invalid_markers": [],
        "orphaned_refs": [],
        "placeholder_markers": [],
        "language_bleed": [],
    }
    assert recompute_quality_passed(_STORED, fresh) is False


def test_fresh_invalid_marker_blocks_despite_clean_stored_metrics():
    fresh = {
        "passed": True,
        "uncited_paragraphs": 0,
        "invalid_markers": [42],
        "orphaned_refs": [],
        "placeholder_markers": [],
        "language_bleed": [],
    }
    assert recompute_quality_passed(_STORED, fresh) is False


def test_metric_formulas_match_the_judge_rubric():
    """M1: 3 points per uncited paragraph off 15; M2: 2 points per invalid
    marker or orphaned reference off 10; neither goes below zero."""
    assert citation_coverage_score({"uncited_paragraphs": 0}) == 15
    assert citation_coverage_score({"uncited_paragraphs": 2}) == 9
    assert citation_coverage_score({"uncited_paragraphs": 9}) == 0
    assert reference_integrity_score({"invalid_markers": [], "orphaned_refs": []}) == 10
    assert reference_integrity_score({"invalid_markers": [3], "orphaned_refs": [7]}) == 6
    assert reference_integrity_score({"invalid_markers": list(range(9)), "orphaned_refs": []}) == 0
