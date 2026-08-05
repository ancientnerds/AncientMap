"""Curator pass — apply logic + scheduling (specs §3, §6).

2026-08-05 review additions: C1 (gen_random_uuid PK fix on connects edges),
C2 (_paper_excerpt splits references off the tail), I3 (_build_user_message
budgets/orders the LLM payload), I4 (enum enforcement on claim status /
hypothesis outcome), I6 (rowcount-driven insert/update counting), I7
(paper backlog cursor tracks papers actually included, not pass time), I8
(established demoted to open below 2 external sources), I9 (cap-before-
filter is intentional — rewritten cap+junk test).

2026-08-05 final-gate additions: F1 (empty LLM output must ALSO close the
20h schedule gate — the test that pinned the opposite behavior is flipped),
F2 (_paper_excerpt now uses the PUBLIC, last-heading theo_citations.
split_artifact instead of the private first-match heading finder), F3
(_paper_excerpt takes a size budget so hypothesis tails don't starve the
rest of the message; _build_user_message warns when still over budget with
no papers left to drop; the summary surfaces dropped/demoted/deferred).
"""

import json
from datetime import UTC, datetime, timedelta

from pipeline.lyra.curator import (
    CURATOR_SCHEMA,
    _apply_curator_output,
    _build_user_message,
    _paper_excerpt,
    thinking_pass_due,
)


class _FakeSession:
    def __init__(self, existing_status=None, rowcount=1):
        self.executed = []
        self._existing_status = existing_status
        self._rowcount = rowcount
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params or {}))
        existing_status = self._existing_status
        rowcount = self._rowcount
        stmt_str = str(stmt)

        class _R:
            def __init__(self):
                self.rowcount = rowcount

            def fetchone(self):
                if "SELECT status FROM knowledge_claims" in stmt_str and existing_status:
                    return type("Row", (), {"status": existing_status})()
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


def test_connection_endpoints_use_gen_random_uuid_not_scalar_id():
    # C1: a scalar :id bind reused across a multi-row INSERT..SELECT (both
    # label-bridge twins matching) produces duplicate PKs and rolls back
    # the whole pass. The id must come from gen_random_uuid() in SQL.
    s = _FakeSession()
    _apply_curator_output(
        s, _out(connections=[{"label": "A ↔ B", "question": "Does A explain B?"}])
    )
    stmt, params = next(e for e in s.executed if "INSERT INTO research_edges" in e[0])
    assert "gen_random_uuid()" in stmt
    assert "id" not in params


def test_connection_insert_conflict_skips_edge_linking():
    # I6: ON CONFLICT DO NOTHING -> rowcount 0 -> _insert_topic_node returns
    # False -> _link_connection_endpoints must not even be attempted.
    s = _FakeSession(rowcount=0)
    stats = _apply_curator_output(
        s, _out(connections=[{"label": "A ↔ B", "question": "Does A explain B?"}])
    )
    assert stats["connections"] == 0
    assert not any("INSERT INTO research_edges" in e[0] for e in s.executed)


def test_connection_cap_before_junk_filter_wastes_a_slot():
    # I9: cap is applied BEFORE the junk-label filter (out.get(...)[:CAP]),
    # so a junk item occupying an early slot consumes that slot without
    # producing an insert — the wasted slot is NOT backfilled from beyond
    # the cap. This documents that as intended conservative behavior.
    conns = [{"label": "null", "question": "q"}]
    conns += [{"label": f"T{i} ↔ U{i}", "question": "q"} for i in range(9)]
    s = _FakeSession()
    stats = _apply_curator_output(s, _out(connections=conns))
    assert stats["connections"] == 4  # 5 cap slots, 1 wasted on the junk item
    assert all("null" not in str(p) for _, p in s.executed if p)


# ---------------------------------------------------------------------------
# _apply_curator_output — claims (refuted terminal, enum enforcement,
# established demotion, paper_ids provenance)
# ---------------------------------------------------------------------------


def test_refuted_claim_never_reopens():
    s = _FakeSession(existing_status="refuted")
    stats = _apply_curator_output(
        s,
        _out(claim_updates=[{"text": "The X claim", "status": "established", "confidence": 0.9}]),
    )
    assert stats["claims"] == 0  # update skipped
    assert not any("UPDATE knowledge_claims" in e[0] for e in s.executed)


def test_claim_with_invalid_status_is_dropped():
    # I4: LLM output is untrusted — _coerce_to_schema doesn't check enums.
    s = _FakeSession()
    stats = _apply_curator_output(s, _out(claim_updates=[{"text": "Bad claim", "status": "maybe"}]))
    assert stats["dropped"] == 1
    assert stats["claims"] == 0
    assert not any("INSERT INTO knowledge_claims" in e[0] for e in s.executed)


def test_established_claim_demoted_below_two_external_sources():
    # I8: spec §5 hard rule, enforced at apply time, not prompt-only.
    s = _FakeSession()
    stats = _apply_curator_output(
        s,
        _out(
            claim_updates=[
                {
                    "text": "Claim B",
                    "status": "established",
                    "confidence": 0.9,
                    "external_source_count": 1,
                }
            ]
        ),
    )
    assert stats["demoted"] == 1
    assert stats["claims"] == 1
    stmt, params = next(e for e in s.executed if "INSERT INTO knowledge_claims" in e[0])
    assert params["status"] == "open"


def test_established_claim_with_two_external_sources_not_demoted():
    s = _FakeSession()
    stats = _apply_curator_output(
        s,
        _out(
            claim_updates=[
                {
                    "text": "Claim C",
                    "status": "established",
                    "confidence": 0.9,
                    "external_source_count": 2,
                }
            ]
        ),
    )
    assert stats["demoted"] == 0
    stmt, params = next(e for e in s.executed if "INSERT INTO knowledge_claims" in e[0])
    assert params["status"] == "established"


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
                    "external_source_count": 2,
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
    stats = _apply_curator_output(
        s, _out(hypothesis_outcomes=[{"node_label": "If X then Z", "outcome": "refuted"}])
    )
    stmt, params = next(e for e in s.executed if "SET outcome" in e[0])
    assert params["outcome"] == "refuted"
    assert stats["outcomes"] == 1


def test_hypothesis_outcome_no_row_match_not_counted():
    # I6: trust rowcount — a norm_label that matches nothing must not
    # increment stats["outcomes"].
    s = _FakeSession(rowcount=0)
    stats = _apply_curator_output(
        s, _out(hypothesis_outcomes=[{"node_label": "If X then Z", "outcome": "refuted"}])
    )
    assert stats["outcomes"] == 0


def test_hypothesis_outcome_invalid_enum_is_dropped():
    s = _FakeSession()
    stats = _apply_curator_output(
        s, _out(hypothesis_outcomes=[{"node_label": "If X then Z", "outcome": "maybe"}])
    )
    assert stats["outcomes"] == 0
    assert stats["dropped"] == 1
    assert not any("SET outcome" in e[0] for e in s.executed)


# ---------------------------------------------------------------------------
# _paper_excerpt — references split, no-duplication, refs sample cap
# ---------------------------------------------------------------------------


def test_paper_excerpt_splits_references_and_samples_them():
    report = (
        "Intro prose about the topic.\n\n"
        "## References\n\n[1] Some Source, tier 1\n[2] Another Source, tier 2\n"
    )
    excerpt = _paper_excerpt(report)
    assert "Intro prose about the topic." in excerpt
    assert "[refs sample]" in excerpt
    assert "Some Source" in excerpt


def test_paper_excerpt_no_duplication_for_short_prose():
    # M10: prose <= 6000 chars must appear verbatim, not head+tail doubled.
    prose = "Short prose sentence. " * 50
    report = prose + "\n\n## References\n\n[1] Foo\n"
    excerpt = _paper_excerpt(report)
    assert excerpt.count("Short prose sentence.") == prose.count("Short prose sentence.")


def test_paper_excerpt_splits_head_and_tail_for_long_prose():
    prose = "A" * 4000 + "MIDDLE" + "B" * 4000
    report = prose + "\n\n## References\n\n[1] Foo\n"
    excerpt = _paper_excerpt(report)
    assert "MIDDLE" not in excerpt
    assert "A" * 100 in excerpt
    assert "B" * 100 in excerpt


def test_paper_excerpt_uses_last_heading_not_first():
    # F2: split_artifact matches the LAST "## References"-shaped line, built
    # for FINAL artifacts. The private _find_references_heading this
    # replaced matches the FIRST occurrence (documented for PRE-final
    # pipeline text) — on a final artifact, an earlier heading-shaped line
    # would truncate real trailing prose as if it were bibliography.
    report = (
        "Opening prose.\n\n"
        "## References\n\n"
        "Real conclusion that appears after an earlier heading-shaped line.\n\n"
        "## References\n\n"
        "[1] True Source\n"
    )
    excerpt = _paper_excerpt(report)
    assert "Real conclusion that appears after an earlier heading-shaped line." in excerpt
    assert "True Source" in excerpt


def test_paper_excerpt_respects_custom_budget():
    # F3: hypothesis-tail callers pass a tighter budget than a full
    # new-paper excerpt.
    prose = "A" * 2000 + "MIDDLE" + "B" * 2000
    report = prose + "\n\n## References\n\n" + ("Source " * 500)
    excerpt = _paper_excerpt(report, head=1000, tail=1500, refs_sample=800)
    assert "MIDDLE" not in excerpt
    assert "A" * 100 in excerpt
    assert "B" * 100 in excerpt
    refs_sample = excerpt.split("[refs sample]\n", 1)[1]
    assert len(refs_sample) <= 800


def test_paper_excerpt_caps_refs_sample_length():
    refs_body = "[1] " + ("Source " * 2000)
    report = "Prose.\n\n## References\n\n" + refs_body
    excerpt = _paper_excerpt(report)
    refs_sample = excerpt.split("[refs sample]\n", 1)[1]
    assert len(refs_sample) <= 1500


def test_paper_excerpt_no_references_heading_returns_prose_only():
    report = "Just prose, no references section at all."
    excerpt = _paper_excerpt(report)
    assert excerpt == report
    assert "[refs sample]" not in excerpt


# ---------------------------------------------------------------------------
# _build_user_message — key order, claim capping, oversized-papers budget
# ---------------------------------------------------------------------------


def test_build_user_message_orders_action_critical_keys_first():
    inputs = {
        "candidates": [{"label": "A"}],
        "open_hypotheses": [{"label": "H"}],
        "claims": [{"text": "c", "status": "open", "confidence": 0.5}],
        "papers": [
            {
                "request_id": "p1",
                "question": "q",
                "excerpt": "e",
                "completed_at": datetime(2026, 8, 1),
            }
        ],
    }
    message = _build_user_message(inputs)
    parsed = json.loads(message)
    assert list(parsed.keys())[:4] == ["candidates", "open_hypotheses", "claims", "papers"]


def test_build_user_message_caps_claims_count_and_text_length():
    claims = [{"text": "x" * 500, "status": "open", "confidence": 0.5} for _ in range(80)]
    inputs = {"candidates": [], "open_hypotheses": [], "claims": claims, "papers": []}
    message = _build_user_message(inputs)
    parsed = json.loads(message)
    assert len(parsed["claims"]) == 60
    assert all(len(c["text"]) <= 300 for c in parsed["claims"])


def test_build_user_message_drops_oversized_papers_keeps_hypotheses():
    big_excerpt = "x" * 30000
    inputs = {
        "candidates": [{"label": "A"}],
        "open_hypotheses": [{"label": "H1"}],
        "claims": [],
        "papers": [
            {
                "request_id": f"p{i}",
                "question": "q",
                "excerpt": big_excerpt,
                "completed_at": datetime(2026, 8, i + 1),
            }
            for i in range(5)
        ],
    }
    message = _build_user_message(inputs)
    assert len(message) <= 60000
    parsed = json.loads(message)
    assert parsed["open_hypotheses"] == [{"label": "H1"}]
    assert parsed.get("papers_deferred", 0) > 0
    assert len(parsed["papers"]) < 5


def test_build_user_message_warns_when_still_over_budget_with_no_papers(caplog):
    # F3(b): dropping every paper is not a guarantee the remaining sections
    # fit — the budget is advisory beyond that point, so surface it rather
    # than silently ship an oversized message.
    inputs = {
        "candidates": [{"label": "x" * 70000}],
        "open_hypotheses": [],
        "claims": [],
        "papers": [],
    }
    with caplog.at_level("WARNING"):
        message = _build_user_message(inputs)
    assert len(message) > 60000
    assert any("over budget" in r.message for r in caplog.records)


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


def test_run_curator_pass_empty_output_logs_failure_and_skips_apply(monkeypatch):
    # F1: `{}` is the DOCUMENTED dominant structured_llm_call failure mode
    # (returned only after both the structured call and its text-fallback
    # retry failed) — without a failure row here, thinking_pass_due's 20h
    # gate never closes and the feeder retries the same failing pass all
    # night. apply must still NOT run on unusable output.
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
    logged = []
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details: logged.append((kind, summary, details)),
    )

    curator.run_curator_pass()

    assert "called" not in applied
    assert logged, "expected a failure row — empty output must still close the 20h gate"
    kind, summary, details = logged[0]
    assert kind == "curator"
    assert "no usable output" in summary
    assert details == {"failed": True}


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
        lambda session, out: {
            "claims": 1,
            "connections": 2,
            "hypotheses": 0,
            "outcomes": 0,
            "dropped": 0,
            "demoted": 0,
        },
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
    assert "0 demoted" in logged["summary"]
    assert "0 dropped" in logged["summary"]
    assert logged["details"]["llm_summary"] == "did stuff"


def test_run_curator_pass_summary_surfaces_demoted_dropped_and_deferred(monkeypatch):
    # F3(c): demoted is the citation-integrity signal (an "established"
    # claim that didn't earn it) and must be visible in the human-readable
    # summary / Discord embed, not just buried in details.
    import pipeline.lyra.curator as curator

    big_excerpt = "x" * 30000
    papers = [
        {
            "request_id": f"p{i}",
            "question": "q",
            "excerpt": big_excerpt,
            "completed_at": datetime(2026, 8, i + 1),
        }
        for i in range(5)
    ]
    monkeypatch.setattr(
        curator,
        "_gather_inputs",
        lambda session: {
            "papers": papers,
            "candidates": [],
            "open_hypotheses": [],
            "claims": [],
            "last_paper_completed_at": datetime(2020, 1, 1),
        },
    )
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())
    monkeypatch.setattr(
        "pipeline.lyra.minimax_shared.structured_llm_call",
        lambda **kw: {"summary": "ok"},
    )
    monkeypatch.setattr(
        curator,
        "_apply_curator_output",
        lambda session, out: {
            "claims": 3,
            "connections": 0,
            "hypotheses": 0,
            "outcomes": 0,
            "dropped": 2,
            "demoted": 1,
        },
    )
    logged = {}
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details: logged.update(summary=summary, details=details),
    )
    monkeypatch.setattr("api.services.notify.send_discord_webhook", lambda payload: True)

    curator.run_curator_pass()  # real _build_user_message drops papers here

    assert "1 demoted" in logged["summary"]
    assert "2 dropped" in logged["summary"]
    assert "papers deferred" in logged["summary"]
    assert logged["details"]["papers_deferred"] > 0


def test_run_curator_pass_advances_cursor_to_included_papers_only(monkeypatch):
    # I7: the cursor must advance only past papers that actually made it
    # into the message that was sent (not everything _gather_inputs fetched
    # — a paper could have been dropped for size by _build_user_message).
    import pipeline.lyra.curator as curator

    papers = [
        {
            "request_id": "old",
            "question": "q",
            "excerpt": "e",
            "completed_at": datetime(2026, 8, 1),
        },
        {
            "request_id": "new",
            "question": "q",
            "excerpt": "e",
            "completed_at": datetime(2026, 8, 3),
        },
    ]
    monkeypatch.setattr(
        curator,
        "_gather_inputs",
        lambda session: {
            "papers": papers,
            "candidates": [],
            "open_hypotheses": [],
            "claims": [],
            "last_paper_completed_at": datetime(2020, 1, 1),
        },
    )
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())
    monkeypatch.setattr(
        "pipeline.lyra.minimax_shared.structured_llm_call",
        lambda **kw: {"summary": "ok"},
    )
    monkeypatch.setattr(
        curator,
        "_apply_curator_output",
        lambda session, out: {
            "claims": 0,
            "connections": 0,
            "hypotheses": 0,
            "outcomes": 0,
            "dropped": 0,
            "demoted": 0,
        },
    )
    logged = {}
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details: logged.update(details=details),
    )
    monkeypatch.setattr("api.services.notify.send_discord_webhook", lambda payload: True)

    curator.run_curator_pass()

    assert logged["details"]["last_paper_completed_at"] == "2026-08-03T00:00:00"


def test_run_curator_pass_swallows_exceptions_and_logs_failure_row(monkeypatch, caplog):
    import pipeline.lyra.curator as curator

    def boom(session):
        raise RuntimeError("db down")

    monkeypatch.setattr(curator, "_gather_inputs", boom)
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())

    logged = []
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details: logged.append((kind, summary, details)),
    )

    with caplog.at_level("ERROR"):
        curator.run_curator_pass()  # must not raise

    assert any("curator pass failed" in r.message for r in caplog.records)
    assert logged, "expected a failure row in thinking_log — closes the 20h schedule gate (I5/M17)"
    kind, summary, details = logged[0]
    assert kind == "curator"
    assert "Denkstunde failed" in summary
    assert details == {"failed": True}


def test_run_curator_pass_quota_exhausted_logs_distinct_failure_row(monkeypatch, caplog):
    import pipeline.lyra.curator as curator
    from pipeline.lyra.minimax_limiter import QuotaExhaustedError

    monkeypatch.setattr(curator, "_gather_inputs", lambda session: {"papers": []})
    monkeypatch.setattr("pipeline.database.get_session", lambda: _FakeCtxSession())

    def boom(**kw):
        raise QuotaExhaustedError("token plan exhausted")

    monkeypatch.setattr("pipeline.lyra.minimax_shared.structured_llm_call", boom)

    logged = []
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details: logged.append((kind, summary, details)),
    )

    with caplog.at_level("ERROR"):
        curator.run_curator_pass()  # must not raise

    assert logged
    kind, summary, details = logged[0]
    assert kind == "curator"
    assert "quota" in summary.lower()
    assert details == {"failed": True}
