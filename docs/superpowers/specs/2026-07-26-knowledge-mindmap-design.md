# Knowledge Mind-Map Section + Public Live Research — Design

**Date:** 2026-07-26
**Status:** Approved (owner brainstorm; sub-project C of the permanent-researcher design)

## Goal

A public "Knowledge" section (nav entry between Research and Library) that
renders the research knowledge graph as an interactive, explorable 3D mind
map — and a login-free live view of the permanent researcher on the Theo
page.

## Decisions

| Question | Decision |
|---|---|
| Visualization | 3D force graph (`3d-force-graph`, builds on the existing three.js) |
| Access | Fully public — no login for the Knowledge page or the live panel |
| Data source | Public v1 API (CC BY 4.0, consistent with `/api/v1/research`) |
| Nav placement | `Knowledge` between `Research` (/theo.html) and `Library` (/library.html) in HamburgerNav |

## API

1. **`GET /api/v1/graph`** (public v1 sub-app: rate-limited 10/min, Redis
   cache 300s):
   `{nodes: [{id, label, kind, status, signal, degree, paper_slug?, site_id?}],
     edges: [{src, dst, kind}], total_nodes}`.
   Explored paper nodes carry `paper_slug` (join research_requests) for
   linking. Hard cap 2000 nodes ordered by `signal + degree` (edges filtered
   to surviving nodes); `total_nodes` reports the uncapped count.
2. **`GET /api/theo/research/current`** (main API, no auth, cache 30s):
   the running batch run's public view — `{running: {question, started_at,
   sites_found, llm_calls, total_tokens, elapsed_s} | null,
   queued_batch: int, last_published: {title, slug} | null}`.
   Never exposes report content (unpublished stays private).

## Frontend

**Knowledge page** (`knowledge.html` + `src/pages/KnowledgePage.tsx`,
bootstrapped like the existing multi-page entries):

- `3d-force-graph` render of `/api/v1/graph`
- NERV aesthetic: explored nodes gold/solid, frontier dim-cyan pulsing,
  currently-researched node red pulsing (matched via the `current`
  endpoint's question ↔ researching node), node size by `signal + degree`
- Interactions: orbit/zoom/drag; click paper node → its paper page via
  `paper_slug`; click site node → globe deep link; frontier node → tooltip
  with the would-be research question
- Search box (find node, fly camera to it), kind filter chips
  (topic/paper/site), header with counts (explored/frontier) and "Theo is
  researching: …"
- Empty state before backfill: friendly note pointing at the live research

**Theo page live panel:** compact, visible without login above the research
library — running question, progress counters, elapsed time, polling
`/api/theo/research/current` every 30s; idle state shows queued count.
Links to the Knowledge page.

**Nav:** new `knowledge` item (network icon) in `HamburgerNav.tsx` between
theo and library.

## Error handling

- Graph fetch failure → retry note, page stays usable
- Empty graph → empty state (see above)
- `current` endpoint failure → panel hides silently (never blocks the page)

## Testing

- API: response shape, node cap, cache key, no-auth access of `current`
- Frontend: `npm run build` green (type-checks all new TSX); widget polling
  logic isolated in a hook for testability

## Out of scope

- Graph editing/curation UI, node voting, per-user views
- 2D fallback mode
