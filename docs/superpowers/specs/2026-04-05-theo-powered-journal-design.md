# Theo-Powered Weekly Journal

**Date:** 2026-04-05
**Scope:** Refactor the weekly journal pipeline to use Theo research stages per-cluster
**Out of scope:** Theo pipeline API/streaming, Lyra chat, Lyra news feed

## Problem

The current journal pipeline writes all sections in one LLM call, verifies against the same YouTube facts it started with (circular), and accepts any web citation without quality auditing. This produces proper noun errors ("Goff's Cave"), low-quality citations (TripAdvisor, Gaia.com), and factual mistakes that survive all verification steps.

The Theo research pipeline has rigorous quality gates (per-source audit, domain specialists, quality judge with convergence loops) but is single-topic only. We need the journal's multi-topic breadth with Theo's per-topic depth.

## Solution

Replace the journal's write → verify → web_verify → assess steps with Theo research stages run per-cluster. Each cluster (a single archaeological discovery/topic) gets its own deep research pass with source audit, specialist analysis, synthesis, and quality judging.

### Pipeline flow

```
BEFORE: collect → cluster → write(all) → verify → web_verify → polish → assess → headline → save
AFTER:  collect → cluster → [per cluster: question → search → audit → specialists → synthesis → judge] → assemble → polish → headline → save
```

### Execution model

- **Sequential** — one cluster at a time
- **Note tier** — 3 specialists, standard source APIs, no debate
- **Estimated runtime** — 50-80 minutes for 5-8 clusters (vs. current ~10 min)
- **Scheduling** — same Sunday 20:00 UTC window

## Per-Cluster Research (Note Tier)

For each cluster (e.g., "13,500-year-old settlement at Sahout, Saudi Arabia"):

### Step 1: Question formulation

Convert the cluster's headline + facts into a Theo-compatible research question.

Input: `{"headline": "13,500-year-old settlement in Saudi Arabia linked to Natufian culture", "facts": ["Site at Sahout in Nefood Desert", "Published in Nature", "Helwan bladelets found"], "channel_name": "The Prehistory Guys", "video_id": "_5_bp8maWa8", "timestamp_seconds": 2889}`

Output: `"What is known about the 13,500-year-old settlement discovered at Sahout in Saudi Arabia and its connection to the Natufian culture?"`

This is a simple LLM call (or even template-based) — no complex logic.

### Step 2: Search (Theo Stage 2)

Run multi-source search using the research question:
- **MiniMax web search** — finds news articles, press releases
- **Semantic Scholar** — finds academic papers
- **OpenAlex / Crossref** — finds journal articles
- **Wikipedia** — finds reference context

The YouTube transcript facts are **injected as a pre-existing source** at Tier 2. This preserves the video citation with timestamp while letting Theo find corroborating sources.

### Step 3: Source audit (Theo Stage 3)

Each discovered source audited individually by LLM:
- Assigns reliability tier (1=academic, 2=reputable, 3=general)
- Rejects off-topic or low-quality sources
- Uses existing `theo_source_audit.txt` prompt
- Blocked domains filtered mechanically before audit (Reddit, TikTok, TripAdvisor, Gaia.com, etc.)

### Step 4: Specialist analysis (Theo Stage 4)

3 specialists selected by domain tags analyze the audited sources:
- Each specialist produces findings with source citations
- Findings must come FROM sources, not general knowledge
- Proper noun attribution verified against source text

### Step 5: Synthesis (Theo Stage 5)

Single LLM call merges specialist findings into consensus:
- Preserves all source citations
- Classifies claims as consensus, contested, or unique insight
- Filters findings against the research question

### Step 6: Quality judge

Score the synthesis on 7 dimensions (citation coverage, reference integrity, attribution accuracy, source fidelity, hedging, coherence, question fidelity).

- **Pass threshold**: score >= 72, zero attribution failures, zero source fidelity failures
- **On failure**: re-run from the identified failing stage (max 2 iterations)
- **On pass**: output the synthesis as a journal section
- **On max iterations exhausted**: drop the cluster from the journal with a log warning. A journal with 4 sections is better than one with a bad section.

### Output per cluster

A section of prose with `[N]` citation markers, plus a `CitationRegistry` mapping each `[N]` to a source with URL, title, tier, and type (YouTube/academic/news/wiki).

## Assembly

After all clusters complete sequentially:

### 1. Filter speculative clusters

During collect, items with `speculative_tag` set are **excluded**. They remain in the news feed and radar but don't enter the journal pipeline. No "Beyond the Mainstream" section.

### 2. Merge sections

Order sections by category using existing `CATEGORY_LABELS`:
- New Excavations & Fieldwork
- Artifact Discoveries
- Dating & Chronology
- Remote Sensing & Technology
- Bioarchaeology & Ancient DNA
- Underwater Archaeology
- Architecture & Monuments
- Inscriptions & Texts
- Ancient Art

### 3. Unify citations

Merge all per-cluster citation registries into one sequential `[1]`-`[N]` list:
- YouTube sources: `[Channel — "Video Title"](youtu.be/ID?t=S) (MM:SS)`
- Academic sources: `[Paper Title](DOI or URL) (Year)`
- News/wiki sources: `[Article Title](URL) (Date)`

Renumber all `[N]` markers in the body to match the unified list.

### 4. Polish

Single editorial pass (same `_polish_article` as now) for tone, transitions, and coherence across sections.

### 5. Headline

Generate journal title in "Week of [Date]: [hook], [second topic], and More" format (same `_generate_headline_tldr` as now).

### 6. Save

Save to `news_articles` table with title, content, summary, week range, video IDs.

## Shared Research Stages Module

Extract Theo's core stages into `pipeline/lyra/research_stages.py`:

### Functions to extract

| Function | From | Used by |
|---|---|---|
| `run_search(question, settings, source_group)` | `theo_pipeline._stage_2_search` | Both |
| `run_source_audit(sources, question, settings)` | `theo_pipeline._stage_3_audit` | Both |
| `run_specialist_analysis(sources, question, specialists, settings)` | `theo_pipeline._stage_4_specialists` | Both |
| `run_synthesis(findings, question, settings)` | `theo_pipeline._stage_5_synthesis` | Both |
| `run_quality_judge(text, citations, question, settings)` | `theo_quality_judge.judge_paper` | Both |

### Interface

Each function takes explicit inputs and returns explicit outputs — no dependency on `ResearchRequest` DB model or streaming. The Theo pipeline's `_stage_N_*` methods become thin wrappers that call the shared functions and write results to the DB/stream.

### Citation registry

Both pipelines use `CitationRegistry` from `theo_citations.py` for tracking sources and claims. The journal pipeline creates one registry per cluster, then merges them during assembly.

## Changes Summary

| File | Change |
|---|---|
| **New: `pipeline/lyra/research_stages.py`** | Shared research stage functions extracted from theo_pipeline |
| **Modify: `pipeline/lyra/theo_pipeline.py`** | Refactor stages to call shared functions from research_stages.py. Behavior unchanged. |
| **Modify: `pipeline/lyra/article_generator.py`** | Replace write/verify/web_verify/assess with `_research_cluster()` calling shared stages. New `_formulate_question()`, `_assemble_journal()`, unified citation merger. |
| **New: `pipeline/lyra/prompts/journal_question.txt`** | Prompt for converting cluster facts into a research question |
| **Modify: `pipeline/lyra/prompts/headline.txt`** | Already updated (journal-style titles) |
| **No change: `pipeline/lyra/theo_citations.py`** | Used as-is by both pipelines |
| **No change: `pipeline/lyra/theo_quality_judge.py`** | Used as-is by both pipelines |
| **No change: `pipeline/lyra/theo_specialists.py`** | Used as-is by both pipelines |
| **No change: `pipeline/lyra/theo_sources.py`** | Used as-is (search adapters) |

## What gets deleted

- `_write_article_body()` — replaced by per-cluster Theo research
- `_verify_article()` — replaced by quality judge
- `_web_verify_article()` — web sources found during Theo search stage
- `_assess_journal()` — proper nouns caught by specialists + quality judge
- `_build_section_payload()` / `_build_speculative_payload()` — speculative section dropped, sections built from Theo synthesis
- Web research backends (`AnthropicWebResearch`, `MiniMaxWebResearch` in `web_research.py`) — no longer needed for journal. Keep if used elsewhere.

## What stays

- `_collect_article_items()` — same DB query for the week's items
- `_cluster_items()` — same LLM-based clustering
- `_group_and_cite()` — adapted to pass clusters to Theo instead of building payloads
- `_polish_article()` — same editorial coherence pass
- `_generate_headline_tldr()` — same journal-style headline
- `_cleanup_citations()` — adapted for unified citation format
- `_assemble_article()` — adapted for new section format
- `should_generate_article()` — same Sunday 20:00 UTC check
- `news_articles` table — same schema

## Risk & Rollback

- **Rollback**: Revert the commit. The old pipeline code is in git history.
- **Feature flag**: Add `LYRA_JOURNAL_MODE=theo|legacy` setting. Default to `theo`, fall back to `legacy` (old pipeline) if Theo stages fail or setting is changed.
- **Gradual**: Deploy and monitor the first Sunday run via logs. If quality judge fails all clusters, the pipeline produces no journal (safe failure — just means no journal that week).
- **Runtime**: ~1 hour vs. ~10 min. The Sunday 20:00 UTC window has 12 hours before the next cycle matters, so runtime is not a concern.

## Success criteria

A regenerated journal where:
1. Every proper noun matches its source spelling
2. Every web citation comes from a reputable source (no TripAdvisor, Gaia.com)
3. Every factual claim is backed by an audited source
4. Quality judge scores >= 72 on all sections
5. No speculative content unless it passes source audit
