"""Library API — search across aggregated citation sources."""

import hmac
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.background_jobs import JobAlreadyRunning, read_status, start_job
from api.services.lyra_tools import _escape_ilike
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import LibrarySource, NewsItem, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# /refresh re-runs the aggregator + static export (expensive); throttle hard.
_refresh_limiter = RateLimiter(max_requests=2, window_seconds=600, namespace="library_refresh")


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
    source_type: str | None = Query(
        None, alias="type", description="Filter by source type: story, journal, research, site"
    ),
    tier: int | None = Query(
        None, description="Filter by reliability tier: 1=academic, 2=reputable, 3=general"
    ),
    sort: str = Query("citations", description="Sort: citations, recent, title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Search across aggregated library sources."""
    query = db.query(LibrarySource)

    if q:
        pattern = f"%{_escape_ilike(q)}%"
        query = query.filter(
            (LibrarySource.title.ilike(pattern, escape="\\"))
            | (LibrarySource.snippet.ilike(pattern, escape="\\"))
            | (LibrarySource.domain.ilike(pattern, escape="\\"))
        )

    if period:
        query = query.filter(LibrarySource.period_tags.any(period))

    if source_type:
        query = query.filter(LibrarySource.source_types.any(source_type))

    if tier is not None:
        query = query.filter(LibrarySource.reliability_tier == tier)

    total = query.count()

    if sort == "recent":
        query = query.order_by(LibrarySource.last_seen.desc())
    elif sort == "title":
        query = query.order_by(LibrarySource.title.asc())
    else:
        query = query.order_by(LibrarySource.citation_count.desc())

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


@router.get("/by-site/{site_id}", response_model=list[LibrarySourceResponse])
def library_by_site(site_id: str, db: Session = Depends(get_db)):
    """Get all library sources linked to a specific site.

    Finds sources via two paths:
    1. Direct site citations (parent_refs with type='site' and id=site_id)
    2. Story citations (parent_refs with type='story' and id matching news items for this site)
    """
    try:
        uuid.UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid site ID format") from None

    # 1. Get news item IDs for this site
    news_ids = [
        str(row[0]) for row in db.query(NewsItem.id).filter(NewsItem.site_id == site_id).all()
    ]

    # 2. Build JSONB containment queries
    #    @> checks if the JSONB array contains an element matching the pattern
    conditions = [
        LibrarySource.parent_refs.op("@>")(json.dumps([{"type": "site", "id": site_id}])),
    ]
    # Add story ref conditions in batches (avoid huge OR chains)
    for nid in news_ids:
        conditions.append(
            LibrarySource.parent_refs.op("@>")(json.dumps([{"type": "story", "id": nid}]))
        )

    from sqlalchemy import or_

    if not conditions:
        return []

    sources = (
        db.query(LibrarySource)
        .filter(or_(*conditions))
        .order_by(LibrarySource.citation_count.desc())
        .limit(100)
        .all()
    )

    return [
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


#: Background-job name of the library refresh (api/services/background_jobs.py).
LIBRARY_REFRESH_JOB = "library-refresh"


def _require_internal_key(req: Request) -> None:
    """X-Internal-Key must match LIBRARY_REFRESH_KEY (audit 2026-08-05, M2).

    The deploy pipeline reads the key from the VPS .env; fails closed with 503 when
    unconfigured.
    """
    expected = os.getenv("LIBRARY_REFRESH_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="LIBRARY_REFRESH_KEY not configured")
    provided = req.headers.get("X-Internal-Key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid internal key")


def _refresh_library_job() -> dict:
    """The job body: aggregate the citations, then write public/data/library/."""
    from pipeline.library_aggregator import aggregate_library
    from pipeline.static_exporter import StaticExporter

    count = aggregate_library()
    StaticExporter()._export_library()
    return {"sources": count}


@router.post("/refresh", status_code=202)
def refresh_library(req: Request):
    """Start a re-run of the library aggregator and the library export (internal).

    Answers 202 at once; the work runs as a background job. The deploy curls this
    with --max-time 120, and the synchronous version took longer than that (the site
    scan alone spent 112 s materialising 1.74M rows, 2026-09-22), so a working
    refresh was reported as failed. GET /refresh/status reports the run.
    """
    _require_internal_key(req)
    if not _refresh_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests")

    try:
        return start_job(LIBRARY_REFRESH_JOB, _refresh_library_job)
    except JobAlreadyRunning:
        raise HTTPException(
            status_code=409, detail="A library refresh is already running"
        ) from None


@router.get("/refresh/status")
def refresh_library_status(req: Request, db: Session = Depends(get_db)):
    """State of the last library refresh: running, ok, error, interrupted or never_run."""
    _require_internal_key(req)
    return read_status(db, LIBRARY_REFRESH_JOB)
