# SPDX-License-Identifier: AGPL-3.0-only
"""GET /api/v1/research/{slug} carries the extras of a Claude-written paper.

Studio spec 2026-09-26 §2.7/§3.7: evidence (with deep links to #ev-NN), videos,
corrections and the writer record are open data like the paper itself (CC BY
4.0). An older paper answers with empty lists and writer null, and its
Markdown content is untouched: the evidence never enters the report text.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.fake_sql import RecordingSession

SLUG = "obsidian-trade-networks-anatolia"
PAPER_ID = "7f00aa00-0000-4000-8000-000000000000"
# Owner decision #13: our own studio thumbnail, stored as its web path.
POSTER = f"/data/research-images/{PAPER_ID}/video_dQw4w9WgXcQ.jpg"
WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}


def _row(**overrides) -> SimpleNamespace:
    row = {
        "id": PAPER_ID,
        "slug": SLUG,
        "question": "How did obsidian move through Neolithic Anatolia?",
        "published_by": "Theo",
        "published_at": datetime(2026, 10, 1, 4, 15),
        "sites_found": 12,
        "title": "Obsidian Trade Networks in Neolithic Anatolia",
        "card_description": "Two exchange spheres.",
        "score": "91",
        "badge": "Claim-checked",
        "word_count": "5200",
        "hero_src": None,
        "published_report": "## Findings\n\nObsidian moved far [1].",
        "report": "raw draft",
        "evidence": None,
        "videos": None,
        "corrections": None,
        "writer": None,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _get(row):
    from api.routes import public_v1

    app = public_v1.create_public_api()
    db = RecordingSession({"WHERE r.slug = :slug": [row]})
    app.dependency_overrides[public_v1.get_db] = lambda: db
    app.dependency_overrides[public_v1.rate_limit_dependency] = lambda: None
    with (
        patch.object(public_v1, "cache_get", return_value=None),
        patch.object(public_v1, "cache_set"),
    ):
        resp = TestClient(app, raise_server_exceptions=False).get(f"/research/{SLUG}")
    return resp, db


def test_an_older_paper_answers_with_empty_extras():
    resp, _ = _get(_row())
    body = resp.json()
    assert resp.status_code == 200
    assert body["content"] == "## Findings\n\nObsidian moved far [1]."
    assert body["evidence"] == []
    assert body["videos"] == []
    assert body["corrections"] == []
    assert body["writer"] is None
    assert body["ai_system"] == "theo-research"


def test_a_claude_written_paper_exposes_evidence_videos_corrections_and_writer():
    resp, _ = _get(
        _row(
            evidence=[
                {
                    "id": "ev-01",
                    "anchor_text": "Obsidian moved far",
                    "claim": "Obsidian moved hundreds of kilometres.",
                    "quote": "moved far",
                }
            ],
            videos=[
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Obsidian roads",
                    "published_at": "2026-10-01T15:00:00+00:00",
                    "evidence_timestamps": {"ev-01": 75},
                    "poster": POSTER,
                },
                {
                    "youtube_id": "aaaaaaaaaaa",
                    "title": "Obsidian roads, the short",
                    "published_at": "2026-10-03T15:00:00+00:00",
                    "evidence_timestamps": {},
                },
            ],
            corrections=[{"date": "2026-10-02", "text": "Typo in a date."}],
            writer=WRITER,
        )
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["evidence"] == [
        {
            "id": "ev-01",
            "claim": "Obsidian moved hundreds of kilometres.",
            "url": f"https://ancientnerds.com/research/{SLUG}#ev-01",
        }
    ]
    assert body["videos"] == [
        {
            "youtube_id": "dQw4w9WgXcQ",
            "title": "Obsidian roads",
            "published_at": "2026-10-01T15:00:00+00:00",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "evidence_timestamps": {"ev-01": 75},
            "poster": POSTER,
        },
        {
            "youtube_id": "aaaaaaaaaaa",
            "title": "Obsidian roads, the short",
            "published_at": "2026-10-03T15:00:00+00:00",
            "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "evidence_timestamps": {},
            "poster": None,
        },
    ]
    assert body["corrections"] == [
        {"date": "2026-10-02", "text": "Typo in a date.", "evidence_id": None}
    ]
    assert body["writer"] == WRITER
    assert body["ai_system"] == "theo-research (MiniMax-M3) + claude-opus-5-5 (claude-code)"
    assert body["ai_generated"] is True


def test_the_detail_query_selects_the_extras():
    _, db = _get(_row())
    sql = db.statement_with("WHERE r.slug = :slug")
    for key in ("evidence", "videos", "corrections", "writer"):
        assert f"r.result_json::jsonb->'{key}' AS {key}" in sql


def test_malformed_extras_are_a_server_error_not_a_silent_omission():
    resp, _ = _get(_row(writer={**WRITER, "human_review": "no"}))
    assert resp.status_code == 500
