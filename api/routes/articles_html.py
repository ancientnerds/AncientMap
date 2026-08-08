"""
SEO-friendly HTML article and news archive routes.

Serves full HTML pages (not JSON) for search engine crawling.
These routes live outside /api/ so nginx proxies them directly.
"""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session, joinedload

from api.seo_shell import shell_response
from pipeline import seo_pages
from pipeline.article_html_renderer import (
    BASE_URL,
    markdown_to_html,
    render_404_html,
    render_medium_copy_html,
    slugify,
    story_id_from_slug,
    story_slug,
)
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}
_HTML_HEADERS_SHORT = {"Cache-Control": "public, max-age=1800"}

STORIES_PER_PAGE = 50


def public_stories_query(db: Session):
    """
    Base query for publicly listed news stories (same filter everywhere).

    Authoritative: /news-archive/{slug} serves exactly this set, so the
    sitemap and any page linking to a story must use it too — otherwise
    we advertise URLs that 404.
    """
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

    return shell_response(seo_pages.article_index_page(article_dicts), _HTML_HEADERS)


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

    return shell_response(
        seo_pages.article_page(
            {
                "title": article.title,
                "slug": slug,
                "summary": article.summary,
                "published_at": article.published_at,
            },
            markdown_to_html(article.content),
        ),
        _HTML_HEADERS,
    )


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
        canonical_url=f"{BASE_URL}/articles/{slug}",
    )
    return Response(content=html, media_type="text/html")


async def _render_news_archive_page(page: int, db: Session) -> Response:
    """Render one paginated page of the news archive."""
    total_count = public_stories_query(db).count()
    total_pages = max(1, -(-total_count // STORIES_PER_PAGE))  # ceil division

    if page < 1 or (page > total_pages):
        return Response(
            content=render_404_html("Page"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )

    items = (
        public_stories_query(db)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel),
            joinedload(NewsItem.site),
        )
        .order_by(NewsVideo.published_at.desc(), NewsItem.created_at.desc())
        .offset((page - 1) * STORIES_PER_PAGE)
        .limit(STORIES_PER_PAGE)
        .all()
    )

    # The joinedloads above already fetch video + site; the listing used to
    # drop both and render title-plus-blurb cards only (2026-08-08).
    stories = [
        {
            "slug": story_slug(item.headline, item.id),
            "headline": item.headline,
            "summary": item.summary,
            "published_at": (
                item.video.published_at
                if item.video and item.video.published_at
                else item.created_at
            ),
            "news_category": item.news_category,
            "site_name": item.site.name if item.site else (item.site_name_extracted or ""),
            "channel_name": (item.video.channel.name if item.video and item.video.channel else ""),
            "speculative_tag": item.speculative_tag,
        }
        for item in items
    ]
    return shell_response(
        seo_pages.story_archive_page(stories, page, total_pages, total_count),
        _HTML_HEADERS_SHORT,
    )


@router.get("/news-archive/")
async def news_archive(db: Session = Depends(get_db)):
    """First page of the crawlable news archive."""
    return await _render_news_archive_page(1, db)


@router.get("/news-archive/page/{page}")
async def news_archive_page(page: int, db: Session = Depends(get_db)):
    """Subsequent pages of the crawlable news archive."""
    return await _render_news_archive_page(page, db)


def _related_stories(db: Session, item: NewsItem, limit: int = 5) -> list[dict]:
    """Other stories worth reading after this one.

    Same site first — that is the strongest link the data offers. Most
    stories never match a site (the extractor only resolves a minority), so
    those fall back to the same category, otherwise an indexed story would
    be a dead end with a single link back to the archive.
    """
    base = public_stories_query(db).filter(NewsItem.id != item.id)
    rows: list[NewsItem] = []
    kind = ""
    if item.site_id:
        rows = (
            base.filter(NewsItem.site_id == item.site_id)
            .order_by(NewsItem.created_at.desc())
            .limit(limit)
            .all()
        )
        kind = "site"
    if not rows and item.news_category:
        rows = (
            base.filter(NewsItem.news_category == item.news_category)
            .order_by(NewsItem.created_at.desc())
            .limit(limit)
            .all()
        )
        kind = "category"
    return [
        {
            "slug": story_slug(r.headline, r.id),
            "headline": r.headline,
            "kind": kind,
        }
        for r in rows
    ]


@router.get("/news-archive/{slug}")
async def story_page(slug: str, db: Session = Depends(get_db)):
    """Full HTML page for a single news story."""
    item_id = story_id_from_slug(slug)
    item = (
        (
            public_stories_query(db)
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
        "site_country": site.country if site else "",
        "screenshot_url": item.screenshot_url,
        "youtube_url": f"https://www.youtube.com/watch?v={video.id}" if video else "",
        "video_title": video.title if video else "",
        "channel_name": video.channel.name if video and video.channel else "",
        "published_at": (video.published_at if video and video.published_at else item.created_at),
        "news_category": item.news_category,
        # Stored per story since the tweet-verifier work, never rendered until
        # 2026-08-08: researched web sources, the exact video offset, and the
        # pipeline's own speculative label.
        "web_sources": item.web_sources,
        "timestamp_seconds": item.timestamp_seconds,
        "speculative_tag": item.speculative_tag,
        "related": _related_stories(db, item),
    }

    return shell_response(seo_pages.story_page(story), _HTML_HEADERS)
