# Permanent Researcher + Knowledge Graph — Design

**Date:** 2026-07-26
**Status:** Approved (brainstorm with owner)

## Goal

Run Theo research continuously so the upgraded MiniMax **Max Plan** (flat,
use-it-or-lose-it) is saturated, while website-submitted research always runs
in parallel at full speed. Topics come from a **knowledge graph** that doubles
as the researcher's brain and, later, as a public mind-map section of the
website.

## Decisions made

| Question | Decision |
|---|---|
| MiniMax upgrade path | **Max Plan (flat)** — saturate it; verify actual Max limits before calibrating |
| Topic sources | Rabbit holes + Stories/News + Map sites + Journal themes — all injected as graph nodes |
| Graph role | **Graph as brain**: frontier nodes ARE the topic queue (not a separate visualization layer) |
| Publish policy | **Auto-publish on quality-gate pass**; gate failures held + Discord notification |
| UI parallelism | **Option 1 — two lanes**: UI runs concurrently at full speed, no preemption |

## Architecture (three sub-projects, build order B → A → C)

### B) Graph data layer + topic engine (first — feeds everything)

**Tables (Postgres):**

- `research_nodes`: `id`, `label`, `kind` (`topic|paper|site|entity`),
  `status` (`frontier|researching|explored`), `score` fields
  (connectivity, source_signal, last_touched), `created_from`
  (`rabbit_hole|story|journal|site|manual|backfill`), `paper_id` (FK
  research_requests, SET NULL), `site_id` (FK unified_sites, SET NULL)
- `research_edges`: `src`, `dst`, `kind`
  (`leads_to|cites|contradicts|about_site|related`), `weight`

**Writers:**

1. **Pipeline persistence** — at run end the orchestrator writes what it
   currently discards: the angle tree, unexplored rabbit holes (→ new
   `frontier` nodes with `leads_to` edges from the paper node), site links,
   reference edges. Data already exists in `ResearchState`; this is
   persistence, not new computation.
2. **Source injectors** — periodic jobs create seed nodes from: Lyra stories
   (weight = mention count), weekly journal themes, prominent map sites
   without papers (card rarity Epic/Legendary), radar discoveries. Dedupe via
   Qdrant similarity + name match before insert.
3. **Backfill** — one LLM extraction pass over the 7 existing published papers.

**Frontier scoring** (topic engine): `connectivity + source_signal +
diversity_penalty (avoid researching the same cluster repeatedly) + small
random component`. Highest-scoring frontier node becomes the next batch topic.

### A) Permanent researcher operation

- **Feeder:** when the batch queue is empty and budget allows, enqueue the
  best frontier node as a `research_request (is_batch=true)`. The 47 existing
  batch rows drain first through the normal queue.
- **Two lanes (worker + limiter):**
  - `THEO_PARALLEL_SLOTS=2` with the claim rule: at most 1 batch run at a
    time; UI submissions claim the free slot anytime (they already outrank
    batch in the claim ORDER BY).
  - Replace the global crawl pin with **per-run pacing lanes**: run priority
    travels via contextvar (same pattern as `token_accounting.bind`), and the
    limiter applies crawl pacing only to low-priority calls. UI calls run at
    full adaptive speed concurrently.
- **Saturation controller:** batch crawl delay becomes adaptive instead of
  fixed 60s — target: use the Max-Plan 5h window down to a floor of ~30%
  remaining (UI + Lyra always keep headroom). Calibrate after the real Max
  limits are known.
- **Auto-publish:** move the stress-test host poller into the worker — on
  completion, if the quality gate passes, approve + publish (author account
  "Theo"); on gate failure, hold + Discord webhook. The VPS host poller
  (`scripts/auto_publish_batch.py`, nohup) is then retired.

### C) Mind-map website section (last — own brainstorm when B has data)

- Public endpoint `GET /api/v1/graph` (CC BY 4.0, consistent with
  `/api/v1/research`).
- Frontend: 3D force graph in the existing Three.js stack — explored nodes
  solid, frontier pulsing ("what Theo thinks about next"), click → paper/site.
- Detailed design deferred until B produces real data.

## Error handling

- Quota exhaustion mid-run: existing defer/watchdog machinery unchanged.
- Feeder failure: batch queue simply stops refilling — no user impact; alert
  via existing log monitoring.
- Graph write failure at run end: paper completion must not fail — graph
  persistence is best-effort with an error log, backfillable later.
- Deploys still restart in-flight runs (known cost); the feeder makes this
  self-healing (run requeues, continues).

## Testing

- Limiter lanes: unit-test that low-priority calls pace while high-priority
  calls run unthrottled concurrently (extend the existing pin tests).
- Topic engine: scoring function unit tests (diversity penalty, dedupe).
- Pipeline persistence: assert a completed test run writes nodes/edges
  matching its angle tree.
- E2E: one batch run + one UI run concurrently on prod, verify pacing split
  via limiter stats.

## Open items

1. **Verify Max Plan limits** (5h window + weekly cap) before buying and
   before calibrating the saturation controller.
2. **"Theo" author account** — create a user for auto-published papers
   (`published_by`, public attribution).
3. Mind-map section scope (sub-project C) gets its own brainstorm.
