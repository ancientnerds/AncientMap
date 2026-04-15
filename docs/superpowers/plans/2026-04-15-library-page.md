# Library Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a curated Library page that aggregates citations and web sources from Stories, Journals, Research papers, and site descriptions into a browsable, period-organized reference index.

**Architecture:** A new `library_sources` DB table stores deduplicated citations. A pipeline aggregator scans 4 source types and upserts into this table. The static exporter writes period-organized JSON files. The frontend browses via static JSON with an API search endpoint for direct lookup.

**Tech Stack:** Python/SQLAlchemy (backend), FastAPI (API), TypeScript/React (frontend), Vite (build), PostgreSQL (DB)

**Spec:** `docs/superpowers/specs/2026-04-15-library-page-design.md`

---

## File Map

### New files

| File | Responsibility |
|------|---------------|
| `pipeline/library_aggregator.py` | Scan 4 citation sources, upsert into library_sources table, trigger static export |
| `api/routes/library.py` | `GET /api/library/search` endpoint |
| `ancient-nerds-map/library.html` | HTML entry point |
| `ancient-nerds-map/src/libraryMain.tsx` | React mount point |
| `ancient-nerds-map/src/pages/LibraryPage.tsx` | Main page component |
| `ancient-nerds-map/src/components/library/LibraryCard.tsx` | Source card in grid |
| `ancient-nerds-map/src/components/library/LibraryDetailCard.tsx` | Detail overlay |
| `ancient-nerds-map/src/styles/library.css` | Page + component styles |
| `ancient-nerds-map/src/types/library.ts` | TypeScript interfaces |

### Modified files

| File | Change |
|------|--------|
| `pipeline/database.py` | Add `LibrarySource` model |
| `pipeline/static_exporter.py` | Add `_export_library()` method, call it from `export_all()` |
| `pipeline/lyra/orchestrator.py` | Add `"library"` step to STEPS/STEP_ORDER |
| `api/main.py` | Register library router |
| `ancient-nerds-map/vite.config.ts` | Add `library` entry point |
| `ancient-nerds-map/src/components/layout/HamburgerNav.tsx` | Add Library nav item |

---

## Task 1: Database Model

**Files:**
- Modify: `pipeline/database.py` (add model after NewsArticle, ~line 985)
- Modify: `pipeline/lyra/orchestrator.py` (add migration in `_run_migrations`)

- [ ] **Step 1: Add LibrarySource model to database.py**

Add this after the `NewsArticle` class (around line 985):

```python
class LibrarySource(Base):
    """Aggregated citation/web source from across all content types."""

    __tablename__ = "library_sources"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # sha256(url)[:12]
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability_tier: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    period_tags: Mapped[list | None] = mapped_column(ARRAY(String(100)), nullable=True)
    source_types: Mapped[list | None] = mapped_column(ARRAY(String(20)), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    citation_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_library_sources_citation_count", "citation_count"),
        Index("idx_library_sources_period_tags", "period_tags", postgresql_using="gin"),
        Index("idx_library_sources_source_types", "source_types", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<LibrarySource {self.id}: {self.domain}>"
```

Note: `ARRAY` needs to be imported from `sqlalchemy.dialects.postgresql`. Check if it's already imported — if not, add it to the existing import line that imports `JSONB`. The import line looks like:

```python
from sqlalchemy.dialects.postgresql import JSONB
```

Change to:

```python
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
```

- [ ] **Step 2: Add migration in orchestrator**

In `pipeline/lyra/orchestrator.py`, find the `_run_migrations(engine)` function. Add this migration at the end of the function body:

```python
    # Library sources table (2026-04-15)
    _maybe_run(conn, """
        CREATE TABLE IF NOT EXISTS library_sources (
            id VARCHAR(12) PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            title VARCHAR(500) NOT NULL,
            domain VARCHAR(255),
            snippet TEXT,
            reliability_tier INTEGER DEFAULT 0,
            period_tags TEXT[],
            source_types VARCHAR(20)[],
            first_seen TIMESTAMP DEFAULT NOW(),
            last_seen TIMESTAMP DEFAULT NOW(),
            citation_count INTEGER DEFAULT 1,
            parent_refs JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _maybe_run(conn, "CREATE INDEX IF NOT EXISTS idx_library_sources_citation_count ON library_sources (citation_count DESC)")
    _maybe_run(conn, "CREATE INDEX IF NOT EXISTS idx_library_sources_period_tags ON library_sources USING gin (period_tags)")
    _maybe_run(conn, "CREATE INDEX IF NOT EXISTS idx_library_sources_source_types ON library_sources USING gin (source_types)")
```

Look at existing migrations in that function to see what `_maybe_run` looks like — it's a helper that wraps `conn.execute(text(...))` with error handling.

- [ ] **Step 3: Verify migration syntax**

Run:
```bash
cd /c/PythonProjects/AncientMap && python -c "from pipeline.database import LibrarySource; print('Model loaded:', LibrarySource.__tablename__)"
```

Expected: `Model loaded: library_sources`

- [ ] **Step 4: Commit**

```bash
git add pipeline/database.py pipeline/lyra/orchestrator.py
git commit -m "feat(library): add LibrarySource database model and migration"
```

---

## Task 2: Library Aggregator — Core

**Files:**
- Create: `pipeline/library_aggregator.py`

This task builds the core aggregation logic: URL hashing, upsert, and the `aggregate_all()` entry point. The individual scanners (NewsItems, Research, etc.) are added in Task 3.

- [ ] **Step 1: Create pipeline/library_aggregator.py with core logic**

```python
"""
Library Aggregator — scans citations from Stories, Journals, Research, and Sites,
then upserts into the library_sources table for the Library page.

Run standalone:  python -m pipeline.library_aggregator
Triggered by:    Lyra orchestrator after pipeline cycle
"""

import hashlib
import json
import logging
import urllib.parse
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pipeline.database import (
    LibrarySource,
    NewsArticle,
    NewsItem,
    ResearchRequest,
    UnifiedSite,
    get_session,
)

logger = logging.getLogger(__name__)


def _url_id(url: str) -> str:
    """Deterministic 12-char hex ID from URL, matching Theo CitationRegistry pattern."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def _extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.removeprefix("www.")
    except Exception:
        return ""


class LibraryAggregator:
    """Scans all citation sources and upserts into library_sources."""

    def __init__(self):
        self.pending: dict[str, dict] = {}  # url_id -> row dict
        self.stats = {"news_items": 0, "research": 0, "sites": 0, "articles": 0}

    def _register(
        self,
        url: str,
        title: str,
        snippet: str,
        source_type: str,
        period_name: str | None,
        parent_type: str,
        parent_id: str,
        parent_title: str,
        reliability_tier: int = 0,
    ):
        """Register a citation. Merges if URL already seen."""
        url = url.strip()
        if not url or not title:
            return

        uid = _url_id(url)
        now = datetime.now(UTC)

        parent_ref = {"type": parent_type, "id": parent_id, "title": parent_title[:200]}

        if uid in self.pending:
            row = self.pending[uid]
            # Merge period tags
            if period_name and period_name not in row["period_tags"]:
                row["period_tags"].append(period_name)
            # Merge source types
            if source_type not in row["source_types"]:
                row["source_types"].append(source_type)
            # Keep longest snippet
            if snippet and len(snippet) > len(row.get("snippet") or ""):
                row["snippet"] = snippet
            # Append parent ref (dedup by type+id)
            existing_keys = {(r["type"], r["id"]) for r in row["parent_refs"]}
            if (parent_ref["type"], parent_ref["id"]) not in existing_keys:
                row["parent_refs"].append(parent_ref)
            # Increment count
            row["citation_count"] += 1
            # Upgrade reliability (lower non-zero = better)
            if reliability_tier > 0:
                if row["reliability_tier"] == 0 or reliability_tier < row["reliability_tier"]:
                    row["reliability_tier"] = reliability_tier
            row["last_seen"] = now
        else:
            self.pending[uid] = {
                "id": uid,
                "url": url,
                "title": title[:500],
                "domain": _extract_domain(url),
                "snippet": snippet,
                "reliability_tier": reliability_tier,
                "period_tags": [period_name] if period_name else [],
                "source_types": [source_type],
                "first_seen": now,
                "last_seen": now,
                "citation_count": 1,
                "parent_refs": [parent_ref],
            }

    def _scan_news_items(self, session):
        """Scan NewsItem.web_sources for citations."""
        items = (
            session.query(NewsItem)
            .filter(NewsItem.web_sources.isnot(None))
            .options()
            .yield_per(500)
        )
        count = 0
        for item in items:
            if not item.web_sources:
                continue
            # Get period from linked site
            period = None
            if item.site_id:
                site = session.get(UnifiedSite, item.site_id)
                if site:
                    period = site.period_name
            for src in item.web_sources:
                url = src.get("url", "")
                title = src.get("title", "")
                snippet = src.get("snippet", "")
                if url:
                    self._register(
                        url=url,
                        title=title or _extract_domain(url),
                        snippet=snippet,
                        source_type="story",
                        period_name=period,
                        parent_type="story",
                        parent_id=str(item.id),
                        parent_title=item.headline or "",
                    )
                    count += 1
        self.stats["news_items"] = count
        logger.info(f"  Scanned news items: {count} citations")

    def _scan_research(self, session):
        """Scan published ResearchRequest.result_json for citations."""
        requests = (
            session.query(ResearchRequest)
            .filter(
                ResearchRequest.is_public.is_(True),
                ResearchRequest.result_json.isnot(None),
            )
            .all()
        )
        count = 0
        for req in requests:
            try:
                result = json.loads(req.result_json) if isinstance(req.result_json, str) else req.result_json
            except (json.JSONDecodeError, TypeError):
                continue

            paper_title = result.get("title", str(req.question)[:200])

            # Extract citations from the report markdown [N] references
            report = result.get("report", "")
            # Look for References section at end of paper
            refs_section = ""
            for marker in ["## References", "## Sources", "**References**"]:
                idx = report.rfind(marker)
                if idx >= 0:
                    refs_section = report[idx:]
                    break

            # Parse reference lines: [N] Title — URL or [N] Title (URL)
            import re
            for match in re.finditer(r'\[(\d+)\]\s*(.+?)(?:\s*[—–-]\s*|\s*\()(https?://[^\s)]+)', refs_section):
                _num, title, url = match.groups()
                self._register(
                    url=url.rstrip(".),;"),
                    title=title.strip().rstrip("—–- "),
                    snippet="",
                    source_type="research",
                    period_name=None,  # Research papers span many periods
                    parent_type="research",
                    parent_id=str(req.id),
                    parent_title=paper_title,
                    reliability_tier=0,
                )
                count += 1

        self.stats["research"] = count
        logger.info(f"  Scanned research papers: {count} citations")

    def _scan_sites(self, session):
        """Scan UnifiedSite.raw_data['description_citations']."""
        sites = (
            session.query(UnifiedSite)
            .filter(UnifiedSite.raw_data.isnot(None))
            .yield_per(1000)
        )
        count = 0
        for site in sites:
            raw = site.raw_data or {}
            citations = raw.get("description_citations")
            if not citations:
                continue
            for cit in citations:
                url = cit.get("url", "")
                if url:
                    self._register(
                        url=url,
                        title=cit.get("title", _extract_domain(url)),
                        snippet=cit.get("claim", ""),
                        source_type="site",
                        period_name=site.period_name,
                        parent_type="site",
                        parent_id=str(site.id),
                        parent_title=site.name or "",
                    )
                    count += 1
        self.stats["sites"] = count
        logger.info(f"  Scanned site descriptions: {count} citations")

    def _scan_articles(self, session):
        """Scan active NewsArticles for web source URLs in markdown content."""
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.active.is_(True))
            .all()
        )
        count = 0
        import re
        for article in articles:
            if not article.content:
                continue
            # Extract markdown links: [text](url)
            for match in re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', article.content):
                title, url = match.groups()
                # Skip YouTube links (those are video refs, not web sources)
                if "youtube.com" in url or "youtu.be" in url:
                    continue
                self._register(
                    url=url,
                    title=title,
                    snippet="",
                    source_type="journal",
                    period_name=None,
                    parent_type="journal",
                    parent_id=str(article.id),
                    parent_title=article.title or "",
                )
                count += 1
        self.stats["articles"] = count
        logger.info(f"  Scanned articles: {count} citations")

    def _flush_to_db(self, session):
        """Upsert all pending records into library_sources."""
        if not self.pending:
            logger.info("  No citations to flush")
            return 0

        # Truncate and rewrite — simpler than merging with existing rows
        session.execute(text("DELETE FROM library_sources"))

        rows = list(self.pending.values())
        for row in rows:
            row["created_at"] = datetime.now(UTC)

        session.bulk_insert_mappings(LibrarySource, rows)
        session.flush()

        total = len(rows)
        logger.info(f"  Flushed {total} unique sources to library_sources")
        return total

    def aggregate_all(self) -> int:
        """Run full aggregation: scan all sources, write to DB. Returns source count."""
        logger.info("=" * 50)
        logger.info("LIBRARY AGGREGATOR — scanning citations")
        logger.info("=" * 50)

        with get_session() as session:
            self._scan_news_items(session)
            self._scan_research(session)
            self._scan_sites(session)
            self._scan_articles(session)
            total = self._flush_to_db(session)

        logger.info(f"Library aggregation complete: {total} unique sources")
        logger.info(f"  Breakdown: {self.stats}")
        return total


def aggregate_library() -> int:
    """Entry point for orchestrator. Returns count of sources."""
    agg = LibraryAggregator()
    return agg.aggregate_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    count = aggregate_library()
    print(f"\nDone. {count} sources in library.")
```

- [ ] **Step 2: Verify module loads**

```bash
cd /c/PythonProjects/AncientMap && python -c "from pipeline.library_aggregator import aggregate_library; print('Module loaded OK')"
```

Expected: `Module loaded OK`

- [ ] **Step 3: Commit**

```bash
git add pipeline/library_aggregator.py
git commit -m "feat(library): add citation aggregator pipeline"
```

---

## Task 3: Static Export

**Files:**
- Modify: `pipeline/static_exporter.py`

- [ ] **Step 1: Add `_export_library()` method to StaticExporter**

Add this method to the `StaticExporter` class, after the existing export methods (around line 570+). Also add the import at the top of the file:

At the top of `static_exporter.py`, add to imports:

```python
from pipeline.database import LibrarySource
```

Then add the method to the class:

```python
    def _export_library(self):
        """Export library sources organized by period."""
        logger.info("\nExporting library data...")

        lib_dir = self.output_dir / "library"
        lib_dir.mkdir(parents=True, exist_ok=True)
        periods_dir = lib_dir / "periods"
        periods_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            sources = session.query(LibrarySource).order_by(LibrarySource.citation_count.desc()).all()

            if not sources:
                logger.info("  No library sources to export")
                save_json(lib_dir / "index.json", [])
                save_json(lib_dir / "stats.json", {"total": 0})
                return

            # Group by period
            period_groups: dict[str, list[dict]] = {}
            type_counts: dict[str, int] = {}
            tier_counts: dict[int, int] = {}
            domain_counts: dict[str, int] = {}

            for src in sources:
                row = {
                    "id": src.id,
                    "url": src.url,
                    "title": src.title,
                    "domain": src.domain,
                    "snippet": src.snippet,
                    "reliability_tier": src.reliability_tier,
                    "citation_count": src.citation_count,
                    "source_types": src.source_types or [],
                    "parent_refs": src.parent_refs or [],
                }

                # Stats
                for st in (src.source_types or []):
                    type_counts[st] = type_counts.get(st, 0) + 1
                tier_counts[src.reliability_tier] = tier_counts.get(src.reliability_tier, 0) + 1
                if src.domain:
                    domain_counts[src.domain] = domain_counts.get(src.domain, 0) + 1

                periods = src.period_tags or []
                if not periods:
                    periods = ["Uncategorized"]
                for period in periods:
                    period_groups.setdefault(period, []).append(row)

            # Write period files
            index = []
            for period_name in sorted(period_groups.keys()):
                group = period_groups[period_name]
                slug = _slugify_period(period_name)

                period_data = {
                    "period": period_name,
                    "slug": slug,
                    "total": len(group),
                    "sources": group,  # already sorted by citation_count from query
                }
                save_json(periods_dir / f"{slug}.json", period_data)
                index.append({"period": period_name, "slug": slug, "count": len(group)})

            save_json(lib_dir / "index.json", index)

            # Stats
            top_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:20]
            stats = {
                "total_sources": len(sources),
                "by_type": type_counts,
                "by_tier": tier_counts,
                "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
                "period_count": len(index),
                "exported_at": datetime.now(UTC).isoformat(),
            }
            save_json(lib_dir / "stats.json", stats)

            self.stats["library_sources"] = len(sources)
            logger.info(f"  Library: {len(sources)} sources across {len(index)} periods")
```

You also need the `_slugify_period` helper. Add it as a module-level function near the other helpers (around line 70, before the class):

```python
def _slugify_period(period_name: str) -> str:
    """Convert period label to URL slug."""
    s = period_name.lower().strip()
    s = s.replace("<", "before").replace("+", "plus").replace(" - ", "-").replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")
```

- [ ] **Step 2: Call `_export_library()` from `export_all()`**

In the `export_all()` method, add a call to `_export_library()` inside the `if not sites_only:` block, after the existing exports:

```python
        # Export library sources by period
        self._export_library()
```

Add it right before `self._save_audit_snapshot()`.

- [ ] **Step 3: Verify export loads**

```bash
cd /c/PythonProjects/AncientMap && python -c "from pipeline.static_exporter import StaticExporter; print('Exporter loads OK')"
```

Expected: `Exporter loads OK`

- [ ] **Step 4: Commit**

```bash
git add pipeline/static_exporter.py
git commit -m "feat(library): add library export to static exporter"
```

---

## Task 4: API Search Endpoint

**Files:**
- Create: `api/routes/library.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create api/routes/library.py**

```python
"""Library API — search across aggregated citation sources."""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from pipeline.database import LibrarySource, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class LibrarySourceResponse(BaseModel):
    id: str
    url: str
    title: str
    domain: str | None = None
    snippet: str | None = None
    reliability_tier: int = 0
    citation_count: int = 1
    source_types: list[str] = []
    parent_refs: list[dict] = []


class LibrarySearchResponse(BaseModel):
    items: list[LibrarySourceResponse]
    total: int
    page: int
    page_size: int


@router.get("/search", response_model=LibrarySearchResponse)
def search_library(
    q: str | None = Query(None, description="Full-text search on title, snippet, domain"),
    period: str | None = Query(None, description="Filter by period tag"),
    type: str | None = Query(None, description="Filter by source type: story, journal, research, site"),
    tier: int | None = Query(None, description="Filter by reliability tier: 1=academic, 2=reputable, 3=general"),
    sort: str = Query("citations", description="Sort: citations, recent, title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Search across aggregated library sources."""
    query = db.query(LibrarySource)

    if q:
        # Simple ILIKE search across title, snippet, domain
        pattern = f"%{q}%"
        query = query.filter(
            (LibrarySource.title.ilike(pattern))
            | (LibrarySource.snippet.ilike(pattern))
            | (LibrarySource.domain.ilike(pattern))
        )

    if period:
        query = query.filter(LibrarySource.period_tags.any(period))

    if type:
        query = query.filter(LibrarySource.source_types.any(type))

    if tier is not None:
        query = query.filter(LibrarySource.reliability_tier == tier)

    # Count before pagination
    total = query.count()

    # Sort
    if sort == "recent":
        query = query.order_by(LibrarySource.last_seen.desc())
    elif sort == "title":
        query = query.order_by(LibrarySource.title.asc())
    else:  # citations (default)
        query = query.order_by(LibrarySource.citation_count.desc())

    # Paginate
    offset = (page - 1) * page_size
    sources = query.offset(offset).limit(page_size).all()

    items = [
        LibrarySourceResponse(
            id=s.id,
            url=s.url,
            title=s.title,
            domain=s.domain,
            snippet=s.snippet,
            reliability_tier=s.reliability_tier,
            citation_count=s.citation_count,
            source_types=s.source_types or [],
            parent_refs=s.parent_refs or [],
        )
        for s in sources
    ]

    return LibrarySearchResponse(items=items, total=total, page=page, page_size=page_size)
```

Add the refresh endpoint at the bottom of the same file:

```python
@router.post("/refresh")
def refresh_library():
    """Re-run the library aggregator. Admin-only (no auth gate for now)."""
    from pipeline.library_aggregator import aggregate_library

    count = aggregate_library()
    return {"status": "ok", "sources": count}
```

- [ ] **Step 2: Register router in api/main.py**

Add the import — in the `from api.routes import (` block (around line 39), add `library,` in alphabetical order (after `interactions,`):

```python
from api.routes import (
    articles_html,
    auth,
    content,
    contributions,
    interactions,
    library,
    lyra,
    ...
```

Add the include_router call — near the other router registrations (around line 617):

```python
app.include_router(library.router, prefix="/api/library", tags=["library"])
```

- [ ] **Step 3: Verify route loads**

```bash
cd /c/PythonProjects/AncientMap && python -c "from api.routes.library import router; print('Routes:', [r.path for r in router.routes])"
```

Expected: `Routes: ['/search']`

- [ ] **Step 4: Commit**

```bash
git add api/routes/library.py api/main.py
git commit -m "feat(library): add /api/library/search endpoint"
```

---

## Task 5: Frontend Types and Entry Points

**Files:**
- Create: `ancient-nerds-map/src/types/library.ts`
- Create: `ancient-nerds-map/library.html`
- Create: `ancient-nerds-map/src/libraryMain.tsx`
- Modify: `ancient-nerds-map/vite.config.ts`
- Modify: `ancient-nerds-map/src/components/layout/HamburgerNav.tsx`

- [ ] **Step 1: Create TypeScript interfaces**

Create `ancient-nerds-map/src/types/library.ts`:

```typescript
export interface LibrarySource {
  id: string
  url: string
  title: string
  domain: string | null
  snippet: string | null
  reliability_tier: number
  citation_count: number
  source_types: string[]
  parent_refs: ParentRef[]
}

export interface ParentRef {
  type: 'story' | 'journal' | 'research' | 'site'
  id: string
  title: string
}

export interface LibraryPeriod {
  period: string
  slug: string
  count: number
}

export interface LibraryPeriodData {
  period: string
  slug: string
  total: number
  sources: LibrarySource[]
}

export interface LibraryStats {
  total_sources: number
  by_type: Record<string, number>
  by_tier: Record<number, number>
  top_domains: { domain: string; count: number }[]
  period_count: number
}

export interface LibrarySearchResponse {
  items: LibrarySource[]
  total: number
  page: number
  page_size: number
}
```

- [ ] **Step 2: Create library.html**

Create `ancient-nerds-map/library.html`. Follow the same pattern as `news.html`:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />

    <title>Library - Sources & Citations | Ancient Nerds</title>
    <meta name="description" content="Browse the Ancient Nerds citation library. Thousands of academic papers, news sources, museum collections, and references organized by historical period." />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="https://ancientnerds.com/library.html" />

    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="icon" type="image/x-icon" href="/favicon.ico" />
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
    <meta name="theme-color" content="#0a1a1f" />

    <!-- Open Graph -->
    <meta property="og:type" content="website" />
    <meta property="og:url" content="https://ancientnerds.com/library.html" />
    <meta property="og:site_name" content="Ancient Nerds" />
    <meta property="og:title" content="Library - Sources & Citations | Ancient Nerds" />
    <meta property="og:description" content="Browse thousands of curated citations and references organized by historical period." />
    <meta property="og:image" content="https://ancientnerds.com/landing/og-image.png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />

    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500;600;700&family=Orbitron:wght@400;500;600;700;900&family=Inter:wght@300;400;500;600&family=Saira+Extra+Condensed:wght@400;700;800&display=swap" rel="stylesheet" />
  </head>
  <body>
    <noscript>
      <div style="padding: 40px 20px; max-width: 800px; margin: 0 auto; background: #0a1a1f; color: #e0e0e0; min-height: 100vh; font-family: sans-serif;">
        <h1 style="color: white;">Library - Ancient Nerds</h1>
        <p>Browse thousands of curated sources and citations from archaeology research, organized by historical period.</p>
      </div>
    </noscript>
    <div id="root"></div>
    <div class="crt-glow"></div>
    <script type="module" src="/src/libraryMain.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create libraryMain.tsx**

Create `ancient-nerds-map/src/libraryMain.tsx`:

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import { OfflineProvider } from './contexts/OfflineContext'
import LibraryPage from './pages/LibraryPage'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OfflineProvider>
      <LibraryPage />
    </OfflineProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 4: Add library entry to vite.config.ts**

In `ancient-nerds-map/vite.config.ts`, add to the `build.rollupOptions.input` object (around line 93, after the `research` entry):

```typescript
        library: resolve(__dirname, 'library.html'),
```

- [ ] **Step 5: Add Library to HamburgerNav**

In `ancient-nerds-map/src/components/layout/HamburgerNav.tsx`, add a new entry to `NAV_ITEMS` array. Insert it after the `articles` (Journal) entry and before the `lyra` entry:

```typescript
  { page: 'library', label: 'Library', href: '/library.html', icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' },
```

This is an open book SVG icon path.

- [ ] **Step 6: Commit**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map
git add src/types/library.ts library.html src/libraryMain.tsx vite.config.ts src/components/layout/HamburgerNav.tsx
git commit -m "feat(library): add frontend entry points, types, and navigation"
```

---

## Task 6: LibraryPage Component

**Files:**
- Create: `ancient-nerds-map/src/pages/LibraryPage.tsx`

- [ ] **Step 1: Create LibraryPage.tsx**

```typescript
import { useState, useEffect, useCallback, useRef } from 'react'
import { config } from '../config'
import PageHeader from '../components/layout/PageHeader'
import LibraryCard from '../components/library/LibraryCard'
import LibraryDetailCard from '../components/library/LibraryDetailCard'
import type { LibrarySource, LibraryPeriod, LibraryPeriodData, LibraryStats, LibrarySearchResponse } from '../types/library'
import '../styles/library.css'

const INITIAL_SHOW = 12

interface PeriodSection {
  meta: LibraryPeriod
  data: LibraryPeriodData | null
  loading: boolean
  expanded: boolean
}

export default function LibraryPage() {
  const [periods, setPeriods] = useState<PeriodSection[]>([])
  const [stats, setStats] = useState<LibraryStats | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<LibrarySource[] | null>(null)
  const [searchTotal, setSearchTotal] = useState(0)
  const [searchLoading, setSearchLoading] = useState(false)
  const [selectedSource, setSelectedSource] = useState<LibrarySource | null>(null)
  const sectionRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  // Load index + stats on mount
  useEffect(() => {
    fetch('/data/library/index.json')
      .then(r => r.ok ? r.json() : [])
      .then((index: LibraryPeriod[]) => {
        setPeriods(index.map(meta => ({ meta, data: null, loading: false, expanded: false })))
      })
      .catch(() => {})

    fetch('/data/library/stats.json')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setStats(data) })
      .catch(() => {})
  }, [])

  // Lazy-load period data when section scrolls into view
  useEffect(() => {
    const observers: IntersectionObserver[] = []

    periods.forEach((section, idx) => {
      const el = sectionRefs.current.get(section.meta.slug)
      if (!el || section.data || section.loading) return

      const observer = new IntersectionObserver(
        entries => {
          if (entries[0].isIntersecting) {
            observer.disconnect()
            setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, loading: true } : s))
            fetch(`/data/library/periods/${section.meta.slug}.json`)
              .then(r => r.ok ? r.json() : null)
              .then((data: LibraryPeriodData | null) => {
                setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, data, loading: false } : s))
              })
              .catch(() => {
                setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, loading: false } : s))
              })
          }
        },
        { rootMargin: '300px' }
      )
      observer.observe(el)
      observers.push(observer)
    })

    return () => observers.forEach(o => o.disconnect())
  }, [periods])

  // Search with debounce
  const handleSearch = useCallback((value: string) => {
    setSearchQuery(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)

    if (!value.trim()) {
      setSearchResults(null)
      return
    }

    searchTimer.current = setTimeout(async () => {
      setSearchLoading(true)
      try {
        const params = new URLSearchParams({ q: value, page_size: '50' })
        const resp = await fetch(`${config.api.baseUrl}/library/search?${params}`)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data: LibrarySearchResponse = await resp.json()
        setSearchResults(data.items)
        setSearchTotal(data.total)
      } catch {
        setSearchResults([])
        setSearchTotal(0)
      } finally {
        setSearchLoading(false)
      }
    }, 300)
  }, [])

  const clearSearch = () => {
    setSearchQuery('')
    setSearchResults(null)
  }

  const toggleExpand = (slug: string) => {
    setPeriods(prev => prev.map(s =>
      s.meta.slug === slug ? { ...s, expanded: !s.expanded } : s
    ))
  }

  const isSearchActive = searchResults !== null

  return (
    <div className="library-page">
      <PageHeader currentPage="library">
        <span className="page-header-title">Library</span>
      </PageHeader>

      <div className="library-content">
        {/* Search bar */}
        <div className="library-search-bar">
          <svg className="library-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            className="library-search-input"
            placeholder="Search sources..."
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
          />
          {searchQuery && (
            <button className="library-search-clear" onClick={clearSearch}>&times;</button>
          )}
        </div>

        {/* Stats bar */}
        {stats && !isSearchActive && (
          <div className="library-stats-bar">
            {stats.total_sources.toLocaleString()} sources across {stats.period_count} periods
          </div>
        )}

        {/* Search results mode */}
        {isSearchActive && (
          <div className="library-search-results">
            <div className="library-stats-bar">
              {searchLoading ? 'Searching...' : `${searchTotal.toLocaleString()} results for "${searchQuery}"`}
            </div>
            <div className="library-card-grid">
              {searchResults?.map(source => (
                <LibraryCard key={source.id} source={source} onClick={() => setSelectedSource(source)} />
              ))}
            </div>
            {!searchLoading && searchResults?.length === 0 && (
              <div className="library-empty">No sources found.</div>
            )}
          </div>
        )}

        {/* Browse mode — period sections */}
        {!isSearchActive && periods.map(section => (
          <div
            key={section.meta.slug}
            className="library-period-section"
            ref={el => { if (el) sectionRefs.current.set(section.meta.slug, el) }}
          >
            <div className="library-period-header">
              <h2 className="library-period-title">{section.meta.period}</h2>
              <span className="library-period-count">{section.meta.count} sources</span>
            </div>

            {section.loading && (
              <div className="library-loading">Loading...</div>
            )}

            {section.data && (
              <>
                <div className="library-card-grid">
                  {(section.expanded ? section.data.sources : section.data.sources.slice(0, INITIAL_SHOW))
                    .map(source => (
                      <LibraryCard key={source.id} source={source} onClick={() => setSelectedSource(source)} />
                    ))
                  }
                </div>
                {section.data.sources.length > INITIAL_SHOW && (
                  <button className="library-show-more" onClick={() => toggleExpand(section.meta.slug)}>
                    {section.expanded
                      ? 'Show less'
                      : `Show all ${section.data.sources.length} sources`
                    }
                  </button>
                )}
              </>
            )}
          </div>
        ))}

        {!isSearchActive && periods.length === 0 && (
          <div className="library-empty">No library data available yet. Run the pipeline to populate.</div>
        )}
      </div>

      {/* Detail overlay */}
      {selectedSource && (
        <LibraryDetailCard source={selectedSource} onClose={() => setSelectedSource(null)} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map && npx tsc --noEmit src/pages/LibraryPage.tsx 2>&1 | head -20
```

This may show errors for the not-yet-created components (LibraryCard, LibraryDetailCard). That's expected — they're created in Task 7.

- [ ] **Step 3: Commit**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map
git add src/pages/LibraryPage.tsx
git commit -m "feat(library): add LibraryPage component"
```

---

## Task 7: Library Card Components and Styles

**Files:**
- Create: `ancient-nerds-map/src/components/library/LibraryCard.tsx`
- Create: `ancient-nerds-map/src/components/library/LibraryDetailCard.tsx`
- Create: `ancient-nerds-map/src/styles/library.css`

- [ ] **Step 1: Create LibraryCard.tsx**

```typescript
import type { LibrarySource } from '../../types/library'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

interface LibraryCardProps {
  source: LibrarySource
  onClick: () => void
}

export default function LibraryCard({ source, onClick }: LibraryCardProps) {
  const tier = TIER_LABELS[source.reliability_tier]

  return (
    <button className="library-card" onClick={onClick} type="button">
      <div className="library-card-header">
        {source.domain && (
          <img
            className="library-card-favicon"
            src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=32`}
            alt=""
            width={16}
            height={16}
            loading="lazy"
          />
        )}
        <span className="library-card-domain">{source.domain || 'Unknown'}</span>
        {tier && <span className={`library-card-tier ${tier.className}`}>{tier.label}</span>}
      </div>
      <div className="library-card-title">{source.title}</div>
      <div className="library-card-footer">
        <span className="library-card-citations">Cited {source.citation_count}x</span>
        <div className="library-card-types">
          {source.source_types.slice(0, 2).map(t => (
            <span key={t} className="library-card-type-pill">{t}</span>
          ))}
          {source.source_types.length > 2 && (
            <span className="library-card-type-pill">+{source.source_types.length - 2}</span>
          )}
        </div>
      </div>
    </button>
  )
}
```

- [ ] **Step 2: Create LibraryDetailCard.tsx**

```typescript
import { useEffect } from 'react'
import type { LibrarySource, ParentRef } from '../../types/library'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

const PARENT_LINKS: Record<string, { label: string; href: (id: string) => string }> = {
  story: { label: 'Story', href: () => '/news.html' },
  journal: { label: 'Journal', href: () => '/articles.html' },
  research: { label: 'Research', href: (id) => `/research.html?id=${id}` },
  site: { label: 'Site', href: (id) => `/site.html?id=${id}` },
}

interface LibraryDetailCardProps {
  source: LibrarySource
  onClose: () => void
}

export default function LibraryDetailCard({ source, onClose }: LibraryDetailCardProps) {
  const tier = TIER_LABELS[source.reliability_tier]

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="library-detail-backdrop" onClick={onClose}>
      <div className="library-detail-card" onClick={e => e.stopPropagation()}>
        <button className="library-detail-close" onClick={onClose}>&times;</button>

        <div className="library-detail-header">
          {source.domain && (
            <img
              className="library-detail-favicon"
              src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=64`}
              alt=""
              width={24}
              height={24}
            />
          )}
          <div>
            <h3 className="library-detail-title">{source.title}</h3>
            <span className="library-detail-domain">{source.domain}</span>
            {tier && <span className={`library-card-tier ${tier.className}`}>{tier.label}</span>}
          </div>
        </div>

        {source.snippet && (
          <p className="library-detail-snippet">{source.snippet}</p>
        )}

        {source.parent_refs.length > 0 && (
          <div className="library-detail-cited-in">
            <h4>Cited in</h4>
            <ul className="library-detail-refs">
              {source.parent_refs.map((ref: ParentRef, i: number) => {
                const link = PARENT_LINKS[ref.type]
                return (
                  <li key={`${ref.type}-${ref.id}-${i}`}>
                    <span className="library-card-type-pill">{link?.label || ref.type}</span>
                    {link ? (
                      <a href={link.href(ref.id)}>{ref.title}</a>
                    ) : (
                      <span>{ref.title}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        <a
          className="library-detail-visit"
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Visit source &rarr;
        </a>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create library.css**

Create `ancient-nerds-map/src/styles/library.css`:

```css
/* ===== Library Page ===== */

.library-page {
  min-height: 100vh;
  background: var(--bg-primary, #0a1a1f);
  color: var(--text-primary, #e0e0e0);
}

.library-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 24px 60px;
}

/* Search bar */
.library-search-bar {
  position: relative;
  margin-bottom: 16px;
}

.library-search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-dimmed, #888);
  pointer-events: none;
}

.library-search-input {
  width: 100%;
  padding: 10px 36px 10px 38px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--text-primary, #e0e0e0);
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
}

.library-search-input:focus {
  border-color: var(--primary-red, #c02023);
}

.library-search-input::placeholder {
  color: var(--text-dimmed, #666);
}

.library-search-clear {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-dimmed, #888);
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
}

/* Stats bar */
.library-stats-bar {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-dimmed, #888);
  margin-bottom: 24px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Card grid */
.library-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

/* Period sections */
.library-period-section {
  margin-bottom: 32px;
}

.library-period-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 8px;
}

.library-period-title {
  font-family: 'Orbitron', sans-serif;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.library-period-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-dimmed, #666);
}

.library-show-more {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-dimmed, #888);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 8px;
}

.library-show-more:hover {
  border-color: var(--primary-red, #c02023);
  color: var(--text-primary, #e0e0e0);
}

/* Individual card */
.library-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  font-family: inherit;
  color: inherit;
}

.library-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
}

.library-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.library-card-favicon {
  border-radius: 2px;
  flex-shrink: 0;
}

.library-card-domain {
  color: var(--text-dimmed, #888);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.library-card-title {
  font-size: 13px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.library-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
}

.library-card-citations {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--text-dimmed, #888);
}

.library-card-types {
  display: flex;
  gap: 4px;
}

.library-card-type-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-dimmed, #888);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/* Tier badges */
.library-card-tier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  flex-shrink: 0;
}

.library-tier-academic {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.library-tier-reputable {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.library-tier-general {
  background: rgba(255, 255, 255, 0.06);
  color: #888;
}

/* Detail overlay */
.library-detail-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.library-detail-card {
  background: var(--bg-primary, #0a1a1f);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 24px;
  max-width: 560px;
  width: 100%;
  max-height: 80vh;
  overflow-y: auto;
  position: relative;
}

.library-detail-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  color: var(--text-dimmed, #888);
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.library-detail-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.library-detail-favicon {
  border-radius: 3px;
  margin-top: 2px;
  flex-shrink: 0;
}

.library-detail-title {
  font-size: 16px;
  margin: 0 0 4px;
  line-height: 1.3;
}

.library-detail-domain {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-dimmed, #888);
  margin-right: 8px;
}

.library-detail-snippet {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-dimmed, #aaa);
  margin: 0 0 20px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
  border-left: 2px solid rgba(255, 255, 255, 0.1);
}

.library-detail-cited-in {
  margin-bottom: 20px;
}

.library-detail-cited-in h4 {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dimmed, #888);
  margin: 0 0 8px;
}

.library-detail-refs {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.library-detail-refs li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.library-detail-refs a {
  color: var(--text-primary, #e0e0e0);
  text-decoration: none;
}

.library-detail-refs a:hover {
  color: var(--primary-red, #c02023);
}

.library-detail-visit {
  display: inline-block;
  padding: 8px 20px;
  background: var(--primary-red, #c02023);
  color: white;
  border-radius: 4px;
  text-decoration: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.library-detail-visit:hover {
  opacity: 0.9;
}

/* Loading & empty states */
.library-loading,
.library-empty {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-dimmed, #666);
  padding: 24px 0;
  text-align: center;
}

/* Mobile */
@media (max-width: 600px) {
  .library-content {
    padding: 12px 12px 40px;
  }
  .library-card-grid {
    grid-template-columns: 1fr;
  }
  .library-detail-card {
    max-height: 90vh;
  }
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map && npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors (or only pre-existing ones unrelated to library files).

- [ ] **Step 5: Commit**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map
git add src/components/library/LibraryCard.tsx src/components/library/LibraryDetailCard.tsx src/styles/library.css
git commit -m "feat(library): add card components and styles"
```

---

## Task 8: Orchestrator Integration

**Files:**
- Modify: `pipeline/lyra/orchestrator.py`

- [ ] **Step 1: Add library step to STEPS dict**

In `pipeline/lyra/orchestrator.py`, add to the `STEPS` dict (around line 49):

```python
    "library": (
        "pipeline.library_aggregator",
        "aggregate_library",
        False,
        "Aggregated {n} library sources",
    ),
```

- [ ] **Step 2: Add to STEP_ORDER**

Add `"library"` at the end of the `STEP_ORDER` list (after `"identify"`):

```python
STEP_ORDER = [
    "fetch",
    "retry",
    "summarize",
    "match",
    "posts",
    "verify",
    "rescore",
    "dedup",
    "screenshots",
    "backfill",
    "identify",
    "library",
]
```

- [ ] **Step 3: Add to STEP_GROUPS**

Add `"library"` to the `"news"` group in `STEP_GROUPS`, since it depends on news data:

```python
    "news": [
        "fetch",
        "retry",
        "summarize",
        "match",
        "posts",
        "verify",
        "rescore",
        "dedup",
        "screenshots",
        "backfill",
        "library",
    ],
```

- [ ] **Step 4: Set interval (run daily, not every cycle)**

Add to `STEP_INTERVALS`:

```python
STEP_INTERVALS: dict[str, int] = {
    "backfill": 24,
    "library": 24,  # Run every 24 cycles (daily)
}
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/orchestrator.py
git commit -m "feat(library): integrate aggregator into Lyra pipeline"
```

---

## Task 9: End-to-End Verification

- [ ] **Step 1: Run aggregator standalone**

```bash
cd /c/PythonProjects/AncientMap && python -m pipeline.library_aggregator
```

Expected: Log output showing scan of 4 source types and flush to DB. The count depends on existing data.

- [ ] **Step 2: Run static export**

```bash
cd /c/PythonProjects/AncientMap && python -c "
from pipeline.static_exporter import StaticExporter
e = StaticExporter()
e._export_library()
"
```

Expected: Files created in `public/data/library/` — check `index.json`, `stats.json`, and at least one period file.

- [ ] **Step 3: Verify exported files**

```bash
ls /c/PythonProjects/AncientMap/public/data/library/
cat /c/PythonProjects/AncientMap/public/data/library/stats.json | python -m json.tool | head -15
```

Expected: `index.json`, `stats.json`, `periods/` directory with period JSON files.

- [ ] **Step 4: Start dev server and test in browser**

```bash
cd /c/PythonProjects/AncientMap/ancient-nerds-map && npm run dev
```

Open `http://localhost:5173/library.html` in a browser. Verify:
- Page loads with header and "Library" title
- Period sections render with source counts
- Cards load as sections scroll into view
- Clicking a card shows the detail overlay
- Search bar returns results from the API
- "Visit source" link opens external URL

- [ ] **Step 5: Verify API search works**

```bash
curl "http://localhost:8000/api/library/search?q=test&page_size=5" | python -m json.tool | head -20
```

Expected: JSON response with `items`, `total`, `page`, `page_size` fields.

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add -A && git status
```

Only commit if there are fixes. If everything passed clean, skip this step.
