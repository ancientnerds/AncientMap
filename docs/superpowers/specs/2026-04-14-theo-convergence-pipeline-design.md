# Theo Research Pipeline v2 — Convergence-Based Research Lab

> **Status:** Design spec — pending implementation plan
> **Date:** 2026-04-14
> **Goal:** Replace the fixed-tier, single-shot pipeline with a convergence-based research system that explores topics through multiple angles, iterates until quality is achieved, and writes papers in The Why Files investigative narrative style.

---

## Problem Statement

The current pipeline has structural flaws that produce poor research:

1. **Single-shot query generation** — All search queries generated before seeing any sources. No iterative refinement.
2. **No topic decomposition** — A flat query list causes all sources to skew toward one framing. Speculative questions get debunked instead of explored.
3. **Fixed tiers determine quality** — Brief (1 specialist, no debate) produces garbage. The *question* should determine effort, not the user's tier selection.
4. **Sources determine everything** — Specialists only see what search returned. Bad sources → bad paper. No mechanism to detect source bias.
5. **Lecturing instead of investigating** — Papers moralize about user's questions instead of exploring the topic.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Event-driven state machine | Convergence IS reactive; stages fire when preconditions are met |
| Convergence detection | Specialist consensus | Specialists are the domain experts; they judge when an angle is exhausted |
| Topic decomposition | Hybrid: LLM proposes + validation search | Prevents dead-end angles while leveraging LLM knowledge |
| Rabbit holes | Spawn new angles dynamically | How real research works; 24h deadline prevents infinite expansion |
| Deadline model | Convergence-first, 24h safety net | Research takes as long as it needs; deadline is emergency only |
| Specialist management | Iterative panel with pruning + interdisciplinary bonus | Adapts to research needs; rewards dot-connectors |
| Tier system | Removed entirely | Every task converges naturally; no artificial quality caps |
| Narrative style | The Why Files playbook | Hook → investigation → connections → counter-evidence → honest assessment |
| Concurrency | Global LLM semaphore | Respects MiniMax rate limits across parallel angle research |
| User attachments | Keep (YouTube videos + URLs as seed sources) | Users can point research at specific content |
| Credit system | Deferred (reserve + refund model) | Not in scope for this design |

---

## Architecture: Event-Driven State Machine

### Research Phases

```
DECOMPOSING → EXPLORING → SYNTHESIZING → DEBATING → WRITING → JUDGING → DONE
                  ↑                                      |
                  └──────── (quality failed) ────────────┘
```

- **DECOMPOSING**: Break question into research angles, validate each with initial search
- **EXPLORING**: Per-angle convergence loops (search → audit → specialist → check novelty)
- **SYNTHESIZING**: Combine saturated angle findings, detect cross-angle patterns
- **DEBATING**: Multi-round specialist debate on synthesized findings
- **WRITING**: Paper assembly using Why Files narrative structure
- **JUDGING**: Quality evaluation; if failed, re-explore weak areas
- **DONE**: Paper released to library

### Event Bus

Handlers react to state changes rather than being called sequentially:

| Event | Trigger | Handler |
|-------|---------|---------|
| `AngleCreated(angle)` | Decomposition or rabbit hole | SearchHandler |
| `SourcesFound(angle)` | Search completed | AuditHandler |
| `SourcesAudited(angle)` | Audit completed | SpecialistHandler |
| `FindingsProduced(angle)` | Specialist analysis done | ConvergenceChecker |
| `AngleSaturated(angle)` | 2 consecutive zero-claim rounds | → check if ALL saturated |
| `AllAnglesSaturated` | Every angle saturated | SynthesisHandler |
| `SynthesisReady` | Cross-angle synthesis complete | DebateHandler |
| `DebateComplete` | Debate rounds finished | PaperHandler |
| `PaperReady` | Paper assembled | JudgeHandler |
| `QualityPassed` | Score ≥ threshold | → DONE |
| `QualityFailed(weak_areas)` | Score < threshold | → targeted re-exploration |
| `NewAngleDiscovered(topic)` | Specialist found unexpected connection | → create angle, SearchHandler |
| `DeadlineApproaching(hours)` | <3h remaining on 24h deadline | → force synthesis from current state |

### Concurrency Model

- All handlers run as async tasks within a single event loop
- Multiple angles can be in different stages simultaneously (Angle 1 in specialist analysis, Angle 3 still searching)
- **Global semaphore**: `asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS=12)` — all MiniMax calls acquire from this pool
- SSE events emitted to frontend for each state change (reuses existing emit pattern)

### Research State

```python
@dataclass
class ResearchState:
    question: str
    seed_urls: list[str]           # user-provided URLs
    seed_video_ids: list[str]      # user-provided YouTube videos
    angles: list[ResearchAngle]
    specialist_panel: list[ActiveSpecialist]  # with contribution scores
    synthesis: dict | None
    debate_result: dict | None
    paper_text: str | None
    paper_title: str | None
    quality_score: dict | None
    phase: ResearchPhase           # enum: DECOMPOSING, EXPLORING, etc.
    started_at: datetime
    deadline: datetime             # started_at + 24h
    registry: CitationRegistry     # reuse existing
    llm_call_count: int
    emit: Callable                 # SSE callback

@dataclass
class ResearchAngle:
    id: str
    topic: str                     # e.g., "Mesopotamian radiant deities"
    description: str
    search_queries: list[str]
    specialist_domains: list[str]  # suggested specialist types
    sources: list[str]             # source IDs in registry
    findings: list[dict]           # accumulated claims
    search_rounds: int
    recent_claim_counts: list[int] # last 3 rounds' new claim counts
    saturated: bool
    spawned_from: str | None       # parent angle ID if rabbit hole

@dataclass
class ActiveSpecialist:
    specialist: Specialist         # from pool
    contribution_score: float      # DyLAN-style peer evaluation
    consecutive_zero_rounds: int   # for pruning
    interdisciplinary_hits: int    # bonus for cross-angle connections
    active: bool
```

---

## Stage 0: Topic Decomposition

### Phase A — LLM Proposes Angles

Input: user question + seed URLs/videos
Output: 3-6 proposed research angles

**Prompt guidance:**
- Separate the TOPIC from the HYPOTHESIS (structural fix for debunking trap)
- Each angle must be independently researchable
- Include the speculative hypothesis as ONE angle, not the only angle
- Include at least one angle exploring the topic's cultural/historical context
- Include at least one angle exploring scholarly debate

**Example for "What if Shining Ones were beings from other planets?":**
1. "Luminous divine beings in Mesopotamian texts (Anunnaki, Igigi, melammu)"
2. "Radiant deities across Indo-European traditions (Devas, Tuatha Dé Danann, Amesha Spentas)"
3. "Archaeological evidence at sites associated with 'divine knowledge transfer'"
4. "The ancient astronaut interpretation — scholarly analysis of Sitchin, von Däniken"
5. "Hermetic and esoteric traditions of luminous wisdom-bringers"

### Phase B — Validation Search

For each proposed angle, run 2-3 search queries. Check:
- Does this angle have actual scholarly sources? (≥2 relevant results → keep)
- Did the results reveal a related angle we didn't think of? (→ add it)
- Is this angle a duplicate of another? (→ merge)

Output: validated list of `ResearchAngle` objects, each with initial search queries.

---

## Per-Angle Convergence Loop

Each angle runs independently:

```
Round 1: SEARCH (3-5 queries) → AUDIT → SPECIALIST ANALYSIS → CHECK
Round 2: REFINED SEARCH (based on gaps) → AUDIT → SPECIALIST → CHECK
Round N: ... until saturated
```

### Search Refinement

After each specialist round, generate refined queries based on:
- What specialists said was missing or underexplored
- Coverage gaps identified during audit
- Cross-angle connections that need deeper sourcing

### Convergence Check

After each specialist round:
1. Count new claims (findings not seen in previous rounds for this angle)
2. Track `recent_claim_counts` (last 3 rounds): e.g., `[12, 4, 0]`
3. **Saturated** when 2 consecutive rounds have 0 new claims
4. **Cross-angle check**: Do any new findings connect to other angles' findings?
   - If yes → flag as interdisciplinary insight
   - If the connection reveals a new sub-topic → emit `NewAngleDiscovered`

### Source Audit (per round)

Same as current Stage 3 (source_audit) but scoped to the angle's new sources:
- Tier assignment (academic/reputable/general)
- Relevance check against the angle's specific topic (not just the overall question)
- Rejection of off-topic sources

---

## Specialist Panel Management

### Initial Selection

At decomposition time, select 5-8 specialists based on:
- Angle topics (each angle suggests specialist domains)
- Question keywords (existing trigger_keywords system)
- Always include baseline generalist (ancient_historian)

### Per-Round Evaluation (DyLAN-style)

After each specialist round across all angles:

**Contribution score** (0-1):
- `+0.3` for each new claim with tier 1-2 sources
- `+0.2` for each claim that cross-references another angle's findings
- `+0.1` for each uncertainty/caveat flagged (adds nuance)
- Score decays by 0.1 each round if no contributions

**Pruning**: `consecutive_zero_rounds ≥ 2` AND `interdisciplinary_hits == 0` → deactivate

**Interdisciplinary bonus**: Specialists whose findings connect to other angles get `interdisciplinary_hits++` and are NEVER pruned (they're the dot-connectors).

**Recruitment**: When a new angle is spawned or specialist analysis reveals a domain gap, recruit from the specialist pool. Check: is there a specialist whose `trigger_domains` match the new need?

**Caps**: Minimum 3 active, maximum 12 active specialists.

---

## Cross-Angle Synthesis

Triggered when ALL angles are saturated.

### Phase 1 — Per-Angle Summary

For each angle, synthesize its findings into:
- Key claims (with source citations)
- Confidence levels
- Open questions

### Phase 2 — Cross-Angle Pattern Detection

**The interdisciplinary gold.** An LLM examines all angle summaries together and identifies:
- **Convergent findings**: Different angles independently found the same pattern
- **Contradictions**: Angle A's evidence conflicts with Angle B's
- **Connections**: Finding in Angle A illuminates or contextualizes a finding in Angle B
- **Gaps**: No angle addressed a sub-topic that clearly matters

Connections and convergent findings become the paper's climax — "what the investigation revealed."

### Phase 3 — Structured Synthesis Output

Same schema as current synthesis (consensus/contested/unique/open_questions) but enriched with cross-angle metadata: which angles contributed, where connections were found.

---

## Debate

Runs after synthesis. Same multi-round debate model as current pipeline:
- Specialists challenge the synthesis from their perspectives
- Defenders respond
- Multiple rounds (determined dynamically based on how contested the findings are)

**New**: Debate rounds continue until:
- No new critical challenges raised in a round, OR
- 4 rounds completed (hard cap to prevent circular arguments)

No fixed debate_rounds per tier — the debate converges on its own.

---

## Paper Assembly: The Why Files Narrative

### Structure

```markdown
# [Compelling Title — Names the Mystery]

[Hook paragraph — draws reader in with the central mystery/question.
 Not "This paper examines..." but "In temples across three continents,
 ancient scribes recorded encounters with beings made of light..."]

## The Investigation

### [Angle 1 Title]
Evidence trail for this angle. Present discoveries as they unfold.
Follow the thread. "This led researchers to X, which revealed Y..."

### [Angle 2 Title]
Same investigative approach for the next angle.

### [Angle N Title]
...

## Connecting the Dots
The interdisciplinary gold. Where did findings from different angles
overlap? What patterns emerged? This is the climax of the investigation.

## The Other Side
Present the strongest counter-evidence or skeptical perspective
fairly. Not as "debunking" but as "here's what the evidence
doesn't support, and why."

## What We Actually Know
Honest assessment. Three categories:
- Well-documented (peer-reviewed, multiple sources)
- Plausible but uncertain (limited evidence, needs more research)
- Speculative (interesting but unsupported)

End with genuine curiosity: what deserves more investigation?

## References
Full citation list with tier labels [Academic] [Reputable]
```

### Narrative Rules (enforced in prompts)

1. **Never lecture the reader** — investigate WITH them
2. **Present the strongest case FOR and AGAINST** — the reader decides
3. **Follow evidence like a detective** — narrative arc, not bullet points
4. **Interdisciplinary connections are the climax** — not a footnote
5. **End with genuine curiosity** — not a verdict
6. **No academic hedging** — "the evidence shows" not "it should be noted that"
7. **Specific over general** — names, dates, sites, texts > vague claims

---

## Quality Judge

Same quality evaluation concept but adapted for convergence:

### Dimensions Scored

- **Source diversity**: Do sources span multiple academic disciplines?
- **Angle coverage**: Did each angle get substantive treatment?
- **Cross-angle connections**: Were interdisciplinary patterns identified?
- **Narrative quality**: Does the paper follow the investigative structure?
- **Citation integrity**: Every claim attributed, no orphaned references
- **Balance**: Were competing perspectives presented fairly?
- **Assessment honesty**: Does the ending distinguish documented from speculative?

### Pass/Fail Routing

- **Pass** (score ≥ 75): Release to library
- **Fail — source gaps**: Specific angles need more/better sources → re-explore those angles
- **Fail — narrative issues**: Paper structure or tone needs revision → re-write only
- **Fail — balance**: One perspective dominates → re-synthesize with explicit balance requirement

### Convergence Protection

If the judge has failed 3 times on the same paper:
- Ship the best-scoring version with a lower quality badge
- Flag for human review
- Do NOT loop forever

---

## 24h Deadline (Safety Net)

The deadline is a safety net, not a scheduling tool. Most research should converge in 2-8 hours.

### Deadline Behavior

- **>3h remaining**: Normal operation. Explore freely.
- **3h remaining**: `DeadlineApproaching` event. System checks: are all angles saturated?
  - If yes: proceed normally (synthesis → debate → paper → judge)
  - If no: force-saturate remaining angles with current findings. Note in paper: "This angle warrants further investigation."
- **1h remaining**: Must be in WRITING or JUDGING phase. If not, force-write from current synthesis.
- **0h**: Release whatever is ready. If paper exists, release with quality badge. If not, release a "preliminary findings" summary.

### Graceful Degradation

The paper always acknowledges what wasn't fully explored:
- "The investigation of [angle X] was limited by available sources and deserves deeper study"
- This is honest, not a failure — real research always has open threads

---

## Frontend Changes

### Submission Flow (Simplified)

**Before:** 4-step wizard (question → relevance check → scope selection → submit)
**After:** Question input + optional attachments + submit button

- Text area for research question (min 200 chars, same as current)
- Optional: attach YouTube video IDs
- Optional: attach source URLs
- Optional: "Advanced" collapsible with specialist include/exclude
- Submit button (no scope/tier selection)
- Relevance check runs on submit (invisible unless it fails)

### Live Overlay (Angle-Based Progress)

Replace the flat 10-stage progress bar with angle-based convergence view:

- Each research angle shown as a labeled row with its own progress indicator
- Progress per angle: search rounds completed, saturation status (exploring/saturated)
- Saturated angles get a checkmark
- Newly spawned angles (rabbit holes) appear with a visual indicator
- Overall progress: "N of M angles saturated"
- Active stats: specialist count, source count, elapsed time
- Status text: current activity description

### Research Facility Stats

Persistent element showing global lab status:
- Active research tasks count
- Queued tasks count
- Published papers count
- Today's activity (sources analyzed, specialist reports generated)

### Completed Paper Cards

- Remove tier/scope badge (BRIEF, ARTICLE, etc.)
- Show: paper title, quality badge, angles researched count, source count, time taken
- Quality badges remain: Unverified, Bronze, Silver, Gold, Platinum

### Report Overlay

- Paper rendered in Why Files narrative structure
- Pipeline trace shows angles instead of flat stages
- Editor + approval flow unchanged

---

## Files Affected

### Backend (new files)
- `pipeline/lyra/convergence_orchestrator.py` — event bus + state machine + main research loop
- `pipeline/lyra/research_state.py` — ResearchState, ResearchAngle, ActiveSpecialist dataclasses
- `pipeline/lyra/handlers/` — directory with one handler per stage:
  - `decomposition_handler.py`
  - `search_handler.py`
  - `audit_handler.py`
  - `specialist_handler.py`
  - `convergence_checker.py`
  - `synthesis_handler.py`
  - `debate_handler.py`
  - `paper_handler.py`
  - `judge_handler.py`
  - `deadline_handler.py`
- `pipeline/lyra/prompts/theo_decomposition.txt` — angle decomposition prompt
- `pipeline/lyra/prompts/theo_paper_whyfiles.txt` — Why Files narrative paper prompt
- `pipeline/lyra/prompts/theo_cross_angle.txt` — cross-angle connection detection prompt

### Backend (modified files)
- `pipeline/lyra/theo_pipeline.py` — refactored: stages extracted into handlers, TheoPipeline.run() delegates to orchestrator
- `pipeline/lyra/theo_specialists.py` — add contribution scoring, pruning logic
- `api/services/theo_config.py` — remove TierConfig, add ResearchConfig (global settings, semaphore size, deadline)
- `api/services/theo_worker.py` — adapt worker to new orchestrator interface
- `api/routes/theo.py` — remove effort/tier from submission API

### Frontend (modified files)
- `ancient-nerds-map/src/pages/TheoPage.tsx` — remove scope wizard, simplify submission, add facility stats
- `ancient-nerds-map/src/components/theo/TheoResearchLive.tsx` — angle-based progress view
- `ancient-nerds-map/src/components/NervLoadingBar.tsx` — may need angle-aware mode
- `ancient-nerds-map/src/components/theo/TheoReportOverlay.tsx` — remove tier badges
- `ancient-nerds-map/src/types/pipeline.ts` — new pipeline stage definitions for angles
- `ancient-nerds-map/src/styles/theo.css` — new styles for angle progress, facility stats

### Prompts (rewritten)
- `theo_question_analysis.txt` → replaced by `theo_decomposition.txt`
- `theo_paper_brief.txt` → replaced by `theo_paper_whyfiles.txt`
- `theo_paper_full.txt` → replaced by `theo_paper_whyfiles.txt`
- `theo_paper_section.txt` → replaced by `theo_paper_whyfiles.txt` (sections handled differently)
- `theo_paper_outline.txt` → integrated into paper handler
- `theo_paper_frame.txt` → integrated into paper handler

### Database
- `theo_research_requests` table: remove `effort` column (or keep for backward compat, default to "research")
- API responses: remove effort/tier references

---

## Migration Strategy

The current pipeline (`theo_pipeline.py`) stays functional during development. The new orchestrator is built alongside it. Switch-over happens when the new pipeline passes the existing test suite (`test_lyra_quality.py`).

### Backward Compatibility
- Existing published papers keep their effort/tier labels in the database
- The API accepts `effort` parameter but ignores it (logs deprecation warning)
- Frontend shows tier badges on old papers, no badge on new ones

---

## Verification

### How to test end-to-end

1. **Unit tests per handler**: Each handler tested in isolation with mock events
2. **Integration test**: Full pipeline run with a known question, verify:
   - Topic decomposition produces ≥3 angles
   - Per-angle convergence loop runs ≥2 search rounds
   - Cross-angle connections detected
   - Paper follows Why Files structure (hook, investigation, connections, assessment)
   - Quality judge passes
3. **Regression**: Run `scripts/test_lyra_quality.py` against new pipeline
4. **The Shining Ones test**: Submit the exact question that produced the lecturing paper. Verify the new pipeline:
   - Produces research angles covering actual traditions (Mesopotamian, Vedic, etc.)
   - Does NOT produce a debunking-only paper
   - Includes interdisciplinary connections
   - Follows The Why Files narrative structure
5. **24h deadline test**: Mock the clock to test graceful convergence behavior
6. **Frontend**: Verify angle-based progress displays correctly in live overlay
