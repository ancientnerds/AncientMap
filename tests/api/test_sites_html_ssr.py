# SPDX-License-Identifier: AGPL-3.0-only
"""Die /sites/-Routen übergeben Payload-Dicts an den SSR-Splice (react-ssr Task 10).

DB-los: die Routen werden direkt mit einer Fake-Session aufgerufen; der
Sidecar (render_page) und die gebaute Shell (render_app_shell) sind gemockt.
Geprüft wird der Payload-Vertrag Richtung React — die Feldnamen hier sind
der Vertrag, den anRoute.ts (SitesIndexRoute/CountryRoute) deklariert.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from api.routes.sites_html import sites_by_country, sites_index


class FakeDb:
    """Liefert je execute()-Aufruf das nächste vorbereitete Zeilen-Set."""

    def __init__(self, *result_sets: list):
        self._results = list(result_sets)

    def execute(self, *args, **kwargs):
        rows = self._results.pop(0)
        return SimpleNamespace(fetchall=lambda: rows)


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
