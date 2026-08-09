"""
SEO-friendly HTML site browser: /sites/, /sites/{country} and
/sites/{country}/{slug}.

These crawlable pages are the link path from the homepage down to each of
the ~5,000 curated site detail pages. Only Ancient Nerds Originals are
listed (same rule as the sitemap) — the bulk-imported 750K sites are
searchable via the app but not part of the crawl surface.
"""

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.articles_html import public_stories_query
from api.seo_shell import shell_response
from pipeline import seo_pages
from pipeline.article_html_renderer import render_404_html, story_slug
from pipeline.database import NewsItem, get_db
from pipeline.sites_html_renderer import (
    country_slug,
    encode_path,
    site_id_prefix_from_slug,
    site_id_short,
    site_path,
    site_slug,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}

_CURATED_WHERE = "source_id = 'ancient_nerds' AND country IS NOT NULL AND country != ''"

# Plain concatenation of two module constants — the id is bound, never formatted in.
_LEGACY_SITE_SQL = text(
    "SELECT name, country FROM unified_sites WHERE id::text = :id AND " + _CURATED_WHERE
)


@router.get("/sites/")
async def sites_index(db: Session = Depends(get_db)):
    """Country index of curated archaeological sites."""
    rows = db.execute(
        text(f"""
            SELECT country, COUNT(*) AS count
            FROM unified_sites
            WHERE {_CURATED_WHERE}
            GROUP BY country
            ORDER BY country
        """)
    ).fetchall()

    countries = [
        {"name": row.country, "slug": country_slug(row.country), "count": row.count} for row in rows
    ]
    return shell_response(seo_pages.sites_index_page(countries), _HTML_HEADERS)


@router.get("/sites/{slug}")
async def sites_by_country(slug: str, db: Session = Depends(get_db)):
    """All curated sites of one country, matched by country slug."""
    rows = db.execute(
        # nosemgrep: semgrep.api-sql-fstring-interpolation -- _CURATED_WHERE is a module-level constant, no user input
        text(f"SELECT DISTINCT country FROM unified_sites WHERE {_CURATED_WHERE}")
    ).fetchall()
    country = next((row.country for row in rows if country_slug(row.country) == slug), None)

    if not country:
        return Response(
            content=render_404_html("Country"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )

    site_rows = db.execute(
        text(f"""
            SELECT id::text AS id, name, site_type, period_name, period_start,
                   description, thumbnail_url
            FROM unified_sites
            WHERE {_CURATED_WHERE} AND country = :country
            ORDER BY name
        """),
        {"country": country},
    ).fetchall()

    sites = [
        {
            "name": row.name,
            "description": row.description,
            "path": site_path(country, row.name, row.id),
            # Type, period and hero were selected here since the page was
            # written and dropped before rendering, so every card looked the
            # same. thumbnail_url is the local hero webp the image downloader
            # already writes per site — no join needed.
            "site_type": row.site_type,
            "period_name": row.period_name,
            "period_start": row.period_start,
            "thumbnail_url": row.thumbnail_url,
        }
        for row in site_rows
    ]
    return shell_response(seo_pages.country_sites_page(country, sites), _HTML_HEADERS)


@router.get("/site.html")
async def legacy_site_redirect(id: str = "", db: Session = Depends(get_db)):
    """
    301 the legacy /site.html?id={uuid} URL to its canonical slug URL.

    Shared links and bookmarks keep working, and Google consolidates the
    ranking signals on one URL per site instead of two. The built
    site.html shell is still read from disk to serve /sites/{country}/{slug} —
    only this HTTP path is redirected.
    """
    row = db.execute(_LEGACY_SITE_SQL, {"id": id}).fetchone() if id else None
    target = site_path(row.country, row.name, id) if row else "/sites/"
    return RedirectResponse(url=encode_path(target), status_code=301)


def _site_404() -> Response:
    return Response(
        content=render_404_html("Site"),
        media_type="text/html",
        status_code=404,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/sites/{country}/{slug}")
async def site_detail(country: str, slug: str, db: Session = Depends(get_db)):
    """
    Full crawlable detail page for one curated site.

    Resolution is by the 8-hex ID suffix in the slug, not by the name part,
    so renaming a site never orphans its URL — a stale name or country in
    the path is answered with a 301 to the current canonical URL.
    """
    prefix = site_id_prefix_from_slug(slug)
    if not prefix:
        return _site_404()

    row = db.execute(
        text(f"""
            SELECT id::text AS id, name, country, site_type, period_name,
                   period_start, period_end, description, lat, lon, source_url,
                   parent_site_id::text AS parent_site_id
            FROM unified_sites
            WHERE {_CURATED_WHERE} AND LEFT(REPLACE(id::text, '-', ''), 8) = :prefix
            LIMIT 1
        """),
        {"prefix": prefix},
    ).fetchone()

    if not row:
        return _site_404()

    canonical_country = country_slug(row.country)
    canonical_slug = site_slug(row.name, row.id)
    if country != canonical_country or slug != canonical_slug:
        return RedirectResponse(url=f"/sites/{canonical_country}/{canonical_slug}", status_code=301)

    site = {
        "id": row.id,
        "name": row.name,
        "country": row.country,
        "site_type": row.site_type,
        "period_name": row.period_name,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "description": row.description,
        "lat": row.lat,
        "lon": row.lon,
        "source_url": row.source_url,
    }
    return shell_response(
        seo_pages.site_detail_page(site, _related_content(row, db)), _HTML_HEADERS
    )


def _related_content(row, db: Session) -> dict:
    """Gather alternate names, hero image, news, resources and sibling sites."""
    alt_names = [
        r.name
        for r in db.execute(
            text("SELECT name FROM unified_site_names WHERE site_id = :sid ORDER BY name"),
            {"sid": row.id},
        ).fetchall()
    ]

    image = None
    img_row = db.execute(
        text("""
            SELECT filename, author, license, commons_page_url
            FROM wiki_images
            WHERE site_id = :sid AND (is_excluded = false OR is_excluded IS NULL)
            ORDER BY is_hero DESC, is_lead DESC, sort_order
            LIMIT 1
        """),
        {"sid": row.id},
    ).fetchone()
    if img_row:
        image = {
            "url": f"/data/images/wiki/{site_id_short(row.id)}/{img_row.filename}",
            "author": img_row.author,
            "license": img_row.license,
            "commons_url": img_row.commons_page_url,
        }

    # Same filter the /news-archive/{slug} route serves, so every link resolves.
    news = [
        {"slug": story_slug(item.headline, item.id), "headline": item.headline}
        for item in public_stories_query(db)
        .filter(NewsItem.site_id == row.id)
        .order_by(NewsItem.created_at.desc())
        .limit(10)
        .all()
    ]

    links = [
        {"title": r.title, "url": r.content_url, "content_type": r.content_type}
        for r in db.execute(
            text("""
                SELECT title, content_url, content_type
                FROM site_content_links
                WHERE site_id = :sid AND content_url IS NOT NULL
                ORDER BY relevance_score DESC NULLS LAST
                LIMIT 15
            """),
            {"sid": row.id},
        ).fetchall()
    ]

    parent = None
    if row.parent_site_id:
        p = db.execute(
            text("SELECT id::text AS id, name FROM unified_sites WHERE id::text = :pid"),
            {"pid": row.parent_site_id},
        ).fetchone()
        if p:
            parent = {"name": p.name, "path": site_path(row.country, p.name, p.id)}

    # Nearest curated neighbours in the same country: relevant to the reader
    # and spreads internal links instead of always pointing at the same
    # alphabetically-first sites.
    siblings = [
        {"name": r.name, "path": site_path(row.country, r.name, r.id)}
        for r in db.execute(
            text(f"""
                SELECT id::text AS id, name
                FROM unified_sites
                WHERE {_CURATED_WHERE} AND country = :country AND id::text <> :sid
                ORDER BY (lat - :lat) * (lat - :lat) + (lon - :lon) * (lon - :lon)
                LIMIT 24
            """),
            {"country": row.country, "sid": row.id, "lat": row.lat, "lon": row.lon},
        ).fetchall()
    ]

    return {
        "alt_names": alt_names,
        "image": image,
        "news": news,
        "links": links,
        "parent": parent,
        "siblings": siblings,
    }
