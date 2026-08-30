# SPDX-License-Identifier: AGPL-3.0-only
"""/sitemap.xml ist ein Sitemap-INDEX auf sechs Teil-Sitemaps je Seitentyp.

Die Aufteilung macht die Indexierungsquote JE TYP in der GSC messbar
(SEO-Task 2026-08-17). DB-los im Stil von test_story_html_ssr.py: die
Routen werden direkt mit Fake-Sessions aufgerufen. Gepinnt wird der
XML-Vertrag: Index → alle Teile, jede Teil-Sitemap valides XML, <loc>
prozentkodiert (encode_path), lastmod ISO, keine URL doppelt über alle
Teile, Story-URLs aus public_stories_query (der maßgebliche Filter —
alles andere bewürbe 404s).
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import Response

from api.routes import sitemap as sm

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _root(resp: Response) -> ET.Element:
    assert resp.status_code == 200
    assert resp.media_type == "application/xml"
    assert resp.headers["cache-control"] == "public, max-age=3600"
    return ET.fromstring(resp.body)


def _locs(resp: Response) -> list[str]:
    # Nur Sitemap-<loc>s — die image:loc der Homepage hat einen anderen NS.
    return [el.text or "" for el in _root(resp).iter(f"{NS}loc")]


def _lastmods(resp: Response) -> list[str]:
    return [el.text or "" for el in _root(resp).iter(f"{NS}lastmod")]


def _execute_db(rows: list[SimpleNamespace]) -> MagicMock:
    """Fake-Session für Routen mit einer einzigen db.execute(text(...))."""
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = rows
    return db


def _orm_db(rows: list) -> MagicMock:
    """Fake-ORM-Session: jede Query-Kette endet in .all() → rows."""
    q = MagicMock()
    for name in ("join", "filter", "with_entities", "order_by", "offset", "limit"):
        getattr(q, name).return_value = q
    q.all.return_value = rows
    db = MagicMock()
    db.query.return_value = q
    return db


def _site(name: str, country: str, site_id: str, lastmod: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(name=name, country=country, id=site_id, lastmod=lastmod)


def _story(item_id: int, headline: str, lastmod: datetime) -> SimpleNamespace:
    return SimpleNamespace(id=item_id, headline=headline, lastmod=lastmod)


SITES = [
    _site("Göbekli Tepe", "Türkiye", "9c8b7a65-4321-4cba-8000-111122223333", datetime(2026, 8, 1)),
    _site("Ayşepınar", "Türkiye", "1a2b3c4d-0000-4000-8000-000000000000", None),
    _site(
        "Stonehenge", "United Kingdom", "5e6f7a8b-0000-4000-8000-000000000000", datetime(2026, 7, 2)
    ),
]

COUNTRIES = [
    # Nach dem Template-Floor (21.08.): Türkiye liegt DANACH und gewinnt,
    # United Kingdom liegt davor und wird auf den Floor gehoben.
    SimpleNamespace(country="Türkiye", lastmod=datetime(2026, 9, 1)),
    SimpleNamespace(country="United Kingdom", lastmod=datetime(2026, 7, 2)),
]

STORIES = [_story(4000 + i, f"Dig update {i}", datetime(2026, 3, 1 + i % 27)) for i in range(120)]

PAPERS = [
    SimpleNamespace(slug="obsidian-trade-networks-anatolia", lastmod=datetime(2026, 7, 2)),
    SimpleNamespace(slug="gobekli-tepe-water-management", lastmod=None),
]

ARTICLES = [
    SimpleNamespace(
        title="Week 31: Hoards & Harbours",
        published_at=datetime(2026, 8, 3),
        created_at=datetime(2026, 8, 2),
    ),
    SimpleNamespace(
        title="Week 30: Mummies & Mosaics",
        published_at=None,
        created_at=datetime(2026, 7, 27),
    ),
]


def _all_part_responses() -> dict[str, Response]:
    return {
        "static": asyncio.run(sm.sitemap_static()),
        "sites": asyncio.run(sm.sitemap_sites(db=_execute_db(SITES))),
        "countries": asyncio.run(sm.sitemap_countries(db=_execute_db(COUNTRIES))),
        "stories": asyncio.run(sm.sitemap_stories(db=_orm_db(STORIES))),
        "research": asyncio.run(sm.sitemap_research(db=_execute_db(PAPERS))),
        "articles": asyncio.run(sm.sitemap_articles(db=_orm_db(ARTICLES))),
    }


def test_index_references_every_part_file_and_nothing_else():
    resp = asyncio.run(sm.sitemap_index())
    root = _root(resp)
    assert root.tag == f"{NS}sitemapindex"
    locs = [el.text for el in root.iter(f"{NS}loc")]
    assert locs == [f"https://ancientnerds.com/sitemap-{part}.xml" for part in sm.SITEMAP_PARTS]


def test_every_part_is_a_valid_urlset():
    for name, resp in _all_part_responses().items():
        root = _root(resp)  # ET.fromstring wirft bei invalidem XML
        assert root.tag == f"{NS}urlset", name
        locs = _locs(resp)
        assert locs, name
        assert all(loc.startswith("https://ancientnerds.com/") for loc in locs), name


def test_locs_are_percent_encoded_pure_ascii():
    """encode_path: Ayşepınar/Türkiye müssen als %-Escapes erscheinen."""
    locs = _locs(asyncio.run(sm.sitemap_sites(db=_execute_db(SITES))))
    assert any("/sites/t%C3%BCrkiye/" in loc for loc in locs)
    assert any("ay%C5%9Fep%C4%B1nar" in loc for loc in locs)
    for loc in locs:
        assert loc.isascii(), loc


def test_lastmod_is_iso_date_and_only_where_data_exists():
    for name, resp in _all_part_responses().items():
        for value in _lastmods(resp):
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), (name, value)
    # Statische Einstiege haben keine Row-Daten — ein erfundenes "today"
    # würde tägliche Änderung signalisieren.
    assert _lastmods(asyncio.run(sm.sitemap_static())) == []


def test_sites_lastmod_is_floored_at_the_template_change():
    """Row-lastmod endet im März, aber JEDE /sites/-Seite änderte sich mit
    dem Rendering-Umbau (react-ssr 16.08. + NERV 21.08.) — Google hält
    ~2.500 davon für Soft 404 aus der Spinner-Ära und crawlt ohne neues
    lastmod nicht nach. Der Floor gilt auch für Rows ganz ohne Datum."""
    sites = _root(asyncio.run(sm.sitemap_sites(db=_execute_db(SITES))))
    urls = list(sites.iter(f"{NS}url"))
    assert len(urls) == 3
    assert [u.findtext(f"{NS}lastmod") for u in urls] == ["2026-08-21"] * 3


def test_no_url_appears_in_two_parts():
    seen: list[str] = []
    for resp in _all_part_responses().values():
        seen.extend(_locs(resp))
    assert len(seen) == len(set(seen))


def test_story_urls_come_from_public_stories_query():
    """Der maßgebliche Filter: /news-archive/{slug} serviert genau dieses Set."""
    q = MagicMock()
    q.with_entities.return_value = q
    q.order_by.return_value = q
    q.all.return_value = [_story(4711, "Sun Chariot fragment found", datetime(2026, 3, 14))]
    db = MagicMock()
    with patch.object(sm, "public_stories_query", return_value=q) as psq:
        locs = _locs(asyncio.run(sm.sitemap_stories(db=db)))

    psq.assert_called_once_with(db)
    assert "https://ancientnerds.com/news-archive/sun-chariot-fragment-found-4711" in locs
    # Eine Story → eine Archivseite, keine erfundenen page/N-URLs.
    assert locs[0] == "https://ancientnerds.com/news-archive/"
    assert len(locs) == 2


def test_stories_part_lists_every_archive_page():
    """120 Stories → 3 Archivseiten (STORIES_PER_PAGE=50) + die Stories selbst."""
    locs = _locs(asyncio.run(sm.sitemap_stories(db=_orm_db(STORIES))))
    assert "https://ancientnerds.com/news-archive/" in locs
    assert "https://ancientnerds.com/news-archive/page/2" in locs
    assert "https://ancientnerds.com/news-archive/page/3" in locs
    assert "https://ancientnerds.com/news-archive/page/4" not in locs
    assert len(locs) == 3 + len(STORIES)


def test_countries_part_carries_the_hub_and_per_country_lastmod():
    resp = asyncio.run(sm.sitemap_countries(db=_execute_db(COUNTRIES)))
    root = _root(resp)
    urls = list(root.iter(f"{NS}url"))
    # Hub zuerst, mit dem globalen Maximum als lastmod. Der Floor hebt nur
    # ältere Daten an — ein Row-Datum NACH dem Template-Umbau gewinnt.
    hub = urls[0]
    assert hub.findtext(f"{NS}loc") == "https://ancientnerds.com/sites/"
    assert hub.findtext(f"{NS}lastmod") == "2026-09-01"
    assert urls[1].findtext(f"{NS}loc") == "https://ancientnerds.com/sites/t%C3%BCrkiye"
    assert urls[1].findtext(f"{NS}lastmod") == "2026-09-01"
    assert urls[2].findtext(f"{NS}lastmod") == "2026-08-21"


def test_research_and_articles_parts_link_hub_and_detail_pages():
    research = _locs(asyncio.run(sm.sitemap_research(db=_execute_db(PAPERS))))
    assert research[0] == "https://ancientnerds.com/research/"
    assert "https://ancientnerds.com/research/obsidian-trade-networks-anatolia" in research

    articles = _locs(asyncio.run(sm.sitemap_articles(db=_orm_db(ARTICLES))))
    assert articles[0] == "https://ancientnerds.com/articles/"
    assert "https://ancientnerds.com/articles/week-31-hoards-harbours" in articles
