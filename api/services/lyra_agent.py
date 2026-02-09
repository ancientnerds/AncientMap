"""
Lyra RAG Agent — LangChain agent with tool calling.

Lyra Wiskerbyte is an archaeological agent who monitors YouTube channels,
extracts transcripts, and can chat about any of the 40K+ sites in the database.

Swappable LLM via env vars:
  LYRA_LLM_PROVIDER=anthropic  → ChatAnthropic (default)
  LYRA_LLM_PROVIDER=ollama     → ChatOllama
  LYRA_LLM_PROVIDER=openai     → ChatOpenAI
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import tool
from sqlalchemy import text

from pipeline.database import get_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("LYRA_LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LYRA_LLM_MODEL", "claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# Seshat polity data (loaded once from bundled JSON)
# ---------------------------------------------------------------------------

_seshat_data: dict | None = None


def _load_seshat_data() -> dict:
    """Load the bundled Seshat polities JSON (frontend bundle)."""
    global _seshat_data
    if _seshat_data is not None:
        return _seshat_data

    # Try the frontend bundle location
    candidates = [
        Path("ancient-nerds-map/src/data/seshat/polities.json"),
        Path("/app/ancient-nerds-map/src/data/seshat/polities.json"),
    ]
    for path in candidates:
        if path.exists():
            _seshat_data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"Loaded Seshat data from {path}: {len(_seshat_data.get('polities', {}))} polities")
            return _seshat_data

    logger.warning("Seshat polities.json not found — empire knowledge unavailable")
    _seshat_data = {"polities": {}}
    return _seshat_data


# ---------------------------------------------------------------------------
# Tools (LangChain @tool functions)
# ---------------------------------------------------------------------------

@tool
def search_sites(
    query: str,
    period: str | None = None,
    country: str | None = None,
    site_type: str | None = None,
    limit: int = 10,
) -> str:
    """Search archaeological sites by name, period, country, or type.

    Args:
        query: Search text (site name, keyword, or description fragment).
        period: Filter by period name (e.g. 'Bronze Age', 'Iron Age', 'Neolithic').
        country: Filter by country (e.g. 'Turkey', 'Egypt', 'Greece').
        site_type: Filter by site type (e.g. 'settlement', 'temple', 'burial').
        limit: Maximum results to return (default 10, max 25).
    """
    limit = min(limit, 25)
    conditions = ["1=1"]
    params: dict = {"limit": limit}

    if query:
        conditions.append(
            "(name ILIKE :q OR description ILIKE :q OR name_normalized ILIKE :q_norm)"
        )
        params["q"] = f"%{query}%"
        params["q_norm"] = f"%{query.lower()}%"

    if period:
        conditions.append("period_name ILIKE :period")
        params["period"] = f"%{period}%"

    if country:
        conditions.append("country ILIKE :country")
        params["country"] = f"%{country}%"

    if site_type:
        conditions.append("site_type ILIKE :site_type")
        params["site_type"] = f"%{site_type}%"

    where = " AND ".join(conditions)
    sql = f"""
        SELECT id::text, name, lat, lon, site_type, period_name, period_start,
               country, description
        FROM unified_sites
        WHERE {where}
        ORDER BY
            CASE WHEN name ILIKE :q THEN 0 ELSE 1 END,
            period_start ASC NULLS LAST
        LIMIT :limit
    """
    # If no query provided, don't use the ordering by name match
    if not query:
        sql = f"""
            SELECT id::text, name, lat, lon, site_type, period_name, period_start,
                   country, description
            FROM unified_sites
            WHERE {where}
            ORDER BY period_start ASC NULLS LAST
            LIMIT :limit
        """
        params["q"] = "%"

    with get_session() as session:
        result = session.execute(text(sql), params)
        rows = result.fetchall()

    if not rows:
        return "No sites found matching the search criteria."

    sites = []
    for r in rows:
        site = {
            "id": r.id,
            "name": r.name,
            "lat": round(r.lat, 4),
            "lon": round(r.lon, 4),
            "type": r.site_type,
            "period": r.period_name,
            "country": r.country,
        }
        if r.description:
            site["description"] = r.description[:200]
        sites.append(site)

    return json.dumps(sites, ensure_ascii=False)


@tool
def get_site_details(site_id: str) -> str:
    """Get detailed information about a specific archaeological site by its UUID or name.

    Args:
        site_id: The UUID or name/slug of the site.
    """
    import uuid as _uuid

    # Detect whether input is a UUID or a name/slug
    try:
        _uuid.UUID(site_id)
        is_uuid = True
    except ValueError:
        is_uuid = False

    if is_uuid:
        find_sql = """
            SELECT s.id::text, s.name, s.lat, s.lon, s.site_type, s.period_name,
                   s.period_start, s.period_end, s.country, s.description,
                   s.source_url, s.source_id, s.thumbnail_url
            FROM unified_sites s
            WHERE s.id = CAST(:site_id AS uuid)
        """
        find_params = {"site_id": site_id}
    else:
        # Name/slug lookup: replace hyphens with spaces, try exact match first (fast)
        search_name = site_id.replace("-", " ").replace("_", " ").strip()
        find_sql = """
            SELECT s.id::text, s.name, s.lat, s.lon, s.site_type, s.period_name,
                   s.period_start, s.period_end, s.country, s.description,
                   s.source_url, s.source_id, s.thumbnail_url
            FROM unified_sites s
            WHERE lower(s.name) = lower(:name)
            LIMIT 1
        """
        find_params = {"name": search_name}

    with get_session() as session:
        row = session.execute(text(find_sql), find_params).fetchone()
        if not row:
            return f"Site '{site_id}' not found."

        actual_uuid = row.id
        names_sql = """
            SELECT name, language_code, name_type
            FROM unified_site_names
            WHERE site_id = CAST(:site_id AS uuid)
            LIMIT 20
        """
        links_sql = """
            SELECT content_type, title, content_url
            FROM site_content_links
            WHERE site_id = CAST(:site_id AS uuid)
            LIMIT 10
        """
        names = session.execute(text(names_sql), {"site_id": actual_uuid}).fetchall()
        links = session.execute(text(links_sql), {"site_id": actual_uuid}).fetchall()

    site = {
        "id": row.id,
        "name": row.name,
        "lat": round(row.lat, 4),
        "lon": round(row.lon, 4),
        "type": row.site_type,
        "period": row.period_name,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "country": row.country,
        "description": row.description,
        "source_url": row.source_url,
        "source": row.source_id,
    }

    if names:
        site["alternate_names"] = [
            {"name": n.name, "lang": n.language_code, "type": n.name_type}
            for n in names
        ]

    if links:
        site["content_links"] = [
            {"type": l.content_type, "title": l.title, "url": l.content_url}
            for l in links
        ]

    return json.dumps(site, ensure_ascii=False)


@tool
def search_news(
    query: str,
    channel: str | None = None,
    days_back: int = 30,
    limit: int = 10,
) -> str:
    """Search recent archaeological news items from YouTube channels.

    Args:
        query: Search text for headline or summary.
        channel: Filter by channel name (optional).
        days_back: How many days back to search (default 30, max 365).
        limit: Maximum results (default 10, max 20).
    """
    limit = min(limit, 20)
    days_back = min(days_back, 365)

    conditions = ["ni.created_at > NOW() - :days_interval * INTERVAL '1 day'"]
    params: dict = {"days_interval": days_back, "limit": limit}

    if query:
        conditions.append("(ni.headline ILIKE :q OR ni.summary ILIKE :q)")
        params["q"] = f"%{query}%"

    if channel:
        conditions.append("nc.name ILIKE :channel")
        params["channel"] = f"%{channel}%"

    where = " AND ".join(conditions)
    sql = f"""
        SELECT ni.id, ni.headline, ni.summary, ni.significance, ni.news_category,
               ni.timestamp_seconds, ni.site_name_extracted,
               nv.id AS video_id, nv.title AS video_title,
               nc.name AS channel_name,
               ni.created_at::text AS created_at
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        WHERE {where}
        ORDER BY ni.created_at DESC
        LIMIT :limit
    """

    with get_session() as session:
        result = session.execute(text(sql), params)
        rows = result.fetchall()

    if not rows:
        return "No recent news items found matching the search."

    items = []
    for r in rows:
        item = {
            "id": r.id,
            "headline": r.headline,
            "summary": r.summary[:300] if r.summary else None,
            "significance": r.significance,
            "category": r.news_category,
            "channel": r.channel_name,
            "video_id": r.video_id,
            "video_title": r.video_title,
            "site_mentioned": r.site_name_extracted,
            "date": r.created_at,
        }
        if r.timestamp_seconds:
            item["youtube_link"] = f"https://youtu.be/{r.video_id}?t={r.timestamp_seconds}"
        items.append(item)

    return json.dumps(items, ensure_ascii=False)


@tool
def get_empire_data(empire_id: str) -> str:
    """Get Seshat historical data for an empire/civilization.

    Returns warfare technology, social complexity, economy, and crisis data.

    Args:
        empire_id: The Seshat polity ID (e.g. 'it_roman_principate', 'eg_new_kingdom').
            Common IDs: eg_new_kingdom, iq_neo_assyrian, it_roman_principate,
            gr_athenian, ir_achaemenid, cn_han_dynasty, in_maurya.
    """
    data = _load_seshat_data()
    polity = data.get("polities", {}).get(empire_id)

    if not polity:
        # Try fuzzy match
        available = list(data.get("polities", {}).keys())
        matches = [k for k in available if empire_id.lower() in k.lower()]
        if matches:
            return json.dumps({
                "error": f"Polity '{empire_id}' not found. Did you mean: {matches[:5]}?",
                "available_ids": matches[:10],
            })
        return json.dumps({
            "error": f"Polity '{empire_id}' not found.",
            "available_count": len(available),
            "sample_ids": available[:15],
        })

    return json.dumps(polity, ensure_ascii=False)


_RERANK_INSTRUCTIONS = {
    "sites": (
        "Prioritize archaeological sites that closely match the queried time period, "
        "site type, and geographic region. Rank sites with specific descriptions "
        "and well-documented provenance higher than generic entries."
    ),
    "news": (
        "Prioritize recent archaeological discoveries and research findings that "
        "directly address the query topic. Rank items with specific site names, "
        "dates, and factual claims higher than general commentary."
    ),
}


def _hybrid_search(
    query: str,
    collection: str = "sites",
    limit: int = 5,
    country: str | None = None,
    period: str | None = None,
    site_type: str | None = None,
) -> tuple[list[dict], int]:
    """Run hybrid dense+BM25 search with RRF fusion and Voyage reranking.

    Returns tuple of (list of payload dicts with relevance scores, voyage tokens used).
    Used by both _auto_retrieve() and the vector_search tool.
    """
    from qdrant_client import models

    from api.services.lyra_embeddings import (
        RERANK_MODEL,
        get_embeddings,
        get_qdrant_client,
        get_reranker,
        get_sparse_model,
    )

    voyage_tokens = 0
    client = get_qdrant_client()

    # Step 1: Embed query — dense (voyage-4) + sparse (BM25)
    embeddings = get_embeddings(usage="query")
    dense_vec = embeddings.embed_query(query)
    voyage_tokens += embeddings.last_total_tokens
    sparse_vecs = list(get_sparse_model().embed([query]))
    sparse_vec = models.SparseVector(
        indices=sparse_vecs[0].indices.tolist(),
        values=sparse_vecs[0].values.tolist(),
    )

    # Step 2: Build metadata filter
    conditions = []
    if country:
        conditions.append(models.FieldCondition(key="country", match=models.MatchText(text=country)))
    if period:
        conditions.append(models.FieldCondition(key="period_name", match=models.MatchText(text=period)))
    if site_type:
        conditions.append(models.FieldCondition(key="site_type", match=models.MatchText(text=site_type)))
    query_filter = models.Filter(must=conditions) if conditions else None

    # Step 3: Hybrid query — prefetch dense + BM25, fuse with RRF
    results = client.query_points(
        collection_name=collection,
        prefetch=[
            models.Prefetch(query=dense_vec, using="dense", limit=20, filter=query_filter),
            models.Prefetch(query=sparse_vec, using="bm25", limit=20, filter=query_filter),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=20,
    )

    scored_points = results.points
    if not scored_points:
        return [], voyage_tokens

    # Step 4: Rerank with voyage rerank-2.5-lite → top K
    # Per Voyage docs: prepend instructions to the query for rerank-2.5-lite
    reranker = get_reranker()
    docs = [_format_payload_for_rerank(hit.payload) for hit in scored_points]
    instruction = _RERANK_INSTRUCTIONS.get(collection, "")
    rerank_query = f"{instruction}\n{query}" if instruction else query
    reranked = reranker.rerank(rerank_query, docs, model=RERANK_MODEL, top_k=limit)
    voyage_tokens += getattr(reranked, "total_tokens", 0) or 0

    items = []
    for r in reranked.results:
        point = scored_points[r.index]
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        payload["relevance"] = round(r.relevance_score, 3)
        items.append(payload)
    return items, voyage_tokens


def _auto_retrieve(query: str, context_type: str) -> tuple[str, list[dict], float | None, int]:
    """Run automatic hybrid retrieval BEFORE the LLM sees the message.

    Searches the sites Qdrant collection to find relevant archaeological sites.
    News is fetched separately via _get_related_news() based on matched site IDs and query filters.

    Returns:
        Tuple of (formatted context string, list of site result dicts for map highlighting,
        average relevance score or None, total Voyage tokens used).
    """
    site_results: list[dict] = []
    all_relevance_scores: list[float] = []
    total_voyage_tokens = 0

    if context_type == "news":
        # News-only context: skip site search entirely
        return "", [], None, 0

    results, vt = _hybrid_search(query, collection="sites", limit=5)
    total_voyage_tokens += vt
    if not results:
        return "", [], None, total_voyage_tokens

    site_results = results
    for r in results:
        if "relevance" in r:
            all_relevance_scores.append(r["relevance"])

    lines = []
    for r in results:
        name = r.get("name", "?")
        period = r.get("period_name", "")
        country = r.get("country", "")
        desc = r.get("description", "")[:150]
        lat = r.get("lat", "")
        lon = r.get("lon", "")
        line = f"- **{name}** ({period}, {country}) [{lat}, {lon}]"
        if desc:
            line += f" — {desc}"
        lines.append(line)

    avg_relevance = sum(all_relevance_scores) / len(all_relevance_scores) if all_relevance_scores else None
    context_str = "\n\n## Retrieved Context\nThe following results were automatically retrieved for the user's query:\n\n### Sites\n" + "\n".join(lines) + "\n"
    return context_str, site_results, avg_relevance, total_voyage_tokens


def _get_related_news(
    site_ids: list[str] | None = None,
    site_names: list[str] | None = None,
    country: str | None = None,
    category: str | None = None,
    channel: str | None = None,
    period: str | None = None,
    site_type: str | None = None,
    min_significance: int | None = None,
    max_year: int | None = None,
    min_year: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """Query the DB for news items matching any combination of filters.

    Filters are ANDed together (except site_ids/site_names which are ORed).
    At least one filter must be provided.
    Returns news items joined with video + site metadata, ordered by significance desc.
    """
    conditions = []
    params: dict = {}

    # Site match: by ID or by extracted name (ORed — covers cross-source ID mismatches)
    site_conditions = []
    if site_ids:
        site_conditions.append("ni.site_id = ANY(CAST(:site_ids AS uuid[]))")
        params["site_ids"] = site_ids
    if site_names:
        name_clauses = []
        for i, name in enumerate(site_names):
            key = f"sname_{i}"
            # Match both with and without spaces (e.g. "Karahan Tepe" vs "Karahantepe")
            name_clauses.append(f"ni.site_name_extracted ILIKE :{key}")
            params[key] = f"%{name}%"
            # Also try the name with spaces removed
            compact = name.replace(" ", "")
            if compact != name:
                key_c = f"sname_{i}_c"
                name_clauses.append(f"ni.site_name_extracted ILIKE :{key_c}")
                params[key_c] = f"%{compact}%"
        site_conditions.append(f"({' OR '.join(name_clauses)})")
    if site_conditions:
        conditions.append(f"({' OR '.join(site_conditions)})")

    if country:
        conditions.append("us.country ILIKE :country")
        params["country"] = f"%{country}%"
    if category:
        conditions.append("ni.news_category = :category")
        params["category"] = category
    if channel:
        conditions.append("nc.name ILIKE :channel")
        params["channel"] = f"%{channel}%"
    if period:
        conditions.append("us.period_name ILIKE :period")
        params["period"] = f"%{period}%"
    if site_type:
        conditions.append("us.site_type ILIKE :site_type")
        params["site_type"] = f"%{site_type}%"
    if min_significance is not None:
        conditions.append("ni.significance >= :min_sig")
        params["min_sig"] = min_significance
    if max_year is not None:
        conditions.append("us.period_start IS NOT NULL AND us.period_start <= :max_year")
        params["max_year"] = max_year
    if min_year is not None:
        conditions.append("us.period_start IS NOT NULL AND us.period_start >= :min_year")
        params["min_year"] = min_year

    if not conditions:
        return []

    where_clause = " AND ".join(conditions)
    params["lim"] = limit

    sql = f"""
        SELECT ni.id, ni.headline, ni.summary, ni.video_id, ni.timestamp_seconds,
               ni.news_category, ni.significance, ni.created_at,
               ni.post_text, ni.screenshot_url, ni.site_name_extracted,
               nv.title AS video_title, nc.name AS channel,
               us.country AS site_country, us.site_type AS site_type,
               us.period_name AS site_period_name, us.period_start AS site_period_start
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        LEFT JOIN unified_sites us ON ni.site_id = us.id
        WHERE {where_clause}
        ORDER BY ni.significance DESC NULLS LAST, ni.created_at DESC
        LIMIT :lim
    """
    with get_session() as session:
        rows = session.execute(text(sql), params).fetchall()

    return [
        {
            "headline": row.headline,
            "summary": row.summary,
            "channel": row.channel or "",
            "video_id": row.video_id,
            "video_title": row.video_title,
            "timestamp_seconds": row.timestamp_seconds,
            "category": row.news_category,
            "significance": row.significance,
            "date": str(row.created_at) if row.created_at else None,
            "post_text": row.post_text,
            "screenshot_url": row.screenshot_url,
            "site_name": row.site_name_extracted,
            "site_country": row.site_country,
            "site_type": row.site_type,
            "site_period_name": row.site_period_name,
            "site_period_start": row.site_period_start,
        }
        for row in rows
    ]


_NEWS_FILTER_EXTRACTION_PROMPT = """You are a filter extractor for an archaeology news database. Given a user query, extract structured filters to find relevant news items.

The current year is 2026. The database stores period_start as an integer year (negative = BCE, positive = CE).

Return a JSON object with ONLY the fields that apply (omit fields that don't apply):

- "site_names": List of archaeological site names mentioned in the query. Include alternate spellings (e.g. ["Karahan Tepe", "Karahantepe"]). ALWAYS extract site names when the user asks about a specific site.
- "country": The country name as stored in a DB (e.g. "Turkey" not "Anatolia", "Egypt" not "Nile Valley"). Resolve region names to countries.
- "category": One of: excavation, artifact, architecture, bioarchaeology, dating, remote_sensing, underwater, epigraphy, conservation, heritage, theory, technology, survey, art, general
- "period": Archaeological period name (e.g. "Neolithic", "Bronze Age", "Iron Age", "Roman", "Byzantine", "Medieval")
- "site_type": Site classification (e.g. "settlement", "temple", "burial", "fortress/citadel", "megalithic stones", "cave", "pyramid", "mound/tumulus")
- "channel": YouTube channel name if the user mentions one
- "min_significance": Integer 1-10. Set to 5+ for "important/significant/major", 7+ for "groundbreaking/breakthrough"
- "max_year": Integer. For "older than N years" → 2026 - N. For "before 500 BC" → -500. Sites with period_start <= this value.
- "min_year": Integer. For "after 500 BC" → -500. For "last 3000 years" → -974. Sites with period_start >= this value.

Examples:
- "recent discoveries in Turkey" → {"country": "Turkey", "min_significance": 5}
- "underwater archaeology in Greece" → {"country": "Greece", "category": "underwater"}
- "Neolithic temples in Malta" → {"country": "Malta", "category": "architecture", "period": "Neolithic"}
- "what has MegalithomaniaUK been covering?" → {"channel": "MegalithomaniaUK"}
- "major pyramid finds in Egypt" → {"country": "Egypt", "category": "architecture", "min_significance": 7}
- "castles older than 2000 years in Peru from DeDunking" → {"site_type": "fortress/citadel", "max_year": 26, "country": "Peru", "channel": "DeDunking"}
- "Bronze Age sites before 1500 BC" → {"period": "Bronze Age", "max_year": -1500}
- "tell me about Göbekli Tepe" → {"site_names": ["Göbekli Tepe", "Gobekli Tepe"]}
- "recent discoveries about Karahantepe" → {"site_names": ["Karahan Tepe", "Karahantepe"]}
- "news about Pompeii excavations" → {"site_names": ["Pompeii"], "category": "excavation"}

Return ONLY valid JSON, no explanation."""


async def _extract_news_filters(query: str) -> dict:
    """Use Haiku to extract structured news filters from the user's query.

    Returns a dict of filter kwargs suitable for _get_related_news().
    """
    from langchain_anthropic import ChatAnthropic

    api_key = os.getenv("LYRA_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        temperature=0,
        api_key=api_key,
    )
    response = await llm.ainvoke([
        SystemMessage(content=_NEWS_FILTER_EXTRACTION_PROMPT),
        HumanMessage(content=query),
    ])

    try:
        raw = response.content.strip()
        # Strip markdown code fences if Haiku wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0].strip()
        filters = json.loads(raw)
        # Validate: only keep known keys
        valid_keys = {"site_names", "country", "category", "period", "site_type", "channel", "min_significance", "max_year", "min_year"}
        return {k: v for k, v in filters.items() if k in valid_keys and v is not None}
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"Failed to parse news filter extraction: {response.content}")
        return {}


@tool
def vector_search(
    query: str,
    collection: str = "sites",
    limit: int = 5,
    country: str | None = None,
    period: str | None = None,
    site_type: str | None = None,
) -> str:
    """Deep semantic search across sites or news using hybrid dense+BM25 vectors.

    Use this for follow-up deep dives beyond the auto-retrieved context.
    Supports metadata filters for targeted searches.

    Args:
        query: Natural language query.
        collection: Which collection to search: 'sites' or 'news'.
        limit: Max results (default 5).
        country: Filter by country name (e.g. 'Turkey', 'Egypt').
        period: Filter by period name (e.g. 'Bronze Age', 'Neolithic').
        site_type: Filter by site type (e.g. 'settlement', 'temple').
    """
    items, _vt = _hybrid_search(
        query, collection=collection, limit=limit,
        country=country, period=period, site_type=site_type,
    )
    if not items:
        return f"No semantic matches in '{collection}' collection."
    return json.dumps(items, ensure_ascii=False)


def _format_payload_for_rerank(payload: dict) -> str:
    """Format a Qdrant payload dict into text for the reranker."""
    parts = []
    if payload.get("name"):
        parts.append(payload["name"])
    if payload.get("headline"):
        parts.append(payload["headline"])
    if payload.get("site_type"):
        parts.append(f"Type: {payload['site_type']}")
    if payload.get("period_name"):
        parts.append(f"Period: {payload['period_name']}")
    if payload.get("country"):
        parts.append(f"Country: {payload['country']}")
    if payload.get("description"):
        parts.append(payload["description"][:300])
    if payload.get("summary"):
        parts.append(payload["summary"][:300])
    if payload.get("channel"):
        parts.append(f"Channel: {payload['channel']}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# LLM initialization
# ---------------------------------------------------------------------------

_llm = None


def _get_llm():
    """Get the configured LLM (singleton)."""
    global _llm
    if _llm is not None:
        return _llm

    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("LYRA_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        _llm = ChatAnthropic(model=LLM_MODEL, max_tokens=1024, streaming=True, stream_usage=True, api_key=api_key)
    elif LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama
        _llm = ChatOllama(model=LLM_MODEL, streaming=True)
    elif LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model=LLM_MODEL, max_tokens=1024, streaming=True)
    else:
        raise ValueError(f"Unknown LYRA_LLM_PROVIDER: {LLM_PROVIDER}")

    logger.info(f"Initialized LLM: {LLM_PROVIDER}/{LLM_MODEL}")
    return _llm


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

LYRA_SYSTEM_PROMPT = """You are LYRA WISKERBYTE, an archaeological AI agent for the Ancient Nerds Map project.

## Your Identity
- One of 100 biopunk Ancient Nerds using pre-Flood tech to uncover lost knowledge
- You monitor 18+ archaeology YouTube channels 24/7 via RSS
- You extract transcripts, distill headlines and facts, and deep-link timestamps
- You know 40,000+ archaeological sites with name variants across the world
- You have access to Seshat historical data for 37 empires/civilizations

## Your Capabilities
1. **Auto-Retrieved Context** — Relevant sites and news are automatically retrieved below. Use this data to answer.
2. **Site Search** — For structured filters (period, country, type) or follow-up queries
3. **News Intelligence** — Search recent archaeological discoveries from YouTube channels
4. **Empire Knowledge** — Access Seshat polity data (warfare, social, economy, crisis)
5. **Image Analysis** — Analyze photos of artifacts, ruins, and inscriptions
6. **Semantic Search** — Deep-dive vector search with metadata filters for follow-up queries

## Behavior
- You have retrieved context below. Use it to answer the user's question directly.
- Use tools for follow-up details, structured filters, or when the retrieved context is insufficient.
- When asked about empires, USE get_empire_data with the Seshat polity ID.
- When shown an image, describe what you see and try to identify the period/culture.
- Be knowledgeable but concise. Archaeology nerds are your audience.
- Include specific dates, coordinates, and links when available.
- If you find relevant sites, list them with coordinates so they can be highlighted on the map.
- Speak naturally but with authority. You live and breathe archaeology.
- When uncertain, say so — never fabricate site data or dates.
"""


def _build_context_prompt(context_type: str, context_id: str | None, context_year: int | None) -> str:
    """Build additional context for the system prompt based on where the user opened the chat."""
    if context_type == "global" or not context_id:
        return ""

    if context_type == "site":
        # Pre-fetch site data for context
        sql = """
            SELECT name, site_type, period_name, period_start, country, description
            FROM unified_sites WHERE id = CAST(:site_id AS uuid)
        """
        with get_session() as session:
            row = session.execute(text(sql), {"site_id": context_id}).fetchone()
        if row:
            return (
                f"\n\n## Current Context — Site\n"
                f"The user is viewing: **{row.name}**\n"
                f"- Type: {row.site_type or 'unknown'}\n"
                f"- Period: {row.period_name or 'unknown'} (start: {row.period_start or '?'})\n"
                f"- Country: {row.country or 'unknown'}\n"
                f"- Description: {(row.description or 'No description')[:300]}\n"
                f"Answer questions in the context of this site."
            )

    if context_type == "empire":
        data = _load_seshat_data()
        polity = data.get("polities", {}).get(context_id)
        if polity:
            year_info = f" at year {context_year}" if context_year else ""
            return (
                f"\n\n## Current Context — Empire\n"
                f"The user is viewing: **{polity.get('name', context_id)}**{year_info}\n"
                f"- Period: {polity.get('startYear', '?')} to {polity.get('endYear', '?')}\n"
                f"- Capital: {polity.get('capital', 'unknown')}\n"
                f"- Population: {polity.get('population', 'unknown')}\n"
                f"Answer questions in the context of this empire."
            )

    if context_type == "news":
        sql = """
            SELECT ni.headline, ni.summary, nv.title AS video_title, nc.name AS channel
            FROM news_items ni
            JOIN news_videos nv ON ni.video_id = nv.id
            JOIN news_channels nc ON nv.channel_id = nc.id
            WHERE ni.id = :news_id
        """
        with get_session() as session:
            row = session.execute(text(sql), {"news_id": int(context_id)}).fetchone()
        if row:
            return (
                f"\n\n## Current Context — News Item\n"
                f"The user is viewing a news item:\n"
                f"- Headline: {row.headline}\n"
                f"- Summary: {(row.summary or '')[:300]}\n"
                f"- From: {row.channel} — {row.video_title}\n"
                f"Answer questions in the context of this news item."
            )

    return ""


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

TOOLS = [search_sites, get_site_details, search_news, get_empire_data, vector_search]


def _build_messages(
    message: str,
    images: list[dict] | None,
    history: list[dict] | None,
    context_type: str,
    context_id: str | None,
    context_year: int | None,
    retrieved_context: str = "",
) -> list:
    """Build the message list for the LLM."""
    system_text = LYRA_SYSTEM_PROMPT + _build_context_prompt(context_type, context_id, context_year) + retrieved_context
    messages = [SystemMessage(content=system_text)]

    # Add conversation history
    if history:
        for msg in history[-10:]:  # Last 10 messages
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=msg["content"]))

    # Build the current user message (may include images)
    content_blocks = []
    if images:
        for img in images:
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": img["data"]},
            })
    content_blocks.append({"type": "text", "text": message})

    if len(content_blocks) == 1:
        messages.append(HumanMessage(content=message))
    else:
        messages.append(HumanMessage(content=content_blocks))

    return messages


async def run_agent_stream(
    message: str,
    images: list[dict] | None = None,
    history: list[dict] | None = None,
    context_type: str = "global",
    context_id: str | None = None,
    context_year: int | None = None,
) -> AsyncIterator[dict]:
    """
    Run the Lyra agent and stream results.

    Yields dicts with:
      {"type": "token", "content": "..."}
      {"type": "sites", "sites": [...]}
      {"type": "done", "metadata": {...}}
      {"type": "error", "error": "..."}
    """
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(TOOLS)

    # Auto-retrieve: run hybrid search BEFORE the LLM sees the message
    # Skip for image-only queries (no meaningful text to search)
    retrieved_context = ""
    all_sites: list[dict] = []
    all_news: list[dict] = []
    avg_relevance: float | None = None
    total_input_tokens = 0
    total_output_tokens = 0
    total_voyage_tokens = 0
    if message and len(message.strip()) > 2:
        # Auto-retrieve sites from Qdrant (isolated so Qdrant failures don't kill the response)
        auto_site_results: list[dict] = []
        try:
            retrieved_context, auto_site_results, avg_relevance, vt = _auto_retrieve(message, context_type)
            total_voyage_tokens += vt
        except Exception as e:
            logger.error(f"Auto-retrieve failed (Qdrant/Voyage issue, falling back to filter-based news): {e}")

        # Extract sites from auto-retrieved results for map highlighting
        # Only include sites with relevance above threshold to avoid irrelevant results
        SITE_RELEVANCE_THRESHOLD = 0.3
        for s in auto_site_results:
            if s.get("lat") and s.get("lon") and s.get("relevance", 0) >= SITE_RELEVANCE_THRESHOLD:
                all_sites.append({
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "site_type": s.get("site_type"),
                    "period_name": s.get("period_name"),
                    "country": s.get("country"),
                })

        # Fetch related news: site-specific first, then broader filters
        site_ids = [s["id"] for s in all_sites if s.get("id")]
        site_names = [s["name"] for s in all_sites if s.get("name")]

        # Site-specific news (by ID and name — always works, no LLM needed)
        all_news = _get_related_news(site_ids=site_ids, site_names=site_names) if (site_ids or site_names) else []

        # Filter-based news (uses Haiku to extract filters including site names — catches site queries even when Qdrant is down)
        try:
            news_filters = await _extract_news_filters(message)
            if news_filters:
                filter_news = _get_related_news(**news_filters)
                existing_keys = {f"{n['video_id']}::{n['headline']}" for n in all_news}
                for n in filter_news:
                    key = f"{n['video_id']}::{n['headline']}"
                    if key not in existing_keys:
                        all_news.append(n)
                        existing_keys.add(key)
        except Exception as e:
            logger.warning(f"News filter extraction failed: {e}")

        # Add news to retrieved context so the LLM can reference them
        if all_news:
            news_lines = []
            for n in all_news:
                line = f"- **{n['headline']}** (from {n['channel']})"
                if n.get("summary"):
                    line += f" — {n['summary'][:150]}"
                if n.get("video_id"):
                    line += f" [youtube: {n['video_id']}]"
                news_lines.append(line)
            retrieved_context += "\n\n### Related News\n" + "\n".join(news_lines) + "\n"

    messages = _build_messages(message, images, history, context_type, context_id, context_year, retrieved_context)

    # Emit auto-retrieved sites immediately for map highlighting
    if all_sites:
        yield {"type": "sites", "sites": all_sites}

    # Emit news linked to matched sites for sidebar
    if all_news:
        yield {"type": "news", "news": all_news}

    tool_calls_made = 0
    max_tool_rounds = 5

    for _round in range(max_tool_rounds):
        # Stream the LLM response
        collected_content = ""
        tool_calls = []

        async for chunk in llm_with_tools.astream(messages):
            if isinstance(chunk, AIMessageChunk):
                # Track token usage from chunks (Anthropic sends on final chunk)
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    um = chunk.usage_metadata
                    total_input_tokens += um.get("input_tokens", 0) or 0
                    total_output_tokens += um.get("output_tokens", 0) or 0
                if chunk.content:
                    text_content = chunk.content if isinstance(chunk.content, str) else ""
                    if isinstance(chunk.content, list):
                        for block in chunk.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_content += block.get("text", "")
                            elif isinstance(block, str):
                                text_content += block
                    if text_content:
                        collected_content += text_content
                        yield {"type": "token", "content": text_content}

                if chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        # Find or create the tool call entry
                        existing = None
                        for existing_tc in tool_calls:
                            if existing_tc.get("index") == tc.get("index"):
                                existing = existing_tc
                                break
                        if existing:
                            existing["args"] = existing.get("args", "") + (tc.get("args") or "")
                        else:
                            tool_calls.append({
                                "index": tc.get("index"),
                                "id": tc.get("id"),
                                "name": tc.get("name"),
                                "args": tc.get("args") or "",
                            })

        # If no tool calls, we're done
        if not tool_calls:
            break

        # The preamble text (e.g. "I'll search for...") was streamed as tokens.
        # Re-emit it as a status event so the frontend can style it differently,
        # then clear the token content so the real answer starts fresh.
        if collected_content.strip():
            yield {"type": "status", "content": collected_content.strip()}

        # Execute tool calls
        from langchain_core.messages import AIMessage, ToolMessage

        # Add the AI message with tool calls to conversation
        ai_msg = AIMessage(
            content=collected_content,
            tool_calls=[
                {"id": tc["id"], "name": tc["name"], "args": json.loads(tc["args"]) if tc["args"] else {}}
                for tc in tool_calls if tc.get("id") and tc.get("name")
            ],
        )
        messages.append(ai_msg)

        # Execute each tool and add results
        tool_map = {t.name: t for t in TOOLS}
        for tc in tool_calls:
            if not tc.get("name") or not tc.get("id"):
                continue
            tool_fn = tool_map.get(tc["name"])
            if not tool_fn:
                messages.append(ToolMessage(content=f"Unknown tool: {tc['name']}", tool_call_id=tc["id"]))
                continue

            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
                result = tool_fn.invoke(args)
                tool_calls_made += 1

                # Extract site data for highlighting
                if tc["name"] in ("search_sites", "get_site_details", "vector_search"):
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, list):
                            for s in parsed:
                                if "lat" in s and "lon" in s:
                                    all_sites.append({
                                        "id": s.get("id", ""),
                                        "name": s.get("name", ""),
                                        "lat": s["lat"],
                                        "lon": s["lon"],
                                        "site_type": s.get("type") or s.get("site_type"),
                                        "period_name": s.get("period") or s.get("period_name"),
                                        "country": s.get("country"),
                                    })
                        elif isinstance(parsed, dict) and "lat" in parsed:
                            all_sites.append({
                                "id": parsed.get("id", ""),
                                "name": parsed.get("name", ""),
                                "lat": parsed["lat"],
                                "lon": parsed["lon"],
                                "site_type": parsed.get("type") or parsed.get("site_type"),
                                "period_name": parsed.get("period") or parsed.get("period_name"),
                                "country": parsed.get("country"),
                            })
                    except (json.JSONDecodeError, KeyError):
                        pass

                messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

            except Exception as e:
                logger.error(f"Tool {tc['name']} failed: {e}")
                messages.append(ToolMessage(content=f"Tool error: {e}", tool_call_id=tc["id"]))

        # Emit sites after tool calls
        if all_sites:
            yield {"type": "sites", "sites": all_sites}

        # Fetch news for any new sites found via tool calls
        new_site_ids = [s["id"] for s in all_sites if s.get("id")]
        new_site_names = [s["name"] for s in all_sites if s.get("name")]
        tool_news = _get_related_news(site_ids=new_site_ids, site_names=new_site_names) if (new_site_ids or new_site_names) else []
        if tool_news:
            # Deduplicate against already-emitted news
            existing_keys = {f"{n['video_id']}::{n['headline']}" for n in all_news}
            new_news = [n for n in tool_news if f"{n['video_id']}::{n['headline']}" not in existing_keys]
            if new_news:
                all_news.extend(new_news)
                yield {"type": "news", "news": all_news}

    # Done
    yield {"type": "done", "metadata": {
        "model": f"{LLM_PROVIDER}/{LLM_MODEL}",
        "tool_calls": tool_calls_made,
        "sites_found": len(all_sites),
        "avg_relevance": round(avg_relevance, 3) if avg_relevance is not None else None,
        "tokens": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "voyage": total_voyage_tokens,
        },
    }}
