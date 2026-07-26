# Full-Project Knowledge Graph — Design

**Date:** 2026-07-26
**Status:** Approved (owner: "der Knowledge Graph war für das GESAMTE PROJEKT gedacht")

## Goal

Extend the research knowledge graph into the project-wide brain: Ancient
Nerds original sites, radar discoveries, periods, empires, countries,
cultures, stories, videos, channels, journals — one explorable 3D mind map,
with the permanent researcher's layer living on top.

## Decisions

| Question | Decision |
|---|---|
| Site scope | ONLY `ancient_nerds` originals (5,012) + radar discoveries (337) — no 750K long tail |
| Node classes | Everything that belongs in a project graph (owner) — see ontology |
| Cultures source | `news_items.entities.cultures` (card_stats.civilization is empty — verified 0 rows) |
| Status semantics | New status **`reference`** for structural knowledge; the frontier picker only ever consumes `frontier`, so ingested sites/stories can never flood the research queue |
| Scale target | ~10–13K nodes / ~30K edges — current 3d-force-graph with performance tuning, no LOD architecture |

## Ontology

Nodes (all in `research_nodes`; `kind` is a free string, no migration):

- `site` (AN originals with `site_id`; radar without), `period` (12 canonical
  epochs, same bucketing CASE as the public API), `country` (98), `empire`
  (Seshat polities from the api-side loader), `culture` + `person` (from
  `news_items.entities`, only when mentioned in ≥2 stories — keeps one-off
  noise out), `story` (news_items), `video` + `channel`, `journal`,
  plus existing `paper` / `topic` / `entity` from the research layer.

Edges: `dated_to` (site→period, empire→period), `located_in` (site→country),
`mentions` (story→site/person/culture via the pre-extracted entities JSON +
the direct news_items.site_id FK), `from_video` (story→video), `on_channel`
(video→channel), `covers` (journal→video), plus existing research kinds.
Honest v1 omission: site↔empire matching is fuzzy geo-temporal work —
empires only link to periods for now.

## Components

1. **`pipeline/lyra/graph_full_ingest.py`** — idempotent SQL-only ingestion
   (`run_full_ingest()`), one function per class, upserts that never
   downgrade an existing node's status; nightly execution from the worker
   feeder loop; zero LLM tokens.
2. **API**: `/api/v1/graph` cap 2000 → 15000, optional `kinds` filter param
   (comma list), cache key includes it.
3. **Frontend Knowledge page**: colors by **kind** (status keeps driving the
   frontier/researching pulse), layer chips grouped (Structure / Sites /
   Content / Research), **focus mode** — clicking a node dims everything
   outside its 1-hop neighborhood and shows an info card with an "open
   paper/site" action (replaces direct click-navigation, which is wrong at
   10K density); performance tuning (nodeResolution, cooldownTicks).

## Error handling

Ingest functions log-and-continue per class; the feeder loop survives any
ingest failure. Frontend unchanged: fetch failure → retry note.

## Testing

Unit tests for period bucketing and the ≥2-mentions entity threshold;
read-only SQL validation against prod; `npm run build` green; full ingest
executed post-deploy with count verification.
