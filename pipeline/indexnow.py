# SPDX-License-Identifier: AGPL-3.0-only
"""IndexNow: tell Bing (and Yandex, Seznam, Naver, Yep) about new and changed
pages the moment they exist, instead of waiting for the next crawl.

Why: ChatGPT search, Copilot and DuckDuckGo answer from the Bing index, and
bingbot fetched a sixth of what Googlebot did in the August 2026 audit. One
POST per change puts a new story or paper in front of Bing within the hour.
Google does not take part; its path stays sitemap + crawl.

The key is public by design — the protocol proves ownership by serving
``/{key}.txt`` from the domain, so it lives in the frontend's public/ folder
and in this module (tests/pipeline/test_indexnow.py keeps the two in sync).

Who calls submit():
- the Lyra orchestrator step ``indexnow`` (submit_recent, every cycle):
  stories, papers, journals and curated sites that became public or changed
  in the last WINDOW, built from the same rules as the sitemap parts;
- the paper publish/unpublish routes and the worker's auto-publish, and the
  weekly journal generator, right after their commit (one URL each);
- scripts/indexnow_submit.py for the one-off bulk submission and by hand.

Fail-soft like api.services.notify: a rejected or unreachable endpoint is
logged and never breaks the caller. Re-submitting a URL is allowed by the
protocol, so overlapping windows are harmless.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import NewsArticle, NewsItem, get_session
from pipeline.news_visibility import public_story_criteria
from pipeline.sites_html_renderer import encode_path, site_path
from pipeline.utils.slugs import BASE_URL, slugify, story_slug

logger = logging.getLogger(__name__)

INDEXNOW_KEY = "fd469cc4e21cf3949e997e570dbc7b6b"
HOST = "ancientnerds.com"
ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_FILE = (
    Path(__file__).resolve().parent.parent / "ancient-nerds-map" / "public" / f"{INDEXNOW_KEY}.txt"
)

#: Protocol maximum per POST.
CHUNK = 10_000

#: The orchestrator cycles hourly (CYCLE_INTERVAL); two hours means every
#: change is announced once or twice, never missed between cycles.
WINDOW = timedelta(hours=2)


def page_url(path: str) -> str:
    """Absolute, percent-encoded URL for a raw site path (slugs carry non-ASCII)."""
    return f"{BASE_URL}{encode_path(path)}"


def submit(urls: Iterable[str]) -> bool:
    """POST the URLs to IndexNow in chunks of CHUNK. True when every chunk was
    accepted (200 or 202); False on any rejection or network error, logged.
    Never raises."""
    unique = list(dict.fromkeys(u for u in urls if u))
    if not unique:
        return True
    ok = True
    for start in range(0, len(unique), CHUNK):
        chunk = unique[start : start + CHUNK]
        payload = {
            "host": HOST,
            "key": INDEXNOW_KEY,
            "keyLocation": f"{BASE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": chunk,
        }
        try:
            resp = httpx.post(ENDPOINT, json=payload, timeout=10.0)
        except Exception as exc:
            logger.warning("[indexnow] %d URLs not submitted: %s", len(chunk), exc)
            ok = False
            continue
        if resp.status_code in (200, 202):
            logger.info("[indexnow] %d URLs accepted (HTTP %d)", len(chunk), resp.status_code)
        else:
            logger.warning(
                "[indexnow] %d URLs rejected: HTTP %d %s",
                len(chunk),
                resp.status_code,
                resp.text[:200],
            )
            ok = False
    return ok


def paths_for(
    stories: Iterable[tuple[int, str]],
    papers: Iterable[str],
    journals: Iterable[str],
    sites: Iterable[tuple[str, str, str]],
) -> list[str]:
    """Site paths for changed content, each group followed by its hub page
    (the listing changed too). stories = (id, headline), papers = slug,
    journals = title, sites = (country, name, id)."""
    paths: list[str] = []
    story_paths = [
        f"/news-archive/{story_slug(headline, item_id)}" for item_id, headline in stories
    ]
    paper_paths = [f"/research/{slug}" for slug in papers]
    journal_paths = [f"/articles/{slugify(title)}" for title in journals]
    site_paths = [site_path(country, name, site_id) for country, name, site_id in sites]
    for group, hub in (
        (story_paths, "/news-archive/"),
        (paper_paths, "/research/"),
        (journal_paths, "/articles/"),
        (site_paths, "/sites/"),
    ):
        if group:
            paths += group + [hub]
    return paths


def recent_public_paths(session: Session, since: datetime) -> list[str]:
    """What became public or changed since ``since``, by the sitemap's rules:
    public_story_criteria for stories, is_public + slug for papers, every
    journal, curated sites with a country."""
    stories = (
        session.query(NewsItem.id, NewsItem.headline)
        .filter(*public_story_criteria(), NewsItem.created_at >= since)
        .all()
    )
    papers = session.execute(
        text("""
            SELECT slug FROM research_requests
            WHERE is_public = TRUE AND status = 'completed' AND slug IS NOT NULL
              AND published_at >= :since
        """),
        {"since": since},
    ).fetchall()
    journals = session.query(NewsArticle.title).filter(NewsArticle.created_at >= since).all()
    sites = session.execute(
        text("""
            SELECT country, name, id FROM unified_sites
            WHERE source_id = 'ancient_nerds' AND country IS NOT NULL AND country != ''
              AND COALESCE(updated_at, created_at) >= :since
        """),
        {"since": since},
    ).fetchall()
    return paths_for(
        [(row.id, row.headline) for row in stories],
        [row.slug for row in papers],
        [row.title for row in journals],
        [(row.country, row.name, str(row.id)) for row in sites],
    )


def submit_recent() -> int:
    """Orchestrator step: announce everything from the last WINDOW. Returns
    the number of URLs submitted (0 when nothing changed)."""
    since = datetime.now(UTC) - WINDOW
    with get_session() as session:
        paths = recent_public_paths(session, since)
    if not paths:
        return 0
    submit(page_url(path) for path in paths)
    return len(paths)
