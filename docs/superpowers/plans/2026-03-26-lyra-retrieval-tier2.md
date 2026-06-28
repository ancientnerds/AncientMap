# Lyra Retrieval Pipeline — Tier 2 Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve retrieval recall for theory/hypothesis questions via multi-query expansion, and make reranking query-type-aware.

**Architecture:** Task 1 extends the existing `_decompose_query` into a multi-query expander that always runs (generating 3 query variants for any non-trivial query). Task 2 makes the Voyage rerank instruction dynamic based on query type. Both changes are in the retrieval layer only — no frontend or synthesis changes.

**Tech Stack:** Python, Anthropic Haiku (for query expansion), Voyage AI rerank-2.5-lite

**Note on Tier 2 item "Move off-topic detection pre-retrieval":** This is deprioritized. The Tier 1 off-topic fix (skip detection when tools already proved relevance + language-aware prompts) handles the real failure mode. A pre-retrieval classifier would save ~3s on genuinely off-topic queries, but those are rare and the cost doesn't justify a new classifier. Skipped.

---

## File Map

| File | Responsibility | Tasks |
|---|---|---|
| `api/services/lyra_tools.py` | `_decompose_query` → `_expand_query`, rerank instruction logic | 1, 2 |
| `api/services/lyra_agent.py` | Trigger expansion for all non-trivial queries, pass query type to `_hybrid_search` | 1, 2 |

---

### Task 1: Multi-Query Expansion (Replace Decomposition)

Currently `_decompose_query` only fires for conjunction/vague queries. Most queries — including theory questions like "polygonal masonry casting theories" — are sent as a single query to Qdrant. SOTA: generate 3 query variants to explore the "intent space", search all variants, merge results via dedup. This captures different phrasings that match different indexed content.

The key insight: we already have the `_decompose_query` LLM call. Instead of decomposing into sub-topics, we repurpose it to generate 3 phrasings of the same question. The infrastructure (parallel search, dedup) already exists.

**Files:**
- Modify: `api/services/lyra_tools.py:46-58` — replace `_DECOMPOSE_SYSTEM` and `_DECOMPOSE_VAGUE_SYSTEM` prompts
- Modify: `api/services/lyra_tools.py:98-139` — rename `_decompose_query` to `_expand_query`, update prompt selection
- Modify: `api/services/lyra_agent.py:1321-1329` — always use expansion for non-local backend, remove conjunction check

- [ ] **Step 1: Replace decompose system prompts with multi-query expansion prompts**

In `api/services/lyra_tools.py`, find and replace the two system prompts (lines 46-58):

```python
_DECOMPOSE_SYSTEM = (
    "You are a search query decomposer. Given a user question about archaeology, "
    "split it into 1-3 independent search queries. If the question is already "
    "focused on a single topic, return it unchanged as a single-element array. "
    "Never add topics the user didn't ask about."
)

_DECOMPOSE_VAGUE_SYSTEM = (
    "You are a search query decomposer. The user asked a vague/exploratory question "
    "about archaeology. Generate 2-3 specific, searchable sub-queries that would "
    "surface genuinely interesting results. Focus on: recent discoveries, unusual "
    "findings, controversial debates. Return as a JSON array of query strings."
)
```

Replace with:

```python
_EXPAND_SYSTEM = (
    "You are a search query expander for an archaeology knowledge base. "
    "Given a user question, generate 2-3 alternative phrasings that would match "
    "different relevant documents. Include:\n"
    "1. The original question (or a cleaned-up version)\n"
    "2. A rephrasing using synonyms or related terms\n"
    "3. A more specific or concrete version if applicable\n"
    "Always keep all variants about the SAME topic — never introduce new topics. "
    "For non-English queries, generate English variants (the database is in English). "
    "Return as a JSON array of query strings."
)

_EXPAND_VAGUE_SYSTEM = (
    "You are a search query expander for an archaeology knowledge base. "
    "The user asked a vague/exploratory question. Generate 2-3 specific, "
    "searchable query variants that would surface interesting results. "
    "Focus on: recent discoveries, unusual findings, controversial debates. "
    "For non-English queries, generate English variants (the database is in English). "
    "Return as a JSON array of query strings."
)
```

- [ ] **Step 2: Rename `_decompose_query` to `_expand_query` and update prompt references**

Find the function definition (line 98):

```python
async def _decompose_query(query: str, *, vague: bool = False) -> list[str]:
    """Split complex queries into 1-3 independent search sub-queries.

    Uses Haiku with a tiny prompt. Returns the original query unchanged
    for simple/focused questions (no extra cost).

    When vague=True, uses an exploratory prompt that generates concrete
    sub-queries from vague questions like "anything interesting lately?".
    """
```

Replace with:

```python
async def _expand_query(query: str, *, vague: bool = False) -> list[str]:
    """Generate 2-3 query variants to explore different phrasings.

    Uses Haiku with a tiny prompt. Always returns the original query
    as the first variant, plus 1-2 alternative phrasings.

    For non-English queries, generates English variants since the
    database content is in English. This also provides BM25 matches
    that the original non-English query would miss.

    When vague=True, generates concrete sub-queries from exploratory questions.
    """
```

Inside the same function, find (line 117):

```python
            system=_DECOMPOSE_VAGUE_SYSTEM if vague else _DECOMPOSE_SYSTEM,
```

Replace with:

```python
            system=_EXPAND_VAGUE_SYSTEM if vague else _EXPAND_SYSTEM,
```

- [ ] **Step 3: Update the caller in `lyra_agent.py` to always expand**

In `api/services/lyra_agent.py`, find the decomposition trigger logic (lines 1321-1329):

```python
        # Skip decomposition for simple queries — saves 1-3s + tokens.
        # Decompose when conjunctions/comparisons suggest multiple sub-topics,
        # OR when the query is vague/exploratory and needs expansion.
        _needs_decomp = any(
            w in message.lower()
            for w in (" and ", " or ", " vs ", " versus ", " compare", " compared to ")
        )
        _is_vague = _is_vague_query(message)
        use_decomposition = ctx.backend_type != "local" and (_needs_decomp or _is_vague)
```

Replace with:

```python
        # Multi-query expansion: generate 2-3 query variants to explore
        # different phrasings. Always enabled for cloud backend — the LLM call
        # costs ~200 tokens and runs in parallel with filter extraction.
        # Skipped for local backend (no Anthropic API key).
        _is_vague = _is_vague_query(message)
        use_expansion = ctx.backend_type != "local"
```

- [ ] **Step 4: Update all references to the old variable names**

In the same file, replace every occurrence of `use_decomposition` with `use_expansion`, and every occurrence of `_decompose_query` with `_expand_query`. There are several spots:

Find (around line 1352):
```python
        if use_decomposition and use_filter_extraction:
            decomp_raw, filter_raw = await asyncio.gather(
                _decompose_query(message, vague=_is_vague),
```
Replace with:
```python
        if use_expansion and use_filter_extraction:
            decomp_raw, filter_raw = await asyncio.gather(
                _expand_query(message, vague=_is_vague),
```

Find (around line 1367):
```python
        elif use_decomposition:
            try:
                sub_queries = await _decompose_query(message, vague=_is_vague)
```
Replace with:
```python
        elif use_expansion:
            try:
                sub_queries = await _expand_query(message, vague=_is_vague)
```

Also update the import at the top of `lyra_agent.py`. Find:
```python
    _decompose_query,
```
Replace with:
```python
    _expand_query,
```

And update the `_is_vague_query` import — it stays unchanged, still used for the `vague` flag.

- [ ] **Step 5: Verify with ruff**

Run: `python -m ruff check api/services/lyra_tools.py api/services/lyra_agent.py`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add api/services/lyra_tools.py api/services/lyra_agent.py
git commit -m "feat: multi-query expansion replaces decomposition for broader retrieval recall"
```

---

### Task 2: Query-Type-Aware Rerank Instructions

The Voyage rerank-2.5-lite `instruction` parameter boosts domain-specific accuracy by +8-11%. Currently, `_RERANK_INSTRUCTIONS` are static per-collection. For theory/hypothesis questions, the reranker should prioritize speculative discussions and alternative explanations rather than factual site data.

**Files:**
- Modify: `api/services/lyra_tools.py:690-716, 880-892` — add theory-aware instruction variant, pass query type to reranker

- [ ] **Step 1: Add theory detection and dynamic instruction selection**

In `api/services/lyra_tools.py`, find the `_RERANK_INSTRUCTIONS` dict (line 690). Add this right after it (after line 716, before the `_EN_STOPWORDS`):

```python
_THEORY_RERANK_INSTRUCTIONS = {
    "sites": (
        "Prioritize archaeological sites associated with construction theories, "
        "alternative building methods, or debated construction techniques. "
        "Rank sites with documented engineering mysteries or contested origins higher."
    ),
    "news": (
        "Prioritize news items discussing alternative theories, construction methods, "
        "fringe hypotheses, or debates about ancient techniques. Rank items with "
        "specific claims about how things were built higher than general discovery news."
    ),
    "transcripts": (
        "Prioritize transcript passages that discuss theories, hypotheses, alternative "
        "explanations, or debates about ancient construction, materials, or techniques. "
        "Rank passages with specific arguments, evidence discussion, or expert opinions "
        "higher than passing mentions."
    ),
    "articles": (
        "Prioritize article sections covering theories, debates, alternative explanations, "
        "or construction method analysis. Rank sections with substantive argumentation higher."
    ),
    "empires": _RERANK_INSTRUCTIONS["empires"],
}

_THEORY_KEYWORDS = frozenset({
    "theory", "theories", "hypothesis", "hypotheses", "how", "why",
    "built", "build", "construct", "construction", "method", "technique",
    "cast", "casting", "carved", "carving", "geopolymer", "concrete",
    "transport", "moved", "lifted", "fringe", "alternative", "mystery",
    "unexplained", "debate", "controversial", "impossible", "advanced",
    "lost", "forgotten", "ancient technology", "precision",
})


def _is_theory_query(query: str) -> bool:
    """Detect theory/hypothesis questions that benefit from theory-aware reranking."""
    words = set(query.lower().split())
    return len(words & _THEORY_KEYWORDS) >= 2
```

- [ ] **Step 2: Use dynamic instruction in `_hybrid_search_inner`**

In `_hybrid_search_inner`, find the rerank instruction selection (around line 888-892):

```python
    reranker = get_reranker(backend=backend)
    docs = [_format_payload_for_rerank(hit.payload) for hit in scored_points]
    instruction = _RERANK_INSTRUCTIONS.get(collection, "")
    rerank_query = f"{instruction}\n{query}" if instruction else query
```

Replace with:

```python
    reranker = get_reranker(backend=backend)
    docs = [_format_payload_for_rerank(hit.payload) for hit in scored_points]
    # Use theory-aware rerank instructions for hypothesis/construction questions
    instructions = (
        _THEORY_RERANK_INSTRUCTIONS if _is_theory_query(query) else _RERANK_INSTRUCTIONS
    )
    instruction = instructions.get(collection, "")
    rerank_query = f"{instruction}\n{query}" if instruction else query
```

- [ ] **Step 3: Verify with ruff**

Run: `python -m ruff check api/services/lyra_tools.py`
Expected: All checks passed

- [ ] **Step 4: Commit**

```bash
git add api/services/lyra_tools.py
git commit -m "feat: query-type-aware rerank instructions for theory/hypothesis questions"
```
