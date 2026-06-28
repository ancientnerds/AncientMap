# Citation Blockchain — Structured Source Tracking

## Problem

Source_ids exist at the specialist level (every finding has source_ids) but degrade through 5 stages of text-only JSON parsing. By the time claims reach the paper writer, only 16 of 687 sources get cited inline. The pipeline has 687 references but uses 16 — a 97.7% citation loss rate.

Root cause: every LLM call in the chain uses `minimax_chat_anthropic()` which returns raw text, parsed with `_parse_json()`. If the LLM omits `source_ids` from its JSON output, the code silently accepts it. There's no schema enforcement, no validation, no retry.

The infrastructure for structured output already exists in `pipeline/lyra/config.py` (`_build_structured_output_tool()`, `_extract_tool_use_json()`, `call_api()` with `response_format` parameter) but is not used by any pipeline handler.

## Solution

Enforce structured output with `required: ["source_ids"]` at every LLM call that produces claims. Every claim carries its sources from birth (specialist) through death (paper). Zero silent drops.

## Architecture

### 1. New utility: `structured_llm_call()`

**File:** `pipeline/lyra/minimax_shared.py`

A new function that wraps the existing `call_api()` infrastructure:

```python
async def structured_llm_call(
    system: str,
    user_msg: str,
    schema: dict,
    max_tokens: int,
    settings,
) -> dict:
```

- Accepts a JSON schema dict with `required` fields
- Uses the tool-use trick for MiniMax (`_build_structured_output_tool`)
- Uses native `response_format` for Anthropic backend
- Returns parsed, validated dict
- On parse failure: retry once, then fall back to text parsing with warning log
- All pipeline handlers switch from `minimax_chat_anthropic()` + `_parse_json()` to this function

### 2. JSON schemas per stage

**File:** `pipeline/lyra/schemas.py` (new file)

Define schemas as Python dicts, one per pipeline stage. All claim objects have `"source_ids"` in their `required` array.

Schemas:
- `SPECIALIST_FINDINGS_SCHEMA` — `findings[].source_ids` required
- `SYNTHESIS_SCHEMA` — `consensus_claims[].source_ids`, `unique_insights[].source_ids` required
- `DEBATE_CHALLENGE_SCHEMA` — `strengthening_suggestions[].source_ids` required
- `DEBATE_DEFENSE_SCHEMA` — `incorporations[].source_ids` required
- `MODERATOR_SCHEMA` — `final_claims[].source_ids`, `revised_claims[].source_ids`, `speculative_claims[].source_ids` required

### 3. Handler refactoring

Each handler replaces its LLM call pattern:

**Before:**
```python
raw = await asyncio.to_thread(minimax_chat_anthropic, system, user_msg, max_tokens, settings)
parsed = self._parse_json(raw)
```

**After:**
```python
parsed = await structured_llm_call(system, user_msg, SCHEMA, max_tokens, settings)
```

Handlers to refactor:
- `angle_specialist.py` — specialist analysis calls
- `synthesis.py` — synthesis call
- `debate.py` — challenge and defense calls
- `moderator.py` — moderation call
- `cross_pollination.py` — cross-angle analysis call
- `decomposition.py` — angle decomposition call

### 4. Paper section citation audit + retry

**File:** `pipeline/lyra/handlers/paper.py`

After each section writer LLM call (investigation, connecting, other side, assessment), count `[N]` markers in the output. If a section has fewer than 1 citation per 200 words:

1. Log warning: `"Section '{title}' has {n} citations in {words} words — below threshold"`
2. Re-prompt the same section with prepended instruction: `"IMPORTANT: The previous draft had too few citations. Every factual claim MUST include its [N] marker from the input claims. Cite generously — at least one citation per 1-2 sentences."`
3. One retry max. If retry still sparse, ship it and log.

### 5. What stays the same

- Paper prose LLM calls remain text output (they write narrative, not JSON)
- `_format_claims_for_prompt()` still embeds `[N]` markers in claim text
- `_collect_all_claims()` still converts source_ids to `[N]` markers via `sid_to_num`
- The reference list generation at the bottom of the paper is unchanged
- `minimax_chat_anthropic()` remains available for non-structured calls (hook writing, paper prose)

## Data Flow

```
Specialist → findings with source_ids (ENFORCED by schema)
    ↓
Synthesis → consensus/contested/unique with source_ids (ENFORCED)
    ↓
Debate → suggestions with source_ids (ENFORCED)
    ↓
Moderator → final/revised/speculative with source_ids (ENFORCED)
    ↓
Paper _collect_all_claims → source_ids → [N] markers via sid_to_num
    ↓
Paper _format_claims_for_prompt → "claim text [2] [45]"
    ↓
Section writer LLM → prose with [N] markers (TEXT output, audited)
    ↓
Citation audit → if sparse, retry once
    ↓
Final paper with inline citations
```

## Files to create/modify

| File | Action | What |
|------|--------|------|
| `pipeline/lyra/schemas.py` | CREATE | All JSON schemas |
| `pipeline/lyra/minimax_shared.py` | MODIFY | Add `structured_llm_call()` |
| `pipeline/lyra/handlers/angle_specialist.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/synthesis.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/debate.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/moderator.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/cross_pollination.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/decomposition.py` | MODIFY | Use structured call |
| `pipeline/lyra/handlers/paper.py` | MODIFY | Add citation audit + retry |

## Verification

1. Run Shining Ones test prompt
2. Check: every `consensus_claims` entry in synthesis has non-empty `source_ids`
3. Check: every `final_claims` entry in moderator has non-empty `source_ids`
4. Check: inline citation count in final paper body (target: >50, was 16)
5. Check: citation audit logs — did any sections trigger retry?
6. Compare citation density: old paper (16/14632 words = 1 per 914 words) vs new paper (target: 1 per 100-200 words)
