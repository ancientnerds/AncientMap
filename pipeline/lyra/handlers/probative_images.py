"""Handler: fetches probative images for qualifying claims and embeds them.

Runs between PaperReady and FactCheckComplete. Produces a high-density image
gallery per section with multiple images per paragraph for YouTube video use.

The embed logic is exposed as the module-level `embed_probative_images()`
coroutine so it can be reused from a backfill CLI without the event bus.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re as re_module
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.illustration_specialist import select_opportunities_with_metrics
from pipeline.lyra.image_fetcher import download_candidate, fetch_candidates
from pipeline.lyra.image_gates import (
    build_vlm_prompt,
    metadata_gate_passes,
    parse_vlm_verdict,
    verdict_is_accept,
    verdict_is_safe,
)
from pipeline.lyra.minimax_shared import create_minimax_client, minimax_vlm
from pipeline.lyra.research_events import PaperReady, ProbativeImagesReady
from pipeline.lyra.research_state import ResearchPhase
from pipeline.lyra.theo_image_captions import (
    find_section_for_claim,
    find_section_for_claim_with_registry,
    image_markdown,
    insert_image_after_paragraph,
    resolve_section_heading,
)
from pipeline.utils.imagehash import DHASH_MAX_DISTANCE, dhash, hamming

logger = logging.getLogger(__name__)

IMAGES_DIR = Path(__file__).resolve().parents[3] / "public" / "data" / "research-images"

# Concurrency cap for `_process_one_opportunity`. Each opportunity does:
#   1. 0-1 on-demand fetch (HTTP fan-out) when the pool is empty for it
#   2. up to 3 download probes (HTTP)
#   3. up to 3 VLM gate calls (LLM)
# At 124 opportunities running in parallel (Run 11), the upstream services
# saturate and most opps see empty fetches and VLM errors. 6 keeps the queue
# warm while still finishing in reasonable wall time.
_EMBED_MAX_PARALLEL = 6


@dataclass
class _EmbedContext:
    """Shared mutable state for one embed run.

    Passed to `_process_one_opportunity` tasks instead of a handler. Safe under
    `asyncio.gather` because Python coroutines are single-threaded between
    `await` points — each paper_text read-modify-write is atomic.

    `placed_source_urls` prevents the same source image from landing twice in
    one paper (fixes the Dendera-zodiac duplication bug). A URL is claimed at
    selection time; released only if download/gate fail.

    `placed_subjects` dedupes by subject fingerprint so three Gilgamesh Flood
    Tablet photos from three different museums don't all stack on one paragraph.
    """

    paper_id: str
    paper_text: str
    image_candidate_pool: dict[str, list[dict]]
    angles: list
    registry: Any  # CitationRegistry
    paper_dir: Path
    client: Any  # MiniMax VLM client
    embedded: list[dict] = field(default_factory=list)
    placed_source_urls: set[str] = field(default_factory=set)
    placed_subjects: set[str] = field(default_factory=set)
    # Content-level dedup (2026-08-31). URL and subject dedup both miss the
    # case where two DIFFERENT catalogue entries resolve to the same picture:
    # the published solar-superflares paper carried one 194x110 Europeana
    # frame twice (identical bytes, item IDs 1151959 vs 1151659), and the
    # Petrie paper used a single photo as evidence for two separate claims.
    # md5 catches identical bytes, dhash the re-encoded/rescaled copies.
    placed_content_hashes: set[str] = field(default_factory=set)
    placed_dhashes: list[int] = field(default_factory=list)
    # Per-strategy embed counts surfaced on quality_score.meta as embed_*
    # so we can see in production how often each fallback path fired.
    # Keys: exact, normalized, first_sentence, section_fallback, failed.
    strategy_counts: dict[str, int] = field(default_factory=dict)
    # Per-section count of how many images landed via the section_fallback
    # strategy. Capped at 2 in _process_one_opportunity so a section with
    # many unmatched anchors doesn't pile up images before its next heading.
    section_fallback_counts: dict[str, int] = field(default_factory=dict)
    # Reason an opportunity didn't produce an embed. Keys:
    #   no_section, no_canonical_section, no_pool_candidates,
    #   no_fetched_candidates, all_unsafe_vlm, dedup_blocked,
    #   duplicate_content, anchor_match_failed, download_failed.
    # Surfaced on state.embed_skip_reasons so we can post-mortem failures
    # without container-log access (Run 11 silently lost 123/124 opps).
    skip_reasons: dict[str, int] = field(default_factory=dict)


def _claim_image_content(ctx, image_bytes: bytes) -> bool:
    """Claim this picture for the paper. False when it is already in it.

    The last dedup line, and the only one that looks at pixels: URL dedup
    fails when two catalogue entries point at the same file, subject dedup
    when neither carries a recognisable subject. Claims only on success, so
    a rejected duplicate never displaces the copy already placed.

    Undecodable bytes are claimed rather than rejected — a body we cannot
    read is not evidence that the picture is a repeat, and refusing it here
    would silently drop images over a Pillow quirk.
    """
    digest = hashlib.md5(image_bytes, usedforsecurity=False).hexdigest()
    if digest in ctx.placed_content_hashes:
        return False

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            fingerprint = dhash(img)
    except Exception:  # noqa: BLE001 — an unreadable body must not kill the run
        ctx.placed_content_hashes.add(digest)
        return True

    if any(hamming(fingerprint, seen) <= DHASH_MAX_DISTANCE for seen in ctx.placed_dhashes):
        return False

    ctx.placed_content_hashes.add(digest)
    ctx.placed_dhashes.append(fingerprint)
    return True


def _subject_fingerprint(cand) -> str:
    """Deterministic fingerprint for an image subject.

    Normalized title prefix — case-insensitive, punctuation stripped, filler
    words removed, first 40 chars. Two images of the same artifact from
    different museum vendors fingerprint identically.
    """
    title = (getattr(cand, "title", "") or "").lower()
    title = re_module.sub(r"[^a-z0-9 ]+", " ", title)
    title = re_module.sub(r"\b(the|of|or|a|an|and)\b", " ", title)
    title = re_module.sub(r"\s+", " ", title).strip()
    return title[:40]


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

    for sec, txt in paragraphs:
        parts.append(f"[{sec}] {txt[:80]}...")
    return "\n".join(parts)


async def _resolve_writer_markers(ctx: _EmbedContext) -> list[dict]:
    """Replace [[IMG:short]] markers the paper writer emitted with real images."""
    markers = re_module.findall(r"\[\[IMG:([a-f0-9]{10})\]\]", ctx.paper_text)
    if not markers:
        return []

    short_to_cand: dict[str, dict] = {}
    for _angle_id, cands in (ctx.image_candidate_pool or {}).items():
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
            ctx.paper_text = ctx.paper_text.replace(f"[[IMG:{short}]]", "")
            continue
        cand = ImageCandidate.from_dict(cand_dict) if isinstance(cand_dict, dict) else cand_dict

        cand_url = getattr(cand, "url", "") or ""
        if cand_url and cand_url in ctx.placed_source_urls:
            logger.info("[probative] skip duplicate writer image %s", cand_url)
            ctx.paper_text = ctx.paper_text.replace(f"[[IMG:{short}]]", "")
            continue

        final_path = ctx.paper_dir / f"writer_img_{i}.jpg"
        if not await download_candidate(cand, final_path):
            ctx.paper_text = ctx.paper_text.replace(f"[[IMG:{short}]]", "")
            continue

        # Same picture, different catalogue entry: drop the file rather than
        # leave an orphan in the paper directory.
        if not _claim_image_content(ctx, final_path.read_bytes()):
            logger.info("[probative] skip duplicate writer image content %s", cand_url)
            final_path.unlink(missing_ok=True)
            ctx.paper_text = ctx.paper_text.replace(f"[[IMG:{short}]]", "")
            continue

        web_path = f"/data/research-images/{ctx.paper_id}/writer_img_{i}.jpg"
        # No rationale for writer-placed images: the old placeholder ("Image
        # placed by the paper writer as visual evidence...") leaked editorial
        # meta-voice into public captions. Empty tail = caption shows only
        # title + attribution.
        md = image_markdown(cand, web_path, "")
        ctx.paper_text = ctx.paper_text.replace(f"[[IMG:{short}]]", md, 1)
        if cand_url:
            ctx.placed_source_urls.add(cand_url)

        embedded.append(
            {
                "paragraph_index": -1,
                "paragraph_text": "[writer-placed]",
                "keyword": "writer-image",
                "image_path": str(final_path),
                "web_path": web_path,
                "source_url": cand_url,
                "source_name": getattr(cand, "source", ""),
                "title": getattr(cand, "title", ""),
                "description": getattr(cand, "description", "")
                or (getattr(cand, "metadata", {}) or {}).get("description", ""),
                "artist": getattr(cand, "artist", ""),
                "license": getattr(cand, "license", ""),
                "license_url": getattr(cand, "license_url", ""),
                "rationale": "",
                "section_heading": "[inline]",
                "search_query": "",
            }
        )
    return embedded


async def embed_probative_images(
    paper_id: str,
    paper_text: str,
    question: str,
    angles: list,
    registry: Any,
    image_candidate_pool: dict[str, list[dict]] | None = None,
    *,
    settings=None,
    emit: Callable[[dict], None] | None = None,
) -> tuple[str, list[dict], dict, dict[str, int]]:
    """Embed probative images into a research paper.

    Reusable from both the live pipeline handler and the backfill CLI. Does
    all the work that used to live inside `ProbativeImagesHandler._on_paper_ready`
    except for event-bus emissions and state-machine transitions.

    Parameters
    ----------
    paper_id: id of the research_requests row — used to namespace the image
        directory (`/data/research-images/<paper_id>/`) and web paths.
    paper_text: full paper markdown. Will have image markdown inserted after
        relevant section headings.
    question: the original user question, passed through to the illustration
        specialist for relevance scoring.
    angles: list of ResearchAngle (or equivalent) objects with `.id`. Used
        when the pool is provided. Pass `[]` for pure on-demand fetching.
    registry: CitationRegistry used by `find_section_for_claim_with_registry`.
        Pass `None` for backfill where no registry was persisted.
    image_candidate_pool: output of `AngleImageResearchHandler`. When `None` or
        empty, `_process_one_opportunity` falls back to on-demand `fetch_candidates`.
    settings: optional settings override (defaults to `_get_settings()`).
    emit: optional SSE emit callback. Defaults to a no-op.

    Returns
    -------
    tuple of (new_paper_text, embedded_list, diversity_dict, strategy_counts).
    `strategy_counts` keys: exact, normalized, first_sentence, section_fallback,
    failed, skipped_fallback_cap. Useful telemetry for tuning the matcher.
    """
    settings = settings or _get_settings()
    emit = emit or (lambda _e: None)

    if not getattr(settings, "probative_images_enabled", True):
        print("[probative] disabled by config, skipping", flush=True)
        return (paper_text, [], {})

    pool = image_candidate_pool or {}
    if not pool:
        print(
            f"[probative] WARNING: image_candidate_pool is EMPTY for request {paper_id} — "
            "on-demand fetch will run per opportunity",
            flush=True,
        )
        logger.warning(
            "[probative] image_candidate_pool is EMPTY — falling back to on-demand fetch"
        )
    else:
        total = sum(len(v) for v in pool.values())
        print(
            f"[probative] image_candidate_pool has {len(pool)} angles, {total} total candidates",
            flush=True,
        )

    emit({"type": "pipeline", "stage": "probative_images", "status": "start"})

    # 1. Ask the illustration specialist for opportunities (LLM per paragraph)
    other_paras = _summarize_other_paragraphs(paper_text)
    image_pool_text = _build_image_pool_text(pool)
    writer_markers_text = _build_writer_markers_text(paper_text)

    opportunities, opp_metrics = await select_opportunities_with_metrics(
        paper_text=paper_text,
        question=question,
        other_paragraphs_text=other_paras,
        image_pool_text=image_pool_text,
        writer_markers_text=writer_markers_text,
        settings=settings,
    )
    # Echo the count to the SSE stream so result_json captures it (the prior
    # logger.info was Python-stdout only, invisible in published artifacts).
    emit(
        {
            "type": "pipeline",
            "stage": "probative_images",
            "status": "progress",
            "meta": {
                "opportunities_selected": opp_metrics["opportunities"],
                "paragraphs_scanned": opp_metrics["paragraphs"],
                "paragraph_calls_failed": opp_metrics["failed"],
                "candidate_pool_size": sum(len(v or []) for v in (pool or {}).values()),
            },
        }
    )

    # 2. Prepare per-paper VLM client + image dir
    paper_dir = IMAGES_DIR / str(paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

    ctx = _EmbedContext(
        paper_id=str(paper_id),
        paper_text=paper_text,
        image_candidate_pool=pool,
        angles=angles or [],
        registry=registry,
        paper_dir=paper_dir,
        client=client,
    )

    try:
        # 3. Resolve writer-placed markers first
        writer_embedded = await _resolve_writer_markers(ctx)
        ctx.embedded.extend(writer_embedded)

        # 4. Bounded-parallel opportunity processing.
        # Run 11: 124 opportunities fired concurrently → only 1 embed survived.
        # Each opportunity does an on-demand fetch (HTTP) + 1-3 VLM calls (LLM).
        # 124 simultaneous fetch+VLM cascades saturate the upstream services
        # (Wikimedia rate limits; MiniMax queue) and most return errors. A
        # semaphore of 6 keeps the candidate pool warm while still finishing
        # in reasonable wall time (124 / 6 ≈ 21 batches × ~10s = ~3 min).
        embed_sem = asyncio.Semaphore(_EMBED_MAX_PARALLEL)

        async def _bounded(opp):
            async with embed_sem:
                return await _process_one_opportunity(ctx, opp, settings)

        tasks = [_bounded(opp) for opp in opportunities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        excepted = 0
        for r in results:
            if isinstance(r, Exception):
                excepted += 1
                logger.warning("opportunity processing failed: %s", r)
                continue
            if isinstance(r, list):
                ctx.embedded.extend(r)
        if excepted:
            logger.warning("[probative] %d/%d opps raised exceptions", excepted, len(opportunities))
    finally:
        client.close()

    from pipeline.lyra.image_diversity import compute_diversity

    diversity = compute_diversity(ctx.embedded)

    logger.info(
        "[probative] embedded %d images, source_diversity=%.2f (%d sources: %s)",
        len(ctx.embedded),
        diversity["source_diversity"],
        diversity["source_count"],
        ", ".join(diversity["sources"]),
    )
    skip_reasons = dict(ctx.skip_reasons)
    if skip_reasons:
        logger.info("[probative] skip_reasons=%s", skip_reasons)
    emit(
        {
            "type": "pipeline",
            "stage": "probative_images",
            "status": "done",
            "meta": {
                "embedded": len(ctx.embedded),
                "skip_reasons": skip_reasons,
                **diversity,
            },
        }
    )

    return (
        ctx.paper_text,
        ctx.embedded,
        diversity,
        dict(ctx.strategy_counts),
        skip_reasons,
    )


class ProbativeImagesHandler(BaseHandler):
    """Thin event-bus wrapper around `embed_probative_images`."""

    def register(self):
        self.bus.on(PaperReady, self._on_paper_ready)

    async def _on_paper_ready(self, event: PaperReady):
        self.state.phase = ResearchPhase.IMAGE_CURATION

        (
            new_paper_text,
            embedded,
            diversity,
            strategy_counts,
            skip_reasons,
        ) = await embed_probative_images(
            paper_id=str(self.state.request_id),
            paper_text=self.state.paper_text or "",
            question=getattr(self.state, "question", "") or "",
            angles=self.state.angles,
            registry=self.state.registry,
            image_candidate_pool=getattr(self.state, "image_candidate_pool", {}) or {},
            emit=self.emit_sse,
        )

        self.state.paper_text = new_paper_text
        self.state.probative_images = embedded
        self.state.probative_images_diversity = diversity
        # Stash strategy counts so the judge handler can surface them on
        # quality_score.meta as embed_*. Lets us see in production how often
        # each anchor-matching path fires (or how often the section-end
        # fallback is rescuing us).
        self.state.embed_strategy_counts = strategy_counts
        # Per-reason skip counts. Lets us see why opportunities die at scale
        # without scraping container logs (Run 11: 124 opps, 1 embed, no
        # surfaced reason).
        self.state.embed_skip_reasons = skip_reasons

        await self.bus.emit(ProbativeImagesReady(embedded_count=len(embedded)))


async def _process_one_opportunity(
    ctx: _EmbedContext,
    opp: dict,
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
        ctx.skip_reasons["bad_input"] = ctx.skip_reasons.get("bad_input", 0) + 1
        return []

    # Resolve section — prefer the opportunity's section field, fall back to registry
    section_name = section or None
    if not section_name and ctx.registry is not None:
        section_name = find_section_for_claim_with_registry(ctx.paper_text, [], ctx.registry)
    if not section_name:
        section_name = find_section_for_claim(ctx.paper_text, para_text[:60])
    if not section_name:
        logger.info("[probative] no section matched for paragraph %s", para_idx)
        ctx.skip_reasons["no_section"] = ctx.skip_reasons.get("no_section", 0) + 1
        return []

    # Normalize section heading to the paper's actual canonical form — the
    # LLM often returns a near-variant ("Sky Beings..." vs "sky beings...")
    # that `insert_image_after_section` (exact match) would silently drop.
    canonical = resolve_section_heading(ctx.paper_text, section_name)
    if not canonical:
        canonical = find_section_for_claim(ctx.paper_text, para_text[:60])
    if not canonical:
        print(
            f"[probative] section '{section_name}' not found in paper for para {para_idx} "
            f"keyword '{keyword}' — skipping",
            flush=True,
        )
        ctx.skip_reasons["no_canonical_section"] = (
            ctx.skip_reasons.get("no_canonical_section", 0) + 1
        )
        return []
    section_name = canonical

    # Primary: pull from the image candidate pool
    cands = _pool_candidates_for_source_ids(ctx.image_candidate_pool or {}, [], ctx.angles)
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
            f"[probative] no candidates for para {para_idx} keyword '{keyword}' — "
            f"on-demand fetch also empty",
            flush=True,
        )
        logger.info("[probative] no candidates for para %s keyword '%s'", para_idx, keyword)
        ctx.skip_reasons["no_candidates"] = ctx.skip_reasons.get("no_candidates", 0) + 1
        return []

    # Embed up to N candidates per opportunity. VLM tags each as verified or
    # unverified but does NOT gate embedding — the reviewer decides in the UI.
    # Only forbidden-elements and poor-quality are safety rejects.
    max_per_opp = getattr(settings, "probative_images_max_per_opportunity", 3)
    tagged: list[tuple] = []  # (cand, verified_bool)
    seen_subjects: set[str] = set()
    seen_urls: set[str] = set()

    for cand in cands:
        if len(tagged) >= max_per_opp:
            break
        cand_url = getattr(cand, "url", "") or ""
        cand_subject = _subject_fingerprint(cand)
        if cand_url in seen_urls:
            continue
        # Cross-opportunity dedup: same source image must not land twice in
        # one paper (the Dendera-zodiac bug). Claim the URL now so parallel
        # tasks racing on the same candidate don't both embed it.
        if cand_url and cand_url in ctx.placed_source_urls:
            continue
        # Cross-opportunity subject dedup: same artifact from a different
        # museum must not appear in two different sections.
        if cand_subject and cand_subject in ctx.placed_subjects:
            continue
        # Per-opportunity subject dedup: three Gilgamesh Flood Tablet photos
        # from three museums collapse to one image for this paragraph.
        if cand_subject and cand_subject in seen_subjects:
            continue
        if cand_url:
            ctx.placed_source_urls.add(cand_url)
        url_hash = hashlib.md5((cand_url or str(id(cand))).encode()).hexdigest()[:16]
        probe_path = ctx.paper_dir / f"_probe_p{para_idx}_{url_hash}.bin"
        ok = await download_candidate(cand, probe_path)
        if not ok:
            if cand_url:
                ctx.placed_source_urls.discard(cand_url)
            continue
        image_bytes = probe_path.read_bytes()
        # Content dedup BEFORE the VLM call: a picture already in the paper
        # cannot become admissible by being judged again, and the vision
        # call is the expensive step here.
        if not _claim_image_content(ctx, image_bytes):
            logger.info(
                "[probative] skip duplicate image content for para %d: %s",
                para_idx,
                (cand.title or cand_url or "")[:80],
            )
            ctx.skip_reasons["duplicate_content"] = ctx.skip_reasons.get("duplicate_content", 0) + 1
            if cand_url:
                ctx.placed_source_urls.discard(cand_url)
            probe_path.unlink(missing_ok=True)
            continue
        prompt = build_vlm_prompt(para_text, must_show, forbidden)
        raw = await asyncio.to_thread(minimax_vlm, ctx.client, image_bytes, prompt)
        verdict = parse_vlm_verdict(raw)
        if not verdict_is_safe(verdict):
            # Diagnostic: distinguish (a) malformed VLM JSON from
            # (b) strict-judge rejection. Run #10 dropped 128 of 138
            # candidates here with no breadcrumb to tell which mode
            # dominated. Without this log we can't tune the prompt or
            # the parser.
            reason = (
                "malformed-json" if verdict is None else f"verdict={verdict.get('verdict', '?')!r}"
            )
            logger.info(
                "[probative] rejected candidate (%s) for para %d keyword '%s': %s",
                reason,
                para_idx,
                keyword[:40],
                (cand.title or cand.url or "")[:80],
            )
            if cand_url:
                ctx.placed_source_urls.discard(cand_url)
            if probe_path.exists():
                probe_path.unlink(missing_ok=True)
            continue
        verified = verdict_is_accept(verdict)
        tagged.append((cand, verified))
        seen_urls.add(cand_url)
        if cand_subject:
            seen_subjects.add(cand_subject)
            ctx.placed_subjects.add(cand_subject)
        if probe_path.exists():
            probe_path.unlink(missing_ok=True)

    if not tagged:
        print(
            f"[probative] no safe candidates for para {para_idx} keyword '{keyword}' — image NOT embedded",
            flush=True,
        )
        ctx.skip_reasons["no_safe_candidates"] = ctx.skip_reasons.get("no_safe_candidates", 0) + 1
        return []

    keyword_slug = re_module.sub(r"[^a-zA-Z0-9]", "_", keyword[:30])
    embedded: list[dict] = []

    # Gallery marker: when 2+ images land on the same paragraph, prefix each
    # alt text with `gallery:<hash>|verified:<y|n>|` so the frontend groups
    # them into a carousel instead of a stacked mosaic.
    is_gallery = len(tagged) > 1
    para_hash = (
        hashlib.sha1((para_text[:100] or str(para_idx)).encode("utf-8")).hexdigest()[:8]
        if is_gallery
        else ""
    )

    for i, (accepted_cand, verified) in enumerate(tagged):
        suffix = "" if i == 0 else f"_{i}"
        final_path = ctx.paper_dir / f"p{para_idx}_{keyword_slug}{suffix}.jpg"
        if not await download_candidate(accepted_cand, final_path):
            continue

        web_path = f"/data/research-images/{ctx.paper_id}/p{para_idx}_{keyword_slug}{suffix}.jpg"
        md = image_markdown(accepted_cand, web_path, rationale)
        if is_gallery:
            prefix = f"gallery:{para_hash}|verified:{'yes' if verified else 'no'}|"
            md = re_module.sub(
                r"!\[([^\]]*)\]",
                lambda m: f"![{prefix}{m.group(1)}]",
                md,
                count=1,
            )

        new_text, strategy = insert_image_after_paragraph(
            ctx.paper_text, section_name, para_text[:60], md
        )
        # Cap section_fallback at ≤2 per section so unmatched anchors in a
        # single section don't pile a stack of images before the next heading.
        if strategy == "section_fallback":
            already = ctx.section_fallback_counts.get(section_name, 0)
            if already >= 2:
                print(
                    f"[probative] SKIP: section '{section_name}' already has "
                    f"{already} fallback images; not stacking another for para "
                    f"{para_idx} keyword '{keyword}'",
                    flush=True,
                )
                ctx.strategy_counts["skipped_fallback_cap"] = (
                    ctx.strategy_counts.get("skipped_fallback_cap", 0) + 1
                )
                continue
            ctx.section_fallback_counts[section_name] = already + 1
        if strategy == "failed":
            print(
                f"[probative] INSERT FAILED: section '{section_name}' itself not "
                f"locatable for para {para_idx} keyword '{keyword}' — image "
                "downloaded but not placed",
                flush=True,
            )
            ctx.strategy_counts["failed"] = ctx.strategy_counts.get("failed", 0) + 1
            continue
        ctx.strategy_counts[strategy] = ctx.strategy_counts.get(strategy, 0) + 1
        ctx.paper_text = new_text

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
                "description": getattr(accepted_cand, "description", "")
                or (getattr(accepted_cand, "metadata", {}) or {}).get("description", ""),
                "artist": getattr(accepted_cand, "artist", ""),
                "license": getattr(accepted_cand, "license", ""),
                "license_url": getattr(accepted_cand, "license_url", ""),
                "rationale": rationale,
                "section_heading": section_name,
                "search_query": search_query,
                "verified": verified,
            }
        )

    verified_count = sum(1 for _, v in tagged if v)
    print(
        f"[probative] embedded {len(embedded)} images for para {para_idx} keyword '{keyword}' "
        f"(verified={verified_count}, unverified={len(tagged) - verified_count})",
        flush=True,
    )
    return embedded
