"""Why Files narrative paper assembly."""

import asyncio
import json
import logging
import re
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import DebateComplete, PaperReady
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Stop words for keyword-overlap matching during mechanical citation insertion
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "to",
    "and", "that", "this", "for", "with", "from", "has", "have", "had",
    "been", "not", "but", "its", "also", "by", "on", "as", "at", "or",
    "it", "be", "can", "may", "would", "could", "should", "will",
})


class PaperHandler(BaseHandler):
    """Assembles the final research paper using the Why Files narrative structure.

    Triggered by DebateComplete. Produces a complete markdown paper with:
    - Hook (vivid opening)
    - Investigation sections (per angle, parallel)
    - Connecting the Dots (cross-angle synthesis)
    - The Other Side (counter-evidence)
    - What We Actually Know (honest assessment)
    - Verified citations with references list
    """

    def register(self):
        self.bus.on(DebateComplete, self._on_debate_complete)

    async def _on_debate_complete(self, event: DebateComplete):
        self.state.phase = ResearchPhase.WRITING
        self.emit_sse({
            "type": "pipeline", "stage": "paper_assembly", "status": "start",
            "meta": {"subtask_total": 6},
        })
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
        self.emit_sse({
            "type": "status",
            "content": "Planning paper structure...",
            "subtask_done": 0, "subtask_total": 6,
        })

        outline = await self._generate_outline(sid_to_num, settings)
        title = outline.get("title", self.state.question[:60])
        sections = outline.get("sections", [])

        if not sections:
            # Minimal fallback structure
            sections = [
                {
                    "id": 1, "type": "investigation",
                    "title": "Findings",
                    "assigned_claims": [c["claim"] for c in all_claims[:20]],
                    "narrative_goal": "Present the evidence",
                },
                {
                    "id": 2, "type": "connecting",
                    "title": "Connecting the Dots",
                    "connections": [],
                    "narrative_goal": "Synthesize threads",
                },
                {
                    "id": 3, "type": "other_side",
                    "title": "The Other Side",
                    "counter_claims": [],
                    "narrative_goal": "Present counter-evidence",
                },
                {
                    "id": 4, "type": "assessment",
                    "title": "What We Actually Know",
                    "narrative_goal": "Honest assessment",
                },
            ]

        logger.info(
            "[paper] Outline: '%s' — %d sections: %s",
            title, len(sections),
            [s.get("title", "?") for s in sections],
        )
        self.state.log("paper", f"Outline generated: {title}, {len(sections)} sections")

        # ---------------------------------------------------------------
        # Step 2: Write hook
        # ---------------------------------------------------------------
        self.emit_sse({
            "type": "status",
            "content": "Writing opening hook...",
            "subtask_done": 1, "subtask_total": 6,
        })

        hook = await self._write_hook(title, all_claims, settings)
        logger.info("[paper] Hook: %d chars", len(hook))

        # ---------------------------------------------------------------
        # Step 3: Write investigation sections in parallel
        # ---------------------------------------------------------------
        investigation_sections = [s for s in sections if s.get("type") == "investigation"]
        connecting_section = next((s for s in sections if s.get("type") == "connecting"), None)
        other_side_section = next((s for s in sections if s.get("type") == "other_side"), None)

        self.emit_sse({
            "type": "status",
            "content": f"Writing {len(investigation_sections)} investigation sections...",
            "subtask_done": 2, "subtask_total": 6,
        })

        section_tasks = [
            self._write_investigation_section(sec, all_claims, ref_map_text, settings)
            for sec in investigation_sections
        ]
        section_results = await asyncio.gather(*section_tasks)

        for sec_title, content in section_results:
            logger.info("[paper] Section '%s': %d chars", sec_title, len(content))

        # ---------------------------------------------------------------
        # Step 4: Write Connecting the Dots + The Other Side
        # ---------------------------------------------------------------
        self.emit_sse({
            "type": "status",
            "content": "Writing cross-angle analysis...",
            "subtask_done": 3, "subtask_total": 6,
        })

        connecting_prose = await self._write_connecting_section(
            connecting_section, all_claims, ref_map_text, settings,
        )
        other_side_prose = await self._write_other_side_section(
            other_side_section, all_claims, ref_map_text, settings,
        )

        # ---------------------------------------------------------------
        # Step 5: Write assessment
        # ---------------------------------------------------------------
        self.emit_sse({
            "type": "status",
            "content": "Writing honest assessment...",
            "subtask_done": 4, "subtask_total": 6,
        })

        assessment = await self._write_assessment(all_claims, settings)
        logger.info("[paper] Assessment: %d chars", len(assessment))

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

        # Strip any [N] markers the LLM snuck in, then insert mechanically
        raw_paper = re.sub(r"\[\d+\]", "", raw_paper)
        raw_paper = self._insert_citations_mechanically(raw_paper, all_claims, sid_to_num)
        raw_paper = re.sub(r" +([.,;])", r"\1", raw_paper)
        raw_paper = re.sub(r"  +", " ", raw_paper)

        self.state.paper_text = raw_paper

        # ---------------------------------------------------------------
        # Step 7: Citation verification
        # ---------------------------------------------------------------
        self.emit_sse({
            "type": "status",
            "content": "Verifying every citation against its source...",
            "subtask_done": 5, "subtask_total": 6,
        })

        from pipeline.lyra.citation_verifier import verify_all_citations

        verify_sources = []
        for sid, num in sorted(sid_to_num.items(), key=lambda kv: kv[1]):
            source = self.state.registry.get_reference(sid)
            if source:
                verify_sources.append({
                    "citation": num,
                    "label": source.title,
                    "url": source.url,
                    "snippet": source.snippet,
                })

        self.state.paper_text = verify_all_citations(
            self.state.paper_text, verify_sources, settings=settings,
        )

        # ---------------------------------------------------------------
        # Step 8: Citation audit
        # ---------------------------------------------------------------
        from pipeline.lyra.theo_citations import audit_citations

        self.state.audit_result = audit_citations(
            self.state.paper_text, self.state.registry,
        )

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
        self.state.paper_title = title_match.group(1).strip() if title_match else self.state.question

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

        self.emit_sse({
            "type": "pipeline", "stage": "paper_assembly", "status": "done",
            "meta": {
                "title": self.state.paper_title,
                "audit_passed": audit_passed,
                "total_citations": total_citations,
                "total_references": total_references,
                "word_count": word_count,
                "llm_calls": self.state.llm_call_count,
            },
        })

        await self.bus.emit(PaperReady())

    # ===================================================================
    # Reference map + claims
    # ===================================================================

    def _build_reference_map(self) -> tuple[dict[str, int], str, dict[str, list[dict]]]:
        """Build sid_to_num mapping, ref_map_text, and per-angle claims.

        Returns (sid_to_num, ref_map_text, claims_by_angle).
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

        # Also from angle findings
        for angle in self.state.angles:
            for finding in angle.findings:
                all_source_ids.update(finding.get("source_ids", []))

        # Assign reference numbers
        ref_map_lines: list[str] = []
        sid_to_num: dict[str, int] = {}
        for sid in sorted(all_source_ids):
            source = self.state.registry.get_reference(sid)
            if source is None:
                continue
            num = self.state.registry.assign_reference_number(sid)
            sid_to_num[sid] = num
            ref_map_lines.append(f"[{num}] {source.title} -- {source.url}")

        ref_map_text = "\n".join(ref_map_lines) if ref_map_lines else "(no references)"

        # Build per-angle claims
        claims_by_angle: dict[str, list[dict]] = {}
        for angle in self.state.angles:
            claims_by_angle[angle.id] = angle.findings

        return sid_to_num, ref_map_text, claims_by_angle

    def _collect_all_claims(self, sid_to_num: dict[str, int]) -> list[dict]:
        """Collect all claims into a flat list with citation strings.

        Each entry: {"claim": str, "citations": str, "confidence": str,
                     "source_ids": list[str], "type": str}
        """
        claims: list[dict] = []

        # From synthesis consensus
        for claim_data in self.state.synthesis.get("consensus_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append({
                "claim": claim_data.get("claim", ""),
                "citations": cites,
                "confidence": claim_data.get("confidence", "medium"),
                "source_ids": sids,
                "type": "consensus",
            })

        # From synthesis contested
        for claim_data in self.state.synthesis.get("contested_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append({
                "claim": claim_data.get("claim", ""),
                "citations": cites,
                "confidence": claim_data.get("confidence", "low"),
                "source_ids": sids,
                "type": "contested",
            })

        # From synthesis unique insights
        for insight in self.state.synthesis.get("unique_insights", []):
            sids = insight.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append({
                "claim": insight.get("insight", insight.get("claim", "")),
                "citations": cites,
                "confidence": insight.get("confidence", "medium"),
                "source_ids": sids,
                "type": "unique",
            })

        # From registry claims (specialist-level)
        for claim in self.state.registry.claims:
            sids = claim.source_ids
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims.append({
                "claim": claim.claim_text,
                "citations": cites,
                "confidence": claim.confidence,
                "source_ids": sids,
                "type": "specialist",
            })

        return claims

    # ===================================================================
    # LLM calls
    # ===================================================================

    async def _llm_call(self, system: str, user_msg: str, max_tokens: int, settings) -> str:
        """Async LLM call with semaphore gating and call count tracking."""
        async with self.semaphore:
            result = await asyncio.to_thread(
                minimax_chat_anthropic, system, user_msg, max_tokens, settings,
            )
        self.state.llm_call_count += 1
        return result

    async def _generate_outline(self, sid_to_num: dict[str, int], settings) -> dict:
        """Generate the paper outline from synthesis, debate, and angle data."""
        outline_prompt = (PROMPTS_DIR / "v2_paper_outline.txt").read_text(encoding="utf-8")

        # Build angle summaries
        angle_summaries = []
        for angle in self.state.angles:
            findings_text = "\n".join(
                f"- {f.get('claim', f.get('finding', ''))}" for f in angle.findings
            ) if angle.findings else "No findings"
            angle_summaries.append(
                f"### Angle: {angle.topic} (id={angle.id})\n"
                f"{angle.description}\n"
                f"Findings ({len(angle.findings)}):\n{findings_text}"
            )

        # Cross-angle connections
        connections_text = ""
        if self.state.cross_angle_connections:
            connections_text = json.dumps(self.state.cross_angle_connections, indent=2)

        # Synthesis summary
        synthesis_text = json.dumps(self.state.synthesis, indent=2) if self.state.synthesis else "{}"

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

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Angle summaries\n\n{'---'.join(angle_summaries)}\n\n"
            f"## Cross-angle connections\n\n{connections_text or 'None detected'}\n\n"
            f"## Synthesis\n\n{synthesis_text}\n\n"
            f"## Debate results\n\n{debate_text or 'No debate conducted'}\n"
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

        raw = await self._llm_call(hook_prompt, user_msg, 2048, settings)
        return raw.strip()

    async def _write_investigation_section(
        self, section: dict, all_claims: list[dict],
        ref_map_text: str, settings,
    ) -> tuple[str, str]:
        """Write a single investigation section. Returns (title, prose)."""
        section_prompt = (PROMPTS_DIR / "v2_paper_section.txt").read_text(encoding="utf-8")
        sec_title = section.get("title", "Untitled")
        assigned_claims = section.get("assigned_claims", [])
        narrative_goal = section.get("narrative_goal", "")

        # Match assigned claim strings to actual claims with source info
        matched_claims = self._match_assigned_claims(assigned_claims, all_claims)

        if not matched_claims and not assigned_claims:
            logger.warning("[paper] Section '%s' has no assigned claims", sec_title)
            return sec_title, ""

        # Format claims for the prompt
        claims_text = self._format_claims_for_prompt(matched_claims if matched_claims else [
            {"claim": c, "citations": "", "confidence": "medium"} for c in assigned_claims
        ])

        user_msg = (
            f"## Section: {sec_title}\n"
            f"Narrative goal: {narrative_goal}\n\n"
            f"## Claims for this section\n\n{claims_text}\n\n"
            f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt, user_msg,
            self.state.config.max_tokens_per_call, settings,
        )
        return sec_title, raw.strip()

    async def _write_connecting_section(
        self, section: dict | None, all_claims: list[dict],
        ref_map_text: str, settings,
    ) -> str:
        """Write the Connecting the Dots section."""
        section_prompt = (PROMPTS_DIR / "v2_paper_section.txt").read_text(encoding="utf-8")

        # Gather cross-angle connections
        connections = []
        if section and section.get("connections"):
            connections = section["connections"]
        elif self.state.cross_angle_connections:
            connections = [
                c.get("description", c.get("connection", str(c)))
                for c in self.state.cross_angle_connections
            ]

        if not connections:
            # Build from synthesis if no explicit connections
            convergent = self.state.synthesis.get("convergent_findings", [])
            if convergent:
                connections = [f.get("finding", str(f)) for f in convergent]

        if not connections:
            return ""

        claims_text = "\n".join(f"- {c}" for c in connections)
        user_msg = (
            f"## Section: Connecting the Dots\n"
            f"Narrative goal: Show how separate threads of investigation converge.\n\n"
            f"## Cross-angle connections\n\n{claims_text}\n\n"
            f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt, user_msg,
            self.state.config.max_tokens_per_call, settings,
        )
        return raw.strip()

    async def _write_other_side_section(
        self, section: dict | None, all_claims: list[dict],
        ref_map_text: str, settings,
    ) -> str:
        """Write The Other Side section with counter-evidence."""
        section_prompt = (PROMPTS_DIR / "v2_paper_section.txt").read_text(encoding="utf-8")

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

        if not counter_claims:
            return ""

        claims_text = "\n".join(f"- {c}" for c in counter_claims[:15])
        user_msg = (
            f"## Section: The Other Side\n"
            f"Narrative goal: Present the strongest counter-evidence and skeptical perspectives fairly.\n\n"
            f"## Counter-evidence and challenges\n\n{claims_text}\n\n"
            f"## Reference map\n\n{ref_map_text}\n"
        )

        raw = await self._llm_call(
            section_prompt, user_msg,
            self.state.config.max_tokens_per_call, settings,
        )
        return raw.strip()

    async def _write_assessment(self, all_claims: list[dict], settings) -> str:
        """Write the What We Actually Know assessment section."""
        assessment_prompt = (PROMPTS_DIR / "v2_paper_assessment.txt").read_text(encoding="utf-8")

        # Categorize findings by confidence
        high_confidence = [c["claim"] for c in all_claims if c.get("confidence") == "high"]
        medium_confidence = [c["claim"] for c in all_claims if c.get("confidence") == "medium"]
        low_confidence = [c["claim"] for c in all_claims if c.get("confidence") == "low"]

        def _format_tier(items: list[str]) -> str:
            if not items:
                return "None"
            return "\n".join(f"- {item}" for item in items[:15])

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Well-documented (high confidence)\n\n{_format_tier(high_confidence)}\n\n"
            f"## Plausible but uncertain (medium confidence)\n\n{_format_tier(medium_confidence)}\n\n"
            f"## Speculative (low confidence)\n\n{_format_tier(low_confidence)}\n"
        )

        raw = await self._llm_call(
            assessment_prompt, user_msg,
            self.state.config.max_tokens_per_call, settings,
        )
        return raw.strip()

    # ===================================================================
    # Mechanical citation insertion
    # ===================================================================

    def _insert_citations_mechanically(
        self, paper_text: str, claims: list[dict], sid_to_num: dict[str, int],
    ) -> str:
        """Insert [N] citations by matching sentences to claims via keyword overlap.

        The LLM writes prose WITHOUT citations. This method matches each
        sentence to claims via keyword overlap and appends the correct [N]
        markers. Guarantees every citation traces back to the claim it was
        assigned to.
        """
        # Build claim -> citation strings list
        claim_citations: list[tuple[str, str]] = []

        # From collected claims (synthesis + registry)
        for c in claims:
            claim_text = c.get("claim", "")
            sids = c.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in sids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))

        if not claim_citations:
            logger.warning("[paper] No claims found for mechanical citation insertion")
            return paper_text

        # Split text into sentences and match
        sentences = re.split(r"(?<=[.!?])\s+", paper_text)
        cited_sentences: list[str] = []
        citations_inserted = 0

        for sentence in sentences:
            # Skip headings, short lines
            if sentence.startswith("#") or len(sentence) < 30:
                cited_sentences.append(sentence)
                continue

            sent_words = set(sentence.lower().split()) - _STOP_WORDS
            best_nums = ""
            best_overlap = 0.0

            for claim_text, nums in claim_citations:
                claim_words = set(claim_text.lower().split()) - _STOP_WORDS
                if not claim_words:
                    continue
                overlap = len(claim_words & sent_words) / len(claim_words)
                if overlap > best_overlap and overlap >= 0.3:
                    best_overlap = overlap
                    best_nums = nums

            if best_nums:
                cited_sentences.append(f"{sentence.rstrip('.')} {best_nums}.")
                citations_inserted += 1
            else:
                cited_sentences.append(sentence)

        logger.info(
            "[paper] Mechanical citation: inserted %d citations across %d sentences",
            citations_inserted, len(sentences),
        )
        return " ".join(cited_sentences)

    # ===================================================================
    # Helpers
    # ===================================================================

    def _match_assigned_claims(
        self, assigned: list[str], all_claims: list[dict],
    ) -> list[dict]:
        """Match outline-assigned claim strings to full claim objects.

        Uses keyword overlap to find the best matching claim from all_claims
        for each assigned claim string from the outline.
        """
        matched: list[dict] = []
        used_indices: set[int] = set()

        for assigned_text in assigned:
            assigned_words = set(assigned_text.lower().split()) - _STOP_WORDS
            if not assigned_words:
                continue

            best_idx = -1
            best_overlap = 0.0

            for i, c in enumerate(all_claims):
                if i in used_indices:
                    continue
                claim_words = set(c["claim"].lower().split()) - _STOP_WORDS
                if not claim_words:
                    continue
                overlap = len(assigned_words & claim_words) / max(len(assigned_words), 1)
                if overlap > best_overlap and overlap >= 0.25:
                    best_overlap = overlap
                    best_idx = i

            if best_idx >= 0:
                matched.append(all_claims[best_idx])
                used_indices.add(best_idx)
            else:
                # No match found -- include as bare claim
                matched.append({
                    "claim": assigned_text,
                    "citations": "",
                    "confidence": "medium",
                })

        return matched

    @staticmethod
    def _format_claims_for_prompt(claims: list[dict]) -> str:
        """Format claims as a numbered list for LLM prompts."""
        lines: list[str] = []
        for i, c in enumerate(claims):
            conf = c.get("confidence", "medium")
            cites = c.get("citations", "")
            notes = c.get("notes", "")
            line = f"{i}. [{conf}] {c.get('claim', '')}"
            if cites:
                line += f"\n   Sources: {cites}"
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
