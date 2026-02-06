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
PICK_ENTITY_PROMPT_PATH = Path(__file__).parent / "prompts" / "pick_wikidata_entity.txt"

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
            name="ANCIENT NERDS Discoveries",
            color="#8b5cf6",
            category="Primary",
            priority=1,
            enabled=True,
            enabled_by_default=False,
            is_primary=True,
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
            UserContribution.enrichment_status.in_(["pending", "enriched", "enriching", "rejected"]),
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
            logger.info(
                f"  [{contribution.name}] status={contribution.enrichment_status}, "
                f"hash={'set' if contribution.last_facts_hash else 'null'}, "
                f"mentions={contribution.mention_count}"
            )
            try:
                # Each contribution runs in a SAVEPOINT so a failure in one
                # doesn't poison the session for the rest.
                with session.begin_nested():
                    result = _process_single(
                        session, contribution, client, prompt_template, settings
                    )
                    if result:
                        processed += 1
                    else:
                        logger.info(f"  [{contribution.name}] _process_single returned False")
            except Exception:
                logger.exception(f"Failed to process contribution {contribution.id}: {contribution.name}")
                try:
                    contribution.enrichment_status = "failed"
                except Exception:
                    logger.warning(f"  Could not set failed status for {contribution.name}")

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
    facts_hash = _compute_facts_hash(facts, video_contexts)
    logger.info(
        f"  [{contribution.name}] facts={len(facts)}, videos={len(video_contexts)}, "
        f"hash_match={contribution.last_facts_hash == facts_hash}"
    )

    # Skip if facts haven't changed since last processing
    if contribution.last_facts_hash == facts_hash and contribution.enrichment_status in ("enriched", "rejected"):
        logger.info(f"  [{contribution.name}] Skipping — facts unchanged (status={contribution.enrichment_status})")
        return False

    # Inject rejection context so AI avoids the same bad match
    if contribution.enrichment_status == "rejected" and contribution.enrichment_data:
        rejected = contribution.enrichment_data.get("rejected_match", {})
        if rejected:
            rejection_note = (
                f"PREVIOUSLY REJECTED: Site '{rejected.get('site_name', '?')}' in "
                f"{rejected.get('site_country', '?')} was rejected because video facts "
                f"indicate {rejected.get('contribution_country', '?')}. "
                f"Do NOT re-match this site."
            )
            facts.append(rejection_note)
            logger.info(f"  [{contribution.name}] Injected rejection context")

    contribution.enrichment_status = "enriching"
    contribution.last_facts_hash = facts_hash

    # Get DB candidates via pg_trgm fuzzy matching
    db_candidates = _fetch_db_candidates(session, contribution.name, threshold=settings.pg_trgm_threshold)
    if db_candidates:
        top3 = ", ".join(f"{c['name']}({c['similarity']})" for c in db_candidates[:3])
        logger.info(f"  [{contribution.name}] DB candidates: {len(db_candidates)} (top: {top3})")
    else:
        logger.info(f"  [{contribution.name}] DB candidates: 0")

    # Get Wikidata candidates
    wikidata_candidates = _search_wikidata(contribution.name)
    if wikidata_candidates:
        top3 = ", ".join(c['label'] for c in wikidata_candidates[:3])
        logger.info(f"  [{contribution.name}] Wikidata candidates: {len(wikidata_candidates)} (top: {top3})")
    else:
        logger.info(f"  [{contribution.name}] Wikidata candidates: 0")

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

    # Escalate low/medium confidence to Sonnet for review
    confidence = identification.get("confidence", "unknown")
    if confidence in ("low", "medium"):
        sonnet_result = _escalate_to_sonnet(client, settings, prompt, response_text, identification)
        if sonnet_result:
            identification = sonnet_result

    match_type = identification.get("match_type")
    corrected_name = identification.get("site_name", "")
    confidence = identification.get("confidence", "unknown")
    logger.info(
        f"Identified '{contribution.name}' as {match_type} "
        f"(confidence: {confidence}, "
        f"corrected: '{corrected_name}')"
    )

    # Post-processing: re-search with corrected name and validate new_site claims.
    # Claude often corrects garbled names (e.g. "Seab Birch" → "Sayburç") but can't
    # search our DB itself, so we re-search with the corrected spelling.
    if match_type not in ("db_match", "not_a_site") and corrected_name:
        corrected_lower = corrected_name.lower().strip()
        original_lower = contribution.name.lower().strip()
        if corrected_lower != original_lower:
            logger.info(f"Re-searching with corrected name '{corrected_name}'")
            # Try DB first (strongly preferred — avoids duplicate dots)
            corrected_candidates = _fetch_db_candidates(session, corrected_name, threshold=settings.pg_trgm_threshold)
            if corrected_candidates:
                best = corrected_candidates[0]
                logger.info(
                    f"Found DB match via corrected name: {best['name']} "
                    f"(similarity: {best['similarity']})"
                )
                identification["match_type"] = "db_match"
                identification["match_id"] = best["site_id"]
                match_type = "db_match"
            else:
                # Try Wikidata with corrected name
                corrected_wd = _search_wikidata(corrected_name)
                if corrected_wd:
                    logger.info(f"Found Wikidata match via corrected name: {corrected_wd[0]['label']}")
                    identification["match_type"] = "wikidata_match"
                    identification["match_id"] = corrected_wd[0]["qid"]
                    match_type = "wikidata_match"

    # For new_site: extra validation — search Wikidata with the site name one more time.
    # With 50k+ DB sites and all of Wikidata, truly unknown sites are very rare.
    if match_type == "new_site" and corrected_name:
        wd_retry = _search_wikidata(corrected_name)
        if wd_retry:
            # Check if any candidate looks archaeological/historical
            for candidate in wd_retry:
                desc = candidate.get("description", "").lower()
                if any(kw in desc for kw in [
                    "archaeolog", "ancient", "historic", "ruin", "settlement",
                    "temple", "tomb", "fort", "monument", "castle", "church",
                    "mosque", "palace", "site", "mound", "city", "town",
                ]):
                    logger.info(f"new_site override: Wikidata match '{candidate['label']}' ({candidate['qid']})")
                    identification["match_type"] = "wikidata_match"
                    identification["match_id"] = candidate["qid"]
                    match_type = "wikidata_match"
                    break

    if match_type == "not_a_site":
        contribution.enrichment_status = "matched"
        contribution.enrichment_data = {"identification": identification}
        return True

    if match_type == "db_match":
        return _handle_db_match(session, contribution, identification, client, settings)

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
                if video.tags:
                    ctx["tags"] = video.tags
                video_contexts.append(ctx)

    return all_facts, video_contexts


def _compute_facts_hash(facts: list[str], video_contexts: list[dict] | None = None) -> str:
    """Compute SHA-256 hash of facts + video contexts.

    Includes video descriptions and tags so that backfilling either
    triggers reprocessing of already-enriched contributions.
    """
    unique_facts = sorted({str(f) for f in facts})
    parts = ["|".join(unique_facts)]
    if video_contexts:
        for ctx in sorted(video_contexts, key=lambda c: c.get("title", "")):
            if ctx.get("description"):
                parts.append(ctx["description"][:500])
            if ctx.get("tags"):
                parts.append(",".join(ctx["tags"]))
    content = "||".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()


def _fetch_db_candidates(session: Session, name: str, limit: int = 10, threshold: float = 0.35) -> list[dict]:
    """Fetch top DB candidate matches via pg_trgm fuzzy matching."""
    normalized = normalize_name(name)
    if not normalized or len(normalized) < 3:
        return []

    try:
        # Use SAVEPOINT so pg_trgm failures don't poison the parent transaction.
        # Without this, a caught exception leaves PostgreSQL in "aborted" state
        # and all subsequent SQL in the same session fails with InFailedSqlTransaction.
        with session.begin_nested():
            session.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = :threshold"), {"threshold": threshold})
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


def _check_enwiki_sitelinks(qids: list[str]) -> dict[str, bool]:
    """Batch-check which Wikidata entities have English Wikipedia pages.

    Single API call to wbgetentities with props=sitelinks&sitefilter=enwiki.
    Returns {qid: has_wikipedia} dict.
    """
    if not qids:
        return {}

    try:
        resp = fetch_with_retry(
            WIKIDATA_ENTITY_URL,
            params={
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "sitelinks",
                "sitefilter": "enwiki",
                "format": "json",
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikidata sitelinks check failed: {e}")
        return {}

    result = {}
    entities = data.get("entities", {})
    for qid in qids:
        entity = entities.get(qid, {})
        sitelinks = entity.get("sitelinks", {})
        result[qid] = "enwiki" in sitelinks

    return result


def _pick_wikidata_entity(
    client: anthropic.Anthropic,
    model: str,
    site_name: str,
    country: str | None,
    site_type: str | None,
    candidates: list[dict],
) -> str | None:
    """Pick the best Wikidata entity from candidates annotated with has_wikipedia.

    1. Filter to candidates with has_wikipedia == True
    2. If 1 → return its QID directly (no Haiku call)
    3. If 0 → return None (skip Wikidata enrichment)
    4. If 2+ → ask Haiku to pick, return chosen QID
    """
    with_wiki = [c for c in candidates if c.get("has_wikipedia")]

    if len(with_wiki) == 0:
        logger.info(f"  [{site_name}] No Wikidata candidates have Wikipedia pages — skipping")
        return None

    if len(with_wiki) == 1:
        qid = with_wiki[0]["qid"]
        logger.info(f"  [{site_name}] Single Wikipedia candidate: {qid} ({with_wiki[0]['label']})")
        return qid

    # Multiple candidates with Wikipedia — ask Haiku to pick
    options_lines = []
    for i, c in enumerate(with_wiki):
        letter = chr(ord("A") + i)
        desc = c.get("description", "no description")
        options_lines.append(f'{letter}) {c["qid"]}: "{c["label"]}" — {desc} (has Wikipedia)')

    context_parts = []
    if country:
        context_parts.append(country)
    if site_type:
        context_parts.append(site_type)
    context = " (" + ", ".join(context_parts) + ")" if context_parts else ""

    prompt_template = PICK_ENTITY_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.format(
        site_name=site_name,
        context=context,
        options="\n".join(options_lines),
    )

    logger.info(f"  [{site_name}] Asking Haiku to pick from {len(with_wiki)} Wikipedia candidates")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=32,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.warning(f"Haiku tiebreaker API error for {site_name}: {e}")
        return with_wiki[0]["qid"]

    if not response.content or not hasattr(response.content[0], "text"):
        return with_wiki[0]["qid"]

    reply = response.content[0].text.strip()
    # Extract QID from reply (e.g. "Q115679382" or "A) Q115679382")
    qid_match = re.search(r"Q\d+", reply)
    if qid_match:
        chosen_qid = qid_match.group()
        # Validate it's one of our candidates
        valid_qids = {c["qid"] for c in with_wiki}
        if chosen_qid in valid_qids:
            logger.info(f"  [{site_name}] Haiku picked: {chosen_qid}")
            return chosen_qid

    # Haiku returned something unexpected — fall back to first
    logger.warning(f"  [{site_name}] Haiku returned unexpected: '{reply}', using first candidate")
    return with_wiki[0]["qid"]


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
        if ctx.get("tags"):
            part += f"\n  Tags: {', '.join(ctx['tags'])}"
        video_text_parts.append(part)
    video_text = "\n".join(video_text_parts) if video_text_parts else "(no video context)"

    # Format DB candidates (include site_id so Haiku can return it as match_id)
    db_text_parts = []
    for c in db_candidates[:10]:
        db_text_parts.append(
            f"  - site_id={c['site_id']}: {c['name']} (country: {c.get('country', 'unknown')}, "
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


ESCALATION_PROMPT_TEMPLATE = """You are a senior archaeological site identification reviewer.

A junior model (Haiku) was asked to identify an archaeological site from YouTube video captions. It returned a {confidence}-confidence answer. Your job is to REVIEW its work and either confirm or override its decision.

## Original Prompt Given to Haiku
<original_prompt>
{original_prompt}
</original_prompt>

## Haiku's Response
<haiku_response>
{haiku_response}
</haiku_response>

## Your Task
1. Check if Haiku's country cross-check reasoning is sound — did it verify the candidate's country matches the video facts?
2. Check if the match_type makes sense given the evidence
3. Check if the confidence should be higher or lower
4. If you disagree with Haiku, provide a corrected JSON response

CRITICAL: Geographic mismatches are HARD DISQUALIFIERS. If Haiku matched a site in country X but the video facts clearly indicate country Y, you MUST override to not_a_site or new_site.

If you agree with Haiku's answer, return the exact same JSON.
If you disagree, return a corrected JSON with the same schema.

Return ONLY valid JSON (same schema as Haiku's response).
"""


def _escalate_to_sonnet(
    client: anthropic.Anthropic,
    settings: LyraSettings,
    original_prompt: str,
    haiku_response: str,
    haiku_identification: dict,
) -> dict | None:
    """Escalate a low/medium confidence identification to Sonnet for review."""
    confidence = haiku_identification.get("confidence", "unknown")
    logger.info(f"Escalating to Sonnet (confidence={confidence})")

    prompt = ESCALATION_PROMPT_TEMPLATE.format(
        confidence=confidence,
        original_prompt=original_prompt,
        haiku_response=haiku_response,
    )

    try:
        response = client.messages.create(
            model=settings.model_identify_escalation,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error(f"Sonnet escalation API error: {e}")
        return None

    if not response.content or not hasattr(response.content[0], "text"):
        logger.warning("Empty Sonnet escalation response")
        return None

    result = _parse_identification(response.content[0].text)
    if not result:
        logger.warning("Failed to parse Sonnet escalation response")
        return None

    sonnet_match = result.get("match_type")
    sonnet_confidence = result.get("confidence")
    haiku_match = haiku_identification.get("match_type")

    if sonnet_match != haiku_match:
        logger.info(
            f"Sonnet overrode Haiku: {haiku_match} -> {sonnet_match} "
            f"(confidence: {sonnet_confidence})"
        )
    else:
        logger.info(f"Sonnet confirmed Haiku's {haiku_match} (confidence: {sonnet_confidence})")

    return result


def _handle_db_match(
    session: Session,
    contribution: UserContribution,
    identification: dict,
    client: anthropic.Anthropic,
    settings: LyraSettings,
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

    # Post-match country validation: reject if countries clearly mismatch
    confidence = identification.get("confidence", "unknown")
    if confidence != "high" and site.country and contribution.country:
        site_country = site.country.strip().lower()
        contrib_country = contribution.country.strip().lower()
        if site_country != contrib_country:
            logger.warning(
                f"Country mismatch for '{contribution.name}': "
                f"site '{site.name}' is in '{site.country}' but "
                f"video facts indicate '{contribution.country}' — rejecting"
            )
            contribution.enrichment_status = "rejected"
            contribution.enrichment_data = {
                "rejected_match": {
                    "site_id": str(site.id),
                    "site_name": site.name,
                    "site_country": site.country,
                    "contribution_country": contribution.country,
                    "reason": "country_mismatch",
                    "identification": identification,
                },
            }
            return False

    # Copy base metadata from matched site
    if not contribution.country and site.country:
        contribution.country = site.country
    if not contribution.site_type and site.site_type:
        contribution.site_type = site.site_type
    if not contribution.period_name and site.period_name:
        contribution.period_name = site.period_name

    # Enrich via Wikidata: search with corrected name or matched site name
    search_name = identification.get("site_name") or site.name
    wikidata_candidates = _search_wikidata(search_name)
    best_qid = None
    if wikidata_candidates:
        # Batch-check which candidates have English Wikipedia pages
        qids = [c["qid"] for c in wikidata_candidates]
        sitelinks = _check_enwiki_sitelinks(qids)
        for c in wikidata_candidates:
            c["has_wikipedia"] = sitelinks.get(c["qid"], False)

        best_qid = _pick_wikidata_entity(
            client, settings.model_identify,
            search_name, contribution.country or site.country,
            contribution.site_type or site.site_type,
            wikidata_candidates,
        )

    if best_qid:
        enrichment = _enrich_from_wikidata(best_qid)
        if enrichment:
            contribution.wikidata_id = best_qid

            if enrichment.get("lat") and enrichment.get("lon"):
                contribution.lat = enrichment["lat"]
                contribution.lon = enrichment["lon"]
            if enrichment.get("thumbnail_url"):
                contribution.thumbnail_url = enrichment["thumbnail_url"]
            if enrichment.get("wikipedia_url"):
                contribution.wikipedia_url = enrichment["wikipedia_url"]

            # Fetch Wikipedia summary for description + better thumbnail
            wiki_title = enrichment.get("wikipedia_title")
            if wiki_title:
                wiki_data = _fetch_wikipedia_summary(wiki_title)
                if wiki_data.get("description"):
                    contribution.description = clean_description(wiki_data["description"])
                if wiki_data.get("thumbnail_url"):
                    contribution.thumbnail_url = wiki_data["thumbnail_url"]
                if wiki_data.get("lat") and wiki_data.get("lon") and not contribution.lat:
                    contribution.lat = wiki_data["lat"]
                    contribution.lon = wiki_data["lon"]

            logger.info(
                f"  [{contribution.name}] Wikidata enrichment: {best_qid}, "
                f"wiki={contribution.wikipedia_url is not None}, "
                f"coords=({contribution.lat}, {contribution.lon})"
            )

    # Fill remaining gaps from the matched site itself
    if not contribution.lat and site.lat:
        contribution.lat = site.lat
    if not contribution.lon and site.lon:
        contribution.lon = site.lon
    if not contribution.description and site.description:
        contribution.description = site.description
    if not contribution.thumbnail_url and site.thumbnail_url:
        contribution.thumbnail_url = site.thumbnail_url

    # Resolve country from coordinates if still missing
    if contribution.lat and contribution.lon and not contribution.country:
        contribution.country = lookup_country(contribution.lat, contribution.lon)

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
    contribution.score = _compute_score(contribution)
    logger.info(f"DB match: '{contribution.name}' -> '{site.name}' ({updated} items linked)")

    # Promote to lyra source so it appears on the globe under Discoveries
    if (
        contribution.score >= settings.min_score_for_promotion
        and contribution.lat is not None
        and contribution.lon is not None
    ):
        record = {
            "period_start": contribution.period_start,
            "period_end": contribution.period_end,
            "lon": contribution.lon,
        }
        if passes_date_cutoff(record):
            site_name = identification.get("site_name") or site.name
            promoted_id = _promote_to_unified_sites(session, contribution, site_name)
            if promoted_id:
                contribution.promoted_site_id = promoted_id
                contribution.enrichment_status = "promoted"
                logger.info(f"Promoted db_match '{contribution.name}' to Discoveries ({promoted_id})")

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
