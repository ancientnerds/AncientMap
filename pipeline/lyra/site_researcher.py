"""Deep site research agent for Lyra radar.

Multi-step research protocol for sites not found via DB fuzzy search:
1. MiniMax pre-research (generate search terms + prior knowledge)
2. Multi-source API search (Wikidata, Wikipedia, GeoNames)
3. MiniMax candidate selection (if ambiguous)
4. MiniMax gap-fill (fill missing fields from AI knowledge)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from pipeline.lyra.config import LyraSettings, call_api, parse_json_response
from pipeline.utils.http import fetch_with_retry

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"

# --- Schemas ---

PRE_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "alternative_names": {"type": "array", "items": {"type": "string"}},
        "country": {"type": "string"},
        "region": {"type": "string"},
        "approximate_period": {"type": "string"},
        "site_type": {"type": "string"},
        "brief_description": {"type": "string"},
        "well_known": {"type": "boolean"},
        "search_strategy": {"type": "string"},
    },
    "required": ["alternative_names", "country", "well_known"],
    "additionalProperties": False,
}

RESEARCH_SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "enum": ["wikidata", "wikipedia", "geonames", "none"]},
        "id": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["source", "confidence", "reasoning"],
    "additionalProperties": False,
}

GAP_FILL_SCHEMA = {
    "type": "object",
    "properties": {
        "country": {"type": "string"},
        "site_type": {
            "type": "string",
            "enum": [
                "settlement", "temple", "tomb", "fortification", "megalithic",
                "cave", "rock_art", "port", "monument", "inscription", "ruin",
                "archaeological_site", "Unknown",
            ],
        },
        "period": {
            "type": "string",
            "enum": [
                "< 4500 BC", "4500 - 3000 BC", "3000 - 1500 BC",
                "1500 - 500 BC", "500 BC - 1 AD", "1 - 500 AD",
                "500 - 1000 AD", "1000 - 1500 AD", "1500+ AD", "Unknown",
            ],
        },
        "brief_description": {"type": "string"},
        "approximate_lat": {"type": "number"},
        "approximate_lon": {"type": "number"},
        "coordinate_confidence": {
            "type": "string",
            "enum": ["exact", "approximate", "unknown"],
        },
    },
    "required": ["country", "site_type", "period"],
    "additionalProperties": False,
}

# --- API URLs ---

WIKIPEDIA_OPENSEARCH_URL = "https://en.wikipedia.org/w/api.php"
GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"


# --- Data classes ---

@dataclass
class ResearchResult:
    """Result of the multi-step research protocol."""
    pre_research: dict | None = None
    all_candidates: dict = field(default_factory=dict)
    best_match: dict | None = None
    gap_fill: dict | None = None
    search_names_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pre_research": self.pre_research,
            "best_match": self.best_match,
            "gap_fill": self.gap_fill,
            "search_names_used": self.search_names_used,
            "candidate_counts": {k: len(v) for k, v in self.all_candidates.items()},
        }


# --- Main entry point ---

def research_site(
    name: str,
    client: anthropic.Anthropic,
    settings: LyraSettings,
    facts: list[str],
    video_contexts: list[dict],
) -> ResearchResult:
    """Multi-step research agent protocol.

    1. MiniMax pre-research (generate search terms + prior knowledge)
    2. Multi-source API search (Wikidata, Wikipedia, GeoNames)
    3. MiniMax candidate selection (if ambiguous)
    4. MiniMax gap-fill (fill missing fields from AI knowledge)

    Always returns a ResearchResult (never None).
    """
    result = ResearchResult()

    # Step 1: MiniMax pre-research
    result.pre_research = _pre_research(name, client, settings, facts, video_contexts)

    # Build search names: original + AI-generated alternatives
    search_names = [name]
    if result.pre_research and result.pre_research.get("alternative_names"):
        for alt in result.pre_research["alternative_names"]:
            if alt and alt.lower().strip() != name.lower().strip() and alt not in search_names:
                search_names.append(alt)
    search_names = search_names[:settings.max_research_names]
    result.search_names_used = search_names

    logger.info(f"  [{name}] Research: searching with {len(search_names)} name variants: {search_names}")

    # Step 2: Multi-source API search
    result.all_candidates = _search_all_sources(search_names, settings)

    total_candidates = sum(len(v) for v in result.all_candidates.values())
    logger.info(
        f"  [{name}] Research: found {total_candidates} candidates "
        f"(wikidata={len(result.all_candidates.get('wikidata', []))}, "
        f"wikipedia={len(result.all_candidates.get('wikipedia', []))}, "
        f"geonames={len(result.all_candidates.get('geonames', []))})"
    )

    # Step 3: Candidate selection (if we found any candidates)
    if total_candidates > 0:
        result.best_match = _select_best_candidate(
            name, client, settings, facts, result.pre_research, result.all_candidates,
        )
        if result.best_match:
            logger.info(
                f"  [{name}] Research: best match from {result.best_match.get('source')}: "
                f"{result.best_match.get('id', 'N/A')} (confidence: {result.best_match.get('confidence')})"
            )

    # Step 4: Gap-fill (fill missing fields from AI knowledge)
    result.gap_fill = _gap_fill(name, client, settings, facts, result)

    return result


# --- Step 1: Pre-Research ---

def _pre_research(
    name: str,
    client: anthropic.Anthropic,
    settings: LyraSettings,
    facts: list[str],
    video_contexts: list[dict],
) -> dict | None:
    """Ask MiniMax what it knows about this site."""
    prompt_template = (PROMPT_DIR / "pre_research.txt").read_text(encoding="utf-8")

    facts_text = "\n".join(f"- {f}" for f in facts[:20]) if facts else "(none)"
    video_text = ""
    for ctx in video_contexts[:3]:
        video_text += f"  Title: {ctx.get('title', '')}\n"
        if ctx.get("description"):
            video_text += f"  Description: {ctx['description'][:300]}\n"
    video_text = video_text.strip() or "(none)"

    prompt = prompt_template.format(name=name, facts=facts_text, video_context=video_text)

    try:
        response = call_api(
            client,
            model=settings.model_identify,
            max_tokens=settings.research_thinking_budget + 1024,
            messages=[{"role": "user", "content": prompt}],
            system=[{
                "type": "text",
                "text": "You are an archaeological research agent. Respond with JSON only.",
                "cache_control": {"type": "ephemeral"},
            }],
            thinking={"type": "enabled", "budget_tokens": settings.research_thinking_budget},
        )
    except anthropic.APIError as e:
        logger.warning(f"  [{name}] Pre-research API error: {e}")
        return None

    for block in response.content:
        if hasattr(block, "text"):
            try:
                result = parse_json_response(block.text)
                logger.info(
                    f"  [{name}] Pre-research: country={result.get('country')}, "
                    f"well_known={result.get('well_known')}, "
                    f"alternatives={len(result.get('alternative_names', []))}"
                )
                return result
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"  [{name}] Pre-research parse error: {e}")
                return None

    return None


# --- Step 2: Multi-Source API Search ---

def _search_all_sources(
    names: list[str],
    settings: LyraSettings,
) -> dict[str, list[dict]]:
    """Search all sources with multiple name variants."""
    all_candidates: dict[str, list[dict]] = {
        "wikidata": [],
        "wikipedia": [],
        "geonames": [],
    }

    for name in names:
        all_candidates["wikidata"].extend(_search_wikidata_entities(name))
        all_candidates["wikipedia"].extend(_search_wikipedia_opensearch(name))
        if settings.geonames_username:
            all_candidates["geonames"].extend(
                _search_geonames(name, settings.geonames_username)
            )

    # Deduplicate within each source
    all_candidates["wikidata"] = _dedupe_by_key(all_candidates["wikidata"], "qid")
    all_candidates["wikipedia"] = _dedupe_by_key(all_candidates["wikipedia"], "title")
    all_candidates["geonames"] = _dedupe_by_key(all_candidates["geonames"], "geoname_id")

    return all_candidates


def _dedupe_by_key(items: list[dict], key: str) -> list[dict]:
    """Deduplicate list of dicts by a key field."""
    seen = set()
    result = []
    for item in items:
        val = item.get(key)
        if val and val not in seen:
            seen.add(val)
            result.append(item)
    return result


def _search_wikidata_entities(name: str) -> list[dict]:
    """Search Wikidata via wbsearchentities API."""
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
        logger.warning(f"Wikidata entity search failed for '{name}': {e}")
        return []

    return [
        {
            "qid": r.get("id"),
            "label": r.get("label"),
            "description": r.get("description", ""),
            "source": "wikidata",
        }
        for r in data.get("search", [])
    ]


def _search_wikipedia_opensearch(name: str, limit: int = 5) -> list[dict]:
    """Search Wikipedia for articles matching the site name."""
    try:
        resp = fetch_with_retry(
            WIKIPEDIA_OPENSEARCH_URL,
            params={
                "action": "opensearch",
                "search": name,
                "limit": str(limit),
                "namespace": "0",
                "format": "json",
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikipedia opensearch failed for '{name}': {e}")
        return []

    if len(data) < 4:
        return []

    return [
        {"title": t, "description": d, "url": u, "source": "wikipedia"}
        for t, d, u in zip(data[1], data[2], data[3])
    ]


def _search_geonames(name: str, username: str, limit: int = 5) -> list[dict]:
    """Search GeoNames for archaeological/historic sites."""
    try:
        resp = fetch_with_retry(
            GEONAMES_SEARCH_URL,
            params={
                "q": name,
                "maxRows": str(limit),
                "username": username,
                "featureClass": "S",
                "style": "FULL",
                "type": "json",
            },
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"GeoNames search failed for '{name}': {e}")
        return []

    return [
        {
            "geoname_id": p.get("geonameId"),
            "name": p.get("name"),
            "country": p.get("countryName"),
            "lat": float(p["lat"]) if p.get("lat") else None,
            "lon": float(p["lng"]) if p.get("lng") else None,
            "feature_code_name": p.get("fcodeName"),
            "wikipedia_url": p.get("wikipediaUrl"),
            "source": "geonames",
        }
        for p in data.get("geonames", [])
    ]


def _search_wikidata_sparql(name: str) -> list[dict]:
    """SPARQL search filtered to archaeological site instances."""
    # Escape for SPARQL string
    safe_name = name.replace('"', '').replace('\\', '')
    if not safe_name:
        return []

    query = f'''
    SELECT ?item ?itemLabel ?itemDescription ?coord ?countryLabel WHERE {{
      ?item rdfs:label ?label .
      FILTER(CONTAINS(LCASE(?label), LCASE("{safe_name}")))
      FILTER(LANG(?label) = "en")
      {{ ?item wdt:P31/wdt:P279* wd:Q839954 }}
      UNION {{ ?item wdt:P31/wdt:P279* wd:Q811979 }}
      UNION {{ ?item wdt:P31/wdt:P279* wd:Q570116 }}
      UNION {{ ?item wdt:P31/wdt:P279* wd:Q2065736 }}
      OPTIONAL {{ ?item wdt:P625 ?coord }}
      OPTIONAL {{ ?item wdt:P17 ?country }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
    }} LIMIT 10
    '''

    try:
        resp = fetch_with_retry(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"Wikidata SPARQL search failed for '{name}': {e}")
        return []

    results = []
    for binding in data.get("results", {}).get("bindings", []):
        item_uri = binding.get("item", {}).get("value", "")
        qid = item_uri.split("/")[-1] if "/entity/" in item_uri else None
        if not qid:
            continue
        results.append({
            "qid": qid,
            "label": binding.get("itemLabel", {}).get("value", ""),
            "description": binding.get("itemDescription", {}).get("value", ""),
            "country": binding.get("countryLabel", {}).get("value"),
            "source": "wikidata_sparql",
        })

    return results


# --- Step 3: Candidate Selection ---

def _select_best_candidate(
    name: str,
    client: anthropic.Anthropic,
    settings: LyraSettings,
    facts: list[str],
    pre_research: dict | None,
    all_candidates: dict[str, list[dict]],
) -> dict | None:
    """Ask MiniMax to pick the best candidate from multi-source results."""
    # Build formatted candidates string
    formatted_parts = []
    candidate_index = {}
    idx = 1

    for source, candidates in all_candidates.items():
        for c in candidates[:5]:
            label = c.get("label") or c.get("title") or c.get("name") or "?"
            desc = c.get("description") or c.get("feature_code_name") or ""
            cid = c.get("qid") or c.get("url") or str(c.get("geoname_id", ""))
            country = c.get("country") or ""
            country_str = f" [{country}]" if country else ""
            formatted_parts.append(f"  {idx}. [{source}] {label}{country_str}: {desc} (id: {cid})")
            candidate_index[str(idx)] = {"source": source, "id": cid, **c}
            idx += 1

    if not formatted_parts:
        return None

    # If only one candidate total, skip the AI call
    if len(formatted_parts) == 1:
        only = candidate_index["1"]
        return {**only, "confidence": "medium", "reasoning": "only candidate"}

    prompt_template = (PROMPT_DIR / "research_synthesis.txt").read_text(encoding="utf-8")

    pre_research_summary = "No pre-research available."
    if pre_research:
        parts = []
        if pre_research.get("country"):
            parts.append(f"country: {pre_research['country']}")
        if pre_research.get("region"):
            parts.append(f"region: {pre_research['region']}")
        if pre_research.get("approximate_period"):
            parts.append(f"period: {pre_research['approximate_period']}")
        if pre_research.get("site_type"):
            parts.append(f"type: {pre_research['site_type']}")
        pre_research_summary = ", ".join(parts) if parts else "No specific details."

    facts_text = "\n".join(f"- {f}" for f in facts[:15]) if facts else "(none)"

    prompt = prompt_template.format(
        name=name,
        pre_research_summary=pre_research_summary,
        facts=facts_text,
        formatted_candidates="\n".join(formatted_parts),
    )

    try:
        response = call_api(
            client,
            model=settings.model_identify,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system=[{
                "type": "text",
                "text": "You are an archaeological site research agent. Pick the best match from the candidates. Respond with JSON only.",
                "cache_control": {"type": "ephemeral"},
            }],
        )
    except anthropic.APIError as e:
        logger.warning(f"  [{name}] Research synthesis API error: {e}")
        return None

    for block in response.content:
        if hasattr(block, "text"):
            try:
                result = parse_json_response(block.text)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"  [{name}] Research synthesis parse error: {e}")
                return None

            if result.get("source") == "none":
                return None

            # Match back to our candidate index
            chosen_id = result.get("id", "")
            for c in candidate_index.values():
                cid = c.get("qid") or c.get("url") or str(c.get("geoname_id", ""))
                if cid == chosen_id:
                    return {**c, "confidence": result.get("confidence", "medium"), "reasoning": result.get("reasoning", "")}

            # If ID didn't match, return the raw result
            return result

    return None


# --- Step 4: Gap-Fill ---

def _gap_fill(
    name: str,
    client: anthropic.Anthropic,
    settings: LyraSettings,
    facts: list[str],
    research: ResearchResult,
) -> dict | None:
    """Fill missing metadata fields from AI knowledge."""
    # Determine what we already know
    known = {}
    missing = []

    # Check pre-research and best_match for existing data
    pr = research.pre_research or {}
    bm = research.best_match or {}

    if pr.get("country") or bm.get("country"):
        known["country"] = pr.get("country") or bm.get("country")
    else:
        missing.append("country")

    if pr.get("site_type"):
        known["site_type"] = pr["site_type"]
    else:
        missing.append("site_type")

    if pr.get("approximate_period"):
        known["period"] = pr["approximate_period"]
    else:
        missing.append("period")

    if pr.get("brief_description"):
        known["description"] = pr["brief_description"]
    else:
        missing.append("brief_description")

    if bm and bm.get("lat") and bm.get("lon"):
        known["coordinates"] = f"{bm['lat']}, {bm['lon']}"
    else:
        missing.append("approximate_lat, approximate_lon")

    # If nothing is missing, skip the gap-fill call
    if not missing:
        logger.info(f"  [{name}] Gap-fill: nothing missing, skipping")
        return None

    prompt_template = (PROMPT_DIR / "gap_fill.txt").read_text(encoding="utf-8")
    facts_text = "\n".join(f"- {f}" for f in facts[:15]) if facts else "(none)"

    prompt = prompt_template.format(
        name=name,
        known_fields=json.dumps(known, indent=2),
        missing_fields=", ".join(missing),
        facts=facts_text,
    )

    try:
        response = call_api(
            client,
            model=settings.model_identify,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system=[{
                "type": "text",
                "text": "You are an archaeological metadata enrichment agent. Fill missing fields from your knowledge. Respond with JSON only.",
                "cache_control": {"type": "ephemeral"},
            }],
        )
    except anthropic.APIError as e:
        logger.warning(f"  [{name}] Gap-fill API error: {e}")
        return None

    for block in response.content:
        if hasattr(block, "text"):
            try:
                result = parse_json_response(block.text)
                logger.info(
                    f"  [{name}] Gap-fill: country={result.get('country')}, "
                    f"type={result.get('site_type')}, period={result.get('period')}, "
                    f"coords=({result.get('approximate_lat')}, {result.get('approximate_lon')})"
                )
                return result
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"  [{name}] Gap-fill parse error: {e}")
                return None

    return None
