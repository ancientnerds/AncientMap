"""
News Feed API Routes.

Serves Lyra pipeline news items, channels, articles, and stats.
"""

import hmac
import logging
import os
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import distinct, func, text
from sqlalchemy.orm import Session, joinedload

from api.cache import cache_get, cache_set
from pipeline.database import (
    NewsArticle,
    NewsChannel,
    NewsItem,
    NewsVideo,
    UnifiedSite,
    get_db,
)
from pipeline.utils.country_lookup import country_name_variants, normalize_country
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period

LYRA_LOG_PATH = Path("/app/logs/ancient_nerds_lyra.log")

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Period Bucketing — uses canonical PERIOD_BUCKETS from pipeline.utils.text
# =============================================================================

_PERIOD_ORDER = {label: i for i, (label, _, _) in enumerate(PERIOD_BUCKETS)}


def _categorize_period(start: int | None) -> str:
    return categorize_period(start) or "Unknown"


def _period_label_to_range(label: str) -> tuple[int, int] | None:
    for bucket_label, lo, hi in PERIOD_BUCKETS:
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
    speculative_tag: str | None = None
    verified: bool = False
    verified_at: str | None = None
    web_sources: list[dict] | None = None


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
    quality_report: dict | None = None


class RejectionBreakdown(BaseModel):
    verified_rejected: int = 0
    low_significance: int = 0
    duplicate: int = 0
    unmatched: int = 0


class NewsStatsResponse(BaseModel):
    total_items: int
    total_videos: int
    total_channels: int
    total_articles: int
    total_duration_hours: float = 0
    latest_item_date: str | None = None
    rejected: RejectionBreakdown | None = None


class LyraStatusResponse(BaseModel):
    status: str  # "online", "offline", "error"
    last_heartbeat: str | None = None
    last_cycle_ok: bool = False


class PipelineStepData(BaseModel):
    count: int
    elapsed: float
    status: str  # "done", "fail", "skip", "run"
    error: str | None = None


class PipelineStatusResponse(BaseModel):
    pipeline: str
    status: str  # "online", "offline"
    last_heartbeat: str | None
    last_cycle_ok: bool
    total_elapsed: float | None
    steps: dict[str, PipelineStepData]


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
    speculative_tags: list[str] = []


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
    speculative_tag: str | None = None,
    sort: str | None = None,
    include_speculative: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get paginated news feed items, newest first."""
    cache_key = f"news:feed:{page}:{page_size}:{channel_id or 'all'}:{site_id or 'all'}:{category or 'all'}:{period or 'all'}:{country or 'all'}:{min_significance or 'all'}:{news_category or 'all'}:{speculative_tag or 'all'}:{sort or 'default'}:{include_speculative}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    query = (
        db.query(NewsItem)
        .join(NewsVideo)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .filter(
            NewsItem.post_text.isnot(None),
            (NewsItem.significance.is_(None)) | (NewsItem.significance >= 2),
        )
    )

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
        variants = country_name_variants(country)
        if variants:
            query = query.filter(func.lower(UnifiedSite.country).in_(variants))
        else:
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

    if speculative_tag:
        query = query.filter(NewsItem.speculative_tag == speculative_tag)

    if news_category:
        query = query.filter(NewsItem.news_category == news_category)
    elif not include_speculative:
        query = query.filter(
            (NewsItem.news_category != "speculative") | (NewsItem.significance >= 3)
        )

    total_count = query.count()
    offset = (page - 1) * page_size

    if sort == "significance":
        items = (
            query.order_by(
                NewsItem.significance.desc().nullslast(),
                NewsVideo.published_at.desc(),
                NewsItem.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )
    else:
        items = (
            query.order_by(NewsVideo.published_at.desc(), NewsItem.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

    result_items = []
    for item in items:
        video = item.video
        channel = video.channel if video else None
        site = item.site

        youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else None
        youtube_deep_url = None
        if video and item.timestamp_seconds:
            youtube_deep_url = (
                f"https://www.youtube.com/watch?v={video.id}&t={item.timestamp_seconds}s"
            )

        result_items.append(
            NewsItemResponse(
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
                speculative_tag=item.speculative_tag,
                verified=item.verified_at is not None,
                verified_at=item.verified_at.isoformat() if item.verified_at else None,
                web_sources=item.web_sources,
            )
        )

    response = NewsFeedResponse(
        items=result_items,
        total_count=total_count,
        page=page,
        has_more=(offset + page_size) < total_count,
    )

    cache_set(cache_key, response.model_dump(), ttl=300)  # 5 min cache
    return response


@router.get("/item/{item_id}", response_model=NewsItemResponse)
async def get_news_item(item_id: int, db: Session = Depends(get_db)):
    """Get a single news item by ID."""
    item = (
        db.query(NewsItem)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .filter(NewsItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")

    video = item.video
    channel = video.channel if video else None
    site = item.site

    youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else None
    youtube_deep_url = None
    if video and item.timestamp_seconds:
        youtube_deep_url = f"https://www.youtube.com/watch?v={video.id}&t={item.timestamp_seconds}s"

    return NewsItemResponse(
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
        speculative_tag=item.speculative_tag,
        verified=item.verified_at is not None,
        verified_at=item.verified_at.isoformat() if item.verified_at else None,
        web_sources=item.web_sources,
    )


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
    raw_countries = [row[0] for row in country_rows]
    iso_groups: dict[str, str] = {}
    for c in raw_countries:
        iso = normalize_country(c)
        if iso not in iso_groups:
            iso_groups[iso] = c
    countries = sorted(iso_groups.values())

    # News categories: distinct news_category values from news items
    news_cat_rows = (
        db.query(NewsItem.news_category)
        .filter(NewsItem.post_text.isnot(None), NewsItem.news_category.isnot(None))
        .distinct()
        .all()
    )
    news_categories = sorted([row[0] for row in news_cat_rows if row[0] != "speculative"])

    # Speculative tags: distinct speculative_tag values from speculative items
    spec_tag_rows = (
        db.query(NewsItem.speculative_tag)
        .filter(
            NewsItem.post_text.isnot(None),
            NewsItem.news_category == "speculative",
            NewsItem.speculative_tag.isnot(None),
        )
        .distinct()
        .all()
    )
    speculative_tags = sorted([row[0] for row in spec_tag_rows])

    result = NewsFiltersResponse(
        channels=channels,
        sites=sites,
        categories=categories,
        periods=period_labels,
        countries=countries,
        news_categories=news_categories,
        speculative_tags=speculative_tags,
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

    channels = (
        db.query(NewsChannel).filter(NewsChannel.enabled.is_(True)).order_by(NewsChannel.name).all()
    )

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
    articles = (
        db.query(NewsArticle)
        .filter(NewsArticle.active.is_(True))
        .order_by(NewsArticle.week_start.desc())
        .limit(limit)
        .all()
    )

    return [
        NewsArticleResponse(
            id=a.id,
            title=a.title,
            content=a.content,
            summary=a.summary,
            week_start=a.week_start.isoformat() if a.week_start else "",
            week_end=a.week_end.isoformat() if a.week_end else "",
            published_at=a.published_at.isoformat() if a.published_at else None,
            quality_report=a.quality_report,
        )
        for a in articles
    ]


# Regex to parse citation lines from ### Sources and ### Videos sections.
# Matches both "1. [...](...)" and "V1. [...](...)" formats.
# e.g. "V1. [Channel — "Title"](https://youtu.be/VIDEO_ID?t=123)"
_CITATION_RE = re.compile(
    r"^V?(\d+)\.\s*\[.*?\]\("
    r"https?://(?:youtu\.be/([^?\s)]+)(?:\?t=(\d+))?|"
    r"(?:www\.)?youtube\.com/watch\?v=([^&\s)]+)(?:&t=(\d+))?)"
    r"\)",
    re.MULTILINE,
)


def _parse_citation_match(m: re.Match) -> tuple[str, str, int | None]:
    """Extract (citation_key, video_id, timestamp) from either URL format.

    citation_key is "V1", "V2" etc for video citations (from ### Videos),
    or "1", "2" etc for source citations (from ### Sources).
    The full match line determines which — the regex captures the number.
    """
    num = m.group(1)
    # Check if original line started with V
    key = f"V{num}" if m.group(0).startswith("V") else num
    if m.group(2):  # youtu.be format
        return key, m.group(2), int(m.group(3)) if m.group(3) else None
    if m.group(4):  # youtube.com format
        return key, m.group(4), int(m.group(5)) if m.group(5) else None
    return key, "", None


@router.get("/articles/{article_id}/citations")
async def article_citations(article_id: int, db: Session = Depends(get_db)):
    """Return news items keyed by citation number for hover cards."""
    cache_key = f"news:article-citations:{article_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Parse (citation_key, video_id, timestamp_seconds) from Sources + Videos sections
    sources_idx = article.content.find("### Sources")
    if sources_idx == -1:
        sources_idx = article.content.find("### Videos")
    if sources_idx == -1:
        return {}
    sources_text = article.content[sources_idx:]
    parsed = [_parse_citation_match(m) for m in _CITATION_RE.finditer(sources_text)]
    parsed = [(c, v, t) for c, v, t in parsed if v]  # filter empty video_ids
    if not parsed:
        return {}

    # Fetch all relevant news items in one query
    video_ids = list({vid for _, vid, _ in parsed})
    items = (
        db.query(NewsItem)
        .filter(NewsItem.video_id.in_(video_ids))
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .all()
    )

    # Build lookup: (video_id, timestamp_seconds) → NewsItem
    by_vid_ts: dict[tuple[str, int | None], NewsItem] = {}
    by_vid: dict[str, list[NewsItem]] = {}
    for item in items:
        by_vid_ts[(item.video_id, item.timestamp_seconds)] = item
        by_vid.setdefault(item.video_id, []).append(item)

    # Match each citation to a NewsItem
    result: dict[str, NewsItemResponse] = {}
    for cit_num, video_id, ts in parsed:
        matched = by_vid_ts.get((video_id, ts))
        if not matched and video_id in by_vid and ts is not None:
            # Fallback: closest timestamp within 60s window (avoid wrong matches
            # when multiple news items come from the same long video)
            candidates = by_vid[video_id]
            candidates.sort(key=lambda i: abs((i.timestamp_seconds or 0) - ts))
            if abs((candidates[0].timestamp_seconds or 0) - ts) <= 60:
                matched = candidates[0]
        if not matched:
            continue

        video = matched.video
        channel = video.channel if video else None
        site = matched.site
        youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else None
        youtube_deep_url = None
        if video and matched.timestamp_seconds:
            youtube_deep_url = (
                f"https://www.youtube.com/watch?v={video.id}&t={matched.timestamp_seconds}s"
            )

        result[str(cit_num)] = NewsItemResponse(
            id=matched.id,
            headline=matched.headline,
            summary=matched.summary,
            post_text=matched.post_text,
            facts=matched.facts,
            timestamp_range=matched.timestamp_range,
            timestamp_seconds=matched.timestamp_seconds,
            screenshot_url=matched.screenshot_url,
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
            created_at=matched.created_at.isoformat() if matched.created_at else "",
            site_id=str(site.id) if site else None,
            site_name=site.name if site else None,
            site_lat=site.lat if site else None,
            site_lon=site.lon if site else None,
            site_type=site.site_type if site else None,
            site_period_name=site.period_name if site else None,
            site_period_start=site.period_start if site else None,
            site_country=site.country if site else None,
            site_name_extracted=matched.site_name_extracted if not site else None,
            significance=matched.significance,
            news_category=matched.news_category,
            speculative_tag=matched.speculative_tag,
        )

    # Serialize Pydantic models — json.dumps in cache_set can't handle them raw
    cache_set(cache_key, {k: v.model_dump() for k, v in result.items()}, ttl=3600)  # 1 hour cache
    return result


@router.get("/stats", response_model=NewsStatsResponse)
async def get_news_stats(db: Session = Depends(get_db)):
    """Get news feed statistics."""
    cache_key = "news:stats"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        total_items = (
            db.query(func.count(NewsItem.id)).filter(NewsItem.post_text.isnot(None)).scalar() or 0
        )
        total_videos = db.query(func.count(distinct(NewsItem.video_id))).scalar() or 0
        total_channels = (
            db.query(func.count(NewsChannel.id)).filter(NewsChannel.enabled.is_(True)).scalar() or 0
        )
        total_articles = db.query(func.count(NewsArticle.id)).scalar() or 0
        total_mins = db.query(func.sum(NewsVideo.duration_minutes)).scalar() or 0
        total_duration_hours = round(total_mins / 60, 1) if total_mins else 0
        latest = db.query(func.max(NewsItem.created_at)).scalar()
        latest_str = latest.isoformat() if latest else None

        # Rejection breakdown
        null_items = (
            db.query(NewsItem.news_category, func.count(NewsItem.id))
            .filter(NewsItem.post_text.is_(None))
            .group_by(NewsItem.news_category)
            .all()
        )

        breakdown = RejectionBreakdown()
        for category, count in null_items:
            if category in ("rejected", "unverified"):
                breakdown.verified_rejected += count
            elif category == "duplicate":
                breakdown.duplicate = count
            else:
                # Significance=1 rescored items keep their old category (usually "general")
                # and items that never got a post matched also land here
                breakdown.low_significance += count
    except Exception:
        db.rollback()
        raise

    result = NewsStatsResponse(
        total_items=total_items,
        total_videos=total_videos,
        total_channels=total_channels,
        total_articles=total_articles,
        total_duration_hours=total_duration_hours,
        latest_item_date=latest_str,
        rejected=breakdown,
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
            text(
                "SELECT last_heartbeat, status, last_error FROM pipeline_heartbeats WHERE pipeline_name = 'lyra'"
            )
        ).fetchone()
    except Exception as exc:
        db.rollback()
        logger.warning(f"Lyra heartbeat query failed: {exc}")
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


@router.get("/pipeline-status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    pipeline: str = Query("news", pattern="^(news|radar|article)$"),
    db: Session = Depends(get_db),
):
    """Get pipeline step-level status for the ops dashboard."""
    cache_key = f"news:pipeline-status:{pipeline}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Determine which heartbeat row and which step keys to include
    if pipeline == "article":
        pipeline_name = "lyra-article"
        step_keys = None  # Include all steps
    else:
        pipeline_name = "lyra"
        # Filter to relevant step group
        if pipeline == "news":
            step_keys = {
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
            }
        else:  # radar
            step_keys = {"identify"}

    try:
        row = db.execute(
            text(
                "SELECT last_heartbeat, status, last_error, step_data FROM pipeline_heartbeats WHERE pipeline_name = :name"
            ),
            {"name": pipeline_name},
        ).fetchone()
    except Exception as exc:
        db.rollback()
        logger.warning(f"Pipeline status query failed: {exc}")
        row = None

    if not row:
        result = PipelineStatusResponse(
            pipeline=pipeline,
            status="offline",
            last_heartbeat=None,
            last_cycle_ok=False,
            total_elapsed=None,
            steps={},
        )
    else:
        last_hb = row[0]
        cycle_status = row[1]
        raw_step_data = row[3] or {}

        age_seconds = (datetime.now(UTC) - last_hb).total_seconds()
        # Online if heartbeat within 2 hours (news pipeline runs hourly)
        # Article pipeline runs weekly, so use 8 days
        max_age = 691200 if pipeline == "article" else 7200
        is_online = age_seconds < max_age

        # Filter steps and extract total_elapsed
        total_elapsed = (
            raw_step_data.get("_total_elapsed") if isinstance(raw_step_data, dict) else None
        )
        steps = {}
        if isinstance(raw_step_data, dict):
            for k, v in raw_step_data.items():
                if k.startswith("_"):
                    continue
                if step_keys is not None and k not in step_keys:
                    continue
                if isinstance(v, dict):
                    steps[k] = PipelineStepData(
                        count=v.get("count", 0),
                        elapsed=v.get("elapsed", 0),
                        status=v.get("status", "done"),
                        error=v.get("error"),
                    )

        result = PipelineStatusResponse(
            pipeline=pipeline,
            status="online" if is_online else "offline",
            last_heartbeat=last_hb.isoformat(),
            last_cycle_ok=(cycle_status == "ok"),
            total_elapsed=total_elapsed,
            steps=steps,
        )

    cache_set(cache_key, result.model_dump(), ttl=30)
    return result


@router.get("/logs", response_class=PlainTextResponse)
async def get_lyra_logs(
    request: Request,
    lines: int = Query(default=100, ge=1, le=2000),
    search: str = Query(default="", max_length=200),
):
    """Return the last N lines from the Lyra pipeline log file.

    Protected by LYRA_ADMIN_KEY — pass via X-Admin-Key header.
    """
    admin_key = os.environ.get("LYRA_ADMIN_KEY", "")
    provided = request.headers.get("X-Admin-Key", "")
    if not admin_key or not hmac.compare_digest(provided, admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    if not LYRA_LOG_PATH.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    # Read last N lines efficiently
    with open(LYRA_LOG_PATH, "rb") as f:
        # Seek from end to find enough newlines
        try:
            f.seek(0, 2)
            size = f.tell()
            # Read at most 512KB from the tail
            read_size = min(size, 512 * 1024)
            f.seek(size - read_size)
            tail = f.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Failed to read log file") from exc

    all_lines = tail.splitlines()
    result = all_lines[-lines:]

    if search:
        search_lower = search.lower()
        result = [ln for ln in result if search_lower in ln.lower()]

    return "\n".join(result)
