# Qdrant RAG Retrieval Best Practices (2025-2026)

Research compiled: 2026-03-26

---

## 1. Qdrant Hybrid Search Configuration

### 1.1 Fusion Methods: RRF vs DBSF

Qdrant supports two server-side fusion methods for combining results from multiple prefetch queries:

**Reciprocal Rank Fusion (RRF)**
- Formula: `RRF_score(d) = SUM( 1 / (k + rank_i(d)) )`
- Default `k` parameter: **60** (the original RRF paper uses 40; Haystack also uses 40)
- RRF ignores raw scores entirely -- it only considers rank positions
- Documents that appear near the top in multiple queries receive higher cumulative scores
- Supports per-prefetch **weights**: e.g., weight 3.0 on prefetch A and 1.0 on prefetch B means a doc ranked 3rd in A scores the same as a doc ranked 1st in B
- Smaller `k` values increase the impact of top-ranked results; larger `k` values flatten the curve

**Distribution-Based Score Fusion (DBSF)**
- Normalizes each search method's raw scores to [0, 1] using mean +/- 3 standard deviations as limits
- Sums the normalized scores for the same document across queries
- More sensitive to actual score magnitudes, not just rank
- Better when score distributions vary significantly between dense and sparse retrievers

**When to use which:**
| Scenario | Recommended |
|---|---|
| Dense + sparse agree on ranking | RRF |
| Score magnitudes vary greatly between methods | DBSF |
| You want simplicity and robustness | RRF |
| You need tighter normalization between incompatible score ranges | DBSF |
| Default starting point | RRF |

Qdrant's own article explicitly discourages linear weighting formulas like `0.7 * vector_score + 0.3 * bm25_score` because relevant and non-relevant objects are not linearly separable in that combined score space.

### 1.2 Prefetch Configuration and Limits

**Prefetch-to-final-limit ratios observed in documentation:**

| Source | Prefetch per method | Final limit | Ratio |
|---|---|---|---|
| Qdrant reranking tutorial | 20 | 10 | 2:1 |
| Qdrant hybrid search article (multistage) | 100 -> 50 -> 25 | 10 | 10:1 overall |
| Qdrant MRL example | 1000 | 10 | 100:1 |
| Typical demos | 20 | 10 | 2:1 |

**Practical guidance:**
- For two-method hybrid (dense + sparse) without reranking: **20 prefetch per method, 10 final** (2:1 ratio)
- For hybrid with client-side reranking: **50-100 prefetch per method, 10-20 final** (5:1 to 10:1)
- For MRL/Matryoshka multistage (small vector -> full vector): **1000 coarse, 10 final** (100:1, because the coarse pass is very cheap)
- The prefetch limit for each sub-query must be >= `limit + offset` of the parent query

**Constraint:** Prefetches can be nested (prefetches within prefetches), enabling multi-stage funneling. Each stage progressively narrows the candidate set.

### 1.3 RRF Configuration Code Example

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://localhost:6333")

results = client.query_points(
    collection_name="my_collection",
    prefetch=[
        models.Prefetch(
            query=dense_embedding,       # float vector
            using="dense",               # named vector
            limit=100,                   # candidates from dense search
        ),
        models.Prefetch(
            query=models.SparseVector(indices=indices, values=values),
            using="sparse",              # named sparse vector
            limit=100,                   # candidates from sparse search
        ),
    ],
    query=models.RrfQuery(
        rrf=models.Rrf(
            k=60,                        # default; tune lower for sharper top-weighting
            weights=[1.0, 1.0],          # equal weight; increase first to favor dense
        )
    ),
    limit=10,                            # final results returned
    with_payload=True,
)
```

### 1.4 DBSF Configuration Code Example

```python
results = client.query_points(
    collection_name="my_collection",
    prefetch=[
        models.Prefetch(query=dense_embedding, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="sparse", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.DBSF),
    limit=10,
    with_payload=True,
)
```

---

## 2. Qdrant Payload Best Practices

### 2.1 Full Text in Payloads vs Metadata Only

**Qdrant's official position:** You can store all chunks and metadata along with vectors in Qdrant -- you do not need additional tools for this. Qdrant is designed to handle payload storage alongside vectors.

**Tradeoffs:**

| Approach | Pros | Cons |
|---|---|---|
| Full text in payload | Single data store, no external DB needed, simpler architecture | Higher RAM if payloads kept in-memory; larger disk footprint |
| Metadata + truncated preview | Lower memory usage, faster payload retrieval | Requires external store for full text; more moving parts |
| Full text with `on_disk_payload: true` | Best of both worlds -- full text stored but not in RAM | Slightly higher latency when reading payloads from disk |

**Recommendation for RAG:** Store full chunk text in the payload with `on_disk_payload: true`. This keeps payloads on disk (not in RAM), read only when requested. For a RAG pipeline you typically only need the payload text for the final top-K results (5-20 documents), so the per-request disk read overhead is negligible.

### 2.2 Memory Impact of Payloads

**Memory estimation formula for vectors:**
```
memory_size = num_vectors * vector_dimension * 4 bytes * 1.5
```
The 1.5x multiplier accounts for HNSW graph metadata, point versions, and temporary optimization segments.

**Payload memory:**
- With `on_disk_payload: false` (default): all payload data lives in RAM
- For 1M points with 5KB JSON payloads: ~4.77 GB of RAM just for payloads
- With `on_disk_payload: true`: payloads read from disk on demand; only indexed fields remain in RAM
- Indexed payload fields always stay in RAM regardless of `on_disk_payload` setting

**Key insight:** If you store 2KB chunk text per point across 1M points, that is ~2GB of RAM wasted on payload data that is only needed at response time. Use `on_disk_payload: true` to reclaim that RAM.

### 2.3 Payload Indexing Best Practices

**Index every field you filter on.** Without an index, Qdrant loads the entire payload from disk to check filter conditions -- defeating the purpose of `on_disk_payload: true`.

**Available index types:**

| Index Type | Use For | Operations Supported |
|---|---|---|
| Keyword | Categories, tags, source IDs, status strings | Match, match-any, except |
| Integer | Counts, years, numeric IDs | Range, match |
| Float | Scores, ratings, coordinates | Range |
| Geo | Lat/lon coordinates | Radius, bounding box, polygon |
| Text (full-text) | Searchable text content (BM25-like) | Full-text search, phrase matching |
| Datetime | Timestamps | Range |
| UUID | Unique identifiers | Match, match-any |
| Bool | Boolean flags | Match |

**What NOT to index:**
- Boolean fields with only true/false (very low cardinality, index adds overhead without benefit)
- Fields with only 2-3 possible values
- Large text fields you do NOT filter on (the text index is memory-heavy due to tokenization)

**What TO index for RAG:**
- `source_id` or `source` (keyword index) -- filter by data source
- `category` or `type` (keyword index) -- filter by content type
- `created_at` or `timestamp` (datetime index) -- for recency filtering/boosting
- `language` (keyword index) -- if multilingual corpus
- `site_id` or `document_id` (keyword or UUID index) -- for document-level operations

**Text index for sparse/BM25 search:** If using Qdrant's built-in full-text index as your sparse retriever instead of external sparse embeddings (SPLADE/BM25), configure tokenizer carefully:
- `word` tokenizer: splits on spaces + punctuation (most common)
- `prefix` tokenizer: splits on spaces + punctuation, then creates prefix index (for autocomplete)

### 2.4 Collection Configuration Example

```python
client.create_collection(
    collection_name="rag_chunks",
    vectors_config={
        "dense": models.VectorParams(
            size=1024,                   # voyage-4 default dimension
            distance=models.Distance.DOT, # cosine = dot for normalized vectors
            on_disk=True,                # MMAP vectors to disk
        ),
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams(
            modifier=models.Modifier.IDF, # built-in IDF weighting
        ),
    },
    optimizers_config=models.OptimizersConfigDiff(
        indexing_threshold=20000,        # delay HNSW build until 20k points
    ),
    on_disk_payload=True,                # payloads on disk, not RAM
)

# Create payload indexes for fields you filter on
client.create_payload_index("rag_chunks", "source_id", models.PayloadSchemaType.KEYWORD)
client.create_payload_index("rag_chunks", "language", models.PayloadSchemaType.KEYWORD)
client.create_payload_index("rag_chunks", "created_at", models.PayloadSchemaType.DATETIME)
```

---

## 3. Voyage AI Embeddings with Qdrant

### 3.1 Voyage-4 Model Family Overview

Released January 2026, the Voyage 4 family uses a Mixture-of-Experts (MoE) architecture:

| Model | Dimensions | Best For | Notes |
|---|---|---|---|
| voyage-4-large | 2048/1024/512/256 | Best accuracy, document indexing | First production MoE embedding model; 40% lower serving costs than comparable dense models |
| voyage-4 | 2048/1024/512/256 | Balanced quality/cost | Good general-purpose and multilingual |
| voyage-4-lite | 2048/1024/512/256 | Low latency, high throughput | Best for query-time embedding |
| voyage-4-nano | 2048/1024/512/256 | Minimal cost | Lightest option |

All four models produce embeddings in the **same shared vector space**. This is the critical feature enabling asymmetric retrieval.

### 3.2 Asymmetric Query/Document Embedding

**Yes, this is explicitly recommended by Voyage AI.** This is one of the headline features of the Voyage 4 family.

**Recommended pattern:**
- Embed documents with `voyage-4-large` (best accuracy, done once or infrequently)
- Embed queries with `voyage-4-lite` or `voyage-4` (lower latency, done continuously at serving time)
- No re-indexing needed when switching query models

**Rationale:** Document embedding is a one-time or infrequent cost. Query embedding happens on every user request. Using a lighter model for queries reduces per-request latency and cost while preserving retrieval quality because all models share the same embedding space.

**Code pattern:**
```python
import voyageai

vo = voyageai.Client()

# Document embedding (done once during indexing)
doc_embeddings = vo.embed(
    texts=documents,
    model="voyage-4-large",
    input_type="document",
)

# Query embedding (done on every search request)
query_embedding = vo.embed(
    texts=[user_query],
    model="voyage-4-lite",    # or voyage-4 for more accuracy
    input_type="query",
)
```

### 3.3 The `input_type` Parameter

**Always specify `input_type` for retrieval tasks.**

- `input_type="query"` -- prepends an internal instruction: "Represent the query for retrieving supporting documents"
- `input_type="document"` -- prepends an internal instruction: "Represent the document for retrieval"
- `None` -- no instruction prepended; use only for non-retrieval tasks (classification, clustering)

This is not optional for RAG. The asymmetric prompting significantly improves retrieval quality.

### 3.4 Distance Metric

Voyage AI embeddings are **normalized to unit length**. This means:
- Cosine similarity = dot product similarity (mathematically equivalent for unit vectors)
- **Use dot product** in Qdrant (`Distance.DOT`) for faster computation
- Do NOT use Euclidean distance

### 3.5 Dimension Selection with Matryoshka Learning

All Voyage 4 models support Matryoshka dimensions: 2048, 1024, 512, 256.

**Recommendation for RAG:**
- **1024 dimensions** is the sweet spot for most RAG applications (good accuracy, reasonable memory)
- **2048 dimensions** for maximum accuracy when memory/storage is not a constraint
- **512 dimensions** for very large corpora (millions of chunks) where memory is tight
- **256 dimensions** only for coarse first-stage retrieval in multistage pipelines

### 3.6 Quantization Support

Voyage 4 supports native quantization: 32-bit float, signed/unsigned 8-bit integer, and binary precision. Binary quantization reduces storage 32x with minimal quality degradation -- useful for very large collections.

In Qdrant, configure scalar quantization:
```python
vectors_config={
    "dense": models.VectorParams(
        size=1024,
        distance=models.Distance.DOT,
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                quantile=0.99,
                always_ram=True,  # keep quantized vectors in RAM for speed
            ),
        ),
    ),
}
```

### 3.7 Multilingual Handling

Voyage AI models are **inherently multilingual** -- semantic similarity is computed irrespective of language. Cross-lingual retrieval works natively (e.g., an English query can retrieve a French document).

**Should you translate before embedding?** No. The models handle multilingual content directly. Pre-translation would add latency and potential translation errors without improving retrieval quality.

**For best multilingual performance:** Use `voyage-4-large` (explicitly described as having the best multilingual retrieval quality).

---

## 4. Qdrant Multistage Retrieval

### 4.1 Architecture Options

**Option A: Prefetch + Fusion (two-stage, simplest)**
```
[Dense prefetch: 100 candidates] --\
                                     +--> RRF/DBSF fusion --> Top 10
[Sparse prefetch: 100 candidates] --/
```

**Option B: Prefetch + Fusion + Server-side Rerank (three-stage)**
```
[Dense prefetch: 100] --\
                         +--> RRF fusion --> Top 50 --> Score-boost formula --> Top 10
[Sparse prefetch: 100] --/
```

**Option C: Prefetch + Fusion + Client-side Rerank (three-stage)**
```
[Dense prefetch: 100] --\
                         +--> RRF fusion --> Top 50 --> [Client: Voyage rerank-2.5] --> Top 10
[Sparse prefetch: 100] --/
```

**Option D: Nested Prefetch with MRL (multistage funnel)**
```
[256-dim MRL: 1000 candidates] --> [1024-dim MRL rescore: 100] --> [ColBERT rerank: 10]
```

**Option E: Full pipeline (Qdrant article's "complex" example)**
```
[Dense 256-dim: 100] --> [Dense 1024-dim rescore: 50] --> [Full vector rescore: 25] --> Top 10
```
Qdrant's own article notes: "You rarely need to build such a complex search pipeline."

### 4.2 Recommended Prefetch Sizes for Production

| Stage | Purpose | Recommended Limit |
|---|---|---|
| Coarse retrieval (MRL small dim) | Cast wide net cheaply | 500-1000 |
| Dense retrieval (full dim) | Semantic candidates | 50-100 |
| Sparse retrieval (BM25/SPLADE) | Keyword candidates | 50-100 |
| Post-fusion, pre-rerank | Candidates for reranker | 20-50 |
| Final results to user/LLM | Context window budget | 5-20 |

**Rules of thumb:**
- Each stage should reduce candidates by 2x-10x
- Rerankers are expensive -- feed them 20-50 candidates, not 500
- Coarse MRL passes are cheap -- 1000 candidates at 256-dim costs less than 100 at 1024-dim

### 4.3 Server-Side Reranking (Qdrant 1.14+)

Qdrant 1.14 introduced the **Score-Boosting Reranker** -- a formula-based rescoring engine that runs server-side. It does NOT replace a neural reranker (like Voyage rerank-2.5) but allows blending semantic scores with payload-based signals.

**What it can do:**
- Combine `$score` (vector similarity) with payload field values
- Apply decay functions (linear, gaussian, exponential) for recency, geo-proximity, etc.
- Weight different content types (e.g., boost titles over body text)

**What it cannot do:**
- Cross-encoder style semantic reranking (that requires a neural model)
- Late-interaction reranking (ColBERT) -- though Qdrant supports this via multivector rescore

**Example: Recency-boosted hybrid search**
```python
results = client.query_points(
    collection_name="rag_chunks",
    prefetch=[
        models.Prefetch(query=dense_vec, using="dense", limit=50),
        models.Prefetch(query=sparse_vec, using="sparse", limit=50),
    ],
    query=models.FormulaQuery(
        formula={
            "sum": [
                "$score",
                {
                    "gauss_decay": {
                        "x": {"datetime_key": "created_at"},
                        "target": {"datetime": "2026-03-26T00:00:00Z"},
                        "scale": 604800,      # 1 week in seconds
                        "midpoint": 0.5,
                    }
                }
            ]
        }
    ),
    limit=10,
)
```

### 4.4 Server-Side vs Client-Side Reranking

| Aspect | Server-side (Score-boost) | Client-side (Voyage/Cohere reranker) |
|---|---|---|
| Latency | Very low (runs in Qdrant) | Additional API call (200-600ms) |
| Accuracy | Heuristic (formula-based) | Neural cross-encoder (much higher quality) |
| Cost | Free (included in Qdrant) | Per-token API cost |
| Use case | Payload-based boosting (recency, geo, category) | Semantic relevance refinement |
| Network | No extra round-trip | Round-trip to reranker API |

**Recommendation:** Use both. Server-side score-boosting for payload-based signals (recency, category weighting). Client-side neural reranking (Voyage rerank-2.5) for semantic refinement of the final candidate set.

### 4.5 ColBERT/Late-Interaction Reranking in Qdrant

For ColBERT-style multi-vector reranking used only in the rescore stage:
- Disable HNSW graph creation: `hnsw_config=models.HnswConfigDiff(m=0)`
- This saves significant resources since ColBERT creates hundreds of embeddings per document
- Qdrant handles MaxSim computation automatically for multi-vector similarity

---

## 5. Voyage Rerank Score Interpretation

### 5.1 Score Range

Voyage rerank-2.5 and rerank-2.5-lite return `relevance_score` values in the **[0, 1] range**.

Example API response:
```json
{
  "data": [
    {"relevance_score": 0.455078125, "index": 0},
    {"relevance_score": 0.439453125, "index": 1}
  ]
}
```

### 5.2 Score Calibration Problem -- Critical Warning

**Voyage reranker scores are NOT well-calibrated for absolute thresholding.** This is a known and documented issue across the industry:

- Voyage rerank models (including rerank-3.5 and older versions) tend to **cluster scores around 0.5** regardless of actual relevance
- Example: Two documents of very different relevance might score 0.5859 and 0.5312 -- nearly indistinguishable
- The scores produce correct *relative ordering* (higher score = more relevant within a single query) but the *absolute values* are not meaningfully interpretable
- You cannot reliably say "0.8 means relevant" and "0.3 means irrelevant"

**Comparison with Cohere:** Cohere Rerank scores have the same fundamental issue -- scores are query-dependent and scattered across the value space. Neither Voyage nor Cohere produces scores where a fixed threshold reliably separates relevant from irrelevant documents.

**Models with better calibration:** ZeroEntropy's zerank-2 uses ELO-based pairwise training that produces better-calibrated probability scores (a score of 0.8 consistently means ~80% relevance). However, zerank-2 is a newer/less established option.

### 5.3 Practical Threshold Strategy

Since absolute thresholds are unreliable, use **relative strategies** instead:

**Strategy 1: Top-K only (recommended for RAG)**
- Take the top K results from the reranker regardless of score
- Feed them all to the LLM as context
- Let the LLM determine relevance during generation
- This is the simplest and most robust approach

**Strategy 2: Empirically calibrated domain-specific threshold**
If you must filter by score (e.g., to avoid feeding clearly irrelevant context to the LLM):
1. Collect 30-50 representative queries from your domain
2. For each query, identify a document that represents the minimum acceptable relevance
3. Pass all (query, borderline-doc) pairs through the reranker
4. Average the resulting scores -- use this as your threshold
5. Re-calibrate periodically as your corpus changes

**Strategy 3: Score gap detection**
- Sort results by descending rerank score
- Look for the largest score gap between consecutive results
- Use the gap as a natural cutoff point
- This adapts per-query without a fixed threshold

**Strategy 4: Relative threshold**
- Take the top result's score as the anchor
- Keep all results within X% of the top score (e.g., within 70% of top score)
- Discard results that fall below this relative threshold

### 5.4 Rerank-2.5 vs Rerank-2.5-lite

| Feature | rerank-2.5 | rerank-2.5-lite |
|---|---|---|
| Accuracy (NDCG@10 vs Cohere v3.5) | +7.94% | +7.16% |
| MAIR benchmark vs Cohere v3.5 | +12.70% | +10.36% |
| Context length | 32K tokens | 32K tokens |
| Instruction-following accuracy boost | +8.13% (domain-specific) | +7.55% (domain-specific) |
| Latency | ~613ms | Lower (lite) |
| Use case | Accuracy-critical | Latency-sensitive |

Both support **instruction-following** -- you can steer relevance scoring with natural language:
```python
results = vo.rerank(
    query="ancient archaeological sites in Turkey",
    documents=candidate_docs,
    model="rerank-2.5",
    instruction="Prioritize documents about sites with active excavations. "
                "Deprioritize tourism-focused content.",
    top_k=10,
)
```

This instruction-following capability improves domain-specific accuracy by +8-11% and partially mitigates the calibration problem by letting you define what "relevant" means for your specific use case.

### 5.5 Practical Recommendations for RAG

1. **Use rerank-2.5** (not lite) unless latency is critical -- the accuracy gain is worth the extra ~150ms
2. **Always use `instruction`** parameter to define your relevance criteria
3. **Do NOT use absolute score thresholds** for filtering -- use top-K or relative strategies
4. **Feed 20-50 candidates** to the reranker, return top 5-10 to the LLM
5. **Truncation defaults to true** -- documents exceeding 32K tokens are automatically truncated, so you do not need to pre-truncate
6. **For multilingual RAG**: rerank-2.5 handles multilingual content natively (same as embeddings)

---

## Appendix: Complete RAG Pipeline Configuration

Putting it all together -- a production Qdrant + Voyage AI RAG pipeline:

```python
# === Collection Setup ===
client.create_collection(
    collection_name="rag_chunks",
    vectors_config={
        "dense": models.VectorParams(
            size=1024,                        # voyage-4-large at 1024 dims
            distance=models.Distance.DOT,     # unit-normalized = cosine
            on_disk=True,                     # MMAP vectors
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        ),
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams(
            modifier=models.Modifier.IDF,
        ),
    },
    on_disk_payload=True,
)

# Payload indexes for filtered search
client.create_payload_index("rag_chunks", "source_id", models.PayloadSchemaType.KEYWORD)
client.create_payload_index("rag_chunks", "language", models.PayloadSchemaType.KEYWORD)
client.create_payload_index("rag_chunks", "created_at", models.PayloadSchemaType.DATETIME)

# === Indexing ===
# Embed documents with voyage-4-large (best accuracy, done once)
doc_embeddings = vo.embed(texts=chunks, model="voyage-4-large", input_type="document")

# === Query Time ===
# 1. Embed query with voyage-4-lite (fast, done per request)
query_emb = vo.embed(texts=[query], model="voyage-4-lite", input_type="query")

# 2. Hybrid retrieval with RRF fusion
candidates = client.query_points(
    collection_name="rag_chunks",
    prefetch=[
        models.Prefetch(query=query_emb[0], using="dense", limit=50),
        models.Prefetch(query=sparse_query, using="sparse", limit=50),
    ],
    query=models.RrfQuery(rrf=models.Rrf(k=60)),
    limit=30,                                    # 30 candidates for reranker
    with_payload=True,
)

# 3. Client-side neural reranking with Voyage
reranked = vo.rerank(
    query=query,
    documents=[hit.payload["text"] for hit in candidates.points],
    model="rerank-2.5",
    instruction="Prioritize documents that directly answer the query. "
                "Deprioritize tangentially related content.",
    top_k=10,
)

# 4. Build LLM context from top reranked results
context_chunks = [candidates.points[r.index].payload["text"] for r in reranked.results]
```

---

## Sources

### Qdrant Documentation and Articles
- [Hybrid Queries Documentation](https://qdrant.tech/documentation/concepts/hybrid-queries/)
- [Hybrid Search Revamped Article](https://qdrant.tech/articles/hybrid-search/)
- [Capacity Planning Guide](https://qdrant.tech/documentation/guides/capacity-planning/)
- [Qdrant 1.14 Release (Server-side Reranking)](https://qdrant.tech/blog/qdrant-1.14.x/)
- [Reranking in Hybrid Search Tutorial](https://qdrant.tech/documentation/tutorials-search-engineering/reranking-hybrid-search/)
- [Vector Search Filtering Guide](https://qdrant.tech/articles/vector-search-filtering/)
- [Decay Functions for Score Boosting](https://qdrant.tech/blog/decay-functions/)
- [Minimal RAM for Million Vectors](https://qdrant.tech/articles/memory-consumption/)
- [Voyage AI Integration Guide](https://qdrant.tech/documentation/embeddings/voyage/)
- [Qdrant Hybrid Search (DeepWiki)](https://deepwiki.com/qdrant/qdrant-client/5.4-hybrid-search)
- [Payload Indexing and Filtering (DeepWiki)](https://deepwiki.com/qdrant/qdrant/4-payload-indexing-and-filtering)
- [Enterprise RAG Settings Discussion](https://github.com/orgs/qdrant/discussions/4130)

### Voyage AI Documentation and Articles
- [Voyage 4 Model Family Blog Post](https://blog.voyageai.com/2026/01/15/voyage-4/)
- [Rerank-2.5 Announcement](https://blog.voyageai.com/2025/08/11/rerank-2-5/)
- [Voyage AI Reranker API Reference](https://docs.voyageai.com/reference/reranker-api)
- [Voyage AI Text Embeddings Documentation](https://docs.voyageai.com/docs/embeddings)
- [Voyage AI FAQ](https://docs.voyageai.com/docs/faq)
- [Voyage AI Reranker Documentation](https://docs.voyageai.com/docs/reranker)
- [Voyage AI Rerankers (MongoDB Docs)](https://www.mongodb.com/docs/voyageai/models/rerankers/)

### Comparison and Analysis
- [RRF vs DBSF Explained (Haikel Fazzani)](https://haikel-fazzani.deno.dev/blog/rrf-vs-dbsf-qdrant)
- [Cohere Reranking Best Practices](https://docs.cohere.com/docs/reranking-best-practices)
- [ZeroEntropy: zerank-2 Reranker Analysis](https://www.zeroentropy.dev/articles/zerank-2-advanced-instruction-following-multilingual-reranker)
- [Agentset: Best Reranker for RAG](https://agentset.ai/blog/best-reranker)
- [Voyage Rerank 2.5 vs Cohere Rerank 4 Fast](https://agentset.ai/rerankers/compare/voyage-ai-rerank-25-vs-cohere-rerank-4-fast)
- [Embedding Model Comparison 2026](https://www.buildmvpfast.com/blog/best-embedding-model-comparison-voyage-openai-cohere-2026)
