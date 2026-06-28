# Remove Ollama Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cleanly remove all Ollama/local LLM infrastructure from the codebase — backend classes, embeddings, Docker stack, env vars, and all `backend_type == "local"` conditional paths. Theo is intentionally left without a backend (Phase 2 will wire MiniMax M2.7).

**Architecture:** The codebase has two LLM backends: `AnthropicBackend` (cloud) and `OllamaBackend` (local). Ollama is threaded through `lyra_backends.py`, `lyra_embeddings.py`, `lyra_agent.py`, `lyra_tools.py`, `lyra_router.py`, `lyra_queue.py`, `theo_config.py`, `theo_worker.py`, `pipeline/lyra/config.py`, `.env.example`, and `llm-server/`. This plan removes all of it in dependency order.

**Tech Stack:** Python (FastAPI), SQLAlchemy, OpenAI SDK, Voyage AI, Docker

---

### Task 1: Remove `OllamaBackend` and helpers from `lyra_backends.py`

**Files:**
- Modify: `api/services/lyra_backends.py`

- [ ] **Step 1: Delete `_langchain_messages_to_ollama_native()` (lines 103-132)**

Remove the entire function:

```python
# DELETE lines 103-132:
def _langchain_messages_to_ollama_native(messages: list) -> list[dict]:
    ...  # entire function
```

- [ ] **Step 2: Delete `OllamaBackend` class (lines 135-267)**

Remove the section comment and entire class:

```python
# DELETE lines 135-267:
# ---------------------------------------------------------------------------
# OllamaBackend — raw openai.AsyncOpenAI (preserves reasoning field)
# ---------------------------------------------------------------------------

class OllamaBackend:
    ...  # entire class
```

- [ ] **Step 3: Remove `"local"` branch from `get_backend()` factory (lines 664-675)**

In the `get_backend()` function, remove the `if backend_type == "local":` block. The function should only create `AnthropicBackend`. Also remove `num_ctx` and `base_url` parameters since they were only used by the local backend.

Before:
```python
def get_backend(
    model_name: str,
    backend_type: str,
    num_ctx: int | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
) -> LLMBackend:
    ...
    key = f"{backend_type}:{model_name}:{num_ctx}:{max_tokens}:{base_url}"
    if key not in _backends:
        if backend_type == "local":
            ctx = num_ctx or int(os.getenv("LYRA_OLLAMA_NUM_CTX", "4096"))
            mt = max_tokens or 1024
            url = base_url if base_url is not None else os.getenv("LYRA_OLLAMA_BASE_URL", "")
            _backends[key] = OllamaBackend(
                model=model_name,
                base_url=url,
                api_key=os.getenv("LYRA_OLLAMA_API_KEY", "") if not base_url else "",
                max_tokens=mt,
                num_ctx=ctx,
            )
            logger.info(f"Created OllamaBackend for {model_name} at {url}")
        else:
            ...
```

After:
```python
def get_backend(
    model_name: str,
    backend_type: str,
    max_tokens: int | None = None,
) -> LLMBackend:
    """Get or create a backend instance for the given model.

    Args:
        model_name: The model to use (e.g. "claude-haiku-4-5-20251001").
        backend_type: Backend identifier (used for cache keying).
        max_tokens: Override max output tokens.
    """
    key = f"{backend_type}:{model_name}:{max_tokens}"
    if key not in _backends:
        from pipeline.lyra.config import get_max_tokens

        api_key = os.getenv("LYRA_ANTHROPIC_API_KEY") or os.getenv("LYRA_API_KEY") or ""
        _backends[key] = AnthropicBackend(
            model=model_name,
            api_key=api_key,
            max_tokens=max_tokens or get_max_tokens(),
        )
        logger.info(f"Created AnthropicBackend for {model_name}")
    return _backends[key]
```

- [ ] **Step 4: Update docstring**

Update the module docstring (line 657) to remove references to local/Ollama.

- [ ] **Step 5: Verify no remaining Ollama references**

Run: `grep -n -i ollama api/services/lyra_backends.py`
Expected: No matches.

- [ ] **Step 6: Commit**

```bash
git add api/services/lyra_backends.py
git commit -m "refactor: remove OllamaBackend and local backend factory from lyra_backends"
```

---

### Task 2: Remove `OllamaEmbeddings` and local reranker from `lyra_embeddings.py`

**Files:**
- Modify: `api/services/lyra_embeddings.py`

- [ ] **Step 1: Remove Ollama env vars and imports (lines 32-36)**

Delete:
```python
# Ollama/self-hosted settings
OLLAMA_EMBED_URL = os.getenv("LYRA_OLLAMA_EMBED_URL", "")
OLLAMA_EMBED_MODEL = os.getenv("LYRA_OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_API_KEY = os.getenv("LYRA_OLLAMA_EMBED_API_KEY", "")
RERANK_URL = os.getenv("LYRA_RERANK_URL", "")
```

- [ ] **Step 2: Delete `OllamaEmbeddings` class (lines 71-100)**

Remove the entire class.

- [ ] **Step 3: Delete `LocalReranker` class and its dataclasses (lines 103-144)**

Remove `_RerankResult`, `_RerankResponse`, and `LocalReranker`.

- [ ] **Step 4: Simplify `get_embeddings()` — remove local branch**

Before:
```python
_embeddings: dict[tuple[str, str], VoyageEmbeddings | OllamaEmbeddings] = {}

def get_embeddings(
    usage: str = "query", backend: str | None = None
) -> VoyageEmbeddings | OllamaEmbeddings:
    ...
    instance: VoyageEmbeddings | OllamaEmbeddings
    if backend == "local":
        instance = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL)
        logger.info(...)
    else:
        model = EMBED_MODEL_INDEX if usage == "index" else EMBED_MODEL_QUERY
        input_type = "document" if usage == "index" else "query"
        instance = VoyageEmbeddings(model=model, input_type=input_type)
        logger.info(...)
```

After:
```python
_embeddings: dict[tuple[str, str], VoyageEmbeddings] = {}

def get_embeddings(
    usage: str = "query", backend: str | None = None
) -> VoyageEmbeddings:
    """Get Voyage embedding model.

    Args:
        usage: 'index' for documents, 'query' for search.
        backend: Kept for API compat (ignored, always Voyage).
    """
    backend = backend or "voyage"
    key = (usage, backend)

    if key in _embeddings:
        return _embeddings[key]

    model = EMBED_MODEL_INDEX if usage == "index" else EMBED_MODEL_QUERY
    input_type = "document" if usage == "index" else "query"
    instance = VoyageEmbeddings(model=model, input_type=input_type)
    logger.info(
        f"Initialized VoyageAI embeddings: {model} (usage={usage}, input_type={input_type})"
    )

    _embeddings[key] = instance
    return instance
```

- [ ] **Step 5: Simplify `get_reranker()` — remove local branch**

Before:
```python
_rerankers: dict[str, voyageai.Client | LocalReranker] = {}

def get_reranker(backend: str | None = None) -> voyageai.Client | LocalReranker:
    ...
    if backend == "local":
        instance = LocalReranker(url=RERANK_URL)
        ...
    else:
        instance = _get_voyage_client()
```

After:
```python
_rerankers: dict[str, voyageai.Client] = {}

def get_reranker(backend: str | None = None) -> voyageai.Client:
    """Get Voyage reranker client."""
    backend = backend or "voyage"

    if backend in _rerankers:
        return _rerankers[backend]

    instance = _get_voyage_client()
    _rerankers[backend] = instance
    return instance
```

- [ ] **Step 6: Update module docstring (lines 1-17)**

Replace:
```python
"""
Lyra Embeddings & Reranker Factory.

Both backends are always available simultaneously (per-request routing via backend param):

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
```

With:
```python
"""
Lyra Embeddings & Reranker Factory.

Uses Voyage AI for all embeddings and reranking:
  - Indexing: voyage-4-large (best quality, 1024-dim) with input_type="document"
  - Querying: voyage-4 (fast/cheap, same 1024-dim space) with input_type="query"
  - Reranking: rerank-2.5-lite (second-pass scorer)
"""
```

- [ ] **Step 7: Remove the `openai` import guard**

The `OllamaEmbeddings` class was the only user of `from openai import OpenAI` in this file. Verify there are no remaining references.

Run: `grep -n "openai" api/services/lyra_embeddings.py`
Expected: No matches.

- [ ] **Step 8: Commit**

```bash
git add api/services/lyra_embeddings.py
git commit -m "refactor: remove OllamaEmbeddings and LocalReranker from lyra_embeddings"
```

---

### Task 3: Remove Ollama conditionals from `lyra_agent.py`

**Files:**
- Modify: `api/services/lyra_agent.py`

- [ ] **Step 1: Delete `_stream_with_heartbeat()` function (lines 736-783)**

This function is only used by the Ollama streaming path. Remove it entirely.

- [ ] **Step 2: Make filter extraction + query expansion unconditional (lines 1523, 1529)**

Before:
```python
        use_filter_extraction = ctx.backend_type != "local"
        ...
        use_expansion = ctx.backend_type != "local"
```

After:
```python
        use_filter_extraction = True
        ...
        use_expansion = True
```

- [ ] **Step 3: Make tool-exhaustion skip unconditional (line 1941)**

Before:
```python
        if not _offer_tools and tool_calls_made > 0 and ctx.backend_type != "local":
```

After:
```python
        if not _offer_tools and tool_calls_made > 0:
```

- [ ] **Step 4: Remove the Ollama streaming `else` branch (lines 2189-2209)**

The `if ctx.backend_type != "local":` block (lines 1964-2188) becomes the only path. Remove the `if` condition wrapper (keep the body) and delete the `else` block entirely:

```python
# DELETE these lines (2189-2209):
        else:
            # Ollama/local: stream with heartbeat
            async for ev in _stream_with_heartbeat(
                backend_impl,
                messages,
                TOOLS if _offer_tools else [],
                enable_thinking=ctx.supports_thinking,
            ):
                if ev["type"] == "heartbeat":
                    yield {"type": "status", "content": f"Processing input ({ev['elapsed_s']}s)..."}
                elif ev["type"] == "reasoning":
                    yield {"type": "thinking", "content": ev["text"]}
                elif ev["type"] == "content":
                    collected_content += ev["text"]
                    _text_emitted = True
                    yield {"type": "token", "content": ev["text"]}
                elif ev["type"] == "tool_call_chunk":
                    _accumulate_tool_call(tool_calls, ev)
                elif ev["type"] == "usage":
                    total_input_tokens += ev["input"]
                    total_output_tokens += ev["output"]
```

Then un-indent the former `if` body so it's no longer conditional. The code at line 1964 changes from:

```python
        if ctx.backend_type != "local":
            # Retry up to 2 times...
            result = None
            ...
```

To just:

```python
        # Retry up to 2 times...
        result = None
        ...
```

- [ ] **Step 5: Remove the Ollama preamble re-emit (lines 2228-2231)**

Delete:
```python
        # For Ollama streaming, the preamble text (e.g. "I'll search for...") was
        # streamed as tokens. Re-emit it as a status event.
        if collected_content.strip() and ctx.backend_type == "local":
            yield {"type": "status", "content": collected_content.strip()}
```

- [ ] **Step 6: Remove Phase 2 Ollama skip comment (lines 2549-2550)**

Delete:
```python
    # For Ollama, Phase 1 already streams tokens directly to the client so
    # _text_emitted is True and Phase 2 is skipped.
```

- [ ] **Step 7: Remove `num_ctx` and `base_url` params from `run_agent_stream()` signature (lines 1433-1435)**

Before:
```python
    num_ctx: int | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
```

After:
```python
    max_tokens: int | None = None,
```

And update the `get_backend()` call (lines 1458-1464):

Before:
```python
    backend_impl = get_backend(
        ctx.model_name,
        ctx.backend_type,
        num_ctx=num_ctx,
        max_tokens=max_tokens,
        base_url=base_url,
    )
```

After:
```python
    backend_impl = get_backend(
        ctx.model_name,
        ctx.backend_type,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 8: Verify no remaining Ollama/local references**

Run: `grep -n -i "ollama\|backend_type.*local" api/services/lyra_agent.py`
Expected: No matches.

- [ ] **Step 9: Commit**

```bash
git add api/services/lyra_agent.py
git commit -m "refactor: remove Ollama conditionals and heartbeat wrapper from lyra_agent"
```

---

### Task 4: Clean up `lyra_router.py`, `lyra_queue.py`, `lyra_tools.py`

**Files:**
- Modify: `api/services/lyra_router.py`
- Modify: `api/services/lyra_queue.py`
- Modify: `api/services/lyra_tools.py`

- [ ] **Step 1: Update `lyra_router.py` docstring and comments**

Line 4, change:
```python
Lyra uses Anthropic (Haiku/Sonnet/Opus). Theo uses local Ollama (configured separately).
```
To:
```python
Lyra uses Anthropic (Haiku/Sonnet/Opus). Theo uses MiniMax M2.7 (configured separately).
```

Line 19, change:
```python
    backend_type: str  # "anthropic" | "local" (local = Theo only)
```
To:
```python
    backend_type: str  # "anthropic" | "minimax"
```

Line 22, change:
```python
    embedding_backend: str  # "voyage" | "local"
```
To:
```python
    embedding_backend: str  # "voyage"
```

Line 67, change:
```python
    if ctx.model_tier == "heavy":
        return "Local model → think=on, tools + retrieval"
```
To:
```python
    if ctx.model_tier == "heavy":
        return "MiniMax M2.7 → think=on, tools + retrieval"
```

- [ ] **Step 2: Update `lyra_queue.py` comment**

Line 22, change:
```python
PARALLEL_SLOTS = 2  # ollama OLLAMA_NUM_PARALLEL
```
To:
```python
PARALLEL_SLOTS = 2
```

- [ ] **Step 3: Update `lyra_tools.py` comments and remove local collection suffix**

Lines 164-165, change:
```python
# "voyage" (default) uses Voyage embeddings + original collections.
# "local" uses Ollama embeddings + *_local collections.
```
To:
```python
# "voyage" — uses Voyage embeddings.
```

Lines 947-948, change:
```python
    # Append _local suffix for local backend collections
    qdrant_collection = f"{collection}_local" if backend == "local" else collection
```
To:
```python
    qdrant_collection = collection
```

- [ ] **Step 4: Commit**

```bash
git add api/services/lyra_router.py api/services/lyra_queue.py api/services/lyra_tools.py
git commit -m "refactor: clean up Ollama references from router, queue, and tools"
```

---

### Task 5: Gut Theo config and worker (leave as stub for Phase 2)

**Files:**
- Modify: `api/services/theo_config.py`
- Modify: `api/services/theo_worker.py`

- [ ] **Step 1: Strip Ollama config from `theo_config.py`**

Replace entire file with:

```python
"""Configuration for Theodore Furcade — async archaeological research agent.

NOTE: Backend not yet configured. Phase 2 will wire MiniMax M2.7.
"""

THEO_PARALLEL_SLOTS = 1
THEO_MAX_TOKENS = 12288

EFFORT_CONFIG = {
    "quick": {"thinking": False, "max_rounds": 1},
    "deep": {"thinking": True, "max_rounds": 5},
    "full": {"thinking": True, "max_rounds": 15},
    "auto": {"thinking": True, "max_rounds": 10},
}

RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 5
```

- [ ] **Step 2: Update `theo_worker.py` imports**

Change:
```python
from api.services.theo_config import (
    EFFORT_CONFIG,
    RESULT_TTL_HOURS,
    THEO_MAX_TOKENS,
    THEO_MODEL,
    THEO_NUM_CTX,
    THEO_OLLAMA_BASE_URL,
    THEO_PARALLEL_SLOTS,
)
```

To:
```python
from api.services.theo_config import (
    EFFORT_CONFIG,
    RESULT_TTL_HOURS,
    THEO_MAX_TOKENS,
    THEO_PARALLEL_SLOTS,
)
```

- [ ] **Step 3: Update `_process_request()` to fail clearly**

In `_process_request()`, the `RequestContext` and `run_agent_stream` call need updating. Replace the context creation and stream call (lines 61-108):

Before:
```python
    ctx = RequestContext(
        backend_type="local",
        model_tier="heavy",
        model_name=THEO_MODEL,
        embedding_backend="local",
        supports_thinking=bool(effort_cfg["thinking"]),
        supports_tools=True,
    )
    ...
    async for event in run_agent_stream(
        message=question,
        context_type="global",
        ctx=ctx,
        system_prompt=THEO_SYSTEM_PROMPT,
        num_ctx=THEO_NUM_CTX,
        max_tokens=THEO_MAX_TOKENS,
        base_url=THEO_OLLAMA_BASE_URL or None,
    ):
```

After:
```python
    # Phase 2 will set backend_type="minimax" and model_name to MiniMax M2.7
    raise NotImplementedError(
        "Theo backend not configured — Phase 2 will wire MiniMax M2.7"
    )
```

Keep the rest of the worker (polling, cleanup, start_worker) intact — it's backend-agnostic infrastructure.

- [ ] **Step 4: Commit**

```bash
git add api/services/theo_config.py api/services/theo_worker.py
git commit -m "refactor: strip Ollama from Theo config/worker (stub for Phase 2 MiniMax)"
```

---

### Task 6: Remove Ollama from pipeline config (`pipeline/lyra/config.py`)

**Files:**
- Modify: `pipeline/lyra/config.py`

- [ ] **Step 1: Remove Ollama fields from `LyraSettings` (lines 157-163)**

Delete:
```python
    # LLM backend: "anthropic" (default) or "ollama" (local)
    llm_backend: str = "anthropic"

    # Ollama endpoint (OpenAI-compatible API, used when llm_backend="ollama")
    ollama_base_url: str = ""
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"
```

Replace with:
```python
    # LLM backend: "anthropic" (default) or "minimax"
    llm_backend: str = "anthropic"
```

- [ ] **Step 2: Delete `_cached_ollama_client` and `_get_ollama_client()` (lines 229-260)**

Delete:
```python
_cached_ollama_client = None
_cached_ollama_key: str = ""


def _get_ollama_client(settings: LyraSettings):
    """Return a cached OpenAI client for the Ollama backend."""
    ...entire function...
```

- [ ] **Step 3: Delete `_call_ollama_api()` function (lines 412-468)**

Remove the entire function.

- [ ] **Step 4: Remove Ollama branch from `call_llm()` (lines 620-622)**

Before:
```python
        if backend == "ollama":
            return _call_ollama_api(settings, prefill=prefill, **kwargs)
        if backend == "minimax":
```

After:
```python
        if backend == "minimax":
```

- [ ] **Step 5: Update the backend comment in `call_llm()` docstring**

Change any references to "ollama" in the `call_llm()` docstring to reflect only "anthropic" and "minimax" backends.

- [ ] **Step 6: Verify no remaining Ollama references**

Run: `grep -n -i ollama pipeline/lyra/config.py`
Expected: No matches.

- [ ] **Step 7: Commit**

```bash
git add pipeline/lyra/config.py
git commit -m "refactor: remove Ollama backend from pipeline LyraSettings and call_llm"
```

---

### Task 7: Clean up `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update backend selector comment (line 133)**

Change:
```
# "anthropic" = Claude (default)  |  "minimax" = MiniMax M2.7  |  "ollama" = local
```
To:
```
# "anthropic" = Claude (default)  |  "minimax" = MiniMax M2.7
```

- [ ] **Step 2: Delete the Ollama section (lines 147-173)**

Remove the entire block:
```
# =============================================================================
# LYRA SELF-HOSTED LLM (local Ollama — set LYRA_LLM_BACKEND=ollama to use)
# =============================================================================
...through...
# The index backend is selected via: python scripts/build_lyra_index.py --backend local|voyage
```

- [ ] **Step 3: Delete the legacy Ollama section (lines 194-207)**

Remove:
```
# =============================================================================
# LLM CONFIGURATION (Ollama)
# =============================================================================
# Ollama server URL
OLLAMA_HOST=http://localhost:11434
...
OLLAMA_TIMEOUT=120
```

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "refactor: remove Ollama env vars from .env.example"
```

---

### Task 8: Delete `llm-server/` directory

**Files:**
- Delete: `llm-server/` (entire directory)

- [ ] **Step 1: Delete the directory**

```bash
rm -rf llm-server/
```

- [ ] **Step 2: Verify it's gone**

```bash
ls llm-server/ 2>&1
```
Expected: "No such file or directory"

- [ ] **Step 3: Commit**

```bash
git add -A llm-server/
git commit -m "refactor: delete llm-server Docker stack (Ollama + reranker + nginx)"
```

---

### Task 9: Final verification

- [ ] **Step 1: Search entire codebase for remaining Ollama references**

```bash
grep -rn -i "ollama" --include="*.py" --include="*.yml" --include="*.yaml" --include="*.md" --include="*.sh" --include="*.env*" . | grep -v node_modules | grep -v .git | grep -v docs/research | grep -v __pycache__ | grep -v docs/superpowers/plans
```

Any hits in code files (not research docs) need to be addressed.

- [ ] **Step 2: Check for broken imports**

```bash
cd api && python -c "from services.lyra_backends import get_backend, AnthropicBackend; print('backends OK')"
cd api && python -c "from services.lyra_embeddings import get_embeddings, get_reranker; print('embeddings OK')"
cd api && python -c "from services.theo_config import THEO_MAX_TOKENS, EFFORT_CONFIG; print('theo_config OK')"
```

- [ ] **Step 3: Commit any remaining fixes**

If Step 1 or 2 found issues, fix and commit.
