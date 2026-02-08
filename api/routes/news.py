"""
News Feed API Routes.

Serves Lyra pipeline news items, channels, articles, and stats.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, text
from sqlalchemy.orm import Session, joinedload

from api.cache import cache_get, cache_set
from pipeline.database import NewsArticle, NewsChannel, NewsItem, NewsVideo, UnifiedSite, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Period Bucketing (mirrors frontend categorizePeriod in src/data/sites.ts)
# =============================================================================

_PERIOD_BUCKETS = [
    ("< 4500 BC", -999999, -4500),
    ("4500 - 3000 BC", -4500, -3000),
    ("3000 - 1500 BC", -3000, -1500),
    ("1500 - 500 BC", -1500, -500),
    ("500 BC - 1 AD", -500, 1),
    ("1 - 500 AD", 1, 500),
    ("500 - 1000 AD", 500, 1000),
    ("1000 - 1500 AD", 1000, 1500),
    ("1500+ AD", 1500, 999999),
]
_PERIOD_ORDER = {label: i for i, (label, _, _) in enumerate(_PERIOD_BUCKETS)}


def _categorize_period(start: int | None) -> str:
    if start is None:
        return "Unknown"
    for label, lo, hi in _PERIOD_BUCKETS:
        if lo <= start < hi:
            return label
    return "Unknown"


def _period_label_to_range(label: str) -> tuple[int, int] | None:
    for bucket_label, lo, hi in _PERIOD_BUCKETS:
        if bucket_label == label:
            return (lo, hi)
    return None


# =============================================================================
# Response Models
# =============================================================================


class NewsChannelResponse(BaseModel):
    id: str
    name: str


class NewsVideoInfo(BaseModel):
    id: str
    title: str
    channel_name: str
    channel_id: str
    published_at: str
    thumbnail_url: str | None = None
    duration_minutes: float | None = None


class NewsItemResponse(BaseModel):
    id: int
    headline: str
    summary: str
    post_text: str | None = None
    facts: list[str] | None = None
    timestamp_range: str | None = None
    timestamp_seconds: int | None = None
    screenshot_url: str | None = None
    youtube_url: str | None = None
    youtube_deep_url: str | None = None
    video: NewsVideoInfo
    created_at: str
    site_id: str | None = None
    site_name: str | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    site_type: str | None = None
    site_period_name: str | None = None
    site_period_start: int | None = None
    site_country: str | None = None
    site_name_extracted: str | None = None
    significance: int | None = None
    news_category: str | None = None


class NewsFeedResponse(BaseModel):
    items: list[NewsItemResponse]
    total_count: int
    page: int
    has_more: bool


class NewsArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    summary: str | None = None
    week_start: str
    week_end: str
    published_at: str | None = None


class NewsStatsResponse(BaseModel):
    total_items: int
    total_videos: int
    total_channels: int
    total_articles: int
    total_duration_hours: float = 0
    latest_item_date: str | None = None


class LyraStatusResponse(BaseModel):
    status: str  # "online", "offline", "error"
    last_heartbeat: str | None = None
    last_cycle_ok: bool = False


class NewsFilterSiteOption(BaseModel):
    id: str
    name: str


class NewsFiltersResponse(BaseModel):
    channels: list[NewsChannelResponse]
    sites: list[NewsFilterSiteOption]
    categories: list[str]
    periods: list[str]
    countries: list[str]
    news_categories: list[str] = []


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/feed", response_model=NewsFeedResponse)
async def get_news_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: str | None = None,
    site_id: str | None = None,
    category: str | None = None,
    period: str | None = None,
    country: str | None = None,
    min_significance: int | None = Query(None, ge=1, le=10),
    news_category: str | None = None,
    sort: str | None = None,
    db: Session = Depends(get_db),
):
    """Get paginated news feed items, newest first."""
    cache_key = f"news:feed:{page}:{page_size}:{channel_id or 'all'}:{site_id or 'all'}:{category or 'all'}:{period or 'all'}:{country or 'all'}:{min_significance or 'all'}:{news_category or 'all'}:{sort or 'default'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    query = db.query(NewsItem).join(NewsVideo).options(
        joinedload(NewsItem.video).joinedload(NewsVideo.channel),
        joinedload(NewsItem.site),
    ).filter(NewsItem.post_text.isnot(None))

    if channel_id:
        query = query.filter(NewsVideo.channel_id == channel_id)

    # Site/category/period/country filters require UnifiedSite join
    site_joined = False

    if site_id:
        query = query.filter(NewsItem.site_id == site_id)

    if category:
        if not site_joined:
            query = query.join(UnifiedSite, NewsItem.site_id == UnifiedSite.id)
            site_joined = True
        query = query.filter(UnifiedSite.site_type == category)

    if country:
        if not site_joined:
            query = query.join(UnifiedSite, NewsItem.site_id == UnifiedSite.id)
            site_joined = True
        query = query.filter(UnifiedSite.country == country)

    if period:
        period_range = _period_label_to_range(period)
        if period_range:
            if not site_joined:
                query = query.join(UnifiedSite, NewsItem.site_id == UnifiedSite.id)
                site_joined = True
            lo, hi = period_range
            query = query.filter(UnifiedSite.period_start >= lo, UnifiedSite.period_start < hi)

    if min_significance:
        query = query.filter(NewsItem.significance >= min_significance)

    if news_category:
        query = query.filter(NewsItem.news_category == news_category)

    total_count = query.count()
    offset = (page - 1) * page_size

    if sort == "significance":
        items = query.order_by(NewsItem.significance.desc().nullslast(), NewsVideo.published_at.desc(), NewsItem.created_at.desc()).offset(offset).limit(page_size).all()
    else:
        items = query.order_by(NewsVideo.published_at.desc(), NewsItem.created_at.desc()).offset(offset).limit(page_size).all()

    result_items = []
    for item in items:
        video = item.video
        channel = video.channel if video else None
        site = item.site

        youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else None
        youtube_deep_url = None
        if video and item.timestamp_seconds:
            youtube_deep_url = f"https://www.youtube.com/watch?v={video.id}&t={item.timestamp_seconds}s"

        result_items.append(NewsItemResponse(
            id=item.id,
            headline=item.headline,
            summary=item.summary,
            post_text=item.post_text,
            facts=item.facts,
            timestamp_range=item.timestamp_range,
            timestamp_seconds=item.timestamp_seconds,
            screenshot_url=item.screenshot_url,
            youtube_url=youtube_url,
            youtube_deep_url=youtube_deep_url,
            video=NewsVideoInfo(
                id=video.id,
                title=video.title,
                channel_name=channel.name if channel else "Unknown",
                channel_id=video.channel_id,
                published_at=video.published_at.isoformat() if video.published_at else "",
                thumbnail_url=video.thumbnail_url,
                duration_minutes=video.duration_minutes,
            ),
            created_at=item.created_at.isoformat() if item.created_at else "",
            site_id=str(site.id) if site else None,
            site_name=site.name if site else None,
            site_lat=site.lat if site else None,
            site_lon=site.lon if site else None,
            site_type=site.site_type if site else None,
            site_period_name=site.period_name if site else None,
            site_period_start=site.period_start if site else None,
            site_country=site.country if site else None,
            site_name_extracted=item.site_name_extracted if not site else None,
            significance=item.significance,
            news_category=item.news_category,
        ))

    response = NewsFeedResponse(
        items=result_items,
        total_count=total_count,
        page=page,
        has_more=(offset + page_size) < total_count,
    )

    cache_set(cache_key, response.model_dump(), ttl=300)  # 5 min cache
    return response


@router.get("/filters", response_model=NewsFiltersResponse)
async def get_news_filters(db: Session = Depends(get_db)):
    """Get available filter options based on existing news data."""
    cache_key = "news:filters"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Channels: distinct enabled channels that have news items with post_text
    channel_ids_q = (
        db.query(NewsVideo.channel_id)
        .join(NewsItem, NewsItem.video_id == NewsVideo.id)
        .filter(NewsItem.post_text.isnot(None))
        .distinct()
    )
    channel_ids = [row[0] for row in channel_ids_q.all()]
    channels_list = (
        db.query(NewsChannel)
        .filter(NewsChannel.enabled.is_(True), NewsChannel.id.in_(channel_ids))
        .order_by(NewsChannel.name)
        .all()
    )
    channels = [NewsChannelResponse(id=ch.id, name=ch.name) for ch in channels_list]

    # Sites: distinct sites linked from news items
    site_rows = (
        db.query(UnifiedSite.id, UnifiedSite.name)
        .join(NewsItem, NewsItem.site_id == UnifiedSite.id)
        .filter(NewsItem.post_text.isnot(None))
        .distinct()
        .order_by(UnifiedSite.name)
        .all()
    )
    sites = [NewsFilterSiteOption(id=str(row[0]), name=row[1]) for row in site_rows]

    # Categories: distinct site_type values
    cat_rows = (
        db.query(UnifiedSite.site_type)
        .join(NewsItem, NewsItem.site_id == UnifiedSite.id)
        .filter(NewsItem.post_text.isnot(None), UnifiedSite.site_type.isnot(None))
        .distinct()
        .all()
    )
    categories = sorted([row[0] for row in cat_rows])

    # Periods: distinct period_start → bucket → deduplicate → sort
    period_rows = (
        db.query(UnifiedSite.period_start)
        .join(NewsItem, NewsItem.site_id == UnifiedSite.id)
        .filter(NewsItem.post_text.isnot(None), UnifiedSite.period_start.isnot(None))
        .distinct()
        .all()
    )
    period_labels = sorted(
        {_categorize_period(row[0]) for row in period_rows} - {"Unknown"},
        key=lambda p: _PERIOD_ORDER.get(p, 999),
    )

    # Countries: distinct country values
    country_rows = (
        db.query(UnifiedSite.country)
        .join(NewsItem, NewsItem.site_id == UnifiedSite.id)
        .filter(NewsItem.post_text.isnot(None), UnifiedSite.country.isnot(None))
        .distinct()
        .all()
    )
    countries = sorted([row[0] for row in country_rows])

    # News categories: distinct news_category values from news items
    news_cat_rows = (
        db.query(NewsItem.news_category)
        .filter(NewsItem.post_text.isnot(None), NewsItem.news_category.isnot(None))
        .distinct()
        .all()
    )
    news_categories = sorted([row[0] for row in news_cat_rows])

    result = NewsFiltersResponse(
        channels=channels,
        sites=sites,
        categories=categories,
        periods=period_labels,
        countries=countries,
        news_categories=news_categories,
    )

    cache_set(cache_key, result.model_dump(), ttl=600)  # 10 min cache
    return result


@router.get("/channels", response_model=list[NewsChannelResponse])
async def get_news_channels(db: Session = Depends(get_db)):
    """List all enabled news channels."""
    cache_key = "news:channels"
    cached = cache_get(cache_key)
    if cached:
        return cached

    channels = db.query(NewsChannel).filter(
        NewsChannel.enabled.is_(True)
    ).order_by(NewsChannel.name).all()

    result = [
        NewsChannelResponse(
            id=ch.id,
            name=ch.name,
        )
        for ch in channels
    ]

    cache_set(cache_key, [r.model_dump() for r in result], ttl=3600)  # 1 hour cache
    return result


@router.get("/articles", response_model=list[NewsArticleResponse])
async def get_news_articles(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Get weekly digest articles, newest first."""
    articles = db.query(NewsArticle).order_by(
        NewsArticle.created_at.desc()
    ).limit(limit).all()

    return [
        NewsArticleResponse(
            id=a.id,
            title=a.title,
            content=a.content,
            summary=a.summary,
            week_start=a.week_start.isoformat() if a.week_start else "",
            week_end=a.week_end.isoformat() if a.week_end else "",
            published_at=a.published_at.isoformat() if a.published_at else None,
        )
        for a in articles
    ]


@router.get("/stats", response_model=NewsStatsResponse)
async def get_news_stats(db: Session = Depends(get_db)):
    """Get news feed statistics."""
    cache_key = "news:stats"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        total_items = db.query(func.count(NewsItem.id)).scalar() or 0
        total_videos = db.query(func.count(distinct(NewsItem.video_id))).scalar() or 0
        total_channels = db.query(func.count(NewsChannel.id)).filter(
            NewsChannel.enabled.is_(True)
        ).scalar() or 0
        total_articles = db.query(func.count(NewsArticle.id)).scalar() or 0
        total_mins = db.query(func.sum(NewsVideo.duration_minutes)).scalar() or 0
        total_duration_hours = round(total_mins / 60, 1) if total_mins else 0
        latest = db.query(func.max(NewsItem.created_at)).scalar()
        latest_str = latest.isoformat() if latest else None
    except Exception:
        db.rollback()
        total_items = 0
        total_videos = 0
        total_channels = 0
        total_articles = 0
        total_duration_hours = 0
        latest_str = None

    result = NewsStatsResponse(
        total_items=total_items,
        total_videos=total_videos,
        total_channels=total_channels,
        total_articles=total_articles,
        total_duration_hours=total_duration_hours,
        latest_item_date=latest_str,
    )

    cache_set(cache_key, result.model_dump(), ttl=300)  # 5 min cache
    return result


@router.get("/lyra-status", response_model=LyraStatusResponse)
async def get_lyra_status(db: Session = Depends(get_db)):
    """Check if the Lyra pipeline is alive based on its heartbeat."""
    cache_key = "news:lyra-status"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        row = db.execute(
            text("SELECT last_heartbeat, status, last_error FROM pipeline_heartbeats WHERE pipeline_name = 'lyra'")
        ).fetchone()
    except Exception:
        db.rollback()
        row = None

    if not row:
        result = LyraStatusResponse(status="offline", last_heartbeat=None, last_cycle_ok=False)
    else:
        last_hb = row[0]
        cycle_status = row[1]
        age_seconds = (datetime.now(UTC) - last_hb).total_seconds()
        # Online if heartbeat within 2 hours (pipeline runs hourly)
        is_online = age_seconds < 7200
        result = LyraStatusResponse(
            status="online" if is_online else "offline",
            last_heartbeat=last_hb.isoformat(),
            last_cycle_ok=(cycle_status == "ok"),
        )

    cache_set(cache_key, result.model_dump(), ttl=60)  # 1 min cache
    return result
