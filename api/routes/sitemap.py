"""
Dynamic sitemap index + per-type part files for SEO.

/sitemap.xml is a sitemap INDEX referencing one part file per page type.
GSC's Sitemaps report lists each part separately, which makes the indexing
rate PER PAGE TYPE measurable for the first time (6,105 of ~7,400 pages
were not indexed as of the 2026-08-09 audit, with no way to tell which
type was failing).

nginx proxies /sitemap.xml and /sitemap-*.xml straight to these routes —
the deploy-time freeze into dist/sitemap.xml is gone, so new stories and
papers appear in the sitemap without a deploy.

Every URL carries <lastmod> where the data provides one (Google uses it to
prioritise recrawls). <changefreq>/<priority> are deliberately dropped:
Google documents that it ignores both.
"""

from datetime import datetime
from html import escape

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from api.routes.articles_html import STORIES_PER_PAGE, public_stories_query
from pipeline.article_html_renderer import slugify, story_slug
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db
from pipeline.sites_html_renderer import country_path, encode_path, site_path

router = APIRouter()

# Base URL for the site
BASE_URL = "https://ancientnerds.com"

#: One part file per page type; /sitemap.xml indexes exactly these.
SITEMAP_PARTS = ("static", "sites", "countries", "stories", "research", "articles")

# 1h: long enough that crawler bursts hit nginx/API caches, short enough
# that a freshly published story is advertised within the hour.
_HEADERS = {"Cache-Control": "public, max-age=3600"}


def _xml(content: str) -> Response:
    return Response(content=content, media_type="application/xml", headers=_HEADERS)


def _loc(path: str) -> str:
    """Absolute, percent-encoded, XML-escaped <loc> value for a raw site path.

    Sitemap URLs must be URL-escaped; ~600 site slugs and ~100 news/article
    slugs contain non-ASCII characters. Takes the UNENCODED path.
    """
    return escape(f"{BASE_URL}{encode_path(path)}")


def _url(path: str, lastmod: datetime | None) -> str:
    """One <url> element; lastmod only where the data actually provides one."""
    lastmod_xml = f"\n    <lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>" if lastmod else ""
    return f"  <url>\n    <loc>{_loc(path)}</loc>{lastmod_xml}\n  </url>"


def _urlset(urls: list[str], *, image_ns: bool = False) -> str:
    ns = ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' if image_ns else ""
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"{ns}>',
            *urls,
            "</urlset>",
        ]
    )


def _newest(lastmods: list[datetime | None]) -> datetime | None:
    return max((d for d in lastmods if d), default=None)


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def sitemap_index():
    """Sitemap index — robots.txt points here, the parts hang below it.

    No <lastmod> on the index entries: it would need one MAX query per part
    on every fetch just to describe files Google refetches cheaply anyway;
    the per-URL lastmod in the parts is the signal that matters.
    """
    entries = [
        f"  <sitemap>\n    <loc>{BASE_URL}/sitemap-{part}.xml</loc>\n  </sitemap>"
        for part in SITEMAP_PARTS
    ]
    return _xml(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
                *entries,
                "</sitemapindex>",
            ]
        )
    )


# Static entry pages. The crawlable hubs (/sites/, /news-archive/,
# /research/, /articles/) live in their per-type part files instead — no URL
# may appear in two parts. No lastmod: nothing in the data tracks when these
# shells change, and stamping "today" would falsely signal daily changes.
_STATIC_PAGES = (
    "/globe.html",
    "/news.html",
    "/lyra.html",
    "/radar.html",
    "/articles.html",
    "/search.html",
    "/theo.html",
    "/library.html",
    "/api.html",
)

_HOMEPAGE_URL = f"""  <url>
    <loc>{BASE_URL}/</loc>
    <image:image>
      <image:loc>{BASE_URL}/landing/og-image.png</image:loc>
      <image:title>Ancient Nerds Interactive Archaeological Research Platform</image:title>
      <image:caption>Explore over 750,000 archaeological sites worldwide on an interactive 3D globe</image:caption>
    </image:image>
  </url>"""


@router.api_route("/sitemap-static.xml", methods=["GET", "HEAD"])
async def sitemap_static():
    """Homepage + the static .html entry points."""
    urls = [_HOMEPAGE_URL] + [_url(path, None) for path in _STATIC_PAGES]
    return _xml(_urlset(urls, image_ns=True))


@router.api_route("/sitemap-sites.xml", methods=["GET", "HEAD"])
async def sitemap_sites(db: Session = Depends(get_db)):
    """All curated site detail pages (/sites/{country}/{slug}, ~5,000).

    Only Ancient Nerds Originals — the routes serve curated sites only, and
    bulk-imported sources would be hundreds of thousands of thin pages. The
    legacy /site.html?id={uuid} URLs stay deliberately unlisted: Google left
    all ~5,000 on "Discovered - currently not indexed" and never fetched one
    (URL Inspection, 2026-08-07).
    """
    rows = db.execute(
        text("""
            SELECT name, country, id, COALESCE(updated_at, created_at) AS lastmod
            FROM unified_sites
            WHERE source_id = 'ancient_nerds'
              AND country IS NOT NULL AND country != ''
            ORDER BY name
        """)
    ).fetchall()
    urls = [_url(site_path(row.country, row.name, row.id), row.lastmod) for row in rows]
    return _xml(_urlset(urls))


@router.api_route("/sitemap-countries.xml", methods=["GET", "HEAD"])
async def sitemap_countries(db: Session = Depends(get_db)):
    """The /sites/ hub + one URL per country listing (98 + 1).

    A country page changes when any of its sites does, so its lastmod is the
    newest curated site edit in that country; the hub takes the global max.
    """
    rows = db.execute(
        text("""
            SELECT country, MAX(COALESCE(updated_at, created_at)) AS lastmod
            FROM unified_sites
            WHERE source_id = 'ancient_nerds'
              AND country IS NOT NULL AND country != ''
            GROUP BY country
            ORDER BY country
        """)
    ).fetchall()
    urls = [_url("/sites/", _newest([row.lastmod for row in rows]))]
    urls += [_url(country_path(row.country), row.lastmod) for row in rows]
    return _xml(_urlset(urls))


@router.api_route("/sitemap-stories.xml", methods=["GET", "HEAD"])
async def sitemap_stories(db: Session = Depends(get_db)):
    """Story pages (~3,000) + the paginated archive listing.

    public_stories_query is the authoritative filter — /news-archive/{slug}
    serves exactly this set; any other query would advertise 404s (the
    sitemap did exactly that for speculative stories before 2026-08-09).
    lastmod is the video publish date — the story's real date — falling back
    to row creation, mirroring the pages' own published_at.
    """
    rows = (
        public_stories_query(db)
        .with_entities(
            NewsItem.id,
            NewsItem.headline,
            func.coalesce(NewsVideo.published_at, NewsItem.created_at).label("lastmod"),
        )
        .order_by(NewsItem.created_at.desc())
        .all()
    )
    newest = _newest([row.lastmod for row in rows])
    # Every archive page shifts when a story lands (offset pagination), so
    # the listing pages all carry the newest story date.
    total_pages = max(1, -(-len(rows) // STORIES_PER_PAGE))
    urls = [_url("/news-archive/", newest)]
    urls += [_url(f"/news-archive/page/{n}", newest) for n in range(2, total_pages + 1)]
    urls += [_url(f"/news-archive/{story_slug(row.headline, row.id)}", row.lastmod) for row in rows]
    return _xml(_urlset(urls))


@router.api_route("/sitemap-research.xml", methods=["GET", "HEAD"])
async def sitemap_research(db: Session = Depends(get_db)):
    """The /research/ hub + all published open-access papers."""
    rows = db.execute(
        text("""
            SELECT slug, COALESCE(published_at, created_at) AS lastmod
            FROM research_requests
            WHERE is_public = TRUE AND status = 'completed' AND slug IS NOT NULL
            ORDER BY published_at DESC NULLS LAST
        """)
    ).fetchall()
    urls = [_url("/research/", _newest([row.lastmod for row in rows]))]
    urls += [_url(f"/research/{row.slug}", row.lastmod) for row in rows]
    return _xml(_urlset(urls))


@router.api_route("/sitemap-articles.xml", methods=["GET", "HEAD"])
async def sitemap_articles(db: Session = Depends(get_db)):
    """The /articles/ hub + all weekly journals."""
    articles = db.query(NewsArticle).order_by(NewsArticle.created_at.desc()).all()
    entries = [(f"/articles/{slugify(a.title)}", a.published_at or a.created_at) for a in articles]
    urls = [_url("/articles/", _newest([lastmod for _, lastmod in entries]))]
    urls += [_url(path, lastmod) for path, lastmod in entries]
    return _xml(_urlset(urls))
