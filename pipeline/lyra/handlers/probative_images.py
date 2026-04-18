"""Handler: fetches probative images for qualifying claims and embeds them.

Runs between PaperReady and FactCheckComplete. If the feature flag is off,
immediately emits ProbativeImagesReady(0) so the fact-check stage can proceed.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.illustration_specialist import select_opportunities
from pipeline.lyra.image_fetcher import download_candidate, fetch_candidates
from pipeline.lyra.image_gates import (
    build_vlm_prompt,
    metadata_gate_passes,
    parse_vlm_verdict,
    verdict_is_accept,
)
from pipeline.lyra.minimax_shared import create_minimax_client, minimax_vlm
from pipeline.lyra.research_events import PaperReady, ProbativeImagesReady
from pipeline.lyra.research_state import ResearchPhase
from pipeline.lyra.theo_image_captions import (
    find_section_for_claim,
    find_section_for_claim_with_registry,
    image_markdown,
    insert_image_after_section,
)

logger = logging.getLogger(__name__)

IMAGES_DIR = Path(__file__).resolve().parents[3] / "public" / "data" / "research-images"


def _pool_candidates_for_source_ids(
    pool: dict[str, list[dict]],
    source_ids: list[str],
    angles: list,
) -> list:
    """Collect ImageCandidate objects from pool entries for angles whose
    source_ids intersect the claim's source_ids.

    `angles` is state.angles; each angle has `.id` and `.source_ids`.
    """
    from pipeline.lyra.image_fetcher import ImageCandidate

    relevant_angle_ids: set[str] = set()
    claim_sid_set = set(source_ids or [])
    if claim_sid_set:
        for a in angles:
            angle_sids = set(getattr(a, "source_ids", []) or [])
            if angle_sids & claim_sid_set:
                relevant_angle_ids.add(a.id)
    else:
        # No source_ids on the claim — grab candidates from every angle
        relevant_angle_ids = {a.id for a in angles}

    out: list[ImageCandidate] = []
    seen_urls: set[str] = set()
    for angle_id in relevant_angle_ids:
        for d in pool.get(angle_id, []):
            if d.get("url") in seen_urls:
                continue
            seen_urls.add(d.get("url") or "")
            out.append(ImageCandidate.from_dict(d))
    return out


class ProbativeImagesHandler(BaseHandler):
    """See module docstring."""

    def register(self):
        self.bus.on(PaperReady, self._on_paper_ready)

    async def _on_paper_ready(self, event: PaperReady):
        self.state.phase = ResearchPhase.IMAGE_CURATION
        settings = _get_settings()

        if not getattr(settings, "probative_images_enabled", True):
            logger.info("[probative] disabled by config, skipping")
            await self.bus.emit(ProbativeImagesReady(embedded_count=0))
            return

        self.emit_sse({"type": "pipeline", "stage": "probative_images", "status": "start"})

        # 1. Pick opportunities
        claims = self._build_claim_list()
        if not claims:
            await self.bus.emit(ProbativeImagesReady(embedded_count=0))
            return

        opportunities = await select_opportunities(claims, settings)
        max_cap = getattr(settings, "probative_images_max_per_paper", 8)
        opportunities = opportunities[:max_cap]

        if not opportunities:
            logger.info("[probative] specialist returned zero opportunities")
            await self.bus.emit(ProbativeImagesReady(embedded_count=0))
            return

        # 2. Prepare per-paper VLM client + image dir
        paper_dir = IMAGES_DIR / str(self.state.request_id)
        paper_dir.mkdir(parents=True, exist_ok=True)

        client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

        # Handle writer-placed [[IMG:id]] markers first (if paper_writer_sees_images is on)
        writer_embedded = await self._resolve_writer_markers(client, paper_dir, settings)
        embedded: list[dict] = list(writer_embedded)

        # 3. For each opportunity, resolve section → gather candidates → metadata gate → VLM gate → download → insert
        for opp in opportunities:
            if opp["claim_index"] >= len(claims):
                continue
            claim_entry = claims[opp["claim_index"]]
            claim = claim_entry.get("claim", "")
            source_ids = claim_entry.get("source_ids", []) or []
            if not claim:
                continue

            # Preferred: resolve section via citation markers (survives paraphrasing)
            section_name = find_section_for_claim_with_registry(
                self.state.paper_text, source_ids, self.state.registry
            )
            # Legacy fallback: try substring match (handles claims with no registered sources)
            if section_name is None:
                section_name = find_section_for_claim(self.state.paper_text, claim)
            if section_name is None:
                logger.info("[probative] no section matched for claim %s", opp["claim_index"])
                continue

            # Primary: pull from the image candidate pool populated during angle image research
            cands = _pool_candidates_for_source_ids(
                self.state.image_candidate_pool, source_ids, self.state.angles
            )
            # Apply metadata gate against must_show
            cands = [c for c in cands if metadata_gate_passes(c, opp["what_image_must_show"])]
            # Fallback: if pool yielded nothing relevant, fetch on-demand (old behavior)
            if not cands:
                cands = await fetch_candidates(
                    opp["search_query"],
                    limit_per_source=settings.probative_images_candidates_per_opportunity,
                )
                cands = [c for c in cands if metadata_gate_passes(c, opp["what_image_must_show"])]
            if not cands:
                continue

            # Vision gate: stop at first accepted
            accepted_cand = None
            for cand in cands[:5]:
                ok = await download_candidate(
                    cand,
                    paper_dir / f"_probe_claim_{opp['claim_index']}.bin",
                )
                if not ok:
                    continue
                image_bytes = (paper_dir / f"_probe_claim_{opp['claim_index']}.bin").read_bytes()
                prompt = build_vlm_prompt(
                    claim,
                    opp["what_image_must_show"],
                    opp.get("forbidden_elements", []),
                )
                raw = await asyncio.to_thread(minimax_vlm, client, image_bytes, prompt)
                verdict = parse_vlm_verdict(raw)
                if verdict_is_accept(verdict):
                    accepted_cand = cand
                    break

            # Clean up probe file
            probe = paper_dir / f"_probe_claim_{opp['claim_index']}.bin"
            if probe.exists():
                probe.unlink(missing_ok=True)

            if not accepted_cand:
                logger.info(
                    "[probative] no candidate survived VLM for claim %s",
                    opp["claim_index"],
                )
                continue

            # Final download to durable path
            final_path = paper_dir / f"claim_{opp['claim_index']}.jpg"
            if not await download_candidate(accepted_cand, final_path):
                continue

            web_path = (
                f"/data/research-images/{self.state.request_id}/claim_{opp['claim_index']}.jpg"
            )
            md = image_markdown(accepted_cand, web_path, opp["rationale"])

            new_text = insert_image_after_section(self.state.paper_text, section_name, md)
            if new_text == self.state.paper_text:
                # Section was renamed between resolver and insert; skip
                logger.info("[probative] insert failed for section '%s'", section_name)
                continue
            self.state.paper_text = new_text

            embedded.append(
                {
                    "claim_index": opp["claim_index"],
                    "claim_text": claim,
                    "image_path": str(final_path),
                    "web_path": web_path,
                    "source_url": accepted_cand.url,
                    "title": accepted_cand.title,
                    "artist": accepted_cand.artist,
                    "license": accepted_cand.license,
                    "license_url": accepted_cand.license_url,
                    "rationale": opp["rationale"],
                    "section_heading": section_name,
                }
            )

        client.close()
        self.state.probative_images = embedded

        from pipeline.lyra.image_diversity import compute_diversity

        diversity = compute_diversity(embedded)
        self.state.probative_images_diversity = diversity

        logger.info(
            "[probative] embedded %d images, source_diversity=%.2f (%d sources: %s)",
            len(embedded),
            diversity["source_diversity"],
            diversity["source_count"],
            ", ".join(diversity["sources"]),
        )
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "probative_images",
                "status": "done",
                "meta": {"embedded": len(embedded), **diversity},
            }
        )
        await self.bus.emit(ProbativeImagesReady(embedded_count=len(embedded)))

    async def _resolve_writer_markers(
        self,
        client,
        paper_dir,
        settings,
    ) -> list[dict]:
        """Replace [[IMG:short]] markers the paper writer emitted with real images.

        Returns list of embedded-image dicts (for state.probative_images + diversity).
        """
        import hashlib
        import re as _re

        markers = _re.findall(r"\[\[IMG:([a-f0-9]{10})\]\]", self.state.paper_text)
        if not markers:
            return []

        # Build short-id → candidate mapping from the pool
        short_to_cand: dict[str, dict] = {}
        for _angle_id, cands in (self.state.image_candidate_pool or {}).items():
            for c in cands:
                url = c.get("url", "")
                if not url:
                    continue
                short = hashlib.sha1(url.encode()).hexdigest()[:10]
                short_to_cand.setdefault(short, c)

        embedded: list[dict] = []
        from pipeline.lyra.image_fetcher import ImageCandidate

        for i, short in enumerate(dict.fromkeys(markers)):  # dedupe, preserve order
            cand_dict = short_to_cand.get(short)
            if not cand_dict:
                logger.info("[probative] writer marker %s not in pool; removing", short)
                self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", "")
                continue
            cand = ImageCandidate.from_dict(cand_dict)

            # Download + light VLM gate (no forbidden-elements rules since the writer
            # explicitly chose it — just verify the image loads and isn't porn/broken)
            final_path = paper_dir / f"writer_img_{i}.jpg"
            if not await download_candidate(cand, final_path):
                self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", "")
                continue

            web_path = f"/data/research-images/{self.state.request_id}/writer_img_{i}.jpg"
            rationale = "Image placed by the paper writer as visual evidence for this passage."
            md = image_markdown(cand, web_path, rationale)
            # Substitute the marker with the image markdown (inline, no section repositioning)
            self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", md, 1)

            embedded.append(
                {
                    "claim_index": -1,
                    "claim_text": "[writer-placed]",
                    "image_path": str(final_path),
                    "web_path": web_path,
                    "source_url": cand.url,
                    "title": cand.title,
                    "artist": cand.artist,
                    "license": cand.license,
                    "license_url": cand.license_url,
                    "rationale": rationale,
                    "section_heading": "[inline]",
                    "source": cand.source,  # for diversity scoring
                }
            )
        return embedded

    def _build_claim_list(self) -> list[dict]:
        """Flatten moderated+synthesis claims into the same shape the Illustration Specialist expects."""
        out: list[dict] = []
        for c in self.state.moderated_result.get("final_claims", []):
            out.append(
                {
                    "claim": c.get("claim", ""),
                    "confidence": c.get("confidence", "medium"),
                    "source_ids": c.get("source_ids", []) or [],
                }
            )
        for c in self.state.synthesis.get("consensus_claims", []):
            out.append(
                {
                    "claim": c.get("claim", ""),
                    "confidence": c.get("confidence", "medium"),
                    "source_ids": c.get("source_ids", []) or [],
                }
            )
        return out
