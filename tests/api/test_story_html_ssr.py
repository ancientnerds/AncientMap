# SPDX-License-Identifier: AGPL-3.0-only
"""Die Story-Routen übergeben Payload-Dicts an den SSR-Splice (react-ssr Task 14).

DB-los: die Routen werden direkt mit einer Fake-ORM-Session aufgerufen; der
Sidecar (render_page) und die gebaute Shell (render_app_shell) sind gemockt.
Geprüft wird der Payload-Vertrag Richtung React — die Feldnamen hier sind
der Vertrag, den anRoute.ts (StoryRoute/StoryArchiveRoute) deklariert: rohe
snake_case-Zeilenfelder. Quellen-Filter, &t=-Deeplink, Blurbs und
Datumsformat leben in src/seo/ bzw. StoryPage/StoryArchivePage.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.routes.articles_html import news_archive_page, story_page


def _orm_db(*, first=None, rows=None, count=0) -> MagicMock:
    """Eine MagicMock-Query, deren Kettenglieder auf sich selbst zeigen.

    Deckt beide Query-Formen der Routen ab: .first() für die Story selbst,
    .all() für Related/Listing, .count() für die Pagination.
    """
    q = MagicMock()
    for name in ("join", "filter", "options", "order_by", "offset", "limit"):
        getattr(q, name).return_value = q
    q.first.return_value = first
    q.all.return_value = rows or []
    q.count.return_value = count
    db = MagicMock()
    db.query.return_value = q
    return db


def _patched():
    return (
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")),
        patch("api.seo_shell.render_app_shell", return_value="<html>ok</html>"),
    )


def _item(**overrides) -> SimpleNamespace:
    video = SimpleNamespace(
        id="abc123",
        title="Sun Chariot's Lost Twin?",
        published_at=datetime(2026, 3, 14, 9, 30),
        channel=SimpleNamespace(name="Ancient Architects"),
    )
    site = SimpleNamespace(
        id="1b2c3d4e-0000-4000-8000-000000000000",
        name="Trundholm Mose",
        country="Denmark",
        source_id="ancient_nerds",
        # Seit 2026-08-21 im Payload: die Story-Seite rendert damit dieselben
        # Badges wie die Karten (SiteBadges/CountryFlag).
        site_type="Burial mound",
        period_name="Bronze Age",
        period_start=-1400,
    )
    row = {
        "id": 4711,
        "headline": "Sun Chariot fragment found",
        "summary": "A second fragment.",
        "facts": ["Second fragment found"],
        "post_text": "Archaeologists re-examined spoil heaps.",
        "site_name_extracted": None,
        "screenshot_url": "/data/news/screenshots/4711.jpg",
        "news_category": "Excavation",
        "web_sources": [
            {"url": "https://en.natmus.dk/sun-chariot/", "title": "The Sun Chariot"},
            {"url": "javascript:alert(1)", "title": "evil"},
        ],
        "timestamp_seconds": 754,
        "speculative_tag": None,
        "significance": 8,
        "created_at": datetime(2026, 3, 15, 8, 0),
        "video": video,
        "site": site,
        "site_id": site.id,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def test_story_hands_the_full_raw_payload():
    item = _item()
    related = [_item(id=4600, headline="Trundholm bog survey planned")]
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(
            story_page("sun-chariot-fragment-found-4711", db=_orm_db(first=item, rows=related))
        )

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=3600"
    assert shell_mock.call_args[0][0] == "story.html"
    route = render_mock.call_args[0][0]
    assert route["type"] == "story"
    assert route["id"] == 4711
    assert route["headline"] == "Sun Chariot fragment found"
    assert route["summary"] == "A second fragment."
    assert route["facts"] == ["Second fragment found"]
    assert route["post_text"] == "Archaeologists re-examined spoil heaps."
    # Roh durchgereicht — der http(s)-Filter ist eine Anzeigeentscheidung
    # und lebt in StoryPage; der javascript:-Eintrag darf dort nie ein href
    # werden (render.test.tsx beweist das).
    assert route["web_sources"] == item.web_sources
    assert route["timestamp_seconds"] == 754
    assert route["screenshot_url"] == "/data/news/screenshots/4711.jpg"
    # Video-Datum gewinnt vor created_at; roher ISO-String, Format in TS.
    assert route["published_at"] == "2026-03-14T09:30:00"
    assert route["youtube_url"] == "https://www.youtube.com/watch?v=abc123"
    assert route["video_title"] == "Sun Chariot's Lost Twin?"
    assert route["channel_name"] == "Ancient Architects"
    assert route["site_name"] == "Trundholm Mose"
    assert route["site_id"] == "1b2c3d4e-0000-4000-8000-000000000000"
    assert route["site_country"] == "Denmark"
    assert route["site_curated"] is True
    # Badge-Felder: dieselben drei, die der Feed den Karten gibt, plus der
    # Score für den Signifikanz-Stempel.
    assert route["site_type"] == "Burial mound"
    assert route["site_period_name"] == "Bronze Age"
    assert route["site_period_start"] == -1400
    assert route["significance"] == 8
    assert route["related"] == [
        {
            "slug": "trundholm-bog-survey-planned-4600",
            "headline": "Trundholm bog survey planned",
            "kind": "site",
        }
    ]


def test_bulk_imported_site_is_not_marked_curated():
    """/sites/{country}/{slug} serviert nur kuratierte Sites — der Detail-Link
    entsteht in StoryPage nur mit site_curated (268-404s-Bug, 2026-08-09)."""
    item = _item()
    item.site.source_id = "wikidata"
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(story_page("sun-chariot-fragment-found-4711", db=_orm_db(first=item)))

    assert render_mock.call_args[0][0]["site_curated"] is False


def test_story_without_video_and_site_falls_back():
    item = _item(video=None, site=None, site_id=None, site_name_extracted="Somewhere")
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(story_page("sun-chariot-fragment-found-4711", db=_orm_db(first=item)))

    route = render_mock.call_args[0][0]
    assert route["published_at"] == "2026-03-15T08:00:00"  # created_at
    assert route["youtube_url"] == ""
    assert route["video_title"] == ""
    assert route["channel_name"] == ""
    assert route["site_name"] == "Somewhere"  # der rohe Extraktor-Fund
    assert route["site_id"] == ""
    assert route["site_curated"] is False


def test_unknown_story_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(story_page("no-such-story-999", db=_orm_db(first=None)))

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()


def test_malformed_slug_is_a_404():
    """Kein numerischer ID-Suffix → gar keine DB-Abfrage nach der Story."""
    render, shell = _patched()
    with render as render_mock, shell:
        resp = asyncio.run(story_page("no-id-suffix", db=_orm_db(first=None)))

    assert resp.status_code == 404
    render_mock.assert_not_called()


def test_story_archive_keeps_its_pagination():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(news_archive_page(2, db=_orm_db(rows=[_item()], count=120)))

    assert resp.status_code == 200
    # Kürzerer Cache als die Einzelstory — das Listing ändert sich täglich.
    assert resp.headers["cache-control"] == "public, max-age=1800"
    assert shell_mock.call_args[0][0] == "story.html"
    route = render_mock.call_args[0][0]
    assert route["type"] == "storyArchive"
    assert route["page"] == 2
    assert route["total_pages"] == 3  # ceil(120 / 50)
    assert route["total"] == 120
    assert route["stories"] == [
        {
            "slug": "sun-chariot-fragment-found-4711",
            "headline": "Sun Chariot fragment found",
            "summary": "A second fragment.",
            "published_at": "2026-03-14T09:30:00",
            "news_category": "Excavation",
            "site_name": "Trundholm Mose",
            "channel_name": "Ancient Architects",
            "speculative_tag": None,
            "screenshot_url": "/data/news/screenshots/4711.jpg",
        }
    ]


def test_out_of_range_page_is_a_404_without_touching_the_renderer():
    render, shell = _patched()
    with render as render_mock, shell as shell_mock:
        resp = asyncio.run(news_archive_page(4, db=_orm_db(count=120)))  # 3 Seiten

    assert resp.status_code == 404
    render_mock.assert_not_called()
    shell_mock.assert_not_called()
