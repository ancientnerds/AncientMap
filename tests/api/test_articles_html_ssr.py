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
        resp = asyncio.run(articles_listing(db=_orm_db([_article()])))

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
            }
        ],
    }


def test_article_page_hands_the_full_raw_payload():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(article_page("week-31-hoards-harbours", db=_orm_db([_article()])))

    assert resp.status_code == 200
    assert shell_mock.call_args[0][0] == "articles.html"
    route = render_mock.call_args[0][0]
    # Rohe Zeilenfelder, snake_case — Datumsformat lebt in src/seo/display.ts.
    assert route["type"] == "article"
    assert route["slug"] == "week-31-hoards-harbours"
    assert route["title"] == "Week 31: Hoards & Harbours"
    assert route["summary"] == "A Viking silver hoard on Gotland."
    assert route["published_at"] == "2026-08-03T00:00:00"
    # Journals tragen kein Hero-Bild — og:image fällt in articleMeta auf den
    # Default zurück, exakt wie im Python-Fragment.
    assert route["hero_image_url"] is None
    # body_html: das Artikel-Markdown, Python-markdown-gerendert.
    assert "<h2" in route["body_html"]
    assert "A silver hoard surfaced." in route["body_html"]


def test_unknown_article_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(article_page("no-such-journal", db=_orm_db([_article()])))

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()
