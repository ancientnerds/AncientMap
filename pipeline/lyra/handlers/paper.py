"""Why Files narrative paper assembly."""

import asyncio
import json
import logging
import re
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import ModeratorComplete, PaperReady
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PaperHandler(BaseHandler):
    """Assembles the final research paper using the Why Files narrative structure.

    Triggered by ModeratorComplete. Produces a complete markdown paper with:
    - Hook (vivid opening)
    - Investigation sections (per angle, parallel)
    - Connecting the Dots (cross-angle synthesis)
    - The Other Side (counter-evidence)
    - What We Actually Know (honest assessment)
    - Verified citations with references list
    """

    def register(self):
        self.bus.on(ModeratorComplete, self._on_moderator_complete)

    async def _on_moderator_complete(self, event: ModeratorComplete):
        self.state.phase = ResearchPhase.WRITING
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "paper_assembly",
                "status": "start",
                "meta": {"subtask_total": 6},
            }
        )
        self.state.log("paper", "Paper assembly started")

        settings = _get_settings()

        # ---------------------------------------------------------------
        # Step 0: Build reference map and claims
        # ---------------------------------------------------------------
        sid_to_num, ref_map_text, claims_by_angle = self._build_reference_map()
        all_claims = self._collect_all_claims(sid_to_num)

        # ---------------------------------------------------------------
        # Step 1: Generate outline
        # ---------------------------------------------------------------
        self.emit_sse(
            {
                "type": "status",
                "content": "Planning paper structure...",
                "subtask_done": 0,
                "subtask_total": 6,
            }
        )

        outline = await self._generate_outline(sid_to_num, settings)
        title = outline.get("title", self.state.question[:60])
        sections = outline.get("sections", [])

        if not sections:
            # Minimal fallback structure
            sections = [
                {
                    "id": 1,
                    "type": "investigation",
                    "title": "Findings",
                    "angle_ids": [a.id for a in self.state.angles],
                    "narrative_goal": "Present the evidence",
                },
                {
                    "id": 2,
                    "type": "connecting",
                    "title": "Connecting the Dots",
                    "connections": [],
                    "narrative_goal": "Synthesize threads",
                },
                {
                    "id": 3,
                    "type": "other_side",
                    "title": "The Other Side",
                    "counter_claims": [],
                    "narrative_goal": "Present counter-evidence",
                },
                {
                    "id": 4,
                    "type": "assessment",
                    "title": "What We Actually Know",
                    "narrative_goal": "Honest assessment",
                },
            ]

        logger.info(
            "[paper] Outline: '%s' -- %d sections: %s",
            title,
            len(sections),
            [s.get("title", "?") for s in sections],
        )
        self.state.log("paper", f"Outline generated: {title}, {len(sections)} sections")

        # ---------------------------------------------------------------
        # Step 2: Write hook
        # ---------------------------------------------------------------
        self.emit_sse(
            {
                "type": "status",
                "content": "Writing opening hook...",
                "subtask_done": 1,
                "subtask_total": 6,
            }
        )

        hook = await self._write_hook(title, all_claims, settings)
        logger.info("[paper] Hook: %d chars", len(hook))

        # ---------------------------------------------------------------
        # Step 3: Write investigation sections in parallel
        # ---------------------------------------------------------------
        investigation_sections = [s for s in sections if s.get("type") == "investigation"]
        connecting_section = next((s for s in sections if s.get("type") == "connecting"), None)
        other_side_section = next((s for s in sections if s.get("type") == "other_side"), None)

        self.emit_sse(
            {
                "type": "status",
                "content": f"Writing {len(investigation_sections)} investigation sections...",
                "subtask_done": 2,
                "subtask_total": 6,
            }
        )

        section_tasks = [
            self._write_investigation_section(sec, all_claims, ref_map_text, settings)
            for sec in investigation_sections
        ]
        section_results = await asyncio.gather(*section_tasks)

        for sec_title, content in section_results:
            logger.info("[paper] Section '%s': %d chars", sec_title, len(content))

        # ---------------------------------------------------------------
        # Step 4: Write Connecting the Dots + The Other Side + Assessment
        # (all independent — run in parallel)
        # ---------------------------------------------------------------
        self.emit_sse(
            {
                "type": "status",
                "content": "Writing cross-angle analysis...",
                "subtask_done": 3,
                "subtask_total": 6,
            }
        )

        connecting_task = self._write_connecting_section(
            connecting_section,
            all_claims,
            ref_map_text,
            sid_to_num,
            settings,
        )
        other_side_task = self._write_other_side_section(
            other_side_section,
            all_claims,
            ref_map_text,
            settings,
        )
        assessment_task = self._write_assessment(all_claims, settings)

        connecting_prose, other_side_prose, assessment = await asyncio.gather(
            connecting_task, other_side_task, assessment_task
        )
        logger.info(
            "[paper] Connecting: %d chars, Other Side: %d chars, Assessment: %d chars",
            len(connecting_prose),
            len(other_side_prose),
            len(assessment),
        )

        # ---------------------------------------------------------------
        # Step 6: Assemble paper
        # ---------------------------------------------------------------
        paper_parts = [f"# {title}\n"]
        paper_parts.append(hook)

        for sec_title, content in section_results:
            if content:
                paper_parts.append(f"## {sec_title}\n\n{content}")

        if connecting_prose:
            paper_parts.append(f"## Connecting the Dots\n\n{connecting_prose}")

        if other_side_prose:
            paper_parts.append(f"## The Other Side\n\n{other_side_prose}")

        paper_parts.append(f"## What We Actually Know\n\n{assessment}")

        raw_paper = "\n\n".join(paper_parts)

        # Clean LLM artifacts
        raw_paper = re.sub(r"\s*---\s*$", "", raw_paper, flags=re.MULTILINE)
        raw_paper = re.sub(r"^\s*---\s*$", "", raw_paper, flags=re.MULTILINE)
        raw_paper = re.sub(r"([^\n])\s*(## )", r"\1\n\n\2", raw_paper)
        raw_paper = re.sub(r" +([.,;])", r"\1", raw_paper)
        raw_paper = re.sub(r"  +", " ", raw_paper)

        self.state.paper_text = raw_paper

        # ---------------------------------------------------------------
        # Step 7: Citation verification
        # ---------------------------------------------------------------
        self.emit_sse(
            {
                "type": "status",
                "content": "Verifying every citation against its source...",
                "subtask_done": 5,
                "subtask_total": 6,
            }
        )

        from pipeline.lyra.citation_verifier import verify_all_citations

        verify_sources = []
        for sid, num in sorted(sid_to_num.items(), key=lambda kv: kv[1]):
            source = self.state.registry.get_reference(sid)
            if source:
                verify_sources.append(
                    {
                        "citation": num,
                        "label": source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                    }
                )

        async with self.semaphore:
            self.state.paper_text = await verify_all_citations(
                self.state.paper_text,
                verify_sources,
                settings=settings,
            )

        # ---------------------------------------------------------------
        # Step 7.5: Finalize references — renumber [N] markers to contiguous
        # [1..M] by first-occurrence order, and populate the registry with
        # only the sources that actually survived verification. This is what
        # prevents ghost references in the published bibliography.
        # ---------------------------------------------------------------
        from pipeline.lyra.theo_citations import audit_citations, finalize_references

        self.state.paper_text, sid_to_num = finalize_references(
            self.state.paper_text,
            sid_to_num,
            self.state.registry,
        )

        # ---------------------------------------------------------------
        # Step 8: Citation audit (runs on finalized [1..M] numbering)
        # ---------------------------------------------------------------
        self.state.audit_result = audit_citations(
            self.state.paper_text,
            self.state.registry,
        )

        # ---------------------------------------------------------------
        # Step 8b: Coherence pass — detect cross-section contradictions +
        # verify every title-term phrase appears in the body.
        # ---------------------------------------------------------------
        # Extract title early so coherence_pass can use it.
        _title_match = re.search(r"^#\s+(.+)$", self.state.paper_text, re.MULTILINE)
        _coherence_title = _title_match.group(1).strip() if _title_match else self.state.question

        from pipeline.lyra import coherence_pass

        async def _coh_llm(sys_prompt, usr, max_tok, s, temp):
            return await asyncio.to_thread(
                minimax_chat_anthropic, sys_prompt, usr, max_tok, s, temperature=temp
            )

        self.state.coherence_result = await coherence_pass.run_coherence_pass(
            title=_coherence_title,
            body=self.state.paper_text,
            llm_call=_coh_llm,
            settings=settings,
        )
        self.state.llm_call_count += 1

        # ---------------------------------------------------------------
        # Step 9: Append references list
        # ---------------------------------------------------------------
        refs_md = self.state.registry.format_references_list()
        if refs_md:
            self.state.paper_text += f"\n\n## References\n\n{refs_md}"

        # ---------------------------------------------------------------
        # Step 10: Extract title
        # ---------------------------------------------------------------
        title_match = re.search(r"^#\s+(.+)$", self.state.paper_text, re.MULTILINE)
        self.state.paper_title = (
            title_match.group(1).strip() if title_match else self.state.question
        )

        # ---------------------------------------------------------------
        # Step 11: Generate card description
        # ---------------------------------------------------------------
        # Pass opener AND conclusion so the card describes what the paper
        # concludes, not just the provocative question it opened with. The
        # references section is stripped so the LLM doesn't waste budget on
        # citation lists.
        _paper_for_card = self.state.paper_text
        _refs_idx = _paper_for_card.find("\n## References")
        if _refs_idx > 0:
            _paper_for_card = _paper_for_card[:_refs_idx]
        _opener = _paper_for_card[:2500]
        _conclusion = _paper_for_card[-4500:] if len(_paper_for_card) > 7000 else ""
        card_system = (
            "Write a 1-3 sentence description of this research paper for a card "
            "preview. Describe what the paper concludes — what it argues is true "
            "— not what it opens by asking. If the paper argues against a "
            "hypothesis the user proposed, say so plainly. Be specific. "
            "No citations, no markdown. Plain text only."
        )
        if _conclusion:
            card_input = (
                f"## Title\n\n{self.state.paper_title}\n\n"
                f"## Opening (first ~500 words)\n\n{_opener}\n\n"
                f"## Conclusion (last ~1500 words)\n\n{_conclusion}"
            )
        else:
            card_input = f"## Title\n\n{self.state.paper_title}\n\n## Paper\n\n{_opener}"
        settings = _get_settings()
        async with self.semaphore:
            # 1024 total budget: ~100 tokens of output prose plus headroom for
            # M2.7's interleaved thinking. The previous 256 was routinely eaten
            # by the reasoning chain, leaving card descriptions empty/truncated.
            self.state.card_description = await asyncio.to_thread(
                minimax_chat_anthropic,
                card_system,
                card_input,
                1024,
                settings,
                temperature=settings.temperature_narrative,
            )
        self.state.llm_call_count += 1

        word_count = len(self.state.paper_text.split())
        total_citations = self.state.audit_result.get("total_citations", 0)
        total_references = self.state.audit_result.get("total_references", 0)
        audit_passed = self.state.audit_result.get("passed", False)

        self.state.log(
            "paper",
            f"Paper assembled: {word_count} words, {total_citations} citations, "
            f"{total_references} references, audit {'passed' if audit_passed else 'failed'}",
            word_count=word_count,
            total_citations=total_citations,
            total_references=total_references,
        )

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "paper_assembly",
                "status": "done",
                "meta": {
                    "title": self.state.paper_title,
                    "audit_passed": audit_passed,
                    "total_citations": total_citations,
                    "total_references": total_references,
                    "word_count": word_count,
                    "llm_calls": self.state.llm_call_count,
                },
            }
        )

        await self.bus.emit(PaperReady())

    # ===================================================================
    # Reference map + claims
    # ===================================================================

    def _build_reference_map(self) -> tuple[dict[str, int], str, dict[str, list[dict]]]:
        """Build a WORKING sid_to_num mapping used only for prompt construction.

        Does NOT call registry.assign_reference_number() — that now happens in
        finalize_references() after verification, so the published references
        list contains only sources actually cited in prose (no ghosts).

        Numbering here is stable within a single pipeline run (sorted by sid)
        so prompts see consistent [N] markers across sections.

        Returns (working_sid_to_num, ref_map_text, claims_by_angle).
        """
        # Collect all source_ids from registry claims
        all_source_ids: set[str] = set()
        for claim in self.state.registry.claims:
            all_source_ids.update(claim.source_ids)

        # Also from synthesis
        for claim_data in self.state.synthesis.get("consensus_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for claim_data in self.state.synthesis.get("contested_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for insight in self.state.synthesis.get("unique_insights", []):
            all_source_ids.update(insight.get("source_ids", []))

        # Also from debate results
        for challenge in self.state.debate_result.get("challenges", []):
            all_source_ids.update(challenge.get("source_ids", []))
        for defense in self.state.debate_result.get("defenses", []):
            all_source_ids.update(defense.get("source_ids", []))

        # Also from moderated results
        for claim_data in self.state.moderated_result.get("final_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for claim_data in self.state.moderated_result.get("revised_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))

        # Also from angle findings
        for angle in self.state.angles:
            for finding in angle.findings:
                all_source_ids.update(finding.get("source_ids", []))

        # Assign WORKING reference numbers (stable within this run, not registered
        # on the CitationRegistry). finalize_references() will re-number these to
        # contiguous [1..M] based on actual first-citation order after verification.
        ref_map_lines: list[str] = []
        sid_to_num: dict[str, int] = {}
        working_num = 1
        for sid in sorted(all_source_ids):
            source = self.state.registry.get_reference(sid)
            if source is None:
                continue
            sid_to_num[sid] = working_num
            ref_map_lines.append(f"[{working_num}] {source.title} -- {source.url}")
            working_num += 1

        ref_map_text = "\n".join(ref_map_lines) if ref_map_lines else "(no references)"

        # Build per-angle claims
        claims_by_angle: dict[str, list[dict]] = {}
        for angle in self.state.angles:
            claims_by_angle[angle.id] = angle.findings

        return sid_to_num, ref_map_text, claims_by_angle

    def _collect_all_claims(self, sid_to_num: dict[str, int]) -> list[dict]:
        """Collect all claims into a flat list with citation strings.

        Only collects from synthesis output (consensus + contested + unique)
        plus moderated results. Registry.claims are the raw specialist inputs
        that synthesis already processed, so including them would double-count.

        Each entry: {"claim": str, "citations": str, "confidence": str,
                     "source_ids": list[str], "type": str}
        """
        claims: list[dict] = []

        # From synthesis consensus
        for claim_data in self.state.synthesis.get("consensus_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": claim_data.get("claim", ""),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "medium"),
                    "source_ids": sids,
                    "type": "consensus",
                }
            )

        # From synthesis contested
        for claim_data in self.state.synthesis.get("contested_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": claim_data.get("claim", ""),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "low"),
                    "source_ids": sids,
                    "type": "contested",
                }
            )

        # From synthesis unique insights
        for insight in self.state.synthesis.get("unique_insights", []):
            sids = insight.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": insight.get("insight", insight.get("claim", "")),
                    "citations": cites,
                    "confidence": insight.get("confidence", "medium"),
                    "source_ids": sids,
                    "type": "unique",
                }
            )

        # From moderated final claims
        for claim_data in self.state.moderated_result.get("final_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": claim_data.get("claim", ""),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "medium"),
                    "source_ids": sids,
                    "type": "moderated_final",
                }
            )

        # From moderated revised claims
        for claim_data in self.state.moderated_result.get("revised_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": claim_data.get("revised", claim_data.get("original", "")),
                    "citations": cites,
                    "confidence": "medium",
                    "source_ids": sids,
                    "type": "moderated_revised",
                    "notes": claim_data.get("reason", ""),
                }
            )

        # From moderated speculative claims
        for claim_data in self.state.moderated_result.get("speculative_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append(
                {
                    "claim": claim_data.get("claim", ""),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "low"),
                    "source_ids": sids,
                    "type": "moderated_speculative",
                    "notes": claim_data.get("notes", ""),
                }
            )

        return claims

    # ===================================================================
    # LLM calls
    # ===================================================================

    async def _llm_call(self, system: str, user_msg: str, max_tokens: int, settings) -> str:
        """Async LLM call with semaphore gating and call count tracking.

        All paper narrative prose (hook, outline, investigation sections, audit retries)
        flows through this wrapper at the narrative temperature — warmer than the rest
        of the pipeline so the Why Files prose has voice.
        """
        async with self.semaphore:
            result = await asyncio.to_thread(
                minimax_chat_anthropic,
                system,
                user_msg,
                max_tokens,
                settings,
                temperature=settings.temperature_narrative,
            )
        self.state.llm_call_count += 1
        return result

    async def _audit_and_retry_section(
        self,
        section_title: str,
        prose: str,
        prompt: str,
        user_msg: str,
        max_tokens: int,
        settings,
    ) -> str:
        """Check citation density in prose. If sparse, retry once with stronger instructions."""
        if not prose:
            return prose

        words = len(prose.split())
        citations = len(re.findall(r"\[\d+\]", prose))

        if words < 100 or citations >= words / 200:
            # Adequate: at least 1 citation per 200 words
            return prose

        logger.warning(
            "[paper] Section '%s' has %d citations in %d words (%.0f words/citation) — retrying",
            section_title,
            citations,
            words,
            words / max(citations, 1),
        )

        retry_prefix = (
            "IMPORTANT: Your previous draft had too few inline citations. "
            "Every factual claim MUST include its [N] marker from the input claims. "
            "Cite generously — at least one citation per 1-2 sentences that state facts. "
            "Do NOT omit citation markers.\n\n"
        )
        retry_msg = retry_prefix + user_msg

        raw = await self._llm_call(prompt, retry_msg, max_tokens, settings)
        retried = raw.strip()

        retry_citations = len(re.findall(r"\[\d+\]", retried))
        if retry_citations > citations:
            logger.info(
                "[paper] Section '%s' retry improved citations: %d -> %d",
                section_title,
                citations,
                retry_citations,
            )
            return retried

        return prose  # retry didn't help, keep original

    async def _generate_outline(self, sid_to_num: dict[str, int], settings) -> dict:
        """Generate the paper outline from synthesis, debate, and angle data."""
        outline_prompt = (PROMPTS_DIR / "v2_paper_outline.txt").read_text(encoding="utf-8")

        # Build angle summaries with IDs for angle-based routing
        angle_summaries = []
        for angle in self.state.angles:
            findings_text = (
                "\n".join(f"- {f.get('claim', f.get('finding', ''))}" for f in angle.findings)
                if angle.findings
                else "No findings"
            )
            angle_summaries.append(
                f"### Angle: {angle.topic} (id={angle.id})\n"
                f"{angle.description}\n"
                f"Findings ({len(angle.findings)}):\n{findings_text}"
            )

        # Build angle ID reference list for the LLM
        angle_id_ref = "\n".join(
            f"- {angle.id}: {angle.topic} ({len(angle.findings)} findings)"
            for angle in self.state.angles
        )

        # Cross-angle connections
        connections_text = ""
        if self.state.cross_angle_connections:
            connections_text = json.dumps(self.state.cross_angle_connections, indent=2)

        # Synthesis summary
        synthesis_text = (
            json.dumps(self.state.synthesis, indent=2) if self.state.synthesis else "{}"
        )

        # Debate results
        debate_text = ""
        if self.state.debate_result:
            challenges = self.state.debate_result.get("challenges", [])
            defenses = self.state.debate_result.get("defenses", [])
            debate_text = (
                f"Debate rounds: {self.state.debate_result.get('rounds', 0)}\n"
                f"Challenges ({len(challenges)}):\n"
                + "\n".join(f"- {c.get('claim', c.get('challenge', ''))}" for c in challenges[:20])
                + f"\n\nDefenses ({len(defenses)}):\n"
                + "\n".join(f"- {d.get('defense', d.get('response', ''))}" for d in defenses[:20])
            )

        # Moderated results
        moderated_text = ""
        if self.state.moderated_result:
            final_ct = len(self.state.moderated_result.get("final_claims", []))
            revised_ct = len(self.state.moderated_result.get("revised_claims", []))
            dropped_ct = len(self.state.moderated_result.get("dropped_claims", []))
            moderated_text = (
                f"Moderated: {final_ct} final, {revised_ct} revised, {dropped_ct} dropped\n"
            )
            for rc in self.state.moderated_result.get("revised_claims", []):
                moderated_text += (
                    f"- Revised: {rc.get('original', '')} -> {rc.get('revised', '')}\n"
                )
            for dc in self.state.moderated_result.get("dropped_claims", []):
                moderated_text += f"- Dropped: {dc.get('claim', '')} ({dc.get('reason', '')})\n"

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Available angle IDs\n\n{angle_id_ref}\n\n"
            f"## Angle summaries\n\n{'---'.join(angle_summaries)}\n\n"
            f"## Cross-angle connections\n\n{connections_text or 'None detected'}\n\n"
            f"## Synthesis\n\n{synthesis_text}\n\n"
            f"## Debate results\n\n{debate_text or 'No debate conducted'}\n\n"
            f"## Moderator results\n\n{moderated_text or 'No moderation conducted'}\n"
        )

        raw = await self._llm_call(outline_prompt, user_msg, 4096, settings)
        return self._parse_json(raw)

    async def _write_hook(self, title: str, claims: list[dict], settings) -> str:
        """Write the opening hook paragraph(s)."""
        hook_prompt = (PROMPTS_DIR / "v2_paper_hook.txt").read_text(encoding="utf-8")

        # Select the most interesting findings for the hook
        key_findings = []
        for c in claims:
            if c.get("confidence") == "high":
                key_findings.append(c["claim"])
        if len(key_findings) < 3:
            for c in claims:
                if c.get("confidence") == "medium" and c["claim"] not in key_findings:
                    key_findings.append(c["claim"])
                if len(key_findings) >= 8:
                    break

        findings_text = "\n".join(f"- {f}" for f in key_findings[:10])

        user_msg = (
            f"## Topic\n\n{self.state.question}\n\n"
            f"## Paper title\n\n{title}\n\n"
            f"## Key findings\n\n{findings_text}\n"
        )

        # 4096 budget: hook is usually 300-500 output tokens, but M2.7 thinking
        # can consume 2K+ before the prose starts. 2048 was too tight.
        raw = await self._llm_call(hook_prompt, user_msg, 4096, settings)
        hook = raw.strip()
        hook = await self._run_hallucination_gate(hook, findings_text, settings)
        return hook

    async def _write_investigation_section(
        self,
        section: dict,
        all_claims: list[dict],
        ref_map_text: str,
        settings,
    ) -> tuple[str, str]:
        """Write a single investigation section. Returns (title, prose)."""
        section_prompt = (PROMPTS_DIR / "v2_paper_section.txt").read_text(encoding="utf-8")
        sec_title = section.get("title", "Untitled")
        narrative_goal = section.get("narrative_goal", "")

        # Collect claims from the assigned angles
        angle_ids = section.get("angle_ids", [])
        matched_claims = self._collect_claims_for_angles(angle_ids, all_claims)

        if not matched_claims:
            logger.warning(
                "[paper] Section '%s' has no claims from angles %s", sec_title, angle_ids
            )
            return sec_title, ""

        # Format claims for the prompt
        claims_text = self._format_claims_for_prompt(matched_claims)

        # Build optional image catalog for this section (paper-writer awareness)
        image_catalog_text = ""
        if getattr(settings, "paper_writer_sees_images", False):
            image_catalog_text = self._build_image_catalog_text(angle_ids)

        user_msg = (
            f"## Section: {sec_title}\n"
            f"Narrative goal: {narrative_goal}\n\n"
            f"## Claims for this section\n\n{claims_text}\n\n"
            + (f"## Available images\n\n{image_catalog_text}\n\n" if image_catalog_text else "")
            + f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._audit_and_retry_section(
            sec_title,
            raw.strip(),
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )

        prose = await self._cite_or_delete_repair(
            prose, section_prompt, user_msg, claims_text, settings, sec_title
        )
        prose = await self._run_hallucination_gate(prose, claims_text, settings)
        return sec_title, prose

    async def _cite_or_delete_repair(
        self,
        prose: str,
        section_prompt: str,
        user_msg: str,
        claims_text: str,
        settings,
        sec_title: str,
    ) -> str:
        """Up to two-stage repair: whole-section, then per-paragraph surgical.

        Stage 1 (whole-section): the writer rewrites the whole section if the
        uncited ratio exceeds 5%. Repair prompt repeats the rules and the
        original claim pack.

        Stage 2 (per-paragraph): if uncited paragraphs survive the first pass,
        list them with their indices and ask the writer to either inject an
        [N] marker from the pack or delete the paragraph entirely. This
        surgical loop is far cheaper than another whole-section regeneration
        and converges quickly because each decision is local.
        """
        # Stage 1 — whole-section
        ratio = self._uncited_ratio(prose)
        if ratio > 0.05:
            repair_user_msg = (
                user_msg + f"\n\nYour previous draft had {ratio:.0%} uncited factual paragraphs. "
                "Rewrite so every factual paragraph carries an [N] marker from the claim pack. "
                "Delete any sentence you cannot cite. Connective prose without facts is allowed "
                "only if it is shorter than one sentence — otherwise carry a marker."
            )
            repair_raw = await self._llm_call(
                section_prompt,
                repair_user_msg,
                self.state.config.max_tokens_per_call,
                settings,
            )
            prose = repair_raw.strip()
            logger.info(
                "[paper] Stage-1 repair for section '%s' — uncited %.0f%% -> rewriting",
                sec_title,
                ratio * 100,
            )

        # Stage 2 — per-paragraph surgical pass
        paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
        uncited_indices: list[int] = []
        for i, p in enumerate(paragraphs):
            if len(p) > 50 and not p.startswith("#") and not re.search(r"\[\d+\]", p):
                uncited_indices.append(i)

        if not uncited_indices:
            return prose

        listing = "\n".join(
            f"PARAGRAPH {idx}: {paragraphs[idx][:300]}"
            + ("..." if len(paragraphs[idx]) > 300 else "")
            for idx in uncited_indices
        )
        surgical_system = (
            "You are repairing a research paper section. Below are paragraphs that "
            "currently have no [N] citation marker. For each, either:\n"
            "  KEEP — add the right [N] marker(s) from the claims pack at the end of "
            "the relevant sentence and return the rewritten paragraph.\n"
            "  DELETE — return the literal string `<<DELETE>>` if no claim in the pack "
            "can support the paragraph.\n\n"
            "Output format (one block per paragraph, separated by blank lines):\n"
            "PARAGRAPH <idx>:\n<rewritten paragraph or <<DELETE>>>\n\n"
            "Do not invent citations. Use only [N] markers that appear verbatim in the claims pack."
        )
        surgical_user = (
            f"## Claims pack\n\n{claims_text}\n\n## Uncited paragraphs to repair\n\n{listing}\n"
        )
        try:
            decisions = await self._llm_call(
                surgical_system,
                surgical_user,
                self.state.config.max_tokens_per_call,
                settings,
            )
        except Exception as exc:
            logger.warning("[paper] Stage-2 surgical repair LLM failed: %s", exc)
            return prose

        # Parse the decisions and apply them by paragraph index
        block_re = re.compile(
            r"PARAGRAPH\s+(\d+)\s*:\s*\n(.+?)(?=\nPARAGRAPH\s+\d+\s*:|\Z)", re.DOTALL
        )
        edits: dict[int, str] = {}
        for m in block_re.finditer(decisions):
            idx = int(m.group(1))
            replacement = m.group(2).strip()
            if idx in uncited_indices:
                edits[idx] = replacement

        new_paragraphs: list[str] = []
        for i, p in enumerate(paragraphs):
            if i in edits:
                rep = edits[i]
                if rep == "<<DELETE>>" or rep.lower() == "delete":
                    continue  # drop the paragraph
                # Sanity: only keep if the LLM added a marker or shortened the prose
                if re.search(r"\[\d+\]", rep) or len(rep) <= 60:
                    new_paragraphs.append(rep)
                else:
                    # LLM returned prose without a marker — drop instead of leak
                    continue
            else:
                new_paragraphs.append(p)

        repaired = "\n\n".join(new_paragraphs)
        logger.info(
            "[paper] Stage-2 surgical repair for section '%s' — %d uncited paragraphs -> %d after",
            sec_title,
            len(uncited_indices),
            sum(
                1
                for p in repaired.split("\n\n")
                if len(p.strip()) > 50
                and not p.strip().startswith("#")
                and not re.search(r"\[\d+\]", p)
            ),
        )
        return repaired

    async def _run_hallucination_gate(
        self,
        prose: str,
        pack: str,
        settings,
    ) -> str:
        """Extract specifics from prose, verify against pack + sources + question.

        Unsupported specifics trigger the hallucination_gate.repair_prose loop.
        Metrics accumulate on self.state.hallucination_metrics. Returns the
        (possibly-repaired) prose.
        """
        from pipeline.lyra import hallucination_gate

        metrics = getattr(
            self.state,
            "hallucination_metrics",
            {"initial": 0, "final": 0, "retries": 0},
        )

        specs = hallucination_gate.extract_specifics(prose)
        unsupported = hallucination_gate.verify_against_pack(
            specs,
            pack=pack,
            sources=self.state.registry.sources,
            original_question=self.state.question,
        )
        metrics["initial"] += len(unsupported)

        if unsupported:

            async def _llm_call(system, user, max_tokens, s, temperature):
                # _llm_call on the handler is (system, user, max_tokens, settings)
                # without a temperature override. For repair we want deterministic
                # output, so we pass the temperature through minimax_chat_anthropic
                # directly via asyncio.to_thread (same shape as the handler's own
                # _llm_call but with explicit temp).
                return await asyncio.to_thread(
                    minimax_chat_anthropic,
                    system,
                    user,
                    max_tokens,
                    s,
                    temperature=temperature,
                )

            prose, remaining, retries = await hallucination_gate.repair_prose(
                prose,
                unsupported,
                pack=pack,
                sources=self.state.registry.sources,
                original_question=self.state.question,
                llm_call=_llm_call,
                settings=settings,
            )
            metrics["retries"] += retries
            metrics["final"] += len(remaining)
            self.state.llm_call_count += retries
            if remaining:
                logger.info(
                    "[paper] hallucination_gate left %d specifics after %d retries",
                    len(remaining),
                    retries,
                )

        self.state.hallucination_metrics = metrics
        return prose

    async def _write_connecting_section(
        self,
        section: dict | None,
        all_claims: list[dict],
        ref_map_text: str,
        sid_to_num: dict[str, int],
        settings,
    ) -> str:
        """Write the Connecting the Dots section."""
        prompt_path = PROMPTS_DIR / "v2_paper_connecting.txt"
        section_prompt = prompt_path.read_text(encoding="utf-8")

        # Gather cross-angle connections with CONCRETE findings
        connection_lines: list[str] = []
        if self.state.cross_angle_connections:
            for c in self.state.cross_angle_connections:
                from_finding = ""
                to_finding = ""
                if isinstance(c.get("from_angle"), dict):
                    from_finding = c["from_angle"].get("finding", "")
                if isinstance(c.get("to_angle"), dict):
                    to_finding = c["to_angle"].get("finding", "")

                if from_finding and to_finding:
                    connection_lines.append(f"{from_finding} — connects to — {to_finding}")
                elif c.get("description"):
                    connection_lines.append(c["description"])

        if section and section.get("connections") and not connection_lines:
            connection_lines = [str(c) for c in section["connections"]]

        if not connection_lines:
            convergent = self.state.synthesis.get("convergent_findings", [])
            for f in convergent:
                if isinstance(f, dict) and f.get("angles_involved"):
                    angle_findings = [
                        a.get("finding", "") for a in f["angles_involved"] if a.get("finding")
                    ]
                    if angle_findings:
                        connection_lines.append(" — ".join(angle_findings))
                elif isinstance(f, dict):
                    connection_lines.append(f.get("pattern", f.get("finding", str(f))))

        if not connection_lines:
            return ""

        # Build angle summaries with concrete findings + citation markers
        angle_summaries = []
        for angle in self.state.angles:
            top_findings = []
            for f in angle.findings[:5]:
                claim_text = f.get("claim", "")
                sids = f.get("source_ids", [])
                cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
                top_findings.append(f"{claim_text} {cites}" if cites else claim_text)
            angle_summaries.append(
                f"Angle '{angle.topic}':\n" + "\n".join(f"  - {tf}" for tf in top_findings)
            )

        claims_text = "\n".join(f"- {c}" for c in connection_lines)
        angles_text = "\n\n".join(angle_summaries)
        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Angle findings\n\n{angles_text}\n\n"
            f"## Cross-angle connections\n\n{claims_text}\n\n"
            f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._audit_and_retry_section(
            "Connecting the Dots",
            raw.strip(),
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._cite_or_delete_repair(
            prose, section_prompt, user_msg, claims_text, settings, "Connecting the Dots"
        )
        prose = await self._run_hallucination_gate(prose, claims_text, settings)
        return prose

    async def _write_other_side_section(
        self,
        section: dict | None,
        all_claims: list[dict],
        ref_map_text: str,
        settings,
    ) -> str:
        """Write The Other Side section with counter-evidence."""
        # Use dedicated other-side prompt
        prompt_path = PROMPTS_DIR / "v2_paper_otherside.txt"
        section_prompt = prompt_path.read_text(encoding="utf-8")

        # Gather counter-evidence
        counter_claims = []
        if section and section.get("counter_claims"):
            counter_claims = section["counter_claims"]

        # Add contested claims from synthesis
        for c in self.state.synthesis.get("contested_claims", []):
            claim_text = c.get("claim", "")
            counter = c.get("counter_evidence", c.get("challenge", ""))
            if counter:
                counter_claims.append(f"{claim_text} -- Counter: {counter}")
            elif claim_text:
                counter_claims.append(claim_text)

        # Add challenges from debate
        for ch in self.state.debate_result.get("challenges", []):
            challenge_text = ch.get("claim", ch.get("challenge", ""))
            if challenge_text:
                counter_claims.append(challenge_text)

        # Add dropped claims from moderator
        for dc in self.state.moderated_result.get("dropped_claims", []):
            claim_text = dc.get("claim", "")
            reason = dc.get("reason", "")
            if claim_text:
                counter_claims.append(f"{claim_text} -- Dropped: {reason}")

        # Add speculative claims as context — The Other Side should address
        # what mainstream scholarship says about these
        for sc in self.state.moderated_result.get("speculative_claims", []):
            claim_text = sc.get("claim", "")
            if claim_text:
                counter_claims.append(f"Hypothesis claim: {claim_text}")

        if not counter_claims:
            return ""

        claims_text = "\n".join(f"- {c}" for c in counter_claims[:15])
        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Counter-evidence and challenges\n\n{claims_text}\n\n"
            f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._audit_and_retry_section(
            "The Other Side",
            raw.strip(),
            section_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._cite_or_delete_repair(
            prose, section_prompt, user_msg, claims_text, settings, "The Other Side"
        )
        prose = await self._run_hallucination_gate(prose, claims_text, settings)
        return prose

    async def _write_assessment(self, all_claims: list[dict], settings) -> str:
        """Write the What We Actually Know assessment section."""
        assessment_prompt = (PROMPTS_DIR / "v2_paper_assessment.txt").read_text(encoding="utf-8")

        # Categorize full claim dicts (NOT bare strings) by confidence so the
        # [N] citation markers travel into the prompt via _format_claims_for_prompt.
        # Dropping to bare strings was the bug that caused [N - topic] placeholders.
        high_confidence = [c for c in all_claims if c.get("confidence") == "high"]
        medium_confidence = [c for c in all_claims if c.get("confidence") == "medium"]
        low_confidence = [c for c in all_claims if c.get("confidence") == "low"]

        def _format_tier(items: list[dict]) -> str:
            if not items:
                return "None"
            # Cap at 15 per tier so the prompt stays bounded, and reuse the
            # same formatter the other sections use (paper.py:_format_claims_for_prompt)
            return self._format_claims_for_prompt(items[:15])

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Well-documented (high confidence)\n\n{_format_tier(high_confidence)}\n\n"
            f"## Plausible but uncertain (medium confidence)\n\n{_format_tier(medium_confidence)}\n\n"
            f"## Speculative (low confidence)\n\n{_format_tier(low_confidence)}\n"
        )

        # Include open questions from synthesis if available
        open_qs = self.state.synthesis.get("open_questions", [])
        if open_qs:
            user_msg += "\n\n## Open questions from synthesis\n\n" + "\n".join(
                f"- {q}" for q in open_qs
            )

        raw = await self._llm_call(
            assessment_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        prose = await self._audit_and_retry_section(
            "What We Actually Know",
            raw.strip(),
            assessment_prompt,
            user_msg,
            self.state.config.max_tokens_per_call,
            settings,
        )
        # Build a pack for the hallucination gate + surgical repair from all
        # three confidence tiers (the assessment cites across all of them).
        _assessment_pack = "\n".join(
            [
                _format_tier(high_confidence),
                _format_tier(medium_confidence),
                _format_tier(low_confidence),
            ]
        )
        prose = await self._cite_or_delete_repair(
            prose,
            assessment_prompt,
            user_msg,
            _assessment_pack,
            settings,
            "What We Actually Know",
        )
        prose = await self._run_hallucination_gate(prose, _assessment_pack, settings)
        return prose

    # ===================================================================
    # Helpers
    # ===================================================================

    def _build_image_catalog_text(self, angle_ids: list[str]) -> str:
        """Build a compact text catalog of available images for these angles.

        Format per line: `[[IMG:candidate_id]] Title — source (license)`
        The writer can embed `[[IMG:candidate_id]]` anywhere in prose to pin an
        image at that location. If the writer doesn't use any, PIH falls back
        to auto-selection for the section.
        """
        import hashlib

        pool = getattr(self.state, "image_candidate_pool", {}) or {}
        if not pool:
            return ""
        lines: list[str] = []
        angle_set = {str(a) for a in angle_ids}
        for angle_id, candidates in pool.items():
            if angle_set and angle_id not in angle_set:
                continue
            for c in candidates[:5]:  # cap so prompt stays bounded
                cid = c.get("url", "")
                title = (c.get("title") or "")[:80]
                source = c.get("source") or ""
                lic = c.get("license") or ""
                if not cid or not title:
                    continue
                # Use a stable short id — hash of URL. Must be reversible via pool lookup.
                short = hashlib.sha1(cid.encode()).hexdigest()[:10]
                lines.append(f"[[IMG:{short}]] {title} — {source} ({lic})")
        if not lines:
            return ""
        return (
            "You MAY insert a marker `[[IMG:xxx]]` from the list below at the point "
            "in prose where the image would strengthen the argument. Only pick an image "
            "that directly illustrates the sentence it follows. Leave the marker "
            "alone (don't paraphrase). You may also ignore the list entirely.\n\n"
            + "\n".join(lines[:15])  # max 15 candidates surfaced
        )

    def _collect_claims_for_angles(
        self,
        angle_ids: list[str],
        all_claims: list[dict],
    ) -> list[dict]:
        """Collect claims from the specified angles' findings.

        Looks up angle findings directly from state, then enriches with
        citation info from all_claims where possible.
        """
        # Normalize angle_ids to strings (LLM may return ints)
        str_ids = {str(aid) for aid in angle_ids}

        # Collect findings from matching angles
        angle_findings: list[dict] = []
        for angle in self.state.angles:
            if angle.id in str_ids:
                angle_findings.extend(angle.findings)

        if not angle_findings:
            return []

        # Build lookup from all_claims for citation enrichment
        claim_lookup: dict[str, dict] = {}
        for c in all_claims:
            key = c.get("claim", "").lower().strip()
            if key:
                claim_lookup[key] = c

        # Match angle findings to enriched claims. Claims without citation
        # backing are dropped; bare-citation claims leak into uncited prose.
        matched: list[dict] = []
        for finding in angle_findings:
            claim_text = finding.get("claim", "").strip()
            if not claim_text:
                continue
            key = claim_text.lower().strip()
            if key in claim_lookup:
                matched.append(claim_lookup[key])
                continue

            source_ids = finding.get("source_ids") or []
            if not source_ids:
                continue  # no support for this finding — drop it

            # Synthesize citations from source_ids via registry reference numbers
            ref_nums: list[int] = []
            for sid in source_ids:
                num = self.state.registry.reference_numbers.get(sid)
                if num is None:
                    num = self.state.registry.assign_reference_number(sid)
                ref_nums.append(num)
            if not ref_nums:
                continue  # none of the source_ids resolved — drop

            citations = " ".join(f"[{n}]" for n in ref_nums)
            matched.append(
                {
                    "claim": claim_text,
                    "citations": citations,
                    "confidence": finding.get("confidence", "medium"),
                    "source_ids": source_ids,
                }
            )

        return matched

    @staticmethod
    def _uncited_ratio(prose: str) -> float:
        """Fraction of factual paragraphs (>50 chars, non-heading) without an [N] marker."""
        paragraphs = [
            p.strip()
            for p in prose.split("\n\n")
            if p.strip() and len(p.strip()) > 50 and not p.strip().startswith("#")
        ]
        if not paragraphs:
            return 0.0
        uncited = sum(1 for p in paragraphs if not re.search(r"\[\d+\]", p))
        return uncited / len(paragraphs)

    @staticmethod
    def _format_claims_for_prompt(claims: list[dict]) -> str:
        """Format claims with inline [N] markers for LLM prompts.

        Embeds citation markers directly in the claim text so the LLM
        can carry them into its prose naturally. Matches the journal
        pipeline approach.
        """
        lines: list[str] = []
        for i, c in enumerate(claims):
            cites = c.get("citations", "")
            if not cites.strip():
                continue  # refuse to format claims without backing (C2 guard)
            conf = c.get("confidence", "medium")
            claim_text = c.get("claim", "")
            notes = c.get("notes", "")
            # Embed [N] markers at the end of the claim text
            line = f"{i}. [{conf}] {claim_text} {cites}"
            if notes:
                line += f"\n   Notes: {notes}"
            lines.append(line)
        return "\n\n".join(lines)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse JSON from LLM response, stripping markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("[paper] Failed to parse JSON: %s", cleaned[:200])
            return {}
