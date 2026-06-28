# MiniMax M2.7 Best Practices Research

**Date**: 2026-03-30
**Objective**: Document M2.7 capabilities for structured output, tool calling, reasoning control, and text processing with citation preservation -- specifically for the article web-verification pipeline.

---

## 1. Structured JSON Output (response_format)

### Official Status

**M2.7 does NOT support `response_format: json_schema` on MiniMax's native API.**

The MiniMax native API (`/v1/chat/completions`) documents `response_format` with `json_schema` support, but **only for MiniMax-Text-01** (a non-reasoning text model). The M2 family (M2, M2.1, M2.5, M2.7) is excluded from this feature in MiniMax's own docs.

However:
- **Third-party providers** (OpenRouter, AI/ML API, DeepInfra) list `response_format` as supported for M2.7, suggesting they may implement constrained decoding server-side.
- **AI/ML API** explicitly documents `json_schema` with `strict: true` for M2, M2.1, and M2.5, meaning the open-weights versions can do it via inference server features (vLLM/SGLang constrained decoding).
- **OpenRouter** lists "Response format" as a supported parameter for M2.7.

### Critical Constraint

```
stream=true and response_format are MUTUALLY EXCLUSIVE on MiniMax's API.
```

This is a hard API error: `"invalid params, stream and response_format are mutually exclusive"`. If you need structured output, you cannot stream. For long prompts, this creates timeout risk.

### Recommendation for Our Pipeline

The current approach (prompt-based JSON extraction with manual parsing) is actually the right call for M2.7 via MiniMax's native API. The `_extract_claims()` method already does this with markdown fence stripping + `json.loads()`. For the verification step, structured output isn't needed -- the freeform text + `[WEB_REFS]` block pattern works better for preserving natural article prose.

If switching to OpenRouter or a third-party provider, `json_schema` with `strict: true` could be used for the claims extraction step to eliminate parse failures.

---

## 2. Tool Calling

### Supported

M2.7 has **full tool calling / function calling support** via both:
- **Native MiniMax API**: `tools` array + `tool_choice` parameter ("none" or "auto")
- **Anthropic-compatible API**: Standard `tool_use` / `tool_result` message types
- **OpenAI-compatible API**: Standard function calling format

### Interleaved Thinking

M2.7's key differentiator is **interleaved thinking** -- it reasons between each round of tool interactions. This means:

1. Model receives query + tool definitions
2. Model thinks (internal reasoning)
3. Model calls tool(s)
4. Tool results returned
5. Model thinks again (reflects on results)
6. Model calls more tools or produces final answer

**Critical requirement**: The complete model response -- including `reasoning_details` or `<think>` blocks -- MUST be preserved in the conversation history between rounds. Stripping thinking content breaks the reasoning chain and degrades quality.

### Tool Definition Format

```json
{
  "name": "search_web",
  "description": "Search function.",
  "parameters": {
    "type": "object",
    "properties": {
      "query_list": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Keywords for search"
      }
    },
    "required": ["query_list"]
  }
}
```

### Relevance to Our Pipeline

Our current pipeline does NOT use M2.7's native tool calling. Instead, we manually orchestrate: M2.7 extracts claims -> we call search API -> M2.7 verifies with results. This is fine and arguably better for our use case because:
- We control which search queries run (no hallucinated tool calls)
- We can deduplicate and curate search results before verification
- We avoid the complexity of multi-turn tool call state management

---

## 3. Reasoning Effort / Thinking Budget

### Via Anthropic-Compatible API (budget_tokens)

When using MiniMax's Anthropic-compatible endpoint (`https://api.minimax.io/anthropic`), you can control reasoning via:

```python
thinking={"type": "enabled", "budget_tokens": 1000}
```

This limits the thinking tokens to 1000, preventing the model from consuming excessive budget on reasoning before producing the answer.

### Via OpenAI-Compatible API (reasoning_split)

```python
extra_body={"reasoning_split": True}
```

This separates thinking content into a `reasoning_details` field but does NOT control the reasoning budget.

### Via Native API

**No documented reasoning control.** The native `/v1/chat/completions` endpoint does not expose reasoning effort parameters. The model always reasons and embeds thinking in `<think>` tags.

### Known Issue: Excessive Reasoning

Multiple reports confirm M2.7 generates **16,000+ thinking tokens even for simple prompts**. When `max_tokens` (or `max_completion_tokens`) is set too low, the reasoning consumes the entire budget and the actual answer gets truncated with `finish_reason: "length"`. This is the reasoning-leaks-into-content problem documented for M2.5 on NVIDIA forums.

### Recommendation

For our pipeline:
- **Claims extraction** (current 4096 max_tokens): This is tight. M2.7 may spend 2-4K on thinking, leaving only 0-2K for the actual JSON. Consider increasing to 6144, or switching to the Anthropic-compatible API with `budget_tokens: 1500` to cap thinking.
- **Section verification** (current 8192 max_tokens): Adequate for most sections but could be tight for long sections. The thinking overhead means only ~4-6K tokens are available for the corrected article text. Consider 12288 for safety, or Anthropic API with `budget_tokens: 3000`.

---

## 4. max_tokens Recommendations

### Model Specifications

| Parameter | Value |
|-----------|-------|
| Context window | 204,800 tokens (input + output combined) |
| Max output | 131,072 tokens |
| Default max_completion_tokens (M2 family) | 10,240 |

### Best Practice from MiniMax Docs

> "Maintain input and output tokens within 200k tokens for lengthy tasks."
> "M2.7 may terminate tasks early when approaching context capacity thresholds."

### Parameter Name

MiniMax's native API uses `max_completion_tokens` (not `max_tokens`, which is deprecated). However, both work -- the API accepts either.

### Temperature

MiniMax recommends `temperature=1.0` for M2 reasoning models (not the 0.1-0.7 range used for Text-01). This is counter-intuitive but aligns with how reasoning models work -- the thinking chain provides self-correction, so higher temperature in generation helps explore more diverse reasoning paths.

Our current code doesn't set temperature, so it defaults to whatever MiniMax's API default is. For fact-checking, consider explicitly setting `temperature=1.0` per MiniMax's recommendation, or test with lower values to see if citation preservation improves.

---

## 5. MiniMax Search MCP Integration

### Architecture

MiniMax provides two MCP approaches:

1. **minimax_search** (general): MCP server with `search` + `browse` tools
   - `search`: Parallel web search via Serper API, returns title/URL/snippet
   - `browse`: Fetches URLs via Jina Reader, processes with MiniMax LLM
   - Requires: SERPER_API_KEY, JINA_API_KEY, MINIMAX_API_KEY

2. **MiniMax-Coding-Plan-MCP** (Token Plan users): `web_search` + `understand_image`
   - `web_search`: Search via MiniMax's own endpoint
   - `understand_image`: Image analysis
   - Requires only: MINIMAX_API_KEY + MINIMAX_API_HOST

### M2.7 vs M2.5 Search Changes

M2.5 had built-in search as a simple configuration toggle. M2.7 moved search to an **MCP tool chain**, requiring explicit tool configuration. This is the agentic architecture -- M2.7 decides when and what to search.

### Relevance to Our Pipeline

We already use MiniMax's search endpoint directly (`/v1/coding_plan/search`), which is the right approach for a programmatic pipeline. The MCP integration is designed for interactive coding assistants (Claude Code, Cursor, etc.), not for backend pipelines.

---

## 6. Citation Marker Handling -- The Core Problem

### Why M2.7 Drops Citations

Based on the research, there is no MiniMax-specific documentation about citation marker handling. The problem is a general LLM behavior pattern:

1. **Reasoning models rewrite aggressively.** M2.7's thinking chain leads it to "improve" text, and inline markers like `[1]`, `[2]` are treated as noise to be cleaned up during rewriting.

2. **No structural awareness.** M2.7 sees `[1]` as plain text with no special semantics. Unlike Anthropic's Citations API which has structural citation support, M2.7 has no concept of "preserve these markers."

3. **Long-context degradation.** When the total input (system prompt + article section + search results) is large, attention to specific instructions ("keep [N] markers") weakens.

4. **Thinking token competition.** If thinking consumes most of the token budget, the output portion gets compressed, and markers are among the first things dropped.

### Current Mitigation in Our Code

The codebase already has a post-processing repair step (lines 372-396 of `web_research.py`):

```python
# Restore YouTube [N] citations that M2.7 may have dropped
orig_yt_cites = set(re.findall(r"\[\d+\]", section_text))
remaining_yt = set(re.findall(r"\[\d+\]", text))
lost = orig_yt_cites - remaining_yt
```

This finds lost `[N]` markers and attempts to re-insert them by matching paragraph openings. It's a reasonable heuristic but can misplace citations.

### Recommended Approach (Ranked by Reliability)

**Option A: Two-pass architecture (most reliable)**

Split verification into two LLM calls per section:
1. **Correction pass**: M2.7 produces corrected text with `[wN]` web markers but is told to output `[YT_PLACEHOLDER_N]` for every YouTube citation position (easier for the model to preserve verbose placeholders than terse `[1]`).
2. **Merge pass**: A simple regex/code step that maps `[YT_PLACEHOLDER_N]` back to `[N]` and validates all original markers are present.

Cost: 2x LLM calls per section, but higher accuracy.

**Option B: Explicit enumeration in prompt (moderate reliability)**

Add to the system prompt:
```
BEFORE you begin, note every [N] citation marker in the input and its exact position.
Your output MUST contain every one of these markers: [1], [3], [7], [12]
(List generated dynamically per section)
```

This forces the model to "register" the markers before processing.

**Option C: Post-processing repair (current approach, lowest reliability)**

Keep the existing heuristic repair. Improve it by:
- Using sentence-level matching instead of paragraph-level (more precise placement)
- Diffing original vs corrected to find which sentences were rewritten
- Re-inserting markers at the end of their matching corrected sentences

**Option D: Switch to Anthropic-compatible API with tool calling**

Use MiniMax's Anthropic-compatible endpoint with native tool calling. Define a `report_corrections` tool that returns structured corrections (claim, correction, web_source), and keep the original article text untouched. Apply corrections programmatically. This avoids the "rewrite the whole section" problem entirely.

```json
{
  "name": "report_corrections",
  "parameters": {
    "type": "object",
    "properties": {
      "corrections": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "original_text": {"type": "string"},
            "corrected_text": {"type": "string"},
            "reason": {"type": "string"},
            "web_source_index": {"type": "integer"}
          }
        }
      },
      "no_corrections_needed": {"type": "boolean"}
    }
  }
}
```

Then programmatically apply `str.replace(original_text, corrected_text)` -- citations in untouched text are preserved perfectly.

---

## 7. Summary of Key Findings

| Capability | M2.7 Support | Notes |
|---|---|---|
| response_format: json_schema | NO (native API) / YES (OpenRouter, third-party) | Only MiniMax-Text-01 on native API |
| stream + response_format | INCOMPATIBLE | Hard API error |
| Tool calling | YES | Full support, all API variants |
| Interleaved thinking | YES | Must preserve reasoning in history |
| Reasoning effort control | YES (Anthropic API only) | `budget_tokens` parameter |
| max_completion_tokens | 131,072 max | Default 10,240 for M2 family |
| Temperature recommendation | 1.0 | Per MiniMax docs for reasoning models |
| MCP search | Available | Token Plan users, separate from pipeline API |
| Citation preservation | NOT RELIABLE | No structural citation support; must mitigate via prompt engineering or architecture |

---

## 8. Actionable Recommendations for Our Pipeline

### Immediate (low effort)

1. **Increase `MINIMAX_VERIFY_MAX_TOKENS` from 8192 to 12288** -- gives more room for thinking + output, reducing truncation risk.

2. **Add explicit marker enumeration to the verification prompt** -- dynamically list all `[N]` markers found in the input section and instruct the model to preserve each one.

3. **Set `temperature=1.0` explicitly** -- matches MiniMax's recommendation for reasoning models.

### Medium-term (moderate effort)

4. **Switch to Anthropic-compatible API** with `budget_tokens` to cap reasoning at ~2000-3000 tokens, leaving more budget for the actual corrected text.

5. **Improve the post-processing repair** -- use sentence-level diffing instead of paragraph-level matching to re-insert lost markers more accurately.

### Longer-term (higher effort, highest reliability)

6. **Option D: Tool-based correction architecture** -- have M2.7 report corrections as structured tool calls instead of rewriting entire sections. Apply corrections programmatically to preserve all original markers perfectly. This eliminates the citation-dropping problem at the architecture level rather than fighting it with prompts.
