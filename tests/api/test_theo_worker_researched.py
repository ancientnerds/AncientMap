"""The worker's research-only branch (spec 2.4): researched, dossier summary, no auto-publish."""

from __future__ import annotations

import json
from types import SimpleNamespace

from api.services import theo_worker as tw
from tests.fake_sql import RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
SUMMARY = {
    "artifact_id": 8812,
    "version": 1,
    "created_at": "2026-09-28T09:14:03+00:00",
    "counts": {
        "angles": 7,
        "findings": 2937,
        "sources": 3697,
        "final_claims": 38,
        "revised_claims": 5,
        "speculative_claims": 9,
        "images": 150,
    },
    "archive": {
        "cited_sources": 171,
        "full_text": 150,
        "abstract_only": 12,
        "missing": 6,
        "tdm_reserved": 3,
    },
}


def _run(monkeypatch, session: RecordingSession) -> dict[str, list]:
    calls: dict[str, list] = {
        "credits": [],
        "corpus": [],
        "explored": [],
        "thinking": [],
        "webhook": [],
    }
    ctx = SimpleNamespace(
        error="",
        quota_exhausted=False,
        dossier_summary=SUMMARY,
        debug_log=[{"msg": "x"}],
        total_tokens=1234,
        llm_call_count=56,
        registry=SimpleNamespace(sources={"a1b2c3d4e5f6": object()}),
        specialist_analyses={"geo": []},
    )

    class FakeOrchestrator:
        async def run(self, question, emit, **kwargs):
            return ctx

    async def fake_corpus(ctx_, request_id, artifact):
        calls["corpus"].append((request_id, artifact))

    monkeypatch.setattr(tw, "get_session", lambda: session)
    monkeypatch.setattr(tw, "get_redis_client", lambda: None)
    monkeypatch.setattr(tw, "_plan_balance_snapshot", lambda: None)
    monkeypatch.setattr(tw, "_record_plan_cost", lambda request_id, start: None)
    monkeypatch.setattr(
        tw, "_deduct_credits", lambda request_id: calls["credits"].append(request_id)
    )
    monkeypatch.setattr(tw, "_persist_training_corpus", fake_corpus)
    monkeypatch.setattr(tw, "_live_events", {})
    monkeypatch.setattr(
        "pipeline.lyra.convergence_orchestrator.ConvergenceOrchestrator", FakeOrchestrator
    )
    monkeypatch.setattr(
        "pipeline.lyra.research_graph.mark_node_explored",
        lambda request_id: calls["explored"].append(request_id),
    )
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details=None: calls["thinking"].append((kind, summary, details)),
    )
    monkeypatch.setattr(
        "api.services.notify.send_discord_webhook",
        lambda payload: calls["webhook"].append(payload) or False,
    )
    return calls


async def test_success_ends_researched_with_the_dossier_and_no_publish(monkeypatch):
    session = RecordingSession(
        {"SET status = 'running'": [object()], "SET status = 'researched'": [object()]}
    )
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "Who cut the Baalbek monoliths?", None, is_batch=True)

    update = session.statement_with("SET status = 'researched'")
    params = next(p for sql, p in session.log if sql == update)
    assert json.loads(params["result"]) == {"dossier": SUMMARY, "title": None}
    assert "status = 'running'" in update
    assert not [sql for sql in session.statements() if "is_public = TRUE" in sql]
    assert calls["credits"] == [REQ]
    assert calls["corpus"] == [(REQ, None)]
    assert calls["explored"] == [REQ]
    kind, _summary, details = calls["thinking"][0]
    assert kind == "run_event"
    assert details["event"] == "dossier_ready"
    assert len(calls["webhook"]) == 1
    assert tw._live_events[REQ][-1] == {"type": "done", "status": "researched"}


async def test_a_ui_run_is_researched_too_but_touches_no_graph_node(monkeypatch):
    session = RecordingSession(
        {"SET status = 'running'": [object()], "SET status = 'researched'": [object()]}
    )
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "A website question", None, is_batch=False)

    assert session.statement_with("SET status = 'researched'")
    assert calls["explored"] == []
    assert calls["thinking"] == []
    assert len(calls["webhook"]) == 1


async def test_a_run_cancelled_mid_flight_is_not_announced(monkeypatch):
    # The researched UPDATE is guarded on status='running'; a DELETE flipped the row.
    session = RecordingSession({"SET status = 'running'": [object()]})
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "q", None, is_batch=True)

    assert calls["explored"] == []
    assert calls["webhook"] == []


def test_the_auto_publish_path_is_gone():
    assert not hasattr(tw, "_auto_publish")
    assert not hasattr(tw, "_paper_artifact")
