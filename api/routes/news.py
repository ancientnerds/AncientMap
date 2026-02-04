"""
News Feed API Routes.

Serves Lyra pipeline news items, channels, articles, and stats.
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from api.cache import cache_get, cache_set
from pipeline.database import NewsArticle, NewsChannel, NewsItem, NewsVideo, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


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
    facts: list[str] | None = None
    timestamp_range: str | None = None
    timestamp_seconds: int | None = None
    youtube_url: str | None = None
    youtube_deep_url: str | None = None
    video: NewsVideoInfo
    created_at: str


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
    latest_item_date: str | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/feed", response_model=NewsFeedResponse)
async def get_news_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Get paginated news feed items, newest first."""
    cache_key = f"news:feed:{page}:{page_size}:{channel_id or 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    query = db.query(NewsItem).join(NewsVideo).options(
        joinedload(NewsItem.video).joinedload(NewsVideo.channel)
    )

    if channel_id:
        query = query.filter(NewsVideo.channel_id == channel_id)

    total_count = query.count()
    offset = (page - 1) * page_size

    items = query.order_by(NewsItem.created_at.desc()).offset(offset).limit(page_size).all()

    result_items = []
    for item in items:
        video = item.video
        channel = video.channel if video else None

        youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else None
        youtube_deep_url = None
        if video and item.timestamp_seconds:
            youtube_deep_url = f"https://www.youtube.com/watch?v={video.id}&t={item.timestamp_seconds}s"

        result_items.append(NewsItemResponse(
            id=item.id,
            headline=item.headline,
            summary=item.summary,
            facts=item.facts,
            timestamp_range=item.timestamp_range,
            timestamp_seconds=item.timestamp_seconds,
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
        ))

    response = NewsFeedResponse(
        items=result_items,
        total_count=total_count,
        page=page,
        has_more=(offset + page_size) < total_count,
    )

    cache_set(cache_key, response.model_dump(), ttl=300)  # 5 min cache
    return response


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
        total_videos = db.query(func.count(NewsVideo.id)).scalar() or 0
        total_channels = db.query(func.count(NewsChannel.id)).filter(
            NewsChannel.enabled.is_(True)
        ).scalar() or 0
        total_articles = db.query(func.count(NewsArticle.id)).scalar() or 0
        latest = db.query(func.max(NewsItem.created_at)).scalar()
        latest_str = latest.isoformat() if latest else None
    except Exception:
        db.rollback()
        total_items = 0
        total_videos = 0
        total_channels = 0
        total_articles = 0
        latest_str = None

    result = NewsStatsResponse(
        total_items=total_items,
        total_videos=total_videos,
        total_channels=total_channels,
        total_articles=total_articles,
        latest_item_date=latest_str,
    )

    cache_set(cache_key, result.model_dump(), ttl=300)  # 5 min cache
    return result
