# Lyra Retrieval Pipeline — Tier 1 Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 highest-impact retrieval failures so Lyra reliably finds relevant content that exists in the database.

**Architecture:** All changes are in the retrieval layer (`_hybrid_search_inner`, `_auto_retrieve`) and the Qdrant indexer (`build_lyra_index.py`). No changes to the LLM generation, synthesis, or frontend. Each task is independently deployable — earlier tasks improve retrieval even without later ones.

**Tech Stack:** Python, Qdrant, Voyage AI rerank-2.5-lite, fastembed BM25

---

## File Map

| File | Responsibility | Tasks |
|---|---|---|
| `api/services/lyra_tools.py` | `_hybrid_search_inner` prefetch config, `_format_payload_for_rerank`, non-English BM25 skip | 1, 3, 5 |
| `api/services/lyra_agent.py` | `_auto_retrieve` context formatting, `_MIN_RELEVANCE` → relative threshold, articles gap | 2, 4 |
| `scripts/build_lyra_index.py` | Qdrant payload truncation (`text_preview`), `on_disk_payload` | 3 |

---

### Task 1: Raise Prefetch Pool from 3x to 10x

The Qdrant prefetch pool is `min(limit * 3, 20)` — e.g. only **9 candidates** for `limit=3` (transcripts). Industry standard is 50-100 per method. Candidates ranked below the prefetch limit are permanently eliminated before reranking can rescue them.

**Files:**
- Modify: `api/services/lyra_tools.py:808` (the `prefetch_limit` calculation)

- [ ] **Step 1: Change prefetch_limit from 3x to 10x, raise cap from 20 to 100**

In `api/services/lyra_tools.py`, find line 808:

```python
prefetch_limit = min(limit * 3, 20)
```

Replace with:

```python
# SOTA: 10:1 prefetch-to-final ratio, cap at 100 (was 3x, cap 20).
# Wider pool lets the reranker rescue relevant results that dense or BM25
# alone ranked lower. Cost: negligible — Qdrant prefetch is <10ms per method.
prefetch_limit = min(limit * 10, 100)
```

- [ ] **Step 2: Verify with ruff**

Run: `python -m ruff check api/services/lyra_tools.py`
Expected: All checks passed

- [ ] **Step 3: Commit**

```bash
git add api/services/lyra_tools.py
git commit -m "perf: raise Qdrant prefetch pool from 3x to 10x (retrieval recall)"
```

---

### Task 2: Replace Hard `_MIN_RELEVANCE = 0.5` with Relative Threshold

Voyage reranker scores cluster around 0.5 regardless of relevance. A hard cutoff of 0.5 randomly drops the best results for niche queries (theory questions, uncommon topics). Industry best practice: use relative threshold (% of top score) or score-gap detection. We use relative threshold because it's simplest and robust.

**Files:**
- Modify: `api/services/lyra_tools.py` — remove `_MIN_RELEVANCE` constant
- Modify: `api/services/lyra_agent.py:720-760` — replace hard threshold with relative threshold function

- [ ] **Step 1: Add `_apply_relevance_filter` helper in `lyra_agent.py`**

Add this function before `_auto_retrieve` (around line 625):

```python
def _apply_relevance_filter(
    results: list[dict],
    min_ratio: float = 0.4,
    min_absolute: float = 0.15,
) -> list[dict]:
    """Filter results using relative threshold — keeps results within min_ratio of the top score.

    SOTA: Voyage reranker scores are poorly calibrated for absolute thresholds
    (scores cluster around 0.5 regardless of relevance). Relative thresholds
    adapt per-query. A result scoring 0.3 when the top scores 0.35 is fine;
    a result scoring 0.3 when the top scores 0.9 is noise.

    Args:
        results: List of dicts with 'relevance' key (Voyage reranker score).
        min_ratio: Keep results scoring >= top_score * min_ratio. Default 0.4.
        min_absolute: Absolute floor — never include results below this. Default 0.15.
    """
    if not results:
        return results
    top_score = max(r.get("relevance", 0) for r in results)
    if top_score <= 0:
        return results
    threshold = max(top_score * min_ratio, min_absolute)
    return [r for r in results if r.get("relevance", 0) >= threshold]
```

- [ ] **Step 2: Replace all `_MIN_RELEVANCE` usage in `_auto_retrieve`**

In `api/services/lyra_agent.py`, find and replace the three filter blocks (lines 720-760).

Remove this line:
```python
    _MIN_RELEVANCE = 0.5
```

Replace the sites filter (line 725):
```python
    sites_for_context = [r for r in site_results if r.get("relevance", 1.0) >= _MIN_RELEVANCE]
```
with:
```python
    sites_for_context = _apply_relevance_filter(site_results)
```

Replace the news filter (line 746):
```python
    news_for_context = [r for r in news_results if r.get("relevance", 1.0) >= _MIN_RELEVANCE]
```
with:
```python
    news_for_context = _apply_relevance_filter(news_results)
```

Replace the transcript filter (line 760):
```python
    transcript_chunks = [r for r in transcript_chunks if r.get("relevance", 1.0) >= _MIN_RELEVANCE]
```
with:
```python
    transcript_chunks = _apply_relevance_filter(transcript_chunks)
```

- [ ] **Step 3: Verify with ruff**

Run: `python -m ruff check api/services/lyra_agent.py`
Expected: All checks passed

- [ ] **Step 4: Commit**

```bash
git add api/services/lyra_agent.py
git commit -m "fix: replace hard 0.5 relevance cutoff with adaptive relative threshold"
```

---

### Task 3: Store Full Chunk Text in Qdrant Payloads

The indexer stores only 200 chars of transcript text and 300 chars of article text in Qdrant payloads. The reranker (`_format_payload_for_rerank`) can only score what it sees. If the relevant sentence is at position 300 in a 2000-char chunk, the reranker never sees it and may score the chunk low.

SOTA: Store full chunk text in payload with `on_disk_payload: true`. Qdrant keeps payloads on disk, reads only for final results — negligible latency impact.

**Files:**
- Modify: `scripts/build_lyra_index.py:536` — transcript `text_preview` truncation
- Modify: `scripts/build_lyra_index.py:692` — article `text_preview` truncation
- Modify: `scripts/build_lyra_index.py:75-90` — add `on_disk_payload=True` to collection creation
- Modify: `api/services/lyra_tools.py:1143-1144` — raise `_format_payload_for_rerank` text limit

- [ ] **Step 1: Raise transcript `text_preview` from 200 to 2000 chars**

In `scripts/build_lyra_index.py`, find line 536:

```python
                        "text_preview": c["text"][:200],
```

Replace with:

```python
                        "text_preview": c["text"][:2000],
```

- [ ] **Step 2: Raise article `text_preview` from 300 to 2000 chars**

In `scripts/build_lyra_index.py`, find line 692:

```python
                        "text_preview": c["text"][:300],
```

Replace with:

```python
                        "text_preview": c["text"][:2000],
```

- [ ] **Step 3: Add `on_disk_payload=True` to collection creation**

In `scripts/build_lyra_index.py`, find the `ensure_collection` function (line 79):

```python
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
```

Replace with:

```python
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
            on_disk_payload=True,
        )
```

- [ ] **Step 4: Raise rerank text limit from 300 to 1500 chars**

In `api/services/lyra_tools.py`, find `_format_payload_for_rerank` (line 1143-1144):

```python
    if payload.get("text_preview"):
        parts.append(payload["text_preview"][:300])
```

Replace with:

```python
    if payload.get("text_preview"):
        parts.append(payload["text_preview"][:1500])
```

Also update the description/summary limits nearby (lines 1139-1142):

```python
    if payload.get("description"):
        parts.append(payload["description"][:300])
    if payload.get("summary"):
        parts.append(payload["summary"][:300])
```

Replace with:

```python
    if payload.get("description"):
        parts.append(payload["description"][:500])
    if payload.get("summary"):
        parts.append(payload["summary"][:500])
```

- [ ] **Step 5: Verify with ruff**

Run: `python -m ruff check scripts/build_lyra_index.py api/services/lyra_tools.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add scripts/build_lyra_index.py api/services/lyra_tools.py
git commit -m "perf: store full chunk text in Qdrant payloads for better reranking"
```

**NOTE:** After deploying, you must rebuild the Qdrant transcript and article indexes to populate the new full-text payloads:
```bash
python scripts/build_lyra_index.py --rebuild-transcripts --rebuild-articles
```
Existing data will continue to work (200/300-char previews) until rebuilt — the reranker just sees less text.

**NOTE:** `on_disk_payload=True` only applies to newly created collections (the `ensure_collection` function has an `if name not in collections` guard). To apply it to existing collections, either delete and recreate them (the `--rebuild-*` flags do this), or call `client.update_collection(collection_name=name, on_disk_payload=True)` separately.

---

### Task 4: Include Articles in Auto-Retrieve Context

`_auto_retrieve` fetches article chunks from Qdrant but never formats them into `context_parts`. The LLM never sees article content unless it explicitly calls the `search_articles` tool (which it rarely does). This is a ~10-line formatting gap.

**Files:**
- Modify: `api/services/lyra_agent.py:758-774` — add article formatting block after transcripts

- [ ] **Step 1: Add article formatting in `_auto_retrieve`**

In `api/services/lyra_agent.py`, find the transcript formatting block ending at line 774:

```python
        context_parts.append("### Transcript Passages\n" + "\n".join(lines))
```

Add immediately after that block (before the `if not context_parts:` check at line 776):

```python
    # Format article results (same pattern as transcripts)
    article_chunks = _apply_relevance_filter(article_chunks)
    if article_chunks:
        article_chunks = _semantic_dedup(article_chunks, text_key="text_preview")
        lines = []
        for r in article_chunks:
            title = r.get("title", "")
            aid = r.get("article_id", "")
            week = r.get("week_start", "")
            preview = r.get("text_preview", "")[:500]
            line = f'- **{title}** (article_id: {aid}, week: {week})'
            if preview:
                line += f"\n  > {preview}"
            lines.append(line)
        context_parts.append("### Weekly Articles\n" + "\n".join(lines))
```

- [ ] **Step 2: Verify with ruff**

Run: `python -m ruff check api/services/lyra_agent.py`
Expected: All checks passed

- [ ] **Step 3: Commit**

```bash
git add api/services/lyra_agent.py
git commit -m "fix: include article chunks in auto-retrieve context (were fetched but never formatted)"
```

---

### Task 5: Skip BM25 for Non-English Queries

BM25 is a keyword tokenizer. A German query produces German tokens that match nothing in the English-indexed documents. The dense embedding (Voyage-4) is multilingual and handles cross-language retrieval natively. When a non-English query is detected, skip the BM25 prefetch leg entirely — dense-only retrieval is better than dense + empty BM25 fused via RRF.

**Files:**
- Modify: `api/services/lyra_tools.py:744-835` — add language detection, conditionally skip BM25 prefetch

- [ ] **Step 1: Add `_is_likely_english` helper**

Add this function before `_hybrid_search_inner` in `api/services/lyra_tools.py` (around line 718):

```python
# English function words — present in virtually all English queries.
# ASCII heuristic fails for German/French (few accented chars) and
# English queries with Turkish site names (Göbekli Tepe).
_EN_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall",
    "i", "you", "he", "she", "it", "we", "they", "my", "your",
    "what", "which", "who", "whom", "where", "when", "why", "how",
    "that", "this", "these", "those", "there", "here",
    "about", "from", "with", "without", "between", "through",
    "any", "some", "all", "each", "every", "both", "few", "more",
    "other", "such", "only", "same", "than", "too", "very",
    "not", "no", "nor", "but", "or", "and", "if", "so",
    "of", "in", "to", "for", "on", "at", "by",
})


def _is_likely_english(text: str) -> bool:
    """Fast heuristic: returns True if text is likely English.

    Uses stopword presence — English text almost always contains common
    function words (the, is, are, what, about, etc.). More reliable than
    ASCII ratio for European languages sharing the Latin alphabet.
    """
    words = set(text.lower().split())
    if len(words) < 3:
        return True  # Too short to tell, assume English
    return bool(words & _EN_STOPWORDS)
```

- [ ] **Step 2: Skip BM25 prefetch when query is non-English**

In `_hybrid_search_inner`, find the prefetch construction (lines 809-818):

```python
    prefetch = []
    if dense_vec is not None:
        prefetch.append(
            models.Prefetch(
                query=dense_vec, using="dense", limit=prefetch_limit, filter=query_filter
            )
        )
    prefetch.append(
        models.Prefetch(query=sparse_vec, using="bm25", limit=prefetch_limit, filter=query_filter)
    )
```

Replace with:

```python
    prefetch = []
    if dense_vec is not None:
        prefetch.append(
            models.Prefetch(
                query=dense_vec, using="dense", limit=prefetch_limit, filter=query_filter
            )
        )
    # Skip BM25 for non-English queries — BM25 tokenizes keywords that won't match
    # English-indexed documents. Dense embedding (Voyage-4) is multilingual and
    # handles cross-language retrieval natively. Empty BM25 results dilute RRF fusion.
    if _is_likely_english(query):
        prefetch.append(
            models.Prefetch(query=sparse_vec, using="bm25", limit=prefetch_limit, filter=query_filter)
        )
```

- [ ] **Step 3: Handle dense-only query path**

The current code at lines 820-835 uses `FusionQuery` when dense is available. When BM25 is skipped and only dense exists, fusion is not needed — just query the dense vector directly.

Find:

```python
    if dense_vec is not None:
        results = client.query_points(
            collection_name=qdrant_collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=prefetch_limit,
        )
    else:
        # BM25-only fallback (embedding failed)
        results = client.query_points(
            collection_name=qdrant_collection,
            prefetch=prefetch,
            query=sparse_vec,
            using="bm25",
            limit=prefetch_limit,
        )
```

Replace with:

```python
    if len(prefetch) > 1:
        # Hybrid: dense + BM25 fused with RRF
        results = client.query_points(
            collection_name=qdrant_collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=prefetch_limit,
        )
    elif dense_vec is not None:
        # Dense-only (non-English query or BM25 skipped)
        results = client.query_points(
            collection_name=qdrant_collection,
            query=dense_vec,
            using="dense",
            limit=prefetch_limit,
            query_filter=query_filter,
        )
    else:
        # BM25-only fallback (embedding failed)
        results = client.query_points(
            collection_name=qdrant_collection,
            query=sparse_vec,
            using="bm25",
            limit=prefetch_limit,
            query_filter=query_filter,
        )
```

- [ ] **Step 4: Verify with ruff**

Run: `python -m ruff check api/services/lyra_tools.py`
Expected: All checks passed

- [ ] **Step 5: Commit**

```bash
git add api/services/lyra_tools.py
git commit -m "fix: skip BM25 for non-English queries to prevent empty sparse results diluting RRF"
```
