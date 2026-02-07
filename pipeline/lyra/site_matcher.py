"""Match extracted site names from news items to unified_sites in the database."""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from pipeline.database import (
    NewsItem,
    NewsVideo,
    SourceMeta,
    UnifiedSite,
    UnifiedSiteName,
    UserContribution,
    get_session,
)
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)


def _load_source_priority(session: Session) -> dict[str, int]:
    """Load source priorities from source_meta. Lower priority = better source."""
    rows = session.query(SourceMeta.id, SourceMeta.priority).filter(SourceMeta.enabled.is_(True)).all()
    return {row.id: row.priority for row in rows}


def _find_site_by_name(
    session: Session,
    extracted_name: str,
    matchable_sources: list[str],
    source_priority: dict[str, int],
) -> UnifiedSite | None:
    """Try to find a single matching UnifiedSite for an extracted site name.

    Strategy:
    1. Exact match on unified_sites.name_normalized
    1.5. Spaceless match on unified_sites.name_normalized
    2. Exact match on unified_site_names.name_normalized (alternate names)
    2.5. Spaceless match on unified_site_names.name_normalized
    If multiple results, prefer curated sources (lowest priority number).
    """
    normalized = normalize_name(extracted_name)
    if not normalized or len(normalized) < 3:
        return None

    source_filter = UnifiedSite.source_id.in_(matchable_sources)
    spaceless = normalized.replace(" ", "")

    # 1+1.5. Exact + spaceless match on unified_sites.name_normalized
    # Merged so "gobekli tepe" (exact) and "gobeklitepe" (spaceless) compete on priority.
    exact = session.query(UnifiedSite).filter(
        UnifiedSite.name_normalized == normalized,
        source_filter,
    ).all()
    spaceless_matches = session.query(UnifiedSite).filter(
        func.replace(UnifiedSite.name_normalized, ' ', '') == spaceless,
        source_filter,
    ).all()
    combined = {m.id: m for m in exact + spaceless_matches}

    if len(combined) == 1:
        return list(combined.values())[0]
    if len(combined) > 1:
        return _pick_best_match(list(combined.values()), source_priority)

    # 2+2.5. Exact + spaceless match on unified_site_names (alternate names)
    alt_exact = session.query(UnifiedSiteName).filter(
        UnifiedSiteName.name_normalized == normalized
    ).all()
    alt_spaceless = session.query(UnifiedSiteName).filter(
        func.replace(UnifiedSiteName.name_normalized, ' ', '') == spaceless
    ).all()
    alt_site_ids = {m.site_id for m in alt_exact + alt_spaceless}

    if alt_site_ids:
        candidates = session.query(UnifiedSite).filter(
            UnifiedSite.id.in_(alt_site_ids), source_filter
        ).all()
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return _pick_best_match(candidates, source_priority)

    return None


def _pick_best_match(matches: list[UnifiedSite], source_priority: dict[str, int]) -> UnifiedSite | None:
    """Pick the best match from multiple candidates, preferring lowest priority (most curated)."""
    return min(matches, key=lambda m: source_priority.get(m.source_id, 99))


def match_sites_for_pending_items() -> int:
    """Match site names for all NewsItems that have site_name_extracted but no site_id.

    Returns number of items matched.
    """
    matched = 0

    with get_session() as session:
        source_priority = _load_source_priority(session)
        matchable_sources = list(source_priority.keys())

        items = session.query(NewsItem).filter(
            NewsItem.site_name_extracted.isnot(None),
            NewsItem.site_id.is_(None),
            NewsItem.site_match_tried.is_(False),
        ).all()

        if not items:
            return 0

        logger.info(f"Attempting site matching for {len(items)} news items")

        for item in items:
            site = _find_site_by_name(session, item.site_name_extracted, matchable_sources, source_priority)
            if site:
                item.site_id = site.id
                matched += 1
                logger.info(
                    f"Matched item {item.id} '{item.site_name_extracted}' -> "
                    f"site '{site.name}' ({site.id})"
                )
            else:
                logger.debug(f"No match for item {item.id} '{item.site_name_extracted}'")
                _upsert_lyra_suggestion(session, item)
            item.site_match_tried = True

    logger.info(f"Site matching complete: {matched}/{len(items)} items matched")
    return matched


def _extract_topic_metadata(session: Session, item: NewsItem) -> dict:
    """Extract country, site_type, period from summary_json for the matching topic."""
    video = session.get(NewsVideo, item.video_id)
    if not video or not video.summary_json:
        return {}

    topics = video.summary_json.get("key_topics", [])
    for topic in topics:
        primary_site = topic.get("primary_site")
        if not primary_site or not isinstance(primary_site, dict):
            continue
        # Match by site name
        if primary_site.get("name") and normalize_name(primary_site["name"]) == normalize_name(item.site_name_extracted):
            return {
                "country": primary_site.get("country"),
                "site_type": primary_site.get("site_type"),
                "period_name": primary_site.get("period"),
            }
    return {}


def _upsert_lyra_suggestion(session: Session, item: NewsItem) -> None:
    """Upsert unmatched site name into user_contributions for curation."""
    normalized = normalize_name(item.site_name_extracted)
    if not normalized or len(normalized) < 3:
        return

    metadata = _extract_topic_metadata(session, item)

    existing = session.query(UserContribution).filter(
        UserContribution.source == "lyra",
        func.lower(UserContribution.name) == normalized,
    ).first()

    if existing:
        existing.mention_count += 1
        # Update metadata if we have better data now
        if metadata.get("country") and not existing.country:
            existing.country = metadata["country"]
        if metadata.get("site_type") and not existing.site_type:
            existing.site_type = metadata["site_type"]
        if metadata.get("period_name") and not existing.period_name:
            existing.period_name = metadata["period_name"]
    else:
        session.add(UserContribution(
            name=item.site_name_extracted,
            source="lyra",
            mention_count=1,
            description=item.headline,
            country=metadata.get("country"),
            site_type=metadata.get("site_type"),
            period_name=metadata.get("period_name"),
            source_url=f"https://www.youtube.com/watch?v={item.video_id}" if item.video_id else None,
        ))
