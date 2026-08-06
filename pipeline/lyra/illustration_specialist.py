"""Runs the Illustration Specialist LLM pass that picks probative images.

Given a paper's paragraphs, returns a list of image opportunities with
multiple opportunities per paragraph — targeting 3+ per substantial paragraph.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from pipeline.lyra.minimax_shared import parse_fenced_json

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "illustration_specialist.txt"

# Hard requirements — without these, an opportunity is unusable downstream
# (no anchor to embed at, no query to fetch with). Everything else gets a
# safe default so the LLM occasionally omitting `forbidden_elements` or
# `rationale` doesn't drop the entire opportunity silently.
_REQUIRED_FIELDS = ("paragraph_index", "search_query")
_OPTIONAL_DEFAULTS: dict = {
    "keyword": "",
    "what_image_must_show": "",
    "forbidden_elements": [],
    "rationale": "",
}


def parse_opportunities(raw: str) -> list[dict]:
    """Parse the specialist LLM output into a list of opportunities.

    Only `paragraph_index` and `search_query` are hard-required. Other fields
    are filled with safe defaults if missing — the prior strict check silently
    dropped every opportunity in Run 10 because MiniMax was omitting one of
    the optional fields, producing 0 embedded images with no surfaced reason.
    """
    if not raw or not raw.strip():
        return []
    data = parse_fenced_json(raw, default=None, extract_object=True)
    if data is None:
        return []
    opps = data.get("opportunities", [])
    out: list[dict] = []
    dropped = 0
    for o in opps:
        if not isinstance(o, dict):
            dropped += 1
            continue
        missing = [k for k in _REQUIRED_FIELDS if k not in o or o.get(k) in (None, "")]
        if missing:
            dropped += 1
            logger.warning(
                "parse_opportunities: dropped opp missing required field(s) %s; got keys=%s",
                missing,
                sorted(o.keys()),
            )
            continue
        for k, default in _OPTIONAL_DEFAULTS.items():
            if k not in o or o.get(k) is None:
                o[k] = default if not isinstance(default, list) else list(default)
        out.append(o)
    if dropped:
        logger.warning("parse_opportunities: dropped %d opps from %d returned", dropped, len(opps))
    return out


def split_paper_into_paragraphs(paper_text: str) -> list[dict]:
    """Split paper text into paragraphs with section context.

    Skips abstract, introduction, references, and sources sections.
    Returns list of {text, paragraph_index, section, line_idx} where
    line_idx is the paragraph's first line in ``paper_text.split("\\n")``
    (used by research_images.inject_source_images for insertion).
    """
    _SKIP_SECTIONS = frozenset({"abstract", "introduction", "references", "sources"})

    lines = paper_text.split("\n")
    paragraphs: list[dict] = []
    current_section = ""
    paragraph_index = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            current_section = heading_match.group(1).strip().lower()
            i += 1
            continue

        if line.strip() and current_section not in _SKIP_SECTIONS:
            para_lines = []
            start_idx = i
            while i < len(lines) and lines[i].strip():
                para_lines.append(lines[i])
                i += 1
            para_text = "\n".join(para_lines)
            if len(para_text) > 80 and not para_text.startswith("!["):
                paragraphs.append(
                    {
                        "text": para_text,
                        "paragraph_index": paragraph_index,
                        "section": current_section,
                        "line_idx": start_idx,
                    }
                )
                paragraph_index += 1
        else:
            i += 1

    return paragraphs


_MAX_KEYWORD_CALLS_IN_FLIGHT = 20


async def _select_for_paragraph(
    paragraph: dict,
    question: str,
    other_paragraphs_text: str,
    image_pool_text: str,
    writer_markers_text: str,
    settings,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Run the specialist on one paragraph to extract keyword opportunities.

    Returns list of opportunities with paragraph_index, keyword, search_query,
    what_image_must_show, forbidden_elements, rationale.
    """
    from pipeline.lyra.minimax_shared import minimax_chat_anthropic

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    section = paragraph["section"]
    para_text = paragraph["text"]

    user_msg = (
        f"## Research Question / Thesis\n{question}\n\n"
        f"## Current Section: {section}\n\n"
        f"## Paragraph to Analyze\n{para_text}\n\n"
        f"## Other Paragraphs in This Paper (for deduplication)\n{other_paragraphs_text}\n\n"
        f"## Image Candidate Pool Available (already retrieved during research)\n{image_pool_text}\n\n"
        f"## Writer-Placed Images (do not duplicate these)\n{writer_markers_text}\n\n"
        f"Analyze the paragraph above and identify every concept that would genuinely "
        f"benefit from a visual. Return ALL visualizable concepts — minimum 3."
    )

    async with semaphore:
        raw = await asyncio.to_thread(
            minimax_chat_anthropic,
            system,
            user_msg,
            8192,  # more room for multiple opportunities per paragraph
            settings,
            temperature=0.1,
        )

    opps = parse_opportunities(raw)
    for o in opps:
        o["paragraph_index"] = paragraph["paragraph_index"]
        o["paragraph_text"] = para_text[:200]
        o["section"] = section

    return opps


async def select_opportunities(
    paper_text: str,
    question: str,
    other_paragraphs_text: str,
    image_pool_text: str,
    writer_markers_text: str,
    settings,
) -> list[dict]:
    """Pick which paragraph concepts merit probative images, running all calls in parallel.

    `paper_text` is the full paper markdown.
    `question` is the research question/thesis for disambiguation.
    `other_paragraphs_text` is a summary of other paragraphs for deduplication.
    `image_pool_text` is the available image candidate catalog.
    `writer_markers_text` is the list of writer-placed [[IMG:short]] markers.

    Each paragraph runs as an independent LLM call in parallel for maximum throughput.
    """
    paragraphs = split_paper_into_paragraphs(paper_text)
    if not paragraphs:
        return []

    semaphore = asyncio.Semaphore(_MAX_KEYWORD_CALLS_IN_FLIGHT)

    results = await asyncio.gather(
        *[
            _select_for_paragraph(
                p,
                question,
                other_paragraphs_text,
                image_pool_text,
                writer_markers_text,
                settings,
                semaphore,
            )
            for p in paragraphs
        ],
        return_exceptions=True,
    )

    out: list[dict] = []
    failed = 0
    for r in results:
        if isinstance(r, Exception):
            failed += 1
            logger.warning("select_opportunities: one paragraph failed: %s", r)
            continue
        out.extend(r)

    logger.info(
        "select_opportunities: %d opportunities from %d paragraphs (%d failed)",
        len(out),
        len(paragraphs),
        failed,
    )
    return out


async def select_opportunities_with_metrics(
    paper_text: str,
    question: str,
    other_paragraphs_text: str,
    image_pool_text: str,
    writer_markers_text: str,
    settings,
) -> tuple[list[dict], dict]:
    """Same as `select_opportunities` but also returns counts for telemetry.

    Use from `embed_probative_images` so a 0-opp run surfaces a clear reason on
    `state.debug_log` (Run 10 lost 9 minutes silently because the metrics never
    escaped this function).
    """
    paragraphs = split_paper_into_paragraphs(paper_text)
    if not paragraphs:
        return [], {"opportunities": 0, "paragraphs": 0, "failed": 0}

    semaphore = asyncio.Semaphore(_MAX_KEYWORD_CALLS_IN_FLIGHT)
    results = await asyncio.gather(
        *[
            _select_for_paragraph(
                p,
                question,
                other_paragraphs_text,
                image_pool_text,
                writer_markers_text,
                settings,
                semaphore,
            )
            for p in paragraphs
        ],
        return_exceptions=True,
    )
    out: list[dict] = []
    failed = 0
    for r in results:
        if isinstance(r, Exception):
            failed += 1
            logger.warning("select_opportunities: one paragraph failed: %s", r)
            continue
        out.extend(r)
    metrics = {"opportunities": len(out), "paragraphs": len(paragraphs), "failed": failed}
    logger.info(
        "select_opportunities: %d opportunities from %d paragraphs (%d failed)",
        len(out),
        len(paragraphs),
        failed,
    )
    return out, metrics
