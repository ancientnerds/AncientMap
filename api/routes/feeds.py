"""
Atom feeds (RFC 4287) of the public stories and the public research papers.

One feed per type, like the sitemap parts (api/routes/sitemap.py): a reader
subscribes to what it wants, and each feed lists exactly the set its hub links.
Before 2026-10-20 the site had no feed at all — /feed.xml, /atom.xml, /rss.xml
and /feed answered 404 (SEO evaluation 2026-10-19, roadmap W13). The hubs and
the homepage name them as <link rel="alternate"> (src/seo/meta.ts), robots.txt
and llms.txt list them.

nginx proxies /feeds/{stories,research}.xml to these routes, as it does the
sitemap parts. API image only: Lyra serves no HTTP and needs none of this.
"""

from datetime import UTC, datetime
from html import escape

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes.articles_html import public_stories_query
from api.routes.sitemap import BASE_URL, PAPER_LASTMOD_SQL
from pipeline.database import NewsItem, get_db
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE
from pipeline.sites_html_renderer import encode_path
from pipeline.utils.slugs import story_slug

router = APIRouter()

#: The newest entries a feed carries. 44-75 public stories a week reached the
#: archive in the five weeks to 2026-10-19 (psql 2026-10-20), so 50 is about a
#: week of stories; the 41 public papers all fit.
FEED_ENTRIES = 50

# Same lifetime as the sitemaps: crawler bursts hit the caches, and a new
# story is in the feed within the hour.
_HEADERS = {"Cache-Control": "public, max-age=3600"}

_AUTHOR = f"<author><name>Ancient Nerds</name><uri>{BASE_URL}/</uri></author>"

# Both feeds carry original Ancient Nerds text (story summaries, paper metadata), which
# terms.html licenses under CC BY 4.0 with attribution.
_RIGHTS = "CC BY 4.0, attribution to Ancient Nerds (https://ancientnerds.com)"

# Atom ids never change, so they are tag URIs on the row id (RFC 4151): a story's
# URL changes with its headline (the old slug 301s), its id does not.
_TAG = "tag:ancientnerds.com,2026"

# The public papers, newest first, with the page's own title fallback (the question,
# as paper_summary_kwargs does) and the sitemap's lastmod as <updated>.
_PAPERS_SQL = text(f"""
    SELECT r.id::text AS id, r.slug, r.published_by, r.question,
           r.result_json::jsonb->>'title' AS title,
           r.result_json::jsonb->>'card_description' AS card_description,
           COALESCE(r.published_at, r.created_at) AS published,
           {PAPER_LASTMOD_SQL} AS updated
    FROM research_requests r
    WHERE {PUBLIC_PAPER_WHERE}
    ORDER BY COALESCE(r.published_at, r.created_at) DESC
    LIMIT {FEED_ENTRIES}
""")


def _time(value: datetime) -> str:
    """RFC 3339 time with its offset. The columns are naive UTC (server Etc/UTC)."""
    return value.replace(tzinfo=UTC).isoformat()


def _entry(
    *,
    entry_id: str,
    title: str,
    path: str,
    published: datetime,
    updated: datetime,
    summary: str | None,
    author: str | None = None,
) -> str:
    parts = [
        "  <entry>",
        f"    <id>{entry_id}</id>",
        f"    <title>{escape(title)}</title>",
        f'    <link rel="alternate" type="text/html" href="{escape(BASE_URL + encode_path(path))}"/>',
        f"    <published>{_time(published)}</published>",
        f"    <updated>{_time(updated)}</updated>",
    ]
    if author:
        parts.append(f"    <author><name>{escape(author)}</name></author>")
    if summary:
        parts.append(f"    <summary>{escape(summary)}</summary>")
    parts.append("  </entry>")
    return "\n".join(parts)


def _feed(
    *,
    name: str,
    title: str,
    subtitle: str,
    hub: str,
    entries: list[str],
    updated: datetime | None,
) -> Response:
    """The feed document; `updated` is its newest entry's, as RFC 4287 4.2.15 asks.

    None means the public set is empty, a legitimate state (no public paper or story
    yet, or all withdrawn): the feed is then valid and empty, and its required
    <updated> is the moment of the answer, since no entry dates it. max() over the
    empty rows raised ValueError and answered 500 before (review 2026-10-20).
    """
    if updated is None:
        updated = datetime.now(UTC).replace(tzinfo=None)
    self_url = f"{BASE_URL}/feeds/{name}.xml"
    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <id>{self_url}</id>",
            f"  <title>{escape(title)}</title>",
            f"  <subtitle>{escape(subtitle)}</subtitle>",
            f'  <link rel="self" type="application/atom+xml" href="{self_url}"/>',
            f'  <link rel="alternate" type="text/html" href="{BASE_URL}{hub}"/>',
            f"  <updated>{_time(updated)}</updated>",
            f"  {_AUTHOR}",
            f"  <icon>{BASE_URL}/apple-touch-icon.png</icon>",
            f"  <rights>{_RIGHTS}</rights>",
            *entries,
            "</feed>",
        ]
    )
    return Response(content=body, media_type="application/atom+xml", headers=_HEADERS)


@router.api_route("/stories.xml", methods=["GET", "HEAD"])
async def stories_feed(db: Session = Depends(get_db)):
    """The newest public stories: public_stories_query, the set the sitemap and the
    archive list (significance >= 2, scored, not speculative).

    Ordered by when the story appeared here (created_at), and dated by it too:
    Atom's <published>/<updated> say when the entry appeared, and readers sort by
    <updated>. The video's publish time (the page's and the sitemap's date) put a new
    story about a weeks-old video weeks down a reader's list and left the feed's
    <updated> unmoved (review 2026-10-20); the page's JSON-LD keeps the video date.
    """
    rows = (
        public_stories_query(db)
        .with_entities(NewsItem.id, NewsItem.headline, NewsItem.summary, NewsItem.created_at)
        .order_by(NewsItem.created_at.desc(), NewsItem.id.desc())
        .limit(FEED_ENTRIES)
        .all()
    )
    entries = [
        _entry(
            entry_id=f"{_TAG}:story-{row.id}",
            title=row.headline,
            path=f"/news-archive/{story_slug(row.headline, row.id)}",
            published=row.created_at,
            updated=row.created_at,
            summary=row.summary,
        )
        for row in rows
    ]
    return _feed(
        name="stories",
        title="Ancient Nerds — Archaeology Stories",
        subtitle=(
            "AI-written summaries of archaeology videos from third-party YouTube channels, "
            "each with its source."
        ),
        hub="/news-archive/",
        entries=entries,
        updated=max((row.created_at for row in rows), default=None),
    )


@router.api_route("/research.xml", methods=["GET", "HEAD"])
async def research_feed(db: Session = Depends(get_db)):
    """The public research papers (is_public AND status = 'completed'), newest first.

    <updated> follows the paper's page: a correction or a registered video changes
    it without touching published_at (the sitemap's lastmod, PAPER_LASTMOD_SQL).
    A person named in published_by is the entry's author (7 of 41 papers,
    2026-10-20); Theo is a pipeline, not a person, so its papers carry the feed's
    author, Ancient Nerds, as their JSON-LD does (researchMeta).
    """
    rows = db.execute(_PAPERS_SQL).fetchall()
    entries = [
        _entry(
            entry_id=f"{_TAG}:paper-{row.id}",
            title=row.title or row.question,
            path=f"/research/{row.slug}",
            published=row.published,
            updated=row.updated,
            summary=row.card_description,
            author=row.published_by if row.published_by not in (None, "Theo") else None,
        )
        for row in rows
    ]
    return _feed(
        name="research",
        title="Ancient Nerds — Research Papers",
        subtitle=(
            "Open-access research papers written by an AI pipeline with citation checking, "
            "published under CC BY 4.0."
        ),
        hub="/research/",
        entries=entries,
        updated=max((row.updated for row in rows), default=None),
    )
