# Theo Convergence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-tier pipeline with a convergence-based research system using event-driven architecture, topic decomposition, iterative specialist consensus, and Why Files narrative paper assembly.

**Architecture:** Event-driven state machine with reactive handlers. Research questions decomposed into angles, each researched iteratively until specialists find no new claims. Cross-angle synthesis detects interdisciplinary connections. Papers written in Why Files investigative narrative style. 24h deadline as safety net.

**Tech Stack:** Python 3.11+, asyncio, MiniMax M2.7 API, FastAPI, PostgreSQL, SSE streaming

**Spec:** `docs/superpowers/specs/2026-04-14-theo-convergence-pipeline-design.md`

---

## File Structure

### New Files (Backend)
- `pipeline/lyra/research_state.py` — ResearchState, ResearchAngle, ActiveSpecialist, ResearchPhase, ResearchConfig dataclasses
- `pipeline/lyra/research_events.py` — Event types + simple async EventBus
- `pipeline/lyra/convergence_orchestrator.py` — Main orchestrator: state machine, handler wiring, global semaphore
- `pipeline/lyra/handlers/__init__.py` — Handler base class
- `pipeline/lyra/handlers/decomposition.py` — Topic decomposition (LLM propose + validation search)
- `pipeline/lyra/handlers/angle_search.py` — Per-angle iterative search (wraps MultiSourceSearch)
- `pipeline/lyra/handlers/angle_audit.py` — Per-angle source audit (wraps existing audit logic)
- `pipeline/lyra/handlers/angle_specialist.py` — Per-angle specialist analysis + convergence check
- `pipeline/lyra/handlers/synthesis.py` — Cross-angle synthesis + interdisciplinary detection
- `pipeline/lyra/handlers/debate.py` — Multi-round debate (convergence-based, not fixed rounds)
- `pipeline/lyra/handlers/paper.py` — Why Files narrative paper assembly
- `pipeline/lyra/handlers/judge.py` — Quality judge with new dimensions
- `pipeline/lyra/handlers/deadline.py` — 24h deadline safety net
- `pipeline/lyra/prompts/v2_decomposition.txt` — Angle decomposition prompt
- `pipeline/lyra/prompts/v2_paper_whyfiles.txt` — Why Files paper assembly prompt
- `pipeline/lyra/prompts/v2_cross_angle.txt` — Cross-angle connection detection
- `pipeline/lyra/prompts/v2_convergence_check.txt` — "Did we learn anything new?" check
- `pipeline/lyra/prompts/v2_paper_outline.txt` — Outline generation for Why Files structure
- `pipeline/lyra/prompts/v2_paper_section.txt` — Per-section prose (investigative style)
- `pipeline/lyra/prompts/v2_paper_hook.txt` — Opening hook generation
- `pipeline/lyra/prompts/v2_paper_assessment.txt` — Honest assessment ending

### Modified Files (Backend)
- `api/services/theo_config.py` — Add ResearchConfig, deprecate TierConfig for v2
- `api/services/theo_worker.py` — Route to v2 orchestrator (effort param becomes optional)
- `api/routes/theo.py` — Make effort optional in submit schema
- `pipeline/lyra/theo_specialists.py` — Add contribution scoring methods

### Modified Files (Frontend)
- `ancient-nerds-map/src/pages/TheoPage.tsx` — Remove scope wizard, simplify to question+submit
- `ancient-nerds-map/src/components/theo/TheoResearchLive.tsx` — Angle-based progress display
- `ancient-nerds-map/src/types/pipeline.ts` — Add angle pipeline stages

---

## Phase 1: Core Data Structures + Event Bus

### Task 1: Research State Dataclasses

- [ ] Create `pipeline/lyra/research_state.py` with ResearchPhase enum, ResearchConfig, ResearchAngle, ActiveSpecialist, ResearchState
- [ ] Verify imports work: `python -c "from pipeline.lyra.research_state import ResearchState"`
- [ ] Commit

### Task 2: Event System

- [ ] Create `pipeline/lyra/research_events.py` with event dataclasses and async EventBus
- [ ] Verify: `python -c "from pipeline.lyra.research_events import EventBus, AngleCreated"`
- [ ] Commit

### Task 3: Handler Base Class

- [ ] Create `pipeline/lyra/handlers/__init__.py` with BaseHandler abstract class
- [ ] Verify: `python -c "from pipeline.lyra.handlers import BaseHandler"`
- [ ] Commit

---

## Phase 2: Research Handlers

### Task 4: Decomposition Handler

- [ ] Create `pipeline/lyra/prompts/v2_decomposition.txt`
- [ ] Create `pipeline/lyra/handlers/decomposition.py` — propose angles + validation search
- [ ] Verify: `python -c "from pipeline.lyra.handlers.decomposition import DecompositionHandler"`
- [ ] Commit

### Task 5: Search Handler

- [ ] Create `pipeline/lyra/handlers/angle_search.py` — per-angle search using existing MultiSourceSearch
- [ ] Verify imports
- [ ] Commit

### Task 6: Audit Handler

- [ ] Create `pipeline/lyra/handlers/angle_audit.py` — per-angle source audit using existing audit logic
- [ ] Verify imports
- [ ] Commit

### Task 7: Specialist Handler + Convergence Check

- [ ] Create `pipeline/lyra/prompts/v2_convergence_check.txt`
- [ ] Create `pipeline/lyra/handlers/angle_specialist.py` — specialist analysis + novelty detection
- [ ] Add contribution scoring to `pipeline/lyra/theo_specialists.py`
- [ ] Verify imports
- [ ] Commit

### Task 8: Synthesis Handler

- [ ] Create `pipeline/lyra/prompts/v2_cross_angle.txt`
- [ ] Create `pipeline/lyra/handlers/synthesis.py` — cross-angle synthesis + interdisciplinary detection
- [ ] Verify imports
- [ ] Commit

### Task 9: Debate Handler

- [ ] Create `pipeline/lyra/handlers/debate.py` — convergence-based debate (not fixed rounds)
- [ ] Verify imports
- [ ] Commit

### Task 10: Paper Handler (Why Files)

- [ ] Create all paper prompts: v2_paper_whyfiles.txt, v2_paper_outline.txt, v2_paper_section.txt, v2_paper_hook.txt, v2_paper_assessment.txt
- [ ] Create `pipeline/lyra/handlers/paper.py` — Why Files narrative assembly
- [ ] Verify imports
- [ ] Commit

### Task 11: Judge Handler

- [ ] Create `pipeline/lyra/handlers/judge.py` — quality judge with new dimensions
- [ ] Verify imports
- [ ] Commit

### Task 12: Deadline Handler

- [ ] Create `pipeline/lyra/handlers/deadline.py` — 24h safety net
- [ ] Verify imports
- [ ] Commit

---

## Phase 3: Orchestrator + Integration

### Task 13: Convergence Orchestrator

- [ ] Create `pipeline/lyra/convergence_orchestrator.py` — state machine, handler wiring, semaphore, main run() method
- [ ] Ensure run() signature is compatible with existing worker: returns PipelineContext-compatible result
- [ ] Verify: `python -c "from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator"`
- [ ] Commit

### Task 14: Worker Integration

- [ ] Modify `api/services/theo_config.py` — add ResearchConfig, add v2 credit cost
- [ ] Modify `api/services/theo_worker.py` — route to v2 orchestrator when effort="research" or not specified
- [ ] Modify `api/routes/theo.py` — make effort optional, default to "research"
- [ ] Commit

### Task 15: End-to-End Test

- [ ] Run `python scripts/test_theo_pipeline.py --effort research` against new pipeline
- [ ] Verify topic decomposition produces multiple angles
- [ ] Verify convergence loop runs
- [ ] Verify paper has Why Files structure
- [ ] Fix any issues
- [ ] Commit

---

## Phase 4: Frontend Updates

### Task 16: Remove Scope Wizard

- [ ] Modify TheoPage.tsx — remove scope/effort selection step, simplify to question+submit
- [ ] Default effort to "research" in submit body
- [ ] Remove EFFORTS array, scope cards, effort state
- [ ] Keep video/URL attachments and specialist options
- [ ] TypeScript check passes
- [ ] Commit

### Task 17: Angle-Based Progress

- [ ] Modify TheoResearchLive.tsx — display research angles with per-angle progress
- [ ] Add angle event handling (new pipeline events from v2)
- [ ] Keep backward compat with v1 events (stage-based)
- [ ] TypeScript check passes
- [ ] Commit

### Task 18: Clean Up

- [ ] Remove tier badges from completed cards
- [ ] Update pipeline.ts with new stage definitions
- [ ] Final TypeScript check
- [ ] Commit

---

## Phase 5: Final Verification

### Task 19: Full Integration Test

- [ ] Run the Shining Ones test: submit the exact question that produced the lecturing paper
- [ ] Verify: produces angles covering actual traditions (not just debunking)
- [ ] Verify: paper follows Why Files narrative (hook, investigation, connections, assessment)
- [ ] Verify: no lecturing or condescending tone
- [ ] Push to main
- [ ] Check CI passes

---

## Verification

1. `python -c "from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator"` — imports clean
2. `python scripts/test_theo_pipeline.py` — end-to-end pipeline produces a paper
3. `npx tsc --noEmit` — frontend compiles
4. CI passes (lint-frontend, lint-backend, security-scan, docker-build)
