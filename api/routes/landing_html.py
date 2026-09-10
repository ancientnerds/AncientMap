# SPDX-License-Identifier: AGPL-3.0-only
"""
GET /home — the homepage with live Stories / Journal / Papers sections.

nginx proxies "/" here (ancientnerds-nginx-config, location = /). The route
builds a {type: "landing"} payload from the DB, renders it through the SSR
sidecar into index.html's #root (api/seo_shell.py, same path as every other
indexed page), substitutes the live counts into the hero and caches the
document for 300 s. When the API or the sidecar is down nginx serves the
static index.html instead — the page stays up, the three sections are empty.

Since 2026-09-10 each section is a portal on the live page and nothing else
(owner: "Why do we still have the list of stories, journals and research
papers on the right side?"), so the payload is three counts and the Theo
line. The paper cards went the same way a day later ("The research paper
examples should be inside the portal, not below it"): /research/ renders
them and the portal shows that page. No row of any kind ships here, and
the queries behind them are gone with the lists that printed them.

Everything above `fetch_landing_data` is a pure function of rows and is
what tests/api/test_landing_html.py covers. Spec:
docs/superpowers/specs/2026-09-09-landing-live-sections-design.md
"""

from __future__ import annotations

import math
import re
import threading
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.news import get_news_stats
from api.routes.theo import get_current_research
from api.seo_shell import ssr_shell_response
from api.services.site_stats import get_site_stats
from pipeline.database import get_db
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE


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
_CACHE_TTL = 300.0
# (expires_at, document bytes) — one document per process; ~200 hits/day need
# no more. Bytes, not the Response object: GZipMiddleware writes
# Content-Encoding into the very raw_headers list a Response carries, so a
# cached object comes back on the next hit already labelled gzip and the
# middleware then passes the uncompressed body through untouched —
# ERR_CONTENT_DECODING_FAILED in the browser.
_cache: dict[str, tuple[float, bytes]] = {}
_cache_lock = threading.Lock()


def fetch_landing_data(db: Session) -> dict:
    """Every DB read of the route, in one place, so the route itself stays testable."""
    paper_total = (
        db.execute(
            # nosemgrep: semgrep.api-sql-fstring-interpolation -- PUBLIC_PAPER_WHERE is a module-level constant, no user input
            text(f"SELECT COUNT(*) FROM research_requests r WHERE {PUBLIC_PAPER_WHERE}")
        ).scalar()
        or 0
    )
    news_stats = get_news_stats(db)
    if not isinstance(news_stats, dict):  # cache_get returns the dict, a cold call the model
        news_stats = news_stats.model_dump()
    return {
        "paper_total": paper_total,
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
        papers = {"total": data["paper_total"], "theo": theo}
    return {
        "type": "landing",
        "stats": {
            "sites": site_stats["total_sites"],
            "stories": data["news_stats"]["total_items"],
            "journals": data["journal_total"],
            "papers": data["paper_total"],
        },
        # Both sections are their portal and a count: /articles.html lists the
        # issues, /research/ renders the paper cards.
        "journals": {"total": data["journal_total"]} if data["journal_total"] else None,
        "papers": papers,
    }


# HEAD too: uptime checks and link checkers probe the homepage with HEAD, and
# the static file answered it before this route took over "/".
@router.api_route("/home", methods=["GET", "HEAD"])
async def home(db: Session = Depends(get_db)):
    """The homepage document. nginx maps "/" here; see the module docstring."""
    with _cache_lock:
        hit = _cache.get("home")
        if hit and hit[0] > time.monotonic():
            return Response(content=hit[1], media_type="text/html", headers=_HTML_HEADERS)
    site_stats = get_site_stats()
    current = await get_current_research()
    route = build_route(fetch_landing_data(db), site_stats, current.get("running"))
    response = ssr_shell_response(
        "index.html", route, _HTML_HEADERS, postprocess=lambda html: apply_stats(html, site_stats)
    )
    with _cache_lock:
        _cache["home"] = (time.monotonic() + _CACHE_TTL, response.body)
    return response
