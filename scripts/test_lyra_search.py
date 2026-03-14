#!/usr/bin/env python3
"""Local test for Lyra search components — verifies search_news, auto-retrieve, and synthesis.

Usage:
    # Test against local Docker DB (must have ancient_nerds_db running):
    python scripts/test_lyra_search.py

    # Test specific query:
    python scripts/test_lyra_search.py "Sacsayhuaman tunnels"

    # Test search_news SQL only (no Qdrant needed):
    python scripts/test_lyra_search.py --sql-only "Sacsayhuaman tunnels"
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_search_news_sql(query: str, days_back: int = 365) -> list[dict]:
    """Test search_news SQL directly against the database."""
    from sqlalchemy import text

    from pipeline.database import get_session

    # Replicate the search_news SQL with full-text search
    params: dict = {"days_interval": days_back, "limit": 10, "q": query}
    sql = """
        SELECT DISTINCT ON (nv.id)
               ni.id, ni.headline, ni.summary, ni.significance,
               ni.site_name_extracted,
               nv.id AS video_id, nv.title AS video_title,
               nc.name AS channel_name,
               ni.created_at::text AS created_at
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        LEFT JOIN unified_sites us ON ni.site_id = us.id
        WHERE ni.created_at > NOW() - :days_interval * INTERVAL '1 day'
          AND to_tsvector('english', unaccent(coalesce(ni.headline, '') || ' ' || coalesce(ni.summary, '')))
              @@ plainto_tsquery('english', unaccent(:q))
        ORDER BY nv.id, ni.significance DESC NULLS LAST, ni.created_at DESC
    """
    sql = f"""
        SELECT * FROM ({sql}) deduped
        ORDER BY created_at DESC
        LIMIT :limit
    """

    with get_session() as session:
        result = session.execute(text(sql), params)
        rows = result.fetchall()

    items = []
    for row in rows:
        items.append({
            "headline": row.headline,
            "summary": (row.summary or "")[:150],
            "channel": row.channel_name,
            "video_id": row.video_id,
            "video_title": row.video_title,
            "site_name": row.site_name_extracted,
            "significance": row.significance,
        })
    return items


def test_search_news_ilike(query: str, days_back: int = 365) -> list[dict]:
    """Test the OLD ILIKE search for comparison."""
    from sqlalchemy import text

    from pipeline.database import get_session

    safe_q = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params: dict = {"days_interval": days_back, "limit": 10, "q": f"%{safe_q}%"}
    sql = """
        SELECT DISTINCT ON (nv.id)
               ni.headline, ni.summary, nc.name AS channel_name,
               nv.id AS video_id
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        WHERE ni.created_at > NOW() - :days_interval * INTERVAL '1 day'
          AND (ni.headline ILIKE :q OR ni.summary ILIKE :q)
        ORDER BY nv.id, ni.significance DESC NULLS LAST
        LIMIT :limit
    """

    with get_session() as session:
        result = session.execute(text(sql), params)
        rows = result.fetchall()

    return [{"headline": r.headline, "channel": r.channel_name, "video_id": r.video_id} for r in rows]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test Lyra search components")
    parser.add_argument("query", nargs="?", default="Sacsayhuaman tunnels")
    parser.add_argument("--sql-only", action="store_true", help="Only test SQL (no Qdrant)")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    query = args.query
    print(f"\n{'='*60}")
    print(f"Testing query: {query!r}")
    print(f"{'='*60}\n")

    # Test 1: SQL full-text search (new)
    print("--- search_news (full-text search) ---")
    try:
        fts_results = test_search_news_sql(query, args.days)
        if fts_results:
            for i, r in enumerate(fts_results):
                print(f"  [{i+1}] {r['headline']}")
                print(f"      channel: {r['channel']}, video: {r['video_id']}")
                if r.get("summary"):
                    print(f"      summary: {r['summary'][:100]}...")
        else:
            print("  (no results)")
        print(f"  Total: {len(fts_results)} results\n")
    except Exception as e:
        print(f"  ERROR: {e}\n")

    # Test 2: SQL ILIKE search (old — for comparison)
    print("--- search_news (old ILIKE — for comparison) ---")
    try:
        ilike_results = test_search_news_ilike(query, args.days)
        if ilike_results:
            for i, r in enumerate(ilike_results):
                print(f"  [{i+1}] {r['headline']} ({r['channel']})")
        else:
            print("  (no results)")
        print(f"  Total: {len(ilike_results)} results\n")
    except Exception as e:
        print(f"  ERROR: {e}\n")

    if args.sql_only:
        return

    # Test 3: Qdrant hybrid search (auto-retrieve)
    print("--- Qdrant hybrid search (auto-retrieve) ---")
    try:
        from api.services.lyra_tools import _hybrid_search

        for collection in ["news", "sites", "transcripts"]:
            results, tokens = _hybrid_search(query, collection=collection, limit=3)
            print(f"  {collection}: {len(results)} results ({tokens} embed tokens)")
            for r in results[:3]:
                name = r.get("headline") or r.get("name") or r.get("video_title") or "?"
                score = r.get("relevance", "?")
                print(f"    - {name} (relevance: {score})")
        print()
    except Exception as e:
        print(f"  ERROR: {e}\n")

    # Test 4: Full auto-retrieve pipeline
    print("--- Full auto-retrieve pipeline ---")
    try:
        from api.services.lyra_agent import _auto_retrieve

        context_str, sites, news, avg_rel, tokens = _auto_retrieve([query], "global")
        print(f"  Sites: {len(sites)}, News: {len(news)}, Avg relevance: {avg_rel}")
        print(f"  Embed tokens: {tokens}")
        if news:
            print("  News items:")
            for n in news:
                print(f"    - {n.get('headline', '?')} ({n.get('channel', '?')})")
        if context_str:
            print(f"\n  Context for LLM ({len(context_str)} chars):")
            # Show first 500 chars of what the LLM sees
            print(f"  {context_str[:500]}...")
        print()
    except Exception as e:
        print(f"  ERROR: {e}\n")


if __name__ == "__main__":
    main()
