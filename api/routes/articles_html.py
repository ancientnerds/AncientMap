"""
SEO-friendly HTML article and news archive routes.

Serves full HTML pages (not JSON) for search engine crawling.
These routes live outside /api/ so nginx proxies them directly.
"""

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session, joinedload

from pipeline.article_html_renderer import (
    render_404_html,
    render_article_html,
    render_article_listing_html,
    render_news_archive_html,
    slugify,
)
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}
_HTML_HEADERS_SHORT = {"Cache-Control": "public, max-age=1800"}


@router.get("/articles/")
async def articles_listing(db: Session = Depends(get_db)):
    """HTML listing of all articles (newest first)."""
    articles = db.query(NewsArticle).order_by(
        NewsArticle.created_at.desc()
    ).all()

    article_dicts = []
    for a in articles:
        article_dicts.append({
            "title": a.title,
            "summary": a.summary,
            "slug": slugify(a.title),
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "week_start": a.week_start.isoformat() if a.week_start else "",
            "week_end": a.week_end.isoformat() if a.week_end else "",
        })

    html = render_article_listing_html(article_dicts)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)


@router.get("/articles/{slug}")
async def article_page(slug: str, db: Session = Depends(get_db)):
    """Full HTML article page by slug."""
    # Find article by matching slugified title
    articles = db.query(NewsArticle).all()
    article = None
    for a in articles:
        if slugify(a.title) == slug:
            article = a
            break

    if not article:
        return Response(
            content=render_404_html("Article"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )

    html = render_article_html(
        title=article.title,
        content_md=article.content,
        summary=article.summary,
        published_at=article.published_at,
        week_start=article.week_start,
        week_end=article.week_end,
        slug=slug,
    )
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)


@router.get("/news-archive/")
async def news_archive(db: Session = Depends(get_db)):
    """HTML page listing the latest ~200 news items, grouped by date."""
    items = (
        db.query(NewsItem)
        .join(NewsVideo)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .filter(NewsItem.post_text.isnot(None))
        .filter(
            (NewsItem.news_category != "speculative") | (NewsItem.news_category.is_(None))
        )
        .order_by(NewsVideo.published_at.desc(), NewsItem.created_at.desc())
        .limit(200)
        .all()
    )

    # Group by date
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        video = item.video
        site = item.site

        date_label = ""
        if video and video.published_at:
            date_label = video.published_at.strftime("%B %d, %Y")
        elif item.created_at:
            date_label = item.created_at.strftime("%B %d, %Y")

        youtube_url = f"https://www.youtube.com/watch?v={video.id}" if video else ""

        grouped[date_label].append({
            "headline": item.headline,
            "summary": item.summary,
            "facts": item.facts,
            "site_name": site.name if site else (item.site_name_extracted or ""),
            "video_title": video.title if video else "",
            "youtube_url": youtube_url,
        })

    # Convert to ordered list of tuples
    items_by_date = list(grouped.items())  # already ordered by query

    total_count = (
        db.query(NewsItem)
        .filter(NewsItem.post_text.isnot(None))
        .filter(
            (NewsItem.news_category != "speculative") | (NewsItem.news_category.is_(None))
        )
        .count()
    )

    html = render_news_archive_html(items_by_date, total_count)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS_SHORT)
