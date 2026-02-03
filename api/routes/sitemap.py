"""
Dynamic Sitemap Generator for SEO.

Generates XML sitemaps for search engine indexing.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import get_db

router = APIRouter()

# Base URL for the site
BASE_URL = "https://ancientnerds.com"


@router.get("/sitemap.xml")
async def get_sitemap(db: Session = Depends(get_db)):
    """
    Generate dynamic sitemap with all archaeological sites.
    Returns XML sitemap format for search engines.
    """
    # Get all sites from database
    query = text("""
        SELECT id, name, updated_at
        FROM unified_sites
        ORDER BY name
        LIMIT 50000
    """)

    result = db.execute(query)
    sites = result.fetchall()

    # Current date for homepage
    today = datetime.now().strftime("%Y-%m-%d")

    # Build XML sitemap
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '',
        '  <!-- Homepage -->',
        '  <url>',
        f'    <loc>{BASE_URL}/</loc>',
        f'    <lastmod>{today}</lastmod>',
        '    <changefreq>weekly</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>',
        '',
    ]

    # Add each site
    for site in sites:
        site_id = str(site.id)
        site_url = f"{BASE_URL}/?site={site_id}"
        # Use updated_at if available, otherwise use today
        lastmod = site.updated_at.strftime("%Y-%m-%d") if site.updated_at else today

        xml_parts.extend([
            '  <url>',
            f'    <loc>{site_url}</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            '    <changefreq>monthly</changefreq>',
            '    <priority>0.8</priority>',
            '  </url>',
        ])

    xml_parts.append('</urlset>')

    xml_content = '\n'.join(xml_parts)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache for 1 day
        }
    )


@router.get("/sitemap-index.xml")
async def get_sitemap_index():
    """
    Generate sitemap index for large sites.
    Points to the main sitemap.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{BASE_URL}/api/sitemap/sitemap.xml</loc>
    <lastmod>{today}</lastmod>
  </sitemap>
</sitemapindex>"""

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=86400",
        }
    )
