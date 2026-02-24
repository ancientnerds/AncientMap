#!/usr/bin/env python3
"""
Build Lyra Vector Index — Qdrant collections for hybrid semantic search.

Creates three collections with named vectors:
  - sites: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - news: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - transcripts: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)

Queries use voyage-4 for dense (shared embedding space, cheaper) + Qdrant/bm25 for sparse.
RRF fusion merges results, then Voyage rerank-2.5-lite scores the top-K.

Incremental: only indexes items not already in Qdrant.

Usage:
  python scripts/build_lyra_index.py
  python scripts/build_lyra_index.py --collection sites
  python scripts/build_lyra_index.py --collection news
  python scripts/build_lyra_index.py --collection transcripts
  python scripts/build_lyra_index.py --rebuild  # wipe and rebuild
"""

import argparse
import logging
import os
import re
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    NamedSparseVector,
    NamedVector,
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

# Fixed vector size for voyage-4-large / voyage-4 shared embedding space
VECTOR_SIZE = 1024


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


def get_existing_ids(client: QdrantClient, collection: str) -> set[str]:
    """Get all point IDs already in the collection."""
    existing = set()
    offset = None
    while True:
        result = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        points, next_offset = result
        for p in points:
            existing.add(str(p.id))
        if next_offset is None:
            break
        offset = next_offset
    return existing


def index_sites(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False):
    """Index archaeological sites into Qdrant with dense + BM25 vectors."""
    collection = "sites"

    if rebuild:
        client.delete_collection(collection)

    ensure_collection(client, collection, VECTOR_SIZE)
    create_payload_indexes(client, collection, ["country", "period_name", "site_type"])

    existing_ids = set() if rebuild else get_existing_ids(client, collection)
    logger.info(f"Sites collection has {len(existing_ids)} existing points")

    # Join with alternate names, raw_data for descriptions, and content links
    sql = """
        SELECT us.id::text, us.name, us.site_type, us.period_name, us.period_start,
               us.country, us.description, us.lat, us.lon, us.raw_data, us.thumbnail_url,
               array_agg(DISTINCT usn.name) FILTER (WHERE usn.name IS NOT NULL) AS alt_names,
               array_agg(DISTINCT scl.title) FILTER (WHERE scl.title IS NOT NULL) AS content_titles
        FROM unified_sites us
        LEFT JOIN unified_site_names usn ON usn.site_id = us.id
        LEFT JOIN site_content_links scl ON scl.site_id = us.id
        WHERE us.source_id = 'ancient_nerds'
        GROUP BY us.id
        ORDER BY us.id
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} sites in database")

    # Filter out already indexed
    to_index = [r for r in rows if r.id not in existing_ids]
    logger.info(f"New sites to index: {len(to_index)}")

    if not to_index:
        logger.info("Nothing to index for sites")
        return

    # Batch index
    total_indexed = 0
    for i in range(0, len(to_index), BATCH_SIZE):
        batch = to_index[i : i + BATCH_SIZE]

        # Build text for embedding
        texts = []
        for r in batch:
            parts = [r.name]
            # Include alternate names for richer embeddings
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
                # Fall back to raw_data description when no dedicated description
                desc = r.raw_data.get("description") or r.raw_data.get("summary", "") if isinstance(r.raw_data, dict) else ""
                if desc:
                    parts.append(desc[:500])
            # Include content link titles for additional context
            if r.content_titles:
                parts.append(f"Related: {', '.join(r.content_titles[:5])}")
            texts.append(" | ".join(parts))

        # Dense vectors (voyage-4-large)
        dense_vectors = embeddings.embed_documents(texts)
        # Sparse vectors (BM25)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for r, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
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
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(to_index)} sites")

    logger.info(f"Done indexing {total_indexed} sites")


def index_news(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False):
    """Index news items into Qdrant with dense + BM25 vectors."""
    collection = "news"

    if rebuild:
        client.delete_collection(collection)

    ensure_collection(client, collection, VECTOR_SIZE)
    create_payload_indexes(client, collection, ["channel", "category"])

    existing_ids = set() if rebuild else get_existing_ids(client, collection)
    logger.info(f"News collection has {len(existing_ids)} existing points")

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

    to_index = [r for r in rows if str(r.id) not in existing_ids]
    logger.info(f"New news items to index: {len(to_index)}")

    if not to_index:
        logger.info("Nothing to index for news")
        return

    total_indexed = 0
    for i in range(0, len(to_index), BATCH_SIZE):
        batch = to_index[i : i + BATCH_SIZE]

        texts = []
        for r in batch:
            parts = [r.headline]
            if r.summary:
                parts.append(r.summary[:500])
            # Include extracted facts for richer embeddings
            if r.facts and isinstance(r.facts, list):
                facts_str = "; ".join(str(f) for f in r.facts[:8])
                parts.append(f"Facts: {facts_str}")
            if r.site_name_extracted:
                parts.append(f"Site: {r.site_name_extracted}")
            if r.channel_name:
                parts.append(f"Channel: {r.channel_name}")
            texts.append(" | ".join(parts))

        # Dense vectors (voyage-4-large)
        dense_vectors = embeddings.embed_documents(texts)
        # Sparse vectors (BM25)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for r, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            # Use a UUID derived from the integer ID for Qdrant
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"news-{r.id}"))
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


def index_transcripts(client: QdrantClient, embeddings, sparse_model, rebuild: bool = False):
    """Index video transcript chunks into Qdrant for semantic search."""
    collection = "transcripts"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    ensure_collection(client, collection, VECTOR_SIZE)
    create_payload_indexes(client, collection, ["channel", "video_id"])

    existing_ids = set() if rebuild else get_existing_ids(client, collection)
    logger.info(f"Transcripts collection has {len(existing_ids)} existing points")

    sql = """
        SELECT nv.id AS video_id, nv.title AS video_title,
               nv.transcript_text, nv.published_at::text AS published_at,
               nc.name AS channel_name
        FROM news_videos nv
        JOIN news_channels nc ON nv.channel_id = nc.id
        WHERE nv.transcript_text IS NOT NULL
          AND nv.status IN ('transcribed', 'summarized')
        ORDER BY nv.published_at DESC
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} videos with transcripts")

    # Chunk all transcripts and filter out already-indexed
    all_chunks = []
    for r in rows:
        chunks = _chunk_transcript(r.transcript_text)
        for chunk in chunks:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"transcript-{r.video_id}-{chunk['chunk_index']}"))
            if point_id in existing_ids:
                continue
            chunk["point_id"] = point_id
            chunk["video_id"] = r.video_id
            chunk["video_title"] = r.video_title
            chunk["channel"] = r.channel_name
            chunk["published_at"] = r.published_at
            all_chunks.append(chunk)

    logger.info(f"New transcript chunks to index: {len(all_chunks)}")

    if not all_chunks:
        logger.info("Nothing to index for transcripts")
        return

    total_indexed = 0
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]

        # Build embedding text: video title + channel + chunk text
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
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(all_chunks)} transcript chunks")

    logger.info(f"Done indexing {total_indexed} transcript chunks")


def main():
    parser = argparse.ArgumentParser(description="Build Lyra vector index")
    parser.add_argument("--collection", choices=["sites", "news", "transcripts"], help="Only index this collection")
    parser.add_argument("--rebuild", action="store_true", help="Wipe and rebuild from scratch")
    args = parser.parse_args()

    client = get_qdrant()
    # Use voyage-4-large for indexing (best quality)
    embeddings = get_embeddings(usage="index")
    # BM25 sparse model for hybrid search
    sparse_model = get_sparse_model()

    if args.collection is None or args.collection == "sites":
        index_sites(client, embeddings, sparse_model, rebuild=args.rebuild)

    if args.collection is None or args.collection == "news":
        index_news(client, embeddings, sparse_model, rebuild=args.rebuild)

    if args.collection is None or args.collection == "transcripts":
        index_transcripts(client, embeddings, sparse_model, rebuild=args.rebuild)

    logger.info("All done!")


if __name__ == "__main__":
    main()
