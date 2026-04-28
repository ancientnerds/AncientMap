"""Presentation assessor -- reviews the assembled paper for consistency,
spelling, formatting, and section balance before the quality judge runs."""

import asyncio
import logging
import re

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import FactCheckComplete, PresentationChecked

logger = logging.getLogger(__name__)


def _split_paper_for_presentation(paper_text: str) -> tuple[str, str]:
    """Split paper into (prose, references_block).

    Run 16 audit found the presentation LLM mangling the references list:
    only [1]-[5] retained their [N] markers; entries 6+ were glued onto a
    single line and 9 of 46 references vanished entirely. The fix is to
    not let the LLM see references at all — split them off, run the LLM on
    prose only, then re-append the references block verbatim.

    Returns (prose_text, references_block). Either may be empty.
    """
    refs_match = re.search(r"\n##\s*References\s*\n", paper_text)
    if not refs_match:
        return paper_text, ""
    return paper_text[: refs_match.start()], paper_text[refs_match.start() :]


_REQUIRED_HEADINGS_LOWER = {
    "connecting the dots",
    "the other side",
    "what we actually know",
}


def _h2_headings_lower(text: str) -> set[str]:
    """Return the set of `## Heading` titles in `text`, lowercased and stripped."""
    return {m.group(1).strip().lower() for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)}


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

CITATION PRESERVATION (HARD REQUIREMENT — VIOLATIONS REJECT THE OUTPUT):
- EVERY `[N]` marker present in the input MUST appear in your output.
- If you split a paragraph or merge sentences, carry the `[N]` markers with the
  facts they cite. Do NOT drop a marker because the surrounding sentence got
  rewritten — re-attach it to the rewritten sentence.
- A factual paragraph (>50 chars, named entities, dates, measurements) WITHOUT
  any `[N]` marker will be deleted from the published paper. Better to keep an
  awkward sentence than strip its citation.
- Image markdown blocks `![...](...)`, captions in italics, and source-link
  trailers `[Source](url)` must be preserved verbatim.

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

        # Split refs off so the LLM never sees them. Run 16 had the LLM
        # mangle the References list (entries 6+ lost their [N] markers,
        # 9 of 46 entries vanished). The references are pipeline-rendered
        # text; the LLM has no business rewriting them.
        prose_for_llm, references_block = _split_paper_for_presentation(paper_text)
        prose_headings_before = _h2_headings_lower(prose_for_llm)
        required_present_before = _REQUIRED_HEADINGS_LOWER & prose_headings_before

        user_msg = f"## Paper to review\n\n{prose_for_llm}"

        async with self.semaphore:
            corrected_prose = await asyncio.to_thread(
                minimax_chat_anthropic,
                _SYSTEM_PROMPT,
                user_msg,
                self.state.config.max_tokens_per_call,
                settings,
                temperature=settings.temperature_narrative,
            )
        self.state.llm_call_count += 1

        corrected_prose = corrected_prose.strip()
        prose_original_len = len(prose_for_llm)
        prose_corrected_len = len(corrected_prose)

        # Validation: the corrected prose must (a) not be drastically shorter,
        # and (b) preserve every required structural heading that was present
        # in the input. If either check fails, reject the LLM's output and
        # keep the writer's original prose — the audit gate's better-fix is
        # an honest rewrite next iteration than a silent structural regression.
        accepted = True
        rejection_reason = ""
        if prose_corrected_len < prose_original_len * 0.7:
            accepted = False
            rejection_reason = (
                f"corrected prose too short ({prose_corrected_len} vs {prose_original_len})"
            )
        else:
            corrected_headings = _h2_headings_lower(corrected_prose)
            dropped_required = required_present_before - corrected_headings
            if dropped_required:
                accepted = False
                rejection_reason = (
                    f"corrected prose dropped required heading(s): {sorted(dropped_required)}"
                )

        if accepted:
            new_paper = corrected_prose
            if references_block:
                new_paper = corrected_prose.rstrip() + "\n" + references_block
            self.state.paper_text = new_paper
            self.state.log(
                "presentation",
                f"Paper corrected: prose {prose_original_len} -> {prose_corrected_len} chars; "
                f"references re-appended verbatim ({len(references_block)} chars)",
            )
        else:
            self.state.log("presentation", f"Rejected LLM correction: {rejection_reason}")

        # Keep these defined for the SSE meta block at the end.
        original_len = len(paper_text)
        corrected_len = len(self.state.paper_text)

        # Re-strip + re-audit after presentation. The LLM rewrite often
        # paraphrases factual paragraphs and drops their [N] markers in the
        # process — Run 11 saw 0 uncited pre-presentation but 23 uncited
        # post-presentation, with a 16% character shrink. Run smart-injection
        # again so paragraphs the LLM stripped citations from get them back
        # from the registry; truly unsupported ones get deleted; then audit
        # the final state.
        from pipeline.lyra.theo_citations import (
            audit_citations,
            prune_orphaned_references,
            prune_unrenderable_references,
            strip_uncited_factual_paragraphs,
        )

        try:
            post_strip_metrics: dict = {}
            self.state.paper_text = strip_uncited_factual_paragraphs(
                self.state.paper_text,
                self.state.registry,
                metrics_out=post_strip_metrics,
            )
            self.state.post_presentation_strip_metrics = post_strip_metrics
            # Drop registry entries that no longer have a [N] in prose.
            # inject_citation_for_paragraph assigns numbers eagerly even when
            # the paragraph it was attached to ends up restored to its
            # un-injected original by the section-preserve safeguard. Run 14:
            # 3 orphans → audit.passed=false despite everything else clean.
            pruned = prune_orphaned_references(self.state.paper_text, self.state.registry)
            self.state.post_presentation_orphans_pruned = pruned
            # Coherence at publish: drop reference_numbers entries whose
            # source was popped by the journal rejection path. Audit (Fix 1)
            # is honest with or without this; the helper just keeps the data
            # structure consistent for any other consumer.
            unrenderable = prune_unrenderable_references(self.state.registry)
            self.state.post_presentation_unrenderable_pruned = unrenderable
            new_audit = audit_citations(self.state.paper_text, self.state.registry)
            self.state.audit_result = new_audit
            self.state.log(
                "presentation",
                f"Post-presentation strip: seen={post_strip_metrics.get('uncited_seen', 0)}, "
                f"injected={post_strip_metrics.get('injected', 0)}, "
                f"dropped={post_strip_metrics.get('dropped', 0)}, "
                f"restored_sections={post_strip_metrics.get('restored_sections', 0)}, "
                f"pruned_orphans={pruned}, "
                f"pruned_unrenderable={unrenderable}",
            )
            self.state.log(
                "presentation",
                f"Re-audit after presentation: passed={new_audit.get('passed')}, "
                f"non_numeric={len(new_audit.get('non_numeric_markers') or [])}, "
                f"uncited={new_audit.get('uncited_paragraphs', 0)}, "
                f"orphaned={len(new_audit.get('orphaned_refs') or [])}",
            )
        except Exception as e:
            logger.warning("post-presentation re-audit failed: %s", e)

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
