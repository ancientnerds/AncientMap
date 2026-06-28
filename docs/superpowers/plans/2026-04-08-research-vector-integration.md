# Research Papers Vector Integration + Journal Rename — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Theo research papers to a full hybrid-search Qdrant collection, wire it into Lyra chat auto-retrieve, and rename "Articles" to "Journals" in the database admin UI.

**Architecture:** The existing `theo_research_sections` collection (dense-only, unnamed vectors) is replaced by a new `research` collection using named vectors (`dense` + `bm25`) matching the other 5 collections. `build_lyra_index.py` gets a new `index_research()` function. Lyra's `_auto_retrieve()` adds research as a 5th parallel search. The DbAuditPage gets a display name map and the new collection.

**Tech Stack:** Python/FastAPI, Qdrant (named vectors + BM25 sparse), Voyage AI embeddings, TypeScript/React

---

### Task 1: Migrate `theo_research_index.py` to Named Vectors + BM25

**Files:**
- Modify: `pipeline/lyra/theo_research_index.py`

- [ ] **Step 1: Update collection name and ensure_collection**

In `pipeline/lyra/theo_research_index.py`, change `COLLECTION_NAME` and update `_ensure_collection()` to create with named vectors:

```python
# Line 21 — change collection name
COLLECTION_NAME = "research"

# Lines 88-101 — replace _ensure_collection with named vectors + BM25
def _ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, Modifier, SparseVectorParams, VectorParams

    from api.services.lyra_embeddings import get_qdrant_client

    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
        logger.info("Created Qdrant collection: %s", COLLECTION_NAME)
```

- [ ] **Step 2: Update `index_paper()` to generate dense + BM25 vectors**

Replace the embedding and point-building section of `index_paper()` (lines 118-158):

```python
def index_paper(
    paper_id: str,
    paper_text: str,
    paper_title: str,
    paper_slug: str,
    author_username: str,
    author_discord_id: str,
    effort: str,
    published_at: str,
) -> int:
    """Split paper into sections, embed, and upsert to Qdrant.

    Returns the number of sections indexed.
    """
    from qdrant_client.models import PointStruct, SparseVector

    from api.services.lyra_embeddings import get_embeddings, get_qdrant_client, get_sparse_model

    sections = _split_sections(paper_text)
    if not sections:
        logger.warning("No sections found in paper %s", paper_id)
        return 0

    _ensure_collection()

    # Embed all sections in one batch — dense + BM25
    embedder = get_embeddings("index")
    sparse_model = get_sparse_model()
    texts = [f"{s['title']}\n\n{s['text']}" for s in sections]
    dense_vectors = embedder.embed_documents(texts)
    sparse_vectors = list(sparse_model.embed(texts))

    # Build Qdrant points with named vectors
    points = []
    for section, dense_vec, sparse_vec in zip(sections, dense_vectors, sparse_vectors, strict=True):
        point_id = _deterministic_uuid(paper_id, section["index"])
        points.append(
            PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec,
                    "bm25": SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
                payload={
                    "paper_id": paper_id,
                    "paper_title": paper_title,
                    "paper_slug": paper_slug,
                    "section_title": section["title"],
                    "section_text": section["text"],
                    "section_index": section["index"],
                    "title": f"{paper_title} — {section['title']}",
                    "text_preview": section["text"][:2000],
                    "author_username": author_username,
                    "author_discord_id": author_discord_id,
                    "effort": effort,
                    "published_at": published_at,
                },
            )
        )

    client = get_qdrant_client()
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("Indexed %d sections for paper %s (%s)", len(points), paper_id, paper_title)
    return len(points)
```

Note: The payload now includes `title` (paper + section combined) and `text_preview` keys so that `_format_payload_for_rerank()` in `lyra_tools.py` picks them up automatically.

- [ ] **Step 3: Update `search_similar()` to use named vectors**

In `search_similar()` (lines 186-231), change the `client.search()` call to use the `"dense"` named vector:

```python
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=("dense", query_vector),
        limit=limit * 3,  # oversample then deduplicate by paper
        score_threshold=0.3,
    )
```

The only change is `query_vector=query_vector` → `query_vector=("dense", query_vector)`.

- [ ] **Step 4: Update `search_sections()` to use named vectors**

In `search_sections()` (lines 234-277), same change:

```python
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=("dense", query_vector),
        limit=limit * 3,
        score_threshold=0.35,
    )
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/theo_research_index.py
git commit -m "refactor: migrate theo_research_index to named vectors + BM25"
```

---

### Task 2: Add `index_research()` to `build_lyra_index.py`

**Files:**
- Modify: `scripts/build_lyra_index.py`

- [ ] **Step 1: Update module docstring**

Replace lines 3-24 to include the `research` collection:

```python
"""
Build Lyra Vector Index — Qdrant collections for hybrid semantic search.

Creates six collections with named vectors:
  - sites: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - news: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - transcripts: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - articles: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - empires: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)
  - research: dense (voyage-4-large, 1024-dim) + bm25 (sparse, IDF-weighted)

Queries use voyage-4 for dense (shared embedding space, cheaper) + Qdrant/bm25 for sparse.
RRF fusion merges results, then Voyage rerank-2.5-lite scores the top-K.

Incremental: only indexes items not already in Qdrant.

Usage:
  python scripts/build_lyra_index.py
  python scripts/build_lyra_index.py --collection sites
  python scripts/build_lyra_index.py --collection news
  python scripts/build_lyra_index.py --collection transcripts
  python scripts/build_lyra_index.py --collection articles
  python scripts/build_lyra_index.py --collection empires
  python scripts/build_lyra_index.py --collection research
  python scripts/build_lyra_index.py --rebuild  # wipe and rebuild
"""
```

- [ ] **Step 2: Add `index_research()` function**

Insert after `index_empires()` (after line 959), before the `_region_from_polity_id()` helper or `main()`:

```python
def index_research(
    client: QdrantClient,
    embeddings,
    sparse_model,
    rebuild: bool = False,
    *,
    vector_size: int = 1024,
    suffix: str = "",
):
    """Index published Theo research papers into Qdrant for semantic search.

    Splits papers by ## headings into sections, same chunking as theo_research_index.py.
    """
    collection = f"research{suffix}"

    if rebuild:
        try:
            client.delete_collection(collection)
        except Exception as exc:
            logger.warning(f"Could not delete collection '{collection}': {exc}")

    ensure_collection(client, collection, vector_size)
    create_payload_indexes(client, collection, ["paper_id", "effort"])

    existing_hashes = {} if rebuild else get_existing_hashes(client, collection)
    logger.info(f"Research collection has {len(existing_hashes)} existing points")

    sql = """
        SELECT id::text AS id, question, result_json, effort,
               published_at::text AS published_at,
               published_by, slug
        FROM research_requests
        WHERE is_public = TRUE AND result_json IS NOT NULL
        ORDER BY published_at DESC
    """

    with get_session() as session:
        result = session.execute(text(sql))
        rows = result.fetchall()

    logger.info(f"Found {len(rows)} published research papers")

    # Split sections using the same logic as theo_research_index
    _SKIP_SECTIONS = frozenset({"references", "methodology", "appendix: specialist debate summary"})

    all_chunks = []
    for r in rows:
        try:
            result_data = json.loads(r.result_json) if r.result_json else {}
        except (json.JSONDecodeError, TypeError):
            continue

        paper_text = result_data.get("report", "")
        paper_title = result_data.get("title", r.question)
        if not paper_text:
            continue

        # Content hash from first 2000 chars of report
        content_hash = _content_hash(paper_text[:2000])

        # Split by ## headings (same logic as theo_research_index._split_sections)
        sections = []
        current_title = ""
        current_lines = []
        section_index = 0
        for line in paper_text.split("\n"):
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                if current_title and current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text and current_title.lower() not in _SKIP_SECTIONS:
                        sections.append({
                            "title": current_title,
                            "text": section_text[:2000],
                            "index": section_index,
                        })
                        section_index += 1
                current_title = heading_match.group(1).strip()
                current_lines = []
            elif line.startswith("# ") and not current_title:
                continue  # Paper title heading — skip
            else:
                current_lines.append(line)

        # Last section
        if current_title and current_lines:
            section_text = "\n".join(current_lines).strip()
            if section_text and current_title.lower() not in _SKIP_SECTIONS:
                sections.append({
                    "title": current_title,
                    "text": section_text[:2000],
                    "index": section_index,
                })

        for section in sections:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"theo:{r.id}:{section['index']}"))
            if point_id in existing_hashes and existing_hashes[point_id] == content_hash:
                continue
            all_chunks.append({
                "point_id": point_id,
                "paper_id": r.id,
                "paper_title": paper_title,
                "paper_slug": r.slug or "",
                "section_title": section["title"],
                "section_text": section["text"],
                "section_index": section["index"],
                "author_username": r.published_by or "",
                "effort": r.effort,
                "published_at": r.published_at or "",
                "content_hash": content_hash,
            })

    logger.info(f"Research sections to index (new + changed): {len(all_chunks)}")

    if not all_chunks:
        logger.info("Nothing to index for research")
        return

    total_indexed = 0
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]

        texts = []
        for c in batch:
            texts.append(f"{c['paper_title']} — {c['section_title']} | {c['section_text']}")

        dense_vectors = embeddings.embed_documents(texts)
        sparse_vectors = list(sparse_model.embed(texts))

        points = []
        for c, dense_vec, sparse_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                PointStruct(
                    id=c["point_id"],
                    vector={
                        "dense": dense_vec,
                        "bm25": SparseVector(
                            indices=sparse_vec.indices.tolist(),
                            values=sparse_vec.values.tolist(),
                        ),
                    },
                    payload={
                        "paper_id": c["paper_id"],
                        "paper_title": c["paper_title"],
                        "paper_slug": c["paper_slug"],
                        "section_title": c["section_title"],
                        "section_index": c["section_index"],
                        "title": f"{c['paper_title']} — {c['section_title']}",
                        "text_preview": c["section_text"][:2000],
                        "author_username": c["author_username"],
                        "effort": c["effort"],
                        "published_at": c["published_at"],
                        "content_hash": c["content_hash"],
                    },
                )
            )

        client.upsert(collection_name=collection, points=points)
        total_indexed += len(points)
        logger.info(f"Indexed {total_indexed}/{len(all_chunks)} research sections")

    logger.info(f"Done indexing {total_indexed} research sections")
```

- [ ] **Step 3: Update `main()` to include research**

In `main()`, add `"research"` to the `--collection` choices (line 992) and add the call after empires (after line 1019):

```python
    parser.add_argument(
        "--collection",
        choices=["sites", "news", "transcripts", "articles", "empires", "research"],
        help="Only index this collection",
    )
```

And after the empires block:

```python
    if args.collection is None or args.collection == "research":
        index_research(client, embeddings, sparse_model, **kwargs)
```

- [ ] **Step 4: Commit**

```bash
git add scripts/build_lyra_index.py
git commit -m "feat: add research collection to build_lyra_index.py"
```

---

### Task 3: Wire Research into Lyra Auto-Retrieve

**Files:**
- Modify: `api/services/lyra_agent.py`

- [ ] **Step 1: Add research search task to `_auto_retrieve()`**

In `_auto_retrieve()` at line 802, add after the articles search task:

```python
    for sub_q in queries:
        search_tasks.append(("research", sub_q, 3))
```

- [ ] **Step 2: Add research deduplication tracking**

At line 817, add after `seen_article_ids`:

```python
    seen_paper_ids: set[str] = set()
    research_chunks: list[dict] = []
```

- [ ] **Step 3: Add research result distribution**

In the `for coll, results, vt in search_results:` loop (line 821), add a new `elif` block after the `"articles"` block (after line 850):

```python
        elif coll == "research":
            for r in results:
                pid = r.get("paper_id")
                if pid and pid not in seen_paper_ids:
                    seen_paper_ids.add(pid)
                    research_chunks.append(r)
```

- [ ] **Step 4: Format research results as context**

After the article formatting block (after line 918), add:

```python
    # Format research paper results
    research_chunks_filtered = _apply_relevance_filter(research_chunks)
    if research_chunks_filtered:
        research_chunks_filtered = _semantic_dedup(research_chunks_filtered, text_key="text_preview")
        lines = []
        for r in research_chunks_filtered:
            paper_title = r.get("paper_title", "")
            section_title = r.get("section_title", "")
            author = r.get("author_username", "")
            effort = r.get("effort", "")
            slug = r.get("paper_slug", "")
            preview = r.get("text_preview", "")[:500]
            line = f"- **{paper_title}** > {section_title} (by {author}, {effort}, slug: {slug})"
            if preview:
                line += f"\n  > {preview}"
            lines.append(line)
        context_parts.append("### Research Papers\n" + "\n".join(lines))
```

- [ ] **Step 5: Rename the articles context header**

At line 918, change:

```python
        context_parts.append("### Weekly Articles\n" + "\n".join(lines))
```

to:

```python
        context_parts.append("### Weekly Journals\n" + "\n".join(lines))
```

- [ ] **Step 6: Update return type and return value**

Update the function signature return type (line 764):

```python
) -> tuple[str, list[dict], list[dict], float | None, int, list[dict], list[dict], list[dict]]:
```

Update the docstring Returns section (line 778-781):

```python
    Returns:
        Tuple of (formatted context string, list of site result dicts for map highlighting,
        list of news result dicts for sidebar cards, average relevance score or None,
        total Voyage tokens used, list of transcript chunk dicts, list of article chunk dicts,
        list of research chunk dicts).
```

Update the return statement (line 939-947):

```python
    return (
        context_str,
        site_results,
        news_results,
        avg_relevance,
        total_voyage_tokens,
        transcript_chunks,
        article_chunks,
        research_chunks,
    )
```

Also update the early return at line 921 (the `if not context_parts:` case):

```python
    if not context_parts:
        return "", [], [], None, total_voyage_tokens, [], article_chunks, research_chunks
```

- [ ] **Step 7: Update the caller to unpack the new return value**

At lines 1541-1549, update the unpacking:

```python
            (
                retrieved_context,
                auto_site_results,
                auto_news_results,
                avg_relevance,
                vt,
                auto_transcript_results,
                auto_article_results,
                auto_research_results,
            ) = auto_result_or_exc
```

After the article dedup block (after line 1566), add research dedup:

```python
            # Extend all_research (deduped by paper_id)
            # (research results are only used for context, no separate tracking needed yet)
```

Note: Research results don't need a separate `all_research` accumulator unless they're used elsewhere in the pipeline. They're already included in `retrieved_context` via the context_parts. If future features need research tracking, add it then.

- [ ] **Step 8: Commit**

```bash
git add api/services/lyra_agent.py
git commit -m "feat: add research papers to Lyra auto-retrieve"
```

---

### Task 4: Add Research to Lyra Tools (Valid Collections + Rerank Instructions)

**Files:**
- Modify: `api/services/lyra_tools.py`

- [ ] **Step 1: Add research to `_VALID_COLLECTIONS`**

At line 1076, change:

```python
    _VALID_COLLECTIONS = {"sites", "news", "transcripts", "articles", "empires", "research"}
```

- [ ] **Step 2: Update the `vector_search` docstring**

At lines 1061-1074, update to mention research:

```python
    """Deep semantic search across sites, news, transcripts, articles, empires, or research using hybrid dense+BM25 vectors.

    Use for deep semantic search when keyword search (search_sites, search_news) didn't find enough.
    Works across sites, news, transcripts, articles, empires, and research collections. Results contain
    collection-specific fields for creating the appropriate marker types.

    Args:
        query: Natural language query.
        collection: Which collection to search: 'sites', 'news', 'transcripts', 'articles', 'empires', or 'research'.
        limit: Max results (default 5).
        country: Filter by country name (e.g. 'Turkey', 'Egypt').
        period: Filter by period name (e.g. 'Bronze Age', 'Neolithic').
        site_type: Filter by site type (e.g. 'settlement', 'temple').
        channel: Filter by channel name (e.g. 'World of Antiquity'). Works on news and transcripts collections.
    """
```

- [ ] **Step 3: Add rerank instructions for research**

In `_RERANK_INSTRUCTIONS` (after the `"empires"` entry at line 711), add:

```python
    "research": (
        "Prioritize research paper sections that directly address the queried topic with "
        "in-depth analysis, cited evidence, and expert synthesis. Rank sections with "
        "specific archaeological findings and scholarly argumentation higher than summaries."
    ),
```

In `_THEORY_RERANK_INSTRUCTIONS` (after the `"empires"` entry at line 735), add:

```python
    "research": (
        "Prioritize research paper sections discussing theories, hypotheses, or alternative "
        "explanations with scholarly evidence and critical analysis. Rank sections with "
        "substantive argumentation and cited sources higher than passing mentions."
    ),
```

- [ ] **Step 4: Add research to chunk compression**

At line 1044-1045, change:

```python
    if collection in ("transcripts", "articles", "research") and items:
```

- [ ] **Step 5: Commit**

```bash
git add api/services/lyra_tools.py
git commit -m "feat: add research to Lyra vector_search tool and rerank instructions"
```

---

### Task 5: Add Research to Backend Vector Sync Status

**Files:**
- Modify: `api/routes/vector_sync.py`

- [ ] **Step 1: Add PG count for research**

After line 112, add:

```python
        pg_research = session.execute(
            text("SELECT COUNT(*) FROM research_requests WHERE is_public = TRUE")
        ).scalar()
```

- [ ] **Step 2: Add research to collection names and PG counts**

At line 117, change:

```python
    _COLLECTION_NAMES = ["sites", "news", "transcripts", "articles", "empires", "research"]
```

At line 166, add to `_pg_counts`:

```python
    _pg_counts = {
        "sites": pg_sites,
        "news": pg_news,
        "transcripts": pg_transcripts,
        "articles": pg_articles,
        "empires": seshat_polity_count,
        "research": pg_research,
    }
```

- [ ] **Step 3: Mark research as chunked (no direct delta comparison)**

At line 172, change:

```python
    _no_delta = {"transcripts", "articles", "research"}  # chunk counts aren't comparable to PG counts
```

- [ ] **Step 4: Update ReindexRequest comment**

At line 92-93, change:

```python
    collection: str | None = (
        None  # "sites" | "news" | "transcripts" | "articles" | "empires" | "research" | None (all)
    )
```

- [ ] **Step 5: Commit**

```bash
git add api/routes/vector_sync.py
git commit -m "feat: add research collection to vector sync status"
```

---

### Task 6: Update DbAuditPage Frontend

**Files:**
- Modify: `ancient-nerds-map/src/pages/DbAuditPage.tsx`

- [ ] **Step 1: Add display name map and update QdrantStatus type**

At line 332, update the `QdrantStatus` interface to include `research`:

```typescript
  interface QdrantStatus { qdrant_available: boolean; collections: { sites: QdrantCollection; news: QdrantCollection; transcripts: QdrantCollection; articles: QdrantCollection; empires: QdrantCollection; research: QdrantCollection }; empires: QdrantEmpires; reindex: QdrantReindex; auto_reindex?: QdrantAutoReindex }
```

Add a display name map just above the `qdrantOpen` state (before line 334):

```typescript
  const qdrantDisplayNames: Record<string, string> = {
    sites: 'Sites',
    news: 'Stories',
    transcripts: 'Transcripts',
    articles: 'Journals',
    empires: 'Empires',
    research: 'Research Papers',
  }
```

- [ ] **Step 2: Update the collection list to include research and use display names**

At line 1337, change the collection array to include `research`:

```typescript
                  {(['sites', 'news', 'transcripts', 'articles', 'empires', 'research'] as const).map(col => {
```

At line 1343, change the display to use the name map:

```typescript
                        <span className="db-qdrant-col-name">{qdrantDisplayNames[col] || col}</span>
```

- [ ] **Step 3: Update the stale check to include research**

At line 1312, add research to the stale detection condition. After the articles check, add:

```
|| (qdrantStatus.collections.research.qdrant_count === 0 && qdrantStatus.collections.research.pg_count > 0)
```

At line 1324, add `'research'` to the chunked delta array:

```typescript
                    const chunkedDelta = (['transcripts', 'articles', 'research'] as const).reduce((sum, col) => {
```

- [ ] **Step 4: Update reindex buttons with display names**

At lines 1399-1405, replace the reindex buttons:

```typescript
                    <div className="db-qdrant-actions">
                      <button onClick={() => handleReindex()}>Reindex All</button>
                      <button onClick={() => handleReindex('sites')}>Sites</button>
                      <button onClick={() => handleReindex('news')}>Stories</button>
                      <button onClick={() => handleReindex('transcripts')}>Transcripts</button>
                      <button onClick={() => handleReindex('articles')}>Journals</button>
                      <button onClick={() => handleReindex('empires')}>Empires</button>
                      <button onClick={() => handleReindex('research')}>Research</button>
                      <button onClick={() => handleReindex(undefined, true)}>Rebuild All</button>
                    </div>
```

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/pages/DbAuditPage.tsx
git commit -m "feat: add research to DbAuditPage, rename articles to journals"
```

---

### Task 7: Verify and Test

- [ ] **Step 1: Verify frontend builds**

```bash
cd ancient-nerds-map && npm run build
```

Expected: Build completes without TypeScript errors.

- [ ] **Step 2: Verify backend linting**

```bash
cd api && python -m ruff check services/lyra_agent.py services/lyra_tools.py routes/vector_sync.py
cd pipeline/lyra && python -m ruff check theo_research_index.py
cd scripts && python -m ruff check build_lyra_index.py
```

Expected: No lint errors.

- [ ] **Step 3: Verify Python imports**

```bash
python -c "from pipeline.lyra.theo_research_index import index_paper, search_similar, search_sections, COLLECTION_NAME; print(f'Collection: {COLLECTION_NAME}')"
```

Expected: `Collection: research`

- [ ] **Step 4: Commit final verification**

If any lint/build fixes were needed, commit them:

```bash
git add -A
git commit -m "fix: lint and build fixes for research vector integration"
```
