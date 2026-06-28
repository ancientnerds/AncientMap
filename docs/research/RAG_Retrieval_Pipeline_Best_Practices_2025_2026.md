# RAG Retrieval Pipeline: State-of-the-Art Best Practices (2025-2026)

*Research compiled March 2026. Focused on production-tested patterns, not academic theory.*

---

## Table of Contents

1. [Relevance Scoring and Thresholds](#1-relevance-scoring-and-thresholds)
2. [Hybrid Search (Dense + Sparse) Fusion](#2-hybrid-search-dense--sparse-fusion)
3. [Multilingual RAG](#3-multilingual-rag)
4. [Reranking Best Practices](#4-reranking-best-practices)
5. [Chunk Design for Transcripts/Long Documents](#5-chunk-design-for-transcriptslong-documents)
6. [Query Understanding and Expansion](#6-query-understanding-and-expansion)
7. [Adaptive Retrieval](#7-adaptive-retrieval)
8. [Off-topic / No-result Handling](#8-off-topic--no-result-handling)

---

## 1. Relevance Scoring and Thresholds

### Hard Thresholds vs Adaptive/Relative Thresholds

**The industry consensus has moved decisively away from fixed hard thresholds toward adaptive, distribution-aware approaches.**

**Fixed hard thresholds fail because:**
- Embedding similarity scores are not calibrated across queries. A score of 0.85 on one query may be equivalent to 0.72 on another depending on corpus density.
- Reranker scores, even when normalized to [0,1], are not linearly interpretable. Cohere's own documentation states: "You can't assume that a document with a relevance score of 0.9109375 is twice as relevant as one with a relevance score of 0.04421997."
- Score distributions vary wildly across domains and customer bases. Assembled's production testing found "similarity scores varied widely across different customers, making it impractical to develop a universal weighting scheme."

**What works in production:**

1. **Adaptive thresholds based on score distribution**: Calculate the mean and standard deviation of scores for each query's result set. Set the threshold as `mean + k*stddev` where k is tuned empirically. This adapts to each query's score landscape.

2. **Relative scoring (percentage of top)**: Keep results within X% of the top score. For example, keep all results scoring above 70% of the best result's score. This is simpler and works well when score distributions are unimodal.

3. **Cohere's calibration methodology** (the most concrete industry guidance available):
   - Select 30-50 representative domain-specific queries
   - Identify a "borderline relevant" document for each query
   - Run all pairs through the reranker
   - Use the **average** of these borderline scores as your filtering threshold
   - This produces a domain-calibrated threshold rather than a universal one

4. **DynamicRAG approach**: Use reinforcement learning to train a dynamic reranker that determines both the ranking AND the number (k) of documents to return per query. The reward signal is the quality of the LLM's final answer.

### No Results vs Always Top-K

**Recommendation: Implement a two-tier approach.**

- **Always retrieve top-K** from the vector store (you need candidates to evaluate).
- **Apply post-retrieval filtering** using reranker scores or confidence estimation.
- **Return "insufficient evidence" when all results fall below the adaptive threshold** rather than forcing low-quality results into the LLM context.

The key insight from 2025 research (Confidence-Calibrated RAG by Ozaki et al.): stuffing irrelevant documents into the context actively harms generation quality and increases hallucination. It is better to return fewer results than to pad with noise.

**Production targets:**
- Precision@5 >= 0.7 for narrow-domain knowledge bases
- Recall@20 >= 0.8 for broad corpus search
- Context relevance and context recall >= 0.75

### Actionable Configuration

```
# Pseudocode for adaptive threshold filtering
results = reranker.rerank(query, candidates, top_k=50)
scores = [r.score for r in results]

if len(scores) == 0:
    return NO_RESULTS

top_score = scores[0]
mean_score = mean(scores)
std_score = std(scores)

# Method 1: Relative to top (simpler)
relative_threshold = top_score * 0.6  # Keep results within 60% of best

# Method 2: Distribution-aware (more robust)
adaptive_threshold = mean_score + 0.5 * std_score

# Method 3: Cohere-style calibrated (most reliable, requires upfront work)
calibrated_threshold = YOUR_DOMAIN_CALIBRATED_VALUE  # From 30-50 query calibration

# Apply whichever method, then check minimum quality
filtered = [r for r in results if r.score >= threshold]
if len(filtered) == 0 or filtered[0].score < absolute_minimum:
    return INSUFFICIENT_EVIDENCE
```

---

## 2. Hybrid Search (Dense + Sparse) Fusion

### RRF vs Weighted Linear Combination

**RRF is the production standard. Linear combination has serious practical problems.**

**Why RRF wins:**
- BM25 scores and cosine similarity scores occupy fundamentally different scales and distributions. Qdrant's analysis demonstrates they are "not linearly separable in that space," making weighted formulas like `0.7*vector + 0.3*text` mathematically unsound.
- RRF operates on **rank positions**, not raw scores, which eliminates normalization problems entirely.
- RRF is robust to outlier scores that can distort linear combinations.
- RRF requires minimal parameter tuning (just the constant k, typically 60).

**When linear combination can work:**
- When you control both the dense and sparse scoring functions and can guarantee comparable distributions.
- Pinecone and Weaviate offer `alpha` parameters (`final_score = alpha * dense + (1-alpha) * sparse`) because they internally normalize scores, but this still requires alpha tuning.

**RRF formula:** `RRF_score(d) = SUM(1 / (k + rank_i(d)))` across all retrieval lists, where k=60 is the standard constant.

**Weighted RRF** (newer, adopted by Elasticsearch in 2025): Assigns different weights to different retrieval lists within the RRF framework, giving the simplicity of rank-based fusion with the control of weighting. This is preferable to weighted linear score combination.

### Prefetch Pool Sizes

**3x is insufficient for most production use cases. The recommended range is 5-10x the final desired result count.**

Specific recommendations from production systems:

| Stage | Pool Size | Purpose |
|-------|-----------|---------|
| Initial dense prefetch | 100 | Broad semantic recall |
| Initial sparse prefetch | 100 | Keyword/entity recall |
| Post-fusion (RRF) | ~150 unique | Merged candidate pool |
| After reranking | 10-25 | High-precision final set |
| Delivered to LLM | 5-10 | Context window budget |

**Qdrant's recommended hybrid configuration:**

```python
# Two-stage: dense + sparse prefetch, fused with RRF
prefetch=[
    models.Prefetch(query=dense_vector, using="dense", limit=100),
    models.Prefetch(query=sparse_vector, using="sparse", limit=100),
]
query=models.FusionQuery(fusion=models.Fusion.RRF)
limit=20  # Post-fusion results for reranking
```

For Matryoshka embedding pipelines, Qdrant supports cascaded prefetch:
- Stage 1: 100 candidates with low-dimensional embeddings (fast, cheap)
- Stage 2: 50 candidates reranked with medium-dimensional embeddings
- Stage 3: 25 candidates with full-dimensional embeddings
- Final: top 10 after cross-encoder reranking

### Alpha Tuning: Should It Be Query-Dependent?

**Yes, but the implementation complexity may not be justified for all use cases.**

**Static alpha** (simpler approach):
- alpha = 0.5-0.7 works for most general-purpose RAG systems
- alpha = 0.7-0.8 (favoring dense) for conversational/semantic queries
- alpha = 0.2-0.3 (favoring sparse) for technical docs with exact terms, error codes, product names

**Dynamic Alpha Tuning (DAT)** -- a March 2025 paper that formalized per-query alpha adjustment:
- Uses an LLM to score the top-1 result from both dense and BM25 retrieval on a 0-5 scale
- Computes alpha as: `alpha(q) = dense_score / (dense_score + bm25_score)`
- Falls back to 0.5 when both methods fail, 1.0 when only dense works, 0.0 when only BM25 works
- Achieved ~7.5% precision improvement on "hybrid-sensitive" queries (the hard cases where dense and sparse disagree)

**Practical recommendation:** If you use RRF (rank-based), the alpha question is less relevant since you are not combining scores. RRF inherently handles the "which method wins" problem per-query. If you use linear combination (Pinecone/Weaviate alpha parameter), start with alpha=0.6, and only invest in dynamic tuning if you measure significant variance in retrieval quality across query types.

### Fusion Methods in Qdrant

Qdrant offers two built-in fusion methods:
1. **RRF (Reciprocal Rank Fusion)**: The "de facto standard in the field" per Qdrant's own documentation. Rank-based, score-agnostic.
2. **DBSF (Distribution-Based Score Fusion)**: Normalizes scores based on their statistical distribution before combining. Useful when you want to preserve score magnitude information.

**Use RRF** unless you have a specific reason to need score-aware fusion and have verified that your score distributions are well-behaved.

---

## 3. Multilingual RAG

### Cross-Language Retrieval Strategy

**The 2025 consensus is: use multilingual embeddings as the foundation, with query translation as a supplementary technique for low-resource languages.**

Four main approaches, ranked by practical effectiveness:

1. **Multilingual embeddings only** (simplest, often sufficient):
   - Embed queries and documents in their native languages
   - Models like `voyage-3-large`, `voyage-multilingual-2`, and `BGE-M3` map all languages into a shared semantic space
   - voyage-multilingual-2 outperforms alternatives by 5.6% on average across 26 languages
   - voyage-3-large covers 100 datasets across 8 domains including multilingual

2. **Question-translation RAG (tRAG)** -- translate query to English before retrieval:
   - Works well when your corpus is primarily English
   - Adds latency from the translation step
   - Can lose nuance in the translation, especially for culturally-specific concepts

3. **CrossRAG** -- translate retrieved documents to query language before generation:
   - More expensive (translate N documents vs 1 query)
   - But preserves the user's original query intent
   - Shown to help with low-resource languages

4. **Dual Knowledge Multilingual RAG (DKM-RAG)** -- fuses translated passages and model-internal knowledge:
   - Most sophisticated, highest accuracy
   - Mitigates both language bias and retrieval bias

### BM25/Sparse Retrieval for Non-English

**BM25 is fundamentally limited for multilingual retrieval:**
- BM25 is keyword-based and language-specific. A German query will not match English documents on keyword overlap.
- Learned sparse models (SPLADE) improve on BM25 but progress beyond English "remains fragmented."
- BGE-M3 combines dense, sparse, and multi-vector retrieval under one model, but its sparse component "underperforms and lacks cross-lingual support."

**Practical approach:**
- For **cross-language retrieval** (query in language A, documents in language B): rely on multilingual dense embeddings. Sparse retrieval will not help here.
- For **same-language retrieval** in non-English: use language-specific BM25 tokenizers/analyzers. Persist the language tag (ISO 639-1) as metadata on each document for early filtering.
- For **hybrid search with non-English queries**: use dense embeddings for the semantic component, and either skip sparse entirely for cross-lingual scenarios or use language-matched BM25 when query and document languages match.

### Voyage Model Specifics

- **voyage-3-large**: State-of-the-art across 8 domains including multilingual (62 datasets, 26 languages). Supports Matryoshka embeddings and int8/binary quantization.
- **voyage-multilingual-2**: Dedicated multilingual model, outperforms OpenAI v3 large and Cohere multilingual v3 across French, German, Japanese, Spanish, Korean, and more.
- Both models handle cross-language queries natively -- a German query will retrieve semantically relevant English documents without translation.

### Actionable Recommendations

1. **Index documents in their original language** -- do not pre-translate your corpus
2. **Embed with a multilingual model** (voyage-3-large or voyage-multilingual-2)
3. **Store language metadata** on every chunk for optional filtering
4. **Skip sparse/BM25 for cross-language retrieval scenarios**
5. **Add query translation as a fallback** only for low-resource languages where embedding quality degrades
6. **Use character 3-gram recall instead of token-F1** for evaluation in multilingual settings (handles transliteration better)

---

## 4. Reranking Best Practices

### Text Length for Rerankers

**Modern rerankers handle varying lengths well, but there are practical guidelines:**

| Model | Max Context | Optimal Input | Notes |
|-------|-------------|---------------|-------|
| Cohere Rerank v4 | 32,768 tokens | Chunks up to ~2000 tokens | Splits into 32,764-token chunks internally |
| Cohere Rerank v3.5 | 4,096 tokens | Chunks up to ~500 tokens | Truncates at limit |
| Jina Reranker v2 | 1,024 tokens | Chunks 256-512 tokens | Uses sliding window for longer inputs |
| Qwen3-Reranker | 32,000 tokens | Flexible | Supports 100+ languages |
| Voyage Rerank 2.5 | ~4,000 tokens | Chunks 256-512 tokens | Fast (595ms avg) |

**Key principle:** Feed the reranker chunks that are large enough to contain relevant context but small enough that the relevant signal is not diluted. 256-512 tokens is the sweet spot for most chunk-based RAG systems. If using parent-child chunking, rerank on the child chunks (small, precise) but return the parent chunks (large, contextual) to the LLM.

### Cross-Encoder vs LLM Rerankers

| Dimension | Cross-Encoder | LLM-Based (Pointwise) | LLM-Based (Listwise) |
|-----------|---------------|----------------------|---------------------|
| Accuracy (NDCG@10) | 0.85+ | 0.70+ | 0.90+ |
| Latency | 200ms-2s | 1-3s | 3-8s |
| Cost per 1M tokens | $0.025-$0.05 | $0.50-$5.00 | $0.50-$5.00 |
| Best for | Production search, RAG | Prototyping, specialized domains | Maximum quality, offline |

**Recommendation:** Use cross-encoder rerankers for production RAG. LLM-based listwise reranking can achieve 5-8% higher accuracy but adds 4-6 seconds of latency, which exceeds user tolerance thresholds (users abandon after 3 seconds). Reserve LLM reranking for offline evaluation or batch processing.

**Top cross-encoder rerankers as of early 2026:**
1. ZeroEntropy zerank-2 (ELO #1 on leaderboard)
2. Cohere Rerank 4 Pro (ELO #2, 32K context, strong on business/finance)
3. Voyage Rerank 2.5 (fast, 595ms, strong general-purpose)
4. Jina Reranker v2 (open-source, self-hostable, multilingual)

### Optimal Candidate Pool Size

**The sweet spot is 50-75 candidates for most applications.**

| Use Case | Recommended Pool | Rationale |
|----------|-----------------|-----------|
| Q&A systems | 25-50 | Answer completeness focus |
| LLM chat | 50 | Speed-sensitive |
| General RAG | 50-75 | Quality/speed balance |
| Financial/regulatory | 100-150 | Compliance requires thoroughness |
| Comprehensive search | 100-200 | Recall-critical |

**Beyond 100 candidates, quality improvements plateau while costs and latency increase linearly.** Databricks testing shows reranking can improve retrieval quality by up to 48%, and reranked results reduce LLM hallucinations by 35%.

### Single-Stage vs Cascade Reranking

**Cascade (multi-stage) reranking is the architecture of choice for high-quality production systems.**

The GAHR-MSR framework demonstrates a practical cascade:
1. **Phase 1**: Hybrid retrieval (dense + sparse with RRF) produces 100 candidates
2. **Phase 2**: Lightweight reranker prunes to 20 candidates (cheap, fast)
3. **Phase 3**: Heavy cross-encoder (e.g., ColBERT) produces final top 5

This achieves 0.859 NDCG@10 at 215ms average latency.

**Three-tier hybrid pipeline (ZeroEntropy recommendation):**
1. BM25 retrieves 200 candidates
2. Dense retrieval adds 100 semantically similar documents
3. Reranking processes combined 300 candidates to surface optimal 10

**When single-stage reranking suffices:**
- Small corpus (< 10K documents)
- Low-latency requirements (< 500ms total)
- Simple query patterns without ambiguity

### Passage Length: Full Documents vs Chunks

**Rerank on chunks, return context-enriched chunks or parent documents.**

- Rerankers perform best on focused passages (256-512 tokens) where the relevance signal is concentrated
- If you feed full documents (2000+ tokens), the relevant sentence may be diluted by surrounding noise
- Use parent-child chunking: rerank small child chunks, then expand to parent context for the LLM

---

## 5. Chunk Design for Transcripts/Long Documents

### Chunk Sizes and Overlap

**Production-validated defaults (re-validated February 2026):**

| Parameter | Recommended | Range | Notes |
|-----------|-------------|-------|-------|
| Chunk size | 400-512 tokens | 256-1024 | Factoid queries favor smaller; analytical favor larger |
| Overlap | 50-100 tokens (10-20%) | 0-20% | Prevents boundary information loss |
| Splitter | RecursiveCharacterTextSplitter | -- | With separators `["\n\n", "\n", ". ", " ", ""]` |

**Query-type-specific sizing:**
- **Factoid queries** (names, dates, facts): 256-512 tokens for precise matching
- **Analytical queries** (explanations, comparisons): 1024+ tokens for more context
- **Mixed workloads**: 400-512 tokens as balanced default

**Important finding (NAACL 2025):** Fixed 200-word chunks match or beat semantic chunking across retrieval and answer generation tasks, suggesting that computational costs of semantic chunking "aren't justified by consistent gains." This counters the hype around semantic chunking.

**Context cliff:** A January 2026 systematic analysis identified that response quality drops significantly around 2,500 tokens per chunk, establishing a practical upper bound.

### Full Chunk Text vs Truncated Previews

**Store full chunk text in the vector database payload. Truncated previews are a false economy.**

- Rerankers need full text to score accurately
- LLMs need full context for generation
- Storage is cheap compared to retrieval quality
- If storage is genuinely constrained, store full text in an external store and only the embedding + metadata in the vector DB, with a lookup key

### Parent-Child Chunking

**This is the most impactful chunking strategy for complex retrieval and the recommended approach for long documents.**

Architecture:
- **Child chunks** (100-500 tokens): Small, precise, used for retrieval matching
- **Parent chunks** (500-2000 tokens): Larger context windows, used for LLM generation
- **Linking**: Each child stores a reference to its parent document/chunk ID

Workflow:
1. Index child chunks in the vector database
2. Retrieve top-K child chunks via hybrid search
3. Rerank the child chunks
4. Expand to parent chunks (deduplicated) for the LLM context
5. Pass parent chunks to generation

**LangChain's ParentDocumentRetriever** implements this pattern natively. The approach is particularly effective for transcripts where a relevant 2-second quote needs 30 seconds of surrounding context to be intelligible.

### The "Relevant Sentence Buried in a Chunk" Problem

This is the core retrieval quality problem. Multiple solutions:

1. **Smaller chunks** (256 tokens): Increases the signal-to-noise ratio per chunk but loses context
2. **Parent-child chunking**: Best of both worlds (small for matching, large for context)
3. **Anthropic's Contextual Retrieval**: Prepend a 50-100 token context summary to each chunk before embedding. Reduced retrieval failure by 35% with embeddings alone, 49% combined with BM25, and 67% with reranking added. Cost: $1.02 per million document tokens at ingestion time (one-time).
4. **Late chunking** (Jina): Embed the full document first, then pool embeddings into chunk-sized segments. Preserves cross-chunk references (e.g., "the city" resolving to "Berlin" mentioned earlier). Requires long-context embedding models (jina-embeddings-v2: 8,192 tokens).
5. **Sentence-window retrieval**: Index individual sentences but retrieve a window of N surrounding sentences.

### Late Chunking vs Traditional Chunking

**Late chunking is architecturally superior but has practical constraints:**

| Aspect | Traditional | Late Chunking |
|--------|-------------|---------------|
| Process | Chunk first, embed each chunk | Embed full document, then chunk embeddings |
| Context awareness | None (each chunk is isolated) | Full (each chunk "sees" the whole document) |
| Anaphora resolution | Broken ("it", "the city" lose referent) | Preserved |
| Model requirement | Any embedding model | Long-context model (8K+ tokens) |
| Document size limit | None | Model's context window (8,192 tokens for Jina v2) |
| Implementation complexity | Standard | ~30 lines of code change to pooling step |
| Performance | Baseline | Superior across retrieval benchmarks, gains increase with document length |

**Recommendation for transcripts:** Late chunking is especially valuable for transcripts where speakers use pronouns and references to earlier statements. If your embedding model supports 8K+ tokens, use late chunking. For documents exceeding the context window, fall back to traditional chunking with Anthropic's Contextual Retrieval enrichment.

---

## 6. Query Understanding and Expansion

### Query Decomposition

**When to decompose:**
- Multi-hop questions: "What was the GDP of the country where the Parthenon is located in 2023?"
- Comparative questions: "How does X compare to Y in terms of Z?"
- Complex analytical queries requiring information from multiple chunks

**When NOT to decompose:**
- Simple factoid queries: "Where is the Parthenon?"
- Queries that map directly to a single chunk
- When latency budget is tight (decomposition adds an LLM call)

**How many sub-queries:** 2-4 is the practical range. More than 4 sub-queries typically introduces noise and redundant retrieval.

**Implementation (Haystack pattern):**
1. LLM decomposes the query into sub-questions
2. Each sub-question is retrieved independently
3. Results are merged (RRF across sub-query result sets)
4. Merged results are reranked
5. Final context is passed to generation

### HyDE (Hypothetical Document Embeddings)

**HyDE is powerful but situational. It is NOT a universal improvement.**

**When HyDE helps significantly:**
- Out-of-domain queries where the embedding model lacks domain knowledge
- Queries phrased very differently from source documents
- Abstract/theoretical questions where keywords don't match indexed content
- Low-resource or specialized domains

**When HyDE hurts or is unnecessary:**
- Well-specified, fact-bound domains (personal data, structured records)
- When the LLM hallucinating a "hypothetical answer" leads retrieval astray
- Small LLMs: 25-60% latency increase with high hallucination risk on factual queries

**Mitigation strategies:**
- Use HyDE **conditionally** -- only when initial retrieval confidence is low
- Apply cross-encoder reranking **after** HyDE-based retrieval to filter hallucination-induced noise
- Use strict guardrails on the hypothetical generation prompt

### Multi-Query Retrieval

**The most reliable query expansion technique for production systems.**

Process:
1. Generate 3-5 alternative phrasings of the user's query using an LLM
2. Run retrieval for each variant
3. Merge results using RRF
4. Rerank the merged set

**This explores the "intent space" of the query** -- each variant captures a different interpretation. It is more robust than HyDE because it does not generate hypothetical answers, just alternative questions.

**RAGFusion (Weaviate)** implements this pattern with RRF-based merging of multi-query results.

### Handling Theory/Hypothesis Questions

These are the hardest for RAG because exact keywords rarely match indexed content.

**Recommended approach (layered):**
1. **Multi-query**: Generate several phrasings including more concrete/specific versions
2. **HyDE**: Generate a hypothetical answer to bridge the vocabulary gap
3. **Semantic search emphasis**: Increase alpha toward dense (0.8+), reduce sparse weight
4. **Broader top-K**: Retrieve more candidates (100+) since precision will be lower
5. **LLM-based reranking**: For these high-value queries, the 5-8% accuracy gain from LLM reranking may justify the latency

### Production Maturity of Techniques

| Technique | Maturity | Typical Improvement | Latency Cost | When to Use |
|-----------|----------|-------------------|--------------|-------------|
| Multi-query | High | 10-20% recall gain | +500ms-1s (1 LLM call) | Most queries |
| Query rewriting | High | 5-15% | +200-500ms | Conversational/ambiguous queries |
| HyDE | Medium | 15-30% on OOD, negative on factual | +500ms-2s | Out-of-domain only |
| Query decomposition | Medium | 20-40% on multi-hop | +1-3s (multiple retrievals) | Complex multi-part questions |
| Feedback expansion (RM3/Rocchio) | High | 5-10% | Minimal | After initial retrieval |

---

## 7. Adaptive Retrieval

### Dynamic Result Count

**Yes, the number of retrieved results should be dynamic. Fixed top-K is suboptimal.**

**Production approaches:**

1. **DynamicRAG**: Trains a dynamic reranker via reinforcement learning to determine both ranking AND the number k of documents per query. Reward signal = LLM answer quality.

2. **Cluster-based Adaptive Retrieval (CAR)**: Analyzes clustering patterns of query-document similarity distances to determine the optimal k. When similarities form a tight cluster, fewer documents are needed; when spread out, more are needed.

3. **Adaptive-RAG (query complexity classifier)**: Routes queries to three tiers:
   - **Simple (A)**: No retrieval needed -- answer from LLM parametric memory
   - **Moderate (B)**: Single-step RAG with standard top-K
   - **Complex (C)**: Multi-step iterative retrieval with expanded K

### How Production Systems Decide How Many Results to Fetch

**Practical implementation patterns (ranked by complexity):**

1. **Score-gap detection** (simplest):
   - After reranking, look for a significant drop in scores between consecutive results
   - If score[i] - score[i+1] > gap_threshold, cut off at i
   - Works because reranker scores tend to show clear "elbows"

2. **Confidence-based cutoff**:
   - Set a minimum reranker score threshold (calibrated per Cohere's 30-50 query method)
   - Return all results above threshold, with a minimum of 1 and maximum of K

3. **Query complexity classification** (moderate complexity):
   - Train a lightweight classifier (or use LLM) to categorize query complexity
   - Map complexity to retrieval depth: simple=5, moderate=10, complex=20

4. **Reinforcement learning** (DynamicRAG, highest complexity):
   - Train the reranker to output a "stop" signal
   - Reward = downstream answer quality

### Retrieval Confidence Estimation

**How to know if you found enough:**

1. **Score distribution analysis**: If the top reranker score is below your calibrated threshold, retrieval confidence is low.

2. **Score entropy**: High entropy (scores are spread evenly) = low confidence. Low entropy (clear winner) = high confidence.

3. **Self-consistency check**: Generate an answer, then check if the cited evidence actually supports it (Self-RAG reflection tokens: `[ISSUP]` for "is supported").

4. **Peek technique**: Generate first 32 tokens of the answer, measure softmax probability. Low probability = low confidence = retrieve more.

### Iterative Retrieval

**The pattern: retrieve, evaluate, retrieve more if needed.**

**FAIR-RAG framework** (2025):
1. Initial retrieval
2. Structured Evidence Assessment (SEA) module evaluates sufficiency
3. If insufficient, refine the query and retrieve again
4. Repeat until evidence threshold is met or max iterations reached

**Auto-RAG** (2025):
- Multi-turn retrieval dialogue using chain-of-thought reasoning
- Trigger words ("However," "no information") detected to signal need for more retrieval
- Iterates until answer confidence is sufficient

**Practical recommendation:** For most production systems, a simple two-pass approach works:
1. First pass: Standard retrieval + reranking
2. If top reranker score < threshold: rewrite query (using LLM) and retrieve again
3. Merge results from both passes
4. If still below threshold: return "insufficient evidence" response

---

## 8. Off-topic / No-result Handling

### Distinguishing "No Relevant Results" from "Off-topic Question"

These are fundamentally different failure modes requiring different handling:

| Failure Mode | Cause | Detection | Response |
|-------------|-------|-----------|----------|
| Off-topic | Query is outside the knowledge base scope entirely | Pre-retrieval classification | "This topic is outside my knowledge area" |
| No relevant results | Query is in-scope but no matching content exists | Post-retrieval score analysis | "I don't have specific information about X" |
| Low-confidence results | Some matches found but uncertain relevance | Reranker score below threshold | "I found some related information but cannot answer confidently" |

### Off-topic Detection: Before or After Retrieval?

**Both. Use a lightweight pre-retrieval check, with post-retrieval validation.**

**Pre-retrieval (guardrails):**
- Topic classifier that checks if the query falls within allowed domains
- Can be as simple as a list of allowed topics + embedding similarity to topic exemplars
- AT-RAG uses BERTopic to dynamically assign topics to queries
- OpenAI's Guardrails framework includes configurable off-topic filters that run before the model call
- Cost: minimal (lightweight classifier, no retrieval needed)

**Post-retrieval (score-based):**
- If all reranker scores are below the calibrated minimum threshold, the query is likely off-topic or unanswerable
- Use the score distribution: if the best score is significantly below the domain average, flag as potentially off-topic

**Implementation pattern:**

```
# Stage 1: Pre-retrieval topic check
if not topic_classifier.is_in_scope(query):
    return "This question is outside my knowledge area. I can help with [topics]."

# Stage 2: Retrieve and rerank
results = retrieve_and_rerank(query)

# Stage 3: Post-retrieval confidence check
if len(results) == 0 or results[0].score < calibrated_minimum:
    return "I don't have enough information to answer this question confidently."

# Stage 4: Generate with confidence indicator
if results[0].score < calibrated_borderline:
    return generate_with_caveat(query, results)  # "Based on limited evidence..."
else:
    return generate(query, results)
```

### Low-Confidence Result Handling

**Best practices from production systems:**

1. **Do not generate when evidence is insufficient.** The #1 source of RAG hallucinations is forcing generation on low-quality retrieval results.

2. **Offer graceful alternatives:**
   - Suggest related topics that ARE in the knowledge base
   - Ask the user to rephrase or provide more specific details
   - Provide what you CAN say with confidence, clearly marking uncertainty

3. **Log "no answer" queries.** These are a goldmine for corpus expansion -- they tell you exactly what users want that you don't have.

4. **Set explicit confidence thresholds per use case:**
   - Medical/legal: High threshold, prefer "I don't know" over uncertain answers
   - Casual chat: Lower threshold, hedged answers acceptable
   - Customer support: Medium threshold, escalate to human when uncertain

5. **Human-in-the-loop routing:** When confidence falls below threshold, route to human review rather than generating a potentially wrong answer.

---

## Summary: Recommended Production Architecture

```
User Query
    |
    v
[1. Pre-retrieval Guardrails]
    - Off-topic detection (topic classifier)
    - Query complexity classification (A/B/C)
    |
    v
[2. Query Processing]
    - For complex queries: decompose into sub-queries
    - For ambiguous queries: generate 3-5 multi-query variants
    - For OOD queries: apply HyDE conditionally
    |
    v
[3. Hybrid Retrieval]
    - Dense prefetch: 100 candidates (multilingual embedding model)
    - Sparse prefetch: 100 candidates (BM25, skip for cross-lingual)
    - Fusion: RRF (not linear combination)
    |
    v
[4. Cascade Reranking]
    - Stage 1: Lightweight reranker, prune to 20-50 candidates
    - Stage 2: Cross-encoder reranker, select top 5-10
    - Apply adaptive score threshold (not fixed)
    |
    v
[5. Confidence Assessment]
    - Check top reranker score against calibrated threshold
    - If below threshold: rewrite query and retry (one iteration)
    - If still below: return "insufficient evidence"
    |
    v
[6. Context Assembly]
    - Expand child chunks to parent chunks (if using parent-child)
    - Deduplicate overlapping content
    - Order by relevance for positional bias mitigation
    |
    v
[7. Generation with Grounding]
    - Pass assembled context to LLM
    - Include confidence level in system prompt
    - Request citations to specific chunks
```

---

## Key Citations and Sources

### Relevance Scoring
- Cohere Reranking Best Practices: https://docs.cohere.com/docs/reranking-best-practices
- DynamicRAG (adaptive k selection): https://arxiv.org/html/2505.07233
- Confidence-Calibrated RAG (Ozaki et al., 2025)
- MAIN-RAG (Multi-Agent Filtering): https://aclanthology.org/2025.acl-long.131.pdf

### Hybrid Search
- Qdrant Hybrid Search: https://qdrant.tech/articles/hybrid-search/
- Assembled Engineering Blog on RRF: https://www.assembled.com/blog/better-rag-results-with-reciprocal-rank-fusion-and-hybrid-search
- Azure AI Search Hybrid Scoring: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
- DAT (Dynamic Alpha Tuning): https://arxiv.org/abs/2503.23013
- Elasticsearch Weighted RRF: https://www.elastic.co/search-labs/blog/weighted-reciprocal-rank-fusion-rrf
- OpenSearch RRF: https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/

### Multilingual RAG
- Voyage-3-large announcement: https://blog.voyageai.com/2025/01/07/voyage-3-large/
- Voyage-multilingual-2: https://blog.voyageai.com/2024/06/10/voyage-multilingual-2-multilingual-embedding-model/
- M4-RAG (Massive-Scale Multilingual): https://arxiv.org/abs/2512.05959
- Multilingual RAG for Knowledge-Intensive Tasks: https://arxiv.org/abs/2504.03616
- NVIDIA Multilingual IR: https://developer.nvidia.com/blog/develop-multilingual-and-cross-lingual-information-retrieval-systems-with-efficient-data-storage/
- Milco (Multilingual Sparse Retrieval): https://arxiv.org/html/2510.00671
- BGE-M3: https://johal.in/bge-m3-multilingual-massive-embeddings-for-global-rag-systems-2025-3/

### Reranking
- ZeroEntropy Reranker Guide: https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025
- Cohere Rerank v4: https://docs.cohere.com/changelog/rerank-v4.0
- Pinecone Two-Stage Retrieval: https://www.pinecone.io/learn/series/rag/rerankers/
- NVIDIA Reranking Microservice: https://developer.nvidia.com/blog/how-using-a-reranking-microservice-can-improve-accuracy-and-costs-of-information-retrieval/
- GAHR-MSR Framework: https://dev.to/lucash_ribeiro_dev/graph-augmented-hybrid-retrieval-and-multi-stage-re-ranking-a-framework-for-high-fidelity-chunk-50ca
- Agentset Reranker Leaderboard: https://agentset.ai/rerankers
- Jina Reranker v2: https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual

### Chunking
- Firecrawl Chunking Strategies: https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- Weaviate Chunking Guide: https://weaviate.io/blog/chunking-strategies-for-rag
- NVIDIA Chunking Research: https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/
- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- Jina Late Chunking: https://jina.ai/news/late-chunking-in-long-context-embedding-models/
- Late Chunking Paper: https://arxiv.org/pdf/2409.04701
- Reconstructing Context (NAACL 2025 chunking comparison): https://arxiv.org/abs/2504.19754
- Databricks Chunking Guide: https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089

### Query Understanding
- Haystack Query Decomposition: https://haystack.deepset.ai/cookbook/query_decomposition
- HyDE Overview: https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde
- Weaviate RAGFusion: https://deepwiki.com/weaviate/retrieve-dspy/4.4-multi-query-generation-and-ragfusion
- Query Optimization Survey: https://arxiv.org/html/2412.17558
- Zilliz HyDE Guide: https://zilliz.com/learn/improve-rag-and-information-retrieval-with-hyde-hypothetical-document-embeddings

### Adaptive Retrieval
- Teaching Models When to Retrieve: https://blog.reachsumit.com/posts/2025/10/learning-to-retrieve/
- Adaptive Iterative Retrieval: https://www.sciencedirect.com/science/article/pii/S0925231225029443
- FAIR-RAG: https://arxiv.org/html/2510.22344v1
- Cluster-based Adaptive Retrieval: https://arxiv.org/abs/2511.14769
- DynamicRAG: https://arxiv.org/html/2505.07233
- Self-RAG: https://www.letsdatascience.com/blog/agentic-rag-self-correcting-retrieval
- Adaptive-RAG: https://www.meilisearch.com/blog/adaptive-rag
- DeepRAG (MDP-based): https://blog.reachsumit.com/posts/2025/10/learning-to-retrieve/

### Off-topic / No-result Handling
- AT-RAG (Topic Filtering): https://arxiv.org/html/2410.12886v1
- Off-Topic Guardrails: https://arxiv.org/html/2411.12946
- RAG Guardrails Guide: https://app.ailog.fr/en/blog/guides/guardrails-rag
- 23 RAG Pitfalls: https://www.nb-data.com/p/23-rag-pitfalls-and-how-to-fix-them
- Confidence in RAG (Medical Domain): https://arxiv.org/abs/2412.20309
