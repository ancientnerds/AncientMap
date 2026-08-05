"""Frontier picker extensions — stored question, dedicated synthesis slot,
synthesis quota (spec §4).

The picker was redesigned from additive kind-weights to a dedicated slot
after a live-graph review showed additive weights can never win: frontier
head source_signal was 1180 (injector-accumulated, ~+120/day) against a
synthesis score ceiling of ~5.5 — a shared ranking put hypothesis nodes at
rank #80 of 1132, never picked.
"""

from pipeline.lyra.research_graph import (
    allow_synthesis,
    pick_next_frontier_topic,
    question_for_node,
    recent_batch_seed_kinds,
)


class _FakeSession:
    """Captures every executed SQL/params pair. `results` is a list of
    values consumed in call order by successive `execute(...).fetchone()`
    calls; a `None` entry means "no row found"."""

    def __init__(self, results=None):
        self.executed = []
        self._results = list(results or [])
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))

        result = self._results.pop(0) if self._results else None

        class _R:
            def fetchone(self):
                return result

        return _R()

    def commit(self):
        self.committed = True


def _row(kind="connection", id_="n1", label="A ↔ B", site_id=None, question="q"):
    return type(
        "Row",
        (),
        {"id": id_, "label": label, "kind": kind, "site_id": site_id, "question": question},
    )()


def test_question_for_node_prefers_stored_question():
    node = {"kind": "connection", "label": "A ↔ B", "question": "Does A explain B?"}
    assert question_for_node(node) == "Does A explain B?"


def test_question_for_node_falls_back_to_template():
    node = {"kind": "topic", "label": "Ein Sof", "question": None}
    assert "Ein Sof" in question_for_node(node)


def test_question_for_node_ignores_whitespace_only_stored_question():
    node = {"kind": "topic", "label": "Ein Sof", "question": "   "}
    assert "Ein Sof" in question_for_node(node)


def test_allow_synthesis_quota():
    # Max 1 of the last 3 weekend runs may be connection/hypothesis (spec §4).
    assert allow_synthesis(["topic", "topic", "topic"]) is True
    assert allow_synthesis(["connection", "topic", "topic"]) is False
    assert allow_synthesis([]) is True
    assert allow_synthesis(["hypothesis"]) is False


def test_pick_next_frontier_topic_tries_synthesis_slot_first():
    # Synthesis query returns a node -> that node wins, topic/site query
    # is never issued (dedicated slot, not a shared ranking).
    s = _FakeSession(results=[_row(kind="hypothesis")])
    node = pick_next_frontier_topic(s, include_synthesis=True)
    assert node["kind"] == "hypothesis"
    select_calls = [(stmt, p) for stmt, p in s.executed if p and "kinds" in p]
    assert len(select_calls) == 1
    assert select_calls[0][1]["kinds"] == ["connection", "hypothesis"]


def test_pick_next_frontier_topic_falls_back_when_synthesis_pool_empty():
    # First (synthesis) query finds nothing -> mandatory fallback to the
    # second (topic/site) query -- the feeder must never idle.
    s = _FakeSession(results=[None, _row(kind="topic", label="X")])
    node = pick_next_frontier_topic(s, include_synthesis=True)
    assert node["kind"] == "topic"
    select_calls = [(stmt, p) for stmt, p in s.executed if p and "kinds" in p]
    assert len(select_calls) == 2
    assert select_calls[0][1]["kinds"] == ["connection", "hypothesis"]
    assert select_calls[1][1]["kinds"] == ["topic", "site"]


def test_pick_next_frontier_topic_skips_synthesis_query_when_disallowed():
    s = _FakeSession(results=[_row(kind="topic", label="X")])
    pick_next_frontier_topic(s, include_synthesis=False)
    select_calls = [(stmt, p) for stmt, p in s.executed if p and "kinds" in p]
    assert len(select_calls) == 1
    assert select_calls[0][1]["kinds"] == ["topic", "site"]


def test_pick_next_frontier_topic_score_includes_real_age_term():
    # Follow-up-Ticket 4 (corrected 2026-08-05 review): a bare
    # `created_at ASC` ORDER BY tiebreak is inert here because `random() *
    # 0.5` is part of the sorted `score` column itself -- two float draws
    # essentially never tie, so ORDER BY never reaches the tiebreak. The
    # real fix puts the age term INSIDE the score: 0.5/day, capped at 3.0.
    s = _FakeSession(results=[_row(kind="connection")])
    pick_next_frontier_topic(s, include_synthesis=True)
    select_stmt = next(stmt for stmt, p in s.executed if p and "kinds" in p)
    assert "LEAST(EXTRACT(EPOCH FROM NOW() - n.created_at) / 86400.0 * 0.5, 3.0)" in select_stmt
    # The ASC tiebreak is kept too (harmless second ORDER BY key).
    assert "ORDER BY score DESC, n.created_at ASC" in select_stmt


def test_pick_next_frontier_topic_excludes_recently_failed_or_cancelled_nodes():
    # Follow-up-Ticket 5 (final review): a node reset to frontier after its
    # run terminally failed/was cancelled must cool down for 24h instead of
    # being picked again immediately in a tight reset->re-pick loop. Fresh
    # nodes (paper_id NULL, never attempted) are unaffected -- NOT EXISTS is
    # vacuously true when there's no research_requests row to match.
    s = _FakeSession(results=[_row(kind="connection")])
    pick_next_frontier_topic(s, include_synthesis=True)
    select_stmt = next(stmt for stmt, p in s.executed if p and "kinds" in p)
    assert "NOT EXISTS (" in select_stmt
    assert "rr.id = n.paper_id" in select_stmt
    assert "rr.status IN ('failed', 'cancelled')" in select_stmt
    assert "rr.completed_at > NOW() - INTERVAL '24 hours'" in select_stmt


def test_pick_next_frontier_topic_defaults_to_include_synthesis():
    s = _FakeSession(results=[_row(kind="connection")])
    pick_next_frontier_topic(s)  # signature stays backward-compatible
    select_calls = [(stmt, p) for stmt, p in s.executed if p and "kinds" in p]
    assert select_calls[0][1]["kinds"] == ["connection", "hypothesis"]


class _FakeFetchAllSession:
    """Session whose execute(...).fetchall() returns pre-seeded kind rows —
    for recent_batch_seed_kinds, which reads a list, not a single row."""

    def __init__(self, kind_rows):
        self.executed = []
        self._kind_rows = kind_rows

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        rows = self._kind_rows

        class _R:
            def fetchall(self):
                return [type("Row", (), {"kind": k})() for k in rows]

        return _R()


def test_recent_batch_seed_kinds_reads_limit_and_returns_kind_list():
    s = _FakeFetchAllSession(["topic", "connection", "topic"])
    kinds = recent_batch_seed_kinds(s)
    assert kinds == ["topic", "connection", "topic"]
    _, params = s.executed[0]
    assert params["limit"] == 3
