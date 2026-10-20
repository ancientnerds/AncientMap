# SPDX-License-Identifier: AGPL-3.0-only
"""
GET /home — the homepage with live Stories / Journal / Papers / Sites sections.

nginx proxies "/" here (ancientnerds-nginx-config, location = /). The route
builds a {type: "landing"} payload from the DB, renders it through the SSR
sidecar into index.html's #root (api/seo_shell.py, same path as every other
indexed page), substitutes the live counts into the hero and caches the
document in Redis: fresh for 300 s, and a visitor never waits for a rebuild
while a copy exists (see _FRESH_S). When the API or the sidecar is down nginx
serves the static index.html instead — the page stays up, the four sections
are empty.

Since 2026-09-10 each section is a portal on the live page and nothing else
(owner: "Why do we still have the list of stories, journals and research
papers on the right side?"), so the payload is four counts and the Theo
line. The paper cards went the same way a day later ("The research paper
examples should be inside the portal, not below it"): /research/ renders
them and the portal shows that page. No row of any kind ships here, and
the queries behind them are gone with the lists that printed them.

Everything above `fetch_landing_data` is a pure function of rows and is
what tests/api/test_landing_html.py covers. Spec:
docs/superpowers/specs/2026-09-09-landing-live-sections-design.md
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete, cache_get_bytes, cache_set_bytes
from api.routes.news import get_news_stats
from api.routes.theo import get_current_research
from api.seo_shell import ssr_shell_response
from api.services.site_stats import get_site_stats
from pipeline.app_shell import entry_version
from pipeline.article_html_renderer import render_error_html
from pipeline.database import get_db, get_session
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE

logger = logging.getLogger(__name__)

# The newest papers the research portal links by title (owner, 2026-10-09). Since
# 2026-09-10 papers hung on /research/ alone, which Googlebot fetched once in 14
# days, and it fetched none of the ten newest papers (SEO audit 2026-10-08): a text
# link from the homepage, which Google fetches often, is how a new paper is found.
LATEST_PAPERS = 5


def sites_compact(n: int) -> str:
    """1759673 → "1.76M", 999999 → "999K" (hero counter)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    return f"{n // 1_000}K"


def sites_long(n: int) -> str:
    """1759673 → "1.7 million" (floored, for the h1)."""
    return f"{math.floor(n / 100_000) / 10:.1f} million"


def apply_stats(html: str, stats: dict) -> str:
    """Replace the text of every element carrying data-stat="…" in the shell."""
    values = {
        "sites": sites_compact(stats["total_sites"]),
        "sites-long": sites_long(stats["total_sites"]),
        "countries": str(stats["curated_countries"]),
    }
    for key, value in values.items():
        html, hits = re.subn(rf'(data-stat="{key}"[^>]*>)[^<]*(<)', rf"\g<1>{value}\g<2>", html)
        if not hits:
            raise ValueError(f'index.html has no data-stat="{key}" marker')
    return html


router = APIRouter()
_HTML_HEADERS = {"Cache-Control": "public, max-age=300"}

# The document cache. Until 2026-10-20 it was one copy per API process, valid
# 300 s, rebuilt inside the request that found it expired. Measured that day
# (TTFB audit, output/seo-audit-2026-10-19/ttfb.md): a rebuild cost 0.79-1.04 s
# when the site counts were cold too (get_site_stats 606-643 ms, news counts
# 78-152 ms, SSR 2-3 ms) and 0.09 s when they were warm, and replayed over the
# 868 browser requests for "/" of 2026-10-05..20 in the nginx log, 41 % of
# them waited for one (23 % the slow kind): nginx spreads "/" over two
# processes, so each kept its own copy, and at ~58 browser visits a day most
# copies had expired. Now there is one copy in Redis for both processes, keyed
# by the shell's build (a deploy never serves the previous build's document),
# and a copy older than _FRESH_S is still served while one task per process
# rebuilds it in the background. A visitor waits only when no copy exists:
# after a deploy, a Redis flush, or _KEEP_S without any request ("/" draws
# ~730 requests a day, crawlers included).
#
# Bytes, not the Response object: GZipMiddleware writes Content-Encoding into
# the very raw_headers list a Response carries, so a cached object comes back
# on the next hit already labelled gzip and the middleware then passes the
# uncompressed body through untouched — ERR_CONTENT_DECODING_FAILED in the
# browser.
_FRESH_S = 300.0
_KEEP_S = 3600
_DOC_KEY = "landing:home:{build}"
# The rebuild in flight in this process (a strong reference: the event loop
# keeps only weak ones). At most one; both processes may rebuild at once.
_refreshing: set[asyncio.Task] = set()


def _pack(built_at: float, body: bytes) -> bytes:
    return f"{built_at:.3f}\n".encode() + body


def _unpack(raw: bytes) -> tuple[float, bytes]:
    stamp, body = raw.split(b"\n", 1)
    return float(stamp), body


def fetch_landing_data(db: Session) -> dict:
    """Every DB read of the route, in one place, so the route itself stays testable."""
    paper_total = (
        db.execute(
            # nosemgrep: semgrep.api-sql-fstring-interpolation -- PUBLIC_PAPER_WHERE is a module-level constant, no user input
            text(f"SELECT COUNT(*) FROM research_requests r WHERE {PUBLIC_PAPER_WHERE}")
        ).scalar()
        or 0
    )
    latest_papers = [
        {"slug": r.slug, "title": r.title}
        for r in db.execute(
            # nosemgrep: semgrep.api-sql-fstring-interpolation -- PUBLIC_PAPER_WHERE is a module-level constant, no user input
            text(f"""
                SELECT r.slug, COALESCE(r.result_json::jsonb->>'title', r.question) AS title
                FROM research_requests r
                WHERE {PUBLIC_PAPER_WHERE}
                ORDER BY r.published_at DESC NULLS LAST
                LIMIT :n
            """),
            {"n": LATEST_PAPERS},
        ).fetchall()
    ]
    news_stats = get_news_stats(db)
    if not isinstance(news_stats, dict):  # cache_get returns the dict, a cold call the model
        news_stats = news_stats.model_dump()
    return {
        "paper_total": paper_total,
        "latest_papers": latest_papers,
        "journal_total": news_stats["total_articles"],
        "news_stats": news_stats,
    }


def build_route(data: dict, site_stats: dict, theo_running: dict | None) -> dict:
    """Counts → the {type: "landing"} payload. A section whose source is empty
    stays None and is not rendered at all — no placeholder content."""
    papers = None
    if data["paper_total"]:
        theo = None
        if theo_running:
            theo = {
                "question": theo_running["question"],
                "started_at": theo_running["started_at"],
                "sites_found": theo_running["sites_found"],
            }
        papers = {"total": data["paper_total"], "theo": theo, "latest": data["latest_papers"]}
    return {
        "type": "landing",
        "stats": {
            "sites": site_stats["total_sites"],
            # Distinct source ids in unified_sites — the by_source keys /api/stats
            # hands out, so the site-search status line and the API agree.
            "sources": len(site_stats["by_source"]),
            "stories": data["news_stats"]["total_items"],
            "journals": data["journal_total"],
            "papers": data["paper_total"],
        },
        # Both sections are their portal and a count: /articles.html lists the
        # issues, /research/ renders the paper cards.
        "journals": {"total": data["journal_total"]} if data["journal_total"] else None,
        "papers": papers,
    }


def _render_document(db: Session, theo_running: dict | None) -> bytes:
    """Every blocking step of a build: the DB counts, the SSR render, the hero."""
    site_stats = get_site_stats()
    route = build_route(fetch_landing_data(db), site_stats, theo_running)
    response = ssr_shell_response(
        "index.html", route, _HTML_HEADERS, postprocess=lambda html: apply_stats(html, site_stats)
    )
    return bytes(response.body)


async def _build_and_store(key: str, db: Session) -> bytes:
    current = await get_current_research()
    # In a worker thread: a build blocks for up to a second, and on the event
    # loop it stalled every other request of this process meanwhile.
    body = await asyncio.to_thread(_render_document, db, current.get("running"))
    cache_set_bytes(key, _pack(time.time(), body), ttl=_KEEP_S)
    return body


async def _refresh(key: str) -> None:
    try:
        # Its own session: the request's closes with the response already sent.
        with get_session() as db:
            await _build_and_store(key, db)
    except Exception:
        # No older and older homepage behind a broken build: dropping the copy
        # hands the next request the build itself, and with it the error (502,
        # which nginx answers with the static index.html, location = /).
        logger.exception("Homepage rebuild failed; dropped the cached document")
        cache_delete(key)


# HEAD too: uptime checks and link checkers probe the homepage with HEAD, and
# the static file answered it before this route took over "/".
@router.api_route("/home", methods=["GET", "HEAD"])
async def home(db: Session = Depends(get_db)):
    """The homepage document. nginx maps "/" here; see the module docstring."""
    key = _DOC_KEY.format(build=entry_version("index.html"))
    raw = cache_get_bytes(key)
    if raw is None:
        body = await _build_and_store(key, db)
    else:
        built_at, body = _unpack(raw)
        if time.time() - built_at >= _FRESH_S and not _refreshing:
            task = asyncio.create_task(_refresh(key))
            _refreshing.add(task)
            task.add_done_callback(_refreshing.discard)
    return Response(content=body, media_type="text/html", headers=_HTML_HEADERS)


@router.api_route("/not-found", methods=["GET", "HEAD"])
async def not_found_page() -> Response:
    """404 for every path no other nginx location serves (location @not_found).

    Until 2026-09-17 nginx fell back to index.html there, so a mistyped or
    retired URL answered 200 with the homepage shell -- a soft 404 for each
    of them. Same error shell and cache window as the 404s of the SSR routes.
    """
    return Response(
        content=render_error_html("Page"),
        media_type="text/html",
        status_code=404,
        headers={"Cache-Control": "public, max-age=300"},
    )
