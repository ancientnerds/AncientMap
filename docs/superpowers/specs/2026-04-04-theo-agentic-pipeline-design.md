# Theo Phase 2: Agentic Research Pipeline

## Context

Theo (Theodore Furcade) is AncientMap's async archaeological research agent. Phase 1 delivered the infrastructure: frontend pages, API routes, DB table (`research_requests`), SSE streaming, and a polling worker. Phase 2 wires the actual research backend.

**Problem**: Theo's `_process_request()` is a stub that immediately fails. Users can submit research questions but get no results.

**Solution**: Implement a full 8-stage agentic pipeline (adapted from tesseract-trading's architecture) that produces academic-quality research papers with proper citations, source attribution, and multi-specialist verification. Every factual claim must trace to a verifiable web source -- zero hallucinations is the top priority.

**LLM**: MiniMax M2.7 exclusively (Token Plan, $10-50/mo). Reuses the existing MiniMax integration from the article web verification pipeline.

---

## Pipeline Architecture

### 8-Stage Flow

```
User Question
    |
[Stage 1] QUESTION ANALYSIS + SPECIALIST SELECTION (Convergence)
    |   - Decompose into sub-questions, search queries, domain tags
    |   - Select specialists from pool based on domain relevance
    |   - Generator-Critic loop ensures comprehensive coverage
    |
[Stage 2] WEB RESEARCH
    |   - Execute MiniMax search API queries (parallel)
    |   - Collect, deduplicate, rank results
    |   - Reformulate empty queries once (append domain keywords)
    |
[Stage 3] SOURCE AUDIT (Convergence)
    |   - Score reliability: tier 1 (academic/institutional), tier 2 (reputable), tier 3 (general)
    |   - Filter social media, forums, content farms
    |   - Assess coverage -- retry to Stage 2 if insufficient
    |
[Stage 4] SPECIALIST ANALYSIS (Parallel)
    |   - Each specialist analyzes vetted sources from their perspective
    |   - Must cite source IDs for every finding
    |   - Outputs: findings + confidence levels + uncertainties
    |
[Stage 5] CROSS-SOURCE SYNTHESIS (Convergence)
    |   - Merge findings: consensus claims, contested claims, unique insights
    |   - Build argument map showing how claims relate
    |   - Critic checks for unsourced claims and missed contradictions
    |
[Stage 6] MULTI-AGENT DEBATE (Thesis only)
    |   - Round 1: Specialists challenge each other's findings (parallel)
    |   - Round 2: Defend or concede (parallel)
    |   - Claims marked as resolved, weakened, or newly caveated
    |
[Stage 7] MODERATOR + DEVIL'S ADVOCATE
    |   - Moderator synthesizes debate/synthesis into final positions
    |   - Devil's advocate attacks consensus
    |   - If flaw found, moderator revises
    |
[Stage 8] PAPER ASSEMBLY + CITATION AUDIT
    |   - Format into academic paper structure
    |   - Mechanical audit: every claim has [N], every [N] maps to reference
    |   - Unsourced claims flagged [citation needed]
    |
Final Paper (Markdown)
```

### Zero-Hallucination Gates

1. **Stage 3**: Source reliability filtering -- tier 3 sources can't be sole backing for claims
2. **Stage 4**: Specialists must attribute every finding to source IDs
3. **Stage 5 Critic**: Scans for unsourced claims sneaking into synthesis
4. **Stage 6**: Specialists challenge each other's claims with counter-evidence
5. **Stage 7**: Devil's advocate deliberately attacks conclusions
6. **Stage 8**: Mechanical scan -- every factual paragraph must have a `[N]` citation

---

## Specialist Pool

18 specialists with distinct perspectives. A "casting director" step in Stage 1 selects the right team per question.

### Selection Algorithm

1. Stage 1 M2.7 call tags the question with `domain_tags` (e.g., `["archaeology", "epigraphy", "bronze_age"]`)
2. Each specialist has `trigger_keywords` and `trigger_domains`
3. Score by keyword/domain overlap
4. `ancient_historian` always included as baseline generalist
5. Top N selected per effort tier: Brief=1, Paper=3-5, Thesis=5-8

### Roster

| ID | Specialist | Domain | Trusts | Skeptical Of |
|----|-----------|--------|--------|-------------|
| `field_archaeologist` | Dr. Elena Vasquez | Field Methods | Stratigraphy, excavation reports | Remote-only analyses |
| `ceramic_analyst` | Dr. Kenji Tanaka | Ceramics | Pottery sequences, type series | Broad claims from single sherds |
| `lithics_specialist` | Dr. Amara Osei | Lithic Technology | Use-wear analysis, chaîne opératoire | Functional claims without lab data |
| `bioarchaeologist` | Dr. Sven Lindqvist | Bioarchaeology | Skeletal analysis, isotopes, aDNA | Health claims without lab results |
| `geoarchaeologist` | Dr. Fatima Al-Rashid | Geoarchaeology | Sediment analysis, geomorphology | Site-formation claims without soil data |
| `dating_specialist` | Dr. Mikhail Petrov | Chronometry | Radiocarbon, OSL, dendro with error ranges | Single-date claims, uncalibrated dates |
| `epigrapher` | Dr. Camille Beaumont | Epigraphy | Well-documented inscriptions | Contested decipherments |
| `ancient_historian` | Dr. Marcus Chen | Ancient History | Texts cross-referenced with material evidence | Ignoring either texts or archaeology |
| `anthropologist` | Dr. Ingrid Solheim | Cultural Anthropology | Cautious ethnographic parallels | Direct analogy to deep prehistory |
| `underwater_archaeologist` | Dr. Carlos Rivera | Maritime Archaeology | Systematic underwater surveys | Treasure-hunter claims |
| `remote_sensing_expert` | Dr. Sarah Okonkwo | Remote Sensing | LiDAR, satellite, GPR with ground-truth | Imagery-only pattern claims |
| `conservation_specialist` | Dr. Tomoko Hayashi | Heritage Conservation | Condition reports, conservation science | Undocumented restoration claims |
| `archaeobotanist` | Dr. Priya Sharma | Archaeobotany | Macrobotanical/pollen analyses | Broad agricultural claims from limited samples |
| `numismatist` | Dr. Alexandros Papadopoulos | Numismatics | Coin typologies, hoard evidence | Economic conclusions from single coins |
| `archaeoastronomer` | Dr. Quilla Mamani | Archaeoastronomy | Documented alignments with statistics | Visual-impression alignment claims |
| `zooarchaeologist` | Dr. Brendan O'Neill | Zooarchaeology | Systematic faunal assemblage analysis | Single-specimen domestication claims |
| `classical_archaeologist` | Dr. Livia Fontana | Classical Archaeology | Well-stratified Mediterranean contexts | Broad Greco-Roman generalizations |
| `prehistorian` | Dr. Nkechi Adeyemi | Prehistory | Long-sequence excavations with dating | Single-site narratives, "earliest" claims |

---

## Effort Tiers

Renamed from quick/deep/full/auto to brief/paper/thesis/auto.

### Tier Definitions

| Tier | Time | Specialists | Stages | M2.7 Calls | Output |
|------|------|-------------|--------|------------|--------|
| `brief` | ~2 min | 1 | 1 (no convergence), 2, 3 (no convergence), 4, 8 (simplified) | ~6 | Literature overview: 3-5 paragraphs + references |
| `paper` | ~5-8 min | 3-5 | 1-5, 7 (simplified), 8 | ~18-25 | Full academic paper |
| `thesis` | ~15 min | 5-8 | All 1-8, full convergence + debate | ~40-55 | Comprehensive paper + debate appendix |
| `auto` | ~5-8 min | 3-5 | Same as Paper | ~18-25 | Same as Paper |

### Convergence Iterations per Tier

| Stage | Brief | Paper | Thesis |
|-------|-------|-------|--------|
| 1. Question Analysis | 0 (single-shot) | Max 2 | Max 3 |
| 2. Web Search | 0 retries | 1 reformulation | 1 reformulation |
| 3. Source Audit | No convergence | Max 1 retry | Max 1 retry |
| 5. Synthesis | Skipped | Max 1 | Max 2 |
| 6. Debate | Skipped | Skipped | 2 rounds |
| 7. Moderator | Skipped | Simplified (1 call) | Full + devil's advocate |

### Paper Output Format

**Brief tier:**
```markdown
# [Title]

[3-5 paragraphs with inline [N] citations]

## References
[1] Title -- URL (accessed YYYY-MM-DD)
```

**Paper/Thesis tiers:**
```markdown
# [Title]

## Abstract
3-5 sentence summary of findings.

## Introduction
Research question context and framing.

## [Domain Section 1]
Specialist findings with [N] citations.

## [Domain Section 2]
...

## Discussion
Cross-cutting analysis, contested claims with both sides.

## Conclusion
Key findings, confidence levels, open questions.

## Methodology
Brief note on multi-specialist agentic approach.

## References
[1] Author/Title -- URL (accessed YYYY-MM-DD) [Academic]
[2] ...
```

**Thesis only -- appended:**
```markdown
## Appendix: Specialist Debate Summary
Summary of challenges, defenses, and position changes.
```

---

## Citation Tracking

### Data Structures

```python
@dataclass
class CitedSource:
    id: str                    # sha256(url)[:12]
    url: str
    title: str
    snippet: str
    date: str
    domain: str
    reliability_tier: int      # 1=academic, 2=reputable, 3=general
    access_timestamp: str
    search_query: str

@dataclass
class ClaimCitation:
    claim_text: str
    source_ids: list[str]
    specialist_id: str
    confidence: str            # "high", "medium", "low"

@dataclass
class CitationRegistry:
    sources: dict[str, CitedSource]
    claims: list[ClaimCitation]
    reference_numbers: dict[str, int]  # source_id -> [N]
```

### Citation Flow

1. **Stage 2**: Search results registered as `CitedSource` in registry
2. **Stage 3**: Sources get `reliability_tier`. Tier 3 can appear as "see also" but never sole backing
3. **Stage 4**: Specialists reference sources by ID. Each finding creates a `ClaimCitation`
4. **Stage 5**: Claims merged -- if two specialists cite same claim, both source_ids included
5. **Stage 8**: Paper text gets `[N]` markers via `assign_reference_number()`. References section generated mechanically (not by LLM)
6. **Citation audit** (mechanical): Every `[N]` maps to a reference. Every factual paragraph has at least one `[N]`. Violations flagged as `[citation needed]`

---

## File Structure

### New Files

| File | Purpose |
|------|---------|
| `pipeline/lyra/theo_pipeline.py` | Main orchestrator: `TheoPipeline` class, 8 stage methods, `_run_convergence_loop()` |
| `pipeline/lyra/theo_specialists.py` | 18 `Specialist` definitions, `select_specialists()`, `build_specialist_prompt()` |
| `pipeline/lyra/theo_debate.py` | Debate engine (R1 challenges, R2 defenses), moderator, devil's advocate |
| `pipeline/lyra/theo_citations.py` | `CitationRegistry`, `CitedSource`, `ClaimCitation`, `audit_citations()` |
| `pipeline/lyra/theo_paper.py` | Paper assembly: format templates per tier, `format_references()` |
| `pipeline/lyra/prompts/theo_question_analysis.txt` | Stage 1 generator |
| `pipeline/lyra/prompts/theo_question_critic.txt` | Stage 1 critic |
| `pipeline/lyra/prompts/theo_source_audit.txt` | Stage 3 auditor |
| `pipeline/lyra/prompts/theo_specialist_analysis.txt` | Stage 4 template (with specialist placeholders) |
| `pipeline/lyra/prompts/theo_synthesis.txt` | Stage 5 generator |
| `pipeline/lyra/prompts/theo_synthesis_critic.txt` | Stage 5 critic |
| `pipeline/lyra/prompts/theo_debate_challenge.txt` | Stage 6 R1 |
| `pipeline/lyra/prompts/theo_debate_defense.txt` | Stage 6 R2 |
| `pipeline/lyra/prompts/theo_moderator.txt` | Stage 7 moderator |
| `pipeline/lyra/prompts/theo_devils_advocate.txt` | Stage 7 adversarial |
| `pipeline/lyra/prompts/theo_paper_brief.txt` | Stage 8 brief format |
| `pipeline/lyra/prompts/theo_paper_full.txt` | Stage 8 paper/thesis format |

### Modified Files

| File | Changes |
|------|---------|
| `api/services/theo_worker.py` | Replace stub `_process_request()` with `TheoPipeline.run()` call, wire SSE emitter |
| `api/services/theo_config.py` | Rename tiers, add per-tier config (specialist count, convergence iters, stages) |
| `api/routes/theo.py` | Update effort validation + `_estimate_minutes()` |
| `pipeline/lyra/minimax_shared.py` | New shared module: `minimax_search()` and `minimax_chat()` extracted from web_research.py |
| `pipeline/lyra/web_research.py` | Refactor to import from `minimax_shared.py` instead of inline implementations |
| `ancient-nerds-map/src/pages/TheoPage.tsx` | Update effort tier labels + time estimates |
| `ancient-nerds-map/src/pages/TheoResearchLive.tsx` | Add pipeline stage names for trace |

### Reuse from Existing Code

| What | From | How |
|------|------|-----|
| MiniMax search API calls | `web_research.py:_search()` | Extract to shared `minimax_search()` |
| M2.7 chat with retry | `web_research.py:_chat()` | Extract to shared `minimax_chat()` |
| OpenAI client (cached) | `config.py:_get_minimax_client()` | Import directly |
| JSON parsing | `config.py:parse_json_response()` | Import directly |
| SSE event system | `theo_worker.py:_append_event()` | Pipeline calls emitter function |
| Prompt loading | `article_generator.py:_load_prompt()` | Same pattern, same `prompts/` dir |

---

## SSE Event Design

Events streamed to frontend for live pipeline trace:

```
Stage start:   {type: "pipeline", stage: "<name>", status: "start"}
Progress:      {type: "status", content: "Dr. Petrov analyzing radiocarbon evidence..."}
Convergence:   {type: "status", content: "Critic found gaps, refining... (iteration 2/3)"}
Stage done:    {type: "pipeline", stage: "<name>", status: "done", duration_ms: N, meta: {...}}
Paper stream:  {type: "token", content: "## Abstract\n\n..."}  (section by section)
Complete:      {type: "done", status: "completed"}
Error:         {type: "pipeline", stage: "<name>", status: "error", meta: {error: "..."}}
```

Stage names: `question_analysis`, `web_search`, `source_audit`, `specialist_analysis`, `synthesis`, `debate_round_1`, `debate_round_2`, `moderator`, `paper_assembly`.

---

## Error Handling

| Scenario | Response |
|----------|----------|
| M2.7 rate limit (429) | 3 retries with exponential backoff (3s, 6s, 9s). SSE: "Rate limited, retrying..." |
| Search returns 0 results | Reformulate once (append domain keywords). If still empty, log and continue with fewer sources |
| All searches fail (API down) | Short-circuit to Stage 8, produce minimal paper with `[unverified]` flags |
| Convergence doesn't converge | Use last generator output, log warning, add to pipeline_trace |
| M2.7 produces only reasoning | Retry with doubled max_tokens (cap 32768). If still empty, return empty string |
| Stage 1-3 failure | Fatal -- set status `failed`, emit error event |
| Stage 4-7 failure | Non-fatal -- reduce specialist count, emit warning, continue with available data |
| Stage 8 failure | Dump raw findings as fallback report |

---

## Verification Plan

### Unit Tests
- `CitationRegistry`: register, assign numbers, audit (orphans, missing citations)
- `select_specialists()`: keyword matching, minimum count, always includes historian
- `_run_convergence_loop()`: mock generator/critic, test convergence and max-iteration behavior

### Integration Tests
- Full Brief pipeline with mocked M2.7 responses -- verify paper structure and citations
- Full Paper pipeline -- verify multi-specialist flow and synthesis
- SSE event sequence -- verify correct stage ordering and event types

### Manual Validation
- Run a real Brief request: "What is the current understanding of Gobekli Tepe's construction timeline?"
- Run a real Paper request: "How has LiDAR changed our understanding of Maya urbanism?"
- Verify: every claim in output has a `[N]` citation, every `[N]` maps to a real URL
- Check SSE stream in TheoResearchLive shows stages progressing

### Rate Limit Testing
- Run 3 Paper requests back-to-back, verify semaphore queuing works
- Monitor MiniMax token consumption against plan limits
