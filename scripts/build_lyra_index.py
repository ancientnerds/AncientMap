#!/usr/bin/env python3
"""
Build Lyra Vector Index — Qdrant collections for hybrid semantic search.

Creates five collections with named vectors:
  - sites: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - news: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - transcripts: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - articles: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - empires: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)

Queries use voyage-4 for dense (shared embedding space, cheaper) + Qdrant/bm25 for sparse.
RRF fusion merges results, then Voyage rerank-2.5-lite scores the top-K.

Incremental: only indexes items not already in Qdrant.

Usage:
  python scripts/build_lyra_index.py
  python scripts/build_lyra_index.py --collection sites
  python scripts/build_lyra_index.py --collection news
  python scripts/build_lyra_index.py --collection transcripts
  python scripts/build_lyra_index.py --collection articles
  python scripts/build_lyra_index.py --collection empires
  python scripts/build_lyra_index.py --rebuild  # wipe and rebuild
  python scripts/build_lyra_index.py --backend local  # Ollama 768-dim, *_local collections
  python scripts/build_lyra_index.py --backend voyage  # Voyage 1024-dim (default)
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)
from sqlalchemy import text

from api.services.lyra_embeddings import get_embeddings, get_sparse_model
from pipeline.database import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
BATCH_SIZE = 100

# Vector sizes per backend (set by --backend flag, not env var)
VECTOR_SIZES = {"voyage": 1024, "local": 768}


def get_qdrant() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection(client: QdrantClient, name: str, vector_size: int):
    """Create collection with named dense + BM25 sparse vectors if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if name not in collections:
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
        logger.info(f"Created collection '{name}' (dense={vector_size}, sparse=bm25)")
    else:
        logger.info(f"Collection '{name}' already exists")


def create_payload_indexes(client: QdrantClient, collection: str, fields: list[str]):
    """Create keyword payload indexes for metadata filtering."""
    from qdrant_client.models import PayloadSchemaType

    for field in fields:
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    logger.info(f"Created payload indexes on '{collection}': {fields}")


def _content_hash(text: str) -> str:
    """Return first 16 hex chars of SHA-256 digest for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_existing_hashes(client: QdrantClient, collection: str) -> dict[str, str]:
    """Get {point_id: content_hash} for all points in the collection."""
    existing: dict[str, str] = {}
    offset = None
    while True:
        result = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=["content_hash"],
            with_vectors=False,
        )
        points, next_offset = result
        for p in points:
            pid = str(p.id)
            existing[pid] = (p.payload or {}).get("content_hash", "")
        if next_offset is None:
            break
        offset = next_offset
    return existing


def index_sites(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False, *, vector_size: int = 1024, suffix: str = ""):
    """Index archaeological sites into Qdrant with dense + BM25 vectors."""
    collection = f"sites{suffix}"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["country", "period_name", "site_type"])

    existing_hashes = {} if rebuild else get_existing_hashes(client, collection)
    logger.info(f"Sites collection has {len(existing_hashes)} existing points")

    # Join with alternate names, raw_data for descriptions, and content links
    sql = """
        SELECT us.id::text, us.name, us.site_type, us.period_name, us.period_start,
               us.country, us.description, us.lat, us.lon, us.raw_data, us.thumbnail_url,
               array_agg(DISTINCT usn.name) FILTER (WHERE usn.name IS NOT NULL) AS alt_names,
               array_agg(DISTINCT scl.title) FILTER (WHERE scl.title IS NOT NULL) AS content_titles
        FROM unified_sites us
        LEFT JOIN unified_site_names usn ON usn.site_id = us.id
        LEFT JOIN site_content_links scl ON scl.site_id = us.id
        WHERE us.description IS NOT NULL AND LENGTH(us.description) > 20
        GROUP BY us.id
        ORDER BY us.id
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} sites in database")

    # Build hash input per site and filter to new/changed
    def _site_hash_input(r) -> str:
        return f"{r.name}|{r.site_type or ''}|{r.period_name or ''}|{r.country or ''}|{(r.description or '')[:500]}"

    to_index = []
    for r in rows:
        h = _content_hash(_site_hash_input(r))
        if r.id in existing_hashes and existing_hashes[r.id] == h:
            continue
        to_index.append((r, h))

    logger.info(f"Sites to index (new + changed): {len(to_index)}")

    if not to_index:
        logger.info("Nothing to index for sites")
        return

    # Batch index
    total_indexed = 0
    for i in range(0, len(to_index), BATCH_SIZE):
        batch = to_index[i : i + BATCH_SIZE]

        # Build text for embedding
        texts = []
        for r, _h in batch:
            parts = [r.name]
            if r.alt_names:
                alt_str = ", ".join(r.alt_names[:10])
                parts.append(f"Also known as: {alt_str}")
            if r.site_type:
                parts.append(f"Type: {r.site_type}")
            if r.period_name:
                period_str = r.period_name
                if r.period_start:
                    period_str += f" ({r.period_start} BCE)" if r.period_start < 0 else f" ({r.period_start} CE)"
                parts.append(f"Period: {period_str}")
            if r.country:
                parts.append(f"Country: {r.country}")
            if r.description:
                parts.append(r.description[:500])
            elif r.raw_data:
                desc = r.raw_data.get("description") or r.raw_data.get("summary", "") if isinstance(r.raw_data, dict) else ""
                if desc:
                    parts.append(desc[:500])
            if r.content_titles:
                parts.append(f"Related: {', '.join(r.content_titles[:5])}")
            texts.append(" | ".join(parts))

        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for (r, h), dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                PointStruct(
                    id=r.id,
                    vector={
                        "dense": dense_vec,
                        "bm25": SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "name": r.name,
                        "site_type": r.site_type,
                        "period_name": r.period_name,
                        "period_start": r.period_start,
                        "country": r.country,
                        "description": (r.description or "")[:500],
                        "lat": float(r.lat) if r.lat else None,
                        "lon": float(r.lon) if r.lon else None,
                        "thumbnail_url": r.thumbnail_url,
                        "alt_names": (r.alt_names or [])[:5],
                        "content_hash": h,
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(to_index)} sites")

    logger.info(f"Done indexing {total_indexed} sites")


def index_news(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False, *, vector_size: int = 1024, suffix: str = ""):
    """Index news items into Qdrant with dense + BM25 vectors."""
    collection = f"news{suffix}"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["channel", "category"])

    existing_hashes = {} if rebuild else get_existing_hashes(client, collection)
    logger.info(f"News collection has {len(existing_hashes)} existing points")

    sql = """
        SELECT ni.id, ni.headline, ni.summary, ni.significance, ni.news_category,
               ni.site_name_extracted, ni.facts,
               ni.transcript_segment, ni.timestamp_seconds,
               nv.id AS video_id, nv.title AS video_title,
               nc.name AS channel_name,
               ni.created_at::text AS created_at
        FROM news_items ni
        JOIN news_videos nv ON ni.video_id = nv.id
        JOIN news_channels nc ON nv.channel_id = nc.id
        ORDER BY ni.id
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} news items in database")

    to_index = []
    for r in rows:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"news-{r.id}"))
        h = _content_hash(f"{r.headline}|{r.summary or ''}")
        if point_id in existing_hashes and existing_hashes[point_id] == h:
            continue
        to_index.append((r, point_id, h))

    logger.info(f"News items to index (new + changed): {len(to_index)}")

    if not to_index:
        logger.info("Nothing to index for news")
        return

    total_indexed = 0
    for i in range(0, len(to_index), BATCH_SIZE):
        batch = to_index[i : i + BATCH_SIZE]

        texts = []
        for r, _pid, _h in batch:
            parts = [r.headline]
            if r.summary:
                parts.append(r.summary[:500])
            if r.facts and isinstance(r.facts, list):
                facts_str = "; ".join(str(f) for f in r.facts[:8])
                parts.append(f"Facts: {facts_str}")
            if r.site_name_extracted:
                parts.append(f"Site: {r.site_name_extracted}")
            if r.channel_name:
                parts.append(f"Channel: {r.channel_name}")
            texts.append(" | ".join(parts))

        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for (r, point_id, h), dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec,
                        "bm25": SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "id": r.id,
                        "headline": r.headline,
                        "summary": (r.summary or "")[:500],
                        "significance": r.significance,
                        "category": r.news_category,
                        "channel": r.channel_name,
                        "video_id": r.video_id,
                        "site_mentioned": r.site_name_extracted,
                        "date": r.created_at,
                        "facts": (r.facts or [])[:8],
                        "transcript_segment": (r.transcript_segment or "")[:300],
                        "timestamp_seconds": r.timestamp_seconds,
                        "content_hash": h,
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(to_index)} news items")

    logger.info(f"Done indexing {total_indexed} news items")


def _parse_ts(ts: str) -> int | None:
    """Parse '[MM:SS]' or '[HH:MM:SS]' to seconds."""
    m = re.match(r"\[?(\d+):(\d{2}):(\d{2})\]?", ts)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"\[?(\d+):(\d{2})\]?", ts)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _chunk_transcript(transcript_text: str, chunk_size: int = 2000, overlap: int = 500) -> list[dict]:
    """Split timestamped transcript into overlapping chunks.

    Each chunk is a dict with keys: text, start_seconds, end_seconds, chunk_index.
    Splits on line boundaries to preserve [MM:SS] timestamps.
    """
    lines = transcript_text.strip().split("\n")
    if not lines:
        return []

    ts_pattern = re.compile(r"\[(\d+:\d{2}(?::\d{2})?)\]")

    # Build list of (line_text, seconds_or_None)
    parsed_lines: list[tuple[str, int | None]] = []
    for line in lines:
        m = ts_pattern.match(line)
        secs = _parse_ts(m.group(1)) if m else None
        parsed_lines.append((line, secs))

    chunks = []
    chunk_idx = 0
    start_line = 0

    while start_line < len(parsed_lines):
        # Accumulate lines until we hit chunk_size chars
        current_text = ""
        end_line = start_line
        while end_line < len(parsed_lines):
            candidate = current_text + parsed_lines[end_line][0] + "\n"
            if len(candidate) > chunk_size and end_line > start_line:
                break
            current_text = candidate
            end_line += 1

        if not current_text.strip():
            start_line = end_line
            continue

        # Extract start/end seconds from the lines in this chunk
        start_secs = None
        end_secs = None
        for i in range(start_line, end_line):
            s = parsed_lines[i][1]
            if s is not None:
                if start_secs is None:
                    start_secs = s
                end_secs = s

        chunks.append({
            "text": current_text.strip(),
            "start_seconds": start_secs or 0,
            "end_seconds": end_secs or 0,
            "chunk_index": chunk_idx,
        })
        chunk_idx += 1

        # Advance start_line, stepping back by overlap chars for overlap
        if end_line >= len(parsed_lines):
            break
        # Find the line where the overlap region starts
        overlap_text = ""
        overlap_start = end_line
        for j in range(end_line - 1, start_line - 1, -1):
            overlap_text = parsed_lines[j][0] + "\n" + overlap_text
            if len(overlap_text) >= overlap:
                overlap_start = j
                break
        start_line = overlap_start if overlap_start > start_line else end_line

    return chunks


def index_transcripts(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False, *, vector_size: int = 1024, suffix: str = ""):
    """Index video transcript chunks into Qdrant for semantic search."""
    collection = f"transcripts{suffix}"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["channel", "video_id"])

    existing_hashes = {} if rebuild else get_existing_hashes(client, collection)
    logger.info(f"Transcripts collection has {len(existing_hashes)} existing points")

    sql = """
        SELECT nv.id AS video_id, nv.title AS video_title,
               nv.transcript_text, nv.published_at::text AS published_at,
               nc.name AS channel_name
        FROM news_videos nv
        JOIN news_channels nc ON nv.channel_id = nc.id
        WHERE nv.transcript_text IS NOT NULL
        ORDER BY nv.published_at DESC
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} videos with transcripts")

    # Per-video hash from first 2000 chars of transcript (detects re-summarization)
    video_hashes: dict[str, str] = {}
    for r in rows:
        video_hashes[r.video_id] = _content_hash(r.transcript_text[:2000])

    # Chunk all transcripts and filter out unchanged
    all_chunks = []
    for r in rows:
        chunks = _chunk_transcript(r.transcript_text)
        vh = video_hashes[r.video_id]
        for chunk in chunks:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"transcript-{r.video_id}-{chunk['chunk_index']}"))
            if point_id in existing_hashes and existing_hashes[point_id] == vh:
                continue
            chunk["point_id"] = point_id
            chunk["video_id"] = r.video_id
            chunk["video_title"] = r.video_title
            chunk["channel"] = r.channel_name
            chunk["published_at"] = r.published_at
            chunk["content_hash"] = vh
            all_chunks.append(chunk)

    logger.info(f"Transcript chunks to index (new + changed): {len(all_chunks)}")

    if not all_chunks:
        logger.info("Nothing to index for transcripts")
        return

    total_indexed = 0
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]

        texts = []
        for c in batch:
            texts.append(f"{c['video_title']} | {c['channel']} | {c['text']}")

        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for c, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                PointStruct(
                    id=c["point_id"],
                    vector={
                        "dense": dense_vec,
                        "bm25": SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "video_id": c["video_id"],
                        "video_title": c["video_title"],
                        "channel": c["channel"],
                        "start_seconds": c["start_seconds"],
                        "end_seconds": c["end_seconds"],
                        "chunk_index": c["chunk_index"],
                        "published_at": c["published_at"],
                        "text_preview": c["text"][:200],
                        "content_hash": c["content_hash"],
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(all_chunks)} transcript chunks")

    logger.info(f"Done indexing {total_indexed} transcript chunks")


def _chunk_article(content: str, chunk_size: int = 2000, overlap: int = 400) -> list[dict]:
    """Split article markdown into overlapping chunks on paragraph boundaries.

    Each chunk is a dict with keys: text, chunk_index.
    """
    paragraphs = content.split("\n\n")
    if not paragraphs:
        return []

    chunks = []
    chunk_idx = 0
    start_para = 0

    while start_para < len(paragraphs):
        current_text = ""
        end_para = start_para
        while end_para < len(paragraphs):
            candidate = current_text + paragraphs[end_para] + "\n\n"
            if len(candidate) > chunk_size and end_para > start_para:
                break
            current_text = candidate
            end_para += 1

        if not current_text.strip():
            start_para = end_para
            continue

        chunks.append({
            "text": current_text.strip(),
            "chunk_index": chunk_idx,
        })
        chunk_idx += 1

        if end_para >= len(paragraphs):
            break

        # Step back for overlap
        overlap_text = ""
        overlap_start = end_para
        for j in range(end_para - 1, start_para - 1, -1):
            overlap_text = paragraphs[j] + "\n\n" + overlap_text
            if len(overlap_text) >= overlap:
                overlap_start = j
                break
        start_para = overlap_start if overlap_start > start_para else end_para

    return chunks


def index_articles(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False, *, vector_size: int = 1024, suffix: str = ""):
    """Index weekly digest articles into Qdrant for semantic search."""
    collection = f"articles{suffix}"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["article_id"])

    existing_hashes = {} if rebuild else get_existing_hashes(client, collection)
    logger.info(f"Articles collection has {len(existing_hashes)} existing points")

    sql = """
        SELECT id, title, content, summary,
               week_start::text AS week_start, week_end::text AS week_end,
               video_ids, published_at::text AS published_at
        FROM news_articles
        ORDER BY published_at DESC
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} articles in database")

    # Per-article hash from first 2000 chars of content
    article_hashes: dict[int, str] = {}
    for r in rows:
        if r.content:
            article_hashes[r.id] = _content_hash(r.content[:2000])

    # Chunk all articles and filter out unchanged
    all_chunks = []
    for r in rows:
        if not r.content:
            continue
        ah = article_hashes[r.id]
        chunks = _chunk_article(r.content)
        for chunk in chunks:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"article-{r.id}-{chunk['chunk_index']}"))
            if point_id in existing_hashes and existing_hashes[point_id] == ah:
                continue
            chunk["point_id"] = point_id
            chunk["article_id"] = r.id
            chunk["title"] = r.title
            chunk["summary"] = r.summary or ""
            chunk["week_start"] = r.week_start
            chunk["week_end"] = r.week_end
            chunk["published_at"] = r.published_at
            chunk["content_hash"] = ah
            all_chunks.append(chunk)

    logger.info(f"Article chunks to index (new + changed): {len(all_chunks)}")

    if not all_chunks:
        logger.info("Nothing to index for articles")
        return

    total_indexed = 0
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]

        texts = []
        for c in batch:
            texts.append(f"{c['title']} | {c['text']}")

        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for c, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                PointStruct(
                    id=c["point_id"],
                    vector={
                        "dense": dense_vec,
                        "bm25": SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "article_id": c["article_id"],
                        "title": c["title"],
                        "summary": c["summary"][:300],
                        "chunk_index": c["chunk_index"],
                        "week_start": c["week_start"],
                        "week_end": c["week_end"],
                        "published_at": c["published_at"],
                        "text_preview": c["text"][:300],
                        "content_hash": c["content_hash"],
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(all_chunks)} article chunks")

    logger.info(f"Done indexing {total_indexed} article chunks")


def _build_empire_text(polity_id: str, p: dict) -> str:
    """Build rich embedding text from all polity fields for semantic search."""
    parts = [p.get("name", polity_id)]

    alt_names = p.get("alternateNames", [])
    if alt_names:
        parts.append(f"Also known as: {', '.join(alt_names)}")

    start = p.get("startYear", "?")
    end = p.get("endYear", "?")
    parts.append(f"Period: {start} to {end}")

    if p.get("capital"):
        parts.append(f"Capital: {p['capital']}")
    if p.get("territory"):
        parts.append(f"Territory: {p['territory']} sq km")
    if p.get("population"):
        parts.append(f"Population: {p['population']}")
    if p.get("languages"):
        parts.append(f"Languages: {', '.join(p['languages'])}")
    if p.get("religions"):
        parts.append(f"Religions: {', '.join(p['religions'])}")
    if p.get("centralization"):
        parts.append(f"Centralization: {p['centralization']}")

    # Warfare
    warfare = p.get("warfare", {})
    if warfare:
        war_parts = []
        for cat_key in ("fortifications", "projectileWeapons", "handheldWeapons", "armor", "naval", "warfareAnimals"):
            cat = warfare.get(cat_key, {})
            if isinstance(cat, dict):
                items = [k for k, v in cat.items() if v is True]
                if items:
                    label = re.sub(r"([A-Z])", r" \1", cat_key).strip().title()
                    war_parts.append(f"{label}: {', '.join(items)}")
        if warfare.get("metals"):
            war_parts.append(f"Metals: {', '.join(warfare['metals'])}")
        if war_parts:
            parts.append("Warfare: " + "; ".join(war_parts))

    # Economy
    economy = p.get("economy", {})
    if economy:
        econ_parts = []
        if economy.get("scripts"):
            econ_parts.append(f"Scripts: {', '.join(economy['scripts'])}")
        for feat in ("writingSystem", "coinage", "storedWealth", "longDistanceTrade", "roads",
                      "irrigationSystems", "markets", "foodStorageSites", "bridges", "canals"):
            if economy.get(feat) is True:
                label = re.sub(r"([A-Z])", r" \1", feat).strip().lower()
                econ_parts.append(label)
        if economy.get("tradeRoutes"):
            econ_parts.append(f"Trade routes: {', '.join(economy['tradeRoutes'])}")
        if econ_parts:
            parts.append("Economy: " + "; ".join(econ_parts))

    # Crisis events
    crisis = p.get("crisis", {})
    events = crisis.get("crisisEvents", [])
    if events:
        ev_strs = []
        for ev in events[:5]:
            ev_str = ev.get("name", "unknown")
            if ev.get("type"):
                ev_str += f" ({ev['type']})"
            if ev.get("description"):
                ev_str += f": {ev['description'][:100]}"
            ev_strs.append(ev_str)
        parts.append("Crisis events: " + "; ".join(ev_strs))

    # Governance
    gov_parts = []
    if p.get("administrativeLevels"):
        gov_parts.append(f"{p['administrativeLevels']} administrative levels")
    if p.get("militaryLevels"):
        gov_parts.append(f"{p['militaryLevels']} military levels")
    if p.get("religiousLevels"):
        gov_parts.append(f"{p['religiousLevels']} religious levels")
    if gov_parts:
        parts.append("Governance: " + ", ".join(gov_parts))

    return " | ".join(parts)


def index_empires(client: QdrantClient, embeddings, sparse_model, *, rebuild: bool = False, vector_size: int = 1024, suffix: str = ""):
    """Index Seshat polities into the 'empires' collection."""
    collection = f"empires{suffix}"

    # Load polities JSON
    candidates = [
        Path("ancient-nerds-map/src/data/seshat/polities.json"),
        Path("/app/ancient-nerds-map/src/data/seshat/polities.json"),
    ]
    polities_data = None
    for path in candidates:
        if path.exists():
            polities_data = json.loads(path.read_text(encoding="utf-8"))
            break

    if not polities_data:
        logger.warning("polities.json not found — skipping empires indexing")
        return

    polities = polities_data.get("polities", {})
    logger.info(f"Found {len(polities)} polities in Seshat data")

    if rebuild:
        try:
            client.delete_collection(collection)
            logger.info(f"Deleted collection '{collection}' for rebuild")
        except Exception:
            pass

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["polity_id", "region"])
    existing_hashes = get_existing_hashes(client, collection)

    # Build points — hash the full polity JSON string for change detection
    new_points = []
    for polity_id, p in polities.items():
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-{polity_id}"))
        h = _content_hash(json.dumps(p, sort_keys=True))
        if point_id in existing_hashes and existing_hashes[point_id] == h:
            continue
        embed_text = _build_empire_text(polity_id, p)
        new_points.append({
            "point_id": point_id,
            "polity_id": polity_id,
            "embed_text": embed_text,
            "polity": p,
            "content_hash": h,
        })

    logger.info(f"Empires to index (new + changed): {len(new_points)}")
    if not new_points:
        logger.info("Nothing to index for empires")
        return

    # Embed and upsert (46 polities fit in one batch)
    texts = [pt["embed_text"] for pt in new_points]
    dense_vectors = embeddings.embed_documents(texts)
    sparse_vectors = list(sparse_model.embed(texts))

    points = []
    for pt, dense_vec, sparse_vec in zip(new_points, dense_vectors, sparse_vectors):
        p = pt["polity"]
        region = polity_id_to_region(pt["polity_id"])
        points.append(
            PointStruct(
                id=pt["point_id"],
                vector={
                    "dense": dense_vec,
                    "bm25": SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
                payload={
                    "polity_id": pt["polity_id"],
                    "name": p.get("name", pt["polity_id"]),
                    "alternate_names": p.get("alternateNames", []),
                    "start_year": p.get("startYear"),
                    "end_year": p.get("endYear"),
                    "peak_year": p.get("peakYear"),
                    "capital": p.get("capital"),
                    "territory": p.get("territory"),
                    "population": p.get("population"),
                    "languages": p.get("languages", []),
                    "religions": p.get("religions", []),
                    "centralization": p.get("centralization"),
                    "region": region,
                    "seshat_url": p.get("seshatUrl"),
                    "wikipedia_url": p.get("wikipediaUrl"),
                    "text_preview": pt["embed_text"][:500],
                    "content_hash": pt["content_hash"],
                },
            )
        )

    client.upsert(collection_name=collection, points=points)
    logger.info(f"Indexed {len(points)} empires")


def polity_id_to_region(polity_id: str) -> str:
    """Map a polity ID prefix to a readable region name."""
    prefix = polity_id.split("_")[0] if "_" in polity_id else polity_id
    region_map = {
        "eg": "Egypt", "iq": "Mesopotamia", "it": "Italy/Rome", "gr": "Greece",
        "ir": "Persia/Iran", "cn": "China", "in": "India", "tr": "Anatolia/Turkey",
        "mx": "Mesoamerica", "pe": "South America", "gb": "Britain",
        "fr": "France/Gaul", "et": "East Africa", "sd": "Sudan/Nubia",
        "kh": "Southeast Asia", "mn": "Mongolia", "jp": "Japan", "kr": "Korea",
    }
    return region_map.get(prefix, "Other")


def main():
    parser = argparse.ArgumentParser(description="Build Lyra vector index")
    parser.add_argument("--collection", choices=["sites", "news", "transcripts", "articles", "empires"], help="Only index this collection")
    parser.add_argument("--rebuild", action="store_true", help="Wipe and rebuild from scratch")
    parser.add_argument("--backend", choices=["voyage", "local"], default="voyage", help="Embedding backend: voyage (1024-dim) or local (Ollama, 768-dim)")
    args = parser.parse_args()

    backend = args.backend
    vector_size = VECTOR_SIZES[backend]
    suffix = "_local" if backend == "local" else ""

    logger.info(f"Backend: {backend} | vector_size: {vector_size} | collection suffix: '{suffix}'")

    client = get_qdrant()
    embeddings = get_embeddings(usage="index", backend=backend)
    sparse_model = get_sparse_model()

    kwargs = {"rebuild": args.rebuild, "vector_size": vector_size, "suffix": suffix}

    if args.collection is None or args.collection == "sites":
        index_sites(client, embeddings, sparse_model, **kwargs)

    if args.collection is None or args.collection == "news":
        index_news(client, embeddings, sparse_model, **kwargs)

    if args.collection is None or args.collection == "transcripts":
        index_transcripts(client, embeddings, sparse_model, **kwargs)

    if args.collection is None or args.collection == "articles":
        index_articles(client, embeddings, sparse_model, **kwargs)

    if args.collection is None or args.collection == "empires":
        index_empires(client, embeddings, sparse_model, **kwargs)

    logger.info(f"All done! (backend={backend})")


if __name__ == "__main__":
    main()
