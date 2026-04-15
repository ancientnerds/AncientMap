"""Quality judge --- evaluates paper quality using v2 dimensions and routes feedback."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import ImageGenComplete, QualityFailed, QualityPassed
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Badge thresholds on the 0-70 raw scale
_BADGE_THRESHOLDS = [
    (63, "Platinum"),
    (56, "Gold"),
    (49, "Silver"),
    (42, "Bronze"),
    (0, "Unverified"),
]
_PASS_RAW = 52  # out of 70


class JudgeHandler(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._judge_attempts = 0
        self._best_score = 0
        self._best_paper = ""
        self._best_audit = {}
        self._best_quality = {}

    def register(self):
        self.bus.on(ImageGenComplete, self._on_image_gen_complete)

    async def _on_image_gen_complete(self, event: ImageGenComplete):
        self.state.phase = ResearchPhase.JUDGING
        self._judge_attempts += 1

        # Initialize best paper from current paper if empty (first attempt)
        if not self._best_paper:
            self._best_paper = self.state.paper_text
            self._best_audit = self.state.audit_result
            self._best_quality = self.state.quality_score

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "start",
                "meta": {"subtask_total": 1, "attempt": self._judge_attempts},
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": f"Running quality judge (attempt {self._judge_attempts})...",
            }
        )

        # Citation audit (mechanical D1/D2 from audit_result)
        from pipeline.lyra.theo_citations import audit_citations

        audit_result = audit_citations(self.state.paper_text, self.state.registry)
        self.state.audit_result = audit_result

        # Mechanical scores from citation audit
        uncited = audit_result.get("uncited_paragraphs", 0)
        mech_citation_coverage = max(0, 10 - uncited)

        invalid = len(audit_result.get("invalid_markers", []))
        orphaned = len(audit_result.get("orphaned_refs", []))
        mech_ref_integrity = max(0, 10 - invalid - orphaned)

        # Build source snippets for judge
        source_snippets = []
        for sid, num in sorted(self.state.registry.reference_numbers.items(), key=lambda kv: kv[1]):
            source = self.state.registry.get_reference(sid)
            if source:
                source_snippets.append(
                    {"ref_num": num, "title": source.title, "snippet": source.snippet}
                )

        # Run v2 quality judge via LLM
        v2_prompt = (PROMPTS_DIR / "v2_quality_judge.txt").read_text(encoding="utf-8")

        source_context = "\n".join(
            f"[{s['ref_num']}] {s['title']}\nSnippet: {s['snippet'][:2000]}\n"
            for s in source_snippets[:20]
        )
        paper_excerpt = self.state.paper_text[:12000]

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Paper text (first 12000 chars)\n\n{paper_excerpt}\n\n"
            f"## Source snippets (for verification)\n\n{source_context}\n\n"
            f"## Citation audit results\n\n"
            f"Citation coverage score: {mech_citation_coverage}/10\n"
            f"Reference integrity score: {mech_ref_integrity}/10\n"
            f"Uncited paragraphs: {uncited}\n"
            f"Invalid markers: {invalid}\n"
            f"Orphaned refs: {orphaned}\n"
        )

        judge_data: dict = {}
        for attempt in range(2):
            try:
                async with self.semaphore:
                    raw = await asyncio.to_thread(
                        minimax_chat_anthropic,
                        v2_prompt,
                        user_msg,
                        4096,
                        _get_settings(),
                    )
                self.state.llm_call_count += 1

                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()

                judge_data = json.loads(cleaned)
                break
            except json.JSONDecodeError as exc:
                logger.warning(
                    "V2 quality judge JSON parse failed (attempt %d): %s", attempt + 1, exc
                )
                if attempt == 1:
                    logger.error("V2 quality judge failed after 2 attempts")
            except Exception as exc:
                logger.error("V2 quality judge call failed: %s", exc)
                break

        # Extract LLM-scored dimensions
        dims = judge_data.get("dimensions", {})
        d_hook = min(10, max(0, dims.get("hook_quality", 0)))
        d_narrative = min(10, max(0, dims.get("investigative_narrative", 0)))
        d_connections = min(10, max(0, dims.get("cross_angle_connections", 0)))
        d_balance = min(10, max(0, dims.get("balance", 0)))
        d_honesty = min(10, max(0, dims.get("assessment_honesty", 0)))
        d_citation = min(10, max(0, dims.get("citation_integrity", 0)))
        d_diversity = min(10, max(0, dims.get("source_diversity", 0)))

        problems = judge_data.get("problems", [])

        # Total on 0-70 raw scale (7 LLM dimensions)
        raw_total = (
            d_hook + d_narrative + d_connections + d_balance + d_honesty + d_citation + d_diversity
        )

        # Scale to 0-100 for backward compat
        scaled_score = round(raw_total / 70 * 100)

        # Badge from raw total
        badge = "Unverified"
        for threshold, badge_name in _BADGE_THRESHOLDS:
            if raw_total >= threshold:
                badge = badge_name
                break

        passed = raw_total >= _PASS_RAW

        result = {
            "score": scaled_score,
            "raw_total": raw_total,
            "passed": passed,
            "badge": badge,
            "problems": problems,
            "dimensions": {
                "hook_quality": d_hook,
                "investigative_narrative": d_narrative,
                "cross_angle_connections": d_connections,
                "balance": d_balance,
                "assessment_honesty": d_honesty,
                "citation_integrity": d_citation,
                "source_diversity": d_diversity,
            },
            "mechanical": {
                "citation_coverage": mech_citation_coverage,
                "reference_integrity": mech_ref_integrity,
            },
        }

        self.state.quality_score = result
        self.state.log(
            "judge",
            f"Score {scaled_score}/100 (raw {raw_total}/70, {badge}), "
            f"passed={passed}, attempt={self._judge_attempts}",
        )

        # Track best
        if scaled_score > self._best_score:
            self._best_score = scaled_score
            self._best_paper = self.state.paper_text
            self._best_audit = audit_result
            self._best_quality = result

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "done",
                "meta": {
                    "score": scaled_score,
                    "raw_total": raw_total,
                    "badge": badge,
                    "passed": passed,
                    "attempt": self._judge_attempts,
                },
            }
        )

        if passed or scaled_score >= self.state.config.quality_pass_threshold:
            self.state.phase = ResearchPhase.DONE
            await self.bus.emit(QualityPassed(score=scaled_score))
        elif self._judge_attempts >= self.state.config.max_judge_failures:
            # Ship best available
            self.state.paper_text = self._best_paper
            self.state.audit_result = self._best_audit
            self.state.quality_score = self._best_quality
            self.state.log(
                "judge",
                f"Max attempts ({self._judge_attempts}) reached, shipping best (score={self._best_score})",
            )
            self.state.phase = ResearchPhase.DONE
            await self.bus.emit(QualityPassed(score=self._best_score))
        else:
            # Identify weak areas for re-research
            weak_areas = [p.get("type", "unknown") for p in problems[:5]]
            await self.bus.emit(QualityFailed(score=scaled_score, weak_areas=weak_areas))
