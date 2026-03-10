# Lyra Structured Output — Test Suite Results & Lessons Learned

**Date**: 2026-03-10
**Branch**: `feature/lyra-structured-output`
**Final Result**: 48/48 tests PASS (100%) with Mercury LLM judge

## Test Suite Summary

```
SUMMARY
  ✓ basic: 4/4 passed
  ✓ site_refs: 5/5 passed
  ✓ coordinates: 3/3 passed
  ✓ news_video: 5/5 passed
  ✓ transcripts: 3/3 passed
  ✓ articles: 2/2 passed
  ✓ empires: 3/3 passed
  ✓ images: 2/2 passed
  ✓ links_flags: 3/3 passed
  ✓ radar: 3/3 passed
  ✓ channels: 2/2 passed
  ✓ edge_cases: 5/5 passed
  ✓ multi_turn: 3/3 passed
  ✓ full_pipeline: 5/5 passed
  Total: 48 passed, 0 failed
  Time: 695.3s
  Judge pool: calls=48 rate_limited=0 free_keys=0
```

## Iteration History

| Run | Pass Rate | Blocker | Fix Applied |
|-----|-----------|---------|-------------|
| 1 | 0/48 judge working | Mercury judge HTTP 400 on every call | Model name `mercury-coder-small-beta` defunct → changed to `mercury-2` |
| 2 | 0/48 judge working | Judge returns empty `{}` — no scores | `max_tokens=1024` too small, reasoning consumed entire budget → increased to `max_tokens=4096` |
| 3 | 47/48 | "Channel-specific transcript" empty response | `complete()` used `max_tokens=32000`, exhausted rate limit → capped to `min(self.max_tokens, 4096)` |
| 4 | 47/48 | "Long complex query" 18 unresolved guillemet markers | Point 2 fallback streamed raw text without stripping markers → collect text, strip, then yield |
| 5 | 47/48 | Temperature `0.75` for all calls (user reported from dashboard) | Added `temperature=0.1` for structured output + judge calls |
| 6 | **48/48** | None | Clean run, 100% pass rate |

## Lessons Learned

### Mercury / Inception Labs API

| Lesson | Detail |
|--------|--------|
| Model names go defunct without warning | `mercury-coder-small-beta` stopped working mid-development. Current valid models: `mercury`, `mercury-2`, `mercury-coder`, `mercury-coder-small`, `mercury-edit`, `mercury-small`. Always verify with curl. |
| `reasoning_effort="high"` shares the `max_tokens` budget | Reasoning tokens and completion tokens come from the same pool. With `max_tokens=1024`, reasoning consumed ~900 tokens leaving 0 for output → empty responses. Use `max_tokens=4096` for structured output. |
| Cap `complete()` max_tokens separately from streaming | Streaming uses `max_tokens=32000` for long responses, but passing that to `complete()` with `reasoning_effort="high"` burns through Mercury's output token rate limit. Cap at `min(self.max_tokens, 4096)`. |
| Temperature matters per call type | `0.1` for structured output formatting and judge scoring (deterministic). Default `0.75` for creative chat streaming. Don't use the same temperature for everything. |
| `response_format: json_schema` works reliably | Once max_tokens was right, structured output with `strict: true` produced valid JSON 100% of the time — zero parse failures across 48 tests. |

### Structured Output Architecture

| Lesson | Detail |
|--------|--------|
| Guillemet markers are a clean separation of concerns | LLM places `«s0»`, `«c0»` etc. in text, fills structured arrays → backend resolves to markdown links. Avoids fragile regex enrichment on free-form text. |
| Always strip unresolved markers before sending to client | Mercury sometimes outputs markers without matching array entries. Both normal and fallback paths must run `re.sub(r"\u00ab[a-z]+\d+\u00bb", "", text)`. |
| Two injection points need identical handling | Point 1 (normal final response) and Point 2 (forced response at max tool rounds) both need: structured output → expand markers → fallback with marker stripping. Forgetting Point 2 caused the "18 unresolved markers" bug. |
| Fallback text must be collected, then cleaned, then emitted | In streaming fallback paths, collect ALL text first, strip markers, THEN yield as a single diffusion event. Yielding incrementally means markers slip through. |

### LLM-as-Judge Testing

| Lesson | Detail |
|--------|--------|
| Structured output eliminates judge parse failures | Previous MiniMax judge had 30% JSON parse failures. Mercury with `response_format: json_schema` had 0% failures across 48 calls. |
| Key pool rotation with cooldown prevents rate limiting | `_JudgeKeyPool` with round-robin + 60s cooldown kept all 48 judge calls successful with 0 rate limits. |
| Separate structural checks from LLM judge | 14 regex-based structural checks catch formatting bugs deterministically. Judge evaluates semantic quality. Together they cover everything. |
| 4-second delay between tests is sufficient | 48 tests × 4s delay ≈ 700s total. No rate limiting issues at this pace. |

### Development Process

| Lesson | Detail |
|--------|--------|
| Iterative test-fix-retest works | Each fix was targeted from specific test output. Don't try to fix everything at once — let the tests guide you. |
| Schema-first design | Defining `LYRA_RESPONSE_SCHEMA` first made prompts, expansion, validation, and tests all fall into place. Start with the data contract. |
| Frontend simplification | Moved 3 fragile regex enrichment passes (coordinates, flags, YouTube linking) from `lyraContentEnricher.ts` to backend structured output. Backend resolves data; frontend renders. |
| Test the API with curl before writing code | Verifying model availability (`mercury-coder-small` access-restricted vs `mercury-2` working) saved hours of debugging. |

## What Changed

| File | Change |
|------|--------|
| `api/services/lyra_schema.py` | **NEW** — JSON schema, `expand_markers()`, `validate_structured_response()` |
| `api/services/lyra_backends.py` | Added `MercuryBackend.complete()` — non-streaming structured output |
| `api/services/lyra_prompts.py` | Replaced site linking instructions with guillemet marker format |
| `api/services/lyra_agent.py` | Injected structured output at Point 1 (normal) and Point 2 (forced) |
| `ancient-nerds-map/src/components/LyraChatModal.tsx` | Added `empire:` link handler |
| `ancient-nerds-map/src/utils/lyraContentEnricher.ts` | Removed backend-handled enrichment (coords, flags, YouTube) |
| `scripts/test_lyra_quality.py` | **REWRITE** — Mercury judge, 48 tests, 14 structural checks |

## Test Categories (48 tests)

| Category | Count | What It Tests |
|----------|-------|---------------|
| basic | 4 | Greeting, off-topic rejection, follow-up context, conciseness |
| site_refs | 5 | Single site, multiple sites, regional sites, table format, site details |
| coordinates | 3 | Single coords, Machu Picchu ranges, multiple coord links |
| news_video | 5 | Recent discoveries, channel attribution, site-specific news, timestamps, multiple sources |
| transcripts | 3 | Transcript search, timestamp deep-links, channel-specific transcripts |
| articles | 2 | Weekly digest, topic search |
| empires | 3 | Empire military data, empire search, empire context mode |
| images | 2 | Site images with `![title](url)`, author/license attribution |
| links_flags | 3 | Wikipedia links, country flags `flag:XX`, multi-country flags |
| radar | 3 | Radar overview, filtered radar, radar details |
| channels | 2 | List channels, channel count |
| edge_cases | 5 | Long complex query, Unicode names, nonexistent site, single char, empty results |
| multi_turn | 3 | Image follow-up, reference resolution, empire follow-up |
| full_pipeline | 5 | Site context, empire context, news context, multi-tool pipeline, structured output validation |

## Structural Checks (14 total)

| Check | What It Validates |
|-------|-------------------|
| `check_not_empty` | Response has content |
| `check_no_error` | No error in SSE stream |
| `check_markers_resolved` | No `«...»` guillemet markers remain in final text |
| `check_site_links` | `[Name](site:UUID)` format, valid UUID regex |
| `check_coord_links` | `[lat, lon](lyra-coord:lat,lon)`, valid ranges |
| `check_video_links` | `[▶ Channel](lyra-video:INDEX)` format |
| `check_empire_links` | `[Name](empire:POLITY_ID)` format |
| `check_image_format` | `![title](url)` with attribution line |
| `check_external_links` | `[text](https://...)` well-formed |
| `check_country_flags` | `[Name](flag:XX)` format |
| `check_no_bare_uuids` | No raw UUIDs outside proper link syntax |
| `check_conciseness` | Under 3000 chars |
| `check_tools_called` | Expected tools invoked |
| `check_no_hallucinated_ids` | Site UUIDs match SSE `sites` event data |
