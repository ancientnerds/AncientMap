"""Stage 1d: the one-off `news_items.entities->'sites'` vein — zero LLM.

Between 2026-03-05 and 2026-04-12 a since-retired NER pass wrote a list of
site names per item that nothing ever read. The names are unverified, so
each one is located in ITS OWN item's text with the same grounding the
model path uses: found verbatim -> a real evidence row with real offsets;
not found -> a hallucination of the old extractor, dropped and counted.
"""

from __future__ import annotations

import logging

from sqlalchemy import text as sql

from pipeline.lyra.prospector.corpus import StoryUnit, story_text
from pipeline.lyra.prospector.mentions import GroundingStats, Mention, ground_mentions
from pipeline.lyra.prospector.pipeline import EvidenceRef
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)

EXTRACTOR_TAG = "prospector_entities_legacy_v1"


def extract_legacy_entities(session) -> tuple[list[tuple[StoryUnit, Mention]], GroundingStats]:
    rows = session.execute(
        sql("""
        SELECT id, video_id, timestamp_seconds, headline, summary, facts,
               site_name_extracted, entities->'sites' AS sites
        FROM news_items
        WHERE jsonb_typeof(entities->'sites') = 'array'
        ORDER BY id
        """)
    ).fetchall()
    stats = GroundingStats()
    out: list[tuple[StoryUnit, Mention]] = []
    for r in rows:
        unit = StoryUnit(
            r.id, r.video_id, r.timestamp_seconds, story_text(r.headline, r.summary, r.facts)
        )
        already = normalize_name(r.site_name_extracted or "")
        names = [
            n
            for n in r.sites
            if isinstance(n, str) and normalize_name(n) and normalize_name(n) != already
        ]
        raw = [
            {
                "name_as_written": n,
                "place_class": "site",
                "country_as_written": "",
                "period_as_written": "",
            }
            for n in names
        ]
        for m in ground_mentions(raw, unit.text, 0, unit.text, stats):
            out.append((unit, m))
    logger.info(
        "[PROSPECTOR] legacy entities: %d items, %d names, %d grounded, %d dropped as unlocatable",
        len(rows),
        stats.emitted,
        stats.grounded,
        stats.rejected,
    )
    return out, stats


def to_pairs(found: list[tuple[StoryUnit, Mention]]) -> list[tuple[Mention, EvidenceRef]]:
    return [
        (m, EvidenceRef("entities_legacy", "news_items", str(u.item_id), u.locator, EXTRACTOR_TAG))
        for u, m in found
    ]
