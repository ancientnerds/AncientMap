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

from pipeline.database import (
    LibrarySource,
    NewsArticle,
    NewsItem,
    ResearchRequest,
    UnifiedSite,
    get_session,
)
from pipeline.utils.text import PERIOD_BUCKETS

logger = logging.getLogger(__name__)

# Only accept known period bucket labels — everything else becomes Uncategorized
_VALID_PERIODS = {label for label, _, _ in PERIOD_BUCKETS}

# Skip these domains — they're video refs, not library sources
_SKIP_DOMAINS = {"youtube.com", "youtu.be", "m.youtube.com"}


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

        # Skip video URLs — not library material
        domain = _extract_domain(url)
        if domain in _SKIP_DOMAINS:
            return

        # Only accept known period bucket labels
        if period_name and period_name not in _VALID_PERIODS:
            period_name = None

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
        # Pre-load site periods to avoid N+1 queries
        site_periods = dict(
            session.query(UnifiedSite.id, UnifiedSite.period_name)
            .filter(UnifiedSite.period_name.isnot(None))
            .all()
        )

        items = session.query(NewsItem).filter(NewsItem.web_sources.isnot(None)).yield_per(500)
        count = 0
        for item in items:
            if not item.web_sources:
                continue
            period = site_periods.get(item.site_id) if item.site_id else None
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
                    reliability_tier=0,
                )
                count += 1

        self.stats["research"] = count
        logger.info(f"  Scanned research papers: {count} citations")

    def _scan_sites(self, session):
        """Scan UnifiedSite.raw_data['description_citations']."""
        sites = session.query(UnifiedSite).filter(UnifiedSite.raw_data.isnot(None)).yield_per(1000)
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
            stmt = pg_insert(LibrarySource).values(**row)
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
