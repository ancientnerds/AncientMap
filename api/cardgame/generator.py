"""CLI stat generator — compute stats for all Ancient Nerds sites.

Usage:
    python -m api.cardgame.generator

Queries all sites with source_id='ancient_nerds', computes stats via stats.py,
and bulk-upserts into card_stats.
"""

import sys
from collections import Counter

from sqlalchemy import func, text

from api.cardgame.models import CardStats
from api.cardgame.stats import compute_all_stats
from pipeline.database import (
    SiteBookmark,
    SiteContentLink,
    SiteLike,
    UnifiedSite,
    WikiImage,
    get_session,
)
from pipeline.historical_boundaries.tagger import tag_site


def _count_combos(session) -> dict[tuple[str | None, str | None], int]:
    """Count (site_type, period_name) combos across all Ancient Nerds sites."""
    rows = (
        session.query(
            UnifiedSite.site_type,
            UnifiedSite.period_name,
            func.count().label("cnt"),
        )
        .filter(UnifiedSite.source_id == "ancient_nerds")
        .group_by(UnifiedSite.site_type, UnifiedSite.period_name)
        .all()
    )
    return {(r.site_type, r.period_name): r.cnt for r in rows}


def _get_content_stats(session, site_id) -> tuple[int, int, bool]:
    """Return (content_link_count, distinct_content_types, has_3d_model)."""
    links = session.query(SiteContentLink).filter(SiteContentLink.site_id == site_id).all()
    content_types = set()
    has_3d = False
    for link in links:
        content_types.add(link.content_type)
        if link.content_type == "model" or link.content_source == "sketchfab":
            has_3d = True
    return len(links), len(content_types), has_3d


def _get_wiki_image_count(session, site_id) -> int:
    return (
        session.query(func.count())
        .select_from(WikiImage)
        .filter(WikiImage.site_id == site_id)
        .scalar()
    ) or 0


def _get_engagement(session, site_id) -> tuple[int, int]:
    """Return (like_count, bookmark_count)."""
    likes = (
        session.query(func.count())
        .select_from(SiteLike)
        .filter(SiteLike.site_id == site_id)
        .scalar()
    ) or 0
    bookmarks = (
        session.query(func.count())
        .select_from(SiteBookmark)
        .filter(SiteBookmark.site_id == site_id)
        .scalar()
    ) or 0
    return likes, bookmarks


def _is_unesco(site) -> bool:
    """Check if site is a UNESCO World Heritage Site.

    Checks description and source_url for UNESCO references.
    """
    checks = [site.description or "", site.source_url or ""]
    for text_val in checks:
        if "unesco" in text_val.lower() or "world heritage" in text_val.lower():
            return True
    return False


def _run_enrichment_migrations(session) -> None:
    """Add enrichment columns to card_stats if they don't exist."""
    columns = [
        ("wikidata_qid", "VARCHAR(20)"),
        ("confidence_score", "DOUBLE PRECISION"),
        ("source_language", "VARCHAR(10)"),
        ("heritage_designation", "TEXT"),
        ("inception_year", "INTEGER"),
        ("best_wiki_url", "VARCHAR(500)"),
        ("commons_image", "VARCHAR(500)"),
    ]
    for col_name, col_type in columns:
        session.execute(
            text(f"""
            DO $$
            BEGIN
                ALTER TABLE card_stats ADD COLUMN {col_name} {col_type};
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
        """)
        )
    session.commit()
    print("[CARDGAME] Enrichment columns ensured on card_stats", flush=True)


def _upsert_stats(session, sites, combo_counts, progress: bool) -> tuple[int, int, Counter]:
    """Compute and upsert card_stats for `sites`. Returns (created, updated, tiers)."""
    tier_counter: Counter = Counter()
    created = 0
    updated = 0
    total = len(sites)

    for i, site in enumerate(sites):
        # Gather data for stat computation
        content_link_count, content_type_count, has_3d = _get_content_stats(session, site.id)
        wiki_image_count = _get_wiki_image_count(session, site.id)
        like_count, bookmark_count = _get_engagement(session, site.id)
        combo_key = (site.site_type, site.period_name)
        combo_count = combo_counts.get(combo_key, 1)

        stats = compute_all_stats(
            period_start=site.period_start,
            period_end=site.period_end,
            site_type=site.site_type,
            has_description=bool(site.description),
            has_thumbnail=bool(site.thumbnail_url),
            content_link_count=content_link_count,
            wiki_image_count=wiki_image_count,
            has_source_url=bool(site.source_url),
            combo_count=combo_count,
            is_unesco=_is_unesco(site),
            like_count=like_count,
            bookmark_count=bookmark_count,
            content_type_count=content_type_count,
            has_3d_model=has_3d,
            country=site.country,
        )

        # Tag with empires
        empires = tag_site(
            lat=site.lat,
            lon=site.lon,
            period_start=site.period_start,
        )
        stats["empires"] = empires
        stats["empire_count"] = len(empires)

        # Upsert
        existing = session.get(CardStats, site.id)
        if existing:
            for key, value in stats.items():
                setattr(existing, key, value)
            updated += 1
        else:
            session.add(CardStats(site_id=site.id, **stats))
            created += 1

        tier_counter[stats["rarity_tier"]] += 1

        if progress and (i + 1) % 500 == 0:
            print(f"[CARDGAME] Processed {i + 1}/{total} sites...", flush=True)
            session.flush()

    session.flush()
    return created, updated, tier_counter


def backfill_placeholder_stats() -> int:
    """Compute stats for card_stats rows the description import left as placeholders.

    The card-description import in api/main.py inserts a zeroed row
    (rarity_tier=0, category_group='unknown') so a generated description has a row
    to live on. Every card query filters on rarity_tier, so such a row is a card
    that can never be drawn — by daily, starter, packs, quiz or expeditions.
    Returns the number of rows filled in.
    """
    with get_session() as session:
        site_ids = [
            r[0] for r in session.query(CardStats.site_id).filter(CardStats.rarity_tier == 0).all()
        ]
        if not site_ids:
            return 0

        sites = session.query(UnifiedSite).filter(UnifiedSite.id.in_(site_ids)).all()
        created, updated, _ = _upsert_stats(session, sites, _count_combos(session), progress=False)

    return created + updated


def generate_stats() -> None:
    """Compute stats for all Ancient Nerds sites that have a description.

    Sites with a description get card_stats rows (and thus card descriptions).
    Missing fields (thumbnail, period, type, country) are handled gracefully
    by the stat functions with sensible defaults.
    """
    with get_session() as session:
        _run_enrichment_migrations(session)

        sites = (
            session.query(UnifiedSite)
            .filter(
                UnifiedSite.source_id == "ancient_nerds",
                UnifiedSite.description.isnot(None),
                UnifiedSite.description != "",
            )
            .all()
        )
        total = len(sites)
        print(f"[CARDGAME] Found {total} Ancient Nerds sites with descriptions", flush=True)

        if total == 0:
            print("[CARDGAME] No sites found. Exiting.", flush=True)
            return

        # Pre-compute combo counts
        combo_counts = _count_combos(session)
        print(f"[CARDGAME] Computed {len(combo_counts)} type/period combos", flush=True)

        created, updated, tier_counter = _upsert_stats(session, sites, combo_counts, progress=True)

    # Print distribution report
    print(f"\n[CARDGAME] Done! Created {created}, updated {updated} card stats.", flush=True)
    print("[CARDGAME] Rarity distribution:", flush=True)
    from api.cardgame.constants import RARITY_NAMES

    for tier in sorted(tier_counter.keys()):
        name = RARITY_NAMES.get(tier, f"Tier {tier}")
        count = tier_counter[tier]
        pct = count / total * 100
        print(f"  {name}: {count} ({pct:.1f}%)", flush=True)


if __name__ == "__main__":
    generate_stats()
