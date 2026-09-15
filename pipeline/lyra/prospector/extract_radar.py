"""Stage 1c: absorb the radar backlog — zero LLM, one queue.

Every lyra contribution that is still undecided (enriched) or was refused
by an LLM (rejected — the site is real, a proposed MATCH was rejected)
enters the proposals queue carrying `contribution_id`. What the radar already
enriched (QID, coordinates, country, type, description) is used as a
prefilled resolution so no Wikipedia call is repeated; the dedup ladder
runs as for any other candidate. A prior LLM rejection demotes rank and
shows a badge; only a founder dismissal is a human verdict and stays out.

Evidence is the contribution's own news items: the headline, deep-linked
to the video. The name is located in the headline when it is there; when
the headline was worded without it, the evidence row starts at 0 with the
whole headline as the quote — still a real sighting, just not a substring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text as sql

from pipeline.lyra.prospector.corpus import StoryUnit, story_text
from pipeline.lyra.prospector.mentions import Mention
from pipeline.lyra.prospector.pipeline import EvidenceRef, Prefill
from pipeline.lyra.prospector.resolve import Resolution
from pipeline.normalizers.dates import passes_date_cutoff
from pipeline.utils.text import clean_llm_name, normalize_name

logger = logging.getLogger(__name__)

EXTRACTOR_TAG = "prospector_radar_v1"


@dataclass
class RadarUnit:
    contribution_id: str
    name: str
    status: str
    wikidata_id: str | None
    lat: float | None
    lon: float | None
    country: str | None
    site_type: str | None
    period_start: int | None
    period_end: int | None
    description: str | None
    thumbnail_url: str | None
    wikipedia_url: str | None
    items: list[StoryUnit]


def load_radar_units(session) -> list[RadarUnit]:
    rows = session.execute(
        sql("""
        SELECT id::text AS id, name, corrected_name, enrichment_status, wikidata_id,
               lat, lon, country, site_type, period_start, period_end,
               description, thumbnail_url, wikipedia_url
        FROM user_contributions
        WHERE source = 'lyra' AND promoted_site_id IS NULL
          AND enrichment_status IN ('enriched', 'rejected')
        ORDER BY created_at
        """)
    ).fetchall()
    units: list[RadarUnit] = []
    for r in rows:
        name = clean_llm_name(r.corrected_name) or clean_llm_name(r.name)
        if not name:
            continue
        items = session.execute(
            sql("""
            SELECT id, video_id, timestamp_seconds, headline, summary, facts
            FROM news_items
            WHERE lower(trim(site_name_extracted)) IN (lower(trim(:a)), lower(trim(:b)))
            ORDER BY created_at
            """),
            {"a": r.name, "b": r.corrected_name or r.name},
        ).fetchall()
        units.append(
            RadarUnit(
                contribution_id=r.id,
                name=name,
                status=r.enrichment_status,
                wikidata_id=r.wikidata_id,
                lat=r.lat,
                lon=r.lon,
                country=r.country,
                site_type=r.site_type,
                period_start=r.period_start,
                period_end=r.period_end,
                description=r.description,
                thumbnail_url=r.thumbnail_url,
                wikipedia_url=r.wikipedia_url,
                items=[
                    StoryUnit(
                        i.id,
                        i.video_id,
                        i.timestamp_seconds,
                        story_text(i.headline, i.summary, i.facts),
                    )
                    for i in items
                ],
            )
        )
    return units


def prefill_for(unit: RadarUnit) -> Prefill:
    """Turn what the radar enriched into a Resolution — or None when it has
    no coordinates, in which case the normal resolver runs."""
    resolution = None
    if unit.lat is not None and unit.lon is not None:
        resolution = Resolution(
            name=unit.name,
            path="contribution",
            verdict="resolved",
            qid=unit.wikidata_id,
            label=unit.name,
            lat=float(unit.lat),
            lon=float(unit.lon),
            country=unit.country,
            site_type=unit.site_type,
            period_start=unit.period_start,
            period_end=unit.period_end,
            description=unit.description,
            thumbnail_url=unit.thumbnail_url,
            wikipedia_url=unit.wikipedia_url,
            in_scope=passes_date_cutoff(
                {"period_start": unit.period_start, "period_end": unit.period_end, "lon": unit.lon}
            ),
            note="coordinates and metadata from the radar's own enrichment",
        )
    return Prefill(
        resolution=resolution,
        contribution_id=unit.contribution_id,
        prior_verdict="llm_match_rejected" if unit.status == "rejected" else None,
    )


def mentions_for(unit: RadarUnit) -> list[tuple[Mention, EvidenceRef]]:
    out: list[tuple[Mention, EvidenceRef]] = []
    for item in unit.items:
        headline = item.text.split("\n", 1)[0]
        i = headline.lower().find(unit.name.lower())
        start, end = (i, i + len(unit.name)) if i >= 0 else (0, 0)
        out.append(
            (
                Mention(
                    name=unit.name,
                    place_class="site",
                    char_start=start,
                    char_end=end,
                    quote=headline,
                    quote_start=0,
                ),
                EvidenceRef("radar", "news_items", str(item.item_id), item.locator, EXTRACTOR_TAG),
            )
        )
    if not out:
        # A contribution whose news items were renamed away still exists as a
        # sighting; record the contribution itself so the card has a source.
        out.append(
            (
                Mention(
                    name=unit.name,
                    place_class="site",
                    char_start=0,
                    char_end=len(unit.name),
                    quote=unit.name,
                    quote_start=0,
                ),
                EvidenceRef(
                    "radar",
                    "user_contributions",
                    unit.contribution_id,
                    "/radar.html",
                    EXTRACTOR_TAG,
                ),
            )
        )
    return out


def group_key(unit: RadarUnit) -> str:
    return normalize_name(unit.name)
