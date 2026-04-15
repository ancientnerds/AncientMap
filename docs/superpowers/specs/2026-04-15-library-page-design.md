# Library Page Design

## Context

Ancient Nerds accumulates citations and web sources across multiple content types: Stories (news items with web verification sources), Journals (weekly digests with citation markers), Theo Research papers (with full CitationRegistry including reliability tiers), and site descriptions (with claim-level citation mapping). These references are currently scattered across 4 different storage formats with no unified way to browse them. The Library page creates a dedicated, curated browsing experience for these sources — organized by historical period — so users can explore the project's accumulated reference material without needing Lyra chat.

## Architecture Overview

```
Pipeline runs (Lyra/Theo)
    ↓
library_aggregator.py scans 4 citation sources
    ↓
Upserts into library_sources table (deduplicated by URL)
    ↓
Static exporter writes public/data/library/ JSON files
    ↓
Frontend: library.html → LibraryPage.tsx (browse via static JSON)
                        → /api/library/search (search via API)
```

## Data Model

### `library_sources` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (PK) | Deterministic hex string: SHA-256(url)[:12], matches Theo CitationRegistry pattern |
| url | TEXT NOT NULL UNIQUE | Canonical key, deduplicated |
| title | TEXT NOT NULL | Source title |
| domain | TEXT | Extracted from URL (e.g. "jstor.org") |
| snippet | TEXT | Best snippet across all citations (longest wins) |
| reliability_tier | INT | 1=academic/institutional, 2=reputable, 3=general, 0=unknown |
| period_tags | TEXT[] | Inherited from parent content: ["Classical", "Bronze Age"] |
| source_types | TEXT[] | Where cited: ["story", "journal", "research", "site"] |
| first_seen | TIMESTAMP | When first ingested |
| last_seen | TIMESTAMP | Most recent citation |
| citation_count | INT | Total times cited across all content |
| parent_refs | JSONB | Backlinks: [{type, id, title}, ...] |
| created_at | TIMESTAMP | Row creation time |

**Foreign keys:** None. This is a materialized aggregate — parent_refs stores denormalized references. No CASCADE risk to unified_sites.

**Indexes:**
- UNIQUE on `url`
- GIN on `period_tags` (array containment queries)
- GIN on `source_types` (array containment queries)
- B-tree on `citation_count DESC` (default sort)
- GIN full-text on `title`, `snippet` (search)

## Pipeline: Citation Aggregator

New file: `pipeline/library_aggregator.py`

### Scan sources (in order)

1. **NewsItems** — extract `web_sources` JSONB. Period derived from linked site's `period_name` (via `site_id` FK). Parent ref: `{type: "story", id: item.id, title: item.headline}`.

2. **ResearchRequests** (where `is_public = true`) — parse `result_json` to extract CitationRegistry sources. These already have `reliability_tier` and `domain`. Period from paper's linked sites. Parent ref: `{type: "research", id: request.id, title: result_json.title}`.

3. **UnifiedSites** (where `raw_data->'description_citations'` is not null) — extract description_citations array. Period directly from `period_name`. Parent ref: `{type: "site", id: site.id, title: site.name}`.

4. **NewsArticles** (where `active = true`) — parse markdown content for citation markers, resolve to NewsItem web_sources. Parent ref: `{type: "journal", id: article.id, title: article.title}`.

### Upsert logic

On URL conflict:
- Merge `period_tags` (union of arrays)
- Append new entries to `parent_refs` (deduplicate by type+id)
- Increment `citation_count`
- Keep longest `snippet`
- Update `last_seen`
- Upgrade `reliability_tier` (keep highest/most specific, i.e. lowest non-zero number)

### Trigger

Runs after Lyra orchestrator completes, as a final step in `pipeline/lyra/orchestrator.py`. Also callable via `POST /api/library/refresh` (admin-only) for manual runs.

## Static Export

New method in `pipeline/static_exporter.py`: `export_library()`

### Output files

```
public/data/library/
├── index.json              # [{period, slug, count}, ...]
├── stats.json              # {total_sources, by_type: {}, by_tier: {}, top_domains: []}
└── periods/
    ├── classical.json
    ├── bronze-age.json
    ├── iron-age.json
    ├── medieval.json
    ├── ancient-egypt.json
    └── ...
```

### Period file structure

```json
{
  "period": "Classical",
  "slug": "classical",
  "total": 342,
  "sources": [
    {
      "id": "a1b2c3d4e5f6",
      "url": "https://www.jstor.org/stable/12345",
      "title": "Roman Forum excavation report 2024",
      "domain": "jstor.org",
      "snippet": "Recent excavations at the Roman Forum have revealed...",
      "reliability_tier": 1,
      "citation_count": 7,
      "source_types": ["research", "story"],
      "parent_refs": [
        {"type": "research", "id": "uuid", "title": "Roman Forum analysis"},
        {"type": "story", "id": "uuid", "title": "New excavation findings"}
      ]
    }
  ]
}
```

Sources sorted by `citation_count` descending within each period.

Period slugs derived from existing `period_name` values in unified_sites, lowercased and hyphenated. Sources with no period tag go into an "uncategorized" file.

## API

### `GET /api/library/search`

Query parameters:
- `q` (string) — full-text search on title, snippet, domain
- `period` (string) — filter by period tag
- `type` (string) — filter by source_type: story, journal, research, site
- `tier` (int) — filter by reliability_tier
- `sort` (string) — `citations` (default), `recent`, `title`
- `page` (int, default 1)
- `page_size` (int, default 50)

Response:
```json
{
  "items": [{ /* same shape as period file sources */ }],
  "total": 128,
  "page": 1,
  "page_size": 50
}
```

New route file: `api/routes/library.py`, registered in `api/main.py`.

## Frontend

### New files

| File | Purpose |
|------|---------|
| `library.html` | HTML entry point |
| `src/libraryMain.tsx` | Vite entry, mounts LibraryPage |
| `src/pages/LibraryPage.tsx` | Main page component |
| `src/components/library/LibraryCard.tsx` | Source card in grid |
| `src/components/library/LibraryDetailCard.tsx` | Overlay detail card |
| `src/styles/library.css` | Page styles |
| `src/types/library.ts` | TypeScript interfaces |

### Modified files

| File | Change |
|------|--------|
| `vite.config.ts` | Add `library` entry point |
| `src/components/layout/HamburgerNav.tsx` | Add Library nav item with book icon |

### Page layout (top to bottom)

1. **PageHeader** — standard, `currentPage="library"`
2. **Search bar** — text input, searches on Enter or 300ms debounce. When active, replaces period sections with search results grid. Clear button returns to browse mode.
3. **Stats bar** — "4,230 sources across 12 periods" from `stats.json`
4. **Period sections** — each rendered as:
   - Section header: period name + source count
   - Card grid: top 12 sources by citation count
   - "Show all N sources" expander if period has >12
   - Lazy-loaded: period JSON fetched when section scrolls into viewport (IntersectionObserver)
5. **Source detail overlay** — triggered on card click:
   - Title + domain + reliability badge
   - Snippet text
   - "Cited in:" list with clickable links to Stories/Journals/Research papers
   - "Visit source" external link button

### LibraryCard component

- Domain favicon (via `https://www.google.com/s2/favicons?domain=X`) or fallback type icon
- Title (2-line truncation)
- Domain name in muted text
- Reliability tier badge (color-coded: green=academic, blue=reputable, gray=general)
- Citation count: "Cited 7x"
- Period pills (small, max 2 shown + "+N more")

### Data flow

- On mount: fetch `library/index.json` and `library/stats.json`
- Render period section headers from index
- On scroll into viewport: fetch `library/periods/{slug}.json`
- On search: `GET /api/library/search?q=...` with debounce
- On card click: show detail overlay (data already loaded from period file)

## Verification

1. Run `library_aggregator.py` standalone — verify it populates `library_sources` from all 4 citation sources
2. Run static exporter — verify `public/data/library/` files are generated with correct structure
3. Start Vite dev server — verify `library.html` loads, period sections render, lazy loading works
4. Test search — verify API returns results, frontend displays them
5. Test detail card — verify parent refs link correctly to Stories/Journals/Research pages
6. Test with empty data — verify graceful empty states
7. Run existing pipeline — verify aggregator runs as final step without breaking Lyra/Theo
