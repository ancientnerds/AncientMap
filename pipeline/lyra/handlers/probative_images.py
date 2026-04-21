"""Handler: fetches probative images for qualifying claims and embeds them.

Runs between PaperReady and FactCheckComplete. Produces a high-density image
gallery per section with multiple images per paragraph for YouTube video use.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re as re_module
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
    image_markdown_with_group,
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


def _build_image_pool_text(pool: dict[str, list[dict]]) -> str:
    """Build a text listing of all image candidates in the pool for the LLM context."""
    from pipeline.lyra.image_fetcher import ImageCandidate

    lines = []
    for _angle_id, cands in pool.items():
        for d in cands or []:
            cand = ImageCandidate.from_dict(d) if isinstance(d, dict) else d
            title = getattr(cand, "title", "") or "Untitled"
            source = getattr(cand, "source", "") or ""
            lines.append(f"- {title} ({source})")
    if not lines:
        return "(no images retrieved yet)"
    return "\n".join(lines[:50])  # cap at 50 for context length


def _build_writer_markers_text(paper_text: str) -> str:
    """Extract [[IMG:short]] markers from paper text for deduplication context."""
    markers = re_module.findall(r"\[\[IMG:([a-f0-9]{10})\]\]", paper_text)
    if not markers:
        return "(none)"
    return ", ".join(markers)


def _group_id_for_section(section: str, paragraph_index: int) -> str:
    """Build a stable group ID for gallery grouping."""
    safe = re_module.sub(r"[^a-zA-Z0-9]", "_", section)[:30]
    return f"{safe}_p{paragraph_index}"


class ProbativeImagesHandler(BaseHandler):
    """See module docstring."""

    def register(self):
        self.bus.on(PaperReady, self._on_paper_ready)

    async def _on_paper_ready(self: ProbativeImagesHandler, event: PaperReady):
        self.state.phase = ResearchPhase.IMAGE_CURATION
        settings = _get_settings()

        if not getattr(settings, "probative_images_enabled", True):
            print("[probative] disabled by config, skipping", flush=True)
            await self.bus.emit(ProbativeImagesReady(embedded_count=0))
            return

        pool = getattr(self.state, "image_candidate_pool", {}) or {}
        if not pool:
            print(
                f"[probative] WARNING: image_candidate_pool is EMPTY for request {self.state.request_id} — no images fetched during research phase",
                flush=True,
            )
            logger.warning(
                "[probative] image_candidate_pool is EMPTY — inline images will likely be 0"
            )
        else:
            total = sum(len(v) for v in pool.values())
            print(
                f"[probative] image_candidate_pool has {len(pool)} angles, {total} total candidates",
                flush=True,
            )

        self.emit_sse({"type": "pipeline", "stage": "probative_images", "status": "start"})

        # Build context strings for the illustration specialist
        question = getattr(self.state, "question", "") or ""
        paper_text = self.state.paper_text or ""
        other_paras = _summarize_other_paragraphs(paper_text)
        image_pool_text = _build_image_pool_text(
            getattr(self.state, "image_candidate_pool", {}) or {}
        )
        writer_markers_text = _build_writer_markers_text(paper_text)

        # 1. Pick opportunities — paragraph-level, full context
        opportunities = await select_opportunities(
            paper_text=paper_text,
            question=question,
            other_paragraphs_text=other_paras,
            image_pool_text=image_pool_text,
            writer_markers_text=writer_markers_text,
            settings=settings,
        )

        # 2. Prepare per-paper VLM client + image dir
        paper_dir = IMAGES_DIR / str(self.state.request_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

        # Handle writer-placed [[IMG:id]] markers first
        writer_embedded = await self._resolve_writer_markers(client, paper_dir, settings)
        embedded: list[dict] = list(writer_embedded)

        # 3. Parallel opportunity processing — all at once via asyncio.gather
        tasks = [
            _process_one_opportunity(
                self,
                opp,
                paper_dir,
                client,
                settings,
            )
            for opp in opportunities
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.warning("opportunity processing failed: %s", r)
                continue
            if isinstance(r, list):
                embedded.extend(r)

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
        """Replace [[IMG:short]] markers the paper writer emitted with real images."""
        markers = re_module.findall(r"\[\[IMG:([a-f0-9]{10})\]\]", self.state.paper_text)
        if not markers:
            return []

        short_to_cand: dict[str, dict] = {}
        for _angle_id, cands in (self.state.image_candidate_pool or {}).items():
            for c in cands or []:
                url = c.get("url", "") if isinstance(c, dict) else getattr(c, "url", "")
                if not url:
                    continue
                short = hashlib.sha1(url.encode()).hexdigest()[:10]
                short_to_cand.setdefault(short, c)

        embedded: list[dict] = []
        from pipeline.lyra.image_fetcher import ImageCandidate

        for i, short in enumerate(dict.fromkeys(markers)):
            cand_dict = short_to_cand.get(short)
            if not cand_dict:
                logger.info("[probative] writer marker %s not in pool; removing", short)
                self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", "")
                continue
            cand = ImageCandidate.from_dict(cand_dict) if isinstance(cand_dict, dict) else cand_dict

            final_path = paper_dir / f"writer_img_{i}.jpg"
            if not await download_candidate(cand, final_path):
                self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", "")
                continue

            web_path = f"/data/research-images/{self.state.request_id}/writer_img_{i}.jpg"
            rationale = "Image placed by the paper writer as visual evidence for this passage."
            md = image_markdown_with_group(cand, web_path, rationale, f"writer_{i}", True, True)
            self.state.paper_text = self.state.paper_text.replace(f"[[IMG:{short}]]", md, 1)

            embedded.append(
                {
                    "paragraph_index": -1,
                    "paragraph_text": "[writer-placed]",
                    "keyword": "writer-image",
                    "image_path": str(final_path),
                    "web_path": web_path,
                    "source_url": getattr(cand, "url", ""),
                    "source_name": getattr(cand, "source", ""),
                    "title": getattr(cand, "title", ""),
                    "artist": getattr(cand, "artist", ""),
                    "license": getattr(cand, "license", ""),
                    "license_url": getattr(cand, "license_url", ""),
                    "rationale": rationale,
                    "section_heading": "[inline]",
                    "search_query": "",
                }
            )
        return embedded


def _summarize_other_paragraphs(paper_text: str) -> str:
    """Build a deduplication summary of all paragraphs except the current one."""
    _SKIP = frozenset({"abstract", "introduction", "references", "sources"})
    lines = paper_text.split("\n")
    parts: list[str] = []
    current_section = ""
    paragraphs: list[tuple[str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        hm = re_module.match(r"^##\s+(.+)$", line)
        if hm:
            current_section = hm.group(1).strip().lower()
            i += 1
            continue
        if line.strip() and current_section not in _SKIP:
            para_lines = []
            while i < len(lines) and lines[i].strip():
                para_lines.append(lines[i])
                i += 1
            text = "\n".join(para_lines)
            if len(text) > 80 and not text.startswith("!["):
                paragraphs.append((current_section, text))
        else:
            i += 1

    if not paragraphs:
        return "(only one paragraph — no deduplication needed)"

    # Summarize each paragraph by section + first 80 chars
    for sec, txt in paragraphs:
        parts.append(f"[{sec}] {txt[:80]}...")
    return "\n".join(parts)


async def _process_one_opportunity(
    handler: ProbativeImagesHandler,
    opp: dict,
    paper_dir: Path,
    client,
    settings,
) -> list[dict]:
    """Process a single opportunity: resolve section, pool lookup, VLM gate, download, insert.

    Returns a list of embedded image dicts — up to
    `settings.probative_images_max_per_opportunity` (default 3) accepted
    candidates. Deduplicates by source_name so we don't embed three images from
    the same museum for one paragraph.
    """
    para_idx = opp.get("paragraph_index", -1)
    keyword = opp.get("keyword", "")
    para_text = opp.get("paragraph_text", "") or opp.get("what_image_must_show", "")
    section = opp.get("section", "")
    search_query = opp.get("search_query", "")
    must_show = opp.get("what_image_must_show", "")
    forbidden = opp.get("forbidden_elements", [])
    rationale = opp.get("rationale", "")

    if para_idx < 0 or not search_query:
        return []

    # Resolve section — prefer the opportunity's section field, fall back to registry
    section_name = section or None
    if not section_name:
        section_name = find_section_for_claim_with_registry(
            handler.state.paper_text, [], handler.state.registry
        )
    if not section_name:
        section_name = find_section_for_claim(handler.state.paper_text, para_text[:60])
    if not section_name:
        logger.info("[probative] no section matched for paragraph %s", para_idx)
        return []

    # Primary: pull from the image candidate pool
    cands = _pool_candidates_for_source_ids(
        handler.state.image_candidate_pool or {}, [], handler.state.angles
    )
    cands = [c for c in cands if metadata_gate_passes(c, must_show)]

    # Fallback: fetch on-demand
    if not cands:
        fetched = await fetch_candidates(
            search_query,
            limit_per_source=getattr(settings, "probative_images_candidates_per_opportunity", 20),
        )
        cands = [c for c in fetched if metadata_gate_passes(c, must_show)]

    if not cands:
        print(
            f"[probative] no candidates for para {para_idx} keyword '{keyword}' — will fallback to on-demand fetch",
            flush=True,
        )
        logger.info("[probative] no candidates for para %s keyword '%s'", para_idx, keyword)
        return []

    # Vision gate: iterate until we have target count of accepted candidates
    max_per_opp = getattr(settings, "probative_images_max_per_opportunity", 3)
    accepted: list = []
    seen_sources: set[str] = set()
    seen_urls: set[str] = set()

    for cand in cands:
        if len(accepted) >= max_per_opp:
            break
        cand_url = getattr(cand, "url", "") or ""
        cand_source = getattr(cand, "source", "") or ""
        if cand_url in seen_urls:
            continue
        # Diversify: skip if we already accepted from this source (only after first)
        if cand_source and cand_source in seen_sources and len(accepted) > 0:
            continue
        url_hash = hashlib.md5((cand_url or str(id(cand))).encode()).hexdigest()[:16]
        probe_path = paper_dir / f"_probe_p{para_idx}_{url_hash}.bin"
        ok = await download_candidate(cand, probe_path)
        if not ok:
            continue
        image_bytes = probe_path.read_bytes()
        prompt = build_vlm_prompt(para_text, must_show, forbidden)
        raw = await asyncio.to_thread(minimax_vlm, client, image_bytes, prompt)
        verdict = parse_vlm_verdict(raw)
        if verdict_is_accept(verdict):
            accepted.append(cand)
            seen_urls.add(cand_url)
            if cand_source:
                seen_sources.add(cand_source)
        if probe_path.exists():
            probe_path.unlink(missing_ok=True)

    if not accepted:
        print(
            f"[probative] VLM gate: no candidate survived for para {para_idx} keyword '{keyword}' — image NOT embedded",
            flush=True,
        )
        logger.info(
            "[probative] no candidate survived VLM for para %s keyword '%s'", para_idx, keyword
        )
        return []

    keyword_slug = re_module.sub(r"[^a-zA-Z0-9]", "_", keyword[:30])
    group_id = _group_id_for_section(section_name, para_idx)
    embedded: list[dict] = []

    for i, accepted_cand in enumerate(accepted):
        suffix = "" if i == 0 else f"_{i}"
        final_path = paper_dir / f"p{para_idx}_{keyword_slug}{suffix}.jpg"
        if not await download_candidate(accepted_cand, final_path):
            continue

        web_path = (
            f"/data/research-images/{handler.state.request_id}/"
            f"p{para_idx}_{keyword_slug}{suffix}.jpg"
        )
        is_first = i == 0
        is_last = i == len(accepted) - 1
        md = image_markdown_with_group(
            accepted_cand, web_path, rationale, group_id, is_first, is_last
        )

        new_text = insert_image_after_section(handler.state.paper_text, section_name, md)
        if new_text == handler.state.paper_text:
            logger.info("[probative] insert failed for section '%s'", section_name)
            continue
        handler.state.paper_text = new_text

        embedded.append(
            {
                "paragraph_index": para_idx,
                "paragraph_text": para_text[:200],
                "keyword": keyword,
                "image_path": str(final_path),
                "web_path": web_path,
                "source_url": getattr(accepted_cand, "url", ""),
                "source_name": getattr(accepted_cand, "source", ""),
                "title": getattr(accepted_cand, "title", ""),
                "artist": getattr(accepted_cand, "artist", ""),
                "license": getattr(accepted_cand, "license", ""),
                "license_url": getattr(accepted_cand, "license_url", ""),
                "rationale": rationale,
                "section_heading": section_name,
                "search_query": search_query,
            }
        )

    print(
        f"[probative] embedded {len(embedded)} images for para {para_idx} keyword '{keyword}'",
        flush=True,
    )
    return embedded
