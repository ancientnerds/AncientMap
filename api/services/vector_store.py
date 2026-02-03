"""
Vector Store Service using Qdrant.

Provides semantic search capabilities for archaeological sites
using sentence embeddings, metadata filtering, and multi-collection support.

Each source has its own collection to preserve data quality hierarchy:
- GOLD: ancient_nerds (797 char avg desc), megalithic_portal, unesco
- SILVER: pleiades, topostext, wikidata
- BRONZE: osm_historic (5.9% have desc), ireland_nms (no desc)
- FEATURE: volcanic_holvol, earth_impacts (for cross-reference queries)
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from pipeline.config import get_ai_thread_limit

# Limit CPU threads for ML libraries BEFORE importing them
_thread_limit = str(get_ai_thread_limit())
os.environ["OMP_NUM_THREADS"] = _thread_limit
os.environ["MKL_NUM_THREADS"] = _thread_limit
os.environ["OPENBLAS_NUM_THREADS"] = _thread_limit
os.environ["VECLIB_MAXIMUM_THREADS"] = _thread_limit
os.environ["NUMEXPR_NUM_THREADS"] = _thread_limit

logger = logging.getLogger(__name__)

# Lazy imports
_qdrant_client = None
_sentence_transformer = None


def _get_qdrant():
    """Lazy import Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            _qdrant_client = QdrantClient(host=host, port=port)
            logger.info(f"Qdrant client connected to {host}:{port}")
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Run: pip install qdrant-client"
            ) from None
    return _qdrant_client


def _get_embedder():
    """Lazy import and load sentence transformer model."""
    global _sentence_transformer
    if _sentence_transformer is None:
        try:
            # Limit torch threads
            import torch
            thread_limit = get_ai_thread_limit()
            torch.set_num_threads(thread_limit)
            torch.set_num_interop_threads(thread_limit)

            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            logger.info(f"Loading embedding model: {model_name} (threads: {thread_limit})")
            _sentence_transformer = SentenceTransformer(model_name, device="cpu")
            logger.info("Embedding model loaded successfully")
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            ) from None
    return _sentence_transformer


@dataclass
class SearchResult:
    """A single search result from vector store."""
    site_id: str
    score: float
    source: str
    name: str
    site_type: str | None
    period_name: str | None
    country: str | None
    description: str | None
    lat: float | None
    lon: float | None
    near_feature: str | None = None
    feature_type: str | None = None


class VectorStore:
    """
    Qdrant-based vector store with multi-collection support.

    Each source has its own collection, enabling:
    - Source-specific searches: search(sources=["ancient_nerds"])
    - Cross-source searches: search(sources=["all"])
    - Quality-weighted ranking: GOLD sources ranked higher
    - Feature reference searches: "sites near volcanos"
    """

    VECTOR_SIZE = 384  # all-MiniLM-L6-v2

    # Source quality tiers (for ranking)
    QUALITY_TIERS = {
        # GOLD - best descriptions
        "ancient_nerds": 1.0,
        "megalithic_portal": 0.95,
        "unesco": 0.9,
        # SILVER - good descriptions
        "pleiades": 0.7,
        "topostext": 0.7,
        "inscriptions_edh": 0.6,
        "wikidata": 0.6,
        "arachne": 0.55,
        # BRONZE - sparse/no descriptions
        "osm_historic": 0.3,
        "ireland_nms": 0.3,
        "historic_england": 0.3,
        "shipwrecks_oxrep": 0.5,
        "dare": 0.5,
        "dinaa": 0.4,
        "eamena": 0.4,
        "sacred_sites": 0.4,
        "rock_art": 0.4,
        "open_context": 0.4,
        # FEATURE collections (not archaeological sites)
        "volcanic_holvol": 0.5,
        "earth_impacts": 0.5,
    }

    # Feature collections (geographic features, not archaeological sites)
    FEATURE_COLLECTIONS = ["volcanic_holvol", "earth_impacts"]

    # Feature type to collection mapping
    FEATURE_TYPE_MAP = {
        "volcano": "volcanic_holvol",
        "volcanic": "volcanic_holvol",
        "volcanic_eruption": "volcanic_holvol",
        "eruption": "volcanic_holvol",
        "impact_crater": "earth_impacts",
        "impact": "earth_impacts",
        "crater": "earth_impacts",
        "meteorite": "earth_impacts",
        "asteroid": "earth_impacts",
    }

    def __init__(self):
        """Initialize vector store with lazy loading."""
        self._client = None
        self._embedder = None
        self._executor = ThreadPoolExecutor(max_workers=get_ai_thread_limit())

    @property
    def client(self):
        """Lazy initialization of Qdrant client."""
        if self._client is None:
            self._client = _get_qdrant()
        return self._client

    @property
    def embedder(self):
        """Lazy initialization of embedding model."""
        if self._embedder is None:
            self._embedder = _get_embedder()
        return self._embedder

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a text string."""
        return self.embedder.encode(text, convert_to_numpy=True).tolist()

    def get_all_collections(self) -> list[str]:
        """Get list of all available collections."""
        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Error getting collections: {e}")
            return []

    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        try:
            return self.client.collection_exists(name)
        except Exception:
            return False

    def get_collection_count(self, name: str) -> int:
        """Get document count for a collection."""
        try:
            info = self.client.get_collection(name)
            return info.points_count
        except Exception:
            return 0

    def _resolve_sources(self, sources: list[str] | None) -> list[str]:
        """Resolve source list to collection names."""
        all_collections = self.get_all_collections()

        if sources is None or sources == ["all"] or "all" in sources:
            # Return all non-feature collections for general searches
            return [c for c in all_collections if c not in self.FEATURE_COLLECTIONS]

        # Return only requested collections that exist
        return [s for s in sources if s in all_collections]

    def _build_filter(self, filters: dict[str, Any] | None) -> Any | None:
        """Build Qdrant filter from filter dict.

        Accepts both VectorStore format and QueryParser format:
        - site_type or site_type_in
        - period_start/period_end or period_start_gte/period_end_lte/period_start_lte
        - bbox or min_lat/max_lat/min_lon/max_lon
        """
        if not filters:
            return None

        logger.debug(f"Building filter from: {filters}")

        from qdrant_client.models import (
            FieldCondition,
            Filter,
            GeoBoundingBox,
            GeoPoint,
            MatchAny,
            MatchValue,
            Range,
        )

        must_conditions = []

        # Site type filter - support both formats
        # Note: Some site_type values like 'megalith' or 'dolmen' don't exist in DB
        # (actual types are 'monument', 'settlement', etc.). Skip filtering for these.
        ACTUAL_DB_SITE_TYPES = {
            'temple', 'church', 'chapel', 'cathedral', 'basilica', 'sanctuary', 'shrine',
            'tomb', 'burial', 'necropolis', 'cemetery', 'grave', 'mausoleum',
            'fort', 'fortress', 'fortification', 'castle', 'citadel',
            'settlement', 'village', 'town', 'city', 'urban', 'habitation',
            'monument', 'memorial', 'cave', 'villa', 'palace', 'road', 'bridge',
            'aqueduct', 'bath', 'theater', 'theatre', 'amphitheater', 'stadium',
            'mine', 'quarry', 'harbor', 'harbour', 'port', 'lighthouse',
            'monastery', 'abbey', 'mosque', 'synagogue', 'site', 'ruin'
        }

        if filters.get("site_type"):
            if filters["site_type"].lower() in ACTUAL_DB_SITE_TYPES:
                must_conditions.append(
                    FieldCondition(key="site_type", match=MatchValue(value=filters["site_type"]))
                )
        elif filters.get("site_type_in"):
            # Filter to only types that actually exist in DB
            valid_types = [t for t in filters["site_type_in"] if t.lower() in ACTUAL_DB_SITE_TYPES]
            if valid_types:
                must_conditions.append(
                    FieldCondition(key="site_type", match=MatchAny(any=valid_types))
                )
            # If no valid types, skip the filter - semantic search will handle it

        # Period filters - support all formats from QueryParser
        # period_start_gte: sites that started >= this date (newer than X)
        # period_start_lte: sites that started <= this date (older than X)
        # period_end_lte: sites that ended <= this date

        # "Older than X" queries: period_start_lte
        period_start_max = filters.get("period_start_lte")
        if period_start_max is not None:
            # Sites that started before this date (older than X)
            must_conditions.append(
                FieldCondition(key="period_start", range=Range(lte=period_start_max))
            )

        # "Newer than X" queries: period_start_gte
        period_start_min = filters.get("period_start_gte") or filters.get("period_start")
        if period_start_min is not None:
            # Sites that started after this date
            must_conditions.append(
                FieldCondition(key="period_start", range=Range(gte=period_start_min))
            )

        # "Before X" queries: period_end_lte
        period_end_max = filters.get("period_end_lte") or filters.get("period_end")
        if period_end_max is not None:
            # Sites that ended before this date
            must_conditions.append(
                FieldCondition(key="period_end", range=Range(lte=period_end_max))
            )

        # Bounding box filter - support both formats
        bbox = filters.get("bbox")
        if not bbox and filters.get("min_lat") is not None:
            # Convert QueryParser format to bbox format
            bbox = {
                "north": filters["max_lat"],
                "south": filters["min_lat"],
                "east": filters["max_lon"],
                "west": filters["min_lon"]
            }

        if bbox:
            must_conditions.append(
                FieldCondition(
                    key="location",
                    geo_bounding_box=GeoBoundingBox(
                        top_left=GeoPoint(lat=bbox["north"], lon=bbox["west"]),
                        bottom_right=GeoPoint(lat=bbox["south"], lon=bbox["east"])
                    )
                )
            )

        if not must_conditions:
            return None

        logger.debug(f"Built {len(must_conditions)} filter conditions")
        return Filter(must=must_conditions)

    def search(
        self,
        query: str,
        sources: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """
        Search across one or multiple collections.

        Args:
            query: Search query text
            sources: List of source collections to search. None or ["all"] = all sources.
            filters: Optional filter dict with keys:
                - site_type: filter by site type
                - period_start: minimum period (sites active after this year)
                - period_end: maximum period (sites active before this year)
                - bbox: {north, south, east, west} bounding box
            limit: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by quality-weighted relevance
        """
        collections = self._resolve_sources(sources)

        if not collections:
            logger.warning("No collections available for search")
            return self._database_fallback_search(query, filters, limit, sources)

        query_vector = self.embed_text(query)
        query_filter = self._build_filter(filters)

        # Search all collections in parallel
        all_results = []

        def search_collection(coll: str) -> list[dict]:
            try:
                # Use query_points (qdrant-client >= 1.7)
                response = self.client.query_points(
                    collection_name=coll,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                )
                return [(coll, hit) for hit in response.points]
            except Exception as e:
                logger.debug(f"Error searching {coll}: {e}")
                return []

        # Execute searches in parallel
        futures = {self._executor.submit(search_collection, coll): coll for coll in collections}

        for future in as_completed(futures):
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                logger.debug(f"Search future error: {e}")

        if not all_results:
            logger.info("No results from vector search, falling back to database")
            return self._database_fallback_search(query, filters, limit, sources)

        # Convert to SearchResult with quality-weighted scores
        search_results = []
        seen_ids = set()

        for coll, hit in all_results:
            site_id = hit.payload.get("site_id", "")
            if site_id in seen_ids:
                continue
            seen_ids.add(site_id)

            quality_weight = self.QUALITY_TIERS.get(coll, 0.5)
            weighted_score = hit.score * quality_weight

            search_results.append(SearchResult(
                site_id=site_id,
                score=weighted_score,
                source=coll,
                name=hit.payload.get("name", ""),
                site_type=hit.payload.get("site_type"),
                period_name=hit.payload.get("period_name"),
                country=hit.payload.get("country"),
                description=hit.payload.get("description"),
                lat=hit.payload.get("location", {}).get("lat") if hit.payload.get("location") else None,
                lon=hit.payload.get("location", {}).get("lon") if hit.payload.get("location") else None,
            ))

        # Sort by weighted score
        search_results.sort(key=lambda x: x.score, reverse=True)
        return search_results[:limit]

    def search_near_feature(
        self,
        feature_type: str,
        sources: list[str] | None = None,
        radius_km: float = 50,
        limit: int = 50,
    ) -> list[SearchResult]:
        """
        Find sites near geographic features (volcanos, impact craters, etc.).

        Args:
            feature_type: Type of feature ("volcano", "impact_crater", etc.)
            sources: List of site collections to search
            radius_km: Search radius in kilometers
            limit: Maximum results to return

        Returns:
            List of SearchResult objects with near_feature populated
        """
        from qdrant_client.models import FieldCondition, Filter, GeoPoint, GeoRadius

        # Get feature collection
        feature_coll = self.FEATURE_TYPE_MAP.get(feature_type.lower())
        if not feature_coll or not self.collection_exists(feature_coll):
            logger.warning(f"Feature collection not found for type: {feature_type}")
            return []

        # Get all features
        try:
            features, _ = self.client.scroll(
                collection_name=feature_coll,
                limit=100,
                with_payload=True
            )
        except Exception as e:
            logger.error(f"Error getting features: {e}")
            return []

        if not features:
            return []

        # Get site collections to search
        site_collections = self._resolve_sources(sources)
        site_collections = [c for c in site_collections if c not in self.FEATURE_COLLECTIONS]

        if not site_collections:
            return []

        all_results = []
        seen_ids = set()

        # For each feature, find nearby sites
        for feature in features:
            loc = feature.payload.get("location", {})
            if not loc or not loc.get("lat") or not loc.get("lon"):
                continue

            feature_name = feature.payload.get("name", "Unknown feature")

            geo_filter = Filter(must=[
                FieldCondition(
                    key="location",
                    geo_radius=GeoRadius(
                        center=GeoPoint(lat=loc["lat"], lon=loc["lon"]),
                        radius=radius_km * 1000  # Convert to meters
                    )
                )
            ])

            for coll in site_collections:
                try:
                    # Use scroll instead of search since we're filtering by geo only
                    results, _ = self.client.scroll(
                        collection_name=coll,
                        scroll_filter=geo_filter,
                        limit=10,
                        with_payload=True
                    )

                    for hit in results:
                        site_id = hit.payload.get("site_id", "")
                        if site_id in seen_ids:
                            continue
                        seen_ids.add(site_id)

                        quality_weight = self.QUALITY_TIERS.get(coll, 0.5)

                        all_results.append(SearchResult(
                            site_id=site_id,
                            score=quality_weight,
                            source=coll,
                            name=hit.payload.get("name", ""),
                            site_type=hit.payload.get("site_type"),
                            period_name=hit.payload.get("period_name"),
                            country=hit.payload.get("country"),
                            description=hit.payload.get("description"),
                            lat=hit.payload.get("location", {}).get("lat") if hit.payload.get("location") else None,
                            lon=hit.payload.get("location", {}).get("lon") if hit.payload.get("location") else None,
                            near_feature=feature_name,
                            feature_type=feature_type,
                        ))
                except Exception as e:
                    logger.debug(f"Error searching {coll} near feature: {e}")

        # Sort by score
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:limit]

    def _database_fallback_search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        source_ids: list[str] | None = None
    ) -> list[SearchResult]:
        """
        Fallback search directly from PostgreSQL when vector store is empty.
        """
        try:
            from sqlalchemy import text

            from pipeline.database import get_session

            conditions = ["1=1"]
            params = {"limit": limit}

            # Source filter
            if source_ids and source_ids != ["all"]:
                source_placeholders = ", ".join([f":source{i}" for i in range(len(source_ids))])
                conditions.append(f"source_id IN ({source_placeholders})")
                for i, sid in enumerate(source_ids):
                    params[f"source{i}"] = sid

            # Apply filters
            if filters:
                if filters.get("site_type"):
                    conditions.append("LOWER(site_type) LIKE :site_type")
                    params["site_type"] = f"%{filters['site_type'].lower()}%"

                # "older than X" query: period_start_lte
                if filters.get("period_start_lte") is not None:
                    conditions.append("period_start IS NOT NULL AND period_start <= :period_start_lte")
                    params["period_start_lte"] = filters["period_start_lte"]

                # "newer than X" query: period_start_gte
                if filters.get("period_start_gte") is not None or filters.get("period_start") is not None:
                    val = filters.get("period_start_gte") or filters.get("period_start")
                    conditions.append("(period_end IS NULL OR period_end >= :period_start)")
                    params["period_start"] = val

                # "before X" query: period_end_lte
                if filters.get("period_end_lte") is not None or filters.get("period_end") is not None:
                    val = filters.get("period_end_lte") or filters.get("period_end")
                    conditions.append("(period_start IS NULL OR period_start <= :period_end)")
                    params["period_end"] = val

                if filters.get("bbox"):
                    bbox = filters["bbox"]
                    conditions.append("lat BETWEEN :south AND :north")
                    conditions.append("lon BETWEEN :west AND :east")
                    params.update(bbox)

            # Text search
            if query:
                stop_words = {'find', 'show', 'search', 'for', 'the', 'and', 'what', 'does', 'mean', 'is', 'are', 'in', 'at', 'on', 'to', 'of', 'a', 'an'}
                words = [w for w in query.lower().split() if len(w) > 2 and w not in stop_words]
                if words:
                    word_conditions = []
                    for i, word in enumerate(words[:5]):
                        word_conditions.append(f"(LOWER(name) LIKE :word{i} OR LOWER(description) LIKE :word{i})")
                        params[f"word{i}"] = f"%{word}%"
                    if word_conditions:
                        conditions.append(f"({' OR '.join(word_conditions)})")

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT
                    id::text,
                    name,
                    site_type,
                    period_name,
                    country,
                    description,
                    lat,
                    lon,
                    source_id
                FROM unified_sites
                WHERE {where_clause}
                ORDER BY
                    CASE source_id
                        WHEN 'ancient_nerds' THEN 1
                        WHEN 'megalithic_portal' THEN 2
                        WHEN 'unesco' THEN 3
                        ELSE 10
                    END
                LIMIT :limit
            """

            with get_session() as session:
                result = session.execute(text(sql), params)

                search_results = []
                for row in result:
                    search_results.append(SearchResult(
                        site_id=row.id,
                        score=self.QUALITY_TIERS.get(row.source_id, 0.5),
                        source=row.source_id,
                        name=row.name,
                        site_type=row.site_type,
                        period_name=row.period_name,
                        country=row.country,
                        description=row.description,
                        lat=row.lat,
                        lon=row.lon,
                    ))

                logger.info(f"Database fallback returned {len(search_results)} results")
                return search_results

        except Exception as e:
            logger.error(f"Database fallback error: {e}")
            return []

    def health_check(self) -> dict[str, Any]:
        """Check vector store health."""
        try:
            collections = self.get_all_collections()
            total_count = sum(self.get_collection_count(c) for c in collections)
            return {
                "status": "healthy",
                "collections": len(collections),
                "total_documents": total_count,
                "collection_list": collections
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Singleton instance
_vector_store_instance: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Get singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance
