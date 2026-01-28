#!/usr/bin/env python3
"""
Build AI Vector Index for Ancient Nerds Map.

Creates Qdrant vector collections - one per source - from the unified_sites table.
Each source gets its own collection to preserve data quality hierarchy.

Usage:
    python scripts/build_ai_index.py                      # Build all sources
    python scripts/build_ai_index.py --source ancient_nerds  # Build single source
    python scripts/build_ai_index.py --rebuild            # Drop and rebuild all
    python scripts/build_ai_index.py --list               # List all sources

Source Quality Tiers:
    GOLD:   ancient_nerds (797 char avg desc), megalithic_portal, unesco
    SILVER: pleiades, topostext, wikidata
    BRONZE: osm_historic (5.9% have desc), ireland_nms (no desc)
    FEATURE: volcanic_holvol, earth_impacts
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Optional, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Qdrant imports
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

VECTOR_SIZE = 384  # all-MiniLM-L6-v2
BATCH_SIZE = 500   # Reduced for stability


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client."""
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def get_embedder():
    """Load sentence transformer model."""
    from sentence_transformers import SentenceTransformer
    model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    logger.info(f"Loading embedding model: {model_name}")
    return SentenceTransformer(model_name)


def build_text_for_embedding(site: dict) -> str:
    """
    Build text string for embedding.

    Format: "{name} | {type} | {period} | {country} | {description[:500]}"
    """
    parts = []

    if site.get("name"):
        parts.append(site["name"])

    if site.get("site_type"):
        parts.append(site["site_type"])

    if site.get("period_name"):
        parts.append(site["period_name"])

    if site.get("country"):
        parts.append(site["country"])

    if site.get("description"):
        # Truncate description to 500 chars for embedding
        parts.append(site["description"][:500])

    return " | ".join(parts) if parts else site.get("name", "Unknown")


def build_payload(site: dict) -> dict:
    """Build Qdrant payload for a site."""
    payload = {
        "site_id": str(site["id"]),
        "name": site.get("name") or "Unknown",
        "site_type": site.get("site_type"),
        "period_start": site.get("period_start"),
        "period_end": site.get("period_end"),
        "period_name": site.get("period_name"),
        "country": site.get("country"),
    }

    # Store location as GeoPoint format for geo filtering
    if site.get("lat") is not None and site.get("lon") is not None:
        payload["location"] = {
            "lat": float(site["lat"]),
            "lon": float(site["lon"])
        }

    # Store truncated description for context building
    if site.get("description"):
        payload["description"] = site["description"][:1000]

    return payload


def get_all_sources() -> List[str]:
    """Get list of all source IDs from database."""
    from pipeline.database import get_session
    from sqlalchemy import text

    with get_session() as session:
        result = session.execute(text("SELECT DISTINCT source_id FROM unified_sites ORDER BY source_id"))
        return [row.source_id for row in result]


def get_source_count(source_id: str) -> int:
    """Get count of sites for a source."""
    from pipeline.database import get_session
    from sqlalchemy import text

    with get_session() as session:
        result = session.execute(
            text("SELECT COUNT(*) FROM unified_sites WHERE source_id = :source_id"),
            {"source_id": source_id}
        )
        return result.scalar()


def build_collection(
    client: QdrantClient,
    embedder,
    source_id: str,
    rebuild: bool = False,
    batch_size: int = BATCH_SIZE
):
    """
    Build a single collection for a source.

    Args:
        client: Qdrant client
        embedder: Sentence transformer model
        source_id: Source ID to build collection for
        rebuild: Whether to drop and rebuild
        batch_size: Number of sites per batch
    """
    from pipeline.database import get_session
    from sqlalchemy import text

    collection_name = source_id

    # Check if collection exists
    exists = client.collection_exists(collection_name)

    if exists and not rebuild:
        info = client.get_collection(collection_name)
        logger.info(f"Collection '{collection_name}' already exists with {info.points_count} points. Use --rebuild to recreate.")
        return

    # Drop if rebuilding
    if exists and rebuild:
        logger.info(f"Dropping existing collection '{collection_name}'...")
        client.delete_collection(collection_name)

    # Create collection
    logger.info(f"Creating collection '{collection_name}'...")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    )

    # Get total count
    total = get_source_count(source_id)
    logger.info(f"Processing {total:,} sites for '{source_id}'...")

    if total == 0:
        logger.warning(f"No sites found for source '{source_id}'")
        return

    # Process in batches
    start_time = datetime.now()
    processed = 0
    offset = 0

    with get_session() as session:
        while offset < total:
            # Fetch batch
            result = session.execute(text("""
                SELECT
                    id::text as id,
                    name,
                    site_type,
                    period_start,
                    period_end,
                    period_name,
                    country,
                    description,
                    lat,
                    lon
                FROM unified_sites
                WHERE source_id = :source_id
                ORDER BY id
                LIMIT :limit OFFSET :offset
            """), {"source_id": source_id, "limit": batch_size, "offset": offset})

            rows = result.fetchall()
            if not rows:
                break

            # Convert to dicts
            sites = []
            for row in rows:
                sites.append({
                    "id": row.id,
                    "name": row.name,
                    "site_type": row.site_type,
                    "period_start": row.period_start,
                    "period_end": row.period_end,
                    "period_name": row.period_name,
                    "country": row.country,
                    "description": row.description,
                    "lat": row.lat,
                    "lon": row.lon,
                })

            # Build embeddings
            texts = [build_text_for_embedding(s) for s in sites]
            embeddings = embedder.encode(texts, convert_to_numpy=True)

            # Build points
            points = []
            for i, site in enumerate(sites):
                # Use hash of site ID as point ID (Qdrant needs int or UUID)
                point_id = abs(hash(site["id"])) % (2**63)

                points.append(PointStruct(
                    id=point_id,
                    vector=embeddings[i].tolist(),
                    payload=build_payload(site)
                ))

            # Upsert batch
            try:
                client.upsert(collection_name=collection_name, points=points)
            except Exception as e:
                logger.error(f"Error upserting batch at offset {offset}: {e}")
                # Continue to next batch
                offset += batch_size
                continue

            processed += len(sites)
            offset += batch_size

            # Progress update
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / rate if rate > 0 else 0
            pct = 100 * processed / total

            logger.info(
                f"  {source_id}: {processed:,}/{total:,} ({pct:.1f}%) - "
                f"{rate:.1f}/sec - ETA: {eta:.0f}s"
            )

    # Final stats
    elapsed = (datetime.now() - start_time).total_seconds()
    info = client.get_collection(collection_name)

    logger.info(f"  {source_id}: Complete! {info.points_count:,} points in {elapsed:.1f}s")


def list_sources():
    """List all sources with counts."""
    from pipeline.database import get_session
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("Available Sources:")
    logger.info("=" * 60)

    with get_session() as session:
        result = session.execute(text("""
            SELECT source_id, COUNT(*) as count,
                   AVG(LENGTH(description)) as avg_desc_len
            FROM unified_sites
            GROUP BY source_id
            ORDER BY count DESC
        """))

        for row in result:
            avg_len = int(row.avg_desc_len) if row.avg_desc_len else 0
            logger.info(f"  {row.source_id:30} {row.count:>10,} sites  (avg desc: {avg_len} chars)")


def main():
    parser = argparse.ArgumentParser(
        description="Build Qdrant vector index for Ancient Nerds Map"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Build single source only (e.g., 'ancient_nerds')"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Sites per batch (default: {BATCH_SIZE})"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop and rebuild collections"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_sources",
        help="List all available sources"
    )

    args = parser.parse_args()

    # List sources
    if args.list_sources:
        list_sources()
        return

    logger.info("=" * 60)
    logger.info("Ancient Nerds Map - Qdrant Vector Index Builder")
    logger.info("=" * 60)

    # Initialize
    client = get_qdrant_client()
    embedder = get_embedder()

    # Get sources to build
    if args.source:
        sources = [args.source]
    else:
        sources = get_all_sources()

    logger.info(f"Building {len(sources)} collection(s)...")

    # Build each collection
    total_start = datetime.now()

    for source_id in sources:
        try:
            build_collection(
                client=client,
                embedder=embedder,
                source_id=source_id,
                rebuild=args.rebuild,
                batch_size=args.batch_size
            )
        except KeyboardInterrupt:
            logger.info("\nInterrupted by user")
            break
        except Exception as e:
            logger.error(f"Error building '{source_id}': {e}")
            continue

    # Summary
    total_elapsed = (datetime.now() - total_start).total_seconds()
    collections = client.get_collections().collections

    logger.info("=" * 60)
    logger.info("Build Complete!")
    logger.info(f"Total time: {total_elapsed/60:.1f} minutes")
    logger.info(f"Collections: {len(collections)}")

    total_points = 0
    for coll in collections:
        info = client.get_collection(coll.name)
        total_points += info.points_count
        logger.info(f"  {coll.name}: {info.points_count:,} points")

    logger.info(f"Total points: {total_points:,}")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)
