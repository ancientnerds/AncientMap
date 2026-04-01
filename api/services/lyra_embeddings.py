"""
Lyra Embeddings & Reranker Factory.

Uses Voyage AI for all embeddings and reranking:
  - Indexing: voyage-4-large (best quality, 1024-dim) with input_type="document"
  - Querying: voyage-4 (fast/cheap, same 1024-dim space) with input_type="query"
  - Reranking: rerank-2.5-lite (second-pass scorer)
"""

import logging
import os

import voyageai

logger = logging.getLogger(__name__)

# Voyage settings
EMBED_MODEL_INDEX = os.getenv("LYRA_EMBED_MODEL_INDEX", "voyage-4-large")
EMBED_MODEL_QUERY = os.getenv("LYRA_EMBED_MODEL_QUERY", "voyage-4")
RERANK_MODEL = os.getenv("LYRA_RERANK_MODEL", "rerank-2.5-lite")

# Shared Voyage client singleton
_voyage_client: voyageai.Client | None = None


def _get_voyage_client() -> voyageai.Client:
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.Client()
        logger.info("Initialized shared voyageai.Client")
    return _voyage_client


class VoyageEmbeddings:
    """Thin wrapper around voyageai.Client.embed() with correct input_type."""

    def __init__(self, model: str, input_type: str):
        self.model = model
        self.input_type = input_type
        self.last_total_tokens = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = _get_voyage_client()
        result = client.embed(texts, model=self.model, input_type=self.input_type)
        self.last_total_tokens = getattr(result, "total_tokens", 0) or 0
        return result.embeddings  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        client = _get_voyage_client()
        result = client.embed([text], model=self.model, input_type=self.input_type)
        self.last_total_tokens = getattr(result, "total_tokens", 0) or 0
        return result.embeddings[0]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Singletons keyed by usage
# ---------------------------------------------------------------------------
_embeddings: dict[str, VoyageEmbeddings] = {}


def get_embeddings(
    usage: str = "query", backend: str | None = None
) -> VoyageEmbeddings:
    """Get Voyage AI embedding model.

    Args:
        usage: 'index' for documents, 'query' for search.
    """
    if usage in _embeddings:
        return _embeddings[usage]

    model = EMBED_MODEL_INDEX if usage == "index" else EMBED_MODEL_QUERY
    input_type = "document" if usage == "index" else "query"
    instance = VoyageEmbeddings(model=model, input_type=input_type)
    logger.info(
        f"Initialized VoyageAI embeddings: {model} (usage={usage}, input_type={input_type})"
    )

    _embeddings[usage] = instance
    return instance


_qdrant_client = None


def get_qdrant_client():
    """Get singleton QdrantClient (reused across requests)."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    from qdrant_client import QdrantClient

    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    _qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
    logger.info(f"Initialized QdrantClient: {qdrant_host}:{qdrant_port}")
    return _qdrant_client


def get_reranker(backend: str | None = None) -> voyageai.Client:
    """Get Voyage AI reranker client."""
    return _get_voyage_client()


_sparse_model = None


def get_sparse_model():
    """Get BM25 sparse embedding model (fastembed, singleton).

    Used for hybrid search: generates sparse vectors alongside dense
    Voyage vectors. The "Qdrant/bm25" model runs server-side IDF
    weighting when stored with SparseVectorParams(modifier=Modifier.IDF).
    """
    global _sparse_model
    if _sparse_model is not None:
        return _sparse_model

    from fastembed import SparseTextEmbedding

    _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    logger.info("Initialized BM25 sparse model: Qdrant/bm25")
    return _sparse_model
