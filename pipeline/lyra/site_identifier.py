"""AI-powered site identification and enrichment for Lyra discoveries.

Takes unmatched site names from user_contributions (source='lyra'),
identifies them via Claude Haiku + Wikidata, enriches with Wikipedia data,
scores completeness, and promotes high-scoring sites to unified_sites.
"""

import hashlib
import json
import logging
import re
import urllib.parse
import uuid
from pathlib import Path

import anthropic
from sqlalchemy import func, text
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
from pipeline.lyra.config import LyraSettings
from pipeline.normalizers.dates import passes_date_cutoff
from pipeline.normalizers.site_type import normalize_site_type
from pipeline.utils.country_lookup import lookup_country
from pipeline.utils.http import fetch_with_retry
from pipeline.utils.text import clean_description, extract_period_from_text, normalize_name

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "identify_site.txt"

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def seed_lyra_source() -> None:
    """Seed the 'lyra' source_meta row for Lyra Discoveries."""
    with get_session() as session:
        existing = session.get(SourceMeta, "lyra")
        if existing:
            return
        session.add(SourceMeta(
            id="lyra",
            name="Lyra Discoveries",
            color="#8b5cf6",
            category="global",
            priority=5,
            enabled=True,
            enabled_by_default=False,
            is_primary=False,
            record_count=0,
        ))
    logger.info("Seeded 'lyra' source_meta row")


def identify_and_enrich_sites(settings: LyraSettings) -> int:
    """Main orchestrator for site identification and enrichment.

    Processes pending Lyra discoveries: identifies via Claude Haiku + Wikidata,
    enriches from Wikipedia, scores completeness, and promotes high-scoring sites.

    Returns number of sites processed.
    """
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping site identification")
        return 0

    processed = 0
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with get_session() as session:
        # Get pending discoveries ordered by mention count (best data first)
        contributions = session.query(UserContribution).filter(
            UserContribution.source == "lyra",
            UserContribution.enrichment_status.in_(["pending", "enriched", "enriching"]),
            UserContribution.promoted_site_id.is_(None),
        ).order_by(
            UserContribution.mention_count.desc()
        ).limit(
            settings.max_identifications_per_cycle
        ).all()

        if not contributions:
            logger.info("No pending discoveries to identify")
            return 0

        logger.info(f"Processing {len(contributions)} discoveries for identification")

        for contribution in contributions:
            try:
                result = _process_single(
                    session, contribution, client, prompt_template, settings
                )
                if result:
                    processed += 1
            except Exception:
                logger.exception(f"Failed to process contribution {contribution.id}: {contribution.name}")
                contribution.enrichment_status = "failed"

    logger.info(f"Site identification complete: {processed}/{len(contributions)} processed")
    return processed


def _process_single(
    session: Session,
    contribution: UserContribution,
    client: anthropic.Anthropic,
    prompt_template: str,
    settings: LyraSettings,
) -> bool:
    """Process a single discovery through identification + enrichment.

    Returns True if the contribution was meaningfully updated.
    """
    # Aggregate facts from all related NewsItems
    facts, video_contexts = _aggregate_facts(session, contribution)
    facts_hash = _compute_facts_hash(facts)

    # Skip if facts haven't changed since last processing
    if contribution.last_facts_hash == facts_hash and contribution.enrichment_status == "enriched":
        logger.debug(f"Skipping {contribution.name} — facts unchanged")
        return False

    contribution.enrichment_status = "enriching"
    contribution.last_facts_hash = facts_hash

    # Get DB candidates via pg_trgm fuzzy matching
    db_candidates = _fetch_db_candidates(session, contribution.name)

    # Get Wikidata candidates
    wikidata_candidates = _search_wikidata(contribution.name)

    # Build and send prompt to Claude Haiku
    prompt = _build_prompt(
        prompt_template, contribution, facts, video_contexts,
        db_candidates, wikidata_candidates
    )

    try:
        response = client.messages.create(
            model=settings.model_identify,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for {contribution.name}: {e}")
        contribution.enrichment_status = "failed"
        return False

    if not response.content or not hasattr(response.content[0], "text"):
        logger.warning(f"Empty or non-text response for {contribution.name}")
        contribution.enrichment_status = "failed"
        return False

    response_text = response.content[0].text
    identification = _parse_identification(response_text)
    if not identification:
        logger.warning(f"Failed to parse identification for {contribution.name}")
        contribution.enrichment_status = "failed"
        return False

    match_type = identification.get("match_type")
    logger.info(
        f"Identified '{contribution.name}' as {match_type} "
        f"(confidence: {identification.get('confidence', 'unknown')})"
    )

    if match_type == "not_a_site":
        contribution.enrichment_status = "matched"
        contribution.enrichment_data = {"identification": identification}
        return True

    if match_type == "db_match":
        return _handle_db_match(session, contribution, identification)

    if match_type in ("wikidata_match", "new_site"):
        return _handle_wikidata_or_new(session, contribution, identification, settings)

    contribution.enrichment_status = "failed"
    return False


def _aggregate_facts(session: Session, contribution: UserContribution) -> tuple[list[str], list[dict]]:
    """Aggregate facts and video context for a discovery from all related NewsItems.

    Uses func.lower() for matching — same approach as site_matcher._upsert_lyra_suggestion
    which stores names via func.lower(UserContribution.name). Do NOT use normalize_name()
    here because that strips diacritics/parentheses which func.lower() does not.
    """
    name_lower = contribution.name.lower().strip()
    items = session.query(NewsItem).filter(
        func.lower(NewsItem.site_name_extracted) == name_lower
    ).all()

    all_facts = []
    video_contexts = []
    seen_video_ids = set()

    for item in items:
        if item.facts:
            all_facts.extend(item.facts)
        if item.video_id and item.video_id not in seen_video_ids:
            seen_video_ids.add(item.video_id)
            video = session.get(NewsVideo, item.video_id)
            if video:
                ctx = {"title": video.title}
                if video.description:
                    ctx["description"] = video.description[:500]
                video_contexts.append(ctx)

    return all_facts, video_contexts


def _compute_facts_hash(facts: list[str]) -> str:
    """Compute SHA-256 hash of sorted, deduplicated facts."""
    unique_facts = sorted(set(str(f) for f in facts))
    content = "|".join(unique_facts)
    return hashlib.sha256(content.encode()).hexdigest()


def _fetch_db_candidates(session: Session, name: str, limit: int = 10) -> list[dict]:
    """Fetch top DB candidate matches via pg_trgm fuzzy matching."""
    normalized = normalize_name(name)
    if not normalized or len(normalized) < 3:
        return []

    try:
        session.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.25"))
        rows = session.execute(text("""
            SELECT usn.site_id, us.name AS site_name,
                   us.country, us.source_id,
                   word_similarity(:qname, usn.name_normalized) AS similarity
            FROM unified_site_names usn
            JOIN unified_sites us ON us.id = usn.site_id
            WHERE :qname <% usn.name_normalized
            ORDER BY usn.name_normalized <->> :qname
            LIMIT :limit
        """), {"qname": normalized, "limit": limit * 3}).fetchall()
    except Exception as e:
        logger.warning(f"pg_trgm query failed for '{name}': {e}")
        return []

    seen = set()
    candidates = []
    for row in rows:
        sid = str(row.site_id)
        if sid in seen:
            continue
        seen.add(sid)
        candidates.append({
            "site_id": sid,
            "name": row.site_name,
            "country": row.country,
            "source": row.source_id,
            "similarity": round(row.similarity, 2),
        })
        if len(candidates) >= limit:
            break

    return candidates


def _search_wikidata(name: str) -> list[dict]:
    """Search Wikidata for entity candidates matching a site name."""
    try:
        resp = fetch_with_retry(
            WIKIDATA_SEARCH_URL,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "limit": "5",
                "format": "json",
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikidata search failed for '{name}': {e}")
        return []

    if data.get("error"):
        logger.warning(f"Wikidata search error for '{name}': {data['error']}")
        return []

    candidates = []
    for result in data.get("search", []):
        candidates.append({
            "qid": result.get("id"),
            "label": result.get("label"),
            "description": result.get("description", ""),
        })

    return candidates


def _enrich_from_wikidata(qid: str) -> dict:
    """Fetch detailed entity data from Wikidata for enrichment.

    Extracts: coordinates (P625), country (P17), instance-of (P31),
    inception (P571), image (P18), and enwiki sitelink.
    """
    try:
        resp = fetch_with_retry(
            WIKIDATA_ENTITY_URL,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|sitelinks",
                "sitefilter": "enwiki",
                "format": "json",
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikidata entity fetch failed for {qid}: {e}")
        return {}

    if data.get("error"):
        logger.warning(f"Wikidata entity error for {qid}: {data['error']}")
        return {}

    entity = data.get("entities", {}).get(qid, {})
    claims = entity.get("claims", {})
    sitelinks = entity.get("sitelinks", {})

    result = {"qid": qid}

    # P625: coordinates
    p625 = claims.get("P625", [])
    if p625:
        coords = p625[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if "latitude" in coords and "longitude" in coords:
            result["lat"] = coords["latitude"]
            result["lon"] = coords["longitude"]

    # P17: country
    p17 = claims.get("P17", [])
    if p17:
        country_id = p17[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
        if country_id:
            result["country_qid"] = country_id

    # P31: instance of (for type classification)
    p31 = claims.get("P31", [])
    instance_labels = []
    for claim in p31:
        val = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if val.get("id"):
            instance_labels.append(val["id"])
    if instance_labels:
        result["instance_of"] = instance_labels

    # P571: inception (date founded)
    p571 = claims.get("P571", [])
    if p571:
        time_val = p571[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if time_val.get("time"):
            result["inception_time"] = time_val["time"]

    # P18: image
    p18 = claims.get("P18", [])
    if p18:
        image_name = p18[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        if image_name:
            # Build Wikimedia Commons thumbnail URL
            safe_name = image_name.replace(" ", "_")
            md5 = hashlib.md5(safe_name.encode()).hexdigest()
            encoded_name = urllib.parse.quote(safe_name, safe="")
            # SVG/PDF files need .png appended for the thumbnail render
            thumb_suffix = f"{encoded_name}.png" if safe_name.lower().endswith((".svg", ".pdf")) else encoded_name
            result["thumbnail_url"] = (
                f"https://upload.wikimedia.org/wikipedia/commons/thumb/"
                f"{md5[0]}/{md5[0:2]}/{encoded_name}/300px-{thumb_suffix}"
            )

    # enwiki sitelink → Wikipedia URL
    enwiki = sitelinks.get("enwiki", {})
    if enwiki.get("title"):
        result["wikipedia_title"] = enwiki["title"]
        encoded_title = urllib.parse.quote(enwiki["title"].replace(" ", "_"), safe="/:")
        result["wikipedia_url"] = f"https://en.wikipedia.org/wiki/{encoded_title}"

    return result


def _fetch_wikipedia_summary(title: str) -> dict:
    """Fetch Wikipedia page summary via REST API.

    Returns dict with extract (description text) and thumbnail if available.
    """
    encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = WIKIPEDIA_SUMMARY_URL.format(title=encoded_title)

    try:
        resp = fetch_with_retry(url)
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikipedia summary fetch failed for '{title}': {e}")
        return {}

    result = {}
    if data.get("extract"):
        result["description"] = data["extract"]
    if data.get("thumbnail", {}).get("source"):
        result["thumbnail_url"] = data["thumbnail"]["source"]
    if data.get("coordinates"):
        result["lat"] = data["coordinates"].get("lat")
        result["lon"] = data["coordinates"].get("lon")

    return result


def _build_prompt(
    template: str,
    contribution: UserContribution,
    facts: list[str],
    video_contexts: list[dict],
    db_candidates: list[dict],
    wikidata_candidates: list[dict],
) -> str:
    """Build the identification prompt for Claude Haiku."""
    # Format facts
    facts_text = "\n".join(f"- {f}" for f in facts[:30]) if facts else "(no facts extracted)"

    # Format video contexts
    video_text_parts = []
    for ctx in video_contexts[:5]:
        part = f"  Title: {ctx['title']}"
        if ctx.get("description"):
            part += f"\n  Description: {ctx['description']}"
        video_text_parts.append(part)
    video_text = "\n".join(video_text_parts) if video_text_parts else "(no video context)"

    # Format DB candidates
    db_text_parts = []
    for c in db_candidates[:10]:
        db_text_parts.append(
            f"  - {c['name']} (country: {c.get('country', 'unknown')}, "
            f"source: {c['source']}, similarity: {c['similarity']})"
        )
    db_text = "\n".join(db_text_parts) if db_text_parts else "(no database matches found)"

    # Format Wikidata candidates
    wd_text_parts = []
    for c in wikidata_candidates[:5]:
        wd_text_parts.append(
            f"  - {c['qid']}: {c['label']} — {c.get('description', '')}"
        )
    wd_text = "\n".join(wd_text_parts) if wd_text_parts else "(no Wikidata matches found)"

    return template.format(
        site_name=contribution.name,
        mention_count=contribution.mention_count,
        existing_country=contribution.country or "unknown",
        existing_site_type=contribution.site_type or "unknown",
        existing_period=contribution.period_name or "unknown",
        facts=facts_text,
        video_contexts=video_text,
        db_candidates=db_text,
        wikidata_candidates=wd_text,
    )


def _parse_identification(response_text: str) -> dict | None:
    """Parse Claude's JSON identification response.

    Tries: 1) full text as JSON, 2) markdown code fence, 3) greedy brace match.
    """
    # Try parsing the full response as JSON first
    stripped = response_text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Fall back to greedy brace match
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return None


def _handle_db_match(
    session: Session,
    contribution: UserContribution,
    identification: dict,
) -> bool:
    """Handle a db_match result: link NewsItems to the matched site."""
    match_id = identification.get("match_id")
    if not match_id:
        contribution.enrichment_status = "failed"
        return False

    try:
        site_uuid = uuid.UUID(match_id)
    except (ValueError, TypeError):
        contribution.enrichment_status = "failed"
        return False

    site = session.get(UnifiedSite, site_uuid)
    if not site:
        contribution.enrichment_status = "failed"
        return False

    # Update all related NewsItems to point to this site
    name_lower = contribution.name.lower().strip()
    updated = session.query(NewsItem).filter(
        func.lower(NewsItem.site_name_extracted) == name_lower,
        NewsItem.site_id.is_(None),
    ).update(
        {NewsItem.site_id: site.id},
        synchronize_session="fetch",
    )

    contribution.enrichment_status = "matched"
    contribution.enrichment_data = {"identification": identification}
    logger.info(f"DB match: '{contribution.name}' -> '{site.name}' ({updated} items linked)")
    return True


def _handle_wikidata_or_new(
    session: Session,
    contribution: UserContribution,
    identification: dict,
    settings: LyraSettings,
) -> bool:
    """Handle wikidata_match or new_site: enrich and possibly promote."""
    # Use corrected name from Claude if provided
    site_name = identification.get("site_name", contribution.name)

    # Enrich from Wikidata if we have a QID
    wikidata_qid = identification.get("match_id")
    enrichment = {}

    if wikidata_qid and wikidata_qid.startswith("Q"):
        enrichment = _enrich_from_wikidata(wikidata_qid)
        contribution.wikidata_id = wikidata_qid

        # Enrich from Wikipedia if we have a title
        wiki_title = enrichment.get("wikipedia_title")
        if wiki_title:
            wiki_data = _fetch_wikipedia_summary(wiki_title)
            enrichment.update({"wikipedia": wiki_data})
            contribution.wikipedia_url = enrichment.get("wikipedia_url")

            if wiki_data.get("description"):
                contribution.description = clean_description(wiki_data["description"])
            if wiki_data.get("thumbnail_url") and not enrichment.get("thumbnail_url"):
                enrichment["thumbnail_url"] = wiki_data["thumbnail_url"]

    # Apply coordinates
    if enrichment.get("lat") and enrichment.get("lon"):
        contribution.lat = enrichment["lat"]
        contribution.lon = enrichment["lon"]

    # Apply country — prefer Wikidata coordinates lookup, fall back to identification
    if contribution.lat and contribution.lon and not contribution.country:
        contribution.country = lookup_country(contribution.lat, contribution.lon)
    if not contribution.country and identification.get("country"):
        contribution.country = identification["country"]

    # Apply site type
    if identification.get("site_type"):
        contribution.site_type = normalize_site_type(identification["site_type"])

    # Apply period
    if identification.get("period_estimate"):
        contribution.period_name = identification["period_estimate"]
        period_start = extract_period_from_text(identification["period_estimate"])
        if period_start is not None:
            contribution.period_start = period_start

    # Apply thumbnail
    if enrichment.get("thumbnail_url"):
        contribution.thumbnail_url = enrichment["thumbnail_url"]

    # Store full enrichment data
    contribution.enrichment_data = {
        "identification": identification,
        "wikidata": enrichment,
    }

    # Compute score
    contribution.score = _compute_score(contribution)
    contribution.enrichment_status = "enriched"

    logger.info(
        f"Enriched '{contribution.name}': score={contribution.score}, "
        f"wikidata={contribution.wikidata_id}, coords=({contribution.lat}, {contribution.lon})"
    )

    # Promote if score is high enough and has coordinates
    if (
        contribution.score >= settings.min_score_for_promotion
        and contribution.lat is not None
        and contribution.lon is not None
    ):
        # Check date cutoff before promoting
        record = {
            "period_start": contribution.period_start,
            "period_end": contribution.period_end,
            "lon": contribution.lon,
        }
        if passes_date_cutoff(record):
            site_id = _promote_to_unified_sites(session, contribution, site_name)
            if site_id:
                contribution.promoted_site_id = site_id
                contribution.enrichment_status = "promoted"
                logger.info(f"Promoted '{contribution.name}' to unified_sites ({site_id})")
        else:
            logger.info(f"Skipping promotion for '{contribution.name}' — outside date cutoff")

    return True


def _compute_score(contribution: UserContribution) -> int:
    """Score a contribution 0-100 based on metadata completeness."""
    score = 0

    # Site name confirmed: 25 points (always true if we got here)
    score += 25

    # Coordinates: 20 points
    if contribution.lat is not None and contribution.lon is not None:
        score += 20

    # Country: 10 points
    if contribution.country:
        score += 10

    # Category/Type: 10 points
    if contribution.site_type:
        score += 10

    # Period/Age: 10 points
    if contribution.period_start is not None:
        score += 10

    # Wikipedia URL: 5 points
    if contribution.wikipedia_url:
        score += 5

    # Description: 10 points (must be >= 50 chars)
    if contribution.description and len(contribution.description) >= 50:
        score += 10

    # Thumbnail: 5 points
    if contribution.thumbnail_url:
        score += 5

    # Wikidata ID: 5 points
    if contribution.wikidata_id:
        score += 5

    return score


def _promote_to_unified_sites(
    session: Session,
    contribution: UserContribution,
    site_name: str,
) -> uuid.UUID | None:
    """Insert a new site into unified_sites from an enriched contribution.

    Returns the new site ID, or None on failure.
    """
    # Check for duplicate: same name within lyra source
    normalized = normalize_name(site_name)
    existing = session.query(UnifiedSite).filter(
        UnifiedSite.source_id == "lyra",
        UnifiedSite.name_normalized == normalized,
    ).all()

    for ex in existing:
        # Same name AND within ~50km = duplicate (handles "Temple of Apollo" in different locations)
        if contribution.lat and contribution.lon and ex.lat and ex.lon:
            lat_diff = abs(contribution.lat - ex.lat)
            lon_diff = abs(contribution.lon - ex.lon)
            if lat_diff < 0.5 and lon_diff < 0.5:  # ~50km at mid-latitudes
                logger.info(f"Site '{site_name}' already exists near ({ex.lat}, {ex.lon}) as lyra source")
                return ex.id
        else:
            # No coords to compare — treat same name as duplicate
            logger.info(f"Site '{site_name}' already exists in unified_sites as lyra source")
            return ex.id

    site_id = uuid.uuid4()
    source_record_id = f"lyra-{contribution.id}"

    site = UnifiedSite(
        id=site_id,
        source_id="lyra",
        source_record_id=source_record_id,
        name=site_name,
        name_normalized=normalized,
        lat=contribution.lat,
        lon=contribution.lon,
        site_type=contribution.site_type,
        period_start=contribution.period_start,
        period_end=contribution.period_end,
        period_name=contribution.period_name,
        country=contribution.country,
        description=contribution.description,
        thumbnail_url=contribution.thumbnail_url,
        source_url=contribution.wikipedia_url,
        raw_data=contribution.enrichment_data,
    )
    session.add(site)

    # Add canonical name to unified_site_names
    session.add(UnifiedSiteName(
        site_id=site_id,
        name=site_name,
        name_normalized=normalized,
        name_type="label",
    ))

    # Add alternate name if contribution name differs
    contrib_normalized = normalize_name(contribution.name)
    if contrib_normalized != normalized:
        session.add(UnifiedSiteName(
            site_id=site_id,
            name=contribution.name,
            name_normalized=contrib_normalized,
            name_type="alias",
        ))

    # Update all related NewsItems to point to the new site
    name_lower = contribution.name.lower().strip()
    session.query(NewsItem).filter(
        func.lower(NewsItem.site_name_extracted) == name_lower,
        NewsItem.site_id.is_(None),
    ).update(
        {NewsItem.site_id: site_id},
        synchronize_session="fetch",
    )

    # Update source_meta record count
    session.query(SourceMeta).filter(
        SourceMeta.id == "lyra"
    ).update(
        {SourceMeta.record_count: SourceMeta.record_count + 1},
        synchronize_session="fetch",
    )

    return site_id
