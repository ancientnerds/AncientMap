# SPDX-License-Identifier: AGPL-3.0-only
"""The Atom feeds /feeds/stories.xml and /feeds/research.xml (owner decision 2026-10-20,
roadmap W13). DB-less like test_sitemap.py: the routes run against fake sessions. Pinned:
valid Atom, the public set only (public_stories_query, PUBLIC_PAPER_WHERE), stable tag ids,
percent-encoded links, RFC 3339 times with offset, and the paper's lastmod as <updated>.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import Response

from api.routes import feeds
from api.routes.sitemap import PAPER_LASTMOD_SQL
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE

A = "{http://www.w3.org/2005/Atom}"
REPO = Path(__file__).resolve().parents[2]


def _root(resp: Response) -> ET.Element:
    assert resp.status_code == 200
    assert resp.media_type == "application/atom+xml"
    assert resp.headers["cache-control"] == "public, max-age=3600"
    root = ET.fromstring(resp.body)
    assert root.tag == f"{A}feed"
    return root


def _stories_query(rows: list) -> MagicMock:
    q = MagicMock()
    for name in ("with_entities", "order_by", "limit"):
        getattr(q, name).return_value = q
    q.all.return_value = rows
    return q


STORIES = [
    SimpleNamespace(
        id=8817,
        headline='Göbekli Tepe\'s pillar 43 & the "vulture stone"',
        summary="A new reading of the vulture stone.",
        published=datetime(2026, 10, 18, 14, 3),
    ),
    SimpleNamespace(
        id=8815,
        headline="Roman road found under Cologne",
        summary="Excavators found a paved road.",
        published=datetime(2026, 10, 16, 9, 0),
    ),
]

PAPERS = [
    SimpleNamespace(
        id="4b6f0a52-1111-4222-8333-444455556666",
        slug="baalbek-1000-tonne-question",
        published_by="Theo",
        question="How were the Baalbek stones moved?",
        title="Baalbek: the 1,000-tonne question",
        card_description="How the quarry stones were cut and moved.",
        published=datetime(2026, 9, 30, 8, 0),
        updated=datetime(2026, 10, 12, 0, 0),
    ),
    SimpleNamespace(
        id="9c8b7a65-1111-4222-8333-444455556666",
        slug="obsidian-trade-networks-anatolia",
        published_by="MrSchneebly",
        question="Obsidian trade in Anatolia?",
        title=None,
        card_description=None,
        published=datetime(2026, 9, 1, 12, 30),
        updated=datetime(2026, 9, 1, 12, 30),
    ),
]


def _stories_feed() -> tuple[ET.Element, MagicMock, MagicMock]:
    q = _stories_query(STORIES)
    db = MagicMock()
    with patch.object(feeds, "public_stories_query", return_value=q) as psq:
        root = _root(asyncio.run(feeds.stories_feed(db=db)))
    return root, psq, q


def test_stories_feed_lists_the_public_stories_as_atom():
    root, psq, q = _stories_feed()
    # The set the sitemap and the archive list: significance >= 2, not speculative.
    psq.assert_called_once()
    q.limit.assert_called_once_with(feeds.FEED_ENTRIES)

    assert root.findtext(f"{A}id") == "https://ancientnerds.com/feeds/stories.xml"
    links = {el.get("rel"): el.get("href") for el in root.findall(f"{A}link")}
    assert links == {
        "self": "https://ancientnerds.com/feeds/stories.xml",
        "alternate": "https://ancientnerds.com/news-archive/",
    }
    # The feed's updated is its newest entry's, with the UTC offset.
    assert root.findtext(f"{A}updated") == "2026-10-18T14:03:00+00:00"
    assert root.find(f"{A}author/{A}name").text == "Ancient Nerds"
    assert root.findtext(f"{A}rights").startswith("CC BY 4.0")

    entries = root.findall(f"{A}entry")
    assert [e.findtext(f"{A}id") for e in entries] == [
        "tag:ancientnerds.com,2026:story-8817",
        "tag:ancientnerds.com,2026:story-8815",
    ]
    first = entries[0]
    assert first.findtext(f"{A}title") == 'Göbekli Tepe\'s pillar 43 & the "vulture stone"'
    # The page URL, percent-encoded like the sitemap <loc> (ö in the slug).
    assert first.find(f"{A}link").get("href") == (
        "https://ancientnerds.com/news-archive/g%C3%B6bekli-tepes-pillar-43-the-vulture-stone-8817"
    )
    assert first.findtext(f"{A}published") == "2026-10-18T14:03:00+00:00"
    assert first.findtext(f"{A}updated") == "2026-10-18T14:03:00+00:00"
    assert first.findtext(f"{A}summary") == "A new reading of the vulture stone."


def test_research_feed_reads_the_public_papers_with_their_page_lastmod():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = PAPERS
    root = _root(asyncio.run(feeds.research_feed(db=db)))

    sql = " ".join(str(db.execute.call_args[0][0]).split())
    assert PUBLIC_PAPER_WHERE in sql
    assert " ".join(PAPER_LASTMOD_SQL.split()) + " AS updated" in sql
    assert f"LIMIT {feeds.FEED_ENTRIES}" in sql

    assert root.findtext(f"{A}id") == "https://ancientnerds.com/feeds/research.xml"
    assert root.findtext(f"{A}updated") == "2026-10-12T00:00:00+00:00"
    theo, person = root.findall(f"{A}entry")
    assert theo.findtext(f"{A}id") == "tag:ancientnerds.com,2026:paper-" + PAPERS[0].id
    assert theo.find(f"{A}link").get("href") == (
        "https://ancientnerds.com/research/baalbek-1000-tonne-question"
    )
    # A correction moves <updated>, not <published>.
    assert theo.findtext(f"{A}published") == "2026-09-30T08:00:00+00:00"
    assert theo.findtext(f"{A}updated") == "2026-10-12T00:00:00+00:00"
    # Theo is a pipeline: its papers carry the feed's author only.
    assert theo.find(f"{A}author") is None
    assert person.find(f"{A}author/{A}name").text == "MrSchneebly"
    # The page's title fallback is the question; no summary without a card description.
    assert person.findtext(f"{A}title") == "Obsidian trade in Anatolia?"
    assert person.find(f"{A}summary") is None


def test_nginx_proxies_both_feeds_to_the_api():
    config = (REPO / "ancientnerds-nginx-config").read_text(encoding="utf-8")
    assert "location ~ ^/feeds/(stories|research)\\.xml$ {" in config
    assert "proxy_pass http://an_api/api$request_uri;" in config


def test_the_app_serves_both_feeds_under_the_path_nginx_proxies():
    from fastapi.testclient import TestClient

    from api.main import app
    from pipeline.database import get_db

    db = MagicMock()
    db.execute.return_value.fetchall.return_value = PAPERS
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)  # no `with`: the lifespan (workers, bot) stays off
        with patch.object(feeds, "public_stories_query", return_value=_stories_query(STORIES)):
            stories = client.get("/api/feeds/stories.xml")
        research = client.get("/api/feeds/research.xml")
    finally:
        app.dependency_overrides.pop(get_db)
    for resp in (stories, research):
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/atom+xml"
        assert ET.fromstring(resp.content).tag == f"{A}feed"
