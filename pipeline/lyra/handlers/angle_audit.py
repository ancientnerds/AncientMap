"""Per-angle source audit --- forwards SourcesFound -> SourcesAudited.

Historical note (Follow-up-Ticket 1, 2026-08-05): this handler used to run
an LLM reliability audit + tier-3 noise floor over "unscored"
(reliability_tier == 0) sources. That gate was unreachable since
inception: register_source (theo_citations.py) always assigns a real tier
at registration time — score_tier_by_domain() never returns 0, and
self_source forces tier 4 — so `source_items` (sources with
reliability_tier == 0) was always empty and the LLM audit body never ran a
single call. Removed as dead code; zero behavior change.

What remains IS live: SearchHandler emits SourcesFound after every search
round, and ContentFetchHandler / SpecialistHandler both listen on
SourcesAudited to advance the pipeline (see convergence_orchestrator.py's
event-flow comment). This handler still has to forward that trigger.

A redesigned source audit (if wanted) is R-Backlog material, not part of
this fix.
"""

import logging

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import SourcesAudited, SourcesFound

logger = logging.getLogger(__name__)


class AuditHandler(BaseHandler):
    def register(self):
        self.bus.on(SourcesFound, self._on_sources_found)

    async def _on_sources_found(self, event: SourcesFound):
        # Preserves the pre-existing edge case exactly: when count == 0 the
        # event fires without checking the angle exists; when count > 0 the
        # (now-removed) audit body looked up the angle first and silently
        # dropped the event if it was gone.
        if event.count == 0:
            await self.bus.emit(SourcesAudited(angle_id=event.angle_id, accepted=0, rejected=0))
            return
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if not angle:
            return
        await self.bus.emit(SourcesAudited(angle_id=event.angle_id, accepted=0, rejected=0))
