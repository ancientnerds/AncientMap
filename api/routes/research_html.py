"""
SEO-friendly HTML pages for the public research library.

Serves full HTML pages (not JSON) for search engine crawling, mirroring
the /api/v1/research JSON endpoints. These routes live outside /api/ so
nginx proxies them directly (see ancientnerds-nginx-config).
"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.public_v1 import PAPER_SUMMARY_COLUMNS, PUBLIC_PAPER_WHERE, paper_summary_kwargs
from api.seo_shell import ssr_shell_response
from pipeline.article_html_renderer import (
    BASE_URL,
    markdown_to_html,
    render_404_html,
    render_medium_copy_html,
)
from pipeline.database import get_db
from pipeline.research_html_renderer import (
    format_image_captions_medium,
    format_references_md,
    strip_leading_title_heading,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_HTML_HEADERS = {"Cache-Control": "public, max-age=1800"}


@router.get("/research.html")
async def legacy_research_redirect(slug: str = ""):
    """301 the legacy /research.html?slug=… entry URL to /research/{slug}."""
    target = f"/research/{quote(slug)}" if slug else "/theo.html#research-library"
    return RedirectResponse(url=target, status_code=301)


@router.get("/research/")
async def research_listing(db: Session = Depends(get_db)):
    """HTML listing of all published research papers."""
    rows = db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS}
            FROM research_requests r
            WHERE {PUBLIC_PAPER_WHERE}
            ORDER BY r.published_at DESC NULLS LAST
        """)
    ).fetchall()

    # Since react-ssr Task 12 the sidecar renders head and body from this
    # payload (researchIndexMeta + ResearchIndexPage); Python only fetches
    # data. The cards need slug, title and summary — nothing more.
    papers = [paper_summary_kwargs(row) for row in rows]
    return ssr_shell_response(
        "research.html",
        {
            "type": "researchIndex",
            "papers": [
                {"slug": p["slug"], "title": p["title"], "summary": p["summary"]} for p in papers
            ],
        },
        _HTML_HEADERS,
    )


def _fetch_paper(slug: str, db: Session):
    """Load one public paper row incl. report content, or None."""
    return db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS},
                   r.result_json::jsonb->>'published_report' AS published_report,
                   r.result_json::jsonb->>'report' AS report
            FROM research_requests r
            WHERE r.slug = :slug AND {PUBLIC_PAPER_WHERE}
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


def _report_markdown(row, title: str) -> str:
    """The stored report, prepared for rendering — shared by paper page and Medium copy.

    The reviewed publication (rejected blocks hidden, edits substituted) is
    what external consumers should see — same rule as /api/v1/research. On
    top of that, two storage quirks are fixed here: papers open with their
    own title as a markdown heading (3 of 16 live papers use '# Title',
    which rendered a second <h1> next to the page's own), and Theo emits
    References as consecutive plain-text lines with bare URLs that markdown
    collapses into one dead-link paragraph.
    """
    return format_references_md(
        strip_leading_title_heading(row.published_report or row.report or "", title)
    )


@router.get("/research/{slug}")
async def research_paper_page(slug: str, db: Session = Depends(get_db)):
    """Full HTML research paper page by slug."""
    row = _fetch_paper(slug, db)
    if not row:
        return _paper_404()

    # Raw snake_case row fields (react-ssr Task 12); date formatting and
    # author defaults are display decisions and live in src/seo/. body_html
    # stays Python-markdown on purpose (nh3-sanitized in markdown_to_html) —
    # React injects the finished HTML instead of re-rendering the markdown.
    paper = paper_summary_kwargs(row)
    return ssr_shell_response(
        "research.html",
        {
            "type": "research",
            "slug": paper["slug"],
            "title": paper["title"],
            "summary": paper["summary"],
            "author": paper["author"],
            "published_at": paper["published_at"],
            "hero_image_url": paper["hero_image_url"],
            "body_html": markdown_to_html(_report_markdown(row, paper["title"])),
        },
        _HTML_HEADERS,
    )


@router.get("/research/{slug}/medium")
async def research_medium_copy(slug: str, db: Session = Depends(get_db)):
    """Clean, light-themed paper page for copying into Medium's editor."""
    row = _fetch_paper(slug, db)
    if not row:
        return _paper_404()

    paper = paper_summary_kwargs(row)
    # On top of the shared preparation: Medium's editor drops figcaption
    # content on paste, so captions become markdown-native italic paragraphs
    # here (the paper page leaves image blocks as plain markdown).
    content = format_image_captions_medium(_report_markdown(row, paper["title"]))
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
