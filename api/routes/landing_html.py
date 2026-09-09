# SPDX-License-Identifier: AGPL-3.0-only
"""
GET /home — the homepage with live Stories / Journal / Papers sections.

nginx proxies "/" here (ancientnerds-nginx-config, location = /). The route
builds a {type: "landing"} payload from the DB, renders it through the SSR
sidecar into index.html's #root (api/seo_shell.py, same path as every other
indexed page), substitutes the live counts into the hero and caches the
document for 300 s. When the API or the sidecar is down nginx serves the
static index.html instead — the page stays up, the three sections are empty.

Everything above `fetch_landing_data` is a pure function of rows and is
what tests/api/test_landing_html.py covers. Spec:
docs/superpowers/specs/2026-09-09-landing-live-sections-design.md
"""

from __future__ import annotations

import math
import re
import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from api.routes.articles_html import public_stories_query
from api.routes.news import get_news_stats
from api.routes.public_v1 import PAPER_SUMMARY_COLUMNS, paper_summary_kwargs
from api.routes.theo import get_current_research
from api.seo_shell import ssr_shell_response
from api.services.site_stats import get_site_stats
from pipeline.article_html_renderer import slugify, story_slug
from pipeline.database import NewsArticle, NewsItem, NewsVideo, get_db
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE

MAX_SUMMARY = 180
WORDS_PER_MINUTE = 238
LEAD_WINDOW = timedelta(hours=48)
CATEGORY_WINDOW = timedelta(days=30)
RAIL_ROWS = 6
RECENT_ROWS = 7
APPENDIX_SECTIONS = {"sources", "videos"}

_TRAILING_URL = re.compile(r"\s*https?://\S+\s*$")
_SENTENCE = re.compile(r"^.*?[.!?](?=\s|$)")
_HEADING = re.compile(r"^##+\s+(.+?)\s*$", re.MULTILINE)
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
_LINK = re.compile(r"https?://")


def first_sentence(post_text: str | None) -> str:
    """First sentence of the story post, for the card summary.

    Same rule as ancient-nerds-map/src/landing/feedClient.ts::firstSentence:
    trailing source links off the *whole* text (splitPostText strips them
    before it splits paragraphs), first paragraph, first sentence, whitespace
    collapsed, cut at 180 on a word boundary. A refetched card must read
    exactly like a server-rendered one.
    """
    if not post_text:
        return ""
    body = post_text.strip()
    while _TRAILING_URL.search(body):
        body = _TRAILING_URL.sub("", body)
    paragraph = next((line for line in (raw.strip() for raw in body.split("\n")) if line), "")
    match = _SENTENCE.match(paragraph)
    sentence = " ".join((match.group(0) if match else paragraph).split())
    if len(sentence) <= MAX_SUMMARY:
        return sentence
    cut = sentence[:MAX_SUMMARY]
    space = cut.rfind(" ")
    return (cut if space == -1 else cut[:space]) + "…"


def reading_minutes(words: int) -> int:
    return math.ceil(words / WORDS_PER_MINUTE) if words else 0


def story_teaser(row) -> dict:
    """NewsItem row (video+channel and site joined) → StoryTeaser.

    `site` is name and country only: detail pages exist just for curated
    sites, and the card does not link the site, so no path is derived.
    """
    site = None
    if row.site is not None and row.site.country:
        site = {"name": row.site.name, "country": row.site.country}
    return {
        "id": row.id,
        "headline": row.headline,
        "summary": first_sentence(row.post_text),
        "screenshot_url": row.screenshot_url,
        "category": row.news_category,
        "significance": row.significance,
        "created_at": row.created_at.isoformat(),
        "channel": row.video.channel.name,
        "sources": len(row.web_sources or []),
        "path": f"/news-archive/{story_slug(row.headline, row.id)}",
        "site": site,
    }


def pick_lead_and_rail(recent: list, lead_48h) -> tuple:
    """Lead = best of the last 48 h, else best of the recent rows (ties → newer).
    Rail = recent rows without the lead, cut to RAIL_ROWS."""
    lead = lead_48h or max(recent, key=lambda r: (r.significance or 0, r.created_at))
    rail = [r for r in recent if r.id != lead.id][:RAIL_ROWS]
    return lead, rail


def journal_teaser(row) -> dict:
    """NewsArticle row → JournalTeaser."""
    content = row.content or ""
    words = len(content.split())
    sections = [h for h in _HEADING.findall(content) if h.strip().lower() not in APPENDIX_SECTIONS]
    image = _IMAGE.search(content)
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "week_start": row.week_start.isoformat() if row.week_start else None,
        "week_end": row.week_end.isoformat() if row.week_end else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "words": words,
        "minutes": reading_minutes(words),
        "sections": sections,
        "sources": len(_LINK.findall(content)),
        "image_url": image.group(1) if image else None,
        "path": f"/articles/{slugify(row.title)}",
    }


def paper_teaser(row) -> dict:
    """PAPER_SUMMARY_COLUMNS row → PaperTeaser, via the public API's mapping."""
    p = paper_summary_kwargs(row)
    words = p["word_count"]
    return {
        "slug": p["slug"],
        "title": p["title"],
        "summary": p["summary"],
        "published_at": p["published_at"],
        "words": words,
        "minutes": reading_minutes(words) if words else None,
        "sources_analyzed": p["sources_analyzed"],
        "quality_score": p["quality_score"],
        "hero_image_url": p["hero_image_url"],
        "path": f"/research/{p['slug']}",
    }


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


def naive_utc_now() -> datetime:
    """news_items.created_at is timestamp *without* time zone — every window
    boundary in this module is measured from here, and only from here."""
    return datetime.now(UTC).replace(tzinfo=None)


def lead_window_start(now: datetime) -> datetime:
    """Oldest story still allowed to take the lead slot."""
    return now - LEAD_WINDOW


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


def _story_query(db: Session):
    """The crawl index, plus the feed's significance floor.

    Two rules meet here and they are not the same rule: /api/news/feed keeps
    speculative stories that score 3 or better, while the crawl index
    (articles_html.public_stories_query - the one definition of "public",
    shared with the archive listing and the sitemap) drops them outright. The
    homepage takes the index set and adds the feed's floor of 2 on top, so
    every card links a page that is itself indexed.
    """
    return (
        public_stories_query(db)
        .options(
            joinedload(NewsItem.video).joinedload(NewsVideo.channel), joinedload(NewsItem.site)
        )
        .filter((NewsItem.significance.is_(None)) | (NewsItem.significance >= 2))
    )


def fetch_landing_data(db: Session) -> dict:
    """Every DB read of the route, in one place, so the route itself stays testable."""
    now = naive_utc_now()
    recent = _story_query(db).order_by(NewsItem.created_at.desc()).limit(RECENT_ROWS).all()
    lead_48h = (
        _story_query(db)
        .filter(NewsItem.created_at >= lead_window_start(now))
        .order_by(NewsItem.significance.desc().nulls_last(), NewsItem.created_at.desc())
        .first()
    )
    # The filter chips, from the same public set as the cards — no chip can
    # open onto stories the homepage would not show.
    categories = [
        row[0]
        for row in public_stories_query(db)
        .with_entities(NewsItem.news_category)
        .filter(
            NewsItem.news_category.isnot(None),
            NewsItem.created_at >= now - CATEGORY_WINDOW,
        )
        .distinct()
        .order_by(NewsItem.news_category)
    ]
    journals = (
        db.query(NewsArticle)
        .filter(NewsArticle.active.is_(True))
        .order_by(NewsArticle.week_start.desc().nulls_last())
        .limit(4)
        .all()
    )
    papers = db.execute(
        text(
            f"""
            SELECT {PAPER_SUMMARY_COLUMNS}
            FROM research_requests r
            WHERE {PUBLIC_PAPER_WHERE}
            ORDER BY r.published_at DESC NULLS LAST
            LIMIT 6
            """
        )
    ).fetchall()
    paper_total = (
        db.execute(
            text(f"SELECT COUNT(*) FROM research_requests r WHERE {PUBLIC_PAPER_WHERE}")
        ).scalar()
        or 0
    )
    news_stats = get_news_stats(db)
    if not isinstance(news_stats, dict):  # cache_get returns the dict, a cold call the model
        news_stats = news_stats.model_dump()
    return {
        "recent": recent,
        "lead_48h": lead_48h,
        "categories": categories,
        "journals": journals,
        "journal_total": news_stats["total_articles"],
        "papers": papers,
        "paper_total": paper_total,
        "news_stats": news_stats,
    }


def build_route(data: dict, site_stats: dict, theo_running: dict | None) -> dict:
    """Rows → the {type: "landing"} payload. A source without rows stays None
    and the section is not rendered at all — no placeholder cards."""
    stories = None
    if data["recent"]:
        lead, rail = pick_lead_and_rail(data["recent"], data["lead_48h"])
        stories = {
            "lead": story_teaser(lead),
            "rail": [story_teaser(r) for r in rail],
            "categories": data["categories"],
        }
    journals = None
    if data["journals"]:
        teasers = [journal_teaser(j) for j in data["journals"]]
        journals = {"lead": teasers[0], "rail": teasers[1:], "total": data["journal_total"]}
    papers = None
    if data["papers"]:
        teasers = [paper_teaser(p) for p in data["papers"]]
        theo = None
        if theo_running:
            theo = {
                "question": theo_running["question"],
                "started_at": theo_running["started_at"],
                "sites_found": theo_running["sites_found"],
            }
        papers = {
            "lead": teasers[0],
            "rail": teasers[1:],
            "total": data["paper_total"],
            "theo": theo,
        }
    return {
        "type": "landing",
        "stats": {
            "sites": site_stats["total_sites"],
            "stories": data["news_stats"]["total_items"],
            "journals": data["journal_total"],
            "papers": data["paper_total"],
        },
        "stories": stories,
        "journals": journals,
        "papers": papers,
    }


@router.get("/home")
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
