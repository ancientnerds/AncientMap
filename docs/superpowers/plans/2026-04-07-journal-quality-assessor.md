# Journal Quality Assessor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 10-dimension quality assessor that converges every journal entry to 10/10 through targeted LLM fixes.

**Architecture:** Single module `journal_assessor.py` with `assess_and_fix(body, sources) -> (fixed_body, AssessmentResult)` that loops up to 3 times. Integrated into the pipeline between screenshot injection and polish. Retroactive script fixes all existing journals.

**Tech Stack:** Python 3.13, MiniMax M2.7 via `minimax_chat_anthropic()`, regex

**Spec:** `docs/superpowers/specs/2026-04-07-journal-quality-assessor-design.md`

---

### Task 1: Create journal_assessor.py with AssessmentResult + mechanical checks (D7, D8)

**Files:**
- Create: `pipeline/lyra/journal_assessor.py`
- Test: `tests/pipeline/test_journal_assessor.py`

Start with the dataclass and the two purely mechanical dimensions that need no LLM.

### Task 2: Add LLM-powered assessment prompt + D1/D4/D6/D9 combined check

**Files:**
- Create: `pipeline/lyra/prompts/journal_assess_full.txt`
- Modify: `pipeline/lyra/journal_assessor.py`

Single LLM call that checks proper nouns (D1), screenshot placement (D4), spelling (D6), and summary accuracy (D9) in one pass.

### Task 3: Add remaining dimensions D2, D3, D5, D10

**Files:**
- Modify: `pipeline/lyra/journal_assessor.py`

Citation coverage (D2), academic style (D3), source quality (D5), section balance (D10).

### Task 4: Build the convergence loop

**Files:**
- Modify: `pipeline/lyra/journal_assessor.py`

`assess_and_fix()` main entry point that loops assess → fix → re-assess until 10/10.

### Task 5: Wire into article_generator.py pipeline

**Files:**
- Modify: `pipeline/lyra/article_generator.py`

Insert between screenshot injection and polish.

### Task 6: Build retroactive script + run on all journals

**Files:**
- Create: `scripts/reassess_journals.py`

Fix all existing journals, report before/after scores.
