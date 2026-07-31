"""
SEO-friendly HTML pages for the public research library.

Serves full HTML pages (not JSON) for search engine crawling, mirroring
the /api/v1/research JSON endpoints. These routes live outside /api/ so
nginx proxies them directly (see ancientnerds-nginx-config).
"""

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.public_v1 import PAPER_SUMMARY_COLUMNS, paper_summary_kwargs
from pipeline.article_html_renderer import BASE_URL, render_404_html, render_medium_copy_html
from pipeline.database import get_db
from pipeline.research_html_renderer import (
    format_image_captions_medium,
    format_references_md,
    render_research_listing_html,
    render_research_paper_html,
    strip_leading_title_heading,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=1800"}

_PUBLIC_WHERE = "r.is_public = TRUE AND r.status = 'completed' AND r.slug IS NOT NULL"


@router.get("/research/")
async def research_listing(db: Session = Depends(get_db)):
    """HTML listing of all published research papers."""
    rows = db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS}
            FROM research_requests r
            WHERE {_PUBLIC_WHERE}
            ORDER BY r.published_at DESC NULLS LAST
        """)
    ).fetchall()

    papers = [paper_summary_kwargs(row) for row in rows]
    html = render_research_listing_html(papers)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)


def _fetch_paper(slug: str, db: Session):
    """Load one public paper row incl. report content, or None."""
    return db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS},
                   r.result_json::jsonb->>'published_report' AS published_report,
                   r.result_json::jsonb->>'report' AS report
            FROM research_requests r
            WHERE r.slug = :slug AND {_PUBLIC_WHERE}
        """),
        {"slug": slug},
    ).fetchone()


def _paper_404() -> Response:
    return Response(
        content=render_404_html("Paper"),
        media_type="text/html",
        status_code=404,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/research/{slug}")
async def research_paper_page(slug: str, db: Session = Depends(get_db)):
    """Full HTML research paper page by slug."""
    row = _fetch_paper(slug, db)
    if not row:
        return _paper_404()

    # The reviewed publication (rejected blocks hidden, edits substituted)
    # is what external consumers should see — same rule as /api/v1/research.
    content = row.published_report or row.report or ""

    html = render_research_paper_html(paper_summary_kwargs(row), content)
    return Response(content=html, media_type="text/html", headers=_HTML_HEADERS)


@router.get("/research/{slug}/medium")
async def research_medium_copy(slug: str, db: Session = Depends(get_db)):
    """Clean, light-themed paper page for copying into Medium's editor."""
    row = _fetch_paper(slug, db)
    if not row:
        return _paper_404()

    paper = paper_summary_kwargs(row)
    # Medium paste drops figcaption content — use the markdown-native caption
    # variant here; the SSR paper page keeps real <figure>/<figcaption>.
    content = format_image_captions_medium(
        format_references_md(
            strip_leading_title_heading(row.published_report or row.report or "", paper["title"])
        )
    )
    html = render_medium_copy_html(
        title=paper["title"],
        content_md=content,
        canonical_url=f"{BASE_URL}/research/{slug}",
        extra_footer_html=(
            f"<p><em>Read more open-access research papers in the "
            f'<a href="{BASE_URL}/research/">Ancient Nerds Research Library</a> '
            f"(CC BY 4.0).</em></p>"
        ),
    )
    return Response(content=html, media_type="text/html")
