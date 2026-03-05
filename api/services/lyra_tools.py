"""
Lyra tool definitions and data helpers.

Contains all @tool functions, Seshat data loader, hybrid search,
and the TOOLS list exported for the agent loop.
"""

import json
import logging
import os
from pathlib import Path

from langchain_core.tools import tool
from sqlalchemy import text

from pipeline.database import get_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("LYRA_LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LYRA_LLM_MODEL", "MiniMax-M2.5")

# Per-request backend: set via contextvars by lyra_agent before each request.
# "voyage" (default) uses Voyage embeddings + original collections.
# "local" uses Ollama embeddings + *_local collections.


def _get_embedding_backend() -> str:
    """Get the embedding backend for the current request from contextvars."""
    try:
        from api.services.lyra_router import get_request_context

        return get_request_context().embedding_backend
    except LookupError:
        return "voyage"  # Default for non-chat contexts (e.g., indexing)


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
            logger.info(
                f"Loaded Seshat data from {path}: {len(_seshat_data.get('polities', {}))} polities"
            )
            return _seshat_data

    logger.warning("Seshat polities.json not found \u2014 empire knowledge unavailable")
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
    query = (query or "")[:500]
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
               country, description, thumbnail_url
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
                   country, description, thumbnail_url
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
        if r.thumbnail_url:
            site["thumbnail_url"] = r.thumbnail_url
        if r.description:
            site["description"] = r.description[:400]
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
        "thumbnail_url": row.thumbnail_url,
    }

    if names:
        site["alternate_names"] = [
            {"name": n.name, "lang": n.language_code, "type": n.name_type} for n in names
        ]

    if links:
        site["content_links"] = [
            {"type": l.content_type, "title": l.title, "url": l.content_url} for l in links
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
    query = (query or "")[:500]
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
               us.name AS canonical_site_name,
               ni.created_at::text AS created_at
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        LEFT JOIN unified_sites us ON ni.site_id = us.id
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
            "site_mentioned": r.canonical_site_name or r.site_name_extracted,
            "date": r.created_at,
        }
        if r.timestamp_seconds:
            item["timestamp_seconds"] = r.timestamp_seconds
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
            return json.dumps(
                {
                    "error": f"Polity '{empire_id}' not found. Did you mean: {matches[:5]}?",
                    "available_ids": matches[:10],
                }
            )
        return json.dumps(
            {
                "error": f"Polity '{empire_id}' not found.",
                "available_count": len(available),
                "sample_ids": available[:15],
            }
        )

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
    "transcripts": (
        "Prioritize transcript passages that contain specific discussions, quotes, "
        "or detailed mentions of the queried topic. Rank passages with concrete "
        "information, expert analysis, and named sites higher than passing mentions."
    ),
    "articles": (
        "Prioritize article sections that directly cover the queried topic with "
        "substantive analysis, specific findings, and cited sources. Rank sections "
        "with detailed reporting higher than brief mentions or summaries."
    ),
    "empires": (
        "Prioritize empires/civilizations that best match the queried time period, "
        "geographic region, or specific attributes (warfare, economy, governance). "
        "Rank empires with directly relevant characteristics higher than tangential matches."
    ),
}


def _hybrid_search(
    query: str,
    collection: str = "sites",
    limit: int = 5,
    country: str | None = None,
    period: str | None = None,
    site_type: str | None = None,
    channel: str | None = None,
) -> tuple[list[dict], int]:
    """Run hybrid dense+BM25 search with RRF fusion and reranking.

    Uses contextvars to determine which collection set and embedding backend to use.
    Returns tuple of (list of payload dicts with relevance scores, embed tokens used).
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

    backend = _get_embedding_backend()
    # Append _local suffix for local backend collections
    qdrant_collection = f"{collection}_local" if backend == "local" else collection

    voyage_tokens = 0
    client = get_qdrant_client()

    # Step 1: Embed query \u2014 dense (voyage-4) + sparse (BM25)
    embeddings = get_embeddings(usage="query", backend=backend)
    dense_vec = embeddings.embed_query(query)
    voyage_tokens += embeddings.last_total_tokens
    sparse_vecs = list(get_sparse_model().embed([query]))
    sparse_vec = models.SparseVector(
        indices=sparse_vecs[0].indices.tolist(),
        values=sparse_vecs[0].values.tolist(),
    )

    # Step 2: Build metadata filter
    conditions: list[models.FieldCondition | models.Filter] = []
    if country:
        conditions.append(
            models.FieldCondition(key="country", match=models.MatchText(text=country))
        )
    if period:
        conditions.append(
            models.FieldCondition(key="period_name", match=models.MatchText(text=period))
        )
    if site_type:
        conditions.append(
            models.FieldCondition(key="site_type", match=models.MatchText(text=site_type))
        )
    if channel:
        conditions.append(
            models.FieldCondition(key="channel", match=models.MatchText(text=channel))
        )
    query_filter = models.Filter(must=conditions) if conditions else None  # type: ignore[arg-type]

    # Step 3: Hybrid query \u2014 prefetch dense + BM25, fuse with RRF
    results = client.query_points(
        collection_name=qdrant_collection,
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

    # Step 4: Rerank with voyage rerank-2.5-lite \u2192 top K
    # Per Voyage docs: prepend instructions to the query for rerank-2.5-lite
    reranker = get_reranker(backend=backend)
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


@tool
def vector_search(
    query: str,
    collection: str = "sites",
    limit: int = 5,
    country: str | None = None,
    period: str | None = None,
    site_type: str | None = None,
    channel: str | None = None,
) -> str:
    """Deep semantic search across sites, news, transcripts, articles, or empires using hybrid dense+BM25 vectors.

    Use this for follow-up deep dives beyond the auto-retrieved context.
    Supports metadata filters for targeted searches.

    Args:
        query: Natural language query.
        collection: Which collection to search: 'sites', 'news', 'transcripts', 'articles', or 'empires'.
        limit: Max results (default 5).
        country: Filter by country name (e.g. 'Turkey', 'Egypt').
        period: Filter by period name (e.g. 'Bronze Age', 'Neolithic').
        site_type: Filter by site type (e.g. 'settlement', 'temple').
        channel: Filter by channel name (e.g. 'World of Antiquity'). Works on news and transcripts collections.
    """
    query = (query or "")[:500]
    items, _vt = _hybrid_search(
        query,
        collection=collection,
        limit=limit,
        country=country,
        period=period,
        site_type=site_type,
        channel=channel,
    )
    if not items:
        return f"No semantic matches in '{collection}' collection."
    return json.dumps(items, ensure_ascii=False)


@tool
def search_radar(
    query: str | None = None,
    country: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> str:
    """Search Lyra's auto-discovered archaeological sites (Radar).

    These are sites discovered by Lyra from YouTube archaeology channels,
    enriched with Wikidata/Wikipedia data. Use this when users ask about
    recent discoveries, new sites, or what Lyra has found.

    Args:
        query: Search by site name (optional).
        country: Filter by country (optional).
        status: Filter by status: 'enriched' (identified), 'promoted' (added to map), 'pending' (awaiting identification). Default: all visible.
        limit: Max results (default 10, max 20).
    """
    query = (query or "")[:500]
    limit = min(limit, 20)
    conditions = ["uc.source = 'lyra'"]
    params: dict = {"limit": limit}

    visible = ("enriched", "promoted", "pending")
    if status and status in visible:
        conditions.append("uc.enrichment_status = :status")
        params["status"] = status
    else:
        conditions.append("uc.enrichment_status IN ('enriched', 'promoted', 'pending')")

    if query:
        conditions.append("(uc.name ILIKE :q OR uc.corrected_name ILIKE :q)")
        params["q"] = f"%{query}%"
    if country:
        conditions.append("uc.country ILIKE :country")
        params["country"] = f"%{country}%"

    where = " AND ".join(conditions)
    sql = f"""
        SELECT uc.id, uc.name, uc.corrected_name, uc.country, uc.site_type,
               uc.period_name, uc.lat, uc.lon, uc.description,
               uc.enrichment_status, uc.mention_count, uc.score,
               uc.wikipedia_url, uc.thumbnail_url
        FROM user_contributions uc
        WHERE {where}
        ORDER BY uc.mention_count DESC, uc.score DESC NULLS LAST
        LIMIT :limit
    """
    with get_session() as session:
        result = session.execute(text(sql), params)
        rows = result.fetchall()

    if not rows:
        return "No Lyra discoveries found matching the search."

    items = []
    for r in rows:
        item = {
            "name": r.corrected_name or r.name,
            "original_name": r.name if r.corrected_name else None,
            "status": r.enrichment_status,
            "mentions": r.mention_count,
            "score": r.score,
            "country": r.country,
            "type": r.site_type,
            "period": r.period_name,
            "description": (r.description or "")[:200],
        }
        if r.lat and r.lon:
            item["lat"] = r.lat
            item["lon"] = r.lon
        if r.wikipedia_url:
            item["wikipedia"] = r.wikipedia_url
        items.append(item)

    return json.dumps(items, ensure_ascii=False)


@tool
def list_channels() -> str:
    """List all YouTube archaeology channels that Lyra monitors.

    Use this when users ask what channels you follow, what sources you have,
    or where your news comes from.
    """
    sql = """
        SELECT nc.id, nc.name, nc.enabled,
               COUNT(nv.id) AS video_count
        FROM news_channels nc
        LEFT JOIN news_videos nv ON nc.id = nv.channel_id
        GROUP BY nc.id, nc.name, nc.enabled
        ORDER BY video_count DESC
    """
    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    channels = []
    for r in rows:
        channels.append(
            {
                "name": r.name,
                "enabled": r.enabled,
                "videos_processed": r.video_count,
                "youtube_url": f"https://www.youtube.com/channel/{r.id}",
            }
        )

    return json.dumps(channels, ensure_ascii=False)


@tool
def get_site_images(
    site: str,
    limit: int = 20,
) -> str:
    """Get Wikipedia/Wikimedia Commons images for an archaeological site.

    Returns images with URLs, attribution, and metadata. Each image has:
    - original_url: Direct image URL — use this for inline images: ![title](original_url)
    - url: Local cached copy (may not be available)
    - commons_url: Wikimedia Commons page (for attribution links, NOT for img src)

    When displaying images, ALWAYS use original_url for the image source.
    Include author and license as attribution below each image.

    Args:
        site: Site UUID or name (e.g. 'Pompeii', 'fa2293fa-5256-4a41-9e61-26844e54fde4').
        limit: Maximum images to return (default 20, max 50).
    """
    import uuid as _uuid

    limit = min(limit, 50)

    try:
        _uuid.UUID(site)
        is_uuid = True
    except ValueError:
        is_uuid = False

    if is_uuid:
        site_id = site
    else:
        # Resolve name to UUID
        find_sql = """
            SELECT id::text FROM unified_sites
            WHERE lower(name) = lower(:name)
            LIMIT 1
        """
        with get_session() as session:
            row = session.execute(text(find_sql), {"name": site}).fetchone()
            if not row:
                return f"Site '{site}' not found."
            site_id = row.id

    sql = """
        SELECT filename, original_url, commons_page_url,
               author, author_url, license, license_url,
               title, is_hero, is_lead, source_type, width, height, site_id
        FROM wiki_images
        WHERE site_id = CAST(:site_id AS uuid)
        ORDER BY sort_order
        LIMIT :limit
    """
    with get_session() as session:
        result = session.execute(text(sql), {"site_id": site_id, "limit": limit})
        rows = result.fetchall()

    if not rows:
        return f"No cached images found for site '{site}'. Images may not have been downloaded yet."

    images = []
    for r in rows:
        sid_short = str(r.site_id).replace("-", "")[:8]
        img = {
            "title": r.title,
            "original_url": r.original_url,
            "url": f"/data/images/wiki/{sid_short}/{r.filename}",
            "commons_url": r.commons_page_url,
            "author": r.author,
            "author_url": r.author_url,
            "license": r.license,
            "license_url": r.license_url,
            "is_hero": r.is_hero,
            "source": r.source_type,
        }
        if r.width and r.height:
            img["dimensions"] = f"{r.width}x{r.height}"
        images.append(img)

    return json.dumps(images, ensure_ascii=False)


def _format_payload_for_rerank(payload: dict) -> str:
    """Format a Qdrant payload dict into text for the reranker."""
    parts = []
    if payload.get("name"):
        parts.append(payload["name"])
    if payload.get("headline"):
        parts.append(payload["headline"])
    if payload.get("title"):
        parts.append(payload["title"])
    if payload.get("video_title"):
        parts.append(payload["video_title"])
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
    if payload.get("text_preview"):
        parts.append(payload["text_preview"][:300])
    if payload.get("channel"):
        parts.append(f"Channel: {payload['channel']}")
    if payload.get("polity_id"):
        parts.append(f"Polity: {payload['polity_id']}")
    if payload.get("region"):
        parts.append(f"Region: {payload['region']}")
    if payload.get("capital"):
        parts.append(f"Capital: {payload['capital']}")
    if payload.get("start_year") is not None:
        parts.append(f"Period: {payload.get('start_year')} to {payload.get('end_year')}")
    return " | ".join(parts)


@tool
def search_transcripts(
    query: str,
    channel: str | None = None,
    limit: int = 5,
) -> str:
    """Search video transcript passages for specific discussions, quotes, or mentions.

    Returns excerpts with YouTube deep-link timestamps. Use this when users ask
    what creators have said about a topic, or to find specific discussions in videos.

    Args:
        query: What to search for in transcripts.
        channel: Filter by channel name (optional).
        limit: Max results (default 5, max 10).
    """
    query = (query or "")[:500]
    limit = min(limit, 10)

    # Use hybrid search on transcripts collection
    items, _vt = _hybrid_search(query, collection="transcripts", limit=limit, channel=channel)
    if not items:
        return "No transcript passages found matching the search."

    # Format as markdown with YouTube deep links
    lines = [f"Found {len(items)} transcript passage{'s' if len(items) != 1 else ''}:\n"]
    for i, item in enumerate(items, 1):
        video_id = item.get("video_id", "")
        video_title = item.get("video_title", "Unknown video")
        ch = item.get("channel", "")
        start = item.get("start_seconds", 0)
        preview = item.get("text_preview", "")

        # Format timestamp as MM:SS
        mins, secs = divmod(start, 60)
        ts_str = f"{mins}:{secs:02d}"

        yt_link = f"https://youtu.be/{video_id}?t={start}" if video_id else ""
        thumb = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else ""

        lines.append(f'{i}. **{ch}** — "{video_title}" (at {ts_str})')
        if thumb:
            lines.append(f"   ![thumbnail]({thumb})")
        if preview:
            lines.append(f"   > {preview}")
        if yt_link:
            lines.append(f"   Watch: {yt_link}")
        lines.append("")

    return "\n".join(lines)


@tool
def search_articles(
    query: str,
    limit: int = 5,
) -> str:
    """Search Lyra's weekly archaeological digest articles.

    These are magazine-quality articles generated from the week's most significant
    discoveries across all monitored YouTube channels. Use this when users ask
    about weekly summaries, digests, or want a comprehensive overview of recent findings.

    Args:
        query: What to search for in articles.
        limit: Max results (default 5, max 10).
    """
    query = (query or "")[:500]
    limit = min(limit, 10)

    items, _vt = _hybrid_search(query, collection="articles", limit=limit)
    if not items:
        return "No article passages found matching the search."

    lines = [f"Found {len(items)} article passage{'s' if len(items) != 1 else ''}:\n"]
    for i, item in enumerate(items, 1):
        title = item.get("title", "Untitled")
        week_start = item.get("week_start", "")
        preview = item.get("text_preview", "")
        summary = item.get("summary", "")

        # Format week range
        week_label = ""
        if week_start:
            week_label = f" (week of {week_start[:10]})"

        lines.append(f"{i}. **{title}**{week_label}")
        if summary:
            lines.append(f"   *{summary[:200]}*")
        if preview:
            lines.append(f"   > {preview}")
        lines.append("")

    return "\n".join(lines)


@tool
def search_empires(
    query: str,
    limit: int = 5,
) -> str:
    """Search ancient empires and civilizations using Seshat historical data.

    Use this to find empires by attributes like warfare technology, economy,
    geographic region, time period, or any other characteristic. Returns matched
    empires with key facts and Seshat polity IDs for deeper lookup with get_empire_data.

    Args:
        query: What to search for (e.g. 'largest army', 'iron age mesopotamia', 'naval power').
        limit: Max results (default 5, max 10).
    """
    query = (query or "")[:500]
    limit = min(limit, 10)

    items, _vt = _hybrid_search(query, collection="empires", limit=limit)
    if not items:
        return "No empires found matching the search."

    lines = [f"Found {len(items)} empire{'s' if len(items) != 1 else ''}:\n"]
    for i, item in enumerate(items, 1):
        name = item.get("name", "Unknown")
        polity_id = item.get("polity_id", "")
        start = item.get("start_year", "?")
        end = item.get("end_year", "?")
        capital = item.get("capital", "unknown")
        territory = item.get("territory")
        population = item.get("population")
        region = item.get("region", "")
        languages = item.get("languages", [])

        lines.append(f"{i}. **{name}** ({start} to {end})")
        lines.append(f"   - Polity ID: `{polity_id}`")
        lines.append(f"   - Capital: {capital} | Region: {region}")
        if territory:
            if isinstance(territory, (int, float)):
                lines.append(f"   - Territory: {territory:,} sq km")
            else:
                lines.append(f"   - Territory: {territory} sq km")
        if population:
            if isinstance(population, (int, float)):
                lines.append(f"   - Population: {population:,}")
            else:
                lines.append(f"   - Population: {population}")
        if languages:
            lines.append(f"   - Languages: {', '.join(languages)}")
        wiki = item.get("wikipedia_url")
        if wiki:
            lines.append(f"   - [Wikipedia]({wiki})")
        lines.append(
            f"   Use `get_empire_data('{polity_id}')` for full warfare, economy, and crisis data."
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exported tools list
# ---------------------------------------------------------------------------

TOOLS = [
    search_sites,
    get_site_details,
    search_news,
    get_empire_data,
    vector_search,
    search_radar,
    list_channels,
    get_site_images,
    search_transcripts,
    search_articles,
    search_empires,
]
