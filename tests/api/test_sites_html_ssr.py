# SPDX-License-Identifier: AGPL-3.0-only
"""Die /sites/-Routen übergeben Payload-Dicts an den SSR-Splice (react-ssr Tasks 10/11).

DB-los: die Routen werden direkt mit einer Fake-Session aufgerufen; der
Sidecar (render_page) und die gebaute Shell (render_app_shell) sind gemockt.
Geprüft wird der Payload-Vertrag Richtung React — die Feldnamen hier sind
der Vertrag, den anRoute.ts (SitesIndexRoute/CountryRoute/SiteRoute)
deklariert.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.routes.sites_html import site_detail, sites_by_country, sites_index


class FakeDb:
    """Liefert je execute()-Aufruf das nächste vorbereitete Zeilen-Set."""

    def __init__(self, *result_sets: list):
        self._results = list(result_sets)

    def execute(self, *args, **kwargs):
        rows = self._results.pop(0)
        return SimpleNamespace(
            fetchall=lambda: rows,
            fetchone=lambda: rows[0] if rows else None,
        )


def _patched():
    return (
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")),
        patch("api.seo_shell.render_app_shell", return_value="<html>ok</html>"),
    )


def test_sites_index_hands_the_countries_payload():
    rows = [
        SimpleNamespace(country="Denmark", count=42),
        SimpleNamespace(country="Türkiye", count=218),
    ]
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(sites_index(db=FakeDb(rows)))

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "site.html"
    assert render_mock.call_args[0][0] == {
        "type": "sitesIndex",
        "countries": [
            {"name": "Denmark", "count": 42, "path": "/sites/denmark"},
            {"name": "Türkiye", "count": 218, "path": "/sites/türkiye"},
        ],
    }


def test_country_route_hands_the_raw_sites_payload():
    country_rows = [SimpleNamespace(country="Denmark")]
    site_rows = [
        SimpleNamespace(
            id="5281654c-0000-4000-8000-000000000000",
            name="Borremose",
            site_type="Fortification",
            period_name="500 BC - 1 AD",
            period_start=-500,
            description="An Iron Age bog fortress.",
            thumbnail_url="/data/images/wiki/5281654c/hero.webp",
        )
    ]
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(sites_by_country("denmark", db=FakeDb(country_rows, site_rows)))

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "site.html"
    route = render_mock.call_args[0][0]
    assert route["type"] == "country"
    assert route["country"] == "Denmark"
    # Rohe Zeilen, keine vorgruppierten Sektionen: die Gruppierung ist eine
    # Darstellungsentscheidung und lebt seit dem Cutover in src/seo/grouping.ts.
    assert "sections" not in route
    assert route["sites"] == [
        {
            "name": "Borremose",
            "description": "An Iron Age bog fortress.",
            "path": "/sites/denmark/borremose-5281654c",
            "site_type": "Fortification",
            "period_name": "500 BC - 1 AD",
            "period_start": -500,
            "thumbnail_url": "/data/images/wiki/5281654c/hero.webp",
        }
    ]


def test_unknown_country_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            sites_by_country("atlantis", db=FakeDb([SimpleNamespace(country="Denmark")]))
        )

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()


def _borremose_row() -> SimpleNamespace:
    return SimpleNamespace(
        id="5281654c-0000-4000-8000-000000000000",
        name="Borremose",
        country="Denmark",
        site_type="Fortification",
        period_name="500 BC - 1 AD",
        period_start=-500,
        period_end=1,
        description="An Iron Age bog fortress.\nThree causeways cross the moat.",
        lat=56.78,
        lon=9.52,
        source_url="https://example.org/borremose",
        parent_site_id=None,
        description_citations=[
            {"n": 1, "url": "https://example.org/ref", "title": "Ref", "domain": "example.org"}
        ],
        best_wiki_url="https://da.wikipedia.org/wiki/Borremose",
        source_language="da",
    )


def test_site_detail_hands_the_full_raw_payload():
    """Task 11: Rohzeile + _related_content mit fertigen Pfaden, kein Stub mehr."""
    alt_rows = [SimpleNamespace(name="Borremose fortress")]
    img_rows = [
        SimpleNamespace(
            filename="hero.webp",
            author="J. Fotograf",
            license="CC BY-SA 4.0",
            commons_page_url="https://commons.wikimedia.org/wiki/File:Borremose.jpg",
        )
    ]
    link_rows = [
        SimpleNamespace(
            title="Museum page", content_url="https://museum.dk/borremose", content_type="reference"
        )
    ]
    sibling_rows = [
        SimpleNamespace(id="99887766-0000-4000-8000-000000000000", name="Lindholm Høje")
    ]
    # public_stories_query ist eine ORM-Query — FakeDb kann sie nicht liefern.
    news_chain = MagicMock()
    news_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        SimpleNamespace(headline="Bog body found at Borremose", id=4321)
    ]

    render, shell = _patched()
    with (
        render as render_mock,
        shell as shell_mock,
        patch("api.routes.sites_html.public_stories_query", return_value=news_chain),
    ):
        resp = asyncio.run(
            site_detail(
                "denmark",
                "borremose-5281654c",
                db=FakeDb([_borremose_row()], alt_rows, img_rows, link_rows, sibling_rows),
            )
        )

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "site.html"
    route = render_mock.call_args[0][0]
    # Rohzeile, snake_case — Anzeigelogik (Periode, Koordinaten) lebt in
    # src/seo/display.ts, nicht im Payload.
    assert route["type"] == "site"
    assert route["id"] == "5281654c-0000-4000-8000-000000000000"
    assert route["name"] == "Borremose"
    assert route["country"] == "Denmark"
    assert route["site_type"] == "Fortification"
    assert route["period_name"] == "500 BC - 1 AD"
    assert route["period_start"] == -500
    assert route["period_end"] == 1
    assert route["lat"] == 56.78
    assert route["lon"] == 9.52
    assert route["source_url"] == "https://example.org/borremose"
    assert route["best_wiki_url"] == "https://da.wikipedia.org/wiki/Borremose"
    assert route["source_language"] == "da"
    assert route["description_citations"][0]["url"] == "https://example.org/ref"
    # _related_content: fertige Pfade, Attribution vollständig.
    assert route["alt_names"] == ["Borremose fortress"]
    assert route["image"] == {
        "url": "/data/images/wiki/5281654c/hero.webp",
        "author": "J. Fotograf",
        "license": "CC BY-SA 4.0",
        "commons_url": "https://commons.wikimedia.org/wiki/File:Borremose.jpg",
    }
    assert route["news"] == [
        {"slug": "bog-body-found-at-borremose-4321", "headline": "Bog body found at Borremose"}
    ]
    assert route["links"] == [
        {"title": "Museum page", "url": "https://museum.dk/borremose", "content_type": "reference"}
    ]
    assert route["parent"] is None
    assert route["siblings"] == [
        {"name": "Lindholm Høje", "path": "/sites/denmark/lindholm-høje-99887766"}
    ]


def test_site_detail_301s_a_stale_slug_to_the_canonical_url():
    """Umbenennung darf keine URL verwaisen — der ID-Suffix löst auf, 301 heilt."""
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            site_detail("denmark", "old-name-5281654c", db=FakeDb([_borremose_row()]))
        )

    assert resp.status_code == 301
    assert resp.headers["location"] == "/sites/denmark/borremose-5281654c"
    render_mock.assert_not_called()
    shell_mock.assert_not_called()


def test_site_detail_404s_a_malformed_slug_without_touching_the_db():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(site_detail("denmark", "no-id-suffix", db=FakeDb()))

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()
