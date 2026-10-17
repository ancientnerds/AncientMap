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

import pytest

from api.routes.research_html import (
    fetch_paper,
    research_listing,
    research_medium_copy,
    research_paper_page,
)
from pipeline.article_html_renderer import markdown_to_html
from pipeline.research_html_renderer import PaperPageError
from tests.fake_sql import RecordingSession


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
        # PAPER_EXTRAS_COLUMNS: jsonb NULL for every paper published before
        # the studio (the keys are absent from its result_json).
        "evidence": None,
        "videos": None,
        "corrections": None,
        "writer": None,
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
    # Genau die Felder, die eine Karte druckt (PaperCard plus ihre Fußzeile) —
    # kein Feld mehr, keins weniger. quality_score, license und die Frage des
    # Papers gehören der Detailseite und /api/v1/research.
    assert route == {
        "type": "researchIndex",
        "papers": [
            {
                "slug": "obsidian-trade-networks-anatolia",
                "title": "Obsidian Trade Networks in Neolithic Anatolia",
                "summary": "Two exchange spheres centred on Cappadocia and Lake Van.",
                "hero_image_url": "https://ancientnerds.com/data/research/obsidian/hero.webp",
                "author": "Theo",
                "published_at": "2026-07-02T04:15:00",
                "cited_sources": 0,
                "word_count": 4200,
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


# ── Claude-written papers (studio spec 2026-09-26 §2.7, §3.7) ─────────────────

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}
OLD_KEYS = {
    "type",
    "slug",
    "title",
    "summary",
    "author",
    "published_at",
    "hero_image_url",
    "body_html",
}
# An evidence anchor opens its paragraph and has at least MIN_ANCHOR_CHARS (20)
# normalised characters (contract C9), which the fixture's "Obsidian moved
# far." paragraph is too short for.
EVIDENCE_REPORT = "## Findings\n\nObsidian moved far across Anatolia."
EVIDENCE_ANCHOR = "Obsidian moved far across"
VIDEO = {
    "youtube_id": "dQw4w9WgXcQ",
    "title": "Obsidian roads",
    "published_at": "2026-10-01T15:00:00+00:00",
    "evidence_timestamps": {},
}


def _route_for(row) -> dict:
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    return render_mock.call_args[0][0]


def test_a_paper_without_extras_keeps_its_exact_payload():
    """All papers published before the studio: same keys, same body bytes."""
    route = _route_for(_paper_row())
    assert set(route) == OLD_KEYS
    assert route["body_html"] == markdown_to_html("## Findings\n\nObsidian moved far.")


def test_writer_corrections_and_videos_join_the_payload():
    route = _route_for(
        _paper_row(
            writer=WRITER,
            corrections=[{"date": "2026-10-02", "text": "Typo in a date."}],
            videos=[VIDEO],
        )
    )
    assert route["writer"] == WRITER
    assert route["corrections"] == [
        {
            "date": "2026-10-02",
            "text": "Typo in a date.",
            "evidence_id": None,
            "holds_anchor": False,
        }
    ]
    assert route["videos"] == [
        {
            "youtube_id": "dQw4w9WgXcQ",
            "title": "Obsidian roads",
            "published_at": "2026-10-01T15:00:00+00:00",
            "poster": None,
        }
    ]


def test_a_registered_poster_joins_the_video_payload():
    """Owner decision #13: our own studio thumbnail, under the paper's own request id."""
    poster = "/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg"
    route = _route_for(_paper_row(videos=[{**VIDEO, "poster": poster}]))
    assert route["videos"][0]["poster"] == poster


def test_a_poster_from_another_papers_folder_fails_the_page():
    poster = "/data/research-images/99999999-8888-7777-6666-555555555555/video_dQw4w9WgXcQ.jpg"
    row = _paper_row(videos=[{**VIDEO, "poster": poster}])
    render, shell = _patched()
    with render as render_mock, shell, pytest.raises(PaperPageError, match="poster must be"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    render_mock.assert_not_called()


def test_evidence_paragraphs_carry_their_anchor_and_video_link():
    route = _route_for(
        _paper_row(
            published_report=EVIDENCE_REPORT,
            evidence=[{"id": "ev-01", "anchor_text": EVIDENCE_ANCHOR, "claim": "It did."}],
            videos=[
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Obsidian roads",
                    "published_at": "2026-10-01",
                    "evidence_timestamps": {"ev-01": 75},
                }
            ],
        )
    )
    body = route["body_html"]
    assert (
        '<p id="ev-01" class="theo-evidence">Obsidian moved far across Anatolia. '
        '<a class="theo-evidence-video"' in body
    )
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=75s" in body
    assert "Video at 1:15</a>" in body
    # The evidence entries stay server-side: their anchors are in body_html.
    assert "evidence" not in route


def test_an_evidence_anchor_that_resolves_nowhere_fails_the_page():
    row = _paper_row(
        published_report=EVIDENCE_REPORT,
        evidence=[{"id": "ev-01", "anchor_text": "Nothing in this paper says so", "claim": "x"}],
    )
    render, shell = _patched()
    with render as render_mock, shell, pytest.raises(PaperPageError, match="ev-01 matches 0"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    render_mock.assert_not_called()


def test_malformed_extras_fail_the_page():
    row = _paper_row(writer={**WRITER, "published": "sometimes"})
    render, shell = _patched()
    with render, shell, pytest.raises(PaperPageError, match="writer.published"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))


def test_the_medium_copy_gets_no_evidence_anchors_and_no_disclosure_line():
    """Owner decision #23: the AI disclosure line stays off the Medium copy.

    The line is a React component of the paper page (PaperDisclosure); the
    Medium copy is server HTML from the report alone.
    """
    row = _paper_row(
        published_report=EVIDENCE_REPORT,
        evidence=[{"id": "ev-01", "anchor_text": EVIDENCE_ANCHOR, "claim": "x"}],
        writer=WRITER,
    )
    resp = asyncio.run(research_medium_copy("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    body = resp.body.decode()
    assert resp.status_code == 200
    assert "Obsidian moved far across Anatolia." in body
    assert 'id="ev-01"' not in body
    assert "theo-paper-disclosure" not in body
    assert "Researched by Theo" not in body


def test_fetch_paper_selects_the_extras_columns():
    db = RecordingSession({"WHERE r.slug = :slug": [_paper_row()]})
    fetch_paper("obsidian-trade-networks-anatolia", db)
    sql = db.statement_with("WHERE r.slug = :slug")
    for key in ("evidence", "videos", "corrections", "writer"):
        assert f"r.result_json::jsonb->'{key}' AS {key}" in sql
