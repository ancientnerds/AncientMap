"""Per-angle source audit --- reliability scoring and rejection."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import SourcesAudited, SourcesFound

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class AuditHandler(BaseHandler):
    def register(self):
        self.bus.on(SourcesFound, self._on_sources_found)

    async def _on_sources_found(self, event: SourcesFound):
        if event.count == 0:
            # No new sources --- pass through with zero audit
            await self.bus.emit(SourcesAudited(angle_id=event.angle_id, accepted=0, rejected=0))
            return
        await self.audit_angle(event.angle_id)

    async def audit_angle(self, angle_id: str):
        """Audit all unscored sources for this angle."""
        angle = next((a for a in self.state.angles if a.id == angle_id), None)
        if not angle:
            return

        # Only audit unscored sources (reliability_tier == 0).
        # Sources already scored by this or any other angle are skipped,
        # which also handles cross-angle dedup automatically.
        source_items = []
        for sid in angle.source_ids:
            source = self.state.registry.get_reference(sid)
            if source and source.reliability_tier == 0:
                source_items.append((sid, source))

        if not source_items:
            await self.bus.emit(SourcesAudited(angle_id=angle_id, accepted=0, rejected=0))
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"audit_{angle_id}",
                "status": "start",
                "meta": {"subtask_total": len(source_items), "angle": angle.topic},
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": f"Auditing {len(source_items)} sources for '{angle.topic}'...",
            }
        )

        system = (PROMPTS_DIR / "theo_source_audit.txt").read_text(encoding="utf-8")
        rejected_ids: set[str] = set()
        total_scored = 0

        async def _audit_one(sid: str, source) -> dict:
            tier_str = ""
            if source.reliability_tier == 1:
                tier_str = " [Academic]"
            elif source.reliability_tier == 2:
                tier_str = " [Reputable]"
            user_msg = (
                f"## Research question\n\n{self.state.question}\n\n"
                f"## Research angle\n\n{angle.topic}: {angle.description}\n\n"
                f"## Source to evaluate\n\n"
                # `Source #sid` not `Source [sid]` — see angle_specialist.py.
                f"Source #{sid}: {source.title}{tier_str}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}\n"
            )
            settings = _get_settings()
            async with self.semaphore:
                raw = await asyncio.to_thread(
                    minimax_chat_anthropic,
                    system,
                    user_msg,
                    self.state.config.max_tokens_per_call,
                    settings,
                    temperature=settings.temperature_research,
                )
            self.state.llm_call_count += 1
            parsed = self._parse_json(raw)
            parsed["_sid"] = sid
            return parsed

        # Run ALL audits at once --- the global MiniMax limiter handles concurrency
        self.emit_sse(
            {
                "type": "status",
                "content": f"Auditing {len(source_items)} sources for '{angle.topic}'...",
                "subtask_done": 0,
                "subtask_total": len(source_items),
            }
        )

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[_audit_one(sid, source) for sid, source in source_items],
                    return_exceptions=True,
                ),
                timeout=300,  # 5 min max for all audits
            )
        except TimeoutError:
            logger.warning("Audit timed out for angle '%s' after 300s", angle.topic)
            self.state.log(
                "audit",
                f"Angle '{angle.topic}': audit timed out, proceeding with unaudited sources",
            )
            results = []

        for result in results:
            if isinstance(result, Exception):
                # asyncio.gather(return_exceptions=True) returns exceptions
                # as values; log them properly with traceback so we can see
                # WHICH source's audit raised instead of guessing.
                logger.error("Audit task failed: %r", result, exc_info=result)
                self.state.log("audit", f"Audit task failed: {result!r}")
                continue
            original_sid = result.get("_sid", "")
            for entry in result.get("scored_sources", []):
                if not isinstance(entry, dict):
                    continue
                sid = entry.get("id", "") or original_sid
                tier_val = entry.get("reliability_tier", 0)
                source = self.state.registry.sources.get(sid)
                if source:
                    source.reliability_tier = tier_val
                    total_scored += 1
            for entry in result.get("rejected_sources", []):
                if not isinstance(entry, dict):
                    continue
                rid = entry.get("id", "") or original_sid
                if rid:
                    rejected_ids.add(rid)

        # Tier floor: tier 3 sources are speculative. Drop them only when
        # this angle has enough academic+reputable supply (>=3 tier1+tier2).
        # When supply is thin, keep tier 3 so the angle isn't starved.
        # Run 15 had angles where 21% of sources were fringe tier-3 with
        # plenty of tier-1/2 supply available — pure noise floor.
        MIN_TIER12 = 3
        tier12_count = sum(
            1
            for sid in angle.source_ids
            if (s := self.state.registry.sources.get(sid)) and s.reliability_tier in (1, 2)
        )
        if tier12_count >= MIN_TIER12:
            for sid in list(angle.source_ids):
                s = self.state.registry.sources.get(sid)
                if s and s.reliability_tier == 3:
                    rejected_ids.add(sid)

        # Remove rejected sources from this angle only.
        # DON'T pop from registry --- other angles may reference this source.
        for rid in rejected_ids:
            if rid in angle.source_ids:
                angle.source_ids.remove(rid)

        accepted = len(angle.source_ids)
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"audit_{angle_id}",
                "status": "done",
                "meta": {
                    "scored": total_scored,
                    "rejected": len(rejected_ids),
                    "accepted": accepted,
                },
            }
        )
        self.state.log(
            "audit",
            f"Angle '{angle.topic}': {total_scored} scored, {len(rejected_ids)} rejected, {accepted} accepted",
        )

        await self.bus.emit(
            SourcesAudited(angle_id=angle_id, accepted=accepted, rejected=len(rejected_ids))
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {}
