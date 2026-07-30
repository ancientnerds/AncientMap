"""
SEO-friendly HTML site browser: /sites/ and /sites/{country}.

These crawlable listings are the link path from the homepage to the
~5,000 curated site detail pages. Only Ancient Nerds Originals are
listed (same rule as the sitemap) — the bulk-imported 750K sites are
searchable via the app but not part of the crawl surface.
"""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.article_html_renderer import render_404_html
from pipeline.database import get_db
from pipeline.sites_html_renderer import (
    country_slug,
    render_country_sites_html,
    render_sites_index_html,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}

_CURATED_WHERE = "source_id = 'ancient_nerds' AND country IS NOT NULL AND country != ''"


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
    html = render_sites_index_html(countries)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)


@router.get("/sites/{slug}")
async def sites_by_country(slug: str, db: Session = Depends(get_db)):
    """All curated sites of one country, matched by country slug."""
    rows = db.execute(
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
            SELECT id::text AS id, name, site_type, period_name, description
            FROM unified_sites
            WHERE {_CURATED_WHERE} AND country = :country
            ORDER BY name
        """),
        {"country": country},
    ).fetchall()

    sites = [
        {
            "id": row.id,
            "name": row.name,
            "site_type": row.site_type,
            "period_name": row.period_name,
            "description": row.description,
        }
        for row in site_rows
    ]
    html = render_country_sites_html(country, slug, sites)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)
