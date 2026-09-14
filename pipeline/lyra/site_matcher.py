"""Match extracted site names from news items to unified_sites in the database."""

import json
import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import (
    NewsItem,
    NewsVideo,
    SourceMeta,
    UnifiedSite,
    UserContribution,
    get_session,
)
from pipeline.utils.text import (
    categorize_period,
    extract_period_from_text,
    normalize_name,
    normalize_transliteration,
)

logger = logging.getLogger(__name__)

# Module-level cache for lyra contribution lookup (built once per match_sites_for_pending_items call)
_lyra_contrib_cache: dict[str, UserContribution] | None = None


def _build_lyra_contrib_cache(session: Session) -> dict[str, UserContribution]:
    """Build a normalize_name → UserContribution lookup for all lyra contributions."""
    all_lyra = (
        session.query(UserContribution)
        .filter(
            UserContribution.source == "lyra",
        )
        .all()
    )
    cache: dict[str, UserContribution] = {}
    for contrib in all_lyra:
        key = normalize_name(contrib.corrected_name or contrib.name)
        if key and key not in cache:
            cache[key] = contrib
    return cache


def _find_lyra_contribution(session: Session, normalized: str) -> UserContribution | None:
    """Find an existing lyra contribution by normalized name."""
    global _lyra_contrib_cache
    if _lyra_contrib_cache is None:
        _lyra_contrib_cache = _build_lyra_contrib_cache(session)
    return _lyra_contrib_cache.get(normalized)


def _load_source_priority(session: Session) -> dict[str, int]:
    """Load source priorities from source_meta. Lower priority = better source."""
    rows = (
        session.query(SourceMeta.id, SourceMeta.priority).filter(SourceMeta.enabled.is_(True)).all()
    )
    return {row.id: row.priority for row in rows}


# Country/region names that should never match as archaeological sites
_GENERIC_NAME_BLOCKLIST = {
    "egypt",
    "peru",
    "turkey",
    "greece",
    "italy",
    "spain",
    "france",
    "germany",
    "england",
    "scotland",
    "ireland",
    "wales",
    "india",
    "china",
    "japan",
    "mexico",
    "brazil",
    "colombia",
    "bolivia",
    "chile",
    "argentina",
    "iran",
    "iraq",
    "syria",
    "jordan",
    "israel",
    "palestine",
    "lebanon",
    "libya",
    "tunisia",
    "morocco",
    "algeria",
    "ethiopia",
    "kenya",
    "tanzania",
    "sudan",
    "cambodia",
    "indonesia",
    "thailand",
    "vietnam",
    "australia",
    "canada",
    "iceland",
    "norway",
    "sweden",
    "denmark",
    "finland",
    "russia",
    "ukraine",
    "portugal",
    "croatia",
    "serbia",
    "africa",
    "europe",
    "asia",
    "americas",
    "sahara",
    "sahara desert",
    "mediterranean",
    "atlantic",
    "pacific",
    "siberia",
    "anatolia",
    "mesopotamia",
    "levant",
    "balkans",
    "scandinavia",
    "polynesia",
    "melanesia",
    "micronesia",
    "north america",
    "south america",
    "central america",
    "middle east",
    "near east",
    "far east",
    "north africa",
    "west africa",
    "east africa",
}


# unified_sites.name_normalized and unified_site_names.name_normalized are
# maintained by Postgres as `left(lower(unaccent(name)), 500)` — see the two
# UPDATEs in orchestrator.py's startup migrations. That is NOT what
# normalize_name() produces: NFKD leaves the Turkish dotless ı and the Danish ø
# alone where unaccent folds them, and normalize_name strips parenthesised
# suffixes where the column keeps them. Measured on prod 2026-09-14: 124 of the
# 5,004 curated sites (2.5%) — 'Ayşepınar', 'Işıkkale', 'Kemune (Zahiku)',
# 'Bølareinen', 'Aké (Yucatan)' — plus ~1.6% of all 1.76M rows and ~2% of the
# alias table could never be exact-matched from Python. Compute the key on the
# database side, with the same expression, so both sides agree by construction.
_KEY_SQL = "left(lower(unaccent(:raw)), 500)"


def _match_site_ids(session: Session, extracted_name: str) -> set:
    """Site ids whose name or alias keys to the same string as `extracted_name`.

    Exact key first (both columns are btree-indexed on name_normalized); the
    spaceless variant only runs on a miss, because `replace(name_normalized,
    ' ', '')` has no functional index and costs a parallel sequential scan of
    1.76M rows — measured at ~125 ms per lookup on prod.
    """
    exact = session.execute(
        text(f"""
        WITH k AS (SELECT {_KEY_SQL} AS key)
        SELECT us.id FROM unified_sites us, k WHERE us.name_normalized = k.key
        UNION
        SELECT usn.site_id FROM unified_site_names usn, k WHERE usn.name_normalized = k.key
        """),
        {"raw": extracted_name},
    ).fetchall()
    if exact:
        return {r[0] for r in exact}

    spaceless = session.execute(
        text(f"""
        WITH k AS (SELECT replace({_KEY_SQL}, ' ', '') AS key)
        SELECT us.id FROM unified_sites us, k
        WHERE replace(us.name_normalized, ' ', '') = k.key
        UNION
        SELECT usn.site_id FROM unified_site_names usn, k
        WHERE replace(usn.name_normalized, ' ', '') = k.key
        """),
        {"raw": extracted_name},
    ).fetchall()
    return {r[0] for r in spaceless}


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

    Steps 2/2.5 treat every unified_site_names row as authoritative evidence,
    so only name types that are themselves authoritative may live in that
    table: ``label`` (the site's own name), ``wikidata_alias`` (Wikidata
    "also known as") and ``alias`` (written by a founder merge). The
    ``caption_garble`` type violated that rule — site_identifier wrote the
    *unverified* contribution name onto whichever site a 0.35-threshold
    trigram search had picked, and this function then promoted that guess to
    an exact match forever. 597 such rows mislinked 588 news items and, via
    _correct_text_fields() below, rewrote 206 published headlines with the
    wrong site name ("Jiahu" → "Kahu-Jo-Darro"). Writer and rows removed
    2026-09-14; do not reintroduce a memoized fuzzy match here.
    """
    normalized = normalize_name(extracted_name)
    if not normalized or len(normalized) < 3:
        return None
    # The blocklist holds plain ASCII country and region names, so the Python
    # key is adequate here. It is NOT adequate for the DB comparison below.
    if normalized in _GENERIC_NAME_BLOCKLIST:
        return None

    # Collect ALL candidates from both primary names and alternate names, then
    # pick the best by source priority, so a low-priority primary-name hit
    # never wins over a curated alternate-name hit.
    site_ids = _match_site_ids(session, extracted_name)
    if not site_ids:
        return None

    combined = {
        s.id: s
        for s in session.query(UnifiedSite)
        .filter(UnifiedSite.id.in_(site_ids), UnifiedSite.source_id.in_(matchable_sources))
        .all()
    }
    if not combined:
        return None
    if len(combined) == 1:
        return list(combined.values())[0]
    return _pick_best_match(list(combined.values()), source_priority)


def _pick_best_match(
    matches: list[UnifiedSite], source_priority: dict[str, int]
) -> UnifiedSite | None:
    """Pick the best match from multiple candidates, preferring lowest priority (most curated)."""
    return min(matches, key=lambda m: source_priority.get(m.source_id, 99))


def _is_same_name(extracted: str, canonical: str) -> bool:
    """True when two names are spellings of the same name, not two names.

    Containment covers expansions ("Hawara" / "Pyramid of Amenemhat III at
    Hawara"); normalize_transliteration covers spelling variants ("Osireion" /
    "Osirion"). Anything else is two different places and must not drive a
    rewrite of published text.
    """
    a, b = normalize_name(extracted), normalize_name(canonical)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return normalize_transliteration(extracted) == normalize_transliteration(canonical)


def _correct_text_fields(item: NewsItem, canonical_name: str) -> None:
    """Replace a garbled site_name_extracted with the canonical spelling.

    Case-insensitive replacement, and only between two spellings of the SAME
    name. Before the _is_same_name gate this rewrote on any match at all, so a
    wrong match rewrote the story itself: 206 published headlines carried the
    matched site's name instead of the one the video said ("Jiahu" appeared as
    "Kahu-Jo-Darro", a different site 4,000 km away). The site_id link already
    carries the identification — the text must keep saying what the source said.
    """
    extracted = item.site_name_extracted
    if not extracted or extracted == canonical_name:
        return
    if not _is_same_name(extracted, canonical_name):
        logger.debug(
            f"Not rewriting text for item {item.id}: '{extracted}' and "
            f"'{canonical_name}' are different names"
        )
        return

    pattern = re.compile(re.escape(extracted), re.IGNORECASE)

    if item.headline and pattern.search(item.headline):
        item.headline = pattern.sub(canonical_name, item.headline)
    if item.post_text and pattern.search(item.post_text):
        item.post_text = pattern.sub(canonical_name, item.post_text)
    if item.summary and pattern.search(item.summary):
        item.summary = pattern.sub(canonical_name, item.summary)
    if item.facts:
        corrected = [pattern.sub(canonical_name, f) if pattern.search(f) else f for f in item.facts]
        if corrected != item.facts:
            item.facts = corrected


def match_sites_for_pending_items() -> int:
    """Match site names for all NewsItems that have site_name_extracted but no site_id.

    Returns number of items matched.
    """
    global _lyra_contrib_cache
    _lyra_contrib_cache = None  # Rebuild cache fresh each cycle
    matched = 0

    with get_session() as session:
        source_priority = _load_source_priority(session)
        matchable_sources = list(source_priority.keys())

        # Preload promoted site IDs so we know which radar items are already "ours"
        promoted_ids = {
            row.promoted_site_id
            for row in session.query(UserContribution.promoted_site_id).filter(
                UserContribution.promoted_site_id.isnot(None)
            )
        }

        # Match untried items first. Already-tried items only retry if new sites
        # were recently promoted (checked via promoted_ids changing).
        items = (
            session.query(NewsItem)
            .filter(
                NewsItem.site_name_extracted.isnot(None),
                NewsItem.site_id.is_(None),
                NewsItem.site_match_tried.is_(False),
            )
            .all()
        )

        if not items:
            return 0

        logger.info(f"Attempting site matching for {len(items)} news items")

        for item in items:
            site = _find_site_by_name(
                session, item.site_name_extracted, matchable_sources, source_priority
            )
            if site:
                item.site_id = site.id
                _correct_text_fields(item, site.name)
                matched += 1

                if site.source_id == "ancient_nerds" or site.id in promoted_ids:
                    # AN Originals or already-promoted radar item — no radar card needed
                    logger.info(
                        f"Matched item {item.id} '{item.site_name_extracted}' -> "
                        f"site '{site.name}' ({site.id}) [AN/promoted, no radar]"
                    )
                else:
                    # External source match — still create a radar card enriched with metadata
                    logger.info(
                        f"Matched item {item.id} '{item.site_name_extracted}' -> "
                        f"site '{site.name}' ({site.id}) [external: {site.source_id}, creating radar card]"
                    )
                    _upsert_lyra_suggestion(session, item, matched_site=site)
            else:
                logger.debug(f"No match for item {item.id} '{item.site_name_extracted}'")
                _upsert_lyra_suggestion(session, item)
            item.site_match_tried = True

        session.flush()
        recount_mentions(session)

    logger.info(f"Site matching complete: {matched}/{len(items)} items matched")
    return matched


def recount_mentions(session: Session) -> int:
    """Set every lyra contribution's mention_count to its true news-item count.

    mention_count used to be accumulated with ``+= 1`` per processed item, so
    every re-match cycle (and every v8/v9 status reset that cleared
    site_match_tried) counted the same news item again. On 2026-09-14 prod
    carried 34,061 accumulated mentions against 2,464 news items with a name —
    one card claimed 1,047 mentions with 21 real items, while the radar UI
    used that number as a filter, a sort key and a badge.

    Counts under BOTH the raw and the AI-corrected name, deduplicated by news
    item id: the evidence for "Göbekli Tepe" sits on items whose extracted name
    is still the garbled "Kekili Tepe". Keying on the corrected name alone put
    252 contributions at zero. This mirrors the evidence join in
    api/routes/radar.py:_build_radar_query — keep the two in step.

    The count is derivable, so derive it. Returns the number of rows changed.
    """
    items_by_name: dict[str, set] = {}
    for item_id, extracted in session.query(NewsItem.id, NewsItem.site_name_extracted).filter(
        NewsItem.site_name_extracted.isnot(None)
    ):
        key = normalize_name(extracted)
        if key:
            items_by_name.setdefault(key, set()).add(item_id)

    changed = 0
    for contrib in session.query(UserContribution).filter(UserContribution.source == "lyra"):
        keys = {normalize_name(contrib.name), normalize_name(contrib.corrected_name or "")}
        matched: set = set()
        for key in keys:
            if key:
                matched |= items_by_name.get(key, set())
        if contrib.mention_count != len(matched):
            contrib.mention_count = len(matched)
            changed += 1

    if changed:
        logger.info(f"Recounted mention_count on {changed} lyra contributions")
    return changed


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
        if primary_site.get("name") and normalize_name(primary_site["name"]) == normalize_name(
            item.site_name_extracted
        ):
            raw_period = primary_site.get("period")
            period_start = extract_period_from_text(raw_period) if raw_period else None
            return {
                "country": primary_site.get("country"),
                "site_type": primary_site.get("site_type"),
                "period_name": categorize_period(period_start)
                if period_start is not None
                else raw_period,
                "period_start": period_start,
            }
    return {}


def _upsert_lyra_suggestion(
    session: Session,
    item: NewsItem,
    matched_site: UnifiedSite | None = None,
) -> None:
    """Upsert site name into user_contributions for curation.

    When matched_site is provided (external source match), copies metadata
    from the matched site into the contribution using a fill-if-missing pattern.
    """
    normalized = normalize_name(item.site_name_extracted)
    if not normalized or len(normalized) < 3:
        return

    metadata = _extract_topic_metadata(session, item)

    # Match using normalize_name() on both sides. func.lower() alone would miss
    # diacritic/parenthetical differences (e.g. "Göbekli Tepe (Turkey)" vs "gobekli tepe").
    # Use corrected_name if available, falling back to name.
    existing = _find_lyra_contribution(session, normalized)

    if existing:
        # mention_count is not incremented here — recount_mentions() derives it
        # from news_items at the end of the cycle. Incrementing double-counted
        # every item that a status reset sent through matching a second time.
        # Update metadata if we have better data now
        if metadata.get("country") and not existing.country:
            existing.country = metadata["country"]
        if metadata.get("site_type") and not existing.site_type:
            existing.site_type = metadata["site_type"]
        if metadata.get("period_name") and not existing.period_name:
            existing.period_name = metadata["period_name"]
        if metadata.get("period_start") is not None and existing.period_start is None:
            existing.period_start = metadata["period_start"]
        # Enrich from matched external site (fill-if-missing)
        if matched_site:
            fill_contrib_from_site(existing, matched_site)
    else:
        contrib = UserContribution(
            name=item.site_name_extracted,
            source="lyra",
            mention_count=1,
            description=item.headline,
            country=metadata.get("country"),
            site_type=metadata.get("site_type"),
            period_name=metadata.get("period_name"),
            period_start=metadata.get("period_start"),
            source_url=f"https://www.youtube.com/watch?v={item.video_id}"
            if item.video_id
            else None,
        )
        # Enrich from matched external site (fill-if-missing)
        if matched_site:
            fill_contrib_from_site(contrib, matched_site)
        session.add(contrib)
        # Add to cache so subsequent items in the same cycle find it
        if _lyra_contrib_cache is not None:
            _lyra_contrib_cache[normalized] = contrib


_GENERIC_TYPES = {"Archaeological Site", "Ruin", "Unknown", None, ""}


def fill_contrib_from_site(contrib: UserContribution, site: UnifiedSite) -> None:
    """Copy metadata from a matched site into a contribution (fill-if-missing).

    Canonical fill function — used by both site_matcher and site_identifier.
    """
    if not contrib.country and site.country:
        contrib.country = site.country
    if site.site_type:
        if not contrib.site_type or contrib.site_type in _GENERIC_TYPES:
            contrib.site_type = site.site_type
        # Never downgrade: if contrib has specific type, keep it even if site has generic
    if not contrib.period_name and site.period_name:
        contrib.period_name = site.period_name
    if contrib.period_start is None and site.period_start is not None:
        contrib.period_start = site.period_start
    if not contrib.lat and site.lat:
        contrib.lat = site.lat
    if not contrib.lon and site.lon:
        contrib.lon = site.lon
    if not contrib.description and site.description:
        contrib.description = site.description
    if not contrib.thumbnail_url and site.thumbnail_url:
        contrib.thumbnail_url = site.thumbnail_url
    if not contrib.wikipedia_url and site.source_url:
        url = site.source_url
        if "wikidata.org" in url:
            qid_match = re.search(r"Q\d+", url)
            if qid_match and not contrib.wikidata_id:
                contrib.wikidata_id = qid_match.group()
        elif "wikipedia.org" in url:
            contrib.wikipedia_url = url
