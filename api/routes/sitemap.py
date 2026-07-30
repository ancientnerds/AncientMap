"""
Dynamic Sitemap Generator for SEO.

Generates XML sitemaps for search engine indexing.
"""

from datetime import datetime
from html import escape

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.article_html_renderer import slugify, story_slug
from pipeline.database import NewsArticle, NewsItem, get_db
from pipeline.sites_html_renderer import country_slug

router = APIRouter()

# Base URL for the site
BASE_URL = "https://ancientnerds.com"


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def get_sitemap(db: Session = Depends(get_db)):
    """
    Generate dynamic sitemap with all archaeological sites.
    Returns XML sitemap format for search engines.
    """
    # Only include Ancient Nerds Originals (curated sites), not bulk-imported sources
    query = text("""
        SELECT id, name, updated_at
        FROM unified_sites
        WHERE source_id = 'ancient_nerds'
        ORDER BY name
    """)

    result = db.execute(query)
    sites = result.fetchall()

    # Current date for homepage
    today = datetime.now().strftime("%Y-%m-%d")

    # Build XML sitemap
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
        "",
        "  <!-- Homepage -->",
        "  <url>",
        f"    <loc>{BASE_URL}/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "    <image:image>",
        f"      <image:loc>{BASE_URL}/landing/og-image.png</image:loc>",
        "      <image:title>Ancient Nerds Interactive Archaeological Research Platform</image:title>",
        "      <image:caption>Explore over 750,000 archaeological sites worldwide on an interactive 3D globe</image:caption>",
        "    </image:image>",
        "  </url>",
        "",
        "  <!-- Interactive Globe -->",
        "  <url>",
        f"    <loc>{BASE_URL}/globe.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.9</priority>",
        "  </url>",
        "",
        "  <!-- Archaeology News -->",
        "  <url>",
        f"    <loc>{BASE_URL}/news.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "",
        "  <!-- Lyra AI Assistant -->",
        "  <url>",
        f"    <loc>{BASE_URL}/lyra.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
        "",
        "  <!-- Discovery Radar -->",
        "  <url>",
        f"    <loc>{BASE_URL}/radar.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
        "",
        "  <!-- Weekly Articles (SPA) -->",
        "  <url>",
        f"    <loc>{BASE_URL}/articles.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
        "",
        "  <!-- Site Search -->",
        "  <url>",
        f"    <loc>{BASE_URL}/search.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
        "",
        "  <!-- Theo Research Lab -->",
        "  <url>",
        f"    <loc>{BASE_URL}/theo.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.7</priority>",
        "  </url>",
        "",
        "  <!-- Citation Library -->",
        "  <url>",
        f"    <loc>{BASE_URL}/library.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
        "",
        "  <!-- API Documentation -->",
        "  <url>",
        f"    <loc>{BASE_URL}/api.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
        "",
        "  <!-- SEO: Crawlable article listing -->",
        "  <url>",
        f"    <loc>{BASE_URL}/articles/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "",
        "  <!-- SEO: Crawlable news archive -->",
        "  <url>",
        f"    <loc>{BASE_URL}/news-archive/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "",
        "  <!-- SEO: Crawlable research library -->",
        "  <url>",
        f"    <loc>{BASE_URL}/research/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "",
        "  <!-- SEO: Crawlable site browser -->",
        "  <url>",
        f"    <loc>{BASE_URL}/sites/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.8</priority>",
        "  </url>",
        "",
    ]

    # --- Country browse pages (/sites/{country}) ---
    country_rows = db.execute(
        text("""
            SELECT DISTINCT country
            FROM unified_sites
            WHERE source_id = 'ancient_nerds' AND country IS NOT NULL AND country != ''
            ORDER BY country
        """)
    ).fetchall()
    for row in country_rows:
        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{escape(f'{BASE_URL}/sites/{country_slug(row.country)}')}</loc>",
                f"    <lastmod>{today}</lastmod>",
                "    <changefreq>weekly</changefreq>",
                "    <priority>0.7</priority>",
                "  </url>",
            ]
        )

    # Add each site
    for site in sites:
        site_id = str(site.id)
        site_url = f"{BASE_URL}/site.html?id={site_id}"
        # Use updated_at if available, otherwise use today
        lastmod = site.updated_at.strftime("%Y-%m-%d") if site.updated_at else today

        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{site_url}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                "    <changefreq>monthly</changefreq>",
                "    <priority>0.8</priority>",
                "  </url>",
            ]
        )

    # --- Articles (high SEO value: keyword-rich, regularly updated) ---
    articles = db.query(NewsArticle).order_by(NewsArticle.created_at.desc()).all()
    for article in articles:
        slug = slugify(article.title)
        article_url = f"{BASE_URL}/articles/{slug}"
        lastmod = article.published_at.strftime("%Y-%m-%d") if article.published_at else today
        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{escape(article_url)}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                "    <changefreq>monthly</changefreq>",
                "    <priority>0.9</priority>",
                "  </url>",
            ]
        )

    # --- Research papers (open-access, multi-thousand-word unique content) ---
    paper_rows = db.execute(
        text("""
            SELECT slug, published_at
            FROM research_requests
            WHERE is_public = TRUE AND status = 'completed' AND slug IS NOT NULL
            ORDER BY published_at DESC NULLS LAST
        """)
    ).fetchall()
    for paper in paper_rows:
        lastmod = paper.published_at.strftime("%Y-%m-%d") if paper.published_at else today
        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{escape(f'{BASE_URL}/research/{paper.slug}')}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                "    <changefreq>monthly</changefreq>",
                "    <priority>0.9</priority>",
                "  </url>",
            ]
        )

    # --- News stories (crawlable /news-archive/{slug} pages) ---
    stories = (
        db.query(NewsItem.id, NewsItem.headline, NewsItem.created_at)
        .filter(NewsItem.post_text.isnot(None))
        .filter((NewsItem.news_category != "speculative") | (NewsItem.news_category.is_(None)))
        .order_by(NewsItem.created_at.desc())
        .all()
    )
    for story in stories:
        slug = story_slug(story.headline, story.id)
        lastmod = story.created_at.strftime("%Y-%m-%d") if story.created_at else today
        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{escape(f'{BASE_URL}/news-archive/{slug}')}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                "    <changefreq>yearly</changefreq>",
                "    <priority>0.6</priority>",
                "  </url>",
            ]
        )

    xml_parts.append("</urlset>")

    xml_content = "\n".join(xml_parts)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache for 1 day
        },
    )


@router.api_route("/sitemap-index.xml", methods=["GET", "HEAD"])
async def get_sitemap_index():
    """
    Generate sitemap index for large sites.
    Points to the main sitemap.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{BASE_URL}/sitemap.xml</loc>
    <lastmod>{today}</lastmod>
  </sitemap>
</sitemapindex>"""

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )
