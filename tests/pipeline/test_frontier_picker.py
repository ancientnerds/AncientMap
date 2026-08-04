"""Frontier picker extensions — stored question, synthesis quota (spec §4)."""

from pipeline.lyra.research_graph import (
    _allow_synthesis,
    pick_next_frontier_topic,
    question_for_node,
)


class _FakeSession:
    """Captures executed SQL/params; SELECT always returns no row (fetchone
    -> None) so pick_next_frontier_topic returns early after the SELECT —
    exactly the statement under test in the SQL-shape assertions below."""

    def __init__(self):
        self.executed = []

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))

        class _R:
            def fetchone(self):
                return None

        return _R()

    def commit(self):
        pass


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
    assert _allow_synthesis(["topic", "topic", "topic"]) is True
    assert _allow_synthesis(["connection", "topic", "topic"]) is False
    assert _allow_synthesis([]) is True
    assert _allow_synthesis(["hypothesis"]) is False


def test_pick_next_frontier_topic_sql_is_parameter_bound_with_all_kinds():
    s = _FakeSession()
    pick_next_frontier_topic(s, include_synthesis=True)
    stmt, params = s.executed[0]
    assert "n.kind = ANY(:kinds)" in stmt
    assert "n.question" in stmt
    assert "WHEN 'hypothesis' THEN 3.0" in stmt
    assert "WHEN 'connection' THEN 2.0" in stmt
    assert params["kinds"] == ["topic", "site", "connection", "hypothesis"]


def test_pick_next_frontier_topic_excludes_synthesis_kinds_when_disallowed():
    s = _FakeSession()
    pick_next_frontier_topic(s, include_synthesis=False)
    stmt, params = s.executed[0]
    assert params["kinds"] == ["topic", "site"]


def test_pick_next_frontier_topic_defaults_to_include_synthesis():
    s = _FakeSession()
    pick_next_frontier_topic(s)  # signature stays backward-compatible
    _, params = s.executed[0]
    assert params["kinds"] == ["topic", "site", "connection", "hypothesis"]
