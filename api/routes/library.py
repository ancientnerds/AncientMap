"""Library API — search across aggregated citation sources."""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
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
    source_type: str | None = Query(None, alias="type", description="Filter by source type: story, journal, research, site"),
    tier: int | None = Query(None, description="Filter by reliability tier: 1=academic, 2=reputable, 3=general"),
    sort: str = Query("citations", description="Sort: citations, recent, title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Search across aggregated library sources."""
    query = db.query(LibrarySource)

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (LibrarySource.title.ilike(pattern))
            | (LibrarySource.snippet.ilike(pattern))
            | (LibrarySource.domain.ilike(pattern))
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
