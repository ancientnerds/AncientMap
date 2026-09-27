"""Dossier handler: the end of a Theo research run (spec 2.1-2.3).

Registered as the only listener on ModeratorComplete. It persists everything a
Claude writer needs as research_artifacts rows (replace semantics: one current
row per (request_id, kind, ref)), completes the source archive for every
source a moderated claim cites, writes the manifest LAST (its presence means
the dossier is complete), then marks the run DONE and emits DossierReady, the
orchestrator's done signal.

Unlike StatePersist's passenger writes, nothing here is fail-soft: an exception
propagates to EventBus.emit, which records it in state.error, and the run ends
'failed'.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from pipeline.lyra.archive_completion import archive_completion_limits, complete_archive
from pipeline.lyra.dossier_manifest import build_manifest, manifest_summary
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import DossierReady, ModeratorComplete
from pipeline.lyra.research_state import ResearchPhase, findings_by_specialist
from pipeline.lyra.training_corpus import registry_payload, save_artifact

logger = logging.getLogger(__name__)


class DossierHandler(BaseHandler):
    """Persists the research dossier and ends the run."""

    def __init__(self, state, bus, semaphore):
        super().__init__(state, bus, semaphore)
        # The moderator runs once per run (handlers/moderator.py), but spec 2.1
        # asks this handler to be idempotent on its own: a second
        # ModeratorComplete waits for the first and then finds dossier_ref set.
        self._lock = asyncio.Lock()

    def register(self):
        self.bus.on(ModeratorComplete, self._on_moderator_complete)

    async def _on_moderator_complete(self, event: ModeratorComplete):
        async with self._lock:
            if self.state.dossier_ref is not None:
                self.state.log(
                    "dossier",
                    "ModeratorComplete fired again: the dossier is already persisted, ignored",
                )
                return
            await self._persist_dossier()

    async def _persist_dossier(self) -> None:
        state = self.state
        if not state.request_id:
            state.error = "A dossier needs a research_requests row, but the run has no request_id"
            return
        final_claims = state.moderated_result.get("final_claims") or []
        if not final_claims:
            state.error = (
                "Moderator produced no final claims: there is nothing to write a paper from, "
                "so no dossier was persisted"
            )
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "dossier",
                "status": "start",
                "meta": {"subtask_total": 3},
            }
        )
        self.emit_sse({"type": "status", "content": "Persisting the research dossier..."})
        await self._save("moderated", state.moderated_result)
        await self._save(
            "synthesis",
            {
                "synthesis": state.synthesis,
                "cross_angle_connections": state.cross_angle_connections,
            },
        )
        await self._save("debate", state.debate_result)
        for angle in state.angles:
            await self._save("angle_findings", asdict(angle), ref=angle.id)
        await self._save(
            "specialist_analyses",
            {
                "analyses": findings_by_specialist(state.angles),
                "panel": [asdict(specialist) for specialist in state.panel],
            },
        )
        await self._save("citation_registry", registry_payload(state.registry))
        await self._save("image_candidate_pool", state.image_candidate_pool)

        self.emit_sse(
            {"type": "status", "content": "Archiving the full texts of every cited source..."}
        )
        max_seconds, concurrency = archive_completion_limits()
        archive = await complete_archive(
            state.request_id,
            state.registry,
            state.moderated_result,
            state.angles,
            max_seconds=max_seconds,
            concurrency=concurrency,
        )
        state.log(
            "dossier",
            f"Archive completion: {archive.full_text}/{archive.cited_sources} cited sources with full "
            f"text, {archive.abstract_only} abstract only, {archive.missing} missing, "
            f"{archive.tdm_reserved} TDM-reserved, {len(archive.failures)} failures "
            f"in {archive.duration_s}s",
        )

        manifest = build_manifest(state, archive.to_dict(), created_at=datetime.now(UTC))
        artifact_id = await self._save("dossier", manifest)
        state.dossier_ref = artifact_id
        state.dossier_summary = manifest_summary(manifest, artifact_id)
        state.phase = ResearchPhase.DONE
        logger.info("[THEO] %s dossier persisted (artifact %s)", state.request_id, artifact_id)
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "dossier",
                "status": "done",
                "meta": {
                    "final_claims": len(final_claims),
                    "cited_sources": archive.cited_sources,
                    "full_text": archive.full_text,
                    "abstract_only": archive.abstract_only,
                    "missing": archive.missing,
                    "tdm_reserved": archive.tdm_reserved,
                },
            }
        )
        await self.bus.emit(DossierReady(request_id=state.request_id))

    async def _save(self, kind: str, payload: Any, ref: str = "") -> int:
        return await asyncio.to_thread(
            save_artifact, self.state.request_id, kind, payload, ref, replace=True
        )
