"""Curator pass — apply logic + scheduling (specs §3, §6)."""

import json
from datetime import UTC, datetime, timedelta

from pipeline.lyra.curator import CURATOR_SCHEMA, _apply_curator_output, thinking_pass_due


class _FakeSession:
    def __init__(self, existing_status=None):
        self.executed = []
        self._existing_status = existing_status
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params or {}))

        class _R:
            def fetchone(inner):
                if "SELECT status FROM knowledge_claims" in str(stmt) and self._existing_status:
                    return type("Row", (), {"status": self._existing_status})()
                return None

        return _R()

    def commit(self):
        self.committed = True


class _FakeCtxSession:
    """Context-manager stand-in for pipeline.database.get_session()."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _out(**kw):
    base = {
        "claim_updates": [],
        "connections": [],
        "hypotheses": [],
        "hypothesis_outcomes": [],
        "summary": "s",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# _apply_curator_output — connections
# ---------------------------------------------------------------------------


def test_connection_nodes_inserted_with_question():
    s = _FakeSession()
    stats = _apply_curator_output(
        s, _out(connections=[{"label": "A ↔ B", "question": "Does A explain B?"}])
    )
    assert stats["connections"] == 1
    stmt, params = next(e for e in s.executed if "INSERT INTO research_nodes" in e[0])
    assert params["kind"] == "connection"
    assert params["question"] == "Does A explain B?"
    # The connection node gets `connects` edges to its endpoints (data model).
    assert any("'connects'" in e[0] for e in s.executed)


def test_connection_cap_and_junk_guard():
    conns = [{"label": f"T{i} ↔ U{i}", "question": "q"} for i in range(9)]
    conns.append({"label": "null", "question": "q"})
    s = _FakeSession()
    stats = _apply_curator_output(s, _out(connections=conns))
    assert stats["connections"] == 5  # cap
    assert all("null" not in str(p) for _, p in s.executed if p)


# ---------------------------------------------------------------------------
# _apply_curator_output — claims (refuted terminal, paper_ids provenance)
# ---------------------------------------------------------------------------


def test_refuted_claim_never_reopens():
    s = _FakeSession(existing_status="refuted")
    stats = _apply_curator_output(
        s,
        _out(claim_updates=[{"text": "The X claim", "status": "established", "confidence": 0.9}]),
    )
    assert stats["claims"] == 0  # update skipped
    assert not any("UPDATE knowledge_claims" in e[0] for e in s.executed)


def test_claim_insert_carries_paper_ids():
    s = _FakeSession()
    stats = _apply_curator_output(
        s,
        _out(
            claim_updates=[
                {
                    "text": "Claim A",
                    "status": "open",
                    "confidence": 0.5,
                    "paper_ids": ["p1", "p2"],
                }
            ]
        ),
    )
    assert stats["claims"] == 1
    stmt, params = next(e for e in s.executed if "INSERT INTO knowledge_claims" in e[0])
    assert json.loads(params["paper_ids"]) == ["p1", "p2"]


def test_claim_update_dedup_appends_paper_ids():
    s = _FakeSession(existing_status="open")
    stats = _apply_curator_output(
        s,
        _out(
            claim_updates=[
                {
                    "text": "Claim A",
                    "status": "established",
                    "confidence": 0.9,
                    "paper_ids": ["p3"],
                }
            ]
        ),
    )
    assert stats["claims"] == 1
    stmt, params = next(e for e in s.executed if "UPDATE knowledge_claims" in e[0])
    assert "jsonb_agg(DISTINCT e)" in stmt
    assert json.loads(params["paper_ids"]) == ["p3"]


# ---------------------------------------------------------------------------
# _apply_curator_output — hypothesis outcomes
# ---------------------------------------------------------------------------


def test_hypothesis_outcome_updates_node():
    s = _FakeSession()
    _apply_curator_output(
        s, _out(hypothesis_outcomes=[{"node_label": "If X then Z", "outcome": "refuted"}])
    )
    stmt, params = next(e for e in s.executed if "SET outcome" in e[0])
    assert params["outcome"] == "refuted"


# ---------------------------------------------------------------------------
# thinking_pass_due — scheduling window
# ---------------------------------------------------------------------------


def test_thinking_pass_due_window():
    mon_night = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)  # Monday 03:00 UTC
    fri_night = datetime(2026, 8, 7, 3, 0, tzinfo=UTC)  # Friday — research days
    mon_noon = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    assert thinking_pass_due(mon_night, None) is True
    assert thinking_pass_due(fri_night, None) is False
    assert thinking_pass_due(mon_noon, None) is False
    assert thinking_pass_due(mon_night, mon_night - timedelta(hours=2)) is False  # ran already


def test_schema_has_required_sections():
    assert set(CURATOR_SCHEMA["required"]) >= {"claim_updates", "connections", "hypotheses"}


# ---------------------------------------------------------------------------
# run_curator_pass — wiring (best-effort orchestration)
# ---------------------------------------------------------------------------


def test_run_curator_pass_empty_output_skips_apply(monkeypatch):
    import pipeline.lyra.curator as curator

    monkeypatch.setattr(curator, "_gather_inputs", lambda session: {"papers": []})
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())
    monkeypatch.setattr("pipeline.lyra.minimax_shared.structured_llm_call", lambda **kw: {})

    applied = {}
    monkeypatch.setattr(
        curator,
        "_apply_curator_output",
        lambda session, out: applied.setdefault("called", True),
    )
    logged = {}
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda *a, **kw: logged.setdefault("called", True),
    )

    curator.run_curator_pass()

    assert "called" not in applied
    assert "called" not in logged


def test_run_curator_pass_success_logs_with_stats(monkeypatch):
    import pipeline.lyra.curator as curator

    monkeypatch.setattr(curator, "_gather_inputs", lambda session: {"papers": []})
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())
    monkeypatch.setattr(
        "pipeline.lyra.minimax_shared.structured_llm_call",
        lambda **kw: {"summary": "did stuff"},
    )
    monkeypatch.setattr(
        curator,
        "_apply_curator_output",
        lambda session, out: {"claims": 1, "connections": 2, "hypotheses": 0, "outcomes": 0},
    )
    logged = {}

    def fake_log(kind, summary, details):
        logged["kind"] = kind
        logged["summary"] = summary
        logged["details"] = details

    monkeypatch.setattr("pipeline.lyra.thinking_log.log_thinking", fake_log)
    monkeypatch.setattr("api.services.notify.send_discord_webhook", lambda payload: True)

    curator.run_curator_pass()

    assert logged["kind"] == "curator"
    assert "1 claims" in logged["summary"]
    assert logged["details"]["llm_summary"] == "did stuff"


def test_run_curator_pass_swallows_exceptions(monkeypatch, caplog):
    import pipeline.lyra.curator as curator

    def boom(session):
        raise RuntimeError("db down")

    monkeypatch.setattr(curator, "_gather_inputs", boom)
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())

    with caplog.at_level("ERROR"):
        curator.run_curator_pass()  # must not raise

    assert any("curator pass failed" in r.message for r in caplog.records)
