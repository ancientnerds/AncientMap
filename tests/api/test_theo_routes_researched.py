"""Owner routes and the 'researched' status (spec 2.5)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import theo as theo_routes
from pipeline.lyra import theo_publishing
from tests.fake_sql import RecordingSession
from tests.pipeline.theo_publish_fixtures import WRITER, make_result

REQ = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(theo_routes, "_get_user_id", lambda req: "owner-1")
    app = FastAPI()
    app.include_router(theo_routes.router)
    with TestClient(app) as test_client:
        yield test_client


def test_the_stream_of_a_researched_run_ends_at_once(client, monkeypatch):
    session = RecordingSession(
        {
            "SELECT user_id, status FROM research_requests": [
                SimpleNamespace(user_id="owner-1", status="researched")
            ]
        }
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)
    response = client.get(f"/research/{REQ}/stream")
    assert response.status_code == 200
    assert "event: done" in response.text
    assert '"status": "researched"' in response.text


def test_the_detail_of_a_researched_run_carries_its_dossier(client, monkeypatch):
    dossier = {"artifact_id": 8812, "version": 1, "counts": {"final_claims": 38}}
    row = SimpleNamespace(
        id=REQ,
        user_id="owner-1",
        question="Who cut the Baalbek monoliths?",
        status="researched",
        result_json=json.dumps({"dossier": dossier, "title": None}),
        pipeline_trace=None,
        debug_log=None,
        sites_found=3697,
        tools_used=12,
        total_tokens=12345678,
        llm_calls=399,
        duration_ms=39_600_000,
        error_message=None,
        created_at=datetime(2026, 9, 27, 20, 0),
        completed_at=datetime(2026, 9, 28, 9, 15),
    )
    session = RecordingSession({"pipeline_trace, debug_log, sites_found": [row]})
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)
    response = client.get(f"/research/{REQ}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "researched"
    assert body["result"] == {"dossier": dossier, "title": None}
    assert body["completed_at"] == "2026-09-28T09:15:00"


def test_deleting_a_researched_row_archives_it_first(client, monkeypatch):
    session = RecordingSession(
        {
            "SELECT user_id, status, is_public FROM research_requests": [
                SimpleNamespace(user_id="owner-1", status="researched", is_public=False)
            ]
        }
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)
    response = client.delete(f"/research/{REQ}")
    assert response.status_code == 200
    statements = session.statements()
    archive = next(
        i for i, sql in enumerate(statements) if "INSERT INTO research_requests_archive" in sql
    )
    delete = next(i for i, sql in enumerate(statements) if "DELETE FROM research_requests" in sql)
    assert archive < delete


def test_the_route_uses_the_shared_slug_rule_and_side_effects():
    assert not hasattr(theo_routes, "_make_slug")
    assert theo_routes.pick_slug is theo_publishing.pick_slug
    assert theo_routes.run_publish_side_effects is theo_publishing.run_publish_side_effects
    assert "researched" in theo_routes._STREAM_TERMINAL_STATUSES


def test_the_founder_route_refuses_a_paper_its_page_could_not_render(client, monkeypatch):
    # A Claude-written paper, unpublished, edited and re-approved here: its second
    # evidence anchor no longer opens a paragraph, so /research/{slug} would 500.
    result = {**make_result(), "writer": WRITER, "approved_by": "QuetzalcoatlCat"}
    result["evidence"][1]["anchor_text"] = "No paragraph of this paper opens with these words"
    row = SimpleNamespace(
        id=REQ,
        user_id="owner-1",
        status="completed",
        is_public=False,
        result_json=json.dumps(result),
        question="Who cut the Baalbek monoliths?",
    )
    session = RecordingSession(
        {"SELECT id::text, user_id, status, is_public, result_json, question": [row]}
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)

    async def fresh_roles(user):
        return []

    monkeypatch.setattr(theo_routes, "_require_fresh_researcher", fresh_roles)

    def announce(urls):
        # An Exception, not pytest.fail: a BaseException would stop the TestClient's portal.
        raise AssertionError("the refused paper was announced")

    monkeypatch.setattr(theo_routes, "indexnow_submit", announce)
    client.app.dependency_overrides[theo_routes.get_current_user] = lambda: SimpleNamespace(
        id=1, discord_id="owner-1", username="QuetzalcoatlCat"
    )

    response = client.post(f"/research/{REQ}/publish")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "the paper page would not render",
        "issues": ["ev-02: anchor_text matches 0 paragraphs (needs exactly 1)"],
    }
    assert not [sql for sql in session.statements() if "UPDATE research_requests" in sql]


def test_a_founder_publish_records_the_review_in_the_disclosure(client, monkeypatch):
    # A founder who publishes a Claude-written paper here approved it (every
    # block, or approved_by): the page's disclosure line must not keep saying
    # "published automatically ... without human editorial review".
    result = {**make_result(), "writer": WRITER, "approved_by": "QuetzalcoatlCat"}
    row = SimpleNamespace(
        id=REQ,
        user_id="owner-1",
        status="completed",
        is_public=False,
        result_json=json.dumps(result),
        question="Who cut the Baalbek monoliths?",
    )
    session = RecordingSession(
        {"SELECT id::text, user_id, status, is_public, result_json, question": [row]}
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)

    async def fresh_roles(user):
        return []

    monkeypatch.setattr(theo_routes, "_require_fresh_researcher", fresh_roles)
    effects: list[dict] = []
    monkeypatch.setattr(
        theo_routes,
        "run_publish_side_effects",
        lambda **kwargs: (
            effects.append(kwargs)
            or {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}
        ),
    )
    client.app.dependency_overrides[theo_routes.get_current_user] = lambda: SimpleNamespace(
        id=1, discord_id="owner-1", username="QuetzalcoatlCat"
    )

    response = client.post(f"/research/{REQ}/publish")

    assert response.status_code == 200
    params = next(p for sql, p in session.log if "UPDATE research_requests" in sql)
    assert params["username"] == "QuetzalcoatlCat"
    assert json.loads(params["result"])["writer"] == {
        **WRITER,
        "published": "manual",
        "human_review": True,
    }
    (call,) = effects
    assert call["author_username"] == "QuetzalcoatlCat"
