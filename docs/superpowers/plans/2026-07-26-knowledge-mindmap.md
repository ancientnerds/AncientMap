# Knowledge Mind-Map + Public Live Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Public "Knowledge" section rendering the research graph as an interactive 3D mind map, plus a login-free live-research panel on the Theo page.

**Architecture:** Two read-only endpoints (public v1 `/graph` with cap+cache; main-API `/theo/research/current` with 30s cache) feed a new Vite multi-page entry (`knowledge.html` → `KnowledgePage.tsx` using `3d-force-graph`) and a small polling panel on TheoPage. Nav entry goes between Research and Library.

**Tech Stack:** FastAPI + Redis cache (existing `cache_get/cache_set`), `3d-force-graph` (three.js-based, three@0.182 already present), React 18 multi-page pattern (`src/<name>Main.tsx`).

**Spec:** `docs/superpowers/specs/2026-07-26-knowledge-mindmap-design.md`

**Conventions:** ruff check+format per backend commit; `npm run build` green before frontend commits; never push (owner rule).

---

### Task 1: `GET /api/v1/graph`

**Files:**
- Modify: `api/schemas/public_v1.py` (append GraphNode/GraphEdge/GraphResponse)
- Modify: `api/routes/public_v1.py` (section 19, before the return; import new schemas)

- [ ] Schemas: `GraphNode {id, label, kind, status, signal: float, degree: int, paper_slug: str|None, site_id: str|None}`, `GraphEdge {src, dst, kind}`, `GraphResponse {nodes, edges, total_nodes}`.
- [ ] Endpoint `/graph`, tags=["Knowledge Graph"], rate-limited, cache key `pubv1:graph`, TTL 300. SQL: nodes joined with degree subquery + `research_requests.slug` (for kind='paper' via paper_id, only is_public), `ORDER BY (source_signal + deg) DESC LIMIT 2000`; edges filtered to surviving node ids in Python; `total_nodes` = uncapped COUNT.
- [ ] ruff, commit.

### Task 2: `GET /api/theo/research/current`

**Files:**
- Modify: `api/routes/theo.py` (new public route ABOVE `/research/{request_id}` so FastAPI matches the literal path first)

- [ ] Route (no auth dependency), cache key `theo:current`, TTL 30 via `api.cache`: running = the `status='running' AND is_batch` row (question, started_at iso, sites_found, llm_calls, total_tokens, elapsed_s computed from started_at); `queued_batch` = COUNT queued/deferred batch rows; `last_published` = latest is_public row (title from result_json, slug). Returns nulls when idle. No report content.
- [ ] Verify SQL against prod DB (read-only psql). ruff, commit.

### Task 3: Knowledge page frontend

**Files:**
- Create: `ancient-nerds-map/knowledge.html` (copy library.html head pattern; title "Knowledge Graph — Ancient Nerds"; script `/src/knowledgeMain.tsx`)
- Create: `ancient-nerds-map/src/knowledgeMain.tsx` (mount pattern like libraryMain.tsx)
- Create: `ancient-nerds-map/src/pages/KnowledgePage.tsx`
- Create: `ancient-nerds-map/src/pages/KnowledgePage.css`
- Modify: `ancient-nerds-map/vite.config.ts` (add `knowledge` input)
- Modify: `ancient-nerds-map/src/components/layout/HamburgerNav.tsx` (insert entry between theo and library)
- Modify: `ancient-nerds-map/package.json` (`npm install 3d-force-graph`)

- [ ] KnowledgePage: fetch `/api/v1/graph` + `/api/theo/research/current`; `ForceGraph3D` with `nodeColor` by status (explored `#FFD700`, frontier `#4fd8eb` dimmed, researching `#c02023`), `nodeVal = 1 + signal + degree`, `nodeLabel` tooltip (label + kind + frontier question hint), background transparent over the site's dark theme; click → paper (`/research.html?slug=`), site (`/globe.html?site=`), frontier (no-op, tooltip only). Header bar: counts, search input (find node by label substring, `cameraPosition` fly-to), kind filter chips re-filtering graphData client-side. Empty state + fetch-error state per spec.
- [ ] `npm run build` green, commit.

### Task 4: Theo page live panel

**Files:**
- Create: `ancient-nerds-map/src/components/theo/LiveResearchPanel.tsx` (+ CSS co-located in KnowledgePage.css? No — `ancient-nerds-map/src/components/theo/LiveResearchPanel.css`)
- Create: `ancient-nerds-map/src/hooks/useCurrentResearch.ts` (30s polling hook, silent failure → null)
- Modify: `ancient-nerds-map/src/pages/TheoPage.tsx` (render panel above the research library section, outside any auth gate)
- Modify: `ancient-nerds-map/src/pages/KnowledgePage.tsx` (header uses the same hook)

- [ ] Hook: `useCurrentResearch(): {running, queuedBatch, lastPublished} | null`, `setInterval` 30s + cleanup, silent catch.
- [ ] Panel: running → pulsing dot, question, elapsed (h:mm), counters (sources/calls), link "Explore the Knowledge Graph →" (/knowledge.html); idle → "N topics queued" + last published link; hook null → render nothing.
- [ ] `npm run build` green, commit.

### Task 5: Verification

- [ ] Backend: ruff over touched files; `pytest tests/api tests/pipeline -q -k "not security"` no NEW failures vs. the known environmental set.
- [ ] Frontend: `npm run build` full output check (dist present).
- [ ] Memory update + final commit.

## Self-review notes

- Spec coverage: API §1→Task 1, §2→Task 2, Knowledge page→Task 3, Theo panel→Task 4, nav→Task 3, error handling folded into Tasks 3/4, testing→Task 5 + build gates.
- Route-order pitfall documented in Task 2 (literal before parameterized path).
- Types: `paper_slug`/`site_id` naming consistent between schema (Task 1) and KnowledgePage click handler (Task 3).
