# Research Papers Vector Integration + Journal Rename

**Date**: 2026-04-08
**Status**: Approved

## Summary

Three changes:
1. Rename "Articles" to "Journals" in the DbAuditPage Qdrant dropdown
2. Migrate `theo_research_sections` to a new `research` collection with named vectors (dense + BM25), consistent with the other 5 collections
3. Wire `research` into Lyra chat auto-retrieve so published Theo papers are always searchable

## 1. DbAuditPage Display Labels

Add a display name map in `DbAuditPage.tsx`:

| Collection ID | Display Name     |
|---------------|------------------|
| sites         | Sites            |
| news          | Stories          |
| transcripts   | Transcripts      |
| articles      | Journals         |
| empires       | Empires          |
| research      | Research Papers  |

Applied to both the collection list (line 1337) and reindex buttons (lines 1399-1404).

## 2. Migrate theo_research_sections to Named Vectors + BM25

**Collection rename**: `theo_research_sections` → `research`

### theo_research_index.py changes
- `COLLECTION_NAME = "research"`
- `_ensure_collection()` creates with named vectors (`dense` + `bm25` sparse) matching other collections
- `index_paper()` generates dense (Voyage) + BM25 sparse vectors per section
- `delete_paper()`, `search_similar()`, `search_sections()` updated for new collection + named vectors

### build_lyra_index.py changes
- New `index_research()` function: reads `research_requests WHERE is_public = TRUE`, splits by `##` headings, embeds dense + BM25, upserts to `research` collection
- CLI option `--collection research` added
- Included in default "all" run
- Incremental with content hashing

### Migration
Run `build_lyra_index.py --collection research --rebuild` to populate from existing published papers. Old `theo_research_sections` collection is abandoned.

## 3. Lyra Auto-Retrieve Integration

### lyra_agent.py `_auto_retrieve()`
- Add `research` search task (limit=3 per sub-query) alongside sites/news/transcripts/articles
- Dedup by `paper_id`
- Format as `### Research Papers` context section (title, author, effort tier, section preview)
- `### Weekly Articles` header renamed to `### Weekly Journals`
- Return type extended to include research chunks

### lyra_tools.py
- Add `"research"` to `_VALID_COLLECTIONS`
- Add rerank instructions for `research` in `_RERANK_INSTRUCTIONS` and `_THEORY_RERANK_INSTRUCTIONS`
- Add `research` to chunk compression (alongside transcripts/articles)

## 4. DbAuditPage + Backend — Research in Qdrant Status

### vector_sync.py
- Add `"research"` to `_COLLECTION_NAMES`
- PG count: `SELECT COUNT(*) FROM research_requests WHERE is_public = TRUE`
- Mark as chunked collection (PG = papers, Qdrant = sections)

### DbAuditPage.tsx
- Add `research` to collection array and `QdrantStatus` type
- Add reindex button
- Apply display name map

## Files to Modify

1. `ancient-nerds-map/src/pages/DbAuditPage.tsx` — display names, add research collection
2. `pipeline/lyra/theo_research_index.py` — migrate to named vectors, rename collection
3. `scripts/build_lyra_index.py` — add `index_research()` function
4. `api/services/lyra_agent.py` — add research to auto-retrieve, rename article header
5. `api/services/lyra_tools.py` — add research to valid collections, rerank instructions, compression
6. `api/routes/vector_sync.py` — add research to status + reindex
