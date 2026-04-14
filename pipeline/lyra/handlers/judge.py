"""Quality judge — evaluates paper quality and routes feedback."""

import asyncio
import logging

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import PaperReady, QualityFailed, QualityPassed
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)


class JudgeHandler(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._judge_attempts = 0
        self._best_score = 0
        self._best_paper = ""
        self._best_audit = {}
        self._best_quality = {}

    def register(self):
        self.bus.on(PaperReady, self._on_paper_ready)

    async def _on_paper_ready(self, event: PaperReady):
        self.state.phase = ResearchPhase.JUDGING
        self._judge_attempts += 1

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

        # Citation audit
        from pipeline.lyra.theo_citations import audit_citations

        audit_result = audit_citations(self.state.paper_text, self.state.registry)
        self.state.audit_result = audit_result

        # Build source snippets for judge
        source_snippets = []
        for sid, num in sorted(self.state.registry.reference_numbers.items(), key=lambda kv: kv[1]):
            source = self.state.registry.get_reference(sid)
            if source:
                source_snippets.append(
                    {"ref_num": num, "title": source.title, "snippet": source.snippet}
                )

        # Run quality judge
        from pipeline.lyra.theo_quality_judge import judge_paper

        def _chat(_model, system, user, max_tokens):
            return minimax_chat_anthropic(system, user, max_tokens, settings=_get_settings())

        async with self.semaphore:
            result = await asyncio.to_thread(
                judge_paper,
                self.state.paper_text,
                self.state.question,
                audit_result,
                source_snippets,
                _chat,
                "MiniMax-M2.7",
            )
        self.state.llm_call_count += 1

        score = result.get("score", 0)
        passed = result.get("passed", False)
        badge = result.get("badge", "")

        self.state.quality_score = result
        self.state.log(
            "judge", f"Score {score}/100 ({badge}), passed={passed}, attempt={self._judge_attempts}"
        )

        # Track best
        if score > self._best_score:
            self._best_score = score
            self._best_paper = self.state.paper_text
            self._best_audit = audit_result
            self._best_quality = result

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "done",
                "meta": {
                    "score": score,
                    "badge": badge,
                    "passed": passed,
                    "attempt": self._judge_attempts,
                },
            }
        )

        if passed or score >= self.state.config.quality_pass_threshold:
            self.state.phase = ResearchPhase.DONE
            await self.bus.emit(QualityPassed(score=score))
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
            problems = result.get("problems", [])
            weak_areas = [p.get("type", "unknown") for p in problems[:5]]
            await self.bus.emit(QualityFailed(score=score, weak_areas=weak_areas))
