"""Presentation assessor -- reviews the assembled paper for consistency,
spelling, formatting, and section balance before the quality judge runs."""

import asyncio
import logging

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import FactCheckComplete, PresentationChecked

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a presentation assessor for a research paper. Review the paper and return a corrected version.

CHECK FOR:
1. Proper nouns, archaeological terms, and site names: ensure consistent spelling throughout.
   - If a name appears in multiple forms (e.g. "Gobekli Tepe" vs "Gobekli tepe"), pick the correct one and use it everywhere.
   - Fix obvious misspellings of well-known terms (e.g. "Mesopotania" -> "Mesopotamia").

2. Section balance: flag if any section is drastically shorter or longer than others.
   - If one section is 10x longer than another, trim the long section to its core points.
   - If a section is fewer than 2 sentences, expand it slightly with a connecting sentence or merge it into an adjacent section.

3. Formatting consistency:
   - All section headings should use ## (not ### or #).
   - Remove any stray markdown artifacts (triple backticks, HTML tags, etc.).
   - Ensure consistent citation format [N] throughout.

4. Readability:
   - Fix run-on sentences.
   - Break up paragraphs longer than 8 sentences.

RULES:
- Return the COMPLETE corrected paper text. Do not summarize or truncate.
- Do NOT add new content, claims, or citations. Only correct what is there.
- Do NOT remove citations or references.
- Do NOT change the paper's conclusions or arguments.
- Preserve the exact heading structure (## title, ## section names, ## References).
- Output ONLY the corrected paper text. No commentary, no explanations.
"""


class PresentationHandler(BaseHandler):
    """Checks paper presentation quality before the judge evaluates it."""

    def register(self):
        self.bus.on(FactCheckComplete, self._on_fact_check_complete)

    async def _on_fact_check_complete(self, event: FactCheckComplete):
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "presentation",
                "status": "start",
                "meta": {"subtask_total": 1},
            }
        )
        self.emit_sse({"type": "status", "content": "Checking paper presentation..."})

        paper_text = self.state.paper_text
        if not paper_text or len(paper_text.strip()) < 100:
            self.state.log("presentation", "Paper too short for presentation check, skipping")
            await self.bus.emit(PresentationChecked())
            return

        settings = _get_settings()

        user_msg = f"## Paper to review\n\n{paper_text}"

        async with self.semaphore:
            corrected = await asyncio.to_thread(
                minimax_chat_anthropic,
                _SYSTEM_PROMPT,
                user_msg,
                self.state.config.max_tokens_per_call,
                settings,
                temperature=settings.temperature_narrative,
            )
        self.state.llm_call_count += 1

        # Only accept the corrected version if it's reasonably close in length
        # to the original (LLM didn't truncate or hallucinate a tiny response)
        corrected = corrected.strip()
        original_len = len(paper_text)
        corrected_len = len(corrected)

        if corrected_len >= original_len * 0.7:
            self.state.paper_text = corrected
            self.state.log(
                "presentation",
                f"Paper corrected: {original_len} -> {corrected_len} chars",
            )
        else:
            self.state.log(
                "presentation",
                f"Corrected paper too short ({corrected_len} vs {original_len}), keeping original",
            )

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "presentation",
                "status": "done",
                "meta": {
                    "original_chars": original_len,
                    "corrected_chars": corrected_len,
                },
            }
        )

        await self.bus.emit(PresentationChecked())
