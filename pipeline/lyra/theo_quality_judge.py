"""Quality scoring for Theo research papers.

Evaluates papers across 7 dimensions (2 mechanical + 5 LLM-judged)
and produces a 0-100 quality score. Used in the convergence loop
to detect hallucinations and trigger regeneration.

Dimensions:
  D1 Citation Coverage (2x weight) — mechanical, from audit_citations()
  D2 Reference Integrity (1x) — mechanical, from audit_citations()
  D3 Attribution Accuracy (1x) — LLM judge, quote-based verification
  D4 Source Fidelity (1x) — LLM judge, claim vs source snippet
  D5 Hedging Appropriateness (1x) — LLM judge
  D6 Logical Coherence (1x) — LLM judge
  D7 Research Question Fidelity (1x) — LLM judge

Score formula: round((D1*2 + D2 + D3 + D4 + D5 + D6 + D7) / 80 * 100)

Badge tiers:
  90-100: Verified (green)
  72-89:  Reviewed (amber)
  55-71:  Provisional (orange)
  0-54:   Unverified (red)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PASS_THRESHOLD = 72


def _score_d1(audit_result: dict) -> int:
    """D1: Citation Coverage. Score 0-10 based on uncited paragraphs."""
    uncited = audit_result.get("uncited_paragraphs", 0)
    return max(0, 10 - uncited)


def _score_d2(audit_result: dict) -> int:
    """D2: Reference Integrity. Score 0-10 based on invalid/orphaned refs."""
    invalid = len(audit_result.get("invalid_markers", []))
    orphaned = len(audit_result.get("orphaned_refs", []))
    return max(0, 10 - invalid - orphaned)


def score_paper(
    paper_text: str,
    question: str,
    audit_result: dict,
    source_snippets: list[dict],
    chat_fn,
    model: str,
) -> dict:
    """Score a research paper across all 7 dimensions.

    Args:
        paper_text: The full paper markdown
        question: The original research question
        audit_result: Output from audit_citations()
        source_snippets: List of {ref_num, title, snippet} for top sources
        chat_fn: Callable(client, model, system, user, max_tokens) -> str
        model: M2.7 model name

    Returns dict with total score, dimension scores, badge, and rationales.
    """
    # D1 + D2: mechanical scoring from audit
    d1 = _score_d1(audit_result)
    d2 = _score_d2(audit_result)

    # D3-D7: bundled LLM judge call
    d3 = d4 = d5 = d6 = d7 = 0  # defaults if judge fails — assume worst case
    judge_data = {}

    try:
        system = (PROMPTS_DIR / "theo_quality_judge.txt").read_text(encoding="utf-8")

        # Build source context for the judge (top 20 referenced snippets)
        source_context = "\n".join(
            f"[{s['ref_num']}] {s['title']}\nSnippet: {s['snippet'][:500]}\n"
            for s in source_snippets[:20]
        )

        # Truncate paper to 12K chars so judge sees most of the paper
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

        d3 = min(10, max(0, judge_data.get("d3_attribution", {}).get("score", 5)))
        d4 = min(10, max(0, judge_data.get("d4_fidelity", {}).get("score", 5)))
        d5 = min(10, max(0, judge_data.get("d5_hedging", {}).get("score", 5)))
        d6 = min(10, max(0, judge_data.get("d6_coherence", {}).get("score", 5)))
        d7 = min(10, max(0, judge_data.get("d7_question_fidelity", {}).get("score", 5)))

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

    # Build failure summary for convergence feedback
    failures: list[str] = []
    if d1 < 8:
        failures.append(
            f"Citation coverage: {audit_result.get('uncited_paragraphs', 0)} uncited paragraphs"
        )
    if d2 < 8:
        failures.append(
            f"Reference integrity: {len(audit_result.get('invalid_markers', []))} invalid, {len(audit_result.get('orphaned_refs', []))} orphaned"
        )
    for dim_key, dim_label in [
        ("d3_attribution", "Attribution accuracy"),
        ("d4_fidelity", "Source fidelity"),
    ]:
        dim_data = judge_data.get(dim_key, {})
        for f in dim_data.get("failures", []):
            failures.append(f"{dim_label}: {f}")

    return {
        "total": total,
        "badge": badge,
        "passed": total >= PASS_THRESHOLD,
        "dimensions": {
            "citation_coverage": d1 * 2,
            "reference_integrity": d2,
            "attribution_accuracy": d3,
            "source_fidelity": d4,
            "hedging": d5,
            "coherence": d6,
            "question_fidelity": d7,
        },
        "failures": failures,
        "rationales": {
            dim_key: judge_data.get(dim_key, {}).get("rationale", "")
            for dim_key in [
                "d3_attribution",
                "d4_fidelity",
                "d5_hedging",
                "d6_coherence",
                "d7_question_fidelity",
            ]
        },
    }
