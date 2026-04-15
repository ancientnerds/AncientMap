"""Fact-checking handler --- verifies citations in the assembled paper before presentation."""

import logging

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import FactCheckComplete, PaperReady

logger = logging.getLogger(__name__)


class FactCheckHandler(BaseHandler):
    def register(self):
        self.bus.on(PaperReady, self._on_paper_ready)

    async def _on_paper_ready(self, event: PaperReady):
        self.emit_sse({"type": "pipeline", "stage": "fact_check", "status": "start"})

        from pipeline.lyra.citation_verifier import verify_all_citations
        from pipeline.lyra.config import _get_settings

        # Build source list for verification
        verify_sources = []
        for sid, num in sorted(self.state.registry.reference_numbers.items(), key=lambda kv: kv[1]):
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

        if verify_sources and self.state.paper_text:
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Fact-checking {len(verify_sources)} citations...",
                }
            )
            self.state.paper_text = verify_all_citations(
                self.state.paper_text,
                verify_sources,
                settings=_get_settings(),
            )
            self.state.log(
                "fact_check",
                f"Verified {len(verify_sources)} citations in paper",
            )
        else:
            self.state.log("fact_check", "No sources to verify, skipping")

        self.emit_sse({"type": "pipeline", "stage": "fact_check", "status": "done"})
        await self.bus.emit(FactCheckComplete())
