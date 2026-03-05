# Unified Lyra Pipeline — Qwen3.5 Multi-Model Architecture

**Date:** 2026-03-05
**Status:** Implemented

## Overview

Replaced qwen3:8b single-model setup with Qwen3.5 4B + 0.8B multi-model architecture behind a unified pipeline. One code path for all backends. Intelligent routing so simple queries respond in seconds. Two concurrent local users via separate per-tier queues.

## Architecture

```
Frontend (backend: "minimax" | "local")
    │
    ▼
/lyra/chat endpoint (api/routes/lyra.py)
    │
    ├─ "minimax" → MiniMax credits flow (unchanged)
    │
    └─ "local" → ModelRouter picks tier:
                  ├─ "fast" (0.8B) → fast_queue semaphore(1)
                  └─ "heavy" (4B)  → heavy_queue semaphore(1)
    │
    ▼
run_agent_stream()  ← ONE function, backend-agnostic
    │
    ├─ Retrieval (Qdrant hybrid search via RequestContext)
    ├─ Augmentation (news, context assembly)
    └─ LLM Reasoning loop:
         backend.stream(messages, tools) → StreamEvent
         (unified interface — same loop for all backends)
```

## Key Design Decisions

1. **Keyword heuristic router** — zero-latency regex check before pipeline starts
2. **Separate queues** — 0.8B and 4B each get their own semaphore(1), allowing 2 concurrent local inferences
3. **MiniMax stays as premium tier** — credit-based, no queue, highest quality
4. **`RequestContext` dataclass** replaces `_current_backend` global — passed through pipeline, stored in `contextvars.ContextVar`
5. **`LLMBackend` Protocol** — both Ollama and MiniMax implement `stream()` → same 4 event types

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `api/services/lyra_backends.py` | NEW | `LLMBackend` Protocol, `OllamaBackend`, `AnthropicBackend` |
| `api/services/lyra_router.py` | NEW | `RequestContext`, `route_request()`, `_classify_query()`, `ContextVar` |
| `api/services/lyra_agent.py` | MODIFY | Unified streaming loop via `backend.stream()`, uses `RequestContext` |
| `api/services/lyra_tools.py` | MODIFY | Replaced `_current_backend` global with `contextvars` |
| `api/services/lyra_queue.py` | MODIFY | Parameterized `LyraQueue`, added `TieredQueue` wrapper |
| `api/routes/lyra.py` | MODIFY | Uses `route_request()`, routes to tiered queues |
| `llm-server/docker-compose.yml` | MODIFY | Two model env vars, `MAX_LOADED_MODELS=3` |
| `llm-server/entrypoint.sh` | MODIFY | Pulls both Qwen3.5 models |
| `scripts/test_vps2.py` | REWRITE | Full multi-model test suite with concurrent test |
| `docs/lyra-pipeline.md` | MODIFY | Added multi-model routing section |
| `docs/lyra-rag-pipeline.html` | MODIFY | Updated agent loop to show multi-model |
