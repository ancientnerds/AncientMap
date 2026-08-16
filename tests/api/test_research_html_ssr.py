# SPDX-License-Identifier: AGPL-3.0-only
"""Die /research/-Routen übergeben Payload-Dicts an den SSR-Splice (react-ssr Task 12).

DB-los: die Routen werden direkt mit einer Fake-Session aufgerufen; der
Sidecar (render_page) und die gebaute Shell (render_app_shell) sind
gemockt. Geprüft wird der Payload-Vertrag Richtung React — die Feldnamen
hier sind der Vertrag, den anRoute.ts (ResearchRoute/ResearchIndexRoute)
deklariert: rohe snake_case-Felder aus paper_summary_kwargs plus das
Python-markdown-gerenderte body_html.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from api.routes.research_html import research_listing, research_paper_page


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


def _paper_row(**overrides) -> SimpleNamespace:
    """Eine Zeile mit den PAPER_SUMMARY_COLUMNS-Aliassen plus Report-Feldern."""
    row = {
        "id": "7f00aa00-0000-4000-8000-000000000000",
        "slug": "obsidian-trade-networks-anatolia",
        "question": "How did obsidian move through Neolithic Anatolia?",
        "published_by": "Theo",
        "published_at": datetime(2026, 7, 2, 4, 15),
        "sites_found": 12,
        "title": "Obsidian Trade Networks in Neolithic Anatolia",
        "card_description": "Two exchange spheres centred on Cappadocia and Lake Van.",
        "score": "9",
        "badge": "gold",
        "word_count": "4200",
        "hero_src": "/data/research/obsidian/hero.webp",
        "published_report": "## Findings\n\nObsidian moved far.",
        "report": "raw draft",
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def test_research_index_hands_the_paper_list():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(research_listing(db=FakeDb([_paper_row()])))

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "research.html"
    route = render_mock.call_args[0][0]
    assert route == {
        "type": "researchIndex",
        "papers": [
            {
                "slug": "obsidian-trade-networks-anatolia",
                "title": "Obsidian Trade Networks in Neolithic Anatolia",
                "summary": "Two exchange spheres centred on Cappadocia and Lake Van.",
            }
        ],
    }


def test_research_paper_hands_the_full_raw_payload():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([_paper_row()]))
        )

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "research.html"
    route = render_mock.call_args[0][0]
    # Rohe paper_summary_kwargs-Felder, snake_case — Autor-Default und
    # Datumsformat leben in src/seo/, nicht im Payload.
    assert route["type"] == "research"
    assert route["slug"] == "obsidian-trade-networks-anatolia"
    assert route["title"] == "Obsidian Trade Networks in Neolithic Anatolia"
    assert route["summary"] == "Two exchange spheres centred on Cappadocia and Lake Van."
    assert route["author"] == "Theo"
    assert route["published_at"] == "2026-07-02T04:15:00"
    assert route["hero_image_url"] == "https://ancientnerds.com/data/research/obsidian/hero.webp"
    # body_html: das reviewte published_report, Python-markdown-gerendert.
    assert "<h2" in route["body_html"]
    assert "Obsidian moved far." in route["body_html"]
    assert "raw draft" not in route["body_html"]


def test_research_paper_falls_back_to_the_raw_report():
    """Ohne published_report zählt der Rohreport — dieselbe Regel wie /api/v1."""
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(
            research_paper_page(
                "obsidian-trade-networks-anatolia",
                db=FakeDb([_paper_row(published_report=None)]),
            )
        )

    assert "raw draft" in render_mock.call_args[0][0]["body_html"]


def test_research_paper_strips_the_stored_title_heading():
    """3 von 16 Live-Papers beginnen mit '# Titel' im gespeicherten Report —
    ungestrippt servierte die Seite zwei <h1> (das eigene plus dieses)."""
    report = "# Obsidian Trade Networks in Neolithic Anatolia\n\n## Findings\n\nObsidian moved far."
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(
            research_paper_page(
                "obsidian-trade-networks-anatolia",
                db=FakeDb([_paper_row(published_report=report)]),
            )
        )

    body = render_mock.call_args[0][0]["body_html"]
    assert "<h1" not in body
    assert "Obsidian moved far." in body


def test_research_paper_links_the_references():
    """Theo speichert References als Plain-Text-Zeilen mit nackten URLs —
    format_references_md macht daraus klickbare Links, wie im Medium-Pfad."""
    report = (
        "## Findings\n\nObsidian moved far.\n\n"
        "## References\n\n"
        "[1] Doe, J. (2020). Obsidian sourcing. https://example.org/paper\n"
        "[2] Roe, R. (2021). Exchange spheres. DOI: 10.1234/abcd"
    )
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(
            research_paper_page(
                "obsidian-trade-networks-anatolia",
                db=FakeDb([_paper_row(published_report=report)]),
            )
        )

    body = render_mock.call_args[0][0]["body_html"]
    assert '<a href="https://example.org/paper"' in body
    assert '<a href="https://doi.org/10.1234/abcd"' in body


def test_unknown_paper_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(research_paper_page("no-such-paper", db=FakeDb([])))

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()
