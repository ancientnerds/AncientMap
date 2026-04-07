# Journal Quality Assessor — Convergence Loop

**Date:** 2026-04-07
**Scope:** Automated quality assessment + fix loop for journal entries, runs as part of the generation pipeline and retroactively on existing journals.

## Problem

Journal entries consistently have the same categories of errors: garbled proper nouns (Monteppi→Montesiepi, Galano Giati→Galgano Guidotti, Vulcansky Dolman→Volkonsky Dolmen), missing citations, misplaced screenshots, academic citation style leaks, low-quality sources, and overlong sections. Manual assessment catches these but can't scale. The goal is 10/10 quality on every journal, always.

## Solution

A `journal_assessor.py` module with 10 quality dimensions, each scored pass/fail. The assessor runs after journal assembly but before polish/headline. If any dimension fails, targeted fixes are applied and the assessor re-runs. Loop until 10/10 or max 3 iterations. Most fixes use MiniMax M2.7 LLM calls (free via Token Plan).

## Pipeline Integration

```
collect → cluster → [per cluster: Theo research] → assemble → screenshots → ASSESS LOOP → polish → headline → save
```

The loop runs before polish so editorial smoothing covers any fix seams, and before headline so the title/summary reflect corrected content.

## The 10 Dimensions

### D1: Proper Nouns (LLM check + LLM fix)

**Check:** LLM reads the journal body + all source titles/URLs. Identifies every proper noun in the body that doesn't match its corresponding source spelling. Catches garbled names even without exact string match — the LLM understands "Galano Giati" is a corruption of "Galgano Guidotti" from the source context.

**Fix:** LLM outputs a JSON array of `{"find": "...", "replace": "..."}` corrections. Applied mechanically.

**Prompt context:** Full journal body + full source list (titles and URLs).

### D2: Citation Coverage (Mechanical check + LLM fix)

**Check:** Every paragraph >100 chars must contain at least one `[N]` citation. Headings (##), image lines (![]...), and the TLDR are exempt.

**Fix:** LLM receives the uncited paragraph + the full source list and rewrites the paragraph with appropriate `[N]` citations inserted.

### D3: No Academic Citation Style (Mechanical check + LLM fix)

**Check:** Regex scan for `(Author, Year)`, `(Name et al., YYYY)`, `(Name, YYYY)` patterns in body text.

**Fix:** LLM replaces each academic citation with the correct `[N]` number based on matching the author/year to the source list.

### D4: Screenshot Placement (LLM check + LLM fix)

**Check:** For each `![alt](url)` image in the body, the LLM evaluates whether the image's alt text topic matches the surrounding paragraph content (the paragraph immediately before the image).

**Fix:** LLM reorders screenshots — moves each to after the paragraph that best matches its alt text content.

### D5: Source Quality (Mechanical check + LLM fix)

**Check:** Each source URL checked against the blocked domains list (tripadvisor.com, gaia.com, quizlet.com, ancient-origins.net, etc.). Also flag Quizlet, Yahoo Answers, Pinterest, and other low-quality education/social sites.

**Fix:** Remove the low-quality source. LLM re-cites the affected paragraph using remaining valid sources.

### D6: Spelling (Mechanical dictionary + LLM verification)

**Check:** Dictionary of known archaeological misspellings applied first:
- dolman → dolmen (and plural)
- synamic → synodic
- Nufian → Natufian
- Epipaleolithic common misspellings

Then LLM scans for any remaining archaeological term misspellings not in the dictionary.

**Fix:** Mechanical replacement for dictionary matches. LLM corrections for others.

### D7: Citation Format (Mechanical check + Mechanical fix)

**Check:** 
- No `[N, M]` comma patterns (should be `[N] [M]`)
- No bare citation numbers without brackets
- Every `[N]` in body exists in the sources list
- No orphaned sources (in list but never cited in body)

**Fix:** All mechanical — regex normalize commas, remove orphaned sources, strip invalid citations.

### D8: Week Date Accuracy (Mechanical check + Mechanical fix)

**Check:** Title must contain "Week of [Month Day]" where the date matches `week_start` from the DB record.

**Fix:** Mechanical string replacement in title.

### D9: Summary Accuracy (LLM check + LLM fix)

**Check:** LLM compares the TLDR/summary (the italic text at the top) against the corrected body. Flags any proper nouns or claims in the summary that don't match the body.

**Fix:** LLM regenerates the summary from the corrected body — 3-4 sentences covering the top findings.

### D10: Section Balance (Mechanical check + LLM fix)

**Check:**
- No section >400 words (this is a digest, not an essay)
- No section with 0 `[N]` citations
- Total journal body between 1500-4000 words

**Fix:** LLM condenses overlong sections while preserving all citations and key facts.

## Scoring

Each dimension is pass (1) or fail (0). Total score is N/10. Target: 10/10.

The assessor returns:
```python
@dataclass
class AssessmentResult:
    score: int  # 0-10
    passed: bool  # score == 10
    dimensions: dict[str, bool]  # D1-D10 pass/fail
    fixes_applied: list[dict]  # {"dimension": "D1", "find": "...", "replace": "..."}
    iteration: int
```

## Convergence Loop

```python
for iteration in range(MAX_ITERATIONS):  # MAX_ITERATIONS = 3
    result = assess(body, sources)
    if result.passed:
        break
    body = apply_fixes(body, result.fixes_applied)
```

Typical convergence:
- **Iteration 1:** D1 (proper nouns), D6 (spelling), D7 (citation format) fix mechanically + LLM. Most issues resolved. Score: 7-8/10.
- **Iteration 2:** D2 (citation coverage), D4 (screenshots), D9 (summary) fix with LLM. Score: 9-10/10.
- **Iteration 3:** Edge cases. Score: 10/10.

## Retroactive Mode

```python
def reassess_all_journals() -> dict[int, tuple[int, int]]:
    """Re-assess and fix all existing journals. Returns {article_id: (before_score, after_score)}."""
```

Loads each `news_articles` row, runs the assess loop, updates the DB. Reports before/after scores. Can be triggered manually or via a one-off script.

## Blocked Domains (D5 expanded list)

```python
QUALITY_BLOCKED_DOMAINS = {
    # Existing pipeline blocks
    "tripadvisor.com", "gaia.com", "ancient-origins.net", "ancient-code.com",
    "yelp.com", "booking.com", "amazon.com", "ebay.com", "etsy.com",
    # Education/flashcard sites (not scholarship)
    "quizlet.com", "brainly.com", "chegg.com", "coursehero.com",
    # User-generated content
    "yahoo.com", "answers.yahoo.com",
    # Content farms
    "readmultiplex.com", "gregreese.substack.com",
}
```

## Files

| File | Purpose |
|---|---|
| **New: `pipeline/lyra/journal_assessor.py`** | The 10-dimension assessor + fix loop |
| **New: `pipeline/lyra/prompts/journal_assess_nouns.txt`** | LLM prompt for D1 proper noun check |
| **New: `pipeline/lyra/prompts/journal_assess_full.txt`** | LLM prompt for D4, D6, D9, D10 combined check |
| **Modify: `pipeline/lyra/article_generator.py`** | Wire assess loop into pipeline between screenshots and polish |
| **New: `scripts/reassess_journals.py`** | CLI script to run retroactive assessment on all journals |

## LLM Call Budget Per Assessment

| Dimension | LLM calls | When |
|---|---|---|
| D1 (proper nouns) | 1 | Always |
| D2 (citation fix) | 0-3 | Per uncited paragraph |
| D3 (academic style fix) | 0-1 | Only if found |
| D4 (screenshot check) | 1 | Always (combined with D6/D9) |
| D5 (source re-cite) | 0-2 | Per bad source |
| D6 (spelling) | 0 or combined | Combined with D4 |
| D9 (summary) | 1 | Always |
| D10 (condense) | 0-3 | Per overlong section |

**Optimization:** D1 + D4 + D6 + D9 can be combined into a single "full assessment" LLM call that checks proper nouns, screenshot placement, spelling, and summary in one pass. This reduces the typical per-iteration cost to 2-3 calls.

**Typical total per iteration:** 2-4 MiniMax calls. Over 3 iterations: ~6-12 calls. With MiniMax Token Plan being free, this is negligible.

## Success Criteria

- All 7 existing journals score 10/10 after retroactive assessment
- Future journals produced by the pipeline score 10/10 before saving
- The assessor never degrades content quality (fixes don't introduce new errors)
