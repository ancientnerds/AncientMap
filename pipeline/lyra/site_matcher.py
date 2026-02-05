"""Match extracted site names from news items to unified_sites in the database."""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from pipeline.database import (
    NewsItem,
    SiteName,
    SourceMeta,
    UnifiedSite,
    UserContribution,
    get_session,
)
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)

# Minimum name length to attempt matching (avoid "Rome", "Troy" false positives on LIKE)
MIN_NAME_LENGTH_FOR_LIKE = 6


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
    2. Exact match on site_names.name_normalized (alternate names)
    3. LIKE match on unified_sites.name_normalized (only for longer names)
    4. If multiple results, prefer curated sources
    5. Return None if ambiguous (0 or 2+ equally-ranked matches)
    """
    normalized = normalize_name(extracted_name)
    if not normalized or len(normalized) < 3:
        return None

    source_filter = UnifiedSite.source_id.in_(matchable_sources)

    # 1. Exact match on unified_sites.name_normalized
    matches = session.query(UnifiedSite).filter(
        UnifiedSite.name_normalized == normalized,
        source_filter,
    ).all()

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        return _pick_best_match(matches, source_priority)

    # 1.5. Spaceless match (handles "Gobekli Tepe" vs "Gobeklitepe")
    spaceless = normalized.replace(" ", "")
    matches = session.query(UnifiedSite).filter(
        func.replace(UnifiedSite.name_normalized, ' ', '') == spaceless,
        source_filter,
    ).all()

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return _pick_best_match(matches, source_priority)

    # 2. Exact match on site_names table (alternate names)
    site_name_matches = session.query(SiteName).filter(
        SiteName.name_normalized == normalized
    ).all()

    if site_name_matches:
        # Get the corresponding unified_sites via the Site -> UnifiedSite path
        # site_names links to sites table, but we need unified_sites
        # Try matching the site name's site.canonical_name against unified_sites
        site_ids = {sn.site_id for sn in site_name_matches}
        if len(site_ids) == 1:
            # All alternate names point to the same site - look it up in unified_sites
            from pipeline.database import Site
            site = session.get(Site, site_ids.pop())
            if site:
                unified = session.query(UnifiedSite).filter(
                    UnifiedSite.name_normalized == normalize_name(site.canonical_name)
                ).first()
                if unified:
                    return unified

    # 3. LIKE match (only for names long enough to avoid false positives)
    if len(normalized) >= MIN_NAME_LENGTH_FOR_LIKE:
        like_matches = session.query(UnifiedSite).filter(
            UnifiedSite.name_normalized.like(f"%{normalized}%"),
            func.length(UnifiedSite.name_normalized) <= len(normalized) * 2,
            source_filter,
        ).limit(5).all()

        if len(like_matches) == 1:
            return like_matches[0]

        if len(like_matches) > 1:
            return _pick_best_match(like_matches, source_priority)

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
        logger.info(f"Matchable sources from source_meta: {matchable_sources}")

        items = session.query(NewsItem).filter(
            NewsItem.site_name_extracted.isnot(None),
            NewsItem.site_id.is_(None),
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

    logger.info(f"Site matching complete: {matched}/{len(items)} items matched")
    return matched


def _upsert_lyra_suggestion(session: Session, item: NewsItem) -> None:
    """Upsert unmatched site name into user_contributions for curation."""
    normalized = normalize_name(item.site_name_extracted)
    if not normalized or len(normalized) < 3:
        return

    existing = session.query(UserContribution).filter(
        UserContribution.source == "lyra",
        func.lower(UserContribution.name) == normalized,
    ).first()

    if existing:
        existing.mention_count += 1
    else:
        session.add(UserContribution(
            name=item.site_name_extracted,
            source="lyra",
            mention_count=1,
            description=item.headline,
            source_url=f"https://www.youtube.com/watch?v={item.video_id}" if item.video_id else None,
        ))
