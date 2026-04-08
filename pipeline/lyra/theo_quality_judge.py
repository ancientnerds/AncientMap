"""Quality judge with backward routing for the Theo agentic pipeline.

Evaluates papers and returns structured routing decisions that tell the
master convergence loop which stage to re-run and what to fix.

The judge scores 7 dimensions (D1-D7) AND identifies specific problems
with their pipeline stage origin and remediation action.

Pass condition: score >= 72 AND zero attribution/fidelity failures.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PASS_THRESHOLD = 72

# Stage number mapping for backward routing
STAGE_NUMBERS = {
    "web_search": 2,
    "source_audit": 3,
    "specialist_analysis": 4,
    "synthesis": 5,
    "debate": 6,
    "moderator": 7,
    "paper_assembly": 8,
}


def _score_d1(audit_result: dict) -> int:
    """D1: Citation Coverage. Score 0-10 based on uncited paragraphs."""
    uncited = audit_result.get("uncited_paragraphs", 0)
    return max(0, 10 - uncited)


def _score_d2(audit_result: dict) -> int:
    """D2: Reference Integrity. Score 0-10 based on invalid/orphaned refs."""
    invalid = len(audit_result.get("invalid_markers", []))
    orphaned = len(audit_result.get("orphaned_refs", []))
    return max(0, 10 - invalid - orphaned)


def judge_paper(
    paper_text: str,
    question: str,
    audit_result: dict,
    source_snippets: list[dict],
    chat_fn,
    model: str,
) -> dict:
    """Judge a research paper and return routing decisions.

    Returns dict with:
        score: int (0-100)
        passed: bool
        problems: list[dict] — each with type, stage, claim, action
        dimensions: dict — D1-D7 scores
        badge: str — Verified/Reviewed/Provisional/Unverified
    """
    # D1 + D2: mechanical scoring from audit
    d1 = _score_d1(audit_result)
    d2 = _score_d2(audit_result)

    # D3-D7: LLM judge call with routing
    d3 = d4 = d5 = d6 = d7 = 0  # worst case if judge fails
    problems: list[dict] = []
    judge_data: dict = {}

    try:
        system = (PROMPTS_DIR / "theo_quality_judge.txt").read_text(encoding="utf-8")

        # Build source context for the judge
        source_context = "\n".join(
            f"[{s['ref_num']}] {s['title']}\nSnippet: {s['snippet'][:2000]}\n"
            for s in source_snippets[:20]
        )

        # Send full paper (up to 12K) for thorough review
        paper_excerpt = paper_text[:12000]

        user_msg = (
            f"## Research question\n\n{question}\n\n"
            f"## Paper text (first 12000 chars)\n\n{paper_excerpt}\n\n"
            f"## Source snippets (for verification)\n\n{source_context}"
        )

        raw = chat_fn(model, system, user_msg, 4096)

        # Parse JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        judge_data = json.loads(cleaned)

        # Extract dimension scores
        dims = judge_data.get("dimensions", {})
        d3 = min(10, max(0, dims.get("attribution_accuracy", 0)))
        d4 = min(10, max(0, dims.get("source_fidelity", 0)))
        d5 = min(10, max(0, dims.get("hedging", 0)))
        d6 = min(10, max(0, dims.get("coherence", 0)))
        d7 = min(10, max(0, dims.get("question_fidelity", 0)))

        # Extract problems
        problems = judge_data.get("problems", [])

    except Exception as exc:
        logger.warning("Quality judge call failed: %s", exc)

    # Calculate total score
    raw_score = d1 * 2 + d2 + d3 + d4 + d5 + d6 + d7
    total = round(raw_score / 80 * 100)

    # Badge tier
    if total >= 90:
        badge = "Verified"
    elif total >= 72:
        badge = "Reviewed"
    elif total >= 55:
        badge = "Provisional"
    else:
        badge = "Unverified"

    # Pass requires score >= 72 AND zero critical failures
    critical_failures = [
        p for p in problems if p.get("type") in ("attribution_failure", "source_fidelity_failure")
    ]
    passed = total >= PASS_THRESHOLD and len(critical_failures) == 0

    return {
        "score": total,
        "passed": passed,
        "badge": badge,
        "problems": problems,
        "dimensions": {
            "citation_coverage": d1 * 2,
            "reference_integrity": d2,
            "attribution_accuracy": d3,
            "source_fidelity": d4,
            "hedging": d5,
            "coherence": d6,
            "question_fidelity": d7,
        },
    }


def get_restart_stage(problems: list[dict]) -> int:
    """Determine which stage to restart from based on judge problems.

    Returns the LOWEST stage number that needs re-running.
    If no problems or only paper_assembly issues, returns 8.
    """
    if not problems:
        return 8

    min_stage = 8
    for problem in problems:
        stage_name = problem.get("stage", "paper_assembly")
        stage_num = STAGE_NUMBERS.get(stage_name, 8)
        if stage_num < min_stage:
            min_stage = stage_num

    return min_stage


def apply_feedback_to_context(ctx, problems: list[dict]) -> None:
    """Apply judge feedback to the pipeline context.

    Strips bad claims from specialist analyses for attribution/fidelity failures.
    Appends search queries for source gaps.
    """
    for problem in problems:
        action = problem.get("action", "")

        if action == "strip_claim" and problem.get("claim"):
            # Remove the offending claim from specialist analyses
            claim_text = problem["claim"].lower()
            for _spec_id, analysis in ctx.specialist_analyses.items():
                findings = analysis.get("findings", [])
                analysis["findings"] = [
                    f for f in findings if claim_text not in f.get("claim", "").lower()
                ]

        elif action == "search_more" and problem.get("suggested_queries"):
            # Append new search queries
            for q in problem["suggested_queries"]:
                if q not in ctx.searched_queries:
                    ctx.search_queries.append(q)
