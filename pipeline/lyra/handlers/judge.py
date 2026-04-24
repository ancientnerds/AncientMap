"""Quality judge --- mechanical badge assignment from pipeline metrics.

No LLM call. No re-loop. The paper has already been vetted by 8 quality
gates (specialists, cross-pollination, convergence, synthesis, debate,
moderation, fact-check, presentation). The judge computes a badge from
measurable structural metrics and always ships the paper.
"""

import logging
import re

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import ImageGenComplete, QualityPassed
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)

# Required Why Files sections (checked by heading match)
_REQUIRED_SECTIONS = [
    "connecting the dots",
    "the other side",
    "what we actually know",
]

# Badge thresholds on the 0-100 scale
_BADGE_THRESHOLDS = [
    (90, "Platinum"),
    (75, "Gold"),
    (60, "Silver"),
    (45, "Bronze"),
    (0, "Unverified"),
]


class JudgeHandler(BaseHandler):
    def register(self):
        self.bus.on(ImageGenComplete, self._on_image_gen_complete)

    async def _on_image_gen_complete(self, event: ImageGenComplete):
        self.state.phase = ResearchPhase.JUDGING

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "start",
                "meta": {"subtask_total": 1},
            }
        )
        self.emit_sse({"type": "status", "content": "Computing quality badge..."})

        # --- Citation audit (mechanical) ---
        # Reuse the audit paper.py already computed during assembly. Re-running
        # here let subtle state differences (e.g., References appended vs not)
        # produce divergent audit results from the stored one, causing the
        # observed "reference_integrity=0 despite audit.orphaned_refs=[]"
        # inconsistency. Single source of truth now.
        audit_result = self.state.audit_result
        if not audit_result:
            # Defensive fallback: paper assembly should always set this.
            from pipeline.lyra.theo_citations import audit_citations

            audit_result = audit_citations(self.state.paper_text, self.state.registry)
            self.state.audit_result = audit_result

        # --- Compute metrics ---
        scores = {}

        # M1: Citation coverage (0-15)
        # Each uncited paragraph costs 3 points
        uncited = audit_result.get("uncited_paragraphs", 0)
        scores["citation_coverage"] = max(0, 15 - uncited * 3)

        # M2: Reference integrity (0-10)
        # Invalid markers and orphaned refs cost 2 points each
        invalid = len(audit_result.get("invalid_markers", []))
        orphaned = len(audit_result.get("orphaned_refs", []))
        scores["reference_integrity"] = max(0, 10 - (invalid + orphaned) * 2)

        # M3: Section completeness (0-20)
        # Check for required Why Files sections
        paper_lower = self.state.paper_text.lower()
        headings_found = sum(1 for sec in _REQUIRED_SECTIONS if f"## {sec}" in paper_lower)
        # Also check for at least one investigation section (any ## heading before Connecting)
        has_investigation = bool(re.search(r"^## .+", self.state.paper_text, re.MULTILINE))
        section_score = (headings_found / len(_REQUIRED_SECTIONS)) * 15
        if has_investigation:
            section_score += 5
        scores["section_completeness"] = min(20, round(section_score))

        # M4: Source diversity (0-15)
        # Count unique sources and their types/tiers
        total_sources = len(self.state.registry.sources)
        sources_with_tier = sum(
            1 for s in self.state.registry.sources.values() if s.reliability_tier > 0
        )
        if total_sources >= 20:
            scores["source_diversity"] = 15
        elif total_sources >= 10:
            scores["source_diversity"] = 12
        elif total_sources >= 5:
            scores["source_diversity"] = 8
        else:
            scores["source_diversity"] = max(0, total_sources * 2)

        # M5: Research depth (0-20)
        # Angles explored, rounds completed, claims produced
        total_claims = sum(len(a.findings) for a in self.state.angles)
        angles_saturated = sum(1 for a in self.state.angles if a.saturated)
        total_angles = len(self.state.angles)
        debate_rounds = 0
        if self.state.debate_result:
            debate_rounds = self.state.debate_result.get("rounds", 0)
            if isinstance(debate_rounds, list):
                debate_rounds = len(debate_rounds)

        depth = 0
        # Angle coverage (0-8)
        if total_angles > 0:
            depth += round((angles_saturated / total_angles) * 8)
        # Claim volume (0-6)
        if total_claims >= 50:
            depth += 6
        elif total_claims >= 20:
            depth += 4
        elif total_claims >= 10:
            depth += 2
        # Debate (0-3)
        depth += min(3, debate_rounds)
        # Cross-pollination bonus (0-3)
        if self.state.cross_pollinated:
            depth += 3
        scores["research_depth"] = min(20, depth)

        # M6: Paper length (0-10)
        # Too short = undercooked, but don't penalize long papers
        word_count = len(self.state.paper_text.split())
        if word_count >= 2000:
            scores["paper_substance"] = 10
        elif word_count >= 1000:
            scores["paper_substance"] = 7
        elif word_count >= 500:
            scores["paper_substance"] = 4
        else:
            scores["paper_substance"] = 2

        # M7: Moderation quality (0-10)
        # Did moderation drop weak claims? (sign of quality control)
        mod = self.state.moderated_result
        final_claims = len(mod.get("final_claims", []))
        dropped_claims = len(mod.get("dropped_claims", []))
        revised_claims = len(mod.get("revised_claims", []))
        if final_claims > 0:
            scores["moderation"] = 7
            if dropped_claims > 0:
                scores["moderation"] += 2  # actually filtering
            if revised_claims > 0:
                scores["moderation"] += 1  # refining
        else:
            scores["moderation"] = 3  # moderation ran but produced nothing

        scores["moderation"] = min(10, scores["moderation"])

        # --- Total ---
        total = sum(scores.values())
        total = min(100, total)

        # Badge
        badge = "Unverified"
        for threshold, badge_name in _BADGE_THRESHOLDS:
            if total >= threshold:
                badge = badge_name
                break

        # Hallucination-gate metrics (populated by PaperHandler._run_hallucination_gate)
        hall_metrics = getattr(
            self.state,
            "hallucination_metrics",
            {"initial": 0, "final": 0, "retries": 0},
        )

        # Coherence-pass result (populated by PaperHandler Step 8b).
        # The gate fails ONLY on `high` severity — outright opposite-binary
        # contradictions (e.g. "exists" vs "does not exist" on the same
        # subject). `medium` flags are surfaced for editorial review but
        # don't block the paper, since the writer often presents nuance
        # across sections that the LLM heuristically labels as conflict.
        coherence = getattr(self.state, "coherence_result", None)
        if coherence is not None:
            high_contradictions = sum(1 for c in coherence.contradictions if c.severity == "high")
            medium_contradictions = sum(
                1 for c in coherence.contradictions if c.severity == "medium"
            )
            undefined_title_terms = [
                t for t, defined in coherence.title_terms_defined_in_body.items() if not defined
            ]
        else:
            high_contradictions = 0
            medium_contradictions = 0
            undefined_title_terms = []

        # Real passed gate — evidence-based, not hardcoded. The paper ships in
        # either case (the caller decides), but `passed` now truthfully signals
        # citation integrity so downstream consumers (UI, auto-publish flows)
        # can distinguish clean from bug-riddled output.
        passed = bool(
            audit_result.get("passed", False)
            and scores["citation_coverage"] >= 9
            and scores["reference_integrity"] == 10
            and not audit_result.get("placeholder_markers")
            and not audit_result.get("language_bleed")
            and hall_metrics.get("final", 0) == 0
            and high_contradictions == 0
            and not undefined_title_terms
        )

        # Badge polish (H1): if the paper failed the gate, a Gold badge is
        # user-confusing. Downgrade to Unverified regardless of raw score.
        if not passed:
            badge = "Unverified"

        result = {
            "score": total,
            "badge": badge,
            "passed": passed,
            "metrics": scores,
            "mechanical": {
                "citation_coverage": scores["citation_coverage"],
                "reference_integrity": scores["reference_integrity"],
            },
            "meta": {
                "total_sources": total_sources,
                "sources_scored": sources_with_tier,
                "total_claims": total_claims,
                "angles": total_angles,
                "angles_saturated": angles_saturated,
                "debate_rounds": debate_rounds,
                "word_count": word_count,
                "uncited_paragraphs": uncited,
                "placeholder_markers": len(audit_result.get("placeholder_markers", [])),
                "language_bleed": len(audit_result.get("language_bleed", [])),
                "hallucination_initial": hall_metrics.get("initial", 0),
                "hallucination_final": hall_metrics.get("final", 0),
                "hallucination_retries": hall_metrics.get("retries", 0),
                "coherence_contradictions": high_contradictions,
                "coherence_medium_contradictions": medium_contradictions,
                "coherence_undefined_title_terms": undefined_title_terms,
            },
        }

        self.state.quality_score = result
        self.state.log(
            "judge",
            f"Mechanical score {total}/100 ({badge}), "
            f"sources={total_sources}, claims={total_claims}, "
            f"words={word_count}",
        )

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "done",
                "meta": {
                    "score": total,
                    "badge": badge,
                    "passed": passed,
                    "metrics": scores,
                },
            }
        )

        self.state.phase = ResearchPhase.DONE
        await self.bus.emit(QualityPassed(score=total))
