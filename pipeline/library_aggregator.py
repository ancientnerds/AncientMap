"""
Library Aggregator — scans citations from Stories, Journals, Research, and Sites,
then upserts into the library_sources table for the Library page.

Run standalone:  python -m pipeline.library_aggregator
Triggered by:    Lyra orchestrator after pipeline cycle
"""

import hashlib
import json
import logging
import re
import urllib.parse
from datetime import UTC, datetime

from sqlalchemy import text

from pipeline.database import (
    LibrarySource,
    NewsArticle,
    NewsItem,
    ResearchRequest,
    UnifiedSite,
    get_session,
)
from pipeline.news_visibility import public_story_criteria
from pipeline.sites_html_renderer import site_path
from pipeline.utils.public_sites import RETIRED, is_retired
from pipeline.utils.slugs import slugify, story_slug
from pipeline.utils.text import PERIOD_BUCKETS

logger = logging.getLogger(__name__)

# Only accept known period bucket labels — everything else becomes Uncategorized
_VALID_PERIODS = {label for label, _, _ in PERIOD_BUCKETS}

# Skip these domains — they're video refs, not library sources
_SKIP_DOMAINS = {"youtube.com", "youtu.be", "m.youtube.com"}

# Rows per multi-row upsert in _flush_to_db (14,241 library sources on 2026-09-22).
_FLUSH_CHUNK = 500

# Drops the parent refs that point at a retired site (E4) from stored rows. The scan
# skips retired sites, and the upsert replaces parent_refs only for the sources it saw
# this run - a source cited by nothing but a now-retired site would keep linking a page
# that answers 410. The row itself stays (the aggregator never deletes).
_STRIP_RETIRED_REFS = text(
    "WITH retired AS (SELECT id::text AS id FROM unified_sites WHERE "
    + is_retired()
    + """)
    UPDATE library_sources ls
    SET parent_refs = (
        SELECT COALESCE(jsonb_agg(e.ref ORDER BY e.ord), '[]'::jsonb)
        FROM jsonb_array_elements(ls.parent_refs) WITH ORDINALITY AS e(ref, ord)
        WHERE NOT (e.ref->>'type' = 'site' AND e.ref->>'id' IN (SELECT id FROM retired))
    )
    WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements(ls.parent_refs) AS r(ref)
        WHERE r.ref->>'type' = 'site' AND r.ref->>'id' IN (SELECT id FROM retired)
    )
    """
)


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
        parent_path: str | None,
        reliability_tier: int = 0,
    ):
        """Register a citation. Merges if URL already seen.

        parent_path is the canonical page of the citing item (None when it
        has none, e.g. a withdrawn story) — the library cards link it. Until
        2026-09-15 the frontend built /site.html?id= and /research.html?id=
        from the bare id, i.e. redirecting legacy URLs on a crawlable page.
        """
        url = url.strip()
        if not url or not title:
            return

        # Skip video URLs — not library material
        domain = _extract_domain(url)
        if domain in _SKIP_DOMAINS:
            return

        # Only accept known period bucket labels
        if period_name and period_name not in _VALID_PERIODS:
            period_name = None

        uid = _url_id(url)
        now = datetime.now(UTC)

        parent_ref = {
            "type": parent_type,
            "id": parent_id,
            "title": parent_title[:200],
            "path": parent_path,
        }

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
        # Pre-load site periods to avoid N+1 queries
        site_periods = dict(
            session.query(UnifiedSite.id, UnifiedSite.period_name)
            .filter(UnifiedSite.period_name.isnot(None))
            .all()
        )

        public_ids = {
            item_id for (item_id,) in session.query(NewsItem.id).filter(*public_story_criteria())
        }
        items = session.query(NewsItem).filter(NewsItem.web_sources.isnot(None)).yield_per(500)
        count = 0
        for item in items:
            if not item.web_sources:
                continue
            period = site_periods.get(item.site_id) if item.site_id else None
            story_path = (
                f"/news-archive/{story_slug(item.headline, item.id)}"
                if item.id in public_ids
                else None
            )
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
                        parent_path=story_path,
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
                result = (
                    json.loads(req.result_json)
                    if isinstance(req.result_json, str)
                    else req.result_json
                )
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
            for match in re.finditer(
                r"\[(\d+)\]\s*(.+?)(?:\s*[—–-]\s*|\s*\()(https?://[^\s)]+)", refs_section
            ):
                _num, title, url = match.groups()
                self._register(
                    url=url.rstrip(".),;"),
                    title=title.strip().rstrip("—–- "),
                    snippet="",
                    source_type="research",
                    period_name=None,
                    parent_type="research",
                    parent_id=str(req.id),
                    parent_title=paper_title,
                    parent_path=f"/research/{req.slug}" if req.slug else None,
                    reliability_tier=0,
                )
                count += 1

        self.stats["research"] = count
        logger.info(f"  Scanned research papers: {count} citations")

    def _scan_sites(self, session):
        """Scan UnifiedSite.raw_data['description_citations'] of the shown sites.

        The filter runs in SQL and only the citations leave the database. The old
        version loaded every row with any raw_data as a full ORM object - 1,736,055 of
        1,759,676 rows, raw JSON included - to find the 2,217 that carry citations:
        112 s for 3,009 citations on 2026-09-22, against 0.65 s for this query
        (EXPLAIN ANALYZE on production, read-only). Retired sites (E4) are left out:
        their page answers 410, so the library must not link it.
        """
        sites = (
            session.query(
                UnifiedSite.id,
                UnifiedSite.name,
                UnifiedSite.country,
                UnifiedSite.source_id,
                UnifiedSite.period_name,
                UnifiedSite.raw_data["description_citations"].label("citations"),
            )
            .filter(
                UnifiedSite.raw_data.has_key("description_citations"),
                UnifiedSite.scope_status.is_distinct_from(RETIRED),
            )
            .all()
        )
        count = 0
        for site in sites:
            citations = site.citations
            if not citations:
                continue
            page_path = (
                site_path(site.country, site.name, str(site.id))
                if site.source_id == "ancient_nerds" and site.country
                else f"/globe.html#focus={site.id}"
            )
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
                        parent_path=page_path,
                    )
                    count += 1
        self.stats["sites"] = count
        logger.info(f"  Scanned site descriptions: {count} citations")

    def _scan_articles(self, session):
        """Scan active NewsArticles for web source URLs in markdown content."""
        articles = session.query(NewsArticle).filter(NewsArticle.active.is_(True)).all()
        count = 0
        for article in articles:
            if not article.content:
                continue
            # Extract markdown links: [text](url)
            for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", article.content):
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
                    parent_path=f"/articles/{slugify(article.title)}" if article.title else None,
                )
                count += 1
        self.stats["articles"] = count
        logger.info(f"  Scanned articles: {count} citations")

    def _flush_to_db(self, session):
        """Upsert all pending records into library_sources. Never deletes existing rows."""
        if not self.pending:
            logger.info("  No citations to flush")
            return 0

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        rows = list(self.pending.values())
        now = datetime.now(UTC)
        for row in rows:
            row["created_at"] = now

        # One multi-row upsert per chunk instead of one statement per source (14,241
        # round trips per refresh on 2026-09-22). `pending` is keyed by id, so no chunk
        # holds the same id twice - ON CONFLICT DO UPDATE refuses that.
        for start in range(0, len(rows), _FLUSH_CHUNK):
            stmt = pg_insert(LibrarySource).values(rows[start : start + _FLUSH_CHUNK])
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "title": stmt.excluded.title,
                    "snippet": stmt.excluded.snippet,
                    "reliability_tier": stmt.excluded.reliability_tier,
                    "period_tags": stmt.excluded.period_tags,
                    "source_types": stmt.excluded.source_types,
                    "last_seen": stmt.excluded.last_seen,
                    "citation_count": stmt.excluded.citation_count,
                    "parent_refs": stmt.excluded.parent_refs,
                },
            )
            session.execute(stmt)

        session.flush()

        # Count total rows in table (includes old ones we didn't touch)
        total = session.query(LibrarySource).count()
        new_this_run = len(rows)
        logger.info(f"  Upserted {new_this_run} sources ({total} total in library)")
        return total

    def _strip_retired_refs(self, session) -> int:
        """Drop parent refs to retired sites from the stored rows; returns rows changed."""
        stripped = session.execute(_STRIP_RETIRED_REFS).rowcount
        if stripped:
            logger.info(f"  Dropped retired-site refs from {stripped} stored sources")
        return stripped

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
            self._strip_retired_refs(session)

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
