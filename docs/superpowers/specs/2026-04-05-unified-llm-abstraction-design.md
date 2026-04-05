# Unified LLM Abstraction Layer

**Date:** 2026-04-05
**Scope:** Lyra news pipeline, article pipeline, radar (site identification/enrichment)
**Out of scope:** Theo pipeline, Lyra chat, `minimax_shared.py`, MiniMax search API

## Problem

The current `call_api()` dispatch in `pipeline/lyra/config.py` has two completely separate code paths:

- `_call_anthropic_api()` — uses the Anthropic SDK, supports structured output (`output_config`), extended thinking, tools, temperature, prefill, documents/citations
- `_call_minimax_api()` — uses the OpenAI SDK, silently discards `response_format`, `thinking`, `temperature`, `tools`, `prefill`, and `documents`

When `LYRA_LLM_BACKEND=minimax` (current prod config), 11 out of 17 call sites lose their structured output guarantees, all thinking is discarded, and temperature control is ignored. MiniMax M2.7 is capable of all these features via its Anthropic-compatible endpoint, but the current adapter doesn't use them.

## Solution

Delete the OpenAI SDK path. Both backends use the **Anthropic SDK** with different base URLs:

| Backend | Base URL | API Key | Model |
|---------|----------|---------|-------|
| Anthropic | `https://api.anthropic.com` (SDK default) | `LYRA_ANTHROPIC_API_KEY` | Per-step (Haiku/Sonnet/Opus) |
| MiniMax | `https://api.minimax.io/anthropic` | `LYRA_MINIMAX_API_KEY` (sk-cp- Token Plan key) | `MiniMax-M2.7` for all steps |

One `_call_anthropic_api()` function with 5 clearly-marked adaptation points for MiniMax differences.

## Adaptation Points

### 1. Client selection

Two cached Anthropic SDK clients. Backend determines which one is used.

```python
def _get_client(settings: LyraSettings) -> anthropic.Anthropic:
    if settings.llm_backend == "minimax":
        return _get_minimax_anthropic_client(settings)
    return _get_anthropic_client(settings.anthropic_api_key)

def _get_minimax_anthropic_client(settings: LyraSettings) -> anthropic.Anthropic:
    # Cached client with base_url="https://api.minimax.io/anthropic"
    ...
```

### 2. Model mapping

When backend is MiniMax, all per-step model names (`model_summarize`, `model_post`, `model_verify`, etc.) are ignored. Every call uses `MiniMax-M2.7`.

```python
if is_minimax:
    model = "MiniMax-M2.7"
```

### 3. Structured output (tool-use trick)

This is the critical adaptation. MiniMax's Anthropic endpoint does not support `response_format` / `output_config` for guaranteed JSON schema output. Instead, we use the **tool-use trick**: define a dummy tool whose `input_schema` matches the desired JSON schema, then force the model to "call" it via `tool_choice`.

**When `response_format` is provided and backend is MiniMax:**

1. Extract the JSON schema from `response_format["json_schema"]["schema"]`
2. Create a tool definition:
   ```python
   tool = {
       "name": "structured_output",
       "description": "Return the result as structured JSON matching the schema.",
       "input_schema": schema,
   }
   ```
3. Set `tool_choice = {"type": "tool", "name": "structured_output"}`
4. Add the tool to `create_kwargs["tools"]`
5. After the API call, find the `tool_use` block in the response content
6. Extract `block.input` (already a parsed dict), serialize to JSON string
7. Wrap in a `TextBlock` so `response.text` returns the JSON string as callers expect

**When `response_format` is provided and backend is Anthropic:**

Existing behavior — use `output_config` with `json_schema` (native structured output).

**Error handling:** If MiniMax returns a response without a `tool_use` block (e.g., model ignores the forced tool and produces plain text), fall back to extracting JSON from the text content using `parse_json_response()`. If that also fails, return the response as-is and let the caller's existing JSON parse error handling deal with it (all callers already have `json.JSONDecodeError` handling).

**Callers see no difference.** Both paths produce `NormalizedResponse` with `response.text` containing valid JSON.

### 4. Temperature clamping

MiniMax M2.7 temperature range is (0, 1] — exclusive of 0. Several call sites pass `temperature=0.0`.

```python
if is_minimax and temperature is not None and temperature <= 0.0:
    temperature = 0.01
```

Note: when `thinking` is enabled, temperature is already omitted (Anthropic requirement). MiniMax also supports thinking, so same rule applies.

**Thinking + tool-use trick:** The tweet_verifier uses both `thinking={"type": "adaptive"}` and `response_format` simultaneously. With the tool-use trick, the response will contain thinking blocks + a tool_use block. This is valid — MiniMax supports interleaved thinking with tool calls. The `_extract_tool_result()` helper scans all content blocks, skipping thinking blocks, to find the tool_use block.

### 5. Documents/citations

MiniMax's Anthropic endpoint does not support document content blocks or citations. When `documents` are provided and backend is MiniMax, inline the document text directly into the user message:

```python
if is_minimax and documents:
    docs_text = "\n\n".join(
        f"--- {doc.get('title', 'Source')} ---\n{doc['data']}"
        for doc in documents
    )
    # Prepend to the last user message content
```

Currently only used by `site_researcher.py`.

## What stays the same

- **`call_api()` signature** — no changes to the public interface
- **`NormalizedResponse`** — same dataclass, same `.text` property
- **All callers** — summarizer, tweet_generator, tweet_verifier, significance_scorer, site_identifier, article_generator, site_researcher, web_research — zero changes needed
- **`minimax_shared.py`** — untouched, continues to use raw httpx for MiniMax search API and direct M2.7 chat (used by article web verification and Theo)
- **`LyraSettings`** — keeps `llm_backend`, `minimax_api_key`, `minimax_base_url`

## What gets deleted

- `_call_minimax_api()` function
- `_get_minimax_client()` function (OpenAI SDK client)
- `_cached_minimax_client` / `_cached_minimax_key` globals
- OpenAI SDK import (`from openai import OpenAI`)
- `minimax_model` setting (always `MiniMax-M2.7`, hardcoded)

## Config changes

| Setting | Before | After |
|---------|--------|-------|
| `LYRA_LLM_BACKEND` | `"anthropic"` or `"minimax"` | Same, no change |
| `LYRA_MINIMAX_API_KEY` | Used with OpenAI SDK | Used with Anthropic SDK |
| `LYRA_MINIMAX_BASE_URL` | `https://api.minimax.io` | `https://api.minimax.io/anthropic` |
| `LYRA_MINIMAX_MODEL` | `MiniMax-M2.7` | Removed (hardcoded) |

The `.env` and `.env.example` files need updating for `LYRA_MINIMAX_BASE_URL`.

## Feature matrix after refactor

| Feature | Anthropic | MiniMax | How |
|---------|-----------|---------|-----|
| Structured output (JSON schema) | Native `output_config` | Tool-use trick | Automatic in dispatch |
| Extended thinking | Native `thinking` param | Native (Anthropic endpoint) | Pass-through |
| Temperature control | 0.0-1.0 | 0.01-1.0 (clamped) | Auto-clamp |
| Tool calling | Native | Native (Anthropic endpoint) | Pass-through |
| Prefill | Native | Native (Anthropic endpoint) | Pass-through |
| Documents/citations | Native content blocks | Inlined into message | Auto-convert |
| Model tiering | Haiku/Sonnet/Opus | All M2.7 | Model override |
| System prompt caching | `cache_control: ephemeral` | Passes through (may be ignored) | Pass-through |

## Files changed

1. **`pipeline/lyra/config.py`** — rewrite dispatch layer:
   - New `_get_minimax_anthropic_client()` with caching
   - Refactor `_call_anthropic_api()` to accept backend parameter, add 5 adaptation points
   - New `_build_structured_output_tool()` helper to create tool definition from schema
   - New `_extract_tool_use_json()` helper to unwrap tool_use response into JSON string
   - Delete `_call_minimax_api()`, `_get_minimax_client()`, OpenAI imports
   - Update `call_api()` to pass backend through instead of branching

2. **`.env.example`** — update `LYRA_MINIMAX_BASE_URL` default, remove `LYRA_MINIMAX_MODEL`

No other files change.

## Risk & rollback

- **Rollback**: Set `LYRA_LLM_BACKEND=anthropic` in prod `.env`. The Anthropic path is unchanged in behavior.
- **Testing**: Run `scripts/test_lyra_quality.py --no-judge` with both backends. The structured output test cases exercise every schema.
- **Gradual rollout**: Deploy with `LYRA_LLM_BACKEND=anthropic` first, verify no regression, then switch to `minimax`.
