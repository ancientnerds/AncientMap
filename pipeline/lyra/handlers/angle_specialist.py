"""Specialist analysis --- runs specialists on per-angle sources, tracks
contribution scores, handles convergence detection and panel management."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic, structured_llm_call
from pipeline.lyra.schemas import SPECIALIST_FINDINGS_SCHEMA

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
from pipeline.lyra.research_events import (
    AngleSaturated,
    ContentFetched,
    FindingsProduced,
    NewAngleDiscovered,
    SourcesAudited,
    SpecialistPruned,
    SpecialistRecruited,
)
from pipeline.lyra.research_state import ActiveSpecialist, ResearchAngle
from pipeline.lyra.theo_specialists import (
    _SPECIALIST_BY_ID,
    SPECIALIST_POOL,
    build_specialist_prompt,
    select_specialists,
)

logger = logging.getLogger(__name__)


class SpecialistHandler(BaseHandler):
    def register(self):
        # Listen on BOTH — SourcesAudited (direct) and ContentFetched (after fetch)
        # Whichever fires first triggers the specialist. ContentFetched is optional.
        self.bus.on(SourcesAudited, self._on_content_fetched)
        self.bus.on(ContentFetched, self._on_content_fetched)

    # ------------------------------------------------------------------
    # Event entry point
    # ------------------------------------------------------------------

    async def _on_content_fetched(self, event: ContentFetched | SourcesAudited):
        # Guard: don't run specialist twice for the same angle+round
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if not angle or angle.saturated:
            return
        # Skip if we already ran specialists for this search round
        expected_rounds = len(angle.recent_claim_counts)
        if expected_rounds > 0 and expected_rounds >= angle.search_rounds:
            return  # already processed this round

        # Select specialists for this angle based on its domains
        if not angle.assigned_specialists:
            count = max(3, min(6, len(angle.specialist_domains) + 2))
            specs = select_specialists(
                domain_tags=angle.specialist_domains,
                question=self.state.question,
                count=count,
                force_include=self.state.force_include or None,
                force_exclude=self.state.force_exclude or None,
            )
            angle.assigned_specialists = [s.id for s in specs]

        # Use this angle's specialists instead of the global panel
        active_spec_ids = angle.assigned_specialists

        if not active_spec_ids:
            self.state.log("specialist", "No specialists assigned to angle")
            return

        # Build ActiveSpecialist wrappers for tracking (reuse from panel if exists)
        panel_lookup = {s.specialist_id: s for s in self.state.panel}
        active_panel: list[ActiveSpecialist] = []
        for spec_id in active_spec_ids:
            if spec_id in panel_lookup:
                active_panel.append(panel_lookup[spec_id])
            else:
                # Create a new panel entry for this specialist
                spec = _SPECIALIST_BY_ID.get(spec_id)
                if spec:
                    new_panel_spec = ActiveSpecialist(
                        specialist_id=spec.id,
                        name=spec.name,
                        domain=spec.domain,
                    )
                    self.state.panel.append(new_panel_spec)
                    active_panel.append(new_panel_spec)

        if not active_panel:
            self.state.log("specialist", "No valid specialists found for angle")
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"specialist_{angle.id}",
                "status": "start",
                "meta": {
                    "subtask_total": len(active_panel),
                    "angle": angle.topic,
                    "specialists": [s.name for s in active_panel],
                },
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": (
                    f"Running {len(active_panel)} specialists on '{angle.topic}' "
                    f"({len(angle.source_ids)} sources)..."
                ),
            }
        )

        # Build sources_context with only NEW sources (not yet analyzed).
        # Previous rounds' findings are passed as context summary instead of
        # re-sending all old sources. This keeps specialist input bounded
        # without throwing away any research.
        analyzed_sids = {sid for f in angle.findings for sid in f.get("_source_ids", [])}
        new_source_ids = [sid for sid in angle.source_ids if sid not in analyzed_sids]
        sources_context = self._build_angle_sources_context(angle, source_ids=new_source_ids)

        # Add previous findings as context summary
        if angle.findings:
            prev_summary = "\n".join(f"- {f.get('claim', '')}" for f in angle.findings[:30])
            sources_context = (
                f"## Previously established findings ({len(angle.findings)} claims)\n\n"
                f"{prev_summary}\n\n"
                f"## New sources to analyze ({len(new_source_ids)} sources)\n\n"
                f"{sources_context}"
            )
        if not sources_context.strip():
            self.state.log(
                "specialist", f"No source content for angle '{angle.topic}', skipping analysis"
            )
            angle.recent_claim_counts.append(0)
            await self._check_saturation(angle)
            await self.bus.emit(
                FindingsProduced(
                    angle_id=angle.id,
                    new_claims=0,
                    total_claims=len(angle.findings),
                )
            )
            return

        # Run all active specialists in parallel
        analyses = await self._run_specialists_parallel(active_panel, angle, sources_context)

        # Process results: count new claims, update scores, register claims
        new_claims_total = 0
        specialist_gaps: list[str] = []
        cross_angle_topics: list[tuple[str, str]] = []  # (topic, source_angle_id)

        for panel_spec in active_panel:
            analysis = analyses.get(panel_spec.specialist_id)
            panel_spec.rounds_participated += 1

            if not analysis:
                panel_spec.consecutive_zero_rounds += 1
                continue

            findings = analysis.get("findings", [])
            uncertainties = analysis.get("uncertainties", [])

            # Count NEW claims not already in angle.findings
            existing_claims = {f.get("claim", "").lower().strip() for f in angle.findings}
            new_findings = []
            for finding in findings:
                claim_text = finding.get("claim", "").strip()
                if not claim_text:
                    continue
                if claim_text.lower().strip() not in existing_claims:
                    new_findings.append(finding)

            new_count = len(new_findings)
            new_claims_total += new_count

            # Update contribution score
            for finding in new_findings:
                source_ids = finding.get("source_ids", [])
                # Check tier of supporting sources
                has_good_source = False
                for sid in source_ids:
                    source = self.state.registry.get_reference(sid)
                    if source and source.reliability_tier in (1, 2):
                        has_good_source = True
                        break
                panel_spec.contribution_score += 0.3 if has_good_source else 0.1

            for _u in uncertainties:
                panel_spec.contribution_score += 0.1

            # Track consecutive zero rounds
            if new_count == 0:
                panel_spec.consecutive_zero_rounds += 1
            else:
                panel_spec.consecutive_zero_rounds = 0

            # Add new findings to angle
            for finding in new_findings:
                finding["specialist_id"] = panel_spec.specialist_id
                finding["_source_ids"] = list(finding.get("source_ids", []))
                angle.findings.append(finding)
                # Register in citation registry
                self.state.registry.add_claim(
                    claim_text=finding.get("claim", ""),
                    source_ids=finding.get("source_ids", []),
                    specialist_id=panel_spec.specialist_id,
                    confidence=finding.get("confidence", "medium"),
                )

            # Collect gaps for query refinement
            specialist_gaps.extend(uncertainties)

            # Check for cross-angle connections
            cross_topics = self._detect_cross_angle_connections(
                new_findings,
                angle,
                panel_spec,
            )
            cross_angle_topics.extend(cross_topics)

        # Novelty check --- classify new claims as restatement/incremental/rabbit_hole
        genuine_novelty = 0
        rabbit_holes_found: list[str] = []
        if new_claims_total > 0 and len(angle.findings) > new_claims_total:
            # Only run novelty check if we have existing findings to compare against
            novelty = await self._check_novelty(angle, new_claims_total)
            genuine_novelty = novelty.get("incremental", 0) + novelty.get("rabbit_holes", 0)
            rabbit_holes_found = novelty.get("rabbit_hole_topics", [])

            # Extend max rounds if rabbit holes found
            if rabbit_holes_found:
                self.state.log(
                    "specialist",
                    f"Rabbit holes in '{angle.topic}': {rabbit_holes_found}",
                )
                # Grant bonus rounds for each rabbit hole (up to double the base max).
                # Quality > speed: the user explicitly does NOT want research depth
                # capped to fit the wall-clock budget. The orchestrator timeout
                # has been raised instead (api/services/theo_worker.py).
                angle_max = self.state.config.max_search_rounds_per_angle
                bonus = min(len(rabbit_holes_found), angle_max)
                # Store effective max on the angle so saturation checks use it
                effective_max = angle_max + bonus
                angle.effective_max_rounds = effective_max
                if angle.search_rounds < effective_max:
                    self.state.log(
                        "specialist",
                        f"Angle '{angle.topic}' granted {bonus} bonus rounds (max now {effective_max})",
                    )
        else:
            # First round --- all claims are novel by definition
            genuine_novelty = new_claims_total

        # Track GENUINE novelty for convergence (not raw claim count)
        angle.recent_claim_counts.append(genuine_novelty)

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"specialist_{angle.id}",
                "status": "done",
                "meta": {
                    "angle": angle.topic,
                    "new_claims": genuine_novelty,
                    "raw_new_claims": new_claims_total,
                    "rabbit_holes": len(rabbit_holes_found),
                    "total_claims": len(angle.findings),
                    "round": angle.search_rounds,
                },
            }
        )
        self.state.log(
            "specialist",
            f"Angle '{angle.topic}': {new_claims_total} new claims ({len(angle.findings)} total)",
        )

        # Prune underperforming specialists
        await self._prune_specialists()

        # Recruit new specialists if cross-angle connections reveal new domains
        await self._recruit_from_connections(cross_angle_topics)

        # Check saturation
        await self._check_saturation(angle)

        # Emit cross-angle discoveries as new angles
        for topic, spawned_from in cross_angle_topics:
            await self.bus.emit(
                NewAngleDiscovered(
                    topic=topic,
                    description=f"Cross-angle connection discovered from '{angle.topic}'",
                    spawned_from=spawned_from,
                )
            )

        # Emit findings event
        await self.bus.emit(
            FindingsProduced(
                angle_id=angle.id,
                new_claims=new_claims_total,
                total_claims=len(angle.findings),
            )
        )

        # After round 1: wait for cross-pollination before triggering round 2.
        # After cross-pollination: trigger subsequent rounds for convergence verification.
        # Skip round 2 trigger here --- the orchestrator handles it via AngleCreated
        # after cross-pollination completes. Only trigger for round 3+.
        if not angle.saturated and self.state.cross_pollinated and angle.search_rounds > 1:
            from pipeline.lyra.handlers.angle_search import SearchHandler

            search_handler = self.bus.get_handler(SearchHandler)
            if search_handler:
                if specialist_gaps and new_claims_total > 0:
                    await search_handler.refine_and_search(angle.id, specialist_gaps)
                else:
                    await search_handler.search_angle(angle.id)
        # Round 1 done but not yet cross-pollinated --- convergence checker will handle it

    # ------------------------------------------------------------------
    # Sources context (per-angle, not full registry)
    # ------------------------------------------------------------------

    def _build_angle_sources_context(
        self, angle: ResearchAngle, source_ids: list[str] | None = None
    ) -> str:
        """Format sources into a text block for specialist prompts.

        If source_ids is provided, only those sources are included (for new-only mode).
        Otherwise falls back to all angle sources (round 1).
        """
        ids_to_use = source_ids if source_ids is not None else angle.source_ids
        lines: list[str] = []
        for sid in ids_to_use:
            source = self.state.registry.get_reference(sid)
            if not source:
                continue
            tier_str = ""
            if source.reliability_tier == 1:
                tier_str = " [Academic]"
            elif source.reliability_tier == 2:
                tier_str = " [Reputable]"
            # NOTE: source id MUST NOT be wrapped in [brackets]. The LLM has
            # been observed to copy [<12-hex-sid>] tokens into claim text,
            # which then fails the citation audit (non_numeric_markers). Use
            # `Source #<sid>:` so the id is visually a label, not a marker.
            lines.append(
                f"Source #{sid}: {source.title}{tier_str}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}\n"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parallel specialist execution
    # ------------------------------------------------------------------

    async def _run_specialists_parallel(
        self,
        panel: list[ActiveSpecialist],
        angle: ResearchAngle,
        sources_context: str,
    ) -> dict[str, dict]:
        """Run all active specialists in parallel via ThreadPoolExecutor.

        Returns {specialist_id: parsed_analysis_dict}.
        """
        settings = _get_settings()
        max_tokens = self.state.config.max_tokens_per_call
        question = self.state.question

        def _run_one(panel_spec: ActiveSpecialist) -> tuple[str, dict]:
            spec = _SPECIALIST_BY_ID.get(panel_spec.specialist_id)
            if not spec:
                return panel_spec.specialist_id, {}

            system_prompt, user_prompt = build_specialist_prompt(
                spec,
                question,
                sources_context,
            )

            parsed = structured_llm_call(
                system_prompt,
                user_prompt,
                SPECIALIST_FINDINGS_SCHEMA,
                max_tokens,
                settings=settings,
                temperature=settings.temperature_research,
            )
            self.state.llm_call_count += 1
            if isinstance(parsed, dict) and parsed:
                return panel_spec.specialist_id, parsed
            logger.warning("Specialist %s returned empty result", panel_spec.specialist_id)
            return panel_spec.specialist_id, {}

        loop = asyncio.get_running_loop()
        worker_count = min(len(panel), self.state.config.max_concurrent_llm_calls)
        analyses: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {loop.run_in_executor(pool, _run_one, ps): ps for ps in panel}
            results = await asyncio.gather(*futures.keys(), return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Specialist call failed: %s", result)
                continue
            spec_id, parsed = result
            if parsed:
                analyses[spec_id] = parsed

        return analyses

    # ------------------------------------------------------------------
    # Novelty assessment
    # ------------------------------------------------------------------

    async def _check_novelty(self, angle: ResearchAngle, new_count: int) -> dict:
        """Classify new findings as restatement/incremental/rabbit_hole."""
        prompt_path = PROMPTS_DIR / "v2_novelty_check.txt"
        if not prompt_path.exists():
            return {"incremental": new_count, "rabbit_holes": 0, "rabbit_hole_topics": []}

        prompt = prompt_path.read_text(encoding="utf-8")

        # Build existing vs new findings for comparison
        existing = angle.findings[:-new_count] if len(angle.findings) > new_count else []
        new = angle.findings[-new_count:]

        existing_text = json.dumps([{"claim": f.get("claim", "")} for f in existing[:20]], indent=2)
        new_text = json.dumps([{"claim": f.get("claim", "")} for f in new], indent=2)

        user_msg = (
            f"## Research angle: {angle.topic}\n\n"
            f"## Existing findings ({len(existing)} total, showing top 20)\n\n{existing_text}\n\n"
            f"## New findings from this round ({len(new)})\n\n{new_text}"
        )

        settings = _get_settings()
        async with self.semaphore:
            raw = await asyncio.to_thread(
                minimax_chat_anthropic,
                prompt,
                user_msg,
                # M2.7's interleaved thinking shares this budget with output;
                # 4096 was getting truncated mid-array on novelty assessments
                # with 10+ new findings. Match the main specialist call so
                # thinking has room without starving the JSON output.
                self.state.config.max_tokens_per_call,
                settings,
                temperature=settings.temperature_research,
            )
        self.state.llm_call_count += 1

        parsed = _parse_json(raw)

        # Count from assessments array instead of trusting LLM summary
        assessments = parsed.get("assessments", [])
        if assessments:
            incremental = sum(1 for a in assessments if a.get("classification") == "incremental")
            rabbit_holes = sum(1 for a in assessments if a.get("classification") == "rabbit_hole")
            rabbit_hole_topics = parsed.get("rabbit_hole_topics", [])
        else:
            # Fallback to summary if no assessments array
            summary = parsed.get("summary", {})
            incremental = summary.get("incremental", 0)
            rabbit_holes = summary.get("rabbit_holes", 0)
            rabbit_hole_topics = parsed.get("rabbit_hole_topics", [])

        self.state.log(
            "novelty",
            f"Angle '{angle.topic}': "
            f"{len(assessments) - incremental - rabbit_holes if assessments else 'N/A'} restatements, "
            f"{incremental} incremental, {rabbit_holes} rabbit holes",
        )

        return {
            "incremental": incremental,
            "rabbit_holes": rabbit_holes,
            "rabbit_hole_topics": rabbit_hole_topics,
        }

    # ------------------------------------------------------------------
    # Saturation detection
    # ------------------------------------------------------------------

    async def _check_saturation(self, angle: ResearchAngle):
        """Mark angle as saturated if last N rounds all produced zero new claims."""
        threshold = self.state.config.saturation_threshold
        recent = angle.recent_claim_counts[-threshold:]
        if len(recent) >= threshold and all(c == 0 for c in recent):
            angle.saturated = True
            self.state.log(
                "specialist",
                f"Angle '{angle.topic}' saturated: {threshold} consecutive zero-claim rounds",
            )
            await self.bus.emit(AngleSaturated(angle_id=angle.id))

        # Also saturate if we hit the hard cap on search rounds
        # Use effective_max_rounds if rabbit holes granted bonus rounds
        max_rounds = max(
            self.state.config.max_search_rounds_per_angle,
            angle.effective_max_rounds,
        )
        if angle.search_rounds >= max_rounds and not angle.saturated:
            angle.saturated = True
            self.state.log(
                "specialist",
                f"Angle '{angle.topic}' saturated: hit max search rounds ({angle.search_rounds})",
            )
            await self.bus.emit(AngleSaturated(angle_id=angle.id))

    # ------------------------------------------------------------------
    # Cross-angle connection detection
    # ------------------------------------------------------------------

    def _detect_cross_angle_connections(
        self,
        new_findings: list[dict],
        current_angle: ResearchAngle,
        panel_spec: ActiveSpecialist,
    ) -> list[tuple[str, str]]:
        """Check if new findings mention topics from OTHER angles.

        Returns list of (new_sub_topic, current_angle_id) for genuinely new
        discoveries that don't already match an existing angle.
        """
        other_angles = [a for a in self.state.angles if a.id != current_angle.id]
        if not other_angles:
            return []

        discovered: list[tuple[str, str]] = []

        for finding in new_findings:
            claim_lower = finding.get("claim", "").lower()
            evidence_lower = finding.get("evidence", "").lower()
            combined = claim_lower + " " + evidence_lower

            for other in other_angles:
                # Check if any key terms from the other angle appear in this finding
                other_words = set(other.topic.lower().split())
                # Require at least 2 meaningful words to match (skip common words)
                skip_words = {"the", "of", "and", "in", "a", "to", "for", "on", "is", "at", "by"}
                meaningful = other_words - skip_words
                if len(meaningful) < 2:
                    continue

                matches = sum(1 for w in meaningful if w in combined)
                if matches >= 2:
                    panel_spec.interdisciplinary_hits += 1
                    self.state.cross_angle_connections.append(
                        {
                            "from_angle": current_angle.id,
                            "to_angle": other.id,
                            "claim": finding.get("claim", ""),
                            "specialist": panel_spec.specialist_id,
                        }
                    )

        # Caveat-text → new-angle extraction has been disabled (2026-05-11).
        # The heuristic was producing unbounded topic drift: a single
        # specialist caveat like "the Great Sphinx of Giza may require
        # further investigation" was being lifted as the topic of a spawned
        # angle, which cross_pollination then enriched with off-topic
        # search queries. A Sea Peoples run spent hours querying Sphinx
        # imagery before stalling. Cross-angle connections (above) still
        # populate state.cross_angle_connections — the only thing removed
        # is the unstructured caveat-to-topic pathway.
        return discovered

    # ------------------------------------------------------------------
    # Specialist pruning
    # ------------------------------------------------------------------

    async def _prune_specialists(self):
        """Remove specialists that consistently produce zero new claims."""
        config = self.state.config
        pruned: list[str] = []

        for panel_spec in self.state.panel:
            if not panel_spec.active:
                continue
            if (
                panel_spec.consecutive_zero_rounds >= config.prune_after_zero_rounds
                and panel_spec.interdisciplinary_hits == 0
                and len(self.state.active_specialists) > config.min_specialists
            ):
                panel_spec.active = False
                pruned.append(panel_spec.specialist_id)
                self.state.log(
                    "specialist",
                    f"Pruned specialist '{panel_spec.name}' ({panel_spec.specialist_id}): "
                    f"{panel_spec.consecutive_zero_rounds} zero rounds, "
                    f"score={panel_spec.contribution_score:.1f}",
                )

        for spec_id in pruned:
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Specialist '{spec_id}' pruned (no contributions)",
                }
            )
            await self.bus.emit(SpecialistPruned(specialist_id=spec_id))

    # ------------------------------------------------------------------
    # Specialist recruitment
    # ------------------------------------------------------------------

    async def _recruit_from_connections(
        self,
        cross_angle_topics: list[tuple[str, str]],
    ):
        """If cross-angle connections reveal a domain not covered by the panel,
        recruit a matching specialist from SPECIALIST_POOL."""
        if not cross_angle_topics:
            return

        config = self.state.config
        if len(self.state.active_specialists) >= config.max_specialists:
            return

        current_ids = {s.specialist_id for s in self.state.panel}
        combined_text = " ".join(topic for topic, _ in cross_angle_topics).lower()

        # Score pool specialists against the cross-angle text
        best_candidate = None
        best_score = 0
        for spec in SPECIALIST_POOL:
            if spec.id in current_ids:
                continue
            score = sum(1 for kw in spec.trigger_keywords if kw.lower() in combined_text)
            if score > best_score:
                best_score = score
                best_candidate = spec

        if best_candidate and best_score >= 2:
            new_panel_spec = ActiveSpecialist(
                specialist_id=best_candidate.id,
                name=best_candidate.name,
                domain=best_candidate.domain,
            )
            self.state.panel.append(new_panel_spec)
            self.state.log(
                "specialist",
                f"Recruited specialist '{best_candidate.name}' ({best_candidate.id}) "
                f"based on cross-angle connections (score={best_score})",
            )
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Recruited specialist '{best_candidate.name}' for emerging topic",
                }
            )
            await self.bus.emit(SpecialistRecruited(specialist_id=best_candidate.id))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse specialist JSON: %s", cleaned[:200])
        return {}
