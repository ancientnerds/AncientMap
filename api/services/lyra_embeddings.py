"""
Lyra Embeddings & Reranker Factory.

Both backends are always available simultaneously (per-request routing):

1. "voyage" (default) — Voyage AI paid API:
   - Indexing: voyage-4-large (best quality, 1024-dim) with input_type="document"
   - Querying: voyage-4 (fast/cheap, same 1024-dim space) with input_type="query"
   - Reranking: rerank-2.5-lite (second-pass scorer)

2. "local" — Self-hosted via Ollama + FlashRank reranker:
   - Embeddings: nomic-embed-text (768-dim) via OpenAI-compatible /v1/embeddings
   - Reranking: FlashRank ONNX service via HTTP

Collections: Voyage uses 'sites', 'news', etc. Local uses 'sites_local', 'news_local', etc.
Both collection sets coexist in Qdrant and are reindexed nightly.
"""

import logging
import os
from dataclasses import dataclass

import voyageai

logger = logging.getLogger(__name__)

# Voyage settings
EMBED_MODEL_INDEX = os.getenv("LYRA_EMBED_MODEL_INDEX", "voyage-4-large")
EMBED_MODEL_QUERY = os.getenv("LYRA_EMBED_MODEL_QUERY", "voyage-4")
RERANK_MODEL = os.getenv("LYRA_RERANK_MODEL", "rerank-2.5-lite")

# Ollama/self-hosted settings
OLLAMA_EMBED_URL = os.getenv("LYRA_OLLAMA_EMBED_URL", "")
OLLAMA_EMBED_MODEL = os.getenv("LYRA_OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_API_KEY = os.getenv("LYRA_OLLAMA_EMBED_API_KEY", "")
RERANK_URL = os.getenv("LYRA_RERANK_URL", "")

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


class OllamaEmbeddings:
    """OpenAI-compatible embeddings via Ollama. Same interface as VoyageEmbeddings."""

    def __init__(self, model: str = OLLAMA_EMBED_MODEL):
        self.model = model
        self.last_total_tokens = 0
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=OLLAMA_EMBED_URL,
                api_key=OLLAMA_EMBED_API_KEY or "unused",
                timeout=120.0,
            )
        return self._client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embeddings.create(model=self.model, input=texts)
        self.last_total_tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        client = self._get_client()
        response = client.embeddings.create(model=self.model, input=[text])
        self.last_total_tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0
        return response.data[0].embedding


# ---------------------------------------------------------------------------
# Self-hosted reranker client
# ---------------------------------------------------------------------------
@dataclass
class _RerankResult:
    index: int
    relevance_score: float


@dataclass
class _RerankResponse:
    results: list[_RerankResult]
    total_tokens: int = 0


class LocalReranker:
    """HTTP client for the FlashRank reranker service. Matches Voyage's rerank() interface."""

    def __init__(self, url: str = RERANK_URL):
        self.url = url.rstrip("/")

    def rerank(self, query: str, documents: list[str], model: str | None = None, top_k: int = 10):
        import httpx

        headers = {}
        if OLLAMA_EMBED_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_EMBED_API_KEY}"

        resp = httpx.post(
            f"{self.url}",
            json={"query": query, "documents": documents, "top_k": top_k},
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            _RerankResult(index=r["index"], relevance_score=r["relevance_score"])
            for r in data["results"]
        ]
        return _RerankResponse(results=results, total_tokens=0)


# ---------------------------------------------------------------------------
# Singletons keyed by (usage, backend)
# ---------------------------------------------------------------------------
_embeddings: dict[tuple[str, str], VoyageEmbeddings | OllamaEmbeddings] = {}


def get_embeddings(
    usage: str = "query", backend: str | None = None
) -> VoyageEmbeddings | OllamaEmbeddings:
    """Get embedding model for the given backend.

    Args:
        usage: 'index' for documents, 'query' for search.
        backend: 'voyage' (default), or 'local' (Ollama).
    """
    backend = backend or "voyage"
    key = (usage, backend)

    if key in _embeddings:
        return _embeddings[key]

    if backend == "local":
        instance = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL)
        logger.info(f"Initialized Ollama embeddings: {OLLAMA_EMBED_MODEL} (usage={usage})")
    else:
        model = EMBED_MODEL_INDEX if usage == "index" else EMBED_MODEL_QUERY
        input_type = "document" if usage == "index" else "query"
        instance = VoyageEmbeddings(model=model, input_type=input_type)
        logger.info(
            f"Initialized VoyageAI embeddings: {model} (usage={usage}, input_type={input_type})"
        )

    _embeddings[key] = instance
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


_rerankers: dict[str, voyageai.Client | LocalReranker] = {}


def get_reranker(backend: str | None = None) -> voyageai.Client | LocalReranker:
    """Get reranker for the given backend."""
    backend = backend or "voyage"

    if backend in _rerankers:
        return _rerankers[backend]

    if backend == "local":
        instance = LocalReranker(url=RERANK_URL)
        logger.info(f"Initialized LocalReranker: {RERANK_URL}")
    else:
        instance = _get_voyage_client()

    _rerankers[backend] = instance
    return instance


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
