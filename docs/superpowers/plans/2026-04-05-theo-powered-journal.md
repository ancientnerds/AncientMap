# Theo-Powered Weekly Journal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the journal pipeline's single-pass write/verify with Theo research stages per-cluster, giving each topic source audit, specialist review, and quality judging.

**Architecture:** Create `research_stages.py` with sync wrapper functions that call existing Theo modules (theo_sources, theo_citations, theo_specialists, theo_quality_judge). The journal's `article_generator.py` calls these per cluster. Theo's own pipeline is not modified — we import its dependencies, not its code.

**Tech Stack:** Python 3.13, Anthropic SDK, MiniMax M2.7, existing Theo modules

**Spec:** `docs/superpowers/specs/2026-04-05-theo-powered-journal-design.md`

---

### Task 1: Create research_stages.py — the shared research module

**Files:**
- Create: `pipeline/lyra/research_stages.py`
- Test: `tests/pipeline/test_research_stages.py`

This module provides sync functions that orchestrate Theo's search → audit → specialist → synthesis → judge pipeline for a single research question. It imports from existing Theo modules but does NOT modify them.

### Task 2: Integrate research_stages into article_generator.py

**Files:**
- Modify: `pipeline/lyra/article_generator.py`

Replace `_write_article_body`, `_verify_article`, `_web_verify_article`, `_assess_journal` with a new `_research_cluster()` function that calls research_stages per cluster.

### Task 3: Update assembly — merge per-cluster citation registries

**Files:**
- Modify: `pipeline/lyra/article_generator.py`

New `_assemble_journal()` that merges per-cluster Theo outputs (prose + citations) into unified journal sections with a single sequential citation list.

### Task 4: Filter speculative items, update pipeline flow

**Files:**
- Modify: `pipeline/lyra/article_generator.py`

Remove speculative section handling. Wire the new per-cluster flow into `generate_weekly_article()`.

### Task 5: Add feature flag and test

**Files:**
- Modify: `pipeline/lyra/config.py` (add `LYRA_JOURNAL_MODE` setting)
- Test: Integration test with mocked LLM calls

### Task 6: End-to-end test on prod

Delete current journal #23, let pipeline regenerate with Theo stages, verify quality.
