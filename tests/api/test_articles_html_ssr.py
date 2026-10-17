# SPDX-License-Identifier: AGPL-3.0-only
"""Die /articles/-Routen übergeben Payload-Dicts an den SSR-Splice (react-ssr Task 13).

DB-los: die Routen werden direkt mit einer Fake-ORM-Session aufgerufen; der
Sidecar (render_page) und die gebaute Shell (render_app_shell) sind
gemockt. Geprüft wird der Payload-Vertrag Richtung React — die Feldnamen
hier sind der Vertrag, den anRoute.ts (ArticleRoute/ArticleIndexRoute)
deklariert: rohe snake_case-Zeilenfelder plus das
Python-markdown-gerenderte body_html.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.routes.articles_html import article_page, articles_listing


def _orm_db(articles: list) -> MagicMock:
    """Fake für die beiden Query-Formen der Routen (order_by().all() / all())."""
    db = MagicMock()
    query = db.query.return_value
    query.order_by.return_value.all.return_value = articles
    query.all.return_value = articles
    return db


def _patched():
    return (
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")),
        patch("api.seo_shell.render_app_shell", return_value="<html>ok</html>"),
    )


def _article(**overrides) -> SimpleNamespace:
    row = {
        "id": 31,
        "title": "Week 31: Hoards & Harbours",
        "summary": "A Viking silver hoard on Gotland.",
        "content": "## Gotland\n\nA silver hoard surfaced.",
        "published_at": datetime(2026, 8, 3),
        "week_start": date(2026, 7, 27),
        "week_end": date(2026, 8, 2),
        "quality_report": None,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def test_articles_listing_hands_the_article_list():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            articles_listing(
                db=_orm_db(
                    [_article(content="![A silver hoard](https://a.example/h.webp)\n\nx " * 40)]
                )
            )
        )

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "articles.html"
    route = render_mock.call_args[0][0]
    assert route == {
        "type": "articleIndex",
        "articles": [
            {
                "slug": "week-31-hoards-harbours",
                "title": "Week 31: Hoards & Harbours",
                "summary": "A Viking silver hoard on Gotland.",
                "thumbnail_url": "https://a.example/h.webp",
                "week_start": "2026-07-27",
                "week_end": "2026-08-02",
                "reading_minutes": 1,
            }
        ],
    }


def test_articles_listing_keeps_a_journal_without_a_picture_playable():
    """Ohne Bild darf die Karte nicht kaputtgehen — nur ohne thumbnail_url."""
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(articles_listing(db=_orm_db([_article(content="Nur Text, kein Bild.")])))

    card = render_mock.call_args[0][0]["articles"][0]
    assert card["thumbnail_url"] is None
    assert card["reading_minutes"] == 1


def test_article_page_hands_the_full_raw_payload():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            article_page(
                "week-31-hoards-harbours",
                db=_orm_db([_article(quality_report={"assessment_score": 9, "total_sources": 21})]),
            )
        )

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "articles.html"
    route = render_mock.call_args[0][0]
    # Rohe Zeilenfelder, snake_case — Datumsformat lebt in src/seo/display.ts.
    assert route["type"] == "article"
    assert route["slug"] == "week-31-hoards-harbours"
    assert route["title"] == "Week 31: Hoards & Harbours"
    assert route["summary"] == "A Viking silver hoard on Gotland."
    assert route["published_at"] == "2026-08-03T00:00:00"
    # Die Zitat-Popovers fragen /news/articles/{id}/citations ab.
    assert route["id"] == 31
    # Das Qualitäts-Panel stand bis 2026-10-12 nur im SPA-Leser.
    assert route["quality_report"] == {"assessment_score": 9, "total_sources": 21}
    # Journals tragen kein Hero-Bild — og:image fällt in articleMeta auf den
    # Default zurück, exakt wie im Python-Fragment.
    assert route["hero_image_url"] is None
    # body_html: das Artikel-Markdown, Python-markdown-gerendert.
    assert "<h2" in route["body_html"]
    assert "A silver hoard surfaced." in route["body_html"]


def test_article_page_without_a_quality_report_passes_none():
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(article_page("week-31-hoards-harbours", db=_orm_db([_article()])))

    assert render_mock.call_args[0][0]["quality_report"] is None


def test_article_page_serves_the_citation_links_the_reader_can_follow():
    """Die Route verdrahtet die Anker, nicht nur der Renderer sie kann.

    Ohne den Aufruf in der Route bliebe die indexierte Seite bei reinem Text
    ("[1]"), weil der Link bisher nur im Browser gebaut wurde - dieser Test
    fällt dann, statt das erst der Crawler zu zeigen.
    """
    render, shell = _patched()
    content = (
        "## Gotland\n\n"
        "The hoard was moved with a sledge [1], the video says [6, 7].\n\n"
        "The temple itself is older [V2].\n\n"
        "### Sources\n\n"
        "1. [A sledge at Gotland](https://a.example/sledge)\n"
        "2. [Not cited](https://a.example/uncited)\n"
    )
    with render as render_mock, shell:
        asyncio.run(
            article_page("week-31-hoards-harbours", db=_orm_db([_article(content=content)]))
        )

    body = render_mock.call_args[0][0]["body_html"]
    assert (
        '<a class="article-citation-link" data-citation="1" href="https://a.example/sledge" '
        'target="_blank" rel="noopener noreferrer">[1]</a>' in body
    )
    # Die Video-Zitatnummer zeigt auf die Quellenliste, wo ihre Karte steht.
    assert '<a class="article-citation-link" data-citation="V2" href="#sources">[V2]</a>' in body
    # Die Gruppenmarke wird vor dem Markdown gesprengt: beide Nummern verlinkt.
    assert 'data-citation="6"' in body and 'data-citation="7"' in body
    assert "[6, 7]" not in body
    # Die Quellenliste bleibt im HTML, wo ein Crawler sie liest.
    assert 'href="https://a.example/uncited"' in body


def test_unknown_article_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(article_page("no-such-journal", db=_orm_db([_article()])))

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()
