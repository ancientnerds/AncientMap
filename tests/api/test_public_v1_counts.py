# SPDX-License-Identifier: AGPL-3.0-only
"""The public API's counts and breakdowns: /status, /sources/{id}, /stats, /news.

Two readings here failed ``mypy api/`` (HUMAN_ONLY A7) without being wrong at runtime:
``.scalar()`` of a COUNT(*) is typed Optional although the count always has its one row
(now ``.scalar_one()``), and ``row.count`` of a grouped row is typed as the tuple method
``count`` although SQLAlchemy's Row returns the column of that name (now the two-column
rows become the dict directly, ``dict(result.tuples())``). These tests pin the responses. The grouped rows are real
SQLAlchemy Rows (built on SQLite in memory), so a column named "count" is exercised as
production sees it.

DB-less on tests/fake_sql.RecordingSession: statements are recorded, and each is answered
with the rows of the first fragment it contains.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.fake_sql import RecordingSession


def _rows(select_sql: str) -> list[Any]:
    """Real Row objects of a SELECT, from SQLite in memory."""
    with create_engine("sqlite://").connect() as conn:
        return list(conn.execute(text(select_sql)).fetchall())


@pytest.fixture
def client_for():
    from api.routes import public_v1

    def build(answers: dict[str, list[Any]]) -> TestClient:
        app = public_v1.create_public_api()
        db = RecordingSession(answers)
        app.dependency_overrides[public_v1.get_db] = lambda: db
        app.dependency_overrides[public_v1.rate_limit_dependency] = lambda: None
        return TestClient(app)

    with (
        patch.object(public_v1, "cache_get", return_value=None),
        patch.object(public_v1, "cache_set"),
    ):
        yield build


def test_status_reports_the_shown_sites_and_the_enabled_sources(client_for):
    client = client_for(
        {
            "COUNT(*) FROM unified_sites": [(4921,)],
            "COUNT(*) FROM source_meta": [(18,)],
        }
    )

    body = client.get("/status").json()

    assert (body["total_sites"], body["source_count"]) == (4921, 18)


def test_a_source_detail_breaks_its_sites_down_by_type_and_period(client_for):
    client = client_for(
        {
            "SELECT COUNT(*) FROM unified_sites": [(5,)],
            "SELECT site_type, COUNT(*)": _rows(
                "SELECT 'temple' AS site_type, 3 AS count UNION ALL SELECT 'tomb', 2"
            ),
            "END as period": _rows(
                "SELECT '3000 - 1500 BC' AS period, 4 AS count UNION ALL SELECT 'Unknown', 1"
            ),
        }
    )

    body = client.get("/sources/ancient_nerds").json()

    assert body["site_count"] == 5
    assert body["types"] == {"temple": 3, "tomb": 2}
    assert body["periods"] == {"3000 - 1500 BC": 4, "Unknown": 1}


def test_stats_count_the_sites_per_source(client_for):
    client = client_for(
        {
            "SELECT COUNT(*) FROM unified_sites": [(7,)],
            "SELECT source_id, COUNT(*)": _rows(
                "SELECT 'ancient_nerds' AS source_id, 5 AS count UNION ALL SELECT 'lyra', 2"
            ),
        }
    )

    body = client.get("/stats").json()

    assert body["total_sites"] == 7
    assert body["by_source"] == {"ancient_nerds": 5, "lyra": 2}


def test_the_news_feed_pages_against_the_total_and_marks_every_item_ai_generated(client_for):
    story = SimpleNamespace(
        id=11,
        headline="New enclosure at Gobekli Tepe",
        summary="Excavators report a sixth enclosure.",
        timestamp_seconds=95,
        created_at=datetime(2026, 9, 20, 8, 0),
        video_id="abc123",
        video_title="Gobekli Tepe 2026",
        video_published_at=datetime(2026, 9, 19, 18, 0),
        video_thumbnail=None,
        channel_name="Ancient Nerds",
        site_id=None,
        site_name=None,
        site_lat=None,
        site_lon=None,
    )
    client = client_for({"SELECT COUNT(*)": [(21,)], "LIMIT :limit OFFSET :offset": [story]})

    body = client.get("/news?page=1&page_size=20").json()

    assert (body["total_count"], body["has_more"]) == (21, True)
    (item,) = body["items"]
    assert item["youtube_deep_url"] == "https://www.youtube.com/watch?v=abc123&t=95s"
    assert (item["ai_generated"], item["ai_system"]) == (True, "lyra-news")
