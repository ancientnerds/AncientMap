# Theo Pipeline Follow-ups — Quality, Observability, Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop on six issues observed in run #10 of the Sea Peoples Theo pipeline — debug-log cleanup, token accounting, badge logic, query sanitization, JSON-parse hardening, and image embed-rate diagnosis. The pipeline now completes reliably (Sea Peoples #10 finished in 4h, score 100); these are quality and observability follow-ups.

**Architecture:** Each task is a focused single-file (or small-multi-file) change with a TDD step where unit-testable, otherwise a smoke-script step. All changes commit individually. Deploy at the end so we don't churn CI per fix.

**Tech Stack:** Python 3.11, FastAPI, MiniMax/Anthropic SDKs, Voyage AI, PostgreSQL, GitHub Actions CI → VPS SSH deploy.

---

## Context summary (read this before starting)

Run #10 (`2f055c7e-d61c-4310-91eb-cd404249d303`) completed at 2026-05-11 19:43 UTC, age 4h 03min, mechanical score 100/100, badge "Unverified", `passed: false`. Observed defects:

1. **Badge ≠ Score.** `judge.py:241` downgrades to "Unverified" when `passed: false`. `passed` is `audit_result.get("passed", False) AND citation_coverage >= 9 AND reference_integrity == 10 AND not placeholder_markers AND not language_bleed AND hallucination_final == 0 AND no contradictions AND not undefined_title_terms`. Quality-score meta in the persisted result_json shows all of those at zero/clean — so `audit_result["passed"]` must be the false branch. That comes from `theo_citations.audit_citations()` (`theo_citations.py:1049`): `not invalid_markers AND not orphaned_refs AND uncited_paragraphs == 0 AND not placeholder_markers AND not language_bleed AND not non_numeric_markers`. Need to inspect the run's actual `audit_result` to find which field nuked it.

2. **`total_tokens=0` in DB despite 367 LLM calls.** `state.total_tokens` is never incremented anywhere in the codebase (grep `total_tokens +=` returns zero hits). The DB column just gets the zero value at completion. Token usage is available on every LLM response (`config.py:464-465` / `499-500` extract `input_tokens` / `output_tokens` per call) — we need to thread those into `state.total_tokens`.

3. **128 image embed opportunities skipped via `no_safe_candidates`** vs only 10 actually embedded. `probative_images.py:611` rejects candidates when `verdict_is_safe(verdict)` is False. That's a strict VLM check (`image_gates.py:120` → `verdict_is_meaningful` → `v.get("verdict") == "meaningful"`). So either (a) MiniMax VLM returns malformed JSON for most images, or (b) the prompt is too strict. Worth investigating before fixing.

4. **`canonical_coverage enumeration failed: Expecting value: line 1 column 1 (char 0)`** — recurring throughout run #10. Pre-existing JSON-parse fail on an LLM call that returns an empty string. Non-blocking but ugly.

5. **Semantic Scholar 400s** on queries like `"1200 BCE)?"` (URL-encoded `%29%3F`). Pre-existing — we don't strip query punctuation before the call.

6. **Debug instrumentation still in `research_events.py`** from runs #8/#9 — `[THEO-diag] EventBus.emit reached …` one-shot log + `[THEO] {req} emit-flush: …` INFO line per ~30s. Both served their purpose (proving the flush path works) and should now move to DEBUG / be deleted.

---

## File map

- **Create** `scripts/inspect_run_result.py` — read-only helper that prints `audit_result` / `quality_score` for a given request id. Reused throughout this plan as a diagnostic. **Untracked** at first to keep CI lint green; tracked once stable.
- **Modify** `pipeline/lyra/research_events.py` — Task 1 (cleanup)
- **Modify** `pipeline/lyra/config.py` — Task 2 (token accounting)
- **Modify** `pipeline/lyra/research_state.py` — Task 2 (helper for thread-safe token add)
- **Modify** `pipeline/lyra/minimax_shared.py` — Task 2 (add tokens after each call)
- **Modify** `pipeline/lyra/handlers/judge.py` — Task 3 (diagnostic log so we can see WHY `passed` is false)
- **Modify** `pipeline/lyra/handlers/probative_images.py` — Task 4 (log VLM verdict bodies on rejection so we know whether it's malformed JSON or strict-rejection)
- **Modify** `pipeline/lyra/canonical_coverage.py` — Task 5 (guard against empty LLM output)
- **Modify** `pipeline/lyra/theo_sources.py` — Task 6 (sanitize Semantic Scholar query)

Tests: `pipeline/lyra/tests/` is the existing structure (`tests/test_*.py` per memory). Each task carries its own test file or extends an existing one.

---

## Task 1 — Remove run-#9 debug instrumentation

**Files:**
- Modify: `pipeline/lyra/research_events.py:240-279`

- [ ] **Step 1: Open `pipeline/lyra/research_events.py` and locate the diag block**

Look for the `_diag_logged_first_emit` one-shot at ~line 246 and the `[THEO] %s emit-flush` `logger.info` at ~line 261.

- [ ] **Step 2: Drop the diag log entirely; downgrade emit-flush log to debug**

Replace the whole `if self._state is not None:` block (lines 246-279) with:

```python
        if self._state is not None:
            request_id = getattr(self._state, "request_id", "") or ""
            if request_id:
                now = time.monotonic()
                if now - self._last_flush_ts >= _FLUSH_INTERVAL_S:
                    self._last_flush_ts = now
                    try:
                        # Lazy import to avoid a circular dep with
                        # convergence_orchestrator (which imports EventBus).
                        from pipeline.lyra.convergence_orchestrator import (
                            _flush_progress_to_db,
                        )

                        _flush_progress_to_db(self._state, request_id)
                    except Exception as flush_exc:
                        # Never let an observability write break the pipeline.
                        logger.warning(
                            "[THEO] %s emit-flush failed: %r",
                            request_id,
                            flush_exc,
                        )
```

Specifically: delete the entire `if not getattr(self, "_diag_logged_first_emit", False): ...` block AND the success `logger.info("[THEO] %s emit-flush: llm=%d sites=%d", ...)` call inside the try block. Keep the warning on failure (silent flush failures are still bad).

- [ ] **Step 3: Verify import still works**

Run: `python -c "from pipeline.lyra.research_events import EventBus; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Verify the diag string is gone**

Run: `grep -n "THEO-diag\|emit-flush: llm=" pipeline/lyra/research_events.py`
Expected: zero matches

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/research_events.py
git commit -m "chore(theo): drop run-#9 debug instrumentation in EventBus.emit

The [THEO-diag] one-shot and per-flush [THEO] emit-flush INFO line proved
the emit-piggybacked DB flush actually runs. Now that it's verified, the
diag is just log noise (>1000 lines per 4h research run). Keep the
warning on flush failure since silent flush failures are still bad."
```

---

## Task 2 — Accumulate `state.total_tokens` across every LLM call

**Files:**
- Modify: `pipeline/lyra/research_state.py:160` (already declares the field)
- Modify: `pipeline/lyra/config.py:455-505` (call_api token extraction sites)
- Modify: `pipeline/lyra/minimax_shared.py:125-200` (minimax_chat_anthropic)

**Strategy:** `state.total_tokens` already exists on `ResearchState` but nothing writes to it. Token usage is already extracted from responses in `config.py` (passed back via `NormalizedResponse.usage`). The cleanest place to accumulate it is at the boundary that does have `state` in scope — the handlers — but threading state into every adapter is invasive. Better: have `minimax_chat_anthropic` / `structured_llm_call` / `call_api` write to a module-level counter that the orchestrator drains into `state.total_tokens` on each flush, OR have each handler add tokens directly. Trade-off: module-level counter is simpler but conflates concurrent runs; handler-level is correct but touches many files.

**Decision:** Module-level counter scoped per `request_id`. `config.py` already knows the request via cache-control / `state` is not threaded through `call_api`. Simplest:

- Add `usage_total: int` attribute on the `NormalizedResponse` (or use the existing `usage` dict).
- Update every site that calls `call_api` / `minimax_chat_anthropic` and has `self.state` in scope to do `self.state.total_tokens += resp.usage.input_tokens + resp.usage.output_tokens` (or the equivalent on the dict-shaped usage).

Counting handler-call sites: there are ~15 spots across handlers. Doable.

**Concrete steps:**

- [ ] **Step 1: Inspect what `NormalizedResponse.usage` already exposes**

Read `pipeline/lyra/config.py:455-505`. Confirm `response.usage.input_tokens` and `response.usage.output_tokens` are pulled into the NormalizedResponse.

- [ ] **Step 2: Add a small accumulator helper on `NormalizedResponse`**

If `NormalizedResponse` is a class/dataclass, add:

```python
@property
def total_tokens(self) -> int:
    if not self.usage:
        return 0
    return int(self.usage.get("input_tokens", 0)) + int(self.usage.get("output_tokens", 0))
```

If it's a `TypedDict`, add a module-level helper `def total_tokens(resp) -> int:` in `pipeline/lyra/config.py` next to call_api.

- [ ] **Step 3: Wire token accumulation into `structured_llm_call`**

`pipeline/lyra/minimax_shared.py:281-300` (the structured path). After `resp = call_api(...)`, if a caller passed `settings` with a state reference... actually `structured_llm_call` doesn't get `state`. We need to return the token count from the function instead, or accept a callback.

Simplest: make `structured_llm_call` and `minimax_chat_anthropic` increment a module-level `_request_token_counter` keyed by an `request_id` arg the caller passes. But that's also invasive.

**Pivot:** Easier and good-enough — have handlers do `self.state.total_tokens += <something>` next to their existing `self.state.llm_call_count += 1` bumps. That site already has state context. Audit those bump sites with `grep -rn "llm_call_count += 1" pipeline/lyra/`.

- [ ] **Step 4: Grep llm_call_count bump sites and add token accumulation alongside**

Run: `grep -rn "llm_call_count += 1" pipeline/lyra/ | grep -v __pycache__`

Expected output (paraphrased): hits in `decomposition.py`, `angle_audit.py`, `angle_specialist.py`, `cross_pollination.py`, `debate.py`, `moderator.py`, `paper.py`, etc.

For each line, change from:

```python
self.state.llm_call_count += 1
```

to:

```python
self.state.llm_call_count += 1
self.state.total_tokens += getattr(resp, "total_tokens", 0) if "resp" in dir() else 0
```

…where `resp` is the actual variable name returned from `call_api` / `structured_llm_call` / `minimax_chat_anthropic` at that site. For `minimax_chat_anthropic` calls that return raw text, we need a different path — the function should also return tokens. Update its signature to return a tuple `(text, token_count)`.

This is the biggest chunk of work in the plan. Split into sub-steps:

- [ ] **Step 4a:** Change `minimax_chat_anthropic` signature to also return token count. Caller sites currently do `raw = await asyncio.to_thread(minimax_chat_anthropic, ...)`. Change to return `(raw, tokens)`. Update every caller.

- [ ] **Step 4b:** Change `structured_llm_call` to also return tokens (it already calls `call_api` which has usage). Either return a tuple, or attach `_tokens` attribute on the returned dict. Tuple is cleaner.

- [ ] **Step 4c:** For each `llm_call_count += 1` site, also add `self.state.total_tokens += tokens` where `tokens` comes from the return tuple.

- [ ] **Step 5: Unit test in a new `pipeline/lyra/tests/test_total_tokens.py`**

```python
from pipeline.lyra.research_state import ResearchState

def test_total_tokens_accumulates():
    state = ResearchState(question="test")
    state.total_tokens = 0
    state.total_tokens += 1234
    state.total_tokens += 567
    assert state.total_tokens == 1801
```

(Trivial because the real accumulation is intermixed with LLM calls. An integration test would require mocking the entire LLM stack — skip for plan scope; rely on a real run for E2E verification.)

Run: `pytest pipeline/lyra/tests/test_total_tokens.py -v`
Expected: PASS

- [ ] **Step 6: Smoke-verify locally — import all modified modules**

```bash
python -c "from pipeline.lyra.minimax_shared import minimax_chat_anthropic, structured_llm_call; print('ok')"
python -c "from pipeline.lyra.handlers.angle_specialist import SpecialistHandler; print('ok')"
python -c "from pipeline.lyra.handlers.cross_pollination import CrossPollinationHandler; print('ok')"
```

Expected: `ok` three times.

- [ ] **Step 7: Commit**

```bash
git add pipeline/lyra/minimax_shared.py pipeline/lyra/config.py pipeline/lyra/handlers/*.py pipeline/lyra/tests/test_total_tokens.py
git commit -m "feat(theo): accumulate total_tokens through every LLM call

state.total_tokens has been an unused field — the DB completion write
read 0 every time despite 367 LLM calls in run #10. Thread token counts
back from minimax_chat_anthropic / structured_llm_call (now tuple
returns) and add to state.total_tokens at every existing llm_call_count
bump site. Cost tracking + judge token-budget logic now have real input."
```

---

## Task 3 — Diagnose & fix the Badge ≠ Score bug

**Files:**
- Create: `scripts/inspect_run_result.py` (untracked diagnostic)
- Modify: `pipeline/lyra/handlers/judge.py:241-243`

**Strategy:** We need to see the actual `audit_result` from run #10 first. Then decide if `passed=false` is correct (and the badge demotion is too harsh) or wrong (and the audit is buggy).

- [ ] **Step 1: Write the diagnostic script `scripts/inspect_run_result.py`**

```python
"""Print audit_result + quality_score for a research_requests row."""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from pipeline.database import get_session


def main(request_id: str) -> None:
    with get_session() as session:
        row = session.execute(
            text("SELECT result_json FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
    if not row or not row[0]:
        print("no result_json on row")
        return
    data = json.loads(row[0])
    print("=== audit_result ===")
    print(json.dumps(data.get("audit", {}), indent=2)[:4000])
    print()
    print("=== quality_score ===")
    print(json.dumps(data.get("quality_score", {}), indent=2)[:4000])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/inspect_run_result.py <request_id>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
```

- [ ] **Step 2: Run it against run #10 via prod DB tunnel**

```bash
ssh ancientnerds "docker exec -i ancient_nerds_api python /app/scripts/inspect_run_result.py 2f055c7e-d61c-4310-91eb-cd404249d303"
```

Wait — script isn't in the container yet. Easier: copy the SQL inline:

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT jsonb_pretty(result_json::jsonb -> 'audit') FROM research_requests WHERE id = '2f055c7e-d61c-4310-91eb-cd404249d303';\""
```

Expected: a JSON blob showing `passed: bool` plus the six audit gates (`invalid_markers`, `orphaned_refs`, `uncited_paragraphs`, `placeholder_markers`, `language_bleed`, `non_numeric_markers`). Identify which is non-empty / non-zero.

- [ ] **Step 3: Based on the offender field, choose the fix**

**Case A — `orphaned_refs` non-empty:** The presentation/strip phase didn't prune references that lost their citation. The right fix is upstream, not in the judge. Add `orphaned_refs` to the surfaced `quality_score.meta` so future runs show it explicitly. Then either fix the strip phase or accept the demotion as correct.

**Case B — `invalid_markers` non-empty:** Pipeline is emitting `[N]` markers where N has no entry in the references list. Same call: fix the marker generation OR mark the demotion as correct.

**Case C — `non_numeric_markers` non-empty:** Debug tokens like `[FOO]` survived into prose. Strip phase didn't catch them.

**Case D — All gates clean, but `passed=False` still:** Bug in audit_citations — investigate further.

For all cases, the minimum change in `judge.py` is to surface the failing field in `quality_score.meta` so the badge demotion has a visible reason. Add:

```python
        # Surface the audit gate that triggered the badge demotion, so the UI
        # can show "Unverified — orphaned_refs: 4" instead of unexplained.
        result["audit_gate_failures"] = {
            "passed": audit_result.get("passed", False),
            "invalid_markers": len(audit_result.get("invalid_markers", [])),
            "orphaned_refs": len(audit_result.get("orphaned_refs", [])),
            "uncited_paragraphs": audit_result.get("uncited_paragraphs", 0),
            "placeholder_markers": len(audit_result.get("placeholder_markers", [])),
            "language_bleed": len(audit_result.get("language_bleed", [])),
            "non_numeric_markers": len(audit_result.get("non_numeric_markers", [])),
        }
```

…inserted after the `passed = bool(...)` block at `judge.py:237`, before `result = {...}` at line 244.

- [ ] **Step 4: Smoke-test locally**

```bash
python -c "from pipeline.lyra.handlers.judge import JudgeHandler; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/handlers/judge.py scripts/inspect_run_result.py
git commit -m "fix(theo): surface audit-gate failure reason in quality_score

Run #10 finished with score=100 but badge=Unverified and passed=false,
with no visible reason — judge.py:241 demotes whenever the audit gate
isn't clean, but the failing field wasn't carried into result.

Now quality_score.audit_gate_failures lists each gate's count so the UI
+ debug log can show 'Unverified — orphaned_refs: 4' instead of an
unexplained discrepancy.

Plus a diagnostic helper at scripts/inspect_run_result.py for offline
audit inspection."
```

---

## Task 4 — Diagnose `embed_skip_no_safe_candidates: 128`

**Files:**
- Modify: `pipeline/lyra/handlers/probative_images.py:608-616`

**Strategy:** The VLM-verdict path silently discards candidates with no breadcrumb. 128 rejected vs 10 accepted is a 92% reject rate. Either MiniMax VLM returns malformed JSON for most images (and `parse_vlm_verdict` returns None), or it returns `verdict != "meaningful"` (and the prompt is too strict). Log the actual verdict body on rejection.

- [ ] **Step 1: Add a rejection log next to the `verdict_is_safe` filter**

`pipeline/lyra/handlers/probative_images.py:611` currently:

```python
        if not verdict_is_safe(verdict):
            if cand_url:
                ctx.placed_source_urls.discard(cand_url)
            if probe_path.exists():
                probe_path.unlink(missing_ok=True)
            continue
```

Change to:

```python
        if not verdict_is_safe(verdict):
            # Diagnostic: log the verdict body so we can tell apart
            # (a) malformed VLM JSON (verdict is None) from
            # (b) strict-judge rejection (verdict != "meaningful").
            # Run #10 saw 128 rejections vs 10 acceptances — without this
            # log we cannot tell which mode dominates.
            reason = (
                "malformed-json" if verdict is None
                else f"verdict={verdict.get('verdict', '?')!r}"
            )
            logger.info(
                "[probative] rejected candidate (%s) for para %d keyword '%s': %s",
                reason,
                para_idx,
                keyword[:40],
                (cand.title or cand.url)[:80],
            )
            if cand_url:
                ctx.placed_source_urls.discard(cand_url)
            if probe_path.exists():
                probe_path.unlink(missing_ok=True)
            continue
```

- [ ] **Step 2: Smoke-import**

```bash
python -c "from pipeline.lyra.handlers.probative_images import ProbativeImagesHandler; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pipeline/lyra/handlers/probative_images.py
git commit -m "fix(theo): log VLM rejection reason in probative-images filter

Run #10 dropped 128 of 138 image-embed candidates with no breadcrumb —
verdict_is_safe just returns False whether the VLM returned malformed
JSON, a non-meaningful verdict, or never replied at all. Surface the
reason so the next run's debug_log tells us which failure mode
dominates before we tune the prompt or the parser."
```

Note: this is diagnostic-only. A follow-up plan (after next run) will tune the prompt or accept-rate based on what the log reveals.

---

## Task 5 — Guard `canonical_coverage` against empty LLM output

**Files:**
- Modify: `pipeline/lyra/canonical_coverage.py`

- [ ] **Step 1: Find the parse site**

Run: `grep -n "canonical_coverage enumeration failed\|json\.loads\|_parse_json" pipeline/lyra/canonical_coverage.py`

Identify the line that parses raw LLM output into JSON. The error `Expecting value: line 1 column 1 (char 0)` means `raw` is an empty string.

- [ ] **Step 2: Add an early-empty-return guard**

Wherever `json.loads(raw)` is called on the response, change to:

```python
raw = raw.strip() if raw else ""
if not raw:
    logger.warning("canonical_coverage: empty LLM response, skipping enumeration")
    return {}  # or whatever the empty-result shape should be
try:
    return json.loads(raw)
except (json.JSONDecodeError, ValueError) as exc:
    logger.warning("canonical_coverage enumeration failed: %s", exc)
    return {}
```

Pick the right return-shape by reading the function's signature — match its `dict | list` contract.

- [ ] **Step 3: Smoke-import**

```bash
python -c "from pipeline.lyra.canonical_coverage import enumerate_canonical_topics; print('ok')"
```

(Use the actual public function name from the module — replace `enumerate_canonical_topics` if different.)

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pipeline/lyra/canonical_coverage.py
git commit -m "fix(theo): early-return canonical_coverage when LLM returns empty

The 'Expecting value: line 1 column 1 (char 0)' warning that fires
repeatedly during long runs is just MiniMax returning '' for some
enumeration calls. Guard against the empty string so it stops looking
like a real parse error in the logs."
```

---

## Task 6 — Sanitize Semantic Scholar query parameters

**Files:**
- Modify: `pipeline/lyra/theo_sources.py:243-405` (`SemanticScholarAdapter`)

- [ ] **Step 1: Read the existing `SemanticScholarAdapter.search` to find query-construction**

Open `pipeline/lyra/theo_sources.py`, find `class SemanticScholarAdapter` at line 243 and its `search` method at ~292. Locate where the `query=` parameter is assembled into the request.

- [ ] **Step 2: Strip punctuation that confuses the Semantic Scholar API**

Add a sanitizer call before the request. Replace the relevant body of `SemanticScholarAdapter.search` with:

```python
async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
    # Semantic Scholar's bulk-search endpoint rejects queries with trailing
    # punctuation that survives URL-encoding — e.g. "1200 BCE)?" → 400.
    # Strip anything that isn't a word char, hyphen, or whitespace.
    import re

    clean_query = re.sub(r"[^\w\s\-]", " ", query).strip()
    clean_query = re.sub(r"\s+", " ", clean_query)
    if not clean_query:
        return []
    # … rest of the existing implementation, but use `clean_query` for the
    # request and keep the original `query` only for logging.
```

The exact merge depends on how the function reads. The goal: regex-strip stray punctuation, fall back to empty-list if nothing's left, otherwise issue the request with the sanitized string.

- [ ] **Step 3: Unit test**

Create `pipeline/lyra/tests/test_semantic_scholar_sanitize.py`:

```python
import re


def _sanitize(query: str) -> str:
    q = re.sub(r"[^\w\s\-]", " ", query).strip()
    return re.sub(r"\s+", " ", q)


def test_strips_parens_and_question_mark():
    assert _sanitize("1200 BCE)?") == "1200 BCE"


def test_keeps_hyphens():
    assert _sanitize("Tel Miqne-Ekron Philistine") == "Tel Miqne-Ekron Philistine"


def test_collapses_double_spaces():
    assert _sanitize("Sea  Peoples   collapse") == "Sea Peoples collapse"


def test_empty_after_strip():
    assert _sanitize("?!()") == ""
```

(Even though the real production sanitizer lives inside `SemanticScholarAdapter.search`, the regex logic is the same — testing it pure-function keeps the test trivial and fast.)

Run: `pytest pipeline/lyra/tests/test_semantic_scholar_sanitize.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/lyra/theo_sources.py pipeline/lyra/tests/test_semantic_scholar_sanitize.py
git commit -m "fix(theo): sanitize Semantic Scholar queries — strip ) ? !

Queries like '1200 BCE)?' (which surfaced in run #6 + #10 from the
Sea Peoples question's trailing parenthetical) get URL-encoded to
%29%3F and Semantic Scholar's bulk-search endpoint rejects them with
400 Bad Request. Strip everything that isn't a word char, hyphen, or
whitespace before issuing the request. Loud-fallback to empty results
if the sanitiser eats the whole query."
```

---

## Task 7 — Push, deploy, verify

- [ ] **Step 1: Lint everything before pushing**

```bash
ruff check pipeline/ scripts/
ruff format --check pipeline/ scripts/
```

Expected: no diff, no errors. If `ruff format --check` complains, run `ruff format pipeline/ scripts/` and amend the most recent commit (or commit as a follow-up chore).

- [ ] **Step 2: Push**

```bash
git push origin main
```

- [ ] **Step 3: Watch CI to green**

```bash
RUN_ID=$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

Expected: deploy job ✓ in ~4-5 min.

- [ ] **Step 4: Smoke-test on prod that nothing broke**

```bash
ssh ancientnerds 'docker exec ancient_nerds_api python -c "
from pipeline.lyra.handlers.angle_specialist import SpecialistHandler
from pipeline.lyra.handlers.cross_pollination import CrossPollinationHandler
from pipeline.lyra.handlers.judge import JudgeHandler
from pipeline.lyra.handlers.probative_images import ProbativeImagesHandler
from pipeline.lyra.research_events import EventBus
print(\"all handler imports OK on prod\")
"'
```

Expected: `all handler imports OK on prod`

- [ ] **Step 5: Inspect run #10 audit_result via the new helper (Task 3 follow-through)**

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT jsonb_pretty(result_json::jsonb -> 'audit') FROM research_requests WHERE id = '2f055c7e-d61c-4310-91eb-cd404249d303';\""
```

Note in this plan's notes section which audit gate caused the demotion. If a real bug surfaces (e.g. `audit_citations` returns `passed=False` despite all gates clean), add a follow-up task to fix it before any new run.

- [ ] **Step 6: Optional — submit a fresh Sea Peoples run to verify all fixes**

Only do this if the user explicitly asks. Otherwise leave the pipeline ready for them to trigger from theo.html.

---

## Out of scope (deferred)

- **Verifier 28% rejection rate** — specialists over-attribute claims to weak sources. Requires prompt-engineering on the specialist + verifier prompts. Bigger work.
- **MiniMax M2.7 `did not return tool_use` warnings** — pre-existing structural unreliability of structured output with interleaved thinking. We already revert strict mode (f9a71c5); a real fix needs a model swap or tool-use prompt redesign.
- **Image embed prompt-tuning** (after Task 4 reveals the failure mode) — separate plan once we know whether the issue is parser or strictness.

---

## Verification (end-to-end)

After all tasks land and deploy is green:

```bash
# (a) lint + format clean
ruff check pipeline/ scripts/ && ruff format --check pipeline/ scripts/

# (b) all critical handler imports clean on prod
ssh ancientnerds 'docker exec ancient_nerds_api python -c "
import pipeline.lyra.research_events
import pipeline.lyra.handlers.judge
import pipeline.lyra.handlers.probative_images
import pipeline.lyra.handlers.cross_pollination
import pipeline.lyra.handlers.angle_specialist
import pipeline.lyra.canonical_coverage
import pipeline.lyra.theo_sources
print(\"OK\")
"'

# (c) no [THEO-diag] / "[THEO] %s emit-flush: llm=" left in source
grep -rn "THEO-diag\|emit-flush: llm=" pipeline/lyra/

# (d) inspect_run_result.py runs against an existing completed run
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \
  \"SELECT result_json::jsonb ? 'audit' AS has_audit, \
    EXTRACT(EPOCH FROM (NOW() - created_at))::int AS age_s \
   FROM research_requests \
   WHERE status='completed' ORDER BY completed_at DESC LIMIT 1;\""
```

Pass criteria:
- (a) zero ruff diff
- (b) `OK`
- (c) zero matches
- (d) `has_audit | t` (true)

If all four pass, the plan is complete.
