"""
SEO-friendly HTML site browser: /sites/, /sites/{country} and
/sites/{country}/{slug}.

These crawlable pages are the link path from the homepage down to each of
the ~5,000 curated site detail pages. Only Ancient Nerds Originals are
listed (same rule as the sitemap) — the bulk-imported 750K sites are
searchable via the app but not part of the crawl surface.

A retired site (E4, migration 0020) is not listed anywhere and its own URL
answers 410 Gone, like a withdrawn story.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.articles_html import public_stories_query
from api.seo_shell import ssr_shell_response
from api.services.description_provenance import card_ai, description_disclosure
from pipeline.article_html_renderer import render_error_html
from pipeline.database import NewsItem, get_db
from pipeline.sites_html_renderer import (
    country_path,
    country_slug,
    encode_path,
    site_id_prefix_from_slug,
    site_id_short,
    site_path,
    site_slug,
)
from pipeline.utils.card_provenance import validate as validate_card_provenance
from pipeline.utils.public_sites import RETIRED, curated_page, not_retired
from pipeline.utils.slugs import story_slug

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=3600"}

_CURATED_WHERE = curated_page()

# Plain concatenation of two module constants — the id is bound, never formatted in.
_LEGACY_SITE_SQL = text(
    "SELECT name, country FROM unified_sites WHERE id::text = :id AND " + _CURATED_WHERE
)

_PARENT_SQL = text(
    "SELECT id::text AS id, name FROM unified_sites WHERE id::text = :pid AND " + not_retired()
)

# Hub slugs that existed and were retired by a data correction, mapped to the hub that
# carries their sites now. The homepage hub list baked on 2026-09-05 still links both,
# and both answered 404 on 2026-09-22 (the country corrections moved every Georgia and
# Easter Island site). A 301 hands their link signals to the hub that replaced them.
# /sites/united-kingdom is deliberately NOT here: the UK lane splits those rows into
# England / Scotland / Wales / Northern Ireland, so no single hub replaces it. Until that
# lane has moved them it is a live hub (6 curated rows still carried 'United Kingdom' and
# the page answered 200 on 2026-09-23); afterwards it answers 404, never a 301
# (tests/api/test_sites_html_scope.py pins both).
_RETIRED_HUBS = {
    "georgia-country": "georgia",
    "chile-easter-island": "chile",
}


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

    # Since react-ssr Task 10 the sidecar renders head and body from this
    # payload (sitesIndexMeta + SitesIndexPage); Python only fetches data.
    return ssr_shell_response(
        "site.html",
        {
            "type": "sitesIndex",
            "countries": [
                {"name": row.country, "count": row.count, "path": country_path(row.country)}
                for row in rows
            ],
        },
        _HTML_HEADERS,
    )


@router.get("/sites/{slug}")
async def sites_by_country(slug: str, db: Session = Depends(get_db)):
    """All curated sites of one country, matched by country slug."""
    rows = db.execute(
        # nosemgrep: semgrep.api-sql-fstring-interpolation -- _CURATED_WHERE is a module-level constant, no user input
        text(f"SELECT DISTINCT country FROM unified_sites WHERE {_CURATED_WHERE}")
    ).fetchall()
    wanted = slug.lower()
    country = next((row.country for row in rows if country_slug(row.country) == wanted), None)

    if not country and wanted in _RETIRED_HUBS:
        return RedirectResponse(url=f"/sites/{_RETIRED_HUBS[wanted]}", status_code=301)
    if not country:
        return Response(
            content=render_error_html("Country"),
            media_type="text/html",
            status_code=404,
            headers={"Cache-Control": "public, max-age=300"},
        )
    # Case variants (/sites/Turkey) are the same hub: one 301 to the slug the
    # sitemap lists, like the detail route does for its country segment.
    if slug != country_slug(country):
        return RedirectResponse(url=f"/sites/{country_slug(country)}", status_code=301)

    # thumbnail_url still points at upload.wikimedia.org for 1,710 of 5,004
    # curated sites, and Wikimedia answers the Googlebot UA with 403 — so
    # Google Images never saw 43 % of the hub thumbnails (render audit
    # 2026-09-15). 1,501 of those sites have a downloaded hero in wiki_images;
    # the hub uses it, with the same pick the detail page makes.
    site_rows = db.execute(
        text(f"""
            SELECT u.id::text AS id, u.name, u.site_type, u.period_name, u.period_start,
                   u.description, u.thumbnail_url, h.filename AS hero_filename
            FROM unified_sites u
            LEFT JOIN LATERAL (
                SELECT w.filename
                FROM wiki_images w
                WHERE w.site_id = u.id AND (w.is_excluded = false OR w.is_excluded IS NULL)
                ORDER BY w.is_hero DESC, w.is_lead DESC, w.sort_order
                LIMIT 1
            ) h ON true
            WHERE {_CURATED_WHERE} AND u.country = :country
            ORDER BY u.name
        """),
        {"country": country},
    ).fetchall()

    sites = [
        {
            "name": row.name,
            "description": row.description,
            "path": site_path(country, row.name, row.id),
            # Type, period and hero feed the React cards; thumbnail_url is the
            # local hero webp the image downloader already writes per site —
            # no join needed.
            "site_type": row.site_type,
            "period_name": row.period_name,
            "period_start": row.period_start,
            "thumbnail_url": (
                f"/data/images/wiki/{site_id_short(row.id)}/{row.hero_filename}"
                if row.hero_filename
                else row.thumbnail_url
            ),
        }
        for row in site_rows
    ]
    # The raw rows go through as-is; grouping, period span and blurbs are
    # display decisions and live in src/seo/grouping.ts since react-ssr
    # Task 10 (countryMeta and CountrySitesPage share one definition).
    return ssr_shell_response(
        "site.html",
        {"type": "country", "country": country, "sites": sites},
        _HTML_HEADERS,
    )


@router.get("/site.html")
async def legacy_site_redirect(
    id: str = "",
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    db: Session = Depends(get_db),
):
    """
    301 the legacy /site.html?id={uuid} URL to its canonical slug URL.

    Shared links and bookmarks keep working, and Google consolidates the
    ranking signals on one URL per site instead of two. The built
    site.html shell is still read from disk to serve /sites/{country}/{slug} —
    only this HTTP path is redirected.

    Drei Fälle, weil es drei ehrliche Antworten gibt:

    * kuratiert  → die Detailseite. Das ist dieselbe Sache unter neuer URL.
    * existiert, aber nicht kuratiert → der Globus, auf den Datensatz
      zentriert. /sites/ war hier bis 12.09.2026 die Antwort, und das ist
      eine Weiterleitung auf eine NICHT gleichwertige Seite — Google wertet
      so etwas wie einen Soft 404, und der Besucher landete auf einer
      generischen Länderliste statt bei seiner Fundstätte. Die
      Fragment-Form erzeugt keine zweite crawlbare URL (brand.ts).
    * unbekannte id → 404. Eine Weiterleitung würde behaupten, es gäbe die
      Sache woanders.
    """
    if not id:
        return _site_404()
    # utm_* survives the hop: the Discord bot tags its links and Umami's UTM
    # report attributes the visit only if the tag reaches the final page.
    utm = urlencode(
        {
            k: v
            for k, v in (
                ("utm_source", utm_source),
                ("utm_medium", utm_medium),
                ("utm_campaign", utm_campaign),
            )
            if v
        }
    )
    query = f"?{utm}" if utm else ""
    row = db.execute(_LEGACY_SITE_SQL, {"id": id}).fetchone()
    if row:
        target = encode_path(site_path(row.country, row.name, id))
        return RedirectResponse(url=f"{target}{query}", status_code=301)
    exists = db.execute(
        text("SELECT scope_status FROM unified_sites WHERE id::text = :id"), {"id": id}
    ).fetchone()
    if exists and exists.scope_status == RETIRED:
        return _site_410()
    if exists:
        return RedirectResponse(url=f"/globe.html{query}#focus={id}", status_code=301)
    return _site_404()


def _site_404() -> Response:
    return Response(
        content=render_error_html("Site"),
        media_type="text/html",
        status_code=404,
        headers={"Cache-Control": "public, max-age=300"},
    )


def _site_410() -> Response:
    """A retired site (E4): it existed and was withdrawn on purpose.

    Same answer and cache lifetime as a withdrawn story (articles_html.story_page):
    Google drops a 410 far faster than a 404. No reason is named - scope_reason is for
    the reviewer, not the public page.
    """
    return Response(
        content=render_error_html("Site", 410, "This site has been withdrawn."),
        media_type="text/html",
        status_code=410,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _site_by_prefix(prefix: str, db: Session):
    """The (id, scope_status) row of a site with this 8-hex prefix, or None.

    Reached when no shown curated site matches: the row is either an uncurated site
    (lives on the globe only) or a retired one (answers 410). A retired row wins a
    prefix shared with another row - the URL asked for a page, and the page is gone.

    A range query on the primary-key column instead of
    `LEFT(REPLACE(id::text, '-', ''), 8) = :prefix`: the prefix is exactly the first UUID
    group, but as an expression over 1.7 million rows it would be a sequential scan on
    every 404 - and anyone can trigger a 404.
    """
    return db.execute(
        text("""
            SELECT id::text AS id, scope_status FROM unified_sites
            WHERE id >= CAST(:lo AS uuid) AND id <= CAST(:hi AS uuid)
            ORDER BY (scope_status IS NOT DISTINCT FROM 'retired') DESC
            LIMIT 1
        """),
        {
            "lo": f"{prefix}-0000-0000-0000-000000000000",
            "hi": f"{prefix}-ffff-ffff-ffff-ffffffffffff",
        },
    ).fetchone()


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

    # card_stats carries the enrichment metadata (non-English wiki source,
    # description citations live in raw_data) that the interactive record
    # shows — /api/sites/{id} serves the same fields, and since react-ssr
    # Task 11 the payload replaces that fetch entirely. No column in
    # card_stats collides with the unqualified names in _CURATED_WHERE.
    row = db.execute(
        text(f"""
            SELECT id::text AS id, name, country, site_type, period_name,
                   period_start, period_end, description, lat, lon, source_url,
                   parent_site_id::text AS parent_site_id,
                   raw_data -> 'description_citations' AS description_citations,
                   raw_data -> '_description_provenance' AS description_provenance,
                   raw_data -> '_card_provenance' AS card_provenance,
                   cs.best_wiki_url, cs.source_language, cs.card_description
            FROM unified_sites
            LEFT JOIN card_stats cs ON cs.site_id = unified_sites.id
            WHERE {_CURATED_WHERE} AND LEFT(REPLACE(id::text, '-', ''), 8) = :prefix
            LIMIT 1
        """),
        {"prefix": prefix},
    ).fetchone()

    if not row:
        # Kein kuratierter Treffer heisst nicht "gibt es nicht": die Fundstätte
        # kann aus einem Massenimport stammen und nur auf dem Globus leben.
        # Google fand solche URLs im Altbestand (z. B. tell-el-hammam-b7cd329f,
        # wikidata) und bekam bis 12.09.2026 einen 404 auf einen existierenden
        # Datensatz. Gleiche Antwort wie bei /site.html?id= — ein Ziel, das es
        # wirklich gibt.
        other = _site_by_prefix(prefix, db)
        if other and other.scope_status == RETIRED:
            return _site_410()
        if other:
            return RedirectResponse(url=f"/globe.html#focus={other.id}", status_code=301)
        return _site_404()

    canonical_country = country_slug(row.country)
    canonical_slug = site_slug(row.name, row.id)
    if country != canonical_country or slug != canonical_slug:
        return RedirectResponse(url=f"/sites/{canonical_country}/{canonical_slug}", status_code=301)

    # The raw row goes through as-is (snake_case, no display formatting —
    # period/coordinate rendering lives in src/seo/display.ts), plus the
    # related content with ready-built paths. Since react-ssr Task 11 this
    # payload is everything SitePage needs: head (siteMeta), crawler body
    # (SiteRecord) and the interactive SitePopup all render without a fetch.
    # The disclosure (AI mark and CC BY-SA attribution) is derived by the one
    # function /api/sites/{id} uses, and only for the text the provenance hashes.
    disclosure = description_disclosure(row.description_provenance, row.description)
    # The card is not on the page, but the SiteCard that opens the page carries it: a teaser
    # card is AI-generated (lane WB, owner decision O10), so the page shows the AI footnote
    # for it as well - derived by the one function /api/sites/{id} uses.
    teaser = row.card_provenance
    marked_card = card_ai(
        row.description_provenance,
        None if teaser is None else validate_card_provenance(teaser),
        row.card_description,
    )
    return ssr_shell_response(
        "site.html",
        {
            "type": "site",
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
            "best_wiki_url": row.best_wiki_url,
            "source_language": row.source_language,
            "description_citations": row.description_citations,
            "description_ai": None if disclosure is None else disclosure["ai"],
            "description_attribution": None if disclosure is None else disclosure["attribution"],
            "card_ai": marked_card,
            **_related_content(row, db),
        },
        _HTML_HEADERS,
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
            SELECT filename, author, license, commons_page_url, width, height
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
            # NULL, solange scripts/backfill_image_dimensions.py für die Zeile
            # nicht gelaufen ist — SiteRecord lässt die Attribute dann weg,
            # statt eine falsche Zahl zu raten.
            "width": img_row.width,
            "height": img_row.height,
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
        p = db.execute(_PARENT_SQL, {"pid": row.parent_site_id}).fetchone()
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
