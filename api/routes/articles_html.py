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
    render_medium_copy_html,
    render_news_archive_html,
    render_story_html,
    slugify,
    story_id_from_slug,
)
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}
_HTML_HEADERS_SHORT = {"Cache-Control": "public, max-age=1800"}

STORIES_PER_PAGE = 50


def _public_stories_query(db: Session):
    """Base query for publicly listed news stories (same filter everywhere)."""
    return (
        db.query(NewsItem)
        .join(NewsVideo)
        .filter(NewsItem.post_text.isnot(None))
        .filter((NewsItem.news_category != "speculative") | (NewsItem.news_category.is_(None)))
    )


@router.get("/articles/")
async def articles_listing(db: Session = Depends(get_db)):
    """HTML listing of all journals — the crawlable hub linking every article page."""
    articles = db.query(NewsArticle).order_by(NewsArticle.created_at.desc()).all()

    article_dicts = [
        {
            "title": article.title,
            "summary": article.summary,
            "slug": slugify(article.title),
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "week_start": article.week_start.isoformat() if article.week_start else "",
            "week_end": article.week_end.isoformat() if article.week_end else "",
        }
        for article in articles
    ]

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


@router.get("/articles/{slug}/medium")
async def article_medium_copy(slug: str, db: Session = Depends(get_db)):
    """Clean, light-themed article page for copying into Medium's editor."""
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
        )

    html = render_medium_copy_html(
        title=article.title,
        content_md=article.content,
        summary=article.summary,
        slug=slug,
    )
    return Response(content=html, media_type="text/html")


async def _render_news_archive_page(page: int, db: Session) -> Response:
    """Render one paginated page of the news archive."""
    total_count = _public_stories_query(db).count()
    total_pages = max(1, -(-total_count // STORIES_PER_PAGE))  # ceil division

    if page < 1 or (page > total_pages):
        return Response(
            content=render_404_html("Page"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )

    items = (
        _public_stories_query(db)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .order_by(NewsVideo.published_at.desc(), NewsItem.created_at.desc())
        .offset((page - 1) * STORIES_PER_PAGE)
        .limit(STORIES_PER_PAGE)
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

        grouped[date_label].append(
            {
                "id": item.id,
                "headline": item.headline,
                "summary": item.summary,
                "facts": item.facts,
                "site_name": site.name if site else (item.site_name_extracted or ""),
                "site_id": str(site.id) if site else "",
                "video_title": video.title if video else "",
                "youtube_url": youtube_url,
            }
        )

    # Convert to ordered list of tuples
    items_by_date = list(grouped.items())  # already ordered by query

    html = render_news_archive_html(items_by_date, total_count, page, total_pages)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS_SHORT)


@router.get("/news-archive/")
async def news_archive(db: Session = Depends(get_db)):
    """First page of the crawlable news archive."""
    return await _render_news_archive_page(1, db)


@router.get("/news-archive/page/{page}")
async def news_archive_page(page: int, db: Session = Depends(get_db)):
    """Subsequent pages of the crawlable news archive."""
    return await _render_news_archive_page(page, db)


@router.get("/news-archive/{slug}")
async def story_page(slug: str, db: Session = Depends(get_db)):
    """Full HTML page for a single news story."""
    item_id = story_id_from_slug(slug)
    item = (
        (
            _public_stories_query(db)
            .options(
                joinedload(NewsItem.video).joinedload(NewsVideo.channel),
                joinedload(NewsItem.site),
            )
            .filter(NewsItem.id == item_id)
            .first()
        )
        if item_id is not None
        else None
    )

    if not item:
        return Response(
            content=render_404_html("Story"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )

    video = item.video
    site = item.site
    story = {
        "id": item.id,
        "headline": item.headline,
        "summary": item.summary,
        "facts": item.facts,
        "post_text": item.post_text,
        "site_name": site.name if site else (item.site_name_extracted or ""),
        "site_id": str(site.id) if site else "",
        "screenshot_url": item.screenshot_url,
        "youtube_url": f"https://www.youtube.com/watch?v={video.id}" if video else "",
        "video_title": video.title if video else "",
        "channel_name": video.channel.name if video and video.channel else "",
        "published_at": (video.published_at if video and video.published_at else item.created_at),
        "news_category": item.news_category,
    }

    html = render_story_html(story)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)
