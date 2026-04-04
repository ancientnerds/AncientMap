# Theo Phase 3: Prompt Tuning + 3-Stage Research UI

## Context

Phase 2 built the 8-stage agentic pipeline with 33 specialists, 10 source adapters, and 5 academic tiers. Testing shows strong output quality (133 citations, 51 references, proper academic tone on fringe topics) but prompts need tuning and the frontend needs a guided workflow.

Branch: `feature/theo-agentic-pipeline`
Spec: `docs/superpowers/specs/2026-04-04-theo-agentic-pipeline-design.md`
Test outputs: `scripts/batch_test_output/shining_ones_note.md`, `note_test_v2.md`

## Phase 3A: Prompt Tuning

### What to analyze
- Read both test papers for content quality issues
- Check all 12 prompts in `pipeline/lyra/prompts/theo_*.txt` against actual M2.7 behavior
- Test output from Shining Ones (fringe) and Obsidian Trade (mainstream) as reference

### Known prompt issues
1. **Paper assembly**: M2.7 sometimes produces paragraphs without [N] citations even when reference map is provided. Need stronger instruction about citation density.
2. **Source audit**: JSON truncation was fixed with batching + token budget, but audit prompt could be more concise to save tokens.
3. **Synthesis critic**: Passed on first try for Shining Ones — may need to be stricter about checking citation preservation.
4. **Specialist analysis**: Some specialists produce generic findings not grounded in the specific sources provided. Prompt should emphasize "cite source IDs for EVERY finding."

### Audit heuristic
- File: `pipeline/lyra/theo_citations.py` audit_citations()
- Currently exempts paragraphs starting with structural patterns
- Still 22 false positives — need more patterns or a smarter approach (e.g., paragraph must contain a factual assertion to require citation)

## Phase 3B: 3-Stage Research UI

### Stage 1 — Topic + Relevancy
**What the user sees:**
- Large text input for research question
- Tier selector (Research Brief / Research Note / Journal Article / Literature Review / Thesis Chapter) with time estimates
- "Check Topic" button

**What happens:**
- Calls `POST /theo/check-relevance` with the question
- Backend runs just the relevancy gate (quick M2.7 call, ~2-3 seconds)
- Returns `{relevant: true/false, reason: "..."}`
- If relevant: green checkmark, "Next" button activates
- If not relevant: red message with reason, suggest rephrasing

**New API endpoint needed:**
```python
@router.post("/check-relevance")
async def check_relevance(body: RelevanceCheckRequest):
    # Run TheoPipeline._check_relevance() standalone
    return {"relevant": bool, "reason": str}
```

### Stage 2 — Specialist Selection
**What the user sees:**
- Toggle: "Auto-select specialists" (default ON) / "Choose manually"
- If auto: brief explanation that specialists are chosen based on question keywords
- If manual: 33 specialists displayed as cards/chips grouped by category:
  - Archaeological Core (18)
  - Interdisciplinary Science (11)
  - Fringe / Alternative (4)
- Each specialist card shows: name, title, domain, 1-line perspective
- Checkboxes to include/exclude
- "Next" button

**Data source:** Export `SPECIALIST_POOL` info via a new API endpoint or embed it in the frontend as static data.

### Stage 3 — Review & Launch
**What the user sees:**
- Summary: question, tier, specialist mode
- If auto mode: shows which specialists WILL be selected (run selection algorithm client-side or preview via API)
- Prompt writing tips panel:
  - "Name specific sites, periods, and civilizations"
  - "Include the hypothesis you want investigated"
  - "Mention specific texts or sources if relevant"
  - "Ask about competing theories to get debate"
- "Start Research" button → submits to `POST /theo/research`

**Updated API request body:**
```python
class ResearchSubmitRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)
    effort: str = Field(default="article")
    force_include: list[str] = Field(default_factory=list)  # specialist IDs
    force_exclude: list[str] = Field(default_factory=list)  # specialist IDs
```

### Files to modify
- `api/routes/theo.py` — add check-relevance endpoint, update research body
- `api/services/theo_worker.py` — pass force_include/force_exclude to pipeline
- `pipeline/lyra/theo_pipeline.py` — accept and use force_include/force_exclude in Stage 1
- `ancient-nerds-map/src/pages/TheoPage.tsx` — complete redesign as 3-step wizard
- `ancient-nerds-map/src/components/theo/TheoResearchLive.tsx` — may need updates for new flow

### Design notes
- Follow existing NERV/EVA visual style from the mockup
- Each stage should feel like a step in a research process, not a form
- The specialist cards should look like ID badges or dossiers
- Mobile-responsive — stages should stack vertically on small screens
